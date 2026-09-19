# -*- coding: utf-8 -*-
"""One-off generator for the 2026-09-16 visual-data.json (57 slides).

v3 map: five B themes x 8 pages, eight news pages, event pages, the fixed
disclaimer, and a dedicated news slide slot at s56. Slide text is derived
from the day's drafts (draft-A/B/C/D) and outline.json.

Historical generator only: do not run for new episodes. The opening haiku
corner was retired for episodes on 2026-09-17 and later; this file keeps its
original s1 slice so the archived 09-16 output remains reproducible.
"""
import io
import json
import sys
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf-8".lower()):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

REPO = Path(__file__).resolve().parents[3]
ISSUE = REPO / "us-stock-daily" / "daily-output" / "2026-09-16"


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


BOND = "assets/concepts/bond-auction.png"
TWIST = "assets/concepts/yield-curve-twist.png"
USDEBT = "assets/concepts/us-debt.png"
FED = "assets/concepts/jackson-hole.png"
OVERHEAT = "assets/concepts/market-overheat.png"
DISC = "assets/concepts/discount-rate.png"
PCE = "assets/concepts/core-pce.png"
MEM = "assets/concepts/memory-price.png"
CYCLE = "assets/concepts/ai-capital-cycle.png"
TREE = "assets/concepts/scenario-tree.png"
SHIELD = "assets/concepts/security-shield.png"
PREDICT = "assets/concepts/prediction-market.png"
TGA = "assets/concepts/tga-vault.png"
SRE = "assets/concepts/saas-re-rating.png"
SAAS = "assets/concepts/ai-saas.png"
NVDA = "assets/brands/companies/nvidia-hq.jpg"
META = "assets/brands/companies/meta-hq.jpg"
TSMC = "assets/brands/companies/tsmc-hq.jpg"

B = {
    1: {
        "short": "米10年債5%突破",
        "pages": [
            ("表紙", "テーマ 1", "金利は本当に「しばらく高い」のか",
             hero("10年債 5.045%", "物価の再上昇・財政供給・AI資金需要が重なり、債券の条件が構造的に厳くなった。",
                  ["20年債入札最高", "逆イールドの深層", "選別相場"], TWIST, "利回り曲線")),
            ("事実", "入札", "落札利回りは過去最高",
             stats([("g", "利回り", "10年債5.045%", "2007年以来の水準まで上昇。", BOND),
                    ("", "20年債", "5.420%", "落札利回りは過去最高。応札倍率2.57倍。", BOND),
                    ("a", "間接入札", "52.47%へ低下", "低い利回りでは買い手が待っている状態。", BOND)])),
            ("背景", "中東", "原油高が期待インフレを刺激",
             stats([("g", "原油", "ブレント107.7ドル", "サウジパイプライン停止で供給不安。", USDEBT),
                    ("", "日本", "30年債4.12%", "先進国の長期金利に共通の圧力。", USDEBT),
                    ("a", "豪州", "10年債5.42%", "世界の債券が同時に売られる局面。", USDEBT)])),
            ("供給", "財政", "借り換えと社債が同時に来る",
             stats([("g", "政府", "財政赤字", "期限到来債の借り換えで長期供給が増加。", FED),
                    ("", "中央銀行", "買い支えから撤退", "外国公式機関も以前ほど拾わない。", FED),
                    ("a", "AI投資", "社債発行", "巨額設備投資が資金調達を膨らませる。", FED)])),
            ("政策", "FOMC", "焦点は利上げより「その後」",
             stats([("g", "織り込み", "利上げ90%超", "利上げ自体は材料出尽くし。", PCE),
                    ("", "声明", "姿勢が弱ければ", "国債の条件はさらに悪化する。", PCE),
                    ("a", "時間差", "高金利が重い", "実体経済に効くまで水準は維持。", PCE)])),
            ("株式", "耐久", "指数は小幅下げにとどまる",
             stats([("g", "指数", "小幅下落", "半導体・光通信には資金が残る。", OVERHEAT),
                    ("", "住宅", "固定ローン金利", "10年債の影響が家計に波及。", OVERHEAT),
                    ("a", "点検", "利益率と現金", "高成長期待だけの比率は減らす。", OVERHEAT)])),
            ("評価", "三つの物差し", "益回り・ERP・PBR×ROE",
             stats([("", "益回り", "6%以上が望ましい", "10年債5%ならPER約11-17倍相当。", DISC),
                    ("", "リスクプレミアム", "妥当PER12-18倍", "債券利回りに3.5-5.5%上乗せ。", DISC),
                    ("a", "資本効率", "18-22倍は一部だけ", "ROE10%前後でPBR3倍超は続かない。", DISC)])),
            ("行動指針", "行動指針", "B1 金利高止まりへの耐久構成",
             acts(["目標は予想EPS×<b>PER13-17倍</b>。高品質成長株だけ<b>18-22倍</b>を許容。",
                   "買い増しは目標中央から<b>10-20%下</b>で小口に分ける。損切りは買い値<b>20-25%</b>。",
                   "株式<b>3-5割</b>・短期債券<b>1-2割</b>・現金<b>2-3割</b>。売買は2-3回に分ける。"])),
        ]
    },
    2: {
        "short": "Meta自社チップ",
        "pages": [
            ("表紙", "テーマ 2", "汎用GPU依存からの分断",
             hero("MTIA 1GW超", "メタが2027年前半に自社ASICを投入。AI投資は推論特化へ軸を移す。",
                  ["ブロードコム設計", "TSMC製造", "3歳超人論"], NVDA, "NVIDIA")),
            ("事実", "世代", "3代目と4代目が並走",
             stats([("g", "MTIA450", "2027年前半", "通称アルケ。データセンターに投入。", META),
                    ("", "MTIA500", "2027年末", "通称アストリッド。設計完了へ。", META),
                    ("a", "電力", "1ギガワット超", "今後12か月で自製チップを大量展開。", META)])),
            ("効率", "コスト", "推論では自製が有利",
             stats([("g", "サンプル", "誤差2-3%", "初回12枚を受領、初日で自社モデル稼働。", TSMC),
                    ("", "オリンパス", "2028-29見送り", "約30%高い価格を大規模展開で拒否。", TSMC),
                    ("a", "潮流", "訓練から推論へ", "用途別の専用チップ時代が来る。", TSMC)])),
            ("限界", "3歳超人", "AIは開発を全自動にしない",
             stats([("g", "発言", "TSMC幹部", "AIに善悪の判断はできない。", SAAS),
                    ("", "現場", "先端は人の手", "A14・A10でAIの直接効果は限定的。", SAAS),
                    ("a", "含み", "取り合いが激化", "専用チップ増は製造・実装の争奪戦。", SAAS)])),
            ("規制", "分断", "法整備は本当に要るか",
             stats([("g", "懐疑", "ジェンセン氏", "新法は不要、市場判断が十分。", NVDA),
                    ("", "議会", "緊急停止法案", "管理重視の立場が対立。", NVDA),
                    ("a", "制約", "電力とデータ主権", "規制より供給側の拘束が強い。", NVDA)])),
            ("視点", "三つ", "分けて見なければ誤る",
             stats([("", "分離", "訓練と推論", "NVIDIAは訓練とネットワークで強い。", CYCLE),
                    ("", "単価", "推論コスト", "1GW超が利益率に効くか検証。", CYCLE),
                    ("a", "追従", "グーグル・MS", "ASIC予算移動は成長率を押し下げる。", CYCLE)])),
            ("評価", "交差検証", "メタ1050ドル・NVIDIA250ドル",
             stats([("", "メタ", "950-1200ドル", "EPS32ドル×30-37倍。中心1050ドル。", META),
                    ("", "エヌビディア", "230-280ドル", "EPS6.8ドル×35-42倍。中心250ドル。", NVDA),
                    ("a", "分かれ目", "織り込み幅", "推論効率と顧客流出の想定が鍵。", CYCLE)])),
            ("行動指針", "行動指針", "B2 Meta/NVIDIA — 決算まで待て",
             acts(["メタ目標<b>950-1200ドル</b>。買い<b>820-880</b>、積み増し<b>920</b>、損切り<b>770割れ</b>。",
                   "NVIDIA目標<b>230-280ドル</b>。買い<b>190-210</b>、積み増し<b>225</b>、損切り<b>175割れ</b>。",
                   "メタ<b>5-8%</b>、NVIDIA<b>10-15%</b>。決算前の買い増しは避ける。"])),
        ]
    },
    3: {
        "short": "中東オイルショック",
        "pages": [
            ("表紙", "テーマ 3", "供給不安は金利を再上昇させる",
             hero("WTI 105.83ドル", "紅海延布港の積出停止と東西パイプライン障害。原油高が物価と金利を重くする。",
                  ["延布港停止", "スタグフレーション警戒", "選別相場"], PCE, "インフレ")),
            ("事実", "荷動き", "積み出しが止まった",
             stats([("g", "米国", "WTI+4.38%", "場中106.5ドル、終値105.83ドルは5月以来の高値。", PCE),
                    ("", "北海", "ブレント108.75ドル", "+2.9%。供給不安の再燃。", PCE),
                    ("a", "東西パイプライン", "日量700万bbl", "全長約1200km。ホルムズ回避の代替路が停止。", PCE)])),
            ("現物", "契約", "荷動きと契約がずれ始める",
             stats([("g", "欧州現物", "一時130ドル超", "フォーティーズは136.75ドルまで上昇。", BOND),
                    ("", "オルレン", "代替調達急ぐ", "北海・ミッドランド・カザフ等で補完。", BOND),
                    ("a", "アラムコ", "積出方法変更", "船対船転載とホルムズ経由を増やす。", BOND)])),
            ("金利", "波及", "期待インフレが国債を売る",
             stats([("g", "米国", "10年債5.02%", "2007年以来の水準を付けた。", TWIST),
                    ("", "日本", "30年債4.12%", "先進国で長期金利が同時に上昇。", TWIST),
                    ("a", "需給", "社債と国債", "AI投資と財政が買い手を奪う。", TWIST)])),
            ("FRB", "選択", "利上げと景気の板挟み",
             stats([("g", "市場", "利上げ90%超", "高金利が成長株を相対的に冷やす。", FED),
                    ("", "家計", "原油負担", "消費の伸び悩みが収益環境を重く。", FED),
                    ("a", "判断", "水準の維持期間", "何日・何週間続くかが分かれ目。", FED)])),
            ("エネルギー", "買い場", "三つの物差しで照合",
             stats([("g", "PER", "10-12倍", "原油100ドル台維持前提なら12倍前後。", OVERHEAT),
                    ("", "FCF利回り", "7%前後", "確保できる水準を買い場候補に。", OVERHEAT),
                    ("a", "配当", "3.5-4.5%", "自社株買いを継続できるか確認。", OVERHEAT)])),
            ("防衛", "契約残高", "ニュースより予算の流れ",
             stats([("g", "PER", "22-25倍", "受注残と営業CFの安定が前提。", SHIELD),
                    ("", "FCF利回り", "3-4%", "この水準を買い場と見る。", SHIELD),
                    ("a", "注意", "停戦報道", "地政学プレミアムは一気に剥がれる。", SHIELD)])),
            ("行動指針", "行動指針", "B3 エネルギー・防衛 — 段階買い",
             acts(["XOM目標<b>125-135ドル</b>・積み増し<b>112</b>・損切り<b>102割れ</b>。CVX<b>175-190</b>/<b>160</b>/<b>148割れ</b>。",
                   "LMT目標<b>520-560ドル</b>・積み増し<b>485</b>・損切り<b>450割れ</b>。RTX<b>180-200</b>/<b>168</b>/<b>152割れ</b>。",
                   "エネルギー<b>5%</b>・防衛<b>3%</b>、合計<b>8%以内</b>。一括買付は避ける。"])),
        ]
    },
    4: {
        "short": "AIメモリ高密度化",
        "pages": [
            ("表紙", "テーマ 4", "主役はHBMだけではない",
             hero("512GB DDR5", "マイクロンが世界初のRDIMM動作検証。AIのボトルネックは演算から保持へ移る。",
                  ["12TB/サーバー", "9200MT/s", "電力-60%"], MEM, "メモリ")),
            ("事実", "実証", "複数サーバーで試験成功",
             stats([("g", "容量", "12TBへ", "2ソケット構成のDDR5上限が拡大。", MEM),
                    ("", "速度", "9200MT/s見込み", "AMDとIntelが能動的検証に着手。", TREE),
                    ("a", "電力", "60%超低下", "128GB×4本構成比。量産は2027年後半。", TREE)])),
            ("理由", "推論", "大きく速く低電力で保持",
             stats([("g", "AI", "中間状態の保持", "呼び出しのたびに待ち時間が生じる。", CYCLE),
                    ("", "基盤", "Spark・RocksDB", "主記憶に置ける量が増えれば階層アクセス減。", CYCLE),
                    ("a", "課題", "計算と記憶の平衡", "演算速度だけでは伸びない。", CYCLE)])),
            ("分担", "役割", "HBMとDDR5は敵同士ではない",
             stats([("g", "HBM", "GPU近接", "極めて広いデータ通路を与える。", TREE),
                    ("", "DDR5", "容量と電力", "CPU側の手薄な容量を補完。", TREE),
                    ("a", "効果", "同じ電気で更多", "ラック当たりの計算量が増える。", TREE)])),
            ("勝ち筋", "三つの層", "チップ外に利益が回る",
             stats([("g", "メモリ大手", "積層技術", "マイクロン・SK・サムスンが候補。", DISC),
                    ("", "プラットフォーム", "CPU/サーバー", "AMD・Intelが設計への反映を早める。", DISC),
                    ("a", "周辺", "電源・冷却", "1ラック当たりの電力削減が鍵。", DISC)])),
            ("リスク", "普及", "成立しても遅い可能性がある",
             stats([("g", "歩留まり", "価格", "256GB倍の価値が認められるか。", OVERHEAT),
                    ("", "競合", "HBM・CXL", "規格間の均衡次第で需要は狭まる。", OVERHEAT),
                    ("a", "金利", "DC投資", "5%台の高金利が資金調達を圧迫。", OVERHEAT)])),
            ("評価", "交差検証", "重なりは180-240ドル",
             stats([("", "循環調整", "144-240ドル", "EPS12-16ドル×PER12-15倍。", USDEBT),
                    ("", "PBR", "120-240ドル", "BPS40-48ドル×3-5倍。", USDEBT),
                    ("a", "EV/EBITDA", "200ドル前後", "6-8倍で支持。240ドル超は先取り。", USDEBT)])),
            ("行動指針", "行動指針", "B4 Micron — 確認後に段階買い",
             acts(["目標<b>180-240ドル</b>。新規買い<b>150ドル以下</b>、積み増し<b>170ドル以下</b>、損切り<b>130割れ</b>。",
                   "ポジションは総資産の<b>3-5%</b>、値幅の大きい半導体は<b>5%上限</b>。",
                   "確認三点: プラットフォーム採用・実売価格の効率・量産歩留まり。"])),
        ]
    },
    5: {
        "short": "Clarity法案否決とBTC",
        "pages": [
            ("表紙", "テーマ 5", "逆風は価格ではなく制度の空白",
             hero("BTC 74,910ドル", "上院はクリア法案を手続き投票で退けた。規制空白長期化が機関資金を遠ざける。",
                  ["60票に届かず", "COIN一時-12%", "相関の再定義"], PREDICT, "規制の不確実性")),
            ("事実", "暴落", "売り圧力が同時に集まった",
             stats([("g", "ビットコイン", "一時-5.3%", "7万4910ドルまで下落。", PREDICT),
                    ("", "イーサリアム", "-8%超", "小型トークンはさらに深い下げ。", PREDICT),
                    ("a", "関連株", "COIN-12% CRCL-13%", "ストラテジーも-8%。金利上昇も同時進行。", TGA)])),
            ("政治", "構図", "約束と資金誘致の矛盾",
             stats([("g", "共和党", "論点修正", "それでも民主党の懸念は解けない。", TGA),
                    ("", "懸念", "利益相反", "トランプ氏関連の暗号資産事業。", TGA),
                    ("a", "枠組み", "CFTC監督", "数億ドルのロビー活動の時間軸が後ずれ。", TGA)])),
            ("機関", "実務", "ルールの方が先にある",
             stats([("g", "指摘", "モナークCOO", "空白は投資先選定と資本配分に影響。", SAAS),
                    ("", "入口", "予見可能性", "価格変動より法制の安定が判断基準。", SAAS),
                    ("a", "限界", "資金コスト", "規制待ちの時間には費用が掛かる。", SAAS)])),
            ("相関", "二軸", "株とBTCは一つに結ばれない",
             stats([("g", "株", "収益と金利", "企業収益と金利のバランスで売られる。", USDEBT),
                    ("", "BTC", "期待と流動性", "規制期待の消失で切れる相関。", USDEBT),
                    ("a", "実務", "金利×規制", "単一数値でなく状態で分ける。", USDEBT)])),
            ("評価", "Coinbase", "三手法の重なり180-220ドル",
             stats([("", "同業比較", "170-220ドル", "規制正常化を前提とした基礎水準。", SRE),
                    ("", "事業別", "180-240ドル", "取引・ステーキング・資産管理の合計。", SRE),
                    ("a", "現金創出", "150-230ドル", "2027-30年度の成長を現在価値に。", SRE)])),
            ("シナリオ", "幅", "単一見通しに賭けない",
             stats([("g", "基準", "170-220ドル", "規制リスクは株価にかなり織り込み済み。", TREE),
                    ("", "上振れ", "230-280ドル", "政策再開と金利低下が重なら9万ドル超も。", TREE),
                    ("a", "弱気", "130-170ドル", "BTC6万5千ドル割れは下落相場移行の警戒。", TREE)])),
            ("行動指針", "行動指針", "B5 COIN/BTC — 空白前提で小さく",
             acts(["COINは<b>170ドル以下</b>で分割買い。<b>145ドル割れ</b>で損切り再考。比率<b>2-3%</b>。",
                   "ビットコイン本体は全体<b>5%以内</b>。持ち高を一度で決めない。",
                   "買い戻しは規制進展と収益改善の両確認まで急がない。"])),
        ]
    },
}


NEWS = [
    ("Google「Gemini 3.8 Live」投入", "会話中に複数タスクを裏側で処理。企業向け音声AIの普及を狙う。"),
    ("Huaweiが3Dデータセンター発表", "電力と冷却の階層分離で大型チップの熱問題と拡張性を両立。"),
    ("MediaTek「Dimensity 9600 Pro」", "2nm採用のスマホ向けチップ。旗艦採用が先端移行の証明に。"),
    ("SeresがAITO主導権を強化", "Huaweiブランド依存から独自の経営基盤へ。車載事業の構造的課題。"),
    ("OpenAI幹部が加拿… カナダDC建設示唆", "電力確保と税制優遇。西側のAI拠点分散化が進む。"),
    ("高金利下で光通信・半導体が逆行高", "AI需要は底堅いとの評価。特定セクターへの資金集中が継続。"),
    ("TSMC幹部「AIの直接寄与は限定的」", "極秘プロセス開発でのAI利用に慎重。現場のリスク管理重視。"),
    ("NVIDIA CEO「AI安全に新法不要」", "競争原理が自律的安全を促す。規制議論の行方に注目。"),
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
    <div class="date-badge">2026年9月16日（水）配信</div>
    <p class="osub">米10年債5%突破、Meta自社チップ、中東オイルショック、AIメモリ高密度化、Clarity法案否決</p>
  </div>
  <div class="ochips">
    <div class="chip"><img class="th" src="assets/concepts/yield-curve-twist.png" alt="">10年債5.045%</div>
    <div class="chip"><img class="th" src="assets/brands/companies/nvidia-hq.jpg" alt="">Meta MTIA</div>
    <div class="chip"><img class="th" src="assets/concepts/core-pce.png" alt="">WTI 105.83ドル</div>
    <div class="chip"><img class="th" src="assets/concepts/memory-price.png" alt="">512GB DDR5</div>
  </div>
</div>
</div>
'''

slices["s1"] = "\n" + label("s1", "Haiku") + f'''
<div class="slide">
{logo()}
<div class="wavebg"><img src="../../assets/brands/template/The_Great_Wave_off_Kanagawa.jpg" alt=""></div>
<div class="haiku-c">
<div class="haiku">米債利回りは五厘へ、五兆ドルのシジョウが<br>静かに揺らぎ始める瞬間を、<br>今夜ここで読み解く。</div>
  <div class="h-ann">— 本日の市場の一句 —</div>
</div>
</div>
'''

topics = [
    "米10年債5%突破と20年債過去最高入札 — 逆イールドの深層",
    "Meta自社チップMTIA投入とNVIDIA依存の転換点",
    "サウジ紅海港閉鎖と原油100ドル超え — オイルショック再燃",
    "マイクロン512GB DDR5実証 — AIメモリ高密度化の構造変化",
    "Clarity法案否決とビットコイン暴落 — 規制の空白が広がる",
]
photo_paths = [BOND, NVDA, PCE, MEM, PREDICT]
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

slices["s3"] = "\n" + label("s3", "今夜の五本柱") + f'''
<div class="slide">
{logo()}
<div class="chrome">
<div class="sec-title">利回りは上昇し、市場の信頼感に変化が生じている</div>
<div class="body col" style="gap:18px">
  <div class="hero-num">五本柱</div>
  <div class="hero-lab">中東リスクとAI投資の転換点、その両端にある「逆イールド」の深層と、規制の空白を今夜の五本柱で読み解く。</div>
  <div class="chips"><div class="chip">逆イールド</div><div class="chip">オイルショック</div><div class="chip">メモリ高密度化</div><div class="chip">規制の空白</div></div>
</div>
</div>
</div>
'''

slices["s4"] = "\n" + label("s4", "前日市況") + f'''
<div class="slide">
{logo()}
<div class="chrome">
<div class="sec-title">主要3指数は小幅安、エネルギーだけ+2.17%</div>
<div class="body col" style="gap:15px">
  <div class="idx-grid">
    <div class="idx-card"><div class="idx-name">S&amp;P 500</div><div class="idx-val">7,585.73</div><div class="idx-chg down">-0.45%</div></div>
    <div class="idx-card"><div class="idx-name">ダウ</div><div class="idx-val">52,093.11</div><div class="idx-chg down">-0.63%</div></div>
    <div class="idx-card"><div class="idx-name">ナスダック</div><div class="idx-val">25,981.57</div><div class="idx-chg down">-0.78%</div></div>
  </div>
  <div class="strip">
    <div class="mi"><span class="mn">VIX</span><span class="mv">17.2（+0.58%）</span></div>
    <div class="mi"><span class="mn">米10年債</span><span class="mv">5.0%（+0.71%）</span></div>
    <div class="mi"><span class="mn">WTI</span><span class="mv">105.48ドル</span></div>
    <div class="mi"><span class="mn">BTC</span><span class="mv">75,463ドル（-3.48%）</span></div>
  </div>
  <div class="note"><b>注:</b> 長期金利の上昇が重石。半導体関連の一部に資金が流入し、金利動向と企業業績のバランスを見極める局面。</div>
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
    + wtl_col("金曜夜", "インフレ", [ev("PCE", "mac", "個人消費支出", "予想上回れば利下げ後ずれ警戒。")], "today")
    + wtl_col("週後半", "決算", [ev("半導体", "ern", "AI需要の実態", "設備投資とガイダンスが分水嶺。")])
    + wtl_col("継続", "金利", [ev("10年債", "mac", "5%台の維持", "高止まりなら株式の割引率に直結。")])
    + wtl_col("注目", "資金", [ev("ローテーション", "ern", "安全・現金創出株へ", "選別相場の継続で資金の質が焦点。")], "next")
    + "</div>")
slices["s53"] = bright_slide("s53", "イベント1", "今週の節目", "金融政策と決算が重なる一週間", tl_body)
slices["s54"] = bright_slide("s54", "イベント2", "PCE", "インフレ沈静化のペースを測る", '<div class="body col" style="gap:18px">'
    '<div class="hero-num">PCEデータ</div>'
    '<div class="hero-lab">日本時間金曜夜の個人消費支出は利下げ時期の先読み材料。上回れば株式に重荷、落ち着けばリスク資産に資金流入が加速する。</div>'
    '<div class="chips"><div class="chip">利下げ後ずれ</div><div class="chip">リスク資産</div><div class="chip">資金流入</div></div></div>')
slices["s55"] = bright_slide("s55", "イベント3", "半導体", "AI設備投資の収益化を試す", '<div class="body col" style="gap:18px">'
    '<div class="hero-num">ガイダンス</div>'
    '<div class="hero-lab">週後半の半導体決算はAI需要の実態を確認する場。期待に応えれば追い風、伸び悩みなら高値圏の売り圧力が下落相場の引き金になり得る。</div>'
    '<div class="chips"><div class="chip">設備投資</div><div class="chip">収益化</div><div class="chip">高値警戒</div></div></div>')

slices["s47"] = '\n<div class="slabel">s47 — 免責事項</div>\n<div class="slide disclaimer">' + logo() + \
    '<div class="disc-body"><div class="disc-title">免責事項</div><div class="disc-text">本番組は金融・投資に関する情報提供とリテラシー向上を目的としたものであり、いかなる投資助言も行うものではありません。<br>投資の最終判断は、ご自身の責任において行ってください。</div><div class="ch-footer"><div class="fmark">SA</div><div class="ftx">Smart Assets 米国株投資チャンネル</div></div></div></div>'

for i in range(0, 57):
    key = f"s{i}"
    if key not in slices:
        raise RuntimeError(f"missing slice {key}")

out = {"date": "2026-09-16", "slices": slices}
dst = ISSUE / "production" / "visual-data.json"
dst.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="")
print(f"wrote {dst} ({dst.stat().st_size} bytes, {len(slices)} slices)")
