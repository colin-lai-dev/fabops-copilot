"""WCAG contrast of the design-lab tokens (both themes): text pairs need 4.5, graphics 3.0.
python scripts/contrast.py
"""

import re
import sys
from pathlib import Path

css = (Path(__file__).resolve().parents[1] / "src" / "style.css").read_text(encoding="utf-8")


def tokens(block):
    return dict(re.findall(r"(--[a-z0-9-]+):\s*(#[0-9a-fA-F]{6})", block))


light = tokens(css[css.index(":root {") : css.index("}", css.index(":root {"))])
start = css.index(':root[data-theme="dark"] {')
dark = {**light, **tokens(css[start : css.index("}", start)])}


def rgb(h):
    return [int(h[i : i + 2], 16) for i in (1, 3, 5)]


def mix(a, b, p):  # p of a over b, like color-mix(in srgb, a p%, b)
    pairs = zip(rgb(a), rgb(b), strict=True)
    return "#" + "".join(f"{round(x * p + y * (1 - p)):02x}" for x, y in pairs)


def lum(h):
    c = [v / 255 for v in rgb(h)]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def ratio(a, b):
    la, lb = sorted([lum(a), lum(b)], reverse=True)
    return (la + 0.05) / (lb + 0.05)


bad = 0
for name, t in (("light", light), ("dark", dark)):
    t = dict(t)
    t["--slot-on"] = mix(t["--amber-wash"], t["--surface"], 0.55)
    t["--step-ink"] = "#131922"
    inks = ("--ink", "--ink-2", "--ink-3", "--good", "--bad", "--violet", "--amber-ink")
    text = [(f, b) for b in ("--bg", "--surface", "--slot-on") for f in inks]
    text += [
        ("--ink", "--sunken"),
        ("--ink-2", "--sunken"),
        ("--ink-3", "--sunken"),
        ("--amber-ink", "--amber-wash"),
        ("--ink", "--amber-wash"),
        ("--good", "--good-wash"),
        ("--bad", "--bad-wash"),
        ("--violet", "--violet-wash"),
        ("--on-console", "--console"),
        ("--step-ink", "--amber"),
        ("--bg", "--good"),
        ("--bg", "--violet"),
        ("--bg", "--ink"),
    ]
    ui = [
        ("--die", "--wafer"),
        ("--die-sop", "--wafer"),
        ("--amber-ink", "--wafer"),
        ("--ink", "--wafer"),
        ("--violet", "--bg"),
        ("--series-0", "--bg"),
        ("--series-1", "--bg"),
        ("--series-2", "--bg"),
        ("--bad", "--bg"),
    ]
    for group, need in ((text, 4.5), (ui, 3.0)):
        for fg, bg in group:
            r = ratio(t[fg], t[bg])
            if r < need or "-v" in sys.argv:
                bad += r < need
                flag = "  <-- FAIL" if r < need else ""
                print(f"{name:5} {fg:14} on {bg:14} {r:5.2f} (need {need}){flag}")
print("failures:", bad)
sys.exit(1 if bad else 0)
