"""Hermetic tests for AgentRunner — a fake ``opencode`` shim, never the real binary.

The shim is a Python script written to ``tmp_path`` that records its argv (via env
``SHIM_ARGV``) and emits canned NDJSON on stdout based on ``SHIM_MODE``:

- ``happy``: tool_use, step_start, text ("thinking..."), step_finish, text ("FINAL REPORT")
- ``err``: one error event, then exit 1
- ``notext``: step_start + step_finish only, exit 0
- ``sleep``: a text event, then sleep(30) (timeout path)
- ``garbage``: a malformed line before a valid text event

No test in this file can invoke the real ``opencode``: the Config's ``agent.binary``
is always pointed at the shim. Env vars are set per-test and restored afterwards.
"""

from __future__ import annotations

import json
import logging
import os
import stat
import subprocess
import time
from dataclasses import replace
from pathlib import Path

import pytest

from agentic_scripts.agent import AgentRunner
from agentic_scripts.config import Agent, Config, Machine, Paths, QuietWindow

# The shim is a Python script executed directly (Config.agent.binary → execve), so it
# needs a shebang; `python3` on PATH is the system interpreter (never the real opencode).
SHIM_SOURCE = """#!/usr/bin/env python3
import json
import os
import sys
import time


def emit(obj):
    print(json.dumps(obj), flush=True)


mode = os.environ.get("SHIM_MODE", "happy")
argv_path = os.environ.get("SHIM_ARGV")
if argv_path:
    with open(argv_path, "w", encoding="utf-8") as fh:
        json.dump(sys.argv[1:], fh)

if mode == "happy":
    emit({"type": "tool_use", "timestamp": 0, "sessionID": "s1"})
    emit({"type": "step_start", "timestamp": 1, "sessionID": "s1"})
    emit({"type": "text", "timestamp": 2, "sessionID": "s1", "part": {"text": "thinking..."}})
    emit({"type": "step_finish", "timestamp": 3, "sessionID": "s1"})
    emit({"type": "text", "timestamp": 4, "sessionID": "s1", "part": {"text": "FINAL REPORT"}})
elif mode == "err":
    emit({"type": "error", "timestamp": 0, "sessionID": "s1", "error": "shim failure: bad model"})
elif mode == "notext":
    emit({"type": "step_start", "timestamp": 0, "sessionID": "s1"})
    emit({"type": "step_finish", "timestamp": 1, "sessionID": "s1"})
elif mode == "sleep":
    emit({"type": "text", "timestamp": 0, "sessionID": "s1", "part": {"text": "partial"}})
    time.sleep(30)
elif mode == "garbage":
    print("not-json", flush=True)
    emit({"type": "text", "timestamp": 0, "sessionID": "s1", "part": {"text": "after garbage"}})

sys.exit(int(os.environ.get("SHIM_EXIT", "0")))
"""


@pytest.fixture
def shim(tmp_path: Path) -> Path:
    """Write the fake opencode shim into tmp_path and make it executable."""
    path = tmp_path / "fake_opencode"
    path.write_text(SHIM_SOURCE, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


@pytest.fixture
def config(shim: Path) -> Config:
    """A minimal Config whose agent.binary points at the shim (deterministic)."""
    machine = Machine(
        quiet_window=QuietWindow(start="22:00", end="08:00"),
        load_threshold=2.0,
        poll_interval_minutes=30,
        gate_polls_required=2,
        gate_poll_tolerance_minutes=10,
    )
    agent = Agent(
        binary=str(shim),
        model="openaiCompatible/Qwen3.8-27B",
        max_steps=40,
        timeout_minutes=1,
        auto_approve=True,
    )
    paths = Paths(state_dir=Path("/tmp/s"), log_dir=Path("/tmp/l"), sandbox_dir=Path("/tmp/x"))
    return Config(machine=machine, agent=agent, paths=paths, admin_repo=None, workflows=[])


def _run(
    config: Config,
    tmp_path: Path,
    mode: str,
    *,
    timeout_seconds: int | None = None,
) -> tuple[object, Path]:
    """Run the shim-backed AgentRunner in ``mode``; return (result, argv_file).

    The shim's env vars are set for the duration of the run and restored afterwards.
    """
    argv_file = tmp_path / f"argv_{mode}.json"
    work_dir = tmp_path / "work"
    work_dir.mkdir(parents=True, exist_ok=True)
    runner = AgentRunner(config=config, logger=logging.getLogger("test.agent"))

    saved = {k: os.environ.get(k) for k in ("SHIM_MODE", "SHIM_ARGV")}
    os.environ["SHIM_MODE"] = mode
    os.environ["SHIM_ARGV"] = str(argv_file)
    try:
        result = runner.run(
            agent="fake-agent",
            brief="do the thing",
            work_dir=work_dir,
            timeout_seconds=timeout_seconds,
        )
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    return result, argv_file


def test_build_command_exact(config: Config) -> None:
    """Default config (auto_approve=True, model set): exact argv with title; brief last."""
    runner = AgentRunner(config=config)
    cmd = runner.build_command(
        agent="oc-todo-resolver", brief="the brief", work_dir=Path("/tmp/work"), title="t1"
    )
    assert cmd == [
        config.agent.binary,
        "run",
        "--agent",
        "oc-todo-resolver",
        "--format",
        "json",
        "--dir",
        "/tmp/work",
        "--title",
        "t1",
        "--auto",
        "--model",
        config.agent.model,
        "the brief",
    ]


def test_build_command_minimal(config: Config) -> None:
    """model=None, auto_approve=False, no title: those flags absent; brief still last."""
    minimal = replace(config, agent=replace(config.agent, model=None, auto_approve=False))
    runner = AgentRunner(config=minimal)
    cmd = runner.build_command(agent="a", brief="b", work_dir=Path("/w"))
    assert "--title" not in cmd
    assert "--auto" not in cmd
    assert "--model" not in cmd
    assert cmd == [
        minimal.agent.binary,
        "run",
        "--agent",
        "a",
        "--format",
        "json",
        "--dir",
        "/w",
        "b",
    ]


def test_happy_path(config: Config, tmp_path: Path) -> None:
    """Happy mode: ok, exit 0, last text wins, 5 events, exact argv captured."""
    result, argv_file = _run(config, tmp_path, "happy")

    assert result.status == "ok"
    assert result.exit_code == 0
    assert result.final_text == "FINAL REPORT"  # last text event beats "thinking..."
    assert len(result.events) == 5
    assert [e["type"] for e in result.events] == [
        "tool_use",
        "step_start",
        "text",
        "step_finish",
        "text",
    ]
    assert result.error is None
    captured = json.loads(argv_file.read_text(encoding="utf-8"))
    assert captured[-1] == "do the thing"  # positional brief last


def test_error_mode(config: Config, tmp_path: Path) -> None:
    """err mode: status error, exit 1, error payload from the error event."""
    argv_file = tmp_path / "argv_err.json"
    work_dir = tmp_path / "work"
    work_dir.mkdir(parents=True, exist_ok=True)
    runner = AgentRunner(config=config, logger=logging.getLogger("test.agent"))

    saved = {k: os.environ.get(k) for k in ("SHIM_MODE", "SHIM_ARGV", "SHIM_EXIT")}
    os.environ["SHIM_MODE"] = "err"
    os.environ["SHIM_ARGV"] = str(argv_file)
    os.environ["SHIM_EXIT"] = "1"
    try:
        result = runner.run(agent="fake-agent", brief="do the thing", work_dir=work_dir)
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    assert result.status == "error"
    assert result.exit_code == 1
    assert "shim failure: bad model" in (result.error or "")


def test_notext_mode(config: Config, tmp_path: Path) -> None:
    """notext mode: exit 0 but no text event → error with the exact sentinel."""
    result, _ = _run(config, tmp_path, "notext")
    assert result.status == "error"
    assert result.exit_code == 0
    assert result.error == "no final text event in stream"
    assert result.final_text is None


def test_timeout_kills_process_group(config: Config, tmp_path: Path) -> None:
    """sleep mode with a 2s timeout: status timeout, fast wall time, no orphans."""
    started = time.monotonic()
    result, _ = _run(config, tmp_path, "sleep", timeout_seconds=2)
    elapsed = time.monotonic() - started

    assert result.status == "timeout"
    assert result.exit_code is None
    assert "exceeded 2s" in (result.error or "")
    assert elapsed < 10  # must not wait out the shim's sleep(30)
    assert result.duration_seconds < 10
    # Partial events captured before the kill: the early text event.
    assert len(result.events) == 1
    assert result.final_text == "partial"
    # No orphan shim process survives (killpg reached the whole group).
    leftovers = subprocess.run(["pgrep", "-f", "fake_opencode"], capture_output=True, text=True)
    assert leftovers.returncode != 0, f"orphan shim processes: {leftovers.stdout!r}"


def test_garbage_line_defensive_parse(config: Config, tmp_path: Path) -> None:
    """garbage mode: malformed stdout line is skipped; valid text event still parsed."""
    result, _ = _run(config, tmp_path, "garbage")
    assert result.status == "ok"
    assert result.final_text == "after garbage"
    assert len(result.events) == 1  # the malformed line was dropped, not stored
