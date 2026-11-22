"""Shared fixtures for the hermetic smoke suite (tests/smoke/).

The smoke tests drive a REAL in-process :func:`agentic_scripts.scheduler.run` against a
copy of the SHIPPED config. Since Task 6 ships ``roadmap-dev`` enabled with ``gate: idle``,
every NON-forced run on the shipped config now evaluates the idle gate — which, unpatched,
would consult the real OpenCode service (``~/.local/state/opencode/service.json`` + an
HTTP GET). The autouse fixture below patches the probe at the scheduler's import site
(``agentic_scripts.scheduler.read_active_sessions`` — the seam T1's own run()-level
idle-gate tests use) with a canned 0-active-sessions answer, keeping the whole suite
hermetic: no real service, no network. Individual tests that need a different session
count (e.g. :mod:`tests.smoke.test_smoke_roadmap_dev`) patch the same name again — the
test-local patch takes effect (same ``monkeypatch`` instance, LIFO undo).
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _canned_active_sessions_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch the scheduler's active-session probe to a canned 0 (hermetic idle-gate input).

    See the module docstring: the shipped config now carries an enabled ``gate: idle``
    workflow, so non-forced ``run()`` calls evaluate the idle gate. A canned 0-session
    probe keeps every smoke test free of the real service (the per-test fixtures in this
    suite — MAIL_* isolation, tmp paths — keep the rest hermetic).
    """
    monkeypatch.setattr("agentic_scripts.scheduler.read_active_sessions", lambda: 0)
