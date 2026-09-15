"""The A/V sync test card: what the Test button puts on screen to be captured.

The problem with a plain five-second nab is that it shows you whatever was
happening anyway, and nothing in it happened at a knowable instant - so there is
nothing to check the audio against. This draws events whose real-world timing is
known exactly, so the recording can be measured against them.

Two passes, because they answer different questions:

  ladder   Five flash/click pairs whose clicks are deliberately played early or
           late by a labelled amount. The pipeline's own error cancels one of
           them out, and picking the best of five is a far finer judgement than
           staring at a single pair and asking "is that aligned?". The label
           under the pair that lines up is the correction.

  clapper  Five pairs played dead on the beat, to confirm the setting you just
           worked out - and to give the ear a steady rhythm to lock onto, which
           is where the last few milliseconds of sensitivity come from.

The sign convention is worth spelling out because it is easy to get backwards.
Let E be the pipeline error, (audio time in the file) - (video time in the
file), for something that really happened at one instant; E > 0 means the sound
lands late. A rung labelled X plays its click X ms after its flash, so in the
recording that pair is separated by X + E. It looks aligned when X = -E. The
capture-side offset shifts recorded audio by exactly its own value, so moving it
by X makes the error E + X = 0. The label IS the amount to add to the offset -
no negation, no halving.
"""
import io
import math
import struct
import time
import tkinter as tk
import wave
from pathlib import Path

import nabd_tokens as T

# Click positions for the ladder, in ms relative to the flash. Spread wide
# enough to bracket a badly wrong setting, since a ladder whose rungs all miss
# tells you only "more than the widest rung".
LADDER = (-200, -100, 0, 100, 200)

LEAD_MS = 1500          # title card, before anything strikes
RUNG_MS = 1500          # per ladder pair - has to clear a +-200ms click
GAP_MS = 700            # ladder -> clapper
CLAP_MS = 1000          # per clapper pair
CLAPS = 5
TAIL_MS = 1000          # let the last click land well inside the clip

FLASH_MS = 50           # hold. The onset is what gets measured; the hold is
                        # only so the flash cannot be missed at normal speed.

# When each event happens, measured from the first frame of the card.
LADDER_AT = tuple(LEAD_MS + i * RUNG_MS for i in range(len(LADDER)))
CLAP_AT = tuple(LADDER_AT[-1] + RUNG_MS + GAP_MS + i * CLAP_MS
                for i in range(CLAPS))
SWITCH_AT = LADDER_AT[-1] + 300         # ladder gives way to the clapper
TOTAL_MS = CLAP_AT[-1] + TAIL_MS
STRIKE_AT = LADDER_AT + CLAP_AT

# Each pass gets the full width of the track to itself, rather than being
# squeezed into half of it. A window is (when the marker leaves x0, when it
# reaches the last bar); the run-in is what makes the first strike predictable.
LADDER_WIN = (0, LADDER_AT[-1])
CLAP_WIN = (SWITCH_AT, CLAP_AT[-1])

# The card sits in the middle of the monitor at this fraction of its height,
# 16:9. It is not fullscreen: a full-screen white flash ten times over is a
# huge amount of change for the encoder to swallow on top of whatever it is
# already recording, and it buys nothing - the flash only has to be
# unmistakable, not enormous.
CARD_FRAC = 0.42
GUARD_MS = 4000         # hard stop after the pattern, whatever else happened

WHITE = "#FFFFFF"
INK = "#0B0910"
BAR = "#3B3450"
TRACK = "#2A2536"
TRACK_LIT = "#CFC9DC"


def click_wav(ms=10, freq=2000, rate=44100):
    """A click, not a beep.

    A tone that fades in has no locatable onset, and an onset is the only thing
    this test needs from it. Full amplitude on the first sample, a few cycles,
    then a short ramp down - long enough to hear, short enough that "when did it
    start" and "when did it happen" are the same question.
    """
    n = int(rate * ms / 1000.0)
    fade = max(1, n // 3)
    out = bytearray()
    for i in range(n):
        a = 1.0 if i < n - fade else (n - i) / float(fade)
        v = int(a * 32000 * math.sin(2 * math.pi * freq * i / rate))
        out += struct.pack("<h", v)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(out))
    return buf.getvalue()


def silence_wav(ms=250, rate=44100):
    """Silence, to open the output device before the pattern needs it.

    An idle output - a wireless headset especially - takes a moment to wake,
    and the first sound played through it arrives late. Measured on a HyperX
    Cloud III: the first click landed 520ms after its flash while every other
    click in the same run was within 20ms. That is not a sync error, but it
    looks exactly like one.
    """
    n = int(rate * ms / 1000.0)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * n)
    return buf.getvalue()


def _wav_file(data_dir, name, make):
    out = Path(data_dir) / name
    try:
        if not out.exists() or out.stat().st_size == 0:
            out.write_bytes(make())
    except OSError:
        return None
    return str(out)


def silence_path(data_dir, name="av_prime.wav"):
    return _wav_file(data_dir, name, silence_wav)


def click_path(data_dir, name="av_click.wav"):
    """The click as a file, because it cannot be played any other way.

    winsound will play from memory, or asynchronously, but not both:
    SND_MEMORY | SND_ASYNC raises "Cannot play asynchronously from memory".
    Synchronously is not an option either - it would block the loop that is
    drawing the flash, which is the other half of the pair being measured.
    So the click goes to disk once and is played from there.
    """
    return _wav_file(data_dir, name, click_wav)


class TestCard:
    """A card in the middle of one monitor that runs the pattern once.

    Owns nothing but its own Toplevel and an after() loop: the caller starts it,
    is told when it has finished, and destroys it.

    It is borderless and always on top, so it must never be able to outlive its
    own run: Escape closes it, and a guard timer closes it even if the tick
    loop stops firing. Without those, a card that stalls is a lid over the
    screen with no handle on it.
    """

    def __init__(self, parent, monitor, note, on_click, on_done):
        """`note` is the caller's line about the offset in force.

        The panel builds it, because only the panel knows whether the slider on
        screen has been saved - and the recording is being made with the saved
        offset, not the one under the user's cursor.
        """
        self.on_click = on_click
        self.on_done = on_done
        self.note_text = str(note)
        self._t0 = None
        self._after = None
        self._flash_until = 0.0
        self._struck = None
        self._was = None          # (lit, struck) as last painted
        self._clapping = False
        self._done = False
        self._mx = None           # last marker x actually drawn

        self._guard = None

        m = monitor
        mw, mh = int(m["width"]), int(m["height"])
        self.h = max(240, int(round(mh * CARD_FRAC)))
        self.w = min(int(round(self.h * 16 / 9.0)), int(mw * 0.8))
        # Kept, because winfo_x on an unmapped Toplevel is 0 - and anything
        # wanting to look at what was captured needs the rectangle, not a
        # placeholder.
        self.x = int(m["x"]) + (mw - self.w) // 2
        self.y = int(m["y"]) + (mh - self.h) // 2
        x, y = self.x, self.y
        top = tk.Toplevel(parent)
        self.top = top
        top.overrideredirect(True)
        top.attributes("-topmost", True)
        top.geometry(f"{self.w}x{self.h}+{x}+{y}")
        self.cv = tk.Canvas(top, width=self.w, height=self.h, bg=INK,
                            highlightthickness=0, bd=0)
        self.cv.pack(fill="both", expand=True)
        # The only way out other than waiting. Bound on the Toplevel and on the
        # canvas, since which of them holds focus is not worth depending on.
        for w in (top, self.cv):
            w.bind("<Escape>", lambda _e: self.finish())
        self._build()

        # Every event in one list, fired against the wall clock rather than by
        # a chain of after() calls: a chain accumulates its own scheduling
        # error, and the gap between a flash and its click is the one number
        # here that has to be right.
        self.events = [(LADDER_AT[0] - 400, "phase", "ladder"),
                       (SWITCH_AT, "phase", "clapper")]
        for i, x in enumerate(LADDER):
            self.events.append((LADDER_AT[i], "flash", i))
            self.events.append((LADDER_AT[i] + x, "click", None))
        for i in range(CLAPS):
            self.events.append((CLAP_AT[i], "flash", len(LADDER) + i))
            self.events.append((CLAP_AT[i], "click", None))
        self.events.sort(key=lambda e: e[0])
        self._next = 0

    # -- drawing ----------------------------------------------------------

    def _px(self, v):
        """The card is drawn against the monitor it lands on, not the panel's
        display, so it cannot use the panel's scale factor."""
        return int(round(v * self.h / 1440.0))

    def _at_x(self, when, win):
        frac = (when - win[0]) / float(win[1] - win[0])
        return self.x0 + max(0.0, min(1.0, frac)) * self.span

    def _bar_x(self, i):
        return self._at_x(STRIKE_AT[i],
                          LADDER_WIN if i < len(LADDER) else CLAP_WIN)

    def _build(self):
        cv, w, h = self.cv, self.w, self.h
        self.mid = mid = h // 2

        self.bg = cv.create_rectangle(0, 0, w, h, fill=INK, outline="")
        # It sits on the desktop now, not over it, so it needs an edge.
        self.edge = cv.create_rectangle(
            1, 1, w - 2, h - 2, outline=T.PURPLE, width=self._px(6), fill="")
        self.title = cv.create_text(
            w // 2, self._px(150), text="A / V  S Y N C",
            fill=T.PURPLE_LIGHT, font=(T.FONT_UI, -self._px(64)))
        self.phase = cv.create_text(
            w // 2, self._px(250), text="get ready",
            fill=T.TEXT_MUTED, font=(T.FONT_UI, -self._px(34)))

        self.x0 = self._px(220)
        self.span = w - 2 * self.x0
        self.top_y, self.bot_y = mid - self._px(120), mid + self._px(120)
        self.track = cv.create_line(self.x0, mid, self.x0 + self.span, mid,
                                    fill=TRACK, width=self._px(3))

        # A strike bar per flash, placed where the marker will be when that
        # flash fires. The marker moves at a constant speed, so every strike is
        # one you can see coming - and a strike you can anticipate is one you
        # can judge.
        self.bars, self.labels, self.nums = [], [], []
        for i in range(len(STRIKE_AT)):
            lad = i < len(LADDER)
            bx = self._bar_x(i)
            self.bars.append(cv.create_rectangle(
                bx - self._px(5), self.top_y, bx + self._px(5), self.bot_y,
                fill=BAR, outline="", state="normal" if lad else "hidden"))
            if lad:
                self.nums.append(cv.create_text(
                    bx, self.bot_y + self._px(56), text=str(i + 1),
                    fill=T.TEXT_FAINT, font=(T.FONT_UI, -self._px(30))))
                self.labels.append(cv.create_text(
                    bx, self.bot_y + self._px(104),
                    text=("%+d" % LADDER[i]) if LADDER[i] else "0",
                    fill=T.PURPLE_LIGHT, font=(T.FONT_MONO, -self._px(38))))
        self.unit = cv.create_text(
            self._bar_x(len(LADDER) - 1) + self._px(80),
            self.bot_y + self._px(104), text="ms", fill=T.TEXT_FAINT,
            font=(T.FONT_UI, -self._px(28)), anchor="w")

        self.marker = cv.create_oval(
            -99, mid - self._px(26), -99 + self._px(52), mid + self._px(26),
            fill=T.PURPLE_LIGHT, outline="")

        self.note = cv.create_text(
            w // 2, h - self._px(190), text=self.note_text,
            fill=T.TEXT, font=(T.FONT_MONO, -self._px(40)))
        self.help = cv.create_text(
            w // 2, h - self._px(120),
            text="Add the number under the pair that lined up.",
            fill=T.TEXT_MUTED, font=(T.FONT_UI, -self._px(32)))
        self.bail = cv.create_text(
            w - self._px(40), self._px(40), text="Esc to stop", anchor="ne",
            fill=T.TEXT_FAINT, font=(T.FONT_UI, -self._px(26)))

    # -- run --------------------------------------------------------------

    def start(self):
        self.top.lift()
        try:
            self.top.focus_force()      # or Escape never reaches it
        except tk.TclError:
            pass
        self.top.update_idletasks()
        # Independent of the tick loop on purpose: if that stops firing - a
        # TclError swallowed somewhere, a display change, anything - this is
        # what still takes the card off the screen.
        try:
            self._guard = self.top.after(int(TOTAL_MS) + GUARD_MS, self.finish)
        except tk.TclError:
            pass
        self._t0 = time.perf_counter()
        self._tick()

    def _tick(self):
        if self._done:
            return
        t = (time.perf_counter() - self._t0) * 1000.0
        try:
            while (self._next < len(self.events)
                   and self.events[self._next][0] <= t):
                _, kind, arg = self.events[self._next]
                self._next += 1
                self._fire(kind, arg)
            self._paint(t)
        except tk.TclError:
            self.finish()
            return
        if t >= TOTAL_MS:
            self.finish()
            return
        try:
            self._after = self.top.after(4, self._tick)
        except tk.TclError:
            self.finish()

    def _fire(self, kind, arg):
        if kind == "click":
            self.on_click()
        elif kind == "flash":
            self._flash_until = time.perf_counter() + FLASH_MS / 1000.0
            self._struck = arg
        elif kind == "phase":
            self._phase(arg)

    def _phase(self, which):
        cv = self.cv
        if which == "ladder":
            cv.itemconfigure(self.phase, text="which pair lines up?")
            return
        self._clapping = True
        cv.itemconfigure(self.phase, text="on the beat  ×5")
        cv.itemconfigure(self.help,
                         text="Clicks and flashes are together here.")
        # Ten bars on screen at once, half of them labelled, would read as a
        # single ten-rung ladder. Only the pass in play shows its bars.
        for i, bar in enumerate(self.bars):
            cv.itemconfigure(
                bar, state="hidden" if i < len(LADDER) else "normal")
        for item in self.labels + self.nums + [self.unit]:
            cv.itemconfigure(item, text="")

    def _paint(self, t):
        cv = self.cv
        lit = time.perf_counter() < self._flash_until
        struck = self._struck if lit else None

        # Only on a change. Recolouring seventeen items every 4ms is work the
        # capture has to encode as well as Tk has to draw - and on a white
        # field the struck bar has to go dark, not white, or the one event the
        # whole test turns on is the one thing that disappears.
        if (lit, struck) != self._was:
            self._was = (lit, struck)
            ink = INK if lit else None
            cv.itemconfigure(self.bg, fill=WHITE if lit else INK)
            cv.itemconfigure(self.track, fill=TRACK_LIT if lit else TRACK)
            for i, bar in enumerate(self.bars):
                hit = i == struck
                cv.itemconfigure(bar, fill=T.PURPLE if hit else (ink or BAR))
                # The struck bar widens as well as changing colour, so it reads
                # as an impact rather than merely as a different shade.
                bx, half = self._bar_x(i), self._px(16 if hit else 5)
                cv.coords(bar, bx - half, self.top_y, bx + half, self.bot_y)
            for i, lab in enumerate(self.labels):
                cv.itemconfigure(lab, fill=(T.PURPLE if i == struck
                                            else (ink or T.PURPLE_LIGHT)))
            for item in self.nums:
                cv.itemconfigure(item, fill=ink or T.TEXT_FAINT)
            for item, rest in ((self.title, T.PURPLE_LIGHT),
                               (self.phase, T.TEXT_MUTED),
                               (self.note, T.TEXT),
                               (self.help, T.TEXT_MUTED),
                               (self.unit, T.TEXT_FAINT)):
                cv.itemconfigure(item, fill=ink or rest)
            cv.itemconfigure(self.marker, fill=INK if lit else T.PURPLE_LIGHT)

        x = self._at_x(t, CLAP_WIN if self._clapping else LADDER_WIN)
        if self._mx is None or abs(x - self._mx) >= 1.0:
            self._mx = x
            r = self._px(26)
            cv.coords(self.marker, x - r, self.mid - r, x + r, self.mid + r)

    def finish(self):
        if self._done:
            return
        self._done = True
        for attr in ("_after", "_guard"):
            ident = getattr(self, attr)
            if ident is not None:
                try:
                    self.top.after_cancel(ident)
                except tk.TclError:
                    pass
                setattr(self, attr, None)
        try:
            self.top.destroy()
        except tk.TclError:
            pass
        if self.on_done:
            self.on_done()
