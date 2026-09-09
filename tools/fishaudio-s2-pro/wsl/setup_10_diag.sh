#!/usr/bin/env bash
# Diagnose why runtime never touches /dev/dxg
set -u
echo "=== ld cache (dxg/hsakmt) ==="
ldconfig -p | grep -E 'dxcore|rocdxg|hsakmt|hsa-runtime'
echo "=== /opt ==="
ls -la /opt | grep -i rocm
echo "=== runtime NEEDED/RUNPATH ==="
objdump -p /opt/rocm-7.2.4/lib/libhsa-runtime64.so.1 | grep -E 'NEEDED|RUNPATH'
echo "=== strace dxg-relevant opens ==="
export HSA_ENABLE_DXG_DETECTION=1
strace -f -e trace=openat /usr/bin/rocminfo 2>&1 | grep -iE 'dxg|dxcore|rocdxg|hsakmt|kfd|amdgpu' | head -30
echo DIAG_DONE
