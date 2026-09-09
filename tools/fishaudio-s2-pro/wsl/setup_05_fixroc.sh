#!/usr/bin/env bash
# Force AMD-repo rocminfo/runtime over Ubuntu universe, then gate-test dxg enum
set -u
export DEBIAN_FRONTEND=noninteractive

echo "=== apt pin repo.radeon.com ==="
printf 'Package: *\nPin: origin repo.radeon.com\nPin-Priority: 1001\n' > /etc/apt/preferences.d/rocm

echo "=== purge universe leftovers ==="
apt-get purge -y libhsa-runtime64-1 libhsakmt1 rocminfo 2>&1 | tail -1
apt-get autoremove -y 2>&1 | tail -1

echo "=== install AMD versions ==="
apt-get install -y --allow-downgrades hsa-rocr rocminfo 2>&1 | tail -2

echo "=== ldconfig state ==="
echo '/opt/rocm/lib' > /etc/ld.so.conf.d/rocm.conf
echo '/opt/rocm-7.2.4/lib' >> /etc/ld.so.conf.d/rocm.conf
ldconfig
ldconfig -p | grep -E 'hsa-runtime|hsakmt|rocdxg'

echo "=== dpkg final ==="
dpkg -l | grep -E 'hsa-rocr|rocminfo|libhsakmt' | head -5

echo "=== rocminfo dxg gate ==="
export HSA_ENABLE_DXG_DETECTION=1
export LD_LIBRARY_PATH=/opt/rocm/lib
rocminfo 2>&1 | grep -i -E 'gfx|Marketing Name|PANIC|error|fail|NOT loaded' | head -25
echo "RC_DONE"
