#!/bin/sh
# Non-root runtime gate: agy must live in the image; volumes must be writable.
set -e

if [ ! -x /usr/local/bin/agy ]; then
  echo "yt-auto: Antigravity CLI missing at /usr/local/bin/agy. Rebuild after ./scripts/stage_agy.sh" >&2
  exit 1
fi

uid="$(id -u)"
if [ "$uid" = "0" ]; then
  echo "yt-auto: refusing to start as root" >&2
  exit 1
fi

for d in /app/data /app/work /app/artifacts /app/logs /app/output /tmp /home/appuser/.gemini; do
  if [ -e "$d" ] && [ ! -w "$d" ]; then
    echo "yt-auto: $d is not writable by uid ${uid}. Recreate named volumes (docker compose down -v)." >&2
    exit 1
  fi
done

exec "$@"
