# agentic_scripts — OC-Todo Resolver Workflow Plan

**Purpose:** The OC-todo resolver workflow: scan a configurable set of GitHub repos across all branches for `OC-todo:` comments and open one pull request per resolved todo via a headless OpenCode agent. Split from `agentic_workflows_plan.md` (2026-10-19; the original file is deleted — full pre-split content is in git history at `628df52`).

**Depends on:** `planning/workflows-base/workflows-base_plan.md` — scheduler gate (Task 1), shared foundation primitives: validated config, durable state, git helpers, agent runner (Task 2), setup/smoke (Task 3). Sibling: `planning/workflows-mail-keeper/workflows-mail-keeper_plan.md` (independent of this plan).

## Objective

Implement the OC-todo resolver workflow of the `agentic_scripts` load-aware system: scan a configurable set of GitHub repos across all branches for `OC-todo:` comments and open one pull request per resolved todo via a headless OpenCode agent. Success = with the gate open, the workflow produces its observable outputs (one reviewable PR per unhandled todo) idempotently; with the gate closed, runs exit as no-ops without touching any repo.

## Context

- **Existing conventions (local evidence):** the `OC-todo:` comment marker is used across the user's repos (e.g. `#OC-todo` lines documented in /workspace/Python/ARP_IMU/planning/archived/attitude-estimator-refactor/attitude_estimator_refactor_plan.md; `% oc-todo:` in /workspace/Latex/Relative-localisation-tutorial-slides/slides/introduction/06_global_localisation.tex, which also references an `oc-original` comment that must survive). Commits follow the `OC:` prefix (git-workflow skill).
- **GitHub limits (why local clones):** the GitHub code-search REST API "only [considers] the default branch" and only files < 384 KB, at 10 req/min authenticated → [GitHub REST search docs](https://docs.github.com/en/rest/search/search).
- Shared system context (environment, agent infrastructure, OpenCode config environment, Python/ops conventions) lives in the base plan.

## Functional Tasks

### Task 1: OC-Todo Resolver Workflow
- **Goal:** For every configured GitHub repo, find every `OC-todo:` comment on every branch; for each one not already handled, have the agent produce a fix in a sandboxed worktree; commit, push a branch, and open one PR per todo that a human can review and merge.
- **Why this approach:**
  - **[Decision: scan = local clone + per-branch grep]** Value = full local clone (all remote branches) and `git grep` per branch, because the GitHub code-search API only covers the default branch, caps files at 384 KB, and is rate-limited to 10 req/min → [GitHub REST search docs](https://docs.github.com/en/rest/search/search); a local clone is deterministic, offline, and branch-complete (own analysis).
  - **[Decision: pattern]** Value = the strict, case-sensitive canonical marker `OC-todo:`, because the user chose the canonical form over a case-insensitive broad pattern (2026-10-14); matching is limited to text files with standard binary/build exclusions (own analysis of the marker's usage in local repos).
  - **[Decision: sandbox]** Value = one git worktree per todo, branched from the branch containing the todo, so concurrent todos and repos never share a checkout and no work happens on a shared clone's branches (own analysis; worktrees keep the full-clone history available to the agent).
  - **[Decision: agent scope]** Value = deterministic Python does clone/fetch, scanning, worktree setup, commit, push, and PR creation; the OpenCode agent only edits code inside the worktree (implement the todo, delete the `OC-todo:` comment — unless the comment or an `oc-original`-style note instructs keeping it — and run the project's test command if one is configured), because git/PR mechanics must be exact and auditable while code understanding is the agent's job (own analysis; `oc-original` convention observed in local repos, e.g. /workspace/Latex/Relative-localisation-tutorial-slides/slides/introduction/06_global_localisation.tex).
  - **[Decision: output = one PR per todo]** Value = push to a dedicated branch and open a PR against the branch that contained the todo, with the PR body quoting the exact comment, file, line, and the agent's summary, because the user chose review-before-merge over auto-push (2026-10-14); PRs are created via the GitHub REST API with the configured PAT because `gh` is not installed (verified 2026-10-14).
  - **[Decision: idempotency]** Value = a todo is skipped when its state says a PR was already opened, or an existing PR is found for the todo's dedicated branch; merged-and-comment-gone todos flip to resolved on the next scan, because the timer will re-scan forever (own analysis).
  - **[Decision: caps and failure]** Value = per-run caps (max todos per repo, agent `steps` cap, hard timeout) and retry-on-next-run semantics: a failed todo is recorded with its error and re-attempted on the next gate-open run, never leaving a partial push, because quiet windows are bounded and a hung agent must not block the schedule (research: /workspace/Research/ai-agent-workflow/agent-token-budget-steps.md — `steps` as the stop-and-report mechanism).
- **Acceptance criteria:**
  - Given a fixture repo with two `OC-todo:` comments on two different branches, one gate-open run produces exactly two PRs, each targeting the branch that contained its todo.
  - Each PR body quotes the exact `OC-todo:` comment text, names the file and line, and summarizes the change; the diff removes the comment (unless a keep-instruction applies).
  - Re-running with no repo changes opens zero new PRs; after merging a PR, the next run marks the todo resolved and does not reopen it.
  - An agent run that times out or exhausts `steps` leaves the todo in a failed/retry state, logs the reason, and the next run re-attempts it.
  - No workflow ever pushes to a protected or pre-existing branch — only freshly created per-todo branches are pushed.

## Alternatives Considered

1. **GitHub code-search API instead of local clones** — Rejected: default-branch-only, 384 KB file cap, 10 req/min → [GitHub REST search docs](https://docs.github.com/en/rest/search/search).
2. **Auto-push / auto-merge for OC-todo fixes** — Rejected by user (chose one PR per todo for human review, 2026-10-14).

## Notes

- **[Assumption]** The initial OC-todo repo list is empty; acceptance testing uses a local fixture repo (user decision, 2026-10-14).
- **[Decision-confirmed]** `OC-todo:` matching is strict and case-sensitive per user choice (2026-10-14) — lowercase `oc-todo` or `#OC-todo` (no colon) instances observed in older notes will **not** match; treat that as intentional pruning of stale markers.
- **[Risk]** Agent quality: a bad "fix" PR is caught in review (that is the PR-per-todo design).
