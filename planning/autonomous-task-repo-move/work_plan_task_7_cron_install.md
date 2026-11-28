# Task Plan: Install the new cron entry + verify a gate-checked fire

**Purpose:** Arm the new engine's 30-minute timer — installed by the engine's OWN
`scripts/setup.sh` (without `--skip-timer`) — and prove one non-forced (gate-checked)
fire from the new location lands cleanly. Runs ONLY after work-plan Task 6 (the
agentic_scripts cleanup) has committed, so at no moment do two roadmap engines exist.

## Objective

In `/workspace/Python/autonomous_task_overview` (on `main`, engine merged; state file
migrated; old engine already roadmap-dev-free per Task 6), run
`bash scripts/setup.sh` (timer valve OPEN) so the `# autonomous-task` cron entry is
installed; verify the crontab holds exactly the two intended engine entries; then run
one NON-forced `uv run autonomous-task run` (a real gate-checked fire) and verify the
phase-1 run logs with zero errors, the listing unchanged (byte-identical), and
`last-run.txt` showing `roadmap-dev=ok`.

## Context

- **Overview clone (live engine home):** `/workspace/Python/autonomous_task_overview`,
  checkout `main` (engine + docs merged, pushed). `state/roadmap-dev.json` already
  holds the migrated entries (re-verify count = 82, all `open`, attempt 0 — if any
  entry is `pending`, STOP and report: a job in flight changes the gate-checked
  run's behavior). `scripts/setup.sh` exists with the `--skip-timer` valve; WITHOUT the
  flag it installs the timer (systemd on real hosts — not this container; cron here).
  Its cron line (from Task 3's spec): `*/30 * * * * cd /workspace/Python/autonomous_task_overview && PATH=/root/.opencode/bin:/root/.local/bin:/usr/local/bin:/usr/bin:/bin /root/.local/bin/uv run autonomous-task run >> /workspace/Python/autonomous_task_overview/logs/cron.log 2>&1` under marker `# autonomous-task`.
- **The other engine:** `/workspace/Python/agentic_scripts` — after Task 6 its config
  has no roadmap-dev and the module is deleted; its cron entry (`# agentic-scripts`)
  MUST remain untouched and byte-identical (it now fires only noop/mail-keeper/
  oc-todo).
- **Expected final crontab:** exactly the old `# agentic-scripts` marker + entry
  (unchanged) and the new `# autonomous-task` marker + entry. Nothing else.
- **Gate-checked fire semantics:** a non-forced run evaluates the idle gate with the
  REAL session probe (`read_active_sessions` — OpenCode service state). Two outcomes,
  both valid: 0 active sessions → the gate records/opens its streak (if the streak is
  already set from the A/B verification, it may OPEN → the drain then finds 0 approved
  rows and starts nothing, logging the no-startable note) or >0 sessions → gate
  CLOSED, drain skipped with `drain skipped (idle gate closed)`. Either way phase 1
  (reaper + scan + reconcile) runs. The run must exit 0 with zero ERROR lines.
- **Git conventions:** `OC:` prefix if anything must be committed (expected: nothing —
  cron + logs are outside the repo; `state/`/`logs/`/`sandbox/` are gitignored);
  `plans.md` never touched.

## Tasks

### Task 1: Precondition guard
- **Do:** Verify: (a) `git -C /workspace/Python/agentic_scripts log --oneline -1` shows the Task 6 cleanup commit and `git -C /workspace/Python/agentic_scripts/config/workflows.yaml | grep -c roadmap` = 0 (the old engine is roadmap-dev-free); (b) `git -C /workspace/Python/autonomous_task_overview branch --show-current` = `main` and `git status` clean; (c) `python3 -c "import json; p=json.load(open('/workspace/Python/autonomous_task_overview/state/roadmap-dev.json'))['plans']; print(len(p), sum(1 for v in p.values() if v['state']!='open'))"` prints `82 0` (or the verified current count with 0 non-open). (d) `crontab -l` has no `# autonomous-task` line yet.
- **Acceptance:** All four checks pass; any failure → STOP and report (do not install).

### Task 2: Install the timer via the engine's own setup
- **Do:** In the clone: `crontab -l > /tmp/crontab-pre.txt` (evidence), then `bash scripts/setup.sh` (NO `--skip-timer`) → exit 0. Then `crontab -l > /tmp/crontab-post.txt`.
- **Acceptance:**
  1. Setup exit 0 (uv sync ok, agents found, preflight warn-or-ok, dirs present, timer installed).
  2. `diff /tmp/crontab-pre.txt /tmp/crontab-post.txt` shows ONLY the addition of the `# autonomous-task` marker line + the exact cron entry line (no other change — the old entry byte-identical).
  3. The new entry's command references the absolute uv path + the PATH incl. opencode (copy the exact line into the result report).
  4. The cron daemon is running (`pgrep -x cron` — setup ensures it; report the check).

### Task 3: One gate-checked (non-forced) fire
- **Do:** In the clone: `uv run autonomous-task run` (no `--force`). Record: exit code; the new `logs/run-*.log` (grep for ERROR — must be none; grep the `GATE` line and the `WORKFLOW roadmap-dev …` summary — record both); `logs/last-run.txt` (record verbatim); listing check: `git -C sandbox/roadmap-dev/prompts fetch -q origin && git -C sandbox/roadmap-dev/prompts rev-parse origin/main` + `git -C sandbox/roadmap-dev/prompts show <tip>:plans.md | sha256sum` (the tip may equal the Task 5 B_TIP — the fire must not change the listing when nothing changed; if it advanced, the advance must be a legitimate reconcile commit — record the diff, which must be listing-only).
- **Acceptance:**
  1. Exit 0; zero ERROR lines in the run log.
  2. The GATE line shows the real probe's verdict (record `active_sessions=N`); the workflow ran: `WORKFLOW roadmap-dev status=ok …` (items_found = the live plan count, errors=0).
  3. `last-run.txt`: `trigger: gate`, `workflows: roadmap-dev=ok(…)`, `overall: ok`.
  4. Listing unchanged: tip + hash identical to the Task 5 evidence (or a listing-only reconcile commit — recorded).
  5. State file: count unchanged, all open (a drain start is impossible with 0 approved rows; if any state entry changed, STOP and report).

### Task 4: Report
- **Do:** Result report with: crontab pre/post diff (verbatim), the new cron line, setup output summary, the run log excerpts (GATE + WORKFLOW lines, ERROR-grep result), last-run.txt verbatim, listing tip + hash, state count, and the one-engine proof: old config grep = 0 roadmap + new cron present = exactly one roadmap engine armed.
- **Acceptance:**
  1. Every artifact above present with exact values.
  2. No commit was needed (if one WAS made, it is justified in the report with an `OC:` message and pushed).

## Out of Scope
- Waiting for a NATURAL 30-min fire (the manual gate-checked run is the equivalent
  proof; the orchestrator will additionally check `last-run.txt` at the next natural
  fire window during the completion gate).
- Any change in `agentic_scripts`.

## Notes
- **[Risk]** The manual non-forced run consults the REAL session probe — if the user
  has an interactive OpenCode session open, the gate reports it (CLOSED, streak
  cleared). That is correct behavior, not a failure — record the probe value.
- **[Risk]** If the cron daemon is not running after setup (container quirk), the setup
  script's cron branch handles install+start (source pattern); a second
  `service cron start` may be needed — report whatever was required.
- **[Convention]** This task creates NO repo artifacts — its evidence is system state
  (crontab, logs, listing tip) captured in the result report.
