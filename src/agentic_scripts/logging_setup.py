"""Run-logging setup and last-run summary writer for agentic_scripts.

Purpose:
    Create a per-run logger that writes to ``logs/run-<run_id>.log`` (always at INFO)
    plus an optional stderr handler, and provide a helper to record the most recent
    run's human-readable summary in ``logs/last-run.txt`` for post-hoc auditing.

Rationale:
    The scheduler is unattended and must be auditable without a dashboard. A stable
    UTC-based run id keeps log files sortable and unique across timer firings; a
    dedicated logger (no propagation to root) avoids duplicate stderr lines while still
    letting ``--verbose`` surface INFO on the console.

Usage:
    >>> from agentic_scripts.logging_setup import new_run_id, setup_run_logger
    >>> run_id = new_run_id()
    >>> logger, log_path = setup_run_logger(Path("logs"), run_id, verbose=True)
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from pathlib import Path


def new_run_id() -> str:
    """Generate a unique, sortable UTC run identifier.

    Returns:
        A timestamp string in the form ``%Y%m%dT%H%M%SZ`` (e.g.
        ``20261021T083015Z``), using current UTC time. The format is stable and
        lexicographically sortable, so per-run log files order correctly on disk.

    Example:
        >>> rid = new_run_id()
        >>> len(rid) == 17 and rid.endswith("Z")
        True
    """
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def setup_run_logger(
    log_dir: Path, run_id: str, *, verbose: bool = False
) -> tuple[logging.Logger, Path]:
    """Configure and return a per-run logger writing to ``run-<run_id>.log``.

    The file handler always logs at INFO. A stderr handler is added at INFO when
    ``verbose`` is True, else at WARNING (so non-verbose runs stay quiet on the
    console but still record everything to the log file). Timestamps are rendered in
    UTC via a ``time.gmtime`` converter for deterministic, sortable asctime values.

    Args:
        log_dir: Directory for run logs; created if it does not exist.
        run_id: The run identifier (see :func:`new_run_id`); used in the log filename.
        verbose: If True, also echo INFO records to stderr; otherwise stderr is limited
            to WARNING and above.

    Returns:
        A ``(logger, log_path)`` tuple where ``log_path`` is
        ``<log_dir>/run-<run_id>.log``. The logger name is ``agentic_scripts`` and it
        does not propagate to the root logger (avoids duplicate stderr lines).

    Example:
        >>> logger, path = setup_run_logger(Path("logs"), "20261021T083015Z")
        >>> logger.name
        'agentic_scripts'
    """
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"run-{run_id}.log"

    # Render asctime in UTC so log timestamps are deterministic and sortable.
    logging.Formatter.converter = time.gmtime  # noqa: SLF001 - documented logging idiom

    logger = logging.getLogger("agentic_scripts")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    # Reset handlers so repeated calls (e.g. in tests) do not stack duplicate handlers.
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%SZ",
    )

    file_handler = logging.FileHandler(log_path, mode="a", encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    stderr_handler = logging.StreamHandler()
    stderr_handler.setLevel(logging.INFO if verbose else logging.WARNING)
    stderr_handler.setFormatter(formatter)
    logger.addHandler(stderr_handler)

    return logger, log_path


def write_last_run(log_dir: Path, lines: list[str]) -> Path:
    """Overwrite ``log_dir/last-run.txt`` with a human-readable run summary.

    Args:
        log_dir: Directory for the last-run file; created if it does not exist.
        lines: The summary lines to write, one per line (a trailing newline is added).

    Returns:
        The path of the written ``last-run.txt`` file (0644 permissions).

    Example:
        >>> path = write_last_run(Path("logs"), ["gate open", "noop ok"])
        >>> path.name
        'last-run.txt'
    """
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / "last-run.txt"
    content = "\n".join(lines) + "\n" if lines else ""
    path.write_text(content, encoding="utf-8")
    path.chmod(0o644)
    return path
