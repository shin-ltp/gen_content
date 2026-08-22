"""ComfyUI img2img ワークフロー送信テスト（Mac API）"""
import base64
import json
import subprocess
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from generate_images import ImageGenerator
from config import COMFYUI_DIR, COMFYUI_API_PORT, COMFYUI_IMG2IMG_DENOISE

HOST = "cho@rw-mac-1"
REF = "ref_2448201804.jpg"  # 既に Mac input にあるファイル
PROMPT = "cinematic editorial portrait, dramatic lighting, premium magazine style"

g = ImageGenerator("2026-08-01")
wf = ImageGenerator._build_comfyui_img2img_workflow(PROMPT, 99999, REF, COMFYUI_IMG2IMG_DENOISE)
payload = json.dumps({"prompt": wf, "client_id": "test-img2img"}, ensure_ascii=False)
payload_b64 = base64.b64encode(payload.encode("utf-8")).decode("ascii")

# ノード存在確認
cmd_info = f"curl -sf http://127.0.0.1:{COMFYUI_API_PORT}/object_info/ReferenceLatent | python3 -c 'import sys,json; d=json.load(sys.stdin); print(\"exists\", \"ReferenceLatent\" in d)'"
r = subprocess.run(["ssh", "-o", "ConnectTimeout=15", "-o", "BatchMode=yes", HOST, cmd_info],
                   capture_output=True, text=True, timeout=30)
print("ReferenceLatent check:", (r.stdout or r.stderr).strip())

submit_cmd = (
    f"echo '{payload_b64}' | base64 -d | "
    f"curl -s -X POST http://127.0.0.1:{COMFYUI_API_PORT}/prompt "
    f"-H 'Content-Type: application/json' -d @-"
)
r2 = subprocess.run(["ssh", "-o", "ConnectTimeout=15", "-o", "BatchMode=yes", HOST, submit_cmd],
                    capture_output=True, text=True, timeout=60)
print("Submit stdout:", r2.stdout[:800])
print("Submit stderr:", r2.stderr[:400])
if r2.returncode != 0:
    sys.exit(1)
try:
    data = json.loads(r2.stdout)
    print("node_errors:", data.get("node_errors"))
    print("prompt_id:", data.get("prompt_id"))
except json.JSONDecodeError:
    print("Not JSON response")
    sys.exit(1)
