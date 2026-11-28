# Task Plan: Install `# autonomous-task` cron + one gate-checked fire + one-engine proof

**Task:** #6    **Plan:** `autonomous-task-rehome`    **Scope:** root crontab + `/workspace/Python/autonomous_task_overview`

## Objective

Arm the re-homed engine's 30-minute timer (marker `# autonomous-task`), verify exactly one
real gate-checked fire from the overview repo, and prove the OLD engine no longer scans for
plans (its workflow entry is gone).

## Steps

0. **Final state sync (new, per orchestrator):** Task 5 has already disarmed roadmap-dev in
   `agentic_scripts`, so its `state/roadmap-dev.json` is final. Re-copy it OVER the overview's
   copy (which came from Task 4's earlier snapshot); record SHA-256 both sides + item-count diff
   vs Task 4's snapshot (explain every delta). Only then touch the crontab.
1. **Precondition guard (stop on any failure):**
   - `crontab -l`: contains the `# agentic-scripts` entry; contains NO `# autonomous-task` line.
   - `grep -c roadmap-dev /workspace/Python/agentic_scripts/config/workflows.yaml` → 0.
   - No `roadmap`/`autonomous-task` process running (`ps aux | grep -E 'autonomous-task|roadmap'`).
2. **Install:** in the overview repo run `bash scripts/setup.sh` (NO `--skip-timer`). The
   script's cron branch installs under marker `# autonomous-task` with the hardened absolute-uv
   + PATH line. Verify `crontab -l` diff = exactly the marker + one `*/30` entry; the
   `# agentic-scripts` entry byte-identical (md5 before/after on just that entry).
3. **One gate-checked fire:** wait for the next `*/30` boundary (or the fastest documented
   manual trigger that keeps gate checks — NOT `--force`). Inspect the produced
   `logs/run-*.log` + `logs/last-run.txt` in the overview repo.
4. **One-engine proof:** after the fire, `agentic_scripts/logs/run-*.log` for the same window
   shows `WORKFLOW roadmap-dev` ABSENT (noop/mail-keeper/oc-todo lines may appear/skip).
5. Report in the result file: crontab diff, fire log tail, last-run.txt, proof lines.

## Acceptance criteria

| # | Check | Pass condition |
|---|---|---|
| 1 | Guard | all three preconditions PASS before any change |
| 2 | Install | crontab diff = exactly marker + hardened `*/30` entry; old entry unchanged |
| 3 | Fire | one run log in overview: `WORKFLOW roadmap-dev status=ok`, 0 ERROR, exit recorded in `last-run.txt` |
| 4 | Listing | overview `main` received a listing commit OR the render was a clean no-op (state untouched) — either recorded |
| 5 | Single engine | same-window agentic_scripts log has NO roadmap-dev workflow line; `grep -c 'autonomous-task' crontab -l` = 1 entry |

## Out of scope

No code changes. If a criterion fails, STOP-and-report (do not retry cron surgery twice;
escalate).
