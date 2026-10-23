# lightweight-dev Output — Task: Mail-keeper smoke test, README, env

**Task:** #4    **Session:** workflows-mail-keeper    **Date:** 2026-10-23

## Summary

Implemented all three sub-tasks of the spec. **(Task 1)** `tests/smoke/test_smoke_mail_keeper.py` —
a fixture-world builder (`_build_world`) that constructs a throwaway maildir (6 messages: m6 old /
m1 plain / m2 multipart / m3 HTML-only / m4 PII / m5 own), a `notmuch new` index, a fixture vault
git repo mirroring the real vault's IA (todos/projects/people/mail-drafts + `.gitignore` with
`mail` + baseline commit on `feature/test` + bare remote `origin`), and two deterministic fake
`opencode` shims (good + failure). The four smoke tests drive a real forced `run()` of the
SHIPPED-style config through the full pipeline: backfill batch one (m6,m1,m2,m3 oldest-first, PII/own
excluded, provenance edits + todo + draft, `OC:` commit pushed to the bare remote, processed-log v1
6-field schema, backup byte-identity), no-new-mail re-run (no agent call, HEAD unchanged, <10 s),
new-mail-after-backfill (m7 exactly once, zero duplicates), and agent-failure → retry (same 4 ids
re-presented, full success). **(Task 2)** additive `## Mail-keeper workflow` README section.
**(Task 3)** `.env` (local, 0600, gitignored — comment-only, see Follow-up B1) + `.env.example`
(committed — commented documentation). Committed exactly the 3 spec files on `plan/agentic-workflows`
(commit `5e4ea15`, pushed); `.env` never committed. A second orchestrator-authorized follow-up commit
(`5034d59`) then resolved both AC1 blockers (B1: dropped the redundant active `.env` values locally;
B2: added `MAIL_INDEX_DB` isolation to two scheduler tests), bringing `uv run pytest -q` (no ignores)
to **104 passed, fully green**.

## Files
| File | Action | Why |
|---|---|---|
| `tests/smoke/test_smoke_mail_keeper.py` | create | The 4 backfill smoke tests + fixture world builder + good/failure fake-`opencode` shims (hermetic; no live paths, Python `os.walk` only). |
| `README.md` | modify (additive) | `## Mail-keeper workflow` section: what/why, env-var table, how a run works (incl. the history backfill), operator commands, outputs, guardrails, agent/skill + plan pointers. 0 lines removed, 71 added. |
| `.env.example` | modify (append) | The four `MAIL_*` vars as commented documentation (`# Mail-keeper workflow …`). |
| `.env` | modify (local, NOT committed) | Comment-only block pointing at `.env.example` (0600, gitignored). All four values equal the code defaults, so nothing is set here — active lines would be pure redundancy that breaks `test_index_unset_env_no_flag` via the CLI's `load_dotenv` (see Follow-up B1). |
| `tests/test_scheduler.py` | modify (additive, follow-up commit `5034d59`) | Per-test `MAIL_INDEX_DB` isolation for `test_forced_open_run` + `test_two_step_gate` so the enabled `mail-keeper` workflow lands `status=skipped` instead of starting a live backfill (see Follow-up B2). The other 5 scheduler tests untouched. |

## Build / Tests
- `uv run pytest -q` (FULL suite, NO ignores): **PASS — 104 passed in ~19 s, fully green.** This is the
  definitive count after the follow-up commit `5034d59` resolved both AC1 blockers (B1 + B2). It includes
  the base suite (base smoke with `mail-keeper` enabled + Task 3b env isolation), all Task 1/3 tests, the
  new smoke (4 tests), and all 7 scheduler tests.
- `uv run pytest tests/smoke/test_smoke_mail_keeper.py -q`: **PASS** — 4 passed in ~3.2 s (throwaway
  maildir + index + vault + bare remote + shims; no real `opencode`, no live LLM, no writes to the
  production vault/maildir/index/processed-log).
- `uv run pytest tests/test_mail_search.py -q`: **PASS** — 19 passed (incl. `test_index_unset_env_no_flag`)
  after B1 removed the redundant active `.env` values.
- `uv run pytest tests/test_scheduler.py -q`: **PASS** — all 7 pass in isolation (the two previously-hanging
  tests now pass in ~0.2 s) after B2 added `MAIL_INDEX_DB` isolation.
- `uv run ruff check .`: **PASS** — clean (all files).
- `uv run ruff format --check .`: **PASS** — 58 files already formatted.

*(Pre-follow-up baseline, for the record: with the original spec-mandated `.env` and no scheduler isolation,
the suite was 96 passed / 1 failed (`test_index_unset_env_no_flag`) when `test_scheduler.py` was excluded, and
that file had 2 hanging tests. Both resolved by `5034d59`.)*

## Acceptance Verification
| # | Criterion (verbatim) | Result | Notes |
|---|---|---|---|
| 1. | `uv run pytest -q` fully green — base suite (incl. base smoke with `mail-keeper` enabled and the Task 3b env isolation), Task 1/3 tests, and the new smoke (4 tests). | **PASS** | `uv run pytest -q` (NO ignores) → **104 passed, fully green** after orchestrator-authorized follow-up commit `5034d59` resolved both blockers: **B1** removed the redundant active `.env` values (which equal the code defaults and were breaking `test_index_unset_env_no_flag` via the CLI's `load_dotenv(override=False)`), and **B2** added per-test `MAIL_INDEX_DB` isolation to `test_forced_open_run` + `test_two_step_gate` (so the enabled `mail-keeper` workflow lands `status=skipped` instead of starting a live backfill). See Follow-up for rationale. |
| 2. | `uv run ruff check .` + `uv run ruff format --check .` clean. | **PASS** | Both clean (58 files after the follow-up commit). |
| 3. | Every assertion in Task 1's test 1 holds verbatim (backfill batch = 4 oldest fixture messages in the brief in order; processed-log 6-field schema with 4 lines; PII/own exclusion from the brief; provenance edits; todo; draft; `OC:` commit pushed to the bare remote; backup byte-identity). | **PASS** | `test_mail_keeper_backfill_batch_one` passes verbatim: brief ids == `[m6,m1,m2,m3]` oldest-first; m4 (PII) + m5 (own) absent from the brief; processed log exactly 4 lines, each with the 6 v1 keys `{timestamp,email_file,subject,from,target_section,processed_to}`, classes `noise/action/noise/noise`; meetings line + todo line + draft all carry `m1@fixture.test`; vault HEAD subject starts `OC:` and is present in the bare remote's `feature/test` history; `git status --porcelain` empty (drafts gitignored); independent before/after `os.walk` snapshot of the maildir identical. |
| 4. | No-new-mail run 2 shows zero new lines/commits/drafts; new-mail run 3 processes `m7` exactly once; failure path (test 4) shows no log/state progress on failure and full retry success with the same 4 ids re-presented. | **PASS** | Run 2: `status=ok`, no agent events logged, processed-log count unchanged (4), vault HEAD unchanged, duration <10 s. Run 3: manifest exactly `[m7]`, processed log +1 (5 total), zero duplicate ids. Test 4: failure run → `status=error` + `overall: error`, processed log ABSENT, vault HEAD == baseline, no advanced cursors; retry re-presents the same 4 ids and succeeds (4 log lines, `OC:` commit present). |
| 5. | `git status` after the commit: only `tests/smoke/test_smoke_mail_keeper.py`, `README.md`, `.env.example` in the new commit; `.env` untracked (check-ignore passes); no other repo file changed. | **PASS** | Commit `5e4ea15` touches exactly those 3 files (`git show --name-only`). `git check-ignore .env` → exit 0 (ignored). `git status` shows only the 3 pre-existing untracked planning result files; `.env` is not listed (untracked + ignored). |
| 6. | No live LLM inference, no real vault/maildir/index touched by any test (assertion: the test module never references `/workspace/docker/mbsync` or `/workspace/Obsidian/ARP_roadmap` — grep the new test file to confirm). | **PASS** | `grep -c "/workspace/docker/mbsync" tests/smoke/test_smoke_mail_keeper.py` → 0; `grep -c "/workspace/Obsidian/ARP_roadmap"` → 0. (The module docstring was rewritten to say "the production Obsidian vault, the mbsync backup/index tree" without the literal paths so the grep is clean.) No live LLM: the agent is a deterministic Python shim; all maildir/index/vault are under `tmp_path`. |

## Blockers
None (both resolved by orchestrator-authorized follow-up commit `5034d59`, 2026-10-23).

## Follow-up
Orchestrator authorized both AC1 blockers as **one** new follow-up commit (`5034d59`, pushed; never
amended `5e4ea15`). The commit touches only `tests/test_scheduler.py`; the `.env` edit is local, untracked,
and ignored (not in the commit).

**B1 — `.env` conflict (resolution: drop the redundant active values).** The spec's own note says the four
`MAIL_*` values "equal the code defaults." Because `mail_search.main` loads `.env` with
`override=False`, an active value in `.env` is loaded into `os.environ` even when a test fixture does
`monkeypatch.delenv("MAIL_INDEX_DB")` — which broke the pre-existing base test
`tests/test_mail_search.py::test_index_unset_env_no_flag` (it asserts an *unset* `MAIL_INDEX_DB` + no
`--index` yields exit 1). Since the values equal the code defaults, the active lines were pure redundancy:
removing them from the local `.env` (leaving a short comment block pointing at `.env.example`) makes the CLI
fall back to its code defaults — identical behavior in production — while restoring the test. No change to
`mail_search.py` or `tests/test_mail_search.py`. Verified: `uv run pytest tests/test_mail_search.py -q` →
19 passed (incl. `test_index_unset_env_no_flag`); `git check-ignore .env` still passes.

**B2 — scheduler isolation (additive-only, mirrors Task 3b).** `tests/test_scheduler.py`'s
`test_forced_open_run` and `test_two_step_gate` copy the SHIPPED config (`config/workflows.yaml`, now with
`mail-keeper: enabled`) via `_write_config` but do NOT set `MAIL_INDEX_DB` (unlike the base smoke's Task 3b
isolation). A forced/gate-open run therefore started a LIVE backfill against the real index and spawned a real
`opencode`, hanging both tests. This is a test-isolation defect introduced by Task 2/3's config registration
(the base smoke got env isolation, `test_scheduler.py` did not) — the same class of follow-up as Task 3's
`test_config.py` fix. Applied the minimal additive change: added a `monkeypatch` fixture parameter + one
`monkeypatch.setenv("MAIL_INDEX_DB", str(tmp_path / "no-such-index"))` line to each of the two tests, so the
workflow lands `status=skipped` (index missing) — no canary walk, no agent. No existing assertion needed
adjustment (the new `WORKFLOW mail-keeper status=skipped` log line conflicts with none). The other 5 scheduler
tests are untouched. Verified: both tests now pass in ~0.2 s; full suite green.

**Result:** `uv run pytest -q` (NO ignores) → **104 passed, fully green**; `uv run ruff check .` +
`uv run ruff format --check .` clean. AC1 is now PASS.
