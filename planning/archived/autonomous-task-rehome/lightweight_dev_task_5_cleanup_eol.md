# lightweight-dev Output — Task: Cleanup + EOL banner (roadmap-dev removal from agentic_scripts)

**Task:** #5    **Session:** lightweight-dev sub-agent of the `autonomous-task-rehome` plan    **Date:** 2026-11-28

## Summary

Roadmap-dev is fully removed from `/workspace/Python/agentic_scripts` (branch
`feature/roadmap-dev-workflow`) per the approved cutover gate, and the README EOL banner
published. Executed strictly in spec order:

1. **Provenance commit FIRST** — exactly the 4 listed planning paths (43 files,
   4,723 insertions): `planning/autonomous-task-repo-move/` (18 files incl. result reports
   1–8), `planning/archived/listing-detail-row-and-workflow-diagram/` (5),
   `planning/archived/plans-md-details-checklist/` (9), `planning/autonomous-task-rehome/`
   (11 — incl. result reports 1–4; plans 1–7). Verified: 0 paths outside `planning/`
   (`git show 56e7e29 --name-only | grep -vc "^planning/"` → `0`);
   `planning/mail-keeper-pruning/` deliberately left untracked.
2. **Baseline suite (pre-edit):** `355 passed in 78.82s` — green before any change.
3. **Deletions (git rm):** `src/agentic_scripts/workflows/roadmap_dev.py`,
   `tests/test_roadmap_dev.py`, `tests/test_roadmap_dev_scan.py`,
   `tests/test_roadmap_dev_pipeline.py`, `tests/test_roadmap_dev_listing_mirror.py`,
   `tests/smoke/test_smoke_roadmap_dev.py`, `plans.md` (needed `-f`: the 18:00 cron fire's
   mirror write had modified it — expected per dispatch warning).
4. **Config de-trim:** `config/workflows.yaml` restored to the pre-`b063a74` shape via
   `git checkout b063a74^ --` (removes the `roadmap_prompts:` section incl. the `local_listing`
   line from `092aeae`, and the `workflows.roadmap-dev:` entry; noop/mail-keeper/oc-todo entries
   byte-identical, `admin_repo` stays). `src/agentic_scripts/config.py` likewise restored to its
   `b063a74^` shape (drops `RoadmapPrompts`, `_EMPTY_ROADMAP_PROMPTS`,
   `DEFAULT_RUN_TIMEOUT_MINUTES`, `_load_roadmap_prompts`, the `Config.roadmap_prompts` field,
   the `allowed_sections` entry, the optional-load block, the kwarg, and docstring refs —
   exactly the reverse of the transplant + mirror commits). `scripts/` needed no change
   (`setup.sh` carries no roadmap step; grep-clean).
5. **Shared test fixes:** `tests/conftest.py` restored to `b063a74^` (the
   `strip_live_repo_workflows` guard + `LIVE_REPO_WORKFLOWS`/`LIVE_REPO_SECTIONS` existed **only**
   to quarantine roadmap-dev, and the autouse `_redirect_roadmap_mirror_root` fixture only to pin
   the roadmap mirror root — both removed; `base_config` deep-copies the shipped config again).
   Same restore for `tests/test_config.py` (the `roadmap_prompts` test block is gone; the
   shipped-config assertion is back to `[noop, mail-keeper, oc-todo]`),
   `tests/smoke/conftest.py` (docstring roadmap-free; the autouse canned-probe fixture kept as
   inert defense-in-depth), `tests/smoke/test_smoke_base.py`, `tests/smoke/test_smoke_mail_keeper.py`,
   `tests/smoke/test_smoke_oc_todo.py` (strip-import + docstring refs removed). **Beyond the plan's
   named list:** `tests/test_scheduler.py` also imported `strip_live_repo_workflows` (added by
   `b063a74` without a literal "roadmap" token) — restored to `b063a74^` for the same reason.
   No unrelated test was weakened: every restored file is byte-identical to its pre-port shape;
   the only hand edits were docstring rewords (next item).
6. **Docstring de-mention** (required by the zero-hits criterion; comments only, zero behavior
   change): `agent.py` ×2 (pid-forensics wording), `config.py` + `workflows/base.py`
   ("admin (roadmap) repo" → "admin repo"), `sessions.py` ×1, `git.py` ×6 (primitive-attribution
   wording made generic). These mentions pre-dated `b063a74` but the literal grep criterion
   requires them gone.
7. **README:** EOL banner (spec text + the mandated engine-fix sentence on `dc51d41`) is the
   FIRST content block, above the H1; the entire `## Roadmap-dev workflow` section (~260 lines,
   from `e228c7c`) deleted; the intro paragraph, the `gate` key doc, the `What / why` goal bullet,
   and the Running-section roadmap Runbook warning updated/removed. Remaining roadmap/plans.md
   mentions: banner (lines 1–4) + the intro pointer sentence (line 16) only.
8. **main one-off:** throwaway branch `tmp/remove-plans-md` from `origin/main` → `git rm plans.md`
   → commit → `git push origin HEAD:main` → **accepted directly, no rejection**
   (`845c139..b5cac40 HEAD -> main`); returned to `feature/roadmap-dev-workflow`, throwaway branch
   deleted. The branch window was ~3 s, far from any fire.
9. **Removal commit** (step 3–7 paths, explicitly staged, 21 files) + push.

### Interleaving notes (live cron checkout)

- **18:00:02Z fire** (pre-yaml-edit, old tree): ran the old engine view — quiet gate CLOSED +
  idle-gate probe line `active_sessions=1 verdict=CLOSED`, `RUN END gate=closed workflows=4
  errors=0 duration=35.3s`. Harmless; its mirror write is why `plans.md` needed `git rm -f`.
- **`config/workflows.yaml` was the FIRST working-tree edit** (~18:12, right after the provenance
  commit) so the next fire could not see the roadmap entry at all.
- **18:30:01Z fire** (first fire on the fully trimmed, committed tree): `RUN START` → quiet-gate
  `CLOSED` → `RUN END gate=closed workflows=0 errors=0 duration=0.0s`, `last-run.txt`
  `overall: skipped`, `workflows: -` — no idle-gate probe line (was present at 18:00), no
  `plans.md` regeneration (working tree stayed clean after the fire). Live confirmation that the
  cron now sees only noop/mail-keeper/oc-todo.
- **No fire overlapped** the branch switch or the final verification.

## Files

| File | Action | Why |
|---|---|---|
| 43 files under the 4 listed `planning/` paths | add (commit 1) | Provenance archive — migration + re-home plan/result history |
| `src/agentic_scripts/workflows/roadmap_dev.py` | delete (git rm) | Engine now lives only in `y2d2/autonomous_task_overview` |
| `tests/test_roadmap_dev{,_scan,_pipeline,_listing_mirror}.py`, `tests/smoke/test_smoke_roadmap_dev.py` | delete (git rm) | Roadmap test suite moved with the engine |
| `plans.md` (root) | delete (git rm -f) | Listing moved to the overview repo |
| `config/workflows.yaml` | restore to `b063a74^` | Drop `roadmap_prompts:` section + `workflows.roadmap-dev:` entry; `admin_repo` stays |
| `src/agentic_scripts/config.py` | restore to `b063a74^` + docstring reword | Un-transplant `RoadmapPrompts` & wiring; "admin repo" wording |
| `tests/conftest.py` | restore to `b063a74^` | `strip_live_repo_workflows` + mirror-root autouse fixture were roadmap-only |
| `tests/test_config.py` | restore to `b063a74^` | Roadmap-prompts test block gone; workflow-list assertion back to 3 |
| `tests/test_scheduler.py` | restore to `b063a74^` | Import of the removed roadmap-only guard (beyond plan's named list — required) |
| `tests/smoke/conftest.py`, `test_smoke_base.py`, `test_smoke_mail_keeper.py`, `test_smoke_oc_todo.py` | restore to `b063a74^` | Drop strip-import/strip-docstring refs |
| `src/agentic_scripts/agent.py`, `git.py`, `sessions.py`, `workflows/base.py` | reword docstrings | Zero-literal-hits criterion (pre-existing mentions; comments only) |
| `README.md` | modify | EOL banner first block; roadmap-dev section + Runbook warning removed; intro/goal/gate-key updated |

## Build / Tests

- **Baseline suite (pre-edit):** PASS — `355 passed in 78.82s (0:01:18)`.
- **Final suite (`uv run pytest tests/ -q`):** PASS — `237 passed in 40.05s` (exit 0). Mail/oc-todo/noop
  suites intact (none deleted): `ls tests/` shows all 19 test modules + `tests/smoke/` (3 smoke modules);
  smoke-only run: `13 passed in 5.28s`. No unrelated test weakened — de-trim was file-shape restores
  to the known-good pre-port commit + comment rewords.
- **Config load:** PASS — prints `['noop', 'mail-keeper', 'oc-todo']`, `has roadmap_prompts: False`.
- **Lint:** PASS — `uv run ruff check src tests config` → "All checks passed!".
- **Crontab:** UNTOUCHED — `crontab -l | md5sum` = `cfb0988abb2ccee6dc0a3a628e485caf` (identical to
  the Task-6-of-repo-move baseline); `# agentic-scripts */30` entry present.
- **Post-task live fire (18:30:01Z):** PASS — `workflows=0 errors=0`, no roadmap activity (see notes).

## Grep evidence (verbatim)

Final battery run after `find src tests config scripts -name __pycache__ -type d -exec rm -rf {} +`
(stale gitignored `.pyc` of deleted modules were purged; regenerated caches contain no roadmap string):

```
$ grep -rn roadmap src/ tests/ config/ scripts/
config/workflows.yaml:20:admin_repo: /workspace/Obsidian/ARP_roadmap   # string or null
grep exit: 0
```

Single remaining hit = the `admin_repo` VALUE, see Acceptance #2 note. `src/`, `tests/`, `scripts/`:
zero hits, text and binary alike.

## Commits (all pushed)

| Commit | Branch | Message | Push confirmation |
|---|---|---|---|
| `56e7e29` | feature/roadmap-dev-workflow | `OC: Archive migration + re-home planning provenance` | `745e6a9..56e7e29  feature/roadmap-dev-workflow -> feature/roadmap-dev-workflow` |
| `b25dc58` | feature/roadmap-dev-workflow | `OC: Remove roadmap-dev — moved permanently to y2d2/autonomous_task_overview (+ README EOL banner)` | `56e7e29..b25dc58  feature/roadmap-dev-workflow -> feature/roadmap-dev-workflow` |
| `b5cac40` | main (via throwaway `tmp/remove-plans-md`) | `OC: Remove plans.md — listing moved to autonomous_task_overview` | `845c139..b5cac40  HEAD -> main` (direct push accepted) |

`b25dc58 --stat`: **21 files changed, 50 insertions(+), 9895 deletions(-)** — exactly the 7 deletions
+ 14 modifications; no stray paths. `56e7e29 --name-only | grep -vc "^planning/"` → `0`.

## README EOL banner (as rendered, first content block)

```markdown
> ⚠️ **Autonomous task execution has MOVED.** The roadmap-dev engine (plan scan → `plans.md`
> listing → idle-time execution) now lives and develops EXCLUSIVELY in
> **`git@github.com:y2d2/autonomous_task_overview.git`** (`/workspace/Python/autonomous_task_overview`).
> Do NOT develop roadmap/plans-engine features in this repo — changes here are dead code and will
> be lost. This repo now hosts only the `noop`, `mail-keeper`, and `oc-todo` workflows. The
> overview-side engine additionally carries one post-port reconcile fix (`dc51d41` — created rows
> of state-migrated plans were dropped from the listing) and is the canonical engine code going
> forward. (Moved 2026-11-28; history in `planning/autonomous-task-rehome/`.)
```

## Acceptance Verification

| # | Criterion (verbatim) | Result | Notes |
|---|---|---|---|
| 1. | "Provenance commit exists, contains ONLY the 4 listed planning paths" | PASS | `56e7e29`: 43 files, all under the 4 listed paths (verified 0 outside `planning/`); `planning/mail-keeper-pruning/` untouched. |
| 2. | "grep for `roadmap` in src/tests/config/scripts = 0 hits (banner excepted)" | PASS (one documented exception) | Verbatim grep above: zero hits in `src/`, `tests/`, `scripts/`; single hit in `config/workflows.yaml` is the `admin_repo` **value** `/workspace/Obsidian/ARP_roadmap` — a real on-disk vault path that spec step 3 explicitly mandates keeping ("admin_repo stays") and that mail-keeper requires (acceptance #3). It is an operational path string, not roadmap-dev coupling; the spec's own steps make a literal zero impossible, so step-3 + acceptance #3 take precedence. |
| 3. | "`uv run pytest tests/ -q` exit 0 (mail/todo/noop suites intact, none deleted)" | PASS | `237 passed in 40.05s`, exit 0. All mail (`test_mail_{canary,keeper,prune,reader,search}`), oc-todo (`test_oc_todo{,_pipeline}`, smoke), noop/base, gate/git/lock/sessions/state/scheduler/config suites present and green; smoke run 13/13. |
| 4. | "ruff clean" | PASS | `uv run ruff check src tests config` → "All checks passed!". |
| 5. | "EOL banner is the first content block; roadmap-dev section removed" | PASS | Banner = README lines 1–8, above the H1 (rendered above, incl. the mandated `dc51d41` canonical-code sentence); `## Roadmap-dev workflow` (~260 lines) deleted; remaining headings: What/why … Extending. |
| 6. | "`y2d2/agentic_scripts` main no longer contains `plans.md`" | PASS | `b5cac40` on `origin/main` (direct push accepted, no rejection): `1 file changed, 790 deletions(-)`. `origin/main` now: README.md only. |
| 7. | "exactly 2 commits from this task (provenance + removal) (+ the one-off main commit); all pushed; `crontab` UNTOUCHED" | PASS | Feature branch: exactly `56e7e29` + `b25dc58` (both pushed, branch in sync with origin). Main: exactly `b5cac40` (pushed). Crontab md5 `cfb0988abb2ccee6dc0a3a628e485caf` unchanged from baseline. Throwaway local branch deleted. |

## Blockers

None. Judgment calls recorded: (a) `tests/test_scheduler.py` added to the restore list — it imported
the roadmap-only `strip_live_repo_workflows` guard (no literal "roadmap" token, so it appeared
test-clean until the guard itself was removed); (b) pre-existing "roadmap" docstring mentions in
`agent.py`/`git.py`/`sessions.py`/`config.py`/`base.py` (older than the port) were reworded to meet
the literal zero-hits grep — comments only, zero behavior change; (c) the `admin_repo` value
exception per Acceptance #2.

## Next Steps

- Task 6 (cron install in `autonomous_task_overview`) may proceed — this checkout's cron entry is
  untouched and now drives noop/mail-keeper/oc-todo only (verified live at 18:30).
- This result report is written after commit `b25dc58` and deliberately left UNTRACKED (repo
  convention from the repo-move cleanup; a third feature-branch commit would violate acceptance #7).
- Optional, out of scope: `state/roadmap-dev.json` (gitignored) may be removed by an operator at
  convenience; the dormant idle-gate machinery (`evaluate_idle_gate`, `sessions.py`,
  `WorkflowEntry.gate`) stays per spec.
