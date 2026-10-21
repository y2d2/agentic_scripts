# Task 1: Project foundation (skeleton, config, state, logging, workflow protocol, noop)

**Purpose:** Create the greenfield Python package skeleton for `agentic_scripts` — canonical config with fail-fast validation, durable per-workflow state store, run-logging + last-run writer, the `Workflow` protocol, and the `noop` demo workflow — so that Tasks 2–5 build on shared primitives with no further pyproject changes.

## Objective

Deliver a working `uv`-managed src-layout package in which (a) `uv sync` + `uv run pytest` + `uv run ruff check .` + `uv run ruff format --check .` all pass, (b) the canonical config `config/workflows.yaml` loads into typed dataclasses with fail-fast validation that names the offending field, (c) the state store round-trips atomically per workflow, (d) the run-logger produces `logs/run-<run_id>.log` + `logs/last-run.txt`, (e) the `Workflow` protocol + `noop` workflow run cleanly via the protocol — with zero side effects outside the repo's gitignored areas.

## Context

- **Repo:** `/workspace/Python/agentic_scripts`, branch `plan/agentic-workflows` (up to date with origin). Commit prefix `OC:` (git-workflow skill). Greenfield: README (1 line) + `planning/` only.
- **Environment (re-verified 2026-10-20):** Ubuntu 24.04 container, root, Python 3.12.3, `uv` 0.12.5, `psutil` 7.2.2 already importable. No LLM, no network needed for this task.
- **Stack:** `uv` + src layout + Ruff (lint+format) + pytest. Runtime deps `pyyaml`, `psutil`, `python-dotenv`; dev deps `pytest`, `ruff`. **This task owns `pyproject.toml`; Tasks 2–5 must not modify it.**
- **Conventions:** Google-style docstrings (coding-standards skill: module docstring with header for modules that are entry points; one-line docstrings elsewhere). All tests hermetic (tmp dirs only). No side effects outside the repo.

### Canonical config schema (single source of truth — use exactly this shape)

`config/workflows.yaml`:

```yaml
# agentic_scripts configuration
machine:
  quiet_window:
    start: "22:00"   # local time, HH:MM; window crosses midnight (start > end)
    end: "08:00"
  load_threshold: 2.0          # load1 must be STRICTLY below this
  poll_interval_minutes: 30    # nominal timer cadence
  gate_polls_required: 2       # consecutive idle polls needed to open the gate; allowed: 1 or 2
  gate_poll_tolerance_minutes: 10  # max gap between consecutive idle polls
agent:
  binary: opencode
  model: openaiCompatible/Qwen3.8-27B   # string or null; null = agent's own frontmatter model
  max_steps: 40            # informational; the live cap is the agent frontmatter `steps`
  timeout_minutes: 45      # per-workflow hard timeout for the agent run
  auto_approve: true       # pass --auto to opencode run
paths:
  state_dir: state         # relative paths resolve against the project root
  log_dir: logs
  sandbox_dir: sandbox
admin_repo: /workspace/Obsidian/ARP_roadmap   # string or null
workflows:
  noop:
    enabled: true
    module: agentic_scripts.workflows.noop
    agent: null            # string or null; set for workflows that spawn an agent
```

### Canonical repo layout (this task creates every file listed T1; layout owner)

```
agentic_scripts/
├── .env.example
├── .gitignore
├── config/workflows.yaml
├── pyproject.toml
├── src/agentic_scripts/
│   ├── __init__.py
│   ├── config.py
│   ├── state.py
│   ├── logging_setup.py
│   └── workflows/
│       ├── __init__.py
│       ├── base.py
│       └── noop.py
└── tests/
    ├── conftest.py
    ├── test_config.py
    ├── test_state.py
    └── test_base_noop.py
```

### Project-root resolution (used by config loader; keep in `config.py`)

`PROJECT_ROOT = Path(__file__).resolve().parents[2]` (file is `src/agentic_scripts/config.py`). Relative `paths.*` values resolve against `PROJECT_ROOT`; absolute values pass through. `--config` default = `PROJECT_ROOT / "config/workflows.yaml"`. Deterministic regardless of CWD (cron's CWD is not trusted).

## Tasks

### 1. Create `pyproject.toml`
- `[project]` name `agentic-scripts`, version `0.1.0`, description, `requires-python = ">=3.12"`.
- Dependencies: `pyyaml>=6`, `psutil>=5`, `python-dotenv>=1`.
- `[project.optional-dependencies]` dev: `pytest>=8`, `ruff>=0.5`.
- `[project.scripts]` `agentic-scripts = "agentic_scripts.cli:main"` — **entry point declared now; `cli.main` lands in Task 2.** Declaring it early means this task's `pyproject` is final; `uv sync` succeeds without the module (entry-point metadata only fails at invocation). Document this in the file with a comment.
- `[build-system]` hatchling. `[tool.hatch.build.targets.wheel]` packages = `["src/agentic_scripts"]`.
- `[tool.ruff]` target-version `"py312"`, line-length 100; `[tool.ruff.lint]` select `["E","F","I","UP","W"]`.
- `[tool.pytest.ini_options]` testpaths `["tests"]`.
- Do not add any other config blocks.

### 2. Create `.gitignore` and `.env.example`
- `.gitignore`: `.venv/`, `__pycache__/`, `*.pyc`, `.pytest_cache/`, `.ruff_cache/`, `logs/`, `state/`, `sandbox/`, `.env`, `.env.local`.
- `.env.example`: single line `GITHUB_PAT=` with a comment: `# Required when a workflow that opens PRs is enabled; secrets live here or in the environment, never in config/`.

### 3. Create `config/workflows.yaml`
- Exactly the canonical schema above (with the comment lines shown).

### 4. Create `src/agentic_scripts/__init__.py`
- `__version__ = "0.1.0"` and a one-line module docstring.

### 5. Create `src/agentic_scripts/config.py`
- Dataclasses (frozen where sensible): `QuietWindow(start: str, end: str)` with `in_window(dt) -> bool` (handles midnight-crossing: `start > end` → `dt >= start or dt < end`; `start < end` → `start <= dt < end`; `start == end` is invalid and rejected at load), `Machine(start/end parsed to `datetime.time`, load_threshold: float, poll_interval_minutes: int, gate_polls_required: int, gate_poll_tolerance_minutes: int)`, `Agent(binary: str, model: str | None, max_steps: int, timeout_minutes: int, auto_approve: bool)`, `Paths(state_dir: Path, log_dir: Path, sandbox_dir: Path)` (resolved against PROJECT_ROOT at load), `WorkflowEntry(name: str, enabled: bool, module: str, agent: str | None)`, `Config(machine, agent, paths, admin_repo: Path | None, workflows: list[WorkflowEntry])` (workflows preserves YAML order).
- `load_config(path: Path) -> Config` — read YAML, validate, return.
- Validation (raise `ConfigError(section_and_field, message)` with a `message` that names the offending dotted field, e.g. `machine.quiet_window.start`): unknown top-level section → error; missing required section/key → error naming it; `HH:MM` format (24h, minutes ≤ 59) for window start/end; `start == end` rejected; `load_threshold > 0`; `poll_interval_minutes` int ≥ 1; `gate_polls_required` in {1, 2}; `gate_poll_tolerance_minutes` int ≥ 0; `agent.binary` non-empty str; `agent.model` str or null; `agent.max_steps` int ≥ 1; `agent.timeout_minutes` int ≥ 1; `agent.auto_approve` bool; `paths.*` non-empty; `admin_repo` str or null; `workflows` is a mapping; each entry: `enabled` bool, `module` dotted importable string, `agent` str or null. **Module existence check:** for each *enabled* entry, `importlib.import_module(module)` must succeed and the module must expose `create(config) -> Workflow` (has that attribute) — otherwise `ConfigError(workflows.<name>.module, ...)`. (At the end of this task only `noop` exists, so this passes for the shipped config.)
- `main()`-style convenience: not needed here (CLI is Task 2).

### 6. Create `src/agentic_scripts/state.py`
- `class StateError(RuntimeError)` — message includes the file path.
- `class StateStore:` `__init__(self, state_dir: Path)`; `state_dir` created on demand.
  - `load(self, name: str) -> dict` — reads `<state_dir>/<name>.json`; missing file → `{}`; corrupt JSON → `StateError` (no silent reset).
  - `save(self, name: str, data: dict) -> None` — atomic: write `<name>.json.tmp` then `os.replace` to `<name>.json`; ensures parent dir; files 0644. **A crashed mid-write run must never leave a torn file** (this is what the Task 2 kill-mid-run test relies on).
  - `update(self, name: str, key: str, value)` and `delete(self, name: str, key: str) -> object | None` (load-mutate-save).
- Docstring on the class: "Per-workflow durable state. Consult state BEFORE acting (idempotency contract)."

### 7. Create `src/agentic_scripts/logging_setup.py`
- `def new_run_id() -> str` — UTC `%Y%m%dT%H%M%SZ`.
- `def setup_run_logger(log_dir: Path, run_id: str, *, verbose: bool = False) -> tuple[logging.Logger, Path]` — returns `(logger, log_path)` where `log_path = log_dir / f"run-{run_id}.log"`. File handler at INFO; stderr handler at INFO when `verbose` else WARNING. Formatter: `%(asctime)s %(levelname)s [%(name)s] %(message)s` with `datefmt` set so asctime is UTC ISO-ish (use a converter to `time.gmtime` for the `logging` root). Logger name `agentic_scripts`. No propagation to root (avoid duplicate stderr lines).
- `def write_last_run(log_dir: Path, lines: list[str]) -> Path` — overwrites `log_dir / "last-run.txt"` (0644), returns path.

### 8. Create `src/agentic_scripts/workflows/base.py`
- `@dataclass class WorkflowResult:` `status: str` (`"ok" | "skipped" | "error"`), `items_found: int = 0`, `actions: list[str] = field(default_factory=list)`, `errors: list[str] = field(default_factory=list)`, `duration_seconds: float = 0.0`.
- `@dataclass class WorkContext:` fields `config: Config`, `state: StateStore`, `logger: logging.Logger`, `run_id: str`, `workflow_name: str`, `sandbox_dir: Path`, `admin_repo: Path | None`. Lazy properties (import inside the property body so Task 1 compiles before Tasks 3/4 land — see Note 8 of the global plan): `git` → `from agentic_scripts.git import Git; return Git()` (cache on `self._git`), `runner` → `from agentic_scripts.agent import AgentRunner; return AgentRunner(config=self.config, logger=self.logger)` (cache on `self._runner`). If the module doesn't exist yet, the import error propagates — acceptable, workflows that need them ship with Task 3.
- `class Workflow(Protocol):` `name: str`; `def run(self, ctx: WorkContext) -> WorkflowResult: ...` — docstring states the workflow contract: (1) consult `ctx.state` before acting (idempotency), (2) keep side effects inside `ctx.sandbox_dir` / declared targets, (3) never raise for business failures — return `WorkflowResult(status="error", errors=[...])`; exceptions are reserved for programmer errors and are caught by the scheduler, logged, and do not stop other workflows.
- `def create(config: Config) -> Workflow` — **required entry point of every workflow module** (documented here; scheduler calls it).

### 9. Create `src/agentic_scripts/workflows/noop.py`
- `class NoopWorkflow:` `name = "noop"`; `run(ctx)`: increment `ctx.state` key `runs` under name `noop` (i.e. `new = ctx.state.update("noop", "runs", ctx.state.load("noop").get("runs", 0) + 1)`), log `"noop: run recorded (n=<new>)"` at INFO, return `WorkflowResult(status="ok", items_found=0, actions=[f"noop run #{new} recorded"])`.
- `def create(config: Config) -> NoopWorkflow: return NoopWorkflow()` — matches the Task 8 entry-point contract.

### 10. Create `src/agentic_scripts/workflows/__init__.py`
- One-line docstring only (avoid importing submodules here — keeps imports explicit).

### 11. Create `tests/conftest.py`
- Fixture `project_root` (path to the repo root, computed from the conftest location — `Path(__file__).resolve().parents[1]`).
- Fixture `tmp_workspace(tmp_path)` — creates `state/`, `logs/`, `sandbox/` under `tmp_path` and returns a dict of the three Paths.
- Fixture `base_config(tmp_path)` — writes a temp copy of the shipped config with `paths` pointing at the `tmp_workspace` dirs (load with `load_config` after rewriting via yaml round-trip) and returns the `Config`.
- (Git-identity env vars are NOT set here — the git tests in Task 3 set their own.)

### 12. Write the tests
- `tests/test_config.py`: (a) shipped `config/workflows.yaml` loads; `config.paths.state_dir` is absolute under PROJECT_ROOT; workflow order = `[noop]`; `noop.agent is None`. (b) Missing `machine` section → `ConfigError` naming `machine`. (c) `quiet_window.start: "25:99"` → `ConfigError` naming `machine.quiet_window.start`. (d) `load_threshold: -1` → names `machine.load_threshold`. (e) `gate_polls_required: 3` → names `machine.gate_polls_required`. (f) Unknown top-level section `bogus:` → names `bogus`. (g) Enabled workflow entry with `module: agentic_scripts.workflows.does_not_exist` → `ConfigError` naming `workflows.<name>.module`. (h) `agent.model: null` loads fine. (i) `start == end` → rejected.
- `tests/test_state.py`: (a) save/load round-trip incl. nested dict + unicode. (b) `load` of missing name → `{}`. (c) Corrupt file (write garbage bytes) → `StateError` mentioning the path. (d) `update`/`delete` semantics; `delete` of missing key → `None`. (e) Atomicity shape: after `save`, no `*.tmp` remains and the target file exists.
- `tests/test_base_noop.py`: (a) `create(config)` returns an object with `name == "noop"`; `run(ctx)` (ctx built from `base_config` + `setup_run_logger` into the tmp logs) → `status == "ok"`, `items_found == 0`, `actions` non-empty. (b) Two consecutive runs → state `noop.runs == 2` (accumulation, not reset). (c) `WorkflowResult` defaults: `WorkflowResult(status="skipped")` → `errors == []`, `duration_seconds == 0.0`.

## Acceptance criteria

1. `uv sync` succeeds from a clean `.venv`; `uv run ruff check .` and `uv run ruff format --check .` exit 0.
2. `uv run pytest tests/ -v` — all tests pass, zero warnings from the package code.
3. `uv run python -c "from agentic_scripts.config import load_config, PROJECT_ROOT; c = load_config(PROJECT_ROOT/'config/workflows.yaml'); print(c.workflows[0].name, c.machine.load_threshold)"` prints `noop 2.0`.
4. `git status --porcelain` shows only the T1 files listed above as untracked/added (plus the pre-existing README/planning).
5. Committed with `OC:` prefix, pushed to `plan/agentic-workflows`.

## Out of Scope

- CLI, scheduler, gate, lock (Task 2); agent runner, git helpers (Task 3); mail reader (Task 4); setup/systemd/README/smoke (Task 5).
- Modifying `pyproject.toml` after this task (owned here; later tasks must not touch it).
- Any real agent, repo, or mail interaction.

## Notes

- The `pyproject.toml` comment about the early entry-point declaration is load-bearing — keep it.
- `WorkContext.git` / `WorkContext.runner` lazy imports are intentional (parallel-safety with Tasks 3/4); do not "fix" them into module-level imports.
- `ConfigError` and `StateError` both expose a `.message` string suitable for CLI display (Task 2 prints them and exits 2).
