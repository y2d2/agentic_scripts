"""Shared pytest fixtures for agentic_scripts tests.

All fixtures are hermetic: they build isolated temporary workspaces under ``tmp_path``
and never touch the real repo's gitignored areas or any external system. Git-identity
env vars are deliberately NOT set here — the git tests in Task 3 set their own.

Hermeticity guard: every scheduler-driving test builds its config by deep-copying the
SHIPPED ``config/workflows.yaml``. An entry in that file may operate on the user's REAL
GitHub repos (``roadmap-dev`` clones its allowed repos and pushes listing commits), and a
``gate: idle`` entry runs on every non-skipped fire — bypassing the quiet-window gate that
would otherwise keep a test fire inert. Such an entry must therefore be stripped from every
test copy before it reaches :func:`agentic_scripts.scheduler.run`; see
:func:`strip_live_repo_workflows`, applied at each shipped-config read site.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
import yaml

from agentic_scripts.config import Config, load_config

#: Workflow names that act on the user's real GitHub repos (clone + commit + push) and are
#: therefore unsafe to execute from a test-built copy of the shipped config.
LIVE_REPO_WORKFLOWS: tuple[str, ...] = ("roadmap-dev",)

#: Top-level config sections that belong exclusively to :data:`LIVE_REPO_WORKFLOWS`; they
#: are stripped alongside their workflows so a test config cannot re-arm one by name.
LIVE_REPO_SECTIONS: tuple[str, ...] = ("roadmap_prompts",)


def strip_live_repo_workflows(data: dict[str, Any]) -> dict[str, Any]:
    """Remove the real-repo workflows (and their settings) from a shipped-config copy.

    Purpose:
        Drop the entries that operate on the user's real GitHub repos — currently
        ``workflows.roadmap-dev`` plus its ``roadmap_prompts`` section — from a config
        mapping read from ``config/workflows.yaml`` *before* that mapping is written to a
        test fixture and handed to :func:`agentic_scripts.scheduler.run`.

    Rationale:
        The scheduler tests deliberately mirror production by deep-copying the shipped
        config, so anything registered there is executed on a fire. ``roadmap-dev`` is
        shipped ``enabled: true`` with ``gate: idle``, which skips the quiet-window gate and
        runs on every non-skipped fire, performing a real phase-1 run: clone the nine
        allowed repos, reconcile the listing, commit and PUSH to the live listing repo.
        Those commits are externally visible on a shared branch and cannot be recalled
        after the fact, so no test fire may carry the entry. ``roadmap-dev`` is covered by
        its own hermetic suite (fixture repos, injected seams, no network) rather than by
        these shipped-config copies. Stripping by name keeps every existing
        noop/mail-keeper/oc-todo assertion meaningful and unchanged.

    Args:
        data: A mutable config mapping, typically a :func:`copy.deepcopy` of the shipped
            YAML. Mutated in place.

    Returns:
        The same ``data`` mapping with :data:`LIVE_REPO_WORKFLOWS` removed from its
        ``workflows`` section and :data:`LIVE_REPO_SECTIONS` removed at top level. Names
        that are absent are ignored, so the guard is inert for configs that do not
        register them.

    Side Effects:
        Mutates ``data`` (a test-owned copy). Never reads or writes the shipped file.

    Example:
        >>> data = {"workflows": {"noop": {"enabled": True}, "roadmap-dev": {}},
        ...         "roadmap_prompts": {"allowed_repos": []}}
        >>> sorted(strip_live_repo_workflows(data)["workflows"])
        ['noop']
        >>> "roadmap_prompts" in data
        False
    """
    for section in LIVE_REPO_SECTIONS:
        data.pop(section, None)
    workflows = data.get("workflows")
    if isinstance(workflows, dict):
        for name in LIVE_REPO_WORKFLOWS:
            workflows.pop(name, None)
    return data


@pytest.fixture(autouse=True)
def _redirect_roadmap_mirror_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Pin the roadmap-dev local-listing mirror's project-root basis to ``tmp_path``.

    Purpose:
        ``roadmap_prompts.local_listing`` defaults to ``"plans.md"``, and
        :meth:`agentic_scripts.workflows.roadmap_dev._mirror_listing` resolves a relative
        value against the module-level ``PROJECT_ROOT`` — i.e. the REAL repo root. Any
        test that happens to drive a roadmap reconcile (shipped-config copy, fixture
        repos) would otherwise write ``plans.md`` into the working tree. This guard
        redirects the basis to the per-test temp dir so no test can ever touch the real
        tree; tests that WANT to assert on the mirror location patch the same name
        themselves (test-local patch wins — same monkeypatch instance, LIFO undo).

    Args:
        monkeypatch: The function-scoped patcher (undo restores the real basis).
        tmp_path: The per-test temporary directory used as the stand-in root.
    """
    monkeypatch.setattr("agentic_scripts.workflows.roadmap_dev.PROJECT_ROOT", tmp_path)


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
    point at the hermetic ``tmp_workspace`` directories (as absolute paths), stripped of
    the real-repo workflows via :func:`strip_live_repo_workflows`, written to a temp file,
    and loaded through :func:`load_config` so full validation runs.

    Returns:
        A fully validated :class:`Config` whose state/log/sandbox dirs live under
        ``tmp_path`` — safe to mutate in tests without touching the real repo.
    """
    project_root = Path(__file__).resolve().parents[1]
    shipped = yaml.safe_load(
        (project_root / "config" / "workflows.yaml").read_text(encoding="utf-8")
    )
    data = strip_live_repo_workflows(copy.deepcopy(shipped))
    data["paths"] = {
        "state_dir": str(tmp_workspace["state"]),
        "log_dir": str(tmp_workspace["logs"]),
        "sandbox_dir": str(tmp_workspace["sandbox"]),
    }
    cfg_path = tmp_path / "workflows.yaml"
    cfg_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return load_config(cfg_path)
