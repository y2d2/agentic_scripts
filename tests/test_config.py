"""Tests for config loading and fail-fast validation.

Covers: the shipped config loads with correct resolved paths/order/agents; missing or
unknown sections are rejected naming the field; each machine/agent/workflow field is
validated (bad HH:MM, negative threshold, out-of-range gate polls, zero-width window);
and enabled workflow modules must import and expose ``create(config)``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from agentic_scripts.config import PROJECT_ROOT, ConfigError, load_config


def _write(tmp_path: Path, data: dict) -> Path:
    """Write a config dict to a temp YAML file and return its path.

    Args:
        tmp_path: The pytest temporary directory.
        data: The config mapping to serialize.

    Returns:
        The path of the written ``workflows.yaml``.
    """
    path = tmp_path / "workflows.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path


def _base(tmp_path: Path) -> dict:
    """Return a deep copy of the shipped config as a mutable dict.

    Args:
        tmp_path: The pytest temporary directory (used to resolve the shipped file).

    Returns:
        A fresh, mutable copy of the canonical config mapping.
    """
    root = Path(__file__).resolve().parents[1]
    return yaml.safe_load((root / "config" / "workflows.yaml").read_text(encoding="utf-8"))


def test_shipped_config_loads(project_root: Path) -> None:
    """The shipped config loads; paths resolve absolute under PROJECT_ROOT; order/agent."""
    cfg = load_config(project_root / "config" / "workflows.yaml")

    # state_dir is absolute and rooted at PROJECT_ROOT.
    assert cfg.paths.state_dir.is_absolute()
    assert (
        PROJECT_ROOT in cfg.paths.state_dir.parents or cfg.paths.state_dir == PROJECT_ROOT / "state"
    )
    assert str(cfg.paths.state_dir).startswith(str(PROJECT_ROOT))

    # Workflow order preserved from YAML: [noop].
    assert [w.name for w in cfg.workflows] == ["noop"]
    # noop has no agent.
    assert cfg.workflows[0].agent is None


def test_missing_machine_section(tmp_path: Path) -> None:
    """A missing `machine` section raises ConfigError naming `machine`."""
    data = _base(tmp_path)
    del data["machine"]
    with pytest.raises(ConfigError) as exc:
        load_config(_write(tmp_path, data))
    assert "machine" in str(exc.value)


def test_bad_quiet_window_start(tmp_path: Path) -> None:
    """An invalid HH:MM start raises ConfigError naming machine.quiet_window.start."""
    data = _base(tmp_path)
    data["machine"]["quiet_window"]["start"] = "25:99"
    with pytest.raises(ConfigError) as exc:
        load_config(_write(tmp_path, data))
    assert "machine.quiet_window.start" in str(exc.value)


def test_negative_load_threshold(tmp_path: Path) -> None:
    """A non-positive load threshold raises ConfigError naming machine.load_threshold."""
    data = _base(tmp_path)
    data["machine"]["load_threshold"] = -1
    with pytest.raises(ConfigError) as exc:
        load_config(_write(tmp_path, data))
    assert "machine.load_threshold" in str(exc.value)


def test_bad_gate_polls_required(tmp_path: Path) -> None:
    """A gate_polls_required outside {1,2} names machine.gate_polls_required."""
    data = _base(tmp_path)
    data["machine"]["gate_polls_required"] = 3
    with pytest.raises(ConfigError) as exc:
        load_config(_write(tmp_path, data))
    assert "machine.gate_polls_required" in str(exc.value)


def test_unknown_top_level_section(tmp_path: Path) -> None:
    """An unknown top-level section raises ConfigError naming it."""
    data = _base(tmp_path)
    data["bogus"] = {"x": 1}
    with pytest.raises(ConfigError) as exc:
        load_config(_write(tmp_path, data))
    assert "bogus" in str(exc.value)


def test_enabled_workflow_module_missing(tmp_path: Path) -> None:
    """An enabled workflow whose module cannot be imported names workflows.<name>.module."""
    data = _base(tmp_path)
    data["workflows"]["ghost"] = {
        "enabled": True,
        "module": "agentic_scripts.workflows.does_not_exist",
        "agent": None,
    }
    with pytest.raises(ConfigError) as exc:
        load_config(_write(tmp_path, data))
    assert "workflows.ghost.module" in str(exc.value)


def test_agent_model_null_loads(tmp_path: Path) -> None:
    """A null agent.model is valid and loads as None."""
    data = _base(tmp_path)
    data["agent"]["model"] = None
    cfg = load_config(_write(tmp_path, data))
    assert cfg.agent.model is None


def test_quiet_window_start_equals_end_rejected(tmp_path: Path) -> None:
    """A zero-width window (start == end) is rejected."""
    data = _base(tmp_path)
    data["machine"]["quiet_window"]["start"] = "08:00"
    data["machine"]["quiet_window"]["end"] = "08:00"
    with pytest.raises(ConfigError):
        load_config(_write(tmp_path, data))
