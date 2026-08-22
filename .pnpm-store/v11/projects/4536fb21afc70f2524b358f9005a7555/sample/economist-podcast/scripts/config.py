"""
共通設定モジュール
プロジェクト全体で使用するパス定義、API設定、定数を管理する
"""
import os
import re
from pathlib import Path
from dotenv import load_dotenv

# === .envファイルの読み込み ===
_script_dir = Path(__file__).resolve().parent
_skill_dir = _script_dir.parent
# スキルディレクトリの.envを優先的に読み込む
load_dotenv(_skill_dir / ".env")
# プロジェクトルートの.envもフォールバックとして読み込む
load_dotenv()

# === GOOGLE_APPLICATION_CREDENTIALS のパス解決 ===
# .envに相対パスが指定された場合、スキルディレクトリを基準に絶対パスへ変換する
_gac = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")
if _gac and not Path(_gac).is_absolute():
    _resolved = (_skill_dir / _gac).resolve()
    if _resolved.exists():
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(_resolved)

# === パス定義 ===
# スクリプトの位置から逆算してプロジェクトルートを特定
# .cursor/skills/economist-podcast/scripts/ → 4階層上がプロジェクトルート
PROJECT_ROOT = _script_dir.parents[3]
BASE_OUTPUT_DIR = PROJECT_ROOT / "contents" / "audiobook" / "output" / "TheEconomist"
SOURCE_DIR = PROJECT_ROOT / "contents" / "audiobook" / "source"
# 音声クローン参考音（Fish / Qwen / VoxCPM 共通・assests/refs/{role}/）
_TTS_REF_ROOT = _skill_dir / "assests" / "refs"


def _resolve_tts_ref_dir() -> Path:
    """TTS_REF_ROLE で assests/refs/{role} を解決（バックエンド非依存）。"""
    role = os.getenv("TTS_REF_ROLE", "kyoujyu").strip() or "kyoujyu"
    return (_TTS_REF_ROOT / role).resolve()


TTS_REF_ROLE = os.getenv("TTS_REF_ROLE", "kyoujyu").strip() or "kyoujyu"
TTS_REF_DIR = _resolve_tts_ref_dir()
TTS_REF_AUDIO = Path(
    os.getenv("TTS_REF_AUDIO", str(TTS_REF_DIR / "ref_audio.wav"))
).resolve()
TTS_REF_META = Path(
    os.getenv("TTS_REF_META", str(TTS_REF_DIR / "ref_meta.json"))
).resolve()

# === テキスト生成プロバイダ ===
# "gemini" | "xiaomi" | "alibaba" | "glm"（后3者は OpenAI 互換 Chat Completions）
TXT_GENERATION_PROVIDER = os.getenv("TXT_GENERATION_PROVIDER", "gemini").strip().lower()
if TXT_GENERATION_PROVIDER not in ("gemini", "xiaomi", "alibaba", "glm"):
    TXT_GENERATION_PROVIDER = "gemini"

# === Gemini API設定（テキスト生成・画像生成）===
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
# テキスト生成用モデル（分析・改写・TTS準備等）: Pro モデル推奨
GEMINI_PRO_MODEL = os.getenv("GEMINI_PRO_MODEL", "gemini-3.1-pro-preview")
# 軽量タスク用（音声検証失敗時のテキスト改写等）: Flash モデル
GEMINI_FLASH_MODEL = os.getenv("GEMINI_FLASH_MODEL", "gemini-3.1-flash-lite-preview")
# 後方互換（未設定時は PRO にフォールバック）
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "") or GEMINI_PRO_MODEL

# === Xiaomi MiMo API（OpenAI 互換・テキスト生成）===
# 参照: https://platform.xiaomimimo.com/docs/zh-CN/api/chat/openai-api
XIAOMI_API_KEY = os.getenv("XIAOMI_API_KEY", "").strip()
XIAOMI_API_URL = os.getenv("XIAOMI_API_URL", "https://api.xiaomi.com/v1").strip().rstrip("/")
XIAOMI_PRO_MODEL = os.getenv("XIAOMI_PRO_MODEL", "mimo-v2.5-pro")
XIAOMI_FLASH_MODEL = os.getenv("XIAOMI_FLASH_MODEL", "mimo-v2.5")

# === X（Twitter）API OAuth 1.0a（投稿用・generate_x_share.py）===
# Consumer Key / Secret（開発者ポータルでは API Key / API Key Secret と表示されることも）
X_CLIENT_ID = os.getenv("X_CLIENT_ID", "").strip()
X_CLIENT_SECRET = os.getenv("X_CLIENT_SECRET", "").strip()
X_ACCESS_TOKEN = os.getenv("X_ACCESS_TOKEN", "").strip()
X_ACCESS_SECRET = os.getenv("X_ACCESS_SECRET", "").strip()
# 公式 XDK 推奨の API ホスト（未指定時は https://api.x.com）
X_API_BASE_URL = os.getenv("X_API_BASE_URL", "https://api.x.com").strip().rstrip("/")

# === 音声生成 TTS バックエンド ===
# fish（Fish Audio S2 Pro INT8 自托管・既定）| qwen | voxcpm（バックアップ切替用）
TTS_BACKEND = os.getenv("TTS_BACKEND", "fish").strip().lower()
if TTS_BACKEND not in ("fish", "qwen", "voxcpm"):
    TTS_BACKEND = "fish"

# === Fish Audio S2 Pro INT8 自托管（TTS_BACKEND=fish 時・Mac MLX / SSH）===
FISH_AUDIO_TTS_REMOTE_HOST = os.getenv(
    "FISH_AUDIO_TTS_REMOTE_HOST", "cho@rw-mac-1"
).strip()
FISH_AUDIO_TTS_REMOTE_ZONE = os.getenv(
    "FISH_AUDIO_TTS_REMOTE_ZONE", "us-central1-b"
).strip()
FISH_AUDIO_TTS_REMOTE_PROJECT = os.getenv("FISH_AUDIO_TTS_REMOTE_PROJECT", "").strip()
FISH_AUDIO_TTS_REMOTE_VENV = os.getenv(
    "FISH_AUDIO_TTS_REMOTE_VENV", "/Users/cho/fish-audio/.venv"
).strip()
FISH_AUDIO_TTS_REMOTE_WORKROOT = os.getenv(
    "FISH_AUDIO_TTS_REMOTE_WORKROOT", "/Users/cho/fish-audio/jobs"
).strip()
FISH_AUDIO_TTS_REMOTE_WORKER = os.getenv(
    "FISH_AUDIO_TTS_REMOTE_WORKER", "/Users/cho/fish-audio/scripts/fish_audio_mlx_worker.py"
).strip()
FISH_AUDIO_TTS_REMOTE_PYTHONPATH = os.getenv(
    "FISH_AUDIO_TTS_REMOTE_PYTHONPATH",
    "~/fish-audio/scripts:~/fish-audio/fish-speech",
).strip()
# 空の場合は worker 側デフォルト（~/fish-audio/checkpoints/fish-speech-s2-pro-int8）
FISH_AUDIO_TTS_CHECKPOINT = os.getenv("FISH_AUDIO_TTS_CHECKPOINT", "").strip()
try:
    FISH_AUDIO_TTS_MAX_SEQ_LEN = max(
        1024, int(os.getenv("FISH_AUDIO_TTS_MAX_SEQ_LEN", "4096"))
    )
except ValueError:
    FISH_AUDIO_TTS_MAX_SEQ_LEN = 4096
try:
    FISH_AUDIO_TTS_CHUNK_LENGTH = max(
        50, int(os.getenv("FISH_AUDIO_TTS_CHUNK_LENGTH", "300"))
    )
except ValueError:
    FISH_AUDIO_TTS_CHUNK_LENGTH = 300
FISH_AUDIO_TTS_COMPILE = os.getenv("FISH_AUDIO_TTS_COMPILE", "1").strip().lower() in (
    "1",
    "true",
    "yes",
)
FISH_AUDIO_TTS_HALF = os.getenv("FISH_AUDIO_TTS_HALF", "1").strip().lower() not in (
    "0",
    "false",
    "no",
)
FISH_AUDIO_TTS_REF_DIR = TTS_REF_DIR
FISH_AUDIO_TTS_REF_AUDIO = TTS_REF_AUDIO
FISH_AUDIO_TTS_REF_META = TTS_REF_META

# === Qwen3-TTS 自托管（TTS_BACKEND=qwen 時・llm-spot GPU）===
QWEN_TTS_MODEL = os.getenv(
    "QWEN_TTS_MODEL", "Qwen/Qwen3-TTS-12Hz-1.7B-Base"
).strip()
QWEN_TTS_LANGUAGE = os.getenv("QWEN_TTS_LANGUAGE", "Japanese").strip()
QWEN_TTS_DTYPE = os.getenv("QWEN_TTS_DTYPE", "float32").strip()
try:
    QWEN_TTS_BATCH_SIZE = max(1, min(16, int(os.getenv("QWEN_TTS_BATCH_SIZE", "6"))))
except ValueError:
    QWEN_TTS_BATCH_SIZE = 6
QWEN_TTS_REMOTE_HOST = os.getenv("QWEN_TTS_REMOTE_HOST", "cho@llm-spot").strip()
QWEN_TTS_REMOTE_ZONE = os.getenv("QWEN_TTS_REMOTE_ZONE", "us-central1-b").strip()
QWEN_TTS_REMOTE_PROJECT = os.getenv("QWEN_TTS_REMOTE_PROJECT", "").strip()
QWEN_TTS_REMOTE_VENV = os.getenv(
    "QWEN_TTS_REMOTE_VENV", "~/qwen3-tts-native/.venv"
).strip()
QWEN_TTS_REMOTE_WORKROOT = os.getenv(
    "QWEN_TTS_REMOTE_WORKROOT", "~/qwen3-tts-native/jobs"
).strip()
QWEN_TTS_REMOTE_WORKER = os.getenv(
    "QWEN_TTS_REMOTE_WORKER", "~/qwen3-tts-native/scripts/batch_synth_worker.py"
).strip()
# SSH / SCP（Windows 長時間セッション対策・接続タイムアウト）
try:
    QWEN_TTS_SSH_CONNECT_TIMEOUT = max(
        5, int(os.getenv("QWEN_TTS_SSH_CONNECT_TIMEOUT", "30"))
    )
except ValueError:
    QWEN_TTS_SSH_CONNECT_TIMEOUT = 30
try:
    QWEN_TTS_SSH_RETRY_COUNT = max(1, int(os.getenv("QWEN_TTS_SSH_RETRY_COUNT", "3")))
except ValueError:
    QWEN_TTS_SSH_RETRY_COUNT = 3
try:
    QWEN_TTS_SSH_RETRY_WAIT_SEC = max(
        1, int(os.getenv("QWEN_TTS_SSH_RETRY_WAIT_SEC", "10"))
    )
except ValueError:
    QWEN_TTS_SSH_RETRY_WAIT_SEC = 10
try:
    QWEN_TTS_SSH_SHORT_TIMEOUT = max(
        30, int(os.getenv("QWEN_TTS_SSH_SHORT_TIMEOUT", "120"))
    )
except ValueError:
    QWEN_TTS_SSH_SHORT_TIMEOUT = 120
try:
    QWEN_TTS_SSH_WORKER_TIMEOUT = max(
        600, int(os.getenv("QWEN_TTS_SSH_WORKER_TIMEOUT", "86400"))
    )
except ValueError:
    QWEN_TTS_SSH_WORKER_TIMEOUT = 86400
try:
    QWEN_TTS_SSH_POLL_INTERVAL_SEC = max(
        5, int(os.getenv("QWEN_TTS_SSH_POLL_INTERVAL_SEC", "15"))
    )
except ValueError:
    QWEN_TTS_SSH_POLL_INTERVAL_SEC = 15
QWEN_TTS_SSH_USE_IAP = os.getenv("QWEN_TTS_SSH_USE_IAP", "").strip().lower() in (
    "1",
    "true",
    "yes",
)
# 既定: 远程 worker を nohup 起動 + 短い SSH でログポーリング（Windows 長時間 SSH ハング回避）
QWEN_TTS_SSH_DETACHED_WORKER = os.getenv(
    "QWEN_TTS_SSH_DETACHED_WORKER", "1"
).strip().lower() not in ("0", "false", "no")
QWEN_TTS_REF_DIR = TTS_REF_DIR
QWEN_TTS_REF_AUDIO = TTS_REF_AUDIO
QWEN_TTS_REF_META = TTS_REF_META

# === VoxCPM2 設定（float16 + torch.compile + Prompt Cache）===
# VoxCPM2 は Qwen と同じ GPU ホスト (llm-spot) を使用、venv は独立
VOXCPM_TTS_MODEL = os.getenv("VOXCPM_TTS_MODEL", "openbmb/VoxCPM2").strip()
VOXCPM_TTS_CFG = float(os.getenv("VOXCPM_TTS_CFG", "1.6"))
try:
    VOXCPM_TTS_STEPS = max(1, int(os.getenv("VOXCPM_TTS_STEPS", "20")))
except ValueError:
    VOXCPM_TTS_STEPS = 20
VOXCPM_TTS_REMOTE_HOST = os.getenv(
    "VOXCPM_TTS_REMOTE_HOST", "cho@llm-spot"
).strip()
VOXCPM_TTS_REMOTE_ZONE = os.getenv(
    "VOXCPM_TTS_REMOTE_ZONE", "us-central1-b"
).strip()
VOXCPM_TTS_REMOTE_PROJECT = os.getenv("VOXCPM_TTS_REMOTE_PROJECT", "").strip()
VOXCPM_TTS_REMOTE_VENV = os.getenv(
    "VOXCPM_TTS_REMOTE_VENV", "~/voxcpm/.venv"
).strip()
VOXCPM_TTS_REMOTE_WORKROOT = os.getenv(
    "VOXCPM_TTS_REMOTE_WORKROOT", "~/voxcpm/jobs"
).strip()
VOXCPM_TTS_REMOTE_WORKER = os.getenv(
    "VOXCPM_TTS_REMOTE_WORKER", "~/voxcpm/scripts/voxcpm_synth_worker.py"
).strip()
VOXCPM_TTS_REF_DIR = TTS_REF_DIR
VOXCPM_TTS_REF_AUDIO = TTS_REF_AUDIO
VOXCPM_TTS_REF_META = TTS_REF_META

GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID", "")
GCP_BUCKET_NAME = os.getenv("GCP_BUCKET_NAME", "")

# === Google Cloud Chirp 3 HD（generate_audio_chirp3.py レガシー専用）===
TTS_VOICE_NAME = os.getenv("TTS_VOICE_NAME", "ja-JP-Chirp3-HD-Algieba")
TTS_LANGUAGE_CODE = os.getenv("TTS_LANGUAGE_CODE", "ja-JP")

# === 画像生成プロバイダ ===
# "gemini" | "alibaba"（DashScope 百炼・文生图）| "comfyui"（ComfyUI 自托管 GPU）
IMG_GENERATION_PROVIDER = os.getenv("IMG_GENERATION_PROVIDER", "gemini").strip().lower()
if IMG_GENERATION_PROVIDER not in ("gemini", "alibaba", "comfyui"):
    IMG_GENERATION_PROVIDER = "gemini"

# === Gemini 画像生成（IMG_GENERATION_PROVIDER=gemini）===
GEMINI_IMAGE_MODEL = os.getenv("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image")

# === 阿里云百炼（テキスト生成・画像生成）===
# テキスト: compatible-mode/v1/chat/completions（OpenAI 互換）
# 画像: 参照 https://www.alibabacloud.com/help/zh/model-studio/text-to-image
ALIBABA_API_KEY = os.getenv("ALIBABA_API_KEY", "").strip()
ALIBABA_API_URL = os.getenv(
    "ALIBABA_API_URL", "https://dashscope-intl.aliyuncs.com/api/v1"
).strip().rstrip("/")
ALIBABA_PRO_MODEL = os.getenv("ALIBABA_PRO_MODEL", "qwen-plus").strip()
ALIBABA_FLASH_MODEL = os.getenv("ALIBABA_FLASH_MODEL", "qwen-flash").strip()
ALIBABA_IMAGE_MODEL = os.getenv("ALIBABA_IMAGE_MODEL", "wan2.7-image-pro").strip()

# === GLM（OpenAI 互換・テキスト生成）===
GLM_API_KEY = os.getenv("GLM_API_KEY", "").strip()
GLM_API_URL = os.getenv("GLM_API_URL", "https://api.z.ai/api/coding/paas/v4").strip().rstrip("/")
GLM_MODEL = os.getenv("GLM_MODEL", "glm-4.5").strip()

# 分析ステップ専用のテキスト生成プロバイダ（既定: gemini + GEMINI_PRO_MODEL）
ANALYSIS_TXT_GENERATION_PROVIDER = os.getenv(
    "ANALYSIS_TXT_GENERATION_PROVIDER", "gemini"
).strip().lower()
if ANALYSIS_TXT_GENERATION_PROVIDER not in ("gemini", "xiaomi", "alibaba", "glm"):
    ANALYSIS_TXT_GENERATION_PROVIDER = "gemini"

# TTS テキスト準備（prepare_tts.py）専用: gemini + GEMINI_FLASH_MODEL
PREPARE_TTS_TXT_GENERATION_PROVIDER = os.getenv(
    "PREPARE_TTS_TXT_GENERATION_PROVIDER", "gemini"
).strip().lower()
if PREPARE_TTS_TXT_GENERATION_PROVIDER not in ("gemini", "xiaomi", "alibaba", "glm"):
    PREPARE_TTS_TXT_GENERATION_PROVIDER = "gemini"

# === 参考画像による img2img 生成（無効化済み・コードは残置）===
# 人物参考画像 → ComfyUI img2img は効果が薄く・失敗時に t2i 二重実行で大幅遅延するため既定オフ。
IMAGE_REFERENCE_ENABLED = os.getenv("IMAGE_REFERENCE_ENABLED", "0").strip().lower() in (
    "1", "true", "yes", "on",
)
# img2img の denoise 強度（0.0=入力画像そのまま / 1.0=ほぼ新規生成）
try:
    COMFYUI_IMG2IMG_DENOISE = max(
        0.0, min(1.0, float(os.getenv("COMFYUI_IMG2IMG_DENOISE", "0.55")))
    )
except ValueError:
    COMFYUI_IMG2IMG_DENOISE = 0.55
# 1 記事あたりの参考画像取得数（上位 N 件を候補とし、最初に成功したものを使用）
try:
    IMAGE_REFERENCE_SEARCH_LIMIT = max(1, int(os.getenv("IMAGE_REFERENCE_SEARCH_LIMIT", "5")))
except ValueError:
    IMAGE_REFERENCE_SEARCH_LIMIT = 5
# 画像ダウンロードのタイムアウト（秒）
try:
    IMAGE_REFERENCE_DOWNLOAD_TIMEOUT = max(
        5, int(os.getenv("IMAGE_REFERENCE_DOWNLOAD_TIMEOUT", "30"))
    )
except ValueError:
    IMAGE_REFERENCE_DOWNLOAD_TIMEOUT = 30
# 最小画像サイズ（バイト・小さすぎるサムネイルを弾く）
try:
    IMAGE_REFERENCE_MIN_BYTES = max(
        1024, int(os.getenv("IMAGE_REFERENCE_MIN_BYTES", "20480"))
    )
except ValueError:
    IMAGE_REFERENCE_MIN_BYTES = 20480
# 画像検索の User-Agent（一部サイトが空 UA を弾くため）
IMAGE_REFERENCE_USER_AGENT = os.getenv(
    "IMAGE_REFERENCE_USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36",
).strip()
# SearXNG（自托管 web/image 検索）URL。空なら無効。
# 例: http://localhost:8888
IMAGE_REFERENCE_SEARXNG_URL = os.getenv(
    "IMAGE_REFERENCE_SEARXNG_URL", "http://localhost:8888"
).strip().rstrip("/")
# SearXNG 検索エンジン指定（既定: bing images, duckduckgo images, google images）
IMAGE_REFERENCE_SEARXNG_ENGINES = os.getenv(
    "IMAGE_REFERENCE_SEARXNG_ENGINES", "bing images,duckduckgo images,google images"
).strip()
try:
    IMAGE_REFERENCE_SEARXNG_TIMEOUT = max(
        5, int(os.getenv("IMAGE_REFERENCE_SEARXNG_TIMEOUT", "20"))
    )
except ValueError:
    IMAGE_REFERENCE_SEARXNG_TIMEOUT = 20
# 検索バックエンドの優先順（カンマ区切り）: searxng | wikimedia | bing
# 例: searxng,wikimedia → 先に SearXNG、ダメなら Wikipedia/Wikimedia API
_raw_backends = os.getenv("IMAGE_REFERENCE_SEARCH_BACKENDS", "searxng,wikimedia").strip().lower()
IMAGE_REFERENCE_SEARCH_BACKENDS = [
    b.strip() for b in _raw_backends.split(",") if b.strip() in ("searxng", "wikimedia", "bing")
] or ["wikimedia"]

# === ComfyUI 自托管（IMG_GENERATION_PROVIDER=comfyui）===
# Mac 原生 ComfyUI + FLUX.2-klein GGUF（MPS）・SSH 経由（既定: cho@rw-mac-1）
COMFYUI_REMOTE_HOST = os.getenv("COMFYUI_REMOTE_HOST", "cho@rw-mac-1").strip()
COMFYUI_DIR = os.getenv("COMFYUI_DIR", "/Users/cho/comfyui/ComfyUI").strip()
# venv は ComfyUI リポジトリ直下ではなく親ディレクトリ（例: /Users/cho/comfyui/.venv）
COMFYUI_VENV = os.getenv("COMFYUI_VENV", "/Users/cho/comfyui/.venv").strip()
COMFYUI_OUTPUT_DIR = os.getenv(
    "COMFYUI_OUTPUT_DIR", "/Users/cho/comfyui/ComfyUI/output"
).strip()
COMFYUI_VAE_NAME = os.getenv("COMFYUI_VAE_NAME", "ae.safetensors").strip()
try:
    COMFYUI_API_PORT = max(1, int(os.getenv("COMFYUI_API_PORT", "8188")))
except ValueError:
    COMFYUI_API_PORT = 8188
# 後方互換（旧 GCE Docker 構成・Mac SSH では未使用）
COMFYUI_REMOTE_ZONE = os.getenv("COMFYUI_REMOTE_ZONE", "us-central1-b").strip()
COMFYUI_REMOTE_PROJECT = os.getenv("COMFYUI_REMOTE_PROJECT", "").strip()
COMFYUI_DOCKER_DIR = os.getenv("COMFYUI_DOCKER_DIR", "~/comfyui-flux2").strip()
try:
    COMFYUI_STEPS = max(1, int(os.getenv("COMFYUI_STEPS", "4")))
except ValueError:
    COMFYUI_STEPS = 4
try:
    COMFYUI_IMAGE_WIDTH = max(256, int(os.getenv("COMFYUI_IMAGE_WIDTH", "768")))
except ValueError:
    COMFYUI_IMAGE_WIDTH = 768
try:
    COMFYUI_IMAGE_HEIGHT = max(256, int(os.getenv("COMFYUI_IMAGE_HEIGHT", "1024")))
except ValueError:
    COMFYUI_IMAGE_HEIGHT = 1024
# ComfyUI 1 ジョブの最大待機（秒）。FLUX t2i は Mac MPS で通常 1〜3 分。
# DNS/SSH 一時障害のバッファ込みで既定 600。
try:
    COMFYUI_GENERATION_TIMEOUT = max(
        120, int(os.getenv("COMFYUI_GENERATION_TIMEOUT", "600"))
    )
except ValueError:
    COMFYUI_GENERATION_TIMEOUT = 600
# SSH 経由 curl の最大待機（秒）。ComfyUI 処理中に API が応答遅延しても SSH が固まらないよう短く保つ
try:
    COMFYUI_CURL_MAX_TIME = max(5, int(os.getenv("COMFYUI_CURL_MAX_TIME", "15")))
except ValueError:
    COMFYUI_CURL_MAX_TIME = 15

# === ポッドキャスト制作パラメータ ===
EPISODE_TARGET_MINUTES = (45, 70)  # エピソードの目標時間範囲（分）
EPISODE_MAX_ARTICLES = 8  # 1エピソードあたりの最大記事数（自動グループ用）
ARTICLE_TARGET_MINUTES = (4, 8)  # 各記事の目標朗読時間（分）
CHARS_PER_MINUTE_JA = 350  # 日本語の通常朗読速度（文字/分）
DROP_BOTTOM_PERCENT = 0.10  # 除外する低スコア記事の割合
# 記事分析（analyze_content）の1リクエストあたり記事数（RAW ブロック単位で分割）
# 大きくするほど API 呼び出し回数が減り RPM 制限に強くなるが、1回あたりの入力が大きくなる
try:
    ANALYSIS_BATCH_SIZE = max(1, int(os.getenv("ANALYSIS_BATCH_SIZE", "20")))
except ValueError:
    ANALYSIS_BATCH_SIZE = 20
# Gemini 等の RPM 制限対策: 連続呼び出しの最小間隔（秒）
try:
    ANALYSIS_API_MIN_INTERVAL_SEC = max(
        0, float(os.getenv("ANALYSIS_API_MIN_INTERVAL_SEC", "30"))
    )
except ValueError:
    ANALYSIS_API_MIN_INTERVAL_SEC = 30.0
# 分析 API のリトライ設定（429/5xx や一時的な失敗の対策）
try:
    ANALYSIS_MAX_RETRIES = max(0, int(os.getenv("ANALYSIS_MAX_RETRIES", "3")))
except ValueError:
    ANALYSIS_MAX_RETRIES = 3
# リトライ1回目の待機時間（秒）・2回目以降は指数バックオフで倍増
try:
    ANALYSIS_RETRY_BASE_WAIT_SEC = max(
        1, float(os.getenv("ANALYSIS_RETRY_BASE_WAIT_SEC", "60"))
    )
except ValueError:
    ANALYSIS_RETRY_BASE_WAIT_SEC = 60.0
# prepare_tts の Gemini RPM 制限対策（15 RPM → 最低 4 秒/回）
try:
    PREPARE_TTS_API_MIN_INTERVAL_SEC = max(
        0, float(os.getenv("PREPARE_TTS_API_MIN_INTERVAL_SEC", "4"))
    )
except ValueError:
    PREPARE_TTS_API_MIN_INTERVAL_SEC = 4.0

# 派生定数（自動計算）
ARTICLE_TARGET_CHARS = (
    ARTICLE_TARGET_MINUTES[0] * CHARS_PER_MINUTE_JA,
    ARTICLE_TARGET_MINUTES[1] * CHARS_PER_MINUTE_JA,
)
EPISODE_TARGET_CHARS = (
    EPISODE_TARGET_MINUTES[0] * CHARS_PER_MINUTE_JA,
    EPISODE_TARGET_MINUTES[1] * CHARS_PER_MINUTE_JA,
)

# === 日本人向け関心度スコア基準 ===
RELEVANCE_TIERS_DESC = {
    1: "日本関連、中国関連、米国関連",
    2: "地政学、グローバル経済、金融投資、ハイテク、サプライチェーン安全保障、AI、ロボティクス、アジア・新興国市場、大人向け消費",
    3: "アニメ、ゲーム、教育、健康、文化、宗教、民族、観光、ナショナリズム",
    4: "その他、欧州主要国関連",
    5: "イギリス国内関連",
}

# === The Economistのセクション類似度マッピング（エピソード分組用）===
# 類似するセクションをグループ化して、短いセクション同士を統合する際の基準にする
SECTION_AFFINITY = {
    "The world this week": "opinion",
    "Leaders": "opinion",
    "Briefing": "opinion",
    "Letters": "opinion",
    "Essay": "opinion",
    "By Invitation": "opinion",
    "United States": "americas",
    "The Americas": "global",
    "Asia": "asia_pacific",
    "China": "China",
    "Middle East and Africa": "global",
    "Middle East & Africa": "global",
    "International": "global",
    "Europe": "europe",
    "Britain": "global",
    "Business": "business_finance",
    "Finance & economics": "business_finance",
    "Finance and economics": "business_finance",
    "Science & technology": "science_culture",
    "Science and technology": "science_culture",
    "Culture": "science_culture",
    "Books & arts": "science_culture",
    "Books and arts": "science_culture",
    "Obituary": "other",
    "Graphic detail": "other",
    "Economic & financial indicators": "business_finance",
    "Economic and financial indicators": "business_finance"
}

# === セクション名の日英対訳マッピング ===
SECTION_JP_MAPPING = {
    "The world this week": "今週の世界",
    "Leaders": "リーダーズ",
    "Briefing": "ブリーフィング",
    "Letters": "読者の手紙",
    "By Invitation": "寄稿",
    "United States": "米国",
    "The Americas": "中南米",
    "Asia": "アジア",
    "China": "中国",
    "Middle East and Africa": "中東・アフリカ",
    "Middle East & Africa": "中東・アフリカ",
    "International": "国際",
    "Europe": "ヨーロッパ",
    "Britain": "英国",
    "Business": "ビジネス",
    "Finance & economics": "金融・経済",
    "Finance and economics": "金融・経済",
    "Science & technology": "科学・技術",
    "Science and technology": "科学・技術",
    "Culture": "カルチャー",
    "Books & arts": "書籍・芸術",
    "Books and arts": "書籍・芸術",
    "Obituary": "追悼",
    "Essay": "寄稿",
    "Graphic detail": "グラフィック・ディテール",
    "Economic & financial indicators": "経済・金融",
    "Economic and financial indicators": "経済・金融"
}


def normalize_economist_section(section: str) -> str:
    """
    誌面見出しが「Leaders | Defeating Viktor」のように大分類＋副題の形式のとき、
    大分類（パイプの左側）のみを返す。SECTION_AFFINITY / SECTION_JP_MAPPING と整合させる。
    「Finance & economics」の & はそのまま残す（パイプが無ければ変更しない）。
    """
    if not isinstance(section, str):
        return section
    s = section.strip()
    if "|" not in s:
        return s
    main = re.split(r"\s*\|\s*", s, maxsplit=1)[0].strip()
    return main if main else s


def ensure_section_mapping(section: str) -> None:
    """
    セクション名に対するマッピングが未定義の場合に、自動的に安全なデフォルト値を追加する。
    - SECTION_AFFINITY: 未定義なら "other" グループに分類
    - SECTION_JP_MAPPING: 未定義なら元の英語名をそのまま使用
    """
    updated = False

    if section not in SECTION_AFFINITY:
        SECTION_AFFINITY[section] = "other"
        updated = True

    if section not in SECTION_JP_MAPPING:
        SECTION_JP_MAPPING[section] = section
        updated = True

    if updated:
        # 将来新しいセクションが追加された場合でも処理が落ちないようにするためのログ
        print(f"[情報] 新しいセクションを自動登録しました: '{section}' → affinity='other', jp='{SECTION_JP_MAPPING[section]}'")


def ensure_section_mappings(sections: list[str]) -> None:
    """複数セクションに対して ensure_section_mapping を一括適用するヘルパー"""
    for s in sections:
        ensure_section_mapping(s)


def get_issue_dir(issue_date: str) -> Path:
    """指定号のベース出力ディレクトリを取得"""
    return BASE_OUTPUT_DIR / issue_date


def get_episode_dir(issue_date: str, episode_num: int) -> Path:
    """指定エピソードの出力ディレクトリを取得"""
    return get_issue_dir(issue_date) / "episodes" / f"{episode_num:02d}"
