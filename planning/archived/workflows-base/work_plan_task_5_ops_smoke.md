# Task 5: Setup, ops, README, smoke test

**Purpose:** Make the system turnkey on this host: an idempotent `scripts/setup.sh` (venv sync, env-var + admin-repo + registered-workflow-agent checks, systemd→cron detection with a 30-minute timer), shipped systemd units for real hosts, a README that serves as the user-facing manual, and a hermetic smoke harness that proves the base's end-to-end paths (gate-closed no-op, forced open run, lock exclusivity, audit, idempotent re-run) without waiting for the quiet window.

## Objective

Deliver `scripts/setup.sh`, `systemd/agentic-scripts.{service,timer}`, `README.md`, and `tests/smoke/test_smoke_base.py` such that: (a) `bash scripts/setup.sh` runs clean and idempotent on this container (cron path), (b) the 30-minute timer is installed and verifiable via `crontab -l`, (c) the smoke test proves both gate paths + lock + audit + idempotency with injected time, (d) a real `uv run agentic-scripts run --force` works end-to-end in the repo, (e) the README documents config, env vars, timer (re)install, and the workflow-extension contract.

## Context

- **Repo:** `/workspace/Python/agentic_scripts`, branch `plan/agentic-workflows`. **Tasks 1–4 are already merged** — the package (config/state/logging), scheduler + CLI (`agentic-scripts run [--force] [--only N] [--config P] [--verbose]`), agent runner + git helpers, and the notmuch reader all exist and pass their tests. Read the four task files + their result reports for the exact behaviors you are wiring up.
- **Environment (re-verified 2026-10-20):** Ubuntu 24.04 container, root user, **no systemd** (PID 1 = `bash`), **no cron package installed** (setup must install it: `apt-get install -y cron` + start the daemon — the daemon does NOT survive a container restart; re-running setup is the documented recovery). Python 3.12.3, `uv` 0.12.5. `/proc/loadavg` = 13.43 today (gate is closed right now on both clauses — convenient for live checks).
- **Shipped config (Task 1):** `config/workflows.yaml` registers only `noop` (agent: null). `admin_repo: /workspace/Obsidian/ARP_roadmap` (exists, is a git repo — verified). Agents `oc-todo-resolver` and `mail-keeper` already exist in `~/.config/opencode/agents/` (verified 2026-10-20) — but are NOT registered in the base config; the setup agent check is data-driven over *registered, enabled* workflows, so base-only state trivially passes and will keep passing after the workflow plans register their entries.
- **Exit-code contract (Task 2):** `run` exits 0 (ran / skipped / gate-closed), 2 (config/usage fault). `last-run.txt` + `run-<id>.log` formats are fixed (see `work_plan_task_2_scheduler.md` §5).
- **Prior art:** `/workspace/scripts/email-sync/setup-timer.sh` — mirror its systemd→cron detection structure (do NOT modify that repo; read it as reference).
- **Conventions:** bash `set -euo pipefail`; Google-style docstrings in Python; Ruff clean; README in English.
- **Parallel-safety:** you own ONLY `scripts/setup.sh`, `systemd/agentic-scripts.service`, `systemd/agentic-scripts.timer`, `README.md`, `tests/smoke/__init__.py`, `tests/smoke/test_smoke_base.py`. You are the only task in your wave — but you must not modify any file owned by Tasks 1–4 (fixing a bug in them = stop and report to the orchestrator instead).

## Tasks

### 1. Create `scripts/setup.sh`
Bash, `set -euo pipefail`, executable. Steps (each prints a `[OK]`/`[WARN]`/`[FAIL]` line; final summary table; exit 0 iff no FAIL):
1. **Resolve root**: `ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"`.
2. **uv**: `command -v uv` → else `[FAIL] uv not found (install: https://docs.astral.sh/uv/)`.
3. **Venv sync**: `uv sync` in `$ROOT` (idempotent; prints uv's own "up to date"/sync output). Then `uv sync --dev` is NOT needed (dev deps are in the default group — verify against Task 1's pyproject; if Task 1 put dev deps in an optional group, sync that group instead — check the file, don't assume).
4. **Env vars**: `GITHUB_PAT` — read from environment OR `$ROOT/.env` (line `GITHUB_PAT=`); if set → `[OK] GITHUB_PAT present`; else `[WARN] GITHUB_PAT missing (required by workflows that open PRs; base-only state does not need it)`. If `$ROOT/.env` is missing: copy `.env.example` → `.env`, `chmod 600`, print a note. If present: `chmod 600` (idempotent).
5. **Admin repo**: extract `admin_repo` from `$ROOT/config/workflows.yaml` with a `uv run python -c` one-liner (yaml is a runtime dep — parse properly, no grep). Path set + `git -C <path> rev-parse --is-inside-work-tree` true → `[OK]`; missing or not a repo → `[WARN] admin_repo ... (needed by the mail-keeper workflow)`.
6. **Registered-workflow agents**: `uv run python -c` reads the config and prints one line per *enabled* workflow entry with a non-null `agent`: `<name> <agent>`; for each, check `$HOME/.config/opencode/agents/<agent>.md` exists → `[OK]` / `[FAIL] agent <agent> not found (expected at <path>; agents live in the oc_config repo)`. Base-only state prints no lines (noop has agent null) → `[OK] no agent-backed workflows registered`.
7. **Runtime dirs**: `mkdir -p "$ROOT"/{state,logs,sandbox}` (idempotent).
8. **Timer (systemd → cron detection)**:
   - If `systemctl is-system running` succeeds (real systemd): render the shipped units (sed-substitute `__ROOT__` placeholder with `$ROOT`) into `/etc/systemd/system/`, `systemctl daemon-reload`, `systemctl enable --now agentic-scripts.timer`, `[OK] systemd timer enabled`.
   - Else (this container): cron path —
     - `command -v crontab` or `command -v cron` → else `apt-get update && apt-get install -y cron` (`[OK] cron installed`), then start the daemon: `service cron start` (or `/etc/init.d/cron start`; `pgrep -x cron` to confirm, else `[FAIL] cron daemon not running`).
     - Idempotent crontab entry (marker comment `# agentic-scripts`): if `crontab -l 2>/dev/null | grep -qF '# agentic-scripts'` → `[OK] cron entry already present`; else `crontab -l 2>/dev/null | sed '/# agentic-scripts/d'` + append:
       ```
       # agentic-scripts
       */30 * * * * cd __ROOT__ && uv run agentic-scripts run >> __ROOT__/logs/cron.log 2>&1
       ```
       (substituted) via `crontab -`. `[OK] cron entry installed`.
   - Print a final note: "container has no init system — after a container restart, re-run `bash scripts/setup.sh` to re-register the cron daemon."
9. **Summary**: print the check table + `setup complete`. Exit 0 iff zero `[FAIL]`.

### 2. Create the systemd units (shipped templates with `__ROOT__` placeholders; rendered by setup)
- `systemd/agentic-scripts.service`:
  ```
  [Unit]
  Description=agentic_scripts load-aware workflow run
  After=network.target

  [Service]
  Type=oneshot
  WorkingDirectory=__ROOT__
  ExecStart=__ROOT__/.venv/bin/python -m agentic_scripts run
  StandardOutput=append:__ROOT__/logs/systemd.log
  StandardError=append:__ROOT__/logs/systemd-err.log
  ```
- `systemd/agentic-scripts.timer`:
  ```
  [Unit]
  Description=Run agentic_scripts every 30 minutes

  [Timer]
  OnCalendar=*:0/30
  Persistent=true
  Unit=agentic-scripts.service

  [Install]
  WantedBy=timers.target
  ```
- Note in a comment header of each file: rendered by `scripts/setup.sh` (substitutes `__ROOT__`); the container host has no systemd — these are for real hosts.

### 3. Create `README.md` (overwrite the 1-line placeholder)
Structure (English, user-facing, no fluff):
1. **What** — one paragraph: load-aware autonomous workflows for a 24/7 dev machine; gate (quiet window + sustained low load), one workflow at a time under a lock, every run logged; currently registered: `noop` (demo); the OC-todo resolver and mail-keeper workflows ship as follow-on plans.
2. **Why** — two sentences: the machine is busy by day / idle at night; this runs work only when it won't fight the user, and every action is auditable in `logs/`.
3. **Quickstart** — `bash scripts/setup.sh`, `source .env` (or export GITHUB_PAT), verify the timer (`crontab -l` / `systemctl list-timers`), force a run (`uv run agentic-scripts run --force`), read `logs/last-run.txt`.
4. **How it works** — the gate (window 22:00–08:00 crossing midnight; load1 < 2.0 on 2 consecutive polls ≤ ~40 min apart; state in `state/scheduler.json`), skip-if-held lock (`state/.lock`), run order = config order, per-run `logs/run-<id>.log` + `last-run.txt`, exit-code contract (0/2).
5. **Configuration reference** — table of every key in `config/workflows.yaml` (section, key, type, default, meaning), incl. `gate_polls_required` ∈ {1,2} and the `workflows.*` entry shape (`enabled`/`module`/`agent`).
6. **Environment variables** — `GITHUB_PAT` (only in env/`.env`, never in git); note that secrets are passed through the process environment to agent runs.
7. **Timer** — what setup installs on this host (cron `*/30`, log to `logs/cron.log`), the container-restart caveat, the systemd units for real hosts, how to (re)install (`bash scripts/setup.sh`), how to check (`crontab -l`, `journalctl -u agentic-scripts.timer` on systemd hosts).
8. **How to add a workflow** — the extension contract (this is the hand-off the two workflow plans rely on): (1) new module `src/agentic_scripts/workflows/<name>.py` exposing `create(config) -> Workflow` implementing `Workflow.run(ctx)` (consult `ctx.state` before acting — idempotency; keep side effects in `ctx.sandbox_dir`/declared targets; return `WorkflowResult`, don't raise on business failures), (2) config entry under `workflows:` with `module:` (+ `agent:` if it spawns one), (3) optional `tests/smoke/test_smoke_<name>.py` + fixtures in `tests/smoke/fixtures/`, (4) re-run setup if a new agent is registered.
9. **Ops** — log locations, `--force`/`--only`/`--verbose`, state reset (delete `state/`), sandbox cleanup (`sandbox/`), troubleshooting (gate stays closed → check `last-run.txt` inputs; lock stuck → it self-releases on process death via flock; cron not firing → `pgrep cron`, re-run setup).
10. **Layout** — the canonical tree (copy from the global work plan) with one-line roles.
11. **References** — the three planning files, the Research cache entries (opencode event stream, steps budget, repo conventions, mail-keeper design).

### 4. Create `tests/smoke/__init__.py` + `tests/smoke/test_smoke_base.py`
- `__init__.py`: one-line docstring ("smoke harness — each workflow plan adds test_smoke_<name>.py + fixtures/ here").
- `test_smoke_base.py` — hermetic end-to-end via `scheduler.run(argv, now=..., load=...)` (injected clock/load; tmp config with tmp `state`/`logs`/`sandbox`; registered workflows: `noop` + the Task 2 slow-workflow tmp module if it's importable, else `noop` alone is sufficient for every assertion below). Tests:
  1. **gate-closed no-op**: now = local 13:00 (outside 22:00–08:00), low load → returns 0, wall time < 5s, run log contains `verdict=CLOSED`, `state/noop.json` absent, `last-run.txt` has `trigger: gate` + `overall: skipped`.
  2. **gate open on 2nd poll**: poll 1 at 23:00 (closed, `1st idle poll`), poll 2 at 23:30 (open, `WORKFLOW noop status=ok`, `overall: ok`).
  3. **forced run**: `--force` at 13:00 → 0, `RUN START force=True`, `gate: FORCED` in last-run.
  4. **lock exclusivity**: hold a flock on `state/.lock` in-test, then `run(["run", "--force", ...])` → 0, log contains `SKIP another run is in progress`, no new `RUN END`.
  5. **audit**: after items 2/3, the run log has, per workflow: `status=`, `items_found=`, `actions=`, `errors=`, `duration=`; `last-run.txt` ≤ 6 lines and contains `run:`, `trigger:`, `gate:`, `workflows:`, `overall:`.
  6. **idempotent re-run**: two consecutive forced runs → `state/noop.json` `runs == 2` (accumulation), second run exit 0, no `*.tmp` files left in `state/`.
  7. **no repo pollution**: after all tests, `git status --porcelain` in the repo (run via subprocess) contains no paths outside the pre-existing baseline (the smoke uses only tmp dirs + the repo's own gitignored `state`/`logs` from the live check below — assert no NEW tracked-file modifications).
- Do NOT test the agent runner or mail reader here (their own tests own that); the smoke is about the *scheduling* end-to-end path.

### 5. Live verification (manual, in this container — paste outputs into the result report)
1. `bash scripts/setup.sh` → full output; expect exit 0; all `[OK]` except possibly `[WARN] GITHUB_PAT missing` (acceptable in base-only state — but if the env actually has GITHUB_PAT set, it must be `[OK]`).
2. `crontab -l` → exactly one `# agentic-scripts` block, `*/30 * * * *` entry with the correct ROOT path.
3. `pgrep -x cron` → daemon running.
4. Re-run `bash scripts/setup.sh` → exit 0, `[OK] cron entry already present`, no duplicate crontab block (idempotency proof).
5. `uv run agentic-scripts run --force` (real repo, real clock) → exit 0; `logs/last-run.txt` shows `trigger: force`, `gate: FORCED`, `noop=ok`; `logs/run-*.log` present. (Artifacts live in gitignored dirs — do not commit.)
6. `uv run pytest tests/smoke -v` → all pass.
7. Full suite: `uv run pytest tests/ -v` → everything green (Tasks 1–4 + smoke).

## Acceptance criteria

1. `bash scripts/setup.sh` first run: exit 0; cron package installed; daemon running; exactly one marker-blocked `*/30` entry in `crontab -l`.
2. Second `bash scripts/setup.sh`: exit 0, `[OK] cron entry already present`, `crontab -l` unchanged (diff before/after is empty).
3. `uv run pytest tests/ -v` — the entire suite (tasks 1–4 + smoke) passes; smoke wall time < 30s.
4. `uv run agentic-scripts run --force` live check passes (item 5.5) with pasted output.
5. `uv run ruff check .` + `uv run ruff format --check .` clean.
6. README: all 11 sections present, no broken internal file references (every path mentioned exists), config table matches `config/workflows.yaml` key-for-key (verify by diffing against the file).
7. `git status --porcelain` shows only this task's 6 files as new (gitignored artifacts excluded from the commit).
8. Committed with `OC:` prefix, pushed to `plan/agentic-workflows`.

## Out of Scope

- The workflow implementations (OC-todo resolver, mail-keeper) and their smoke modules/fixtures — they extend `tests/smoke/` per the README §8 contract.
- Modifying Tasks 1–4 code (report bugs to the orchestrator instead of patching).
- Docker, CI, packaging/publishing, agent-definition changes, any change to `/workspace/scripts/email-sync/` (prior art is read-only reference).
- systemd install on this container (impossible — no systemd; the units are shipped + documented, inspection-verified only).

## Notes

- The cron daemon is the weakest link in this container (dies with the container, no init to restart it) — the README §7 caveat is load-bearing; keep it visible.
- `logs/cron.log` captures the timer's stderr/stdout (setup appends `>> __ROOT__/logs/cron.log`); the run's own detailed log is `logs/run-<id>.log` — document the distinction in README §9.
- If `apt-get` has no network in the container, setup must fail loudly with `[FAIL] apt-get install cron failed (no network?)` — do not fall back silently; report it.
- Keep setup.sh under ~150 lines; the python one-liners do the YAML work.
- The smoke `test 7` baseline: capture `git status --porcelain` at test start and assert the post-set is a subset (plus known gitignored noise) — do not hardcode the expected paths.
