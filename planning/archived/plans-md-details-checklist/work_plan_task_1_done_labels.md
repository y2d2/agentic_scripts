# Task Plan: task_done_labels helper

**Purpose:** Add the pure completion-label extractor `task_done_labels` to `roadmap_dev.py` + unit tests, without changing any existing behavior.

## Objective
In `/workspace/Python/agentic_scripts`, add a small pure function that, given the plan folder's file names, returns the set of task labels for which a lightweight-dev result report exists (`lightweight[-_]dev_task_<num><letter>_<desc>.md`). This feeds the new 3-column checklist details table in a later task. End state: helper + tests exist and the full suite is green.

## Context
`src/agentic_scripts/workflows/roadmap_dev.py` generates `plans.md`. Its "Listing details-table extractors" section (~lines 334–368) already defines sibling regexes (`_TASK_FILE_NAME_RE` etc.) anchored on the basename with `(?:^|/)`. Plan folders contain `work_plan.md`, `work_plan_task_<N>_<desc>.md` task specs, and `lightweight_dev_task_<N>_<desc>.md` result reports (e.g. `lightweight_dev_task_1_engine_scaffold.md`); the docs elsewhere also show a hyphenated form `lightweight-dev_task_*.md`, so accept both. Labels follow the plan's own numbering: digits plus optional single lowercase letter (`1`, `3b`). Function style: match the file's existing conventions — `from __future__ import annotations`, full Google-style docstring with Purpose/Args/Returns/Note, never raises on empty/None-ish input, `Sequence` is already imported from `collections.abc`.

## Tasks

### Task 1: Add `_TASK_REPORT_NAME_RE` + `task_done_labels` + unit tests
- **Files:** `src/agentic_scripts/workflows/roadmap_dev.py` (modify); `tests/test_roadmap_dev.py` (modify — append a new test class/section near the existing extractor tests)
- **Do:**
  1. In the extractors section, add exactly:
     `_TASK_REPORT_NAME_RE = re.compile(r"(?:^|/)lightweight[-_]dev_task_(\d+)([a-z]?)_[^/]*\.md$")`
  2. Add a pure public function:
     `def task_done_labels(file_names: Sequence[str]) -> frozenset[str]:` — for each name, `match = _TASK_REPORT_NAME_RE.search(name)`; collect `f"{num}{letter}"` (empty letter allowed). Defensive: `""`/None-ish/empty sequence → `frozenset()`. Never raises.
  3. Unit tests (pytest, match the file's existing test style):
     - `lightweight_dev_task_1_engine_scaffold.md` → `{"1"}`
     - `lightweight-dev_task_3b_fix_ci.md` → `{"3b"}`
     - folder-relative `sub/lightweight_dev_task_2_runner.md` → `{"2"}` (basename anchoring)
     - mixed folder with reports 1, 2, 5 and specs only → exactly `{"1","2","5"}`
     - non-matches yield `frozenset()`: `work_plan_task_1_x.md`, `lightweight_dev_task_1.md` (no `_<desc>_` segment), `not-lightweight_dev_task_2_x.md`, `lightweight_dev_tasks_1_x.md` (plural), case-different `Lightweight_Dev_Task_1_x.md`
     - empty input → `frozenset()`
- **Notes:** Do NOT wire the helper into `discover_plans`, `Plan`, or `_plan_block` in this task — pure addition only; the suite must stay fully green because nothing existing changes.
- **Acceptance:**
  1. `task_done_labels` importable from `agentic_scripts.workflows.roadmap_dev` and returns the exact sets listed above (new tests pass).
  2. `ruff check src tests` clean (or repo's configured lint command).
  3. `pytest -q` full suite green (pre-existing suite + new tests).
  4. `git diff` shows no changes outside the two files; commit with `OC:` prefix and push to the current branch.

## Out of Scope
- Any renderer/parser/`Plan`/`ListingRow`/`discover_plans` change (Task 2 owns those).
- Any change to result-report generation or the sub-agent communication format.

## Notes
- [Assumption] Report-file existence means "task completed"; report content is intentionally NOT parsed (verified: reports carry no stable status line — only one file has a one-off inline "Status: NOT EXECUTED").
