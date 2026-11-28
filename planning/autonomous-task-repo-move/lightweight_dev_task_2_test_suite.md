# lightweight-dev Output — Task: test-suite

**Task:** #2    **Session:** ses_df665d712ffeSgQ47elV5QgSBl    **Date:** 2026-11-23

## Summary

Moved + adapted the roadmap-dev test suite (pure core, scan, pipeline, smoke, both
conftests) from the live read-only source `/workspace/Python/agentic_scripts` into the
clone `/workspace/Python/autonomous_task_overview` (branch `feature/engine-move`):

- **Sub-task 1 (pure files, mechanical rewrite)** — `tests/__init__.py` (empty, created;
  source has none), `tests/conftest.py`, `tests/test_roadmap_dev.py` (1,422),
  `tests/test_roadmap_dev_scan.py` (911), `tests/test_roadmap_dev_pipeline.py` (1,364).
  The three test files were produced by the exact mechanical rewrite
  (`sed 's/agentic_scripts/autonomous_task/g'`) — the plan's freeze-check
  `diff <(sed 's/agentic_scripts/autonomous_task/g' <source>) <target>` is **empty for
  all three** (verified). `conftest.py` = same rewrite plus ONE comment adaptation the
  plan prescribes for conftest ("Drop/update comments that reference the removed
  gate/scheduler/multi-workflow machinery"): the `base_config` comment
  "tests exercise gate/scheduler behavior, not scanning" → "tests exercise the
  roadmap-dev core, not scanning". No assertion or fixture changes anywhere. The
  `base_config` fixture reads the shipped (trimmed) `config/workflows.yaml`, rewrites
  `paths`, empties `roadmap_prompts.allowed_repos` — unchanged, works as-is.
- **Sub-task 2 (smoke suite, prescribed adaptations)** — `tests/smoke/__init__.py`
  (one-line docstring adapted to the new package), `tests/smoke/conftest.py` (autouse
  canned-probe fixture now patches `autonomous_task.runner.read_active_sessions`;
  docstring rewritten: single-workflow runner, no mail-keeper),
  `tests/smoke/test_smoke_roadmap_dev.py` (394 lines, 6 tests) — all plan-prescribed
  adaptations applied exactly: module docstring rewritten; `_isolate_mail_env` dropped
  (and the now-unused `import os`); `_git_env` kept; `load=` dropped from every `run()`
  (`now=`/`run_id=` kept); `--only roadmap-dev` dropped from test 1; quiet-gate reason
  line, all three sibling-skip (`noop`/`mail-keeper`/`oc-todo`) lines, and the
  `gate_last_ok is None` assertion dropped from tests 2–3; the seeded state doc in test
  4 now contains only `idle_gate_last_ok`; T5-scaffold test replaced by
  `test_smoke_roadmap_dev_empty_listing_stub` (header-only stub → `parse_listing` →
  `[]`, see deviation 1 under Blockers); per-test docstrings/comments updated where they
  described removed machinery. All original kept-assertions are verbatim.
- **Sub-task 3 (verification + commit)** — full suite 81/81 green, ruff clean,
  grep criteria met (single plan-mandated `config/` hit per the orchestrator
  refinement), committed + pushed on `feature/engine-move`.

## Files

| File | Action | Why |
|---|---|---|
| `/workspace/Python/autonomous_task_overview/tests/__init__.py` | create | Empty package init (source `tests/` lacks one; plan: "create to match the smoke pattern") |
| `/workspace/Python/autonomous_task_overview/tests/conftest.py` | create | `project_root`/`tmp_workspace`/`base_config` fixtures; mechanical import rewrite + 1 prescribed comment update |
| `/workspace/Python/autonomous_task_overview/tests/test_roadmap_dev.py` | create | Pure core suite (50 tests); pure mechanical rewrite, freeze-check clean |
| `/workspace/Python/autonomous_task_overview/tests/test_roadmap_dev_scan.py` | create | Discovery/scan suite (12 tests); pure mechanical rewrite, freeze-check clean |
| `/workspace/Python/autonomous_task_overview/tests/test_roadmap_dev_pipeline.py` | create | Drain pipeline suite (13 tests); pure mechanical rewrite, freeze-check clean |
| `/workspace/Python/autonomous_task_overview/tests/smoke/__init__.py` | create | One-line docstring adapted to `autonomous_task` (single-workflow runner) |
| `/workspace/Python/autonomous_task_overview/tests/smoke/conftest.py` | create | Autouse canned 0-session probe at `autonomous_task.runner.read_active_sessions`; docstring rewritten per plan |
| `/workspace/Python/autonomous_task_overview/tests/smoke/test_smoke_roadmap_dev.py` | create | 6 run()-level tests ported with the exact prescribed adaptations (incl. scaffold→stub test replacement) |

No files in `/workspace/Python/agentic_scripts` were created, modified, or staged
(read-only; verified — its `git status` shows only the orchestrator's pre-existing
planning files).

## Build / Tests

- Freeze-check (pure files): PASS — `diff <(sed 's/agentic_scripts/autonomous_task/g' <source>) <target>` empty for `test_roadmap_dev.py`, `test_roadmap_dev_scan.py`, `test_roadmap_dev_pipeline.py`
- `uv run pytest tests/test_roadmap_dev.py tests/test_roadmap_dev_scan.py tests/test_roadmap_dev_pipeline.py -q` (before any smoke work): PASS — 75 passed in 31.97s
- `uv run pytest tests/smoke/test_smoke_roadmap_dev.py -q` (under `env -u GITHUB_PAT`): PASS — 6 passed in 0.39s
- Seam grep: PASS — `autonomous_task.runner.read_active_sessions` present in `smoke/conftest.py` (autouse) + 3 test-local `monkeypatch.setattr` patches (tests 2, 3, 4); zero `agentic_scripts` in `tests/`
- Removed-machinery grep in `tests/`: PASS — no `gate_last_ok` (beyond `idle_gate_last_ok`), no `--only`, no `load=` (beyond `safe_load`), no `MAIL_`, no old staging path / "scaffold"
- `uv run pytest -q` (whole clone, `testpaths = ["tests"]`): PASS — **81 passed in 32.77s**, 0 failed (75 core+scan+pipeline + 6 smoke)
- `uv run ruff check .`: PASS — "All checks passed!" (tests are in ruff's view by default — the clone `pyproject.toml` has no ruff `exclude`, so no pyproject change was needed; source lints tests the same way)
- `grep -rn "agentic_scripts" src/ tests/ config/ pyproject.toml .gitignore`: PASS per orchestrator refinement — exactly 1 hit, the plan-mandated data value `config/workflows.yaml:27: - y2d2/agentic_scripts`; zero in `src/`, `tests/`, `pyproject.toml`, `.gitignore`
- Environment: CPython 3.14.7 / pytest 9.2.0 — no version-conditional failures; suite is version-agnostic
- Commit + push: PASS — `OC: Move roadmap-dev test suite (core, scan, pipeline, smoke) adapted to the standalone runner` on `feature/engine-move`; 8 files, 4,189 insertions(+), 0 deletions (all `create mode`); pushed, remote `feature/engine-move` matches local HEAD; tree clean after push

## Acceptance Verification

| # | Criterion (verbatim) | Result | Notes |
|---|---|---|---|
| 1.1 | `grep -rn "agentic_scripts" tests/` returns zero hits. | PASS | Run verbatim from the clone root: zero hits (exit 1) |
| 1.2 | `uv run pytest tests/test_roadmap_dev.py tests/test_roadmap_dev_scan.py tests/test_roadmap_dev_pipeline.py -q` — all green (these run hermetically against the new package; they must pass BEFORE any smoke-test work, proving the package move is behavior-identical). | PASS | 75 passed, 0 failed; ran BEFORE any smoke file existed in the clone |
| 2.1 | `uv run pytest tests/smoke/test_smoke_roadmap_dev.py -q` — all 6 tests green. | PASS | 6 passed (registered_noop, idle_gate_first_poll, idle_gate_second_poll_opens, sessions_active_no_drain, config_fault, empty_listing_stub) |
| 2.2 | The patched seam is `autonomous_task.runner.read_active_sessions` in both conftest and the 3 test-local patches (grep shows the new name; zero `agentic_scripts`). | PASS | 1 conftest autouse + 3 test-local patches; zero `agentic_scripts` in `tests/` |
| 2.3 | No test references `gate_last_ok`, `--only`, `load=`, MAIL_*, or the old repo's staging path. | PASS | All five greps clean (`idle_gate_last_ok` is the new engine's key and is distinct from `gate_last_ok`) |
| 3.1 | `uv run pytest -q` in the clone: 100% of the moved suite green (core + scan + pipeline + smoke; hundreds of tests). | PASS | 81/81 green. Note: the moved suite is 81 tests, not "hundreds" — the plan's parenthetical over-estimated the source file sizes; the operative requirement (100% of the moved suite green) is met exactly |
| 3.2 | `uv run ruff check .` clean. | PASS | "All checks passed!" — no pyproject change needed (no ruff `exclude`; tests already in scope) |
| 3.3 | `grep -rn "agentic_scripts" src/ tests/ config/ pyproject.toml .gitignore` — zero hits. | PASS | Per the orchestrator refinement (tests/ zero; `config/` allows exactly the one allowlist line): exactly 1 hit repo-wide — `config/workflows.yaml:27: - y2d2/agentic_scripts` (plan-mandated GitHub repo id, a data value); `src/`, `tests/`, `pyproject.toml`, `.gitignore` all zero |
| 3.4 | Commit landed on `feature/engine-move`, pushed; `plans.md`/`README.md` not in the diff. | PASS | Commit `OC: Move roadmap-dev test suite (core, scan, pipeline, smoke) adapted to the standalone runner` (see `git log` for SHA) on `feature/engine-move`, pushed (remote ref verified to match local HEAD); `git diff --stat` lists only the 8 new test files (all `create mode`); `plans.md`/`README.md` absent; `git status` clean after push |

## Blockers

None — no criterion failed and no guessed adaptations were made. Three findings for
the orchestrator (none weaken a criterion):

1. **Stub-text "verbatim" deviation (required by the criteria)** — the plan prescribed
   reusing the OLD repo's T5 staging file text *verbatim*. That file's 3rd line reads
   "Reconciled automatically by the **agentic_scripts** `roadmap-dev` workflow
   (see README)" — a verbatim copy would place an `agentic_scripts` string inside
   `tests/`, directly violating criterion 3.3 and your refinement (tests/ must be
   zero). The adapted test therefore carries the 4-line header with that one token
   rewritten to `autonomous_task` (identical mechanical rewrite as everywhere else;
   the other 3 lines are byte-identical). Test intent fully preserved: header-only
   stub → `parse_listing` → `[]`. Flagged per the "report any deviation" instruction.
2. **Docstring prose in the pure files mentions removed machinery — left untouched
   (no adaptation made, per your guardrail)** — `test_roadmap_dev_scan.py` (line 5) and
   `test_roadmap_dev_pipeline.py` (line 13) module docstrings say the workflow "is
   driven directly (NOT via ``scheduler.run``)", and `test_roadmap_dev.py` has the test
   `test_extract_report_sections_matches_oc_todo_behavior` (name + docstring citing the
   oc_todo parallel). These are prose/name references, not functional ones: the pure
   files' *imports* are exactly the sanctioned set (`config`, `state`, `git`, `agent`,
   `workflows.base`, `workflows.roadmap_dev`), both docstring statements remain
   factually true in the new repo (there is no scheduler at all; the `oc_todo`
   parallel lives on in the old repo's kept suite), and the `admin_repo=None` kwargs
   are valid because `WorkContext` in the frozen `workflows/base.py` still carries the
   `admin_repo` field. I did NOT edit them (guardrail: no guessed adaptations); the
   freeze-check diff is therefore still empty. If you want them reworded, that is a
   doc-polish decision for a later task (work-plan Task 4 cites these docstrings).
3. **Micro-deviation in the smoke port (docstring only)** — the source
   `_bare_remote` helper's docstring cross-referenced `:mod:`tests.test_git``
   (a module NOT moved into this repo); I dropped that dangling cross-reference and
   kept `:mod:`tests.test_roadmap_dev_pipeline`` (which is present). No test logic
   touched.

## Next Steps

- None required for the test move — the clone's suite is green and committed.
- Orchestrator decision point on finding 2 (reword the two "NOT via ``scheduler.run``"
  docstring lines + the `oc_todo`-named test, or leave them as historical prose).
- Task 3 of the global plan (setup/infra) can proceed; note from Task 1's report still
  stands: if CPython 3.12 parity with the source env is wanted, add a `.python-version`
  pin there (this suite passed on 3.14.7 as-is).
