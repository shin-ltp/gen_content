"""
テキスト生成 LLM の統一クライアント。

TXT_GENERATION_PROVIDER に応じて Gemini / Xiaomi MiMo / 阿里云百炼（OpenAI 互換）を使用する。
画像生成は IMG_GENERATION_PROVIDER（generate_images.py）で別管理。
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Literal

from config import (
    TXT_GENERATION_PROVIDER,
    GEMINI_API_KEY,
    GEMINI_PRO_MODEL,
    GEMINI_FLASH_MODEL,
    XIAOMI_API_KEY,
    XIAOMI_API_URL,
    XIAOMI_PRO_MODEL,
    XIAOMI_FLASH_MODEL,
    ALIBABA_API_KEY,
    ALIBABA_API_URL,
    ALIBABA_PRO_MODEL,
    ALIBABA_FLASH_MODEL,
    GLM_API_KEY,
    GLM_API_URL,
    GLM_MODEL,
)

ModelTier = Literal["pro", "flash"]

# response_format=json_object 利用時、ルート配列を許可しない OpenAI 互換 API
_OPENAI_COMPATIBLE_JSON_PROVIDERS = frozenset({"xiaomi", "alibaba", "glm"})

_gemini_client: Any | None = None


def _resolve_provider(provider_override: str | None = None) -> str:
    provider = (provider_override or TXT_GENERATION_PROVIDER or "").strip().lower()
    return provider or "gemini"


def provider_label(provider_override: str | None = None) -> str:
    provider = _resolve_provider(provider_override)
    return {
        "xiaomi": "Xiaomi MiMo",
        "alibaba": "阿里云百炼",
        "glm": "GLM",
        "gemini": "Gemini",
    }.get(provider, provider)


def required_env_hint(provider_override: str | None = None) -> str:
    """未設定時のエラーメッセージ用。"""
    provider = _resolve_provider(provider_override)
    return {
        "xiaomi": "XIAOMI_API_KEY / XIAOMI_API_URL",
        "alibaba": "ALIBABA_API_KEY / ALIBABA_API_URL",
        "glm": "GLM_API_KEY / GLM_API_URL",
        "gemini": "GEMINI_API_KEY",
    }.get(provider, "テキスト生成 API 設定")


def is_moderation_rejection(response_text: str) -> bool:
    """API がコンテンツ審査で拒否したプレーンテキスト応答かどうか。"""
    lower = (response_text or "").strip().lower()
    return (
        "high risk" in lower
        or "rejected because" in lower
        or lower.startswith("the request was rejected")
    )


def is_configured(provider_override: str | None = None) -> bool:
    provider = _resolve_provider(provider_override)
    if provider == "xiaomi":
        return bool(XIAOMI_API_KEY and XIAOMI_API_URL)
    if provider == "alibaba":
        return bool(ALIBABA_API_KEY and ALIBABA_API_URL)
    if provider == "glm":
        return bool(GLM_API_KEY and GLM_API_URL)
    return bool(GEMINI_API_KEY)


def get_model_name(tier: ModelTier = "pro", provider_override: str | None = None) -> str:
    provider = _resolve_provider(provider_override)
    if provider == "xiaomi":
        return XIAOMI_PRO_MODEL if tier == "pro" else XIAOMI_FLASH_MODEL
    if provider == "alibaba":
        return ALIBABA_PRO_MODEL if tier == "pro" else ALIBABA_FLASH_MODEL
    if provider == "glm":
        return GLM_MODEL
    return GEMINI_PRO_MODEL if tier == "pro" else GEMINI_FLASH_MODEL


def _get_gemini_client():
    global _gemini_client
    if _gemini_client is None:
        from google import genai

        _gemini_client = genai.Client(api_key=GEMINI_API_KEY)
    return _gemini_client


def _extract_gemini_text(response: Any) -> str:
    if hasattr(response, "text") and response.text:
        return response.text.strip()
    if getattr(response, "candidates", None):
        parts = getattr(response.candidates[0].content, "parts", None) or []
        return "".join((getattr(p, "text", None) or "") for p in parts).strip()
    return ""


def _openai_compatible_chat(
    prompt: str,
    model: str,
    *,
    api_url: str,
    api_key: str,
    provider_name: str,
    json_mode: bool = False,
) -> str:
    url = f"{api_url.rstrip('/')}/chat/completions"
    body: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}

    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"{provider_name} API HTTP {e.code}: {err_body[:500]}"
        ) from e

    choices = payload.get("choices") or []
    if not choices:
        raise RuntimeError(
            f"{provider_name} API: empty choices in response: {str(payload)[:300]}"
        )
    message = choices[0].get("message") or {}
    content = message.get("content") or ""
    return content.strip()


def _chat(
    prompt: str,
    model: str,
    *,
    provider: str,
    json_mode: bool = False,
) -> str:
    """現在の TXT_GENERATION_PROVIDER で Chat Completions を呼ぶ。"""
    if provider == "xiaomi":
        return _openai_compatible_chat(
            prompt,
            model,
            api_url=XIAOMI_API_URL,
            api_key=XIAOMI_API_KEY,
            provider_name="Xiaomi",
            json_mode=json_mode,
        )
    if provider == "alibaba":
        return _openai_compatible_chat(
            prompt,
            model,
            api_url=ALIBABA_API_URL,
            api_key=ALIBABA_API_KEY,
            provider_name="Alibaba",
            json_mode=json_mode,
        )
    if provider == "glm":
        return _openai_compatible_chat(
            prompt,
            model,
            api_url=GLM_API_URL,
            api_key=GLM_API_KEY,
            provider_name="GLM",
            json_mode=json_mode,
        )
    raise RuntimeError(f"Unsupported provider for chat: {provider}")


def generate_text(
    prompt: str,
    tier: ModelTier = "pro",
    *,
    provider_override: str | None = None,
) -> str:
    """プレーンテキストを生成して返す。"""
    provider = _resolve_provider(provider_override)
    model = get_model_name(tier, provider_override=provider)
    if provider in _OPENAI_COMPATIBLE_JSON_PROVIDERS:
        return _chat(prompt, model, provider=provider, json_mode=False)

    client = _get_gemini_client()
    response = client.models.generate_content(
        model=model,
        contents=[prompt],
    )
    return _extract_gemini_text(response)


def _openai_json_schema_wrap(json_schema: dict | None) -> tuple[dict | None, str]:
    """
    OpenAI 互換 json_object モードはルート配列を許可しない。
    配列スキーマは {"articles": [...]} 形式に差し替える。
    """
    if json_schema is None:
        return None, ""
    if json_schema.get("type") != "array":
        return json_schema, ""
    wrapped = {
        "type": "object",
        "properties": {"articles": json_schema},
        "required": ["articles"],
    }
    note = (
        "トップレベルは JSON オブジェクトとし、記事の配列は必ずキー \"articles\" に入れてください。"
        "ルートを配列 [...] だけにしないでください。"
    )
    return wrapped, note


def generate_json(
    prompt: str,
    json_schema: dict | None = None,
    tier: ModelTier = "pro",
    *,
    provider_override: str | None = None,
) -> str:
    """
    JSON 形式のレスポンス本文（文字列）を返す。
    json_schema がある場合はプロンプトにスキーマ説明を付与する。
    """
    provider = _resolve_provider(provider_override)
    model = get_model_name(tier, provider_override=provider)
    full_prompt = prompt
    if json_schema is not None:
        schema_for_prompt = json_schema
        format_extra = ""
        if provider in _OPENAI_COMPATIBLE_JSON_PROVIDERS:
            schema_for_prompt, format_extra = _openai_json_schema_wrap(json_schema)
        schema_hint = json.dumps(schema_for_prompt, ensure_ascii=False, indent=2)
        extra_line = f"{format_extra}\n" if format_extra else ""
        full_prompt = (
            f"{prompt}\n\n"
            "【出力形式】有効な JSON のみを出力してください。"
            "マークダウンのコードブロックや説明文は不要です。\n"
            f"{extra_line}"
            f"次の JSON Schema に厳密に従ってください:\n{schema_hint}"
        )

    if provider in _OPENAI_COMPATIBLE_JSON_PROVIDERS:
        return _chat(full_prompt, model, provider=provider, json_mode=True)

    config: dict[str, Any] = {"response_mime_type": "application/json"}
    if json_schema is not None:
        config["response_json_schema"] = json_schema

    client = _get_gemini_client()
    response = client.models.generate_content(
        model=model,
        contents=[prompt],
        config=config,
    )
    return _extract_gemini_text(response)
