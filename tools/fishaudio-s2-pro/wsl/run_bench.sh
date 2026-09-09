#!/bin/bash
# Foreground bench runner: usage: run_bench.sh <smoke|long|both>
export PATH="/root/fish/venv/bin:$PATH"
cd /root
MODE="$1"
echo "=== bench mode=$MODE start=$(date +%T) ==="
python -u /root/bench_wsl.py "$MODE"
echo "=== rc=$? end=$(date +%T) ==="
