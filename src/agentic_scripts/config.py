"""Configuration loading and fail-fast validation for agentic_scripts.

Purpose:
    Read the canonical ``config/workflows.yaml`` into typed, frozen dataclasses and
    validate every field up front so that a misconfiguration aborts start-up with a
    human-readable message naming the offending dotted field (e.g.
    ``machine.quiet_window.start``) rather than failing deep inside a workflow run.

Rationale:
    The scheduler is timer-driven and unattended, so it must fail fast and loudly at
    load time. Relative ``paths.*`` values are resolved against :data:`PROJECT_ROOT`
    (not the process CWD — cron's CWD is not trusted) so behaviour is deterministic
    regardless of how the entry point is invoked.

Usage:
    >>> from agentic_scripts.config import load_config, PROJECT_ROOT
    >>> cfg = load_config(PROJECT_ROOT / "config" / "workflows.yaml")
    >>> cfg.machine.load_threshold
    2.0
"""

from __future__ import annotations

import importlib
import re
from dataclasses import dataclass, field
from datetime import time
from pathlib import Path
from typing import Any

import yaml

# The repo root. This file is ``src/agentic_scripts/config.py``, so two parents up
# (``agentic_scripts`` -> ``src``) is the project root. Deterministic regardless of CWD.
PROJECT_ROOT = Path(__file__).resolve().parents[2]

_HHMM_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")

# Default cap on the number of OC-todos *processed* per repo per run. A user-tunable
# knob (the ``oc_todo.max_todos_per_repo`` section field); see Task 1 plan GATE note.
DEFAULT_MAX_TODOS_PER_REPO = 3


class ConfigError(Exception):
    """Raised when the configuration file is missing, malformed, or invalid.

    Attributes:
        section_and_field: The dotted path of the offending field (e.g.
            ``machine.quiet_window.start``), used for programmatic handling.
        message: A human-readable description naming the offending field, suitable
            for CLI display (Task 2 prints it and exits 2).

    Example:
        >>> raise ConfigError("machine.load_threshold", "must be > 0")
        Traceback (most recent call last):
            ...
        agentic_scripts.config.ConfigError: machine.load_threshold must be > 0
    """

    def __init__(self, section_and_field: str, message: str) -> None:
        self.section_and_field = section_and_field
        self.message = f"{section_and_field}: {message}"
        super().__init__(self.message)


@dataclass(frozen=True)
class QuietWindow:
    """A daily quiet window in local time, possibly crossing midnight.

    Attributes:
        start: Window start as a 24h ``HH:MM`` string (e.g. ``"22:00"``).
        end: Window end as a 24h ``HH:MM`` string (e.g. ``"08:00"``).

    Note:
        A window is valid only when ``start != end``; that case is rejected at load
        time. ``in_window`` handles the midnight-crossing case (``start > end``) by
        treating the interval as wrapping around 24:00.
    """

    start: str
    end: str

    def in_window(self, dt: time) -> bool:
        """Return whether ``dt`` falls inside this window.

        Args:
            dt: A wall-clock :class:`datetime.time` (no date component).

        Returns:
            True if ``dt`` is within the quiet window, else False. For a
            midnight-crossing window (``start > end``) the interval wraps:
            ``dt >= start or dt < end``. For ``start < end`` it is the simple
            ``start <= dt < end``.

        Example:
            >>> QuietWindow("22:00", "08:00").in_window(time(23, 30))
            True
            >>> QuietWindow("22:00", "08:00").in_window(time(12, 0))
            False
        """
        start = _parse_hhmm(self.start, "quiet_window.start")
        end = _parse_hhmm(self.end, "quiet_window.end")
        if start > end:  # crosses midnight
            return dt >= start or dt < end
        return start <= dt < end


@dataclass(frozen=True)
class Machine:
    """Machine-level scheduling parameters (gate inputs and cadence).

    Attributes:
        quiet_window: The daily quiet window during which the gate may open.
        load_threshold: 1-minute load average must be STRICTLY below this to count
            as idle. Must be > 0.
        poll_interval_minutes: Nominal timer cadence in minutes. Must be an int >= 1.
        gate_polls_required: Consecutive idle polls needed to open the gate; allowed
            values are 1 or 2.
        gate_poll_tolerance_minutes: Maximum gap (minutes) between consecutive idle
            polls before the streak resets. Must be an int >= 0.
    """

    quiet_window: QuietWindow
    load_threshold: float
    poll_interval_minutes: int
    gate_polls_required: int
    gate_poll_tolerance_minutes: int


@dataclass(frozen=True)
class Agent:
    """Agent-runner parameters shared by all workflows that spawn an agent.

    Attributes:
        binary: The agent CLI binary name (e.g. ``"opencode"``). Non-empty string.
        model: Model identifier to pass to the agent, or None to use the agent's own
            frontmatter model.
        max_steps: Informational step budget; the live cap is the agent frontmatter
            ``steps``. Must be an int >= 1.
        timeout_minutes: Per-workflow hard timeout for the agent run in minutes. Must
            be an int >= 1.
        auto_approve: Whether to pass ``--auto`` to the agent CLI.
    """

    binary: str
    model: str | None
    max_steps: int
    timeout_minutes: int
    auto_approve: bool


@dataclass(frozen=True)
class Paths:
    """Resolved filesystem locations for state, logs, and sandbox.

    Attributes:
        state_dir: Durable per-workflow state directory (absolute).
        log_dir: Run-log directory (absolute).
        sandbox_dir: Sandbox directory for workflow side effects (absolute).

    Note:
        Relative values in the config are resolved against :data:`PROJECT_ROOT` at
        load time; absolute values pass through unchanged.
    """

    state_dir: Path
    log_dir: Path
    sandbox_dir: Path


@dataclass(frozen=True)
class WorkflowEntry:
    """A single registered workflow.

    Attributes:
        name: The workflow's stable name (the key under ``workflows`` in the YAML).
        enabled: Whether the workflow is active; disabled entries are skipped by the
            scheduler and their modules are not import-checked.
        module: Dotted importable path to the workflow module, which must expose a
            ``create(config) -> Workflow`` entry point.
        agent: The OpenCode agent name this workflow spawns, or None for workflows
            that do not spawn an agent.
        gate: Which scheduler gate gates this workflow: ``"quiet_window"`` (the default;
            the machine-global quiet-window + load gate) or ``"idle"`` (the session-based
            idle gate — the workflow runs on every non-skipped fire and makes its own
            drain decision from ``WorkContext.gate_open``).
    """

    name: str
    enabled: bool
    module: str
    agent: str | None
    gate: str = "quiet_window"


@dataclass(frozen=True)
class OCTodo:
    """OC-todo workflow settings (repos to scan, caps, per-repo overrides).

    Attributes:
        repos: Ordered list of GitHub repo ids in ``owner/name`` form. An empty list
            means the workflow has nothing to scan and no-ops for that run.
        max_todos_per_repo: Maximum number of OC-todos *processed* per repo per run.
            Must be an int >= 1; defaults to :data:`DEFAULT_MAX_TODOS_PER_REPO`.
        test_commands: Optional per-repo test command (e.g. ``"uv run pytest"``). Keys
            must be members of :attr:`repos`; values are non-empty strings. Empty when
            no overrides are configured.
        repo_urls: Optional clone-URL override per repo (a local path or a URL; the
            hermetic-test/mirror seam). Keys must be members of :attr:`repos`; values
            are non-empty strings. Empty when no overrides are configured.

    Note:
        An empty ``repos`` list means the workflow no-ops: there is nothing to scan, so
        downstream tasks (3–5) skip the run entirely.
    """

    repos: list[str]
    max_todos_per_repo: int
    test_commands: dict[str, str]
    repo_urls: dict[str, str]


_EMPTY_OC_TODO = OCTodo(
    repos=[],
    max_todos_per_repo=DEFAULT_MAX_TODOS_PER_REPO,
    test_commands={},
    repo_urls={},
)


# Default per-job hard timeout (minutes) for roadmap-dev execution runs.
DEFAULT_RUN_TIMEOUT_MINUTES = 480


@dataclass(frozen=True)
class RoadmapPrompts:
    """Roadmap-dev workflow execution parameters (repos to scan, listing, caps).

    Attributes:
        allowed_repos: Ordered list of GitHub repo ids in ``owner/name`` form to scan for
            un-archived plans. An empty list means the workflow has nothing to scan and
            no-ops for that run.
        listing_repo: The live plan-listing repo as ``owner/name`` (e.g.
            ``y2d2/ARP_prompts``); empty string when the section is absent.
        listing_repo_url: Optional clone-URL override for the listing repo (a local path
            or URL; the hermetic-test/mirror seam). Empty string (default) derives
            ``git@github.com:<listing_repo>.git``.
        listing_path: The listing file inside the listing repo (e.g. ``plans.md``).
            Empty string when the section is absent.
        listing_branch: The branch holding the listing (e.g. ``main``). Empty string when
            the section is absent.
        run_timeout_minutes: Per-job hard timeout for an execution run in minutes. Must be
            an int >= 1; defaults to :data:`DEFAULT_RUN_TIMEOUT_MINUTES`.
        test_commands: Optional per-repo test command (e.g. ``"uv run pytest"``). Keys must
            be members of :attr:`allowed_repos`; values are non-empty strings. Empty when
            no overrides are configured.
        repo_urls: Optional clone-URL override per repo (a local path or a URL; the
            hermetic-test/mirror seam). Keys must be members of :attr:`allowed_repos`;
            values are non-empty strings. Empty when no overrides are configured.

    Note:
        An empty ``allowed_repos`` list means the workflow no-ops: there is nothing to
        scan, so the run exits 0 without any state file or sandbox.
    """

    allowed_repos: list[str]
    listing_repo: str
    listing_repo_url: str
    listing_path: str
    listing_branch: str
    run_timeout_minutes: int
    test_commands: dict[str, str]
    repo_urls: dict[str, str]


_EMPTY_ROADMAP_PROMPTS = RoadmapPrompts(
    allowed_repos=[],
    listing_repo="",
    listing_repo_url="",
    listing_path="",
    listing_branch="",
    run_timeout_minutes=DEFAULT_RUN_TIMEOUT_MINUTES,
    test_commands={},
    repo_urls={},
)


@dataclass(frozen=True)
class Config:
    """The fully validated, typed agentic_scripts configuration.

    Attributes:
        machine: Machine-level scheduling parameters.
        agent: Shared agent-runner parameters.
        paths: Resolved state/log/sandbox directories.
        admin_repo: Path to the admin (roadmap) repo, or None if not configured.
        workflows: Registered workflow entries, preserving YAML document order.
        oc_todo: OC-todo workflow settings; empty defaults when the ``oc_todo`` section
            is absent.
        roadmap_prompts: Roadmap-dev execution parameters; empty defaults when the
            ``roadmap_prompts`` section is absent (the workflow no-ops).
    """

    machine: Machine
    agent: Agent
    paths: Paths
    admin_repo: Path | None
    workflows: list[WorkflowEntry]
    oc_todo: OCTodo = field(default_factory=lambda: _EMPTY_OC_TODO)
    roadmap_prompts: RoadmapPrompts = field(default_factory=lambda: _EMPTY_ROADMAP_PROMPTS)


def _parse_hhmm(value: Any, field: str) -> time:
    """Parse a ``HH:MM`` string into a :class:`datetime.time`.

    Args:
        value: A 24-hour clock string with two-digit hour and minute.
        field: The dotted field name of the value (e.g.
            ``machine.quiet_window.start``), used in error messages so the offending
            field is named precisely.

    Returns:
        The corresponding :class:`datetime.time`.

    Raises:
        ConfigError: If the value is not a valid ``HH:MM`` string, naming ``field``.
    """
    if not isinstance(value, str):
        raise ConfigError(field, f"expected HH:MM string, got {type(value).__name__}")
    m = _HHMM_RE.match(value)
    if not m:
        raise ConfigError(field, f"'{value}' is not a valid 24h HH:MM time")
    return time(int(m.group(1)), int(m.group(2)))


def _require_mapping(section: str, data: Any) -> dict[str, Any]:
    """Ensure ``data`` is a mapping and return it.

    Args:
        section: The dotted field name of the section, for error messages.
        data: The value to check.

    Returns:
        The mapping.

    Raises:
        ConfigError: If ``data`` is not a dict/mapping.
    """
    if not isinstance(data, dict):
        raise ConfigError(section, f"expected a mapping, got {type(data).__name__}")
    return data


def _require_key(section: str, data: dict[str, Any], key: str) -> Any:
    """Return ``data[key]`` or raise a ConfigError naming the missing field.

    Args:
        section: The dotted path of the parent section.
        data: The mapping to read from.
        key: The key that must be present.

    Returns:
        The value stored under ``key``.

    Raises:
        ConfigError: If ``key`` is absent from ``data``.
    """
    if key not in data:
        raise ConfigError(f"{section}.{key}", "required key is missing")
    return data[key]


def _resolve_path(value: Any, field: str) -> Path:
    """Resolve a config path value against PROJECT_ROOT.

    Args:
        value: A string path (relative or absolute).
        field: The dotted field name, for error messages.

    Returns:
        An absolute :class:`Path`. Relative values are resolved against
        :data:`PROJECT_ROOT`; absolute values pass through unchanged.

    Raises:
        ConfigError: If the value is not a non-empty string.
    """
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(field, "must be a non-empty path string")
    p = Path(value)
    return p if p.is_absolute() else (PROJECT_ROOT / p)


def _load_machine(data: dict[str, Any]) -> Machine:
    """Validate and build the ``machine`` section.

    Args:
        data: The raw mapping under the ``machine`` key.

    Returns:
        A validated :class:`Machine`.

    Raises:
        ConfigError: If any machine field is missing or invalid, naming the field.
    """
    section = "machine"
    quiet_raw = _require_mapping(
        f"{section}.quiet_window", _require_key(section, data, "quiet_window")
    )
    start = _require_key(f"{section}.quiet_window", quiet_raw, "start")
    end = _require_key(f"{section}.quiet_window", quiet_raw, "end")
    # Parse both to validate HH:MM format (raises ConfigError naming the field).
    start_t = _parse_hhmm(start, f"{section}.quiet_window.start")
    end_t = _parse_hhmm(end, f"{section}.quiet_window.end")
    if start_t == end_t:
        raise ConfigError(
            f"{section}.quiet_window.start",
            "quiet window start must differ from end (a zero-width window is invalid)",
        )

    load_threshold = _require_key(section, data, "load_threshold")
    if not isinstance(load_threshold, (int, float)) or isinstance(load_threshold, bool):
        raise ConfigError(f"{section}.load_threshold", "must be a number")
    if load_threshold <= 0:
        raise ConfigError(f"{section}.load_threshold", "must be > 0")

    poll_interval = _require_key(section, data, "poll_interval_minutes")
    if not isinstance(poll_interval, int) or isinstance(poll_interval, bool):
        raise ConfigError(f"{section}.poll_interval_minutes", "must be an integer")
    if poll_interval < 1:
        raise ConfigError(f"{section}.poll_interval_minutes", "must be >= 1")

    gate_polls = _require_key(section, data, "gate_polls_required")
    if not isinstance(gate_polls, int) or isinstance(gate_polls, bool):
        raise ConfigError(f"{section}.gate_polls_required", "must be an integer")
    if gate_polls not in (1, 2):
        raise ConfigError(f"{section}.gate_polls_required", "must be 1 or 2")

    tolerance = _require_key(section, data, "gate_poll_tolerance_minutes")
    if not isinstance(tolerance, int) or isinstance(tolerance, bool):
        raise ConfigError(f"{section}.gate_poll_tolerance_minutes", "must be an integer")
    if tolerance < 0:
        raise ConfigError(f"{section}.gate_poll_tolerance_minutes", "must be >= 0")

    return Machine(
        quiet_window=QuietWindow(start=start, end=end),
        load_threshold=float(load_threshold),
        poll_interval_minutes=poll_interval,
        gate_polls_required=gate_polls,
        gate_poll_tolerance_minutes=tolerance,
    )


def _load_agent(data: dict[str, Any]) -> Agent:
    """Validate and build the ``agent`` section.

    Args:
        data: The raw mapping under the ``agent`` key.

    Returns:
        A validated :class:`Agent`.

    Raises:
        ConfigError: If any agent field is missing or invalid, naming the field.
    """
    section = "agent"
    binary = _require_key(section, data, "binary")
    if not isinstance(binary, str) or not binary.strip():
        raise ConfigError(f"{section}.binary", "must be a non-empty string")

    model = _require_key(section, data, "model")
    if model is not None and (not isinstance(model, str) or not model.strip()):
        raise ConfigError(f"{section}.model", "must be a non-empty string or null")

    max_steps = _require_key(section, data, "max_steps")
    if not isinstance(max_steps, int) or isinstance(max_steps, bool):
        raise ConfigError(f"{section}.max_steps", "must be an integer")
    if max_steps < 1:
        raise ConfigError(f"{section}.max_steps", "must be >= 1")

    timeout = _require_key(section, data, "timeout_minutes")
    if not isinstance(timeout, int) or isinstance(timeout, bool):
        raise ConfigError(f"{section}.timeout_minutes", "must be an integer")
    if timeout < 1:
        raise ConfigError(f"{section}.timeout_minutes", "must be >= 1")

    auto_approve = _require_key(section, data, "auto_approve")
    if not isinstance(auto_approve, bool):
        raise ConfigError(f"{section}.auto_approve", "must be a boolean")

    return Agent(
        binary=binary,
        model=model,
        max_steps=max_steps,
        timeout_minutes=timeout,
        auto_approve=auto_approve,
    )


def _load_paths(data: dict[str, Any]) -> Paths:
    """Validate and build the ``paths`` section, resolving against PROJECT_ROOT.

    Args:
        data: The raw mapping under the ``paths`` key.

    Returns:
        A validated :class:`Paths` with absolute directories.

    Raises:
        ConfigError: If any path field is missing or empty, naming the field.
    """
    section = "paths"
    return Paths(
        state_dir=_resolve_path(_require_key(section, data, "state_dir"), f"{section}.state_dir"),
        log_dir=_resolve_path(_require_key(section, data, "log_dir"), f"{section}.log_dir"),
        sandbox_dir=_resolve_path(
            _require_key(section, data, "sandbox_dir"), f"{section}.sandbox_dir"
        ),
    )


def _load_workflows(data: dict[str, Any]) -> list[WorkflowEntry]:
    """Validate and build the ``workflows`` section, preserving YAML order.

    Args:
        data: The raw mapping under the ``workflows`` key.

    Returns:
        A list of validated :class:`WorkflowEntry`, in document order.

    Raises:
        ConfigError: If an entry field is missing/invalid (e.g. an unknown
            ``workflows.<name>.gate`` value), or if an *enabled* entry's module cannot be
            imported or lacks a ``create(config)`` attribute — naming
            ``workflows.<name>.module``.
    """
    section = "workflows"
    if not isinstance(data, dict):
        raise ConfigError(section, "expected a mapping of workflow entries")

    entries: list[WorkflowEntry] = []
    for name, raw in data.items():
        field_prefix = f"{section}.{name}"
        entry = _require_mapping(field_prefix, raw)

        enabled = _require_key(field_prefix, entry, "enabled")
        if not isinstance(enabled, bool):
            raise ConfigError(f"{field_prefix}.enabled", "must be a boolean")

        module = _require_key(field_prefix, entry, "module")
        if not isinstance(module, str) or not re.match(
            r"^[A-Za-z_][\w]*(\.[A-Za-z_][\w]*)+$", module
        ):
            raise ConfigError(f"{field_prefix}.module", "must be a dotted importable module path")

        agent = _require_key(field_prefix, entry, "agent")
        if agent is not None and (not isinstance(agent, str) or not agent.strip()):
            raise ConfigError(f"{field_prefix}.agent", "must be a non-empty string or null")

        # gate: optional; default "quiet_window"; must be one of the two gate types.
        gate = entry.get("gate", "quiet_window")
        if gate not in ("quiet_window", "idle"):
            raise ConfigError(f"{field_prefix}.gate", "must be 'quiet_window' or 'idle'")

        # Import-check only *enabled* entries: the module must exist and expose a
        # ``create(config) -> Workflow`` entry point. Disabled entries are skipped by
        # the scheduler, so their modules need not be present at load time.
        if enabled:
            try:
                mod = importlib.import_module(module)
            except Exception as exc:  # noqa: BLE001 - report any import failure as config error
                raise ConfigError(
                    f"{field_prefix}.module",
                    f"could not import '{module}': {exc}",
                ) from exc
            if not hasattr(mod, "create"):
                raise ConfigError(
                    f"{field_prefix}.module",
                    f"module '{module}' does not expose a create(config) entry point",
                )

        entries.append(
            WorkflowEntry(name=name, enabled=enabled, module=module, agent=agent, gate=gate)
        )
    return entries


_REPO_ID_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def _load_oc_todo(data: dict[str, Any]) -> OCTodo:
    """Validate and build the optional ``oc_todo`` section.

    Args:
        data: The raw mapping under the ``oc_todo`` key (already confirmed to be a
            mapping by the caller via :func:`_require_mapping`).

    Returns:
        A validated :class:`OCTodo`.

    Raises:
        ConfigError: If any field is invalid — each error names the offending dotted
            field (e.g. ``oc_todo.repos[0]``, ``oc_todo.test_commands.owner/name``).
    """
    section = "oc_todo"

    # repos: required key in the section (present but may be []); a list of owner/name.
    raw_repos = _require_key(section, data, "repos")
    if not isinstance(raw_repos, list):
        raise ConfigError(f"{section}.repos", "must be a list of 'owner/name' repo ids")
    repos: list[str] = []
    for i, entry in enumerate(raw_repos):
        field_name = f"{section}.repos[{i}]"
        if not isinstance(entry, str) or not _REPO_ID_RE.match(entry):
            raise ConfigError(field_name, "must be a 'owner/name' repo id")
        repos.append(entry)

    # max_todos_per_repo: optional; default DEFAULT_MAX_TODOS_PER_REPO; int >= 1.
    max_todos = data.get("max_todos_per_repo", DEFAULT_MAX_TODOS_PER_REPO)
    if not isinstance(max_todos, int) or isinstance(max_todos, bool):
        raise ConfigError(f"{section}.max_todos_per_repo", "must be an integer")
    if max_todos < 1:
        raise ConfigError(f"{section}.max_todos_per_repo", "must be >= 1")

    # test_commands / repo_urls: optional; default {}; keys must be in repos, values
    # non-empty strings.
    def _load_repo_map(key: str) -> dict[str, str]:
        raw = data.get(key, {})
        if not isinstance(raw, dict):
            raise ConfigError(f"{section}.{key}", "must be a mapping of repo -> string")
        out: dict[str, str] = {}
        for repo, value in raw.items():
            field_name = f"{section}.{key}.{repo}"
            if repo not in repos:
                raise ConfigError(field_name, "repo is not in oc_todo.repos")
            if not isinstance(value, str) or not value.strip():
                raise ConfigError(field_name, "must be a non-empty string")
            out[repo] = value
        return out

    test_commands = _load_repo_map("test_commands")
    repo_urls = _load_repo_map("repo_urls")

    return OCTodo(
        repos=repos,
        max_todos_per_repo=max_todos,
        test_commands=test_commands,
        repo_urls=repo_urls,
    )


def _load_roadmap_prompts(data: dict[str, Any]) -> RoadmapPrompts:
    """Validate and build the optional ``roadmap_prompts`` section.

    Args:
        data: The raw mapping under the ``roadmap_prompts`` key (already confirmed to be
            a mapping by the caller via :func:`_require_mapping`).

    Returns:
        A validated :class:`RoadmapPrompts`.

    Raises:
        ConfigError: If any field is invalid — each error names the offending dotted
            field (e.g. ``roadmap_prompts.allowed_repos[0]``,
            ``roadmap_prompts.listing_repo``, ``roadmap_prompts.test_commands.owner/name``).
    """
    section = "roadmap_prompts"

    # allowed_repos: required key in the section (present but may be []); a list of
    # owner/name ids (same regex as oc_todo). Empty = the workflow no-ops.
    raw_repos = _require_key(section, data, "allowed_repos")
    if not isinstance(raw_repos, list):
        raise ConfigError(f"{section}.allowed_repos", "must be a list of 'owner/name' repo ids")
    allowed_repos: list[str] = []
    for i, entry in enumerate(raw_repos):
        field_name = f"{section}.allowed_repos[{i}]"
        if not isinstance(entry, str) or not _REPO_ID_RE.match(entry):
            raise ConfigError(field_name, "must be a 'owner/name' repo id")
        allowed_repos.append(entry)

    # listing_repo: required key when the section is present; 'owner/name'.
    listing_repo = _require_key(section, data, "listing_repo")
    if not isinstance(listing_repo, str) or not _REPO_ID_RE.match(listing_repo):
        raise ConfigError(f"{section}.listing_repo", "must be a 'owner/name' repo id")

    # listing_repo_url: optional; a string ("" = derive git@github.com:<listing_repo>.git;
    # non-empty = clone-URL override, e.g. a local fixture in hermetic tests).
    listing_repo_url = data.get("listing_repo_url", "")
    if not isinstance(listing_repo_url, str):
        raise ConfigError(f"{section}.listing_repo_url", "must be a string ('' or a URL)")

    # listing_path / listing_branch: required keys; non-empty strings.
    listing_path = _require_key(section, data, "listing_path")
    if not isinstance(listing_path, str) or not listing_path.strip():
        raise ConfigError(f"{section}.listing_path", "must be a non-empty string")

    listing_branch = _require_key(section, data, "listing_branch")
    if not isinstance(listing_branch, str) or not listing_branch.strip():
        raise ConfigError(f"{section}.listing_branch", "must be a non-empty string")

    # run_timeout_minutes: optional; default DEFAULT_RUN_TIMEOUT_MINUTES; int >= 1.
    run_timeout = data.get("run_timeout_minutes", DEFAULT_RUN_TIMEOUT_MINUTES)
    if not isinstance(run_timeout, int) or isinstance(run_timeout, bool):
        raise ConfigError(f"{section}.run_timeout_minutes", "must be an integer")
    if run_timeout < 1:
        raise ConfigError(f"{section}.run_timeout_minutes", "must be >= 1")

    # test_commands / repo_urls: optional; default {}; keys must be in allowed_repos,
    # values non-empty strings (same pattern as oc_todo).
    def _load_repo_map(key: str) -> dict[str, str]:
        raw = data.get(key, {})
        if not isinstance(raw, dict):
            raise ConfigError(f"{section}.{key}", "must be a mapping of repo -> string")
        out: dict[str, str] = {}
        for repo, value in raw.items():
            field_name = f"{section}.{key}.{repo}"
            if repo not in allowed_repos:
                raise ConfigError(field_name, "repo is not in roadmap_prompts.allowed_repos")
            if not isinstance(value, str) or not value.strip():
                raise ConfigError(field_name, "must be a non-empty string")
            out[repo] = value
        return out

    test_commands = _load_repo_map("test_commands")
    repo_urls = _load_repo_map("repo_urls")

    return RoadmapPrompts(
        allowed_repos=allowed_repos,
        listing_repo=listing_repo,
        listing_repo_url=listing_repo_url,
        listing_path=listing_path,
        listing_branch=listing_branch,
        run_timeout_minutes=run_timeout,
        test_commands=test_commands,
        repo_urls=repo_urls,
    )


def load_config(path: Path) -> Config:
    """Read and validate the canonical agentic_scripts configuration file.

    Args:
        path: Path to the ``workflows.yaml`` file. The default (used by the CLI in
            Task 2) is ``PROJECT_ROOT / "config/workflows.yaml"``.

    Returns:
        A fully validated :class:`Config`. Relative ``paths.*`` values are resolved
        against :data:`PROJECT_ROOT`; ``workflows`` preserves YAML document order; the
        optional ``oc_todo`` and ``roadmap_prompts`` sections load into
        :attr:`Config.oc_todo` / :attr:`Config.roadmap_prompts` (empty defaults when
        absent).

    Raises:
        ConfigError: If the file is missing, not valid YAML, has an unknown or
            missing top-level section, or any field fails validation — each error
            names the offending dotted field.

    Example:
        >>> cfg = load_config(PROJECT_ROOT / "config" / "workflows.yaml")
        >>> cfg.workflows[0].name
        'noop'
    """
    path = Path(path)
    if not path.is_file():
        raise ConfigError(str(path), "configuration file not found")

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(str(path), f"invalid YAML: {exc}") from exc

    if not isinstance(raw, dict):
        raise ConfigError(str(path), "top-level document must be a mapping")

    allowed_sections = {
        "machine",
        "agent",
        "paths",
        "admin_repo",
        "workflows",
        "oc_todo",
        "roadmap_prompts",
    }
    for key in raw:
        if key not in allowed_sections:
            raise ConfigError(key, "unknown top-level section")

    for required in ("machine", "agent", "paths", "workflows"):
        if required not in raw:
            raise ConfigError(required, "required top-level section is missing")

    machine = _load_machine(_require_mapping("machine", raw["machine"]))
    agent = _load_agent(_require_mapping("agent", raw["agent"]))
    paths = _load_paths(_require_mapping("paths", raw["paths"]))

    admin_repo_raw = raw.get("admin_repo")  # optional; default None
    if admin_repo_raw is not None:
        if not isinstance(admin_repo_raw, str) or not admin_repo_raw.strip():
            raise ConfigError("admin_repo", "must be a non-empty string or null")
        admin_repo = _resolve_path(admin_repo_raw, "admin_repo")
    else:
        admin_repo = None

    workflows = _load_workflows(_require_mapping("workflows", raw["workflows"]))

    oc_todo_raw = raw.get("oc_todo")  # optional; empty defaults when absent
    if oc_todo_raw is not None:
        oc_todo = _load_oc_todo(_require_mapping("oc_todo", oc_todo_raw))
    else:
        oc_todo = _EMPTY_OC_TODO

    roadmap_prompts_raw = raw.get("roadmap_prompts")  # optional; empty defaults when absent
    if roadmap_prompts_raw is not None:
        roadmap_prompts = _load_roadmap_prompts(
            _require_mapping("roadmap_prompts", roadmap_prompts_raw)
        )
    else:
        roadmap_prompts = _EMPTY_ROADMAP_PROMPTS

    return Config(
        machine=machine,
        agent=agent,
        paths=paths,
        admin_repo=admin_repo,
        workflows=workflows,
        oc_todo=oc_todo,
        roadmap_prompts=roadmap_prompts,
    )
