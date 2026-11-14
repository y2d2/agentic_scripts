# Task Plan: oc_todo core (scan parse, identity, state, renderers) + `git.py` additions

**Purpose:** Build the pure, testable core of the OC-todo workflow — marker scan parsing, todo identity, state schema and the run-planning decision table, brief/PR renderers — plus the additive `git.py` methods the scan and pipeline need.

**Task:** #3    **Session:** `planning/workflows-oc-todo/`    **Result file:** `planning/workflows-oc-todo/lightweight_dev_task_3_oc_todo_core.md`

## Objective

After this task, `agentic_scripts.workflows.oc_todo` contains every helper the pipeline needs (each independently unit-testable), and `git.py` can grep a branch ref, read a file at a ref, delete a local branch, and pass auth env to clone/fetch. No orchestration logic (`run`) yet — that lands in Task 4.

## Context

Project: `/workspace/Python/agentic_scripts` (Python ≥3.12, `uv`, src layout). Lint: `uv run ruff check src tests` (line-length 100, E/F/I/UP/W). Tests: `uv run pytest tests/ -v`. No new dependencies. Do not commit/push — the orchestrator handles git.

**Depends on Task 1 (already landed when you start):** `agentic_scripts.config` exposes frozen `OCTodo(repos, max_todos_per_repo, test_commands, repo_urls)` and `Config.oc_todo`. Read `src/agentic_scripts/config.py` for the exact shapes.

Read first:
- `src/agentic_scripts/git.py` — the class you are extending (stateless, argv-list subprocess calls, `GitError` with stderr tail, `_TIMEOUT_LOCAL=60` / `_TIMEOUT_REMOTE=300`).
- `tests/test_git.py` — throwaway-repo test style: `init_repo`, `init_bare`, `_git` helpers, git identity via `os.environ.setdefault(...)` at module import.
- `src/agentic_scripts/workflows/mail_keeper.py` — the in-repo style to mirror: module docstring (Purpose/Rationale/Usage), module-level constants with `#:` doc-comments, private `_helper` functions, one class per workflow.
- `src/agentic_scripts/agent.py` — `AgentResult` (Task 4's pipeline consumes it; you only duplicate the step-exhaustion sentinel).
- The agent/skill contract (do not modify): `~/.config/opencode/agents/oc-todo-resolver.md` + `~/.config/opencode/skills/oc-todo-resolver/SKILL.md` — the brief inputs (marker text, file:line hint, branch, test command, keep-instruction flag) and the report shape (`## Summary`, `## Files`, `## Build / Tests`, `## Acceptance Verification`, `## Blockers`) are load-bearing.
- Docstring convention: Google-style, `Purpose:` / `Rationale:` / `Usage:`, typed Args/Returns/Raises.

## Tasks

### Task 1: Additive `git.py` methods
- **Files:** `src/agentic_scripts/git.py` (modify — additions only)
- **Do:**
  1. `clone(self, url, path, *, depth: int | None = None, env: dict[str, str] | None = None)`: add the keyword-only `env` param — when given, subprocess runs with `{**os.environ, **env}` (import `os`). Document: used to inject git auth config env (`GIT_CONFIG_*`) so PATs never appear in argv. No other behavior change (existing callers in `tests/test_git.py` keep working — verify).
  2. `fetch(self, path, remote: str = "origin", *, prune: bool = True, env: dict[str, str] | None = None)`: add `--prune` when `prune` (stale remote-tracking refs disappear when deleted upstream), plus the `env` param as in `clone`. Update the method docstring. The only existing caller is `tests/test_git.py:143` (`git.fetch(fresh)`) — local bare remote, prune is harmless; re-run that test to confirm.
  3. `grep_fixed(self, repo: Path, ref: str, pattern: str, *, exclude_standard: bool = True) -> list[str]`:
     - Runs `git -C <repo> grep -n -F -I -e <pattern> [--exclude-standard] <ref>`.
     - Exit 0 → `proc.stdout.splitlines()`; **exit 1 → `[]`** (git grep's "no match" code — NOT an error); any other exit → `GitError` (via `_check`).
     - `-F` fixed string, `-I` ignore binary files, `--exclude-standard` respects .gitignore (the "standard binary/build exclusions" from the high-level plan).
     - Returns raw output lines of the shape `<ref>:<file>:<line>:<content>`.
  4. `show_file(self, repo: Path, ref: str, path: str) -> str`: `git -C <repo> show <ref>:<path>` → stdout (minus trailing newline). `GitError` on missing path/ref.
  5. `delete_branch(self, path: Path, branch: str, *, force: bool = True) -> None`: `git -C <path> branch -D <branch>` (`-d` when `force=False`). `GitError` propagates (caller pre-checks existence via `rev_parse`).
- **Notes:** All new params are keyword-only with defaults — zero behavior change for existing calls. Timeouts: `grep_fixed`/`show_file`/`delete_branch` → `_TIMEOUT_LOCAL`; `clone`/`fetch` keep `_TIMEOUT_REMOTE`.

### Task 2: `src/agentic_scripts/workflows/oc_todo.py` — constants, dataclasses, pure helpers
- **Files:** `src/agentic_scripts/workflows/oc_todo.py` (create)
- **Do:**
  1. Module docstring (Purpose/Rationale/Usage): scan model (local full clone + per-branch `git grep`; why — GitHub code search is default-branch-only, 384 KB cap, 10 req/min), one-PR-per-todo, runner-owns-git split with the `oc-todo-resolver` agent, idempotency model (state + existing-PR check), pointer to the high-level plan `planning/workflows-oc-todo/workflows-oc-todo_plan.md`.
  2. Constants:
     - `MARKER_PREFIX = "OC-todo:"` — strict, case-sensitive canonical marker (user decision 2026-10-14; lowercase/`#OC-todo` variants deliberately NOT matched).
     - `_STATE_KEY = "oc-todo"`, `_STATE_VERSION = 1`.
     - `DEFAULT_MAX_TODOS_PER_REPO = 3` (mirror of the config default, for direct-construction tests).
     - Sandbox layout: `_CLONES_SUBDIR = "clones"`, `_WT_SUBDIR = "wt"` — clone at `<sandbox>/oc-todo/clones/<owner>__<repo>`, worktree at `<sandbox>/oc-todo/wt/<owner>__<repo>/<todo_id>` (helpers below).
     - `KEEP_CONTEXT_LINES = 3` — keep-instruction scan window below the marker line.
  3. Pure helpers (each docstring-complete):
     - `repo_slug(repo: str) -> str` — `repo.replace("/", "__")` (`owner/name` → `owner__name`).
     - `clone_dir(sandbox_dir: Path, repo: str) -> Path` and `worktree_dir(sandbox_dir: Path, repo: str, todo_id: str) -> Path` — the two layout paths above.
     - `todo_id(repo: str, branch: str, file: str, marker: str) -> str` — `hashlib.sha1(f"{repo}|{branch}|{file}|{marker}".encode("utf-8")).hexdigest()[:12]`.
     - `todo_branch_name(tid: str) -> str` — `f"oc-todo/{tid}"` (fresh-branch invariant: pushed branches always start `oc-todo/`).
     - `@dataclass(frozen=True) Todo`: `repo: str`, `branch: str`, `file: str`, `line: int`, `marker: str` (the exact marker line content, verbatim), `keep: bool = False`; property `id -> str` (`todo_id(...)`), property `branch_name -> str`.
     - `parse_grep_lines(repo: str, branch: str, ref: str, lines: list[str]) -> list[Todo]`:
       - Each input line is `<ref>:<file>:<line-no>:<content>` (from `Git.grep_fixed` against `ref = f"origin/{branch}"`).
       - Parse with regex `f"^{re.escape(ref)}:(.+):(\d+):(.*)$"` (greedy file part — handles `:` inside file paths; see plan Notes).
       - Keep only lines whose **content** contains `MARKER_PREFIX` (re-check — grep already filtered, this is defense in depth); store `marker` = the content (rstrip trailing newline/whitespace, otherwise verbatim — no stripping of leading comment chars).
       - `keep=False` here (the scanner in Task 4 sets it from file context).
       - Unparseable lines: skip (do not raise — a ref with an odd path should not kill the scan).
     - `has_keep_instruction(context_lines: list[str]) -> bool` — True iff any line contains `"oc-original"` (case-insensitive). The `context_lines` = the marker line plus the next `KEEP_CONTEXT_LINES` lines (Task 4 builds them via `Git.show_file`).
     - `pr_state_from_api(pr: dict) -> str` — maps a GitHub PR object to `"merged"` (`pr["merged"] is True`), else `"open"`/`"closed"` (from `pr["state"]`; default `"closed"` when the key is odd).
     - `clone_env_for(pat: str | None) -> dict[str, str] | None` — None when no PAT; else the git-env auth triple so the PAT never appears in argv:
       `{"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "http.extraHeader", "GIT_CONFIG_VALUE_0": f"Authorization: Bearer {pat}"}`.
  4. State schema (v1) helpers:
     - `fresh_state() -> dict` — `{"version": 1, "todos": {}}`.
     - `validate_state(st: dict) -> str | None` — None when `st == {}` (first run); error string otherwise iff `st.get("version") != 1` or `st.get("todos")` is not a dict. Error messages must contain `"state schema mismatch"` and `"delete state/oc-todo.json"` (mail-keeper pattern — the operator deletes the file to re-bootstrap).
     - Todo entry statuses (document in the module docstring): **absent** = pending; `"pr_open"` (fields: `repo, branch, file, line, marker, branch_name, pr_number, pr_url, commit_sha, attempts, last_run_id, updated_at`); `"failed"` (same minus PR fields + `last_error`); `"resolved"` (same as pr_open, terminal). Entry helper: `make_entry(todo: Todo, status: str, **fields) -> dict` (stamps `updated_at` UTC ISO-8601 + `attempts` default 0).
     - **The decision table** — `plan_run(current: list[Todo], st: dict, pr_states: dict[str, str | None]) -> list[dict]`:
       Pure classifier. `pr_states` maps `todo_id → "open" | "merged" | "closed" | "missing" | None` (`"missing"` = the recorded PR no longer exists — human closed+deleted; `None` = API lookup failed; only needed for `pr_open` todos — callers look up only those). Returns one action dict per current todo + one per vanished state entry:
       - **Current todo**, entry absent or status `"failed"` → `{"action": "process", "todo": todo}`.
       - **Current todo**, entry `"pr_open"`: pr_state `"open"` → `{"action": "skip", ..., "reason": "PR already open"}`; `"merged"` → `{"action": "resolve", ...}`; `"closed"` → `{"action": "process", ..., "reason": "PR closed unmerged — retry"}`; `"missing"` → `{"action": "process", ..., "reason": "recorded PR no longer exists — re-verify"}`; `None` → `{"action": "skip", ..., "reason": "PR state unknown (API error) — guardrail: no re-creation"}`.
       - **Current todo**, entry `"resolved"` → `{"action": "process", ..., "reason": "marker reappeared after resolution — re-attempt"}`.
       - **State entry whose todo is NOT in current** (marker gone — merged+removed or manually deleted) → `{"action": "resolve", "entry_id": tid, "reason": "marker no longer present"}` (all statuses).
       - Action dict fields: `action`, plus `todo` (for current) or `entry_id`/`entry` (for vanished), plus optional `reason`.
  5. Renderers (byte-stable formats — the agent reads the brief by eye; the PR body is human review surface):
     - `render_brief(run_id: str, todo: Todo, test_cmd: str | None) -> str` — **exact** format (one block, no extra blank lines):
       ```
       oc-todo-resolver run <run_id> — resolve exactly ONE OC-todo marker in this sandboxed worktree.

       Marker: <todo.marker verbatim>
       Location: <todo.file>:<todo.line>  (hint — locate the marker by its exact text; the line may have moved)
       Branch: <todo.branch>
       Test command: <test_cmd or none>
       Keep-instruction: <yes — implement the todo but leave the marker line verbatim | no — implement the todo and remove the marker line exactly>

       Follow skill: oc-todo-resolver (fix loop, marker rules, report shape).
       Do NOT run git commit or git push — the runner owns git and will commit, push, and open the PR after you exit.
       Your final message must be the result report (Summary / Files / Build / Tests / Acceptance Verification / Blockers).
       ```
     - `render_pr_title(marker: str) -> str` — `"OC: " +` the marker with the leading `MARKER_PREFIX` removed, whitespace-collapsed, truncated to 72 chars (no ellipsis; cut at char 72).
     - `extract_report_sections(final_text: str | None) -> dict` — best-effort parse of the agent's result report: `{"summary": str, "files": str, "tests": str, "blockers": str, "has_report": bool}`. Section = text between `## Summary` (or `## Files`, `## Build / Tests`, `## Blockers`) and the next `## ` heading, stripped. `blockers` is the section text lowercased-compared against `"none"` by the caller. Missing sections → `""`. None/empty input → all empty + `has_report=False`.
     - `render_pr_body(todo: Todo, repo: str, sections: dict, run_id: str) -> str` — **exact** format:
       ```
       ## OC-todo resolution

       - **Repo:** `<repo>`
       - **Base branch:** `<todo.branch>`
       - **Marker (verbatim):**

       ```
       <todo.marker>
       ```

       - **Location:** `<todo.file>` line `<todo.line>`
       - **Keep-instruction:** <yes|no>

       ## Agent summary

       <sections["summary"] or "(agent report unavailable)">

       ## Files changed

       <sections["files"] or "-">

       ## Tests

       <sections["tests"] or "-">

       ---
       *Opened automatically by agentic_scripts (run `<run_id>`). The marker was found on branch `<todo.branch>` by the scheduled scan. Review before merging; merging removes the marker (unless a keep-instruction applies).*
       ```
       (Inner triple-backtick fence around the marker — the whole body is rendered with a plain string build; ensure the marker fence uses triple backticks and the body has no other fence conflicts.)
     - `_is_step_exhausted(final_text: str | None) -> bool` — **duplicate** (do not import) the 6-line mail-keeper sentinel: True iff `final_text.lower()` contains `"maximum steps reached"` or `"maximum number of steps allowed"` (see `workflows/mail_keeper.py`; add a one-line comment pointing at the origin and why it's duplicated: no cross-workflow imports).
     - `apply_cap(todos: list[Todo], cap: int) -> tuple[list[Todo], list[Todo]]` — first `cap` (in the given order — caller sorts deterministically) → `(to_process, not_processed)`.
  6. `class OCTodoWorkflow` (shell only in this task — `run` lands in Task 4):
     - Class attribute `name = "oc-todo"`.
     - `__init__(self, settings: OCTodo, *, git=None, github=None, runner=None)`: `settings` = the `config.OCTodo`; `git` defaults to `Git()` (import from `agentic_scripts.git`); `github` defaults to `GitHubClient()` (import from `agentic_scripts.github` — Task 2 module); `runner` may be None → resolved from `ctx.runner` at call time (Task 4). Store as `self._settings / self._git / self._github / self._runner_override`.
     - Docstring: constructor injection is the hermetic-test seam (fakes for `git`/`github`/`runner`); production wiring via `create()` (Task 5).
- **Notes:** No I/O in any pure helper. No `run` method yet (adding a broken stub is worse than an absent one — Task 4 adds it).

### Task 3: `tests/test_oc_todo.py`
- **Files:** `tests/test_oc_todo.py` (create)
- **Do:** Hermetic. Two groups:
  **A. Pure logic (no git):**
  1. `todo_id` stable across calls; distinct for different (repo/branch/file/marker); 12 hex chars. `todo_branch_name("abc123def456") == "oc-todo/abc123def456"`.
  2. `parse_grep_lines`: exact-shape line → correct `Todo` fields; content with `:` inside the file path (e.g. `origin/dev:src/a:b.py:7:OC-todo: x`) parses with file `src/a:b.py`; content without the marker prefix is dropped; non-integer line numbers skipped; `keep` is False.
  3. `has_keep_instruction`: marker line with `(oc-original: keep this marker)` → True; `OC-ORIGINAL` (case) → True; plain marker + 3 clean lines → False; `oc-original` on the 3rd context line → True.
  4. **Decision table** — parametrize `plan_run` over the FULL matrix: entry status ∈ {absent, pr_open, failed, resolved} × pr_state ∈ {open, merged, closed, missing, None} (pr_state only consulted for pr_open — the non-pr_open statuses are each one case) = 8 current-todo cells, per the table in Task 2.4; plus 2 vanished-entry cases (pr_open and failed → `resolve`).
  5. `render_brief`: assert the exact header line, `Marker:` line carries the verbatim marker, `Test command: none` vs a real command, keep yes/no wording (two sub-cases).
  6. `render_pr_title`: prefix stripped, whitespace collapsed, 72-char truncation (feed a 200-char marker).
  7. `extract_report_sections`: a full sample report (use the skill's report shape) → all four sections extracted; report missing `## Blockers` → `""`; `None` → `has_report=False`.
  8. `render_pr_body`: marker appears verbatim inside the fence; `Location:` line carries file + line; base branch; run id in footer; `sections` empty → fallbacks `"(agent report unavailable)"` / `"-"`.
  9. `_is_step_exhausted`: both boilerplate phrases (any case) → True; normal report → False; None → False.
  10. `apply_cap`: cap 2 over 4 todos → split 2/2; cap 5 over 2 → all processed.
  11. `clone_env_for`: PAT → exact 3-key dict with `http.extraHeader` value; None/`""` → None.
  12. `validate_state`: `{}` → None; `{"version": 1, "todos": {}}` → None; `{"version": 2, ...}` → error containing `"state schema mismatch"` + `"delete state/oc-todo.json"`; `{"version": 1, "todos": [1]}` → error.
  **B. Real-git helper tests** (mirror `tests/test_git.py`: `init_repo`/`init_bare`/`_git`, identity via `os.environ.setdefault`):
  13. `grep_fixed`: repo with `OC-todo: alpha` on `main` and a different marker on branch `side` → `grep_fixed(repo, "origin/main", "OC-todo:")` after clone returns exactly the `origin/main:...` line; branch with no marker → `[]` (exit-1 path); a binary file (write bytes) containing the marker bytes is NOT returned (`-I`); a .gitignored text file containing the marker is NOT returned (`--exclude-standard`).
  14. `show_file`: returns the file content at `origin/main`; missing path → `GitError`.
  15. `delete_branch`: creates a local branch, deletes it, `rev_parse` now raises `GitError`.
- **Acceptance:**
  1. `uv run pytest tests/test_oc_todo.py -v` — all pass.
  2. `uv run pytest tests/ -v` — full suite green (including `tests/test_git.py` after the `git.py` additions).
  3. `uv run ruff check src tests` — clean.

## Out of Scope
- No `run()` orchestration, no clone/fetch loop, no agent invocation, no state persistence (Task 4).
- No `create(config)` entry point (Task 5).
- No changes to `scheduler.py`, `agent.py`, `state.py`, `workflows/base.py`, mail-keeper.

## Notes
- `[Decision]` Todo identity collapses duplicate identical markers in one file (sha1 over repo|branch|file|marker) — pathological, accepted (see work_plan Notes).
- `[Decision]` `pr_state = None` (API failure) on a `pr_open` todo → skip, never re-process (API-outage guardrail).
- `[Assumption]` Keep-instruction = `oc-original` (case-insensitive) in the marker line or the next 3 lines.
- `re` import for the grep-line regex; `hashlib` for `todo_id` — both stdlib.

## Amendment (2026-11-14, post-implementation)

- **[Amendment]** `render_pr_title` as originally specified ("strip the leading `MARKER_PREFIX`") leaves comment decoration behind for the typical marker shape (`# OC-todo: ...` → `OC: # OC-todo: ...`). Correct semantics — implemented as **Task 0 of `work_plan_task_4_oc_todo_pipeline.md`**: strip leading comment decoration (`#`/`//`/`;`/`%`/`--` + whitespace), then the `OC-todo:` prefix, then collapse + truncate. The PR body still quotes the marker verbatim (unchanged); only the PR title and commit message are affected.
- **[Accepted deviation]** `grep_fixed` does not pass `--exclude-standard` when grepping a ref (git exits 128 for tracked contents — verified by the dev and re-verified by the orchestrator). The param stays (inert, documented); binary exclusion is carried by `-I`. Task 4 must not rely on that flag.
