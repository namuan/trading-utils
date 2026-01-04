#!/usr/bin/env bash
if [[ $# -eq 0 ]]; then
  echo 'SESSION_NAME required as first argument'
  exit 0
fi

SESSION_NAME=$1

# Kill the tmux session
tmux kill-session -t "${SESSION_NAME}"
