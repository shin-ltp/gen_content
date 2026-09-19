# -*- coding: utf-8 -*-
"""One-off generator for the 2026-09-15 visual-data.json (57 slides).

The v3 map uses five B themes x 8 pages, eight news pages, three event pages,
the fixed disclaimer, and a dedicated final news/end-card slide. Slide text is
derived from the day's script.json and outline.json.

Historical generator only: do not run for new episodes. The opening haiku
corner was retired for episodes on 2026-09-17 and later; this file keeps its
original s1 slice so the archived 09-15 output remains reproducible.
"""
import io
import json
import sys
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

REPO = Path(__file__).resolve().parents[3]
ISSUE = REPO / "us-stock-daily" / "daily-output" / "2026-09-15"


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


MEM = "assets/concepts/memory-price.png"
SAAS = "assets/concepts/ai-saas.png"
SEC = "assets/concepts/security-shield.png"
BOND = "assets/concepts/bond-auction.png"
CYCLE = "assets/concepts/ai-capital-cycle.png"
FED = "assets/brands/companies/federal-reserve-hq.jpg"
USDEBT = "assets/concepts/us-debt.png"

B = {
    1: {
        "short": "AIメモリとSandisk",
        "pages": [
            ("表紙", "テーマ 1", "AI推論の主役が計算から記憶へ",
             hero("HBF 1.6TB/s級", "サンディスクは純NAND戦略とHBF中間層で、AI推論の記憶ボトルネックに挑む。",
                  ["NAND専業", "CBA構造", "大容量QLC"], MEM, "AIメモリ")),
            ("事実", "推論", "生成のたびに文脈を読み書きする",
             stats([("g", "需要", "大容量QLC SSD", "長文脈・画像・動画で読み書きが急増。", MEM),
                    ("", "製品", "PCIe 5.0/6.0", "汎用メモリではなく高速DC向けに偏る。", MEM),
                    ("a", "構造", "需給が締む", "クラウド長期契約がスマホ・PC向け供給を圧迫。", MEM)])),
            ("戦略", "純度", "NAND専業は周期の反応を素直にする",
             stats([("g", "強み", "分社化", "HDD混在から離れ、NAND市況を直接反映。", MEM),
                    ("", "競合", "DRAM/HBM比重", "三星・SK・マイクロンはNAND単体の受け皿が限定的。", MEM),
                    ("a", "注意", "親会社売却", "2026年2月に750万株売却計画。供給圧の消化が焦点。", MEM)])),
            ("供給", "日本連携", "BiCS10で大容量と低コストを両立",
             stats([("g", "協業", "2034年末まで", "キオクシアとの期限延長。日本に310億ドル超投資計画。", MEM),
                    ("", "拠点", "四日市・北上", "世界最大級のNANDと新増量拠点。", MEM),
                    ("a", "技術", "BiCS10 332層", "面密度29Gb/mm2超、従来比+59%。BiCS11も開発。", MEM)])),
            ("技術", "CBA", "層数より横密度と接合構造",
             stats([("g", "狙い", "高密度化", "メモリアレイと制御回路を分離して接合。", MEM),
                    ("", "競合", "SK321層QLC", "三星は400層級へ。マイクロンはDRAM重視。", MEM),
                    ("a", "効果", "密度+50%", "既存更新で単位コスト10-20%低下を見込む。", MEM)])),
            ("HBF", "中間層", "HBMとSSDの間で大文脈を読む",
             stats([("g", "性能", "1.6TB/s級", "容量はHBMの8-16倍。SKと共同仕様公開。", MEM),
                    ("", "制約", "遅延10μs", "HBM比で長く、超低遅延キャッシュの代替ではない。", MEM),
                    ("a", "日程", "2027年度", "推論サンプル到着。まずHBM併用構成が現実的。", MEM)])),
            ("評価", "交差", "記憶層の実装速度でレンジが動く",
             stats([("", "PER", "300-520ドル", "EPS20-26ドルに15-20倍。", MEM),
                    ("", "再生価値", "250-400ドル", "日本合弁・CBA・大容量QLCの下支え。", MEM),
                    ("a", "DCF", "400-550ドル", "推論需要継続とHBF選択肢を織り込む。", MEM)])),
            ("行動指針", "行動指針", "B1 Sandisk — 記憶需要が利益へ変わる速度",
             acts(["目標株価<b>430-540ドル</b>、中央<b>485ドル</b>。買い候補は<b>400ドル以下</b>。",
                   "押し目積み増しは<b>370ドル以下</b>。損切りは<b>330ドル割れ</b>。",
                   "ポジションは<b>1-2%</b>、最大<b>3%</b>。QLC比率・HBF反応・単価在庫を確認。"])),
        ]
    },
    2: {
        "short": "ソフトバンク信用リスク",
        "pages": [
            ("表紙", "テーマ 2", "震源地は市場から財務へ",
             hero("200億ドル超", "OpenAI IPO延期が資金ギャップを露呈。ソフトバンクは成長株ではなく信用銘柄として見る局面。",
                  ["IPO延期", "社債条件", "担保融資"], SAAS, "AI資金")),
            ("事実", "資金", "足りないのは返済資金",
             stats([("g", "投資", "約646億ドル", "持ち分約13%。評価額8520億ドル想定。", SAAS),
                    ("", "借換", "100-200億ドル", "約400億ドルつなぎ融資を債券で借り換え計画。", SAAS),
                    ("a", "不足", "200億ドル超", "株式担保や円建て債券を加えても残る。", SAAS)])),
            ("構造", "集中", "ArmとOpenAIが総資産約75%",
             stats([("g", "資産", "一社依存", "換金不能な資産の拡大が信用評価を重くする。", SAAS),
                    ("", "収入", "通信配当", "金利費用を覆うには弱い。", SAAS),
                    ("a", "債権者", "担保と現金", "株主の成長物語とは別の評価。", SAAS)])),
            ("金利", "円", "低金利前提は繰り返せない",
             stats([("g", "負債", "円建て約半分", "資産はドル建て中心で為替が負担。", USDEBT),
                    ("", "利回り", "10年債3%前後", "追加利上げ観測が調達コストを上げる。", USDEBT),
                    ("a", "調達", "ドル市場", "円市場で集められなければ高金利を払う。", USDEBT)])),
            ("市場", "条件", "格付けより低い扱い",
             stats([("g", "既存債", "利回り8.5%超", "5年債が低格付け債に近い扱い。", BOND),
                    ("", "追加投資", "約300億ドル", "評価上昇後・借入で取得。", BOND),
                    ("a", "判断", "利ざや年限", "条件の劣化と保証を必ず確認。", BOND)])),
            ("点検", "四項目", "債券・現金化・配当・追加保証",
             stats([("", "発行", "可能か", "100-200億ドル債の条件劣化。", BOND),
                    ("", "OpenAI", "現金化", "二次売却や株式担保の余地。", BOND),
                    ("a", "資金", "配当/追加負担", "通信配当と米DC投資の追加借入を点検。", BOND)])),
            ("評価", "交差検証", "9000-13000円が中心",
             stats([("", "資産価値", "8000-13000円", "集中と流動性割引30-50%。", SAAS),
                    ("", "事業価値", "7500-12500円", "Arm・通信CFOに6-10倍。", SAAS),
                    ("a", "資金コスト", "上値重い", "借入8.5%超なら要求リターン11-13%。", SAAS)])),
            ("行動指針", "行動指針", "B2 SoftBank — 信用銘柄として扱う",
             acts(["目標株価<b>9000-13000円</b>、中心<b>1万0500円</b>。",
                   "買い検討は<b>9000円以下</b>、条件付きで<b>1万2000円まで</b>。損切りは<b>7800円割れ</b>。",
                   "現物中心<b>5%以内</b>。資金調達失敗が観測された時点で徹底見直し。"])),
        ]
    },
    3: {
        "short": "AIリスクとサイバー株",
        "pages": [
            ("表紙", "テーマ 3", "資金は半導体から守りへ",
             hero("+13.8%", "CrowdStrikeが過去最高値。Palo Alto +13%、Fortinet +9%。セキュリティETFが半導体ETFを大きく上回る。",
                  ["CrowdStrike", "Palo Alto", "Fortinet"], SEC, "サイバー")),
            ("背景", "警告", "AI速度より危険管理の支出",
             stats([("g", "発言", "Amodei警告", "AI自己設計による能力跳ね上がり懸念。", SEC),
                    ("", "事例", "基盤攻撃", "AIエージェントがOSS標的と報じられ恐怖を刺激。", SEC),
                    ("a", "解釈", "管理コスト", "成長から運用・管理コストへ評価が移る。", SEC)])),
            ("構造", "AI権限", "鍵と監査が新しい市場",
             stats([("g", "必要", "ID管理", "AIを人間と同じ権限で導入できない。", SEC),
                    ("", "優先", "経営管理", "閲覧・操作・監査は現場の趣味でなく統制。", SEC),
                    ("a", "候補", "Okta等", "SailPoint・PANW・CRWDに予算が寄りやすい。", SEC)])),
            ("決算", "収益化", "統合契約の継続率を見る",
             stats([("g", "時期", "2027年度以降", "AI安全対策の実質収益寄与は遅い。", SEC),
                    ("", "評価", "稼働中保護", "CRWD/PANWは運用土台と連携で有利。", SEC),
                    ("a", "点検", "既存追加", "単価より統合契約継続率とNRR。", SEC)])),
            ("データ", "境界", "自社環境要求が予算を作る",
             stats([("g", "制限", "ログ30日", "機密扱いに敏感な企業がモデル利用を制限。", SEC),
                    ("", "方向", "オンプレ分離", "NVDA/Palantir/BAHが用途別管理。", SEC),
                    ("a", "機会", "接続点", "MSFT自社案も含め監視・隔離・監査需要。", SEC)])),
            ("反論", "クラウド同梱", "独立監視は補完でもある",
             stats([("g", "懸念", "標準防御", "クラウド内蔵で専用企業が圧迫。", SEC),
                    ("", "環境", "複雑化", "大企業ほど第三者独立監視が必要。", SEC),
                    ("a", "判断", "競合/補完", "予算は分散しやすい。契約数頭打ちに注意。", SEC)])),
            ("評価", "質", "成長+収益性と継続課金",
             stats([("", "基準", "40%超", "成長率と収益性合計の簡易基準。", SEC),
                    ("", "倍率", "金利弱い", "EV/Sは継続課金比率で急落しにくい。", SEC),
                    ("a", "比較", "統合力", "CRWD展開力/PANW統合提案/FTNTコスト力。", SEC)])),
            ("行動指針", "行動指針", "B3 Cyber — 5-10%で分散",
             acts(["CRWD評価<b>430-460ドル</b>。買い<b>380ドル以下</b>、積み増し<b>350ドル以下</b>。",
                   "PANW評価<b>240-260ドル</b>。買い<b>210ドル以下</b>、積み増し<b>190ドル以下</b>。",
                   "セクター計<b>5-10%</b>。CRWD/PANW各<b>3-6%</b>。損切りCRWD320、PANW170前後。"])),
        ]
    },
    4: {
        "short": "Oracleの投資回収",
        "pages": [
            ("表紙", "テーマ 4", "削減は成長のためか限界のためか",
             hero("144.72ドル", "年初-25%。二桁リストラはAIインフラ投資の資金確保と成長速度疑念を同時に示す。",
                  ["リストラ13%", "CapEx拡大", "格下げ圧力"], SAAS, "Oracle")),
            ("事実", "削減", "従業員14.1万人に",
             stats([("g", "削減", "二桁割合", "9/14発表。株価一時-5%、終値144.72。", SAAS),
                    ("", "費用", "7億ドル", "再編費用を規制書類に計上。", SAAS),
                    ("a", "人数", "-13%", "2026/5期末は前年比約2.1万人減。", SAAS)])),
            ("投資", "CapEx", "人件費削減は設備購入へ消える",
             stats([("g", "Q1", "285億ドル", "前年85億ドルから3倍強。", SAAS),
                    ("", "計画", "900-950億ドル", "2027年度維持。ラック・冷却・機器に直結。", SAAS),
                    ("a", "焦点", "CFO", "削減が利益か穴埋めかで評価が分かれる。", SAAS)])),
            ("市場", "中立", "粗利率と現金化速度",
             stats([("g", "目標", "210ドル", "大手証券中立。現値から約45%上。", SAAS),
                    ("", "鍵", "粗利率", "売上成長よりAI事業の収益質。", SAAS),
                    ("a", "失敗", "延命", "現金確認できなければリストラは限界証拠。", SAAS)])),
            ("創業者", "売却取消", "需給緩和でも自信証明は難しい",
             stats([("g", "枠", "5000万株", "約75億ドル。実際は未売却。", SAAS),
                    ("", "取消", "9/11書類", "理由と代替案は非公表。", SAAS),
                    ("a", "読み", "注意", "買い意欲か単なる機会損失か判断保留。", SAAS)])),
            ("評価", "幅", "130-180ドルが現実圏",
             stats([("", "楽観", "210ドル", "収益確認後の再評価。", SAAS),
                    ("", "悲観", "100-120ドル", "負債と金利負担が重なると下値。", SAAS),
                    ("a", "上限", "140ドル", "粗利率・CFO確認前は上値抑制。", SAAS)])),
            ("点検", "四つ数字", "感情より現金",
             stats([("", "利益率", "粗利率", "営業利益率が上向くか。", SAAS),
                    ("", "CapEx", "増額/長期", "900-950億ドル計画の変化。", SAAS),
                    ("a", "契約", "受注残質", "値引き競争と現金残余を確認。", SAAS)])),
            ("行動指針", "行動指針", "B4 Oracle — 新規投げ込みは避ける",
             acts(["保有は比率引き下げを検討。比率<b>3%以下</b>、最大<b>5%</b>。",
                   "買い増しは<b>130-140ドル</b>に限定。<b>120ドル割れ</b>で距離を取る戦略も。",
                   "<b>145ドル回復</b>確認までは新規買い控え。確認後は180-210ドル視野。"])),
        ]
    },
    5: {
        "short": "銀行株の収益質",
        "pages": [
            ("表紙", "テーマ 5", "ボラティリティはボーナスではない",
             hero("ほぼ横ばい", "モイニハンCEOが第3四半期取引収益を示唆。米銀株に売り圧力が拡大。",
                  ["BAC -5.14%", "GS -3.9%", "MS -3.6%"], FED, "米銀")),
            ("事実", "BAC", "投銀手数料は想定割れ",
             stats([("g", "収益", "横ばい", "Q3取引収益は前年同期比ほぼ横ばい。", FED),
                    ("", "手数料", "16-18億ドル", "市場想定20億ドル前後を下回る。", FED),
                    ("a", "株価", "終値-5.14%", "大型銀指数に下げが広がる。", FED)])),
            ("質", "値動き", "顧客が参加して初めて収益",
             stats([("g", "条件", "リスク許容度", "様子見・ポジション圧縮は収益に響く。", BOND),
                    ("", "コスト", "管理負荷", "ヘッジ・自己資本・与信枠が増える。", BOND),
                    ("a", "伝播", "与信", "AI銘柄崩れがファンド経由で波及し得る。", BOND)])),
            ("判断", "四点", "一時調整か構造変化か",
             stats([("", "取引", "持続性", "顧客リスク許容度低下が半年続くか。", BOND),
                    ("", "手数料", "価格/遅延", "想定割れの質を見る。", BOND),
                    ("a", "純利息", "支え維持", "金利低下期待と結ぶと評価が冷える。", BOND)])),
            ("基盤", "収益", "NII 6-8%の上限が鍵",
             stats([("g", "市場業務", "17四半期", "連続成長を目指すが速度鈍化。", BOND),
                    ("", "NII", "6-8%", "上限付近なら利益中心を維持。", BOND),
                    ("a", "注意", "預金コスト", "粘着と信用コストで下支え弱まる。", BOND)])),
            ("M&A", "完了", "パイプラインよりクローズ",
             stats([("g", "案件", "偏在", "主幹事と成立時期で手数料が偏る。", BOND),
                    ("", "追跡", "完了実績", "大型M&A・発行市場・融資手数料。", BOND),
                    ("a", "周期", "3Q平均", "案件数ではなく完了実績を点検。", BOND)])),
            ("評価", "レンジ", "P/TBV・PER・還元",
             stats([("", "JPモルガン", "300-325ドル", "ROE前提にP/TBV1.1-1.3倍。", BOND),
                    ("", "ゴールドマン", "640-690ドル", "PER10-12倍台と還元で下値確認。", BOND),
                    ("a", "他行", "MS/C/WFC/BAC", "175-190/90-100/78-88/52-58ドル。", BOND)])),
            ("行動指針", "行動指針", "B5 Banks — 分割買いと機械的見直し",
             acts(["買い増しJPM<b>285以下</b>、GS<b>600以下</b>、MS<b>165以下</b>。",
                   "C<b>85以下</b>、WFC<b>72以下</b>、BAC<b>47以下</b>。目標到達後3割・5割利確。",
                   "損切りJPM275、GS570、MS155、C78、WFC65、BAC43割れ。セクター<b>5%以内</b>。"])),
        ]
    },
}


NEWS = [
    ("ブレント原油が108ドル突破", "ホルムズ緊迫と主要パイプライン閉鎖で供給懸念再燃。"),
    ("ガスタービン不足で蒸気発電が代替台頭", "AI拠点の電力確保にボイラー・蒸気タービンが現実解。"),
    ("AI半導体調整、サイバー株へ資金移動", "CrowdStrikeなどが大幅高。安全対策支出への認識拡大。"),
    ("プライバシー保護が企業AIの差別化に", "MSFTが独自環境ソリューションで顧客獲得機会拡大。"),
    ("ソフトバンクの信用リスク指標が悪化", "OpenAI IPO延期で回収計画不透明、調達負担増。"),
    ("Oracleが13%リストラ、株価下落", "AI投資資金確保とコスト削減、回収速度に焦点。"),
    ("米銀CEOが取引収益鈍化を示唆", "銀行株に売り圧力。市場不透明感が収益環境を重く。"),
    ("SandiskのAIサーバー向けメモリ技術に注目", "大容量処理でDRAM偏重からのシフトを狙う。"),
]

slices = {}

slices["s0"] = "\n" + label("S0", "Opening") + '''
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
    <div class="date-badge">2026年9月15日（火）配信</div>
    <p class="osub">AIメモリ転換、ソフトバンク信用リスク、サイバー株再評価、Oracle投資回収、銀行株逆風</p>
  </div>
  <div class="ochips">
    <div class="chip"><img class="th" src="assets/concepts/memory-price.png" alt="">Sandisk HBF</div>
    <div class="chip"><img class="th" src="assets/concepts/ai-saas.png" alt="">ソフトバンク債券</div>
    <div class="chip"><img class="th" src="assets/concepts/security-shield.png" alt="">CRWD +13.8%</div>
    <div class="chip"><img class="th" src="assets/concepts/us-debt.png" alt="">S&P500 -0.48%</div>
  </div>
</div>
</div>
'''

slices["s1"] = "\n" + label("s1", "Haiku") + f'''
<div class="slide">
{logo()}
<div class="wavebg"><img src="../../assets/brands/template/The_Great_Wave_off_Kanagawa.jpg" alt=""></div>
<div class="haiku-c">
<div class="haiku">エーアイの記憶が鍵。ソフトバンクの壁、決算の闇。<br>シジョウの熱を冷ます三つの真実。</div>
  <div class="h-ann">— 本日の市場の一句 —</div>
</div>
</div>
'''

topics = [
    "AI推論の記憶ボトルネックとSandiskの純NAND戦略",
    "OpenAI IPO延期で露呈するソフトバンクの資金ギャップ",
    "AIリスクを引き金にしたサイバーセキュリティ株の再評価",
    "オラクルのリストラ発表と株価急落、AIインフラ投資拡大の実態",
    "取引収益停滞が示す銀行株の逆風と収益の質",
]
photo_paths = [MEM, SAAS, SEC, CYCLE, USDEBT]
topic_items = []
for i, t in enumerate(topics):
    cls = "active" if i == 0 else "dimmed"
    topic_items.append(f'<div class="topic-item {cls}" data-idx="{i}"><div class="topic-number">{i+1}</div><div class="topic-title">{t}</div></div>')
frames = "".join(f'<div class="photo-frame{" active" if i==0 else ""}" data-idx="{i}"><img src="{p}" alt=""></div>' for i, p in enumerate(photo_paths))
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

slices["s3"] = "\n" + label("s3", "AIブームの質的転換") + f'''
<div class="slide">
{logo()}
<div class="chrome">
<div class="sec-title">AIブームの質的転換 — 収益・信用・統制を見る</div>
<div class="body col" style="gap:18px">
  <div class="hero-num">質的転換</div>
  <div class="hero-lab">数字の裏側にある資金の流れを紐解く。AIは選別を深め、信用・統制・回収と現金で判断する局面へ移る。</div>
  <div class="chips"><div class="chip">記憶と推論</div><div class="chip">資金調達</div><div class="chip">現金創出</div></div>
</div>
</div>
</div>
'''

slices["s4"] = "\n" + label("s4", "前日市況") + f'''
<div class="slide">
{logo()}
<div class="chrome">
<div class="sec-title">S&P500小幅安、半導体から選別売り</div>
<div class="body col" style="gap:15px">
  <div class="idx-grid">
    <div class="idx-card"><div class="idx-name">S&amp;P 500</div><div class="idx-val">小幅下落</div><div class="idx-chg down">-0.48%</div></div>
    <div class="idx-card"><div class="idx-name">Nvidia / AMD</div><div class="idx-val">軟調</div><div class="idx-chg down">-3.36% / -4.4%</div></div>
    <div class="idx-card"><div class="idx-name">MSFT / Alphabet</div><div class="idx-val">資金流入</div><div class="idx-chg up">相対堅調</div></div>
  </div>
  <div class="strip">
    <div class="mi"><span class="mn">警戒</span><span class="mv">半導体セクター調整</span></div>
    <div class="mi"><span class="mn">VIX</span><span class="mv">17.1（+7.95%）</span></div>
    <div class="mi"><span class="mn">温度感</span><span class="mv">慎重・選別売り</span></div>
    <div class="mi"><span class="mn">焦点</span><span class="mv">大型テックと記憶需要</span></div>
  </div>
  <div class="note"><b>注:</b> ハイテク全体への売りではなく、成長の先行きに対する選別売りが目立った。</div>
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
    sid = "s56" if i == 3 else f"s{44 + i}"
    items = "".join(news_item(j, j == i, esc(NEWS[j-1][0]), esc(NEWS[j-1][1])) for j in range(1, 9))
    body = f'<div class="news-grid">{items}</div>'
    slices[sid] = bright_slide(sid, f"ニュース{i}", f"ニュース {i}/8", title, body)

tl_body = ('<div class="week-tl">'
    + wtl_col("近期", "信用", [ev("社債", "mac", "ソフトバンク社債", "発行条件の硬化と株価波及を確認。")], "today")
    + wtl_col("近期", "金利", [ev("米国", "mac", "インフレ・金利指標", "金利と為替の不安定化、輸出入影響を監視。")])
    + wtl_col("随時", "Tech", [ev("決算", "ern", "テック設備投資", "収益化の具体性とガイダンス変動を点検。")])
    + wtl_col("継続", "選別", [ev("資金", "ern", "資金の質", "半導体から安全・現金創出株へのローテーション。")], "next")
    + "</div>")
slices["s53"] = bright_slide("s53", "イベント1", "信用", "社債条件と金利が選別を進める", tl_body)
slices["s54"] = bright_slide("s54", "イベント2", "金利・為替", "米国金利と円安圧力の再燃", '<div class="body col" style="gap:18px">'
    '<div class="hero-num">金利・為替</div>'
    '<div class="hero-lab">インフレ懸念の再燃で金利関連指標が不安定。ドル高・円安圧力は輸出企業の採算改善期待を後押しする一方、輸入コスト増は景気全体の重荷になる。</div>'
    '<div class="chips"><div class="chip">金利関連指標</div><div class="chip">円安圧力</div><div class="chip">輸出企業</div></div></div>')
slices["s55"] = bright_slide("s55", "イベント3", "テック", "AI設備投資の収益化を試す", '<div class="body col" style="gap:18px">'
    '<div class="hero-num">ガイダンス</div>'
    '<div class="hero-lab">生成AI関連の設備投資意欲は衰えず、市場は収益化の具体性と成長持続性に厳しい目を向け始めている。材料の出し惜しみやガイダンス変動は資金の質への逃避を促す。</div>'
    '<div class="chips"><div class="chip">設備投資</div><div class="chip">収益化</div><div class="chip">ガイダンス変動</div></div></div>')

slices["s47"] = '\n<div class="slabel">s47 — 免責事項</div>\n<div class="slide disclaimer">' + logo() + \
    '<div class="disc-body"><div class="disc-title">免責事項</div><div class="disc-text">本番組は金融・投資に関する情報提供とリテラシー向上を目的としたものであり、いかなる投資助言も行うものではありません。<br>投資の最終判断は、ご自身の責任において行ってください。</div><div class="ch-footer"><div class="fmark">SA</div><div class="ftx">Smart Assets 米国株投資チャンネル</div></div></div></div>'

for i in range(0, 57):
    key = f"s{i}"
    if key not in slices:
        raise RuntimeError(f"missing slice {key}")

out = {"date": "2026-09-15", "slices": slices}
dst = ISSUE / "production" / "visual-data.json"
dst.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="")
print(f"wrote {dst} ({dst.stat().st_size} bytes, {len(slices)} slices)")
