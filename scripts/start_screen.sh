#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")"/.. && pwd)"
DEFAULT_NAME="$(basename "$PROJECT_DIR")"
SESSION_NAME="${SESSION_NAME:-$DEFAULT_NAME}"

if ! command -v tmux >/dev/null 2>&1; then
  echo "tmux is not installed. On macOS, install via: brew install tmux"
  exit 1
fi

if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
  echo "tmux session '$SESSION_NAME' already exists."
else
  tmux new-session -d -s "$SESSION_NAME"
  echo "Started tmux session '$SESSION_NAME'."
fi

if [[ "${ATTACH:-0}" == "1" ]]; then
  tmux attach -t "$SESSION_NAME"
fi
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
