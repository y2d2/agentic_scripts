# lightweight_dev Output — Task: plans.md per-plan sections (render + tests)

**Task:** #1    **Session:** listing-detail-row-and-workflow-diagram    **Date:** 2026-11-26

## Summary

In `/workspace/Python/autonomous_task_overview`, on a new branch `feature/listing-detail-row`
created from clean, up-to-date `main` (pushed with `-u`), replaced the listing "detail row"
renderer with the per-plan two-table structure per the byte contract: each plan now renders as
a `### <plan path>` heading, its own 6-column table (header + separator + the single,
byte-unchanged data row), and — only when the plan has real goal text or task titles — a
separate single-column `details` table whose one cell holds `**Goal:** …` and each task on its
own `<br>` line. A plan with neither emits NO details table (no all-dash noise row; the scan's
`"—"` no-marker sentinel is counted as "no goal"). Exactly one blank line follows every block
(doubling as the separator before the next `###`/`##`/`#` line); `#`/`##` lines stay
contiguous; empty rows → `""`; single trailing newline. `parse_listing` logic is **unchanged**
(docstrings only — every new artifact falls out of the existing guards, and old-format
`| — | — | …` rows keep being skipped via the em-dash priority). `reconcile`, the state
machine and the drain logic differ from `main` in docstrings only. `plans.md`, `config/`,
`systemd/` and the docs (`README.md`, `WORKFLOW.md`, `VARIABLES.md` — Task 2) untouched.

Work is committed as the single commit **“OC: Render plans.md listing as per-plan sections
with optional details tables”** on `feature/listing-detail-row` (pushed; upstream `-u` set).
`ruff check` and `ruff format --check` are clean on `src` + `tests`.

## Files

| File | Action | Why |
|---|---|---|
| `src/autonomous_task/workflows/roadmap_dev.py` | modify | Replaced `_detail_row` with `_plan_block` (per-plan section per byte contract); added `_DETAILS_HEADER` / `_DETAILS_SEPARATOR` constants (`\| details \|`, 9-dash separator); rewrote `render_listing` emit loop (grouping/order logic identical); reworded module/`extract_goal`/`extract_task_titles`/`Plan`/`ListingRow`/`_escape_cell`/`parse_listing`/`reconcile` docstrings — parser/reconciler CODE bodies byte-unchanged |
| `tests/test_roadmap_dev.py` | modify | Round-trip + section-render fixtures to the new bytes; adversarial skip test rewritten (pipes, ☑, old-format rows, word `details`; asserts only data rows parse, and a goal-less/task-less plan renders no details table); exact-bytes test rewritten (details-present + details-skipped + goal-only/tasks-only + escaped pipes); NEW focused test `test_render_listing_pipes_round_trip_to_exact_data_rows`; fixed-point test rewritten to section structure |
| `tests/test_roadmap_dev_scan.py` | modify | `DETAIL_UNITEST`/`DETAIL_ORBIT` constants replaced with `PLAN_*` / `DETAILS_*` and `EXPECTED_RUN1` rebuilt to the new bytes (unitest: NO details table; orbit: `\| **Goal:** —<br>**Tasks:**<br>1 x \|`) |
| `tests/test_roadmap_dev_pipeline.py` | (untouched) | Verified: embeds no old-format bytes; its `_user_edit_listing` / `_row` helpers are row-substring/parse based and fixture plans yield no details tables |
| `tests/smoke/test_smoke_roadmap_dev.py` | (untouched) | Verified: only the header-only listing stub; no old-format bytes |

## Build / Tests

- `uv run pytest` (repo root, at HEAD): **PASS — 82 passed, 0 failed** (incl. all smoke tests; selection unchanged, none deselected/added)
- `uv run ruff check src tests`: PASS
- `uv run ruff format --check src tests`: PASS
- Contract spot-render (manual `render_listing` of goal+tasks / goal-only / tasks-only / pipe rows): **PASS** — byte-identical to the spec sample block

## Acceptance Verification

| # | Criterion (verbatim) | Result | Notes |
|---|---|---|---|
| 1. | `uv run pytest` from `/workspace/Python/autonomous_task_overview` → entirely green (report pass/fail counts). | PASS | 82 passed / 0 failed (51 unit + 13 pipeline + 12 scan + 6 smoke). |
| 2. | Exact-byte unit test proves the new per-plan block contract (heading, repeated header/separator, blank line, details table only when goal or tasks exist, `<br>`-separated tasks, single trailing newline). | PASS | `test_render_listing_emits_per_plan_sections` (full byte dump: details present + both-empty skip) + round-trip/empty-stable fixtures; goal-only → `<br>**Tasks:** —`, tasks-only → `**Goal:** —` also pinned. |
| 3. | Parse tests prove: new artifacts never parse as data rows (incl. escaped pipes in details, ☑ glyph, old-format rows); data rows parse identically to before. | PASS | `test_parse_listing_skips_per_plan_sections` (adversarial + appended old-format rows + word `details`) and the new `test_render_listing_pipes_round_trip_to_exact_data_rows`; `parse_listing(SAMPLE)` (legacy plain + old detail-row listings) unchanged. |
| 4. | Fixed-point test proves no-op reconcile renders byte-identical text. | PASS | `test_listing_pipeline_fixed_point`: `file1 == file0`, `rows1 == rows0`, `st2 == st1`, `log1 == []`, plus section-structure assertions (unitest has NO details table). |
| 5. | `git log` shows the work on `feature/listing-detail-row` (OC: commits, pushed, `-u` set); `main` untouched; `plans.md` byte-identical (`git diff main -- plans.md` empty). | PASS | Single OC: commit (“OC: Render plans.md listing as per-plan sections with optional details tables”) pushed to `origin/feature/listing-detail-row` (upstream set at creation); `git diff main` touches only the 3 files above; `git diff main -- plans.md` empty; nothing committed on `main`. |
| 6. | `parse_listing`, `reconcile`, and all state/drain logic behaviorally unchanged (diff review: their code differs only in docstrings/none). | PASS | Diff review: `parse_listing` and `reconcile` hunks are entirely within docstrings; state/drain/`_reconcile_and_push` code not in the diff at all; `render_listing` grouping loop identical, only the emit lines changed. |

## Blockers

None.

## Next Steps

- Task 2 (docs): mirror the byte contract in `README.md` / `WORKFLOW.md` / `VARIABLES.md` — the
  authoritative rendering is now `### <plan>` + own table + optional `| details |` table; the
  old `| — | — | **Goal:** …` row is gone from the renderer but still PARSED-silent in live
  listings.
- Orchestrator note (non-blocking, by-design): after this branch merges, the cron engine will
  rewrite the live `plans.md` to the new structure on its next fire — the no-op fixed point
  holds (verified), so exactly one format-migration commit is expected, then silence.
- Observation (informational, spec-faithful): the parser's six-cell + `int()` guards skip all
  emitted details lines in practice; a hand-crafted goal containing ≥5 raw pipes with a bare
  integer in the wrong position could theoretically forge a ghost row, which the reconciler
  drops as a ghost on every pass (self-healing, no render churn). Parser logic was left
  unchanged exactly as the task plan mandates.
