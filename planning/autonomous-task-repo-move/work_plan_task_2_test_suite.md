# Task Plan: Move + adapt the roadmap-dev test suite

**Purpose:** Port the roadmap-dev test suite (pure core, scan, pipeline, smoke) into the
new package so a fresh clone + `uv sync` yields a fully green run with zero
`agentic_scripts` references.

## Objective

In `/workspace/Python/autonomous_task_overview` (branch `feature/engine-move`, where
Task 1 already landed the `autonomous_task` package: `runner.py` single-workflow runner,
trimmed `config.py`, copied primitives), move and adapt the four roadmap-dev test files
plus the two conftests from `/workspace/Python/agentic_scripts/tests/` so that
`uv run pytest -q` is 100% green.

## Context

- **Target repo:** `/workspace/Python/autonomous_task_overview`, branch
  `feature/engine-move` (already pushed). Package `autonomous_task` under `src/`;
  runner module `autonomous_task/runner.py` exposes `run(argv, *, now, run_id)` (NO
  `load` parameter — the quiet-window/load gate does not exist in this engine),
  `evaluate_idle_gate`, `acquire_lock`, `GateResult(open, reason, now)`.
  `config/workflows.yaml` is TRIMMED: sections `machine` (quiet_window,
  poll_interval_minutes, gate_polls_required, gate_poll_tolerance_minutes — no
  load_threshold), `agent`, `paths`, `roadmap_prompts` (live 9-repo allowlist,
  listing `y2d2/autonomous_task_overview`/`plans.md`/`main`). There is NO `workflows:`
  section, no `oc_todo:`, no `admin_repo:` — the engine has exactly one workflow
  (`roadmap-dev`) wired directly by the runner.
- **Source repo (read-only):** `/workspace/Python/agentic_scripts` (LIVE checkout —
  no changes, no test runs there). Source test files: `tests/test_roadmap_dev.py`
  (1,422 lines — pure core: identity, parsing, rendering, reconcile, state machine,
  brief/commit renderers), `tests/test_roadmap_dev_scan.py` (911 — discovery/scan),
  `tests/test_roadmap_dev_pipeline.py` (1,364 — drain pipeline with fakes),
  `tests/smoke/test_smoke_roadmap_dev.py` (434 — run()-level), `tests/conftest.py`
  (69), `tests/smoke/conftest.py` (29), plus `tests/smoke/__init__.py` (empty).
- **Why the smoke test needs adaptation (verified by the orchestrator):** the original
  asserts against (a) `--only roadmap-dev` (flag removed from the new CLI),
  (b) sibling workflows `noop`/`mail-keeper`/`oc-todo` skip lines (they don't exist
  here), (c) the quiet-gate state key `gate_last_ok` (the new runner never manages it —
  only `idle_gate_last_ok`), (d) a `load=` kwarg on `run()` (removed),
  (e) the MAIL_* env isolation fixture (no mail-keeper in this engine), and
  (f) the T5 staging skeleton `autonomous_task_overview/plans.md` in the OLD repo
  (the new repo's `plans.md` is the LIVE listing — not an empty scaffold).
- **Git conventions:** `OC:` prefix; explicit path staging (never `git add -A`);
  never touch/commit `plans.md` (live listing) or `.venv`.
- **Hermeticity rules (load-bearing):** all tests build isolated `tmp_path` workspaces;
  the idle-probe seam is the runner's TOP-LEVEL import of `read_active_sessions`
  (monkeypatch `autonomous_task.runner.read_active_sessions`); local bare-repo fixtures
  via `repo_urls`/`listing_repo_url` overrides (no network); git identity set per-test;
  `GITHUB_PAT` unset in smoke tests.

## Tasks

### Task 1: Move the pure test files (mechanical rewrite)
- **Files (create in the overview clone):** `tests/__init__.py` (empty — if the source lacks one, create to match the smoke pattern), `tests/conftest.py`, `tests/test_roadmap_dev.py`, `tests/test_roadmap_dev_scan.py`, `tests/test_roadmap_dev_pipeline.py`
- **Do:** Copy the three pure test files; in each, rewrite every `agentic_scripts.` import prefix → `autonomous_task.` (and docstring references to the package). No assertion or fixture changes: these files only import `Config`, `RoadmapPrompts`, `StateStore`, `Git`, `GitError`, `WorkContext`, `AgentResult`, and names from `autonomous_task.workflows.roadmap_dev` — all present in the new package with identical behavior.
  `tests/conftest.py`: same rewrite; the `base_config` fixture reads the shipped `config/workflows.yaml` (now the trimmed one) and rewrites `paths` + empties `roadmap_prompts.allowed_repos` — that keeps working unchanged. Drop/update comments that reference the removed gate/scheduler/multi-workflow machinery.
- **Acceptance:**
  1. `grep -rn "agentic_scripts" tests/` returns zero hits.
  2. `uv run pytest tests/test_roadmap_dev.py tests/test_roadmap_dev_scan.py tests/test_roadmap_dev_pipeline.py -q` — all green (these run hermetically against the new package; they must pass BEFORE any smoke-test work, proving the package move is behavior-identical).

### Task 2: Adapt the smoke suite
- **Files (create in the overview clone):** `tests/smoke/__init__.py`, `tests/smoke/conftest.py`, `tests/smoke/test_smoke_roadmap_dev.py`
- **Do:**
  1. `tests/smoke/conftest.py`: the autouse canned-probe fixture now patches `"autonomous_task.runner.read_active_sessions"` (same semantics: lambda → 0). Update the docstring (no mail-keeper, single-workflow runner).
  2. `tests/smoke/test_smoke_roadmap_dev.py` — port with these exact adaptations (everything else preserved):
     - Imports: `from autonomous_task.runner import run`; `from autonomous_task.workflows.roadmap_dev import parse_listing`. `SHIPPED_CONFIG = REPO_ROOT / "config" / "workflows.yaml"` (the trimmed shipped config).
     - DROP the `_isolate_mail_env` autouse fixture entirely (no mail-keeper exists in this engine — its docstring rationale no longer applies). KEEP the `_git_env` fixture.
     - Every `run([...])` call: drop the `load=(...)` kwarg (the new signature has no `load`); keep `now=` and `run_id=` (the seams the gate-timing tests rely on).
     - `test_smoke_roadmap_dev_registered_noop`: remove `--only roadmap-dev` from the argv (single-workflow runner — a forced run is always roadmap-dev). Keep the assertions: exit 0; log line `WORKFLOW roadmap-dev status=ok items_found=0 actions=1 errors=0`; last-run `trigger: force`, `roadmap-dev=ok(0 items, 1 actions, 0 errors)`, `overall: ok`; no `sandbox/roadmap-dev` dir; no `state/roadmap-dev.json`.
     - `test_smoke_roadmap_dev_idle_gate_first_poll`: keep the non-forced run with canned probe 0. KEEP assertions: `active_sessions=0`, `reason=no active sessions (1st idle poll recorded)`, `WORKFLOW roadmap-dev status=ok items_found=0 actions=1 errors=0`, last-run `trigger: gate` + `overall: ok`, `idle_gate_last_ok` is a str, no side-effect files. DROP: all `WORKFLOW noop/mail-keeper/oc-todo status=skipped reason=quiet gate closed` assertions, the `gate_last_ok is None` assertion (key no longer managed), and the quiet-gate reason line assertion (`reason=outside quiet window...` — no quiet gate in this engine).
     - `test_smoke_roadmap_dev_idle_gate_second_poll_opens`: same reduction — keep the t1→t2 (+30 min) sequence, the `verdict=OPEN` + `reason=no active sessions (2nd consecutive idle poll)` + `active_sessions=0` assertions, the workflow-invocation assertion, the streak-kept state assertion (`idle_gate_last_ok == first_poll`), no-side-effects; drop the sibling-skip lines and quiet-gate lines.
     - `test_smoke_roadmap_dev_sessions_active_no_drain`: keep structurally intact (local bare-remote fixtures, seeded 30-min-old streak, canned probe 2, real phase-1 scan, `gate_open=False` → `drain skipped (idle gate closed)`, 3 actions, clone dir created, no state file). Adapt: the config it builds comes from the trimmed shipped YAML (drop any reference to removed sections); drop the `load=` kwarg; keep all assertions (the `WORKFLOW roadmap-dev status=ok items_found=0 actions=3 errors=0` line, `f"roadmap-dev: owner/fixture — found 0 plan(s)"`, no `drain start`, streak cleared, clone dir, no state doc).
     - `test_smoke_roadmap_dev_config_fault`: keep unchanged apart from import rewrite (malformed `roadmap_prompts.allowed_repos` → exit 2, `roadmap_prompts.allowed_repos` named on stderr).
     - `test_smoke_roadmap_dev_scaffold_listing_empty`: the old repo's T5 staging skeleton no longer exists. Replace with: write the header-only listing stub (the 4-line `# plans — roadmap-dev listing` header the engine renders for an empty listing — reuse the exact text from the OLD repo's `autonomous_task_overview/plans.md` staging file, copied verbatim into a tmp file by the test) and assert `parse_listing(stub) == []`. Rename the test to `test_smoke_roadmap_dev_empty_listing_stub` and update its docstring.
     - Rewrite the module docstring to describe the new engine (single-workflow runner, no siblings, no mail isolation, no `--only`).
- **Acceptance:**
  1. `uv run pytest tests/smoke/test_smoke_roadmap_dev.py -q` — all 6 tests green.
  2. The patched seam is `autonomous_task.runner.read_active_sessions` in both conftest and the 3 test-local patches (grep shows the new name; zero `agentic_scripts`).
  3. No test references `gate_last_ok`, `--only`, `load=`, MAIL_*, or the old repo's staging path.

### Task 3: Full-suite verification + commit
- **Do:** `uv run pytest -q` (whole new repo), then `uv run ruff check .` (add `tests` to ruff's view if the pyproject's default excludes it — the source repo lints tests), then stage the new test files explicitly and commit `OC: Move roadmap-dev test suite (core, scan, pipeline, smoke) adapted to the standalone runner`, push.
- **Acceptance:**
  1. `uv run pytest -q` in the clone: 100% of the moved suite green (core + scan + pipeline + smoke; hundreds of tests).
  2. `uv run ruff check .` clean.
  3. `grep -rn "agentic_scripts" src/ tests/ config/ pyproject.toml .gitignore` — zero hits.
  4. Commit landed on `feature/engine-move`, pushed; `plans.md`/`README.md` not in the diff.

## Out of Scope
- Any test of the copied primitives' ORIGINAL coverage in the old repo (the old repo keeps its own suite — it is being cleaned in a later work-plan task).
- New test coverage beyond what the source files provide (adaptation, not authoring — except the scaffold-stub test replacement, which preserves the original's intent).
- Any change in `/workspace/Python/agentic_scripts`.

## Notes
- **[Assumption]** The pure test files (core/scan/pipeline) contain no references to the scheduler, mail-keeper, oc-todo, `--only`, or quiet-gate state — verified by the orchestrator's import scan (they import only config/state/git/agent/base/roadmap_dev). If a stray reference is found, adapt minimally in the same spirit and note it in the result report.
- **[Risk]** The pipeline tests drive the drain with fake runners and local git fixtures — they are the hermetic proof that the MOVED engine still executes jobs (slots, top-up, 480-min kill mapping, tests gate, report routing). A red here after Task 1 green = behavior drift in the copies; diagnose via the `diff <(sed ...)` freeze-check from Task 1's notes before "fixing" tests.
- **[Convention]** Keep the source tests' docstring style and fixture names (they document the seams; the docs in work-plan Task 4 cite them).
