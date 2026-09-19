# 流水线编排方式评估：子代理编排 vs 代码编排 + API 生成

> 结论先行：**代码编排 + LLM API 单点生成** 明显优于现在的「每阶段拉起子代理」模式。
> 参考 `sample/economist-podcast`（git 历史 `ba191e0`）已验证的架构，本项目的日更流水线
> 应当把所有确定性工作交给代码，LLM 只在固定的内容生成步骤出现，并通过统一的
> `text_llm` 封装直连 API。预计编排侧 token 消耗可下降 70-90%，同时质量和可调试性提升。

## 1. 现状问题

当前流程按 `AGENTS.md` 定义 Phase 0-5，每阶段由一个子代理执行，主代理负责拉起、
监视和临时调整。`pipeline.mjs` 提供了状态机、看门狗和告警，但它是**被动账本**：
它只记录状态和发现问题（exit 2），不会自己去启动下一步或重试失败项。真正的
「执行者」是每次都被拉起的大模型子代理。

由此产生的 token 消耗集中在：

1. 每个子代理启动时重新加载系统提示 + AGENTS.md + phase 规范 + 素材（每次 2-5 万 token）。
2. 主代理轮询 `pipeline.mjs check`，每次轮询都是一次完整的模型调用。
3. 运行中出现小问题时，主代理读文件、改文件、再验证，上下文反复膨胀。
4. 以上全部是**编排开销**，没有一行产出实际内容。

## 2. economist 参考架构

`ba191e0` 中的 economist-podcast 实现验证了一条不同的路：

| 层 | 职责 | 实现方式 |
|---|---|---|
| 主进程 | 启动 3 个 Worker、崩溃检测+自动重启、进度仪表盘 | 纯 Python（`orchestrate.py`），零 LLM |
| 状态 | 跨进程共享进度、原子写、stale 重置、断点恢复 | `episode_progress.json` + `StateManager`，`.tmp→os.replace` 原子写 |
| LLM | 文章分析、改写、TTS 文案、插图提示 | 通过 `text_llm.py` 统一 API 调用，pro/flash 两档，多供应商可切换 |
| 生产 | TTS、渲染、上传 | 独立脚本，Worker 按状态标志触发 |
| 人工 | 选题确认、分组确认 | 2 处 WebUI 确认点，其余全自动 |

关键洞察：**编排是确定性的，所以用代码写；内容生成是非确定性的，所以用 API 调**。
两者不要混在一起。

## 3. 逐环节评估

| 环节 | 推荐方式 | 理由 |
|---|---|---|
| 环境检查、启动、监视 | 纯代码 | 完全确定性，代码做 100% 可靠且零 token |
| 出错重试 | 纯代码 | 指数退避 + 最大次数 + 日志，不需要模型判断 |
| 结果预评估（字数/简体字/格式/契约） | 纯代码 | `check_japanese.py`、`check_draft_length.py`、`build_pipeline.py validate` 已存在，接进重试循环即可 |
| Phase 0 采集 | 已代码化 | `collect-*.mjs` 已就绪，无需改动 |
| Phase 1 选题 | **API 单点调用** | 评分标准已在 `phase1-triage.md` 中明确；硬门槛（美股关联性、素材量、重复排除、宏观平衡）用代码做前置/后置过滤，比代理判断更稳定 |
| Phase 2 写作 | **API 单点调用（pro 档）** | 质量由「模型 + 固定前置文 + 素材」决定，代理壳不增益单文档写作；每个 block 一次调用，代码校验不通过则带错误反馈重试 |
| Phase 3 素材/TTS | 已代码化 | 保持现状 |
| Phase 4 QA | 机器检查为主 + 可选 1 次 LLM 语义评审 | 机械项代码检查；深度/可操作性等语义项一次 API 调用即可 |
| Phase 5 集成 | 纯代码 | `build_pipeline.py run` 已覆盖 TTS→渲染→校验 |
| 发布 | 纯代码 | 保持现状 |

## 4. 质量影响评估

### 选题：无质量损失，一致性更好

选题质量取决于评分标准的编码程度，而不是代理的「思考自由度」。当前规范
（`phase1-triage.md`）已经把评分轴（a-j）、四道前置门槛、宏观上限、产业下限、
tie-break 规则全部写清了。把这些变成「prompt 中的 rubric + JSON Schema 输出 +
代码后置校验」后：

- 硬门槛由代码强制执行，不会像代理那样偶尔「觉得应该没问题」就放行。
- 评分结果落盘为 `outline.json`（结构化），后续审计和人工确认都更容易。
- 唯一的主观部分（如「信息非对称价值」打分）用一次 pro 档 API 调用完成，
  与代理模式的判断力相同，但每次输入固定、可复现。

### 写作：无质量损失，反而消除代理惰性风险

单文档长文写作的质量变量是：模型能力、提示词质量、素材质量、字数约束。
子代理壳对这些变量没有贡献——它只多了一层「读指令 → 理解 → 写文件」的中介。
把 `phase2-scriptwriting.md` 中的标准前置文（已有完整文本）+ 对应素材 +
目标 block 的元信息拼成一次 API 调用：

- 用的模型可以明确指定 pro 档（代理模式下取决于宿主环境）。
- 字数/简体字/日语质量检查失败时，代码把具体错误信息追加到 prompt 重试，
  比代理模式下「再改一下」的模糊反馈收敛更快。
- 消除了代理「写了一半偷懒缩短」的风险，因为每次调用目标就是一个 block。

### 代理仍有价值的场景

保留代理作为**兜底**而非默认路径：
- 代码重试 N 次仍失败的异常诊断（新型基础设施问题）。
- 视觉设计的创意判断（如果未来引入）。
- 用户主动要求的人工介入式讨论。

## 5. Token 成本对比（估算）

| 模式 | 编排开销 | 生成开销 | 单日总量级 |
|---|---|---|---|
| 子代理编排（现状） | 30-60 万 output token（每次启动/轮询/修调） | 5-10 万（嵌入在代理回复中） | **40-70 万**，以高价 output 为主 |
| 代码编排 + API | ≈0（代码运行不耗 token） | 15-25 万 input + 2-4 万 output | **17-29 万**，以低价 input 为主 |

说明：API 模式的生成 input 略高（因为要显式传入素材和前置文），但 output 少一个
数量级且不需要重复加载规范。综合成本（按 output 5-10 倍于 input 的定价）约下降 80%。

## 6. 推荐目标架构

```
run_daily.py（纯代码，参照 orchestrate.py）
 ├─ Worker [collect]     collect-all.mjs → Gate #0 校验
 ├─ Worker [content]     analyze_topics.py → 人工/自动确认
 │                       → write_blocks.py（逐 block API + 机械校验循环）
 │                       → build_pipeline.py scaffold/validate
 ├─ Worker [production]  build_pipeline.py run（TTS → 渲染 → artifact 校验）
 │
 ├─ ProgressState        pipeline.json（复用现有格式）原子读写
 ├─ text_llm.py          统一 API 封装：多供应商、pro/flash、重试+退避+限流
 └─ 告警                 沿用 pipeline.mjs 的邮件通知 + deadline 检查
```

人工确认点保留 2 处（与 economist 一致）：
1. 选题确认：`outline.json` 生成后，展示给用户确认或走代码规则自动通过。
2. 终稿抽查：全部 block 写完 + 机械校验通过后，人工浏览或抽听。

## 7. 实装状態（2026-09-13 更新）

以下のモジュールは実装済み（すべて `us-stock-daily/tools/pipeline/` 配下）:

| ファイル | 役割 |
|---|---|
| `text_llm.py` | 統一 LLM API クライアント。Gemini + OpenAI 互換の二系統、pro/flash の二段階、指数バックオフ再試行、RPM スライディング窓レート制限、緩い JSON パース（markdown 囲み許容）、再帰スキーマ検証。 |
| `analyze_topics.py` | 二段階トピック選定。段階0 は純コードのハードゲート（カテゴリ重み・文字数・直近3集の主アンカー重複）。段階1 は flash API で候補絞り込み。コードが本文から高信号文を抽出して 115 件でも全文へ近い証拠を渡し、タイトルのみで見落とす事故を防ぐ。段階2 は pro API で全文採点し、`validate_schema` 失敗時はエラーを付けて 1 回修復再試行する。`--stage` で部分再実行可。 |
| `write_blocks.py` | 契約生成型の脚本執筆。A/C/D は flash JSON 呼び出し＋コード検証。B は pro で全文生成後、コードが段落分割。`episode.config.json` + `script.json` + `segment-map.json` + `draft-{A,B,C,D}.md` を一括生成し、`build_pipeline.py validate` で後置検証。 |
| `final_qa.py` | 終検。機械検査（check_japanese / check_draft_length / validate / check-artifacts）＋任意の pro 1 回意味審査。`review/qa-report.json` に報告。終了コード: 0=合格 2=機械不合格 3=意味不合格。 |
| `tts_dispatch.py` | JST 10時前は Mac SSH 到達性を探測し、到達可能なら文字数均衡で local と Mac に並列割り当て。両側完了後に `reconstruct_durations.py` で durations.json を一括再構築（並行書き込み競合の解消）。10時以降または Mac 到達不可時は local 単独で実行。 |
| `run_daily.py` | 主編成器。collect → select → write → qa → tts の順次実行。`production/pipeline-progress.json` に原子書き込みで進捗を保存し、クラッシュ後は `--from <stage>` で再開。`--status` で状態確認。 |

### 実行方法

```bash
cd us-stock-daily
# 前提: .env に GEMINI_API_KEY または OPENAI_COMPAT_* を設定

# 全段階一括実行
python -X utf8 tools/pipeline/run_daily.py 2026-09-15

# 段階を指定して再開
python -X utf8 tools/pipeline/run_daily.py 2026-09-15 --from write

# TTS のみ（並行判定含む）
python -X utf8 tools/pipeline/tts_dispatch.py 2026-09-15 --dry-run
```

### 環境変数

| 変数 | 説明 |
|---|---|
| `TEXT_LLM_PROVIDER` | `gemini`（既定）または `openai_compat` |
| `GEMINI_API_KEY` | Gemini 用 API キー |
| `OPENAI_COMPAT_API_URL` / `OPENAI_COMPAT_API_KEY` | OpenAI 互換エンドポイント設定 |
| `OPENAI_COMPAT_PRO_MODEL` / `OPENAI_COMPAT_FLASH_MODEL` | モデル名 |
| `TEXT_LLM_MAX_RETRIES` | 1 回の API 呼び出しの最大再試行（既定 3） |
| `TEXT_LLM_RPM` | RPM レート制限（既定 10） |
| `FISH_AUDIO_TTS_REMOTE_HOST` | Mac SSH ホスト（既定 cho@rw-mac-1） |

## 8. 残課題

1. **visual HTML 生成**：`write_blocks.py` は S0 固定タイトルカードと
   A-p1..A-pN 予告スライドを含む `visual-data.json` / `visual-brief.md` を
   生成する。その後 `render_visual.py` が `visual.html` を自動生成する。
2. **build_pipeline.py run の呼び出し**：TTS 以降のレンダリングは
   `build_pipeline.py run --date X --render` を明示的に実行する必要がある。
   run_daily.py に `render` stage として統合するかは別途判断する。
3. **API キーの設定**：現状 `.env` に LLM API キーがないため、初回実行前に要設定。
