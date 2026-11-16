# Work Plan: Hermetic MAIL_* env isolation in smoke tests

**Purpose:** Make the smoke-test mail-env isolation live in the autouse fixture (as documented) so no in-process `run()` in the smoke suite can reach the real notmuch index and dispatch a live agent.

**Date:** 2026-11-16    **Branch:** `plan/agentic-workflows`    **Status:** awaiting dispatch

## Objective

`tests/smoke/test_smoke_oc_todo.py::test_smoke_oc_todo_empty_repo_list_no_agent` hangs on this machine (47–140 min) whenever the runner's model ref is resolvable: it is the only smoke test that builds its config without `_workspace()`, and the autouse `_isolate_mail_env` fixture only *saves/restores* `MAIL_INDEX_DB`/`MAIL_PROCESSED_LOG` — it never *points* them at nonexistent tmp paths (that logic lives in `_workspace()`, whose docstring is what the module docstring claims the fixture does). With `MAIL_INDEX_DB` unset, `run()` falls back to the default `/workspace/docker/mbsync/notmuch` (real index, present on this machine) → mail-keeper runs canary + detection → dispatches a **live** `opencode run --agent mail-keeper` over the real pending mail. Before the model-ref fix it only "passed" because the dead model killed the agent in ~4 s.

End state: the autouse fixture in BOTH smoke files (`test_smoke_base.py`, `test_smoke_oc_todo.py`) is the single source of MAIL_* env isolation (points both vars at per-test nonexistent tmp paths, then restores); the duplicate env-setting in `_workspace()` is removed; the previously-buggy test additionally pins the isolation by asserting `WORKFLOW mail-keeper status=skipped` in its run log; the full plain `uv run pytest -q` suite is green on this machine with no deselects and no test able to spawn a live agent.

## Context

- Repo: `/workspace/Python/agentic_scripts`, branch `plan/agentic-workflows` (clean tree; production catch-up run executes in parallel against the Obsidian vault — smoke tests are hermetic and must stay that way).
- `tests/smoke/test_smoke_oc_todo.py`: `_workspace()` L74–90 sets `MAIL_INDEX_DB`/`MAIL_PROCESSED_LOG` (L87–88); autouse `_isolate_mail_env` L93–102 saves/restores only; tests at L105/L130/L152 use `_workspace()`, test at L175 (`test_smoke_oc_todo_empty_repo_list_no_agent`) writes its config manually (L177–189) and gets no isolation.
- `tests/smoke/test_smoke_base.py`: same pair (fixture ≈L84–90 save/restore only; `_workspace()` ≈L75–78 sets env); all 5 of its tests use `_workspace()` — latent, not active.
- `tests/smoke/test_smoke_mail_keeper.py`: builds its own hermetic notmuch index and `monkeypatch.setenv("MAIL_INDEX_DB", ...)` per test (≈L633) — self-isolated; do NOT modify.
- Shipped `config/workflows.yaml` has `mail-keeper: enabled: true`, so every smoke `run()` executes the mail-keeper workflow; a missing index dir makes it return `skipped` (fast, agent never reached — `workflows/mail_keeper.py` precheck).
- The in-process `run()` also calls `load_dotenv(.env, override=False)`; the repo `.env` sets no `MAIL_*` vars, and dotenv never overrides vars already set by the fixture — the fixture stays authoritative.
- Conventions: pytest + ruff per repo tooling; Google-style docstrings; `OC:` commit prefix; commit to current branch + push; stage only explicit paths.

## Tasks

### Task 1: Move MAIL_* isolation into the autouse fixtures + pin it in the buggy test
- **Plan:** `work_plan_task_1_hermetic_mail_env.md`
- **Files:** `tests/smoke/test_smoke_oc_todo.py`, `tests/smoke/test_smoke_base.py`
- **Acceptance (summary):** both fixtures point + restore; `_workspace()` no longer sets env; buggy test asserts `WORKFLOW mail-keeper status=skipped`; plain full suite green on this machine (no deselects, no hang); ruff clean; committed + pushed.

## Out of Scope

- `tests/smoke/test_smoke_mail_keeper.py` (self-isolated via monkeypatch; leave untouched)
- Any change to `workflows/mail_keeper.py`, `scheduler.py`, or the shipped config
- The separate pre-existing ruff-format debt in 5 unrelated files

## Notes

- [Assumption] `tmp_path` is unique per test within a session (pytest default) — the fixture's per-test nonexistent subpaths therefore cannot collide with another test's fixtures.
- Risk: minimal — test-only change; the only behavior delta is that every smoke `run()` now deterministically skips mail-keeper instead of depending on which helper built the config.
