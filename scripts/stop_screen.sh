#!/usr/bin/env bash
if [[ $# -eq 0 ]]; then
  echo 'COMMAND required as first argument. python3.6 ...'
  exit 0
fi

SCREEN_NAME=$1

screen -X -S "${SCREEN_NAME}" stuff "^C"
screen -X -S "${SCREEN_NAME}" quit

