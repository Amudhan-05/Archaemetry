"""Stage 4 - publish a profile SVG to a CVA-style drawing.

Post-processes extract_profile's profile.svg: adds a scale bar and a caption,
and normalises line weight. Done as portable SVG-text editing (no Inkscape /
GUI dependency) so the whole lane stays packageable. Inkscape can still be used
for a final manual pass; this covers the deterministic conventions.

Usage:
  python publish_svg.py profile.svg profile_report.json out_drawing.svg
                        [--scale-bar-mm N] [--line-weight-mm W]
"""
import argparse
import json
import re


def nice_bar_mm(height_mm):
    """Pick a round scale-bar length ~1/3 of the drawing height."""
    target = max(height_mm / 3.0, 5.0)
    for v in (5, 10, 20, 30, 50, 100, 150, 200):
        if v >= target:
            return v
    return 200


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("svg")
    ap.add_argument("report")
    ap.add_argument("out")
    ap.add_argument("--scale-bar-mm", type=float, default=None)
    ap.add_argument("--line-weight-mm", type=float, default=0.3)
    args = ap.parse_args()

    svg = open(args.svg).read()
    rep = json.load(open(args.report))
    height_mm = rep.get("height_mm", 100.0)

    # viewBox is in mm units (1 unit == 1 mm), width/height carry a "mm" suffix
    m = re.search(r'viewBox="([\d.\- ]+)"', svg)
    vb = [float(x) for x in m.group(1).split()]
    vx, vy, vw, vh = vb

    # expand the canvas with margins so caption (top) + scale bar (bottom) fit
    mL = mR = 8.0
    mT, mB = 10.0, 16.0
    nvx, nvy = vx - mL, vy - mT
    nvw, nvh = vw + mL + mR, vh + mT + mB
    svg = re.sub(r'width="[\d.]+mm"', f'width="{nvw:.1f}mm"', svg, count=1)
    svg = re.sub(r'height="[\d.]+mm"', f'height="{nvh:.1f}mm"', svg, count=1)
    svg = re.sub(r'viewBox="[\d.\- ]+"',
                 f'viewBox="{nvx:.2f} {nvy:.2f} {nvw:.2f} {nvh:.2f}"', svg, count=1)

    bar = args.scale_bar_mm or nice_bar_mm(height_mm)
    # place the bar in the bottom margin, lower-left
    x0 = vx
    y0 = vy + vh + 0.5 * mB
    lw = args.line_weight_mm
    tick = 2.0
    bar_svg = (
        f'<g stroke="black" fill="black" stroke-width="{lw}" '
        f'font-family="sans-serif" font-size="4">'
        f'<line x1="{x0:.2f}" y1="{y0:.2f}" x2="{x0+bar:.2f}" y2="{y0:.2f}"/>'
        f'<line x1="{x0:.2f}" y1="{y0-tick:.2f}" x2="{x0:.2f}" y2="{y0+tick:.2f}"/>'
        f'<line x1="{x0+bar:.2f}" y1="{y0-tick:.2f}" x2="{x0+bar:.2f}" y2="{y0+tick:.2f}"/>'
        f'<text x="{x0+bar/2:.2f}" y="{y0+7:.2f}" text-anchor="middle" '
        f'stroke="none">{bar/10:g} cm</text>'
        f'</g>'
    )
    cap = (rep.get("input", "").split("/")[-1].split("\\")[-1] or "profile")
    axis_note = rep.get("axis_method", "")
    caption = (
        f'<text x="{nvx+2:.2f}" y="{vy-3:.2f}" '
        f'font-family="sans-serif" font-size="3.5" fill="black">'
        f'{cap}  (h={height_mm:.0f} mm, axis={axis_note})</text>'
    )
    # normalise stroke widths on the profile polylines
    svg = re.sub(r'stroke-width="0\.3"', f'stroke-width="{lw}"', svg)
    out = svg.replace("</svg>", bar_svg + caption + "</svg>")
    with open(args.out, "w") as f:
        f.write(out)
    print(f"wrote {args.out}  (scale bar {bar/10:g} cm, line {lw} mm)")


if __name__ == "__main__":
    main()
