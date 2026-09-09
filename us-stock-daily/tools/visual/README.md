# visual.html テンプレート契約

## 構成

- `templates/visual-skeleton.html`: 固定デザイン層。47 枚の `<div class="swrap">` のみを持ち、各スライド内部は `{{SLICE:sN}}` マーカー。
- `production/visual-data.json`: 当日データ層。`{"date": "...", "slices": {"sN": "<div>...</div>"}}`。
- `render_visual.py`: JSON を HTML に接合し、構造検証後に `production/visual.html` と issue ルートの `visual.html` を同時出力する。

## 日次フロー

1. 前日 `production/visual-data.json` を当日 `production/visual-data.json` にコピーする。
2. データ性スライドのみ更新する: S2/S3/C/D、および当日変更のある B コンテンツスライド。
3. レンダラーを実行する。

   ```powershell
   python -X utf8 us-stock-daily/tools/visual/render_visual.py --date YYYY-MM-DD
   ```

4. DOM 検査と Playwright スクリーンショット検査を行う。

## 禁止事項

- `visual.html` を手で編集しない。
- `visual-skeleton.html` を日次で変更しない。基線デザインを採用し直す場合のみ `extract_skeleton.py` を再実行する。
- レンダラーの検証失敗は無視せず、`visual-data.json` 側のタグ整合性を修正する。

## S3 市況契約

S3 の各指標カードは価格または利回りに加えて、当日の変化率を必ず含む。データ源は当日の `collection/MKT-*.md` とし、表示例は `+8.19%` / `-0.58%` の形式とする。
