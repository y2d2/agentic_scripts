# Task Plan: roadmap-dev listing — goal + task-titles detail row

**Purpose:** Make the roadmap-dev `plans.md` listing (the plan overview) carry, under every plan row, a workflow-owned detail row with the plan's goal and the title of every task in the plan.

## Objective

The live plan overview (`plans.md` in `y2d2/autonomous_task_overview`, reconciled by the
`roadmap-dev` workflow every 30-minute scan) currently shows one 6-column row per plan
(`| approval | priority | plan | title | state | remove |`) with only the plan's h1 title.
End state: directly under each plan row the workflow renders an extra 6-cell **detail row**
(user decision 2026-11-22, format "B"):

```
| ☐ | 1 | planning/orbit-dmp/work_plan.md | Task Plan: ORBIT DMP v0 — consortium DMP | open | ☐ |
| — | — | **Goal:** Build `projects/ORBIT/DMP/ORBIT_DMP_v0.md`, the table-first consortium DMP, in five sequential sub-agent tasks. | **Tasks:** 1 Skeleton & front matter · 2 Master table 1 · 3 Supporting tables 2–6 · 4 Minimal prose + Coera/IP text · 5 QA pass | — | — |
```

Content sources (all workflow-owned, derived from the plan at scan time — no new state
schema): goal = the `**Purpose:**`/`**Goal:**` line of `work_plan.md` (fallback `## Purpose`/
`## Goal` section, else `—`); task titles = the `### Task N[:letter]: <title>` headings
(fallback: a task table in `work_plan.md`, then the `work_plan_task_<N>_<desc>.md` file
names; else `—`), all of them, no truncation. The detail row is byte-stable, is silently
skipped by the defensive `parse_listing` (non-numeric priority cell), and is re-derived on
every pass — the listing's steady-state no-push invariant is preserved.

## Context

- **Repo/branch:** `/workspace/Python/agentic_scripts` on `feature/roadmap-dev-workflow`
  (up to date with origin; working tree has 3 untracked `planning/mail-keeper-pruning/`
  result files from another session — leave them alone). Python ≥3.12, `uv`-managed;
  lint `uv run ruff check .` (line-length 100, E/F/I/UP/W), format `uv run ruff format --check .`,
  test `uv run pytest -q` (testpaths `tests`).
- **Conventions:** heavy Google-style docstrings — every function carries
  Purpose/Args/Returns (± Side Effects/Raises/Note); module docstrings document design
  rationale. New code must match (see `roadmap_dev.py` itself).
- **Code under change:** `src/agentic_scripts/workflows/roadmap_dev.py` (≈2980 lines):
  pure core (`extract_title` L294, `Plan` L315, `discover_plans` L368, `ListingRow` L543,
  `parse_listing` L575, `render_listing` L638, `reconcile` L686) + the workflow shell.
  Listing constants `LISTING_COLUMNS`/`_LISTING_HEADER`/`_LISTING_SEPARATOR` L98–106.
  Tests: `tests/test_roadmap_dev.py` (1018 lines; key fixtures `SAMPLE` contract sample,
  `_roadmap_config`, `base_config`; round-trip test L321, render test L389, reconcile
  tests L459ff construct `ListingRow` positionally).
- **Parser contract (load-bearing):** `parse_listing` silently skips any line that is not
  a 6-cell table row with an INTEGER priority cell (int() → ValueError → skip). The detail
  row relies on this: its priority cell is `—` (EM DASH U+2014, NOT a hyphen — the
  separator-row check is `set(cell) == {"-"}`). A rendered detail row must therefore
  NEVER parse as a data row; add a regression test with adversarial goal/task text
  (pipes, digits, `☑`, the word "approval", dash strings).
- **Renderer contract:** `render_listing(rows)` is byte-stable; `_reconcile_and_push`
  compares `render_listing(new_rows) == current_md` for the no-push decision. The detail
  row must be deterministic from the row's fields (it is — goal/task_titles are stamped
  from the scanned `Plan`, whose content is hashed into the plan identity, so an edited
  plan already yields a new row).
- **Real plan-format coverage (verified 2026-11-22 across the 9 allowed repos, 77 plans):**
  inline `**Purpose:**` 61 plans, `## Purpose` section 1, neither 15 (→ `—`); task
  headings `### Task N: …` dominant, with `### Task 3b:` subtask labels, plural
  `### Tasks 8–9 …: CANCELLED` (must NOT match), non-task h3s containing "Task"
  (`### Bag-reader format support (RESOLVED by Task 2 …)`), and trailing spec refs in
  `→ \`file.md\`` / `— see \`file.md\`` / `— \`file.md\`` forms (strip); task-table plans
  (ARP_roadmap) use `| Task | File | Schedule |` or `| # | Task | Agent | Depends on |`
  tables with cells like `1 — relocate e-mail lists`, bare `1`, or
  `work_plan_task_1_tikz_scenario_b.md — TikZ schematic …`; heading-less plans still have
  `work_plan_task_<N>_<desc>.md` files (e.g. orbit-plenary-i-slides, 24 tasks).
- **Live listing:** `y2d2/autonomous_task_overview` main, currently 77 data rows (all `open`,
  all ☐ — nothing approved, so a forced run starts no jobs). Local read copy:
  `/workspace/Obsidian/ARP_roadmap/autonomous_task_overview` (Obsidian vault; its
  `README.md` documents the listing format and MUST be updated in Task 2).
- **CLI:** `uv run agentic-scripts run --force --only roadmap-dev` — `--force` bypasses the
  quiet+idle gates (for an idle-gate workflow `gate_open` is then True, so the drain runs,
  but with zero approved rows `_select_startable` returns [] → "drain done (startable=0)",
  no job starts).

## Tasks

### Task 1: Core — extractors, Plan/ListingRow fields, render/parse/reconcile, tests
- **Files:** `src/agentic_scripts/workflows/roadmap_dev.py` (modify), `tests/test_roadmap_dev.py` (modify)
- **Do:** Full spec in `work_plan_task_1_core_detail_line.md`.
- **Acceptance:** extraction pure functions + `Plan`/`ListingRow` fields + detail-row render + parser safety + fixed-point pipeline test; `uv run pytest -q` green; ruff check + format clean; committed (OC: prefix, explicit paths, not pushed).

### Task 2: Listing-repo README — document the detail row (parallel with #1)
- **Files:** `/workspace/Obsidian/ARP_roadmap/autonomous_task_overview/README.md` (modify)
- **Do:** Full spec in `work_plan_task_2_listing_readme.md`.
- **Acceptance:** README "## The listing" sample shows the detail row + ownership note; committed (OC:) + pushed to origin/main.

## After above complete

### Task 3: Live run + remote/local verification (depends on #1, #2)
- **Files:** none (operational verification; pulls the Obsidian copy)
- **Do:** Full spec in `work_plan_task_3_live_verify.md`.
- **Acceptance:** forced run `status=ok errors=0`; listing pushed with a detail row under
  every one of the 77 data rows; second run adds no new commit (idempotent); no
  `roadmap-dev/*` attempt branch created; Obsidian local copy pulled and shows the detail rows.

## Out of Scope

- No state-schema change (`state/roadmap-dev.json` v1 untouched — goal/task titles are
  derived from the scan, never persisted).
- No change to the 6-column data-row contract, user-owned cells (approval/priority/remove),
  the re-arm rule, identity/content-hash semantics, or the brief/drain/outcome routing.
- No PR creation / GitHub API (workflow invariant — delivery is the pushed attempt branch,
  human opens the PR).
- No goal/task truncation (the user asked for every task title).
- No change to the renderer's existing behaviour of emitting no title header (pre-existing).
- No changes to `oc_todo.py`, `mail_keeper.py`, `config/workflows.yaml`, or `planning/`
  (incl. the untracked mail-keeper-pruning result files).
- No migration/rewrite of already-pushed listing history (one-time re-push adds the rows).

## Notes

- [Assumption] "Plan overview" = the `plans.md` listing — confirmed by the user's format
  choice (extra table row) on 2026-11-22.
- [Assumption] Goal source = the Purpose/Goal markers (62/77 real plans), task source
  tiers = headings → task table → task file names; the 15 plans without a Purpose line
  show `**Goal:** —`. Verified against the live clones of all 9 allowed repos.
- [Note] The detail row is **workflow-owned** (like `title`/`state`): user hand-edits to it
  are overwritten on the next scan — documented in the README (Task 2).
- [Note] Load-bearing parser defense: the detail row's priority cell must stay the em dash
  `—` (not `-`, not numeric) or it could parse as data. Regression-tested in Task 1.
- [Note] Pre-existing quirk, unchanged: `Git.show_file` strips trailing newlines, so
  `_reconcile_and_push` attempts a (no-op) commit every run; observable effect: no extra
  commits after the first push of the new format.
- [Risk] Task 3's `--force` opens the drain gate; if the user has approved any plan
  between now and the run, the workflow WILL start a real job (by design). The dev agent
  must check the `drain start … startable=N` log line and report `N > 0` as a Next Step —
  never kill an in-flight job.
- [Note] Editing a plan's Purpose/Task section changes the content hash → new identity →
  new row; the old row reconciles away. The detail row is always in sync with identity.
- [Adjudication 2026-11-22] Task-3 flagged the orbit-plenary-i-slides detail row
  (`**Tasks:** 9 outcomes report · 10 cleaned deck`) against this plan's stale spec
  expectation ("24 tasks from file names"). Orchestrator verified the LIVE
  `work_plan.md`: it was restructured (Phase A "done, tasks 1–8" prose-only; Phase B is a
  2-row task table for tasks 9–10). Tier 2 (the plan's own current task table) winning
  over tier 3 (23 residual spec files) is the committed tier precedence — CORRECT-BY-DESIGN,
  no code change. The spec expectation was stale (investigation had read only the file top).
- [Note] Live-run overlap observed 2026-11-22: the 19:30 systemd fire (working-tree code,
  pre-commit) already pushed the new format (`110c648`) before Task 3's forced runs —
  Task 3's spec tolerates this (remote file content is the authority; forced runs then
  rendered identically → no-op commits, verified idempotent).
