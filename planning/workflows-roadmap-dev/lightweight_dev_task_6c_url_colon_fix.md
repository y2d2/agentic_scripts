# lightweight-dev Output — Task: SSH URL colon fix (T6c)

**Task:** #6c    **Session:** ses_dfdb7c0ffffe7sMoIDTKhcOf2E    **Date:** 2026-11-22

## Summary
Fixed the root cause of the first live-run clone failures: `_repo_url` and `_prompts_repo_url` derived default SSH URLs with a slash after `github.com` (`git@github.com/<repo>.git`), which git classifies as a local path (stat → instant `does not exist`). Both f-strings now derive the colon form `git@github.com:<repo>.git`, and the `_repo_url` docstring Returns clause was updated to match. Added 2 byte-exact regression tests in `tests/test_roadmap_dev.py` (group E, alongside the existing workflow-shell tests) that construct the workflow via the existing `_roadmap_config` / `base_config` fixture pattern and assert the exact derived URL strings with `==`. Mutation-verified: flipping either f-string back to the slash form fails its regression test. Committed on `feature/roadmap-dev-workflow` (explicit paths only, message: `OC: roadmap-dev T6c — fix SSH URL derivation (colon, not slash) in _repo_url/_prompts_repo_url (+ regression tests)`); NOT pushed per dispatch (orchestrator pushes between waves).

## Files
| File | Action | Why |
|---|---|---|
| `src/agentic_scripts/workflows/roadmap_dev.py` | modify | Colon fix in `_repo_url` f-string (line 1429), `_prompts_repo_url` f-string (line 1438), and the `_repo_url` docstring Returns clause (line 1427). Nothing else touched — the `https://github.com/...` listing strings, `repo_from_url` parsing, and `scripts/setup.sh` were verified untouched. |
| `tests/test_roadmap_dev.py` | modify | 2 new byte-exact tests in group E (after `test_constructor_seams`): `test_repo_url_default_is_ssh_colon_form`, `test_prompts_repo_url_default_is_ssh_colon_form`. No new test module. |

## Build / Tests
- `uv run pytest` (full suite): PASS — 320 passed in 71.99s (baseline 318 + 2 new tests).
- `uv run ruff check src tests`: PASS — All checks passed. (One intermediate E501 on a test docstring found during verification; fixed, re-verified clean.)
- `uv run ruff format --check src tests`: PASS — 49 files already formatted.
- Mutation check (ad hoc, pre-commit): flipping each f-string back to the slash form failed its regression test (2 failed); restored — both pass.

## Acceptance Verification
| # | Criterion (verbatim) | Result | Notes |
|---|---|---|---|
| 1. | `uv run pytest -v` — full suite: current baseline is 318 passed; with your 2 new tests expect 320, all green. | PASS | `320 passed in 71.99s`; the 2 new tests selected and green via `-k "ssh_colon_form"`. |
| 2. | `uv run ruff check src tests` — clean. | PASS | `All checks passed!` |
| 3. | `uv run ruff format --check src tests` — clean. | PASS | `49 files already formatted` |
| 4. | `_repo_url("y2d2/ARP_MPE")` with `repo_urls == {}` must return exactly `git@github.com:y2d2/ARP_MPE.git` | PASS | Byte-exact `==` assertion in `test_repo_url_default_is_ssh_colon_form`; fails under slash mutation. |
| 5. | `_prompts_repo_url()` with `listing_repo_url == ""` and `listing_repo == "y2d2/autonomous_task_overview"` must return exactly `git@github.com:y2d2/autonomous_task_overview.git` | PASS | Byte-exact `==` assertion in `test_prompts_repo_url_default_is_ssh_colon_form`; fails under slash mutation. |
| 6. | Commit ONLY the two modified files with explicit paths, `OC:`-prefixed message; do NOT push; do NOT commit `planning/` or config files. | PASS | Commit `fbfe0af` on `feature/roadmap-dev-workflow`, 2 files (+20/−3); untracked `planning/mail-keeper-pruning/*` (other session) left untouched; no push performed. |

## Blockers
None.

## Next Steps
- Orchestrator: push `feature/roadmap-dev-workflow` (this task's commit is ready; T6c's commit is referenced by message — see `git log` for the SHA).
- Optional live re-run of the roadmap-dev workflow to confirm the 9 allowed-repo clones + listing-repo clone now succeed over SSH (the original failure mode).
