# Prepare remotion/public/ for one episode:
#   1. screenshot visual.html slides (with per-cue state variants) via headless Chrome
#   2. copy TTS wavs, the fixed opening/ending mixes, and the transition sting
#   3. merge durations.json (measured) with segment-map.json -> remotion_input.json
# Run after tools/tts/generate_audio.py has produced production/audio/durations.json.
import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Dict, Optional, Tuple
from pathlib import Path

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
DAILY = Path(__file__).resolve().parents[2]  # us-stock-daily/
FPS = 30

# ffprobe is not on PATH; use the binary bundled with Remotion's compositor.
FFPROBE = DAILY / "remotion/node_modules/@remotion/compositor-win32-x64-msvc/ffprobe.exe"


# Remotion plays the fixed opening/ending voice+BGM mixes directly; the only
# raw BGM file it needs at render time is the standalone section sting.
BGM = {
    "sting": DAILY / "assets/bgm/transition/tr_04_technology_6s.mp3",
}

# S0 fixed opening background (vision-design.md §0.1, 2026-09-01).
# Auto-copied into the issue dir when visual.html references it but Phase 3 forgot.
OPENING_VISUAL_SRC = DAILY / "assets/brands/template/opening-visual.png"

WEEK_JA = ["月", "火", "水", "木", "金", "土", "日"]

# Opening cover slot (slide s0). Injected when the day's segment-map has no
# S00 opening (v3 pipeline maps). If the pre-mixed intro wav exists it drives
# the slot duration; otherwise the cover holds silently for this many seconds.
OPENING_SLIDE = "s0"
OPENING_WAV_NAME = "005_S00-intro.wav"
OPENING_FALLBACK_SEC = 6.0


def ffprobe_duration(path: Path) -> float:
    exe = str(FFPROBE) if FFPROBE.is_file() else "ffprobe"
    out = subprocess.run(
        [exe, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nk=1:nw=1", str(path)],
        capture_output=True, text=True,
    )
    if out.returncode != 0:
        raise RuntimeError(f"ffprobe failed for {path}: {out.stderr.strip()}")
    return float(out.stdout.strip())


def corner_of(seg_id: str) -> str:
    if seg_id.startswith(("S00", "S01")):
        return "OP"
    if seg_id.startswith(("S02", "S03")):
        return "A"
    # v3 id format (2026-09-03 onward): A-pN / B1-pN / C-pN / D-pN / END-*
    if seg_id.startswith("A-"):
        return "A"
    if re.match(r"^B\d-p", seg_id):
        return "B"
    if seg_id.startswith("C-"):
        return "C"
    if seg_id.startswith("D-"):
        return "D"
    if seg_id.startswith("S01"):
        return "OP"
    if seg_id.startswith("S37"):
        return "C"
    if seg_id.startswith("S38"):
        return "D"
    if seg_id.startswith("S39"):
        return "DISC"
    if seg_id.startswith("END"):
        return "ED"
    return "B"


def section_unit_of(seg_id: str) -> Optional[str]:
    """Theme-group identity, used to suppress in-group page stings.

    v3 ids give B1/B2/... directly; legacy S-ids use the S-number itself.
    """
    m = re.match(r"^(B\d+)-p", seg_id)
    if m:
        return m.group(1)
    m = re.match(r"^(S\d+)", seg_id)
    return m.group(1) if m else None


def should_play_sting(
    previous_slide: Optional[str], slide: Optional[str],
    previous_corner: Optional[str], corner: str,
    previous_unit: Optional[str] = None, unit: Optional[str] = None,
) -> bool:
    """Play a transition only at commentary section boundaries.

    Allowed boundaries are A->A, A->B, B->B, and B->C; a B->B sting requires
    the theme group itself to change (B1->B2, B2->B3, ...), not just the page.
    Other transitions (opening->A, C internal pages, C->D, ending) stay dry.
    """
    if previous_corner is None:
        return False
    if (previous_corner, corner) not in {
        ("A", "A"),
        ("A", "B"),
        ("B", "B"),
        ("B", "C"),
    }:
        return False
    # A B-group change (B1->B2, ...) always stings, even in the defensive
    # case where the group's first/last pages share one slide id.
    if previous_corner == "B" and corner == "B":
        return previous_unit != unit
    # Multiple narration segments can share one visual page. The sting marks
    # an actual page change, not every new narration paragraph.
    if previous_slide == slide:
        return False
    if previous_slide is None or slide is None:
        return False
    return True


def slide_state(
    slide: str, cue: str, seg_id: str
) -> Tuple[Optional[str], Optional[str]]:
    """Return (state key, kind) for the slide image (None = base)."""
    m = re.search(r"carousel idx=(\d)", cue)
    if m:
        return f"i{m.group(1)}", "carousel"
    m = re.search(r"news idx=(\d)", cue)
    if m:
        return f"i{m.group(1)}", "news"
    # Legacy 08-28 id/cue format (kept for reruns of older episodes).
    if slide == "s2":
        m = re.search(r"idx=(\d)", cue)
        if m:
            return f"i{m.group(1)}", "carousel"
        return ("i3" if ("close" in seg_id or "stays" in cue) else "i0"), "carousel"
    if slide == "s33":
        m = re.match(r"S37-C(\d)", seg_id)
        return (f"i{int(m.group(1)) - 1}" if m else "i0"), "news"
    return None, None


def state_js(slide: str, kind: str, idx: int) -> str:
    """JS that sets slide to its variant state before the screenshot."""
    if kind == "carousel":
        return (
            f"document.querySelectorAll('#{slide} .topic-item').forEach((el,i)=>{{"
            f"el.classList.toggle('active',i==={idx});"
            f"el.classList.toggle('dimmed',i!=={idx});}});"
            f"document.querySelectorAll('#{slide} .photo-frame').forEach((el,i)=>"
            f"el.classList.toggle('active',i==={idx}));")
    if kind == "news":
        return (
            f"document.querySelectorAll('#{slide} .n-item').forEach((el,i)=>{{"
            f"el.classList.toggle('active',i==={idx});"
            f"el.classList.toggle('dim',i!=={idx});}});")
    return ""


def _shot_order(png: str) -> Tuple[int, int, int]:
    """Sort base and delta shots as s0, s0_base, s0_i1, ... ."""
    m = re.match(r"(s\d+)(?:_i(\d+))?\.png", png)
    if not m:
        return (10**9, 0, 0)
    return (int(m.group(1)[1:]), 0 if m.group(2) is None else 1,
            int(m.group(2) or 0))


def capture_shots(
    issue_dir: Path, slides_dir: Path, seg_map: dict
) -> Dict[str, str]:
    """Capture one base PNG per slide and delta PNGs for changed states.

    Returns slide id -> base image path. Carousel/news state deltas are also
    captured and are resolved to exact state images during input assembly.
    """
    html_src = (issue_dir / "visual.html").read_text(encoding="utf-8")
    html_src = re.sub(r"<script>.*?</script>", "", html_src, flags=re.S)
    if "assets/concepts/opening-visual.png" in html_src:
        dst = issue_dir / "assets/concepts/opening-visual.png"
        if not dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(OPENING_VISUAL_SRC, dst)
            print("[copy] assets/concepts/opening-visual.png (fixed S0 background)")
    slides_dir.mkdir(parents=True, exist_ok=True)
    # Slide base shots are always needed. Carousel/news state shots are
    # collected from the actual segment timeline, so no stale variant can
    # leak into the render.
    want: Dict[str, Tuple[str, Optional[str], Optional[str], int]] = {}
    for sm in re.finditer(r'id="(s\d+)"', html_src):
        slide = sm.group(1)
        want[f"{slide}.png"] = (slide, None, None, -1)
    for seg in seg_map.get("segments", []):
        slide = seg.get("slide") or ""
        if not re.fullmatch(r"s\d+", slide):
            continue
        state, kind = slide_state(slide, seg.get("cue", ""), seg.get("id", ""))
        if state is None:
            continue
        idx = int(state.lstrip("i"))
        want[f"{slide}_{state}.png"] = (slide, state, kind, idx)

    base_images: Dict[str, str] = {}
    with tempfile.TemporaryDirectory() as tmp:
        # Temp HTML must sit next to visual.html so relative <img> paths
        # (assets/..., ../../assets/logo.png) still resolve.
        caps = []
        try:
            for png, (target, state, kind, idx) in sorted(
                want.items(), key=lambda kv: _shot_order(kv[0])
            ):
                css = (
                    "<style>.nav-bar,.slabel{display:none!important}"
                    ".slide-container{margin-top:0!important;padding:0!important;gap:0!important}"
                    f".swrap{{display:none!important}}#{target}{{display:block!important}}"
                    ".slide{border-radius:0!important;box-shadow:none!important}</style>")
                js = ""
                if kind:
                    js = (
                        "<script>document.addEventListener('DOMContentLoaded',()=>{"
                        + state_js(target, kind, idx)
                        + "});</script>")
                page = html_src.replace("</body>", f"{css}{js}</body>")
                cap = issue_dir / f".cap_{png}.html"
                caps.append(cap)
                cap.write_text(page, encoding="utf-8")
                out = slides_dir / png
                proc = subprocess.run(
                    [CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                     "--no-sandbox",
                     "--force-device-scale-factor=1", "--window-size=1920,1080",
                     "--virtual-time-budget=20000", f'--user-data-dir={tmp}/profile',
                     f"--screenshot={out}", cap.as_uri()],
                    capture_output=True, text=True, encoding="utf-8", errors="replace")
                if not out.exists() or out.stat().st_size < 10000:
                    print(f"[error] screenshot failed: {png} rc={proc.returncode} size={out.stat().st_size if out.exists() else 0}")
                    if proc.stdout.strip():
                        print(proc.stdout.strip())
                    if proc.stderr.strip():
                        print(proc.stderr.strip())
                    sys.exit(1)
                print(f"[shot] {png}")
                if state is None:
                    base_images[target] = f"assets/slides/{png}"
        finally:
            for c in caps:
                c.unlink(missing_ok=True)
    return base_images


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--issue", default="2026-08-28")
    ap.add_argument("--skip-shots", action="store_true")
    args = ap.parse_args()

    issue_dir = DAILY / "daily-output" / args.issue
    prod = issue_dir / "production"
    durations_path = prod / "audio" / "durations.json"
    if not durations_path.exists():
        print("[error] durations.json missing; run generate_audio.py first")
        return 1
    durations = json.loads(durations_path.read_text(encoding="utf-8-sig"))
    seg_map = json.loads((prod / "segment-map.json").read_text(encoding="utf-8-sig"))
    meas = {s["id"]: s for s in durations["segments"]}

    pub = DAILY / "remotion" / "public"
    for sub in (pub / "audio", pub / "bgm"):
        shutil.rmtree(sub, ignore_errors=True)
    if not args.skip_shots:
        shutil.rmtree(pub / "assets" / "slides", ignore_errors=True)
    (pub / "assets" / "slides").mkdir(parents=True, exist_ok=True)
    (pub / "bgm").mkdir(parents=True, exist_ok=True)
    (pub / "audio").mkdir(parents=True, exist_ok=True)

    if not args.skip_shots:
        base_images = capture_shots(issue_dir, pub / "assets" / "slides", seg_map)
    else:
        base_images = {}

    for kind in ("sting",):
        shutil.copy2(BGM[kind], pub / "bgm" / BGM[kind].name)
    shutil.copy2(DAILY / "assets" / "logo.png", pub / "assets" / "logo.png")
    shutil.copy2(DAILY / "assets" / "logo-white-bk.png", pub / "assets" / "logo-white-bk.png")
    fixed_opening = DAILY / "assets" / "audio" / "fixed" / "opening.wav"
    fixed_ending = DAILY / "assets" / "audio" / "fixed" / "ending.wav"
    fixed_ending_meta_path = fixed_ending.with_suffix(".json")
    sting_frames = round(ffprobe_duration(BGM["sting"]) * FPS)

    dt = datetime.date.fromisoformat(args.issue)
    date_ja = f"{dt.year}年{dt.month}月{dt.day}日（{WEEK_JA[dt.weekday()]}）"

    segments = []
    previous_slide: Optional[str] = None
    previous_corner: Optional[str] = None
    previous_unit: Optional[str] = None
    for meta in sorted(seg_map["segments"], key=lambda s: s["order"]):
        sid = meta["id"]
        # External slots (BGM-only, e.g. legacy S00-title) carry no audio and
        # no measured timing; the v3 voice-driven timeline starts at S00-intro.
        if meta.get("type") == "external":
            print(f"[skip] external slot {sid}")
            continue
        m = meas.get(sid)
        if m is None:
            print(f"[error] no measured timing for {sid}")
            return 1
        # Fixed intro replaces the daily opening narration when available.
        if sid == "S00-intro" and fixed_opening.is_file():
            print(f"[use] fixed opening asset: {fixed_opening.name}")
            m = {
                **m,
                "file": Path(os.path.relpath(fixed_opening, issue_dir)).as_posix(),
                "duration": ffprobe_duration(fixed_opening),
            }
        corner = corner_of(sid)
        unit = section_unit_of(sid)
        slide = meta.get("slide") or None
        cue = meta.get("cue", "")
        # Voice-driven timeline: every tts segment already carries its own
        # audio (intro/greeting wavs are pre-mixed with opening/ending BGM;
        # corner-change sting is pre-mixed into the page-head wavs).
        dur = m["duration"]
        audio = None
        wav = issue_dir / m["file"]
        if wav.exists():
            shutil.copy2(wav, pub / "audio" / wav.name)
            audio = f"audio/{wav.name}"
            # Opening/ending wavs contain BGM lead/tail, so the real file is
            # longer than the narration cursor in durations.json. The visual
            # slot must cover the full mixed audio.
            dur = max(dur, ffprobe_duration(wav))
        state, _kind = slide_state(slide, cue, sid)
        if slide is None:
            # No slide (END outro): image null -> Episode renders end card in code.
            image = None
        else:
            image = (
                f"assets/slides/{slide}_{state}.png"
                if state
                else base_images.get(
                    slide, f"assets/slides/{slide}.png"
                )
            )
            if not args.skip_shots and slide not in base_images:
                image = None
        sentences = [
            {"text": s["text"], "start": s["start"], "end": s["end"]}
            for s in m["sentences"] if s["end"] > s["start"]
        ]
        play_sting = should_play_sting(
            previous_slide, slide, previous_corner, corner,
            previous_unit, unit,
        )
        previous_slide = slide
        previous_corner = corner
        previous_unit = unit
        # New ending: one reusable fixed asset already contains disclaimer,
        # the 3.5s disclaimer hold, greeting, and looping BGM tail.
        if sid == "END-disclaimer" and fixed_ending.is_file():
            if not fixed_ending_meta_path.is_file():
                print("[error] fixed ending meta missing")
                return 1
            fixed_meta = json.loads(fixed_ending_meta_path.read_text(encoding="utf-8-sig"))
            segments.append({
                "order": meta["order"],
                "id": sid,
                "slide": slide,
                "image": image,
                "audio": f"audio/{fixed_ending.name}",
                "durationSec": round(float(fixed_meta["durationSec"]), 3),
                "timingSource": "measured",
                "title": meta.get("title", sid),
                "corner": corner,
                "sting": play_sting,
                "sentences": sentences,
                "stateKey": f"{slide}:{state}" if slide and state else f"{slide}:base",
                "endCardAtSec": round(float(fixed_meta["endCardAtSec"]), 3),
            })
            shutil.copy2(fixed_ending, pub / "audio" / fixed_ending.name)
            continue
        if sid == "END-outro":
            print("[skip] included in fixed END-disclaimer asset")
            continue
        # Ending slot: keep the disclaimer visual during the greeting, then
        # fade the end card in after speech while the BGM tail keeps playing.
        speech_end = sentences[-1]["end"] if sid in ("S39-greeting", "END-outro") and sentences else None
        segments.append({
            "order": meta["order"],
            "id": sid,
            "slide": slide,
            "image": image,
            "audio": audio,
            "durationSec": round(dur, 3),
            "timingSource": "measured",
            "title": meta.get("title", sid),
            "corner": corner,
            "sting": play_sting,
            "sentences": sentences,
            "stateKey": f"{slide}:{state}" if slide and state else f"{slide}:base",
        })
        if speech_end is not None:
            segments[-1]["speechEndSec"] = round(speech_end, 3)

    # Template guarantee: the video always opens on the s0 cover. Days whose
    # segment-map already contains an s0 segment (e.g. S00-intro) pass through.
    if not any(s.get("slide") == OPENING_SLIDE for s in segments):
        opening_audio = None
        opening_dur = OPENING_FALLBACK_SEC
        opening_source = "fallback"
        # Reusable fixed asset first; the daily intro wav is the legacy path.
        opening_wav = fixed_opening
        if not opening_wav.is_file():
            opening_wav = issue_dir / "production" / "audio" / OPENING_WAV_NAME
        if opening_wav.exists():
            shutil.copy2(opening_wav, pub / "audio" / opening_wav.name)
            opening_audio = f"audio/{opening_wav.name}"
            opening_dur = ffprobe_duration(opening_wav)
            opening_source = "measured"
        segments.insert(0, {
            "order": 0,
            "id": "S00-intro",
            "slide": OPENING_SLIDE,
            "image": f"assets/slides/{OPENING_SLIDE}.png",
            "audio": opening_audio,
            "durationSec": round(opening_dur, 3),
            "timingSource": opening_source,
            "title": "番組紹介（固定文言）",
            "corner": "OP",
            "sting": False,
            "sentences": [],
        })

    input_json = {
        "episode": args.issue,
        "dateJa": date_ja,
        "fps": FPS,
        "width": 1920,
        "height": 1080,
        # BGM is pre-mixed into the opening/ending/sting wavs; no global bed.
        "bgmBed": None,
        "stingFile": f"bgm/{BGM['sting'].name}",
        "stingFrames": sting_frames,
        "segments": segments,
    }
    total = sum(s["durationSec"] for s in segments)
    # no BOM here: webpack JSON.parse would choke on one
    (pub / "remotion_input.json").write_text(
        json.dumps(input_json, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[done] {len(segments)} segments, total {total / 60:.1f} min -> {pub / 'remotion_input.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
