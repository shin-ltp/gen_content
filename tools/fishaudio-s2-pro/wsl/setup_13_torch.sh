#!/usr/bin/env bash
# Create venv, install torch 2.11 rocm7.2 + triton-rocm 3.6 (Linux-only path)
set -u
python3 -m venv /root/fish/venv
source /root/fish/venv/bin/activate
pip install -q --upgrade pip 2>&1 | tail -1
echo "=== torch install (big download) ==="
pip install torch==2.11.0 torchaudio==2.11.0 --index-url https://download.pytorch.org/whl/rocm7.2 2>&1 | tail -3
echo "=== triton ==="
pip install triton==3.6.0 --index-url https://download.pytorch.org/whl/rocm7.2 2>&1 | tail -3
echo "=== verify ==="
export HSA_ENABLE_DXG_DETECTION=1
export LD_LIBRARY_PATH=/opt/rocm/lib:/opt/rocm-7.2.4/lib
python - <<'EOF'
import torch
print("torch", torch.__version__, "hip", torch.version.hip)
print("cuda avail:", torch.cuda.is_available())
if torch.cuda.is_available():
    print("dev:", torch.cuda.get_device_name(0), torch.cuda.get_device_capability(0))
    x = torch.randn(2048, 2048, device="cuda", dtype=torch.bfloat16)
    y = x @ x
    torch.cuda.synchronize()
    print("matmul ok:", y.shape, y.dtype)
import triton
print("triton", triton.__version__)
EOF
echo TORCH_DONE
