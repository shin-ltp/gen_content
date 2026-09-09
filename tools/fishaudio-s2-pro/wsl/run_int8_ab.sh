#!/bin/bash
# int8+compile A/B: two smoke runs (1st pays compile, 2nd = steady state).
LOG=/root/bench_int8_ab.log
echo "=== AB start $(date +%T) ===" >> "$LOG"
bash /root/run_bench.sh smoke >> "$LOG" 2>&1
sleep 5
bash /root/run_bench.sh smoke >> "$LOG" 2>&1
echo "=== AB end $(date +%T) ===" >> "$LOG"
