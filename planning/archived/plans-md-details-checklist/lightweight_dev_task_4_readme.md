# lightweight-dev Output — Task: README listing sample

**Task:** #4    **Session:** ses_dde297a79ffe6178f213UROu16    **Date:** 2026-11-28

## Summary

Updated the README "The listing" section to document the new 3-column details checklist.
The intro sentence now describes a three-column `details` checklist (columns
`# | details | ✓`, `G` goal row + one row per task with the plan's own labels, skipped
when the plan has neither goal nor tasks); the fenced sample replaces the old single-cell
`| details |` block with the locked 3-column block; the paragraph after the columns table
keeps the workflow-owned/edits-pointless note (now explicitly covering the ✓ column) and
adds the ☑ rules: task ☑ = `lightweight_dev_task_<label>_*.md` result report present in
the plan folder, `G` ☑ = plan state `success`, goal/task text still comes from the plan.
Verified against the code first: `_DETAILS_HEADER` / `_DETAILS_SEPARATOR` in
`src/agentic_scripts/workflows/roadmap_dev.py` (lines 124/129) match the spec bytes
exactly, so no code-vs-spec divergence to reconcile.

## Files

| File | Action | Why |
|---|---|---|
| `README.md` | modify | "The listing" section: intro sentence, fenced sample, and ☑-rules paragraph |

## Build / Tests

- README lint (structural): PASS — no `| details |` single-column header or `<br>` remains anywhere in the section; sample uses the locked bytes; parenthesization of the intro sentence balanced (checked programmatically); no trailing whitespace introduced.
- Sample-vs-code cross-check: PASS — sample rows (`| G | … | ☐ |`, `| 1 | … | ☑ |`) match the `_plan_block` renderer's output shape and `roadmap_dev.py` constants byte-for-byte on header/separator.
- Diff containment: PASS — `git diff` shows only `README.md` changed by this task (hunks confined to the listing section, ~lines 444–484); the pre-existing `plans.md` modification was left unstaged and untouched.
- Commit + push: PASS — commit message `OC: README — 3-col details checklist sample` on `feature/roadmap-dev-workflow`, pushed to origin (see git log).

## Acceptance Verification

| # | Criterion (verbatim) | Result | Notes |
|---|---|---|---|
| 1. | "No `| details |` single-column sample remains in README.md; the new sample matches the locked bytes (`| # | details | ✓ |` / `|---|---------|---|`)." | PASS | Grep confirms zero `^| details |$` and zero `<br>` in README.md; the locked header/separator lines are present and identical to the code constants. |
| 2. | "The section explains all three columns and both ☑ rules; a reader who knows nothing of the internals can predict what appears when a task's report file is committed." | PASS | Intro explains `#` (`G` + task labels), `details` (goal/task text), `✓`; new **Check marks** sentences state task ☑ ⇔ `lightweight_dev_task_<label>_*.md` report present (committed by the dev agent on completion), `G` ☑ ⇔ state `success`, and that the next scan rewrites it — so committing the report flips the row to ☑ at the next scan. |
| 3. | "Diff touches only `README.md` and only within the listing section; commit `OC: README — 3-col details checklist sample` + push." | PASS | Only README.md was staged/committed (never `git add -A`); all hunks lie inside the listing section; commit message exact; pushed to `origin/feature/roadmap-dev-workflow`. |

## Blockers

None.

## Next Steps

- Orchestrator: when the parallel implementation task lands, no README rework is expected — the docs mirror the merged `_DETAILS_HEADER`/`_DETAILS_SEPARATOR` constants, which already matched the spec.
- The result file itself lives in untracked `planning/plans-md-details-checklist/`; per dispatch rules only `README.md` was staged, so the planning folder is left for the orchestrator to handle.
