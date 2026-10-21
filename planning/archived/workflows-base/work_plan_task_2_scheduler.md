# Task 2: Scheduler core (gate, lock, run loop, CLI)

**Purpose:** Implement the hybrid gate (quiet window + sustained low load), the skip-if-held exclusive lock, and the timer-agnostic run loop behind the `agentic-scripts` CLI — the core that makes every future workflow run on schedule, safely, and audibly.

## Objective

Deliver `agentic_scripts.scheduler` + `agentic_scripts.cli` (+ `__main__.py`) such that: (a) a timer-triggered run outside the quiet window or under load exits 0 within ~5s with NO workflow side effects; (b) two consecutive idle polls open the gate and the registered workflows run in config order; (c) a concurrent second invocation is skipped cleanly (skip, never deadlock); (d) every run writes `logs/run-<run_id>.log` + refreshes `logs/last-run.txt`; (e) a kill -9 mid-run leaves no torn state files and a re-invocation succeeds.

## Context

- **Repo:** `/workspace/Python/agentic_scripts`, branch `plan/agentic-workflows`. **Task 1 is already merged** — the skeleton, `Config`/`load_config` (dotted-field `ConfigError`), `StateStore` (atomic save, `StateError`), `setup_run_logger`/`write_last_run`/`new_run_id`, `Workflow` protocol, `WorkContext`, `WorkflowResult`, and the `noop` workflow exist exactly as specified in `work_plan_task_1_foundation.md`. Read those files before implementing; do not modify them except where this task explicitly says so (it does not).
- **Environment (re-verified 2026-10-20):** Ubuntu 24.04 container, no systemd (PID 1 = bash), no cron (Task 5 installs it), Python 3.12.3, `uv` 0.12.5. `/proc/loadavg` reflects the host kernel (readable; value today 13.43 — well above the 2.0 threshold, and 13:xx is outside the 22:00–08:00 window, so a real `run` right now must exit closed in ~5s).
- **Canonical config (from Task 1):** `machine.quiet_window.start/end` (crosses midnight, `start > end`), `machine.load_threshold` (2.0), `machine.poll_interval_minutes` (30), `machine.gate_polls_required` (1 or 2), `machine.gate_poll_tolerance_minutes` (10), `agent.*`, `paths.*` (absolute, resolved by the config loader), `workflows` (ordered entries with `enabled`/`module`/`agent`).
- **Conventions:** Google-style docstrings, Ruff clean, all automated tests hermetic (tmp config + tmp dirs + injected clock/load; NO real `opencode`, NO real repos). The shipped `config/workflows.yaml` registers only `noop` — the smoke test for this task must not depend on any other workflow.
- **Parallel-safety:** you own ONLY `src/agentic_scripts/scheduler.py`, `src/agentic_scripts/cli.py`, `src/agentic_scripts/__main__.py`, `tests/test_gate.py`, `tests/test_lock.py`, `tests/test_scheduler.py`. Do NOT touch `pyproject.toml`, `config/workflows.yaml`, `state.py`, `config.py`, `logging_setup.py`, or any file owned by Tasks 3/4/5. (The `console script` entry point `agentic_scripts.cli:main` is already declared in pyproject by Task 1.)

## Gate algorithm (canonical — implement exactly this)

All comparisons on local time `now` (the machine's clock).

```
window_open = QuietWindow.in_window(now)            # Task 1's method (midnight-crossing aware)
load_ok     = load1 < load_threshold                 # STRICT
idle        = window_open and load_ok

gate state: state/scheduler.json = {"gate_last_ok": "<iso8601 UTC>" | null}

evaluate(now, load1, machine, state) -> (open: bool, reason: str):
  if not idle:
      state.update("scheduler", "gate_last_ok", None)
      return False, "outside quiet window" | "load above threshold" | "outside quiet window and load above threshold"
  if machine.gate_polls_required == 1:
      return True, "single idle poll"
  prev = state.load("scheduler").get("gate_last_ok")
  if prev is not None and (now - prev) <= timedelta(minutes=poll_interval_minutes + gate_poll_tolerance_minutes):
      return True, "2nd consecutive idle poll"
  state.update("scheduler", "gate_last_ok", now.isoformat())
  return False, "1st idle poll recorded"
```

`prev` parses as UTC ISO-8601. `now` is a `datetime` (local, naive) throughout the gate; store UTC when persisting. Corrupt/missing `scheduler.json` → treat as `gate_last_ok = null` but do NOT clear-and-save over a corrupt file with different content silently: if `load` raises `StateError`, the scheduler logs ERROR and aborts the run with exit 2 (a corrupt state store is a real fault, not a gate input).

## Tasks

### 1. Create `src/agentic_scripts/scheduler.py`
- `@dataclass class GateResult:` `open: bool`, `reason: str`, `load1: float`, `load5: float`, `load15: float`, `window_open: bool`, `now: datetime`.
- `def read_load() -> tuple[float, float, float]` — wraps `psutil.getloadavg()`; isolated so tests can monkeypatch it.
- `def evaluate_gate(now: datetime, load: tuple[float, float, float], machine: Machine, state: StateStore) -> GateResult` — pure apart from the `state` writes described above. No I/O beyond state.
- `def acquire_lock(state_dir: Path) -> int | None` — opens `<state_dir>/.lock` (create, 0644), tries `fcntl.flock(fd, LOCK_EX | LOCK_NB)`; on `BlockingIOError` returns `None`; else returns the open fd (caller must `os.close` to release — closing releases the flock). Do NOT delete the lock file (unlink races).
- `def run(argv: list[str] | None = None, *, now: datetime | None = None, load: tuple[float, float, float] | None = None) -> int` — the full loop (see Run loop below). `now=None` → `datetime.now()`; `load=None` → `read_load()`. Returns the exit code (CLI calls `sys.exit(run(...))` — testable without `SystemExit`).
- `def list_enabled(config: Config, only: str | None) -> list[WorkflowEntry]` — config order, `enabled` filter, `only` filter (unknown `only` → raise `SchedulerUsageError(name)`).
- `class SchedulerUsageError(RuntimeError)` (message carries the offending workflow name); `class SchedulerError(RuntimeError)` for unexpected faults.
- Keep every function importable and small; the run loop assembles them.

### 2. Run loop (exact order inside `run()`)
1. **Parse args** (argparse, defined in `cli.py` but the parser-builder `build_parser()` must live in `scheduler.py` OR be importable from `cli.py` — your choice; `run(argv)` accepts raw argv and parses): `run` subcommand (default when first token is `run`; bare `agentic-scripts` with no subcommand → print help, exit 2); flags `--force` (bool), `--only NAME`, `--config PATH` (default `PROJECT_ROOT/config/workflows.yaml`), `--verbose` (bool).
2. **Load config**: `load_config(path)`; on `ConfigError` → print `config error: <message>` to stderr, return 2.
3. **Load .env**: `dotenv.load_dotenv(PROJECT_ROOT / ".env", override=False)` (missing file is fine).
4. **Run logger**: `run_id = new_run_id()`; `logger, log_path = setup_run_logger(config.paths.log_dir, run_id, verbose=verbose)`; log `RUN START force=<bool> only=<name|None>` at INFO.
5. **Lock**: `fd = acquire_lock(config.paths.state_dir)`; if `None` → log `SKIP another run is in progress` at INFO, `write_last_run([...one line...])` (see format), close nothing, return 0.
6. **Gate** (unless `--force`): `gate = evaluate_gate(now, load, config.machine, StateStore(config.paths.state_dir))`; log inputs + verdict at INFO, e.g. `GATE now=... load1=13.43 load5=... load15=... window=open threshold=2.0 prev_poll=... verdict=CLOSED reason=load above threshold`. If closed → log `RUN END gate=closed duration=...`, write last-run (see format), return 0.
7. **Resolve workflows**: `entries = list_enabled(config, only)` (usage error → log ERROR, return 2).
8. **Per workflow** (in order, never let one failure stop the rest): `importlib.import_module(entry.module)` (ImportError → record `status=error`, error string, continue); `wf = module.create(config)` (exception → record, continue); `ctx = WorkContext(config=config, state=StateStore(config.paths.state_dir), logger=logger.getChild(entry.name), run_id=run_id, workflow_name=entry.name, sandbox_dir=config.paths.sandbox_dir, admin_repo=config.admin_repo)`; `t0 = time.monotonic()`; `result = wf.run(ctx)`; on exception → `result = WorkflowResult(status="error", errors=[f"{type(e).__name__}: {e}"])`, log exception with traceback at ERROR; `result.duration_seconds = time.monotonic() - t0`; log `WORKFLOW <name> status=... items_found=... actions=<len> errors=<len> duration=<s>s`.
9. **Finish**: overall status = `error` if any workflow errored else `ok`; log `RUN END gate=<open|forced|closed> workflows=<n> errors=<n> duration=<s>s`; `write_last_run(...)` (format below); return 0 (per-workflow errors are logged, not fatal — the next poll retries; only config/usage faults exit 2).

### 3. Create `src/agentic_scripts/cli.py`
- `def main() -> None: sys.exit(run())` (imports `run` from `scheduler`). Docstring documents the console-script entry point.
- Nothing else — keep the CLI a 3-line shell over `run()`.

### 4. Create `src/agentic_scripts/__main__.py`
- `from agentic_scripts.cli import main` + `if __name__ == "__main__": main()` so `python -m agentic_scripts` works.

### 5. Run-log line formats (canonical — tests assert substrings, README documents them)

`logs/run-<run_id>.log` (INFO file level):
```
2026-10-20T22:00:01 INFO [agentic_scripts] RUN START force=False only=None
2026-10-20T22:00:01 INFO [agentic_scripts] GATE now=2026-10-20T22:00:01 load1=1.23 load5=1.50 load15=1.80 window=open threshold=2.0 prev_poll=2026-10-20T21:30:02Z verdict=OPEN reason=2nd consecutive idle poll
2026-10-20T22:00:05 INFO [agentic_scripts.noop] WORKFLOW noop status=ok items_found=0 actions=1 errors=0 duration=0.02s
2026-10-20T22:00:05 INFO [agentic_scripts] RUN END gate=open workflows=1 errors=0 duration=4.1s
```

`logs/last-run.txt` (always overwritten; 4–5 short lines):
```
run: 20261020T220001Z
trigger: gate
gate: CLOSED now=... load1=13.43 threshold=2.0 window=closed reason=load above threshold
workflows: -
overall: skipped
```
or, for a forced open run: `trigger: force`, `gate: FORCED`, `workflows: noop=ok(0 items, 1 action, 0 errors)`, `overall: ok`.

### 6. Write the tests (all hermetic; use `tmp_path`-based configs pointing at tmp `state`/`logs`/`sandbox` dirs — copy the shipped YAML, rewrite `paths`, `load_config` the copy)
- `tests/test_gate.py` (call `evaluate_gate` directly with injected `now`/`load`/`StateStore`):
  1. Out-of-window now + low load → closed, reason mentions window; `scheduler.json` `gate_last_ok` cleared to null.
  2. In-window now + high load (load1 ≥ threshold) → closed, reason mentions load; state cleared.
  3. In-window + low load, no prev → closed, reason `1st idle poll recorded`; state now holds `gate_last_ok`.
  4. Second poll 30 min later (within 30+10) → open, reason `2nd consecutive idle poll`.
  5. Second poll 45 min later (beyond tolerance) → closed, reason `1st idle poll recorded`; state reset to the newer now.
  6. `gate_polls_required: 1` config → open on the first idle poll.
  7. Corrupt `scheduler.json` (garbage bytes) → `StateError` propagates (no silent reset).
  8. Midnight-crossing window: now 01:00 → window open; now 13:00 → closed (using shipped defaults 22:00–08:00).
- `tests/test_lock.py`:
  1. `acquire_lock` on a fresh tmp dir → fd not None; close → second `acquire_lock` succeeds again.
  2. Hold a `fcntl.flock` on the same `.lock` path in-test, then `acquire_lock` → returns `None`.
- `tests/test_scheduler.py` (call `scheduler.run(argv, now=..., load=...)`):
  1. **Gate-closed no-op**: config with shipped window/thresholds; `now` = local 13:00 (or load 99.0) → returns 0 in < 5s (assert wall time < 5s), run log exists and contains `verdict=CLOSED`, `last-run.txt` exists, noop state file NOT created (no workflow side effects).
  2. **Forced open run**: `["run", "--force", "--config", cfg]` → 0; run log contains `RUN START force=True`, `WORKFLOW noop status=ok`, `RUN END gate=forced`; `state/noop.json` has `runs == 1`; `last-run.txt` has `trigger: force`.
  3. **Two-step gate**: poll 1 (`now` T, low load) → 0, closed; poll 2 (`now` T+30min, low load) → 0, open, `WORKFLOW noop status=ok` in the second run log.
  4. **Concurrency**: `run()` in a `subprocess` (spawn `uv run python -m agentic_scripts run --force --config <cfg>` twice with a small sleep between, OR in-thread with a workflow that sleeps — simplest robust: two subprocesses of a small driver script that imports `run` with a test-registered slow workflow) → exactly one `RUN END` line across both logs, exactly one `SKIP another run is in progress`. (You may register a slow test workflow via a tmp module on `sys.path` referenced in the tmp config — see item 5.)
  5. **Registry extensibility**: write a tmp module `slow_wf.py` (creates a workflow that `time.sleep(3)`s then returns ok), add it to the tmp config's `workflows`, force-run → both `noop` and `slow_wf` lines present, in config order. This proves "adding a workflow = new module + config entry, zero scheduler changes".
  6. **Kill mid-run, no torn state**: run the item-5 config in a subprocess; after ~1s `kill -9`; assert the process is gone; assert `state/noop.json` (if present) parses as valid JSON (atomic save — never torn); then a fresh forced run succeeds (exit 0).
  7. **--only unknown** → exit 2, stderr/log mentions the name.
  8. **Bare invocation / no subcommand** → `run([])` returns 2 (help shown).

## Acceptance criteria

1. `uv run pytest tests/test_gate.py tests/test_lock.py tests/test_scheduler.py -v` — all pass, no flaky wall-clock dependence (all times injected).
2. `uv run ruff check .` + `uv run ruff format --check .` clean (whole repo).
3. `uv run agentic-scripts run --help` and `uv run python -m agentic_scripts run --help` both work (entry point from Task 1 now resolves).
4. **Live gate-closed check (manual, in this container):** `uv run agentic-scripts run` (real clock, real load 13.43, 13:xx) → exits 0 in < 5s; `logs/last-run.txt` shows `trigger: gate` + `gate: CLOSED`; no `state/noop.json` created. Paste the command + output into the result report. (The container's repo-root `logs/` and `state/` are gitignored — expected artifacts, do not commit.)
5. `git status --porcelain` shows only this task's 6 files as new (plus the gitignored artifacts, which must NOT be staged).
6. Committed with `OC:` prefix, pushed to `plan/agentic-workflows`.

## Out of Scope

- Agent spawning, git ops, mail (Tasks 3/4); setup/systemd/README/smoke harness (Task 5).
- Modifying `pyproject.toml`, `config/workflows.yaml`, or any Task 1 file.
- cron/systemd installation (Task 5 owns the timer; this task is timer-agnostic by design).
- Real `opencode` invocations.

## Notes

- The gate is a **polling hybrid**: the timer fires often (30 min); only a *sustained* idle window (2 polls ~30 min apart) opens the gate — one idle blip must not open it. This is the user's core requirement ("wait until the machine is actually idle for ~1 hour").
- `--force` is the operator override AND the smoke-test path for "open" without waiting for the gate.
- Exit-code contract: 0 = ran, skipped (lock), or gate-closed; 2 = config/usage fault. Per-workflow failures NEVER change the exit code (they are logged; the next poll retries) — state is consulted before acting, so a retry is safe.
- Keep `evaluate_gate` free of psutil imports (load is passed in) so gate tests need no monkeypatching.
- If the item-4/6 subprocess tests turn out flaky in the container, prefer the in-process slow-workflow variant (item 5's tmp module) with `threading` + lock held across a sleep; document whichever you ship.
