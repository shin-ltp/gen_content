#!/bin/bash
# Minimal POST probe: tiny token count, verify server responds end to end
export PATH="/root/fish/venv/bin:$PATH"
cd /root
REF_B64=$(base64 -w0 /mnt/c/my_project/gen-contents/us-stock-daily/assets/cast_refs/xiaomei/ref_audio.wav)
REF_TEXT=$(python -c "import json;print(json.load(open('/mnt/c/my_project/gen-contents/us-stock-daily/assets/cast_refs/xiaomei/ref_meta.json',encoding='utf-8'))['ref_text'])")
cat > /tmp/probe.json <<EOF
{"text":"テスト。","format":"wav","max_new_tokens":8,"references":[{"audio":"$REF_B64","text":"$REF_TEXT"}]}
EOF
echo "payload bytes: $(wc -c < /tmp/probe.json)"
curl -s -S -X POST http://127.0.0.1:8080/v1/tts -H "Content-Type: application/json" --data @/tmp/probe.json -o /tmp/probe.wav -w "http=%{http_code} time=%{time_total}s\n"
ls -la /tmp/probe.wav
