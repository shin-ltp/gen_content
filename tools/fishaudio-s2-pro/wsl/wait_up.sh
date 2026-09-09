#!/bin/bash
# Poll until the API server finishes loading (Uvicorn line in /root/fg.log).
# usage: wait_up.sh [max_polls] [sleep_sec]
MAX=${1:-40}
SEC=${2:-5}
for i in $(seq 1 "$MAX"); do
  if grep -aq "Uvicorn running" /root/fg.log; then
    echo READY
    exit 0
  fi
  sleep "$SEC"
done
echo TIMEOUT
exit 1
