"""Ground-truth-registered accuracy oracle.

Crops rim wedges of varying angular width from a complete vessel and measures how
accurately the pipeline recovers the profile — WITHOUT any heuristic alignment,
because the true axis is known from the complete vessel and every crop stays in
the same coordinate frame.

Metrics per fragment (same sherd vertices, two axes):
  - axis_angle_err_deg : angle between estimated and true axis direction
  - radial_rms_mm      : RMS over sherd vertices of (dist-to-est-axis
                         - dist-to-true-axis) -> the radial distortion the axis
                         error imprints on the drawn profile
  - rim_diam_err_mm    : estimated vs true vessel diameter at the rim band

Produces a CSV and a plot of error vs arc length for each axis method.

Usage:
  python accuracy_oracle.py FULL_VESSEL.ply OUTDIR [--hmin-frac 0.62 --hmax-frac 1.0]
"""
import argparse
import csv
import os
import sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import open3d as o3d

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from extract_profile import fit_axis, fit_axis_rim_arc, basis_from_dir


def perp_radius(V, p0, d):
    d = d / np.linalg.norm(d)
    W = V - p0
    proj = W @ d
    perp = W - np.outer(proj, d)
    return np.linalg.norm(perp, axis=1)


def angle_deg(d1, d2):
    c = abs(np.dot(d1 / np.linalg.norm(d1), d2 / np.linalg.norm(d2)))
    return float(np.degrees(np.arccos(np.clip(c, 0, 1))))


def crop_wedge_faces(V, T, p_true, d_true, deg, hmin_frac, hmax_frac, center_deg=0.0):
    e1, e2, d = basis_from_dir(d_true)
    W = V - p_true
    h = W @ d
    u = W @ e1
    v = W @ e2
    ang = np.degrees(np.arctan2(v, u))
    hlo, hhi = h.min(), h.max()
    h0 = hlo + hmin_frac * (hhi - hlo)
    h1 = hlo + hmax_frac * (hhi - hlo)
    dang = (ang - center_deg + 180) % 360 - 180
    keepv = (h >= h0) & (h <= h1) & (np.abs(dang) <= deg / 2.0)
    keept = keepv[T].all(axis=1)
    tris = T[keept]
    vids = np.unique(tris.ravel())
    remap = -np.ones(len(V), dtype=np.int64)
    remap[vids] = np.arange(len(vids))
    return V[vids].copy(), remap[tris].copy(), (h0, h1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("full")
    ap.add_argument("outdir")
    ap.add_argument("--hmin-frac", type=float, default=0.62)
    ap.add_argument("--hmax-frac", type=float, default=1.0)
    ap.add_argument("--degrees", default="45,60,90,120,180,240,300,360")
    args = ap.parse_args()
    os.makedirs(args.outdir, exist_ok=True)

    mesh = o3d.io.read_triangle_mesh(args.full)
    V = np.asarray(mesh.vertices)
    T = np.asarray(mesh.triangles)
    p_true, d_true, _ = fit_axis(V)               # ground truth from complete vessel
    print(f"true axis dir = {d_true.round(4)}")

    degs = [float(x) for x in args.degrees.split(",")]
    rows = []
    for deg in degs:
        Vs, Ts, (h0, h1) = crop_wedge_faces(V, T, p_true, d_true, deg,
                                            args.hmin_frac, args.hmax_frac)
        if len(Vs) < 50:
            continue
        r_true_all = perp_radius(Vs, p_true, d_true)
        for method in ("pca", "rim_arc"):
            if method == "rim_arc":
                p_est, d_est, info = fit_axis_rim_arc(Vs, Ts)
            else:
                p_est, d_est, _ = fit_axis(Vs)
            r_est_all = perp_radius(Vs, p_est, d_est)
            radial_rms = float(np.sqrt(np.mean((r_est_all - r_true_all) ** 2)))
            ang_err = angle_deg(d_est, d_true)
            rows.append(dict(deg=deg, method=method, n_verts=len(Vs),
                             axis_angle_err_deg=round(ang_err, 2),
                             radial_rms_mm=round(radial_rms, 3)))
            print(rows[-1])

    csv_path = os.path.join(args.outdir, "accuracy_vs_arc.csv")
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)

    # plot
    fig, ax = plt.subplots(1, 2, figsize=(11, 5))
    for method, col in (("pca", "tab:blue"), ("rim_arc", "tab:red")):
        rr = [r for r in rows if r["method"] == method]
        xs = [r["deg"] for r in rr]
        ax[0].plot(xs, [r["radial_rms_mm"] for r in rr], "-o", color=col, label=method)
        ax[1].plot(xs, [r["axis_angle_err_deg"] for r in rr], "-o", color=col, label=method)
    for a, t, yl in ((ax[0], "Radial RMS error vs rim-arc length", "radial RMS (mm)"),
                     (ax[1], "Axis angle error vs rim-arc length", "axis angle err (deg)")):
        a.set_xlabel("rim arc kept (degrees)"); a.set_ylabel(yl); a.set_title(t)
        a.axhline(1.0, color="gray", ls=":", lw=0.8); a.legend(); a.grid(alpha=0.3)
    fig.tight_layout()
    png = os.path.join(args.outdir, "accuracy_vs_arc.png")
    fig.savefig(png, dpi=120); plt.close(fig)
    print("wrote", csv_path, png)


if __name__ == "__main__":
    main()
