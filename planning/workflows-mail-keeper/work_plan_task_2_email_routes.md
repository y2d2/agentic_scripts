# Task Plan: Real `email-routes.md`

**Purpose:** Replace the placeholder mail routing config with real, index-backed routing rules the `mail-keeper` agent consults at runtime (its skill says: "consulted at runtime **when non-placeholder**").

## Objective

Write a real `/workspace/Obsidian/config/email-routes.md`: routing rules + sender→vault mappings derived from actual senders in the notmuch index (read-only probes) and the `ARP_roadmap` vault's existing people/project structure, plus a folder table matching the real maildir and an audit-trail section documenting the runner-owned processed log. Success: no sample/placeholder domains remain; every listed sender/folder is verifiable against the index or maildir; the file's shape stays consumable by the `mail-keeper` skill's runtime consultation.

## Context

- **Target file:** `/workspace/Obsidian/config/email-routes.md` — currently 95 lines of placeholder (mtime 2026-09-10): sample senders `*@orbit-project.com`, `*@vub.be`, `HR@company.com`, `support@projecttools.com`, an empty "fill in" mapping table, a folder table with only `INBOX → todos/active.md → Inbox section`, and an audit-trail section documenting the v1 (now-superseded) `inbox/processed/YYYY-MM-DD/` layout. `/workspace/Obsidian` is **NOT a git repository** (verified 2026-10-21) → write the file, do NOT commit; state this in the result report.
- **Consumer:** the `mail-keeper` agent (global `skills/mail-keeper/SKILL.md`) — it applies importance heuristics by default and consults this file when non-placeholder; it does NOT parse it programmatically (no code depends on exact table syntax) — but keep the v1 table structure (Routing Rules Table / Sender-to-Project Mapping / Folder-Specific Rules / Audit Trail) so the file remains a drop-in upgrade.
- **Data sources (all read-only):**
  - Live notmuch index: `/workspace/docker/mbsync/notmuch` over mail root `/workspace/docker/mbsync/backup` (account `yuri.durodie@vub.be`). Probe with `NOTMUCH_CONFIG` pointing at a generated reader config (template: `[database]\npath=...\nmail_root=...\n[maildir]\nsynchronize_flags=false\n`) — e.g. a Python one-liner using the base reader or raw `notmuch search --format=json`. Suggested probe: INBOX messages from the last ~6 months (`folder:"yuri.durodie@vub.be/INBOX" and date:2026*`), aggregate `authors` from thread rows, top ~15 senders by count. (These are READ-ONLY queries — never `notmuch new`, never write the index/maildir. GNU `find` does not descend into this maildir; use Python `os.walk` for any filesystem check.)
  - Vault (read-only): `/workspace/Obsidian/ARP_roadmap` — `people/` (existing person folders), `projects/ORBIT/00_Project_management/people.md` (ORBIT roster), `direction.md`, `todos/active.md` sections (`## 📂 Projects`, `## 🔬 Research & Papers`, `## 💰 Funding & Grants`, `## 🏫 Onboarding & Learning`, `## 👤 People`, `## 📋 Projects in Preparation`, `## ⏳ Waiting On`).
- **Real maildir folders (verified on disk):** `INBOX`, `INBOX/Admin`, `INBOX/Admin/Data_storage`, `INBOX/FU-Admin`, `INBOX/FU-Admin/Nerdland`, `INBOX/FU-Admin/PhD_applications` (PII — excluded), `INBOX/FU-Admin/VICON_ICT`, `INBOX/ORBIT`, `INBOX/Spin-off`, `INBOX/Students`, `Sent Items`.
- **Processed-log contract (to document in the Audit Trail section):** path `/workspace/Obsidian/config/email-processing-log.jsonl`, **runner-owned** (written by the `agentic_scripts` mail-keeper workflow, never by the agent or v1), one compact JSON line per triaged message, 6 fields: `timestamp` (UTC ISO-8601 str), `email_file` (the RFC 5322 message-id — v1 stored a UID here; identifier semantics preserved), `subject` (str), `from` (list of addresses), `target_section` (triage class `noise`/`info`/`action`/`urgent`, or `mail-keeper` when the class could not be parsed), `processed_to` (usually `""`; drafts are gitignored local files, not vault targets). The v1 pipeline (`/workspace/scripts/email-sync`) is OFF (no `.env`) and stays so.
- **Conventions:** keep the file's YAML frontmatter (update `date_modified` to today, extend `keywords` with `mail-keeper`); plain prose + tables; no emojis; date format `YYYY-MM-DD`.

## Tasks

### Task 1: Extract real senders and vault structure (read-only)
- **Files:** none (investigation; record outputs in the result report)
- **Do:** (a) Run the notmuch sender probe above against the live index; record the top ~15 senders with counts (name + address where resolvable from `From:` headers via a few `notmuch show --format=json` spot-checks). (b) List `people/` folder names in the vault and read `projects/ORBIT/00_Project_management/people.md` (names/roles). (c) Record the vault's current branch (`git -C /workspace/Obsidian/ARP_roadmap branch --show-current`) and that the vault tree is dirty (pre-existing user work — read-only, do not touch).
- **Notes:** Everything strictly read-only. Keep the probe small (≤ ~10 notmuch invocations).

### Task 2: Write the real `email-routes.md`
- **Files:** `/workspace/Obsidian/config/email-routes.md` (modify — outside the repo, no commit)
- **Do:** Rebuild the file on the v1 structure:
  - Frontmatter: same `title`/`topic`, `date_modified: <today>`, `keywords` extended with `mail-keeper`; `sources_used` may stay `[]`.
  - `# Email Routing Rules` + `> How to use:` rewritten for the `mail-keeper` agent: heuristics first, this file as the authoritative routing reference for sender→target and folder handling; the agent records in its report when it deviates.
  - **Default Behavior:** unchanged semantics (unmatched → `todos/active.md`, matching-section line, format `- [ ] Subject (from sender — YYYY-MM-DD) *(from: X, "Subject", YYYY-MM-DD, msg-id)*` — i.e. the v1 format plus the provenance tag the agent always applies).
  - **Routing Rules Table:** real rules derived from Task 1 — e.g. ORBIT project senders/roster → `projects/ORBIT/00_Project_management/` (`01_Meetings.md`/`02_Reporting.md`/`03_Communications.md` by topic); tracked persons (`people/<Name>/` folders) → that person's note; funding/grant keywords (FWO, EUG, ERC, Steerco) → `todos/active.md` `## 💰 Funding & Grants`; urgent/action verbs → top of `## ⏳ Waiting On` or `## 📂 Projects` per topic; keep the `URGENT`/`ACTION REQUIRED` subject rule; default fallback row retained.
  - **Sender-to-Project Mapping:** real addresses/domains from the probe (e.g. ORBIT colleagues, `yuri.durodie@vub.be` = own account → excluded from triage, style sampling via `mail-search --own` only), one row per sender with the vault target; mark unverified entries as such.
  - **Folder-Specific Rules:** the real maildir folder table — `INBOX` (primary, triaged), label subfolders by their meaning (ORBIT → project IA; FU-Admin → academic/admin tasks, `## 🔬 Research & Papers`/`## 🏫 Onboarding & Learning` where fitting; Students/Spin-off/Admin per Task 1's sender mix), `INBOX/FU-Admin/PhD_applications/` → **excluded (PII) — never read, never drafted, never written from** (explicit dispatch override only, per agent hard rule), `Sent Items` → not triaged; own-mail corpus for reply style sampling.
  - **How to Add a New Rule / New Folder:** keep v1's guidance, adjusted (the file is read by the agent, not a script — "add a row; the next mail-keeper run picks it up").
  - **Audit Trail:** replace the v1 `inbox/processed/YYYY-MM-DD/` text with the runner-owned processed-log contract from Context (path, 6-field schema, runner-owned, v1 OFF).
- **Notes:** Keep it tight (~100–150 lines). Every sender row must trace to the Task 1 probe output (record the traceability in the result report). Do not invent senders.

## Acceptance

1. `/workspace/Obsidian/config/email-routes.md` exists, valid YAML frontmatter with `date_modified` = today; none of the placeholder identifiers remain (`orbit-project.com`, `HR@company.com`, `support@projecttools.com`, `projecttools`).
2. Top senders in the Sender-to-Project Mapping all appear in the Task 1 probe output recorded in the result report (traceable, no invented addresses).
3. The Folder-Specific Rules table lists every real maildir folder from Context (incl. the PII exclusion row and the Sent Items row).
4. The Audit Trail section documents the exact 6-field processed-log schema and path from Context.
5. No file inside `/workspace/Obsidian/ARP_roadmap`, the maildir, or `/workspace/docker/mbsync` was modified (`git -C /workspace/Obsidian/ARP_roadmap status --porcelain` identical to the pre-task state: ` M direction.md` + the 3 untracked entries).
6. Result report records: probe output (top senders + counts), branch check, and "not a git repo — no commit" explicitly.

## Out of Scope

- Any repo commit (the file is not in a git repo); changes to the vault, maildir, mbsync WIP, v1 pipeline, the agent/skill, or `/workspace/Research`; making the file machine-parsed (no code consumes it structurally).

## Notes

- **[Assumption]** "Top-sender candidates extractable from the index" (high-level plan) = authors aggregated over recent INBOX traffic; Sent Items authors (own mail) are excluded from the mapping except the self-account row.
- **[Risk]** The vault's `people/` folders use mixed casing (e.g. `henri`); preserve exact folder names verbatim in the mapping table.
- **[Note]** This task commits nothing to `agentic_scripts` — the orchestrator's per-task commit check for this task is "repo tree unchanged."
