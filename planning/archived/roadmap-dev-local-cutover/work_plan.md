# Task Plan: Local roadmap-dev cutover (≤50 chars)

**Purpose:** Stop the autonomous-task cron job and run the plan scan/list/execute workflow entirely from the agentic_scripts repo again, with the listing written into this repo's `plans.md`.

## Objective

Today the plan scanner (`roadmap-dev`) runs as a separate cron job from `/workspace/Python/autonomous_task_overview` (AT-OVERVIEW). The user wants that cron job stopped, and this repo's existing cron job (`agentic-scripts run`, which currently runs noop + mail-keeper + oc-todo) to instead:
1. scan the 9 allowed repos for un-archived `planning/**/work_plan.md` plans,
2. publish the live listing into **this repo's** `plans.md` (remote `y2d2/agentic_scripts` main + a local working-tree mirror), and
3. execute eligible plans via the `planner-enhanced` agent when the machine is idle.

Success = AT cron gone, `uv run agentic-scripts run` covers mail + issues + roadmap-dev, `plans.md` visible at this repo root, zero regressions to existing workflows/tests.

## Context (verified during planning)

- **Two crontab entries** (root): (a) `# agentic-scripts ...` + `*/30 * * * * cd /workspace/Python/agentic_scripts && PATH=... /root/.local/bin/uv run agentic-scripts run >> .../logs/cron.log 2>&1`, (b) `# autonomous-task` + `*/30 * * * * cd /workspace/Python/autonomous_task_overview && ... autonomous-task run >> .../logs/cron.log 2>&1`. Only (b) and its comment line are removed. `/etc/cron.d/*` entries are unrelated — untouched.
- **Port source**: AT-OVERVIEW checkout `/workspace/Python/autonomous_task_overview`, branch `feature/listing-detail-row` @ `899ce44` (clean tree). It carries the *evolved* `roadmap_dev.py` (3395 lines, per-plan-section `plans.md` renderer, commits `15d49f6`/`e6a69c9`/`899ce44`) **and its adapted test suite** (`tests/test_roadmap_dev.py`, `tests/test_roadmap_dev_scan.py`, `tests/test_roadmap_dev_pipeline.py`, `tests/smoke/test_smoke_roadmap_dev.py`), which no longer exist in agentic_scripts (deleted by `80e0820` here).
- **Framework is already compatible**: `git.py`, `agent.py`, `state.py`, `workflows/base.py`, `sessions.py` are byte-identical between the two repos (modulo `autonomous_task`→`agentic_scripts` rename). Only `config.py` differs (~305 diff lines — the removed `RoadmapPrompts` section). All `Git` helper methods used by `roadmap_dev.py` exist in agentic_scripts' `git.py`.
- **Gate infrastructure retained in agentic_scripts**: `scheduler.py` already implements per-workflow gates — `config.py` `Workflow.gate: "quiet_window"|"idle"` and the run loop (≈lines 600–712) evaluates the session-based idle gate (via `sessions.read_active_sessions()`) and lets `gate: idle` workflows run even when the global quiet-window gate is CLOSED. The global quiet window (22:00–08:00, load1 < 32) keeps gating mail-keeper/oc-todo/noop.
- **Idle gate semantics**: opens iff the shared OpenCode service reports **0 active sessions**, sustained across 2 consecutive 30-min polls (`gate_polls_required: 2`, tolerance 10 min). No quiet window. This is what "executes when it can" means — overnight *or* daytime idle.
- **Executor agent**: `planner-enhanced` (exists at `/root/.config/opencode/agents/planner-enhanced.md`; `roadmap_dev.py` hardcodes `_AGENT_NAME = "planner-enhanced"`).
- **Listing mechanics in code**: `_fetch_listing()` reads `listing_path` (`plans.md`) on `listing_branch` (`main`) of a sandbox clone of `listing_repo`; `_reconcile_and_push()` renders byte-stable per-plan sections, commits `OC: roadmap-dev: reconcile listing (run <id>)`, pushes with fetch-retry on conflict.
- **Live state**: AT-OVERVIEW `state/roadmap-dev.json` (updated 2026-11-26) holds current plan-identity tracking (77 items). agentic_scripts' `state/roadmap-dev.json` is stale (2026-11-22) and must be replaced by the fresh copy so processed items aren't re-tracked from scratch.
- **Branch**: agentic_scripts is on `feature/roadmap-dev-workflow` (tracks origin). Work is committed here with `OC:` prefix + push (git-workflow skill). Untracked `planning/*` session artifacts exist — stage only explicit paths, never `git add -A`.

## Tasks

### Task 1: Cron cutover + state snapshot (ops, no code)
- **Files:** root crontab (modify); `/workspace/Python/agentic_scripts/state/roadmap-dev.json` (overwrite); backup `logs/crontab-backup-20261126.txt` (create).
- **Do:** verify no `autonomous-task`/`autonomous_task` process is running; back up `crontab -l`; delete the `# autonomous-task` comment line and the line containing `autonomous_task_overview`; install; copy AT-OVERVIEW `state/roadmap-dev.json` over agentic_scripts' stale copy.
- **Acceptance:** crontab shows only the agentic-scripts entry (+ its comment); agentic entry byte-identical to before; state file SHA-256 matches AT's; no AT process.

### Task 2: Port roadmap_dev module + RoadmapPrompts config + yaml entry (depends on #1)
- **Files:** `src/agentic_scripts/workflows/roadmap_dev.py` (create — copy from AT HEAD, rewrite `autonomous_task.` → `agentic_scripts.`); `src/agentic_scripts/config.py` (modify — transplant `RoadmapPrompts` dataclass + loader + `Config.roadmap_prompts` wiring from AT's `config.py`); `config/workflows.yaml` (modify — add `roadmap_prompts:` section [9 `allowed_repos`, `listing_repo: y2d2/agentic_scripts`, `listing_repo_url: ""`, `listing_path: plans.md`, `listing_branch: main`, `run_timeout_minutes: 480`, `test_commands: {}`, `repo_urls: {}`] and `workflows.roadmap-dev:` [`enabled: true`, `module: agentic_scripts.workflows.roadmap_dev`, `agent: planner-enhanced`, `gate: idle`]).
- **Notes:** copy the AT file verbatim except import-path renames; also transplant any optional `RoadmapPrompts` field the module references (e.g. `local_listing` is introduced in Task 3 — do NOT add it here). Keep `noop`, `mail-keeper`, `oc-todo` yaml entries byte-identical. Commit `OC: Port roadmap-dev workflow back from autonomous_task_overview (module, config, yaml entry, gate: idle)` + push.
- **Acceptance:**
  1. `uv run python -c "from agentic_scripts.workflows.roadmap_dev import create"` exits 0.
  2. Config loads with the new yaml: `uv run python -c` snippet loading config via `agentic_scripts.config` and resolving enabled workflows (incl. importing `roadmap_dev`) exits 0.
  3. Existing suite unaffected: `uv run pytest tests/ -q -x` PASS (current tests don't touch roadmap yet).
  4. `uv run ruff check src config` (repo lint config) clean on changed files.

### Task 3: Listing destination → this repo + local plans.md mirror (depends on #2)
- **Files:** `src/agentic_scripts/workflows/roadmap_dev.py` (modify); `src/agentic_scripts/config.py` (modify); `config/workflows.yaml` (modify).
- **Do:**
  1. Add optional `RoadmapPrompts.local_listing: str | None` (YAML key `local_listing`, default `"plans.md"`; `null` disables). Resolve it against the same project-root basis `config.py` already uses for relative `paths.*`.
  2. In the reconcile path (after the remote push step of `_reconcile_and_push`, and also when the remote push is skipped because the listing is unchanged — always keep the mirror fresh): write the rendered listing text to `<project root>/<local_listing>` when content differs; wrap in try/except → on failure log `listing mirror write failed: ...` at ERROR but do **not** add it to workflow errors/abort. On write, append action string `listing mirrored to <path>`.
  3. Update module docstring lines that reference the old listing repo (`ARP_prompts/plans.md` / autonomous_task_overview) to say the listing lives at `y2d2/agentic_scripts` main, mirrored to the local project-root `plans.md`.
- **Notes:** canonical state cells remain the **remote** listing (user edits must be committed+pushed to drive re-arming — existing design). The mirror is read-only from the workflow's perspective. Do not change push/retry logic. Commit `OC: roadmap-dev — listing repo is y2d2/agentic_scripts; mirror plans.md into project root` + push.
- **Acceptance:**
  1. Import/config-load checks from Task 2 still pass.
  2. `grep -n "local_listing" src/agentic_scripts/config.py` shows the field + loader + validation (must be a non-empty string or None).
  3. Mirror call-site exists in the reconcile path and cannot raise into the caller (try/except verified by inspection).

### Task 4: Port test suite + full green (depends on #3)
- **Files:** `tests/test_roadmap_dev.py`, `tests/test_roadmap_dev_scan.py`, `tests/test_roadmap_dev_pipeline.py`, `tests/smoke/test_smoke_roadmap_dev.py` (create — copy from AT HEAD, rewrite `autonomous_task` → `agentic_scripts`); `tests/conftest.py`, `tests/smoke/conftest.py` (modify — restore roadmap-related fixtures from AT where agentic_scripts dropped them in `80e0820`); `tests/test_config.py`, `tests/test_scheduler.py` (modify — transplant AT's roadmap_prompts / idle-gate-with-roadmap-dev test cases missing here).
- **Notes:** AT tests are already adapted to the evolved per-plan-section renderer — keep their assertions; only package renames + fixture merges. Adapt any test that asserts listing-repo identity to the new config (`listing_repo: y2d2/agentic_scripts`, `local_listing`). Add ≥2 new tests: (a) mirror file written with rendered text at `<tmp project root>/plans.md`; (b) `local_listing: null` disables the write. All hermetic — no real network/GitHub (fixture clones/`repo_urls` overrides per existing smoke patterns). Commit `OC: Port roadmap-dev test suite (core, scan, pipeline, smoke) + local-listing tests` + push.
- **Acceptance:**
  1. `uv run pytest tests/ -q` fully PASS (zero failures, zero roadmap skips).
  2. `uv run ruff check .` clean.
  3. Smoke run writes the mirror inside a temp dir only (inspect test).

### Task 5: Validation run + README + archive note (depends on #4)
- **Files:** `README.md` (modify — restore a roadmap-dev section: pipeline, `plans.md` control surface incl. re-arming `failure→open` state cells, `gate: idle` semantics, local mirror; adapt the mermaid diagram from AT README @ `899ce44`); `logs/` + `state/` artifacts (observe only).
- **Do:** from `/workspace/Python/agentic_scripts`, run `uv run agentic-scripts run --only roadmap-dev` **without `--force`** (active OpenCode sessions keep the idle gate closed → scan + listing reconcile only, no plan drain — this is the safety property that makes the run non-destructive). Inspect `logs/run-*.log`, `logs/last-run.txt`, `state/roadmap-dev.json`, and root `plans.md`. Confirm mail/oc-todo/noop config untouched. Commit `OC: README — roadmap-dev workflow restored locally (plans.md listing, idle gate)` + push.
- **Acceptance:**
  1. Run exits 0; log shows scan actions and a listing reconcile/mirror action; **no** `planner-enhanced` agent spawn lines.
  2. `/workspace/Python/agentic_scripts/plans.md` exists with per-plan sections for the discovered un-archived plans.
  3. `state/roadmap-dev.json` in agentic_scripts updated by this run.
  4. Next scheduled cron tick (≤30 min later, or simulated with a second identical manual run) shows the agentic-scripts cron entry still intact and still running mail/issues workflows per their quiet gate.

## Parallel

None — all tasks touch the same repo/module and must run strictly in order 1→2→3→4→5.

## Out of Scope

- Deleting or modifying `/workspace/Python/autonomous_task_overview` source, git history, or its remote (only its crontab entry dies).
- Any change to noop / mail-keeper / oc-todo modules or their gates.
- New agents, opencode.jsonc changes, `/etc/cron.d` entries, systemd (not available in this container).
- Executing any real plan during validation (drain happens only on a future idle-gate-open tick).
- Migrating AT-OVERVIEW's sandbox clones (fresh fetches are the default; reuse was rejected for worktree-path safety).

## Notes

- `[Assumption]` Port source = AT-OVERVIEW `feature/listing-detail-row` @ `899ce44` (its 2 unmerged renderer commits are wanted: they are the newest `plans.md` format). If the user prefers AT `main` as source, re-cut Task 2.
- `[Assumption]` The remote canonical listing moves to `y2d2/agentic_scripts` main; the AT repo's `plans.md` becomes frozen history.
- `[Assumption]` User edits to `plans.md` drive execution only after commit+push to `y2d2/agentic_scripts` (existing reconcile reads remote). The mirror keeps the local copy visible/editable.
- Risk: first run re-fetches 9 repos into `sandbox/roadmap-dev/` (network, minutes). Nov 25 showed one `Permission denied (publickey)` for `y2d2/ARP_IMU`; today's AT run reported 0 errors — if the scan logs that repo's fetch failure, it's a pre-existing access issue, not a regression; report, don't fix.
- Risk: untracked `planning/*` files on the current branch — all commits stage explicit paths only.
- Task 5 must NOT use `--force` (it bypasses both gates and would spawn real 480-min plan executions).
