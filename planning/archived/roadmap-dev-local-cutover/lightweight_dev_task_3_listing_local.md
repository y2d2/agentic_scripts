# lightweight-dev Output — Task: Listing to this repo + plans.md mirror

**Task:** #3    **Session:** roadmap-dev-local-cutover    **Date:** 2026-11-27

## Summary

Implemented the `local_listing` mirror for `roadmap-dev`: a new optional `RoadmapPrompts.local_listing: str | None` config field (default `"plans.md"`, `null` disables, `""`/non-string rejected with a `ConfigError` naming `roadmap_prompts.local_listing`), shipped as `local_listing: plans.md` in `config/workflows.yaml`. In the reconcile path, a new best-effort `RoadmapDevWorkflow._mirror_listing` writes the final rendered listing text (exact bytes, no trailing-newline divergence) to `<project root>/<local_listing>` when the file's content differs, appending the action `listing mirrored to <path>`. It runs after **every** reconcile decision — the remote-push no-op branch, the pushed path, and the retry path (using the re-reconciled rows) — so a missing/stale local mirror self-heals even while the remote listing is unchanged. Relative values resolve against `PROJECT_ROOT`, the exact same basis `_resolve_path` uses for `paths.*`. The whole block is wrapped in `try/except Exception` → `logger.error("listing mirror write failed: %s", exc)`; it never touches the run's error list and never aborts the workflow. The module docstring's old-listing-repo mention (`ARP_prompts/plans.md`) now describes the canonical listing on `y2d2/agentic_scripts` main mirrored to `<project root>/plans.md`. No `uv run agentic-scripts run` was invoked; verification was targeted import/config checks + the full pytest suite + ruff + direct helper micro-checks under a patched temp `PROJECT_ROOT` (repo working tree never gained a `plans.md`).

## Files

| File | Action | Why |
|---|---|---|
| `src/agentic_scripts/config.py` | modify | `RoadmapPrompts.local_listing` field (+ docstring, EMPTY-sentinel `None` = disabled when section absent), loader validation, pass-through in the return |
| `config/workflows.yaml` | modify | `local_listing: plans.md` line under `roadmap_prompts` with the plan's comment |
| `src/agentic_scripts/workflows/roadmap_dev.py` | modify | `_mirror_listing` helper + two call sites in `_reconcile_and_push` (no-op branch + tail), `PROJECT_ROOT` import, `_reconcile_and_push` docstring (Purpose/Side Effects), module docstring listing-location fix |

## Build / Tests

- `uv run ruff check src config`: PASS
- `uv run pytest tests/ -q`: PASS — 237 passed in 36.22s (no regression; suite still has no roadmap tests, per plan)
- Config loader micro-check (`uv run python`, shipped yaml + temp variants): PASS 6/6 — shipped config loads with `local_listing == "plans.md"`; `local_listing: null` → `None`; key absent → default `"plans.md"`; `""` → `ConfigError` naming `roadmap_prompts.local_listing`; `7` → same; dataclass default `"plans.md"`, `_EMPTY_ROADMAP_PROMPTS.local_listing is None`
- `_mirror_listing` behavior micro-check (direct helper calls, `PROJECT_ROOT` patched to temp dirs): PASS 4/4 — write-on-missing/stale with byte-exact content and `listing mirrored to <path>` action; skip (no action) when bytes equal; parent dirs created; `None` → disabled with no file written; write failure (mkdir fault) → `logger.error("listing mirror write failed: …")`, no raise, no action; absolute path passes through untouched by `PROJECT_ROOT`
- Grep checks: PASS — `grep -n "autonomous_task" src/agentic_scripts/workflows/roadmap_dev.py` empty (also `ARP_prompts` empty); docstring lines 35–36 name `y2d2/agentic_scripts` and `<project root>/plans.md`
- Commit (`OC: roadmap-dev — local_listing mirror of plans.md into project root`): PASS — stat shows exactly the three files (`config/workflows.yaml`, `src/agentic_scripts/config.py`, `src/agentic_scripts/workflows/roadmap_dev.py`); pushed to `origin/feature/roadmap-dev-workflow`
- Safety: no workflow run invoked; `strip_live_repo_workflows` guard and its call sites untouched; `/workspace/Python/autonomous_task_overview` untouched; untracked `planning/*` never staged

## Acceptance Verification

| # | Criterion (verbatim) | Result | Notes |
|---|---|---|---|
| 1. | config loads; `config.roadmap_prompts.local_listing == "plans.md"` | PASS | Shipped `config/workflows.yaml` loaded via `load_config`; asserted equality |
| 2. | `local_listing: null` loads as `None` (micro-check via a temp yaml copy) | PASS | Temp copy in `/tmp/opencode/task3_checks/null_variant.yaml` |
| 3. | non-empty-string validation raises `ConfigError` naming the field on `""` | PASS | `""` → `ConfigError` mentioning `roadmap_prompts.local_listing`; bonus: non-string (`7`) rejected too; key-absent defaults to `"plans.md"` |
| 4. | Call-site inspection: mirror block located relative to the push/no-op branch; failure cannot propagate (grep + read) | PASS | Call at the no-op early-return (`listing unchanged … — no push` → mirror → return) and at the tail after the push try/except/else (fresh `render_listing(new_rows)` covers the retry path); all IO inside `_mirror_listing`'s `try/except Exception` → `logger.error`, `errors` list never touched; confirmed by failure-injection micro-check |
| 5. | Task 2's import/config checks still pass; `uv run pytest tests/ -q` still fully green (suite has no roadmap tests yet — it must not regress) | PASS | 237 passed, 0 failed; import + loader micro-checks pass |
| 6. | `uv run ruff check src config` clean | PASS | "All checks passed!" |
| 7. | `grep -n "autonomous_task" src/agentic_scripts/workflows/roadmap_dev.py` returns nothing; docstring names `y2d2/agentic_scripts` and the local mirror | PASS | Grep empty (incl. `ARP_prompts`); module docstring now: canonical listing `plans.md` on `y2d2/agentic_scripts` main, mirror at `<project root>/plans.md`, edits effective once pushed |
| 8. | commit stat shows exactly `config/workflows.yaml`, `src/agentic_scripts/config.py`, `src/agentic_scripts/workflows/roadmap_dev.py`; pushed | PASS | Commit message `OC: roadmap-dev — local_listing mirror of plans.md into project root`; 3 files changed, 82 insertions(+), 7 deletions(-); pushed to `origin/feature/roadmap-dev-workflow` |

## Blockers

None.

## Next Steps

- Next global task: roadmap-dev test suite — add tests for `_mirror_listing` (write/skip/None/failure-swallow) and the `local_listing` loader paths; the micro-checks in `/tmp/opencode/task3_checks/` show the behaviors to codify.
- First live fire (scheduler, not this task) will create the working-tree `plans.md` mirror; the file becomes tracked once the pushed listing lands on main and is pulled — expected per the plan's `[Assumption]`.
