# lightweight-dev Output — Task: details 3-col contract

**Task:** #2    **Session:** ses_dde54217cffemH30p2Vur2U1Lc    **Date:** 2026-11-28

## Summary

Changed the `plans.md` details table in `roadmap_dev.py` from the single-cell `<br>` layout to the locked 3-column multi-row checklist, end-to-end in the source file:

- **Constants:** `_DETAILS_HEADER = "| # | details | ✓ |"`, `_DETAILS_SEPARATOR = "|---|---------|---|"` (comments updated).
- **Data model:** `Plan.task_titles` and `ListingRow.task_titles` are now `tuple[tuple[str, str, bool], ...]` — `(label, title, done)` triples; attribute docstrings updated (done = a `lightweight[-_]dev_task_<label>_*.md` result report exists in the plan folder; the goal row's mark is NOT stored, it mirrors `state`).
- **`discover_plans`:** stamps via `titles = extract_task_titles(...)` + `done = task_done_labels(entry.file_contents)` + `task_titles = tuple((label, title, label in done) ...)` — uses Task 1's `task_done_labels`, does not re-add it.
- **`_plan_block`:** same presence rule (real goal or non-empty `task_titles` → emit); emits blank + header + separator + goal row `| G | <goal or —> | ☑/☐ |` (☑ iff `row.state == "success"`) + one row per task `| <label> | <title> | ☑/☐ |` (☑ iff `done`). Old `<br>` body assembly dropped; goal/label/title escaped with `_escape_cell`; no trailing spaces on any emitted line.
- **Docstrings updated** (file's dense style kept): module docstring details paragraph (3-column checklist + ☑ derivation), both constants' comments, `Plan.task_titles` / `ListingRow.task_titles`, `_plan_block` (new line counts: 4, or 8 + n_tasks), `parse_listing` (3-cell checklist rows likewise never six-cell → skipped; old 1-cell and em-dash-6-cell detail lines keep being skipped as before), `reconcile` rule-1 re-stamp sentence (re-stamped triples now carry the done flags).
- **No logic change** to `parse_listing` (3 ≠ 6 cells), `extract_goal`, `extract_task_titles`, `_escape_cell`; the three `reconcile` re-stamp sites are untouched (pure pass-through of the now-triple field; no tuple unpacking of `task_titles` anywhere else in `src/`). No test file touched.

Committed with message `OC: plans.md details table -> 3-col checklist (contract)` to `feature/roadmap-dev-workflow` and pushed (only `roadmap_dev.py` staged; the pre-existing modified `plans.md` and untracked `planning/**` left untouched).

## Files

| File | Action | Why |
|---|---|---|
| `src/agentic_scripts/workflows/roadmap_dev.py` | modify | The whole contract change: constants, data-model arity, `discover_plans` done-flag stamping, `_plan_block` 3-col renderer, all affected docstrings |

## Build / Tests

- `ruff check src`: **PASS** — "All checks passed!"
- `python -c "from agentic_scripts.workflows import roadmap_dev"`: **PASS**
- Acceptance snippet (`ListingRow` render check): **PASS** — see criterion 2 below
- Round-trip / byte-stability / legacy-skip / reconcile-stability snippet: **PASS** — see criterion 3 below
- `pytest -q` (full suite): **6 failed, 341 passed** — all 6 failures are the expected details-fixture / tuple-arity category (per criterion 4; fixed by follow-up Task 3). Baseline before the change: 347 passed.

### Remaining pytest failures (expected — Task 3 updates these fixtures)

| # | Test | Failure reason | Category |
|---|---|---|---|
| 1 | `tests/test_roadmap_dev.py::test_discover_plans_stamps_goal_and_tasks` | `AssertionError: assert (('1', 'Skeleton & front matter', False), …) == (('1', 'Skeleton & front matter'), …)` — expected value is the old 2-tuple pair; production now stamps 3-tuples | tuple-arity fixture |
| 2 | `tests/test_roadmap_dev.py::test_parse_listing_skips_per_plan_sections` | `ValueError: not enough values to unpack (expected 3, got 2)` in `_plan_block` — fixture builds `task_titles=(("1", "x \| y"),)` 2-tuples | tuple-arity fixture |
| 3 | `tests/test_roadmap_dev.py::test_render_listing_emits_per_plan_sections` | `ValueError: not enough values to unpack (expected 3, got 2)` — 2-tuple fixtures; expected bytes also encode the old 1-cell `| details |` layout | tuple-arity + details byte fixture |
| 4 | `tests/test_roadmap_dev.py::test_render_listing_pipes_round_trip_to_exact_data_rows` | `ValueError: not enough values to unpack (expected 3, got 2)` — 2-tuple fixtures | tuple-arity fixture |
| 5 | `tests/test_roadmap_dev.py::test_listing_pipeline_fixed_point` | `ValueError: not enough values to unpack (expected 3, got 2)` — `_row` helper passes 2-tuples (`task_titles=(("1", "One"), ("2", "Two"))`) | tuple-arity fixture |
| 6 | `tests/test_roadmap_dev_scan.py::test_first_run_discovers_two_plans_and_pushes_listing` | `assert _remote_listing(bare_p) == EXPECTED_RUN1` — `EXPECTED_RUN1` byte fixture still expects the old `| details |` one-cell layout; actual now `| # | details | ✓ |` etc. | details byte fixture |

All other 341 tests pass (non-table behavior, pipeline, state, identity, scan integration unaffected).

## Acceptance Verification

| # | Criterion (verbatim) | Result | Notes |
|---|---|---|---|
| 1. | "`ruff check src` clean; `python -c "from agentic_scripts.workflows import roadmap_dev"` OK." | PASS | "All checks passed!"; import OK (venv, Python 3.12). |
| 2. | "New inline behavior verifiable via `python - <<'PY'` snippet: a `ListingRow` with `state="success"`, `goal="G"`, `task_titles=(("1","t",True),("2","u",False))` renders exactly `| # | details | ✓ |`, `|---|---------|---|`, `| G | G | ☑ |`, `| 1 | t | ☑ |`, `| 2 | u | ☐ |`; the same row with `state="open"` renders `| G | G | ☐ |`." | PASS | Verified byte-exact via inline snippet (plus: no trailing spaces, em-dash goal → `| G | — | ☐ |`, absent goal+no tasks → no table, goal-only with `("3b", …)` label renders). |
| 3. | "A rendered listing round-trips: `parse_listing(render_listing(rows))` returns exactly the six-cell rows (no details rows), and re-render with re-stamped fields is byte-stable." | PASS | 3-row listing (success/open/review, pipe-escaped titles, em-dash goal): parse returns exactly the 3 six-cell rows with `goal=""`/`task_titles=()`; re-render after re-stamp is byte-identical. Legacy old 1-cell + em-dash-6-cell lines appended → still skipped. Full `discover_plans → reconcile → render → parse → reconcile` no-op pass: bytes, state doc, and action log all stable. |
| 4. | "Full `pytest -q` failures are confined to details-fixture / tuple-arity tests (list them in the result report); non-table tests pass." | PASS | `6 failed, 341 passed` — all 6 listed above, each a details byte fixture or a 2-tuple `task_titles` fixture; every non-details test passes. Task 3 will update these fixtures. |
| 5. | "Diff touches only `roadmap_dev.py`; commit `OC: plans.md details table -> 3-col checklist (contract)` + push." | PASS | Commit `OC: plans.md details table -> 3-col checklist (contract)` contains exactly 1 file (`roadmap_dev.py`, 75+/53−); pushed to `feature/roadmap-dev-workflow` (see git log). `plans.md` WIP and untracked `planning/**` remain unstaged/untouched. |

## Blockers

None.

One plan-vs-reality note (non-blocking): the plan's `_plan_block` docstring hint said "new line counts: 4, or 5 + n_tasks"; the truthful total is **4, or 8 + n_tasks** (base 4 + blank + header + separator + goal row + n task rows — empirically 10 lines for n=2, confirmed by the criterion-2 byte block). The docstring states the measured value; the byte contract itself matches the plan exactly.

## Next Steps

- **Task 3 (test fixtures):** update the 6 failing tests listed above — 3-tuple `task_titles` fixtures (`("label", "title", done)`) and new 3-col byte fixtures (`| # | details | ✓ |` / `|---|---------|---|` / goal row / task rows), including `EXPECTED_RUN1` in `test_roadmap_dev_scan.py`; add coverage for the goal-row mark mirroring `state` and the `done` flag from report file names.
- **Task 4 (README):** describe the new 3-column checklist details table.
- Live `plans.md` will re-render into the new layout on the next roadmap-dev reconcile run (its details sections are workflow-owned and re-stamped each pass).
