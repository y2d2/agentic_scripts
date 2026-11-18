# Task Plan: mail-keeper — runner-owned pruning of checked daily entries

**Purpose:** Fix the mail-keeper workflow so checked (`- [x]`) day-file entries are pruned and emptied day-files deleted on **every** scheduled run — including runs with no new mail — instead of only inside the (sometimes hallucinating) LLM agent step.

## Objective

The mail-keeper workflow's "Checkbox Lifecycle" (prune `- [x]` entries from `mail/daily/*.md`, record their msg-ids in `mail/daily/.pruned.jsonl`, delete day-files left with no entries) exists **only** as an instruction in the agent's skill. The runner (`src/agentic_scripts/workflows/mail_keeper.py`, `_run` step 5) invokes the agent **only when the manifest batch is non-empty** — so when no new mail arrives, no agent runs and nothing is ever pruned. Observed consequence: 82 checked entries accumulated across 12 day-files, one all-checked day-file (`2026-11-14.md`) never deleted, `.pruned.jsonl` frozen at 2 lines since Nov 12. A second, proven defect: run `20261117T223001Z` *reported* "49 entries pruned … appended to .pruned.jsonl" without doing either (mtimes + content prove no write happened) — pruning claims by the agent are unverifiable and unreliable.

End state: pruning is deterministic runner-side code, executed on every run path (no-new-mail, index-degraded, agent-run), with tests; the agent-side pruning instruction is removed from the skill (user decision 2026-11-18: runner-only); the 82-entry backlog is cleared by a forced run with before/after verification.

## Context

- Repo: `/workspace/Python/agentic_scripts`, branch `plan/agentic-workflows` (clean tree, up to date). Python ≥3.12, `uv`-managed; lint `uv run ruff check .` (line-length 100, rules E/F/I/UP/W), test `uv run pytest -q` (testpaths `tests`).
- Heavy docstring convention: every function carries a Purpose/Args/Returns (±Side Effects) Google-style docstring; module docstrings document env surface and design rationale. New code must match.
- The workflow already writes one vault-owned file (`config/email-processing-log.jsonl` via `_append_processed_log`) — writing `mail/daily/**` (git-ignored, local-only per vault `.gitignore` line `mail`) is consistent; the workflow still never writes vault *content* (notes/todos) and never runs git.
- Authoritative pruning semantics = the current `## Checkbox Lifecycle` section of `/root/.config/opencode/skills/mail-keeper/SKILL.md` (scan all `mail/daily/*.md`; strip each `- [x]` entry block = checkbox line + indented continuation lines incl. inline draft, up to next checkbox line or EOF; collapse blanks to one separator; append full msg-id from the entry's `id:` line to `mail/daily/.pruned.jsonl`; delete any day-file left with no entries; **old-format files with no checkbox lines are never touched**; vault notes/todos never removed).
- Test patterns: `tests/test_mail_keeper.py` has 16 tests; `hermetic_mail` fixture (line 275) isolates MAIL_* env; `_make_ctx(...)` (line ~305) builds a WorkContext with an `admin_repo` tmp dir and a fake runner. New tests must follow these patterns and leave existing tests passing unchanged.
- CLI for task 4: `uv run agentic-scripts run --force --only mail-keeper` (`--force` bypasses the gate; `--only` limits to the named workflow).
- Vault under test/operation: `/workspace/Obsidian/ARP_roadmap` (`admin_repo` in `config/workflows.yaml`).
- Commit policy (both repos): `OC:` prefix, commit to current branch, push after. agentic_scripts: `plan/agentic-workflows`. Skill repo `/root/.config/opencode`: `feature/flash-llamacpp-provider` (clean tree).

## Tasks

### Task 1: Deterministic prune module + unit tests
- **Files:** `src/agentic_scripts/mail/prune.py` (create), `tests/test_mail_prune.py` (create)
- Self-contained spec: `work_plan_task_1_prune_module.md`
- No dependency on other tasks.

### Task 2: Runner hook in MailKeeper + integration tests (depends on #1)
- **Files:** `src/agentic_scripts/workflows/mail_keeper.py` (modify), `tests/test_mail_keeper.py` (modify — append tests)
- Self-contained spec: `work_plan_task_2_runner_hook.md`

### Task 3: Skill doc — remove agent-side pruning (parallel with #1)
- **Files:** `/root/.config/opencode/skills/mail-keeper/SKILL.md` (modify, separate git repo)
- Self-contained spec: `work_plan_task_3_skill_doc.md`
- Independent of Tasks 1/2 (different repo, different files) → schedule in parallel with Task 1.

### Task 4: Forced backlog cleanup + end-to-end verification (depends on #2)
- **Files:** none in git (operational run + vault state verification)
- Self-contained spec: `work_plan_task_4_backlog_cleanup.md`

## Scheduling

| Batch | Tasks | Why |
|---|---|---|
| 1 (parallel) | #1 + #3 | No shared files/repos; #3 is a doc edit in a separate repo |
| 2 (consecutive) | #2 | Imports and tests #1's module; modifies `mail_keeper.py` after #1 exists |
| 3 (consecutive) | #4 | Needs #2's hook in place; verifies the exact user scenario end-to-end and clears the backlog |

## Out of Scope

- No change to detection/cursors/processed-log/backup-guardrail behavior (existing tests must pass unchanged).
- No agent model/prompt changes beyond the skill doc edits in Task 3.
- No migration of old-format (pre-checkbox) day-files; they are never pruned (skill rule, preserved).
- No new config/env variables; pruning path is derived from `admin_repo` (`mail/daily/`).
- No git operations on the vault by the runner (day-files are git-ignored; pruning produces no git activity).
- No changes to `pyproject.toml` (no new dependencies — stdlib only).

## Notes

- [Assumption] Pruning placement: right after the `admin_repo` precheck and **before** the notmuch-index check, so vault cleanup still runs on index-degraded runs. Rationale: the reported failure mode is "cleanup never happens when there is no mail"; coupling cleanup to index health would reintroduce it.
- [Assumption] Prune failure is best-effort: recorded in `errors` (surfaced as run status `error`) but the mail pipeline continues — a vault-cleanup glitch must not block triage, and silent failure is the defect being fixed. Documented in Task 2 spec.
- Risk: live forced run (Task 4) touches real user data — mitigated by pre/post counts in the spec, atomic writes, and the fact that `mail/daily/**` is git-ignored local-only (durable audit remains processed log + commit messages). Expected run: no new mail → no agent dispatch → ~10 s.
- Result files: `lightweight_dev_task_<N>_<desc>.md` in this folder.
