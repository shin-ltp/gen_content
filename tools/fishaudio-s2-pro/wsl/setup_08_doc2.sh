#!/usr/bin/env bash
# Dump Ryzen-on-WSL official how-to as plain text
set -u
curl -sL --max-time 25 https://rocm.docs.amd.com/projects/radeon-ryzen/en/latest/docs/install/installryz/wsl/howto_wsl.html \
  | sed -e 's/<script[^>]*>.*<\/script>//g' -e 's/<[^>]*>//g' \
  | grep -vE '^\s*$' | head -160
echo DOC2_DONE
