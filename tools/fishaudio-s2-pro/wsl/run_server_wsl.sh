#!/usr/bin/env bash
# Fish Speech S2-Pro server on WSL2 (ROCm 7.2.4 + torch 2.11 + triton).
# Usage:  bash run_server_wsl.sh [port]            (eager)
#         COMPILE=1 bash run_server_wsl.sh [port]  (torch.compile / inductor)
set -u

export HSA_ENABLE_DXG_DETECTION=1            # rocdxg gate: ROCm < 7.13 needs this
export HSA_OVERRIDE_GFX_VERSION=11.0.0       # wheel has no gfx1103 binaries -> segfault
export LD_LIBRARY_PATH=/opt/rocm/lib:/opt/rocm-7.2.4/lib
export FORCE_GFX1103_FIX=1                   # arch reports gfx1100 after override; force patches

export HSA_ENABLE_SDMA=0
export GPU_MAX_HW_QUEUES=1
export HSA_USE_SVM=0
export MAX_SEQ_LEN=${MAX_SEQ_LEN:-2048}
export KV_CACHE_BITS=${KV_CACHE_BITS:-4}
export GPU_RESIDENT=${GPU_RESIDENT:-1}
export VRAM_FRACTION=${VRAM_FRACTION:-0.98}
export LLM_TIMEOUT=${LLM_TIMEOUT:-1200}
export MIOPEN_FIND_MODE=${MIOPEN_FIND_MODE:-3}
export PYTORCH_HIP_ALLOC_CONF=max_split_size_mb:4096
export USE_SUBPROCESS_DECODER=false
export PYTHONIOENCODING=utf-8:replace
export TRITON_CACHE_DIR=/root/.triton_cache
export TORCHINDUCTOR_CACHE_DIR=/root/.inductor_cache

PORT=${1:-8080}

source /root/fish/venv/bin/activate
cd /root/fish/fish-speech

ARGS=(--listen 127.0.0.1:${PORT}
      --llama-checkpoint-path checkpoints/fish-speech-s2-pro-int8
      --decoder-checkpoint-path checkpoints/fish-speech-s2-pro-int8/codec.pth
      --decoder-config-name modded_dac_vq
      --device cuda)
if [ "${COMPILE:-0}" = "1" ]; then ARGS+=(--compile); fi

echo "COMPILE=${COMPILE:-0} GPU_RESIDENT=$GPU_RESIDENT MAX_SEQ_LEN=$MAX_SEQ_LEN SKIP_GFX1103_FIX=${SKIP_GFX1103_FIX:-} port=$PORT"
exec python tools/api_server.py "${ARGS[@]}"
