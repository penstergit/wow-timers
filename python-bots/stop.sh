#!/usr/bin/env bash
# Stops all running bots by PID.

cd "$(dirname "$0")"

for name in bg agm dmf stv; do
  pid_file=".pid_${name}"
  if [ -f "$pid_file" ]; then
    PID=$(cat "$pid_file")
    if kill -0 "$PID" 2>/dev/null; then
      kill "$PID"
      echo "[STOP] $name  (PID $PID)"
    else
      echo "[SKIP] $name — PID $PID not running"
    fi
    rm "$pid_file"
  else
    echo "[SKIP] $name — no PID file found"
  fi
done

echo "Done."
