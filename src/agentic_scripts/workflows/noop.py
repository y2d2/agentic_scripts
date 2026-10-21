"""No-op demo workflow proving the registry mechanism end-to-end.

Purpose:
    Provide a trivially safe, side-effect-free workflow that records a run counter in
    durable state and reports success. It exercises the full registry path — config
    import-check, ``create(config)``, scheduling, per-run logging, and state
    round-trip — without touching any external system, so it is ideal for smoke tests
    and as the default registered workflow.

Rationale:
    A real workflow needs a repo/agent/mail to be meaningful; the noop gives the base
    an always-runnable unit that accumulates state across runs (proving idempotent
    accumulation) while never mutating anything outside the gitignored state area.

Usage:
    >>> from agentic_scripts.workflows.noop import create
    >>> wf = create(config)   # config is a loaded Config
    >>> wf.name
    'noop'
"""

from __future__ import annotations

from agentic_scripts.config import Config
from agentic_scripts.workflows.base import WorkflowResult


class NoopWorkflow:
    """A workflow that does nothing except record that it ran.

    Each run increments the ``runs`` counter in the ``noop`` state document and logs
    the new count at INFO. It never raises for business reasons and never touches any
    external system.

    Attributes:
        name: The stable workflow name, matching its config key (``"noop"``).
    """

    name = "noop"

    def run(self, ctx) -> WorkflowResult:
        """Record one noop run in durable state and report success.

        Args:
            ctx: The shared :class:`~agentic_scripts.workflows.base.WorkContext`. Used
                for its ``state`` store (to increment the run counter) and ``logger``
                (to log the recorded count at INFO).

        Returns:
            A :class:`WorkflowResult` with ``status="ok"``, ``items_found=0``, and a
            single action describing the recorded run number.

        Example:
            >>> result = NoopWorkflow().run(ctx)
            >>> result.status
            'ok'
        """
        new = ctx.state.update("noop", "runs", ctx.state.load("noop").get("runs", 0) + 1)
        ctx.logger.info("noop: run recorded (n=%s)", new)
        return WorkflowResult(status="ok", items_found=0, actions=[f"noop run #{new} recorded"])


def create(config: Config):
    """Create and return a :class:`NoopWorkflow` instance.

    Entry point called by the scheduler (and required of every workflow module). The
    ``config`` argument is accepted for contract uniformity but not used by the noop,
    which needs no configuration-specific behaviour.

    Args:
        config: The fully validated :class:`~agentic_scripts.config.Config`.

    Returns:
        A new :class:`NoopWorkflow`, ready to be run by the scheduler.
    """
    return NoopWorkflow()
