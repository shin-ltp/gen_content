# Phase 5：統合・最終化（integrator-agent）

> 旧 PLAN.md 第四章 Phase 5。状態: 🚧 補完（骨子）。ひな形は [../templates/daily-template.md](../templates/daily-template.md)、内容原則は [../spec/content-framework.md](../spec/content-framework.md)。

- **入力**: 検査合格の各ドラフト（`draft-{A,B,C,D}.md`）。免責はコーナー入力ではない（俳句は2026-09-17廃止）
- **出力**: `YYYY-MM-DD.md`（完成スクリプト）

---

## 統合作業

1. **コーナー統合**: 検査合格の各ドラフトを [daily-template.md](../templates/daily-template.md) の順序（A → B → C → D → 固定エンディング）に結合。
2. **Topic 登録簿の更新（2026-09-04 追加・2026-09-09 強化）**: 終選確定後に [../db/topic-history.md](../db/topic-history.md) へ、採用した全 B テーマの 放送日／B枠／主アンカー／副アンカー／事件日／状態 を追記する。表は新しい順に保ち、20 集より古い行は削除してよい。**翌日の Phase 1 がこの表で重複排除するため、triage done 前日までの行が欠けると翌日の triage done がパイプライン機械チェックで拒否される（9/8 未登録が 9/9 Apple 重複の温床になった）。**
3. **俳句OP制作**: **廃止（2026-09-17）**。A は予告 → 市況の構成のみ。旧工程は実施しない。
4. **免責の配置**: 番組末尾 `END-disclaimer` 静止画にのみ表示する。冒頭免責・ナレーション免責は禁止（[../spec/compliance.md](../spec/compliance.md)）。
5. **つなぎ言葉の調整**: コーナー間の唐突な切り替えをなくし、自然なつなぎで整える。
6. **音声層への引き渡し（2026-08-28 改訂）**: Gate #4 合格後、採用テーマの draft 本文から
   `production/segment-map.json`（視覚ページ×ナレーション×声の切り分け定義）を作成し、
   `tools/tts/prepare_tts.py` で TTS テキストへ変換する（数字の漢字読み・[pause] 挿入は自動）。
   旧 `broadcast-script.md` 単ファイル方式は廃止。音声合成は `tools/tts/generate_audio.py`、
   Remotion との同期は合成後に生成される `production/audio/durations.json`（実測音声時間）が担う。
   **固定発話の必須組み込み（2026-09-03 改訂）**: segment-map には以下の tts セグメントを必ず含めること。
   - 冒頭 `S00-intro`（slide s0）: 「ようこそ、毎日米国株式の市場分析をお届けするSmart Assets米国株投資チャンネルです。」
     当該 WAV は冒頭 BGM（1 秒前導 → 語り → 3 秒フェードアウト）を予めミックス済みとして生成する。
   - 旧契約（2026-09-16 以前）の末尾は `S39-greeting`（slide s35）＋ `S39-disclaimer`（画面のみ）だった。
   - 2026-09-17 以降は挨拶と免責を含む fixed ending WAV を `END-disclaimer` fixed slot に束ね、
     `endCardAtSec` で `END-card` へ切替える。次回が休場日の場合は fixed ending 生成前に休場予告を1文挿入する。
   - 転場 sting（2026-09-08 改訂）: `prepare_remotion.py` が Remotion タイムライン上で
     `assets/bgm/transition/tr_04_technology_6s.mp3`（6.0 秒・0.25 秒フェードイン／1.2 秒フェードアウト）を
     独立再生する。挿入条件はセクション切替 6 箇所のみ:
     旧契約は A の市況→B1（s3→次）、2026-09-17 以降は A-p(N+1)→B1（s(N+1)→次）。
     旧契約の B1→B2、B2→B3、B3→B4、最終 B→C も同様。
     A・B 内の同一テーマページ切替、OP→A・C 内部・C→D・ED には挿入しない。
     sting はページ切替フレームから開始し、
     ナレーションは既定の頭 pad（16 フレーム ≒ 0.53 秒）後に始まる。本文 WAV には sting を混入させない。

---

## Gate #5（完了定義）

- [ ] 全コーナー（A/B/C/D）が統合済み
- [ ] Topic 登録簿（[../db/topic-history.md](../db/topic-history.md)）に採用 B テーマを追記済み
- [ ] 俳句コーナーが存在しないこと（2026-09-17 廃止）を確認
- [ ] 免責が `END-disclaimer` 静止画のみに配置され、音声テキストに含まれていない
- [ ] `status.md` の全 Phase が ✅done になり、完成スクリプト `YYYY-MM-DD.md` を生成
