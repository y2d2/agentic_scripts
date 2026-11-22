# lightweight-dev Output — Task: T4 — Phase 2/3 drain: continuous slots, job pipeline, outcomes

**Task:** #4    **Session:** ses_dff5540d7ffeifX3YxxYcRZCdi    **Date:** 2026-11-22

## Summary

Replaced the T3 drain stub in `roadmap_dev.py` with the full in-process top-up drain and per-job pipeline, exactly as specified:

- **Slots:** `2 if machine.quiet_window.in_window(now_fn().time()) else 1`, recomputed every drain-loop iteration. Startable = state ∈ {open, review} AND listing approval ☑, sorted `(priority, scan order)`, deduped by identity; no API lookups (re-execution safety from the state machine).
- **Drain loop:** reap finished jobs (dead worker → `RuntimeError` abort, pending entry stays for the reaper) → route outcome under one `threading.Lock` with atomic save → in-flight jobs trigger a re-scan every `machine.poll_interval_minutes` (default 30) plus 15-s bounded `join(timeout)`; nothing in flight → re-scan FIRST (unless first top-up) → live probe `active_sessions() > 0` → `gate closed — no new starts` + break, else start up to `slots` (`top-up: starting <id> (slot N/M)`); none start → `drain done (slots=S startable=N)` + break.
- **Job start:** state → `pending` (`attempt += 1`) persisted atomically BEFORE spawn; worktree on `roadmap-dev/<id>-<attempt>` from `origin/<branch>` (stale local branch dropped first, worktree faults revert to `open`); headless `planner-enhanced` in a daemon `threading.Thread` with the 8 h budget.
- **Outcome routing:** error/timeout → `failure.md` on the plan's branch (diag worktree); ok → `job_status_from_report`: questions → `questions.md` commit+push on plan branch + state `review` + sanctioned `force_unapprove` pass; failure → `failure.md` + state `failure`; success → tests gate (600 s, skipped with a note when unconfigured) → impl commit → `git mv` archive commit → `commit_sha` → push attempt branch (`upstream=True`) → state `success`; log `pushed branch … — human opens the PR`. No PR, no GitHub API. `finally` always removes the attempt worktree + best-effort deletes the local branch.
- **`agent.py`:** `AgentResult.pid: int | None = None` (set from `proc.pid` right after `Popen`; None when spawn fails) + docstring. Forensic only — the reaper treats all `pending` entries as orphans (new process).

Hermetic tests in the new `tests/test_roadmap_dev_pipeline.py`: bare remotes + real `Git`/`StateStore`, `FakeRunner` (scripted per-identity `AgentResult`s, concurrency counter, double-flight tracker, `hold_seconds` in-flight holds, `on_start` hooks for clock/gate flips), mutable `Clock`, injectable `active_sessions`.

**Extra bugs found and fixed during implementation** (all covered by the suite):

1. **Re-arm self-trigger:** T2's sanctioned re-arm (doc `failure` + remote row `open` → re-open) misfired MID-drain — the remote row is stale until the failure row is pushed, so a failed job would re-arm itself and restart forever. Fix: defaulted `rearm_guard: frozenset[str] = frozenset()` on `reconcile` (suppressed for the drain's already-routed identities this drain; genuine user re-arms in a later run still work). T2 behavior unchanged (default).
2. **Checked-out diag branch:** a fresh default clone has `plan.branch` checked out → `git branch -D` refuses → `worktree_add -b <plan.branch>` fails. Fix: `_detach_head` (raw `git checkout --detach`, no Git-helper method exists) in `_commit_diag` only when `current_branch(clone) == plan.branch`.
3. **Stale local-HEAD no-op in `_reconcile_and_push`:** with the local clone HEAD behind `origin/<branch>` (user pushed a listing edit after the last fetch), the no-op commit check is local-HEAD-relative and silently SKIPPED the very push that consumes the user's edit (e.g. a remove ☑ whose re-appearance is byte-identical to the last pushed row). Fix: re-point the local branch to `origin/<branch>` before committing when it is behind.
4. **Final-save clobber:** copy-on-write `reconcile` can move the drain's transitions into a newer doc object than the Phase-1 one `_run` held → the run's final save overwrote drain results. Fix: `_drain` returns `(actions, final_state_doc)`; `_run` saves that document.
5. **`git mv` ENOENT:** rename(2) needs the destination parent; a repo with no `planning/archived/` yet fails `git mv`. Fix: `mkdir planning/archived` (untracked empty dir suffices) before the mv.
6. **`Thread(excepthook=…)` doesn't exist** (my first implementation draft): worker threads now catch their own exceptions, record `job.error`, and log via `ctx.logger`; the drain still aborts on a dead job.

**Two T3 tests updated** (behavior improved by fix #3 — their core assertions all still hold): `test_user_listing_edits_are_preserved` now asserts `push_calls == 0` (render byte-identical to remote tip → no-op commit, no push) and `test_prompts_push_race_retries_and_keeps_user_commit` now asserts `push_calls == 1` (commit lands on top of the user commit → one fast-forward push, no rejected first push). `test_drain_stub_note_tracks_gate` was rewritten per plan (it asserted the removed stub string) — it now injects `active_sessions=lambda: 0` (the real probe would hit this machine's live OpenCode service) and asserts gate-open → `drain start slots=1 startable=0` + `drain done (…)` vs gate-closed → `drain skipped (idle gate closed)`.

## Files

| File | Action | Why |
|---|---|---|
| `src/agentic_scripts/agent.py` | modify | `AgentResult.pid` field (+docstring, capture at both result sites) — the only allowed change outside the workflow + tests |
| `src/agentic_scripts/workflows/roadmap_dev.py` | modify | Real `_drain`/`_route_job`/`_start_job`/`_route_success`/`_commit_diag`/`_force_unapprove`/`_detach_head` replacing the drain stub; `reconcile`+push helpers gained defaulted `rearm_guard`/stale-HEAD re-point; `_drain` returns the final doc for the run's save |
| `tests/test_roadmap_dev_pipeline.py` | create | 13 hermetic AC tests + `FakeRunner`/`Clock`/`ActiveFlag` fakes and fixture-repo builders |
| `tests/test_roadmap_dev_scan.py` | modify | `test_drain_stub_note_tracks_gate` rewritten (stub removed); two push-count tests aligned to the stale-HEAD fix (fix #3) |

## Build / Tests

- `uv run pytest tests/test_roadmap_dev_pipeline.py -v`: PASS — 13/13 (≈26 s; concurrency tests use 0.1–0.5 s `hold_seconds`)
- `uv run pytest -q` (full suite): PASS — **312 passed** (299 baseline + 13 new), 72 s
- `uv run ruff check src tests`: PASS — clean
- `uv run ruff format --check src tests`: PASS — clean
- Commit: on `feature/roadmap-dev-workflow`, 4 files staged by explicit path (`planning/` left untouched), committed `OC: roadmap-dev T4 — real top-up drain (1d/2n slots, rescan, let-finish) + per-job pipeline (worktree, headless planner-enhanced, success→tests+commit+archive+push-branch, questions→questions.md, failure/timeout→failure.md) + AgentResult.pid + 13 AC tests` (4 files, +2481/−51). **Not pushed** (per dispatch).

## Acceptance Verification

| # | Criterion (verbatim) | Result | Notes |
|---|---|---|---|
| 1. | **Day drain:** now=12:00, 3 approved `open` plans (priorities 1–3), fake runner "succeeds" (returns a canned success report) → all 3 jobs run; fake runner's observed max concurrency == 1; starts in priority order; each next start happens in the same drain (no drain-end between jobs — assert the drain returned only after job 3 finished, and the start timestamps show a top-up immediately after each finish). | PASS | `test_ac1_day_drain_sequential_priority_order` — 3 runner calls, `max_concurrency == 1`, starts in priority order (1→2→3), each top-up `top-up: starting <id> (slot 1/1)` in the same drain, three attempt branches pushed. |
| 2. | **Night drain:** now=23:00, 3 approved plans → max concurrency == 2 (jobs 1+2 in flight together, job 3 starts after one finishes). | PASS | `test_ac2_night_drain_two_concurrent` — `drain start slots=2 startable=3`, first two starts overlap (`max(starts) < min(ends)`), job 3 starts after the first finish, `max_concurrency == 2`, no double-flight. |
| 3. | **Window crossing:** 2 jobs in flight at 23:59; clock advances past 00:00… no — slots recompute: start job 1 at 23:30 (1 slot… day? 23:30 is night → 2 slots). Use: jobs in flight; clock crosses 08:00 → slots=1 → no new starts until an in-flight job finishes, then exactly one starts. | PASS | `test_ac3_window_crossing_slots_shrink` — 2 in flight at night (slots=2), `on_start` hook advances the clock past 08:00 → re-computed slots=1 → the 3rd startable waits until an in-flight job finishes, then exactly one starts (`slots=1` thereafter). |
| 4. | **Gate close mid-drain:** 2 jobs in flight (night); `active_sessions` flips to 1 → remaining startable plans are NOT started; both in-flight jobs finish; drain ends; a fresh `run()` (new ctx, gate_open=False) → Phase 1 only, drain note `drain skipped (idle gate closed)`, zero runner calls. | PASS | `test_ac4_gate_close_mid_drain_let_finish` — `gate closed — no new starts` logged, 3rd plan never started, both in-flight finish (let-finish), fresh closed-gate run = Phase 1 only + the exact skip note, 0 runner calls. |
| 5. | **Review round-trip:** job 1 returns a report with `Status: questions` and the fake worktree contains `questions.md` (fake runner writes it into the workdir) → on the fixture REMOTE, the plan's branch (`main`) gains a commit `OC: roadmap-dev: <id> — questions (run …)` adding `planning/<topic>/questions.md`; row `state=review`, `approval=☐` (remote `plans.md` updated); next run: test edits `questions.md` on the branch (answers) + flips the row back to ☑ (re-commit on the prompts remote) → job re-runs with `attempt=2`, returns success → attempt branch `roadmap-dev/<id>-2` pushed exactly ONCE for the identity (git-remote branch list), state `success` with `branch_name` + `commit_sha` set. | PASS | `test_ac5_review_round_trip` — diag commit `OC: roadmap-dev: <id> — questions (run test-run)` adds `planning/orbit-sim/questions.md` on remote `main`; row `review` + approval ☐ (`unapproved <id> (questions raised)`); identity is stable across the `questions.md` edit (`DIAGNOSTIC_FILES` excluded from the plan hash); attempt=2 succeeds, `roadmap-dev/<id>-2` pushed exactly once, `branch_name`+`commit_sha` set. |
| 6. | **Timeout:** fake runner returns `AgentResult(status="timeout", …)` → `failure.md` committed on the plan's branch (content = `agent timeout: agent run exceeded …`), state `failure`, `last_error` set; next drain: identity NOT started (failure never auto-restarts) even though approval ☑. | PASS | `test_ac6_timeout_failure_no_autorestart` — `failure.md` on remote `main` with `agent timeout: agent run exceeded 28800s`, row `state=failure` (pushed in the same drain's re-scan), `last_error` set, run status `error` with `owner/fixture (<id>): agent timeout: …`; a follow-up drain with approval ☑ starts it zero times and logs no re-arm (the `rearm_guard` is what makes this hold). |
| 7. | **Crash reaper:** seed state with a `pending` entry (attempt 2) + leaked attempt worktree dir; run → reaper flips to `open` + removes the dir; drain then starts it fresh (attempt 3) — one runner call. | PASS | `test_ac7_crash_reaper_restarts_at_next_attempt` — `reaped orphan <id> (pending -> open)` + leaked dir removed (attempt counter sticks at 2); listing pre-seeded with the row the pre-crash run would have pushed (realistic world); drain starts attempt 3, exactly one runner call, success delivered. |
| 8. | **Success re-run guard:** state entry `success` (branch pushed) → candidate NOT startable on any subsequent drain (no runner call, no branch push); the re-appeared `success` row (after a `remove` ☑) is likewise never startable. | PASS | `test_ac8_success_never_startable_again` — after success, repeated drains = 0 runner calls; user ticks `remove` ☑ → row drops+re-adds as `success` (approval preserved) → still 0 runner calls, no new branch. |
| 9. | **Refused repo:** fixture repo present in the clone sandbox but NOT in `allowed_repos` → never scanned, no row, no job. | PASS | `test_ac9_refused_repo_never_scanned` — the `owner/other` bare remote exists but is absent from `allowed_repos` → no clone dir, no listing row, no job; only the allowed repo's 1 job runs. |
| 10. | **Malformed plan:** folder without `work_plan.md` → no row, no job, no error line for it. | PASS | `test_ac10_malformed_plan_ignored` — the malformed folder produces no row and no error line (`errors == []`), the sibling plan still scans/runs. |
| 11. | **No double-flight:** 5 approved plans, night → at no moment is the same identity in flight twice (fake runner tracks concurrent identities); total runner calls == 5. | PASS | `test_ac11_no_double_flight_five_plans` — `double_flight == []`, exactly 5 runner calls, `max_concurrency <= 2`. |
| 12. | **State atomics:** after every job transition the state file on disk reflects the new state (assert file content after each scripted job finish) — a mid-drain "crash" (test kills the run via an exception injected in the fake runner after job 1's `pending` persist) leaves a valid JSON state file (no torn write) with the pending entry for the reaper. | PASS | Two tests: `test_ac12_state_file_after_every_transition` (file on disk matches the expected doc after each transition) and `test_ac12_mid_drain_crash_leaves_valid_state` (runner raises after the `pending` persist → run status `error`, state file is valid JSON with the `pending` entry intact for the reaper). |
| 13. | `uv run pytest tests/test_roadmap_dev_pipeline.py -v` green; full suite green; ruff clean. | PASS | 13/13 pipeline tests; full suite 312/312; `ruff check` and `ruff format --check` both clean (see Build / Tests). |

## Blockers

None.

## Next Steps

- Nothing for T4 — all 13 ACs green, committed (see Build / Tests message), not pushed per dispatch.
- For the orchestrator / follow-up tasks:
  - `reconcile`'s new defaulted `rearm_guard` kwarg is part of the T4 surface — any future caller that routes outcomes mid-reconcile should pass the routed identities to keep the failure-row push and re-arm from racing.
  - The 600 s test-command timeout is a module constant (`_TESTS_GATE_TIMEOUT_SECONDS`), NOT configurable (plan [Assumption]); a follow-up could add `roadmap_prompts.test_timeout_seconds`.
  - `Thread`-based job workers swallow a raising runner into `job.error` + run-status `error` (the pending entry stays for the reaper) — the dead-worker path is exercised only indirectly (the AC12 crash variant uses a runner that raises).
