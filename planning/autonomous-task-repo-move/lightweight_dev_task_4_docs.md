# lightweight-dev Output — Task: WORKFLOW.md + VARIABLES.md + README update

**Task:** #4    **Session:** ses_df5df4913ffen67T0VvLsLfXeq    **Date:** 2026-11-24

## Summary

Docs-only task in `/workspace/Python/autonomous_task_overview` (branch `feature/engine-move`).
Created `WORKFLOW.md` (pipeline split table with all 25 Context-§2 steps attributed
script/LLM — 22 script + 3 LLM — plus the dedicated boundary-rule subsection, the
where-each-side-runs section, and the failure-modes table), created `VARIABLES.md`
(sections A–G transcribed from the plan's verified tables, all values re-confirmed
against `config/workflows.yaml` and the code before writing), and reframed the README
top (single-home statement, "Running the engine" commands, pointers to the two new
docs) while leaving the entire plan-authoring guide below intact. Every code reference
cited in the docs was grepped and confirmed to resolve to a real symbol; no file under
`src/`, `tests/`, `config/`, `scripts/`, or `systemd/` was touched; `plans.md` was never
modified or staged. Committed and pushed as `OC: Add WORKFLOW.md (scripts-vs-LLM split)
+ VARIABLES.md (first proposal) + README home update`.

Corrections vs. the plan's proposal (code wins), both recorded here:

1. **Section G location.** The plan located the agent knobs in `~/.config/opencode/agents/`.
   Reality: `agents/*.md` carries only identity + behavior (name/description/icon/tags/mode);
   the model + sampling knobs live in the agent entries of `~/.config/opencode/opencode.jsonc`
   (`planner-enhanced`: model `llama-cpp/{file:active-model.txt}`, temperature `1.0`, top_p `0.95`;
   `lightweight-dev`: same model slot, temperature `0.7`, top_p `0.80`, `enable_thinking: false`,
   `presence_penalty: 1.5`), and the slot file `active-model.txt` resolves to `Qwen3.8-27B`.
   `VARIABLES.md` §G documents this accurate split; the knob *values* match the plan exactly.
2. **`job_join_timeout_seconds` constant name.** The plan's Context wrote the bare name; the
   actual module constant is `_JOB_JOIN_TIMEOUT_SECONDS = 15` (`roadmap_dev.py:138`). The Where
   cell cites the exact name. (No value change.)

Everything else matched: all `config/workflows.yaml` values (machine/agent/paths/
roadmap_prompts, incl. the live 9 `allowed_repos`, which are listed by name in §C),
`_AGENT_NAME = "planner-enhanced"` (`roadmap_dev.py:134`), `_TESTS_GATE_TIMEOUT_SECONDS = 600`
(`:143`), `_slots` hardcoding 1/2 (`:2421`, returns 2 in `quiet_window` else 1), the brief text
"Dispatch @lightweight-dev ONE small self-contained task" (`render_brief`, `:1523`), cron `*/30`
(`scripts/setup.sh:171`), systemd `OnCalendar=*:0/30`, `--force` (`cli.py`), sandbox layout,
state values, `_STATE_VERSION = 1`, `LISTING_COLUMNS`, `ARCHIVED_SEGMENT`, `DIAGNOSTIC_FILES`.

## Files

| File | Action | Why |
|---|---|---|
| `/workspace/Python/autonomous_task_overview/WORKFLOW.md` | create | Operator analysis: scripts-vs-LLM pipeline split, boundary rule, run locations, failure modes |
| `/workspace/Python/autonomous_task_overview/VARIABLES.md` | create | First-proposal variable catalogue (sections A–G), values verified against code/config |
| `/workspace/Python/autonomous_task_overview/README.md` | modify | Top reframed to "single home" + "Running the engine" + doc pointers; plan-authoring guide kept intact |
| `/workspace/Python/agentic_scripts/planning/autonomous-task-repo-move/lightweight_dev_task_4_docs.md` | create | This result report |

## Build / Tests

- `uv run pytest -q` (post-commit, in the overview clone): **PASS** — 81 passed in 33.87 s.
- Symbol grep sweep for every WORKFLOW.md code reference (`evaluate_idle_gate`, `acquire_lock`,
  `active_session_count`, `_reap_orphans`, `_scan_and_reconcile`, `discover_plans`, `plan_identity`,
  `plan_folder_hash`, `parse_listing`, `render_listing`, `reconcile`, `_reconcile_and_push`, `_slots`,
  `_select_startable`, `_start_job`, `branch_name`, `render_brief`, `_route_job`,
  `extract_report_sections`, `job_status_from_report`, `_route_success`, `_commit_diag`, `AgentRunner`,
  `StateStore`, `_TESTS_GATE_TIMEOUT_SECONDS`, `_JOB_JOIN_TIMEOUT_SECONDS`, `_AGENT_NAME`,
  `LISTING_COLUMNS`): **PASS** — all resolve in `src/autonomous_task/`.
- Attribution audit (extracted every split-table row + its "Executed by" cell): **PASS** —
  22 script rows + 3 LLM rows, exactly matching the plan's list.

## Acceptance Verification

| # | Criterion (verbatim) | Result | Notes |
|---|---|---|---|
| 1.1 | "Every step in the list in Context §2 appears in the split table, attributed exactly as specified (script steps never marked LLM and vice versa)." | PASS | All 25 rows present; mechanical extraction confirmed 22 script / 3 LLM (plan review, task execution, acceptance-criteria verification + result reports), matching the plan's bold attributions. |
| 1.2 | "The boundary rule sentence \"the LLM never commits or pushes; the script never makes implementation decisions\" (or a verbatim-equivalent) appears as a dedicated subsection." | PASS | `## The boundary rule`, bold sentence verbatim, plus the consequence (human PR is the final gate; engine never opens PRs). |
| 1.3 | "All code references (module + function names) resolve to real symbols in `src/autonomous_task/` (spot-check by grep)." | PASS | Full grep sweep (see Build / Tests) — every cited module + function found. |
| 2.1 | "All 7 sections (A–G) present with the tables above; every \"Where\" cell matches the code (spot-check: `_AGENT_NAME` is a constant in `roadmap_dev.py`; `_TESTS_GATE_TIMEOUT_SECONDS = 600` is a module constant; `_slots` hardcodes 1/2)." | PASS | Sections A–G all present with the plan's tables. Spot-checks: `_AGENT_NAME = "planner-enhanced"` (`roadmap_dev.py:134`), `_TESTS_GATE_TIMEOUT_SECONDS = 600` (`:143`), `_slots` returns 2 in quiet window / 1 by day, hardcoded (`:2421`). All config cells match `config/workflows.yaml` exactly; the 9 `allowed_repos` listed by name. Two accurate-name corrections noted in Summary (§G knob location; `_JOB_JOIN_TIMEOUT_SECONDS`). |
| 2.2 | "The intro states the documentation-first stance (no code refactor implied)." | PASS | Intro: "documentation-first proposal … implies no code refactor — the code keeps its current constant/config split"; "proposal: promote" markers kept as documentation. |
| 3.1 | "The README states the repo is the full home of the autonomous task (engine + docs + listing) in the first section." | PASS | Lead paragraph "**single home of the autonomous task**" + "What this repo is" bullets: engine / operator docs / `plans.md` listing; old `agentic_scripts` home noted as mail-keeper/oc-todo only. |
| 3.2 | "A \"Running the engine\" section exists with the exact commands above." | PASS | `## Running the engine` with `bash scripts/setup.sh` (30-min timer), `bash scripts/setup.sh --skip-timer`, `uv run autonomous-task run`, `uv run autonomous-task run --force`. |
| 3.3 | "The plan-authoring material (state machine, user-owned cells, PR flow) remains present (grep the key terms: `open`, `pending`, `review`, `success`, `failure`, `approval`, `priority`)." | PASS | Grep counts: open 10, pending 1, review 5, success 5, failure 6, approval 6, priority 5; "State machine", detail-row paragraph, and the PR-flow bullets all intact — the diff touches only the top framing (README diff: +26/−5, all above "## How to write a plan"). |
| 4.1 | "Clean tree on `feature/engine-move`; pushed; `plans.md` untouched; suite still green (`uv run pytest -q` — docs shouldn't affect it, but verify the repo is not left in a broken state)." | PASS | After push: `nothing to commit, working tree clean`, up to date with origin. Commit contains exactly the 3 doc files (`git diff HEAD~1 --stat`); last `plans.md` change remains the engine's `OC: roadmap-dev: reconcile listing (run 20261123T150001Z)`. `uv run pytest -q`: 81 passed. |

## Blockers

None.

## Next Steps

- Orchestrator: this commit is `OC: Add WORKFLOW.md (scripts-vs-LLM split) + VARIABLES.md
  (first proposal) + README home update` on `feature/engine-move` (referenced by message per
  protocol). Ready for Task #5 (merge/cutover check).
- If a follow-up ever promotes `day_slots`/`night_slots`, `tests_gate_timeout_seconds`, or
  `worker_agent` to config, update `VARIABLES.md` §A/§B "Where" cells accordingly.
