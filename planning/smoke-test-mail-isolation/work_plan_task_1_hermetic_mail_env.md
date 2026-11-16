# Task Plan: Hermetic MAIL_* env isolation in smoke tests

**Purpose:** One test-only change: make the autouse fixture the single source of MAIL_* env isolation in the two smoke files, so no in-process `run()` can reach the real notmuch index and dispatch a live agent.

## Objective

`tests/smoke/test_smoke_oc_todo.py::test_smoke_oc_todo_empty_repo_list_no_agent` (L175) is the only smoke test that builds its config without calling `_workspace()`; the autouse `_isolate_mail_env` fixture only saves/restores `MAIL_INDEX_DB`/`MAIL_PROCESSED_LOG` and never points them at nonexistent tmp paths (that logic lives in `_workspace()`). With `MAIL_INDEX_DB` unset, the in-process `run()` falls back to the default `/workspace/docker/mbsync/notmuch` (a REAL index on this machine) → mail-keeper runs canary + detection and dispatches a **live** `opencode run --agent mail-keeper` over real pending mail (47–140 min hang). Before the 2026-11-16 model-ref fix the test only "passed" because the dead model ref killed the agent in ~4 s. After this task: the autouse fixture in BOTH `tests/smoke/test_smoke_base.py` and `tests/smoke/test_smoke_oc_todo.py` points both vars at per-test nonexistent tmp paths (then restores), `_workspace()` no longer sets env, the previously-buggy test pins the isolation by asserting the mail-keeper skip line, and the plain full suite (`uv run pytest -q`, no deselects) is green on this machine.

## Context

- Repo: `/workspace/Python/agentic_scripts`, branch `plan/agentic-workflows` (clean tree). A production mail-keeper run executes in parallel against the Obsidian vault — the smoke tests must stay hermetic; do not run any command that could dispatch a real agent.
- `tests/smoke/test_smoke_oc_todo.py`:
  - `_workspace()` (≈L74–90) sets `os.environ["MAIL_INDEX_DB"] = str(tmp_path / "no-such-index")` and `os.environ["MAIL_PROCESSED_LOG"] = str(tmp_path / "no-such-log.jsonl")` (L87–88) with a comment explaining why (shipped config has mail-keeper enabled; nonexistent index → workflow `skipped`, no canary walk, no agent).
  - autouse `_isolate_mail_env` (≈L93–102): saves both vars, yields, restores (pops when originally None). Its docstring claims it "Point[s] MAIL_* env at tmp paths" — it currently does not.
  - Tests L105 (`registered_noop`), L130 (`gate_closed_noop`), L152 (`config_fault`) call `_workspace()`; test L175 (`empty_repo_list_no_agent`) writes its config manually (L177–189) → no isolation.
  - Module docstring L18–22 describes the isolation as fixture-provided — after the fix that description is finally true.
- `tests/smoke/test_smoke_base.py`: the identical pair — `_workspace()` (≈L64–78) sets the two env vars; autouse fixture (≈L84–90) only saves/restores (docstring: "restores both after each test"). All 5 of its tests use `_workspace()` (latent instance of the same defect).
- `tests/smoke/test_smoke_mail_keeper.py`: self-isolated (per-test hermetic notmuch index + `monkeypatch.setenv("MAIL_INDEX_DB", ...)` ≈L633). DO NOT modify.
- Shipped `config/workflows.yaml`: `mail-keeper: enabled: true`, `agent.model: llama-cpp/Qwen3.8-27B` (now resolvable), `admin_repo: /workspace/Obsidian/ARP_roadmap` — so every smoke `run()` executes the mail-keeper workflow; a missing index dir makes it return `status="skipped"` before any canary/agent work (`workflows/mail_keeper.py` precheck, ≈L859–863).
- The in-process `run()` also calls `load_dotenv(PROJECT_ROOT/.env, override=False)`; the repo `.env` sets no `MAIL_*` vars and dotenv never overrides already-set vars — the fixture stays authoritative even if a user env var exists.
- Conventions: `uv run pytest` / `uv run ruff` from repo root; Google-style docstrings; `OC:` commit prefix; commit to current branch + push; stage only explicit paths (never `git add -A`).

## Tasks

### Task 1: Fixtures become the single isolation point (both smoke files)
- **Files:** `tests/smoke/test_smoke_oc_todo.py` (modify), `tests/smoke/test_smoke_base.py` (modify)
- **Do:** In BOTH files:
  1. Extend the autouse `_isolate_mail_env` fixture to request `tmp_path: Path` and, before `yield`, set `os.environ["MAIL_INDEX_DB"] = str(tmp_path / "no-such-index")` and `os.environ["MAIL_PROCESSED_LOG"] = str(tmp_path / "no-such-log.jsonl")`. Keep the existing save/restore logic (pop when originally None) after `yield`. Update its docstring to state that it points both vars at nonexistent per-test tmp paths AND restores the originals.
  2. Remove the two `os.environ[...]` assignments from `_workspace()` (keep the surrounding comment, trimmed to note that env isolation now lives in the autouse fixture — the "why" (shipped config enables mail-keeper; nonexistent index → skipped) must remain documented in the fixture docstring or a comment there).
  3. In `tests/smoke/test_smoke_oc_todo.py`, verify the module docstring (L18–22) still accurately describes the isolation after the change (it claims the fixture points `MAIL_INDEX_DB` at a nonexistent tmp path — that becomes true); adjust only if wording drifts.
- **Notes:** Use `pytest`'s `tmp_path` (unique per test within a session) — per-test subpaths cannot collide with other tests' fixtures. Do not touch `test_smoke_mail_keeper.py`. No source/config changes.
- **Acceptance:**
  1. `grep -n "os.environ\[" tests/smoke/test_smoke_base.py tests/smoke/test_smoke_oc_todo.py` shows the MAIL_* assignments only inside the autouse fixtures (restore-loop assignments aside) — none in `_workspace()`.
  2. `uv run pytest tests/smoke/ -q` → all pass, total wall time < 2 min (previously the oc-todo file hung 47+ min on this machine).

### Task 2: Pin the isolation in the previously-buggy test (depends on #1)
- **Files:** `tests/smoke/test_smoke_oc_todo.py` (modify)
- **Do:** In `test_smoke_oc_todo_empty_repo_list_no_agent`, after the existing `WORKFLOW oc-todo status=ok` assertion, add one assertion that the run log also contains `WORKFLOW mail-keeper status=skipped` (the shipped config enables mail-keeper; with the fixture's nonexistent index it must skip before any canary/agent work). Add a one-line comment: this pins the env isolation — without it the test would dispatch a live agent.
- **Notes:** The `run()` in this test executes all enabled workflows (noop, mail-keeper, oc-todo) — the skip line is present in the run log. Assert on the run log (the test's existing `_run_logs(dirs["logs"])[0]` read), not `last-run.txt` (which carries only the first workflow's summary).
- **Acceptance:**
  1. The new assertion passes: `uv run pytest tests/smoke/test_smoke_oc_todo.py::test_smoke_oc_todo_empty_repo_list_no_agent -q` → PASS in < 30 s on this machine.
  2. Temporarily reverting Task 1's fixture change makes this test FAIL (or hang) — sanity-check the test actually pins the behavior, then re-apply. (Do this carefully with `git stash`/manual revert and verify the working tree is restored — never leave the tree dirty.)

### Task 3: Verify, commit, push (depends on #1–#2)
- **Do:**
  1. Plain full suite on this machine: `uv run pytest -q` (no deselects) → all green; report counts (expected ≈183 passed, 0 failed, 0 deselected — the previously-deselected smoke test now passes).
  2. `uv run ruff check tests/smoke/` + `uv run ruff format --check` on the two touched files → clean (pre-existing repo-wide format debt in 5 unrelated files stays untouched).
  3. `git status` → only the two smoke test files modified. Stage exactly those two paths, commit `OC: Hermetic MAIL_* env isolation in smoke fixtures (no live agent dispatch)`, push.
- **Acceptance:**
  1. Full suite green, counts reported.
  2. Lint/format clean on touched files.
  3. Commit landed on `plan/agentic-workflows` and pushed; commit message quoted in the result report.

## Out of Scope

- `tests/smoke/test_smoke_mail_keeper.py` (self-isolated; leave untouched)
- `workflows/mail_keeper.py`, `scheduler.py`, `config/workflows.yaml`, `opencode.jsonc`, `agents/*.md`
- The pre-existing ruff-format debt in 5 unrelated files
- Triggering/monitoring the production catch-up run (orchestrator-owned)

## Notes

- [Assumption] `pytest`'s `tmp_path` is unique per test within a session (default behavior, no `basetemp` override in `pyproject.toml` — verify; if a `basetemp` addopt exists, the per-test subdirectory is still unique).
- [Assumption] No smoke test intentionally depends on the live default index (verified by grep: only `test_smoke_mail_keeper.py` sets `MAIL_INDEX_DB`, always to its own hermetic fixture index).
- The production catch-up run (run `run-20261116T164153Z`) is executing in parallel against the real index/vault — this test-only change cannot affect it, and the verification commands here never dispatch a real agent.
