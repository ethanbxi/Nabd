"""Where do the two SVG arcs actually start and end?

The mark is published as two path elements. If they share an endpoint it is one
continuous stroke with a single gap, and drawing it as two pieces leaves a seam.
"""
import math

CENTRE = (50.0, 50.0)
POINTS = {
    "main start": (18.05, 38.37),
    "main end": (79.44, 33.0),
    "lit start": (47.04, 16.13),
    "lit end": (18.05, 38.37),
}


def tk_angle(point):
    """Tk/maths convention: degrees counter-clockwise from 3 o'clock, y up."""
    dx = point[0] - CENTRE[0]
    dy = CENTRE[1] - point[1]          # SVG y grows downward
    return math.degrees(math.atan2(dy, dx)) % 360


def clock(angle):
    """Same angle as a clock position, for sanity."""
    hour = ((90 - angle) % 360) / 30
    return f"{int(hour) or 12}:{int((hour % 1) * 60):02d}"


for name, point in POINTS.items():
    a = tk_angle(point)
    r = math.dist(point, CENTRE)
    print(f"  {name:<11} {a:7.2f} deg   {clock(a):>5}   r={r:.2f}")

main_s, main_e = tk_angle(POINTS["main start"]), tk_angle(POINTS["main end"])
lit_s, lit_e = tk_angle(POINTS["lit start"]), tk_angle(POINTS["lit end"])

print(f"\n  main sweep  {main_s:.1f} -> {main_e:.1f} "
      f"= {(main_e - main_s) % 360:.1f} deg ccw")
print(f"  lit sweep   {lit_s:.1f} -> {lit_e:.1f} "
      f"= {(lit_e - lit_s) % 360:.1f} deg ccw")
print(f"  gap         {main_e:.1f} -> {lit_s:.1f} "
      f"= {(lit_s - main_e) % 360:.1f} deg")

joined = abs(lit_e - main_s) < 0.01
print(f"\n  lit ends where main starts: {joined}")
if joined:
    total = ((main_e - lit_s) % 360)
    print(f"  -> one continuous stroke of {total:.1f} deg from {lit_s:.1f} deg,"
          f" with a single {(lit_s - main_e) % 360:.1f} deg gap")
