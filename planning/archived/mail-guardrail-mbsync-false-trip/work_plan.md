# Work Plan: mail-keeper guardrail — exclude mbsync bookkeeping from snapshot

**Purpose:** Stop the backup-integrity guardrail false-tripping when the host-side mbsync sync rewrites its per-folder state files (`.mbsyncstate`, `.uidvalidity`) during an agent run, while keeping full detection power for any real mutation of mail files.

## Objective

On 2026-11-20 the first v2-era forced mail-keeper run (10:58–13:22, agent `status=ok`, triage complete, commit `7f3c9a9` pushed) ended with a workflow-level error: `mail backup tree changed during the run (guardrail trip)`. Root cause: the host-side mbsync sync at 11:00 rewrote exactly four bookkeeping files — `INBOX/.mbsyncstate`, `INBOX/.uidvalidity`, `Sent Items/.mbsyncstate`, `Sent Items/.uidvalidity` — mid-run; `_backup_snapshot()` (byte-identity over `{relpath: (size, mtime_ns)}`) includes those dotfiles, so the comparison tripped. No mail file changed. The trip was report-only (state persist at step (e) precedes the check at step (f)), so no data loss and no re-processing occurred — but with 2–3 h nightly runs and periodic mbsync syncs, the false error will recur.

Desired end state: `_backup_snapshot()` ignores tool bookkeeping dotfiles (maildir mail files never start with `.`), so sync-state rewrites no longer trip the guardrail, while any mutation/touch/deletion of an actual mail file still trips it. Covered by new unit + integration tests.

## Context

- Repo: `/workspace/Python/agentic_scripts` (branch `feature/opencode-v2-run`, HEAD `de7db5b`). Python 3.12, uv, pytest, Ruff (see `pyproject.toml` / `python-dev-loop` skill: `uv run pytest`, `uv run ruff check`, `uv run ruff format`).
- Guardrail code: `src/agentic_scripts/workflows/mail_keeper.py`, `_backup_snapshot(mail_root)` (lines ~265–303). Walks with `os.walk` (GNU `find` does NOT descend this maildir — documented reproduced failure; never use `find` on it), maps each regular file to `(st_size, st_mtime_ns)`. Called before (line ~968) and after (line ~1063) the agent invocation; any dict difference appends the error `mail backup tree changed during the run (guardrail trip)`.
- Maildir naming: mail files look like `1791910414.1_24.3c9813293be1,U=24:2,` (uniq = epoch-based, never dot-prefixed). Tool bookkeeping is dot-prefixed: mbsync writes `<folder>/.mbsyncstate` and `<folder>/.uidvalidity` (mbsync runs on the docker host — no mbsync process inside the container; the volume is shared).
- The agent is permission-denied from `mail/backup/**` (edit + write) and from bash segments matching `*mail/backup/*` — it cannot write the dotfiles either, so excluding them does not weaken the guardrail's anti-violation power.
- Tests: `tests/test_mail_keeper.py` — hermetic fixture `hermetic_mail` (provides `mail_root` with `ACCOUNT/INBOX/cur/m1.eml` etc.), helpers `_set_mail_env`, `_make_ctx`, `_run_workflow`, `_FakeRunner`, `_ok_result`, `_triage_table`. Existing guardrail test: `test_backup_integrity_trip` (~line 1247) monkeypatches the 2nd snapshot call to `touch()` a real mail file and asserts `status == "error"` + `"guardrail trip"`.
- Git conventions (skill: git-workflow): feature branch only, `OC:` commit prefix, push after commit, stage explicit paths only (never `git add -A` — the working tree has unrelated untracked `planning/mail-keeper-pruning/*` files that must stay untouched).

## Tasks

### Task 1: Exclude dotfile bookkeeping from `_backup_snapshot` (+ tests)
See `work_plan_task_1_snapshot_dotfile_exclusion.md` (self-contained).

## Out of Scope
- Reordering step (e) state-persist vs step (f) guardrail check — a semantics decision (rollback vs report-only) for a separate task.
- mbsync host-side scheduling / the maildir filesystem quirk itself.
- Cron boot-persistence (start cron on container boot) — separate infra task.
- V2 config hygiene (top-level `subagent_depth`, V1 frontmatter sampling, duplicate `mail-keeper` skill) — separate task.
- Any change to the agent's permission denies or the guardrail's error message.

## Notes
- [Assumption] No tool that writes into the maildir names a MAIL file with a leading dot (maildir spec + live-tree observation back this; the live tree shows only dot-prefixed tool files: `.mbsyncstate`, `.uidvalidity`).
- [Assumption] `hermetic_mail` fixture files are real regular files writable by the test (the existing trip test `touch()`es one) — new tests reuse the same fixture.
- The incident evidence (4 files, 11:00 mtime) was collected with `find -L` + `stat`; the fix makes the guardrail immune to the whole class of sync-state rewrites, not just those 4 names.
