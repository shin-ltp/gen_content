#!/usr/bin/env bash
# Dump the install section of Ryzen-on-WSL doc + rocdxg v1.1.x release notes
set -u
echo "===== DOC: install section ====="
curl -sL --max-time 25 https://rocm.docs.amd.com/projects/radeon-ryzen/en/latest/docs/install/installryz/wsl/howto_wsl.html \
  | sed -e 's/<[^>]*>//g' | grep -vE '^\s*$' \
  | sed -n '/Install WSL with ROCDXG/,/DOCX_END/p' | head -120
echo "===== v1.1.0 notes ====="
curl -sL --max-time 20 "https://api.github.com/repos/ROCm/librocdxg/releases/tags/v1.1.0" \
  | grep -oE '"body":.*' | head -c 2500
echo
echo "===== v1.1.2 notes ====="
curl -sL --max-time 20 "https://api.github.com/repos/ROCm/librocdxg/releases/tags/v1.1.2" \
  | grep -oE '"body":.*' | head -c 2000
echo
echo DOC3_DONE
