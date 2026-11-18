"""Hermetic tests for AgentRunner — a fake ``opencode`` shim, never the real binary.

The shim is a Python script written to ``tmp_path`` that records its argv (via env
``SHIM_ARGV``) and emits canned NDJSON on stdout based on ``SHIM_MODE``:

- ``happy``: tool_use, step_start, text ("thinking..."), step_finish, text ("FINAL REPORT")
- ``err``: one error event, then exit 1
- ``notext``: step_start + step_finish only, exit 0
- ``sleep``: a text event, then sleep(30) (timeout path)
- ``garbage``: a malformed line before a valid text event
- ``env``: records cwd, ``PWD`` and stdin state as JSON to ``SHIM_ENV_OUT``, then a text
- ``v2err``: an OpenCode 2.x error event ``{"error": {"type": "aborted", "message": "x"}}``
- ``join``: two text events of one message (distinct ``part.id``) — expect a join
- ``dup``: two text events sharing a ``part.id`` — only the latest text counts

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

elif mode == "env":
    st = os.fstat(0)
    import stat as _stat
    info = {
        "cwd": os.getcwd(),
        "pwd": os.environ.get("PWD"),
        "stdin_is_fifo": _stat.S_ISFIFO(st.st_mode),
        "stdin_read": sys.stdin.read(),
    }
    with open(os.environ["SHIM_ENV_OUT"], "w", encoding="utf-8") as fh:
        json.dump(info, fh)
    emit({"type": "text", "timestamp": 0, "sessionID": "s1", "part": {"text": "env ok"}})
elif mode == "v2err":
    emit({"type": "error", "timestamp": 0, "sessionID": "s1",
          "error": {"type": "aborted", "message": "x"}})
elif mode == "join":
    emit({"type": "text", "timestamp": 0, "sessionID": "s1",
          "part": {"id": "p0", "messageID": "m0", "text": "older message"}})
    emit({"type": "text", "timestamp": 1, "sessionID": "s1",
          "part": {"id": "p1", "messageID": "m1", "text": "Hello, "}})
    emit({"type": "tool_use", "timestamp": 2, "sessionID": "s1", "part": {"id": "c1"}})
    emit({"type": "text", "timestamp": 3, "sessionID": "s1",
          "part": {"id": "p2", "messageID": "m1", "text": "world."}})
elif mode == "dup":
    emit({"type": "text", "timestamp": 0, "sessionID": "s1",
          "part": {"id": "p1", "messageID": "m1", "text": "draft"}})
    emit({"type": "text", "timestamp": 1, "sessionID": "s1",
          "part": {"id": "p1", "messageID": "m1", "text": "draft final"}})

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
        model="llama-cpp/Qwen3.8-27B",
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
    extra_env: dict[str, str] | None = None,
) -> tuple[object, Path]:
    """Run the shim-backed AgentRunner in ``mode``; return (result, argv_file).

    The shim's env vars (plus ``extra_env``) are set for the duration of the run and
    restored afterwards.
    """
    argv_file = tmp_path / f"argv_{mode}.json"
    work_dir = tmp_path / "work"
    work_dir.mkdir(parents=True, exist_ok=True)
    runner = AgentRunner(config=config, logger=logging.getLogger("test.agent"))

    extra_env = extra_env or {}
    saved = {k: os.environ.get(k) for k in ("SHIM_MODE", "SHIM_ARGV", *extra_env)}
    os.environ["SHIM_MODE"] = mode
    os.environ["SHIM_ARGV"] = str(argv_file)
    os.environ.update(extra_env)
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
        "--standalone",
        "--agent",
        "oc-todo-resolver",
        "--format",
        "json",
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
        "--standalone",
        "--agent",
        "a",
        "--format",
        "json",
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
    assert "--dir" not in captured  # OpenCode 2.x rejects --dir
    assert captured[:2] == ["run", "--standalone"]


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


def test_child_cwd_pwd_and_stdin(config: Config, tmp_path: Path) -> None:
    """(a) Child runs with cwd == PWD == work_dir and stdin is /dev/null (not a pipe, EOF)."""
    env_out = tmp_path / "env.json"
    result, _ = _run(config, tmp_path, "env", extra_env={"SHIM_ENV_OUT": str(env_out)})
    assert result.status == "ok"
    info = json.loads(env_out.read_text(encoding="utf-8"))
    work_dir = tmp_path / "work"
    assert Path(info["cwd"]).resolve() == work_dir.resolve()
    assert info["pwd"] == str(work_dir)
    assert info["stdin_is_fifo"] is False
    assert info["stdin_read"] == ""  # immediately at EOF
    assert os.environ.get("PWD") != str(work_dir)  # parent env untouched


def test_v2_error_event_shape(config: Config, tmp_path: Path) -> None:
    """(b) 2.x error object {type, message} + exit 1 → "aborted: x"."""
    result, _ = _run(config, tmp_path, "v2err", extra_env={"SHIM_EXIT": "1"})
    assert result.status == "error"
    assert result.exit_code == 1
    assert result.error == "aborted: x"


def test_text_joined_per_message(config: Config, tmp_path: Path) -> None:
    """(c) Text events of the last message (distinct part.id) are joined in order."""
    result, _ = _run(config, tmp_path, "join")
    assert result.status == "ok"
    assert result.final_text == "Hello, world."


def test_text_same_part_id_latest_wins(config: Config, tmp_path: Path) -> None:
    """(c) Two text events with the same part.id → only the latest text is kept."""
    result, _ = _run(config, tmp_path, "dup")
    assert result.status == "ok"
    assert result.final_text == "draft final"


def test_error_message_helper_shapes() -> None:
    """_error_message: dict with type+message, message only, and legacy string."""
    from agentic_scripts.agent import _error_message

    assert _error_message({"type": "unknown", "message": "boom"}) == "unknown: boom"
    assert _error_message({"message": "boom"}) == "boom"
    assert _error_message("legacy failure") == "legacy failure"
    assert _error_message({"type": "error", "sessionID": "s"}) == str(
        {"type": "error", "sessionID": "s"}
    )
