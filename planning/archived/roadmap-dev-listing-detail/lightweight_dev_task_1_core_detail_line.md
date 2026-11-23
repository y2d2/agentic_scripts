# lightweight-dev Output — Task: roadmap-dev listing goal + task-titles detail row (core)

**Task:** #1    **Session:** ses_dfb879917ffeBO6KAtzJfnBi6e    **Date:** 2026-11-22

## Summary
Implemented the Task 1 core from `work_plan_task_1_core_detail_line.md` in
`/workspace/Python/agentic_scripts` (branch `feature/roadmap-dev-workflow`, committed as
`OC: roadmap-dev listing — goal + task-titles detail row (render + extract)`, NOT pushed):

- **New pure extractors** (next to `extract_title`, heavy Google-style docstrings, never raise):
  - `extract_goal(work_plan_text) -> str` — (a) inline `**Purpose:**`/`**Goal:**` marker
    line (line remainder PLUS wrapped continuation lines up to a blank line / `#` line,
    joined with single spaces), then (b) a `## Purpose`/`## Goal` section (first paragraph
    of the body — the heading's blank line(s) are skipped), else `"—"`.
  - `extract_task_titles(work_plan_text, file_names=()) -> tuple[tuple[str, str], ...]` —
    tier 1 `### Task <n>[<a-z>]: <title>` headings (trailing spec-ref cut at the first
    `→`/`— see`/`—`/`-` connector that leads to a backticked-or-bare `.md` ref — internal
    arrows not leading to a `.md` never cut; `### Tasks 8–9 …`, `### Bag-reader …`, and all
    h2s never match); tier 2 task tables (header cell `task`/`#`, ALL such tables scanned,
    num under the `#` column else leading of the Task cell, all three observed cell shapes:
    `1 — <title>`, bare `1` + File-column derivation, `#` column + `file.md — <title>` tail,
    any-cell same-N fallback, no-num rows skipped); tier 3 `work_plan_task_<n>[<a-z>]_<desc>.md`
    file names (basename-anchored regex, so both basenames and folder-relative paths work —
    `discover_plans` passes `list(entry.file_contents)` as the spec's main text dictates).
    First tier that yields ≥1 pair wins; first occurrence per label; sorted by
    `(int(num), letter)` (so `10` sorts after `2`).
- **`Plan`:** new fields `goal: str`, `task_titles: tuple[tuple[str, str], ...]` (after
  `content_hash`), docstring updated; `discover_plans` always stamps both from the scan.
  **Deviation (documented in Blockers/Notes):** the fields carry defaults `""`/`()` instead
  of no-default — `tests/test_roadmap_dev_pipeline.py` (OUTSIDE the allowed change set)
  constructs `Plan(...)` with 5 positional args, and the ground rules demand BOTH
  "modify only the two named files" AND "whole suite green"; no-default fields would make
  that file `TypeError`. The production path (`discover_plans`) always stamps both fields.
- **`ListingRow`:** new LAST-TWO fields WITH DEFAULTS, per spec: `goal: str = ""`,
  `task_titles: tuple[tuple[str, str], ...] = ()` (existing positional constructions keep
  working; parsed rows carry no goal/tasks).
- **`render_listing`:** emits the detail row directly under EVERY data row via new private
  helpers `_detail_row(goal, task_titles)` + `_escape_cell` (`|` → `\|`): `| — | — |
  **Goal:** <goal|—> | **Tasks:** <label> <title> · … | — | — |` with EM DASHES (U+2014) in
  the 4 dash cells (byte-exact, load-bearing for the parser skip), `" · "` join, no
  truncation; byte-stable, single trailing newline.
- **`parse_listing`:** NO code change (the detail row fails `int()` on its em-dash
  priority cell; pipe-escaped goal/task text also breaks the six-cell count) — docstring
  extended to document the deliberate skip and the non-numeric-priority-cell safety
  contract.
- **`reconcile`:** stamps `goal=plan.goal, task_titles=plan.task_titles` on ALL THREE
  `ListingRow` constructions (rule 2 new row, rule 1 `updated_by_key`, rule 5 success
  re-add); docstring updated. Parsed rows keep the defaults — the detail row is always
  re-stamped from the scan (always fresh).
- **Module docstring:** listing-contract paragraph now documents the detail row
  (workflow-owned, derived from Purpose/Goal + task headings/tables/file names,
  re-stamped on every reconcile, parser-skipped, byte-stable).
- **Tests** (`tests/test_roadmap_dev.py`, 38 → 50 tests): 12 NEW —
  `test_extract_goal_inline_markers`, `test_extract_goal_wrapped_inline_and_sections`
  (`## Purpose` wrapped first paragraph, `## Goal` section),
  `test_extract_goal_fallback_and_adversarial` (no marker → `"—"`, empty → `"—"`,
  `## E-mail lists` mention INSIDE the goal line not truncated),
  `test_extract_task_titles_heading_order_and_duplicates` (3b/5c order, first per label),
  `test_extract_task_titles_ref_tail_cuts` (all four connector forms incl. the
  `(single task, …)` paren after the ref and `lightweight-dev_task_*.md`),
  `test_extract_task_titles_internal_arrow_and_non_task_headings` (internal
  `text → speaker notes` not cut; `### Tasks 8–9 …: CANCELLED`, `### Bag-reader …`, h2s
  never matched), `test_extract_task_titles_table_tier` (all three cell shapes + several
  tables + no-num/file-less row skipped + non-task table yields nothing),
  `test_extract_task_titles_file_name_tier_and_empty` (basenames AND folder-relative,
  `work_plan_task_10_*.md` sorts after `2`, empty input → `()`),
  `test_discover_plans_stamps_goal_and_tasks`, `test_parse_listing_skips_detail_rows`
  (adversarial: pipes in goal/tasks, ☑, words "approval"/"open", all-dash goal, digits →
  zero extra rows), `test_render_listing_emits_detail_rows` (exact bytes, goal present/
  absent, tasks present/absent, pipe escaping, byte-stable, single trailing newline),
  `test_listing_pipeline_fixed_point` (steady-state `file1 == file0`, rows value-equal,
  state doc unchanged, no actions, every data row immediately followed by ITS detail row).
  3 UPDATED — `test_parse_listing_round_trip_sample` (render now expects the default
  detail row after each data row; parse of the new form yields the same data rows),
  `test_render_listing_empty_stable_and_ordered` (expected output gains a detail row per
  data row), `test_reconcile_discovers_new_plan_empty_and_nonempty_table` (expected rows
  assert the stamped `goal`/`task_titles`; fixture plan with known goal/tasks asserted on
  the output row).

## Files
| File | Action | Why |
|---|---|---|
| `src/agentic_scripts/workflows/roadmap_dev.py` | modify (+386/−7) | extractors, `Plan`/`ListingRow` fields, detail-row rendering (`_detail_row`/`_escape_cell`), parse docstring, reconcile stamping ×3, module docstring |
| `tests/test_roadmap_dev.py` | modify (+415/−11) | 12 new tests + 3 updated covering the spec's full test list |
| `tests/test_roadmap_dev_scan.py` | modify (+7/−2) | `EXPECTED_RUN1` fixture constant gains the two detail rows (CONSTANTS ONLY, no test-logic changes — orchestrator-approved follow-up, Blocker option 1) |

## Build / Tests
- `uv run pytest tests/test_roadmap_dev.py -v`: PASS — 50/50 (12 new, 3 updated; all pre-existing green)
- `uv run pytest tests/test_roadmap_dev_scan.py -v`: PASS — 12/12 (incl. the previously
  failing `test_first_run_discovers_two_plans_and_pushes_listing` after the approved
  `EXPECTED_RUN1` patch)
- `uv run pytest -q` (whole suite): PASS — **335 passed, 0 failed**
- `uv run ruff check .`: PASS — All checks passed
- `uv run ruff format --check .`: PASS — 136 files already formatted
- Commits on `feature/roadmap-dev-workflow` (explicit paths, no `git add -A`, NOT pushed —
  orchestrator pushes; `planning/` and `config/` untouched):
  1. `OC: roadmap-dev listing — goal + task-titles detail row (render + extract)` — the two
     original in-scope files
  2. `OC: roadmap-dev listing — EXPECTED_RUN1 fixture gains the detail rows` — the
     orchestrator-approved 1-file follow-up (constant only)

## Acceptance Verification
| # | Criterion (verbatim) | Result | Notes |
|---|---|---|---|
| 1. | "extract_goal/extract_task_titles exist, pure, heavy docstrings; all the 'real plan formats verified' cases above pass as tests." | PASS | Both pure (no git/network/clock), full Google-style headers (Purpose/Rationale/Args/Returns/Note). Covered by tests: inline `**Purpose:**`/`**Goal:**`, `## Purpose`/`## Goal` sections (wrapped first paragraph), wrapped inline continuation until blank/heading, no marker → `"—"`, empty → `"—"`, `## E-mail lists` inside the goal line kept; heading order with `3b`/`5c` + first-per-label + `(int(num), letter)` sort; ref-tail cuts for all four connector forms (incl. `(single task, …)` paren after the ref, `lightweight-dev_task_*.md`, internal-arrow case cut at the FIRST connector that leads to a `.md`); `### Tasks 8–9 …: CANCELLED` / `### Bag-reader …` / h2 `## Tasks` NOT matched; table tier all three cell shapes (bare `1` + File-column derivation; `1 — <title>`; `#` column + `file.md — <title>`) + several tables + any-cell fallback + no-num row skipped; file-name tier (basenames AND folder-relative, `work_plan_task_10_*.md` numeric sort 2, 10); empty input → `()` |
| 2. | "Plan/ListingRow carry the new fields; discover_plans and all three reconcile row constructions stamp them; render_listing emits the detail row under every data row; parse_listing skips it (regression-tested with adversarial text)." | PASS | All stamp sites in place (rule 2, rule 1, rule 5 re-add); `test_parse_listing_skips_detail_rows` adversarial (pipes, ☑, "approval", "open", all-dash goal, digits) → zero extra rows; fixed-point test proves under-every-data-row emission. Deviation: new `Plan` fields have defaults (see Blockers) — forced by the unmodifiable pipeline test file; `discover_plans` always stamps |
| 3. | "uv run pytest tests/test_roadmap_dev.py -v fully green; uv run pytest -q (whole suite) green; uv run ruff check . and uv run ruff format --check . clean." | PASS | `-v`: 50/50 green. Whole suite: **335 passed, 0 failed** (after the orchestrator-approved `EXPECTED_RUN1` patch — see resolved note under Blockers). ruff check: All checks passed. ruff format --check: 136 files already formatted |
| 4. | "Committed on feature/roadmap-dev-workflow with an OC:-prefixed message (e.g. OC: roadmap-dev listing — goal + task-titles detail row (render + extract)) staging ONLY the two modified files (explicit paths; no git add -A); NOT pushed (the orchestrator pushes); planning/ and config/ untouched by the commit." | PASS | Committed with exactly the suggested message; `git show --stat` confirms only the two files; no push; untracked `planning/**` files untouched and not committed |

## Blockers
**None (one was reported and is now RESOLVED).**

- **[RESOLVED 2026-11-22] Previously failing test outside the original change set** —
  `tests/test_roadmap_dev_scan.py::test_first_run_discovers_two_plans_and_pushes_listing`
  asserted `_remote_listing(bare_p) == EXPECTED_RUN1` (L437), a byte-exact constant that
  predated the detail row (the fixture's orbit-sim folder carries
  `work_plan_task_1_x.md` → tier 3 yields `("1", "x")`, and neither fixture plan has a
  Purpose/Goal marker, so the two rendered detail rows are exactly
  `| — | — | **Goal:** — | **Tasks:** — | — | — |` after the unitest row and
  `| — | — | **Goal:** — | **Tasks:** 1 x | — | — |` after the orbit row). The orchestrator
  independently verified the diagnosis and **approved option 1** (add
  `tests/test_roadmap_dev_scan.py` to the change set, CONSTANTS ONLY).
  - Applied exactly as approved: `EXPECTED_RUN1` gains the two detail rows via two new
    `DETAIL_UNITEST` / `DETAIL_ORBIT` constants (matching the file's `ROW_*` style), the
    constant's no-trailing-newline shape preserved (last element is the bare orbit detail
    row, no `\n` — per the L58–60 NOTE about `show_file` rstripping). Nothing else in the
    file changed.
  - Verified after the patch: `tests/test_roadmap_dev_scan.py -v` 12/12 green (previously
    failing test now PASSES); whole suite **335 passed, 0 failed**; ruff check +
    `ruff format --check` clean. No other failures surfaced.
  - Landed as follow-up commit `OC: roadmap-dev listing — EXPECTED_RUN1 fixture gains
    the detail rows` (1 file, +7/−2; NOT pushed — orchestrator pushes).
- [Note] The `Plan` field-default deviation (Summary, Acceptance criterion 2) stands as
  documented: the new `Plan` fields carry defaults `""`/`()` because the unmodifiable-at-
  the-time `tests/test_roadmap_dev_pipeline.py` constructs `Plan(...)` positionally; the
  production path (`discover_plans`) always stamps both fields, so it is
  behavior-compatible with the spec. No action needed.

## Next Steps
- Orchestrator: push the two commits (I did not push, per dispatch):
  1. `OC: roadmap-dev listing — goal + task-titles detail row (render + extract)`
  2. `OC: roadmap-dev listing — EXPECTED_RUN1 fixture gains the detail rows`
- Task 1 is COMPLETE — all four acceptance criteria now PASS (see Acceptance
  Verification).
