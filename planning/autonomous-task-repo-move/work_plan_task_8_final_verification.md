# Task Plan: Final end-to-end verification

**Purpose:** After the cutover is armed (Tasks 6–7), produce the single end-to-end
evidence pack proving: both repos' suites green, the listing byte-identical pre/post
cutover, exactly one roadmap engine armed, state intact, and a working rollback path.

## Objective

Verify the post-cutover world in one pass across both repos and the system, and write
the evidence pack the orchestrator presents at the completion gate:
(1) `agentic_scripts` suite 100% green on its post-cleanup commit;
(2) overview-repo suite 100% green on `main`;
(3) the listing tip chain from the cutover baseline (`d119c66`, Task 5) to NOW contains
ONLY `OC: roadmap-dev: reconcile listing (…)` commits, and the content delta vs the
cutover baseline is exactly the documented live-world changes (see Context);
(4) exactly one engine armed (new `# autonomous-task` cron + old
`# agentic-scripts` cron with a roadmap-dev-free config);
(5) state file at the NEW location: 90 entries, all `open`, max attempt 0;
(6) `last-run.txt` at the new location shows `roadmap-dev=ok` / `overall: ok` from a
natural (gate-checked) fire;
(7) the rollback path is documented and one-step.

## Context

- **Both repos (post-cutover world):**
  - `/workspace/Python/agentic_scripts` — branch `feature/roadmap-dev-workflow`, tip =
    the Task 6 cleanup commit (pushed). roadmap-dev module/config/tests/staging dir are
    GONE; remaining workflows: noop, mail-keeper, oc-todo. Its cron entry
    (`# agentic-scripts`) still fires it every 30 min (now roadmap-dev-free).
  - `/workspace/Python/autonomous_task_overview` — checkout `main` (engine + docs
    merged; tip was `d119c66` at Task 5, since advanced by listing-only reconciles —
    see below). Its cron entry (`# autonomous-task`) fires `autonomous-task run`
    every 30 min. `state/roadmap-dev.json` migrated (90 entries, all open, attempt 0).
    `plans.md` = live listing (engine-reconciled).
- **Baseline evidence (from work-plan Task 5's result report — read it):**
  `A_TIP = d119c66…` + `A_HASH = 93d538…` (old engine's post-forced-run listing tip +
  plans.md content sha256), the state guard counts (89 all-open), and the new
  engine's `B_TIP`/`B_HASH` (== A, byte-identical).
- **Documented live-world changes after the cutover baseline (all legitimate, all
  listed in the Task 7 report — verify the chain against them, not against a static
  hash):**
  1. `4345ebc` (run 20261124T083001Z, OLD engine's last fire pre-Task-7): listing-only,
     −2 lines — real-world deletion of the `beam-flip-event-detection` plan.
  2. `252c176` (run 20261124T102647Z, NEW engine's first fire): listing-only, +1/−1 —
     the user's 09:35:41 revision of the `planning/orbit-rob-kickoff-slides/` folder
     changed the orbit-rob row's priority (17→18); scan Rule 2 legitimately discovered
     the new revision.
  3. State: 89 → 90 between the Task 5 migration and Task 7's fire — exactly one entry
     added (open, attempt 0, no pid), zero modified, zero removed; NO drain start
     (0 approved rows).
- **Result reports to consult:** `lightweight_dev_task_5_merge_cutover_check.md`
  (baseline + A/B evidence), `lightweight_dev_task_6_cleanup.md` (cleanup commit +
  suite), `lightweight_dev_task_7_cron_install.md` (crontab diff + gate-checked fire).
- **Git hygiene:** read-only task — NO commits, NO changes in either repo, NO crontab
  edits. In `agentic_scripts`, NEVER `git add` anything (untracked
  `planning/mail-keeper-pruning/` files must stay untouched).

## Tasks

### Task 1: Suite verification (both repos)
- **Do:**
  1. `cd /workspace/Python/agentic_scripts && uv run pytest -q` (full remaining suite) + `uv run agentic-scripts run --help`.
  2. `cd /workspace/Python/autonomous_task_overview && uv run pytest -q` (full moved suite) + `uv run autonomous-task run --help`.
- **Acceptance:**
  1. Both suites 100% green (record test counts per repo); both CLIs exit 0.

### Task 2: One-engine proof
- **Do:**
  1. `crontab -l` — record verbatim; assert exactly two engine entries: `# agentic-scripts` (byte-identical to the pre-cutover line — compare against the line recorded in the Task 5/6/7 reports) and `# autonomous-task` (the Task 7 line). No other engine-like entries.
  2. Old engine roadmap-free: `grep -c roadmap /workspace/Python/agentic_scripts/config/workflows.yaml` = 0; `ls /workspace/Python/agentic_scripts/src/agentic_scripts/workflows/` shows no `roadmap_dev.py`; `ls /workspace/Python/agentic_scripts/tests/` shows no `test_roadmap_dev*.py`.
  3. New engine armed: `grep -c autonomous_task /workspace/Python/autonomous_task_overview/src/autonomous_task/workflows/roadmap_dev.py` > 0 (module present on main); `git -C /workspace/Python/autonomous_task_overview log --oneline -3` shows the merged engine commits on main.
- **Acceptance:**
  1. Exactly one roadmap engine can fire (the new one); the old entry runs only the remaining workflows (proof = config + module absence).

### Task 3: Listing + state identity
- **Do:**
  1. `git ls-remote git@github.com:y2d2/autonomous_task_overview.git refs/heads/main` → `NOW_TIP`.
  2. Compare against `A_TIP` (Task 5 baseline): if `NOW_TIP == A_TIP`, content identity holds trivially (also compare hashes: `git show A_TIP:plans.md | sha256sum` from the old engine's listing clone vs `git show NOW_TIP:plans.md | sha256sum` from the new engine's clone — must match). If `NOW_TIP != A_TIP`: enumerate `git log --oneline A_TIP..NOW_TIP` (via either clone after fetch) — every commit must be a legitimate engine reconcile (`OC: roadmap-dev: reconcile listing (…)`); then verify `git show NOW_TIP:plans.md | sha256sum` equals a FRESH render — the simplest proof: the Task 7 gate-checked fire already re-verified byte-identity post-merge; record its tip/hash and confirm `NOW_TIP`'s hash equals it (or that the only delta is listing-only content).
  3. State: `python3 -c "import json; p=json.load(open('/workspace/Python/autonomous_task_overview/state/roadmap-dev.json'))['plans']; print(len(p), {s: sum(1 for v in p.values() if v['state']==s) for s in set(v['state'] for v in p.values())}, max(v['attempt'] for v in p.values()))"` → record (expected: 90, all open, max attempt 0).
  4. `cat /workspace/Python/autonomous_task_overview/logs/last-run.txt` → record verbatim (expected: `roadmap-dev=ok`, `overall: ok`; `trigger: gate` from the last natural/gate-checked fire).
- **Acceptance:**
  1. `A_TIP..NOW_TIP` contains ONLY `OC: roadmap-dev: reconcile listing (…)` commits and the content delta vs the cutover baseline is exactly the two documented changes in Context (or a superset of that same kind, each reconcile commit listing-only — record any additions); state 90 all-open attempt 0; last-run clean.

### Task 4: Rollback path documentation
- **Do:** In the result report, document the exact one-step rollback for the cutover: (a) `cd /workspace/Python/agentic_scripts && git revert HEAD && git push` (re-arms the old engine — its cron line was never removed); (b) remove the new cron entry: `crontab -l | sed '/# autonomous-task/d; /autonomous-task run/d' | crontab -` (record the exact two-line deletion); (c) note: the overview repo's `main` merge is ADDITIVE (the old engine's listing clone reads only `plans.md`), so no overview-repo revert is needed for rollback; (d) note: the migrated state file stays valid for BOTH engines (same schema, same key `state/roadmap-dev.json`). Do NOT execute any of it.
- **Acceptance:**
  1. The rollback section is complete, ordered, and marked NOT-executed.

### Task 5: Evidence pack
- **Do:** Assemble the result report: suite results (both repos, counts), crontab verbatim, one-engine proof lines, `NOW_TIP` + hash chain vs baseline, state summary, last-run.txt verbatim, rollback path, plus a final `git status` of both repos (clean, except the known untracked `planning/` files in agentic_scripts — `mail-keeper-pruning/` ×3 from a separate session and the `autonomous-task-repo-move/` plan+reports — which must remain untracked and unmodified).
- **Acceptance:**
  1. Every numbered evidence item present with exact values; no repo was modified by this task (`git status` clean in both; `git log -1` unchanged in both).

## Out of Scope
- Executing the rollback (documentation only).
- Live drain execution (0 approved rows; the user decides at the completion gate).
- Any commit/push in either repo.

## Notes
- **[Assumption]** The new engine's natural fires at 10:30, 11:00, 11:30 (during Task 7)
  were all clean (identical render → no push); more will occur between Task 7 and this
  task — that is expected and is exactly what the last-run.txt + tip checks capture. If
  `last-run.txt` shows an `overall: error`, do NOT proceed to the completion gate —
  report it as a blocker.
- **[Risk]** A natural fire of the OLD engine's remaining workflows (mail-keeper /
  oc-todo) is unrelated to this verification — their logs may show activity; ignore
  them (they are the pre-existing behavior of that repo).
