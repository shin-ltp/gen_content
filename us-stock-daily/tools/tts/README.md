# us-stock-daily TTS pipeline

Phase 5 音声層: 内容原稿 (draft-A/B/C/D) → 播音稿切分 → Fish Audio 合成 → Remotion 用音声 + 时长清单。

**默认引擎: 本机 WSL2 + Fish S2-Pro int8 + torch.compile (稳态约 320ms/token, 比 Mac MLX 快约 4 倍)。**
本地服务器不可达时 `auto` 模式自动回落到 Mac MLX (SSH)，行为与旧版一致。

## Pipeline

```
production/segment-map.json      # 人工维护: slide ↔ 旁白 ↔ 声音 ↔ cue 的切分映射
        │
        ▼  prepare_tts.py
production/tts/NNN_<id>.txt      # Fish-safe 日语 (数字汉字化 / 缩写片假名化 / [pause] 标记)
production/tts/manifest.json     # 机器可读清单 (供 generate_audio 与 Remotion)
production/tts/segments.md       # 人工校对表
        │
        ▼  generate_audio.py     # 切句 → 逐句 HTTP 合成 (默认 WSL2 本地, 可回落 Mac SSH) → 静音拼接
production/audio_work/NNN_<id>/  # 逐句 WAV (可断点续传)
production/audio/NNN_<id>.wav    # 每个内容块一条 WAV (44.1kHz mono 16bit)
production/audio/durations.json  # 逐句 start/end/duration → Remotion 精确对轨
```

> 本地拼接优先用 ffmpeg；若未安装则自动回退到 Python 标准库 `wave` 直接拼接
> PCM（要求 Fish worker 返回的 WAV 参数一致，正常情况均满足）。

## 分段増分 TTS（partial workflow）

原稿が一部固定できた段階で、その分だけ先に合成できます。`segment-map.json` が
完成 block のみを含む partial 版のときは `--partial` を付けます（視覚 HTML を
要求しません）。`durations.json` は既存セグメントを保持したまま増分結合します。

```powershell
python -B -X utf8 tools/orchestrator/build_pipeline.py build-map --date YYYY-MM-DD --only draft-A
python -B -X utf8 tools/tts/prepare_tts.py YYYY-MM-DD --partial
python -B -X utf8 tools/tts/generate_audio.py YYYY-MM-DD --only draft-A
```

## 切分规则 (影音同步的关键)

- **页面切换 = 独立文件**: 现行契约使用 `visual.html`，S0 是固定标题卡；
  2026-09-19 起 A-p1..A-pN 共享 s1 一览页，但每个预告仍是独立 TTS 文件，
  并在音频时长驱动的 timeline 中切换 s1 的标题行和主题图。
- **页内切换 = 独立文件**: 旧契约的 S2 四问轮播、S3 市况页、S22 新闻和 S31
  事件页仅在历史回放中保留。当前契约按 segment-map 的页面边界切段。
- **文件名含编号**: `NNN_内容ID.txt`，页间编号留 10 的间隔 (040, 050, ...)，
  后期可在间隔处插入 BGM、节目介绍等外部音频; 页内子段 +1 递增。
- **外部槽位**: `type: "external"` (S00 片头、END 片尾) 只占编号不合成，由后期素材填充。
- **声音映射**: 俳句 S01 已于 2026-09-17 废除；新契约下全部 = `xiaomei`，写入 segment-map 的 `voice` 字段。

## Fish Audio 对策

- **间隔控制**: `[pause long]` / `[pause short]` 标记不会送给 Fish，切句时剥离并在
  拼接时插入 1.0s / 0.45s 静音; 句号后统一 0.35s。超长句 (>120 字) 在最靠近中间的
  「、」处二次切分。
- **数字读法**: 年份 (2026年→二千二十六年)、月日、百分比 (5.33%→五点三三パーセント)、
  美元 ($4.92→四ドル九十二セント)、千分位整数 (4,323億→四千三百二十三億)、
  小数、正负号全部转汉字，避免 Fish 用日语误读阿拉伯数字。
- **缩写/公司名**: FOMC/FRB/NVDA/TSMC/EPS/PER/Kioxia/CoreWeave 等按 glossary 转片假名。
- **引用标记**: 【出所: ...】【当番組の見解】在正则化时剔除，不朗读。

## 引擎选择 (--engine / 环境变量 FISH_TTS_ENGINE)

| 值 | 行为 |
|----|------|
| `auto` (默认) | 走 **wsl2-local** (`fish_local_engine.FishLocalEngine`)。正式合成时服务器未就绪会自动拉起；启动失败直接报错，不静默回落 Mac |
| `local` | 强制 WSL2 本地引擎；同样自动拉起，失败报错 |
| `mac` | 强制 Mac SSH 引擎（仅用户显式指定时使用，作为备份链路） |

### 本地服务器启动（自动化会自动执行）

正式合成时 `fish_local_engine.ensure_server()` 会自动调用
[start_server_guard.ps1](</C:/my_project/gen-contents/tools/fishaudio-s2-pro/wsl/start_server_guard.ps1:1>)
（幂等：先 HTTP OPTIONS 探测，服务健康则直接返回，不会杀进程；未就绪则拉起并等待，
默认最长 900 秒）。手动启动等价于：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
  tools/fishaudio-s2-pro/wsl/start_server_guard.ps1 -Mode compile -WaitSeconds 900
```

- 首次请求 (或换引用音色/采样配置后) 需等 torch.compile 编译 (约 475s 一次性)，之后缓存命中，稳态 317~338 ms/token。
- 覆盖整期节目期间 Windows 端口直通 (mirrored network)，无需额外配置。
- 服务器以 systemd-run 的临时 unit（fishtts）常驻启动，不随 WSL 会话退出而终止。
- 相关环境变量: `FISH_LOCAL_API_URL`、`FISH_LOCAL_TTS_TIMEOUT` (默认 1800s)、`FISH_LOCAL_TOKENS_PER_CHAR` (默认 4.2，用于估算 max_new_tokens)、`FISH_LOCAL_STARTUP_TIMEOUT` (默认 900s，传给 guard 的等待时间)。

## Usage

```powershell
# 1. 内容 → 播音稿 (本地执行，不碰 Mac)
python us-stock-daily/tools/tts/prepare_tts.py 2026-08-19

# 2. 查看合成计划 (不连 Mac)
python us-stock-daily/tools/tts/generate_audio.py 2026-08-19 --dry-run

# 3. 正式合成 (默认 auto: 本地 WSL2 服务器未就绪时自动拉起，不回落 Mac)
python us-stock-daily/tools/tts/generate_audio.py 2026-08-19

# 重生成单个内容块
python us-stock-daily/tools/tts/generate_audio.py 2026-08-19 --only S22-C03 --force

# 强制走某条链路
python us-stock-daily/tools/tts/generate_audio.py 2026-08-19 --engine mac
python us-stock-daily/tools/tts/generate_audio.py 2026-08-19 --engine local
```

Mac 回落链路环境变量 (默认值同 economist-podcast sample):
`FISH_AUDIO_TTS_REMOTE_HOST` (cho@rw-mac-1), `FISH_AUDIO_TTS_REMOTE_VENV`,
`FISH_AUDIO_TTS_REMOTE_WORKROOT`, `FISH_AUDIO_TTS_REMOTE_WORKER`。

## 给 Remotion 的接口

`durations.json` 每个 segment 含 `order/id/slide/voice/file/duration` 和逐句
`sentences[] (text/start/end/pause_after)`。旧契约轮播高亮、现行契约页内内容切换直接用句子级
时间戳对轨; 页间切换用 segment 边界。外部槽位 (S00/END) 由 manifest 的
`asset_hint` 提示后期插入。
