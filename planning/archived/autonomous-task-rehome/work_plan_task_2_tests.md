# Task Plan: Port + adapt roadmap-dev test suite into autonomous_task_overview

**Task:** #2    **Plan:** `autonomous-task-rehome`    **Repo:** `/workspace/Python/autonomous_task_overview` (branch `feature/rehome-final`, after Task 1)

## Objective

Replace the overview repo's stale (Nov-24) roadmap-dev test suite with the CURRENT evolved
suite from `agentic_scripts`, adapted to the single-workflow `autonomous_task.runner`, and get
the FULL suite green.

## Context

- Source files (read-only, `agentic_scripts` HEAD): `tests/test_roadmap_dev.py`,
  `tests/test_roadmap_dev_scan.py`, `tests/test_roadmap_dev_pipeline.py`,
  `tests/test_roadmap_dev_listing_mirror.py`, `tests/smoke/test_smoke_roadmap_dev.py`.
  Also read `tests/conftest.py` + `tests/smoke/conftest.py` in BOTH repos for fixture deltas.
- Proven adaptation recipe from the first migration: `planning/autonomous-task-repo-move/
  lightweight_dev_task_2_test_suite.md` (pure files = mechanical `s/agentic_scripts/
  autonomous_task/g` with empty freeze-diff; smoke suite = prescribed adaptations: drop
  cross-workflow skip-line assertions — noop/mail-keeper/oc-todo don't exist here — keep
  `_git_env`, drop `load=` kwargs, patch `autonomous_task.runner.read_active_sessions` in the
  autouse probe fixture).
- The `local_listing` mirror test (`test_roadmap_dev_listing_mirror.py`) is NEW: port with the
  mechanical rewrite; its fixtures use tmp paths (verify no hardcoded `/workspace/Python/
  agentic_scripts` — rewrite such paths to the target repo root if present).
- Overview's `runner.py` has no `--only` and no mail-keeper: adapt the smoke tests to the
  single-workflow surface (they already existed in overview pre-revert; diff against them).

## Steps

1. Pure files: rewrite + replace the 3 core test files (mechanical rename), run the same
   freeze-diff check as Task 1 → must be empty (or list the exact delta lines + reason).
2. Port `test_roadmap_dev_listing_mirror.py` (mechanical rename; fix any absolute paths).
3. Smoke suite: replace `tests/smoke/test_smoke_roadmap_dev.py`; adapt per the recipe above.
4. Update `tests/conftest.py` / `tests/smoke/conftest.py` in the target ONLY where fixtures
   require it (roadmap_prompts hermetic lines, autouse patches). Keep the shipped-config-based
   `base_config` pattern.
5. `uv run pytest tests/ -q` → FULL suite green (old suite was green at Nov 24; the new suite
   must be green with zero skips beyond design-intended ones).
6. `uv run ruff check tests` clean on changed files.
7. Commit explicit paths: `OC: Port evolved roadmap-dev test suite (incl. listing-mirror) from agentic_scripts`. Push.

## Acceptance criteria

| # | Check | Pass condition |
|---|---|---|
| 1 | Freeze diffs | empty (or per-file justified delta list ≤ docstring/comment lines) |
| 2 | Suite | `uv run pytest tests/ -q` exit 0, ALL green |
| 3 | Mirror test | `test_roadmap_dev_listing_mirror.py` collected + passing |
| 4 | Lint | ruff clean on changed test files |
| 5 | Git | one commit on `feature/rehome-final`, pushed, clean status |

## Out of scope

No src/ changes. If a src bug blocks a ported test, STOP and report (do not fix engine code).
