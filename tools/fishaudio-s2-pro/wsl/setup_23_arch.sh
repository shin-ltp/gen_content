#!/usr/bin/env bash
set -u
export HSA_ENABLE_DXG_DETECTION=1
export LD_LIBRARY_PATH=/opt/rocm/lib:/opt/rocm-7.2.4/lib
source /root/fish/venv/bin/activate
echo "=== hip ==="; python -c "import torch; print(torch.version.hip, torch.version.rocm if hasattr(torch.version,'rocm') else '')"
echo "=== arch list (env) ==="; python -c "import torch; print(torch.cuda.get_arch_list())"
echo "=== default arch ==="; python -c "import os; print(os.environ.get('PYTORCH_TUNABLEOP_ENABLED',''), os.environ.get('HSA_OVERRIDE_GFX_VERSION',''))"
echo "=== matmul with override 11.0.0 ==="
HSA_OVERRIDE_GFX_VERSION=11.0.0 python - <<'EOF'
import torch
a = torch.randn(512, 512, device="cuda", dtype=torch.bfloat16)
print("mm", (a @ a).float().mean().item())
EOF
echo "rc=$?"
echo "=== matmul with override 11.0.2 ==="
HSA_OVERRIDE_GFX_VERSION=11.0.2 python - <<'EOF'
import torch
a = torch.randn(512, 512, device="cuda", dtype=torch.bfloat16)
print("mm", (a @ a).float().mean().item())
EOF
echo "rc=$?"
echo ARCH_DONE
