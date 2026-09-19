# visual.html テンプレート契約

## 構成

- `templates/visual-skeleton.html`: 固定デザイン層。各スライド内部は `{{SLICE:sN}}` マーカーを持つ。2026-09-16 以前は 57 枚、2026-09-17 以降の v3 契約では必要に応じ s60 まで拡張し、当日 config が参照しない末尾ページは空のまま残せる。
- `production/visual-data.json`: 当日データ層。`{"date": "...", "slices": {"sN": "<div>...</div>"}}`。
- `render_visual.py`: JSON を HTML に接合し、構造検証後に `production/visual.html` と issue ルートの `visual.html` を同時出力する。

## 日次フロー

1. 2026-09-17 以降は `write_blocks.py` が当日 `production/visual-data.json` を生成する。前日 JSON のコピー流用は禁止する。旧契約（2026-09-16 以前）のみ前日コピー更新を使える。
2. データ性スライドのみ更新する: v3 では A-p1..A-p(N+1)、B/C/D の全参照スライド、END-card、END-disclaimer を含める。旧契約の S2/S3 記法は 2026-09-16 以前のみ使う。
   - 2026-09-19以降、A-p1..A-pN は **s1 の1枚の一覧ページ**を共有する。左側はテーマ短标题のみ表示し、简介は表示しない。右側は対応 `assets/b{n}-1.png` を読み上げ同期でハイライト切替する。
   - A-p(N+1) は市況専用ページとし、[vision-design §2](../../spec/vision-design.md) の固定 4 段を省略せず作る: 三指数カード、値上がり/値下がりセクターブロック、その他市場バー、本日の要点。
   - END-card と END-disclaimer は当日 config の末尾 slide 参照に従い、別ページとして必ず埋める。
3. レンダラーを実行する。

   ```powershell
   python -X utf8 us-stock-daily/tools/visual/render_visual.py --date YYYY-MM-DD
   ```

4. DOM 検査と Playwright スクリーンショット検査を行う。

## 禁止事項

- `visual.html` を手で編集しない。
- `visual-skeleton.html` を日次で変更しない。基線デザインを採用し直す場合のみ `extract_skeleton.py` を再実行する。
- レンダラーの検証失敗は無視せず、`visual-data.json` 側のタグ整合性を修正する。

## A-p(N+1) 市況契約

A-p(N+1)（2026-09-16 以前の旧契約では S3）の各指標カードは価格または利回りに加えて、当日の変化率を必ず含む。データ源は当日の `collection/MKT-*.md` とし、表示例は `+8.19%` / `-0.58%` の形式とする。上記 4 段のうちどれかを空欄・省略にしたままレンダリングしない。
