# Result: Task 3 — Agent runner + git helpers
## Status
DONE_WITH_CONCERNS

## Acceptance (check each item from the task file)
- [x] **AC1: `uv run pytest tests/test_agent.py tests/test_git.py -v` — all pass; total suite wall time < 60s (timeout test ≤ ~10s); no test spawns the real `opencode` or touches the network** — evidence:
  - `tests/test_agent.py` + `tests/test_git.py`: **13 passed in 3.51s**.
  - Full suite (`uv run pytest tests/ -q`, includes Task 1's 18 + parallel Tasks 2/4 files present at run time): **62 passed in 11.87s** — wall time well under 60s; the timeout test alone runs in ~2.5s (asserts `elapsed < 10`).
  - No real binary: every agent test points `Config.agent.binary` at a tmp-dir Python shim (`fake_opencode`); git tests use local-path bare remotes only (no network).
- [x] **AC2: `uv run ruff check .` + `uv run ruff format --check .` clean (whole repo)** — evidence: `ruff check .` → `All checks passed!` (exit 0); `ruff format --check .` → `36 files already formatted` (exit 0).
- [x] **AC3: `AgentRunner(config=..., logger=...)` keyword signature matches `WorkContext.runner` in Task 1's `base.py` exactly** — evidence: `python -c` importing `WorkContext`, building one with the shipped config + a tmp `StateStore`, and accessing `.runner` → printed `runner type: AgentRunner`; no `TypeError`.
- [x] **AC4: `git status --porcelain` shows only this task's 4 files as new** — evidence: after commit, my 4 files are committed; remaining untracked entries are the pre-existing `planning/` files and the *parallel* Task 2 files (`__main__.py`, `cli.py`, `scheduler.py`, `test_gate.py`, `test_lock.py`, `test_scheduler.py`) which I did not create or stage. See Concerns for a commit-hygiene incident that was corrected.
- [x] **AC5: Committed with `OC:` prefix, pushed to `plan/agentic-workflows`** — evidence: commit `56ab3c0` "OC: Add agent runner (opencode JSON) and git helpers" (4 files changed, 1106 insertions); `git push --force-with-lease` → `f650085...56ab3c0 plan/agentic-workflows -> plan/agentic-workflows (forced update)` (exit 0).

## Files created/modified
| File | Purpose |
|---|---|
| `src/agentic_scripts/agent.py` | `AgentResult` dataclass + `AgentRunner`: exact command construction (`binary run --agent A --format json --dir D [--title T] [--auto] [--model M] brief`), NDJSON streaming via `select()`-bounded readline (deadline checked even when the child goes silent), daemon-thread stderr drain (last 40 lines kept), process-group kill on timeout (`start_new_session=True` + `os.killpg(SIGKILL)`), exit-code→status mapping (0+text→ok / 0 no-text→error "no final text event in stream" / non-zero→error with error-event payload or stderr tail). Module docstring covers the verified event schema + steps-cap contract + research cache pointer. Import-safe: pulls in only `agentic_scripts.config`. |
| `src/agentic_scripts/git.py` | `GitError` (`<op> failed (exit <code>): <stderr tail>`) + stateless `Git`: `is_repo` (False, not error), `current_branch`, `rev_parse` (raises on bad refs), `clone` (+`depth`), `fetch`, `branches` (strips `origin/`, drops `HEAD` *and* the spurious local-clone `origin/HEAD` entry, sorted), `worktree_add`/`worktree_remove`, `add`, `commit` (returns False on "nothing to commit" — idempotency primitive), `push` (+`upstream`). Timeouts: 300s clone/fetch/push, 60s local; no `shell=True`, no `check=True`. |
| `tests/test_agent.py` | Fake `opencode` shim (tmp-dir Python script with shebang; argv recorded via `SHIM_ARGV`; modes `happy`/`err`/`notext`/`sleep`/`garbage`). 7 tests: exact build_command (full + minimal flag absence, brief last), happy path (ok, exit 0, last-text-wins "FINAL REPORT", 5 events, argv verified), err (exit 1 via `SHIM_EXIT`, error payload), notext (exact sentinel error), sleep+timeout=2s (status timeout, elapsed <10s, partial event, no orphan shim process), garbage line (defensive parse, still ok). |
| `tests/test_git.py` | Throwaway repos: `init_repo`/`init_bare` helpers (bare HEAD symref set to `main` so clone can check out; git identity via `os.environ.setdefault` at module import). 6 tests: is_repo true/false, clone→branch/SHA match + depth=1, push new branch → fresh clone+fetch lists it + empty commit returns False, worktree add/remove (second remove → GitError), bad ref → GitError with "failed (exit", staged commit moves SHA. |

## Commits
- `56ab3c0` — "OC: Add agent runner (opencode JSON) and git helpers" (4 files, 1106 insertions) — **pushed** to `origin/plan/agentic-workflows`.
- Note: an intermediate commit `f650085` was pushed by mistake (see Concerns) and replaced by the force-with-lease push above; it is no longer on the branch.

## Deviations from task spec
1. **Timeout detection uses `select()`-bounded readline instead of a plain blocking read loop.** The spec's step 3/6 ("read line-by-line", "wrap the wait loop with the deadline") cannot be honored with a bare `proc.stdout.readline()` iterator: when the child goes silent mid-stream (the `sleep` mode), `readline()` blocks indefinitely and the deadline is never checked. Each readline is now preceded by `select.select([stdout], [], [], 0.25)`; on timeout breach the group is killed exactly as specified. Behavior contract (status, partial events, killpg) is unchanged.
2. **`err` test mode sets exit 1 via `SHIM_EXIT=1`.** The spec's shim description says modes select the payload and "(c) honors SHIM_EXIT"; the `err` payload alone exits 0 by default, so the test sets `SHIM_EXIT=1` to realize "one error event then exit 1".
3. **Git test setup details (not in spec, required for determinism):**
   - `init_bare` sets the bare repo's HEAD symref (`symbolic-ref HEAD refs/heads/main`). Without it, this git build (2.43.0) clones with "remote HEAD refers to nonexistent ref, unable to checkout" — no branch checked out, `rev-parse HEAD` fails (verified empirically in /tmp).
   - The push test creates the local `feature/x` branch (`checkout -b`) before `push(branch, upstream=True)` — the spec's `git push --set-upstream origin <branch>` form requires a local branch to exist.
   - `_drop_origin_head` removes the `origin/HEAD` symref that cloning a *local* bare repo creates (a spurious `origin` entry in `branches()`); `Git.branches` also drops it defensively so real-origin behavior is unaffected.

## Concerns / notes for orchestrator
1. **Commit-hygiene incident (corrected):** the first commit (`f650085`) accidentally included Task 2's files (`__main__.py`, `cli.py`, `scheduler.py`, `test_gate.py`, `test_lock.py`, `test_scheduler.py`) and a 2-line change to `config.py` — the parallel Task 2 agent had *pre-staged* those in the shared index before I ran `git add <my 4 files>` + `git commit`. I corrected it with `git reset --soft HEAD~1`, unstaged the foreign paths, recommitted only my 4 files (`56ab3c0`), and pushed with `--force-with-lease` (safe: the branch had no other commits in between; Task 2's work remains intact as untracked/modified files for that agent to commit). **Recommendation:** parallel dev agents should stage-and-commit atomically, or the orchestrator should serialize commits per branch.
2. **`config.py` shows a 2-line working-tree modification** (`QuietWindow.in_window` now passes field names to `_parse_hhmm`) — made by the Task 2 agent, not me; left untouched and uncommitted.
3. **Local-clone `origin/HEAD` quirk:** `Git.branches()` defensively drops a ref literally named `origin/HEAD`; with real remote origins this is a no-op (they don't expose that ref). Documented in the test file.
4. **No fallback needed for process-group kill:** `start_new_session=True` + `killpg(SIGKILL)` worked correctly under this container's cgroup limits — orphans verified absent via `pgrep -f fake_opencode`.
5. **Import-safety verified:** importing `agentic_scripts.agent` pulls in only `agentic_scripts.config` (checked via `sys.modules`) — parallel-safe with Tasks 2/4.
