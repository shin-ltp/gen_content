# Phase 5：統合・最終化（integrator-agent）

> 旧 PLAN.md 第四章 Phase 5。状態: 🚧 補完（骨子）。ひな形は [../templates/daily-template.md](../templates/daily-template.md)、内容原則は [../spec/content-framework.md](../spec/content-framework.md)。

- **入力**: 検査合格の各ドラフト（`draft-{A,B,C,D}.md`）＋ 俳句（A の任意形式・全セクション完成後に制作）＋ 免責
- **出力**: `YYYY-MM-DD.md`（完成スクリプト）

---

## 統合作業

1. **コーナー統合**: 検査合格の各ドラフトを [daily-template.md](../templates/daily-template.md) の順序（A → B → C → D → 免責）に結合。
2. **俳句OP制作**: 全セクション完成後、当日の核心を5-7-5音の俳句に練り上げ、A の冒頭に置く（内容が凝縮できる時のみ）。後段の分析と呼応させる。
3. **免責の配置**: 冒頭と末尾に免責事項を配置（[../spec/compliance.md](../spec/compliance.md)）。
4. **つなぎ言葉の調整**: コーナー間の唐突な切り替えをなくし、自然なつなぎで整える。
5. **音声層への引き渡し（Stage S1）**: Gate #4 合格後、完成稿 `YYYY-MM-DD.md` から
   `production/broadcast-script.md`（TTS対応稿）を生成する。変換内容は 口語化・300字/分換算の
   タイムコード・**数字の漢字読み表記**・[pause]/[slowly]/[emph] 演出記号（規約は [../PLAN.md](../PLAN.md)
   §5 Stage S1。2026-08-04 試跑実績を参照）。TTS・Remotion（Stage S3/S4）はこの稿を入力とする。

---

## Gate #5（完了定義）

- [ ] 全コーナー（A/B/C/D）が統合済み
- [ ] 俳句（採用時）が後段分析と呼応している
- [ ] 免責が冒頭／末尾に配置済み
- [ ] `status.md` の全 Phase が ✅done になり、完成スクリプト `YYYY-MM-DD.md` を生成
