# lightweight-dev Output — Task: gate_config

**Task:** #1    **Session:** ses_e011892daffe20FqX6B9uyG7Gs    **Date:** 2026-11-21

## Summary

Implemented all 3 subtasks of Task 1 — the `roadmap-dev` foundation — in
`/workspace/Python/agentic_scripts` (branch `feature/roadmap-dev-workflow`, no branch
switches):

- **Subtask 1 (`sessions.py`):** New stdlib-only module probing the shared OpenCode
  service for active interactive sessions: `ServiceState` dataclass,
  `read_service_state` (default `~/.local/state/opencode/service.json`; missing/unreadable/
  corrupt/missing-required-key → `None`), `active_session_count` (Basic auth
  `opencode:<password>` → `GET <url>/api/session/active`, counts `{"data": {...}}` keys;
  **any** transport/HTTP/timeout/parse failure → 0 with a WARNING via
  `logging.getLogger("agentic_scripts.sessions")`; never raises), `read_active_sessions`
  convenience, and the `_urlopen = urllib.request.urlopen` test seam (mirrors
  `github.py`). 21 hermetic tests (no real home dir, no network).
- **Subtask 2 (config):** Validated `roadmap_prompts` section in `config.py`
  (`RoadmapPrompts` frozen dataclass, `_load_roadmap_prompts` with dotted fail-fast errors
  like `roadmap_prompts.allowed_repos[0]` / `roadmap_prompts.listing_repo` /
  `roadmap_prompts.run_timeout_minutes`, `_EMPTY_ROADMAP_PROMPTS` defaults when absent,
  `allowed_repos` required / `listing_repo` + `listing_path` + `listing_branch` required
  when section present, `run_timeout_minutes` int ≥ 1 default 480, `test_commands`/
  `repo_urls` keys must be in `allowed_repos`), added to `Config` + `allowed_sections`.
  `WorkflowEntry.gate` (`"quiet_window"` default | `"idle"`, unknown → `ConfigError`
  naming `workflows.<name>.gate`). `config/workflows.yaml` ships the `roadmap_prompts`
  section (`allowed_repos: []`, `listing_repo: y2d2/ARP_prompts`, …) and the
  `roadmap-dev` entry (`enabled: false`, `module: agentic_scripts.workflows.roadmap_dev`,
  `agent: planner-enhanced`, `gate: idle`). 15 new tests; `test_shipped_config_loads`
  order assertion updated to include the new entry (required by the plan's file list).
- **Subtask 3 (scheduler):** `evaluate_idle_gate(now, state, machine, active_sessions)`
  in `scheduler.py` — idle ⇔ `active_sessions == 0` (no quiet window, no load check),
  identical 2-poll mechanics under the separate `idle_gate_last_ok` key (reasons
  `"no active sessions (1st idle poll recorded)"` / `"(2nd consecutive idle poll)"` /
  `"(single idle poll)"` / `"N active session(s)"`), reusing `GateResult` with
  documented sentinel semantics (load fields 0.0, `window_open=True`); `evaluate_gate`
  is 100% behavior-compatible (still owns `gate_last_ok` only). `WorkContext.gate_open:
  bool = True` added (docstring noted, no field removed). `run()` rewired:
  `list_enabled` moved before the gate-closed early return (usage-error handling
  unchanged); early return only when the quiet gate is closed AND no selected workflow
  has `gate == "idle"`; quiet-gated workflows are skipped with
  `WORKFLOW <name> status=skipped reason=quiet gate closed` + a `skipped(…)` summary
  line when their gate is closed; the idle gate is evaluated once per non-forced run
  (only when an idle-gated workflow is selected, keeping the streak honest) via
  `read_active_sessions()`, its verdict passed as `ctx.gate_open`, and an analogous
  `GATE now=… active_sessions=… verdict=… reason=no active sessions (…)` INFO line is
  logged; `--force` runs all selected workflows with `gate_open=True` and writes neither
  streak key. 7 new idle-gate tests (incl. key-collision and corrupt-state) and 4 new
  scheduler tests (probe workflow via tmp package records `ctx.gate_open` in state).

Scope discipline held: no changes to `oc_todo.py`, `mail_keeper.py`, `noop.py`,
`agent.py`, `git.py`, `github.py`, or `state.py` (the 7 out-of-scope files in the
second commit below are **whitespace-only** ruff re-normalization, AST-verified); no
`roadmap_dev` module created; `roadmap-dev` ships `enabled: false`.

## Files

| File | Action | Why |
|---|---|---|
| `src/agentic_scripts/sessions.py` | create | Active-session probe (`ServiceState`, `read_service_state`, `active_session_count`, `read_active_sessions`, `_urlopen` seam) per plan Context. |
| `tests/test_sessions.py` | create | 21 hermetic tests: state-file parsing, 0/1/5-key counts, Basic-auth header, all probe-failure paths → 0 without raising. |
| `src/agentic_scripts/config.py` | modify | `RoadmapPrompts` + `_EMPTY_ROADMAP_PROMPTS` + `_load_roadmap_prompts` (dotted fail-fast), `roadmap_prompts` in `Config`/`allowed_sections`, `WorkflowEntry.gate` with validation. |
| `config/workflows.yaml` | modify | Ships `roadmap_prompts` section (`allowed_repos: []`) and disabled `roadmap-dev` entry (`gate: idle`, `agent: planner-enhanced`) with house-style comments. |
| `tests/test_config.py` | modify | 15 new tests (absent defaults, shipped load, valid roundtrip, every invalid field naming its dotted name, gate default/validation); shipped-order assertion extended for the new entry. |
| `src/agentic_scripts/scheduler.py` | modify | `evaluate_idle_gate` (separate `idle_gate_last_ok` key, documented `GateResult` reuse), `_idle_gate_line`, `run()` gate-dispatch rewire per plan; `run`/`evaluate_gate`/`GateResult` public API stable. |
| `src/agentic_scripts/workflows/base.py` | modify | `WorkContext.gate_open: bool = True` field + docstring note (no existing field touched). |
| `tests/test_gate.py` | modify | 7 new `evaluate_idle_gate` tests (2-poll, tolerance reset, non-idle clear, `polls_required=1`, key separation, corrupt state); existing tests byte-identical. |
| `tests/test_scheduler.py` | modify | 4 new gate-dispatch tests (quiet-closed + idle wf runs with `gate_open=False`/`True`, `--force` all-run/no gate state/probe-never-called, `--only roadmap-dev` disabled no-op); existing tests byte-identical. |
| `src/agentic_scripts/workflows/{mail_keeper,oc_todo}.py`, `tests/{test_github,test_mail_prune,test_oc_todo,test_oc_todo_pipeline}.py`, `tests/smoke/test_smoke_oc_todo.py` | modify (separate commit `e86e717`) | Pre-existing ruff 0.17.1 format drift at HEAD (7 files failed `ruff format --check` **before** this task); whitespace/line-wrap only — every file AST-identical to HEAD. Required for the repo-wide format gate (see Blockers note). |

## Build / Tests

- `uv run pytest tests/test_sessions.py -v`: PASS — 21 passed
- `uv run pytest tests/test_config.py -v`: PASS — 39 passed
- `uv run pytest tests/test_gate.py tests/test_scheduler.py tests/test_base_noop.py -v`: PASS — 30 passed (pre-existing tests unmodified)
- `uv run pytest` (full suite, hermetic): PASS — 254 passed in ~38s
- `uv run ruff check src tests`: PASS — "All checks passed!"
- `uv run ruff format --check src tests`: PASS — "43 files already formatted"
- Commit 1 (`e86e717`, whitespace-only drift, 7 files) + Commit 2 (`c7f493a`, task files, 9 files) on `feature/roadmap-dev-workflow`; **not pushed** (orchestrator pushes between waves); no `planning/` file committed.

## Acceptance Verification

| # | Criterion (verbatim) | Result | Notes |
|---|---|---|---|
| T1.1 | `uv run pytest tests/test_sessions.py -v` passes; every probe-failure path returns 0 without raising. | PASS | 21/21 green. Failure paths covered: HTTP 401, `URLError` (connection refused), `TimeoutError`, non-JSON body, missing/`data`-not-a-mapping — all assert `== 0` with no exception; `None` state short-circuits with zero HTTP calls. |
| T2.1 | `uv run pytest tests/test_config.py -v` passes (old + new tests). | PASS | 39/39 green (24 pre-existing + 15 new; `test_shipped_config_loads` order assertion updated as the plan's file list mandates). |
| T2.2 | `load_config(PROJECT_ROOT/"config/workflows.yaml")` returns `Config` with `workflows` containing `roadmap-dev` (`enabled=False`, `gate="idle"`, `agent="planner-enhanced"`) and `roadmap_prompts.allowed_repos == []`. | PASS | Proven by `test_roadmap_prompts_shipped_loads` (also asserts listing fields + `run_timeout_minutes == 480`). |
| T3.1 | `uv run pytest tests/test_gate.py tests/test_scheduler.py tests/test_base_noop.py -v` passes (pre-existing tests unmodified and green). | PASS | 30/30 green; `git diff` confirms only module docstring/import lines changed in those two files — every pre-existing test body byte-identical. |
| T3.2 | With the quiet gate closed, an idle-gate workflow's `run()` IS invoked (proven by a test), receiving `ctx.gate_open` equal to the idle gate verdict. | PASS | `test_gate_closed_idle_workflow_runs_gate_open_false` (quiet gate closed on window, probe=1 → idle gate closed → probe workflow's `run` records `gate_open: False`) and `test_gate_closed_idle_gate_open_runs_gate_open_true` (2nd idle poll within tolerance → `gate_open: True`); quiet-gate noop skipped with `WORKFLOW noop status=skipped reason=quiet gate closed` + `noop=skipped` summary line in both. |
| T3.3 | `uv run ruff check src tests` and `uv run ruff format --check src tests` clean. | PASS | Both clean at final state (after the AST-identical drift commit — see Blockers note). |

## Blockers

None — but one item **needs orchestrator attention** (disclosed per scope discipline):

- **Out-of-scope whitespace commit `e86e717`:** 7 files outside this task's file list
  (`oc_todo.py`, `mail_keeper.py`, `test_github.py`, `test_mail_prune.py`, `test_oc_todo.py`,
  `test_oc_todo_pipeline.py`, `test_smoke_oc_todo.py`) were format-dirty at HEAD under the
  installed ruff 0.17.1 (verified on pristine HEAD copies with the repo's `pyproject.toml`:
  "7 files would be reformatted"), while the plan-level acceptance #6 demands ruff
  "clean across the repo" and the dispatch mandates `ruff format --check src tests` clean
  as the final gate — impossible without normalizing them. I ran `ruff format`, verified
  **every one of the 7 files AST-identical to its HEAD version** (zero logic change), and
  committed them separately (`e86e717`) so the task commit `c7f493a` matches the plan's
  file scope exactly. If the orchestrator objects, `e86e717` is a single
  whitespace-only commit and can be reverted/renormalized later; note that until then
  (or until it lands) the repo will fail `ruff format --check src tests` again.

## Next Steps

- Orchestrator: push the branch when the wave completes (I did not push, per dispatch).
- Review commit `e86e717` (whitespace-only drift) — keep or re-do under a different
  policy; it is intentionally separate from the task commit.
- Task 2 (`roadmap_dev` pure core) can now consume `Config.roadmap_prompts` /
  `WorkflowEntry.gate`; Task 6 flips `roadmap-dev` to `enabled: true` (the module does
  not exist yet, so the entry must stay disabled until then).
- Remember the idle-gate probe semantics for smoke tests: probe failure = 0 active
  sessions = idle (WARNING-logged); `read_active_sessions` is the seam to patch
  (`agentic_scripts.scheduler.read_active_sessions`).
