"""Measure how far audio sits from video in a real clip.

Plays a source whose white flashes and tone bursts start on the same frame,
records it through the normal pipeline, then finds each flash and each burst in
the result. A positive offset means the sound arrives late.
"""
import array
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import nabd  # noqa: E402

ffmpeg = nabd.find_ffmpeg()
ffplay = ffmpeg.replace("ffmpeg.exe", "ffplay.exe")
OUT = Path(__file__).resolve().parent / "out"
SOURCE = OUT / "sync_source.mp4"
FPS = 60
PERIOD = 2.0          # seconds between flashes
FLASH = 0.05          # flash / burst length
RECORD = 13


def build_source():
    OUT.mkdir(parents=True, exist_ok=True)
    if SOURCE.exists():
        return
    # Flashes and bursts both gated on the same expression, so they are
    # simultaneous by construction.
    gate = f"lt(mod(t+1\\,{PERIOD})\\,{FLASH})"
    subprocess.run(
        [ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
         "-f", "lavfi", "-i", f"color=black:s=1280x720:r={FPS}:d=12",
         "-f", "lavfi", "-i", "sine=frequency=1000:duration=12",
         "-filter_complex",
         f"[0:v]drawbox=x=0:y=0:w=iw:h=ih:color=white:t=fill:enable='{gate}'[v];"
         f"[1:a]volume='if({gate}\\,1\\,0)':eval=frame[a]",
         "-map", "[v]", "-map", "[a]",
         "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
         "-c:a", "aac", str(SOURCE)],
        capture_output=True, creationflags=nabd.CREATE_NO_WINDOW)


def brightness(path):
    """(pts_time, average luma) per frame.

    Uses real presentation timestamps: deriving them from an assumed frame rate
    drifts against a clip that is not exactly 60fps, which shows up as markers
    that creep apart over the recording.
    """
    # Two passes over the same decode order rather than one lavfi graph: a
    # Windows drive letter cannot be escaped reliably into a movie= source.
    probe = ffmpeg.replace("ffmpeg.exe", "ffprobe.exe")
    stamps = subprocess.run(
        [probe, "-v", "error", "-select_streams", "v:0",
         "-show_entries", "frame=pts_time", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, creationflags=nabd.CREATE_NO_WINDOW)
    times = []
    for line in stamps.stdout.splitlines():
        try:
            times.append(float(line.strip().rstrip(",")))
        except ValueError:
            pass

    pixels = subprocess.run(
        [ffmpeg, "-hide_banner", "-loglevel", "error", "-i", str(path),
         "-vf", "scale=1:1,format=gray", "-f", "rawvideo", "-"],
        capture_output=True, creationflags=nabd.CREATE_NO_WINDOW)
    lum = list(pixels.stdout)

    if not times or not lum:
        print(f"  brightness probe failed: frames={len(times)} pixels={len(lum)}"
              f"  {stamps.stderr.strip()[:120]}")
        return []
    return list(zip(times, lum))


def envelope(path):
    res = subprocess.run(
        [ffmpeg, "-hide_banner", "-loglevel", "error", "-i", str(path),
         "-vn", "-ac", "1", "-ar", "48000", "-f", "s16le", "-"],
        capture_output=True, creationflags=nabd.CREATE_NO_WINDOW)
    samples = array.array("h")
    samples.frombytes(res.stdout[:len(res.stdout) // 2 * 2])
    return samples


def rising_edges(values, times, threshold, min_gap):
    edges, last = [], -999
    for v, t in zip(values, times):
        if v >= threshold and t - last > min_gap:
            edges.append(t)
            last = t
    return edges


BIN = 0.005          # 5 ms analysis grid
MAX_LAG = 0.600      # search +/- 600 ms


def correlate(path):
    """Lag that best aligns the video flash train with the audio burst train.

    Threshold-free, so it does not care how loud the tone came back or what
    else was on screen. Positive means audio arrives later than video.
    """
    frames = brightness(path)
    samples = envelope(path)
    if not frames or not samples:
        return None

    span = frames[-1][0]
    n = int(span / BIN)
    if n < 100:
        return None

    vid = [0.0] * n
    for t, lum in frames:
        i = int(t / BIN)
        if 0 <= i < n:
            vid[i] = max(vid[i], float(lum))

    aud = [0.0] * n
    step = int(48000 * BIN)
    for i in range(n):
        chunk = samples[i * step:(i + 1) * step]
        if chunk:
            aud[i] = float(max(abs(min(chunk)), abs(max(chunk))))

    def normalise(xs):
        mean = sum(xs) / len(xs)
        centred = [x - mean for x in xs]
        mag = sum(x * x for x in centred) ** 0.5
        return [x / mag for x in centred] if mag else centred

    vid, aud = normalise(vid), normalise(aud)

    lags = int(MAX_LAG / BIN)
    best_lag, best_score = 0, -2.0
    for lag in range(-lags, lags + 1):
        score = 0.0
        for i in range(max(0, -lag), min(n, n - lag)):
            score += vid[i] * aud[i + lag]
        if score > best_score:
            best_score, best_lag = score, lag
    return best_lag * BIN, best_score


def analyse(path):
    frames = brightness(path)
    if not frames:
        return None
    v_times = [t for t, _ in frames]
    lum = [v for _, v in frames]
    peak, floor = max(lum), min(lum)
    if peak - floor < 40:
        print("  no flashes found in the recording")
        return None
    flashes = rising_edges(lum, v_times, floor + (peak - floor) * 0.6, PERIOD / 2)

    samples = envelope(path)
    if not samples:
        return None
    # 1 ms windows, then keep only sustained runs. A single loud window is
    # noise; a tone burst stays loud for tens of milliseconds.
    win = 48
    amps = []
    for i in range(0, len(samples) - win, win):
        chunk = samples[i:i + win]
        amps.append(max(abs(min(chunk)), abs(max(chunk))))
    loudest = max(amps) if amps else 0
    if loudest < 500:
        print("  no tone bursts found in the recording")
        return None

    threshold = loudest * 0.5
    min_run = 15          # ms a genuine burst must sustain
    bursts, run_start = [], None
    for i, amp in enumerate(amps):
        if amp >= threshold:
            if run_start is None:
                run_start = i
        else:
            if run_start is not None and i - run_start >= min_run:
                bursts.append(run_start / 1000)
            run_start = None
    if run_start is not None and len(amps) - run_start >= min_run:
        bursts.append(run_start / 1000)

    print(f"  flashes at: {', '.join(f'{t:.3f}' for t in flashes[:6])}")
    print(f"  bursts  at: {', '.join(f'{t:.3f}' for t in bursts[:6])}")

    offsets = []
    for f in flashes:
        near = min(bursts, key=lambda b: abs(b - f), default=None)
        if near is not None and abs(near - f) < PERIOD / 2:
            offsets.append(near - f)
    return offsets


def record(seconds, offset_ms=0):
    cfg = nabd.load_config()
    cfg["clip_seconds"] = 120
    cfg["output_dir"] = str(OUT)
    cfg["save_delay"] = 2.0
    cfg["audio_offset_ms"] = offset_ms
    # Room noise on the mic swamps the tone bursts and ruins onset detection.
    cfg["capture_mic"] = False

    rec = nabd.Recorder(cfg, ffmpeg)
    clip = nabd.Clipper(cfg, ffmpeg, rec)
    before = {p.name for p in OUT.glob("nab_*.mp4")}
    rec.clear_buffer()
    rec.start()
    time.sleep(2)

    player = subprocess.Popen(
        [ffplay, "-i", str(SOURCE), "-fs", "-autoexit", "-loglevel", "quiet"],
        creationflags=nabd.CREATE_NO_WINDOW)
    time.sleep(seconds)
    try:
        player.kill()
    except OSError:
        pass

    done = []
    clip.save(on_done=lambda ok, d: done.append(ok))
    for _ in range(80):
        if done:
            break
        time.sleep(0.25)
    rec.stop()
    if not done or not done[0]:
        return None
    return max((p for p in OUT.glob("nab_*.mp4") if p.name not in before),
               key=lambda p: p.stat().st_mtime)


def measure(offset_ms=0):
    path = record(RECORD, offset_ms)
    if not path:
        print("  could not record")
        return None
    offsets = analyse(path)
    if not offsets:
        print("  could not locate markers")
        return None
    offsets.sort()
    median = offsets[len(offsets) // 2]
    print(f"  offsets (ms): {', '.join(f'{o*1000:+.0f}' for o in offsets)}")
    print(f"  median: {median*1000:+.0f} ms "
          f"({'audio late' if median > 0 else 'audio early'})")
    return median


def main():
    print("building sync source...")
    build_source()

    # The detector carries a small bias of its own (grid granularity plus
    # encoder priming); measure it on the source so it can be subtracted.
    base = correlate(SOURCE)
    if not base:
        print("FAIL: cannot read the source; measurement would be meaningless")
        sys.exit(1)
    base_lag, base_score = base
    print(f"source self-check: lag {base_lag*1000:+.0f} ms "
          f"(correlation {base_score:.2f})")
    if base_score < 0.2:
        print("FAIL: markers do not correlate even in the source")
        sys.exit(1)

    print(f"\nrecording {RECORD}s with audio_offset_ms=0")
    path = record(RECORD, 0)
    if not path:
        print("FAIL: could not record")
        sys.exit(1)

    found = correlate(path)
    if not found:
        print("FAIL: could not analyse the recording")
        sys.exit(1)
    lag, score = found
    print(f"  recorded lag: {lag*1000:+.0f} ms (correlation {score:.2f})")
    if score < 0.15:
        print("  WARNING: weak correlation; treat this number with suspicion")

    true_offset = lag - base_lag
    print(f"\n  pipeline offset: {true_offset*1000:+.0f} ms "
          f"({'audio late' if true_offset > 0 else 'audio early'})")

    # Now prove the correction lands, using whatever the config ships with.
    applied = int(nabd.load_config().get("audio_offset_ms", 0))
    print(f"\nrecording {RECORD}s with audio_offset_ms={applied}")
    path2 = record(RECORD, applied)
    if not path2:
        print("  could not record the verification pass")
        return
    found2 = correlate(path2)
    if not found2:
        print("  could not analyse the verification pass")
        return
    lag2, score2 = found2
    residual = lag2 - base_lag
    print(f"  recorded lag: {lag2*1000:+.0f} ms (correlation {score2:.2f})")
    print(f"\n  before {true_offset*1000:+.0f} ms  ->  after "
          f"{residual*1000:+.0f} ms")
    if abs(residual) < abs(true_offset):
        print(f"  improvement: {(abs(true_offset)-abs(residual))*1000:.0f} ms "
              f"closer to aligned")
    else:
        print("  no improvement - the offset is not behaving as a constant")


if __name__ == "__main__":
    main()

