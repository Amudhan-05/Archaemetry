"""End-to-end accuracy check against an ANALYTIC ground truth (no downloads).

Builds a vessel as a surface of revolution with a known r(h), adds the things a real
SfM mesh has (a non-symmetric handle, a turntable disc, noise islands, vertex noise),
runs the real scripts (run.py -> clean_mesh -> extract_profile -> publish_svg) as
subprocesses, then parses the *published SVG* back to (r, h) and compares it to the
analytic profile. So the number reported is the error of the drawn 2D image itself.

Usage:
  python synthetic_validation.py OUTDIR [--noise-mm 0.05]
"""
import argparse
import json
import os
import re
import subprocess
import sys
import numpy as np
import open3d as o3d

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(HERE)
sys.path.insert(0, SCRIPTS)
sys.path.insert(0, HERE)
from accuracy_oracle import crop_wedge_faces  # noqa: E402

# knots of the true outer profile (h mm, r mm): flared foot, body, shoulder, neck, rim
KH = np.array([0, 4, 20, 50, 75, 85, 100, 110, 114.0])
KR = np.array([14, 17, 22, 21, 16, 7, 6, 9.5, 11.0])


def true_r(h):
    return np.interp(h, KH, KR)


def revolve(n_h=500, n_t=360, rng=None, noise=0.0):
    h = np.linspace(0, 114, n_h)
    t = np.linspace(0, 2 * np.pi, n_t, endpoint=False)
    H, TH = np.meshgrid(h, t, indexing="ij")
    R = true_r(H)
    V = np.stack([R * np.cos(TH), H, R * np.sin(TH)], -1).reshape(-1, 3)
    idx = np.arange(n_h * n_t).reshape(n_h, n_t)
    a, b = idx[:-1], idx[1:]
    a2, b2 = np.roll(a, -1, 1), np.roll(b, -1, 1)
    T = np.concatenate([np.stack([a, b, a2], -1).reshape(-1, 3),
                        np.stack([a2, b, b2], -1).reshape(-1, 3)])
    if noise:
        # radial noise, so it perturbs the surface and not the axis
        n = rng.normal(0, noise, len(V))
        rad = np.stack([np.cos(TH), np.zeros_like(TH), np.sin(TH)], -1).reshape(-1, 3)
        V = V + rad * n[:, None]
    return V, T


def add_handle(V, T, h0=60, h1=95, out=22.0, n=60, m=14):
    """A loop handle (half torus-ish tube) attached on the +x side."""
    s = np.linspace(0, np.pi, n)
    cx = np.array([21 + out * np.sin(s) * 0.6, h0 + (h1 - h0) * (s / np.pi), np.zeros_like(s)]).T
    tube = 3.0
    phi = np.linspace(0, 2 * np.pi, m, endpoint=False)
    pts = []
    for c in cx:
        for p in phi:
            pts.append(c + tube * np.array([np.cos(p), 0, np.sin(p)]))
    P = np.array(pts)
    idx = np.arange(n * m).reshape(n, m)
    a, b = idx[:-1], idx[1:]
    a2, b2 = np.roll(a, -1, 1), np.roll(b, -1, 1)
    Th = np.concatenate([np.stack([a, b, a2], -1).reshape(-1, 3),
                         np.stack([a2, b, b2], -1).reshape(-1, 3)]) + len(V)
    return np.vstack([V, P]), np.vstack([T, Th])


def add_turntable_and_noise(V, T, rng):
    # coarse flat disc (large area, few faces) + tiny floating noise islands
    n = 24
    ang = np.linspace(0, 2 * np.pi, n, endpoint=False)
    disc = np.vstack([[0, -2, 0], np.stack([150 * np.cos(ang), -2 + 0 * ang, 150 * np.sin(ang)], 1)])
    tris = np.array([[0, 1 + i, 1 + (i + 1) % n] for i in range(n)]) + len(V)
    V, T = np.vstack([V, disc]), np.vstack([T, tris])
    for _ in range(40):
        c = rng.uniform(-60, 60, 3)
        tri = c + rng.normal(0, 0.5, (3, 3))
        T = np.vstack([T, [len(V), len(V) + 1, len(V) + 2]])
        V = np.vstack([V, tri])
    return V, T


def save(V, T, path):
    m = o3d.geometry.TriangleMesh(o3d.utility.Vector3dVector(V), o3d.utility.Vector3iVector(T))
    o3d.io.write_triangle_mesh(path, m)


def parse_svg_profile(path):
    """Return (r_mm, h_mm_from_bottom) for the RIGHT polyline of profile.svg / drawing.svg."""
    s = open(path).read()
    mm = re.search(r'width="([\d.]+)mm" height="([\d.]+)mm" viewBox="0 0 ([\d.]+) ([\d.]+)"', s)
    W, Hh = float(mm.group(3)), float(mm.group(4))
    pts = re.findall(r'<polyline[^>]*points="([^"]+)"', s)[0].split()
    xy = np.array([[float(v) for v in p.split(",")] for p in pts])
    pad = 5.0
    cx = W / 2.0               # axis x
    r = xy[:, 0] - cx
    h = (Hh - pad) - xy[:, 1]  # y = total_h - h + pad  ->  h = total_h - (y - pad); total_h = Hh - 2*pad
    h = (Hh - 2 * pad) - (xy[:, 1] - pad)
    return r, h


def score(svg, h_offset_candidates):
    r, h = parse_svg_profile(svg)
    best = None
    for flip in (False, True):
        hh = (h.max() - h) if flip else h
        # profile h is measured from the lowest sampled band; true h0 = unknown offset, solve it
        for off in np.arange(0, 114.01, 0.05):
            e = r - true_r(hh + off)
            rms = float(np.sqrt(np.mean(e ** 2)))
            if best is None or rms < best[0]:
                best = (rms, float(np.abs(e).max()), flip, float(off), float(np.median(e)))
    return best


def run_case(name, V, T, outdir, axis_method):
    d = os.path.join(outdir, name)
    os.makedirs(d, exist_ok=True)
    mesh = os.path.join(d, "in.ply")
    save(V, T, mesh)
    cfg = os.path.join(d, "cfg.yaml")
    open(cfg, "w").write(f"cleanup: {{}}\nprofile:\n  axis_method: {axis_method}\n  bands: 300\npublish: {{line_weight_mm: 0.3}}\n")
    p = subprocess.run([sys.executable, os.path.join(SCRIPTS, "run.py"), "--config", cfg,
                        "--input", mesh, "--outdir", os.path.join(d, "out")],
                       capture_output=True, text=True)
    if p.returncode:
        return dict(case=name, error=(p.stdout + p.stderr)[-600:])
    rep = json.load(open(os.path.join(d, "out", "run_report.json")))
    prof_svg = os.path.join(d, "out", "profile", "profile.svg")
    rms, mx, flip, off, bias = score(prof_svg, None)
    # Stage 4 must not alter geometry: same polylines, and mm-scale preserved (1 user unit = 1 mm)
    a = re.findall(r'points="([^"]+)"', open(prof_svg).read())
    b = re.findall(r'points="([^"]+)"', open(os.path.join(d, "out", "drawing.svg")).read())
    s = open(os.path.join(d, "out", "drawing.svg")).read()
    m = re.search(r'width="([\d.]+)mm" height="([\d.]+)mm" viewBox="[\-\d.]+ [\-\d.]+ ([\d.]+) ([\d.]+)"', s)
    scale_ok = abs(float(m.group(1)) - float(m.group(3))) < 0.15 and abs(float(m.group(2)) - float(m.group(4))) < 0.15
    publish_ok = (a == b[:len(a)]) and scale_ok
    return dict(case=name, verdict=rep["verdict"], radial_rms_mm=round(rms, 3),
                radial_max_mm=round(mx, 3), bias_mm=round(bias, 3),
                publish_geometry_preserved=bool(publish_ok), axis_dir=rep["profile"]["axis_dir"], coverage=rep["profile"]["mean_angular_coverage"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("outdir")
    ap.add_argument("--noise-mm", type=float, default=0.05)
    a = ap.parse_args()
    os.makedirs(a.outdir, exist_ok=True)
    rng = np.random.default_rng(0)
    results = []

    Vc, Tc = revolve(rng=rng, noise=a.noise_mm)
    results.append(run_case("A_clean_vessel", Vc, Tc, a.outdir, "pca"))

    Vh, Th = add_handle(Vc, Tc)
    Vb, Tb = add_turntable_and_noise(Vh, Th, rng)
    results.append(run_case("B_vessel_handle_turntable_noise", Vb, Tb, a.outdir, "pca"))

    # tilt the whole mesh arbitrarily (real captures are not axis-aligned)
    th = np.radians(25)
    Rm = np.array([[1, 0, 0], [0, np.cos(th), -np.sin(th)], [0, np.sin(th), np.cos(th)]])
    results.append(run_case("C_tilted_25deg", Vb @ Rm.T + [10, 5, -7], Tb, a.outdir, "pca"))

    # simulated rim sherds from the clean vessel (known crop frame)
    p_true, d_true = np.zeros(3), np.array([0, 1.0, 0])
    for deg in (360, 180, 120, 90, 60):
        Vs, Ts, _ = crop_wedge_faces(Vc, Tc, p_true, d_true, deg, 0.62, 1.0)
        results.append(run_case(f"D_rimsherd_{deg}deg_rim_arc", Vs, Ts, a.outdir, "rim_arc"))

    for r in results:
        print(json.dumps(r))
    json.dump(results, open(os.path.join(a.outdir, "results.json"), "w"), indent=2)


if __name__ == "__main__":
    main()
