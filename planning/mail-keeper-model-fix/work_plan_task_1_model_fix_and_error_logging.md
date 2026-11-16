# Task Plan: Fix mail-keeper model ref + log workflow errors

**Purpose:** One bounded change: make the runner's `--model` reference resolvable again and make workflow error text visible in run logs.

## Objective

`agentic_scripts` dispatches agents with `opencode run ... --model <config.agent.model>`. Since the provider ID was renamed `openaiCompatible` → `llama-cpp` in the global opencode config (2026-11-09), the live value `openaiCompatible/Qwen3.8-27B` in `config/workflows.yaml` no longer resolves — every mail-keeper dispatch dies in ~4 s with a single NDJSON `error` event (`UnknownError: Unexpected server error`, exit 1), and the error text is swallowed by the scheduler (only `errors=1` is logged). After this task: the runner passes the resolvable `llama-cpp/Qwen3.8-27B`, all stale references are synced, and every `WorkflowResult.errors` entry is logged at ERROR level in the run log, proven by a new test.

## Context

- Repo: `/workspace/Python/agentic_scripts`, branch `plan/agentic-workflows` (working tree clean).
- `src/agentic_scripts/agent.py` — `AgentRunner.build_command()`: when `config.agent.model is not None` it appends `["--model", cfg.model]` to the argv. Its docstring's Example (around line 130–134) shows the argv containing `'openaiCompatible/Qwen3.8-27B'` — stale.
- `config/workflows.yaml` — `agent:` section, line 12: `model: openaiCompatible/Qwen3.8-27B   # string or null; null = agent's own frontmatter model`. This is the live, load-bearing value.
- `tests/test_agent.py` — fixture `config` (≈L92–98) builds `Agent(..., model="openaiCompatible/Qwen3.8-27B", ...)`; the file contains argv assertions (a shim writes argv to a file) that may assert the model string — find every occurrence of `openaiCompatible` in the test file and sync them.
- `src/agentic_scripts/scheduler.py` — `run()` workflow loop (≈L543–565): after `result = wf.run(ctx)` and `result.duration_seconds = ...`, it logs the canonical INFO summary line:
  `logger.info("WORKFLOW %s status=%s items_found=%d actions=%d errors=%d duration=%.2fs", ...)`.
  `result.errors` (a `list[str]`) is currently only counted. Two earlier failure paths (ImportError at ≈L520, create() failure at ≈L528) already log error text at ERROR level — match that style.
- `tests/test_scheduler.py` — asserts substrings of the run log such as `"WORKFLOW noop status=ok"` (L132, L166, L300–302). The canonical INFO line MUST remain byte-identical; the new error logging is additive.
- Project conventions (see repo README / python-dev-loop skill): tests via `uv run pytest` from the repo root; Ruff for lint/format; Google-style docstrings. Commit prefix `OC:`; commit to the current branch and push after.
- HARD CONSTRAINT: do NOT modify `opencode.jsonc`, any `agents/*.md`, skills, or `planning/archived/**`. Do not change detection/cursor logic in `workflows/mail_keeper.py`.

## Tasks

### Task 1: Point the runner at the renamed provider
- **Files:** `config/workflows.yaml` (modify)
- **Do:** Line 12: change `model: openaiCompatible/Qwen3.8-27B` → `model: llama-cpp/Qwen3.8-27B`. Keep the trailing comment (`# string or null; null = agent's own frontmatter model`) unchanged.
- **Notes:** This is the fix. The new ref matches the live `opencode.jsonc` provider block (`"llama-cpp"` with model `Qwen3.8-27B`) and `agents/mail-keeper.md` frontmatter. Verified by the orchestrator that `opencode run --agent mail-keeper --model llama-cpp/Qwen3.8-27B` starts and responds.
- **Acceptance:**
  1. `grep -rn "openaiCompatible" config/` → no matches.
  2. `uv run pytest tests/test_config.py -q` (or the config-loading test that parses `workflows.yaml`) → PASS.

### Task 2: Sync the stale references in the test fixture and docstring (depends on #1)
- **Files:** `tests/test_agent.py` (modify), `src/agentic_scripts/agent.py` (modify — docstring only)
- **Do:**
  1. In `tests/test_agent.py`, replace every occurrence of `openaiCompatible/Qwen3.8-27B` (fixture at ≈L94 and any argv assertion) with `llama-cpp/Qwen3.8-27B`.
  2. In `src/agentic_scripts/agent.py`, update the `build_command` docstring Example's argv line: `'openaiCompatible/Qwen3.8-27B'` → `'llama-cpp/Qwen3.8-27B'`. No code change in `agent.py`.
- **Notes:** Run the file's doctest if the project runs doctests (`uv run pytest` config — check `pyproject.toml` `doctest` settings); the docstring example must stay consistent with `build_command`'s real output shape (binary, flags order, model last-but-one before the brief).
- **Acceptance:**
  1. `grep -rn "openaiCompatible" src/ tests/` → no matches.
  2. `uv run pytest tests/test_agent.py -q` → all PASS.
  3. Doctests (if run by the suite) → PASS.

### Task 3: Log workflow error text in the run log (depends on #1)
- **Files:** `src/agentic_scripts/scheduler.py` (modify), `tests/test_scheduler.py` (modify — add one test)
- **Do:**
  1. In `scheduler.py` `run()`'s workflow loop, right before the canonical INFO `WORKFLOW ...` summary line, add an additive ERROR log for each error string:
     ```python
     for err in result.errors:
         logger.error("WORKFLOW %s error: %s", entry.name, err)
     ```
     (Place it after `result.duration_seconds = time.monotonic() - t0` so ordering matches the existing per-workflow logging. Keep the canonical INFO line byte-identical — tests assert its substrings.)
  2. In `tests/test_scheduler.py`, add a focused test (follow the file's existing fake-workflow pattern, e.g. the `noop`/`slow_wf` fixtures): a workflow whose `run()` returns `WorkflowResult(status="error", errors=["agent run error: boom (duration 4s)"])`; assert the run log contains both `"WORKFLOW bad_wf status=error"` (existing canonical line) AND `"WORKFLOW bad_wf error: agent run error: boom (duration 4s)"` (the new ERROR line).
- **Notes:** Do not alter `_last_run_lines` / `last-run.txt` format (it carries counts only by design). Match the logging style of the two existing ERROR paths (ImportError ≈L520, create failure ≈L528).
- **Acceptance:**
  1. New test in `tests/test_scheduler.py` passes; existing scheduler tests (L132, L166, L300–302 assertions) still pass.
  2. `uv run pytest tests/test_scheduler.py -q` → all PASS.

### Task 4: Verify, commit, push (depends on #1–#3)
- **Do:**
  1. Full suite: `uv run pytest -q` → all green (report the counts).
  2. Lint/format per project tooling: `uv run ruff check src/ tests/` and `uv run ruff format --check src/ tests/` (or the repo's documented equivalents from README/pyproject) → clean; fix any violations you introduced.
  3. `git status` → only the five intended files modified (`config/workflows.yaml`, `src/agentic_scripts/agent.py`, `src/agentic_scripts/scheduler.py`, `tests/test_agent.py`, `tests/test_scheduler.py`) plus this task's result file. Stage ONLY those paths (explicit paths, never `git add -A`), commit with message `OC: Fix mail-keeper model ref (openaiCompatible→llama-cpp) + log workflow error text`, then `git push`.
- **Acceptance:**
  1. Full test suite green, counts reported.
  2. Lint/format clean.
  3. Commit landed on `plan/agentic-workflows` and pushed; commit message quoted in the result report.

## Out of Scope

- `opencode.jsonc`, `agents/*.md`, skills, crontab, MCP config
- Any change to `workflows/mail_keeper.py` detection/cursor/manifest logic
- Triggering a production run (orchestrator handles the catch-up run after verification)
- Archived `planning/` docs

## Notes

- [Assumption] `llama-cpp/Qwen3.8-27B` is the canonical model ref going forward (orchestrator-verified live).
- [Assumption] `agent.model` stays a non-null string (runner-owned model choice) — switching to `null` was rejected as a wider behavior change.
- The 10 pending mails are safe: failed runs advance no cursors, so the batch re-presents after this fix.
