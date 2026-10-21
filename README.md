# agentic_scripts

Autonomous workflows that run on this 24/7 server **only when it is idle**. A load-aware
scheduler (quiet time window + sustained low load) gates a timer-triggered entry point; when
the gate is open, the registered workflows run one at a time. When the gate is closed, the run
is a fast, logged no-op that touches nothing. Every run is auditable afterwards.

Workflows plug in as new registered modules — no scheduler changes.

## What / why

- **Goal:** keep this rig doing useful background work (resolving `OC-todo:` comments into PRs;
  triaging the local maildir backup into the `ARP_roadmap` admin vault) without ever competing
  with interactive LLM inference or daytime use.
- **How:** a timer (every 30 min) invokes a stateless entry point that checks the gate itself.
  The gate opens only after *two consecutive idle polls* (~30 min apart) — one idle blip must not
  open it. An exclusive file lock means overlapping timer fires are skipped, never double-processed.

## Setup

```bash
git clone <this repo> /workspace/Python/agentic_scripts   # already here on this machine
cd /workspace/Python/agentic_scripts
bash scripts/setup.sh
```

`setup.sh` is idempotent and safe to re-run (it is also the documented recovery after a container
restart, because this container has no init system to restart cron for us). It:

1. syncs the `uv` environment (runtime + the `dev` extra — `uv sync --extra dev`);
2. checks `GITHUB_PAT` (warns if missing; required only by workflows that open PRs);
3. verifies the `admin_repo` clone from the config (needed by mail-keeper);
4. verifies the global OpenCode agent for every *enabled* workflow that declares one
   (`~/.config/opencode/agents/<name>.md`; base-only state with `noop` passes trivially);
5. creates the runtime dirs (`state/`, `logs/`, `sandbox/`);
6. installs the 30-minute timer — via systemd on real hosts, or cron in this container
   (installs the `cron` package if absent and starts the daemon).

Exit code `0` iff every step printed `[OK]` (a missing `GITHUB_PAT` is a `[WARN]`, not a failure).

## Configuration

Single declarative file: `config/workflows.yaml`. Validated at start-up with fail-fast,
human-readable errors naming the offending field.

### Machine section

| Key | Default | Meaning |
|-----|---------|---------|
| `machine.quiet_window.start` / `.end` | `22:00` / `08:00` | Quiet window (crosses midnight; `start > end`). |
| `machine.load_threshold` | `2.0` | 1-min load average must be **strictly below** this. |
| `machine.poll_interval_minutes` | `30` | Timer cadence; also the gate's poll-spacing reference. |
| `machine.gate_polls_required` | `2` | Consecutive idle polls needed to open the gate (`1` opens on the first). |
| `machine.gate_poll_tolerance_minutes` | `10` | Slack allowed between two idle polls (so a 35-min gap still counts). |

### Paths section

Absolute paths, resolved by the config loader. All three are gitignored:

- `paths.state_dir` — durable per-workflow state (JSON), consulted before any action.
- `paths.log_dir` — per-run logs + the `last-run.txt` summary.
- `paths.sandbox_dir` — scratch area for workflow work.

### Agent section

`agent.model`, `agent.steps` — defaults for the shared agent-runner wrapper (the `steps` cap is
the sanctioned stop-and-report budget knob; OpenCode has no native token budget).

### Workflows section

Ordered mapping of registered workflows. Each entry:

- `enabled` — whether the scheduler runs it;
- `module` — dotted Python module exposing a `create(config) -> Workflow`;
- `agent` — global OpenCode agent name, or `null` for non-agent workflows (e.g. `noop`).

**Adding a workflow = write a new module + add an entry here.** No scheduler changes.

## Environment variables

| Var | Required | Purpose |
|-----|----------|---------|
| `GITHUB_PAT` | by PR-opening workflows only | GitHub personal access token for opening PRs. Lives in `.env` (0600) or the environment — never in the config file or git. |

`.env.example` is committed; `setup.sh` creates a 0600 `.env` from it if absent.

## Running

```bash
uv run agentic-scripts run                 # gate-checked (the timer path)
uv run agentic-scripts run --force         # bypass the gate (operator override / smoke test)
uv run agentic-scripts run --only noop     # run a single workflow by name
uv run agentic-scripts run --verbose       # DEBUG-level console output
uv run agentic-scripts run --config PATH   # alternate config file
```

Exit-code contract: `0` = ran, skipped (lock held), or gate-closed; `2` = config/usage fault.
Per-workflow failures are logged and never change the exit code — the next poll retries, and state
is consulted before acting, so a retry is safe.

## Timer

- **This container (no systemd):** cron entry `*/30 * * * * cd <root> && uv run agentic-scripts run >> logs/cron.log 2>&1`.
- **Real hosts:** the shipped `systemd/agentic-scripts.{service,timer}` units (rendered by
  `setup.sh`, which substitutes the repo root).

To (re)install the timer, just re-run `bash scripts/setup.sh` — it detects systemd vs cron and is
idempotent. **After a container restart**, re-running setup is required: the cron daemon does not
survive it (no init system here).

## Logs

- `logs/run-<run_id>.log` — full per-run log (INFO file level), one file per run.
- `logs/last-run.txt` — short human-readable summary, always overwritten:

  ```
  run: 20261020T220001Z
  trigger: gate            # or: force
  gate: CLOSED now=... load1=13.43 threshold=2.0 window=closed reason=load above threshold
  workflows: -             # e.g. noop=ok(0 items, 1 action, 0 errors)
  overall: skipped         # or: ok / error
  ```

## Smoke test

Hermetic end-to-end proof of the base paths — gate-closed no-op, forced open run, two-step gate
opening, lock exclusivity, audit outputs, and idempotent re-runs. All clock/load inputs are
injected; no real `opencode`, no real repos, no network.

```bash
uv run pytest tests/smoke/ -v
```

## Extending with a new workflow

1. Add a module under `src/agentic_scripts/workflows/` exposing `create(config) -> Workflow`.
2. Register it in `config/workflows.yaml` (`enabled`, `module`, `agent`).
3. If it needs an agent, make sure the global OpenCode agent exists
   (`~/.config/opencode/agents/<name>.md`) — `setup.sh` verifies this and fails fast if not.

The scheduler, gate, lock, state, logging, and agent-runner primitives are shared — a workflow
never contains its own timer or lock logic.
