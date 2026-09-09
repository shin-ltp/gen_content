import wave
from pathlib import Path

import numpy as np


SAMPLE_RATE = 48000
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "assets" / "bgm" / "_audition" / "transition_synth_candidates"
DURATION = 3.2


def bell(freq, duration, decay, partials, detune_cents=0.0):
    t = np.arange(int(duration * SAMPLE_RATE)) / SAMPLE_RATE
    out = np.zeros_like(t)
    ratio_shift = 2 ** (detune_cents / 1200)
    for ratio, amp, damp in partials:
        f = freq * ratio * ratio_shift
        if f >= SAMPLE_RATE * 0.47:
            continue
        rate = decay * damp
        out += amp * np.sin(2 * np.pi * f * t) * np.exp(-rate * t)
    return out


def strike(duration):
    t = np.arange(int(duration * SAMPLE_RATE)) / SAMPLE_RATE
    noise = np.random.default_rng(7).normal(0, 1, len(t))
    return noise * np.exp(-t / 0.004)


def place(buffer, sound, start, amp, pan=0.0):
    offset = int(start * SAMPLE_RATE)
    end = min(offset + len(sound), len(buffer))
    left_gain = np.sqrt((1 - pan) / 2)
    right_gain = np.sqrt((1 + pan) / 2)
    buffer[offset:end, 0] += sound[: end - offset] * amp * left_gain
    buffer[offset:end, 1] += sound[: end - offset] * amp * right_gain


def add_reverb(buffer):
    rng = np.random.default_rng(19)
    ir_len = int(0.30 * SAMPLE_RATE)
    ir_t = np.arange(ir_len) / SAMPLE_RATE
    result = buffer.copy()
    for ch, seed in enumerate((31, 53)):
        ir = rng.normal(0, 1, ir_len) * np.exp(-ir_t / 0.09)
        n = len(buffer) + ir_len - 1
        wet = np.fft.irfft(np.fft.rfft(buffer[:, ch], n) * np.fft.rfft(ir, n))[: len(buffer)]
        result[:, ch] += 0.13 * wet
    return result


G5, A5, C6, D6, E6, G6, C7 = 783.99, 880.00, 1046.50, 1174.66, 1318.51, 1567.98, 2093.00

MALLETS = ((1, 1.0, 4.5), (2.76, 0.28, 7.0), (5.40, 0.10, 11.0))
GLOCK = ((1, 1.0, 3.2), (2.76, 0.22, 5.5), (5.40, 0.09, 9.0))
CELESTA = ((1, 1.0, 2.6), (2.00, 0.35, 3.8), (4.01, 0.10, 6.5))
WOOD = ((1, 1.0, 8.0), (4.02, 0.14, 14.0))


def make_candidate(kind):
    n = int(DURATION * SAMPLE_RATE)
    buf = np.zeros((n, 2))
    click = strike(0.012)

    if kind == "c11_bright_mallet_asc":
        notes = [(0.00, G5, 0.72, -0.15), (0.16, A5, 0.72, 0.15), (0.32, C6, 0.85, -0.15), (0.50, D6, 0.95, 0.15)]
        for start, freq, amp, pan in notes:
            place(buf, bell(freq, 2.2, 5, MALLETS), start, amp, pan)
            place(buf, click, start, amp * 0.10, pan)
        place(buf, bell(G6, 2.2, 6, GLOCK), 0.72, 0.38, 0)

    elif kind == "c12_marimba_pop":
        notes = [(0.00, E6, 0.80, -0.20), (0.18, C6, 0.80, 0.20), (0.36, G6, 0.95, 0)]
        for start, freq, amp, pan in notes:
            place(buf, bell(freq, 1.8, 8, WOOD), start, amp, pan)
            place(buf, click, start, amp * 0.14, pan)
        place(buf, bell(C7, 1.8, 7, GLOCK), 0.60, 0.35, 0)

    elif kind == "c13_celesta_shimmer":
        notes = [(0.00, C6, 0.58, -0.25), (0.14, G5, 0.58, 0.25), (0.28, E6, 0.66, -0.15)]
        for start, freq, amp, pan in notes:
            place(buf, bell(freq, 2.6, 3, CELESTA, -4), start, amp, pan)
            place(buf, bell(freq, 2.6, 3, CELESTA, 4), start, amp * 0.85, pan)
        place(buf, bell(G6, 2.6, 2.4, CELESTA, -3), 0.52, 0.78, 0.10)
        place(buf, bell(G6, 2.6, 2.4, CELESTA, 3), 0.52, 0.68, -0.10)

    elif kind == "c14_two_tone_call":
        place(buf, bell(G5, 2.4, 4, MALLETS), 0.00, 0.80, -0.18)
        place(buf, click, 0.00, 0.09, -0.18)
        place(buf, bell(D6, 2.4, 4, MALLETS), 0.30, 0.86, 0.18)
        place(buf, click, 0.30, 0.10, 0.18)
        place(buf, bell(G6, 2.4, 3, GLOCK), 0.62, 0.72, 0)
        place(buf, bell(D6, 2.4, 5, GLOCK), 0.86, 0.20, 0)

    buf = add_reverb(buf)
    buf = np.tanh(buf * 1.15) * 0.85
    return buf


def write_wav(path, audio):
    data = np.clip(audio, -1, 1)
    pcm = (data * 32767).astype("<i2")
    with wave.open(str(path), "wb") as f:
        f.setnchannels(2)
        f.setsampwidth(2)
        f.setframerate(SAMPLE_RATE)
        f.writeframes(pcm.tobytes())


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    kinds = ["c11_bright_mallet_asc", "c12_marimba_pop", "c13_celesta_shimmer", "c14_two_tone_call"]
    for kind in kinds:
        audio = make_candidate(kind)
        write_wav(OUTPUT_DIR / f"{kind}.wav", audio)
        print(f"wrote {kind}.wav")


if __name__ == "__main__":
    main()
