#!/usr/bin/env bash
# Find the Ryzen-on-WSL official doc page and dump it
set -u
curl -sL --max-time 20 https://rocm.docs.amd.com/projects/radeon-ryzen/en/latest/index.html \
  | grep -oE 'href="[^"]*"' | grep -iE 'wsl' | sort -u | head -20
echo LINKS_DONE
