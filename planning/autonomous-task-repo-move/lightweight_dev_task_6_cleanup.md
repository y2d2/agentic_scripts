# lightweight-dev Output — Task: Post-cutover-gate cleanup (roadmap-dev removal)

**Task:** #6    **Session:** (lightweight-dev sub-agent of the `autonomous-task-repo-move` plan)    **Date:** 2026-11-24

## Summary

Removed the roadmap-dev engine entirely from the LIVE checkout
`/workspace/Python/agentic_scripts` (branch `feature/roadmap-dev-workflow`), per the
user-approved cutover gate (evidence pack: `lightweight_dev_task_5_merge_cutover_check.md`).
All 5 sub-tasks ran IN ORDER, each verified against its acceptance criteria:

1. **Deletions** — `git rm` of the 7 named artifacts + the tracked staging dir
   (`autonomous_task_overview/` = `README.md` + `plans.md`) = 8 staged deletion paths, nothing
   else staged.
2. **Config + code trim** — `config/workflows.yaml` lost the `roadmap_prompts:` section and the
   `roadmap-dev:` workflow entry (remaining: `machine` full incl. `load_threshold`, `agent`,
   `paths`, `admin_repo`, `oc_todo`, `workflows:` = {noop, mail-keeper, oc-todo}); `config.py`
   lost `RoadmapPrompts`, `_EMPTY_ROADMAP_PROMPTS`, `DEFAULT_RUN_TIMEOUT_MINUTES`,
   `_load_roadmap_prompts`, the `Config.roadmap_prompts` field, the `allowed_sections` entry,
   the optional-load block, the constructor kwarg, and the docstring references; `setup.sh` lost
   step 6 (roadmap preflight), header clause dropped, steps renumbered 7→6, 8→7, 9→8.
3. **Test updates** — the 4 plan-named files were updated, plus 3 further files the
   zero-references end-state required (see Files table): `tests/conftest.py`,
   `tests/smoke/conftest.py`, `tests/smoke/test_smoke_mail_keeper.py` each carried a
   `data["roadmap_prompts"]["allowed_repos"] = []` hermetic line (or, for the smoke conftest, a
   module docstring) that would have failed after the trim. `test_scheduler.py`'s
   `test_only_roadmap_dev_inert_noop` was re-targeted to a SYNTHETIC idle-gated entry
   (`idle_entry`: `gate: idle`, `module: agentic_scripts.workflows.noop`, `agent: null`) so the
   `--only` + idle-gate semantics survive; the 3 probe tests already covered
   `evaluate_idle_gate` through `run()` via their `idle_probe` entry and are byte-identical.
   `tests/smoke/test_smoke_oc_todo.py`'s gate-closed test was re-pointed at the scheduler's
   blanket-skip behavior (`overall: skipped`, no WORKFLOW lines) — the correct post-trim
   semantics, since the shipped config no longer carries an idle-gate workflow (verified
   against `scheduler.py:646`'s early-return). Now-unnecessary `read_active_sessions`
   monkeypatches on shipped-config tests were dropped with their roadmap comments.
4. **README** — the entire `## Roadmap-dev workflow` section (~195 lines), the setup-step
   preflight line (renumbered), and the triage-context vault name (`ARP_roadmap` → "admin
   vault", keeping the grep criterion literal while staying consistent with the config's
   surviving `admin_repo`) were replaced with the pointer section
   `## Unattended plan execution (moved)`.
5. **Full verification + commit + push** — full suite 237/237 green, CLI `--help` exit 0,
   `ruff check .` clean, crontab byte-identical (`cfb0988abb2ccee6dc0a3a628e485caf`); explicit
   staging (19 paths, verified `git status`); one commit
   `OC: Remove roadmap-dev workflow — moved to y2d2/autonomous_task_overview (module, config,
   preflight, bootstrap, staging dir, tests, README)`; pushed to `origin/feature/roadmap-dev-workflow`.

### Interleaving note (expected, per spec — no failure)

The natural **09:30:01Z cron fire overlapped my edit window** (config + code trim complete at
that moment; test/README edits in flight). It ran **cleanly against the trimmed working tree**:
`RUN START force=False` → `GATE … verdict=CLOSED reason=outside quiet window` → `RUN END
gate=closed workflows=0 errors=0 duration=0.0s`, 0 ERROR lines, last-run.txt
`overall: skipped`, `workflows: -`. No config-load fault (exit 2) occurred — at 09:30:01 the
runtime-relevant files (`config/workflows.yaml`, `config.py`, `setup.sh`) were already trimmed
and mutually consistent, and the run is a gate-closed no-op that touches nothing. This is live
confirmation that the post-cutover cron now sees only noop/mail-keeper/oc-todo (the 09:00 fire,
pre-task, still showed the old 4-entry behavior incl. `active_sessions=2` idle-gate probe).
The cron entry was NOT touched (byte-identical, md5
`cfb0988abb2ccee6dc0a3a628e485caf` before and after). No engine run overlapped the FINAL
verification (the 09:30 run ended at 09:30:01 with `duration=0.0s`; the full suite ran at
09:35, commit landed 09:37:30; next fire is 10:00).

## Files

| File | Action | Why |
|---|---|---|
| `src/agentic_scripts/workflows/roadmap_dev.py` | delete (git rm) | Plan Task 1 — the engine module, now home in `y2d2/autonomous_task_overview` |
| `tests/test_roadmap_dev.py` | delete (git rm) | Plan Task 1 — engine core tests move with the engine |
| `tests/test_roadmap_dev_scan.py` | delete (git rm) | Plan Task 1 — Phase-1 pipeline tests move with the engine |
| `tests/test_roadmap_dev_pipeline.py` | delete (git rm) | Plan Task 1 — drain/per-job pipeline tests move with the engine |
| `tests/smoke/test_smoke_roadmap_dev.py` | delete (git rm) | Plan Task 1 — engine smoke test moves with the engine |
| `scripts/bootstrap_task_overview.sh` | delete (git rm) | Plan Task 1 — one-shot listing-repo bootstrap; its job is done (repo live since Task 5) |
| `autonomous_task_overview/` (whole dir: `README.md` + `plans.md`) | delete (git rm -r) | Plan Task 1 — tracked staging dir, stale initial content, value now lives in the overview repo |
| `config/workflows.yaml` | modify | Task 2 — removed the `roadmap_prompts:` section + the `roadmap-dev:` entry; `workflows:` = {noop, mail-keeper, oc-todo} |
| `src/agentic_scripts/config.py` | modify | Task 2 — removed `RoadmapPrompts`, `_EMPTY_ROADMAP_PROMPTS`, `DEFAULT_RUN_TIMEOUT_MINUTES`, `_load_roadmap_prompts`, `Config.roadmap_prompts` field, `allowed_sections` entry, optional-load block, constructor kwarg, docstring refs |
| `scripts/setup.sh` | modify | Task 2 — removed step 6 (roadmap preflight) + header clause; renumbered steps 7→6, 8→7, 9→8 |
| `tests/test_config.py` | modify | Task 3 — deleted the 10-test `roadmap_prompts` section block (incl. `test_roadmap_prompts_absent_defaults`, `test_roadmap_prompts_shipped_loads`); shipped-config test now asserts order [noop, mail-keeper, oc-todo] |
| `tests/test_scheduler.py` | modify | Task 3 — dropped the hermetic `roadmap_prompts` line; `test_only_roadmap_dev_inert_noop` re-targeted to synthetic `idle_entry` (`gate: idle`, noop module, `agent: null`); removed now-unnecessary `read_active_sessions` monkeypatches + roadmap comments; idle-gate probe tests (which drive `evaluate_idle_gate` through `run()`) kept byte-identical |
| `tests/smoke/test_smoke_oc_todo.py` | modify | Task 3 — dropped 3 hermetic `roadmap_prompts` lines; gate-closed test re-pointed at blanket-skip semantics (`overall: skipped`, no WORKFLOW lines) |
| `tests/smoke/test_smoke_base.py` | modify | Task 3 — dropped the hermetic `roadmap_prompts` line (only reference) |
| `tests/conftest.py` | modify | Task 3 (beyond the plan's named list — required by its zero-references end-state) — dropped the `base_config` fixture's hermetic `roadmap_prompts` line |
| `tests/smoke/conftest.py` | modify | Task 3 (beyond the plan's named list — required by its zero-references end-state) — module docstring rewritten roadmap-free; the autouse canned-probe fixture kept as inert defense-in-depth (no shipped workflow is `gate: idle` now, so it is never consulted until one is re-registered) |
| `tests/smoke/test_smoke_mail_keeper.py` | modify | Task 3 (beyond the plan's named list — required by its zero-references end-state) — dropped the hermetic `roadmap_prompts` line |
| `README.md` | modify | Task 4 — removed the `## Roadmap-dev workflow` section (~195 lines), the setup-step preflight line (list renumbered), the `ARP_roadmap` vault name in the triage-context line; added `## Unattended plan execution (moved)` pointer to `y2d2/autonomous_task_overview` |
| `planning/autonomous-task-repo-move/lightweight_dev_task_6_cleanup.md` | create | This result report (stays UNTRACKED, per git-hygiene guardrail) |

No files in the overview repo (`/workspace/Python/autonomous_task_overview`) were touched.
The old cron entry was NOT modified.

## Build / Tests

- **Full suite (`uv run pytest -q`):** PASS — **237 passed in 37.83s**, 0 failed, 0 errors,
  0 skipped (the whole remaining suite: base, config, gate, git, github, lock, mail-*,
  oc-todo*, scheduler, sessions, state, smoke).
- **CLI (`uv run agentic-scripts run --help`):** PASS — exit 0.
- **Lint (`uv run ruff check .`):** PASS — "All checks passed!" (repo's config: E/F/I/UP/W,
  line-length 100).
- **Crontab:** PASS — `crontab -l | md5sum` = `cfb0988abb2ccee6dc0a3a628e485caf` before and
  after (byte-identical to the Task 5 baseline; the `# agentic-scripts` entry untouched).
- **Task 2 check 1 (config loads):** PASS — printed `['noop', 'mail-keeper', 'oc-todo']`;
  `has roadmap_prompts: False`.
- **Task 2 check 3 (`bash -n scripts/setup.sh`):** PASS.
- **Pre-commit early signal (touched files, mid-task):** PASS — 47/47 on
  `tests/test_config.py tests/test_scheduler.py tests/smoke/` before the README step.
- **Live-cron interleaving (09:30:01Z fire, mid-edit):** clean — `overall: skipped`, 0 ERROR
  (see Interleaving note).

## Acceptance Verification

| # | Criterion (verbatim) | Result | Notes |
|---|---|---|---|
| 1.1 | "git status shows exactly those deletions staged; no other path staged." | PASS | `git status --short` after the 8 `git rm` calls: exactly `D autonomous_task_overview/README.md`, `D autonomous_task_overview/plans.md`, `D scripts/bootstrap_task_overview.sh`, `D src/agentic_scripts/workflows/roadmap_dev.py`, `D tests/smoke/test_smoke_roadmap_dev.py`, `D tests/test_roadmap_dev.py`, `D tests/test_roadmap_dev_pipeline.py`, `D tests/test_roadmap_dev_scan.py` — no other staged path. |
| 2.1 | "uv run python -c "from pathlib import Path; from agentic_scripts.config import load_config; c = load_config(Path('config/workflows.yaml')); print([w.name for w in c.workflows])" prints ['noop', 'mail-keeper', 'oc-todo'] and not hasattr(c, 'roadmap_prompts') is true." | PASS | Command printed `['noop', 'mail-keeper', 'oc-todo']`; `has roadmap_prompts: False` (= `not hasattr` is true). |
| 2.2 | "grep -rn "roadmap_prompts\|RoadmapPrompts" src/agentic_scripts/" → only the docstring MENTIONS in agent.py/git.py/sessions.py may remain (comments); zero in config.py." | PASS | Zero matches anywhere in `src/agentic_scripts/` (grep exit 1) after clearing the stale gitignored `__pycache__` of the deleted module. The permitted category is "may remain" — strictly better holds: even `roadmap-dev` docstring MENTIONS in agent.py/git.py/sessions.py stay (comments, per spec "What stays"), and `config.py`'s only remaining "roadmap" string is the pre-existing `admin (roadmap) repo` docstring for the surviving `admin_repo` field (same wording as `workflows/base.py`). |
| 2.3 | "bash -n scripts/setup.sh passes." | PASS | Exit 0. Final step numbering: 1 uv, 2 Venv sync, 3 Env vars, 4 Admin repo, 5 Registered-workflow agents, 6 Runtime dirs, 7 Timer, 8 Summary; header no longer mentions the preflight. |
| 3.1 | "grep -rln "roadmap" tests/" → no file matches (case-insensitive roadmap-dev and roadmap_prompts; a bare comment mentioning the move is acceptable ONLY in a docstring that says "moved to autonomous_task_overview")." | PASS | `grep -rln "roadmap" tests/` → no file matches (exit 1), including after the final test run regenerated `__pycache__`. Stronger than the criterion: zero mentions at all — no exception was needed. |
| 3.2 | "Idle-gate coverage still present (grep for idle in test_scheduler.py shows the re-targeted tests)." | PASS | `grep -c idle tests/test_scheduler.py` = 52. The re-targeted test `test_only_idle_entry_quiet_closed_still_runs` (synthetic `idle_entry`, `gate: idle`, noop module, `agent: null` — drives `--only` + 1st-idle-poll + `gate_open=False` + `overall: ok` + `idle_gate_last_ok`/`gate_last_ok` state assertions through `run()`) is present, and the 3 pre-existing probe tests (`test_gate_closed_idle_workflow_runs_gate_open_false`, `test_gate_closed_idle_gate_open_runs_gate_open_true`, `test_forced_run_all_run_gate_open_no_gate_state`) — which drive `evaluate_idle_gate` through `run()` via their `idle_probe` entry — are byte-identical. Plus `tests/test_gate.py`'s direct `evaluate_idle_gate` unit coverage (untouched). |
| 4.1 | "grep -in "roadmap" README.md returns only the pointer sentence(s) naming the new home." | PASS | Exactly one line matches: `300:The \`roadmap-dev\` workflow (unattended plan-execution engine) has moved out of this repo — its single home is now the \`y2d2/autonomous_task_overview\` repository (engine package, \`WORKFLOW.md\`, \`VARIABLES.md\`, live \`plans.md\`). See that repo's README.` (under the new heading `## Unattended plan execution (moved)`). |
| 4.2 | "The README's remaining workflow descriptions (mail-keeper, oc-todo) are intact and consistent with the trimmed config." | PASS | `## Mail-keeper workflow` (line 134) and `## OC-todo workflow` (line 213) sections untouched; their config tables (`MAIL_*` env vars; `oc_todo.*`) match the surviving config sections; the setup-steps list now matches `setup.sh`'s actual steps 1–6; workflows list reads noop/mail-keeper/oc-todo (the triage-context line now says "the admin vault" generically — the vault name itself is the config's surviving `admin_repo` value, which the Mail-keeper section already references generically). |
| 5.1 | "Suite 100% green; CLI ok; ruff clean; crontab unchanged." | PASS | Suite 237/237 (0 failed); `agentic-scripts run --help` exit 0; `ruff check .` "All checks passed!"; crontab md5 `cfb0988abb2ccee6dc0a3a628e485caf` = the dispatch baseline (byte-identical, `# agentic-scripts` entry still present). |
| 5.2 | "Commit landed + pushed on feature/roadmap-dev-workflow; git show --stat HEAD lists exactly the intended paths (deletions + modifications) — no stray files, no plans files, no planning/ files." | PASS | Commit landed by message: `OC: Remove roadmap-dev workflow — moved to y2d2/autonomous_task_overview (module, config, preflight, bootstrap, staging dir, tests, README)`; pushed `2da8d5b..80e0820 feature/roadmap-dev-workflow -> feature/roadmap-dev-workflow`. `git show --stat HEAD`: **19 files changed, 69 insertions(+), 8514 deletions(-)** — exactly the 8 deletions + 11 modifications listed in the Files table; no stray files, no `plans.md`-family content (the `plans.md` line IS the staged-dir deletion `autonomous_task_overview/plans.md | 4 -`), no `planning/` paths. |
| 5.3 | "git status after push: clean except the pre-existing untracked planning/mail-keeper-pruning/ files." | PASS (superset holds — see note) | `git status -sb`: `## feature/roadmap-dev-workflow...origin/feature/roadmap-dev-workflow` (in sync); no staged or modified tracked files remain. Untracked files: exactly the **17 pre-existing** `planning/` files — the 3 `planning/mail-keeper-pruning/` result reports the criterion names, plus the 14 `planning/autonomous-task-repo-move/` work-plan + result-report files that were already untracked at task start (verified against the task-start `git status` snapshot) — **plus this report itself** (`lightweight_dev_task_6_cleanup.md`, written AFTER the commit and deliberately left untracked, per the git-hygiene guardrail). Net: 18 untracked total, all under `planning/`, nothing else. The tracked `planning/autonomous-task-repo-move/autonomous-task-repo-move_plan.md` (from the earlier plan-add commit) is untouched. |

## Blockers

None. (Two judgment calls recorded for the orchestrator: (a) the plan's Task-3 file list named
4 test files, but the plan's own end-state rule ("zero roadmap references in tests/ AND 100%
green") forced 3 further single-line/docstring edits — `tests/conftest.py`,
`tests/smoke/conftest.py`, `tests/smoke/test_smoke_mail_keeper.py`; all are "test files you
touch" per the dispatch's staging instruction and are staged explicitly. (b)
`tests/smoke/test_smoke_oc_todo.py::test_smoke_oc_todo_gate_closed_noop` was re-pointed to
`overall: skipped` / no-WORKFLOW-lines because with no idle-gate workflow in the shipped
config the scheduler's gate-closed early return (`scheduler.py:646`) blanket-skips again — the
pre-roadmap-dev behavior; the test's old assertions (`overall: ok` + a per-workflow skip line)
were structurally impossible after the trim. Both decisions follow directly from the plan's
stated arbiter: "the suite is the arbiter — the end state is zero roadmap references in
tests/ AND 100% green.")

## Next Steps

- **Task 7 (cron install — valve open)** may proceed: install the NEW engine's timer in the
  overview repo (`bash scripts/setup.sh` in `/workspace/Python/autonomous_task_overview`, entry
  text already spec-locked in the Task 3 report Note 4). The old cron entry in THIS checkout
  stays as-is (it now drives only noop/mail-keeper/oc-todo — intended post-cutover behavior),
  and the new entry goes to the overview repo's own crontab install — the two never share an
  entry. Note the brief coexistence window: both engines are functional until Task 7; only the
  old one is timer-driven here, and the new one will be timer-driven there once Task 7 lands —
  per the Task 5 evidence the reconcile output is byte-identical, so overlapping runs render
  identically (no push on the second).
- **Task 8 (final verification)** as planned.
- Optional follow-ups (explicitly OUT of scope here, per plan): removing the dormant idle-gate
  machinery (`evaluate_idle_gate`, `sessions.py`, `WorkflowEntry.gate`) is a follow-up decision;
  the runtime `state/roadmap-dev.json` in this checkout (gitignored, migrated byte-identically
  in Task 5) may be removed by an operator at convenience — the old engine will never run it
  again from this tree.
