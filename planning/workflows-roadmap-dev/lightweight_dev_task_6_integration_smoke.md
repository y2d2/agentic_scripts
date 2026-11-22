# lightweight-dev Output — Task: final integration: enable the workflow + hermetic smoke suite

**Task:** #6    **Session:** ses_dfe55efedffeyYp2RpdDwrWnjr    **Date:** 2026-11-22

## Summary

Shipped `roadmap-dev` in its safe default state (Subtask 1): `workflows.roadmap-dev.enabled: true`
with the one-line inert comment, and `roadmap_prompts.listing_repo` fixed to the renamed
`y2d2/autonomous_task_overview` (user decision 2026-11-21); `allowed_repos` ships `[]` (the
orchestrator seeds the 9 repos post-bootstrap). Wrote the hermetic smoke suite
(Subtask 2): `tests/smoke/test_smoke_roadmap_dev.py` with the 6 planned tests, mirroring
`test_smoke_oc_todo.py` (docstring, `_write_config`/`_run_logs`/`_last_run`/`_workspace`,
autouse MAIL_* save/restore fixture). **Probe seam documented in the module docstring:**
T1's run()-level seam is the scheduler's own import site — the tests monkeypatch
`agentic_scripts.scheduler.read_active_sessions` (the name bound at `scheduler` import time)
with a canned 0/2-session lambda, exactly as T1's idle-gate tests in `tests/test_scheduler.py`
do; neither `sessions.read_service_state` (home-dir read) nor `sessions._urlopen` (HTTP GET
against the live service) is ever reached. Test 4 drives a REAL phase-1 scan over LOCAL
bare-repo fixtures (`repo_urls`/`listing_repo_url` overrides; local-protocol `git clone`, no
network, `GITHUB_PAT` unset, git identity via autouse fixture) so the `ctx.gate_open=False`
drain note is observable. Verified the whole suite + tooling (Subtask 3) in the plan's exact
order; 318/318 green (312 baseline + 6 new). Three pre-existing tests that assumed the
entry shipped disabled were updated minimally (behavior-preserving; named under Blockers),
one T1 scheduler last-run rendering bug surfaced by the flip was fixed minimally
(`gate: FORCED` was written for gate-triggered runs), and the new enabled idle-gate entry's
probe was hermeticized for all pre-existing non-forced shipped-config runs (2 per-test
patches + a new `tests/smoke/conftest.py` autouse fixture). Committed locally
(`OC:`-prefixed, explicit paths, planning/ untouched); NOT pushed (orchestrator pushes
between waves).

## Files

| File | Action | Why |
|---|---|---|
| `config/workflows.yaml` | modify | Subtask 1 — `roadmap-dev.enabled: true` + one-line inert comment; `listing_repo: y2d2/autonomous_task_overview`; `allowed_repos: []` kept empty |
| `tests/smoke/test_smoke_roadmap_dev.py` | create | Subtask 2 — the 6 hermetic run()-level smoke tests (registered no-op, idle-gate 1st poll, 2nd poll opens, sessions-active no-drain over local bare fixtures, malformed-section exit 2, scaffold `parse_listing` → `[]`) |
| `tests/smoke/conftest.py` | create | Autouse canned-probe fixture (0 sessions at the scheduler's import site) keeping the whole smoke suite hermetic now that a non-forced shipped-config run evaluates the idle gate |
| `src/agentic_scripts/scheduler.py` | modify | Minimal T1-rewire fix: the final `write_last_run` now renders the quiet gate's ACTUAL verdict for gate-triggered runs (previously `gate: FORCED`, contradicting `trigger: gate`); `gate: FORCED` only under `--force` |
| `tests/test_config.py` | modify | Pre-existing flip break — `test_roadmap_prompts_shipped_loads` now asserts the new shipped values (`enabled is True`, `listing_repo == "y2d2/autonomous_task_overview"`) |
| `tests/test_scheduler.py` | modify | Pre-existing flip break — `test_only_disabled_roadmap_dev_is_clean_noop` (pinned disabled-ship behavior) renamed `test_only_roadmap_dev_inert_noop` and updated to the enabled-ship behavior (loop entered, 1st idle poll recorded, inert no-op, `overall: ok`); probe patched; 2 other shipped-config non-forced runs probe-patched for hermeticity |
| `tests/smoke/test_smoke_oc_todo.py` | modify | Pre-existing flip break — `test_smoke_oc_todo_gate_closed_noop`: quiet-gate-closed runs now enter the loop (inert roadmap-dev no-op), so `overall: skipped` → `overall: ok`; added the oc-todo quiet-gate-skip line assertion; docstring updated |

## Build / Tests

- Task-1 acceptance one-liner (`uv run python -c "...assert e.enabled and e.gate=='idle' and e.agent=='planner-enhanced'; assert c.roadmap_prompts.listing_repo == 'y2d2/autonomous_task_overview'..."`): PASS — prints `ok` (also asserted `allowed_repos == []`).
- `uv run ruff check .`: PASS — "All checks passed!".
- `uv run ruff format --check .`: FAIL — 4 files would be reformatted, ALL pre-existing tracked `planning/**/*.md` docs (whitespace drift in markdown code fences; tracked + unmodified at HEAD, i.e. failing BEFORE this task); 0 files created/modified by this task fail it, and `uv run ruff format --check src tests` (the T1–T5 scope) is clean (49 files) — see Blockers #1.
- `uv run pytest -v` (full suite): PASS — 318 passed (312 baseline + 6 new), 0 failed, 72.5s. NOTE: `GITHUB_PAT` is unset in this environment (and in `.env`), so this run is byte-identical to the PAT-stripped acceptance run.
- `env -u GITHUB_PAT uv run pytest tests/smoke/ -v` (Task-2 acceptance): PASS — 19 passed across all four smoke modules (base 5, mail-keeper 4, oc-todo 4, roadmap-dev 6); no network, no real agent, no live mail.
- `uv run agentic-scripts run --force --only roadmap-dev` (real config, real `state/`+`logs/`+`sandbox/`): PASS — exit 0; `logs/last-run.txt` = `trigger: force` / `gate: FORCED` / `roadmap-dev=ok(0 items, 1 actions, 0 errors)` / `overall: ok`; `state/roadmap-dev.json` ABSENT; `sandbox/roadmap-dev` ABSENT; run log `RUN END gate=forced workflows=1 errors=0 duration=0.0s`; the new `logs/run-20261122T061614Z.log` stays (normal per plan).
- `bash scripts/setup.sh`: PASS — ends `[OK] setup complete (no failures)` (exit 0); the enabled entry triggered the data-driven check and passed: `[OK] agent for workflow 'roadmap-dev': planner-enhanced`; `[OK] roadmap-dev: allowlist empty — workflow is inert (no-op until repos are listed)`; only advisory `[WARN] GITHUB_PAT missing` (not a failure).

## Acceptance Verification

| # | Criterion (verbatim) | Result | Notes |
|---|---|---|---|
| T1.1 | `uv run python -c "from agentic_scripts.config import load_config, PROJECT_ROOT; c = load_config(PROJECT_ROOT/'config/workflows.yaml'); e = [w for w in c.workflows if w.name=='roadmap-dev'][0]; assert e.enabled and e.gate=='idle' and e.agent=='planner-enhanced'; assert c.roadmap_prompts.listing_repo == 'y2d2/autonomous_task_overview'; print('ok')"` prints `ok` | PASS | Prints `ok`. |
| T1.2 | `uv run pytest -v` (full suite as of T4/T5, before the new smoke file) still green. | PASS | Interpreted as "the pre-existing suite stays green after the flip": all 312 baseline tests pass (3 of them required minimal behavior-preserving updates for the flip — named under Blockers). Final full suite: 318/318. |
| T2.1 | `uv run pytest tests/smoke/ -v` green (all three smoke modules) with no network, no real agent, no live mail — run with `env -u GITHUB_PAT` to prove independence from the PAT. | PASS | All FOUR smoke modules green (the plan predates this module's own addition): 19 passed, `env -u GITHUB_PAT`. |
| T2.2 | Each test asserts observable behavior (exit code, last-run.txt line, state-file content, log-line grep) — no "it didn't crash" tests. | PASS | Every test asserts exit code + log-line greps (`WORKFLOW … status=…`, `reason=…`, `active_sessions=…`) and/or state-file content (`idle_gate_last_ok` set/cleared, `gate_last_ok` null) and/or last-run.txt lines and/or sandbox/state absence; test 4 additionally asserts the fixture clone landed in the sandbox. |
| T3.1 | All four commands above succeed with the exact assertions in Context; record each in the result report's Build/Tests section (PASS/FAIL + one line). | PARTIAL | 4 of 5 recorded commands PASS (ruff check, pytest, live no-op with all 4 assertions, setup.sh); `uv run ruff format --check .` FAILs on 4 PRE-EXISTING unformatted planning docs (tracked + unmodified at HEAD; none of this task's files) — recorded in Build/Tests + Blockers #1. All live-run assertions held verbatim. |
| T3.2 | If a pre-existing test broke due to the T1 scheduler rewire, fix it minimally (behavior-preserving) and note it under Blockers. | PASS | Three flip-breaks fixed minimally (Blockers #2) + one T1-rewire last-run rendering bug fixed minimally (Blockers #3) + hermeticity probe patches for 5 pre-existing runs (Blockers #4). |

## Blockers

None blocking — the task is complete and the suite is green. Items needing orchestrator
attention (all named per T3.2, all already fixed in-tree where in scope):

1. **`uv run ruff format --check .` fails on 4 pre-existing planning docs** (T3.1 recorded as
   PARTIAL for this one command): `planning/mail-keeper-pruning/work_plan_task_1_prune_module.md`,
   `planning/mail-keeper-pruning/work_plan_task_2_runner_hook.md`,
   `planning/workflows-mail-keeper/work_plan_task_5f_pool_order.md`,
   `planning/workflows-mail-keeper/work_plan_task_5h_step_sentinel.md` — whitespace/line-wrap
   drift in markdown code fences, tracked + unmodified at HEAD (they failed the repo-wide gate
   BEFORE this task; T1's report hit the identical drift for 7 src/test files and committed an
   AST-identical fix). I left them untouched: the dispatch forbids committing anything under
   `planning/` and they are outside this task's file scope. Everything this task created or
   modified is format-clean (`ruff format --check src tests` → 49 files clean). Suggested
   orchestrator options: (a) commit a whitespace-only `ruff format` fix for those 4 files as
   housekeeping, or (b) add `planning/` to ruff's `extend-exclude` (planning docs are
   inter-agent artifacts, not code).
2. **Pre-existing tests broken by the `enabled: true` flip (fixed minimally, behavior-preserving):**
   - `tests/test_config.py::test_roadmap_prompts_shipped_loads` — asserted the shipped
     `entry.enabled is False` and the stale `listing_repo == "y2d2/ARP_prompts"`; updated to the
     new shipped values (`is True` / `y2d2/autonomous_task_overview`) + docstring note.
   - `tests/test_scheduler.py::test_only_disabled_roadmap_dev_is_clean_noop` — pinned the
     disabled-ship behavior (`overall: skipped`, `workflows: -`, no idle streak key); renamed to
     `test_only_roadmap_dev_inert_noop` and updated to the enabled-ship reality (the name is
     still registered → no usage error; quiet gate closed; idle gate records its 1st poll via the
     T1 probe seam; inert no-op `roadmap-dev=ok(0 items, 1 actions, 0 errors)`; `overall: ok`;
     `idle_gate_last_ok` set, `gate_last_ok` null, no state file).
   - `tests/smoke/test_smoke_oc_todo.py::test_smoke_oc_todo_gate_closed_noop` — asserted
     `overall: skipped`; with the enabled idle-gate entry, a quiet-gate-closed run now enters the
     workflow loop (oc-todo skipped by the quiet gate, inert roadmap-dev no-ops), so the run ends
     `overall: ok`. Assertion updated + oc-todo skip-line assertion added + docstring; the
     no-repo-touched assertions (the test's intent) are unchanged.
3. **T1 scheduler-rewire bug surfaced by the flip (fixed minimally in `scheduler.py`):** the
   final `write_last_run` in `run()` passed `gate_line=None`, so a NON-forced (gate-triggered)
   run that entered the workflow loop wrote `gate: FORCED` to `last-run.txt` while writing
   `trigger: gate` — an audit-trail contradiction (pre-existing: no test exercised that path
   before the flip, because gate-closed runs early-returned). `tests/smoke/test_smoke_base.py::
   test_smoke_gate_closed_noop` broke on `assert "gate: CLOSED" in last` as a consequence. Fix:
   the final write now renders the quiet gate's actual verdict (same format as the early-return
   path) for gate-triggered runs; `gate: FORCED` is retained exactly for `--force`.
   `test_mail_keeper.py::test_base_smoke_compatibility` (spawns the base smoke suite) failed only
   via this same root cause and passes after the fix.
4. **Hermeticity of pre-existing non-forced shipped-config runs (fix added):** the flip makes
   `idle_entries` non-empty for every full shipped-config run, so `run()` now evaluates the idle
   gate — unpatched, the REAL probe (`~/.local/state/opencode/service.json` + HTTP GET) would be
   consulted by 5 pre-existing tests (`test_scheduler.py::test_gate_closed_noop`,
   `test_two_step_gate`, and the smoke base/oc-todo gate tests). Fixed with T1's own seam
   (monkeypatch `agentic_scripts.scheduler.read_active_sessions`): 2 per-test patches in
   `test_scheduler.py` (canned 0) and a NEW `tests/smoke/conftest.py` autouse fixture (canned 0)
   covering the smoke suite; test-local patches (0 or 2) in `test_smoke_roadmap_dev.py` override
   it per test (same `monkeypatch` instance, LIFO undo).

## Next Steps

- Orchestrator: push the branch (this task committed locally, no push, per dispatch).
- Orchestrator decision on Blockers #1 (format the 4 planning docs, or exclude `planning/` from
  ruff) so the repo-wide `ruff format --check .` gate goes green.
- Post-bootstrap operator steps (NOT part of this task, per the plan): run
  `scripts/bootstrap_task_overview.sh --vault /workspace/Obsidian/ARP_roadmap` (user pre-approved
  2026-11-21), then seed `roadmap_prompts.allowed_repos` from the user's repo selection and commit.
- Plan-folder archiving is an orchestrator step after final report + user confirmation.
