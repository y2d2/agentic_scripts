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
import yaml

from agentic_scripts.config import Config, RoadmapPrompts, load_config
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
    extract_goal,
    extract_report_sections,
    extract_task_titles,
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
    task_done_labels,
    validate_state,
)

# The injected clock (UTC) — the pure core never calls datetime.now() itself.
NOW = datetime(2026, 11, 21, 12, 0, tzinfo=UTC)


@pytest.fixture
def base_config(tmp_path: Path) -> Config:
    """Shipped-config copy for the roadmap suite (deliberately shadows ``tests/conftest``).

    Purpose:
        Load ``config/workflows.yaml`` with ``paths`` pointed at a tmp workspace and
        ``roadmap_prompts.allowed_repos`` seeded to ``[]``, through :func:`load_config`
        (full validation) — the T1-style config the E-group workflow-shell tests need.

    Rationale:
        The shared :func:`tests.conftest.base_config` strips ``roadmap-dev`` and its
        ``roadmap_prompts`` section (the shipped-config hermeticity guard for
        scheduler-driving tests). Roadmap tests must NOT get the stripped copy — an
        empty-section config would make the shell tests pass vacuously — so this
        module-local fixture shadows it (pytest resolves module fixtures first). Safe
        because nothing here calls :func:`agentic_scripts.scheduler.run`: the workflow
        is constructed and driven directly, and the seeded-empty allowlist keeps even
        the ``create(base_config)`` no-op path away from any real repo.

        Extra local delta: ``local_listing`` is set to ``null``. The local listing
        mirror (see :meth:`RoadmapDevWorkflow._mirror_listing`) has no counterpart in
        the ported source, and its write would add a ``listing mirrored to …`` action
        note; the mirror is covered by its own section-G tests below, so it stays off
        here and the ported action-count assertions hold byte-for-byte.

    Args:
        tmp_path: The pytest temporary directory holding the config copy and dirs.

    Returns:
        A fully validated :class:`Config` with tmp paths, the roadmap section present,
        its allowlist empty, and the local mirror disabled.
    """
    root = Path(__file__).resolve().parents[1]
    data = yaml.safe_load((root / "config" / "workflows.yaml").read_text(encoding="utf-8"))
    data["paths"] = {
        "state_dir": str(tmp_path / "state"),
        "log_dir": str(tmp_path / "logs"),
        "sandbox_dir": str(tmp_path / "sandbox"),
    }
    # hermetic: seeded allowlist; tests exercise the workflow shell, not scanning.
    data["roadmap_prompts"]["allowed_repos"] = []
    data["roadmap_prompts"]["local_listing"] = None  # mirror covered by section G below
    cfg_path = tmp_path / "workflows.yaml"
    cfg_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return load_config(cfg_path)

# The exact sample from the listing contract (byte-stable round-trip reference; the
# plain pre-section form — the parser must keep accepting such legacy listings).
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
    goal: str = "",
    task_titles: tuple[tuple[str, str], ...] = (),
) -> Plan:
    """Build a :class:`Plan` test fixture with a stable (non-colliding) identity.

    ``goal`` / ``task_titles`` default to empty (the parsed-row shape) so the listing
    renders byte-stably across the steady-state tests; pass them to exercise the
    details-table stamping.
    """
    return Plan(
        repo=repo,
        branch=branch,
        path=f"{folder}/work_plan.md",
        title=title,
        content_hash=content_hash,
        goal=goal,
        task_titles=task_titles,
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
    base = {"work_plan.md": b"# T\n", "work_plan_task_1_core.md": b"task one\n"}
    h_base = plan_folder_hash(base)
    assert len(h_base) == 64

    # Adding and editing diagnostic files must NOT change the hash.
    h_added = plan_folder_hash({**base, "questions.md": b"1. what?\n"})
    h_edited = plan_folder_hash(
        {**base, "failure.md": b"boom\n", "questions.md": b"1. what? (edited)\n"}
    )
    assert h_base == h_added == h_edited

    # Any change to a non-diagnostic file DOES change the hash.
    assert plan_folder_hash({**base, "work_plan.md": b"# T2\n"}) != h_base
    assert plan_folder_hash({**base, "new_task.md": b"x\n"}) != h_base

    # Deterministic across dict orderings.
    reversed_ = dict(reversed(list(base.items())))
    assert plan_folder_hash(reversed_) == h_base

    # A diagnostics-only folder hashes to the empty string's digest.
    assert (
        plan_folder_hash({"questions.md": b"q\n", "failure.md": b"f\n"})
        == hashlib.sha256(b"").hexdigest()
    )
    # The diagnostic set is exactly the two workflow-written files.
    assert DIAGNOSTIC_FILES == frozenset({"questions.md", "failure.md"})


def test_plan_folder_hash_binary_bytes_are_byte_stable() -> None:
    """Binary bytes hash byte-stably: raw bytes (no decode, no rstrip), NUL-separated
    sorted pairs — the T6d regression for plan folders with binary assets."""
    wp = b"# A\n"
    blob = b"\xcb\x0d\x00\x00\x00\x00\x00\x00\x00"
    contents = {"work_plan.md": wp, "data/blob.bin": blob}

    # The expected digest from the documented formula: sorted (relpath, bytes) pairs,
    # each contributing relpath.utf8 + NUL + raw bytes + NUL (no diagnostics here).
    # "data/blob.bin" sorts before "work_plan.md", so its contribution is first.
    expected = hashlib.sha256(
        b"data/blob.bin" + b"\0" + blob + b"\0" + b"work_plan.md" + b"\0" + wp + b"\0"
    ).hexdigest()

    h = plan_folder_hash(contents)
    assert h == expected
    assert len(h) == 64
    int(h, 16)  # 64-char hex

    # Byte-stable: identical bytes in any dict ordering → identical digest.
    assert plan_folder_hash(dict(reversed(list(contents.items())))) == h
    # The binary entry contributes: the combined folder ≠ the text-only folder.
    assert h != plan_folder_hash({"work_plan.md": wp})


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


def test_extract_goal_inline_markers() -> None:
    """Inline **Purpose:** / **Goal:** markers: the line's remainder is the goal."""
    assert extract_goal("**Purpose:** Build the DMP.\n") == "Build the DMP."
    # Leading whitespace + a ``Goal`` marker also match; a marker line mid-text wins.
    assert extract_goal("  **Purpose:**   Padded marker\n") == "Padded marker"
    assert extract_goal("intro\n**Goal:**  Ship it\n\nrest\n") == "Ship it"


def test_extract_goal_wrapped_inline_and_sections() -> None:
    """Wrapped inline goals join with single spaces; section goals take the first paragraph."""
    wrapped = (
        "**Purpose:** Build `projects/ORBIT/DMP/ORBIT_DMP_v0.md`, the\n"
        "table-first consortium DMP, in five sequential sub-agent tasks.\n"
        "\n"
        "## Tasks\n"
    )
    assert extract_goal(wrapped) == (
        "Build `projects/ORBIT/DMP/ORBIT_DMP_v0.md`, the table-first consortium DMP, "
        "in five sequential sub-agent tasks."
    )
    # A line starting with # (of its own) ends the inline goal.
    assert extract_goal("**Purpose:** First part\nsecond part\n# A heading\nthird part\n") == (
        "First part second part"
    )
    # ## Purpose section: the FIRST paragraph (the blank after the heading is skipped;
    # the second paragraph is not the goal).
    section = (
        "## Purpose\n"
        "\n"
        "Build the ORBIT DMP in five\n"
        "sequential tasks, table-first.\n"
        "\n"
        "Second paragraph is not the goal.\n"
        "\n"
        "## Tasks\n"
    )
    assert extract_goal(section) == "Build the ORBIT DMP in five sequential tasks, table-first."
    # ## Goal section without a blank line after the heading; a ## heading ends it.
    assert extract_goal("## Goal\nOne line goal.\n## Next\n") == "One line goal."


def test_extract_goal_fallback_and_adversarial() -> None:
    """No marker (or an empty one) → '—'; a # heading INSIDE the goal line is kept."""
    assert extract_goal("no marker here\n## Tasks\n") == "—"
    assert extract_goal("") == "—"
    assert extract_goal("**Purpose:**\n") == "—"  # marker, empty remainder, no continuation
    # A '## E-mail lists' mention INSIDE the goal line must not truncate it.
    assert (
        extract_goal("**Purpose:** Relocate the lists (see ## E-mail lists for the format).\n")
        == "Relocate the lists (see ## E-mail lists for the format)."
    )


def test_extract_task_titles_heading_order_and_duplicates() -> None:
    """Tier-1 headings: original numbering kept (3b/5c), first per label, sorted."""
    text = (
        "### Task 2: Master table\n"
        "### Task 1: Skeleton & front matter\n"
        "### Task 3b: Sub part\n"
        "### Task 1: Duplicate kept-first\n"
        "### Task 5c: QA pass\n"
        "### Task 3: Supporting tables\n"
    )
    assert extract_task_titles(text) == (
        ("1", "Skeleton & front matter"),
        ("2", "Master table"),
        ("3", "Supporting tables"),
        ("3b", "Sub part"),
        ("5c", "QA pass"),
    )


def test_extract_task_titles_ref_tail_cuts() -> None:
    """Tier-1 ref tails cut at the FIRST connector for all four observed forms."""
    text = (
        "### Task 1: Skeleton & front matter → `work_plan_task_1_skeleton.md` "
        "(single task, @lightweight-dev)\n"
        "### Task 2: Master table 1 — see `work_plan_task_2_master.md`\n"
        "### Task 3: Supporting tables 2–6 — `work_plan_task_3_support.md`\n"
        "### Task 4: Baseline → `lightweight-dev_task_4_baseline.md`\n"
    )
    assert extract_task_titles(text) == (
        ("1", "Skeleton & front matter"),  # the (single task, …) paren after the ref is cut
        ("2", "Master table 1"),  # — see `…`
        ("3", "Supporting tables 2–6"),  # — `…` (the en dash in 2–6 is NOT the cut point)
        ("4", "Baseline"),  # lightweight-dev_task_*.md refs cut too
    )


def test_extract_task_titles_internal_arrow_and_non_task_headings() -> None:
    """An internal → that does NOT lead to a .md ref never cuts; non-task headings skip."""
    text = (
        '### Task 4: Minimal prose + Coera/IP text (user 19/11: "…"; text → speaker notes)\n'
        "### Task 5: Build X text → speaker notes → `work_plan_task_5_notes.md`\n"
        "### Tasks 8–9 (remaining drawings + deck integration): CANCELLED\n"
        "### Bag-reader format support (RESOLVED by Task 2, 2026-10-19, rosbags 0.11.8)\n"
        "## Tasks\n"
        "## Task sequence (h2, not a task)\n"
        "## Task Index (h2, not a task)\n"
    )
    assert extract_task_titles(text) == (
        # The internal arrow tail is part of the title (no .md ref after it).
        ("4", 'Minimal prose + Coera/IP text (user 19/11: "…"; text → speaker notes)'),
        # Cut at the FIRST connector that leads to a .md ref (the second arrow).
        ("5", "Build X text → speaker notes"),
    )


def test_extract_task_titles_table_tier() -> None:
    """Tier-2 tables: all three observed cell shapes, several tables, no-num rows skip."""
    text = (
        "## Tasks\n"
        "\n"
        "| Task | File | dispatch |\n"
        "|------|------|----------|\n"
        "| 1 — relocate e-mail lists | work_plan_task_1_relocate_email_lists.md | single task |\n"
        "| 2 | work_plan_task_2_remove_open_source.md | single task |\n"
        "\n"
        "## Revision 2\n"
        "\n"
        "| # | Task | dispatch |\n"
        "|---|------|----------|\n"
        "| 3 | work_plan_task_3_tikz_scenario_b.md — TikZ schematic of 2027 "
        "Scenario B, render PDF + PNG, visual check | @lightweight-dev |\n"
        "| 4 | | single task |\n"  # no file anywhere in the row → skipped
    )
    assert extract_task_titles(text) == (
        ("1", "relocate e-mail lists"),  # '1 — <title>' in the Task column
        ("2", "remove open source"),  # bare '1' + File-column derivation (underscores → spaces)
        # '#'-column number + file.md — <title> tail (em-dash separated)
        ("3", "TikZ schematic of 2027 Scenario B, render PDF + PNG, visual check"),
    )
    # A non-task table (no task/# header cell) yields nothing.
    assert extract_task_titles("| Name | Value |\n|------|-------|\n| 1 — foo | bar |\n") == ()


def test_extract_task_titles_file_name_tier_and_empty() -> None:
    """Tier-3 file names (basenames AND folder-relative), numeric sort 2, 10; empty → ()."""
    names = [
        "work_plan.md",
        "work_plan_task_10_last_pass.md",
        "work_plan_task_2_skeleton.md",
        "sub/work_plan_task_3_fig.md",  # folder-relative path (basename-anchored match)
        "notes.md",
    ]
    expected = (("2", "skeleton"), ("3", "fig"), ("10", "last pass"))  # 10 sorts AFTER 2
    assert extract_task_titles("no task headings here\n", names) == expected
    # The same names as plain basenames (what discover_plans may pass) give the same.
    assert extract_task_titles("", [Path(n).name for n in names]) == expected
    # Tiers 1–2 win over tier 3 (heading tasks are kept, file names ignored).
    assert extract_task_titles("### Task 1: Only heading\n", names) == (("1", "Only heading"),)
    # Empty input → ().
    assert extract_task_titles("") == ()
    assert extract_task_titles("", []) == ()


# --- task_done_labels (report-file existence → completion labels) ------------- #


def test_task_done_labels_matches_report_spellings() -> None:
    """Underscore + hyphen spellings and folder-relative paths all yield their label."""
    assert task_done_labels(["lightweight_dev_task_1_engine_scaffold.md"]) == frozenset({"1"})
    assert task_done_labels(["lightweight-dev_task_3b_fix_ci.md"]) == frozenset({"3b"})
    # Folder-relative path (basename-anchored match, like _TASK_FILE_NAME_RE).
    assert task_done_labels(["sub/lightweight_dev_task_2_runner.md"]) == frozenset({"2"})


def test_task_done_labels_mixed_folder() -> None:
    """A mixed folder yields EXACTLY the reported labels; specs and notes are ignored."""
    names = [
        "work_plan.md",
        "work_plan_task_1_engine_scaffold.md",
        "work_plan_task_2_runner.md",
        "work_plan_task_3_docs.md",
        "work_plan_task_4_check.md",
        "work_plan_task_5_final.md",
        "lightweight_dev_task_1_engine_scaffold.md",
        "lightweight_dev_task_2_runner.md",
        "lightweight-dev_task_5_final.md",
        "questions.md",
    ]
    assert task_done_labels(names) == frozenset({"1", "2", "5"})


def test_task_done_labels_non_matches_and_empty() -> None:
    """Specs, missing desc segment, foreign prefixes, plurals and wrong case never match."""
    for name in (
        "work_plan_task_1_x.md",
        "lightweight_dev_task_1.md",  # no `_<desc>_` segment
        "not-lightweight_dev_task_2_x.md",  # basename anchor rejects the prefix
        "lightweight_dev_tasks_1_x.md",  # plural
        "Lightweight_Dev_Task_1_x.md",  # case-sensitive
    ):
        assert task_done_labels([name]) == frozenset()
    # Empty / None-ish input → frozenset().
    assert task_done_labels([]) == frozenset()
    assert task_done_labels(()) == frozenset()
    assert task_done_labels(None) == frozenset()  # type: ignore[arg-type]


def test_discover_plans_filters_sorts_and_stamps() -> None:
    """discover_plans keeps valid planning/ folders, drops malformed/archived, sorts by dir."""
    entries = [
        PlanEntry(
            dir="planning/zeta", work_plan_text="# Z\n", file_contents={"work_plan.md": b"# Z\n"}
        ),
        PlanEntry(dir="planning/alpha", work_plan_text=None, file_contents={}),  # malformed
        PlanEntry(  # archived (an 'archived' path segment) → dropped
            dir=f"planning/{ARCHIVED_SEGMENT}/orbit", work_plan_text="# A\n", file_contents={}
        ),
        PlanEntry(
            dir="docs/plans/orbit", work_plan_text="# D\n", file_contents={}
        ),  # not under planning/
        PlanEntry(
            dir="planning/alpha2",
            work_plan_text="# Alpha\n",
            file_contents={"work_plan.md": b"# Alpha\n", "questions.md": b"stale\n"},
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
    assert alpha.content_hash == plan_folder_hash({"work_plan.md": b"# Alpha\n"})
    assert alpha.identity == plan_identity("o/r", "main", alpha.path, alpha.content_hash)


def test_discover_plans_stamps_goal_and_tasks() -> None:
    """discover_plans stamps each Plan with extract_goal + extract_task_titles."""
    wp = (
        "# Orbit DMP v0\n"
        "\n"
        "**Purpose:** Build `projects/ORBIT/DMP/ORBIT_DMP_v0.md`, the table-first "
        "consortium DMP.\n"
        "\n"
        "## Tasks\n"
        "\n"
        "### Task 1: Skeleton & front matter\n"
        "\n"
        "### Task 2: Master table 1\n"
    )
    entry = PlanEntry(
        dir="planning/orbit-dmp",
        work_plan_text=wp,
        file_contents={
            "work_plan.md": wp.encode("utf-8"),
            "work_plan_task_1_skeleton.md": b"# Skeleton\n",
            "work_plan_task_2_master.md": b"# Master\n",
        },
    )
    plans = discover_plans("o/r", "main", [entry])
    assert len(plans) == 1
    plan = plans[0]
    assert plan.goal == (
        "Build `projects/ORBIT/DMP/ORBIT_DMP_v0.md`, the table-first consortium DMP."
    )
    # Tier-1 headings win over the tier-3 task files in file_contents.
    assert plan.task_titles == (("1", "Skeleton & front matter"), ("2", "Master table 1"))
    # Identity is unchanged by the new fields (repo/branch/path/hash only).
    assert plan.identity == plan_identity("o/r", "main", plan.path, plan.content_hash)


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
    """The contract sample parses to exact rows and renders back byte-identically.

    The rendered form now carries the workflow-owned per-plan section — the plan's
    ``###`` heading plus its OWN header/separator/data-row table — and no details
    table here, because the parsed rows carry no goal/tasks.
    """
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
    # Byte-identical round-trip (incl. the trailing newline): each plan renders as its
    # own section (### heading + its own header/separator/data-row table); the blank
    # line after a section separates it from the next heading.
    expected = (
        "# https://github.com/y2d2/ARP_MPE.git\n"
        "## main\n"
        "### planning/orbit-sim/work_plan.md\n"
        "| approval | priority | plan | title | state | remove |\n"
        "|----------|----------|------|-------|-------|--------|\n"
        "| ☐ | 1 | planning/orbit-sim/work_plan.md | ORBIT sim extension | open | ☐ |\n"
        "\n"
        "## dev\n"
        "### planning/unitest/work_plan.md\n"
        "| approval | priority | plan | title | state | remove |\n"
        "|----------|----------|------|-------|-------|--------|\n"
        "| ☑ | 2 | planning/unitest/work_plan.md | Unit tests | review | ☐ |\n"
    )
    assert render_listing(rows) == expected
    # ...and the pre-sections sample still parses to the SAME data rows.
    assert parse_listing(expected) == rows


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
    # None of these rows carries goal/tasks, so NO plan gets a details table; the blank
    # line after each section separates it from the next heading.
    out = render_listing([r1, r2, r3])
    assert out == (
        "# https://github.com/o/r.git\n"
        "## main\n"
        "### planning/a/work_plan.md\n"
        "| approval | priority | plan | title | state | remove |\n"
        "|----------|----------|------|-------|-------|--------|\n"
        "| ☑ | 2 | planning/a/work_plan.md | A | open | ☐ |\n"
        "\n"
        "## dev\n"
        "### planning/b/work_plan.md\n"
        "| approval | priority | plan | title | state | remove |\n"
        "|----------|----------|------|-------|-------|--------|\n"
        "| ☐ | 1 | planning/b/work_plan.md | B | success | ☑ |\n"
        "\n"
        "# https://github.com/o/s.git\n"
        "## main\n"
        "### planning/c/work_plan.md\n"
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


def test_parse_listing_skips_per_plan_sections() -> None:
    """Rendered per-plan sections (heading + own table + details table) parse to EXACTLY
    the data rows.

    Adversarial details text — pipes in goal/tasks, the ☑ glyph, the words 'approval'
    and 'open', digits, and the literal word 'details' in the details cell — still
    yields zero extra rows: the ``###`` heading is not a ``|``-row and every
    details-table line is one cell (escaped pipes may split the content line, never
    into the six cells of a data row). OLD-format detail rows appended below keep being
    skipped too (their em-dash priority cell fails ``int()``).
    """
    rows = [
        ListingRow(
            "https://github.com/o/r.git",
            "main",
            False,
            1,
            "planning/a/work_plan.md",
            "A",
            "open",
            False,
            goal="Has | pipes ☑ approval open words 12345",
            task_titles=(("1", "Pipe | task ☑ approval open"),),
        ),
        ListingRow(
            "https://github.com/o/r.git",
            "main",
            False,
            2,
            "planning/b/work_plan.md",
            "B",
            "review",
            False,
            goal="—",  # the no-goal sentinel → renders **Goal:** —
            task_titles=(("1", "42 digits 3b"), ("2", "the word details | itself")),
        ),
        ListingRow(
            "https://github.com/o/r.git",
            "main",
            False,
            3,
            "planning/c/work_plan.md",
            "C",
            "success",
            True,
        ),  # defaults (no goal, no tasks) → NO details table at all
    ]
    md = render_listing(rows)
    # A live listing may still carry the PREVIOUS format's detail rows (the renderer
    # dropped them; the parser must keep skipping them): the 7-cell one fails the cell
    # count, the 6-cell one the em-dash priority's int().
    md += (
        "| — | — | **Goal:** legacy | pipes ☑ approval open 12345 | **Tasks:** — | — | — |\n"
        "| — | — | **Goal:** — | **Tasks:** — | — | — |\n"
    )

    parsed = parse_listing(md)
    assert [r.plan for r in parsed] == [  # exactly the data rows — zero extra rows
        "planning/a/work_plan.md",
        "planning/b/work_plan.md",
        "planning/c/work_plan.md",
    ]
    assert [r.priority for r in parsed] == [1, 2, 3]
    # Parsed rows carry no goal/tasks (details tables never parse as rows).
    assert all(r.goal == "" and r.task_titles == () for r in parsed)
    # The user cells of the adversarial goal/tasks never leak into the parsed rows.
    assert [r.title for r in parsed] == ["A", "B", "C"]
    # Row c really renders NO details table; rows a and b do.
    assert md.count("| details |") == 2


def test_render_listing_emits_per_plan_sections() -> None:
    """render_listing: exact per-plan-section bytes (details present, details skipped
    when goal AND tasks are empty, one-sided parts, escaped pipes)."""
    with_goal_tasks = ListingRow(
        "https://github.com/o/r.git",
        "main",
        False,
        1,
        "planning/orbit-dmp/work_plan.md",
        "ORBIT DMP v0",
        "open",
        False,
        goal="Build the DMP, table-first.",
        task_titles=(("1", "Skeleton & front matter"), ("2", "Master table 1")),
    )
    default = ListingRow(
        "https://github.com/o/r.git",
        "main",
        True,
        2,
        "planning/unitest/work_plan.md",
        "Unit tests",
        "review",
        False,
    )
    md = render_listing([with_goal_tasks, default])
    assert md == (
        "# https://github.com/o/r.git\n"
        "## main\n"
        "### planning/orbit-dmp/work_plan.md\n"
        "| approval | priority | plan | title | state | remove |\n"
        "|----------|----------|------|-------|-------|--------|\n"
        "| ☐ | 1 | planning/orbit-dmp/work_plan.md | ORBIT DMP v0 | open | ☐ |\n"
        "\n"
        "| details |\n"
        "|---------|\n"
        "| **Goal:** Build the DMP, table-first.<br>**Tasks:**<br>"
        "1 Skeleton & front matter<br>2 Master table 1 |\n"
        "\n"
        "### planning/unitest/work_plan.md\n"
        "| approval | priority | plan | title | state | remove |\n"
        "|----------|----------|------|-------|-------|--------|\n"
        "| ☑ | 2 | planning/unitest/work_plan.md | Unit tests | review | ☐ |\n"
    )
    # Goal only → '<br>**Tasks:** —' directly after the goal part; tasks only (empty
    # goal) → '**Goal:** —'.
    goal_only = ListingRow(
        "https://github.com/o/r.git",
        "main",
        False,
        1,
        "planning/g/work_plan.md",
        "G",
        "open",
        False,
        goal="G only",
    )
    tasks_only = ListingRow(
        "https://github.com/o/r.git",
        "main",
        False,
        2,
        "planning/t/work_plan.md",
        "T",
        "open",
        False,
        task_titles=(("3b", "Sub"),),
    )
    md_side = render_listing([goal_only, tasks_only])
    assert "| **Goal:** G only<br>**Tasks:** — |" in md_side
    assert "| **Goal:** —<br>**Tasks:**<br>3b Sub |" in md_side
    # Pipes in goal/task text are escaped (a raw pipe would break the table).
    pipe_row = ListingRow(
        "https://github.com/o/r.git",
        "main",
        False,
        1,
        "planning/p/work_plan.md",
        "P",
        "open",
        False,
        goal="a | b",
        task_titles=(("1", "x | y"),),
    )
    md2 = render_listing([pipe_row])
    assert "**Goal:** a \\| b" in md2
    assert "<br>1 x \\| y" in md2
    # Byte-stable across calls; single trailing newline; no trailing spaces.
    assert render_listing([with_goal_tasks, default]) == md
    assert md.endswith("\n") and not md.endswith("\n\n")
    assert all(line == line.rstrip() for line in md.splitlines())


def test_render_listing_pipes_round_trip_to_exact_data_rows() -> None:
    """Goal/tasks with raw pipes: the details cell carries escaped ``\\|`` only AND
    ``parse_listing(render_listing(rows))`` still returns exactly the data rows."""
    rows = [
        ListingRow(
            "https://github.com/o/r.git",
            "main",
            False,
            1,
            "planning/p/work_plan.md",
            "P",
            "open",
            False,
            goal="a | b",
            task_titles=(("1", "x | y"),),
        ),
        ListingRow(
            "https://github.com/o/r.git",
            "main",
            False,
            2,
            "planning/q/work_plan.md",
            "Q",
            "open",
            False,
            goal="| leading and trailing |",
            task_titles=(("2", "p | q | r"), ("3", "plain")),
        ),
    ]
    md = render_listing(rows)
    assert "**Goal:** a \\| b" in md and "<br>1 x \\| y" in md
    assert "**Goal:** \\| leading and trailing \\|" in md and "<br>2 p \\| q \\| r" in md
    assert "| **Goal:** a | b" not in md  # never an UNESCAPED pipe in the details cell
    parsed = parse_listing(md)
    assert [(r.plan, r.priority, r.title) for r in parsed] == [
        ("planning/p/work_plan.md", 1, "P"),
        ("planning/q/work_plan.md", 2, "Q"),
    ]
    assert all(r.goal == "" and r.task_titles == () for r in parsed)


def test_listing_pipeline_fixed_point() -> None:
    """Steady-state no-push invariant with the per-plan sections: render is a fixed point.

    ``render(reconcile(plans, parse(render(reconcile(plans, []))), st1)) == file0``:
    the parse skips the section artifacts (headings, details tables), the reconcile
    re-stamps the goal/tasks from the same scan, and the render is byte-identical
    (state doc value-equal, no actions logged).
    """
    plans = [
        _plan(
            folder="planning/orbit-dmp",
            title="ORBIT DMP v0",
            goal="Build the consortium DMP, table-first.",
            task_titles=(("1", "Skeleton & front matter"), ("2", "Master table 1")),
        ),
        _plan(folder="planning/unitest", title="Unit tests"),
    ]
    st0 = fresh_state()
    rows0, st1, log0 = reconcile(plans, [], st0, now=NOW)
    assert len(log0) == 2  # both plans discovered
    file0 = render_listing(rows0)

    rows1, st2, log1 = reconcile(plans, parse_listing(file0), st1, now=NOW)
    file1 = render_listing(rows1)

    assert file1 == file0  # byte-stable fixed point (the steady-state no-push invariant)
    assert rows1 == rows0  # re-stamped rows are value-equal to the first pass
    assert st2 == st1  # state doc unchanged in the steady state
    assert log1 == []  # no actions in the steady state
    # Every plan is its own section: the ``### <plan>`` heading, then its OWN header +
    # separator + data row. Scan order (path-sorted): orbit-dmp first, unitest second.
    lines = file0.splitlines()
    heads = [i for i, line in enumerate(lines) if line.startswith("### ")]
    assert [lines[i] for i in heads] == [
        "### planning/orbit-dmp/work_plan.md",
        "### planning/unitest/work_plan.md",
    ]
    for i, priority in zip(heads, (1, 2), strict=True):
        assert lines[i + 1] == "| approval | priority | plan | title | state | remove |"
        assert lines[i + 2] == "|----------|----------|------|-------|-------|--------|"
        assert lines[i + 3].startswith(f"| ☐ | {priority} | ")
        assert lines[i + 3].endswith(" | open | ☐ |")
    # The stamped plan's details table follows its data row after exactly one blank
    # line, one task per <br> line; the plan with NEITHER goal nor tasks has NO
    # details table at all.
    assert lines[heads[0] + 4] == ""
    assert lines[heads[0] + 5 : heads[0] + 8] == [
        "| details |",
        "|---------|",
        "| **Goal:** Build the consortium DMP, table-first.<br>**Tasks:**<br>"
        "1 Skeleton & front matter<br>2 Master table 1 |",
    ]
    assert heads[1] == heads[0] + 9  # exactly one blank line between the two blocks
    assert lines[heads[1] + 3] == (
        "| ☐ | 2 | planning/unitest/work_plan.md | Unit tests | open | ☐ |"
    )
    assert "| details |" not in lines[heads[1] :]


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

    # Empty listing → priority 1; state entry created; discovery logged. The emitted
    # row carries the details-table fields stamped from the scanned Plan (defaults here —
    # the fixture plan carries no goal/tasks).
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
            goal=plan.goal,
            task_titles=plan.task_titles,
        )
    ]
    assert doc["plans"][plan.identity]["state"] == "open"
    assert doc["plans"][plan.identity]["attempt"] == 0
    assert f"discovered {plan.identity} (y2d2/ARP_MPE @ main)" in log

    # A plan with known goal/tasks → the output row is stamped with them.
    known = _plan(
        folder="planning/known",
        title="Known plan",
        goal="The known goal.",
        task_titles=(("1", "One"), ("2", "Two")),
    )
    rows_known, _, _ = reconcile([known], [], fresh_state(), now=NOW)
    assert rows_known[0].goal == "The known goal."
    assert rows_known[0].task_titles == (("1", "One"), ("2", "Two"))

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
        local_listing=None,  # mirror is covered by its own section-G tests
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


def test_repo_url_default_is_ssh_colon_form(base_config: Config) -> None:
    """_repo_url fallback (no repo_urls override) is the byte-exact SSH URL — colon, not slash."""
    settings = _roadmap_config(base_config, ["y2d2/ARP_MPE"]).roadmap_prompts
    wf = RoadmapDevWorkflow(settings)
    assert wf._repo_url("y2d2/ARP_MPE") == "git@github.com:y2d2/ARP_MPE.git"


def test_prompts_repo_url_default_is_ssh_colon_form(base_config: Config) -> None:
    """_prompts_repo_url fallback (no listing_repo_url) is the byte-exact SSH URL — colon."""
    settings = dataclasses.replace(
        _roadmap_config(base_config, []).roadmap_prompts,
        listing_repo="y2d2/agentic_scripts",  # this repo is the listing repo (local delta)
    )
    wf = RoadmapDevWorkflow(settings)
    assert wf._prompts_repo_url() == "git@github.com:y2d2/agentic_scripts.git"


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
