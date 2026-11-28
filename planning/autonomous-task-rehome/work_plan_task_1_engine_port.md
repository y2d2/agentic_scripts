# Task Plan: Port evolved roadmap-dev engine into autonomous_task_overview

**Task:** #1    **Plan:** `autonomous-task-rehome`    **Repo:** `/workspace/Python/autonomous_task_overview`

## Objective

Bring the CURRENT live engine (`agentic_scripts` HEAD `745e6a9`) into the overview repo as
`autonomous_task.workflows.roadmap_dev`, add the `local_listing` config support the evolved
module needs, sync `roadmap_prompts` to the live values, on new branch `feature/rehome-final`.

## Context

- Source (read-only): `/workspace/Python/agentic_scripts`, branch `feature/roadmap-dev-workflow`.
  Evolved features vs the overview's Nov-24 copy: `task_done_labels` helper; 3-col
  details/checklist renderer; `local_listing` mirror of the listing into the project root;
  per-plan-section renderer (shared ancestor).
- Target `config/workflows.yaml` already has `listing_repo: y2d2/autonomous_task_overview`,
  `listing_path: plans.md`, `listing_branch: main`; it LACKS `local_listing` and its
  `allowed_repos` is the stale Nov-23 snapshot.
- Primitives (`agent.py`, `git.py`, `state.py`, `sessions.py`, `logging_setup.py`,
  `workflows/base.py`) already exist in the target and were byte-identical at the previous
  port; verify, do not rewrite them.

## Steps

1. In the overview clone: `git fetch origin && git checkout main && git pull`. Verify clean
   tree. Create `feature/rehome-final` from `main`; `git push -u origin feature/rehome-final`.
2. Copy `agentic_scripts/src/agentic_scripts/workflows/roadmap_dev.py` →
   `autonomous_task/src/autonomous_task/workflows/roadmap_dev.py` applying ONLY the mechanical
   rewrite `s/agentic_scripts/autonomous_task/g`. Freeze-check:
   `diff <(sed 's/agentic_scripts/autonomous_task/g' <source>) <target>` must be EMPTY.
3. `src/autonomous_task/config.py`: transplant the `local_listing: str | None` field
   (+ loader line + docstring) from `agentic_scripts/src/agentic_scripts/config.py` into the
   existing `RoadmapPrompts` dataclass/loader, matching the transplant pattern of commit
   `b063a74`/`092aeae` (read those diffs with `git show` in the source repo).
4. `config/workflows.yaml`: replace the whole `roadmap_prompts:` section with the LIVE
   section from `agentic_scripts/config/workflows.yaml` (9 `allowed_repos` incl.
   `y2d2/agentic_scripts`, `run_timeout_minutes`, `test_commands`, `repo_urls`), EXCEPT set
   `listing_repo: y2d2/autonomous_task_overview` and add `local_listing: plans.md`.
   Do not touch any other config section.
5. Smoke check (no commits yet):
   - `uv run python -c "from autonomous_task.workflows.roadmap_dev import create"` → exit 0.
   - config load snippet resolving `roadmap_prompts.local_listing == "plans.md"` → exit 0.
   - `uv run ruff check src config` clean on changed files.
6. Commit ONLY those paths: message `OC: Port evolved roadmap-dev engine from agentic_scripts (done-labels, 3-col checklist, local_listing) + config sync`. Push.

## Acceptance criteria

| # | Check | Pass condition |
|---|---|---|
| 1 | Freeze check | `diff <(sed ...)` empty for roadmap_dev.py |
| 2 | Import | `create` imports, exit 0 |
| 3 | Config | loads; `local_listing == "plans.md"`; `listing_repo == "y2d2/autonomous_task_overview"`; 9 allowed_repos incl. `y2d2/agentic_scripts` |
| 4 | Lint | ruff clean on changed files |
| 5 | Git | one commit on `feature/rehome-final`, pushed; `git status` clean; no other files staged |

## Out of scope

No test changes, no docs changes, no runner/CLI changes.
