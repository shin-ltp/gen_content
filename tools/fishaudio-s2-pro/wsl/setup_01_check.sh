#!/usr/bin/env bash
# List all rocdxg releases to find one matching gfx1103 (Radeon 780M)
set -u
curl -sL --max-time 25 "https://api.github.com/repos/ROCm/librocdxg/releases" -o /tmp/rel.json
python3 - <<'EOF'
import json
data = json.load(open("/tmp/rel.json"))
for r in data:
    print(r["tag_name"], "|", r["name"])
EOF
