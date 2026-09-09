#!/usr/bin/env bash
# GATE TEST 2: install AMD-repo hsa-rocr + rocminfo, verify gfx1103 via dxg
set -u
export DEBIAN_FRONTEND=noninteractive

echo "=== purge ubuntu-universe runtime ==="
apt-get purge -y libhsa-runtime64-1 rocminfo 2>&1 | tail -2
apt-get autoremove -y 2>&1 | tail -1

echo "=== install AMD repo runtime ==="
apt-get install -y --no-install-recommends hsa-rocr rocminfo rocm-smi-lib 2>&1 | tail -3

echo "=== hsa libs ==="
ls -la /opt/rocm/lib/libhsa-runtime64.so* 2>/dev/null | head -5
ls -la /opt/rocm/lib/libhsakmt.so* /opt/rocm/lib/librocdxg.so* 2>/dev/null

echo "=== rocminfo via dxg ==="
export HSA_ENABLE_DXG_DETECTION=1
export LD_LIBRARY_PATH=/opt/rocm/lib
/opt/rocm/bin/rocminfo 2>&1 | grep -i -E 'gfx|Marketing Name|Agent |THE AGENTS|error|fail|dxg' | head -40
echo "EXIT_CODE_ABOVE"
