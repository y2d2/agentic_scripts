# Task Plan: Final end-to-end verification (both repos)

**Task:** #7    **Plan:** `autonomous-task-rehome`    **Scope:** read-only verification + result file

## Objective

Prove the end state: one engine, one listing, no roadmap-dev anywhere in `agentic_scripts`,
both suites green, rollback path valid.

## Checks (run all; record every command + output in the result file)

1. **Suites:** `uv run pytest tests/ -q` green in BOTH repos; `uv run ruff check src tests config` clean in both.
2. **Code absence:** in `agentic_scripts`: `grep -rn roadmap src/ tests/ config/ scripts/` = 0
   hits (README banner excepted); `src/agentic_scripts/workflows/roadmap_dev.py` absent;
   root `plans.md` absent (branch + main).
3. **Code presence:** in overview `main`: `roadmap_dev.py` present with `task_done_labels`
   (grep) and 3-col renderer; `local_listing` in config + `config.py`.
4. **One engine:** crontab has exactly one roadmap-scan entry (`# autonomous-task`); overview
   `logs/` shows a fire newer than the cleanup commit; agentic logs show no roadmap-dev lines
   after that commit's timestamp.
5. **State continuity:** overview `state/roadmap-dev.json` mtime advancing; item count ≥ the
   Task-4 snapshot count; no unexplained mass-deletion (diff count vs snapshot ≤ small delta
   with per-entry explanation if any).
6. **Rollback drill (paper, not executed):** result file documents the two rollback steps
   (revert agentic cleanup commit / delete `# autonomous-task` crontab lines) with exact
   commands, verified present in git log.
7. **Tip identity:** local `main` == `origin/main` in both repos; `feature/rehome-final` merged
   (no divergence); agentic feature branch pushed.

## Acceptance

ALL 7 checks PASS → verdict `READY FOR COMPLETION GATE`. Any FAIL → stop-and-report with the
failing output verbatim; do not attempt fixes.
