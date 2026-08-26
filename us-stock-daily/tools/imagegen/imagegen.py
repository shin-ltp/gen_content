"""us-stock-daily 文生图工具：qwen-image-3.0-pro(DashScope) 主、Mac ComfyUI FLUX2 备。

CLI 例：
    python imagegen.py "NVDA 数据中心 概念图" -o out/nvda.png
    python imagegen.py "概念图" --out out/nvda.png --provider comfyui
"""
import argparse
import base64
import io
import json
import random
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from PIL import Image as PILImage

from config import (
    COMFYUI_API_PORT,
    COMFYUI_CURL_MAX_TIME,
    COMFYUI_DIR,
    COMFYUI_GENERATION_TIMEOUT,
    COMFYUI_IMAGE_HEIGHT,
    COMFYUI_IMAGE_WIDTH,
    COMFYUI_OUTPUT_DIR,
    COMFYUI_REMOTE_HOST,
    COMFYUI_STEPS,
    COMFYUI_VAE_NAME,
    IMG_FALLBACK,
    IMG_GENERATION_PROVIDER,
    OUTPUT_HEIGHT,
    OUTPUT_WIDTH,
    QWEN_IMAGE_API_KEY,
    QWEN_IMAGE_API_URL,
    QWEN_IMAGE_GENERATION_TIMEOUT,
    QWEN_IMAGE_MODEL,
    QWEN_IMAGE_SIZE,
    QWEN_IMAGE_WATERMARK,
)
import ssh_base



def _qwen_generation_url() -> str:
    base = QWEN_IMAGE_API_URL.rstrip("/")
    if "/services/aigc/" in base:
        return base
    return f"{base}/services/aigc/multimodal-generation/generation"


def _qwen_tasks_url(task_id: str) -> str:
    base = QWEN_IMAGE_API_URL.rstrip("/")
    if "/services/aigc/" in base:
        base = base.split("/services/aigc/")[0]
    return f"{base}/tasks/{task_id}"


def _is_moderation_error(text: str) -> bool:
    t = (text or "").lower()
    return "datainspectionfailed" in t or "green net check failed" in t


def _extract_image_url(data: dict) -> str | None:
    output = data.get("output") or {}
    if output.get("task_status") == "SUCCEEDED":
        for key in ("results", "result"):
            block = output.get(key)
            if isinstance(block, dict):
                url = block.get("url") or block.get("image")
                if url:
                    return url
            if isinstance(block, list):
                for item in block:
                    if isinstance(item, dict):
                        url = item.get("url") or item.get("image")
                        if url:
                            return url
    for choice in output.get("choices") or []:
        message = choice.get("message") or {}
        for item in message.get("content") or []:
            if isinstance(item, dict) and item.get("image"):
                return item["image"]
    return None


def _download(url: str) -> bytes:
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.read()


def _qwen_post(body: dict) -> dict:
    url = _qwen_generation_url()
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {QWEN_IMAGE_API_KEY}",
    }
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=QWEN_IMAGE_GENERATION_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _qwen_get_task(task_id: str) -> dict:
    url = _qwen_tasks_url(task_id)
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {QWEN_IMAGE_API_KEY}"},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _poll_qwen(task_id: str) -> dict | None:
    deadline = time.time() + QWEN_IMAGE_GENERATION_TIMEOUT
    interval = 3.0
    while time.time() < deadline:
        try:
            data = _qwen_get_task(task_id)
        except urllib.error.HTTPError as e:
            print(f"  [qwen] 任务查询失败 HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:300]}")
        except Exception as e:
            print(f"  [qwen] 任务查询异常: {e}")
        else:
            output = data.get("output") or {}
            status = output.get("task_status")
            if status == "SUCCEEDED":
                return data
            if status in ("FAILED", "CANCELED", "UNKNOWN"):
                print(f"  [qwen] 任务失败: status={status} {data.get('message', '')}")
                return None
        time.sleep(interval)
        interval = min(interval * 1.3, 10.0)
    print(f"  [qwen] 任务超时 (task_id={task_id})")
    return None


def _save_pil(
    image: PILImage.Image,
    output_path: Path,
    width: int = OUTPUT_WIDTH,
    height: int = OUTPUT_HEIGHT,
) -> None:
    if image.mode != "RGB":
        image = image.convert("RGB")
    image.resize((width, height), PILImage.Resampling.LANCZOS).save(
        str(output_path)
    )


def generate_with_qwen(
    prompt: str,
    output_path: Path,
    width: int = OUTPUT_WIDTH,
    height: int = OUTPUT_HEIGHT,
) -> bool:
    """DashScope qwen-image-3.0-pro 异步文生图。"""
    if not QWEN_IMAGE_API_KEY:
        print("[qwen] 未配置 QWEN_IMAGE_API_KEY，跳过")
        return False
    print(
        f"[qwen] 生成中 {QWEN_IMAGE_MODEL} ({QWEN_IMAGE_SIZE}) "
        f"→ {output_path.name}"
    )
    body = {
        "model": QWEN_IMAGE_MODEL,
        "input": {"messages": [{"role": "user", "content": [{"text": prompt}]}]},
        "parameters": {
            "size": f"{width}*{height}",
            "n": 1,
            "watermark": QWEN_IMAGE_WATERMARK,
        },
    }
    try:
        data = _qwen_post(body)
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")
        if _is_moderation_error(err):
            print(f"  [qwen] 内容审核拒绝: {err[:300]}")
        else:
            print(f"  [qwen] API HTTP {e.code}: {err[:500]}")
        return False
    except Exception as e:
        print(f"  [qwen] API 调用异常: {e}")
        return False

    task_id = (data.get("output") or {}).get("task_id")
    if not task_id:
        image_url = _extract_image_url(data)
        if not image_url:
            print(f"  [qwen] 响应缺少 task_id / image: {str(data)[:300]}")
            return False
    else:
        result = _poll_qwen(task_id)
        if not result:
            return False
        image_url = _extract_image_url(result)
        if not image_url:
            print(f"  [qwen] 任务成功但无图片 URL: {str(result)[:300]}")
            return False

    try:
        raw = _download(image_url)
        _save_pil(PILImage.open(io.BytesIO(raw)), output_path, width, height)
    except Exception as e:
        print(f"  [qwen] 图片下载/保存失败: {e}")
        return False
    print(f"  [qwen] 完成: {output_path}")
    return True


def _comfyui_api_curl(path: str) -> str:
    return (
        f"curl -sf --max-time {COMFYUI_CURL_MAX_TIME} "
        f"http://127.0.0.1:{COMFYUI_API_PORT}{path}"
    )


def _build_comfyui_workflow(prompt: str, seed: int) -> dict:
    """FLUX2 (Mac ComfyUI) の t2i ワークフロー。モデル・VAE は環境に合わせて調整可能。"""
    checkpoint = COMFYUI_DIR + "/models/checkpoints/flux2.safetensors"
    g = COMFYUI_IMAGE_WIDTH
    h = COMFYUI_IMAGE_HEIGHT
    bn = 8
    width = max(bn, g - g % bn)
    height = max(bn, h - h % bn)
    return {
        "3": {
            "class_type": "KSampler",
            "inputs": {
                "cfg": 3.5,
                "denoise": 1.0,
                "latent_image": ["5", 0],
                "model": ["4", 0],
                "negative": ["7", 0],
                "positive": ["6", 0],
                "sampler_name": "euler",
                "scheduler": "simple",
                "seed": seed,
                "steps": COMFYUI_STEPS,
            },
        },
        "4": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": checkpoint},
        },
        "5": {
            "class_type": "EmptyLatentImage",
            "inputs": {
                "batch_size": 1,
                "height": height,
                "width": width,
            },
        },
        "6": {
            "class_type": "CLIPTextEncode",
            "inputs": {"clip": ["4", 1], "text": prompt},
        },
        "7": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "clip": ["4", 1],
                "text": "",
            },
        },
        "8": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["3", 0], "vae": ["4", 2]},
        },
        "9": {
            "class_type": "SaveImage",
            "inputs": {
                "filename_prefix": "usd",
                "images": ["8", 0],
            },
        },
    }


def generate_with_comfyui(prompt: str, output_path: Path) -> bool:
    """Mac ComfyUI FLUX2 t2i（SSH + curl + SCP）。Mac とな別ネットワークの場合は失敗する。"""
    if not COMFYUI_REMOTE_HOST:
        print("[comfyui] 未配置 COMFYUI_REMOTE_HOST，跳过")
        return False
    print(
        f"[comfyui] Mac FLUX2 生成中 ({COMFYUI_REMOTE_HOST}, "
        f"{COMFYUI_IMAGE_WIDTH}x{COMFYUI_IMAGE_HEIGHT}, steps={COMFYUI_STEPS})"
    )
    try:
        ssh = ssh_base.PlainSSHRemote(COMFYUI_REMOTE_HOST)
        seed = random.randint(0, 2**32)
        workflow = _build_comfyui_workflow(prompt, seed)
        payload = json.dumps(
            {"prompt": workflow, "client_id": f"usd-{seed}"},
            ensure_ascii=False,
        )
        payload_b64 = base64.b64encode(payload.encode("utf-8")).decode("ascii")
        submit_cmd = (
            f"echo '{payload_b64}' | base64 -d | "
            f"curl -s -X POST http://127.0.0.1:{COMFYUI_API_PORT}/prompt "
            f"-H 'Content-Type: application/json' -d @-"
        )
        resp_text = ssh.ssh(submit_cmd, label="ComfyUI submit", timeout=120)
        resp = json.loads(resp_text)
    except Exception as e:
        print(f"  [comfyui] 提交失败: {e}")
        return False

    if resp.get("node_errors"):
        print(f"  [comfyui] 节点错误: {resp['node_errors']}")
        return False

    prompt_id = resp.get("prompt_id")
    if not prompt_id:
        print(f"  [comfyui] 无 prompt_id: {str(resp)[:300]}")
        return False

    poll_interval = 5
    max_attempts = max(1, COMFYUI_GENERATION_TIMEOUT // poll_interval)
    for attempt in range(max_attempts):
        time.sleep(poll_interval)
        try:
            hist_text = ssh.ssh(
                _comfyui_api_curl(f"/history/{prompt_id}"),
                label="ComfyUI poll",
                timeout=COMFYUI_CURL_MAX_TIME + 20,
            )
        except RuntimeError as e:
            if (attempt + 1) % 6 == 0:
                print(f"  [comfyui] 轮询警告 ({attempt + 1}/{max_attempts}): {e}")
            continue
        if not hist_text:
            continue
        try:
            hist = json.loads(hist_text)
        except json.JSONDecodeError:
            continue

        entry = hist.get(prompt_id)
        if not entry:
            continue
        status = entry.get("status", {})
        if status.get("status_str") == "error":
            print(f"  [comfyui] 执行错误: {str(status.get('messages', []))[:300]}")
            return False
        if not status.get("completed"):
            continue

        filename = None
        subfolder = ""
        for _nid, nout in (entry.get("outputs") or {}).items():
            for img in nout.get("images", []):
                filename = img["filename"]
                subfolder = img.get("subfolder", "") or ""
                break
            if filename:
                break
        if not filename:
            print("  [comfyui] 输出图片缺失")
            return False
        remote_path = (
            f"{COMFYUI_OUTPUT_DIR}/{subfolder}/{filename}"
            if subfolder
            else f"{COMFYUI_OUTPUT_DIR}/{filename}"
        )
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            ssh.scp_from_remote(remote_path, str(tmp_path))
            _save_pil(PILImage.open(tmp_path), output_path)
            print(f"  [comfyui] 完成: {output_path}")
            return True
        except Exception as e:
            print(f"  [comfyui] 下载失败: {e}")
            return False
        finally:
            tmp_path.unlink(missing_ok=True)

    print(f"  [comfyui] 生成超时 ({COMFYUI_GENERATION_TIMEOUT}s)")
    return False


def generate_image(
    prompt: str,
    output_path: Path,
    provider: str | None = None,
    width: int = OUTPUT_WIDTH,
    height: int = OUTPUT_HEIGHT,
) -> bool:
    """统一入口：qwen 默认，失败按 IMG_GENERATION_FALLBACK 回退到 comfyui。"""
    providers = [provider or IMG_GENERATION_PROVIDER]
    if IMG_FALLBACK:
        for p in ("qwen", "comfyui"):
            if p not in providers:
                providers.append(p)
    for p in providers:
        print(f"[imagegen] provider={p}")
        if p == "qwen":
            ok = generate_with_qwen(prompt, output_path, width, height)
        elif p == "comfyui":
            ok = generate_with_comfyui(prompt, output_path)
        else:
            print(f"[imagegen] 未知 provider: {p}")
            return False
        if ok:
            return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="us-stock-daily 文生图")
    parser.add_argument("prompt", help="文生图 prompt")
    parser.add_argument("-o", "--out", required=True, help="输出图片路径 (png)")
    parser.add_argument(
        "--provider",
        choices=("qwen", "comfyui"),
        default=None,
        help="强制指定 provider（默认读 env）",
    )
    parser.add_argument("--width", type=int, default=OUTPUT_WIDTH, help="输出宽度")
    parser.add_argument("--height", type=int, default=OUTPUT_HEIGHT, help="输出高度")
    args = parser.parse_args()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if not generate_image(args.prompt, out, args.provider, args.width, args.height):
        print("[imagegen] 生成失败")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
