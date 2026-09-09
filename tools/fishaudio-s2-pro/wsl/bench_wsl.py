"""xiaomei-voice benchmark for the WSL2 server (compile vs eager).

Sends the same 122-char Japanese text used for the Windows baseline, with
the xiaomei reference voice, and prints per-request wall time + token stats
pulled from the server log.
"""
import base64
import json
import re
import sys
import time
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

REF_WAV = "/mnt/c/my_project/gen-contents/us-stock-daily/assets/cast_refs/xiaomei/ref_audio.wav"
REF_META = "/mnt/c/my_project/gen-contents/us-stock-daily/assets/cast_refs/xiaomei/ref_meta.json"
TEXT_FILE = "/mnt/c/my_project/gen-contents/tools/fishaudio-s2-pro/fish-speech/test130_text.txt"
SERVER_LOG = "/root/server.log"
URL = "http://127.0.0.1:8080/v1/tts"


def load_body(text, max_new_tokens):
    ref_audio = base64.b64encode(open(REF_WAV, "rb").read()).decode()
    ref_text = json.load(open(REF_META, encoding="utf-8"))["ref_text"]
    return json.dumps(
        {
            "text": text,
            "format": "wav",
            "chunk_length": 200,
            "max_new_tokens": max_new_tokens,
            "normalize": True,
            "references": [{"audio": ref_audio, "text": ref_text}],
        }
    ).encode("utf-8")


def log_size():
    try:
        return len(open(SERVER_LOG, "rb").read())
    except FileNotFoundError:
        return 0


def parse_log(since):
    with open(SERVER_LOG, encoding="utf-8", errors="replace") as f:
        f.seek(since)
        tail = f.read()
    out = {}
    m = re.findall(r"Generated (\d+) tokens in (\d+\.\d+) seconds", tail)
    if m:
        toks, secs = m[-1]
        out["tokens"] = int(toks)
        out["decode_s"] = float(secs)
        out["ms_per_tok"] = float(secs) * 1000 / int(toks)
    m = re.findall(r"Compilation time: (\d+\.\d+) seconds", tail)
    if m:
        out["compile_s"] = float(m[-1])
    m = re.findall(r"VQ decode: (\d+\.\d+)s", tail)
    if m:
        out["vq_s"] = float(m[-1])
    return out


def run(label, text, max_new_tokens, out_path):
    body = load_body(text, max_new_tokens)
    since = log_size()
    t0 = time.perf_counter()
    req = urllib.request.Request(
        URL, data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=5400) as resp:
        audio = resp.read()
    dt = time.perf_counter() - t0
    open(out_path, "wb").write(audio)
    stats = parse_log(since)
    print(
        f"[{label}] chars={len(text)} e2e={dt:.1f}s "
        f"tokens={stats.get('tokens')} decode={stats.get('decode_s')}s "
        f"ms/tok={stats.get('ms_per_tok') and round(stats['ms_per_tok'])} "
        f"compile={stats.get('compile_s')}s vq={stats.get('vq_s')}s "
        f"wav={len(audio) / 1024:.0f}KB -> {out_path}",
        flush=True,
    )


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "short"
    full_text = open(TEXT_FILE, encoding="utf-8-sig").read().strip()
    short = "本日の日経平均は前日比三百二十円高。"
    if mode in ("smoke", "both"):
        run("short-" + mode, short, 256, f"/root/out_short_{mode}.wav")
    if mode in ("long", "both"):
        run("long-" + mode, full_text, 1024, f"/root/out_long_{mode}.wav")
