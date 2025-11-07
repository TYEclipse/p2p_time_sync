#!/usr/bin/env bash
set -euo pipefail

BASEDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOGDIR="$BASEDIR/logs"

if [ ! -d "$LOGDIR" ]; then
  echo "No logs/pids found at $LOGDIR"
  exit 0
fi

echo "Stopping nodes using pid files in $LOGDIR"

shopt -s nullglob
for pidfile in "$LOGDIR"/*.pid; do
  pid=$(cat "$pidfile" || true)
  if [ -n "$pid" ]; then
    if kill -0 "$pid" 2>/dev/null; then
      echo "Killing pid $pid (from $pidfile)"
      kill "$pid" || true
      sleep 0.1
    else
      echo "Process $pid not running, removing $pidfile"
    fi
  fi
  rm -f "$pidfile"
done

echo "Done. You can check logs in $LOGDIR"