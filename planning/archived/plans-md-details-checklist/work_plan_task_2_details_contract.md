# Task Plan: details 3-col contract

**Purpose:** Change the `plans.md` details table in `roadmap_dev.py` from the single-cell layout to the locked 3-column multi-row checklist table, with per-task done flags and a state-mirrored goal mark.

## Objective
In `/workspace/Python/agentic_scripts/src/agentic_scripts/workflows/roadmap_dev.py`, implement the new details-table contract (below) end-to-end inside the source file: constants, data-model arity, scan stamping, renderer, and every affected docstring. End state: source renders/parses the new layout; all non-details byte fixtures still pass.

## Context
Task 1 (already merged in the working tree) added `_TASK_REPORT_NAME_RE` and `task_done_labels(file_names) -> frozenset[str]` to this file. Current state of the file: `_DETAILS_HEADER = "| details |"` (~line 121), `_DETAILS_SEPARATOR = "|---------|"` (~125), `Plan` (~633, `task_titles: tuple[tuple[str, str], ...] = ()`), `discover_plans` stamps `task_titles=extract_task_titles(entry.work_plan_text, list(entry.file_contents))` (~730), `ListingRow` (~872, same field), `_plan_block` (~925) renders the one-cell table, `parse_listing` (~971) defensively accepts ONLY six-cell `| … |` rows, `render_listing` (~1048) joins blocks with exactly one blank line, and `reconcile` re-stamps `task_titles=plan.task_titles` at three sites (~1227, ~1283, ~1299) — pure pass-through, verify no tuple unpacking anywhere else. `extract_task_titles` (~515) is unchanged by this task. Repo is `agentic_scripts`; commit with `OC:` prefix to the current branch and push.

## Locked render contract (exact bytes)
```markdown
| # | details | ✓ |
|---|---------|---|
| G | <goal text, or — when absent> | ☑ if row.state == "success" else ☐ |
| 1 | <task title> | ☑ if done else ☐ |
| 3b | <task title> | ☐ |
```

## Tasks

### Task 1: Contract change in `roadmap_dev.py`
- **Files:** `src/agentic_scripts/workflows/roadmap_dev.py` (modify only this file)
- **Do:**
  1. Constants: `_DETAILS_HEADER = "| # | details | ✓ |"`; `_DETAILS_SEPARATOR = "|---|---------|---|"`. Update their comment lines.
  2. `Plan.task_titles` and `ListingRow.task_titles` become `tuple[tuple[str, str, bool], ...] = ()` — 3-tuples `(label, title, done)`; update the attribute docstrings (done = a `lightweight[-_]dev_task_<label>_*.md` result report exists in the plan folder; the goal row's mark is NOT stored, it mirrors `state`).
  3. `discover_plans`: stamp via
     ```
     titles = extract_task_titles(entry.work_plan_text, list(entry.file_contents))
     done = task_done_labels(entry.file_contents)
     task_titles = tuple((label, title, label in done) for label, title in titles)
     ```
  4. `_plan_block`: keep the presence rule (`goal` not in `("", "—")` or `task_titles` non-empty → emit). Emit `["", _DETAILS_HEADER, _DETAILS_SEPARATOR]` then one row per entry: `| G | {_escape_cell(goal or "—")} | {"☑" if row.state == "success" else "☐"} |`, then for each `(label, title, done)`: `| {_escape_cell(label)} | {_escape_cell(title)} | {"☑" if done else "☐"} |`. Drop the old `<br>` body assembly. No trailing spaces.
  5. Docstrings to update (keep the file's dense documentation style): module docstring lines ~41–49 (describe the new 3-column checklist + how ☑ is derived); the two constants' comments; `Plan.task_titles` / `ListingRow.task_titles`; `_plan_block` (new line counts: 4, or 5 + n_tasks); `parse_listing` (add: the multi-row 3-cell details rows are likewise never six-cell → skipped; old 1-cell and em-dash-6-cell detail lines keep being skipped as before); `reconcile` rule-1 re-stamp sentence (re-stamped fields now carry the done flags).
- **Notes:** `parse_listing` needs NO logic change (3 ≠ 6 cells). Do not touch `extract_goal`/`extract_task_titles`/`_escape_cell`. Do not edit tests in this task — byte fixtures are Task 3's job; run the suite and REPORT the expected failures (they should be limited to details-by fixtures and `task_titles` 2-tuple fixture constructions).
- **Acceptance:**
  1. `ruff check src` clean; `python -c "from agentic_scripts.workflows import roadmap_dev"` OK.
  2. New inline behavior verifiable via `python - <<'PY'` snippet: a `ListingRow` with `state="success"`, `goal="G"`, `task_titles=(("1","t",True),("2","u",False))` renders exactly `| # | details | ✓ |`, `|---|---------|---|`, `| G | G | ☑ |`, `| 1 | t | ☑ |`, `| 2 | u | ☐ |`; the same row with `state="open"` renders `| G | G | ☐ |`.
  3. A rendered listing round-trips: `parse_listing(render_listing(rows))` returns exactly the six-cell rows (no details rows), and re-render with re-stamped fields is byte-stable.
  4. Full `pytest -q` failures are confined to details-fixture / tuple-arity tests (list them in the result report); non-table tests pass.
  5. Diff touches only `roadmap_dev.py`; commit `OC: plans.md details table -> 3-col checklist (contract)` + push.

## Out of Scope
- Test fixture updates (Task 3), README (Task 4), `plans.md` hand-edits, `parse_listing` logic, state schema, identity/hash behavior, work-plan `- [x]` support, report-content parsing.

## Notes
- [Assumption] Report existence ⇒ done (blocked reports will read ☑) — user-accepted; goal mark mirrors plan state per user decision 2026-11-28.
- Byte-stability across no-op reconciles must hold: done flags come from the deterministic scan, so the rendered bytes are deterministic for unchanged folders.
