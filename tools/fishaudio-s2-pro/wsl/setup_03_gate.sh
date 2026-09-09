#!/usr/bin/env bash
# GATE TEST: install minimal ROCm runtime via apt, verify 780M (gfx1103) visible via dxg
set -u
export DEBIAN_FRONTEND=noninteractive

echo "=== add rocm 7.2.4 apt source ==="
install -d -m0755 -o root -g root /etc/apt/keyrings
curl -fsSL --max-time 30 https://repo.radeon.com/rocm/rocm.gpg.key | gpg --dearmor -o /etc/apt/keyrings/rocm.gpg
echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/rocm.gpg] https://repo.radeon.com/rocm/apt/7.2.4 noble main" > /etc/apt/sources.list.d/rocm.list

echo "=== apt update (tail) ==="
apt-get update 2>&1 | tail -3

echo "=== install minimal runtime (no DKMS metapkg) ==="
apt-get install -y --no-install-recommends rocm-core rocminfo rocm-smi-lib libhsa-runtime64-1 2>&1 | tail -4

echo "=== verify librocdxg present in system rocm ==="
ls -la /opt/rocm/lib/librocdxg.so* 2>/dev/null
ls -la /opt/rocm/lib/libhsakmt.so* 2>/dev/null

echo "=== rocminfo via dxg ==="
export HSA_ENABLE_DXG_DETECTION=1
export LD_LIBRARY_PATH=/opt/rocm/lib:${LD_LIBRARY_PATH:-}
PATH=/opt/rocm/bin:$PATH rocminfo 2>&1 | grep -i -E 'gfx|Marketing Name|Agent|error|fail' | head -40
