# lightweight-dev Output — Task: 6d binary scan safety

**Task:** #6d    **Session:** ses_dfda056a3ffeMRrTCsqLGIpZYc    **Date:** 2026-11-22

## Summary

Made the roadmap-dev plan-folder scan **binary-safe** so a plan folder containing
binary assets (images, committed `.pyc` build artifacts) can no longer crash the run
with a `UnicodeDecodeError` escaping the defensive `except GitError` handlers.

- **`git.py`** — added `Git.show_file_bytes(repo, ref, path) -> bytes`: identical
  `git -C <repo> show <ref>:<path>` argv + local timeout as `show_file`, but
  `text=False` and returning `proc.stdout` verbatim (no decode, **no rstrip** — a
  blob's trailing newlines are content). `GitError` handling is identical. `show_file`
  is unchanged (text form for `_fetch_listing` + OC-todo). To support a binary capture
  the shared `_run` gained a `binary` flag and `_check` tolerates bytes stderr (decoded
  for the error tail).
- **`roadmap_dev.py`**
  - `plan_folder_hash` now takes `file_contents: dict[str, bytes]` and updates the
    digest with the raw bytes (no `.encode("utf-8")`). Same sha256, same sorted
    `(relpath, content)` order, same NUL separators, same `DIAGNOSTIC_FILES` skip —
    so a text-only folder hashes **byte-identical** to the old text-based value.
  - `PlanEntry.file_texts: dict[str, str]` → `file_contents: dict[str, bytes]`.
  - `discover_plans` passes `entry.file_contents`.
  - `_scan_repo` reads `work_plan.md` and every folder file via `show_file_bytes`
    (no decode on the hash path). `work_plan.md` is decoded UTF-8 in a
    `try/except UnicodeDecodeError`; on failure it logs a WARNING
    (`… is not valid UTF-8 — treating folder as malformed`) and sets
    `work_plan_text = None` so the folder is skipped as malformed. The existing
    `except GitError` "cannot read / treating as absent" handlers are preserved.
  - Docstrings updated (binary-safe read, raw-byte hash input, malformed rule).
- **Tests** — converted every existing `PlanEntry(...)` / `plan_folder_hash(...)` call
  from `str` to `bytes`, and added the three T6d regression tests (pure-core binary
  hash; scan of a binary-asset folder; non-UTF-8 `work_plan.md` skipped with WARNING).
  No existing test asserted a specific hash hex value, so no asserted value changed
  (byte-stable property holds).

## Files

| File | Action | Why |
|---|---|---|
| `src/agentic_scripts/git.py` | modify | Add `show_file_bytes` (binary-safe read, no rstrip); `_run`/`_check` support binary capture; module + class docstrings. |
| `src/agentic_scripts/workflows/roadmap_dev.py` | modify | `plan_folder_hash` raw-bytes signature; `PlanEntry.file_contents`; `discover_plans`; `_scan_repo` byte reads + non-UTF-8 `work_plan.md` malformed handling + docstrings. |
| `tests/test_roadmap_dev.py` | modify | Convert `PlanEntry`/`plan_folder_hash` inputs to bytes; add `test_plan_folder_hash_binary_bytes_are_byte_stable`. |
| `tests/test_roadmap_dev_scan.py` | modify | Add binary-asset + non-UTF-8 fixture builders, `_write_bytes`, `logger` seam in `_ctx`, and the two scan regression tests. |
| `tests/test_roadmap_dev_pipeline.py` | modify | Update the two `plan_folder_hash` mirror sites to `text.encode("utf-8")` (raw-byte scan input, no rstrip) + comments. |

## Build / Tests

- `uv run pytest -v`: **PASS** — 323 passed (baseline 320 + 3 new T6d tests), 0 failed, 0 errors.
- `uv run ruff check src tests`: **PASS** — "All checks passed!"
- `uv run ruff format --check src tests`: **PASS** — "49 files already formatted".

## Acceptance Verification

| # | Criterion (verbatim) | Result | Notes |
|---|---|---|---|
| 1. | `uv run pytest -v` — current baseline is 320 passed; expect 320 + your new tests, all green. | PASS | 323 passed = 320 baseline + 3 new T6d tests. |
| 2. | `uv run ruff check src tests` — clean. | PASS | "All checks passed!" |
| 3. | `uv run ruff format --check src tests` — clean. | PASS | "49 files already formatted". |

Supporting checks (from the fix spec):
- Pure-core binary hash is byte-stable and equals the independently computed
  NUL-separated sha256 of `{"work_plan.md": b"# A\n", "data/blob.bin": <9 raw bytes>}`;
  64-char hex; stable across dict orderings — PASS.
- Scan of a folder with a binary asset discovers exactly 1 plan, no exception, and the
  `content_hash` is identical across two scan passes — PASS.
- Non-UTF-8 `work_plan.md` → no exception, folder skipped (0 plans, no state entry),
  WARNING logged (asserted via `caplog`) — PASS.
- Out of scope respected: `Git.show_file` unchanged; OC-todo untouched; no build-artifact
  dir exclusions added; `config/`, `scripts/`, `planning/` untouched.

## Blockers

None.

## Next Steps

- **(informational)** Committed build-artifact dirs under plan folders (e.g.
  `y2d2/ARP_roadmap` @ `orbit-demo1-visual` → `planning/orbit-plenary-i-slides/build/.venv/`)
  now make that folder's hash sensitive to rebuilds — every rebuild changes the folder's
  `content_hash` (and thus its identity + listing row). A future `scan_exclude_dirs`
  config option could be considered if that becomes a nuisance; it is a policy decision
  deliberately out of scope for this fix.
- Commit is on `feature/roadmap-dev-workflow` (not pushed — the orchestrator pushes
  between waves).
