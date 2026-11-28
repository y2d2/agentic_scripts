# Task Plan: Merge to main + live state snapshot + forced-run validation (pre-gate evidence)

**Task:** #4    **Plan:** `autonomous-task-rehome`    **Repos:** overview (merge+run) and agentic_scripts (baseline run only — READ/execute, no edits)

## Objective

Land the re-homed engine on overview `main`, migrate the LIVE plan-tracking state, and
produce the evidence pack for the user cutover gate: old engine still authoritative; new
engine proven by forced runs only (NO cron changes in this task).

## Steps

1. **Merge:** in overview, merge `feature/rehome-final` → `main` (ff when possible), push
   `main`. Baseline note (from Task 1): `main` had advanced to `e99307f` (PR #1 merged
   `feature/listing-detail-row`) — use CURRENT `main` as merge base / A-B baseline. If
   `origin/main` advanced further (engine commits cannot exist — no engine fires — but listing
   commits could), merge them in first, then push.
2. **Setup:** `bash scripts/setup.sh --skip-timer` (crontab must stay byte-identical — record
   `crontab -l | md5sum` before and after; they MUST match).
3. **State snapshot:** copy `/workspace/Python/agentic_scripts/state/roadmap-dev.json` (live)
   OVER `/workspace/Python/autonomous_task_overview/state/roadmap-dev.json`. Record SHA-256 of
   both (must match). Commit? NO — `state/` is gitignored runtime data; do not stage.
4. **Baseline A (old engine, still live):** trigger one forced run in agentic_scripts
   (`uv run agentic-scripts run --force --only roadmap-dev` if supported, else the documented
   force path). Record: run-log final line, `plans.md` content hash + git tip of
   `y2d2/agentic_scripts` main after, state entries count (add/remove/modify diff vs before).
5. **Run B (new engine):** forced run in overview (`uv run autonomous-task run --force` —
   verify the flag in `runner.py`; setup used `--skip-timer` so no cron exists yet). Record:
   run-log, exit code, ERROR count, listing push to overview `main` (new `plans.md` commit or
   no-op), state diff.
6. **Run C (stability):** one more forced run in overview; second run must render
   byte-identical `plans.md` (no churn commit) and no new state entries.
7. **Evidence report:** write everything into the task result file, including the A-listing vs
   B-listing entry-set comparison (same plan identities expected; renderer + listing target
   changed, so byte-identity A↔B is NOT expected — instead verify: every open plan identity in
   A's listing appears in B's listing; B contains no invented plans).

## Acceptance criteria

| # | Check | Pass condition |
|---|---|---|
| 1 | Merge | overview `main` contains the re-homed code (`git log main -1` shows merge/ff of `feature/rehome-final`) |
| 2 | Cron guard | `crontab -l` md5 identical before/after the task (NO new entry yet) |
| 3 | State | SHA-256 of both `roadmap-dev.json` files equal at snapshot time |
| 4 | Run B | exit 0, 0 ERROR lines, `WORKFLOW roadmap-dev status=ok`, listing push to overview `main` present (or clean no-op) |
| 5 | Run C | second render byte-identical (no listing churn commit, no state add) |
| 6 | Listing parity | A-listing and B-listing contain the same set of plan identities (report both lists) |
| 7 | agentic untouched | no new commits in agentic_scripts from this task |

## Out of scope

No cron install, NO removal of anything from agentic_scripts, no state edits beyond the copy.
