"""Hermetic integration tests for the roadmap-dev drain + per-job pipeline (Task 4).

Fixture world: as in Task 3 — local bare remotes play GitHub (one per allowed repo +
one for the listing repo); a REAL :class:`Git` helper and a REAL :class:`StateStore`
over a throwaway workspace; the only fakes are the agent runner (:class:`FakeRunner`
— scripted results, a threading concurrency counter, per-call state-file snapshots),
the active-session probe (a mutable flag), and the clock (:class:`Clock` — the tests
advance it from the fake's worker threads, since the injected ``now_fn`` IS the
drain's wall clock). NO network, no real ``opencode``, no ``GITHUB_PAT``, and — per
the user decision of 2026-11-21 — NO GitHub API / NO PR creation anywhere. Git
identity is set per test (autouse fixture) and restored afterwards.

Every test drives :meth:`RoadmapDevWorkflow.run` directly (NOT via ``scheduler.run``):
run 1 discovers the plans and pushes the unapproved listing, the "user" then edits the
REMOTE ``plans.md`` (approval ☑, priorities, remove ☑) or the plan branch (answers in
``questions.md``), and subsequent gate-open runs execute the drain.

Acceptance coverage: [AC1] day drain — 3 approved plans run one at a time, in
priority order, top-up immediately after each finish; [AC2] night drain — 2
concurrent; [AC3] window crossing — slots shrink to 1 past 08:00, exactly one new
start after in-flight jobs finish; [AC4] gate close mid-drain — let-finish, no new
starts, fresh closed-gate run = phase 1 only; [AC5] review round-trip — questions →
diag commit on the plan's branch + row review/☐, answer + re-approve → attempt-2
success, the attempt branch pushed exactly once for the identity; [AC6] timeout →
failure.md on the plan's branch, state failure, never auto-restarts even with ☑;
[AC7] crash reaper — seeded pending + leaked worktree → reaped + started as attempt 3;
[AC8] success re-run guard — success (and its remove-☑ re-appearance) never startable;
[AC9] refused repo never scanned; [AC10] malformed plan ignored; [AC11] no
double-flight across 5 plans at night; [AC12] state file correct after every
transition + valid JSON after a mid-drain crash; [AC13] the suite + ruff gate.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import subprocess
import threading
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from agentic_scripts.agent import AgentResult
from agentic_scripts.config import Config, RoadmapPrompts, load_config
from agentic_scripts.git import Git
from agentic_scripts.state import StateStore
from agentic_scripts.workflows.base import WorkContext
from agentic_scripts.workflows.roadmap_dev import (
    Plan,
    RoadmapDevWorkflow,
    branch_name,
    make_plan_entry,
    parse_listing,
    plan_folder_hash,
    plan_worktree_dir,
)

# --- Constants ---------------------------------------------------------------- #

FIX = "owner/fixture"
OTHER = "owner/other"
PROMPTS_REPO = "owner/prompts"
LISTING_PATH = "plans.md"
LISTING_BRANCH = "main"
ORBIT_TOPIC = "orbit-sim"
ORBIT_PLAN_PATH = f"planning/{ORBIT_TOPIC}/work_plan.md"

DAY_1200 = datetime(2026, 11, 21, 12, 0, tzinfo=UTC)
NIGHT_2330 = datetime(2026, 11, 21, 23, 30, tzinfo=UTC)
DAY_0801 = datetime(2026, 11, 22, 8, 1, tzinfo=UTC)

ALPHA_PLAN = "# Alpha plan\n\nFirst plan.\n"
BETA_PLAN = "# Beta plan\n\nSecond plan.\n"
GAMMA_PLAN = "# Gamma plan\n\nThird plan.\n"
ORBIT_PLAN = "# ORBIT sim extension\n\nExtend the ORBIT simulation pipeline.\n"

QUIET = logging.getLogger("test.roadmap_dev_pipeline")
QUIET.setLevel(logging.CRITICAL)  # quiet: the workflow logs at INFO/WARNING/ERROR


@pytest.fixture
def base_config(tmp_path: Path) -> Config:
    """Shipped-config copy for the roadmap suite (deliberately shadows ``tests/conftest``).

    Same fixture as in :mod:`tests.test_roadmap_dev`: the conftest copy strips the
    roadmap-dev workflow and its ``roadmap_prompts`` section (a guard for
    scheduler-driving tests); this suite needs the real section with a seeded-empty
    allowlist and never calls ``scheduler.run`` — the workflow is driven directly with
    fixture remotes. ``local_listing`` is set to ``null`` so the local listing mirror
    (a local delta, covered by dedicated tests) never adds action notes here.
    """
    root = Path(__file__).resolve().parents[1]
    data = yaml.safe_load((root / "config" / "workflows.yaml").read_text(encoding="utf-8"))
    data["paths"] = {
        "state_dir": str(tmp_path / "state"),
        "log_dir": str(tmp_path / "logs"),
        "sandbox_dir": str(tmp_path / "sandbox"),
    }
    data["roadmap_prompts"]["allowed_repos"] = []  # seeded: fixture configs replace it
    data["roadmap_prompts"]["local_listing"] = None  # mirror covered by its own tests
    cfg_path = tmp_path / "workflows.yaml"
    cfg_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return load_config(cfg_path)


@pytest.fixture(autouse=True)
def _git_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set the git identity env vars for every git subprocess this test spawns."""
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Test Author")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "author@example.test")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "Test Committer")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "committer@example.test")


# --- Raw git + fixture builders ------------------------------------------------ #


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


def _make_repo_remote(
    tmp_path: Path,
    name: str,
    *,
    plans: dict[str, str] | None = None,
    broken: bool = False,
) -> Path:
    """Build a work repo whose ``main`` carries the given planning topics, as a bare.

    Args:
        tmp_path: The pytest temp dir (sources + bare live under it).
        name: A label for the src/bare dirs (and the README).
        plans: ``{topic: work_plan.md text}`` — each becomes
            ``planning/<topic>/work_plan.md`` on ``main``.
        broken: Also add ``planning/broken/README.md`` (a malformed plan folder —
            no ``work_plan.md`` — the scan must skip it).

    Returns:
        The bare remote path (the clone URL in the config).
    """
    src = tmp_path / f"src-{name}"
    src.mkdir()
    _git(src, "init", "-b", "main")
    _write(src / "README.md", f"# {name}\n")
    for topic, text in sorted((plans or {}).items()):
        _write(src / "planning" / topic / "work_plan.md", text)
    if broken:
        _write(src / "planning" / "broken" / "README.md", "# broken\n\nNo work_plan.md.\n")
    _commit(src, "initial")
    return _push_bare(src, tmp_path / f"{name}.git")


def _make_prompts_remote(tmp_path: Path, listing: str = "") -> Path:
    """Build the ``owner/prompts`` listing repo (``main`` with ``plans.md``) as a bare."""
    src = tmp_path / "prompts-src"
    src.mkdir()
    _git(src, "init", "-b", "main")
    _write(src / LISTING_PATH, listing)
    _commit(src, "initial plans.md")
    return _push_bare(src, tmp_path / "prompts.git")


def _bare_branches(bare: Path) -> list[str]:
    """List the bare remote's local (pushed) branch names."""
    out = _git(bare, "branch", "--list").stdout
    return [b.strip() for b in out.splitlines() if b.strip()]


def _bare_file(bare: Path, ref: str, path: str) -> str | None:
    """Return ``<ref>:<path>`` from the bare remote (None when the file is absent)."""
    proc = subprocess.run(
        ["git", "-C", str(bare), "show", f"{ref}:{path}"], capture_output=True, text=True
    )
    return proc.stdout if proc.returncode == 0 else None


def _row(bare_p: Path, plan_path: str) -> dict:
    """Parse the REMOTE listing and return one row's user/workflow cells.

    Returns:
        ``{"approval": bool, "priority": int, "state": str, "remove": bool}`` for the
        row whose plan path matches (raises AssertionError when no such row exists).
    """
    md = _bare_file(bare_p, LISTING_BRANCH, LISTING_PATH) or ""
    for row in parse_listing(md):
        if row.plan == plan_path:
            return {
                "approval": row.approval,
                "priority": row.priority,
                "state": row.state,
                "remove": row.remove,
            }
    raise AssertionError(f"no row for {plan_path} in remote listing: {md!r}")


# --- "User" actions (edits on the remotes) ------------------------------------- #


def _user_edit_listing(tmp_path: Path, bare_p: Path, label: str, edits: dict[str, dict]) -> None:
    """Clone the listing remote, apply per-row user edits, commit + push.

    Args:
        tmp_path: The pytest temp dir (the user clone lives under it).
        bare_p: The listing (prompts) bare remote.
        label: A label for the clone dir + commit message.
        edits: ``{plan_path: {"approval": bool?, "priority": int?, "remove": bool?}}``
            — only the given cells of the matching row are changed (the user's cells).
    """
    clone = tmp_path / f"user-{label}"
    _git(tmp_path, "clone", str(bare_p), clone.name)
    md = clone / LISTING_PATH
    lines = md.read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(lines):
        if not line.startswith("|") or "----" in line or "approval" in line:
            continue
        for path, edit in edits.items():
            if path not in line:
                continue
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if edit.get("approval") is not None:
                cells[0] = "☑" if edit["approval"] else "☐"
            if edit.get("priority") is not None:
                cells[1] = str(edit["priority"])
            if edit.get("remove") is not None:
                cells[5] = "☑" if edit["remove"] else "☐"
            lines[i] = "| " + " | ".join(cells) + " |"
            break
    md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    _commit(clone, f"user: {label}")
    _git(clone, "push", "origin", LISTING_BRANCH)


def _user_answer_questions(tmp_path: Path, bare: Path, topic: str, label: str) -> None:
    """Clone the plan's repo, append an answer to its ``questions.md``, push."""
    clone = tmp_path / f"answering-{label}"
    _git(tmp_path, "clone", str(bare), clone.name)
    q = clone / "planning" / topic / "questions.md"
    q.write_text(
        q.read_text(encoding="utf-8") + "\n**A1.** Yes — the add-on is in scope.\n",
        encoding="utf-8",
    )
    _commit(clone, "user: answers")
    _git(clone, "push", "origin", LISTING_BRANCH)


# --- Fakes ---------------------------------------------------------------------- #


class Clock:
    """A mutable injected clock (the drain's ``now_fn``); the tests advance it."""

    def __init__(self, start: datetime) -> None:
        self.t = start
        self._lock = threading.Lock()

    def now(self) -> datetime:
        """Return the current simulated time (thread-safe)."""
        with self._lock:
            return self.t

    def set(self, t: datetime) -> None:
        """Jump the simulated time (called from the fake's worker threads)."""
        with self._lock:
            self.t = t


class ActiveFlag:
    """A mutable active-session count (the injected idle-gate probe)."""

    def __init__(self, n: int = 0) -> None:
        self.n = n

    def count(self) -> int:
        """Return the current count (the probe callable)."""
        return self.n


def _report(status: str) -> str:
    """Build a skill-shaped result report ending with the mandated status line."""
    return (
        "# roadmap-dev result report\n"
        "\n"
        "## Summary\n"
        f"Outcome: {status}.\n"
        "\n"
        "## Files\n"
        "| File | Action |\n"
        "|---|---|\n"
        "| `impl.txt` | add |\n"
        "\n"
        "## Build / Tests\n"
        "- ok\n"
        "\n"
        "## Blockers\n"
        "None\n"
        "\n"
        f"Status: {status}\n"
    )


def ok_result(status: str) -> AgentResult:
    """A canned ``ok`` :class:`AgentResult` carrying a report with ``status``."""
    return AgentResult(
        status="ok",
        exit_code=0,
        final_text=_report(status),
        events=[],
        error=None,
        duration_seconds=45.0,
    )


def timeout_result() -> AgentResult:
    """A canned ``timeout`` :class:`AgentResult` (the per-job hard budget hit)."""
    return AgentResult(
        status="timeout",
        exit_code=None,
        final_text=None,
        events=[],
        error="agent run exceeded 28800s",
        duration_seconds=28800.0,
    )


class FakeRunner:
    """A scripted headless-agent stand-in (the T4 test seam).

    Records every call (agent, brief, work_dir, title, timeout), tracks concurrency
    (in-flight identities, max, double-flight violations), sleeps ``hold_seconds``
    per call so the drain's join-with-timeout loop actually observes in-flight jobs,
    and returns per-identity scripted results (consumed in call order; the last
    result repeats when exhausted). Optional per-call work mimics the agent's output:
    ``"success"`` writes ``impl.txt`` into the worktree (the non-empty diff gate) and
    ``"questions"`` writes ``<topic>/questions.md`` next to ``work_plan.md``. At each
    call start it may snapshot the state file (AC12) and run an ``on_start`` hook
    (AC3 clock jumps, AC4 gate flips). ``raise_after`` raises on the Nth call
    (AC12 mid-drain crash).
    """

    def __init__(
        self,
        scripts: dict[str, list[AgentResult]],
        *,
        work: str = "success",
        hold_seconds: float = 0.3,
        state_file: Path | None = None,
        on_start: dict[str, object] | None = None,
        raise_after: int | None = None,
    ) -> None:
        self.scripts = scripts
        self.work = work
        self.hold_seconds = hold_seconds
        self.state_file = state_file
        self.on_start = on_start or {}
        self.raise_after = raise_after
        self.calls: list[dict] = []
        self.events: list[tuple[str, str]] = []
        self.state_snapshots: list[dict] = []
        self.double_flight: list[str] = []
        self.max_concurrency = 0
        self._lock = threading.Lock()
        self._active: dict[str, int] = {}
        self._cursor: dict[str, int] = {}

    def run(
        self,
        *,
        agent: str,
        brief: str,
        work_dir: Path,
        title: str | None = None,
        timeout_seconds: int | None = None,
    ) -> AgentResult:
        """Record the call, do the scripted work, sleep, return the canned result."""
        assert agent == "planner-enhanced"  # the drain's documented agent
        ident = title.split()[1]  # title: "roadmap-dev <id> (<run_id>)"
        with self._lock:
            n = self._active.get(ident, 0) + 1
            if n > 1:
                self.double_flight.append(ident)
            self._active[ident] = n
            self.max_concurrency = max(self.max_concurrency, len(self._active))
            self.events.append(("start", ident))
            self.calls.append(
                {
                    "agent": agent,
                    "brief": brief,
                    "work_dir": work_dir,
                    "title": title,
                    "timeout_seconds": timeout_seconds,
                }
            )
        try:
            hook = self.on_start.get(ident)
            if hook is not None:
                hook()  # e.g. a clock jump or a gate flip (AC3 / AC4)
            if self.state_file is not None:
                raw = self.state_file.read_text(encoding="utf-8")
                self.state_snapshots.append(json.loads(raw) if raw.strip() else {})
            self._do_work(Path(work_dir))
            time.sleep(self.hold_seconds)
            if self.raise_after is not None and len(self.calls) >= self.raise_after:
                raise RuntimeError(f"injected runner crash (call {len(self.calls)})")
            return self._next_result(ident)
        finally:
            with self._lock:
                left = self._active[ident] - 1
                if left:
                    self._active[ident] = left
                else:
                    del self._active[ident]
                self.events.append(("end", ident))

    def _do_work(self, work_dir: Path) -> None:
        """Mimic the agent's worktree output for this runner's ``work`` mode."""
        if self.work == "success":
            (work_dir / "impl.txt").write_text("impl by fake\n", encoding="utf-8")
        elif self.work == "questions":
            folder = next(work_dir.glob("planning/*/work_plan.md")).parent
            (folder / "questions.md").write_text(
                "1. **Scope question** — does the plan include the X add-on?\n"
                "   Context: the plan is silent on it and it changes the API surface.\n"
                "   Needed: a yes/no answer.\n",
                encoding="utf-8",
            )
        # "none": no file change

    def _next_result(self, ident: str) -> AgentResult:
        """Pop this identity's next scripted result (the last one repeats)."""
        with self._lock:
            results = self.scripts[ident]
            i = self._cursor.get(ident, 0)
            self._cursor[ident] = i + 1
            return results[i] if i < len(results) else results[-1]


# --- Config / context / workflow builders --------------------------------------- #


def _config(
    base_config: Config,
    *,
    allowed_repos: list[str],
    repo_urls: dict[str, str],
    listing_repo_url: str,
) -> Config:
    """Point ``base_config``'s roadmap_prompts at the fixture remotes."""
    rp = RoadmapPrompts(
        allowed_repos=list(allowed_repos),
        listing_repo=PROMPTS_REPO,
        listing_repo_url=listing_repo_url,
        listing_path=LISTING_PATH,
        listing_branch=LISTING_BRANCH,
        run_timeout_minutes=480,
        test_commands={},
        repo_urls=dict(repo_urls),
        local_listing=None,  # mirror is covered by its own tests (local delta)
    )
    return dataclasses.replace(base_config, roadmap_prompts=rp)


def _ctx(config: Config, state_dir: Path, *, gate_open: bool = True) -> WorkContext:
    """Build a hermetic :class:`WorkContext` over the tmp workspace (quiet logger)."""
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


def _wf(
    config: Config, *, clock: Clock, runner: FakeRunner, active: ActiveFlag
) -> RoadmapDevWorkflow:
    """Build the workflow with the injected runner / probe / clock (no real seams)."""
    return RoadmapDevWorkflow(
        config.roadmap_prompts,
        git=Git(),
        runner=runner,
        active_sessions=active.count,
        now_fn=clock.now,
    )


def _state(ctx: WorkContext) -> dict:
    """Return the workflow's persisted state document ({} when absent)."""
    return ctx.state.load("roadmap-dev")


def _attempt_branches(bare: Path) -> list[str]:
    """Return the bare remote's ``roadmap-dev/*`` attempt branches (sorted)."""
    return sorted(b for b in _bare_branches(bare) if b.startswith("roadmap-dev/"))


def _identities_for(paths: dict[str, str], repo: str = FIX, branch: str = "main") -> dict:
    """Compute the scanned identity for each ``{topic: work_plan text}`` plan.

    The scan hashes ONLY ``work_plan.md`` here (each fixture folder carries exactly
    that one file), and :meth:`Git.show_file_bytes` returns the exact blob bytes
    (no decode, no rstrip) — so the hash input is ``text.encode("utf-8")`` (exactly
    what ``_scan_repo`` feeds the hash).
    """
    out = {}
    for topic, text in paths.items():
        h = plan_folder_hash({"work_plan.md": text.encode("utf-8")})
        plan = Plan(repo, branch, f"planning/{topic}/work_plan.md", "", h)
        out[topic] = plan.identity
    return out


def _three_plan_world(tmp_path: Path, *, broken: bool = False) -> tuple[Path, Path]:
    """Build the 3-plan fixture repo + empty listing repo; return (bare, prompts_bare)."""
    bare_f = _make_repo_remote(
        tmp_path,
        "fixture",
        plans={"alpha": ALPHA_PLAN, "beta": BETA_PLAN, "gamma": GAMMA_PLAN},
        broken=broken,
    )
    bare_p = _make_prompts_remote(tmp_path)
    return bare_f, bare_p


# --- AC1: day drain (sequential, priority order) -------------------------------- #


def test_ac1_day_drain_sequential_priority_order(base_config: Config, tmp_path: Path) -> None:
    """[AC1] now=12:00, 3 approved plans → one at a time, priority order, top-up
    immediately after each finish (the drain returns only after job 3)."""
    bare_f, bare_p = _three_plan_world(tmp_path, broken=True)
    config = _config(
        base_config,
        allowed_repos=[FIX],
        repo_urls={FIX: str(bare_f)},
        listing_repo_url=str(bare_p),
    )
    state_dir = tmp_path / "state"
    ctx = _ctx(config, state_dir, gate_open=False)
    clock = Clock(DAY_1200)

    r1 = _wf(config, clock=clock, runner=FakeRunner({}), active=ActiveFlag(0)).run(ctx)
    assert r1.status == "ok"
    assert r1.items_found == 3
    assert r1.actions[-1] == "drain skipped (idle gate closed)"
    # [AC10 shared fixture] the malformed folder produced no row and no error.
    assert r1.errors == []
    assert "broken" not in (_bare_file(bare_p, LISTING_BRANCH, LISTING_PATH) or "")

    idents = _identities_for({"alpha": ALPHA_PLAN, "beta": BETA_PLAN, "gamma": GAMMA_PLAN})
    i_a, i_b, i_g = idents["alpha"], idents["beta"], idents["gamma"]

    # The user approves with priorities beta=1, gamma=2, alpha=3.
    _user_edit_listing(
        tmp_path,
        bare_p,
        "approve",
        {
            "planning/beta/work_plan.md": {"approval": True, "priority": 1},
            "planning/gamma/work_plan.md": {"approval": True, "priority": 2},
            "planning/alpha/work_plan.md": {"approval": True, "priority": 3},
        },
    )

    runner = FakeRunner(
        {
            i_b: [ok_result("success")],
            i_g: [ok_result("success")],
            i_a: [ok_result("success")],
        }
    )
    r2 = _wf(config, clock=clock, runner=runner, active=ActiveFlag(0)).run(
        _ctx(config, state_dir, gate_open=True)
    )

    assert r2.status == "ok"
    assert r2.errors == []
    assert r2.items_found == 3
    assert "drain start slots=1 startable=3" in r2.actions
    # One at a time: strictly start/end/start/end/... in priority order.
    assert runner.max_concurrency == 1
    assert runner.double_flight == []
    assert [ident for _, ident in runner.events] == [
        i_b,
        i_b,
        i_g,
        i_g,
        i_a,
        i_a,
    ]
    assert [a for a in r2.actions if a.startswith("top-up: starting")] == [
        f"top-up: starting {i_b} (slot 1/1)",
        f"top-up: starting {i_g} (slot 1/1)",
        f"top-up: starting {i_a} (slot 1/1)",
    ]
    # The drain returned only after job 3 finished (all three ends are recorded).
    assert sum(1 for ev, _ in runner.events if ev == "end") == 3
    assert r2.actions[-1] == "drain done (slots=1 startable=0)"
    # Spawn contract: the documented agent, the 8 h budget, the attempt worktree.
    assert runner.calls[0]["agent"] == "planner-enhanced"
    assert runner.calls[0]["timeout_seconds"] == 480 * 60
    assert runner.calls[0]["work_dir"].name == i_b
    assert runner.calls[0]["title"] == f"roadmap-dev {i_b} (test-run)"

    # All three delivered: state + one attempt branch each (implementation + archive).
    st = _state(_ctx(config, state_dir))
    for topic, ident in (("beta", i_b), ("gamma", i_g), ("alpha", i_a)):
        e = st["plans"][ident]
        assert e["state"] == "success"
        assert e["branch_name"] == f"roadmap-dev/{ident}-1"
        assert e["commit_sha"]
        assert e["finished_at"] is not None
        br = f"roadmap-dev/{ident}-1"
        assert _bare_file(bare_f, br, "impl.txt") == "impl by fake\n"
        assert _bare_file(bare_f, br, f"planning/archived/{topic}/work_plan.md")
        assert _bare_file(bare_f, br, f"planning/{topic}/work_plan.md") is None
    assert _attempt_branches(bare_f) == sorted(
        f"roadmap-dev/{ident}-1" for ident in (i_a, i_b, i_g)
    )
    # The delivery note (NO PR is created — the human opens it).
    for ident in (i_a, i_b, i_g):
        assert (
            f"pushed branch roadmap-dev/{ident}-1 for {FIX} @ main ({ident}) — human "
            "opens the PR" in r2.actions
        )
    # The listing shows all three as success (approval preserved).
    for topic in ("alpha", "beta", "gamma"):
        row = _row(bare_p, f"planning/{topic}/work_plan.md")
        assert row["state"] == "success" and row["approval"] is True


# --- AC2: night drain (two concurrent) ------------------------------------------ #


def test_ac2_night_drain_two_concurrent(base_config: Config, tmp_path: Path) -> None:
    """[AC2] now=23:30, 3 approved plans → jobs 1+2 in flight together, job 3 after
    one finishes (max concurrency 2)."""
    bare_f, bare_p = _three_plan_world(tmp_path)
    config = _config(
        base_config,
        allowed_repos=[FIX],
        repo_urls={FIX: str(bare_f)},
        listing_repo_url=str(bare_p),
    )
    state_dir = tmp_path / "state"
    clock = Clock(NIGHT_2330)

    r1 = _wf(config, clock=clock, runner=FakeRunner({}), active=ActiveFlag(0)).run(
        _ctx(config, state_dir, gate_open=False)
    )
    assert r1.status == "ok"
    idents = _identities_for({"alpha": ALPHA_PLAN, "beta": BETA_PLAN, "gamma": GAMMA_PLAN})
    i_a, i_b, i_g = idents["alpha"], idents["beta"], idents["gamma"]
    _user_edit_listing(
        tmp_path,
        bare_p,
        "approve",
        {
            "planning/alpha/work_plan.md": {"approval": True, "priority": 1},
            "planning/beta/work_plan.md": {"approval": True, "priority": 2},
            "planning/gamma/work_plan.md": {"approval": True, "priority": 3},
        },
    )

    runner = FakeRunner(
        {
            i_a: [ok_result("success")],
            i_b: [ok_result("success")],
            i_g: [ok_result("success")],
        },
        hold_seconds=0.5,
    )
    r2 = _wf(config, clock=clock, runner=runner, active=ActiveFlag(0)).run(
        _ctx(config, state_dir, gate_open=True)
    )

    assert r2.status == "ok"
    assert "drain start slots=2 startable=3" in r2.actions
    # First top-up fills BOTH slots: alpha and beta start before either one ends
    # (that overlap IS the 2-slot concurrency — max_concurrency proves it).
    starts = {ident: n for n, (ev, ident) in enumerate(runner.events) if ev == "start"}
    ends = {ident: n for n, (ev, ident) in enumerate(runner.events) if ev == "end"}
    assert starts[i_a] < ends[i_a] and starts[i_b] < ends[i_b]
    assert max(starts[i_a], starts[i_b]) < min(ends[i_a], ends[i_b])  # in flight together
    # Job 3 starts after at least one of the first two finishes (the top-up).
    assert starts[i_g] > min(ends[i_a], ends[i_b])
    assert Counter(ident for _, ident in runner.events) == {i_a: 2, i_b: 2, i_g: 2}
    assert runner.max_concurrency == 2
    assert runner.double_flight == []
    assert [a for a in r2.actions if a.startswith("top-up: starting")] == [
        f"top-up: starting {i_a} (slot 1/2)",
        f"top-up: starting {i_b} (slot 2/2)",
        f"top-up: starting {i_g} (slot 1/2)",
    ]
    assert all(
        _state(_ctx(config, state_dir))["plans"][ident]["state"] == "success"
        for ident in (i_a, i_b, i_g)
    )


# --- AC3: window crossing (slots shrink) ---------------------------------------- #


def test_ac3_window_crossing_slots_shrink(base_config: Config, tmp_path: Path) -> None:
    """[AC3] jobs in flight at night; the clock crosses 08:00 → slots=1 → no new
    starts until in-flight jobs finish, then exactly one starts (slot 1/1)."""
    bare_f, bare_p = _three_plan_world(tmp_path)
    config = _config(
        base_config,
        allowed_repos=[FIX],
        repo_urls={FIX: str(bare_f)},
        listing_repo_url=str(bare_p),
    )
    state_dir = tmp_path / "state"
    clock = Clock(NIGHT_2330)

    r1 = _wf(config, clock=clock, runner=FakeRunner({}), active=ActiveFlag(0)).run(
        _ctx(config, state_dir, gate_open=False)
    )
    assert r1.status == "ok"
    idents = _identities_for({"alpha": ALPHA_PLAN, "beta": BETA_PLAN, "gamma": GAMMA_PLAN})
    i_a, i_b, i_g = idents["alpha"], idents["beta"], idents["gamma"]
    # Priorities: gamma=1, alpha=2 (the night pair), beta=3 (the waiter).
    _user_edit_listing(
        tmp_path,
        bare_p,
        "approve",
        {
            "planning/gamma/work_plan.md": {"approval": True, "priority": 1},
            "planning/alpha/work_plan.md": {"approval": True, "priority": 2},
            "planning/beta/work_plan.md": {"approval": True, "priority": 3},
        },
    )

    # As the first night job starts, the box wakes: the clock jumps past 08:00.
    runner = FakeRunner(
        {
            i_g: [ok_result("success")],
            i_a: [ok_result("success")],
            i_b: [ok_result("success")],
        },
        hold_seconds=0.4,
        on_start={i_g: lambda: clock.set(DAY_0801)},
    )
    r2 = _wf(config, clock=clock, runner=runner, active=ActiveFlag(0)).run(
        _ctx(config, state_dir, gate_open=True)
    )

    assert r2.status == "ok"
    seq = [ident for _, ident in runner.events]
    # Night pair started together (slots=2 at 23:30), then both finish.
    assert seq[0] == i_g and seq[1] == i_a
    assert seq[2] in (i_g, i_a)
    assert seq[3] in (i_g, i_a)
    # After the crossing (08:01 → slots=1) exactly ONE starts — after both finished.
    assert seq[4] == i_b and seq[5] == i_b
    assert runner.max_concurrency == 2
    tops = [a for a in r2.actions if a.startswith("top-up: starting")]
    assert tops[0] == f"top-up: starting {i_g} (slot 1/2)"
    assert tops[1] == f"top-up: starting {i_a} (slot 2/2)"
    assert tops[2] == f"top-up: starting {i_b} (slot 1/1)"  # slots=1 after 08:00
    assert all(
        _state(_ctx(config, state_dir))["plans"][ident]["state"] == "success"
        for ident in (i_a, i_b, i_g)
    )


# --- AC4: gate close mid-drain (let-finish) -------------------------------------- #


def test_ac4_gate_close_mid_drain_let_finish(base_config: Config, tmp_path: Path) -> None:
    """[AC4] 2 jobs in flight (night); the gate closes → the remaining startable is
    NOT started, both in-flight jobs finish, the drain ends; a fresh closed-gate run
    is phase 1 only (zero runner calls)."""
    bare_f, bare_p = _three_plan_world(tmp_path)
    config = _config(
        base_config,
        allowed_repos=[FIX],
        repo_urls={FIX: str(bare_f)},
        listing_repo_url=str(bare_p),
    )
    state_dir = tmp_path / "state"
    clock = Clock(NIGHT_2330)

    r1 = _wf(config, clock=clock, runner=FakeRunner({}), active=ActiveFlag(0)).run(
        _ctx(config, state_dir, gate_open=False)
    )
    assert r1.status == "ok"
    idents = _identities_for({"alpha": ALPHA_PLAN, "beta": BETA_PLAN, "gamma": GAMMA_PLAN})
    i_a, i_b, i_g = idents["alpha"], idents["beta"], idents["gamma"]
    _user_edit_listing(
        tmp_path,
        bare_p,
        "approve",
        {
            "planning/alpha/work_plan.md": {"approval": True, "priority": 1},
            "planning/beta/work_plan.md": {"approval": True, "priority": 2},
            "planning/gamma/work_plan.md": {"approval": True, "priority": 3},
        },
    )

    active = ActiveFlag(0)
    # The user sits down as soon as the first job starts (the gate closes).
    runner = FakeRunner(
        {
            i_a: [ok_result("success")],
            i_b: [ok_result("success")],
            i_g: [ok_result("success")],
        },
        hold_seconds=0.4,
        on_start={i_a: lambda: setattr(active, "n", 1)},
    )
    r2 = _wf(config, clock=clock, runner=runner, active=active).run(
        _ctx(config, state_dir, gate_open=True)
    )

    assert r2.status == "ok"
    seq = [ident for _, ident in runner.events]
    # The night pair ran to completion (let-finish — no preemption); gamma never started.
    assert sorted(seq) == [i_a, i_a, i_b, i_b]
    assert i_g not in seq
    assert "gate closed — no new starts" in r2.actions
    st = _state(_ctx(config, state_dir))
    assert st["plans"][i_a]["state"] == "success"
    assert st["plans"][i_b]["state"] == "success"
    assert st["plans"][i_g]["state"] == "open"  # never started

    # Fresh run, gate closed: phase 1 only, the exact skip note, zero runner calls.
    runner2 = FakeRunner({})
    r3 = _wf(config, clock=clock, runner=runner2, active=ActiveFlag(0)).run(
        _ctx(config, state_dir, gate_open=False)
    )
    assert r3.status == "ok"
    assert r3.actions[-1] == "drain skipped (idle gate closed)"
    assert runner2.calls == []


# --- AC5: review round-trip ------------------------------------------------------- #


def test_ac5_review_round_trip(base_config: Config, tmp_path: Path) -> None:
    """[AC5] questions → diag commit on the plan's branch + row review/☐ → the user
    answers + re-approves → attempt-2 success: the attempt branch pushed exactly ONCE
    for the identity, state success with branch_name + commit_sha."""
    bare_f = _make_repo_remote(tmp_path, "fixture", plans={ORBIT_TOPIC: ORBIT_PLAN})
    bare_p = _make_prompts_remote(tmp_path)
    config = _config(
        base_config,
        allowed_repos=[FIX],
        repo_urls={FIX: str(bare_f)},
        listing_repo_url=str(bare_p),
    )
    state_dir = tmp_path / "state"
    clock = Clock(DAY_1200)

    r1 = _wf(config, clock=clock, runner=FakeRunner({}), active=ActiveFlag(0)).run(
        _ctx(config, state_dir, gate_open=False)
    )
    assert r1.status == "ok" and r1.items_found == 1
    ident = _identities_for({ORBIT_TOPIC: ORBIT_PLAN})[ORBIT_TOPIC]

    _user_edit_listing(
        tmp_path, bare_p, "approve", {ORBIT_PLAN_PATH: {"approval": True, "priority": 1}}
    )

    # Run 2: the planner raises a major question.
    runner = FakeRunner({ident: [ok_result("questions")]}, work="questions")
    r2 = _wf(config, clock=clock, runner=runner, active=ActiveFlag(0)).run(
        _ctx(config, state_dir, gate_open=True)
    )
    assert r2.status == "ok"
    assert len(runner.calls) == 1
    assert runner.calls[0]["work_dir"].name == ident  # the attempt worktree
    assert "Attempt: 1" in runner.calls[0]["brief"]
    # The diag commit landed on the plan's branch (main) of the fixture REMOTE.
    subject = _git(bare_f, "log", "--format=%s", "-1", LISTING_BRANCH).stdout.strip()
    assert subject == f"OC: roadmap-dev: {ident} — questions (run test-run)"
    q_remote = _bare_file(bare_f, LISTING_BRANCH, f"planning/{ORBIT_TOPIC}/questions.md")
    assert q_remote and "Scope question" in q_remote
    # Row: review + de-approved (the ONE sanctioned approval removal).
    row = _row(bare_p, ORBIT_PLAN_PATH)
    assert row == {"approval": False, "priority": 1, "state": "review", "remove": False}
    e = _state(_ctx(config, state_dir))["plans"][ident]
    assert e["state"] == "review" and e["attempt"] == 1
    # No attempt branch was pushed (the questions outcome is not a delivery).
    assert _attempt_branches(bare_f) == []
    assert any(a.startswith(f"job finished {ident} status=questions") for a in r2.actions)
    assert f"unapproved {ident} (questions raised)" in r2.actions

    # The user answers questions.md on the branch and re-approves the row.
    _user_answer_questions(tmp_path, bare_f, ORBIT_TOPIC, "r2")
    _user_edit_listing(tmp_path, bare_p, "re-approve", {ORBIT_PLAN_PATH: {"approval": True}})

    # Run 3: attempt 2 succeeds → the delivery branch is pushed exactly once.
    runner3 = FakeRunner({ident: [ok_result("success")]})
    r3 = _wf(config, clock=clock, runner=runner3, active=ActiveFlag(0)).run(
        _ctx(config, state_dir, gate_open=True)
    )
    assert r3.status == "ok"
    assert "Attempt: 2" in runner3.calls[0]["brief"]
    e = _state(_ctx(config, state_dir))["plans"][ident]
    assert e["state"] == "success"
    assert e["attempt"] == 2
    assert e["branch_name"] == f"roadmap-dev/{ident}-2"
    assert e["commit_sha"] == _git(bare_f, "rev-parse", f"roadmap-dev/{ident}-2").stdout.strip()
    # Exactly ONE attempt branch for the identity (the questions attempt never pushed).
    assert _attempt_branches(bare_f) == [f"roadmap-dev/{ident}-2"]
    br = f"roadmap-dev/{ident}-2"
    assert _bare_file(bare_f, br, "impl.txt") == "impl by fake\n"
    # The plan folder is archived on the attempt branch (the implementation + archive).
    assert _bare_file(bare_f, br, f"planning/archived/{ORBIT_TOPIC}/work_plan.md")
    assert _bare_file(bare_f, br, ORBIT_PLAN_PATH) is None
    # Commit subjects: the implementation commit, then the archive commit.
    subjects = _git(bare_f, "log", "--format=%s", br).stdout.splitlines()
    assert subjects[0] == f"OC: roadmap-dev: archive plan {ident} (run test-run)"
    assert subjects[1] == "OC: ORBIT sim extension"
    # The listing row: success (the user's approval survived the round-trip).
    row = _row(bare_p, ORBIT_PLAN_PATH)
    assert row["state"] == "success" and row["approval"] is True
    assert f"pushed branch {br} for {FIX} @ main ({ident}) — human opens the PR" in r3.actions


# --- AC6: timeout → failure, no auto-restart ------------------------------------- #


def test_ac6_timeout_failure_no_autorestart(base_config: Config, tmp_path: Path) -> None:
    """[AC6] a timeout job → failure.md on the plan's branch, state failure with
    last_error; the next drain does NOT restart it even though approval is still ☑
    (the stale remote row must not self re-arm)."""
    bare_f = _make_repo_remote(tmp_path, "fixture", plans={ORBIT_TOPIC: ORBIT_PLAN})
    bare_p = _make_prompts_remote(tmp_path)
    config = _config(
        base_config,
        allowed_repos=[FIX],
        repo_urls={FIX: str(bare_f)},
        listing_repo_url=str(bare_p),
    )
    state_dir = tmp_path / "state"
    clock = Clock(DAY_1200)

    r1 = _wf(config, clock=clock, runner=FakeRunner({}), active=ActiveFlag(0)).run(
        _ctx(config, state_dir, gate_open=False)
    )
    assert r1.status == "ok"
    ident = _identities_for({ORBIT_TOPIC: ORBIT_PLAN})[ORBIT_TOPIC]
    _user_edit_listing(
        tmp_path, bare_p, "approve", {ORBIT_PLAN_PATH: {"approval": True, "priority": 1}}
    )

    runner = FakeRunner({ident: [timeout_result()]}, work="none", hold_seconds=0.1)
    r2 = _wf(config, clock=clock, runner=runner, active=ActiveFlag(0)).run(
        _ctx(config, state_dir, gate_open=True)
    )
    # A failed job is a business error (names repo + identity for the operator).
    assert r2.status == "error"
    assert r2.errors == [f"{FIX} ({ident}): agent timeout: agent run exceeded 28800s"]
    # failure.md committed on the plan's branch, content = the failure reason.
    subject = _git(bare_f, "log", "--format=%s", "-1", LISTING_BRANCH).stdout.strip()
    assert subject == f"OC: roadmap-dev: {ident} — failure (run test-run)"
    content = _bare_file(bare_f, LISTING_BRANCH, f"planning/{ORBIT_TOPIC}/failure.md")
    assert content == "agent timeout: agent run exceeded 28800s"
    e = _state(_ctx(config, state_dir))["plans"][ident]
    assert e["state"] == "failure"
    assert e["last_error"] == "agent timeout: agent run exceeded 28800s"
    # The failure row landed in the listing (so a later pass sees failure, not open).
    row = _row(bare_p, ORBIT_PLAN_PATH)
    assert row["state"] == "failure" and row["approval"] is True
    assert not any("re-armed" in a for a in r2.actions)  # no self re-arm

    # Next drain: approval still ☑ — failure never auto-restarts.
    runner2 = FakeRunner({ident: [ok_result("success")]})
    r3 = _wf(config, clock=clock, runner=runner2, active=ActiveFlag(0)).run(
        _ctx(config, state_dir, gate_open=True)
    )
    assert r3.status == "ok"
    assert runner2.calls == []  # the identity was never startable
    assert r3.actions[-1] == "drain done (slots=1 startable=0)"
    assert _attempt_branches(bare_f) == []
    assert _state(_ctx(config, state_dir))["plans"][ident]["state"] == "failure"


# --- AC7: crash reaper ------------------------------------------------------------- #


def test_ac7_crash_reaper_restarts_at_next_attempt(base_config: Config, tmp_path: Path) -> None:
    """[AC7] seeded ``pending`` entry (attempt 2) + leaked attempt worktree → the
    run-start reaper flips to open and removes the dir; the drain then starts it
    fresh as attempt 3 (one runner call). The listing is pre-seeded with the row the
    workflow would have pushed before the crash (already approved by the user)."""
    bare_f = _make_repo_remote(tmp_path, "fixture", plans={ORBIT_TOPIC: ORBIT_PLAN})
    bare_p = _make_prompts_remote(
        tmp_path,
        listing=(
            f"# https://github.com/{FIX}.git\n"
            "## main\n"
            "| approval | priority | plan | title | state | remove |\n"
            "|----------|----------|------|-------|-------|--------|\n"
            f"| ☑ | 1 | {ORBIT_PLAN_PATH} | ORBIT sim extension | open | ☐ |\n"
        ),
    )
    config = _config(
        base_config,
        allowed_repos=[FIX],
        repo_urls={FIX: str(bare_f)},
        listing_repo_url=str(bare_p),
    )
    state_dir = tmp_path / "state"
    clock = Clock(DAY_1200)

    # Seed the "crashed" world: a pending entry (attempt 2) + a leaked worktree dir.
    # (show_file_bytes returns exact blob bytes — mirror the scan's hash input.)
    h = plan_folder_hash({"work_plan.md": ORBIT_PLAN.encode("utf-8")})
    plan = Plan(FIX, "main", ORBIT_PLAN_PATH, "ORBIT sim extension", h)
    ident = plan.identity
    entry = make_plan_entry(
        plan,
        "pending",
        now=DAY_1200,
        attempt=2,
        pid=424242,
        branch_name=branch_name(ident, 2),
        last_run_id="crashed-run",
    )
    StateStore(state_dir).save("roadmap-dev", {"version": 1, "plans": {ident: entry}})
    sandbox = state_dir.parent / "sandbox"
    leaked = plan_worktree_dir(sandbox / "roadmap-dev", FIX, ident)
    _write(leaked / "leak.txt", "leaked worktree content\n")

    r1 = _wf(config, clock=clock, runner=FakeRunner({}), active=ActiveFlag(0)).run(
        _ctx(config, state_dir, gate_open=False)
    )
    assert r1.status == "ok"
    assert f"reaped orphan {ident} (pending -> open)" in r1.actions
    assert not leaked.exists()  # the leaked worktree dir was removed
    e = _state(_ctx(config, state_dir))["plans"][ident]
    assert e["state"] == "open" and e["attempt"] == 2  # the attempt counter sticks

    # Run 2: the drain starts it fresh — attempt 3, exactly one runner call.
    runner = FakeRunner({ident: [ok_result("success")]})
    r2 = _wf(config, clock=clock, runner=runner, active=ActiveFlag(0)).run(
        _ctx(config, state_dir, gate_open=True)
    )
    assert r2.status == "ok"
    assert len(runner.calls) == 1
    assert "Attempt: 3" in runner.calls[0]["brief"]
    e = _state(_ctx(config, state_dir))["plans"][ident]
    assert e["state"] == "success"
    assert e["attempt"] == 3
    assert e["branch_name"] == f"roadmap-dev/{ident}-3"
    assert _attempt_branches(bare_f) == [f"roadmap-dev/{ident}-3"]


# --- AC8: success re-run guard ------------------------------------------------------ #


def test_ac8_success_never_startable_again(base_config: Config, tmp_path: Path) -> None:
    """[AC8] a ``success`` entry is never startable again (no runner call, no new
    push) — including its remove-☑ re-appearance as a ``success`` row."""
    bare_f = _make_repo_remote(tmp_path, "fixture", plans={ORBIT_TOPIC: ORBIT_PLAN})
    bare_p = _make_prompts_remote(tmp_path)
    config = _config(
        base_config,
        allowed_repos=[FIX],
        repo_urls={FIX: str(bare_f)},
        listing_repo_url=str(bare_p),
    )
    state_dir = tmp_path / "state"
    clock = Clock(DAY_1200)

    r1 = _wf(config, clock=clock, runner=FakeRunner({}), active=ActiveFlag(0)).run(
        _ctx(config, state_dir, gate_open=False)
    )
    assert r1.status == "ok"
    ident = _identities_for({ORBIT_TOPIC: ORBIT_PLAN})[ORBIT_TOPIC]
    _user_edit_listing(
        tmp_path, bare_p, "approve", {ORBIT_PLAN_PATH: {"approval": True, "priority": 1}}
    )

    # First drain: one success (attempt 1).
    runner1 = FakeRunner({ident: [ok_result("success")]})
    r2 = _wf(config, clock=clock, runner=runner1, active=ActiveFlag(0)).run(
        _ctx(config, state_dir, gate_open=True)
    )
    assert r2.status == "ok"
    assert len(runner1.calls) == 1
    assert _attempt_branches(bare_f) == [f"roadmap-dev/{ident}-1"]

    # Second drain: success is not startable — no runner call, no new push.
    runner2 = FakeRunner({ident: [ok_result("success")]})
    r3 = _wf(config, clock=clock, runner=runner2, active=ActiveFlag(0)).run(
        _ctx(config, state_dir, gate_open=True)
    )
    assert r3.status == "ok"
    assert runner2.calls == []
    assert r3.actions[-1] == "drain done (slots=1 startable=0)"
    assert _attempt_branches(bare_f) == [f"roadmap-dev/{ident}-1"]

    # The user remove-☑'s the success row → it re-appears (harmless) as success,
    # still never startable.
    _user_edit_listing(tmp_path, bare_p, "remove", {ORBIT_PLAN_PATH: {"remove": True}})
    runner3 = FakeRunner({ident: [ok_result("success")]})
    r4 = _wf(config, clock=clock, runner=runner3, active=ActiveFlag(0)).run(
        _ctx(config, state_dir, gate_open=True)
    )
    assert r4.status == "ok"
    assert runner3.calls == []
    assert _attempt_branches(bare_f) == [f"roadmap-dev/{ident}-1"]
    row = _row(bare_p, ORBIT_PLAN_PATH)
    assert row["state"] == "success" and row["remove"] is False
    assert _state(_ctx(config, state_dir))["plans"][ident]["state"] == "success"


# --- AC9: refused repo ---------------------------------------------------------------- #


def test_ac9_refused_repo_never_scanned(base_config: Config, tmp_path: Path) -> None:
    """[AC9] a repo that exists as a bare remote but is NOT in ``allowed_repos`` is
    never scanned (no clone, no row, no job)."""
    bare_f = _make_repo_remote(tmp_path, "fixture", plans={ORBIT_TOPIC: ORBIT_PLAN})
    bare_o = _make_repo_remote(
        tmp_path, "other", plans={"other-plan": "# Other plan\n\nRefused repo.\n"}
    )
    bare_p = _make_prompts_remote(tmp_path)
    assert bare_o.is_dir()  # the refused repo exists as a bare remote…
    # allowed_repos: only FIX — OTHER is deliberately absent (no repo_urls entry).
    config = _config(
        base_config,
        allowed_repos=[FIX],
        repo_urls={FIX: str(bare_f)},
        listing_repo_url=str(bare_p),
    )
    state_dir = tmp_path / "state"
    clock = Clock(DAY_1200)

    r1 = _wf(config, clock=clock, runner=FakeRunner({}), active=ActiveFlag(0)).run(
        _ctx(config, state_dir, gate_open=False)
    )
    assert r1.status == "ok"
    assert r1.items_found == 1
    clones = state_dir.parent / "sandbox" / "roadmap-dev" / "clones"
    assert (clones / "owner__fixture").is_dir()
    assert not (clones / "owner__other").exists()  # never cloned
    listing = _bare_file(bare_p, LISTING_BRANCH, LISTING_PATH) or ""
    assert "owner/other" not in listing and "other-plan" not in listing

    # Approving the only fixture plan runs exactly one job (the refused repo's plan,
    # even if it had a row, could never start — there is no scan of its repo).
    ident = _identities_for({ORBIT_TOPIC: ORBIT_PLAN})[ORBIT_TOPIC]
    _user_edit_listing(
        tmp_path, bare_p, "approve", {ORBIT_PLAN_PATH: {"approval": True, "priority": 1}}
    )
    runner = FakeRunner({ident: [ok_result("success")]})
    r2 = _wf(config, clock=clock, runner=runner, active=ActiveFlag(0)).run(
        _ctx(config, state_dir, gate_open=True)
    )
    assert r2.status == "ok"
    assert len(runner.calls) == 1
    assert runner.calls[0]["work_dir"].name == ident


# --- AC10: malformed plan --------------------------------------------------------------- #


def test_ac10_malformed_plan_ignored(base_config: Config, tmp_path: Path) -> None:
    """[AC10] a folder without ``work_plan.md`` → no row, no job, no error line."""
    bare_f = _make_repo_remote(
        tmp_path,
        "fixture",
        plans={ORBIT_TOPIC: ORBIT_PLAN},
        broken=True,
    )
    bare_p = _make_prompts_remote(tmp_path)
    config = _config(
        base_config,
        allowed_repos=[FIX],
        repo_urls={FIX: str(bare_f)},
        listing_repo_url=str(bare_p),
    )
    state_dir = tmp_path / "state"
    clock = Clock(DAY_1200)

    r1 = _wf(config, clock=clock, runner=FakeRunner({}), active=ActiveFlag(0)).run(
        _ctx(config, state_dir, gate_open=False)
    )
    assert r1.status == "ok"
    assert r1.errors == []
    assert r1.items_found == 1
    listing = _bare_file(bare_p, LISTING_BRANCH, LISTING_PATH) or ""
    assert "broken" not in listing
    assert len(_state(_ctx(config, state_dir))["plans"]) == 1


# --- AC11: no double-flight (5 plans, night) -------------------------------------------- #


def test_ac11_no_double_flight_five_plans(base_config: Config, tmp_path: Path) -> None:
    """[AC11] 5 approved plans at night (2 slots) → at no moment is the same identity
    in flight twice; all 5 run exactly once each."""
    plans = {f"p{n}": f"# P{n} plan\n\nPlan {n}.\n" for n in range(1, 6)}
    bare_f = _make_repo_remote(tmp_path, "fixture", plans=plans)
    bare_p = _make_prompts_remote(tmp_path)
    config = _config(
        base_config,
        allowed_repos=[FIX],
        repo_urls={FIX: str(bare_f)},
        listing_repo_url=str(bare_p),
    )
    state_dir = tmp_path / "state"
    clock = Clock(NIGHT_2330)

    r1 = _wf(config, clock=clock, runner=FakeRunner({}), active=ActiveFlag(0)).run(
        _ctx(config, state_dir, gate_open=False)
    )
    assert r1.status == "ok" and r1.items_found == 5
    idents = _identities_for(plans)
    edits = {
        f"planning/{topic}/work_plan.md": {"approval": True, "priority": n}
        for n, topic in enumerate(sorted(idents), start=1)
    }
    _user_edit_listing(tmp_path, bare_p, "approve", edits)

    scripts = {ident: [ok_result("success")] for ident in idents.values()}
    runner = FakeRunner(scripts, hold_seconds=0.4)
    r2 = _wf(config, clock=clock, runner=runner, active=ActiveFlag(0)).run(
        _ctx(config, state_dir, gate_open=True)
    )

    assert r2.status == "ok"
    assert len(runner.calls) == 5  # every plan ran exactly once
    assert runner.max_concurrency == 2  # the night slots
    assert runner.double_flight == []  # never the same identity twice
    seq = [ident for _, ident in runner.events]
    assert sorted(seq) == sorted([ident for ident in idents.values() for _ in (0, 1)])
    assert all(
        _state(_ctx(config, state_dir))["plans"][ident]["state"] == "success"
        for ident in idents.values()
    )
    assert len(_attempt_branches(bare_f)) == 5


# --- AC12: state atomics --------------------------------------------------------------- #


def test_ac12_state_file_after_every_transition(base_config: Config, tmp_path: Path) -> None:
    """[AC12a] the state file on disk reflects the new state after every job
    transition (snapshotted at each job start: the previous job is already routed)."""
    bare_f = _make_repo_remote(tmp_path, "fixture", plans={"alpha": ALPHA_PLAN, "beta": BETA_PLAN})
    bare_p = _make_prompts_remote(tmp_path)
    config = _config(
        base_config,
        allowed_repos=[FIX],
        repo_urls={FIX: str(bare_f)},
        listing_repo_url=str(bare_p),
    )
    state_dir = tmp_path / "state"
    state_file = state_dir / "roadmap-dev.json"
    clock = Clock(DAY_1200)

    r1 = _wf(config, clock=clock, runner=FakeRunner({}), active=ActiveFlag(0)).run(
        _ctx(config, state_dir, gate_open=False)
    )
    assert r1.status == "ok"
    idents = _identities_for({"alpha": ALPHA_PLAN, "beta": BETA_PLAN})
    i_a, i_b = idents["alpha"], idents["beta"]
    _user_edit_listing(
        tmp_path,
        bare_p,
        "approve",
        {
            "planning/alpha/work_plan.md": {"approval": True, "priority": 1},
            "planning/beta/work_plan.md": {"approval": True, "priority": 2},
        },
    )

    runner = FakeRunner(
        {i_a: [ok_result("success")], i_b: [ok_result("success")]},
        state_file=state_file,
    )
    r2 = _wf(config, clock=clock, runner=runner, active=ActiveFlag(0)).run(
        _ctx(config, state_dir, gate_open=True)
    )
    assert r2.status == "ok"

    # Snapshot at job 1's start: it is pending (persisted before spawn), job 2 open.
    snap0 = runner.state_snapshots[0]
    assert snap0["plans"][i_a]["state"] == "pending"
    assert snap0["plans"][i_b]["state"] == "open"
    # Snapshot at job 2's start: job 1 is already routed success (with its sha).
    snap1 = runner.state_snapshots[1]
    assert snap1["plans"][i_a]["state"] == "success"
    assert snap1["plans"][i_a]["commit_sha"]
    assert snap1["plans"][i_a]["finished_at"] is not None
    assert snap1["plans"][i_b]["state"] == "pending"
    # Final on-disk document: both success.
    final = json.loads(state_file.read_text(encoding="utf-8"))
    assert final["plans"][i_a]["state"] == "success"
    assert final["plans"][i_b]["state"] == "success"


def test_ac12_mid_drain_crash_leaves_valid_state(base_config: Config, tmp_path: Path) -> None:
    """[AC12b] a runner crash mid-drain (after job 1's ``pending`` persist) aborts
    the run but leaves a VALID JSON state file with the pending entry for the reaper
    (no torn write)."""
    bare_f = _make_repo_remote(tmp_path, "fixture", plans={"alpha": ALPHA_PLAN, "beta": BETA_PLAN})
    bare_p = _make_prompts_remote(tmp_path)
    config = _config(
        base_config,
        allowed_repos=[FIX],
        repo_urls={FIX: str(bare_f)},
        listing_repo_url=str(bare_p),
    )
    state_dir = tmp_path / "state"
    state_file = state_dir / "roadmap-dev.json"
    clock = Clock(DAY_1200)

    r1 = _wf(config, clock=clock, runner=FakeRunner({}), active=ActiveFlag(0)).run(
        _ctx(config, state_dir, gate_open=False)
    )
    assert r1.status == "ok"
    idents = _identities_for({"alpha": ALPHA_PLAN, "beta": BETA_PLAN})
    i_a, i_b = idents["alpha"], idents["beta"]
    _user_edit_listing(
        tmp_path,
        bare_p,
        "approve",
        {
            "planning/alpha/work_plan.md": {"approval": True, "priority": 1},
            "planning/beta/work_plan.md": {"approval": True, "priority": 2},
        },
    )

    # The runner raises on its FIRST call (job 1 = alpha, priority 1).
    runner = FakeRunner(
        {i_a: [ok_result("success")], i_b: [ok_result("success")]},
        raise_after=1,
    )
    r2 = _wf(config, clock=clock, runner=runner, active=ActiveFlag(0)).run(
        _ctx(config, state_dir, gate_open=True)
    )

    # The run aborted loudly (the dead worker is an infrastructure error).
    assert r2.status == "error"
    assert any("worker thread died" in err for err in r2.errors)
    # The state file is valid JSON (atomic save — no torn write) with the pending
    # entry for the reaper (job 2 was never started).
    doc = json.loads(state_file.read_text(encoding="utf-8"))
    assert doc["version"] == 1
    assert doc["plans"][i_a]["state"] == "pending"
    assert doc["plans"][i_a]["branch_name"] == f"roadmap-dev/{i_a}-1"
    assert doc["plans"][i_b]["state"] == "open"
    # And the reaper picks it up on the next run (AC7's path).
    r3 = _wf(config, clock=clock, runner=FakeRunner({}), active=ActiveFlag(0)).run(
        _ctx(config, state_dir, gate_open=False)
    )
    assert r3.status == "ok"
    assert f"reaped orphan {i_a} (pending -> open)" in r3.actions
    assert _state(_ctx(config, state_dir))["plans"][i_a]["state"] == "open"
