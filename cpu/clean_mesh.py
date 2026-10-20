"""Stage 2 - automated mesh cleanup (replaces the manual MeshLab step).

Replicates, with zero clicks:
  - Remove Isolated pieces  -> keep the largest connected component by face count
  - (background/turntable removal falls out of the same step here, because the
     turntable is a separate, face-sparse component)
  - Close Holes             -> optional, capped so it never fabricates large gaps

Emits a small JSON confidence report so downstream stages / a human reviewer can
tell whether the cleanup is trustworthy (did we drop too much? is it still one
body? is the kept body plausibly compact?).

Usage:
  python clean_mesh.py IN.obj OUT.obj [--min-faces N] [--close-holes-max N] [--report R.json]
"""
import argparse
import json
import sys
import numpy as np
import open3d as o3d


def largest_component(mesh):
    labels, n_tri, _ = mesh.cluster_connected_triangles()
    labels = np.asarray(labels)
    n_tri = np.asarray(n_tri)
    keep = int(n_tri.argmax())
    drop_idx = np.where(labels != keep)[0]
    mesh.remove_triangles_by_index(drop_idx.tolist())
    mesh.remove_unreferenced_vertices()
    return mesh, len(n_tri), int(n_tri[keep]), int(n_tri.sum())


def close_holes(in_path, out_path, max_size):
    """Optional hole fill via pymeshlab, capped by max boundary-edge count."""
    import pymeshlab
    ms = pymeshlab.MeshSet()
    ms.load_new_mesh(in_path)
    try:
        ms.apply_filter("meshing_close_holes", maxholesize=int(max_size),
                        selfintersection=False)
    except Exception as e:
        print(f"  [close_holes] skipped: {e}")
    ms.save_current_mesh(out_path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inp")
    ap.add_argument("out")
    ap.add_argument("--min-faces", type=int, default=None,
                    help="drop components smaller than this (default: keep largest only)")
    ap.add_argument("--close-holes-max", type=int, default=0,
                    help="max hole size (boundary edges) to fill; 0 = never")
    ap.add_argument("--report", default=None)
    args = ap.parse_args()

    mesh = o3d.io.read_triangle_mesh(args.inp)
    v0, f0 = len(mesh.vertices), len(mesh.triangles)
    print(f"IN : {v0:,} verts / {f0:,} faces")

    mesh, n_comp, kept_faces, total_faces = largest_component(mesh)
    ext = mesh.get_axis_aligned_bounding_box().get_extent()
    v1, f1 = len(mesh.vertices), len(mesh.triangles)
    print(f"components before: {n_comp}  ->  kept largest: {kept_faces:,} faces "
          f"({100*kept_faces/total_faces:.1f}%)")
    print(f"OUT: {v1:,} verts / {f1:,} faces   bbox=({ext[0]:.3f},{ext[1]:.3f},{ext[2]:.3f})")

    o3d.io.write_triangle_mesh(args.out, mesh)

    if args.close_holes_max > 0:
        print(f"closing holes (max {args.close_holes_max})...")
        close_holes(args.out, args.out, args.close_holes_max)

    # confidence signals
    compactness = float(min(ext) / max(ext)) if max(ext) > 0 else 0.0
    report = {
        "input": args.inp,
        "output": args.out,
        "components_before": n_comp,
        "faces_before": f0,
        "faces_after": f1,
        "kept_fraction": round(f1 / f0, 4),
        "bbox_extent": [round(float(x), 4) for x in ext],
        "compactness_ratio": round(compactness, 3),
        "single_body": True,
    }
    print("\nreport:", json.dumps(report, indent=2))
    if args.report:
        with open(args.report, "w") as fh:
            json.dump(report, fh, indent=2)


if __name__ == "__main__":
    main()
