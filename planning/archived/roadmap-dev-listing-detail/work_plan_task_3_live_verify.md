# Task Plan: roadmap-dev listing — live run + verification (detail row)

**Purpose:** Verify the goal + task-titles detail row end-to-end: a forced roadmap-dev run
pushes the new format to the live `plans.md`, a second run proves idempotency, and the
Obsidian local copy is pulled so the user sees the detail rows.

## Objective

With the core code change (companion Task 1) committed on
`feature/roadmap-dev-workflow` in `/workspace/Python/agentic_scripts` and the README doc
(companion Task 2) pushed, run the real workflow once, verify the live listing
(`y2d2/autonomous_task_overview`, `plans.md` on `main`) now carries a detail row under
every one of the 77 plan rows, verify a second run adds no new commit (steady-state
no-push), verify NO plan job was started (no approvals exist → nothing may start), and
pull the local Obsidian copy so the user's plan overview shows the new rows.

## Context

- **Repo:** `/workspace/Python/agentic_scripts`, branch `feature/roadmap-dev-workflow`.
  Preconditions (verify, report as blocker if unmet): `git status` shows the companion
  Task-1 commit present (latest commit message contains `roadmap-dev listing`), working
  tree otherwise clean EXCEPT the known 3 untracked files under
  `planning/mail-keeper-pruning/` (another session — never stage/commit them) and the
  untracked `planning/roadmap-dev-listing-detail/` plan folder (orchestrator-owned —
  never stage/commit it either).
- **Live listing state (2026-11-22):** `origin/main` of `y2d2/autonomous_task_overview`
  carries 77 data rows (regex `^\| [☑☐] \|`), all `state=open`, all approval `☐` (nothing
  approved — the drain must start zero jobs). Local read copy at
  `/workspace/Obsidian/ARP_roadmap/autonomous_task_overview` (Obsidian vault; branch
  `main`; behind origin — it will be fast-forwarded by the pull in step 6). The live
  workflow (systemd timer, every 30 min at :00/:30) runs `python -m agentic_scripts run`
  FROM THIS WORKING TREE — so once the companion Task-1 code is in place, a live fire
  between now and your forced run may ALREADY push the new format (and the rebase/push of
  the companion Task-2 README commit may be interleaved too). Treat the remote file
  CONTENT after your run as the authority — not the number of commits.
- **CLI:** `uv run agentic-scripts run --force --only roadmap-dev` (run from the repo
  root). `--force` bypasses the quiet+idle gates; for this idle-gate workflow that means
  `gate_open=True` and the in-process drain DOES run — but with zero approved rows
  `_select_startable` returns `[]` and the drain ends with
  `drain done (slots=N startable=0)` (or `gate closed — no new starts` if the live session
  probe sees an interactive session — either way: no job starts). A full run takes
  ~60–90 s (9 allowed repos scanned over SSH).
- **Run log:** `logs/run-<UTC-stamp>Z.log` (latest file in `logs/`); the workflow logs
  `roadmap-dev: <repo> — found N plan(s)` per repo, the scheduler logs
  `WORKFLOW roadmap-dev status=<ok|error> items_found=<N> actions=<N> errors=<N>
  duration=<…>s`. The action notes (incl. `listing pushed to y2d2/autonomous_task_overview
  (77 row(s))` / `drain start slots=… startable=…`) are in the returned
  `WorkflowResult` — NOT all of them appear in the log file; use the log + git evidence
  below.
- **Sandbox prompts clone:** `sandbox/roadmap-dev/prompts` — the workflow's clone of the
  listing repo; after a push its local `main` and `origin/main` carry the new reconcile
  commit `OC: roadmap-dev: reconcile listing (run <run-id>)`.
- **Detail-row contract (what the pushed file must contain):** under EVERY data row
  (`^\| [☑☐] \|`), immediately the next line, a row starting with
  `| — | — | **Goal:** ` (em dashes, `**Goal:**` bold marker). 77 data rows → 77 detail
  rows. Spot-check expectations (real plans, 2026-11-22):
  - `planning/orbit-dmp/work_plan.md` (repo section `ARP_roadmap.git`, branch `main`):
    goal starts `Build \`projects/ORBIT/DMP/ORBIT_DMP_v0.md\`` and the Tasks cell lists
    20 tasks starting `1 Skeleton & front matter`.
  - `planning/esa-no-open-source/work_plan.md` (ARP_roadmap, main): `**Goal:** —` (no
    Purpose/Goal marker) with `**Tasks:** 1 remove open source` (derived from the task
    table / file name).
  - `planning/orbit-plenary-i-slides/work_plan.md` (ARP_roadmap, main): `**Goal:** —` and
    24 tasks derived from the `work_plan_task_N_*.md` file names (starting
    `1 slides note`).
  - `planning/arp-imu-active-measurements/work_plan.md` (ARP_IMU, master): goal starts
    `Implement the SGal3 active-measurements buffer` and the Tasks cell starts
    `1 Add active-measurements buffer infrastructure to ARP_IMU`.
- **Git conventions here:** no commits are expected from THIS task (the workflow commits
  the listing itself in its sandbox clone; nothing in the agentic_scripts repo should be
  committed by you). The Obsidian-copy pull is a fast-forward only.

## Tasks

### Task 1: Forced run + remote verification + idempotency + local pull
- **Files:** none modified (operational run; read-only checks; one `git pull --ff-only`
  in the Obsidian copy)
- **Do:**
  1. Preconditions: `cd /workspace/Python/agentic_scripts && git status` (Task-1 commit
     present; only the known untracked files), `uv run pytest tests/test_roadmap_dev.py -q`
     (green — a 30-second guard before touching the live listing), and
     `git -C sandbox/roadmap-dev/prompts rev-parse HEAD` → record it as `P0`.
  2. Run: `uv run agentic-scripts run --force --only roadmap-dev` (shell timeout ≥ 600 s).
     Capture the run-log file name (latest `logs/run-*.log`).
  3. Verify the run: log contains `WORKFLOW roadmap-dev status=ok` with `errors=0`;
     `items_found` ≈ 77 (≥ 70 — plan folders may move between sessions; report the exact
     number). Extract the `drain start slots=… startable=N` / `drain done …` lines from
     the log or state: **if `startable` > 0, the run started a real job — report it as a
     Next Step immediately (do NOT kill or revert anything).**
  4. Verify the listing surface: `git -C sandbox/roadmap-dev/prompts fetch origin` then
     `git -C sandbox/roadmap-dev/prompts log --oneline -3 origin/main`. A new commit
     `OC: roadmap-dev: reconcile listing (run …)` normally exists (`P1 ≠ P0`) — but a live
     :00/:30 fire may have pushed the identical new format already (then `P1 == P0` is
     FINE and expected; note which case occurred in the report).
  5. Verify the file — this is the AUTHORITY (from
     `git -C sandbox/roadmap-dev/prompts show origin/main:plans.md`):
     - data-row count (`grep -cE '^\| [☑☐] \|'`) equals detail-row count
       (`grep -cE '^\| — \| — \| \*\*Goal:\*\*'`); both ≥ 70;
     - every data row is immediately followed by a detail row (loop: for each matching
       line number, the next line starts with `| — | — | **Goal:** `);
     - the four spot-checks from Context all hold;
     - no line starts with `| — | — | **Goal:** ` that is not directly under a data row.
  6. Idempotency: record `P1 = git -C sandbox/roadmap-dev/prompts rev-parse origin/main`
     (after step 4's fetch), run the CLI command AGAIN (step 2, second forced run),
     re-fetch, and assert `origin/main` HEAD is UNCHANGED (the no-op commit path: the
     rendered listing is identical to the remote one; at most a no-op commit attempt, no
     new commit, log shows the second run `status=ok errors=0`).
  7. No jobs: `git -C sandbox/roadmap-dev/prompts ls-remote origin 'refs/heads/roadmap-dev/*'`
     returns nothing, and in each allowed-repo sandbox clone
     (`sandbox/roadmap-dev/clones/*/`) `git ls-remote origin 'refs/heads/roadmap-dev/*'`
     (or a plain `git branch -r` after fetch) shows no `roadmap-dev/<id>-1` branch —
     consistent with `startable=0` in step 3.
  8. Local pull: `git -C /workspace/Obsidian/ARP_roadmap/autonomous_task_overview
     pull --ff-only` (expected: fast-forward including the README doc commit from the
     companion Task 2 and the listing push) and verify the local `plans.md` has equal
     data-row and detail-row counts (same two greps).
- **Notes:** the second run (step 6) re-scans all repos (~60–90 s) — total task budget
  ≤ ~10 minutes. If the FIRST push is rejected non-fast-forward (a human edited the
  listing concurrently), the workflow retries once by itself; if it still failed the run
  shows `errors=1` with `listing push failed for …` — report as blocker with the error
  text, do not hand-push. Never run `git add -A` anywhere; never commit in this task.
- **Acceptance:**
  1. First forced run: `WORKFLOW roadmap-dev status=ok … errors=0`; a new
     `OC: roadmap-dev: reconcile listing (run …)` commit on `origin/main` of
     `y2d2/autonomous_task_overview` is the normal evidence — or `origin/main` is
     already at the new format because a live :00/:30 fire pushed it first (both cases
     PASS; record which occurred); the remote `plans.md` (the authority) has a detail
     row directly under every data row (counts equal, order verified) and all four
     spot-checks hold.
  2. Second forced run: `status=ok errors=0` and `origin/main` HEAD unchanged
     (idempotent, no duplicate commit).
  3. `startable=0` in the drain log lines and NO `roadmap-dev/*` branch on any remote
     (or: if `startable > 0`, a prominent Next Step reporting the started job).
  4. Obsidian local copy fast-forwarded; its `plans.md` shows the detail rows (counts
     equal); `git status` there clean after the pull.
  5. No commits made in `/workspace/Python/agentic_scripts` by this task (the untracked
     `planning/roadmap-dev-listing-detail/` folder and the 3 mail-keeper-pruning files
     remain untracked).

## Out of Scope

- Fixing anything the run reveals (report as blocker instead), PRs, branch deletion,
  config changes, killing in-flight jobs (there must be none).

## Notes

- [Risk] `--force` opens the drain gate — the only way this run starts a job is a user
  approval between now and the run; step 3/7 detection + reporting covers that (by-design
  behaviour, surfaced loudly).
- [Assumption] 77 rows is the 2026-11-22 count; the assertions use `≥ 70` + equal
  data/detail counts so the verification stays valid if plans appear/disappear.
- [Note] The workflow's state file `state/roadmap-dev.json` is updated by the runs
  (normal operation — no acceptance beyond `status=ok`).
