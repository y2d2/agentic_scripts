# Task Plan: Listing to this repo + plans.md mirror

**Task:** #3    **Session:** roadmap-dev-local-cutover

## Objective

Make `roadmap-dev` in `/workspace/Python/agentic_scripts` publish its live listing into **this repo** — remote `y2d2/agentic_scripts` main (already repointed in Task 2's yaml) — plus a local working-tree mirror `plans.md` at the project root, so the user sees and edits the listing in the repo itself.

## Context

- Prior state (Task 2, already merged on branch `feature/roadmap-dev-workflow`): `src/agentic_scripts/workflows/roadmap_dev.py` (ported from AT-OVERVIEW @ `899ce44`), `RoadmapPrompts` in `config.py` (fields: `allowed_repos`, `listing_repo`, `listing_repo_url`, `listing_path`, `listing_branch`, `run_timeout_minutes`, `test_commands`, `repo_urls`), and `config/workflows.yaml` with `roadmap_prompts.listing_repo: y2d2/agentic_scripts` and a `workflows.roadmap-dev` entry (`gate: idle`).
- Listing flow in the module: `Workflow.run` → scan → `reconcile()` renders the byte-stable per-plan-section listing → `_fetch_listing()` (remote text on `origin/<listing_branch>`, "" when absent) and `_reconcile_and_push()` (writes `listing_path` in the sandbox clone of `listing_repo`, `git add`, commit `OC: roadmap-dev: reconcile listing (run <run_id>)`, push with fetch+retry on conflict; when the rendered text equals the fetched remote text the push step is skipped as a no-op).
- `config.py` resolves relative paths (`paths.state_dir`, etc.) against a project-root basis — find how (the loader receives/derives a root or resolves relative to CWD) and reuse the exact same basis for the mirror path.
- The canonical control surface stays the **remote** listing: user edits to `plans.md` state cells (e.g. re-arming `failure` → `open`) take effect only after they commit+push — this matches how `_fetch_listing` reads. The local mirror is workflow→user, never user→workflow.
- Commit with `OC:` prefix, push; stage explicit paths only; never touch untracked `planning/*` files.

## Tasks

### Task 1: Add `local_listing` config field
- **Files:** `src/agentic_scripts/config.py`, `config/workflows.yaml`.
- **Do:** add `local_listing: str | None` to `RoadmapPrompts` (default `"plans.md"`). Loader: key `local_listing` optional; value must be a non-empty string or `null` (validate like sibling fields; document in the dataclass docstring: relative paths resolve against the same project-root basis as `paths.*`; `null` disables the local mirror). In `config/workflows.yaml` under `roadmap_prompts:` add `local_listing: plans.md` with a one-line comment (`# also mirror the listing into <project root>/plans.md; null disables`).
- **Acceptance:** config loads; `config.roadmap_prompts.local_listing == "plans.md"`; `local_listing: null` loads as `None` (micro-check via a temp yaml copy); non-empty-string validation raises `ConfigError` naming the field on `""`.

### Task 2: Write the mirror in the reconcile path
- **Files:** `src/agentic_scripts/workflows/roadmap_dev.py`.
- **Do:**
  1. In the run/reconcile path where the rendered listing text is final (after `_fetch_listing` + `reconcile` decision, around `_reconcile_and_push`), if `settings.local_listing` is set and the file's current content differs from the rendered text, write the rendered text to `<project root>/<local_listing>` (create parent dirs if missing — they exist). Add action string `listing mirrored to <path>` to the workflow's actions list when a write happened.
  2. Wrap the mirror block in `try/except Exception as exc:` → `logger.error("listing mirror write failed: %s", exc)` and continue; it must never add to the run's error count or abort the workflow.
  3. The mirror must update even when the remote push was a no-op (listing unchanged remotely but mirror missing/stale locally).
- **Notes:** keep byte-stability (same rendered text as pushed); no trailing-newline divergence — write exactly the rendered text. Do not commit the local mirror file from the workflow (no git ops on the working tree).
- **Acceptance:**
  1. Call-site inspection: mirror block located relative to the push/no-op branch; failure cannot propagate (grep + read).
  2. Task 2's import/config checks still pass; `uv run pytest tests/ -q` still fully green (suite has no roadmap tests yet — it must not regress).
  3. `uv run ruff check src config` clean.

### Task 3: Docstring accuracy
- **Files:** `src/agentic_scripts/workflows/roadmap_dev.py`.
- **Do:** update module docstring mentions of the old listing location (`ARP_prompts/plans.md`, the autonomous_task_overview listing repo) to describe the new destination: canonical listing on `y2d2/agentic_scripts` main at `plans.md`, mirrored to `<project root>/plans.md` (user edits must be pushed to be picked up).
- **Acceptance:** `grep -n "autonomous_task" src/agentic_scripts/workflows/roadmap_dev.py` returns nothing; docstring names `y2d2/agentic_scripts` and the local mirror.

### Task 4: Commit + push
- **Do:** commit only the changed files: `OC: roadmap-dev — local_listing mirror of plans.md into project root` ; push.
- **Acceptance:** commit stat shows exactly `config/workflows.yaml`, `src/agentic_scripts/config.py`, `src/agentic_scripts/workflows/roadmap_dev.py`; pushed.

## Out of Scope

- Behavior of the remote push/retry logic (unchanged).
- Tests for the mirror (next global task).
- Any real run of the workflow (`uv run agentic-scripts run` — forbidden; could spawn executions).

## Notes

- `[Assumption]` Writing an untracked/modified `plans.md` into the working tree is desired UX even while the repo sits on a feature branch; the file becomes tracked when merged/pulled from main where the workflow's pushed listing lands.
