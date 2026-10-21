"""Compare axis estimators on wedges cropped from a vessel whose true axis is known.

Methods: pca, rim_arc, normals, normals+refine, pca+refine, rim_arc+refine.
Crops: 'rim' (top of the vessel) and 'body' (mid-wall, no rim at all).
Metrics (same as accuracy_oracle): axis angle error, and radial RMS over the
fragment's vertices of (dist to estimated axis - dist to true axis).

Usage: python axis_methods_eval.py OUTDIR [--noise 0.05,0.25]
"""
import argparse, csv, json, os, sys
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE)); sys.path.insert(0, HERE)
from extract_profile import fit_axis, fit_axis_rim_arc
from axis_fit import fit_axis_normals, refine_consistency, axis_uncertainty
from accuracy_oracle import crop_wedge_faces, perp_radius, angle_deg
from synthetic_validation import revolve

CROPS = {"rim": (0.62, 1.0), "body": (0.25, 0.55)}
_h = np.linspace(0, 80, 41)
SHAPES = {   # name -> (knots, oval)
    "lekythos":   (None, 0.0),
    "lekythos+3%oval": (None, 0.03),
    "jar_straight": ((np.array([0, 100.0]), np.array([30.0, 28.0])), 0.0),
    "cone_bowl":  ((np.array([0, 50.0]), np.array([15.0, 45.0])), 0.0),
    "hemisphere": ((_h, np.sqrt(np.maximum(40.0 ** 2 - (_h - 40.0) ** 2, 1.0))), 0.0),
}


def run_method(name, V, T):
    if name == "pca":
        p, d, _ = fit_axis(V); return p, d, {}
    if name == "rim_arc":
        p, d, i = fit_axis_rim_arc(V, T); return p, d, i
    if name == "normals":
        return fit_axis_normals(V, T)
    base, _ = name.split("+")
    if base == "pca":
        p, d, i = fit_axis(V)[0], fit_axis(V)[1], {}
    elif base == "rim_arc":
        p, d, i = fit_axis_rim_arc(V, T)
    else:
        p, d, i = fit_axis_normals(V, T)
    p, d, j = refine_consistency(V, p, d)
    i = dict(i); i.update(j); i["pred_sigma_mm"] = round(axis_uncertainty(V, p, d), 3); return p, d, i


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("outdir")
    ap.add_argument("--noise", default="0.05,0.25")
    ap.add_argument("--shapes", default="")
    ap.add_argument("--degrees", default="45,60,90,120,180")
    ap.add_argument("--methods", default="pca,rim_arc,normals,normals+refine,pca+refine,rim_arc+refine")
    a = ap.parse_args()
    os.makedirs(a.outdir, exist_ok=True)
    rng = np.random.default_rng(1)
    rows = []
    p_true, d_true = np.zeros(3), np.array([0, 1.0, 0])
    for shape, (knots, oval) in SHAPES.items():
      if a.shapes and shape not in a.shapes.split(","):
        continue
      for noise in [float(x) for x in a.noise.split(",")]:
        V, T = revolve(rng=rng, noise=noise, knots=knots, oval=oval)
        ymax = V[:, 1].max()
        for crop, (h0, h1) in CROPS.items():
            for deg in [float(x) for x in a.degrees.split(",")]:
                Vs, Ts, _ = crop_wedge_faces(V, T, p_true, d_true, deg, h0, h1)
                if len(Vs) < 200:
                    continue
                rt = perp_radius(Vs, p_true, d_true)
                for m in a.methods.split(","):
                    try:
                        p, d, info = run_method(m, Vs, Ts)
                        rms = float(np.sqrt(np.mean((perp_radius(Vs, p, d) - rt) ** 2)))
                        row = dict(shape=shape, noise=noise, crop=crop, deg=deg, method=m,
                                   axis_err_deg=round(angle_deg(d, d_true), 2), radial_rms_mm=round(rms, 3),
                                   info=json.dumps({k: v for k, v in info.items() if k in
                                                    ("pred_sigma_mm", "spread_after_mm")}))
                    except Exception as e:
                        row = dict(shape=shape, noise=noise, crop=crop, deg=deg, method=m, axis_err_deg=-1, radial_rms_mm=-1, info=str(e)[:80])
                    rows.append(row)
    with open(os.path.join(a.outdir, "axis_methods.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    meths = a.methods.split(",")
    for shape in dict.fromkeys(r["shape"] for r in rows):
        for noise in sorted({r["noise"] for r in rows}):
            for crop in CROPS:
                print(f"\n[{shape}] noise={noise} mm crop={crop}  radial RMS mm (axis err deg) [pred sigma]")
                print("arc   " + "".join(f"{m:>24}" for m in meths))
                for deg in sorted({r["deg"] for r in rows}):
                    cells = []
                    for m in meths:
                        r = next((x for x in rows if x["shape"] == shape and x["noise"] == noise and x["crop"] == crop and x["deg"] == deg and x["method"] == m), None)
                        if not r:
                            cells.append("-"); continue
                        ps = json.loads(r["info"]).get("pred_sigma_mm") if r["info"].startswith("{") else None
                        cells.append(f"{r['radial_rms_mm']:.2f} ({r['axis_err_deg']:.1f})" + (f" [{ps}]" if ps is not None else ""))
                    print(f"{deg:<6.0f}" + "".join(f"{c:>24}" for c in cells))


if __name__ == "__main__":
    main()
