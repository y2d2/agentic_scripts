# lightweight-dev Output — Task: Snapshot dotfile exclusion (mbsync false-trip fix)

**Task:** #1    **Session:** ses_e068ff029ffeZ1jWw9sdN4TWcH    **Date:** 2026-11-20

## Summary

Implemented the task plan exactly: `_backup_snapshot()` in `src/agentic_scripts/workflows/mail_keeper.py` now skips dot-prefixed entries (a single `continue` at the top of the inner `for name in filenames:` loop, with the incident-referencing comment from the plan), and its docstring's Rationale section now states that mbsync bookkeeping dotfiles (`.mbsyncstate` / `.uidvalidity`) are intentionally excluded — written by the host-side syncer, never by the permission-denied agent — citing the 2026-11-20 false-trip incident. `os.walk` usage, the `is_file()`/`stat()` logic, the return shape, both call sites, and the error message are all unchanged. Added section `# 8b. Backup snapshot dotfile exclusion` to `tests/test_mail_keeper.py` with the 3 named tests (dotfile rewrites invisible to the snapshot; touch/append/delete of a real mail file still flips it; integration run mirroring `test_backup_integrity_trip` where the 2nd snapshot call rewrites a NEW dotfile instead of touching the mail file → `status == "ok"`, no trip, `backup tree unchanged` action). The existing `test_backup_integrity_trip` was not modified and keeps passing.

Counterexample check (plan assumption, dispatch hard constraint): **no dot-prefixed legitimate mail file exists** — the hermetic fixture contains only `m1.eml`…`m10.eml` under `cur/` dirs, and the live tree `/workspace/docker/mbsync/backup` (13,652 files, scanned with `os.walk`, never `find`) contains exactly 29 dot-prefixed files: 14 × `.mbsyncstate`, 14 × `.uidvalidity`, 1 × `.gitkeep`. The plan's assumption holds; nothing was special-cased.

Committed as `OC: mail-keeper guardrail — exclude syncer dotfiles (mbsync state) from backup snapshot` on new branch `feature/mail-guardrail-mbsync-exclusion` (base `de7db5b`, branch `feature/opencode-v2-run`), pushed with `-u` to `origin`. Only the two task files were staged (explicit paths; `git add -A` never used); the untracked `planning/mail-keeper-pruning/*` files and the session dir were left untouched (they remain untracked in `git status -s`).

## Files

| File | Action | Why |
|---|---|---|
| `src/agentic_scripts/workflows/mail_keeper.py` | modify | One `continue` in the `_backup_snapshot` inner loop skipping dot-prefixed filenames (+ comment citing the 2026-11-20 incident); docstring Rationale extended with the exclusion rationale + incident citation. Net +11/−1, both hunks inside `_backup_snapshot` only. |
| `tests/test_mail_keeper.py` | modify | New section 8b with `test_backup_snapshot_ignores_dotfiles`, `test_backup_snapshot_still_catches_mail_mutation`, `test_backup_integrity_no_trip_on_sync_state_rewrite` (pure insertion of 134 lines after the unchanged `test_backup_integrity_trip`; all dotfiles/mail mutations restored in `finally` blocks to keep the module-scoped fixture pristine). |

## Build / Tests

- `uv run pytest tests/test_mail_keeper.py -q`: PASS — 23 passed in 10.60s (incl. the 3 new tests and the unchanged `test_backup_integrity_trip`; `-v` grep confirms all four guardrail tests PASSED)
- `uv run pytest -q` (full suite): PASS — 203 passed in 36.76s, no regressions
- `uv run ruff check src/ tests/`: PASS — "All checks passed!"
- `uv run ruff format --check src/ tests/`: FAIL (pre-existing, NOT introduced by this change) — 7 files flagged; all 7 already fail at base commit `de7db5b` (verified by running the check against `git show de7db5b:` copies of the files). My `tests/test_mail_keeper.py` is format-clean ("already formatted"); the single hunk flagged in `mail_keeper.py` (the `return WorkflowResult(status=status, items_found=0, actions=actions, errors=errors)` rewrap in the batch-empty path, ~line 973) exists verbatim at base (line 963 there) — my diff does not touch it. The other 6 flagged files (`oc_todo.py`, `test_smoke_oc_todo.py`, `test_github.py`, `test_mail_prune.py`, `test_oc_todo.py`, `test_oc_todo_pipeline.py`) were not touched by this task at all. Making the full-repo command pass would require staging 6 files the dispatch forbids.

## Acceptance Verification

| # | Criterion (verbatim) | Result | Notes |
|---|---|---|---|
| 1. | `uv run pytest tests/test_mail_keeper.py -q` passes, including the 3 new tests AND the unchanged `test_backup_integrity_trip`. | PASS | 23 passed; `-v` output: `test_backup_integrity_trip PASSED`, `test_backup_snapshot_ignores_dotfiles PASSED`, `test_backup_snapshot_still_catches_mail_mutation PASSED`, `test_backup_integrity_no_trip_on_sync_state_rewrite PASSED`. |
| 2. | Full suite `uv run pytest -q` passes (no regressions elsewhere). | PASS | 203 passed, 0 failed. |
| 3. | `uv run ruff check src/ tests/` and `uv run ruff format --check src/ tests/` both pass. | FAIL | `ruff check` passes. `ruff format --check src/ tests/` exits non-zero due to **pre-existing** formatting debt: 7 files flagged, all already failing at base `de7db5b` (verified per-file against the base versions). This change adds no new formatting issues — `tests/test_mail_keeper.py` is format-clean and the only `mail_keeper.py` hunk is pre-existing. The literal command cannot pass under the dispatch constraint "stage ONLY the two task files" (6 of the 7 files are out of scope). See Blockers. |
| 4. | Behavior proven by tests: rewriting/deleting a dotfile alone → snapshots equal (no trip, workflow `status == "ok"` with `backup tree unchanged` action); touching/renaming-content/deleting a real mail file → snapshots differ (trip preserved). | PASS | Rewrite (different bytes + `os.utime` bump) of both `INBOX/.mbsyncstate` and `INBOX/.uidvalidity` → `snap1 == snap2`, neither dotfile a snapshot key, and no dot-prefixed key anywhere (`Path(p).name.startswith(".")` check); integration run with dotfile rewrite between the guardrail snapshots → `status == "ok"`, no `"guardrail trip"` error, `"backup tree unchanged" in result.actions`; touch (with `time.sleep(0.01)` as in the trip test), one-byte append, and deletion of `ACCOUNT/INBOX/cur/m1.eml` each flip the snapshot. |
| 5. | Commit `OC: mail-keeper guardrail — exclude syncer dotfiles (mbsync state) from backup snapshot` pushed to `feature/mail-guardrail-mbsync-exclusion` (verify with `git log --oneline -1` + `git status -s` showing only the pre-existing untracked planning files). | PASS | `git log --oneline -1` → `OC: mail-keeper guardrail — exclude syncer dotfiles (mbsync state) from backup snapshot` (referenced by message, not SHA, per protocol); `git push -u origin feature/mail-guardrail-mbsync-exclusion` succeeded (new remote branch, upstream tracking set); `git status -s` shows only the pre-existing untracked `planning/mail-guardrail-mbsync-false-trip/` and `planning/mail-keeper-pruning/*` files. |

## Blockers

1. **Acceptance criterion 3 (`ruff format --check src/ tests/`) fails due to pre-existing repo state, not this change.** At base commit `de7db5b` the command already fails on 7 files (`src/agentic_scripts/workflows/oc_todo.py`, `src/agentic_scripts/workflows/mail_keeper.py`, `tests/smoke/test_smoke_oc_todo.py`, `tests/test_github.py`, `tests/test_mail_prune.py`, `tests/test_oc_todo.py`, `tests/test_oc_todo_pipeline.py`) — verified by running the check against `git show de7db5b:` copies. 6 of the 7 are outside the dispatch's allowed staging set, and the plan mandates "one `continue` + docstring + tests. No refactoring", so I did not reformat anything. Orchestrator decision needed: (a) accept criterion 3 as "no new issues introduced" (my change satisfies that), or (b) dispatch a separate formatting task (e.g. `uv run ruff format` on the 7 files) so the gate goes green. Until then, `ruff format --check src/ tests/` will report FAIL on any branch of this repo.

## Next Steps

- Orchestrator: resolve the criterion-3 question above (accept as-is, or queue a pre-existing-formatting fix as a separate task).
- Open/merge the PR for `feature/mail-guardrail-mbsync-exclusion` into `feature/opencode-v2-run` (remote suggested: https://github.com/y2d2/agentic_scripts/pull/new/feature/mail-guardrail-mbsync-exclusion).
- No further tasks remain in this plan (`work_plan.md` lists Task 1 only; the step-e/cursor reordering, mbsync scheduling, cron boot-persistence, and V2 config hygiene items are explicitly out-of-scope follow-ups for separate tasks).
