# Task Plan: Mail-keeper smoke test, README, env

**Purpose:** Prove the high-level plan's acceptance end-to-end in a hermetic smoke test (throwaway maildir + notmuch index, fixture vault git repo, deterministic fake `opencode`), and document the workflow for operators.

## Objective

Create `tests/smoke/test_smoke_mail_keeper.py` driving a real forced `run()` of the SHIPPED-style config (paths/env pointed at fixtures) through the full pipeline — canary, backfill start (first run = oldest batch of the fixture history), detection, one agent invocation (fake shim performing the agent's contract: provenance-tagged vault edit, todo line, draft, `OC:` commit + push), processed-log append, cursor advance, backup byte-identity, no-new-mail re-run, new-mail-after-backfill, and the agent-failure → retry path. Plus the README section, `.env.example`/`.env` env vars, and a fully green suite. Success = the high-level plan acceptance (triage record + provenance edits + todo + draft + pushed `OC:` commit; zero duplicates on re-run; PII/own never in the brief; backup byte-identical; no send) holds inside `uv run pytest`.

## Context

- **Repo:** `/workspace/Python/agentic_scripts`, branch `plan/agentic-workflows`. Conventions: Google-style docstrings, `uv run ruff check .` + `uv run ruff format --check .` clean (line length 100), hermetic tests only, commit `OC:` prefix, push, ONLY this task's files.
- **What exists (do NOT modify):** `workflows/mail_keeper.py` (Task 3: `create(config)`, run = canary → state (absent cursors = epoch 0 → first runs backfill the whole index oldest-first) → detection (per-folder thread search, ts > cursor, oldest-first walk, owner/PII/processed-log exclusion, `deferred` cap list) → manifest ≤10 (`MAX_BATCH`) → pre-walk → one `ctx.runner.run(agent="mail-keeper", brief, work_dir=ctx.admin_repo, title=...)` → on ok: processed-log append (v1 6-field schema at `MAIL_PROCESSED_LOG`, default `/workspace/Obsidian/config/email-processing-log.jsonl`), cursor advance (per-folder max batch ts), post-walk byte-identity check; state doc `state/mail-keeper.json` `{bootstrapped_at, cursors: {folder: {last_date, last_message_id}}, deferred: [...]}` — state saved only on no-new-mail or agent-`ok`), `mail/mail_search.py` + `mail/canary.py` (Task 1), `config/workflows.yaml` (entries `noop`, `mail-keeper` enabled), `agent.py` (`AgentRunner.build_command` → `[binary, "run", "--agent", agent, "--format", "json", "--dir", work_dir] + ["--title", t]? + ["--auto"]? + ["--model", m]? + [brief]` — the shim must tolerate all flags), base smoke style (`tests/smoke/test_smoke_base.py` — in-process `run([...], now=..., load=...)` with a tmp config copy of the shipped YAML; already env-isolated for `MAIL_*` by Task 3b).
- **Scheduler:** `run(argv, now=None, load=None, run_id=None)` — `--force` bypasses the gate; per-run log `logs/run-*.log` contains `WORKFLOW <name> status=<status>` lines; `last-run.txt` has `overall: ok|error`; exit 0 on ok/skipped, 2 on config/usage fault.
- **Fixture vault IA (must mirror the real vault's shape so the shim's writes are realistic):** `todos/active.md` with `# Active Tasks` + `## 📂 Projects` + `## 💰 Funding & Grants` + `## ⏳ Waiting On`; `projects/ORBIT/00_Project_management/01_Meetings.md` (with `## EUG Meetings`); `people/` (empty dir + `.gitkeep`); `mail/drafts/` (empty + `.gitkeep`); `.gitignore` containing `mail`; a baseline commit on branch `feature/test`; a bare remote (`git init --bare`) named `origin` + initial push (so the shim's `git push origin HEAD` works offline).
- **Fixture maildir + index:** account `acct@example.test`; messages in `cur/` (maildir files, any unique names): `m1` (plain text, `From: Coera <coera@orbit.example.test>`, `Subject: EUG schedule`, `Date:` = recent past, message-id `<m1@fixture.test>`), `m2` (multipart plain+html, `From: Nikos <nikos@orbit.example.test>`, `<m2@fixture.test>`), `m3` (HTML-only, `<m3@fixture.test>`, `INBOX/cur/`), `m4` (PII: `INBOX/FU-Admin/PhD_applications/cur/`, `<m4@fixture.test>`), `m5` (own: `From: Yuri Durodie <yuri.durodie@vub.be>`, `Sent Items/cur/`, `<m5@fixture.test>`), plus `m6` an OLD message (`Date:` ~2 months back, `From: Old <old@fixture.test>`, `INBOX/cur/`, `<m6@fixture.test>`) — the oldest batch member, exercising the backfill's oldest-first ordering. Distinct increasing `Date:` values across m6 < m1 ≈ m2 ≈ m3 (m1/m2/m3 may share a day — use distinct timestamps). Index: `notmuch new` with a generated config (`database.path`=tmp idx, `mail_root`=tmp maildir, `synchronize_flags=false`) — same pattern as `tests/test_mail_reader.py`.
- **Fake `opencode` shim (the fake agent):** a standalone executable **Python 3 script** under `tmp_path` (written by the test, `chmod 0755`), no third-party imports. It parses argv: find `--dir` (vault path), `--title`, and the final positional arg (the brief). Deterministic behavior mirroring the REAL agent contract (`skills/mail-keeper/SKILL.md`):
  1. Parse manifest lines from the brief (Task 3's `_render_brief` renders ids WITHOUT angle brackets): `^\d+\. (?P<id>\S+) \| (?P<folder>[^|]+) \| (?P<date>\d{4}-\d{2}-\d{2}) \| (?P<from>[^|]+) \| (?P<subject>.*)$` — tolerant of a wrapped id form.
  2. For each manifest msg-id NOT under the PII folder and not own-mail (the workflow already excludes both — the shim just asserts their ABSENCE): if the msg-id contains `m1` → append to `projects/ORBIT/00_Project_management/01_Meetings.md` under `## EUG Meetings` the line `- <date> EUG session confirmed; deck due Friday *(from: Coera, "EUG schedule", <date>, m1@fixture.test)*`; append to `todos/active.md` under `## 📂 Projects` the line `- [ ] Confirm EUG deck (from Coera — <date>) *(from: Coera, "EUG schedule", <date>, m1@fixture.test)*`; write `mail/drafts/<date>_eug-schedule.md` with `To: Coera <coera@orbit.example.test>` / `Subject: Re: EUG schedule` / a 3-line body / `---` / `*(from: Me, "draft reply to EUG schedule", <date>, m1@fixture.test)*`. For `m6`/`m2`/`m3` → no writes (classified noise).
  3. Git: `git -C <vault> add <only the touched paths>`; `git -C <vault> commit -m "OC: mail triage (N mail(s) triaged, 2 vault edit(s), 1 draft(s))"` (skip commit if nothing staged); `git -C <vault> push origin HEAD`.
  4. Emit NDJSON on stdout, one JSON object per line: `{"type":"step_start","timestamp":...}` → `{"type":"tool_use","timestamp":...,"tool":"bash"}` → final `{"type":"text","timestamp":...,"part":{"text":"<REPORT>"}}` where `<REPORT>` is a result report containing the EXACT Triage table (Task 3 parses it) — one row per manifest id received (the backfill batch of the fixture world is `m6, m1, m2, m3` oldest-first):
     ```
     ## Triage
     | msg-id | folder | from | class | action taken |
     |---|---|---|---|---|
     | m6@fixture.test | INBOX | old@fixture.test | noise | logged only |
     | m1@fixture.test | INBOX | coera@orbit.example.test | action | meetings+todo+draft |
     | m2@fixture.test | INBOX | nikos@orbit.example.test | noise | logged only |
     | m3@fixture.test | INBOX | nikos@orbit.example.test | noise | logged only |
     ```
     (rows only for the manifest ids actually received — the failure-retry scenario re-receives the same ids). Exit 0.
  5. **Failure mode:** if the brief contains the sentinel `FAIL_AGENT` (the test injects it by monkeypatching nothing — instead the test uses a SECOND shim script `shim_fail.py` that immediately emits an `{"type":"error",...}` line and exits 1), the failure shim is used via a config copy with `agent.binary` pointed at it.
- **Env for the smoke:** `MAIL_INDEX_DB`=<tmp idx>, `MAIL_MAIL_ROOT`=<tmp maildir>, `MAIL_OWNER_ADDRESS`=`yuri.durodie@vub.be`, `MAIL_PROCESSED_LOG`=<tmp>/processing.jsonl (all via `monkeypatch.setenv` — the workflow reads env at run time; the in-process `run()` also loads the project `.env` with `override=False`, so test env wins).
- **Config for the smoke:** tmp copy of the SHIPPED `config/workflows.yaml` (like base smoke) with `paths` → tmp dirs, `admin_repo` → fixture vault, `agent.binary` → shim path, `agent.model: null`, `agent.timeout_minutes: 5`. The `noop` entry runs first (harmless); `mail-keeper` second.
- **README (base-owned file, extend — this is the plan's ops wave, single agent, no parallel conflict):** base `README.md` has config reference / env vars / how-to-add-a-workflow sections; ADD a `## Mail-keeper workflow` section (do not rewrite existing content).

## Tasks

### Task 1: Smoke test module
- **Files:** `tests/smoke/test_smoke_mail_keeper.py` (create)
- **Do:** One fixture-builder helper (`_build_world(tmp_path, monkeypatch) -> dict` returning paths: maildir, index, vault, bare_remote, shim, shim_fail, config_path, processed_log, plus the `notmuch new` call) + these tests (each builds a fresh world; in-process `run([...], now=datetime(2026,10,21,22,30), load=(0.1,0.1,0.1))` — inside the quiet window AND forced where noted):
  1. `test_mail_keeper_backfill_batch_one` — fresh world (empty state = epoch-0 cursors → first run IS the backfill start) + `run(["run","--force","--config",cfg])`:
     - exit 0; run log contains `WORKFLOW mail-keeper status=ok` and `agent mail-keeper started` (the shim ran);
     - the shim's captured brief (`<tmp>/brief.txt`): contains `m6@fixture.test`, `m1@fixture.test`, `m2@fixture.test`, `m3@fixture.test` in that (oldest-first) order; does NOT contain `m4@fixture.test` (PII) or `m5@fixture.test` (own);
     - processed log: exactly 4 lines — `m6@fixture.test` (`target_section` `"noise"`), `m1@fixture.test` (`"action"`), `m2@fixture.test` (`"noise"`), `m3@fixture.test` (`"noise"`); every line has exactly the 6 v1 keys;
     - vault: `01_Meetings.md` contains the provenance line with `m1@fixture.test`; `todos/active.md` contains the todo line with `m1@fixture.test`; `mail/drafts/2026-…_eug-schedule.md` exists with `To:`, `Subject: Re:`, and the provenance footer;
     - vault git: `git -C <vault> log -1 --format=%s` starts with `OC:`; `git -C <bare> log --oneline origin/feature/test` shows that commit (pushed); `git -C <vault> status --porcelain` empty (drafts gitignored);
     - backup integrity: the maildir's file set + sizes + mtimes identical to the pre-run `os.walk` snapshot (the test computes its own before/after — independent of the workflow's internal check).
  2. `test_mail_keeper_no_new_mail_after_backfill` — continue the same world: run 2 → run log contains `WORKFLOW mail-keeper status=ok` and NO `agent mail-keeper started` line; processed log line count unchanged (4); vault HEAD unchanged; run 2 duration < 10 s (smoke-speed guard).
  3. `test_mail_keeper_new_mail_after_backfill` — continue the same world: add `m7` (newer `Date:`, `INBOX/cur/`, `<m7@fixture.test>`) + `notmuch new` on the fixture index → run 3 → manifest exactly `[m7]` (brief line count 1), processed log +1 line (`m7@fixture.test`), zero duplicate lines vs runs 1–2.
  4. `test_mail_keeper_agent_failure_retry` — FRESH world with `agent.binary` = `shim_fail` (empty state → backfill start presents 4 candidates): run 1 → `WORKFLOW mail-keeper status=error`, `overall: error` (assert against `scheduler.py`'s ACTUAL exit-code behavior and correct this spec line in the result report if needed), processed log ABSENT, vault HEAD unchanged (baseline commit only), no state file with advanced cursors; then re-run with a config copy pointing `agent.binary` back at the good shim → the SAME 4 ids are re-presented (brief contains all four) and the run succeeds (4 log lines, `OC:` commit present).
- **Notes:** The shim MUST be robust to the exact brief format of Task 3 (read `mail_keeper._render_brief` in the repo before writing the shim parser; if the format differs, adapt the shim to the ACTUAL format and note it in the result report — the brief format is the contract). The shim writes `brief.txt` as its first act (so failure-mode briefs are capturable). Git in fixtures: set `GIT_AUTHOR_NAME/EMAIL` + `GIT_COMMITTER_NAME/EMAIL` env for the subprocesses (shim and test) to a fixture identity.

### Task 2: README section
- **Files:** `README.md` (modify — additive section only)
- **Do:** Add `## Mail-keeper workflow` (after the base content, before any appendix): one-paragraph what-it-does (gate-open run → triage new mail → provenance-tagged vault fills → local drafts, never sent → `OC:` commit + push to the vault's current branch); the env-var table (`MAIL_INDEX_DB`, `MAIL_MAIL_ROOT`, `MAIL_OWNER_ADDRESS`, `MAIL_PROCESSED_LOG` — values, defaults, meaning); how the run works (canary/freshness with the 100-message tolerance + report-and-defer, **first runs start the history backfill** — epoch-0 cursors, whole index triaged oldest-first in batches of `MAX_BATCH = 10` per run until caught up, ~1,000 runs expected, operator can chain `--force` runs to accelerate, per-folder cursors + processed log = idempotency, one batched `mail-keeper` agent invocation per run, agent dedup = safe re-delivery); operator commands (`uv run agentic-scripts run --force --only mail-keeper` for a manual run; note the quiet-window gate for scheduled runs); where outputs live (vault on its current branch, `mail/drafts/` gitignored, processed log path); guardrails (PII folder, backup read-only + byte-identity check, no send tooling); pointer to the agent/skill in the global OpenCode config and the high-level plan file.
- **Notes:** Match the README's existing heading levels/style; no emojis.

### Task 3: Env vars (committed example + local `.env`)
- **Files:** `.env.example` (modify — append, committed), `.env` (modify — append, local 0600, untracked — NEVER commit it)
- **Do:** Append to BOTH (`.env` gets real values; `.env.example` gets the same lines as documentation with a comment header `# Mail-keeper workflow (defaults shown; uncomment to override)`):
  ```
  MAIL_INDEX_DB=/workspace/docker/mbsync/notmuch
  MAIL_MAIL_ROOT=/workspace/docker/mbsync/backup
  MAIL_OWNER_ADDRESS=yuri.durodie@vub.be
  MAIL_PROCESSED_LOG=/workspace/Obsidian/config/email-processing-log.jsonl
  ```
  (`.env` lines active; `.env.example` lines prefixed `#`. Verify `git check-ignore .env` passes before committing anything; `git status` must NOT show `.env` as added.)
- **Notes:** Values equal the code defaults (single-user machine) — the entries document the surface; the `mail-search` CLI (agent-facing) reads `MAIL_INDEX_DB` from this `.env` (it loads the project `.env` itself).

## Acceptance

1. `uv run pytest -q` fully green — base suite (incl. base smoke with `mail-keeper` enabled and the Task 3b env isolation), Task 1/3 tests, and the new smoke (4 tests).
2. `uv run ruff check .` + `uv run ruff format --check .` clean.
3. Every assertion in Task 1's test 1 holds verbatim (backfill batch = 4 oldest fixture messages in the brief in order; processed-log 6-field schema with 4 lines; PII/own exclusion from the brief; provenance edits; todo; draft; `OC:` commit pushed to the bare remote; backup byte-identity).
4. No-new-mail run 2 shows zero new lines/commits/drafts; new-mail run 3 processes `m7` exactly once; failure path (test 4) shows no log/state progress on failure and full retry success with the same 4 ids re-presented.
5. `git status` after the commit: only `tests/smoke/test_smoke_mail_keeper.py`, `README.md`, `.env.example` in the new commit; `.env` untracked (check-ignore passes); no other repo file changed.
6. No live LLM inference, no real vault/maildir/index touched by any test (assertion: the test module never references `/workspace/docker/mbsync` or `/workspace/Obsidian/ARP_roadmap` — grep the new test file to confirm).

## Out of Scope

- Live acceptance with the REAL agent (manual protocol, global work plan Note 8 — user approves each run after Task 4); the mbsync WIP; agent/skill/`opencode.jsonc` changes; `find`-based verification (forbidden for this maildir); anything in `/workspace/Research` or `/workspace/Obsidian`; starting the live backfill (production runs only).

## Notes

- **[Assumption]** The scheduler exits 0 even when a workflow reports `status="error"` (base CLI docstring: "0 = ran/skipped/gate-closed, 2 = config/usage fault") — test 4 asserts against the ACTUAL behavior and corrects this assumption in the result report if needed.
- **[Assumption]** `notmuch new` on the fixture index builds cleanly over the 6 fixture messages (threading via `References:` is not exercised by the smoke).
- **[Risk]** The shim's git push to the bare remote requires `receive.denyCurrentBranch` to not block (bare repo → no issue) and a fixture identity; if the host git blocks local pushes (unlikely), use `git remote add` with a `file://` URL.
- **[Note]** The smoke's per-run canary disk walk over the FIXTURE maildir (6 messages) is milliseconds; the base smoke's live-index coupling is already isolated by Task 3b, so no latency concern remains in any automated test.
