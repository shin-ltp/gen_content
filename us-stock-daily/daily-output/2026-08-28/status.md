# 2026-08-28 収集・制作状態

> 本日は規範改訂（write-then-select・シーン表廃止・分量管理）後の初の全流程実走。

| Phase | 状態 | 担当 | Gate | 備考 |
|-------|------|------|------|------|
| 0 情報収集 | ✅done | collector | PASS(#0) | 素材126件（market7/rss64/wscn31/36kr7/insights12/email5・longbridge設定skip） |
| 1 テーマ選定 | ✅done | triage | PASS(#1) | `production/outline.md`。候補5テーマ（素材容量ゲート全通過） |
| 2 スクリプト | ✅done | scriptwriter | PASS(#2) | draft-A/B/C/D。B終選: 採用4（35.3分）・落選1（小売分化→C/Aでカバー）。`check_draft_length.py` PASS |
| 3 視覚素材 | 🚧skeleton | — | — | 視覚設計ブリーフ作成済・視覚骨架32页。アセット取得・本デザインは今回の範囲外（TTS文本生成まで） |
| 4 品質検査 | ⬜todo | — | — | — |
| 5 統合 | ⬜todo | — | — | — |
| TTS文本 | ✅done | tools/tts | — | `production/tts/` 52文件・15,075字・推定43.1分。dry-run 387句（kyoujyu 3 / xiaomei 384）。音声合成はMac空闲后执行 |

## Phase 進行メモ

- 収集チャネル健康: market/rss/wscn/36kr/insights/email すべて OK（longbridge は認証未設定で config-skip）
- Gate #0 独立再評価（verify-collection）: PASS
- 採用素材 37件の frontmatter を `adopted: true` に更新済み
- B終選記録: `production/outline.md` §7 参照（B-1 NVDA 17点／B-3 Warsh 16点／B-4 SaaS 16点／B-2 Twist 15点採用、B-5 小売 15点落選）
- 規範準拠: シーン表なし・分量管理（目標9-10分/通過帯7-12分）・視覚設計ブリーフ経由の引き渡し・A は B 終選後に制作

## 差戻しログ

- 2026-08-28 分量リライト: 初稿で B-1/B-3/B-4/B-5 が通過帯割れ → 証拠・シナリオ・方法論ディテールで拡張し全テーマ PASS（水増しなし・素材由来の追加のみ）
- 2026-08-28 TTS正規化修正: 「過去4四半期」→「過去4つの四半期」（漢字化後の誤読リスク対策）