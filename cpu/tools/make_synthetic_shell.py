"""Generate a synthetic hollow vessel-wall shell (inner + outer surfaces) with a
KNOWN wall thickness, to validate thickness extraction against ground truth.

A tapered frustum shell: inner radius Ri(z) = Ri0 + slope*z, outer = inner + T.

Usage:
  python make_synthetic_shell.py OUT.ply [--ri0 18 --ritop 24 --thick 6 --height 60 --arc 360]
"""
import argparse
import numpy as np
import open3d as o3d

ap = argparse.ArgumentParser()
ap.add_argument("out")
ap.add_argument("--ri0", type=float, default=18.0)
ap.add_argument("--ritop", type=float, default=24.0)
ap.add_argument("--thick", type=float, default=6.0)
ap.add_argument("--height", type=float, default=60.0)
ap.add_argument("--arc", type=float, default=360.0)
ap.add_argument("--nz", type=int, default=60)
ap.add_argument("--nt", type=int, default=140)
a = ap.parse_args()

zs = np.linspace(0, a.height, a.nz)
full = abs(a.arc - 360.0) < 1e-6
th = np.linspace(0, np.radians(a.arc), a.nt, endpoint=not full)
nt = len(th)
Ri = a.ri0 + (a.ritop - a.ri0) * (zs / a.height)
Ro = Ri + a.thick

def ring(Rz):
    V = np.zeros((a.nz, nt, 3))
    for i, z in enumerate(zs):
        V[i, :, 0] = Rz[i] * np.cos(th)
        V[i, :, 1] = Rz[i] * np.sin(th)
        V[i, :, 2] = z
    return V

Vin = ring(Ri); Vout = ring(Ro)
verts = np.vstack([Vin.reshape(-1, 3), Vout.reshape(-1, 3)])
off = a.nz * nt

def idx(surface, i, j):
    return surface * off + i * nt + (j % nt)

tris = []
jmax = nt if full else nt - 1
for surf in (0, 1):
    for i in range(a.nz - 1):
        for j in range(jmax):
            a00 = idx(surf, i, j); a01 = idx(surf, i, j + 1)
            a10 = idx(surf, i + 1, j); a11 = idx(surf, i + 1, j + 1)
            tris += [[a00, a10, a11], [a00, a11, a01]]
# top + bottom annular caps (connect inner & outer)
for i in (0, a.nz - 1):
    for j in range(jmax):
        ii = idx(0, i, j); ii1 = idx(0, i, j + 1)
        oo = idx(1, i, j); oo1 = idx(1, i, j + 1)
        tris += [[ii, oo, oo1], [ii, oo1, ii1]]

mesh = o3d.geometry.TriangleMesh()
mesh.vertices = o3d.utility.Vector3dVector(verts)
mesh.triangles = o3d.utility.Vector3iVector(np.array(tris))
mesh.compute_vertex_normals()
o3d.io.write_triangle_mesh(a.out, mesh)
print(f"wrote {a.out}: {len(verts):,} verts, thickness={a.thick} mm, "
      f"Ri {a.ri0}->{a.ritop}, H={a.height}, arc={a.arc} deg")
