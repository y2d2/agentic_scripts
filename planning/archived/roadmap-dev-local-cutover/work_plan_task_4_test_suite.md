# Task Plan: Port roadmap-dev test suite green

**Task:** #4    **Session:** roadmap-dev-local-cutover

## Objective

Restore full test coverage for the re-hosted `roadmap-dev` workflow in `/workspace/Python/agentic_scripts` by porting the adapted test suite from the AT-OVERVIEW repo, plus new tests for the `local_listing` mirror, and get the entire suite + lint green.

## Context

- Already on branch `feature/roadmap-dev-workflow`: `roadmap_dev.py` ported (Task 2), `local_listing` + mirror added (Task 3). This repo's roadmap tests were deleted here in commit `80e0820`.
- **Test source:** `/workspace/Python/autonomous_task_overview` @ `899ce44` (branch `feature/listing-detail-row`): `tests/test_roadmap_dev.py`, `tests/test_roadmap_dev_scan.py`, `tests/test_roadmap_dev_pipeline.py`, `tests/smoke/test_smoke_roadmap_dev.py` — already adapted to the evolved per-plan-section `plans.md` renderer. Plus their fixture needs: compare `tests/conftest.py` and `tests/smoke/conftest.py` between the two repos and restore roadmap-related fixtures this repo dropped.
- Package rewrite for all ported files: `autonomous_task` → `agentic_scripts`.
- Config deltas this repo's suite must reflect: `roadmap_prompts.listing_repo: y2d2/agentic_scripts` (AT fixtures may hardcode `y2d2/autonomous_task_overview` as listing repo in expectations) and the new optional `local_listing` field (default `"plans.md"`, `null` disables).
- Smoke tests are hermetic by this repo's established pattern (`tests/smoke/conftest.py` fixture repos, `repo_urls` overrides, temp `state/`, `sandbox/`, `logs/` dirs) — the ported smoke file already follows it after rewrite; verify no test hits the network or real GitHub.
- Commit with `OC:` prefix, push; explicit paths only; untracked `planning/*` files untouched.

## Tasks

### Task 1: Port the four test files
- **Files:** `tests/test_roadmap_dev.py`, `tests/test_roadmap_dev_scan.py`, `tests/test_roadmap_dev_pipeline.py`, `tests/smoke/test_smoke_roadmap_dev.py` (create).
- **Do:** copy from AT @ `899ce44`; rewrite `autonomous_task` → `agentic_scripts`; keep assertions intact (they match the current renderer).
- **Acceptance:** after Task 3, all four run with zero failures.

### Task 2: Merge fixtures and adjacent test sections
- **Files:** `tests/conftest.py`, `tests/smoke/conftest.py` (modify as needed); `tests/test_config.py`, `tests/test_scheduler.py` (modify).
- **Do:**
  1. Diff conftest files vs AT; restore roadmap-related fixtures this repo lacks (they were removed in `80e0820`: `tests/conftest.py` −2 lines, `tests/smoke/conftest.py` −22 lines) without disturbing mail/oc-todo fixtures.
  2. From AT's `tests/test_config.py`, transplant the `roadmap_prompts` validation/load test cases missing here; adapt expectations: `listing_repo` accepts `y2d2/agentic_scripts`; add cases for `local_listing` (default `"plans.md"`, explicit string, `null`, and `""` → `ConfigError`).
  3. From AT's `tests/test_scheduler.py`, transplant idle-gate-with-registered-workflow cases missing here (e.g. gate-closed quiet run continues for `gate: idle` entries).
- **Acceptance:** `uv run pytest tests/test_config.py tests/test_scheduler.py -q` PASS with the transplanted cases collected (verify via `-k` counts).

### Task 3: New mirror tests
- **Files:** inside `tests/test_roadmap_dev.py` (or a new `tests/test_roadmap_dev_listing_mirror.py`, your choice — same file as the other listing tests is preferred).
- **Do:** add ≥2 hermetic tests driving the reconcile path with a temp project root:
  1. `local_listing: "plans.md"` → after a reconcile run (fixture clones, no network), `<tmp root>/plans.md` exists and equals the rendered listing text byte-for-byte; action list contains `listing mirrored to`.
  2. `local_listing: null` → no file written.
  3. Bonus if cheap: mirror updated when remote push is a no-op (mirror stale/deleted, listing unchanged → mirror written).
- **Acceptance:** the new tests PASS, and they demonstrably fail if the mirror call-site is stubbed out (verify once by temporary local mutation, then revert).

### Task 4: Full green + lint + commit
- **Do:** `uv run pytest tests/ -q` (all tests, zero failures, zero roadmap skips); `uv run ruff check .`; commit `OC: Port roadmap-dev test suite (core, scan, pipeline, smoke) + local_listing mirror tests` + push.
- **Acceptance:**
  1. Full-suite pytest PASS (record collected-count delta in the result report).
  2. `uv run ruff check .` clean.
  3. Commit stat lists only test files; pushed.

## Out of Scope

- Module logic changes — if a ported test reveals a real bug in the ported code, report it as a blocker instead of silently changing behavior (exception: import-path/fixture wiring fixes).
- README, validation runs, AT repo changes.

## Notes

- `[Assumption]` AT @ 899ce44's suite is self-consistent with the ported module (same source revision) — any mismatch here should trace to this repo's config/yaml deltas, not to module drift.
