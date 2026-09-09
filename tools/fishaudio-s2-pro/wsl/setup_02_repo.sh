#!/usr/bin/env bash
# Probe ROCm apt repo structure for 7.x on ubuntu2404
set -u
echo "=== apt root listing (rocm dir) ==="
curl -s --max-time 10 https://repo.radeon.com/rocm/apt/ | grep -oE 'href="[^"]+"' | tail -25
echo "=== 7.2 top ==="
curl -s --max-time 10 https://repo.radeon.com/rocm/apt/7.2/ | grep -oE 'href="[^"]+"' | head -15
echo "=== try jammy/noble Release paths ==="
for p in "7.2/dists/jammy/Release" "7.2/dists/noble/Release" "7.2/layers/dists/ubuntu2404/Release"; do
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "https://repo.radeon.com/rocm/apt/$p")
  echo "$p -> $code"
done
