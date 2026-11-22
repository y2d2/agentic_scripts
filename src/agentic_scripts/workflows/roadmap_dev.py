"""The ``roadmap-dev`` workflow core: reviewed-plan identity + discovery, the ``plans.md``
listing parser/renderer, the user-cell-preserving reconciler, the state machine + reaper,
and the brief / commit-message renderers — the shell runs phase 1 (reaper, scan,
reconcile, push) on every run; the idle-gated drain is stubbed until Task 4.

Purpose:
    Provide every helper the roadmap-dev pipeline needs as a small, independently
    unit-testable function or dataclass: :func:`plan_folder_hash` / :func:`plan_identity`
    (the reviewed-plan identity — repo + branch + plan-folder path + content hash of the
    plan folder EXCLUDING the workflow-written diagnostics), :func:`discover_plans` (the
    pure scan filter), the v1 state schema helpers (:func:`fresh_state`,
    :func:`validate_state`, :func:`make_plan_entry`), the byte-stable ``plans.md`` listing
    pair (:func:`parse_listing` / :func:`render_listing`), the pure :func:`reconcile`
    (workflow-owned cells vs user-owned cells, row-drop rules, re-arm), the state machine
    (:func:`reap_orphans`, :func:`apply_job_outcome`), and the renderers
    (:func:`render_brief`, :func:`job_status_from_report`, :func:`render_commit_title`,
    :func:`archive_commit_message`, :func:`diag_commit_message`). The
    :class:`RoadmapDevWorkflow` shell (``create`` + ``run``) wires the constructor seams
    and implements phase 1: the run-start reaper (orphan flip + worktree cleanup), the
    per-repo clone/fetch + all-branch scan, the listing read/reconcile/commit/push (one
    non-fast-forward retry), and the atomic state persist; the idle-gated drain is a stub
    until Task 4.

Rationale:
    A **reviewed plan** is a folder ``planning/<topic>/work_plan.md`` (+ task files) on a
    branch of an allowed repo. Its identity is repo + branch + folder path + sha256 of the
    folder's files **excluding** ``questions.md`` and ``failure.md`` (workflow-written
    diagnostics must not change identity); any user edit of any other plan file yields a
    new identity and a new listing row. The live listing (``ARP_prompts/plans.md``) is a
    per-repo ``#`` / per-branch ``##`` table with exactly the columns
    :data:`LISTING_COLUMNS`; the reconciler owns the ``title`` and ``state`` cells and
    preserves the user-owned ``approval`` / ``priority`` / ``remove`` cells (the one
    sanctioned state-cell edit is re-arming a ``failure`` row to ``open``). Delivery is
    the pushed attempt branch — **this workflow never creates PRs and never calls the
    GitHub API** (user decision 2026-11-21: PR/merge is human-level verification; all git
    over SSH). Every function in the core is pure: no git, no network, no subprocess, and
    no ``datetime.now()`` at call sites — time enters only through the injected
    ``now: datetime`` argument (UTC ISO-8601 stamps). The workflow shell takes the already
    composed sandbox root (``ctx.sandbox_dir / "roadmap-dev"``) in its layout helpers,
    mirroring :mod:`agentic_scripts.workflows.oc_todo`.

State schema (v1) — ``state/roadmap-dev.json``:
    ``{"version": 1, "plans": {<identity>: entry}}`` with entry fields ``identity, repo,
    branch, path, title, content_hash, state ("open" | "pending" | "review" | "success" |
    "failure"), attempt, started_at, finished_at, pid, branch_name, commit_sha,
    last_error, last_run_id, updated_at``. ``open`` is startable with ☑; ``pending`` is a
    running job (not startable); ``review`` means major questions sit in ``questions.md``
    (startable once the user re-☑'s); ``success`` is terminal (attempt branch pushed,
    human verifies/merges — removable via ``remove`` ☑); ``failure`` is re-armed by the
    user setting the state cell ``open``. The operator re-bootstraps a corrupt state by
    deleting ``state/roadmap-dev.json`` (see :func:`validate_state`).

Usage:
    >>> from agentic_scripts.workflows.roadmap_dev import Plan, discover_plans  # doctest: +SKIP
    >>> plans = discover_plans("owner/name", "main", entries)  # doctest: +SKIP
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from agentic_scripts.config import Config, RoadmapPrompts
from agentic_scripts.git import Git, GitError
from agentic_scripts.workflows.base import WorkflowResult

# --- Constants --------------------------------------------------------------- #

#: The state-document key under ``state/roadmap-dev.json``.
_STATE_KEY = "roadmap-dev"

#: The state-document schema version (v1; a mismatch is an operator error, not migrated).
_STATE_VERSION = 1

#: Workflow-written diagnostics whose changes must NOT change a plan's identity (they live
#: on the plan's branch as small ``OC:`` commits and are the review/re-arm surface).
DIAGNOSTIC_FILES = frozenset({"questions.md", "failure.md"})

#: A plan folder under this path segment is archived (the whole folder is moved to
#: ``planning/archived/<topic>/``) and must not be discovered.
ARCHIVED_SEGMENT = "archived"

#: The plan-listing columns, in order (the exact header row of ``plans.md``).
LISTING_COLUMNS = ("approval", "priority", "plan", "title", "state", "remove")

#: The exact header row the renderer emits (and the parser skips).
_LISTING_HEADER = "| approval | priority | plan | title | state | remove |"

#: The exact separator row the renderer emits (and the parser skips). Widths are copied
#: verbatim from the listing contract sample (header width + 2).
_LISTING_SEPARATOR = "|----------|----------|------|-------|-------|--------|"

#: Sandbox layout sub-directories (the workflow-level root is ``ctx.sandbox_dir /
#: "roadmap-dev"``, composed by the workflow shell): clones under
#: ``<root>/clones/<slug>``, execution worktrees under ``<root>/wt/<slug>/<identity>``,
#: diagnostics worktrees under ``<root>/diag/<slug>/<identity>``, and the listing-repo
#: clone under ``<root>/prompts`` (see the ``*_dir`` helpers below).
_CLONES_SUBDIR = "clones"
_WT_SUBDIR = "wt"
_DIAG_SUBDIR = "diag"
_PROMPTS_SUBDIR = "prompts"

#: The job outcomes the pipeline reports back (see :func:`apply_job_outcome`).
_OUTCOME_STATES = {"success": "success", "questions": "review", "failure": "failure"}

#: The ``kind`` values accepted by :func:`diag_commit_message`.
_DIAG_KINDS = ("questions", "failure")

#: The result-report status line the brief mandates (first match wins, case-insensitive).
_STATUS_LINE_RE = re.compile(r"^\s*status\s*:\s*(success|questions|failure)\s*$", re.IGNORECASE)


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
        sandbox_dir: The workflow's sandbox root (``ctx.sandbox_dir / "roadmap-dev"`` —
            already composed by the workflow shell).
        repo: A repo id in ``owner/name`` form.

    Returns:
        ``<sandbox_dir>/clones/<owner>__<name>`` — the clone destination.
    """
    return sandbox_dir / _CLONES_SUBDIR / repo_slug(repo)


def plan_worktree_dir(sandbox_dir: Path, repo: str, identity: str) -> Path:
    """Return the per-plan execution worktree directory under the sandbox.

    Args:
        sandbox_dir: The workflow's sandbox root (``ctx.sandbox_dir / "roadmap-dev"``).
        repo: A repo id in ``owner/name`` form.
        identity: The 12-char plan identity (see :func:`plan_identity`).

    Returns:
        ``<sandbox_dir>/wt/<owner>__<name>/<identity>`` — the execution worktree
        destination (fresh attempt branch ``roadmap-dev/<identity>-<attempt>``).
    """
    return sandbox_dir / _WT_SUBDIR / repo_slug(repo) / identity


def diag_worktree_dir(sandbox_dir: Path, repo: str, identity: str) -> Path:
    """Return the per-plan diagnostics worktree directory under the sandbox.

    Args:
        sandbox_dir: The workflow's sandbox root (``ctx.sandbox_dir / "roadmap-dev"``).
        repo: A repo id in ``owner/name`` form.
        identity: The 12-char plan identity (see :func:`plan_identity`).

    Returns:
        ``<sandbox_dir>/diag/<owner>__<name>/<identity>`` — the worktree used to commit
        ``questions.md`` / ``failure.md`` onto the plan's branch.
    """
    return sandbox_dir / _DIAG_SUBDIR / repo_slug(repo) / identity


def prompts_clone_dir(sandbox_dir: Path) -> Path:
    """Return the listing-repo clone directory under the sandbox.

    Args:
        sandbox_dir: The workflow's sandbox root (``ctx.sandbox_dir / "roadmap-dev"``).

    Returns:
        ``<sandbox_dir>/prompts`` — the single clone of the listing repo (there is exactly
        one listing repo, so no per-repo slug).
    """
    return sandbox_dir / _PROMPTS_SUBDIR


def plan_folder_hash(file_texts: dict[str, str]) -> str:
    """Return the sha256 hex content hash of a plan folder.

    Purpose:
        The content component of the reviewed-plan identity: a byte-stable digest over the
        folder's files (relative path + content, sorted by relative path), **skipping**
        files whose basename is in :data:`DIAGNOSTIC_FILES` — workflow-written diagnostics
        must not change identity, while any user edit of any other plan file yields a new
        hash (and therefore a new identity and a new listing row).

    Args:
        file_texts: Mapping of folder-relative path -> file text (as read by the scan
            layer). Insertion order is irrelevant (the pairs are sorted).

    Returns:
        The 64-char sha256 hex digest (empty dict -> sha256 of the empty string).
    """
    digest = hashlib.sha256()
    for relpath, content in sorted(file_texts.items()):
        if Path(relpath).name in DIAGNOSTIC_FILES:
            continue
        # NUL separators keep (path, content) pairs unambiguous; .encode("utf-8") is
        # byte-stable by spec (UP012 is style-only, as in oc_todo.todo_id).
        digest.update(relpath.encode("utf-8"))  # noqa: UP012
        digest.update(b"\0")
        digest.update(content.encode("utf-8"))  # noqa: UP012
        digest.update(b"\0")
    return digest.hexdigest()


def plan_identity(repo: str, branch: str, plan_path: str, content_hash: str) -> str:
    """Return the stable 12-char identity for a reviewed plan.

    Purpose:
        A plan is identified by where it lives (repo + branch + the path to its
        ``work_plan.md``) and what it says (the folder content hash excluding diagnostics).
        Collapsing to a short sha1 prefix keeps state keys compact while staying
        deterministic across runs — mirroring :func:`agentic_scripts.workflows.oc_todo.todo_id`.

    Args:
        repo: The ``owner/name`` repo id.
        branch: The branch (short name) the plan folder is on.
        plan_path: The path to ``work_plan.md`` (e.g. ``"planning/orbit-sim/work_plan.md"``).
        content_hash: The :func:`plan_folder_hash` of the plan folder.

    Returns:
        The first 12 hex chars of ``sha1("repo|branch|plan_path|content_hash")``.
    """
    digest = hashlib.sha1(
        f"{repo}|{branch}|{plan_path}|{content_hash}".encode("utf-8")  # noqa: UP012
    ).hexdigest()
    return digest[:12]


def branch_name(identity: str, attempt: int) -> str:
    """Return the dedicated attempt-branch name for a plan identity.

    Purpose:
        Enforce the fresh-branch invariant: every pushed branch starts with
        ``roadmap-dev/`` and carries the attempt number, so the workflow never pushes to a
        protected or pre-existing branch and re-runs never collide with a live attempt.

    Args:
        identity: The 12-char plan identity (see :func:`plan_identity`).
        attempt: The 1-based attempt number for this execution.

    Returns:
        ``"roadmap-dev/<identity>-<attempt>"``.
    """
    return f"roadmap-dev/{identity}-{attempt}"


def extract_title(work_plan_text: str) -> str:
    """Return the plan title from a ``work_plan.md`` text.

    Purpose:
        The listing's ``title`` cell is workflow-owned and comes from the plan itself: the
        first ATX h1 line (``^#\\s+``), stripped of its leading ``#`` and whitespace. A
        plan without an h1 falls back to a fixed sentinel so the listing always has a title.

    Args:
        work_plan_text: The full text of ``work_plan.md`` (or a str to parse defensively).

    Returns:
        The h1 text (single line), or ``"Untitled plan"`` when no ``^#\\s+`` line exists.
    """
    for line in work_plan_text.splitlines():
        match = re.match(r"^#\s+", line)
        if match:
            return line[match.end() :].strip()
    return "Untitled plan"


@dataclass(frozen=True)
class Plan:
    """One reviewed plan discovered by the scan (a folder under ``planning/``).

    Attributes:
        repo: The ``owner/name`` repo id the plan was found in.
        branch: The branch (short name) the plan folder is on.
        path: The path to ``work_plan.md`` (e.g. ``"planning/orbit-sim/work_plan.md"``).
        title: The plan title (from :func:`extract_title`).
        content_hash: The :func:`plan_folder_hash` of the plan folder.

    Note:
        :attr:`identity` and :attr:`topic` are derived properties — the identity is always
        recomputed from the fields, never stored separately; the attempt number (and hence
        the attempt branch name) is not known here and is computed by the pipeline via
        :func:`branch_name`.
    """

    repo: str
    branch: str
    path: str
    title: str
    content_hash: str

    @property
    def identity(self) -> str:
        """Return the stable 12-char identity for this plan (see :func:`plan_identity`)."""
        return plan_identity(self.repo, self.branch, self.path, self.content_hash)

    @property
    def topic(self) -> str:
        """Return the plan folder (the parent directory of :attr:`path`)."""
        return str(Path(self.path).parent)


@dataclass(frozen=True)
class PlanEntry:
    """One scanned plan folder as handed to the pure core by the scan layer (Task 3).

    Attributes:
        dir: The plan folder path (e.g. ``"planning/orbit-sim"``).
        work_plan_text: The text of ``<dir>/work_plan.md``, or None when the folder is
            malformed (no ``work_plan.md`` — :func:`discover_plans` skips such entries).
        file_texts: Folder-relative path -> file text for the folder's files (the input to
            :func:`plan_folder_hash`).
    """

    dir: str
    work_plan_text: str | None
    file_texts: dict[str, str]


def discover_plans(repo: str, branch: str, entries: list[PlanEntry]) -> list[Plan]:
    """Filter scanned plan folders into valid :class:`Plan` objects (pure).

    Purpose:
        The scan layer (Task 3) walks a branch's tree and hands back one
        :class:`PlanEntry` per candidate folder; this is the deterministic rule set that
        decides which folders count as reviewed plans and stamps each with its identity
        inputs (content hash + title). Malformed entries (``work_plan_text is None``) are
        skipped, never raised — an odd folder must not kill the scan.

    Args:
        repo: The ``owner/name`` repo id (stored on each :class:`Plan`).
        branch: The branch (short name) the entries were scanned from (stored on each plan).
        entries: The scanned candidate folders (the scan layer guarantees no duplicate dirs).

    Returns:
        The valid plans sorted by folder dir (deterministic). A folder is valid when
        ``work_plan_text`` is not None, its dir's top-level segment is ``"planning"``, and
        no path segment is :data:`ARCHIVED_SEGMENT` (archived folders are never re-found).
    """
    plans: list[Plan] = []
    for entry in entries:
        if entry.work_plan_text is None:
            continue  # malformed folder (no work_plan.md) — skip, do not raise
        segments = entry.dir.split("/")
        if not segments or segments[0] != "planning" or ARCHIVED_SEGMENT in segments:
            continue  # not under planning/, or archived
        plans.append(
            Plan(
                repo=repo,
                branch=branch,
                path=f"{entry.dir}/work_plan.md",
                title=extract_title(entry.work_plan_text),
                content_hash=plan_folder_hash(entry.file_texts),
            )
        )
    plans.sort(key=lambda p: p.path)
    return plans


# --- State schema (v1) ------------------------------------------------------- #


def _utc_iso(now: datetime) -> str:
    """Return ``now`` as a UTC ISO-8601 string (naive inputs are treated as UTC).

    Purpose:
        The single place state entries are stamped from an injected clock — the pure core
        never calls ``datetime.now()`` itself.

    Args:
        now: The injected time (aware or naive; naive is assumed UTC).

    Returns:
        The UTC ISO-8601 string (e.g. ``"2026-11-21T12:00:00+00:00"``).
    """
    if now.tzinfo is None:
        return now.replace(tzinfo=UTC).isoformat()
    return now.astimezone(UTC).isoformat()


def fresh_state() -> dict:
    """Return a fresh v1 state document for a first run.

    Returns:
        ``{"version": 1, "plans": {}}`` — no plans recorded yet.
    """
    return {"version": _STATE_VERSION, "plans": {}}


def validate_state(st: dict) -> str | None:
    """Validate a loaded state document against the v1 schema.

    Purpose:
        There is no older state to migrate, so a mismatched shape is an operator error
        that must surface as a clear, actionable message telling the operator to delete the
        state file and let the workflow re-bootstrap (the oc-todo / mail-keeper pattern).

    Args:
        st: The parsed state document (possibly empty on a first run).

    Returns:
        None when ``st == {}`` (first run) or it matches v1; otherwise an error string
        that contains both ``"state schema mismatch"`` and ``"delete state/roadmap-dev.json"``.
    """
    if st == {}:
        return None  # no state yet → first run (the caller initialises it)
    if st.get("version") != _STATE_VERSION or not isinstance(st.get("plans"), dict):
        return (
            "state schema mismatch: expected version 1 with a 'plans' mapping — delete "
            "state/roadmap-dev.json and let the workflow re-bootstrap."
        )
    return None


def make_plan_entry(plan: Plan, state: str, *, now: datetime, **fields) -> dict:
    """Build one state entry for a plan at ``state``.

    Purpose:
        Stamp an entry with the plan's identity fields, the requested state, and a fresh
        UTC ISO-8601 ``updated_at`` (plus ``attempt`` defaulting to 0), so callers never
        forget the bookkeeping fields. Extra ``fields`` override or extend the base (e.g.
        ``last_error``, ``last_run_id``, ``branch_name``).

    Args:
        plan: The :class:`Plan` this entry describes (identity fields + content hash).
        state: One of ``"open"``, ``"pending"``, ``"review"``, ``"success"``, ``"failure"``.
        now: The injected clock (UTC ISO-8601 ``updated_at``; never a bare
            ``datetime.now()`` in the pure core).
        **fields: Additional/overriding fields (e.g. ``last_error``, ``last_run_id``).

    Returns:
        A dict with all v1 entry fields, merged with any extra ``fields``.
    """
    entry = {
        "identity": plan.identity,
        "repo": plan.repo,
        "branch": plan.branch,
        "path": plan.path,
        "title": plan.title,
        "content_hash": plan.content_hash,
        "state": state,
        "attempt": 0,
        "started_at": None,
        "finished_at": None,
        "pid": None,
        "branch_name": None,
        "commit_sha": None,
        "last_error": None,
        "last_run_id": None,
        "updated_at": _utc_iso(now),
    }
    entry.update(fields)
    return entry


# --- Listing (plans.md) ------------------------------------------------------ #


def repo_from_url(repo_url: str) -> str | None:
    """Derive the ``owner/name`` repo id from a listing section URL.

    Purpose:
        Listing rows carry the section's repo URL (not a repo id); the reconciler derives
        the id to match rows against scanned plans and state entries. Both forms the
        operator may have written are accepted: ``https://github.com/<owner>/<name>.git``
        and ``git@github.com:<owner>/<name>.git`` (each with or without the trailing
        ``.git``). The renderer only ever emits the https form, so any other shape (e.g. a
        local-path hand-edit) is treated as a ghost row (documented assumption).

    Args:
        repo_url: The section URL string (a row's ``repo_url`` cell value).

    Returns:
        The ``owner/name`` repo id, or None when the URL is not in an accepted form.
    """
    url = repo_url.strip()
    if url.startswith("https://"):
        url = url[len("https://") :]
        # Drop the host (first path segment): github.com/<owner>/<name> → <owner>/<name>.
        if "/" not in url:
            return None
        url = url.split("/", 1)[1]
    elif url.startswith("git@github.com:"):
        url = url[len("git@github.com:") :]
    else:
        return None
    if url.endswith(".git"):
        url = url[: -len(".git")]
    parts = url.split("/")
    if len(parts) != 2 or not all(parts):
        return None
    return url


@dataclass(frozen=True)
class ListingRow:
    """One parsed row of the ``plans.md`` listing.

    Attributes:
        repo_url: The section header URL (e.g. ``"https://github.com/y2d2/ARP_MPE.git"``).
        branch: The ``##`` branch the row sits under.
        approval: The user's approval checkbox (☑ = True).
        priority: The row's priority (int, ascending; 1 = first; ties by row order).
        plan: The path to ``work_plan.md``.
        title: The plan title (workflow-owned; refreshed from the scan on each reconcile).
        state: The state cell (workflow-owned; the one sanctioned user edit is re-arming
            ``failure`` rows to ``open``).
        remove: The user's remove checkbox (☑ = True; valid on ``success`` rows — the row
            is deleted next scan and re-appears while the plan is still in the scan).
    """

    repo_url: str
    branch: str
    approval: bool
    priority: int
    plan: str
    title: str
    state: str
    remove: bool


def _checkmark(cell: str) -> bool:
    """Map a checkbox cell to a bool (only the ☑ glyph is True; ☐/empty/other → False)."""
    return cell == "☑"


def parse_listing(md: str) -> list[ListingRow]:
    """Parse a ``plans.md`` listing into :class:`ListingRow` objects (defensive).

    Purpose:
        Turn the live listing (per-repo ``#`` sections, per-branch ``##`` tables, six
        columns) back into rows for the reconciler. The parser is deliberately defensive —
        it NEVER raises on malformed input: header and separator rows are skipped, table
        rows with exactly six cells are parsed, and everything else (free text between
        sections, unknown ``###`` headings, wrong column counts, non-int priorities,
        non-glyph checkboxes) is skipped silently. A row outside any repo/branch section is
        skipped, as is a ``##`` line that appears before any ``#`` section.

    Args:
        md: The full listing text (may be empty or None).

    Returns:
        The parsed rows in file order; empty when no valid row was found.
    """
    rows: list[ListingRow] = []
    repo_url: str | None = None
    branch: str | None = None
    for line in (md or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            # A repo section header (rest of the line = repo_url, stripped); resets the
            # branch context (a ## line only makes sense inside a repo section).
            repo_url = stripped[2:].strip()
            branch = None
            continue
        if stripped.startswith("## "):
            if repo_url is not None:
                branch = stripped[3:].strip()
            continue  # ## outside a repo section (or ### free text) → skipped
        if repo_url is None or branch is None:
            continue  # rows outside any repo/branch section are skipped
        if not (stripped.startswith("|") and stripped.endswith("|") and len(stripped) >= 2):
            continue  # not a table row
        cells = [cell.strip() for cell in stripped[1:-1].split("|")]
        if len(cells) != len(LISTING_COLUMNS):
            continue  # wrong column count → skip silently
        if tuple(cells) == LISTING_COLUMNS:
            continue  # the header row
        if all(cell and set(cell) == {"-"} for cell in cells):
            continue  # the separator row
        try:
            priority = int(cells[1])
        except ValueError:
            continue  # non-int priority → skip the whole row silently
        rows.append(
            ListingRow(
                repo_url=repo_url,
                branch=branch,
                approval=_checkmark(cells[0]),
                priority=priority,
                plan=cells[2],
                title=cells[3],
                state=cells[4],
                remove=_checkmark(cells[5]),
            )
        )
    return rows


def render_listing(rows: list[ListingRow]) -> str:
    """Render rows into the byte-stable ``plans.md`` listing text.

    Purpose:
        The inverse of :func:`parse_listing`: rows are grouped by repo (``# <repo_url>``
        emitted ONCE per repo) and, within a repo, by branch (``## <branch>`` per table),
        preserving the first-appearance order of the input rows; rows within a table keep
        their given order, and each table emits the exact header + separator + one line
        per row. Byte-stable (deterministic for a given input) — the reconciler relies on
        this to keep the listing diff-free across no-op passes.

    Args:
        rows: The rows to render (in the desired per-section order).

    Returns:
        The listing text with no trailing spaces and a single trailing newline; ``""``
        (a truly empty file) when ``rows`` is empty.
    """
    if not rows:
        return ""
    repos: list[str] = []
    branches_by_repo: dict[str, list[str]] = {}
    rows_by_section: dict[tuple[str, str], list[ListingRow]] = {}
    for row in rows:
        if row.repo_url not in branches_by_repo:
            branches_by_repo[row.repo_url] = []
            repos.append(row.repo_url)
        if row.branch not in branches_by_repo[row.repo_url]:
            branches_by_repo[row.repo_url].append(row.branch)
        rows_by_section.setdefault((row.repo_url, row.branch), []).append(row)
    lines: list[str] = []
    for repo_url in repos:
        lines.append(f"# {repo_url}")
        for branch in branches_by_repo[repo_url]:
            lines.append(f"## {branch}")
            lines.append(_LISTING_HEADER)
            lines.append(_LISTING_SEPARATOR)
            for row in rows_by_section[(repo_url, branch)]:
                lines.append(
                    f"| {'☑' if row.approval else '☐'} | {row.priority} | {row.plan} | "
                    f"{row.title} | {row.state} | {'☑' if row.remove else '☐'} |"
                )
    return "\n".join(lines) + "\n"


# --- Reconciler (pure) ------------------------------------------------------- #


def reconcile(
    plans: list[Plan],
    existing_rows: list[ListingRow],
    state_doc: dict,
    *,
    now: datetime,
    force_unapproved: frozenset[str] = frozenset(),
) -> tuple[list[ListingRow], dict, list[str]]:
    """Reconcile the scan + state against the listing (the heart of idempotency, pure).

    Purpose:
        Map (scanned plans, current listing rows, state document) to the next listing rows
        + state document + an action log. Per plan (identity-scoped), in order:

        1. **Scanned + in state** → the row exists (or is created) with the workflow-owned
           cells updated (``title`` from the scan, ``state`` from the state doc) EXCEPT the
           sanctioned re-arm: state doc ``failure`` + existing row state ``open`` → the
           user's ``open`` wins (state doc synced to ``open``, logged ``re-armed
           <id> (user set open)``). Any other divergence → the workflow state wins.
           User-owned cells (``approval``, ``priority``, ``remove``) are always preserved
           from the existing row.
        2. **Scanned + not in state** → new row (no checkmarks, ``state="open"``, priority
           = max in its (repo_url, branch) table + 1, or 1 for an empty table) + new state
           entry; logged ``discovered <id> (<repo> @ <branch>)``.
        3. **In state + not scanned** (vanished: archived/merged/deleted, repo removed from
           the allowlist, or the plan edited into a new identity — the OLD identity then
           vanishes) → its row is dropped, the state entry is KEPT (forensics); logged
           ``dropped row <id> (plan no longer in scan)``.
        4. **Ghost rows** (in neither scan nor state) → dropped; logged ``dropped ghost
           row <plan> (no state entry)``.
        5. **``remove`` ☑ on a ``success`` row** (scanned or not) → the row is dropped
           (state kept); if the plan is still scanned it is re-added in the same pass as a
           ``success`` row (fresh ``remove=False``, ``approval`` as before, priority
           max+1 — the documented harmless re-appearance); logged ``removed <id> (user
           remove tick)``.
        6. State entries are never deleted by the reconciler.

        ``force_unapproved`` (identities the pipeline wants de-approved, e.g. after a
        ``questions`` outcome) sets ``approval=False`` on those rows in this pass — the ONE
        sanctioned user-cell overwrite, logged ``unapproved <id> (questions raised)``.

    Rationale:
        Row identity is matched on ``(repo, branch, path)`` (rows carry no content hash),
        with the state entry at that key providing the 12-hex identity for state updates
        and logs; a key that is still scanned belongs to the CURRENT identity, so a stale
        twin entry never drops the live row. The input ``state_doc`` is never mutated
        (copy-on-write); a steady-state pass (unchanged scan + state) returns rows that
        render byte-identically to the input and a value-equal state document.

    Args:
        plans: The scanned plans (any order; sorted internally for determinism).
        existing_rows: The current listing rows (any order; first-appearance order drives
            section order in the output).
        state_doc: The loaded state document (``{"version": 1, "plans": {id: entry}}``).
        now: The injected clock (UTC ISO-8601 stamps on new/re-armed entries).
        force_unapproved: Identities to de-approve in this pass (see above).

    Returns:
        A ``(new_rows, new_state_doc, actions_log)`` tuple — the next listing rows
        (existing sections first, then scan-only sections; existing row order within a
        section, new rows appended), the copy-on-write state document, and the action-log
        lines (in pass order: scanned plans, then vanished entries, then ghost rows).
    """
    actions: list[str] = []

    plans_sorted = sorted(plans, key=lambda p: (p.repo, p.branch, p.path))
    scanned_idents = {plan.identity for plan in plans_sorted}

    # Section bookkeeping: first-appearance order + running row list per (repo_url, branch)
    # (the max-priority source for new rows; new rows are appended as they are created).
    section_order: list[tuple[str, str]] = []
    section_rows: dict[tuple[str, str], list[ListingRow]] = {}
    for row in existing_rows:
        sec = (row.repo_url, row.branch)
        if sec not in section_rows:
            section_rows[sec] = []
            section_order.append(sec)
        section_rows[sec].append(row)

    def _next_priority(sec: tuple[str, str]) -> int:
        """Max priority in the section so far + 1 (1 for an empty/absent table)."""
        return max((r.priority for r in section_rows.get(sec, [])), default=0) + 1

    # Index rows by (repo, branch, path); unparseable repo_url rows stay ghosts (rule 4).
    row_by_key: dict[tuple[str, str, str], ListingRow] = {}
    for row in existing_rows:
        repo = repo_from_url(row.repo_url)
        if repo is not None:
            row_by_key[(repo, row.branch, row.plan)] = row

    # Copy-on-write the state document (the input is never mutated).
    new_doc = dict(state_doc)
    new_entries = dict(state_doc.get("plans") or {})

    # --- Pass 1: scanned plans (rules 1, 2, 5-readd, force_unapproved). --- #
    updated_by_key: dict[tuple[str, str, str], ListingRow] = {}
    new_rows: list[tuple[tuple[str, str], ListingRow]] = []  # (section, row), creation order

    for plan in plans_sorted:
        ident = plan.identity
        key = (plan.repo, plan.branch, plan.path)
        existing = row_by_key.pop(key, None)  # a scanned plan owns its row position
        entry = new_entries.get(ident)

        if entry is None:
            # Rule 2: scanned + not in state → new row (never pre-approved) + new entry.
            sec = (f"https://github.com/{plan.repo}.git", plan.branch)
            row = ListingRow(
                repo_url=sec[0],
                branch=sec[1],
                approval=False,
                priority=_next_priority(sec),
                plan=plan.path,
                title=plan.title,
                state="open",
                remove=False,
            )
            if ident in force_unapproved:
                actions.append(f"unapproved {ident} (questions raised)")
            section_rows.setdefault(sec, []).append(row)
            new_rows.append((sec, row))
            new_entries[ident] = make_plan_entry(plan, "open", now=now)
            actions.append(f"discovered {ident} ({plan.repo} @ {plan.branch})")
            continue

        # Rule 1: scanned + in state → workflow-owned cells from scan/state; user cells
        # preserved from the existing row (defaults when the row is absent).
        doc_state = entry.get("state")
        re_armed = False
        if doc_state == "failure" and existing is not None and existing.state == "open":
            doc_state = "open"  # the sanctioned re-arm: the user's open wins
            re_armed = True

        if existing is not None:
            sec = (existing.repo_url, existing.branch)
            approval = existing.approval
            priority = existing.priority
            remove_tick = existing.remove
        else:
            sec = (f"https://github.com/{plan.repo}.git", plan.branch)
            approval = False
            priority = _next_priority(sec)
            remove_tick = False

        if re_armed:
            new_entries[ident] = {**entry, "state": "open", "updated_at": _utc_iso(now)}
            actions.append(f"re-armed {ident} (user set open)")

        if ident in force_unapproved:
            approval = False
            actions.append(f"unapproved {ident} (questions raised)")

        if remove_tick and doc_state == "success":
            # Rule 5 (scanned): drop + re-add in the same pass (harmless re-appearance).
            actions.append(f"removed {ident} (user remove tick)")
            section_rows[sec].remove(existing)
            row = ListingRow(
                repo_url=sec[0],
                branch=sec[1],
                approval=approval,
                priority=_next_priority(sec),
                plan=plan.path,
                title=plan.title,
                state="success",
                remove=False,
            )
            section_rows[sec].append(row)
            new_rows.append((sec, row))
            continue

        updated_by_key[key] = ListingRow(
            repo_url=sec[0],
            branch=sec[1],
            approval=approval,
            priority=priority,
            plan=plan.path,
            title=plan.title,
            state=doc_state,
            remove=remove_tick,
        )

    # --- Pass 2: in state + not scanned (rule 3) → row dropped, entry kept. --- #
    for ident in sorted(new_entries):
        if ident in scanned_idents:
            continue
        entry = new_entries[ident]
        key = (entry.get("repo"), entry.get("branch"), entry.get("path"))
        row = row_by_key.get(key)
        if row is None:
            continue  # no row left at this key (it belongs to a scanned plan, or none)
        del row_by_key[key]
        if row.state == "success" and row.remove:
            actions.append(f"removed {ident} (user remove tick)")
        else:
            actions.append(f"dropped row {ident} (plan no longer in scan)")

    # --- Pass 3: ghost rows (rule 4) → dropped. --- #
    for row in row_by_key.values():
        actions.append(f"dropped ghost row {row.plan} (no state entry)")

    # --- Assemble the output rows (existing sections first, then scan-only). --- #
    new_rows_by_sec: dict[tuple[str, str], list[ListingRow]] = {}
    for sec, row in new_rows:
        new_rows_by_sec.setdefault(sec, []).append(row)

    out_rows: list[ListingRow] = []
    emitted: set[tuple[str, str]] = set()
    for sec in section_order:
        sec_rows = [
            updated_by_key[(repo_from_url(r.repo_url), r.branch, r.plan)]
            for r in existing_rows
            if (r.repo_url, r.branch) == sec
            and (repo_from_url(r.repo_url), r.branch, r.plan) in updated_by_key
        ]
        sec_rows += new_rows_by_sec.get(sec, [])
        if sec_rows:
            emitted.add(sec)
            out_rows.extend(sec_rows)
    for sec, sec_rows in new_rows_by_sec.items():
        if sec not in emitted:
            out_rows.extend(sec_rows)

    new_doc["plans"] = new_entries  # copy-on-write: point the output doc at the new mapping
    return out_rows, new_doc, actions


def reap_orphans(state_doc: dict, *, now: datetime) -> tuple[dict, list[str]]:
    """Reap orphaned ``pending`` entries (infra death = auto-retry, pure).

    Purpose:
        A job that was ``pending`` at process death (crash/restart/OOM) can never finish —
        the in-process drain is gone. Every such entry is flipped back to ``open`` so the
        next drain re-starts it (the attempt counter was already incremented at start, so
        the fresh attempt branch name is free), with a forensics ``last_error`` and the
        bookkeeping fields cleared (``pid`` / ``started_at``). Worktree cleanup is the
        pipeline's job (Task 3); this helper only fixes the state document.

    Args:
        state_doc: The loaded state document.
        now: The injected clock (UTC ISO-8601 ``updated_at`` stamps).

    Returns:
        A ``(new_state_doc, actions_log)`` tuple — a copy-on-write document (the input is
        never mutated) plus one log line per reaped identity.
    """
    actions: list[str] = []
    new_doc = dict(state_doc)
    entries = dict(state_doc.get("plans") or {})
    for ident in sorted(entries):
        entry = entries[ident]
        if entry.get("state") != "pending":
            continue
        entries[ident] = {
            **entry,
            "state": "open",
            "last_error": "orphaned pending (crash/restart) — reaped",
            "pid": None,
            "started_at": None,
            "updated_at": _utc_iso(now),
        }
        actions.append(f"reaped orphan {ident} (pending -> open)")
    new_doc["plans"] = entries
    return new_doc, actions


def apply_job_outcome(entry: dict, outcome: str, *, now: datetime, **fields) -> dict:
    """Map one pipeline job outcome onto a state entry (pure; used by Task 4).

    Purpose:
        The state-machine step at job end: ``"success"`` → state ``success`` with the
        delivery fields (``branch_name`` — the pushed attempt branch is the delivery, NO
        PR is created — plus ``commit_sha``); ``"questions"`` → state ``review`` (major
        questions sit in ``questions.md`` until the user re-☑'s); ``"failure"`` → state
        ``failure`` with ``last_error``. ``finished_at`` is stamped from the injected clock
        in every case; ``attempt`` is unchanged (it was incremented at job start by the
        pipeline).

    Args:
        entry: The plan's current state entry (not mutated).
        outcome: One of ``"success"``, ``"questions"``, ``"failure"``.
        now: The injected clock (UTC ISO-8601 ``finished_at`` / ``updated_at``).
        **fields: Outcome-specific fields (e.g. ``branch_name``, ``commit_sha``,
            ``last_error``, ``last_run_id``) merged into the new entry.

    Returns:
        A new entry dict with the outcome's state, ``finished_at`` / ``updated_at``
        stamped, and the extra ``fields`` merged in (``attempt`` untouched).

    Raises:
        ValueError: If ``outcome`` is not one of the three documented outcomes.
    """
    if outcome not in _OUTCOME_STATES:
        allowed = ", ".join(f'"{name}"' for name in _OUTCOME_STATES)
        raise ValueError(f"unknown job outcome: {outcome!r} (expected one of {allowed})")
    new = dict(entry)
    new.update(fields)
    new["state"] = _OUTCOME_STATES[outcome]
    new["finished_at"] = _utc_iso(now)
    new["updated_at"] = _utc_iso(now)
    return new


# --- Report parsing + renderers (pure, byte-stable) -------------------------- #


def extract_report_sections(final_text: str | None) -> dict:
    """Best-effort parse of the agent's result report into named sections.

    Purpose:
        The pipeline gates a job's success on the report's ``blockers`` section and quotes
        the summary in the run log. This extracts each section as the text between its
        ``## <Heading>`` line and the next ``## `` heading (stripped). It is best-effort: a
        missing section yields ``""``, and None/empty input yields all-empty sections with
        ``has_report=False``.

    Note:
        Deliberate duplicate of the behaviour of
        :func:`agentic_scripts.workflows.oc_todo.extract_report_sections` — there are no
        cross-workflow imports (each workflow module is self-contained), so the small
        helper is copied rather than shared.

    Args:
        final_text: The agent's final message (its result report), or None.

    Returns:
        A dict ``{"summary": str, "files": str, "tests": str, "blockers": str,
        "has_report": bool}``. ``blockers`` is left raw — the caller lowercases and
        compares it against ``"none"`` to decide whether any blocker was reported.
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


def job_status_from_report(final_text: str | None) -> str | None:
    """Return the mandated status line of the agent's result report, or None.

    Purpose:
        The autonomy brief mandates an explicit status line (exactly one of
        ``Status: success | questions | failure``); this scans the report for the first
        line matching ``^\\s*status\\s*:\\s*(success|questions|failure)\\s*$``
        (case-insensitive) and returns the lowercase status. The pipeline uses it as the
        primary outcome signal (the report sections are secondary context).

    Args:
        final_text: The agent's final message (its result report), or None.

    Returns:
        ``"success"``, ``"questions"``, or ``"failure"`` for the first matching line, else
        None (no status line, or none that names an allowed outcome).
    """
    if not final_text:
        return None
    for line in final_text.splitlines():
        match = _STATUS_LINE_RE.match(line)
        if match:
            return match.group(1).lower()
    return None


def render_brief(
    *,
    run_id: str,
    plan: Plan,
    repo_url: str,
    attempt: int,
    timeout_minutes: int,
    test_cmd: str | None,
) -> str:
    """Render the autonomy brief in the exact stable format the planner reads by eye.

    Purpose:
        Produce the single self-contained dispatch message for ONE approved plan: the run
        header, the plan identity, the hard budget, the no-user / no-questions mandate,
        the review → execute → report sequence (with the major/minor question split and
        the mandated ``Status: …`` line), and the git-ownership rule (the runner commits,
        archives the plan folder, and pushes the attempt branch — a human opens the PR).
        The format is load-bearing (the 27B planner reads it by eye), so it must stay
        byte-stable (one block, no extra blank lines).

    Args:
        run_id: The unique run identifier for this invocation.
        plan: The :class:`Plan` to execute (path/branch/title/topic).
        repo_url: The repo's https URL (the listing's section-header form).
        attempt: The 1-based attempt number for this execution.
        timeout_minutes: The per-job hard budget in minutes (the process is killed at it).
        test_cmd: The configured per-repo test command, or None when none is set.

    Returns:
        The brief string, exactly in the documented format.
    """
    test_line = test_cmd if test_cmd else "none configured — the runner runs tests itself"
    return "\n".join(
        [
            f"roadmap-dev autonomous run {run_id} — execute ONE approved plan, pre-approved, "
            "no user present.",
            "",
            f"Plan: {plan.path}",
            f"Repo: {repo_url}   Branch: {plan.branch}   Title: {plan.title}",
            f"Attempt: {attempt}   Hard budget: {timeout_minutes} minutes (process will be "
            "killed at the deadline).",
            "",
            "You are running headless. There is NO user: the question tool is unavailable, "
            "nothing is",
            "pending your approval — this run is fully pre-approved. Do NOT ask questions, "
            "do NOT wait.",
            "",
            f"1. REVIEW THE PLAN. Read {plan.path} and every task file in its folder.",
            "   - MAJOR question = anything that would change scope, requirements, or dependencies",
            "     (NOT an implementation detail). If — and only if — a major open question exists:",
            f"     write it to {plan.topic}/questions.md (numbered questions, each with "
            "context and",
            "     exactly what you need answered), change nothing else, and finish with the result",
            '     report whose status line is "Status: questions". Do NOT execute any task.',
            "   - MINOR things: decide yourself; record each decision in your result report only.",
            f"   - If {plan.topic}/questions.md already contains user answers, read them and "
            "proceed",
            "     (they answer a previous round of this same plan).",
            "2. EXECUTE IN SEQUENCE. Dispatch @lightweight-dev ONE small self-contained task "
            "at a time",
            "   — strictly sequential, NEVER in parallel — and verify each task's acceptance "
            "criteria",
            "   from its result report before dispatching the next.",
            "3. REPORT. Your final message must be the result report:",
            "   ## Summary / ## Files / ## Tests / ## Blockers",
            "   plus an explicit status line, exactly one of:",
            "     Status: success      (every task done, every acceptance criterion verified)",
            "     Status: questions    (major questions written to questions.md, no task executed)",
            "     Status: failure      (cannot proceed; explain why in Blockers)",
            f"   Test command: {test_line}",
            "",
            "Git rules: do NOT run git commit or git push — the runner owns git and will commit,",
            "archive the plan folder and push the branch after you exit (a human opens the PR).",
            "Work ONLY inside this worktree.",
        ]
    )


def render_commit_title(plan: Plan) -> str:
    """Render the implementation commit message for a plan.

    Purpose:
        Produce ``"OC: " + <plan title>`` truncated to 72 characters TOTAL (no ellipsis —
        cut at char 72), mirroring :func:`agentic_scripts.workflows.oc_todo.render_pr_title`'s
        truncation discipline. The ``OC:`` prefix matches the repo's commit convention; the
        commit lands on the attempt branch (a human opens the PR).

    Args:
        plan: The :class:`Plan` whose implementation is being committed.

    Returns:
        The commit message string, at most 72 characters in total.
    """
    return f"OC: {plan.title}"[:72]


def archive_commit_message(identity: str, run_id: str) -> str:
    """Render the commit message for archiving an executed plan folder.

    Purpose:
        The archive commit moves the whole plan folder to ``planning/archived/<topic>/``
        on the attempt branch (part of the success delivery, before the push).

    Args:
        identity: The 12-char plan identity (see :func:`plan_identity`).
        run_id: The unique run identifier that executed the plan.

    Returns:
        ``"OC: roadmap-dev: archive plan <identity> (run <run_id>)"``.
    """
    return f"OC: roadmap-dev: archive plan {identity} (run {run_id})"


def diag_commit_message(identity: str, kind: str, run_id: str) -> str:
    """Render the commit message for a diagnostics commit on the plan's branch.

    Purpose:
        ``questions.md`` (a ``questions`` outcome) and ``failure.md`` (a ``failure``
        outcome) are committed as small ``OC:`` commits directly on the plan's branch via
        a diagnostics worktree — this is their operator surface (the re-arm reads
        ``questions.md``; the failure explanation lives in ``failure.md``).

    Args:
        identity: The 12-char plan identity (see :func:`plan_identity`).
        kind: The diagnostic kind — ``"questions"`` or ``"failure"``.
        run_id: The unique run identifier that produced the diagnostic.

    Returns:
        ``"OC: roadmap-dev: <identity> — <kind> (run <run_id>)"``.

    Raises:
        ValueError: If ``kind`` is not one of ``"questions"`` or ``"failure"``.
    """
    if kind not in _DIAG_KINDS:
        raise ValueError(f"kind must be one of {_DIAG_KINDS}, got {kind!r}")
    return f"OC: roadmap-dev: {identity} — {kind} (run {run_id})"


# --- Workflow shell ---------------------------------------------------------- #


def clone_env_for(pat: str | None) -> dict[str, str] | None:
    """Build the git-auth environment triple for a PAT, or None when there is no PAT.

    Purpose:
        Inject the token as an ``http.extraHeader`` via git's config env vars so the PAT
        never appears in argv (it would otherwise show up in ``ps`` output). Kept for
        phase 1: repos cloned over HTTPS need it, and it is harmless for the default SSH
        URLs and for local fixture paths.

    Args:
        pat: The personal access token, or None/empty when no auth is needed (SSH / local).

    Returns:
        ``None`` when ``pat`` is None or empty; otherwise a dict with
        ``GIT_CONFIG_COUNT=1``, ``GIT_CONFIG_KEY_0=http.extraHeader`` and
        ``GIT_CONFIG_VALUE_0="Authorization: Bearer <pat>"``.

    Note:
        Deliberate duplicate of :func:`agentic_scripts.workflows.oc_todo.clone_env_for` —
        there are no cross-workflow imports (each workflow module is self-contained), so
        the small helper is copied rather than shared.
    """
    if not pat:
        return None
    return {
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "http.extraHeader",
        "GIT_CONFIG_VALUE_0": f"Authorization: Bearer {pat}",
    }


def create(config: Config) -> "RoadmapDevWorkflow":  # noqa: UP037 - forward ref; class defined below
    """Create and return a :class:`RoadmapDevWorkflow` instance (the scheduler's entry point).

    Purpose:
        Production wiring for the scheduler's per-run construction: build the workflow
        from the validated ``roadmap_prompts`` settings, using the real :class:`Git`
        collaborator (the constructor default), leaving ``runner`` as None so it is
        resolved lazily from ``ctx.runner`` at call time, and defaulting the session probe
        and clock to the real :func:`agentic_scripts.sessions.read_active_sessions` /
        wall clock (resolved lazily, so the constructor stays side-effect free). There is
        NO ``github`` seam — this workflow never calls the GitHub API (no PR creation;
        user decision 2026-11-21).

    Args:
        config: The fully validated :class:`~agentic_scripts.config.Config`; its
            :attr:`Config.roadmap_prompts` settings (allowed repos, listing repo, timeout,
            test commands, clone-URL overrides) are used to build the workflow.

    Returns:
        A new :class:`RoadmapDevWorkflow`, ready to be run by the scheduler.

    Example:
        >>> wf = create(config)  # doctest: +SKIP
        >>> wf.name
        'roadmap-dev'
    """
    return RoadmapDevWorkflow(settings=config.roadmap_prompts)


class RoadmapDevWorkflow:
    """The roadmap-dev workflow: one idempotent run (phase 1 + drain stub).

    Purpose:
        Hold the injected collaborators and expose the stable :attr:`name` plus
        :meth:`run`. Phase 1 is implemented (:meth:`_scan_and_reconcile`): on every run,
        reap orphaned ``pending`` plans (state flip + worktree cleanup), scan all
        ``allowed_repos`` (sandbox clone/fetch, all branches except ``roadmap-dev/*``)
        for un-archived plans, reconcile the remote ``plans.md`` in the listing-repo
        clone, and commit + push the listing when it changed (one non-fast-forward
        retry). The idle-gated drain is still a stub: :meth:`_run` appends the load-bearing
        note ``"drain: not implemented (Task 4)"`` (gate open) or
        ``"drain skipped (idle gate closed)"`` (gate closed) — Task 4 replaces that with
        :meth:`_drain`.

    Rationale:
        Constructor injection (``git`` / ``runner`` / ``active_sessions`` / ``now_fn``) is
        the hermetic-test seam: tests pass fakes for each collaborator, while production
        wiring (via :func:`create`) passes the real :class:`Git` and lazily resolved
        runner/session probe/clock. The pipeline never raises for business failures —
        per-repo and per-step faults are logged and reported in the
        :class:`WorkflowResult` (``status="error"`` when any business error accumulated),
        and every repo is scanned even if an earlier one failed. There is deliberately NO
        ``github`` collaborator: this workflow never calls the GitHub API (no PR
        creation — user decision 2026-11-21).

    Attributes:
        name: The stable workflow name, matching its config key (``"roadmap-dev"``).
    """

    name = "roadmap-dev"

    def __init__(
        self,
        settings: RoadmapPrompts,
        *,
        git: Git | None = None,
        runner=None,
        active_sessions: Callable[[], int] | None = None,
        now_fn: Callable[[], datetime] | None = None,
    ) -> None:
        """Create the workflow with injected collaborators.

        Args:
            settings: The :class:`~agentic_scripts.config.RoadmapPrompts` settings
                (allowed repos, listing repo/path/branch, per-job timeout, test commands,
                clone-URL overrides).
            git: The :class:`Git` helper; defaults to a fresh :class:`Git()` when None.
            runner: The agent runner; may be None, in which case it is resolved from
                ``ctx.runner`` at call time (Task 4).
            active_sessions: A zero-arg callable returning the count of active interactive
                OpenCode sessions (the idle-gate input); defaults to
                :func:`agentic_scripts.sessions.read_active_sessions` when None (resolved
                lazily so the constructor stays side-effect free).
            now_fn: A zero-arg callable returning the current time (the injected clock);
                defaults to ``datetime.now(UTC)`` when None (resolved lazily).

        Note:
            A None ``runner`` / ``active_sessions`` / ``now_fn`` is not constructed or
            called here — it is resolved lazily at call time so the constructor (and the
            module import) stay side-effect free. There is deliberately NO ``github``
            collaborator: this workflow never calls the GitHub API.
        """
        self._settings = settings
        self._git = git if git is not None else Git()
        self._runner_override = runner
        self._active_sessions = active_sessions
        self._now_fn = now_fn

    # --- Lazy seams ---------------------------------------------------------- #

    def _active_session_count(self) -> int:
        """Return the active-session count (injected probe, else the real one).

        Returns:
            The count from the injected ``active_sessions`` callable, or from
            :func:`agentic_scripts.sessions.read_active_sessions` when none was injected.
        """
        if self._active_sessions is not None:
            return self._active_sessions()
        from agentic_scripts.sessions import read_active_sessions

        return read_active_sessions()

    def _now(self) -> datetime:
        """Return the current time (injected clock, else the wall clock in UTC).

        Returns:
            The time from the injected ``now_fn`` callable, else ``datetime.now(UTC)``.
        """
        if self._now_fn is not None:
            return self._now_fn()
        return datetime.now(UTC)

    # --- Pipeline helpers (phase 1) ------------------------------------------- #

    def _repo_url(self, repo: str) -> str:
        """Return the clone URL for ``repo`` (config override wins over the SSH default).

        Purpose:
            Resolve where an allowed repo is cloned from: an explicit ``repo_urls``
            override (a local path or mirror — the hermetic-test seam) when present, else
            the default SSH URL ``git@github.com:<repo>.git`` (this box authenticates via
            SSH; the PAT env support in :meth:`_clone_or_fetch` is for HTTPS mirrors).

        Args:
            repo: The ``owner/name`` repo id.

        Returns:
            The override string when configured, else ``"git@github.com/<repo>.git"``.
        """
        return self._settings.repo_urls.get(repo) or f"git@github.com/{repo}.git"

    def _prompts_repo_url(self) -> str:
        """Return the listing-repo clone URL (override wins over the SSH default).

        Returns:
            ``listing_repo_url`` when set, else ``"git@github.com:<listing_repo>.git"``.
        """
        return (
            self._settings.listing_repo_url or f"git@github.com/{self._settings.listing_repo}.git"
        )

    def _clone_or_fetch(
        self, ctx, url: str, path: Path, label: str, errors: list[str]
    ) -> Path | None:
        """Clone from ``url`` into ``path`` on first sight, else fetch it (shared helper).

        Purpose:
            Ensure a full local clone exists at ``path`` and is current with the remote:
            when the directory is absent (or not a git repo) it is cloned from ``url``;
            otherwise it is fetched (with ``--prune``). A PAT, if present in the
            environment at run time, is injected as git-auth env (never argv; harmless for
            SSH and local URLs) — kept so repos that need HTTPS auth still work.

        Args:
            ctx: The shared context (for logging).
            url: The clone URL (config override or the SSH default; a local path in tests).
            path: The clone destination (the caller composes it via the layout helpers).
            label: A human name for this clone (the repo id, or
                ``"listing repo <owner/name>"``), used in log and error lines.
            errors: The run's business-error list; a clone/fetch failure appends one
                error string here (so the caller can continue with the next repo).

        Returns:
            ``path`` on success, or None on a :class:`GitError` (logged with the stderr
            tail and recorded in ``errors``) — a clone failure never stops the other repos.

        Side Effects:
            ``mkdir -p`` of the clone's parent; one ``git clone`` or ``git fetch`` per
            call.
        """
        env = clone_env_for(os.environ.get("GITHUB_PAT", "").strip() or None)
        try:
            if not (path.exists() and self._git.is_repo(path)):
                path.parent.mkdir(parents=True, exist_ok=True)
                self._git.clone(url, path, env=env)
            else:
                self._git.fetch(path, env=env)  # prune by default
        except GitError as exc:
            ctx.logger.error("roadmap-dev: clone/fetch failed for %s: %s", label, exc)
            errors.append(f"clone/fetch failed for {label}: {exc}")
            return None
        return path

    def _scan_repo(self, ctx, repo: str, clone: Path) -> list[Plan]:
        """Scan every remote branch of ``clone`` for reviewed plan folders.

        Purpose:
            The local full-clone scan model (oc_todo's ref-grep, adapted): for each
            remote branch (short name — skipping ``HEAD`` / ``origin`` and the
            workflow's own ``roadmap-dev/*`` attempt branches), list the branch's tree
            with :meth:`Git.ls_tree`, keep the paths matching ``planning/**/work_plan.md``
            outside an ``archived`` segment, and — per candidate folder — read
            ``work_plan.md`` plus every file under the folder at that ref into a
            :class:`PlanEntry`; :func:`discover_plans` then applies the pure validity
            rules (malformed folders are skipped, never raised).

        Args:
            ctx: The shared context (for logging).
            repo: The ``owner/name`` repo id (stored on each :class:`Plan`).
            clone: The full-clone directory to scan.

        Returns:
            The discovered :class:`Plan` objects (deterministic — one
            :func:`discover_plans` pass per branch, each sorted by path); empty when no
            branch carries a plan.

        Side Effects:
            Read-only git calls (:meth:`Git.branches`, :meth:`Git.ls_tree`,
            :meth:`Git.show_file`). A :class:`GitError` mid-branch (e.g. a vanished ref)
            is logged and that branch skipped — the scan continues; an unreadable file
            inside a plan folder is treated as absent (logged), and an unreadable
            ``work_plan.md`` makes the folder malformed (skipped, logged WARNING).
        """
        plans: list[Plan] = []
        branch_list = [
            b
            for b in self._git.branches(clone)
            if b not in ("HEAD", "origin") and not b.startswith("roadmap-dev/")
        ]
        for branch in branch_list:
            ref = f"origin/{branch}"
            try:
                files = self._git.ls_tree(clone, ref)
            except GitError as exc:
                ctx.logger.warning(
                    "roadmap-dev: ls-tree failed on %s@%s — skipping branch: %s",
                    repo,
                    ref,
                    exc,
                )
                continue
            entries: list[PlanEntry] = []
            for path in files:
                if not path.endswith("/work_plan.md"):
                    continue
                folder = path[: -len("/work_plan.md")]
                segments = folder.split("/")
                if not segments or segments[0] != "planning" or ARCHIVED_SEGMENT in segments:
                    continue  # discover_plans re-checks; this just avoids wasted file reads
                try:
                    work_plan_text = self._git.show_file(clone, ref, path)
                except GitError as exc:
                    ctx.logger.warning(
                        "roadmap-dev: cannot read %s@%s — treating folder as malformed: %s",
                        path,
                        ref,
                        exc,
                    )
                    work_plan_text = None
                file_texts: dict[str, str] = {}
                prefix = folder + "/"
                for f in files:
                    if not f.startswith(prefix):
                        continue
                    try:
                        file_texts[f[len(prefix) :]] = self._git.show_file(clone, ref, f)
                    except GitError as exc:
                        ctx.logger.warning(
                            "roadmap-dev: cannot read %s@%s — treating file as absent: %s",
                            f,
                            ref,
                            exc,
                        )
                entries.append(
                    PlanEntry(dir=folder, work_plan_text=work_plan_text, file_texts=file_texts)
                )
            plans.extend(discover_plans(repo, branch, entries))
        return plans

    def _fetch_listing(self, ctx, prompts_clone: Path) -> str:
        """Return the current listing text on ``origin/<listing_branch>`` ("" when absent).

        Purpose:
            Read the live listing file at the remote tip without checking it out — the
            base for :func:`parse_listing`. A :class:`GitError` (file or branch absent,
            e.g. the first run before the listing branch exists) yields ``""`` (an empty
            listing) with an INFO log — the reconciler then creates all rows from the scan.

        Args:
            ctx: The shared context (for logging).
            prompts_clone: The listing-repo clone directory.

        Returns:
            The listing text (trailing newlines stripped by :meth:`Git.show_file`), or
            ``""`` when the file/branch is absent.
        """
        settings = self._settings
        try:
            return self._git.show_file(
                prompts_clone, f"origin/{settings.listing_branch}", settings.listing_path
            )
        except GitError as exc:
            ctx.logger.info(
                "roadmap-dev: no listing at %s on %s — treating as empty (first run): %s",
                settings.listing_path,
                settings.listing_branch,
                exc,
            )
            return ""

    def _reconcile_and_push(
        self, ctx, prompts_clone: Path, plans: list[Plan], st: dict, current_md: str
    ) -> tuple[dict, list[str], list[str]]:
        """Reconcile the fetched listing against the scan + state and push the result.

        Purpose:
            The listing-pushing half of phase 1: parse ``current_md`` into rows, run
            :func:`reconcile`, and — when the rendered listing differs from the fetched
            text — ensure ``listing_branch`` is checked out (:meth:`Git.checkout` with
            ``-B <branch> origin/<branch>`` when the clone is on another branch), write
            the file, stage it, commit (the idempotent primitive — ``False`` means
            no-op, skip push), and push (``--set-upstream`` only when
            ``origin/<branch>`` is absent, probed via :meth:`Git.rev_parse`). A push
            failure (e.g. a non-fast-forward from a concurrent user edit) triggers ONE
            retry: fetch, re-point the branch to the remote tip, re-read the remote
            listing, re-run :func:`reconcile` on the fresh rows (the user's cells are
            preserved; the previous attempt's local commit is re-created on the new
            base), re-write + commit + push. A second failure records ``listing push
            failed for <repo>: …`` in the errors (the state document is still returned
            for persistence — the next fire retries, and reconcile is idempotent so
            re-applying is safe).

        Args:
            ctx: The shared context (``run_id`` in the commit message, logger).
            prompts_clone: The listing-repo clone directory.
            plans: The scanned plans (this run).
            st: The current state document (the reaper's output; never mutated in place).
            current_md: The fetched listing text ("" when the file/branch is absent).

        Returns:
            A ``(new_state, actions, errors)`` tuple — the reconciled state document
            (from the last reconcile pass), the human-readable action notes (reconcile
            log lines + listing push notes), and the business errors (empty when the
            push succeeded or was not needed).

        Side Effects:
            At most two listing commits (first attempt + retry), at most two pushes, one
            fetch per retry; the listing file is rewritten before each commit.

        Raises:
            GitError: Never from this method — commit/push faults are caught (the retry
                then the recorded error); a :class:`GitError` from :meth:`Git.fetch` /
                :meth:`Git.checkout` on the retry path is caught the same way.
        """
        settings = self._settings
        branch = settings.listing_branch
        commit_msg = f"OC: roadmap-dev: reconcile listing (run {ctx.run_id})"
        actions: list[str] = []
        errors: list[str] = []

        rows = parse_listing(current_md)
        new_rows, new_state, logs = reconcile(plans, rows, st, now=self._now())
        actions.extend(logs)

        if render_listing(new_rows) == current_md:
            actions.append(f"listing unchanged ({len(new_rows)} row(s)) — no push")
            return new_state, actions, errors

        def commit_and_push(md: str) -> bool:
            """Write, stage, and commit the listing; push unless the commit was a no-op.

            Returns:
                True when a push was performed, False when :meth:`Git.commit` reported
                no changes (nothing to push — treated as a no-op success).

            Raises:
                GitError: On a commit or push failure (e.g. a non-fast-forward push).
            """
            target = prompts_clone / settings.listing_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(md, encoding="utf-8")
            self._git.add(prompts_clone, [settings.listing_path])
            if not self._git.commit(prompts_clone, commit_msg):
                return False  # no changes → no-op, skip push
            try:
                self._git.rev_parse(prompts_clone, f"origin/{branch}")
                upstream = False  # origin/<branch> exists → a plain push reaches it
            except GitError:
                upstream = True  # first push of the branch → set the upstream
            self._git.push(prompts_clone, branch, upstream=upstream)
            return True

        try:
            if branch != self._git.current_branch(prompts_clone):
                self._git.checkout(prompts_clone, branch, ref=f"origin/{branch}")
            pushed = commit_and_push(render_listing(new_rows))
        except GitError as exc:
            # ONE retry: fetch, re-point, re-read the remote listing, re-reconcile.
            ctx.logger.warning(
                "roadmap-dev: listing push failed for %s — one retry (re-read + re-reconcile): %s",
                settings.listing_repo,
                exc,
            )
            actions.append(
                f"listing push conflict for {settings.listing_repo} — retrying after fetch"
            )
            try:
                self._git.fetch(prompts_clone)
                self._git.checkout(prompts_clone, branch, ref=f"origin/{branch}")
                current_md = self._fetch_listing(ctx, prompts_clone)
                new_rows, new_state, logs = reconcile(
                    plans, parse_listing(current_md), new_state, now=self._now()
                )
                actions.extend(logs)
                if commit_and_push(render_listing(new_rows)):
                    actions.append(f"listing pushed to {settings.listing_repo} after retry")
                else:
                    actions.append(
                        f"listing unchanged after retry ({len(new_rows)} row(s)) — no push"
                    )
            except GitError as exc2:
                errors.append(f"listing push failed for {settings.listing_repo}: {exc2}")
                ctx.logger.error(
                    "roadmap-dev: listing push failed for %s (retry): %s",
                    settings.listing_repo,
                    exc2,
                )
        else:
            if pushed:
                actions.append(
                    f"listing pushed to {settings.listing_repo} ({len(new_rows)} row(s))"
                )
            else:
                actions.append(f"listing unchanged ({len(new_rows)} row(s)) — no push")
        return new_state, actions, errors

    def _reap_orphans(self, ctx, st: dict) -> tuple[dict, list[str]]:
        """Reap orphaned ``pending`` plans at run start (state flip + worktree cleanup).

        Purpose:
            The run-start crash recovery (before any scan): every ``pending`` entry in
            the state document belongs to a job that died with its process (crash/
            restart/OOM) — the in-process drain is gone, so the plan is flipped back to
            ``open`` (the pure :func:`reap_orphans`) and its leaked worktrees (execution
            + diagnostics) are removed best-effort. The attempt counter was already
            incremented at job start, so the fresh attempt branch name is free.

        Args:
            ctx: The shared context (sandbox root for the worktree paths, logger).
            st: The loaded + validated state document.

        Returns:
            A ``(new_state_doc, action notes)`` tuple — the document is unchanged (the
            same object, no log lines) when no entry is ``pending``.

        Side Effects:
            Best-effort worktree cleanup under ``<root>/wt`` and ``<root>/diag`` for each
            reaped identity (never raises — a cleanup fault is logged, not fatal).
        """
        entries = st.get("plans") or {}
        pending = [ident for ident, entry in entries.items() if entry.get("state") == "pending"]
        if not pending:
            return st, []
        new_st, actions = reap_orphans(st, now=self._now())
        root = ctx.sandbox_dir / "roadmap-dev"
        for ident in pending:
            repo = new_st["plans"][ident].get("repo") or ""
            if repo:
                clone = clone_dir(root, repo)
                for wt in (
                    plan_worktree_dir(root, repo, ident),
                    diag_worktree_dir(root, repo, ident),
                ):
                    self._best_effort_remove_worktree(ctx, clone, wt)
            ctx.logger.info("roadmap-dev: reaped orphan %s (pending -> open)", ident)
        return new_st, actions

    def _best_effort_remove_worktree(self, ctx, clone: Path | None, wt: Path) -> None:
        """Remove ``wt`` from ``clone`` best-effort (never raises).

        Purpose:
            The reaper's cleanup primitive: remove a leaked worktree and, on failure,
            fall back to a prune + ``rmtree`` so a leftover directory never bricks the
            next attempt. The clone may be absent (the sandbox was partially deleted) —
            then the directory is simply removed from disk.

        Args:
            ctx: The shared context (for logging).
            clone: The full-clone repository the worktree is registered in (or None /
                absent when the clone is gone).
            wt: The worktree directory to remove (may already be gone).

        Side Effects:
            At most one :meth:`Git.worktree_remove` (+ a best-effort prune fallback) or
            one ``shutil.rmtree``; the now-empty per-repo parent dir is removed when it
            is empty (so no empty dirs remain under the sandbox).
        """
        if not wt.exists():
            return
        clone_present = clone is not None and clone.is_dir() and self._git.is_repo(clone)
        try:
            if clone_present:
                self._git.worktree_remove(clone, wt, force=True)
            else:
                shutil.rmtree(wt, ignore_errors=True)
        except GitError as exc:
            ctx.logger.warning(
                "roadmap-dev: worktree_remove failed for %s — falling back: %s", wt, exc
            )
            if clone_present:
                self._prune_best_effort(ctx, clone)
            shutil.rmtree(wt, ignore_errors=True)
        # Remove the now-empty per-repo parent dir so no worktree dirs remain under the
        # sandbox (a leftover empty dir would be noise).
        parent = wt.parent
        try:
            if parent.is_dir() and not any(parent.iterdir()):
                parent.rmdir()
        except OSError:
            pass  # a non-empty or vanished parent is harmless — leave it

    def _prune_best_effort(self, ctx, clone: Path) -> None:
        """Run ``git worktree prune`` best-effort (a failure is logged, never raised).

        Args:
            ctx: The shared context (for logging).
            clone: The full-clone repository to prune.
        """
        try:
            self._git.prune_worktrees(clone)
        except GitError as exc:
            ctx.logger.warning("roadmap-dev: worktree prune failed for %s: %s", clone, exc)

    def _scan_and_reconcile(
        self, ctx, st: dict, errors: list[str]
    ) -> tuple[list[Plan], dict, list[str]]:
        """Run phase 1: reap orphans, scan the allowed repos, reconcile + push the listing.

        Purpose:
            The scan/reconcile surface of one run: (1) reap orphaned ``pending`` entries
            (state flip + worktree cleanup, before any scan); (2) clone-or-fetch every
            allowed repo (config order) and scan all its branches for un-archived plans;
            (3) clone-or-fetch the listing repo and hand the scan + state to
            :meth:`_reconcile_and_push`, which reads the current ``plans.md`` from
            ``origin/<listing_branch>``, reconciles, and commits + pushes when the
            rendered listing changed (one non-fast-forward retry). Without a prompts
            clone the listing push is skipped (the error was already recorded), but the
            scan results + reconciled state still persist.

        Args:
            ctx: The shared context (sandbox, logger, run_id).
            st: The loaded + validated state document (copy-on-write by the reaper and
                the reconciler; the input is never mutated in place).
            errors: The run's business-error list (appended: clone/fetch failures,
                listing push failures) — the caller maps any entry to ``status="error"``.

        Returns:
            A ``(plans, new_state, logs)`` tuple — the scanned plans (this run's
            ``items_found``), the reconciled state document (to be persisted when
            changed), and the human-readable action notes (reaper + scan + reconcile log
            lines + listing push notes + error notes).

        Side Effects:
            Clones/fetches under the sandbox; worktree cleanup for reaped orphans; at
            most one (or two, on the retry) listing commit + push.
        """
        root = ctx.sandbox_dir / "roadmap-dev"
        settings = self._settings
        actions: list[str] = []

        # --- 1. Reaper (before any scan). --- #
        st, reaped = self._reap_orphans(ctx, st)
        actions.extend(reaped)

        # --- 2+3. Per allowed repo (config order): clone-or-fetch + scan. A repo
        #        failure never stops the other repos. --- #
        plans: list[Plan] = []
        for repo in settings.allowed_repos:
            clone = self._clone_or_fetch(
                ctx, self._repo_url(repo), clone_dir(root, repo), repo, errors
            )
            if clone is None:
                continue  # repo-level error already recorded; continue with the next repo
            repo_plans = self._scan_repo(ctx, repo, clone)
            plans.extend(repo_plans)
            actions.append(f"scanned {repo}: {len(repo_plans)} plan(s)")
            ctx.logger.info("roadmap-dev: %s — found %d plan(s)", repo, len(repo_plans))

        # --- 4. Prompts clone (the listing repo). --- #
        prompts_clone = self._clone_or_fetch(
            ctx,
            self._prompts_repo_url(),
            prompts_clone_dir(root),
            f"listing repo {settings.listing_repo}",
            errors,
        )

        # --- 5+6. Read the current listing and reconcile (unconditionally). --- #
        if prompts_clone is None:
            # No listing surface: the scan + reconciled state still persist.
            _, new_state, logs = reconcile(plans, [], st, now=self._now())
            actions.append("listing push skipped (prompts clone unavailable)")
            actions.extend(logs)
        else:
            current_md = self._fetch_listing(ctx, prompts_clone)
            new_state, push_actions, push_errors = self._reconcile_and_push(
                ctx, prompts_clone, plans, st, current_md
            )
            actions.extend(push_actions)
            errors.extend(push_errors)
        return plans, new_state, actions + errors

    # --- Run orchestration --------------------------------------------------- #

    def run(self, ctx) -> WorkflowResult:
        """Perform one run of the roadmap-dev workflow and report its outcome.

        Purpose:
            The scheduler-facing entry point: wrap :meth:`_run` and map any unexpected
            exception to ``status="error"`` (workflows never raise for business failures).
            The run body: no-op on an empty allowlist, else load + validate the state
            document, run phase 1 (reaper + scan + reconcile + push), append the drain
            stub note (Task 4), and persist the state when it changed.

        Failure contract:
            Business failures (e.g. a state schema mismatch, a clone/fetch failure, a
            listing push failure) are returned as ``status="error"`` with the reasons in
            :attr:`WorkflowResult.errors`; unexpected exceptions are caught and mapped
            the same way (logged at ERROR).

        Args:
            ctx: The shared :class:`~agentic_scripts.workflows.base.WorkContext`.

        Returns:
            A :class:`WorkflowResult` (``status`` one of ``"ok"`` / ``"error"``;
            ``items_found`` the scanned plans this run; ``actions`` the side-effect
            notes; ``errors`` the business failures).

        Side Effects:
            Clones/fetches under the sandbox, worktree cleanup for reaped orphans, at
            most one (or two, on retry) listing commit + push, and — only when the state
            document changed — one atomic :meth:`agentic_scripts.state.StateStore.save`.
        """
        try:
            return self._run(ctx)
        except Exception as exc:  # noqa: BLE001 - map unexpected exceptions to a business error
            ctx.logger.error("roadmap-dev run failed unexpectedly: %s", exc)
            return WorkflowResult(
                status="error", errors=[f"unexpected error during roadmap-dev run: {exc}"]
            )

    def _run(self, ctx) -> WorkflowResult:
        """The unwrapped run body (called by :meth:`run`, which maps exceptions)."""
        # --- 1. No repos configured → no-op (no state write). --- #
        if not self._settings.allowed_repos:
            return WorkflowResult(
                status="ok", items_found=0, actions=["no repos configured — nothing to scan"]
            )

        # --- 2. Load + validate state (a mismatch is an operator error: no side effects). --- #
        st = ctx.state.load(_STATE_KEY)
        err = validate_state(st)
        if err is not None:
            return WorkflowResult(status="error", errors=[err])
        if st == {}:
            st = fresh_state()
        loaded_snapshot = json.dumps(st, sort_keys=True)

        # --- 3. Phase 1: reaper + scan + reconcile + push. --- #
        errors: list[str] = []
        plans, new_state, logs = self._scan_and_reconcile(ctx, st, errors)

        # --- 4. Drain (stub until Task 4 — these exact notes are load-bearing for its diff). --- #
        drain_note = (
            "drain: not implemented (Task 4)"
            if ctx.gate_open
            else "drain skipped (idle gate closed)"
        )

        # --- 5. Single atomic state save, only when the document changed. --- #
        if json.dumps(new_state, sort_keys=True) != loaded_snapshot:
            ctx.state.save(_STATE_KEY, new_state)

        return WorkflowResult(
            status="error" if errors else "ok",
            items_found=len(plans),
            actions=logs + [drain_note],
            errors=errors,
        )
