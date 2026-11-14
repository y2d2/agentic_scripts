# Work Plan: OC-Todo Resolver Workflow (agentic_scripts)

**Purpose:** Implement the OC-todo resolver workflow: scan a configurable set of GitHub repos (all remote branches, via local full clone + per-branch `git grep`) for strict `OC-todo:` markers, and for every unhandled marker run the headless `oc-todo-resolver` agent in a sandboxed git worktree, commit the agent's fix, push a freshly-created per-todo branch, and open one reviewable PR per todo — idempotent across timer runs, gated by the scheduler, and a logged no-op (touching nothing) when the gate is closed or the repo list is empty.

## Objective

The high-level functional plan is `workflows-oc-todo_plan.md` (same directory). This work plan decomposes it into five tractable, testable tasks. End state:

1. `config/workflows.yaml` carries a new validated `oc_todo` section (repo list, per-run cap, per-repo test commands, clone-URL overrides) and registers the `oc-todo` workflow (enabled, empty repo list → safe no-op).
2. `agentic_scripts.github` provides a stdlib-only GitHub REST client (PAT from `GITHUB_PAT`) for the two operations the workflow needs: find-PR-by-head and create-PR.
3. `agentic_scripts.workflows.oc_todo` implements the full pipeline: clone-or-fetch → per-branch scan → state diff (pr_open/failed/resolved) → per-todo worktree → agent → commit → push → PR → state persist, with per-repo caps and retry-on-next-run failure semantics.
4. Hermetic test coverage for every acceptance criterion in the high-level plan (fixture bare repo, fake agent, fake GitHub — no network, no real `opencode`), plus run()-level smoke tests.
5. README documents the workflow (config keys, env, operator commands, outputs, guardrails).

Success = every high-level acceptance criterion maps to a passing test (mapping table in Task 5), the full suite + ruff are green, and a forced `--only oc-todo` run with the empty shipped config exits 0 as a no-op.

## Context (shared by all tasks)

**Repo & tooling.** `/workspace/Python/agentic_scripts` — load-aware agentic workflow scheduler. Python ≥3.12, `uv`, src layout (`src/agentic_scripts/`). Lint/format: `uv run ruff check src tests` (ruff: line-length 100, rules E/F/I/UP/W). Tests: `uv run pytest tests/ -v` (or a targeted file). **No new dependencies** — stdlib only for new modules. **Do not modify `pyproject.toml`.**

**Docstring convention (coding-standards skill).** Every module and public function/class carries a Google-style docstring with `Purpose:` / `Rationale:` (where non-obvious) / `Usage:` sections and typed Args/Returns/Raises — match the style of `config.py`, `state.py`, `git.py`, `workflows/mail_keeper.py` exactly (read one before writing).

**Existing primitives (read before coding; do not modify except the additive changes named per task):**

| Module | Relevance |
|---|---|
| `config.py` | `load_config` → frozen `Config` dataclass (fields: `machine`, `agent`, `paths`, `admin_repo`, `workflows`); `ConfigError(field, msg)` names the offending dotted field; `allowed_sections` set gates top-level keys; optional sections default when absent (see `admin_repo`). |
| `state.py` | `StateStore(state_dir)` — one JSON doc per workflow name; `load` (missing file → `{}`, corrupt → `StateError`), atomic `save`, `update`, `delete`. **Idempotency contract: consult state BEFORE acting.** |
| `scheduler.py` | `run()` assembles config → lock → gate → workflows. A workflow is imported by `entry.module`, called as `module.create(config)`, and run as `wf.run(ctx)`; failures are logged, never fatal. No changes here. |
| `agent.py` | `AgentRunner(config, logger).run(agent=, brief=, work_dir=, title=)` → `AgentResult(status ∈ ok|error|timeout, exit_code, final_text, events, error, duration_seconds)`. **A run that hits the agent's frontmatter `steps` cap exits 0** with step-exhaustion boilerplate as final text and is reported `ok` — the workflow must sentinel-detect it (see `mail_keeper._is_step_exhausted`). |
| `git.py` | `Git` stateless helper: `is_repo`, `current_branch`, `rev_parse` (raises `GitError` on bad ref), `clone(url, path, depth=)`, `fetch(path)`, `branches(path)` (sorted `origin/*` short names), `worktree_add(repo, path, new_branch, ref)`, `worktree_remove(repo, path, force=)`, `add`, `commit` (**returns False on nothing-to-commit** — the idempotency primitive), `push(path, branch, upstream=)`. All raise `GitError` with a stderr tail. |
| `workflows/base.py` | `Workflow` protocol: class attribute `name` + `run(ctx) -> WorkflowResult`. `WorkContext(config, state, logger, run_id, workflow_name, sandbox_dir, admin_repo)` with lazy `.git` / `.runner` properties. Contract: never raise for business failures — return `WorkflowResult(status=..., items_found=..., actions=..., errors=...)`. |
| `workflows/mail_keeper.py` | The in-repo pattern to mirror: module-level constants, private `_helper` functions, one class whose `run` wraps `_run` and maps unexpected exceptions to `status="error"`; state loaded once + validated + one atomic save at the end; step-exhaustion sentinel; hermetic tests with an injected fake agent (`tests/test_mail_keeper.py`). |

**The agent contract (already built — do not modify).** `~/.config/opencode/agents/oc-todo-resolver.md` + `~/.config/opencode/skills/oc-todo-resolver/SKILL.md`: leaf agent, `steps: 40`, launched as `opencode run --agent oc-todo-resolver --dir <worktree> "<brief>"`. The brief must carry: exact marker text, `file:line` hint, branch, test command (or "none"), keep-instruction flag. It edits code only — **never commits or pushes** (runner owns git), and its final message is the result report with sections `## Summary`, `## Files` (table), `## Build / Tests`, `## Acceptance Verification`, `## Blockers`.

**Test conventions.** Hermetic only: everything under `tmp_path`; a bare local repo plays "GitHub remote" (local-protocol clone — see `tests/test_git.py` helpers `init_repo`/`init_bare`/`_git`); git identity via `os.environ.setdefault("GIT_AUTHOR_NAME", ...)` etc. at test-module import (never clobber a real env); agents faked by injecting an `AgentRunner`-shaped object (never real `opencode`); GitHub API faked by injection (never network). The `base_config` fixture in `tests/conftest.py` loads the shipped config with paths redirected to tmp. **Smoke tests drive `run()` in-process** with injected `now`/`load`/`run_id` (see `tests/smoke/test_smoke_base.py`).

**Git discipline for dev agents.** Work on branch `plan/agentic-workflows` (current). **Dev agents do NOT commit or push** — the orchestrator commits (`OC:` prefix) and pushes after verifying each task's result. Never run destructive git commands.

**Session dir.** All inter-agent artifacts live in `planning/workflows-oc-todo/` (this directory). Result reports: `planning/workflows-oc-todo/lightweight_dev_task_<N>_<desc>.md` in the `sub-agent-communication` result-report format.

## Task Block A — parallel (no interdependencies)

### Task 1: Config extension — `oc_todo` section (→ `work_plan_task_1_config.md`)
Add the frozen `OCTodo` dataclass + `_load_oc_todo` validator to `config.py`; wire it into `Config` as an **optional** section (absent → empty defaults) and into `allowed_sections`. Extend `tests/test_config.py`.
Files: `src/agentic_scripts/config.py` (modify), `tests/test_config.py` (modify).

### Task 2: GitHub REST client (→ `work_plan_task_2_github_client.md`)
New stdlib-only module `src/agentic_scripts/github.py`: `GitHubError`, `GitHubClient` with `find_pr_by_head` and `create_pr` (urllib, PAT from `GITHUB_PAT`, injectable `_urlopen` seam). New `tests/test_github.py`.
Files: `src/agentic_scripts/github.py` (create), `tests/test_github.py` (create).

## Task Block B — sequential (after Block A; each depends on its predecessors)

### Task 3: oc_todo core + `git.py` additions (→ `work_plan_task_3_oc_todo_core.md`, depends on #1 and #2 — `OCTodoWorkflow.__init__` wires the default `GitHubClient`)
Additive `git.py` methods (`clone`/`fetch` env-override, `grep_fixed`, `show_file`, `delete_branch`). New `workflows/oc_todo.py`: `Todo` dataclass, todo identity/branch naming, grep-line parser, keep-instruction detection, state schema (v1) + decision classifier (`plan_run`), brief/PR-title/PR-body renderers, section parser, step-exhaustion sentinel, `clone_env_for`, cap helper, `OCTodoWorkflow.__init__`. New `tests/test_oc_todo.py` (pure logic + real-git helper tests).
Files: `src/agentic_scripts/git.py` (modify, additive), `src/agentic_scripts/workflows/oc_todo.py` (create), `tests/test_oc_todo.py` (create).

### Task 4: Per-todo pipeline + hermetic integration tests (→ `work_plan_task_4_oc_todo_pipeline.md`, depends on #2, #3)
`Git.prune_worktrees`; `OCTodoWorkflow._scan_repo`, `_process_todo` (PR check → orphan-branch resume → worktree → agent → commit → push → PR → worktree cleanup), and `run()` orchestration (clone-or-fetch per repo, state diff, caps, single atomic state save, result aggregation). New `tests/test_oc_todo_pipeline.py` — fixture bare repo (2 branches, 2+ markers), fake agent + fake GitHub, 10 integration tests covering every high-level acceptance criterion.
Files: `src/agentic_scripts/git.py` (modify, additive), `src/agentic_scripts/workflows/oc_todo.py` (modify), `tests/test_oc_todo_pipeline.py` (create).

### Task 5: Registration, smoke, README, final acceptance pass (→ `work_plan_task_5_integration.md`, depends on #4)
`create(config)` entry point; `config/workflows.yaml` registration (`oc_todo` section + `oc-todo` workflow entry, enabled, empty repos); `tests/smoke/test_smoke_oc_todo.py` (run()-level: registered no-op with empty repos, gate-closed no-op, config-fault exit 2); README "OC-todo workflow" section; full-suite + ruff + live `--force --only oc-todo` verification; acceptance-mapping table.
Files: `src/agentic_scripts/workflows/oc_todo.py` (modify), `config/workflows.yaml` (modify), `tests/smoke/test_smoke_oc_todo.py` (create), `README.md` (modify).

## Out of Scope

- No changes to scheduler, agent runner, state store, logging, or CLI (base primitives are final).
- No auto-merge, no PR closing, no issue creation, no GitHub Actions; `gh` CLI is not used (not installed — REST API only, per the high-level plan).
- No matching of non-canonical markers (`oc-todo` lowercase, `#OC-todo` without colon) — intentional pruning of stale markers (user decision 2026-10-14).
- No runtime repo-list changes (config-driven only); no cross-repo todo de-duplication; no worktree/clone GC beyond per-attempt cleanup.
- No changes to mail-keeper behavior or to `~/.config/opencode` (agent/skill already exist).
- No `pyproject.toml` changes (stdlib only).

## Notes

- **[Decision]** Config mechanism = new `oc_todo` **YAML section** (not env vars): per-repo test commands are structured data (a mapping), the project principle is fail-fast declarative config, and `repo_urls` gives a clean hermetic-test seam (fixture repos via local paths) that env vars cannot express. Mirrors how `admin_repo` is an optional top-level section.
- **[Decision]** Todo identity = `sha1("{repo}|{branch}|{file}|{marker}")[:12]`; branch name `oc-todo/<todo_id>` (fresh-branch invariant: pushed branches always start with `oc-todo/`). Two *identical* markers in one file collapse to one todo — pathological, accepted.
- **[Decision]** API-outage guardrail: if the PR-state lookup fails (network/rate-limit), a `pr_open` todo is **skipped with an error note, never re-processed** — a GitHub outage must not cause duplicate PRs. A `pr_open` entry whose recorded PR no longer exists (human closed+deleted) is re-verified (re-processed).
- **[Decision]** Per-todo failures are business errors: they land in the run's `errors` (→ `overall: error` in `last-run.txt`) AND in the `failed` state (retried next gate-open run) — surfaced and recoverable.
- **[Decision]** Orphan branch (pushed by a previous crashed run, no PR yet): create the PR directly against the pushed branch — it contains a complete, committed, agent-reported fix; no agent re-run.
- **[Decision]** Agent-reported `## Blockers` (anything but "None") → todo fails (no commit/push/PR): an unverified fix is not PR'd.
- **[Assumption]** Keep-instruction detection: the marker line or any of the **next 3 lines** contains `oc-original` (case-insensitive) → the marker line is kept verbatim (per the `oc-original` convention observed in local repos).
- **[Assumption]** Shipped config registers `oc-todo` **enabled with an empty repo list** → safe no-op until the operator adds repos; cap default `max_todos_per_repo = 3`.
- **[Decision]** `state/oc-todo.json` v1 schema `{version: 1, todos: {<todo_id>: entry}}`; statuses `pr_open` / `failed` / `resolved` (absent entry = pending); schema mismatch = hard error telling the operator to delete the file (mail-keeper pattern).
- **[Decision]** Step-exhaustion sentinel is **duplicated** (6 lines) into `oc_todo.py` rather than imported cross-workflow — keeps workflow modules decoupled.
- **[Risk]** Agent quality: a bad "fix" PR is caught in human review (that is the one-PR-per-todo design).
- **Research pointer:** scan decision source — GitHub REST code search is default-branch-only, 384 KB file cap, 10 req/min authenticated (https://docs.github.com/en/rest/search/search; cited in the high-level plan).
