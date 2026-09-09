#!/usr/bin/env bash
# ==============================================================================
# Setup Worktree Environment
# Idempotently symlink shared .venv, .agents, and .env from the primary checkout
# into any derived worktree. Never prints secret file contents.
# ==============================================================================
set -euo pipefail

usage() {
    echo "Usage: $0 [target_dir]"
    echo "Idempotently link .venv, .agents, and .env from the primary yt-auto checkout."
    exit 1
}

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
    usage
fi

resolve_primary_root() {
    local start="${1:-.}"
    local common
    if common="$(git -C "$start" rev-parse --path-format=absolute --git-common-dir 2>/dev/null)"; then
        :
    elif common="$(git -C "$start" rev-parse --git-common-dir 2>/dev/null)"; then
        if [ "${common#/}" = "$common" ]; then
            common="$(cd "$start" && cd "$common" && pwd)"
        fi
    else
        echo "ERROR: $start is not inside a git worktree." >&2
        exit 1
    fi
    if [ "$(basename "$common")" = ".git" ]; then
        cd "$(dirname "$common")" && pwd -P
    else
        git -C "$start" worktree list --porcelain | awk '/^worktree / { print substr($0, 10); exit }'
    fi
}

relative_or_absolute() {
    local src="$1"
    local dest_parent="$2"
    if command -v realpath >/dev/null 2>&1; then
        realpath --relative-to="$dest_parent" "$src" 2>/dev/null || printf '%s\n' "$src"
    else
        printf '%s\n' "$src"
    fi
}

same_target() {
    local a="$1" b="$2"
    local ra rb
    ra="$(readlink -f "$a" 2>/dev/null || true)"
    rb="$(readlink -f "$b" 2>/dev/null || true)"
    [ -n "$ra" ] && [ "$ra" = "$rb" ]
}

link_shared() {
    local label="$1"
    local src="$2"
    local dest="$3"
    local dest_parent
    dest_parent="$(dirname "$dest")"

    if [ ! -e "$src" ]; then
        return 0
    fi

    mkdir -p "$dest_parent"

    if [ -e "$dest" ] && [ ! -L "$dest" ]; then
        echo "skip ${label}: exists and is not a symlink"
        return 0
    fi

    if [ -L "$dest" ] && same_target "$dest" "$src"; then
        echo "already linked ${label}"
        return 0
    fi

    local link_target
    link_target="$(relative_or_absolute "$src" "$dest_parent")"
    ln -sfn "$link_target" "$dest"
    echo "Linked ${label}"
}

link_loop_assets() {
    local src_root="$PRIMARY_ROOT/assets/loops"
    local dest_root="$TARGET_DIR/assets/loops"

    if [ ! -d "$src_root" ]; then
        return 0
    fi

    mkdir -p "$dest_root"

    # Link all .mp4 physical assets preserving category directory structure
    find "$src_root" -type f -name "*.mp4" | while IFS= read -r src_file; do
        local rel_path="${src_file#"$src_root"/}"
        local dest_file="$dest_root/$rel_path"
        local dest_dir
        dest_dir="$(dirname "$dest_file")"
        mkdir -p "$dest_dir"

        if [ -L "$dest_file" ] && same_target "$dest_file" "$src_file"; then
            continue
        fi

        local link_target
        link_target="$(relative_or_absolute "$src_file" "$dest_dir")"
        ln -sfn "$link_target" "$dest_file"
    done

    # Prune any dangling .mp4 symlinks in worktree if files were deleted from primary
    find "$dest_root" -xtype l -name "*.mp4" -delete 2>/dev/null || true
    echo "Linked assets/loops video files"
}

TARGET_DIR="$(cd "${1:-.}" && pwd)"
PRIMARY_ROOT="$(resolve_primary_root "$TARGET_DIR")"

if [ ! -d "$PRIMARY_ROOT" ]; then
    echo "ERROR: could not resolve primary repository root." >&2
    exit 1
fi

PRIMARY_REAL="$(cd "$PRIMARY_ROOT" && pwd -P)"
TARGET_REAL="$(cd "$TARGET_DIR" && pwd -P)"

if [ "$TARGET_REAL" = "$PRIMARY_REAL" ]; then
    echo "Primary checkout ${PRIMARY_REAL}: no worktree links required."
    exit 0
fi

link_shared ".venv" "$PRIMARY_ROOT/.venv" "$TARGET_DIR/.venv"
link_shared ".agents" "$PRIMARY_ROOT/.agents" "$TARGET_DIR/.agents"
link_shared ".env" "$PRIMARY_ROOT/.env" "$TARGET_DIR/.env"
mkdir -p "$TARGET_DIR/data"
if [ -f "$TARGET_DIR/data/loop_catalog.db" ] && [ ! -L "$TARGET_DIR/data/loop_catalog.db" ]; then
    rm -f "$TARGET_DIR/data/loop_catalog.db"
fi
link_shared "data/loop_catalog.db" "$PRIMARY_ROOT/data/loop_catalog.db" "$TARGET_DIR/data/loop_catalog.db"
link_loop_assets

echo "Worktree environment initialized in ${TARGET_DIR}"
