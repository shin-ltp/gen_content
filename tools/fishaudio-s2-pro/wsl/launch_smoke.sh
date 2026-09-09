#!/bin/bash
# Launch bench_wsl.py in background, detached, with fixed log path
cd /root
export PATH="/root/fish/venv/bin:$PATH"
if pgrep -f "bench_ws[l].py" > /dev/null; then
  echo "already running"
  exit 0
fi
setsid nohup python /root/bench_wsl.py "$1" > "/root/smoke_$1.log" 2>&1 < /dev/null &
echo "STARTED pid=$!"
