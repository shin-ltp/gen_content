"""Generate concept images for 2026-08-19 show via imagegen (qwen-image-3.0-pro)."""
import subprocess
import sys
from pathlib import Path

IMAGEGEN = Path(r"D:\work\gen_content\us-stock-daily\tools\imagegen\imagegen.py")
OUT = Path(r"D:\work\gen_content\us-stock-daily\daily-output\2026-08-19\assets\concepts")
OUT.mkdir(parents=True, exist_ok=True)

# (file, width, height, prompt)
JOBS = [
    (
        "discount-rate.png", 1600, 900,
        "Premium financial editorial concept art, dark navy background #0A1628. "
        "A giant glowing golden coin dissolving into smaller particles as it travels "
        "through a long corridor of rising red interest-rate pillars, symbolizing "
        "the discounting of future cash flows. Cinematic lighting, photorealistic 3D "
        "render, refined and premium. No text, no numbers, no letters, no watermark.",
    ),
    (
        "bubble-history.png", 1600, 900,
        "Premium financial editorial concept art, dark navy background #0A1628. "
        "Five iridescent soap bubbles of different sizes arranged in a timeline, "
        "each bubble reflecting a golden rising bond-yield curve inside, the largest "
        "bubble at the apex about to burst. Symbolic of historical financial bubbles "
        "peaking during rising rate eras. Cinematic, photorealistic 3D render, "
        "premium. No text, no numbers, no letters, no watermark.",
    ),
    (
        "capital-curve.png", 1600, 900,
        "Premium financial editorial concept art, dark navy background #0A1628. "
        "A sweeping golden capital flow curve arcing over a miniature landscape of "
        "railway tracks transforming into glowing fiber-optic data cables, symbolizing "
        "the AI infrastructure financing cycle compared to the 19th century railway "
        "boom. Cinematic, photorealistic 3D render, refined. No text, no numbers, "
        "no letters, no watermark.",
    ),
    (
        "k-shaped-consumption.png", 1600, 900,
        "Premium financial editorial concept art, light cream background #FAF6EE. "
        "A stylized glowing letterless K-shaped divergence: the upper branch rises "
        "with golden luxury shopping bags and premium cards, the lower branch falls "
        "into muted grey with empty wallets. Clean editorial illustration style, "
        "sophisticated, high-end. No text, no numbers, no letters, no watermark.",
    ),
    (
        "opening-visual.png", 1600, 900,
        "Premium financial editorial wide shot, dark navy background #0A1628. "
        "A dramatic aerial view of Wall Street and the New York Stock Exchange area "
        "at dusk with warm golden window lights, subtle red and green candlestick-like "
        "light trails flowing through the streets. Cinematic, photorealistic, "
        "blockbuster atmosphere. No text, no numbers, no letters, no watermark.",
    ),
]


def main() -> int:
    failed = []
    for name, w, h, prompt in JOBS:
        dest = OUT / name
        if dest.exists() and dest.stat().st_size > 50000:
            print(f"[{name}] exists, skip", flush=True)
            continue
        print(f"\n=== {name} ===", flush=True)
        r = subprocess.run(
            [sys.executable, str(IMAGEGEN), prompt, "-o", str(dest),
             "--width", str(w), "--height", str(h)],
            capture_output=False,
        )
        if r.returncode != 0 or not dest.exists() or dest.stat().st_size < 50000:
            failed.append(name)
            print(f"  FAILED {name}", flush=True)
    print("\n=== SUMMARY ===", flush=True)
    for f in sorted(OUT.glob("*.png")):
        print(f"{f.name} {f.stat().st_size // 1024} KB", flush=True)
    if failed:
        print(f"FAILED: {', '.join(failed)}", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
