# Task Plan: Cron cutover + state snapshot

**Task:** #1    **Session:** roadmap-dev-local-cutover

## Objective

Stop the autonomous-task cron job (the migrated roadmap-dev runner at `/workspace/Python/autonomous_task_overview`) and snapshot its live plan-tracking state into this repo, so the workflow can be re-hosted here without double-running.

## Context

- Root crontab (`crontab -l`) currently contains exactly two managed entries:
  1. `# agentic-scripts (fixed 2026-10-23: absolute uv path + PATH incl. opencode; previous line failed 78x with 'uv: not found')` followed by `*/30 * * * * cd /workspace/Python/agentic_scripts && PATH=/root/.opencode/bin:/root/.local/bin:/usr/local/bin:/usr/bin:/bin /root/.local/bin/uv run agentic-scripts run >> /workspace/Python/agentic_scripts/logs/cron.log 2>&1` — **KEEP byte-identical**.
  2. `# autonomous-task` followed by `*/30 * * * * cd /workspace/Python/autonomous_task_overview && PATH=/root/.opencode/bin:/root/.local/bin:/usr/local/bin:/usr/bin:/bin /root/.local/bin/uv run autonomous-task run >> /workspace/Python/autonomous_task_overview/logs/cron.log 2>&1` — **REMOVE both lines**.
- `/etc/cron.d/` entries are unrelated system jobs — never touch.
- The AT job ran its last completed run at 2026-11-26T19:00 with status ok (no in-flight jobs expected, but verify).
- AT-OVERVIEW live state: `/workspace/Python/autonomous_task_overview/state/roadmap-dev.json` (schema-compatible with this repo's `StateStore`). This repo's copy `/workspace/Python/agentic_scripts/state/roadmap-dev.json` is stale (2026-11-22) and must be replaced.

## Tasks

### Task 1: Remove AT cron entry and copy state
- **Files:** root crontab (modify), `/workspace/Python/agentic_scripts/logs/crontab-backup-20261126.txt` (create), `/workspace/Python/agentic_scripts/state/roadmap-dev.json` (overwrite).
- **Do:**
  1. `pgrep -af "autonomous.task|autonomous_task"` — must show nothing; if a process is running, STOP and report (do not kill).
  2. `crontab -l > /workspace/Python/agentic_scripts/logs/crontab-backup-20261126.txt`
  3. Produce the new crontab by filtering out exactly the line `# autonomous-task` and any line containing `autonomous_task_overview`, e.g. `crontab -l | grep -vE '^# autonomous-task$|autonomous_task_overview' | crontab -`. Do not reorder or reformat remaining lines.
  4. `sha256sum /workspace/Python/autonomous_task_overview/state/roadmap-dev.json` then `cp` it to `/workspace/Python/agentic_scripts/state/roadmap-dev.json` and `sha256sum` again — hashes must match.
  5. Do NOT delete or edit anything under `/workspace/Python/autonomous_task_overview` itself.
- **Notes:** This is an ops task — no source-file changes, no commits needed (state file lives under `state/` which is runtime data; do not commit it).
- **Acceptance:**
  1. `crontab -l` contains no line matching `autonomous_task_overview` and no `# autonomous-task` line.
  2. The agentic-scripts entry (comment + `*/30` line) is present and byte-identical to the backup.
  3. Backup file exists with the original 4-entry content.
  4. SHA-256 of `/workspace/Python/agentic_scripts/state/roadmap-dev.json` equals AT's.

## Out of Scope

- Removing/altering the agentic-scripts cron entry.
- Any code, config, or test change.
- Deleting the AT repo or its crontab logs.

## Notes

- If `crontab` install fails, restore the backup immediately (`crontab <backup>`) and report.
