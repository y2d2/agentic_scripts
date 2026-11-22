"""Hermetic integration tests for the roadmap-dev Phase-1 pipeline (Task 3).

Fixture world: local bare remotes play GitHub (one per allowed repo + one for the
listing repo); a work repo is pushed to each bare, and :meth:`RoadmapDevWorkflow.run`
is driven directly (NOT via ``scheduler.run``) with a REAL :class:`Git` helper, a real
:class:`StateStore` over a throwaway workspace, and an injected fixed clock. NO network,
no real ``opencode``, no ``GITHUB_PAT``. Git identity is set per test (autouse fixture)
and restored afterwards.

Acceptance coverage: [AC1] first-run discovery + listing push; [AC2] steady-state no-op;
[AC3] user-cell preservation; [AC4] success + remove ☑ round-trip + drain-stub bound;
[AC5] run-start reaper; [AC6] repo removed from the allowlist; [AC7] unreachable repo;
[AC8a/b] listing push race (retry) and retry exhaustion.
"""

from __future__ import annotations

import dataclasses
import logging
import subprocess
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest

from agentic_scripts.config import Config, RoadmapPrompts
from agentic_scripts.git import Git, GitError
from agentic_scripts.state import StateStore
from agentic_scripts.workflows.base import WorkContext
from agentic_scripts.workflows.roadmap_dev import RoadmapDevWorkflow

# The injected clock (UTC) — the pipeline never calls datetime.now() itself.
NOW = datetime(2026, 11, 21, 12, 0, tzinfo=UTC)

# --- Fixture constants ------------------------------------------------------- #
FIXTURE_REPO = "owner/fixture"
FIXTURE_SLUG = "owner__fixture"
OTHER_REPO = "owner/other"
PROMPTS_REPO = "owner/prompts"
LISTING_PATH = "plans.md"
LISTING_BRANCH = "main"

ORBIT_PLAN = "# ORBIT sim extension\n\nExtend the ORBIT simulation pipeline.\n"
UNITEST_PLAN = "# Unit tests\n\nAdd unit tests for the core modules.\n"
DONE_PLAN = "# Done plan\n\nAlready archived; must never be discovered.\n"
BROKEN_README = "# broken folder\n\nThis folder has no work_plan.md (malformed).\n"
IGNORED_PLAN = "# Ignored plan\n\nOn a roadmap-dev/* branch; must never be discovered.\n"

LISTING_HEADER = "| approval | priority | plan | title | state | remove |"
LISTING_SEP = "|----------|----------|------|-------|-------|--------|"
ROW_UNITEST = "| ☐ | 1 | planning/unitest/work_plan.md | Unit tests | open | ☐ |"
ROW_ORBIT = "| ☐ | 1 | planning/orbit-sim/work_plan.md | ORBIT sim extension | open | ☐ |"
ROW_NETFIT = "| ☐ | 1 | planning/netfit/work_plan.md | Netfit | open | ☐ |"
# NOTE: no trailing newline — :meth:`Git.show_file` (used by ``_remote_listing``) rstrips
# the file's trailing newline(s); the file on the remote carries exactly one (the renderer
# emits one).
EXPECTED_RUN1 = (
    f"# https://github.com/{FIXTURE_REPO}.git\n"
    "## dev\n"
    f"{LISTING_HEADER}\n{LISTING_SEP}\n{ROW_UNITEST}\n"
    "## main\n"
    f"{LISTING_HEADER}\n{LISTING_SEP}\n{ROW_ORBIT}"
)

QUIET = logging.getLogger("test.roadmap_dev_scan")
QUIET.setLevel(logging.CRITICAL)  # quiet: the workflow logs at INFO/WARNING/ERROR


@pytest.fixture(autouse=True)
def _git_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set the git identity env vars for every git subprocess this test spawns.

    Purpose:
        Local bare-repo commits need an author/committer identity; monkeypatch sets the
        four vars deterministically (even over a real environment) and restores them
        after the test.
    """
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Test Author")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "author@example.test")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "Test Committer")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "committer@example.test")


# --- Raw git + fixture builders ---------------------------------------------- #


def _git(path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run a raw git command in ``path`` (test setup helper)."""
    return subprocess.run(
        ["git", "-C", str(path), *args], capture_output=True, text=True, check=True
    )


def _write(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` (creating parents)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _commit(src: Path, message: str) -> None:
    """Stage everything in ``src`` and commit with ``message``."""
    _git(src, "add", "-A")
    _git(src, "commit", "-m", message)


def _push_bare(src: Path, bare: Path, branches: tuple[str, ...] = ("main",)) -> Path:
    """Create a bare remote at ``bare`` and push ``branches`` from ``src`` into it."""
    bare.mkdir(parents=True, exist_ok=True)
    _git(bare, "init", "--bare")
    _git(bare, "symbolic-ref", "HEAD", "refs/heads/main")
    _git(src, "remote", "add", "origin", str(bare))
    for branch in branches:
        _git(src, "push", "-u", "origin", branch)
    return bare


def _make_fixture_remote(tmp_path: Path) -> Path:
    """Build the ``owner/fixture`` repo and push it to a bare remote.

    Purpose:
        The AC1 fixture: ``main`` carries ``planning/orbit-sim/`` (``work_plan.md`` + a
        task file); ``dev`` (cut from the marker-free base) carries
        ``planning/unitest/``; BOTH branches also carry an archived plan
        (``planning/archived/done/``) and a malformed folder (``planning/broken/`` with
        no ``work_plan.md``); an attempt branch ``roadmap-dev/abcdef123456-1`` carries a
        plan that the scan must skip. Exactly two plans are discoverable.

    Args:
        tmp_path: The pytest temp dir (sources + bare live under it).

    Returns:
        The bare remote path (the clone URL in the config).
    """
    src = tmp_path / "fixture-src"
    src.mkdir()
    _git(src, "init", "-b", "main")
    _write(src / "README.md", "# fixture\n")
    _commit(src, "base")

    # dev branches off the marker-free base (its own plan set only).
    _git(src, "checkout", "-b", "dev")
    _write(src / "planning/unitest/work_plan.md", UNITEST_PLAN)
    _write(src / "planning/archived/done/work_plan.md", DONE_PLAN)
    _write(src / "planning/broken/README.md", BROKEN_README)
    _commit(src, "add dev plans")

    # main: orbit-sim plan (+ task file), archived plan, malformed folder.
    _git(src, "checkout", "main")
    _write(src / "planning/orbit-sim/work_plan.md", ORBIT_PLAN)
    _write(src / "planning/orbit-sim/work_plan_task_1_x.md", "# Task 1\n\nExtend ORBIT.\n")
    _write(src / "planning/archived/done/work_plan.md", DONE_PLAN)
    _write(src / "planning/broken/README.md", BROKEN_README)
    _commit(src, "add main plans")

    # An attempt branch with a plan — the scan must skip it.
    _git(src, "checkout", "-b", "roadmap-dev/abcdef123456-1")
    _write(src / "planning/ignored/work_plan.md", IGNORED_PLAN)
    _commit(src, "attempt branch plan (must be skipped)")
    _git(src, "checkout", "main")

    return _push_bare(src, tmp_path / "fixture.git", ("main", "dev", "roadmap-dev/abcdef123456-1"))


def _make_simple_remote(tmp_path: Path) -> Path:
    """Build the ``owner/other`` repo (one plan on main) and push it to a bare remote."""
    src = tmp_path / "other-src"
    src.mkdir()
    _git(src, "init", "-b", "main")
    _write(src / "README.md", "# other\n")
    _commit(src, "base")
    _write(src / "planning/netfit/work_plan.md", "# Netfit\n\nTune the network model.\n")
    _commit(src, "add plan")
    return _push_bare(src, tmp_path / "other.git")


def _make_prompts_remote(tmp_path: Path, listing: str = "") -> Path:
    """Build the ``owner/prompts`` listing repo (``main`` with ``plans.md``) as a bare.

    Args:
        tmp_path: The pytest temp dir.
        listing: The initial ``plans.md`` text ("" = empty file, the AC1 first-run case).

    Returns:
        The bare remote path (the ``listing_repo_url`` in the config).
    """
    src = tmp_path / "prompts-src"
    src.mkdir()
    _git(src, "init", "-b", "main")
    _write(src / LISTING_PATH, listing)
    _commit(src, "initial plans.md")
    return _push_bare(src, tmp_path / "prompts.git")


# --- Remote inspection + user-edit helpers ------------------------------------ #


def _remote_listing(bare: Path) -> str:
    """Return the remote's ``plans.md`` on ``main`` (trailing newlines stripped)."""
    return Git().show_file(bare, LISTING_BRANCH, LISTING_PATH)


def _remote_log(bare: Path) -> list[str]:
    """Return the remote's ``main`` commit subjects, newest first."""
    return [
        line
        for line in _git(bare, "log", "--format=%s", LISTING_BRANCH).stdout.splitlines()
        if line.strip()
    ]


def _user_edit_listing(
    bare: Path, tmp_path: Path, label: str, transform: Callable[[str], str]
) -> None:
    """Hand-commit a user edit of the remote listing (fresh clone → edit → push).

    Purpose:
        Simulate the operator editing ``plans.md`` between runs: clone the bare, apply
        ``transform`` to the current listing text (no trailing newline), commit with
        ``label`` (an ``OC:``-free message, so workflow commits stay recognizable), and
        push. The edit is on top of the remote tip → the next workflow run's first push
        is a genuine non-fast-forward unless the reconcile output matches exactly.

    Args:
        bare: The listing repo's bare remote.
        tmp_path: The pytest temp dir (the scratch clone lives under it).
        label: The user's commit message.
        transform: Listing text → edited listing text.
    """
    scratch = tmp_path / f"user-edit-{label}"
    Git().clone(str(bare), scratch)
    md = Git().show_file(scratch, f"origin/{LISTING_BRANCH}", LISTING_PATH)
    _write(scratch / LISTING_PATH, transform(md) + "\n")
    Git().add(scratch)
    assert Git().commit(scratch, label) is True
    Git().push(scratch, LISTING_BRANCH)


# --- Git fakes ---------------------------------------------------------------- #


class PushCountingGit(Git):
    """A :class:`Git` that counts :meth:`push` calls (to prove a retry happened).

    Attributes:
        push_calls: Number of :meth:`push` calls delegated to the real git.
    """

    def __init__(self) -> None:
        self.push_calls = 0

    def push(
        self, path: Path, branch: str, *, remote: str = "origin", upstream: bool = False
    ) -> None:
        """Count the call, then delegate to the real :meth:`Git.push`."""
        self.push_calls += 1
        super().push(path, branch, remote=remote, upstream=upstream)


class FailingPushGit(Git):
    """A :class:`Git` whose :meth:`push` always fails (a rejected non-fast-forward).

    Purpose:
        Force the retry path to exhaust: both the first push and the retry's push raise,
        so the run records the ``listing push failed for …`` error (AC8b).
    """

    def push(
        self, path: Path, branch: str, *, remote: str = "origin", upstream: bool = False
    ) -> None:
        """Raise a canned non-fast-forward :class:`GitError` (never delegates)."""
        raise GitError(
            f"push failed (exit 1): ! [rejected] {branch} -> {branch} (non-fast-forward)"
        )


# --- Config / context / workflow builders -------------------------------------- #


def _config(
    base_config: Config,
    *,
    allowed_repos: list[str],
    repo_urls: dict[str, str],
    listing_repo_url: str,
) -> Config:
    """Point ``base_config``'s roadmap_prompts at the fixture remotes.

    Args:
        base_config: A T1-style loaded :class:`Config` (tmp paths).
        allowed_repos: The ``roadmap_prompts.allowed_repos`` list (config order).
        repo_urls: Per-repo clone-URL overrides (local bare paths — the hermetic seam).
        listing_repo_url: The listing repo's clone URL (local bare path).

    Returns:
        A new :class:`Config` with the replaced :class:`RoadmapPrompts` section.
    """
    rp = RoadmapPrompts(
        allowed_repos=list(allowed_repos),
        listing_repo=PROMPTS_REPO,
        listing_repo_url=listing_repo_url,
        listing_path=LISTING_PATH,
        listing_branch=LISTING_BRANCH,
        run_timeout_minutes=480,
        test_commands={},
        repo_urls=dict(repo_urls),
    )
    return dataclasses.replace(base_config, roadmap_prompts=rp)


def _ctx(config: Config, state_dir: Path, *, gate_open: bool = False) -> WorkContext:
    """Build a hermetic :class:`WorkContext` over the tmp workspace (quiet logger).

    Args:
        config: A loaded :class:`Config` whose paths point at the tmp workspace.
        state_dir: The state directory (``<tmp>/state``; the sandbox is ``<tmp>/sandbox``).
        gate_open: The idle-gate verdict for this fire (False → the closed-gate drain note).

    Returns:
        A fully wired :class:`WorkContext` (``run_id="test-run"``, ``admin_repo=None``).
    """
    return WorkContext(
        config=config,
        state=StateStore(state_dir),
        logger=QUIET,
        run_id="test-run",
        workflow_name="roadmap-dev",
        sandbox_dir=state_dir.parent / "sandbox",
        admin_repo=None,
        gate_open=gate_open,
    )


def _wf(config: Config, git: Git | None = None) -> RoadmapDevWorkflow:
    """Build a workflow over ``config.roadmap_prompts`` with a real (or fake) Git + fixed clock."""
    return RoadmapDevWorkflow(config.roadmap_prompts, git=git or Git(), now_fn=lambda: NOW)


def _state(ctx: WorkContext) -> dict:
    """Return the workflow's persisted state document ({} when absent)."""
    return ctx.state.load("roadmap-dev")


# --- Tests --------------------------------------------------------------------- #


def test_first_run_discovers_two_plans_and_pushes_listing(
    base_config: Config, tmp_path: Path
) -> None:
    """[AC1] Fresh world → exactly 2 plans (archived/malformed/attempt-branch excluded);
    the prompts REMOTE gets plans.md (per-branch tables, open rows, ☐ checkmarks) with the
    exact OC: commit message; state written with 2 open entries."""
    bare_a = _make_fixture_remote(tmp_path)
    bare_p = _make_prompts_remote(tmp_path)
    config = _config(
        base_config,
        allowed_repos=[FIXTURE_REPO],
        repo_urls={FIXTURE_REPO: str(bare_a)},
        listing_repo_url=str(bare_p),
    )
    ctx = _ctx(config, tmp_path / "state")

    result = _wf(config).run(ctx)

    assert result.status == "ok"
    assert result.errors == []
    assert result.items_found == 2
    # Action notes: per-repo scan note + drain stub note (gate closed here).
    assert f"scanned {FIXTURE_REPO}: 2 plan(s)" in result.actions
    assert result.actions[-1] == "drain skipped (idle gate closed)"

    # Remote listing: one repo section, a table per branch. NOTE: the T2 reconciler
    # numbers priorities per (repo_url, branch) table — an empty world gives BOTH first
    # rows priority 1 (the task plan's "1/2" phrasing mirrors the hand-set sample
    # skeleton, whose dev row priority is user-owned data, not reconciler output).
    assert _remote_listing(bare_p) == EXPECTED_RUN1

    # Exactly one new commit on the remote, with the exact OC: message.
    log = _remote_log(bare_p)
    assert log[0] == "OC: roadmap-dev: reconcile listing (run test-run)"
    assert len(log) == 2  # initial plans.md + the reconcile commit

    # State: 2 entries, both open, version 1.
    st = _state(ctx)
    assert st["version"] == 1
    assert {e["path"] for e in st["plans"].values()} == {
        "planning/orbit-sim/work_plan.md",
        "planning/unitest/work_plan.md",
    }
    assert all(e["state"] == "open" for e in st["plans"].values())


def test_second_run_no_changes_is_a_noop(base_config: Config, tmp_path: Path) -> None:
    """[AC2] Second run with no changes → NO new commit (same HEAD), byte-identical state
    file, action notes present, status ok."""
    bare_a = _make_fixture_remote(tmp_path)
    bare_p = _make_prompts_remote(tmp_path)
    config = _config(
        base_config,
        allowed_repos=[FIXTURE_REPO],
        repo_urls={FIXTURE_REPO: str(bare_a)},
        listing_repo_url=str(bare_p),
    )
    ctx = _ctx(config, tmp_path / "state")

    r1 = _wf(config).run(ctx)
    assert r1.status == "ok"
    head1 = _git(bare_p, "rev-parse", LISTING_BRANCH).stdout.strip()
    bytes1 = (tmp_path / "state" / "roadmap-dev.json").read_bytes()

    r2 = _wf(config).run(ctx)

    assert r2.status == "ok"
    assert r2.errors == []
    assert r2.items_found == 2
    assert _git(bare_p, "rev-parse", LISTING_BRANCH).stdout.strip() == head1  # no new commit
    assert (tmp_path / "state" / "roadmap-dev.json").read_bytes() == bytes1  # byte-identical
    # Action notes present: scan note + the no-push note + the drain stub note.
    assert f"scanned {FIXTURE_REPO}: 2 plan(s)" in r2.actions
    assert any("listing unchanged" in a for a in r2.actions)
    assert r2.actions[-1] == "drain skipped (idle gate closed)"


def test_drain_stub_note_tracks_gate(base_config: Config, tmp_path: Path) -> None:
    """[AC4 note] With the gate open the drain stub note is the exact Task-4 string."""
    bare_a = _make_fixture_remote(tmp_path)
    bare_p = _make_prompts_remote(tmp_path)
    config = _config(
        base_config,
        allowed_repos=[FIXTURE_REPO],
        repo_urls={FIXTURE_REPO: str(bare_a)},
        listing_repo_url=str(bare_p),
    )
    ctx = _ctx(config, tmp_path / "state", gate_open=True)

    result = _wf(config).run(ctx)

    assert result.status == "ok"
    assert [a for a in result.actions if a.startswith("drain")] == [
        "drain: not implemented (Task 4)"
    ]


def test_user_listing_edits_are_preserved(base_config: Config, tmp_path: Path) -> None:
    """[AC3] Hand-committed user edit (approve row 1 ☑, swap priorities) → both user cells
    survive the reconcile (fetched listing as base); workflow cells still correct."""
    bare_a = _make_fixture_remote(tmp_path)
    bare_p = _make_prompts_remote(tmp_path)
    config = _config(
        base_config,
        allowed_repos=[FIXTURE_REPO],
        repo_urls={FIXTURE_REPO: str(bare_a)},
        listing_repo_url=str(bare_p),
    )
    ctx = _ctx(config, tmp_path / "state")
    assert _wf(config).run(ctx).status == "ok"

    # User edit: approve the first row (unitest on dev) and swap the priorities.
    approved_unitest = "| ☑ | 2 | planning/unitest/work_plan.md | Unit tests | open | ☐ |"
    swapped_orbit = "| ☐ | 3 | planning/orbit-sim/work_plan.md | ORBIT sim extension | open | ☐ |"
    _user_edit_listing(
        bare_p,
        tmp_path,
        "approve-swap",
        lambda md: md.replace(ROW_UNITEST, approved_unitest).replace(ROW_ORBIT, swapped_orbit),
    )

    git = PushCountingGit()
    r2 = _wf(config, git).run(ctx)

    assert r2.status == "ok"
    # The user commit after the workflow's own commit makes the FIRST push a genuine
    # non-fast-forward → the documented ONE retry fires: it re-reads the remote and finds
    # it ALREADY in the reconciled state (every edited cell is user-owned) → the re-commit
    # is a no-op, so no second push is needed.
    assert git.push_calls == 1
    assert any("retrying after fetch" in a for a in r2.actions)
    # Both user cells preserved; workflow-owned cells (title/state) still correct.
    listing = _remote_listing(bare_p)
    assert approved_unitest in listing
    assert swapped_orbit in listing


def test_success_row_with_remove_tick_reappears_as_success(
    base_config: Config, tmp_path: Path
) -> None:
    """[AC4] A success row with remove ☑ (hand-edited; state entry success) → the row is
    re-added as success (fresh remove ☐) while the plan is still scanned; the drain stub
    keeps it never-startable (exactly one drain note)."""
    bare_a = _make_fixture_remote(tmp_path)
    bare_p = _make_prompts_remote(tmp_path)
    config = _config(
        base_config,
        allowed_repos=[FIXTURE_REPO],
        repo_urls={FIXTURE_REPO: str(bare_a)},
        listing_repo_url=str(bare_p),
    )
    ctx = _ctx(config, tmp_path / "state")
    assert _wf(config).run(ctx).status == "ok"

    st = _state(ctx)
    orbit_id = next(
        ident for ident, e in st["plans"].items() if e["path"] == "planning/orbit-sim/work_plan.md"
    )
    # State entry set to success (as if a job had finished), then the listing row is
    # hand-edited to success + remove ☑.
    st["plans"][orbit_id]["state"] = "success"
    ctx.state.save("roadmap-dev", st)
    removed_orbit = (
        "| ☐ | 1 | planning/orbit-sim/work_plan.md | ORBIT sim extension | success | ☑ |"
    )
    _user_edit_listing(
        bare_p, tmp_path, "remove-tick", lambda md: md.replace(ROW_ORBIT, removed_orbit)
    )

    r2 = _wf(config).run(ctx)
    assert r2.status == "ok"

    # The old (success + remove ☑) row is gone; the plan reappears as success with a
    # FRESH remove ☐ (approval kept, priority re-assigned to the empty main table = 1).
    listing = _remote_listing(bare_p)
    assert removed_orbit not in listing
    assert (
        "| ☐ | 1 | planning/orbit-sim/work_plan.md | ORBIT sim extension | success | ☐ |" in listing
    )
    assert f"removed {orbit_id} (user remove tick)" in r2.actions
    assert _state(ctx)["plans"][orbit_id]["state"] == "success"

    # The drain is a stub: exactly ONE drain note — the exact closed-gate string.
    assert [a for a in r2.actions if a.startswith("drain")] == ["drain skipped (idle gate closed)"]


def test_reaper_reaps_pending_and_cleans_leaked_worktrees(
    base_config: Config, tmp_path: Path
) -> None:
    """[AC5] A seeded pending entry + fake leaked worktree dirs → entry open with
    ``last_error`` set, both dirs removed, the reaper log line present."""
    bare_a = _make_fixture_remote(tmp_path)
    bare_p = _make_prompts_remote(tmp_path)
    config = _config(
        base_config,
        allowed_repos=[FIXTURE_REPO],
        repo_urls={FIXTURE_REPO: str(bare_a)},
        listing_repo_url=str(bare_p),
    )
    ctx = _ctx(config, tmp_path / "state")
    assert _wf(config).run(ctx).status == "ok"

    st = _state(ctx)
    unitest_id = next(
        ident for ident, e in st["plans"].items() if e["path"] == "planning/unitest/work_plan.md"
    )
    st["plans"][unitest_id].update(
        state="pending", pid=4242, started_at="2026-11-21T10:00:00+00:00"
    )
    ctx.state.save("roadmap-dev", st)

    # Fake leaked worktree dirs (plain dirs, NOT git worktrees — the fallback path
    # worktree_remove → prune + rmtree must clean them).
    root = tmp_path / "sandbox" / "roadmap-dev"
    wt_dir = root / "wt" / FIXTURE_SLUG / unitest_id
    diag_dir = root / "diag" / FIXTURE_SLUG / unitest_id
    _write(wt_dir / "junk.txt", "leaked\n")
    _write(diag_dir / "junk.txt", "leaked\n")

    r2 = _wf(config).run(ctx)
    assert r2.status == "ok"

    entry = _state(ctx)["plans"][unitest_id]
    assert entry["state"] == "open"
    assert entry["last_error"] == "orphaned pending (crash/restart) — reaped"
    assert entry["pid"] is None
    assert entry["started_at"] is None
    assert not wt_dir.exists()
    assert not diag_dir.exists()
    assert f"reaped orphan {unitest_id} (pending -> open)" in r2.actions


def test_repo_removed_from_allowlist_drops_row_keeps_state(
    base_config: Config, tmp_path: Path
) -> None:
    """[AC6] B removed from ``allowed_repos`` (config change) → its row drops on the next
    run; the state entry is KEPT in the doc (forensics)."""
    bare_a = _make_fixture_remote(tmp_path)
    bare_b = _make_simple_remote(tmp_path)
    bare_p = _make_prompts_remote(tmp_path)
    config1 = _config(
        base_config,
        allowed_repos=[FIXTURE_REPO, OTHER_REPO],
        repo_urls={FIXTURE_REPO: str(bare_a), OTHER_REPO: str(bare_b)},
        listing_repo_url=str(bare_p),
    )
    ctx = _ctx(config1, tmp_path / "state")

    r1 = _wf(config1).run(ctx)
    assert r1.status == "ok"
    assert r1.items_found == 3
    listing1 = _remote_listing(bare_p)
    assert f"# https://github.com/{OTHER_REPO}.git" in listing1
    assert ROW_NETFIT in listing1

    other_id = next(ident for ident, e in _state(ctx)["plans"].items() if e["repo"] == OTHER_REPO)

    # Config change: B is no longer allowed (same workspace → same state + clones).
    config2 = _config(
        base_config,
        allowed_repos=[FIXTURE_REPO],
        repo_urls={FIXTURE_REPO: str(bare_a)},
        listing_repo_url=str(bare_p),
    )
    r2 = _wf(config2).run(ctx)
    assert r2.status == "ok"

    listing2 = _remote_listing(bare_p)
    assert OTHER_REPO not in listing2  # the whole repo section is gone
    assert f"# https://github.com/{FIXTURE_REPO}.git" in listing2  # A's section intact
    assert f"dropped row {other_id} (plan no longer in scan)" in r2.actions

    # The state entry is kept (forensics).
    st2 = _state(ctx)
    assert other_id in st2["plans"]
    assert st2["plans"][other_id]["state"] == "open"


def test_unreachable_repo_is_repo_level_error_others_scanned(
    base_config: Config, tmp_path: Path
) -> None:
    """[AC7] An unreachable repo URL (nonexistent local path) → repo-level error with the
    repo named, other repos still scanned, status error."""
    bare_a = _make_fixture_remote(tmp_path)
    bare_p = _make_prompts_remote(tmp_path)
    config = _config(
        base_config,
        allowed_repos=[FIXTURE_REPO, OTHER_REPO],
        repo_urls={
            FIXTURE_REPO: str(bare_a),
            OTHER_REPO: str(tmp_path / "does-not-exist.git"),
        },
        listing_repo_url=str(bare_p),
    )
    ctx = _ctx(config, tmp_path / "state")

    result = _wf(config).run(ctx)

    assert result.status == "error"
    assert any(OTHER_REPO in e and "clone/fetch failed" in e for e in result.errors)
    assert result.items_found == 2  # A is still scanned
    # The listing was pushed with A's section only (no row for B).
    listing = _remote_listing(bare_p)
    assert f"# https://github.com/{FIXTURE_REPO}.git" in listing
    assert OTHER_REPO not in listing
    # The drain stub note is still appended.
    assert result.actions[-1] == "drain skipped (idle gate closed)"


def test_prompts_push_race_retries_and_keeps_user_commit(
    base_config: Config, tmp_path: Path
) -> None:
    """[AC8a] A divergent user commit on the prompts remote → the first push is rejected;
    the ONE retry re-reads the remote + re-reconciles + pushes; the user commit is kept
    (no OC: commit lost), the user's cells survive, and the workflow-owned cell the user
    touched is overwritten back."""
    bare_a = _make_fixture_remote(tmp_path)
    bare_p = _make_prompts_remote(tmp_path)
    config = _config(
        base_config,
        allowed_repos=[FIXTURE_REPO],
        repo_urls={FIXTURE_REPO: str(bare_a)},
        listing_repo_url=str(bare_p),
    )
    ctx = _ctx(config, tmp_path / "state")

    g1 = PushCountingGit()
    r1 = _wf(config, g1).run(ctx)
    assert r1.status == "ok"
    assert g1.push_calls == 1

    # User hand-commits on the remote (divergence): approves unitest (a user-owned cell —
    # must survive) AND sets the orbit state cell to "review" (a workflow-owned cell — the
    # reconciler overwrites it back to the state-doc value "open", so the retry's output
    # DIFFERS from the user text and the retry push actually lands).
    approved_unitest = "| ☑ | 1 | planning/unitest/work_plan.md | Unit tests | open | ☐ |"
    reviewed_orbit = (
        "| ☐ | 1 | planning/orbit-sim/work_plan.md | ORBIT sim extension | review | ☐ |"
    )
    _user_edit_listing(
        bare_p,
        tmp_path,
        "user-approve",
        lambda md: md.replace(ROW_UNITEST, approved_unitest).replace(ROW_ORBIT, reviewed_orbit),
    )

    g2 = PushCountingGit()
    r2 = _wf(config, g2).run(ctx)

    assert r2.status == "ok"
    assert g2.push_calls == 2  # first rejected (non-ff), the retry lands
    assert any("retrying after fetch" in a for a in r2.actions)

    # Remote history: the user commit is KEPT (not force-overwritten); the latest commit
    # is the retry's OC: reconcile; no OC: commit is lost.
    log = _remote_log(bare_p)
    oc_msg = "OC: roadmap-dev: reconcile listing (run test-run)"
    assert log[0] == oc_msg
    assert log[1] == "user-approve"
    assert log.count(oc_msg) == 2

    # Final remote listing = reconcile(remote rows): the user's approval is preserved,
    # the workflow-owned state cell is back to the state-doc value.
    listing = _remote_listing(bare_p)
    assert approved_unitest in listing
    assert ROW_ORBIT in listing  # state cell back to "open" (user's "review" overwritten)
    assert "review" not in listing


def test_prompts_push_retry_exhausted_records_error_keeps_state(
    base_config: Config, tmp_path: Path
) -> None:
    """[AC8b] When the second push still fails → the error string (repo named) is
    recorded, the state is persisted (next fire retries), and nothing crashes."""
    bare_a = _make_fixture_remote(tmp_path)
    bare_p = _make_prompts_remote(tmp_path)
    config = _config(
        base_config,
        allowed_repos=[FIXTURE_REPO],
        repo_urls={FIXTURE_REPO: str(bare_a)},
        listing_repo_url=str(bare_p),
    )
    ctx = _ctx(config, tmp_path / "state")

    assert _wf(config).run(ctx).status == "ok"
    # Divergent user commit (a real non-ff) that also differs from the reconciled output
    # (the orbit state cell is touched) — so BOTH the first push and the retry's push are
    # attempted, and FailingPushGit rejects them both.
    approved_unitest = "| ☑ | 1 | planning/unitest/work_plan.md | Unit tests | open | ☐ |"
    reviewed_orbit = (
        "| ☐ | 1 | planning/orbit-sim/work_plan.md | ORBIT sim extension | review | ☐ |"
    )
    _user_edit_listing(
        bare_p,
        tmp_path,
        "user-approve",
        lambda md: md.replace(ROW_UNITEST, approved_unitest).replace(ROW_ORBIT, reviewed_orbit),
    )

    result = _wf(config, FailingPushGit()).run(ctx)

    assert result.status == "error"
    assert len(result.errors) == 1
    assert result.errors[0].startswith(f"listing push failed for {PROMPTS_REPO}:")
    # The state is persisted (complete: both entries, both open) — the next fire retries.
    st = _state(ctx)
    assert st["version"] == 1
    assert len(st["plans"]) == 2
    assert all(e["state"] == "open" for e in st["plans"].values())
    # The remote is untouched by this run: the user commit sits on top of run 1's commit.
    log = _remote_log(bare_p)
    assert log[0] == "user-approve"
    assert log[1] == "OC: roadmap-dev: reconcile listing (run test-run)"
