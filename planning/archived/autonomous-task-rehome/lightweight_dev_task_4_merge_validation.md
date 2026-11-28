# lightweight-dev Output — Task: Merge to main + live state snapshot + forced-run validation (pre-gate evidence)

**Task:** #4    **Session:** lightweight-dev (autonomous-task-rehome)    **Date:** 2026-11-28

## Summary

Landed the re-homed engine on overview `main`, migrated the live plan-tracking state, and produced the
A/B/C(c) forced-run evidence pack — **and caught a latent engine bug that acceptance #6 exposed**,
root-caused it, fixed it with a regression test, and re-validated to full parity (Runs B2/C2).
Crontab never touched; old engine stayed authoritative and live throughout.

1. **Merge (step 1).** Fetched overview: `origin/main` had **not** advanced past `e99307f` (no listing
   commits since PR #1 — no engine fires). `git merge --ff-only feature/rehome-final` → clean fast-forward
   `e99307f..56887a2`, pushed. (12 files, +926/−171; branch tip `56887a2` = Task 3's tip.)
2. **Setup (step 2).** `bash scripts/setup.sh --skip-timer` exit 0: venv synced, 2 agents present,
   10/10 SSH preflights green, `timer install skipped`. Crontab byte-identical (md5 §Evidence).
3. **State snapshot (step 3).** Quiet moment verified first (`ps`: no engine processes; last cron run
   15:30:01–15:30:37 ended 24 min earlier). Copied live `roadmap-dev.json` over the overview's
   27-Nov-dormant one (was 59 723 B, Nov 26 11:01). Both files byte-identical (SHA §Evidence, `cmp` clean).
   Not staged — `state/` is gitignored runtime data. 116 entries, all `state=open`, none `pending`/`running`.
4. **Run A — baseline, OLD engine (step 4).** Verified the documented force path in `cli.py`/`scheduler.py`
   (`run` subcommand carries `--force` + `--only NAME`): `uv run agentic-scripts run --force --only roadmap-dev`.
   Exit 0, `roadmap-dev=ok(60 items, 12 actions, 0 errors)`, drain ran with the live session probe closed
   (`gate closed — no new starts`, `startable=0`) → no job dispatches. State diff vs before: **0 added /
   0 removed / 0 modified** (file stayed byte-identical `bb30e379…`). Mirror `plans.md` hash unchanged
   (`004e30a7…`, byte-stable re-render). **No commit appeared in agentic_scripts.**
5. **Run B — new engine (step 5).** `uv run autonomous-task run --force` (flag verified in `runner.py`;
   `--skip-timer` meant no overview cron existed). Exit 0, 0 ERROR lines, `WORKFLOW roadmap-dev status=ok
   items_found=60 actions=13 errors=0`, listing pushed to overview `main` (commit `b0c1a03`), mirror written
   to repo root. **BUT the listing rendered only 2 of the 60 plans.** Run C (pre-fix stability) then proved
   the 2-row render was byte-stable (no churn) — self-consistent, structurally wrong.
6. **Root cause (acceptance #6 failure).** `reconcile()`'s final row assembly (`roadmap_dev.py` L1378 ff):
   rule 1 ("scanned **+ in state** → the row exists **(or is created)**") stores created rows only in
   `updated_by_key`, but the assembly emits `updated_by_key` entries **only for keys that had a pre-existing
   listing row**. So a scanned plan whose state entry exists while its listing row does not — exactly the
   migrated-state scenario (116 seeded entries vs a 2-row listing) — had its created row silently dropped.
   Verified with a pure-function repro: scan 3 + state 3 + listing 0 → **0 rows out, no action logged**
   (rule 2 discovery path with state empty → 3 rows). Latent in the LIVE agentic engine too (invisible there
   only because all 60 scanned plans already have listing rows). No test in the ported suite covered it.
7. **Fix + re-verification.** Branch `fix/reconcile-created-row-emit` in overview: created rule-1 rows are
   now registered in the section bookkeeping (running-max priorities) and emitted via the scan-only stream
   (+61/−1 across engine + one new regression test `test_reconcile_created_missing_row_for_in_state_plan`).
   Full suite **97/97** (96+1), ruff clean. Pushed; merged to `main` (`dc51d41`, merge `992774d` — see
   Deviations 2). **Run B2** (post-fix forced run): `ok(60 items, 13 actions, 0 errors)`, listing commit
   `c61f873` re-rendering all **60** plans, mirror == pushed bytes (`bb042ea8…`). **Run C2** (stability):
   `ok(60 items, 12 actions, 0 errors)`, **no new commit** (`origin/main` still `c61f873`), mirror
   byte-identical, state unchanged. **A-listing ≡ B2-listing: 60 identities each, symmetric difference
   EMPTY** (§Parity for full lists + field-level comparison).
8. **Cron guard (whole task).** `crontab -l | md5sum` identical at start and end (§Evidence); the
   `# autonomous-task` entry was NOT installed (stays a Task 6 action). Natural cron fires kept running
   the old engine (16:00, 16:30) — both recorded as interleaving notes (§Interleaving), nothing aborted.

## Files

| File | Repo | Action | Why |
|---|---|---|---|
| `src/autonomous_task/workflows/roadmap_dev.py` | overview | modify | Fix: emit rule-1 **created** rows in `reconcile()` assembly + section-bookkeeping (created-row running-max priority) |
| `tests/test_roadmap_dev.py` | overview | modify | Regression test `test_reconcile_creates_missing_row_for_in_state_plan` (created row: cells/priority/no-log, max+1 in live section, idempotent re-render) |
| `state/roadmap-dev.json` | overview | overwrite (runtime, NOT committed) | Live state migrated from agentic_scripts per plan step 3 (SHA-matched copy, `state/` gitignored) |
| `plans.md` (root mirror) | overview | engine-written | By Runs B/B2/C2 (`local_listing` mirror; engine-owned, never hand-edited, never committed from checkout) |
| `planning/autonomous-task-rehome/lightweight_dev_task_4_merge_validation.md` | agentic_scripts | create | This result report (uncommitted — Task 5 owns the provenance commit; NO other agentic_scripts file touched, NO commits there) |

Overview commits (this task): `56887a2` (=ff merge of `feature/rehome-final` onto `main`), `dc51d41`
fix (message: `OC: Fix reconcile dropping rule-1 created rows (state-migrated plans never re-listed)`),
merge `992774d`; engine listing commits `b0c1a03` (Run B) and `c61f873` (Run B2). All pushed.
Staged via explicit paths only.

## Build / Tests

- `bash scripts/setup.sh --skip-timer`: **PASS** — exit 0, all preflights green, timer skipped
- State snapshot `cmp`: **PASS** — byte-identical copies
- Run A (`agentic-scripts run --force --only roadmap-dev`): **PASS** — exit 0, 0 ERROR, ok(60/12/0)
- Run B (`autonomous-task run --force`, pre-fix): **PASS (mechanics)** — exit 0, 0 ERROR, ok(60/13/0); **content defect found** (2-row listing → fixed)
- Run C (pre-fix stability): **PASS** — exit 0, 0 ERROR, ok(60/12/0), zero churn, zero state add
- Bug repro (pure `reconcile`, pre-fix): **CONFIRMED** — in-state plans, no rows: 0 out / 0 logs
- Fix regression test: **PASS** — added, passing
- `uv run pytest tests/ -q` (post-fix full suite): **PASS** — **97 passed** (38.06 s), exit 0
- `uv run ruff check src tests`: **PASS** · `python -m compileall -q src`: **PASS**
- Run B2 (post-fix forced): **PASS** — exit 0, 0 ERROR, ok(60/13/0), full 60-plan listing pushed, `startable=0` (no dispatches)
- Run C2 (post-fix stability): **PASS** — exit 0, 0 ERROR, ok(60/12/0), byte-identical mirror, no new commit
- Mirror hygiene: **PASS** — test suite never touched the repo `plans.md`; only engine runs did (as designed)

## Acceptance Verification

| # | Criterion (verbatim) | Result | Notes |
|---|---|---|---|
| 1. | Merge — overview `main` contains the re-homed code (`git log main -1` shows merge/ff of `feature/rehome-final`) | **PASS** | `git merge --ff-only feature/rehome-final` → `Updating e99307f..56887a2`, pushed. `main` contains all re-homed code. (`main -1` today is engine listing commit `c61f873` — Runs B2/below legitimately advanced it after the merge; `git log main` shows the ff of `feature/rehome-final` plus the additive fix/listing commits.) |
| 2. | Cron guard — `crontab -l` md5 identical before/after the task (NO new entry yet) | **PASS** | Before **and** after: `cfb0988abb2ccee6dc0a3a628e485caf`. Only the pre-existing `# agentic-scripts */30` line; no `# autonomous-task` entry installed. |
| 3. | State — SHA-256 of both `roadmap-dev.json` files equal at snapshot time | **PASS** | Both: `bb30e379ff9dc27680bc2468dc0db7d39fb6579cf2361f0bd12ab5acf82aeb16` (+ `cmp` exit 0) at 15:54 UTC, quiet moment verified via `ps` (no engine process in flight). |
| 4. | Run B — exit 0, 0 ERROR lines, `WORKFLOW roadmap-dev status=ok`, listing push to overview `main` present (or clean no-op) | **PASS** | Exit 0; `ERROR lines: 0`; `WORKFLOW roadmap-dev status=ok items_found=60 actions=13 errors=0`; listing push present → commit `b0c1a03` on `main`. Footnote: B's rendered listing was content-truncated (2/60 rows) — see #6 and the fix. |
| 5. | Run C — second render byte-identical (no listing churn commit, no state add) | **PASS** | Pre-fix C (16:01): mirror `8a2c993c…` byte-identical to B, `origin/main` unchanged (`b0c1a03`), state unchanged. Post-fix B2→C2 re-proved it: mirror `bb042ea8…` identical, `origin/main` stayed `c61f873` (no churn commit), state unchanged (`bb30e379`). |
| 6. | Listing parity — A-listing and B-listing contain the same set of plan identities (report both lists) | **FAIL→FIXED→PASS** | As shipped: A=60 identities vs B=2 → **FAIL**. Root cause: latent `reconcile()` row-assembly bug (Summary §6). Fixed in overview (`dc51d41`, +regression test, 97/97 green), re-validated by Runs B2/C2: **A-listing 60 ≡ B2-listing 60, identical sorted lists, symmetric difference EMPTY**. Field-level: every row's approval/title/state/remove cells equal and every per-plan checklist byte-equal A vs B2; only section ORDER + numeric priority re-stamp differ (both benign — §Parity). |
| 7. | agentic untouched — no new commits in agentic_scripts from this task | **PASS** | `feature/roadmap-dev-workflow` == local HEAD == `745e6a9f2523c30fea504d0d0b1711df1ce80f3f` before/after. `origin/main` == `845c13971c220ec024df8ffdfcb4a192de75f123` before (after a fresh fetch) and after — that commit is natural **13:00:36 UTC cron** activity (`run 20261128T130001Z`), ~2.5 h before this task began. Run A pushed/committed nothing; the 16:00/16:30 natural fires no-op'd. My only writes there: this result file (untracked, per dispatch). |

## Evidence (verbatim)

**Crontab md5 (task start 15:41 → task end 16:31):**
```
cfb0988abb2ccee6dc0a3a628e485caf   (before)
cfb0988abb2ccee6dc0a3a628e485caf   (after)
```

**Git tips before → after:**

| Repo / ref | Before task | After task |
|---|---|---|
| overview `main` (local + origin) | `e99307f` | `56887a2` (ff merge) → `b0c1a03` (Run B listing) → `dc51d41`+`992774d` (fix+merge) → **origin/main `c61f873`** (Run B2 listing). Local `main` HEAD = `992774d` (one engine listing commit behind origin — engine-owned churn, not pulled by design; mirrors agentic's own stale-local-`main` pattern) |
| overview `feature/rehome-final` | `56887a2` | `56887a2` (untouched; merged) |
| overview `fix/reconcile-created-row-emit` | — | `dc51d41` (new, pushed, merged) |
| agentic_scripts HEAD + `feature/roadmap-dev-workflow` | `745e6a9` | `745e6a9` |
| agentic_scripts `origin/main` | `845c139` (fresh fetch; pre-existing 13:00 cron commit — first local read `29e2…`/`29e62bf` was a stale remote-tracking ref, corrected by the post-A fetch) | `845c139` (unchanged) |

**State snapshot + SHAs:** agentic live == overview (copied) == `bb30e379ff9dc27680bc2468dc0db7d39fb6579cf2361f0bd12ab5acf82aeb16`; 116 entries (all `open`).
State was still exactly `bb30e379…` at task end in BOTH repos: Runs A, B, C, B2, C2 and the 16:00/16:30 natural cron fires all left it byte-identical (116 → 116; **0 added / 0 removed / 0 modified** across every diff).

**Run-log final lines (verbatim, all five):**
```
A  (agentic 20261128T155455Z, forced+only):
2026-11-28T15:55:32Z INFO [agentic_scripts.roadmap-dev] roadmap-dev: drain start slots=1 startable=0
2026-11-28T15:55:32Z INFO [agentic_scripts.roadmap-dev] roadmap-dev: gate closed — no new starts (drain ends)
2026-11-28T15:55:32Z INFO [agentic_scripts] WORKFLOW roadmap-dev status=ok items_found=60 actions=12 errors=0
2026-11-28T15:55:32Z INFO [agentic_scripts] RUN END gate=forced workflows=1 errors=0 duration=37.5s

B  (overview 20261128T155906Z, pre-fix):
2026-11-28T15:59:45Z INFO [autonomous_task] roadmap-dev: listing mirrored to /workspace/Python/autonomous_task_overview/plans.md
2026-11-28T15:59:47Z INFO [autonomous_task] roadmap-dev: drain start slots=1 startable=0
2026-11-28T15:59:47Z INFO [autonomous_task] roadmap-dev: gate closed — no new starts (drain ends)
2026-11-28T15:59:47Z INFO [autonomous_task] WORKFLOW roadmap-dev status=ok items_found=60 actions=13 errors=0

C  (overview 20261128T160136Z, pre-fix stability):
2026-11-28T16:02:14Z INFO [autonomous_task] roadmap-dev: drain start slots=1 startable=0
2026-11-28T16:02:14Z INFO [autonomous_task] roadmap-dev: gate closed — no new starts (drain ends)
2026-11-28T16:02:14Z INFO [autonomous_task] WORKFLOW roadmap-dev status=ok items_found=60 actions=12 errors=0

B2 (overview 20261128T162755Z, post-fix):
2026-11-28T16:28:34Z INFO [autonomous_task] roadmap-dev: listing mirrored to /workspace/Python/autonomous_task_overview/plans.md
2026-11-28T16:28:35Z INFO [autonomous_task] roadmap-dev: drain start slots=1 startable=0
2026-11-28T16:28:35Z INFO [autonomous_task] roadmap-dev: gate closed — no new starts (drain ends)
2026-11-28T16:28:35Z INFO [autonomous_task] WORKFLOW roadmap-dev status=ok items_found=60 actions=13 errors=0

C2 (overview 20261128T162946Z, post-fix stability):
2026-11-28T16:30:24Z INFO [autonomous_task] roadmap-dev: drain start slots=1 startable=0
2026-11-28T16:30:24Z INFO [autonomous_task] roadmap-dev: gate closed — no new starts (drain ends)
2026-11-28T16:30:24Z INFO [autonomous_task] WORKFLOW roadmap-dev status=ok items_found=60 actions=12 errors=0
```
ERROR lines: 0 in all five logs (and 0 in the 16:00/16:30 natural cron logs). No job dispatched by any run.

**Listing render hashes:** A mirror (== agentic `origin/main:plans.md`) `004e30a7…` (60 sections, 790 lines);
B/pre-fix pushed+mirror `8a2c993c…` (2 sections, 27 lines); B2 pushed == C2 mirror `bb042ea8…`
(60 sections, 790 lines). A↔B2: 316 diff lines = section order + priority re-stamp ONLY (§Parity).

### Listing identity lists (identity = `repo_url|branch|plan_path`)

**A-listing — old engine, post-Run A (60 identities):**
```
 1. https://github.com/y2d2/ARP_1A_anchored_implementations.git|feat/setup-sh-submodules|planning/setup-sh-submodules/work_plan.md
 2. https://github.com/y2d2/ARP_1A_anchored_implementations.git|feat/single-anchor-ukf-plan|planning/setup-sh-submodules/work_plan.md
 3. https://github.com/y2d2/ARP_IMU.git|master|planning/arp-imu-active-measurements/work_plan.md
 4. https://github.com/y2d2/ARP_MPE.git|mpe-rl-project|planning/observation-tokenisation/work_plan.md
 5. https://github.com/y2d2/ARP_implementations.git|main|planning/repo-review-2026-11-17/work_plan.md
 6. https://github.com/y2d2/ARP_roadmap.git|feature/orbit-rob-kickoff-slides|planning/esa-bt-gate0-slide/work_plan.md
 7. https://github.com/y2d2/ARP_roadmap.git|feature/orbit-rob-kickoff-slides|planning/esa-no-open-source/work_plan.md
 8. https://github.com/y2d2/ARP_roadmap.git|feature/orbit-rob-kickoff-slides|planning/orbit-demo1-visual/work_plan.md
 9. https://github.com/y2d2/ARP_roadmap.git|feature/orbit-rob-kickoff-slides|planning/orbit-dmp-unification/work_plan.md
10. https://github.com/y2d2/ARP_roadmap.git|feature/orbit-rob-kickoff-slides|planning/orbit-dmp/work_plan.md
11. https://github.com/y2d2/ARP_roadmap.git|feature/orbit-rob-kickoff-slides|planning/orbit-email-lists-per-wp/work_plan.md
12. https://github.com/y2d2/ARP_roadmap.git|feature/orbit-rob-kickoff-slides|planning/orbit-people-update/work_plan.md
13. https://github.com/y2d2/ARP_roadmap.git|feature/orbit-rob-kickoff-slides|planning/orbit-plenary-i-slides/work_plan.md
14. https://github.com/y2d2/ARP_roadmap.git|feature/orbit-rob-kickoff-slides|planning/orbit-rob-kickoff-slides/work_plan.md
15. https://github.com/y2d2/ARP_roadmap.git|feature/orbit-rob-kickoff-slides|planning/orbit-rob-kickoff-workshop-notes/work_plan.md
16. https://github.com/y2d2/ARP_roadmap.git|feature/orbit-rob-kickoff-slides|planning/unitree-vault-note/work_plan.md
17. https://github.com/y2d2/ARP_roadmap.git|main|planning/esa-bt-gate0-slide/work_plan.md
18. https://github.com/y2d2/ARP_roadmap.git|main|planning/esa-no-open-source/work_plan.md
19. https://github.com/y2d2/ARP_roadmap.git|main|planning/orbit-demo1-visual/work_plan.md
20. https://github.com/y2d2/ARP_roadmap.git|main|planning/orbit-dmp-unification/work_plan.md
21. https://github.com/y2d2/ARP_roadmap.git|main|planning/orbit-dmp/work_plan.md
22. https://github.com/y2d2/ARP_roadmap.git|main|planning/orbit-email-lists-per-wp/work_plan.md
23. https://github.com/y2d2/ARP_roadmap.git|main|planning/orbit-people-update/work_plan.md
24. https://github.com/y2d2/ARP_roadmap.git|main|planning/orbit-plenary-i-slides/work_plan.md
25. https://github.com/y2d2/ARP_roadmap.git|main|planning/unitree-vault-note/work_plan.md
26. https://github.com/y2d2/ARP_utility_code.git|fix/code-review-findings|planning/basic-usage-notebook/work_plan.md
27. https://github.com/y2d2/ARP_utility_code.git|fix/code-review-findings|planning/code-review-fixes/work_plan.md
28. https://github.com/y2d2/ARP_utility_code.git|fix/code-review-findings|planning/python-3.12-upgrade/work_plan.md
29. https://github.com/y2d2/ARP_utility_code.git|fix/code-review-findings|planning/repo-cleanup/work_plan.md
30. https://github.com/y2d2/ARP_utility_code.git|main|planning/basic-usage-notebook/work_plan.md
31. https://github.com/y2d2/ARP_utility_code.git|main|planning/code-review-fixes/work_plan.md
32. https://github.com/y2d2/ARP_utility_code.git|main|planning/python-3.12-upgrade/work_plan.md
33. https://github.com/y2d2/ARP_utility_code.git|main|planning/repo-cleanup/work_plan.md
34. https://github.com/y2d2/PRP_ARP_M.git|docs/readme-diagram-rework|planning/arp-prp-data-import-verification/work_plan.md
35. https://github.com/y2d2/PRP_ARP_M.git|docs/readme-mermaid-fix|planning/arp-prp-data-import-verification/work_plan.md
36. https://github.com/y2d2/PRP_ARP_M.git|docs/repo-consistency-review|planning/arp-prp-data-import-verification/work_plan.md
37. https://github.com/y2d2/PRP_ARP_M.git|docs/repo-consistency-review|planning/readme-mermaid-fix/work_plan.md
38. https://github.com/y2d2/PRP_ARP_M.git|feat/beam-flip-event-detection|planning/arp-prp-data-import-verification/work_plan.md
39. https://github.com/y2d2/PRP_ARP_M.git|feat/beam-flip-event-detection|planning/run-all-arp-prp-experiments/work_plan.md
40. https://github.com/y2d2/PRP_ARP_M.git|feat/py312-submodule-bump|planning/arp-prp-data-import-verification/work_plan.md
41. https://github.com/y2d2/PRP_ARP_M.git|feat/py312-submodule-bump|planning/run-all-arp-prp-experiments/work_plan.md
42. https://github.com/y2d2/PRP_ARP_M.git|feat/run-all-arp-prp-experiments|planning/arp-prp-data-import-verification/work_plan.md
43. https://github.com/y2d2/PRP_ARP_M.git|feat/run-all-arp-prp-experiments|planning/run-all-arp-prp-experiments/work_plan.md
44. https://github.com/y2d2/PRP_ARP_M.git|main|planning/arp-prp-data-import-verification/work_plan.md
45. https://github.com/y2d2/agentic_scripts.git|feature/mail-guardrail-mbsync-exclusion|planning/mail-keeper-model-fix/work_plan.md
46. https://github.com/y2d2/agentic_scripts.git|feature/mail-guardrail-mbsync-exclusion|planning/mail-keeper-pruning/work_plan.md
47. https://github.com/y2d2/agentic_scripts.git|feature/mail-guardrail-mbsync-exclusion|planning/smoke-test-mail-isolation/work_plan.md
48. https://github.com/y2d2/agentic_scripts.git|feature/mail-guardrail-mbsync-exclusion|planning/workflows-mail-keeper/work_plan.md
49. https://github.com/y2d2/agentic_scripts.git|feature/opencode-v2-run|planning/mail-keeper-model-fix/work_plan.md
50. https://github.com/y2d2/agentic_scripts.git|feature/opencode-v2-run|planning/mail-keeper-pruning/work_plan.md
51. https://github.com/y2d2/agentic_scripts.git|feature/opencode-v2-run|planning/smoke-test-mail-isolation/work_plan.md
52. https://github.com/y2d2/agentic_scripts.git|feature/opencode-v2-run|planning/workflows-mail-keeper/work_plan.md
53. https://github.com/y2d2/agentic_scripts.git|feature/roadmap-dev-workflow|planning/mail-keeper-model-fix/work_plan.md
54. https://github.com/y2d2/agentic_scripts.git|feature/roadmap-dev-workflow|planning/mail-keeper-pruning/work_plan.md
55. https://github.com/y2d2/agentic_scripts.git|feature/roadmap-dev-workflow|planning/smoke-test-mail-isolation/work_plan.md
56. https://github.com/y2d2/agentic_scripts.git|feature/roadmap-dev-workflow|planning/workflows-mail-keeper/work_plan.md
57. https://github.com/y2d2/agentic_scripts.git|plan/agentic-workflows|planning/mail-keeper-model-fix/work_plan.md
58. https://github.com/y2d2/agentic_scripts.git|plan/agentic-workflows|planning/mail-keeper-pruning/work_plan.md
59. https://github.com/y2d2/agentic_scripts.git|plan/agentic-workflows|planning/smoke-test-mail-isolation/work_plan.md
60. https://github.com/y2d2/agentic_scripts.git|plan/agentic-workflows|planning/workflows-mail-keeper/work_plan.md
```

**B-listing — new engine, PRE-FIX (Run B, the evidence of the bug — 2 identities):**
```
 1. https://github.com/y2d2/ARP_roadmap.git|feature/orbit-rob-kickoff-slides|planning/orbit-rob-kickoff-slides/work_plan.md
 2. https://github.com/y2d2/ARP_roadmap.git|feature/orbit-rob-kickoff-slides|planning/orbit-rob-kickoff-workshop-notes/work_plan.md
```

**B-listing (POST-FIX, Run B2) — 60 identities: verbatim identical to the A-listing above**
(same sorted list, programmatically compared: `A == B2 → True`; no invented plans, none missing).

**Parity field-level breakdown (A vs B2):** rows per listing 60/60; identity-set symmetric difference
**empty**; per-row `approval/title/state/remove` cells — all 60 equal; per-plan details-checklist blocks —
byte-equal for all 60 plans; **0 approved (☑) rows in either listing** (so the created-rows-never-pre-approved
default migrates zero user approvals — nothing lost; nothing is startable until a user ticks approval, which
matches the live situation where the idle gate has been blocking starts anyway). Remaining diffs: section
ORDER (B2: legacy section first, then created sections in sorted order) and numeric PRIORITY re-stamp
(created rows get 1..N per section; A carried historical values up to 23). Both are render bookkeeping,
user-editable, and do not affect identity, state cells, or startability (`_select_startable` requires
approval, which is False for every row in both listings).

**Interleaving notes (natural cron, `# agentic-scripts */30`):**
- `run-20261128T160001Z` (old engine, 16:00:01–16:00:36, ok/60/11/0): fired **between** Run B (ended
  15:59:47) and Run C (started 16:01:36) — sandwiched, no overlap with any measured run.
- `run-20261128T163002Z` (old engine, 16:00… ended 16:30:36, `RUN END gate=closed workflows=4 errors=0`):
  **truly concurrent** with Run C2's last ~20 s (C2 16:29:46–16:30:24; both engine processes alive together
  — recorded, not aborted). Safe: separate state files, sandboxes, listing targets; all C2/B2 evidence
  re-read only after both processes exited (`ALL ENTRIES DONE` verified first). Neither listing or state
  changed as a result.
- agentic commit `845c139` (−429 lines on agentic `main` `plans.md`) is natural cron churn from **13:00:36**
  (run `20261128T130001Z`) — before this task started; it, not any task action, is why the first stale-ref
  read (`29e62bf`) differed. Listings of both engines were byte-stable from 13:00 onward (every post-13:00
  old-engine push a no-op).

## Deviations

1. **Engine bug fix added to overview `main` (beyond plan steps 1–7).** Acceptance #6 was unreachable with
   the shipped code (A=60 vs B=2). The fix is the minimal change to honor `reconcile`'s own documented
   contract (rule-1 rows "or is created") — 2 files, +61/−1, regression-tested, 97/97. Overview code now
   **intentionally diverges from the frozen agentic source** (the migration freeze-diff is superseded by
   this fix; the agentic side is EOL and was deliberately NOT touched — no backport). If the user rejects
   the fix, parity without it would require deleting state entries (explicitly out of scope).
2. **Merge commit `992774d` on `main`.** The fix was ff-merged onto a local `main` that hadn't yet pulled
   Run B's listing commit (`b0c1a03`), so pushing required integrating origin first. Resolved additively
   with `git pull --no-rebase` (merge commit), zero rewrites; the engine mirror `plans.md` was stash→restore
   danced around the merge and verified byte-correct afterward (working tree clean at 16:0x, then engine-
   dirty exactly as designed).
3. **Interleaving as above** — the previous migration's recurrence: a natural cron fire overlapped a
   measured run (C2). Recorded per dispatch; no abort; no cross-engine interference (isolation re-verified).
4. **Run B's listing commit `b0c1a03` is content-truncated (2 rows)** — it satisfies acceptance #4
   mechanically. The Task-3 carry-forward ("first forced run legitimately re-renders `plans.md`") held in
   FORMAT (3-col checklist) but not CONTENT due to the bug; B2's `c61f873` is the real re-render. `b0c1a03`
   remains on `main` as honest evidence (engine history, not edited away).
5. **No commit for this task's own file in agentic_scripts** — git-workflow's commit step intentionally
   skipped there (dispatch forbids commits; plan assigns the untracked `planning/` provenance commit to
   Task 5). Overview commits done + pushed. Overview local `main` deliberately not pulled to `c61f873`
   (root ` M plans.md` is the engine-owned display mirror; same steady state as agentic's checkout).

## Blockers

None. (The one blocking-class finding — the reconcile assembly bug — was root-caused, fixed, regression-
tested, and re-validated to full parity within this task.)

## Next Steps

- **GATE (orchestrator → user):** present this pack. Headline: merge + migration + stability clean; the
  forced-run validation exposed and fixed a latent `reconcile` bug that would otherwise have made the new
  engine list only pre-existing rows (migrated plans invisible). The fix commit on overview `main` needs
  the user's acknowledgment as part of cutover approval.
- **Task 5 (cleanup):** unchanged scope — now also note in the agentic README EOL text that the overview
  engine carries one post-port fix (`dc51d41`); freeze-diff comparisons of future engine work must use the
  FIXED overview code, not `745e6a9`.
- **Task 6 (cron install):** unchanged. First scheduled overview fire is expected to be a pure no-op
  (render steady `bb042ea8`, `startable=0` while nothing is approved/idle-gate closed).
- Housekeeping (optional, non-blocking): stale local remote-tracking branches harmless (`agentic main`
  `f7812e1`, overview local `main` one listing commit behind origin); fix branch `fix/reconcile-created-row-emit`
  can be pruned anytime (merged).
