# lightweight-dev Output — Task: oc_todo core (scan parse, identity, state, renderers) + git.py additions

**Task:** #3    **Session:** `planning/workflows-oc-todo/`    **Date:** 2026-11-14

## Summary

Implemented the pure, testable core of the OC-todo workflow and the additive `git.py`
methods it needs. Concretely: (1) extended `Git` with `grep_fixed`, `show_file`,
`delete_branch` and added keyword-only `env`/`prune` params to `clone`/`fetch` (additive
only — no existing call changes behaviour); (2) created
`src/agentic_scripts/workflows/oc_todo.py` with the marker scan parser (`parse_grep_lines`,
greedy file group), todo identity (`todo_id`/`todo_branch_name`/`Todo`), layout helpers,
keep-instruction detection, PR-state mapping, the v1 state schema helpers, the `plan_run`
decision table (all 8 current-todo cells + vanished entries), and the byte-stable renderers
(`render_brief`, `render_pr_title`, `extract_report_sections`, `render_pr_body`) plus the
deliberately-duplicated `_is_step_exhausted` sentinel and `apply_cap`; (3) created a hermetic
`tests/test_oc_todo.py` (pure-logic group A + real-git group B). No orchestration (`run`),
no `create(config)` — those are Tasks 4–5. One spec-level deviation on `grep_fixed`'s
`--exclude-standard` is documented under Blockers.

## Files
| File | Action | Why |
|---|---|---|
| `src/agentic_scripts/git.py` | modify (additive) | Added `os` import; keyword-only `env` on `clone`/`fetch`, `prune`+`env` on `fetch`; new `grep_fixed`, `show_file`, `delete_branch`. Existing calls keep their behaviour. |
| `src/agentic_scripts/workflows/oc_todo.py` | create | The Task-3 core: constants, `Todo`, pure helpers, state schema, `plan_run` decision table, byte-stable renderers, `_is_step_exhausted`, `apply_cap`, and the `OCTodoWorkflow` shell. |
| `tests/test_oc_todo.py` | create | Hermetic tests: group A (pure logic) + group B (real-git `grep_fixed`/`show_file`/`delete_branch`). |

## Build / Tests
- `uv run pytest tests/test_oc_todo.py -v`: PASS — 33 passed.
- `uv run pytest tests/test_git.py -v` (unmodified): PASS — 6 passed.
- `uv run pytest tests/ -v` (full suite): PASS — 166 passed, no regressions.
- `uv run ruff check src tests`: PASS — All checks passed.

## Acceptance Verification
| # | Criterion (verbatim) | Result | Notes |
|---|---|---|---|
| 1. | `uv run pytest tests/test_oc_todo.py -v` — all pass. | PASS | 33 passed in ~1.1s. |
| 2. | `uv run pytest tests/ -v` — full suite green (including `tests/test_git.py` after the `git.py` additions). | PASS | 166 passed; `test_git.py` green unmodified. |
| 3. | `uv run ruff check src tests` — clean. | PASS | All checks passed. |

## Blockers
None (all acceptance criteria pass). One **spec-level deviation** the orchestrator should
note before Task 4 wires the scan:

- **`grep_fixed` does not pass `--exclude-standard`.** The spec's Do #3 says to run
  `git grep -n -F -I -e <pattern> [--exclude-standard] <ref>` and its test #13 asserts a
  `.gitignored` text file is excluded. This is **not implementable for a committed ref**:
  git errors out with exit 128 (`fatal: --[no-]exclude-standard cannot be used for tracked
  contents`) on *any* grep of a ref when `--exclude-standard` is present — verified against
  the installed git. Since the scanner always greps a ref (`origin/<branch>`), passing the
  flag would make every scan call fail, and a committed ref contains no untracked files for
  the flag to filter anyway. I kept the keyword-only `exclude_standard: bool = False` param
  (API stability) but it is intentionally inert, with a Note in the docstring explaining why.
  The spec's "standard binary/build exclusions" intent is satisfied by `-F -I` (binary files
  are excluded; build artifacts are not committed). The test therefore asserts the binary
  (`-I`) exclusion and drops the `.gitignored` sub-case, with a note documenting the reason.
  **Task 4 should not rely on `--exclude-standard`; if untracked-file scanning is ever
  needed it must grep the working tree, not a ref.**

## Next Steps
- Task 4 (`run` orchestration) can build directly on these helpers: scan via
  `Git.grep_fixed(clone_dir, f"origin/{branch}", MARKER_PREFIX)` → `parse_grep_lines`, keep
  context via `Git.show_file` + `has_keep_instruction`, identity via `Todo.id`/
  `todo_branch_name`, plan via `plan_run`, render the brief/PR via `render_brief`/
  `render_pr_title`/`render_pr_body`, parse the report via `extract_report_sections`, and
  detect step-cap exhaustion via `_is_step_exhausted`.
- Confirm the orchestrator accepts the `--exclude-standard` deviation (see Blockers) before
  Task 4 finalizes the scan loop.
