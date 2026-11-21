# Work Plan: roadmap-dev workflow (idle execution of approved plans)

**Purpose:** Implement the `roadmap-dev` workflow in `agentic_scripts` per the reviewed plan `workflows-roadmap-dev_plan.md`: on every 30-min timer fire, scan allowed GitHub repos (all branches) for un-archived plans, reconcile a live listing (`plans.md` in the new `y2d2/ARP_prompts` repo), and — when the box is idle (no interactive OpenCode sessions, day or night) — keep execution slots continuously full (1 by day, 2 by night), each job a headless `planner-enhanced` run that executes one approved plan sequentially via `@lightweight-dev`, delivered as branch + PR.

## Objective

Ship a new registered workflow `roadmap-dev` (module `agentic_scripts.workflows.roadmap_dev`, agent `planner-enhanced`) that:

1. **Phase 1 (every fire):** scans `roadmap_prompts.allowed_repos` (sandbox clone/fetch, all branches except `roadmap-dev/*`) for `planning/<topic>/work_plan.md` outside `planning/archived/`, and reconciles the listing in `ARP_prompts/plans.md` (per-repo `#` sections, per-branch `##` tables, 6 columns) — never clobbering user-owned cells (approval, priority, remove, failure→open re-arm).
2. **Phase 2 (room check):** an *idle* gate type (new, per-workflow): open iff the shared OpenCode service reports zero active sessions (live-verified mechanism: `GET /api/session/active`, Basic auth from `~/.local/state/opencode/service.json`), day or night, with the existing two-consecutive-polls rule (separate state key `idle_gate_last_ok`). Existing workflows keep the quiet-window gate, unchanged.
3. **Phase 3 (drain, in-process):** while the idle gate stays open and startable plans remain, keep slots full — 1 by day, 2 by night (night = `machine.quiet_window` 22:00–08:00) — each job one `planner-enhanced` headless run in a worktree on fresh branch `roadmap-dev/<id>-<attempt>` cut from the plan's branch, 8 h per-job timeout; top up immediately on job end (re-reading the table first); gate close → let in-flight jobs finish, no new starts.
4. **Outcomes:** `success` → verify (no blockers, tests green if configured, non-empty diff) → commit implementation + archive plan folder → **push the attempt branch** (NO PR creation by the agent — branch push is the delivery; PR/merge is human-level verification, user decision 2026-11-21) → state `success`; `questions` → `questions.md` committed as small `OC:` commit on the **plan's branch** → state `review` + checkmark removed (logged); `failure`/timeout → `failure.md` on the plan's branch → state `failure`; crash → reaper flips orphan `pending` → `open` (+ worktree cleanup) at next run.
5. **Operator surface:** `roadmap_prompts` config section (fail-fast validation), `workflows.yaml` entry (`gate: idle`), `setup.sh` checks, README section, hermetic unit + smoke tests, one-shot bootstrap script for the `y2d2/autonomous_task_overview` listing repo + vault submodule.

Success conditions: a pushed attempt branch (implementation + archived plan folder) per successfully executed plan — humans open PRs/verify; a listing that always shows state/priority/approval at a glance; zero duplicate work across runs; `uv run pytest -v` green hermetically.

## Context

- Repo: `/workspace/Python/agentic_scripts`, branch `feature/roadmap-dev-workflow` (created from the current de-facto mainline; `main` is a stale placeholder).
- Framework: 30-min cron → `uv run agentic-scripts run` → `scheduler.run()` (exclusive flock, single machine-global gate today, per-workflow sequential loop, `WorkContext`, `WorkflowResult`). Templates to mirror: `workflows/oc_todo.py` (runner-owns-git, constructor-injected `git`/`github`/`runner` seams, idempotent `Git.commit` primitive, worktree add/remove with `finally` cleanup, `OC:` commits, fresh-branch push, PR dedup by head ref), `git.py` (thin git plumbing, `GitError` with stderr tail), `github.py` (stdlib REST client, `_urlopen` test seam, PAT from `GITHUB_PAT`), `state.py` (atomic JSON store, one doc per workflow), `agent.py` (`AgentRunner` → `opencode run --standalone --agent … --format json --auto --model …`, process-group kill on timeout, `AgentResult`).
- **Live-verified facts (2026-11-21, this box):** shared OpenCode service at `http://127.0.0.1:49374` (dynamic port) — state file `~/.local/state/opencode/service.json` carries `url` + `password` + `pid`; `GET /api/session/active` with **Basic auth** (`opencode:<password>`) returns `{"data": {<sessionID>: {"type": "running"}, …}}` — one entry per open interactive (TUI) session; `--standalone` worker runs are invisible to it by construction. SSH to GitHub works as `y2d2` (all git ops over `git@github.com:…`; **no PAT and no GitHub API at all in this workflow** — PR creation is deliberately human-level, user decision 2026-11-21). The listing repo `git@github.com:y2d2/autonomous_task_overview.git` **exists and is empty** (ls-remote 2026-11-21). llama.cpp backend for Qwen3.8-27B has exactly 2 slots (→ 1 day / 2 night cap).
- Plan convention: `planning/<topic>/work_plan.md` + task files; archive = whole folder move to `planning/archived/<topic>/` with an `OC:` commit.
- Code style: Google-style docstrings (Purpose/Rationale/Args/Returns/Side Effects/Example), `coding-standards` skill; ruff lint+format clean; tests hermetic (`tmp_path` workspaces, `repo_urls`-style local-URL seams, fakes for runner/github, injected clock) — see `tests/smoke/test_smoke_oc_todo.py` (MAIL_* env-isolation autouse fixture pattern) and `tests/test_oc_todo_pipeline.py`.

## Tasks (scheduling)

| # | Task | Files (primary) | Depends on | Schedule |
|---|------|-----------------|------------|----------|
| 1 | Config section + per-workflow gate types + idle gate | `config.py`, `scheduler.py`, new `sessions.py`, `workflows.yaml` (entry `enabled: false`), `tests/test_config.py`, `tests/test_gate.py`, `tests/test_scheduler*.py` | — | Wave 1 |
| 2 | `roadmap_dev` pure core (identity, discovery, listing parser/renderer, reconciler, state machine, reaper, brief/PR renderers) | new `workflows/roadmap_dev.py`, new `tests/test_roadmap_dev.py` | 1 (config types) | Wave 2 |
| 3 | Phase 1 pipeline: scan + prompts-clone + reconcile + push + reaper + git plumbing (`ls_tree`, `mv`) | `workflows/roadmap_dev.py`, `git.py`, new `tests/test_roadmap_dev_scan.py` | 2 | Wave 3 |
| 4 | Phase 2/3 drain + job pipeline (slots, top-up, let-finish, outcomes: branch push / diag commits — no PR API) | `workflows/roadmap_dev.py`, `agent.py` (`AgentResult.pid`), new `tests/test_roadmap_dev_pipeline.py` | 3 | Wave 4 (parallel with 5) |
| 5 | Operator surface & bootstrap (README section, `setup.sh`, bootstrap script — pure git, no REST/PAT — `autonomous_task_overview` staging content, `.env.example`) | `README.md`, `scripts/setup.sh`, new `scripts/bootstrap_task_overview.sh`, new `autonomous_task_overview/`, `.env.example` | 1 | **Parallel with 4** |
| 6 | Final integration: config flip (`enabled: true`) + hermetic smoke + full suite | `workflows.yaml`, new `tests/smoke/test_smoke_roadmap_dev.py` | 3, 4, 5 | Wave 5 |

**Parallel block:** Task 5 runs concurrently with Task 4 (disjoint files). All others consecutive (same-file edits / import dependencies).

## Out of Scope

- No detached background supervisors / job persistence across scheduler processes (in-process drain only — plan decision).
- No preemption of in-flight jobs when the user returns (let-finish).
- No auto-restart of `success`/`failure` rows (human re-arm only); no `max_attempts` caps.
- No changes to `planner-enhanced` / `lightweight-dev` agent definitions; no headless-variant agent (autonomy comes from the brief).
- Worker does not plan new work (note → plan-draft mode is a later extension).
- No merging of PRs, no deletion of attempt branches (operator hygiene).
- No new Python dependencies (stdlib + existing deps only; bootstrap script uses `curl`).
- Task 1 ships the `roadmap-dev` entry with `enabled: false`; enabling is Task 6.

## Notes

- **[Assumption] Content-hash scope:** identity = repo + branch + plan-folder path + sha256 of the plan folder's files **excluding** `questions.md` and `failure.md` (workflow-written diagnostics must not change plan identity; any user edit of a plan file = new identity = new row).
- **[Assumption] Row-drop rules (reconciler):** ghost rows (neither in scan nor in state) dropped; a plan vanishing from the scan (archived/merged/deleted, or repo removed from allowlist) drops its row but keeps the state entry (PR-dedup forensics); `remove` ☑ on a `success` row drops the row — it reappears as `success` (not re-executable) on the next scan while the PR is unmerged, and disappears for good once the plan folder is gone from the branch (merged).
- **[Assumption] Default priority** for a newly discovered plan = max priority in its (repo, branch) table + 1 (or 1 for an empty table); ties by row order (documented in the ARP_prompts README).
- **[Assumption] User re-arm** = the one sanctioned state-cell edit: setting `open` on a `failure` row; the workflow syncs it into the state JSON. Any other state-cell divergence is overwritten by the workflow cell.
- **[Assumption] Phase-1 freshness mid-drain:** the drain re-runs scan+reconcile+push (a) at drain start, (b) before each top-up, (c) every `machine.poll_interval_minutes` while jobs are in flight — so the listing stays live even while the drain holds the global lock (other fires skip on the lock; accepted risk per plan).
- **[Assumption] Idle probe failure semantics:** if the service state file is missing, the service is down, or the HTTP call fails, the probe reports 0 active sessions (idle) — logged at WARNING; the 2-poll rule and run logs keep this auditable.
- **[Assumption] Clone URLs default to SSH** (`git@github.com:<owner>/<name>.git`) because SSH is live-verified on this box; `repo_urls` / `listing_repo_url` config overrides are the hermetic-test seam (local paths) and mirror the `oc_todo.repo_urls` pattern.
- **[Decision, user 2026-11-21] NO PR creation by the agent — NO GitHub REST API in this workflow at all.** Success delivery = the pushed attempt branch (`roadmap-dev/<id>-<n>` carrying implementation + archived plan folder); the human opens the PR / verifies / merges. State records `branch_name` instead of PR refs; no `GITHUB_PAT` needed anywhere in roadmap-dev; re-run safety comes from the state machine (`success` never startable) + the listing, not from API lookups.
- **[Design decision] `gate:` lives on the workflow entry** (scheduler-level concern), not in the `roadmap_prompts` section as the high-level plan sketched — same effect, cleaner separation; the section keeps execution parameters (`allowed_repos`, `run_timeout_minutes: 480`, listing repo/path/branch, `test_commands`, `repo_urls`).
- **[Design decision] Scheduler gate split:** quiet gate (machine-global, unchanged) gates quiet-window workflows; idle gate (separate 2-poll streak, key `idle_gate_last_ok`) gates `roadmap-dev`'s drain; phase 1 of `roadmap-dev` runs on every fire regardless (the gate-closed early-return now applies only when no idle-gate workflow is selected).
- **[Note] Night** for the 2-slot cap = the existing `machine.quiet_window` (22:00–08:00); slot count re-evaluated at every drain-loop iteration.
- **[Note] `AgentResult` gains `pid: int | None`** (set at spawn; None on timeout-kill before spawn) for the plan's state bookkeeping (pids per the plan).
- **[Risk] Drain holds the global lock for hours:** other workflows and manual `--force` runs skip until it ends (lock-skip, exit 0) — accepted per plan.
- **[Risk] Local 27B planner may still attempt a question form headless:** run exits 1 → job outcome `failure` (`failure.md` written) — operator re-arms after reading it; expect to watch the first runs.
- **[Risk] Two night jobs saturate the 2 backend slots:** each runs at ~half effective throughput; explicitly accepted with the night-2 requirement.

## Blockers / Decisions (status 2026-11-21, post user answers)

- **[B1 — RESOLVED by user] No PR creation from agents.** Delivery = pushed attempt branch; PR/merge is human-level verification. All git over SSH (`y2d2`). No PAT anywhere in the workflow or bootstrap. Listing repo renamed `ARP_prompts` → **`y2d2/autonomous_task_overview`** (exists, empty — user-specified name, used for the vault submodule too).
- **[B2 — DECIDED by user] Vault submodule:** commit ONLY `.gitmodules` + the submodule path on the vault's current branch (`feature/orbit-rob-kickoff-slides`); the dirty slides work stays untouched; push after. Submodule path: `autonomous_task_overview/` (user: "use that name as well").
- **[B3 — DECIDED by user, selection pending] Initial `allowed_repos`:** seed with multiple repos — user picks from the candidate list (asked; repos with active plans locally: `ARP_MPE`, `ARP_implementations`, `ARP_1A_anchored_implementations`, `ARP_utility_code`, `PRP_ARP_M`, `ARP_IMU`, `agentic_scripts`, `ARP_roadmap`). Set in `config/workflows.yaml` post-bootstrap (operator step, not a dev task).

## Acceptance (plan-level)

1. `uv run pytest -v` (full suite incl. new unit + smoke) passes hermetically — no real `opencode`, no network, no live mail.
2. `uv run agentic-scripts run --force --only roadmap-dev` with the shipped empty allowlist exits 0 and no-ops cleanly (action note, no state file, no sandbox).
3. With a fixture repo + approved plans + fake runner: day = 1 concurrent job, night = 2, no 30-min dead time between jobs (top-up on completion), gate close mid-drain = let-finish, review round-trip works, timeout → `failure`, crash → reaper → `open`, no duplicate branch pushes / re-executions on re-run, `success`/`failure` never auto-restart.
4. User edits in `plans.md` (approval/priority/remove/re-arm) survive any number of reconciles; a `success` row with `remove` ☑ disappears on the next scan.
5. Config typos fail fast with the offending dotted field named; `setup.sh` stays idempotent.
6. ruff check + format clean across the repo.
