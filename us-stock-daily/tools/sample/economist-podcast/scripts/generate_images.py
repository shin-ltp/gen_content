"""
挿絵生成モジュール
各エピソード内の記事に対して挿絵を生成する。
カバーストーリーの場合は雑誌の表紙画像をそのまま使用し、
それ以外は IMG_GENERATION_PROVIDER に応じて API で縦型挿絵を生成する。

- gemini: Gemini 2.5 Flash Image（GEMINI_API_KEY）
- alibaba: 百炼 DashScope 万相/千问文生图（ALIBABA_API_KEY 等）
- comfyui: ComfyUI 自托管（Mac MPS / FLUX.2-klein GGUF, SSH 経由）
"""
import base64
import io
import json
import random
import re
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from PIL import Image as PILImage

from config import (
    ALIBABA_API_KEY,
    ALIBABA_API_URL,
    ALIBABA_IMAGE_MODEL,
    COMFYUI_API_PORT,
    COMFYUI_CURL_MAX_TIME,
    COMFYUI_DIR,
    COMFYUI_GENERATION_TIMEOUT,
    COMFYUI_VENV,
    COMFYUI_IMAGE_HEIGHT,
    COMFYUI_IMAGE_WIDTH,
    COMFYUI_OUTPUT_DIR,
    COMFYUI_REMOTE_HOST,
    COMFYUI_STEPS,
    COMFYUI_VAE_NAME,
    GEMINI_API_KEY,
    GEMINI_FLASH_MODEL,
    GEMINI_IMAGE_MODEL,
    IMG_GENERATION_PROVIDER,
    get_issue_dir,
)
import text_llm
from state_manager import StateManager

# 出力画像サイズ（幅 x 高さ）
OUTPUT_WIDTH = 768
OUTPUT_HEIGHT = 1024

# 阿里云出力サイズ（3:4 縦、後で 768x1024 にリサイズ）
ALIBABA_IMAGE_SIZE = f"{OUTPUT_WIDTH}*{OUTPUT_HEIGHT}"

_ALIBABA_NEGATIVE_PROMPT = (
    "低分辨率，低画质，肢体畸形，手指畸形，蜡像感，"
    "人脸无细节，过度光滑，画面具有AI感。构图混乱。"
    "文字，标题，字幕，水印，商标，字母，数字，汉字，日文，假名，韩文，任何语言文字。"
)

# API 送信前に除去・置換する語句（雑誌表紙レイアウト＝見出し文字を誘発しやすい）
_PROMPT_LAYOUT_PHRASES = (
    (r"magazine\s+cover\s+style", "editorial illustration"),
    (r"magazine\s+cover", "editorial illustration"),
    (r"book\s+cover", "editorial scene"),
    (r"poster\s+layout", "cinematic scene"),
)

_NO_TEXT_SUFFIX = (
    " CRITICAL: Purely visual scene only — ZERO written language in the image. "
    "No headlines, captions, labels, logos, watermarks, letters, numbers, "
    "Japanese, Chinese, Korean, or any characters anywhere."
)

# rewrite_content.py と同じ image_prompt ルール（再生成時は記事改写せず prompt のみ更新）
_IMAGE_PROMPT_LLM_RULES = """\
- **英語のみ・日本語禁止**: 記事の主題を**視覚的な比喩・シーン**として描写する。タイトル・見出し・キーワードの列挙は禁止。
- 【スタイルの選び方】: 以下の5種類から**記事のテーマ・トーンに最も合うものを1つだけ**自律的に選び、プロンプト冒頭で英語に訳して明示すること:
  - モノクローム → monochrome
  - 水彩イラスト → watercolor illustration
  - ドキュメンタリー写真風 → documentary photography style
  - シネマティック写真 → cinematic photography
  - 手描きスケッチ風 → hand-drawn sketch style
- 【主題の視覚化】: 記事の核心を**1つの印象的なシーン**に凝縮する。構図は**シンプル**に、余計な要素を詰め込まない。**インパクト**と**高級感**（refined, premium, striking visual）を意識する。
- 【国・地域が主題の場合】: 該当国・地域を象徴する要素を**積極的に**用いる（例：象徴的なランドマーク、代表的な動物、国旗の色やモチーフ）。ただし**国家元首・政治家の肖像を直接描かない**こと（シルエット・後ろ姿・象徴物のみで示す）。
- 【品質要件（必ず含める）】: high quality, highly detailed, professional, striking composition, clean and elegant
- 【構図の注意】: 「雑誌の表紙」「ポスター」「書籍カバー」のレイアウトは禁止。文字を載せる余白や帯を想定しない。**純粋なイラスト／シーンのみ**。
- 【禁止事項（必ず含める）】: 日本語・中国語・韓国語を一切書かない。No text, no typography, no words, no letters, no numbers, no captions, no headlines, no logos, no watermarks, no characters in any language. No recognizable portraits of political leaders or heads of state."""


def _finalize_prompt_for_api(prompt: str) -> str:
    """保存済み／回退いずれのプロンプトも、API 直前に正規化する。"""
    text = (prompt or "").strip()
    for pattern, replacement in _PROMPT_LAYOUT_PHRASES:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    if _NO_TEXT_SUFFIX.strip() not in text:
        text = text.rstrip(". ") + "." + _NO_TEXT_SUFFIX
    return text


def _is_alibaba_compatible_mode() -> bool:
    return "compatible-mode" in ALIBABA_API_URL


def _alibaba_generation_url() -> str:
    """DashScope / Token Plan 文生图エンドポイント URL を組み立てる。"""
    base = ALIBABA_API_URL.rstrip("/")
    if _is_alibaba_compatible_mode():
        return f"{base}/chat/completions"
    if "/services/aigc/" in base:
        return base
    model = ALIBABA_IMAGE_MODEL.lower()
    if model.startswith("wan2.7") or model.startswith("qwen"):
        path = "/services/aigc/multimodal-generation/generation"
    elif model.startswith("wan"):
        path = "/services/aigc/image-generation/generation"
    else:
        path = "/services/aigc/multimodal-generation/generation"
    return f"{base}{path}"


def _alibaba_tasks_url(task_id: str) -> str:
    base = ALIBABA_API_URL.rstrip("/")
    if "/services/aigc/" in base:
        base = base.split("/services/aigc/")[0]
    return f"{base}/tasks/{task_id}"


def _extract_image_url_from_response(data: dict) -> str | None:
    output = data.get("output") or {}
    task_status = output.get("task_status")
    if task_status == "FAILED":
        return None
    if task_status == "SUCCEEDED":
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


class ImageGenerator:
    """挿絵生成クラス"""

    def __init__(self, issue_date: str):
        self.issue_date = issue_date
        self.state = StateManager(issue_date)
        self.output_dir = get_issue_dir(issue_date)
        self.provider = IMG_GENERATION_PROVIDER
        self._gemini_client = None
        self._ssh_remote = None  # ComfyUI Mac SSH (lazy init)

        if self.provider == "gemini":
            if not GEMINI_API_KEY:
                raise ValueError(
                    "IMG_GENERATION_PROVIDER=gemini ですが GEMINI_API_KEY が未設定です。"
                )
            from google import genai

            self._gemini_client = genai.Client(api_key=GEMINI_API_KEY)
            print(f"[情報] 画像生成: Gemini ({GEMINI_IMAGE_MODEL})")
        elif self.provider == "alibaba":
            if not ALIBABA_API_KEY:
                raise ValueError(
                    "IMG_GENERATION_PROVIDER=alibaba ですが ALIBABA_API_KEY が未設定です。"
                )
            print(
                f"[情報] 画像生成: 阿里云百炼 ({ALIBABA_IMAGE_MODEL}) "
                f"→ {_alibaba_generation_url()}"
            )
        elif self.provider == "comfyui":
            print(
                f"[情報] 画像生成: ComfyUI Mac MLX "
                f"({COMFYUI_REMOTE_HOST}, {COMFYUI_IMAGE_WIDTH}x{COMFYUI_IMAGE_HEIGHT}, "
                f"steps={COMFYUI_STEPS}, VAE={COMFYUI_VAE_NAME})"
            )
        else:
            raise ValueError(f"未対応の IMG_GENERATION_PROVIDER: {self.provider}")

        self._last_moderation_block = False

    @staticmethod
    def _is_moderation_error_text(text: str) -> bool:
        t = (text or "").lower()
        return "datainspectionfailed" in t or "green net check failed" in t

    def _find_cover_image(self) -> Path | None:
        """保存済みの雑誌表紙画像を検索する"""
        for ext in ["jpg", "jpeg", "png", "webp"]:
            cover_path = self.output_dir / f"cover.{ext}"
            if cover_path.exists():
                return cover_path
        return None

    def _resize_to_output(self, image: PILImage.Image) -> PILImage.Image:
        """画像を指定サイズ（768x1024）にリサイズする"""
        return image.resize(
            (OUTPUT_WIDTH, OUTPUT_HEIGHT),
            PILImage.Resampling.LANCZOS,
        )

    def _load_saved_image_prompt(self, article_meta: dict) -> str | None:
        """rewrite_content が保存した NNN_prompt.txt を読み込む。"""
        aid = article_meta.get("id")
        if aid is None:
            return None
        prompt_file = self.output_dir / "articles" / "images" / f"{int(aid):03d}_prompt.txt"
        if not prompt_file.exists():
            return None
        try:
            text = prompt_file.read_text(encoding="utf-8").strip()
        except OSError:
            return None
        return text or None

    def _save_image_prompt(self, article_id: int | str, prompt: str) -> Path:
        """NNN_prompt.txt に image_prompt を保存する。"""
        images_dir = self.output_dir / "articles" / "images"
        images_dir.mkdir(parents=True, exist_ok=True)
        prompt_file = images_dir / f"{int(article_id):03d}_prompt.txt"
        prompt_file.write_text(prompt.strip(), encoding="utf-8")
        return prompt_file

    def _load_article_body(self, article_id: int | str) -> str | None:
        """改写済み記事本文（front matter 除去）を読み込む。"""
        article_file = self.output_dir / "articles" / f"{int(article_id):03d}.md"
        if not article_file.exists():
            return None
        try:
            text = article_file.read_text(encoding="utf-8")
        except OSError:
            return None
        if text.startswith("---"):
            parts = text.split("---", 2)
            if len(parts) >= 3:
                body = parts[2].strip()
                return body or None
        body = text.strip()
        return body or None

    @staticmethod
    def _strip_llm_plain_output(text: str) -> str:
        """LLM 応答から余計なマークダウン装飾を除去する。"""
        cleaned = (text or "").strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```\w*\n?", "", cleaned)
            cleaned = re.sub(r"\n?```\s*$", "", cleaned).strip()
        return cleaned.strip('"').strip("'")

    def _build_image_prompt_llm_request(self, article: dict, body: str) -> str:
        """GEMINI_FLASH_MODEL 向けの image_prompt 再生成プロンプトを組み立てる。"""
        title_ja = article.get("japanese_title") or article.get("original_title", "")
        title_en = article.get("original_title", "")
        section = article.get("section", "")
        keywords = article.get("keywords_ja") or []
        keywords_str = ", ".join(keywords) if keywords else "（なし）"
        summary = article.get("summary_ja", "")

        return f"""あなたはエディトリアル挿絵のための画像生成プロンプト作成者です。
以下の記事内容に基づき、画像生成 AI 用の **英語プロンプトのみ** を1つ作成してください。
記事の改写は不要です。プロンプト文字列だけを出力してください（説明文・マークダウン・コードブロック禁止）。

## 記事メタデータ
- 日本語タイトル: {title_ja}
- 英語タイトル: {title_en}
- セクション: {section}
- キーワード: {keywords_str}
- 要約: {summary}

## image_prompt 作成ルール
{_IMAGE_PROMPT_LLM_RULES}

## 記事本文（日本語）
{body}"""

    def _regenerate_image_prompt_with_llm(self, article: dict) -> str | None:
        """記事本文から GEMINI_FLASH_MODEL で image_prompt を再生成し保存する。"""
        aid = article.get("id")
        if aid is None:
            return None

        body = self._load_article_body(aid)
        if not body:
            print(
                f"      [警告] 記事本文が見つかりません "
                f"(articles/{int(aid):03d}.md)"
            )
            return None

        if not GEMINI_API_KEY:
            print("      [エラー] GEMINI_API_KEY が未設定のため prompt を再生成できません")
            return None

        llm_prompt = self._build_image_prompt_llm_request(article, body)
        try:
            image_prompt = self._strip_llm_plain_output(
                text_llm.generate_text(
                    llm_prompt,
                    tier="flash",
                    provider_override="gemini",
                )
            )
        except Exception as e:
            print(f"      [エラー] image_prompt の LLM 生成に失敗: {e}")
            return None

        if not image_prompt:
            print("      [エラー] LLM が空の image_prompt を返しました")
            return None

        self._save_image_prompt(aid, image_prompt)
        print(
            f"      [情報] 新しいプロンプトを LLM ({GEMINI_FLASH_MODEL}) で生成し、"
            f"articles/images/{int(aid):03d}_prompt.txt に保存しました"
        )
        return image_prompt

    def _build_image_prompt(self, article_meta: dict) -> str:
        """画像生成用のプロンプトを構築する（保存済み prompt を優先）。"""
        saved = self._load_saved_image_prompt(article_meta)
        if saved:
            return saved

        title = article_meta.get("original_title", "")
        return (
            "Generate a high-end editorial illustration with cinematic epic scale and blockbuster visual impact. "
            f"Visual concept inspired by the article topic (do not render any words): {title}. "
            "Striking conceptual metaphor, bold vibrant aesthetics, powerful focal point. "
            "Photorealistic, high-quality 3D render, or premium digital art. "
            "Large central subjects filling the frame. "
            "Purely visual scene — NOT a magazine cover layout, NOT a poster, NOT a book cover. "
            "Absolutely no text, typography, captions, headlines, logos, watermarks, letters, numbers, or characters of any language."
        )

    def _build_neutral_image_prompt(self, article_meta: dict) -> str:
        """阿里云のコンテンツ審査（Green net）回避用。人物名・対立構図を避けた抽象プロンプト。"""
        saved = self._load_saved_image_prompt(article_meta)
        if saved:
            return saved

        title = article_meta.get("original_title", "global economy")
        return (
            "High-end editorial illustration, cinematic epic scale, blockbuster visual impact. "
            f"Abstract visual metaphor inspired by: {title}. "
            "Symbolic objects, globes, bridges, or geometric structures only. "
            "Bold vibrant aesthetics. Photorealistic or premium digital art. "
            "No recognizable people, no faces, no political leaders, no national flags, "
            "no weapons, no fighting, no war scenes. "
            "NOT a magazine cover. Purely visual. "
            "Absolutely no text, typography, captions, letters, numbers, or characters in any language."
        )

    @staticmethod
    def _build_minimal_image_prompt() -> str:
        """審査が厳しい題材向けの最小プロンプト（地域・人物・対立を一切含めない）。"""
        return (
            "High-end editorial illustration, cinematic epic scale, blockbuster visual impact. "
            "A striking conceptual metaphor with a globe, connecting lines, or abstract structures suggesting "
            "international business and cooperation. Bold vibrant aesthetics. Photorealistic or premium digital art. "
            "NOT a magazine cover. No people, no faces, no flags, no landmarks. "
            "Absolutely no text, typography, captions, letters, numbers, or characters in any language."
        )

    def _save_pil_to_output(self, pil_image: PILImage.Image, output_path: Path) -> None:
        if pil_image.mode != "RGB":
            pil_image = pil_image.convert("RGB")
        self._resize_to_output(pil_image).save(str(output_path))

    def _download_image_bytes(self, url: str) -> bytes:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=120) as resp:
            return resp.read()

    def _alibaba_post(self, body: dict, *, async_mode: bool = False) -> dict:
        url = _alibaba_generation_url()
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {ALIBABA_API_KEY}",
        }
        if async_mode:
            headers["X-DashScope-Async"] = "enable"
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=300) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _alibaba_get_task(self, task_id: str) -> dict:
        url = _alibaba_tasks_url(task_id)
        req = urllib.request.Request(
            url,
            headers={"Authorization": f"Bearer {ALIBABA_API_KEY}"},
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _poll_alibaba_task(self, task_id: str, max_wait_sec: int = 180) -> dict | None:
        deadline = time.time() + max_wait_sec
        interval = 3.0
        while time.time() < deadline:
            data = self._alibaba_get_task(task_id)
            output = data.get("output") or {}
            status = output.get("task_status")
            if status == "SUCCEEDED":
                return data
            if status in ("FAILED", "UNKNOWN", "CANCELED"):
                print(f"      [エラー] 阿里云タスク失敗: status={status} {data.get('message', '')}")
                return None
            time.sleep(interval)
            interval = min(interval * 1.2, 10.0)
        print(f"      [エラー] 阿里云タスクがタイムアウトしました (task_id={task_id})")
        return None

    def _alibaba_request_parameters(self) -> dict:
        """モデル世代に応じた parameters を組み立てる。"""
        params: dict = {
            "size": ALIBABA_IMAGE_SIZE,
            "n": 1,
            "watermark": False,
        }
        model_lower = ALIBABA_IMAGE_MODEL.lower()
        if model_lower.startswith("wan2.7"):
            params["thinking_mode"] = False
        else:
            params["prompt_extend"] = False
            params["negative_prompt"] = _ALIBABA_NEGATIVE_PROMPT
        return params

    def _build_alibaba_request_body(self, prompt: str) -> dict:
        messages = [
            {
                "role": "user",
                "content": [{"text": prompt}],
            }
        ]
        params = self._alibaba_request_parameters()
        if _is_alibaba_compatible_mode():
            return {
                "model": ALIBABA_IMAGE_MODEL,
                "messages": messages,
                "parameters": params,
            }
        return {
            "model": ALIBABA_IMAGE_MODEL,
            "input": {"messages": messages},
            "parameters": params,
        }

    def _generate_image_alibaba(self, prompt: str, output_path: Path) -> bool:
        """阿里云百炼（DashScope / Token Plan）で画像を生成して保存する。"""
        self._last_moderation_block = False
        body = self._build_alibaba_request_body(prompt)

        try:
            data = self._alibaba_post(body, async_mode=False)
            image_url = _extract_image_url_from_response(data)

            if not image_url:
                output = data.get("output") or {}
                task_id = output.get("task_id")
                if task_id:
                    polled = self._poll_alibaba_task(task_id)
                    if polled:
                        image_url = _extract_image_url_from_response(polled)

            if not image_url:
                code = data.get("code") or ""
                message = data.get("message") or ""
                if self._is_moderation_error_text(f"{code} {message}"):
                    self._last_moderation_block = True
                print(
                    f"      [警告] レスポンスに画像 URL がありません"
                    f"{f' ({code}: {message})' if code or message else ''}"
                )
                return False

            raw = self._download_image_bytes(image_url)
            pil_image = PILImage.open(io.BytesIO(raw))
            self._save_pil_to_output(pil_image, output_path)
            return True

        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            if self._is_moderation_error_text(err_body):
                self._last_moderation_block = True
            print(f"      [エラー] 阿里云 API HTTP {e.code}: {err_body[:500]}")
            return False
        except Exception as e:
            print(f"      [エラー] 阿里云画像生成に失敗: {e}")
            return False

    def _generate_image_gemini(self, prompt: str, output_path: Path) -> bool:
        """Gemini 2.5 Flash Imageで画像を生成して保存する（出力サイズ: 768x1024）"""
        from google.genai import types

        try:
            config = types.GenerateContentConfig(
                image_config=types.ImageConfig(
                    aspect_ratio="3:4",
                    image_size="2K",
                ),
            )
            response = self._gemini_client.models.generate_content(
                model=GEMINI_IMAGE_MODEL,
                contents=[prompt],
                config=config,
            )

            for part in response.parts:
                if part.inline_data is not None and getattr(part.inline_data, "data", None):
                    pil_image = PILImage.open(io.BytesIO(part.inline_data.data))
                    self._save_pil_to_output(pil_image, output_path)
                    return True

            print("      [警告] レスポンスに画像データが含まれていません")
            for part in response.parts:
                if part.text is not None:
                    print(f"      モデル応答: {part.text[:200]}")
            return False

        except Exception as e:
            print(f"      [エラー] Gemini 画像生成に失敗: {e}")
            return False

    def _generate_image(self, prompt: str, output_path: Path) -> bool:
        if self.provider == "alibaba":
            return self._generate_image_alibaba(prompt, output_path)
        if self.provider == "comfyui":
            return self._generate_image_comfyui(prompt, output_path)
        return self._generate_image_gemini(prompt, output_path)

    # ------------------------------------------------------------------
    # ComfyUI provider (Mac native MPS + FLUX.2-klein GGUF, SSH)
    # ------------------------------------------------------------------

    def _get_ssh_remote(self):
        """Lazy-init plain SSH/SCP client for Mac ComfyUI host."""
        if self._ssh_remote is None:
            from fish_audio_batch import _PlainSSHRemote

            self._ssh_remote = _PlainSSHRemote(
                COMFYUI_REMOTE_HOST,
                lock_path=self.output_dir / ".comfyui_ssh.lock",
            )
        return self._ssh_remote

    @staticmethod
    def _comfyui_api_curl(path: str, *, fail_ok: bool = True) -> str:
        """SSH 経由で Mac 上の ComfyUI API を curl するコマンド文字列。

        --max-time で ComfyUI 処理中の応答遅延による SSH ハングを防ぐ。
        fail_ok=True のとき HTTP エラーでも空文字を返す（|| true）。
        """
        fail_flag = "-sf" if fail_ok else "-s"
        return (
            f"curl {fail_flag} --max-time {COMFYUI_CURL_MAX_TIME} "
            f"http://127.0.0.1:{COMFYUI_API_PORT}{path} || true"
        )

    def _ensure_comfyui_api_ready(self) -> None:
        """Mac 上の ComfyUI API (8188) が応答するまで待機。未起動なら nohup で起動する。"""
        ssh = self._get_ssh_remote()

        resp = ssh.ssh_short(self._comfyui_api_curl("/system_stats"), label="ComfyUI API check")
        if resp and '"system"' in resp:
            print("      [ComfyUI] API は既に応答しています")
            return

        print("      [ComfyUI] サーバーを起動中…")
        launch = (
            f"cd {COMFYUI_DIR} && "
            f"source {COMFYUI_VENV}/bin/activate && "
            f"export PYTORCH_ENABLE_MPS_FALLBACK=1 && "
            f"nohup python main.py --force-fp16 --reserve-vram 3 "
            f"--listen 127.0.0.1 --port {COMFYUI_API_PORT} "
            f"> {COMFYUI_DIR}/comfyui_server.log 2>&1 &"
        )
        ssh.ssh_short(launch, label="ComfyUI launch")

        print("      [ComfyUI] API の起動を待機中…")
        for attempt in range(60):  # max 300s
            time.sleep(5)
            resp = ssh.ssh_short(
                self._comfyui_api_curl("/system_stats"),
                label="ComfyUI API poll",
            )
            if resp and '"system"' in resp:
                print(f"      [ComfyUI] API 準備完了 ({(attempt + 1) * 5}s)")
                return
        raise RuntimeError("ComfyUI API が 300 秒以内に起動しませんでした")

    @staticmethod
    def _build_comfyui_workflow(prompt: str, seed: int) -> dict:
        """Build ComfyUI API-format workflow JSON with injected prompt (text2image)."""
        return {
            "116": {
                "class_type": "CLIPLoaderGGUF",
                "inputs": {"clip_name": "Qwen3-8B-Q4_K_M.gguf", "type": "flux2"},
            },
            "114": {
                "class_type": "UnetLoaderGGUF",
                "inputs": {"unet_name": "flux-2-klein-9b-Q4_K_M.gguf"},
            },
            "121": {
                "class_type": "VAELoader",
                "inputs": {"vae_name": COMFYUI_VAE_NAME},
            },
            "124": {
                "class_type": "EmptyFlux2LatentImage",
                "inputs": {
                    "width": COMFYUI_IMAGE_WIDTH,
                    "height": COMFYUI_IMAGE_HEIGHT,
                    "batch_size": 1,
                },
            },
            "123": {
                "class_type": "CLIPTextEncode",
                "inputs": {"text": prompt, "clip": ["116", 0]},
            },
            "126": {
                "class_type": "ConditioningZeroOut",
                "inputs": {"conditioning": ["123", 0]},
            },
            "118": {
                "class_type": "KSampler",
                "inputs": {
                    "model": ["114", 0],
                    "positive": ["123", 0],
                    "negative": ["126", 0],
                    "latent_image": ["124", 0],
                    "seed": seed,
                    "steps": COMFYUI_STEPS,
                    "cfg": 1.0,
                    "sampler_name": "euler",
                    "scheduler": "simple",
                    "denoise": 1.0,
                },
            },
            "120": {
                "class_type": "VAEDecode",
                "inputs": {"samples": ["118", 0], "vae": ["121", 0]},
            },
            "9": {
                "class_type": "SaveImage",
                "inputs": {"images": ["120", 0], "filename_prefix": "Flux2"},
            },
        }

    def _comfyui_queue_status(self, ssh, prompt_id: str) -> str | None:
        """ComfyUI /queue から prompt_id の状態を返す: running | pending | None"""
        try:
            q_text = ssh.ssh_short(
                self._comfyui_api_curl("/queue", fail_ok=False),
                label="ComfyUI queue",
            )
        except RuntimeError:
            return None
        if not q_text:
            return None
        try:
            q = json.loads(q_text)
        except (json.JSONDecodeError, TypeError):
            return None
        for item in q.get("queue_running") or []:
            if len(item) >= 2 and item[1] == prompt_id:
                return "running"
        for item in q.get("queue_pending") or []:
            if len(item) >= 2 and item[1] == prompt_id:
                return "pending"
        return None

    def _generate_image_comfyui(self, prompt: str, output_path: Path) -> bool:
        """Generate image via ComfyUI API on Mac (SSH + curl + SCP). text2image only."""
        ssh = self._get_ssh_remote()
        seed = random.randint(0, 2**32)
        workflow = self._build_comfyui_workflow(prompt, seed)

        # Build workflow and encode as base64 to avoid shell escaping issues
        payload = json.dumps(
            {"prompt": workflow, "client_id": f"img-{seed}"},
            ensure_ascii=False,
        )
        payload_b64 = base64.b64encode(payload.encode("utf-8")).decode("ascii")

        # Submit prompt via SSH (base64 decode on remote, pipe to curl)
        submit_cmd = (
            f"echo '{payload_b64}' | base64 -d | "
            f"curl -s -X POST http://127.0.0.1:{COMFYUI_API_PORT}/prompt "
            f"-H 'Content-Type: application/json' -d @-"
        )
        resp_text = ssh.ssh_short(submit_cmd, label="ComfyUI submit")
        try:
            resp_data = json.loads(resp_text)
        except (json.JSONDecodeError, TypeError):
            print(f"      [エラー] ComfyUI レスポンス解析失敗: {resp_text[:500]}")
            return False

        # Check for node_errors or missing prompt_id
        node_errors = resp_data.get("node_errors", {})
        if node_errors:
            print(f"      [エラー] ComfyUI ノードエラー: {node_errors}")
            return False

        prompt_id = resp_data.get("prompt_id")
        if not prompt_id:
            err = resp_data.get("error") or {}
            print(
                f"      [エラー] ComfyUI prompt_id なし: "
                f"{err.get('message', '')} {resp_text[:300]}"
            )
            return False

        # Poll for completion（FLUX t2i は Mac MPS で 1〜3 分程度）
        poll_interval = 5
        max_attempts = max(1, COMFYUI_GENERATION_TIMEOUT // poll_interval)
        dns_fail_streak = 0
        print(
            f"      [ComfyUI] 生成待機中… (prompt_id={prompt_id[:8]}…, "
            f"最大 {COMFYUI_GENERATION_TIMEOUT}s)"
        )
        for attempt in range(max_attempts):
            time.sleep(poll_interval)
            try:
                hist_text = ssh.ssh_short(
                    self._comfyui_api_curl(f"/history/{prompt_id}", fail_ok=False),
                    label="ComfyUI poll",
                )
                dns_fail_streak = 0
            except RuntimeError as e:
                dns_fail_streak += 1
                # DNS/SSH 失敗は連発するため間引き表示（毎回ログるとダッシュボードが埋まる）
                if dns_fail_streak == 1 or dns_fail_streak % 12 == 0:
                    print(
                        f"      [警告] ComfyUI poll SSH 失敗 "
                        f"({attempt + 1}/{max_attempts}, streak={dns_fail_streak}): {e}"
                    )
                continue

            if not hist_text:
                continue

            try:
                hist = json.loads(hist_text)
            except (json.JSONDecodeError, TypeError):
                continue

            entry = hist.get(prompt_id)
            if not entry:
                q_status = self._comfyui_queue_status(ssh, prompt_id)
                if (attempt + 1) % 6 == 0:
                    elapsed = (attempt + 1) * poll_interval
                    if q_status == "running":
                        print(
                            f"      [ComfyUI] 実行中… {elapsed}s / {COMFYUI_GENERATION_TIMEOUT}s"
                        )
                    elif q_status == "pending":
                        print(
                            f"      [ComfyUI] キュー待ち… {elapsed}s / "
                            f"{COMFYUI_GENERATION_TIMEOUT}s"
                        )
                    else:
                        print(
                            f"      [ComfyUI] 待機中… {elapsed}s / "
                            f"{COMFYUI_GENERATION_TIMEOUT}s"
                        )
                continue

            status = entry.get("status", {})

            # Check for execution error
            if status.get("status_str") == "error":
                msgs = status.get("messages", [])
                print(f"      [エラー] ComfyUI 実行エラー: {str(msgs)[:300]}")
                return False

            if not status.get("completed", False):
                if (attempt + 1) % 6 == 0:
                    elapsed = (attempt + 1) * poll_interval
                    q_status = self._comfyui_queue_status(ssh, prompt_id)
                    state = q_status or "processing"
                    print(
                        f"      [ComfyUI] {state}… {elapsed}s / "
                        f"{COMFYUI_GENERATION_TIMEOUT}s"
                    )
                continue

            # Completed — extract output filename
            outputs = entry.get("outputs", {})
            filename = None
            subfolder = ""
            for _nid, nout in outputs.items():
                for img in nout.get("images", []):
                    filename = img["filename"]
                    subfolder = img.get("subfolder", "") or ""
                    break
                if filename:
                    break

            if not filename:
                print("      [エラー] ComfyUI 出力画像が見つかりません")
                return False

            # SCP download image
            if subfolder:
                remote_path = f"{COMFYUI_OUTPUT_DIR}/{subfolder}/{filename}"
            else:
                remote_path = f"{COMFYUI_OUTPUT_DIR}/{filename}"
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                tmp_path = Path(tmp.name)

            try:
                ssh.run_with_retry(
                    ssh.scp_from_remote(remote_path, tmp_path),
                    timeout=60,
                    label="ComfyUI SCP download",
                )
                pil_image = PILImage.open(tmp_path)
                self._save_pil_to_output(pil_image, output_path)
                return True
            except Exception as e:
                print(f"      [エラー] ComfyUI 画像ダウンロード失敗: {e}")
                return False
            finally:
                tmp_path.unlink(missing_ok=True)

        print(
            f"      [エラー] ComfyUI 生成がタイムアウトしました "
            f"({COMFYUI_GENERATION_TIMEOUT}s)"
        )
        return False

    def _image_exists_for_order(self, images_dir: Path, order: int) -> bool:
        """generate_video._validate_episode_assets と同じ基準で画像の有無を判定する。"""
        base = f"{int(order):02d}"
        for ext in ("png", "jpg", "jpeg", "webp"):
            if (images_dir / f"{base}.{ext}").exists():
                return True
        return False

    def _generate_or_copy_article_image(
        self,
        article: dict,
        images_dir: Path,
        cover_image: Path | None,
        file_stem: str,
    ) -> bool:
        """1 記事分の挿絵を生成または表紙からコピーする。成功時 True。"""
        image_path = images_dir / f"{file_stem}.png"

        if article.get("is_cover_story") and cover_image:
            cover_img = PILImage.open(cover_image).convert("RGB")
            self._resize_to_output(cover_img).save(image_path)
            return True

        saved_prompt = self._load_saved_image_prompt(article)
        if saved_prompt:
            print(f"      [情報] プロンプト: 保存済み articles/images/{file_stem}_prompt.txt")
            raw_prompt = saved_prompt
        else:
            print(
                f"      [情報] プロンプト: 回退テンプレート"
                f"（{file_stem}_prompt.txt がありません）"
            )
            raw_prompt = self._build_image_prompt(article)

        prompt = _finalize_prompt_for_api(raw_prompt)
        if self._generate_image(prompt, image_path):
            return True
        if self.provider == "alibaba" and self._last_moderation_block:
            print("      [情報] コンテンツ審査により拒否されたため、抽象・中立プロンプトで再試行…")
            neutral = _finalize_prompt_for_api(self._build_neutral_image_prompt(article))
            time.sleep(1)
            if self._generate_image(neutral, image_path):
                return True
            if self._last_moderation_block:
                print("      [情報] 中立プロンプトも拒否されたため、最小プロンプトで再試行…")
                time.sleep(1)
                return self._generate_image(
                    _finalize_prompt_for_api(self._build_minimal_image_prompt()), image_path
                )
        return False

    def _collect_missing_articles(self) -> list[dict]:
        """analysis.json の KEEP 記事について、許容拡張子のいずれも無いものを列挙する。"""
        missing: list[dict] = []
        analysis_path = self.output_dir / "analysis.json"
        if not analysis_path.exists():
            return missing

        with open(analysis_path, "r", encoding="utf-8") as f:
            analysis = json.load(f)

        images_dir = self.output_dir / "articles" / "images"
        for article in analysis:
            if article.get("status") != "KEEP":
                continue

            aid = article.get("id")
            if aid is None:
                continue

            base = f"{int(aid):03d}"
            found = False
            for ext in ("png", "jpg", "jpeg", "webp"):
                if (images_dir / f"{base}.{ext}").exists():
                    found = True
                    break
            if not found:
                missing.append(article)
        return missing

    def _verify_and_retry_missing_images(
        self,
        cover_image: Path | None,
        max_rounds: int = 3,
    ) -> bool:
        """タスク終了時に不足挿絵を検査し、欠損があれば再生成を繰り返す。"""
        images_dir = self.output_dir / "articles" / "images"
        images_dir.mkdir(parents=True, exist_ok=True)

        for round_idx in range(max_rounds):
            missing = self._collect_missing_articles()
            if not missing:
                if round_idx > 0:
                    print("\n[情報] 全記事の挿絵が揃いました。")
                return True

            print(
                f"\n[情報] 挿絵不足 {len(missing)} 件を検出しました。"
                f" 再生成します（{round_idx + 1}/{max_rounds} 回目）…"
            )
            for article in missing:
                aid = article["id"]
                title = article.get("japanese_title", article.get("original_title", ""))
                base = f"{int(aid):03d}"

                print(f"    [{base}] 再生成: {title}")
                ok = self._generate_or_copy_article_image(article, images_dir, cover_image, base)
                out_path = images_dir / f"{base}.png"
                if ok:
                    print(f"      → 保存: {out_path}")
                else:
                    print("      → 生成失敗")
                if not (article.get("is_cover_story") and cover_image):
                    time.sleep(1)

        final_missing = self._collect_missing_articles()
        if final_missing:
            ids_preview = ", ".join(f"{int(a['id']):03d}" for a in final_missing[:15])
            more = f" …他{len(final_missing) - 15}件" if len(final_missing) > 15 else ""
            print(
                f"\n[エラー] {max_rounds} 回の再生成後も挿絵が不足しています: {ids_preview}{more}"
            )
            return False
        return True

    def process_all_articles(self, skip_review: bool = False) -> bool:
        """全記事の挿絵を生成する（エピソード分組前）

        Args:
            skip_review: True の場合はユーザーレビューを要求しない。
        """
        self.state.start_step("GENERATE_IMAGES")

        if self.provider == "comfyui":
            self._ensure_comfyui_api_ready()

        try:
            analysis_path = self.output_dir / "analysis.json"
            if not analysis_path.exists():
                print("[エラー] analysis.json が見つかりません。")
                return False

            with open(analysis_path, "r", encoding="utf-8") as f:
                analysis = json.load(f)

            cover_image = self._find_cover_image()
            if cover_image:
                print(f"[情報] 雑誌表紙画像: {cover_image}")
            else:
                print("[警告] 雑誌表紙画像が見つかりません。カバーストーリーにもAPIで画像を生成します。")

            images_dir = self.output_dir / "articles" / "images"
            images_dir.mkdir(parents=True, exist_ok=True)

            articles = [a for a in analysis if a.get("status") == "KEEP"]
            print(f"\n[処理中] {len(articles)}篇の記事挿絵を生成")

            for article in articles:
                aid = article["id"]
                title = article.get("japanese_title", article.get("original_title", ""))
                base = f"{int(aid):03d}"

                exists = False
                for ext in ("png", "jpg", "jpeg", "webp"):
                    if (images_dir / f"{base}.{ext}").exists():
                        exists = True
                        break

                if exists:
                    print(f"    [{base}] スキップ（既存）: {title}")
                    continue

                if article.get("is_cover_story") and cover_image:
                    print(f"    [{base}] 表紙画像をコピー（リサイズ）: {title}")
                    success = self._generate_or_copy_article_image(
                        article, images_dir, cover_image, base
                    )
                    if success:
                        print(f"      → 保存: {images_dir / f'{base}.png'}")
                    else:
                        print("      → 失敗")
                else:
                    print(f"    [{base}] 生成中: {title}")
                    success = self._generate_or_copy_article_image(
                        article, images_dir, cover_image, base
                    )
                    if success:
                        print(f"      → 保存: {images_dir / f'{base}.png'}")
                    else:
                        print("      → 生成失敗")
                    time.sleep(1)

            if not self._verify_and_retry_missing_images(cover_image):
                return False

            if not skip_review:
                self.state.request_user_review(
                    "GENERATE_IMAGES",
                    "生成された挿絵を articles/images/ ディレクトリで確認してください。"
                    "不要な画像を差し替えたい場合は同名ファイルで上書きしてください。確認後 --approve で承認してください。",
                )
            else:
                self.state.complete_step("GENERATE_IMAGES")

            return True
        finally:
            if self.provider == "comfyui":
                stop_comfyui_container_if_running()

    def regenerate_article_image(self, article_id: int | str) -> bool:
        """指定された記事の画像を強制的に再生成する（WebUI等から単発呼び出し用）"""
        if self.provider == "comfyui":
            self._ensure_comfyui_api_ready()

        analysis_path = self.output_dir / "analysis.json"
        if not analysis_path.exists():
            return False

        with open(analysis_path, "r", encoding="utf-8") as f:
            analysis = json.load(f)

        target_article = None
        for a in analysis:
            if str(a.get("id")) == str(article_id):
                target_article = a
                break

        if not target_article:
            print(f"[エラー] ID {article_id} の記事が analysis.json に見つかりません。")
            return False

        cover_image = self._find_cover_image()
        images_dir = self.output_dir / "articles" / "images"
        images_dir.mkdir(parents=True, exist_ok=True)
        base = f"{int(article_id):03d}"

        print(
            f"\n[WebUI] 記事 {base} ({target_article.get('japanese_title', '')}) の画像を再生成します..."
        )

        if not (target_article.get("is_cover_story") and cover_image):
            print(f"      [情報] 記事内容から image_prompt を LLM で再生成します ({GEMINI_FLASH_MODEL})…")
            if not self._regenerate_image_prompt_with_llm(target_article):
                print("      [警告] prompt 再生成に失敗したため、既存 prompt で続行します")

        success = self._generate_or_copy_article_image(target_article, images_dir, cover_image, base)
        if success:
            print(f"      → 保存: {images_dir / f'{base}.png'}")
        else:
            print("      → 生成失敗")

        return success


def stop_comfyui_container_if_running() -> None:
    """ComfyUI を停止し Mac 上のメモリを解放する（/free → プロセス終了）。

    process_all_articles 完了時（成功/失敗問わず）および orchestrate が TTS 開始前に呼ぶ。
    幂等: 既に停止済みなら no-op。
    No-op if IMG_GENERATION_PROVIDER != "comfyui".
    """
    if IMG_GENERATION_PROVIDER != "comfyui":
        return

    print("[ComfyUI] 停止・メモリ解放中…")
    try:
        from fish_audio_batch import _PlainSSHRemote

        ssh = _PlainSSHRemote(COMFYUI_REMOTE_HOST)

        try:
            ssh.ssh_short(
                f"curl -sf -X POST http://127.0.0.1:{COMFYUI_API_PORT}/free "
                f"-H 'Content-Type: application/json' "
                f"-d '{{\"unload_models\": true, \"free_memory\": true}}' || true",
                label="ComfyUI /free",
            )
        except Exception:
            pass  # API 未応答時は kill のみ続行

        port = COMFYUI_API_PORT
        kill_cmd = (
            f"for pid in $(lsof -ti tcp:{port} 2>/dev/null); do "
            f"kill -15 $pid 2>/dev/null || true; done; "
            f"sleep 2; "
            f"for pid in $(lsof -ti tcp:{port} 2>/dev/null); do "
            f"kill -9 $pid 2>/dev/null || true; done; "
            f"true"
        )
        ssh.ssh_short(kill_cmd, label="ComfyUI kill")
        print("[ComfyUI] サーバー停止・メモリ解放完了")
    except Exception as e:
        print(f"[警告] ComfyUI 停止に失敗: {e}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("使用方法: python generate_images.py <YYYY-MM-DD>")
        sys.exit(1)

    issue_date = sys.argv[1]

    generator = ImageGenerator(issue_date)
    generator.process_all_articles()


