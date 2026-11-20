# Task Plan: Guardrail dotfile exclusion (mbsync false-trip fix)

**Purpose:** Make `_backup_snapshot()` skip tool bookkeeping dotfiles so the mbsync state-file rewrite no longer false-trips the mail-keeper backup guardrail, with regression tests proving real mail-file mutations still trip it.

## Objective

The 2026-11-20 10:58–13:22 forced mail-keeper run (agent `status=ok`, commit `7f3c9a9` pushed) ended `status=error` with `mail backup tree changed during the run (guardrail trip)` because the host-side mbsync sync at 11:00 rewrote `INBOX/.mbsyncstate`, `INBOX/.uidvalidity`, `Sent Items/.mbsyncstate`, `Sent Items/.uidvalidity` mid-run, and the byte-identity snapshot includes dotfiles. After this task: dotfile rewrites must NOT trip the guardrail; any mutation/touch/deletion of a real mail file MUST still trip it. Full test suite + ruff green.

## Context

- Repo root: `/workspace/Python/agentic_scripts`. Tooling: `uv` (`/root/.local/bin/uv`), Python 3.12, pytest, Ruff. Run tests from the repo root: `uv run pytest -q`, lint: `uv run ruff check src/ tests/`, format: `uv run ruff format --check src/ tests/`.
- Target file: `src/agentic_scripts/workflows/mail_keeper.py`.
  - `_backup_snapshot(mail_root: Path) -> dict[str, tuple[int, int]]` is at ~lines 265–303. Current inner loop:
    ```python
    for dirpath, _dirnames, filenames in os.walk(root):
        base = Path(dirpath)
        for name in filenames:
            full = base / name
            try:
                if not full.is_file():
                    continue
                stat = full.stat()
            except OSError:
                continue  # a file that vanished mid-walk is not a guardrail concern
            rel = str(full.relative_to(root))
            snapshot[rel] = (stat.st_size, stat.st_mtime_ns)
    return snapshot
    ```
  - It is called at ~line 968 (`snapshot_before = _backup_snapshot(mail_root)`) and ~line 1063 (`snapshot_after = ...`); `if snapshot_before != snapshot_after:` appends the error `mail backup tree changed during the run (guardrail trip)` (line ~1065), and the `backup tree unchanged` action is added at ~line 1072. Do NOT change either call site or the error message.
  - Docstring of `_backup_snapshot` currently has Purpose/Rationale/Args/Returns sections. Keep that structure; extend it.
  - IMPORTANT constraint (from the docstring, keep it true): GNU `find` does not descend this maildir (reproduced failure) — the function must keep using `os.walk`; do not "fix" the walk into a `find`-based implementation. Tests must not shell out to `find` on a maildir either.
- Maildir naming: mail files look like `1791910414.1_24.3c9813293be1,U=24:2,` — uniq is epoch-based and NEVER dot-prefixed. All tool bookkeeping in the tree is dot-prefixed (mbsync: `<folder>/.mbsyncstate`, `<folder>/.uidvalidity`; mbsync runs on the docker host, not in this container). The agent is permission-denied from `mail/backup/**` (edit/write) and from bash segments `*mail/backup/*`, so it cannot write those dotfiles — the exclusion does not weaken anti-violation detection.
- Test file: `tests/test_mail_keeper.py`.
  - Fixture `hermetic_mail` (from `tests/conftest.py`) provides `hermetic_mail["mail_root"]` containing `ACCOUNT/INBOX/cur/m1.eml`, `ACCOUNT/INBOX/new/...` etc. (the existing trip test touches `hermetic_mail["mail_root"] / ACCOUNT / "INBOX" / "cur" / "m1.eml"` — module-level constant `ACCOUNT`).
  - Existing guardrail test `test_backup_integrity_trip` (~line 1247): monkeypatches `mail_keeper._backup_snapshot` so the 2nd call `touch()`es a real mail file, runs the workflow via `_run_workflow(ctx)`, asserts `result.status == "error"` and `any("guardrail trip" in e for e in result.errors)`. Leave this test unchanged — it must keep passing after the fix (it mutates a real mail file, not a dotfile).
  - Helpers available: `_set_mail_env(monkeypatch, hermetic_mail, tmp_path)`, `_make_ctx(tmp_path, hermetic_mail, admin_repo=..., fake_runner=...)`, `_run_workflow(ctx)`, `_FakeRunner(_ok_result(_triage_table([...]))`, module constants `M1_ID`–`M10_ID`, `ACCOUNT`.

## Tasks

### Task 1: Exclude dotfile bookkeeping from `_backup_snapshot`
- **Files:** `src/agentic_scripts/workflows/mail_keeper.py` (modify), `tests/test_mail_keeper.py` (modify)
- **Do:**
  1. In `_backup_snapshot`, at the TOP of the inner `for name in filenames:` loop, skip dot-prefixed entries:
     ```python
     for name in filenames:
         if name.startswith("."):
             # Tool bookkeeping (mbsync: .mbsyncstate / .uidvalidity, written by the
             # host-side syncer mid-run 2026-11-20 11:00 -> false guardrail trip).
             # Maildir mail files are epoch-uniq named and never dot-prefixed.
             continue
     ```
     (Comment wording may vary; keep the incident reference.) Do not change the `os.walk` usage, the `is_file()`/`stat()` logic, or the return shape.
  2. Update the `_backup_snapshot` docstring: in Rationale (or a new Purpose/Rationale sentence) state that dot-prefixed entries (tool bookkeeping such as mbsync `.mbsyncstate`/`.uidvalidity`) are intentionally excluded — they are written by the host-side syncer, never by the agent (which is permission-denied from the tree) — and cite the 2026-11-20 false-trip incident.
  3. In `tests/test_mail_keeper.py`, add a new section (e.g. `# 8b. Backup snapshot dotfile exclusion`) with these tests:
     - `test_backup_snapshot_ignores_dotfiles(hermetic_mail)`: create `<mail_root>/<ACCOUNT>/INBOX/.mbsyncstate` and `<mail_root>/<ACCOUNT>/INBOX/.uidvalidity` with distinct contents; `snap1 = mail_keeper._backup_snapshot(mail_root)`; rewrite both dotfiles (different bytes + `os.utime` bump); `snap2 = ...`; assert `snap1 == snap2`; also assert neither dotfile path is a key in `snap1` (and no dot-prefixed key exists anywhere: `assert not any(p.startswith(".") for p in snap1)` — relative paths, so check the basename: `any(Path(p).name.startswith(".") for p in snap1)`).
     - `test_backup_snapshot_still_catches_mail_mutation(hermetic_mail)`: `snap1`; then (a) `touch()` `ACCOUNT/INBOX/cur/m1.eml` (as the existing trip test does, with a small sleep for mtime resolution) → `snap2 != snap1`; rebuild `snap1` fresh, (b) append one byte to the same mail file → differ; rebuild, (c) delete the mail file → differ. (Each mutation: re-snapshot AFTER, compare against a snapshot taken BEFORE that mutation.)
     - `test_backup_integrity_no_trip_on_sync_state_rewrite(hermetic_mail, tmp_path, monkeypatch)`: integration — mirror `test_backup_integrity_trip`, but the monkeypatched 2nd snapshot call rewrites a NEW dotfile (e.g. `ACCOUNT/INBOX/.mbsyncstate` with different content + utime bump) instead of touching the mail file; run `_run_workflow(ctx)` with the same `_FakeRunner(_ok_result(_triage_table([...])))` pattern; assert `result.status == "ok"`, `not any("guardrail trip" in e for e in result.errors)`, and `"backup tree unchanged" in result.actions`. Clean up any dotfile you created so other tests see a pristine fixture (fixture is per-test tmp-based, so creating inside the test is safe; still remove what you add).
  4. Run: `uv run pytest tests/test_mail_keeper.py -q`, then the full suite `uv run pytest -q`, then `uv run ruff check src/ tests/` and `uv run ruff format --check src/ tests/`.
  5. Git (skill: git-workflow): from the repo root, `git checkout -b feature/mail-guardrail-mbsync-exclusion` (base: current HEAD `de7db5b`, branch `feature/opencode-v2-run`), stage ONLY `src/agentic_scripts/workflows/mail_keeper.py` and `tests/test_mail_keeper.py` (explicit paths — never `git add -A`; the untracked `planning/mail-keeper-pruning/*` files must stay untouched), commit with message `OC: mail-keeper guardrail — exclude syncer dotfiles (mbsync state) from backup snapshot`, then `git push -u origin feature/mail-guardrail-mbsync-exclusion`.
- **Notes:**
  - Keep the change minimal and local: one `continue` + docstring + tests. No refactoring of the snapshot function, no new parameters, no behavior change for non-dot files.
  - The relative-path keys in the snapshot look like `yuri.durodie@vub.be/INBOX/cur/m1.eml` in production; in the hermetic fixture the account dir is `ACCOUNT`. The dotfile check is on the FILENAME (`name.startswith(".")`), not on the rel path — this also covers dotfiles at any depth.
  - `os.utime` is needed for deterministic mtime bumps in tests (naive `touch` + `time.sleep(0.01)` is what the existing test uses; either is fine, but keep it deterministic where easy).
  - If `test_backup_integrity_trip` (existing) fails after the change, the fix is wrong — the mail-file trip must keep working. Do not modify that test.
- **Acceptance:**
  1. `uv run pytest tests/test_mail_keeper.py -q` passes, including the 3 new tests AND the unchanged `test_backup_integrity_trip`.
  2. Full suite `uv run pytest -q` passes (no regressions elsewhere).
  3. `uv run ruff check src/ tests/` and `uv run ruff format --check src/ tests/` both pass.
  4. Behavior proven by tests: rewriting/deleting a dotfile alone → snapshots equal (no trip, workflow `status == "ok"` with `backup tree unchanged` action); touching/renaming-content/deleting a real mail file → snapshots differ (trip preserved).
  5. Commit `OC: mail-keeper guardrail — exclude syncer dotfiles (mbsync state) from backup snapshot` pushed to `feature/mail-guardrail-mbsync-exclusion` (verify with `git log --oneline -1` + `git status -s` showing only the pre-existing untracked planning files).

## Out of Scope
- Reordering state-persist (step e) vs guardrail check (step f) in `mail_keeper.run`.
- Changing the guardrail error message, call sites, or the agent permission config.
- mbsync scheduling, cron boot persistence, V2 config hygiene items.

## Notes
- [Assumption] No legitimate mail file in this maildir is dot-prefixed (maildir epoch-uniq naming; live tree observation). If the dev agent finds a counterexample in the hermetic fixture or live tree, STOP and report as a blocker rather than special-casing.
- The live production maildir cannot be used in tests (and `find` must not be run on it) — all tests use the hermetic fixture.
