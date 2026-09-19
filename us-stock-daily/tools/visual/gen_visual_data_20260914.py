# -*- coding: utf-8 -*-
"""One-off generator for the 2026-09-14 visual-data.json (56 slides).

The 09-14 segment map uses the extended v3 layout: five B themes x 8 pages,
eight news pages, three event pages, plus fixed opening/haiku/overview/market
and the fixed disclaimer page. Visible numbers are taken from script.json /
outline.json; this script only arranges them into the existing slide CSS.

Historical generator only: do not run for new episodes. The opening haiku
corner was retired for episodes on 2026-09-17 and later; this file keeps its
original s1 slice so the archived 09-14 output remains reproducible.
"""
import io
import json
import sys
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

REPO = Path(__file__).resolve().parents[3]
ISSUE = REPO / "us-stock-daily" / "daily-output" / "2026-09-14"

def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def logo():
    return ('<div class="show-logo"><img src="../../assets/logo.png" '
            'alt="Smart Assets 米国株"><span>Smart Assets 米国株</span></div>')

def label(s, text):
    return f'<div class="slabel">{s} — {text}</div>'

def split_slide(s, text, chip, title, body):
    return "\n" + label(s, text) + f'\n<div class="slide split">{logo()}\n<div class="chrome">\n' \
           f'<div class="theme-chip">{chip}</div>\n<div class="sec-title">{title}</div>\n{body}\n</div>\n</div>\n'

def bright_slide(s, text, chip, title, body):
    return "\n" + label(s, text) + f'\n<div class="slide bright">{logo()}\n<div class="chrome">\n' \
           f'<div class="theme-chip">{chip}</div>\n<div class="sec-title">{title}</div>\n{body}\n</div>\n</div>\n'

def photo(path, alt="", cap=None, name=None):
    cap_html = ""
    if cap:
        cap_html = f'<div class="pf-cap"><span>{esc(cap[0])}</span><span>{esc(cap[1])}</span></div>'
    elif name:
        cap_html = f'<div class="pf-name">{esc(name)}</div>'
    return f'<div class="photo-frame"><img src="{path}" alt="{esc(alt)}">{cap_html}</div>'

def stats(items):
    rows = []
    for cls, l, n, d, _img in items:
        rows.append(f'<div class="stat {cls}"><div class="l">{l}</div><div class="n">{n}</div><div class="d">{d}</div></div>')
    return ('<div class="body"><div class="visual">' + photo(items[-1][4]) + '</div>\n'
            '<div class="content" style="display:flex;flex-direction:column;gap:16px">'
            + "".join(rows) + "</div></div>")

def acts(items):
    rows = "".join(
        f'<div class="act"><div class="no">{i}</div><div class="tx">{tx}</div></div>'
        for i, tx in enumerate(items, 1))
    return f'<div class="body col" style="gap:14px">{rows}</div>'

def hero(num, lab, chips, photo_path, alt=""):
    chip_html = "".join(f'<div class="chip">{c}</div>' for c in chips)
    return ('<div class="body col">\n'
            f'  <div class="hero-num">{num}</div>\n'
            f'  <div class="hero-lab">{lab}</div>\n'
            f'  <div class="chips">{chip_html}</div>\n'
            '</div>\n'
            f'<div class="body"><div class="visual">{photo(photo_path, alt)}</div></div>')

def news_item(num, active, title, sub):
    cls = "active" if active else "dim"
    return (f'<div class="n-item {cls}"><div class="n-num">{num}</div>'
            f'<div class="n-tx"><div class="n-title">{title}</div>'
            f'<div class="n-sub">{sub}</div></div></div>')

def ev(tag, tag_cls, big, sub):
    return (f'<div class="ev"><span class="tag {tag_cls}">{tag}</span>'
            f'<div class="col"><div class="big">{big}</div><div class="sub">{sub}</div></div></div>')

def wtl_col(day, sub, events, extra=""):
    evs = "".join(events)
    return (f'<div class="wtl-col {extra}"><div class="wtl-day">{day} <span>{sub}</span></div>'
            f'<div class="wtl-dot"></div><div class="wtl-events">{evs}</div></div>')

B = {
    1: {
        "short": "AI資本主義の転換点",
        "pages": [
            ("表紙", "テーマ 1", "自社株買い退潮と設備投資への移動",
             hero("1兆ドル前後", "世界の自社株買いは総量を保ちつつ、株高を作る力の配分が変わった。",
                  ["買い戻し 4割以上減", "設備投資へ資金移動", "EPSモデル修正"],
                  "assets/concepts/ai-capital-cycle.png", "AI資本循環")),
            ("事実", "総額", "総額は減っていない、使い道が変わった",
             stats([("g", "4-5月発表", "5,330億ドル", "2025年同期4,870億ドルを上回る。", "assets/concepts/ai-capital-cycle.png"),
                    ("", "S&P500見通し", "2026年+3%", "GS集計。2027年は+5%で総量は維持。", "assets/concepts/ai-capital-cycle.png"),
                    ("a", "構造", "中心銘柄が变化", "総量楽観より現金収支の分断を分解する。", "assets/concepts/ai-capital-cycle.png")])),
            ("設備投資", "CapEx", "現金は未来投資へ先送り",
             stats([("g", "S&P500設備投資", "2026年+33%", "研究開発+18%、自社株買いは+3%。", "assets/concepts/server-datacenter.jpg"),
                    ("", "AI基盤5社", "7,550億ドル", "2027年は8,920億ドルへ拡大可能性。", "assets/concepts/server-datacenter.jpg"),
                    ("a", "大型株買い戻し", "約440億ドル", "770億ドルから1年で4割以上減。", "assets/concepts/server-datacenter.jpg")])),
            ("EPS", "評価軸", "買い戻しのEPS押上げが細る",
             stats([("", "影響", "EPS伸び低下", "株式数圧縮の寄与をモデルから外す。", "assets/concepts/discount-rate.png"),
                    ("", "費用", "利益の先送り", "償却・電力・冷却・保証費が将来費用へ。", "assets/concepts/discount-rate.png"),
                    ("a", "本質", "ROIC確認", "回収できなければPERは低下しやすい。", "assets/concepts/discount-rate.png")])),
            ("反論", "強気", "設備投資は収益加速にもなる",
             stats([("g", "前提", "需要接続", "クラウドとAIサービス収益に結びつけば加速。", "assets/concepts/market-overheat.png"),
                    ("", "条件", "4指標が強い", "受注残・電力・稼働率・AI収益率。", "assets/concepts/market-overheat.png"),
                    ("a", "崩れ", "期待再計算", "前提が一部でも崩れると成長期待を再計算。", "assets/concepts/market-overheat.png")])),
            ("分岐", "三つのケース", "回収期間と転換率で判定",
             stats([("g", "強気", "収益が追いつく", "主役は需給ではなく利益成長。", "assets/concepts/scenario-tree.png"),
                    ("", "基本", "中位一桁EPS", "高PERには修正圧力。", "assets/concepts/scenario-tree.png"),
                    ("a", "弱気", "資本コスト再計算", "電力・金利・在庫が重なる場合は下落も調整超え。", "assets/concepts/scenario-tree.png")])),
            ("評価", "標準モデル", "三手法は500ドル前後に交差",
             stats([("", "PER", "486-540ドル", "36-40倍。現値450ドル・EPS13.5ドル想定。", "assets/concepts/saas-re-rating.png"),
                    ("", "FCF", "481-542ドル", "利回り2.4-2.7%許容。", "assets/concepts/saas-re-rating.png"),
                    ("a", "EV/EBITDA", "465-527ドル", "15-17倍。検証レンジ480-530ドル。", "assets/concepts/saas-re-rating.png")])),
            ("行動指針", "行動指針", "B1 大型クラウド — 回収で買い増す",
             acts(["目標株価<b>480-530ドル</b>。買い増しは<b>450ドル以下</b>。損切りは<b>415ドル割れ</b>。",
                   "ポジションは<b>5-8%</b>。指数が割高なら<b>3-5%</b>へ縮小。",
                   "クラウド売上・稼働率・電力単価・償却率の悪化で買い増しを停止。"])),
        ]
    },
    2: {
        "short": "OpenAI IPO延期と安全",
        "pages": [
            ("表紙", "テーマ 2", "安全が上場の前提条件になった",
             hero("2026年非上場", "速度より持続性へ。AI評価は収支と責任体制で組み替わる。",
                  ["IPO延期", "安全審査", "収益化は後ろ倒しも"],
                  "assets/concepts/security-shield.png", "AI安全")),
            ("経営判断", "制御", "止められる体制を資金より優先",
             stats([("g", "構造", "一時停止可能", "非営利法人が最終統制を持つ前提。", "assets/concepts/security-shield.png"),
                    ("", "実績", "学習停止", "数か月で一部停止の報道。", "assets/concepts/security-shield.png"),
                    ("a", "判断", "IPO拒否", "数兆円より制御不能リスクの遮断を優先。", "assets/concepts/security-shield.png")])),
            ("市場", "二段階", "過熱が冷え、収益化が遅れる",
             stats([("", "未上場株", "過熱感低下", "巨大IPOの催しが消える。", "assets/concepts/market-overheat.png"),
                    ("", "事業会社", "出口が遠のく", "AIベンチャー出資の評価切り下げ要因。", "assets/concepts/market-overheat.png"),
                    ("a", "新収入", "安全監査", "検証サービス化できる企業に機会。", "assets/concepts/security-shield.png")])),
            ("モデル", "寿命", "速さだけでは使われない",
             stats([("", "高速モデル", "7か月で退役", "精度不足で利用が伸びなかった。", "assets/concepts/ai-saas.png"),
                    ("g", "代替", "上位モデル高速化", "速度は製品ではなく料金プランへ。", "assets/concepts/ai-saas.png"),
                    ("a", "収益", "用途別プレミアム", "トークン単価から責任と品質の価格へ。", "assets/concepts/ai-saas.png")])),
            ("半導体", "需要", "学習は減っても推論は続く",
             stats([("", "サーバー投資", "伸びは緩む", "効率化で同じ売上の必要投資が低下。", "assets/concepts/server-datacenter.jpg"),
                    ("g", "安全推論", "需要は継続", "専用チップ・電力・冷却・冗長化。", "assets/concepts/server-datacenter.jpg"),
                    ("a", "制約", "電力と冷却", "商用推論が伸びるほど新ボトルネック。", "assets/concepts/server-datacenter.jpg")])),
            ("点検", "四項目", "審査、条項、受注、費用",
             stats([("", "公開日程", "審査で遅延確認", "安全審査が新モデル公開を遅らせるか。", "assets/concepts/prediction-market.png"),
                    ("", "契約", "安全条項", "クラウド大手が監査対応を売上に前借りできるか。", "assets/concepts/prediction-market.png"),
                    ("a", "数字", "AI売上-設備投資", "受注残・稼働率・安全人員費用も併せて確認。", "assets/concepts/prediction-market.png")])),
            ("評価", "交差検証", "NVDAとMSFTの中心レンジ",
             stats([("", "NVDA", "190-215ドル", "PER法165-200 / DCF180-220 / 相対190-225。", "assets/concepts/market-overheat.png"),
                    ("", "MSFT", "440-480ドル", "PER法420-476 / DCF430-480 / 相対440-480。", "assets/concepts/market-overheat.png"),
                    ("a", "前提", "収益半年-1年遅延", "学習需要削減と契約更新維持を仮定。", "assets/concepts/discount-rate.png")])),
            ("行動指針", "行動指針", "B2 安全と収益性へ移す",
             acts(["NVDAは<b>190-215ドル</b>。買い増しは<b>190ドル以下</b>、損切り<b>165ドル割れ</b>。",
                   "MSFTは<b>440-480ドル</b>。買い増しは<b>445ドル以下</b>、損切り<b>400ドル割れ</b>。",
                   "AI関連は<b>10-15%</b>、個別は<b>3-5%</b>。下限まで分割買い。"])),
        ]
    },
    3: {
        "short": "RSIと監視",
        "pages": [
            ("表紙", "テーマ 3", "速さではなく監視と責任",
             hero("70%超", "脆弱性検出などで成功水準超えの報告。人間だけの作業かは疑問が残る。",
                  ["RSI疑惑", "高密度コード", "監査可能性"],
                  "assets/concepts/security-shield.png", "AI監視")),
            ("事実", "未検証", "うわさと公式を分ける",
             stats([("", "報告", "RSI連想語", "第三者検証には至っていない。", "assets/concepts/security-shield.png"),
                    ("", "証言", "鍵回収", "短期間でアクセス鍵が回収されたと報告。", "assets/concepts/security-shield.png"),
                    ("a", "公式", "沈黙", "うわさ本身ではなく開発周期の短縮を見る。", "assets/concepts/security-shield.png")])),
            ("周期", "6週間3回", "小型モデルが相次ぎ公開",
             stats([("g", "公開", "3回連続", "2026年9月前後の小型高速モデル。", "assets/concepts/ai-saas.png"),
                    ("", "成功水準", "70%超", "脆弱性検出などの報告。", "assets/concepts/ai-saas.png"),
                    ("a", "条件", "検証の公開", "再現性がなければ誇大広告へ戻る。", "assets/concepts/ai-saas.png")])),
            ("業界", "学習ループ", "人間のコード領域が縮む",
             stats([("", "OpenAI/Anthropic", "評価に組込み", "モデルが一部コードを担うとされる。", "assets/concepts/ai-saas.png"),
                    ("g", "RSI", "既に進行", "経営トップの発言。同時に速度緩和を要請。", "assets/concepts/ai-saas.png"),
                    ("a", "財務", "監視体制", "事故はブランドと売上に波及する費用。", "assets/concepts/security-shield.png")])),
            ("保守", "35時間", "動くが読めないコード",
             stats([("", "追加", "数万行", "数十回コミット、数千ドル規模のコスト報告。", "assets/concepts/ai-saas.png"),
                    ("", "評価", "長期保守が難しい", "機能と節約が報酬化し、読みやすさが測れない。", "assets/concepts/ai-saas.png"),
                    ("a", "影響", "リスク管理費上昇", "脆弱性と運用事故の入口が増える。", "assets/concepts/security-shield.png")])),
            ("監視", "回避", "人間が見ていないと変わる",
             stats([("", "トークン節約", "語を圧縮", "人間に分かりにくい言語へ近づく例。", "assets/concepts/security-shield.png"),
                    ("", "事故", "隔離越え", "自律エージェントが情報交換し攻撃に加担した報告。", "assets/concepts/security-shield.png"),
                    ("a", "評価", "証跡と監査", "ログ・権限分離・停止スイッチ・責任者まで確認。", "assets/concepts/security-shield.png")])),
            ("手順", "三条件", "超大型プラットフォームに限定",
             stats([("", "数値", "検証可能か", "自律化主張が第三者検証に耐えるか。", "assets/concepts/scenario-tree.png"),
                    ("", "設計", "人間承認", "停止と承認が製品に入っているか。", "assets/concepts/scenario-tree.png"),
                    ("a", "財務", "法的責任", "損益に織り込める体力があるか。", "assets/concepts/scenario-tree.png")])),
            ("行動指針", "行動指針", "B3 Alphabetは中長期積み増し",
             acts(["目標株価<b>228-248ドル</b>、中央<b>238ドル</b>。",
                   "初回買いは<b>215ドル以下</b>、積み増し<b>198ドル以下</b>。損切りは<b>185ドル割れ</b>候補。",
                   "Alphabetは<b>3%</b>まで。監視ソフトとサイバー保険合計<b>5%</b>まで。"])),
        ]
    },
    4: {
        "short": "AIインフラ実物資産",
        "pages": [
            ("表紙", "テーマ 4", "実物資産は選別株高",
             hero("+328.3%", "中国建築のデータセンター・演算センター新規契約が前年同期比で急増。",
                  ["需要は本物", "土建は限定", "電力と立地"],
                  "assets/buildings/tencent-hq.jpg", "建築・不動産")),
            ("受注", "873億元", "AIモデルより先に電力と立地",
             stats([("g", "DC・演算契約", "873億元", "前年同期比+328.3%。", "assets/buildings/tencent-hq.jpg"),
                    ("", "工場含む新規", "5,617億元", "同+24.2%。工業用比率36.2%へ。", "assets/buildings/tencent-hq.jpg"),
                    ("a", "米中クラウド9社", "8,867億ドル", "2026年度設備投資の推計。", "assets/concepts/server-datacenter.jpg")])),
            ("費用", "40/50", "建物より設備と機器",
             stats([("", "比率", "10/40/50%", "インフラ・電気機械・機器の構成。", "assets/concepts/server-datacenter.jpg"),
                    ("", "1GW前投資", "約1,600億元", "計算機器と電力が中心。", "assets/concepts/server-datacenter.jpg"),
                    ("a", "土木", "20%未満", "設備購入は8割超、土木設計は14-15%。", "assets/concepts/server-datacenter.jpg")])),
            ("受注の質", "分業", "上流と専門工事が有利",
             stats([("g", "上流", "電力一括", "総合請負大手が電気と電力を統合。", "assets/buildings/tencent-hq.jpg"),
                    ("", "中流", "液冷・空調", "専門工事と半導体関連が有利。", "assets/buildings/tencent-hq.jpg"),
                    ("a", "事例", "受注と利益は別", "売上14.59%増でも純利益はマイナスの例。", "assets/buildings/tencent-hq.jpg")])),
            ("REIT", "選別", "高規格と稼働率で分かれる",
             stats([("", "一般産業REIT", "-25%超", "直近60日で下落。", "assets/buildings/tencent-hq.jpg"),
                    ("g", "ハイテク団地", "公募288倍", "稼働率92.07%、分配利回り約6%。", "assets/buildings/tencent-hq.jpg"),
                    ("a", "供給", "15万ヘクタール", "2031年までに工業・倉庫用地が回復見通し。", "assets/buildings/tencent-hq.jpg")])),
            ("リスク", "40%→20%", "増分資本収益率の低下",
             stats([("", "ROIC", "18か月で半減", "40%から20%へ。支出継続なら10%懸念。", "assets/concepts/b4-fault-line.png"),
                    ("", "契約", "切替可能性", "異業種の演算センター解約例。", "assets/concepts/b4-fault-line.png"),
                    ("a", "遅延", "電力と冷却", "長期契約でも供給遅れが利益を圧迫。", "assets/concepts/b4-fault-line.png")])),
            ("評価", "6-8元", "中国建築を三手法で測る",
             stats([("", "PER法", "6.5-9.1元", "EPS1.3元に建設業5-7倍。", "assets/concepts/saas-re-rating.png"),
                    ("", "P/B法", "6.0-7.7元", "BPS11元に0.55-0.70倍。", "assets/concepts/saas-re-rating.png"),
                    ("a", "配当利回り", "6.0-7.5元", "配当0.3元で利回り4-5%逆算。", "assets/concepts/saas-re-rating.png")])),
            ("行動指針", "行動指針", "B4 少額ずつ、電力と利率を見る",
             acts(["中心目標<b>6.5-8元</b>、上振れ<b>9元</b>。買い増しは<b>5.8-6.6元</b>に限定。",
                   "損切りは<b>4.8元割れ</b>。B/P0.45倍付近と配当4%以下をサインに。",
                   "株式全体<b>5%</b>まで。REIT代替は全体<b>8-12%</b>、利回り5.5-6.5%で稼働率90%下限。"])),
        ]
    },
    5: {
        "short": "インフレと負の金利",
        "pages": [
            ("表紙", "テーマ 5", "判断軸は実質金利と現金",
             hero("87.3%", "9月利上げ織り込みが急上昇。年内2回目は約99%とほぼ満額。",
                  ["CPI再燃", "実質金利上昇", "AI評価圧縮"],
                  "assets/concepts/us-debt.png", "金利")),
            ("数字", "CPI 0.4%", "サービス価格の粘着",
             stats([("", "CPI前年比", "3.4%", "前月とほぼ同じ。", "assets/concepts/core-pce.png"),
                    ("", "前月比", "0.4%", "エネルギーとサービスで加速。", "assets/concepts/core-pce.png"),
                    ("a", "コア", "0.3%", "予想と前月を上回る。", "assets/concepts/core-pce.png")])),
            ("実質金利", "剥落", "AIの金利吸収力が細る",
             stats([("g", "かつて", "PPI>利回り", "AI関連は金利上昇を吸収できた。", "assets/concepts/yield-curve-twist.png"),
                    ("", "現在", "差は縮小", "半導体指数が全体市場より劣後。", "assets/concepts/yield-curve-twist.png"),
                    ("a", "判定", "物価vs金利", "物価上昇力が金利上昇力を追い越せるか。", "assets/concepts/yield-curve-twist.png")])),
            ("評価", "8-12%", "割引条件が変わった",
             stats([("", "DCF", "-10〜-15%", "実質金利+0.5ptで理論値下振れ。", "assets/concepts/discount-rate.png"),
                    ("", "相対PER", "プレミアム圧縮", "30%前後から12-18%へ。", "assets/concepts/discount-rate.png"),
                    ("a", "PEG", "25倍妥当線", "20%成長。35倍超は切り下げが深い。", "assets/concepts/discount-rate.png")])),
            ("選別", "四指標", "現金で耐える会社を選ぶ",
             stats([("g", "強い", "厚い現金収支", "クラウドやソフト大手は自前で回せる。", "assets/concepts/scenario-tree.png"),
                    ("", "弱い", "外部資金依存", "小型AI・電力・DC末端は影響大。", "assets/concepts/scenario-tree.png"),
                    ("a", "見どころ", "受注残とCFO", "設備投資比率と金利負担の余裕。", "assets/concepts/scenario-tree.png")])),
            ("マクロ", "二経路", "金利経路で守られる利益",
             stats([("g", "利上げ+物価低下", "成長維持", "AIは選別の中で買える。", "assets/concepts/us-debt.png"),
                    ("", "物価が粘着", "実物選好", "エネルギーと金属が有利。", "assets/concepts/us-debt.png"),
                    ("a", "最悪", "停滞インフレ", "成長鈍化と物価強さが併存する局面。", "assets/concepts/us-debt.png")])),
            ("配分", "10-15%", "高値追いは慎重",
             stats([("", "AI中核", "10-15%", "半導体・DCなど値幅枠は3-5%。", "assets/concepts/scenario-tree.png"),
                    ("", "個別", "5%上限", "中核2-3%、投機枠1-2%。", "assets/concepts/scenario-tree.png"),
                    ("a", "方法", "3回分割", "決算と10年債利回り低下を確認してから。", "assets/concepts/scenario-tree.png")])),
            ("行動指針", "行動指針", "B5 金利環境では現金と質",
             acts(["NVDA<b>160-190ドル</b>。買い<b>130-145ドル</b>。損切り<b>115ドル割れ</b>。",
                   "MSFT<b>470-510ドル</b>。買い<b>400-430ドル</b>。損切り<b>370ドル割れ</b>。",
                   "Alphabet<b>200-225ドル</b>。買い<b>170-185ドル</b>。損切り<b>150ドル割れ</b>。3社合計投機枠5%。"])),
        ]
    },
}

NEWS = [
    ("自社株買いがAI設備投資に押され減少", "大型株の四半期額は過去1年で4割以上減。資金はDC・チップへ。"),
    ("Google、AI自己進化の内部開発との情報", "能力向上をAI自身に任せる構想。検証は未了。"),
    ("OpenAI、安全優先で2026年IPO中止", "制御不能リスクへの備えを資金調達より重視。"),
    ("OpenAI高速モデル、7か月で終了", "速度は優位でも精度不足。汎用モデル高速化へ。"),
    ("有力数学者らがOpenAIを批判", "検証・修正に研究者の無報酬労働が偏ると指摘。"),
    ("AI生成の圧縮コードが保守性を損なう懸念", "トークン節約優先で可読性と管理性が低下。"),
    ("AI医薬は設計から検証・自動化ラボへ", "調達資金の70%を実験設備に充てる企業も。"),
    ("Nvidia、Hugging Faceを1兆3000億円で買収検討か", "ハードとソフトの融合、規制当局動向が焦点。"),
]

slices = {}

s0 = "\n" + label("S0", "Opening") + '''
<div class="slide">
''' + logo() + '''
<div class="opening"><img src="assets/concepts/opening-visual.png" alt=""><div></div></div>
<div class="oc">
  <div class="omain">
  <div class="olockup">
    <img src="../../assets/logo.png" alt="">
    <div>
      <div class="och-name">Smart Assets 米国株投資チャンネル</div>
      <h1>米国株<span class="acc">デイリー</span><br>深層分析</h1>
    </div>
  </div>
    <div class="date-badge">2026年9月14日（月）配信</div>
    <p class="osub">自社株買い退潮、OpenAI IPO延期、RSIと監視、実物資産、利上げ観測</p>
  </div>
  <div class="ochips">
    <div class="chip"><img class="th" src="assets/concepts/ai-capital-cycle.png" alt="">買い戻し−44%</div>
    <div class="chip"><img class="th" src="assets/concepts/security-shield.png" alt="">OpenAI IPO延期</div>
    <div class="chip"><img class="th" src="assets/concepts/us-debt.png" alt="">利上げ87.3%</div>
    <div class="chip"><img class="th" src="assets/concepts/server-datacenter.jpg" alt="">S&P500 +0.86%</div>
  </div>
</div>
</div>
'''
slices["s0"] = s0

slices["s1"] = "\n" + label("s1", "Haiku") + f'''
<div class="slide">
{logo()}
<div class="wavebg"><img src="../../assets/brands/template/The_Great_Wave_off_Kanagawa.jpg" alt=""></div>
<div class="haiku-c">
<div class="haiku">資本移動の波がエーアイ銘柄を再構築する。<br>自社株買い退潮と設備投資転換、<br>その先にあるシジョウの本質とは。</div>
  <div class="h-ann">— 本日の市場の一句 —</div>
</div>
</div>
'''

topics = [
    "1兆ドル自社株買いの退潮と、設備投資への資金移動",
    "OpenAI IPO延期と安全基準が収益化を変える",
    "RSI・高密度コード・人間による監視の限界",
    "AIインフラが建築・不動産など実物資産へ広がる",
    "インフレ再燃と負の金利剥落、利上げ観測の再燃",
]
topic_items = []
photo_paths = [
    "assets/concepts/ai-capital-cycle.png",
    "assets/concepts/security-shield.png",
    "assets/concepts/ai-saas.png",
    "assets/buildings/tencent-hq.jpg",
    "assets/concepts/us-debt.png",
]
for i, t in enumerate(topics):
    cls = "active" if i == 0 else "dimmed"
    topic_items.append(f'<div class="topic-item {cls}" data-idx="{i}"><div class="topic-number">{i+1}</div><div class="topic-title">{t}</div></div>')
frames = "".join(f'<div class="photo-frame{" active" if i==0 else ""}" data-idx="{i}"><img src="{p}" alt=""></div>' for i,p in enumerate(photo_paths))
slices["s2"] = "\n" + label("s2", "五つの問い") + f'''
<div class="slide split">
{logo()}
<div class="chrome">
<div class="sec-title">今日の五つの問い</div>
<div class="carousel">
  <div class="visual">{frames}</div>
  <div class="content">{"".join(topic_items)}</div>
</div>
</div>
</div>
'''

slices["s3"] = "\n" + label("s3", "実体経済の第二波") + f'''
<div class="slide">
{logo()}
<div class="chrome">
<div class="sec-title">AIブーム第二波 — 実体経済への影響を織り込む</div>
<div class="body col" style="gap:18px">
  <div class="hero-num">第二波</div>
  <div class="hero-lab">数字の裏側にある資金の流れを紐解く。物語ではなく、回収と現金で判断する。</div>
  <div class="chips"><div class="chip">実体経済接続</div><div class="chip">資金フロー</div><div class="chip">回収指標</div></div>
</div>
</div>
</div>
'''

slices["s4"] = "\n" + label("s4", "前日市況") + f'''
<div class="slide">
{logo()}
<div class="chrome">
<div class="sec-title">S&P500反発、銘柄選別が進む</div>
<div class="body col" style="gap:15px">
  <div class="idx-grid">
    <div class="idx-card"><div class="idx-name">S&amp;P 500</div><div class="idx-val">7,656.98</div><div class="idx-chg up">+0.86%</div></div>
    <div class="idx-card"><div class="idx-name">Nvidia</div><div class="idx-val">小動き</div><div class="idx-chg">選別</div></div>
    <div class="idx-card"><div class="idx-name">Qualcomm / AMD</div><div class="idx-val">買われる</div><div class="idx-chg up">資金流入</div></div>
  </div>
  <div class="strip">
    <div class="mi"><span class="mn">警戒</span><span class="mv">利上げ観測の再燃</span></div>
    <div class="mi"><span class="mn">VIX</span><span class="mv">低下</span></div>
    <div class="mi"><span class="mn">温度感</span><span class="mv">中立でやや上昇気味</span></div>
    <div class="mi"><span class="mn">焦点</span><span class="mv">AI設備投資期待</span></div>
  </div>
  <div class="note"><b>注:</b> 半導体は一枚岩ではなく、資金は実体と設備投資の接続で選別された。</div>
</div>
</div>
</div>
'''

cursor = 5
for n in range(1, 6):
    meta = B[n]
    pages = meta["pages"]
    for pi, (kind, chip, title, body) in enumerate(pages):
        sid = f"s{cursor}"
        if pi == len(pages) - 1:
            slices[sid] = bright_slide(sid, f"B{n} {kind}", chip, title, body)
        else:
            slices[sid] = split_slide(sid, f"B{n} {kind}", chip, title, body)
        cursor += 1

for i, (title, sub) in enumerate(NEWS, 1):
    # s47 is reserved for the fixed disclaimer; news3 gets dedicated s56.
    if i == 3:
        sid = "s56"
    else:
        sid = f"s{44 + i}"
    items = "".join(news_item(j, j == i, esc(NEWS[j-1][0]), esc(NEWS[j-1][1])) for j in range(1, 9))
    body = f'<div class="news-grid">{items}</div>'
    slices[sid] = bright_slide(sid, f"ニュース{i}", f"ニュース {i}/8", title, body)
    cursor += 1

tl_body = ('<div class="week-tl">'
    + wtl_col("9/19", "FOMC", [ev("金利", "mac", "FOMC 政策金利", "日本時間19日未明。追加利上げと据え置きが交錯。")], "today")
    + wtl_col("近期", "AI", [ev("AI", "ern", "OpenAI 次期モデル", "期待超過でハイテク株全体の勢いが変わる。")])
    + wtl_col("近期", "中国", [ev("中国", "mac", "経済指標", "生産と消費の回復が景気腰折れ懸念を払拭できるか。")])
    + wtl_col("随時", "市場", [ev("管理", "ern", "売買高と投機資金", "技術革新系は短期的資金を呼びやすい。")])
    + wtl_col("継続", "リスク", [ev("為替", "mac", "ドルと資金流向", "新興国資金と日本株の海外資金に直結。")], "next")
    + "</div>")
slices["s53"] = bright_slide("s53", "イベント1", "来週", "FOMCが環境を左右する", tl_body)
slices["s54"] = bright_slide("s54", "イベント2", "AI", "OpenAI次期モデルの期待と投機", '<div class="body col" style="gap:18px">'
    '<div class="hero-num">次期モデル</div>'
    '<div class="hero-lab">発表内容が市場期待を上回るか否かで、ハイテク株全体の勢いが変わる。</div>'
    '<div class="chips"><div class="chip">半導体</div><div class="chip">ソフトウェア</div><div class="chip">売買高注意</div></div></div>')
slices["s55"] = bright_slide("s55", "イベント3", "中国", "中国経済指標と輸出関連", '<div class="body col" style="gap:18px">'
    '<div class="hero-num">生産・消費</div>'
    '<div class="hero-lab">回復が腰折れ懸念を払拭できるか。悪化なら輸出関連株の重荷、政策支援期待なら買い優勢も。</div>'
    '<div class="chips"><div class="chip">日本企業の販売先</div><div class="chip">政策支援</div><div class="chip">リスク管理</div></div></div>')

slices["s47"] = '\n<div class="slabel">s47 — 免責事項</div>\n<div class="slide disclaimer">' + logo() + \
    '<div class="disc-body"><div class="disc-title">免責事項</div><div class="disc-text">本番組は金融・投資に関する情報提供とリテラシー向上を目的としたものであり、いかなる投資助言も行うものではありません。<br>投資の最終判断は、ご自身の責任において行ってください。</div><div class="ch-footer"><div class="fmark">SA</div><div class="ftx">Smart Assets 米国株投資チャンネル</div></div></div></div>'

for i in range(48, 57):
    key = f"s{i}"
    if key not in slices:
        raise RuntimeError(f"missing slice {key}")
for i in range(0, 48):
    key = f"s{i}"
    if key not in slices:
        raise RuntimeError(f"missing slice {key}")

out = {"date": "2026-09-14", "slices": slices}
dst = ISSUE / "production" / "visual-data.json"
dst.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="")
print(f"wrote {dst} ({dst.stat().st_size} bytes, {len(slices)} slices)")
