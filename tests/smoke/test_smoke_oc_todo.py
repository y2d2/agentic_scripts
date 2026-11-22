"""Run()-level hermetic smoke tests for the oc-todo workflow (Task 5).

These prove the shipped, registered ``oc-todo`` entry point end-to-end through a real
in-process :func:`agentic_scripts.scheduler.run` against a tmp workspace with a copy of the
shipped config pointed at it — mirroring :mod:`tests.smoke.test_smoke_base`. They cover the
base paths only:

  * the registered workflow is discoverable and no-ops cleanly with the shipped empty
    ``oc_todo.repos`` list (exactly ONE action, no state file, no sandbox dir);
  * a gate-closed run exits as a no-op without touching any repo;
  * a malformed ``oc_todo`` section fails fast at config load (exit 2, field named on stderr).

The fixture-repo world (two markers → two PRs, idempotency, merge-resolution, caps, fresh-
branch-only pushes) is proven hermetically in :mod:`tests.test_oc_todo_pipeline` with fakes —
the same split as mail-keeper (``test_smoke_mail_keeper.py`` proves the base paths,
``test_mail_keeper.py`` proves the fixture world).

Env isolation is load-bearing: the shipped config has ``mail-keeper`` enabled, so a forced
``run()`` would otherwise drive the LIVE mail-keeper (real notmuch index, real agent). The
autouse fixture below points ``MAIL_INDEX_DB`` at a nonexistent tmp path (→ mail-keeper
returns ``skipped``) and ``MAIL_PROCESSED_LOG`` at a tmp path, saving/restoring the originals —
exactly the pattern in :mod:`tests.smoke.test_smoke_base`.
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import pytest
import yaml

from agentic_scripts.scheduler import run

REPO_ROOT = Path(__file__).resolve().parents[2]
SHIPPED_CONFIG = REPO_ROOT / "config" / "workflows.yaml"


def _write_config(tmp_path: Path, state_dir: Path, log_dir: Path, sandbox_dir: Path) -> Path:
    """Write a tmp copy of the shipped config pointed at the given dirs and return its path.

    Args:
        tmp_path: pytest temp dir to hold the YAML file.
        state_dir/log_dir/sandbox_dir: Absolute dirs for the ``paths`` section.

    Returns:
        The path of the written config file.
    """
    data = yaml.safe_load(SHIPPED_CONFIG.read_text(encoding="utf-8"))
    data["paths"] = {
        "state_dir": str(state_dir),
        "log_dir": str(log_dir),
        "sandbox_dir": str(sandbox_dir),
    }
    cfg_path = tmp_path / "workflows.yaml"
    cfg_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return cfg_path


def _run_logs(log_dir: Path) -> list[Path]:
    """Return all ``run-*.log`` files in a log dir, sorted by name."""
    return sorted(log_dir.glob("run-*.log"))


def _last_run(log_dir: Path) -> str:
    """Return the contents of ``logs/last-run.txt`` (empty string if absent)."""
    path = log_dir / "last-run.txt"
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def _workspace(tmp_path: Path) -> tuple[Path, dict[str, Path]]:
    """Create isolated state/log/sandbox dirs and a tmp config pointed at them.

    Returns:
        A tuple of the config path and a ``{state, logs, sandbox}`` dirs mapping.
    """
    dirs = {name: tmp_path / name for name in ("state", "logs", "sandbox")}
    for path in dirs.values():
        path.mkdir(parents=True, exist_ok=True)
    # MAIL_* env isolation now lives in the autouse _isolate_mail_env fixture below — it points
    # both vars at nonexistent per-test tmp paths so mail-keeper returns `skipped` (no live agent).
    cfg = _write_config(tmp_path, dirs["state"], dirs["logs"], dirs["sandbox"])
    return cfg, dirs


@pytest.fixture(autouse=True)
def _isolate_mail_env(tmp_path: Path):
    """Point MAIL_* env at nonexistent per-test tmp paths and restore the originals after.

    The shipped config has ``mail-keeper`` enabled, so a forced in-process ``run()`` would
    otherwise drive the LIVE mail-keeper (real notmuch index + real agent). Pointing
    ``MAIL_INDEX_DB`` at a nonexistent tmp path makes the workflow return ``skipped`` (index
    missing) — no canary walk, no agent — and ``MAIL_PROCESSED_LOG`` at a tmp path keeps the
    production log from being probed. The originals are restored after each test (popped when
    they were unset).
    """
    saved = {k: os.environ.get(k) for k in ("MAIL_INDEX_DB", "MAIL_PROCESSED_LOG")}
    os.environ["MAIL_INDEX_DB"] = str(tmp_path / "no-such-index")
    os.environ["MAIL_PROCESSED_LOG"] = str(tmp_path / "no-such-log.jsonl")
    yield
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def test_smoke_oc_todo_registered_noop(tmp_path: Path) -> None:
    """Forced run with the shipped config (empty repos) → oc-todo no-ops: 1 action, no state."""
    cfg, dirs = _workspace(tmp_path)

    code = run(
        ["run", "--force", "--config", str(cfg)],
        now=datetime(2026, 11, 14, 13, 0),  # out-of-window; --force bypasses the gate
        load=(99.0, 99.0, 99.0),
    )

    assert code == 0
    log_text = _run_logs(dirs["logs"])[0].read_text(encoding="utf-8")
    # Exact counts per the no-repos path: 1 action, 0 items, 0 errors (assert on the run log,
    # NOT last-run.txt — which only carries the FIRST workflow's summary).
    assert "WORKFLOW oc-todo status=ok items_found=0 actions=1 errors=0" in log_text

    last = _last_run(dirs["logs"])
    assert "trigger: force" in last
    assert "overall: ok" in last

    # No side effects: no sandbox/oc-todo dir and no state file (a no-change run saves nothing).
    assert not (dirs["sandbox"] / "oc-todo").exists()
    assert not (dirs["state"] / "oc-todo.json").exists()


def test_smoke_oc_todo_gate_closed_noop(tmp_path: Path) -> None:
    """Gate-closed run → exit 0, CLOSED verdict, no repo touched (no sandbox dir, no state).

    With ``roadmap-dev`` shipped enabled (Task 6, ``gate: idle``), a quiet-gate-closed run
    still enters the workflow loop: oc-todo (a quiet-gate sibling) is SKIPPED and touches
    no repo, while the inert roadmap-dev entry no-ops — so the run ends ``overall: ok``
    (it no longer blanket-skips to ``overall: skipped``).
    """
    cfg, dirs = _workspace(tmp_path)

    code = run(
        ["run", "--config", str(cfg)],
        now=datetime(2026, 11, 14, 13, 0),  # outside the quiet window → gate CLOSED
        load=(0.5, 0.5, 0.5),
    )

    assert code == 0
    log_text = _run_logs(dirs["logs"])[0].read_text(encoding="utf-8")
    assert "verdict=CLOSED" in log_text
    # oc-todo is skipped by the closed quiet gate (never reaches its own no-repos path).
    assert "WORKFLOW oc-todo status=skipped reason=quiet gate closed" in log_text

    last = _last_run(dirs["logs"])
    assert "overall: ok" in last

    # With the gate closed, oc-todo exits as a skip without touching any repo.
    assert not (dirs["sandbox"] / "oc-todo").exists()
    assert not (dirs["state"] / "oc-todo.json").exists()


def test_smoke_oc_todo_config_fault(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A malformed oc_todo section (repos without a slash) → exit 2, field named on stderr."""
    dirs = {name: tmp_path / name for name in ("state", "logs", "sandbox")}
    for path in dirs.values():
        path.mkdir(parents=True, exist_ok=True)

    data = yaml.safe_load(SHIPPED_CONFIG.read_text(encoding="utf-8"))
    data["paths"] = {
        "state_dir": str(dirs["state"]),
        "log_dir": str(dirs["logs"]),
        "sandbox_dir": str(dirs["sandbox"]),
    }
    data["oc_todo"]["repos"] = ["no-slash"]  # not an owner/name id → config fault
    cfg_path = tmp_path / "workflows.yaml"
    cfg_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    code = run(["run", "--force", "--config", str(cfg_path)])

    assert code == 2
    captured = capsys.readouterr()
    assert "oc_todo.repos[0]" in captured.err


def test_smoke_oc_todo_empty_repo_list_no_agent(tmp_path: Path) -> None:
    """Explicitly empty oc_todo.repos → forced run no-ops (ok, 0 items); no agent can run."""
    dirs = {name: tmp_path / name for name in ("state", "logs", "sandbox")}
    for path in dirs.values():
        path.mkdir(parents=True, exist_ok=True)

    data = yaml.safe_load(SHIPPED_CONFIG.read_text(encoding="utf-8"))
    data["paths"] = {
        "state_dir": str(dirs["state"]),
        "log_dir": str(dirs["logs"]),
        "sandbox_dir": str(dirs["sandbox"]),
    }
    data["oc_todo"]["repos"] = []  # explicit empty list (the shipped value, made explicit)
    cfg_path = tmp_path / "workflows.yaml"
    cfg_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    code = run(
        ["run", "--force", "--config", str(cfg_path)],
        now=datetime(2026, 11, 14, 13, 0),
        load=(99.0, 99.0, 99.0),
    )

    assert code == 0
    log_text = _run_logs(dirs["logs"])[0].read_text(encoding="utf-8")
    # The workflow returns before any runner access: ok with 0 items and exactly one action.
    assert "WORKFLOW oc-todo status=ok items_found=0 actions=1 errors=0" in log_text
    # Pins the env isolation: mail-keeper must skip (nonexistent index) — without this the test
    # would dispatch a LIVE agent over the real notmuch index and hang for hours.
    assert "WORKFLOW mail-keeper status=skipped" in log_text
    # Proven by the absence of any sandbox dir + state (the agent is never reached).
    assert not (dirs["sandbox"] / "oc-todo").exists()
    assert not (dirs["state"] / "oc-todo.json").exists()
