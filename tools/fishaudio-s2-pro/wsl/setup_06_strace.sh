#!/usr/bin/env bash
# Trace how hsa runtime probes for GPU (dxg vs kfd)
set -u
export DEBIAN_FRONTEND=noninteractive
apt-get install -y -qq strace 2>&1 | tail -1
export HSA_ENABLE_DXG_DETECTION=1
strace -f -e trace=openat,ioctl,access /usr/bin/rocminfo 2>&1 | grep -E 'dxg|kfd|dri|drm|rocdxg|libdxcore|ENOENT' | grep -v -E 'ld\.so|libc|libm|libdl|locale|gconv|/proc|/sys/devices/system|tls' | head -40
echo STRACE_DONE
