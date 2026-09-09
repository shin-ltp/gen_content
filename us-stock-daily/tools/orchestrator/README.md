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

## 所有範囲

| レイヤー | 責務 |
|----------|------|
| Python | ブロック順序、固定 opening/ending 契約、TTS セグメント整合、`remotion_input.json` 検証、レンダリング先 |
| LLM | 日本語の選題分析、ニュース要約、テーマ原稿、俳句などの自然文作成 |

## 変換が失敗した場合

TTS の `durations.json` が壊れた場合は、全 WAV から再構築できます。

```powershell
python -B -X utf8 tools/tts/reconstruct_durations.py YYYY-MM-DD
```
