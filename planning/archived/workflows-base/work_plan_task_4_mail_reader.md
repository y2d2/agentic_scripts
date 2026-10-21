# Task 4: Notmuch mail reader

**Purpose:** Implement `NotmuchReader` — the shared library over notmuch's verified 0.38.3 query surface — plus pure query-builder helpers, so the mail-keeper workflow plan can build its `mail-search` CLI, canaries, and triage logic on a tested, hermetic base without touching notmuch directly.

## Objective

Deliver `src/agentic_scripts/mail/reader.py` (+ `__init__.py`) with hermetic tests against a throwaway notmuch index (built inside `tmp_path`) such that: (a) count/search/message-ids/show/body_text all behave per the verified 0.38.3 JSON shapes, (b) the HTML-only fallback path returns the raw maildir file for caller-side MIME parsing, (c) query-builder helpers emit exactly the verified working forms (and refuse the broken ones), (d) the reader is read-only by construction (`synchronize_flags=false`, no `notmuch new` in the class API).

## Context

- **Repo:** `/workspace/Python/agentic_scripts`, branch `plan/agentic-workflows`. **Task 1 is already merged** (skeleton, `Config`, `StateStore`, logging, Ruff/pytest config). Read `work_plan_task_1_foundation.md` for shapes.
- **Environment (re-verified 2026-10-20):** `notmuch` 0.38.3 at `/usr/bin/notmuch`, Python 3.12.3, `uv` 0.12.5. Hermetic tests only — the live index at `/workspace/docker/mbsync/notmuch/` (13,111 messages) is the *reference*, not a test input.
- **Verified notmuch 0.38.3 reader surface (read-only probes against the live index today — the spec below is empirical, not guesswork):**
  - Reader config (what this class generates):
    ```
    [database]
    path=<index_path>
    mail_root=<mail_root>
    [maildir]
    synchronize_flags=false
    ```
    (`synchronize_flags=true` belongs to the mbsync *writer* side only; the reader must never flip flags.)
  - `notmuch count [query]` → integer line. Bare `notmuch count` (no query) = total message count (live: 13,111).
  - `notmuch search --format=json <query>` → **JSON array of thread objects**: `{thread, timestamp, date_relative, matched, total, authors, subject, query, tags}`. `query` is a **2-element array** `[matched_subquery, unmatched_subquery]`, each a space-joined string of `id:<msgid>` clauses. Message-ids (RFC 5322 Message-Id) never contain spaces → **whitespace split is safe** to recover per-thread message ids. `matched`/`total` are per-thread counts; `authors` is the joined author string; `timestamp` is ISO-ish.
  - **`--format=messages` does NOT exist in this build** (unknown keyword argument) — do not use it; per-message data comes from `show`.
  - `notmuch show --format=json 'id:<msgid>'` → nested recursive JSON **list**. The primary message is the **first element**; thread-context messages are nested arrays deeper in the structure (recursive walk). Message object keys: `{id, match, excluded, filename[], timestamp, date_relative, tags, duplicate, body[], crypto, headers}`. `filename` is a list (single-element for normal mail). `body` parts: `text/plain` parts carry `content` (decoded text); **`text/html` parts carry only `content-length` — no body content** → HTML-only messages require reading the raw maildir file at `filename[0]` and parsing the MIME.
  - Working query forms: free text, `from:"Name Or <email>"`, `folder:"<account>/<dir>"` (**always double-quoted** — paths contain spaces, e.g. `folder:"yuri.durodie@vub.be/Sent Items"` → 2,960 on the live index), `id:<msgid>`, `thread:<tid>`, `date:YYYY*` (prefix star works).
  - **Broken in this build — do not use (and the builder refuses them):** `all:`, `field:*` wildcards, `after:`, `before:`, `last:`.
- **Conventions:** Google-style docstrings, Ruff clean, hermetic tests.
- **Parallel-safety:** you own ONLY `src/agentic_scripts/mail/__init__.py`, `src/agentic_scripts/mail/reader.py`, `tests/test_mail_reader.py`. Do NOT touch `pyproject.toml`, `config/workflows.yaml`, `scheduler.py`/`cli.py`/`__main__.py` (Task 2), `agent.py`/`git.py` (Task 3), Task 5 files, or Task 1 files. Importing `agentic_scripts.mail.reader` must not import `agent`, `git`, or `scheduler`.

## Tasks

### 1. Create `src/agentic_scripts/mail/__init__.py`
- One-line module docstring ("notmuch reader package — read-only mail access for workflows"). No submodule imports.

### 2. Create `src/agentic_scripts/mail/reader.py`
- `class NotmuchError(RuntimeError)` — message = `<op> failed (exit <code>): <stderr tail>`.
- **Query builders** (module-level pure functions; the verified working forms, nothing else):
  - `q_text(term: str) -> str` — returns the term unchanged (caller passes a safe phrase).
  - `q_from(value: str) -> str` — `from:"<value>"`.
  - `q_folder(account: str, path: str) -> str` — `folder:"<account>/<path>"` (single quoting of the whole path; account/path values are NOT re-quoted internally).
  - `q_id(msgid: str) -> str` — `id:<msgid>` (no quoting — ids never need it).
  - `q_thread(tid: str) -> str` — `thread:<tid>`.
  - `q_date_prefix(year: int) -> str` — `date:<year>*`.
  - `q_and(*clauses: str) -> str` — join with `" and "` (empty input → `NotmuchError` — an empty compound query is a caller bug).
  - Refusal contract (documented in the module docstring, enforced by a `SUPPORTED_PREFIXES = {"from", "folder", "id", "thread", "date"}` constant that the builder functions reference): `all:`, `field:` wildcards, `after:`, `before:`, `last:` are unsupported in this notmuch build — there is deliberately no helper for them, and `q_and` rejects any clause whose first token starts with an unsupported prefix (raise `NotmuchError`).
- `class NotmuchReader:`
  - `__init__(self, *, index_path: Path, mail_root: Path, work_dir: Path, logger: logging.Logger | None = None, notmuch_bin: str = "notmuch")` — creates `<work_dir>/notmuch-reader-config` containing exactly the reader config above (paths resolved to absolute), 0600. Every subprocess call passes `env={**os.environ, "NOTMUCH_CONFIG": str(that file)}`. Store `self._env`. The class never mutates `index_path`/`mail_root` contents (read-only contract, stated in the docstring).
  - `_run(self, args: list[str], *, timeout: int = 120) -> str` — `subprocess.run([self._bin] + args, capture_output=True, text=True, env=self._env, timeout=timeout)`; non-zero → `NotmuchError`; timeout → `NotmuchError`. Returns stdout.
  - `count(self, query: str = "") -> int` — `notmuch count [query]`; parse the stdout integer (first token).
  - `search(self, query: str, limit: int = 25) -> list[dict]` — `notmuch search --format=json <query>` → parse JSON array of thread objects → return **at most `limit` thread rows**, each normalized to `{thread, subject, authors, timestamp, tags, matched, total, message_ids}` where `message_ids` = whitespace-split `id:` clauses of `query[0]` (strip the `id:` prefix), in order. (Document: `limit` bounds *threads*, not messages.)
  - `message_ids(self, query: str) -> list[str]` — all matched message ids across threads (same extraction as above), deduplicated preserving first-seen order.
  - `show(self, message_id: str) -> dict` — `notmuch show --format=json 'id:<msgid>'` → parsed JSON list → return `{"primary": <first element>, "context": [<all other message objects, depth-first, in document order>], "raw": <full parsed doc>}`. Empty list → `NotmuchError` (no such message).
  - `body_text(self, message_id: str) -> tuple[str | None, Path | None]` — from `show`'s primary: walk `body` parts in order; concatenate `content` of `text/plain` parts (UTF-8, `errors="replace"`); if any plain text found → `(text, None)`. If none found and at least one `text/html` part exists → `(None, Path(primary["filename"][0]))` (the raw maildir file for caller-side MIME parsing). Neither → `(None, None)`.
- Module docstring: one paragraph on the read-only contract + one paragraph summarizing the verified 0.38.3 shapes (with the broken-query list) — this file is the team's reference for what this notmuch build does and does not do.

### 3. Write `tests/test_mail_reader.py` (hermetic: throwaway maildir + index in `tmp_path`; never touch the live index)
- **Fixture `hermetic_mail(tmp_path)`:** build a minimal maildir layout under `tmp_path/mail/<acct>/cur/` (3 messages):
  1. `m1.eml` — plain text, `From: Alice <alice@example.com>`, `Subject: Hello plain`, `Message-Id: <m1@example.com>`, date in 2026.
  2. `m2.eml` — multipart/mixed with a `text/html` part (HTML body, no plain part), `From: Bob <bob@example.com>`, `Subject: Html only`, `Message-Id: <m2@example.com>`.
  3. `m3.eml` — plain text, `From: Alice <alice@example.com>`, `Subject: Second from alice`, `Message-Id: <m3@example.com>`.
  - Build the index: write the reader-style config (index dir `tmp_path/notmuch-index`), `NOTMUCH_CONFIG=... notmuch new` (subprocess; this is test setup, NOT the class API — the class itself never calls `new`).
  - Return `(reader, tmp_path, message metadata)`.
- Tests:
  1. `count() == 3`; `count(q_from("Alice")) == 2`; `count(q_folder(acct, "cur")) == 3` (or the folder notmuch reports for cur — assert against the value `count()`'s own query returns, i.e. consistency, not a hardcoded folder name, if the folder name turns out to include the account path).
  2. `search(q_from("Alice"))` → 1–2 thread rows; union of their `message_ids` == {`m1@example.com`, `m3@example.com`}; every row has `subject`/`authors`/`timestamp` non-empty.
  3. `message_ids("hello plain second from alice")` (free-text matching both Alice subjects) == the two Alice ids, deduped.
  4. `show(<m1 id>)` → `primary["id"]` correct; `primary["headers"]` contains `Subject: Hello plain`; `context` is a list (possibly empty).
  5. `body_text(<m1 id>)` → plain text present, contains `Hello plain` content, second element `None`.
  6. `body_text(<m2 id>)` → `(None, path)` where `path` exists and its bytes contain the HTML marker (the fallback path — the exact shape the mail-keeper plan will consume).
  7. `count` on a nonexistent id query → `0` (not an error).
  8. Builder unit tests (no notmuch involved): `q_from("Yuri Durodie")` == `from:"Yuri Durodie"`; `q_folder("a@b", "Sent Items")` == `folder:"a@b/Sent Items"`; `q_date_prefix(2026)` == `date:2026*`; `q_and(q_from("x"), q_date_prefix(2026))` == `from:"x" and date:2026*`; `q_and()` (no args) → `NotmuchError`; a clause with an `after:` prefix rejected by `q_and` → `NotmuchError`.
  9. Broken query surfaces: `reader.count("all:")` raises `NotmuchError` (exit ≠ 0, stderr tail in message) — documents that the build rejects it.
  10. Read-only contract: snapshot the mtime of every file under `tmp_path/mail` before a `search` + `show` cycle; assert unchanged afterwards.

## Acceptance criteria

1. `uv run pytest tests/test_mail_reader.py -v` — all pass; the test creates its own index (no dependency on the live one); total wall time < 30s.
2. `uv run ruff check .` + `uv run ruff format --check .` clean (whole repo).
3. `import agentic_scripts.mail.reader` succeeds with no imports of `agentic_scripts.agent`/`git`/`scheduler` (verify by `python -c` + `sys.modules` check).
4. The generated reader config file (in `work_dir`) matches the canonical reader config byte-for-byte modulo the two paths (asserted in a test).
5. `git status --porcelain` shows only this task's 3 files as new.
6. Committed with `OC:` prefix, pushed to `plan/agentic-workflows`.

## Out of Scope

- The `mail-search` CLI (arg surface, list/detail modes, exit codes), live-index canary verification, triage/vault/draft logic, HTML MIME parsing (the reader only *points* at the raw file for HTML) — all mail-keeper-plan work built on this library.
- Tag operations, `notmuch new`, flag sync, any write to maildir or index (read-only by contract).
- Scheduling, state, git (other tasks).

## Notes

- If `notmuch new` in the fixture is slow or fails in the container (e.g. Xapian lock quirks under parallel task waves), run the index build with a unique tmp dir per test session (the `tmp_path` fixture already guarantees this) and set `NOTMUCH_CONFIG` per-process — no shared state.
- The `message_ids` extraction (splitting `query[0]` on whitespace) is **verified safe for this build's output** (RFC 5322 Message-Ids contain no spaces); keep the split trivial and document the assumption — do not over-engineer a parser.
- Keep `limit` semantics documented as "max threads" — the mail-keeper CLI will page on its own.
- The live-index reference numbers (13,111 / 10,001 / 2,960 / 2,987) are for the mail-keeper plan's canaries; this task asserts nothing against them.
