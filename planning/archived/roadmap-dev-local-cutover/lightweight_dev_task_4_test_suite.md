# lightweight-dev Output — Task: Port roadmap-dev test suite + local_listing mirror tests

**Task:** #4    **Session:** roadmap-dev-local-cutover    **Date:** 2026-11-27

## Summary

Ported the full roadmap-dev test suite from `/workspace/Python/autonomous_task_overview` @ `899ce44` into this repo with the `autonomous_task → agentic_scripts` token rewrite (core 51, scan 12, pipeline 13, smoke 6 tests), restored the 16 `roadmap_prompts` config-validation cases removed in `80e0820` plus 6 new `local_listing` cases, added 3 hermetic tests for the Task-3 local mirror, and landed the full suite green with lint clean.

Key wiring decisions (all fixture-level; **no `src/` behavior touched**):
- **Suite-local `base_config`**: the three `test_roadmap_dev*.py` modules define a module-local `base_config` fixture (shipped-config copy, tmp paths, `allowed_repos` seeded `[]`, `load_config` validation) that deliberately shadows `tests/conftest.py::base_config` — the shared copy strips `roadmap-dev`/`roadmap_prompts` (its guard is for scheduler-driving tests only); using it would have made the roadmap shell tests vacuous. The strip guard and its 6 existing call sites are unchanged.
- **Mirror off in the ported fixture worlds**: every ported config builder passes `local_listing=None` so the new mirror never adds a `listing mirrored to …` action note and AT's exact action-count assertions hold byte-for-byte. The mirror has its own dedicated tests.
- **Suite-wide defense guard**: `tests/conftest.py` gained an autouse fixture pinning `agentic_scripts.workflows.roadmap_dev.PROJECT_ROOT` to each test's `tmp_path`, so no test can ever write a mirror into the real repo tree (mirroring tests patch the same name to their own dir; test-local patch wins).
- **Smoke adaptations** (single-workflow AT runner → multi-workflow scheduler): `agentic_scripts.scheduler.run` with the `load=` kwarg, probe patched at `agentic_scripts.scheduler.read_active_sessions`, `MAIL_*` env isolation copied from `tests/smoke/test_smoke_base.py` (shipped mail-keeper is live), roadmap-dev entry deliberately KEPT in the config copy (seeded-empty allowlist or local bare-remotes keep it hermetic), and roadmap per-workflow summary assertions moved from `last-run.txt` (which carries only the FIRST workflow's line here) to the run log.
- **listing_repo expectations** adapted to `y2d2/agentic_scripts` (shipped delta); local_listing validation covers default `"plans.md"`, explicit string, `null`, and `""`/`"   "`/`42` → `ConfigError` naming `roadmap_prompts.local_listing`.

## Files

| File | Action | Why |
|---|---|---|
| `tests/test_roadmap_dev.py` | create | Ported core suite (51 tests) + suite-local `base_config` |
| `tests/test_roadmap_dev_scan.py` | create | Ported phase-1 integration suite (12 tests) + suite-local `base_config` |
| `tests/test_roadmap_dev_pipeline.py` | create | Ported drain/pipeline suite (13 tests) + suite-local `base_config` |
| `tests/test_roadmap_dev_listing_mirror.py` | create | NEW local_listing mirror tests (3: byte-identical mirror, null → no write, no-op-push stale-mirror self-heal) |
| `tests/smoke/test_smoke_roadmap_dev.py` | create | Ported smoke suite (6 tests), adapted to the multi-workflow scheduler |
| `tests/test_config.py` | modify | Restored the 16 roadmap_prompts validation cases + 6 local_listing cases (default/explicit/null/bad) |
| `tests/conftest.py` | modify | Autouse PROJECT_ROOT guard pinning the mirror basis to tmp_path |
| `tests/smoke/conftest.py` | — no change needed | Its autouse probe + strip-aware docstring already anticipated the roadmap re-registration (the `80e0820` "−22 lines" were docstring rewrites only) |
| `tests/test_scheduler.py` | — no change needed | The idle-gate-with-registered-workflow cases already exist here (`test_only_idle_entry_quiet_closed_still_runs` + the two idle-probe dispatch tests — 3 collected via `-k idle`, all pass); AT @ `899ce44` has no `tests/test_scheduler.py` (single-workflow runner), so this repo's synthetic-entry replacements are the canonical versions |

## Build / Tests

- `uv run pytest tests/test_roadmap_dev*.py` (core+scan+pipeline+mirror): PASS — 79 passed
- `uv run pytest tests/smoke/test_smoke_roadmap_dev.py tests/test_config.py tests/test_scheduler.py -q`: PASS — 62 passed
- Transplanted-case counts (`-k`): `roadmap_prompts` → **22 passed** in `test_config.py`; `idle` → **3 passed** in `test_scheduler.py`
- Mirror mutation proof (temporary, then reverted): stubbed BOTH `self._mirror_listing(...)` call-sites in `roadmap_dev.py` → `test_mirror_written_byte_identical_after_reconcile` and `test_mirror_rewritten_even_when_push_is_a_noop` **FAIL**, `test_mirror_not_written_when_local_listing_null` passes (correct negative control); mutation reverted (`src/` verified clean pre-commit)
- Full suite: `uv run pytest tests/ -q` → **PASS 344, 0 failed, 0 skipped** — collected-count delta **237 → 344 (+107)** = 82 ported + 3 new mirror + 22 config cases
- `uv run ruff check .` → clean
- Safety: never ran `agentic-scripts run`; `git ls-remote origin refs/heads/main` identical before/after the final full-suite run (`29e62bf0b4d216d758d69fa3d76e81358714d722`)
- Commit (message only, per protocol): `OC: Port roadmap-dev test suite (core, scan, pipeline, smoke) + local_listing mirror tests` — stat lists ONLY the 7 test files; pushed to `feature/roadmap-dev-workflow`

## Acceptance Verification

| # | Criterion (verbatim) | Result | Notes |
|---|---|---|---|
| 1. | "after Task 3, all four run with zero failures" | PASS | 82 tests across the four ported files, zero failures (token rewrite + the documented smoke/config adaptations above; renderer assertions untouched) |
| 2. | "`uv run pytest tests/test_config.py tests/test_scheduler.py -q` PASS with the transplanted cases collected (verify via `-k` counts)" | PASS | 62 passed; `-k roadmap_prompts` = 22, `-k idle` = 3; scheduler idle-gate-registered cases were already present (see Files), so nothing was missing to transplant |
| 3. | "the new tests PASS, and they demonstrably fail if the mirror call-site is stubbed out (verify once by temporary local mutation, then revert)" | PASS | 3/3 pass; both positive tests fail with both call-sites stubbed; reverted before commit (src diff verified empty) |
| 4.1 | "Full-suite pytest PASS (record collected-count delta in the result report)" | PASS | 344 passed (was 237 → +107), zero roadmap skips |
| 4.2 | "`uv run ruff check .` clean" | PASS | All checks passed |
| 4.3 | "Commit stat lists only test files; pushed" | PASS | 7 files, all under `tests/`; `planning/*` left untracked; pushed to `feature/roadmap-dev-workflow` |
| 5. | (dispatch) "`git ls-remote origin refs/heads/main` must be identical before and after your final full-suite run" | PASS | `29e62bf…` before, at full-suite time, and at push time |

## Blockers

None.

Noteworthy findings (not caused by this task):
1. **Host cron runs the live engine every 30 min on this repo** (`crontab -l`: `uv run agentic-scripts run`). The repo-root `plans.md` (untracked) appeared at 16:31:03 from the `run-20261127T163001Z` cron fire — the Task-3 mirror doing exactly its job (log: "listing mirrored to /workspace/Python/agentic_scripts/plans.md"), after the earlier 12:38–12:47 cron runs pushed the initial listing to main (origin/main = `29e62bf`, a `reconcile listing` commit predating this session). Tests wrote nothing at the real root (the conftest guard would have redirected any such write anyway).
2. **`plans.md` is neither gitignored nor tracked** at the repo root — the live mirror rewrites it every idle poll. Suggest the operator decide (gitignore it, or track it) in a follow-up — out of this task's scope (test-files-only commit).

## Next Steps

- Orchestrator: run the live verification pass whenever planned — the cron is already exercising the workflow end-to-end; consider a `.gitignore` (or tracking) decision for the root `plans.md` mirror artifact.
- No further work needed on the test suite; the ported suite is green and hermetic (fixture bare remotes, injected seams, tmp dirs, MAIL_* isolation, probe patches).
