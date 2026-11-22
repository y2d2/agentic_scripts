# lightweight-dev Output — Task: T5 operator surface & bootstrap

**Task:** #5    **Session:** workflows-roadmap-dev    **Date:** 2026-11-22

## Summary

Shipped the four T5 deliverables (docs/scripts only, no Python touched): (1) the new
`## Roadmap-dev workflow` README section (8 sub-sections, mirroring the OC-todo
structure), inserted between `## OC-todo workflow` and `## Extending with a new
workflow`, written from the 2026-11-21 no-PR contract and cross-checked against the
landed T1–T3 code (listing columns/renderer, scan branch filter, reconciler rules,
state machine, sandbox layout, idle-gate mechanics); (2) a new numbered step 6
"roadmap-dev preflight" in `scripts/setup.sh` (data-driven `uv run --project`
one-liner; inert OK line on the shipped empty allowlist; WARN-only `git ls-remote
--exit-code … HEAD` reachability checks for allowed repos + listing repo; subsequent
steps renumbered 6→7, 7→8, 8→9), plus the matching one-line update to the README's
`## Setup` step list; (3) `scripts/bootstrap_task_overview.sh` — one-shot, idempotent,
`--dry-run`, pure git over SSH (no curl/python/PAT), with `--repo` override and the
optional `--vault <path>` submodule step carrying the refuse-on-dirty-vault guard
(commits ONLY `.gitmodules` + `autonomous_task_overview`); (4) the
`autonomous_task_overview/` staging dir with exactly `README.md` (what-the-repo-is +
5 authoring rules incl. the major-question definition + listing legend/sample +
state machine + operating actions incl. the human PR step) and `plans.md` (header
skeleton, no table sections). Committed as a single commit with an `OC:` prefix
(5 explicit paths staged; not pushed, per dispatch). All 10 numbered acceptance
criteria verified — details in the table below, including a hermetic end-to-end
bootstrap test against local bare repos (git `insteadOf` rewrite in a throwaway
`GIT_CONFIG_GLOBAL`, no real GitHub touched, real listing repo still 0 refs).

## Files

| File | Action | Why |
|---|---|---|
| `README.md` | modify | New `## Roadmap-dev workflow` section (Overview / Configuration / How a run works / The listing / State machine / Operator commands / Where outputs live / Guardrails) + the `## Setup` step list updated for the new setup.sh step. |
| `scripts/setup.sh` | modify | New step 6 "roadmap-dev preflight" (inert OK line; WARN-only reachability for allowed repos + listing repo); steps renumbered (Runtime dirs 7, Timer 8, Summary 9); header comment updated. |
| `scripts/bootstrap_task_overview.sh` | create | One-shot pure-git-SSH bootstrap of the empty `y2d2/autonomous_task_overview` listing repo (staged `autonomous_task_overview/*` → `main`), `--dry-run`, `--repo` override, optional `--vault <path>` submodule step with refuse-on-dirty-vault guard. |
| `autonomous_task_overview/README.md` | create | The listing repo's own README: what-the-repo-is, 5 plan-authoring rules, listing legend + exact 2-section sample + priority semantics + identity note, 5-state machine, operating actions (incl. human PR open/merge + branch prune + delete-folder escape hatch). |
| `autonomous_task_overview/plans.md` | create | Listing skeleton: title + one pointer line, NO table sections — parses to zero rows via the workflow's `parse_listing` (verified directly). |

## Build / Tests

- `bash -n scripts/setup.sh`: PASS — clean.
- `bash -n scripts/bootstrap_task_overview.sh`: PASS — clean.
- `bash scripts/setup.sh` (run 1, this box): PASS — exit 0, ends `[OK] setup complete (no failures)`, prints `[OK] roadmap-dev: allowlist empty — workflow is inert (no-op until repos are listed)`; no new FAILs with the shipped empty allowlist.
- `bash scripts/setup.sh` (run 2, idempotency): PASS — byte-identical except one pre-existing non-deterministic uv line in step 2 (`Checked 10 packages in 48ms` → `0.45ms`; not part of the new step).
- setup.sh step 6 non-inert branch (scratch config: 1 local reachable repo + 1 bogus repo + listing): PASS — `[OK]` for the reachable repo, `[WARN]` (not FAIL) for the bogus repo and the unreachable listing, with the `scripts/bootstrap_task_overview.sh` note.
- `bash scripts/bootstrap_task_overview.sh --dry-run` (this box, real remote): PASS — prints preflight `[repo reachable, empty]` → planned push_initial → submodule-reminder; exit 0; verified `git ls-remote` of the real `y2d2/autonomous_task_overview` still returns 0 refs (no push) and no vault writes (no `--vault`).
- Hermetic full-flow test (local bare repos via `insteadOf` in a throwaway `GIT_CONFIG_GLOBAL`; no real GitHub, no global-config pollution): PASS — empty-remote initial push (`main` with exactly `README.md` + `plans.md`, commit `OC: Initial task-overview content (plans listing + authoring guide)`, bot identity fallback), populated-remote re-run skip, clean-vault `--vault` run (submodule added; commit contains exactly `.gitmodules` + `autonomous_task_overview`; vault pushed), already-added re-run skip.
- Dirty-fixture-vault refusal (scratch `git init` repo, one dirty tracked file, `--vault`): PASS — `[FAIL] refusing the vault step: … uncommitted changes outside .gitmodules/autonomous_task_overview …` + the offending path listed; exit 1; `git log` unchanged (nothing committed) and the dirty file left untouched.
- `plans.md` skeleton parse (actual `agentic_scripts.workflows.roadmap_dev.parse_listing`): PASS — 0 rows.
- `uv run pytest tests/ -q` (full suite, sanity — no Python was modified): PASS — 299 passed in 46.21s.

## Acceptance Verification

| # | Criterion (verbatim) | Result | Notes |
|---|---|---|---|
| 1. (T1) | `grep -n "^## " README.md` shows the new section between `OC-todo workflow` and `Extending with a new workflow`; the section contains the 6 sub-sections above; the state machine table and listing sample match the plan doc verbatim in substance (spot-check the 6 columns and the 5 states). | PASS | `## Roadmap-dev workflow` at L301, between `## OC-todo workflow` (L216) and `## Extending with a new workflow` (L496). All sub-sections present as `###` (Overview, Configuration, How a run works, The listing, State machine, Operator commands, Where outputs live, Guardrails). Listing sample = the plan doc's exact 2-section example (6 columns; header/separator byte-matched to the renderer's `_LISTING_HEADER`/`_LISTING_SEPARATOR`); 5-state table carries the startable column with the contract wording (`success` = attempt branch pushed, human verifies/merges). |
| 1. (T2) | `bash -n scripts/setup.sh` clean; running `bash scripts/setup.sh` on this box ends with `[OK] setup complete (no failures)` (it currently does — the new steps must not introduce FAILs with the shipped empty allowlist) and prints the `roadmap-dev: allowlist empty` OK line. | PASS | See Build/Tests: syntax clean; run 1 exit 0, `[OK] setup complete (no failures)`, and `[OK] roadmap-dev: allowlist empty — workflow is inert (no-op until repos are listed)` printed; no FAILs. |
| 2. (T2) | Re-running immediately produces identical output (idempotent). | PASS | Run 2 diff vs run 1: only the pre-existing uv timing line in step 2 (`Checked 10 packages in 48ms` → `0.45ms`); every setup-logic line, incl. the new step, byte-identical. |
| 1. (T3) | `bash -n scripts/bootstrap_task_overview.sh` clean. | PASS | |
| 2. (T3) | `bash scripts/bootstrap_task_overview.sh --dry-run` on this box → prints the planned steps (preflight [repo reachable, empty] → push_initial → submodule-reminder) and exits 0; `--dry-run` performs NO pushes, NO vault writes (its `git ls-remote` preflight probe is the only network call — acceptable: read-only). | PASS | Output matched the planned-step sequence exactly; exit 0; real listing repo verified still 0 refs after the dry-run; only network call was the read-only `git ls-remote` probe (no temp dir created in dry-run). |
| 3. (T3) | `--vault` with a dirty temp fixture vault (a scratch `git init` repo with one dirty unrelated file) → refuses with the uncommitted-work message, exit 1, nothing committed. | PASS | Fixture: scratch repo, 1 commit, 1 dirty tracked file. Script printed the refusal message listing the offending path, exited 1, `git log` unchanged, dirty file untouched. |
| 4. (T3) | Idempotent second run against a populated remote: `push_initial` skipped (`[OK] remote already populated`), submodule step skipped (already added), exit 0. | PASS | Hermetic test: run 1 populated the local bare remote; run 2 printed `[OK] remote already populated — skipping initial push` + `[OK] vault submodule already present … — skipping`, exit 0. |
| 5. (T3) | No changes to any Python source file in this task; the script uses only git + coreutils (no curl, no python, no PAT). | PASS | Commit touches only `README.md`, `scripts/setup.sh`, `scripts/bootstrap_task_overview.sh`, `autonomous_task_overview/*`. Script tooling: bash + git + coreutils (`timeout`, `mktemp`, `cp`) + `sed` (POSIX text tail/prefix); no curl, no python, no PAT reference anywhere. |
| 1. (T4) | `autonomous_task_overview/` contains exactly `README.md` + `plans.md`; the README covers: what-the-repo-is, the 5 authoring rules (incl. the major-question definition), the listing legend, the state machine, the operating actions (incl. the human PR step). | PASS | `ls` shows exactly the two files. README sections: "What this repo is" (workflow- vs user-owned cells, pushed attempt branches, human opens the PR), "How to write a plan" (rules 1–5 incl. major = scope/requirements/dependencies, NOT implementation detail), "The listing" (legend table + exact 2-section sample + priority semantics incl. max+1 + identity note), "State machine" (5 states, startable column), "Operating the listing" (approve / re-prioritize / answer a review / re-arm / remove / human open+merge PR + prune / delete-folder escape hatch). |
| 2. (T4) | The skeleton `plans.md` parses to an empty listing (cross-checked in T6's tests — no test code in this task). It carries a short header (title + one pointer line to the README) and NO table sections yet. | PASS | Verified with the actual `parse_listing` (T2 core): 0 rows. File is title + one pointer line + one note line; no `# <repo>`/`## <branch>` table sections. |

## Blockers

None.

Flags for the record (no action needed by T5; follow the contract text per dispatch):

1. **Task-plan Context wording vs contract/code (flagged, not edited).** The T5 Context
   summary says "Outcomes: success → PR (…)" and "How a run works … (… PR refs)", and the
   reviewed plan doc's state-machine table says `success` = "PR opened" — but the
   2026-11-21 user contract + the landed T2/T3 code (`apply_job_outcome`: "the pushed
   attempt branch is the delivery, NO PR is created"; state schema records `branch_name`,
   not PR refs) say the agent pushes the attempt branch and a human opens the PR. The
   README follows the contract throughout. If the orchestrator wants the plan doc's
   `success` row wording aligned to the no-PR contract, that is a doc fix outside T5 scope.
2. **`config/workflows.yaml` still ships `roadmap_prompts.listing_repo: y2d2/ARP_prompts`**
   (T1's pre-rename value). Per the task plan's Notes, T6 updates it; the README documents
   the target `y2d2/autonomous_task_overview` (the `ARP_prompts` name appears in no new
   artifact). Until T6 lands there is a temporary README↔yaml default mismatch; setup.sh
   step 6 reads the value from the yaml dynamically, so it stays correct either way.
3. **Operational bootstrap run vs dirty vault.** The live vault
   `/workspace/Obsidian/ARP_roadmap` (`feature/orbit-rob-kickoff-slides`) is dirty right
   now (modified `projects/ORBIT/DMP/ORBIT_DMP_v0.md` + untracked
   `planning/orbit-rob-kickoff-slides/build/…`), and no `autonomous_task_overview`
   submodule exists yet. The pre-approved operational run of
   `scripts/bootstrap_task_overview.sh --vault /workspace/Obsidian/ARP_roadmap` will be
   REFUSED by the (spec-mandated) dirty guard until that slides work is committed or
   stashed. The initial-push half can run without `--vault` right now (remote is empty);
   the vault wiring is then a one-flag follow-up once the vault is clean.

## Next Steps

- **T6 (final integration):** flip `workflows.roadmap-dev.enabled: true`; set
  `roadmap_prompts.allowed_repos` (the 9 repos per global-plan B3); update
  `roadmap_prompts.listing_repo` to `y2d2/autonomous_task_overview`; add the hermetic
  smoke (the `plans.md` skeleton already parses to 0 rows — verified here with the
  landed `parse_listing`).
- **Orchestrator operational step (user pre-approved):** run
  `bash scripts/bootstrap_task_overview.sh` against the real empty
  `y2d2/autonomous_task_overview` (push initial content over SSH), then — once the
  vault's slides work is committed — re-run with
  `--vault /workspace/Obsidian/ARP_roadmap` (submodule-only commit + push on the
  vault's current branch). No other action needed from this task.
- Push of this task's commit is the orchestrator's (between waves) — left unpushed
  here per dispatch.
