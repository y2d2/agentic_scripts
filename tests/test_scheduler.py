"""Hermetic tests for the scheduler run loop (``run``), CLI surface, and registry.

All gate inputs are injected (``now``/``load``) so no real clock or host load is consulted.
Concurrency and kill-mid-run tests spawn subprocesses that import ``run`` with a slow test
workflow registered via a tmp module on ``sys.path`` (referenced in a tmp config), proving
"adding a workflow = new module + config entry, zero scheduler changes".
"""

from __future__ import annotations

import copy
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest
import yaml

from agentic_scripts.scheduler import run

REPO_ROOT = Path(__file__).resolve().parents[1]
SHIPPED_CONFIG = REPO_ROOT / "config" / "workflows.yaml"


def _write_config(
    tmp_path: Path,
    state_dir: Path,
    log_dir: Path,
    sandbox_dir: Path,
    *,
    workflows: dict | None = None,
    extra_machine: dict | None = None,
) -> Path:
    """Write a tmp copy of the shipped config pointed at the given dirs and return its path.

    Args:
        tmp_path: pytest temp dir to hold the YAML file.
        state_dir/log_dir/sandbox_dir: Absolute dirs for the ``paths`` section.
        workflows: Optional override mapping for the ``workflows`` section (defaults to
            the shipped single ``noop`` entry).
        extra_machine: Optional dict merged into the ``machine`` section.

    Returns:
        The path of the written config file.
    """
    data = copy.deepcopy(yaml.safe_load(SHIPPED_CONFIG.read_text(encoding="utf-8")))
    data["paths"] = {
        "state_dir": str(state_dir),
        "log_dir": str(log_dir),
        "sandbox_dir": str(sandbox_dir),
    }
    if workflows is not None:
        data["workflows"] = workflows
    if extra_machine is not None:
        data["machine"].update(extra_machine)
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


def _dir_kwargs(dirs: dict[str, Path]) -> dict[str, Path]:
    """Map a ``{state, logs, sandbox}`` dirs dict to ``_write_config`` keyword names."""
    return {
        "state_dir": dirs["state"],
        "log_dir": dirs["logs"],
        "sandbox_dir": dirs["sandbox"],
    }


# --------------------------------------------------------------------------- #
# In-process run-loop tests (injected now/load)                                #
# --------------------------------------------------------------------------- #


def test_gate_closed_noop(tmp_path: Path) -> None:
    """1. Gate-closed no-op: out-of-window now → 0 in <5s, CLOSED log, no noop state."""
    dirs = {n: tmp_path / n for n in ("state", "logs", "sandbox")}
    for d in dirs.values():
        d.mkdir(parents=True)
    cfg = _write_config(tmp_path, **_dir_kwargs(dirs))

    now = datetime(2026, 10, 20, 13, 0)  # local 13:00 — outside the window
    t0 = time.monotonic()
    code = run(["run", "--config", str(cfg)], now=now, load=(0.5, 0.5, 0.5))
    elapsed = time.monotonic() - t0

    assert code == 0
    assert elapsed < 5.0
    logs = _run_logs(dirs["logs"])
    assert len(logs) == 1
    log_text = logs[0].read_text(encoding="utf-8")
    assert "verdict=CLOSED" in log_text
    assert (dirs["logs"] / "last-run.txt").is_file()
    # No workflow side effects: the noop state file must NOT have been created.
    assert not (dirs["state"] / "noop.json").exists()


def test_forced_open_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """2. Forced open run: --force → 0; RUN START force=True, WORKFLOW ok, gate=forced."""
    # Task 4 follow-up (additive): the shipped config now has mail-keeper enabled, so a
    # forced run would otherwise start a LIVE BACKFILL (real agent over real history). Point
    # MAIL_INDEX_DB at a nonexistent tmp path so the workflow lands status=skipped (index
    # missing) — no canary walk, no agent. Mirrors Task 3b's base-smoke env isolation.
    monkeypatch.setenv("MAIL_INDEX_DB", str(tmp_path / "no-such-index"))
    dirs = {n: tmp_path / n for n in ("state", "logs", "sandbox")}
    for d in dirs.values():
        d.mkdir(parents=True)
    cfg = _write_config(tmp_path, **_dir_kwargs(dirs))

    now = datetime(2026, 10, 20, 13, 0)  # even out-of-window; --force bypasses the gate
    code = run(["run", "--force", "--config", str(cfg)], now=now, load=(99.0, 99.0, 99.0))

    assert code == 0
    log_text = _run_logs(dirs["logs"])[0].read_text(encoding="utf-8")
    assert "RUN START force=True" in log_text
    assert "WORKFLOW noop status=ok" in log_text
    assert "RUN END gate=forced" in log_text

    noop_state = json.loads((dirs["state"] / "noop.json").read_text(encoding="utf-8"))
    assert noop_state["runs"] == 1
    assert "trigger: force" in _last_run(dirs["logs"])


def test_two_step_gate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """3. Two-step gate: poll 1 closed, poll 2 (T+30min) open and runs noop."""
    # Task 4 follow-up (additive): the shipped config now has mail-keeper enabled, so a
    # gate-open run would otherwise start a LIVE BACKFILL (real agent over real history).
    # Point MAIL_INDEX_DB at a nonexistent tmp path so the workflow lands status=skipped
    # (index missing) — no canary walk, no agent. Mirrors Task 3b's base-smoke env isolation.
    monkeypatch.setenv("MAIL_INDEX_DB", str(tmp_path / "no-such-index"))
    dirs = {n: tmp_path / n for n in ("state", "logs", "sandbox")}
    for d in dirs.values():
        d.mkdir(parents=True)
    cfg = _write_config(tmp_path, **_dir_kwargs(dirs))

    t1 = datetime(2026, 10, 20, 22, 0)  # inside the window, idle
    code1 = run(["run", "--config", str(cfg)], now=t1, load=(0.5, 0.5, 0.5), run_id="poll-1")
    assert code1 == 0
    log1 = _run_logs(dirs["logs"])[0].read_text(encoding="utf-8")
    assert "verdict=CLOSED" in log1
    assert "1st idle poll recorded" in log1

    t2 = t1 + timedelta(minutes=30)  # within 30+10 tolerance → opens
    code2 = run(["run", "--config", str(cfg)], now=t2, load=(0.5, 0.5, 0.5), run_id="poll-2")
    assert code2 == 0
    logs = _run_logs(dirs["logs"])
    assert len(logs) == 2
    log2 = logs[1].read_text(encoding="utf-8")
    assert "verdict=OPEN" in log2
    assert "WORKFLOW noop status=ok" in log2


def test_only_unknown_returns_2(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    """7. --only with an unknown workflow name → exit 2; the name is surfaced."""
    dirs = {n: tmp_path / n for n in ("state", "logs", "sandbox")}
    for d in dirs.values():
        d.mkdir(parents=True)
    cfg = _write_config(tmp_path, **_dir_kwargs(dirs))

    code = run(
        ["run", "--force", "--only", "does_not_exist", "--config", str(cfg)],
        now=datetime(2026, 10, 20, 23, 0),
        load=(0.5, 0.5, 0.5),
    )
    assert code == 2
    captured = capsys.readouterr()
    log_text = _run_logs(dirs["logs"])[0].read_text(encoding="utf-8")
    # The offending name must appear in the run log (or stderr).
    assert "does_not_exist" in log_text or "does_not_exist" in captured.err


def test_bare_invocation_returns_2(capsys: pytest.CaptureFixture) -> None:
    """8. Bare invocation / no subcommand → run([]) returns 2 (help shown)."""
    code = run([])
    assert code == 2
    captured = capsys.readouterr()
    # Help is printed to stdout by argparse.
    assert "usage" in captured.out.lower()


# --------------------------------------------------------------------------- #
# Subprocess tests: concurrency, registry extensibility, kill mid-run          #
# --------------------------------------------------------------------------- #

SLOW_WF_SOURCE = '''
"""A slow test workflow used to exercise lock exclusion and kill-mid-run."""
import time

from agentic_scripts.workflows.base import WorkflowResult


class SlowWorkflow:
    """A workflow that sleeps then reports ok (to hold the lock across a delay)."""

    name = "slow_wf"

    def run(self, ctx):
        time.sleep(3)
        return WorkflowResult(status="ok", items_found=0, actions=["slow done"])


def create(config):
    """Return a :class:`SlowWorkflow` instance (required workflow entry point)."""
    return SlowWorkflow()
'''

DRIVER_SOURCE = """
import sys

from agentic_scripts.scheduler import run

if __name__ == "__main__":
    sys.exit(run(sys.argv[1:]))
"""


def _write_slow_pkg(tmp_path: Path) -> None:
    """Write a ``test_slow_pkg`` package (with a slow ``slow_wf`` module) under ``tmp_path``.

    The config loader rejects single-word module names, so the slow workflow lives in a
    dotted package (``test_slow_pkg.slow_wf``). The package dir is added to PYTHONPATH by
    :func:`_spawn` for subprocess runs and to ``sys.path`` for in-process re-runs.
    """
    pkg = tmp_path / "test_slow_pkg"
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "slow_wf.py").write_text(SLOW_WF_SOURCE, encoding="utf-8")


def _slow_wf_workflows(tmp_path: Path) -> dict:
    """Return a workflows mapping with the shipped noop plus the tmp slow_wf module."""
    return {
        "noop": {"enabled": True, "module": "agentic_scripts.workflows.noop", "agent": None},
        "slow_wf": {"enabled": True, "module": "test_slow_pkg.slow_wf", "agent": None},
    }


def _spawn(cfg: Path, tmp_path: Path, extra: list[str] | None = None) -> subprocess.Popen:
    """Spawn a subprocess that imports ``run`` with the slow-wf module on sys.path."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(tmp_path) + os.pathsep + env.get("PYTHONPATH", "")
    driver = tmp_path / "driver.py"
    driver.write_text(DRIVER_SOURCE, encoding="utf-8")
    cmd = [sys.executable, str(driver), "run", "--force", "--config", str(cfg)]
    if extra:
        cmd += extra
    return subprocess.Popen(
        cmd,
        cwd=REPO_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def test_registry_extensibility_and_concurrency(tmp_path: Path) -> None:
    """4+5. Two concurrent forced runs → exactly one RUN END, one SKIP; both workflows run."""
    dirs = {n: tmp_path / n for n in ("state", "logs", "sandbox")}
    for d in dirs.values():
        d.mkdir(parents=True)
    _write_slow_pkg(tmp_path)
    cfg = _write_config(tmp_path, **_dir_kwargs(dirs), workflows=_slow_wf_workflows(tmp_path))

    # Spawn two concurrent forced runs; the second must skip (lock held by the first).
    p1 = _spawn(cfg, tmp_path)
    time.sleep(0.6)  # let p1 acquire the lock and start its slow workflow
    p2 = _spawn(cfg, tmp_path)

    out1, err1 = p1.communicate(timeout=30)
    out2, err2 = p2.communicate(timeout=30)
    assert p1.returncode == 0
    assert p2.returncode == 0

    logs = _run_logs(dirs["logs"])
    all_text = "\n".join(log.read_text(encoding="utf-8") for log in logs)
    # Exactly one run completed (one RUN END); the other skipped.
    assert all_text.count("RUN END") == 1
    assert all_text.count("SKIP another run is in progress") == 1

    # The completed run executed both workflows, in config order (noop before slow_wf).
    end_log = max(logs, key=lambda p: len(p.read_text(encoding="utf-8")))
    text = end_log.read_text(encoding="utf-8")
    assert "WORKFLOW noop status=ok" in text
    assert "WORKFLOW slow_wf status=ok" in text
    assert text.index("WORKFLOW noop") < text.index("WORKFLOW slow_wf")


def test_kill_mid_run_no_torn_state(tmp_path: Path) -> None:
    """6. Kill -9 mid-run → process gone; any state file is valid JSON; re-run succeeds."""
    dirs = {n: tmp_path / n for n in ("state", "logs", "sandbox")}
    for d in dirs.values():
        d.mkdir(parents=True)
    _write_slow_pkg(tmp_path)
    cfg = _write_config(tmp_path, **_dir_kwargs(dirs), workflows=_slow_wf_workflows(tmp_path))

    proc = _spawn(cfg, tmp_path)
    time.sleep(1.0)  # let it start (noop done, slow_wf sleeping)
    os.kill(proc.pid, signal.SIGKILL)
    proc.wait(timeout=10)
    assert proc.returncode != 0  # killed by signal

    # Any state file that exists must parse as valid JSON (atomic save — never torn).
    for state_file in list(dirs["state"].glob("*.json")):
        json.loads(state_file.read_text(encoding="utf-8"))

    # A fresh forced run succeeds (exit 0) and completes both workflows. The tmp package
    # must be importable in-process, so add it to sys.path for this call only.
    sys.path.insert(0, str(tmp_path))
    try:
        code = run(
            ["run", "--force", "--config", str(cfg)],
            now=datetime(2026, 10, 20, 23, 0),
            load=(0.5, 0.5, 0.5),
            run_id="rerun-after-kill",
        )
    finally:
        sys.path.remove(str(tmp_path))
    assert code == 0
    log_text = _run_logs(dirs["logs"])[-1].read_text(encoding="utf-8")
    assert "RUN END" in log_text
