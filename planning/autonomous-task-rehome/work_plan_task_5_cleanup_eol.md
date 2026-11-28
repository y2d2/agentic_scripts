# Task Plan: agentic_scripts — provenance commit + roadmap-dev removal + README EOL banner

**Task:** #5    **Plan:** `autonomous-task-rehome`    **Repo:** `/workspace/Python/agentic_scripts` (branch `feature/roadmap-dev-workflow`)
**Runs ONLY after the user's cutover-gate approval of Task 4's evidence.**

## Objective

Remove roadmap-dev entirely from this repo, publish a README EOL notice pointing to
`y2d2/autonomous_task_overview`, commit the untracked planning artifacts as provenance first,
and keep the remaining suite (noop/mail-keeper/oc-todo) green.

## Steps

1. **Provenance commit (first, separate commit):** stage EXPLICIT paths only:
   `planning/autonomous-task-repo-move/`, `planning/archived/listing-detail-row-and-workflow-diagram/`,
   `planning/archived/plans-md-details-checklist/`, `planning/autonomous-task-rehome/` (this
   plan folder incl. any result files already present). Commit
   `OC: Archive migration + re-home planning provenance`. (Never `git add -A`.)
2. **Deletions:** `git rm` —
   `src/agentic_scripts/workflows/roadmap_dev.py`,
   `tests/test_roadmap_dev.py`, `tests/test_roadmap_dev_scan.py`,
   `tests/test_roadmap_dev_pipeline.py`, `tests/test_roadmap_dev_listing_mirror.py`,
   `tests/smoke/test_smoke_roadmap_dev.py`, `plans.md`.
3. **Config:** `config/workflows.yaml` — delete the `roadmap_prompts:` section and the
   `workflows.roadmap-dev:` entry (noop/mail-keeper/oc-todo entries byte-identical, `admin_repo`
   stays). `src/agentic_scripts/config.py` — revert the transplanted `RoadmapPrompts`
   dataclass/loader/kwarg/docstring refs (pattern: the pre-`b063a74` shape; `git show b063a74^`
   is the reference).
4. **Shared test fixes:** remove/retarget roadmap references in `tests/conftest.py`,
   `tests/test_config.py`, `tests/smoke/conftest.py`, `tests/smoke/test_smoke_base.py`,
   `tests/smoke/test_smoke_mail_keeper.py`, `tests/smoke/test_smoke_oc_todo.py` (e.g. hermetic
   `roadmap_prompts` lines become unnecessary; any `--only roadmap-dev` test retargeted to a
   synthetic fixture per the last cleanup's pattern in `planning/autonomous-task-repo-move/
   lightweight_dev_task_6_cleanup.md`).
5. **README EOL banner:** add at the very top of `README.md` (before everything else):
   > ⚠️ **Autonomous task execution has MOVED.** The roadmap-dev engine (plan scan →
   > `plans.md` listing → idle-time execution) now lives and develops EXCLUSIVELY in
   > **`git@github.com:y2d2/autonomous_task_overview.git`** (`/workspace/Python/
   > autonomous_task_overview`). Do NOT develop roadmap/plans-engine features in this repo —
   > changes here are dead code and will be lost. This repo now hosts only the `noop`,
   > `mail-keeper`, and `oc-todo` workflows. (Moved 2026-11-28; history in
   > `planning/autonomous-task-rehome/`.)
   Also delete the old roadmap-dev README section (`e228c7c`).
6. **Remove root listing from remote main (one-off):** on a throwaway branch from `origin/main`,
   `git rm plans.md`, commit `OC: Remove plans.md — listing moved to autonomous_task_overview`,
   push to `main` per repo convention; return to `feature/roadmap-dev-workflow`.
7. **Verify:** `grep -rn roadmap src/ tests/ config/ scripts/` → ZERO hits (README banner
   line excepted). `uv run pytest tests/ -q` green. `uv run ruff check src tests config` clean.
8. Commit step 2–5 paths: `OC: Remove roadmap-dev — moved permanently to y2d2/autonomous_task_overview (+ README EOL banner)`. Push.

## Acceptance criteria

| # | Check | Pass condition |
|---|---|---|
| 1 | Provenance commit | exists, contains ONLY the 4 listed planning paths |
| 2 | Zero refs | grep for `roadmap` in src/tests/config/scripts = 0 hits (banner excepted) |
| 3 | Suite | `uv run pytest tests/ -q` exit 0 (mail/todo/noop suites intact, none deleted) |
| 4 | Lint | ruff clean |
| 5 | README | EOL banner is the first content block; roadmap-dev section removed |
| 6 | main | `y2d2/agentic_scripts` main no longer contains `plans.md` |
| 7 | Git | exactly 2 commits from this task (provenance + removal) (+ the one-off main commit); all pushed; `crontab` UNTOUCHED |

## Out of scope

No crontab changes. No changes to mail-keeper/oc-todo/noop behavior. No scheduler/gate code
removal (dormant idle-gate machinery stays).
