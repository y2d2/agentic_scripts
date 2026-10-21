#!/usr/bin/env bash
# setup.sh — idempotent turnkey setup for agentic_scripts.
#
# Syncs the uv environment (runtime + dev extras), checks GITHUB_PAT, verifies the
# admin repo and the agents of every registered enabled workflow, creates the runtime
# dirs, and installs the 30-minute timer via systemd (real hosts) or cron (this
# container). Every step prints [OK]/[WARN]/[FAIL]; exit 0 iff no [FAIL].
#
# Re-run after a container restart: the cron daemon does not survive it (no init
# system here), and re-running setup is the documented recovery.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

ok()   { echo "[OK] $*"; }
warn() { echo "[WARN] $*"; }
fail() { echo "[FAIL] $*"; FAILURES=$((FAILURES + 1)); }
FAILURES=0

# --- 1. uv -------------------------------------------------------------------
if command -v uv >/dev/null 2>&1; then
    ok "uv found ($(command -v uv))"
else
    fail "uv not found (install: https://docs.astral.sh/uv/)"
fi

# --- 2. Venv sync -------------------------------------------------------------
# Dev tools (pytest, ruff) live in the `[project.optional-dependencies] dev` group
# (pyproject.toml), so sync that extra too; a plain `uv sync` would skip it.
if (cd "$ROOT" && uv sync --extra dev); then
    ok "venv synced (uv sync --extra dev)"
else
    fail "uv sync failed"
fi

# --- 3. Env vars ---------------------------------------------------------------
# GITHUB_PAT is required only by workflows that open PRs; base-only state does not need it.
if [ -f "$ROOT/.env" ]; then
    chmod 600 "$ROOT/.env"   # idempotent
else
    cp "$ROOT/.env.example" "$ROOT/.env"
    chmod 600 "$ROOT/.env"
    echo "note: created $ROOT/.env from .env.example (chmod 600)"
fi
if [ -n "${GITHUB_PAT:-}" ] || grep -qE '^GITHUB_PAT=.' "$ROOT/.env"; then
    ok "GITHUB_PAT present"
else
    warn "GITHUB_PAT missing (required by workflows that open PRs; base-only state does not need it)"
fi

# --- 4. Admin repo -------------------------------------------------------------
ADMIN_REPO="$(uv run --project "$ROOT" python -c \
    'import yaml,sys; print(yaml.safe_load(open(sys.argv[1])).get("admin_repo") or "")' \
    "$ROOT/config/workflows.yaml")"
if [ -n "$ADMIN_REPO" ]; then
    if git -C "$ADMIN_REPO" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        ok "admin_repo is a git repo: $ADMIN_REPO"
    else
        warn "admin_repo not a git repo or missing: $ADMIN_REPO (needed by the mail-keeper workflow)"
    fi
else
    warn "admin_repo not set in config/workflows.yaml (needed by the mail-keeper workflow)"
fi

# --- 5. Registered-workflow agents ----------------------------------------------
# Data-driven over *enabled* workflows with a non-null agent; base-only state (noop,
# agent: null) prints no lines and passes trivially.
AGENT_LINES="$(uv run --project "$ROOT" python -c '
import sys, yaml
cfg = yaml.safe_load(open(sys.argv[1]))
for name, wf in cfg.get("workflows", {}).items():
    if wf.get("enabled") and wf.get("agent"):
        print(name, wf["agent"])
' "$ROOT/config/workflows.yaml")"
if [ -z "$AGENT_LINES" ]; then
    ok "no agent-backed workflows registered"
else
    while read -r wf_name agent_name; do
        if [ -f "$HOME/.config/opencode/agents/$agent_name.md" ]; then
            ok "agent for workflow '$wf_name': $agent_name"
        else
            fail "agent $agent_name not found (expected at $HOME/.config/opencode/agents/$agent_name.md; agents live in the oc_config repo)"
        fi
    done <<< "$AGENT_LINES"
fi

# --- 6. Runtime dirs -------------------------------------------------------------
mkdir -p "$ROOT/state" "$ROOT/logs" "$ROOT/sandbox"
ok "runtime dirs present (state, logs, sandbox)"

# --- 7. Timer: systemd → cron detection ------------------------------------------
if systemctl is-system running >/dev/null 2>&1; then
    # Real systemd host: render the shipped units (__ROOT__ placeholder) and enable.
    sed "s|__ROOT__|$ROOT|g" "$ROOT/systemd/agentic-scripts.service" > /etc/systemd/system/agentic-scripts.service
    sed "s|__ROOT__|$ROOT|g" "$ROOT/systemd/agentic-scripts.timer"   > /etc/systemd/system/agentic-scripts.timer
    systemctl daemon-reload
    systemctl enable --now agentic-scripts.timer
    ok "systemd timer enabled (agentic-scripts.timer)"
else
    # No systemd (this container): cron path.
    if ! command -v crontab >/dev/null 2>&1 && ! command -v cron >/dev/null 2>&1; then
        if apt-get update -qq && apt-get install -y -qq cron; then
            ok "cron installed"
        else
            fail "apt-get install cron failed (no network?)"
        fi
    fi
    service cron start >/dev/null 2>&1 || /etc/init.d/cron start >/dev/null 2>&1 || true
    if pgrep -x cron >/dev/null 2>&1; then
        ok "cron daemon running"
    else
        fail "cron daemon not running"
    fi

    CRON_ENTRY="*/30 * * * * cd $ROOT && uv run agentic-scripts run >> $ROOT/logs/cron.log 2>&1"
    if crontab -l 2>/dev/null | grep -qF '# agentic-scripts'; then
        ok "cron entry already present"
    else
        { crontab -l 2>/dev/null | sed '/# agentic-scripts/d'; echo "# agentic-scripts"; echo "$CRON_ENTRY"; } | crontab - || fail "failed to install cron entry"
        if crontab -l 2>/dev/null | grep -qF '# agentic-scripts'; then
            ok "cron entry installed (*/30, log: $ROOT/logs/cron.log)"
        fi
    fi
    echo "note: container has no init system — after a container restart, re-run \`bash scripts/setup.sh\` to re-register the cron daemon."
fi

# --- 8. Summary -------------------------------------------------------------------
echo ""
if [ "$FAILURES" -eq 0 ]; then
    ok "setup complete (no failures)"
else
    fail "setup finished with $FAILURES failure(s)"
    exit 1
fi
