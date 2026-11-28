# lightweight-dev Output — Task: task_done_labels helper

**Task:** #1
**Source Agent:** lightweight-dev
**Date:** 2026-11-28
**Branch:** `feature/roadmap-dev-workflow`

## Summary

Added the pure completion-label extractor to `roadmap_dev.py` exactly as planned, with unit tests, and changed nothing else:

- **`_TASK_REPORT_NAME_RE`** — added verbatim (`re.compile(r"(?:^|/)lightweight[-_]dev_task_(\d+)([a-z]?)_[^/]*\.md$")`) in the "Listing details-table extractors" section, right after `_TASK_FILE_NAME_RE`, with a `#:` comment matching the section's convention (basename-anchored; accepts both the underscore and hyphenated spellings).
- **`task_done_labels(file_names: Sequence[str]) -> frozenset[str]`** — added at the end of the extractors section (after `extract_task_titles`, before `class Plan`). For each name it `search`es with `_TASK_REPORT_NAME_RE` and collects `f"{num}{letter}"` (empty letter allowed). Defensive: `None` / `""` / empty sequence → `frozenset()`; never raises. Full Google-style docstring (Purpose/Args/Returns/Note) per the file's conventions; note documents that report *content* is deliberately not parsed.
- **Tests** — appended a `task_done_labels` subsection in `tests/test_roadmap_dev.py` directly after the existing `extract_task_titles` extractor tests (Group A), in the file's existing flat test-function style, covering every case listed in the plan: underscore form → `{"1"}`, hyphenated form → `{"3b"}`, folder-relative basename anchoring → `{"2"}`, mixed folder (reports 1, 2, 5 among specs/notes) → exactly `{"1","2","5"}`, and the five non-matches (`work_plan_task_1_x.md`, `lightweight_dev_task_1.md` without the `_<desc>_` segment, `not-lightweight_dev_task_2_x.md`, plural `lightweight_dev_tasks_1_x.md`, case-different `Lightweight_Dev_Task_1_x.md`) plus empty/None-ish inputs → `frozenset()`.

Pure addition — `discover_plans`, `Plan`, `_plan_block` and every other existing code path are untouched, as required.

## Files

| File | Change |
|---|---|
| `src/agentic_scripts/workflows/roadmap_dev.py` | Modified: +`_TASK_REPORT_NAME_RE` (extractors section) +`task_done_labels` (37 lines) |
| `tests/test_roadmap_dev.py` | Modified: +`task_done_labels` import + 3 test functions under a section banner (45 lines) |

## Build / Tests

| Action | Command | Result |
|---|---|---|
| Lint | `uv run ruff check src tests` | PASS — "All checks passed!" |
| New tests | `uv run pytest -q tests/test_roadmap_dev.py -k task_done_labels` | PASS — 3 passed |
| Full suite | `uv run pytest -q` | PASS — **347 passed** in 74s (pre-existing suite + 3 new) |
| Direct import + behavior spot-check | `uv run python -c "…"` against all plan-listed inputs | PASS — exact sets confirmed independently of pytest |

## Acceptance Verification

| # | Criterion (verbatim) | Result | Evidence |
|---|---|---|---|
| 1 | "`task_done_labels` importable from `agentic_scripts.workflows.roadmap_dev` and returns the exact sets listed above (new tests pass)." | **PASS** | 3 new tests pass (`-k task_done_labels`); independent REPL import + equality checks over every listed case printed `DIRECT CHECKS OK`. |
| 2 | "`ruff check src tests` clean (or repo's configured lint command)." | **PASS** | `uv run ruff check src tests` → "All checks passed!" |
| 3 | "`pytest -q` full suite green (pre-existing suite + new tests)." | **PASS** | `uv run pytest -q` → 347 passed, 0 failed. |
| 4 | "`git diff` shows no changes outside the two files; commit with `OC:` prefix and push to the current branch." | **PASS** | The commit contains exactly the two files ("2 files changed, 82 insertions(+)"). Caveat: the worktree held pre-existing unrelated changes before this task started (`M plans.md`, untracked `planning/**`); those were deliberately left unstaged/untouched per dispatch rules. Pushed to `feature/roadmap-dev-workflow` (`f2a3798..` → new head, verified via `git push` output and `git status`). |

## Blockers

None.

## Next Steps

- Task 2 (per plan's ownership note): wire `task_done_labels` into `discover_plans` / `Plan` / `_plan_block` for the 3-column checklist details table — intentionally NOT done here (out of scope).
- The pre-existing uncommitted `plans.md` modification and untracked `planning/**` files remain in the worktree for whoever owns them.
