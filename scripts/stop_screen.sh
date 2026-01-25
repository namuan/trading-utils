#!/usr/bin/env bash
if [[ $# -eq 0 ]]; then
  echo 'SESSION_NAME required as first argument'
  exit 0
fi

SESSION_NAME=$1

# Get all pids of the session
PIDS=$(tmux list-panes -t "${SESSION_NAME}" -F "#{pane_pid}" 2>/dev/null)

if [ -n "$PIDS" ]; then
  for pid in $PIDS; do
    # Find the process group ID (PGID) for the PID
    pgid=$(ps -o pgid= -p "$pid" | grep -o '[0-9]*')

    if [ -n "$pgid" ]; then
      # Kill the entire process group
      kill -TERM -"$pgid" 2>/dev/null
    fi
  done
fi

# Kill the tmux session
tmux kill-session -t "${SESSION_NAME}" 2>/dev/null
