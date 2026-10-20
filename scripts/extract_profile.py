"""Stage 3 - automated profile extraction from a (near-)rotationally-symmetric
vessel or sherd mesh.  Replaces the GigaMesh GUI step for plain profiles.

Method (same principle GigaMesh uses):
  1. Seed the symmetry axis with PCA (longest extent for a tall vessel).
  2. Refine by the circle-centers method: slice perpendicular to the axis,
     robustly fit a circle to each slice (outlier rejection so a handle / broken
     edge does not bias the centre), then re-fit the axis through the centres.
     Iterate.
  3. Express every vertex in cylindrical coords (h along axis, r from axis).
  4. Per height band, take a robust radius (median over angle => ignores the
     handle, which is a minority of the circumference) -> exterior profile r(h).
  5. Emit an SVG profile (mirrored to show the full outline) + a validation
     overlay PNG + a JSON confidence report.

Usage:
  python extract_profile.py IN.(ply|obj) OUTDIR [--bands N] [--assume-mm-per-unit K]
"""
import argparse
import json
import os
import sys
import numpy as np
import open3d as o3d


# ---------- geometry helpers ----------
def robust_circle_fit(P2, n_iter=3, k=2.5):
    """Algebraic (Kasa) circle fit with iterative outlier rejection.
    P2: (N,2). Returns center(2,), radius, inlier_fraction."""
    idx = np.ones(len(P2), dtype=bool)
    cx = cy = r = 0.0
    for _ in range(n_iter):
        p = P2[idx]
        if len(p) < 8:
            break
        u, v = p[:, 0], p[:, 1]
        A = np.column_stack([u, v, np.ones_like(u)])
        b = -(u**2 + v**2)
        sol, *_ = np.linalg.lstsq(A, b, rcond=None)
        D, E, F = sol
        cx, cy = -D / 2, -E / 2
        r = np.sqrt(max(cx**2 + cy**2 - F, 1e-12))
        d = np.abs(np.sqrt((P2[:, 0] - cx)**2 + (P2[:, 1] - cy)**2) - r)
        mad = np.median(d) + 1e-9
        idx = d < k * mad
    return np.array([cx, cy]), r, float(idx.mean())


def basis_from_dir(d):
    """Orthonormal (e1,e2) spanning the plane perpendicular to unit vector d."""
    d = d / np.linalg.norm(d)
    a = np.array([1.0, 0, 0]) if abs(d[0]) < 0.9 else np.array([0, 1.0, 0])
    e1 = np.cross(d, a); e1 /= np.linalg.norm(e1)
    e2 = np.cross(d, e1)
    return e1, e2, d


def fit_axis(V, n_bands=40, n_refine=4, seed_dir=None):
    """Return (point_on_axis, unit_dir, per-slice residual). Circle-centre
    refinement seeded by PCA major axis, or by `seed_dir` when given (used by
    rim_arc to avoid PCA's seed flipping on wider-than-tall rim bands)."""
    c = V.mean(0)
    if seed_dir is not None:
        d = np.asarray(seed_dir, float)
        d = d / np.linalg.norm(d)
    else:
        cov = np.cov((V - c).T)
        evals, evecs = np.linalg.eigh(cov)
        d = evecs[:, np.argmax(evals)]      # PCA seed = major axis
    p0 = c.copy()
    resid = np.nan
    for _ in range(n_refine):
        e1, e2, d = basis_from_dir(d)
        h = (V - p0) @ d
        lo, hi = np.percentile(h, [5, 95])   # trim caps
        edges = np.linspace(lo, hi, n_bands + 1)
        centers3d, resids = [], []
        for i in range(n_bands):
            m = (h >= edges[i]) & (h < edges[i + 1])
            if m.sum() < 30:
                continue
            Pw = V[m] - p0
            P2 = np.column_stack([Pw @ e1, Pw @ e2])
            ctr2, r, inl = robust_circle_fit(P2)
            hb = h[m].mean()
            c3 = p0 + ctr2[0] * e1 + ctr2[1] * e2 + hb * d
            centers3d.append(c3)
            resids.append(r)
        centers3d = np.array(centers3d)
        if len(centers3d) < 4:
            break
        # refit axis as best line through the circle centres
        cc = centers3d.mean(0)
        _, _, Vt = np.linalg.svd(centers3d - cc)
        d = Vt[0]
        p0 = cc
        # residual = how far the circle centres deviate from the fitted line
        proj = (centers3d - cc) @ d
        line_pts = cc + np.outer(proj, d)
        resid = float(np.sqrt(((centers3d - line_pts)**2).sum(1)).mean())
    return p0, d / np.linalg.norm(d), resid


def find_border_loops(T, n_verts):
    """Return a list of vertex-index arrays, one per connected border loop.
    Border edges are those used by exactly one triangle."""
    from collections import defaultdict
    ecount = defaultdict(int)
    for tri in T:
        for a, b in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
            ecount[(min(a, b), max(a, b))] += 1
    border = [e for e, c in ecount.items() if c == 1]
    if not border:
        return []
    # union-find over border vertices connected by border edges
    parent = {}
    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    def union(a, b):
        parent[find(a)] = find(b)
    for a, b in border:
        union(a, b)
    groups = defaultdict(set)
    for a, b in border:
        groups[find(a)].add(a); groups[find(a)].add(b)
    return [np.array(sorted(g)) for g in groups.values() if len(g) >= 8]


def fit_planar_circle(P3):
    """Fit a plane + circle to 3D points. Return (center3d, normal, radius,
    norm_residual, arc_span_deg, planarity). planarity = out-of-plane extent /
    in-plane extent; small => a thin planar band (a clean rim), large => a
    non-planar band (e.g. a flared mouth) whose normal is unreliable."""
    c = P3.mean(0)
    _, S, Vt = np.linalg.svd(P3 - c)
    normal = Vt[2]                       # smallest-variance dir = plane normal
    e1, e2 = Vt[0], Vt[1]
    planarity = float(S[2] / (S[0] + 1e-12))
    P2 = np.column_stack([(P3 - c) @ e1, (P3 - c) @ e2])
    ctr2, r, inl = robust_circle_fit(P2)
    d = np.abs(np.sqrt((P2[:, 0] - ctr2[0])**2 + (P2[:, 1] - ctr2[1])**2) - r)
    norm_resid = float(np.median(d) / (r + 1e-9))
    ang = np.arctan2(P2[:, 1] - ctr2[1], P2[:, 0] - ctr2[0])
    arc_span = float(np.degrees(ang.max() - ang.min()))
    center3d = c + ctr2[0] * e1 + ctr2[1] * e2
    return center3d, normal, r, norm_resid, arc_span, planarity


def border_vertices(T):
    """Indices of vertices on a border edge (edge used by exactly one triangle)."""
    from collections import defaultdict
    ec = defaultdict(int)
    for tri in T:
        for a, b in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
            ec[(min(a, b), max(a, b))] += 1
    bv = set()
    for (a, b), c in ec.items():
        if c == 1:
            bv.add(a); bv.add(b)
    return np.array(sorted(bv))


def fit_axis_rim_arc(V, T, max_resid=0.05, min_span_deg=70.0, band_frac=0.15):
    """Axis from the horizontal circular arcs on the mesh border (the rim, and
    any clean horizontal break). A rim sherd is topologically a disk, so its
    border is one mixed loop; we isolate horizontal arcs by taking border
    vertices in several height bands (height along a PCA-seeded axis) and
    robustly circle-fitting each.

    The best arc's plane normal SEEDS a circle-centre refinement over the whole
    fragment (fit_axis with seed_dir) -- the rim normal is a robust direction for
    a long arc, and refinement then pins the position. We pick the arc by
    LARGEST span among those with a clean circle fit (a longer arc constrains the
    normal far better than a short one), and gate on a minimum span. Falls back
    to PCA when no clean, long-enough arc exists (a short-arc fragment cannot be
    auto-axised reliably -- it should be flagged for the manual/GigaMesh route).
    Mirrors the archaeological rim-chart method."""
    c = V.mean(0)
    evals, evecs = np.linalg.eigh(np.cov((V - c).T))
    d0 = evecs[:, np.argmax(evals)]

    bidx = border_vertices(T)
    if len(bidx) < 16:
        p0, d, resid = fit_axis(V)
        return p0, d, dict(method="pca_fallback", n_arcs=0, resid=resid)
    B = V[bidx]
    h = (B - c) @ d0
    top = B[h >= np.quantile(h, 1 - band_frac)]
    bot = B[h <= np.quantile(h, band_frac)]

    arcs = []
    for name, band in (("top", top), ("bot", bot)):
        if len(band) < 12:
            continue
        center, normal, r, nres, span, planarity = fit_planar_circle(band)
        # accept only a clean, planar AND long-enough arc: a short or non-planar
        # arc's plane normal is unreliable, so we would rather refuse (fall back)
        # than guess an axis.
        if (r > 0 and nres < max_resid and span >= min_span_deg
                and planarity < 0.12):
            arcs.append(dict(name=name, center=center, normal=normal, r=float(r),
                             nres=float(nres), span=float(span),
                             planarity=float(planarity)))
    if len(arcs) == 0:
        p0, d, resid = fit_axis(V)
        return p0, d, dict(method="pca_fallback", n_arcs=0, resid=resid,
                           note="no clean rim arc >= min_span_deg; flag for manual")

    # Axis = the best-fit (lowest-residual) clean arc's plane normal; position =
    # its centre. Circle-centre refinement was tried and made it worse (it tilts
    # on partial wedges), so we trust the arc normal directly.
    best = min(arcs, key=lambda a: a["nres"])
    d = best["normal"] / np.linalg.norm(best["normal"])
    p0 = best["center"]
    info = dict(method="rim_arc", n_arcs=len(arcs),
                rim_radius=round(best["r"], 3), rim_arc_deg=round(best["span"], 1),
                arc_resid=round(best["nres"], 4))
    return p0, d, info


def split_walls(r, min_sep):
    """Split a band's radii into inner- and outer-wall surfaces via a 1-D Otsu
    threshold. Returns (r_inner, r_outer, is_two_walled). A single-surface band
    (e.g. an exterior-only scan) is unimodal -> inner==outer, thickness 0."""
    if len(r) < 12:
        m = float(np.median(r)); return m, m, False
    lo, hi = np.percentile(r, [2, 98])
    if hi - lo < min_sep:                     # too tight to be two walls
        m = float(np.median(r)); return m, m, False
    bins = np.linspace(lo, hi, 33)
    hist, _ = np.histogram(r, bins=bins)
    centers = 0.5 * (bins[:-1] + bins[1:])
    total = hist.sum()
    w0 = np.cumsum(hist)
    w1 = total - w0
    mu = np.cumsum(hist * centers)
    muT = mu[-1]
    with np.errstate(divide="ignore", invalid="ignore"):
        between = (muT * w0 - mu) ** 2 / (w0 * w1)
    between = np.nan_to_num(between)
    k = int(np.argmax(between[:-1]))
    t = centers[k]
    inner = r[r <= t]
    outer = r[r > t]
    if len(inner) < 3 or len(outer) < 3:
        m = float(np.median(r)); return m, m, False
    ri, ro = float(np.median(inner)), float(np.median(outer))
    if ro - ri < min_sep:
        m = float(np.median(r)); return m, m, False
    return ri, ro, True


def profile_from_axis(V, p0, d, n_bands=300, walls=False, min_sep=0.4):
    e1, e2, d = basis_from_dir(d)
    Pw = V - p0
    h = Pw @ d
    u = Pw @ e1
    v = Pw @ e2
    r = np.sqrt(u**2 + v**2)
    lo, hi = h.min(), h.max()
    edges = np.linspace(lo, hi, n_bands + 1)
    hs, r_med, r_max, cover = [], [], [], []
    r_in, r_out, thick = [], [], []
    for i in range(n_bands):
        m = (h >= edges[i]) & (h < edges[i + 1])
        if m.sum() < 10:
            continue
        ang = np.arctan2(v[m], u[m])
        # angular coverage: fraction of 24 sectors that contain a point
        filled = len(np.unique(np.floor((ang + np.pi) / (2 * np.pi) * 24).astype(int)))
        hs.append(0.5 * (edges[i] + edges[i + 1]))
        r_med.append(np.median(r[m]))       # robust wall radius (ignores handle)
        r_max.append(np.percentile(r[m], 98))
        cover.append(filled / 24.0)
        if walls:
            ri, ro, two = split_walls(r[m], min_sep)
            r_in.append(ri); r_out.append(ro)
            thick.append(ro - ri if two else np.nan)
    if walls:
        return (np.array(hs), np.array(r_med), np.array(r_max), np.array(cover),
                np.array(r_in), np.array(r_out), np.array(thick))
    return (np.array(hs), np.array(r_med), np.array(r_max), np.array(cover))


# ---------- output ----------
def write_svg(hs, r_outer, r_inner, path, mm, stroke=0.3):
    """CVA-style half-section: right side = exterior contour; left side = the cut
    section (exterior + interior wall lines, gap = wall thickness)."""
    h0 = hs.min()
    H = (hs - h0) * mm
    Ro = r_outer * mm
    Ri = r_inner * mm
    Rmax = Ro.max()
    total_h = H.max()
    pad = 5
    W = 2 * Rmax + 2 * pad

    def poly(rs, hh, sign):
        pts = " ".join(f"{Rmax + sign * r + pad:.2f},{total_h - h + pad:.2f}"
                       for r, h in zip(rs, hh))
        return f'<polyline fill="none" stroke="black" stroke-width="{stroke}" points="{pts}"/>'

    parts = [
        poly(Ro, H, +1),                 # right: exterior contour
        poly(Ro, H, -1),                 # left: exterior wall of the section
        poly(Ri, H, -1),                 # left: interior wall of the section
    ]
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W:.1f}mm" '
           f'height="{total_h + 2 * pad:.1f}mm" '
           f'viewBox="0 0 {W:.1f} {total_h + 2 * pad:.1f}">\n'
           + "\n".join(parts) +
           f'\n<line x1="{Rmax + pad:.1f}" y1="{pad}" x2="{Rmax + pad:.1f}" '
           f'y2="{total_h + pad:.1f}" stroke="black" stroke-width="0.1" '
           f'stroke-dasharray="2,2"/>\n</svg>')
    with open(path, "w") as f:
        f.write(svg)


def write_overlay(hs, r_outer, r_inner, thick, cover, path, mm):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    H = (hs - hs.min()) * mm
    fig, ax = plt.subplots(1, 2, figsize=(9, 7), gridspec_kw={"width_ratios": [2, 1]})
    ax[0].plot(r_outer * mm, H, "-k", lw=1.2, label="exterior")
    ax[0].plot(-r_outer * mm, H, "-k", lw=1.2)
    ax[0].plot(-r_inner * mm, H, "-", color="tab:red", lw=1.0, label="interior (section)")
    ax[0].set_aspect("equal"); ax[0].set_title("Extracted profile (half-section)")
    ax[0].legend(fontsize=7)
    ax[0].set_xlabel("radius (mm)"); ax[0].set_ylabel("height (mm)")
    ax[1].plot(thick * mm, H, "-", color="tab:green")
    ax[1].set_title("wall thickness (mm)"); ax[1].set_xlabel("mm")
    tmax = np.nanmax(thick * mm) if np.isfinite(thick).any() else 1
    ax[1].set_xlim(0, max(tmax * 1.3, 1))
    fig.tight_layout(); fig.savefig(path, dpi=110); plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inp")
    ap.add_argument("outdir")
    ap.add_argument("--bands", type=int, default=300)
    ap.add_argument("--axis-method", choices=["pca", "rim_arc"], default="pca",
                    help="pca: near-complete vessels; rim_arc: rim sherds (axis from border arcs)")
    ap.add_argument("--assume-mm-per-unit", type=float, default=1.0,
                    help="scale factor unit->mm (1.0 if mesh already in mm)")
    ap.add_argument("--min-wall-sep-mm", type=float, default=0.4,
                    help="min inner/outer radius gap (in mesh units) to call it a two-walled sherd")
    args = ap.parse_args()
    os.makedirs(args.outdir, exist_ok=True)

    mesh = o3d.io.read_triangle_mesh(args.inp)
    V = np.asarray(mesh.vertices)
    T = np.asarray(mesh.triangles)
    ext = V.max(0) - V.min(0)
    print(f"loaded {len(V):,} verts, bbox={ext.round(3)}")

    axis_info = {"method": "pca"}
    if args.axis_method == "rim_arc":
        p0, d, axis_info = fit_axis_rim_arc(V, T)
        resid = axis_info.get("resid", float("nan"))
        print(f"axis[rim_arc]: {axis_info}")
    else:
        p0, d, resid = fit_axis(V)
    print(f"axis dir={d.round(3)}  residual={resid:.4g} units")

    hs, r_med, r_max, cover, r_in, r_out, thick = profile_from_axis(
        V, p0, d, args.bands, walls=True, min_sep=args.min_wall_sep_mm)
    mm = args.assume_mm_per_unit
    height_mm = (hs.max() - hs.min()) * mm
    maxr_mm = r_med.max() * mm
    th_valid = thick[np.isfinite(thick)] * mm
    two_walled_frac = float(np.isfinite(thick).mean())
    if len(th_valid):
        print(f"wall thickness: mean={th_valid.mean():.2f}mm "
              f"({th_valid.min():.2f}-{th_valid.max():.2f}), "
              f"two-walled bands={two_walled_frac:.0%}")
    else:
        print("wall thickness: none detected (single-surface / exterior-only mesh)")
    print(f"profile: {len(hs)} bands, height={height_mm:.2f}mm, max radius={maxr_mm:.2f}mm")
    print(f"mean angular coverage={cover.mean():.2f}  (1.0=full vessel, <0.5=partial sherd)")

    svg = os.path.join(args.outdir, "profile.svg")
    png = os.path.join(args.outdir, "profile_overlay.png")
    write_svg(hs, r_out, r_in, svg, mm)
    write_overlay(hs, r_out, r_in, thick, cover, png, mm)

    report = {
        "input": args.inp,
        "axis_method": axis_info.get("method", args.axis_method),
        "axis_info": {k: (round(v, 4) if isinstance(v, float) else v)
                      for k, v in axis_info.items() if k != "method"},
        "axis_dir": [round(float(x), 4) for x in d],
        "axis_residual_units": round(float(resid), 5),
        "bbox_units": [round(float(x), 4) for x in ext],
        "n_bands": int(len(hs)),
        "height_mm": round(height_mm, 3),
        "max_radius_mm": round(maxr_mm, 3),
        "mean_angular_coverage": round(float(cover.mean()), 3),
        "min_angular_coverage": round(float(cover.min()), 3),
        "wall_thickness_mm": ({
            "mean": round(float(th_valid.mean()), 3),
            "min": round(float(th_valid.min()), 3),
            "max": round(float(th_valid.max()), 3),
            "two_walled_band_fraction": round(two_walled_frac, 3),
        } if len(th_valid) else None),
    }
    with open(os.path.join(args.outdir, "profile_report.json"), "w") as f:
        json.dump(report, f, indent=2)
    print("\nreport:", json.dumps(report, indent=2))
    print("wrote:", svg, png)


if __name__ == "__main__":
    main()
