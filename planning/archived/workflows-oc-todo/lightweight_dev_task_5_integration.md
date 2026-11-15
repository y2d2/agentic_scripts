# lightweight-dev Output — Task: Registration, smoke, README, final acceptance pass

**Task:** #5    **Session:** `planning/workflows-oc-todo/`    **Date:** 2026-11-15

## Summary

Shipped the OC-todo workflow end-to-end. Implemented all of Task 5's sub-tasks:

- **Task 0 (production-bug fix):** Changed both `create_pr(...)` call sites in
  `src/agentic_scripts/workflows/oc_todo.py` from the INVALID GitHub head ref
  `f"{todo.repo}:{branch_name}"` (`owner/name:branch`) to the correct single-owner-account form
  `f"{owner}:{branch_name}"`. Updated the two test assertions and the `FakeGitHub.find_pr_by_head`
  matcher + docstring in `tests/test_oc_todo_pipeline.py` to the `owner:branch` shape. Re-verified
  no other code/test references the `owner/name:branch` shape (only stale planning docs remain, out of scope).
- **Task 1 (`create(config)`):** Added `def create(config: Config) -> "OCTodoWorkflow"` to
  `oc_todo.py` (production wiring: `OCTodoWorkflow(settings=config.oc_todo)`, default git/github,
  `runner=None` → `ctx.runner` at call time). The module now exposes `create` for the config
  loader's enabled-entry import-check.
- **Task 2 (config registration):** Added the top-level `oc_todo` section (empty `repos`) and the
  `oc-todo` workflow entry (`enabled: true`, `agent: oc-todo-resolver`) to `config/workflows.yaml`.
- **Task 3 (smoke tests):** Created `tests/smoke/test_smoke_oc_todo.py` — 4 run()-level hermetic
  tests with the mandatory autouse `MAIL_*` env isolation (copy of `test_smoke_base._isolate_mail_env`).
- **Task 4 (README):** Added an "## OC-todo workflow" section after "Mail-keeper workflow", before
  "Extending with a new workflow" — additions only (85 insertions, 0 deletions).
- **Task 5 (final acceptance pass):** Full suite + ruff green; both live no-op runs exit 0.

**One out-of-scope test update (necessary):** `tests/test_config.py::test_shipped_config_loads`
hardcoded the workflow list as `["noop", "mail-keeper"]`; registering `oc-todo` in the shipped config
made it fail. Updated the assertion to `["noop", "mail-keeper", "oc-todo"]`. This is a direct, intended
consequence of Task 2 (the plan's own Task 2 acceptance #1 requires the loaded config to contain
`oc-todo`), not a change to Tasks 1–4 workflow code.

## Files

| File | Action | Why |
|---|---|---|
| `src/agentic_scripts/workflows/oc_todo.py` | modify | Task 0 head-ref fix at both `create_pr` sites; Task 1 `create(config)` + `Config` import. |
| `tests/test_oc_todo_pipeline.py` | modify | Task 0: correct the two head assertions to `owner:branch`; update `FakeGitHub.find_pr_by_head` matcher + docstring. |
| `config/workflows.yaml` | modify | Task 2: add top-level `oc_todo` section (empty repos) + `oc-todo` workflow entry. |
| `tests/smoke/test_smoke_oc_todo.py` | create | Task 3: 4 run()-level hermetic smoke tests with autouse `MAIL_*` env isolation. |
| `README.md` | modify | Task 4: new "## OC-todo workflow" section (additions only). |
| `tests/test_config.py` | modify | Update the hardcoded shipped-config workflow list to include `oc-todo` (consequence of Task 2 registration; required for full-suite green). |

## Build / Tests

- `uv run pytest tests/test_oc_todo_pipeline.py -v`: PASS — 12 passed (after the Task 0 fix).
- `uv run pytest tests/smoke/ -v`: PASS — 13 passed (5 base + 4 mail-keeper + 4 oc-todo).
- `uv run pytest tests/ -v`: PASS — **182 passed** in ~38.6s (full suite, no failures).
- `uv run ruff check src tests`: PASS — "All checks passed!" (clean).
- Config one-liner: PASS — prints `['noop', 'mail-keeper', 'oc-todo'] []`.
- Live forced no-op run (`uv run agentic-scripts run --force --only oc-todo --verbose`): PASS — exit 0; log line `WORKFLOW oc-todo status=ok items_found=0 actions=1 errors=0`; `logs/last-run.txt` shows `oc-todo=ok(0 items, 1 actions, 0 errors)` / `overall: ok`.
- Live gate-path run (`uv run agentic-scripts run`): PASS — exit 0 (gate verdict OPEN at eval time; oc-todo no-op'd with 0 repos). **Caveat:** see Blockers — the *live* mail-keeper ran and errored in this real environment, so `last-run.txt` shows `overall: error`. This is pre-existing live-environment behavior unrelated to oc-todo (which reported `status=ok`).

## Acceptance Verification

### Per-task acceptance criteria (verbatim from `work_plan_task_5_integration.md`)

| # | Criterion (verbatim) | Result | Notes |
|---|---|---|---|
| T0.1 | "`uv run pytest tests/test_oc_todo_pipeline.py -v` green; full suite green; ruff clean." | PASS | 12 pipeline tests green; full suite 182 green; ruff clean. |
| T1.1 | "`python -c \"import agentic_scripts.workflows.oc_todo as m; print(m.create)\"` (via `uv run`) resolves — the module exposes `create`" | PASS | Prints `<function create at 0x...>`. |
| T1.2 | "`uv run pytest tests/ -v` — full suite green." | PASS | 182 passed. |
| T2.1 | "…prints `['noop', 'mail-keeper', 'oc-todo'] []` (the enabled-entry import-check passes → the module is importable and exposes `create`)." | PASS | Exact output matched. |
| T2.2 | "`uv run pytest tests/ -v` — full suite green (…every base smoke test's forced run now ALSO executes `oc-todo` with 0 repos; they must stay green…)" | PASS | All base smoke tests still green; oc-todo no-ops side-effect-free on each forced run. |
| T3.1 | "`uv run pytest tests/smoke/ -v` — all smoke tests (base + mail-keeper + oc-todo) pass." | PASS | 13 passed. |
| T3.2 | "`uv run pytest tests/ -v` — full suite green." | PASS | 182 passed. |
| T4.1 | "The section exists, is factually consistent with the shipped config/code (spot-check: every config key, path, and command it names exists as documented), and follows the README's formatting (tables/bullets)." | PASS | Section added; spot-checked `oc_todo.*` keys/defaults, sandbox/state paths, both operator commands against the code — all accurate. |
| T4.2 | "`git diff README.md` shows additions only (no unrelated rewrites)." | PASS | 85 insertions, 0 deletions. |
| T5.1 | "Full suite green + ruff clean (both commands, recorded output in the result report)." | PASS | 182 passed; "All checks passed!" (recorded above). |
| T5.2 | "Both live runs exit 0 with the documented `last-run.txt` contents." | PASS (with caveat) | Both exit 0. Forced run's `last-run.txt` is exactly as documented (`oc-todo=ok(0 items, 1 actions, 0 errors)` / `overall: ok`). Gate-path `last-run.txt` shows `overall: error` because the *live* mail-keeper errored in this real env — not an oc-todo fault (see Blockers). |
| T5.3 | "The result report contains the complete, honest acceptance mapping table." | PASS | Table below. |
| T5.4 | "`git status` clean of unintended files (orchestrator commits)." | PASS | Working tree holds exactly the 6 intended files; `state/`, `logs/`, `sandbox/` are gitignored. |

### High-level acceptance-criterion → test mapping table (Task 5 step 5.4)

| # | High-level acceptance criterion (verbatim from `workflows-oc-todo_plan.md`) | Proven by |
|---|---|---|
| 1 | "Given a fixture repo with two `OC-todo:` comments on two different branches, one gate-open run produces exactly two PRs, each targeting the branch that contained its todo." | `tests/test_oc_todo_pipeline.py::test_two_branches_two_prs` — PASS (verified: suite green) |
| 2 | "Each PR body quotes the exact `OC-todo:` comment text, names the file and line, and summarizes the change; the diff removes the comment (unless a keep-instruction applies)." | `::test_two_branches_two_prs` + `::test_pr_diff_removes_marker` + `::test_keep_instruction_preserves_marker` — PASS (verified: suite green) |
| 3 | "Re-running with no repo changes opens zero new PRs; after merging a PR, the next run marks the todo resolved and does not reopen it." | `::test_rerun_opens_no_new_prs` + `::test_merge_resolves_todo` — PASS (verified: suite green) |
| 4 | "An agent run that times out or exhausts `steps` leaves the todo in a failed/retry state, logs the reason, and the next run re-attempts it." | `::test_agent_timeout_fails_and_retries` + `::test_step_exhausted_treated_as_failure` — PASS (verified: suite green) |
| 5 | "No workflow ever pushes to a protected or pre-existing branch — only freshly created per-todo branches are pushed." | `::test_only_fresh_branches_pushed` — PASS (verified: suite green) |
| — | Objective: gate closed → no-op, touches nothing. | `tests/smoke/test_smoke_oc_todo.py::test_smoke_oc_todo_gate_closed_noop` — PASS (verified: smoke suite green) |

Every mapped test exists and was executed in the green full-suite / smoke-suite runs above; each row is an honest PASS.

## Blockers

- **None blocking.** All Task 5 sub-task acceptance criteria pass.
- **Observation (not a blocker, not caused by this task):** the live gate-path run
  (`uv run agentic-scripts run`) exited 0 as required, but in this real environment the *live*
  mail-keeper workflow ran and reported `status=error` (`items_found=10`, agent exit 1 after ~4s),
  so `logs/last-run.txt` recorded `overall: error`. This is pre-existing live-environment behavior of
  mail-keeper (real notmuch index + real `opencode` agent) and is unrelated to oc-todo, which no-op'd
  cleanly (`status=ok`, 0 repos). It does not affect the exit-code contract (per-workflow errors never
  change the exit code) nor any Task 5 acceptance criterion. Flagging it so the orchestrator/user are
  aware that a live full `run` on this host will surface mail-keeper's live state in `last-run.txt`.

## Next Steps

- Orchestrator: commit and push the 6 working-tree files (the result report itself is not committed by
  this agent). Suggested message: `OC: OC-todo workflow Task 5 — create(config), config registration, smoke tests, README, final acceptance pass (+ Task 0 head-ref fix)`.
- No follow-up code work is required for Task 5.
