#!/usr/bin/env bash
set -u
export HSA_ENABLE_DXG_DETECTION=1
export HSA_OVERRIDE_GFX_VERSION=11.0.0
export LD_LIBRARY_PATH=/opt/rocm/lib:/opt/rocm-7.2.4/lib
export FORCE_GFX1103_FIX=1
export MAX_SEQ_LEN=2048 KV_CACHE_BITS=4 GPU_RESIDENT=1 VRAM_FRACTION=0.98
export USE_SUBPROCESS_DECODER=false PYTHONIOENCODING=utf-8:replace
source /root/fish/venv/bin/activate
cd /root/fish/fish-speech
echo "=== python: $(which python) ==="
timeout 240 python -u tools/api_server.py \
  --listen 127.0.0.1:8080 \
  --llama-checkpoint-path checkpoints/fish-speech-s2-pro-int8 \
  --decoder-checkpoint-path checkpoints/fish-speech-s2-pro-int8/codec.pth \
  --decoder-config-name modded_dac_vq \
  --device cuda
echo "server_rc=$?"
