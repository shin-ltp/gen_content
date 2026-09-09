# Phase 5：統合・最終化（integrator-agent）

> 旧 PLAN.md 第四章 Phase 5。状態: 🚧 補完（骨子）。ひな形は [../templates/daily-template.md](../templates/daily-template.md)、内容原則は [../spec/content-framework.md](../spec/content-framework.md)。

- **入力**: 検査合格の各ドラフト（`draft-{A,B,C,D}.md`）＋ 俳句（A の任意形式・全セクション完成後に制作）＋ 免責
- **出力**: `YYYY-MM-DD.md`（完成スクリプト）

---

## 統合作業

1. **コーナー統合**: 検査合格の各ドラフトを [daily-template.md](../templates/daily-template.md) の順序（A → B → C → D → 免責）に結合。
2. **Topic 登録簿の更新（2026-09-04 追加）**: 終選確定後に [../db/topic-history.md](../db/topic-history.md) へ、採用した全 B テーマの 放送日／B枠／主アンカー／副アンカー／事件日／状態 を追記する。表は新しい順に保ち、20 集より古い行は削除してよい。
3. **俳句OP制作**: 全セクション完成後、当日の核心を5-7-5音の俳句に練り上げ、A の冒頭に置く（内容が凝縮できる時のみ）。後段の分析と呼応させる。
4. **免責の配置**: 冒頭と末尾に免責事項を配置（[../spec/compliance.md](../spec/compliance.md)）。
5. **つなぎ言葉の調整**: コーナー間の唐突な切り替えをなくし、自然なつなぎで整える。
6. **音声層への引き渡し（2026-08-28 改訂）**: Gate #4 合格後、採用テーマの draft 本文から
   `production/segment-map.json`（視覚ページ×ナレーション×声の切り分け定義）を作成し、
   `tools/tts/prepare_tts.py` で TTS テキストへ変換する（数字の漢字読み・[pause] 挿入は自動）。
   旧 `broadcast-script.md` 単ファイル方式は廃止。音声合成は `tools/tts/generate_audio.py`、
   Remotion との同期は合成後に生成される `production/audio/durations.json`（実測音声時間）が担う。
   **固定発話の必須組み込み（2026-09-03 改訂）**: segment-map には以下の tts セグメントを必ず含めること。
   - 冒頭 `S00-intro`（slide s0）: 「ようこそ、毎日米国株式の市場分析をお届けするSmart Assets米国株投資チャンネルです。」
     当該 WAV は冒頭 BGM（1 秒前導 → 語り → 3 秒フェードアウト）を予めミックス済みとして生成する。
   - 末尾 `S39-greeting`（slide s35）: エンディング挨拶の固定文言（[daily-template.md](../templates/daily-template.md) 末尾の節）。
     次回が休場日の場合は最終行の直前に休場予告を1文挿入。
     当該 WAV はエンディング BGM（語り前 0.5 秒 → 語り → 終了後 5 秒の余韻フェード）を予めミックス済みとする。
   - `S39-disclaimer`（免責）は **TTS 不要・読み上げなし**。画面表示のみとし、当該スロットの
     音声は `S39-greeting` のミックス済み WAV が担う。
   - 転場 sting（2026-09-08 改訂）: `prepare_remotion.py` が Remotion タイムライン上で
     `assets/bgm/transition/tr_04_technology_6s.mp3`（6.0 秒・0.25 秒フェードイン／1.2 秒フェードアウト）を
     独立再生する。挿入条件はセクション切替 6 箇所のみ:
     A の主題→市況（s2→s3）、A→B1、B1→B2、B2→B3、B3→B4、最終 B→C。
     A・B 内の同一テーマページ切替、OP→A・C 内部・C→D・ED には挿入しない。
     sting はページ切替フレームから開始し、
     ナレーションは既定の頭 pad（16 フレーム ≒ 0.53 秒）後に始まる。本文 WAV には sting を混入させない。

---

## Gate #5（完了定義）

- [ ] 全コーナー（A/B/C/D）が統合済み
- [ ] Topic 登録簿（[../db/topic-history.md](../db/topic-history.md)）に採用 B テーマを追記済み
- [ ] 俳句（採用時）が後段分析と呼応している
- [ ] 免責が冒頭／末尾に配置済み
- [ ] `status.md` の全 Phase が ✅done になり、完成スクリプト `YYYY-MM-DD.md` を生成
