"""Timer-agnostic scheduler core: hybrid gate, exclusive lock, and run loop.

Purpose:
    Implement the load-aware scheduling core behind the ``agentic-scripts`` CLI: a
    *hybrid* gate that opens only when the machine is inside its quiet window AND the
    1-minute load has stayed below threshold across two consecutive polls, an
    exclusive skip-if-held lock so overlapping timer firings never deadlock or double-run,
    and a single ``run()`` loop that assembles config → dotenv → logger → lock → gate →
    workflows → last-run summary. Every run writes ``logs/run-<run_id>.log`` and refreshes
    ``logs/last-run.txt`` so the unattended system is auditable without a dashboard.

Rationale:
    The timer fires often (every 30 min) but must only do work when the machine is
    *sustainedly* idle — one idle blip must not open the gate ("wait until the machine
    is actually idle for ~1 hour"). ``evaluate_gate`` is kept pure apart from its
    documented state writes and takes the load as an argument (no psutil import) so gate
    tests need no monkeypatching. The lock uses ``flock(LOCK_EX | LOCK_NB)``: a second
    invocation skips cleanly (returns None) rather than blocking, and the lock file is
    never unlinked (unlink races). Per-workflow failures are logged, not fatal — the next
    poll retries, which is safe because state is consulted before acting.

Usage:
    >>> from agentic_scripts.scheduler import run
    >>> code = run(["run", "--force"])   # operator override; 0 on success
    >>> code
    0
"""

from __future__ import annotations

import argparse
import fcntl
import importlib
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import psutil
from dotenv import load_dotenv

from agentic_scripts.config import (
    PROJECT_ROOT,
    Config,
    ConfigError,
    Machine,
    WorkflowEntry,
    load_config,
)
from agentic_scripts.logging_setup import new_run_id, setup_run_logger, write_last_run
from agentic_scripts.state import StateError, StateStore
from agentic_scripts.workflows.base import WorkContext, WorkflowResult

DEFAULT_CONFIG = PROJECT_ROOT / "config" / "workflows.yaml"


class SchedulerUsageError(RuntimeError):
    """Raised when a run request is malformed (e.g. ``--only`` names an unknown workflow).

    The message carries the offending workflow name so it can be surfaced to the operator
    on stderr and in the run log before the run aborts with exit code 2.

    Example:
        >>> raise SchedulerUsageError("nope")
        Traceback (most recent call last):
            ...
        agentic_scripts.scheduler.SchedulerUsageError: unknown workflow 'nope'
    """


class SchedulerError(RuntimeError):
    """Raised for unexpected faults inside the scheduler core.

    Reserved for programmer errors and genuine I/O failures that should not be swallowed;
    per-workflow business failures are reported via :class:`WorkflowResult` instead and do
    not raise here.
    """


@dataclass(frozen=True)
class GateResult:
    """The outcome of a single gate evaluation.

    Attributes:
        open: Whether the gate is open (workflows should run).
        reason: A short human-readable verdict phrase (e.g. ``"2nd consecutive idle poll"``).
        load1: The 1-minute load average at evaluation time.
        load5: The 5-minute load average at evaluation time.
        load15: The 15-minute load average at evaluation time.
        window_open: Whether the local clock is inside the quiet window.
        now: The local (naive) wall-clock time the gate was evaluated at.
    """

    open: bool
    reason: str
    load1: float
    load5: float
    load15: float
    window_open: bool
    now: datetime


def read_load() -> tuple[float, float, float]:
    """Read the 1/5/15-minute load averages from ``psutil.getloadavg()``.

    Isolated in its own function so tests can monkeypatch it (or inject a load tuple into
    :func:`run`) without touching psutil. The gate itself never imports this — it receives
    the load as an argument, keeping :func:`evaluate_gate` free of any psutil dependency.

    Returns:
        A ``(load1, load5, load15)`` tuple of floats.

    Example:
        >>> l1, l5, l15 = read_load()
        >>> isinstance(l1, float)
        True
    """
    return psutil.getloadavg()


def evaluate_gate(
    now: datetime,
    load: tuple[float, float, float],
    machine: Machine,
    state: StateStore,
) -> GateResult:
    """Evaluate the hybrid quiet-window + sustained-low-load gate.

    Implements the canonical algorithm exactly: the gate is *idle* only when the local
    clock ``now`` is inside the quiet window AND the 1-minute load is STRICTLY below the
    threshold. With ``gate_polls_required == 1`` a single idle poll opens the gate; with
    ``2``, a second idle poll within ``poll_interval + tolerance`` minutes of the last
    recorded one does, and an out-of-window/over-threshold poll clears the recorded streak.

    Args:
        now: The local (naive) wall-clock time to evaluate at. All comparisons use this;
            it is persisted as UTC when stored.
        load: A ``(load1, load5, load15)`` tuple; only ``load1`` gates (STRICT comparison).
        machine: The validated :class:`~agentic_scripts.config.Machine` parameters.
        state: The durable :class:`StateStore`; the gate reads/writes the ``scheduler``
            document's ``gate_last_ok`` key.

    Returns:
        A :class:`GateResult` with the verdict, reason, load triple, window flag, and now.

    Side Effects:
        Writes ``state/scheduler.json`` (``gate_last_ok``) on every non-forced evaluation:
        cleared to null when not idle, set to the UTC ISO-8601 of ``now`` on a first idle
        poll. No other I/O.

    Raises:
        StateError: If the ``scheduler`` state document is corrupt (a real fault, not a
            gate input) — propagates so the caller logs ERROR and aborts with exit 2.

    Example:
        >>> result = evaluate_gate(now, (0.5, 0.5, 0.5), machine, store)
        >>> result.open in (True, False)
        True
    """
    load1, load5, load15 = load
    window_open = machine.quiet_window.in_window(now.time())
    load_ok = load1 < machine.load_threshold
    idle = window_open and load_ok

    if not idle:
        state.update("scheduler", "gate_last_ok", None)
        if not window_open and not load_ok:
            reason = "outside quiet window and load above threshold"
        elif not window_open:
            reason = "outside quiet window"
        else:
            reason = "load above threshold"
        return GateResult(
            open=False,
            reason=reason,
            load1=load1,
            load5=load5,
            load15=load15,
            window_open=window_open,
            now=now,
        )

    if machine.gate_polls_required == 1:
        return GateResult(
            open=True,
            reason="single idle poll",
            load1=load1,
            load5=load5,
            load15=load15,
            window_open=window_open,
            now=now,
        )

    prev_raw = state.load("scheduler").get("gate_last_ok")  # may raise StateError (corrupt)
    if prev_raw is not None:
        prev = (
            datetime.fromisoformat(prev_raw.replace("Z", "+00:00"))
            .astimezone()
            .replace(tzinfo=None)
        )
        max_gap = timedelta(
            minutes=machine.poll_interval_minutes + machine.gate_poll_tolerance_minutes
        )
        if (now - prev) <= max_gap:
            return GateResult(
                open=True,
                reason="2nd consecutive idle poll",
                load1=load1,
                load5=load5,
                load15=load15,
                window_open=window_open,
                now=now,
            )

    state.update("scheduler", "gate_last_ok", now.astimezone().isoformat())
    return GateResult(
        open=False,
        reason="1st idle poll recorded",
        load1=load1,
        load5=load5,
        load15=load15,
        window_open=window_open,
        now=now,
    )


def acquire_lock(state_dir: Path) -> int | None:
    """Acquire an exclusive non-blocking lock on ``<state_dir>/.lock``.

    Opens (creating if needed, 0644) the lock file and attempts ``flock(LOCK_EX | LOCK_NB)``.
    The lock file is intentionally never unlinked — unlinking a flock target races with a
    concurrent opener that would then lock a different inode and both runs would proceed.

    Args:
        state_dir: Directory holding (or to hold) the ``.lock`` file; created if absent.

    Returns:
        The open file descriptor on success — the caller MUST ``os.close(fd)`` to release
        the lock (closing releases the flock). ``None`` if another process already holds
        the lock (the run should skip, never block).

    Example:
        >>> fd = acquire_lock(Path("state"))
        >>> fd is None or isinstance(fd, int)
        True
        >>> os.close(fd) if fd is not None else None  # release
    """
    state_dir = Path(state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    lock_path = state_dir / ".lock"
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        return None
    return fd


def list_enabled(config: Config, only: str | None) -> list[WorkflowEntry]:
    """Return the enabled workflow entries in config order, optionally filtered by name.

    Args:
        config: The validated :class:`Config` whose ``workflows`` preserves YAML order.
        only: If given, restrict to the single entry with this name; None means all enabled.

    Returns:
        A list of :class:`WorkflowEntry`, in original config order, containing only enabled
        entries (and, when ``only`` is set, only that named entry).

    Raises:
        SchedulerUsageError: If ``only`` names a workflow not present in the config.

    Example:
        >>> entries = list_enabled(config, None)   # all enabled, config order
        >>> [e.name for e in entries]
        ['noop']
    """
    if only is not None and not any(entry.name == only for entry in config.workflows):
        raise SchedulerUsageError(only)
    return [
        entry
        for entry in config.workflows
        if entry.enabled and (only is None or entry.name == only)
    ]


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser for the ``run`` subcommand.

    The parser lives here (not in ``cli.py``) so :func:`run` can parse a raw argv list and
    stay unit-testable without going through ``sys.exit``. A bare invocation with no
    subcommand is handled by :func:`run` (prints help, exits 2); the parser itself always
    has a ``run`` subparser as the effective default.

    Returns:
        An :class:`argparse.ArgumentParser` with a ``run`` subcommand carrying the flags
        ``--force``, ``--only NAME``, ``--config PATH`` (defaulting to the shipped config),
        and ``--verbose``.

    Example:
        >>> parser = build_parser()
        >>> ns = parser.parse_args(["run", "--force"])
        >>> ns.force
        True
    """
    parser = argparse.ArgumentParser(
        prog="agentic-scripts",
        description="Load-aware agentic workflow scheduler.",
    )
    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser(
        "run", help="Run the scheduled workflows (gated unless --force)."
    )
    run_parser.add_argument(
        "--force",
        action="store_true",
        help="Bypass the gate and run immediately (operator override / smoke path).",
    )
    run_parser.add_argument(
        "--only",
        metavar="NAME",
        default=None,
        help="Run only this workflow by name (must be a registered workflow).",
    )
    run_parser.add_argument(
        "--config",
        metavar="PATH",
        default=str(DEFAULT_CONFIG),
        help=f"Path to the workflows config (default: {DEFAULT_CONFIG}).",
    )
    run_parser.add_argument(
        "--verbose",
        action="store_true",
        help="Echo INFO-level log records to stderr.",
    )
    return parser


def _gate_line(gate: GateResult, machine: Machine) -> str:
    """Format the canonical GATE log line for a gate evaluation.

    Args:
        gate: The :class:`GateResult` to render.
        machine: The :class:`Machine` (for the threshold and quiet-window label).

    Returns:
        A single INFO log line matching the documented format, e.g.
        ``GATE now=... load1=13.43 ... verdict=CLOSED reason=load above threshold``.
    """
    window = "open" if gate.window_open else "closed"
    return (
        f"GATE now={gate.now.isoformat()} "
        f"load1={gate.load1:.2f} load5={gate.load5:.2f} load15={gate.load15:.2f} "
        f"window={window} threshold={machine.load_threshold} "
        f"verdict={'OPEN' if gate.open else 'CLOSED'} reason={gate.reason}"
    )


def _last_run_lines(
    run_id: str,
    trigger: str,
    gate_line: str | None,
    workflow_summaries: list[str],
    overall: str,
) -> list[str]:
    """Assemble the canonical ``logs/last-run.txt`` lines.

    Args:
        run_id: The unique run identifier (first line).
        trigger: ``"gate"`` or ``"force"`` (second line).
        gate_line: The gate summary line, e.g. ``gate: CLOSED now=... reason=...``; None
            for a forced run (rendered as ``gate: FORCED``).
        workflow_summaries: One line per workflow, e.g.
            ``workflows: noop=ok(0 items, 1 action, 0 errors)``; empty when no workflows ran.
        overall: The overall outcome word, e.g. ``"skipped"``, ``"ok"``, or ``"error"``.

    Returns:
        A list of short lines (4–5) suitable for :func:`write_last_run`.
    """
    gate = gate_line if gate_line is not None else "gate: FORCED"
    workflows = workflow_summaries[0] if workflow_summaries else "workflows: -"
    return [f"run: {run_id}", f"trigger: {trigger}", gate, workflows, f"overall: {overall}"]


def run(
    argv: list[str] | None = None,
    *,
    now: datetime | None = None,
    load: tuple[float, float, float] | None = None,
    run_id: str | None = None,
) -> int:
    """Run the full scheduler loop and return the process exit code.

    Assembles the pipeline in exact order: parse args → load config → load .env → set up
    the run logger → acquire the exclusive lock → evaluate the gate (unless ``--force``)
    → resolve enabled workflows → run each (a failure never stops the rest) → write the
    last-run summary. Returning an int (rather than calling ``sys.exit``) keeps this
    directly testable without catching ``SystemExit``.

    Args:
        argv: Raw argument list to parse (defaults to ``sys.argv[1:]``). A bare/empty
            invocation prints help and returns 2; the ``run`` subcommand is the default.
        now: The local wall-clock time to evaluate the gate at; None uses
            ``datetime.now()``. Injected in tests so timing is deterministic.
        load: The ``(load1, load5, load15)`` tuple to gate on; None reads it live via
            :func:`read_load`. Injected in tests to avoid real host load.
        run_id: The unique run identifier for this invocation; None generates one via
            :func:`new_run_id` (real wall-clock). Injecting distinct ids in tests avoids
            same-second collisions when several runs share a log dir.

    Returns:
        ``0`` for a run that completed (including gate-closed and lock-skip no-ops), or
        ``2`` for a config/usage fault. Per-workflow errors never change the exit code —
        they are logged and retried on the next poll.

    Example:
        >>> run(["run", "--force"])   # operator override
        0
    """
    global _t0
    _t0 = time.monotonic()

    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()

    # A bare invocation (no subcommand) prints help and exits 2; "run" is the default.
    if not argv:
        parser.print_help()
        return 2
    if argv[0] != "run":
        argv = ["run", *argv]
    args = parser.parse_args(argv)

    # Load config (fail fast, exit 2 on a ConfigError).
    try:
        config = load_config(Path(args.config))
    except ConfigError as exc:
        print(f"config error: {exc.message}", file=sys.stderr)
        return 2

    # Load .env (missing file is fine; never override the real environment).
    load_dotenv(PROJECT_ROOT / ".env", override=False)

    if now is None:
        now = datetime.now()
    if load is None:
        load = read_load()

    run_id = run_id if run_id is not None else new_run_id()
    logger, log_path = setup_run_logger(config.paths.log_dir, run_id, verbose=args.verbose)
    logger.info("RUN START force=%s only=%s", args.force, args.only)

    # Exclusive lock: skip cleanly (exit 0) if another run already holds it.
    fd = acquire_lock(config.paths.state_dir)
    if fd is None:
        logger.info("SKIP another run is in progress")
        write_last_run(
            config.paths.log_dir,
            _last_run_lines(run_id, "gate", None, [], "skipped"),
        )
        return 0

    try:
        # Gate (unless forced). A corrupt scheduler state is a real fault → exit 2.
        gate = None
        if not args.force:
            try:
                gate = evaluate_gate(now, load, config.machine, StateStore(config.paths.state_dir))
            except StateError as exc:
                logger.error("state error: %s", exc)
                write_last_run(
                    config.paths.log_dir,
                    _last_run_lines(run_id, "gate", None, [], "error"),
                )
                return 2
            logger.info(_gate_line(gate, config.machine))
            if not gate.open:
                duration = time.monotonic() - _t0
                logger.info("RUN END gate=closed workflows=0 errors=0 duration=%.1fs", duration)
                write_last_run(
                    config.paths.log_dir,
                    _last_run_lines(
                        run_id,
                        "gate",
                        (
                            f"gate: CLOSED now={gate.now.isoformat()} "
                            f"load1={gate.load1:.2f} threshold={config.machine.load_threshold} "
                            f"window={'open' if gate.window_open else 'closed'} "
                            f"reason={gate.reason}"
                        ),
                        [],
                        "skipped",
                    ),
                )
                return 0

        # Resolve workflows (usage error → exit 2).
        try:
            entries = list_enabled(config, args.only)
        except SchedulerUsageError as exc:
            logger.error("usage error: %s", exc)
            write_last_run(
                config.paths.log_dir,
                _last_run_lines(run_id, "force" if args.force else "gate", None, [], "error"),
            )
            return 2

        # Run each workflow in order; a failure never stops the rest.
        state = StateStore(config.paths.state_dir)
        summaries: list[str] = []
        error_count = 0
        for entry in entries:
            try:
                module = importlib.import_module(entry.module)
            except ImportError as exc:
                logger.error("WORKFLOW %s status=error error=%s", entry.name, exc)
                summaries.append(f"{entry.name}=error(0 items, 0 actions, 1 errors)")
                error_count += 1
                continue

            try:
                wf = module.create(config)
            except Exception as exc:  # noqa: BLE001 - any create failure is a workflow fault
                logger.error("WORKFLOW %s status=error error=%s", entry.name, exc)
                summaries.append(f"{entry.name}=error(0 items, 0 actions, 1 errors)")
                error_count += 1
                continue

            ctx = WorkContext(
                config=config,
                state=state,
                logger=logger.getChild(entry.name),
                run_id=run_id,
                workflow_name=entry.name,
                sandbox_dir=config.paths.sandbox_dir,
                admin_repo=config.admin_repo,
            )
            t0 = time.monotonic()
            try:
                result = wf.run(ctx)
            except Exception as exc:  # noqa: BLE001 - programmer error; log and continue
                logger.exception("WORKFLOW %s raised", entry.name)
                result = WorkflowResult(status="error", errors=[f"{type(exc).__name__}: {exc}"])
            result.duration_seconds = time.monotonic() - t0

            if result.status == "error":
                error_count += 1
            logger.info(
                "WORKFLOW %s status=%s items_found=%d actions=%d errors=%d duration=%.2fs",
                entry.name,
                result.status,
                result.items_found,
                len(result.actions),
                len(result.errors),
                result.duration_seconds,
            )
            summaries.append(
                f"{entry.name}={result.status}"
                f"({result.items_found} items, {len(result.actions)} actions, "
                f"{len(result.errors)} errors)"
            )

        overall = "error" if error_count else "ok"
        gate_word = "forced" if args.force else ("open" if gate and gate.open else "closed")
        duration = time.monotonic() - _t0
        logger.info(
            "RUN END gate=%s workflows=%d errors=%d duration=%.1fs",
            gate_word,
            len(entries),
            error_count,
            duration,
        )
        write_last_run(
            config.paths.log_dir,
            _last_run_lines(run_id, "force" if args.force else "gate", None, summaries, overall),
        )
        return 0
    finally:
        os.close(fd)


# Start-time anchor for duration reporting inside ``run``. Bound at module import and
# reset to ``time.monotonic()`` at the top of every ``run()`` call (via ``global _t0``).
_t0 = 0.0
