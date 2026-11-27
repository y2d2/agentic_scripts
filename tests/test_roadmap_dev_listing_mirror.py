"""Hermetic tests for the ``local_listing`` mirror (this repo's roadmap-dev addition).

Fixture world: as in :mod:`tests.test_roadmap_dev_scan` — local bare remotes play
GitHub (one allowed repo carrying ONE discoverable plan + one listing repo starting
with an empty ``plans.md``); :meth:`RoadmapDevWorkflow.run` is driven directly (NOT via
``scheduler.run``) with a REAL :class:`Git` helper, a real :class:`StateStore` over a
throwaway workspace, and an injected fixed clock. NO network, no ``GITHUB_PAT``; git
identity is set per test (autouse fixture).

The one extra seam: a relative ``local_listing`` resolves against the module-level
``PROJECT_ROOT`` of :mod:`agentic_scripts.workflows.roadmap_dev` — every test here
monkeypatches THAT name to a private temp dir (``<tmp>/project``) so the write lands
hermetically and nothing can touch the real repo tree (the same technique the
suite-wide autouse guard in ``tests/conftest.py`` applies defensively).

Coverage:
  * ``local_listing: "plans.md"`` → after a reconcile run the file exists under the
    (patched) project root, equals the rendered listing byte-for-byte, and the action
    list carries the ``listing mirrored to`` note;
  * ``local_listing: null`` → no file written, no mirror note (the reconcile itself
    still pushes);
  * a stale mirror is rewritten EVEN when the remote push is a no-op — the remote gets
    no extra commit while the mirror self-heals (the no-op early return still calls
    :meth:`RoadmapDevWorkflow._mirror_listing`).
"""

from __future__ import annotations

import logging
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from agentic_scripts.config import Config, load_config
from agentic_scripts.git import Git
from agentic_scripts.state import StateStore
from agentic_scripts.workflows.base import WorkContext
from agentic_scripts.workflows.roadmap_dev import (
    RoadmapDevWorkflow,
    parse_listing,
    render_listing,
)

# The injected clock (UTC) — the pipeline never calls datetime.now() itself.
NOW = datetime(2026, 11, 21, 12, 0, tzinfo=UTC)

FIX = "owner/fixture"
PROMPTS_REPO = "owner/prompts"
LISTING_PATH = "plans.md"
LISTING_BRANCH = "main"
PLAN = "# Mirror plan\n\nA single discoverable plan so the listing renders non-empty.\n"

QUIET = logging.getLogger("test.roadmap_dev_listing_mirror")
QUIET.setLevel(logging.CRITICAL)  # quiet: the workflow logs at INFO/WARNING/ERROR


@pytest.fixture(autouse=True)
def _git_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set the git identity env vars for every git subprocess this test spawns."""
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Test Author")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "author@example.test")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "Test Committer")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "committer@example.test")
    monkeypatch.delenv("GITHUB_PAT", raising=False)


# --- Raw git + fixture builders ------------------------------------------------ #


def _git(path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run a raw git command in ``path`` (test setup helper)."""
    return subprocess.run(
        ["git", "-C", str(path), *args], capture_output=True, text=True, check=True
    )


def _bare_remote(tmp_path: Path, name: str, files: dict[str, str]) -> Path:
    """Build a local bare remote with one commit on ``main`` carrying ``files``."""
    src = tmp_path / f"src-{name}"
    src.mkdir()
    _git(src, "init", "-b", "main")
    for rel, text in sorted(files.items()):
        target = src / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    _git(src, "add", "-A")
    _git(src, "commit", "-m", f"fixture {name}")
    bare = tmp_path / f"{name}.git"
    bare.mkdir()
    _git(bare, "init", "--bare")
    _git(bare, "symbolic-ref", "HEAD", "refs/heads/main")
    _git(src, "remote", "add", "origin", str(bare))
    _git(src, "push", "-q", "-u", "origin", "main")
    return bare


def _remote_file(bare: Path, rel: str) -> bytes:
    """Return the RAW bytes of ``rel`` on the bare remote's ``main`` (no rstrip)."""
    out = subprocess.run(
        ["git", "-C", str(bare), "show", f"main:{rel}"], capture_output=True, check=True
    )
    return out.stdout


# --- Config / context / workflow builders --------------------------------------- #


def _world(tmp_path: Path, *, local_listing: str | None) -> tuple[Config, Path]:
    """Build the fixture remotes and a loaded config pointing the section at them.

    Args:
        tmp_path: The pytest temp dir (fixture sources/bares live under it).
        local_listing: Value for ``roadmap_prompts.local_listing`` — a relative path
            (resolved against the patched ``PROJECT_ROOT``) or ``None`` (mirror off).

    Returns:
        A tuple ``(config, listing_bare)`` — the fully validated config (tmp paths,
        one fixture repo with a local-URL override, the listing bare as listing URL)
        and the listing repo's bare-remote path.
    """
    bare_a = _bare_remote(tmp_path, "fixture", {"planning/mirror/work_plan.md": PLAN})
    bare_p = _bare_remote(tmp_path, "listing", {LISTING_PATH: ""})

    root = Path(__file__).resolve().parents[1]
    data = yaml.safe_load((root / "config" / "workflows.yaml").read_text(encoding="utf-8"))
    data["paths"] = {
        "state_dir": str(tmp_path / "state"),
        "log_dir": str(tmp_path / "logs"),
        "sandbox_dir": str(tmp_path / "sandbox"),
    }
    data["roadmap_prompts"] = {
        "allowed_repos": [FIX],
        "listing_repo": PROMPTS_REPO,
        "listing_repo_url": str(bare_p),  # hermetic seam: local bare remote
        "listing_path": LISTING_PATH,
        "listing_branch": LISTING_BRANCH,
        "run_timeout_minutes": 480,
        "test_commands": {},
        "repo_urls": {FIX: str(bare_a)},  # hermetic seam: local bare remote
        "local_listing": local_listing,
    }
    cfg_path = tmp_path / "workflows.yaml"
    cfg_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return load_config(cfg_path), bare_p


def _ctx(config: Config, tmp_path: Path) -> WorkContext:
    """Build a hermetic :class:`WorkContext` over the tmp workspace (quiet logger)."""
    return WorkContext(
        config=config,
        state=StateStore(tmp_path / "state"),
        logger=QUIET,
        run_id="test-mirror-run",
        workflow_name="roadmap-dev",
        sandbox_dir=tmp_path / "sandbox",
        admin_repo=None,
        gate_open=False,  # keep the drain inert: these tests are about the mirror
    )


def _wf(config: Config) -> RoadmapDevWorkflow:
    """Build a workflow over ``config.roadmap_prompts`` with a real Git + fixed clock."""
    return RoadmapDevWorkflow(config.roadmap_prompts, git=Git(), now_fn=lambda: NOW)


# --- Tests ----------------------------------------------------------------------- #


def test_mirror_written_byte_identical_after_reconcile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """local_listing "plans.md" → reconcile writes <root>/plans.md byte-for-byte + action note.

    The mirror content equals the listing the workflow pushed to the remote — and the
    rendered-text fixed point (``render_listing(parse_listing(x)) == x``) proves that
    content IS the rendered listing, not just some file.
    """
    project_root = tmp_path / "project"
    project_root.mkdir()
    monkeypatch.setattr("agentic_scripts.workflows.roadmap_dev.PROJECT_ROOT", project_root)

    config, bare_p = _world(tmp_path, local_listing="plans.md")
    result = _wf(config).run(_ctx(config, tmp_path))

    assert result.status == "ok", result.errors
    remote_bytes = _remote_file(bare_p, LISTING_PATH)
    assert remote_bytes  # sanity: the run pushed a non-empty listing (one discovered plan)

    mirror = project_root / "plans.md"
    assert mirror.is_file()
    assert mirror.read_bytes() == remote_bytes
    # The byte content IS the rendered listing (fixed point through parse → render).
    rendered = render_listing(parse_listing(remote_bytes.decode("utf-8")))
    assert rendered.encode("utf-8") == remote_bytes

    assert any(a.startswith("listing mirrored to ") for a in result.actions), result.actions
    # The drain note still closes the action list — the mirror note never displaces it.
    assert result.actions[-1] == "drain skipped (idle gate closed)"


def test_mirror_not_written_when_local_listing_null(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """local_listing null → the run reconciles normally but writes NO mirror anywhere."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    monkeypatch.setattr("agentic_scripts.workflows.roadmap_dev.PROJECT_ROOT", project_root)

    config, bare_p = _world(tmp_path, local_listing=None)
    result = _wf(config).run(_ctx(config, tmp_path))

    assert result.status == "ok", result.errors
    assert _remote_file(bare_p, LISTING_PATH)  # the reconcile/push itself happened
    assert not (project_root / "plans.md").exists()
    assert not any(a.startswith("listing mirrored to ") for a in result.actions)


def test_mirror_rewritten_even_when_push_is_a_noop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A stale mirror self-heals on a run where the remote push is a no-op (no new commit)."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    monkeypatch.setattr("agentic_scripts.workflows.roadmap_dev.PROJECT_ROOT", project_root)

    config, bare_p = _world(tmp_path, local_listing="plans.md")
    result1 = _wf(config).run(_ctx(config, tmp_path))
    assert result1.status == "ok", result1.errors
    remote_bytes = _remote_file(bare_p, LISTING_PATH)
    commits_after_1 = len(_git(bare_p, "log", "--oneline", "main").stdout.splitlines())

    # Make the mirror stale between runs; the world (remote listing, plan, state) is
    # unchanged, so run 2 takes the push-no-op path — yet the mirror must be rewritten.
    mirror = project_root / "plans.md"
    mirror.write_text("stale hand-edit\n", encoding="utf-8")

    result2 = _wf(config).run(_ctx(config, tmp_path))

    assert result2.status == "ok", result2.errors
    assert any(a.startswith("listing unchanged") for a in result2.actions), result2.actions
    assert any(a.startswith("listing mirrored to ") for a in result2.actions), result2.actions
    assert mirror.read_bytes() == remote_bytes
    # No extra push: the remote HEAD moved no further than after run 1.
    commits_after_2 = len(_git(bare_p, "log", "--oneline", "main").stdout.splitlines())
    assert commits_after_2 == commits_after_1
