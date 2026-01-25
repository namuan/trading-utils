#!/usr/bin/env bash
if [[ $# -eq 0 ]] ; then
    echo 'COMMAND required as first argument. python3.6 ...'
    exit 0
fi

SESSION_NAME=$1
SESSION_CMD=$2

# Kill existing session if it exists
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
"${SCRIPT_DIR}/stop_screen.sh" "${SESSION_NAME}"

# Create new session and run command
tmux new-session -d -s "${SESSION_NAME}" "${SESSION_CMD}"
