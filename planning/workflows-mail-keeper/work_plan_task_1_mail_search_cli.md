# Task Plan: mail-search CLI + index-freshness canary

**Purpose:** Ship the `mail-search` CLI (the `mail-keeper` agent's only reading surface, contract fixed verbatim by the existing global skill) plus a reusable index-freshness canary module, both over the base `NotmuchReader`.

## Objective

Build `src/agentic_scripts/mail/mail_search.py` (CLI) and `src/agentic_scripts/mail/canary.py` (freshness checks) as additive modules of the `agentic_scripts` package, fully hermetic-tested against a throwaway notmuch index. Success: the CLI matches the skill's verbatim contract (exit codes, output format, filters), the canary reports disk-vs-index staleness correctly, and a read-only live-index probe confirms the canary works against the production index.

## Context

- **Repo:** `/workspace/Python/agentic_scripts`, branch `plan/agentic-workflows`. Conventions: Google-style docstrings on every public function (Purpose/Args/Returns/Side Effects — match existing code, e.g. `reader.py`), `uv run ruff check .` and `uv run ruff format --check .` clean (line length 100), hermetic tests only (tmp dirs; throwaway notmuch indexes — the base `tests/test_mail_reader.py` already builds one; read it and follow its fixture pattern), commit `OC:` prefix, push, ONLY this task's files.
- **Base API (do NOT modify these files):** `src/agentic_scripts/mail/reader.py` — `NotmuchReader(index_path: Path, mail_root: Path, work_dir: Path, logger=None, notmuch_bin="notmuch")` (writes its own 0600 config into `work_dir`; read-only by construction); methods `count(query="") -> int`, `search(query, limit=25) -> list[dict]` (rows: `thread, subject, authors, timestamp(int epoch), tags, matched, total, message_ids`), `message_ids(query) -> list[str]`, `show(message_id) -> {"primary", "context", "raw"}` (primary = first message object: `id, filename[], timestamp(int epoch), tags, duplicate, body[], headers(dict)`, ...), `body_text(message_id) -> (text|None, raw_path|None)` (plain text, OR raw maildir path for HTML-only, OR `(None, None)`). Query builders: `q_text`, `q_from(value)`, `q_folder(account, path)`, `q_id`, `q_thread(tid)`, `q_date_prefix(year)`, `q_and(*clauses)` (refuses `all:`/`field:`/`after:`/`before:`/`last:` — notmuch 0.38.3 silently reinterprets those as free text). Errors: `NotmuchError` (op/code/stderr-tail).
- **notmuch 0.38.3 quirks (load-bearing):** `search --format=json` returns THREADS (message ids inside `query[0]`/`query[1]` subqueries; the reader exposes only matched ids); `--format=messages` does not exist; search-row `timestamp` is an integer epoch; `text/html` parts carry no body in `show` JSON (raw-file MIME fallback); message-ids contain no spaces. Per-message From/Subject/folder/timestamp therefore come from `show` per id (N calls for N listed messages — acceptable: local index, `--limit` default 25; do NOT add multi-id `show` support and do NOT modify `reader.py`).
- **Machine facts:** notmuch 0.38.3 at `/usr/bin/notmuch`; live index `/workspace/docker/mbsync/notmuch`, mail root `/workspace/docker/mbsync/backup` (account = single top-level dir `yuri.durodie@vub.be`; folders `INBOX`, `INBOX/ORBIT`, `Sent Items`, ...). **GNU `find` does not descend into this maildir** — use Python `os.walk` everywhere. The venv bin (`/workspace/Python/agentic_scripts/.venv/bin`) is NOT on PATH (`opencode` lives in `/root/.opencode/bin`); the agent invokes `mail-search` bare via bash, so a `/usr/local/bin/mail-search` shim is required (see Task 2 below).
- **Env-var surface (shared with later tasks — do not rename):** `MAIL_INDEX_DB` (index db path), `MAIL_MAIL_ROOT` (maildir root, default `/workspace/docker/mbsync/backup`), `MAIL_OWNER_ADDRESS` (default `yuri.durodie@vub.be`). The CLI loads the project `.env` first: `from dotenv import load_dotenv; load_dotenv(PROJECT_ROOT/".env", override=False)` where `PROJECT_ROOT = Path(__file__).resolve().parents[3]` (this file is `src/agentic_scripts/mail/mail_search.py`).

## Tasks

### Task 1: `mail-search` CLI module
- **Files:** `src/agentic_scripts/mail/mail_search.py` (create)
- **Do:** Implement `main(argv: list[str] | None = None) -> int` (and a `console script`-safe module) implementing EXACTLY this contract (verbatim from the global `skills/mail-keeper/SKILL.md` — the agent depends on it byte-for-byte in behavior):

  ```
  Usage:
    mail-search <query> [options]           list mode
    mail-search --show <message-id>         detail mode

  Options:
    <query>            full-text query (positional; list mode)
    --from <pattern>   only messages whose From name/address contains <pattern> (case-insensitive)
    --folder <path>    only messages in folder <path> (e.g. INBOX, INBOX/ORBIT, "Sent Items")
    --since <date>     only messages with date >= YYYY-MM-DD
    --until <date>     only messages with date <= YYYY-MM-DD
    --thread           expand matches to the full thread (References/In-Reply-To closure), date order
    --own              only messages sent from the configured user address (style sampling)
    --limit <n>        max messages returned (default 25)
    --index <path>     index DB path (default $MAIL_INDEX_DB; exit 1 if unset/unreadable)

  List-mode stdout (one block per message; blank line between blocks):
    === <message-id> | <folder> | <YYYY-MM-DD HH:MM> | <From: name <addr>> | <Subject>
    <MIME-extracted plain-text body, truncated at 2000 chars>
  Detail-mode stdout: full headers + full plain-text body.
  Exit codes: 0 = ok (even zero matches), 1 = index missing/unreadable, 2 = usage error.
  ```

  Implementation notes:
  - argparse; `--help` exits 0 (before index resolution). List mode REQUIRES a positional query or `--folder` (neither → exit 2); `--show` is exclusive with the positional query (both → exit 2); `--show` without an id → exit 2; invalid `--since`/`--until` (not `YYYY-MM-DD`) → exit 2.
  - Index path: `--index` else `os.environ.get("MAIL_INDEX_DB")`; absent, or path not an existing directory, or the first `notmuch` call fails with a missing-database error → print a reason to stderr, exit 1.
  - `mail_root`: `MAIL_MAIL_ROOT` env else `/workspace/docker/mbsync/backup`; `account` = the single top-level directory under `mail_root` (more or zero → exit 2 with a message). `owner`: `MAIL_OWNER_ADDRESS` env else `yuri.durodie@vub.be`.
  - Reader: `work_dir` = `tempfile.mkdtemp(prefix="mail-search-")` (leave it; /tmp is ephemeral). `NOTMUCH_CONFIG` is handled by the reader itself.
  - **List mode algorithm:** (1) clauses = `[q_folder(account, folder)]` if `--folder` + `[q_text(query)]` if positional → `q_and(*clauses)` (or the single clause). (2) `rows = reader.search(q, limit=10**9)`; message ids = flattened, deduped `message_ids` in row order. (3) If `--thread`: for each distinct row `thread` id, `reader.search(q_thread(tid), limit=10**9)` and union the ids (the reader exposes only matched ids; re-searching the thread id recovers the full closure). (4) For each id: `reader.show(id)` (on `NotmuchError` warn to stderr, skip the message, continue — exit stays 0); take `primary`. (5) Post-filters on the primary: `--from` → `pattern.lower() in str(headers.get("From","")).lower()`; `--own` → `owner.lower() in str(headers.get("From","")).lower()`; `--since`/`--until` → local calendar date of `primary["timestamp"]` (int epoch) within range. (6) Order: date ascending by `timestamp` (stable). (7) Apply `--limit` (default 25) to the filtered list. (8) Per message: folder = `filename[0]` relative to `mail_root/account`, with the trailing maildir state segment (`cur`/`new`) removed (e.g. `INBOX/ORBIT`); body = `reader.body_text(id)` → `(text, None)` → `text[:2000]`; `(None, raw_path)` → MIME fallback: read the raw file, `email.message_from_bytes`, walk parts, concatenate `text/plain` contents (decode errors=replace); if only `text/html` present, naive tag-stripping (documented best-effort) — `""` if unreadable; `(None, None)` → `""`. (9) Emit blocks exactly per the contract (header line + body line(s), blank line BETWEEN blocks, no trailing blank line) to stdout; exit 0.
- **Notes:** No ANSI, no logging to stdout (stderr only). Keep the module importable without side effects. The CLI never writes anywhere except the temp reader config.

### Task 2: `pyproject.toml` console script + PATH shim (host step)
- **Files:** `pyproject.toml` (modify — ADD ONE line under `[project.scripts]`; the only base-file edit in this plan, additive, no parallel-safety issue — this wave is single-agent); `/usr/local/bin/mail-search` (create, host-level, not in the repo)
- **Do:** Add `mail-search = "agentic_scripts.mail.mail_search:main"` to `[project.scripts]`. Run `uv sync` (regenerates venv entry points; idempotent). Create the shim (root, on this host): `#!/bin/sh` + `exec /workspace/Python/agentic_scripts/.venv/bin/python -m agentic_scripts.mail.mail_search "$@"` — wait, the module has no `__main__` guard requirement: add `if __name__ == "__main__": raise SystemExit(main())` to `mail_search.py` so `python -m` works, and make the shim `exec /workspace/Python/agentic_scripts/.venv/bin/mail-search "$@"` (the venv console script). `chmod 0755`. Verify from a neutral cwd: `cd /tmp && mail-search --help` → exit 0; `cd /tmp && mail-search` (no args) → exit 2.
- **Notes:** `mail_search.main` must be import-safe for the entry point (hatchling only needs the attribute at install).

### Task 3: Index-freshness canary module
- **Files:** `src/agentic_scripts/mail/canary.py` (create)
- **Do:**
  - `STALE_TOLERANCE = 100` (module constant; observed live delta 2026-10-19 = 36).
  - `disk_message_counts(mail_root: Path, account: str) -> dict[str, int]` — Python `os.walk` (NEVER `find`) under `mail_root/account`; a directory that contains a `new/` or `cur/` child is a message folder; count regular files directly inside its `new/` and `cur/` (skip the `tmp/` state dir and anything deeper); return `{"total": N, "<folder>": n, ...}` with folder keys relative to the account (e.g. `"INBOX"`, `"INBOX/ORBIT"`, `"Sent Items"`, `"INBOX/FU-Admin/PhD_applications"`).
  - `index_folder_counts(reader: NotmuchReader, account: str, folders: list[str]) -> dict[str, int]` — `reader.count(q_folder(account, f))` per folder + `reader.count("")` as `"total"`.
  - `run_canaries(reader, mail_root, account, *, tolerance=STALE_TOLERANCE, folders=None) -> dict` — `folders` default = folder keys discovered by `disk_message_counts`. Returns `{"total_disk", "total_index", "per_folder": {f: {"disk", "index", "delta"}}, "stale": bool, "reasons": [str], "spot_check": {"ok": bool, "message_id": str|None, "note": str}}`. Stale when: `total_disk - total_index > tolerance`; OR any `delta < 0` (index ahead of disk — broken); OR the `"Sent Items"` delta (when present) `!= 0` (acceptance: Sent Items must equal disk exactly). Reasons are human-readable strings. Spot-check: `reader.search(q_folder(account, "Sent Items"), limit=1)` → first row's first message id → `reader.show` + `reader.body_text` → `ok` = no exception and (`text` or raw path) non-None.
  - Pure/deterministic; no CLI (the workflow module in Task 3 consumes it).
- **Notes:** The disk walk over the 4.5 GB tree is ~1–3 s — acceptable for a per-run check; document the cost in the docstring.

### Task 4: Hermetic tests
- **Files:** `tests/test_mail_search.py` (create), `tests/test_mail_canary.py` (create)
- **Do:** Build a throwaway maildir + index in `tmp_path` (follow `tests/test_mail_reader.py`'s fixture pattern): account dir `acct@example.test` with `INBOX/cur/` (≥4 messages: m1 plain-text `From: Coera <coera@orbit.example.test>` `Subject: EUG schedule` with a recent `Date:`; m2 multipart plain+html; m3 HTML-only with a long body > 2000 chars; m4 replying to m1 with `References: <m1-id>` and `In-Reply-To: <m1-id>`; m5 `From: Yuri Durodie <yuri.durodie@vub.be>` in `Sent Items/cur/`) and run `notmuch new` with a generated config (same template shape as the reader's: `database.path`/`mail_root`/`synchronize_flags=false`, injected via `NOTMUCH_CONFIG`). Call the CLI in-process: `mail_search.main([...])` with `capsys` + `monkeypatch` env (`MAIL_MAIL_ROOT`, `MAIL_OWNER_ADDRESS=yuri.durodie@vub.be`; pass `--index` explicitly). Cover at minimum:
  1. Usage: no query and no `--folder` → exit 2; `--show` + positional → 2; `--show` alone → 2; bad `--since` → 2; `--help` → 0.
  2. Index: unset `MAIL_INDEX_DB` + no `--index` → 1 with stderr reason; `--index /nonexistent` → 1.
  3. List mode on the throwaway index: exact block format `=== <id> | INBOX | <YYYY-MM-DD HH:MM> | Coera <coera@orbit.example.test> | EUG schedule`, body present, blank line between blocks, zero trailing blank line; zero-match query → exit 0, empty stdout.
  4. Filters: `--from coera` (case-insensitive, partial) matches m1 only; `--folder INBOX` vs `--folder "Sent Items"` (space) vs `--folder INBOX/ORBIT` (missing → zero matches, exit 0); `--since`/`--until` boundary behavior; `--own` returns only m5; `--limit 2` returns 2 messages.
  5. `--thread` on a query matching m1 returns BOTH m1 and m4 in date order.
  6. HTML-only m3: body non-empty via the raw-file MIME fallback (tag-stripped) — assert the fallback path is taken (raw path from `body_text` is non-None in a direct unit call).
  7. Detail mode `--show <m1-id>`: stdout contains `From:`, `Subject:`, `Date:`, `Message-ID:` header lines + the full (untruncated) body.
  8. Canary: disk/index counts agree on the throwaway tree (`stale` False, reasons empty); append one new message file to `INBOX/cur/` WITHOUT `notmuch new` → `stale` True, `reasons` mention the total delta, `per_folder["INBOX"]["delta"] == 1`; spot-check `ok` True with a real message id.
- **Notes:** No test may touch the live index/maildir or `/workspace/docker/mbsync`. Tests must pass with `uv run pytest tests/test_mail_search.py tests/test_mail_canary.py -q` AND the full suite `uv run pytest -q` (base suite must stay green).

### Task 5: Live-index canary probe (read-only verification, NOT a test)
- **Do:** After the tests pass, run one read-only probe against the production index and record its full output in the result report's "Build / Tests" section: a small Python snippet (or `python -c`) that builds `NotmuchReader(index_path=Path("/workspace/docker/mbsync/notmuch"), mail_root=Path("/workspace/docker/mbsync/backup"), work_dir=Path("/tmp/mk-canary-probe"))` and prints `canary.run_canaries(reader, Path("/workspace/docker/mbsync/backup"), "yuri.durodie@vub.be")`. Expected: `total_index` ≈ 13,111 + any new mail since 2026-10-19, `total_disk` ≈ 13,147 + delta, `per_folder["Sent Items"]["delta"] == 0`, `stale` False within tolerance (delta ≤ 100), spot-check ok. If `stale` is True or spot-check fails: do NOT fail the task — record the exact output in Blockers (the workflow treats staleness as report-and-defer).
- **Notes:** Strictly read-only (no `notmuch new`, no writes outside `/tmp`).

## Acceptance

1. `uv run pytest -q` fully green (base suite + new tests), `uv run ruff check .` and `uv run ruff format --check .` clean.
2. From `/tmp`: `mail-search --help` exits 0; `mail-search` (no args) exits 2; `mail-search ORBIT --index /workspace/docker/mbsync/notmuch` exits 0 and prints well-formed blocks against the LIVE index (read-only spot check — include 2 sample lines, redacted of nothing, in the result report).
3. Live canary probe output recorded in the result report with the expected numbers above (or deviation recorded in Blockers).
4. `pyproject.toml` diff = exactly one added `[project.scripts]` line; `/usr/local/bin/mail-search` exists, mode 0755, 2-line shim.
5. No file outside this task's file list was modified in the repo (`git status` after commit shows only the task files in the new commit).

## Out of Scope

- The workflow module (Task 3 of the global plan), `email-routes.md` (Task 2), any change to `reader.py`/`config.py`/`scheduler.py`/base tests, the agent/skill/`opencode.jsonc`, live LLM inference, committing anything outside this repo.

## Notes

- **[Assumption]** `account` = single top-level dir under `mail_root`; multi-account is a usage error (exit 2).
- **[Assumption]** List-mode order = date ascending (the skill mandates date order only for `--thread`; ascending is the documented generalization).
- **[Risk]** Per-message `show` calls (N subprocesses) are the cost of not extending `reader.py`; acceptable at `--limit` 25 default. If the live probe (Task 5) shows list mode > ~10 s for 25 messages, note it in the result for the orchestrator (do not redesign in this task).
- **[Note]** The `/usr/local/bin/mail-search` shim is a host setup step (root, dedicated container) — analogous to `scripts/setup.sh`'s role; folding it into `setup.sh` is a follow-up (out of scope here).
- **[Note]** `python-dotenv` is already a runtime dependency (base); `PROJECT_ROOT` computation: `Path(__file__).resolve().parents[3]` for `src/agentic_scripts/mail/mail_search.py`.
