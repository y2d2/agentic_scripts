# lightweight-dev Output — Task: allowlist hermetic (tests only)

**Task:** #6b    **Session:** ses_dfdf9c6ffffeAeQidcHtqniUfz    **Date:** 2026-11-22

## Summary
Kept the test suite hermetic against the operator-seeded 9-repo `roadmap_prompts.allowed_repos` in the shipped `config/workflows.yaml` (the orchestrator's uncommitted edit). Tests only — no `src/`, no `config/`, no `planning/` changes.

1. `tests/test_config.py::test_roadmap_prompts_shipped_loads` — `allowed_repos` assertion updated to the 9 seeded repos exactly as in the shipped YAML (order preserved); all other assertions untouched; stale "INERT (empty allowlist)" docstring updated to the seeded reality.
2. One-liner `data["roadmap_prompts"]["allowed_repos"] = []` (with the hermeticity comment) inserted right after the `paths` rewrite in each of the 5 shared shipped-config helpers: `tests/smoke/test_smoke_base.py::_write_config`, `tests/smoke/test_smoke_oc_todo.py::_write_config`, `tests/smoke/test_smoke_mail_keeper.py::_write_config`, `tests/smoke/test_smoke_roadmap_dev.py::_write_config`, `tests/test_scheduler.py::_write_config`.
3. Sweep found 3 additional shipped-config-copy builders driving `run()` without an allowlist override (details in Notes below): the shared `tests/conftest.py::base_config` fixture and 2 per-test inline builders in `tests/smoke/test_smoke_oc_todo.py`. Same one-liner applied to all 3.
4. Verified `test_smoke_roadmap_dev_sessions_active_no_drain` override order: it does NOT call `_write_config` — it builds its config inline and sets `allowed_repos=[FIX]` + `repo_urls`/`listing_repo_url` itself after the `paths` rewrite, so the helper one-liner cannot affect it (confirmed green).
5. Committed only the 7 modified test files (explicit paths, no `git add -A`): commit `OC: roadmap-dev T6b — keep smoke/scheduler tests hermetic with the seeded 9-repo allowlist`. `config/workflows.yaml` left modified-uncommitted in the working tree (orchestrator-owned); nothing under `planning/` staged; NOT pushed (orchestrator pushes between waves).

## Files
| File | Action | Why |
|---|---|---|
| `tests/test_config.py` | modify | `test_roadmap_prompts_shipped_loads` asserts the 9 seeded repos (in YAML order); docstring updated to match |
| `tests/smoke/test_smoke_base.py` | modify | `_write_config` forces empty allowlist — all 5 base smoke tests drive `run()` on a shipped-config copy |
| `tests/smoke/test_smoke_oc_todo.py` | modify | `_write_config` + 2 per-test inline builders (`…_config_fault`, `…_empty_repo_list_no_agent`) force empty allowlist |
| `tests/smoke/test_smoke_mail_keeper.py` | modify | `_write_config` (the shared helper behind every `run()` in the module, incl. the retry config) forces empty allowlist |
| `tests/smoke/test_smoke_roadmap_dev.py` | modify | `_write_config` (3 base-path tests) forces empty allowlist; the 2 inline builders set their own allowlists and were left untouched |
| `tests/test_scheduler.py` | modify | `_write_config` (all 13 scheduler `run()` tests, incl. `test_only_roadmap_dev_inert_noop` on shipped workflows) forces empty allowlist |
| `tests/conftest.py` | modify | `base_config` fixture (sweep find) forces empty allowlist — protects `test_roadmap_dev.py::test_run_empty_allowed_repos_is_noop` |

## Build / Tests
- `uv run pytest -v` (full suite): PASS — `318 passed in 71.92s` (baseline 318, all green)
- `env -u GITHUB_PAT uv run pytest tests/smoke/ -v`: PASS — `19 passed in 5.13s` (green + hermetic; 5s wall time with `GITHUB_PAT` unset — no test could have completed 9 SSH clones of `y2d2/…` or a push to `y2d2/autonomous_task_overview`; the only git traffic in the smoke suite is local bare-repo clones in `test_smoke_roadmap_dev_sessions_active_no_drain`)
- `uv run ruff check src tests`: PASS — `All checks passed!`
- `uv run ruff format --check src tests`: PASS — `49 files already formatted`
- git: PASS — commit `0a262c2` on `feature/roadmap-dev-workflow`, 7 files changed (+29/−3), explicit paths only; `config/workflows.yaml` + `planning/` untouched by the commit; not pushed

## Acceptance Verification
| # | Criterion (verbatim) | Result | Notes |
|---|---|---|---|
| 1. | `tests/test_config.py::test_roadmap_prompts_shipped_loads`: update the `allowed_repos` assertion to the 9 seeded repos exactly as they appear in `config/workflows.yaml` (preserve order; keep every other assertion in that test). | PASS | Order verified against `config/workflows.yaml` lines 28–36 (ARP_MPE, ARP_implementations, ARP_1A_anchored_implementations, ARP_utility_code, PRP_ARP_M, ARP_IMU, agentic_scripts, ARP_roadmap, ARP_engine); all other assertions in the test kept verbatim; test green in the 318-run |
| 2. | Hermeticity one-liner: in EACH of the 5 test modules that build a config copy from the shipped YAML via a shared helper, force an empty allowlist in that helper, right after the `paths` rewrite, with a one-line comment | PASS | One-liner `data["roadmap_prompts"]["allowed_repos"] = []` + `# hermetic: shipped allowlist is seeded; tests exercise gate/scheduler behavior, not scanning` placed immediately after the `paths` rewrite in `test_smoke_base.py`, `test_smoke_oc_todo.py`, `test_smoke_mail_keeper.py`, `test_smoke_roadmap_dev.py` (each `_write_config`), and `test_scheduler.py` (`_write_config`); `test_smoke_roadmap_dev_sessions_active_no_drain` override order verified (builds config inline, own `allowed_repos=[FIX]` after `paths` — unaffected) |
| 3. | Sweep: grep ALL of `tests/` (smoke and non-smoke) for any OTHER test that drives `run()` on a shipped-config copy WITHOUT an explicit `allowed_repos` override (e.g. per-test `yaml.safe_load(SHIPPED_CONFIG…)` builders, or helpers I missed) and apply the same one-liner where needed. Tests that set their own allowlist (fixture-based scan/pipeline tests: `tests/test_roadmap_dev_scan.py`, `tests/test_roadmap_dev_pipeline.py`, the roadmap smoke fixture test) must NOT be touched. | PASS | 3 more builders found & fixed: `tests/conftest.py::base_config` (missed helper — its consumer `test_roadmap_dev.py::test_run_empty_allowed_repos_is_noop` drives the workflow `run()` on the shipped config with no override; without the fix it would SSH-clone the 9 real repos), and the 2 per-test inline builders in `tests/smoke/test_smoke_oc_todo.py` (`…_empty_repo_list_no_agent` — forced run enters the workflow loop, one-liner load-bearing; `…_config_fault` — exits 2 at config load before any workflow, one-liner defensive/consistency). Not touched (verified safe): `test_roadmap_dev_scan.py` + `test_roadmap_dev_pipeline.py` (every run replaces `roadmap_prompts` via `dataclasses.replace` with fixture remotes/own allowlists), `test_smoke_roadmap_dev.py::test_smoke_roadmap_dev_sessions_active_no_drain` + `…_config_fault` (set own `allowed_repos`), `test_mail_keeper.py::_make_ctx` (mail-keeper-only `WorkContext`; never reads `roadmap_prompts`; no scheduler `run()`), `test_oc_todo_pipeline.py::_write_config` (minimal config built from scratch, no `roadmap_prompts` section → empty default), `test_base_noop.py` (noop workflow only) |
| 4. | Verify (in order): `uv run pytest -v` (full suite — baseline 318, must end green); `env -u GITHUB_PAT uv run pytest tests/smoke/ -v` (green, hermetic — no test may attempt an SSH clone of a `y2d2/…` repo or reach `y2d2/autonomous_task_overview`); `uv run ruff check src tests` + `uv run ruff format --check src tests` clean. If any test still touches the network, name it in Blockers rather than hacking around it. | PASS | Ran in order: full suite `318 passed in 71.92s`; smoke under `env -u GITHUB_PAT` `19 passed in 5.13s` (wall time proves no outbound git traffic — a real Phase-1 scan of 9 GitHub repos would dominate that budget); `ruff check` clean, `ruff format --check` clean. No test touches the network — nothing to name |

## Blockers
None

## Next Steps
- Orchestrator: commit `config/workflows.yaml` (the seeded-allowlist operator edit still sits uncommitted in the working tree) and push between waves; the test files are already committed locally at `0a262c2`.
- Coupling note for the record: `tests/test_config.py::test_roadmap_prompts_shipped_loads` now pins the exact 9-repo allowlist, so any future re-seed of `config/workflows.yaml` requires updating that assertion (by design — it documents the operator step).
- Optional (out of scope, not done): the `test_run_empty_allowed_repos_is_noop` comment "The shipped T1 config has roadmap_prompts.allowed_repos: []" in `tests/test_roadmap_dev.py` now rests on the `base_config` fixture's hermetic rewrite rather than the shipped value — left as-is (tests-only scope respected; the test itself was not in the change list and passes).
