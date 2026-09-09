#!/usr/bin/env bash
# Copy repo + checkpoints from /mnt/c to ext4 for best IO
set -u
SRC=/mnt/c/my_project/gen-contents/tools/fishaudio-s2-pro/fish-speech
DST=/root/fish
mkdir -p $DST

echo "=== system deps ==="
export DEBIAN_FRONTEND=noninteractive
apt-get install -y -qq python3-venv python3-pip rsync 2>&1 | tail -1

echo "=== sync repo (excl venv/ckpt/pycache) ==="
rsync -a --info=stats1,progress2 \
  --exclude '.venv' --exclude 'checkpoints' --exclude '__pycache__' \
  --exclude 'rocm-env*' --exclude '*.log' --exclude '*.err' \
  "$SRC/" "$DST/fish-speech/" 2>&1 | tail -4

echo "=== copy checkpoints (7GB, via 9p; be patient) ==="
mkdir -p "$DST/fish-speech/checkpoints"
rsync -a --info=stats1,progress2 "$SRC/checkpoints/" "$DST/fish-speech/checkpoints/" 2>&1 | tail -4

echo "=== sizes ==="
du -sh $DST/fish-speech $DST/fish-speech/checkpoints
echo COPY_DONE
