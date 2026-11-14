# Task Plan: Registration, smoke, README, final acceptance pass

**Purpose:** Ship the workflow: wire the `create(config)` entry point, register `oc-todo` in `config/workflows.yaml` (enabled, empty repo list), add run()-level hermetic smoke tests, document the workflow in the README, and prove every high-level acceptance criterion end-to-end.

**Task:** #5    **Session:** `planning/workflows-oc-todo/`    **Result file:** `planning/workflows-oc-todo/lightweight_dev_task_5_integration.md`

## Objective

The OC-todo workflow is registered, discoverable, and documented: `uv run agentic-scripts run --force --only oc-todo` exits 0 as a clean no-op with the empty shipped config (and would process the fixture world in tests); a gate-closed run touches nothing; the full suite + ruff are green; the README's "OC-todo workflow" section is accurate; and the result report carries the acceptance-criterion → test mapping table.

## Context

Project: `/workspace/Python/agentic_scripts` (Python ≥3.12, `uv`, src layout). Lint: `uv run ruff check src tests` (line-length 100, E/F/I/UP/W). Tests: `uv run pytest tests/ -v`. Do not commit/push — the orchestrator handles git.

**Depends on Tasks 1–4 (all landed when you start).** Read first:
- `src/agentic_scripts/workflows/oc_todo.py` — the finished workflow (Task 3+4): `OCTodoWorkflow` with `__init__(settings, *, git, github, runner)`, `run(ctx)`, all helpers. Add `create(config)` here.
- `src/agentic_scripts/workflows/mail_keeper.py` — `create(config)` pattern (returns the workflow instance; `config` accepted for contract uniformity).
- `config/workflows.yaml` — current shipped config (read it fully before editing; keep comments in the house style).
- `tests/smoke/test_smoke_base.py` — the run()-level smoke pattern to mirror: `_write_config` (tmp copy of the shipped config with tmp paths), `_workspace`, injected `now`/`load`/`run_id`, assertions on `logs/run-*.log` + `logs/last-run.txt` + state files.
- `tests/smoke/test_smoke_mail_keeper.py` — how a workflow-specific smoke file is structured (and how it keeps the LIVE world out via env/config pointing at tmp paths).
- `README.md` — especially the "Mail-keeper workflow" section (structure to mirror: What/how, config table, env vars, "How a run works" numbered list, operator commands, where outputs live, guardrails) and the "Extending with a new workflow" section (the workflow you are registering is the exemplar).
- The high-level plan `planning/workflows-oc-todo/workflows-oc-todo_plan.md` — the acceptance criteria (its "Acceptance criteria" list, 5 items) + Objective + Notes (for the README's guardrail/risk prose).
- The agent/skill contract (for README accuracy): `~/.config/opencode/agents/oc-todo-resolver.md` + `~/.config/opencode/skills/oc-todo-resolver/SKILL.md`.

## Tasks

### Task 1: `create(config)` entry point
- **Files:** `src/agentic_scripts/workflows/oc_todo.py` (modify)
- **Do:** `def create(config: Config) -> "OCTodoWorkflow"` — production wiring: `OCTodoWorkflow(settings=config.oc_todo)` (default `git`/`github` from the modules, `runner=None` → `ctx.runner` at call time). Docstring per the mail-keeper `create` pattern (the scheduler's entry point; import-check target for the enabled config entry).
- **Acceptance:**
  1. `python -c "import agentic_scripts.workflows.oc_todo as m; print(m.create)"` (via `uv run`) resolves — the module exposes `create` (what the config loader's import-check for enabled entries requires).
  2. `uv run pytest tests/ -v` — full suite green.

### Task 2: Register in `config/workflows.yaml`
- **Files:** `config/workflows.yaml` (modify)
- **Do:**
  1. Add the top-level `oc_todo` section (after `admin_repo`, before `workflows` — or anywhere top-level; keep the file's comment style):
     ```yaml
     oc_todo:
       repos: []                  # GitHub repos to scan ("owner/name"); empty = no-op scan
       max_todos_per_repo: 3      # max todos processed per repo per run
       test_commands: {}          # optional per-repo test command, e.g. { "owner/name": "uv run pytest" }
       repo_urls: {}              # optional clone-URL overrides per repo (local fixtures / mirrors)
     ```
  2. Add the workflow entry (after `mail-keeper`, preserving the existing entries verbatim):
     ```yaml
       oc-todo:
         enabled: true
         module: agentic_scripts.workflows.oc_todo
         agent: oc-todo-resolver
     ```
- **Acceptance:**
  1. `uv run python -c "from agentic_scripts.config import load_config, PROJECT_ROOT; c = load_config(PROJECT_ROOT/'config'/'workflows.yaml'); print([w.name for w in c.workflows], c.oc_todo.repos)"` prints `['noop', 'mail-keeper', 'oc-todo'] []` (the enabled-entry import-check passes → the module is importable and exposes `create`).
  2. `uv run pytest tests/ -v` — full suite green (the `base_config` fixture now loads a config containing the `oc-todo` entry — every base smoke test's forced run now ALSO executes `oc-todo` with 0 repos; they must stay green, which is itself a regression proof that the empty-repo path is side-effect-free).

### Task 3: Run()-level smoke tests
- **Files:** `tests/smoke/test_smoke_oc_todo.py` (create)
- **Do:** Mirror `test_smoke_base.py`'s patterns (tmp workspace, `_write_config`-style tmp config from the shipped YAML, injected clock/load, in-process `run()`):
  0. **Env isolation (MANDATORY first):** the shipped config has `mail-keeper` enabled — a forced `run()` would otherwise drive the LIVE mail-keeper (real notmuch index, real agent). This module needs its own autouse fixture exactly like `test_smoke_base._isolate_mail_env`: point `MAIL_INDEX_DB` at a nonexistent tmp path (→ mail-keeper returns `skipped`) and `MAIL_PROCESSED_LOG` at a tmp path, saving/restoring the originals. (This is load-bearing — the base smoke tests prove the same hazard.)
  1. `test_smoke_oc_todo_registered_noop` — forced run (`--force`) with the shipped config (tmp paths): exit 0; the run log contains `WORKFLOW oc-todo status=ok items_found=0 actions=1 errors=0` (exact counts per the no-repos path: 1 action, 0 items, 0 errors — assert on the run log, NOT `last-run.txt`, which only carries the FIRST workflow's summary — scheduler quirk, `workflow_summaries[0]`); `last-run.txt` has `trigger: force` and `overall: ok`; **no** `sandbox/oc-todo/` directory created; **no** `state/oc-todo.json` written (no-change run saves nothing).
  2. `test_smoke_oc_todo_gate_closed_noop` — gate-closed run (`now` outside the quiet window, e.g. `datetime(2026, 11, 14, 13, 0)`, low load): exit 0; `verdict=CLOSED` in the log; `overall: skipped`; no `sandbox/oc-todo/` dir, no `state/oc-todo.json` — *"with the gate closed, runs exit as no-ops without touching any repo"* (the objective's second half).
  3. `test_smoke_oc_todo_config_fault` — tmp config with a malformed `oc_todo` section (e.g. `repos: ["no-slash"]`): `run(["run", "--force", "--config", str(cfg)])` returns **2** and the config-error path prints the field name (`oc_todo.repos[0]`) on stderr (assert via `capsys`).
  4. `test_smoke_oc_todo_empty_repo_list_no_agent` (optional, cheap) — a tmp config with `oc_todo.repos: []` explicitly: forced run → `oc-todo=ok(0 items, ...)`; assert no `opencode` invocation is possible (the workflow returns before any runner access — proven by the absence of sandbox dirs + state).
  - **Do NOT** build a run()-level fixture-repo smoke test here (the hermetic pipeline proof lives in `tests/test_oc_todo_pipeline.py`, class-level with fakes — same split as mail-keeper: `test_smoke_mail_keeper.py` proves the base paths, `test_mail_keeper.py` proves the fixture world).
- **Acceptance:**
  1. `uv run pytest tests/smoke/ -v` — all smoke tests (base + mail-keeper + oc-todo) pass.
  2. `uv run pytest tests/ -v` — full suite green.

### Task 4: README section
- **Files:** `README.md` (modify)
- **Do:** Add an "## OC-todo workflow" section (place it after "Mail-keeper workflow", before "Extending with a new workflow") mirroring the mail-keeper section's structure. Content to cover (prose is yours — match the README's tone/density; every claim must be true of the shipped code):
  - **What/how (1–2 paragraphs):** scans the configured GitHub repos across **all branches** (local full clone + per-branch `git grep` — why: GitHub code search is default-branch-only, 384 KB file cap, 10 req/min), opens **one reviewable PR per unhandled `OC-todo:` marker** (strict, case-sensitive marker), the headless `oc-todo-resolver` agent edits code only in a sandboxed worktree while the Python runner owns git/PR mechanics; no auto-merge — humans review.
  - **Config table** (`oc_todo.*`): `repos`, `max_todos_per_repo` (default 3), `test_commands`, `repo_urls` — one row each, meaning + default.
  - **How a run works** (numbered): clone-or-fetch → per-branch scan → state diff (`pr_open`/`failed`/`resolved`; existing-PR check via REST) → per-todo worktree → agent (brief: marker/file:line/branch/test command/keep-instruction) → commit (`OC:` prefix) → push fresh `oc-todo/<id>` branch → PR (body quotes marker/file/line + agent report) → state persist; caps + retry-on-next-run.
  - **Idempotency:** state + existing-PR check; merged-and-removed markers flip to `resolved`; a GitHub API outage never re-creates a PR (skip + note).
  - **Keep-instruction:** `oc-original` markers keep the comment line verbatim.
  - **Operator commands:** `uv run agentic-scripts run --force --only oc-todo` (manual) / `uv run agentic-scripts run` (scheduled).
  - **Where outputs live:** PRs on GitHub; clones at `sandbox/oc-todo/clones/<owner>__<repo>`; worktrees (transient) under `sandbox/oc-todo/wt/`; state `state/oc-todo.json` (v1 schema, one-line description).
  - **Guardrails** (bullet list): fresh-branch-only pushes (every pushed branch is `oc-todo/<12-hex>`); per-repo per-run cap + agent step cap + hard timeout; per-todo failure → `failed` state, retried next gate-open run (never a partial push); API-outage skip guardrail; agent Blockers gate (no PR without a passing report); one PR per todo for human review (no auto-merge); `GITHUB_PAT` required only when repos are configured (cross-reference the existing env-var table).
  - **First-run note:** the shipped config has an empty `repos` list → the workflow is a no-op until repos are added (per the high-level plan's Notes).
  - If the "Extending with a new workflow" section still says `noop` is the only example, leave it (still accurate); do not rewrite other sections.
- **Acceptance:**
  1. The section exists, is factually consistent with the shipped config/code (spot-check: every config key, path, and command it names exists as documented), and follows the README's formatting (tables/bullets).
  2. `git diff README.md` shows additions only (no unrelated rewrites).

### Task 5: Final acceptance pass (the orchestrator re-verifies)
- **Files:** none (verification only)
- **Do:**
  1. `uv run pytest tests/ -v` — **full suite** green (record the count).
  2. `uv run ruff check src tests` — clean.
  3. Live no-op run (real env, real config, empty repos): `uv run agentic-scripts run --force --only oc-todo --verbose` → exit 0; `logs/last-run.txt` shows `oc-todo=ok(0 items, ...)`. Then `uv run agentic-scripts run` (gate path) → exit 0 (gate verdict either way; with 0 repos, no repo can be touched regardless).
  4. Fill the **acceptance mapping table** in your result report:
     | # | High-level acceptance criterion (verbatim from `workflows-oc-todo_plan.md`) | Proven by |
     |---|---|---|
     | 1 | two markers on two branches → exactly two PRs, each targeting its branch | `tests/test_oc_todo_pipeline.py::test_two_branches_two_prs` |
     | 2 | PR body quotes marker/file/line + summary; diff removes the comment unless keep-instruction | `::test_two_branches_two_prs` + `::test_pr_diff_removes_marker` + `::test_keep_instruction_preserves_marker` |
     | 3 | re-run opens zero new PRs; after merge, todo resolved, not reopened | `::test_rerun_opens_no_new_prs` + `::test_merge_resolves_todo` |
     | 4 | timeout/step-exhaustion → failed/retry state, reason logged, next run re-attempts | `::test_agent_timeout_fails_and_retries` + `::test_step_exhausted_treated_as_failure` |
     | 5 | only freshly created per-todo branches are pushed | `::test_only_fresh_branches_pushed` |
     | — | Objective: gate closed → no-op, touches nothing | `tests/smoke/test_smoke_oc_todo.py::test_smoke_oc_todo_gate_closed_noop` |
  5. If anything in the table does not yet pass, fix it (or report it as a Blocker — do not claim a PASS you did not verify).
- **Acceptance:**
  1. Full suite green + ruff clean (both commands, recorded output in the result report).
  2. Both live runs exit 0 with the documented `last-run.txt` contents.
  3. The result report contains the complete, honest acceptance mapping table.
  4. `git status` clean of unintended files (orchestrator commits).

## Out of Scope
- No changes to Tasks 1–4 code beyond the `create` function and the README.
- No real-GitHub dry run (no repos configured — by design; live verification is the no-op path only).
- No systemd/cron changes (the timer already fires `run`; registration is config-only).
- No `~/.config/opencode` changes (agent/skill already exist and are verified by `setup.sh`).

## Notes
- The base smoke tests now exercise `oc-todo` (0 repos) on every forced run — if any of them regresses, the empty-repo path has a side effect; fix the workflow, not the smoke assertion.
- `[Assumption]` `oc-todo` ships `enabled: true` with empty repos — reviewed at the plan GATE.
- README wording for the scan rationale must cite the same source as the high-level plan (GitHub REST search docs) — the plan already carries the URL; do not invent new claims.
- Keep the `last-run.txt` action-count assertions exact: the no-repos path emits exactly ONE action (`"no repos configured — nothing to scan"`).
