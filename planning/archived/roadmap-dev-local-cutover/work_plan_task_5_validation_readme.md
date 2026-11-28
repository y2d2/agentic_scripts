# Task Plan: Validation run + README restore

**Task:** #5    **Session:** roadmap-dev-local-cutover

## Objective

Prove the re-hosted roadmap-dev works end-to-end inside `/workspace/Python/agentic_scripts` with a safe validation run (scan + listing reconcile + local `plans.md` mirror, no plan execution), and restore the README documentation for the workflow.

## Context

- Done before this task: cron entry for `/workspace/Python/autonomous_task_overview` removed and its `state/roadmap-dev.json` copied into this repo (Task 1); module/config/yaml ported with `roadmap_prompts.listing_repo: y2d2/agentic_scripts` and `workflows.roadmap-dev: {enabled: true, agent: planner-enhanced, gate: idle}` (Task 2); `local_listing` mirror added (Task 3); full test suite green (Task 4). All on branch `feature/roadmap-dev-workflow`.
- This repo's cron entry (unchanged) runs `uv run agentic-scripts run` every 30 min. With `roadmap-dev` registered as `gate: idle`, the scheduler no longer early-returns on a closed quiet gate; mail-keeper/oc-todo/noop keep the quiet-window gate (22:00–08:00 + load<32) and simply skip outside it.
- **Safety property that makes the validation run non-destructive:** the idle gate opens only when the shared OpenCode service reports **0 active sessions** (2 consecutive polls). The user is actively using OpenCode during this validation, so `gate_open=False` → the workflow scans/reconciles but never spawns `planner-enhanced` executors. AT-OVERVIEW's 2026-11-26T19:00 run is the reference behavior: `GATE ... active_sessions=1 verdict=CLOSED` yet `roadmap-dev=ok(77 items, 11 actions, 0 errors)`.
- **Never pass `--force`** — it bypasses both gates and would start real (up to 8 h) plan executions.
- First real run fetches 9 GitHub repos into `sandbox/roadmap-dev/` (minutes). `y2d2/ARP_IMU` previously showed a one-off `Permission denied (publickey)`; if it fails again, record it as pre-existing access context, not a regression.
- The validation run pushes the listing to `y2d2/agentic_scripts` **main** from the sandbox clone (expected, desired). It does not touch the working tree except writing `plans.md`.
- README: this repo's roadmap-dev docs were deleted in `80e0820` (206 lines). Recover content from `git show 80e0820^:README.md` and the AT-OVERVIEW README @ `899ce44` (includes the mermaid pipeline diagram and per-plan-section listing docs).

## Tasks

### Task 1: Safe validation run
- **Files:** observes `logs/run-*.log`, `logs/last-run.txt`, `logs/cron.log`, `state/roadmap-dev.json`, `state/scheduler.json`, root `plans.md` (all created/updated by the run itself).
- **Do:** `cd /workspace/Python/agentic_scripts && uv run agentic-scripts run --only roadmap-dev` (no `--force`). Capture the run log. Then inspect artifacts.
- **Acceptance:**
  1. Exit code 0.
  2. Run log contains a `GATE`/idle-gate line with `verdict=CLOSED` (active sessions present) or an open verdict with **no** agent spawn — in practice CLOSED; and a `WORKFLOW roadmap-dev status=ok` line with non-zero items scanned (state had 77 items as of 2026-11-26).
  3. No line indicating a `planner-enhanced` agent spawn / job start.
  4. `/workspace/Python/agentic_scripts/plans.md` exists, contains per-plan sections (`### <plan>` headings + six-column rows) for un-archived plans across the allowed repos, and the log shows a mirror/push action.
  5. `state/roadmap-dev.json` mtime is now and content reflects the run; `state/scheduler.json`'s idle-gate key updated.

### Task 2: Cron coexistence check
- **Files:** none (read-only).
- **Do:** verify `crontab -l` still holds only the agentic-scripts entry; run `uv run agentic-scripts run` once without `--only` (full selection, still unforced) to confirm mail-keeper/oc-todo/noop skip cleanly outside the quiet window while roadmap-dev scans.
- **Acceptance:** exit 0; log shows quiet-gate workflows `status=skipped reason=quiet gate closed` (outside 22:00–08:00) and `roadmap-dev status=ok`; no errors.

### Task 3: README restore
- **Files:** `README.md` (modify).
- **Do:** re-add a roadmap-dev section covering: what it does (scan allowed repos for un-archived `planning/**/work_plan.md`, reconcile `plans.md`, drain-and-execute on idle), the `plans.md` control surface (per-plan sections, six-column rows, state cells, re-arming `failure`→`open` via commit+push to main), `gate: idle` semantics (zero OpenCode sessions, 2 polls), the `roadmap_prompts` config keys incl. `local_listing`, and the pipeline diagram (adapt AT's mermaid). Update any workflow-list/cron description to state roadmap-dev runs from this repo. Keep the rest of the README intact.
- **Acceptance:** `grep -n "roadmap-dev" README.md` hits the new section; markdown renders sanely (no broken mermaid fence); no stale claim that roadmap-dev lives in autonomous_task_overview.

### Task 4: Commit + push
- **Do:** commit `README.md` + root `plans.md` (the mirror output, now tracked): `OC: README roadmap-dev section + initial plans.md listing from validation run`; push. If the validation run's listing push to main created divergence the working branch can't cleanly include, commit the local `plans.md` on the current branch as-is and note it.
- **Acceptance:** commit pushed; `git status` shows no leftover unstaged source changes (untracked `planning/*` artifacts may remain).

## Out of Scope

- Waiting for an idle-gate night run or forcing an execution.
- Any AT-OVERVIEW repo changes; cron edits (done in Task 1).

## Notes

- If the run ends `status=error`, capture the error text verbatim in the result report; do not retry more than once after a trivial fix.
- `[Assumption]` GitHub SSH access from this box is healthy for 8/9 repos (proven by AT's 2026-11-26 run).
