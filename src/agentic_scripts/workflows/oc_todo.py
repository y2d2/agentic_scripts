"""The ``oc-todo`` workflow: marker scan parsing, todo identity, the state schema and
run-planning decision table, the brief / PR renderers, and the full per-run pipeline.

Purpose:
    Provide every helper the OC-todo pipeline needs as a small, independently
    unit-testable function or dataclass — :func:`parse_grep_lines` (turn raw ``git grep``
    output into :class:`Todo` objects), :func:`todo_id` / :func:`todo_branch_name`
    (stable identity + the fresh-branch invariant), the v1 state schema helpers
    (:func:`fresh_state`, :func:`validate_state`, :func:`make_entry`) and the pure
    classifier :func:`plan_run` (the decision table that maps current todos + recorded
    state + PR lookups to one action per todo) — plus the byte-stable renderers
    (:func:`render_brief`, :func:`render_pr_title`, :func:`render_pr_body`) and the
    agent-report parser :func:`extract_report_sections`. The :class:`OCTodoWorkflow` class
    wires these into one idempotent run: clone-or-fetch per repo, per-branch scan, state
    diff, per-todo worktree, agent invocation, commit/push/PR, and a single atomic state
    persist.

Rationale:
    The scan model is a **local full clone + per-branch ``git grep``** (not the GitHub
    code-search API), because that API only considers the default branch, caps files at
    384 KB, and is rate-limited to 10 req/min — a local clone is deterministic, offline,
    and branch-complete. Each todo becomes **one PR**: the runner owns git (clone/fetch,
    worktree setup, commit, push, PR creation) while the ``oc-todo-resolver`` agent only
    edits code inside its sandboxed worktree (implement the todo, remove the marker line
    unless a keep-instruction applies, run the test command). Idempotency comes from two
    sources: the durable state document (one entry per todo id) and an existing-PR check
    by head ref — a ``pr_open`` todo whose PR is still open is skipped, one whose PR was
    merged is resolved, and one whose PR vanished or failed is re-processed. See the
    high-level plan at ``planning/workflows-oc-todo/workflows-oc-todo_plan.md``.

    State schema (v1) — entry statuses: **absent** = pending (never seen);
    ``"pr_open"`` (fields ``repo, branch, file, line, marker, branch_name, pr_number,
    pr_url, commit_sha, attempts, last_run_id, updated_at``); ``"failed"`` (the same
    minus the PR fields, plus ``last_error``); ``"resolved"`` (same as ``pr_open``,
    terminal). The operator re-bootstraps a corrupt state by deleting
    ``state/oc-todo.json`` (see :func:`validate_state`).

Usage:
    >>> from agentic_scripts.workflows.oc_todo import Todo, parse_grep_lines  # doctest: +SKIP
    >>> todos = parse_grep_lines("owner/name", "dev", "origin/dev", lines)  # doctest: +SKIP
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

from agentic_scripts.config import Config, OCTodo
from agentic_scripts.git import Git, GitError
from agentic_scripts.github import GitHubClient, GitHubError
from agentic_scripts.workflows.base import WorkflowResult

# --- Constants --------------------------------------------------------------- #

#: The strict, case-sensitive canonical marker. User decision (2026-10-14): the canonical
#: form only — lowercase ``oc-todo`` and ``#OC-todo`` (no colon) variants are deliberately
#: NOT matched (treated as intentional pruning of stale markers).
MARKER_PREFIX = "OC-todo:"

#: The state-document key under ``state/oc-todo.json``.
_STATE_KEY = "oc-todo"

#: The state-document schema version (v1; a mismatch is an operator error, not migrated).
_STATE_VERSION = 1

#: Mirror of the config default (``config.DEFAULT_MAX_TODOS_PER_REPO``) for direct-
#: construction tests that build a :class:`Todo` pipeline without loading the full config.
DEFAULT_MAX_TODOS_PER_REPO = 3

#: Sandbox layout sub-directories: clones live under ``<sandbox>/oc-todo/clones/<slug>`` and
#: worktrees under ``<sandbox>/oc-todo/wt/<slug>/<todo_id>`` (see :func:`clone_dir` /
#: :func:`worktree_dir`).
_CLONES_SUBDIR = "clones"
_WT_SUBDIR = "wt"

#: The keep-instruction scan window below the marker line (the marker line plus this many
#: following lines are checked for an ``oc-original`` note).
KEEP_CONTEXT_LINES = 3

#: Sentinel passed to :meth:`OCTodoWorkflow._process_todo` when the caller has not already
#: looked up the todo's PR. Disambiguates "no lookup performed yet" (→ do one) from a
#: lookup that ran and found no PR (``None``) — so each todo costs at most ONE API call per
#: run even when the classifier and the pipeline both want to know the PR state.
_NOT_LOOKED_UP = object()


# --- Identity and layout helpers --------------------------------------------- #


def repo_slug(repo: str) -> str:
    """Return the filesystem-safe slug for a repo id.

    Purpose:
        Map an ``owner/name`` repo id to a single path segment (``owner__name``) so clone
        and worktree directories can be nested without ambiguity.

    Args:
        repo: A repo id in ``owner/name`` form.

    Returns:
        The slug with ``/`` replaced by ``__`` (e.g. ``"owner/name" -> "owner__name"``).
    """
    return repo.replace("/", "__")


def clone_dir(sandbox_dir: Path, repo: str) -> Path:
    """Return the full-clone directory for ``repo`` under the sandbox.

    Args:
        sandbox_dir: The workflow's sandbox root (``ctx.sandbox_dir / "oc-todo"``).
        repo: A repo id in ``owner/name`` form.

    Returns:
        ``<sandbox_dir>/clones/<owner>__<repo>`` — the clone destination.
    """
    return sandbox_dir / _CLONES_SUBDIR / repo_slug(repo)


def worktree_dir(sandbox_dir: Path, repo: str, todo_id: str) -> Path:
    """Return the per-todo worktree directory under the sandbox.

    Args:
        sandbox_dir: The workflow's sandbox root (``ctx.sandbox_dir / "oc-todo"``).
        repo: A repo id in ``owner/name`` form.
        todo_id: The 12-char todo identity (see :func:`todo_id`).

    Returns:
        ``<sandbox_dir>/wt/<owner>__<repo>/<todo_id>`` — the worktree destination.
    """
    return sandbox_dir / _WT_SUBDIR / repo_slug(repo) / todo_id


def todo_id(repo: str, branch: str, file: str, marker: str) -> str:
    """Return the stable 12-char identity for a todo occurrence.

    Purpose:
        A todo is identified by where its marker lives (repo + branch + file) and what it
        says (the verbatim marker line). Collapsing to a short sha1 prefix keeps state keys
        compact while staying deterministic across runs.

    Args:
        repo: The ``owner/name`` repo id.
        branch: The branch the marker is on.
        file: The file path (relative to the repo root) containing the marker.
        marker: The exact marker line content (verbatim).

    Returns:
        The first 12 hex chars of ``sha1("repo|branch|file|marker")``.
    """
    # Spec mandates .encode("utf-8") (byte-stable identity); UP012 is style-only.
    digest = hashlib.sha1(f"{repo}|{branch}|{file}|{marker}".encode("utf-8")).hexdigest()  # noqa: UP012
    return digest[:12]


def todo_branch_name(tid: str) -> str:
    """Return the dedicated branch name for a todo id.

    Purpose:
        Enforce the fresh-branch invariant: every pushed branch starts with ``oc-todo/``,
        so no workflow ever pushes to a protected or pre-existing branch.

    Args:
        tid: The 12-char todo identity (see :func:`todo_id`).

    Returns:
        ``"oc-todo/<tid>"``.
    """
    return f"oc-todo/{tid}"


@dataclass(frozen=True)
class Todo:
    """One ``OC-todo:`` marker occurrence found by the scan.

    Attributes:
        repo: The ``owner/name`` repo id the marker was found in.
        branch: The branch (short name, no ``origin/`` prefix) the marker is on.
        file: The file path (relative to the repo root) containing the marker.
        line: The 1-based line number of the marker (a hint — it may have moved).
        marker: The exact marker line content, verbatim (the full line, not just the
            prefix).
        keep: Whether a keep-instruction applies (leave the marker line in place); set by
            the scanner from file context, False at parse time.

    Note:
        :attr:`id` and :attr:`branch_name` are derived properties — the identity is always
        recomputed from the fields, never stored separately.
    """

    repo: str
    branch: str
    file: str
    line: int
    marker: str
    keep: bool = False

    @property
    def id(self) -> str:
        """Return the stable 12-char identity for this todo (see :func:`todo_id`)."""
        return todo_id(self.repo, self.branch, self.file, self.marker)

    @property
    def branch_name(self) -> str:
        """Return the dedicated branch name for this todo (see :func:`todo_branch_name`)."""
        return todo_branch_name(self.id)


# --- Scan parsing ------------------------------------------------------------ #


def parse_grep_lines(repo: str, branch: str, ref: str, lines: list[str]) -> list[Todo]:
    """Parse raw ``git grep`` output lines into :class:`Todo` objects.

    Purpose:
        Turn the output of :meth:`Git.grep_fixed` (run against ``ref = "origin/<branch>"``)
        into structured todos. Each input line has the shape
        ``<ref>:<file>:<line-no>:<content>``; only lines whose **content** contains
        :data:`MARKER_PREFIX` are kept (a re-check — grep already filtered, this is defense
        in depth).

    Rationale:
        The file part is matched greedily so a ``:`` inside a file path does not break the
        parse (e.g. ``src/a:b.py``); the line number is anchored to be all digits and the
        content is everything after it. Unparseable lines are skipped, never raised — a ref
        with an odd path must not kill the scan.

    Args:
        repo: The ``owner/name`` repo id (stored on each :class:`Todo`).
        branch: The branch name (stored on each :class:`Todo`; the short name).
        ref: The ref that was grepped (e.g. ``"origin/dev"``); each line must begin with it.
        lines: The raw output lines from :meth:`Git.grep_fixed`.

    Returns:
        A list of :class:`Todo` (in input order), one per marker-bearing line; empty when
        no line carries the marker prefix. ``keep`` is always False here — the scanner sets
        it from file context in Task 4.
    """
    # Greedy file part (group 1) so a ":" inside a file path does not break the parse.
    pattern = re.compile(rf"^{re.escape(ref)}:(.+):(\d+):(.*)$")
    todos: list[Todo] = []
    for line in lines:
        match = pattern.match(line)
        if not match:
            continue  # unparseable (or a ref with an odd path) — skip, do not raise
        file_path, line_no, content = match.group(1), int(match.group(2)), match.group(3)
        if MARKER_PREFIX not in content:
            continue  # grep already filtered; this is defense in depth
        marker = content.rstrip()  # drop trailing newline/whitespace, keep leading comment chars
        todos.append(Todo(repo=repo, branch=branch, file=file_path, line=line_no, marker=marker))
    return todos


def has_keep_instruction(context_lines: list[str]) -> bool:
    """Return True when the context window carries an ``oc-original`` keep-instruction.

    Purpose:
        A keep-instruction means "implement the todo but leave the marker line verbatim".
        It is signalled by the literal ``oc-original`` (case-insensitive) appearing on the
        marker line or in the following :data:`KEEP_CONTEXT_LINES` lines.

    Args:
        context_lines: The marker line plus the next :data:`KEEP_CONTEXT_LINES` lines (the
            caller builds this via :meth:`Git.show_file`).

    Returns:
        True if any line contains ``"oc-original"`` case-insensitively, else False.
    """
    return any("oc-original" in line.lower() for line in context_lines)


def pr_state_from_api(pr: dict) -> str:
    """Map a GitHub PR object to its coarse state for the decision table.

    Purpose:
        Reduce the full PR payload to one of ``"merged"``, ``"open"``, or ``"closed"`` —
        the granularity :func:`plan_run` needs. A merged PR always wins (it may still carry
        a non-``closed`` state field).

    Args:
        pr: A GitHub pull-request object (a dict from the REST API).

    Returns:
        ``"merged"`` when ``pr["merged"] is True``; otherwise ``pr["state"]`` when it is
        ``"open"`` or ``"closed"``, else ``"closed"`` (the safe default for an odd state).
    """
    if pr.get("merged") is True:
        return "merged"
    state = pr.get("state")
    if state in ("open", "closed"):
        return state
    return "closed"


def clone_env_for(pat: str | None) -> dict[str, str] | None:
    """Build the git-auth environment triple for a PAT, or None when there is no PAT.

    Purpose:
        Inject the token as an ``http.extraHeader`` via git's config env vars so the PAT
        never appears in argv (it would otherwise show up in ``ps`` output). The triple sets
        exactly one extra header carrying the bearer token.

    Args:
        pat: The personal access token, or None/empty when no auth is needed (local mirror).

    Returns:
        ``None`` when ``pat`` is None or empty; otherwise a dict with
        ``GIT_CONFIG_COUNT=1``, ``GIT_CONFIG_KEY_0=http.extraHeader`` and
        ``GIT_CONFIG_VALUE_0="Authorization: Bearer <pat>"``.
    """
    if not pat:
        return None
    return {
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "http.extraHeader",
        "GIT_CONFIG_VALUE_0": f"Authorization: Bearer {pat}",
    }


# --- State schema (v1) ------------------------------------------------------- #


def fresh_state() -> dict:
    """Return a fresh v1 state document for a first run.

    Returns:
        ``{"version": 1, "todos": {}}`` — no todos recorded yet.
    """
    return {"version": _STATE_VERSION, "todos": {}}


def validate_state(st: dict) -> str | None:
    """Validate a loaded state document against the v1 schema.

    Purpose:
        There is no older state to migrate, so a mismatched shape is an operator error that
        must surface as a clear, actionable message telling the operator to delete the state
        file and let the workflow re-bootstrap (the mail-keeper pattern).

    Args:
        st: The parsed state document (possibly empty on a first run).

    Returns:
        None when ``st == {}`` (first run) or it matches v1; otherwise an error string that
        contains both ``"state schema mismatch"`` and ``"delete state/oc-todo.json"``.
    """
    if st == {}:
        return None  # no state yet → first run (the caller initialises it)
    if st.get("version") != _STATE_VERSION or not isinstance(st.get("todos"), dict):
        return (
            "state schema mismatch: expected version 1 with a 'todos' mapping — delete "
            "state/oc-todo.json and let the workflow re-bootstrap."
        )
    return None


def make_entry(todo: Todo, status: str, **fields) -> dict:
    """Build one state entry for a todo at ``status``.

    Purpose:
        Stamp an entry with its identity fields, the requested status, and a fresh UTC
        ISO-8601 ``updated_at`` (plus ``attempts`` defaulting to 0), so callers never forget
        the bookkeeping fields. Extra ``fields`` override or extend the base.

    Args:
        todo: The :class:`Todo` this entry describes.
        status: One of ``"pr_open"``, ``"failed"``, ``"resolved"`` (absent = pending, no entry).
        **fields: Additional/overriding fields (e.g. ``pr_number``, ``last_error``).

    Returns:
        A dict with the todo's identity fields, ``status``, ``attempts`` (default 0), and
        ``updated_at`` (UTC ISO-8601), merged with any extra ``fields``.
    """
    entry = {
        "repo": todo.repo,
        "branch": todo.branch,
        "file": todo.file,
        "line": todo.line,
        "marker": todo.marker,
        "status": status,
        "attempts": 0,
        "updated_at": datetime.now(UTC).isoformat(),
    }
    entry.update(fields)
    return entry


# --- Decision table ---------------------------------------------------------- #


def plan_run(current: list[Todo], st: dict, pr_states: dict[str, str | None]) -> list[dict]:
    """Classify current todos + recorded state into one action per todo (pure).

    Purpose:
        The heart of idempotency. Given the freshly-scanned ``current`` todos, the loaded
        state document ``st``, and ``pr_states`` (a ``todo_id -> "open" | "merged" |
        "closed" | "missing" | None`` map — only consulted for ``pr_open`` todos), return
        one action dict per current todo plus one per vanished state entry.

    Rationale:
        A todo is skipped only when a PR is already open for it (or its state is unknown due
        to an API error — the guardrail that never re-creates a PR on an outage). Merged or
        closed/missing PRs, failed attempts, and reappeared markers are all re-processed. A
        recorded entry whose marker has vanished (merged+removed or manually deleted) is
        resolved regardless of its prior status.

    Args:
        current: The todos found on this scan (in deterministic order).
        st: The loaded state document (``{"version": 1, "todos": {tid: entry}}``).
        pr_states: ``todo_id -> "open" | "merged" | "closed" | "missing" | None``; ``None``
            means the API lookup failed. Only looked up for ``pr_open`` todos.

    Returns:
        A list of action dicts. For a current todo: ``{"action": ..., "todo": <Todo>}`` plus
        an optional ``reason``. For a vanished entry: ``{"action": "resolve", "entry_id": tid,
        "entry": <entry>, "reason": ...}``.
    """
    todos = st.get("todos", {}) or {}
    actions: list[dict] = []

    current_ids = {todo.id for todo in current}
    for todo in current:
        entry = todos.get(todo.id)
        status = entry.get("status") if isinstance(entry, dict) else None

        if status is None or status == "failed":
            # Absent (pending) or a prior failure → process.
            actions.append({"action": "process", "todo": todo})
            continue

        if status == "pr_open":
            pr_state = pr_states.get(todo.id)  # may be None (API error) or absent
            if pr_state == "open":
                actions.append({"action": "skip", "todo": todo, "reason": "PR already open"})
            elif pr_state == "merged":
                actions.append({"action": "resolve", "todo": todo})
            elif pr_state == "closed":
                actions.append(
                    {
                        "action": "process",
                        "todo": todo,
                        "reason": "PR closed unmerged — retry",
                    }
                )
            elif pr_state == "missing":
                actions.append(
                    {
                        "action": "process",
                        "todo": todo,
                        "reason": "recorded PR no longer exists — re-verify",
                    }
                )
            else:  # None → API lookup failed; guardrail: never re-create on an outage
                actions.append(
                    {
                        "action": "skip",
                        "todo": todo,
                        "reason": "PR state unknown (API error) — guardrail: no re-creation",
                    }
                )
            continue

        if status == "resolved":
            actions.append(
                {
                    "action": "process",
                    "todo": todo,
                    "reason": "marker reappeared after resolution — re-attempt",
                }
            )
            continue

        # Unknown status (should not happen for a validated state) → process to be safe.
        actions.append({"action": "process", "todo": todo})

    # Vanished entries: recorded todos whose marker is no longer in the scan.
    for tid, entry in todos.items():
        if tid in current_ids:
            continue
        actions.append(
            {
                "action": "resolve",
                "entry_id": tid,
                "entry": entry,
                "reason": "marker no longer present",
            }
        )

    return actions


# --- Renderers --------------------------------------------------------------- #


def render_brief(run_id: str, todo: Todo, test_cmd: str | None) -> str:
    """Render the agent brief in the exact stable format the resolver reads by eye.

    Purpose:
        Produce the single self-contained dispatch message for one todo: a header naming the
        run and the one-todo scope, the marker/location/branch/test/keep-instruction fields,
        and the skill pointer + git-ownership mandate. The format is load-bearing — the agent
        reads it by eye — so it must stay byte-stable (one block, no extra blank lines).

    Args:
        run_id: The unique run identifier for this invocation.
        todo: The :class:`Todo` to resolve (marker verbatim, file/line hint, branch, keep flag).
        test_cmd: The configured test command, or None when none is set (rendered as ``none``).

    Returns:
        The brief string, exactly in the documented format.
    """
    keep = (
        "yes — implement the todo but leave the marker line verbatim"
        if todo.keep
        else "no — implement the todo and remove the marker line exactly"
    )
    return "\n".join(
        [
            f"oc-todo-resolver run {run_id} — resolve exactly ONE OC-todo marker in this "
            "sandboxed worktree.",
            "",
            f"Marker: {todo.marker}",
            f"Location: {todo.file}:{todo.line}  (hint — locate the marker by its exact "
            "text; the line may have moved)",
            f"Branch: {todo.branch}",
            f"Test command: {test_cmd if test_cmd else 'none'}",
            f"Keep-instruction: {keep}",
            "",
            "Follow skill: oc-todo-resolver (fix loop, marker rules, report shape).",
            "Do NOT run git commit or git push — the runner owns git and will commit, push, "
            "and open the PR after you exit.",
            "Your final message must be the result report (Summary / Files / Build / Tests / "
            "Acceptance Verification / Blockers).",
        ]
    )


def render_pr_title(marker: str) -> str:
    """Render a PR title from a marker line.

    Purpose:
        Produce ``"OC: " + <marker body, truncated to 72 chars>`` (no ellipsis — cut at
        char 72). The ``OC:`` prefix matches the repo's commit convention. The body is the
        marker with ONE leading comment decoration and its following whitespace stripped
        first (``#``, ``//``, ``;``, ``%``, or ``--``), then the leading :data:`MARKER_PREFIX`
        stripped if present, then whitespace-collapsed.

    Rationale:
        A typical marker is a comment line — ``# OC-todo: fix bug A`` — so stripping only
        the prefix (the old behaviour) leaked the comment decoration into the title and, via
        the pipeline's commit step, into the commit message. Stripping the decoration first
        makes ``# OC-todo: x``, ``%OC-todo: x`` and a bare ``OC-todo: x`` all yield the same
        clean body (``fix bug A`` / ``do x`` / ``fix``).

    Args:
        marker: The exact marker line content (verbatim, including any comment decoration).

    Returns:
        The PR title string (``"OC: " + <body[:72]>``).
    """
    body = marker.strip()
    # Strip ONE leading comment decoration plus its following whitespace (applied before the
    # prefix strip so a decorated marker and a bare marker both work).
    body = re.sub(r"^(?://|#|;|%|--)\s*", "", body)
    if body.startswith(MARKER_PREFIX):
        body = body[len(MARKER_PREFIX) :]
    collapsed = " ".join(body.split())
    return "OC: " + collapsed[:72]


def extract_report_sections(final_text: str | None) -> dict:
    """Best-effort parse of the agent's result report into named sections.

    Purpose:
        The PR body wants the agent's summary, file list, test verdict, and blockers. This
        extracts each as the text between its ``## <Heading>`` line and the next ``## ``
        heading (stripped). It is best-effort: a missing section yields ``""``, and None/empty
        input yields all-empty sections with ``has_report=False``.

    Args:
        final_text: The agent's final message (its result report), or None.

    Returns:
        A dict ``{"summary": str, "files": str, "tests": str, "blockers": str,
        "has_report": bool}``. ``blockers`` is left raw — the caller lowercases and compares
        it against ``"none"`` to decide whether any blocker was reported.
    """
    empty = {"summary": "", "files": "", "tests": "", "blockers": "", "has_report": False}
    if not final_text:
        return empty

    headings = {
        "## Summary": "summary",
        "## Files": "files",
        "## Build / Tests": "tests",
        "## Blockers": "blockers",
    }
    lines = final_text.splitlines()
    sections: dict[str, list[str]] = {key: [] for key in headings.values()}
    current: str | None = None
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            current = headings.get(stripped)  # None when it is a heading we do not capture
            continue
        if current is not None:
            sections[current].append(line)

    return {
        "summary": "\n".join(sections["summary"]).strip(),
        "files": "\n".join(sections["files"]).strip(),
        "tests": "\n".join(sections["tests"]).strip(),
        "blockers": "\n".join(sections["blockers"]).strip(),
        "has_report": True,
    }


def render_pr_body(todo: Todo, repo: str, sections: dict, run_id: str) -> str:
    """Render the PR body in the exact stable format (human review surface).

    Purpose:
        Quote the todo verbatim inside a fenced block, name the repo/base branch/location/
        keep-instruction, and embed the agent's report sections (with fallbacks when the
        report is unavailable), ending with an auto-open footer naming the run. The format is
        load-bearing for review, so it must stay byte-stable.

    Args:
        todo: The :class:`Todo` this PR resolves (marker verbatim, file/line, branch, keep flag).
        repo: The ``owner/name`` repo id (carried in the body header).
        sections: The dict from :func:`extract_report_sections` (may be all-empty).
        run_id: The unique run identifier (named in the footer).

    Returns:
        The PR body string, exactly in the documented format.
    """
    keep = "yes" if todo.keep else "no"
    summary = sections.get("summary") or "(agent report unavailable)"
    files = sections.get("files") or "-"
    tests = sections.get("tests") or "-"
    return "\n".join(
        [
            "## OC-todo resolution",
            "",
            f"- **Repo:** `{repo}`",
            f"- **Base branch:** `{todo.branch}`",
            "- **Marker (verbatim):**",
            "",
            "```",
            todo.marker,
            "```",
            "",
            f"- **Location:** `{todo.file}` line `{todo.line}`",
            f"- **Keep-instruction:** {keep}",
            "",
            "## Agent summary",
            "",
            summary,
            "",
            "## Files changed",
            "",
            files,
            "",
            "## Tests",
            "",
            tests,
            "",
            "---",
            f"*Opened automatically by agentic_scripts (run `{run_id}`). The marker was "
            f"found on branch `{todo.branch}` by the scheduled scan. Review before merging; "
            "merging removes the marker (unless a keep-instruction applies).*",
        ]
    )


def _is_step_exhausted(final_text: str | None) -> bool:
    """Return True when the agent's final message is opencode's step-cap boilerplate.

    Purpose:
        Detect that the agent hit its frontmatter ``steps`` cap mid-fix. When this happens,
        opencode still **exits 0** and uses the step-exhaustion boilerplate as the "final
        message" — so the runner cannot distinguish a step-exhausted run from a real success
        by exit code alone. Without this sentinel the workflow would record the todo resolved
        for a fix that never completed. The caller treats a step-exhausted "ok" as a failure:
        no state advance, and the todo is re-presented next run.

    Note:
        Deliberate duplicate of the 6-line
        :func:`agentic_scripts.workflows.mail_keeper._is_step_exhausted` sentinel — there
        are no cross-workflow imports (each workflow module is self-contained), so the small
        helper is copied rather than shared.

    Args:
        final_text: The agent's final message (its result report), or None.

    Returns:
        True when ``final_text`` contains (case-insensitive) one of the two stable fragments
        of opencode's step-cap boilerplate — ``maximum steps reached`` or ``maximum number of
        steps allowed``; False for None/empty or a normal report.
    """
    if not final_text:
        return False
    lowered = final_text.lower()
    return "maximum steps reached" in lowered or "maximum number of steps allowed" in lowered


def apply_cap(todos: list[Todo], cap: int) -> tuple[list[Todo], list[Todo]]:
    """Split ``todos`` into the first ``cap`` (to process) and the rest.

    Purpose:
        Enforce the per-run per-repo cap on how many todos are processed. The caller sorts
        ``todos`` deterministically before calling, so "first ``cap``" is well-defined.

    Args:
        todos: The todos in deterministic (caller-sorted) order.
        cap: The maximum number to process this run (an int >= 1).

    Returns:
        A ``(to_process, not_processed)`` tuple: the first ``cap`` todos and the remainder
        (empty when there are fewer than ``cap`` todos).
    """
    return todos[:cap], todos[cap:]


# --- Workflow shell ---------------------------------------------------------- #


def create(config: Config) -> "OCTodoWorkflow":  # noqa: UP037 - forward ref; class defined below
    """Create and return an :class:`OCTodoWorkflow` instance (the scheduler's entry point).

    Purpose:
        Production wiring for the config loader's import-check of enabled entries and the
        scheduler's per-run construction: build the workflow from the validated ``oc_todo``
        settings, using the real :class:`Git` and :class:`GitHubClient` collaborators (the
        constructor defaults) and leaving ``runner`` as None so it is resolved lazily from
        ``ctx.runner`` at call time.

    Args:
        config: The fully validated :class:`~agentic_scripts.config.Config`; its
            :attr:`Config.oc_todo` settings (repos, caps, per-repo test commands and
            clone-URL overrides) are used to build the workflow.

    Returns:
        A new :class:`OCTodoWorkflow`, ready to be run by the scheduler.

    Example:
        >>> wf = create(config)  # doctest: +SKIP
        >>> wf.name
        'oc-todo'
    """
    return OCTodoWorkflow(settings=config.oc_todo)


class OCTodoWorkflow:
    """The oc-todo workflow: one idempotent run over every configured repo.

    Purpose:
        Hold the injected collaborators and expose the stable :attr:`name` plus a full
        :meth:`run`: clone-or-fetch each repo, scan every branch for ``OC-todo:`` markers,
        diff against durable state, and — per todo, in order — open (or resume) one PR on a
        fresh ``oc-todo/<id>`` branch. Each run ends with a single atomic state persist.

    Rationale:
        Constructor injection (``git`` / ``github`` / ``runner``) is the hermetic-test seam:
        tests pass fakes for each collaborator, while production wiring (via ``create()`` in
        Task 5) passes the real :class:`Git`, :class:`GitHubClient`, and a runner resolved
        from the context at call time. The pipeline never raises for business failures —
        per-todo and per-repo faults are logged and reported in the :class:`WorkflowResult`
        (``status="error"`` when any business error accumulated), and every repo is scanned
        even if an earlier one failed.

    Attributes:
        name: The stable workflow name, matching its config key (``"oc-todo"``).
    """

    name = "oc-todo"

    def __init__(
        self,
        settings: OCTodo,
        *,
        git: Git | None = None,
        github: GitHubClient | None = None,
        runner=None,
    ) -> None:
        """Create the workflow with injected collaborators.

        Args:
            settings: The :class:`~agentic_scripts.config.OCTodo` settings (repos, caps,
                per-repo test commands and clone-URL overrides).
            git: The :class:`Git` helper; defaults to a fresh :class:`Git()` when None.
            github: The :class:`GitHubClient`; defaults to a fresh :class:`GitHubClient()`
                (reads ``GITHUB_PAT``) when None.
            runner: The agent runner; may be None, in which case it is resolved from
                ``ctx.runner`` at call time (Task 4).

        Note:
            The injected collaborators are stored privately and used by the run body; a None
            ``runner`` is not constructed here — it is resolved lazily from ``ctx.runner`` at
            call time so the constructor stays side-effect free.
        """
        self._settings = settings
        self._git = git if git is not None else Git()
        self._github = github if github is not None else GitHubClient()
        self._runner_override = runner

    # --- Pipeline helpers ---------------------------------------------------- #

    def _repo_url(self, repo: str) -> str:
        """Return the clone URL for ``repo`` (config override wins over the GitHub default).

        Purpose:
            Resolve where a repo is cloned from: an explicit ``oc_todo.repo_urls`` override
            (a local path or mirror — the hermetic-test seam) when present, else the default
            GitHub HTTPS URL for the ``owner/name`` id.

        Args:
            repo: The ``owner/name`` repo id.

        Returns:
            The override string when configured, else ``"https://github.com/<repo>.git"``.
        """
        return self._settings.repo_urls.get(repo) or f"https://github.com/{repo}.git"

    def _clone_or_fetch(self, ctx, repo: str, errors: list[str]) -> Path | None:
        """Clone ``repo`` into the sandbox on first sight, else fetch it.

        Purpose:
            Ensure a full local clone exists under :func:`clone_dir` and is current with the
            remote: when the directory is absent (or not a git repo) it is cloned from
            :meth:`_repo_url`; otherwise it is fetched (with ``--prune``). A PAT, if present
            in the environment at run time, is injected as git-auth env (never argv); public
            repos and local fixture URLs need none.

        Args:
            ctx: The shared :class:`~agentic_scripts.workflows.base.WorkContext`.
            repo: The ``owner/name`` repo id.
            errors: The run's business-error list; a clone/fetch failure appends one
                repo-level error string here (so the caller can continue to the next repo).

        Returns:
            The clone :class:`Path` on success, or None on a :class:`GitError` (logged with
            the stderr tail and recorded in ``errors``) — a repo failure never stops other
            repos.

        Side Effects:
            ``mkdir -p`` of the clone's parent; one ``git clone`` or ``git fetch`` per call.
        """
        path = clone_dir(ctx.sandbox_dir, repo)
        env = clone_env_for(os.environ.get("GITHUB_PAT", "").strip() or None)
        try:
            if not (path.exists() and self._git.is_repo(path)):
                path.parent.mkdir(parents=True, exist_ok=True)
                self._git.clone(self._repo_url(repo), path, env=env)
            else:
                self._git.fetch(path, env=env)  # prune by default
        except GitError as exc:
            ctx.logger.error("oc-todo: clone/fetch failed for %s: %s", repo, exc)
            errors.append(f"clone/fetch failed for {repo}: {exc}")
            return None
        return path

    def _scan_repo(self, ctx, repo: str, clone: Path) -> list[Todo]:
        """Scan every remote branch of ``clone`` for ``OC-todo:`` markers.

        Purpose:
            The local full-clone scan model: for each remote branch (short name), grep the
            committed ref ``origin/<branch>`` for :data:`MARKER_PREFIX`, parse the matches
            into :class:`Todo` objects, and — per todo — read the file at that ref to decide
            whether a keep-instruction applies (the marker line plus the next
            :data:`KEEP_CONTEXT_LINES` lines).

        Args:
            ctx: The shared :class:`~agentic_scripts.workflows.base.WorkContext`.
            repo: The ``owner/name`` repo id (stored on each :class:`Todo`).
            clone: The full-clone directory to scan.

        Returns:
            A deterministically sorted (by ``(branch, file, line)``) list of :class:`Todo`
            with :attr:`Todo.keep` set from file context; empty when no branch carries a
            marker.

        Side Effects:
            Read-only git calls (:meth:`Git.branches`, :meth:`Git.grep_fixed`,
            :meth:`Git.show_file`). A :class:`GitError` mid-branch (e.g. a vanished ref) is
            logged and that branch skipped — the scan continues.
        """
        todos: list[Todo] = []
        # Skip non-source branches: HEAD/origin (local-clone symref artifacts) and the
        # workflow's own oc-todo/* fix branches (scanning them would re-detect the same
        # marker on a branch that already carries it — including an orphan resume).
        branch_list = [
            b
            for b in self._git.branches(clone)
            if b not in ("HEAD", "origin") and not b.startswith("oc-todo/")
        ]
        for branch in branch_list:
            ref = f"origin/{branch}"
            try:
                lines = self._git.grep_fixed(clone, ref, MARKER_PREFIX)
            except GitError as exc:
                ctx.logger.warning(
                    "oc-todo: grep failed on %s@%s — skipping branch: %s", repo, ref, exc
                )
                continue
            for todo in parse_grep_lines(repo, branch, ref, lines):
                todos.append(self._with_keep(ctx, clone, ref, todo))
        todos.sort(key=lambda t: (t.branch, t.file, t.line))
        return todos

    def _with_keep(self, ctx, clone: Path, ref: str, todo: Todo) -> Todo:
        """Return ``todo`` with :attr:`Todo.keep` set from the file context at ``ref``.

        Purpose:
            Read the marker's file at ``ref`` and check the keep-instruction window (the
            marker line plus the next :data:`KEEP_CONTEXT_LINES` lines) for an
            ``oc-original`` note; a missing/unreadable file is treated as no-keep (logged).

        Args:
            ctx: The shared context (for logging).
            clone: The full-clone directory to read from.
            ref: The committed ref the marker was found on (e.g. ``"origin/dev"``).
            todo: The parsed :class:`Todo` (its :attr:`Todo.keep` is False at parse time).

        Returns:
            A copy of ``todo`` with :attr:`Todo.keep` set (the dataclass is frozen, so this
            uses :func:`dataclasses.replace`).
        """
        try:
            text = self._git.show_file(clone, ref, todo.file)
        except GitError as exc:
            ctx.logger.warning(
                "oc-todo: cannot read %s@%s for keep check — assuming no-keep: %s",
                todo.file,
                ref,
                exc,
            )
            return replace(todo, keep=False)
        lines = text.splitlines()
        start = max(0, todo.line - 1)
        context = lines[start : start + KEEP_CONTEXT_LINES + 1]
        return replace(todo, keep=has_keep_instruction(context))

    def _lookup_pr(self, owner: str, name: str, branch_name: str) -> dict | None | str:
        """Look up the PR whose head is ``owner:branch_name`` — at most ONE API call.

        Purpose:
            The single idempotency query for one todo. Every PR-state consumption (the
            :func:`plan_run` classifier and the pipeline) goes through this so a todo costs
            at most one ``find_pr_by_head`` per run; the caller caches the result in
            ``pr_cache`` and passes it back to :meth:`_process_todo`.

        Args:
            owner: The repo owner (the head ref's left side).
            name: The repo name.
            branch_name: The todo's ``oc-todo/<id>`` branch name.

        Returns:
            The raw PR dict when one exists, ``None`` when no PR has that head, or the string
            ``"api_error"`` on a :class:`GitHubError` (logged WARNING; guardrail: an unknown
            state is treated as "skip, never re-create").
        """
        try:
            return self._github.find_pr_by_head(owner, name, branch_name)
        except GitHubError as exc:
            logging.getLogger("agentic_scripts.oc_todo").warning(
                "oc-todo: PR lookup failed for %s:%s — guardrail (skip, never re-create): %s",
                owner,
                branch_name,
                exc,
            )
            return "api_error"

    def _process_todo(
        self,
        ctx,
        todo: Todo,
        test_cmd: str | None,
        clone: Path,
        cached_lookup: dict | None | str | object = _NOT_LOOKED_UP,
    ) -> dict:
        """Run one todo's full pipeline and return its outcome.

        Purpose:
            Take a single :class:`Todo` from scan to (attempted) PR: check for an existing
            PR (skip / resolve / retry), resume an orphan branch if the fix was already
            pushed, otherwise set up a fresh worktree, invoke the ``oc-todo-resolver`` agent,
            gate on its report, then commit, push, and open the PR. The worktree is always
            cleaned up (try/finally).

        Args:
            ctx: The shared :class:`~agentic_scripts.workflows.base.WorkContext`.
            todo: The :class:`Todo` to resolve (marker verbatim, file/line hint, branch, keep).
            test_cmd: The configured per-repo test command, or None.
            clone: The full-clone directory the worktree is created in and pushed from.
            cached_lookup: A PR dict / ``None`` / ``"api_error"`` already looked up by the
                caller (the classifier's lookup for a ``pr_open`` todo), or the
                :data:`_NOT_LOOKED_UP` sentinel to do one here — so each todo costs at most
                ONE API call per run.

        Returns:
            An outcome dict ``{"status", "reason", "pr_number", "pr_url", "commit_sha"}``
            where ``status`` is one of ``"pr_created"``, ``"skipped"``, ``"resolved"``, or
            ``"failed"``. Business failures are returned (never raised).

        Side Effects:
            At most one :meth:`Git.worktree_add`/``worktree_remove`` pair, at most one agent
            invocation, at most one push of a fresh ``oc-todo/<id>`` branch, and at most one
            PR creation. The worktree is removed in a ``finally`` (best-effort).
        """
        owner, name = todo.repo.split("/", 1)
        branch_name = todo.branch_name

        # --- Step 1: existing-PR check (at most ONE API call per run). --- #
        lookup = (
            cached_lookup
            if cached_lookup is not _NOT_LOOKED_UP
            else self._lookup_pr(owner, name, branch_name)
        )
        if isinstance(lookup, dict):
            if lookup.get("merged") is True:
                return self._outcome(
                    "resolved", "PR merged — todo resolved", None, lookup.get("html_url"), None
                )
            if lookup.get("state") == "open":
                return self._outcome(
                    "skipped",
                    f"PR already open #{lookup.get('number')}",
                    lookup.get("number"),
                    lookup.get("html_url"),
                    None,
                )
            # closed (unmerged) → fall through and retry.
        elif lookup == "api_error":
            return self._outcome(
                "skipped",
                "PR state unknown (API error) — guardrail: no re-creation",
                None,
                None,
                None,
            )
        # lookup is None (no PR) → fresh attempt or orphan resume below.

        # --- Step 2: orphan-branch resume (pushed branch, no PR). --- #
        try:
            commit_sha = self._git.rev_parse(clone, f"origin/{branch_name}")
        except GitError:
            commit_sha = None
        if commit_sha is not None:
            body_note = (
                "\n\n(Branch reused from a previous run — the agent's committed fix was "
                "already pushed; no agent re-run.)"
            )
            sections: dict = {}
            try:
                number, url = self._github.create_pr(
                    owner,
                    name,
                    title=render_pr_title(todo.marker),
                    body=render_pr_body(todo, todo.repo, sections, ctx.run_id) + body_note,
                    head=f"{owner}:{branch_name}",
                    base=todo.branch,
                )
            except GitHubError as exc:
                return self._outcome("failed", f"create_pr failed: {exc}", None, None, commit_sha)
            return self._outcome(
                "pr_created", "resumed orphan branch (no agent re-run)", number, url, commit_sha
            )

        # --- Steps 3–8 wrapped so the worktree is ALWAYS cleaned up. --- #
        wt = worktree_dir(ctx.sandbox_dir, todo.repo, todo.id)
        try:
            # Step 3: fresh attempt — drop a stale local branch, clean any leaked worktree.
            try:
                self._git.rev_parse(clone, branch_name)
                self._git.delete_branch(clone, branch_name)  # stale from a prior attempt
            except GitError:
                pass  # no local branch (the normal case) — nothing to delete
            if wt.exists():
                self._best_effort_remove_worktree(ctx, clone, wt)
            self._git.worktree_add(clone, wt, branch_name, f"origin/{todo.branch}")

            # Step 4: agent invocation.
            runner = self._runner_override or ctx.runner
            brief = render_brief(ctx.run_id, todo, test_cmd)
            res = runner.run(
                agent="oc-todo-resolver",
                brief=brief,
                work_dir=wt,
                title=f"oc-todo {todo.id} ({ctx.run_id})",
            )

            # Step 5: agent gate.
            if res.status in {"error", "timeout"}:
                return self._outcome(
                    "failed", f"agent {res.status}: {res.error or res.status}", None, None, None
                )
            if res.status == "ok" and _is_step_exhausted(res.final_text):
                return self._outcome(
                    "failed", "agent hit its step cap — no complete fix", None, None, None
                )
            sections = extract_report_sections(res.final_text)
            blockers = sections["blockers"].strip().lower()
            if blockers not in ("", "none"):
                return self._outcome(
                    "failed",
                    f"agent reported blockers: {sections['blockers'][:200]}",
                    None,
                    None,
                    None,
                )

            # Step 6: commit (the idempotency primitive — False when the agent changed nothing).
            self._git.add(wt)
            created = self._git.commit(wt, render_pr_title(todo.marker))
            if created is False:
                return self._outcome(
                    "failed", "agent made no changes — nothing to commit", None, None, None
                )
            commit_sha = self._git.rev_parse(wt, "HEAD")

            # Step 7: push the fresh branch (never a protected/pre-existing one).
            try:
                self._git.push(wt, branch_name, upstream=True)
            except GitError as exc:
                return self._outcome("failed", f"push failed: {exc}", None, None, commit_sha)

            # Step 8: open the PR.
            number, url = self._github.create_pr(
                owner,
                name,
                title=render_pr_title(todo.marker),
                body=render_pr_body(todo, todo.repo, sections, ctx.run_id),
                head=f"{owner}:{branch_name}",
                base=todo.branch,
            )
            return self._outcome(
                "pr_created", "PR created from fresh worktree", number, url, commit_sha
            )
        except GitError as exc:
            return self._outcome("failed", f"git failure: {exc}", None, None, None)
        finally:
            # Step 9: cleanup (ALWAYS) — a leaked worktree is loud, not fatal.
            self._best_effort_remove_worktree(ctx, clone, wt)

    def _best_effort_remove_worktree(self, ctx, clone: Path, wt: Path) -> None:
        """Remove ``wt`` from ``clone`` best-effort (never raises).

        Purpose:
            The pipeline's cleanup primitive: remove the per-todo worktree and, on failure,
            fall back to a prune + ``rmtree`` so a leaked directory never bricks the next
            attempt. Each step is wrapped — a :class:`GitError` is logged (WARNING) and the
            remaining fallbacks still run.

        Args:
            ctx: The shared context (for logging).
            clone: The full-clone repository the worktree is registered in.
            wt: The worktree directory to remove (may already be gone).
        """
        if not wt.exists():
            return
        try:
            self._git.worktree_remove(clone, wt, force=True)
        except GitError as exc:
            ctx.logger.warning("oc-todo: worktree_remove failed for %s — falling back: %s", wt, exc)
            self._prune_best_effort(ctx, clone)
            shutil.rmtree(wt, ignore_errors=True)
        # Remove the now-empty per-repo parent dir so no worktree dirs remain under
        # <sandbox>/wt (a leftover empty dir would be noise in the sandbox).
        parent = wt.parent
        try:
            if parent.is_dir() and not any(parent.iterdir()):
                parent.rmdir()
        except OSError:
            pass  # a non-empty or vanished parent is harmless — leave it

    def _prune_best_effort(self, ctx, clone: Path) -> None:
        """Run ``git worktree prune`` best-effort (a failure is logged, never raised)."""
        try:
            self._git.prune_worktrees(clone)
        except GitError as exc:
            ctx.logger.warning("oc-todo: worktree prune failed for %s: %s", clone, exc)

    @staticmethod
    def _outcome(status: str, reason: str, pr_number, pr_url, commit_sha) -> dict:
        """Build a :meth:`_process_todo` outcome dict (a small shared helper)."""
        return {
            "status": status,
            "reason": reason,
            "pr_number": pr_number,
            "pr_url": pr_url,
            "commit_sha": commit_sha,
        }

    # --- Run orchestration --------------------------------------------------- #

    def run(self, ctx) -> WorkflowResult:
        """Perform one complete, idempotent oc-todo run and report its outcome.

        Purpose:
            Wire the core into a full run over every configured repo (config order,
            sequential): clone-or-fetch → per-branch scan → PR-state lookups for the
            ``pr_open`` subset → :func:`plan_run` classification → per-todo pipeline (capped)
            → vanished-entry resolution → a single atomic state persist.

        Idempotency contract:
            State is consulted BEFORE acting; a re-run never duplicates a PR. A ``pr_open``
            todo whose PR is still open is skipped, one whose PR merged is resolved, and one
            whose PR failed/vanished is re-processed. Merged+removed or manually-deleted
            markers resolve their recorded entries.

        Failure contract:
            Per-todo failures become ``failed`` state (retryable next gate-open run) AND a
            business error in the result; repo-level clone/fetch failures are logged and the
            other repos continue; the run returns ``status="error"`` only when at least one
            business error accumulated. Unexpected exceptions map to ``status="error"``.

        Args:
            ctx: The shared :class:`~agentic_scripts.workflows.base.WorkContext`.

        Returns:
            A :class:`WorkflowResult` (``items_found`` = total current markers across all
            repos; ``actions`` the side-effect notes; ``errors`` the business failures).

        Side Effects:
            Clones/fetches into the sandbox, one PR per processed todo on a fresh branch, and
            (only when the state document changed) one atomic :meth:`StateStore.save`.
        """
        try:
            return self._run(ctx)
        except Exception as exc:  # noqa: BLE001 - map unexpected exceptions to a business error
            ctx.logger.error("oc-todo run failed unexpectedly: %s", exc)
            return WorkflowResult(
                status="error", errors=[f"unexpected error during oc-todo run: {exc}"]
            )

    def _run(self, ctx) -> WorkflowResult:
        """The unwrapped run body (called by :meth:`run`, which maps exceptions)."""
        actions_out: list[str] = []
        errors: list[str] = []

        # --- 1. No repos configured → no-op (no state write). --- #
        if not self._settings.repos:
            return WorkflowResult(
                status="ok", items_found=0, actions=["no repos configured — nothing to scan"]
            )

        # --- 2. Load + validate state. --- #
        st = ctx.state.load(_STATE_KEY)
        err = validate_state(st)
        if err is not None:
            return WorkflowResult(status="error", errors=[err])
        if st == {}:
            st = fresh_state()

        todos_map: dict[str, dict] = st.setdefault("todos", {})
        loaded_snapshot = json.dumps(st, sort_keys=True)
        items_found = 0

        # --- 3. Per repo (config order), sequential. A repo failure never stops others. --- #
        for repo in self._settings.repos:
            clone = self._clone_or_fetch(ctx, repo, errors)
            if clone is None:
                continue  # repo-level error already recorded; continue to the next repo

            current = self._scan_repo(ctx, repo, clone)
            items_found += len(current)
            ctx.logger.info(
                "oc-todo: %s — found %d marker(s)",
                repo,
                len(current),
            )

            # 3c. PR-state lookups for the pr_open subset (one API call each).
            pr_cache: dict[str, dict | None | str] = {}
            pr_states: dict[str, str | None] = {}
            for todo in current:
                entry = todos_map.get(todo.id)
                if isinstance(entry, dict) and entry.get("status") == "pr_open":
                    lookup = self._lookup_pr(*todo.repo.split("/", 1), todo.branch_name)
                    pr_cache[todo.id] = lookup
                    if isinstance(lookup, dict):
                        pr_states[todo.id] = pr_state_from_api(lookup)
                    elif lookup is None:
                        pr_states[todo.id] = "missing"
                    else:  # "api_error"
                        pr_states[todo.id] = None

            actions = plan_run(current, st, pr_states)
            process_queue = [a["todo"] for a in actions if a["action"] == "process"]
            to_process, not_processed = apply_cap(process_queue, self._settings.max_todos_per_repo)
            test_cmd = self._settings.test_commands.get(repo)

            # 3d. Process the capped queue in order; route outcome notes per spec.
            for todo in to_process:
                old_entry = todos_map.get(todo.id)
                old_attempts = (
                    int(old_entry.get("attempts", 0)) if isinstance(old_entry, dict) else 0
                )
                outcome = self._process_todo(
                    ctx,
                    todo,
                    test_cmd,
                    clone,
                    cached_lookup=pr_cache.get(todo.id, _NOT_LOOKED_UP),
                )
                self._apply_outcome(
                    ctx, repo, todo, old_attempts, outcome, todos_map, actions_out, errors
                )

            # 3e. Skip / resolve actions (state unchanged for skip; resolved for resolve).
            for action in actions:
                kind = action["action"]
                if kind == "skip":
                    t = action["todo"]
                    reason = action.get("reason", "PR already open")
                    actions_out.append(f"skipped {t.repo} ({t.file}:{t.line}): {reason}")
                elif kind == "resolve" and "entry_id" not in action:
                    todo = action["todo"]
                    todos_map[todo.id] = make_entry(todo, "resolved", last_run_id=ctx.run_id)
                    actions_out.append(
                        f"resolved {todo.repo} ({todo.file}:{todo.line}): PR merged — resolved"
                    )

            # 3f. Vanished entries (recorded but no longer in the scan) → resolved.
            for action in actions:
                if action["action"] == "resolve" and "entry_id" in action:
                    tid = action["entry_id"]
                    todos_map[tid] = make_entry(
                        Todo(
                            repo=(action.get("entry") or {}).get("repo", repo),
                            branch=(action.get("entry") or {}).get("branch", ""),
                            file=(action.get("entry") or {}).get("file", "?"),
                            line=int((action.get("entry") or {}).get("line", 0)),
                            marker=(action.get("entry") or {}).get("marker", ""),
                        ),
                        "resolved",
                        last_run_id=ctx.run_id,
                    )
                    actions_out.append(
                        f"resolved {repo} (recorded entry {tid}): marker no longer present"
                    )

            if not_processed:
                actions_out.append(
                    f"{len(not_processed)} todo(s) not processed this run "
                    f"(cap {self._settings.max_todos_per_repo})"
                )

        # --- 4. Single atomic state save, only when the document changed. --- #
        if json.dumps(st, sort_keys=True) != loaded_snapshot:
            ctx.state.save(_STATE_KEY, st)

        return WorkflowResult(
            status="error" if errors else "ok",
            items_found=items_found,
            actions=actions_out,
            errors=errors,
        )

    def _apply_outcome(
        self,
        ctx,
        repo: str,
        todo: Todo,
        old_attempts: int,
        outcome: dict,
        todos_map: dict[str, dict],
        actions_out: list[str],
        errors: list[str],
    ) -> None:
        """Apply one :meth:`_process_todo` outcome to the in-memory state + result lists.

        Purpose:
            The spec's outcome routing: ``pr_created``/``skipped``/``resolved`` append a note
            to ``actions_out`` (and update the state entry for ``pr_created``/``resolved``);
            ``failed`` appends a business error to ``errors`` AND sets the state entry to
            ``failed`` (retryable next run).

        Args:
            ctx: The shared context (for logging + ``run_id``).
            repo: The ``owner/name`` repo id.
            todo: The :class:`Todo` this outcome is for.
            old_attempts: The entry's prior attempt count (0 when absent) — incremented on a
                new attempt (``pr_created`` / ``failed``).
            outcome: The dict returned by :meth:`_process_todo`.
            todos_map: The state document's ``"todos"`` mapping (mutated in place).
            actions_out: The run's side-effect note list (appended to).
            errors: The run's business-error list (appended to on failure).
        """
        status = outcome["status"]
        if status == "pr_created":
            todos_map[todo.id] = make_entry(
                todo,
                "pr_open",
                pr_number=outcome["pr_number"],
                pr_url=outcome["pr_url"],
                commit_sha=outcome["commit_sha"],
                attempts=old_attempts + 1,
                last_run_id=ctx.run_id,
            )
            actions_out.append(f"PR #{outcome['pr_number']} for {repo} ({todo.file}:{todo.line})")
        elif status == "skipped":
            actions_out.append(f"skipped {repo} ({todo.file}:{todo.line}): {outcome['reason']}")
        elif status == "resolved":
            todos_map[todo.id] = make_entry(todo, "resolved", last_run_id=ctx.run_id)
            actions_out.append(f"resolved {repo} ({todo.file}:{todo.line}): {outcome['reason']}")
        else:  # failed — a business error AND retryable state
            todos_map[todo.id] = make_entry(
                todo,
                "failed",
                last_error=outcome["reason"],
                attempts=old_attempts + 1,
                last_run_id=ctx.run_id,
            )
            errors.append(f"{repo} ({todo.file}:{todo.line}): {outcome['reason']}")
            ctx.logger.warning(
                "oc-todo: %s (%s:%d) failed: %s", repo, todo.file, todo.line, outcome["reason"]
            )
