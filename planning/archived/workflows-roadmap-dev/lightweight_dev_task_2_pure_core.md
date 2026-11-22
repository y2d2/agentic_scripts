# lightweight-dev Output — Task: roadmap_dev pure core (identity, discovery, listing, reconciler, reaper, renderers)

**Task:** #2    **Session:** ses_e004cab4cffe0zpNt4jS9UB68L    **Date:** 2026-11-21

## Summary

Created `src/agentic_scripts/workflows/roadmap_dev.py` — the deterministic core of the
`roadmap-dev` workflow as small, independently unit-testable pure functions and dataclasses
mirroring the `oc_todo.py` "pure helpers + workflow shell" structure — plus
`tests/test_roadmap_dev.py` (36 hermetic tests, injected clock, no git/network/subprocess).

Implemented per the task plan (all 5 subtasks):

- **Identity + discovery + state schema (pure):** `plan_folder_hash` (sha256 over sorted
  `(relpath, content)` pairs, skipping `DIAGNOSTIC_FILES = {questions.md, failure.md}`),
  `plan_identity` (first 12 hex of sha1, mirroring `todo_id`), `branch_name`
  (`roadmap-dev/<id>-<attempt>`), `extract_title` (first `^#\s+` ATX h1, fallback
  `"Untitled plan"`), `Plan` frozen dataclass (`.identity`/`.topic` properties),
  `PlanEntry` + `discover_plans` (skips `work_plan_text=None` / non-`planning/` / any
  `archived` path segment; sorted by dir), and the v1 state schema
  (`fresh_state` / `validate_state` with the "delete `state/roadmap-dev.json`" operator
  message / `make_plan_entry` stamped from the injected `now` — entry fields per the
  contract incl. `branch_name`, **no PR fields**).
- **Listing parser + renderer (pure, byte-stable):** `LISTING_COLUMNS`, `ListingRow`,
  `parse_listing` (defensive; `#`/`##` sections, 6-cell rows only, `☑`/`☐` glyphs only,
  non-int priority → row skipped, never raises), `render_listing` (repo header emitted
  ONCE per repo, branch tables in first-appearance order, exact header + separator from
  the contract sample, single trailing newline, `""` for empty input).
- **Reconciler + state machine + reaper (pure):** `repo_from_url` (https ±host,
  `git@github.com:` form, ±`.git`; anything else → ghost), `reconcile(plans,
  existing_rows, state_doc, *, now, force_unapproved=frozenset())` implementing all six
  identity-scoped rules (workflow-owned `title`/`state` cells vs preserved user-owned
  `approval`/`priority`/`remove`; sanctioned `failure`→`open` re-arm; vanished = row
  dropped + entry kept; ghost rows dropped; `remove` ☑ on `success` = drop + same-pass
  re-add with fresh `remove=False` / approval kept / priority max+1; entries never
  deleted; copy-on-write state doc), `reap_orphans` (`pending`→`open` with the
  documented `last_error`, `pid`/`started_at` cleared), `apply_job_outcome` (success →
  `success` + `branch_name`/`commit_sha`; questions → `review`; failure → `failure` +
  `last_error`; `finished_at` stamped; `attempt` unchanged).
- **Brief + report renderers (pure, byte-stable):** `extract_report_sections` (verbatim
  behavior duplicate of the `oc_todo` version), `job_status_from_report` (first
  case-insensitive `^\s*status\s*:\s*(success|questions|failure)\s*$` match),
  `render_brief` (the exact autonomy brief from the plan — verified byte-for-byte by
  test), `render_commit_title` (`OC: <title>`, truncated to 72 chars TOTAL),
  `archive_commit_message`, `diag_commit_message`. **No PR renderers, no `github`
  seam** (contract update: PR/merge is human-level; delivery is the pushed attempt
  branch).
- **Workflow shell stub:** `create(config)` reading `config.roadmap_prompts`;
  `RoadmapDevWorkflow` with `name = "roadmap-dev"`, constructor seams
  `git`/`runner`/`active_sessions` (lazy → `sessions.read_active_sessions`)/`now_fn`
  (lazy → `datetime.now(UTC)`) — no `github` seam; `run(ctx)` wrapped in the
  exception→`status="error"` guard exactly like `OCTodoWorkflow.run`; stub body: no-op
  on empty `allowed_repos` (action `no repos configured — nothing to scan`, no state
  write), else load+validate state and return action `phase-1 not implemented (Task 3)`.

## Files

| File | Action | Why |
|---|---|---|
| `src/agentic_scripts/workflows/roadmap_dev.py` | create | Task 2's pure core + stub workflow shell (the module `workflows.yaml`'s disabled `roadmap-dev` entry points at; left disabled) |
| `tests/test_roadmap_dev.py` | create | 36 hermetic unit tests covering every numbered acceptance criterion (injected clock; no git/network/subprocess) |

No other file was modified (no `git.py`, no `scheduler.py`, no `config.py`, no
`workflows.yaml`, no `oc_todo` changes).

## Build / Tests

- `uv run pytest tests/test_roadmap_dev.py -v` (from repo root): PASS — 36/36
- `uv run pytest -v` (full suite): PASS — 290/290 (T1 baseline 254 + 36 new; nothing regressed)
- `uv run ruff check src tests`: PASS — clean
- `uv run ruff format --check src tests`: PASS — clean (45 files)
- Import side-effect check: `import agentic_scripts.workflows.roadmap_dev` with the
  entry still `enabled: false` creates no files (clean import)

## Acceptance Verification

| # | Criterion (verbatim) | Result | Notes |
|---|---|---|---|
| T1.1 | `plan_folder_hash` ignores added/edited `questions.md`/`failure.md` (same hash), changes on any other file change (different hash); deterministic across dict orderings. | PASS | `test_plan_folder_hash_ignores_diagnostics` |
| T1.2 | `plan_identity` is 12 hex chars; stable for identical inputs; differs when any of repo/branch/path/hash differ. | PASS | `test_plan_identity_hex_stable_distinct` |
| T1.3 | `discover_plans` keeps valid folders, drops entries with `work_plan_text=None` (malformed) and any folder whose path contains an `archived` segment; sorted by dir. | PASS | `test_discover_plans_filters_sorts_and_stamps` (also asserts path/title/topic/identity stamping) |
| T1.4 | `extract_title` handles `# Title` (→ `Title`), indented `#  Double` (→ `Double`), no-h1 (→ `Untitled plan`). | PASS | `test_extract_title` |
| T2.1 | Round-trip: `render_listing(parse_listing(sample)) == sample` for the exact 2-repo/2-branch sample in Context (byte-identical, incl. trailing newline). | PASS | `test_parse_listing_round_trip_sample` — exact Context sample as the test constant |
| T2.2 | Malformed input (wrong column count, non-int priority, text between sections, unknown headers) → rows skipped, no exception. | PASS | `test_parse_listing_malformed_input_never_raises` (also `###` free text, `##` before any `#`, `[x]`/`[ ]`/empty → False) |
| T2.3 | `render_listing([]) == ""`; rendering is stable across repeated calls (byte-stable). | PASS | `test_render_listing_empty_stable_and_ordered` (also asserts section ordering + no trailing spaces + single trailing newline) |
| T3.1 | New-plan discovery: row appears under the right `# repo`/`## branch` section with `open`, no checkmarks, priority `max+1` (and `1` in an empty table); state entry created. | PASS | `test_reconcile_discovers_new_plan_empty_and_nonempty_table` (both empty → 1 and max+1 = 5; entry `state="open"`, `attempt=0`; `discovered …` log) |
| T3.2 | User-cell preservation: seed rows with `approval=True, priority=5, remove=False`; reconcile 3× with unchanged scan+state → output identical to input (byte-stable md via renderer), state doc unchanged. | PASS | `test_reconcile_preserves_user_cells_across_repeated_passes` (3 passes, `render_listing(out) == md_in`, `doc_out == doc`, empty log) |
| T3.3 | Re-arm: state-doc `failure` + row state `open` → state doc becomes `open`, row kept `open`, log line present. | PASS | `test_reconcile_rearms_failure_row_set_open_by_user` (`re-armed <id> (user set open)`; entry `updated_at` stamped from injected `now`) |
| T3.4 | Non-failure state divergence: row says `open`, state doc says `review` → row becomes `review` (workflow wins). | PASS | `test_reconcile_state_divergence_workflow_wins` (incl. reverse divergence; no spurious re-arm log) |
| T3.5 | `remove` ☑ on `success` (plan still scanned, state `success`) → row dropped then re-added as `success` in the same pass (net: present, `remove=False`); when the plan is NOT scanned → simply dropped. | PASS | `test_reconcile_remove_success_scanned_reappears` + `test_reconcile_remove_success_unscanned_dropped` (approval kept, priority max+1, entry kept in both) |
| T3.6 | Vanished plan (state entry, no scan) → row dropped, entry kept; ghost row (no scan, no state) → dropped. | PASS | `test_reconcile_vanished_plan_drops_row_keeps_entry` + `test_reconcile_ghost_row_dropped` (exact log lines per spec) |
| T3.7 | `force_unapproved={id}` → that row's `approval=False` in the output (log present). | PASS | `test_reconcile_force_unapproved` (`unapproved <id> (questions raised)`; checkmark preserved without the flag) |
| T3.8 | `reap_orphans` flips all `pending`→`open` (others untouched), logs each; `apply_job_outcome` sets the documented fields for all three outcomes. | PASS | `test_reap_orphans_flips_pending_only` + `test_apply_job_outcome_all_outcomes` (success: `branch_name`/`commit_sha` — NO PR fields; `finished_at` stamped; `attempt` unchanged; input entry not mutated; unknown outcome raises) |
| T4.1 | `render_brief` output contains (assert each verbatim): `"pre-approved, no user present"`, `"question tool is unavailable"`, `"NEVER in parallel"`, the plan path, the attempt number, the timeout value, and the exact three `Status: …` lines; byte-stable across calls (assert equality of two renders). | PASS | `test_render_brief_exact_and_byte_stable` — asserts the FULL brief byte-for-byte against the plan's block (strongest form) plus each verbatim substring and two-render equality; `test_render_brief_test_command_line` covers the test-command branch |
| T4.2 | `job_status_from_report`: `"Status: questions"` mid-report → `"questions"`; no status line → None; `"status: SUCCESS"` (lowercase label) → `"success"`; `"Status: succeeded"` (not in the allowed set on that line) → None unless a real line exists. | PASS | `test_job_status_from_report` (all four cases verbatim) |
| T4.3 | `extract_report_sections` matches `oc_todo` behavior on a sample report (same assertions style as `tests/test_oc_todo.py` for that function). | PASS | `test_extract_report_sections_matches_oc_todo_behavior` (full / missing-Blockers / None cases, same style) |
| T4.4 | `render_commit_title` = `OC: <title>` truncated at 72 chars total (assert on a >72-char title); `archive_commit_message` / `diag_commit_message` produce the exact documented strings. | PASS | `test_render_commit_title_truncates_at_72_total` + `test_archive_and_diag_commit_messages` (incl. invalid `kind` → `ValueError`) |
| T5.1 | `uv run pytest tests/test_roadmap_dev.py -v` fully green; `uv run pytest -v` (whole suite) green; ruff check + format clean. | PASS | See Build / Tests: 36/36, 290/290, ruff check + format clean. Shell behavior also covered: `test_create_returns_named_workflow` (name == `"roadmap-dev"`, no `github` seam), `test_run_empty_allowed_repos_is_noop` (status `"ok"`, exactly one action, state file absent after run), `test_run_nonempty_allowlist_reports_phase1_stub` (status `"ok"` + `phase-1 not implemented (Task 3)`) |

## Blockers

None.

## Next Steps

- **Task 3 (Phase 1 pipeline)** replaces the `RoadmapDevWorkflow._run` stub: scan
  (`git ls-tree`/`show_file` → `PlanEntry` list per allowed repo/branch), prompts-clone
  of the listing repo (`prompts_clone_dir`), `parse_listing` → `reconcile` →
  `render_listing` → push, plus `reap_orphans` wiring and the `git.py` additions the
  plan calls for (`ls_tree`, `mv`). The seams this task left in place are the intended
  wiring points: `self._git`, `self._runner_override` (lazy `ctx.runner`),
  `self._active_session_count()` (lazy `sessions.read_active_sessions`),
  `self._now()`.
- `render_brief` is final (byte-verified against the plan) — Task 4's job pipeline
  consumes it as-is; `apply_job_outcome` is the outcome step for that pipeline.
- `workflows.yaml` still carries `roadmap-dev: enabled: false` — untouched, as
  instructed (flipping is Task 6).
