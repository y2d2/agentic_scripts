# Task Plan: roadmap-dev listing — goal + task-titles detail row (core)

**Purpose:** Add the goal + task-titles detail row to the `plans.md` listing in the
roadmap-dev workflow: pure extraction functions, `Plan`/`ListingRow` fields, the
byte-stable renderer, parser safety, and the full test update.

## Objective

The `roadmap-dev` workflow (`/workspace/Python/agentic_scripts`, branch
`feature/roadmap-dev-workflow`) reconciles a live listing `plans.md` (repo
`y2d2/autonomous_task_overview`, path `plans.md`, branch `main`) with one 6-column row per
plan: `| approval | priority | plan | title | state | remove |`. Extend it so that
`render_listing` emits, directly under each data row, an extra 6-cell **detail row**
(workflow-owned, derived from the scanned plan, byte-stable):

```
| ☐ | 1 | planning/orbit-dmp/work_plan.md | Task Plan: ORBIT DMP v0 — consortium DMP | open | ☐ |
| — | — | **Goal:** Build `projects/ORBIT/DMP/ORBIT_DMP_v0.md`, the table-first consortium DMP, in five sequential sub-agent tasks. | **Tasks:** 1 Skeleton & front matter · 2 Master table 1 · 3 Supporting tables 2–6 · 4 Minimal prose + Coera/IP text · 5 QA pass | — | — |
```

- Cells: approval=`—`, priority=`—` (EM DASH U+2014 — load-bearing, see below),
  plan-cell=`**Goal:** <goal>`, title-cell=`**Tasks:** <t1> · <t2> · …`, state=`—`,
  remove=`—`.
- `<goal>` is the extracted goal text or `—` when none; the task list joins
  `<label> <title>` pairs with ` · ` (one space on each side of the middle dot) and is `—`
  when empty. No truncation — every task.
- `parse_listing` must silently skip the detail row (it never parses as a data row).
- `reconcile` stamps goal/task titles from the scanned `Plan` on every row it emits.
- The steady-state no-push invariant holds: for unchanged plans,
  `render(reconcile(plans, parse(file), state)) == file`.

## Context

- **Work in:** `/workspace/Python/agentic_scripts`, branch `feature/roadmap-dev-workflow`
  (do NOT switch branches; it is up to date with origin). Working tree has 3 untracked
  files under `planning/mail-keeper-pruning/` from another session — never stage/commit them.
- **Tooling:** Python ≥3.12, `uv`-managed. Lint `uv run ruff check .` (line-length 100,
  rules E/F/I/UP/W); format `uv run ruff format --check .`; tests `uv run pytest -q`
  (testpaths `tests`), single file `uv run pytest tests/test_roadmap_dev.py -v`.
- **Docstring convention (match the existing file exactly):** Google-style with
  `Purpose:` (when non-obvious), `Args:`, `Returns:` and `Note:`/`Rationale:` where the
  file already uses them — every function in `roadmap_dev.py` carries one; module
  docstring documents the design rationale.
- **Files:** `src/agentic_scripts/workflows/roadmap_dev.py` (module docstring L1–61;
  constants L82–137 — `LISTING_COLUMNS` L99, `_LISTING_HEADER` L102, `_LISTING_SEPARATOR`
  L106); `tests/test_roadmap_dev.py` (1018 lines).
- **Key existing symbols (all in `roadmap_dev.py`):**
  - `extract_title(work_plan_text: str) -> str` (L294) — first `^#\s+` ATX h1 → `title`
    cell; fallback `"Untitled plan"`. Mirror its style for the new extractors.
  - `Plan` frozen dataclass (L315): `repo, branch, path, title, content_hash` + derived
    `identity`/`topic` properties.
  - `PlanEntry` (L350): `dir, work_plan_text (str|None), file_contents (dict[str, bytes])`
    — folder-relative path → raw bytes; `discover_plans` (L368) already receives it and
    builds `Plan(repo, branch, path=f"{dir}/work_plan.md", title=extract_title(...),
    content_hash=plan_folder_hash(...))`, sorted by path.
  - `ListingRow` frozen dataclass (L543): `repo_url, branch, approval, priority, plan,
    title, state, remove` — NO defaults currently; tests construct it positionally.
  - `parse_listing(md) -> list[ListingRow]` (L575): line loop; `# ` sets repo_url,
    `## ` sets branch; a line is a row only when it starts+ends with `|`, has exactly 6
    stripped cells, is not the header tuple, is not the all-`-` separator, and `int(cell)`
    of the 2nd cell succeeds — everything else (incl. free text, `###` headings, 5/7-cell
    rows, non-int priority) is skipped silently. NEVER raises.
  - `render_listing(rows) -> str` (L638): groups by repo (first appearance), then branch;
    per table emits header + separator + `f"| {'☑' if row.approval else '☐'} | {row.priority} | {row.plan} | {row.title} | {row.state} | {'☑' if row.remove else '☐'} |"`;
    `""` for no rows; single trailing newline; no trailing spaces.
  - `reconcile(plans, existing_rows, state_doc, *, now, force_unapproved=…, rearm_guard=…)`
    (L686) — builds `ListingRow` in THREE places: rule 2 "scanned + not in state" (L803),
    rule 1 "scanned + in state" → `updated_by_key` (L871), rule 5 "remove ☑ on success"
    re-add (L857). All three have the scanned `plan` in scope.
  - `_reconcile_and_push` (L1626): no-push test is
    `render_listing(new_rows) == current_md` (L1701); `current_md` comes from
    `Git.show_file`, which rstrips trailing newlines (pre-existing quirk — do NOT fix it).
- **Real plan formats verified (2026-11-22, all 9 allowed repos, 77 plans) — the extractors
  must cover exactly these:**
  - Goal: `**Purpose:** <text>` inline (61 plans, line starts the line, optional leading
    whitespace); `## Purpose` heading section (1 plan — body wraps over multiple lines,
    first paragraph until blank line/next heading); `**Goal:** <text>` inline (1 plan);
    neither (15 plans → `—`).
  - Tasks, tier 1 headings: `### Task 1: <title>` (dominant); subtask labels
    `### Task 3b: …`, `### Task 5c: …`; trailing spec refs to strip:
    `→ \`work_plan_task_1_people_per_wp.md\` (single task, @lightweight-dev)`,
    `— see \`work_plan_task_1_storyboard.md\``, `— \`work_plan_task_1_event_detection.md\``,
    `→ \`lightweight-dev_task_1_baseline.md\``; must NOT match: plural range heading
    `### Tasks 8–9 (remaining drawings + deck integration): CANCELLED`, non-task h3
    `### Bag-reader format support (RESOLVED by Task 2, 2026-10-19, rosbags 0.11.8)`,
    any h2 (`## Tasks`, `## Task sequence …`, `## Task Index …`). Titles may contain
    em/en dashes, backticks, colons, `(user 19/11: "…"; text → speaker notes)` tails.
  - Tasks, tier 2 tables: header row cell `Task` (or `#`), data rows like
    `| 1 — relocate e-mail lists | work_plan_task_1_relocate_email_lists.md | single task |`,
    `| 1 | work_plan_task_1_remove_open_source.md | single task |` (title only in the
    file name), `| 1 | work_plan_task_1_tikz_scenario_b.md — TikZ schematic of 2027
    Scenario B, render PDF + PNG, visual check | @lightweight-dev | — |` (number in `#`
    column; title AFTER the file name, em-dash separated).
  - Tasks, tier 3 file names (folder-relative, from `PlanEntry.file_contents` keys):
    `work_plan_task_1_prune_module.md` … e.g. orbit-plenary-i-slides has 24 such files and
    no `### Task` headings.

## Tasks

### Task 1: Core — extractors, Plan/ListingRow fields, render/parse/reconcile, tests
- **Files:** `src/agentic_scripts/workflows/roadmap_dev.py` (modify), `tests/test_roadmap_dev.py` (modify)
- **Do:**

  1. **`extract_goal(work_plan_text: str) -> str`** (new pure function, near
     `extract_title`): first match wins:
     - (a) Inline marker: first line matching
       `^\s*\*\*(?:Purpose|Goal):\*\*\s*(.*)$` (MULTILINE). The goal text is that line's
       remainder PLUS subsequent lines up to (not including) a blank line or a line
       starting with `#`, joined with single spaces, stripped.
     - (b) Section marker: first line matching `^##\s+(?:Purpose|Goal)\s*$` (MULTILINE).
       The goal text is the first paragraph of the section body (lines up to a blank line
       or the next `^#` heading), joined with single spaces, stripped.
     - (c) Fallback: `"—"`.
     Never raises on empty/None-ish input (`""` → `"—"`).
  2. **`extract_task_titles(work_plan_text: str, file_names: Sequence[str] = ()) ->
     tuple[tuple[str, str], ...]`** (new pure function): returns `(label, title)` pairs,
     first tier that yields ≥1 pair wins:
     - Tier 1 — headings: find all `^###\s+Task\s+(\d+)([a-z])?:\s*(.+)$` (MULTILINE).
       label = `f"{num}{letter}"` (e.g. `"1"`, `"3b"`). Title = the captured text with a
       trailing spec ref removed: cut at the FIRST match of
       `re.search(r"\s+(?:→|[—–-]\s+(?:see\s+)?)[—–]?\s*`?[^`|]*\.md`?", title)` — i.e. a
       `→` or `— see`/`—`/`-` connector followed by a backticked-or-bare `.md` file name
       (covers `lightweight-dev_task_*.md` refs too); strip the remainder. Keep the first
       occurrence per label; sort by `(int(num), letter)`.
       (The regex requires h3 + exactly `Task` + space, so `### Tasks 8–9 …: CANCELLED`,
       `### Bag-reader …`, and all h2 lines never match.)
     - Tier 2 — task table (only when tier 1 yields nothing): scan ALL markdown tables
       whose header row (a `| … |` line) contains a cell equal to `task` or `#` after
       `strip().lower()` — a plan may carry several (e.g. tasks added under a later
       `## Revision N` section, as in orbit-demo1-visual) — and collect rows from every
       one of them. For each data row (each subsequent `|`-line until a non-`|` line):
       - `num` = the cell under the `#` column when present, else the leading
         `^(\d+)([a-z]?)\b` of the `Task`-column cell; rows without a num are skipped.
       - title: let `cell` be the Task-column text; strip a leading
         `^(\d+)([a-z]?)\s*[—–-]?\s*`; if the rest starts with a (backticked-or-bare)
         `work_plan_task_<N>_<desc>.md` name, take the em/en-dash-separated tail after it
         as the title, else derive it from `desc` (underscores → spaces); if the rest is
         non-empty and has no file name, use it as the title (with the tier-1 ref-cut);
         if still empty, derive from a `work_plan_task_<N>_<desc>.md` found in ANY cell of
         the row (by the same N), else skip the row.
       - Keep first per label; sort by `(int(num), letter)`.
     - Tier 3 — file names (only when tiers 1–2 yield nothing): for each name in
       `file_names` (folder-relative basenames are enough) matching
       `^work_plan_task_(\d+)([a-z]?)_(.+)\.md$` → `(f"{num}{letter}", desc.replace("_", " "))`,
       sorted.
     - Else `()`. Never raises.
  3. **`Plan`:** add fields `goal: str` and `task_titles: tuple[tuple[str, str], ...]`
     (after `content_hash`); update the docstring Attributes/Note. `discover_plans`:
     compute `goal=extract_goal(entry.work_plan_text)` and
     `task_titles=extract_task_titles(entry.work_plan_text, list(entry.file_contents))`
     when building each `Plan` (note `entry.file_contents` keys are the folder-relative
     paths — the tier-3 regex anchors on the basename form, so pass the basenames or make
     the regex basename-anchored — your choice, test both).
  4. **`ListingRow`:** add `goal: str = ""` and `task_titles: tuple[tuple[str, str], ...]
     = ()` AS THE LAST TWO FIELDS WITH DEFAULTS (existing positional constructions in
     tests keep working; parsed rows carry no goal/tasks). Update docstring.
  5. **`render_listing`:** after appending each data-row line, append the detail row via a
     small private helper `_detail_row(goal: str, task_titles: tuple[tuple[str, str], ...])
     -> str`:
     `f"| — | — | **Goal:** {_escape_cell(goal.strip() or '—')} | **Tasks:** {_escape_cell(joined)} | — | — |"`
     where `joined = " · ".join(f"{label} {title}".strip() for label, title in task_titles)
     or "—"` and `_escape_cell(s) = s.replace("|", "\\|")` (a pipe in goal/task text must
     not break the table; the parser splits on raw `|`, so an escaped pipe still makes the
     row the wrong cell count → skipped, which is exactly the safety we want).
     Em dashes `—` (U+2014) in the 4 dash cells — NOT hyphens (the separator-row check is
     `set(cell) == {"-"}`; a hyphen-only cell plus the int-failure is what keeps the row
     out of the parser, but em dash is the contract — keep it byte-stable).
  6. **`parse_listing`:** NO code change needed (the detail row fails `int()` on its
     priority cell and is skipped) — but extend its docstring: document that the
     workflow-rendered detail row (`| — | — | **Goal:** … | **Tasks:** … | — | — |`) is
     deliberately skipped, and that the renderer must keep the priority cell non-numeric.
  7. **`reconcile`:** stamp `goal=plan.goal, task_titles=plan.task_titles` on ALL THREE
     `ListingRow` constructions (rule 2 new row, rule 1 `updated_by_key`, rule 5
     re-add). Parsed rows (from `parse_listing`) keep the defaults — reconcile output is
     always re-stamped from the scan, so the detail row is always fresh.
  8. **Module docstring:** update the listing-contract paragraph (L34–38) to mention the
     detail row (one extra 6-cell row per plan, workflow-owned, parser-skipped, derived
     from the Purpose/Goal line + task headings/tables/file names).
  9. **Tests** (`tests/test_roadmap_dev.py`):
     - New: `test_extract_goal_*` — inline `**Purpose:**`, inline `**Goal:**`, `## Purpose`
       section (wrapped paragraph joined with spaces), `## Goal` section, wrapped inline
       (continuation until blank line/heading), no marker → `"—"`, empty text → `"—"`,
       a `## E-mail lists` mention INSIDE the goal line must not truncate it.
     - New: `test_extract_task_titles_*` — heading order with `3b`/`5c` labels; ref-tail
       cuts for all four observed connector forms (incl. the `(single task, …)` paren after
       the ref and the `text → speaker notes` internal-arrow case — cut at the FIRST
       connector); `### Tasks 8–9 …: CANCELLED` and `### Bag-reader …` NOT matched; h2
       `## Tasks` NOT matched; table tier with all three observed cell shapes (bare `1` +
       File column derivation; `1 — <title>`; `#` column + `file.md — <title>`); file-name
       tier (incl. `work_plan_task_10_*.md` numeric sort 2,10 order); empty input → `()`.
     - New: `test_discover_plans_stamps_goal_and_tasks` — a fixture `PlanEntry` folder
       (`work_plan.md` with `**Purpose:**` + 2 `### Task N:` headings, plus
       `work_plan_task_1_*.md` in `file_contents`) → `Plan.goal`/`task_titles` stamped.
     - New: `test_parse_listing_skips_detail_rows` — a file with data rows each followed
       by a rendered detail row (build with `render_listing`) parses to EXACTLY the data
       rows; adversarial detail-row text: pipes in goal/tasks, `☑`, the words "approval"
       and "open", all-dash goal (`—`), digits in the goal cell — still zero extra rows.
     - New: `test_render_listing_emits_detail_rows` — exact expected bytes for 1–2 rows
       (goal present/absent, tasks present/absent, pipe escaping); byte-stable; single
       trailing newline.
     - New: `test_listing_pipeline_fixed_point` — the steady-state invariant with the
       detail row: build `plans` (fixture via `Plan` or `discover_plans`), `st0 =
       fresh_state()`; `file0 = render_listing(reconcile(plans, [], st0, now=NOW)[0])`;
       `st1 = …[1]`; `file1 = render_listing(reconcile(plans, parse_listing(file0), st1,
       now=NOW)[0])`; assert `file1 == file0` and that every data row in `file0` is
       immediately followed by its detail row.
     - Update: `test_parse_listing_round_trip_sample` (L321) — parse still yields the same
       data rows; the byte-identical-render assertion now expects the default detail row
       (`| — | — | **Goal:** — | **Tasks:** — | — | — |`) after each data row (build the
       expected string explicitly; parsed rows carry no goal/tasks).
     - Update: `test_render_listing_empty_stable_and_ordered` (L389) — expected output
       gains a detail row per data row (default `—` cells).
     - Update: any reconcile test asserting full `ListingRow(...)` equality against
       expected rows — the emitted rows now carry `goal`/`task_titles` from the fixture
       `Plan`s; add the matching fields to the expected constructions (or construct the
       fixture plans with known goal/tasks and assert them on the output rows).
- **Notes:** pure core stays pure — no git, no `datetime.now()`, no new imports needed
  beyond what the module already has (`re`, `dataclass` are in); `Sequence` may need a
  `collections.abc` import (already imported: `Callable` is from there — extend that
  import). Keep the em-dash byte exact (`\u2014` or literal `—`). Never change
  `_LISTING_HEADER`/`_LISTING_SEPARATOR`/`LISTING_COLUMNS`.
- **Acceptance:**
  1. `extract_goal`/`extract_task_titles` exist, pure, heavy docstrings; all the
     "real plan formats verified" cases above pass as tests.
  2. `Plan`/`ListingRow` carry the new fields; `discover_plans` and all three
     `reconcile` row constructions stamp them; `render_listing` emits the detail row
     under every data row; `parse_listing` skips it (regression-tested with adversarial text).
  3. `uv run pytest tests/test_roadmap_dev.py -v` fully green; `uv run pytest -q` (whole
     suite) green; `uv run ruff check .` and `uv run ruff format --check .` clean.
  4. Committed on `feature/roadmap-dev-workflow` with an `OC:`-prefixed message
     (e.g. `OC: roadmap-dev listing — goal + task-titles detail row (render + extract)`)
     staging ONLY the two modified files (explicit paths; no `git add -A`); NOT pushed
     (the orchestrator pushes); `planning/` and `config/` untouched by the commit.

## Out of Scope

- The listing-repo README (separate task), the live run (separate task), state schema,
  brief/drain changes, `oc_todo`/`mail_keeper`, config, the pre-existing
  `show_file` trailing-newline quirk.

## Notes

- [Assumption] Goal = Purpose/Goal markers (62/77 real plans) — the 15 plans without one
  show `—` by design (user accepted the fallback in the format choice).
- [Assumption] "label title" join: original plan numbering is preserved (incl. `3b`), not
  renumbered sequentially — the user asked for the titles of the tasks as the plan names
  them.
- [Note] The ref-tail cut is best-effort: a title that legitimately embeds
  "— see `x.md`" mid-text is cut there too — acceptable (spec refs are not titles).
- [Note] If a fixture `Plan` construction in an existing test breaks type checking because
  of the new required `Plan` fields, give the new `Plan` fields NO defaults (frozen dataclass,
  always stamped by `discover_plans`) and update the direct `Plan(...)` constructions in
  tests to pass them.
