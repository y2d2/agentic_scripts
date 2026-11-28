# Task Plan: plans.md details 3-col checklist

**Purpose:** Replace the one-cell `details` table in the generated `plans.md` listing with a multi-row 3-column checklist table (G/labels | details | ☑).

## Objective
The per-plan **details table** rendered by `src/agentic_scripts/workflows/roadmap_dev.py` into `plans.md` is a single-column table whose one cell crams `**Goal:** …<br>**Tasks:**<br>…`. Replace it with a 3-column, multi-row table: column 1 is `G` (goal) then the task labels `1…n`; column 2 the description; column 3 a checkmark — **task ☑ iff a `lightweight[-_]dev_task_<label>_*.md` result report exists in the plan folder** (user decision 2026-11-28), **goal ☑ iff the plan's `state` is `success`** (user decision 2026-11-28). Success condition: byte-stable rendering, parser unaffected (3-cell rows never pass the six-cell gate), full pytest suite green, README sample updated.

## Locked render contract (all tasks share these exact bytes)
```markdown
| # | details | ✓ |
|---|---------|---|
| G | <goal text, or — when absent> | ☑ if row.state == "success" else ☐ |
| 1 | <task title> | ☑ if done else ☐ |
| 3b | <task title> | ☐ |
```
- Constants: `_DETAILS_HEADER = "| # | details | ✓ |"`, `_DETAILS_SEPARATOR = "|---|---------|---|"`.
- Details table emitted only when the plan has a real goal or ≥1 task (unchanged presence rule); goal cell is `—` when goal absent.
- Task done-flag: `label in done_labels`, where `done_labels` comes from the plan folder's file names matching `(?:^|/)lightweight[-_]dev_task_(\d+)([a-z]?)_[^/]*\.md$` (label = `{num}{letter}`).
- Cells escaped with `_escape_cell` exactly as today; the ☑/☐ glyphs match the existing checkbox style (`_checkmark()` maps ☑→True).

## Context
`plans.md` is generated + parsed by `roadmap_dev.py` (`_plan_block` ~line 925 renders; `parse_listing` ~971 parses defensively — only 6-cell rows pass; `render_listing` ~1048; `reconcile` re-stamps `goal`/`task_titles` from the scan at 3 sites ~1227/1283/1299). Data flow: `discover_plans` (~695–730) stamps `Plan(goal=extract_goal(...), task_titles=extract_task_titles(work_plan_text, list(entry.file_contents)))`; `Plan` (~633) and `ListingRow` (~872) are frozen dataclasses whose `task_titles` is `tuple[tuple[str, str], ...]`. Verified: no `- [ ]` checkboxes exist in any `work_plan.md`; result reports (`lightweight_dev_task_<N>_*.md`) have NO stable machine-readable status line → "report exists ⇒ ☑" is the rule. `entry.file_contents` keys are the folder-relative file names — the visibility point for reports (only **committed** files are seen by the scan).

## Tasks

### Task 1: Pure helper `task_done_labels` + unit tests (no behavior change)
- **Files:** `src/agentic_scripts/workflows/roadmap_dev.py` (modify), `tests/test_roadmap_dev.py` (modify, append tests)
- **Do:** Add regex `_TASK_REPORT_NAME_RE = re.compile(r"(?:^|/)lightweight[-_]dev_task_(\d+)([a-z]?)_[^/]*\.md$")` next to the other task regexes, and a pure `task_done_labels(file_names: Sequence[str]) -> frozenset[str]` returning `f"{num}{letter}"` for every matching name (defensive on empty input). Add unit tests covering: underscore + hyphen forms, `3b` label, folder-relative paths, non-matches (`work_plan_task_1_x.md`, `lightweight_dev_task_1.md` (no `_<desc>_`), `other_lightweight_dev_task_2_x.md` mid-string without boundary).
- **Acceptance:** see task file.

### Task 2: Contract change in `roadmap_dev.py` (depends on #1)
- **Files:** `src/agentic_scripts/workflows/roadmap_dev.py` (modify)
- **Do:** Per the locked contract: new `_DETAILS_HEADER`/`_DETAILS_SEPARATOR` values; `task_titles: tuple[tuple[str, str, bool], ...]` on `Plan` and `ListingRow`; `discover_plans` stamps the 3-tuples via `task_done_labels(entry.file_contents)`; `_plan_block` renders the 3-column multi-row table (G row marked ☑ iff `row.state == "success"`); update all affected docstrings (module header lines 41–49, constants, `Plan`/`ListingRow` attrs, `_extract` docs, `_plan_block`, `parse_listing` backward-compat paragraph — new 3-cell rows never pass the six-cell gate — and `reconcile` rule-1 re-stamp wording). The `reconcile` sites themselves pass `plan.task_titles` through and need no logic change (verify no unpacking there).
- **Acceptance:** ruff clean; non-details tests green; details-table byte fixtures MAY fail (Task 3 fixes them) — list of expected failures reported.

### Task 3: Test-suite update for the new layout (depends on #2)
- **Files:** `tests/test_roadmap_dev.py`, `tests/test_roadmap_dev_scan.py`, `tests/test_roadmap_dev_pipeline.py`, `tests/test_roadmap_dev_listing_mirror.py`, `tests/smoke/test_smoke_roadmap_dev.py` (modify as needed)
- **Do:** Update every fixture touching the details table / `task_titles` arity (grep `task_titles`, `details`, `DETAILS_HEADER`, `**Goal:**`, `<br>`); update byte-exact expectations to the locked contract; ADD behavior tests: ☑ on a task whose report file is in `file_contents`, ☐ without it, G ☑ only for `state="success"`, round-trip render→`parse_listing`→re-render stability incl. the new rows, old 1-cell and em-dash 6-cell detail lines still skipped.
- **Acceptance:** full `pytest -q` green; ruff clean.

### Task 4: README listing sample + wording (parallel with #3 — spec-locked, different file)
- **Files:** `README.md` (modify, "The listing" section ~lines 441–476)
- **Do:** Replace the single-column `| details |` sample and the "single-column … `<br>`-separated" wording with the new 3-column table sample and one sentence on how ☑ is computed (task: `lightweight_dev_task_<label>_*.md` report in the plan folder; goal: plan state `success`). Keep the "workflow-owned, edits pointless" note true and mention it still applies to the checkmarks.
- **Acceptance:** see task file.

## Parallel (after Task 2)
Tasks 3 and 4 run concurrently (disjoint files).

## Out of Scope
- No changes to `parse_listing` logic (skipping already suffices), to `plan_folder_hash`/identity, to state schema, or to the dev-agent report format.
- No hand-editing of `plans.md` (it is a generated mirror — the new layout lands on the next workflow reconcile run).
- No `- [x]` checkbox support in work plans (rejected alternative), no report-content status parsing (no stable status line exists).

## Notes
- [Assumption] "Result report exists ⇒ task done" is the completion signal (user-chosen). Blocked/partial runs also produce reports and will read ☑ — documented limitation; content-based status parsing is a possible follow-up.
- Result reports must be **committed** to the plan branch to be visible to the scan (currently often untracked locally) — the user was informed of this when choosing this source.
- Pre-existing uncommitted files (`plans.md` modified, many untracked `planning/**`) are NOT part of this plan; commit only explicit task paths (`git add <paths>`, never `-A`), `OC:`-prefix messages, stay on branch `feature/roadmap-dev-workflow`, push after each task commit.
- Byte-stability across no-op reconciles must be preserved (reconciler relies on it to keep the listing diff-free).
- Never reference the agent's own commit SHA in result reports (communication-skill incident rule).
