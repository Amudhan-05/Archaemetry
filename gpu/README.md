# gpu/ — Stage 1: images to scaled mesh (planned)

Structure-from-Motion + Multi-View Stereo turns the photo set into the mesh that
[`../cpu/`](../cpu/) consumes. The dense (MVS) step is the part that needs a CUDA GPU,
which is why this folder is named for the hardware it needs, not the technique.

**Status: not built.** Today Stage 1 is run by hand (RealityCapture or Meshroom) and the
`cpu/` lane starts from the exported mesh.

## Planned contents
- COLMAP + OpenMVS (or `meshroom_batch`) headless runner
- per-image background masking
- ArUco scale step: detect markers, apply the calliper distances from
  `data/reference/marker-measurements.csv`, output a mesh in millimetres
- optional camera pose priors (Orbiter rig extrinsics)
- own `requirements.txt` / Dockerfile, so GPU dependencies never leak into `cpu/`

## Contract with `cpu/`
Output: `mesh.obj` (or `.ply`) **in millimetres**, sherd plus whatever background survived.
`cpu/clean_mesh.py` handles the rest.
