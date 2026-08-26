"""文生图通用配置モジュール qwen-image-3.0-pro(Mac FLUX2 fallback)"""
import os
from pathlib import Path

from dotenv import load_dotenv

_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parents[1]
load_dotenv(_PROJECT_ROOT / ".env")
load_dotenv()


def _int_env(name: str, default: int, lo: int) -> int:
    try:
        return max(lo, int(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return default


def _float_env(name: str, default: float, lo: float) -> float:
    try:
        return max(lo, float(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return default


IMG_GENERATION_PROVIDER = os.getenv("IMG_GENERATION_PROVIDER", "qwen").strip().lower()
if IMG_GENERATION_PROVIDER not in ("qwen", "comfyui"):
    IMG_GENERATION_PROVIDER = "qwen"

IMG_FALLBACK = os.getenv("IMG_GENERATION_FALLBACK", "1").strip().lower() not in (
    "0",
    "false",
    "no",
)

QWEN_IMAGE_API_KEY = os.getenv("QWEN_IMAGE_API_KEY", "").strip()
QWEN_IMAGE_API_URL = os.getenv(
    "QWEN_IMAGE_API_URL", "https://dashscope-intl.aliyuncs.com/api/v1"
).strip().rstrip("/")
QWEN_IMAGE_MODEL = os.getenv("QWEN_IMAGE_MODEL", "qwen-image-3.0-pro").strip()
QWEN_IMAGE_SIZE = os.getenv("QWEN_IMAGE_SIZE", "768*1024").strip()
try:
    QWEN_IMAGE_GENERATION_TIMEOUT = max(
        60, int(os.getenv("QWEN_IMAGE_GENERATION_TIMEOUT", "300"))
    )
except ValueError:
    QWEN_IMAGE_GENERATION_TIMEOUT = 300
QWEN_IMAGE_WATERMARK = os.getenv("QWEN_IMAGE_WATERMARK", "0").strip().lower() in (
    "1",
    "true",
    "yes",
)

COMFYUI_REMOTE_HOST = os.getenv("COMFYUI_REMOTE_HOST", "cho@rw-mac-1").strip()
COMFYUI_DIR = os.getenv("COMFYUI_DIR", "/Users/cho/comfyui/ComfyUI").strip()
COMFYUI_VENV = os.getenv("COMFYUI_VENV", "/Users/cho/comfyui/.venv").strip()
COMFYUI_OUTPUT_DIR = os.getenv(
    "COMFYUI_OUTPUT_DIR", "/Users/cho/comfyui/ComfyUI/output"
).strip()
COMFYUI_VAE_NAME = os.getenv("COMFYUI_VAE_NAME", "ae.safetensors").strip()
COMFYUI_API_PORT = _int_env("COMFYUI_API_PORT", 8188, 1)
COMFYUI_IMAGE_WIDTH = _int_env("COMFYUI_IMAGE_WIDTH", 768, 256)
COMFYUI_IMAGE_HEIGHT = _int_env("COMFYUI_IMAGE_HEIGHT", 1024, 256)
COMFYUI_STEPS = _int_env("COMFYUI_STEPS", 4, 1)
COMFYUI_GENERATION_TIMEOUT = _int_env("COMFYUI_GENERATION_TIMEOUT", 600, 120)
COMFYUI_CURL_MAX_TIME = _int_env("COMFYUI_CURL_MAX_TIME", 15, 5)
COMFYUI_SSH_CONNECT_TIMEOUT = _int_env("COMFYUI_SSH_CONNECT_TIMEOUT", 30, 5)
COMFYUI_SSH_RETRY_COUNT = _int_env("COMFYUI_SSH_RETRY_COUNT", 3, 1)
COMFYUI_SSH_RETRY_WAIT_SEC = _int_env("COMFYUI_SSH_RETRY_WAIT_SEC", 10, 1)
COMFYUI_IMG2IMG_DENOISE = _float_env("COMFYUI_IMG2IMG_DENOISE", 0.55, 0.0)

OUTPUT_WIDTH = 768
OUTPUT_HEIGHT = 1024
