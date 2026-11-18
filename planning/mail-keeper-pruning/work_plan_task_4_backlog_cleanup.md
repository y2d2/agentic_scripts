# Task Plan: mail-keeper — runner-owned pruning of checked daily entries (Task 4/4)

**Purpose:** Prove the fix end-to-end on the live system by running one forced, mail-keeper-only pass that clears the accumulated backlog (82 checked entries across 12 day-files), with exact pre/post verification numbers.

## Objective

After Tasks 1+2 are merged and the full test suite is green, execute one forced scheduler pass scoped to mail-keeper (`uv run agentic-scripts run --force --only mail-keeper` from `/workspace/Python/agentic_scripts`) and verify, with exact counts, that the runner pruned all 82 checked entries, deleted the 7 emptied day-files, left the 6 files with unchecked entries intact (their unchecked entries byte-identical), grew `mail/daily/.pruned.jsonl` from 2 to 84 lines with no duplicate ids, dispatched **no** agent (no new mail), and left the vault's git state untouched. Success = every check in the Acceptance list passes and the before/after table is reported.

## Context

- Repo/working dir: `/workspace/Python/agentic_scripts`, branch `plan/agentic-workflows`. Run the command with the project's uv venv: `uv run agentic-scripts run --force --only mail-keeper` (`--force` bypasses the quiet-window gate; `--only mail-keeper` skips the noop and oc-todo workflows). Console script declared in `pyproject.toml` (`agentic-scripts = "agentic_scripts.cli:main"`).
- **Prerequisites (verify first, STOP and report as Blocker if any fails):**
  1. `git log --oneline -3` in `agentic_scripts` shows the Tasks 1+2 commits (prune module + runner hook).
  2. `uv run pytest -q` → fully green.
  3. `uv run ruff check .` → clean.
- **Live system:** `admin_repo` (the vault) = `/workspace/Obsidian/ARP_roadmap` (per `config/workflows.yaml`); `mail/daily/` inside it is git-ignored (bare `mail` line in the vault `.gitignore`) and local-only. The notmuch index + maildir live under `/workspace/docker/mbsync/` (do not touch). The mail-keeper workflow reads `MAIL_*` env vars (defaults match the live paths; a `.env` in the repo root is loaded by the app — do not modify it).
- **Expected pre-run state (measured 2026-11-18; re-measure and use YOUR measured values as the baseline if they differ — report both):**
  - Checked entries (`grep -c '^\s*- \[x\]'` per file): `2026-11-05.md`=11, `2026-11-06.md`=4, `2026-11-07.md`=3, `2026-11-09.md`=16, `2026-11-10.md`=10, `2026-11-11.md`=2, `2026-11-12.md`=19, `2026-11-13.md`=6, `2026-11-14.md`=1, `2026-11-15.md`=3, `2026-11-16.md`=4, `2026-11-17.md`=3 → **total 82**.
  - Unchecked entries: **23**, only in `2026-11-04.md`, `2026-11-10.md`, `2026-11-11.md`, `2026-11-12.md`, `2026-11-13.md`, `2026-11-16.md`.
  - Files to be **deleted** after pruning (zero unchecked entries): `2026-11-05.md`, `2026-11-06.md`, `2026-11-07.md`, `2026-11-09.md`, `2026-11-14.md`, `2026-11-15.md`, `2026-11-17.md` → **7 files**.
  - Files that **remain** (6): the unchecked-bearing six above.
  - `mail/daily/.pruned.jsonl`: **2 lines** (ids `DB9PR01MB9980D80353CE75E1C6602BD1E2652@…`, `DU0PR05MB9264AA2F6BD66BF5CDA47A9B99652@…`) → after: **84 lines**.
  - Expected agent dispatch: **none** — every scheduled run since 2026-11-17T22:30Z reported no new mail (`items_found=0`); the run should take ~10–30 s (canary + detection + prune), NOT tens of minutes. If it starts looking like an agent run (long duration, `step_start` events in the log), STOP and report as Blocker before it dispatches mail triage.
- **Safety:** the run writes only `mail/daily/**` in the vault (git-ignored), the workflow's own `state/` + `logs/` in `agentic_scripts`, and the processed log only if the agent ran (it won't). It never touches `mail/backup`, never commits/pushes anywhere, never sends mail. Pre-existing vault modifications (`direction.md`, `projects/ORBIT/ORBIT_people_per_WP.pdf`) must remain as they are.

## Tasks

### Task 1: Capture baseline + run + verify
- **Files:** none in git (operational task) — artifacts are the run log (auto-created in `logs/`) and the vault state
- **Do:**
  1. Baseline (record in the result report): `ls mail/daily/`, per-file `grep -c '^\s*- \[x\]'` / `'^\s*- \[ \]'` totals, `wc -l mail/daily/.pruned.jsonl`, `git status --short` in the vault, `date -u`.
  2. Run: `uv run agentic-scripts run --force --only mail-keeper` (from `/workspace/Python/agentic_scripts`). Capture full stdout; it ends with a `RUN END …` line.
  3. Locate the new run log: newest `logs/run-*.log`; extract the `WORKFLOW mail-keeper` line (expect `status=ok items_found=0 errors=0` — note: prune success adds an action but not an error) and confirm the run took seconds, and that **no** `step_start`/agent events appear for mail-keeper.
  4. Post-checks (record in the result report):
     - `mail/daily/` listing: exactly the 6 expected files remain (or your re-measured equivalent); the 7 emptied ones are gone.
     - `grep -c '^\s*- \[x\]' mail/daily/*.md` → 0 matches in every remaining file.
     - Unchecked totals unchanged (23) and the 6 surviving files' unchecked entry blocks are byte-identical to baseline (compare with a saved pre-copy: copy `mail/daily/` to `/tmp/opencode/mail_daily_pre` in step 1 and diff the surviving entries).
     - `.pruned.jsonl`: 84 lines; `sort | uniq -d` → empty (no duplicate ids); the 2 original ids still present.
     - Blank-line hygiene in surviving files: no double blank lines between entries (spot-check with `grep -n '^$'` on the shortest surviving file).
     - Vault `git status --short` → identical to baseline (only the two pre-existing `M` entries; no new/modified/deleted tracked files; `mail/` untracked-and-ignored).
     - `agentic_scripts` `git status` → only `state/`/`logs/` runtime changes (no source changes by the run).
  5. Do **not** commit anything in this task (the code commits happened in Tasks 1+2; runtime state/logs are not committed).
- **Notes:** If any post-check deviates from expectation: STOP, capture the run log excerpt + the offending file state, report as Blocker (do not attempt manual repair of the vault).
- **Acceptance (all must hold):**
  1. Run completed `status=ok`, `items_found=0`, no agent dispatch (no agent events in the run log), duration < 5 min.
  2. 82 checked entries removed (your measured baseline − post-check = 0 remaining checked).
  3. 7 emptied day-files deleted; 6 files remain with all 23 unchecked entries byte-identical.
  4. `.pruned.jsonl`: 2 → 84 lines, zero duplicate ids, original 2 preserved.
  5. Vault + repo git states match the pre-run baseline (no collateral changes).
  6. The new run log's mail-keeper `actions` include a `pruned 82 …` line (or your measured equivalent).

## Out of Scope

- No code changes (report Blocker instead if the run reveals a bug), no commits, no `git add`/`push` anywhere, no manual editing of vault files, no touching `mail/backup`, notmuch index, or `.env`.

## Notes

- [Assumption] "No new mail" holds at run time (12 consecutive runs showed `items_found=0`); if new mail arrived since the last measurement, the run WILL dispatch the agent (by design) — that is still a valid end-to-end test of the prune-on-agent-path (Task 2 test 2 covers the logic; here you would additionally verify the prune action appeared), but report the manifest size in the result so the orchestrator can judge.
- Result report path: `planning/mail-keeper-pruning/lightweight_dev_task_4_backlog_cleanup.md` (sub-agent-communication result-report format; include the full before/after table).
