"""Hermetic tests for the roadmap-dev pure core (Task 2).

All time is injected (``NOW``); there is no git, no network, no subprocess, no real
clock, and no filesystem access outside ``tmp_path``. Groups: (A) identity + discovery
+ state schema; (B) the ``plans.md`` listing parser/renderer (byte-stable round-trip +
malformed input); (C) the reconciler + state machine + reaper; (D) the brief / report /
commit renderers; (E) the workflow shell (phase 1 landed in Task 3 — its fixture-repo
pipeline tests live in ``tests/test_roadmap_dev_scan.py``).
"""

from __future__ import annotations

import copy
import dataclasses
import hashlib
import logging
from datetime import UTC, datetime
from pathlib import Path

import pytest

from agentic_scripts.config import Config, RoadmapPrompts
from agentic_scripts.state import StateStore
from agentic_scripts.workflows.base import WorkContext
from agentic_scripts.workflows.roadmap_dev import (
    ARCHIVED_SEGMENT,
    DIAGNOSTIC_FILES,
    LISTING_COLUMNS,
    ListingRow,
    Plan,
    PlanEntry,
    RoadmapDevWorkflow,
    apply_job_outcome,
    archive_commit_message,
    branch_name,
    clone_dir,
    create,
    diag_commit_message,
    diag_worktree_dir,
    discover_plans,
    extract_report_sections,
    extract_title,
    fresh_state,
    job_status_from_report,
    make_plan_entry,
    parse_listing,
    plan_folder_hash,
    plan_identity,
    plan_worktree_dir,
    prompts_clone_dir,
    reap_orphans,
    reconcile,
    render_brief,
    render_commit_title,
    render_listing,
    repo_from_url,
    repo_slug,
    validate_state,
)

# The injected clock (UTC) — the pure core never calls datetime.now() itself.
NOW = datetime(2026, 11, 21, 12, 0, tzinfo=UTC)

# The exact sample from the listing contract (byte-stable round-trip reference).
SAMPLE = (
    "# https://github.com/y2d2/ARP_MPE.git\n"
    "## main\n"
    "| approval | priority | plan | title | state | remove |\n"
    "|----------|----------|------|-------|-------|--------|\n"
    "| ☐ | 1 | planning/orbit-sim/work_plan.md | ORBIT sim extension | open | ☐ |\n"
    "## dev\n"
    "| approval | priority | plan | title | state | remove |\n"
    "|----------|----------|------|-------|-------|--------|\n"
    "| ☑ | 2 | planning/unitest/work_plan.md | Unit tests | review | ☐ |\n"
)


def _plan(
    folder: str = "planning/orbit-sim",
    title: str = "ORBIT sim extension",
    repo: str = "y2d2/ARP_MPE",
    branch: str = "main",
    content_hash: str = "c" * 64,
) -> Plan:
    """Build a :class:`Plan` test fixture with a stable (non-colliding) identity."""
    return Plan(
        repo=repo,
        branch=branch,
        path=f"{folder}/work_plan.md",
        title=title,
        content_hash=content_hash,
    )


def _row(
    plan: Plan,
    *,
    approval: bool = False,
    priority: int = 1,
    state: str = "open",
    remove: bool = False,
    repo_url: str | None = None,
) -> ListingRow:
    """Build a :class:`ListingRow` under the plan's canonical (https) section."""
    return ListingRow(
        repo_url=repo_url or f"https://github.com/{plan.repo}.git",
        branch=plan.branch,
        approval=approval,
        priority=priority,
        plan=plan.path,
        title=plan.title,
        state=state,
        remove=remove,
    )


def _entry(plan: Plan, state: str = "open", **overrides) -> dict:
    """Build a v1 state entry for ``plan`` at ``state`` (stamped from ``NOW``)."""
    entry = make_plan_entry(plan, state, now=NOW)
    entry.update(overrides)
    return entry


def _state_doc(*entries: dict) -> dict:
    """Build a v1 state document from state entries (keyed by identity)."""
    doc = fresh_state()
    for entry in entries:
        doc["plans"][entry["identity"]] = entry
    return doc


# --------------------------------------------------------------------------- #
# A. Identity + discovery + state schema (pure)
# --------------------------------------------------------------------------- #


def test_plan_folder_hash_ignores_diagnostics() -> None:
    """Diagnostics (questions.md/failure.md) never change the hash; any other file does."""
    base = {"work_plan.md": "# T\n", "work_plan_task_1_core.md": "task one\n"}
    h_base = plan_folder_hash(base)
    assert len(h_base) == 64

    # Adding and editing diagnostic files must NOT change the hash.
    h_added = plan_folder_hash({**base, "questions.md": "1. what?\n"})
    h_edited = plan_folder_hash(
        {**base, "failure.md": "boom\n", "questions.md": "1. what? (edited)\n"}
    )
    assert h_base == h_added == h_edited

    # Any change to a non-diagnostic file DOES change the hash.
    assert plan_folder_hash({**base, "work_plan.md": "# T2\n"}) != h_base
    assert plan_folder_hash({**base, "new_task.md": "x\n"}) != h_base

    # Deterministic across dict orderings.
    reversed_ = dict(reversed(list(base.items())))
    assert plan_folder_hash(reversed_) == h_base

    # A diagnostics-only folder hashes to the empty string's digest.
    assert (
        plan_folder_hash({"questions.md": "q\n", "failure.md": "f\n"})
        == hashlib.sha256(b"").hexdigest()
    )
    # The diagnostic set is exactly the two workflow-written files.
    assert DIAGNOSTIC_FILES == frozenset({"questions.md", "failure.md"})


def test_plan_identity_hex_stable_distinct() -> None:
    """plan_identity is 12 hex chars; stable; distinct for each differing input."""
    repo, branch, path, chash = "y2d2/ARP_MPE", "main", "planning/orbit-sim/work_plan.md", "c" * 64
    ident = plan_identity(repo, branch, path, chash)
    assert ident == plan_identity(repo, branch, path, chash)  # stable
    assert len(ident) == 12
    int(ident, 16)  # raises ValueError if not hex

    ids = {
        ident,
        plan_identity("other/repo", branch, path, chash),  # different repo
        plan_identity(repo, "dev", path, chash),  # different branch
        plan_identity(repo, branch, "planning/other/work_plan.md", chash),  # different path
        plan_identity(repo, branch, path, "d" * 64),  # different content hash
    }
    assert len(ids) == 5
    # The Plan property recomputes the same identity.
    plan = _plan()
    assert plan.identity == plan_identity(plan.repo, plan.branch, plan.path, plan.content_hash)


def test_branch_name() -> None:
    """branch_name enforces the roadmap-dev/<id>-<attempt> fresh-branch invariant."""
    assert branch_name("abc123def456", 1) == "roadmap-dev/abc123def456-1"
    assert branch_name("abc123def456", 2) == "roadmap-dev/abc123def456-2"


def test_extract_title() -> None:
    """extract_title: # Title → Title; #  Double → Double; no h1 → Untitled plan."""
    assert extract_title("# Title\nbody text\n") == "Title"
    assert extract_title("#  Double\n") == "Double"
    assert extract_title("intro line\n# Late title\n") == "Late title"
    assert extract_title("no heading here\n## subheading only\n") == "Untitled plan"
    assert extract_title("") == "Untitled plan"


def test_discover_plans_filters_sorts_and_stamps() -> None:
    """discover_plans keeps valid planning/ folders, drops malformed/archived, sorts by dir."""
    entries = [
        PlanEntry(
            dir="planning/zeta", work_plan_text="# Z\n", file_texts={"work_plan.md": "# Z\n"}
        ),
        PlanEntry(dir="planning/alpha", work_plan_text=None, file_texts={}),  # malformed
        PlanEntry(  # archived (an 'archived' path segment) → dropped
            dir=f"planning/{ARCHIVED_SEGMENT}/orbit", work_plan_text="# A\n", file_texts={}
        ),
        PlanEntry(
            dir="docs/plans/orbit", work_plan_text="# D\n", file_texts={}
        ),  # not under planning/
        PlanEntry(
            dir="planning/alpha2",
            work_plan_text="# Alpha\n",
            file_texts={"work_plan.md": "# Alpha\n", "questions.md": "stale\n"},
        ),
    ]
    plans = discover_plans("o/r", "main", entries)
    assert [p.path for p in plans] == [
        "planning/alpha2/work_plan.md",  # sorted by dir
        "planning/zeta/work_plan.md",
    ]
    alpha = plans[0]
    assert (alpha.repo, alpha.branch) == ("o/r", "main")
    assert alpha.title == "Alpha"
    assert alpha.topic == "planning/alpha2"
    # The content hash excludes the diagnostic file.
    assert alpha.content_hash == plan_folder_hash({"work_plan.md": "# Alpha\n"})
    assert alpha.identity == plan_identity("o/r", "main", alpha.path, alpha.content_hash)


def test_repo_slug_and_layout_paths(tmp_path: Path) -> None:
    """Layout helpers nest clones/wt/diag/prompts under the composed sandbox root."""
    assert repo_slug("owner/name") == "owner__name"
    sandbox = tmp_path / "roadmap-dev"
    assert clone_dir(sandbox, "owner/name") == sandbox / "clones" / "owner__name"
    assert plan_worktree_dir(sandbox, "owner/name", "abc123def456") == (
        sandbox / "wt" / "owner__name" / "abc123def456"
    )
    assert diag_worktree_dir(sandbox, "owner/name", "abc123def456") == (
        sandbox / "diag" / "owner__name" / "abc123def456"
    )
    assert prompts_clone_dir(sandbox) == sandbox / "prompts"


def test_fresh_state_validate_and_make_entry() -> None:
    """v1 state schema: fresh/validate/make_plan_entry (stamped from the injected now)."""
    assert fresh_state() == {"version": 1, "plans": {}}
    assert validate_state({}) is None  # first run
    assert validate_state({"version": 1, "plans": {}}) is None

    bad_version = validate_state({"version": 2, "plans": {}})
    assert bad_version is not None
    assert "state schema mismatch" in bad_version
    assert "delete state/roadmap-dev.json" in bad_version

    bad_plans = validate_state({"version": 1, "plans": [1]})
    assert bad_plans is not None
    assert "state schema mismatch" in bad_plans

    plan = _plan()
    entry = make_plan_entry(plan, "open", now=NOW)
    assert entry["identity"] == plan.identity
    assert entry["repo"] == "y2d2/ARP_MPE" and entry["branch"] == "main"
    assert entry["path"] == "planning/orbit-sim/work_plan.md"
    assert entry["title"] == "ORBIT sim extension"
    assert entry["content_hash"] == "c" * 64
    assert entry["state"] == "open"
    assert entry["attempt"] == 0
    assert entry["updated_at"] == "2026-11-21T12:00:00+00:00"
    # The branch-name fields (no PR fields — this workflow never creates PRs).
    assert entry["branch_name"] is None
    assert entry["commit_sha"] is None
    assert entry["pid"] is None
    assert "pr_number" not in entry and "pr_url" not in entry

    # Overrides win; a naive (local) now is normalised to UTC.
    entry2 = make_plan_entry(
        plan, "pending", now=datetime(2026, 11, 21, 14, 0), attempt=3, last_run_id="r1"
    )
    assert entry2["state"] == "pending"
    assert entry2["attempt"] == 3
    assert entry2["last_run_id"] == "r1"
    assert entry2["updated_at"] == "2026-11-21T14:00:00+00:00"


# --------------------------------------------------------------------------- #
# B. Listing parser + renderer (pure, byte-stable)
# --------------------------------------------------------------------------- #


def test_parse_listing_round_trip_sample() -> None:
    """The contract sample parses to exact rows and renders back byte-identically."""
    rows = parse_listing(SAMPLE)
    assert rows == [
        ListingRow(
            repo_url="https://github.com/y2d2/ARP_MPE.git",
            branch="main",
            approval=False,
            priority=1,
            plan="planning/orbit-sim/work_plan.md",
            title="ORBIT sim extension",
            state="open",
            remove=False,
        ),
        ListingRow(
            repo_url="https://github.com/y2d2/ARP_MPE.git",
            branch="dev",
            approval=True,
            priority=2,
            plan="planning/unitest/work_plan.md",
            title="Unit tests",
            state="review",
            remove=False,
        ),
    ]
    # Byte-identical round-trip (incl. the trailing newline).
    assert render_listing(rows) == SAMPLE


def test_parse_listing_malformed_input_never_raises() -> None:
    """Wrong column counts, non-int priorities, free text, unknown headers → skipped."""
    md = (
        "free text before any section\n"
        "## no-repo-branch\n"  # ## outside a repo section → skipped
        "| ☐ | 1 | planning/x/work_plan.md | X | open | ☐ |\n"  # outside a section → skipped
        "# https://github.com/o/r.git\n"
        "### unknown heading\n"  # not a #/## line → skipped
        "notes between sections\n"
        "## main\n"
        "| approval | priority | plan | title | state | remove |\n"
        "|----------|----------|------|-------|-------|--------|\n"
        "| ☐ | one | planning/a/work_plan.md | A | open | ☐ |\n"  # non-int priority → skipped
        "| ☐ | 2 | planning/a/work_plan.md | A | open |\n"  # 5 cells → skipped
        "| ☐ | 3 | planning/a/work_plan.md | A | open | ☐ | extra |\n"  # 7 cells → skipped
        "| [x] | 4 | planning/b/work_plan.md | B | open | [ ] |\n"  # non-glyph checks → False
        "## dev\n"
        "| ☑ | 5 | planning/c/work_plan.md | C | review | ☑ |\n"
    )
    rows = parse_listing(md)
    assert [r.plan for r in rows] == ["planning/b/work_plan.md", "planning/c/work_plan.md"]
    b, c = rows
    assert (b.approval, b.priority, b.remove) == (False, 4, False)
    assert (c.approval, c.priority, c.state, c.remove) == (True, 5, "review", True)

    # Empty checkbox cells → False (only the ☑ glyph is True).
    empty_check = parse_listing(
        "# https://github.com/o/r.git\n"
        "## main\n"
        "| approval | priority | plan | title | state | remove |\n"
        "|----------|----------|------|-------|-------|--------|\n"
        "|  | 6 | planning/d/work_plan.md | D | open |  |\n"
    )
    assert len(empty_check) == 1
    assert (empty_check[0].approval, empty_check[0].remove) == (False, False)

    assert parse_listing("") == []


def test_render_listing_empty_stable_and_ordered() -> None:
    """render_listing: sections in first-appearance order, byte-stable, '' for no rows."""
    assert render_listing([]) == ""

    r1 = ListingRow(
        "https://github.com/o/r.git", "main", True, 2, "planning/a/work_plan.md", "A", "open", False
    )
    r2 = ListingRow(
        "https://github.com/o/r.git",
        "dev",
        False,
        1,
        "planning/b/work_plan.md",
        "B",
        "success",
        True,
    )
    r3 = ListingRow(
        "https://github.com/o/s.git",
        "main",
        False,
        3,
        "planning/c/work_plan.md",
        "C",
        "failure",
        False,
    )
    out = render_listing([r1, r2, r3])
    assert out == (
        "# https://github.com/o/r.git\n"
        "## main\n"
        "| approval | priority | plan | title | state | remove |\n"
        "|----------|----------|------|-------|-------|--------|\n"
        "| ☑ | 2 | planning/a/work_plan.md | A | open | ☐ |\n"
        "## dev\n"
        "| approval | priority | plan | title | state | remove |\n"
        "|----------|----------|------|-------|-------|--------|\n"
        "| ☐ | 1 | planning/b/work_plan.md | B | success | ☑ |\n"
        "# https://github.com/o/s.git\n"
        "## main\n"
        "| approval | priority | plan | title | state | remove |\n"
        "|----------|----------|------|-------|-------|--------|\n"
        "| ☐ | 3 | planning/c/work_plan.md | C | failure | ☐ |\n"
    )
    # Byte-stable across repeated calls; no trailing spaces; single trailing newline.
    assert render_listing([r1, r2, r3]) == out
    assert out.endswith("\n") and not out.endswith("\n\n")
    assert all(line == line.rstrip() for line in out.splitlines())
    # The header column tuple is the contract constant.
    assert LISTING_COLUMNS == ("approval", "priority", "plan", "title", "state", "remove")


# --------------------------------------------------------------------------- #
# C. Reconciler + state machine + reaper (pure)
# --------------------------------------------------------------------------- #


def test_repo_from_url_forms() -> None:
    """repo_from_url accepts https + git@ forms (±.git); anything else → None (ghost)."""
    assert repo_from_url("https://github.com/y2d2/ARP_MPE.git") == "y2d2/ARP_MPE"
    assert repo_from_url("https://github.com/y2d2/ARP_MPE") == "y2d2/ARP_MPE"
    assert repo_from_url("git@github.com:y2d2/ARP_MPE.git") == "y2d2/ARP_MPE"
    assert repo_from_url("git@github.com:y2d2/ARP_MPE") == "y2d2/ARP_MPE"
    assert repo_from_url("  https://github.com/y2d2/ARP_MPE.git  ") == "y2d2/ARP_MPE"
    assert repo_from_url("/tmp/local/mirror") is None
    assert repo_from_url("git@github.com:onlyowner") is None
    assert repo_from_url("https://github.com/a/b/c.git") is None
    assert repo_from_url("") is None


def test_reconcile_discovers_new_plan_empty_and_nonempty_table() -> None:
    """New plan → row under the right section, no checkmarks, priority max+1 / 1, entry."""
    plan = _plan()

    # Empty listing → priority 1; state entry created; discovery logged.
    rows, doc, log = reconcile([plan], [], fresh_state(), now=NOW)
    assert rows == [
        ListingRow(
            "https://github.com/y2d2/ARP_MPE.git",
            "main",
            False,
            1,
            plan.path,
            plan.title,
            "open",
            False,
        )
    ]
    assert doc["plans"][plan.identity]["state"] == "open"
    assert doc["plans"][plan.identity]["attempt"] == 0
    assert f"discovered {plan.identity} (y2d2/ARP_MPE @ main)" in log

    # Non-empty table in the same (repo_url, branch) section → priority max+1.
    other = _plan(folder="planning/unitest", title="Unit tests")
    existing = _row(other, approval=True, priority=4)
    rows2, doc2, log2 = reconcile([plan, other], [existing], _state_doc(_entry(other)), now=NOW)
    by_plan = {r.plan: r for r in rows2}
    assert by_plan[plan.path].priority == 5
    assert by_plan[plan.path].approval is False
    # The existing row survives with its user cells intact, in its original position.
    assert rows2[0] == existing
    assert [r.plan for r in rows2] == [other.path, plan.path]
    assert f"discovered {plan.identity} (y2d2/ARP_MPE @ main)" in log2
    assert doc2["plans"][plan.identity]["state"] == "open"


def test_reconcile_preserves_user_cells_across_repeated_passes() -> None:
    """Steady state: 3 reconciles → byte-identical listing, state doc unchanged, no logs."""
    plan = _plan()
    row = _row(plan, approval=True, priority=5, state="open")
    doc = _state_doc(_entry(plan, "open"))
    md_in = render_listing([row])

    for _ in range(3):
        rows_out, doc_out, log = reconcile([plan], parse_listing(md_in), doc, now=NOW)
        assert render_listing(rows_out) == md_in  # byte-stable md
        assert doc_out == doc  # state doc unchanged
        assert log == []


def test_reconcile_rearms_failure_row_set_open_by_user() -> None:
    """State doc failure + row state open → the user's open wins; doc synced + logged."""
    plan = _plan()
    row = _row(plan, approval=True, priority=2, state="open")
    doc = _state_doc(_entry(plan, "failure", last_error="boom"))
    later = datetime(2026, 11, 21, 13, 0, tzinfo=UTC)

    rows_out, doc_out, log = reconcile([plan], [row], doc, now=later)

    assert rows_out == [row]  # the row keeps open
    entry = doc_out["plans"][plan.identity]
    assert entry["state"] == "open"  # state doc synced to open
    assert entry["last_error"] == "boom"  # the rest of the entry is preserved
    assert entry["updated_at"] == "2026-11-21T13:00:00+00:00"  # stamped from the injected now
    assert f"re-armed {plan.identity} (user set open)" in log


def test_reconcile_state_divergence_workflow_wins() -> None:
    """Any non-failure divergence → the workflow (state-doc) state cell wins."""
    plan = _plan()
    row = _row(plan, approval=True, priority=3, state="open")
    doc = _state_doc(_entry(plan, "review"))

    rows_out, _, log = reconcile([plan], [row], doc, now=NOW)
    out = rows_out[0]
    assert out.state == "review"  # workflow wins
    assert (out.approval, out.priority, out.remove) == (True, 3, False)  # user cells kept
    assert not any("re-armed" in line for line in log)  # re-arm requires doc state failure

    # Reverse divergence (row failure, doc open) → the row is corrected to open.
    doc2 = _state_doc(_entry(plan, "open"))
    rows2, _, _ = reconcile([plan], [_row(plan, state="failure")], doc2, now=NOW)
    assert rows2[0].state == "open"


def test_reconcile_remove_success_scanned_reappears() -> None:
    """remove ☑ on a success row (still scanned) → drop + re-add as success in one pass."""
    plan = _plan()
    row = _row(plan, approval=True, priority=1, state="success", remove=True)
    doc = _state_doc(_entry(plan, "success"))

    rows_out, doc_out, log = reconcile([plan], [row], doc, now=NOW)

    assert len(rows_out) == 1
    out = rows_out[0]
    assert out.state == "success"
    assert out.remove is False  # fresh remove cell
    assert out.approval is True  # approval as before
    assert out.priority == 1  # table empty after the drop → max+1 = 1
    assert f"removed {plan.identity} (user remove tick)" in log
    # The state entry is KEPT (success entries are never deleted).
    assert doc_out["plans"][plan.identity]["state"] == "success"


def test_reconcile_remove_success_unscanned_dropped() -> None:
    """remove ☑ on a success row (plan NOT scanned) → simply dropped, entry kept."""
    plan = _plan()
    row = _row(plan, state="success", remove=True)
    doc = _state_doc(_entry(plan, "success"))

    rows_out, doc_out, log = reconcile([], [row], doc, now=NOW)

    assert rows_out == []
    assert plan.identity in doc_out["plans"]  # entry kept (forensics)
    assert f"removed {plan.identity} (user remove tick)" in log


def test_reconcile_vanished_plan_drops_row_keeps_entry() -> None:
    """In state + not scanned → row dropped, state entry kept, logged."""
    plan = _plan()
    row = _row(plan, state="open")
    doc = _state_doc(_entry(plan, "open"))

    rows_out, doc_out, log = reconcile([], [row], doc, now=NOW)

    assert rows_out == []
    assert plan.identity in doc_out["plans"]
    assert f"dropped row {plan.identity} (plan no longer in scan)" in log


def test_reconcile_ghost_row_dropped() -> None:
    """A row in neither scan nor state → dropped with a ghost log line."""
    ghost = _row(_plan(folder="planning/ghosty", title="Ghost"))
    rows_out, doc_out, log = reconcile([], [ghost], fresh_state(), now=NOW)

    assert rows_out == []
    assert doc_out["plans"] == {}
    assert f"dropped ghost row {ghost.plan} (no state entry)" in log


def test_reconcile_input_doc_not_mutated() -> None:
    """reconcile is copy-on-write: the input state doc is never mutated."""
    plan = _plan()
    doc = _state_doc(_entry(plan, "failure"))
    snapshot = copy.deepcopy(doc)

    reconcile([plan], [_row(plan, state="open")], doc, now=NOW)  # triggers the re-arm

    assert doc == snapshot


def test_reconcile_force_unapproved() -> None:
    """force_unapproved de-approves the named row (the one sanctioned user-cell overwrite)."""
    plan = _plan()
    row = _row(plan, approval=True, priority=2)
    doc = _state_doc(_entry(plan, "open"))

    rows_out, _, log = reconcile(
        [plan], [row], doc, now=NOW, force_unapproved=frozenset({plan.identity})
    )
    assert rows_out[0].approval is False
    assert f"unapproved {plan.identity} (questions raised)" in log

    # Without the flag the checkmark is preserved.
    rows2, _, log2 = reconcile([plan], [row], doc, now=NOW)
    assert rows2[0].approval is True
    assert not any("unapproved" in line for line in log2)


def test_reconcile_new_rows_same_section_get_consecutive_priorities() -> None:
    """Two new plans in one empty section get priority 1 then 2 (no ties)."""
    a = _plan(folder="planning/a", title="A")
    b = _plan(folder="planning/b", title="B")
    rows, _, _ = reconcile([a, b], [], fresh_state(), now=NOW)
    by_plan = {r.plan: r for r in rows}
    assert by_plan[a.path].priority == 1
    assert by_plan[b.path].priority == 2
    # Output order: scan-only section, plans sorted by (repo, branch, path).
    assert [r.plan for r in rows] == [a.path, b.path]


def test_reap_orphans_flips_pending_only() -> None:
    """reap_orphans flips every pending → open (cleared bookkeeping), others untouched."""
    a = _plan(folder="planning/a", title="A")
    b = _plan(folder="planning/b", title="B")
    doc = _state_doc(
        _entry(a, "pending", pid=1234, started_at="2026-11-21T10:00:00+00:00"),
        _entry(b, "success"),
    )

    new_doc, log = reap_orphans(doc, now=NOW)

    reaped = new_doc["plans"][a.identity]
    assert reaped["state"] == "open"
    assert reaped["last_error"] == "orphaned pending (crash/restart) — reaped"
    assert reaped["pid"] is None
    assert reaped["started_at"] is None
    assert new_doc["plans"][b.identity] == doc["plans"][b.identity]  # untouched
    assert log == [f"reaped orphan {a.identity} (pending -> open)"]  # one line per identity
    assert doc["plans"][a.identity]["state"] == "pending"  # input not mutated

    # A doc without pending entries → no-op.
    noop_doc, noop_log = reap_orphans(new_doc, now=NOW)
    assert noop_doc == new_doc
    assert noop_log == []


def test_apply_job_outcome_all_outcomes() -> None:
    """apply_job_outcome maps success/questions/failure and stamps finished_at."""
    plan = _plan()
    entry = _entry(plan, "pending", attempt=2)
    now = datetime(2026, 11, 21, 16, 30, tzinfo=UTC)

    ok = apply_job_outcome(
        entry,
        "success",
        now=now,
        branch_name="roadmap-dev/x-2",
        commit_sha="abc123",
        last_run_id="r9",
    )
    assert ok["state"] == "success"
    assert ok["branch_name"] == "roadmap-dev/x-2"  # the delivery surface (NO PR)
    assert ok["commit_sha"] == "abc123"
    assert ok["attempt"] == 2  # unchanged (incremented at start, by the pipeline)
    assert ok["finished_at"] == "2026-11-21T16:30:00+00:00"

    questions = apply_job_outcome(entry, "questions", now=now, last_run_id="r9")
    assert questions["state"] == "review"
    assert questions["branch_name"] is None

    failed = apply_job_outcome(entry, "failure", now=now, last_error="boom", last_run_id="r9")
    assert failed["state"] == "failure"
    assert failed["last_error"] == "boom"

    with pytest.raises(ValueError):
        apply_job_outcome(entry, "exploded", now=now)

    assert entry["state"] == "pending"  # the input entry is not mutated


# --------------------------------------------------------------------------- #
# D. Brief + report + commit renderers (pure, byte-stable)
# --------------------------------------------------------------------------- #


def test_render_brief_exact_and_byte_stable() -> None:
    """render_brief emits the exact mandated brief (verbatim substrings, stable)."""
    plan = _plan()
    brief = render_brief(
        run_id="r1",
        plan=plan,
        repo_url="https://github.com/y2d2/ARP_MPE.git",
        attempt=3,
        timeout_minutes=480,
        test_cmd=None,
    )
    expected = (
        "roadmap-dev autonomous run r1 — execute ONE approved plan, pre-approved, "
        "no user present.\n"
        "\n"
        "Plan: planning/orbit-sim/work_plan.md\n"
        "Repo: https://github.com/y2d2/ARP_MPE.git   Branch: main   Title: ORBIT sim extension\n"
        "Attempt: 3   Hard budget: 480 minutes (process will be killed at the deadline).\n"
        "\n"
        "You are running headless. There is NO user: the question tool is unavailable, "
        "nothing is\n"
        "pending your approval — this run is fully pre-approved. Do NOT ask questions, "
        "do NOT wait.\n"
        "\n"
        "1. REVIEW THE PLAN. Read planning/orbit-sim/work_plan.md and every task file in "
        "its folder.\n"
        "   - MAJOR question = anything that would change scope, requirements, or "
        "dependencies\n"
        "     (NOT an implementation detail). If — and only if — a major open question "
        "exists:\n"
        "     write it to planning/orbit-sim/questions.md (numbered questions, each with "
        "context and\n"
        "     exactly what you need answered), change nothing else, and finish with the "
        "result\n"
        '     report whose status line is "Status: questions". Do NOT execute any task.\n'
        "   - MINOR things: decide yourself; record each decision in your result report "
        "only.\n"
        "   - If planning/orbit-sim/questions.md already contains user answers, read them "
        "and proceed\n"
        "     (they answer a previous round of this same plan).\n"
        "2. EXECUTE IN SEQUENCE. Dispatch @lightweight-dev ONE small self-contained task "
        "at a time\n"
        "   — strictly sequential, NEVER in parallel — and verify each task's acceptance "
        "criteria\n"
        "   from its result report before dispatching the next.\n"
        "3. REPORT. Your final message must be the result report:\n"
        "   ## Summary / ## Files / ## Tests / ## Blockers\n"
        "   plus an explicit status line, exactly one of:\n"
        "     Status: success      (every task done, every acceptance criterion verified)\n"
        "     Status: questions    (major questions written to questions.md, no task "
        "executed)\n"
        "     Status: failure      (cannot proceed; explain why in Blockers)\n"
        "   Test command: none configured — the runner runs tests itself\n"
        "\n"
        "Git rules: do NOT run git commit or git push — the runner owns git and will "
        "commit,\n"
        "archive the plan folder and push the branch after you exit (a human opens the "
        "PR).\n"
        "Work ONLY inside this worktree."
    )
    assert brief == expected

    # The acceptance criterion's verbatim substrings.
    lines = brief.splitlines()
    for needle in (
        "pre-approved, no user present",
        "question tool is unavailable",
        "NEVER in parallel",
        "planning/orbit-sim/work_plan.md",  # the plan path
        "Attempt: 3   Hard budget: 480 minutes (process will be killed at the deadline).",
        "     Status: success      (every task done, every acceptance criterion verified)",
        "     Status: questions    (major questions written to questions.md, no task executed)",
        "     Status: failure      (cannot proceed; explain why in Blockers)",
    ):
        assert needle in brief
        if needle.startswith("     Status:"):
            assert needle in lines  # each status line is a line of its own

    # Byte-stable across calls.
    assert brief == render_brief(
        run_id="r1",
        plan=plan,
        repo_url="https://github.com/y2d2/ARP_MPE.git",
        attempt=3,
        timeout_minutes=480,
        test_cmd=None,
    )


def test_render_brief_test_command_line() -> None:
    """The test-command line renders the configured command or the none-configured note."""
    plan = _plan()
    with_cmd = render_brief(
        run_id="r1",
        plan=plan,
        repo_url="https://github.com/y2d2/ARP_MPE.git",
        attempt=1,
        timeout_minutes=60,
        test_cmd="uv run pytest",
    )
    assert "   Test command: uv run pytest" in with_cmd.splitlines()

    no_cmd = render_brief(
        run_id="r1",
        plan=plan,
        repo_url="https://github.com/y2d2/ARP_MPE.git",
        attempt=1,
        timeout_minutes=60,
        test_cmd=None,
    )
    assert "   Test command: none configured — the runner runs tests itself" in no_cmd.splitlines()


def test_job_status_from_report() -> None:
    """job_status_from_report: first allowed status line wins (case-insensitive), else None."""
    report = "## Summary\nDid it.\n\nStatus: questions\n\n## Blockers\nNone\n"
    assert job_status_from_report(report) == "questions"
    assert job_status_from_report("## Summary\nno status line here\n") is None
    assert job_status_from_report(None) is None
    assert job_status_from_report("") is None
    assert job_status_from_report("status: SUCCESS\n") == "success"
    # "succeeded" is not an allowed outcome on that line → no match...
    assert job_status_from_report("Status: succeeded\n") is None
    # ...but a real line later in the report still wins.
    assert job_status_from_report("Status: succeeded\nblah\n  Status: failure\n") == "failure"


def test_extract_report_sections_matches_oc_todo_behavior() -> None:
    """extract_report_sections: same headings map + return shape as the oc_todo version."""
    report = (
        "# roadmap-dev Output\n"
        "\n"
        "## Summary\n"
        "Ran the plan end to end.\n"
        "\n"
        "## Files\n"
        "| `a.py` | modify |\n"
        "\n"
        "## Build / Tests\n"
        "- `uv run pytest`: PASS\n"
        "\n"
        "## Acceptance Verification\n"
        "- All green\n"
        "\n"
        "## Blockers\n"
        "None\n"
    )
    sections = extract_report_sections(report)
    assert sections["has_report"] is True
    assert sections["summary"] == "Ran the plan end to end."
    assert "a.py" in sections["files"]
    assert "PASS" in sections["tests"]
    assert sections["blockers"].lower() == "none"

    # A report missing ## Blockers → blockers "" (other sections still extracted).
    no_blockers = "## Summary\nS\n\n## Files\nF\n\n## Build / Tests\nT\n"
    got = extract_report_sections(no_blockers)
    assert got["blockers"] == ""
    assert got["summary"] == "S"

    # None input → all empty + has_report False.
    empty = extract_report_sections(None)
    assert empty == {"summary": "", "files": "", "tests": "", "blockers": "", "has_report": False}


def test_render_commit_title_truncates_at_72_total() -> None:
    """render_commit_title = 'OC: <title>' truncated to 72 chars TOTAL (no ellipsis)."""
    short = _plan(title="Fix the parser")
    assert render_commit_title(short) == "OC: Fix the parser"

    long = _plan(title="x" * 100)
    out = render_commit_title(long)
    assert len(out) == 72
    assert out == "OC: " + "x" * 68

    # A title exactly at the boundary is untouched.
    boundary = _plan(title="y" * 68)
    assert render_commit_title(boundary) == "OC: " + "y" * 68


def test_archive_and_diag_commit_messages() -> None:
    """archive/diag commit messages are the exact documented strings."""
    assert archive_commit_message("abc123def456", "r1") == (
        "OC: roadmap-dev: archive plan abc123def456 (run r1)"
    )
    assert diag_commit_message("abc123def456", "questions", "r1") == (
        "OC: roadmap-dev: abc123def456 — questions (run r1)"
    )
    assert diag_commit_message("abc123def456", "failure", "r2") == (
        "OC: roadmap-dev: abc123def456 — failure (run r2)"
    )
    with pytest.raises(ValueError):
        diag_commit_message("abc123def456", "merged", "r1")


# --------------------------------------------------------------------------- #
# E. Workflow shell (phase 1 pipeline; drain stub — pipeline integration in
#    tests/test_roadmap_dev_scan.py)
# --------------------------------------------------------------------------- #


def _roadmap_config(base_config: Config, allowed_repos: list[str]) -> Config:
    """Point ``base_config``'s roadmap_prompts at the given allowed repos."""
    rp = RoadmapPrompts(
        allowed_repos=allowed_repos,
        listing_repo="y2d2/ARP_prompts",
        listing_repo_url="",
        listing_path="plans.md",
        listing_branch="main",
        run_timeout_minutes=480,
        test_commands={},
        repo_urls={},
    )
    return dataclasses.replace(base_config, roadmap_prompts=rp)


def _ctx(config: Config, state_dir: Path) -> WorkContext:
    """Build a hermetic :class:`WorkContext` rooted at ``tmp_path``."""
    return WorkContext(
        config=config,
        state=StateStore(state_dir),
        logger=logging.getLogger("test.roadmap_dev"),
        run_id="run-test",
        workflow_name="roadmap-dev",
        sandbox_dir=state_dir.parent / "sandbox",
        admin_repo=None,
    )


def test_create_returns_named_workflow(base_config: Config) -> None:
    """create on a T1-style config returns a roadmap-dev workflow (no github seam)."""
    wf = create(base_config)
    assert isinstance(wf, RoadmapDevWorkflow)
    assert wf.name == "roadmap-dev"
    # There is deliberately NO GitHub collaborator (this workflow never calls the API).
    assert not hasattr(wf, "_github")
    assert wf._runner_override is None


def test_constructor_seams(base_config: Config) -> None:
    """Injected active_sessions/now_fn seams are used; defaults stay lazy."""

    def probe() -> int:
        return 7

    fixed = datetime(2026, 11, 21, 15, 30, tzinfo=UTC)

    def clock() -> datetime:
        return fixed

    wf = RoadmapDevWorkflow(base_config.roadmap_prompts, active_sessions=probe, now_fn=clock)
    assert wf._active_session_count() == 7
    assert wf._now() == fixed


def test_run_empty_allowed_repos_is_noop(base_config: Config, tmp_path: Path) -> None:
    """run with an empty allowlist → ok, the no-repos action, and NO state write."""
    # The shipped T1 config has roadmap_prompts.allowed_repos: [].
    wf = create(base_config)
    result = wf.run(_ctx(base_config, tmp_path / "state"))

    assert result.status == "ok"
    assert result.actions == ["no repos configured — nothing to scan"]
    assert result.errors == []
    assert not (tmp_path / "state" / "roadmap-dev.json").exists()  # no state write


def test_run_state_schema_mismatch_is_business_error(base_config: Config, tmp_path: Path) -> None:
    """A schema-mismatched state document → status error with the operator message."""
    config = _roadmap_config(base_config, ["o/r"])
    state_dir = tmp_path / "state"
    StateStore(state_dir).save("roadmap-dev", {"version": 2, "plans": {}})

    result = create(config).run(_ctx(config, state_dir))

    assert result.status == "error"
    assert "state schema mismatch" in result.errors[0]
    assert "delete state/roadmap-dev.json" in result.errors[0]


def test_run_maps_unexpected_exceptions_to_error(base_config: Config, tmp_path: Path) -> None:
    """run wraps _run: an unexpected exception becomes status='error' (never raised)."""
    config = _roadmap_config(base_config, ["o/r"])
    ctx = _ctx(config, tmp_path / "state")

    class _BoomState:
        def load(self, name: str) -> dict:
            raise RuntimeError("boom")

        def save(self, name: str, data: dict) -> None:
            raise AssertionError("unreachable")

    ctx.state = _BoomState()  # type: ignore[assignment]

    result = create(config).run(ctx)
    assert result.status == "error"
    assert result.errors == ["unexpected error during roadmap-dev run: boom"]
