#!/usr/bin/env bash
# Start (or restart) the fish-speech API server inside WSL, detached.
# Usage: bash start_server_bg.sh [compile|eager] [port]
set -u
MODE=${1:-eager}
PORT=${2:-8080}
pkill -f "tools/api_server.py" 2>/dev/null || true
sleep 1
: > /root/server.log
if [ "$MODE" = "compile" ]; then
  nohup env COMPILE=1 bash /root/run_server_wsl.sh "$PORT" >> /root/server.log 2>&1 &
else
  nohup bash /root/run_server_wsl.sh "$PORT" >> /root/server.log 2>&1 &
fi
echo "STARTED mode=$MODE pid=$!"
