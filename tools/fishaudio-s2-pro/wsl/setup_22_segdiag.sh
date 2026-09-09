#!/usr/bin/env bash
set -u
export HSA_ENABLE_DXG_DETECTION=1
export LD_LIBRARY_PATH=/opt/rocm/lib:/opt/rocm-7.2.4/lib
source /root/fish/venv/bin/activate
for step in t1 t2 t3 t4 t5; do
python - <<EOF 2>&1 | tail -3
import sys
print("STEP $step start", flush=True)
import torch
torch.cuda.init()
print("cuda init ok", flush=True)
if "$step" == "t2":
    p = torch.cuda.get_device_properties(0)
    print(p.name, p.gcnArchName, p.total_memory/1e9, flush=True)
if "$step" == "t3":
    a = torch.randn(256, 256, device="cuda")
    print("randn ok", flush=True)
if "$step" == "t4":
    a = torch.randn(2048, 2048, device="cuda", dtype=torch.bfloat16)
    print("mm", (a@a).float().mean().item(), flush=True)
if "$step" == "t5":
    b = torch.empty(int(11e9//2), dtype=torch.bfloat16, device="cuda")
    print("11GB alloc ok", flush=True)
print("STEP $step done", flush=True)
EOF
done
echo SEGDIAG_DONE
