# Task Plan: tests for 3-col details

**Purpose:** Update all `plans.md` details-table test fixtures to the new 3-column checklist layout and add behavior tests for the checkmark rules; full suite green.

## Objective
In `/workspace/Python/agentic_scripts/tests`, Task 2 changed the details-table bytes and `task_titles` arity (`tuple[tuple[str, str, bool], ...]`). Fix every affected fixture/expectation, add the new-behavior tests below, and bring the full pytest suite to green.

## Context
New locked contract (rendered inside each per-plan section, one blank line before it, present only when the plan has a real goal or ≥1 task):
```markdown
| # | details | ✓ |
|---|---------|---|
| G | <goal or —> | ☑ if state == "success" else ☐ |
| 1 | <title> | ☑ if done else ☐ |
```
Constants: `_DETAILS_HEADER = "| # | details | ✓ |"`, `_DETAILS_SEPARATOR = "|---|---------|---|"`. Done flags: a plan folder with `lightweight_dev_task_1_engine_scaffold.md` in `PlanEntry.file_contents` ⇒ task `1` is ☑; hyphen form `lightweight-dev_task_3b_x.md` ⇒ `3b`; `task_done_labels` is exported from `agentic_scripts.workflows.roadmap_dev`. Parser invariants to keep proving: new 3-cell rows never parse as rows; the historical 1-cell (`| details |`, old body line) and the older six-cell em-dash detail lines remain skipped. Entry points under test: `render_listing`, `parse_listing`, `_plan_block`, `discover_plans`, `reconcile`. Grep for: `task_titles`, `details`, `DETAILS_HEADER`, `**Goal:**`, `<br>`, `☐`, and 2-tuple constructions in the test files. Likely affected: `tests/test_roadmap_dev.py` (byte fixtures ~lines 690–990 + `ListingRow`/`Plan` kwargs), `tests/test_roadmap_dev_scan.py` (`DETAILS_HEADER` const ~line 64, real-plan expectations), `tests/test_roadmap_dev_pipeline.py`, `tests/test_roadmap_dev_listing_mirror.py`, `tests/smoke/test_smoke_roadmap_dev.py` (only if fixtures carry goal/tasks).

## Tasks

### Task 1: Update fixtures + add behavior tests
- **Files:** `tests/test_roadmap_dev.py`, `tests/test_roadmap_dev_scan.py`, `tests/test_roadmap_dev_pipeline.py`, `tests/test_roadmap_dev_listing_mirror.py`, `tests/smoke/test_smoke_roadmap_dev.py` (modify only what the change actually breaks, plus new tests)
- **Do:**
  1. Convert all `task_titles=(("1","t"), ...)` fixtures to 3-tuples; pick done flags matching each test's intent.
  2. Update details-table byte expectations to the locked contract (headers, G row, task rows, ☐/☑, blank-line placement); `md.count("| details |")`-style assertions → count the new header or `_DETAILS_HEADER`.
  3. ADD tests:
     - `discover_plans`: entry whose `file_contents` include `lightweight_dev_task_2_runner.md` → its plan's `task_titles` has `("2", <title>, True)` and other tasks False; hyphen-form file marks `3b`; folder-relative paths work.
     - render: task ☑/☐ per flag; G ☑ iff `state="success"`, ☐ for `open`/`pending`/`failure`/`review`; goal absent → `| G | — | ☐ |`; pipe in a task title escaped `\|`; no goal+no tasks → no details table (unchanged).
     - round-trip: render (with details incl. a ☑ row) → `parse_listing` → exactly the six-cell data rows; re-render byte-identical (no-op stability).
     - backward compat: a listing containing OLD details lines (`| details |`, `|---------|`, a 1-cell body line) and an older 6-cell em-dash detail row still parses the same row set as before (skip contract).
  4. Keep docstrings/comments truthful in touched tests.
- **Notes:** Do not weaken existing assertions to pass; update them to the new contract. If a smoke/pipeline fixture's expected bytes are generated rather than hand-written, regenerate via a one-off snippet and diff-check by eye against the locked contract.
- **Acceptance:**
  1. `pytest -q` full suite green (including Task-1's `task_done_labels` tests).
  2. `ruff check src tests` clean.
  3. New behavior tests exist and fail when the corresponding production line is reverted (sanity-check at least the G-☑-on-success and task-done tests via temporary local edit, then restore).
  4. Diff touches only the listed test files; commit `OC: tests for 3-col details checklist layout` + push.

## Out of Scope
- `src/` changes (if you find a genuine source bug, stop and report it as a blocker instead of editing source), README, `plans.md`.

## Notes
- The working tree may hold unrelated untracked files (`planning/**`) — never `git add -A`; stage only your test files.
