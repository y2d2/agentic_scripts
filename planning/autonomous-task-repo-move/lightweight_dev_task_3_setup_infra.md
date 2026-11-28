# lightweight-dev Output — Task: setup-infra

**Task:** #3    **Session:** ses_df61d5843ffeOhcdjRu5EtO3Vs    **Date:** 2026-11-23

## Summary

Gave the overview clone `/workspace/Python/autonomous_task_overview` (branch
`feature/engine-move`) its own turnkey setup infrastructure, all three sub-tasks
landed in one commit and pushed:

- **Sub-task 1 (`scripts/setup.sh`, 191 lines, mode 100755)** — modeled on the
  live `/workspace/Python/agentic_scripts/scripts/setup.sh` (identical
  `[OK]/[WARN]/[FAIL]` reporting, `set -euo pipefail`, `ROOT` resolution,
  step-numbered sections, uv-run-python config reads): uv check → `uv sync
  --extra dev` → `.env` from `.env.example` (idempotent, `chmod 600`) +
  `GITHUB_PAT` advisory → **agent check** for `planner-enhanced` +
  `lightweight-dev` (FAIL on missing, per plan — an engine without its
  orchestrator cannot drain) → **roadmap preflight** (data-driven read of
  `roadmap_prompts`; `repo_urls`/`listing_repo_url` overrides honored; `""` →
  derived `git@github.com:<repo>.git`; `timeout 15 git ls-remote --exit-code
  <url> HEAD` per repo; WARN-never-FAIL; empty allowlist → "allowlist empty —
  engine is inert") → runtime dirs → **timer** only when `--skip-timer` is NOT
  passed (systemd branch renders the shipped `__ROOT__` units into
  `/etc/systemd/system/autonomous-task.{service,timer}`; cron branch installs
  under its OWN marker `# autonomous-task` with the plan-verbatim entry
  carrying the live old entry's `PATH=` + absolute-`uv` hardening). `--skip-timer`
  valve leaves crontab and `/etc/systemd` completely untouched (step 7 is
  skipped entirely — no crontab read or write at all).
- **Sub-task 2 (`systemd/` units + `.env.example` + `.python-version`)** —
  service/timer units mirror the source units with `autonomous-task` naming and
  `python -m autonomous_task run`; `.env.example` is the plan-verbatim 4-line
  file (PAT only, no MAIL_*); **`.python-version` pins `3.12`** per the
  orchestrator refinement. `uv sync --extra dev` then REBUILT the venv from
  CPython 3.14.7 → **CPython 3.12.3** (`/usr/bin/python3.12` — the exact
  interpreter the live old engine runs, so parity is exact, not just
  `>=3.12`).
- **Sub-task 3 (re-verify + commit)** — full suite **81/81 green under 3.12.3**
  (verified twice: once right after the pin rebuild, once in final state before
  committing), committed `OC: Add setup.sh (--skip-timer), systemd units,
  .env.example` (5 files, 220 insertions, all `create mode`), pushed to
  `origin/feature/engine-move`. `plans.md` absent from the diff.

**Guard details honored:** `crontab -l` is BYTE-IDENTICAL before/after the
`--skip-timer` run (md5 `cfb0988abb2ccee6dc0a3a628e485caf` both times; `cmp`
exit 0; both outputs recorded verbatim below). Preflight produced **10 `[OK]`
lines** (9 allowlisted repos + listing repo) and zero `[WARN]`s — every repo
reachable over SSH.

## Files

| File | Action | Why |
|---|---|---|
| `/workspace/Python/autonomous_task_overview/scripts/setup.sh` | create (mode 100755) | Turnkey setup with the `--skip-timer` valve, own `# autonomous-task` cron marker, `PATH=` + absolute-uv cron line (plan-verbatim) |
| `/workspace/Python/autonomous_task_overview/systemd/autonomous-task.service` | create | Oneshot unit for real systemd hosts (`__ROOT__` placeholder, rendered by setup.sh) |
| `/workspace/Python/autonomous_task_overview/systemd/autonomous-task.timer` | create | `OnCalendar=*:0/30`, `Persistent=true`, `WantedBy=timers.target` |
| `/workspace/Python/autonomous_task_overview/.env.example` | create | Plan-verbatim: comments + empty `GITHUB_PAT=` only (no MAIL_* — this engine has no mail-keeper) |
| `/workspace/Python/autonomous_task_overview/.python-version` | create | Orchestrator refinement: pin `3.12` (parity with the live engine's interpreter) |
| `/workspace/Python/autonomous_task_overview/.env` | create (runtime; gitignored) | Byproduct of the `--skip-timer` run: copied from `.env.example`, `chmod 600` |
| `/workspace/Python/autonomous_task_overview/state/`, `logs/`, `sandbox/` | create (runtime; gitignored) | Runtime dirs from setup.sh step 6 |

No files in `/workspace/Python/agentic_scripts` were created, modified, or
staged (read-only pattern source; verified — its `git status` shows only the
orchestrator's pre-existing planning files, zero other changes).

## Build / Tests

- `bash -n scripts/setup.sh`: PASS (syntax check, exit 0)
- `bash scripts/setup.sh --help`: PASS — prints usage, exit 0
- `bash scripts/setup.sh --bogus-flag`: PASS — prints usage, exit 2
- **`bash scripts/setup.sh --skip-timer` (valve CLOSED): PASS — exit 0.** Full output:
  ```
  [OK] uv found (/root/.local/bin/uv)
  Resolved 10 packages in 2ms
  Checked 9 packages in 0.47ms
  [OK] venv synced (uv sync --extra dev)
  note: created /workspace/Python/autonomous_task_overview/.env from .env.example (chmod 600)
  [WARN] GITHUB_PAT missing (only needed for HTTPS-mirror clones via roadmap_prompts.repo_urls; the engine's default clone path is git over SSH)
  [OK] agent present: planner-enhanced (/root/.config/opencode/agents/planner-enhanced.md)
  [OK] agent present: lightweight-dev (/root/.config/opencode/agents/lightweight-dev.md)
  [OK] roadmap preflight: y2d2/ARP_MPE reachable over SSH (git@github.com:y2d2/ARP_MPE.git)
  [OK] roadmap preflight: y2d2/ARP_implementations reachable over SSH (git@github.com:y2d2/ARP_implementations.git)
  [OK] roadmap preflight: y2d2/ARP_1A_anchored_implementations reachable over SSH (git@github.com:y2d2/ARP_1A_anchored_implementations.git)
  [OK] roadmap preflight: y2d2/ARP_utility_code reachable over SSH (git@github.com:y2d2/ARP_utility_code.git)
  [OK] roadmap preflight: y2d2/PRP_ARP_M reachable over SSH (git@github.com:y2d2/PRP_ARP_M.git)
  [OK] roadmap preflight: y2d2/ARP_IMU reachable over SSH (git@github.com:y2d2/ARP_IMU.git)
  [OK] roadmap preflight: y2d2/agentic_scripts reachable over SSH (git@github.com:y2d2/agentic_scripts.git)
  [OK] roadmap preflight: y2d2/ARP_roadmap reachable over SSH (git@github.com:y2d2/ARP_roadmap.git)
  [OK] roadmap preflight: y2d2/ARP_engine reachable over SSH (git@github.com:y2d2/ARP_engine.git)
  [OK] roadmap preflight: y2d2/autonomous_task_overview reachable over SSH (git@github.com:y2d2/autonomous_task_overview.git)
  [OK] runtime dirs present (state, logs, sandbox)
  [OK] timer install skipped (--skip-timer: crontab and /etc/systemd untouched)

  [OK] setup complete (no failures)
  ```
  Preflight: **10/10 `[OK]`**, zero `[WARN]`s (all 9 allowlisted repos + the listing repo reachable over SSH). The lone `[WARN]` (GITHUB_PAT) is the plan-specified advisory and does not affect exit status.
- **Crontab guard (valve CLOSED):** `crontab -l` captured before and after; **byte-identical** (`cmp` exit 0, `diff` empty, md5 `cfb0988abb2ccee6dc0a3a628e485caf` both). Both outputs verbatim (identical, so shown once):
  ```
  # agentic-scripts (fixed 2026-10-23: absolute uv path + PATH incl. opencode; previous line failed 78x with 'uv: not found')
  */30 * * * * cd /workspace/Python/agentic_scripts && PATH=/root/.opencode/bin:/root/.local/bin:/usr/local/bin:/usr/bin:/bin /root/.local/bin/uv run agentic-scripts run >> /workspace/Python/agentic_scripts/logs/cron.log 2>&1
  ```
  Still byte-identical after the subsequent commit work (re-verified at report time).
- Runtime dirs: PASS — `state/`, `logs/`, `sandbox/` exist (plus `.env`, mode 600)
- `uv sync --extra dev` after the `.python-version` pin: PASS — `Using CPython 3.12.3 interpreter at: /usr/bin/python3.12`, `Removed virtual environment at: .venv` → `Creating virtual environment at: .venv`, 9 packages installed; `.venv/bin/python --version` → `Python 3.12.3`; **`uv.lock` unchanged** (no restage needed)
- `uv run pytest -q` (right after the 3.12.3 rebuild): PASS — **81 passed in 33.69s**
- `uv run pytest -q` (final state, all new files in place, before commit): PASS — **81 passed in 33.48s**
- `uv run ruff check scripts/ 2>/dev/null || true` (plan-verbatim): PASS — printed "All checks passed!" (no Python files in `scripts/`; harmless)
- `sed "s|__ROOT__|/workspace/Python/autonomous_task_overview|g" systemd/autonomous-task.service` (dry-render): PASS — `ExecStart=/workspace/Python/autonomous_task_overview/.venv/bin/python -m autonomous_task run`; zero `__ROOT__` residual after substitution; `/etc/systemd/system/` contains no `autonomous-task` units (nothing installed on this host)
- `.env.example` checks: PASS — `grep -c MAIL_` = 0; only non-comment line is `GITHUB_PAT=` (empty) — no secrets
- Commit + push: PASS — `OC: Add setup.sh (--skip-timer), systemd units, .env.example` on `feature/engine-move`; 5 files, 220 insertions(+), 0 deletions (all `create mode`); pushed (`15d49f6..8aaa905`), remote `feature/engine-move` matches local HEAD; tree clean after push; `plans.md` absent from the commit

## Acceptance Verification

| # | Criterion (verbatim) | Result | Notes |
|---|---|---|---|
| T1.1 | `bash scripts/setup.sh --skip-timer` in the clone exits 0; `crontab -l` is BYTE-IDENTICAL before and after the run (record both outputs in the result report); `state/ logs/ sandbox/` exist. | PASS | Exit 0; before/after crontab md5 `cfb0988abb2ccee6dc0a3a628e485caf` both, `cmp` exit 0, `diff` empty — both outputs recorded verbatim in Build/Tests (identical, shown once); `state/ logs/ sandbox/` all exist. This guard FAILed nothing — the valve is closed: step 7 is skipped entirely, so the script never reads or writes the crontab under `--skip-timer` |
| T1.2 | `bash scripts/setup.sh --help` prints usage and exits 0; an unknown flag exits 2. | PASS | `--help` printed the usage block, exit 0; `--bogus-flag` printed the usage block, exit 2 |
| T1.3 | `bash -n scripts/setup.sh` (syntax check) passes. | PASS | Exit 0 |
| T1.4 | The agent-check and preflight sections reference `planner-enhanced`/`lightweight-dev` and the 9 allowlisted repos + the listing repo (grep the script). | PASS | Functional agent loop `for agent in planner-enhanced lightweight-dev` (step 4) greps both names; step 5's section carries an operator comment listing all 9 allowlisted repos + the listing repo (lines 98–103). The preflight itself reads `config/workflows.yaml` data-driven per the plan's step spec — the comment records the shipped allowlist for grep-ability and operator context (see Notes 5) |
| T2.1 | `sed "s|__ROOT__|/workspace/Python/autonomous_task_overview|g" systemd/autonomous-task.service` renders a unit whose `ExecStart` names `python -m autonomous_task run` (dry-render check only — do NOT install anything in `/etc/systemd` on this host). | PASS | Rendered `ExecStart=/workspace/Python/autonomous_task_overview/.venv/bin/python -m autonomous_task run`; 0 residual `__ROOT__` across both rendered units; nothing written to `/etc/systemd` (verified absent) |
| T2.2 | `.env.example` contains no MAIL_* variables and no secrets. | PASS | `grep -c "MAIL_"` = 0; only variable is `GITHUB_PAT=` (empty value); content is plan-verbatim |
| T2.R (orchestrator refinement) | create `.python-version` pinning `3.12` (parity with the live engine's interpreter), then re-run `uv sync --extra dev` so the venv is rebuilt on 3.12, and re-verify the full suite 81/81 green under the new interpreter before committing. | PASS | `.python-version` = `3.12`; re-sync rebuilt the venv on **CPython 3.12.3** (`/usr/bin/python3.12` — the live engine's exact interpreter, so parity is exact); suite re-verified **81/81 green under 3.12.3** before committing. CPython 3.12 was available, so the Blocker path (keep pin + `uv python list`) was not needed |
| T3.1 | Suite still 100% green; commit + push landed on `feature/engine-move`; `plans.md` untouched. | PASS | `uv run pytest -q` in final state: 81 passed, 0 failed (CPython 3.12.3); commit `OC: Add setup.sh (--skip-timer), systemd units, .env.example` on `feature/engine-move`, pushed (remote ref verified to match local HEAD); `git show --name-only` for the commit lists only the 5 new files — `plans.md` untouched; tree clean after push |

## Blockers

None — no criterion failed, CPython 3.12 was available to uv (3.12.3 at
`/usr/bin/python3.12`), and the crontab guard held byte-for-byte.

Notes for the orchestrator (no action required; none weaken a criterion):

1. **Ordering adaptation (no scope change):** the sub-task 1 acceptance run
   (`setup.sh --skip-timer` must exit 0) requires `.env.example` to already
   exist — setup.sh's env step copies it to `.env` when `.env` is missing, and
   the clone had no `.env` yet. `.env.example` (a sub-task 2 file) was therefore
   created first; its own acceptance (T2.2) was verified in sub-task 2 as
   spec'd. All files still landed in the single sub-task 3 commit.
2. **`.python-version` is in the commit** — the sub-task 3 stage list names 4
   files, but it predates your refinement adding `.python-version` to
   sub-task 2's file list. The pin only achieves its purpose (a fresh clone →
   3.12, turnkey parity) if it is tracked, and your refinement says to keep it
   even on the 3.12-unavailable path, so I staged it explicitly alongside the
   4 listed files. If you intended it untracked, say so and I'll follow up with
   a removing commit (inverse-commit per the git workflow, not a reset).
3. **`uv.lock` is unchanged** by the 3.14.7 → 3.12.3 rebuild (no locked version
   requires a 3.14-specific resolution), so no lock restage was needed.
4. **Future cron line (for work-plan Task 7 reference)** — what setup.sh
   installs WITHOUT `--skip-timer` on this host (marker `# autonomous-task`,
   same hardening as the live old entry):
   `*/30 * * * * cd /workspace/Python/autonomous_task_overview && PATH=/root/.opencode/bin:/root/.local/bin:/usr/local/bin:/usr/bin:/bin /root/.local/bin/uv run autonomous-task run >> /workspace/Python/autonomous_task_overview/logs/cron.log 2>&1`
   The installer is idempotent and marker-keyed, so Task 7's run will replace
   any stale `# autonomous-task` line without touching the old engine's
   `# agentic-scripts` entry (verified by construction; both markers are
   distinct strings).
5. **Preflight comment is documentation, not logic** — the 10 repo ids in
   setup.sh step 5 are a comment recording the shipped allowlist (the
   acceptance grep requires the section to reference them); the runtime check
   reads `config/workflows.yaml` and is authoritative. If the allowlist ever
   changes, the comment needs a refresh (one line, noted for Task 4's docs
   pass if convenient).
6. **`ruff check scripts/` printed "All checks passed!"** — ruff 0.17 exits 0
   with no Python files present, so the plan's `2>/dev/null || true` line was
   a no-op in practice.

## Next Steps

- Work-plan Task 4 (docs) can document `setup.sh` usage; the script's header
  docstring already carries the re-run-after-restart note and the
  `--skip-timer` semantics.
- Work-plan Task 7 (cron install, post-cutover-gate) can run `bash
  scripts/setup.sh` (valve OPEN) in the clone — the cron branch is
  structurally verified, the entry text is spec-locked (Note 4), and the
  installer is idempotent.
- A real-host systemd path (render + `daemon-reload` + `enable --now`) remains
  unexecuted by design (no systemd in this container); the units passed the
  dry-render check only.
