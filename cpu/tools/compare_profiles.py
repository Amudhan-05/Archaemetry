"""Quantify sherd-partiality error: compare the profile extracted from a cropped
fragment against the profile from the complete vessel (ground truth), aligned by
the rim (top). Reports RMS / max radius error in mm over the overlapping band."""
import os
import sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import open3d as o3d
# extract_profile.py lives in the parent cpu/ directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from extract_profile import fit_axis, fit_axis_rim_arc, profile_from_axis

full_path, sherd_path, out_png = sys.argv[1], sys.argv[2], sys.argv[3]
# optional 4th arg: axis method for the sherd (pca | rim_arc), default pca
sherd_method = sys.argv[4] if len(sys.argv) > 4 else "pca"

def prof(path, bands=300, method="pca"):
    m = o3d.io.read_triangle_mesh(path)
    V = np.asarray(m.vertices)
    if method == "rim_arc":
        p0, d, info = fit_axis_rim_arc(V, np.asarray(m.triangles))
        resid = info.get("resid", info.get("arc_resid", float("nan")))
    else:
        p0, d, resid = fit_axis(V)
    hs, r_med, r_max, cover = profile_from_axis(V, p0, d, bands)
    return hs, r_med, cover, resid

hf, rf, cf, resf = prof(full_path, method="pca")
hs, rs, cs, ress = prof(sherd_path, method=sherd_method)

# align by rim: depth measured downward from the top of each profile
df = hf.max() - hf
ds = hs.max() - hs
order_f = np.argsort(df); df, rf = df[order_f], rf[order_f]
order_s = np.argsort(ds); ds, rs, cs = ds[order_s], rs[order_s], cs[order_s]

# compare only where the sherd has good angular coverage (real wall, not edge noise)
good = cs > 0.15
ds_g, rs_g = ds[good], rs[good]
dmax = min(df.max(), ds_g.max())
grid = np.linspace(0, dmax, 200)
rf_i = np.interp(grid, df, rf)
rs_i = np.interp(grid, ds_g, rs_g)
err = rs_i - rf_i
rms = float(np.sqrt(np.mean(err**2)))
mae = float(np.mean(np.abs(err)))
mx = float(np.max(np.abs(err)))

print(f"full  axis residual = {resf:.3f} mm")
print(f"sherd axis residual = {ress:.3f} mm")
print(f"overlap depth-from-rim = 0..{dmax:.1f} mm")
print(f"RADIUS ERROR vs ground truth:  RMS={rms:.3f} mm  MAE={mae:.3f} mm  MAX={mx:.3f} mm")

fig, ax = plt.subplots(1, 2, figsize=(10, 6), gridspec_kw={"width_ratios": [1, 1]})
ax[0].plot(rf, df, "-k", lw=1.5, label="full vessel (truth)")
ax[0].plot(rs_g, ds_g, "-", color="tab:red", lw=1.2, label="from rim sherd")
ax[0].invert_yaxis(); ax[0].set_xlabel("radius (mm)"); ax[0].set_ylabel("depth from rim (mm)")
ax[0].set_title("Profile: sherd vs ground truth"); ax[0].legend(fontsize=8); ax[0].set_aspect("equal")
ax[1].plot(err, grid, "-", color="tab:purple")
ax[1].axvline(0, color="k", lw=0.5); ax[1].invert_yaxis()
ax[1].set_xlabel("radius error (mm)"); ax[1].set_ylabel("depth from rim (mm)")
ax[1].set_title(f"error  RMS={rms:.2f}  MAX={mx:.2f} mm")
fig.tight_layout(); fig.savefig(out_png, dpi=120); plt.close(fig)
print("wrote", out_png)
