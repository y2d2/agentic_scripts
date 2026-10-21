# agentic_scripts — Workflow Base Plan (Scheduler, Foundation, Ops)

**Purpose:** The shared foundation for the load-aware agentic workflow system in `agentic_scripts`: the load-aware scheduler core, the shared Python package foundation, and setup, ops, and smoke test. The two workflows build on this plan and live in sibling plans. Split from `agentic_workflows_plan.md` (2026-10-19; the original file is deleted — full pre-split content is in git history at `628df52`).

**Sibling plans (this repo):**
- `planning/workflows-oc-todo/workflows-oc-todo_plan.md` — OC-todo resolver workflow
- `planning/workflows-mail-keeper/workflows-mail-keeper_plan.md` — mail-keeper workflow

**Build order:** this plan first (scheduler + foundation must exist); the two workflow plans are then independent of each other.

## Objective

Build `agentic_scripts` into a small Python project of autonomous workflows that run on this 24/7 server only when it is idle. Two workflows ship now: (1) an **OC-todo resolver** that scans a configurable set of GitHub repos across all branches for `OC-todo:` comments and opens one pull request per resolved todo via a headless OpenCode agent (→ workflows-oc-todo plan); (2) a **mail-keeper** workflow that reads the local maildir backup (13,147 messages on 2026-10-19) through the maintained notmuch index, triages new mail, and keeps the `ARP_roadmap` admin vault up to date — provenance-tagged people/project notes and tracked todos — while draft replies are saved locally as files (never sent); vault changes are committed directly to the current branch with an `OC:` prefix and pushed (→ workflows-mail-keeper plan). Success = a fresh setup script brings the system up; with the gate open, each workflow produces its observable outputs idempotently; with the gate closed, runs exit as no-ops without touching any repo. Future workflows plug in as new registered modules without scheduler changes.

## Context

- **Greenfield repo.** `agentic_scripts` contains only a README (verified 2026-10-14). This plan family defines the whole system.
- **Environment (verified 2026-10-14):** Ubuntu 24.04 container where PID 1 is `bash` — **no systemd init, cron package not installed**; Python 3.12.3, `uv` 0.12.5, `psutil` 7.2.2 present; `gh` CLI absent. `/proc/loadavg` inside the container reflects the host kernel, so load-based gating works from inside.
- **Commit convention:** commits follow the `OC:` prefix (git-workflow skill).
- **Agent infrastructure:** local OpenCode + llama.cpp router with Qwen3.8-27B resident on the 24/7 rig (research: /workspace/Research/ai-agent-workflow/ — `LLM_configurations` topic). OpenCode agents have **no native token budget**; the sanctioned stop-and-report knob is the agent `steps` cap (research: /workspace/Research/ai-agent-workflow/agent-token-budget-steps.md). Headless invocation `opencode run` supports `--agent`, `--model`, `--dir`, `--auto`, `--format json`, `--title` (verified 2026-10-14 via `opencode run --help` on this machine).
- **OpenCode config environment (verified 2026-10-14):** the global OpenCode config at `~/.config/opencode` is itself a git repo → `git@github.com:y2d2/oc_config.git` (branch `feature/llamacpp-migration`), already holding the user's 8 purpose-built agents in `agents/` and 14 skills in `skills/`. Agent discovery is per session directory: project `.opencode/agent(s)/` found by walking up from the session's cwd, else global `~/.config/opencode/agent(s)/`; `opencode run --dir` sets the session directory (verified `opencode run --help` 2026-10-14; customize-opencode skill). Config loads once at start — agent/skill changes need an opencode restart.
- **Python/ops conventions:** `uv` + Ruff + pytest under `pyproject.toml` with `src/` layout is the adopted 2025/2026 stack; secrets in `.env` with 0600; timers or cron with self-checking entry points (research: /workspace/Research/ai-agent-workflow/repo-file-conventions-best-practices.md; /workspace/Research/home/email-m365-imap-oauth2-findings.md).

Workflow-specific context (mail corpus, mbsync WIP, v1 pipeline, mail-keeper design doc; OC-todo marker evidence, GitHub search limits) lives in the two workflow plans.

## Functional Tasks

### Task 1: Load-Aware Scheduler Core
- **Goal:** A single entry point, invoked by a timer, that decides whether the server is idle enough and, if so, runs the registered workflows one at a time. When idle is not confirmed, the run is a fast, logged no-op. Every run is auditable afterwards.
- **Why this approach:**
  - **[Decision: gate = hybrid window + load]** Value = quiet time window (default 22:00–08:00, crosses midnight) AND 1-min load average below a threshold (default 2.0) sustained across 2 consecutive polls (~30 min apart, stored between polls in the state area) because user chose hybrid gating (2026-10-14) and the rig serves interactive LLM inference during the day — a single low-load sample can be a transient dip (own analysis; 24/7 rig context in /workspace/Research/ai-agent-workflow/).
  - **[Decision: timer + self-check, not a daemon]** Value = a timer (default every 30 min) invokes a stateless entry point that performs the gate check itself, because user chose timer + self-check over a resident daemon (2026-10-14). The entry point is deliberately timer-agnostic so a daemon or manual `--force` run reuses the same gate logic.
  - **[Decision: trigger mechanism]** Value = cron entry on this machine (cron package installed by setup; verified not present 2026-10-14) plus a systemd timer/service unit shipped for real systemd hosts, because this container has no init system (PID 1 = `bash`, verified) — cron is the smallest reliable recurring trigger available here (own analysis of the verified environment; prior art: /workspace/scripts/email-sync/setup-timer.sh already implements the systemd→cron detection for the v1 pipeline).
  - **[Decision: load source]** Value = `/proc/loadavg` (via psutil) because inside the container it still reports host-kernel load, which is what "server load" means (own analysis; psutil verified present).
  - **[Decision: exclusivity]** Value = an exclusive file lock with skip-if-held semantics (no queueing): if a timer fires while a run is active, it logs and exits, because agent runs can outlast the 30-min interval and overlapping runs must never double-process (own analysis; idempotency is also enforced per-workflow in the two workflow plans).
  - **[Decision: logging]** Value = per-run log files in a gitignored log area plus a short human-readable last-run summary, because automation that acts on repos and mail must be auditable without a dashboard (own analysis).
  - **[Decision: testability]** Value = `--force` (bypass gate) and `--only <workflow>` flags, because acceptance testing must not wait for 22:00 or for the server to idle (own analysis).
- **Acceptance criteria:**
  - With load above threshold or outside the window, the entry point exits 0 within seconds, logs the gate inputs (time, load1/5/15, window state) and a "gate closed" verdict, and changes nothing on disk in any repo.
  - Two simultaneous invocations never run workflows concurrently (second logs "already running" and exits).
  - Each run's log records, per workflow: triggered/skipped, items found, actions taken, errors.
  - A new workflow can be enabled by adding it to the configuration's registered list without modifying scheduler logic.

### Task 2: Project Foundation
- **Goal:** A Python package that both workflows share: validated configuration, durable per-workflow state, git helpers, an agent-runner wrapper, and the mail reader — so future workflows are additive modules.
- **Why this approach:**
  - **[Decision: stack]** Value = Python 3.12 managed by `uv`, `src/` layout, Ruff for lint/format, pytest for tests, because this is the adopted 2025/2026 stack and the machine already has `uv` 0.12.5 + Python 3.12.3 (research: /workspace/Research/ai-agent-workflow/repo-file-conventions-best-practices.md; verified locally 2026-10-14).
  - **[Decision: configuration]** Value = one declarative config file (YAML) with sensible defaults plus a machine section (window, threshold, poll cadence), a workflow section (repo list, mail folder, admin repo path, caps), and an agent section (model, steps cap); validated at start-up with fail-fast, human-readable errors, because every deployment difference (repos, folders, thresholds) must be tunable without code edits (own analysis).
  - **[Decision: secrets]** Value = secrets (GitHub PAT) only via environment variables / `.env` with 0600, never in the config file or git, because the config is committed while secrets are not (research: /workspace/Research/home/email-m365-imap-oauth2-findings.md — credential handling pattern; own analysis).
  - **[Decision: state]** Value = a per-workflow durable state store (JSON) in a gitignored state area, keyed by stable identities (todo: repo + branch + commit SHA + path + line; email: Message-ID), because re-runs are the norm under a timer and every workflow must be idempotent (own analysis).
  - **[Decision: agent runner]** Value = one shared wrapper that launches `opencode run --agent <name> --model <configured> --dir <sandbox>` with a hard timeout and captures the JSON event stream into the run log, because both workflows need identical budgeting (agent `steps` cap), timeouts, and auditability, and `opencode run` exposes exactly these knobs (verified `opencode run --help` 2026-10-14; budgeting: /workspace/Research/ai-agent-workflow/agent-token-budget-steps.md).
  - **[Decision: agent definitions live in the global OpenCode config, not this repo]** Value = the purpose-built agents (`oc-todo-resolver`, `mail-keeper`) + their skills are defined in `~/.config/opencode/agents/` + `skills/` (versioned in the `oc_config` git repo) and referenced by name from this repo's runner, because (a) agent discovery follows the session directory — the workflow launches sessions with `--dir` targeting the vault / maildir / worktrees, where a project-scoped agent from `agentic_scripts` would not resolve (customize-opencode skill; verified `opencode run --dir` 2026-10-14); (b) the mail-keeper design requires interactive Task-tool dispatch from *any* session ("check mail", "draft a reply to X"), which only a global agent supports (research: /workspace/Research/ai-agent-workflow/mail-keeper-agent-design.md); (c) the user's 8 existing purpose-built agents establish global `agents/` as the single source of truth, and the agent-config-pattern skill forbids defining the same agent name in two places. Setup verifies the required agents exist and fails fast with a clear message if not (own analysis). Agents carry `steps` caps (research: /workspace/Research/ai-agent-workflow/agent-token-budget-steps.md).
- **Acceptance criteria:**
  - Missing or invalid configuration aborts start-up with a message naming the offending field.
  - Killing a run mid-flight and re-invoking never duplicates side effects (state is consulted before any action).
  - Both workflows import the same gate, lock, state, git, and agent-runner primitives; no workflow contains its own timer or lock logic.

### Task 3: Setup, Ops & Smoke Test
- **Goal:** One setup script brings a fresh environment up; a documented smoke test proves both end-to-end paths without waiting for the gate.
- **Why this approach:**
  - **[Decision: setup idempotency]** Value = the setup script detects systemd vs cron (mirroring the detection logic already in /workspace/scripts/email-sync/setup-timer.sh), installs the cron package (absent, verified) and registers the 30-minute crontab entry (idempotent), syncs the `uv` environment, checks required env vars, verifies the admin repo clone, and verifies the required global OpenCode agents exist (`oc-todo-resolver`, `mail-keeper`) — failing fast with a clear message if not — safe to re-run after container restarts, because this container has no init system to restart services for us (verified 2026-10-14; prior art: email-sync setup-timer.sh; own analysis).
  - **[Decision: smoke test]** Value = `--force` runs against a local fixture repo (with planted `OC-todo:` comments on multiple branches) and a fixture `.eml`, asserting the acceptance outputs of the two workflow plans (workflows-oc-todo Task 1; workflows-mail-keeper Task 1), because gate-dependent behavior must be verifiable on demand (own analysis).
  - **[Decision: documentation]** Value = a README front-loading what/why, the config reference, the env-var list, and how to (re)install the timer, because future workflows and future-you will onboard via the README (research: /workspace/Research/ai-agent-workflow/repo-file-conventions-best-practices.md — README structure guidance).
- **Acceptance criteria:**
  - On a clean environment, one setup run + config + env vars → the next gate-open run (or `--force`) executes both workflows correctly.
  - The smoke test passes end-to-end (fixture PRs created, fixture mail processed) and can be re-run without side effects on real repos (fixture-only).
  - Re-running setup on an already-configured machine changes nothing and reports that state.

## Alternatives Considered

1. **Resident daemon polling load** — Rejected by user (chose timer + self-check, 2026-10-14); the timer-agnostic entry point keeps the option open.
2. **Agent definitions inside `agentic_scripts` (project-scoped)** — Rejected: agent discovery follows the session directory (`opencode run --dir`), and workflow sessions target the vault/maildir/worktrees where a project-scoped agent would not resolve; interactive Task dispatch from other projects would also break; the global config (`oc_config` repo) is the established single source of truth for the user's 8 existing agents (customize-opencode skill; agent-config-pattern skill).
3. **Raw LLM API calls instead of OpenCode CLI** — Rejected: loses the reusable agent/skill/config infrastructure and the `steps` stop-and-report budgeting that headless runs rely on (research: /workspace/Research/ai-agent-workflow/agent-token-budget-steps.md).
4. **CPU-idle-based gating** — Superseded by the user's hybrid window+load choice (2026-10-14).

## Notes

- **[Assumption]** Agent model defaults to the local Qwen3.8-27B via the llama.cpp router (24/7 rig, resident), overridable per workflow in config — consistent with the local-rig cost research → /workspace/Research/ai-agent-workflow/ (local-vs-subscription TCO, `LLM_configurations` topic).
- **[Risk]** No init system in this container (PID 1 = `bash`, cron not installed — verified 2026-10-14): the cron daemon must be started with the container; a container restart requires re-running the (idempotent) setup. Mitigation: systemd unit shipped for real hosts; setup re-run is a documented one-liner.
- **[Risk]** Long agent runs can overlap the next timer fire. Mitigation: skip-if-held lock; per-run caps and timeouts bound run length.
- **[Note]** Window/threshold/poll-cadence defaults (22:00–08:00, load1 < 2.0, 2 consecutive polls at ~30 min) are user-confirmed 2026-10-14 and all remain config-tunable.
