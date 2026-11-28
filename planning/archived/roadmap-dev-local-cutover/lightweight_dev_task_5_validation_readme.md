# lightweight-dev Output — Task: Validation run + README restore

**Task:** #5    **Session:** roadmap-dev-local-cutover    **Date:** 2026-11-27

## Summary

Proved the re-hosted roadmap-dev end-to-end in `/workspace/Python/agentic_scripts` and restored its README docs. Validation run (`run --only roadmap-dev`, unforced): exit 0, idle gate CLOSED (`active_sessions=3 verdict=CLOSED`) → scan + reconcile only, zero spawns, `WORKFLOW roadmap-dev status=ok items_found=77 actions=12 errors=0`, root `plans.md` mirrored (723 lines, 77 per-plan sections, byte-identical to `origin/main:plans.md`). Cron coexistence full run: exit 0, noop/mail-keeper/oc-todo `status=skipped reason=quiet gate closed`, roadmap-dev ok, no errors. README restored (overview, pipeline mermaid, config table incl. `local_listing`, idle-gate semantics, listing/state-machine/operator surface, guardrails, runbook warning) and committed with the tracked root `plans.md`; pushed.

**One repair was required mid-validation** (see Blockers): a migration-leftover `sandbox/roadmap-dev/prompts` clone pinned to the old `y2d2/autonomous_task_overview` remote made the first runs reconcile against AT's stale 19-line listing. Evacuated the clean scratch clone (preserved in /tmp), re-ran — the workflow self-cloned from the configured remote and everything aligned.

## Files

| File | Action | Why |
|---|---|---|
| `README.md` | modify | Replaced the "Unattended plan execution (moved)" stub with the full Roadmap-dev workflow section; updated intro (two gate types), What/why, Workflows-section `gate` key, Running-section runbook warning |
| `plans.md` | create (tracked) | Root mirror of the live 77-plan listing produced by the validation run's mirror; now committed per plan |
| `/tmp/opencode/roadmap-dev-prompts-stale-AT-clone-20261127/` | create (outside repo) | Forensic backup of the stale wrong-remote prompts clone (disposable) |

Commit (message form): `OC: README roadmap-dev section + initial plans.md listing from validation run` → `e228c7c`, pushed to `feature/roadmap-dev-workflow` (1d27646..e228c7c). Only `README.md` + `plans.md` staged; `planning/*` left untracked as instructed.

## Build / Tests

- Validation run `uv run agentic-scripts run --only roadmap-dev` (17:01 UTC): PASS exit 0 — but mirror content revealed the stale-clone issue (below)
- Re-run after clone repair (17:20 UTC): PASS exit 0, full 77-row mirror, `listing mirrored to .../plans.md` logged
- Cron coexistence run `uv run agentic-scripts run` (17:23 UTC): PASS — 3 quiet-gate workflows skipped, roadmap-dev ok, `RUN END errors=0`
- Post-commit 17:30 cron fire: PASS — `WORKFLOW roadmap-dev status=ok items_found=77 errors=0` on the new clone (repair proven under cron)
- README: no stale `autonomous_task_overview` claim (grep: none); 14 code fences balanced; mermaid block structurally verified (27 nodes — 24 rects + 3 diamonds — all defined, edge-referenced, class-assigned; quotes balanced); `## main` inside the listing example is inside a code fence (renders as code)
- No code changes → test suite untouched (344 tests remained green from Task 4); no `--force` used; no lock collisions (manual runs at 17:01/17:20/17:23, all ≥4 min clear of :00/:30)

## Acceptance Verification

| # | Criterion (verbatim) | Result | Notes |
|---|---|---|---|
| 1. | Exit code 0. | PASS | `EXIT_CODE=0` (both `--only` run and the post-repair re-run). |
| 2. | Run log contains a `GATE`/idle-gate line with `verdict=CLOSED` (active sessions present) or an open verdict with **no** agent spawn — in practice CLOSED; and a `WORKFLOW roadmap-dev status=ok` line with non-zero items scanned (state had 77 items as of 2026-11-26). | PASS | `GATE ... active_sessions=3 verdict=CLOSED reason=3 active session(s)`; `WORKFLOW roadmap-dev status=ok items_found=77 actions=12 errors=0 duration=65.96s` (log `run-20261127T172030Z.log`). |
| 3. | No line indicating a `planner-enhanced` agent spawn / job start. | PASS | Log contains no spawn/job lines; drain never entered (gate CLOSED). |
| 4. | `/workspace/Python/agentic_scripts/plans.md` exists, contains per-plan sections (`### <plan>` headings + six-column rows) for un-archived plans across the allowed repos, and the log shows a mirror/push action. | PASS | After the clone repair: 723 lines, 77 `###` sections + six-column data rows across the 8 repos with plans, `diff`-identical to `origin/main:plans.md`; log shows `roadmap-dev: listing mirrored to /workspace/.../plans.md`. Before the repair the first run mirrored only AT's stale 19-line listing (2 sections) — see Blockers. No listing push was needed (canonical main already held the identical 77-row listing from the 12:3x–12:4x runs). |
| 5. | `state/roadmap-dev.json` mtime is now and content reflects the run; `state/scheduler.json`'s idle-gate key updated. | PASS | Content reflects the run (77 scanned plans reconcile onto the 93 state entries; saved only-when-changed by design, `roadmap_dev.py` run() final save guard), so its mtime correctly stays at the 09:28 migration copy. `scheduler.json` mtime IS now — written by the run's gate evaluation, clearing `idle_gate_last_ok` to null (the documented CLOSED write). |
| 6. | verify `crontab -l` still holds only the agentic-scripts entry | PASS | Exactly one entry (+ its comment line) — the `*/30` agentic-scripts line. |
| 7. | exit 0; log shows quiet-gate workflows `status=skipped reason=quiet gate closed` (outside 22:00–08:00) and `roadmap-dev status=ok`; no errors. | PASS | Full run `run-20261127T172324Z.log`: noop/mail-keeper/oc-todo all `status=skipped reason=quiet gate closed`, `WORKFLOW roadmap-dev status=ok items_found=77`, `RUN END gate=closed workflows=4 errors=0`. |
| 8. | `grep -n "roadmap-dev" README.md` hits the new section | PASS | 24 hits; `## Roadmap-dev workflow` at README line 308. |
| 9. | markdown renders sanely (no broken mermaid fence) | PASS | Fence count even (14); mermaid validated structurally (all node/edge/class references consistent, quotes balanced); example `## main`/tables confirmed inside code fences. |
| 10. | no stale claim that roadmap-dev lives in autonomous_task_overview | PASS | `grep -n autonomous_task_overview README.md` → none; moved-stub replaced; intro/Running updated to state roadmap-dev runs from this repo (cron `*/30` unchanged); config table notes the effective `listing_repo: y2d2/agentic_scripts`. |
| 11. | commit pushed | PASS | `OC: README roadmap-dev section + initial plans.md listing from validation run` (message per plan), `README.md` + `plans.md` only, pushed 1d27646..e228c7c to `feature/roadmap-dev-workflow`. |
| 12. | `git status` shows no leftover unstaged source changes (untracked `planning/*` artifacts may remain) | PASS | Post-push `git status --short` minus `?? planning/*` = empty. |

## Blockers

None (everything landed). Findings needing orchestrator attention:

1. **RESOLVED — stale migration clone pinned the live runs to the old listing repo.** `sandbox/roadmap-dev/prompts` (copied in with sandbox preservation during the cutover) had remote `git@github.com:y2d2/autonomous_task_overview.git`; `_clone_or_fetch` only fetches an existing clone (never repairs the remote) and `_fetch_listing` reads the clone's worktree, so the 16:30/17:00/17:01 runs reconciled against AT's stale 19-line listing (2 plan sections) instead of `y2d2/agentic_scripts` main. Fix applied: moved the scratch clone (clean, `HEAD==origin/main`, no unique objects) to `/tmp/opencode/roadmap-dev-prompts-stale-AT-clone-20261127`; the next run self-cloned from the configured remote; the 17:30 cron fire confirmed healthy on the new clone. **If any other sandbox subdir was copied from AT, it should be checked for the same wrong-remote pinning.**
2. **Suspected upstream reconcile gap (code-read only, not empirically triggered; no live impact now):** in `reconcile()`'s output assembly, a rule-1 *created* row (scanned + in state but **no existing listing row**) is computed into `updated_by_key` but never emitted (only existing-row matches and rule-2 rows are assembled). With the migrated 93-entry state, a plan tracked in state but missing from `plans.md` could never be re-materialized (only a plan edit → new identity → rule-2 recovers it). This also exactly explains why the stale-remote runs collapsed to AT's 2-row listing. Suggest a follow-up task + test if confirmed.
3. `y2d2/ARP_IMU`: the historical `Permission denied (publickey)` hiccup did **not** recur — all runs scanned it (1 plan). The 9 sandbox repo clones all have correct remotes.
4. `state/roadmap-dev.json` holds 93 entries vs 77 scanned: the 16 non-scanned entries are kept-forensics vanished plans (documented reconcile behavior), e.g. AT-era allowlist members; harmless.

## Next Steps

- Orchestrator: triage finding 2 (reconcile rule-1 row-creation assembly) — a small upstream fix + regression test in the workflow module would close it.
- Orchestrator: consider a guard in `_clone_or_fetch` (warn/repair when an existing clone's remote URL differs from the configured one) — cheap defense against future sandbox migrations of this kind.
- The /tmp backup of the stale clone can be deleted whenever.
