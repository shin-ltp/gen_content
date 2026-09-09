#!/usr/bin/env bash
# Check tooling and record torch state to a file
set -u
source /root/fish/venv/bin/activate
echo "uv: $(command -v uv || echo none)"
echo "pip: $(pip --version 2>&1)"
python -c "import numpy; print('numpy', numpy.__version__)"
python -c "import torch,triton; print('torch',torch.__version__,'hip',torch.version.hip,'avail',torch.cuda.is_available(),'name',torch.cuda.get_device_name(0),'triton',triton.__version__)"
echo ENV_DONE
