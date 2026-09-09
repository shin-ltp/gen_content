#!/usr/bin/env bash
# Sync the Windows-side gfx1103 patches into the ext4 repo copy (same base
# commit, so direct file copy with CRLF strip is exact and simplest).
set -eu
SRC=/mnt/c/my_project/gen-contents/tools/fishaudio-s2-pro/fish-speech
DST=/root/fish/fish-speech
FILES="
fish_speech/utils/rocm_gfx1103.py
fish_speech/inference_engine/__init__.py
fish_speech/inference_engine/vq_manager.py
fish_speech/models/dac/inference.py
fish_speech/models/text2semantic/inference.py
tools/server/model_manager.py
"
for f in $FILES; do
  tr -d '\r' < "$SRC/$f" > "$DST/$f"
  echo "synced $f"
done
source /root/fish/venv/bin/activate
cd "$DST"
python -c "import ast,sys; [ast.parse(open(p).read()) for p in ['fish_speech/utils/rocm_gfx1103.py','fish_speech/inference_engine/__init__.py','tools/server/model_manager.py']]; print('SYNTAX_OK')"
echo SYNC_DONE
