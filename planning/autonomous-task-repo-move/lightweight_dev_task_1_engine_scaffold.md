# lightweight-dev Output — Task: engine-scaffold

**Task:** #1    **Session:** ses_df70124b1ffeeooOoiE08oBdgz    **Date:** 2026-11-23

## Summary

Built the standalone `autonomous-task` engine package in the new persistent clone
`/workspace/Python/autonomous_task_overview` (cloned fresh from
`git@github.com:y2d2/autonomous_task_overview.git`, branch `feature/engine-move`):

- **Clone + branch** — fresh clone, `feature/engine-move` created from `main` and
  pushed with upstream tracking before any work.
- **Package scaffold** — `pyproject.toml` (hatchling, `autonomous-task` console
  script, ruff `py312`/100/`E,F,I,UP,W`, pytest testpaths, deps `pyyaml>=6` +
  `python-dotenv>=1`, NO psutil), `.gitignore` (runtime dirs; `plans.md` deliberately
  NOT ignored), `src/autonomous_task/` src layout with `__init__.py`, `__main__.py`,
  `cli.py` (thin `main()` → `runner.run` → `sys.exit`).
- **Frozen leaf copies** — `agent.py`, `git.py`, `sessions.py`, `state.py`,
  `logging_setup.py`, `workflows/__init__.py`, `workflows/base.py`,
  `workflows/roadmap_dev.py` (3,356 lines) copied with ONLY the mechanical
  `agentic_scripts` → `autonomous_task` rewrite. The plan's freeze-check
  (`diff <(sed 's/agentic_scripts/autonomous_task/g' <source>) <target>`) was run for
  all 8 files: **empty diff for every one**.
- **Trimmed config** — `src/autonomous_task/config.py` ported with `Machine`
  (no `load_threshold`), `Config` (no `workflows`/`oc_todo`/`admin_repo`),
  `load_config` requiring `machine`/`agent`/`paths` with optional `roadmap_prompts`
  (empty defaults); shipped `config/workflows.yaml` with the LIVE values from the
  source config (9-repo `allowed_repos` verbatim in order) trimmed to
  `machine`/`agent`/`paths`/`roadmap_prompts`, no `workflows:`/`oc_todo:`/`admin_repo:`.
- **New single-workflow `runner.py`** (the only new code) — `WORKFLOW_NAME`,
  `DEFAULT_CONFIG`, `GateResult(open, reason, now)`, `evaluate_idle_gate` (two-poll
  streak on `idle_gate_last_ok` in the `"scheduler"` state document, identical
  semantics to the source), `acquire_lock` (verbatim flock port), `build_parser`
  (`run` subcommand, `--force`/`--config`/`--verbose`, NO `--only`), `_gate_line`
  (exact canonical format), `_last_run_lines` (5-line format, `None` → `gate: FORCED`),
  and `run()` following the 11-step pipeline in the plan (top-level
  `from autonomous_task.sessions import read_active_sessions` seam preserved;
  per-workflow errors never change the exit code — a raised fault is mapped to a
  `WorkflowResult(status="error")` exactly as in the source scheduler).
- **Commit + push** — 17 files, 6,472 insertions, all `create mode`; committed
  `OC: Add standalone autonomous-task engine package (primitives, trimmed config,
  single-workflow runner, CLI)` and pushed to `origin/feature/engine-move`.
  `plans.md`/`README.md` untouched (never staged).

## Files

| File | Action | Why |
|---|---|---|
| `/workspace/Python/autonomous_task_overview` (repo) | create | Persistent clone of `autonomous_task_overview.git` (engine's future run location) |
| `.gitignore` | create | Ignore runtime dirs (`.venv/`, caches, `logs/`, `state/`, `sandbox/`, `.env*`); `plans.md` intentionally tracked |
| `pyproject.toml` | create | `autonomous-task` 0.1.0, `>=3.12`, `pyyaml`+`python-dotenv` (no psutil), dev extras, console script, hatchling, ruff/pytest config per plan |
| `src/autonomous_task/__init__.py` | create | One-line package docstring |
| `src/autonomous_task/__main__.py` | create | `python -m autonomous_task` entry, mirrors source |
| `src/autonomous_task/cli.py` | create | Thin `main()` delegating to `autonomous_task.runner.run`, `sys.exit(run())` |
| `src/autonomous_task/agent.py` | create | Frozen copy (mechanical rewrite only; freeze-check clean) |
| `src/autonomous_task/git.py` | create | Frozen copy (mechanical rewrite only; freeze-check clean) |
| `src/autonomous_task/sessions.py` | create | Frozen copy (mechanical rewrite only; freeze-check clean) |
| `src/autonomous_task/state.py` | create | Frozen copy (mechanical rewrite only; freeze-check clean) |
| `src/autonomous_task/logging_setup.py` | create | Frozen copy (mechanical rewrite only; freeze-check clean) |
| `src/autonomous_task/workflows/__init__.py` | create | Frozen copy (one-line docstring) |
| `src/autonomous_task/workflows/base.py` | create | Frozen copy (`Workflow`/`WorkContext`/`WorkflowResult`; freeze-check clean) |
| `src/autonomous_task/workflows/roadmap_dev.py` | create | Frozen copy, 3,356 lines, no behavioral edits (freeze-check clean) |
| `src/autonomous_task/config.py` | create | Trimmed port (drops `load_threshold`, `workflows`, `oc_todo`, `admin_repo`); source docstring style kept |
| `config/workflows.yaml` | create | Shipped LIVE config trimmed to `machine`/`agent`/`paths`/`roadmap_prompts`; 9-repo allowlist verbatim; source inline comments carried over |
| `src/autonomous_task/runner.py` | create | **New** single-workflow runner (idle gate + lock + run-id + logging + last-run), per plan spec |
| `uv.lock` | create | Byproduct of the mandatory `uv sync --extra dev`; committed so `git status` is clean (T5.1) — matches the source repo's convention of a tracked lock file |

## Build / Tests

- `uv sync --extra dev` in the clone: PASS — resolved + installed 9 packages (`autonomous-task==0.1.0` built via hatchling; env is CPython 3.14.7, satisfies `>=3.12`)
- `uv run ruff check src/`: PASS — "All checks passed!" (re-run after every stage; final run covers all 16 `src/` modules)
- `uv run python -c "import autonomous_task.workflows.roadmap_dev"`: PASS
- `uv run python -c "from autonomous_task.runner import run, evaluate_idle_gate, acquire_lock, GateResult"`: PASS
- `uv run autonomous-task run --help`: PASS — shows `run` with `--force`/`--config`/`--verbose`, zero occurrences of `--only`
- Freeze-check (plan Notes): `diff <(sed 's/agentic_scripts/autonomous_task/g' <source>) <target>` — PASS, empty for all 8 copied files
- Config load check (T3.1 one-liner): PASS — printed exactly `2 y2d2/autonomous_task_overview 9`
- End-to-end forced no-op run (T4.4), tmp config `allowed_repos: []` + tmp dirs: PASS — exit 0, log contains exact line `WORKFLOW roadmap-dev status=ok items_found=0 actions=1 errors=0`, `last-run.txt` = `run: <id>` / `trigger: force` / `gate: FORCED` / `workflows: roadmap-dev=ok(0 items, 1 actions, 0 errors)` / `overall: ok`; tmp files cleaned up afterwards
- Extra self-test — non-forced live run (gate path, 4 real active sessions): PASS — `GATE now=... active_sessions=4 verdict=CLOSED reason=4 active session(s)`, exit 0, `trigger: gate`, `overall: ok`
- Extra self-test — `evaluate_idle_gate` unit transitions (fresh `StateStore`, `gate_polls_required` 1 and 2): PASS — 1st-idle CLOSED, 2nd-in-window OPEN, active-sessions CLOSED w/ count, streak cleared after non-idle, stale gap (90 min > 30+10) resets to 1st-idle CLOSED, `polls_required=1` → OPEN `"single idle poll"`
- Extra self-test — lock-skip: PASS — while a background process held `flock` on `state/.lock`, run logged `SKIP another run is in progress`, exit 0, `overall: skipped`
- Extra self-test — config error: PASS — `--config /nonexistent.yaml` → stderr `config error: /nonexistent.yaml: configuration file not found`, exit 2
- `grep -rn "agentic_scripts" pyproject.toml .gitignore src/`: PASS — zero hits
- Repo-wide grep (excl. `.git`/`.venv`): only remaining `agentic_scripts` strings are `config/workflows.yaml:27` (`- y2d2/agentic_scripts` — the plan-mandated verbatim allowlist repo id, a data value) and text in `plans.md` (live listing, untouched)

## Acceptance Verification

| # | Criterion (verbatim) | Result | Notes |
|---|---|---|---|
| T1.1 | `git -C /workspace/Python/autonomous_task_overview status -sb` shows `## feature/engine-move...origin/feature/engine-move` with a clean tree. | PASS | After clone + `checkout -b` + `push -u`, status showed exactly `## feature/engine-move...origin/feature/engine-move` with no file lines |
| T1.2 | `git ls-remote origin HEAD` succeeds (SSH reachable). | PASS | Returned `2c0999ddf3b2f6d6241140534bff7502ae14335e  HEAD` |
| T2.1 | `uv sync --extra dev` exits 0 in the clone; `uv run ruff check src/` exits 0. | PASS | sync exit=0 (9 packages incl. built `autonomous-task==0.1.0`); ruff exit=0, "All checks passed!" |
| T2.2 | `uv run python -c "import autonomous_task.workflows.roadmap_dev"` succeeds. | PASS | **Ordering note:** first attempt (right after Task 2's own steps) failed with `ModuleNotFoundError: No module named 'autonomous_task.config'` — expected, because the frozen `agent.py` imports `config.py`, which is a Task 3 deliverable in the plan's own ordering. Re-verified verbatim after Task 3: succeeds. Criterion not weakened |
| T2.3 | `grep -rn "agentic_scripts" pyproject.toml .gitignore src/` returns zero hits. | PASS | grep exit=1 (no hits) |
| T2.4 | `plans.md` and `README.md` are untouched (`git status` shows only new files). | PASS | `git status --porcelain` showed only new untracked entries (`.gitignore`, `pyproject.toml`, `src/`, `uv.lock`, later `config/`); tracked files unmodified |
| T3.1 | `uv run python -c "from pathlib import Path; from autonomous_task.config import load_config; c = load_config(Path('config/workflows.yaml')); print(c.machine.gate_polls_required, c.roadmap_prompts.listing_repo, len(c.roadmap_prompts.allowed_repos))"` prints `2 y2d2/autonomous_task_overview 9`. | PASS | Printed exactly `2 y2d2/autonomous_task_overview 9`, exit 0 |
| T3.2 | `uv run ruff check src/` clean; zero `agentic_scripts` references in `src/`. | PASS | ruff exit=0; `grep -rn "agentic_scripts" src/` zero hits |
| T4.1 | `uv run autonomous-task run --help` prints the `run` subcommand with `--force`, `--config`, `--verbose` and NO `--only`. | PASS | Help printed `usage: autonomous-task run [-h] [--force] [--config PATH] [--verbose]`; `--only` count = 0 |
| T4.2 | `uv run python -c "from autonomous_task.runner import run, evaluate_idle_gate, acquire_lock, GateResult"` succeeds. | PASS | Clean import, exit 0 |
| T4.3 | `uv run ruff check src/` clean. | PASS | "All checks passed!" with `runner.py` present |
| T4.4 | A manual forced run with an EMPTY allowlist config (write a tmp config with `roadmap_prompts.allowed_repos: []` pointed at tmp dirs) via `uv run autonomous-task run --force --config <tmp>` exits 0 and logs `WORKFLOW roadmap-dev status=ok items_found=0 actions=1 errors=0` — proving the no-op path end-to-end without touching the live listing. (Clean up tmp files afterwards.) | PASS | Exit 0; exact line present in `run-<id>.log`; `last-run.txt` consistent (`gate: FORCED`, `overall: ok`); no listing repo contacted (empty allowlist no-ops before any git work); tmp dirs/files deleted afterwards |
| T5.1 | `git status` clean on `feature/engine-move`; `git log --oneline -2` shows the new commit; remote branch updated. | PASS | Status: `## feature/engine-move...origin/feature/engine-move` (no file lines); log shows `OC: Add standalone autonomous-task engine package (primitives, trimmed config, single-workflow runner, CLI)` above the prior listing commit; `git ls-remote origin feature/engine-move` matches the local HEAD |
| T5.2 | `plans.md` / `README.md` unchanged in the commit (`git show --stat` lists only new files). | PASS | `git show --stat` lists 17 files, all `create mode`, 6,472 insertions(+), 0 deletions; `plans.md`/`README.md` absent from the diff |

## Blockers

None.

Observations for the orchestrator (no action required; none of these weaken a criterion):

1. **Plan ordering quirk (T2.2)** — Task 2's import acceptance cannot pass before Task 3 creates `config.py`, because the frozen `agent.py` imports it. Verified as soon as the dependency existed; no deviation from the criteria.
2. **`uv.lock` committed** — it is an unavoidable byproduct of the mandatory `uv sync --extra dev`, is not covered by the spec'd `.gitignore`, and T5.1 demands a clean `git status`; the source repo also tracks its lock file. Staged explicitly (never `git add -A`). Flagging in case the plan intended it untracked (that reading is unsatisfiable with a clean status).
3. **Lock-skip `last-run.txt` renders `gate: FORCED`** — faithful port: the source scheduler also passes `gate_line=None` on the lock-skip path, and the plan's `_last_run_lines` contract maps `None` → `gate: FORCED` without specifying a distinct lock-skip format.
4. **Interpreter** — uv created the env with CPython 3.14.7 (source venv uses 3.12.3). Both satisfy the spec'd `requires-python >=3.12`; the plan specifies no `.python-version` pin. If the follow-on systemd/setup task wants parity with 3.12, add a `.python-version` pin there.
5. **Remaining `agentic_scripts` strings in the repo** — only the plan-mandated verbatim allowlist value `y2d2/agentic_scripts` in `config/workflows.yaml` (a GitHub repo id, not a package reference) and text inside `plans.md` (live listing, untouched). Zero references in `pyproject.toml`, `.gitignore`, and all of `src/`.

## Next Steps

- Task 2 of the work plan (tests) can be ported against this scaffold; the load-bearing seams are in place: top-level `read_active_sessions` import in `runner.py`, injectable `now`/`run_id` kwargs, `evaluate_idle_gate` taking the probe count as an argument, and the canonical log-line formats verified above.
- The engine can be smoke-run non-forced at any time (`uv run autonomous-task run`); with active sessions the gate will correctly stay CLOSED, and the no-op workflow is safe under an empty allowlist.
- If run-environment parity with the source project matters, consider a `.python-version` (3.12) pin in the follow-on setup task.
