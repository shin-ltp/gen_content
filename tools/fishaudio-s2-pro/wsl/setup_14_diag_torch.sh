#!/usr/bin/env bash
# Isolate the torch import segfault: numpy? HIP init? bundled hsa?
set -u
source /root/fish/venv/bin/activate
pip install -q numpy 2>&1 | tail -1
export HSA_ENABLE_DXG_DETECTION=1
export LD_LIBRARY_PATH=/opt/rocm/lib:/opt/rocm-7.2.4/lib
echo "=== which hsa does torch bundle ==="
ls /root/fish/venv/lib/python3.12/site-packages/torch/lib | grep -E 'hsa|rocm|hip' | head
echo "=== step1: import torch only ==="
python -c "import torch; print('torch', torch.__version__, 'hip', torch.version.hip)"; echo "rc1=$?"
echo "=== step2: is_available ==="
python -c "import torch; print('avail', torch.cuda.is_available())"; echo "rc2=$?"
echo "=== step3: matmul with bundled hsa path (no /opt) ==="
env -u LD_LIBRARY_PATH python -c "import torch; torch.zeros(1).cuda(); print('cuda ok')"; echo "rc3=$?"
echo DIAG_TORCH_DONE
