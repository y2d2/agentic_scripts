"""Shared pytest fixtures for agentic_scripts tests.

All fixtures are hermetic: they build isolated temporary workspaces under ``tmp_path``
and never touch the real repo's gitignored areas or any external system. Git-identity
env vars are deliberately NOT set here — the git tests in Task 3 set their own.
"""

from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml

from agentic_scripts.config import Config, load_config


@pytest.fixture
def project_root() -> Path:
    """Return the repository root, computed from this conftest's location.

    Returns:
        The absolute :class:`Path` to the repo root (one level above ``tests/``).
    """
    return Path(__file__).resolve().parents[1]


@pytest.fixture
def tmp_workspace(tmp_path: Path) -> dict[str, Path]:
    """Create an isolated state/log/sandbox workspace under ``tmp_path``.

    Returns:
        A dict with keys ``state``, ``logs``, and ``sandbox``, each mapping to the
        corresponding (already created) directory under ``tmp_path``.
    """
    dirs = {name: tmp_path / name for name in ("state", "logs", "sandbox")}
    for path in dirs.values():
        path.mkdir(parents=True, exist_ok=True)
    return dirs


@pytest.fixture
def base_config(tmp_path: Path, tmp_workspace: dict[str, Path]) -> Config:
    """Load a temp copy of the shipped config with paths pointed at the tmp workspace.

    The shipped ``config/workflows.yaml`` is read, its ``paths`` section rewritten to
    point at the hermetic ``tmp_workspace`` directories (as absolute paths), written to
    a temp file, and loaded through :func:`load_config` so full validation runs.

    Returns:
        A fully validated :class:`Config` whose state/log/sandbox dirs live under
        ``tmp_path`` — safe to mutate in tests without touching the real repo.
    """
    project_root = Path(__file__).resolve().parents[1]
    shipped = yaml.safe_load(
        (project_root / "config" / "workflows.yaml").read_text(encoding="utf-8")
    )
    data = copy.deepcopy(shipped)
    data["paths"] = {
        "state_dir": str(tmp_workspace["state"]),
        "log_dir": str(tmp_workspace["logs"]),
        "sandbox_dir": str(tmp_workspace["sandbox"]),
    }
    cfg_path = tmp_path / "workflows.yaml"
    cfg_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return load_config(cfg_path)
