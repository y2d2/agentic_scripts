"""Agent runner: process wrapper over ``opencode run --format json``.

Purpose:
    Spawn a single OpenCode agent run (``opencode run --agent <name> --format json
    ...``), stream its stdout as NDJSON events, enforce a hard wall-clock timeout by
    killing the whole process group, and reduce the event stream to a final assistant
    text plus an :class:`AgentResult` status.

Rationale:
    ``opencode run --format json`` (verified against v1.18.35; full research cache at
    ``/workspace/Research/ai-agent-workflow/opencode-run-json-event-stream.md``) writes
    pure NDJSON to stdout — one object per line, no preamble, no ANSI:
    ``{"type": <event>, "timestamp": ..., "sessionID": ..., ...payload}``. Event types
    are ``tool_use``, ``step_start``, ``step_finish``, ``text``, ``reasoning`` (only
    with ``--thinking``, which we never pass), and ``error``. The final assistant text
    is the ``part.text`` of the LAST ``type == "text"`` event — a run may emit several
    ``text`` events, earlier ones being intermediate output. Exit code 0 means success
    *including* the case where the agent's frontmatter ``steps`` cap is hit: the cap
    produces an ordinary final ``text`` event with a "maximum steps reached"-style
    summary (there is no distinct cap event), so this runner reports it as a normal
    ``ok``. Exit 1 signals usage/API/session errors, with details on stderr.
    Detecting a cap-style summary in ``final_text`` and re-dispatching with fresh
    context is the *workflow* layer's job (see
    ``/workspace/Research/ai-agent-workflow/agent-token-budget-steps.md``); this runner
    deliberately does no such special-casing.

Usage:
    >>> from agentic_scripts.agent import AgentRunner
    >>> runner = AgentRunner(config=config, logger=logger)
    >>> result = runner.run(agent="oc-todo-resolver", brief="...", work_dir=repo_path)
    >>> if result.status == "ok":
    ...     print(result.final_text)

Side effects:
    Spawns one subprocess (its own process group via ``start_new_session``); on
    timeout the whole group is SIGKILLed so agent-spawned children die too. No other
    I/O beyond logging. The class has no repo/mail/scheduler knowledge — it is a pure
    process wrapper.
"""

from __future__ import annotations

import json
import logging
import os
import select
import signal
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from agentic_scripts.config import Config


@dataclass
class AgentResult:
    """The outcome of a single agent run.

    Attributes:
        status: One of ``"ok"``, ``"error"``, or ``"timeout"``. ``ok`` means exit 0
            with at least one ``text`` event in the stream (this includes runs that
            stopped at the agent's ``steps`` cap — see module docstring). ``error``
            covers non-zero exits and zero-exit runs with no final text. ``timeout``
            means the hard deadline was breached and the process group was killed.
        exit_code: The child's exit code, or None when it was killed by timeout (no
            natural exit).
        final_text: The ``part.text`` of the last ``type == "text"`` event, or None if
            the stream contained no text events.
        events: Every successfully parsed NDJSON object from stdout, in stream order
            (malformed lines are logged and skipped, never stored).
        error: A human-readable failure description for ``error``/``timeout`` statuses;
            None on success.
        duration_seconds: Wall-clock seconds the run took (from spawn to reap).
    """

    status: str
    exit_code: int | None
    final_text: str | None
    events: list[dict] = field(default_factory=list)
    error: str | None = None
    duration_seconds: float = 0.0


class AgentRunner:
    """Runs one OpenCode agent invocation and captures its NDJSON event stream.

    The runner is a pure process wrapper: it builds the exact command line, streams
    stdout line-by-line into parsed events, drains stderr in a daemon thread, enforces
    a hard timeout via process-group kill (so children spawned by the agent die too),
    and maps the exit code plus event stream to an :class:`AgentResult`. It knows
    nothing about repos, mail, or workflow policy.

    Note:
        A run that hits the agent's frontmatter ``steps`` cap exits 0 with a final
        ``text`` summary and is therefore reported as ``status="ok"`` — see the module
        docstring for the verified schema and the steps-cap contract.
    """

    def __init__(self, *, config: Config, logger: logging.Logger | None = None) -> None:
        """Initialize the runner.

        Args:
            config: The validated :class:`~agentic_scripts.config.Config`; only the
                ``agent`` section (binary, model, auto_approve, timeout_minutes) is used.
            logger: Optional logger; defaults to ``logging.getLogger("agentic_scripts.agent")``.
        """
        self._config = config
        self._log = logger or logging.getLogger("agentic_scripts.agent")

    def build_command(
        self, *, agent: str, brief: str, work_dir: Path, title: str | None = None
    ) -> list[str]:
        """Build the exact ``opencode run`` command line for one agent run.

        Args:
            agent: The OpenCode agent name (e.g. ``"oc-todo-resolver"``).
            brief: The task message; passed as the single positional argument, always LAST.
            work_dir: Directory the agent operates in (passed to ``--dir``).
            title: Optional session title (``--title``); omitted when None.

        Returns:
            The argv list, in this exact order:
            ``[binary, "run", "--agent", agent, "--format", "json", "--dir", str(work_dir)]``
            + ``["--title", title]`` if title is set + ``["--auto"]`` when
            ``config.agent.auto_approve`` + ``["--model", model]`` when
            ``config.agent.model is not None`` + ``[brief]``.

        Example:
            >>> runner.build_command(agent="noop", brief="hi", work_dir=Path("/tmp/x"))
            ['opencode', 'run', '--agent', 'noop', '--format', 'json', '--dir', '/tmp/x',
             '--auto', '--model', 'openaiCompatible/Qwen3.8-27B', 'hi']
        """
        cfg = self._config.agent
        cmd: list[str] = [
            cfg.binary,
            "run",
            "--agent",
            agent,
            "--format",
            "json",
            "--dir",
            str(work_dir),
        ]
        if title is not None:
            cmd += ["--title", title]
        if cfg.auto_approve:
            cmd += ["--auto"]
        if cfg.model is not None:
            cmd += ["--model", cfg.model]
        cmd.append(brief)
        return cmd

    def run(
        self,
        *,
        agent: str,
        brief: str,
        work_dir: Path,
        title: str | None = None,
        timeout_seconds: int | None = None,
    ) -> AgentResult:
        """Run one agent invocation and return the captured result.

        Args:
            agent: The OpenCode agent name.
            brief: The task message (positional argument).
            work_dir: Directory passed to ``--dir``; the agent's working area.
            title: Optional session title.
            timeout_seconds: Hard wall-clock timeout override in seconds; when None,
                ``config.agent.timeout_minutes * 60`` is used. On breach the whole
                process group is SIGKILLed and the result has ``status="timeout"``.

        Returns:
            An :class:`AgentResult`. Status mapping: exit 0 with >=1 ``text`` event →
            ``ok`` (final_text = last text event's ``part.text``); exit 0 with no text
            event → ``error`` ("no final text event in stream"); non-zero exit →
            ``error`` (the ``error``-event payload if present, else the stderr tail).

        Side effects:
            Spawns one subprocess in its own process group; on timeout kills the group
            with SIGKILL. Logs compact INFO lines per parsed event and a final summary.
        """
        cmd = self.build_command(agent=agent, brief=brief, work_dir=work_dir, title=title)
        timeout = (
            timeout_seconds
            if timeout_seconds is not None
            else self._config.agent.timeout_minutes * 60
        )
        deadline = time.monotonic() + timeout

        started = time.monotonic()
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,  # own process group → killpg reaches agent children
        )
        self._log.debug("agent %s started (pid=%d): %s", agent, proc.pid, " ".join(cmd))

        events: list[dict] = []
        stderr_lines: list[str] = []
        stderr_done = threading.Event()

        def _drain_stderr() -> None:
            """Drain the child's stderr into ``stderr_lines`` (daemon thread)."""
            assert proc.stderr is not None
            for raw in iter(proc.stderr.readline, b""):
                stderr_lines.append(raw.decode("utf-8", errors="replace").rstrip("\n"))
            stderr_done.set()

        stderr_thread = threading.Thread(target=_drain_stderr, daemon=True)
        stderr_thread.start()

        timed_out = False
        assert proc.stdout is not None
        while True:
            # select() bounds each readline so the deadline is checked even when the
            # child goes silent mid-stream (a blocking readline would defeat it).
            r, _, _ = select.select([proc.stdout], [], [], 0.25)
            if time.monotonic() >= deadline:
                timed_out = True
                break
            if not r:
                continue
            raw_line = proc.stdout.readline()
            if not raw_line:  # EOF
                break
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                self._log.warning(
                    "agent %s: unparseable stdout line (skipped): %r (%s)", agent, line[:200], exc
                )
                continue
            events.append(event)
            self._log.info("event %s #%d", event.get("type"), len(events))

        if timed_out:
            self._kill_group(proc)
            stderr_done.wait(timeout=5)
            duration = time.monotonic() - started
            result = AgentResult(
                status="timeout",
                exit_code=None,
                final_text=_final_text(events),
                events=events,
                error=f"agent run exceeded {timeout}s",
                duration_seconds=duration,
            )
            self._log.info(
                "agent %s done status=%s exit=%s events=%d duration=%.1fs",
                agent,
                result.status,
                result.exit_code,
                len(events),
                duration,
            )
            return result

        # stdout hit EOF: the process should be exiting; give it a grace window.
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self._kill_group(proc)
        exit_code = proc.returncode
        stderr_done.wait(timeout=5)
        duration = time.monotonic() - started

        final_text = _final_text(events)
        if exit_code == 0 and final_text is not None:
            status, error = "ok", None
        elif exit_code == 0:
            status, error = "error", "no final text event in stream"
        else:
            status = "error"
            error_event = next((e for e in reversed(events) if e.get("type") == "error"), None)
            if error_event is not None:
                payload = error_event.get("error", error_event)
                error = str(payload)
            else:
                error = _tail(stderr_lines, 40) or f"agent exited with code {exit_code}"

        result = AgentResult(
            status=status,
            exit_code=exit_code,
            final_text=final_text,
            events=events,
            error=error,
            duration_seconds=duration,
        )
        self._log.info(
            "agent %s done status=%s exit=%s events=%d duration=%.1fs",
            agent,
            result.status,
            result.exit_code,
            len(events),
            duration,
        )
        return result

    def _kill_group(self, proc: subprocess.Popen) -> None:
        """SIGKILL the child's entire process group and reap it.

        Args:
            proc: The live :class:`subprocess.Popen` (started with ``start_new_session``).
        """
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except ProcessLookupError:
            pass  # already gone
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


def _final_text(events: list[dict]) -> str | None:
    """Return the ``part.text`` of the last ``type == "text"`` event, or None.

    Args:
        events: Parsed NDJSON events in stream order.

    Returns:
        The final assistant text (last text event wins — earlier ones are
        intermediate), or None when no text event was seen.
    """
    for event in reversed(events):
        if event.get("type") == "text":
            part = event.get("part")
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                return part["text"]
    return None


def _tail(lines: list[str], n: int) -> str:
    """Return the last ``n`` lines joined by newlines (empty string when no lines).

    Args:
        lines: The full line list (e.g. drained stderr).
        n: Maximum number of trailing lines to keep.
    """
    return "\n".join(lines[-n:]) if lines else ""
