# Task 5c: Base reader decode fix (acceptance blocker)

**Purpose:** Acceptance Run 1 (live, 2026-10-24 08:13 UTC) failed in 40 s: `reader._run` uses `subprocess.run(..., text=True)` → strict UTF-8 decode of notmuch output. This notmuch 0.38.3 build emits message bodies RAW into `show --format=json` (known build quirk — the HTML-body gap), and a recent live message (FARI/Unitree thread, arrived in the last days) carries a **latin-1 `0xe9`** in its body → `UnicodeDecodeError: 'utf-8' codec can't decode byte 0xe9 in position 632` → workflow error, no state saved → **the backfill would fail on this message forever**. Fix the base reader's decode (lossless UTF-8 → latin-1 fallback) + regression test.

## Change (exact)

- **`src/agentic_scripts/mail/reader.py`** — `NotmuchReader._run`: replace `capture_output=True, text=True` with `capture_output=True` (bytes) and, after the non-zero-exit check:
  ```python
  out = proc.stdout or b""
  try:
      return out.decode("utf-8")
  except UnicodeDecodeError:
      return out.decode("latin-1")  # lossless fallback: latin-1 maps all 256 bytes
  ```
  Update the docstring (Returns/Raises) to document the fallback (one line). No other change to reader.py.
- **`tests/test_mail_reader.py`** (additive test, base test file — same class of additive base-test update approved earlier in this session): new test `test_show_latin1_body_fallback` — write a message with a latin-1 body into the throwaway maildir (raw bytes, e.g. subject/body containing `b"r\xe9sum\xe9"` — build the `.eml` with explicit latin-1 bytes, NOT utf-8), `notmuch new` the throwaway index, then `reader.show(msg_id)` and `reader.body_text(msg_id)` → both succeed and the body contains the decoded `é` characters (U+00E9). Also assert a UTF-8 message still decodes correctly (existing tests already cover this — do not duplicate).
- **Result file:** append a **Task 5c** section to `lightweight_dev_task_5_backfill_newest_first.md`: the acceptance-blocker context (Run 1 2026-10-24 08:13 UTC failure, traceback root cause), the fix, and the new test.

## Acceptance

1. `uv run pytest -q` fully green — NO ignores — + `uv run ruff check .` + `uv run ruff format --check .` clean.
2. The new latin-1 test passes (a latin-1 body decodes to proper `é` via `show`/`body_text`); the full existing suite is unchanged.
3. Commit purity: exactly `src/agentic_scripts/mail/reader.py` + `tests/test_mail_reader.py`; `OC:`-prefixed commit (e.g. `OC: Reader decode: UTF-8 with latin-1 fallback (Task 5c, acceptance blocker)`), pushed.
4. Quick live proof (read-only): `uv run python -c` reproducing the acceptance repro (fresh cursors, `_detect` over the live index) now returns a manifest without the decode error — record the manifest size + first 3 lines (subject/folder/ts) in the result report.

## Out of Scope

- Any other base file; the workflow module; agent/skill; live runs (the orchestrator re-runs acceptance after this).
