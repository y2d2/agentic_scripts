# lightweight-dev Output — Task: Config extension — `oc_todo` section

**Task:** #1    **Session:** `planning/workflows-oc-todo/`    **Date:** 2026-11-14

## Summary

Extended the declarative, fail-fast config loader (`src/agentic_scripts/config.py`) to
support an optional top-level `oc_todo` section that validates into a new frozen
dataclass `OCTodo`. When the section is absent (e.g. the current shipped
`config/workflows.yaml`, pre-Task-5), the workflow gets empty defaults (no repos →
no-op). Every invalid value fails fast with a `ConfigError` naming the offending dotted
field, matching the loader's existing style.

Concretely: added module constant `DEFAULT_MAX_TODOS_PER_REPO = 3` and a module-level
`_EMPTY_OC_TODO` instance; added frozen dataclass `OCTodo` (placed after `WorkflowEntry`)
with `repos`, `max_todos_per_repo`, `test_commands`, `repo_urls`; added the
`_load_oc_todo(data)` loader (required `repos` list of `owner/name` ids, optional
`max_todos_per_repo` int >= 1 defaulting to 3, optional `test_commands`/`repo_urls`
mappings whose keys must be members of `repos` and values non-empty strings); wired the
section into `load_config` (`"oc_todo"` added to `allowed_sections`, optional handling
mirroring `admin_repo`, returned in the `Config(...)` construction); and added the
`oc_todo: OCTodo = field(default_factory=lambda: _EMPTY_OC_TODO)` field as the **last**
field of `Config` (so the direct-construction at `tests/test_agent.py:100` still works).
Updated `load_config`'s docstring Args/Returns to mention the optional section.

Added a focused test group in `tests/test_config.py` covering all seven required cases.

## Files
| File | Action | Why |
|---|---|---|
| `src/agentic_scripts/config.py` | modify | Add `OCTodo` dataclass, `_load_oc_todo` loader, `DEFAULT_MAX_TODOS_PER_REPO`/`_EMPTY_OC_TODO` constants, `oc_todo` field on `Config`, and `load_config` wiring. |
| `tests/test_config.py` | modify | Add the `oc_todo` test group (absent defaults, valid round-trip, bad repo strings, bad cap, key-not-in-repos for both maps, not-a-mapping, shipped-config still loads). |

## Build / Tests
- `uv run pytest tests/test_config.py -v`: PASS — 20 passed (11 pre-existing + 9 new).
- `uv run pytest tests/ -v`: PASS — 124 passed, no regressions.
- `uv run ruff check src tests`: PASS — "All checks passed!" (clean).

## Acceptance Verification
| # | Criterion (verbatim) | Result | Notes |
|---|---|---|---|
| 1. | `uv run pytest tests/test_config.py -v` — all new + existing tests pass. | PASS | 20/20 passed. |
| 2. | `uv run pytest tests/ -v` — full suite green (no regressions). | PASS | 124/124 passed. |
| 3. | `uv run ruff check src tests` — clean. | PASS | No findings. |

## Blockers
None.

## Next Steps
- Task 5 (integration) is expected to add the `oc_todo` section to `config/workflows.yaml` alongside workflow registration; until then the shipped config loads with empty defaults (verified by `test_shipped_config_without_oc_todo_still_loads`).
- Downstream tasks (3–5) can now read validated, typed settings from `cfg.oc_todo`.
