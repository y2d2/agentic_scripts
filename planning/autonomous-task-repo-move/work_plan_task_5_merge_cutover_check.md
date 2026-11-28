# Task Plan: Merge to main + byte-identical cutover check

**Purpose:** Land the engine + docs on the overview repo's `main`, then prove — with the
old engine still authoritative — that the NEW engine, run from its future live location,
produces a byte-identical `plans.md` with all state intact. This is the evidence pack
for the user cutover gate.

## Objective

In `/workspace/Python/autonomous_task_overview` (branch `feature/engine-move` fully
green: package, suite, setup infra, docs), merge to `main` and push; then run a
controlled A/B: (A) one forced run of the OLD engine in
`/workspace/Python/agentic_scripts`, recording the listing tip + plans.md content hash
+ state; (B) set up the new engine in the persistent clone (setup `--skip-timer`,
state-file copy) and one forced run of it, recording the same three. Deliver the
evidence pack: byte-identical listing content, 82 state entries intact in the new
location, `last-run.txt` showing `roadmap-dev=ok` / `overall: ok`, zero ERROR lines,
crontab UNCHANGED (no new timer installed yet).

## Context

- **Overview clone:** `/workspace/Python/autonomous_task_overview`, branch
  `feature/engine-move` (pushed; suite green; `scripts/setup.sh` supports
  `--skip-timer`; package `autonomous_task`, console `autonomous-task`, config
  `config/workflows.yaml` with the live 9-repo allowlist + listing
  `y2d2/autonomous_task_overview`/`plans.md`/`main`). `plans.md` is the LIVE listing —
  never edit/stage it.
- **Old engine:** `/workspace/Python/agentic_scripts` (branch
  `feature/roadmap-dev-workflow` — LIVE; cron fires there every 30 min). Forced run:
  `cd /workspace/Python/agentic_scripts && uv run agentic-scripts run --force`.
  Its state: `state/roadmap-dev.json` (82 entries, all `open`, attempt 0 — re-verify
  the count at run time; if a job is mid-flight (`pending` with a live pid), STOP and
  report — do not proceed to step B). Its listing clone: `sandbox/roadmap-dev/prompts`
  (main; the engine fetches/pushes there).
- **Why this order:** the old engine runs FIRST so the baseline is the state of the
  world the new engine then must reproduce. If plans changed remotely between A and B,
  the listing legitimately advances — the check is content-hash identity at
  corresponding points (see verification), and a mid-run remote plan change invalidates
  the comparison → re-run A then B.
- **The new engine's runtime home IS this clone** (`/workspace/Python/autonomous_task_overview`) —
  state/logs/sandbox under it (gitignored). The engine's own listing clone will be
  `sandbox/roadmap-dev/prompts` UNDER THE CLONE (a separate clone of the remote — this
  checkout is never used for listing writes).
- **No double-engine:** do NOT install the cron entry in this task (`--skip-timer`);
  do NOT remove anything from `agentic_scripts` (that is post-gate). Both engines may
  be present, but only the old one is timer-driven; the new one runs only when we
  invoke it.
- **Git conventions:** `OC:` prefix; explicit staging; `plans.md` never staged.

## Tasks

### Task 1: Merge `feature/engine-move` → `main`
- **Do:** In the clone: `git fetch origin`; verify `origin/main` advanced only by
  listing-reconcile commits since our branch point (`git log --oneline feature/engine-move..origin/main` — expected: `OC: roadmap-dev: reconcile listing (…)` lines only; if ANY non-listing commit appears, STOP and report). Merge: `git merge origin/main` into `feature/engine-move` (our branch never touched `plans.md`, so this is conflict-free; if a conflict appears, STOP and report), then `git checkout main && git merge --ff-only feature/engine-move && git push origin main`.
- **Acceptance:**
  1. `origin/main` tip = our merge tip; `git log --oneline -5` on main shows the engine package + tests + setup + docs commits above the latest reconcile commit.
  2. `git diff <pre-merge-main-tip>..main -- plans.md` is EMPTY (no listing change came in via our branch).

### Task 2: (A) Old-engine baseline forced run
- **Do:** In `/workspace/Python/agentic_scripts` (read/execute ONLY — no file changes, no commits, no `git add` of anything; its untracked `planning/mail-keeper-pruning/` files must remain untouched):
  1. Guard: `python3 -c "import json; d=json.load(open('state/roadmap-dev.json'))['plans']; print(len(d), sum(1 for v in d.values() if v['state']=='pending'))"` — record count + pending count. **If pending > 0, STOP and report (a job is in flight — cutover window is not open).**
  2. Record pre-run listing tip: `git -C sandbox/roadmap-dev/prompts fetch -q origin && git -C sandbox/roadmap-dev/prompts rev-parse origin/main` → `BASELINE_TIP`; `git -C sandbox/roadmap-dev/prompts show BASELINE_TIP:plans.md | sha256sum` → `BASELINE_HASH`.
  3. Run: `uv run agentic-scripts run --force` (exit code must be 0).
  4. Record post-run: `git -C sandbox/roadmap-dev/prompts fetch -q origin && git -C sandbox/roadmap-dev/prompts rev-parse origin/main` → `A_TIP`; `git -C sandbox/roadmap-dev/prompts show A_TIP:plans.md | sha256sum` → `A_HASH`. (A may legitimately equal BASELINE or be one reconcile commit ahead.)
  5. Re-verify the state count (must be unchanged; all open/attempt 0).
- **Acceptance:**
  1. Forced run exit 0; `logs/last-run.txt` shows `overall: ok` and a `roadmap-dev=ok(…)` line; the run log has no ERROR.
  2. Evidence recorded: `BASELINE_TIP/HASH`, `A_TIP/HASH`, state count + 0 pending.

### Task 3: (B) New-engine setup + forced run
- **Do:** In `/workspace/Python/autonomous_task_overview` (checkout `main` — after Task 1 it holds the engine):
  1. `bash scripts/setup.sh --skip-timer` → exit 0. Guard: `crontab -l` BEFORE and AFTER the setup — must be byte-identical (the valve held; if not, STOP and report).
  2. State migration (copy, one-time): `cp /workspace/Python/agentic_scripts/state/roadmap-dev.json state/roadmap-dev.json` (the `state/` dir was created by setup). Verify: entry count identical to the Task 2 guard count; all `open`; all `attempt` 0. (Do NOT copy `state/scheduler.json` — the idle-gate streak starts fresh by design; do NOT copy sandbox dirs — the engine re-clones.)
  3. Record the pre-run tip of the NEW engine's listing clone — it does not exist yet (first run creates it); instead record the remote tip: `git ls-remote origin main` → `B_PRE_TIP` (must equal `A_TIP` — same world; if it differs, plans advanced → go back to Task 2 for a fresh baseline and redo Tasks 2–3).
  4. Run: `uv run autonomous-task run --force` (exit 0).
  5. Record: `B_TIP = git -C sandbox/roadmap-dev/prompts rev-parse origin/main` (after its internal push — the clone now exists); `B_HASH = git -C sandbox/roadmap-dev/prompts show B_TIP:plans.md | sha256sum`.
- **Acceptance:**
  1. Setup exit 0 with crontab byte-identical; state copied with identical count, all open/attempt 0.
  2. Forced run exit 0; `logs/last-run.txt` shows `trigger: force`, `workflows: roadmap-dev=ok(<n> items, …)`, `overall: ok`; `logs/run-*.log` has no ERROR and shows the GATE line rendered as `gate: FORCED` (or the forced marker per the runner's format) and the canonical `WORKFLOW roadmap-dev …` summary.
  3. **Byte-identical check:** `B_TIP == A_TIP` AND `B_HASH == A_HASH` — the new engine's reconcile found nothing to change (identical render → no commit → same tip) — OR, if the new engine pushed a reconcile commit, `B_HASH == A_HASH` still (content identity is the contract; the tip may differ by exactly the reconcile commit only if the OLD engine's run A pushed one that the new engine's run re-rendered identically — in that case report `B_TIP` vs `A_TIP` and the diff between them, which must be listing-only).
  4. New sandbox populated: `sandbox/roadmap-dev/clones/` holds the 9 `<owner>__<name>` clones + `sandbox/roadmap-dev/prompts/` (the listing clone).
  5. State file at the new location: entry count unchanged, all `open`, attempt 0.

### Task 4: Evidence pack + commit (if any) + result
- **Do:** Assemble the evidence in the result report: both tips + hashes, state counts (A-guard, B), last-run excerpts from BOTH locations, the crontab-unchanged proof, the clone inventory, the run-log grep for ERROR (empty). If step B's run produced any commit in the clone (it must not — engine writes go to the remote via the listing clone, and our checkout holds only the branch work), report it; otherwise no commit is needed for this task (the merge commit from Task 1 is already pushed).
- **Acceptance:**
  1. The result report contains every artifact listed above, with exact values (no paraphrasing of hashes/tips).
  2. `git -C /workspace/Python/agentic_scripts status` is UNCHANGED by this task (no new/modified tracked files, the untracked mail-keeper-pruning files still untracked).
  3. The crontab still has exactly its single `# agentic-scripts` entry (no `# autonomous-task` line).

## Out of Scope
- Installing the new cron entry (work-plan Task 7 — post-gate).
- ANY removal from `agentic_scripts` (work-plan Task 6 — post-gate).
- Live drain execution (no approved rows; impossible by design today).

## Notes
- **[Risk]** The old engine's 30-min cron may fire MID-VERIFICATION (between our A and
  B steps). That is harmless (same render → no push, or a reconcile commit that both
  engines reproduce identically) — but it can shift tips between steps: if
  `B_PRE_TIP != A_TIP` for reasons other than our own runs, re-baseline (Task 2 → 3)
  and note it.
- **[Risk]** A forced old-engine run while the new engine's sandbox is mid-clone: not
  possible here (sequential steps), but if any step is retried, ensure the previous
  run fully exited (check no `uv run …` process remains) before re-running.
- **[Convention]** This task touches BOTH repos' runtime state (state file, sandboxes,
  logs) but NO committed code in `agentic_scripts` and no crontab — the gate the user
  approves next is the first moment anything is removed/installed.
