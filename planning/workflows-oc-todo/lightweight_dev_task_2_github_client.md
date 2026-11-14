# lightweight-dev Output — Task: GitHub REST client (`github.py`)

**Task:** #2    **Session:** `planning/workflows-oc-todo/`    **Date:** 2026-11-14

## Summary
Implemented the OC-todo workflow's two GitHub REST operations as a small stdlib-only
client. Created `src/agentic_scripts/github.py` exposing `GitHubError` (with `status` /
`body` attributes and a documented message format) and `GitHubClient` with exactly two
public operations — `find_pr_by_head` (idempotency check) and `create_pr`. The PAT is
read from `GITHUB_PAT` at construction, sent only in the `Authorization: Bearer` header,
and never logged or placed in error bodies. The module-level `_urlopen = urllib.request.urlopen`
alias is the single test seam. Also created a fully hermetic `tests/test_github.py` (9 tests)
that monkeypatches `agentic_scripts.github._urlopen` so no test touches the network.

Style mirrors `src/agentic_scripts/git.py`: module docstring (Purpose/Rationale/Usage),
a `*Error(RuntimeError)` with a documented message shape, a stateless class, small explicit
methods, and Google-style docstrings with typed Args/Returns/Raises on every method.

## Files
| File | Action | Why |
|---|---|---|
| `src/agentic_scripts/github.py` | create | The stdlib-only GitHub REST client (`GitHubError`, `GitHubClient.find_pr_by_head`, `GitHubClient.create_pr`) with the `_urlopen` test seam. |
| `tests/test_github.py` | create | Hermetic tests for all 10 plan-specified cases; every test patches `agentic_scripts.github._urlopen` (zero network). |

## Build / Tests
- `uv run pytest tests/test_github.py -v`: PASS — 9 passed (all 10 plan cases covered; see Acceptance Verification #1)
- `uv run pytest tests/ -v`: PASS — 133 passed (baseline was 124 before this task; +9 are the new github tests, no regressions)
- `uv run ruff check src tests`: PASS — All checks passed!
- stdlib-only import check: PASS — `agentic_scripts.github` imports only `__future__`, `json`, `os`, `urllib`; all resolve to `/usr/lib/python3.12/` (no site-packages / `.venv` third-party packages)

## Acceptance Verification
| # | Criterion (verbatim) | Result | Notes |
|---|---|---|---|
| 1. | `uv run pytest tests/test_github.py -v` — all pass, zero network (the fake records every call; no test may let `_urlopen` be the real function). | PASS | 9/9 pass. Every test uses the `recorder` fixture, which does `monkeypatch.setitem(gh.__dict__, "_urlopen", rec)`; the real `urllib.request.urlopen` is never invoked. `test_missing_pat_no_network` additionally asserts `len(recorder.calls) == 0`. |
| 2. | `uv run pytest tests/ -v` — full suite green. | PASS | 133 passed (baseline 124 + 9 new). No regressions. Note: a parallel Task-1 agent concurrently modified `tests/test_config.py`; the full-suite run was performed against the working tree and is green. |
| 3. | `uv run ruff check src tests` — clean. | PASS | "All checks passed!" (line-length 100, E/F/I/UP/W). |
| 4. | `import agentic_scripts.github` pulls in no third-party packages (stdlib + nothing). | PASS | AST scan of the module's imports → `{__future__, json, os, urllib}`; each resolves to a `/usr/lib/python3.12/...` stdlib path. No `requests`, no new dependencies, `pyproject.toml` untouched. |

## Blockers
None.

## Next Steps
- Task 4 (OC-todo pipeline) can now consume `GitHubClient` for its idempotency check and PR creation; it should treat any `GitHubError` as the API-outage guardrail (skip-and-note), since this client deliberately performs no retry/backoff.
- Operator must ensure `GITHUB_PAT` is present in the environment by workflow time (the scheduler loads `.env` before workflows run); with no PAT, both methods raise a `GitHubError` naming `GITHUB_PAT` before any network call.
