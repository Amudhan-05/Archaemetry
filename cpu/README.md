# archaemetry — scripted pipeline

Automation for the pottery-sherd pipeline described in [`../README.md`](../README.md)
and [`../docs/handoff.md`](../docs/handoff.md). This folder turns the manual,
GUI-driven stages into headless, parameter-driven scripts so a field user can set a
few values and run, and so the pipeline can eventually be packaged to run
machine-independently (notebook / container / hosted).

## Architecture: automate *around* the specialist tool

Not every stage should be automated the same way. The pipeline splits into two lanes:

```
                     ┌─────────────── AUTOMATABLE LANE (this folder) ───────────────┐
  capture ─▶ SfM/MVS ─▶ clean_mesh.py ─▶ extract_profile.py ─▶ (Inkscape CLI, TODO) ─▶ profile
  (rig)     COLMAP/     Stage 2          Stage 3                Stage 4
            Meshroom    remove bg,       axis fit +
                        keep sherd       plane-section
                                    │
                                    └──▶ GigaMesh (manual GUI station) ──▶ Inkscape
                                         Stage 3-specialist:
                                         rollout + faint-decoration (MSII)
                                         for DECORATED ware only
```

- **Plain rotationally-symmetric sherds** → fully automatable lane (the scripts here).
- **Decorated / fine ware (rollouts, faint incised decoration)** → GigaMesh's genuinely
  specialist capabilities; keep it as a manual desktop station. Don't package it —
  package *around* it.

**Two deployment shapes, both valid** (pick per accuracy needs):

1. **Bookend** — automate *up to* GigaMesh (SfM + cleanup + rough orientation) and
   *after* GigaMesh (Inkscape publish), leaving the profile/rollout as manual GigaMesh
   clicks. Lowest risk; keeps GigaMesh's axis/profile quality; a human still touches
   every sherd.
2. **Full-auto** — replace GigaMesh's middle with `extract_profile.py` for plain sherds.
   True walk-away, *if* it hits mm accuracy on fragments (see Validation status — the
   rim-arc axis method is the open item that decides this).

## The parameter surface

The entire field-facing configuration is [`config/sherd.example.yaml`](config/sherd.example.yaml).
Most values have defaults; a field user typically edits only `images_dir`, the `scale`
block, and `ware`. Each run also emits a **confidence report** (JSON) —
`axis_residual`, `angular_coverage`, `kept_fraction` — that is what decides whether a
result is trustworthy or should be flagged for human review / routed to the GigaMesh
station.

## Scripts

| Script | Stage | What it does |
|---|---|---|
| `run.py` | all | **One-command orchestrator.** Reads `sherd.yaml`, drives Stages 2→3→4, aggregates the confidence reports, and prints a **GO / REVIEW** verdict (flags fragments that should go to the manual/GigaMesh route). |
| `clean_mesh.py` | 2 | Keep the largest connected component (drops turntable + noise islands, deterministically), optional capped hole-fill. Replaces the manual MeshLab crop. Emits `*_report.json`. |
| `extract_profile.py` | 3 | Auto-fit the symmetry axis (`pca`, or `rim_arc` for rim sherds with span+planarity gates and graceful fallback), project to cylindrical coords, split each band into inner/outer walls (metric **wall thickness**), and emit a CVA half-section SVG + validation overlay + confidence report. Replaces GigaMesh's profile step for plain ware. |
| `publish_svg.py` | 4 | Add a metric scale bar, caption, and CVA line weight to the profile SVG (portable SVG editing, no GUI dependency). |
| `tools/diagnose_components.py` | — | Inspect the connected-component structure of a raw SfM mesh (sherd vs turntable vs noise). |
| `tools/render_mesh.py` | — | Quick PNG render of a mesh for visual checks. |
| `tools/crop_wedge.py` | — | Crop a complete vessel to an angular wedge to *simulate* a rim/body sherd with ground truth. |
| `tools/compare_profiles.py` | — | Quantify sherd-partiality error: fragment profile vs full-vessel ground truth, RMS/max radius error in mm. |

### Usage

```bash
python -m venv .venv && .venv/Scripts/activate       # Windows; use bin/activate on *nix
pip install -r requirements.txt

# Whole lane in one command (mesh -> cleaned -> profile -> CVA drawing + verdict)
python run.py --config config/sherd.example.yaml --input in_mesh.obj --outdir out/
# -> out/clean.obj, out/profile/profile.svg, out/drawing.svg, out/run_report.json
#    and a printed GO / REVIEW verdict

# Or stage by stage:
python clean_mesh.py       in_mesh.obj out/clean.obj --report out/clean_report.json
python extract_profile.py  out/clean.obj out/profile/ --axis-method rim_arc --bands 300
python publish_svg.py      out/profile/profile.svg out/profile/profile_report.json out/drawing.svg
```

Paths with spaces are fragile through some of the CLI tools (GigaMesh in particular);
work under a space-free root.

## Validation status

Measured on the open CC-BY-SA lekythos mesh (Zenodo 5102757), with a cropped wedge used
as a ground-truthed "rim sherd". Full write-up + figures:
[`../docs/AUTOMATION_VALIDATION.md`](../docs/AUTOMATION_VALIDATION.md).

| Case | Result |
|---|---|
| Stage 2 cleanup | 710 components → 1; turntable + noise removed deterministically ✅ |
| Stage 3, complete vessel | Profile matches silhouette; handle auto-rejected; axis auto-found ✅ |
| Stage 3, 70° rim sherd | Runs + self-flags as partial, but **RMS 4.4 mm / max 10.8 mm** vs truth ❌ |

**Open item (the crux):** on a partial fragment the whole error comes from axis
estimation — a narrow sherd under-constrains the PCA fit, tilting the axis ~7°, and that
tilt accumulates into radius error away from the rim. The fix is a **rim-arc axis
method** (fit the rim's circular edge → axis = rim-plane normal, diameter = arc radius),
mirroring archaeological rim-chart practice and GigaMesh's circle-centre approach. Until
that lands, use the **bookend** deployment (keep GigaMesh for the profile) for fragments.

## Not yet built

- **Stage 1 wrapper** (COLMAP/Meshroom batch + per-image masking + scale from ArUco) —
  the lane currently starts from a mesh.
- **`inner_surface` axis method** for body sherds (hardest case).
- **Hatching** of the section cut in `publish_svg.py` (scale bar + line weight are done).
- **Packaging** (Dockerfile / Colab notebook) for machine-independent execution — goal 5.
- **Validation on real broken rim sherds** (current numbers are from cropped complete
  vessels; open broken-sherd meshes are scarce, so this needs rig captures).
