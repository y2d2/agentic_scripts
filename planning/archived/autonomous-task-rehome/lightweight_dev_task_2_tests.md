# lightweight-dev Output — Task: Port + adapt roadmap-dev test suite into autonomous_task_overview

**Task:** #2    **Session:** lightweight-dev (autonomous-task-rehome)    **Date:** 2026-11-28

## Summary

Replaced the overview repo's stale (Nov-24) roadmap-dev test suite with the CURRENT evolved
suite from `agentic_scripts` (`feature/roadmap-dev-workflow` @ `745e6a9`), adapted to the
single-workflow `autonomous_task.runner`, and got the FULL suite green (96/96, zero skips).

1. **Pure files (mechanical rewrite + freeze check).** `tests/test_roadmap_dev.py` (62 tests),
   `tests/test_roadmap_dev_scan.py` (12), `tests/test_roadmap_dev_pipeline.py` (13), and the NEW
   `tests/test_roadmap_dev_listing_mirror.py` (3) were produced by the exact mechanical
   `sed 's/agentic_scripts/autonomous_task/g'` of the current sources.
   `diff <(sed 's/agentic_scripts/autonomous_task/g' <source>) <target>` is **empty for all four**.
   The evolved content (task_done_labels tests, 3-col checklist `DETAILS_*` fixtures, module-local
   `base_config` shadowing conftest with `allowed_repos=[]` + `local_listing=None`, the
   `local_listing=None` kwargs in the scan/pipeline config builders) carried in wholesale.
2. **Mirror hermeticity (the Task-1 carry-forward).** Ported the suite-wide autouse guard
   `_redirect_roadmap_mirror_root` into `tests/conftest.py` — patches
   `autonomous_task.workflows.roadmap_dev.PROJECT_ROOT` to the per-test `tmp_path`, so no test can
   ever write the repo's own `plans.md` (test-local patches in the mirror tests still win, LIFO).
   Verified `git status` shows NO `plans.md` change after the full-suite run (checked mid-suite and
   after commit). The mirror test file itself is fully hermetic: every test patches `PROJECT_ROOT`
   to a private tmp dir and builds its config from local bare remotes; no absolute
   `/workspace/Python/agentic_scripts` path exists in it.
3. **Smoke suite.** Replaced `tests/smoke/test_smoke_roadmap_dev.py` (6 tests) with the current
   source file plus the prescribed single-workflow adaptations: `from autonomous_task.runner import run`;
   patch seam `autonomous_task.runner.read_active_sessions` (autouse conftest + 3 test-local);
   `_isolate_mail_env` fixture and `import os` dropped (no mail-keeper here); `load=` kwargs dropped;
   docstrings rewritten for the single-workflow runner (no noop/mail-keeper/oc-todo skip-line or
   multi-workflow last-run assertions); the NEW source content kept — `_write_config(..., mirror_off=True)`
   seeding `local_listing: null`, test 1's `assert not (tmp_path / "plans.md").exists()`, and the
   `roadmap_prompts.local_listing = None` seeding in test 4 — while keeping this repo's stronger
   last-run assertion `roadmap-dev=ok(0 items, 1 actions, 0 errors)`.
4. **Conftests.** `tests/conftest.py`: mirror-guard fixture added (mechanical port of the source
   hunk) + a matching module-docstring paragraph; the shipped-config-based `base_config` pattern kept
   untouched (allowed_repos emptied as before). `tests/smoke/conftest.py`: **unchanged** — it already
   patches `autonomous_task.runner.read_active_sessions` with a single-workflow docstring; the source
   delta is docstring-only scheduler prose.
5. **Verified + committed.** Full suite green, ruff clean, hygiene greps clean; committed the 6
   explicit paths and pushed.

## Files

| File | Action | Why |
|---|---|---|
| `tests/test_roadmap_dev.py` | modify | Current source suite (62 tests) via mechanical rewrite; freeze-diff empty |
| `tests/test_roadmap_dev_scan.py` | modify | Current scan suite (12 tests); mechanical rewrite; freeze-diff empty |
| `tests/test_roadmap_dev_pipeline.py` | modify | Current pipeline suite (13 tests); mechanical rewrite; freeze-diff empty |
| `tests/test_roadmap_dev_listing_mirror.py` | create | NEW `local_listing` mirror suite (3 tests); mechanical rewrite; freeze-diff empty |
| `tests/conftest.py` | modify | Added autouse `_redirect_roadmap_mirror_root` (PROJECT_ROOT→tmp_path guard) + docstring paragraph |
| `tests/smoke/test_smoke_roadmap_dev.py` | modify | Current smoke suite, adapted to the single-workflow runner per the migration recipe |

(All relative to `/workspace/Python/autonomous_task_overview`.) No files in `agentic_scripts`
created/modified under `src/`, `tests/`, or `config/` — verified after the run.

Commit on `feature/rehome-final`: `4e9cc16` `OC: Port evolved roadmap-dev test suite (incl. listing-mirror) from agentic_scripts`
(6 files, +673/−79, one `create mode`). Pushed; local HEAD == `origin/feature/rehome-final`.

## Build / Tests

- Freeze-check (4 files): **PASS** — `diff <(sed 's/agentic_scripts/autonomous_task/g' <src>) <tgt>` empty, exit 0, for all four
- `uv run pytest tests/test_roadmap_dev.py tests/test_roadmap_dev_scan.py tests/test_roadmap_dev_pipeline.py tests/test_roadmap_dev_listing_mirror.py -q` (BEFORE smoke work): **PASS** — 90 passed in 40.95s
- `env -u GITHUB_PAT uv run pytest tests/smoke/test_smoke_roadmap_dev.py -q`: **PASS** — 6 passed in 1.41s
- `env -u GITHUB_PAT uv run pytest tests/ -q` (FULL suite): **PASS** — **96 passed in 33.73s, exit 0, zero skips** (62 core + 12 scan + 13 pipeline + 3 mirror + 6 smoke)
- Hygiene greps in `tests/` (`*.py`): **PASS** — zero `agentic_scripts`; no `--only`; no `load=` (beyond `safe_load`); no `MAIL_`; no scheduler patch seam (only prose, see Deviations 4)
- Seam grep: **PASS** — `autonomous_task.runner.read_active_sessions` in smoke conftest (autouse) + 3 test-local patches; `autonomous_task.workflows.roadmap_dev.PROJECT_ROOT` patched at conftest autouse + 3 test-local sites in the mirror suite
- Mirror/repo-tree hygiene: **PASS** — `git status --porcelain | grep plans.md` → empty after the pure-suite run AND after the full suite; the only working-tree entries were the 6 intended test files
- Lint: **PASS** — `uv run ruff check tests` → "All checks passed!", exit 0
- Byte-compile: **PASS** — `uv run python -m compileall -q tests`

## Acceptance Verification

| # | Criterion (verbatim) | Result | Notes |
|---|---|---|---|
| 1. | Freeze diffs — empty (or per-file justified delta list ≤ docstring/comment lines) | **PASS** | Empty for ALL FOUR pure files (`test_roadmap_dev.py`, `test_roadmap_dev_scan.py`, `test_roadmap_dev_pipeline.py`, `test_roadmap_dev_listing_mirror.py`). Smoke file is exempt (step 3 prescribes adaptation); its diff vs. the sed-rewritten source is 105 lines, all docstring/comment/import/kwarg/patch-name adaptations (see Deviations). |
| 2. | Suite — `uv run pytest tests/ -q` exit 0, ALL green | **PASS** | 96 passed in 33.73s, exit 0, zero skips ("zero skips beyond design-intended ones": there were none). |
| 3. | Mirror test — `test_roadmap_dev_listing_mirror.py` collected + passing | **PASS** | 3/3 collected and passing (`test_mirror_written_byte_identical_after_reconcile`, `test_mirror_not_written_when_local_listing_null`, `test_mirror_rewritten_even_when_push_is_a_noop`). No test wrote the repo's `plans.md` (git status clean for it, mid-run and at the end). |
| 4. | Lint — ruff clean on changed test files | **PASS** | `uv run ruff check tests` → "All checks passed!", exit 0. |
| 5. | Git — one commit on `feature/rehome-final`, pushed, clean status | **PASS** | One commit `4e9cc16` (Task 1's `d49158c` precedes it on the branch, as planned); exactly the 6 intended paths staged; pushed `d49158c..4e9cc16`; local HEAD == `origin/feature/rehome-final`; `git status --porcelain` empty after push. |

## Deviations

1. **`strip_live_repo_workflows` NOT ported to `tests/conftest.py`.** The source guard exists to strip the
   registered `roadmap-dev` workflow from shipped-config copies handed to `scheduler.run` in the multi-workflow
   scheduler suite — machinery that does not exist here (the overview's shipped `workflows.yaml` has no
   `workflows:` section at all, per Task 1 note 3, and the single-workflow runner cannot disable the engine).
   Its protection is replaced here by: conftest `base_config`'s existing `allowed_repos = []` seeding, the
   new autouse mirror-root guard, and the smoke suite's `local_listing: null` seeding. Plan step 4 authorizes
   conftest updates "ONLY where fixtures require it"; the scheduler strip is not required by any ported fixture.
2. **Smoke docstring/comment rewordings beyond the previous port.** The new source paragraph about hermeticity
   was adapted (kept: seeded allowlist + `local_listing: null` guard, now pointing at
   `tests/test_roadmap_dev_listing_mirror.py`; dropped: the mail-keeper `_isolate_mail_env` and `oc-todo`
   sentences) instead of dropped wholesale, because the mirror-off info is new and load-bearing. The test-4
   comment "the action count stays exactly the AT-era one" (foreign-repo reference) became "exactly the three
   asserted below". All kept-assertions are verbatim.
3. **`tests/conftest.py` docstring +`base_config` untouched.** Kept this repo's shipped-config `base_config`
   pattern as instructed; did not add `local_listing: null` to it — the autouse guard already makes any
   accidental mirror write land in `tmp_path`, and conftest's `base_config` is shadowed by every roadmap test
   module that could reach a reconcile anyway.
4. **One stale docstring prose line kept (freeze discipline).** `tests/test_roadmap_dev.py:86` reads
   "nothing here calls :func:`autonomous_task.scheduler.run`" — the mechanical rewrite of the source's
   `agentic_scripts.scheduler.run` prose. Same class as the previous migration's finding 2: prose-only, factually
   true here (there is no `autonomous_task.scheduler` at all), kept verbatim to hold the empty freeze diff.
   Doc-polish candidate for the docs task.

## Blockers

None. No src/ changes were made or needed — no engine bug surfaced; every ported test passed against the
Task-1 ported engine as-is.

## Next Steps

- **Task 4 (merge/cutover):** use current `main` (`e99307f`) as the merge base per Task 1's note; this task
  adds commit `4e9cc16` on top of Task 1's `d49158c` on `feature/rehome-final`.
- Optional doc polish (non-blocking, see Deviation 4): reword the `autonomous_task.scheduler.run` prose in
  `test_roadmap_dev.py:86` (and the analogous `scheduler.run` mentions in the module-local `base_config`
  docstrings of the scan/pipeline files, inherited via the same freeze contract) if a future relaxation of
  the freeze check wants overview-accurate prose.
- Cron/live runs (later tasks) will exercise the REAL mirror to the repo's `plans.md`; the test suite
  deliberately never touches it (autouse guard + per-test `local_listing: null`).
