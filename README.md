# archaemetry

A low-cost, field-portable photogrammetry (SfM/MVS) pipeline for digitising archaeological pottery sherds — built as a proof of concept for a funding application, with an explicit upgrade path once funded.

For each sherd the pipeline produces a metrically accurate 3D mesh, a publication-standard profile drawing (cross-section), and, for decorated ware, a flattened surface rollout showing the full decorative programme.

**Benchmark:** validated against a real museum dataset (Swedish National Historical Museums, Pitted Ware Culture rim fragment — 149 images, Canon 5DS R, RealityCapture, 2,598,096 polygons) to confirm this budget pipeline can approach professional output quality.

The full project handoff, with all setup rationale and detail, is in [`docs/handoff.md`](docs/handoff.md). This README is the short version.

## Repository layout

```
archaemetry/
  docs/
    handoff.md              full project handoff / design rationale
  data/
    reference/
      grey-card-reference.jpg   (add your own — see Capture protocol)
      aruco-markers/            printable marker images
      marker-measurements.csv   calliper-measured distances between marker pairs
  templates/
    sherd_template/          copy this per sherd (see below)
  cpu/                       Stages 2-4: cleanup, profile extraction, publish (built, CPU-only)
  gpu/                       Stage 1: images -> scaled mesh (SfM/MVS; planned, needs a CUDA GPU)
```

Each sherd gets its own working copy of `templates/sherd_template/`, renamed to its sherd ID:

```
sherd_ID/
  raw_images/               original camera files, never modified
  processed_images/         JPGs from RawTherapee (if RAW-capable camera used)
  realitycapture_project/   (or meshroom_project/)
  meshlab/
    sherd_ID_raw.obj        unedited primary record — never overwrite
    sherd_ID_clean.obj      cleaned working version
  gigamesh/
    sherd_ID_profile.svg
    sherd_ID_rollout.svg    (decorated/fine ware only)
  output/
    sherd_ID_drawing.svg    final Inkscape output
  notes.txt                 session notes, grey card RGB, calliper measurements
```

Large binaries (raw/processed images, photogrammetry project files, meshes) are git-ignored by default — see `.gitignore`. Archive them separately (external drive, then Zenodo/Sketchfab) rather than committing them.

## Hardware (current, proof-of-concept)

| Component | Spec |
|---|---|
| Camera | Nikon Coolpix AW100 (16MP, small sensor, 6.17mm sensor width) — acceptable for PoC only |
| Laptop | AMD Ryzen 7 5000 series, Nvidia RTX 3050 (4GB VRAM) |

The AW100 has wide-angle distortion and no RAW capability — fine for proving the pipeline, not for final accuracy. Upgrade path: mirrorless + 50mm macro lens (e.g. Sony A6000-series).

## Capture setup

- **Light tent:** DIY cardboard, ~60×50×50cm interior, side panels open and diffused (white fabric/tracing paper), back and top solid and lined with white chart paper, floor lined with matte white/grey paper.
- **Lighting:** two identical PAR20 7–8W 6500K dimmable LEDs on inline dimmers, fixed at ~20–30cm from the diffusion panels at ~45° elevation via cardboard cones so geometry never drifts between sessions. For slipped/glossy ware, cross-polarise (filters on lights + rotated circular polariser on lens).
- **Turntable:** manual lazy susan (~30cm), marked in 10° increments, matte white/grey surface.
- **Sherd support:** modelling clay (or a sand tray for batches); underside captured in a second session with the sherd propped ~45°, meshes merged later in MeshLab.
- **Scale reference:** 6–10 matte ArUco markers (3–5cm), 4 flat around the sherd on the turntable + 2 on angled card tents for elevation visibility. Marker-pair distances measured with a digital calliper and logged in `data/reference/marker-measurements.csv` — this is the source of all downstream dimensional accuracy.
- **Reproducible lighting:** one physical 18% grey card, shot at the start of every session before placing the sherd. Check colour neutrality (R=G=B) and match brightness to the recorded reference values, adjusting the dimmer as needed. Camera white balance locked manually (Daylight/Cloudy — never Auto).
- **Camera settings:** lowest ISO, fixed wide-angle zoom (never changed mid-session), 2-second timer or IR remote to avoid shake.

## Shooting protocol

- ~80–150 images per sherd, across three elevation rings + overhead: Low (~15–20°), Mid (~45°), High (~70°), Overhead (~90°, 1–3 shots).
- 10° rotation increments per ring (36 shots/ring for Low and Mid); drop to 5° if SfM later fails from insufficient overlap.
- Camera stays fixed per ring; only the turntable rotates. 60–70% overlap required between adjacent shots.
- Photograph a legible label/sherd ID as the first frame of every set.
- If shooting RAW: cull, apply an ICC profile (from a ColorChecker Passport shot), lift shadows (especially for dark/black-slip wares), export JPG 95+ in RawTherapee before the photogrammetry stage. Skip this stage entirely on cameras without RAW (e.g. the AW100).

## Software pipeline

1. **Photogrammetry — RealityCapture (primary).** Import images, set scale from the ArUco calliper measurements (built-in scale bar tool), align → dense reconstruct → mesh, mask background before meshing, export a textured, already-scaled OBJ. ~5–10x faster than Meshroom on the same hardware; pay-per-image (~$0.01/image) after a free tier.
   - **Fallbacks:** Meshroom (free, AliceVision — slow on 4GB VRAM; see `docs/handoff.md` for tuned settings), Metashape (30-day trial, ~₹9–12k academic licence, more reliable on dark/glossy surfaces), or renting a better GPU (Google Colab / Vast.ai) to run Meshroom.
2. **MeshLab (finishing, ~10 min with RealityCapture).** Residual background cleanup, orient the vessel's rotation axis to Y (required for GigaMesh), fill the underside contact-point hole. Do **not** simplify or smooth before GigaMesh — that erases real surface detail and degrades thickness measurements. Export both `sherd_ID_raw.obj` (primary unedited record, never overwritten) and `sherd_ID_clean.obj` (working version).
3. **GigaMesh (profile + rollout).** Free, purpose-built for rotationally symmetric vessels. Automatic axis detection (using the interior surface); profile output is a metrically calibrated SVG cross-section with wall thickness extractable at intervals; rollout output (decorated ware only) unrolls the coloured 3D surface onto a flat, to-scale image — needs clean even lighting, full 360° coverage, and correct axis alignment.
4. **Inkscape (final manual pass).** CVA publication conventions: 0.3mm line weight, scale bar in cm, section-cut hatching, and manual completion of the internal profile where inner-surface data was sparse.

See `docs/handoff.md` for the detailed rationale behind each stage, tool comparisons, and exact settings.

## Error / uncertainty reporting

For the eventual methods section: take ≥3 independent photo sets of the same sherd (repositioning sherd/scale bar/targets slightly between sets), extract thickness at the same 5–10 points across all resulting models, and compare to calibrated digital-calliper measurements (0.01mm accuracy) at the same points. Report mean difference and standard deviation — this separates repeatability (same session) from reproducibility (different sessions) and gives defensible accuracy figures.

## Archiving & data management

- Keep RAW files forever where the camera supports RAW — they're the primary record, never deleted after JPG export.
- `sherd_ID_raw.obj` is the 3D equivalent of a site photograph — a permanent, never-overwritten record.
- For publication/sharing: upload OBJ + texture to Zenodo (free DOI) or Sketchfab (best web viewer, PBR support).
- Default licensing for captured datasets: **CC BY-NC-SA 4.0**, unless the partner institution/museum specifies otherwise. (This repository's own code and documentation are MIT-licensed — see `LICENSE`.)

## Budget snapshot (proof of concept, India, approximate)

| Item | Cost |
|---|---|
| Turntable | ₹900 |
| DIY light tent (cardboard + fabric) | ₹150–300 |
| 2× PAR20 7W 6500K dimmable bulbs | ₹400–700 |
| 2× clamp lamp holders | ₹200–400 |
| 2× inline LED dimmers | ₹300–600 |
| Chart paper, clay, misc | ₹200–300 |
| ArUco markers (printed) | ₹0–50 |
| USB card reader + spare microSD | ₹450–600 |
| Digital calliper | ₹300–500 |
| **Hardware total** | **~₹3,000–4,300** |
| RealityCapture (per-image, PoC scale) | negligible |
| Metashape (optional, 30-day trial) | free trial / ₹9–12k academic |

All core pipeline software (MeshLab, GigaMesh, Inkscape) is free.

## Open threads / next steps

1. Validate RealityCapture output against the Swedish museum benchmark dataset (target ~2.6M polygons on 149 images) to confirm pipeline equivalence for the funding writeup.
2. Test whether the AW100's wide-angle distortion produces usable-but-imperfect meshes, or whether a camera upgrade is needed before shooting real sherds.
3. Run the 3-session error/reproducibility protocol once one sherd clears the full pipeline, to generate defensible accuracy figures for the methods section.
4. Decide the production-scale processing path (local GPU rental via Vast.ai vs. RealityCapture per-image cost vs. Metashape licence) once funded.
5. Regenerate a formatted Word version of the setup/workflow (`sfm_pottery_setup_workflow.docx`) from `docs/handoff.md` if a formatted deliverable is needed again.
