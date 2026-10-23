# Task Plan: Backfill redesign — newest-first with 1-year floor

**Purpose:** Re-design the mail-keeper backfill per the user decision of 2026-10-23: (a) process history **newest-first** (not oldest-first), (b) backfill **at most 1 year** of history — anything older is out of scope ("older will most likely not be relevant anymore"), (c) **newly arriving mail must never be starved** while the backfill is in flight — each run fills its batch with new mail first, then history newest-first. The repo runner state is FRESH (`state/mail-keeper.json` absent — verified 2026-10-23), so no migration is needed.

## Objective

Rewrite the detection/state portion of `src/agentic_scripts/workflows/mail_keeper.py` from the single-forward-cursor/oldest-first model to a **two-boundary model** (per folder: `new` = newest-seen forward boundary, `back` = oldest-processed backward frontier) with a fixed **1-year floor**, update the hermetic tests (`tests/test_mail_keeper.py`, `tests/smoke/test_smoke_mail_keeper.py`, including fixture extension) and the README backfill paragraph. Outcome: run 1 = the 10 NEWEST messages in the past year; each later run = new mail first, then history newest-first (capped 10) until every folder's frontier reaches the floor; then steady state (new-mail-only, fast runs). All guardrails (canary, PII, owner, processed-log dedup, deferred, backup byte-identity, `MAX_BATCH = 10`, agent-failure semantics, brief format, triage-table parse) stay exactly as they are.

## Context

- **Repo:** `/workspace/Python/agentic_scripts`, branch `plan/agentic-workflows`. Conventions: Google-style docstrings, `uv run ruff check .` + `uv run ruff format --check .` clean (line length 100), hermetic tests only, commit `OC:` prefix, push, ONLY this task's files, `uv sync --extra dev` if re-syncing (bare `uv sync` drops dev extras).
- **What exists (modify only what the spec says):** `src/agentic_scripts/workflows/mail_keeper.py` (816 lines — Task 3: canary → state → detection (per-folder `search`, oldest-first walk, owner/PII/processed-log exclusion, `deferred` cap list) → manifest ≤10 → one agent call → on ok: processed-log append (v1 6-field schema), cursor advance, state save, backup byte-identity; includes the notmuch 0.38.3 thread-root workaround — `_find_message_by_id`-style recovery, KEEP IT), `tests/test_mail_keeper.py` (8 hermetic tests, throwaway notmuch index, injected fake agent), `tests/smoke/test_smoke_mail_keeper.py` (4 tests + fixture world: 6 messages m6/m1/m2/m3/m4(PII)/m5(own), fixture vault + bare remote + good/failure shims), `README.md` (`## Mail-keeper workflow` section, Task 4). Do NOT modify: `mail/mail_search.py`, `mail/canary.py`, `config/workflows.yaml`, base tests, agent/skill, `opencode.jsonc`.
- **State reality (verified 2026-10-23):** `state/mail-keeper.json` does not exist in the repo (fresh — no v1 state to migrate). The processed log `/workspace/Obsidian/config/email-processing-log.jsonl` exists with 10 records of **2021** mail (from the user's own 11 test runs of the real agent, 2026-10-22/23) — all outside the new floor, so they will never be presented again; **leave the file untouched** (it is the user's test-run record and the dedup safety net). The two `/tmp` state files (`/tmp/ac2_spot`, `/tmp/tmpvpiyef1g`) are dev artifacts, irrelevant to production state.
- **Measured window (read-only counts, 2026-10-23, live index 13,160 total):** `date:2025*` = 2,813; `date:2026*` = 2,980 → the 1-year window (floor = first-run-now − 365 d = 2025-10-23) ≈ **~3,500 messages ≈ ~350 runs** of `MAX_BATCH = 10`. Pace: quiet-window overnight schedule (≈8–10 runs/night) ≈ 10–12 weeks; chained `--force` runs (≈10/hour, agent runs ~1 h) ≈ 2 weeks.
- **notmuch order (load-bearing, verified Task 3):** `search --format=json` rows come back **newest-first** by default — the new design uses that order directly (the old spec's "reverse to oldest-first" is removed; keep a test pinning the natural order).
- **Costs (measured Task 1):** one `notmuch show` ≈ 0.5–0.6 s live; per-folder full `search` ≈ 1 s; canary walk ≈ 1–3 s. Per-run budget ≤ ~20 shows holds unchanged.

## Design (source of truth — implement exactly this)

### State document v2

```json
{
  "bootstrapped_at": "<ISO-8601, first run>",
  "backfill_floor": <int epoch seconds>,
  "cursors": {
    "<folder>": {
      "new":  {"last_date": <int epoch>, "last_message_id": "<id>"},
      "back": {"last_date": <int epoch>, "last_message_id": "<id>"}
    }
  },
  "deferred": [ {"message_id": "...", "folder": "...", "timestamp": <int epoch>}, ... ]
}
```

- `new` = forward boundary (max ts the workflow has handed to the agent). New mail = `ts > new.last_date`.
- `back` = backward frontier (oldest ts processed in that folder). History candidates = `back.last_date < ts <= new.last_date`.
- `backfill_floor` = `now − 365*86400` captured at FIRST run, stored, never recomputed.
- **Fresh-state initialization:** `backfill_floor = now − 365*86400`; per triage folder `new = {"last_date": 0, "last_message_id": ""}`, `back = {"last_date": <floor>, "last_message_id": ""}`. (Run 1: `new_set` = everything (`ts > 0`), `hist_set` = ∅ (`ts <= 0` impossible); the floor filter then excludes pre-floor mail.)
- **v1 schema guard:** on load, if `backfill_floor` is missing or any folder entry lacks both `new` and `back` keys (v1 shape) → workflow returns `status="error"` with a message containing `"state schema mismatch"` and the instruction `"delete state/mail-keeper.json"`. No auto-migration.

### Detection (per run, per triage folder `f` with cursors `c`)

1. `rows = reader.search(q_folder(account, f), limit=10**9)` — ONE search per folder (unchanged; ~1 s live).
2. **Split:** `new_set = [r for r in rows if r["timestamp"] > c["new"]["last_date"]]`; `hist_set = [r for r in rows if c["back"]["last_date"] < r["timestamp"] <= c["new"]["last_date"]]` — **EXCEPT** when `c["back"]["last_date"] <= backfill_floor` (folder's backfill complete): `hist_set = []` (sound: every message in `(floor, new]` was already evaluated — kept ⇒ in the processed log, or excluded ⇒ permanently owner/PII; message timestamps are immutable).
3. **Order both sets newest-first** (notmuch's natural row order — do not reverse; keep the test pinning this).
4. **Merge:** `candidates = new_set + deferred + hist_set`, de-duplicated by message id (deferred is re-injected so cap-overflow mail is never lost; the processed-log id set is read once at run start and used in step 5).
5. **Walk + per-message filter** (as today, over the merged candidates, threads, collecting up to ≥ `2 * MAX_BATCH` ids): per id `doc = reader.show(id)` (on `NotmuchError`: skip + log); **recover the requested message object from `doc["raw"]` (thread-root quirk — unchanged)**; keep iff `msg["timestamp"] > c["back"]["last_date"]` (strict — the floor is enforced because `back.last_date` starts at the floor and only moves down… and only to processed-min, see step 8; invariant: never below the floor, because every kept ts > the previous frontier ≥ floor), AND From ≠ owner address (case-insensitive), AND not under the PII prefix, AND not in the processed-log id set.
6. `manifest = first MAX_BATCH kept` (merge order = new mail first, then deferred, then history newest-first); `deferred_new = kept beyond the cap` (stored as `{"message_id","folder","timestamp"}`).
7. **Backfill-complete log:** if a folder's frontier crosses the floor this run (old `back.last_date` > floor ≥ new value) → log INFO `"backfill complete for <folder>"`.
8. **Cursor update (only on `agent.status == "ok"`, only if the manifest is non-empty):** `new.last_date = max(new.last_date, max ts of the manifest)`, `new.last_message_id` = that newest manifest id; `back.last_date = min(back.last_date, min ts of the manifest)`, `back.last_message_id` = that oldest manifest id. (Manifest min/max across ALL members — kind-agnostic; the min/max make updates monotone and safe for deferred-overflow re-presentation. Invariant: `back.last_date` never drops below the floor.) Then `deferred = deferred_new`; save state; then processed-log append (every manifest entry, v1 6-field schema — unchanged); then backup byte-identity check (unchanged).
9. **No-new-mail:** merged candidate pool (after the completion-skip) empty → status `ok`, NO agent call, state re-saved with identical content (or skipped — content must be unchanged), fast (< 10 s smoke guard).
10. **Agent failure:** `status="error"`, NO cursor advance, NO log append → the identical batch (incl. deferred) is re-presented next run (unchanged semantics).

### Brief / agent contract / triage parse

Unchanged. The brief's manifest order = merge order (new mail first). The agent's provenance/dedup/commit contract is untouched.

### README

Rewrite ONLY the backfill paragraph of `## Mail-keeper workflow`: first run = 10 NEWEST messages of the past year; every run: new mail first, then history newest-first, 10 per run; floor = first-run − 1 year (fixed) — mail older than that is never triaged; per-folder backfill completes when the frontier reaches the floor (steady state = new-mail-only runs); measured window ≈ 3,500 messages ≈ ~350 runs (2025: 2,813 / 2026: 2,980 of a 13,160-message index, measured 2026-10-23); pace: overnight schedule ≈ 10–12 weeks, chained `--force` ≈ 2 weeks; new mail is never starved. Do not rewrite the rest of the section.

### Tests

**Fixture extension (both test files, keep the two worlds aligned):** add `m8` — old mail, `Date: 2025-03-15` (OUTSIDE the floor: test `now` = 2026-10-21 22:30 ⇒ floor = 2025-10-21), `INBOX/cur/`, `<m8@fixture.test>`; fix explicit distinct timestamps: `m1 = 2026-10-21T09:00`, `m2 = 2026-10-21T10:00`, `m3 = 2026-10-21T11:00` (INBOX), `m6 = 2026-08-15` (INBOX), plus `m9 = 2026-09-15` and `m10 = 2026-07-15` (INBOX) for the multi-run backfill tests; `m4` (PII) and `m5` (own, Sent Items) unchanged. Newest-first pool order (full fixture, in-window): `m3, m2, m1, m9, m6, m10` (`m8` excluded by the floor).

**`tests/test_mail_keeper.py`** (rewrite the order-sensitive tests; keep canary/byte-identity/failure tests, adapted):
1. `test_run_one_fresh_state_newest_first` — fresh world, `MAX_BATCH` default (10): run 1 brief ids == `[m3, m2, m1, m9, m6, m10]` (newest-first; `m4`/`m5`/`m8` ABSENT); processed log 6 lines in that order; state v2: `backfill_floor` == now−365d (±2 s), `new.last_date` == ts(m3), `back.last_date` == ts(m10) (manifest min).
2. `test_run_two_no_new_mail_hist_filtered_by_log` — continue: no agent call, status ok, processed-log count unchanged, state content identical (the `hist_set` re-walk of m1/m2 is filtered by the processed log).
3. `test_run_three_new_mail` — add `m7 = 2026-10-22T12:00` + reindex: manifest exactly `[m7]`; `new.last_date` == ts(m7); `back.last_date` unchanged (ts(m10)).
4. `test_new_mail_not_starved_during_backfill` — FRESH world, `monkeypatch.setattr` `mail_keeper.MAX_BATCH = 3`: run 1 manifest == `[m3, m2, m1]`, `deferred == [m9, m6, m10]` (kept overflow, newest-first), state `back.last_date` == ts(m1); then add `n1 = 2026-10-22T09:00` + reindex; run 2 manifest == `[n1, m9, m6]` — **assert `n1` first even with 3 deferred history messages waiting** (no starvation); state `new.last_date` == ts(n1), `back.last_date` == ts(m6); `deferred == [m10]`.
5. `test_floor_excludes_old_mail` — `m8` absent from every brief across runs 1–4 above (parametrize or re-run the sequence in one test).
6. `test_agent_failure_retry` — failure shim: status error, no state file (fresh world) / state unchanged, processed log absent; retry with good shim re-presents the same ids (adapted from the current test).
7. `test_v1_schema_guard` — pre-write a v1-shaped state (folder entry without `new`/`back`) → run → status error, message contains `"state schema mismatch"`.
8. Keep the existing canary-staleness and backup-byte-identity tests (adapt fixtures if the message count changed).

**`tests/smoke/test_smoke_mail_keeper.py`** (update expectations; the world builder gains `m8/m9/m10` + explicit timestamps):
- test 1 (backfill batch one): brief ids == `[m3, m2, m1, m9, m6, m10]` newest-first; `m8`/`m4`/`m5` absent; processed log 6 lines (order + classes per the shim table); provenance edits/todo/draft for `m1` unchanged; `OC:` commit pushed; backup byte-identity unchanged; shim triage table updated to the 6 rows (classes: m3/m2 noise, m1 action, m9/m6/m10 noise — keep the existing m1 action row).
- test 2 (no-new-mail run 2): unchanged semantics (no agent, counts unchanged, HEAD unchanged, < 10 s).
- test 3 (new mail m7): unchanged (manifest exactly `[m7]`, log +1, zero duplicates).
- test 4 (failure retry): unchanged (same ids re-presented, then full success).
- Shim: still writes `brief.txt` first; parses the ACTUAL `_render_brief` format; triage table rows only for received ids (keep the failure shim).

## Acceptance

1. `uv run pytest -q` fully green — **no ignores** (base suite, Task 1/3 tests, updated Task 3/5 tests, the 4 smoke tests, all 7 scheduler tests) — plus `uv run ruff check .` and `uv run ruff format --check .` clean.
2. Run 1 of the fresh-state test presents the NEWEST in-window messages first (`[m3, m2, m1, m9, m6, m10]` in the fixture) and the >1-year-old `m8` is never presented in any test run; state v2 fields exactly as designed (floor = now−365d, `new`/`back` per the min/max rule).
3. `test_new_mail_not_starved_during_backfill` passes (new mail ahead of deferred/history in the batch).
4. Steady state: with the frontier at the floor the history walk is skipped (test 2 proves no agent call + unchanged state; assert no `show`-driven manifest beyond new mail).
5. `test_v1_schema_guard` passes (clear error, no auto-migration).
6. README backfill paragraph rewritten per the spec (newest-first, 1-year floor, no starvation, measured ~3,500 msgs / ~350 runs, pace options).
7. Commit purity: exactly `src/agentic_scripts/workflows/mail_keeper.py`, `tests/test_mail_keeper.py`, `tests/smoke/test_smoke_mail_keeper.py`, `README.md` in the new commit; `.env` untracked (`git check-ignore .env` passes).
8. Hermetic: the test modules never reference `/workspace/docker/mbsync` or `/workspace/Obsidian/ARP_roadmap` (grep both, 0 hits — rewrite docstrings if needed), no live LLM, no live index/maildir (the fixture world only). The ONE allowed live touch: a single read-only `notmuch count` pair for the README note (generated read-only reader config, `synchronize_flags=false`) — record the numbers in the result report (they should match 2,813 / 2,980).

## Out of Scope

- Agent/skill/`opencode.jsonc` changes; processed-log schema changes; changing `MAX_BATCH` in production code (tests may monkeypatch it); canary/`mail_search` changes; state migration (there is no v1 state in the repo); starting any LIVE backfill run (that is the acceptance protocol, after this task verifies); the mbsync WIP; the cron entry (already fixed and armed).

## Notes

- **[Note]** In the new design the **processed log is the primary history-dedup mechanism** (a message already handed to the agent sits in `(back, new]` and must be filtered on re-walk); it stays runner-owned. The 10 pre-existing 2021 records are outside the floor — inert.
- **[Note]** The frontier update is **manifest min/max across all members** (not per-kind): this keeps the frontier a true "everything above was evaluated" boundary, makes deferred-overflow re-presentation safe, and bounds re-walk waste to the few messages inside the last batch's ts-span.
- **[Note]** `notmuch search` natural order is newest-first (verified Task 3) — no reversal; a test pins it.
- **[Note]** Per-run cost unchanged: ≤13 searches + ≤20 shows; steady-state (post-completion) runs walk only `new_set` (≤10 shows) — cheap.
- **[Note]** Measured window for the README: 2025: 2,813 / 2026: 2,980 / total 13,160 (2026-10-23, read-only) ⇒ ≈3,500 in the 1-year window ⇒ ≈350 runs.
- **[Note]** Use `uv sync --extra dev` if re-syncing (bare `uv sync` drops dev extras — verified Task 1).
- **[Assumption]** `mail_keeper.MAX_BATCH` is a module-level constant the tests can `monkeypatch.setattr` (it is — Task 3 defines `MAX_BATCH = 10` at module level).
