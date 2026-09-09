#!/usr/bin/env bash
# Wait until the local API server answers (or timeout), then show the log tail.
set -u
LIMIT=${1:-60}
for i in $(seq 1 "$LIMIT"); do
  code=$(curl -s -o /dev/null -m 2 -w '%{http_code}' http://127.0.0.1:8080/ 2>/dev/null)
  if [ "$code" != "000" ] && [ -n "$code" ]; then
    echo "READY http_code=$code after $((i * 5))s"
    break
  fi
  sleep 5
done
echo "=== server.log tail ==="
tail -25 /root/server.log
