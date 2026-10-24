# Task 5f — Pool ordering + fresh-frontier routing (Run-2 finding)

**Topic:** workflows-mail-keeper · **Depends on:** Task 5b · **Blocks:** the live backfill grind
**Status:** spec (pending dispatch) · **Owner:** lightweight-dev (session ses_e96dac798ffecqJlojaxBJDuxW)

## Context (what the live runs showed)

Acceptance Run 2 (2026-10-24 16:22 UTC, `status=ok`) left `state/mail-keeper.json` with
**`deferred` = 2,672 entries / 978 KB**. Root cause, traced in
`src/agentic_scripts/workflows/mail_keeper.py::_detect`:

1. **Fresh-frontier folders flood the pool as "new".** For any folder whose `new.last_date == 0`
   (never batched yet — all folders on a fresh bootstrap), line ~700 computes
   `new_set = [rows with ts > 0]` = the folder's ENTIRE in-window mail, and pass 1 collects it
   **unbounded** (the unboundedness exists to protect genuinely-new mail from starvation).
   Run 1 therefore put ~2,680 entries into `deferred_new = pool[10:]` (the whole backlog), and
   every later run re-injects + re-defers them (state rewrite each run).
2. **The pool is per-folder-block ordered, not globally newest-first.** The docstring/comment at
   lines ~712–715 claims "ordered GLOBALLY newest-first across folders (not per-folder)" but the
   code only appends per folder (each folder's rows individually newest-first). Consequence seen
   live: INBOX July-2026 history (pass 2, bounded) sits behind April-2026 mail from other
   folders (pass 1) — the opposite of the user-confirmed recency intent
   ("newest-first … older will most likely not be relevant anymore").

Correctness is unaffected (no loss, no dupes — processed-log + re-collection guarantee it), so
this is an ordering/state-hygiene fix, not a data-integrity fix.

## Changes (in `src/agentic_scripts/workflows/mail_keeper.py`)

### Change 1 — fresh-frontier folders route to the bounded history pass (~lines 700–710)

In the per-folder loop of `_detect`, after `new_last_date` / `back_last_date` are read:

```python
if new_last_date == 0:
    # Folder's new frontier has never advanced: it has no "new" mail — its entire
    # in-window mail is backfill. Route it to the bounded history pass so a fresh
    # bootstrap cannot flood the pool/deferred with the whole backlog. The floor
    # lower bound is enforced inside _collect (lower_bound = max(back, floor)).
    new_set: list[dict] = []
    hist_set = list(rows)
else:
    new_set = [row for row in rows if int(row.get("timestamp", 0)) > new_last_date]
    if back_last_date < floor:
        hist_set = []  # defensive completion-skip (unchanged)
    else:
        hist_set = [row for row in rows if back_last_date < int(row.get("timestamp", 0)) <= new_last_date]
```

(Same shape as today, just branched on `new_last_date == 0`. The existing
`back_last_date < floor` defensive guard stays on the non-fresh branch.)

### Change 2 — sort the pool globally newest-first before the cap (~line 737)

```python
pool.sort(key=lambda e: (-int(e["timestamp"]), e["message_id"]))
batch = pool[:MAX_BATCH]
deferred_new = [dict(c) for c in pool[MAX_BATCH:]]
```

This makes the batch the true global newest-first across new/deferred/history, and drains the
deferred queue in recency order. Tie-break on `message_id` for determinism. The
"new mail is never starved" invariant still holds: genuinely-new mail (new_last > 0 folders) is
still collected unbounded in pass 1 and, under global recency order, a NEW arrival always beats
OLDER history; a new arrival OLDER than current history is ordered by recency (not lost — it
stays in the pool/deferred and is processed in order).

### Docstrings

- `_detect` docstring: pass 1 bullet — "every folder's new_set (UNBOUNDED only for folders with
  an advanced frontier, new_last > 0; a fresh-frontier folder's mail is backfill → bounded
  history pass)"; merge-order bullet — "the pool is sorted globally newest-first
  (ts desc, id tie-break) before the cap is applied".
- Delete/fix the now-true comment at ~712–715 (it now matches the code — keep, reword to
  reference the sort).
- `_run` docstring step (c) cursor-advance note: add the recorded known-quirk — a folder's FIRST
  batched entries (old new_last = 0) advance `new`, not `back`; from the second touch onward
  `back` tracks correctly. Harmless (processed log + re-collection keep correctness; the
  backfill-complete guard is defensive-only). Document, do not fix.

## Tests (hermetic — `tests/test_mail_keeper.py`, fixture world m1–m10 + PII/own exclusions)

1. **Update `test_run_one_fresh_state_newest_first`** — expectations now: batch = the 10 newest
   KEPT messages **globally** (across folders), `deferred_new` **≤ 2·MAX_BATCH − 10** (the kept
   budget, not the whole world). Assert `len(deferred_new) <= MAX_BATCH` and batch order =
   descending timestamp.
2. **Verify `test_cross_folder_new_mail_not_starved`** still pins the invariant under global
   sort (its small-folder NEW mail is the newest candidate → still batched first). Adjust ONLY
   if the fixture dates make the new mail older than the history candidates — record any change
   in the result file.
3. **New `test_fresh_bootstrap_deferred_capped`** — fresh state, fixture world with >10 kept
   messages → batch = 10 newest globally; `len(deferred_new) <= MAX_BATCH`; a second `_detect`
   call (next run) re-picks up exactly `deferred_new`'s head minus processed — no loss, no dupe.
4. **New `test_pool_global_newest_first_order`** — two folders with interleaved dates
   (folder A: ts 90/70, folder B: ts 80/60) → batch order 90, 80, 70, 60 (global), NOT A-block
   then B-block.

## Acceptance criteria

1. `uv run pytest -q` → full suite green, **no ignores**; `uv run ruff check .` +
   `uv run ruff format --check .` clean.
2. All 4 tests above pass (2 updated/new in `tests/test_mail_keeper.py`).
3. Commit purity: exactly `src/agentic_scripts/workflows/mail_keeper.py` +
   `tests/test_mail_keeper.py` + the result file, `OC:`-prefixed, pushed to
   `plan/agentic-workflows`.
4. Result file: append a **Task 5f** section to
   `planning/workflows-mail-keeper/lightweight_dev_task_5_backfill_newest_first.md`
   (Run-2 finding, the two changes, test deltas incl. any test-2 adjustment, suite count,
   commit hash).

## Out of scope

- Cursor-update logic (documented known-quirk only, see Change 3 docstring).
- **State reset** — the ORCHESTRATOR performs it after verifying this task (delete
  `state/mail-keeper.json`; the processed log keeps the 30 records so nothing is re-triaged).
- Skill files, config, agent definitions.
