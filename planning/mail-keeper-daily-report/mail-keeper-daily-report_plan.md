# Mail-Keeper Daily Mail Report Plan

**Purpose:** Add a per-day mail triage report — mails, artifacts updated, drafts — to the ARP_roadmap vault via the mail-keeper agent.

## Objective

Each mail-keeper run must maintain a per-day report file in the ARP_roadmap vault listing every message processed that day, its triage class, the vault artifacts that message updated (file + section), and the draft file created for messages deemed to need a reply. End state: a `mail/daily/YYYY-MM-DD.md` file exists in the vault after the first run, grows by one `## Run` block per run, and a re-run of the same manifest adds nothing. Success condition: for any given day, the daily file answers "what mail came in, what did the agent do with it, and where did it land (notes / todos / draft)" without consulting git history or the processed log. No changes to the `agentic_scripts` runner are part of this work.

## Context

- **Pipeline split (load-bearing).** The runner (`agentic_scripts`, `src/agentic_scripts/workflows/mail_keeper.py`) owns detection, the ≤10-message manifest, two-boundary cursors (`state/mail-keeper.json`), the processed log (`/workspace/Obsidian/config/email-processing-log.jsonl`), and the backup-tree byte-identity guardrail. It **never writes vault files and never commits**. The `mail-keeper` agent (definition in `~/.config/opencode/agents/mail-keeper.md`, behavior in `skill: mail-keeper`) runs with the vault as cwd, triages, writes, drafts, and is itself the vault's git owner (`OC:` commit + push to the current branch). This split is what makes re-runs idempotent.
- **Vault `.gitignore` (constrains this feature).** The vault's `.gitignore` contains a bare `mail` line, so the whole `mail/` tree is git-ignored: only 3 force-added old drafts are tracked; drafts from 2026-10-24 onward are local-only. **User decision 2026-10-27: leave the gitignore as-is.** Consequence: the daily report is a local-only artifact — visible in Obsidian, not in git history. Accepted.
- **Dedup mechanism (reused).** Before every write the agent greps the message-id across vault text files and `mail/drafts/` (excluding `mail/backup`); a hit means "skipped (already processed)". Report entries carry msg-ids, so the existing rule extends to the report with no new mechanism.
- **`email-routes.md` location/status.** `/workspace/Obsidian/config/email-routes.md` — a sibling `config/` folder next to the vault, not inside it. Read by the agent at runtime (no script parses it). It is **no longer a placeholder**: 37 routing-rule rows, `date_modified: 2026-10-22`. The skill text still calls it a placeholder (stale).
- **Runner-side raw data already exists.** The runner logs the agent's full final report (Triage table + Files) to `logs/run-*.log` in `agentic_scripts`. The daily report is the human-readable, in-vault layer on top of that; the durable audit fallback (durable across a vault re-clone) remains the `OC:` commit messages + processed log.

## Functional Tasks

### Task 1: Define the daily report artifact and its format (skill change)
- **Goal:** The skill defines a per-day report as a first-class write target: one file per processing day in the vault's mail area, with a stable format — a day header; one `## Run` block per run (run time, batch size, class counts); one entry per message (subject, sender, mail date, msg-id, triage class, artifacts updated as file + section, draft file or an explicit "—").
- **Why this approach:**
  - **[Decision: Report location]** Value = `mail/daily/YYYY-MM-DD.md` (a new subfolder of the vault's existing `mail/` area) because user preference (2026-10-27) and it is mail-scoped, co-located with the drafts it references, and leaves the personal journal untouched. The skill already special-cases `mail/` for drafts, so extending it is consistent.
  - **[Decision: Grouping key]** Value = processing day (run day), not mail date, because backfill batches contain old mail and the report's job is the audit question "what did the agent do on day X"; each entry still displays the mail's own date so recency is never lost. My analysis, consistent with the workflow's local-date convention for manifests.
  - **[Decision: Coverage]** Value = all triage classes, including `noise`, because the file must be a complete triage record for the day, not only a write log; noise entries carry class + "no artifacts".
  - **[Decision: Idempotency mechanism]** Value = reuse the existing pre-write msg-id grep, because report entries carry the msg-id verbatim, so a re-delivered batch is detected before any report line is written and a re-run of an identical manifest adds zero lines. No new dedup machinery.
- **Acceptance criteria:** After a run that triages N messages, the day's file contains exactly one entry per message with class, artifact list (file + section), and draft reference where a draft was written. A second run of the identical manifest adds zero report lines and zero other writes. A backfill run of old mail appends under the run day, with each entry showing the mail's own (older) date.

### Task 2: Wire the report into the agent's run steps and commit policy (skill change)
- **Goal:** The run procedure gains a report step — after vault writes and drafts, before commit, the agent appends the per-run block to the day's file (creating it if absent) — and the commit policy explicitly excludes `mail/daily/` (and drafts) from the list of paths it commits, with an instruction to never force-add git-ignored paths.
- **Why this approach:**
  - **[Decision: Local-only artifacts]** Value = keep the vault's bare `mail` gitignore line (user decision 2026-10-27), so drafts and the daily report remain local-only. Chosen over the `mail/backup`-scoped gitignore alternative because the user opted to leave it as-is; the plan documents the consequence (report survives neither re-clone nor wipe; durable fallback is `OC:` commit messages + processed log).
  - **[Decision: No runner changes]** Value = `agentic_scripts` untouched, because the runner contract (never writes vault files, never commits, never advances state on failure) is a hard design rule, and the agent already possesses every field the report needs (its own triage table, the files it touched, the drafts it wrote) — no new data flow between runner and agent is required.
- **Acceptance criteria:** The agent's result report lists the daily file under its Files section. A run's `OC:` commit contains no `mail/daily/**` or draft paths, and run logs show no `git add -f` attempts. The result report's "no-op" path (all dedup-skipped/noise with zero writes) still appends the run block, so the day's file records runs that changed nothing.

### Task 3: Correct stale descriptions in skill and agent definition (housekeeping)
- **Goal:** Remove the skill's stale claim that `email-routes.md` is "currently a placeholder" (it is a 37-row table as of 2026-10-22) and update the agent definition's description/role line to name the daily report as an artifact.
- **Why this approach:**
  - **[Decision: Documentation accuracy]** Value = fix both, because the agent reads the skill at runtime and dispatchers read the agent description; a stale "placeholder" line would make every report claim the routes file is unused, and an outdated description would omit the new artifact from the dispatch contract.
- **Acceptance criteria:** Neither the skill nor the agent definition states `email-routes.md` is a placeholder; both reference it as the runtime routing table. The agent definition's description lists the daily report alongside notes, todos, and drafts.

## Alternatives Considered

1. **Runner-generated report** — the runner holds the manifest and the agent's final text and could append a vault report itself. Rejected: violates the hard design split (runner never writes vault files, never commits; the agent is the vault's git owner) and would force either a second commit path or the agent committing a file it did not write.
2. **`journals/YYYY-MM-DD.md` daily notes** — the vault's existing daily-note convention (one empty `2026-09-07.md`). Rejected by user preference (2026-10-27); also mixes machine-generated operational logs into the personal journal.
3. **Gitignore fix (`mail` → `mail/backup`)** — would make drafts and the report actually commit. Rejected by user decision (2026-10-27): leave as-is; the local-only consequence is documented in Task 2 and Notes.
4. **Per-batch report files** — one file per run instead of per day. Rejected: the requested unit is a day; per-batch files would fragment one day's record across up to ~48 files.

## Notes

- **[Assumption]** Multiple runs per day are normal (~30-minute cadence); the per-run append model handles one run and many alike.
- **[Assumption]** The processing day follows the machine-local timezone, consistent with the workflow's local-date manifest convention.
- **[Assumption]** The report is written by the agent in the same invocation that writes the notes/drafts (single agent pass, no second agent call).
- **[Risk]** Local-only: the report is lost on vault re-clone or machine wipe. Mitigation: durable audit remains the `OC:` commit messages (N triaged / M edits / K drafts per run) plus the processed log; the report is the human-readable layer.
- **[Risk]** Step budget: the extra report write costs a small fraction of one agent step per run against the agent's 80-step cap; the runner's step-exhaustion sentinel (treats cap-boilerplate as failure, re-presents the batch) remains the safety net.
- **[Note]** The `mail/backup` symlink (vault → 4.5 GB mbsync tree) stays git-ignored and is excluded from the agent's dedup grep scope exactly as today; no change.
- **[Note]** If the gitignore decision is ever reversed (Task 2 decision), the only follow-on change is one line in the commit policy — the report format and run steps are unaffected.
