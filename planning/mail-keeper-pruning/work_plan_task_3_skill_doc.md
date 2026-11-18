# Task Plan: mail-keeper — runner-owned pruning of checked daily entries (Task 3/4)

**Purpose:** Remove the agent-side pruning instructions from the global `mail-keeper` skill (user decision 2026-11-18: pruning is runner-only) and document the new division of responsibility, so the agent is never again expected — or observed — to perform (or fabricate) pruning.

## Objective

Edit `/root/.config/opencode/skills/mail-keeper/SKILL.md` (separate git repo from the code) so that: (1) the executable "Checkbox Lifecycle" pruning section is replaced by a concise **`## Pruning (runner-owned)`** section stating the runner does it on every scheduled run (incl. no-new-mail) and the agent never prunes; (2) `## Run` no longer contains a prune step (renumbered); (3) all dangling cross-references to the removed section are fixed; (4) the change is committed with an `OC:` prefix and pushed. Success: the skill contains no instruction telling the agent to remove entries or delete files; the run list is a gapless 1–7; cross-references resolve; repo clean + pushed.

## Context

- **Repo:** `/root/.config/opencode` (the global OpenCode config repo), branch `feature/flash-llamacpp-provider` (verified clean, up to date). Commit convention: `OC:` prefix, push after commit, current branch only (no PR, no new branch).
- **File:** `/root/.config/opencode/skills/mail-keeper/SKILL.md` (212 lines). Make **exactly** the four edits below (verbatim old → verbatim new); do not reflow or rewrite any other part of the file. The background (for your understanding only — do not quote it into the file): the pruning step lived agent-side and only ran when new mail triggered an agent dispatch, so checked entries accumulated forever on no-mail days; run `20261117T223001Z` even *reported* pruning it never performed. A deterministic runner module (`prune_daily`) now owns the lifecycle on every scheduled run (other tasks in this plan).
- The semantics the runner now owns (documented in the replacement section, kept faithful to the old `## Checkbox Lifecycle`): scan all `mail/daily/*.md`; remove each `- [x]` entry block (checkbox line + indented continuation lines, incl. inline drafts), up to the next checkbox line or EOF; append each pruned msg-id (the entry's `id:` line, no angle brackets) to `mail/daily/.pruned.jsonl`, dedup'd, one per line; delete any day-file left with no entries (day header only); old-format files with no checkbox lines are never pruned; vault notes and todo lines are never removed.
- The skill's `## Dedup / Idempotency` section (msg-id check **first** in `mail/daily/.pruned.jsonl` → "skipped (pruned)"; **then** vault grep) stays **unchanged** — it still works: `.pruned.jsonl` is now maintained by the runner, and unchecked/checked entries keep their `id:` lines greppable until pruned.

## Tasks

### Task 1: Replace `## Checkbox Lifecycle` with `## Pruning (runner-owned)`
- **Files:** `/root/.config/opencode/skills/mail-keeper/SKILL.md` (modify)
- **Do:** Replace the entire section from the `## Checkbox Lifecycle` heading through its last paragraph (the `Record: pruning produces no git activity…` line) with exactly:

  ```markdown
  ## Pruning (runner-owned)

  Pruning is performed by the **mail-keeper runner**, not the agent: on **every** scheduled run — including runs with no new mail — the runner scans `mail/daily/*.md`, removes each `- [x]` entry block (checkbox line plus its indented continuation lines, including inline drafts, up to the next checkbox line or EOF), appends each pruned msg-id (the entry's `id:` line, no angle brackets) to `mail/daily/.pruned.jsonl` (dedup'd, one per line), and deletes any day-file left with no entries (day header only). Old-format files (no checkbox lines) are never pruned; vault notes and todo lines are never removed by pruning.

  The agent operates on the post-prune state and **never prunes** (this step used to be agent-side; it was removed 2026-11-18 because it only ran when new mail triggered an agent dispatch, and a run once reported pruning it never performed). Consequence for a manual agent invocation (no runner): checked entries are not removed and survive until the next scheduled run — their msg-ids stay greppable in the day-files, so the dedup skips still hold; nothing is double-written.

  Pruning produces no git activity (git-ignored paths); the runner reports pruned entries / deleted files in its run log, not in the agent's result report.
  ```
- **Notes:** Keep the section between `## Daily Report` and `## PII Guardrail` (i.e. in the current position — the old section sits there).
- **Acceptance:**
  1. `grep -n "Checkbox Lifecycle" SKILL.md` → zero hits (no heading, no cross-references).
  2. The new section's text appears verbatim once, in the same position.

### Task 2: Fix the `## Daily Report` cross-reference (Rules paragraph)
- **Files:** `/root/.config/opencode/skills/mail-keeper/SKILL.md` (modify)
- **Do:** In the `## Daily Report` → `Rules:` paragraph, replace the sentence fragment
  `- [ ] is the Obsidian task checkbox (the user ticks handled mails; the agent prunes `- [x]` entries — see the Checkbox Lifecycle section added in Task 2).`
  with
  `- [ ] is the Obsidian task checkbox (the user ticks handled mails; the runner prunes `- [x]` entries between runs — see `## Pruning (runner-owned)`).`
- **Acceptance:**
  1. `grep -n "runner prunes" SKILL.md` → one hit; the old "agent prunes" phrasing is gone.

### Task 3: Remove the prune step from `## Run` + drop the report clause
- **Files:** `/root/.config/opencode/skills/mail-keeper/SKILL.md` (modify)
- **Do:**
  1. In `## Run`, delete current step 3 entirely:
     `3. **Prune:** scan `mail/daily/*.md` per `## Checkbox Lifecycle` — remove `- [x]` entry blocks, append each pruned msg-id to `mail/daily/.pruned.jsonl`, delete emptied day-files — **before any manifest processing**.`
     and renumber the remaining steps so the list is a gapless `1.`–`7.` (old steps 4–8 become 3–7).
  2. In the (renumbered) final step — currently: `8. Commit/push per the commit policy (or no-op report); **final message = result report** in the `skill: sub-agent-communication` result-report shape, adapted as described under Report Shape below — including the pruning summary when pruning removed anything.` — delete the trailing clause ` — including the pruning summary when pruning removed anything`.
  3. In `## Report Shape` → `## Summary` line, replace
     `<what was done this run — manifest size, classes found, writes/drafts made; state the pruning outcome when non-zero: entries pruned, files deleted>`
     with
     `<what was done this run — manifest size, classes found, writes/drafts made>`.
- **Notes:** Check the whole file afterwards for any remaining "prun" occurrences — after this edit the only pruning content is the new `## Pruning (runner-owned)` section and the one `## Daily Report` cross-reference (Task 2). `grep -in "prun" SKILL.md` should return only those (plus the word "pruned" inside the new section and the unchanged `## Dedup / Idempotency` "skipped (pruned)" phrasing).
- **Acceptance:**
  1. `## Run` is a numbered list `1.`–`7.` with no missing numbers and no prune step.
  2. No sentence anywhere instructs the agent to remove entries, delete day-files, or append to `.pruned.jsonl`.
  3. The `## Summary` report line no longer mentions pruning.

### Task 4: Commit + push in the config repo
- **Files:** (git) `/root/.config/opencode`
- **Do:** `git -C /root/.config/opencode add skills/mail-keeper/SKILL.md` (that exact path only — never `git add -A`), commit `OC: mail-keeper skill — pruning is runner-owned (remove agent-side step)`, `git -C /root/.config/opencode push`.
- **Acceptance:**
  1. New commit present in `git log --oneline -3`, on `feature/flash-llamacpp-provider`, pushed (upstream in sync — `git status` shows nothing to commit and no ahead/behind).
  2. Only `skills/mail-keeper/SKILL.md` in the commit (`git show --stat HEAD`).

## Out of Scope

- No other skill/agent files, no `opencode.jsonc`, no code in `agentic_scripts` (Tasks 1/2/4 of the global plan), no changes to the `## Dedup / Idempotency`, `## Drafts`, `## PII Guardrail`, `## Commit Policy`, `## Hard Rules` sections.

## Notes

- [Assumption] The agent will not be told *what* the prune output looks like beyond the division of responsibility; the skill stays instruction-focused (it is an executable brief for the agent, not system documentation).
- Result report path: `planning/mail-keeper-pruning/lightweight_dev_task_3_skill_doc.md` (sub-agent-communication result-report format).
