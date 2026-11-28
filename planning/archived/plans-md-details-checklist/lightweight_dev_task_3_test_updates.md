# lightweight-dev Output — Task: tests for 3-col details

**Task:** #3    **Session:** ses_dde297a7affeSbuYlQ81r0v66j    **Date:** 2026-11-28

## Summary

Updated every `plans.md` details-table test fixture in the roadmap suite to the locked
3-column checklist layout (`| # | details | ✓ |` / `|---|---------|---|` / `G` goal row /
one row per task, ☑/☐ marks) and added the new-behavior coverage, bringing the full
pytest suite from the 6 expected failures to **355 passed** (347 baseline + 8 new cases).
No `src/` file was touched.

`tests/test_roadmap_dev.py`:

- **Fixtures to 3-tuples:** the `_plan` helper's `task_titles` annotation is now
  `tuple[tuple[str, str, bool], ...]` (docstring documents the done flag); all five
  broken fixtures (`stamps_goal_and_tasks`, `skips_per_plan_sections`,
  `emits_per_plan_sections`, `pipes_round_trip…`, `listing_pipeline_fixed_point`) and
  the reconcile stamping fixture (`test_reconcile_discovers_new_plan_empty_and_nonempty_table`)
  carry `(label, title, done)` triples with done flags matching each test's intent.
- **Byte fixtures:** exact-render expectations rewritten to the locked contract (blank
  line + header + separator + G row + task rows, ☑/☐ per flag/`state`, escaped `\|`
  cells, one-blank-line placement, `heads[1] == heads[0] + 11` in the fixed-point test);
  the `md.count("| details |")`-style assertions now count the imported
  `_DETAILS_HEADER` / `_DETAILS_SEPARATOR` constants.
- **New behavior tests (8 cases):**
  - `test_discover_plans_stamps_task_done_flags_from_reports` — folder report
    `lightweight_dev_task_2_runner.md` ⇒ `("2", …, True)` with the other tasks False;
    the hyphen spelling `lightweight-dev_task_3b_fix.md` under a folder-relative path
    marks `3b`.
  - `test_render_listing_goal_mark_mirrors_state` (parametrized ×5) — G row ☑ for
    `state="success"`, ☐ for `open`/`pending`/`failure`/`review`.
  - `test_render_listing_goal_mark_mirrors_state_task_flags_unchanged` — the state
    changes only the G row; task ☑/☐ keep following their done flags.
  - `test_render_parse_round_trip_with_checkmarks_is_byte_stable` — render (details
    incl. ☑ rows) → `parse_listing` returns exactly the six-cell data rows → re-stamp
    from the same scan data → re-render byte-identical (fixed point, incl. a
    pipe-containing title).
  - Plus contract points folded into the existing render/parse tests: absent goal →
    `| G | — | ☐ |`; goal-only ⇒ no task rows (checked by what follows the G row);
    pipe in a task title escaped `\|`; row with no goal + no tasks → no checklist;
    the **backward-compat fixture extended** with the old 1-cell details lines
    (`| details |`, `|---------|`, the one-cell `**Goal:** …<br>…` body line) alongside
    the older 6-cell em-dash detail row — the parsed row set is unchanged.
- Docstrings/comments kept truthful throughout ("details table" → "details checklist",
  one-cell wording → three-cell, etc.); no existing assertion was weakened — each was
  restated against the new contract.

`tests/test_roadmap_dev_scan.py`: the `DETAILS_HEADER` / `DETAILS_SEP` / `DETAILS_ORBIT`
constants now encode the 3-col contract (`| G | — | ☐ |` + `| 1 | x | ☐ |` for orbit-sim:
tier-3 task `("1", "x")`, no result report → ☐; no Purpose/Goal marker → em-dash G row, ☐
while open), so `EXPECTED_RUN1` matches the re-rendered listing; the comment above them
was rewritten to describe the new layout. `test_roadmap_dev_pipeline.py`,
`test_roadmap_dev_listing_mirror.py` and `tests/smoke/test_smoke_roadmap_dev.py` needed
no changes (their fixtures carry no goal/tasks and none asserts details bytes).

Committed with message `OC: tests for 3-col details checklist layout` to
`feature/roadmap-dev-workflow` and pushed (only the two test files staged; the
pre-existing modified `plans.md` and untracked `planning/**` left untouched).

## Files

| File | Action | Why |
|---|---|---|
| `tests/test_roadmap_dev.py` | modify | All 3-tuple fixture conversions, new 3-col byte fixtures, `_DETAILS_HEADER`-based counts, backward-compat old-layout lines, and the 8 new behavior-test cases |
| `tests/test_roadmap_dev_scan.py` | modify | `DETAILS_HEADER`/`DETAILS_SEP`/`DETAILS_ORBIT` constants (and `EXPECTED_RUN1` via them) to the new contract + comment truthfulness |

## Build / Tests

- `uv run pytest -q` (full suite): **PASS** — 355 passed (was 6 failed / 341 passed; all
  6 expected failures fixed, +8 new cases, zero regressions).
- `uv run ruff check src tests`: **PASS** — "All checks passed!"
- Behavior-revert sanity (criterion 3, each edit temporary, `src/` restored to a clean
  diff after every step — verified via `git diff --stat src/` empty):
  - G-mark line reverted to always-☐ → `test_render_listing_goal_mark_mirrors_state[success-☑]`
    and `…_task_flags_unchanged` fail.
  - Task-mark line reverted to always-☐ → `test_render_listing_emits_per_plan_sections`,
    `…_task_flags_unchanged`, `test_render_parse_round_trip_with_checkmarks_is_byte_stable`
    and `test_listing_pipeline_fixed_point` fail.
  - `discover_plans` done-stamp reverted to `False` → `test_discover_plans_stamps_task_done_flags_from_reports`
    fails.

## Acceptance Verification

| # | Criterion (verbatim) | Result | Notes |
|---|---|---|---|
| 1. | "`pytest -q` full suite green (including Task-1's `task_done_labels` tests)." | PASS | `355 passed` — the 6 Task-2 expected failures are fixed, Task-1's three `task_done_labels` tests pass, no new failures. |
| 2. | "`ruff check src tests` clean." | PASS | "All checks passed!" (after the isort-ordered `_DETAILS_*` import placement). |
| 3. | "New behavior tests exist and fail when the corresponding production line is reverted (sanity-check at least the G-☑-on-success and task-done tests via temporary local edit, then restore)." | PASS | Three separate temporary reverts (G-mark, task-mark, discover done-stamp) each made the matching new tests fail, see Build/Tests; `src/` restored after each (empty `git diff src/`). |
| 4. | "Diff touches only the listed test files; commit `OC: tests for 3-col details checklist layout` + push." | PASS | The commit contains exactly 2 files (`tests/test_roadmap_dev.py`, `tests/test_roadmap_dev_scan.py`; 214+/62− — the other three listed files needed no edits and are untouched); pushed to `feature/roadmap-dev-workflow`. `plans.md` WIP and untracked `planning/**` remain unstaged/untouched. |

## Blockers

None.

Plan-vs-reality notes (non-blocking):

- The plan's "Likely affected" list included `test_roadmap_dev_pipeline.py`,
  `test_roadmap_dev_listing_mirror.py` and `tests/smoke/test_smoke_roadmap_dev.py`;
  none of them constructs `task_titles`/goal fixtures or asserts details bytes, so per
  the plan's own "modify only what the change actually breaks" instruction they were left
  untouched (their full-suite runs are green).
- `test_render_listing_goal_mark_mirrors_state_task_flags_unchanged` compares the task
  rows (not the whole render) between the `open` and `success` renders, because the six-cell
  data row legitimately differs in its state cell — the G-row-only mirroring is still
  asserted exactly.

## Next Steps

- **Task 4 (README):** already landed ahead of this task (a README commit for the 3-col
  sample sits between Task 2 and this one on the branch) — the orchestrator may confirm
  it closes Task 4.
- Live `plans.md` re-renders into the new layout on the next roadmap-dev reconcile run
  (its details sections are workflow-owned and re-stamped each pass).
