"""Widgets for the nab'd settings panel, built on nabd_tokens + nabd_paint.

Everything here is classic tk. See TKINTER-BUILD.md for why: ttk cannot be
themed to this palette on Windows, and every rounded/gradient/alpha shape is a
pre-rendered Pillow image.

The one structural trick worth knowing: a card's rounded corners are four small
masks placed over the corners of an ordinary square Frame, rather than the whole
card being an image with the content inset into it. The frame still sizes itself
from its children, so layout is completely unaffected and the radius costs four
cached 10x10 images for the entire panel.
"""
from __future__ import annotations

import tkinter as tk

from PIL import Image

import nabd_paint as P
import nabd_tokens as T

_photo = P.photo


# ---------------------------------------------------------------------------
# corner masking
# ---------------------------------------------------------------------------

_CORNER_CACHE: dict[tuple, list] = {}


def corner_masks(r, fill, outline, bg, width=1):
    """Four r x r images that round off the corners of a square frame.

    Each is a crop of one rounded rectangle, so the arc and its 1px outline are
    identical to what rounded_rect would have drawn at full size.
    """
    key = (r, fill, outline, bg, width, T.scale())
    if key in _CORNER_CACHE:
        return _CORNER_CACHE[key]
    box = P.rounded_rect(r * 2, r * 2, r, fill, outline, width, bg)
    out = [box.crop(c) for c in ((0, 0, r, r), (r, 0, r * 2, r),
                                 (0, r, r, r * 2), (r, r, r * 2, r * 2))]
    _CORNER_CACHE[key] = out
    return out


class RoundedFrame(tk.Frame):
    """A square Frame with its corners masked into a radius.

    `body` is where children go. The frame keeps a 1px border via
    highlightthickness, and the four masks cover where that border would
    otherwise turn a square corner.
    """

    def __init__(self, parent, radius=None, fill=T.SURFACE, outline=T.LINE,
                 bg=T.PANEL, **kw):
        self.radius = r = T.px(T.R_CARD if radius is None else radius)
        # No highlightthickness. Tk can only draw that ring square, and it is
        # painted outside the area children occupy, so it survives underneath
        # the corner masks as a hard right angle around the arc. The border is
        # therefore four straight strips between the four arcs instead.
        super().__init__(parent, bg=fill, highlightthickness=0, bd=0, **kw)
        self.body = self
        self.fill_c, self.outline_c, self.parent_bg = fill, outline, bg
        self._masks = []
        imgs = corner_masks(r, fill, outline, bg)
        for i, (ax, ay) in enumerate(((0, 0), (1, 0), (0, 1), (1, 1))):
            lbl = tk.Label(self, bd=0, highlightthickness=0, bg=fill)
            _photo(lbl, imgs[i])
            lbl.configure(image=getattr(lbl, "_img"))
            lbl.place(relx=ax, rely=ay, x=-r * ax, y=-r * ay, anchor="nw")
            lbl._chrome = True      # drawn as part of the box in the still
            self._masks.append(lbl)

        t = T.px(1)
        self._edges = [tk.Frame(self, bg=outline, bd=0, highlightthickness=0)
                       for _ in range(4)]
        top, bot, left, right = self._edges
        top.place(x=r, y=0, relwidth=1.0, width=-2 * r, height=t)
        bot.place(x=r, rely=1.0, y=-t, relwidth=1.0, width=-2 * r, height=t)
        left.place(x=0, y=r, relheight=1.0, height=-2 * r, width=t)
        right.place(relx=1.0, x=-t, y=r, relheight=1.0, height=-2 * r, width=t)
        # Children are packed after this runs, so they would stack above the
        # border. Re-raise it whenever the frame lays out.
        self.bind("<Configure>", self._lift_chrome, add="+")

    def set_corner_patch(self, index, patch):
        """Re-cut one corner so its arc reveals `patch` instead of the flat
        fill - for a corner that sits over an image or a coloured child."""
        try:
            lbl = self._masks[index]
            _photo(lbl, P.corner_over(patch, self.radius, index,
                                      self.outline_c, self.parent_bg))
            lbl.configure(image=getattr(lbl, "_img"))
        except (tk.TclError, IndexError):
            pass

    def _lift_chrome(self, _e=None):
        for w in self._masks + self._edges:
            try:
                w.lift()
            except tk.TclError:
                pass


# ---------------------------------------------------------------------------
# structure
# ---------------------------------------------------------------------------

def eyebrow(parent, text, trailing=None, bg=T.PANEL):
    """Mono uppercase group label with a hairline rule running to the right.

    Tk has no letter-spacing and the face is monospace, so inserting a thin
    space still costs a full advance - roughly 6px where the spec asks for
    .16em, or 1.6px. Each glyph is therefore its own label, spaced by hand.
    """
    head = tk.Frame(parent, bg=bg)
    track = tk.Frame(head, bg=bg)
    track.pack(side="left", padx=(T.px(3), 0), pady=(T.px(2), T.px(3)))
    # A default Label carries 7px of padding and border around a 5px glyph,
    # which doubles the tracking before any gap is added. Zero it, then the
    # 1px gap plus the label's own 1px lands on the spec's 1.6px.
    gap = max(1, T.px(1.6) - T.px(1))
    for ch in text.upper():
        tk.Label(track, text=ch, bg=bg, fg=T.TEXT_FAINT, padx=0, pady=0,
                 bd=0, highlightthickness=0,
                 font=T.font("eyebrow")).pack(side="left", padx=(0, gap))
    rule = tk.Frame(head, bg=T.LINE, height=T.px(1))
    rule.pack(side="left", fill="x", expand=True,
              padx=(T.px(12), T.px(12) if trailing else 0), pady=(T.px(1), 0))
    if trailing:
        trailing(head)
    return head


class Row:
    """One settings row: a flexing label on the left, a fixed control column on
    the right. Secondary content stacks *inside* the control column so it stays
    attached to its control and every control's left edge lines up.
    """

    def __init__(self, card, label, row, first=False, last=False):
        # Corner masks sit *over* the frame rather than insetting it, so the
        # first and last rows need no padding adjustment - every row gets the
        # same 13px and the radius costs no vertical space.
        top = bot = T.px(T.ROW_PAD_Y)

        self.card = card
        self.index = row
        self.label_text = label or ""
        self.label_widget = None
        if label is not None:
            # A holder of spans rather than one Label: search highlights the
            # matched substring, and Tk cannot colour part of a Label.
            self.label_widget = tk.Frame(card.body, bg=T.SURFACE)
            self.label_widget.grid(
                row=row, column=0, sticky="nw",
                padx=(T.px(T.ROW_PAD_X), T.px(20)),
                pady=(top + T.px(T.LABEL_TOP_PAD), bot))
            self.set_label()
        self.control = tk.Frame(card.body, bg=T.SURFACE)
        # "ew", not "e": the column is a fixed 344px and the frame has to fill
        # it, or it shrinks to its content and the stacked meters, sliders and
        # helper text under a narrow control no longer span the column.
        self.control.grid(row=row, column=1, sticky="ew",
                          padx=(0, T.px(T.ROW_PAD_X)), pady=(top, bot))
        # the first line of the control column, right-aligned
        self.line = tk.Frame(self.control, bg=T.SURFACE)
        self.line.pack(fill="x")

    def sub(self, pady=None):
        """A stacked line under the control, inside the same column."""
        f = tk.Frame(self.control, bg=T.SURFACE)
        f.pack(fill="x", pady=(T.px(9) if pady is None else pady, 0))
        return f

    def set_label(self, query=""):
        """Render the label, tinting the matched run if there is one."""
        if not self.label_widget:
            return
        for w in self.label_widget.winfo_children():
            w.destroy()
        text = self.label_text
        lo = text.lower().find(query.lower()) if query else -1
        spans = ([(text, False)] if lo < 0 else
                 [(text[:lo], False), (text[lo:lo + len(query)], True),
                  (text[lo + len(query):], False)])
        for part, hit in spans:
            if not part:
                continue
            tk.Label(self.label_widget, text=part,
                     bg=T.PURPLE_DEEP if hit else T.SURFACE,
                     fg=T.TEXT if hit else T.TEXT_MUTED,
                     font=T.font("label"), padx=0, pady=0, bd=0,
                     highlightthickness=0).pack(side="left")

    def hide(self):
        if self.label_widget:
            self.label_widget.grid_remove()
        self.control.grid_remove()

    def show(self):
        if self.label_widget:
            self.label_widget.grid()
        self.control.grid()

    def helper(self, text="", colour=None):
        return Helper(self.control, text, colour)


class Helper(tk.Label):
    """The helper line under a control.

    Takes no vertical space at all when it has nothing to say - a packed empty
    Label still reserves a line, which left a visible gap under rows whose
    helper only appears in certain states.
    """

    def __init__(self, parent, text="", colour=None):
        super().__init__(parent, bg=T.SURFACE, fg=colour or T.TEXT_FAINT,
                         font=T.font("helper"), anchor="w", justify="left",
                         wraplength=T.px(T.CONTROL_COL))
        self._shown = False
        self.set(text, colour)

    def set(self, text, colour=None):
        self.configure(text=text or "", fg=colour or T.TEXT_FAINT)
        if text and not self._shown:
            self.pack(fill="x", pady=(T.px(8), 0))
            self._shown = True
        elif not text and self._shown:
            self.pack_forget()
            self._shown = False


def separator(card, row):
    bar = tk.Frame(card.body, bg=T.LINE, height=T.px(1))
    bar.grid(row=row, column=0, columnspan=2, sticky="ew")
    return bar


def card(parent, bg=T.PANEL):
    """A settings card with the two-column grid already configured."""
    c = RoundedFrame(parent, bg=bg)
    c.body.grid_columnconfigure(0, weight=1)
    c.body.grid_columnconfigure(1, weight=0, minsize=T.px(T.CONTROL_COL))
    return c


# ---------------------------------------------------------------------------
# controls
# ---------------------------------------------------------------------------

def text_width(font_spec, text):
    """Rendered width of `text`, for sizing an image behind it."""
    from tkinter import font as tkfont
    return tkfont.Font(font=font_spec).measure(text)


class Button(tk.Label):
    """primary | ghost | quiet, per the spec's three variants.

    One Label with compound="center": the rounded rectangle is the image and
    the caption is drawn over it, so there is no inner widget whose opaque
    background would square off the corners.
    """

    VARIANTS = {
        "primary": (T.PURPLE, T.PURPLE, T.TEXT_ON_PURPLE,
                    T.PURPLE_HOVER, T.PURPLE_HOVER),
        "ghost":   (T.RAISED, T.LINE_STRONG, T.TEXT,
                    T.RAISED_HOVER, T.LINE_HOVER),
        "quiet":   (None, T.LINE_STRONG, T.TEXT_MUTED,
                    T.RAISED_HOVER, T.LINE_HOVER),
    }

    def __init__(self, parent, text, command=None, variant="ghost",
                 small=False, bg=T.SURFACE, width=None):
        super().__init__(parent, bd=0, highlightthickness=0, bg=bg,
                         compound="center", cursor="hand2")
        self.h = T.px(T.CONTROL_H_SM if small else T.CONTROL_H)
        self.variant, self.parent_bg, self.command = variant, bg, command
        self.enabled = True
        self._hover = False
        self.font = T.font("value")
        self._pad = T.px(12 if small else 14)
        self._min_w = T.px(width) if width else 0
        self.configure(font=self.font, text=text)
        self._measure(text)
        self._paint()
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_click)

    def _measure(self, text):
        self.w = max(self._min_w, text_width(self.font, text) + self._pad * 2)

    def _colours(self):
        fill, line, fg, hfill, hline = self.VARIANTS[self.variant]
        if self._hover and self.enabled:
            fill, line = hfill, hline
        return (fill or self.parent_bg), line, fg

    def _paint(self):
        fill, line, fg = self._colours()
        img = P.rounded_rect(self.w, self.h, T.px(T.R_CONTROL), fill, line,
                             T.px(1), self.parent_bg)
        if not self.enabled:
            img = Image.blend(Image.new("RGB", img.size,
                                        P._rgb(self.parent_bg)), img, 0.4)
        _photo(self, img, "_bgimg")
        self.configure(image=self._bgimg,
                       fg=fg if self.enabled else T.TEXT_FAINT)

    def _on_enter(self, _e):
        self._hover = True
        self._paint()

    def _on_leave(self, _e):
        self._hover = False
        self._paint()

    def _on_click(self, _e):
        if self.enabled and self.command:
            self.command()

    def set_enabled(self, on):
        self.enabled = bool(on)
        self.configure(cursor="hand2" if on else "arrow")
        self._paint()

    def set_text(self, text):
        self.configure(text=text)
        self._measure(text)
        self._paint()


class Toggle(tk.Label):
    """40x23 switch. Replaces the old checkbox; the label sits to its left."""
    # Its appearance follows a setting, so the slide-in still leaves it
    # out rather than baking a state that is about to be replaced.
    _dynamic = True


    def __init__(self, parent, value=False, command=None, bg=T.SURFACE):
        super().__init__(parent, bd=0, highlightthickness=0, bg=bg,
                         cursor="hand2")
        self.value, self.command, self.bg = bool(value), command, bg
        self._paint()
        self.bind("<Button-1>", self._click)

    def _paint(self):
        _photo(self, P.toggle(self.value, self.bg))
        self.configure(image=self._img)

    def _click(self, _e=None):
        self.value = not self.value
        self._paint()
        if self.command:
            self.command(self.value)

    def set(self, value):
        self.value = bool(value)
        self._paint()

    def get(self):
        return self.value


class Meter(tk.Label):
    """6px capsule. Fill goes amber past 60% and danger past 85% -- the caller
    passes the level, thresholds live in the panel (see TKINTER-BUILD.md §9)."""
    # Its text follows a setting, so the slide-in still leaves it blank
    # rather than baking a value that is about to be replaced.
    _dynamic = True


    def __init__(self, parent, width, pct=0.0, level="ok", bg=T.SURFACE):
        super().__init__(parent, bd=0, highlightthickness=0, bg=bg)
        self.w, self.bg = T.px(width), bg
        self.set(pct, level)

    def set(self, pct, level="ok"):
        _photo(self, P.meter(self.w, float(pct), level, self.bg))
        self.configure(image=self._img)


def elide_left(font_spec, text, max_px):
    """Truncate from the left, so the folder name at the end stays visible."""
    if text_width(font_spec, text) <= max_px:
        return text
    ell = "…"
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi) // 2
        if text_width(font_spec, ell + text[mid:]) <= max_px:
            hi = mid
        else:
            lo = mid + 1
    return ell + text[lo:]


def elide_right(font_spec, text, max_px):
    if text_width(font_spec, text) <= max_px:
        return text
    ell = "…"
    for i in range(len(text), 0, -1):
        if text_width(font_spec, text[:i] + ell) <= max_px:
            return text[:i] + ell
    return ell


class _Box(RoundedFrame):
    """A fixed-height rounded control: the shared shell of Select, Field and
    HotkeyField."""

    def __init__(self, parent, height, bg=T.SURFACE, radius=None,
                 fill=T.RAISED, outline=T.LINE_STRONG, width=None):
        super().__init__(parent,
                         radius=T.R_CONTROL if radius is None else radius,
                         fill=fill, outline=outline, bg=bg,
                         height=T.px(height))
        self.fill, self.outline_c, self.parent_bg = fill, outline, bg
        if width:
            self.configure(width=T.px(width))
        self.pack_propagate(False)
        self.grid_propagate(False)

    def set_outline(self, colour):
        # A <Leave> can land after teardown has begun, which reaches here with
        # the strips already destroyed.
        self.outline_c = colour
        try:
            for edge in self._edges:
                edge.configure(bg=colour)
            for lbl, img in zip(self._masks,
                                corner_masks(self.radius, self.fill, colour,
                                             self.parent_bg)):
                _photo(lbl, img)
                lbl.configure(image=getattr(lbl, "_img"))
        except tk.TclError:
            return
        self._lift_chrome()


class Select(_Box):
    """36px select. The popup is a borderless Toplevel, not an OptionMenu --
    OptionMenu cannot be themed to this palette."""
    # Its text follows a setting, so the slide-in still leaves it blank
    # rather than baking a value that is about to be replaced.
    _dynamic = True


    def __init__(self, parent, values=(), index=0, command=None, bg=T.SURFACE,
                 width=None):
        super().__init__(parent, T.CONTROL_H, bg=bg, width=width)
        self.values = list(values)
        self.index = index if 0 <= index < len(self.values) else 0
        self.command = command
        self.popup = None
        self.text = tk.Label(self, bg=T.RAISED, fg=T.TEXT,
                             font=T.font("value"), anchor="w", cursor="hand2")
        self.text.pack(side="left", fill="x", expand=True, padx=(T.px(13), 0))
        self.chev = tk.Label(self, bg=T.RAISED, bd=0, highlightthickness=0,
                             cursor="hand2")
        _photo(self.chev, P.chevron(T.px(16), T.TEXT_FAINT, T.RAISED))
        self.chev.configure(image=self.chev._img)
        self.chev.pack(side="right", padx=(T.px(6), T.px(11)))
        for w in (self, self.text, self.chev):
            w.bind("<Button-1>", self._toggle)
            w.bind("<Enter>", self._hover_on)
            w.bind("<Leave>", self._hover_off)
        self.bind("<Configure>", lambda _e: self._render())
        self._render()

    def _render(self):
        label = self.values[self.index] if self.values else ""
        avail = (self.winfo_width() or T.px(T.CONTROL_COL)) - T.px(46)
        self.text.configure(text=elide_right(T.font("value"), label, avail))

    def _hover_on(self, _e):
        if not self.popup:
            self._fill(T.RAISED_HOVER, T.LINE_HOVER)

    def _hover_off(self, _e):
        if not self.popup:
            self._fill(T.RAISED, T.LINE_STRONG)

    def _fill(self, colour, outline):
        self.fill = colour
        self.configure(bg=colour)
        self.text.configure(bg=colour)
        self.chev.configure(bg=colour)
        _photo(self.chev, P.chevron(T.px(16), T.TEXT_FAINT, colour))
        self.chev.configure(image=self.chev._img)
        self.set_outline(outline)

    def _toggle(self, _e=None):
        self.close() if self.popup else self.open()

    def open(self):
        if self.popup or not self.values:
            return
        self.set_outline(T.PURPLE_LIGHT)
        top = tk.Toplevel(self)
        self.popup = top
        top.overrideredirect(True)
        top.attributes("-topmost", True)
        top.configure(bg=T.LINE_STRONG)
        inner = tk.Frame(top, bg=T.SURFACE)
        inner.pack(fill="both", expand=True, padx=T.px(1), pady=T.px(1))
        w = self.winfo_width()
        for i, v in enumerate(self.values):
            sel = i == self.index
            lbl = tk.Label(inner,
                           text=elide_right(T.font("value"), v, w - T.px(26)),
                           bg=T.PURPLE if sel else T.SURFACE,
                           fg=T.TEXT_ON_PURPLE if sel else T.TEXT,
                           font=T.font("value"), anchor="w", cursor="hand2",
                           padx=T.px(13))
            lbl.pack(fill="x", ipady=T.px(6))
            lbl.bind("<Button-1>", lambda _e, n=i: self._choose(n))
            lbl.bind("<Enter>", lambda _e, l=lbl, s=sel:
                     l.configure(bg=T.PURPLE if s else T.RAISED_HOVER))
            lbl.bind("<Leave>", lambda _e, l=lbl, s=sel:
                     l.configure(bg=T.PURPLE if s else T.SURFACE))
        top.update_idletasks()
        x = self.winfo_rootx()
        y = self.winfo_rooty() + self.winfo_height() + T.px(4)
        h = top.winfo_reqheight()
        if y + h > self.winfo_screenheight():       # flip above rather than
            y = self.winfo_rooty() - h - T.px(4)    # fall off the bottom
        top.geometry(f"{w}x{h}+{x}+{y}")

    def close(self):
        if self.popup:
            self.popup.destroy()
            self.popup = None
        self._fill(T.RAISED, T.LINE_STRONG)

    def _choose(self, i):
        self.index = i
        self.close()
        self._render()
        if self.command:
            self.command(i)

    def set_values(self, values, index=0):
        self.values = list(values)
        self.index = index if 0 <= index < len(self.values) else 0
        self._render()

    def current(self):
        return self.index

    def value(self):
        return self.values[self.index] if self.values else None


class Field(_Box):
    """Read-only path field. Mono, truncated from the left."""
    # Its text follows a setting, so the slide-in still leaves it blank
    # rather than baking a value that is about to be replaced.
    _dynamic = True


    def __init__(self, parent, text="", bg=T.SURFACE, width=None):
        super().__init__(parent, T.CONTROL_H, bg=bg, width=width)
        self.full = text
        self.label = tk.Label(self, bg=T.RAISED, fg=T.TEXT,
                              font=T.font("mono"), anchor="w")
        self.label.pack(side="left", fill="x", expand=True,
                        padx=(T.px(13), T.px(11)))
        self.bind("<Configure>", lambda _e: self._render())
        self._render()

    def _render(self):
        avail = (self.winfo_width() or T.px(240)) - T.px(24)
        self.label.configure(text=elide_left(T.font("mono"), self.full, avail))

    def set(self, text):
        self.full = text
        self._render()

    def get(self):
        return self.full


class Segmented(_Box):
    """Track with 3px padding; the selected cell is a purple fill."""
    # Not _dynamic: its wording is three fixed options, not a setting, so the
    # still carries them. Which cell is lit is chrome, and is drawn too.


    def __init__(self, parent, options, index=0, command=None, bg=T.SURFACE):
        # 30px cells inside 3px padding inside a 1px border: 38, not the 36 a
        # plain control is.
        super().__init__(parent, T.CONTROL_H_SM + 6 + 2, bg=bg, radius=8)
        self.options, self.index, self.command = list(options), index, command
        self.cells = []
        pad = T.px(3)
        holder = self.holder = tk.Frame(self, bg=T.RAISED)
        holder.pack(fill="both", expand=True, padx=pad, pady=pad)
        self.cell_h = T.px(T.CONTROL_H_SM)
        last = len(self.options) - 1
        for i, opt in enumerate(self.options):
            # bg matters: the image does not cover every pixel of the label,
            # and Tk's default light-grey background shows as a bright rim.
            # padx/pady zeroed: a Label carries 1px of its own on each side,
            # which is not in the width totalled up below. Three cells wanted
            # six pixels the track had not budgeted, so the last one hung over
            # the end and lost the round of its pill to the clip.
            lbl = tk.Label(holder, text=opt, bd=0, highlightthickness=0,
                           padx=0, pady=0,
                           bg=T.RAISED, compound="center", cursor="hand2",
                           font=T.font("value"))
            lbl._w_px = text_width(T.font("value"), opt) + T.px(32)
            lbl.grid(row=0, column=i,
                     padx=(0, T.px(3) if i < last else 0))
            lbl.bind("<Button-1>", lambda _e, n=i: self.set(n, notify=True))
            self.cells.append(lbl)
        # _Box switches propagation off so the fixed height survives, which
        # also stops the track sizing itself from its cells - so total it up.
        # Exactly the cells, the gaps between them and the padding round the
        # outside. The stray +2 that used to be here was standing in for the
        # Labels' own padding and was four pixels short of it.
        self.configure(width=(sum(c._w_px for c in self.cells)
                              + T.px(3) * last + pad * 2))
        self._cell_imgs = []
        self._paint()
        # Cell positions are only real once the track has been laid out, and
        # the corner arcs are cut from them.
        self.bind("<Configure>", lambda _e: self._patch_corners(), add="+")

    def _paint(self):
        shown = []
        for i, lbl in enumerate(self.cells):
            sel = i == self.index
            fill = T.PURPLE if sel else T.RAISED
            img = P.rounded_rect(lbl._w_px, self.cell_h, T.px(T.R_SEG_CELL),
                                 fill, None, 1, T.RAISED)
            shown.append(img)
            _photo(lbl, img)
            lbl.configure(
                image=lbl._img,
                fg=T.TEXT_ON_PURPLE if sel else T.TEXT_MUTED,
                font=T.font("value", T.FONT_UI_MEDIUM if sel else None))
        self._cell_imgs = shown
        self._patch_corners()

    def _patch_corners(self):
        """The track's corner arcs overlap the first and last cells.

        Only 3px of padding separates a cell from the track's edge, and the
        radius is 8, so a flat arc in the track colour cuts a square notch out
        of the selected cell whenever it is one of the ends. Cut each corner
        from what is really underneath instead.

        Positions come from Tk rather than from adding up paddings: grid
        distributes the couple of pixels the track carries over its cells, so
        the arithmetic was a pixel or two out and the crop landed on the flat
        middle of a pill rather than on its rounded end.
        """
        r = self.radius
        w, h = self.winfo_width(), self.winfo_height()
        if w <= 2 * r or h <= 2 * r or not self._cell_imgs:
            return
        hx, hy = self.holder.winfo_x(), self.holder.winfo_y()
        placed = []
        for lbl, img in zip(self.cells, self._cell_imgs):
            # A Label pads and centres its image, so the pill is a pixel in
            # from the cell's own origin. Reading the cell alone put the crop
            # a pixel off and squared the rounded end off again.
            placed.append((hx + lbl.winfo_x()
                           + (lbl.winfo_width() - img.width) // 2,
                           hy + lbl.winfo_y()
                           + (lbl.winfo_height() - img.height) // 2, img))
        for idx, (ax, ay) in enumerate(((0, 0), (1, 0), (0, 1), (1, 1))):
            px0 = 0 if ax == 0 else w - r
            py0 = 0 if ay == 0 else h - r
            patch = Image.new("RGB", (r, r), P._rgb(T.RAISED))
            hit = False
            for cx, cy, img in placed:
                x0, y0 = max(px0, cx), max(py0, cy)
                x1 = min(px0 + r, cx + img.width)
                y1 = min(py0 + r, cy + img.height)
                if x1 > x0 and y1 > y0:
                    patch.paste(img.crop((x0 - cx, y0 - cy,
                                          x1 - cx, y1 - cy)),
                                (x0 - px0, y0 - py0))
                    hit = True
            if hit:
                self.set_corner_patch(idx, patch)

    def set(self, index, notify=False):
        if not 0 <= index < len(self.options):
            return
        self.index = index
        self._paint()
        if notify and self.command:
            self.command(index)

    def current(self):
        return self.index


class Slider(tk.Canvas):
    """4px track, purple-light fill, 14px cream knob. Pair it with a
    fixed-width mono readout or the row twitches while dragging."""
    # Its appearance follows a setting, so the slide-in still leaves it
    # out rather than baking a state that is about to be replaced.
    _dynamic = True


    def __init__(self, parent, lo=0, hi=100, value=0, command=None,
                 bg=T.SURFACE, width=None, step=1):
        self.h = T.px(20)
        super().__init__(parent, bg=bg, highlightthickness=0, bd=0,
                         height=self.h,
                         width=T.px(width) if width else T.px(200))
        self.lo, self.hi, self.step = lo, hi, step
        self.val = value
        self.command = command
        self.bg = bg
        self.bind("<Configure>", lambda _e: self._draw())
        self.bind("<Button-1>", self._jump)
        self.bind("<B1-Motion>", self._jump)
        self.bind("<Left>", lambda _e: self._nudge(-1))
        self.bind("<Right>", lambda _e: self._nudge(1))
        self.configure(takefocus=1)

    def _frac(self):
        span = (self.hi - self.lo) or 1
        return max(0.0, min(1.0, (self.val - self.lo) / span))

    def _draw(self):
        self.delete("all")
        w = self.winfo_width() or T.px(200)
        k = T.px(T.KNOB_D)
        cy = self.h // 2
        th = T.px(T.TRACK_H)
        x0, x1 = k // 2, w - k // 2
        self.create_rectangle(x0, cy - th // 2, x1, cy + th // 2,
                              fill=T.LINE_STRONG, outline="")
        fx = x0 + (x1 - x0) * self._frac()
        if fx > x0:
            self.create_rectangle(x0, cy - th // 2, fx, cy + th // 2,
                                  fill=T.PURPLE_LIGHT, outline="")
        P.photo(self, P.knob(k, T.TEXT_ON_PURPLE, self.bg), "_knob")
        self.create_image(fx, cy, image=self._knob)

    def _from_x(self, x):
        w = self.winfo_width() or T.px(200)
        k = T.px(T.KNOB_D)
        x0, x1 = k // 2, w - k // 2
        f = 0.0 if x1 == x0 else (x - x0) / (x1 - x0)
        f = max(0.0, min(1.0, f))
        raw = self.lo + f * (self.hi - self.lo)
        return int(round(raw / self.step) * self.step)

    def _jump(self, e):
        self.focus_set()
        self.set(self._from_x(e.x), notify=True)

    def _nudge(self, d):
        self.set(self.val + d * self.step, notify=True)

    def set(self, value, notify=False):
        value = max(self.lo, min(self.hi, value))
        changed = value != self.val
        self.val = value
        self._draw()
        if notify and changed and self.command:
            self.command(value)

    def get(self):
        return self.val


class HotkeyField(_Box):
    """34px keycap. The lighter bottom edge is what suggests a key."""
    # Its text follows a setting, so the slide-in still leaves it blank
    # rather than baking a value that is about to be replaced.
    _dynamic = True


    PAD = 16                  # each side of the caption
    MAX_W = T.CONTROL_COL     # never wider than the column it sits in

    def __init__(self, parent, text="", command=None, bg=T.SURFACE, width=None):
        super().__init__(parent, T.KBD_H, bg=bg, width=width)
        self.command = command
        self._min_w = T.px(width) if width else 0
        self._held_w = 0          # floor while a capture is in progress
        # bd/padx zeroed so the label asks for exactly its text: the box is
        # sized from a font measurement, and Tk's own default padding around a
        # Label is invisible in that sum and shows up as a clipped glyph.
        self.label = tk.Label(self, bg=T.RAISED, fg=T.TEXT, bd=0, padx=0,
                              pady=0, highlightthickness=0,
                              font=T.font("mono"), cursor="hand2", text=text)
        self.label.pack(fill="both", expand=True, padx=T.px(self.PAD))
        self.lip = tk.Frame(self, bg="#3C3C44", height=T.px(1))
        self.lip.place(relx=0, rely=1.0, relwidth=1.0, y=-T.px(1), anchor="nw")
        for w in (self, self.label):
            w.bind("<Button-1>", self._click)
        self._fit()

    def _fit(self):
        """Grow to the caption. The width passed in is a floor, not a size:
        a keycap is as wide as the combination on it, and combinations run
        from "Ins" to "Ctrl + Alt + Shift + F12"."""
        try:
            # +2 because a measured advance is not always the inked width, and
            # a keycap one pixel short of its caption is the whole complaint.
            want = (text_width(self.label.cget("font"),
                               self.label.cget("text"))
                    + 2 * T.px(self.PAD) + 2)
            self.configure(width=max(self._min_w, self._held_w,
                                     min(want, T.px(self.MAX_W))))
        except tk.TclError:
            pass

    def _click(self, _e=None):
        if self.command:
            self.command(self)

    def set_text(self, text):
        self.label.configure(text=text)
        self._fit()

    def get_text(self):
        return self.label.cget("text")

    def mark(self, mode="rest"):
        """rest | capturing | error"""
        if mode == "capturing":
            # Hold the width for the duration. "Press keys..." is narrower
            # than most combinations, so without this the field visibly
            # shrinks the moment you click it and snaps back afterwards.
            self._held_w = max(self._held_w, self.winfo_width())
            self.set_outline(T.PURPLE_LIGHT)
            self.label.configure(fg=T.PURPLE_LIGHT)
        elif mode == "error":
            self.set_outline(T.DANGER)
            self.label.configure(fg=T.TEXT)
        else:
            self._held_w = 0
            self.set_outline(T.LINE_STRONG)
            self.label.configure(fg=T.TEXT)
            self._fit()


class Scrollbar(tk.Canvas):
    """A 10px scrollbar that can actually be themed.

    Tk's own scrollbar takes a Windows look that nothing in this palette can
    reach, so this is a canvas: a rounded LINE_STRONG thumb inset 3px on a
    track that stays the panel colour. It hides itself when the content fits,
    which is the only time a scrollbar should ever be absent.
    """

    W = 10

    def __init__(self, parent, target, bg=T.PANEL):
        super().__init__(parent, width=T.px(self.W), bg=bg,
                         highlightthickness=0, bd=0)
        self.target = target
        self.bg = bg
        self.first, self.last = 0.0, 1.0
        self._drag_from = None
        self._hover = False
        self.bind("<Configure>", lambda _e: self._draw())
        self.bind("<Button-1>", self._press)
        self.bind("<B1-Motion>", self._drag)
        self.bind("<ButtonRelease-1>", lambda _e: setattr(self, "_drag_from",
                                                          None))
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)

    # target calls this as its yscrollcommand
    def set(self, first, last):
        self.first, self.last = float(first), float(last)
        self._draw()

    def needed(self):
        return (self.last - self.first) < 0.999

    def _enter(self, _e):
        self._hover = True
        self._draw()

    def _leave(self, _e):
        self._hover = False
        self._draw()

    def _geom(self):
        h = self.winfo_height() or 1
        span = max(0.06, self.last - self.first)     # keep it grabbable
        th = max(T.px(28), int(h * span))
        ty = int((h - th) * (self.first / max(1e-6, 1 - (self.last - self.first))))
        return h, th, max(0, min(h - th, ty))

    def _draw(self):
        self.delete("all")
        if not self.needed():
            return
        w = self.winfo_width() or T.px(self.W)
        _h, th, ty = self._geom()
        img = P.scroll_thumb(w, th,
                             T.LINE_HOVER if self._hover else T.LINE_STRONG,
                             self.bg)
        _photo(self, img, "_thumb")
        self.create_image(0, ty, image=self._thumb, anchor="nw")

    def _press(self, e):
        h, th, ty = self._geom()
        if ty <= e.y <= ty + th:
            self._drag_from = e.y - ty
        else:
            self._drag_from = th // 2
            self._to(e.y - self._drag_from, h, th)

    def _drag(self, e):
        if self._drag_from is None:
            return
        h, th, _ = self._geom()
        self._to(e.y - self._drag_from, h, th)

    def _to(self, ty, h, th):
        frac = 0.0 if h == th else max(0.0, min(1.0, ty / (h - th)))
        span = self.last - self.first
        self.target.yview_moveto(frac * (1 - span))


class IconButton(_Box):
    """A ghost button with a 16px icon before its caption.

    Not the plain Button: that one is a single Label whose image slot is
    already taken by its own rounded rectangle, so there is nowhere to put a
    glyph. This is a rounded frame with the icon and caption packed inside.
    """

    def __init__(self, parent, text, icon, command=None, bg=T.SURFACE,
                 small=True):
        h = T.CONTROL_H_SM if small else T.CONTROL_H
        super().__init__(parent, h, bg=bg)
        self.command = command
        pad = T.px(12 if small else 14)
        self.icon = tk.Label(self, bd=0, highlightthickness=0, bg=T.RAISED,
                             cursor="hand2")
        _photo(self.icon, icon)
        self.icon.configure(image=self.icon._img)
        self.icon.pack(side="left", padx=(pad, 0))
        self.text = tk.Label(self, text=text, bg=T.RAISED, fg=T.TEXT,
                             font=T.font("value"), cursor="hand2")
        self.text.pack(side="left", padx=(T.px(7), pad))
        self.configure(width=(pad * 2 + icon.width + T.px(7)
                              + text_width(T.font("value"), text) + T.px(2)))
        for w in (self, self.icon, self.text):
            w.bind("<Button-1>", self._click)
            w.bind("<Enter>", self._on)
            w.bind("<Leave>", self._off)

    def _fill(self, colour, outline):
        self.fill = colour
        for w in (self, self.icon, self.text):
            w.configure(bg=colour)
        self.set_outline(outline)

    def _on(self, _e):
        self._fill(T.RAISED_HOVER, T.LINE_HOVER)

    def _off(self, _e):
        self._fill(T.RAISED, T.LINE_STRONG)

    def _click(self, _e=None):
        if self.command:
            self.command()


class SearchField(_Box):
    """34px search box: icon, entry, and the Ctrl F hint on the right."""

    def __init__(self, parent, command=None, bg="#0E0E11", placeholder="Search settings"):
        super().__init__(parent, 34, bg=bg, radius=8)
        self.command = command
        self.placeholder = placeholder
        icon = tk.Label(self, bd=0, highlightthickness=0, bg=T.RAISED)
        _photo(icon, P.search_icon(T.px(15), T.TEXT_FAINT, T.RAISED))
        icon.configure(image=icon._img)
        icon.pack(side="left", padx=(T.px(12), 0))
        self.icon = icon

        self.hint = tk.Label(self, text="Ctrl F", bg=T.RAISED, fg="#46433E",
                             font=T.font("mono_xs"))
        self.hint.pack(side="right", padx=(T.px(6), T.px(12)))

        self.var = tk.StringVar()
        self.entry = tk.Entry(self, textvariable=self.var, bd=0,
                              highlightthickness=0, bg=T.RAISED, fg=T.TEXT,
                              insertbackground=T.TEXT, font=T.font("value"))
        self.entry.pack(side="left", fill="x", expand=True, padx=(T.px(9), 0))
        self._show_placeholder()
        self.entry.bind("<FocusIn>", self._focus_in)
        self.entry.bind("<FocusOut>", self._focus_out)
        self.var.trace_add("write", lambda *_a: self._changed())

    def _show_placeholder(self):
        self._ph = True
        self.entry.configure(fg=T.TEXT_FAINT)
        self.var.set(self.placeholder)

    def _focus_in(self, _e):
        self.set_outline(T.PURPLE_LIGHT)
        if self._ph:
            self._ph = False
            self.var.set("")
            self.entry.configure(fg=T.TEXT)

    def _focus_out(self, _e):
        self.set_outline(T.LINE_STRONG)
        if not self.var.get():
            self._show_placeholder()

    def _changed(self):
        if self._ph:
            return
        if self.command:
            self.command(self.var.get().strip())

    def query(self):
        return "" if self._ph else self.var.get().strip()

    def clear(self):
        self._ph = False
        self.var.set("")
        self._show_placeholder()

    def focus(self):
        self.entry.focus_set()

    def matches(self, n):
        self.hint.configure(
            text="Ctrl F" if self._ph or not self.var.get()
            else f"{n} match" + ("" if n == 1 else "es"),
            fg="#46433E" if self._ph else T.TEXT_MUTED)
