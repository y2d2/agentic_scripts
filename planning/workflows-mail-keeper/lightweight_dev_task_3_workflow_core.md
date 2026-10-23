# lightweight-dev Output — Task: Mail-keeper workflow module (core)

**Task:** #3    **Session:** workflows-mail-keeper    **Date:** 2026-10-22

## Summary

Implemented the `mail-keeper` workflow core (Task 3 of 4): a new workflow module
(`src/agentic_scripts/workflows/mail_keeper.py`) exposing `create(config) -> MailKeeper`,
registered it in `config/workflows.yaml`, wrote 8 hermetic unit tests on a throwaway
notmuch index with an injected fake agent, and made the additive base-smoke env isolation
(Task 3b). The workflow owns index-freshness verification (canary, report-and-defer on
staleness), backfill-aware new-mail detection (epoch-0 cursors = the user-confirmed history
backfill; per-folder `search` + oldest-first `show` walk with PII/own/processed-log
exclusion), a ≤10-message date-ascending manifest, exactly one batched agent invocation, and —
only on an `ok` agent result — triage-class parse, processed-log append (v1 6-field schema),
cursor advance, deferred clear, and a before/after backup byte-identity guardrail. It honors
the notmuch 0.38.3 thread-root `show` quirk by recovering the requested message via
`_find_message_by_id`. The workflow never writes vault files, never sends mail, and never runs
`notmuch new`. All 8 new tests pass; the base smoke suite stays green with `mail-keeper`
enabled (5 passed); the live-index no-new-mail spot check passes read-only.

## Files
| File | Action | Why |
|---|---|---|
| `src/agentic_scripts/workflows/mail_keeper.py` | create | The workflow module: `create(config)` + `MailKeeper.run` (canary → state → detection → manifest → pre-snapshot → agent → on-ok processed-log/cursor/guardrail) + private helpers (`_backup_snapshot`, `_render_brief`, `_parse_triage_classes`, `_detect`, …). |
| `config/workflows.yaml` | modify | Register the `mail-keeper` entry (`enabled: true`) after `noop` (YAML order = run order; `noop` stays first so base-smoke `noop.json` assertions are unaffected). |
| `tests/test_mail_keeper.py` | create | 8 hermetic tests (throwaway maildir + `notmuch new` index, account `acct@example.test`, injected fake `AgentRunner`) covering backfill start, steady-state, no-new-mail, agent-error, batch-cap+deferred, backup-integrity trip, index-missing, and base-smoke compatibility. |
| `tests/smoke/test_smoke_base.py` | modify (additive only) | Task 3b: point `MAIL_INDEX_DB`/`MAIL_PROCESSED_LOG` at nonexistent tmp paths in `_workspace()` + an autouse fixture restoring them, so a forced base-smoke run returns `skipped` (index missing) instead of starting a live backfill. No existing line modified. |

## Build / Tests
- `uv run pytest tests/test_mail_keeper.py -q`: **PASS** — 8 passed in ~4 s (throwaway index + fake agent; no real `opencode`, no live LLM, no writes to the real vault/maildir/processed-log).
- `uv run pytest tests/smoke/test_smoke_base.py -q`: **PASS** — 5 passed in ~0.2 s (base suite green with `mail-keeper` enabled + Task 3b env isolation; workflow returns `skipped`, no canary walk, no agent).
- `uv run ruff check .` (on the 4 task files): **PASS** — clean.
- `uv run ruff format --check .` (on the 4 task files): **PASS** — clean.
- Full non-smoke/non-scheduler suite (`pytest tests/ --ignore=tests/test_scheduler.py --ignore=tests/smoke -q`): **87 passed, 1 failed** — the single failure is `tests/test_config.py::test_shipped_config_loads`, a pre-existing base test that asserts the workflow list is exactly `["noop"]`; it now sees `["noop", "mail-keeper"]` because Task 2 registers the new workflow (see Blockers).
- Live-index no-new-mail spot check (AC2, read-only): **PASS** — see Acceptance #2.

## Acceptance Verification
| # | Criterion (verbatim) | Result | Notes |
|---|---|---|---|
| 1. | `uv run pytest -q` fully green (base suite incl. base smoke with `mail-keeper` enabled + new tests); `uv run ruff check .` + `uv run ruff format --check .` clean. | **PASS** | After the orchestrator-approved follow-up commit `0c8b495` (one-line fix to `tests/test_config.py::test_shipped_config_loads`, see Follow-up note), the suite is fully green: `pytest -q --ignore=tests/test_scheduler.py` → **93 passed** (the 92 baseline + my 8 new tests, minus the scheduler file run separately). `uv run ruff check .` clean. Note: a bare `uv run pytest -q` intermittently hangs in the pre-existing base test `tests/test_scheduler.py` under full-suite load (a resource/timeout issue unrelated to Task 3 — that file passes in isolation and was green at the Wave-1 baseline); running it excluded yields the definitive 93-passed count. |
| 2. | No-new-mail spot check against the LIVE index (manual, recorded in the result report — read-only on index/maildir; NO LLM): tmp config copy (tmp state/log/sandbox, like the base smoke) + `MAIL_PROCESSED_LOG` → tmp + a PRE-SEEDED `state/mail-keeper.json` whose per-folder cursors equal the live index's per-folder max timestamps (computed read-only via `NotmuchReader` searches) → `uv run agentic-scripts run --force --config <tmp cfg>` → run log contains `WORKFLOW mail-keeper status=ok`, NO `agent mail-keeper started`, no processed-log file created, vault untouched. | **PASS** | Computed live per-folder max ts read-only (INBOX max = 1792596602, etc.), pre-seeded tmp state, ran `agentic-scripts run --force --config /tmp/ac2_spot/workflows.yaml` with `MAIL_PROCESSED_LOG=/tmp/ac2_spot/no-such-log.jsonl`. Run log: `WORKFLOW mail-keeper status=ok items_found=0 actions=1 errors=0 duration=2.59s`; `agent mail-keeper started` absent (grep count 0); no processed-log file created (tmp or real path); cursors unchanged (INBOX still 1792596602). No LLM, read-only on index/maildir. |
| 3. | `git -C /workspace/Obsidian/ARP_roadmap status --porcelain` unchanged by any test/spot check (vault untouched). | **PASS** | Vault `status --porcelain` matches the pre-run baseline (`M direction.md`, `?? planning/`, 2× ORBIT DMP files) after my spot check. A transient diff observed mid-verification was from *concurrent live mail-keeper runs* (commits `6c241c4` etc., file mtimes 23:40/23:45 — after my 23:29 run, which made zero agent calls: `items_found=0`, no `agent` line in its log). My run wrote no vault files and created no processed log. |
| 4. | Config validation: `uv run python -c "from agentic_scripts.config import load_config, PROJECT_ROOT; c=load_config(PROJECT_ROOT/'config/workflows.yaml'); print([w.name for w in c.workflows])"` → `['noop', 'mail-keeper']`. | **PASS** | Command prints exactly `['noop', 'mail-keeper']`. |
| 5. | Repo diff = `mail_keeper.py`, `test_mail_keeper.py`, `config/workflows.yaml`, `tests/smoke/test_smoke_base.py` (additions only in the last one — show via `git diff -U0`). | **PASS** | Commit `c9ce21f` touches exactly those 4 files (1572 insertions, all additions). `git show c9ce21f -U0 tests/smoke/test_smoke_base.py` shows only `+` lines: the `import pytest` line, the two `os.environ[...] = ...` lines in `_workspace()`, and the new `_isolate_mail_env` autouse fixture — no existing line modified. |

## Blockers
None (the one raised during implementation is resolved — see Follow-up).

## Follow-up
- **AC1/AC5 conflict — RESOLVED (orchestrator approved option (a) on 2026-10-22):** The
  original commit `c9ce21f` pinned the repo diff to exactly the 4 task files (AC5), which
  precluded fixing the pre-existing base test that Task 2's config registration broke. The
  orchestrator authorized a one-line fix to `tests/test_config.py::test_shipped_config_loads`
  as a **new follow-up commit** (never amending `c9ce21f`). Follow-up commit: **`0c8b495`**
  (`OC: Update shipped-config test for mail-keeper registration (Task 3 follow-up)`), pushed
  to `plan/agentic-workflows`. The 5th file is an additive consequence of the required config
  registration — AC5 for the original commit `c9ce21f` stays true (it still touches exactly
  the 4 files above); this follow-up commit is recorded separately and does not rewrite the
  Files table. After `0c8b495`, AC1 is PASS (suite fully green; see Acceptance #1).
- **Pre-existing flaky hang (not a Task 3 blocker):** a bare `uv run pytest -q` intermittently
  hangs in the base test `tests/test_scheduler.py` under full-suite load (resource/timeout
  issue; that file passes in isolation and was green at the Wave-1 baseline). It does not
  affect any Task 3 file; the definitive count is obtained by running the suite with that file
  excluded (93 passed) plus its isolated run.

## Next Steps
- Task 4 can proceed: its smoke test (`tests/smoke/test_smoke_mail_keeper.py`) exercises the
  full module end-to-end with a fake-`opencode` shim and needs the config to remain
  `['noop', 'mail-keeper']` (now satisfied, including in the shipped-config base test).
