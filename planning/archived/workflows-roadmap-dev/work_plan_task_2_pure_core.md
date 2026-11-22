# Task Plan: T2 — `roadmap_dev` pure core (identity, discovery, listing, reconciler, reaper, renderers)

**Purpose:** Create `agentic_scripts/workflows/roadmap_dev.py` as a module of small, independently unit-testable pure functions and dataclasses — the plan identity + discovery logic, the `plans.md` listing parser/renderer, the reconciler (user-cell preservation + row-drop rules), the state machine + reaper, and the brief/PR renderers — mirroring the `oc_todo.py` "pure helpers + workflow shell" structure, with the workflow shell stubbed until Tasks 3/4.

## Objective

Ship the deterministic core of the `roadmap-dev` workflow so that Tasks 3/4 (git scan, drain, job pipeline) are thin wiring. Every function is pure (no git/network/subprocess/`datetime.now()` at module call sites — inject `now` where needed) and covered by hermetic unit tests in `tests/test_roadmap_dev.py`.

## Context

- Work in `/workspace/Python/agentic_scripts` (branch `feature/roadmap-dev-workflow`). T1 has landed: `config.RoadmapPrompts` (fields: `allowed_repos`, `listing_repo`, `listing_repo_url`, `listing_path`, `listing_branch`, `run_timeout_minutes=480`, `test_commands`, `repo_urls`) and `WorkflowEntry.gate` exist. Read first: `src/agentic_scripts/workflows/oc_todo.py` (structure to mirror: constants → identity/layout helpers → pure core → renderers → workflow shell with constructor-injected seams; Google-style docstrings; `dataclass`/frozen patterns), `src/agentic_scripts/config.py`, `tests/test_oc_todo.py` (test style), `tests/test_gate.py`.
- **State document** (`state/roadmap-dev.json`, key `_STATE_KEY = "roadmap-dev"`, `_STATE_VERSION = 1`):

```json
{
  "version": 1,
  "plans": {
    "<identity12>": {
      "identity": "<12hex>", "repo": "owner/name", "branch": "main",
      "path": "planning/topic/work_plan.md", "title": "…",
      "content_hash": "<sha256 hex>", "state": "open|pending|review|success|failure",
      "attempt": 0, "started_at": null, "finished_at": null,
      "pid": null, "branch_name": null, "commit_sha": null,
      "last_error": null, "last_run_id": null, "updated_at": "…ISO-8601 UTC…"
    }
  }
}
```

  `fresh_state()` / `validate_state(st)` / `make_plan_entry(plan, state, **fields)` mirror the `oc_todo` versions (`fresh_state`, `validate_state`, `make_entry`), including the "delete `state/roadmap-dev.json`" operator message on schema mismatch. `updated_at` stamped from an injected `now: datetime` argument (UTC ISO-8601), never from a bare `datetime.now()` inside the pure functions.
- **Plan identity** (reviewed-plan contract): identity = repo + branch + plan-folder path + **content hash of the plan folder EXCLUDING `questions.md` and `failure.md`** (workflow-written diagnostics must not change identity; any user edit of any other plan file = new identity = new row).
- **States:** `open` (startable with ☑), `pending` (job running; not startable), `review` (major questions in `questions.md`; startable once user re-☑'s; approval was removed by the workflow), `success` (attempt branch pushed with implementation + archived plan folder — NO PR by the agent, human verifies/merges; not startable; removable via `remove` ☑), `failure` (`failure.md` on the plan's branch; not startable; re-arm = user sets state cell `open`). **No GitHub API anywhere in this workflow** (user decision 2026-11-21: PR creation is human-level verification; all git over SSH).
- **Listing contract** (`ARP_prompts/plans.md`; repo and branch are HEADERS, not columns):

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

  Columns: `approval` (user ☐/☑), `priority` (int, ascending; 1 = first; ties by row order), `plan` (path to `work_plan.md`), `title`, `state`, `remove` (user ☐/☑; valid on `success` rows → row deleted next scan). Sections persist while they have — or historically had — a known plan (rows, not sections, are dropped per the reconciler rules below).
- **Layout helpers** (mirror `oc_todo.clone_dir`/`worktree_dir`): `_CLONES_SUBDIR="clones"`, `_WT_SUBDIR="wt"`, `_DIAG_SUBDIR="diag"`, `_PROMPTS_SUBDIR="prompts"`; `clone_dir(sandbox_dir, repo)` → `<sandbox>/roadmap-dev/clones/<owner>__<name>` (note: the workflow-level sandbox root `<sandbox>/roadmap-dev/` is composed by the workflow shell via `ctx.sandbox_dir / "roadmap-dev"` — the helpers take the already-composed sandbox root as `oc_todo` does with its own root), `plan_worktree_dir(sandbox_dir, repo, identity)`, `diag_worktree_dir(sandbox_dir, repo, identity)`, `prompts_clone_dir(sandbox_dir)`, `repo_slug(repo)` (reuse the `<owner>__<name>` convention).
- Style: `from __future__ import annotations`; sha1/sha256 via `hashlib` (`.encode("utf-8")` byte-stable, `# noqa: UP012` where the style flag objects, as in `oc_todo.todo_id`); ruff clean; docstrings with Purpose/Rationale/Args/Returns.
- The workflow shell in this task: `create(config) -> RoadmapDevWorkflow` (reads `config.roadmap_prompts`) and `class RoadmapDevWorkflow` with `name = "roadmap-dev"`, `__init__(self, settings, *, git=None, runner=None, active_sessions=None, now_fn=None)` (constructor-injected seams, `oc_todo` pattern — NO `github` seam: this workflow never calls the GitHub API; `active_sessions: Callable[[], int] | None` default None → `agentic_scripts.sessions.read_active_sessions`; `now_fn: Callable[[], datetime] | None` default None → `datetime.now`), and `run(ctx)` that for NOW only does: load+validate state, return `WorkflowResult(status="ok", actions=["phase-1 not implemented (Task 3)"])` when `allowed_repos` is empty (action `no repos configured — nothing to scan`), else raise nothing but return `status="ok"` with action `phase-1 not implemented (Task 3)` — Tasks 3/4 replace `run`'s body. Wrap `_run` in the exception→`status="error"` guard exactly like `OCTodoWorkflow.run`.

## Tasks

### Task 1: Identity + discovery + state schema (pure)
- **Files:** `src/agentic_scripts/workflows/roadmap_dev.py` (create)
- **Do:**
  - `plan_folder_hash(file_texts: dict[str, str]) -> str` — sha256 hex over sorted `(relpath, content)` pairs, **skipping** files whose basename is `questions.md` or `failure.md` (constant `DIAGNOSTIC_FILES = frozenset({"questions.md", "failure.md"})`).
  - `plan_identity(repo, branch, plan_path, content_hash) -> str` — first 12 hex of sha1 of `f"{repo}|{branch}|{plan_path}|{content_hash}"` (mirror `todo_id`).
  - `branch_name(identity: str, attempt: int) -> str` — `f"roadmap-dev/{identity}-{attempt}"` (fresh-branch invariant: always this prefix; never a protected branch).
  - `extract_title(work_plan_text: str) -> str` — text of the first line matching `^#\s+` (ATX h1, stripped of leading `#` and whitespace, single-line); fallback `"Untitled plan"` when absent.
  - `Plan` frozen dataclass: `repo, branch, path, title, content_hash` + `@property identity` (recomputed via `plan_identity`) + `@property branch_name`? (no — attempt is not known here; branch name is computed by the pipeline). `@property topic` (the plan folder dir = `path`'s parent).
  - `discover_plans(repo, branch, entries: list[PlanEntry]) -> list[Plan]` — pure: `PlanEntry` frozen dataclass = `{"dir": str (plan folder path, e.g. "planning/orbit-sim"), "work_plan_text": str | None, "file_texts": dict[str,str] (relative paths within the folder)}` built by the scan layer (Task 3) from `git ls-tree`/`show_file`. Rules: a valid plan requires `work_plan_text is not None` (malformed entries skipped, never raised); the dir must be under `planning/` (top-level segment) and must NOT contain an `archived` path segment (constant `ARCHIVED_SEGMENT = "archived"`); duplicate dirs impossible (scan layer guarantees). Returns plans sorted by `(dir,)` for determinism.
  - State schema helpers `fresh_state()`, `validate_state(st)`, `make_plan_entry(plan, state, *, now, **fields)` per Context (with the `attempts`→`attempt` naming: entry field is `attempt`, int default 0).
- **Acceptance:**
  1. `plan_folder_hash` ignores added/edited `questions.md`/`failure.md` (same hash), changes on any other file change (different hash); deterministic across dict orderings.
  2. `plan_identity` is 12 hex chars; stable for identical inputs; differs when any of repo/branch/path/hash differ.
  3. `discover_plans` keeps valid folders, drops entries with `work_plan_text=None` (malformed) and any folder whose path contains an `archived` segment; sorted by dir.
  4. `extract_title` handles `# Title` (→ `Title`), indented `#  Double` (→ `Double`), no-h1 (→ `Untitled plan`).

### Task 2: Listing parser + renderer (pure, byte-stable)
- **Files:** `src/agentic_scripts/workflows/roadmap_dev.py` (modify), `tests/test_roadmap_dev.py` (create)
- **Do:**
  - `LISTING_COLUMNS = ("approval", "priority", "plan", "title", "state", "remove")` — exact header row `| approval | priority | plan | title | state | remove |` and separator `|----------|----------|------|-------|-------|--------|` (copy the exact separator widths from the contract sample; the renderer emits this exact form).
  - `ListingRow` dataclass: `repo_url: str` (section header, e.g. `https://github.com/y2d2/ARP_MPE.git`), `branch: str`, `approval: bool`, `priority: int`, `plan: str`, `title: str`, `state: str`, `remove: bool`.
  - `parse_listing(md: str) -> list[ListingRow]` — defensive parse: `# ` lines open a repo section (the rest of the line = repo_url, stripped; a `#` line while no section context is valid; non-matching `#`/`##` free text is skipped), `## ` lines set the current branch (only inside a repo section), table rows with exactly 6 cells are parsed (checkbox cell: `☑` → True, `☐`/empty → False — also accept `[x]`/`[ ]`? NO: only the `☑`/`☐` glyphs, anything else → False; priority: int(cell) — non-int cell → skip the whole row silently); rows outside any repo/branch section are skipped; the header + separator rows are skipped. Never raises on malformed input.
  - `render_listing(rows: list[ListingRow]) -> str` — deterministic: sections grouped by `(repo_url, branch)` preserving first-appearance order of rows; within a section, rows in given order; emit `# <repo_url>` / `## <branch>` + exact header + separator + one line per row `| ☐ | <priority> | <plan> | <title> | <state> | ☐ |`; no trailing spaces; single trailing newline; empty input → `""` (empty string, no header — an empty listing is a truly empty file).
- **Acceptance:**
  1. Round-trip: `render_listing(parse_listing(sample)) == sample` for the exact 2-repo/2-branch sample in Context (byte-identical, incl. trailing newline).
  2. Malformed input (wrong column count, non-int priority, text between sections, unknown headers) → rows skipped, no exception.
  3. `render_listing([]) == ""`; rendering is stable across repeated calls (byte-stable).

### Task 3: Reconciler + state machine + reaper (pure)
- **Files:** `src/agentic_scripts/workflows/roadmap_dev.py` (modify), `tests/test_roadmap_dev.py` (modify — extend)
- **Do:**
  - `reconcile(plans: list[Plan], existing_rows: list[ListingRow], state_doc: dict, *, now) -> tuple[list[ListingRow], dict, list[str]]` — returns `(new_rows, new_state_doc, actions_log)`. `new_state_doc` is a fresh dict (copy-on-write; the input doc is not mutated). Matching key = identity (row identity = `plan_identity(row.repo_slug→repo…)`) — NOTE: rows carry `repo_url`, so derive repo from it: `repo_from_url(repo_url)` helper strips `https://` and trailing `.git` → `owner/name` (accept `git@github.com:owner/name.git` too by stripping `git@github.com:`). Rules, in order, per plan (identity-scoped):
    1. **Scanned + in state** → row exists (or is created): workflow-owned cells updated: `title` (from scan), `state` (from state doc) — EXCEPT the sanctioned re-arm: if state-doc state is `failure` and the existing row's state cell is `open`, the user's `open` wins (state doc synced to `open`; log `re-armed <id> (user set open)`); any other row/state divergence → workflow state wins (row cell set to state-doc value). User-owned cells always preserved from the existing row: `approval`, `priority`, `remove`.
    2. **Scanned + not in state** → new row: `approval=False`, `remove=False`, `priority` = (max priority among existing rows in the same `(repo_url, branch)` table) + 1, or 1 when the table is empty/absent; `state="open"`; new state entry (`state="open"`, `attempt=0`); log `discovered <id> (<repo> @ <branch>)`.
    3. **In state + not scanned** (vanished: archived/merged/deleted, repo removed from allowlist, or plan edited into a new identity — the OLD identity then vanishes) → row dropped; state entry KEPT (forensics/PR-dedup); log `dropped row <id> (plan no longer in scan)`. A `success` entry whose PR merged is the normal case.
    4. **Ghost rows** (row in neither scan nor state) → dropped; log `dropped ghost row <plan> (no state entry)`.
    5. **`remove` ☑ on a `success` row** (scanned or not) → row dropped (state kept); if the plan is still scanned it is re-added in the same pass as a `success` row (per rule 1/2 ordering: process the removal after computing keep-set; net effect = row reappears with state `success`, fresh `remove=False` cell, `approval` as before, priority max+1 — the documented "harmless re-appearance"). Log `removed <id> (user remove tick)`.
    6. State entries are never deleted by the reconciler.
    - Output row ordering: for each section (first-appearance order across `existing_rows` first, then sections that only appear in the scan), rows in existing order, new rows appended at the end of their section.
  - `force_unapproved` handling: signature `reconcile(..., force_unapproved: set[str] = frozenset())` — identities in the set get `approval=False` on their (existing or new) row in this pass (the workflow removes the checkmark after a `questions` outcome — logged `unapproved <id> (questions raised)`); this is the ONE sanctioned user-cell overwrite.
  - `reap_orphans(state_doc: dict, *, now) -> tuple[dict, list[str]]` — every entry with `state == "pending"` → `state="open"` (infra death = auto-retry), `last_error="orphaned pending (crash/restart) — reaped"`, `pid=None`, `started_at=None`, log per identity; returns new doc + logs. (Worktree cleanup is the pipeline's job, Task 3.)
  - Job-outcome transition helper `apply_job_outcome(entry: dict, outcome: str, *, now, **fields) -> dict` — maps the pipeline outcome to a new entry: `"success"` → state `success` + `pr_number/pr_url/commit_sha` fields; `"questions"` → state `review`; `"failure"` → state `failure` + `last_error`; sets `finished_at=now`, `attempt` unchanged (incremented at start, by the pipeline). Pure; used by Task 4.
- **Acceptance:**
  1. New-plan discovery: row appears under the right `# repo`/`## branch` section with `open`, no checkmarks, priority `max+1` (and `1` in an empty table); state entry created.
  2. User-cell preservation: seed rows with `approval=True, priority=5, remove=False`; reconcile 3× with unchanged scan+state → output identical to input (byte-stable md via renderer), state doc unchanged.
  3. Re-arm: state-doc `failure` + row state `open` → state doc becomes `open`, row kept `open`, log line present.
  4. Non-failure state divergence: row says `open`, state doc says `review` → row becomes `review` (workflow wins).
  5. `remove` ☑ on `success` (plan still scanned, state `success`) → row dropped then re-added as `success` in the same pass (net: present, `remove=False`); when the plan is NOT scanned → simply dropped.
  6. Vanished plan (state entry, no scan) → row dropped, entry kept; ghost row (no scan, no state) → dropped.
  7. `force_unapproved={id}` → that row's `approval=False` in the output (log present).
  8. `reap_orphans` flips all `pending`→`open` (others untouched), logs each; `apply_job_outcome` sets the documented fields for all three outcomes.

### Task 4: Brief + report renderers (pure, byte-stable)
- **Files:** `src/agentic_scripts/workflows/roadmap_dev.py` (modify), `tests/test_roadmap_dev.py` (modify — extend)
- **Do:**
  - `extract_report_sections(final_text: str | None) -> dict` — copy the `oc_todo` version verbatim in behavior (same headings map, same return shape `{summary, files, tests, blockers, has_report}`) — deliberately duplicated (no cross-workflow imports; see `oc_todo._is_step_exhausted`'s note). Used by the pipeline to gate on `blockers` and quote the report in the run log.
  - `job_status_from_report(final_text: str | None) -> str | None` — scan the report (case-insensitive) for a line matching `^\s*status\s*:\s*(success|questions|failure)\s*$` (first match wins); return the lowercase status or None. (The brief below mandates this line.)
  - `render_brief(*, run_id, plan: Plan, repo_url: str, attempt: int, timeout_minutes: int, test_cmd: str | None) -> str` — the autonomy brief (load-bearing; the 27B planner reads it by eye). Exact content (single string, `"\n".join([...])` style, no extra blank lines):

    ```
    roadmap-dev autonomous run {run_id} — execute ONE approved plan, pre-approved, no user present.

    Plan: {plan.path}
    Repo: {repo_url}   Branch: {plan.branch}   Title: {plan.title}
    Attempt: {attempt}   Hard budget: {timeout_minutes} minutes (process will be killed at the deadline).

    You are running headless. There is NO user: the question tool is unavailable, nothing is
    pending your approval — this run is fully pre-approved. Do NOT ask questions, do NOT wait.

    1. REVIEW THE PLAN. Read {plan.path} and every task file in its folder.
       - MAJOR question = anything that would change scope, requirements, or dependencies
         (NOT an implementation detail). If — and only if — a major open question exists:
         write it to {plan.topic}/questions.md (numbered questions, each with context and
         exactly what you need answered), change nothing else, and finish with the result
         report whose status line is "Status: questions". Do NOT execute any task.
       - MINOR things: decide yourself; record each decision in your result report only.
       - If {plan.topic}/questions.md already contains user answers, read them and proceed
         (they answer a previous round of this same plan).
    2. EXECUTE IN SEQUENCE. Dispatch @lightweight-dev ONE small self-contained task at a time
       — strictly sequential, NEVER in parallel — and verify each task's acceptance criteria
       from its result report before dispatching the next.
    3. REPORT. Your final message must be the result report:
       ## Summary / ## Files / ## Tests / ## Blockers
       plus an explicit status line, exactly one of:
         Status: success      (every task done, every acceptance criterion verified)
         Status: questions    (major questions written to questions.md, no task executed)
         Status: failure      (cannot proceed; explain why in Blockers)
       Test command: {test_cmd if test_cmd else "none configured — the runner runs tests itself"}

    Git rules: do NOT run git commit or git push — the runner owns git and will commit,
    archive the plan folder and push the branch after you exit (a human opens the PR).
    Work ONLY inside this worktree.
    ```

  - `render_commit_title(plan: Plan) -> str` — the implementation commit message: `f"OC: {plan.title}"` truncated to 72 chars total (no ellipsis), mirroring `oc_todo.render_pr_title`'s truncation discipline.
  - `archive_commit_message(identity: str, run_id: str) -> str` — `f"OC: roadmap-dev: archive plan {identity} (run {run_id})"`.
  - `diag_commit_message(identity: str, kind: str, run_id: str) -> str` — `kind ∈ {"questions", "failure"}`: `f"OC: roadmap-dev: {identity} — {kind} (run {run_id})"`.
  - (NO PR title/body renderers — the agent never opens PRs; the pushed branch + its commit messages are the delivery surface, the human opens the PR.)
- **Acceptance:**
  1. `render_brief` output contains (assert each verbatim): `"pre-approved, no user present"`, `"question tool is unavailable"`, `"NEVER in parallel"`, the plan path, the attempt number, the timeout value, and the exact three `Status: …` lines; byte-stable across calls (assert equality of two renders).
  2. `job_status_from_report`: `"Status: questions"` mid-report → `"questions"`; no status line → None; `"status: SUCCESS"` (lowercase label) → `"success"`; `"Status: succeeded"` (not in the allowed set on that line) → None unless a real line exists.
  3. `extract_report_sections` matches `oc_todo` behavior on a sample report (same assertions style as `tests/test_oc_todo.py` for that function).
  4. `render_commit_title` = `OC: <title>` truncated at 72 chars total (assert on a >72-char title); `archive_commit_message` / `diag_commit_message` produce the exact documented strings.

### Task 5: Workflow shell stub
- **Files:** `src/agentic_scripts/workflows/roadmap_dev.py` (modify), `tests/test_roadmap_dev.py` (modify — extend)
- **Do:** `create(config)` + `RoadmapDevWorkflow` shell per Context (name, seams — note: NO `github` seam, `run` guard, phase-1-not-implemented actions). Test: `create` on a T1-style config returns an instance with `name == "roadmap-dev"`; `run` with empty `allowed_repos` → `status="ok"`, exactly one action `no repos configured — nothing to scan`, no state write (state file absent afterwards); with non-empty `allowed_repos` → `status="ok"` + action `phase-1 not implemented (Task 3)`.
- **Acceptance:**
  1. `uv run pytest tests/test_roadmap_dev.py -v` fully green; `uv run pytest -v` (whole suite) green; ruff check + format clean.

## Out of Scope

- No git, no network, no subprocess, no threads, no scheduler changes — all in Tasks 3/4.
- No changes to existing modules (this task only creates `roadmap_dev.py` + its test file).
- No `workflows.yaml` changes (T1 already registered the disabled entry; the module now exists but stays disabled until T6).

## Notes

- **[Assumption] `repo_from_url`** accepts both `https://github.com/<owner>/<name>.git` and `git@github.com:<owner>/<name>.git` (and without `.git`); any other form → the row is treated as a ghost (documented; the renderer only ever emits the https form, so this only matters for hand-edited rows).
- **[Note] Row identity vs. state identity:** both are the 12-hex `plan_identity`; state entries are keyed by it; the reconciler never compares titles for matching.
- **[Note] Keep the module importable with zero side effects** — T1's config loader import-checks only *enabled* entries, but later tasks' smoke tests import the module with the disabled entry; a clean import must not touch the filesystem.
- **[Note] Determinism:** no `datetime.now()` in pure functions — always the injected `now`; no `random`/set-iteration order leaks (sort where order matters).
