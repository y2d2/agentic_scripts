"""Per-workflow durable state store with atomic writes.

Purpose:
    Provide a small JSON-backed key-value store, one file per workflow
    (``<state_dir>/<name>.json``), that survives process restarts so workflows can be
    idempotent across timer invocations. Writes are atomic (temp file + ``os.replace``)
    so a run killed mid-write never leaves a torn/partial JSON file on disk.

Rationale:
    Re-runs are the norm under a timer; every workflow must consult state BEFORE acting
    to avoid duplicating side effects. A crashed mid-write run must not corrupt the
    previous good state — hence the write-then-replace protocol. Corrupt files raise
    :class:`StateError` (no silent reset) so data loss is loud, not hidden.

Usage:
    >>> from pathlib import Path
    >>> store = StateStore(Path("state"))
    >>> store.update("noop", "runs", 1)
    1
    >>> store.load("noop")
    {'runs': 1}
"""

from __future__ import annotations

import json
import os
from pathlib import Path


class StateError(RuntimeError):
    """Raised when a state file cannot be read or is corrupt.

    The message always includes the offending file path so operators can locate and
    inspect the bad file. Corrupt JSON raises this rather than silently resetting to
    an empty dict — silent data loss would break idempotency guarantees.
    """


class StateStore:
    """Per-workflow durable state. Consult state BEFORE acting (idempotency contract).

    Each workflow owns one JSON document keyed by its stable name. The store is the
    single source of truth for "what has this workflow already done", so workflows
    must read it before taking any action that could be repeated.

    Attributes:
        state_dir: Directory holding ``<name>.json`` files. Created on demand on first
            write; reads tolerate its absence (a missing file yields an empty dict).
    """

    def __init__(self, state_dir: Path) -> None:
        """Initialize the store rooted at ``state_dir`` (not created until needed).

        Args:
            state_dir: Directory for state files. May not exist yet; it is created
                on demand by :meth:`save`/update/delete.
        """
        self.state_dir = Path(state_dir)

    def _path(self, name: str) -> Path:
        """Return the file path for a workflow's state document.

        Args:
            name: The stable workflow name (file stem).

        Returns:
            ``<state_dir>/<name>.json``.
        """
        return self.state_dir / f"{name}.json"

    def load(self, name: str) -> dict:
        """Load a workflow's state document.

        Args:
            name: The stable workflow name.

        Returns:
            The parsed JSON object (a dict). A missing file yields ``{}`` — an absent
            state is the same as "nothing recorded yet".

        Raises:
            StateError: If the file exists but contains invalid JSON (corrupt). The
                message includes the file path. No silent reset to ``{}`` occurs.
        """
        path = self._path(name)
        if not path.is_file():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise StateError(f"corrupt state file {path}: {exc}") from exc
        if not isinstance(data, dict):
            raise StateError(f"state file {path} must contain a JSON object")
        return data

    def save(self, name: str, data: dict) -> None:
        """Atomically persist a workflow's state document.

        Writes to ``<name>.json.tmp`` then ``os.replace`` over ``<name>.json``, so a
        crash mid-write leaves either the old complete file or the new complete file —
        never a torn one. Ensures the parent directory exists and sets 0644 perms.

        Args:
            name: The stable workflow name.
            data: The JSON-serializable dict to persist.

        Raises:
            StateError: If ``data`` is not JSON-serializable or the write fails.
        """
        self.state_dir.mkdir(parents=True, exist_ok=True)
        target = self._path(name)
        tmp = target.with_suffix(".json.tmp")
        try:
            payload = json.dumps(data, indent=2, ensure_ascii=False)
            tmp.write_text(payload, encoding="utf-8")
            os.chmod(tmp, 0o644)
            os.replace(tmp, target)
        except (OSError, TypeError, ValueError) as exc:
            # Best-effort cleanup of a partial temp file; the original target is intact.
            try:
                if tmp.exists():
                    tmp.unlink()
            except OSError:
                pass
            raise StateError(f"failed to write state file {target}: {exc}") from exc

    def update(self, name: str, key: str, value) -> object:
        """Set a single key in a workflow's state and persist it.

        Load-mutate-save: reads the current document, sets ``key`` to ``value``, and
        atomically writes it back.

        Args:
            name: The stable workflow name.
            key: The top-level key to set.
            value: The JSON-serializable value to store under ``key``.

        Returns:
            The value that was stored (the ``value`` argument), for convenient use in
            expressions like ``new = store.update("noop", "runs", n + 1)``.
        """
        data = self.load(name)
        data[key] = value
        self.save(name, data)
        return value

    def delete(self, name: str, key: str) -> object | None:
        """Remove a single key from a workflow's state and persist it.

        Load-mutate-save: reads the current document, drops ``key`` if present, and
        atomically writes it back.

        Args:
            name: The stable workflow name.
            key: The top-level key to remove.

        Returns:
            The value that was removed, or None if the key was not present.
        """
        data = self.load(name)
        if key in data:
            removed = data.pop(key)
            self.save(name, data)
            return removed
        return None
