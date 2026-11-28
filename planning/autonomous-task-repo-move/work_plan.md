# Work Plan: Autonomous Task → Overview Repo (engine move, docs, cutover)

**Purpose:** Make `y2d2/autonomous_task_overview` the single, self-contained home of the
roadmap-dev autonomous task — relocated standalone engine, `WORKFLOW.md`
(scripts-vs-LLM split), `VARIABLES.md` (first proposal of every variable) — and cut the
server over to it with zero double-engine exposure.

**Source plan:** `autonomous-task-repo-move_plan.md` (this folder). This work plan is the
refined, dispatch-ready decomposition of it.

## Objective

Move the roadmap-dev engine out of `agentic_scripts` into the overview repo as a
standalone uv project (fresh clone + setup = green suite, runnable `autonomous-task run`),
write the operator docs, and — behind a user cutover gate — remove the engine from
`agentic_scripts` and install the new 30-minute cron entry so exactly one engine ever
fires.

## Context (verified 2026-11-23 by the orchestrator)

- **Old engine:** `/workspace/Python/agentic_scripts`, package `agentic_scripts`
  (`src/agentic_scripts/`), branch `feature/roadmap-dev-workflow` — this is the LIVE
  checkout; cron `*/30` (`# agentic-scripts` marker) runs `agentic-scripts run` here.
  Core: `workflows/roadmap_dev.py` (3,356 lines; internal imports: `AgentResult`,
  `Config`/`RoadmapPrompts`, `Git`/`GitError`, `WorkflowResult`), `agent.py` (414),
  `git.py` (657), `sessions.py` (175), `state.py` (166), `config.py` (827),
  `scheduler.py` (791), `workflows/base.py` (196), `logging_setup.py` (124), `cli.py` (38).
  `github.py` is NOT used by roadmap-dev (never calls the GitHub API).
- **New engine home:** `/workspace/Python/autonomous_task_overview` (persistent clone of
  `git@github.com:y2d2/autonomous_task_overview.git`; created in Task 1). The repo today
  holds only `README.md` (plan-authoring guide) + `plans.md` (live listing, `main`,
  reconciled + pushed by the engine every fire). Vault display copy
  (`/workspace/Obsidian/ARP_roadmap/autonomous_task_overview`) is NOT touched.
- **State (verified):** `state/roadmap-dev.json` — **82 entries, all `open`, all attempt
  0** (the source plan said 78; the live count governs). No in-flight jobs → safe
  cutover window. `state/scheduler.json` gate streaks are both `null`.
- **Runner env (verified):** OpenCode v2.3.2; agents `planner-enhanced` +
  `lightweight-dev` present in `~/.config/opencode/agents/` (global config, NOT
  versioned in the repo — user decision 2026-11-23). Runner invocation already
  proven in production (research cache:
  `/workspace/Research/ai-agent-workflow/opencode-2x-run-headless.md`).
- **Corrections to the source plan's first proposal (folded into Task 4):**
  1. `orchestrator_agent` (`planner-enhanced`) is a **code constant**
     `_AGENT_NAME` in `roadmap_dev.py` (line 134) — the old config entry
     `workflows.roadmap-dev.agent` was informational; the scheduler never passed the
     agent name to the workflow. `VARIABLES.md` documents the code constant.
  2. The smoke suite is **adapted, not moved verbatim**: it asserts on sibling
     workflows (`noop`/`mail-keeper`/`oc-todo` skip lines), the quiet-gate state key
     (`gate_last_ok`), `--only`, and a `load=` injection that the single-workflow
     runner does not have. Adaptation spec is in Task 2.
  3. `machine.load_threshold` (quiet-window gate) and `psutil` are dropped from the new
     package (idle gate is session-based only; `_slots` keeps using
     `machine.quiet_window` for day/night slots).
- **Cutover sequencing (double-engine avoidance):** the new cron entry is installed
  AFTER the user gate and AFTER `agentic_scripts` loses the engine (cleanup first,
  cron second). Before the gate, the new engine is verified with direct `--force`
  invocations only (`setup.sh --skip-timer`).
- **Live drain cannot be exercised:** all 82 rows are unapproved → drain never starts.
  Post-cutover drain verification relies on the hermetic pipeline suite (moved, green)
  + a live window if the user approves a row (user's call at completion).

## Naming (finalized by orchestrator — source plan delegated these)

| Thing | Value |
|---|---|
| Project name (pyproject) | `autonomous-task` |
| Python package (src layout) | `autonomous_task` |
| Console script | `autonomous-task` |
| Single-workflow runner module | `autonomous_task/runner.py` |
| Config file | `config/workflows.yaml` (trimmed: `machine`/`agent`/`paths`/`roadmap_prompts`) |
| Workflow name | `roadmap-dev` (unchanged — state file + sandbox continuity) |
| Feature branch (overview repo) | `feature/engine-move` |
| Cron marker (new entry) | `# autonomous-task` |

## Tasks & Scheduling

All tasks are dispatched to `@lightweight-dev`. **Entirely consecutive** — no parallel
block is possible: Tasks 1–5 share one repo/branch (merge-conflict rule), and Tasks 6–8
operate on the live system where the double-engine and live-checkout constraints
serialize them.

| # | Task | Repo | Depends on | Gate before? |
|---|------|------|-----------|--------------|
| 1 | Engine package scaffold (primitives, trimmed config, new runner, CLI, pyproject) — imports + CLI work | overview clone | — | no |
| 2 | `roadmap_dev.py` port + test suite move/adapt — full suite green | overview clone | 1 | no |
| 3 | `scripts/setup.sh` (+`--skip-timer`), systemd units, `.env.example` | overview clone | 2 | no |
| 4 | Docs: `WORKFLOW.md` + `VARIABLES.md` + `README.md` update | overview clone | 3 | no |
| 5 | Merge `feature/engine-move` → `main`; byte-identical cutover check (old forced run baseline vs new forced run) | both | 4 | no |
| — | **GATE: cutover approval** (user confirms evidence before any removal lands) | — | 5 | 🛑 |
| 6 | `agentic_scripts` cleanup (module, config, preflight, bootstrap, staging dir, tests, README) — suite green, committed + pushed | agentic_scripts | GATE | — |
| 7 | Install new cron entry (`# autonomous-task`); one gate-checked (non-forced) fire verified | system + overview clone | 6 | — |
| 8 | Final end-to-end verification (both suites, tip identity, one-engine proof, rollback path) | both | 7 | — |
| — | **COMPLETION GATE** (canonical completion question → archive per `skill: implementation-plan`) | — | 8 | — |

Result files: `lightweight_dev_task_<N>_<desc>.md` in this folder (one per task).

## Dispatch protocol (per `skill: sub-agent-communication`)

Each dispatch carries: (1) the per-task plan path `work_plan_task_<N>_<desc>.md`,
(2) the exact result filename, (3) the task number. Orchestrator re-reads each result,
verifies the acceptance table against the task spec, and only then dispatches the
dependent task. Max 2 retries per task before escalation.

## Out of Scope

- No code refactor of `VARIABLES.md`-recommended promotions (day/night slots,
  `tests_gate_timeout_seconds`, `worker_agent` stay code constants/brief text).
- No versioning of agent definitions in the repo (stays `~/.config/opencode/agents/`).
- No migration of sandbox clones (fresh re-clone on first run is the documented path).
- No vault-side work (the display submodule updates itself when the user pulls).
- No removal of the dormant idle-gate machinery from `agentic_scripts`
  (`evaluate_idle_gate`, `sessions.py`, `WorkflowEntry.gate` stay — dead but tested;
  removing them is a follow-up decision).
- No live drain execution (no approved rows; user decides at completion).
- `plans.md` content: never hand-edited by any dev task.

## Notes

- **[Assumption]** The overview repo is not (and must not become) an `allowed_repos`
  entry — the engine never scans its own docs for plans (docs live at repo root, never
  under `planning/`).
- **[Assumption]** Merging engine code into the overview repo's `main` is safe for the
  engine: the listing clone (`sandbox/roadmap-dev/prompts`) reads only `plans.md` and
  the non-fast-forward retry in `_reconcile_and_push` assumes a dedicated clone —
  engine-code files can never conflict with listing commits.
- **[Risk]** Drift between the frozen primitive copies and their `agentic_scripts`
  originals — accepted per source plan (copies are frozen leaf code; the engine is a
  terminal consumer).
- **[Risk]** Cutover with a job in flight — impossible today (0 pending; verified).
- **[Hygiene]** `agentic_scripts` carries untracked files from a separate session
  (`planning/mail-keeper-pruning/` result reports). Every dev task in that repo MUST
  stage explicit paths only — never `git add -A` / `git add .`.
- **[Rollback]** Post-gate rollback = `git revert` of the Task 6 commit in
  `agentic_scripts` (engine re-armed; its cron line was never removed) + delete the
  `# autonomous-task` crontab lines. The overview `main` merge is additive (the old
  engine ignores engine-code files).
- **[Verification note]** "Byte-identical" means: plans.md content hash at the old
  engine's post-run tip == plans.md content hash at the new engine's post-run tip
  (a legitimate listing advance between the two runs invalidates the check → re-run).
