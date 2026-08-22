import subprocess, json
HOST = "cho@rw-mac-1"
for node in ["ReferenceLatent", "ImageScaleToTotalPixels", "VAEEncode"]:
    cmd = f"curl -sf http://127.0.0.1:8188/object_info/{node}"
    r = subprocess.run(["ssh", "-o", "BatchMode=yes", HOST, cmd], capture_output=True, text=True, timeout=30)
    if r.stdout:
        d = json.loads(r.stdout).get(node, {})
        print(node, "inputs:", list(d.get("input", {}).keys()))
        print(" required:", d.get("input", {}).get("required", d.get("input_order", {})))
    else:
        print(node, "MISSING")
