# Task Plan: agentic_scripts cleanup (post-cutover-gate)

**Purpose:** Remove the roadmap-dev engine entirely from `agentic_scripts` — module,
config section + entry, preflight, bootstrap script, staging dir, tests, README section
— so no second process can ever reconcile the same listing. Runs ONLY after the user
has approved the cutover gate.

## Objective

In the LIVE checkout `/workspace/Python/agentic_scripts` (branch
`feature/roadmap-dev-workflow`), delete every roadmap-dev artifact, keep the remaining
workflows (noop, mail-keeper, oc-todo) with a 100% green suite, replace the README's
roadmap-dev section with a pointer to the new home, commit with the `OC:` prefix, and
push. The old cron entry stays UNTOUCHED (it now runs only the remaining workflows —
that is the intended post-cutover behavior).

## Context

- **Repo:** `/workspace/Python/agentic_scripts`, branch `feature/roadmap-dev-workflow`
  (the LIVE checkout — cron fires here; this task is the moment roadmap-dev leaves it).
  Package `agentic_scripts` under `src/`; config `config/workflows.yaml`; tests
  `tests/` + `tests/smoke/`; setup `scripts/setup.sh`; bootstrap
  `scripts/bootstrap_task_overview.sh`; staging dir `autonomous_task_overview/`
  (tracked; the OLD bootstrap's initial-content copy — now stale: its README predates
  the live vault README's detail-row docs, so NOTHING of value is lost by removing it);
  README `README.md` (~29 KB).
- **Precondition (verified by the orchestrator before dispatch):** the cutover gate was
  approved; the new engine's main holds the full engine + docs (overview repo); the
  byte-identical A/B check passed (work-plan Task 5). If any precondition is missing,
  STOP and report.
- **What stays (deliberately):** the multi-workflow `scheduler.py` (now driving only
  noop/mail-keeper/oc-todo), the quiet-window/load gate, `machine.load_threshold`,
  `github.py`, the mail package, `oc_todo` workflow + config, `admin_repo`, and the
  DORMANT idle-gate machinery (`evaluate_idle_gate`, `sessions.py`,
  `WorkflowEntry.gate`) — removing the idle machinery is a follow-up decision, not this
  task. `agent.py`/`git.py` docstring MENTIONS of roadmap-dev may stay (comments, not
  references).
- **Config mechanics (verified):** `roadmap_prompts` is an OPTIONAL section in
  `load_config` (empty defaults when absent) and `Config.roadmap_prompts` /
  `RoadmapPrompts` / `_load_roadmap_prompts` / `_EMPTY_ROADMAP_PROMPTS` /
  `DEFAULT_RUN_TIMEOUT_MINUTES` are the code surface to remove. After removal, the
  shipped config has no `roadmap_prompts:` key — `load_config` must not require it.
- **Test files that reference roadmap (must end green, with the references gone or
  re-targeted):** `tests/test_config.py` (roadmap_prompts section tests + the
  shipped-config test asserting the roadmap-dev entry + workflow-order test naming
  `roadmap-dev`), `tests/test_scheduler.py` (14 references — its idle-gate interaction
  tests use the roadmap-dev entry: re-target them to a synthetic idle-gated entry, e.g.
  a test-fixture config with a `gate: idle` workflow pointing at the existing
  `noop` module — the idle machinery stays, so these tests keep covering it),
  `tests/smoke/test_smoke_oc_todo.py` (5 references — likely last-run/summary
  expectations that include a roadmap-dev line), `tests/smoke/test_smoke_base.py`
  (check for references). Rule: the suite is the arbiter — the end state is zero
  roadmap references in `tests/` AND 100% green.
- **Git hygiene (CRITICAL):** the working tree carries UNTRACKED files from a separate
  session: `planning/mail-keeper-pruning/lightweight_dev_task_{1,2,3}_*.md`. NEVER
  `git add -A` / `git add .` — stage EXPLICIT paths only (the deletions via
  `git rm`/`git rm -r` of the named artifacts + the modified files). Those untracked
  files must still be untracked and unmodified at the end.
- **Git conventions:** commit prefix `OC:` (this is one commit); push after commit;
  branch `feature/roadmap-dev-workflow` (the live branch — do NOT switch branches in
  this checkout, do NOT rebase).

## Tasks

### Task 1: Deletions
- **Files (delete):** `src/agentic_scripts/workflows/roadmap_dev.py`, `tests/test_roadmap_dev.py`, `tests/test_roadmap_dev_scan.py`, `tests/test_roadmap_dev_pipeline.py`, `tests/smoke/test_smoke_roadmap_dev.py`, `scripts/bootstrap_task_overview.sh`, `autonomous_task_overview/` (whole tracked dir: `README.md` + `plans.md`)
- **Do:** `git rm` each (the dir with `git rm -r autonomous_task_overview`). Nothing else.
- **Acceptance:** `git status` shows exactly those deletions staged; no other path staged.

### Task 2: Config + code trim
- **Files (modify):** `config/workflows.yaml`, `src/agentic_scripts/config.py`, `scripts/setup.sh`
- **Do:**
  1. `config/workflows.yaml`: delete the entire `roadmap_prompts:` section (lines ~26–43 in the current file, incl. its comments) and the `roadmap-dev:` entry under `workflows:` (incl. its comments). Keep `machine` (full, incl. `load_threshold` + `quiet_window`), `agent`, `paths`, `admin_repo`, `oc_todo`, and `workflows:` = {noop, mail-keeper, oc-todo}.
  2. `config.py`: remove `RoadmapPrompts`, `_EMPTY_ROADMAP_PROMPTS`, `DEFAULT_RUN_TIMEOUT_MINUTES`, `_load_roadmap_prompts`, the `Config.roadmap_prompts` field, and the `roadmap_prompts` handling in `load_config` (the required-sections entry + the optional-load block + the constructor kwarg) and the docstring references. Keep `OCTodo`/`WorkflowEntry`/`Machine` (with `load_threshold`)/everything else untouched.
  3. `scripts/setup.sh`: delete step 6 (roadmap preflight, the `ROADMAP_LINES=…` block + its if/else) and renumber/adjust the header docstring (drop the roadmap-dev preflight clause). Keep every other step (uv, venv, env, admin repo, agents-over-enabled-workflows, runtime dirs, timer) — note step 5's data-driven agent check now resolves to mail-keeper + oc-todo-resolver only (no action needed).
- **Acceptance:**
  1. `uv run python -c "from pathlib import Path; from agentic_scripts.config import load_config; c = load_config(Path('config/workflows.yaml')); print([w.name for w in c.workflows])"` prints `['noop', 'mail-keeper', 'oc-todo']` and `not hasattr(c, 'roadmap_prompts')` is true.
  2. `grep -rn "roadmap_prompts\|RoadmapPrompts" src/agentic_scripts/` → only the docstring MENTIONS in `agent.py`/`git.py`/`sessions.py` may remain (comments); zero in `config.py`.
  3. `bash -n scripts/setup.sh` passes.

### Task 3: Test updates
- **Files (modify):** `tests/test_config.py`, `tests/test_scheduler.py`, `tests/smoke/test_smoke_oc_todo.py`, `tests/smoke/test_smoke_base.py` (if it references roadmap)
- **Do:**
  1. `test_config.py`: delete the `roadmap_prompts` section tests (`test_roadmap_prompts_absent_defaults`, `test_roadmap_prompts_shipped_loads`) — the concept no longer exists in this package; update the shipped-config-load test to assert workflows == [noop, mail-keeper, oc-todo] with NO roadmap-dev entry; update the workflow-order test (it currently expects `[noop, mail-keeper, oc-todo, roadmap-dev]`).
  2. `test_scheduler.py`: re-target every roadmap-dev reference to a SYNTHETIC idle-gated entry (test-fixture configs get a workflow entry with `gate: idle` and `module: agentic_scripts.workflows.noop`, `agent: null`) so the idle-gate interaction coverage (streak recording, 2nd-poll open, active-sessions close, `--only` semantics) is preserved against the dormant machinery. If a test is purely about roadmap-dev specifics (e.g. its name/behavior in last-run), convert it to the generic idle entry or delete it — the arbiter: green suite + idle-gate behavior still covered (at least one test must still drive `evaluate_idle_gate` through `run()`).
  3. `test_smoke_oc_todo.py` (+ `test_smoke_base.py` if needed): drop/adjust assertions that expected roadmap-dev lines in last-run/summaries (with the entry gone, the shipped-config smoke runs now list only the remaining workflows).
  4. Keep ALL other tests byte-identical.
- **Acceptance:**
  1. `grep -rln "roadmap" tests/` → no file matches (case-insensitive `roadmap-dev` and `roadmap_prompts`; a bare comment mentioning the move is acceptable ONLY in a docstring that says "moved to autonomous_task_overview").
  2. Idle-gate coverage still present (grep for `idle` in `test_scheduler.py` shows the re-targeted tests).

### Task 4: README
- **Files (modify):** `README.md`
- **Do:** Remove the roadmap-dev section(s) (the workflow description, its `roadmap_prompts.*` config table, the state/sandbox/attempt-branch references, the "First run" note about the allowlist, and the pointer to the archived `workflows-roadmap-dev` plan) and any other roadmap mentions (the triage-context line and the setup-step line). Replace with a short pointer section: "The `roadmap-dev` workflow (unattended plan-execution engine) has moved out of this repo — its single home is now the `y2d2/autonomous_task_overview` repository (engine package, `WORKFLOW.md`, `VARIABLES.md`, live `plans.md`). See that repo's README." Adjust the setup-steps list (setup.sh no longer runs the roadmap preflight) and the workflows list (noop, mail-keeper, oc-todo).
- **Acceptance:**
  1. `grep -in "roadmap" README.md` returns only the pointer sentence(s) naming the new home.
  2. The README's remaining workflow descriptions (mail-keeper, oc-todo) are intact and consistent with the trimmed config.

### Task 5: Full verification + commit + push
- **Do:**
  1. `uv run pytest -q` — 100% green (the whole remaining suite: base, config, gate, git, github, lock, mail-*, oc-todo*, scheduler, sessions, state, smoke).
  2. `uv run agentic-scripts run --help` exits 0 (CLI intact).
  3. `uv run ruff check .` clean (if the repo lints — mirror its config).
  4. `crontab -l` unchanged (the `# agentic-scripts` entry still there, byte-identical — this task does not touch the timer).
  5. Stage EXPLICITLY (the deleted paths are already staged by `git rm`; add the modified: `config/workflows.yaml`, `src/agentic_scripts/config.py`, `scripts/setup.sh`, the four test files, `README.md`). Verify `git status` shows NO untracked file staged and the `planning/mail-keeper-pruning/` files still untracked. Commit: `OC: Remove roadmap-dev workflow — moved to y2d2/autonomous_task_overview (module, config, preflight, bootstrap, staging dir, tests, README)`. Push.
- **Acceptance:**
  1. Suite 100% green; CLI ok; ruff clean; crontab unchanged.
  2. Commit landed + pushed on `feature/roadmap-dev-workflow`; `git show --stat HEAD` lists exactly the intended paths (deletions + modifications) — no stray files, no `plans` files, no `planning/` files.
  3. `git status` after push: clean except the pre-existing untracked `planning/mail-keeper-pruning/` files.

## Out of Scope
- Installing/removing any cron entry (Task 7 installs the NEW one; the old one stays).
- Removing the dormant idle-gate machinery, `github.py`, or anything mail/oc-todo.
- Any change in the overview repo.

## Notes
- **[Risk]** This is the LIVE checkout — a broken commit here degrades the running
  engine (mail-keeper/oc-todo) at the next cron fire. The full-suite-green + CLI checks
  (Task 5.1–2) are the guard; a FAIL means revert YOUR OWN staged work by unstaging
  (`git restore --staged` + re-edit) — never destructive reset. The pre-commit state is
  fully intact in git (branch tip before this commit).
- **[Assumption]** `test_scheduler.py`'s roadmap references are fixture/config-level
  (verified: 14 grep hits), not deep coupling to roadmap-specific behavior — the
  synthetic idle-entry re-target keeps the idle machinery covered. If the coupling runs
  deeper than expected, STOP and report rather than deleting coverage.
- **[Rollback]** If anything post-commit looks wrong: `git revert HEAD` + push (an
  inverse commit, per git-workflow) re-arms the old engine; the new engine's cron entry
  does not exist yet (Task 7 runs after this one), so no double-engine window can occur
  from a rollback of THIS commit.
