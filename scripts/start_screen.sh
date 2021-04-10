#!/usr/bin/env bash
if [[ $# -eq 0 ]] ; then
    echo 'COMMAND required as first argument. python3.6 ...'
    exit 0
fi

SCREEN_NAME=$1
SCREEN_CMD=$2

screen -X -S "${SCREEN_NAME}" stuff "^C"
screen -X -S "${SCREEN_NAME}" quit
screen -d -m -S "${SCREEN_NAME}"
screen -S "${SCREEN_NAME}" -p 0 -X stuff "${SCREEN_CMD}$(printf \\r)"