"""裁剪并归一化 BGM 素材。

所有裁剪点按 BPM 小节线对齐（Kevin MacLeod / incompetech, CC BY 4.0）。
两遍 loudnorm（linear 模式）: 片头/片尾/转场 -16 LUFS, 解说垫乐 -20 LUFS。
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(r"C:\my_project\gen-contents\us-stock-daily\assets\bgm")
SRC = ROOT / "_original"

# (输出相对路径, 源文件, in秒, out秒, 淡入秒, 淡出秒, 目标LUFS, 小节长秒)
JOBS = [
    # ---- 片头 S00-title ----
    ("opening/open_01_inspired_30sec.mp3", "Inspired.mp3",
     0.0, 30.0, 0.05, 2.0, -16, 2.0),
    ("opening/open_02_life-of-riley_31sec.mp3", "Life of Riley.mp3",
     0.0, 30.588, 0.05, 2.353, -16, 4 * 60 / 102),
    ("opening/open_03_news-theme_27sec.mp3", "News Theme.mp3",
     0.0, 27.0, 0.03, 0.15, -16, 4 * 60 / 124),
    # ---- 片尾 END-outro ----
    ("ending/end_01_and-awaken_28sec.mp3", "And Awaken.mp3",
     0.0, 28.24, 0.05, 0.8, -16, 0),
    ("ending/end_02_bright-wish_40sec.mp3", "Bright Wish.mp3",
     0.0, 40.0, 0.03, 0.8, -16, 0),
    ("ending/end_03_daytime-tv-theme_46sec.mp3", "Daytime TV Theme.mp3",
     0.0, 45.9, 0.03, 0.5, -16, 0),
    # ---- 转场（B セクション間 / コーナー切り替わり）----
    ("transition/tr_01_loping-sting_4sec.mp3", "Loping Sting.mp3",
     0.0, 4.1, 0.01, 0.15, -16, 0),
    ("transition/tr_02_light-sting_6sec.mp3", "Light Sting.mp3",
     0.99, 6.316, 0.03, 0.8, -16, 4 * 60 / 114),
    ("transition/tr_03_news-sting_5sec.mp3", "NewsSting.mp3",
     0.40, 5.2, 0.02, 0.8, -16, 4 * 60 / 150),
    ("transition/tr_04_there-it-is_6sec.mp3", "There It Is.mp3",
     0.48, 6.95, 0.02, 0.5, -16, 4 * 60 / 130),
    # ---- 解说垫乐（任意）----
    ("bed/bed_01_easy-lemon_120sec.mp3", "Easy Lemon.mp3",
     0.0, 120.0, 1.5, 3.0, -20, 4 * 60 / 82),
    ("bed/bed_02_tech-live_97sec.mp3", "Tech Live.mp3",
     0.0, 96.774, 1.5, 3.0, -20, 4 * 60 / 124),
]


def run(cmd: list[str]) -> str:
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf8", errors="replace")
    if p.returncode != 0:
        raise RuntimeError(p.stderr[-2000:])
    return p.stderr


def measure(inp: str, out: str, fi: float, fo: float, o: float, target: float) -> dict:
    dur = round(o - inp, 3)
    chain = (
        f"afade=t=in:d={fi},afade=t=out:st={dur - fo:.3f}:d={fo},"
        f"loudnorm=I={target}:TP=-1.5:LRA=11:print_format=json"
    )
    log = run(["ffmpeg", "-hide_banner", "-nostats", "-ss", str(inp), "-t", str(dur),
               "-i", out_src(out), "-af", chain, "-f", "null", "-"])
    blk = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", log, re.S)
    if not blk:
        raise RuntimeError(f"loudnorm JSON not found for {out}\n{log[-1500:]}")
    j = json.loads(blk.group(0))
    return {"measured_I": j["input_i"], "measured_TP": j["input_tp"],
            "measured_LRA": j["input_lra"], "measured_thresh": j["input_thresh"]}


def out_src(name: str) -> str:
    return str(SRC / name)


def build() -> None:
    report = []
    for rel, src_name, inp, o, fi, fo, target, bar in JOBS:
        m = measure(inp, src_name, fi, fo, o, target)
        dur = round(o - inp, 3)
        chain = (
            f"afade=t=in:d={fi},afade=t=out:st={dur - fo:.3f}:d={fo},"
            f"loudnorm=I={target}:TP=-1.5:LRA=11:linear=true"
            f":measured_I={m['measured_I']}:measured_TP={m['measured_TP']}"
            f":measured_LRA={m['measured_LRA']}:measured_thresh={m['measured_thresh']}"
            f",aresample=44100"
        )
        dst = ROOT / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        run(["ffmpeg", "-y", "-hide_banner", "-nostats", "-ss", str(inp), "-t", str(dur),
             "-i", out_src(src_name), "-af", chain, "-c:a", "libmp3lame", "-b:a", "320k",
             str(dst)])
        # 検証: 実際の長さ/サンプルレート
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries",
             "format=duration:stream=sample_rate,channels", "-of", "json", str(dst)],
            capture_output=True, text=True)
        info = json.loads(probe.stdout)
        report.append({
            "file": rel, "src": src_name, "dur": info["format"]["duration"],
            "in": inp, "out": o, "target": target,
            "pre": m, "bar": bar,
        })
        print(f"OK {rel}  {float(info['format']['duration']):.2f}s  (src {src_name})")
    (ROOT / "_research" / "build_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    build()
