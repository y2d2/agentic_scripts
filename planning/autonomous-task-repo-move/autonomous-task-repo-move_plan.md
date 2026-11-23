# Autonomous Task → Overview Repo: Move, Workflow Analysis, and Variables File

**Purpose:** Make `y2d2/autonomous_task_overview` the single, self-contained home of the autonomous task (roadmap-dev): engine, scripts, docs, workflow analysis, and a variables file.

## Objective

Move every script and required file of the roadmap-dev ("autonomous task") workflow out of
`agentic_scripts` and into the `y2d2/autonomous_task_overview` repo, so that repo alone
defines, documents, and runs the unattended plan-execution engine. The server's 30-minute
timer will then run the engine from a persistent clone of the overview repo;
`agentic_scripts` keeps only mail-keeper, oc-todo, and their shared primitives.
Deliverables: (1) the relocated, standalone engine that reconciles `plans.md`
byte-identically and keeps all 78 state entries; (2) a `WORKFLOW.md` that splits the
pipeline into its script-executed parts and its LLM-executed parts; (3) a `VARIABLES.md`
with the full first proposal of every variable.

## Context

- The engine today runs from `/workspace/Python/agentic_scripts` (package
  `agentic_scripts`): `workflows/roadmap_dev.py` (3,356 lines) on shared primitives
  `agent.py` (AgentRunner), `git.py` (Git), `sessions.py` (idle probe), `state.py`,
  `config.py`, `scheduler.py`, `workflows/base.py`, CLI — driven by cron
  `*/30 * * * *` installed by `scripts/setup.sh`, configured in
  `config/workflows.yaml` (`machine`, `agent`, `paths`, `roadmap_prompts`,
  `workflows.roadmap-dev` sections) (local: `README.md`, `config/workflows.yaml`).
- The overview repo (`y2d2/autonomous_task_overview`, `main` @ `110c648`) currently holds
  only `README.md` (plan-authoring guide) + `plans.md` (78-row live listing), and is
  reconciled/pushed by the engine on every fire. It is a vault submodule for Obsidian
  visibility.
- The project's own convention is workflow self-containment: "there are no
  cross-workflow imports (each workflow module is self-contained)" — small helpers are
  copied, not shared (local: `roadmap_dev.py` docstrings on `extract_report_sections` /
  `clone_env_for`). A standalone engine package in the overview repo follows this
  established pattern.
- LLM side: headless `opencode run --standalone --agent planner-enhanced --format json`
  spawns the orchestrator, which dispatches `@lightweight-dev` per task; agent
  definitions live in `~/.config/opencode/agents/` and stay there (user decision
  2026-11-23). Runner verified against OpenCode v2.3.2 (research cache:
  `/workspace/Research/ai-agent-workflow/opencode-2x-run-headless.md`).
- User decisions (2026-11-23): **full engine move** into the overview repo; agent
  definitions are **not** versioned in the repo — they stay in the global OpenCode
  config and are documented in the variables file.

## Functional Tasks

### Task 1: Standalone engine package in the overview repo

- **Goal:** The overview repo contains a runnable Python project: the roadmap-dev
  workflow moved in full, plus the primitives it needs (agent runner, git helper,
  idle-session probe, state store, config loader trimmed to `machine`/`agent`/`paths`/
  `roadmap_prompts`, base protocol, single-workflow runner with the idle gate + lock +
  run-id + logging, CLI entry point), a `pyproject` (uv project), the trimmed config
  file, and the roadmap-dev test suite.
- **Why this approach:**
  - **[Decision: standalone package vs agentic_scripts dependency]** Value = standalone
    package with its own copies of the needed primitives because the overview repo must
    be cloneable and runnable anywhere without a second repo, and the project already
    self-contains workflows by copying rather than cross-importing (local:
    `roadmap_dev.py` docstring convention). The ~2.5 k lines of duplicated primitives
    are frozen leaf copies; drift is a documented, accepted risk. Rejected alternative:
    importing `agentic_scripts` by path would couple the repos' versions and break the
    "single home" property.
  - **[Decision: scheduler trimming]** Value = a single-workflow runner (idle gate +
    lock + run-id + logging, ~1 order of magnitude smaller than the multi-workflow
    `scheduler.py`) because after the move the engine runs exactly one workflow; the
    quiet-window gate and multi-workflow loop belong to `agentic_scripts` and are not
    needed here. (Own analysis.)
  - **[Decision: listing clone]** Value = keep the engine's separate listing clone under
    its sandbox (unchanged behavior) rather than reading `plans.md` from its own
    checkout, to avoid mixing engine-code checkout with workflow listing writes.
    (Local: `_reconcile_and_push` retry contract assumes a dedicated clone.)
- **Acceptance criteria:**
  - A fresh clone of the overview repo + its setup script yields a green test run of
    the moved roadmap-dev suite (pure core, scan, pipeline, smoke) with no reference to
    `agentic_scripts`.
  - `run --force` from the new location performs a phase-1 scan of the 9 allowlisted
    repos and pushes a byte-identical `plans.md` (no diff), with all 78 state entries
    intact.
  - The engine still: reconciles user-owned cells, runs the drain (1 day / 2 night
    slots), enforces the 480-min per-job kill, and never calls the GitHub API (all git
    over SSH).

### Task 2: Docs — workflow analysis + variables file (repo root)

- **Goal:** Two new root-level files in the overview repo: `WORKFLOW.md` (the
  scripts-vs-LLM split, written as an operator-facing analysis) and `VARIABLES.md`
  (every variable the task uses, with the first proposal below); `README.md` updated to
  say the repo is now the full home of the autonomous task.
- **Why this approach:**
  - **[Decision: WORKFLOW.md as separate file]** Value = a dedicated `WORKFLOW.md`
    rather than a README section because the README stays the plan-authoring guide (its
    current, proven role) while the analysis is operator/maintainer material of
    comparable size. (Own analysis.)
  - **[Decision: variables as documentation-first]** Value = `VARIABLES.md` documents
    the variable set (name, value, where set, meaning, who may change it) before any
    code refactor of the constants it recommends; the code keeps its current
    constant/config split until a follow-up decides otherwise. (Own analysis — the user
    asked for a first proposal, not a config refactor.)
- **Acceptance criteria:**
  - `WORKFLOW.md` correctly attributes every pipeline step to either "script
    (deterministic)" or "LLM (headless OpenCode)" — in particular: timer/gate/lock/
    scan/identity/reconcile/push/slots/drain/job-start/report-routing/tests-gate/
    commit/archive/push are script; plan review, major-question decisions, task
    execution, acceptance-criteria verification, result reports are LLM
    (`planner-enhanced` + `lightweight-dev`); and the boundary rule "LLM never
    commits/pushes; script never makes implementation decisions" is explicit.
  - `VARIABLES.md` contains the full variable table below, is committed, and passes a
    user review.

**First proposal for `VARIABLES.md`** (grouped; each row: variable, value, where set,
meaning, owner):

**A. Scheduling & gate** (config `machine.*` / engine constants)

| Variable | Value | Where | Meaning | Owner |
|---|---|---|---|---|
| `quiet_window.start` / `.end` | `22:00` / `08:00` | config | Defines "night" (crosses midnight) → drives slot count | operator |
| `poll_interval_minutes` | `30` | config | Timer cadence; drain re-scan cadence while jobs run | operator |
| `gate_polls_required` | `2` | config | Consecutive idle polls needed to open the idle gate | operator |
| `gate_poll_tolerance_minutes` | `10` | config | Max gap between consecutive idle polls | operator |
| `day_slots` / `night_slots` | `1` / `2` | **code constant** (proposal: promote to config) | Concurrent jobs by day / by night | operator (proposed) |
| `run_timeout_minutes` | `480` | config `roadmap_prompts.*` | Per-job hard budget; expiry = process-group kill → `failure` | operator |
| `tests_gate_timeout_seconds` | `600` | **code constant** (proposal: promote) | Timeout for the success-path tests gate | operator (proposed) |
| `job_join_timeout_seconds` | `15` | code constant | Bounded join-poll while waiting for a job | engine |

**B. Agent runner** (config `agent.*`)

| Variable | Value | Where | Meaning | Owner |
|---|---|---|---|---|
| `binary` | `opencode` | config | Executable the runner spawns | operator |
| `model` | `llama-cpp/Qwen3.8-27B` | config | Model passed to `opencode run --model` | operator |
| `max_steps` | `80` | config | Informational mirror of the agent frontmatter budget knob | operator |
| `timeout_minutes` | `180` | config | Default per-run agent timeout (roadmap-dev overrides per job with `run_timeout_minutes`) | operator |
| `auto_approve` | `true` | config | Passes `--auto` to `opencode run` | operator |
| `orchestrator_agent` | `planner-enhanced` | config workflow entry | Headless agent that reviews + executes the plan | operator |
| `worker_agent` | `lightweight-dev` | **in brief text** (proposal: promote to config) | Sub-agent dispatched per task | operator (proposed) |

**C. Repo surface** (config `roadmap_prompts.*`)

| Variable | Value | Where | Meaning | Owner |
|---|---|---|---|---|
| `allowed_repos` | 9 repos | config | Repos scanned for plans; empty = no-op | operator |
| `listing_repo` | `y2d2/autonomous_task_overview` | config | This repo — home of `plans.md` | operator |
| `listing_repo_url` | `""` | config | Clone-URL override (`""` → SSH derive; local path = test seam) | operator |
| `listing_path` / `listing_branch` | `plans.md` / `main` | config | Listing file + branch | operator |
| `repo_urls` | `{}` | config | Per-repo clone-URL override (hermetic-test seam) | operator |
| `test_commands` | `{}` | config | Per-repo test command the success gate runs | operator |

**D. Plan-discovery contract** (code constants — documented so operators know the invariants)

| Variable | Value | Meaning |
|---|---|---|
| planning root / plan marker | `planning/` / `work_plan.md` | A plan = `planning/<topic>/work_plan.md` |
| archived segment | `archived` | Folders under it are never discovered |
| diagnostic files | `questions.md`, `failure.md` | Excluded from identity hashing; the review/re-arm surface |
| attempt-branch prefix | `roadmap-dev/<id>-<n>` | Fresh-branch-only push invariant |
| state schema version | `1` | `state/roadmap-dev.json` (no migration; delete to re-bootstrap) |
| commit prefix | `OC:` | All engine commits (listing, archive, diagnostics) |
| listing columns | `approval, priority, plan, title, state, remove` | User-owned: approval/priority/remove (+ `failure`→`open` re-arm); workflow-owned: title/state |
| state values | `open, pending, review, success, failure` | State machine (see README) |

**E. Runtime paths** (config `paths.*`, gitignored)

| Variable | Value | Meaning |
|---|---|---|
| `state_dir` / `log_dir` / `sandbox_dir` | `state` / `logs` / `sandbox` | Engine-relative runtime dirs |
| sandbox layout | `clones/<owner>__<name>`, `wt/<…>/<identity>`, `diag/<…>/<identity>`, `prompts/` | Clones, execution worktrees, diagnostics worktrees, listing clone |
| state file | `state/roadmap-dev.json` | Per-plan machine bookkeeping (identity, state, attempt, pid, branch, sha, last error) |

**F. Environment variables**

| Variable | Required | Meaning |
|---|---|---|
| `GITHUB_PAT` | no (SSH default) | Only for HTTPS-mirror clones via `repo_urls`; never in config or git |

**G. LLM agent knobs** (global OpenCode config — documented, not versioned here per user decision)

| Agent | Knobs |
|---|---|
| `planner-enhanced` | model `llama-cpp/Qwen3.8-27B`, temperature `1.0`, top_p `0.95` |
| `lightweight-dev` | model `llama-cpp/Qwen3.8-27B`, temperature `0.7`, top_p `0.80`, thinking off, presence penalty `1.5` |

### Task 3: Server rewiring + `agentic_scripts` cleanup

- **Goal:** The server runs the autonomous task only from the overview-repo clone:
  persistent clone at `/workspace/Python/autonomous_task_overview` (sibling of
  `agentic_scripts`), the engine's own setup script installs the 30-min cron entry (and
  systemd units for real hosts), runtime dirs + `.env` handled as today; one-time
  migration of `state/roadmap-dev.json` (and sandbox clones, optional) into the new
  engine's dirs; `agentic_scripts` loses the roadmap-dev workflow entirely (module,
  config entry, preflight, README section) so no second process can ever reconcile the
  same listing.
- **Why this approach:**
  - **[Decision: full removal vs disable in agentic_scripts]** Value = remove module +
    entry (not just `enabled: false`) because the two engines would use different lock
    files and state files — a "disabled-but-present" engine is a maintenance trap and a
    double-push hazard for `plans.md`. (Own analysis.)
  - **[Decision: sibling clone path]** Value = `/workspace/Python/autonomous_task_overview`
    because it is persistent and visible (the sandbox is scratch and must never hold the
    running checkout). (Own analysis.)
  - **[Decision: state migration by copy]** Value = one-time copy of
    `state/roadmap-dev.json` (all 78 entries are `open`/attempt 0 today) rather than
    re-bootstrap, so forensics and attempt numbering survive unchanged (local:
    `state/roadmap-dev.json`).
- **Acceptance criteria:**
  - After cutover, exactly one cron entry fires the engine (from the overview clone);
    `agentic_scripts` runs its remaining workflows with a green suite and its README no
    longer describes roadmap-dev as live.
  - A scheduled (gate-checked) fire from the new location logs a phase-1 run with zero
    errors; the listing is unchanged (byte-identical).
  - An approved row ☑'d on `plans.md` starts a drain job from the new location exactly
    as before (verified with a forced drain or a live overnight window).

### Task 4: Verification & cutover gate

- **Goal:** Proven end-to-end before the old engine is deleted: moved suite green in
  both repos, byte-identical reconcile from the new location, state intact, no double
  engine, and a rollback path (old engine can be re-armed by re-adding its cron line —
  but only after the new one is confirmed).
- **Acceptance criteria:** Both suites green; `last-run.txt` from the new location shows
  `roadmap-dev=ok`; `plans.md` remote tip is byte-identical pre/post cutover; user
  confirms cutover via a gate question before `agentic_scripts` cleanup commits land.

## Alternatives Considered

1. **Supporting files only (engine stays in agentic_scripts)** — Rejected by user choice
   (2026-11-23); leaves the "single home" goal unmet and the overview repo cannot be
   cloned + run standalone.
2. **Engine as synced copy (submodule/sync into agentic_scripts)** — Rejected (user
   chose full move): a sync mechanism is a new standing failure mode; the
   self-contained-package convention already exists in this codebase.
3. **Version agent definitions in the repo + install step** — Rejected by user choice
   (2026-11-23); agents stay in `~/.config/opencode/agents/` and are documented in
   `VARIABLES.md` §G.
4. **Engine reads `plans.md` from its own checkout** — Rejected: mixing engine-code
   checkout with workflow listing writes muddies the non-fast-forward retry path that
   assumes a dedicated clone (local: `_reconcile_and_push`).

## Notes

- **[Assumption]** The overview repo is not (and should not become) an
  `allowed_repos` entry: the engine must never scan its own docs for plans (docs stay
  at repo root, never under `planning/`).
- **[Risk]** Drift between the duplicated primitives and their `agentic_scripts`
  originals — accepted; the copies are frozen leaf code and the engine is a terminal
  consumer.
- **[Risk]** Cutover while a job is in flight would orphan it (the reaper flips
  `pending`→`open` on the next run of whichever engine owns it) — all 78 rows are
  currently unapproved (no drain possible), so cutover should land in an
  unapproved-only window, which is the current state (local:
  `state/roadmap-dev.json`, live listing clone).
- **[Assumption]** Entry-point and package names (e.g. `ato` / `autonomous_task`) are
  placeholders for the refiner-orchestrator to finalize; behavior is name-agnostic.
