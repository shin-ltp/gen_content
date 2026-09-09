#!/usr/bin/env bash
# Long-running server (no timeout); tee keeps a copy at /root/fg.log.
set -u
export HSA_ENABLE_DXG_DETECTION=1
export HSA_OVERRIDE_GFX_VERSION=11.0.0
export LD_LIBRARY_PATH=/opt/rocm/lib:/opt/rocm-7.2.4/lib
export FORCE_GFX1103_FIX=1
export MAX_SEQ_LEN=2048 KV_CACHE_BITS=4 GPU_RESIDENT=1 VRAM_FRACTION=0.98
export LLM_TIMEOUT=1200 MIOPEN_FIND_MODE=3
export PYTORCH_HIP_ALLOC_CONF=max_split_size_mb:4096
export USE_SUBPROCESS_DECODER=false PYTHONIOENCODING=utf-8:replace
export TRITON_CACHE_DIR=/root/.triton_cache
export TORCHINDUCTOR_CACHE_DIR=/root/.inductor_cache
source /root/fish/venv/bin/activate
cd /root/fish/fish-speech
CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-}
ARGS="--listen 127.0.0.1:8080 --llama-checkpoint-path checkpoints/fish-speech-s2-pro-int8 --decoder-checkpoint-path checkpoints/fish-speech-s2-pro-int8/codec.pth --decoder-config-name modded_dac_vq --device cuda"
if [ "${COMPILE:-0}" = "1" ]; then ARGS="$ARGS --compile"; fi
echo "RUN COMPILE=${COMPILE:-0}"
exec python -u tools/api_server.py $ARGS
