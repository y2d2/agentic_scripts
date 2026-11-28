# lightweight-dev Output — Task: Docs sync in autonomous_task_overview (README / WORKFLOW.md / VARIABLES.md)

**Task:** #3    **Session:** lightweight-dev (autonomous-task-rehome)    **Date:** 2026-11-28

## Summary

Synced the three operator docs in `/workspace/Python/autonomous_task_overview` (branch
`feature/rehome-final`, on top of Task 2's `4e9cc16`) to the re-homed engine as it now stands:

1. **README.md** — permanence was already stated (kept; the intro already says the repo is the
   single home and `agentic_scripts` keeps only mail-keeper/oc-todo — accurate, untouched).
   Added the **listing-lifecycle paragraph** to `## The listing`: every 30-min scan rebuilds
   `plans.md` end-to-end, commits from the dedicated sandbox clone, pushes to **this repo's own
   `main`** (`listing_repo` / `listing_path` / `listing_branch`), retries once on conflict, then
   mirrors the same bytes into the checkout's root `plans.md` (`roadmap_prompts.local_listing`,
   default `plans.md`, `null` disables) — a display copy the engine writes but never commits,
   while the scan reads the pushed `main`. Replaced the stale single-column `details`-table
   example with the **current three-column checklist** (`| # | details | ✓ |`) and rewrote the
   **Per-plan sections** paragraph to the real renderer contract: `G` goal row whose ☑ mirrors
   `state == success`, one row per task, task ☑ from `task_done_labels` (existence of a
   `lightweight[-_]dev_task_<label>_<desc>.md` result report — content never parsed), title
   fallback chain, checklist omitted when nothing to show. "Running the engine" kept verbatim.
2. **WORKFLOW.md** — split table: rewrote the **Listing parse/render** row (3-col checklist +
   `task_done_labels` done source), the **reconcile** row (checklist wording), and the
   **Listing commit + push w/ retry** row (`listing_branch` (`main`) of `listing_repo`, this repo);
   added a new **Local listing mirror** row (`roadmap_dev.py:_mirror_listing`, after every
   decision, self-healing, write-failure logged only, never runs git). Updated the header
   paragraph, the "Where each side runs" Listing bullet (mirror, written-only), added a
   **Listing mirror write failure** row to the failure-mode table, and inserted a `MIRROR` node
   (script-classed) into the mermaid diagram between PUSH and GATE so the at-a-glance view
   matches the table.
3. **VARIABLES.md** — added the **`local_listing`** entry (value `plans.md`; mirror destination
   resolves against project root, absolute passes through; `null` disables; display-copy
   semantics) to section C; clarified `listing_repo` meaning (pushes land on `listing_branch`);
   section D: "listing columns" wording → three-column checklist, plus two new contract rows
   (**details checklist header** `# / details / ✓` = `_DETAILS_HEADER`, **task done-labels**
   filename pattern); refreshed the "Values verified against the code" date to 2026-11-28.
   `allowed_repos` (9, incl. `y2d2/agentic_scripts`) and `listing_repo` value were **already
   correct** — re-confirmed against `config/workflows.yaml`, values unchanged.

Every config key and code symbol cited was grepped against `config/workflows.yaml` / `src/**/*.py`
before writing. Per the dispatch reminder, agentic_scripts-only concepts (`workflows:` section,
`machine.load_threshold`, `admin_repo`) were NOT documented here, and the `autonomous_task.scheduler.run`
prose in test files was left untouched (freeze contract).

## Files

| File | Action | Why |
|---|---|---|
| `README.md` | modify | Lifecycle paragraph (scan → render → push own `main` + root mirror); 3-col checklist example + Per-plan sections rewrite; cell-ownership wording |
| `WORKFLOW.md` | modify | Header paragraph, mermaid MIRROR node, render/reconcile/push rows, new mirror row, "Where each side runs", failure-mode row, identity-hex accuracy fix |
| `VARIABLES.md` | modify | `local_listing` entry (+default/`null` disable), `listing_repo` meaning, checklist contract rows in D, verification date |

Commit on `feature/rehome-final`: `56887a2` `OC: Docs — re-home sync (self-listing, local_listing, checklist renderer)`
(3 files, +59/−32). Pushed `4e9cc16..56887a2`; `git status --porcelain` empty after push.
No `src/`, `tests/`, `config/`, `scripts/`, `systemd/` or `plans.md` change; nothing written to
`agentic_scripts` except this result file.

## Build / Tests (docs-only — verification actions)

- README example byte-accuracy: **PASS** — extracted the fenced example and compared against real
  `render_listing([2 ListingRows])` output: `README example == render_listing output: True`.
- Config-key resolution: **PASS** — all 21 keys cited anywhere in the three docs
  (`quiet_window, poll_interval_minutes, gate_polls_required, gate_poll_tolerance_minutes,
  run_timeout_minutes, binary, model, max_steps, timeout_minutes, auto_approve, allowed_repos,
  listing_repo, listing_repo_url, listing_path, listing_branch, local_listing, repo_urls,
  test_commands, state_dir, log_dir, sandbox_dir`) grep-hit `config/workflows.yaml` (count ≥ 1 each).
- Code-symbol resolution: **PASS** — all 31 symbols cited (`_reap_orphans, _scan_and_reconcile,
  discover_plans, plan_identity, plan_folder_hash, parse_listing, render_listing, reconcile,
  _reconcile_and_push, _mirror_listing, task_done_labels, _slots, _select_startable, _start_job,
  branch_name, render_brief, _route_job, extract_report_sections, job_status_from_report,
  _route_success, _TESTS_GATE_TIMEOUT_SECONDS, _JOB_JOIN_TIMEOUT_SECONDS, _commit_diag,
  _AGENT_NAME, _DETAILS_HEADER, LISTING_COLUMNS, evaluate_idle_gate, acquire_lock,
  read_active_sessions, StateStore, AgentRunner`) resolve in `src/**/*.py` (evidence lines captured,
  e.g. `_mirror_listing` → `roadmap_dev.py:2276`, `task_done_labels` → `roadmap_dev.py:643`,
  `_DETAILS_HEADER = "| # | details | ✓ |"` → `roadmap_dev.py:124`). State-schema-version-`1` claim
  resolves to `_STATE_VERSION` (`roadmap_dev.py:812,832`).
- Stale-claim scan: **PASS** — `grep agentic` in the three docs returns only the (correct)
  permanence sentence in README and `y2d2/agentic_scripts` in the `allowed_repos` row; no doc
  claims roadmap-dev runs in `agentic_scripts`.
- Markdown table integrity: **PASS** — column-count check on every table in all three files OK
  (run twice, incl. after the last row rewrite).
- `plans.md` untouched: **PASS** — not in the commit, never modified in the working tree.

## Acceptance Verification

| # | Criterion (verbatim) | Result | Notes |
|---|---|---|---|
| 1. | Accuracy — every config key/symbol cited in the three docs greps to real code/config; no doc claims roadmap-dev still runs in agentic_scripts | **PASS** | 21/21 config keys → `config/workflows.yaml`; 31/31 symbols → `src/**/*.py`; README example is byte-identical to the live renderer's output; only two `agentic_scripts` mentions remain, both correct. Bonus: fixed a pre-existing wrong "16-hex" identity claim (code: `plan_identity` returns first 12 hex chars of sha1). |
| 2. | Completeness — all three files updated; `local_listing` documented with default + disable semantics | **PASS** | `git show --stat HEAD`: exactly README.md, WORKFLOW.md, VARIABLES.md. `local_listing` documented in all three: README lifecycle ("default `plans.md`; `null` disables"), WORKFLOW mirror row (same), VARIABLES C entry (value `plans.md`, `null` disables, project-root resolution, write-never-commit semantics). |
| 3. | Git — one commit, pushed, only doc files staged; no src/tests touched | **PASS** | One commit `56887a2` on `feature/rehome-final`, pushed (`4e9cc16..56887a2`), staged via explicit paths only (`git add README.md WORKFLOW.md VARIABLES.md`); commit stat shows exactly the 3 doc files; working tree clean after push; `agentic_scripts` untouched. |

## Deviations

1. **README example + "Per-plan sections" paragraph rewritten (beyond step 1's literal wording).**
   They claimed to show "the renderer's exact output" but showed the pre-re-home single-column
   `details` table — false as of Task 1's engine port. Fixing them is required by the task's
   objective ("describe the re-homed engine as it now stands") and acceptance #1's accuracy spirit;
   the replacement example was generated from the actual `render_listing` call, not hand-written.
2. **Mermaid diagram touched** (one new script-classed `MIRROR` node + PUSH label). Step 2 names
   the split-table rows, but the same section's diagram feeds off them ("the split table below owns
   the step detail"); leaving it without the mirror step would contradict the new row.
3. **Pre-existing "16-hex hash" → "12-hex sha1 identity"** in the WORKFLOW Identity-hashing row.
   Not a re-home row, but it factually misdescribes `plan_identity` (`digest[:12]`; the folder hash
   is the full sha256) in a doc this task owns. One-cell fix, recorded here.
4. **`allowed_repos` / `listing_repo` values unchanged** — step 3's adjustments (9 repos incl.
   `y2d2/agentic_scripts`; `listing_repo: y2d2/autonomous_task_overview`) were already correct in
   the doc and re-confirmed against the yaml (Task 1's finding #2); only the verification date and
   `listing_repo`'s "Meaning" wording changed.
5. No test-suite runs: docs-only task ("No code/config changes"); nothing import- or test-affecting
   was modified. The `uv run python` verification invocations only produced gitignored caches.

## Blockers

None.

## Next Steps

- **Task 4** inherits Task 1/2's notes: merge base / A-B baseline = current `main` (`e99307f`);
  branch tip now `56887a2` (`d49158c` → `4e9cc16` → `56887a2`).
- **Forced-run validation (Task 4)** will be the first render of the tracked root `plans.md` in the
  new checklist format (the committed copy still shows the Nov-26 single-column render — that is
  the engine's output to re-render, not docs to hand-edit; per the plan's hygiene rule).
- Optional polish candidates deliberately left: `test_roadmap_dev*.py` `scheduler.run` docstring
  prose (freeze contract, per dispatch reminder and Task 2 Deviation 4).
