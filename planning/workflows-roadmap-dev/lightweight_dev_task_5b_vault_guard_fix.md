# lightweight-dev Output — Task: T5b vault-submodule guard fix

**Task:** #5b    **Session:** workflows-roadmap-dev    **Date:** 2026-11-22

## Summary

Inverted the over-conservative vault guard in `scripts/bootstrap_task_overview.sh` per the
ratified 2026-11-22 semantics (user decision B2: commit the submodule-only paths NOW while
the rest of the vault stays dirty). The old guard (`vault_unrelated_change`) refused when
the vault had ANY uncommitted change OUTSIDE `.gitmodules`/`autonomous_task_overview` — so
unrelated dirty work (the user's slides files) could never be worked around, even though
the submodule commit stages exactly those two paths and can never sweep in other work.
The new guard (`vault_staged_path_change`) emits the porcelain lines for uncommitted
changes ON `.gitmodules` or INSIDE `autonomous_task_overview` — the only paths that could
be swept into the commit — and refuses (exit 1) only on those; the dry-run branch and the
real refusal now state WHY (these are the only paths the submodule commit stages;
in-progress work there would be swept in — commit or stash it first) and list the
offending lines. Header comment, usage text, variable (`dirty` → `staged_change`), and
helper name all updated to the new meaning. `set -euo pipefail`, pure bash+git+coreutils
(no PAT/curl/python), never force-push; preflight, push_initial, ordering, idempotency
untouched. All 4 acceptance items verified hermetically (33/33 checks; local bare listing
remote via `insteadOf` in a throwaway `GIT_CONFIG_GLOBAL` — no real GitHub touched),
including the full clean-vault regression flow and the dirty-unrelated-file PROCEED case.
Committed as a single `OC:`-prefixed commit (1 explicit path staged — the script only;
not pushed, per dispatch).

## Files

| File | Action | Why |
|---|---|---|
| `scripts/bootstrap_task_overview.sh` | modify | Guard inverted: helper `vault_unrelated_change` → `vault_staged_path_change` (now emits porcelain lines for changes ON `.gitmodules` or INSIDE `autonomous_task_overview` instead of everything outside them); refusal + dry-run messages + variable renamed to state the new semantics (refuse only when in-progress work sits on the two paths the commit stages); header comment (~L8) and usage text (~L50) updated to match. Nothing else in the script touched. |

## Build / Tests

- `bash -n scripts/bootstrap_task_overview.sh`: PASS — clean.
- `grep -n "unrelated\|outside" scripts/bootstrap_task_overview.sh`: PASS — zero matches (old-guard wording fully gone from comments and messages).
- Hermetic fixture matrix (33 checks, `/tmp/opencode/t5b/run_matrix.sh`; scratch `git init` vaults + local bare listing remote; git identity set in-test in a throwaway `GIT_CONFIG_GLOBAL`; `git@github.com:y2d2/autonomous_task_overview.git` rewritten via `insteadOf`; `protocol.file.allow=always` for the file-protocol submodule clone on git 2.43; no real GitHub, no repo test files added): PASS 33/0 —
  - (D1) clean-flow regression: empty-remote initial push (listing bare gets `main` with exactly `README.md` + `plans.md`) → populated-remote re-run skip → clean-vault `--vault` run (commit = exactly `.gitmodules` + `autonomous_task_overview`, vault branch pushed to its local origin) → already-added re-run skip; all exit 0.
  - (D2) `--dry-run --vault <clean vault>`: exit 0, prints the planned wiring line, listing remote ref byte-identical before/after (no pushes), vault untouched (no `.gitmodules`, status/log unchanged). `--dry-run --vault <dirty-.gitmodules vault>`: exit 0, prints the new `[dry-run] would REFUSE …` line (no writes).
  - (a) vault = 1 commit + 1 dirty UNRELATED tracked file (`notes/keep.md`) + listing remote populated with the staged content (produced by D1's initial push) → run PROCEEDS, exit 0; new vault commit verified via `git show --name-only` = exactly `.gitmodules` + `autonomous_task_overview`; commit message = `OC: Add autonomous_task_overview submodule (listing for roadmap-dev)`; dirty file's edit still in worktree and still in `git status` (unmodified, uncommitted); vault branch pushed (local HEAD == origin HEAD); listing remote ref unchanged.
  - (b) vault with a committed-then-dirtied `.gitmodules` → REFUSES, exit 1, with the new message; `git log` HEAD unchanged (nothing committed); no `autonomous_task_overview` path created.
  - (c) vault where `autonomous_task_overview/` pre-exists as an untracked dir containing `scratch.md` → REFUSES, exit 1 (guard fires before `submodule add` — no `.gitmodules` created, no commits); pre-existing dir + file untouched.
- Sample of the new refusal (verbatim, fixture (b)-style run):
  `[FAIL] refusing the vault step: <vault> has uncommitted changes ON .gitmodules or INSIDE autonomous_task_overview — these are the only paths the submodule commit stages, so in-progress work there would be swept into it (commit or stash it first):` + listed ` M .gitmodules`.

## Acceptance Verification

| # | Criterion (verbatim) | Result | Notes |
|---|---|---|---|
| 1. | `bash -n scripts/bootstrap_task_overview.sh` clean. | PASS | Exit 0, no output. |
| 2. | Hermetic fixture matrix (scratch `git init` vaults + a local bare listing remote, git identity set in-test; mirror the fixture style of the Task 5 report): (a) vault with 1 commit + one dirty UNRELATED tracked file + listing remote populated with the staged content → `--vault <vault>` runs to completion: the vault's NEW commit contains exactly `.gitmodules` + `autonomous_task_overview` (verify via `git show --name-only`), the dirty file is unmodified and uncommitted, vault branch pushed; (b) vault with a dirty `.gitmodules` → REFUSES with the new message, exit 1, nothing committed; (c) vault where `autonomous_task_overview/` pre-exists as an untracked dir containing a file → REFUSES (guard fires before `submodule add`), exit 1. | PASS | All three variants green in the 33-check hermetic matrix (details in Build/Tests). (a) `git show --name-only` on the new commit = exactly the two paths; dirty file's appended edit still present in the worktree and still listed by `git status --porcelain`; vault `main` == its origin `main`. (b) new message text matched, `git log` HEAD unchanged. (c) refusal with `?? autonomous_task_overview/` listed; no `.gitmodules` created (guard precedes `submodule add`). |
| 3. | Regression: the clean-vault flow from the Task 5 report still works end-to-end (initial push → populated-skip → clean-vault submodule commit with exactly two paths → already-added skip), and `--dry-run` still exits 0 with no pushes/vault writes. | PASS | D1 sequence reproduced all four stages (initial push → `[OK] remote already populated — skipping initial push` → clean-vault submodule commit with exactly two paths + push → `[OK] vault submodule already present … — skipping`), all exit 0. `--dry-run` exit 0; listing remote ref unchanged before/after; vault free of `.gitmodules`/commits/status changes. |
| 4. | `grep -n "unrelated\|outside" scripts/bootstrap_task_overview.sh` shows no leftover old-guard wording (comments/messages updated). | PASS | Zero matches (grep exit 1). Header, usage, helper comment, dry-run and refusal messages all carry the new "only the staged paths" wording. |

## Blockers

None.

Notes for the record (no action needed):

1. **Untracked in-progress work from the parallel Task 4 agent** (`src/agentic_scripts/agent.py`,
   `src/agentic_scripts/workflows/roadmap_dev.py`, `tests/test_roadmap_dev_scan.py` modified)
   was present in the working tree throughout; it was never staged — this commit stages only
   `scripts/bootstrap_task_overview.sh` by explicit path. No index.lock contention occurred
   on this attempt.
2. **Operational consequence (expected, per B2):** the live vault run
   `bash scripts/bootstrap_task_overview.sh --vault /workspace/Obsidian/ARP_roadmap` is now
   UNBLOCKED — the vault's dirty slides work no longer trips the guard, and the vault commit
   will contain exactly `.gitmodules` + `autonomous_task_overview`. It will only be refused
   if in-progress work exists ON those two paths in the live vault (none observed).

## Next Steps

- **Orchestrator:** push this branch's commits between waves (this task's commit left
  unpushed per dispatch; reference by message — `OC: roadmap-dev T5b — invert vault-submodule
  guard: refuse only on uncommitted changes ON .gitmodules / INSIDE autonomous_task_overview
  (the only paths the submodule commit stages), per ratified decision B2`).
- **Orchestrator operational step (user pre-approved):** the bootstrap run against the real
  empty `y2d2/autonomous_task_overview` + `--vault /workspace/Obsidian/ARP_roadmap` can now
  proceed in one shot (initial push + submodule-only vault commit + vault push on the
  vault's current branch) — no longer requires committing/stashing the slides work first.
