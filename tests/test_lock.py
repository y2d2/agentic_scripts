"""Hermetic tests for the skip-if-held exclusive lock (``acquire_lock``).

These exercise real ``flock`` semantics against a tmp state dir: a fresh acquire succeeds,
releasing (close) lets a second acquire succeed, and holding the lock in-test makes a
concurrent acquire return ``None`` (skip, never block).
"""

from __future__ import annotations

import fcntl
import os
from pathlib import Path

from agentic_scripts.scheduler import acquire_lock


def test_acquire_then_release_allows_reacquire(tmp_path: Path) -> None:
    """1. Fresh dir → fd not None; close → second acquire succeeds again."""
    state_dir = tmp_path / "state"
    first = acquire_lock(state_dir)
    assert first is not None

    # The lock file must exist (created, 0644).
    lock_file = state_dir / ".lock"
    assert lock_file.is_file()

    os.close(first)  # release the flock

    second = acquire_lock(state_dir)
    assert second is not None
    os.close(second)


def test_hold_lock_makes_concurrent_acquire_return_none(tmp_path: Path) -> None:
    """2. Hold a flock on the same .lock path in-test → concurrent acquire returns None."""
    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    lock_file = state_dir / ".lock"

    # Open and hold an exclusive non-blocking lock ourselves.
    held_fd = os.open(lock_file, os.O_CREAT | os.O_RDWR, 0o644)
    fcntl.flock(held_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

    try:
        # A concurrent acquire must skip (None), not block or raise.
        assert acquire_lock(state_dir) is None
    finally:
        os.close(held_fd)  # release; now a fresh acquire should succeed again

    after = acquire_lock(state_dir)
    assert after is not None
    os.close(after)
