# Episode Orchestrator

このツールは番組構成をコードで所有します。LLM は日本語台本の作成だけを担当し、
順序・固定資産・検証・レンダリング先は Python が決定します。

## 実行

```powershell
python -B -X utf8 tools/orchestrator/build_pipeline.py scaffold --date YYYY-MM-DD
python -B -X utf8 tools/orchestrator/build_pipeline.py validate --date YYYY-MM-DD
python -B -X utf8 tools/orchestrator/build_pipeline.py build-map --date YYYY-MM-DD
python -B -X utf8 tools/orchestrator/build_pipeline.py check-artifacts --date YYYY-MM-DD
python -B -X utf8 tools/orchestrator/build_pipeline.py run --date YYYY-MM-DD --render
```

`run --render` は音声準備と Remotion 組立を行い、成片を
`daily-output/<date>/episode.mp4` へ出力します。`--render` を付けない場合は、
実行予定コマンドだけを表示します。

## 分段増分 TTS

原稿が一部固定できた時点で、その分だけ地図と TTS を先回しできます
（`durations.json` は既存セグメントを保持したまま結合されます）。

```powershell
python -B -X utf8 tools/orchestrator/build_pipeline.py build-map --date YYYY-MM-DD --only draft-A
python -B -X utf8 tools/orchestrator/build_pipeline.py commands --date YYYY-MM-DD --only draft-A
# 出力された prepare_tts / generate_audio コマンドをそのまま実行
```

`--only` には block id（例: `draft-A` `draft-B1`）を渡します。視覚 HTML が無い段階では
partial マップで TTS だけを進め、Remotion 前処理は全稿確定後に行います。

## 所有範囲

| レイヤー | 責務 |
|----------|------|
| Python | ブロック順序、固定 opening/ending 契約、TTS セグメント整合、`remotion_input.json` 検証、レンダリング先 |
| LLM | 日本語の選題分析、ニュース要約、テーマ原稿、予告文などの自然文作成 |

日次は必ず `scaffold` から開始する。`scaffold` は放送日で契約を判定し、2026-09-17 以降は
`END-card` と `END-disclaimer` を含む 3 個の fixed slots を生成する。

## 変換が失敗した場合

TTS の `durations.json` が壊れた場合は、全 WAV から再構築できます。

```powershell
python -B -X utf8 tools/tts/reconstruct_durations.py YYYY-MM-DD
```
