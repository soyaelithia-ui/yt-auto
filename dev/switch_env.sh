#!/usr/bin/env bash
# dev/switch_env.sh - Profile & Environment Switcher for yt-auto

TARGET_PROFILE="${1:-dev}"

case "$TARGET_PROFILE" in
    prod|production)
        export YT_PROFILE="prod"
        export YT_AUTO_ENV="production"
        export WORK_ROOT="/home/moku/projects/yt-auto/work/prod"
        export ARTIFACT_ROOT="/home/moku/projects/yt-auto/artifacts/prod"
        export YOUTUBE_AUTOMATION_DB="/home/moku/projects/yt-auto/data/shorts_queue.db"
        export VIDEO_REVIEW_DB_PATH="/home/moku/projects/yt-auto/data/review_state.db"
        echo "🟢 [yt-auto] Entorno cambiado a: PRODUCCIÓN (YT_PROFILE=prod)"
        echo "   • DB: $YOUTUBE_AUTOMATION_DB"
        echo "   • Work: $WORK_ROOT"
        ;;
    test|testing)
        export YT_PROFILE="test"
        export YT_AUTO_ENV="test"
        export WORK_ROOT="/home/moku/projects/yt-auto/work/test"
        export ARTIFACT_ROOT="/home/moku/projects/yt-auto/artifacts/test"
        export YOUTUBE_AUTOMATION_DB="/home/moku/projects/yt-auto/data/test/shorts_queue.db"
        export VIDEO_REVIEW_DB_PATH="/home/moku/projects/yt-auto/data/test/review_state.db"
        echo "🟡 [yt-auto] Entorno cambiado a: TEST / PRUEBAS (YT_PROFILE=test)"
        echo "   • DB: $YOUTUBE_AUTOMATION_DB"
        echo "   • Work: $WORK_ROOT"
        ;;
    dev|cli|sandbox|*)
        export YT_PROFILE="cli"
        export YT_AUTO_ENV="development"
        export WORK_ROOT="/home/moku/projects/yt-auto/work/cli"
        export ARTIFACT_ROOT="/home/moku/projects/yt-auto/artifacts/cli"
        export YOUTUBE_AUTOMATION_DB="/home/moku/projects/yt-auto/data/cli/shorts_queue.db"
        export VIDEO_REVIEW_DB_PATH="/home/moku/projects/yt-auto/data/cli/review_state.db"
        echo "🔵 [yt-auto] Entorno cambiado a: DESARROLLO / SANDBOX (YT_PROFILE=cli)"
        echo "   • DB: $YOUTUBE_AUTOMATION_DB"
        echo "   • Work: $WORK_ROOT"
        ;;
esac
