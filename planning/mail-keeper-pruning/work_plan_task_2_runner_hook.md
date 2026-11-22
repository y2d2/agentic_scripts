# Task Plan: mail-keeper — runner-owned pruning of checked daily entries (Task 2/4)

**Purpose:** Wire the Task-1 prune module into `MailKeeper._run` so pruning executes on **every** run path (including no-new-mail and index-degraded runs), reports its outcome in the workflow result, and is covered by integration tests — then prove the full suite stays green.

## Objective

Modify `src/agentic_scripts/workflows/mail_keeper.py` to call `prune_daily(ctx.admin_repo)` on every non-skipped-early run (right after the `admin_repo` precheck, before the notmuch-index check), with best-effort error handling (recorded in `errors`, pipeline continues), an `actions` line when anything was pruned, and docstring updates keeping the module's documentation accurate. Add integration tests to `tests/test_mail_keeper.py` reproducing the exact user scenario: *a run with no new mail prunes checked day-file entries and deletes emptied day-files*. Success: `uv run ruff check .` clean, `uv run pytest -q` fully green (all pre-existing tests unchanged and passing), new tests pass.

## Context

- Repo: `/workspace/Python/agentic_scripts`, branch `plan/agentic-workflows`. Python ≥3.12, `uv`-managed. Lint `uv run ruff check .` (line-length 100, rules E/F/I/UP/W), test `uv run pytest -q` (testpaths `tests`).
- **Dependency (Task 1, already merged before this task starts):** `src/agentic_scripts/mail/prune.py` provides
  ```python
  @dataclass(frozen=True)
  class PruneSummary:
      entries_pruned: int
      files_touched: tuple[str, ...]
      files_deleted: tuple[str, ...]
      ids_recorded: tuple[str, ...]


  def prune_daily(vault_root: Path) -> PruneSummary: ...
  ```
  Semantics: strips `- [x]` entry blocks from `<vault_root>/mail/daily/*.md`, appends pruned msg-ids (dedup'd) to `<vault_root>/mail/daily/.pruned.jsonl`, deletes day-files left with no entries, never touches old-format (checkbox-less) files, atomic writes, stdlib-only. Import it as `from agentic_scripts.mail import prune` (package style: `mail/__init__.py` currently only has a docstring — import the submodule directly: `from agentic_scripts.mail.prune import PruneSummary, prune_daily`).
- **Target file:** `src/agentic_scripts/workflows/mail_keeper.py`. Its `_run(self, ctx)` currently starts:
  1. Precheck: `admin_repo = ctx.admin_repo`; if `None` → return `skipped`.
  2. Resolve `MAIL_INDEX_DB` / `MAIL_MAIL_ROOT` / `MAIL_OWNER_ADDRESS` / `MAIL_PROCESSED_LOG` env vars.
  3. `if not index_db.is_dir(): return skipped(...)`; then `NotmuchReader` + `reader.count("")` probe → `skipped` on `NotmuchError`; then `_resolve_account` → `skipped` if `None`.
  4. Canary → state load/validate → detection (`_detect`) → `merged = batch` → **step 5: `if not merged:` persist state, `actions.append("no new mail (...)")`, return `ok` with `items_found=0`** (this is the path that currently skips everything — pruning must happen BEFORE it) → snapshot → agent call → ok-path bookkeeping.
  - `ctx.admin_repo` is a `Path` (see `tests/test_mail_keeper.py` `_make_ctx`, which sets `data["admin_repo"] = str(admin_repo)` when provided).
  - The run wrapper `run()` maps unexpected exceptions to `status="error"`; `_run` collects `actions: list[str]` and `errors: list[str]` and returns a `WorkflowResult`.
  - Docstring convention is strict: module docstring (Purpose/Rationale/Environment/Cost note/Usage), every function has Purpose/Args/Returns(±Side Effects). The module docstring currently states the workflow "NEVER writes vault files" — that sentence must be updated to stay truthful (it writes runner-owned, git-ignored `mail/daily/**` maintenance files; it still never writes vault *content* — notes/todos — and never runs git).
- **Design decisions (fixed by the global plan — do not revisit):**
  - **Placement:** new step right after the `admin_repo is None` early-return, **before** the `index_db.is_dir()` check. Rationale: vault cleanup is independent of notmuch-index health; the defect being fixed is "cleanup never runs when there is no mail (or the index degrades)".
  - **Failure mode:** wrap the call in `try/except Exception` — on failure: `ctx.logger.error("mail-keeper prune failed: %s", exc)`, `errors.append(f"prune failed: {exc}")`, continue the pipeline (pruning is best-effort; a cleanup glitch must not block triage; but the error is surfaced — silent failure is the defect). The run's final status becomes `error` via the existing `status = "error" if errors else "ok"` logic only on the agent-`ok` path; on the no-new-mail early return, build the `WorkflowResult` including `errors` (currently the no-new-mail return omits `errors` — pass `errors=errors` there so a prune failure on that path is visible).
  - **Reporting:** when `prune_res.entries_pruned or prune_res.files_deleted`, append ONE compact action, e.g. `pruned {entries_pruned} checked entr(y/ies) ({len(files_touched)} day-file(s) touched, {len(files_deleted)} deleted, {len(ids_recorded)} id(s) recorded)`. No action line when nothing was pruned (keep no-op logs quiet).
- **Test patterns (follow exactly):** `tests/test_mail_keeper.py` — `hermetic_mail` fixture (line ~275) provides isolated MAIL_* env + a real notmuch index/maildir under `tmp_path_factory`; `_make_ctx(tmp_path, hermetic_mail, admin_repo=Path, fake_runner=...)` (line ~305) builds the shared context; `FakeRunner`-style objects record `ctx.runner.run(...)` calls (see `test_run_three_new_mail` for the non-empty-manifest pattern, `test_run_two_no_new_mail_hist_filtered_by_log` for the no-new-mail pattern). Existing tests must pass **unchanged** — new tests are appended.

## Tasks

### Task 1: Hook `prune_daily` into `MailKeeper._run`
- **Files:** `src/agentic_scripts/workflows/mail_keeper.py` (modify)
- **Do:**
  1. Import `PruneSummary, prune_daily` from `agentic_scripts.mail.prune`.
  2. Insert the prune step in `_run` immediately after the `admin_repo is None` early return (a clearly commented step, e.g. `# --- 1.5 Prune: runner-owned checkbox lifecycle — every run, incl. no-new-mail. --- #`), before the `index_db` resolution:
     - call `prune_res = prune_daily(admin_repo)` inside `try/except Exception` per the fixed failure-mode design above;
     - on success with `entries_pruned or files_deleted`: append the compact action line (fixed format above);
     - on success with nothing pruned: no action line.
  3. On the no-new-mail early return (`if not merged:`), pass `errors=errors` to `WorkflowResult` so a prune failure is reported on that path (this path currently returns without `errors`).
  4. Docstring updates (keep them truthful and in-voice): module docstring — the "NEVER writes vault files" claim → precise wording (runner-owned maintenance of git-ignored `mail/daily/**`; never vault content; never git); `_run`'s Purpose/Side Effects — mention the prune step (every run, best-effort, reported in actions/errors); `run`'s Returns note if it enumerates skip/ok/error causes.
- **Notes:** Do not change detection, cursors, processed-log, agent-call, or guardrail logic. Do not change step numbering of existing comments more than necessary (insert `1.5`). Keep the action string compact (single line, logged as part of `actions`).
- **Acceptance:**
  1. `uv run ruff check .` → clean.
  2. `uv run pytest tests/test_mail_keeper.py -q` → all pre-existing tests PASS unmodified (no edits to existing test functions — append-only for tests).
  3. A no-new-mail run against a vault containing one `- [x]` entry now prunes it (covered by the integration tests below — this is the core user scenario).

### Task 2: Integration tests (append to `tests/test_mail_keeper.py`)
- **Files:** `tests/test_mail_keeper.py` (modify — append new tests at the end; do not edit existing ones)
- **Do:** Add tests using the existing `hermetic_mail` + `_make_ctx` machinery. In each test, create day-file content under `admin_repo/mail/daily/` (use a small local helper writing the documented entry format: `- [ ]`/`- [x]` line, indented `Summary:`/`People:`/`Artifacts:`/`id:` lines, blank line between entries, `# Mail daily — <date>` header) and assert the full post-run state. **Minimum set:**
  1. **`test_no_new_mail_run_prunes_checked_entries` (the user's exact scenario):** advance the state so there is no new mail (follow the `test_run_two_no_new_mail_hist_filtered_by_log` pattern — e.g. process one message in run 1, run 2 finds nothing new). Before run 2, seed `admin_repo/mail/daily/2026-11-14.md` with 1 `- [x]` + 1 `- [ ]` entry and `admin_repo/mail/daily/2026-11-13.md` with 2 `- [x]` entries only. Run 2 → PASS: `status == "ok"`, `items_found == 0`, fake runner **not** called (no agent dispatch), `2026-11-14.md` now contains only the unchecked entry (byte-check the surviving block), `2026-11-13.md` **deleted**, `.pruned.jsonl` contains the 3 pruned msg-ids, and exactly one `actions` entry starts with `pruned 3 checked`.
  2. **`test_prune_runs_on_agent_path_too`:** non-empty manifest (follow `test_run_three_new_mail`), plus a pre-existing checked entry in a day-file; agent fake returns a minimal `ok` result with a Triage table row for the manifest id (see existing tests for the exact final-text shape `_parse_triage_classes` needs). → PASS: agent called exactly once, checked entry pruned + id recorded, normal `ok` result with both the `pruned …` action and the `agent ok …` action, processed log appended (1 record).
  3. **`test_prune_failure_is_reported_but_pipeline_continues`:** no-new-mail setup + `monkeypatch.setattr("agentic_scripts.workflows.mail_keeper.prune_daily", ...)` raising `OSError("vault locked")`. → PASS: run returns with `status == "error"`, `errors` contains a string starting `prune failed:`, and state was still persisted (`_save_state` happened — assert via the no-new-mail action being present).
  4. **`test_skip_when_no_admin_repo_skips_prune`:** `admin_repo=None` context (existing pattern) → PASS: `status == "skipped"`, and no `mail/daily` directory is created under any tmp root (assert the absence — proves pruning is not attempted without a vault).
- **Notes:** Keep each test self-contained (own `tmp_path` tree); do not depend on test execution order. Day-file fixture dates/ids should be arbitrary fixed strings (msg-ids like `test1@vault.example`).
- **Acceptance:**
  1. `uv run pytest tests/test_mail_keeper.py -q` → all tests PASS (pre-existing 16 + new 4 = 20).
  2. `uv run pytest -q` (full repo suite) → green.
  3. `uv run ruff check .` → clean.

## Out of Scope

- No changes to `prune.py` itself (if its API proves unworkable, report it as a Blocker instead of editing it).
- No skill-doc changes (Task 3), no backlog run (Task 4), no config/env additions, no `pyproject.toml` changes.
- No changes to the oc-todo / noop workflows or the scheduler.
- Commit your changes with an `OC:` prefix on `plan/agentic-workflows` and push (separate from the planner's plan-file commits).

## Notes

- [Assumption] Inserting step `1.5` before the index check means an index-degraded run (e.g. `notmuch` DB missing) still prunes and returns `skipped` with the prune action present — intended per the global plan.
- [Assumption] Passing `errors` on the no-new-mail return is a behavior change for that path only in the prune-failure case; with pruning healthy, `errors` is empty and results are byte-identical to before.
- Result report path: `planning/mail-keeper-pruning/lightweight_dev_task_2_runner_hook.md` (sub-agent-communication result-report format).
