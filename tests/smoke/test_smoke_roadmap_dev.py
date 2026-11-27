"""Run()-level hermetic smoke tests for the roadmap-dev workflow.

These prove the shipped, registered ``roadmap-dev`` entry (``enabled: true``,
``gate: idle``) end-to-end through a real in-process :func:`agentic_scripts.scheduler.run`
against a tmp workspace with a copy of the shipped config pointed at it. They cover the
base paths only:

  * the forced run no-ops cleanly with the shipped ``roadmap_prompts.allowed_repos``
    seeded empty (exactly ONE roadmap-dev action, no state file, no sandbox dir);
  * a non-forced run evaluates the idle gate — with the canned 0-active-session probe
    it records its 1st poll (``idle_gate_last_ok``) and still runs the workflow
    (Phase-1 no-op; the quiet-gate workflows are individually skipped);
  * a 2nd idle poll 30 min later (within the poll tolerance) opens the idle gate
    (``verdict=OPEN`` + the canonical 2nd-poll reason line, grepped from the run log);
  * active sessions (probe → 2) with the streak seeded → the idle gate closes AND
    clears the streak, and the workflow — now past its empty-allowlist shortcut —
    appends the exact gate-closed drain note instead of a drain start;
  * a malformed ``roadmap_prompts`` section fails fast at config load (exit 2, field
    named on stderr);
  * the header-only listing stub parses as a valid EMPTY listing
    (``parse_listing`` → ``[]``).

Unlike the other smoke modules, the config copy here deliberately KEEPS the roadmap-dev
entry — it is the subject under test. Hermeticity then comes from three other guards:
(1) ``allowed_repos`` is seeded ``[]`` (or pointed at LOCAL bare-repo fixtures), so the
workflow can never reach GitHub; (2) ``local_listing`` is set to ``null`` — this repo's
local listing mirror would otherwise write a file and an extra action note mid-test (the
mirror itself is covered by section G of ``tests/test_roadmap_dev.py``); and (3) the
``_isolate_mail_env`` autouse fixture keeps the shipped ``mail-keeper`` entry inert
(nonexistent MAIL_* paths → ``skipped``), exactly the pattern in
:mod:`tests.smoke.test_smoke_base`. The shipped ``oc-todo`` entry needs no isolation
(``repos: []`` → no-op scan).

Idle-probe seam (what we patch, and why): the scheduler calls the probe at its own
import site — ``agentic_scripts.scheduler.read_active_sessions`` (the name bound when
``scheduler`` is imported) — so the tests monkeypatch THAT name with a lambda returning
a canned session count (0 or 2). This keeps the tests free of the real OpenCode service:
neither ``sessions.read_service_state`` (the ``~/.local/state/opencode/service.json``
read) nor ``sessions._urlopen`` (the HTTP GET against the live service) is reached. The
suite-wide autouse probe in ``tests/smoke/conftest.py`` already answers 0; the per-test
patch below takes effect where a test needs a different count (same ``monkeypatch``
instance, LIFO undo).

The sessions-active drain test drives a REAL phase-1 scan against LOCAL bare-repo
fixtures (the ``repo_urls`` / ``listing_repo_url`` overrides — this repo's hermetic-test
seam): a plain ``git clone`` of a local path, no network, no ``GITHUB_PAT`` (the git
identity is set by an autouse fixture and ``GITHUB_PAT`` is unset for every test here).
With the streak seeded and the probe reporting 2 active sessions, the idle gate closes
(streak cleared) and the workflow runs with ``gate_open=False`` — the gate-closed
drain note, never a drain start.

``last-run.txt`` carries only the FIRST executed workflow's summary line (multi-workflow
scheduler convention — that is ``noop`` here), so roadmap-dev per-workflow assertions
are made against the run log (``WORKFLOW roadmap-dev status=…``), not last-run.
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

import pytest
import yaml

from agentic_scripts.scheduler import run
from agentic_scripts.workflows.roadmap_dev import parse_listing

REPO_ROOT = Path(__file__).resolve().parents[2]
SHIPPED_CONFIG = REPO_ROOT / "config" / "workflows.yaml"

#: The single allowed repo in the sessions-active drain test (a local bare-remote fixture).
FIX = "owner/fixture"

#: The header-only listing stub: the 4-line ``# plans — roadmap-dev listing`` header a
#: fresh listing starts with — no ``# <repo>`` / ``## <branch>`` sections, so
#: :func:`parse_listing` yields an empty list.
_EMPTY_LISTING_STUB = (
    "# plans — roadmap-dev listing\n"
    "\n"
    "Reconciled automatically by the agentic_scripts `roadmap-dev` workflow (see README).\n"
    "Sections (`# <repo>` / `## <branch>`) appear as plans are discovered.\n"
)


def _write_config(
    tmp_path: Path, state_dir: Path, log_dir: Path, sandbox_dir: Path, *, mirror_off: bool = True
) -> Path:
    """Write a tmp copy of the shipped config pointed at the given dirs and return its path.

    Unlike the other smoke modules the roadmap-dev entry is KEPT (subject under test);
    hermeticity comes from the seeded-empty ``allowed_repos`` (no repo can be cloned)
    and — with ``mirror_off`` — ``local_listing: null`` so the local listing mirror
    never writes during these tests (see the module docstring).

    Args:
        tmp_path: pytest temp dir to hold the YAML file.
        state_dir/log_dir/sandbox_dir: Absolute dirs for the ``paths`` section.
        mirror_off: When True (default), set ``roadmap_prompts.local_listing`` to null.

    Returns:
        The path of the written config file.
    """
    data = yaml.safe_load(SHIPPED_CONFIG.read_text(encoding="utf-8"))
    data["paths"] = {
        "state_dir": str(state_dir),
        "log_dir": str(log_dir),
        "sandbox_dir": str(sandbox_dir),
    }
    # hermetic: shipped allowlist is seeded; tests exercise scheduler/gate behavior, not scanning
    data["roadmap_prompts"]["allowed_repos"] = []
    if mirror_off:
        data["roadmap_prompts"]["local_listing"] = None
    cfg_path = tmp_path / "workflows.yaml"
    cfg_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return cfg_path


def _run_logs(log_dir: Path) -> list[Path]:
    """Return all ``run-*.log`` files in a log dir, sorted by name."""
    return sorted(log_dir.glob("run-*.log"))


def _last_run(log_dir: Path) -> str:
    """Return the contents of ``logs/last-run.txt`` (empty string if absent)."""
    path = log_dir / "last-run.txt"
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def _scheduler_state(state_dir: Path) -> dict:
    """Return the parsed ``state/scheduler.json`` document (``{}`` when absent)."""
    path = state_dir / "scheduler.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def _workspace(tmp_path: Path) -> tuple[Path, dict[str, Path]]:
    """Create isolated state/log/sandbox dirs and a tmp config pointed at them.

    Returns:
        A tuple of the config path and a ``{state, logs, sandbox}`` dirs mapping.
    """
    dirs = {name: tmp_path / name for name in ("state", "logs", "sandbox")}
    for path in dirs.values():
        path.mkdir(parents=True, exist_ok=True)
    cfg = _write_config(tmp_path, dirs["state"], dirs["logs"], dirs["sandbox"])
    return cfg, dirs


@pytest.fixture(autouse=True)
def _isolate_mail_env(tmp_path: Path) -> None:
    """Point MAIL_* env at nonexistent per-test tmp paths (shipped mail-keeper stays inert).

    The shipped config also registers ``mail-keeper``, and this module's config copy is
    NOT stripped — so a forced run would drive the LIVE mail-keeper (real notmuch index
    + real agent) without this isolation. Pointing ``MAIL_INDEX_DB`` at a nonexistent
    tmp path makes it return ``skipped``; ``MAIL_PROCESSED_LOG`` at a tmp path keeps the
    production log untouched (same pattern as :mod:`tests.smoke.test_smoke_base`).
    """
    os.environ["MAIL_INDEX_DB"] = str(tmp_path / "no-such-index")
    os.environ["MAIL_PROCESSED_LOG"] = str(tmp_path / "no-such-log.jsonl")


@pytest.fixture(autouse=True)
def _git_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set the git identity for fixture commits and unset GITHUB_PAT (hermetic clones).

    The sessions-active drain test builds local bare-repo fixtures (fixture commits)
    and the workflow clones them over the local protocol — no credentials involved.
    ``GITHUB_PAT`` is unset so no test in this module can accidentally route git auth
    through a real token (the suite's acceptance runs under ``env -u GITHUB_PAT``).
    """
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Test Author")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "author@example.test")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "Test Committer")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "committer@example.test")
    monkeypatch.delenv("GITHUB_PAT", raising=False)


def _git(path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run a raw git command in ``path`` (fixture setup helper)."""
    return subprocess.run(
        ["git", "-C", str(path), *args], capture_output=True, text=True, check=True
    )


def _bare_remote(tmp_path: Path, name: str, files: dict[str, str]) -> Path:
    """Build a local bare remote with one commit on ``main`` carrying ``files``.

    A bare repo serves as the "remote" (local-protocol clone, no auth) — the same
    hermetic pattern as :mod:`tests.test_roadmap_dev_pipeline`.

    Args:
        tmp_path: The pytest temp dir (source + bare live under it).
        name: A label for the src/bare dirs.
        files: Repo-relative path -> file text for the single commit
            (e.g. ``{"plans.md": ""}`` for an empty listing file).

    Returns:
        The bare remote path (used as a clone URL in the config).
    """
    src = tmp_path / f"src-{name}"
    src.mkdir()
    _git(src, "init", "-b", "main")
    for rel, text in sorted(files.items()):
        target = src / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    _git(src, "add", "-A")
    _git(src, "commit", "-m", f"fixture {name}")
    bare = tmp_path / f"{name}.git"
    bare.mkdir()
    _git(bare, "init", "--bare")
    _git(bare, "symbolic-ref", "HEAD", "refs/heads/main")
    _git(src, "remote", "add", "origin", str(bare))
    _git(src, "push", "-q", "-u", "origin", "main")
    return bare


def test_smoke_roadmap_dev_registered_noop(tmp_path: Path) -> None:
    """Forced run with the shipped config (seeded-empty allowlist) → roadmap-dev no-ops."""
    cfg, dirs = _workspace(tmp_path)

    code = run(
        ["run", "--force", "--config", str(cfg)],
        now=datetime(2026, 11, 21, 13, 0),  # --force bypasses the gates
        load=(99.0, 99.0, 99.0),
        run_id="rd-smoke-1",
    )

    assert code == 0
    log_text = _run_logs(dirs["logs"])[0].read_text(encoding="utf-8")
    # The no-repos path: 1 action, 0 items, 0 errors — asserted on the run log
    # (last-run carries only the FIRST workflow's summary, which is noop here).
    assert "WORKFLOW roadmap-dev status=ok items_found=0 actions=1 errors=0" in log_text

    last = _last_run(dirs["logs"])
    assert "trigger: force" in last
    assert "overall: ok" in last

    # No side effects: no sandbox/roadmap-dev dir and no state file (a no-op run saves nothing).
    assert not (dirs["sandbox"] / "roadmap-dev").exists()
    assert not (dirs["state"] / "roadmap-dev.json").exists()
    # The mirror is switched off in this module's config — nothing at the tmp root either.
    assert not (tmp_path / "plans.md").exists()


def test_smoke_roadmap_dev_idle_gate_first_poll(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Non-forced run → idle gate records its 1st poll; roadmap-dev still invoked.

    The non-forced run evaluates the idle gate (canned probe: 0 active sessions) and
    records its 1st poll, then the (inert) roadmap-dev workflow no-ops with
    ``gate_open=False`` — the run ENTERED the workflow, not a blanket skip.
    """
    cfg, dirs = _workspace(tmp_path)
    # Canned probe: 0 active sessions (never touches the real service — module docstring).
    monkeypatch.setattr("agentic_scripts.scheduler.read_active_sessions", lambda: 0)

    code = run(
        ["run", "--config", str(cfg)],
        now=datetime(2026, 11, 21, 13, 0),
        load=(0.5, 0.5, 0.5),
        run_id="rd-smoke-2",
    )

    assert code == 0
    log_text = _run_logs(dirs["logs"])[0].read_text(encoding="utf-8")
    assert "active_sessions=0" in log_text
    assert "reason=no active sessions (1st idle poll recorded)" in log_text

    # The workflow loop ENTERED: roadmap-dev is invoked (Phase-1 no-op).
    assert "WORKFLOW roadmap-dev status=ok items_found=0 actions=1 errors=0" in log_text

    # State: the idle gate recorded its 1st poll.
    sched = _scheduler_state(dirs["state"])
    assert isinstance(sched.get("idle_gate_last_ok"), str)

    last = _last_run(dirs["logs"])
    assert "trigger: gate" in last
    assert "overall: ok" in last

    # The inert workflow leaves no side effects (no state file, no sandbox dir).
    assert not (dirs["state"] / "roadmap-dev.json").exists()
    assert not (dirs["sandbox"] / "roadmap-dev").exists()


def test_smoke_roadmap_dev_idle_gate_second_poll_opens(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """2nd idle poll 30 min later (within tolerance) → the idle gate OPENS (log-grepped).

    Continues the first-poll world: with the recorded 1st-poll state present and ``now``
    advanced by ``poll_interval_minutes`` (30), the same non-forced run opens the idle
    gate (``verdict=OPEN reason=no active sessions (2nd consecutive idle poll)``) and
    runs roadmap-dev again.
    """
    cfg, dirs = _workspace(tmp_path)
    monkeypatch.setattr("agentic_scripts.scheduler.read_active_sessions", lambda: 0)

    t1 = datetime(2026, 11, 21, 13, 0)
    code1 = run(["run", "--config", str(cfg)], now=t1, load=(0.5, 0.5, 0.5), run_id="rd-smoke-3a")
    assert code1 == 0
    log1 = _run_logs(dirs["logs"])[0].read_text(encoding="utf-8")
    assert "reason=no active sessions (1st idle poll recorded)" in log1
    first_poll = _scheduler_state(dirs["state"])["idle_gate_last_ok"]
    assert isinstance(first_poll, str)

    t2 = t1 + timedelta(minutes=30)  # == poll_interval_minutes; within 30+10 tolerance
    code2 = run(["run", "--config", str(cfg)], now=t2, load=(0.5, 0.5, 0.5), run_id="rd-smoke-3b")
    assert code2 == 0
    log2 = _run_logs(dirs["logs"])[1].read_text(encoding="utf-8")

    # The gate OPENED: the canonical GATE line with the 2nd-poll reason (grep the run log).
    assert "active_sessions=0" in log2
    assert "verdict=OPEN" in log2
    assert "reason=no active sessions (2nd consecutive idle poll)" in log2
    # roadmap-dev runs again (an idle-gate workflow runs on every non-skipped fire).
    assert "WORKFLOW roadmap-dev status=ok items_found=0 actions=1 errors=0" in log2

    # The opening poll keeps the 1st-poll timestamp (it is not overwritten — the gate
    # opens ON that streak) — the key is present, not cleared.
    sched = _scheduler_state(dirs["state"])
    assert sched.get("idle_gate_last_ok") == first_poll

    # The inert workflow still leaves no side effects (empty allowlist).
    assert not (dirs["state"] / "roadmap-dev.json").exists()
    assert not (dirs["sandbox"] / "roadmap-dev").exists()


def test_smoke_roadmap_dev_sessions_active_no_drain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Seeded streak + 2 active sessions → idle gate closed (streak cleared), no drain start.

    The allowlist points at LOCAL bare-repo fixtures (one allowed repo + the listing
    repo), so this run drives a REAL phase-1 scan (the gate-closed drain note is only
    produced past the empty-allowlist shortcut). The idle streak is seeded 30 min old
    (this fire would open the gate if the box were idle); the canned probe reports 2
    active sessions → the idle gate closes, clears the streak, and roadmap-dev runs with
    ``gate_open=False``: the exact ``drain skipped (idle gate closed)`` note, no
    ``drain start``.
    """
    fixture_bare = _bare_remote(tmp_path, "fixture", {"README.md": "# fixture repo\n"})
    listing_bare = _bare_remote(tmp_path, "listing", {"plans.md": ""})

    dirs = {name: tmp_path / name for name in ("state", "logs", "sandbox")}
    for path in dirs.values():
        path.mkdir(parents=True, exist_ok=True)

    data = yaml.safe_load(SHIPPED_CONFIG.read_text(encoding="utf-8"))
    data["paths"] = {
        "state_dir": str(dirs["state"]),
        "log_dir": str(dirs["logs"]),
        "sandbox_dir": str(dirs["sandbox"]),
    }
    # One allowed repo + the listing repo, both LOCAL bare remotes (the repo_urls /
    # listing_repo_url hermetic-test seam; no network, no credentials). Mirror off so
    # the action count stays exactly the AT-era one (see module docstring).
    data["roadmap_prompts"]["allowed_repos"] = [FIX]
    data["roadmap_prompts"]["repo_urls"] = {FIX: str(fixture_bare)}
    data["roadmap_prompts"]["listing_repo_url"] = str(listing_bare)
    data["roadmap_prompts"]["local_listing"] = None
    cfg_path = tmp_path / "workflows.yaml"
    cfg_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    # Seed the idle streak: a 1st poll 30 min ago → this fire WOULD open the gate if the
    # box were idle. The probe says otherwise: 2 active sessions.
    now = datetime(2026, 11, 21, 13, 0)
    (dirs["state"] / "scheduler.json").write_text(
        json.dumps(
            {
                "idle_gate_last_ok": (now - timedelta(minutes=30)).astimezone().isoformat(),
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("agentic_scripts.scheduler.read_active_sessions", lambda: 2)

    code = run(
        ["run", "--config", str(cfg_path)],
        now=now,
        load=(0.5, 0.5, 0.5),
        run_id="rd-smoke-4",
    )

    assert code == 0
    log_text = _run_logs(dirs["logs"])[0].read_text(encoding="utf-8")
    # The idle gate closed on the active sessions (the seeded streak would have opened it).
    assert "active_sessions=2" in log_text
    assert "reason=2 active session(s)" in log_text
    # Phase 1 really ran against the local fixtures: the scan found 0 plans.
    assert f"roadmap-dev: {FIX} — found 0 plan(s)" in log_text
    # The drain did NOT start: gate_open=False → 3 actions (scan + listing unchanged +
    # the gate-closed drain note), and no drain-start note anywhere.
    assert "WORKFLOW roadmap-dev status=ok items_found=0 actions=3 errors=0" in log_text
    assert "drain start" not in log_text

    # Streak reset: the non-idle poll cleared the idle-gate key to null.
    sched = _scheduler_state(dirs["state"])
    assert sched.get("idle_gate_last_ok") is None
    # The scan cloned the fixture into the sandbox (phase 1 ran)…
    assert (dirs["sandbox"] / "roadmap-dev" / "clones" / "owner__fixture").is_dir()
    # …and the reconciled state was unchanged → no state document was persisted.
    assert not (dirs["state"] / "roadmap-dev.json").exists()


def test_smoke_roadmap_dev_config_fault(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A malformed roadmap_prompts section (allowed_repos a string) → exit 2, field named."""
    dirs = {name: tmp_path / name for name in ("state", "logs", "sandbox")}
    for path in dirs.values():
        path.mkdir(parents=True, exist_ok=True)

    data = yaml.safe_load(SHIPPED_CONFIG.read_text(encoding="utf-8"))
    data["paths"] = {
        "state_dir": str(dirs["state"]),
        "log_dir": str(dirs["logs"]),
        "sandbox_dir": str(dirs["sandbox"]),
    }
    data["roadmap_prompts"]["allowed_repos"] = "owner/name"  # string, not a list → config fault
    cfg_path = tmp_path / "workflows.yaml"
    cfg_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    code = run(["run", "--force", "--config", str(cfg_path)], load=(0.5, 0.5, 0.5))

    assert code == 2
    captured = capsys.readouterr()
    assert "roadmap_prompts.allowed_repos" in captured.err


def test_smoke_roadmap_dev_empty_listing_stub(tmp_path: Path) -> None:
    """The header-only listing stub parses as a valid EMPTY listing (no rows yet)."""
    stub_path = tmp_path / "plans.md"
    stub_path.write_text(_EMPTY_LISTING_STUB, encoding="utf-8")

    rows = parse_listing(stub_path.read_text(encoding="utf-8"))
    assert rows == []  # the stub has no ``# <repo>`` / ``## <branch>`` tables yet
