# Work Plan: mail-keeper model-ref fix + error-text logging

**Purpose:** Restore the broken mail-keeper agent dispatch (dead provider ID in the runner's `--model`) and make workflow error text visible in run logs so the next config drift is diagnosable.

**Date:** 2026-11-15    **Branch:** `plan/agentic-workflows` (clean tree)    **Status:** awaiting dispatch

## Objective

The headless mail-keeper agent has failed on every dispatch since 2026-11-09 22:30 (exit 1, single NDJSON `error` event, ~4 s, zero work). Root cause (verified by reproduction): the provider ID in `opencode.jsonc` was renamed `openaiCompatible` → `llama-cpp` (config-repo commit `71688a5`, 2026-11-09 09:11), but `agentic_scripts` still passes the old reference — `config/workflows.yaml` → `agent.model: openaiCompatible/Qwen3.8-27B` → `opencode run ... --model openaiCompatible/Qwen3.8-27B`. After the rename that model no longer resolves; `opencode` fails instantly with `UnknownError: Unexpected server error`. Reproduction: old ref fails immediately; `--model llama-cpp/Qwen3.8-27B` runs the agent correctly.

Second defect (why the failure was invisible for 5.5 days): `scheduler.run()` logs only the *count* of `WorkflowResult.errors` (`errors=1`) — the error text (which carries the opencode error payload) is never written to `logs/run-*.log`.

End state: runner builds the resolvable `--model llama-cpp/Qwen3.8-27B`; test + docstring references synced; every workflow error string logged at ERROR level in the run log with a covering test. One commit, `OC:` prefix, pushed.

## Context

- Runner: `src/agentic_scripts/agent.py` `AgentRunner.build_command()` appends `["--model", cfg.model]` when `config.agent.model is not None`; `config/workflows.yaml` is the live source (`load_config` in `config.py`).
- Scheduler: `src/agentic_scripts/scheduler.py` `run()` workflow loop (≈L550–560) logs the canonical INFO line `WORKFLOW %s status=%s items_found=%d actions=%d errors=%d duration=%.2fs`. Tests in `tests/test_scheduler.py` assert substrings of that line (`WORKFLOW noop status=ok`, …) — keep the line byte-stable.
- `tests/test_agent.py` L94 fixture carries the dead model string; argv assertions in that file may reference it — sync all occurrences.
- `src/agentic_scripts/agent.py` `build_command` docstring (≈L133) shows `'openaiCompatible/Qwen3.8-27B'` in the example argv — stale.
- Constraint (agent-config-pattern): this task must NOT touch `opencode.jsonc` or any `agents/*.md` — the config repo is the source of truth for provider IDs; the runner only follows it.
- Consequences of the fix (orchestrator-handled, NOT in this task): 10 pending mails (since 2026-11-09 22:30) re-present on the next run; orchestrator triggers a forced run after the fix is verified.

## Tasks

### Task 1: Fix model reference + sync references + log workflow error text
- **Plan:** `work_plan_task_1_model_fix_and_error_logging.md`
- **Files:** `config/workflows.yaml`, `src/agentic_scripts/agent.py` (docstring only), `tests/test_agent.py`, `src/agentic_scripts/scheduler.py`, `tests/test_scheduler.py` (new test)
- **Acceptance (summary):** no `openaiCompatible` refs left in `config/ src/ tests/`; full `uv run pytest` green; built command carries `--model llama-cpp/Qwen3.8-27B`; a workflow's error text appears in the run log at ERROR level (new test proves it); committed `OC:` + pushed.

## Out of Scope

- `opencode.jsonc`, `agents/*.md`, skills, crontab, MCP config (config repo — separate source of truth)
- Triggering the production catch-up run (orchestrator does this after verification)
- Any change to detection/cursor/logic in `workflows/mail_keeper.py`
- Archived `planning/` docs (historical records)

## Notes

- [Assumption] `llama-cpp/Qwen3.8-27B` is the canonical ref going forward (matches `agents/mail-keeper.md` frontmatter and the current `opencode.jsonc` provider block).
- [Assumption] the runner-owned `agent.model` stays a non-null string (design intent: runner picks the model uniformly); switching to `null` (agent frontmatter) was considered and rejected as a wider behavior change.
- Risk: none material — one config string + doc/test sync + additive ERROR logging.
