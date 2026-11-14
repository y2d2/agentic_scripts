# Task Plan: Config extension — `oc_todo` section

**Purpose:** Add the OC-todo workflow's configuration (repo list, per-run cap, per-repo test commands, clone-URL overrides) to the declarative, fail-fast config loader, so the workflow (Tasks 3–5) reads validated, typed settings from `config/workflows.yaml`.

**Task:** #1    **Session:** `planning/workflows-oc-todo/`    **Result file:** `planning/workflows-oc-todo/lightweight_dev_task_1_config.md`

## Objective

`load_config` gains support for an optional top-level `oc_todo` section that validates into a new frozen dataclass `OCTodo`. When the section is absent (e.g. pre-existing configs), the workflow gets empty defaults (no repos → no-op). Every invalid value fails fast with a `ConfigError` naming the offending dotted field, matching the loader's existing style.

## Context

Project: `/workspace/Python/agentic_scripts` (Python ≥3.12, `uv`, src layout). Lint: `uv run ruff check src tests` (line-length 100, E/F/I/UP/W). Tests: `uv run pytest tests/ -v`. No new dependencies; **do not modify `pyproject.toml`**. Do not commit/push — the orchestrator handles git.

Read first (style + structure source of truth):
- `src/agentic_scripts/config.py` — the loader you are extending: `ConfigError`, the frozen dataclasses (`Machine`, `Agent`, `Paths`, `WorkflowEntry`, `Config`), the `_require_mapping` / `_require_key` / `_resolve_path` helpers, `_load_machine` / `_load_agent` / `_load_paths` / `_load_workflows`, and `load_config` (note how the **optional** `admin_repo` section is handled: `raw.get(...)` with a None default; `allowed_sections` gates unknown top-level keys; the required-sections loop stays unchanged).
- `tests/test_config.py` — existing test patterns (valid config loads, ConfigError field naming, unknown-section rejection, shipped-config load).
- Docstring convention: Google-style with `Purpose:` / `Rationale:` (where non-obvious) / `Usage:`, typed Args/Returns/Raises — copy the register of `config.py` exactly.

Key constraint discovered by the orchestrator: `tests/test_agent.py:100` constructs `Config(machine=..., agent=..., paths=..., admin_repo=None, workflows=[])` **directly** — so the new `Config` field MUST have a default (frozen dataclass → default goes last; use `field(default_factory=...)` with a module-level `_EMPTY_OC_TODO` constant so the default instance is never shared-mutated).

## Tasks

### Task 1: `OCTodo` dataclass + loader + `Config` wiring
- **Files:** `src/agentic_scripts/config.py` (modify)
- **Do:**
  1. Add module constant `DEFAULT_MAX_TODOS_PER_REPO = 3` (the per-run cap default) and a module-level `_EMPTY_OC_TODO` instance (see step 5).
  2. Add frozen dataclass `OCTodo` (place it with the other dataclasses, after `WorkflowEntry`):
     - `repos: list[str]` — ordered list of GitHub repo ids in `owner/name` form; empty list = nothing to scan.
     - `max_todos_per_repo: int` — max todos *processed* per repo per run.
     - `test_commands: dict[str, str]` — optional per-repo test command; keys must be members of `repos`, values non-empty strings.
     - `repo_urls: dict[str, str]` — optional clone-URL overrides per repo (local paths or URLs; hermetic-test/mirror seam); keys must be members of `repos`, values non-empty strings.
     - Docstring: Attributes section explaining each + that an empty `repos` list means the workflow no-ops.
  3. Add `_load_oc_todo(data: dict[str, Any]) -> OCTodo`:
     - `repos`: required key in the section (present but may be `[]`); must be a list; each entry must be a string matching `^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$` — else `ConfigError(f"oc_todo.repos[{i}]", ...)` naming the index.
     - `max_todos_per_repo`: optional; default `DEFAULT_MAX_TODOS_PER_REPO`; when present must be an int (not bool) `>= 1` — else `ConfigError("oc_todo.max_todos_per_repo", ...)`.
     - `test_commands` / `repo_urls`: optional; default `{}`; when present must be mappings; every key must be a member of `repos` (else `ConfigError(f"oc_todo.test_commands.{repo}", "repo is not in oc_todo.repos")` / same shape for `repo_urls`); every value a non-empty string.
     - The `oc_todo` section itself, when present, must be a mapping (use `_require_mapping("oc_todo", ...)`).
  4. Wire into `load_config`:
     - Add `"oc_todo"` to `allowed_sections`.
     - Optional handling (mirror `admin_repo`): `oc_todo_raw = raw.get("oc_todo")`; `oc_todo = _load_oc_todo(_require_mapping("oc_todo", oc_todo_raw)) if oc_todo_raw is not None else _EMPTY_OC_TODO`.
     - Return it in the `Config(...)` construction.
  5. Add field `oc_todo: OCTodo = field(default_factory=lambda: _EMPTY_OC_TODO)` to the `Config` dataclass — **last position** (after `workflows`), with a docstring line ("OC-todo workflow settings; empty defaults when the `oc_todo` section is absent").
  6. Update `load_config`'s docstring (Args/Returns) to mention the optional `oc_todo` section.
- **Notes:** Keep the loader's error-message style (short, field-naming). No behavior change for configs without the section — every existing config must load byte-identically in effect. Import `field` from `dataclasses` (already imported).

### Task 2: Tests
- **Files:** `tests/test_config.py` (modify)
- **Do:** Add a focused test group (follow the file's existing YAML-to-tmp-file pattern):
  1. `oc_todo` section absent → `cfg.oc_todo.repos == []`, `max_todos_per_repo == 3`, `test_commands == {}`, `repo_urls == {}` (use the shipped-config load path, e.g. `base_config` fixture).
  2. Valid section parses: `repos: ["owner/one", "owner/two"]`, `max_todos_per_repo: 5`, `test_commands: {owner/one: "uv run pytest"}`, `repo_urls: {owner/two: "/tmp/local.git"}` → exact round-trip.
  3. Bad repo string (`"no-slash"`, `"a/b/c"`, `""`) → `ConfigError` whose message contains `oc_todo.repos[0]` (parametrize the index).
  4. `max_todos_per_repo: 0` and `max_todos_per_repo: "three"` → `ConfigError` naming `oc_todo.max_todos_per_repo`.
  5. `test_commands` key not in `repos` → `ConfigError` naming `oc_todo.test_commands.<that-repo>`; same for a `repo_urls` key.
  6. `oc_todo` present but not a mapping (e.g. a list) → `ConfigError` naming `oc_todo`.
  7. Confirm the shipped `config/workflows.yaml` (pre-Task-5, without the section) still loads.
- **Acceptance:**
  1. `uv run pytest tests/test_config.py -v` — all new + existing tests pass.
  2. `uv run pytest tests/ -v` — full suite green (no regressions).
  3. `uv run ruff check src tests` — clean.

## Out of Scope
- No `workflows.yaml` edits (the section is added in Task 5 alongside the workflow registration).
- No other config sections touched; no changes to `WorkflowEntry` / `machine` / `agent` / `paths` handling.

## Notes
- The `owner/name` regex is deliberately permissive (GitHub's real rules are stricter) — validation depth here is shape-only; the real check is the clone/PR call at run time.
- `[Assumption]` cap default 3 per repo per run — a user-tunable knob, reviewed at the plan GATE.
