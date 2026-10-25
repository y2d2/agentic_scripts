# Task 5h — Step-exhaustion sentinel (Run-A incident, 2026-10-25)

**Topic:** workflows-mail-keeper · **Depends on:** Task 5f · **Blocks:** the live backfill grind
**Status:** spec (pending dispatch) · **Owner:** lightweight-dev (session ses_e96dac798ffecqJlojaxBJDuxW)

## Incident (context)

Chain Run A (2026-10-25 08:40 UTC, `--force`) reported `status=ok` and advanced state +
processed log (40→50) — but the agent's final message was opencode's **step-exhaustion
boilerplate** ("CRITICAL - MAXIMUM STEPS REACHED …"), not a triage report: the agent hit the
`steps: 40` frontmatter cap (41 tool calls, 19 min, mid-triage) and opencode still exited 0.
No vault writes were made (verified: vault HEAD unchanged, only pre-existing user WIP).
**Consequence:** 10 messages (log records stamped `2026-10-25T08:59:25.458831+00:00`, all
ts ≥ 2026-10-19 15:04) were marked processed without completed triage.

**Recovery already performed by the orchestrator (documented, not code):**
- Removed exactly those 10 records from `/workspace/Obsidian/config/email-processing-log.jsonl`
  (backup: `/tmp/processed-log-backup-20261025.jsonl`); log is back at 40 records.
- Reset `state/mail-keeper.json` INBOX `back` to the floor (it had advanced to
  2026-10-19 15:04:38 = the batch's oldest entry, which would have orphaned that entry from
  re-collection); `new` and the 12-entry deferred list untouched
  (backup: `/tmp/state-backup-20261025.json`).
- Net effect: the next run re-presents exactly the failed batch (global recency: those 10 are
  the newest unprocessed).

## Change (in `src/agentic_scripts/workflows/mail_keeper.py`)

1. **New helper** `_is_step_exhausted(final_text: str | None) -> bool` (module level, near the
   other private helpers): True when the text contains (case-insensitive) `maximum steps
   reached` OR `maximum number of steps allowed` — the two stable fragments of opencode's
   step-cap boilerplate. `None`/empty → False. Docstring: explains the opencode exit-0-on-step
   cap behavior that makes this sentinel necessary (the CLI cannot distinguish
   step-exhausted success from real success by exit code).
2. **In `MailKeeper._run`**, immediately after the existing
   `if agent.status in {"error", "timeout"}:` block, add:

   ```python
   # Step-exhaustion sentinel: opencode exits 0 when the agent hits its frontmatter step cap,
   # with the boilerplate as final message. Without this check the run would be recorded ok —
   # processed log + cursors advanced — for triage that never completed (Run-A incident,
   # 2026-10-25). Treat as failure: no log append, no cursor advance, batch re-presented.
   if agent.status == "ok" and _is_step_exhausted(agent.final_text):
       errors.append(
           "agent hit its step cap (opencode exited 0 with step-exhaustion boilerplate) — "
           "treating as failure; batch re-presented next run"
       )
       return WorkflowResult(
           status="error", items_found=len(merged), actions=actions, errors=errors
       )
   ```

   (Place BEFORE `classes = _parse_triage_classes(...)` — i.e. at the top of the "Agent ok"
   section. The existing error path already writes no state/log, so placement needs no other
   change.)
3. **Docstring:** update the `run`/`_run` docstring error-conditions sentence to include
   "agent step-cap exhaustion (sentinel on the final message)".

## Tests (`tests/test_mail_keeper.py`, hermetic)

1. **`test_agent_step_exhausted_is_error`** — fake agent returns status="ok" with final_text =
   the step-exhaustion boilerplate (use the real fragment: "CRITICAL - MAXIMUM STEPS REACHED
   … maximum number of steps allowed for this task has been reached …") → assert:
   `result.status == "error"`, the error mentions the step cap, processed log UNCHANGED
   (byte-identical / same line count), and — for fresh state — no state file written.
2. **`test_is_step_exhausted_unit`** — parameterized: boilerplate → True; a normal
   "# mail-keeper Output …" report → False; `None` → False; empty → False.

## Acceptance criteria

1. `uv run pytest -q` → full suite green, **no ignores**; ruff check + format clean.
2. Both new tests pass; the existing agent-failure retry test still passes unchanged.
3. Commit purity: `mail_keeper.py` + `tests/test_mail_keeper.py` + the result file,
   `OC:`-prefixed, pushed to `plan/agentic-workflows`.
4. Result file: **Task 5h** section (incident summary + recovery record + sentinel + tests +
   commit hash) appended to
   `planning/workflows-mail-keeper/lightweight_dev_task_5_backfill_newest_first.md`.

## Out of scope

- The agent frontmatter `steps: 40 → 80` bump lives in
  `~/.config/opencode/agents/mail-keeper.md` (agent definition — user-approved separately by
  the orchestrator; NOT part of this commit).
- No changes to the agent runner (`agent.py`), skill, or config.
