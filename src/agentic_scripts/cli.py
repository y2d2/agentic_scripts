"""Console-script entry point for the ``agentic-scripts`` CLI.

Purpose:
    Provide the thin ``main()`` that the ``agentic-scripts`` console script (declared in
    ``pyproject.toml``) calls. It delegates entirely to :func:`agentic_scripts.scheduler.run`
    and exits with the returned code, keeping the CLI a 3-line shell over the scheduler core.

Rationale:
    Keeping the CLI minimal means all behaviour (parsing, gating, locking, logging) lives in
    ``scheduler.py`` where it is unit-testable without ``SystemExit``; this module only bridges
    the console script to that loop and maps the returned int onto the process exit code.

Usage:
    >>> agentic-scripts run --force   # operator override (see scheduler.run for details)
"""

from __future__ import annotations

import sys

from agentic_scripts.scheduler import run


def main() -> None:
    """Entry point for the ``agentic-scripts`` console script.

    Calls :func:`agentic_scripts.scheduler.run` with no arguments (so it parses
    ``sys.argv[1:]``, reads the live clock and load) and exits with the returned code.

    Returns:
        None — the function signals completion by calling :func:`sys.exit` with the
        scheduler's return value (0 = ran/skipped/gate-closed, 2 = config/usage fault).

    Example:
        >>> import agentic_scripts.cli as cli
        >>> cli.main()   # runs `agentic-scripts run` against sys.argv[1:]
    """
    sys.exit(run())
