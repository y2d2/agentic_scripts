# Task Plan: T1 — config section, per-workflow gate types, idle gate

**Purpose:** Foundation for the `roadmap-dev` workflow: a validated `roadmap_prompts` config section, a `gate:` type per workflow entry, and a session-based idle gate with the two-poll rule — without changing existing workflows' behavior.

## Objective

Extend `agentic_scripts` configuration and the scheduler so that (a) the new `roadmap-dev` workflow can be registered (`enabled: false` for now, `gate: idle`, agent `planner-enhanced`) with its execution parameters in a new `roadmap_prompts` section, (b) the scheduler supports per-workflow gate types — existing workflows keep the machine-global quiet-window gate **byte-for-byte in behavior**, while `idle`-gate workflows are invoked on every non-skipped fire (their drain decision is made inside the workflow from a `gate_open` flag), and (c) a new idle gate evaluates "no active interactive OpenCode sessions" with the existing two-consecutive-polls rule under a **separate** state key. All unit-tested hermetically.

## Context

- Work in `/workspace/Python/agentic_scripts` (branch `feature/roadmap-dev-workflow`). Read first: `src/agentic_scripts/config.py`, `src/agentic_scripts/scheduler.py`, `src/agentic_scripts/state.py`, `config/workflows.yaml`, `tests/test_config.py`, `tests/test_gate.py`, `tests/test_scheduler.py` (and `tests/smoke/test_smoke_base.py`).
- Style: Google-style docstrings (Purpose/Rationale/Args/Returns/Raises/Example), `from __future__ import annotations`, dataclass `field` defaults for optional config sections (mirror the `OCTodo` / `_EMPTY_OC_TODO` pattern in `config.py`), `ConfigError(section_and_field, message)` names the dotted offending field. Ruff lint+format clean (`uv run ruff check` / `uv run ruff format --check`).
- **Live-verified idle mechanism (2026-11-21, this box):** the shared OpenCode service (TUIs attach to it; `--standalone` worker runs do NOT) writes state to `~/.local/state/opencode/service.json` = `{"id": …, "version": …, "url": "http://127.0.0.1:<port>", "pid": …, "password": "…"}` (port is dynamic per service start). `GET <url>/api/session/active` with **HTTP Basic auth, user `opencode`**, password = that file's `password`, returns `{"data": {<sessionID>: {"type": "running"}, …}}` — one entry per open interactive session. Stdlib only (`urllib.request`, `json`, `os`, `pathlib`) — no new dependencies.
- The scheduler today (`scheduler.py::run`): parse args → load config → dotenv → logger → `acquire_lock` (skip if held) → `evaluate_gate` (unless `--force`) → **if gate closed: early-return 0 before any workflow runs** → `list_enabled(config, only)` → loop workflows → last-run summary. The early-return must change to: skip all workflows only when the gate is closed AND no *selected* workflow has `gate == "idle"`.
- Gate streak state lives in the `scheduler` state document: existing key `gate_last_ok` (quiet gate). The idle gate uses a **new** key `idle_gate_last_ok`, same mechanics (first idle poll records timestamp; second idle poll within `poll_interval_minutes + gate_poll_tolerance_minutes` opens; any non-idle poll clears it). `machine.gate_polls_required` (1|2) applies to both.
- `WorkContext` (`workflows/base.py`): add field `gate_open: bool = True` — for an idle-gate workflow: the idle gate's verdict for this fire (True on `--force`); the scheduler sets it. Do not remove any existing field.
- Config section shape (validated, fail-fast, human-readable field names in errors):

```yaml
roadmap_prompts:            # optional section; absent → empty defaults (workflow no-ops)
  allowed_repos: []         # required key; list of 'owner/name' ids (same regex as oc_todo); empty = no-op
  listing_repo: y2d2/ARP_prompts   # required key when section present; 'owner/name'
  listing_repo_url: ""      # optional; non-empty string or "" (clone-URL override / test seam; default derived: git@github.com:<listing_repo>.git)
  listing_path: plans.md    # required key; non-empty string
  listing_branch: main      # required key; non-empty string
  run_timeout_minutes: 480  # optional; int >= 1; default 480
  test_commands: {}         # optional; per-repo test command; keys must be in allowed_repos (oc_todo pattern)
  repo_urls: {}             # optional; per-repo clone-URL override (local fixtures); keys must be in allowed_repos
```

- `workflows` entry additions: each entry may carry `gate: quiet_window` (default) or `idle`. Validate: must be one of the two; error names `workflows.<name>.gate`. Absent → `quiet_window`. `WorkflowEntry` gains `gate: str = "quiet_window"`.
- Shipped `config/workflows.yaml`: add the `roadmap_prompts:` section (as above, `allowed_repos: []`) and the entry:

```yaml
  roadmap-dev:
    enabled: false          # flipped to true in a later task (module lands later)
    module: agentic_scripts.workflows.roadmap_dev
    agent: planner-enhanced
    gate: idle
```

  Disabled entries are not import-checked (existing behavior in `_load_workflows`) — the module does not exist yet; that is fine.
- New module `src/agentic_scripts/sessions.py`:
  - `ServiceState` dataclass: `url: str`, `password: str`, `pid: int | None`.
  - `read_service_state(path: Path | None = None) -> ServiceState | None` — default path `Path.home() / ".local/state/opencode/service.json"`; missing/unreadable/invalid JSON → `None`.
  - `active_session_count(service_state: ServiceState | None, *, timeout: int = 5) -> int` — `None` state → 0. Otherwise `GET <url>/api/session/active` with `urllib.request` + `base64` Basic auth header `opencode:<password>`; parse `{"data": {...}}` → number of keys; **any** transport/HTTP/parse failure → 0 (logged via `logging.getLogger("agentic_scripts.sessions")` WARNING with the reason). Never raises.
  - `read_active_sessions(path: Path | None = None) -> int` — convenience: `active_session_count(read_service_state(path))`.
  - Test seam: module-level `_urlopen = urllib.request.urlopen` alias (mirror `github.py`) so tests patch `agentic_scripts.sessions._urlopen` with a canned-response fake; `ServiceState` is injectable so tests never touch the real home dir.
- Scheduler changes (keep the public API of `run`/`evaluate_gate`/`GateResult` stable; existing tests must pass unmodified):
  - New `evaluate_idle_gate(now, state, machine, active_sessions) -> GateResult` in `scheduler.py` (or a new `gates` module if cleaner — prefer `scheduler.py`): `active_sessions` is an int (probe result, taken as argument — no psutil-style imports inside); idle ⇔ `active_sessions == 0` (NO quiet window, NO load check); 2-poll mechanics identical to `evaluate_gate` but writing/reading key `idle_gate_last_ok` and reasons like `"no active sessions (1st idle poll recorded)"` / `"no active sessions (2nd consecutive idle poll)"` / `"N active session(s)"`. Reuse `GateResult` (its `load*`/`window_open` fields carry zeros/True for idle-gate results — document this; alternatively a tiny `IdleGateResult` if it keeps tests clearer, but prefer reuse with documented semantics).
  - `run()`: after the quiet-gate evaluation (unchanged), compute `selected = list_enabled(config, only)` **before** the gate-closed early-return (move `list_enabled` up; usage-error handling unchanged). If the quiet gate is closed and `not any(e.gate == "idle" for e in selected)` → early-return exactly as today. Else proceed into the workflow loop; for each entry: if `entry.gate == "quiet_window"` and the quiet gate was evaluated closed and not forced → skip this workflow (log `WORKFLOW <name> status=skipped reason=quiet gate closed`, add a `skipped(...)` summary line, continue). Idle-gate workflows run; before the loop (non-forced) evaluate the idle gate once via `evaluate_idle_gate(now, StateStore(state_dir), config.machine, read_active_sessions())` and pass its `open` verdict as `WorkContext.gate_open` for idle-gate workflows (quiet-gate workflows get `gate_open=True` — they are already gated). Forced run: `gate_open=True` for all.
  - `--force` semantics unchanged: all selected workflows run.
- Keep `evaluate_gate` (quiet) 100% behavior-compatible: it still writes `gate_last_ok`; the idle gate never touches that key.

## Tasks

### Task 1: `sessions.py` module + tests
- **Files:** `src/agentic_scripts/sessions.py` (create), `tests/test_sessions.py` (create)
- **Do:** Implement `ServiceState`, `read_service_state`, `active_session_count`, `read_active_sessions`, `_urlopen` seam exactly as in Context. Tests (all hermetic, no real home dir, no network): state file parsing (valid → fields; missing file → None; corrupt JSON → None; missing keys → None); `active_session_count` with fake `_urlopen` (data with 0/1/5 keys → 0/1/5; HTTP error → 0 + no raise; timeout-ish transport error → 0; non-JSON body → 0); `read_service_state` against a `tmp_path` service.json (url/password read; nonexistent path → None).
- **Acceptance:**
  1. `uv run pytest tests/test_sessions.py -v` passes; every probe-failure path returns 0 without raising.

### Task 2: config section + gate field
- **Files:** `src/agentic_scripts/config.py` (modify), `config/workflows.yaml` (modify), `tests/test_config.py` (modify)
- **Do:** Add `RoadmapPrompts` frozen dataclass (fields per Context shape), `_load_roadmap_prompts` (fail-fast, dotted field names: e.g. `roadmap_prompts.repos[0]`-style errors → use `roadmap_prompts.allowed_repos[i]`, `roadmap_prompts.listing_repo`, …), empty-defaults dataclass `_EMPTY_ROADMAP_PROMPTS` when the section is absent (add `roadmap_prompts` to `Config` + `allowed_sections`), `WorkflowEntry.gate` with validation (unknown value → `ConfigError("workflows.<name>.gate", …)`; absent → `"quiet_window"`). Ship the `roadmap_prompts` section + `roadmap-dev` entry (`enabled: false`) in `workflows.yaml` (with brief comments in the house style). Tests: valid section loads (defaults: absent section → `allowed_repos == []`, `run_timeout_minutes == 480`); each invalid field names its dotted name (bad `listing_repo` format, `run_timeout_minutes: 0`, `test_commands` key not in `allowed_repos`, non-list `allowed_repos`, bad `gate` value, unknown top-level section still rejected); `gate` default on existing entries (`noop`/`mail-keeper`/`oc-todo` → `quiet_window`); full `load_config` on the shipped `workflows.yaml` still succeeds with the new disabled entry.
- **Acceptance:**
  1. `uv run pytest tests/test_config.py -v` passes (old + new tests).
  2. `load_config(PROJECT_ROOT/"config/workflows.yaml")` returns `Config` with `workflows` containing `roadmap-dev` (`enabled=False`, `gate="idle"`, `agent="planner-enhanced"`) and `roadmap_prompts.allowed_repos == []`.

### Task 3: idle gate + scheduler wiring
- **Files:** `src/agentic_scripts/scheduler.py` (modify), `src/agentic_scripts/workflows/base.py` (modify — `WorkContext.gate_open` field, default True, docstring note), `tests/test_gate.py` (modify), `tests/test_scheduler.py` (modify; add new test cases in the existing style)
- **Do:** `evaluate_idle_gate` per Context (injected `active_sessions: int`, state key `idle_gate_last_ok`, 2-poll mechanics, `GateResult` reuse documented). `WorkContext.gate_open: bool = True`. `run()` rewire per Context: `list_enabled` before the early-return; early-return only when quiet gate closed AND no selected `idle` workflow; per-workflow gate dispatch (quiet-gate workflows skipped with a log + `skipped` summary line when their gate is closed; idle-gate workflows run and receive `gate_open` from the one-shot idle-gate evaluation; forced → all run, `gate_open=True`). Non-forced idle evaluation happens when at least one selected idle-gate workflow exists (to keep the streak honest) — pass the probe result (call `read_active_sessions()` once). Keep the GATE log line for the quiet gate; add an analogous `GATE … verdict=… reason=no active sessions (…)` INFO line for the idle gate when evaluated. Tests: idle gate 2-poll (fresh state: 1st poll records → closed; 2nd within `poll_interval+tolerance` → open; beyond → reset; non-idle poll clears; `gate_polls_required=1` → opens immediately; state key is `idle_gate_last_ok`, `gate_last_ok` untouched); scheduler: (a) quiet gate closed, only quiet-gate workflows selected → identical skip behavior as today (existing tests pass unmodified); (b) quiet gate closed + enabled idle-gate workflow selected → loop runs, idle workflow invoked with `gate_open=False` (fake workflow module via a test config pointing `module:` at a small in-test module or a tmp module file — follow existing `test_scheduler.py` patterns for injected configs), quiet workflows skipped with summary lines; (c) quiet gate closed + idle gate open → idle workflow gets `gate_open=True`; (d) `--force` → all run, `gate_open=True`, no gate state writes; (e) `--only roadmap-dev` with it disabled → usage error unchanged.
- **Acceptance:**
  1. `uv run pytest tests/test_gate.py tests/test_scheduler.py tests/test_base_noop.py -v` passes (pre-existing tests unmodified and green).
  2. With the quiet gate closed, an idle-gate workflow's `run()` IS invoked (proven by a test), receiving `ctx.gate_open` equal to the idle gate verdict.
  3. `uv run ruff check src tests` and `uv run ruff format --check src tests` clean.

## Out of Scope

- No changes to `oc_todo.py`, `mail_keeper.py`, `noop.py`, `agent.py`, `git.py`, `github.py`, `state.py` (except nothing — read-only here).
- No `roadmap_dev` module yet; no smoke tests (later tasks). No drain logic.
- No CLI changes (`--force`/`--only` semantics preserved).

## Notes

- **[Assumption] `GateResult` reuse for idle verdicts** (load fields zeroed, `window_open=True`) is acceptable; if it hurts test clarity, a thin `IdleGateResult` dataclass with the same fields is fine — but then `run()` must not leak it into quiet-gate log lines.
- **[Note] The idle gate has NO quiet window and NO load check** — "idle" means "no interactive sessions", per the reviewed plan (load-based would self-block; user's explicit choice).
- **[Note] Streak state keys must not collide:** quiet=`gate_last_ok`, idle=`idle_gate_last_ok`, both in `state/scheduler.json`.
- **[Note] `--force` bypasses BOTH gates** and must not write either streak key (matches existing force behavior for the quiet gate).
- **[Note] Keep the single lock model** — no new locks in this task.
