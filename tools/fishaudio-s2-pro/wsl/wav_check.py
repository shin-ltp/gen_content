import sys
import wave

for f in sys.argv[1:]:
    w = wave.open(f)
    n = w.readframes(w.getnframes())
    # 16-bit mono RMS via struct-free approach
    import array

    a = array.array("h")
    a.frombytes(n[: len(n) // 2 * 2])
    rms = int((sum(x * x for x in a[::7]) / max(1, len(a[::7]))) ** 0.5)
    print(
        f.split("/")[-1],
        w.getframerate(),
        "Hz",
        w.getnchannels(),
        "ch",
        "dur=",
        round(w.getnframes() / w.getframerate(), 2),
        "s rms~",
        rms,
    )
