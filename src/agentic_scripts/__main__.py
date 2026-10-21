"""Package ``__main__`` so ``python -m agentic_scripts`` works.

Purpose:
    Make the package runnable as a module (``python -m agentic_scripts run --force``) by
    delegating to :func:`agentic_scripts.cli.main`, which in turn calls
    :func:`agentic_scripts.scheduler.run`. This mirrors the ``agentic-scripts`` console
    script so both invocation styles behave identically.

Rationale:
    A module entry point is convenient for tests and for hosts without the installed
    console script; keeping it a one-line delegation ensures the CLI surface stays in one
    place (``cli.main``) and cannot drift from the scheduler core.

Usage:
    >>> python -m agentic_scripts run --help
"""

from __future__ import annotations

from agentic_scripts.cli import main

if __name__ == "__main__":
    main()
