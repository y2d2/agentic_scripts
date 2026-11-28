# https://github.com/y2d2/ARP_1A_anchored_implementations.git
## feat/setup-sh-submodules
### planning/setup-sh-submodules/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 23 | planning/setup-sh-submodules/work_plan.md | Task Plan: setup.sh, submodules, pyproject, README | open | ☐ |

| # | details | ✓ |
|---|---------|---|
| G | Give the ARP_1A_anchored_implementations repo a modern, reproducible environment setup (venv + 3 submodules) and a README consistent with the merged CAO implementation. | ☐ |
| 1 | Rename package dir to lowercase PEP 8 + fix 7 imports | ☑ |
| 2 | Add 3 submodules + recursive init | ☑ |
| 3 | Edit pyproject.toml (1 line) + create .python-version + setup.sh | ☑ |
| 3b | Fix setup.sh — `PYBIND11_FINDPYTHON=ON` + manifpy idempotency guard | ☑ |
| 4 | Run ./setup.sh end-to-end + pytest (depends on #1, #2, #3) — ATTEMPT 1 BLOCKED | ☑ |
| 4b | Re-run ./setup.sh (fixed) + pytest (depends on #3b, #6) | ☑ |
| 5 | Update README (depends on #7) | ☑ |
| 6 | Replace deleted SE23 import with new-API equivalent (user-approved) | ☑ |
| 7 | Fix SGal3 vs matrix mismatches (3 source sites + 4 fixture sites + 1 import) — pytest gate | ☑ |

## feat/single-anchor-ukf-plan
### planning/setup-sh-submodules/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 23 | planning/setup-sh-submodules/work_plan.md | Task Plan: setup.sh, submodules, pyproject, README | open | ☐ |

| # | details | ✓ |
|---|---------|---|
| G | Give the ARP_1A_anchored_implementations repo a modern, reproducible environment setup (venv + 3 submodules) and a README consistent with the merged CAO implementation. | ☐ |
| 1 | Rename package dir to lowercase PEP 8 + fix 7 imports | ☑ |
| 2 | Add 3 submodules + recursive init | ☑ |
| 3 | Edit pyproject.toml (1 line) + create .python-version + setup.sh | ☑ |
| 3b | Fix setup.sh — `PYBIND11_FINDPYTHON=ON` + manifpy idempotency guard | ☑ |
| 4 | Run ./setup.sh end-to-end + pytest (depends on #1, #2, #3) — ATTEMPT 1 BLOCKED | ☑ |
| 4b | Re-run ./setup.sh (fixed) + pytest (depends on #3b, #6) | ☑ |
| 5 | Update README (depends on #7) | ☑ |
| 6 | Replace deleted SE23 import with new-API equivalent (user-approved) | ☑ |
| 7 | Fix SGal3 vs matrix mismatches (3 source sites + 4 fixture sites + 1 import) — pytest gate | ☑ |

# https://github.com/y2d2/ARP_IMU.git
## master
### planning/arp-imu-active-measurements/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 23 | planning/arp-imu-active-measurements/work_plan.md | Implementation Plan: ARP_IMU Active Measurements | open | ☐ |

| # | details | ✓ |
|---|---------|---|
| G | Implement the SGal3 active-measurements buffer, roll/pitch from buffer, and rewrite the analysis script | ☐ |
| 1 | Add active-measurements buffer infrastructure to ARP_IMU | ☐ |
| 2 | Implement `get_imu_measurments()` method | ☐ |
| 3 | Implement `get_uwb_range()` method | ☐ |
| 4 | Rewrite `get_roll_pitch()` method | ☐ |
| 5 | Rewrite `experiments/arp_imu_analysis.py` as lean driver | ☐ |

# https://github.com/y2d2/ARP_MPE.git
## mpe-rl-project
### planning/observation-tokenisation/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 23 | planning/observation-tokenisation/work_plan.md | Task Plan: Observation Tokenisation | open | ☐ |

| # | details | ✓ |
|---|---------|---|
| G | Set Transformer entity-token observation pipeline on the custom BaseAgent track, a working PPO rollout loop, and a full ablation on `simple_spread_v3`. | ☐ |
| 1 | wrapper step fix | ☑ |
| 2 | obs adapter | ☑ |
| 3 | set transformer | ☑ |
| 4 | entity agent | ☑ |
| 5 | rollout collector | ☑ |
| 6 | ppo training | ☑ |
| 7 | ablation | ☑ |

# https://github.com/y2d2/ARP_implementations.git
## main
### planning/repo-review-2026-11-17/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 23 | planning/repo-review-2026-11-17/work_plan.md | Work Plan: Repo review — verify findings, then fix | open | ☐ |

| # | details | ✓ |
|---|---------|---|
| G | Confirm the 2026-11-17 review findings with reproducible probes, then fix the confirmed ones. | ☐ |
| 2 | SGal3 loop indexing (B1, U1, M2) | ☑ |
| 3 | Baselines loop / NLS / 6DoF / check_validity (B2, B3, B6, B7, B9, M1) | ☑ |
| 4 | Math checks — WLS Jacobian, algebraic logger, QCQP c5, arccos heading (B4, B5, B8, M3) | ☑ |

# https://github.com/y2d2/ARP_roadmap.git
## feature/orbit-rob-kickoff-slides
### planning/esa-bt-gate0-slide/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 243 | planning/esa-bt-gate0-slide/work_plan.md | Work plan — ESA OSIP imec BT Gate 0 slide | open | ☐ |

| # | details | ✓ |
|---|---------|---|
| G | — | ☐ |
| 1 | fill bt slide | ☑ |

### planning/esa-no-open-source/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 244 | planning/esa-no-open-source/work_plan.md | Work plan — ESA OSIP: drop open-source commitment | open | ☐ |

| # | details | ✓ |
|---|---------|---|
| G | — | ☐ |
| 1 | remove open source | ☑ |

### planning/orbit-demo1-visual/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 245 | planning/orbit-demo1-visual/work_plan.md | Work plan — ORBIT Demonstrator 1, Scenario B visual | open | ☐ |

| # | details | ✓ |
|---|---------|---|
| G | — | ☐ |
| 1 | TikZ schematic of 2027 Scenario B, render PDF + PNG, visual check | ☑ |
| 2 | teaser illustration, robot B = Unitree G1 humanoid | ☑ |

### planning/orbit-dmp-unification/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 246 | planning/orbit-dmp-unification/work_plan.md | Work Plan: Unify ORBIT DMP Questionnaire Answers | open | ☐ |

| # | details | ✓ |
|---|---------|---|
| G | Merge the 5 partner responses in `projects/ORBIT/DMP Questionnaire ORBIT.xlsx` (Google Forms export) into a single, unified Markdown document that keeps per-research-group specifics and tracks every dataset. | ☐ |
| 1 | Create the unified DMP Markdown document | ☑ |

### planning/orbit-dmp/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 247 | planning/orbit-dmp/work_plan.md | Task Plan: ORBIT DMP v0 — consortium data management plan | open | ☐ |

| # | details | ✓ |
|---|---------|---|
| G | Build `projects/ORBIT/DMP/ORBIT_DMP_v0.md`, the table-first consortium DMP, in five sequential sub-agent tasks. | ☐ |
| 1 | Skeleton & front matter (no dependencies) | ☑ |
| 2 | Master table 1 (depends on #1) | ☑ |
| 3 | Supporting tables 2–6 (depends on #2) | ☑ |
| 4 | Minimal prose + Coera/IP text (depends on #3) | ☑ |
| 5 | QA pass (depends on #4) | ☑ |
| 6 | Coera removal + ethics commission (depends on #5; user-directed change 2026-11-10) | ☑ |
| 7 | brubotics-hamed label → VUB-IMS-confidential (depends on #6; user-directed change 2026-11-10) | ☑ |
| 8 | add IDLab-IWIN to consortium list (depends on #7; user-directed change 2026-11-10) | ☑ |
| 9 | IDLab-IWIN → IDLab-IWINE (depends on #8; verified externally 2026-11-16) | ☑ |
| 10 | Table 1 — drop Label & Storage & backup columns (depends on #9; user-directed 2026-11-16) | ☑ |
| 11 | EM entries → EM-IWINE (depends on #10; user-directed 2026-11-16) | ☑ |
| 12 | Dataset IDs in Table 1, cross-referenced in Tables 2–6 (depends on #11; user-approved 2026-11-16) | ☑ |
| 13 | §6 — drop IPTA sentence, use dataset IDs (depends on #12; user-directed 2026-11-16) | ☑ |
| 14 | Remove Miluv dataset, keep new robot localisation dataset B2 (depends on #13; user-directed 2026-11-16) | ☑ |
| 15 | Data IDs as first column in Tables 2–6 (depends on #14; user-directed 2026-11-16) | ☑ |
| 16 | Renumber B IDs, unify table inputs, full ID coverage (depends on #15; user-directed 2026-11-18) | ☑ |
| 17 | Funding scheme imec PROSPECT (depends on #16; user-confirmed 2026-11-18) | ☑ |
| 18 | Remove section 6 (depends on #17; user-directed 2026-11-18) | ☑ |
| 19 | Plain "Reused" in Table 1 (depends on #18; user-directed 2026-11-18) | ☑ |
| 20 | Move C5 to A8, renumber C6 → C5 (depends on #19; user-directed 2026-11-18) | ☑ |

### planning/orbit-email-lists-per-wp/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 248 | planning/orbit-email-lists-per-wp/work_plan.md | Work plan — ORBIT e-mail lists per WP | open | ☐ |

| # | details | ✓ |
|---|---------|---|
| G | Move the per-WP copy-paste e-mail lines in `projects/ORBIT/ORBIT_people_per_WP.md` from the separate "## E-mail lists" section into each WP section; keep one "All" line. | ☐ |
| 1 | relocate e-mail lists | ☑ |

### planning/orbit-people-update/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 249 | planning/orbit-people-update/work_plan.md | Work Plan: ORBIT people per WP — Oct 2026 refresh | open | ☐ |

| # | details | ✓ |
|---|---------|---|
| G | Update `projects/ORBIT/ORBIT_people_per_WP.md` with staffing changes since 13 Oct 2026. | ☐ |
| 1 | Rewrite file + commit | ☑ |

### planning/orbit-plenary-i-slides/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 250 | planning/orbit-plenary-i-slides/work_plan.md | Work plan — ORBIT Plenary I (28 Oct 2026): slides, deck, post-meeting outcomes | open | ☐ |

| # | details | ✓ |
|---|---------|---|
| G | — | ☐ |
| 9 | outcomes report | ☑ |
| 10 | cleaned deck | ☑ |

### planning/orbit-rob-kickoff-slides/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 251 | planning/orbit-rob-kickoff-slides/work_plan.md | Task Plan: ORBIT ROB kick-off presentation (drafts) | open | ☐ |

| # | details | ✓ |
|---|---------|---|
| G | Produce a 30-min ORBIT presentation for the ROB kick-off Advisory Board (25 Nov 2026, Ghent), starting with a storyboard draft. | ☐ |
| 1 | Storyboard (markdown) | ☑ |
| 2 | Integrate user edits into storyboard | ☑ |
| 3 | Build draft .pptx | ☑ |
| 4 | Picture-led storyboard v2 | ☑ |
| 5 | Picture-led draft .pptx | ☑ |
| 6 | Image-generator prompts | ☑ |
| 7 | TikZ illustration kit + text-free teaser + pilots P02/P09/P16 | ☑ |

### planning/unitree-vault-note/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 253 | planning/unitree-vault-note/work_plan.md | Task Plan: Unitree FARI acquisition vault note | open | ☐ |

| # | details | ✓ |
|---|---------|---|
| G | Persist a short, clean note in the ORBIT vault documenting the Unitree G1/Go2 configuration FARI put in the tender (PROC 1), with mail provenance tags. | ☐ |
| 1 | Create the vault note | ☑ |
| 2 | Commit + push the note (depends on #1) | ☑ |

### planning/orbit-rob-kickoff-workshop-notes/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 254 | planning/orbit-rob-kickoff-workshop-notes/work_plan.md | Work plan — ORBIT ROB kick-off workshop notes (Autonomous Navigation, group 2) | open | ☐ |

| # | details | ✓ |
|---|---------|---|
| G | Turn the 5 board photos + note-taker notes from the 25/11 ROB kick-off "Autonomous Navigation" table (deSter, Pfizer, DroneDivision, RBD Robotics, coera) into a Markdown summary mirroring `workshop orbit en fidex.docx` (spoken summary + board transcription per company), then commit/push the agreed scope. | ☐ |
| 1 | workshop md and commit | ☐ |

## main
### planning/esa-no-open-source/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 200 | planning/esa-no-open-source/work_plan.md | Work plan — ESA OSIP: drop open-source commitment | open | ☐ |

| # | details | ✓ |
|---|---------|---|
| G | — | ☐ |
| 1 | remove open source | ☑ |

### planning/orbit-demo1-visual/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 201 | planning/orbit-demo1-visual/work_plan.md | Work plan — ORBIT Demonstrator 1, Scenario B visual | open | ☐ |

| # | details | ✓ |
|---|---------|---|
| G | — | ☐ |
| 1 | TikZ schematic of 2027 Scenario B, render PDF + PNG, visual check | ☑ |
| 2 | teaser illustration, robot B = Unitree G1 humanoid | ☑ |

### planning/orbit-dmp-unification/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 202 | planning/orbit-dmp-unification/work_plan.md | Work Plan: Unify ORBIT DMP Questionnaire Answers | open | ☐ |

| # | details | ✓ |
|---|---------|---|
| G | Merge the 5 partner responses in `projects/ORBIT/DMP Questionnaire ORBIT.xlsx` (Google Forms export) into a single, unified Markdown document that keeps per-research-group specifics and tracks every dataset. | ☐ |
| 1 | Create the unified DMP Markdown document | ☑ |

### planning/orbit-dmp/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 203 | planning/orbit-dmp/work_plan.md | Task Plan: ORBIT DMP v0 — consortium data management plan | open | ☐ |

| # | details | ✓ |
|---|---------|---|
| G | Build `projects/ORBIT/DMP/ORBIT_DMP_v0.md`, the table-first consortium DMP, in five sequential sub-agent tasks. | ☐ |
| 1 | Skeleton & front matter (no dependencies) | ☑ |
| 2 | Master table 1 (depends on #1) | ☑ |
| 3 | Supporting tables 2–6 (depends on #2) | ☑ |
| 4 | Minimal prose + Coera/IP text (depends on #3) | ☑ |
| 5 | QA pass (depends on #4) | ☑ |
| 6 | Coera removal + ethics commission (depends on #5; user-directed change 2026-11-10) | ☑ |
| 7 | brubotics-hamed label → VUB-IMS-confidential (depends on #6; user-directed change 2026-11-10) | ☑ |
| 8 | add IDLab-IWIN to consortium list (depends on #7; user-directed change 2026-11-10) | ☑ |
| 9 | IDLab-IWIN → IDLab-IWINE (depends on #8; verified externally 2026-11-16) | ☑ |
| 10 | Table 1 — drop Label & Storage & backup columns (depends on #9; user-directed 2026-11-16) | ☑ |
| 11 | EM entries → EM-IWINE (depends on #10; user-directed 2026-11-16) | ☑ |
| 12 | Dataset IDs in Table 1, cross-referenced in Tables 2–6 (depends on #11; user-approved 2026-11-16) | ☑ |
| 13 | §6 — drop IPTA sentence, use dataset IDs (depends on #12; user-directed 2026-11-16) | ☑ |
| 14 | Remove Miluv dataset, keep new robot localisation dataset B2 (depends on #13; user-directed 2026-11-16) | ☑ |
| 15 | Data IDs as first column in Tables 2–6 (depends on #14; user-directed 2026-11-16) | ☑ |
| 16 | Renumber B IDs, unify table inputs, full ID coverage (depends on #15; user-directed 2026-11-18) | ☑ |
| 17 | Funding scheme imec PROSPECT (depends on #16; user-confirmed 2026-11-18) | ☑ |
| 18 | Remove section 6 (depends on #17; user-directed 2026-11-18) | ☑ |
| 19 | Plain "Reused" in Table 1 (depends on #18; user-directed 2026-11-18) | ☑ |
| 20 | Move C5 to A8, renumber C6 → C5 (depends on #19; user-directed 2026-11-18) | ☑ |

### planning/orbit-email-lists-per-wp/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 204 | planning/orbit-email-lists-per-wp/work_plan.md | Work plan — ORBIT e-mail lists per WP | open | ☐ |

| # | details | ✓ |
|---|---------|---|
| G | Move the per-WP copy-paste e-mail lines in `projects/ORBIT/ORBIT_people_per_WP.md` from the separate "## E-mail lists" section into each WP section; keep one "All" line. | ☐ |
| 1 | relocate e-mail lists | ☑ |

### planning/orbit-people-update/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 205 | planning/orbit-people-update/work_plan.md | Work Plan: ORBIT people per WP — Oct 2026 refresh | open | ☐ |

| # | details | ✓ |
|---|---------|---|
| G | Update `projects/ORBIT/ORBIT_people_per_WP.md` with staffing changes since 13 Oct 2026. | ☐ |
| 1 | Rewrite file + commit | ☑ |

### planning/unitree-vault-note/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 207 | planning/unitree-vault-note/work_plan.md | Task Plan: Unitree FARI acquisition vault note | open | ☐ |

| # | details | ✓ |
|---|---------|---|
| G | Persist a short, clean note in the ORBIT vault documenting the Unitree G1/Go2 configuration FARI put in the tender (PROC 1), with mail provenance tags. | ☐ |
| 1 | Create the vault note | ☑ |
| 2 | Commit + push the note (depends on #1) | ☑ |

### planning/esa-bt-gate0-slide/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 208 | planning/esa-bt-gate0-slide/work_plan.md | Work plan — ESA OSIP imec BT Gate 0 slide | open | ☐ |

| # | details | ✓ |
|---|---------|---|
| G | — | ☐ |
| 1 | fill bt slide | ☑ |

### planning/orbit-plenary-i-slides/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 209 | planning/orbit-plenary-i-slides/work_plan.md | Work plan — ORBIT Plenary I (28 Oct 2026): slides, deck, post-meeting outcomes | open | ☐ |

| # | details | ✓ |
|---|---------|---|
| G | — | ☐ |
| 9 | outcomes report | ☑ |
| 10 | cleaned deck | ☑ |

# https://github.com/y2d2/ARP_utility_code.git
## fix/code-review-findings
### planning/basic-usage-notebook/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 89 | planning/basic-usage-notebook/work_plan.md | Work Plan: Basic-usage Jupyter notebook | open | ☐ |

| # | details | ✓ |
|---|---------|---|
| G | Add a short, runnable Jupyter notebook demonstrating the library's core functionality, plus a dependency-free test that keeps it runnable. | ☐ |
| 1 | notebook + cell-exec test + README pointer | ☑ |

### planning/code-review-fixes/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 90 | planning/code-review-fixes/work_plan.md | Task Plan: Code-review findings — verify & fix | open | ☐ |

| # | details | ✓ |
|---|---------|---|
| G | Confirm the findings of the 2026-11-16 critical review by execution, then fix every confirmed High/Medium finding plus cheap Low fixes. | ☐ |
| 1 | Baseline test/lint run | ☑ |
| 2 | Probe scripts confirming review findings | ☑ |

### planning/python-3.12-upgrade/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 91 | planning/python-3.12-upgrade/work_plan.md | Task Plan: Move project from Python 3.11 to 3.12 | open | ☐ |

| # | details | ✓ |
|---|---------|---|
| G | Retarget the repo's interpreter from Python 3.11 to 3.12 and prove the build and gates still pass. | ☐ |
| 1 | Bump pins, relock, rebuild, verify | ☑ |

### planning/repo-cleanup/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 92 | planning/repo-cleanup/work_plan.md | Work Plan: Repo Cleanup (remove SGal3_filters, deprecated modules, stray files; README mermaid rewrite) | open | ☐ |

| # | details | ✓ |
|---|---------|---|
| G | Bring `arp_utility_code` to a single, honest state — only actively used code remains — with all dangling references updated, the suite strictly green, and a rewritten README carrying two Mermaid diagrams. | ☐ |
| 1 | Remove the SGal3_filters package (files: `src/arp_utility_code/SGal3_filters/`, `tests/test_SGal3_filters/`, `docs/filters.rst`, doc/README references, `filterpy` dependency) | ☑ |
| 2 | Remove deprecated/orphan UtilityCode modules + uwb_noise_filters (after Task 1 — shares `pyproject.toml`, `uv.lock`, `docs/*.rst`, `README.md`) | ☑ |
| 3 | Remove the stray root task report (parallel with Task 1 — no shared files) | ☑ |
| 4 | Rewrite the README with Mermaid overviews (after Task 2 — examples must run against the final package state) | ☑ |
| 5 | Verify all gates and finalize (after all — push + PR URL + draft description) | ☑ |

## main
### planning/basic-usage-notebook/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 89 | planning/basic-usage-notebook/work_plan.md | Work Plan: Basic-usage Jupyter notebook | open | ☐ |

| # | details | ✓ |
|---|---------|---|
| G | Add a short, runnable Jupyter notebook demonstrating the library's core functionality, plus a dependency-free test that keeps it runnable. | ☐ |
| 1 | notebook + cell-exec test + README pointer | ☑ |

### planning/code-review-fixes/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 90 | planning/code-review-fixes/work_plan.md | Task Plan: Code-review findings — verify & fix | open | ☐ |

| # | details | ✓ |
|---|---------|---|
| G | Confirm the findings of the 2026-11-16 critical review by execution, then fix every confirmed High/Medium finding plus cheap Low fixes. | ☐ |
| 1 | Baseline test/lint run | ☑ |
| 2 | Probe scripts confirming review findings | ☑ |

### planning/python-3.12-upgrade/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 91 | planning/python-3.12-upgrade/work_plan.md | Task Plan: Move project from Python 3.11 to 3.12 | open | ☐ |

| # | details | ✓ |
|---|---------|---|
| G | Retarget the repo's interpreter from Python 3.11 to 3.12 and prove the build and gates still pass. | ☐ |
| 1 | Bump pins, relock, rebuild, verify | ☑ |

### planning/repo-cleanup/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 92 | planning/repo-cleanup/work_plan.md | Work Plan: Repo Cleanup (remove SGal3_filters, deprecated modules, stray files; README mermaid rewrite) | open | ☐ |

| # | details | ✓ |
|---|---------|---|
| G | Bring `arp_utility_code` to a single, honest state — only actively used code remains — with all dangling references updated, the suite strictly green, and a rewritten README carrying two Mermaid diagrams. | ☐ |
| 1 | Remove the SGal3_filters package (files: `src/arp_utility_code/SGal3_filters/`, `tests/test_SGal3_filters/`, `docs/filters.rst`, doc/README references, `filterpy` dependency) | ☑ |
| 2 | Remove deprecated/orphan UtilityCode modules + uwb_noise_filters (after Task 1 — shares `pyproject.toml`, `uv.lock`, `docs/*.rst`, `README.md`) | ☑ |
| 3 | Remove the stray root task report (parallel with Task 1 — no shared files) | ☑ |
| 4 | Rewrite the README with Mermaid overviews (after Task 2 — examples must run against the final package state) | ☑ |
| 5 | Verify all gates and finalize (after all — push + PR URL + draft description) | ☑ |

# https://github.com/y2d2/PRP_ARP_M.git
## docs/readme-diagram-rework
### planning/arp-prp-data-import-verification/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 23 | planning/arp-prp-data-import-verification/work_plan.md | Task Plan: ARP_PRP data import verification | open | ☐ |

| # | details | ✓ |
|---|---------|---|
| G | Verify experimentally that the sensor data in `/workspace/data/ARP_PRP*/exp*` is importable by the data-loading harness of the `ARP_utility_code` module — TurtleBot wheel odometry, ESP IMU/UWB, and Husky LiDAR point cloud — and produce an evidence-backed PASS/FAIL report. | ☐ |
| 1 | Provision verification environment | ☑ |
| 2 | Probe bag-reader format support (depends on Task 1) | ☑ |
| 3 | Full import verification (depends on Task 2) | ☑ |
| 4 | (CONDITIONAL — only after user approval) Fix mcap import gap — **CANCELLED (2026-10-19)** | ☐ |

## docs/readme-mermaid-fix
### planning/arp-prp-data-import-verification/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 23 | planning/arp-prp-data-import-verification/work_plan.md | Task Plan: ARP_PRP data import verification | open | ☐ |

| # | details | ✓ |
|---|---------|---|
| G | Verify experimentally that the sensor data in `/workspace/data/ARP_PRP*/exp*` is importable by the data-loading harness of the `ARP_utility_code` module — TurtleBot wheel odometry, ESP IMU/UWB, and Husky LiDAR point cloud — and produce an evidence-backed PASS/FAIL report. | ☐ |
| 1 | Provision verification environment | ☑ |
| 2 | Probe bag-reader format support (depends on Task 1) | ☑ |
| 3 | Full import verification (depends on Task 2) | ☑ |
| 4 | (CONDITIONAL — only after user approval) Fix mcap import gap — **CANCELLED (2026-10-19)** | ☐ |

## docs/repo-consistency-review
### planning/arp-prp-data-import-verification/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 45 | planning/arp-prp-data-import-verification/work_plan.md | Task Plan: ARP_PRP data import verification | open | ☐ |

| # | details | ✓ |
|---|---------|---|
| G | Verify experimentally that the sensor data in `/workspace/data/ARP_PRP*/exp*` is importable by the data-loading harness of the `ARP_utility_code` module — TurtleBot wheel odometry, ESP IMU/UWB, and Husky LiDAR point cloud — and produce an evidence-backed PASS/FAIL report. | ☐ |
| 1 | Provision verification environment | ☑ |
| 2 | Probe bag-reader format support (depends on Task 1) | ☑ |
| 3 | Full import verification (depends on Task 2) | ☑ |
| 4 | (CONDITIONAL — only after user approval) Fix mcap import gap — **CANCELLED (2026-10-19)** | ☐ |

### planning/readme-mermaid-fix/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 46 | planning/readme-mermaid-fix/work_plan.md | Task Plan: Fix mindmap parse error in root README | open | ☐ |

| # | details | ✓ |
|---|---------|---|
| G | Repair the first (structure) mermaid diagram in `README.md`, which fails to render on GitHub with `Parse error on line 13 ... Expecting 'SPACELINE', 'NL', 'EOF', got 'NODE_ID'`. | ☐ |
| 1 | Rewrite the 17 two-token label lines in the first mermaid block | ☐ |

## feat/beam-flip-event-detection
### planning/arp-prp-data-import-verification/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 45 | planning/arp-prp-data-import-verification/work_plan.md | Task Plan: ARP_PRP data import verification | open | ☐ |

| # | details | ✓ |
|---|---------|---|
| G | Verify experimentally that the sensor data in `/workspace/data/ARP_PRP*/exp*` is importable by the data-loading harness of the `ARP_utility_code` module — TurtleBot wheel odometry, ESP IMU/UWB, and Husky LiDAR point cloud — and produce an evidence-backed PASS/FAIL report. | ☐ |
| 1 | Provision verification environment | ☑ |
| 2 | Probe bag-reader format support (depends on Task 1) | ☑ |
| 3 | Full import verification (depends on Task 2) | ☑ |
| 4 | (CONDITIONAL — only after user approval) Fix mcap import gap — **CANCELLED (2026-10-19)** | ☐ |

### planning/run-all-arp-prp-experiments/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 46 | planning/run-all-arp-prp-experiments/work_plan.md | Work Plan: Run-all ARP-PRP experiments (pilot = exp15) | open | ☐ |

| # | details | ✓ |
|---|---------|---|
| G | Decompose `run_all_arp_prp_experiments_plan.md` into self-contained sub-agent tasks; drive one pilot experiment (exp15) end-to-end producing metrics + true-vs-estimated trajectory PNG + 2D/3D GIFs. | ☐ |
| 1 | Variable-length event detection (NN pairing) | ☑ |
| 2 | Real-data calibration module | ☑ |
| 3 | Run-all driver (depends on #1, #2, #4) | ☑ |
| 4 | Figure + GIF renderer | ☑ |
| 5 | Pilot run + verification gate (depends on #3) | ☑ |
| 6 | Renderer 2× GIF size + 60° 3D camera (user request 2026-11-14) | ☑ |
| 7 | Launch full 21-experiment batch (user request 2026-11-14) | ☑ |

## feat/py312-submodule-bump
### planning/arp-prp-data-import-verification/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 45 | planning/arp-prp-data-import-verification/work_plan.md | Task Plan: ARP_PRP data import verification | open | ☐ |

| # | details | ✓ |
|---|---------|---|
| G | Verify experimentally that the sensor data in `/workspace/data/ARP_PRP*/exp*` is importable by the data-loading harness of the `ARP_utility_code` module — TurtleBot wheel odometry, ESP IMU/UWB, and Husky LiDAR point cloud — and produce an evidence-backed PASS/FAIL report. | ☐ |
| 1 | Provision verification environment | ☑ |
| 2 | Probe bag-reader format support (depends on Task 1) | ☑ |
| 3 | Full import verification (depends on Task 2) | ☑ |
| 4 | (CONDITIONAL — only after user approval) Fix mcap import gap — **CANCELLED (2026-10-19)** | ☐ |

### planning/run-all-arp-prp-experiments/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 46 | planning/run-all-arp-prp-experiments/work_plan.md | Work Plan: Run-all ARP-PRP experiments (pilot = exp15) | open | ☐ |

| # | details | ✓ |
|---|---------|---|
| G | Decompose `run_all_arp_prp_experiments_plan.md` into self-contained sub-agent tasks; drive one pilot experiment (exp15) end-to-end producing metrics + true-vs-estimated trajectory PNG + 2D/3D GIFs. | ☐ |
| 1 | Variable-length event detection (NN pairing) | ☑ |
| 2 | Real-data calibration module | ☑ |
| 3 | Run-all driver (depends on #1, #2, #4) | ☑ |
| 4 | Figure + GIF renderer | ☑ |
| 5 | Pilot run + verification gate (depends on #3) | ☑ |
| 6 | Renderer 2× GIF size + 60° 3D camera (user request 2026-11-14) | ☑ |
| 7 | Launch full 21-experiment batch (user request 2026-11-14) | ☑ |

## feat/run-all-arp-prp-experiments
### planning/arp-prp-data-import-verification/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 45 | planning/arp-prp-data-import-verification/work_plan.md | Task Plan: ARP_PRP data import verification | open | ☐ |

| # | details | ✓ |
|---|---------|---|
| G | Verify experimentally that the sensor data in `/workspace/data/ARP_PRP*/exp*` is importable by the data-loading harness of the `ARP_utility_code` module — TurtleBot wheel odometry, ESP IMU/UWB, and Husky LiDAR point cloud — and produce an evidence-backed PASS/FAIL report. | ☐ |
| 1 | Provision verification environment | ☑ |
| 2 | Probe bag-reader format support (depends on Task 1) | ☑ |
| 3 | Full import verification (depends on Task 2) | ☑ |
| 4 | (CONDITIONAL — only after user approval) Fix mcap import gap — **CANCELLED (2026-10-19)** | ☐ |

### planning/run-all-arp-prp-experiments/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 46 | planning/run-all-arp-prp-experiments/work_plan.md | Work Plan: Run-all ARP-PRP experiments (pilot = exp15) | open | ☐ |

| # | details | ✓ |
|---|---------|---|
| G | Decompose `run_all_arp_prp_experiments_plan.md` into self-contained sub-agent tasks; drive one pilot experiment (exp15) end-to-end producing metrics + true-vs-estimated trajectory PNG + 2D/3D GIFs. | ☐ |
| 1 | Variable-length event detection (NN pairing) | ☑ |
| 2 | Real-data calibration module | ☑ |
| 3 | Run-all driver (depends on #1, #2, #4) | ☑ |
| 4 | Figure + GIF renderer | ☑ |
| 5 | Pilot run + verification gate (depends on #3) | ☑ |
| 6 | Renderer 2× GIF size + 60° 3D camera (user request 2026-11-14) | ☑ |
| 7 | Launch full 21-experiment batch (user request 2026-11-14) | ☑ |

## main
### planning/arp-prp-data-import-verification/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 23 | planning/arp-prp-data-import-verification/work_plan.md | Task Plan: ARP_PRP data import verification | open | ☐ |

| # | details | ✓ |
|---|---------|---|
| G | Verify experimentally that the sensor data in `/workspace/data/ARP_PRP*/exp*` is importable by the data-loading harness of the `ARP_utility_code` module — TurtleBot wheel odometry, ESP IMU/UWB, and Husky LiDAR point cloud — and produce an evidence-backed PASS/FAIL report. | ☐ |
| 1 | Provision verification environment | ☑ |
| 2 | Probe bag-reader format support (depends on Task 1) | ☑ |
| 3 | Full import verification (depends on Task 2) | ☑ |
| 4 | (CONDITIONAL — only after user approval) Fix mcap import gap — **CANCELLED (2026-10-19)** | ☐ |

# https://github.com/y2d2/agentic_scripts.git
## feature/mail-guardrail-mbsync-exclusion
### planning/mail-keeper-model-fix/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 89 | planning/mail-keeper-model-fix/work_plan.md | Work Plan: mail-keeper model-ref fix + error-text logging | open | ☐ |

| # | details | ✓ |
|---|---------|---|
| G | Restore the broken mail-keeper agent dispatch (dead provider ID in the runner's `--model`) and make workflow error text visible in run logs so the next config drift is diagnosable. | ☐ |
| 1 | Fix model reference + sync references + log workflow error text | ☑ |

### planning/mail-keeper-pruning/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 90 | planning/mail-keeper-pruning/work_plan.md | Task Plan: mail-keeper — runner-owned pruning of checked daily entries | open | ☐ |

| # | details | ✓ |
|---|---------|---|
| G | Fix the mail-keeper workflow so checked (`- [x]`) day-file entries are pruned and emptied day-files deleted on **every** scheduled run — including runs with no new mail — instead of only inside the (sometimes hallucinating) LLM agent step. | ☐ |
| 1 | Deterministic prune module + unit tests | ☐ |
| 2 | Runner hook in MailKeeper + integration tests (depends on #1) | ☐ |
| 3 | Skill doc — remove agent-side pruning (parallel with #1) | ☐ |
| 4 | Forced backlog cleanup + end-to-end verification (depends on #2) | ☐ |

### planning/smoke-test-mail-isolation/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 91 | planning/smoke-test-mail-isolation/work_plan.md | Work Plan: Hermetic MAIL_* env isolation in smoke tests | open | ☐ |

| # | details | ✓ |
|---|---------|---|
| G | Make the smoke-test mail-env isolation live in the autouse fixture (as documented) so no in-process `run()` in the smoke suite can reach the real notmuch index and dispatch a live agent. | ☐ |
| 1 | Move MAIL_* isolation into the autouse fixtures + pin it in the buggy test | ☑ |

### planning/workflows-mail-keeper/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 92 | planning/workflows-mail-keeper/work_plan.md | Work Plan: agentic_scripts — Mail-Keeper Workflow | open | ☐ |

| # | details | ✓ |
|---|---------|---|
| G | Orchestration work plan for `planning/workflows-mail-keeper/workflows-mail-keeper_plan.md` — ship the `mail-search` CLI over the maintained notmuch index, the mail-keeper workflow module (freshness canary, backfill-aware new-mail detection, manifest, batched agent invocation, processed log, guardrail verification), the real `email-routes.md`, and the hermetic smoke proving the end-to-end acceptance criteria with a fake agent. | ☐ |
| 1 | `mail-search` CLI + index-freshness canary | ☑ |
| 2 | Real `email-routes.md` | ☑ |
| 3 | Mail-keeper workflow module (core) | ☑ |
| 4 | Smoke test, README, env | ☑ |
| 5 | Backfill redesign — newest-first with 1-year floor | ☑ |
| 5b | Batch cap, cross-folder new-first, true per-folder frontier | ☐ |
| 5c | Base reader decode fix (acceptance blocker) | ☐ |

## feature/opencode-v2-run
### planning/mail-keeper-model-fix/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 89 | planning/mail-keeper-model-fix/work_plan.md | Work Plan: mail-keeper model-ref fix + error-text logging | open | ☐ |

| # | details | ✓ |
|---|---------|---|
| G | Restore the broken mail-keeper agent dispatch (dead provider ID in the runner's `--model`) and make workflow error text visible in run logs so the next config drift is diagnosable. | ☐ |
| 1 | Fix model reference + sync references + log workflow error text | ☑ |

### planning/mail-keeper-pruning/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 90 | planning/mail-keeper-pruning/work_plan.md | Task Plan: mail-keeper — runner-owned pruning of checked daily entries | open | ☐ |

| # | details | ✓ |
|---|---------|---|
| G | Fix the mail-keeper workflow so checked (`- [x]`) day-file entries are pruned and emptied day-files deleted on **every** scheduled run — including runs with no new mail — instead of only inside the (sometimes hallucinating) LLM agent step. | ☐ |
| 1 | Deterministic prune module + unit tests | ☐ |
| 2 | Runner hook in MailKeeper + integration tests (depends on #1) | ☐ |
| 3 | Skill doc — remove agent-side pruning (parallel with #1) | ☐ |
| 4 | Forced backlog cleanup + end-to-end verification (depends on #2) | ☐ |

### planning/smoke-test-mail-isolation/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 91 | planning/smoke-test-mail-isolation/work_plan.md | Work Plan: Hermetic MAIL_* env isolation in smoke tests | open | ☐ |

| # | details | ✓ |
|---|---------|---|
| G | Make the smoke-test mail-env isolation live in the autouse fixture (as documented) so no in-process `run()` in the smoke suite can reach the real notmuch index and dispatch a live agent. | ☐ |
| 1 | Move MAIL_* isolation into the autouse fixtures + pin it in the buggy test | ☑ |

### planning/workflows-mail-keeper/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 92 | planning/workflows-mail-keeper/work_plan.md | Work Plan: agentic_scripts — Mail-Keeper Workflow | open | ☐ |

| # | details | ✓ |
|---|---------|---|
| G | Orchestration work plan for `planning/workflows-mail-keeper/workflows-mail-keeper_plan.md` — ship the `mail-search` CLI over the maintained notmuch index, the mail-keeper workflow module (freshness canary, backfill-aware new-mail detection, manifest, batched agent invocation, processed log, guardrail verification), the real `email-routes.md`, and the hermetic smoke proving the end-to-end acceptance criteria with a fake agent. | ☐ |
| 1 | `mail-search` CLI + index-freshness canary | ☑ |
| 2 | Real `email-routes.md` | ☑ |
| 3 | Mail-keeper workflow module (core) | ☑ |
| 4 | Smoke test, README, env | ☑ |
| 5 | Backfill redesign — newest-first with 1-year floor | ☑ |
| 5b | Batch cap, cross-folder new-first, true per-folder frontier | ☐ |
| 5c | Base reader decode fix (acceptance blocker) | ☐ |

## feature/roadmap-dev-workflow
### planning/mail-keeper-model-fix/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 89 | planning/mail-keeper-model-fix/work_plan.md | Work Plan: mail-keeper model-ref fix + error-text logging | open | ☐ |

| # | details | ✓ |
|---|---------|---|
| G | Restore the broken mail-keeper agent dispatch (dead provider ID in the runner's `--model`) and make workflow error text visible in run logs so the next config drift is diagnosable. | ☐ |
| 1 | Fix model reference + sync references + log workflow error text | ☑ |

### planning/mail-keeper-pruning/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 90 | planning/mail-keeper-pruning/work_plan.md | Task Plan: mail-keeper — runner-owned pruning of checked daily entries | open | ☐ |

| # | details | ✓ |
|---|---------|---|
| G | Fix the mail-keeper workflow so checked (`- [x]`) day-file entries are pruned and emptied day-files deleted on **every** scheduled run — including runs with no new mail — instead of only inside the (sometimes hallucinating) LLM agent step. | ☐ |
| 1 | Deterministic prune module + unit tests | ☐ |
| 2 | Runner hook in MailKeeper + integration tests (depends on #1) | ☐ |
| 3 | Skill doc — remove agent-side pruning (parallel with #1) | ☐ |
| 4 | Forced backlog cleanup + end-to-end verification (depends on #2) | ☐ |

### planning/smoke-test-mail-isolation/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 91 | planning/smoke-test-mail-isolation/work_plan.md | Work Plan: Hermetic MAIL_* env isolation in smoke tests | open | ☐ |

| # | details | ✓ |
|---|---------|---|
| G | Make the smoke-test mail-env isolation live in the autouse fixture (as documented) so no in-process `run()` in the smoke suite can reach the real notmuch index and dispatch a live agent. | ☐ |
| 1 | Move MAIL_* isolation into the autouse fixtures + pin it in the buggy test | ☑ |

### planning/workflows-mail-keeper/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 92 | planning/workflows-mail-keeper/work_plan.md | Work Plan: agentic_scripts — Mail-Keeper Workflow | open | ☐ |

| # | details | ✓ |
|---|---------|---|
| G | Orchestration work plan for `planning/workflows-mail-keeper/workflows-mail-keeper_plan.md` — ship the `mail-search` CLI over the maintained notmuch index, the mail-keeper workflow module (freshness canary, backfill-aware new-mail detection, manifest, batched agent invocation, processed log, guardrail verification), the real `email-routes.md`, and the hermetic smoke proving the end-to-end acceptance criteria with a fake agent. | ☐ |
| 1 | `mail-search` CLI + index-freshness canary | ☑ |
| 2 | Real `email-routes.md` | ☑ |
| 3 | Mail-keeper workflow module (core) | ☑ |
| 4 | Smoke test, README, env | ☑ |
| 5 | Backfill redesign — newest-first with 1-year floor | ☑ |
| 5b | Batch cap, cross-folder new-first, true per-folder frontier | ☐ |
| 5c | Base reader decode fix (acceptance blocker) | ☐ |

## plan/agentic-workflows
### planning/mail-keeper-model-fix/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 89 | planning/mail-keeper-model-fix/work_plan.md | Work Plan: mail-keeper model-ref fix + error-text logging | open | ☐ |

| # | details | ✓ |
|---|---------|---|
| G | Restore the broken mail-keeper agent dispatch (dead provider ID in the runner's `--model`) and make workflow error text visible in run logs so the next config drift is diagnosable. | ☐ |
| 1 | Fix model reference + sync references + log workflow error text | ☑ |

### planning/mail-keeper-pruning/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 90 | planning/mail-keeper-pruning/work_plan.md | Task Plan: mail-keeper — runner-owned pruning of checked daily entries | open | ☐ |

| # | details | ✓ |
|---|---------|---|
| G | Fix the mail-keeper workflow so checked (`- [x]`) day-file entries are pruned and emptied day-files deleted on **every** scheduled run — including runs with no new mail — instead of only inside the (sometimes hallucinating) LLM agent step. | ☐ |
| 1 | Deterministic prune module + unit tests | ☐ |
| 2 | Runner hook in MailKeeper + integration tests (depends on #1) | ☐ |
| 3 | Skill doc — remove agent-side pruning (parallel with #1) | ☐ |
| 4 | Forced backlog cleanup + end-to-end verification (depends on #2) | ☐ |

### planning/smoke-test-mail-isolation/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 91 | planning/smoke-test-mail-isolation/work_plan.md | Work Plan: Hermetic MAIL_* env isolation in smoke tests | open | ☐ |

| # | details | ✓ |
|---|---------|---|
| G | Make the smoke-test mail-env isolation live in the autouse fixture (as documented) so no in-process `run()` in the smoke suite can reach the real notmuch index and dispatch a live agent. | ☐ |
| 1 | Move MAIL_* isolation into the autouse fixtures + pin it in the buggy test | ☑ |

### planning/workflows-mail-keeper/work_plan.md
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 92 | planning/workflows-mail-keeper/work_plan.md | Work Plan: agentic_scripts — Mail-Keeper Workflow | open | ☐ |

| # | details | ✓ |
|---|---------|---|
| G | Orchestration work plan for `planning/workflows-mail-keeper/workflows-mail-keeper_plan.md` — ship the `mail-search` CLI over the maintained notmuch index, the mail-keeper workflow module (freshness canary, backfill-aware new-mail detection, manifest, batched agent invocation, processed log, guardrail verification), the real `email-routes.md`, and the hermetic smoke proving the end-to-end acceptance criteria with a fake agent. | ☐ |
| 1 | `mail-search` CLI + index-freshness canary | ☑ |
| 2 | Real `email-routes.md` | ☑ |
| 3 | Mail-keeper workflow module (core) | ☑ |
| 4 | Smoke test, README, env | ☑ |
| 5 | Backfill redesign — newest-first with 1-year floor | ☑ |
| 5b | Batch cap, cross-folder new-first, true per-folder frontier | ☐ |
| 5c | Base reader decode fix (acceptance blocker) | ☐ |
