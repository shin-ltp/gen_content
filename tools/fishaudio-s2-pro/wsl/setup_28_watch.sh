#!/usr/bin/env bash
# Relaunch the server, then sample memory + process state every 5s.
set -u
pkill -9 -f "api_serve[r].py" 2>/dev/null || true
sleep 1
echo "=== dmesg before ==="
dmesg | tail -3
setsid nohup bash /root/run.sh > /root/fg.log 2>&1 < /dev/null &
echo "LAUNCHED pid=$!"
for i in $(seq 1 60); do
  sleep 5
  alive=$(pgrep -f "api_serve[r].py" | head -1)
  mem=$(awk "/MemAvailable/{print \$2/1048576}" /proc/meminfo)
  rss=$(awk "/VmRSS/{print \$2/1048576}" /proc/$alive/status 2>/dev/null || echo "-")
  echo "t=$((i*5))s alive=$alive availGB=${mem} rssGB=${rss}"
  if [ -z "$alive" ]; then echo "PROCESS DIED at t=$((i*5))s"; break; fi
done
echo "=== log tail ==="
tail -8 /root/fg.log | cut -c1-180
echo "=== dmesg after ==="
dmesg | tail -15
echo "=== journal oom ==="
journalctl -k --since "-5 min" 2>/dev/null | grep -iE "oom|killed" | tail -8
