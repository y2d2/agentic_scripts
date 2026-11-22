#!/usr/bin/env bash
# bootstrap_task_overview.sh — one-shot bootstrap for the roadmap-dev listing repo.
#
# Pure git over SSH: NO GitHub REST, NO PAT, NO curl. Pushes the staged initial
# content (this repo's autonomous_task_overview/README.md + plans.md) to the
# listing repo (default y2d2/autonomous_task_overview — must exist and be empty),
# and — with --vault <path> — wires the listing into the vault as the
# `autonomous_task_overview/` submodule: committing ONLY .gitmodules + the
# submodule path, and REFUSING (exit 1) if the vault has any uncommitted change
# outside those two paths (never sweeps the vault's other work into the commit).
#
# Idempotent: a populated remote skips the initial push; an already-added
# submodule skips the vault step. --dry-run prints the planned actions and
# performs no pushes, no vault writes, no temp-dir creation (the git ls-remote
# probe is the only network call — read-only).
#
# Usage:
#   bash scripts/bootstrap_task_overview.sh [--dry-run] [--repo owner/name] [--vault <path>]
#
# Exit: 0 iff no step failed; 1 on refusal/failure; 2 on usage error.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
STAGING="$ROOT/autonomous_task_overview"

DRY_RUN=0
LISTING_REPO="y2d2/autonomous_task_overview"
VAULT=""
TMP_DIR=""
REMOTE_KIND=""
FAILURES=0

ok() { echo "[OK] $*"; }
warn() { echo "[WARN] $*"; }
fail() { echo "[FAIL] $*"; FAILURES=$((FAILURES + 1)); }

usage() {
    cat <<'EOF'
Usage: bootstrap_task_overview.sh [--dry-run] [--repo owner/name] [--vault <path>]

One-shot bootstrap for the roadmap-dev listing repo (pure git over SSH — no
GitHub REST, no PAT, no curl):

  --dry-run        print the planned actions; no pushes, no vault writes
  --repo R         listing repo to bootstrap (default: y2d2/autonomous_task_overview)
  --vault PATH     also add the listing as the `autonomous_task_overview/` submodule
                   of the git repo at PATH (commits only .gitmodules + the submodule
                   path; refuses on any other uncommitted vault change)
  -h, --help       this help
EOF
}

# --- args -----------------------------------------------------------------------
while [ $# -gt 0 ]; do
    case "$1" in
        --dry-run) DRY_RUN=1 ;;
        --repo)
            [ $# -ge 2 ] || { echo "error: --repo needs a value (owner/name)" >&2; exit 2; }
            LISTING_REPO="$2"
            shift
            ;;
        --vault)
            [ $# -ge 2 ] || { echo "error: --vault needs a path" >&2; exit 2; }
            VAULT="$2"
            shift
            ;;
        -h|--help) usage; exit 0 ;;
        *) echo "error: unknown argument: $1" >&2; usage >&2; exit 2 ;;
    esac
    shift
done

if ! [[ "$LISTING_REPO" =~ ^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$ ]]; then
    echo "error: --repo must be in owner/name form (got: $LISTING_REPO)" >&2
    exit 2
fi
LISTING_URL="git@github.com:${LISTING_REPO}.git"

cleanup() {
    if [ -n "$TMP_DIR" ]; then
        rm -rf "$TMP_DIR"
    fi
}
trap cleanup EXIT

# --- 1. preflight ----------------------------------------------------------------
preflight() {
    # Staged initial content must be present in this repo.
    if [ ! -f "$STAGING/README.md" ] || [ ! -f "$STAGING/plans.md" ]; then
        fail "staged initial content missing — expected $STAGING/README.md and $STAGING/plans.md"
        exit 1
    fi
    ok "staged initial content present (autonomous_task_overview/README.md + plans.md)"

    # The listing repo must be reachable over SSH; classify empty vs populated.
    local refs
    if ! refs="$(timeout 15 git ls-remote "$LISTING_URL" 2>/dev/null)"; then
        fail "listing repo not reachable over SSH — check SSH key ($LISTING_URL)"
        exit 1
    fi
    if [ -n "$refs" ]; then
        REMOTE_KIND="populated"
        ok "listing repo reachable and populated ($LISTING_REPO)"
    else
        REMOTE_KIND="empty"
        ok "listing repo reachable and empty ($LISTING_REPO)"
    fi
}

# --- 2. initial push (empty remote only — never force-pushed) ---------------------
push_initial() {
    if [ "$REMOTE_KIND" = "populated" ]; then
        ok "remote already populated — skipping initial push"
        return 0
    fi
    if [ "$DRY_RUN" -eq 1 ]; then
        echo "[dry-run] would push initial content (README.md + plans.md) to $LISTING_URL (branch main)"
        return 0
    fi

    TMP_DIR="$(mktemp -d)"
    git -C "$TMP_DIR" init -q
    # Reuse the configured git identity when present; fall back to the bot identity.
    if ! git -C "$TMP_DIR" config user.name >/dev/null 2>&1; then
        git -C "$TMP_DIR" config user.name "agentic-scripts"
    fi
    if ! git -C "$TMP_DIR" config user.email >/dev/null 2>&1; then
        git -C "$TMP_DIR" config user.email "bot@localhost"
    fi
    cp "$STAGING/README.md" "$STAGING/plans.md" "$TMP_DIR/"
    git -C "$TMP_DIR" add -A
    git -C "$TMP_DIR" commit -q -m "OC: Initial task-overview content (plans listing + authoring guide)"
    git -C "$TMP_DIR" branch -M main
    git -C "$TMP_DIR" remote add origin "$LISTING_URL"

    local out
    if ! out="$(git -C "$TMP_DIR" push -u origin main 2>&1)"; then
        fail "initial push to $LISTING_URL failed (never force-pushed):"
        printf '%s\n' "$out" | tail -n 5 | sed 's/^/    /'
        exit 1
    fi
    ok "initial content pushed to $LISTING_URL (branch main)"
}

# --- 3. vault submodule (optional) -------------------------------------------------
# Echo one porcelain status line per uncommitted vault change OUTSIDE the two paths
# the submodule step is allowed to commit (.gitmodules, autonomous_task_overview).
vault_unrelated_change() {
    local line path
    while IFS= read -r line; do
        [ -n "$line" ] || continue
        path="${line:3}"
        path="${path%/}"
        case "$path" in
            .gitmodules | autonomous_task_overview | autonomous_task_overview/*) continue ;;
        esac
        printf '%s\n' "$line"
    done < <(git -C "$1" status --porcelain)
}

add_submodule() {
    if [ -z "$VAULT" ]; then
        echo "note: no --vault given — skipping the vault submodule step (the workflow reconciles its own sandbox clone of the listing; the submodule exists for Obsidian visibility). Re-run with --vault <path> to wire it."
        return 0
    fi

    local vault
    if ! vault="$(cd "$VAULT" 2>/dev/null && pwd)"; then
        fail "vault path not found: $VAULT"
        exit 1
    fi
    if ! git -C "$vault" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        fail "not a git repo: $vault"
        exit 1
    fi

    # Idempotent: already wired as a submodule?
    if [ -f "$vault/.gitmodules" ] \
        && git -C "$vault" config -f .gitmodules --get submodule.autonomous_task_overview.url >/dev/null 2>&1; then
        ok "vault submodule already present ($vault/autonomous_task_overview) — skipping"
        return 0
    fi

    local dirty
    dirty="$(vault_unrelated_change "$vault")"

    if [ "$DRY_RUN" -eq 1 ]; then
        if [ -n "$dirty" ]; then
            echo "[dry-run] would REFUSE the vault step — uncommitted changes outside .gitmodules/autonomous_task_overview:"
            printf '%s\n' "$dirty" | sed 's/^/    /'
        else
            echo "[dry-run] would wire the vault submodule: git -C $vault submodule add $LISTING_URL autonomous_task_overview → commit (OC:) → git -C $vault push"
        fi
        return 0
    fi

    if [ -n "$dirty" ]; then
        fail "refusing the vault step: $vault has uncommitted changes outside .gitmodules/autonomous_task_overview — your work must never be swept into the submodule commit:"
        printf '%s\n' "$dirty" | sed 's/^/    /'
        exit 1
    fi

    local out
    if ! out="$(git -C "$vault" submodule add "$LISTING_URL" autonomous_task_overview 2>&1)"; then
        fail "git submodule add failed in $vault:"
        printf '%s\n' "$out" | tail -n 5 | sed 's/^/    /'
        exit 1
    fi
    # Commit ONLY .gitmodules + the submodule path (the dirty check above guarantees
    # no other vault work is staged).
    git -C "$vault" add .gitmodules autonomous_task_overview
    if ! out="$(git -C "$vault" commit -m "OC: Add autonomous_task_overview submodule (listing for roadmap-dev)" 2>&1)"; then
        fail "vault submodule commit failed in $vault:"
        printf '%s\n' "$out" | tail -n 5 | sed 's/^/    /'
        exit 1
    fi
    if ! out="$(git -C "$vault" push 2>&1)"; then
        fail "vault push failed in $vault:"
        printf '%s\n' "$out" | tail -n 5 | sed 's/^/    /'
        exit 1
    fi
    ok "vault submodule wired and pushed ($vault/autonomous_task_overview @ $(git -C "$vault" branch --show-current))"
}

# --- main -------------------------------------------------------------------------
echo "bootstrap_task_overview: $LISTING_REPO (url: $LISTING_URL, dry-run: $DRY_RUN)"
preflight
push_initial
add_submodule

echo ""
if [ "$FAILURES" -eq 0 ]; then
    ok "bootstrap complete (no failures)"
else
    fail "bootstrap finished with $FAILURES failure(s)"
    exit 1
fi
