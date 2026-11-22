# autonomous_task_overview

The live listing of the `roadmap-dev` workflow — this box's unattended plan-execution
engine — plus the guide for the people who write the plans it executes.

## What this repo is

- **`plans.md`** is the live listing of every un-archived plan the engine can pick up.
  It is reconciled by the workflow on every 30-minute scan:
  - **workflow-owned cells** (`title`, `state`) update automatically;
  - **user-owned cells** — the `approval` ☑, the numeric `priority`, the `remove` ☑, and
    the `failure` → `open` re-arm — are never clobbered.
- Executed plans land as **pushed `roadmap-dev/<id>-<n>` branches** on the plan's repo
  (implementation + archived plan folder). The engine never creates PRs — **a human opens
  the PR and verifies** before merging.
- Everything else in this repo is documentation: this guide is where plan authors learn
  the rules.

## How to write a plan

A plan is a folder `planning/<topic>/work_plan.md` (plus optional
`work_plan_task_<N>_<desc>.md` task files) in **any allowed repo, on any branch**,
**outside `planning/archived/`**. The engine discovers it, lists it, and — once you
approve it — executes it in a headless `planner-enhanced` run.

The rules that make a plan executable:

1. **Small, self-contained tasks.** Each task must be executable by one
   `lightweight-dev` dispatch with everything it needs in the task spec — the worker
   has no user to ask.
2. **Testable acceptance criteria.** Every task needs at least one observable PASS
   condition; the worker verifies each task's criteria before starting the next.
3. **Split big plans.** A plan that needs the full 8-hour job budget should be split
   into several smaller plans — context size is the speed bottleneck, not compute.
4. **Know what counts as a *major* question.** Anything that changes **scope,
   requirements, or dependencies** — NOT implementation detail. Major questions go to
   `planning/<topic>/questions.md` and the plan stops in `review`; minor decisions are
   made and recorded by the headless planner itself.
5. **An edited plan is a new plan.** A plan's identity includes a content hash: editing
   any plan file yields a new row with new attempt numbering. To re-arm a *failed*
   plan, either set its `state` cell to `open` (same plan) or edit the plan (new plan).

## The listing

`plans.md`: one `#` section per repo (repo URL as header), one `##` table per branch —
repo/branch are headers, not columns:

```markdown
# https://github.com/y2d2/ARP_MPE.git
## main
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☐ | 1 | planning/orbit-sim/work_plan.md | ORBIT sim extension | open | ☐ |
## dev
| approval | priority | plan | title | state | remove |
|----------|----------|------|-------|-------|--------|
| ☑ | 2 | planning/unitest/work_plan.md | Unit tests | review | ☐ |
```

| Column | Owner | Meaning |
|--------|-------|---------|
| `approval` | user | The permission to execute — the engine only runs plans you ☑. |
| `priority` | user | Numeric, ascending: 1 = first; ties by row order; new plans get max+1 in their table. |
| `plan` | workflow | Path to `work_plan.md` (identity anchor). |
| `title` | workflow | The plan's title, refreshed from the scan. |
| `state` | workflow | See the state machine below. The one sanctioned user edit: `failure` → `open`. |
| `remove` | user | Valid on `success` rows: the row is dropped on the next scan (reappears as `success` while the attempt branch is unmerged, then disappears for good). |

**Identity:** repo + branch + plan-folder path + content hash of the folder (excluding
the workflow-written `questions.md` / `failure.md`). An edited plan = new identity =
new row; the old row reconciles away.

## State machine

| state | meaning | startable |
|---|---|---|
| `open` | discovered, awaiting approval/execution | yes, with ☑ |
| `pending` | job running | no |
| `review` | major questions in `questions.md`; checkmark removed by the engine (logged) | yes, once you re-☑ |
| `success` | attempt branch `roadmap-dev/<id>-<n>` pushed (implementation + archived plan folder, base = the plan's branch) — a human opens the PR, verifies, merges | no; removable via `remove` ☑ |
| `failure` | `failure.md` (reason) on the plan's branch; plan not archived | no — re-arm = set `state` to `open` (or edit the plan → new row) |

`success` / `failure` never auto-restart. A `success` row that reappears after a
`remove` tick stays `success` — it is never re-executed.

## Operating the listing

All of this is editing `plans.md` (or the plan's branch) and pushing — the next scan
picks it up:

- **Approve a plan** — ☑ its `approval` cell.
- **Re-prioritize** — change the numeric `priority` (1 = first; ties by row order).
- **Answer a review** — edit `planning/<topic>/questions.md` on the plan's branch,
  commit + push, then re-☑ the row.
- **Re-arm a failure** — set the row's `state` cell to `open`.
- **Remove a success row** — ☑ its `remove` cell.
- **Open + merge the PR** (human step) — in a local clone of the plan's repo,
  `git checkout roadmap-dev/<id>-<n>` (or the GitHub UI) and open the PR (base = the
  plan's branch); after merging, prune the branch:
  `git push origin --delete roadmap-dev/<id>-<n>`.
- **Delete a plan folder** — the row reconciles away. This is the escape hatch for a
  plan that keeps ping-ponging through `review`.
