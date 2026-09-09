#!/usr/bin/env bash
# apt audio libs + fish-speech python deps (torch already installed; pip must keep it)
set -u
export DEBIAN_FRONTEND=noninteractive
apt-get install -y -qq libsndfile1 portaudio19-dev ffmpeg git build-essential 2>&1 | tail -1
source /root/fish/venv/bin/activate
cd /root/fish/fish-speech
pip install --no-input \
  numpy "transformers>=4.45.0" "datasets==2.18.0" "lightning>=2.1.0" "hydra-core>=1.3.2" \
  "tensorboard>=2.14.1" "natsort>=8.4.0" "einops>=0.7.0" "librosa>=0.10.1" "rich>=13.5.3" \
  "gradio>=6.0" "grpcio>=1.58.0" "kui>=1.6.0" "uvicorn>=0.30.0" "loguru>=0.6.0" \
  "loralib>=0.1.2" "pyrootutils>=1.0.4" "resampy>=0.4.3" "einx[torch]==0.2.2" \
  "zstandard>=0.22.0" pydub pyaudio "modelscope==1.17.1" "opencc-python-reimplemented==0.1.7" \
  silero-vad ormsgpack "tiktoken>=0.8.0" "pydantic==2.9.2" cachetools descript-audio-codec safetensors \
  "protobuf>=3.20.0,<6.0.0" 2>&1 | grep -vE '^(Collecting|Downloading|Using cached)' | tail -6
pip install -e . --no-deps 2>&1 | tail -2
python -c "import torch; print('torch still', torch.__version__)"
echo DEPS_DONE
