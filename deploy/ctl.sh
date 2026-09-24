#!/usr/bin/env bash
# YTAuto production control — single entrypoint for tmux-hosted services.
# Usage: ./deploy/ctl.sh {start|stop|status|restart} [sched|bot|all]
set -euo pipefail

PROJECT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [ -f "$PROJECT/.env" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$PROJECT/.env"
  set +a
fi
PY="${PYTHON_BIN:-}"
if [ -z "$PY" ] || [ ! -x "$PY" ]; then
  if [ -x "$PROJECT/.venv/bin/python" ]; then
    PY="$PROJECT/.venv/bin/python"
  else
    PY="$(command -v python3 || command -v python)"
  fi
fi
SESSION_PREFIX="${YT_CTL_SESSION_PREFIX:-ytauto}"

svc_session() { case "$1" in sched) echo "${SESSION_PREFIX}-sched";; bot) echo "${SESSION_PREFIX}-bot";; *) return 1;; esac; }
svc_script()  { case "$1" in sched) echo "deploy/tmux_scheduler.py";; bot) echo "deploy/tmux_review_bot.py";; *) return 1;; esac; }

is_running() {  # $1 = svc
  local script
  script="$(svc_script "$1" 2>/dev/null | sed 's|deploy/||' || true)"
  [ -n "$script" ] || return 1
  pgrep -f "$script" >/dev/null 2>&1
}

start_one() {
  local svc="$1" sess script
  sess="$(svc_session "$svc")"; script="$(svc_script "$svc")"
  if is_running "$svc"; then
    echo "[$svc] already running ($(pgrep -f "${script#deploy/}" | head -1)) — skip"
    return 0
  fi
  # Guard against running both Docker daemon and host tmux supervisor simultaneously
  if command -v docker >/dev/null 2>&1 && [ "${YT_FORCE_HOST:-0}" != "1" ]; then
    if docker ps --format '{{.Names}}' 2>/dev/null | grep -q '^yt-automation$'; then
      echo "[$svc] ERROR: Docker container 'yt-automation' is already running." >&2
      echo "[$svc] Running host tmux simultaneously duplicates resources and causes DB collisions." >&2
      echo "[$svc] Stop Docker container first or use YT_FORCE_HOST=1." >&2
      return 1
    fi
  fi
  # Clean dead session leftovers before recreating.
  tmux kill-session -t "$sess" 2>/dev/null || true
  mkdir -p "$PROJECT/logs"
  tmux new-session -d -s "$sess" \
    "cd '$PROJECT' && PYTHON_BIN='$PY' exec '$PY' '$script' >> 'logs/${sess#ytauto-}.out' 2>&1"
  sleep 2
  if is_running "$svc"; then
    echo "[$svc] STARTED (pid $(pgrep -f "${script#deploy/}" | head -1), tmux: $sess)"
  else
    echo "[$svc] FAILED to start — check logs/${sess#ytauto-}.out" >&2
    return 1
  fi
}

stop_one() {
  local svc="$1" sess script pid
  sess="$(svc_session "$svc")"; script="$(svc_script "$svc")"
  if is_running "$svc"; then
    pid="$(pgrep -f "${script#deploy/}" | head -1)"
    kill "$pid" 2>/dev/null || true
    for _ in $(seq 1 20); do is_running "$svc" || break; sleep 0.5; done
    is_running "$svc" && { kill -9 "$pid" 2>/dev/null || true; echo "[$svc] force-killed ($pid)"; } \
                      || echo "[$svc] stopped gracefully ($pid)"
  else
    echo "[$svc] not running"
  fi
  if [ "$svc" = "sched" ]; then
    pkill -f "python[0-9.]* .*main\.py daemon" 2>/dev/null || true
  fi
  tmux kill-session -t "$sess" 2>/dev/null || true
}

status_all() {
  local line script
  printf "%-6s %-14s %-8s %s\n" "SVC" "SESSION" "STATE" "PID"
  for svc in sched bot; do
    script="$(svc_script "$svc")"
    if is_running "$svc"; then
      line="$(pgrep -f "${script#deploy/}" | head -1)"
      printf "%-6s %-14s %-8s %s\n" "$svc" "$(svc_session "$svc")" "RUNNING" "$line"
    else
      printf "%-6s %-14s %-8s %s\n" "$svc" "$(svc_session "$svc")" "STOPPED" "-"
    fi
  done
}

main() {
  local action="${1:-status}" target="${2:-all}"
  case "$action" in
    start)
      [ "$target" = all ] && { start_one sched; start_one bot; } || start_one "$target";;
    stop)
      [ "$target" = all ] && { stop_one bot; stop_one sched; } || stop_one "$target";;
    restart) main stop "$target"; main start "$target";;
    status) status_all;;
    *) echo "usage: $0 {start|stop|status|restart} [sched|bot|all]" >&2; exit 2;;
  esac
}

main "$@"
