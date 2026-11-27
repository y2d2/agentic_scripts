# https://github.com/y2d2/ARP_1A_anchored_implementations.git
## feat/setup-sh-submodules
### planning/setup-sh-submodules/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 11 | planning/setup-sh-submodules/work_plan.md | Task Plan: setup.sh, submodules, pyproject, README | open | ☐ |

| details |
|---------|
| **Goal:** Give the ARP_1A_anchored_implementations repo a modern, reproducible environment setup (venv + 3 submodules) and a README consistent with the merged CAO implementation.<br>**Tasks:**<br>1 Rename package dir to lowercase PEP 8 + fix 7 imports<br>2 Add 3 submodules + recursive init<br>3 Edit pyproject.toml (1 line) + create .python-version + setup.sh<br>3b Fix setup.sh — `PYBIND11_FINDPYTHON=ON` + manifpy idempotency guard<br>4 Run ./setup.sh end-to-end + pytest (depends on #1, #2, #3) — ATTEMPT 1 BLOCKED<br>4b Re-run ./setup.sh (fixed) + pytest (depends on #3b, #6)<br>5 Update README (depends on #7)<br>6 Replace deleted SE23 import with new-API equivalent (user-approved)<br>7 Fix SGal3 vs matrix mismatches (3 source sites + 4 fixture sites + 1 import) — pytest gate |

## feat/single-anchor-ukf-plan
### planning/setup-sh-submodules/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 11 | planning/setup-sh-submodules/work_plan.md | Task Plan: setup.sh, submodules, pyproject, README | open | ☐ |

| details |
|---------|
| **Goal:** Give the ARP_1A_anchored_implementations repo a modern, reproducible environment setup (venv + 3 submodules) and a README consistent with the merged CAO implementation.<br>**Tasks:**<br>1 Rename package dir to lowercase PEP 8 + fix 7 imports<br>2 Add 3 submodules + recursive init<br>3 Edit pyproject.toml (1 line) + create .python-version + setup.sh<br>3b Fix setup.sh — `PYBIND11_FINDPYTHON=ON` + manifpy idempotency guard<br>4 Run ./setup.sh end-to-end + pytest (depends on #1, #2, #3) — ATTEMPT 1 BLOCKED<br>4b Re-run ./setup.sh (fixed) + pytest (depends on #3b, #6)<br>5 Update README (depends on #7)<br>6 Replace deleted SE23 import with new-API equivalent (user-approved)<br>7 Fix SGal3 vs matrix mismatches (3 source sites + 4 fixture sites + 1 import) — pytest gate |

# https://github.com/y2d2/ARP_IMU.git
## master
### planning/arp-imu-active-measurements/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 11 | planning/arp-imu-active-measurements/work_plan.md | Implementation Plan: ARP_IMU Active Measurements | open | ☐ |

| details |
|---------|
| **Goal:** Implement the SGal3 active-measurements buffer, roll/pitch from buffer, and rewrite the analysis script<br>**Tasks:**<br>1 Add active-measurements buffer infrastructure to ARP_IMU<br>2 Implement `get_imu_measurments()` method<br>3 Implement `get_uwb_range()` method<br>4 Rewrite `get_roll_pitch()` method<br>5 Rewrite `experiments/arp_imu_analysis.py` as lean driver |

# https://github.com/y2d2/ARP_MPE.git
## mpe-rl-project
### planning/observation-tokenisation/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 11 | planning/observation-tokenisation/work_plan.md | Task Plan: Observation Tokenisation | open | ☐ |

| details |
|---------|
| **Goal:** Set Transformer entity-token observation pipeline on the custom BaseAgent track, a working PPO rollout loop, and a full ablation on `simple_spread_v3`.<br>**Tasks:**<br>1 wrapper step fix<br>2 obs adapter<br>3 set transformer<br>4 entity agent<br>5 rollout collector<br>6 ppo training<br>7 ablation |

# https://github.com/y2d2/ARP_implementations.git
## main
### planning/repo-review-2026-11-17/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 11 | planning/repo-review-2026-11-17/work_plan.md | Work Plan: Repo review — verify findings, then fix | open | ☐ |

| details |
|---------|
| **Goal:** Confirm the 2026-11-17 review findings with reproducible probes, then fix the confirmed ones.<br>**Tasks:**<br>2 SGal3 loop indexing (B1, U1, M2)<br>3 Baselines loop / NLS / 6DoF / check_validity (B2, B3, B6, B7, B9, M1)<br>4 Math checks — WLS Jacobian, algebraic logger, QCQP c5, arccos heading (B4, B5, B8, M3) |

# https://github.com/y2d2/ARP_roadmap.git
## feature/dual-mode-roadmap
### planning/orbit-dmp-unification/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 51 | planning/orbit-dmp-unification/work_plan.md | Work Plan: Unify ORBIT DMP Questionnaire Answers | open | ☐ |

| details |
|---------|
| **Goal:** Merge the 5 partner responses in `projects/ORBIT/DMP Questionnaire ORBIT.xlsx` (Google Forms export) into a single, unified Markdown document that keeps per-research-group specifics and tracks every dataset.<br>**Tasks:**<br>1 Create the unified DMP Markdown document |

### planning/orbit-email-lists-per-wp/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 52 | planning/orbit-email-lists-per-wp/work_plan.md | Work plan — ORBIT e-mail lists per WP | open | ☐ |

| details |
|---------|
| **Goal:** Move the per-WP copy-paste e-mail lines in `projects/ORBIT/ORBIT_people_per_WP.md` from the separate "## E-mail lists" section into each WP section; keep one "All" line.<br>**Tasks:**<br>1 relocate e-mail lists |

### planning/orbit-people-update/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 53 | planning/orbit-people-update/work_plan.md | Work Plan: ORBIT people per WP — Oct 2026 refresh | open | ☐ |

| details |
|---------|
| **Goal:** Update `projects/ORBIT/ORBIT_people_per_WP.md` with staffing changes since 13 Oct 2026.<br>**Tasks:**<br>1 Rewrite file + commit |

### planning/orbit-plenary-i-slides/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 54 | planning/orbit-plenary-i-slides/work_plan.md | Work plan — ORBIT Plenary I (28 Oct 2026): slides, deck, post-meeting outcomes | open | ☐ |

| details |
|---------|
| **Goal:** —<br>**Tasks:**<br>9 outcomes report<br>10 cleaned deck |

### planning/unitree-vault-note/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 55 | planning/unitree-vault-note/work_plan.md | Task Plan: Unitree FARI acquisition vault note | open | ☐ |

| details |
|---------|
| **Goal:** Persist a short, clean note in the ORBIT vault documenting the Unitree G1/Go2 configuration FARI put in the tender (PROC 1), with mail provenance tags.<br>**Tasks:**<br>1 Create the vault note<br>2 Commit + push the note (depends on #1) |

## feature/orbit-rob-kickoff-slides
### planning/esa-bt-gate0-slide/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 111 | planning/esa-bt-gate0-slide/work_plan.md | Work plan — ESA OSIP imec BT Gate 0 slide | open | ☐ |

| details |
|---------|
| **Goal:** —<br>**Tasks:**<br>1 fill bt slide |

### planning/esa-no-open-source/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 112 | planning/esa-no-open-source/work_plan.md | Work plan — ESA OSIP: drop open-source commitment | open | ☐ |

| details |
|---------|
| **Goal:** —<br>**Tasks:**<br>1 remove open source |

### planning/orbit-demo1-visual/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 113 | planning/orbit-demo1-visual/work_plan.md | Work plan — ORBIT Demonstrator 1, Scenario B visual | open | ☐ |

| details |
|---------|
| **Goal:** —<br>**Tasks:**<br>1 TikZ schematic of 2027 Scenario B, render PDF + PNG, visual check<br>2 teaser illustration, robot B = Unitree G1 humanoid |

### planning/orbit-dmp-unification/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 114 | planning/orbit-dmp-unification/work_plan.md | Work Plan: Unify ORBIT DMP Questionnaire Answers | open | ☐ |

| details |
|---------|
| **Goal:** Merge the 5 partner responses in `projects/ORBIT/DMP Questionnaire ORBIT.xlsx` (Google Forms export) into a single, unified Markdown document that keeps per-research-group specifics and tracks every dataset.<br>**Tasks:**<br>1 Create the unified DMP Markdown document |

### planning/orbit-dmp/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 115 | planning/orbit-dmp/work_plan.md | Task Plan: ORBIT DMP v0 — consortium data management plan | open | ☐ |

| details |
|---------|
| **Goal:** Build `projects/ORBIT/DMP/ORBIT_DMP_v0.md`, the table-first consortium DMP, in five sequential sub-agent tasks.<br>**Tasks:**<br>1 Skeleton & front matter (no dependencies)<br>2 Master table 1 (depends on #1)<br>3 Supporting tables 2–6 (depends on #2)<br>4 Minimal prose + Coera/IP text (depends on #3)<br>5 QA pass (depends on #4)<br>6 Coera removal + ethics commission (depends on #5; user-directed change 2026-11-10)<br>7 brubotics-hamed label → VUB-IMS-confidential (depends on #6; user-directed change 2026-11-10)<br>8 add IDLab-IWIN to consortium list (depends on #7; user-directed change 2026-11-10)<br>9 IDLab-IWIN → IDLab-IWINE (depends on #8; verified externally 2026-11-16)<br>10 Table 1 — drop Label & Storage & backup columns (depends on #9; user-directed 2026-11-16)<br>11 EM entries → EM-IWINE (depends on #10; user-directed 2026-11-16)<br>12 Dataset IDs in Table 1, cross-referenced in Tables 2–6 (depends on #11; user-approved 2026-11-16)<br>13 §6 — drop IPTA sentence, use dataset IDs (depends on #12; user-directed 2026-11-16)<br>14 Remove Miluv dataset, keep new robot localisation dataset B2 (depends on #13; user-directed 2026-11-16)<br>15 Data IDs as first column in Tables 2–6 (depends on #14; user-directed 2026-11-16)<br>16 Renumber B IDs, unify table inputs, full ID coverage (depends on #15; user-directed 2026-11-18)<br>17 Funding scheme imec PROSPECT (depends on #16; user-confirmed 2026-11-18)<br>18 Remove section 6 (depends on #17; user-directed 2026-11-18)<br>19 Plain "Reused" in Table 1 (depends on #18; user-directed 2026-11-18)<br>20 Move C5 to A8, renumber C6 → C5 (depends on #19; user-directed 2026-11-18) |

### planning/orbit-email-lists-per-wp/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 116 | planning/orbit-email-lists-per-wp/work_plan.md | Work plan — ORBIT e-mail lists per WP | open | ☐ |

| details |
|---------|
| **Goal:** Move the per-WP copy-paste e-mail lines in `projects/ORBIT/ORBIT_people_per_WP.md` from the separate "## E-mail lists" section into each WP section; keep one "All" line.<br>**Tasks:**<br>1 relocate e-mail lists |

### planning/orbit-people-update/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 117 | planning/orbit-people-update/work_plan.md | Work Plan: ORBIT people per WP — Oct 2026 refresh | open | ☐ |

| details |
|---------|
| **Goal:** Update `projects/ORBIT/ORBIT_people_per_WP.md` with staffing changes since 13 Oct 2026.<br>**Tasks:**<br>1 Rewrite file + commit |

### planning/orbit-plenary-i-slides/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 118 | planning/orbit-plenary-i-slides/work_plan.md | Work plan — ORBIT Plenary I (28 Oct 2026): slides, deck, post-meeting outcomes | open | ☐ |

| details |
|---------|
| **Goal:** —<br>**Tasks:**<br>9 outcomes report<br>10 cleaned deck |

### planning/orbit-rob-kickoff-slides/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 119 | planning/orbit-rob-kickoff-slides/work_plan.md | Task Plan: ORBIT ROB kick-off presentation (drafts) | open | ☐ |

| details |
|---------|
| **Goal:** Produce a 30-min ORBIT presentation for the ROB kick-off Advisory Board (25 Nov 2026, Ghent), starting with a storyboard draft.<br>**Tasks:**<br>1 Storyboard (markdown)<br>2 Integrate user edits into storyboard<br>3 Build draft .pptx<br>4 Picture-led storyboard v2<br>5 Picture-led draft .pptx<br>6 Image-generator prompts<br>7 TikZ illustration kit + text-free teaser + pilots P02/P09/P16 |

### planning/orbit-rob-kickoff-workshop-notes/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 120 | planning/orbit-rob-kickoff-workshop-notes/work_plan.md | Work plan — ORBIT ROB kick-off workshop notes (Autonomous Navigation, group 2) | open | ☐ |

| details |
|---------|
| **Goal:** Turn the 5 board photos + note-taker notes from the 25/11 ROB kick-off "Autonomous Navigation" table (deSter, Pfizer, DroneDivision, RBD Robotics, coera) into a Markdown summary mirroring `workshop orbit en fidex.docx` (spoken summary + board transcription per company), then commit/push the agreed scope.<br>**Tasks:**<br>1 workshop md and commit |

### planning/unitree-vault-note/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 121 | planning/unitree-vault-note/work_plan.md | Task Plan: Unitree FARI acquisition vault note | open | ☐ |

| details |
|---------|
| **Goal:** Persist a short, clean note in the ORBIT vault documenting the Unitree G1/Go2 configuration FARI put in the tender (PROC 1), with mail provenance tags.<br>**Tasks:**<br>1 Create the vault note<br>2 Commit + push the note (depends on #1) |

## main
### planning/esa-bt-gate0-slide/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 91 | planning/esa-bt-gate0-slide/work_plan.md | Work plan — ESA OSIP imec BT Gate 0 slide | open | ☐ |

| details |
|---------|
| **Goal:** —<br>**Tasks:**<br>1 fill bt slide |

### planning/esa-no-open-source/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 92 | planning/esa-no-open-source/work_plan.md | Work plan — ESA OSIP: drop open-source commitment | open | ☐ |

| details |
|---------|
| **Goal:** —<br>**Tasks:**<br>1 remove open source |

### planning/orbit-demo1-visual/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 93 | planning/orbit-demo1-visual/work_plan.md | Work plan — ORBIT Demonstrator 1, Scenario B visual | open | ☐ |

| details |
|---------|
| **Goal:** —<br>**Tasks:**<br>1 TikZ schematic of 2027 Scenario B, render PDF + PNG, visual check<br>2 teaser illustration, robot B = Unitree G1 humanoid |

### planning/orbit-dmp-unification/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 94 | planning/orbit-dmp-unification/work_plan.md | Work Plan: Unify ORBIT DMP Questionnaire Answers | open | ☐ |

| details |
|---------|
| **Goal:** Merge the 5 partner responses in `projects/ORBIT/DMP Questionnaire ORBIT.xlsx` (Google Forms export) into a single, unified Markdown document that keeps per-research-group specifics and tracks every dataset.<br>**Tasks:**<br>1 Create the unified DMP Markdown document |

### planning/orbit-dmp/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 95 | planning/orbit-dmp/work_plan.md | Task Plan: ORBIT DMP v0 — consortium data management plan | open | ☐ |

| details |
|---------|
| **Goal:** Build `projects/ORBIT/DMP/ORBIT_DMP_v0.md`, the table-first consortium DMP, in five sequential sub-agent tasks.<br>**Tasks:**<br>1 Skeleton & front matter (no dependencies)<br>2 Master table 1 (depends on #1)<br>3 Supporting tables 2–6 (depends on #2)<br>4 Minimal prose + Coera/IP text (depends on #3)<br>5 QA pass (depends on #4)<br>6 Coera removal + ethics commission (depends on #5; user-directed change 2026-11-10)<br>7 brubotics-hamed label → VUB-IMS-confidential (depends on #6; user-directed change 2026-11-10)<br>8 add IDLab-IWIN to consortium list (depends on #7; user-directed change 2026-11-10)<br>9 IDLab-IWIN → IDLab-IWINE (depends on #8; verified externally 2026-11-16)<br>10 Table 1 — drop Label & Storage & backup columns (depends on #9; user-directed 2026-11-16)<br>11 EM entries → EM-IWINE (depends on #10; user-directed 2026-11-16)<br>12 Dataset IDs in Table 1, cross-referenced in Tables 2–6 (depends on #11; user-approved 2026-11-16)<br>13 §6 — drop IPTA sentence, use dataset IDs (depends on #12; user-directed 2026-11-16)<br>14 Remove Miluv dataset, keep new robot localisation dataset B2 (depends on #13; user-directed 2026-11-16)<br>15 Data IDs as first column in Tables 2–6 (depends on #14; user-directed 2026-11-16)<br>16 Renumber B IDs, unify table inputs, full ID coverage (depends on #15; user-directed 2026-11-18)<br>17 Funding scheme imec PROSPECT (depends on #16; user-confirmed 2026-11-18)<br>18 Remove section 6 (depends on #17; user-directed 2026-11-18)<br>19 Plain "Reused" in Table 1 (depends on #18; user-directed 2026-11-18)<br>20 Move C5 to A8, renumber C6 → C5 (depends on #19; user-directed 2026-11-18) |

### planning/orbit-email-lists-per-wp/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 96 | planning/orbit-email-lists-per-wp/work_plan.md | Work plan — ORBIT e-mail lists per WP | open | ☐ |

| details |
|---------|
| **Goal:** Move the per-WP copy-paste e-mail lines in `projects/ORBIT/ORBIT_people_per_WP.md` from the separate "## E-mail lists" section into each WP section; keep one "All" line.<br>**Tasks:**<br>1 relocate e-mail lists |

### planning/orbit-people-update/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 97 | planning/orbit-people-update/work_plan.md | Work Plan: ORBIT people per WP — Oct 2026 refresh | open | ☐ |

| details |
|---------|
| **Goal:** Update `projects/ORBIT/ORBIT_people_per_WP.md` with staffing changes since 13 Oct 2026.<br>**Tasks:**<br>1 Rewrite file + commit |

### planning/orbit-plenary-i-slides/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 98 | planning/orbit-plenary-i-slides/work_plan.md | Work plan — ORBIT Plenary I (28 Oct 2026): slides, deck, post-meeting outcomes | open | ☐ |

| details |
|---------|
| **Goal:** —<br>**Tasks:**<br>9 outcomes report<br>10 cleaned deck |

### planning/unitree-vault-note/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 99 | planning/unitree-vault-note/work_plan.md | Task Plan: Unitree FARI acquisition vault note | open | ☐ |

| details |
|---------|
| **Goal:** Persist a short, clean note in the ORBIT vault documenting the Unitree G1/Go2 configuration FARI put in the tender (PROC 1), with mail provenance tags.<br>**Tasks:**<br>1 Create the vault note<br>2 Commit + push the note (depends on #1) |

## oc/orbit-dmp-plan
### planning/orbit-dmp-unification/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 61 | planning/orbit-dmp-unification/work_plan.md | Work Plan: Unify ORBIT DMP Questionnaire Answers | open | ☐ |

| details |
|---------|
| **Goal:** Merge the 5 partner responses in `projects/ORBIT/DMP Questionnaire ORBIT.xlsx` (Google Forms export) into a single, unified Markdown document that keeps per-research-group specifics and tracks every dataset.<br>**Tasks:**<br>1 Create the unified DMP Markdown document |

### planning/orbit-dmp/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 62 | planning/orbit-dmp/work_plan.md | Task Plan: ORBIT DMP v0 — consortium data management plan | open | ☐ |

| details |
|---------|
| **Goal:** Build `projects/ORBIT/DMP/ORBIT_DMP_v0.md`, the table-first consortium DMP, in five sequential sub-agent tasks.<br>**Tasks:**<br>1 Skeleton & front matter (no dependencies)<br>2 Master table 1 (depends on #1)<br>3 Supporting tables 2–6 (depends on #2)<br>4 Minimal prose + Coera/IP text (depends on #3)<br>5 QA pass (depends on #4)<br>6 Coera removal + ethics commission (depends on #5; user-directed change 2026-11-10)<br>7 brubotics-hamed label → VUB-IMS-confidential (depends on #6; user-directed change 2026-11-10)<br>8 add IDLab-IWIN to consortium list (depends on #7; user-directed change 2026-11-10)<br>9 IDLab-IWIN → IDLab-IWINE (depends on #8; verified externally 2026-11-16)<br>10 Table 1 — drop Label & Storage & backup columns (depends on #9; user-directed 2026-11-16)<br>11 EM entries → EM-IWINE (depends on #10; user-directed 2026-11-16)<br>12 Dataset IDs in Table 1, cross-referenced in Tables 2–6 (depends on #11; user-approved 2026-11-16)<br>13 §6 — drop IPTA sentence, use dataset IDs (depends on #12; user-directed 2026-11-16)<br>14 Remove Miluv dataset, keep new robot localisation dataset B2 (depends on #13; user-directed 2026-11-16)<br>15 Data IDs as first column in Tables 2–6 (depends on #14; user-directed 2026-11-16)<br>16 Renumber B IDs, unify table inputs, full ID coverage (depends on #15; user-directed 2026-11-18)<br>17 Funding scheme imec PROSPECT (depends on #16; user-confirmed 2026-11-18)<br>18 Remove section 6 (depends on #17; user-directed 2026-11-18)<br>19 Plain "Reused" in Table 1 (depends on #18; user-directed 2026-11-18)<br>20 Move C5 to A8, renumber C6 → C5 (depends on #19; user-directed 2026-11-18) |

### planning/orbit-people-update/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 63 | planning/orbit-people-update/work_plan.md | Work Plan: ORBIT people per WP — Oct 2026 refresh | open | ☐ |

| details |
|---------|
| **Goal:** Update `projects/ORBIT/ORBIT_people_per_WP.md` with staffing changes since 13 Oct 2026.<br>**Tasks:**<br>1 Rewrite file + commit |

### planning/orbit-plenary-i-slides/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 64 | planning/orbit-plenary-i-slides/work_plan.md | Work plan — ORBIT Plenary I (28 Oct 2026): slides, deck, post-meeting outcomes | open | ☐ |

| details |
|---------|
| **Goal:** —<br>**Tasks:**<br>9 outcomes report<br>10 cleaned deck |

### planning/todos-sync-20261109/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 65 | planning/todos-sync-20261109/work_plan.md | Work Plan: Todos sync 2026-11-09 — archive completed items + update active todos from new mail | open | ☐ |

| details |
|---------|
| **Goal:** Move all 22 completed (`[x]`) items out of `todos/active.md` into `todos/done.md`, then fold the 33 new mail messages (2026-11-04 → 2026-11-09) into `todos/active.md` as provenance-tagged updates/new lines, and commit + push the two todo files.<br>**Tasks:**<br>1 Move 22 checked items to `todos/done.md`<br>2 Update `todos/active.md` from the 33 new mails<br>3 Commit + push the two todo files |

### planning/unitree-vault-note/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 66 | planning/unitree-vault-note/work_plan.md | Task Plan: Unitree FARI acquisition vault note | open | ☐ |

| details |
|---------|
| **Goal:** Persist a short, clean note in the ORBIT vault documenting the Unitree G1/Go2 configuration FARI put in the tender (PROC 1), with mail provenance tags.<br>**Tasks:**<br>1 Create the vault note<br>2 Commit + push the note (depends on #1) |

## orbit-demo1-visual
### planning/orbit-demo1-visual/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 61 | planning/orbit-demo1-visual/work_plan.md | Work plan — ORBIT Demonstrator 1, Scenario B visual | open | ☐ |

| details |
|---------|
| **Goal:** —<br>**Tasks:**<br>1 TikZ schematic of 2027 Scenario B, render PDF + PNG, visual check<br>2 teaser illustration, robot B = Unitree G1 humanoid |

### planning/orbit-dmp-unification/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 62 | planning/orbit-dmp-unification/work_plan.md | Work Plan: Unify ORBIT DMP Questionnaire Answers | open | ☐ |

| details |
|---------|
| **Goal:** Merge the 5 partner responses in `projects/ORBIT/DMP Questionnaire ORBIT.xlsx` (Google Forms export) into a single, unified Markdown document that keeps per-research-group specifics and tracks every dataset.<br>**Tasks:**<br>1 Create the unified DMP Markdown document |

### planning/orbit-people-update/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 63 | planning/orbit-people-update/work_plan.md | Work Plan: ORBIT people per WP — Oct 2026 refresh | open | ☐ |

| details |
|---------|
| **Goal:** Update `projects/ORBIT/ORBIT_people_per_WP.md` with staffing changes since 13 Oct 2026.<br>**Tasks:**<br>1 Rewrite file + commit |

### planning/orbit-plenary-i-slides/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 64 | planning/orbit-plenary-i-slides/work_plan.md | Work plan — ORBIT Plenary I (28 Oct 2026): slides, deck, post-meeting outcomes | open | ☐ |

| details |
|---------|
| **Goal:** —<br>**Tasks:**<br>9 outcomes report<br>10 cleaned deck |

### planning/todos-sync-20261109/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 65 | planning/todos-sync-20261109/work_plan.md | Work Plan: Todos sync 2026-11-09 — archive completed items + update active todos from new mail | open | ☐ |

| details |
|---------|
| **Goal:** Move all 22 completed (`[x]`) items out of `todos/active.md` into `todos/done.md`, then fold the 33 new mail messages (2026-11-04 → 2026-11-09) into `todos/active.md` as provenance-tagged updates/new lines, and commit + push the two todo files.<br>**Tasks:**<br>1 Move 22 checked items to `todos/done.md`<br>2 Update `todos/active.md` from the 33 new mails<br>3 Commit + push the two todo files |

### planning/unitree-vault-note/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 66 | planning/unitree-vault-note/work_plan.md | Task Plan: Unitree FARI acquisition vault note | open | ☐ |

| details |
|---------|
| **Goal:** Persist a short, clean note in the ORBIT vault documenting the Unitree G1/Go2 configuration FARI put in the tender (PROC 1), with mail provenance tags.<br>**Tasks:**<br>1 Create the vault note<br>2 Commit + push the note (depends on #1) |

# https://github.com/y2d2/ARP_utility_code.git
## fix/code-review-findings
### planning/basic-usage-notebook/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 41 | planning/basic-usage-notebook/work_plan.md | Work Plan: Basic-usage Jupyter notebook | open | ☐ |

| details |
|---------|
| **Goal:** Add a short, runnable Jupyter notebook demonstrating the library's core functionality, plus a dependency-free test that keeps it runnable.<br>**Tasks:**<br>1 notebook + cell-exec test + README pointer |

### planning/code-review-fixes/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 42 | planning/code-review-fixes/work_plan.md | Task Plan: Code-review findings — verify & fix | open | ☐ |

| details |
|---------|
| **Goal:** Confirm the findings of the 2026-11-16 critical review by execution, then fix every confirmed High/Medium finding plus cheap Low fixes.<br>**Tasks:**<br>1 Baseline test/lint run<br>2 Probe scripts confirming review findings |

### planning/python-3.12-upgrade/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 43 | planning/python-3.12-upgrade/work_plan.md | Task Plan: Move project from Python 3.11 to 3.12 | open | ☐ |

| details |
|---------|
| **Goal:** Retarget the repo's interpreter from Python 3.11 to 3.12 and prove the build and gates still pass.<br>**Tasks:**<br>1 Bump pins, relock, rebuild, verify |

### planning/repo-cleanup/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 44 | planning/repo-cleanup/work_plan.md | Work Plan: Repo Cleanup (remove SGal3_filters, deprecated modules, stray files; README mermaid rewrite) | open | ☐ |

| details |
|---------|
| **Goal:** Bring `arp_utility_code` to a single, honest state — only actively used code remains — with all dangling references updated, the suite strictly green, and a rewritten README carrying two Mermaid diagrams.<br>**Tasks:**<br>1 Remove the SGal3_filters package (files: `src/arp_utility_code/SGal3_filters/`, `tests/test_SGal3_filters/`, `docs/filters.rst`, doc/README references, `filterpy` dependency)<br>2 Remove deprecated/orphan UtilityCode modules + uwb_noise_filters (after Task 1 — shares `pyproject.toml`, `uv.lock`, `docs/*.rst`, `README.md`)<br>3 Remove the stray root task report (parallel with Task 1 — no shared files)<br>4 Rewrite the README with Mermaid overviews (after Task 2 — examples must run against the final package state)<br>5 Verify all gates and finalize (after all — push + PR URL + draft description) |

## main
### planning/basic-usage-notebook/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 41 | planning/basic-usage-notebook/work_plan.md | Work Plan: Basic-usage Jupyter notebook | open | ☐ |

| details |
|---------|
| **Goal:** Add a short, runnable Jupyter notebook demonstrating the library's core functionality, plus a dependency-free test that keeps it runnable.<br>**Tasks:**<br>1 notebook + cell-exec test + README pointer |

### planning/code-review-fixes/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 42 | planning/code-review-fixes/work_plan.md | Task Plan: Code-review findings — verify & fix | open | ☐ |

| details |
|---------|
| **Goal:** Confirm the findings of the 2026-11-16 critical review by execution, then fix every confirmed High/Medium finding plus cheap Low fixes.<br>**Tasks:**<br>1 Baseline test/lint run<br>2 Probe scripts confirming review findings |

### planning/python-3.12-upgrade/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 43 | planning/python-3.12-upgrade/work_plan.md | Task Plan: Move project from Python 3.11 to 3.12 | open | ☐ |

| details |
|---------|
| **Goal:** Retarget the repo's interpreter from Python 3.11 to 3.12 and prove the build and gates still pass.<br>**Tasks:**<br>1 Bump pins, relock, rebuild, verify |

### planning/repo-cleanup/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 44 | planning/repo-cleanup/work_plan.md | Work Plan: Repo Cleanup (remove SGal3_filters, deprecated modules, stray files; README mermaid rewrite) | open | ☐ |

| details |
|---------|
| **Goal:** Bring `arp_utility_code` to a single, honest state — only actively used code remains — with all dangling references updated, the suite strictly green, and a rewritten README carrying two Mermaid diagrams.<br>**Tasks:**<br>1 Remove the SGal3_filters package (files: `src/arp_utility_code/SGal3_filters/`, `tests/test_SGal3_filters/`, `docs/filters.rst`, doc/README references, `filterpy` dependency)<br>2 Remove deprecated/orphan UtilityCode modules + uwb_noise_filters (after Task 1 — shares `pyproject.toml`, `uv.lock`, `docs/*.rst`, `README.md`)<br>3 Remove the stray root task report (parallel with Task 1 — no shared files)<br>4 Rewrite the README with Mermaid overviews (after Task 2 — examples must run against the final package state)<br>5 Verify all gates and finalize (after all — push + PR URL + draft description) |

# https://github.com/y2d2/PRP_ARP_M.git
## docs/readme-diagram-rework
### planning/arp-prp-data-import-verification/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 11 | planning/arp-prp-data-import-verification/work_plan.md | Task Plan: ARP_PRP data import verification | open | ☐ |

| details |
|---------|
| **Goal:** Verify experimentally that the sensor data in `/workspace/data/ARP_PRP*/exp*` is importable by the data-loading harness of the `ARP_utility_code` module — TurtleBot wheel odometry, ESP IMU/UWB, and Husky LiDAR point cloud — and produce an evidence-backed PASS/FAIL report.<br>**Tasks:**<br>1 Provision verification environment<br>2 Probe bag-reader format support (depends on Task 1)<br>3 Full import verification (depends on Task 2)<br>4 (CONDITIONAL — only after user approval) Fix mcap import gap — **CANCELLED (2026-10-19)** |

## docs/readme-mermaid-fix
### planning/arp-prp-data-import-verification/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 11 | planning/arp-prp-data-import-verification/work_plan.md | Task Plan: ARP_PRP data import verification | open | ☐ |

| details |
|---------|
| **Goal:** Verify experimentally that the sensor data in `/workspace/data/ARP_PRP*/exp*` is importable by the data-loading harness of the `ARP_utility_code` module — TurtleBot wheel odometry, ESP IMU/UWB, and Husky LiDAR point cloud — and produce an evidence-backed PASS/FAIL report.<br>**Tasks:**<br>1 Provision verification environment<br>2 Probe bag-reader format support (depends on Task 1)<br>3 Full import verification (depends on Task 2)<br>4 (CONDITIONAL — only after user approval) Fix mcap import gap — **CANCELLED (2026-10-19)** |

## docs/repo-consistency-review
### planning/arp-prp-data-import-verification/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 21 | planning/arp-prp-data-import-verification/work_plan.md | Task Plan: ARP_PRP data import verification | open | ☐ |

| details |
|---------|
| **Goal:** Verify experimentally that the sensor data in `/workspace/data/ARP_PRP*/exp*` is importable by the data-loading harness of the `ARP_utility_code` module — TurtleBot wheel odometry, ESP IMU/UWB, and Husky LiDAR point cloud — and produce an evidence-backed PASS/FAIL report.<br>**Tasks:**<br>1 Provision verification environment<br>2 Probe bag-reader format support (depends on Task 1)<br>3 Full import verification (depends on Task 2)<br>4 (CONDITIONAL — only after user approval) Fix mcap import gap — **CANCELLED (2026-10-19)** |

### planning/readme-mermaid-fix/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 22 | planning/readme-mermaid-fix/work_plan.md | Task Plan: Fix mindmap parse error in root README | open | ☐ |

| details |
|---------|
| **Goal:** Repair the first (structure) mermaid diagram in `README.md`, which fails to render on GitHub with `Parse error on line 13 ... Expecting 'SPACELINE', 'NL', 'EOF', got 'NODE_ID'`.<br>**Tasks:**<br>1 Rewrite the 17 two-token label lines in the first mermaid block |

## feat/beam-flip-event-detection
### planning/arp-prp-data-import-verification/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 21 | planning/arp-prp-data-import-verification/work_plan.md | Task Plan: ARP_PRP data import verification | open | ☐ |

| details |
|---------|
| **Goal:** Verify experimentally that the sensor data in `/workspace/data/ARP_PRP*/exp*` is importable by the data-loading harness of the `ARP_utility_code` module — TurtleBot wheel odometry, ESP IMU/UWB, and Husky LiDAR point cloud — and produce an evidence-backed PASS/FAIL report.<br>**Tasks:**<br>1 Provision verification environment<br>2 Probe bag-reader format support (depends on Task 1)<br>3 Full import verification (depends on Task 2)<br>4 (CONDITIONAL — only after user approval) Fix mcap import gap — **CANCELLED (2026-10-19)** |

### planning/run-all-arp-prp-experiments/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 22 | planning/run-all-arp-prp-experiments/work_plan.md | Work Plan: Run-all ARP-PRP experiments (pilot = exp15) | open | ☐ |

| details |
|---------|
| **Goal:** Decompose `run_all_arp_prp_experiments_plan.md` into self-contained sub-agent tasks; drive one pilot experiment (exp15) end-to-end producing metrics + true-vs-estimated trajectory PNG + 2D/3D GIFs.<br>**Tasks:**<br>1 Variable-length event detection (NN pairing)<br>2 Real-data calibration module<br>3 Run-all driver (depends on #1, #2, #4)<br>4 Figure + GIF renderer<br>5 Pilot run + verification gate (depends on #3)<br>6 Renderer 2× GIF size + 60° 3D camera (user request 2026-11-14)<br>7 Launch full 21-experiment batch (user request 2026-11-14) |

## feat/py312-submodule-bump
### planning/arp-prp-data-import-verification/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 21 | planning/arp-prp-data-import-verification/work_plan.md | Task Plan: ARP_PRP data import verification | open | ☐ |

| details |
|---------|
| **Goal:** Verify experimentally that the sensor data in `/workspace/data/ARP_PRP*/exp*` is importable by the data-loading harness of the `ARP_utility_code` module — TurtleBot wheel odometry, ESP IMU/UWB, and Husky LiDAR point cloud — and produce an evidence-backed PASS/FAIL report.<br>**Tasks:**<br>1 Provision verification environment<br>2 Probe bag-reader format support (depends on Task 1)<br>3 Full import verification (depends on Task 2)<br>4 (CONDITIONAL — only after user approval) Fix mcap import gap — **CANCELLED (2026-10-19)** |

### planning/run-all-arp-prp-experiments/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 22 | planning/run-all-arp-prp-experiments/work_plan.md | Work Plan: Run-all ARP-PRP experiments (pilot = exp15) | open | ☐ |

| details |
|---------|
| **Goal:** Decompose `run_all_arp_prp_experiments_plan.md` into self-contained sub-agent tasks; drive one pilot experiment (exp15) end-to-end producing metrics + true-vs-estimated trajectory PNG + 2D/3D GIFs.<br>**Tasks:**<br>1 Variable-length event detection (NN pairing)<br>2 Real-data calibration module<br>3 Run-all driver (depends on #1, #2, #4)<br>4 Figure + GIF renderer<br>5 Pilot run + verification gate (depends on #3)<br>6 Renderer 2× GIF size + 60° 3D camera (user request 2026-11-14)<br>7 Launch full 21-experiment batch (user request 2026-11-14) |

## feat/run-all-arp-prp-experiments
### planning/arp-prp-data-import-verification/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 21 | planning/arp-prp-data-import-verification/work_plan.md | Task Plan: ARP_PRP data import verification | open | ☐ |

| details |
|---------|
| **Goal:** Verify experimentally that the sensor data in `/workspace/data/ARP_PRP*/exp*` is importable by the data-loading harness of the `ARP_utility_code` module — TurtleBot wheel odometry, ESP IMU/UWB, and Husky LiDAR point cloud — and produce an evidence-backed PASS/FAIL report.<br>**Tasks:**<br>1 Provision verification environment<br>2 Probe bag-reader format support (depends on Task 1)<br>3 Full import verification (depends on Task 2)<br>4 (CONDITIONAL — only after user approval) Fix mcap import gap — **CANCELLED (2026-10-19)** |

### planning/run-all-arp-prp-experiments/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 22 | planning/run-all-arp-prp-experiments/work_plan.md | Work Plan: Run-all ARP-PRP experiments (pilot = exp15) | open | ☐ |

| details |
|---------|
| **Goal:** Decompose `run_all_arp_prp_experiments_plan.md` into self-contained sub-agent tasks; drive one pilot experiment (exp15) end-to-end producing metrics + true-vs-estimated trajectory PNG + 2D/3D GIFs.<br>**Tasks:**<br>1 Variable-length event detection (NN pairing)<br>2 Real-data calibration module<br>3 Run-all driver (depends on #1, #2, #4)<br>4 Figure + GIF renderer<br>5 Pilot run + verification gate (depends on #3)<br>6 Renderer 2× GIF size + 60° 3D camera (user request 2026-11-14)<br>7 Launch full 21-experiment batch (user request 2026-11-14) |

## main
### planning/arp-prp-data-import-verification/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 11 | planning/arp-prp-data-import-verification/work_plan.md | Task Plan: ARP_PRP data import verification | open | ☐ |

| details |
|---------|
| **Goal:** Verify experimentally that the sensor data in `/workspace/data/ARP_PRP*/exp*` is importable by the data-loading harness of the `ARP_utility_code` module — TurtleBot wheel odometry, ESP IMU/UWB, and Husky LiDAR point cloud — and produce an evidence-backed PASS/FAIL report.<br>**Tasks:**<br>1 Provision verification environment<br>2 Probe bag-reader format support (depends on Task 1)<br>3 Full import verification (depends on Task 2)<br>4 (CONDITIONAL — only after user approval) Fix mcap import gap — **CANCELLED (2026-10-19)** |

# https://github.com/y2d2/agentic_scripts.git
## feature/mail-guardrail-mbsync-exclusion
### planning/mail-keeper-model-fix/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 41 | planning/mail-keeper-model-fix/work_plan.md | Work Plan: mail-keeper model-ref fix + error-text logging | open | ☐ |

| details |
|---------|
| **Goal:** Restore the broken mail-keeper agent dispatch (dead provider ID in the runner's `--model`) and make workflow error text visible in run logs so the next config drift is diagnosable.<br>**Tasks:**<br>1 Fix model reference + sync references + log workflow error text |

### planning/mail-keeper-pruning/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 42 | planning/mail-keeper-pruning/work_plan.md | Task Plan: mail-keeper — runner-owned pruning of checked daily entries | open | ☐ |

| details |
|---------|
| **Goal:** Fix the mail-keeper workflow so checked (`- [x]`) day-file entries are pruned and emptied day-files deleted on **every** scheduled run — including runs with no new mail — instead of only inside the (sometimes hallucinating) LLM agent step.<br>**Tasks:**<br>1 Deterministic prune module + unit tests<br>2 Runner hook in MailKeeper + integration tests (depends on #1)<br>3 Skill doc — remove agent-side pruning (parallel with #1)<br>4 Forced backlog cleanup + end-to-end verification (depends on #2) |

### planning/smoke-test-mail-isolation/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 43 | planning/smoke-test-mail-isolation/work_plan.md | Work Plan: Hermetic MAIL_* env isolation in smoke tests | open | ☐ |

| details |
|---------|
| **Goal:** Make the smoke-test mail-env isolation live in the autouse fixture (as documented) so no in-process `run()` in the smoke suite can reach the real notmuch index and dispatch a live agent.<br>**Tasks:**<br>1 Move MAIL_* isolation into the autouse fixtures + pin it in the buggy test |

### planning/workflows-mail-keeper/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 44 | planning/workflows-mail-keeper/work_plan.md | Work Plan: agentic_scripts — Mail-Keeper Workflow | open | ☐ |

| details |
|---------|
| **Goal:** Orchestration work plan for `planning/workflows-mail-keeper/workflows-mail-keeper_plan.md` — ship the `mail-search` CLI over the maintained notmuch index, the mail-keeper workflow module (freshness canary, backfill-aware new-mail detection, manifest, batched agent invocation, processed log, guardrail verification), the real `email-routes.md`, and the hermetic smoke proving the end-to-end acceptance criteria with a fake agent.<br>**Tasks:**<br>1 `mail-search` CLI + index-freshness canary<br>2 Real `email-routes.md`<br>3 Mail-keeper workflow module (core)<br>4 Smoke test, README, env<br>5 Backfill redesign — newest-first with 1-year floor<br>5b Batch cap, cross-folder new-first, true per-folder frontier<br>5c Base reader decode fix (acceptance blocker) |

## feature/opencode-v2-run
### planning/mail-keeper-model-fix/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 41 | planning/mail-keeper-model-fix/work_plan.md | Work Plan: mail-keeper model-ref fix + error-text logging | open | ☐ |

| details |
|---------|
| **Goal:** Restore the broken mail-keeper agent dispatch (dead provider ID in the runner's `--model`) and make workflow error text visible in run logs so the next config drift is diagnosable.<br>**Tasks:**<br>1 Fix model reference + sync references + log workflow error text |

### planning/mail-keeper-pruning/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 42 | planning/mail-keeper-pruning/work_plan.md | Task Plan: mail-keeper — runner-owned pruning of checked daily entries | open | ☐ |

| details |
|---------|
| **Goal:** Fix the mail-keeper workflow so checked (`- [x]`) day-file entries are pruned and emptied day-files deleted on **every** scheduled run — including runs with no new mail — instead of only inside the (sometimes hallucinating) LLM agent step.<br>**Tasks:**<br>1 Deterministic prune module + unit tests<br>2 Runner hook in MailKeeper + integration tests (depends on #1)<br>3 Skill doc — remove agent-side pruning (parallel with #1)<br>4 Forced backlog cleanup + end-to-end verification (depends on #2) |

### planning/smoke-test-mail-isolation/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 43 | planning/smoke-test-mail-isolation/work_plan.md | Work Plan: Hermetic MAIL_* env isolation in smoke tests | open | ☐ |

| details |
|---------|
| **Goal:** Make the smoke-test mail-env isolation live in the autouse fixture (as documented) so no in-process `run()` in the smoke suite can reach the real notmuch index and dispatch a live agent.<br>**Tasks:**<br>1 Move MAIL_* isolation into the autouse fixtures + pin it in the buggy test |

### planning/workflows-mail-keeper/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 44 | planning/workflows-mail-keeper/work_plan.md | Work Plan: agentic_scripts — Mail-Keeper Workflow | open | ☐ |

| details |
|---------|
| **Goal:** Orchestration work plan for `planning/workflows-mail-keeper/workflows-mail-keeper_plan.md` — ship the `mail-search` CLI over the maintained notmuch index, the mail-keeper workflow module (freshness canary, backfill-aware new-mail detection, manifest, batched agent invocation, processed log, guardrail verification), the real `email-routes.md`, and the hermetic smoke proving the end-to-end acceptance criteria with a fake agent.<br>**Tasks:**<br>1 `mail-search` CLI + index-freshness canary<br>2 Real `email-routes.md`<br>3 Mail-keeper workflow module (core)<br>4 Smoke test, README, env<br>5 Backfill redesign — newest-first with 1-year floor<br>5b Batch cap, cross-folder new-first, true per-folder frontier<br>5c Base reader decode fix (acceptance blocker) |

## feature/roadmap-dev-workflow
### planning/mail-keeper-model-fix/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 41 | planning/mail-keeper-model-fix/work_plan.md | Work Plan: mail-keeper model-ref fix + error-text logging | open | ☐ |

| details |
|---------|
| **Goal:** Restore the broken mail-keeper agent dispatch (dead provider ID in the runner's `--model`) and make workflow error text visible in run logs so the next config drift is diagnosable.<br>**Tasks:**<br>1 Fix model reference + sync references + log workflow error text |

### planning/mail-keeper-pruning/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 42 | planning/mail-keeper-pruning/work_plan.md | Task Plan: mail-keeper — runner-owned pruning of checked daily entries | open | ☐ |

| details |
|---------|
| **Goal:** Fix the mail-keeper workflow so checked (`- [x]`) day-file entries are pruned and emptied day-files deleted on **every** scheduled run — including runs with no new mail — instead of only inside the (sometimes hallucinating) LLM agent step.<br>**Tasks:**<br>1 Deterministic prune module + unit tests<br>2 Runner hook in MailKeeper + integration tests (depends on #1)<br>3 Skill doc — remove agent-side pruning (parallel with #1)<br>4 Forced backlog cleanup + end-to-end verification (depends on #2) |

### planning/smoke-test-mail-isolation/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 43 | planning/smoke-test-mail-isolation/work_plan.md | Work Plan: Hermetic MAIL_* env isolation in smoke tests | open | ☐ |

| details |
|---------|
| **Goal:** Make the smoke-test mail-env isolation live in the autouse fixture (as documented) so no in-process `run()` in the smoke suite can reach the real notmuch index and dispatch a live agent.<br>**Tasks:**<br>1 Move MAIL_* isolation into the autouse fixtures + pin it in the buggy test |

### planning/workflows-mail-keeper/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 44 | planning/workflows-mail-keeper/work_plan.md | Work Plan: agentic_scripts — Mail-Keeper Workflow | open | ☐ |

| details |
|---------|
| **Goal:** Orchestration work plan for `planning/workflows-mail-keeper/workflows-mail-keeper_plan.md` — ship the `mail-search` CLI over the maintained notmuch index, the mail-keeper workflow module (freshness canary, backfill-aware new-mail detection, manifest, batched agent invocation, processed log, guardrail verification), the real `email-routes.md`, and the hermetic smoke proving the end-to-end acceptance criteria with a fake agent.<br>**Tasks:**<br>1 `mail-search` CLI + index-freshness canary<br>2 Real `email-routes.md`<br>3 Mail-keeper workflow module (core)<br>4 Smoke test, README, env<br>5 Backfill redesign — newest-first with 1-year floor<br>5b Batch cap, cross-folder new-first, true per-folder frontier<br>5c Base reader decode fix (acceptance blocker) |

## plan/agentic-workflows
### planning/mail-keeper-model-fix/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 41 | planning/mail-keeper-model-fix/work_plan.md | Work Plan: mail-keeper model-ref fix + error-text logging | open | ☐ |

| details |
|---------|
| **Goal:** Restore the broken mail-keeper agent dispatch (dead provider ID in the runner's `--model`) and make workflow error text visible in run logs so the next config drift is diagnosable.<br>**Tasks:**<br>1 Fix model reference + sync references + log workflow error text |

### planning/mail-keeper-pruning/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 42 | planning/mail-keeper-pruning/work_plan.md | Task Plan: mail-keeper — runner-owned pruning of checked daily entries | open | ☐ |

| details |
|---------|
| **Goal:** Fix the mail-keeper workflow so checked (`- [x]`) day-file entries are pruned and emptied day-files deleted on **every** scheduled run — including runs with no new mail — instead of only inside the (sometimes hallucinating) LLM agent step.<br>**Tasks:**<br>1 Deterministic prune module + unit tests<br>2 Runner hook in MailKeeper + integration tests (depends on #1)<br>3 Skill doc — remove agent-side pruning (parallel with #1)<br>4 Forced backlog cleanup + end-to-end verification (depends on #2) |

### planning/smoke-test-mail-isolation/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 43 | planning/smoke-test-mail-isolation/work_plan.md | Work Plan: Hermetic MAIL_* env isolation in smoke tests | open | ☐ |

| details |
|---------|
| **Goal:** Make the smoke-test mail-env isolation live in the autouse fixture (as documented) so no in-process `run()` in the smoke suite can reach the real notmuch index and dispatch a live agent.<br>**Tasks:**<br>1 Move MAIL_* isolation into the autouse fixtures + pin it in the buggy test |

### planning/workflows-mail-keeper/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 44 | planning/workflows-mail-keeper/work_plan.md | Work Plan: agentic_scripts — Mail-Keeper Workflow | open | ☐ |

| details |
|---------|
| **Goal:** Orchestration work plan for `planning/workflows-mail-keeper/workflows-mail-keeper_plan.md` — ship the `mail-search` CLI over the maintained notmuch index, the mail-keeper workflow module (freshness canary, backfill-aware new-mail detection, manifest, batched agent invocation, processed log, guardrail verification), the real `email-routes.md`, and the hermetic smoke proving the end-to-end acceptance criteria with a fake agent.<br>**Tasks:**<br>1 `mail-search` CLI + index-freshness canary<br>2 Real `email-routes.md`<br>3 Mail-keeper workflow module (core)<br>4 Smoke test, README, env<br>5 Backfill redesign — newest-first with 1-year floor<br>5b Batch cap, cross-folder new-first, true per-folder frontier<br>5c Base reader decode fix (acceptance blocker) |
