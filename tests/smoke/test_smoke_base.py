"""End-to-end smoke tests for the agentic_scripts base (scheduler, gate, lock, audit).

These are hermetic: they build a temp workspace under ``tmp_path`` with a copy of the
shipped config pointing at it, and drive ``run()`` in-process with injected clock/load.
No real ``opencode``, no real repos, no network — only the shipped ``noop`` workflow.

Covers the acceptance paths that must hold on any host:
  * gate-closed run exits 0 fast and touches nothing (no workflow side effects);
  * a forced open run executes the registered workflow and is auditable;
  * a concurrent invocation is skipped cleanly (exclusive lock, no deadlock);
  * per-run logs + ``last-run.txt`` are written with the documented fields;
  * re-running is idempotent — state accumulates, never duplicates.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

import yaml

from agentic_scripts.scheduler import acquire_lock, run

REPO_ROOT = Path(__file__).resolve().parents[2]
SHIPPED_CONFIG = REPO_ROOT / "config" / "workflows.yaml"


def _write_config(tmp_path: Path, state_dir: Path, log_dir: Path, sandbox_dir: Path) -> Path:
    """Write a tmp copy of the shipped config pointed at the given dirs and return its path.

    Args:
        tmp_path: pytest temp dir to hold the YAML file.
        state_dir/log_dir/sandbox_dir: Absolute dirs for the ``paths`` section.

    Returns:
        The path of the written config file.
    """
    data = yaml.safe_load(SHIPPED_CONFIG.read_text(encoding="utf-8"))
    data["paths"] = {
        "state_dir": str(state_dir),
        "log_dir": str(log_dir),
        "sandbox_dir": str(sandbox_dir),
    }
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


def test_smoke_gate_closed_noop(tmp_path: Path) -> None:
    """Gate closed (out-of-window now) → exit 0 in <5s, CLOSED log, no side effects."""
    cfg, dirs = _workspace(tmp_path)

    t0 = time.monotonic()
    code = run(
        ["run", "--config", str(cfg)],
        now=datetime(2026, 10, 20, 13, 0),
        load=(0.5, 0.5, 0.5),
    )
    elapsed = time.monotonic() - t0

    assert code == 0
    assert elapsed < 5.0
    log_text = _run_logs(dirs["logs"])[0].read_text(encoding="utf-8")
    assert "verdict=CLOSED" in log_text
    last = _last_run(dirs["logs"])
    assert "trigger: gate" in last
    assert "gate: CLOSED" in last
    # No workflow side effects: the noop state file must NOT have been created.
    assert not (dirs["state"] / "noop.json").exists()


def test_smoke_forced_open_run(tmp_path: Path) -> None:
    """Forced open run → exit 0, workflow ok, auditable last-run with trigger: force."""
    cfg, dirs = _workspace(tmp_path)

    code = run(
        ["run", "--force", "--config", str(cfg)],
        now=datetime(2026, 10, 20, 13, 0),  # even out-of-window; --force bypasses the gate
        load=(99.0, 99.0, 99.0),
    )

    assert code == 0
    log_text = _run_logs(dirs["logs"])[0].read_text(encoding="utf-8")
    assert "RUN START force=True" in log_text
    assert "WORKFLOW noop status=ok" in log_text
    assert "RUN END gate=forced" in log_text

    last = _last_run(dirs["logs"])
    assert "trigger: force" in last
    assert "gate: FORCED" in last
    assert "overall: ok" in last

    noop_state = json.loads((dirs["state"] / "noop.json").read_text(encoding="utf-8"))
    assert noop_state["runs"] == 1


def test_smoke_two_step_gate_opens(tmp_path: Path) -> None:
    """Two consecutive idle polls (~30 min apart) open the gate and run the workflow."""
    cfg, dirs = _workspace(tmp_path)

    t1 = datetime(2026, 10, 20, 22, 0)  # inside the window, idle
    code1 = run(["run", "--config", str(cfg)], now=t1, load=(0.5, 0.5, 0.5), run_id="smoke-poll-1")
    assert code1 == 0
    log1 = _run_logs(dirs["logs"])[0].read_text(encoding="utf-8")
    assert "verdict=CLOSED" in log1
    assert "1st idle poll recorded" in log1

    t2 = t1 + timedelta(minutes=30)  # within 30+10 tolerance → opens
    code2 = run(["run", "--config", str(cfg)], now=t2, load=(0.5, 0.5, 0.5), run_id="smoke-poll-2")
    assert code2 == 0
    log2 = _run_logs(dirs["logs"])[1].read_text(encoding="utf-8")
    assert "verdict=OPEN" in log2
    assert "WORKFLOW noop status=ok" in log2


def test_smoke_lock_exclusivity(tmp_path: Path) -> None:
    """A concurrent invocation while a run is active is skipped (lock held), never deadlocks."""
    cfg, dirs = _workspace(tmp_path)

    # Hold the lock in-process for the duration of the run() call below.
    fd = acquire_lock(dirs["state"])
    assert fd is not None  # fresh dir → lock must be acquirable

    code = run(
        ["run", "--force", "--config", str(cfg)],
        now=datetime(2026, 10, 20, 23, 0),
        load=(0.5, 0.5, 0.5),
        run_id="smoke-locked",
    )

    os.close(fd)  # release the flock (closing releases it; the lock file is not deleted)

    assert code == 0
    log_text = _run_logs(dirs["logs"])[0].read_text(encoding="utf-8")
    assert "SKIP another run is in progress" in log_text


def test_smoke_idempotent_rerun(tmp_path: Path) -> None:
    """Re-running a forced run accumulates state (runs counter), never duplicates or corrupts."""
    cfg, dirs = _workspace(tmp_path)

    now = datetime(2026, 10, 20, 13, 0)
    for i in range(2):
        code = run(
            ["run", "--force", "--config", str(cfg)],
            now=now,
            load=(99.0, 99.0, 99.0),
            run_id=f"smoke-rerun-{i}",
        )
        assert code == 0

    noop_state = json.loads((dirs["state"] / "noop.json").read_text(encoding="utf-8"))
    assert noop_state["runs"] == 2
    # Each run wrote its own log; the last-run summary reflects the most recent run.
    assert len(_run_logs(dirs["logs"])) == 2
    assert "overall: ok" in _last_run(dirs["logs"])
