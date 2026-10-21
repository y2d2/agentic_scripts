# Task 3: Agent runner + git helpers

**Purpose:** Implement the two shared primitives every future workflow will call: `AgentRunner` (wraps `opencode run --format json` with hard timeout + NDJSON event capture + final-text extraction) and `Git` (thin, deterministic subprocess wrappers around the exact operations the OC-todo and mail-keeper workflows need).

## Objective

Deliver `src/agentic_scripts/agent.py` and `src/agentic_scripts/git.py` with hermetic tests (a fake `opencode` shim for the runner; a throwaway local repo/bare-remote for git) such that: (a) the runner builds the exact command line, streams and parses the verified NDJSON event schema, extracts the final assistant text, enforces the hard timeout without hanging, and maps exit codes to statuses; (b) the Git helper performs clone/fetch/branch-list/worktree-add-remove/commit/push round-trips correctly and reports failures with stderr tails instead of raising bare exceptions.

## Context

- **Repo:** `/workspace/Python/agentic_scripts`, branch `plan/agentic-workflows`. **Task 1 is already merged** (skeleton, `Config`/`WorkflowEntry` with `agent: str | None`, `StateStore`, `setup_run_logger`, `WorkContext`, `WorkflowResult`). Read `work_plan_task_1_foundation.md` for the shapes; `WorkContext.runner` lazily constructs `AgentRunner(config=self.config, logger=self.logger)` — **your constructor signature must match that exactly**.
- **Environment (re-verified 2026-10-20):** Ubuntu 24.04 container, Python 3.12.3, `uv` 0.12.5, `opencode` 1.18.35 installed (but tests MUST NOT invoke the real binary — fake shim only). git available. No `gh` CLI.
- **`opencode run --format json` (v1.18.35) — verified from the installed binary's source; full cache: `/workspace/Research/ai-agent-workflow/opencode-run-json-event-stream.md`:**
  - stdout is **pure NDJSON**, one object per line, no preamble, no ANSI. Each object: `{"type": <event>, "timestamp": ..., "sessionID": ..., ...type-specific payload}`.
  - Event `type` values: `tool_use`, `step_start`, `step_finish`, `text`, `reasoning` (only emitted with `--thinking`; we don't pass it), `error`.
  - **Final assistant text** = `part.text` of the **last** event with `type == "text"` (a run can emit several `text` events — earlier ones are intermediate).
  - **Exit 0 on success — including when the agent's `steps` cap is hit** (the cap produces a final `text` event with a "maximum steps reached"-style summary; there is no distinct cap event). Exit 1 for usage/API/session errors (details on stderr).
  - Flags we use (all verified against `opencode run --help`): `run` subcommand, `--agent <name>`, `--model <model>` (optional), `--dir <path>`, `--auto` (auto-approve tools), `--format json`, `--title <title>`, and one positional message (the brief) as the final argument.
- **Steps-cap contract (research: `/workspace/Research/ai-agent-workflow/agent-token-budget-steps.md`):** the agent frontmatter `steps: 40` (see `~/.config/opencode/agents/oc-todo-resolver.md`) is the sanctioned budget stop — at the cap the agent stops and writes its final text; the runner treats that as a normal `ok`. **Workflows** (not the runner) detect cap-style summaries in `final_text` and re-dispatch with fresh context. Note this in the `AgentRunner` docstring; implement no special-casing here.
- **Conventions:** Google-style docstrings, Ruff clean, hermetic tests only.
- **Parallel-safety:** you own ONLY `src/agentic_scripts/agent.py`, `src/agentic_scripts/git.py`, `tests/test_agent.py`, `tests/test_git.py`. Do NOT touch `pyproject.toml`, `config/workflows.yaml`, scheduler/cli/`__main__` (Task 2), `mail/` (Task 4), or Task 1 files. (Task 2 runs in parallel with you; do not import anything it owns — you don't need to.)

## Tasks

### 1. Create `src/agentic_scripts/agent.py`
- `@dataclass class AgentResult:` `status: str` (`"ok" | "error" | "timeout"`), `exit_code: int | None`, `final_text: str | None`, `events: list[dict]` (all parsed NDJSON objects, in order), `error: str | None`, `duration_seconds: float`.
- `class AgentRunner:`
  - `__init__(self, *, config: Config, logger: logging.Logger | None = None)` — store `self._config = config`; `self._log = logger or logging.getLogger("agentic_scripts.agent")`.
  - `def build_command(self, *, agent: str, brief: str, work_dir: Path, title: str | None = None) -> list[str]` — returns, in this exact order:
    `[config.agent.binary, "run", "--agent", agent, "--format", "json", "--dir", str(work_dir)]` + `["--title", title]` if title + `["--auto"]` if `config.agent.auto_approve` + `["--model", config.agent.model]` if `config.agent.model is not None` + `[brief]`. (Positional brief LAST.)
  - `def run(self, *, agent: str, brief: str, work_dir: Path, title: str | None = None, timeout_seconds: int | None = None) -> AgentResult`:
    1. `deadline = time.monotonic() + (timeout_seconds or config.agent.timeout_minutes * 60)`.
    2. `subprocess.Popen(cmd, stdout=PIPE, stderr=PIPE, start_new_session=True)` (own process group → killpg on timeout so child agents die too).
    3. Read stdout **line-by-line in binary**, decode `utf-8` with `errors="replace"`; each non-empty line → `json.loads` inside try/except: parsed → append to `events`, log a compact INFO line (`event <type> #<n>`); unparseable → log WARNING with the raw line (defensive; do not crash).
    4. Drain stderr in a daemon thread into a list (join before finishing); keep the **last ~40 lines** for error reporting.
    5. After stdout hits EOF: `proc.wait(timeout=10)`; if the process still refuses, killpg + reap.
    6. On `TimeoutExpired` (checked by wrapping the wait loop with the deadline; on breach): `os.killpg(os.getpgid(proc.pid), SIGKILL)`, reap, `status="timeout"`, `error=f"agent run exceeded {n}s"`, keep partial `events`/`final_text`.
    7. Status mapping: exit 0 + ≥1 `text` event → `ok`, `final_text` = last text event's `part.text`; exit 0 + no `text` event → `error`, `error="no final text event in stream"`; exit ≠ 0 → `error`, `error` = the `error`-event payload (stringified) if present, else the stderr tail.
    8. Log INFO `agent <agent> done status=... exit=... events=<n> duration=<s>s`.
  - Keep the class free of any repo/mail knowledge — pure process wrapper.
- Module docstring: one paragraph covering the verified event schema + the steps-cap note (see Context) + a pointer to the Research cache file.

### 2. Create `src/agentic_scripts/git.py`
- `class GitError(RuntimeError)` — message = `<op> failed (exit <code>): <stderr tail>`.
- `class Git:` thin wrapper; every method shells out with `subprocess.run([...], capture_output=True, text=True, timeout=...)` and raises `GitError` on non-zero exit. No `shell=True`, no `check=True`.
  - `is_repo(path: Path) -> bool` — `git -C <path> rev-parse --is-inside-work-tree` (False, not error, when not a repo).
  - `current_branch(path: Path) -> str` — `rev-parse --abbrev-ref HEAD`.
  - `rev_parse(path: Path, ref: str) -> str` — `rev-parse <ref>` (raises `GitError` for bad refs — workflows rely on this).
  - `clone(url: str, path: Path, *, depth: int | None = None) -> None` — `git clone [--depth N] <url> <path>` (parent dir must exist; `GitError` carries the stderr tail, e.g. auth failure).
  - `fetch(path: Path, remote: str = "origin") -> None`.
  - `branches(path: Path) -> list[str]` — `for-each-ref --format='%(refname:short)' refs/remotes/origin/`, strip the `origin/` prefix, drop `HEAD`, sorted.
  - `worktree_add(repo: Path, worktree_path: Path, new_branch: str, ref: str) -> None` — `git -C <repo> worktree add -b <new_branch> <worktree_path> <ref>`.
  - `worktree_remove(repo: Path, worktree_path: Path, *, force: bool = False) -> None` — `git -C <repo> worktree remove [--force] <worktree_path>`.
  - `add(path: Path, paths: list[str] | None = None) -> None` — `git -C <path> add -A` when `paths is None` else `add <paths...>`.
  - `commit(path: Path, message: str) -> bool` — `git -C <path> commit -m <message>`; **returns `False` (no raise) when there is nothing to commit** (detect `nothing to commit` in stderr/exit) — this is the idempotency primitive: a second run with no changes must not create an empty commit; else `True`.
  - `push(path: Path, branch: str, *, remote: str = "origin", upstream: bool = False) -> None` — `git -C <path> push [--set-upstream <remote>] <remote> <branch>`.
  - Every method: `cwd=None`, explicit `-C` where relevant, `timeout` (clone/fetch/push: 300s; others: 60s) → on timeout raise `GitError` (subprocess.TimeoutExpired wrapped).
- Module docstring: one paragraph — "thin, deterministic git plumbing for workflows; no branching policy, no PR logic (those live in the workflow layer); secrets (PATs) come from the environment, never from arguments."

### 3. Write `tests/test_agent.py` (fake `opencode` shim — no real binary, no LLM)
- Build the shim inside the test (tmp dir, `chmod +x`): a Python script that (a) writes its argv to a file (path passed via env `SHIM_ARGV`), (b) prints canned NDJSON to stdout based on env `SHIM_MODE` (`happy`: `tool_use`, `step_start`, `text` (interim `"thinking..."`), `step_finish`, `text` (final `"FINAL REPORT"`); `err`: one `error` event then exit 1; `notext`: `step_start`+`step_finish` only, exit 0; `sleep`: `text` event then `time.sleep(30)`, exit 0), (c) honors `SHIM_EXIT`.
- Run `AgentRunner` with a `Config` whose `agent.binary` = shim path (build a minimal `Config` in-test via `load_config` on a tmp YAML, OR construct the dataclasses directly — your choice; keep it deterministic).
- Tests:
  1. `build_command` exact list (default `auto_approve=True`, `model` set, title set; then a variant with `model=None`, `auto_approve=False`, no title — assert absence; brief always last).
  2. `happy` → `status ok`, `exit_code 0`, `final_text == "FINAL REPORT"` (last-text-wins: shim emits two `text` events, earlier `"thinking..."`), `len(events) == 5`.
  3. `err` → `status error`, `exit_code 1`, `error` contains the shim's error payload.
  4. `notext` → `status error`, `error == "no final text event in stream"`.
  5. `sleep` with `timeout_seconds=2` → `status timeout`, `duration_seconds < 10` (test itself runs in a few seconds, not 30), partial events present, and no orphan process group survives (assert via `os.killpg(..., 0)` raising `ProcessLookupError`).
  6. A deliberately malformed stdout line (shim variant `garbage`: prints `not-json` before a valid `text` event) → still `ok`, `events` contains the valid one (defensive parse).

### 4. Write `tests/test_git.py` (throwaway repos in `tmp_path` — no network, no real remotes)
- Setup helpers (in the test file): `init_repo(path, branch="main")` (init + a first commit with git identity env set in-test: `GIT_AUTHOR_NAME/EMAIL`, `GIT_COMMITTER_NAME/EMAIL`); `init_bare(path)`; `remote_url` = the bare repo's path (local-protocol clone — no auth).
- Set the identity env vars **at module import** of the test file (`os.environ.setdefault(...)`) so every git subprocess has an identity.
- Tests:
  1. `is_repo` true/false.
  2. `clone` the bare remote into a work dir → `current_branch == "main"`, `rev_parse` of the commit matches the source sha; `clone` with `depth=1` works.
  3. Push a new branch from the clone (`add`/`commit`/`push(branch, upstream=True)`) → `branches()` on a fresh `fetch`ed clone lists it; `commit` with no changes returns `False` (run commit again without new changes).
  4. `worktree_add` a `feature/x` branch at the current ref → worktree dir exists, `current_branch` inside it is `feature/x`; `worktree_remove` → dir gone; a second `worktree_remove` → `GitError`.
  5. `rev_parse(path, "definitely-not-a-ref")` → `GitError` whose message contains `failed (exit`.
  6. `commit` with staged changes returns `True` and the new sha ≠ old sha.

## Acceptance criteria

1. `uv run pytest tests/test_agent.py tests/test_git.py -v` — all pass; total suite wall time < 60s (timeout test ≤ ~10s); no test spawns the real `opencode` or touches the network.
2. `uv run ruff check .` + `uv run ruff format --check .` clean (whole repo).
3. `AgentRunner(config=..., logger=...)` keyword signature matches `WorkContext.runner` in Task 1's `base.py` exactly (verify by importing `WorkContext` in a `python -c` and constructing the runner via the lazy property with a tmp config — no `TypeError`).
4. `git status --porcelain` shows only this task's 4 files as new.
5. Committed with `OC:` prefix, pushed to `plan/agentic-workflows`.

## Out of Scope

- PR/branch-policy logic (OC-todo plan), mail (Task 4), CLI/scheduler (Task 2), setup/README (Task 5).
- Modifying agent definitions in `~/.config/opencode/agents/` (they exist and are owned by the oc_config repo).
- Retries, streaming-to-UI, token accounting — deliberately not here (see Context: steps cap is the budget knob; cap-summary detection belongs to workflow layers).

## Notes

- The shim file lives under `tmp_path` (or a `tests/`-local helper module if you prefer importability) — either way it must never be executed for real in CI: it is a test double, not a fixture with side effects.
- If `start_new_session=True` + `killpg` misbehaves under the container's cgroup limits, fall back to `proc.kill()` + a documented note in the result report — but try the process-group kill first (it is the correct fix for agent-spawned children).
- Keep `AgentRunner` import-safe: importing `agentic_scripts.agent` must not import `git`, `mail`, `scheduler`, or `cli` (parallel-safety; Tasks 2/4 run concurrently).
