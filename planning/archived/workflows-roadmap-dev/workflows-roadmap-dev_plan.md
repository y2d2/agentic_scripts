# Idle Execution of Approved Plans (`roadmap-dev`) Plan

**Purpose:** Idle-triggered execution of approved repo plans by `planner-enhanced`, delivered as PRs, governed by a live listing.

## Objective

The new `roadmap-dev` workflow turns this rig into an unattended plan-execution engine. On every timer fire it scans the allowed GitHub repos (all branches) for plans that have not been archived (`planning/<topic>/work_plan.md`), reconciles them into a listing table in the new `y2d2/ARP_prompts` repo (mounted as a submodule in the ARP_roadmap vault), and — whenever the server is idle (no user sessions, day or night) — keeps its execution slots continuously full: **1 by day, 2 by night**, always the highest-priority approved plan (`open`, or re-approved `review`, carrying the user's checkmark). Each job is one headless `planner-enhanced` run that reviews the plan, raises *major* questions into `questions.md` (plan → `review`, checkmark removed), or executes it by dispatching `@lightweight-dev` **strictly sequentially, one small self-contained task at a time**; the runner delivers success as a fresh branch + PR (implementation + archived plan folder) and diagnostics as small `OC:` commits on the plan's branch. Success condition: a PR per successfully executed plan, a listing that always shows state/priority/approval at a glance, and zero duplicate work across runs.

## Context

- `agentic_scripts` already provides: the 30-min timer, exclusive lock, per-run logging, `state/` + `sandbox/` conventions, and `AgentRunner` — a headless wrapper over `opencode run --standalone --agent … --format json --auto --model llama-cpp/Qwen3.8-27B <brief>` with cwd=`PWD` binding, process-group kill on timeout, NDJSON→`AgentResult` reduction (/workspace/Research/ai-agent-workflow/opencode-2x-run-headless.md).
- `oc-todo` is the proven runner-owns-git template: clone/fetch, worktree, `OC:` commit, fresh-branch push, PR, blocker gate, step-exhaustion sentinel, atomic state persist, retry on next gate-open run.
- OpenCode 2.x facts (verified): `--agent` selects any agent (incl. `mode: primary`); a headless question the run cannot answer ends the run with exit 1 — a *detected* failure, not a hang (https://opencode.ai/docs/cli). OpenCode imposes **no concurrency limits** (one runner fiber per active session), and this rig's llama.cpp backend for Qwen3.8-27B has **exactly 2 slots** (live-verified on this box) — so 2 concurrent jobs saturate it, and 1 concurrent job leaves one slot for interactive use (/workspace/Research/ai-agent-workflow/opencode-2x-llm-concurrency.md).
- Plan convention (both existing repos follow it): `planning/<topic>/work_plan.md` + task files; archive = whole folder `git mv planning/<topic>/ planning/archived/<topic>/` with an `OC:` commit (skill: implementation-plan).
- `planner-enhanced` (interactive by design: asks, gates, dispatches `@lightweight-dev`, plans in `./planning/<topic>/`, never codes) runs **unchanged**; autonomy comes entirely from the brief.

## Functional Tasks

### Task 1: `ARP_prompts` repo bootstrap + vault submodule
- **Goal:** The new `y2d2/ARP_prompts` repo exists — README (how to write plans: small self-contained tasks, testable acceptance criteria, what counts as a *major* question; the listing legend + state machine; how to approve, re-arm, answer, and remove rows) plus the initial `plans.md` skeleton — and is mounted into ARP_roadmap as a submodule at `agent-prompts/`.
- **Why this approach:**
  - **[Decision: dedicated repo via submodule]** Value = separate repo in the vault because it is a clean workflow-writable source of truth with zero coupling to the dirty Obsidian clone (no `index.lock` interplay with mail-keeper) while staying visible/editable in Obsidian → user proposal, 2026-11-21.
  - **[Decision: workflow keeps its own clone]** Value = sandbox clone + fetch-per-fire, because "current" must mean latest GitHub, independent of the vault's checkout state.
- **Acceptance criteria:** `git submodule update --init` in ARP_roadmap resolves `agent-prompts/` to the new repo; a `plans.md` row the user hand-edits survives any number of workflow scans (user-owned cells preserved).

### Task 2: Session-aware idle gate + per-workflow gate types
- **Goal:** Two gate types: existing workflows keep the quiet-window gate (night only, unchanged); `roadmap-dev` gets an *idle* gate — open whenever **no user/interactive sessions** exist, day or night; both keep the two-consecutive-idle-polls rule.
- **Why this approach:**
  - **[Decision: idle = no user sessions]** Value = session-based over load-based, because the worker's own runs raise load and would self-block between jobs (user's explicit choice). Interactive sessions attach to the shared OpenCode service; worker runs use `--standalone` and are invisible to that service **by construction** → /workspace/Research/ai-agent-workflow/opencode-2x-llm-concurrency.md.
  - **[Decision: per-workflow gate override]** Value = per-workflow gate type over relaxing the machine-global quiet window, because mail-keeper and oc-todo stay overnight-only (user's explicit choice).
  - **[Decision: 2-poll rule kept]** Value = 30–60 min of sustained idle before any start, so a session the user is *starting* is not interrupted (existing design property, preserved).
- **Acceptance criteria:** With the user's TUI active, nothing new starts (in-flight jobs finish); 30–60 min after it closes, `roadmap-dev` starts on a daytime poll; mail-keeper/oc-todo behavior is unchanged (quiet window, load, 2 polls).

### Task 3: Plan discovery + listing reconciler
- **Goal:** Every timer fire (even while jobs are in flight): scan all allowed repos (clone/fetch in sandbox, **all branches**), discover non-archived plans, and reconcile `plans.md` — new plan → new row (`open`, no checkmark); update workflow-owned cells (title, state); drop rows where the user ticked **remove** on a `success` row; never clobber user-owned cells (approval, priority, remove, state re-arm).
- **Listing contract** — `ARP_prompts/plans.md`, one section per repo, one table per branch (repo and branch are headers, not columns):

  ```markdown
  # https://github.com/y2d2/ARP_MPE.git
  ## main
  | approval | priority | plan | title | state | remove |
  |----------|----------|------|-------|-------|--------|
  | ☐ | 1 | planning/orbit-sim/work_plan.md | ORBIT sim extension | open | ☐ |
  ## dev
  | approval | priority | plan | title | state | remove |
  |----------|----------|------|-------|-------|--------|
  | ☑ | 2 | planning/unitest/work_plan.md | Unit tests | review | ☐ |
  ```

  A repo/branch section exists while it has — or historically had — a known plan. Columns: `approval` (user's checkmark — the permission), `priority` (numeric, ascending; 1 = first; ties by row order), `plan` (path to `work_plan.md`), `title`, `state`, `remove` (user's checkmark; valid on `success` rows → row deleted on next scan). Plan identity = repo + branch + plan-folder path + content hash (an edited plan is a new plan).
- **State machine** (the listing is the human source of truth; `state/roadmap-dev.json` mirrors it for execution bookkeeping — pids, hashes, PR refs):

  | state | meaning | startable |
  |---|---|---|
  | `open` | discovered, awaiting approval/execution | yes, with ☑ |
  | `pending` | job running | no |
  | `review` | major questions in `questions.md`; **checkmark removed by the workflow** (logged) | yes, once the user re-☑'s |
  | `success` | attempt branch pushed (implementation + archived folder on `roadmap-dev/<id>-<n>`; a human opens the PR — user decision 2026-11-21: NO PR creation by the agent) | no; removable via remove ☑ |
  | `failure` | `failure.md` (reason) on the plan's branch; plan not archived | no — re-arm = set state `open` (or edit the plan → new identity → `open`) |

  Timeout (8 h, configurable) → `failure`. Crash/box-restart → reaper flips orphan `pending` → `open` (infra death ≠ job failure → auto-retry next drain).
- **Why this approach:**
  - **[Decision: discovery over hand-written prompts]** Value = scan the allowed repos for un-archived plans over a hand-maintained prompt queue, because plans are the planner's existing native artifact (`work_plan.md`) — no new authoring format — and the archive action doubles as the success marker → user re-spec, 2026-11-21.
  - **[Decision: header-per-repo/branch layout]** Value = `#` repo URL + `##` branch + per-branch table over one flat table with repo/branch columns, because it groups plans the way the user reads them and keeps the table narrow (6 columns) → user's format spec, 2026-11-21.
  - **[Decision: listing = human surface, state JSON = machine surface]** Value = two representations (md table = what the user reads/edits; JSON = pids/hashes/PR refs) because the cron-reconciled md table is both operator dashboard and approval mechanism — the checkmark *is* the permission.
  - **[Decision: allowlist = "allowed githubs"]** Value = a repo outside `allowed_repos` is never scanned or executed; empty list = no-op at ship (mirrors `oc_todo.repos`).
- **Acceptance criteria:** Adding a plan folder to an allowed repo appears as an `open` row under the right `# repo` / `## branch` section within one cron fire; the user's checkmark/priority edits survive any number of scans; a `success` row with remove ☑ disappears on the next scan (and reappears — harmlessly — if the PR is unmerged and the plan still un-archived).

### Task 4: The `roadmap-dev` workflow — room check, continuous slots, job pipeline
- **Goal:** Timer fire → phase 1 (Task 3 scan) → phase 2 **room check** (idle gate open) → phase 3 **drain**: keep the slots continuously full — **1 by day, 2 by night** (night = the existing 22:00–08:00 window) — by starting, into each free slot, the highest-priority ☑-approved `open`/`review` plan (`→ pending`); the moment a job ends, its slot is topped up immediately (re-reading the table first, so the user can re-prioritize between jobs) as long as the gate is still open and startable plans remain. While the gate closes (user returns), no new starts; in-flight jobs finish (let-finish).
- **Job contract** — one `planner-enhanced` headless run (agent unchanged, autonomy brief, `--auto`, 8 h per-job timeout) in a worktree on fresh branch `roadmap-dev/<plan-id>-<attempt>` cut from the plan's branch:
  1. **Review the plan.** Major open question (changes scope/requirements/dependencies — *not* implementation detail) → write `planning/<topic>/questions.md`, report status `questions`. Minor things → decide itself and record the decision.
  2. **Execute in sequence.** Dispatch `@lightweight-dev` **one small self-contained task at a time — never in parallel** (small context = the speed bottleneck); verify each task's acceptance criteria before the next.
  3. **Report.** Final message = result report with an explicit status (`success` / `questions` / `failure`), files, tests, blockers. No git commit/push by the agent — the runner owns git.
- **Runner outcomes:** `success` → verify (no blockers, tests green, non-empty diff) → commit implementation + **archive the plan folder** (whole folder → `planning/archived/`, `OC:` commit) → push → **PR** (base = plan's branch; body quotes the plan's title/path/branch + the planner's report) → state `success`. `questions` → commit + push `questions.md` on the **plan's branch** (small `OC:` commit, no code) → state `review` + **checkmark removed**. `failure`/timeout → commit + push `failure.md` (reason) on the plan's branch → state `failure`. Worktree always cleaned up (`finally`); state persisted atomically; everything logged (`logs/last-run.txt`, per-run logs).
- **Why this approach:**
  - **[Decision: continuous slots 1 day / 2 night]** Value = slots kept full while idle (top-up on completion) over one-job-per-poll, because "the planning should always be running — one session continuously, two at night" is the user's explicit requirement, and top-up avoids 30–90 min of dead time between jobs → user spec, 2026-11-21.
  - **[Decision: 2 = night parallelism ceiling]** Value = 2 concurrent jobs by night over more, because the local Qwen3.8-27B backend has exactly 2 slots — a 3rd job would queue, not parallelize; by day 1 job leaves a slot for interactive work (verified slot count) → /workspace/Research/ai-agent-workflow/opencode-2x-llm-concurrency.md.
  - **[Decision: sequential dev dispatch within a job]** Value = one `@lightweight-dev` at a time, small self-contained tasks, over parallel dispatch, because context size is the dominant speed bottleneck and parallel sub-agents would multiply context churn without adding correctness → user spec, 2026-11-21.
  - **[Decision: in-process top-up drain]** Value = start-next-on-completion within one lock-holding run over detached background supervisors (reaper/orphan machinery rejected for complexity) → own analysis vs. the README's stateless-entry-point design, extended minimally.
  - **[Decision: autonomy brief, agent unchanged]** Value = brief declares the run pre-approved, no user present, question tool unavailable, the major-question protocol, and the sequential small-task mandate — over a headless variant agent, because the user wants the *same* planner-enhanced as in interactive use, and a stray headless question is a detected exit-1 (auto-retried) → https://opencode.ai/docs/cli.
  - **[Decision: diagnostics on the plan's branch]** Value = `questions.md`/`failure.md` land as small `OC:` commits on the branch shown in the listing, because the user's loop is "answer in the plan folder, re-checkmark" — the plan folder is on that branch; re-runs start from it and read the answers → user choice, 2026-11-21.
  - **[Decision: success = PR, archive inside it]** Value = fresh branch + PR with the archive commit included, because the plan becomes truly archived on the plan's branch only when the user merges — the scanner's "not archived" test then self-resolves; attempt branches `roadmap-dev/<id>-<n>` are forensics the user may prune → user's standing delivery choice.
  - **[Decision: failure waits for the user]** Value = `failure` is not auto-started, because in a review-loop world a failing plan needs a human eye on `failure.md`, not 1–2 h of compute per cron cycle; re-arming is one cell edit.
  - **[Decision: reaper distinguishes infra from job death]** Value = timeout → `failure` (bounded job failure), crash/restart → `open` (auto-retry), because a box restart must not require a human re-arm while a hung job must not loop forever.
  - **[Decision: 8 h per-job timeout]** Value = 480 min configurable, process-group kill — the only mechanism converting a hang (the one end-state that never self-reports) into a failure → user call after correction, 2026-11-21.
- **Acceptance criteria:**
  - With approved `open` plans queued and an idling box, a job is in flight from ~11:00 on (2-poll rule) and, as long as the gate stays open and plans remain, a slot is refilled the moment a job ends — by day one job at a time, by night two concurrently, with no 30-min gaps between jobs.
  - With the user's TUI active, no new job starts; in-flight jobs finish.
  - A plan with a major question appears in `review` with its checkmark removed and `questions.md` committed on its branch; the user answers in `questions.md` + re-☑ → it re-runs and reads the answers.
  - Each `success` yields exactly one PR on `roadmap-dev/<id>-<n>` quoting the plan + the planner report; re-runs never duplicate PRs; `success`/`failure` rows never auto-restart.
  - A killed (timeout) or crashed job leaves no leaked worktree, no partial push, and the correct state (`failure` / `open`).
  - Inside any job, at most one `@lightweight-dev` is ever in flight.

### Task 5: Config, registration, operator surface, docs
- **Goal:** `roadmap_prompts` config section (`allowed_repos`, `run_timeout_minutes: 480`, listing path/branch, gate type) with fail-fast, human-readable validation; `workflows.yaml` entry (`agent: planner-enhanced`); `setup.sh` verifies the global agent (existing mechanism) + prompts-repo reachability; README section (run pipeline, listing legend, state machine, operator commands incl. `uv run agentic-scripts run --force --only roadmap-dev`, guardrails, where outputs live).
- **Why this approach:**
  - **[Decision: empty allowlist = no-op]** Value = shipped config inert until repos are listed (mirrors the `oc_todo.repos: []` first-run pattern) → README oc-todo section.
  - **[Decision: authoring guidance in the ARP_prompts README]** Value = plan-authoring rules (small tasks, major-question threshold) live with the thing they describe.
- **Acceptance criteria:** `uv run agentic-scripts run --force --only roadmap-dev` drives a full scan + drain with fixture repos; a config typo names the offending field; `setup.sh` stays idempotent on re-run.

### Task 6: Hermetic tests
- **Goal:** Unit tests (plan discovery/identity, listing parser/reconciler incl. user-cell preservation, state-machine transitions, reaper, brief renderer, allowlist) plus smoke tests following the existing suite conventions (injected clock/idle check, fake agent runner, local-URL fixture repos): full drain with day-1/night-2 slot switching, priority re-ordering mid-drain, gate-close mid-drain, review round-trip (`questions.md` → answer → re-☑ → re-run reads answers), timeout kill, crash/reaper, PR dedup on re-run, remove-row rule, refused repo, malformed plan skip.
- **Why this approach:**
  - **[Decision: same seams as existing suites]** Value = injected idle check + fake runner + local repo URLs (the `repo_urls` seam pattern), so no real `opencode`, repos, or network are needed → tests/smoke/ convention.
- **Acceptance criteria:** `uv run pytest tests/smoke/ -v` passes hermetically; every guardrail in Tasks 3–4 has a failing-test counterpart.

## Alternatives Considered
1. **Hand-written prompt files in ARP_prompts (first draft)** — superseded by the user's re-spec: discovery of existing plans + listing governance.
2. **One job per cron poll** — rejected: 30–90 min of dead time between jobs contradicts "always running".
3. **Detached background supervisor (jobs outlive the scheduler process)** — rejected: reaper/orphan machinery for no throughput gain over in-process top-up.
4. **Direct push to the plan's branch** — rejected by the user: fresh branch + PR remains the delivery contract.
5. **Diagnostics on the attempt branch** — rejected by the user: `questions.md`/`failure.md` belong on the plan's branch where the loop answers them.
6. **Worker also plans (note → plan draft mode)** — out of scope by user choice: day = user/interactive sessions plan; idle = worker executes (may become a later extension).
7. **Load-based idle** — rejected: self-blocking; session-based is the user's choice.
8. **Preemption kill on user return** — rejected by the user: let in-flight jobs finish.
9. **3+ parallel jobs at night** — rejected: the backend has exactly 2 slots; a 3rd job would queue, not parallelize.

## Notes
- **[Assumption]** Plan = `planning/<topic>/work_plan.md` outside `planning/archived/`; title from the `work_plan.md` heading; identity includes a content hash so an edited plan is a new plan.
- **[Assumption]** "Night" for the 2-slot cap = the existing quiet-window hours (22:00–08:00); day = otherwise.
- **[Risk]** Two concurrent night jobs saturate the 2 backend slots → each job runs at ~half effective throughput, and the user's interactive session queues until one finishes — explicitly accepted with the night-2 requirement; day-1 keeps a slot free.
- **[Risk]** Context size is the speed bottleneck (user's words) — the ARP_prompts README mandates small self-contained tasks; a plan that needs a full 8 h job should be split into several smaller plans.
- **[Risk]** An unanswerable plan can ping-pong through `review` (each round-trip is a full job); the escape hatch is deleting the plan folder (the row then reconciles away) or leaving it un-approved.
- **[Risk]** `planner-enhanced` (local 27B) may occasionally still attempt a question form headless → the run exits 1, is logged, and the plan's state is reaped (`open`) or stays as-is — auto-retried next drain; expect to watch the first few runs.
- **[Risk]** While a drain holds the global lock (potentially hours), other workflows and manual `--force` runs wait until it ends; phase 1 (scan + listing update) still runs every 30-min fire regardless. Accepted as the cost of "always running".
- **[Risk]** Attempt branches accumulate as forensics (`roadmap-dev/<id>-<n>`); the user prunes them manually; the workflow never merges or pushes them except as PR heads.
- **[Note]** `--auto` (auto_approve) is already in config; `planner-enhanced` carries no `steps:` cap (agent file unchanged) — the 8 h wall clock is the job's only budget.
- **[Note]** `max_attempts`-style caps are deliberately absent from the state machine: `failure` waits for a human re-arm; only infra deaths auto-retry.
