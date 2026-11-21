"""Hermetic tests for the OpenCode service active-session probe (``sessions``).

No real home dir, no network: the service-state path is always a ``tmp_path`` file and
the ``_urlopen`` seam is monkeypatched with a fake that returns canned bodies (or raises)
so every probe-failure path is exercised without touching the real OpenCode service.
"""

from __future__ import annotations

import base64
import json
import urllib.error
from pathlib import Path

import pytest

from agentic_scripts import sessions
from agentic_scripts.sessions import (
    ServiceState,
    active_session_count,
    read_active_sessions,
    read_service_state,
)


class _FakeResp:
    """A context-manager response whose ``read`` returns a fixed body."""

    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self) -> bytes:
        """Return the canned response body (single-read semantics, like a socket)."""
        return self._body

    def __enter__(self) -> _FakeResp:
        return self

    def __exit__(self, *exc) -> bool:
        return False


def _patch_urlopen(
    monkeypatch: pytest.MonkeyPatch, *, body: bytes | None = None, exc: Exception | None = None
) -> list[tuple[object, object]]:
    """Point ``agentic_scripts.sessions._urlopen`` at a canned fake and record its calls.

    Args:
        monkeypatch: The pytest monkeypatch fixture.
        body: The canned response body (default ``b"{}"``).
        exc: When set, the fake raises this instead of returning a response.

    Returns:
        The list of ``(request, timeout)`` call tuples recorded during the test.
    """
    calls: list[tuple[object, object]] = []

    def fake(req, timeout=None):
        calls.append((req, timeout))
        if exc is not None:
            raise exc
        return _FakeResp(body if body is not None else b"{}")

    monkeypatch.setattr(sessions, "_urlopen", fake)
    return calls


def _state_file(tmp_path: Path, **overrides: object) -> Path:
    """Write a valid service.json under ``tmp_path`` and return its path.

    Args:
        tmp_path: The pytest temporary directory.
        **overrides: Values to replace in the default (valid) state mapping (tests that
            delete a key build the mapping themselves).

    Returns:
        The path of the written ``service.json``.
    """
    data = {
        "id": "svc-1",
        "version": "1.0",
        "url": "http://127.0.0.1:49374",
        "pid": 4242,
        "password": "s3cret",
    }
    data.update(overrides)
    path = tmp_path / "service.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _state() -> ServiceState:
    """Return a valid :class:`ServiceState` for probe tests (no I/O involved)."""
    return ServiceState(url="http://127.0.0.1:1", password="pw", pid=None)


# --- read_service_state --------------------------------------------------------


def test_read_service_state_valid(tmp_path: Path) -> None:
    """A valid state file parses to url/password/pid."""
    path = _state_file(tmp_path)
    state = read_service_state(path)
    assert state == ServiceState(url="http://127.0.0.1:49374", password="s3cret", pid=4242)


def test_read_service_state_missing_file(tmp_path: Path) -> None:
    """A nonexistent path yields None (no exception)."""
    assert read_service_state(tmp_path / "no-such" / "service.json") is None


def test_read_service_state_corrupt_json(tmp_path: Path) -> None:
    """A file that is not valid JSON yields None (no exception)."""
    path = tmp_path / "service.json"
    path.write_text("{not-json", encoding="utf-8")
    assert read_service_state(path) is None


def test_read_service_state_not_a_mapping(tmp_path: Path) -> None:
    """A JSON value that is not an object yields None."""
    path = tmp_path / "service.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")
    assert read_service_state(path) is None


@pytest.mark.parametrize("key", ["url", "password"])
def test_read_service_state_missing_required_key(tmp_path: Path, key: str) -> None:
    """A missing ``url`` or ``password`` key yields None."""
    data = {
        "id": "svc-1",
        "url": "http://127.0.0.1:1",
        "pid": 1,
        "password": "pw",
    }
    del data[key]
    path = tmp_path / "service.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    assert read_service_state(path) is None


def test_read_service_state_missing_pid_defaults_none(tmp_path: Path) -> None:
    """A missing ``pid`` key is valid; the state carries ``pid=None``."""
    data = {
        "id": "svc-1",
        "url": "http://127.0.0.1:1",
        "password": "pw",
    }
    path = tmp_path / "service.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    state = read_service_state(path)
    assert state is not None
    assert state.pid is None
    assert state.url == "http://127.0.0.1:1"
    assert state.password == "pw"


def test_read_service_state_non_int_pid(tmp_path: Path) -> None:
    """A non-integer ``pid`` is invalid (yields None)."""
    path = _state_file(tmp_path, pid="not-an-int")
    assert read_service_state(path) is None


# --- active_session_count ------------------------------------------------------


def test_active_session_count_none_state() -> None:
    """No service state → 0, with no HTTP call at all."""
    assert active_session_count(None) == 0


@pytest.mark.parametrize("count", [0, 1, 5])
def test_active_session_count_counts_data_keys(monkeypatch: pytest.MonkeyPatch, count: int) -> None:
    """A body with N data keys → N (one key per open interactive session)."""
    body = json.dumps({"data": {f"s{i}": {"type": "running"} for i in range(count)}}).encode()
    calls = _patch_urlopen(monkeypatch, body=body)
    assert active_session_count(_state()) == count
    # The request targets <url>/api/session/active and honours the timeout kwarg.
    req, timeout = calls[0]
    assert str(req.full_url).endswith("/api/session/active")
    assert timeout == 5


def test_active_session_count_sends_basic_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    """The request carries HTTP Basic auth 'opencode:<password>' (live-verified scheme)."""
    calls = _patch_urlopen(monkeypatch, body=b'{"data": {}}')
    active_session_count(_state())
    req, _ = calls[0]
    header = req.get_header("Authorization")
    token = base64.b64decode(header.removeprefix("Basic ")).decode("utf-8")
    assert token == "opencode:pw"


@pytest.mark.parametrize(
    "exc",
    [
        urllib.error.HTTPError("http://127.0.0.1:1", 401, "Unauthorized", {}, None),
        urllib.error.URLError("Connection refused"),
        TimeoutError("timed out"),
    ],
    ids=["http-error", "transport-error", "timeout"],
)
def test_active_session_count_probe_failure_returns_zero(
    monkeypatch: pytest.MonkeyPatch, exc: Exception
) -> None:
    """Any transport/HTTP/timeout failure → 0 without raising (treated as idle)."""
    _patch_urlopen(monkeypatch, exc=exc)
    assert active_session_count(_state()) == 0


def test_active_session_count_non_json_body(monkeypatch: pytest.MonkeyPatch) -> None:
    """A non-JSON response body → 0 without raising (treated as idle)."""
    _patch_urlopen(monkeypatch, body=b"not-json{{")
    assert active_session_count(_state()) == 0


def test_active_session_count_missing_data_mapping(monkeypatch: pytest.MonkeyPatch) -> None:
    """A JSON body without a 'data' mapping → 0 without raising (treated as idle)."""
    _patch_urlopen(monkeypatch, body=b'{"other": 1}')
    assert active_session_count(_state()) == 0


def test_active_session_count_data_not_a_mapping(monkeypatch: pytest.MonkeyPatch) -> None:
    """A 'data' value that is not a mapping → 0 without raising (treated as idle)."""
    _patch_urlopen(monkeypatch, body=b'{"data": ["s1"]}')
    assert active_session_count(_state()) == 0


# --- read_active_sessions (state path + probe in one) ---------------------------


def test_read_active_sessions_uses_state_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """read_active_sessions(path) reads the state at path and counts probe sessions."""
    _state_file(tmp_path)
    _patch_urlopen(monkeypatch, body=b'{"data": {"a": {}, "b": {}}}')
    assert read_active_sessions(tmp_path / "service.json") == 2


def test_read_active_sessions_missing_state(tmp_path: Path) -> None:
    """No state file at the given path → 0 (no probe attempted, no exception)."""
    assert read_active_sessions(tmp_path / "missing" / "service.json") == 0
