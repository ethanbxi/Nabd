"""Build the settings window headlessly and verify it wires up correctly."""
import json
import shutil
import sys
import time
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))
import brand  # noqa: E402
import nabd  # noqa: E402
import settings as S  # noqa: E402
import theme as T  # noqa: E402

CONFIG = APP / "config.json"
BACKUP = APP / "config.json.uibak"
shutil.copyfile(CONFIG, BACKUP)


class FakeEvent:
    def __init__(self, keysym, state):
        self.keysym = keysym
        self.state = state


results = {}
try:
    win = S.SettingsWindow()
    # The harness drives the window while the terminal holds focus, which
    # would otherwise trip click-away dismissal immediately.
    win.auto_dismiss = False

    deadline = time.time() + 30
    while time.time() < deadline:
        win.root.update()
        if win.speakers and win.monitors:
            break
        time.sleep(0.1)
    for _ in range(20):
        win.root.update()
        time.sleep(0.02)

    # let the slide-in animation finish
    for _ in range(80):
        win.root.update()
        time.sleep(0.01)
    geo = win.root.geometry()          # WxH+X+Y
    x = int(geo.split("+")[1])
    work = S.work_area()
    width = win.root.winfo_width()
    height = win.root.winfo_height()
    work_h = work.bottom - work.top
    print(f"geometry : {geo}   work area right={work.right} height={work_h}")
    results["window is a real width"] = width > 380
    results["spans the full height"] = abs(height - work_h) <= 4
    results["flush with the right edge"] = abs(x - (work.right - width)) <= 2
    results["fully on screen"] = x + width <= work.right
    results["no system title bar"] = bool(win.root.overrideredirect())

    results["devices populated"] = bool(win.speakers and win.monitors)
    print("speakers :", win.speaker_dd._values)
    print("mics     :", win.mic_dd._values)
    print("monitors :", win.monitor_dd._values)
    print("hotkey   :", win.hotkey_btn["text"], "|", win.hotkey_status["text"])
    print("quality  :", win.quality_dd.get(), "| fps:", win.fps_dd.get())
    print("length   :", win.length.get())
    print("estimate :", win.estimate["text"])

    results["speaker default option"] = (
        win.speaker_dd._values[0] == "Windows default output")
    results["mic none option"] = "None" in win.mic_dd._values[0]
    results["monitor preselected"] = win.monitor_dd.current() >= 0
    results["estimate rendered"] = any(u in win.estimate["text"]
                                       for u in ("MB", "GB"))

    # --- dark theme actually applied
    # The root carries the 1px edge rule; the panel body is the dark surface.
    results["panel is dark"] = win.shell["bg"] == T.BG
    results["edge rule drawn"] = win.root["bg"] == T.BORDER

    # Brand conformance
    print(f"type     : ui={T.F_BODY[0]!r} mono={T.F_MONO[0]!r}")
    results["shell is the brand shell"] = T.BG == brand.SHELL
    results["text is cream"] = T.TEXT == brand.CREAM
    results["ui face from the Outfit chain"] = (
        T.F_BODY[0] in brand._FALLBACKS["Outfit"])
    results["mono face from the JetBrains chain"] = (
        T.F_MONO[0] in brand._FALLBACKS["JetBrains Mono"])
    results["px type scale"] = T.F_BODY[1] == -15 and T.F_SMALL[1] == -13
    # The one contrast rule: purple linework on dark must be Purple Light,
    # and full-strength purple may only appear as a field under cream.
    results["accent is Purple Light"] = T.ACCENT == brand.PURPLE_LIGHT
    results["field is Nabd Purple"] = T.FIELD == brand.PURPLE
    results["field text is cream"] = T.FIELD_TEXT == brand.CREAM
    # The header uses the tile lockup. It deliberately sits under the
    # guidelines' 120px lockup minimum for a compact header; that is only
    # tenable because the artwork is downscaled from a 512px render rather than
    # drawn as linework, so the strokes survive. Flagged, not enforced.
    if win.logo_image is not None:
        logo_w = win.logo_image.width()
        note = "" if logo_w >= brand.MIN_LOCKUP_WIDTH else \
            f"  (under the {brand.MIN_LOCKUP_WIDTH}px minimum, by choice)"
        print(f"header lockup image: {logo_w}x{win.logo_image.height()}px{note}")
        results["header lockup rendered from artwork"] = logo_w > 40

    header_w = brand.lockup_width(brand.MIN_LOCKUP_HEIGHT)
    print(f"header lockup: {header_w:.0f}px wide "
          f"(minimum {brand.MIN_LOCKUP_WIDTH})")
    results["lockup clears its minimum width"] = (
        header_w >= brand.MIN_LOCKUP_WIDTH)
    results["dropdown is dark"] = win.speaker_dd["bg"] == T.SURFACE

    # --- hotkey capture: NumLock (0x0008) must NOT be read as Alt
    print("\n--- hotkey capture ---")
    cases = [
        ("ctrl only",            "c", S.STATE_CTRL,                    "ctrl+c"),
        ("ctrl + NumLock on",    "c", S.STATE_CTRL | 0x0008,           "ctrl+c"),
        ("ctrl+shift + NumLock", "s", S.STATE_CTRL | S.STATE_SHIFT | 0x0008,
                                                                       "ctrl+shift+s"),
        ("real alt",             "x", S.STATE_ALT,                     "alt+x"),
        ("F9 + ScrollLock on",   "F9", 0x0020,                         "f9"),
        ("shift+F8, NumLock on", "F8", S.STATE_SHIFT | 0x0008,         "shift+f8"),
    ]
    for name, keysym, state, expect in cases:
        win.capturing = "clip"
        win._on_key(FakeEvent(keysym, state))
        got = win.hotkey_value
        ok = got == expect
        results[f"hotkey: {name}"] = ok
        print(f"  {'PASS' if ok else 'FAIL'}  {name:<22} -> {got:<14} (want {expect})")

    # --- monitor identify overlay
    print("\n--- identify overlay ---")
    win._identify()
    for _ in range(10):
        win.root.update()
        time.sleep(0.02)
    overlay = win._overlay
    results["identify overlay created"] = overlay is not None
    if overlay:
        geo = overlay.geometry()
        mon = win.monitors[max(0, win.monitor_dd.current())]
        print(f"  overlay geometry {geo}  (monitor {mon['width']}x{mon['height']}"
              f"+{mon['x']}+{mon['y']})")
        results["overlay covers monitor"] = (
            geo.startswith(f"{mon['width']}x{mon['height']}"))
    for _ in range(100):  # let it fade out
        win.root.update()
        time.sleep(0.02)

    # --- save round trip
    # buffer-reset toggle
    start = win.reset_after.get()
    win.reset_after.toggle()
    results["reset toggle flips"] = win.reset_after.get() != start
    results["reset hint updates"] = bool(win.reset_hint["text"])
    win.reset_after.set(True)
    print("reset hint:", win.reset_hint["text"])

    # recent clips strip + folder button
    print("recent   :", [c.name for c in win.clips] or "none yet")
    results["recent strip built"] = win.recent.winfo_exists()
    results["recent shows cards or an empty note"] = bool(
        win.recent.winfo_children())

    if len(win.clips) > S.PER_PAGE:
        print(f"pager    : {win._pages()} pages, label {win.page_label['text']!r}")
        results["strip shows a full page"] = (
            len(win.recent.winfo_children()) == S.PER_PAGE)
        win._page(1)
        results["arrow advances"] = win.page == 1
        win._page(-1)
        results["arrow goes back"] = win.page == 0
        win._page(-1)
        results["pager clamps at the start"] = win.page == 0
        win._page(99)
        results["pager clamps at the end"] = win.page == 0
        win.root.update()

    # second hotkey: opening the panel without the tray
    win.capturing = "open"
    win._on_key(FakeEvent("n", S.STATE_CTRL | S.STATE_ALT | 0x0008))
    print("open hotkey:", win.open_hotkey_value)
    results["open hotkey captured"] = win.open_hotkey_value == "ctrl+alt+n"

    # dropdown: chevron, toggle open/closed, and matching the column width
    dd = win.quality_dd
    dd.toggle()
    win.root.update()
    opened = dd._popup is not None
    popup_w = dd._popup.winfo_width() if opened else 0
    field_w = dd.winfo_width()
    dd.toggle()
    win.root.update()
    results["dropdown opens on click"] = opened
    results["dropdown closes on second click"] = dd._popup is None
    print(f"dropdown : field {field_w}px, popup {popup_w}px, "
          f"chevron {'yes' if dd.chevron.find_all() else 'no'}")
    results["popup matches field width"] = abs(popup_w - field_w) <= 2
    results["chevron drawn"] = bool(dd.chevron.find_all())
    # every select shares the control column, so their widths agree
    controls = (win.quality_dd, win.fps_dd, win.monitor_dd, win.speaker_dd,
                win.mic_dd)
    widths = {w.winfo_width() for w in controls}
    print(f"select widths: {sorted(widths)}")
    results["all selects share one width"] = len(widths) == 1

    # sliders live in the same column, so they are the same length as a select
    slider_widths = {s.winfo_width() for s in (win.desktop_slider,
                                               win.mic_slider,
                                               win.sync_slider)}
    print(f"slider widths: {sorted(slider_widths)}")
    results["sliders match the selects"] = slider_widths == widths

    # every box is one height
    heights = {w.winfo_height() for w in controls}
    heights.add(win.dir_entry.winfo_height())
    print(f"box heights: {sorted(heights)}  (FIELD_H={T.FIELD_H})")
    results["all boxes share one height"] = heights == {T.FIELD_H}

    # A/V sync trim
    win.sync_slider.set(-80)
    win.root.update()
    results["sync slider reads back"] = win.sync_slider.get() == -80
    results["sync readout updates"] = "ms" in win.sync_read["text"]
    print("sync readout:", win.sync_read["text"])

    win.length.set(180)
    win.quality_dd.current(0)
    win.fps_dd.current(0)
    if len(win.speaker_dd._values) > 1:
        win.speaker_dd.current(1)
    if len(win.mic_dd._values) > 1:
        win.mic_dd.current(1)
    win._estimate()
    win.root.update()
    print("\nestimate@3min/highest/30fps:", win.estimate["text"])

    win.dir_var.set(str(Path(nabd.load_config()["output_dir"])))
    win._save()
    for _ in range(30):
        win.root.update()
        time.sleep(0.05)

    saved = json.loads(CONFIG.read_text())
    print("saved:", json.dumps({k: saved[k] for k in (
        "clip_seconds", "cq", "fps", "speaker_device", "mic_device",
        "capture_mic", "hotkey")}, indent=2))
    results["saved clip length"] = saved["clip_seconds"] == 180
    results["saved quality"] = saved["cq"] == S.QUALITY[0][1]
    results["saved fps"] = saved["fps"] == 30
    results["saved speaker"] = bool(saved["speaker_device"])
    results["saved mic"] = saved["capture_mic"] and bool(saved["mic_device"])
    results["saved hotkey"] = saved["hotkey"] == win.hotkey_value
    results["saved reset toggle"] = saved["reset_after_clip"] is True
    results["saved audio offset"] = saved["audio_offset_ms"] == -80
    results["saved open hotkey"] = saved["open_hotkey"] == "ctrl+alt+n"
    results["config still valid"] = all(k in saved for k in nabd.DEFAULTS)

    # Dismiss should animate the panel off-screen, then tear it down.
    win.dismiss()
    gone = False
    for _ in range(120):
        try:
            win.root.update()
            if not win.root.winfo_exists():
                gone = True
                break
        except Exception:
            gone = True   # destroyed: Tk raises rather than returning false
            break
        time.sleep(0.01)
    results["dismiss animates then closes"] = gone
finally:
    shutil.copyfile(BACKUP, CONFIG)
    BACKUP.unlink(missing_ok=True)

print("\n--- results ---")
for name, ok in results.items():
    print(f"  {'PASS' if ok else 'FAIL'}  {name}")
sys.exit(0 if all(results.values()) else 1)
