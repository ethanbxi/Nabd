# nab'd save banner — 1-for-1 package

Four modules to ship, two dev tools, and the ground truth to check against.

```
nabd_ease.py            the eight easing curves        -> repo root
nabd_banner.py          the 4,120 ms timeline          -> repo root
nabd_mark.py            artwork paths + posing         -> repo root
nabd_mark_frames.py     build-time flipbook            -> repo root

verify_banner.py        the 1-for-1 check              stays in docs/banner/
make_reference_gif.py   regenerates the GIFs           stays in docs/banner/

reference/banner-4120ms.gif    the target, real time
reference/mark-closeup.gif     the mark at 220 px, same timeline
reference/timeline.csv         sample(t) every 4 ms, all 15 channels
reference/nabd-mark-*.svg      the mark at rest, for eyeballing

BANNER.md               the spec
PROMPT.md               what to paste into Claude Code
```

Start with `BANNER.md`. Watch the GIFs before writing anything.

To check a build:

```
python verify_banner.py
```

It must end `OK -- 1 for 1 with the reference.`
