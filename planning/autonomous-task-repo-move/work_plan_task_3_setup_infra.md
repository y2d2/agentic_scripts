# Task Plan: Setup script, systemd units, .env.example

**Purpose:** Give the overview repo its own turnkey `scripts/setup.sh` (uv sync, env,
agent + reachability preflight, runtime dirs, timer install with a `--skip-timer`
valve), systemd units for real hosts, and a minimal `.env.example` — so a fresh clone
becomes a running engine with one command.

## Objective

In `/workspace/Python/autonomous_task_overview` (branch `feature/engine-move`; the
`autonomous_task` package + green suite already landed in Tasks 1–2), add
`scripts/setup.sh`, `systemd/autonomous-task.service`, `systemd/autonomous-task.timer`,
and `.env.example`. End state: `bash scripts/setup.sh --skip-timer` exits 0 in the
clone with no crontab mutation; the timer path is structurally correct (this container
has no systemd, so the cron path is the live one).

## Context

- **Target repo:** `/workspace/Python/autonomous_task_overview`, branch
  `feature/engine-move` (pushed). The package is `autonomous_task` (console script
  `autonomous-task`); `uv sync --extra dev` is the documented env setup; config at
  `config/workflows.yaml` (sections `machine`/`agent`/`paths`/`roadmap_prompts`;
  `roadmap_prompts.allowed_repos` holds the live 9-repo list; `listing_repo` =
  `y2d2/autonomous_task_overview`).
- **Reference implementation (read-only):** `/workspace/Python/agentic_scripts/scripts/setup.sh`
  (173 lines) — the proven pattern: `[OK]/[WARN]/[FAIL]` reporting, `set -euo pipefail`,
  `ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"`, systemd→cron detection via
  `systemctl is-system running`, idempotent cron install keyed on a comment marker,
  absolute `uv` path in the cron line (a previous relative-`uv` cron line failed 78×
  with `uv: not found` — the marker comment records that fix).
- **Current live crontab (verified):** one entry under marker `# agentic-scripts`
  (fixed 2026-10-23): `*/30 * * * * cd /workspace/Python/agentic_scripts && PATH=/root/.opencode/bin:/root/.local/bin:/usr/local/bin:/usr/bin:/bin /root/.local/bin/uv run agentic-scripts run >> /workspace/Python/agentic_scripts/logs/cron.log 2>&1`. The new entry must use its OWN marker `# autonomous-task` so the two installers can never clobber each other, and must carry the same `PATH=` + absolute-`uv` hardening.
- **Agents (global, not versioned):** `~/.config/opencode/agents/planner-enhanced.md`
  and `~/.config/opencode/agents/lightweight-dev.md` (both verified present). The
  orchestrator agent is a code constant in the workflow; the worker is embedded in the
  brief text — the setup check verifies the two files exist (best-effort `[WARN]`-on-
  missing would be wrong: an engine without its orchestrator cannot drain — use `[FAIL]`
  like the source script's agent check).
- **Git conventions:** `OC:` prefix; explicit staging (never `git add -A`); never
  touch/commit `plans.md`.
- **`GITHUB_PAT`:** only needed for HTTPS-mirror clones via `roadmap_prompts.repo_urls`
  overrides (the default path is pure git over SSH). `.env.example` therefore carries
  ONLY the PAT (no MAIL_* — this engine has no mail-keeper).

## Tasks

### Task 1: `scripts/setup.sh`
- **Files:** `scripts/setup.sh` (create; `chmod +x`)
- **Do:** Model on the source script, adapted to this engine:
  1. Header docstring: purpose (turnkey setup for the autonomous-task engine), the
     re-run-after-container-restart note (cron daemon does not survive it — same as
     source), and the `--skip-timer` flag documented.
  2. `set -euo pipefail`, `ROOT` resolution, `ok/warn/fail` helpers, `FAILURES` counter
     (identical pattern).
  3. Steps:
     - **uv** present (FAIL if missing).
     - **Venv sync:** `uv sync --extra dev` in `$ROOT` (FAIL on error).
     - **Env:** if `$ROOT/.env` missing, `cp .env.example .env` + `chmod 600` (idempotent); `GITHUB_PAT` present in env or `.env` → OK, else **WARN** ("only needed for HTTPS-mirror clones via repo_urls; the engine's default path is git over SSH").
     - **Agents:** check `~/.config/opencode/agents/planner-enhanced.md` AND `~/.config/opencode/agents/lightweight-dev.md` exist → each OK; missing → FAIL (name the expected path; agents live in the global OpenCode config, not this repo).
     - **Roadmap preflight:** data-driven read of `roadmap_prompts` (same `uv run --project "$ROOT" python -c` pattern as the source): for each `allowed_repos` entry (honor `repo_urls` overrides; `""` → derive `git@github.com:<repo>.git`) and the listing repo, `timeout 15 git ls-remote --exit-code <url> HEAD` → OK, else **WARN** (reachability is advisory — the engine logs per-repo errors at run time; NO PAT here). Empty allowlist → OK "allowlist empty — engine is inert".
     - **Runtime dirs:** `mkdir -p state logs sandbox` (relative to `$ROOT`) → OK.
     - **Timer (only when `--skip-timer` is NOT passed):** systemd branch (render the two shipped units with `sed "s|__ROOT__|$ROOT|g"` into `/etc/systemd/system/autonomous-task.{service,timer}`, `daemon-reload`, `enable --now autonomous-task.timer`) / cron branch (ensure cron installed + running as in the source; idempotent install keyed on the `# autonomous-task` marker — first `sed '/# autonomous-task/d'` any stale lines, then append marker + entry). The cron entry:
       `*/30 * * * * cd $ROOT && PATH=/root/.opencode/bin:/root/.local/bin:/usr/local/bin:/usr/bin:/bin /root/.local/bin/uv run autonomous-task run >> $ROOT/logs/cron.log 2>&1`
       (same PATH + absolute uv as the old engine's fixed line). Re-run note for the no-init container (verbatim intent from the source).
  4. `--skip-timer` parsing: a simple `while` arg loop (`--skip-timer`, `-h/--help` with usage); unknown flag → usage + exit 2.
  5. Summary: `setup complete (no failures)` exit 0, else `exit 1` (source pattern).
- **Acceptance:**
  1. `bash scripts/setup.sh --skip-timer` in the clone exits 0; `crontab -l` is BYTE-IDENTICAL before and after the run (record both outputs in the result report); `state/ logs/ sandbox/` exist.
  2. `bash scripts/setup.sh --help` prints usage and exits 0; an unknown flag exits 2.
  3. `bash -n scripts/setup.sh` (syntax check) passes.
  4. The agent-check and preflight sections reference `planner-enhanced`/`lightweight-dev` and the 9 allowlisted repos + the listing repo (grep the script).

### Task 2: systemd units + `.env.example` + `.python-version`
- **Files:** `systemd/autonomous-task.service`, `systemd/autonomous-task.timer`, `.env.example`, `.python-version` (create)
- **Do:**
  1. `autonomous-task.service`: mirror the source unit — `[Unit] Description=autonomous-task engine run` + `After=network.target`; `[Service] Type=oneshot`, `WorkingDirectory=__ROOT__`, `ExecStart=__ROOT__/.venv/bin/python -m autonomous_task run`, `StandardOutput=append:__ROOT__/logs/systemd.log`, `StandardError=append:__ROOT__/logs/systemd-err.log`. Rendered-by-setup.sh comment header (same as source).
  2. `autonomous-task.timer`: `Description=Run autonomous-task every 30 minutes`; `OnCalendar=*:0/30`; `Persistent=true`; `Unit=autonomous-task.service`; `WantedBy=timers.target`.
  3. `.env.example`:
     ```
     # autonomous-task engine — secrets live here or in the environment, never in config/
     # GITHUB_PAT is optional: only HTTPS-mirror clones via roadmap_prompts.repo_urls use it.
     # The engine's default clone path is git over SSH (git@github.com:...).
     GITHUB_PAT=
     ```
- **Acceptance:**
  1. `sed "s|__ROOT__|/workspace/Python/autonomous_task_overview|g" systemd/autonomous-task.service` renders a unit whose `ExecStart` names `python -m autonomous_task run` (dry-render check only — do NOT install anything in `/etc/systemd` on this host).
  2. `.env.example` contains no MAIL_* variables and no secrets.

### Task 3: Re-verify suite + commit
- **Do:** `uv run pytest -q` (still green after the new files), `uv run ruff check scripts/ 2>/dev/null || true` (bash is not linted — skip), then stage `scripts/setup.sh`, `systemd/autonomous-task.service`, `systemd/autonomous-task.timer`, `.env.example` explicitly and commit `OC: Add setup.sh (--skip-timer), systemd units, .env.example`, push.
- **Acceptance:**
  1. Suite still 100% green; commit + push landed on `feature/engine-move`; `plans.md` untouched.

## Out of Scope
- Actually installing the live cron entry (work-plan Task 7, post-cutover-gate — this
  task proves the installer works with the valve CLOSED).
- Changes to the source repo's `scripts/setup.sh` (work-plan Task 6 removes its roadmap
  preflight there).
- Docs (work-plan Task 4 documents `setup.sh` usage in the README/WORKFLOW).

## Notes
- **[Risk]** If `--skip-timer` handling is wrong, the valve could install the timer
  early (double-engine exposure). Acceptance #1's byte-identical crontab check is the
  guard — treat a FAIL there as a task FAIL, not a warning.
- **[Assumption]** The cron daemon on this container persists between now and
  work-plan Task 7 (no container restart in between); if it died, Task 7's setup run
  reinstalls it (the script's cron branch handles that, as the source does).
- **[Convention]** Keep the `[OK]/[WARN]/[FAIL]` reporting style and step numbering
  pattern of the source script — operators know the format.
