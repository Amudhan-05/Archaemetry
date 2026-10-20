"""Diagnose connected-component structure of a raw SfM mesh (Open3D).
Shows the largest components by triangle count with bbox size + center, so we
can see whether the sherd is the largest body or whether the turntable/backdrop
dominates (which would break a naive 'keep largest').
"""
import sys
import numpy as np
import open3d as o3d

path = sys.argv[1]
print(f"Loading {path} ...")
mesh = o3d.io.read_triangle_mesh(path)
V = np.asarray(mesh.vertices)
T = np.asarray(mesh.triangles)
print(f"Total: {len(V):,} verts / {len(T):,} faces")

print("Clustering connected triangles...")
labels, n_tri, areas = mesh.cluster_connected_triangles()
labels = np.asarray(labels)
n_tri = np.asarray(n_tri)
areas = np.asarray(areas)
print(f"Connected components: {len(n_tri)}")

order = np.argsort(n_tri)[::-1]
print(f"\n{'rank':>4} {'faces':>10} {'%mesh':>6}   {'bbox (x,y,z)':>26}   {'center (x,y,z)':>26}")
for rank, ci in enumerate(order[:15]):
    tri_idx = np.where(labels == ci)[0]
    vids = np.unique(T[tri_idx].ravel())
    pts = V[vids]
    ext = pts.max(0) - pts.min(0)
    ctr = (pts.max(0) + pts.min(0)) / 2
    pct = 100 * n_tri[ci] / len(T)
    print(f"{rank:>4} {n_tri[ci]:>10,} {pct:>5.1f}%   "
          f"({ext[0]:.3f},{ext[1]:.3f},{ext[2]:.3f})".rjust(26) + "   " +
          f"({ctr[0]:.3f},{ctr[1]:.3f},{ctr[2]:.3f})".rjust(26))

big = n_tri[order[0]]
print(f"\nLargest component = {big:,} faces ({100*big/len(T):.1f}% of mesh)")
print(f"Components with >=1%% of faces: {(n_tri >= 0.01*len(T)).sum()}")
print(f"Components with <100 faces (noise): {(n_tri < 100).sum()}")
