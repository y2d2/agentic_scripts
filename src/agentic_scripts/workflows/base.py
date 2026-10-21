"""Workflow protocol, result type, and shared work context.

Purpose:
    Define the contract every workflow module must satisfy (a ``create(config)`` entry
    point returning a :class:`Workflow`), the :class:`WorkflowResult` value object a
    run produces, and the :class:`WorkContext` handed to each workflow's ``run`` with
    everything it needs: validated config, durable state, a per-run logger, and lazy
    access to the git/agent primitives.

Rationale:
    The scheduler is workflow-agnostic: it imports a module, calls ``create(config)``,
    and runs the returned object against a shared context. Keeping the protocol small
    (one method) makes new workflows additive modules with no scheduler changes.
    ``WorkContext.git``/``runner`` are lazy properties that import their modules on
    first access so this file compiles before Tasks 3/4 land (parallel-safety).

Usage:
    >>> from agentic_scripts.workflows.base import Workflow, WorkContext, WorkflowResult
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

from agentic_scripts.config import Config
from agentic_scripts.state import StateStore


@dataclass
class WorkflowResult:
    """The outcome of a single workflow run.

    Attributes:
        status: One of ``"ok"``, ``"skipped"``, or ``"error"``. Business failures are
            reported as ``status="error"`` with the reasons in :attr:`errors` —
            workflows never raise for business failures (exceptions are reserved for
            programmer errors and are caught by the scheduler).
        items_found: Number of candidate items the workflow discovered this run
            (e.g. todos found, new mail messages seen). Defaults to 0.
        actions: Human-readable list of side effects the workflow performed this run.
            Defaults to an empty list.
        errors: Human-readable list of business failures encountered this run.
            Defaults to an empty list.
        duration_seconds: Wall-clock seconds the run took. Defaults to 0.0; the
            scheduler may overwrite it with its own measurement.
    """

    status: str
    items_found: int = 0
    actions: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0


@dataclass
class WorkContext:
    """Everything a workflow needs to run, shared by the scheduler with each workflow.

    Attributes:
        config: The fully validated :class:`~agentic_scripts.config.Config`.
        state: The durable per-workflow :class:`~agentic_scripts.state.StateStore`.
        logger: The per-run :class:`logging.Logger` (name ``agentic_scripts``).
        run_id: The unique run identifier for this invocation.
        workflow_name: The name of the workflow currently running.
        sandbox_dir: Directory in which the workflow may create side effects; keep all
            filesystem mutations inside here or other declared targets.
        admin_repo: Path to the admin (roadmap) repo, or None if not configured.

    Note:
        :attr:`git` and :attr:`runner` are lazy properties that import their modules on
        first access (and cache the instance). This keeps ``base.py`` importable before
        Tasks 3/4 provide those modules; a workflow that needs them will raise an
        ``ImportError`` if accessed before they land, which is acceptable because such
        workflows ship with Task 3.
    """

    config: Config
    state: StateStore
    logger: logging.Logger
    run_id: str
    workflow_name: str
    sandbox_dir: Path
    admin_repo: Path | None

    def __post_init__(self) -> None:
        """Initialize lazy caches for the git and runner properties."""
        self._git = None
        self._runner = None

    @property
    def git(self):
        """Lazily construct and cache the shared :class:`Git` helper.

        Returns:
            A ``agentic_scripts.git.Git`` instance (imported on first access).

        Raises:
            ImportError: If the ``agentic_scripts.git`` module has not landed yet
                (Task 3). Propagated so callers fail loudly rather than silently.
        """
        if self._git is None:
            from agentic_scripts.git import Git

            self._git = Git()
        return self._git

    @property
    def runner(self):
        """Lazily construct and cache the shared :class:`AgentRunner`.

        Returns:
            An ``agentic_scripts.agent.AgentRunner`` instance configured with this
            context's config and logger (imported on first access).

        Raises:
            ImportError: If the ``agentic_scripts.agent`` module has not landed yet
                (Task 3). Propagated so callers fail loudly rather than silently.
        """
        if self._runner is None:
            from agentic_scripts.agent import AgentRunner

            self._runner = AgentRunner(config=self.config, logger=self.logger)
        return self._runner


@runtime_checkable
class Workflow(Protocol):
    """The contract every workflow module's ``create(config)`` must return.

    A workflow is a stateless object whose single method performs one run against the
    shared context and reports its outcome as a :class:`WorkflowResult`.

    Attributes:
        name: The workflow's stable name, matching its key under ``workflows`` in the
            config.

    Contract (implementations MUST honor):
        1. Consult ``ctx.state`` BEFORE acting — state is the idempotency source of
           truth; re-runs must not duplicate side effects.
        2. Keep side effects inside ``ctx.sandbox_dir`` or other declared targets; never
           mutate unrelated repositories or paths.
        3. Never raise for business failures — return
           ``WorkflowResult(status="error", errors=[...])`` instead. Exceptions are
           reserved for programmer errors and are caught by the scheduler, logged, and
           do not stop other workflows from running.

    Example:
        >>> class Noop(Workflow):
        ...     name = "noop"
        ...     def run(self, ctx):
        ...         return WorkflowResult(status="ok")
    """

    name: str

    def run(self, ctx: WorkContext) -> WorkflowResult:
        """Perform one run of the workflow and report its outcome.

        Args:
            ctx: The shared :class:`WorkContext` for this invocation.

        Returns:
            A :class:`WorkflowResult` describing what was found, done, and any business
            errors encountered. Must not raise for business failures.
        """
        ...


def create(config: Config) -> Workflow:
    """Required entry point of every workflow module (documented here).

    The scheduler imports a workflow's module and calls this function with the loaded
    :class:`Config` to obtain a runnable :class:`Workflow`. Each concrete workflow
    module defines its own ``create``; this stub documents the contract.

    Args:
        config: The fully validated :class:`~agentic_scripts.config.Config`.

    Returns:
        A :class:`Workflow` instance ready for the scheduler to run.

    Raises:
        NotImplementedError: This base stub is not runnable; concrete workflow modules
            override ``create`` with their own implementation.
    """
    raise NotImplementedError("each workflow module must define its own create(config)")
