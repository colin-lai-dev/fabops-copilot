"""Clearance colours against the state colours, for normal vision and simulated colour blindness.

The four clearance chips must not be mistaken for a state: amber (retrieved), green / red
(verdict), violet (agent) or the cited ring (ink). For each theme this prints the smallest
colour difference (CIE76 dE in Lab) between any clearance colour and any state colour, and
between neighbouring clearance levels, under normal vision, protanopia and deuteranopia
(Machado et al. 2009, severity 1.0). A dE under 20 is flagged.

    python scripts/palette_check.py
"""

import re
import sys
from itertools import pairwise
from pathlib import Path

css = (Path(__file__).resolve().parents[1] / "src" / "style.css").read_text(encoding="utf-8")
MIN_DE = 20.0
SIM = {
    "normal": None,
    "protanopia": (
        (0.152286, 1.052583, -0.204868),
        (0.114503, 0.786281, 0.099216),
        (-0.003882, -0.048116, 1.051998),
    ),
    "deuteranopia": (
        (0.367322, 0.860646, -0.227968),
        (0.280085, 0.672501, 0.047413),
        (-0.011820, 0.042940, 0.968881),
    ),
}
LEVELS = ["--clr-0-bg", "--clr-1-bg", "--clr-2-bg", "--clr-3-bg"]
STATES = ["--amber", "--good", "--bad", "--violet", "--ink"]


def tokens(block):
    return dict(re.findall(r"(--[a-z0-9-]+):\s*(#[0-9a-fA-F]{6})", block))


light = tokens(css[css.index(":root {") : css.index("}", css.index(":root {"))])
start = css.index(':root[data-theme="dark"] {')
dark = {**light, **tokens(css[start : css.index("}", start)])}


def linear(h):
    c = [int(h[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    return [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c]


def simulate(rgb, m):
    if m is None:
        return rgb
    return [min(1.0, max(0.0, sum(row[i] * rgb[i] for i in range(3)))) for row in m]


def lab(rgb):
    r, g, b = rgb
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883

    def f(t):
        return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116

    return (116 * f(y) - 16, 500 * (f(x) - f(y)), 200 * (f(y) - f(z)))


def de(a, b, m):
    la, lb = lab(simulate(linear(a), m)), lab(simulate(linear(b), m))
    return sum((p - q) ** 2 for p, q in zip(la, lb, strict=True)) ** 0.5


bad = 0
for theme, t in (("light", light), ("dark", dark)):
    for name, m in SIM.items():
        vs_state = min((de(t[c], t[s], m), c, s) for c in LEVELS for s in STATES)
        steps = min((de(t[a], t[b], m), a, b) for a, b in pairwise(LEVELS))
        for label, (d, a, b) in (("clearance vs state", vs_state), ("neighbouring levels", steps)):
            flag = "" if d >= MIN_DE else "  <-- too close"
            bad += d < MIN_DE
            print(f"{theme:5} {name:12} {label:19} min dE {d:5.1f}  ({a} / {b}){flag}")
print("too close:", bad)
sys.exit(1 if bad else 0)
