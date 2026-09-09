#!/usr/bin/env bash
set -u
export HSA_ENABLE_DXG_DETECTION=1
export LD_LIBRARY_PATH=/opt/rocm/lib:/opt/rocm-7.2.4/lib
source /root/fish/venv/bin/activate
cd /root/fish/fish-speech
python - <<'EOF'
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
import torch
print("torch", torch.__version__, "cuda avail:", torch.cuda.is_available())
import transformers
print("transformers", transformers.__version__)
try:
    import tools.server.model_manager as mm
    print("model_manager import OK")
except Exception as e:
    print("IMPORT FAIL:", type(e).__name__, e)
    raise
EOF
echo IMPORT_DONE
