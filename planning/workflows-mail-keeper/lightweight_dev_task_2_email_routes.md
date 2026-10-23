# lightweight-dev Output — Task: Real `email-routes.md`

**Task:** #2    **Session:** workflows-mail-keeper    **Date:** 2026-10-22

## Summary

Replaced the placeholder `/workspace/Obsidian/config/email-routes.md` (sample domains,
empty mapping table) with real routing rules derived from two read-only data sources:
(a) a notmuch sender probe against the live index (`/workspace/docker/mbsync/notmuch`
over mail root `/workspace/docker/mbsync/backup`, account `yuri.durodie@vub.be`) and
(b) the `ARP_roadmap` vault's existing people/project structure. The file keeps the v1
shape (Routing Rules Table / Sender-to-Project Mapping / Folder-Specific Rules / Audit
Trail) so it stays a drop-in for the `mail-keeper` agent's runtime consultation, with
every sender row traced to the probe output below and no invented addresses.

**Not a git repo — no commit.** `/workspace/Obsidian` is not a git repository (verified:
`git -C /workspace/Obsidian rev-parse --is-inside-work-tree` → `fatal: not a git
repository`). Per the task spec, this task commits NOTHING anywhere; no `git commit` was
run.

## Files
| File | Action | Why |
|---|---|---|
| `/workspace/Obsidian/config/email-routes.md` | modify | Real routing rules + sender→vault mapping + folder table (incl. PII exclusion & Sent Items) + runner-owned processed-log audit trail; `date_modified` = 2026-10-22, `keywords` extended with `mail-keeper`. Outside any git repo → no commit. |

## Build / Tests

No build (markdown config file). Verification actions:

- **Notmuch sender probe (read-only, base `NotmuchReader`, `synchronize_flags=false`,
  generated reader config in `/tmp/opencode/probe_work`)**: PASS — never ran `notmuch new`;
  total index count = **13,160** messages.
- **Probe — recent INBOX traffic (2026):** `INBOX_2026_TOTAL_THREADS = 2123`. The thread-row
  `authors` field is a single letter in notmuch 0.38.3 (not usable for aggregation), so real
  senders were resolved by `show`-ing the primary message of each sampled thread and parsing
  the `From:` header.

### Probe output — top INBOX-2026 senders (sample of first 60 newest threads; count = threads in sample)

| Count | From address | Display name |
|---|---|---|
| 5 | `bram.vanderborght@vub.be` | Bram VANDERBORGHT |
| 3 | `yuri.durodie@vub.be` | Yuri Durodié (own account) |
| 2 | `ai.experience.centre@vub.be` | PL9.-1 AI Experience Centre |
| 1 | `bas.boom@imec.nl` | Bas Boom (imec) |
| 1 | `robotics@listserv.vub.be` | Niels Gadeyne via robotics |
| 1 | `igor.petrov@imec.nl` | Igor Petrov (imec) |
| 1 | `nikos.kouvelas@imec.nl` | Nikos Kouvelas (imec) |
| 1 | `hpc-announce@listserv.vub.be` | The VUB-HPC Team |
| 1 | `vubstaffnews@universiteit.vub.be` | VUB staff news |
| 1 | `muhammad.farooq.rasheed@vub.be` | Muhammad Farooq Rasheed |
| 1 | `sc@world-comp.org` (Steering Committee) | — |
| 1 | `no-reply@ict.vub.be` | Hamed Firouzipouyaei in Teams |
| 1 | `ivisit@vub.be` | — |
| 1 | `eric.vanderhulst@imec.be` | Eric Van der Hulst (imec) |
| 1 | `aixc@vub.be` | AI Experience centre |
| 1 | `ieee-ras@deliver.ieee.org` | IEEE Robotics & Automation Society |
| 1 | `octavian.astefanei.ext@imec.nl` | Octavian Astefanei (imec) |
| 1 | `eli.depoorter@ugent.be` | Eli De Poorter (UGent-imec) |

### Probe output — per-folder primary senders (sample of first 12 threads each)

- **INBOX/ORBIT:** `bram.vanderborght@vub.be` (5), `renske.landeweert@imec.nl`,
  `ive.weygers@imec.be`, `django.lienart@willemen.be`, `yuri.durodie@vub.be`,
  `bram.vanderborght@imec.be`.
- **INBOX/Students:** `yuri.durodie@vub.be` (5), `bram.vanderborght@vub.be` (2),
  `yann.ketis.noubayo.wouassi@ulb.be` (NOUBAYO WOUASSI Yann Ketis).
- **INBOX/Spin-off:** `tuur.roels@vub.be` (2), `webcms@tu-dresden.de`,
  `maarten.de.ruyck@vub.be`.
- **INBOX/Admin:** `tom.turcksin@vub.be`.
- **INBOX/FU-Admin/VICON_ICT:** `vub@service-now.com` (10, VUB ICT Service Desk),
  `tom.turcksin@vub.be` (2).
- **Sent Items:** `yuri.durodie@vub.be` (7), `muhammad.farooq.rasheed@vub.be`,
  `bram.vanderborght@vub.be`, `eric.vanderhulst@imec.be`, `niels.gadeyne@vub.be`,
  `no-reply@imec-int.com` (Renske Landeweert).

### Probe output — per-folder message counts (read-only `notmuch count`)

| Count | Folder |
|---|---|
| 10,038 | INBOX |
| 5 | INBOX/Admin |
| 8 | INBOX/Admin/Data_storage |
| 1 | INBOX/FU-Admin |
| 3 | INBOX/FU-Admin/Nerdland |
| 31 | INBOX/FU-Admin/PhD_applications (PII — excluded) |
| 60 | INBOX/FU-Admin/VICON_ICT |
| 22 | INBOX/ORBIT |
| 5 | INBOX/Spin-off |
| 9 | INBOX/Students |
| 2,972 | Sent Items |

- **Vault structure (read-only):** `people/` = 28 person folders (verbatim, mixed casing —
  e.g. `Bram Vanderborght`, `Hamed Firouzipouyaei`, `henri`); ORBIT roster read from
  `projects/ORBIT/00_Project_management/people.md`; `todos/active.md` section headers
  confirmed verbatim (`## 📂 Projects`, `## 🔬 Research & Papers`, `## 💰 Funding & Grants`,
  `## 🏫 Onboarding & Learning`, `## 👤 People`, `## 📋 Projects in Preparation`,
  `## ⏳ Waiting On`).
- **Vault branch check:** `git -C /workspace/Obsidian/ARP_roadmap branch --show-current` →
  `feature/dual-mode-roadmap`. Tree is dirty (pre-existing user work — read-only, untouched):
  ` M direction.md`, `?? planning/`, `?? projects/ORBIT/DMP Questionnaire ORBIT.md`,
  `?? projects/ORBIT/DMP Questionnaire ORBIT.xlsx`.
- **YAML frontmatter validation:** PASS — parses cleanly; keys
  `title/topic/date_created/date_modified/sources_used/keywords`; `date_modified: 2026-10-22`;
  `keywords` includes `mail-keeper`.
- **Placeholder identifiers absent:** PASS — none of `orbit-project.com`, `HR@company.com`,
  `support@projecttools.com`, `projecttools` remain.
- **No-modification verification (AC5):** PASS — re-snapshot + diff vs pre-task baseline:
  - `ARP_roadmap`: `find . -type f -not -path './.git/*' -printf '%T@ %p\n' | sort` identical
    before/after → **ARP_ROADMAP_UNCHANGED**. `git status --porcelain` identical to pre-task
    state (` M direction.md` + 3 untracked entries).
  - maildir: Python `os.walk` over `/workspace/docker/mbsync/backup` (13,226 files) —
    mtime-ns snapshot identical before/after → **MAILDIR_UNCHANGED**.
  - `/workspace/docker/mbsync`: no file written by this task; `git status --porcelain` shows
    only pre-existing WIP (`M .dockerignore/.gitignore/README.md/docker-compose.yml/sync.sh`,
    `?? Dockerfile.notmuch/notmuch-config/notmuch/`) — all predating this task.
- **Processed-log path:** confirmed `/workspace/Obsidian/config/email-processing-log.jsonl`
  does not exist yet (runner will create it on first run) — Audit Trail text is accurate.

## Acceptance Verification
| # | Criterion (verbatim) | Result | Notes |
|---|---|---|---|
| 1. | `/workspace/Obsidian/config/email-routes.md` exists, valid YAML frontmatter with `date_modified` = today; none of the placeholder identifiers remain (`orbit-project.com`, `HR@company.com`, `support@projecttools.com`, `projecttools`). | PASS | File exists (132 lines); YAML parses; `date_modified: 2026-10-22`; all four placeholder identifiers confirmed absent via grep. |
| 2. | Top senders in the Sender-to-Project Mapping all appear in the Task 1 probe output recorded in the result report (traceable, no invented addresses). | PASS | Every sender row traces to the probe tables above (recent INBOX + per-folder samples); single-sample entries are explicitly marked "single-sample; verify on recurrence"; own-account row noted as excluded from triage. |
| 3. | The Folder-Specific Rules table lists every real maildir folder from Context (incl. the PII exclusion row and the Sent Items row). | PASS | All 12 folders listed: INBOX, Admin, Admin/Data_storage, FU-Admin, FU-Admin/Nerdland, FU-Admin/VICON_ICT, ORBIT, Spin-off, Students, **FU-Admin/PhD_applications (PII — EXCLUDED)**, Sent Items. |
| 4. | The Audit Trail section documents the exact 6-field processed-log schema and path from Context. | PASS | Documents path `/workspace/Obsidian/config/email-processing-log.jsonl`, runner-owned, one JSON line per message, all 6 fields (`timestamp`/`email_file`=message-id/`subject`/`from` list/`target_section` triage class or `mail-keeper`/`processed_to` usually `""`), and v1 OFF. |
| 5. | No file inside `/workspace/Obsidian/ARP_roadmap`, the maildir, or `/workspace/docker/mbsync` was modified (`git -C /workspace/Obsidian/ARP_roadmap status --porcelain` identical to the pre-task state: ` M direction.md` + the 3 untracked entries). | PASS | Vault mtime-ns snapshot + `git status --porcelain` identical to pre-task baseline; maildir `os.walk` snapshot identical; mbsync shows only pre-existing WIP (nothing written by this task). |
| 6. | Result report records: probe output (top senders + counts), branch check, and "not a git repo — no commit" explicitly. | PASS | Probe output (top senders + per-folder + folder counts) in Build/Tests; branch check `feature/dual-mode-roadmap` recorded; "Not a git repo — no commit" stated in Summary. |

## Blockers
None.

## Next Steps
- **Traceability note for the orchestrator:** the recent-INBOX sender sample (first 60 newest
  threads) is dominated by ORBIT/imec senders because ORBIT is the most active project; a few
  mapping rows are single-sample and marked as such — they should be re-verified on recurrence.
  The `people/` folders use mixed casing (e.g. `henri`) and were preserved verbatim in the
  mapping per the task's risk note.
- Task 2 commits nothing; the orchestrator's per-task commit check for this task is "repo tree
  unchanged" — confirmed (`agentic_scripts` shows only Task 1's files, which belong to the
  parallel task, not this one).
