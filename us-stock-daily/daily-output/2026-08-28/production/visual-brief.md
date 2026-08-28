# 2026-08-28 視覚設計ブリーフ（終選後・Phase 3 / Stage S2 への引き渡し）

> 定義: [phase2-scriptwriting.md](../../../phases/phase2-scriptwriting.md)「視覚設計ブリーフの定義」。
> 頁立て・スタイル・秒数は含めない（Stage S2 の設計自由度）。アセット需要は本書が正式インプット。

---

## A（オープニング・固定版式）

- 使用データ: S&P500 7,730.99 +0.72%／NASDAQ 26,541.35 +1.57%／DOW 53,569.40 +0.20%／
  値上がり: NVDA +8.74%・MSFT +1.75%・TSLA +2.60%／値下がり: WMT -9%・BBY -7%・DKS -30%／
  10年 4.67%・2年 3.68%・金 4,652・WTI 83.09・BTC 79,714・VIX 14.51
- アセット候補: `none`（固定カード版式・vision-design §3）
- 出所: Yahoo Finance・CNBC

## B-1 NVDA財報の深層

- **核心メッセージ**: 供給制約下でも初の1年前指引 — 需要の見える化が先行している
- **可視化候補**: 決算数字カード（売上962.2B・+106%／EPS 2.46・+128%／DC 890.2B）／
  時価総額の単日増加4,415億ドル／FY2028指引+70% vs コンセンサス+45%の差／
  粗利率の推移（75%→74%→71-72%→72-73%）／コミットメント内訳（調達279B・土地電力56B・Ohio 105B…合計530.5B）／
  Grace CPU 50億ドル→年換算200億ドル／株主還元260億ドル・還元率60%
- **チャート候補**: `chart:NVDA_quarterly-revenue`（四半期売上の加速・出所 CNBC/LSEG）
- **候補アセット**: `photo:nvidia-hq`（単独用）／`person:jensen-huang`（決算発言）／`person:jim-cramer`（ベア論崩壊）
- **出所マップ**: CNBC（決算・指引・コミットメント）／WallstreetCN（アナリスト反応）／Yahoo Finance（株価）

## B-2 Treasury Twistの解剖

- **核心メッセージ**: 政府は金利を抑えられるか — 価格発見と当局介入の攻防
- **可視化候補**: 買い増し2B→4B+ドル／30年債5.3%（2007年6月以来）と発表後の反転／
  ブレークイーブン2.34%上昇（「インフレ的」読み）／TGA残高約950B vs 従来目標550-600B／
  債務40兆ドル・4年半で+10兆／利払い1.2兆ドル／ドラケンミラーの「請求書」引用／
  Citrini新協定の3変数（財務省・FRB・銀行）／BofA牛熊指標9.7・82%買われすぎ
- **チャート候補**: `chart:US30Y_2024-2026`（30年債利回りの長期推移と介入点・出所 CNBC/Yahoo）
- **候補アセット**: `photo:treasury-hq`／`person:druckenmiller`／`person:bessent`
- **出所マップ**: CNBC（買い増し・TGA・債務）／WSJ（ドラケンミラー）／WallstreetCN（Citrini・BofA）／Morgan Stanley

## B-3 ウォーシュのジャクソンホール

- **核心メッセージ**: 「語らない議長」という不確実性の価格付け
- **可視化候補**: カリシーオッズ（bond market 16%／rate cut 8%／inflation 90%／task force 70%）／
  コアPCE 3.3%・総合3.7%の構造（財-0.1%・サービス+0.3%・金融+1.2%）／
  タスクフォース5本のリスト／7月FOMC 9対3（反対3人）／市場織り込み（9・10月据え置き→12月利上げ）／
  三つのシナリオ表
- **チャート候補**: `chart:corePCE_2024-2026`（コアPCEと2%目標・出所 CNBC/Commerce Dept）
- **候補アセット**: `photo:federal-reserve-hq`／`person:warsh`／`person:hammack`
- **出所マップ**: CNBC（講演プレビュー・PCE・ハマック）／WallstreetCN（BofA台本）

## B-4 SaaS再評価

- **核心メッセージ**: AIはソフトを食べるのか、お金を払うのか — 第2層への降下
- **可視化候補**: CRM +22%（史上2番目）／売上113.5B+11%・有機+6.4%／アンソロピック評価益26億ドル（評価額965B）／
  Agentforce ARR 15億ドル+240% vs 収入基盤460億ドル／BofA目標160ドル vs クレイマー+20%／
  CRWD ARR 58.4B+25%・純増過去最高／Okta RPO 48.6B／
  構造図: インフラ層（NVDA）→アプリ・セキュリティ層（CRM/CRWD）
- **チャート候補**: なし（概念図・数字カードで足りる）
- **候補アセット**: `photo:salesforce-hq`／`person:benioff`／`logo:anthropic`
- **出所マップ**: CNBC（決算・Claudeforce・網安）／WallstreetCN（BofA・SaaS反発）

## C / D

- C: ニュース一覧1画面（8項目・使用データは outline §4 の見出し通り）。
  `logo:sk-hynix` `logo:anthropic` `logo:openai` `logo:spacex` `logo:alibaba` 程度の軽い需要
- D: 週間タイムライン1画面（8/28 講演・9/3 Cybercab・9/9 財務省オペ・9/15-16 FOMC）
