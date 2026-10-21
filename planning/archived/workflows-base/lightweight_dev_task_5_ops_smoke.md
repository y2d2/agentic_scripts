# Task 5 Result: Setup, Ops & Smoke Test (base)

**Status:** DONE — all acceptance criteria met; committed and pushed.
**Commit:** `a7e5c32` on `plan/agentic-workflows` (pushed to `github.com:y2d2/agentic_scripts.git`).

## Objective

Deliver the turnkey ops layer for the agentic_scripts base: an idempotent `scripts/setup.sh`,
shipped systemd units, a user-facing `README.md`, and hermetic smoke tests proving the base
paths (gate-closed no-op, forced open run, two-step gate, lock exclusivity, audit outputs,
idempotent re-runs) — plus a live end-to-end verification in this container.

## Changes made

Six owned files created/modified (nothing else):

| File | What it does |
|------|--------------|
| `scripts/setup.sh` | Idempotent turnkey setup: uv sync (`--extra dev`), GITHUB_PAT check, admin-repo + registered-workflow-agent verification, runtime dirs, systemd→cron detection with 30-min timer install. Exit 0 iff no `[FAIL]`. |
| `systemd/agentic-scripts.service` | Oneshot unit for real hosts (rendered by setup.sh via `__ROOT__` placeholder). |
| `systemd/agentic-scripts.timer` | 30-min `OnCalendar` timer, `Persistent=true`, for real hosts. |
| `README.md` | What/why, config reference, env-var list, run commands, timer (re)install, log formats, smoke test, workflow-extension contract. |
| `tests/smoke/__init__.py` | Smoke-test package marker. |
| `tests/smoke/test_smoke_base.py` | 5 hermetic end-to-end tests (injected clock/load; no real opencode/repos/network). |

### setup.sh behavior (this container path)

- Detects no systemd (`systemctl is-system running` fails) → cron path.
- Installs the `cron` package via apt if absent, starts the daemon (`service cron start`).
- Registers an idempotent crontab entry tagged `# agentic-scripts`:
  `*/30 * * * * cd <root> && uv run agentic-scripts run >> <root>/logs/cron.log 2>&1`
- On re-run, reports `[OK] cron entry already present` and changes nothing.
- Agent check is data-driven over *enabled* workflows with a non-null `agent`; base-only state
  (`noop`, `agent: null`) prints `[OK] no agent-backed workflows registered` and passes trivially.

## Acceptance evidence

### 1. Clean setup run (fresh container, cron absent) — exit 0

```
[OK] uv found (/root/.local/bin/uv)
Resolved 11 packages in 2ms
Checked 10 packages in 0.42ms
[OK] venv synced (uv sync --extra dev)
note: created /workspace/Python/agentic_scripts/.env from .env.example (chmod 600)
[WARN] GITHUB_PAT missing (required by workflows that open PRs; base-only state does not need it)
[OK] admin_repo is a git repo: /workspace/Obsidian/ARP_roadmap
[OK] no agent-backed workflows registered
[OK] runtime dirs present (state, logs, sandbox)
... (apt-get install cron output) ...
[OK] cron installed
[OK] cron daemon running
[OK] cron entry installed (*/30, log: /workspace/Python/agentic_scripts/logs/cron.log)
note: container has no init system — after a container restart, re-run `bash scripts/setup.sh` to re-register the cron daemon.

[OK] setup complete (no failures)
=== exit: 0 ===
```

### 2. Timer installed and verifiable via crontab -l

```
$ crontab -l
# agentic-scripts
*/30 * * * * cd /workspace/Python/agentic_scripts && uv run agentic-scripts run >> /workspace/Python/agentic_scripts/logs/cron.log 2>&1
```

### 3. Re-running setup on an already-configured machine changes nothing

```
$ bash scripts/setup.sh | grep -E "cron entry|setup complete"
[OK] cron entry already present
[OK] setup complete (no failures)
```

### 4. Lint / format / full test suite

```
$ uv run ruff check .
All checks passed!
$ uv run ruff format --check .
41 files already formatted
$ uv run pytest tests/ -q
...................................................................      [100%]
67 passed in 12.53s
```

(62 pre-existing + 5 new smoke tests.)

### 5. Smoke test (hermetic, injected clock/load)

```
$ uv run pytest tests/smoke/ -v
tests/smoke/test_smoke_base.py::test_smoke_gate_closed_noop PASSED       [ 20%]
tests/smoke/test_smoke_base.py::test_smoke_forced_open_run PASSED        [ 40%]
tests/smoke/test_smoke_base.py::test_smoke_two_step_gate_opens PASSED    [ 60%]
tests/smoke/test_smoke_base.py::test_smoke_lock_exclusivity PASSED       [ 80%]
tests/smoke/test_smoke_base.py::test_smoke_idempotent_rerun PASSED       [100%]
============================== 5 passed in 0.81s ===============================
```

### 6. Live gate-closed run (real clock, real load) — exit 0 in <5s, no side effects

```
$ time uv run agentic-scripts run
real    0m0.235s
exit=0
--- last-run.txt ---
run: 20261021T141036Z
trigger: gate
gate: CLOSED now=2026-10-21T14:10:36.633549 load1=7.62 threshold=2.0 window=closed reason=outside quiet window and load above threshold
workflows: -
overall: skipped
--- noop.json exists? ---
ls: cannot access 'state/noop.json': No such file or directory
```

### 7. Live forced run (bypasses gate) — end-to-end success

```
$ uv run agentic-scripts run --force
exit=0
--- last-run.txt ---
run: 20261021T141047Z
trigger: force
gate: FORCED
noop=ok(0 items, 1 actions, 0 errors)
overall: ok
--- noop.json ---
{
  "runs": 1
}
```

## Deviations

None. All six owned files implemented as specified; no Task 1–4 file modified. Two minor
implementation notes (both within spec):

- `setup.sh` creates a 0600 `.env` from `.env.example` if absent (the plan's "checks required env
  vars" step, made turnkey); a missing `GITHUB_PAT` is a `[WARN]`, not a failure, since base-only
  state does not open PRs.
- The systemd units use a `__ROOT__` placeholder that `setup.sh` substitutes with the repo root at
  render time (the units are shipped for real hosts; this container uses the cron path).

## Commit + push status

```
$ git add README.md scripts/setup.sh systemd/agentic-scripts.service \
      systemd/agentic-scripts.timer tests/smoke/__init__.py tests/smoke/test_smoke_base.py
$ git commit -m "OC: Add setup.sh, systemd units, README, and base smoke tests (Task 5)"
[plan/agentic-workflows a7e5c32] OC: Add setup.sh, systemd units, README, and base smoke tests (Task 5)
 6 files changed, 484 insertions(+)
$ git push
To github.com:y2d2/agentic_scripts.git
   6034c13..a7e5c32  plan/agentic-workflows -> plan/agentic-workflows
```

Staged only the six owned files explicitly (no `git add -A`); the untracked `planning/`
orchestration files and gitignored `logs/`/`state/`/`sandbox/` artifacts were not committed.
