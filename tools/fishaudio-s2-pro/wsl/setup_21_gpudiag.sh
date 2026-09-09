#!/usr/bin/env bash
set -u
export HSA_ENABLE_DXG_DETECTION=1
export LD_LIBRARY_PATH=/opt/rocm/lib:/opt/rocm-7.2.4/lib
source /root/fish/venv/bin/activate
python - <<'EOF'
import torch, triton
print("triton", triton.__version__)
assert torch.cuda.is_available()
p = torch.cuda.get_device_properties(0)
print("name:", p.name, "arch:", p.gcnArchName)
print("total_memory: %.2f GB" % (p.total_memory / 1e9))
a = torch.randn(2048, 2048, device="cuda", dtype=torch.bfloat16)
print("matmul ok:", (a @ a).float().mean().item())
# big alloc test: can we reserve 11GB?
del a
try:
    b = torch.empty(int(11e9 // 2), dtype=torch.bfloat16, device="cuda")
    print("11GB alloc ok, free now: %.2f GB" % (torch.cuda.mem_get_info()[0] / 1e9))
    del b
except RuntimeError as e:
    print("11GB alloc FAILED:", str(e)[:200])
EOF
echo GPUDIAG_DONE
