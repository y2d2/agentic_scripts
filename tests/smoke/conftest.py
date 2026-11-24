"""Shared fixtures for the hermetic smoke suite (tests/smoke/).

The smoke tests drive a REAL in-process :func:`agentic_scripts.scheduler.run` against a
copy of the SHIPPED config. Whenever the shipped config registers a ``gate: idle``
workflow, every NON-forced run evaluates the idle gate — which, unpatched, would consult
the real OpenCode service (``~/.local/state/opencode/service.json`` + an HTTP GET). The
autouse fixture below patches the probe at the scheduler's import site
(``agentic_scripts.scheduler.read_active_sessions`` — the seam the run()-level idle-gate
tests use) with a canned 0-active-sessions answer, keeping the whole suite hermetic:
no real service, no network. The shipped config currently carries no ``gate: idle``
workflow, so the patch is inert until one is re-registered; tests that need a different
session count patch the same name again — the test-local patch takes effect (LIFO undo).
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _canned_active_sessions_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch the scheduler's active-session probe to a canned 0 (hermetic idle-gate input).

    See the module docstring: if the shipped config carries an enabled ``gate: idle``
    workflow, non-forced ``run()`` calls evaluate the idle gate. A canned 0-session
    probe keeps every smoke test free of the real service (the per-test fixtures in this
    suite — MAIL_* isolation, tmp paths — keep the rest hermetic).
    """
    monkeypatch.setattr("agentic_scripts.scheduler.read_active_sessions", lambda: 0)
