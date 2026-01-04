#!/usr/bin/env bash
if [[ $# -eq 0 ]] ; then
    echo 'SESSION_NAME and COMMAND required as arguments'
    exit 0
fi

SESSION_NAME=$1
SESSION_CMD=$2

# Kill existing session if it exists
tmux kill-session -t "${SESSION_NAME}" 2>/dev/null

# Create new session and run command
tmux new-session -d -s "${SESSION_NAME}" "${SESSION_CMD}"
