"""Crop a complete vessel mesh to an angular wedge over a height band, to
simulate a rim/body sherd with GROUND TRUTH (we know the true axis + profile).
Uses the true (PCA) axis for cropping; the extractor must then re-discover the
axis from the fragment alone.

Usage:
  python crop_wedge.py IN.ply OUT.ply --deg 70 --hmin-frac 0.6 --hmax-frac 1.0
"""
import argparse
import numpy as np
import open3d as o3d

ap = argparse.ArgumentParser()
ap.add_argument("inp"); ap.add_argument("out")
ap.add_argument("--deg", type=float, default=70.0, help="angular width of wedge")
ap.add_argument("--hmin-frac", type=float, default=0.6)
ap.add_argument("--hmax-frac", type=float, default=1.0)
ap.add_argument("--center-deg", type=float, default=0.0)
a = ap.parse_args()

mesh = o3d.io.read_triangle_mesh(a.inp)
V = np.asarray(mesh.vertices)
T = np.asarray(mesh.triangles)

# true axis via PCA (vertical for a tall vessel)
c = V.mean(0)
evals, evecs = np.linalg.eigh(np.cov((V - c).T))
d = evecs[:, np.argmax(evals)]
a1 = np.array([1.0, 0, 0]) if abs(d[0]) < 0.9 else np.array([0, 1.0, 0])
e1 = np.cross(d, a1); e1 /= np.linalg.norm(e1)
e2 = np.cross(d, e1)

Pw = V - c
h = Pw @ d
u = Pw @ e1; v = Pw @ e2
ang = np.degrees(np.arctan2(v, u))

hlo, hhi = h.min(), h.max()
h0 = hlo + a.hmin_frac * (hhi - hlo)
h1 = hlo + a.hmax_frac * (hhi - hlo)
half = a.deg / 2.0
dang = (ang - a.center_deg + 180) % 360 - 180
vert_keep = (h >= h0) & (h <= h1) & (np.abs(dang) <= half)

# keep triangles whose all 3 vertices are kept
tri_keep = vert_keep[T].all(axis=1)
drop = np.where(~tri_keep)[0]
mesh.remove_triangles_by_index(drop.tolist())
mesh.remove_unreferenced_vertices()
o3d.io.write_triangle_mesh(a.out, mesh)
print(f"wedge: {a.deg} deg, height {a.hmin_frac:.2f}-{a.hmax_frac:.2f} of vessel")
print(f"kept {np.asarray(mesh.vertices).shape[0]:,} verts / "
      f"{np.asarray(mesh.triangles).shape[0]:,} faces")
