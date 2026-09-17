"""nab'd error sound -- the same phrase, refusing to resolve.

Built on synth5's voices and envelopes so the two sounds are unmistakably the
same instrument. Only the notes change, and only after the point where things
go wrong:

    SAVE                                   ERROR
      0   line slides out    air             0   air            <- identical
    320   card rises          E3           320   E3             <- identical
    900   ring completes      B3           900   Bb3            <- the tritone
   3200   ring winds back     B3          3200   Bb3
   3630   card collapses      E3          3630   D3             <- lands BELOW home
   3890   line withdraws     air          3890   air            <- identical

The first two events are the same sound because at 320 ms nothing has failed
yet -- the card is still just arriving. The banner commits to being an error at
900, the same instant the save banner commits to being a success, and it does
it by putting a tritone where the perfect fifth was.

The exit mirrors the entry as the save sound's does, but walks down past home
instead of returning to it: air, E3, Bb3 | Bb3, D3, air. A phrase that ends a
whole tone under the note it started on does not sound finished, which is the
point -- nothing was finished.

The shake is silent, for the same reason the wink is: the sound marks
structural events, the gesture is character. Scoring it would turn a
one-second refusal into a second announcement.

Deliberately NOT an alarm. It is low-passed at 1.2 kHz and held to the same
spectral limits as the save sound, so it sits under game audio exactly as that
one does. An error is not an emergency, and this plays while someone is still
playing.
"""
import sys, pathlib
import numpy as np

sys.path.insert(0, "/home/claude/nabd/sfx")
from synth5 import (SR, PEAK, LEN_MS, AIR_IN, CARD, RING, UNRING, COLLAPSE,
                    AIR_OUT, SUB, ROOT, t, sine, env, air, _voice, place,
                    finish, write, rms, tone, hf, centroid)

# E3 stays home. Bb3 is the tritone above it; D3 is a whole tone below it.
TRITONE = 233.08          # Bb3
UNDER = 146.83            # D3

K = dict(kind="struck", air=.034, h2=.150,
         g_dur=760, g_amp=.76, g_a=.030, g_d=.225,
         sub=.42, sub_dur=620, sub_d=.185,
         # the tritone opens rather than strikes, and holds a little longer:
         # it should land like a realisation, not like a buzzer
         r_dur=620, r_amp=.46, r_a=.078, r_d=.185,
         x=.46, xr_dur=400, xr_a=.044, xr_d=.135,
         xg_dur=350, xg_a=.034, xg_d=.072)


def build(layers=False):
    n = int(SR * LEN_MS / 1000)
    L = {"air": np.zeros(n), "tone": np.zeros(n)}
    y = L["tone"]

    # ── entry: air, E3, Bb3 ──────────────────────────────────────────────
    place(L["air"], air(230, K["air"], 21), AIR_IN)
    y = place(y, _voice("struck", ROOT, K["g_dur"], K["g_amp"],
                        K["g_a"], K["g_d"], K["h2"]), CARD)
    s = t(K["sub_dur"])
    y = place(y, sine(SUB, s) * env(s, .024, K["sub_d"], 1.2) * K["sub"], CARD + 4)
    # the tritone. `open` rather than `struck` so it swells in under the E3's
    # tail -- the dissonance arrives, it is not hit.
    y = place(y, _voice("open", TRITONE, K["r_dur"], K["r_amp"],
                        K["r_a"], K["r_d"], .04), RING)
    # the E2 pedal is what makes Bb read as a tritone rather than as a stray
    # note; without it the interval has nothing to be wrong against.
    ps = t(560)
    y = place(y, sine(SUB, ps) * env(ps, .060, .170, 1.20) * K["sub"] * .55, RING)

    # ── exit: Bb3, D3, air -- the same three, walked back past home ───────
    y = place(y, _voice("struck", TRITONE, K["xr_dur"], K["r_amp"] * K["x"],
                        K["xr_a"], K["xr_d"], .03), UNRING)
    # a sag down past the root to D3. The save sound falls a short way INTO
    # E3; this one falls through it. The glide is kept to 110 ms for the reason
    # synth5 gives -- a long glide never states the note, and the phrase is
    # checked by which note is stated, not by where it started. 80 ms leaves
    # D3 stated and decaying for 190 ms before the closing breath arrives --
    # the air has to be the last voice, as it is in the save sound.
    y = place(y, _voice("struck", UNDER, K["xg_dur"], K["g_amp"] * K["x"],
                        K["xg_a"], K["xg_d"], .035,
                        glide_from=TRITONE * .88, gl_ms=80), COLLAPSE)
    xs = t(240)
    y = place(y, sine(SUB, xs) * env(xs, .034, .070, 1.2) * K["sub"] * .7,
              COLLAPSE + 10)
    place(L["air"], air(230, K["air"], 45, hi=430), AIR_OUT)
    return L if layers else L["air"] + L["tone"]


def check(y, d):
    """Every assertion the save sound has to pass, plus the ones that make this
    one an error rather than a second success."""
    import synth5 as S
    out = {}

    # ── the notes are what the docstring claims ──────────────────────────
    # Pitch is read off the TONE layer, not the mix: the closing breath sits
    # at 170-430 Hz and would otherwise be measured as the landing note.
    T = build(layers=True)["tone"]
    e_g = tone(T, 320, 580); e_r = tone(T, 900, 1200)
    x_r = tone(T, 3200, 3450); x_g = tone(T, 3725, 3875)
    assert abs(e_g - ROOT) / ROOT < .06, "entry gesture is %.0f Hz, not E3" % e_g
    assert abs(e_r - TRITONE) / TRITONE < .06, "900 should be Bb3, got %.0f Hz" % e_r
    assert abs(x_r - TRITONE) / TRITONE < .06, "3200 should be Bb3, got %.0f Hz" % x_r
    assert abs(x_g - UNDER) / UNDER < .07, "3630 should land on D3, got %.0f Hz" % x_g

    # ── it must not resolve ──────────────────────────────────────────────
    assert x_g < ROOT * 0.98, \
        "the phrase came home to %.0f Hz; an error must not resolve" % x_g
    ratio = e_r / ROOT
    assert 1.38 < ratio < 1.44, \
        "900 is a %.3f ratio above the root -- that is not a tritone" % ratio
    assert abs(ratio - 1.5) > 0.05, "900 is too close to a perfect fifth"

    # ── and it must not become an alarm ──────────────────────────────────
    assert centroid(y) < 300, "centroid %.0f Hz -- back into the band that hurt" % centroid(y)
    assert hf(y) < -50, "too much above 2 kHz: %.1f dB" % hf(y)
    assert np.max(np.abs(np.diff(d.astype(float)))) < 4000, "transient too hard"
    assert rms(y, 3200, 3880) < rms(y, 320, 580) - 2, "exit louder than the entry"
    assert rms(y, 1400, 3100) < rms(y, 320, 580) - 34, \
        "rings through the shake: still section is only %.1f dB down" \
        % (rms(y, 320, 580) - rms(y, 1400, 3100))

    # ── shared with the save sound ───────────────────────────────────────
    assert len(d) == int(SR * LEN_MS / 1000), "length must equal the banner's TOTAL_MS"
    assert abs(d[0]) <= 2 and abs(d[-1]) <= 2, "edge click"
    assert 320 - 10 <= 1000 * np.argmax(np.abs(y)) / SR <= 580, "peak outside the card rise"
    L = build(layers=True)
    assert rms(L["air"], 3890, 4110) > rms(L["tone"], 3890, 4110) + 4, \
        "the fall is still the loudest thing during the withdrawal"
    assert abs(rms(L["air"], 3890, 4110) - rms(L["air"], 0, 230)) < 3, \
        "closing breath does not match the opening one"

    out.update(centroid=centroid(y), hf=hf(y), e_g=e_g, e_r=e_r, x_r=x_r, x_g=x_g,
               ratio=ratio)
    return out


if __name__ == "__main__":
    out = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "assets/sound")
    out.mkdir(parents=True, exist_ok=True)
    y = finish(build())
    d = write(out / "nabd-sound-error.wav", y)
    r = check(y, d)
    print("nabd-sound-error.wav   %d ms   %d Hz   peak %.1f dBFS"
          % (LEN_MS, SR, 20 * np.log10(np.max(np.abs(y)))))
    print("  entry   air  E3 %.0f Hz  Bb3 %.0f Hz   (%.3f above the root -- a tritone)"
          % (r["e_g"], r["e_r"], r["ratio"]))
    print("  exit    Bb3 %.0f Hz  D3 %.0f Hz  air    (lands %.0f Hz UNDER home)"
          % (r["x_r"], r["x_g"], ROOT - r["x_g"]))
    print("  centroid %.0f Hz, %.1f dB above 2 kHz -- same band as the save sound"
          % (r["centroid"], r["hf"]))
