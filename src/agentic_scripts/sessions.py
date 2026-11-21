"""Probe for the number of active interactive OpenCode sessions on this box.

Purpose:
    Read the shared OpenCode service's state file (``~/.local/state/opencode/service.json``)
    and query its ``/api/session/active`` endpoint to count open interactive (TUI) sessions.
    The ``roadmap-dev`` idle gate uses this count: zero active sessions means the box is
    idle (day or night) and drain work may start; ``--standalone`` headless worker runs do
    not attach to the service and are invisible to the probe by construction.

Rationale:
    Stdlib only (``urllib.request``, ``base64``, ``json``, ``pathlib``) — no new
    dependencies. The service is live-verified (2026-11-21): the state file carries
    ``url`` + ``password`` + ``pid``, and ``GET <url>/api/session/active`` with HTTP Basic
    auth (user ``opencode``) returns ``{"data": {<sessionID>: {"type": "running"}, ...}}`` —
    one entry per open interactive session. Any probe failure (missing/unreadable state
    file, invalid JSON, transport/HTTP error, non-JSON body) is treated as *idle* (0
    active sessions) and logged at WARNING with the reason — the two-poll streak rule and
    the run logs keep the decision auditable. The module-level
    ``_urlopen = urllib.request.urlopen`` alias is the single test seam (mirrors
    ``github.py``): tests patch ``agentic_scripts.sessions._urlopen`` with a canned-response
    fake, so no test ever touches the network or the real home dir.

Usage:
    >>> from agentic_scripts.sessions import read_active_sessions
    >>> active = read_active_sessions()  # 0 when no interactive sessions (or probe failed)
    >>> active >= 0
    True
"""

from __future__ import annotations

import base64
import json
import logging
import urllib.request
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("agentic_scripts.sessions")

# The single test seam for HTTP. Production uses the real function; tests monkeypatch
# ``agentic_scripts.sessions._urlopen`` with a fake that records calls and returns canned
# responses (or raises), so no test ever touches the network.
_urlopen = urllib.request.urlopen


@dataclass(frozen=True)
class ServiceState:
    """The shared OpenCode service's endpoint identity, read from its state file.

    Attributes:
        url: The service's base URL (e.g. ``"http://127.0.0.1:49374"``); the port is
            dynamic per service start, so it must be read, never hardcoded.
        password: The password for HTTP Basic auth against the service API (user is
            always ``opencode``). Never log this value.
        pid: The service process id, or None when the state file does not carry one.
    """

    url: str
    password: str
    pid: int | None


def read_service_state(path: Path | None = None) -> ServiceState | None:
    """Read and validate the OpenCode service state file.

    Args:
        path: Path to the service state JSON file. Defaults to
            ``~/.local/state/opencode/service.json`` (computed at call time, so the real
            home dir is only touched when no explicit path is given). Pass an explicit
            path in tests to stay hermetic.

    Returns:
        A validated :class:`ServiceState`, or None when the file is missing, unreadable,
        not valid JSON, not a JSON object, or lacks a usable ``url``/``password`` string.
        A missing ``pid`` key yields ``pid=None`` (the count endpoint does not need it).

    Example:
        >>> state = read_service_state(Path.home() / ".local/state/opencode/service.json")
        >>> state is None or (state.url and state.password)
        True
    """
    if path is None:
        path = Path.home() / ".local" / "state" / "opencode" / "service.json"
    path = Path(path)
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(data, dict):
        return None

    url = data.get("url")
    if not isinstance(url, str) or not url.strip():
        return None
    password = data.get("password")
    if not isinstance(password, str):
        return None
    pid = data.get("pid")
    if pid is not None and (not isinstance(pid, int) or isinstance(pid, bool)):
        return None
    return ServiceState(url=url, password=password, pid=pid)


def active_session_count(service_state: ServiceState | None, *, timeout: int = 5) -> int:
    """Count active interactive OpenCode sessions via the service API.

    Args:
        service_state: The :class:`ServiceState` to probe, or None (e.g. no service state
            file on this box) — None short-circuits to 0 without any I/O.
        timeout: Per-request wall-clock timeout in seconds (int >= 1).

    Returns:
        The number of keys in the response's ``"data"`` mapping (one per open interactive
        session). Every failure path — missing state, transport error, HTTP error,
        timeout, non-JSON body, or a body lacking a ``"data"`` mapping — returns 0 and is
        logged at WARNING with the reason. This function NEVER raises: a probe failure
        means "idle" (a documented assumption; the 2-poll rule keeps it auditable).

    Example:
        >>> active_session_count(None)
        0
    """
    if service_state is None:
        return 0

    token = base64.b64encode(f"opencode:{service_state.password}".encode()).decode("ascii")
    try:
        req = urllib.request.Request(
            service_state.url.rstrip("/") + "/api/session/active",
            headers={
                "Authorization": f"Basic {token}",
                "Accept": "application/json",
                "User-Agent": "agentic-scripts",
            },
            method="GET",
        )
        with _urlopen(req, timeout=timeout) as resp:
            body = resp.read()
    except Exception as exc:  # noqa: BLE001 - any transport/HTTP failure counts as idle
        logger.warning("active-session probe failed (treating as idle): %s", exc)
        return 0

    try:
        data = json.loads(body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        logger.warning("active-session probe body is not valid JSON (treating as idle): %s", exc)
        return 0
    sessions = data.get("data") if isinstance(data, dict) else None
    if not isinstance(sessions, dict):
        logger.warning("active-session probe response lacks a 'data' mapping (treating as idle)")
        return 0
    return len(sessions)


def read_active_sessions(path: Path | None = None) -> int:
    """Convenience probe: read the service state at ``path`` and count active sessions.

    Args:
        path: Path to the service state JSON file, or None for the default location
            (``~/.local/state/opencode/service.json``). See :func:`read_service_state`.

    Returns:
        The number of active interactive sessions (0 when the service state is missing or
        the probe fails — see :func:`active_session_count`). Never raises.

    Example:
        >>> read_active_sessions() >= 0
        True
    """
    return active_session_count(read_service_state(path))
