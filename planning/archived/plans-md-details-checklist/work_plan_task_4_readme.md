# Task Plan: README listing sample

**Purpose:** Update the README "The listing" section so its sample and prose show the new 3-column checklist details table.

## Objective
In `/workspace/Python/agentic_scripts/README.md`, the "The listing" section (~lines 441–476) documents and shows the OLD single-column details table (`| details |` with a `<br>`-crammed cell). Replace the sample and the describing sentence with the new locked contract, and state how the ☑ marks are computed.

## Context
The layout change is fully specified (implementation runs in parallel — this task is spec-locked, do not wait for code). New details table rendered under each plan's six-column table:
```markdown
| # | details | ✓ |
|---|---------|---|
| G | <goal> | ☐ |
| 1 | <task title> | ☐ |
```
Semantics to document: column 1 — `G` is the goal row, then the plan's own task labels (`1`, `3b`, …); column 2 — goal/task description (workflow-owned, from the plan); column 3 — workflow-computed checkmark: a task is ☑ when the plan folder contains a `lightweight_dev_task_<label>_*.md` result report (the report the dev agent commits when it completes the task), ☐ otherwise; the `G` row is ☑ when the plan's state is `success`. The table is skipped entirely when the plan has neither goal nor tasks. The "workflow-owned: editing it in `plans.md` is pointless — the next scan rewrites it" note must stay and cover the checkmarks too.

## Tasks

### Task 1: README "The listing" section update
- **Files:** `README.md` (modify only this file, only the listing section)
- **Do:**
  1. In the intro sentence: "a workflow-rendered single-column `details` table (goal + one `<br>`-separated task line per task, …)" → describe the multi-row 3-column `details` table (goal row `G` + one row per task; columns `# | details | ✓`).
  2. In the fenced ```markdown sample (~lines 450–461): replace the `| details |` block with the new 3-column block, e.g.
     ```
     | # | details | ✓ |
     |---|---------|---|
     | G | Build the DMP, table-first. | ☐ |
     | 1 | Skeleton & front matter | ☑ |
     | 2 | Master table | ☐ |
     ```
     Keep the sample's other lines (repo/branch/plan heading, six-column table) unchanged.
  3. In the paragraph after the columns table (~472–476): keep "workflow-owned / edits pointless" and add one short sentence: task ☑ = `lightweight_dev_task_<label>_*.md` result report present in the plan folder; `G` ☑ = plan state `success`; goal/task text still comes from the plan itself (edit the plan to change what shows).
- **Acceptance:**
  1. No `| details |` single-column sample remains in README.md; the new sample matches the locked bytes (`| # | details | ✓ |` / `|---|---------|---|`).
  2. The section explains all three columns and both ☑ rules; a reader who knows nothing of the internals can predict what appears when a task's report file is committed.
  3. Diff touches only `README.md` and only within the listing section; commit `OC: README — 3-col details checklist sample` + push.

## Out of Scope
- Any other README section, `plans.md`, source or tests.

## Notes
- If the merged source constants somehow differ from this spec, the CODE is the truth — mirror the source's `_DETAILS_HEADER`/`_DETAILS_SEPARATOR` values (grep `roadmap_dev.py`) instead of the spec bytes.
