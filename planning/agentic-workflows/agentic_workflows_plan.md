# agentic_scripts — Load-Aware Agentic Workflows Plan

**Purpose:** Timer-gated, load-aware automation: OC-todo resolver and email-admin workflows driven by headless OpenCode.

## Objective

Build `agentic_scripts` into a small Python project of autonomous workflows that run on this 24/7 server only when it is idle. Two workflows ship now: (1) an **OC-todo resolver** that scans a configurable set of GitHub repos across all branches for `OC-todo:` comments and opens one pull request per resolved todo via a headless OpenCode agent; (2) an **email-admin** workflow that reads newly downloaded `.eml` files from a local mail folder and keeps the `ARP_roadmap` admin vault up to date — people/project notes, draft replies as files, and tracked todos — with a direct push to that vault. Success = a fresh setup script brings the system up; with the gate open, each workflow produces its observable outputs idempotently; with the gate closed, runs exit as no-ops without touching any repo. Future workflows plug in as new registered modules without scheduler changes.

## Context

- **Greenfield repo.** `agentic_scripts` contains only a README (verified 2026-10-14). This plan defines the whole system.
- **Environment (verified 2026-10-14):** Ubuntu 24.04 container where PID 1 is `bash` — **no systemd init, cron package not installed**; Python 3.12.3, `uv` 0.12.5, `psutil` 7.2.2 present; `gh` CLI absent. `/proc/loadavg` inside the container reflects the host kernel, so load-based gating works from inside.
- **Existing conventions (local evidence):** the `OC-todo:` comment marker is used across the user's repos (e.g. `#OC-todo` lines documented in /workspace/Python/ARP_IMU/planning/archived/attitude-estimator-refactor/attitude_estimator_refactor_plan.md; `% oc-todo:` in /workspace/Latex/Relative-localisation-tutorial-slides/slides/introduction/06_global_localisation.tex, which also references an `oc-original` comment that must survive). Commits follow the `OC:` prefix (git-workflow skill).
- **Admin repo (verified 2026-10-14):** `/workspace/Obsidian/ARP_roadmap` = `git@github.com:y2d2/ARP_roadmap.git`, an Obsidian vault with `todos/{inbox,active,done}.md` (markdown checkboxes, wikilinks), `people/<Name>/` notes, `projects/`, `direction.md`. Its `mail/` folder is **gitignored** and is a local-only mirror of the M365 mailbox (per-account → mailbox folders → `.eml` files, e.g. `INBOX`, `Sent Items`; currently an empty skeleton). **The mailbox is not part of the repo** (user, 2026-10-14) — it is read-only input to the email workflow.
- **Mail pipeline is in flux:** the user is still researching tooling that makes mail easier to read (mbsync-style sync; cached research: /workspace/Research/home/email-m365-imap-oauth2-findings.md, /workspace/Research/home/mbsync-docker-microsoft-oauth-thunderbird.md). The mail reader must therefore be an isolated, swappable component, and the folder may be empty.
- **Agent infrastructure:** local OpenCode + llama.cpp router with Qwen3.8-27B resident on the 24/7 rig (research: /workspace/Research/ai-agent-workflow/ — `LLM_configurations` topic). OpenCode agents have **no native token budget**; the sanctioned stop-and-report knob is the agent `steps` cap (research: /workspace/Research/ai-agent-workflow/agent-token-budget-steps.md). Headless invocation `opencode run` supports `--agent`, `--model`, `--dir`, `--auto`, `--format json`, `--title` (verified 2026-10-14 via `opencode run --help` on this machine).
- **GitHub limits (why local clones):** the GitHub code-search REST API "only [considers] the default branch" and only files < 384 KB, at 10 req/min authenticated → [GitHub REST search docs](https://docs.github.com/en/rest/search/search).
- **Python/ops conventions:** `uv` + Ruff + pytest under `pyproject.toml` with `src/` layout is the adopted 2025/2026 stack; secrets in `.env` with 0600; timers or cron with self-checking entry points (research: /workspace/Research/ai-agent-workflow/repo-file-conventions-best-practices.md; /workspace/Research/home/email-m365-imap-oauth2-findings.md).

## Functional Tasks

### Task 1: Load-Aware Scheduler Core (shared foundation)
- **Goal:** A single entry point, invoked by a timer, that decides whether the server is idle enough and, if so, runs the registered workflows one at a time. When idle is not confirmed, the run is a fast, logged no-op. Every run is auditable afterwards.
- **Why this approach:**
  - **[Decision: gate = hybrid window + load]** Value = quiet time window (default 22:00–08:00, crosses midnight) AND 1-min load average below a threshold (default 2.0) sustained across 2 consecutive polls (~30 min apart, stored between polls in the state area) because user chose hybrid gating (2026-10-14) and the rig serves interactive LLM inference during the day — a single low-load sample can be a transient dip (own analysis; 24/7 rig context in /workspace/Research/ai-agent-workflow/).
  - **[Decision: timer + self-check, not a daemon]** Value = a timer (default every 30 min) invokes a stateless entry point that performs the gate check itself, because user chose timer + self-check over a resident daemon (2026-10-14). The entry point is deliberately timer-agnostic so a daemon or manual `--force` run reuses the same gate logic.
  - **[Decision: trigger mechanism]** Value = cron entry on this machine (cron package installed by setup; verified not present 2026-10-14) plus a systemd timer/service unit shipped for real systemd hosts, because this container has no init system (PID 1 = `bash`, verified) — cron is the smallest reliable recurring trigger available here (own analysis of the verified environment).
  - **[Decision: load source]** Value = `/proc/loadavg` (via psutil) because inside the container it still reports host-kernel load, which is what "server load" means (own analysis; psutil verified present).
  - **[Decision: exclusivity]** Value = an exclusive file lock with skip-if-held semantics (no queueing): if a timer fires while a run is active, it logs and exits, because agent runs can outlast the 30-min interval and overlapping runs must never double-process (own analysis; idempotency is also enforced per-workflow in Tasks 3–4).
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
  - **[Decision: agent definitions]** Value = purpose-built agents (`oc-todo-resolver`, `email-admin`) defined in this repo and shipped with it, with `steps` caps, because headless runs must be reproducible from the repo alone and bounded in cost (research: /workspace/Research/ai-agent-workflow/agent-token-budget-steps.md).
- **Acceptance criteria:**
  - Missing or invalid configuration aborts start-up with a message naming the offending field.
  - Killing a run mid-flight and re-invoking never duplicates side effects (state is consulted before any action).
  - Both workflows import the same gate, lock, state, git, and agent-runner primitives; no workflow contains its own timer or lock logic.

### Task 3: OC-Todo Resolver Workflow
- **Goal:** For every configured GitHub repo, find every `OC-todo:` comment on every branch; for each one not already handled, have the agent produce a fix in a sandboxed worktree; commit, push a branch, and open one PR per todo that a human can review and merge.
- **Why this approach:**
  - **[Decision: scan = local clone + per-branch grep]** Value = full local clone (all remote branches) and `git grep` per branch, because the GitHub code-search API only covers the default branch, caps files at 384 KB, and is rate-limited to 10 req/min → [GitHub REST search docs](https://docs.github.com/en/rest/search/search); a local clone is deterministic, offline, and branch-complete (own analysis).
  - **[Decision: pattern]** Value = the strict, case-sensitive canonical marker `OC-todo:`, because the user chose the canonical form over a case-insensitive broad pattern (2026-10-14); matching is limited to text files with standard binary/build exclusions (own analysis of the marker's usage in local repos).
  - **[Decision: sandbox]** Value = one git worktree per todo, branched from the branch containing the todo, so concurrent todos and repos never share a checkout and no work happens on a shared clone's branches (own analysis; worktrees keep the full-clone history available to the agent).
  - **[Decision: agent scope]** Value = deterministic Python does clone/fetch, scanning, worktree setup, commit, push, and PR creation; the OpenCode agent only edits code inside the worktree (implement the todo, delete the `OC-todo:` comment — unless the comment or an `oc-original`-style note instructs keeping it — and run the project's test command if one is configured), because git/PR mechanics must be exact and auditable while code understanding is the agent's job (own analysis; `oc-original` convention observed in local repos, e.g. /workspace/Latex/Relative-localisation-tutorial-slides/slides/introduction/06_global_localisation.tex).
  - **[Decision: output = one PR per todo]** Value = push to a dedicated branch and open a PR against the branch that contained the todo, with the PR body quoting the exact comment, file, line, and the agent's summary, because the user chose review-before-merge over auto-push (2026-10-14); PRs are created via the GitHub REST API with the configured PAT because `gh` is not installed (verified 2026-10-14).
  - **[Decision: idempotency]** Value = a todo is skipped when its state says a PR was already opened, or an existing PR is found for the todo's dedicated branch; merged-and-comment-gone todos flip to resolved on the next scan, because the timer will re-scan forever (own analysis).
  - **[Decision: caps and failure]** Value = per-run caps (max todos per repo, agent `steps` cap, hard timeout) and retry-on-next-run semantics: a failed todo is recorded with its error and re-attempted on the next gate-open run, never leaving a partial push, because quiet windows are bounded and a hung agent must not block the schedule (research: /workspace/Research/ai-agent-workflow/agent-token-budget-steps.md — `steps` as the stop-and-report mechanism).
- **Acceptance criteria:**
  - Given a fixture repo with two `OC-todo:` comments on two different branches, one gate-open run produces exactly two PRs, each targeting the branch that contained its todo.
  - Each PR body quotes the exact `OC-todo:` comment text, names the file and line, and summarizes the change; the diff removes the comment (unless a keep-instruction applies).
  - Re-running with no repo changes opens zero new PRs; after merging a PR, the next run marks the todo resolved and does not reopen it.
  - An agent run that times out or exhausts `steps` leaves the todo in a failed/retry state, logs the reason, and the next run re-attempts it.
  - No workflow ever pushes to a protected or pre-existing branch — only freshly created per-todo branches are pushed.

### Task 4: Email-Admin Workflow
- **Goal:** Read newly downloaded mail from the local mail folder and keep the admin vault current: per-person and project notes updated with what the mail says, a draft reply written as a file per email, and any action items added to the vault's todo files — then commit and push the vault.
- **Why this approach:**
  - **[Decision: mail source = local folder reader]** Value = recursive scan of `.eml` files under a configured folder (default the `ARP_roadmap/mail` mirror) with the Python stdlib `email` parser, because the mailbox is mirrored locally and **not part of the repo** (user, 2026-10-14), and stdlib parsing handles the M365 multipart/base64 envelopes observed in the local `.eml` files (verified locally 2026-10-14); the reader is an isolated component because the user is still researching mail tooling that may change how files arrive (user, 2026-10-14; research: /workspace/Research/home/mbsync-docker-microsoft-oauth-thunderbird.md).
  - **[Decision: folders processed]** Value = configurable include/exclude list of mailbox folders, defaulting to the `INBOX` tree (including label subfolders) and excluding `Sent Items`, because only received mail creates work, and the mirror layout already separates them (observed locally: `INBOX`, `Sent Items`, 2026-10-14; own analysis).
  - **[Decision: newness]** Value = Message-ID deduplication in the state store; malformed or undecodable files are logged and skipped (recorded for inspection) without aborting the batch, because a single bad file must never block the rest of the mail (own analysis).
  - **[Decision: batched agent]** Value = one `email-admin` agent invocation per batch of new mail (manifest of senders, subjects, dates, bodies + vault layout), not one per email, because per-email agent launches waste context setup and the agent needs the whole batch to dedupe overlapping follow-ups (own analysis; budgeting: /workspace/Research/ai-agent-workflow/agent-token-budget-steps.md).
  - **[Decision: vault updates]** Value = the agent writes only Markdown into the existing vault structure — new action items into `todos/` (respecting the existing checkbox/wikilink style), per-person updates into `people/<Name>/` (creating a folder note for unknown people), status facts into project/direction notes — because the vault already defines the information architecture the user maintains by hand (observed locally 2026-10-14; own analysis).
  - **[Decision: drafts as repo files]** Value = one draft file per email in a new `drafts/` area of the vault: full headers (From/To/CC/Date/Subject), the original body, and a "Suggested reply" section, because drafts must live in the repo (user, 2026-10-14) and the workflow never sends mail — no SMTP is in scope (own analysis).
  - **[Decision: commit policy]** Value = direct commit (`OC:` prefix) and push to the vault's current branch, because `ARP_roadmap` is a single-user personal vault where a PR gate adds friction without review value (user decision, 2026-10-14); the mail folder itself is only ever read, never written, moved, or deleted (own analysis of the gitignored-input constraint).
- **Acceptance criteria:**
  - Placing one new `.eml` in the mail folder and running with `--force` produces, in the vault: a draft file with headers + original body + suggested reply, at least one new todo line (or a logged explicit decision that none is needed), and any relevant person/project note updates; the vault is committed with an `OC:` prefix and pushed.
  - Re-running with the same mail produces zero changes and zero commits.
  - An empty mail folder yields a clean no-op with a logged summary.
  - A corrupt `.eml` is logged and skipped while remaining files in the same batch are processed.
  - The mail folder's contents and file names are byte-identical before and after any run.

### Task 5: Setup, Ops & Smoke Test
- **Goal:** One setup script brings a fresh environment up; a documented smoke test proves both end-to-end paths without waiting for the gate.
- **Why this approach:**
  - **[Decision: setup idempotency]** Value = the setup script installs the cron package (absent, verified), registers the 30-minute crontab entry (idempotent), syncs the `uv` environment, checks required env vars, and verifies the admin repo clone — safe to re-run after container restarts, because this container has no init system to restart services for us (verified 2026-10-14; own analysis).
  - **[Decision: smoke test]** Value = `--force` runs against a local fixture repo (with planted `OC-todo:` comments on multiple branches) and a fixture `.eml`, asserting the Task 3/4 acceptance outputs, because gate-dependent behavior must be verifiable on demand (own analysis).
  - **[Decision: documentation]** Value = a README front-loading what/why, the config reference, the env-var list, and how to (re)install the timer, because future workflows and future-you will onboard via the README (research: /workspace/Research/ai-agent-workflow/repo-file-conventions-best-practices.md — README structure guidance).
- **Acceptance criteria:**
  - On a clean environment, one setup run + config + env vars → the next gate-open run (or `--force`) executes both workflows correctly.
  - The smoke test passes end-to-end (fixture PRs created, fixture mail processed) and can be re-run without side effects on real repos (fixture-only).
  - Re-running setup on an already-configured machine changes nothing and reports that state.

## Alternatives Considered

1. **GitHub code-search API instead of local clones** — Rejected: default-branch-only, 384 KB file cap, 10 req/min → [GitHub REST search docs](https://docs.github.com/en/rest/search/search).
2. **Resident daemon polling load** — Rejected by user (chose timer + self-check, 2026-10-14); the timer-agnostic entry point keeps the option open.
3. **Direct IMAP/OAuth2 mail reading** — Deferred: the local mirror is the source of truth for now and the user is still researching mail tooling; the isolated reader makes a future IMAP-backed source a drop-in replacement (research: /workspace/Research/home/email-m365-imap-oauth2-findings.md).
4. **Auto-push / auto-merge for OC-todo fixes** — Rejected by user (chose one PR per todo for human review, 2026-10-14).
5. **PRs for admin-vault changes** — Rejected: single-user personal vault; direct push keeps the review surface where it matters (code repos) (user decision, 2026-10-14).
6. **Raw LLM API calls instead of OpenCode CLI** — Rejected: loses the reusable agent/skill/config infrastructure and the `steps` stop-and-report budgeting that headless runs rely on (research: /workspace/Research/ai-agent-workflow/agent-token-budget-steps.md).
7. **CPU-idle-based gating** — Superseded by the user's hybrid window+load choice (2026-10-14).

## Notes

- **[Assumption]** Agent model defaults to the local Qwen3.8-27B via the llama.cpp router (24/7 rig, resident), overridable per workflow in config — consistent with the local-rig cost research → /workspace/Research/ai-agent-workflow/ (local-vs-subscription TCO, `LLM_configurations` topic).
- **[Assumption]** The mail folder will be populated by the user's separately researched sync pipeline; the reader must tolerate an empty folder indefinitely (verified empty on 2026-10-14).
- **[Assumption]** The initial OC-todo repo list is empty; acceptance testing uses a local fixture repo (user decision, 2026-10-14).
- **[Decision-confirmed]** `OC-todo:` matching is strict and case-sensitive per user choice (2026-10-14) — lowercase `oc-todo` or `#OC-todo` (no colon) instances observed in older notes will **not** match; treat that as intentional pruning of stale markers.
- **[Risk]** No init system in this container (PID 1 = `bash`, cron not installed — verified 2026-10-14): the cron daemon must be started with the container; a container restart requires re-running the (idempotent) setup. Mitigation: systemd unit shipped for real hosts; setup re-run is a documented one-liner.
- **[Risk]** Long agent runs can overlap the next timer fire. Mitigation: skip-if-held lock; per-run caps and timeouts bound run length.
- **[Risk]** Agent quality: a bad "fix" PR is caught in review (that is the PR-per-todo design); vault commits are inspectable via `git log` and reversible via inverse commits (git-workflow skill — no destructive resets).
- **[Risk]** Email privacy: drafts and distilled facts are pushed to the personal vault's remote; the user owns the remote, but should be aware that todo/distillation content becomes visible there (own analysis).
- **[Note]** Window/threshold/poll-cadence defaults (22:00–08:00, load1 < 2.0, 2 consecutive polls at ~30 min) are user-confirmed 2026-10-14 and all remain config-tunable.
