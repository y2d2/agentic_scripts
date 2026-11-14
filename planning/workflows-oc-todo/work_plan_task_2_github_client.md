# Task Plan: GitHub REST client (`github.py`)

**Purpose:** Provide the OC-todo workflow's two GitHub REST operations — find-a-PR-by-head-branch and create-a-PR — as a small stdlib-only client that reads the PAT from the environment, fails loudly with context, and is fully testable without network.

**Task:** #2    **Session:** `planning/workflows-oc-todo/`    **Result file:** `planning/workflows-oc-todo/lightweight_dev_task_2_github_client.md`

## Objective

New module `src/agentic_scripts/github.py` exposing `GitHubError` and `GitHubClient` with exactly two public operations (`find_pr_by_head`, `create_pr`). `gh` CLI is not installed on this machine, so PR mechanics go through the REST API with the configured PAT (`GITHUB_PAT` in `.env`/environment — never in config or argv). The module must be importable and unit-testable with **zero network access**.

## Context

Project: `/workspace/Python/agentic_scripts` (Python ≥3.12, `uv`, src layout). Lint: `uv run ruff check src tests` (line-length 100, E/F/I/UP/W). Tests: `uv run pytest tests/ -v`. **Stdlib only** (`urllib.request`, `urllib.error`, `json`, `os`) — no `requests`, no new dependencies; do not modify `pyproject.toml`. Do not commit/push — the orchestrator handles git.

Read first (style source of truth):
- `src/agentic_scripts/git.py` — the module style to mirror: module docstring (Purpose/Rationale/Usage), `*Error(RuntimeError)` with documented message shape, a stateless class, small explicit methods, no `shell=True`-style shortcuts. `github.py` sits beside it as the HTTP sibling (git.py owns git plumbing; github.py owns PR plumbing; both are consumed by the workflow layer).
- `src/agentic_scripts/mail/reader.py` or `mail/canary.py` — for the "wrap a subprocess/IO call, raise a named error with context" pattern.
- `tests/test_git.py` — hermetic test style (throwaway fixtures, no network).
- Docstring convention: Google-style, `Purpose:` / `Rationale:` / `Usage:`, typed Args/Returns/Raises/Side Effects.

Environment contract: the scheduler loads `.env` before workflows run (see `scheduler.run`), so by workflow time `GITHUB_PAT` is in `os.environ` if the operator configured it. The client reads it **at client construction** (not per request) and keeps no secrets in logs.

## Tasks

### Task 1: `src/agentic_scripts/github.py`
- **Files:** `src/agentic_scripts/github.py` (create)
- **Do:**
  1. Module docstring: Purpose (the two PR operations for the oc-todo workflow; PAT from environment, never from arguments or logs), Rationale (why REST API: `gh` not installed — verified 2026-10-14; stdlib-only keeps the dependency footprint zero; the `_urlopen` module-level indirection is the test seam), Usage (construct `GitHubClient()`, call `find_pr_by_head` / `create_pr`).
  2. `class GitHubError(RuntimeError)` — attributes: `status: int | None` (HTTP status, None for transport errors), `body: str` (response body excerpt, ≤ ~40 lines / truncated to ~4 KB). Document the message format `<context>: HTTP <status>` or `<context>: <transport error>`.
  3. Module-level `_urlopen = urllib.request.urlopen` — the single monkeypatch seam (tests patch `agentic_scripts.github._urlopen`; production uses the real function).
  4. `class GitHubClient` (stateless per instance):
     - `__init__(self, *, pat: str | None = None, base_url: str | None = None, timeout: int = 30)`:
       - `pat` defaults to `os.environ.get("GITHUB_PAT", "").strip()`.
       - `base_url` defaults to `"https://api.github.com"`; strip trailing `/`.
       - `timeout` is the per-request wall-clock timeout in seconds (int ≥ 1; validate — `ValueError` on bad timeout is fine, it's a programmer error).
     - `def _request(self, method: str, path: str, *, payload: dict | None = None) -> dict | list | None`:
       - No PAT (empty string) → raise `GitHubError(status=None, ...)` with a message naming `GITHUB_PAT` (and that the workflow cannot proceed) — **before** any network call.
       - Build `urllib.request.Request(base_url + path, data=json.dumps(payload).encode("utf-8") if payload is not None else None, method=method, headers={...})`. Headers: `Authorization: Bearer <pat>`, `Accept: application/vnd.github+json`, `X-GitHub-Api-Version: 2022-11-28`, `User-Agent: agentic-scripts`, plus `Content-Type: application/json` when a payload is sent.
       - Call `resp = _urlopen(req, timeout=self.timeout)`; `body = resp.read()`. If the body is empty (204-style) → return None; else `json.loads` (on `json.JSONDecodeError` → `GitHubError` with the body excerpt).
       - Catch `urllib.error.HTTPError as e` → `GitHubError(status=e.code, body=<excerpt of e.read() decoded with errors="replace">)` (context = the method+path); catch `urllib.error.URLError as e` → `GitHubError(status=None, body=str(e.reason))`.
     - `def find_pr_by_head(self, owner: str, repo: str, head_branch: str) -> dict | None`:
       - GET `/repos/{owner}/{repo}/pulls?state=all&head={owner}:{head_branch}` (simple f-string; owner/repo are validated `owner/name` tokens, `head_branch` is `oc-todo/<12 hex>` — no URL-encoding needed; document that).
       - Returns the first item of the list (a head ref is unique per owner:branch), or None when the list is empty.
     - `def create_pr(self, owner: str, repo: str, *, title: str, body: str, head: str, base: str) -> tuple[int, str]`:
       - POST `/repos/{owner}/{repo}/pulls` with payload `{"title": ..., "body": ..., "head": ..., "base": ...}` (`head` is `owner:branch`, `base` is the target branch name).
       - Returns `(data["number"], data["html_url"])` (KeyError → `GitHubError` — a malformed 201 response is a fault).
     - **No other methods** — no close/merge/issue operations (out of scope).
  5. Keep every method docstring-complete per the convention.
- **Notes:** This class is deliberately dumb: it does no retry, no rate-limit backoff, no caching — the workflow layer (Task 4) decides what to do with a `GitHubError` (skip-and-note, per the plan's API-outage guardrail). Rate-limit 403/429 responses simply surface as `GitHubError(status=403/429, ...)`.

### Task 2: `tests/test_github.py`
- **Files:** `tests/test_github.py` (create)
- **Do:** Hermetic — monkeypatch `agentic_scripts.github._urlopen` with a fake that records every call and returns canned responses; never touch the network.
  1. Test fixtures/helpers: `FakeResponse(status: int, body: bytes)` with `.read()`; a `recorder` that appends `(method, url, headers, payload_bytes)` per call; `monkeypatch.setitem("agentic_scripts.github._urlopen", fake)`.
  2. `test_create_pr_sends_exact_request`: `create_pr("owner", "name", title="OC: fix x", body="BODY", head="owner:oc-todo/abc123def456", base="dev")` → recorder sees exactly one call: method `POST`, URL `https://api.github.com/repos/owner/name/pulls`, headers include `Authorization: Bearer test-pat`, `Accept: application/vnd.github+json`, `X-GitHub-Api-Version: 2022-11-28`, `User-Agent: agentic-scripts`, `Content-Type: application/json`; parsed JSON payload equals `{"title": "OC: fix x", "body": "BODY", "head": "owner:oc-todo/abc123def456", "base": "dev"}`; fake returns `{"number": 7, "html_url": "https://github.com/owner/name/pull/7"}` → call returns `(7, "https://github.com/owner/name/pull/7")`. (Set `pat="test-pat"` via the constructor; do not rely on env.)
  3. `test_find_pr_by_head_returns_pr`: GET to the exact URL `https://api.github.com/repos/owner/name/pulls?state=all&head=owner:oc-todo/abc123def456` (assert the recorded URL verbatim), no payload, no Content-Type header; fake returns `[{"number": 3, "state": "open", ...}]` → the dict is returned.
  4. `test_find_pr_by_head_empty`: fake returns `[]` → None.
  5. `test_http_error_mapped`: fake raises `urllib.error.HTTPError(url=..., code=422, msg="Validation Failed", hdrs=None, fp=io.BytesIO(b'{"message": "Validation Failed"}'))` → `pytest.raises(GitHubError)` with `e.status == 422` and the body excerpt containing `"Validation Failed"`.
  6. `test_transport_error_mapped`: fake raises `urllib.error.URLError("connection refused")` → `GitHubError` with `status is None` and reason in the message.
  7. `test_missing_pat_no_network`: construct with `pat=""` (and monkeypatch `os.environ.pop("GITHUB_PAT", None)` via `monkeypatch.delenv(..., raising=False)`) → both methods raise `GitHubError` whose message names `GITHUB_PAT`; the recorder must record **zero** calls.
  8. `test_env_pat_default`: with `monkeypatch.setenv("GITHUB_PAT", "env-pat")`, `GitHubClient()` issues `Authorization: Bearer env-pat` (assert via recorder).
  9. `test_base_url_trailing_slash_stripped`: `base_url="https://gh.example.test/api/"` → recorded URL starts `https://gh.example.test/api/repos/...` (single slash).
  10. `test_empty_body_returns_none`: `_request` with a 204-style empty body → None.
- **Acceptance:**
  1. `uv run pytest tests/test_github.py -v` — all pass, zero network (the fake records every call; no test may let `_urlopen` be the real function).
  2. `uv run pytest tests/ -v` — full suite green.
  3. `uv run ruff check src tests` — clean.
  4. `import agentic_scripts.github` pulls in no third-party packages (stdlib + nothing).

## Out of Scope
- No retry/backoff/rate-limit budgeting (workflow layer's job).
- No organization/team/issue endpoints; no PR close/merge/update.
- No changes to `git.py` or any workflow module.

## Notes
- The `X-GitHub-Api-Version: 2022-11-28` header is required by GitHub's REST API v2022+; keep it literal.
- PAT values must never appear in log messages or error `body` excerpts (they only go in the request header).
- `[Assumption]` the `state=all` list endpoint with `head=` filter is the idempotency query (existing-PR check) — stable, documented GitHub REST behavior.
