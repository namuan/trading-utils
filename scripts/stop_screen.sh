#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")"/.. && pwd)"
DEFAULT_NAME="$(basename "$PROJECT_DIR")"
SESSION_NAME="${SESSION_NAME:-$DEFAULT_NAME}"

if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
  tmux kill-session -t "$SESSION_NAME"
  echo "Stopped tmux session '$SESSION_NAME'."
else
  echo "tmux session '$SESSION_NAME' not found."
fi
#!/usr/bin/env bash
if [[ $# -eq 0 ]]; then
  echo 'SESSION_NAME required as first argument'
  exit 0
fi

SESSION_NAME=$1

# Kill the tmux session
tmux kill-session -t "${SESSION_NAME}"
