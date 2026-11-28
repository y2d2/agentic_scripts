# Task Plan: Engine package scaffold in overview repo

**Purpose:** Stand up the standalone `autonomous-task` uv project in the overview repo
(primitives, trimmed config, new single-workflow runner, CLI) so the package imports and
the CLI works before the workflow and tests are ported.

## Objective

Create `/workspace/Python/autonomous_task_overview` as a persistent clone of
`git@github.com:y2d2/autonomous_task_overview.git` and, on branch
`feature/engine-move`, build the `autonomous_task` package scaffold: frozen copies of the
six primitive modules, a trimmed `config.py` + `config/workflows.yaml`, a NEW
single-workflow `runner.py` (idle gate + lock + run-id + logging), `cli.py` +
`__main__.py`, `pyproject.toml`, `.gitignore`. End state: `uv sync --extra dev` clean,
`uv run autonomous-task run --help` works, `import autonomous_task.workflows.roadmap_dev`
succeeds, ruff clean, zero `agentic_scripts` references anywhere in the new repo.

## Context

- **Source repo (read-only for this task):** `/workspace/Python/agentic_scripts`, branch
  `feature/roadmap-dev-workflow`. It is a LIVE checkout (cron fires there every 30 min) —
  read files from it, but make NO changes and run NO builds/tests in it.
- **Target:** `/workspace/Python/autonomous_task_overview` — the persistent clone (this
  is also where the engine will later RUN). The repo today holds only `README.md` +
  `plans.md`. `plans.md` is the live listing reconciled/pushed by the engine itself —
  NEVER edit it, never stage it, never commit it.
- **Naming (finalized):** project `autonomous-task`; package `autonomous_task` (src
  layout `src/autonomous_task/`); console script `autonomous-task`; runner module
  `autonomous_task/runner.py`; config `config/workflows.yaml`; workflow name stays
  `roadmap-dev`.
- **Git conventions:** `OC:` commit prefix; feature branch only; `git push -u origin
  feature/engine-move`; no destructive git; stage explicit paths (the target repo has no
  untracked-session hazard, but `plans.md`/`.venv` must never be staged — `.gitignore`
  covers the runtime dirs).
- **Tooling:** uv + Python 3.12; ruff (line-length 100, `E,F,I,UP,W`); hatchling build.
- **Design decisions (from the approved plan — do not revisit):** standalone package with
  its own frozen copies of the primitives (no cross-repo imports; the codebase's
  self-containment convention copies rather than cross-imports); single-workflow runner
  instead of the multi-workflow `scheduler.py` (the quiet-window/load gate and the
  multi-workflow loop stay in `agentic_scripts`); the engine keeps its separate listing
  clone under its sandbox (unchanged).
- The original `scheduler.py` is the reference implementation for the new runner. Read
  `acquire_lock` (flock, never-unlock-file semantics), `evaluate_idle_gate` (session
  probe, two-poll streak on state key `idle_gate_last_ok` in the `scheduler` state
  document), `_idle_gate_line` (exact GATE log format), `_last_run_lines` (last-run.txt
  format), and the `run()` pipeline (parse → config → dotenv → logger → lock → gate →
  workflow → last-run; exit codes 0/2; per-workflow errors never change the exit code).

## Tasks

### Task 1: Create the persistent clone + branch
- **Files:** `/workspace/Python/autonomous_task_overview` (create)
- **Do:** If the directory does not exist: `git clone git@github.com:y2d2/autonomous_task_overview.git /workspace/Python/autonomous_task_overview`. If it exists: verify `git remote -v` shows that remote, working tree clean, on `main`. Then `git checkout -b feature/engine-move && git push -u origin feature/engine-move`.
- **Acceptance:**
  1. `git -C /workspace/Python/autonomous_task_overview status -sb` shows `## feature/engine-move...origin/feature/engine-move` with a clean tree.
  2. `git ls-remote origin HEAD` succeeds (SSH reachable).

### Task 2: Package scaffold + primitive copies
- **Files (create, in the overview clone):** `pyproject.toml`, `.gitignore`, `src/autonomous_task/__init__.py`, `src/autonomous_task/__main__.py`, `src/autonomous_task/cli.py`, `src/autonomous_task/agent.py`, `src/autonomous_task/git.py`, `src/autonomous_task/sessions.py`, `src/autonomous_task/state.py`, `src/autonomous_task/logging_setup.py`, `src/autonomous_task/workflows/__init__.py`, `src/autonomous_task/workflows/base.py`, `src/autonomous_task/workflows/roadmap_dev.py`
- **Do:**
  1. `pyproject.toml`: name `autonomous-task`, version `0.1.0`, `requires-python >=3.12`, dependencies `pyyaml>=6` + `python-dotenv>=1` (NO psutil — the load/quiet gate is gone), optional dev `pytest>=8` + `ruff>=0.5`, `[project.scripts] autonomous-task = "autonomous_task.cli:main"`, hatchling build with `packages = ["src/autonomous_task"]`, ruff config identical to the source repo (`py312`, line-length 100, `E,F,I,UP,W`), `[tool.pytest.ini_options] testpaths = ["tests"]`. Description: standalone unattended plan-execution engine (roadmap-dev).
  2. `.gitignore`: `.venv/`, `__pycache__/`, `*.pyc`, `.pytest_cache/`, `.ruff_cache/`, `logs/`, `state/`, `sandbox/`, `.env`, `.env.local` — and explicitly NOT `plans.md` (the listing is tracked).
  3. Copy `agent.py`, `git.py`, `sessions.py`, `state.py`, `logging_setup.py`, `workflows/__init__.py`, `workflows/base.py` from the source repo into the new package. In every copied file: rewrite all `agentic_scripts.` import prefixes → `autonomous_task.`, rename all `agentic_scripts` logger-name strings (e.g. `logging.getLogger("agentic_scripts.sessions")`) and docstring package references to `autonomous_task`. Behavior otherwise byte-identical (frozen leaf copies).
  4. Copy `workflows/roadmap_dev.py` (3,356 lines) → `src/autonomous_task/workflows/roadmap_dev.py` with the same mechanical rewrite only (`agentic_scripts.` → `autonomous_task.` in imports, logger names, docstrings). NO behavioral edits — the module is terminal-consumer code.
  5. `__init__.py`: one-line package docstring. `__main__.py`: mirror the source repo's `__main__.py` (imports `main` from `autonomous_task.cli` and calls it under `if __name__ == "__main__"`). `cli.py`: mirror the source repo's `cli.py` (thin `main()` delegating to `autonomous_task.runner.run`, `sys.exit(run())`).
- **Acceptance:**
  1. `uv sync --extra dev` exits 0 in the clone; `uv run ruff check src/` exits 0.
  2. `uv run python -c "import autonomous_task.workflows.roadmap_dev"` succeeds.
  3. `grep -rn "agentic_scripts" pyproject.toml .gitignore src/` returns zero hits.
  4. `plans.md` and `README.md` are untouched (`git status` shows only new files).

### Task 3: Trimmed `config.py` + shipped `config/workflows.yaml`
- **Files:** `src/autonomous_task/config.py` (create — trimmed from source `config.py`), `config/workflows.yaml` (create)
- **Do:**
  1. `config.py`: port from the source file, KEEPING: `PROJECT_ROOT`, `ConfigError`, `QuietWindow`, `Machine` (fields: `quiet_window`, `poll_interval_minutes`, `gate_polls_required`, `gate_poll_tolerance_minutes` — DROP `load_threshold`), `Agent`, `Paths`, `RoadmapPrompts` (+ `DEFAULT_RUN_TIMEOUT_MINUTES = 480`), `Config` (fields: `machine`, `agent`, `paths`, `roadmap_prompts` — DROP `workflows`, `oc_todo`, `admin_repo`), `_parse_hhmm`, `_require_mapping`, `_require_key`, `_resolve_path`, `_load_machine` (drop load_threshold parsing), `_load_agent`, `_load_paths`, `_load_roadmap_prompts`, `_EMPTY_ROADMAP_PROMPTS`, `load_config` (required sections: `machine`, `agent`, `paths`; `roadmap_prompts` optional with empty defaults — same as source; drop all `workflows`/`oc_todo`/`admin_repo` handling). Preserve the source docstring style (Purpose/Rationale/Usage) with package references updated.
  2. `config/workflows.yaml` — the LIVE values (copy from the source repo's `config/workflows.yaml`), trimmed to exactly these sections:
     ```yaml
     machine:
       quiet_window:
         start: "22:00"
         end: "08:00"
       poll_interval_minutes: 30
       gate_polls_required: 2
       gate_poll_tolerance_minutes: 10
     agent:
       binary: opencode
       model: llama-cpp/Qwen3.8-27B
       max_steps: 80
       timeout_minutes: 180
       auto_approve: true
     paths:
       state_dir: state
       log_dir: logs
       sandbox_dir: sandbox
     roadmap_prompts:
       allowed_repos:            # the live 9-repo list from the source config, verbatim, in order
         - y2d2/ARP_MPE
         - y2d2/ARP_implementations
         - y2d2/ARP_1A_anchored_implementations
         - y2d2/ARP_utility_code
         - y2d2/PRP_ARP_M
         - y2d2/ARP_IMU
         - y2d2/agentic_scripts
         - y2d2/ARP_roadmap
         - y2d2/ARP_engine
       listing_repo: y2d2/autonomous_task_overview
       listing_repo_url: ""
       listing_path: plans.md
       listing_branch: main
       run_timeout_minutes: 480
       test_commands: {}
       repo_urls: {}
     ```
     (Carry over the useful inline comments from the source config for the fields that remain. No `workflows:`, `oc_todo:`, `admin_repo:` keys.)
- **Acceptance:**
  1. `uv run python -c "from pathlib import Path; from autonomous_task.config import load_config; c = load_config(Path('config/workflows.yaml')); print(c.machine.gate_polls_required, c.roadmap_prompts.listing_repo, len(c.roadmap_prompts.allowed_repos))"` prints `2 y2d2/autonomous_task_overview 9`.
  2. `uv run ruff check src/` clean; zero `agentic_scripts` references in `src/`.

### Task 4: The new single-workflow `runner.py`
- **Files:** `src/autonomous_task/runner.py` (create — new code; the only non-copied module)
- **Do:** Implement the single-workflow runner, porting the contracts from the source `scheduler.py` (read `evaluate_idle_gate`, `acquire_lock`, `_idle_gate_line`, `_last_run_lines`, and `run()` in full). Required surface:
  - Module-level: `WORKFLOW_NAME = "roadmap-dev"`; `DEFAULT_CONFIG = PROJECT_ROOT / "config" / "workflows.yaml"`; top-level `from autonomous_task.sessions import read_active_sessions` (tests monkeypatch THIS import site — load-bearing seam).
  - `GateResult` frozen dataclass: `open: bool`, `reason: str`, `now: datetime`.
  - `evaluate_idle_gate(now, state: StateStore, machine: Machine, active_sessions: int) -> GateResult` — semantics identical to the source: `active_sessions > 0` → clear `idle_gate_last_ok` (state doc `"scheduler"`), CLOSED with reason `f"{n} active session(s)"`; `gate_polls_required == 1` → OPEN, reason `"no active sessions (single idle poll)"`; previous poll within `poll_interval_minutes + gate_poll_tolerance_minutes` → OPEN, reason `"no active sessions (2nd consecutive idle poll)"`; else record `now` (UTC ISO) in `idle_gate_last_ok`, CLOSED, reason `"no active sessions (1st idle poll recorded)"`.
  - `acquire_lock(state_dir: Path) -> int | None` — port verbatim (flock `LOCK_EX|LOCK_NB` on `<state_dir>/.lock`, create-if-absent, never unlink the file).
  - `build_parser()` — `prog="autonomous-task"`, subcommand `run` with `--force`, `--config` (default `str(DEFAULT_CONFIG)`), `--verbose`. NO `--only`.
  - `_gate_line(gate, active_sessions)` — exact format: `f"GATE now={gate.now.isoformat()} active_sessions={active_sessions} verdict={'OPEN' if gate.open else 'CLOSED'} reason={gate.reason}"`.
  - `_last_run_lines(run_id, trigger, gate_line, workflow_summary, overall)` — lines: `run: <id>`, `trigger: <gate|force>`, `gate: FORCED` when `gate_line is None` else the gate line, `workflows: <summary>`, `overall: <ok|error|skipped>`.
  - `run(argv: list[str] | None = None, *, now: datetime | None = None, run_id: str | None = None) -> int` — pipeline in exact order: (1) argv default `sys.argv[1:]`; empty → print help, return 2; `argv[0] != "run"` → prepend `"run"`; parse. (2) `load_config(Path(args.config))` → `ConfigError` → `print(f"config error: {exc.message}", file=sys.stderr)`, return 2. (3) `load_dotenv(PROJECT_ROOT / ".env", override=False)`. (4) `now := now or datetime.now()`; `run_id := run_id or new_run_id()`. (5) `logger, _ = setup_run_logger(config.paths.log_dir, run_id, verbose=args.verbose)`; log `RUN START force=%s`. (6) `fd = acquire_lock(config.paths.state_dir)`; `None` → log `SKIP another run is in progress`, write last-run with overall `skipped`, return 0. (7) non-forced only: `n = read_active_sessions()`; `gate = evaluate_idle_gate(now, StateStore(config.paths.state_dir), config.machine, n)` (a `StateError` → log ERROR, write last-run `error`, close fd, return 2); log `_gate_line`; `gate_open = gate.open`. Forced → `gate_open = True`, no gate line (rendered `gate: FORCED`). (8) `wf = create(config)` imported from `autonomous_task.workflows.roadmap_dev`; `ctx = WorkContext(config=config, state=StateStore(config.paths.state_dir), logger=logger, run_id=run_id, workflow_name=WORKFLOW_NAME, sandbox_dir=config.paths.sandbox_dir, admin_repo=None, gate_open=gate_open)`; `result = wf.run(ctx)`. (9) Log the canonical summary line `WORKFLOW roadmap-dev status=<status> items_found=<n> actions=<n> errors=<n>` (INFO for ok; each error additionally at ERROR level); overall = `result.status`. (10) `write_last_run(config.paths.log_dir, _last_run_lines(run_id, "force" if args.force else "gate", gate_line, f"roadmap-dev={result.status}({result.items_found} items, {len(result.actions)} actions, {len(result.errors)} errors)", overall))`. (11) `finally: os.close(fd)`; return 0 — per-workflow errors never change the exit code (same contract as the source scheduler). Docstrings in the source repo's style.
- **Acceptance:**
  1. `uv run autonomous-task run --help` prints the `run` subcommand with `--force`, `--config`, `--verbose` and NO `--only`.
  2. `uv run python -c "from autonomous_task.runner import run, evaluate_idle_gate, acquire_lock, GateResult"` succeeds.
  3. `uv run ruff check src/` clean.
  4. A manual forced run with an EMPTY allowlist config (write a tmp config with `roadmap_prompts.allowed_repos: []` pointed at tmp dirs) via `uv run autonomous-task run --force --config <tmp>` exits 0 and logs `WORKFLOW roadmap-dev status=ok items_found=0 actions=1 errors=0` — proving the no-op path end-to-end without touching the live listing. (Clean up tmp files afterwards.)

### Task 5: Commit + push
- **Do:** Stage the new files explicitly (list them; never `git add -A`), commit `OC: Add standalone autonomous-task engine package (primitives, trimmed config, single-workflow runner, CLI)`, push.
- **Acceptance:**
  1. `git status` clean on `feature/engine-move`; `git log --oneline -2` shows the new commit; remote branch updated.
  2. `plans.md` / `README.md` unchanged in the commit (`git show --stat` lists only new files).

## Out of Scope
- Tests (Task 2 of the work plan), `setup.sh`/systemd (work-plan Task 3), docs (work-plan Task 4).
- Any change in `/workspace/Python/agentic_scripts` (read-only source).
- Any behavior change inside the copied modules (frozen leaves; mechanical rewrites only).

## Notes
- **[Assumption]** `WorkContext` field order is `config, state, logger, run_id, workflow_name, sandbox_dir, admin_repo, gate_open` (dataclass) — construct with keywords; `config.paths.sandbox_dir` is already an absolute, PROJECT_ROOT-resolved Path.
- **[Assumption]** The source `config.py`'s `_resolve_path` resolves relative `paths.*` against `PROJECT_ROOT`; the new repo keeps the same `src/<pkg>/config.py` depth, so `PROJECT_ROOT = parents[2]` still lands on the repo root.
- **[Risk]** Copy drift: if a copy differs from the source beyond the mechanical rewrites, the move silently changes behavior. Mitigation: after each copy, `diff <(sed 's/agentic_scripts/autonomous_task/g' <source>) <target>` should be empty for the verbatim-copy files (agent/git/sessions/state/logging_setup/base/roadmap_dev).
- **[Convention]** Coding-standards headers (Purpose/Rationale/Usage docstrings) are the repo's norm — keep them in `runner.py`; update all package-name references.
