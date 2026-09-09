# us-stock-daily Remotion 環境

音声駆動の番組動画レンダリング用 Remotion プロジェクト（環境構築完了）。
タイムラインは production/audio/durations.json（TTS 実測長）駆動。

## セットアップ済み

- Remotion 4.0.427 / React 19 / TypeScript（npm install 済み）
- src/Episode.tsx: durations.json ベースのセグメント合成 + フェーディング間隔
  - BGM はRemotion 側で鳴らさない。開幕・終幕・転場 sting は generate_audio.py が
    各セグメント WAV へ予めミックス済み（voice-driven 音声駆動アーキテクチャ）
  - 開幕: S00-intro WAV = BGM 1 秒 → 番組紹介 → 3 秒フェードアウト（計約 10 秒）
  - 終幕: S39-greeting WAV = 挨拶 → BGM 余韻 5 秒（計約 25 秒）。
    speechEndSec（挨拶終了秒）で EndCard が s35 上へフェードイン
  - 転場: コーナー先頭 WAV 冒頭に sting 4.8 秒 + 間 1 秒を焼き込み済み。
    画面はフェードパッド中に切替済みのため、sting → 1 秒 → 語り開始で同期
- 検証済み: npx tsc --noEmit PASS / still 描画 PASS（桩 durations で通し確認）

## エピソード投入手順

```powershell
cd us-stock-daily/remotion

# 1. TTS 合成（Mac fish audio 環境 / BGM ミックス・sting 前導は自動）
python ..\tools\tts\generate_audio.py 2026-08-28

# 2. 素材注入（visual.html スクリーンショット + audio + bgm + remotion_input.json）
python ..\tools\remotion\prepare_remotion.py --issue 2026-08-28

# 3. Studio プレビュー / レンダリング
npm run dev
npx remotion render Episode out/episode.mp4 --props=public/remotion_input.json
npx remotion still Episode out/check.png --frame=600 --props=public/remotion_input.json
```

## データ仕様

- 入力: public/remotion_input.json（BOM なし = webpack JSON.parse 互換）
  - segments[]: order / id / slide / image / audio / durationSec / timingSource /
    title / corner / sting / sentences[]（句単位 start・end はセグメント内秒）
    ※ durationSec は BGM ミックス済み WAV の実長。S39-greeting のみ speechEndSec を持つ
- 視覚: visual.html の各 swrap id=sN（1920x1080）を headless Chrome で PNG 化。
  s2（四問カルーセル idx0-3）・s3（内容ブロック切替）・s33（ニュース強調）は
  キュー状態別のバリアント PNG を生成
- public/ は prepare_remotion.py が毎回再生成（git 管理外）
