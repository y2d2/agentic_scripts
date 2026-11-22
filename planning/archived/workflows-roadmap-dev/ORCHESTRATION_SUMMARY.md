# Orchestration Summary — roadmap-dev workflow (complete)

**Orchestrator:** planner-enhanced · **Session date:** 2026-11-22 · **Branch:** `feature/roadmap-dev-workflow`
**Plan:** `work_plan.md` (T1–T6) + follow-up tasks T5b, T6b, T6c, T6d (each with its result report below).

## Delivery (all committed + pushed)

| Task | Scope | Commit |
|------|-------|--------|
| T1 | scheduler gate rewire (idle gate, `--force`), config schema | `c7f493a` (+ drift `e86e717`) |
| T2 | pure core: plan identity, folder hash, listing parse/reconcile | `26b9f57` |
| T3 | Phase-1 scan/reconcile/push + `git.py` `ls_tree`/`mv`/`checkout` | `f7caea1` |
| T4 | drain + job pipeline, `AgentResult.pid` | `08605f6` |
| T5 | operator surface (bootstrap script, setup preflight) | `f3f4454` |
| T5b | vault-guard refinement (staged-path dirt only) | `ce89de5` |
| T6 | enable workflow + 6 smoke tests + last-run verdict fix | `ea4fd29` |
| T6b | keep smoke/scheduler tests hermetic vs. seeded allowlist | `0a262c2` |
| T6c | fix SSH URL derivation (colon, not slash) + regression tests | `fbfe0af` |
| T6d | binary-safe plan-folder scan (raw-byte reads + hash) | `14c2ae9` |
| ops | seed `allowed_repos` with the 9 operator-selected repos | `1ab819d` |

Final suite: **323 passed**, `ruff check` + `ruff format --check` clean (repo-wide).

## Operational close-out (all verified live)

1. **Bootstrap** — `y2d2/autonomous_task_overview` main = README.md + `plans.md` (header only); vault
   (`/workspace/Obsidian/ARP_roadmap`) commit `3bacaf2` = exactly `.gitmodules` + submodule; vault branch
   pushed; slides work left untouched.
2. **Allowlist seeded** — 9 repos in `config/workflows.yaml` (user-selected 2026-11-21).
3. **Live run #1** — exposed **T6c**: `_repo_url`/`_prompts_repo_url` built `git@github.com/<repo>.git`
   (slash) instead of `git@github.com:<repo>.git` (colon) → git treated every URL as a local path
   ("repository … does not exist" in ~3 ms, no ssh transport). Hermetic tests missed it because they all
   inject local fixture URLs via `repo_urls`/`listing_repo_url`. Fixed + byte-exact regression tests.
4. **Live run #2 (post-T6c)** — clones worked (7 repos scanned, 42 plans) but crashed on `y2d2/ARP_roadmap`
   @ `orbit-demo1-visual`: plan folder `planning/orbit-plenary-i-slides/` contains committed build artifacts
   (`build/.venv/`, ~500 binary `.pyc` + JPG/PNG). `Git.show_file` (`text=True`) raised `UnicodeDecodeError`
   (not a `GitError`) → escaped the defensive handlers → run aborted. Exposed **T6d**: plan-folder files are
   now read as raw bytes and hashed as bytes (text-folder hashes byte-identical — no identity churn);
   non-UTF-8 `work_plan.md` ⇒ folder malformed (skipped + WARNING), per the existing contract.
5. **Live run #3 (post-T6d)** — `roadmap-dev=ok(78 items, 90 actions, 0 errors)`, `gate: FORCED`:
   - 9 repos scanned: ARP_MPE 1, ARP_implementations 1, ARP_1A 2, ARP_utility_code 8, PRP_ARP_M 12,
     ARP_IMU 1, agentic_scripts 17, **ARP_roadmap 36** (binary `.venv` folder survived — T6d proven live),
     ARP_engine 0.
   - Listing pushed: `y2d2/autonomous_task_overview` main = `8070332 OC: roadmap-dev: reconcile listing
     (run 20261122T085857Z)` — remote tip verified == local `origin/main`; `plans.md` = 78 rows
     (8 repo sections, 23 branch subsections), all `☐` unapproved, state `open`.
   - Drain no-op as designed: `drain start slots=1 startable=0` → gate closed, zero runner calls.
   - `state/roadmap-dev.json` = 78 identity-keyed entries (identity/repo/branch/path/title/content_hash/
     state=open/attempt=0).

## Mechanism notes (for future operators)

- Idle probe: `~/.local/state/opencode/service.json` (url/password/pid, dynamic port) +
  `GET <url>/api/session/active` with **Basic auth user `opencode`** (Bearer → 401) → open interactive TUI
  sessions; `--standalone` job workers are invisible to it (jobs can drain even while an operator is idle-gated
  out — by design).
- Cron `*/30 * * * *` (repo ROOT) runs `uv run agentic-scripts run`; quiet window 22:00–08:00; night = 2
  drain slots, day = 1; per-job timeout 480 min. Non-forced runs with no approved rows are Phase-1-only.
- Delivery contract (user, 2026-11-21): **no PR creation, no GitHub API** — delivery = pushed attempt branch
  `roadmap-dev/<id>-<attempt>`; PR/merge is human-level verification. All git over SSH, no PAT anywhere.
- `planning/mail-keeper-pruning/*.md` (3 result reports + `work_plan.md`) are untracked foreign files —
  never staged by this orchestration; untracked ⇒ never scanned by Phase 1.

## Known follow-ups (informational, not blocking)

- Committed build-artifact dirs under a plan folder (e.g. `planning/orbit-plenary-i-slides/build/.venv/` on
  `y2d2/ARP_roadmap` @ `orbit-demo1-visual`) make that folder's content hash rebuild-sensitive: any rebuild
  changes the hash ⇒ new identity ⇒ re-approval. A future `scan_exclude_dirs` config option could address
  this if it becomes a nuisance.
- Repo-hygiene suggestion for the vault: `build/.venv` under `planning/` should not be committed.
