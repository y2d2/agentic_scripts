"""Tests for the durable per-workflow state store.

Covers: save/load round-trip (including nested dicts and unicode), missing-file load
yielding an empty dict, corrupt files raising StateError (naming the path), update/delete
semantics, delete of a missing key returning None, and atomic-write shape (no ``*.tmp``
left behind after a save).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agentic_scripts.state import StateError, StateStore


def test_save_load_roundtrip(tmp_path: Path) -> None:
    """A saved dict round-trips exactly, including nested dicts and unicode."""
    store = StateStore(tmp_path / "state")
    data = {"runs": 3, "nested": {"a": [1, 2, 3], "b": "café — ünïcode"}, "flag": True}
    store.save("wf", data)
    assert store.load("wf") == data


def test_load_missing_returns_empty(tmp_path: Path) -> None:
    """Loading a name with no file returns an empty dict (no error)."""
    store = StateStore(tmp_path / "state")
    assert store.load("never-saved") == {}


def test_corrupt_file_raises_stateerror(tmp_path: Path) -> None:
    """A corrupt state file raises StateError whose message names the path."""
    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    bad = state_dir / "broken.json"
    bad.write_bytes(b"{ this is not valid json")

    store = StateStore(state_dir)
    with pytest.raises(StateError) as exc:
        store.load("broken")
    assert str(bad) in str(exc.value)


def test_update_and_delete_semantics(tmp_path: Path) -> None:
    """update sets a key (returning the value); delete removes it (returning the old)."""
    store = StateStore(tmp_path / "state")

    returned = store.update("wf", "count", 1)
    assert returned == 1
    assert store.load("wf") == {"count": 1}

    # update overwrites an existing key.
    store.update("wf", "count", 2)
    assert store.load("wf") == {"count": 2}

    removed = store.delete("wf", "count")
    assert removed == 2
    assert store.load("wf") == {}


def test_delete_missing_key_returns_none(tmp_path: Path) -> None:
    """Deleting a key that is not present returns None and changes nothing."""
    store = StateStore(tmp_path / "state")
    store.save("wf", {"keep": 1})
    assert store.delete("wf", "absent") is None
    assert store.load("wf") == {"keep": 1}


def test_atomic_write_leaves_no_tmp(tmp_path: Path) -> None:
    """After a save, the target file exists and no ``*.tmp`` remains in state_dir."""
    state_dir = tmp_path / "state"
    store = StateStore(state_dir)
    store.save("wf", {"a": 1})

    target = state_dir / "wf.json"
    assert target.is_file()
    assert list(state_dir.glob("*.tmp")) == []
