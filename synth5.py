"""nab'd capture sound v5 -- deeper, and the exit is the entry backwards.

v3 played the exit in the same order as the entry (air, then the fall). That
is a repeat, not an inverse. Playing the phrase backwards means the last thing
in is the first thing out:

    ENTRY                             EXIT
      0   line slides out    air        3200  ring winds back    B4   <- resolve
    320   card rises          E4        3630  card collapses     E4   <- gesture
    900   ring completes      B4        3900  line withdraws    air   <- air

Read down the entry and up the exit: air, E4, B4 | B4, E4, air. The entry
climbs a fifth and the exit walks back down it, and the breath that opened the
banner is the thing that closes it.

Two octaves below the first pass now: E3/B3 over an E2, lowpassed at 1.2 kHz.
The second harmonic of E3 is 330 Hz -- the fundamental of the last version --
so the tone still speaks on a laptop speaker while the *perceived* pitch sits
an octave lower. Nothing in the file is sharp enough to interrupt anything.

Attacks are 28-70 ms of raised cosine. Nothing here is struck; it arrives.
The exit runs 9-12 dB under the entry -- an answer, not a second announcement.
"""
import numpy as np, wave, pathlib
from scipy import signal

SR = 48_000
PEAK = 10 ** (-12 / 20)          # winsound has no volume; file level IS level
LEN_MS = 4120                    # == the banner's TOTAL_MS, deliberately.
# The banner is a fresh process per nab and calls root.destroy() at TOTAL_MS.
# Async playback dies with the process, so a file even slightly longer than the
# animation gets its tail cut off. Making the two exactly equal removes the
# whole problem -- no lingering process, no trailing silence, nothing clipped.

# banner beats (BANNER-MOTION.md §3), entry then its mirror
AIR_IN, CARD, RING       = 0, 320, 900
UNRING, COLLAPSE, AIR_OUT = 3200, 3630, 3890

SUB, ROOT, FIFTH = 82.41, 164.81, 246.94        # E2 / E3 / B3 -- another octave down

def t(ms):  return np.arange(int(SR * ms / 1000)) / SR
def sine(f, x): return np.sin(2 * np.pi * f * x)
def glide(f0, f1, x, curve=1.0):
    k = (x / max(x[-1], 1e-9)) ** curve
    return np.sin(2 * np.pi * np.cumsum(f0 + (f1 - f0) * k) / SR)
def env(x, a, d, p=1.1):
    return (.5 - .5 * np.cos(np.pi * np.clip(x / a, 0, 1))) * np.exp(-(x / d) ** p)
def swell(x, a, d, hold=0.0):
    return (.5 - .5 * np.cos(np.pi * np.clip(x / a, 0, 1))) \
         * np.exp(-(np.clip(x - a - hold, 0, None) / d) ** 1.25)
def lp(sig, f, order=2):
    b, a = signal.butter(order, f / (SR/2), btype="low"); return signal.lfilter(b, a, sig)
def bp(sig, lo, hi, order=2):
    b, a = signal.butter(order, [lo/(SR/2), hi/(SR/2)], btype="band"); return signal.lfilter(b, a, sig)
def noise(x, s=7): return np.random.default_rng(s).standard_normal(len(x))
def place(buf, sig, ms):
    i = int(SR * ms / 1000); n = min(len(sig), len(buf) - i)
    if n > 0: buf[i:i+n] += sig[:n]
    return buf

def air(ms, amp, seed, hi=520, a=.095, d=.055):
    x = t(ms); n = bp(noise(x, seed), 170, hi, 2); n /= np.max(np.abs(n))
    return n * swell(x, a, d, hold=.02) * amp


def _voice(kind, f, dur, amp, a, d, h2=.055, glide_from=None, gl_ms=110):
    """glide_from: fall into f over gl_ms, then hold. a long glide never
    states the note, and the mirror is checked by which note is stated."""
    x = t(dur)
    if glide_from:
        n = len(x); g = min(int(SR * gl_ms / 1000), n)
        fr = np.full(n, float(f))
        fr[:g] = glide_from + (f - glide_from) * (.5 - .5 * np.cos(np.pi * np.linspace(0, 1, g)))
        v = np.sin(2 * np.pi * np.cumsum(fr) / SR)
    else:
        v = sine(f, x)
    v = v + sine(f * 2, x) * h2
    e = env(x, a, d, 1.2) if kind == "struck" else swell(x, a, d, hold=.03)
    return v * e * amp

def build(kind, k, layers=False):
    """k holds the per-variant character; the score is identical across all three.

    layers=True returns the breath and the tones as separate buffers, which is
    how the mirror is actually tested -- "the air is the last voice you hear"
    is a statement about two layers, not about a level in a time window."""
    n = int(SR * LEN_MS / 1000)
    L = {"air": np.zeros(n), "tone": np.zeros(n)}
    y = L["tone"]

    # ── entry: air, E4, B4 ───────────────────────────────────────────────
    place(L["air"], air(230, k["air"], 21), AIR_IN)
    y = place(y, _voice(kind, ROOT, k["g_dur"], k["g_amp"], k["g_a"], k["g_d"], k["h2"]), CARD)
    s = t(k["sub_dur"])
    y = place(y, sine(SUB, s) * env(s, .024, k["sub_d"], 1.2) * k["sub"], CARD + 4)
    y = place(y, _voice(kind, FIFTH, k["r_dur"], k["r_amp"], k["r_a"], k["r_d"], .04), RING)

    # ── exit: B4, E4, air -- the same three, walked back ─────────────────
    y = place(y, _voice(kind, FIFTH, k["xr_dur"], k["r_amp"] * k["x"], k["xr_a"], k["xr_d"], .03),
              UNRING)
    y = place(y, _voice(kind, ROOT, k["xg_dur"], k["g_amp"] * k["x"], k["xg_a"], k["xg_d"], .035,
                        glide_from=FIFTH * .93), COLLAPSE)          # a short fall into E3
    xs = t(220)
    y = place(y, sine(SUB, xs) * env(xs, .030, .062, 1.2) * k["sub"] * .7, COLLAPSE + 10)
    place(L["air"], air(230, k["air"], 45, hi=430), AIR_OUT)
    return L if layers else L["air"] + L["tone"]


# character per variant. the score above does not change.
K = {
 "pip":    dict(kind="struck", air=.034, h2=.150, g_dur=760, g_amp=.76, g_a=.030, g_d=.225,
                sub=.42, sub_dur=620, sub_d=.185, r_dur=560, r_amp=.44, r_a=.034, r_d=.190,
                x=.46, xr_dur=380, xr_a=.038, xr_d=.125, xg_dur=300, xg_a=.032, xg_d=.070),
 "settle": dict(kind="struck", air=.050, h2=.085, g_dur=960, g_amp=.80, g_a=.034, g_d=.262,
                sub=.52, sub_dur=860, sub_d=.212, r_dur=660, r_amp=.48, r_a=.040, r_d=.212,
                x=.42, xr_dur=420, xr_a=.044, xr_d=.140, xg_dur=330, xg_a=.038, xg_d=.078),
 "bloom":  dict(kind="open",   air=.042, h2=.110, g_dur=1100, g_amp=.82, g_a=.070, g_d=.260,
                sub=.34, sub_dur=820, sub_d=.210, r_dur=560, r_amp=.52, r_a=.052, r_d=.210,
                x=.40, xr_dur=430, xr_a=.050, xr_d=.135, xg_dur=300, xg_a=.050, xg_d=.060),
}
ORDER = ("pip", "settle", "bloom")


def finish(y):
    y = lp(y - np.mean(y), 1200, 2)
    ni, no = int(SR * .003), int(SR * .040)
    y[:ni] *= .5 - .5 * np.cos(np.pi * np.linspace(0, 1, ni))
    y[-no:] *= .5 + .5 * np.cos(np.pi * np.linspace(0, 1, no))
    return y * (PEAK / np.max(np.abs(y)))

def write(p, y):
    d = (np.clip(y, -1, 1) * 32767).astype("<i2")
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes(d.tobytes())
    return d

def rms(y, a, b):
    s = y[int(SR*a/1000):int(SR*b/1000)]
    return 20*np.log10(max(np.sqrt(np.mean(s**2)), 1e-12))

def tone(y, a, b):
    """dominant frequency in a window -- how the mirror is actually checked."""
    s = y[int(SR*a/1000):int(SR*b/1000)] * np.hanning(int(SR*(b-a)/1000))
    m = np.abs(np.fft.rfft(s, 1 << 17))
    f = np.fft.rfftfreq(1 << 17, 1/SR)
    band = (f > 120) & (f < 1800)
    return float(f[band][np.argmax(m[band])])

def hf(y):
    f, P = signal.welch(y, SR, nperseg=4096)
    return 10*np.log10(max(np.sum(P[f > 2000])/np.sum(P), 1e-14))

def centroid(y):
    f, P = signal.welch(y, SR, nperseg=4096)
    return float(np.sum(f*P)/np.sum(P))


if __name__ == "__main__":
    out = pathlib.Path("wav4"); out.mkdir(exist_ok=True)
    print("%-8s %8s %8s | %-26s | %-26s" % ("name","cen",">2kHz","entry  air   E3    B3","exit   B3    E3   air"))
    for name in ORDER:
        y = finish(build(K[name]["kind"], K[name])); d = write(out / ("nabd-sound-%s.wav" % name), y)
        e_g, e_r = tone(y, 320, 580), tone(y, 900, 1150)
        x_r, x_g = tone(y, 3200, 3450), tone(y, 3630, 3860)

        # the mirror, checked by pitch rather than by hope
        assert abs(e_g - ROOT)  / ROOT  < .06, (name, "entry gesture is %.0f Hz, not E3" % e_g)
        assert abs(e_r - FIFTH) / FIFTH < .06, (name, "entry resolve is %.0f Hz, not B3" % e_r)
        assert abs(x_r - FIFTH) / FIFTH < .06, (name, "exit should open on B3, got %.0f Hz" % x_r)
        assert abs(x_g - ROOT)  / ROOT  < .06, (name, "exit should land on E3, got %.0f Hz" % x_g)
        # air is the last voice you hear, as it was the first -- checked on the
        # layers, because in the mixed file it is competing with a decaying tone
        L = build(K[name]["kind"], K[name], layers=True)
        assert rms(L["air"], 3890, 4110) > rms(L["tone"], 3890, 4110) + 4, \
            (name, "the fall is still the loudest thing during the withdrawal")
        assert abs(rms(L["air"], 3890, 4110) - rms(L["air"], 0, 230)) < 3, \
            (name, "closing breath does not match the opening one")
        assert rms(y, 3890, 4110) < rms(y, 3630, 3860), (name, "air louder than the fall")
        # unchanged from v3
        assert 320-10 <= 1000*np.argmax(np.abs(y))/SR <= 580, (name, "peak outside the card rise")
        assert centroid(y) < 300 and hf(y) < -50,             (name, "back into the band that hurt")
        assert rms(y,1400,3100) < rms(y,320,580) - 36,        (name, "rings through the still section")
        assert rms(y,3200,3880) < rms(y,320,580) - 2,         (name, "exit louder than the entry")
        assert abs(d[0]) <= 2 and abs(d[-1]) <= 2,            (name, "edge click")
        assert np.max(np.abs(np.diff(d.astype(float)))) < 4000,(name, "transient too hard")

        print("%-8s %6.0fHz %7.1fdB | %5.1f %5.0fHz %5.0fHz | %5.0fHz %5.0fHz %5.1f"
              % (name, centroid(y), hf(y), rms(y,0,230), e_g, e_r, x_r, x_g, rms(y,3890,4110)))
    print("\nE3 = %.2f   B3 = %.2f   E2 = %.2f" % (ROOT, FIFTH, SUB))
