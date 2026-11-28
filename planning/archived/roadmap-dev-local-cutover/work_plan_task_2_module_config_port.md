# Task Plan: Port roadmap_dev module + config + yaml

**Task:** #2    **Session:** roadmap-dev-local-cutover

## Objective

Restore the `roadmap-dev` workflow into the `agentic_scripts` package by porting the current evolved version from the `autonomous_task_overview` repo (module + `RoadmapPrompts` config support + YAML entries), gated by the session-based idle gate. After this task the workflow resolves and the package imports cleanly; no behavior changes to the ported logic (listing-destination changes come in Task 3).

## Context

- **Repo:** `/workspace/Python/agentic_scripts`, branch `feature/roadmap-dev-workflow` (tracks origin). Commit with `OC:` prefix, push. Stage explicit paths only — there are untracked `planning/*` files that must stay untouched.
- **Port source:** `/workspace/Python/autonomous_task_overview` (package `autonomous_task`), branch `feature/listing-detail-row` @ `899ce44`. Read it; never modify it.
- **Verified equivalence:** `git.py`, `agent.py`, `state.py`, `workflows/base.py`, `sessions.py` are byte-identical between the two repos after renaming `autonomous_task`→`agentic_scripts`. Every `Git`/`AgentRunner`/`StateStore`/`WorkContext` member used by `roadmap_dev.py` exists here. Only `config.py` diverges (here it lost `RoadmapPrompts` in this repo's commit `80e0820`).
- **Gate support already present here:** `config.py` `Workflow` dataclass has `gate: str = "quiet_window"` accepting `"quiet_window"` or `"idle"` (validated); `scheduler.py` evaluates the idle gate via `sessions.read_active_sessions()` and runs `gate: idle` workflows even when the quiet gate is closed. No scheduler changes are needed.
- **Executor:** `roadmap_dev.py` hardcodes `_AGENT_NAME = "planner-enhanced"` — the agent exists globally; do not touch.
- The workflow module exposes `create(config) -> Workflow` (scheduler entry-point contract, mirrors `oc_todo.py`).

## Tasks

### Task 1: Copy the module with import rewrite
- **Files:** `src/agentic_scripts/workflows/roadmap_dev.py` (create).
- **Do:** copy `/workspace/Python/autonomous_task_overview/src/autonomous_task/workflows/roadmap_dev.py` verbatim, rewriting every occurrence of the module path token `autonomous_task` → `agentic_scripts` (imports `from autonomous_task.agent import AgentResult`, `.config`, `.git`, `.workflows.base`, and docstring/doctest references). No logic edits, no formatting reflow.
- **Acceptance:**
  1. `cd /workspace/Python/agentic_scripts && uv run python -c "import agentic_scripts.workflows.roadmap_dev as m; assert callable(m.create)"` exits 0 (after Task 2 lands config — if run before, expect only the `RoadmapPrompts` ImportError).
  2. `diff <(sed 's/agentic_scripts/PKG/g' src/agentic_scripts/workflows/roadmap_dev.py) <(sed 's/autonomous_task/PKG/g' /workspace/Python/autonomous_task_overview/src/autonomous_task/workflows/roadmap_dev.py)` is empty.

### Task 2: Transplant RoadmapPrompts into config.py
- **Files:** `src/agentic_scripts/config.py` (modify).
- **Do:** from the AT `config.py` (`/workspace/Python/autonomous_task_overview/src/autonomous_task/config.py`), transplant, adapted to this file's existing style/sections:
  1. The `RoadmapPrompts` frozen dataclass (docstring included; rewrite package refs) with its fields: `allowed_repos: list[str]`, `listing_repo: str`, `listing_repo_url: str`, `listing_path: str`, `listing_branch: str`, `run_timeout_minutes: int`, `test_commands: dict[str, str]`, `repo_urls: dict[str, str]` — copy the AT field set exactly as present at 899ce44.
  2. Its loader/validation function mirroring the existing `_load_*` helpers (unknown-key rejection, types, non-empty `listing_repo`/`listing_path`/`listing_branch`, `run_timeout_minutes > 0`, `test_commands`/`repo_urls` keys ⊆ `allowed_repos` — whatever AT validates, keep identical).
  3. Wire `roadmap_prompts` as a top-level optional section: absent key → `None` (or AT's default-empty behavior — match AT exactly), and `Config.roadmap_prompts` field on the dataclass.
- **Notes:** Do NOT add `local_listing` (introduced in Task 3). Do NOT remove/alter existing sections (`admin_repo`, `oc_todo`, `agent`, `machine`, `paths`, `workflows`).
- **Acceptance:**
  1. `uv run python -c "from agentic_scripts.config import RoadmapPrompts, Config"` exits 0.
  2. With the current (pre-yaml-change) `config/workflows.yaml`, config still loads unchanged (section absent → default), i.e. `uv run python -c` invoking this repo's config-load entry (as used by `cli.py`) exits 0.

### Task 3: Add yaml sections
- **Files:** `config/workflows.yaml` (modify).
- **Do:** append the `roadmap_prompts:` section (place it after `admin_repo:`/before `oc_todo:`, mirroring the pre-removal layout `git show 80e0820^:config/workflows.yaml`) with exactly:
  - `allowed_repos:` the 9 entries in AT order: `y2d2/ARP_MPE`, `y2d2/ARP_implementations`, `y2d2/ARP_1A_anchored_implementations`, `y2d2/ARP_utility_code`, `y2d2/PRP_ARP_M`, `y2d2/ARP_IMU`, `y2d2/agentic_scripts`, `y2d2/ARP_roadmap`, `y2d2/ARP_engine`
  - `listing_repo: y2d2/agentic_scripts`   ← deliberately repointed from `y2d2/autonomous_task_overview`
  - `listing_repo_url: ""`, `listing_path: plans.md`, `listing_branch: main`, `run_timeout_minutes: 480`, `test_commands: {}`, `repo_urls: {}`
  and append under `workflows:` a fourth entry:
  ```yaml
  roadmap-dev:
    enabled: true
    module: agentic_scripts.workflows.roadmap_dev
    agent: planner-enhanced
    gate: idle
  ```
  Keep `noop`, `mail-keeper`, `oc-todo` entries byte-identical (same order, same comments).
- **Acceptance:**
  1. Config loads with the new yaml: `uv run python -c "from agentic_scripts.config import load_config; ..."` (use the real loader symbol from `config.py`) exits 0 and `config.roadmap_prompts.allowed_repos` has 9 entries, `listing_repo == 'y2d2/agentic_scripts'`.
  2. Workflow resolution: scheduler's enabled-workflow resolution (as `scheduler.list_enabled` does) imports `agentic_scripts.workflows.roadmap_dev` successfully; `roadmap-dev` entry has `gate == 'idle'`, `agent == 'planner-enhanced'`.

### Task 4: Regression + lint + commit
- **Do:** `uv run pytest tests/ -q` (must be fully green — existing tests must not regress); `uv run ruff check src config`; commit ONLY the three changed/created files + push: `OC: Port roadmap-dev workflow back from autonomous_task_overview (module, config, yaml entry, gate: idle)`.
- **Acceptance:**
  1. pytest PASS, 0 failures/errors.
  2. ruff clean on changed files.
  3. Commit contains exactly `src/agentic_scripts/workflows/roadmap_dev.py`, `src/agentic_scripts/config.py`, `config/workflows.yaml` (`git show --stat`); pushed.

## Out of Scope

- Listing-destination/`local_listing` changes (Task 3 of the global plan).
- Test files for roadmap-dev (next global task), README, scheduler changes, AT repo changes.
- Running the workflow for real (`uv run agentic-scripts run`) — forbidden here: a forced/idle run could spawn plan executions.

## Notes

- If the ported module references any config symbol absent from this repo's `config.py` after the transplant, fix by porting that symbol from AT `config.py` too (same rules) and record it in the result report.
- pyproject dependencies are expected identical; if the module's imports fail on a third-party package, report as blocker (do not add deps without noting).
