# -*- coding: utf-8 -*-
"""Render actual-size PNGs of every menu state, at 1x and 2x.

    python render_reference.py

The Tk view has to match these. Sizes come from nabd_tray_model, so a change
to the metrics shows up here as a differently sized PNG rather than as a
drawing that quietly drifts from the spec.
"""
import pathlib, sys
from nabd_tray_model import (Menu, State, C, PAD, ROW_H, SEP_H, STATUS_H,
                             ROW_PAD_X, ROW_RADIUS, GAP, MARK, METER_H, TICK_W,
                             ITEM, SEP, STATUS)

BRAND = pathlib.Path("/home/claude/nabd/refresh/out/brand")


def mark_svg(colour, px):
    import re
    s = (BRAND / "nabd-mark-cream.svg").read_text()
    vb = re.search(r'viewBox="([^"]+)"', s).group(1)
    body = s[s.index(">", s.index("<svg")) + 1: s.rindex("</svg>")]
    body = re.sub(r"<metadata>.*?</metadata>", "", body, flags=re.S)
    body = body.replace('fill="#E8E4DC"', 'fill="%s"' % colour)
    return '<svg viewBox="%s" style="width:%dpx;height:%dpx;display:block">%s</svg>' % (
        vb, px, px, body)


def html(menu, focus=None, hover=None):
    st = menu.state
    label, buf, fill = menu.status_text()
    on = st.recording
    out = ['<div class="menu">']
    for i, r in enumerate(menu.rows):
        if r.kind == SEP:
            out.append('<div class="sep" style="height:%dpx"></div>' % r.height)
        elif r.kind == STATUS:
            out.append(
                '<div class="stat%s" style="height:%dpx">'
                '<div class="top">%s<span class="st">%s</span>'
                '<span class="buf">%s</span></div>'
                '<div class="meter"><i style="width:%.1f%%"></i></div></div>'
                % ("" if on else " off", r.height,
                   mark_svg(C["lit"] if on else C["mark_off"], MARK),
                   label, buf, fill * 100))
        else:
            cls = ["row"]
            if r.primary: cls.append("prim")
            if r.default: cls.append("bold")
            if not r.enabled: cls.append("dim")
            if i == hover: cls.append("hov")
            if i == focus: cls.append("focus")
            out.append('<div class="%s" style="height:%dpx"><span class="ind"></span>%s%s</div>'
                       % (" ".join(cls), r.height, r.label,
                          ('<span class="k">%s</span>' % r.accel) if r.accel else ""))
    out.append("</div>")
    return "".join(out)


def fontface():
    """Inline the real faces. Google Fonts is not reachable from the build box,
    and a pixel reference set in a fallback face is not a pixel reference."""
    import base64
    root = pathlib.Path("/tmp/fonts/ttf")
    faces = [("Outfit", 400, "Outfit-Regular.ttf"), ("Outfit", 500, "Outfit-Medium.ttf"),
             ("JetBrains Mono", 400, "JetBrainsMono-Regular.ttf")]
    out = []
    for fam, wt, name in faces:
        f = root / name
        if not f.exists():
            raise SystemExit("missing %s -- the references must use the real faces" % f)
        out.append("@font-face{font-family:'%s';font-weight:%d;font-style:normal;"
                   "src:url(data:font/ttf;base64,%s) format('truetype')}"
                   % (fam, wt, base64.b64encode(f.read_bytes()).decode()))
    return "".join(out)


CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{background:transparent;font-family:Outfit,system-ui,sans-serif}
.menu{width:%(W)dpx;height:%(H)dpx;background:%(menu)s;border:1px solid %(border)s;
  border-radius:8px;padding:%(PAD)dpx;font-size:13px;color:%(text)s}
.row{display:flex;align-items:center;gap:%(GAP)dpx;padding:0 %(PADX)dpx;
  border-radius:%(RR)dpx;white-space:nowrap}
.row .k{margin-left:auto;font-family:'JetBrains Mono',monospace;font-size:10.5px;color:%(faint)s}
.row.dim{color:%(faint)s}
.row.bold{font-weight:500}
.row.prim{font-weight:500}.row.prim .k{color:%(lit)s}
.row.prim.dim .k{color:%(faint)s}
.row.hov{background:%(hover)s}
.row.prim.hov{background:%(deep)s}.row.prim.hov .k{color:%(key)s}
.row.focus{box-shadow:inset 0 0 0 1px %(lit)s}
.ind{width:%(TICK)dpx;flex:0 0 %(TICK)dpx}
.sep{display:flex;align-items:center;padding:0 9px}
.sep::before{content:"";display:block;width:100%%;height:1px;background:%(rule)s}
.stat{padding:11px %(PADX)dpx 0}
.stat .top{display:flex;align-items:center;gap:%(GAP)dpx;height:%(MARK)dpx}
.stat .st{font-weight:500}
.stat.off .st{color:%(muted)s}
.stat .buf{margin-left:auto;font-family:'JetBrains Mono',monospace;font-size:11px;
  color:%(muted)s;font-variant-numeric:tabular-nums}
.meter{margin-top:10px;height:%(METER)dpx;border-radius:2px;background:%(meter_bg)s;overflow:hidden}
.meter i{display:block;height:100%%;background:%(lit)s}
.stat.off .meter i{background:%(meter_off)s}
"""


def main():
    from playwright.sync_api import sync_playwright
    out = pathlib.Path("reference"); out.mkdir(exist_ok=True)
    states = {
        "full":     (State(True, 60, 60), None, None),
        "filling":  (State(True, 22, 60), None, None),
        "paused":   (State(False, 0, 60), None, None),
        "hover":    (State(True, 60, 60), None, 2),
        "focus":    (State(True, 60, 60), 3, None),
    }
    base = Menu.build(State())
    css = fontface() + CSS % dict(W=base.width, H=base.height, PAD=PAD,
                                  PADX=ROW_PAD_X, RR=ROW_RADIUS, GAP=GAP,
                                  TICK=TICK_W, MARK=MARK, METER=METER_H, **C)
    made = []
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        for scale in (1, 2):
            pg = b.new_page(viewport={"width": 420, "height": 420},
                            device_scale_factor=scale)
            for name, (st, focus, hover) in states.items():
                m = Menu.build(st)
                pg.set_content("<style>%s</style>%s" % (css, html(m, focus, hover)))
                pg.wait_for_timeout(350)
                p = out / ("menu-%s@%dx.png" % (name, scale))
                pg.locator(".menu").screenshot(path=str(p))
                made.append((p, m, scale))
            pg.close()
        b.close()

    from PIL import Image
    print("%-26s %-11s %s" % ("file", "pixels", "expected from the model"))
    bad = 0
    for p, m, scale in made:
        im = Image.open(p)
        want = (m.width * scale, m.height * scale)
        flag = "" if im.size == want else "   <-- MISMATCH"
        if flag:
            bad += 1
        print("%-26s %-11s %dx%d%s" % (p.name, "%dx%d" % im.size, *want, flag))
    if bad:
        raise SystemExit("%d reference(s) do not match the model's metrics" % bad)
    print("\nevery reference matches nabd_tray_model's metrics")


if __name__ == "__main__":
    main()
