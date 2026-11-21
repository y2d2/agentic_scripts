# Task Plan: T5 — operator surface & bootstrap (docs, setup.sh, bootstrap script, task-overview staging)

**Purpose:** The human/operator surface for `roadmap-dev`: the README workflow section, `setup.sh` checks, the one-shot bootstrap script for the `y2d2/autonomous_task_overview` listing repo (pure git over SSH — NO REST, NO PAT), the initial repo content (plan-authoring README + `plans.md` skeleton) staged in this repo, and the vault-submodule wiring. Runs **in parallel with Task 4** (disjoint files; no code).

## Objective

Ship the operator-facing artifacts so that, once Tasks 3/4/6 land, a human can (a) understand the workflow from the README, (b) re-run `setup.sh` idempotently with the new checks green, (c) bootstrap the `y2d2/autonomous_task_overview` listing repo (push initial content over SSH; the repo exists and is empty) + the vault submodule (`autonomous_task_overview/` in ARP_roadmap — commit ONLY the submodule paths, never the vault's other uncommitted work) with one reviewed script, and (d) learn how to write plans from the autonomous_task_overview README itself.

## Context

- Work in `/workspace/Python/agentic_scripts` (branch `feature/roadmap-dev-workflow`). Read first: `README.md` (esp. the `## OC-todo workflow` section — mirror its sub-structure: `### Configuration` / `### How a run works` / `### Idempotency` (or equivalent) / `### Operator commands` / `### Where outputs live` / `### Guardrails`), `scripts/setup.sh` (numbered steps, `[OK]/[WARN]/[FAIL]` helpers, data-driven agent check over enabled workflows with non-null `agent`), `.env.example`, and the reviewed plan `workflows-roadmap-dev_plan.md` (listing contract, state machine, decisions — the README must match what Tasks 1–4 implement).
- **Live-verified facts (2026-11-21):** SSH to GitHub works as `y2d2` (all clone/push over `git@github.com:…`; NO PAT needed anywhere in this workflow — user decision: PR creation is human-level verification, so there is no GitHub REST at all). The listing repo `git@github.com:y2d2/autonomous_task_overview.git` EXISTS and is EMPTY (ls-remote 2026-11-21). The vault `/workspace/Obsidian/ARP_roadmap` is dirty (uncommitted slides work on `feature/orbit-rob-kickoff-slides`) — the submodule step must commit ONLY `.gitmodules` + the submodule path.
- **What the workflow (T1–T4) does — for the README:** every 30-min fire → Phase 1: scan `roadmap_prompts.allowed_repos` (all branches, sandbox clones) for `planning/<topic>/work_plan.md` outside `planning/archived/` + reconcile `plans.md` in `y2d2/autonomous_task_overview` (user-owned cells never clobbered); Phase 2: idle gate (no interactive OpenCode sessions, 2-poll rule, day or night); Phase 3: drain — slots 1 by day / 2 by night (night = 22:00–08:00), top-up on job end, let-finish on gate close. Job = headless `planner-enhanced` in a worktree on `roadmap-dev/<id>-<attempt>` from the plan's branch, 480-min timeout. Outcomes: success → PR (implementation + archived plan folder) on the attempt branch, base = plan's branch; questions → `questions.md` + checkmark removed on the plan's branch; failure/timeout → `failure.md` on the plan's branch; crash → reaper re-arms to `open`.
- **State machine (README table):** `open` (startable with ☑) / `pending` (job running) / `review` (questions raised; checkmark removed by workflow; startable once re-☑) / `success` (PR opened; removable via `remove` ☑) / `failure` (`failure.md`; re-arm = set state cell `open` or edit the plan → new identity).
- **The bootstrap script** must be POSIX-bash, `set -euo pipefail`, idempotent, and dry-run capable. It runs on THIS box (or any box with git + curl + the PAT in the environment or `.env`).

## Tasks

### Task 1: README section
- **Files:** `README.md` (modify)
- **Do:** Add a `## Roadmap-dev workflow` section directly after the `## OC-todo workflow` section (before `## Extending with a new workflow`), sub-sections mirroring the OC-todo structure:
  - **Overview** (2–4 sentences): unattended plan-execution engine; idle-triggered; PRs as delivery; listing as operator surface.
  - **Configuration (`roadmap_prompts.*` + `workflows.roadmap-dev`)**: table of fields (`allowed_repos` (empty = no-op), `listing_repo`/`listing_repo_url`/`listing_path`/`listing_branch`, `run_timeout_minutes` (480), `test_commands`, `repo_urls`), the entry (`agent: planner-enhanced`, `gate: idle`), and the idle-gate semantics (no interactive OpenCode sessions per `GET /api/session/active` on the shared service; 2-poll rule; worker `--standalone` runs invisible by construction).
  - **How a run works**: Phase 1 (scan all allowed repos, all branches, non-archived `planning/<topic>/work_plan.md`; reconcile `plans.md` — new rows `open`, user cells preserved, `remove` ☑ on `success` drops the row) → Phase 2 (idle gate) → Phase 3 (drain: slots 1 day / 2 night, top-up on completion, re-read table between jobs, periodic re-scan every 30 min mid-drain, let-finish on gate close) → job contract (review → major question → `questions.md`; else execute via `@lightweight-dev` strictly sequential, one small task at a time; report with explicit `Status:` line) → runner outcomes (success = verify + commit + archive + push the attempt branch — NO PR, a human opens it and verifies; questions = `OC:` commit on the plan's branch + uncheck; failure/timeout = `failure.md` on the plan's branch; crash = reaper → `open`).
  - **The listing** (`plans.md` layout sample — use the exact 2-section example from the plan doc; column legend; repo/branch as headers; identity = repo+branch+folder+content hash (edited plan = new row)).
  - **State machine**: the 5-state table (`success` = attempt branch pushed, human verifies/merges) + re-arm semantics.
  - **Operator commands**: `uv run agentic-scripts run --force --only roadmap-dev` (full scan + drain on demand), how to approve (☑ `approval`), re-prioritize (numeric `priority`), answer questions (edit `questions.md` on the branch + re-☑), re-arm a failure (`state` cell → `open`), remove a success row (☑ `remove`), open a PR from an attempt branch (human step: `git checkout roadmap-dev/<id>-<n>` in a local clone or the GitHub UI — the branch carries implementation + archived plan folder), prune attempt branches after merging (`git push origin --delete roadmap-dev/…` — manual, forensics), where to watch logs.
  - **Where outputs live**: `y2d2/autonomous_task_overview:plans.md` (listing), `state/roadmap-dev.json` (machine bookkeeping: attempts, pids, PR refs), `sandbox/roadmap-dev/{clones,wt,diag,prompts}/`, `logs/run-<id>.log` + `logs/last-run.txt`.
  - **Guardrails**: allowlist-only scanning; empty allowlist = no-op at ship; `success`/`failure` never auto-restart (a re-appeared `success` row stays `success` — never re-executed); NO GitHub API / no PR creation by the agent (PR + merge are human-level verification; attempt branches are the forensics the human opens as PRs and prunes); drain holds the global lock (other workflows skip until it ends — accepted); 8 h per-job hard timeout via process-group kill; worktree always cleaned (`finally` + reaper); all git over SSH — no PAT needed for roadmap-dev.
- **Acceptance:**
  1. `grep -n "^## " README.md` shows the new section between `OC-todo workflow` and `Extending with a new workflow`; the section contains the 6 sub-sections above; the state machine table and listing sample match the plan doc verbatim in substance (spot-check the 6 columns and the 5 states).

### Task 2: setup.sh checks
- **Files:** `scripts/setup.sh` (modify)
- **Do:** Insert a new numbered step (after step 5 "Registered-workflow agents", before runtime dirs — renumber subsequent steps): **roadmap-dev preflight** — read the `roadmap_prompts` section from `config/workflows.yaml` via the existing `uv run --project` python one-liner pattern:
  - if the section is absent or `allowed_repos` is empty → `[OK] roadmap-dev: allowlist empty — workflow is inert (no-op until repos are listed)`.
  - else: check each `allowed_repos` entry is reachable with `git ls-remote --exit-code <url> HEAD >/dev/null 2>&1` (URL = `repo_urls` override if present else `git@github.com:<repo>.git`; 15 s timeout via `timeout 15`) — `[OK]`/`[WARN]` (WARN, not FAIL: reachability is best-effort; the workflow logs repo errors at run time).
  - check `listing_repo` reachability the same way (URL = `listing_repo_url` override else `git@github.com:<listing_repo>.git`) → `[OK]`/`[FAIL]`? NO — `[WARN]` with a note `autonomous_task_overview not reachable — run scripts/bootstrap_task_overview.sh` (keep first-run idempotent; a WARN, not a FAIL).
  - Do NOT check the `planner-enhanced` agent separately — the existing data-driven step 5 covers it once the entry is `enabled: true` (T6 flips it); while disabled it is correctly not checked.
  - NO PAT check for roadmap-dev (there is no GitHub API in this workflow — all git over SSH; step 3's GITHUB_PAT handling stays as-is for oc-todo).
  - Keep every step idempotent; no new system packages.
- **Acceptance:**
  1. `bash -n scripts/setup.sh` clean; running `bash scripts/setup.sh` on this box ends with `[OK] setup complete (no failures)` (it currently does — the new steps must not introduce FAILs with the shipped empty allowlist) and prints the `roadmap-dev: allowlist empty` OK line.
  2. Re-running immediately produces identical output (idempotent).

### Task 3: Bootstrap script
- **Files:** `scripts/bootstrap_task_overview.sh` (create)
- **Do:** One-shot, idempotent, `--dry-run` prints the planned actions and exits 0. **Pure git over SSH — no REST, no PAT, no curl.** Behavior:
  1. `preflight()`: root dir = repo root (script's parent's parent); require `autonomous_task_overview/README.md` + `autonomous_task_overview/plans.md` to exist (else FAIL with a message); `LISTING_REPO` defaults to `y2d2/autonomous_task_overview` (overridable with `--repo owner/name`); `timeout 15 git ls-remote git@github.com:<LISTING_REPO>.git` must succeed (else FAIL `listing repo not reachable over SSH — check SSH key`); classify the remote: **empty** (zero refs) vs **populated** (≥1 ref).
  2. `push_initial()`: ONLY when the remote is empty (populated → `[OK] remote already populated — skipping initial push`). Temp dir (`mktemp -d`, trap cleanup); `git init -q` + `git config user.name/email` (reuse `git config user.name`/`user.email` if set, else `agentic-scripts`/`bot@localhost`); copy `autonomous_task_overview/*` (README.md + plans.md); `git add -A`; `git commit -m "OC: Initial task-overview content (plans listing + authoring guide)"`; `git branch -M main`; `git remote add origin git@github.com:<LISTING_REPO>.git`; `git push -u origin main` (SSH — no PAT); failure → FAIL with git's stderr tail (NEVER force-push).
  3. `add_submodule()`: only when `--vault <path>` is given (else print a reminder and skip — the workflow uses its own sandbox clone; the submodule is for Obsidian visibility): `git -C <vault> submodule add git@github.com:<LISTING_REPO>.git autonomous_task_overview` (path = `autonomous_task_overview/`, user-specified name; skip idempotently if it already resolves: `git -C <vault> config -f .gitmodules submodule.autonomous_task_overview.url` set), then `git -C <vault> add .gitmodules autonomous_task_overview` and `git -C <vault> commit -m "OC: Add autonomous_task_overview submodule (listing for roadmap-dev)"` + `git -C <vault> push` — **refuse** (exit 1, clear message) if the vault has uncommitted changes to ANY path OTHER than `.gitmodules` and `autonomous_task_overview` (check `git -C <vault> status --porcelain`, ignoring exactly those two paths) — never sweep the user's work into the submodule commit.
  4. Summary line per step (`[OK]/[FAIL]` style), exit 0 iff no FAIL.
- **Acceptance:**
  1. `bash -n scripts/bootstrap_task_overview.sh` clean.
  2. `bash scripts/bootstrap_task_overview.sh --dry-run` on this box → prints the planned steps (preflight [repo reachable, empty] → push_initial → submodule-reminder) and exits 0; `--dry-run` performs NO pushes, NO vault writes (its `git ls-remote` preflight probe is the only network call — acceptable: read-only).
  3. `--vault` with a dirty temp fixture vault (a scratch `git init` repo with one dirty unrelated file) → refuses with the uncommitted-work message, exit 1, nothing committed.
  4. Idempotent second run against a populated remote: `push_initial` skipped (`[OK] remote already populated`), submodule step skipped (already added), exit 0.
  5. No changes to any Python source file in this task; the script uses only git + coreutils (no curl, no python, no PAT).

### Task 4: autonomous_task_overview staging content
- **Files:** `autonomous_task_overview/README.md` (create), `autonomous_task_overview/plans.md` (create) — the staging dir holds exactly the two files that land in the `y2d2/autonomous_task_overview` repo (nothing else).
- **Do:**
  - `README.md` (the `autonomous_task_overview` repo's own README — the overview of the box's autonomous task execution; where plan authors learn the rules; concise, skimmable, no fluff):
    - **What this repo is**: the live listing (`plans.md`) of the unattended `roadmap-dev` plan-execution engine + the plan-authoring guide. `plans.md` is reconciled by the workflow on every 30-min scan — workflow-owned cells update automatically; user-owned cells (☑ `approval`, `priority`, ☑ `remove`, and the `failure`→`open` re-arm) are never clobbered. Executed plans land as pushed `roadmap-dev/<id>-<n>` branches (implementation + archived plan folder) — a human opens the PR and verifies.
    - **How to write a plan** (the load-bearing authoring contract): a plan = `planning/<topic>/work_plan.md` (+ optional `work_plan_task_<N>_<desc>.md` task files) in any allowed repo, any branch, OUTSIDE `planning/archived/`. Rules: (1) small, self-contained tasks — each task executable by one `lightweight-dev` dispatch with everything it needs in the task spec; (2) testable acceptance criteria — every task has at least one observable PASS condition; (3) a plan that needs a full 8-hour job should be split into several smaller plans (context size is the speed bottleneck); (4) what counts as a **major** question: anything that changes scope, requirements, or dependencies — NOT implementation detail (the headless planner decides minor things itself and records the decision); (5) an edited plan is a NEW plan (new row, new attempt numbering) — to re-arm a failed plan either set its `state` to `open` or edit the plan.
    - **The listing** (column legend + the exact section/table sample + priority semantics (ascending, 1 = first, ties by row order, new plans get max+1) + identity note).
    - **State machine** (the 5-state table with startable column, same as the agentic_scripts README).
    - **Operating the listing**: approve (☑ `approval`) / re-prioritize (change `priority`) / answer a review (edit `questions.md` on the plan's branch, commit/push, then re-☑) / re-arm a failure (`state` → `open`) / remove a success row (☑ `remove`; it reappears as `success` until the attempt branch is merged, then disappears) / open + merge the PR from the pushed attempt branch (human step) / delete a plan folder (row reconciles away — the escape hatch for a ping-ponging plan).
  - `plans.md` (skeleton the reconciler starts from — the listing doc):
    ```markdown
    # plans — roadmap-dev listing

    Reconciled automatically by the agentic_scripts `roadmap-dev` workflow (see README).
    Sections (`# <repo>` / `## <branch>`) appear as plans are discovered.
    ```
    (No sections yet — the reconciler creates them; this file must parse to zero rows with the workflow's `parse_listing` — the `#`/plain-text lines are skipped by design.)
- **Acceptance:**
  1. `autonomous_task_overview/` contains exactly `README.md` + `plans.md`; the README covers: what-the-repo-is, the 5 authoring rules (incl. the major-question definition), the listing legend, the state machine, the operating actions (incl. the human PR step).
  2. The skeleton `plans.md` parses to an empty listing (cross-checked in T6's tests — no test code in this task). It carries a short header (title + one pointer line to the README) and NO table sections yet.

## Out of Scope

- No Python source changes, no config changes (T6 flips `enabled` + sets the final `allowed_repos`), no smoke tests (T6), no execution of the bootstrap against the real GitHub (that is the orchestrator's post-approval operational step — the user has pre-approved it: push initial content + submodule-only vault commit + vault push).
- No `.env.example` change (roadmap-dev needs no PAT — all git over SSH; PR creation is human-level).

## Notes

- **[Decision, user 2026-11-21] NO PR creation by the agent and NO GitHub REST anywhere** — the bootstrap is pure git over SSH against the existing (empty) `y2d2/autonomous_task_overview` repo; no PAT, no curl.
- **[Assumption] Repo name/path:** listing repo = `y2d2/autonomous_task_overview`; vault submodule path = `autonomous_task_overview/` (user: "use that name as well in the ARP_roadmap submodule"). Config value `roadmap_prompts.listing_repo: y2d2/autonomous_task_overview` (T1 shipped the old name `y2d2/ARP_prompts` — T6 updates it; do NOT touch workflows.yaml in this task).
- **[Note] The README's "How a run works" must stay in sync with Tasks 3/4** — this task runs in parallel with T4; write it from the reviewed plan contract (above) and flag any discrepancy you notice in the result report's Blockers (do NOT edit T4's code).
- **[Note] Do not push to GitHub or touch the vault in this task** — the script is the deliverable; running it is a later operational step (the user has pre-approved that run: push initial content, submodule-only vault commit on the vault's current branch, vault push).
