"""End-to-end ComfyUI img2img poll test (article 060, minimal)."""
import io
import sys
import time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)

from generate_images import ImageGenerator
from config import COMFYUI_GENERATION_TIMEOUT

issue = "2026-08-01"
g = ImageGenerator(issue)
g._ensure_comfyui_api_ready()

ref = Path(r"c:\my_project\crypto-research-jp\contents\audiobook\output\TheEconomist\2026-08-01\articles\images\060_ref.jpg")
prompt_path = Path(r"c:\my_project\crypto-research-jp\contents\audiobook\output\TheEconomist\2026-08-01\articles\images\060_prompt.txt")
prompt = prompt_path.read_text(encoding="utf-8").strip()
out = Path(r"c:\my_project\crypto-research-jp\contents\audiobook\output\TheEconomist\2026-08-01\articles\images\060_img2img_test.png")

print(f"ref={ref.exists()} prompt_len={len(prompt)} timeout={COMFYUI_GENERATION_TIMEOUT}s", flush=True)
t0 = time.time()
ok = g._generate_image_comfyui(prompt, out, ref_image=ref)
elapsed = time.time() - t0
print(f"RESULT={'OK' if ok else 'FAIL'} elapsed={elapsed:.0f}s out_exists={out.exists()}", flush=True)
if out.exists():
    print(f"  size={out.stat().st_size:,} bytes", flush=True)
sys.exit(0 if ok else 1)
