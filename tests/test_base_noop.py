"""Tests for the workflow protocol, WorkContext, WorkflowResult, and the noop workflow.

Covers: ``create(config)`` returning a named workflow whose ``run`` produces an ok
result; two consecutive runs accumulating state (not resetting); and the
``WorkflowResult`` defaults.
"""

from __future__ import annotations

from pathlib import Path

from agentic_scripts.config import Config
from agentic_scripts.logging_setup import new_run_id, setup_run_logger
from agentic_scripts.state import StateStore
from agentic_scripts.workflows.base import WorkContext, WorkflowResult
from agentic_scripts.workflows.noop import create


def _build_ctx(config: Config, workspace: dict[str, Path]) -> WorkContext:
    """Build a WorkContext from a config and a tmp workspace.

    Args:
        config: A loaded :class:`Config`.
        workspace: A dict with ``state``/``logs``/``sandbox`` Paths (from the
            ``tmp_workspace`` fixture).

    Returns:
        A fully populated :class:`WorkContext` for running a workflow in tests.
    """
    logger, _ = setup_run_logger(workspace["logs"], new_run_id(), verbose=False)
    return WorkContext(
        config=config,
        state=StateStore(workspace["state"]),
        logger=logger,
        run_id=new_run_id(),
        workflow_name="noop",
        sandbox_dir=workspace["sandbox"],
        admin_repo=config.admin_repo,
    )


def test_create_and_run_noop(base_config: Config, tmp_workspace: dict[str, Path]) -> None:
    """create(config) returns a named workflow; run yields an ok result with actions."""
    wf = create(base_config)
    assert wf.name == "noop"

    ctx = _build_ctx(base_config, tmp_workspace)
    result = wf.run(ctx)

    assert result.status == "ok"
    assert result.items_found == 0
    assert len(result.actions) > 0


def test_two_runs_accumulate_state(base_config: Config, tmp_workspace: dict[str, Path]) -> None:
    """Two consecutive noop runs accumulate to runs == 2 (not reset to 1)."""
    wf = create(base_config)
    ctx = _build_ctx(base_config, tmp_workspace)

    wf.run(ctx)
    wf.run(ctx)

    assert ctx.state.load("noop")["runs"] == 2


def test_workflow_result_defaults() -> None:
    """WorkflowResult defaults: empty errors list and zero duration."""
    result = WorkflowResult(status="skipped")
    assert result.errors == []
    assert result.duration_seconds == 0.0
