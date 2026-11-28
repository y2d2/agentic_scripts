# Task Plan: Docs sync in autonomous_task_overview (README / WORKFLOW.md / VARIABLES.md)

**Task:** #3    **Plan:** `autonomous-task-rehome`    **Repo:** `/workspace/Python/autonomous_task_overview` (branch `feature/rehome-final`, after Task 2)

## Objective

Update the three operator docs so they describe the re-homed engine as it now stands: this
repo is the permanent home; the listing publishes to this repo's own `plans.md` (`main`) with
a root mirror via `local_listing`; the renderer emits per-plan sections + 3-col checklist
tables; completion labels come from report files via `task_done_labels`.

## Steps

1. `README.md`: state permanence (single home of autonomous-task execution; mail-keeper and
   oc-todo live in `agentic_scripts`), keep "Running the engine" section, add one paragraph on
   the listing lifecycle (scan → render → push own `main` + root mirror).
2. `WORKFLOW.md`: update the pipeline split-table rows touched by the re-home (listing
   render/push steps, `local_listing` mirror step) — same table format; verify each cited
   symbol exists via grep.
3. `VARIABLES.md`: add/adjust entries: `local_listing` (default `plans.md`, `null` disables);
   `listing_repo` now = `y2d2/autonomous_task_overview`; `allowed_repos` count 9 (now includes
   `y2d2/agentic_scripts`). Values re-confirmed against `config/workflows.yaml` before writing.
4. Commit explicit paths: `OC: Docs — re-home sync (self-listing, local_listing, checklist renderer)`. Push.

## Acceptance criteria

| # | Check | Pass condition |
|---|---|---|
| 1 | Accuracy | every config key/symbol cited in the three docs greps to real code/config; no doc claims roadmap-dev still runs in agentic_scripts |
| 2 | Completeness | all three files updated; `local_listing` documented with default + disable semantics |
| 3 | Git | one commit, pushed, only doc files staged; no src/tests touched |

## Out of scope

No code/config changes. Do not touch `plans.md`.
