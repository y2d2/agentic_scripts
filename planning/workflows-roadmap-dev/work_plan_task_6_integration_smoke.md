# Task Plan: T6 — final integration: enable the workflow + hermetic smoke suite

**Purpose:** Flip `roadmap-dev` to `enabled: true` (with the shipped empty allowlist = inert no-op) and prove the registered, shipped entry point end-to-end through the real in-process `scheduler.run` with hermetic smoke tests, then verify the whole suite + tooling are green.

## Objective

Ship the workflow in its safe default state: registered and enabled, inert until `allowed_repos` is filled (the `oc_todo.repos: []` first-run pattern), with smoke tests that guard the base paths of the registered entry point (discoverable, no-ops cleanly, gate behavior, config fail-fast) — mirroring `tests/smoke/test_smoke_oc_todo.py` — and a fully green suite as the release gate.

## Context

- Work in `/workspace/Python/agentic_scripts` (branch `feature/roadmap-dev-workflow`). T1–T5 landed: the workflow module (Phase 1 + drain), config section + `gate: idle` entry (currently `enabled: false`), idle gate in the scheduler, README section, `setup.sh` steps, bootstrap script + `arp_prompts_initial/` staging. Read first: `tests/smoke/test_smoke_oc_todo.py` (the pattern to mirror: shipped-config copy pointed at tmp dirs via `_write_config`, `_run_logs`/`_last_run` helpers, the autouse MAIL_* env-isolation fixture, gate-closed no-op, malformed-section exit 2), `tests/smoke/test_smoke_base.py`, `tests/smoke/test_smoke_mail_keeper.py`, `config/workflows.yaml`, `scripts/setup.sh`, `README.md` (the new section).
- **The shipped config after this task:** `workflows.roadmap-dev.enabled: true` (everything else as T1 shipped it: `gate: idle`, `agent: planner-enhanced`, `module: agentic_scripts.workflows.roadmap_dev`); `roadmap_prompts.allowed_repos: []` stays EMPTY at ship (no-op until the operator lists repos — plan decision; the operator sets real repos post-bootstrap).
- **Smoke conventions (load-bearing):** hermetic only — no real `opencode`, no network, no live mail, no real GitHub. The in-process `scheduler.run([...], now=…, load=…, run_id=…)` drives the real config copy. Because the shipped config has `mail-keeper` enabled, the autouse fixture must isolate `MAIL_INDEX_DB` / `MAIL_PROCESSED_LOG` exactly like `test_smoke_oc_todo.py._isolate_mail_env` (point both at nonexistent per-test tmp paths; save/restore originals). `oc-todo` (empty `repos`) and `roadmap-dev` (empty `allowed_repos`) no-op; `noop` runs.
- **Gate-interaction facts (T1):** quiet gate = machine-global (22:00–08:00 window + load + 2 polls); idle gate = zero active sessions + 2 polls, key `idle_gate_last_ok`. A non-forced `run()` with the quiet gate closed and an enabled `gate: idle` workflow enters the workflow loop and runs it with `ctx.gate_open` = idle verdict; quiet-gate workflows are skipped with summary lines. The idle probe (`sessions.read_active_sessions`) reads `~/.local/state/opencode/service.json` + does an HTTP GET — in smoke tests this MUST NOT touch the real service: T1 made the probe injectable via… — CHECK T1's landing: if `run()` calls `read_active_sessions()` directly (not injectable), the smoke test must monkeypatch `agentic_scripts.sessions._urlopen` (the T1 seam) to return a canned `{"data": {}}` response and point `read_service_state` at a tmp file via monkeypatching `Path.home`? — **whichever seam T1 landed, use it; if none is cleanly patchable, monkeypatch `agentic_scripts.sessions.active_session_count` at its import site in `scheduler`** (document what you patch in the test module docstring).
- **Acceptance command for the live no-op:** `uv run agentic-scripts run --force --only roadmap-dev` (real shipped config, real `state/`+`logs/`+`sandbox/` dirs — the workflow is inert with the empty allowlist, so this is side-effect-free: assert no `state/roadmap-dev.json` is created and no `sandbox/roadmap-dev/` dir appears; the run writes its normal `logs/run-*.log` + `last-run.txt`).

## Tasks

### Task 1: Config flip + listing-repo name
- **Files:** `config/workflows.yaml` (modify)
- **Do:** (a) Set `roadmap-dev.enabled: true`. Add a one-line comment on the entry: `# enabled, but inert until roadmap_prompts.allowed_repos is non-empty`. (b) Fix the listing-repo value: T1 shipped `roadmap_prompts.listing_repo: y2d2/ARP_prompts` — the user renamed the repo (decision 2026-11-21): set it to `y2d2/autonomous_task_overview` (the repo exists and is empty; bootstrap pushes content there). Leave `allowed_repos: []` (seeded post-bootstrap by the orchestrator, not by this task).
- **Acceptance:**
  1. `uv run python -c "from agentic_scripts.config import load_config, PROJECT_ROOT; c = load_config(PROJECT_ROOT/'config/workflows.yaml'); e = [w for w in c.workflows if w.name=='roadmap-dev'][0]; assert e.enabled and e.gate=='idle' and e.agent=='planner-enhanced'; assert c.roadmap_prompts.listing_repo == 'y2d2/autonomous_task_overview'; print('ok')"` prints `ok`.
  2. `uv run pytest -v` (full suite as of T4/T5, before the new smoke file) still green.

### Task 2: Smoke tests
- **Files:** `tests/smoke/test_smoke_roadmap_dev.py` (create)
- **Do:** Mirror `test_smoke_oc_todo.py` structure (docstring stating the base-path scope, `_write_config`/`_run_logs`/`_last_run` helpers, `_workspace`, the autouse MAIL_* isolation fixture — copy the fixture pattern verbatim with the same save/restore discipline). Tests (all in-process `run()`, injected `now`/`load`/`run_id`):
  1. **Inert no-op (forced):** `run(["run", "--force", "--only", "roadmap-dev"], …)` → exit 0; last-run.txt shows `roadmap-dev=ok(0 items, 1 actions, 0 errors)` (the `no repos configured — nothing to scan` action); NO `state/roadmap-dev.json` created; NO `sandbox/roadmap-dev/` dir.
  2. **Gate-closed non-forced, quiet gate only context:** pick `now` outside the quiet window with `load` above threshold (quiet gate closed), fresh state, and the idle probe patched to report 0 active sessions with a fresh idle streak → first run: idle gate records its 1st poll (closed) → `roadmap-dev=ok(0 items, … actions, 0 errors)` (Phase 1 no-op runs — the entry is invoked even with the quiet gate closed), `noop` runs, `mail-keeper` skipped (env isolation), `oc-todo` skipped or ok (empty repos → ok no-op) — assert the workflow loop entered (last-run.txt lists `roadmap-dev=ok`, not a blanket skip) and `state/scheduler.json` gained `idle_gate_last_ok` (1st poll) while `gate_last_ok` is null/absent.
  3. **Idle gate 2nd poll opens:** repeat test 2 with the recorded 1st-poll state present and `now` advanced by `poll_interval_minutes` (30) → `roadmap-dev` invoked again, `idle_gate_last_ok` updated; assert the gate OPENED (reason visible in the run log `GATE … verdict=OPEN reason=no active sessions (2nd consecutive idle poll)` — grep the `run-*.log`).
  4. **Sessions active → no drain:** idle gate open (seed both streak states), probe patched to 2 active sessions → run → `roadmap-dev=ok(0 items, …, 0 errors)` with a `drain skipped` action (empty allowlist makes the drain a no-op anyway — the assertion target is `ctx.gate_open=False` behavior: the action list contains the gate-closed drain note, NOT a drain-start note) and `idle_gate_last_ok` cleared (streak reset).
  5. **Malformed section fail-fast:** config copy with `roadmap_prompts: {allowed_repos: "owner/name"}` (string, not list) → `run(...)` exits 2 and stderr contains `roadmap_prompts.allowed_repos`.
  6. **Scaffold sanity:** `parse_listing` (from `workflows.roadmap_dev`) on `autonomous_task_overview/plans.md` (the T5 staging skeleton) returns `[]` (a valid empty listing) — import the module, read the file by relative path from the repo root.
- **Acceptance:**
  1. `uv run pytest tests/smoke/ -v` green (all three smoke modules) with no network, no real agent, no live mail — run with `env -u GITHUB_PAT` to prove independence from the PAT.
  2. Each test asserts observable behavior (exit code, last-run.txt line, state-file content, log-line grep) — no "it didn't crash" tests.

### Task 3: Full-suite verification + tooling
- **Files:** (no source changes unless a regression is found — fix it, name it in the report)
- **Do:** Run, in order: `uv run ruff check .` → `uv run ruff format --check .` → `uv run pytest -v` (full suite) → `uv run agentic-scripts run --force --only roadmap-dev` (real config; then verify: exit 0, `logs/last-run.txt` has `roadmap-dev=ok(0 items, 1 actions, 0 errors)`, `state/roadmap-dev.json` absent, `sandbox/roadmap-dev` absent — and if the last-run check leaves the new `logs/run-*.log` behind, that is normal and stays) → `bash scripts/setup.sh` (must end `[OK] setup complete (no failures)`; the enabled entry now triggers the data-driven agent check for `planner-enhanced` — it exists, so [OK]).
- **Acceptance:**
  1. All four commands above succeed with the exact assertions in Context; record each in the result report's Build/Tests section (PASS/FAIL + one line).
  2. If a pre-existing test broke due to the T1 scheduler rewire, fix it minimally (behavior-preserving) and note it under Blockers.

## Out of Scope

- No workflow code changes (T4's drain is consumed as-is), no README/setup.sh/bootstrap changes (T5), no real-repo bootstrap execution, no `allowed_repos` population (operator action post-bootstrap — the user's choice of first repos), no archiving of this plan folder (orchestrator step after final report + user confirmation).

## Notes

- **[Assumption] Ship inert:** `enabled: true` + empty allowlist is the plan's "empty allowlist = no-op at ship" pattern — the workflow is registered, discoverable by `--only`, and auditable in last-run.txt, but does nothing until the operator lists repos.
- **[Note] Smoke test 2/3/4 seed the gate streaks** by writing `state/scheduler.json` directly (the tmp state dir) — do not try to drive real 30-min intervals.
- **[Note] The `--only roadmap-dev` acceptance run uses the REAL `state/` dir** — it must leave no `roadmap-dev` state file (asserted); other workflows' state files are untouched because `--only` skips them.
- **[Note] Post-bootstrap operator step (orchestrator, after this task + T5's script lands):** run `scripts/bootstrap_task_overview.sh --vault /workspace/Obsidian/ARP_roadmap` (push initial content to the empty repo + submodule-only vault commit + push — user pre-approved 2026-11-21), then seed `roadmap_prompts.allowed_repos` from the user's selection and commit. NOT part of this task's acceptance.
