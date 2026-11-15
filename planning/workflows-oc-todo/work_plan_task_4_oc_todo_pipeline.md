# Task Plan: Per-todo pipeline + hermetic integration tests

**Purpose:** Wire the core (Task 3) into the full workflow run: clone-or-fetch per repo → per-branch scan → state diff → per-todo worktree → agent → commit → push → PR → state persist — with caps, retry-on-next-run failures, and the fresh-branch-only push invariant — proven by hermetic integration tests against a fixture bare repo.

**Task:** #4    **Session:** `planning/workflows-oc-todo/`    **Result file:** `planning/workflows-oc-todo/lightweight_dev_task_4_oc_todo_pipeline.md`

## Objective

`OCTodoWorkflow.run(ctx)` performs one complete, idempotent run and returns a `WorkflowResult`. The high-level plan's acceptance criteria (one PR per unhandled todo on the correct base branch; verbatim PR bodies; re-run no-ops; merged→resolved; timeout/step-exhaustion→failed→retry; only fresh `oc-todo/*` branches pushed) are each covered by a passing hermetic test in `tests/test_oc_todo_pipeline.py`.

## Context

Project: `/workspace/Python/agentic_scripts` (Python ≥3.12, `uv`, src layout). Lint: `uv run ruff check src tests` (line-length 100, E/F/I/UP/W). Tests: `uv run pytest tests/ -v`. No new dependencies. Do not commit/push — the orchestrator handles git.

**Depends on Tasks 1–3 (all landed when you start).** Read first:
- `src/agentic_scripts/workflows/oc_todo.py` — Task 3's core: `Todo`, `todo_id`/`todo_branch_name`, `clone_dir`/`worktree_dir`, `parse_grep_lines`, `has_keep_instruction`, `pr_state_from_api`, `clone_env_for`, `fresh_state`/`validate_state`/`make_entry`, `plan_run`, `render_brief`/`render_pr_title`/`render_pr_body`/`extract_report_sections`, `_is_step_exhausted`, `apply_cap`, and the `OCTodoWorkflow.__init__` shell (`self._settings`, `self._git`, `self._github`, `self._runner_override`).
- `src/agentic_scripts/git.py` — available methods (incl. Task 3's `grep_fixed`, `show_file`, `delete_branch`, `clone(env=)`, `fetch(env=, prune=)`).
- `src/agentic_scripts/agent.py` — `AgentResult` shape (the fake must match it exactly).
- `src/agentic_scripts/workflows/base.py` — `WorkflowResult`, `WorkContext` (a plain dataclass you can construct in tests; `ctx.runner` is a lazy property that caches `ctx._runner` — tests can pre-set `ctx._runner` to a fake, or use `runner=` constructor injection).
- `src/agentic_scripts/workflows/mail_keeper.py` — the `run`/`_run` wrapper pattern (wrap the body, map unexpected exceptions to `status="error"`; one atomic state save at the end).
- `tests/test_git.py` — fixture-repo helpers (`init_repo`, `init_bare`, `_git`, identity `os.environ.setdefault` at module import).
- `tests/test_mail_keeper.py` — fake-agent injection style (docstring: "injected fake agent — NO real opencode, no live LLM").
- Agent contract: `~/.config/opencode/agents/oc-todo-resolver.md` + `skills/oc-todo-resolver/SKILL.md` (brief inputs; report shape; the agent NEVER commits/pushes).

## Tasks

### Task 0: Fix `render_pr_title` comment-decoration stripping (precondition fix)
- **Files:** `src/agentic_scripts/workflows/oc_todo.py` (modify), `tests/test_oc_todo.py` (modify)
- **Do:** The Task-3 implementation strips `MARKER_PREFIX` only when the marker *starts* with it, so the typical marker shape `# OC-todo: fix bug A` yields the PR title `OC: # OC-todo: fix bug A` (comment decoration leaks into the title and — via Task 4 step 6 — the commit message). Change `render_pr_title` to:
  1. `body = marker.strip()`
  2. Strip ONE leading comment decoration + following whitespace: `re.sub(r"^(?://|#|;|%|--)\s*", "", body)` (applies before the prefix strip, so `# OC-todo: x` and bare `OC-todo: x` both work).
  3. Strip the leading `MARKER_PREFIX` if present.
  4. Collapse whitespace, truncate at 72 chars, prefix `"OC: "`.
  Update the docstring (Purpose) to state the decoration-stripping rule. Extend `test_render_pr_title_strip_collapse_truncate` (or add siblings): `# OC-todo: fix bug A` → `OC: fix bug A`; `%OC-todo: do x` → `OC: do x`; bare `OC-todo: fix` → `OC: fix`; 200-char marker still truncates at 72 (keep the existing assertions that still hold).
- **Acceptance:** `uv run pytest tests/test_oc_todo.py -v` green (including the new cases); full suite green; ruff clean.
- **Why now:** this title feeds the PR title and the commit message in the pipeline below — fixing it before any pipeline test exists keeps those tests' expectations honest.

### Task 1: `Git.prune_worktrees` (git.py, additive)
- **Files:** `src/agentic_scripts/git.py` (modify — additions only)
- **Do:** `prune_worktrees(self, repo: Path) -> None` — `git -C <repo> worktree prune` (`_TIMEOUT_LOCAL`, `GitError` on failure). Used to deregister worktree entries whose directories were removed out from under git (crash recovery).

### Task 2: `OCTodoWorkflow` pipeline methods
- **Files:** `src/agentic_scripts/workflows/oc_todo.py` (modify)
- **Do:** Add to the class (docstring per method, Purpose/Args/Returns/Side Effects):

  1. `def _repo_url(self, repo: str) -> str` — `self._settings.repo_urls.get(repo) or f"https://github.com/{repo}.git"` (config override wins; default GitHub HTTPS URL).

  2. `def _clone_or_fetch(self, ctx, repo: str) -> Path | None`:
     - `path = clone_dir(ctx.sandbox_dir, repo)`; `env = clone_env_for(os.environ.get("GITHUB_PAT", "").strip() or None)` (read env at run time; PAT may be absent for public repos/local fixture URLs — then `env=None`).
     - If `not path.exists()` (or not a git repo per `self._git.is_repo`) → `self._git.clone(self._repo_url(repo), path, env=env)`.
     - Else → `self._git.fetch(path, env=env)` (prune by default).
     - Return `path` on success; on `GitError` → log ERROR with the stderr tail, append a repo-level error string to the caller's `errors` list (pass `errors` in or return `(None, error_msg)` — pick one shape and document), return None. **A repo failure never stops other repos.**
     - `mkdir -p` the clone's parent before cloning.

  3. `def _scan_repo(self, ctx, repo: str, clone: Path) -> list[Todo]`:
     - `branches = self._git.branches(clone)` (sorted).
     - For each branch: `ref = f"origin/{branch}"`; `lines = self._git.grep_fixed(clone, ref, MARKER_PREFIX)`; `todos = parse_grep_lines(repo, branch, ref, lines)`.
     - Per todo: read context for keep-instruction: `text = self._git.show_file(clone, ref, todo.file)` (GitError → log warning, `keep=False`); `context = text.splitlines()[max(0, todo.line - 1): todo.line - 1 + KEEP_CONTEXT_LINES + 1]` (marker line + next `KEEP_CONTEXT_LINES`); rebuild the todo with `keep = has_keep_instruction(context)` (frozen dataclass → `dataclasses.replace(todo, keep=...)`).
     - Sort the result deterministically: `(branch, file, line)`.
     - `GitError` mid-branch (e.g. a vanished ref) → log, skip that branch, continue.

  4. `def _lookup_pr(self, owner: str, name: str, branch_name: str) -> dict | None | str` — ONE `find_pr_by_head` call: returns the raw PR dict, or `None` (no PR), or the string `"api_error"` (a `GitHubError` — logged WARNING; guardrail: unknown → skip, never re-create). All PR-state consumption (classifier + pipeline) goes through this so each todo costs at most one API call per run (see the `pr_cache` in `run`).

  5. `def _process_todo(self, ctx, todo: Todo, test_cmd: str | None, clone: Path, cached_lookup: dict | None | str | object = _NOT_LOOKED_UP) -> dict` — one todo's full pipeline; returns an outcome dict `{"status": "pr_created" | "skipped" | "resolved" | "failed", "reason": str, "pr_number": int | None, "pr_url": str | None, "commit_sha": str | None}`. Module-level sentinel `_NOT_LOOKED_UP = object()` disambiguates "caller has no lookup" from "lookup found no PR". Steps (owner/name split once at top):
     1. **Existing-PR check:** `lookup = cached_lookup if cached_lookup is not _NOT_LOOKED_UP else self._lookup_pr(owner, name, branch_name)` — so each todo costs at most ONE API call per run (run passes the classifier's cached lookup for `pr_open`-derived todos). `lookup` is a PR dict, `None` (no PR), or `"api_error"`. Outcome: PR dict with `pr["state"] == "open"` → `skipped` ("PR already open #N"); PR dict with `pr["merged"] is True` → `resolved`; PR dict closed (unmerged) → continue (retry); `"api_error"` → `skipped` ("PR state unknown (API error) — guardrail"); `None` (no PR) → continue (fresh attempt or orphan resume below).
     2. **Orphan-branch resume:** `branch_name = todo.branch_name`; probe `self._git.rev_parse(clone, f"origin/{branch_name}")` — on success (remote branch exists, no PR) → create the PR directly: `commit_sha = <that sha>`; body note appended: `"(Branch reused from a previous run — the agent's committed fix was already pushed; no agent re-run.)"`; jump to step 7 with `sections = {}`.
     3. **Fresh attempt:** probe local branch `self._git.rev_parse(clone, branch_name)` → if it exists, `self._git.delete_branch(clone, branch_name)` (stale from a previous attempt). `wt = worktree_dir(ctx.sandbox_dir, todo.repo, todo.id)`; if `wt.exists()` → best-effort `self._git.worktree_remove(clone, wt, force=True)` then `shutil.rmtree(wt, ignore_errors=True)` + `self._git.prune_worktrees(clone)` (each wrapped: GitError → log warning, continue — a leaked dir must not brick the attempt). Then `self._git.worktree_add(clone, wt, branch_name, f"origin/{todo.branch}")`.
     4. **Agent:** `runner = self._runner_override or ctx.runner`; `brief = render_brief(ctx.run_id, todo, test_cmd)`; `res = runner.run(agent="oc-todo-resolver", brief=brief, work_dir=wt, title=f"oc-todo {todo.id} ({ctx.run_id})")`.
     5. **Agent gate:**
        - `res.status in {"error", "timeout"}` → `failed` (reason = `res.error or res.status`).
        - `res.status == "ok" and _is_step_exhausted(res.final_text)` → `failed` ("agent hit its step cap — no complete fix").
        - `sections = extract_report_sections(res.final_text)`; `sections["blockers"].strip().lower() not in ("", "none")` → `failed` (reason = first 200 chars of the blockers text) — an unverified fix is not PR'd.
     6. **Commit:** `self._git.add(wt)` (add -A); `created = self._git.commit(wt, render_pr_title(todo.marker))`; `created is False` → `failed` ("agent made no changes — nothing to commit"); `commit_sha = self._git.rev_parse(wt, "HEAD")`.
     7. **Push:** `self._git.push(wt, branch_name, upstream=True)` (GitError → `failed`, reason = the GitError message).
     8. **PR:** `number, url = self._github.create_pr(owner, name, title=render_pr_title(todo.marker), body=render_pr_body(todo, todo.repo, sections, ctx.run_id), head=f"{owner}:{branch_name}", base=todo.branch)` (GitHubError → `failed`).
     9. **Cleanup (ALWAYS — wrap steps 3–8 in try/finally):** `self._git.worktree_remove(clone, wt, force=True)`; on `GitError` → `self._git.prune_worktrees(clone)` best-effort + `shutil.rmtree(wt, ignore_errors=True)` + log WARNING (a leaked worktree is loud, not fatal; the next attempt re-cleans).
     - Any `GitError`/`GitHubError` in steps 2–8 → `failed` with the error message (never raise out of `_process_todo` for business failures).
  6. `def run(self, ctx) -> WorkflowResult` — the full orchestration (wrap in the mail-keeper `run`/`_run` pattern: unexpected exception → `status="error"`):
     1. `if not self._settings.repos:` → `WorkflowResult(status="ok", items_found=0, actions=["no repos configured — nothing to scan"])` (no state write).
     2. `st = ctx.state.load(_STATE_KEY)`; `err = validate_state(st)` → `WorkflowResult(status="error", errors=[err])`.
      3. Per repo (config order), sequential:
        a. `clone = self._clone_or_fetch(ctx, repo, errors)` → None → continue to next repo.
        b. `current = self._scan_repo(ctx, repo, clone)`.
        c. **PR-state lookups** for the subset of current todos whose state entry is `pr_open`: `pr_cache[tid] = self._lookup_pr(...)` (PR dict / `None` / `"api_error"`; one call each). Derive the classifier input `pr_states[tid]` = `pr_state_from_api(pr)` when dict, `"missing"` when `None`, `None` when `"api_error"`.
        d. `actions = plan_run(current, st, pr_states)`; process in order:
           - `action == "process"`: enforce the cap — `to_process = apply_cap(process_queue, self._settings.max_todos_per_repo)`; per processed todo: `test_cmd = self._settings.test_commands.get(repo)`; `outcome = self._process_todo(ctx, todo, test_cmd, clone, cached_lookup=pr_cache.get(todo.id))`; update the in-memory state doc per outcome:
             - `pr_created` → `make_entry(todo, "pr_open", pr_number=, pr_url=, commit_sha=, attempts=old+1, last_run_id=ctx.run_id)`
             - `skipped` → entry unchanged (refresh nothing)
             - `resolved` → `make_entry(todo, "resolved", ...)`
             - `failed` → `make_entry(todo, "failed", last_error=outcome["reason"], attempts=old+1, last_run_id=ctx.run_id)`
             - **Routing of outcome notes:** `pr_created`/`skipped`/`resolved` → `actions_out` (`f"PR #{number} for <repo> (<file>:<line>)"`, skip reason, resolve note); `failed` → **`errors`** (f-string with repo, file:line, and the reason) — per-todo failures are business errors: they must surface in `last-run.txt` (`overall: error`) and in the run's `errors`, while remaining retryable (state = `failed`).
           - `action == "skip"` → `actions_out` gets the skip reason (state unchanged).
           - `action == "resolve"` → state entry → `resolved`; `actions_out` note.
           - Unprocessed (cap) todos → stay at their previous status (absent stays absent); `actions_out` note `f"{n} todo(s) not processed this run (cap {cap})"`.
        e. Actions for vanished entries (from `plan_run`) → state → `resolved`; `actions_out` note.
     4. **Single atomic state save** at the end — but only if the state doc changed (compare against the loaded one; no-change runs — e.g. all skips — write nothing). `ctx.state.save(_STATE_KEY, st)`.
     5. Return `WorkflowResult(status="error" if errors else "ok", items_found=len(current markers total), actions=actions_out, errors=errors)`.
     - Logging: per-repo INFO line (repo, branches scanned, markers found), per-todo INFO/WARNING lines (outcome + reason). Keep the run log auditable (the whole point of this system).
- **Notes:** The `ctx.state` key is `_STATE_KEY = "oc-todo"`. `items_found` counts CURRENT markers (across all repos) — "todos found", mirroring mail-keeper's candidate count. Keep every method ≤ ~80 lines; extract small private helpers freely. The `run` docstring must state the idempotency contract (state consulted before acting; a re-run never duplicates a PR) and the failure contract (per-todo failures → `failed` state, retried next gate-open run; repo failures logged, other repos continue; the run itself returns `error` only on business-error accumulation).

### Task 3: `tests/test_oc_todo_pipeline.py`
- **Files:** `tests/test_oc_todo_pipeline.py` (create)
- **Do:** Hermetic integration tests — a fixture bare repo plays GitHub; fake agent + fake GitHub; drive `OCTodoWorkflow.run(ctx)` directly (NOT via `scheduler.run`).
  **Fixture helpers (module-level, mirror `tests/test_git.py`):**
  - Git identity: `os.environ.setdefault("GIT_AUTHOR_NAME", "Test Author")` + 3 sibling vars at import.
  - `_make_fixture_repo(tmp_path) -> tuple[Path, dict]`: working repo on `main` with `src/a.py` containing a marker line `# OC-todo: fix bug A in alpha()` (at a known line number) + a real function; branch `dev` (off main) adds `src/b.py` with `# OC-todo: fix bug B in beta()`; then `git clone --bare` to `<tmp>/remote.git` (or `init_bare` + push both branches; ensure `refs/heads/main` + `refs/heads/dev` exist in the bare repo). Return the bare path + a dict of known marker facts (repo string `"fixture/owner-repo"`, per-branch file/marker/line).
  - `FakeGitHub`: in-memory `prs: list[dict]`; `find_pr_by_head(owner, repo, head)` → first stored PR whose `head == f"{owner}:{head}"` else None; `create_pr(...)` → appends `{"number": n, "html_url": f"https://github.com/{owner}/{repo}/pull/{n}", "state": "open", "merged": False, "head": head, "base": base, "title": title, "body": body}` (n = len+1), returns `(n, url)`; helper `set_state(number, state, merged=False)` to flip `open`→`closed`/`merged`.
  - `FakeRunner(mode: str)`: `.run(agent=, brief=, work_dir=, title=)` → `AgentResult`. **It must simulate the agent's real work**: find the marker line in the worktree (search all text files under `work_dir` for `MARKER_PREFIX`), and per mode:
    - `"ok"`: delete the marker line (unless the brief says keep — parse the `Keep-instruction: yes` line), make a trivial code edit next to it (e.g. append a comment `# fixed by oc-todo-resolver`), return `AgentResult(status="ok", exit_code=0, final_text=<sample report>, events=[], duration_seconds=0.1)` where the sample report follows the skill's shape with `## Summary` ("Removed marker and fixed bug A..."), `## Files` table, `## Build / Tests` ("`pytest`" line or "not configured"), `## Blockers` = "None".
    - `"timeout"`: no file change, `AgentResult(status="timeout", exit_code=None, final_text=None, error="agent run exceeded 300s", ...)`.
    - `"step-exhausted"`: no file change, status `"ok"`, `final_text="maximum steps reached — partial work, see summary"`.
    - `"blockers"`: no file change, status `"ok"`, report with `## Blockers` = "- tests fail: 2 errors".
    - `"no-op"`: no file change, status `"ok"`, normal report.
    - Record every call (`self.calls` list of `(agent, brief, work_dir, title)`).
  - `make_ctx(tmp, cfg)`: build a `WorkContext` over the tmp workspace (real `StateStore`, `logging.getLogger("test.oc-todo")`, `run_id="test-run"`, `workflow_name="oc-todo"`, `sandbox_dir=tmp/sandbox`, `admin_repo=None`); config from a tmp YAML (repos `["fixture/owner-repo"]`, `repo_urls: {fixture/owner-repo: str(bare)}`, `test_commands` as the test needs) via `load_config`.
  - `make_wf(cfg, fake_gh, fake_runner)`: `OCTodoWorkflow(cfg.oc_todo, github=fake_gh, runner=fake_runner)`.
  **Tests (each maps to a high-level acceptance criterion — name them so):**
  1. `test_two_branches_two_prs` — fixture with the two markers on `main` + `dev`; one `run` → `result.status == "ok"`, exactly 2 PRs in `FakeGitHub`; PR A `base == "main"`, PR B `base == "dev"`; each `head == "fixture/owner-repo:oc-todo/<12hex>"`; each PR body contains the exact marker line verbatim, the file path, and the line number; state file `state/oc-todo.json` has both entries `pr_open` with `pr_number`/`pr_url`/`commit_sha`; the bare remote now has exactly 2 new refs, both matching `^refs/heads/oc-todo/[0-9a-f]{12}$`; no worktree dirs remain under `sandbox/oc-todo/wt` (cleanup). **[AC1]**
  2. `test_pr_diff_removes_marker` — after the run, fetch the pushed branch in a throwaway clone of the bare repo: `git grep` for the marker on `oc-todo/<id>` → empty (FakeRunner removed it); the commit on that branch is exactly 1 (agent's fix, committed by the runner) with message `OC: ...`. **[AC2 diff half]**
  3. `test_keep_instruction_preserves_marker` — fixture variant: the marker line in `dev`'s file has `(oc-original: keep this marker)` on the line below; run → PR B created; on the pushed branch the marker line is STILL present verbatim; the PR body says `Keep-instruction: yes`. **[AC2 keep half]**
  4. `test_rerun_opens_no_new_prs` — run twice (fresh FakeRunner each time) → `FakeGitHub.create_pr` called exactly twice total; second run `status == "ok"`, `items_found == 2`, actions mention the skips; state unchanged (both `pr_open`). **[AC3 first half]**
  5. `test_merge_resolves_todo` — after run 1: `fake_gh.set_state(prA, "closed", merged=True)` AND update the bare repo's `main` to remove the marker (commit on main in a scratch clone, push); re-run → state: todo A `resolved`, todo B still `pr_open`; zero new PRs. **[AC3 second half]**
  6. `test_agent_timeout_fails_and_retries` — FakeRunner `"timeout"` → run 1: `result.status == "error"` (a per-todo failure is a business error), the todo's state entry is `failed` with `last_error` mentioning the timeout, `result.errors` non-empty, no `oc-todo/*` ref pushed for it, worktree cleaned; run 2 with FakeRunner `"ok"` → PR created; state `pr_open`; `attempts == 2`. **[AC4 timeout half]**
  7. `test_step_exhausted_treated_as_failure` — FakeRunner `"step-exhausted"` → run 1: `result.status == "error"`, todo `failed` with reason mentioning the step cap, no push, no PR; run 2 `"ok"` → PR created, run 2 `status == "ok"`. **[AC4 steps half]**
  8. `test_blockers_report_fails_no_pr` — FakeRunner `"blockers"` → `result.status == "error"`, todo `failed` with reason containing the blocker text; no commit on any `oc-todo/*` branch (branch absent from the bare remote), no PR. **[blocker gate]**
  9. `test_cap_limits_and_drains` — fixture with 4 markers on `main` (4 files), config `max_todos_per_repo: 2` → run 1: exactly 2 PRs + action note about the 2 unprocessed; run 2: exactly 2 more PRs; run 3: zero. **[caps]**
  10. `test_only_fresh_branches_pushed` — across a full run, collect refs added to the bare remote: every new ref matches `^refs/heads/oc-todo/[0-9a-f]{12}$`; `main` and `dev` SHAs are byte-identical before/after the run. **[AC5]**
  11. `test_agent_no_op_fails` — FakeRunner `"no-op"` → `result.status == "error"`, todo `failed` with reason mentioning "no changes"; no PR. **[commit-False path]**
  12. `test_orphan_branch_resumes_without_agent` — pre-push a branch `oc-todo/<id>` to the bare repo (content: the fixed file, 1 commit); FakeRunner that raises if called; run → PR created (head = that branch, base = the todo's branch), body contains the orphan-branch note, `FakeRunner.calls == []`. **[orphan resume]**
- **Acceptance:**
  1. `uv run pytest tests/test_oc_todo_pipeline.py -v` — all 12 pass.
  2. `uv run pytest tests/ -v` — full suite green.
  3. `uv run ruff check src tests` — clean.
  4. No test touches the network or real `opencode` (grep the test file for `urlopen`/`opencode` invocations — only via fakes).

## Out of Scope
- No `create(config)` / no `workflows.yaml` registration (Task 5).
- No run()-level (`scheduler.run`) smoke tests (Task 5).
- No worktree/clone garbage collection beyond per-attempt cleanup (old clones persist in the sandbox — operator-managed).
- No rate-limit budgeting across repos (one PR check per `pr_open` todo per run is the only API traffic; creation is capped by the per-repo cap).

## Notes
- `[Decision]` Orphan branch (pushed, no PR) → PR directly, no agent re-run (see work_plan Notes).
- `[Decision]` Agent `## Blockers` ≠ "None" → todo fails, no PR.
- The fake agent editing real files in the worktree is what makes AC2 (diff removes the marker) meaningful — keep the fake's edit realistic (line removal, not whole-file rewrite).
- `shutil` for the best-effort `rmtree` fallback (stdlib).
- Watch the frozen `Todo`: use `dataclasses.replace` to set `keep`.
- One `find_pr_by_head` per `pr_open` todo per run — do not call the API twice for the same todo (plan_run's classifier consumes the `pr_states` dict built in run step 3c).

## Amendment (2026-11-15, post-implementation)

- **[Accepted deviation]** The scan skips non-source branches (`HEAD`, `origin`, and `oc-todo/*`): the `oc-todo/*` skip is load-bearing (without it, a re-run re-detects markers on the workflow's own fix branches — permanent for keep-instruction markers — and would open duplicate PRs); the spec's test fixture also surfaced spurious `origin`/`HEAD` entries in the bare-clone world. A user source branch literally named `oc-todo/...` would be skipped (accepted).
- **[Spec bug → fixed as Task 0 of Task 5]** This spec's test assertion `head == "fixture/owner-repo:oc-todo/<12hex>"` contradicted its own pipeline step (`head=f"{owner}:{branch}"`); the implementation followed the assertion, producing an INVALID GitHub head ref (`owner/name:branch` — the account part must be a single owner; GitHub rejects it with 422). The orchestrator verified the code; the correct fix (`head=f"{owner}:{branch}"` at both call sites + test/fake updates) is recorded as **Task 0 in `work_plan_task_5_integration.md`**.
