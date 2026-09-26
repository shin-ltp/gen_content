"""Unified LLM API client for content generation (topic scoring, writing, QA).

Replaces per-phase sub-agent invocations with direct API calls. Code owns
orchestration; this module only handles the LLM HTTP round-trip.

Supported providers:
  gemini        Google Gemini API (default)
  openai_compat Any OpenAI-compatible chat completions endpoint
                (GLM, DeepSeek, Alibaba Bailian, etc.)

Environment variables (.env in us-stock-daily/ or process env):
  TEXT_LLM_PROVIDER          gemini | openai_compat  (default: gemini)
  TEXT_LLM_MAX_RETRIES       max attempts per call (default: 3)
  TEXT_LLM_RPM               max requests per minute (default: 10)

  Gemini:
    GEMINI_API_KEY
    GEMINI_PRO_MODEL           (default: gemini-2.5-pro)
    GEMINI_FLASH_MODEL         (default: gemini-2.5-flash)

  OpenAI-compatible:
    OPENAI_COMPAT_API_URL      e.g. https://open.bigmodel.cn/api/paas/v4
    OPENAI_COMPAT_API_KEY
    OPENAI_COMPAT_PRO_MODEL    e.g. glm-4-plus
    OPENAI_COMPAT_FLASH_MODEL  e.g. glm-4-flash

Vision (image-understanding) calls reuse the same provider dispatch:
  TEXT_LLM_VISION_MODEL        model that accepts image_url parts
                               (default: same as the pro-tier model)
"""
from __future__ import annotations

import base64
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

_US_ROOT = Path(__file__).resolve().parents[2]
_ENV_LOADED = False


def _load_env() -> None:
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    _ENV_LOADED = True
    for env_path in (_US_ROOT / ".env", Path(".env")):
        if not env_path.is_file():
            continue
        for line in env_path.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
        break


def _env(key: str, default: str = "") -> str:
    _load_env()
    return os.environ.get(key, default).strip()


def _int_env(key: str, default: int) -> int:
    try:
        return int(_env(key, str(default)))
    except ValueError:
        return default


# ---------------------------------------------------------------------------
# Provider configuration
# ---------------------------------------------------------------------------

def _provider() -> str:
    explicit = _env("TEXT_LLM_PROVIDER")
    if explicit:
        return explicit.lower()
    # Auto-select a configured provider so OPENAI_COMPAT_* alone is enough.
    if _env("OPENAI_COMPAT_API_URL") and _env("OPENAI_COMPAT_API_KEY"):
        return "openai_compat"
    return "gemini"


def _model(tier: str) -> str:
    tier = tier.lower()
    if _provider() == "openai_compat":
        if tier == "flash":
            return _env("OPENAI_COMPAT_FLASH_MODEL", "glm-4-flash")
        return _env("OPENAI_COMPAT_PRO_MODEL", "glm-4-plus")
    if tier == "flash":
        return _env("GEMINI_FLASH_MODEL", "gemini-2.5-flash")
    return _env("GEMINI_PRO_MODEL", "gemini-2.5-pro")


def _vision_model() -> str:
    """Model used for image-understanding calls (defaults to the pro model)."""
    return _env("TEXT_LLM_VISION_MODEL") or _model("pro")


def is_configured() -> bool:
    if _provider() == "openai_compat":
        return bool(_env("OPENAI_COMPAT_API_URL") and _env("OPENAI_COMPAT_API_KEY"))
    return bool(_env("GEMINI_API_KEY"))


def reasoning_effort() -> str:
    """Thinking effort for OpenAI-compatible endpoints.

    xhigh is the Aliyun/Qwen-compatible representation of "extra high".
    Set TEXT_LLM_REASONING_EFFORT=auto (or empty) to omit the parameter.
    """
    return _env("TEXT_LLM_REASONING_EFFORT", "xhigh")


def provider_label() -> str:
    p = _provider()
    if p == "openai_compat":
        return f"openai_compat:{_model('pro')}"
    return f"gemini:{_model('pro')}"


# ---------------------------------------------------------------------------
# Rate limiting (simple sliding window)
# ---------------------------------------------------------------------------

_call_timestamps: list[float] = []
_RPM = 0  # lazily read from env


def _rate_limit() -> None:
    global _RPM
    if _RPM == 0:
        _RPM = max(1, _int_env("TEXT_LLM_RPM", 10))
    now = time.monotonic()
    window = 60.0
    _call_timestamps[:] = [t for t in _call_timestamps if now - t < window]
    if len(_call_timestamps) >= _RPM:
        wait = window - (now - _call_timestamps[0]) + 0.5
        print(f"[text_llm] rate limit: waiting {wait:.1f}s", flush=True)
        time.sleep(wait)
    _call_timestamps.append(time.monotonic())


# ---------------------------------------------------------------------------
# HTTP callers
# ---------------------------------------------------------------------------

def _call_openai_compat(
    prompt: str,
    model: str,
    *,
    json_mode: bool = False,
    max_tokens: int | None = None,
    images: list[str] | None = None,
) -> str:
    url = _env("OPENAI_COMPAT_API_URL").rstrip("/") + "/chat/completions"
    content: Any = prompt
    if images:
        # OpenAI-compatible multimodal shape: text + base64 data-URI images.
        content = [{"type": "text", "text": prompt}]
        for uri in images:
            content.append(
                {"type": "image_url", "image_url": {"url": uri}},
            )
    body: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": content}],
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    if max_tokens:
        body["max_tokens"] = max_tokens
    effort = reasoning_effort()
    if effort and effort.lower() != "auto":
        body["reasoning_effort"] = effort.lower()

    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {_env('OPENAI_COMPAT_API_KEY')}",
    }, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"openai_compat HTTP {e.code}: {err_body}") from e
    choices = payload.get("choices") or []
    if not choices:
        raise RuntimeError(f"openai_compat: empty choices: {str(payload)[:300]}")
    content = (choices[0].get("message") or {}).get("content") or ""
    return content.strip()


def _call_gemini(prompt: str, model: str, *, json_mode: bool = False) -> str:
    try:
        from google import genai
    except ImportError:
        raise RuntimeError("google-genai not installed; pip install google-genai")
    client = genai.Client(api_key=_env("GEMINI_API_KEY"))
    config: dict[str, Any] = {}
    if json_mode:
        config["response_mime_type"] = "application/json"
    response = client.models.generate_content(
        model=model, contents=[prompt],
        config=config or None,
    )
    if hasattr(response, "text") and response.text:
        return response.text.strip()
    if getattr(response, "candidates", None):
        parts = getattr(response.candidates[0].content, "parts", None) or []
        return "".join(getattr(p, "text", None) or "" for p in parts).strip()
    return ""


def _call_raw(prompt: str, tier: str, *, json_mode: bool = False) -> str:
    model = _model(tier)
    if _provider() == "openai_compat":
        return _call_openai_compat(prompt, model, json_mode=json_mode)
    return _call_gemini(prompt, model, json_mode=json_mode)


def prepare_image_bytes(path: Path, max_edge: int = 512) -> bytes:
    """Downscale an image to a review-friendly JPEG payload (keeps tokens low)."""
    from PIL import Image
    import io

    with Image.open(path) as im:
        im = im.convert("RGB")
        im.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=82)
        return buf.getvalue()


def _call_gemini_with_images(prompt: str, model: str, images: list[bytes],
                             *, json_mode: bool = False) -> str:
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        raise RuntimeError("google-genai not installed; pip install google-genai")
    client = genai.Client(api_key=_env("GEMINI_API_KEY"))
    parts: list[Any] = [types.Part.from_text(text=prompt)]
    for blob in images:
        parts.append(types.Part.from_bytes(data=blob, mime_type="image/jpeg"))
    config: dict[str, Any] = {}
    if json_mode:
        config["response_mime_type"] = "application/json"
    response = client.models.generate_content(
        model=model,
        contents=[types.Content(role="user", parts=parts)],
        config=config or None,
    )
    if hasattr(response, "text") and response.text:
        return response.text.strip()
    return ""


def generate_json_with_images(
    prompt: str,
    images: list[Path],
    tier: str = "pro",
    *,
    schema_hint: str | None = None,
    max_retries: int | None = None,
    max_edge: int = 512,
) -> Any:
    """Multimodal JSON call: one prompt + local images, parsed response.

    `tier` is kept for signature parity but TEXT_LLM_VISION_MODEL wins.
    """
    if not images:
        return generate_json(prompt, tier, schema_hint=schema_hint,
                             max_retries=max_retries)
    full_prompt = prompt
    if schema_hint:
        full_prompt += (
            "\n\n【出力形式】有効な JSON のみを出力してください。"
            "マークダウンのコードブロックや説明文は不要です。\n"
            f"次の JSON Schema に厳密に従ってください:\n{schema_hint}"
        )
    blobs = [prepare_image_bytes(Path(p), max_edge=max_edge) for p in images]
    if max_retries is None:
        max_retries = _int_env("TEXT_LLM_MAX_RETRIES", 3)
    model = _vision_model()
    last_err: Exception | None = None
    for attempt in range(1, max_retries + 1):
        _rate_limit()
        try:
            if _provider() == "openai_compat":
                uris = [
                    "data:image/jpeg;base64," + base64.b64encode(b).decode("ascii")
                    for b in blobs
                ]
                raw = _call_openai_compat(
                    full_prompt, model, json_mode=True, images=uris,
                )
            else:
                raw = _call_gemini_with_images(
                    full_prompt, model, blobs, json_mode=True,
                )
            if not raw:
                raise RuntimeError("empty vision response")
            return _parse_json_loose(raw)
        except Exception as e:  # noqa: BLE001 - retry loop owns degradation
            last_err = e
        if attempt < max_retries:
            wait = min(60, 2 ** attempt * 5)
            print(f"[text_llm] vision attempt {attempt}/{max_retries} failed: "
                  f"{str(last_err)[:200]}; retry in {wait}s", flush=True)
            time.sleep(wait)
    raise RuntimeError(
        f"generate_json_with_images failed after {max_retries} attempts: {last_err}"
    )


# ---------------------------------------------------------------------------
# Public API with retry
# ---------------------------------------------------------------------------

def generate_text(
    prompt: str,
    tier: str = "pro",
    *,
    max_retries: int | None = None,
) -> str:
    """Generate plain text. Retries with exponential backoff on failure."""
    if max_retries is None:
        max_retries = _int_env("TEXT_LLM_MAX_RETRIES", 3)
    last_err: Exception | None = None
    for attempt in range(1, max_retries + 1):
        _rate_limit()
        try:
            result = _call_raw(prompt, tier)
            if result:
                return result
            last_err = RuntimeError("empty response")
        except Exception as e:
            last_err = e
        if attempt < max_retries:
            wait = min(60, 2 ** attempt * 5)
            print(f"[text_llm] attempt {attempt}/{max_retries} failed: {last_err}; retry in {wait}s", flush=True)
            time.sleep(wait)
    raise RuntimeError(f"generate_text failed after {max_retries} attempts: {last_err}")


def generate_json(
    prompt: str,
    tier: str = "pro",
    *,
    schema_hint: str | None = None,
    max_retries: int | None = None,
) -> Any:
    """Generate JSON and return the parsed object. Retries on parse failure."""
    full_prompt = prompt
    if schema_hint:
        full_prompt += (
            "\n\n【出力形式】有効な JSON のみを出力してください。"
            "マークダウンのコードブロックや説明文は不要です。\n"
            f"次の JSON Schema に厳密に従ってください:\n{schema_hint}"
        )
    if max_retries is None:
        max_retries = _int_env("TEXT_LLM_MAX_RETRIES", 3)
    last_err: Exception | None = None
    for attempt in range(1, max_retries + 1):
        _rate_limit()
        try:
            raw = _call_raw(full_prompt, tier, json_mode=True)
            return _parse_json_loose(raw)
        except (json.JSONDecodeError, ValueError) as e:
            last_err = e
            # Append parse error to prompt for next attempt
            full_prompt = prompt + (
                f"\n\n【前回のエラー】JSON パースに失敗しました: {e}\n"
                "今度は確実に有効な JSON のみを出力してください。"
            )
            if schema_hint:
                full_prompt += f"\n次の JSON Schema に厳密に従ってください:\n{schema_hint}"
        except Exception as e:
            last_err = e
        if attempt < max_retries:
            wait = min(60, 2 ** attempt * 5)
            print(f"[text_llm] JSON attempt {attempt}/{max_retries} failed: {last_err}; retry in {wait}s", flush=True)
            time.sleep(wait)
    raise RuntimeError(f"generate_json failed after {max_retries} attempts: {last_err}")


def _parse_json_loose(raw: str) -> Any:
    """Parse JSON, tolerating markdown code fences around the payload."""
    text = raw.strip()
    # Strip ```json ... ``` wrapper if present
    m = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL)
    if m:
        text = m.group(1).strip()
    return json.loads(text)


# ---------------------------------------------------------------------------
# Lightweight JSON schema validation (recursive, covers common patterns)
# ---------------------------------------------------------------------------

def validate_schema(data: Any, schema: dict, path: str = "$") -> list[str]:
    """Return a list of validation errors (empty = valid)."""
    errors: list[str] = []
    expected_type = schema.get("type")
    type_map = {"object": dict, "array": list, "string": str, "number": (int, float),
                "integer": int, "boolean": bool, "null": type(None)}
    if expected_type and expected_type in type_map:
        py_type = type_map[expected_type]
        if expected_type == "integer" and isinstance(data, bool):
            errors.append(f"{path}: expected integer, got boolean")
            return errors
        if not isinstance(data, py_type):
            errors.append(f"{path}: expected {expected_type}, got {type(data).__name__}")
            return errors
    if expected_type == "object" and isinstance(data, dict):
        for key in schema.get("required", []):
            if key not in data:
                errors.append(f"{path}: missing required key '{key}'")
        for key, sub in schema.get("properties", {}).items():
            if key in data:
                errors.extend(validate_schema(data[key], sub, f"{path}.{key}"))
    elif expected_type == "array" and isinstance(data, list):
        items = schema.get("items")
        if items:
            for i, item in enumerate(data):
                errors.extend(validate_schema(item, items, f"{path}[{i}]"))
    if "enum" in schema and data not in schema["enum"]:
        errors.append(f"{path}: value {data!r} not in enum {schema['enum']}")
    if "minimum" in schema and isinstance(data, (int, float)) and data < schema["minimum"]:
        errors.append(f"{path}: {data} < minimum {schema['minimum']}")
    if "maximum" in schema and isinstance(data, (int, float)) and data > schema["maximum"]:
        errors.append(f"{path}: {data} > maximum {schema['maximum']}")
    return errors
