"""Hermetic tests for the gates (``evaluate_gate`` and ``evaluate_idle_gate``).

All times, loads, and session counts are injected; no real clock, load, or host state is
consulted. Each gate's only I/O is its documented ``scheduler.json`` read/write, which is
pointed at a tmp dir via :class:`StateStore`. Corrupt-state behaviour is asserted to
raise :class:`StateError` (no silent reset). The two gates' streak keys
(``gate_last_ok`` vs ``idle_gate_last_ok``) are asserted not to collide.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from agentic_scripts.config import Config, Machine, QuietWindow
from agentic_scripts.scheduler import evaluate_gate, evaluate_idle_gate
from agentic_scripts.state import StateError, StateStore


def _machine(
    start: str = "22:00",
    end: str = "08:00",
    threshold: float = 2.0,
    polls: int = 2,
    interval: int = 30,
    tolerance: int = 10,
) -> Machine:
    """Build a :class:`Machine` for gate tests with the shipped defaults unless overridden."""
    return Machine(
        quiet_window=QuietWindow(start=start, end=end),
        load_threshold=threshold,
        poll_interval_minutes=interval,
        gate_polls_required=polls,
        gate_poll_tolerance_minutes=tolerance,
    )


def _store(tmp_path: Path) -> StateStore:
    """Return a :class:`StateStore` rooted at a fresh tmp state dir."""
    return StateStore(tmp_path / "state")


def test_out_of_window_low_load_closes_and_clears(tmp_path: Path, base_config: Config) -> None:
    """1. Out-of-window now + low load → closed (window reason); gate_last_ok cleared to null."""
    store = _store(tmp_path)
    # Pre-seed a stale prev so we can assert it is cleared on a non-idle poll.
    store.update("scheduler", "gate_last_ok", "2026-10-20T22:00:00+00:00")

    now = datetime(2026, 10, 20, 13, 0)  # local 13:00 — outside the 22:00–08:00 window
    result = evaluate_gate(now, (0.5, 0.5, 0.5), base_config.machine, store)

    assert result.open is False
    assert "window" in result.reason
    assert result.window_open is False
    assert store.load("scheduler").get("gate_last_ok") is None


def test_in_window_high_load_closes_and_clears(tmp_path: Path, base_config: Config) -> None:
    """2. In-window now + load1 >= threshold → closed (load reason); state cleared."""
    store = _store(tmp_path)
    store.update("scheduler", "gate_last_ok", "2026-10-20T22:00:00+00:00")

    now = datetime(2026, 10, 20, 23, 0)  # local 23:00 — inside the window
    # load1 must be >= the shipped threshold to count as "high load" (Task 5g raised it to 32.0);
    # use a value above it so the gate closes on the load reason regardless of the exact threshold.
    high_load = base_config.machine.load_threshold + 1.0
    result = evaluate_gate(now, (high_load, high_load, high_load), base_config.machine, store)

    assert result.open is False
    assert "load" in result.reason
    assert result.window_open is True
    assert store.load("scheduler").get("gate_last_ok") is None


def test_first_idle_poll_records(tmp_path: Path, base_config: Config) -> None:
    """3. In-window + low load, no prev → closed '1st idle poll recorded'; state now set."""
    store = _store(tmp_path)

    now = datetime(2026, 10, 20, 22, 30)  # inside the window, idle
    result = evaluate_gate(now, (0.5, 0.5, 0.5), base_config.machine, store)

    assert result.open is False
    assert result.reason == "1st idle poll recorded"
    stored = store.load("scheduler").get("gate_last_ok")
    assert stored is not None


def test_second_poll_within_tolerance_opens(tmp_path: Path, base_config: Config) -> None:
    """4. Second poll 30 min later (within 30+10) → open '2nd consecutive idle poll'."""
    store = _store(tmp_path)

    first = datetime(2026, 10, 20, 22, 0)
    evaluate_gate(first, (0.5, 0.5, 0.5), base_config.machine, store)

    second = first + timedelta(minutes=30)  # 22:30, within tolerance
    result = evaluate_gate(second, (0.5, 0.5, 0.5), base_config.machine, store)

    assert result.open is True
    assert result.reason == "2nd consecutive idle poll"


def test_second_poll_beyond_tolerance_resets(tmp_path: Path, base_config: Config) -> None:
    """5. Second poll 45 min later (beyond tolerance) → closed '1st idle poll recorded'."""
    store = _store(tmp_path)

    first = datetime(2026, 10, 20, 22, 0)
    evaluate_gate(first, (0.5, 0.5, 0.5), base_config.machine, store)

    second = first + timedelta(minutes=45)  # 22:45 > 30+10
    result = evaluate_gate(second, (0.5, 0.5, 0.5), base_config.machine, store)

    assert result.open is False
    assert result.reason == "1st idle poll recorded"
    # The stored prev must now reflect the newer poll time (reset to second).
    stored = store.load("scheduler").get("gate_last_ok")
    parsed = datetime.fromisoformat(stored.replace("Z", "+00:00")).astimezone().replace(tzinfo=None)
    assert abs((parsed - second).total_seconds()) < 60


def test_single_poll_required_opens_immediately(tmp_path: Path, base_config: Config) -> None:
    """6. gate_polls_required=1 → open on the first idle poll."""
    store = _store(tmp_path)
    machine = _machine(polls=1)

    now = datetime(2026, 10, 20, 23, 0)
    result = evaluate_gate(now, (0.5, 0.5, 0.5), machine, store)

    assert result.open is True
    assert result.reason == "single idle poll"


def test_corrupt_scheduler_state_raises(tmp_path: Path, base_config: Config) -> None:
    """7. Corrupt scheduler.json (garbage bytes) → StateError propagates (no silent reset)."""
    store = _store(tmp_path)
    # Force a corrupt file: write garbage directly to the scheduler state path.
    (tmp_path / "state").mkdir(parents=True, exist_ok=True)
    (tmp_path / "state" / "scheduler.json").write_text("not-json{{", encoding="utf-8")

    now = datetime(2026, 10, 20, 23, 0)  # idle → the gate will try to load prev
    with pytest.raises(StateError):
        evaluate_gate(now, (0.5, 0.5, 0.5), base_config.machine, store)


def test_midnight_crossing_window(tmp_path: Path, base_config: Config) -> None:
    """8. Midnight-crossing window: 01:00 → open; 13:00 → closed (shipped 22:00–08:00)."""
    store = _store(tmp_path)
    machine = _machine(polls=1)  # single poll so only the window matters

    late_night = datetime(2026, 10, 20, 1, 0)  # 01:00 — inside (crosses midnight)
    assert evaluate_gate(late_night, (0.5, 0.5, 0.5), machine, store).open is True

    midday = datetime(2026, 10, 20, 13, 0)  # 13:00 — outside
    assert evaluate_gate(midday, (0.5, 0.5, 0.5), machine, store).open is False


# --- idle gate (evaluate_idle_gate) ---------------------------------------------


def test_idle_first_poll_records(tmp_path: Path, base_config: Config) -> None:
    """I1. Zero active sessions, fresh state → closed 'no active sessions (1st …)';
    idle_gate_last_ok set. NO quiet window: works at midday, any load is irrelevant."""
    store = _store(tmp_path)

    now = datetime(2026, 11, 20, 13, 0)  # midday — the idle gate has no window
    result = evaluate_idle_gate(now, store, base_config.machine, 0)

    assert result.open is False
    assert result.reason == "no active sessions (1st idle poll recorded)"
    assert store.load("scheduler").get("idle_gate_last_ok") is not None
    # GateResult reuse semantics: load fields zeroed, window_open sentinel True.
    assert (result.load1, result.load5, result.load15) == (0.0, 0.0, 0.0)
    assert result.window_open is True


def test_idle_second_poll_within_tolerance_opens(tmp_path: Path, base_config: Config) -> None:
    """I2. Second idle poll 30 min later (within 30+10) → open '2nd consecutive'."""
    store = _store(tmp_path)

    first = datetime(2026, 11, 20, 13, 0)
    evaluate_idle_gate(first, store, base_config.machine, 0)

    second = first + timedelta(minutes=30)
    result = evaluate_idle_gate(second, store, base_config.machine, 0)

    assert result.open is True
    assert result.reason == "no active sessions (2nd consecutive idle poll)"


def test_idle_second_poll_beyond_tolerance_resets(tmp_path: Path, base_config: Config) -> None:
    """I3. Second idle poll 45 min later (beyond 30+10) → closed '1st …'; prev re-recorded."""
    store = _store(tmp_path)

    first = datetime(2026, 11, 20, 13, 0)
    evaluate_idle_gate(first, store, base_config.machine, 0)

    second = first + timedelta(minutes=45)
    result = evaluate_idle_gate(second, store, base_config.machine, 0)

    assert result.open is False
    assert result.reason == "no active sessions (1st idle poll recorded)"
    stored = store.load("scheduler").get("idle_gate_last_ok")
    parsed = datetime.fromisoformat(stored.replace("Z", "+00:00")).astimezone().replace(tzinfo=None)
    assert abs((parsed - second).total_seconds()) < 60


def test_idle_active_sessions_closes_and_clears(tmp_path: Path, base_config: Config) -> None:
    """I4. N active sessions → closed 'N active session(s)'; idle_gate_last_ok cleared."""
    store = _store(tmp_path)
    # Pre-seed a streak so we can assert a non-idle poll clears it.
    evaluate_idle_gate(datetime(2026, 11, 20, 13, 0), store, base_config.machine, 0)
    assert store.load("scheduler").get("idle_gate_last_ok") is not None

    now = datetime(2026, 11, 20, 13, 30)
    result = evaluate_idle_gate(now, store, base_config.machine, 3)

    assert result.open is False
    assert result.reason == "3 active session(s)"
    assert store.load("scheduler").get("idle_gate_last_ok") is None


def test_idle_single_poll_required_opens_immediately(tmp_path: Path, base_config: Config) -> None:
    """I5. gate_polls_required=1 → open on the first idle poll."""
    store = _store(tmp_path)
    machine = _machine(polls=1)

    now = datetime(2026, 11, 20, 13, 0)
    result = evaluate_idle_gate(now, store, machine, 0)

    assert result.open is True
    assert result.reason == "no active sessions (single idle poll)"
    # A single-poll open must not record a streak (mirrors the quiet gate).
    assert store.load("scheduler").get("idle_gate_last_ok") is None


def test_idle_gate_never_touches_quiet_gate_key(tmp_path: Path, base_config: Config) -> None:
    """I6. Idle-gate evaluations leave gate_last_ok untouched (separate streak keys)."""
    store = _store(tmp_path)
    seed = "2026-11-19T22:00:00+00:00"
    store.update("scheduler", "gate_last_ok", seed)

    now = datetime(2026, 11, 20, 13, 0)
    evaluate_idle_gate(now, store, base_config.machine, 0)  # 1st idle poll recorded
    evaluate_idle_gate(now + timedelta(minutes=1), store, base_config.machine, 2)  # clears idle

    doc = store.load("scheduler")
    assert doc["gate_last_ok"] == seed  # quiet-gate key untouched
    assert doc["idle_gate_last_ok"] is None  # idle key driven by idle polls only


def test_idle_corrupt_scheduler_state_raises(tmp_path: Path, base_config: Config) -> None:
    """I7. Corrupt scheduler.json → StateError propagates (no silent reset)."""
    store = _store(tmp_path)
    (tmp_path / "state").mkdir(parents=True, exist_ok=True)
    (tmp_path / "state" / "scheduler.json").write_text("not-json{{", encoding="utf-8")

    now = datetime(2026, 11, 20, 13, 0)  # idle → the gate will try to load prev
    with pytest.raises(StateError):
        evaluate_idle_gate(now, store, base_config.machine, 0)
