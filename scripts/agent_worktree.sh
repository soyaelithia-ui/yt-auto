#!/usr/bin/env bash
# ==============================================================================
# Agent Worktree Manager for Multi-Agent Concurrent Workflows
# Creates, force-removes, lists, and prunes isolated Git worktrees, then
# idempotently links shared .venv, .agents, and .env. Never mutates or deletes
# the primary repository checkout.
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SETUP_ENV="${SCRIPT_DIR}/setup_worktree_env.sh"

resolve_primary_root() {
    local start="${1:-$SCRIPT_DIR/..}"
    local common
    if common="$(git -C "$start" rev-parse --path-format=absolute --git-common-dir 2>/dev/null)"; then
        :
    elif common="$(git -C "$start" rev-parse --git-common-dir 2>/dev/null)"; then
        if [ "${common#/}" = "$common" ]; then
            common="$(cd "$start" && cd "$common" && pwd)"
        fi
    else
        echo "ERROR: not inside a git repository." >&2
        exit 1
    fi
    if [ "$(basename "$common")" = ".git" ]; then
        cd "$(dirname "$common")" && pwd -P
    else
        git -C "$start" worktree list --porcelain | awk '/^worktree / { print substr($0, 10); exit }'
    fi
}

PRIMARY_ROOT="$(resolve_primary_root "$SCRIPT_DIR/..")"
if [ -z "$PRIMARY_ROOT" ] || [ ! -d "$PRIMARY_ROOT" ]; then
    echo "ERROR: could not resolve primary repository root." >&2
    exit 1
fi
PRIMARY_REAL="$(cd "$PRIMARY_ROOT" && pwd -P)"

if [ -n "${YT_AUTO_WORKTREES_DIR:-}" ]; then
    WORKTREES_DIR="$YT_AUTO_WORKTREES_DIR"
else
    WORKTREES_DIR="$(dirname "$PRIMARY_ROOT")/yt-auto-worktrees/$(basename "$PRIMARY_ROOT")"
fi

usage() {
    echo "Usage: $0 {create <name> [branch]|remove <name>|list|prune|clean}"
    echo ""
    echo "Commands:"
    echo "  create <name> [branch]  Create an isolated worktree (default branch: agent/<name>)"
    echo "  remove <name>           Force-remove an agent worktree and prune metadata"
    echo "  list                    List all git worktrees"
    echo "  prune | clean           Prune stale worktree metadata only"
    echo ""
    echo "Safety: never deletes or modifies the primary checkout (${PRIMARY_REAL})."
    echo "Shared links: .venv, .agents, .env via setup_worktree_env.sh"
    echo "Override worktree parent with YT_AUTO_WORKTREES_DIR."
    exit 1
}

die() {
    echo "ERROR: $*" >&2
    exit 1
}

validate_name() {
    local name="${1:-}"
    if [ -z "$name" ]; then
        usage
    fi
    if [ "$name" = "." ] || [ "$name" = ".." ]; then
        die "invalid worktree name '${name}'"
    fi
    case "$name" in
        */*|*\\*|*".."*)
            die "invalid worktree name '${name}'"
            ;;
    esac
    if ! [[ "$name" =~ ^[A-Za-z0-9._-]+$ ]]; then
        die "invalid worktree name '${name}' (allowed: A-Za-z0-9._-)"
    fi
}

abspath_maybe_missing() {
    local p="$1"
    local dir base
    dir="$(dirname "$p")"
    base="$(basename "$p")"
    if [ -d "$dir" ]; then
        echo "$(cd "$dir" && pwd -P)/${base}"
    else
        echo "$p"
    fi
}

assert_not_primary() {
    local target="$1"
    local target_abs
    target_abs="$(abspath_maybe_missing "$target")"
    if [ "$target_abs" = "$PRIMARY_REAL" ] || [ "$target" = "$PRIMARY_ROOT" ] || [ "$target" = "$PRIMARY_REAL" ]; then
        die "refusing to operate on the primary repository (${PRIMARY_REAL})"
    fi
    if [ -e "$target" ]; then
        local target_real
        target_real="$(cd "$target" && pwd -P)"
        if [ "$target_real" = "$PRIMARY_REAL" ]; then
            die "refusing to operate on the primary repository (${PRIMARY_REAL})"
        fi
    fi
}

assert_under_worktrees_dir() {
    local target="$1"
    mkdir -p "$WORKTREES_DIR"
    local wt_real target_abs
    wt_real="$(cd "$WORKTREES_DIR" && pwd -P)"
    target_abs="$(abspath_maybe_missing "$target")"
    case "$target_abs" in
        "$wt_real"|"$wt_real"/*) ;;
        *)
            die "refusing path outside worktree root (${wt_real}): ${target}"
            ;;
    esac
    if [ "$target_abs" = "$wt_real" ]; then
        die "refusing to remove the worktrees root (${wt_real})"
    fi
}

git_common() {
    git -C "$PRIMARY_ROOT" "$@"
}

cmd_create() {
    local name="${1:-}"
    local branch="${2:-agent/${name}}"
    validate_name "$name"
    mkdir -p "$WORKTREES_DIR"
    local target_dir="$WORKTREES_DIR/$name"
    assert_not_primary "$target_dir"
    assert_under_worktrees_dir "$target_dir"

    if [ -e "$target_dir" ]; then
        die "worktree directory already exists: ${target_dir}"
    fi

    echo "Creating worktree at ${target_dir} on branch '${branch}'..."
    if git_common show-ref --verify --quiet "refs/heads/${branch}"; then
        git_common worktree add "$target_dir" "$branch"
    else
        local start="HEAD"
        if git_common show-ref --verify --quiet "refs/remotes/origin/main"; then
            start="origin/main"
        fi
        git_common worktree add -b "$branch" "$target_dir" "$start"
    fi

    if [ -x "$SETUP_ENV" ]; then
        "$SETUP_ENV" "$target_dir"
    else
        die "setup_worktree_env.sh is missing or not executable"
    fi

    echo "Worktree '${name}' ready at ${target_dir}"
}

cmd_remove() {
    local name="${1:-}"
    validate_name "$name"
    local target_dir="$WORKTREES_DIR/$name"
    assert_not_primary "$target_dir"
    assert_under_worktrees_dir "$target_dir"

    if [ -e "$target_dir" ]; then
        local cwd_real target_real
        cwd_real="$(pwd -P)"
        target_real="$(cd "$target_dir" && pwd -P)"
        if [ "$target_real" = "$cwd_real" ]; then
            die "refusing to remove the worktree of the current working directory"
        fi
        if [ "$target_real" = "$PRIMARY_REAL" ]; then
            die "refusing to operate on the primary repository (${PRIMARY_REAL})"
        fi
    fi

    echo "Force-removing worktree ${target_dir}..."
    if ! git_common worktree list --porcelain | awk '/^worktree / { print substr($0, 10) }' | grep -Fxq "$PRIMARY_REAL"; then
        die "primary worktree disappeared from git worktree list; aborting"
    fi

    if [ ! -e "$target_dir" ]; then
        git_common worktree prune
        die "worktree not found: ${target_dir}"
    fi

    git_common worktree remove --force "$target_dir" || true
    git_common worktree prune

    if [ -e "$target_dir" ]; then
        assert_not_primary "$target_dir"
        assert_under_worktrees_dir "$target_dir"
        rm -rf "$target_dir"
    fi

    if git_common worktree list --porcelain | awk '/^worktree / { print substr($0, 10) }' | grep -Fxq "$PRIMARY_REAL"; then
        :
    else
        die "primary worktree missing after remove; aborting"
    fi

    echo "Worktree '${name}' removed."
}

cmd_list() {
    git_common worktree list
}

cmd_prune() {
    echo "Pruning stale worktree metadata (primary checkout untouched)..."
    git_common worktree prune -v
    echo "Worktrees pruned."
}

case "${1:-}" in
    create)
        shift
        cmd_create "${1:-}" "${2:-}"
        ;;
    remove)
        shift
        cmd_remove "${1:-}"
        ;;
    list)
        cmd_list
        ;;
    prune|clean)
        cmd_prune
        ;;
    *)
        usage
        ;;
esac
