# Task Plan: WORKFLOW.md + VARIABLES.md + README update

**Purpose:** Write the two operator docs for the standalone engine — `WORKFLOW.md`
(the scripts-vs-LLM pipeline split) and `VARIABLES.md` (every variable, first proposal) —
and update the repo README to say the repo is now the full home of the autonomous task.

## Objective

In `/workspace/Python/autonomous_task_overview` (branch `feature/engine-move`; engine
package + tests + setup infra already landed), create `WORKFLOW.md` and `VARIABLES.md`
at the repo root and update `README.md`'s framing. End state: `WORKFLOW.md` attributes
every pipeline step to script or LLM with the boundary rule explicit; `VARIABLES.md`
carries the full variable tables below (values verified against the code); the README
presents the repo as the single home (engine + docs + live listing) while keeping its
plan-authoring-guide role.

## Context

- **Target repo:** `/workspace/Python/autonomous_task_overview`, branch
  `feature/engine-move` (pushed). Layout: `src/autonomous_task/` (`runner.py` =
  single-workflow runner: parse → config → dotenv → logger → `acquire_lock` (flock) →
  `evaluate_idle_gate` (session probe, `idle_gate_last_ok` streak in
  `state/scheduler.json`) → `WorkContext` → workflow; `workflows/roadmap_dev.py` = the
  3,356-line workflow; `agent.py` = `AgentRunner` (spawns
  `opencode run --standalone --agent planner-enhanced --format json` with a
  process-group kill on timeout); `git.py` = Git helper (pure git, all SSH by default);
  `sessions.py` = idle probe (OpenCode service state + HTTP); `state.py` = `StateStore`;
  `config.py` + `config/workflows.yaml` (trimmed); `scripts/setup.sh` (with
  `--skip-timer`); `systemd/` units; `plans.md` = the LIVE listing (engine-owned,
  reconciled + pushed to `main` every fire); `state/roadmap-dev.json` = per-plan
  bookkeeping (82 entries today, all `open`, attempt 0).
- **Pipeline facts (verified against the code — use them verbatim in the analysis):**
  - `runner.py`: timer fire (cron `*/30` installed by `setup.sh`), `--force` operator
    bypass, flock lock (concurrent-fire skip), run-id + per-run log
    (`logs/run-<id>.log`) + `logs/last-run.txt`, idle gate (0 active OpenCode sessions,
    2 consecutive polls within `poll_interval + tolerance`; streak key
    `idle_gate_last_ok`; `--force` → gate open).
  - `roadmap_dev.py` phase 1 (every run, gate-independent): reaper
    (`_reap_orphans` — dead `pending` jobs flip back to `open` + worktree cleanup),
    scan (`_scan_and_reconcile` → per-repo clone/fetch under
    `sandbox/roadmap-dev/clones/<owner>__<name>`, every remote branch except
    `roadmap-dev/*`, plans = `planning/<topic>/work_plan.md` minus `archived/`,
    identity = 16-hex hash of repo+branch+path+content-hash), identity/
    `plan_folder_hash` (excludes `questions.md`/`failure.md` — the diagnostic
    files), listing parse/render (`LISTING_COLUMNS = approval, priority, plan, title,
    state, remove` + the workflow-owned goal/task detail row), `reconcile()`
    (user-owned cells — `approval` ☑, numeric `priority`, `remove` ☑, `failure`→`open`
    re-arm — are NEVER clobbered; workflow-owned `title`/`state` + detail row are
    rewritten), `_reconcile_and_push` (commit + push in the dedicated listing clone
    `sandbox/roadmap-dev/prompts`; one non-fast-forward retry: fetch, re-render,
    re-commit, re-push).
  - Drain (only when the idle gate is open): `_slots` = 1 by day / 2 inside
    `machine.quiet_window` (22:00–08:00, crosses midnight), recomputed each iteration;
    `_select_startable` (approved ☑ rows, priority order, not already running);
    `_start_job` → attempt worktree `sandbox/roadmap-dev/wt/<owner>__<name>/<identity>`
    on a fresh branch `roadmap-dev/<id>-<n>` cut from the plan's branch; brief
    (`render_brief`) embeds "Dispatch @lightweight-dev ONE small self-contained task";
    spawn = headless `planner-enhanced` (code constant `_AGENT_NAME`), per-job hard
    budget `run_timeout_minutes` (480) → `AgentRunner` process-group SIGKILL →
    `failure`; top-up loop (slots kept full; in-flight jobs finish when the probe
    reports the gate closed — no preemption; bounded join-poll
    `job_join_timeout_seconds = 15`); outcome routing `_route_job`:
    `extract_report_sections`/`job_status_from_report` parse the agent's final text →
    success path runs the per-repo `test_commands` under
    `_TESTS_GATE_TIMEOUT_SECONDS = 600` (tests gate), then commits + `git mv`-archives
    the plan folder to `planning/archived/<topic>` and pushes the attempt branch (NO
    PR — a human opens/verifies/merges); questions/failure/timeout paths write
    `questions.md`/`failure.md` via diag worktrees (`sandbox/roadmap-dev/diag/...`) and
    `OC:` diagnostic commits on the plan's branch. State machine:
    `open → pending → review | success | failure` (re-arm `failure → open` is
    user-owned in the listing). ALL engine commits are `OC:`-prefixed.
  - LLM side: `planner-enhanced` (orchestrator: plan review, major-question decisions,
    dispatching `@lightweight-dev` per task) + `lightweight-dev` (task execution,
    acceptance-criteria verification, result reports). Agent definitions live in
    `~/.config/opencode/agents/` (global OpenCode config — deliberately NOT versioned in
    this repo, user decision 2026-11-23). OpenCode v2.3.2 (runner verified against it;
    research cache: `/workspace/Research/ai-agent-workflow/opencode-2x-run-headless.md`).
  - **Boundary rule (must be stated explicitly in WORKFLOW.md):** the LLM never
    commits or pushes (it works in the attempt worktree; the script owns every
    commit/push — attempt branch, archive, diagnostics, listing reconcile); the script
    never makes implementation decisions (it executes the reviewed plan; all
    code-level choices are the agents').
- **Git conventions:** `OC:` prefix; explicit staging; never touch/commit `plans.md`.
- **Docs style:** operator-facing, concise, code-located (cite module/function names);
  no marketing. Markdown tables where the data is tabular.

## Tasks

### Task 1: `WORKFLOW.md`
- **Files:** `WORKFLOW.md` (create, repo root)
- **Do:** Write the operator-facing analysis, structured as:
  1. **What this is** — one paragraph: the repo is the single home of the unattended
     plan-execution engine; the 30-minute timer (cron/systemd) fires
     `autonomous-task run`; phase 1 always runs, the drain runs when the box is idle.
  2. **The pipeline split** — a table with columns `Step | Executed by | Where (code) |
     Notes`, with EVERY one of these rows attributed correctly:
     timer fire (script — cron entry from `scripts/setup.sh`); operator `--force`
     (script); idle gate (script — `runner.py:evaluate_idle_gate`, session probe);
     lock (script — `runner.py:acquire_lock`); run-id + logging (script —
     `runner.py` + `logging_setup.py`); phase-1 reaper (script); scan + plan discovery
     (script); identity hashing (script); listing parse/render (script);
     user-cell-preserving reconcile (script); listing commit + push w/ retry (script);
     slot computation 1 day / 2 night (script — `roadmap_dev.py:_slots`);
     startable selection (script); attempt worktree + fresh branch (script); brief
     rendering (script — `render_brief`); job spawn (script — `AgentRunner` launches
     headless OpenCode); **plan review + major-question decisions (LLM —
     `planner-enhanced`)**; **task execution (LLM — `lightweight-dev` dispatched per
     task)**; **acceptance-criteria verification + result reports (LLM)**; 480-min
     per-job kill (script — process-group SIGKILL); report routing (script —
     `_route_job` parses the LLM's final text); tests gate (script — runs
     `test_commands`, 600 s); success commit + archive + attempt-branch push (script);
     diagnostic commits for questions/failure (script — the content of
     `questions.md`/`failure.md` is LLM-authored); state persistence (script).
  3. **The boundary rule** — a dedicated subsection quoting the rule from Context
     verbatim, plus its consequence: the human PR is the final gate (the engine never
     opens PRs; attempt branches are reviewed + merged by a human).
  4. **Where each side runs** — the script runs from this repo's persistent clone; the
     LLM runs headless (`opencode run --standalone`) inside the attempt worktree with
     the global agent config (`~/.config/opencode/agents/`); the listing clone is a
     separate clone under the engine's sandbox (never this checkout).
  5. **Failure modes at a glance** — short table: gate closed → phase 1 only, drain
     note; job timeout → `failure` + diag commit + re-arm possible; non-fast-forward
     listing push → one retry; orphaned `pending` → reaper flips to `open` next run.
- **Acceptance:**
  1. Every step in the list in Context §2 appears in the split table, attributed exactly as specified (script steps never marked LLM and vice versa).
  2. The boundary rule sentence "the LLM never commits or pushes; the script never makes implementation decisions" (or a verbatim-equivalent) appears as a dedicated subsection.
  3. All code references (module + function names) resolve to real symbols in `src/autonomous_task/` (spot-check by grep).

### Task 2: `VARIABLES.md`
- **Files:** `VARIABLES.md` (create, repo root)
- **Do:** Write the first-proposal variable catalogue: intro paragraph (this is a
  documentation-first proposal — the code keeps its current constant/config split until
  a follow-up decides otherwise; "owner" = who may change the value), then these
  sections with these exact tables (values VERIFIED against the code 2026-11-23):

  **A. Scheduling & gate** (config `machine.*` / engine constants)

  | Variable | Value | Where | Meaning | Owner |
  |---|---|---|---|---|
  | `quiet_window.start` / `.end` | `22:00` / `08:00` | config `machine` | Defines "night" (crosses midnight) → drives the drain slot count | operator |
  | `poll_interval_minutes` | `30` | config `machine` | Timer cadence; drain re-scan cadence while jobs run | operator |
  | `gate_polls_required` | `2` | config `machine` | Consecutive idle polls needed to open the idle gate | operator |
  | `gate_poll_tolerance_minutes` | `10` | config `machine` | Max gap between consecutive idle polls | operator |
  | `day_slots` / `night_slots` | `1` / `2` | **code constant** (`roadmap_dev.py:_slots`, hardcoded) — proposal: promote to config | Concurrent jobs by day / by night | operator (proposed) |
  | `run_timeout_minutes` | `480` | config `roadmap_prompts` | Per-job hard budget; expiry = process-group kill → `failure` | operator |
  | `tests_gate_timeout_seconds` | `600` | **code constant** (`_TESTS_GATE_TIMEOUT_SECONDS`) — proposal: promote | Timeout for the success-path tests gate | operator (proposed) |
  | `job_join_timeout_seconds` | `15` | code constant | Bounded join-poll while waiting for a job | engine |

  **B. Agent runner** (config `agent.*`)

  | Variable | Value | Where | Meaning | Owner |
  |---|---|---|---|---|
  | `binary` | `opencode` | config `agent` | Executable the runner spawns | operator |
  | `model` | `llama-cpp/Qwen3.8-27B` | config `agent` | Model passed to `opencode run --model` | operator |
  | `max_steps` | `80` | config `agent` | Informational mirror of the agent frontmatter budget knob | operator |
  | `timeout_minutes` | `180` | config `agent` | Default per-run agent timeout (roadmap-dev overrides per job with `run_timeout_minutes`) | operator |
  | `auto_approve` | `true` | config `agent` | Passes `--auto` to `opencode run` | operator |
  | `orchestrator_agent` | `planner-enhanced` | **code constant** (`_AGENT_NAME` in `roadmap_dev.py`) — the old `workflows.roadmap-dev.agent` config entry was informational only; the scheduler never passed the agent name | Headless agent that reviews + executes the plan | operator |
  | `worker_agent` | `lightweight-dev` | **in the brief text** (`render_brief`: "Dispatch @lightweight-dev …") — proposal: promote to config | Sub-agent dispatched per task | operator (proposed) |

  **C. Repo surface** (config `roadmap_prompts.*`)

  | Variable | Value | Where | Meaning | Owner |
  |---|---|---|---|---|
  | `allowed_repos` | the live 9 repos (list them) | config | Repos scanned for plans; empty = no-op | operator |
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
  | listing columns | `approval, priority, plan, title, state, remove` | User-owned: approval/priority/remove (+ `failure`→`open` re-arm); workflow-owned: title/state (+ the goal/task detail row) |
  | state values | `open, pending, review, success, failure` | State machine (see README) |

  **E. Runtime paths** (config `paths.*`; runtime dirs gitignored)

  | Variable | Value | Meaning |
  |---|---|---|
  | `state_dir` / `log_dir` / `sandbox_dir` | `state` / `logs` / `sandbox` | Engine-relative runtime dirs |
  | sandbox layout | `clones/<owner>__<name>`, `wt/<…>/<identity>`, `diag/<…>/<identity>`, `prompts/` | Repo clones, execution worktrees, diagnostics worktrees, the dedicated listing clone |
  | state file | `state/roadmap-dev.json` | Per-plan machine bookkeeping (identity, state, attempt, pid, branch, sha, last error) |

  **F. Environment variables**

  | Variable | Required | Meaning |
  |---|---|---|
  | `GITHUB_PAT` | no (SSH default) | Only for HTTPS-mirror clones via `repo_urls`; never in config or git |

  **G. LLM agent knobs** (global OpenCode config `~/.config/opencode/agents/` — documented, NOT versioned in this repo per user decision 2026-11-23)

  | Agent | Knobs |
  |---|---|
  | `planner-enhanced` | model `llama-cpp/Qwen3.8-27B`, temperature `1.0`, top_p `0.95` |
  | `lightweight-dev` | model `llama-cpp/Qwen3.8-27B`, temperature `0.7`, top_p `0.80`, thinking off (`enable_thinking: false`), presence penalty `1.5` |

- **Acceptance:**
  1. All 7 sections (A–G) present with the tables above; every "Where" cell matches the code (spot-check: `_AGENT_NAME` is a constant in `roadmap_dev.py`; `_TESTS_GATE_TIMEOUT_SECONDS = 600` is a module constant; `_slots` hardcodes 1/2).
  2. The intro states the documentation-first stance (no code refactor implied).

### Task 3: README update
- **Files:** `README.md` (modify — the existing plan-authoring guide)
- **Do:** Keep the existing plan-authoring content (state machine, user-owned cells,
  the detail row, PR flow) intact. Update the top framing (first ~15 lines): the repo
  is now the **single home** of the autonomous task — it contains the engine package
  (`src/autonomous_task/`), its config, `scripts/setup.sh`, `systemd/` units, the
  operator docs (`WORKFLOW.md`, `VARIABLES.md`), AND the live `plans.md` listing; the
  old `agentic_scripts` home keeps only mail-keeper/oc-todo. Add a short "Running the
  engine" section: fresh clone → `bash scripts/setup.sh` (installs the 30-min timer;
  `--skip-timer` for manual runs) → `uv run autonomous-task run [--force]`; and a
  pointer section to `WORKFLOW.md` (scripts-vs-LLM split) and `VARIABLES.md`
  (every variable). Do not restructure the rest of the guide.
- **Acceptance:**
  1. The README states the repo is the full home of the autonomous task (engine + docs + listing) in the first section.
  2. A "Running the engine" section exists with the exact commands above.
  3. The plan-authoring material (state machine, user-owned cells, PR flow) remains present (grep the key terms: `open`, `pending`, `review`, `success`, `failure`, `approval`, `priority`).

### Task 4: Commit + push
- **Do:** Stage `WORKFLOW.md`, `VARIABLES.md`, `README.md` explicitly; commit `OC: Add WORKFLOW.md (scripts-vs-LLM split) + VARIABLES.md (first proposal) + README home update`; push.
- **Acceptance:** Clean tree on `feature/engine-move`; pushed; `plans.md` untouched; suite still green (`uv run pytest -q` — docs shouldn't affect it, but verify the repo is not left in a broken state).

## Out of Scope
- Code changes of ANY kind (this is a docs-only task; the "proposal: promote" markers
  are documentation, not refactors).
- Vault-side doc updates; the old repo's README (work-plan Task 6).

## Notes
- **[Assumption]** The "first proposal" values are the LIVE values as of 2026-11-23;
  if a config value in `config/workflows.yaml` differs from a table above, the CODE
  wins (re-verify and note the correction in the result report).
- **[Risk]** Doc drift: WORKFLOW.md must not describe behavior the code no longer has
  (e.g. quiet-window load gating — that belongs to `agentic_scripts`). If in doubt,
  the code is the source of truth.
