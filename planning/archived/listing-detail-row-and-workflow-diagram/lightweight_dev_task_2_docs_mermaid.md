# lightweight-dev Output — Task: docs — mermaid pipeline graph + listing-format alignment

**Task:** #2    **Session:** listing-detail-row-and-workflow-diagram    **Date:** 2026-11-26

## Summary

Docs-only task in `/workspace/Python/autonomous_task_overview` on the existing branch
`feature/listing-detail-row` (checked out, clean, pulled — no new branch; `main` and
`plans.md` untouched).

1. **Mermaid pipeline diagram** — new `## The pipeline at a glance` section inserted in
   `WORKFLOW.md` directly after "What this is" and before "The pipeline split": ONE
   `flowchart TD` with 26 nodes covering the full split — timer → lock → phase-1
   (reap/scan+discover/hash/parse/reconcile/push) → idle-gate diamond (closed = drain
   skipped, state persisted) → drain (slots/select/worktree+roadmap-dev ID-N branch/
   brief/spawn) → planner review with major-question diamond (yes → `questions.md` +
   review, no → per-task lightweight-dev execution) → report routing → tests-gate
   diamond (yes → success commit + archive + push attempt branch; no → failure +
   `failure.md`) → questions-diagnostic path → dotted 480-min-budget timeout branch →
   human PR gate. Color-coded via `classDef`/`class`: blue = deterministic script
   (incl. the three script-evaluated decision diamonds `GATE`/`Q`/`TESTS`, which the
   spec skeleton left unassigned — added, along with `DONE`, so all 26 nodes are
   colored), orange = LLM (`PLAN`/`DEV`/`QMD`/`FAIL`), green = human (`HUMAN`). A
   legend sentence naming the three colors sits directly under the diagram. Node
   labels contain no `<`, `>` or double-quote characters (`roadmap-dev ID-N` style).
2. **Wording alignment** — every docs mention of the old detail row now describes the
   per-plan `###` sections + single-column `details` table (see Files). The README
   example is copied verbatim from Task 1's exact-byte fixture in
   `tests/test_roadmap_dev.py::test_render_listing_emits_per_plan_sections` and
   demonstrates both cases: one plan WITH a details table, one plan with neither goal
   nor tasks rendering NO details table.

No `src/` or `tests/` changes; the engine regenerating (never hand-migrating) the
listing is already the README's framing and stays intact.

## Files

| File | Action | Why |
|---|---|---|
| `WORKFLOW.md` | modify | New `## The pipeline at a glance` mermaid section (+ legend sentence); "Listing parse/render" row → per-plan `###` sections + workflow-owned single-column `details` table; "User-cell-preserving reconcile" row "detail row" → "details table" |
| `README.md` | modify | "The listing" example replaced with the exact-byte per-plan-section output (2 plans: with-details + no-details skip case); intro line now says one `###` section per plan; "**Detail row:**" paragraph rewritten as "**Per-plan sections:**" (heading + own data-row table + `details` table: goal + `<br>`-separated task lines, derivation, skip rule, per-reconcile refresh, not data rows — engine ignores, never approve/prioritize on them); intro bullet "goal/task detail row" → "per-plan `details` table" |
| `VARIABLES.md` | modify | Listing-columns row: "(+ the goal/task detail row)" → "(+ the per-plan details table)" |

## Build / Tests

- `uv run pytest -q` (repo root): **PASS** — 82 passed (identical to the pre-edit baseline; no code touched)
- `uv run ruff check .`: **PASS** — All checks passed
- Mermaid verification: **PASS** — rendered with `npx -y @mermaid-js/mermaid-cli@12.2.0`
  (`--no-sandbox` puppeteer config) to `/tmp/opencode/mermaid_check.png` and, after the
  class-assignment fix, `/tmp/opencode/mermaid_check2.png` (exit 0, "Generating single
  mermaid chart", ~128 KB PNG). `diff` confirms the fence block embedded in `WORKFLOW.md`
  is **byte-identical** to the verified `.mmd`. Plus a programmatic consistency check
  (node script): 26 nodes first-declared with bracket types, no bracket-type conflicts,
  balanced quotes, no `<`/`>` in labels, all `class` targets declared, all 26 nodes
  assigned to a class. (Eye-level PNG inspection was not possible — this model has no
  image input and nested subagent dispatch hit the depth limit — the render itself is a
  full parse+layout pass and is the verification named in the acceptance criteria.)
- README byte-consistency check: **PASS** — a script extracted the README fenced block
  and compared it to the live `render_listing()` output for the fixture's two rows:
  `BYTE-MATCH: True`; `parse_listing()` on the example returns exactly the 2 data rows
  (proving the details lines are not data rows).
- Stale-mention sweep: **PASS** — no "detail row" (case-insensitive) and no `| — | — |`
  legacy row remains in `README.md` / `WORKFLOW.md` / `VARIABLES.md`.

## Acceptance Verification

| # | Criterion (verbatim) | Result | Notes |
|---|---|---|---|
| T1.1 | `WORKFLOW.md` contains exactly one ` ```mermaid ` fenced `flowchart` covering: timer → phase-1 (reap/scan/discover/hash/parse/reconcile/push) → idle-gate branch (closed = skip drain) → drain (slots/select/worktree/brief/spawn) → LLM review with major-question branch → per-task execution → report routing → tests gate → success (archive + push attempt branch) / failure (diagnostic) / questions (diagnostic) → timeout branch → human PR gate. | PASS | `grep -c '^```mermaid' WORKFLOW.md` = 1; all listed stages present as nodes/branches (see Summary); section placed after "What this is", before "The pipeline split" |
| T1.2 | Script vs LLM vs human color-coded via `classDef` + `class` statements; legend sentence under the diagram naming the colors. | PASS | 3 `classDef`s; `class` statements cover all 26 nodes (skeleton's unassigned `GATE`/`Q`/`TESTS`/`DONE` added to `script` — the spec parenthetical states the diamonds are script-evaluated and `DONE` is a script step in the split table); legend sentence sits directly under the fence |
| T1.3 | Diagram verified (mermaid-cli render to /tmp/opencode/ or documented careful review). | PASS | mermaid-cli render to `/tmp/opencode/` succeeded twice (final: `mermaid_check2.png`, exit 0) AND a programmatic structural check passed; embedded bytes verified identical to the rendered file |
| T2.1 | No mention of the old `\| — \| — \|` detail row remains in the three docs; the README example is byte-consistent with the Task 1 exact-byte tests (compare character-for-character the data-row + details-table lines). | PASS | Grep sweep: zero "detail row" / `\| — \| — \|` in the three docs; README block compared character-for-character against the live `render_listing()` output for the test fixture's rows → `BYTE-MATCH: True` (the example IS the `test_render_listing_emits_per_plan_sections` expected string) |
| T2.2 | `uv run pytest` from the repo root is still fully green (you changed no code). | PASS | 82 passed; ruff also clean |
| T2.3 | Commits `OC:`-prefixed on `feature/listing-detail-row`, pushed. | PASS | Commit "OC: Add mermaid pipeline diagram; align listing docs with per-plan sections" on `feature/listing-detail-row`, pushed to origin (branch tip: see git log) |

## Blockers

None. (Two tooling notes, not blockers: the diagram QA subagent could not be dispatched
— subagent depth limit — so visual PNG inspection was replaced by the successful
mermaid-cli render + structural script; the render output is very tall (~1:7, inherent
to a 26-stage `flowchart TD` the spec mandates), which is normal for pipeline diagrams
in Markdown.)

## Next Steps

- Orchestrator: Task #2 done — the global plan (WORKFLOW mermaid + per-plan-section docs)
  is complete. Awaiting human review/merge of `feature/listing-detail-row`.
- Reminder (per plan Notes): the live `plans.md` switches to the new per-plan format on
  the first engine fire after merge — no manual migration, as the docs state.
