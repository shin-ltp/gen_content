#!/usr/bin/env bash
# Verify gfx1103 (780M, PCI dev 0x1500) inside librocdxg source table
set -u
echo "=== fetch rocdxg source ==="
cd /root/setup
curl -sL --max-time 30 -o rocdxg.cpp https://raw.githubusercontent.com/ROCm/rocm-systems/develop/projects/rocr-runtime/libhsakmt/src/dxg/rocdxg.cpp
wc -c rocdxg.cpp
echo "=== gfxip table ==="
grep -n -E '\{[ ]*0x1|[ ]*16[0-9]{3},' rocdxg.cpp | head -40
echo "=== gfx1103 mentions ==="
grep -n -i 'gfx1103\|0x1500\|1500,' rocdxg.cpp | head -10
echo GATE4_DONE
