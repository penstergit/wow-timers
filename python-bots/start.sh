#!/usr/bin/env bash
# Starts all four bots in the background and saves their PIDs.
# Logs go to logs/bg.log, logs/agm.log, logs/dmf.log, logs/stv.log

set -e
cd "$(dirname "$0")"

mkdir -p logs data

start_bot() {
  local name="$1"
  local script="$2"
  local pid_file=".pid_${name}"
  local log_file="logs/${name}.log"

  if [ -f "$pid_file" ] && kill -0 "$(cat "$pid_file")" 2>/dev/null; then
    echo "[SKIP] $name is already running (PID $(cat "$pid_file"))"
    return
  fi

  nohup python3 "$script" >> "$log_file" 2>&1 &
  echo $! > "$pid_file"
  echo "[START] $name  (PID $!)  — logs: $log_file"
}

start_bot bg    bot_bg.py
start_bot agm   bot_agm.py
start_bot dmf   bot_dmf.py
start_bot stv   bot_stv.py

echo ""
echo "All bots started. Use ./stop.sh to shut them down."
echo "Use 'tail -f logs/bg.log' etc. to watch live output."
