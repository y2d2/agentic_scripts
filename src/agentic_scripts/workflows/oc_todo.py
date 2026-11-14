"""The ``oc-todo`` workflow core: marker scan parsing, todo identity, the state schema and
run-planning decision table, and the brief / PR renderers — plus the pure helpers the
pipeline needs. No orchestration yet (the ``run`` method lands in Task 4).

Purpose:
    Provide every helper the OC-todo pipeline needs as a small, independently
    unit-testable function or dataclass: :func:`parse_grep_lines` (turn raw ``git grep``
    output into :class:`Todo` objects), :func:`todo_id` / :func:`todo_branch_name`
    (stable identity + the fresh-branch invariant), the v1 state schema helpers
    (:func:`fresh_state`, :func:`validate_state`, :func:`make_entry`) and the pure
    classifier :func:`plan_run` (the decision table that maps current todos + recorded
    state + PR lookups to one action per todo), and the byte-stable renderers
    (:func:`render_brief`, :func:`render_pr_title`, :func:`render_pr_body`) plus the
    agent-report parser :func:`extract_report_sections`.

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
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from agentic_scripts.config import OCTodo
from agentic_scripts.git import Git
from agentic_scripts.github import GitHubClient

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
                actions.append(
                    {"action": "skip", "todo": todo, "reason": "PR already open"}
                )
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
        Produce ``"OC: " + <marker with the leading MARKER_PREFIX removed, whitespace-
        collapsed, truncated to 72 chars>`` (no ellipsis — cut at char 72). The ``OC:``
        prefix matches the repo's commit convention.

    Args:
        marker: The exact marker line content (verbatim).

    Returns:
        The PR title string.
    """
    body = marker[len(MARKER_PREFIX) :] if marker.startswith(MARKER_PREFIX) else marker
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


class OCTodoWorkflow:
    """The oc-todo workflow (shell only in this task — ``run`` lands in Task 4).

    Purpose:
        Hold the injected collaborators and expose the stable :attr:`name`. The pipeline
        itself (clone/fetch, scan, worktree setup, agent invocation, commit/push/PR, state)
        is added in Task 4; this class exists so the constructor-injection seam and the
        name are testable now.

    Rationale:
        Constructor injection (``git`` / ``github`` / ``runner``) is the hermetic-test seam:
        tests pass fakes for each collaborator, while production wiring (via ``create()`` in
        Task 5) passes the real :class:`Git`, :class:`GitHubClient`, and a runner resolved
        from the context at call time.

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
            The injected collaborators are stored privately and used by the (Task 4) run
            body; a None ``runner`` is not constructed here — it is resolved lazily so the
            constructor stays side-effect free.
        """
        self._settings = settings
        self._git = git if git is not None else Git()
        self._github = github if github is not None else GitHubClient()
        self._runner_override = runner
