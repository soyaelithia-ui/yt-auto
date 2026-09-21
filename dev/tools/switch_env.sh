#!/usr/bin/env bash
# dev/switch_env.sh - Profile & Environment Switcher for yt-auto

TARGET_PROFILE="${1:-dev}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

case "$TARGET_PROFILE" in
    prod|production)
        export YT_PROFILE="prod"
        export YT_AUTO_ENV="production"
        export WORK_ROOT="$REPO_ROOT/work/prod"
        export ARTIFACT_ROOT="$REPO_ROOT/artifacts/prod"
        export YOUTUBE_AUTOMATION_DB="$REPO_ROOT/data/shorts_queue.db"
        export VIDEO_REVIEW_DB_PATH="$REPO_ROOT/data/review_state.db"
        echo "🟢 [yt-auto] Entorno cambiado a: PRODUCCIÓN (YT_PROFILE=prod)"
        echo "   • DB: $YOUTUBE_AUTOMATION_DB"
        echo "   • Work: $WORK_ROOT"
        ;;
    test|testing)
        export YT_PROFILE="test"
        export YT_AUTO_ENV="test"
        export WORK_ROOT="$REPO_ROOT/work/test"
        export ARTIFACT_ROOT="$REPO_ROOT/artifacts/test"
        export YOUTUBE_AUTOMATION_DB="$REPO_ROOT/data/test/shorts_queue.db"
        export VIDEO_REVIEW_DB_PATH="$REPO_ROOT/data/test/review_state.db"
        echo "🟡 [yt-auto] Entorno cambiado a: TEST / PRUEBAS (YT_PROFILE=test)"
        echo "   • DB: $YOUTUBE_AUTOMATION_DB"
        echo "   • Work: $WORK_ROOT"
        ;;
    dev|cli|sandbox|*)
        export YT_PROFILE="cli"
        export YT_AUTO_ENV="development"
        export WORK_ROOT="$REPO_ROOT/work/cli"
        export ARTIFACT_ROOT="$REPO_ROOT/artifacts/cli"
        export YOUTUBE_AUTOMATION_DB="$REPO_ROOT/data/cli/shorts_queue.db"
        export VIDEO_REVIEW_DB_PATH="$REPO_ROOT/data/cli/review_state.db"
        echo "🔵 [yt-auto] Entorno cambiado a: DESARROLLO / SANDBOX (YT_PROFILE=cli)"
        echo "   • DB: $YOUTUBE_AUTOMATION_DB"
        echo "   • Work: $WORK_ROOT"
        ;;
esac
