# Task Plan: roadmap-dev listing — README doc update (detail row)

**Purpose:** Document the new goal + task-titles detail row in the operator guide
(`README.md`) of the plan-overview repo `y2d2/autonomous_task_overview`, so plan authors
know the extra row under each plan is workflow-owned.

## Objective

The roadmap-dev workflow starts rendering a detail row under every plan row in `plans.md`
(a companion code task in `agentic_scripts` does the rendering):

```
| ☐ | 1 | planning/orbit-dmp/work_plan.md | Task Plan: ORBIT DMP v0 — consortium DMP | open | ☐ |
| — | — | **Goal:** Build `projects/ORBIT/DMP/ORBIT_DMP_v0.md`, the table-first consortium DMP, in five sequential sub-agent tasks. | **Tasks:** 1 Skeleton & front matter · 2 Master table 1 · 3 Supporting tables 2–6 | — | — |
```

The repo's `README.md` ("How to write a plan" / "The listing" operator guide) currently
documents only the 6-column row. End state: the "## The listing" section shows the detail
row in its sample, documents its source (derived from the plan's Purpose/Goal line and
task headings — refreshed from the scan on every reconcile) and its ownership
(**workflow-owned** — user edits to the detail row are overwritten on the next scan, like
`title`/`state`), and clarifies that nothing else in the format changes (same 6-column
data row, same user cells, same state machine). Committed with the `OC:` prefix and
pushed to `origin/main`.

## Context

- **Repo:** `/workspace/Obsidian/ARP_roadmap/autonomous_task_overview` — a git checkout of
  `y2d2/autonomous_task_overview`, branch `main`, clean tree, up to date with origin
  (verify with `git status` + `git pull --ff-only` first; if not clean/up-to-date, STOP
  and report — do not stash or force anything).
- **File:** `README.md` (102 lines). Relevant section: `## The listing` (L43–71) — it
  shows the sample listing (L48–58), the column table (L60–67), and the identity paragraph
  (L69–71). The top intro (L8–12) already says workflow-owned cells (`title`, `state`)
  update automatically and user-owned cells (approval ☑, priority, remove ☑, failure→open
  re-arm) are never clobbered.
- **Exact detail-row format (byte contract, do not improvise):** one row directly under
  each data row, six cells:
  `| — | — | **Goal:** <goal> | **Tasks:** <label title> · <label title> … | — | — |`
  with `—` = EM DASH U+2014 (not a hyphen); `<goal>` = the plan's `**Purpose:**`/`**Goal:**`
  line of its `work_plan.md` (fallback `## Purpose`/`## Goal` section, else `—`);
  `<label title>` pairs = the plan's `### Task N: <title>` headings (fallback: a task
  table in `work_plan.md`, then the `work_plan_task_<N>_<desc>.md` file names; else `—`),
  all of them, joined with ` · ` (space, middle dot U+00B7, space).
- **Git conventions (this repo):** commit message `OC: <meaningful description>`, commit on
  `main`, `git push` after. This repo has no protected-branch friction (the workflow
  itself pushes `plans.md` to `main` with `OC:` commits).
- **Do NOT touch** `plans.md` (the workflow owns it; it is reconciled/pushed
  automatically) or any other file in the repo.

## Tasks

### Task 1: README — document the detail row
- **Files:** `README.md` (modify)
- **Do:**
  1. `git -C /workspace/Obsidian/ARP_roadmap/autonomous_task_overview status` +
     `git pull --ff-only` (clean tree expected; if not clean or not fast-forwardable,
     STOP and report as a blocker).
  2. In `## The listing`: extend the markdown sample (L48–58) so each data row is followed
     by a detail row, e.g. the `orbit-sim` row gains:
     `| — | — | **Goal:** Extend the ORBIT simulator with … | **Tasks:** 1 Core loop · 2 Rendering | — | — |`
     (illustrative text is fine — the sample is already fictional).
  3. Add one short paragraph right after the column table (before the `**Identity:**`
     paragraph), in the doc's existing style (imperative, concise, backticked terms),
     covering: (a) what the detail row is — one workflow-rendered row per plan carrying
     the plan's goal and the title of every task; (b) source — derived from
     `work_plan.md` (the `**Purpose:**`/`**Goal:**` line; the `### Task N:` headings, with
     task tables / task file names as fallbacks), refreshed from the scan on every
     reconcile — no user action; (c) ownership — **workflow-owned**: editing it in
     `plans.md` is pointless, the next scan rewrites it (the sanctioned way to change
     what it shows is editing the plan itself); (d) it is NOT a data row — the engine
     ignores it (never approve/prioritize on it).
  4. In the intro bullet list (L9–12), extend the workflow-owned-cells bullet to also
     name the detail row (keep it one line: "workflow-owned cells (`title`, `state`, and
     the per-plan goal/task detail row) update automatically;").
  5. Read the whole README once after editing for consistency (terminology: "detail row",
     never "sub-row"/"second row").
- **Notes:** keep the change additive and minimal (≤ ~15 lines added, no rewrites of
  existing prose); the column table stays exactly as-is (6 columns).
- **Acceptance:**
  1. `git diff` shows changes to `README.md` only; the "## The listing" sample contains a
     detail row under each data row and the new paragraph documents source + ownership +
     "not a data row"; the intro bullet names the detail row.
  2. Committed with an `OC:`-prefix message (e.g.
     `OC: document the plan goal/task detail row in the listing README`) staging ONLY
     `README.md`, and pushed: `git ls-remote origin main` equals local `git rev-parse HEAD`.

## Out of Scope

- `plans.md` (workflow-owned), the agentic_scripts code (companion task), other repos.

## Notes

- [Assumption] The README is the only operator doc for the listing format (the
  agentic_scripts module docstring is code-internal; a separate step of the code task
  updates it). If you find another user-facing doc describing the `plans.md` format in
  THIS repo, report it instead of editing it.
- [Note] Push conflicts are not expected (the workflow's last commit here was the initial
  content; listing reconcile commits touch only `plans.md`). If the push is rejected
  non-fast-forward, re-run `git pull --ff-only` + push once; if it still fails, report.
