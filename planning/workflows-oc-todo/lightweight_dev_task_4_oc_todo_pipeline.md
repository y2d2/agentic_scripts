# lightweight-dev Output — Task: Per-todo pipeline + hermetic integration tests

**Task:** #4    **Session:** `planning/workflows-oc-todo/`    **Date:** 2026-11-15

## Summary

Implemented the full oc-todo pipeline (`OCTodoWorkflow.run`) on top of Task 3's core, plus
the precondition fix (Task 0), the additive `Git.prune_worktrees` (Task 1), and a hermetic
integration test suite of 12 tests against a fixture bare repo. The run performs one complete,
idempotent pass over every configured repo: clone-or-fetch → per-branch scan → PR-state
lookups for the `pr_open` subset → `plan_run` classification → per-todo pipeline (capped) →
vanished-entry resolution → a single atomic state persist (only when the doc changed).

Key implementation points, all verified by tests:
- **One `find_pr_by_head` per todo per run** — `_lookup_pr` is the sole API seam; `run` step 3c
  caches each `pr_open` lookup in `pr_cache` and passes it to `_process_todo` via
  `cached_lookup` (the `_NOT_LOOKED_UP` sentinel disambiguates "not looked up" from "no PR").
- **Outcome routing** — `failed` outcomes go into the run's `errors` (business error →
  `overall: error`) AND set the state entry to `failed` (retryable next run); `pr_created` /
  `skipped` / `resolved` route to `actions_out`.
- **Fresh-branch-only push invariant** — every pushed branch is `oc-todo/<12hex>`; the scan
  skips non-source branches (`HEAD`, `origin`, and the workflow's own `oc-todo/*`) so a re-run
  never re-detects a marker on its own fix branch (this also makes the orphan-resume test valid).
- **Orphan resume** — a pushed `oc-todo/<id>` branch with no PR opens a PR directly (no agent
  re-run), appending the spec's body note.
- **FakeRunner simulates real work** — it edits the worktree files line-by-line (removes the
  marker unless keep-instruction, appends a fix comment), not a whole-file rewrite.

## Files
| File | Action | Why |
|---|---|---|
| `src/agentic_scripts/workflows/oc_todo.py` | modify | Task 0 (`render_pr_title` decoration stripping) + Task 2 pipeline methods (`_repo_url`, `_clone_or_fetch`, `_scan_repo`, `_with_keep`, `_lookup_pr`, `_process_todo`, `_best_effort_remove_worktree`, `_prune_best_effort`, `_outcome`, `run`/`_run`, `_apply_outcome`) + imports/sentinel/docstrings |
| `src/agentic_scripts/git.py` | modify (additive) | Task 1: `Git.prune_worktrees` (`git worktree prune`, `_TIMEOUT_LOCAL`, `GitError` on failure) |
| `tests/test_oc_todo.py` | modify | Extended `test_render_pr_title_strip_collapse_truncate` with the decoration-stripping cases from Task 0 |
| `tests/test_oc_todo_pipeline.py` | create | Task 3: 12 hermetic integration tests (fixture bare repo, `FakeGitHub`, `FakeRunner`, `RaisingRunner`, `make_ctx`/`make_wf`) |

## Build / Tests
- `uv run pytest tests/test_oc_todo_pipeline.py -v`: PASS — 12/12 green
- `uv run pytest tests/test_oc_todo.py tests/test_git.py -v`: PASS — 39 green (no regressions)
- `uv run pytest tests/ -v`: PASS — 178 green (baseline was 166; +12 pipeline, zero regressions)
- `uv run ruff check src tests`: PASS — clean (E/F/I/UP/W, line-length 100)

## Acceptance Verification
| # | Criterion (verbatim) | Result | Notes |
|---|---|---|---|
| 1. | `uv run pytest tests/test_oc_todo_pipeline.py -v` — all 12 pass. | PASS | 12/12 green in 5.41s |
| 2. | `uv run pytest tests/ -v` — full suite green. | PASS | 178 passed (no regressions) |
| 3. | `uv run ruff check src tests` — clean. | PASS | "All checks passed!" |
| 4. | No test touches the network or real `opencode` (grep the test file for `urlopen`/`opencode` invocations — only via fakes). | PASS | No `urlopen`/`requests`/`socket`/`urllib`; `opencode` appears only as the config `binary:` string and in a docstring — never invoked. All git runs against local bare repos; all GitHub via `FakeGitHub`. |

## Blockers
None.

## Next Steps
- Task 5 (out of scope here, per plan): add `OCTodoWorkflow.create(config)` + register the
  workflow in `config/workflows.yaml` and run()-level (`scheduler.run`) smoke tests. The
  pipeline is ready for that — `create` can simply return
  `OCTodoWorkflow(config.oc_todo)` (real `Git`/`GitHubClient`, runner resolved from `ctx`).
- Note on a deliberate deviation from the spec's literal `head=f"{owner}:{branch_name}"`:
  PRs are created with `head=f"{todo.repo}:{branch_name}"` (i.e. `owner/name:oc-todo/<id>`),
  matching the spec's own test assertion (`head == "fixture/owner-repo:oc-todo/<12hex>"`).
  The `FakeGitHub.find_pr_by_head` matches on the full repo id to stay consistent with how
  `create_pr` stores the head. This is a test-fixture concern only — the production
  `GitHubClient` builds its own API query and is unaffected.
