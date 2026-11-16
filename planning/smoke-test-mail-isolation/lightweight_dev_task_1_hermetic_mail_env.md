# lightweight-dev Output — Task: Hermetic MAIL_* env isolation in smoke tests

**Task:** #1    **Session:** smoke-test-mail-isolation    **Date:** 2026-11-16

## Summary

Made the autouse `_isolate_mail_env` fixture the single source of MAIL_* env isolation in both
`tests/smoke/test_smoke_base.py` and `tests/smoke/test_smoke_oc_todo.py`. The fixture now requests
`tmp_path`, points `MAIL_INDEX_DB`/`MAIL_PROCESSED_LOG` at nonexistent per-test tmp paths before
`yield` (so mail-keeper returns `skipped` — no canary walk, no live agent), and keeps the existing
save/restore. Removed the duplicated `os.environ[...]` assignments from `_workspace()` in both files
(replaced with a trimmed comment pointing at the fixture; the "why" rationale moved into the fixture
docstring). Added one assertion to `test_smoke_oc_todo_empty_repo_list_no_agent` pinning the
isolation (`WORKFLOW mail-keeper status=skipped`). The previously-hanging test now passes in <1 s,
and the plain full suite (no deselects) is green: 183 passed.

## Files
| File | Action | Why |
|---|---|---|
| `tests/smoke/test_smoke_oc_todo.py` | modify | Fixture becomes single isolation point; `_workspace()` no longer sets env; new assertion pins the skip in the previously-buggy test |
| `tests/smoke/test_smoke_base.py` | modify | Same fixture change + `_workspace()` env removal (latent instance of the same defect) |

## Build / Tests
- `uv run pytest tests/smoke/ -q`: PASS — 13 passed in 5.2 s (well under the 2-min limit; previously the oc-todo file hung 47+ min on this machine).
- `uv run pytest tests/smoke/test_smoke_oc_todo.py::test_smoke_oc_todo_empty_repo_list_no_agent -q`: PASS — 1 passed in 0.09 s (well under 30 s).
- Sanity check (Task 2 note): temporarily reverted the fixture to save/restore-only → the test **hung** (`timeout 45` → exit 124), proving the new assertion pins the behavior. Restored byte-identical; no run log was created in the repo `logs/` dir, no pytest process left alive.
- `uv run pytest -q` (full suite, no deselects): PASS — **183 passed** in 30 s, 0 failed, 0 deselected.
- `uv run ruff check` on both touched files: PASS — "All checks passed!".
- `uv run ruff format --check`: `test_smoke_base.py` clean; `test_smoke_oc_todo.py` reports one pre-existing unformatted line (`_write_config` signature, L40) that is **not** in my diff and was already unformatted at HEAD (verified via `git show HEAD:... | ruff format --check`). My changed lines are not in the format diff.

## Acceptance Verification
| # | Criterion (verbatim) | Result | Notes |
|---|---|---|---|
| T1.1 | `grep -n "os.environ\[" tests/smoke/test_smoke_base.py tests/smoke/test_smoke_oc_todo.py` shows the MAIL_* assignments only inside the autouse fixtures (restore-loop assignments aside) — none in `_workspace()`. | PASS | base: L91–92 (fixture) + L98 (restore loop); oc_todo: L101–102 (fixture) + L108 (restore loop). No MAIL_* assignment in either `_workspace()`. |
| T1.2 | `uv run pytest tests/smoke/ -q` → all pass, total wall time < 2 min (previously the oc-todo file hung 47+ min on this machine). | PASS | 13 passed in 5.19 s. |
| T2.1 | The new assertion passes: `uv run pytest tests/smoke/test_smoke_oc_todo.py::test_smoke_oc_todo_empty_repo_list_no_agent -q` → PASS in < 30 s on this machine. | PASS | 1 passed in 0.09 s. |
| T2.2 | Temporarily reverting Task 1's fixture change makes this test FAIL (or hang) — sanity-check the test actually pins the behavior, then re-apply. (Do this carefully with `git stash`/manual revert and verify the working tree is restored — never leave the tree dirty.) | PASS | Reverted fixture to save/restore-only → test hung (timeout 45 → exit 124). Restored byte-identical (verified via `diff` against backup); `git status` clean except untracked `planning/`. |
| T3.1 | Full suite green, counts reported. | PASS | `uv run pytest -q` (no deselects): **183 passed**, 0 failed, 0 deselected in 30 s. |
| T3.2 | Lint/format clean on touched files. | PASS | ruff check clean on both; my changed lines are format-clean. The one `ruff format --check` flag in oc_todo (`_write_config`, L40) is pre-existing at HEAD and outside my diff (left untouched per Out-of-Scope). |
| T3.3 | Commit landed on `plan/agentic-workflows` and pushed; commit message quoted in the result report. | PASS | Committed on `plan/agentic-workflows` and pushed to origin (`642b0f7..550ce4a`). Message: `OC: Hermetic MAIL_* env isolation in smoke fixtures (no live agent dispatch)`. |

## Blockers
None.

Note for the orchestrator: while running the Task 2 sanity check I briefly reverted the fixture and ran the previously-buggy test under a 45 s timeout. The test hung as expected and was killed by `timeout` before it could write a run log or leave a process behind (verified: no run log in the repo `logs/` dir from that window, no pytest/agentic_scripts process alive). Several `opencode run --agent mail-keeper` processes were observed on the machine, but all pre-date my test (started 11:03, 13:44, 21:06, 21:13 — the last ~5 min before my test ran) and are part of the parallel production catch-up runs the spec warned about; none was spawned by my test. No live agent was dispatched by any command I ran in the final (restored) state.

## Next Steps
- None required for this task. The full suite is green with no deselects; the previously-deselected smoke test now passes and pins the isolation.
