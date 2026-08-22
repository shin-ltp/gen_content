---
name: economist-podcast
description: 『The Economist』誌の電子版（PDF/EPUB）からテキストを抽出し、日本のリスナー向けポッドキャスト（日本語音声＋YouTube動画）を自動制作するワークフロースキル
---

# The Economist ポッドキャスト制作スキル

## 概要

『The Economist』誌（PDF/EPUB）から日本のリスナー向けポッドキャストを自動制作する
エンドツーエンドのワークフロー。記事の分析・改写・エピソード編成・挿絵生成・
音声合成・動画制作の全工程を自動化し、各ステップでユーザーの確認・修正が可能。

制作は **主プロセス + 3ワーカー** 構成で並列実行される。

---

## アーキテクチャ

```
主プロセス（起動・監視・進捗表示）
 ├─ Worker 1 [resources]  リソース生成
 │    Phase A: process_source → analyze_content → [WebUI確認]
 │             → rewrite_content → group_episodes → [WebUI確認]
 │    Phase B: prepare_tts（全エピソードをループ）
 │    Phase C: generate_images（全エピソードをループ）  ← Worker 2 と並行
 │    Phase D: audio完了を監視 → renderable フラグ付与  ← Worker 3 に通知
 │
 ├─ Worker 2 [audio]  音声合成
 │    tts_ready フラグをポーリング → generate_audio（エピソードごと）
 │
 └─ Worker 3 [render]  レンダリング・アップロード
      renderable フラグをポーリング → generate_video → remotionレンダー
      → render_thumbnail → upload_youtube（1エピソードずつ直列）
```

### ワーカー間 IPC（プロセス間通信）

`episode_progress.json` を共有状態ファイルとして使用。各ワーカーは担当フィールドのみ書き込む。
書き込みはアトミック（`.tmp` 経由の `os.replace()`）。

| ワーカー | 書き込むフィールド |
|---------|--------------|
| Worker 1 | `prepare_tts`, `tts_ready`, `generate_images`, `renderable` |
| Worker 2 | `generate_audio` |
| Worker 3 | `generate_video`, `render_video`, `render_thumbnail`, `upload_youtube` |
| 全員 | `_meta`（`p1_status`, `episodes_defined`, `webui_url` 等） |

**シグナルフロー**:
1. Worker 1 が `prepare_tts` 完了 → `tts_ready=True` → Worker 2 が検知して音声合成開始
2. Worker 1 が `generate_images` 完了 かつ Worker 2 が `generate_audio` 完了 → `renderable=True` → Worker 3 が検知してレンダリング開始

---

## ワークフロー詳細

### Worker 1 — Phase A: 前処理（逐次・2回のWebUI確認あり）

#### 1. テキスト抽出 (`EXTRACT_TEXT`)
- PDF/EPUB からテキスト抽出・表紙画像保存

#### 2. 記事分析・スコアリング (`ANALYZE_ARTICLES`)
- Gemini API で各記事を識別・分類
- 日本人向け関心度を5段階で評価（第1〜5档）
- スコア最低の10%を除外対象候補としてマーク

#### 3. 記事分析レビュー (`REVIEW_ANALYSIS`) — **WebUI確認**
- ブラウザが自動で開く（または表示されたURLを開く）
- 左列: DROP 記事、右列: KEEP 記事。各カードでDROP⇔KEEP を切り替え可能
- 「保存」→「確認」でこのステップを完了

#### 4. 記事改写 (`REWRITE_ARTICLES`)
- 各記事を日本語ポッドキャスト原稿に改写（NHK・日経等の解説番組に匹敵する文体）
- 第三者的な視点での記述 / Markdown Front Matter 付与
- 純粋な記事内容のみ（挨拶・導入・締めはTTS準備時に追加）

#### 5. エピソード分組・確認 (`GROUP_EPISODES`) — **WebUI確認**
- セクション類似度に基づいて45〜70分のエピソードにグループ化
- `episodes_plan.json` を出力
- ブラウザが自動で開く。ドラッグ＆ドロップで記事を再編成可能
- 「保存」→「確認」で `metadata.json` を生成し、Worker 2/3 が開始可能になる

### Worker 1 — Phase B〜D: エピソード準備

#### Phase B: TTS テキスト準備（全エピソード、逐次）
- 各記事をTTS用台本に変換（Gemini API 使用）
  - チャンネル紹介、番組紹介、転換文を自動挿入
  - 英語のカタカナ化、口語化、記号除去
  - 休止は `[pause short]` / `[pause long]` で指定
- 各エピソード完了時点で `tts_ready=True` → Worker 2 が即座に音声合成を開始

#### Phase C: 挿絵生成（全エピソード、Worker 2 と並行）
- カバーストーリーには雑誌表紙画像を使用
- その他の記事は **Gemini 2.5 Flash Image** で統一スタイルの縦型挿絵を生成

#### Phase D: renderable フラグ付与（ポーリング）
- `generate_images == completed` かつ `generate_audio == completed` の条件が揃ったエピソードに
  `renderable=True` を付与 → Worker 3 がレンダリングを開始

### Worker 2 — 音声合成（ポーリングループ）

- `tts_ready=True` のエピソードを検知 → `generate_audio.py` を実行
- TTS バックエンド: `.env` の `TTS_BACKEND`（`orchestrate` / `generate_audio` 共通）または CLI `--tts-backend`
  - **qwen**（既定）: Qwen3-TTS voice clone — llm-spot GPU 上で远程 batch（`qwen_tts_batch.py`）
  - **gemini**: Google Cloud Text-to-Speech（Gemini TTS）
  - **fish**: Fish Audio S1（レガシー・非推奨）
- TTSテキストを `[pause long]`・`[pause short]`・句点（。）で分片
- 各分片を WAV/MP3 で生成 → 正規化・無音を挟んで連結 → MP3出力
- 作業ディレクトリ（`audio_work/`）に `segments.json` と個別WAVを保存し、再実行時に再利用

### Worker 3 — レンダリング・アップロード（ポーリングループ）

- `renderable=True` のエピソードを検知 → 以下を1エピソードずつ直列実行
  1. **`generate_video.py`** — 音声・画像を `remotion/public/` に配置し `remotion_input.json` を生成
  2. **`npx remotion render`** — MP4 動画をレンダリング → `episodes/{id}/video/episode_{YYYY-MM-DD}_{id}.mp4`
  3. **`npx remotion still`** — サムネイルを生成 → `episodes/{id}/video/thumbnail_{YYYY-MM-DD}_{id}.jpg`
  4. **`upload_youtube.py`** — 動画・サムネイルをYouTubeにアップロード（失敗しても継続）

> **注意**: `generate_video` は `remotion/public/` を全消去して再構築するため、
> エピソードは必ず直列処理する。再起動時にも `generate_video → render` の整合性を自動チェックする。

---

## 使用方法

### 事前準備

```bash
pip install -r .cursor/skills/economist-podcast/requirements.txt
# .cursor/skills/economist-podcast/.env を作成してAPIキーを設定
# contents/audiobook/source/ にPDF/EPUBを配置（ファイル名にYYYY-MM-DDを含む）
```

### 基本コマンド

```bash
# ── 通常実行（全ワーカーを起動し進捗を表示）──
python .cursor/skills/economist-podcast/scripts/orchestrate.py --issue 2026-02-07

# ── 別ターミナルから進捗確認（いつでも）──
python .cursor/skills/economist-podcast/scripts/orchestrate.py --issue 2026-02-07 --status
```

### クラッシュ・中断後の再開

各ワーカーは独立して再起動できる。起動時に stale な `in_progress` 状態を自動リセットし、
完了済みのステップはスキップして再開する。

```bash
# Worker 1（リソース生成）を単体で再起動
python .cursor/skills/economist-podcast/scripts/orchestrate.py --issue 2026-02-07 --worker resources

# Worker 2（音声合成）を単体で再起動
python .cursor/skills/economist-podcast/scripts/orchestrate.py --issue 2026-02-07 --worker audio

# Worker 3（レンダリング）を単体で再起動
python .cursor/skills/economist-podcast/scripts/orchestrate.py --issue 2026-02-07 --worker render
```

> **ログファイル**: `contents/audiobook/output/TheEconomist/{YYYY-MM-DD}/p_resources.log` 等に
> 各ワーカーの詳細ログが保存される。主プロセスの進捗表示画面にも末尾2行が表示される。

### 特定ステップからやり直し

```bash
# 前処理ステップからリセット（それ以降の status.json をクリア）
python .cursor/skills/economist-podcast/scripts/orchestrate.py --issue 2026-02-07 --from EXTRACT_TEXT
python .cursor/skills/economist-podcast/scripts/orchestrate.py --issue 2026-02-07 --from ANALYZE_ARTICLES
python .cursor/skills/economist-podcast/scripts/orchestrate.py --issue 2026-02-07 --from REVIEW_ANALYSIS
python .cursor/skills/economist-podcast/scripts/orchestrate.py --issue 2026-02-07 --from REWRITE_ARTICLES
python .cursor/skills/economist-podcast/scripts/orchestrate.py --issue 2026-02-07 --from GROUP_EPISODES

# ワーカーの制作進捗をリセット（episode_progress.json の該当フィールドをクリア）
python .cursor/skills/economist-podcast/scripts/orchestrate.py --issue 2026-02-07 --reset-worker resources
python .cursor/skills/economist-podcast/scripts/orchestrate.py --issue 2026-02-07 --reset-worker audio
python .cursor/skills/economist-podcast/scripts/orchestrate.py --issue 2026-02-07 --reset-worker render
```

> `--from GROUP_EPISODES` 以前をリセットすると、`episode_progress.json` の `_meta` フラグ
> （`episodes_defined` 等）も自動的にクリアされる。制作進捗（音声・動画等）はそのまま保持される。

### 特定ワーカーのみ起動

```bash
# Worker 1/2 のみ起動（レンダリングは後で行う）
python .cursor/skills/economist-podcast/scripts/orchestrate.py \
  --issue 2026-02-07 --workers resources audio
```

### 個別スクリプトの直接実行

```bash
python .cursor/skills/economist-podcast/scripts/process_source.py 2026-02-07
python .cursor/skills/economist-podcast/scripts/analyze_content.py 2026-02-07
python .cursor/skills/economist-podcast/scripts/rewrite_content.py 2026-02-07
python .cursor/skills/economist-podcast/scripts/group_episodes.py 2026-02-07
python .cursor/skills/economist-podcast/scripts/generate_images.py 2026-02-07
python .cursor/skills/economist-podcast/scripts/prepare_tts.py 2026-02-07
python .cursor/skills/economist-podcast/scripts/generate_audio.py 2026-02-07
python .cursor/skills/economist-podcast/scripts/generate_audio.py 2026-02-07 --tts-backend gemini
python .cursor/skills/economist-podcast/scripts/generate_video.py 2026-02-07
python .cursor/skills/economist-podcast/scripts/upload_youtube.py --issue 2026-02-07 --episode 01
```

### YouTube アップロード

- **手動実行**（推奨）: トークンが期限切れ・無効の場合はブラウザが開き、再認証後にアップロードが続行する。
  ```bash
  python .cursor/skills/economist-podcast/scripts/upload_youtube.py --issue 2026-02-07 --episode 01
  python .cursor/skills/economist-podcast/scripts/upload_youtube.py --issue 2026-02-07 --episode 02 --privacy unlisted
  ```
- **Worker 3 からの自動実行**: `non_interactive` モードで呼ばれる。トークンが無効な場合はアップロードをスキップし、警告を記録して後続ステップへ進む（ブラウザは開かない）。
- **トークン**: `youtube_token.json` が期限切れ・revoke された場合、手動で上記コマンドを実行すると再認証フローが走り、新しいトークンが保存される。
- 環境変数 `YOUTUBE_NON_INTERACTIVE=1` を設定すると、CLI から実行する場合も「認証が必要ならスキップ」となる。

### 音声セグメント GUI エディタ

```bash
# GUIエディタ起動（セグメントの可視化・テキスト編集・再生成・挿入・分割）
python .cursor/skills/economist-podcast/scripts/audio_editor_gui.py 2026-02-21 -e 01 -a 01

# generate_audio.py からも起動可能
python .cursor/skills/economist-podcast/scripts/generate_audio.py 2026-02-21 -e 01 -a 01 --gui
```

主な機能:
- セグメント一覧を状態別に色分け表示（OK / 未生成 / エラー / 無音）
- テキスト編集 → 該当セグメントのみ再生成（他の分片に影響なし）
- 任意位置への新規セグメント挿入 / カーソル位置でのセグメント分割
- セグメントの削除・並べ替え・音声再生
- 全セグメント結合 → MP3 出力

---

## ディレクトリ構造

### スキルファイル

```
.cursor/skills/economist-podcast/
├── SKILL.md
├── requirements.txt
├── .env                       # 環境変数（要作成、gitignore対象）
├── youtube_client.json        # YouTube OAuth クライアント（要配置）
├── youtube_token.json         # YouTube OAuth トークン（初回認証後に自動生成）
└── scripts/
    ├── config.py              # 共通設定・定数・環境変数
    ├── state_manager.py       # 前処理ステップの状態管理（status.json）
    ├── webui_server.py        # WebUI サーバー（記事確認・エピソード編集）
    ├── orchestrate.py         # 主プロセス + 3ワーカー統合管理
    ├── process_source.py      # テキスト・表紙抽出（PDF/EPUB）
    ├── analyze_content.py     # 記事分析・スコアリング
    ├── rewrite_content.py     # 記事改写
    ├── group_episodes.py      # エピソード分組・metadata.json 生成
    ├── generate_images.py     # 挿絵生成（Gemini 2.5 Flash Image）
    ├── prepare_tts.py         # TTS 用テキスト準備・導入文生成
    ├── tts_backends.py        # TTS バックエンド抽象化（Fish / Gemini）
    ├── generate_audio.py      # 音声生成・分片管理・WAV 結合
    ├── audio_editor_gui.py    # 音声セグメント GUI エディタ
    ├── generate_video.py      # Remotion 用データ準備（remotion_input.json）
    ├── upload_youtube.py      # YouTube アップロード（OAuth・非対話モード対応）
    ├── generate_audio_chirp3.py  # Chirp 3 HD 補助
    ├── generate_x_share.py    # X（Twitter）投稿補助
    └── backfill_youtube_stub.py  # YouTube メタデータ後付け補助
```

### 出力ファイル

```
contents/audiobook/output/TheEconomist/{YYYY-MM-DD}/
├── status.json                    # 前処理ステップの完了状態
├── episode_progress.json          # エピソード制作進捗（ワーカー間共有状態）
│   ├── _meta                      # 全体メタ（episodes_defined, webui_url 等）
│   └── "01", "02", ...            # エピソードごとの各サブステップ状態
├── p_resources.log                # Worker 1 ログ
├── p_audio.log                    # Worker 2 ログ
├── p_render.log                   # Worker 3 ログ
├── raw/                           # 章ごとの生テキスト（001.txt, 002.txt ...）
├── raw_text.txt                   # 全文（互換用）
├── extraction_meta.json
├── cover.{jpg|png}
├── analysis.json                  # 記事分析結果（WebUI で確認・編集）
├── episodes_plan.json             # エピソード編成計画（WebUI で確認・編集）
├── articles/                      # 改写済み個別記事（Markdown）
│   ├── 001.md, 002.md, ...
└── episodes/
    └── 01/
        ├── metadata.json
        ├── tts/                   # TTS 用プレーンテキスト
        │   ├── intro.txt
        │   ├── 01.txt, 02.txt, ...
        │   └── closing.txt
        ├── audio/                 # 最終音声（MP3）
        │   ├── intro.mp3
        │   ├── 01.mp3, 02.mp3, ...
        │   └── closing.mp3
        ├── audio_work/            # 音声生成作業ディレクトリ
        │   └── 01/
        │       ├── segments.json
        │       ├── seg_0000.wav, seg_0001.wav, ...
        │       └── combined.wav
        ├── images/
        │   ├── 01.png, 02.png, ...
        └── video/
            ├── episode_{YYYY-MM-DD}_{id}.mp4
            └── thumbnail_{YYYY-MM-DD}_{id}.jpg
```

---

## 環境変数

`.cursor/skills/economist-podcast/.env`:

```env
# === Gemini API（記事分析・改写・TTS準備・挿絵生成に使用）===
GEMINI_API_KEY=your-gemini-api-key
GEMINI_PRO_MODEL=gemini-2.5-pro        # テキスト生成用（分析・改写等）
GEMINI_FLASH_MODEL=gemini-2.0-flash    # 軽量タスク用（音声検証リトライ等）

# === 音声生成 TTS バックエンド ===
# qwen（既定・推奨）| gemini | fish（レガシー）
TTS_BACKEND=qwen

# === Qwen3-TTS（TTS_BACKEND=qwen 時・llm-spot GPU）===
# QWEN_TTS_REMOTE_HOST=cho@llm-spot
# QWEN_TTS_REMOTE_ZONE=us-central1-b
# QWEN_TTS_REMOTE_PROJECT=fuzoku-sns
# QWEN_TTS_REF_DIR=hosting_ai/qwen-tts/tests/2026-05-30-voice-clone

# === Google Cloud TTS（TTS_BACKEND=gemini 時）===
GCP_PROJECT_ID=your-gcp-project-id
GCP_BUCKET_NAME=your-gcs-bucket-name
TTS_MODEL_NAME=gemini-2.5-pro-tts
TTS_VOICE_NAME=ja-JP-Chirp3-HD-Algieba
TTS_LANGUAGE_CODE=ja-JP
# Gemini TTS 用ナレーション・プロンプト（空の場合はデフォルト）
# TTS_PROMPT=

# === YouTube アップロード（任意）===
# 公開設定: private | unlisted | public（未設定時は private）
# YOUTUBE_PRIVACY_STATUS=private
# 非対話モード（認証が必要な場合はスキップ）。Worker 3 からは自動設定
# YOUTUBE_NON_INTERACTIVE=1

# === X（Twitter）投稿（任意）===
# X_CLIENT_ID=
# X_CLIENT_SECRET=
# X_ACCESS_TOKEN=
# X_ACCESS_SECRET=
```

YouTube アップロード用に `youtube_client.json`（OAuth 2.0 クライアント）をスキルルートに配置する。
初回認証後に `youtube_token.json` が自動生成される。トークンが無効になった場合は手動で
`upload_youtube.py --issue ... --episode ...` を実行すると再認証できる。

---

## 進捗ダッシュボード（表示例）

```
================================================================
  The Economist 2026-03-15  制作ダッシュボード
================================================================
  Worker 1 [リソース生成]   running:generate_images:02
  Worker 2 [音声合成]       running:audio:01
  Worker 3 [レンダリング]   waiting
----------------------------------------------------------------
   EP   TTS  画像  音声  動画準  レン    UP  状態
   01     ✓     ✓     ✓     -     -     -  TTS完了
   02     ✓     ▶     ▶     -     -     -  処理中
   03     ✓     -     -     -     -     -  待機中
----------------------------------------------------------------
  [W1] [EP 02] 挿絵生成...
  [W2] [Worker 2] EP 01 音声合成 開始...
================================================================
  更新: 14:23:05  (5秒ごとに自動更新)
```

WebUI 確認が必要な場合は URL が表示される:
```
  ⚠  ブラウザで確認が必要です: 記事分析レビュー
     URL: http://localhost:8765/
```
