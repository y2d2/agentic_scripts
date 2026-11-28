# Work Plan: Autonomous-Task Re-home (final): agentic_scripts → autonomous_task_overview

**Purpose:** Make `y2d2/autonomous_task_overview` the permanent home of ALL autonomous-task
execution (the roadmap-dev engine) with the live plan listing published to its own `plans.md`;
strip roadmap-dev entirely from `agentic_scripts` (which keeps only `noop`, `mail-keeper`,
`oc-todo`) and mark that repo end-of-life for this functionality with a README notice.

**Decided by user (2026-11-28):**
1. Listing destination = the overview repo's own `plans.md` (its `main` + root mirror).
2. EOL guard = README banner only (no AGENTS.md, no hooks).
3. Pre-cleanup: commit the untracked `planning/` artifacts as provenance; drop the
   uncommitted root `plans.md` mirror (it dies with this move).

## Objective

`agentic_scripts` cron keeps firing but only runs mail/todo work; the `# autonomous-task`
cron entry is re-installed pointing at the overview repo, which runs the *current, evolved*
engine (per-plan-section renderer, 3-col checklist, `task_done_labels`, `local_listing`),
with the live 86-item state migrated. Exactly one roadmap-dev engine ever fires. After this
plan, roadmap-dev code must not exist in `agentic_scripts` and its README says so.

## Context (verified by orchestrator 2026-11-28)

- **History:** roadmap-dev was migrated to the overview repo on Nov 24
  (`planning/autonomous-task-repo-move/`, 8/8 tasks), then ported BACK on Nov 27
  (`planning/archived/roadmap-dev-local-cutover/`, 5/5 tasks). This plan is the *final*
  re-home; the local-cutover port direction reverses. All operational gotchas (uv absolute
  path + PATH hardening in cron lines, crontab markers, forced-run validation, byte-stable
  rendering, headless `opencode run`) are documented inside those two folders' result files.
- **LIVE engine:** `agentic_scripts`, branch `feature/roadmap-dev-workflow`, cron
  `# agentic-scripts` `*/30` (mail/todo fire under quiet-window gate; roadmap-dev under
  `gate: idle`). Firing every 30 min (logs to `logs/run-20261128T*Z.log`).
  `state/roadmap-dev.json` live (last run 86 items, 11 actions, 0 errors).
- **Port source (code):** `agentic_scripts` HEAD `745e6a9` — `src/agentic_scripts/workflows/
  roadmap_dev.py` (evolved: `task_done_labels` `4c29098`, 3-col checklist contract `1e0d047`,
  `local_listing` mirror `092aeae`, per-plan-section renderer inherited from overview
  `feature/listing-detail-row@899ce44`).
- **Overview repo** `/workspace/Python/autonomous_task_overview` (persistent clone): dormant
  since Nov 27 09:01 (no cron entry). `main` tip `ced8907`; unmerged `feature/listing-detail-row`
  @ `899ce44` (ancestor of the current code — superseded by this port). Its
  `config/workflows.yaml` ALREADY has `listing_repo: y2d2/autonomous_task_overview`,
  `listing_path: plans.md`, `listing_branch: main`, but NOT `local_listing` (new in agentic
  code) and its `roadmap_prompts.allowed_repos` is the Nov-23 snapshot (9 repos, no
  `y2d2/agentic_scripts`) — sync from live config.
- **Overview package:** `autonomous_task`, single-workflow `runner.py`, trimmed `config.py`
  (`machine`/`agent`/`paths`/`roadmap_prompts`), NO psutil, agents (`planner-enhanced`,
  `lightweight-dev`) live in `~/.config/opencode/` (global, not versioned).
- **Setup:** `scripts/setup.sh` exists in overview (idempotent, `--skip-timer` valve, installs
  the `# autonomous-task` cron marker when run without the valve).
- **agentic_scripts cleanup surface (verified):** `src/agentic_scripts/workflows/
  roadmap_dev.py`; `config.py` (`RoadmapPrompts` block, transplanted `b063a74`);
  `config/workflows.yaml` (`roadmap_prompts:` L21+, `workflows.roadmap-dev:` L58+);
  tests `test_roadmap_dev.py`, `test_roadmap_dev_scan.py`, `test_roadmap_dev_pipeline.py`,
  `test_roadmap_dev_listing_mirror.py`, `smoke/test_smoke_roadmap_dev.py` + roadmap refs in
  `tests/conftest.py`, `tests/test_config.py`, `smoke/conftest.py`, `smoke/test_smoke_base.py`,
  `smoke/test_smoke_mail_keeper.py`, `smoke/test_smoke_oc_todo.py`; README roadmap-dev section
  (`e228c7c`); root `plans.md` (mirror, currently dirty). `scripts/setup.sh` has NO roadmap
  preflight step (verified — nothing to trim there).
- **Uncommitted (agentic_scripts):** ` M plans.md` + untracked `planning/autonomous-task-repo-move/`,
  `planning/archived/listing-detail-row-and-workflow-diagram/`,
  `planning/archived/plans-md-details-checklist/` (+ this folder once written).

## Naming (unchanged from the first migration)

| Thing | Value |
|---|---|
| Project / package / script | `autonomous-task` / `autonomous_task` / `autonomous-task` |
| Listing | `listing_repo: y2d2/autonomous_task_overview`, `plans.md`, branch `main`, `local_listing: plans.md` |
| Workflow name | `roadmap-dev` |
| Feature branch (overview) | `feature/rehome-final` (from `main`) |
| Cron markers | new: `# autonomous-task`; stays: `# agentic-scripts` (mail/todo only) |

## Tasks & Scheduling

All dispatched to `@lightweight-dev`. **Entirely consecutive** (shared repos + one engine
safety constraint). Result files: `lightweight_dev_task_<N>_<desc>.md` (this folder).

| # | Task | Repo | Depends on | Gate before? |
|---|------|------|-----------|--------------|
| 1 | Port evolved engine (module, `local_listing` config field, yaml sync, branch) | overview | — | no |
| 2 | Port + adapt test suite (incl. listing-mirror test), full suite green | overview | 1 | no |
| 3 | Docs sync (README/WORKFLOW/VARIABLES) | overview | 2 | no |
| 4 | Merge → `main`, live state snapshot, forced-run validation (A/B + double-render stability) | both | 3 | no |
| — | **GATE: cutover approval** (orchestrator presents Task-4 evidence; nothing is removed before user OK) | — | 4 | 🛑 |
| 5 | agentic_scripts: provenance commit + full roadmap-dev removal + README EOL banner, suite green | agentic_scripts | GATE | — |
| 6 | Install `# autonomous-task` cron; one gate-checked fire; one-engine proof | system + overview | 5 | — |
| 7 | Final end-to-end verification both repos | both | 6 | — |

## Out of Scope

- No split of mail-keeper/oc-todo out of `agentic_scripts` (user: later).
- Vault display copy `/workspace/Obsidian/ARP_roadmap/autonomous_task_overview` untouched.
- No deletion of overview's `feature/engine-move` / `feature/listing-detail-row` branches
  (historical; user can prune any time).
- No AGENTS.md, no pre-commit hooks, no GitHub-archive action (README banner only, per user).
- No hand-editing of `plans.md` in either repo by dev tasks (the engine owns it).
- No removal of dormant idle-gate machinery from `agentic_scripts` scheduler.

## Notes

- **[Assumption]** `y2d2/agentic_scripts` remains in `allowed_repos` (the engine must keep
  scanning this repo's `planning/` for plans even though the engine no longer lives here).
- **[Decision]** Overview repo `main` accumulates engine code + docs + listing commits —
  proven safe during Nov 24–27 (listing clone is a sandbox; commits never conflict).
- **[Decision]** agentic_scripts `main` also carries a one-off commit deleting root `plans.md`
  (the listing must not keep a ghost on the EOL repo's main; the engine pushed listing
  commits there Nov 27–28). Done inside Task 5 with the gate's blessing.
- **[Risk]** Double-engine: prevented by ordering — cleanup (5) strictly before cron install
  (6); between gate and 6, no roadmap-dev engine runs anywhere (its agentic yaml entry is
  deleted in 5; the `# autonomous-task` line is installed only in 6). A few idle 30-min
  windows with no scanner are acceptable and safe.
- **[Rollback]** Post-5/6: `git revert` the agentic cleanup commit (engine re-armed under its
  never-removed cron line) + delete `# autonomous-task` lines; overview merge is additive and
  needs no revert.
- **[Hygiene]** Every dev task stages explicit paths only — never `git add -A` (dirty
  worktrees with unrelated artifacts exist).
