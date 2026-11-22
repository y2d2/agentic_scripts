# Task Plan: mail-keeper — runner-owned pruning of checked daily entries (Task 1/4)

**Purpose:** Add a pure, deterministic, stdlib-only module that prunes checked (`- [x]`) entries from mail-keeper day-files, records pruned msg-ids, and deletes emptied day-files — with full unit tests. No runner wiring in this task (Task 2 does that).

## Objective

Create `src/agentic_scripts/mail/prune.py` exposing one entry point `prune_daily(vault_root: Path) -> PruneSummary` plus a frozen `PruneSummary` dataclass, implementing the mail-keeper "Checkbox Lifecycle" semantics exactly (spec below), and `tests/test_mail_prune.py` covering all enumerated behaviors. Success: `uv run ruff check .` clean and `uv run pytest tests/test_mail_prune.py -q` green; module importable with no side effects and no third-party imports.

## Context

- Repo: `/workspace/Python/agentic_scripts`, branch `plan/agentic-workflows`. Python ≥3.12, `uv`-managed venv. Lint: `uv run ruff check .` (line-length 100, rules E/F/I/UP/W). Test: `uv run pytest -q` (testpaths `tests`; run the full suite once at the end to prove no regressions).
- The `src/agentic_scripts/mail/` package already holds sibling modules `canary.py`, `reader.py`, `mail_search.py` — match their style: `from __future__ import annotations`, module docstring with Purpose/Rationale/Usage sections and doctest `# doctest: +SKIP` examples, Google-style docstrings (Purpose / Args / Returns / Side Effects) on every public function, type hints throughout, `# noqa: T201` style diagnostics only where the sibling modules use them.
- **Authoritative semantics** (ported from the global skill `mail-keeper` → `## Checkbox Lifecycle`; this becomes the single source of truth once the skill section is removed by another task — do NOT rely on the skill file at implementation time, use this spec):
  1. Target dir: `<vault_root>/mail/daily/`. Scan `*.md` files there (sorted order, deterministic). `vault_root` is the Obsidian vault (the workflow's `admin_repo`).
  2. **Old-format files are never touched:** a file that contains **no** checkbox line matching `^\s*- \[( |x)\] ` anywhere is left byte-identical (pre-rework files carry `## Run` blocks / `### <msg-id>` headings and no checkboxes).
  3. **Entry block** = one checkbox line (`- [ ]` or `- [x]`) plus its indented continuation lines (`Summary:`, `People:`, `Artifacts:`, `Draft:` + quoted lines, `id:`) — i.e., everything up to (not including) the next checkbox line or EOF.
  4. For every `- [x]` entry: extract the msg-id from the entry's `id:` line (the last line of the entry; per format it is the full RFC 5322 Message-ID **without** angle brackets — defensively strip surrounding `<>` if present), then remove the whole block.
  5. After removal, collapse runs of blank lines between surviving entries to exactly one blank line; keep the day header (`# Mail daily — <date>`) and the file's leading structure intact.
  6. **Delete rule:** a day-file left with zero entries after removal (only the day header / whitespace) is deleted.
  7. **Record rule:** append each pruned msg-id (one per line, no angle brackets) to `<vault_root>/mail/daily/.pruned.jsonl`, creating the file if absent. **Dedup:** ids already present in the file are not appended again (keeps re-runs idempotent; the file may already hold ids from earlier runs).
  8. Only `- [x]` (checked) entries are pruned; `- [ ]` (unchecked) entries are always preserved, verbatim.
  9. **Scope fence:** the function touches nothing outside `<vault_root>/mail/daily/` — never vault notes, never `todos/`, never the notmuch index, never any git binary.
- **Atomicity:** rewrite each modified day-file via temp file in the same directory + `os.replace` (an interrupted run must never corrupt a day-file). `.pruned.jsonl` is append-only; to stay crash-safe, read existing content, append new ids, and atomically replace (same dir temp + `os.replace`).
- **API shape** (spec — the exact names are load-bearing, Task 2 imports them):
  ```python
  from dataclasses import dataclass


  @dataclass(frozen=True)
  class PruneSummary:
      entries_pruned: int  # checked entry blocks removed
      files_touched: tuple[
          str, ...
      ]  # day-file basenames rewritten (checked entries removed, file kept)
      files_deleted: tuple[str, ...]  # day-file basenames deleted (emptied)
      ids_recorded: tuple[
          str, ...
      ]  # msg-ids appended to .pruned.jsonl this pass (excludes already-present ids)


  def prune_daily(vault_root: Path) -> PruneSummary: ...
  ```
  - `<vault_root>/mail/daily/` missing or not a directory → return an empty `PruneSummary` (no crash, nothing created).
  - Unexpected per-file error (e.g. unreadable file) → let it propagate to the caller (the runner, in Task 2, decides best-effort handling); do not catch-and-swallow inside the module.
- Stdlib only: `pathlib`, `re`, `os`, `tempfile`/`dataclasses`. No new dependencies, no `pyproject.toml` changes.

## Tasks

### Task 1: Implement `prune_daily` + `PruneSummary`
- **Files:** `src/agentic_scripts/mail/prune.py` (create)
- **Do:** Implement the module per the Context spec: `PruneSummary` dataclass (frozen), `prune_daily(vault_root)` with the 9 semantic rules, atomic writes, deterministic sorted iteration, docstrings in the sibling-module style, module docstring with Purpose/Rationale (note it is the runner-owned replacement for the agent-side skill step) and Usage.
- **Notes:** Entry-block parsing should be line-based (not regex over the whole file) — iterate lines, track "inside an entry" state; a checkbox line starts a block, the next checkbox line or EOF ends the previous one. Blank lines between entries belong to the *preceding* block for removal purposes but must be re-normalised (one blank line) between surviving entries. Keep the day header and any content before the first checkbox line untouched.
- **Acceptance:**
  1. `uv run ruff check src/agentic_scripts/mail/prune.py` → no findings.
  2. `python -c "from agentic_scripts.mail.prune import prune_daily, PruneSummary"` (via `uv run python`) succeeds; `PruneSummary(0, (), (), ())` is constructible (frozen dataclass).
  3. Module imports nothing beyond stdlib (`uv run ruff check` with the repo rules passes; no new imports visible in the file).

### Task 2: Unit tests
- **Files:** `tests/test_mail_prune.py` (create)
- **Do:** Write pytest tests building tiny vault trees under `tmp_path` (`vault_root/mail/daily/*.md`) and asserting on file contents, deletions, and `.pruned.jsonl` lines. Cover **at minimum** these cases (numbered; assert exact observable state, not just "no exception"):
  1. **Mixed file:** one day-file with 2 checked + 2 unchecked entries, one of the checked entries carrying a multi-line `Draft:` block (quoted lines) — PASS: both checked blocks gone, both unchecked blocks byte-identical and in original order, exactly one blank line between surviving entries, day header intact, `.pruned.jsonl` has exactly the 2 checked msg-ids (one per line), file NOT deleted, `PruneSummary == (entries_pruned=2, files_touched=("d.md",), files_deleted=(), ids_recorded=(<id1>, <id2>))`.
  2. **All-checked file:** a day-file whose only entries are all `- [x]` — PASS: file deleted (not present after run), ids recorded, `files_deleted` contains its basename, `files_touched` does not.
  3. **Old-format file untouched:** a file with `## Run` block + `### <msg-id>` headings, **no** checkbox lines — PASS: byte-identical (compare full text before/after), 0 pruned.
  4. **Idempotent second pass:** run twice on the state produced by case 1 — PASS: second `PruneSummary` fully empty, no file changes, `.pruned.jsonl` line count unchanged (no duplicate lines).
  5. **Dedup against pre-existing ids:** a checked entry whose msg-id is already a line in an existing `.pruned.jsonl` — PASS: entry still removed, `.pruned.jsonl` gains 0 lines (no duplicate), `ids_recorded` empty for that id.
  6. **Missing dir:** `prune_daily(tmp_path)` where `tmp_path/mail/daily` does not exist — PASS: empty `PruneSummary`, no directories/files created.
  7. **Unchecked-only file:** file with only `- [ ]` entries — PASS: byte-identical, empty `PruneSummary` (file not touched — do not even rewrite it).
  8. **Malformed entry (defensive):** a checked entry with no `id:` line — PASS: block still removed, no id appended, no exception.
- **Notes:** Build fixture day-file content in the exact format (checkbox line, indented `Summary:`/`People:`/`Artifacts:`/`Draft:`/`id:` lines, one blank line between entries) — reuse a small helper in the test module. Test file style: match `tests/test_mail_canary.py` / `tests/test_mail_search.py` (plain pytest, no fixtures needed beyond `tmp_path`).
- **Acceptance:**
  1. `uv run pytest tests/test_mail_prune.py -q` → all tests PASS.
  2. Full suite `uv run pytest -q` → no regressions (all pre-existing tests still pass).
  3. `uv run ruff check .` → clean across the repo.

## Out of Scope

- No changes to `mail_keeper.py`, the runner, config, or the skill doc (Tasks 2/3).
- No CLI exposure of pruning (it is a library function for the workflow).
- No git operations, no commits beyond what the dev-agent workflow requires (commit the two new files with an `OC:` prefix on `plan/agentic-workflows` and push).

## Notes

- [Assumption] Basename-only summary fields (not full paths) — the caller knows the root; keeps the summary JSON-serialisable if ever logged.
- [Assumption] `id:` extraction is best-effort and defensive (missing/malformed → no id recorded) per the "never crash on user data" property of the existing canary/reader modules.
- Result report path: `planning/mail-keeper-pruning/lightweight_dev_task_1_prune_module.md` (use the sub-agent-communication result-report format).
