# Spotcheck for a rendered episode: duration sanity + stills at cut boundaries.
# Usage: python -X utf8 spotcheck_episode.py --date YYYY-MM-DD [path-to-mp4]
import argparse
import json
import random
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
COMPOSITOR = ROOT / 'remotion/node_modules/@remotion/compositor-win32-x64-msvc'
FFPROBE = COMPOSITOR / 'ffprobe.exe'
FFMPEG = COMPOSITOR / 'ffmpeg.exe'


def probe(exe: Path, path: Path) -> dict:
    result = subprocess.run(
        [str(exe), '-v', 'error', '-show_entries',
         'format=duration:stream=codec_type,codec_name', '-of', 'json', str(path)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--date', required=True)
    parser.add_argument('mp4', nargs='?')
    args = parser.parse_args()

    prod = ROOT / 'daily-output' / args.date / 'production'
    default_mp4 = ROOT / 'daily-output' / args.date / 'episode.mp4'
    mp4 = Path(args.mp4) if args.mp4 else default_mp4
    assert mp4.is_file(), f'missing {mp4}'

    info = probe(FFPROBE, mp4)
    duration = float(info['format']['duration'])
    print(f'mp4 duration: {duration / 60:.1f} min ({duration:.1f}s)')
    print('streams:', ', '.join(
        f"{stream['codec_type']}={stream['codec_name']}" for stream in info['streams']
    ))

    input_path = ROOT / 'remotion/public/remotion_input.json'
    episode_input = json.loads(input_path.read_text(encoding='utf-8'))
    fps = episode_input['fps']
    flip = 16
    sting_frames = episode_input['stingFrames']
    expected = sum(
        round(segment['durationSec'] * fps) + 2 * flip
        + (sting_frames + fps if segment['sting'] else 0)
        for segment in episode_input['segments']
    ) / fps
    total = expected
    print(f'expected by frames: {expected:.1f}s; diff {abs(expected - duration):.1f}s')
    assert abs(expected - duration) < 2.0, 'duration mismatch > 2s vs frame math'

    out_dir = prod / 'spotcheck'
    out_dir.mkdir(exist_ok=True)
    cuts = [0.0, 60.0]
    accumulated = 0.0
    for segment in episode_input['segments']:
        accumulated += segment['durationSec']
        cuts.append(accumulated)

    random.seed(3)
    segments = episode_input['segments']
    extra = sorted(random.sample(range(len(segments)), 6))
    accumulated = 0.0
    for index, segment in enumerate(segments):
        if index in extra:
            cuts.append(accumulated + segment['durationSec'] / 2)
        accumulated += segment['durationSec']

    cuts = sorted(set(round(value, 2) for value in cuts if 0 < value < total - 0.5))
    for timestamp in cuts:
        name = out_dir / f'still_{int(timestamp * 10):06d}.png'
        result = subprocess.run(
            [str(FFMPEG), '-v', 'error', '-ss', str(timestamp), '-i', str(mp4),
             '-frames:v', '1', '-y', str(name)],
            capture_output=True, text=True,
        )
        passed = name.is_file() and name.stat().st_size > 20000
        print(f'still t={timestamp:8.2f}s -> {name.name} {"OK" if passed else "FAIL/SMALL"}')
    print('spotcheck done:', len(cuts), 'stills in', out_dir)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
