# Work Plan: agentic_scripts — Workflow Base (Scheduler, Foundation, Ops)

**Purpose:** Orchestration work plan for `planning/workflows-base/workflows-base_plan.md` — build the load-aware scheduler core, shared Python package foundation, and setup/ops/smoke harness. Sibling plans (workflows-oc-todo, workflows-mail-keeper) build on the primitives produced here and are OUT OF SCOPE for this work plan.

## Objective

Turn the greenfield `agentic_scripts` repo into a working, auditable, timer-driven system: a stateless entry point that gates on quiet-window + sustained low load, runs registered workflows one at a time under an exclusive lock, and logs every run — plus a shared Python package (validated config, durable state, git helpers, agent-runner wrapper, notmuch mail reader) and an idempotent setup script with a hermetic smoke test. Success = the base acceptance criteria of `workflows-base_plan.md` Tasks 1–3 hold with zero registered real workflows (a `noop` demo workflow proves the registry), and the system is ready for the two workflow plans to plug in as additive modules.

## Context (shared by all tasks)

- **Repo:** `/workspace/Python/agentic_scripts`, branch `plan/agentic-workflows` (up to date with origin). Commit prefix `OC:` (git-workflow skill). Greenfield: README + planning/ only.
- **Environment (re-verified 2026-10-20):** Ubuntu 24.04 container, PID 1 = `bash` (no systemd), **no cron package** (setup installs it), root user, no docker, no `gh` CLI. Python 3.12.3, `uv` 0.12.5, `psutil` 7.2.2, `notmuch` 0.38.3 at `/usr/bin/notmuch`, `opencode` 1.18.35. `/proc/loadavg` reflects host kernel (readable; live value today 13.43).
- **Stack:** `uv`-managed venv, `src/` layout, Ruff (lint+format), pytest. Runtime deps: `pyyaml`, `psutil`, `python-dotenv`. Dev deps: `pytest`, `ruff`. All declared in Task 1's `pyproject.toml` — later tasks MUST NOT touch pyproject.
- **Conventions:** Google-style docstrings (coding-standards skill), `uv run ruff check .` + `uv run ruff format --check .` clean, all automated tests hermetic: no real repos, no LLM inference, no live notmuch index, no side effects outside tmp dirs. Secrets only via env/`.env` (0600), never in config or git.
- **Agent infra:** local OpenCode + llama.cpp router; model string `openaiCompatible/Qwen3.8-27B` (global opencode config, provider `openaiCompatible` → `http://192.168.122.203:8081/v1`). `opencode run` flags verified: `--agent`, `--model`, `--dir`, `--auto`, `--format json`, `--title`, positional message. The `steps` cap lives in the agent frontmatter (sanctioned stop-and-report knob; research: /workspace/Research/ai-agent-workflow/agent-token-budget-steps.md). Both workflow agents (`oc-todo-resolver`, `mail-keeper`) **already exist** in `~/.config/opencode/agents/` (verified 2026-10-20).
- **`opencode run --format json` (v1.18.35) — verified from installed binary source, cached: /workspace/Research/ai-agent-workflow/opencode-run-json-event-stream.md** — stdout is pure NDJSON, one object per line: `{type, timestamp, sessionID, ...payload}`. Event types: `tool_use`, `step_start`, `step_finish`, `text`, `reasoning` (only with `--thinking`), `error`. Final assistant text = `part.text` of the **last** `type=="text"` event (several `text` events possible per run). Exit 0 on success — **including when the steps cap is hit** (the cap summary arrives as a normal `text` event). Exit 1 for usage/API/session errors (stderr). No preamble/ANSI on stdout.
- **notmuch 0.38.3 reader surface — verified 2026-10-20 by read-only probes against the live index** (reader config: `database.path=/workspace/docker/mbsync/notmuch`, `mail_root=/workspace/docker/mbsync/backup`, `synchronize_flags=false`): bare `notmuch count` = 13,111; `folder:"yuri.durodie@vub.be/INBOX"` = 10,001; `folder:"yuri.durodie@vub.be/Sent Items"` = 2,960 (quoted form works with spaces); `from:"Yuri Durodie"` = 2,987; `id:`, `thread:`, `date:YYYY*` prefix all work. `notmuch search --format=json` emits **thread objects** (array): `{thread, timestamp, date_relative, matched, total, authors, subject, query: [matched_subquery, unmatched_subquery], tags}` where each `query` element is a space-joined string of `id:<msgid>` clauses (message-ids never contain spaces → whitespace split is safe). **`--format=messages` does not exist in this build.** `notmuch show --format=json 'id:<msgid>'` emits a nested recursive JSON list; the primary message is the first element; each message object has `id, match, excluded, filename[], timestamp, tags, duplicate, body[], crypto, headers` — `text/plain` parts carry `content`; **`text/html` parts carry only `content-length` (no body)** and are nested under a multipart container's `content` list → raw-file MIME fallback via `filename` is required for HTML-only messages. **Search-row `timestamp` is an integer epoch** (verified: 1792395502), not an ISO string. **Unknown query properties are NOT rejected — they are silently reinterpreted as free-text terms** (notmuch's documented fallback; verified 2026-10-20 on the live index): `all:` behaves exactly like the free-text word `all` (5,678 matches — identical to `notmuch count 'all'`), and date-style terms (`after:1990-01-01`, `before:2100-01-01`, `last:30d`) match nothing (0) — all exit 0, no error. So these forms are forbidden not because they error but because they can silently return large irrelevant result sets; the builder's refusal contract (`SUPPORTED_PREFIXES`) is the only safe guard, and date ranges must use the verified `date:YYYY*` prefix form.
- **Canonical repo layout** (Task 1 creates the skeleton; each later task adds ONLY its listed files):

```
agentic_scripts/
├── .env.example                  T1
├── .gitignore                    T1
├── README.md                     T5
├── config/workflows.yaml         T1
├── pyproject.toml                T1
├── scripts/setup.sh              T5
├── systemd/agentic-scripts.service   T5
├── systemd/agentic-scripts.timer     T5
├── src/agentic_scripts/
│   ├── __init__.py               T1
│   ├── __main__.py               T2
│   ├── cli.py                    T2
│   ├── scheduler.py              T2
│   ├── config.py                 T1
│   ├── state.py                  T1
│   ├── logging_setup.py          T1
│   ├── agent.py                  T3
│   ├── git.py                    T3
│   ├── mail/__init__.py          T4
│   ├── mail/reader.py            T4
│   └── workflows/
│       ├── __init__.py           T1
│       ├── base.py               T1
│       └── noop.py               T1
├── tests/
│   ├── conftest.py               T1
│   ├── test_config.py            T1
│   ├── test_state.py             T1
│   ├── test_base_noop.py         T1
│   ├── test_gate.py              T2
│   ├── test_lock.py              T2
│   ├── test_scheduler.py         T2
│   ├── test_agent.py             T3
│   ├── test_git.py               T3
│   ├── test_mail_reader.py       T4
│   └── smoke/
│       ├── __init__.py           T5
│       └── test_smoke_base.py    T5
└── planning/                     (existing)
```

## Tasks

### Task 1: Project foundation (skeleton, config, state, logging, workflow protocol, noop)
Files & spec: `work_plan_task_1_foundation.md`. Creates the full skeleton, canonical config + fail-fast validation, atomic per-workflow state store, run-logging + last-run writer, `Workflow` protocol + `WorkContext`/`WorkflowResult`, and the `noop` demo workflow.
**Depends on:** nothing.

### Task 2: Scheduler core (gate, lock, run loop, CLI)
Files & spec: `work_plan_task_2_scheduler.md`. Hybrid gate (quiet window 22:00–08:00 crossing midnight AND load1 < 2.0 on 2 consecutive polls ≤ ~40 min apart, persisted in `state/scheduler.json`), skip-if-held `flock`, timer-agnostic run loop with `--force`/`--only`, per-run log + `last-run.txt`, exit codes.
**Depends on:** Task 1.

### Task 3: Agent runner + git helpers
Files & spec: `work_plan_task_3_agent_git.md`. `AgentRunner` wrapping `opencode run --format json` (verified event schema in Context; hard timeout; NDJSON capture; final-text extraction) and thin `Git` subprocess helpers (clone/fetch/branches/worktree/commit/push).
**Depends on:** Task 1. **Parallel with:** Task 2, Task 4 (disjoint files).

### Task 4: Notmuch mail reader
Files & spec: `work_plan_task_4_mail_reader.md`. `NotmuchReader` library over the verified 0.38.3 query subset (count/search/show/body_text with HTML raw-file fallback marker), generated reader config, pure query-builder helpers. Hermetic tests against a throwaway index.
**Depends on:** Task 1. **Parallel with:** Task 2, Task 3 (disjoint files).

### Task 5: Setup, ops, README, smoke test
Files & spec: `work_plan_task_5_ops_smoke.md`. Idempotent `scripts/setup.sh` (uv sync, env-var check, admin-repo check, registered-workflow agent check, systemd→cron detection + 30-min timer install), shipped systemd units, README (config reference, env vars, timer (re)install, how-to-add-a-workflow), hermetic smoke harness proving gate-closed no-op / forced open run / lock exclusivity / audit log / idempotent re-run.
**Depends on:** Tasks 1, 2, 3, 4.

## Parallel blocks

| Wave | Tasks | Rationale |
|---|---|---|
| 1 | 1 | everything imports its config/state/logging |
| 2 | 2 ∥ 3 ∥ 4 | disjoint files; all depend only on Task 1 |
| 3 | 5 | smoke + setup exercise the whole system |

## Out of Scope

- The OC-todo resolver workflow and the mail-keeper workflow (sibling plans `workflows-oc-todo`, `workflows-mail-keeper`), including their fixture repos, fixture `.eml`, `mail-search` CLI surface, live-index canary set, triage/vault/draft logic, and their smoke modules. The base smoke harness is structured so those plans add `tests/smoke/test_smoke_<workflow>.py` + fixtures later (see Note 1).
- Writing/modifying agent definitions — `oc-todo-resolver` and `mail-keeper` already exist in the global OpenCode config (`~/.config/opencode/agents/`, oc_config repo); the base only references agents by name.
- Editing `/workspace/Research/*`, `/workspace/scripts/email-sync/*`, the mbsync WIP, `ARP_roadmap`, or the maildir.
- Any live LLM inference in automated tests (agent tests use a fake `opencode` shim; a live run is a manual note in the result report).
- Docker (not on this host); systemd installation (container has no systemd — units are shipped, install path documented and tested only by inspection).

## Notes

1. **[Interpretation — smoke sequencing]** Base plan Task 3 acceptance mentions "fixture PRs created, fixture mail processed" — those outputs require the workflow plans, which build AFTER this plan. The base smoke test therefore proves the base's own end-to-end paths (gate-closed no-op, forced open run, lock, audit, idempotency) with the `noop` workflow, and the harness is extensible: each workflow plan adds its own smoke module + fixtures to `tests/smoke/`. The fixture-PR/fixture-mail assertions are tracked by their own plans' acceptance criteria.
2. **[Interpretation — mail reader boundary]** Base ships the `NotmuchReader` *library* (shared primitive, hermetic tests). The `mail-search` CLI (arg surface, exit codes 0/1/2, list/detail modes) and live-index canary verification are the mail-keeper plan's first build step.
3. **[Assumption]** Directory names for the gitignored areas: `state/`, `logs/`, `sandbox/` (plan text says "state area"/"log area" without naming them).
4. **[Assumption]** Naming: package `agentic_scripts`, console script `agentic-scripts`, config file `config/workflows.yaml`.
5. **[Assumption]** A `noop` demo workflow ships registered in the default config: it proves the registry mechanism end-to-end and gives the smoke test a runnable unit; removable by setting `enabled: false`.
6. **[Decision, verified 2026-10-20]** Setup's agent-existence check is data-driven: it verifies the agent file for every *registered, enabled* workflow entry (base-only state: none required). Both real agents already exist globally, so the check passes today and after the workflow plans register their workflows.
7. **[Risk]** No init system (PID 1 = `bash`): cron daemon dies with the container; setup re-run is the documented recovery (idempotent). systemd units shipped for real hosts.
8. **[Constraint]** Task 1 owns `pyproject.toml`; Tasks 2–5 must not modify it (parallel-safety). `WorkContext` lazily imports `git`/`runner` (properties) so Task 1 compiles before Tasks 3/4 land.
9. **[Risk]** Long agent runs overlap the next timer fire → skip-if-held lock (Task 2) + per-invocation timeout (Task 3) bound the damage.
10. **[Note]** Window/threshold/cadence defaults (22:00–08:00, load1 < 2.0, 2 polls ~30 min) are user-confirmed (2026-10-14) and config-tunable; the gate state is persisted in `state/scheduler.json` between polls.
11. **[Verified corrections, orchestrator live probes 2026-10-20, wave-2 review]** (a) Unknown notmuch query properties are silently reinterpreted as free text (`all:` = 5,678 = the word `all`; `after:`/`before:`/`last:` → 0; never an error) — supersedes the "broken in this build" phrasing inherited from the high-level plan; T4's reader.py docstring (which claimed "silent no-op, returns 0") is being corrected via fix-task 4b. (b) Search-row `timestamp` is an integer epoch — supersedes "ISO-ish" phrasing. (c) `--format=messages` absence re-confirmed.
12. **[Process incident, resolved]** Task 3's first commit (parallel wave) accidentally included Task 2's pre-staged files; corrected via soft-reset + recommit + `--force-with-lease`. Post-incident verification (orchestrator): linear history, all four wave commits in HEAD and on origin, working tree clean, per-commit file-purity confirmed, full suite 62 passed. Lesson applied: remaining work (fix 4b, then Task 5) is single-agent — no parallel commits.

## Dispatch protocol

- Sub-agent: `@lightweight-dev` for every task (implementation + tests + self-verification + `OC:` commit + push of the task's files only).
- Per-task dispatch inputs: (1) the task file path below, (2) the exact result filename, (3) the task number.
- Result files: `lightweight_dev_task_1_foundation.md`, `lightweight_dev_task_2_scheduler.md`, `lightweight_dev_task_3_agent_git.md`, `lightweight_dev_task_4_mail_reader.md`, `lightweight_dev_task_5_ops_smoke.md`.
- Orchestrator verifies each result's acceptance table before dispatching the next wave. Retry limit 2 per task, then structured escalation to user.
- Archive (implementation-plan skill) only after the final report and explicit user confirmation.
