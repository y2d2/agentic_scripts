# lightweight-dev Output — Task: Port roadmap_dev module + config + yaml

**Task:** #2    **Session:** roadmap-dev-local-cutover    **Date:** 2026-11-27

## Summary

Restored the `roadmap-dev` workflow into the `agentic_scripts` package, exactly as specified:

1. **Module** — `src/agentic_scripts/workflows/roadmap_dev.py` copied verbatim from the read-only
   source `autonomous_task_overview @ 899ce44`; **only** the module-path token `autonomous_task` →
   `agentic_scripts` was rewritten (20 occurrences, all pure module paths — imports of `.agent`,
   `.config`, `.git`, `.workflows.base`, `.sessions`, `.state`, plus docstring/cross-refs). No logic
   edits, no reflow; the normalized diff against the source is empty (AC-1.2).
2. **Config** — transplanted `DEFAULT_RUN_TIMEOUT_MINUTES = 480`, the frozen `RoadmapPrompts`
   dataclass (8 fields, AT's exact field set), `_EMPTY_ROADMAP_PROMPTS`, `_load_roadmap_prompts()`
   and the `Config.roadmap_prompts` wiring, adapted to this file's section layout. **Validation is
   byte-identical to AT** (verified by extracting both regions and diffing). It reuses this repo's
   existing `_REPO_ID_RE` instead of duplicating AT's copy. Absent section → empty defaults, exactly
   AT's behavior. No `local_listing` added (Task 3); `admin_repo`/`oc_todo`/`agent`/`machine`/
   `paths`/`workflows` sections untouched.
3. **YAML** — added the `roadmap_prompts:` section (9 `allowed_repos` in AT order,
   `listing_repo: y2d2/agentic_scripts`, `listing_repo_url: ""`, `listing_path: plans.md`,
   `listing_branch: main`, `run_timeout_minutes: 480`, `test_commands: {}`, `repo_urls: {}`) and the
   fourth `workflows:` entry (`enabled: true`, `module: agentic_scripts.workflows.roadmap_dev`,
   `agent: planner-enhanced`, `gate: idle`). Diff is **additions-only** — `noop`/`mail-keeper`/
   `oc-todo` byte-identical.
4. **Test-suite fix (user-approved scope extension)** — see *Blockers*: the shipped YAML became a
   live config, and every scheduler-driving test deep-copies it, so the suite executed real
   roadmap-dev runs. Added `conftest.strip_live_repo_workflows()` and applied it at all 6 shipped-config
   read sites, plus corrected the one stale shipped-config assertion. Suite is fully green.

## Files

| File | Action | Why |
|---|---|---|
| `src/agentic_scripts/workflows/roadmap_dev.py` | create | Ported module (token-rewritten, otherwise byte-identical to AT `899ce44`) |
| `src/agentic_scripts/config.py` | modify | `RoadmapPrompts` + `DEFAULT_RUN_TIMEOUT_MINUTES` + `_load_roadmap_prompts` + `Config.roadmap_prompts` + `roadmap_prompts` in `allowed_sections` |
| `config/workflows.yaml` | modify | `roadmap_prompts` section (9 repos, listing repointed) + `roadmap-dev` entry with `gate: idle` |
| `tests/conftest.py` | modify | New `strip_live_repo_workflows()` guard + applied in `base_config` |
| `tests/test_scheduler.py` | modify | Strip in `_write_config` (drives real `scheduler.run`) |
| `tests/test_config.py` | modify | Shipped workflow list now `[noop, mail-keeper, oc-todo, roadmap-dev]` + gate/agent/module assertions |
| `tests/smoke/conftest.py` | modify | Module docstring corrected (it claimed the shipped config carries no `gate: idle` workflow) |
| `tests/smoke/test_smoke_base.py` | modify | Strip in `_write_config` |
| `tests/smoke/test_smoke_oc_todo.py` | modify | Strip in `_write_config` + 2 inline config copies |
| `tests/smoke/test_smoke_mail_keeper.py` | modify | Strip in `_write_config` |

## Build / Tests

Exact commands (all from `/workspace/Python/agentic_scripts`):

| Command | Result |
|---|---|
| `uv run python -c "import agentic_scripts.workflows.roadmap_dev as m; assert callable(m.create)"` | **PASS** (exit 0) |
| `diff <(sed 's/agentic_scripts/PKG/g' src/…/roadmap_dev.py) <(sed 's/autonomous_task/PKG/g' <AT>/src/autonomous_task/workflows/roadmap_dev.py)` | **PASS** (empty) |
| `uv run python -c "from agentic_scripts.config import RoadmapPrompts, Config"` | **PASS** (exit 0) |
| `load_config(scheduler.DEFAULT_CONFIG)` on the **pre-YAML-change** yaml (section absent) | **PASS** → empty defaults, other sections unchanged |
| `load_config(scheduler.DEFAULT_CONFIG)` + `scheduler.list_enabled(cfg, None)` + `importlib.import_module(entry.module)` + `mod.create(cfg)` (new yaml) | **PASS** — 9 repos, `listing_repo == y2d2/agentic_scripts`, `gate=idle`, `agent=planner-enhanced`, `create() -> RoadmapDevWorkflow` |
| `uv run pytest tests/ -q` — **first run, before the test fix** | **FAIL** — 6 failed, 231 passed in 3014 s (see Blockers) |
| `uv run pytest tests/ -q` — **final, after the test fix** | **PASS** — **237 passed in 34.31 s**, exit 0 |
| `uv run ruff check src config tests` | **PASS** — All checks passed! |
| `uv run ruff format --check src tests config` | **PASS** — 45 files already formatted |
| `git -C <AT> status --porcelain` | **PASS** — source repo pristine at `899ce44`, never modified |
| `git ls-remote origin refs/heads/main` before/after the final suite | **PASS** — unchanged (`29e62bf` → `29e62bf`): no test can reach GitHub anymore |

The `uv run agentic-scripts run` command was **never** invoked, per the plan's prohibition. The 50 min → 34 s
suite runtime is itself the proof that 13 embedded real phase-1 runs are gone.

## Acceptance Verification

| # | Criterion (verbatim) | Result | Notes |
|---|---|---|---|
| 1.1 | `cd /workspace/Python/agentic_scripts && uv run python -c "import agentic_scripts.workflows.roadmap_dev as m; assert callable(m.create)"` exits 0 (after Task 2 lands config — if run before, expect only the `RoadmapPrompts` ImportError). | PASS | Exit 0; `create` resolves to the module's scheduler entry point. Run after the config transplant. |
| 1.2 | `diff <(sed 's/agentic_scripts/PKG/g' src/agentic_scripts/workflows/roadmap_dev.py) <(sed 's/autonomous_task/PKG/g' /workspace/Python/autonomous_task_overview/src/autonomous_task/workflows/roadmap_dev.py)` is empty. | PASS | Empty diff, re-verified after the final edit pass. Zero residual `autonomous_task` tokens. |
| 2.1 | `uv run python -c "from agentic_scripts.config import RoadmapPrompts, Config"` exits 0. | PASS | Exit 0; field set == AT's 8 fields in AT order: `allowed_repos, listing_repo, listing_repo_url, listing_path, listing_branch, run_timeout_minutes, test_commands, repo_urls`. |
| 2.2 | With the current (pre-yaml-change) `config/workflows.yaml`, config still loads unchanged (section absent → default), i.e. `uv run python -c` invoking this repo's config-load entry (as used by `cli.py`) exits 0. | PASS | Loaded via `agentic_scripts.scheduler.DEFAULT_CONFIG` (`cli.py` → `scheduler.run` → `load_config`). Absent section → `Config.roadmap_prompts == _EMPTY_ROADMAP_PROMPTS` (`allowed_repos=[]`, empty strings, `run_timeout_minutes=480`); `oc_todo`/`admin_repo`/`machine` unchanged. |
| 3.1 | Config loads with the new yaml: `uv run python -c "from agentic_scripts.config import load_config; …"` (use the real loader symbol from `config.py`) exits 0 and `config.roadmap_prompts.allowed_repos` has 9 entries, `listing_repo == 'y2d2/agentic_scripts'`. | PASS | 9 entries in AT order; `listing_repo == y2d2/agentic_scripts`; `listing_path=plans.md`, `listing_branch=main`, `run_timeout_minutes=480`, `test_commands={}`, `repo_urls={}`. |
| 3.2 | Workflow resolution: scheduler's enabled-workflow resolution (as `scheduler.list_enabled` does) imports `agentic_scripts.workflows.roadmap_dev` successfully; `roadmap-dev` entry has `gate == 'idle'`, `agent == 'planner-enhanced'`. | PASS | `list_enabled` order `[noop, mail-keeper, oc-todo, roadmap-dev]`; module imported (same `importlib.import_module` call as `scheduler.py:705`); `gate=idle`, `agent=planner-enhanced`; `create(cfg)` returns `RoadmapDevWorkflow` (constructor is side-effect-free). |
| 4.1 | `uv run pytest tests/ -q` (must be fully green — existing tests must not regress) | PASS (after approved scope extension) | Final: **237 passed, 0 failed/errors** in 34.31 s. The first run failed 6 tests; 1 was the necessarily-stale shipped-config assertion, 5 were real-network side effects of the same root cause. Fixed only after the user approved adding test files to the commit (AC-4.3 trade-off presented via the question tool). |
| 4.2 | ruff clean on changed files. | PASS | `ruff check src config tests` clean; `ruff format --check` clean. Required one autofix: ruff/isort classifies `conftest` as third-party, so `from conftest import …` sorts into the third-party block. |
| 4.3 | Commit contains exactly `src/agentic_scripts/workflows/roadmap_dev.py`, `src/agentic_scripts/config.py`, `config/workflows.yaml` (`git show --stat`); pushed. | FAIL (deviation approved) | As written this is **impossible together with AC-4.1** (see Blockers). The commit (message: *"OC: Port roadmap-dev workflow back from autonomous_task_overview (module, config, yaml entry, gate: idle)"*) contains the 3 mandated files **plus 7 test files** — the option the user explicitly chose. It is pushed to `feature/roadmap-dev-workflow` (remote tip confirmed). The 3 mandated files are all present with the specified content; `planning/*` untracked artifacts were **not** staged (explicit paths only). |

## Blockers

**1. INCIDENT — the suite pushed 23 real commits to `y2d2/agentic_scripts` `main` (user decision: report only).**

Root cause chain, verified end to end:

- Task 3's mandated YAML makes the **shipped** `config/workflows.yaml` a *live* config: `roadmap-dev`
  is `enabled: true` with `gate: idle`, and `gate: idle` **bypasses the quiet-window gate and runs on every
  non-skipped fire**, with 9 real repos and `listing_repo: y2d2/agentic_scripts`.
- Every scheduler-driving test builds its config by **deep-copying the shipped file**
  (`tests/test_scheduler.py::_write_config`, `tests/conftest.py::base_config`, `tests/smoke/*`) and hands it
  to a real in-process `scheduler.run(...)`. So each fire performed a **real phase-1 run**: clone the 9
  repos, read/reconcile the listing, **commit and push** to the real repo's `main`.
- Evidence: `main` moved `f7812e1..29e62bf` = **23 commits**, all titled
  `OC: roadmap-dev: reconcile listing (run …)`, timestamps **11:18–12:47 UTC** — the first one **5 minutes
  after** I wrote the YAML at 11:13:31 UTC. 15 authored `Test Author <author@example.test>`, 8 `OC <yd@oc.ai>`.
  Run-ids visible in the messages (`smoke-poll-1`, `mk-smoke-2a`, `poll-1`, timestamp ids) match the failing
  tests one-for-one. **Only `plans.md` was touched**; it did not exist at `f7812e1`. No attempt/plan branches,
  no agent/plan executions were spawned, no code was pushed. Local `state/` (gitignored) also received a
  `scheduler.json`/`.lock` write from one pre-fix run.
- **Fix shipped in this commit:** `conftest.strip_live_repo_workflows()` (name-based, documented) applied at
  all 6 shipped-config read sites removes `workflows.roadmap-dev` + the `roadmap_prompts` section from every
  test-owned copy. Proven by (a) the 6 previously-affected tests now passing in 8.7 s instead of minutes,
  (b) the full suite in 34 s, and (c) `git ls-remote origin refs/heads/main` **unchanged** before/after.
  `tests/smoke/conftest.py`'s existing probe patch is retained as defense-in-depth (its docstring claimed the
  shipped config carried no `gate: idle` workflow — now corrected).
- **Per your decision I made no further changes to `main` and ran nothing else against it.** State at close:
  `origin/main` = `29e62bf`, containing the workflow-generated `plans.md` (legitimate listing content a real
  first run would recreate anyway).

**2. AC-4.1 and AC-4.3 were mutually exclusive as written.** `tests/test_config.py::test_shipped_config_loads`
asserts the shipped workflow list is *exactly* `[noop, mail-keeper, oc-todo]`; the mandated 4th entry breaks it
necessarily, so a 3-file commit could not also be green. Resolved by the user's choice ("also fix tests").

**3. Minor, deliberate deviation in transplanted doc text (1 line).** In `RoadmapPrompts`' docstring the
`listing_repo` example is repointed `y2d2/autonomous_task_overview` → `y2d2/agentic_scripts`, because after
this cutover the listing lives here and the old example is misleading. Doc-example only — zero behavioral
impact; every field, default and validation branch is byte-identical to AT (diff of the extracted regions
shows only this line).

**4. Plan-placement note.** The plan said to place `roadmap_prompts:` "after `admin_repo:`/before `oc_todo:`,
mirroring the pre-removal layout"; in `git show 80e0820^:config/workflows.yaml` that section actually sits
*after* `oc_todo:`. I followed the explicit positional instruction (after `admin_repo:`, before `oc_todo:`)
and reused the pre-removal block's bytes verbatim for content/comments, taking the `roadmap-dev` entry text
from the same pre-removal file minus its now-false comment ("inert until allowed_repos is non-empty" — with
9 repos configured it is not inert). Top-level YAML section order is behaviorally irrelevant here.

**5. No missing symbols / no dependency issues.** The ported module references only `config.machine` and
`config.roadmap_prompts`, both present; no additional AT config symbols needed porting. Its non-stdlib
imports are **only** `agentic_scripts.*` (verified via AST), so no third-party dependency was added and
`pyproject.toml` was untouched.

## Next Steps

1. **Decide `main` cleanup (yours, per your choice).** Options, safest first: (a) leave as-is — the commits
   are additive, touch only `plans.md`, and hold valid listing content; (b) one additive inverse commit
   removing `plans.md` (no reset/force-push), understanding the next real run recreates it. Do not rewrite
   the pushed range.
2. **Next global task (roadmap-dev tests) must be hermetic by construction.** It must build its own configs
   with fixture repos + injected `Git`/runner/session seams — note the new `strip_live_repo_workflows` guard
   applies **only to shipped-config copies**, so it will not hide `roadmap-dev` from its own dedicated suite.
   Consider renaming the guard's lists if a second live-repo workflow ever ships.
3. **First real scheduler fire is now a real delivery.** Cron for autonomous-task was removed in Task 1, so
   nothing runs unattended; but any invocation of the CLI on this branch will run phase 1 for real
   (clone 9 repos + push `plans.md` to `main`). Worth stating explicitly in the runbook/README task.
4. **Task 3 (global plan) — `local_listing`:** the `listing_repo`/`listing_path`/`listing_repo_url` fields and
   the YAML block added here are the surface it changes; the validation function `_load_roadmap_prompts` is
   currently AT-identical and will need its own rules (and, ideally, a validation test — none exist yet,
   none are required by this task's scope).
5. **Optional hardening:** make the strip guard fail loudly (assert) if a test ever hands a
   `roadmap_prompts`-bearing config to `scheduler.run`, and/or add a CI check that no test config carries a
   live-repo workflow, so this class of incident cannot silently return.
