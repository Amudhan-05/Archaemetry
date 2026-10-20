# Project Handoff v2 — Automation Architecture & State

**Purpose of this document.** This is a self-contained migration handoff so the project can
be continued in a fresh conversation (or by another person) with zero prior context. It
records: the goal, how the idea evolved, every tool choice and its rationale, the
architecture we converged on, exactly what was built, the sample data, the outputs, the
empirical findings (with numbers), what is pending, and how to run everything.

It **extends** the original [`handoff.md`](handoff.md) (capture rig, lighting, shooting
protocol, budget — still valid) and pairs with [`AUTOMATION_VALIDATION.md`](AUTOMATION_VALIDATION.md)
(the empirical results with figures). Read those two alongside this.

- **Repo:** https://github.com/Amudhan-05/archaemetry
- **Working branch:** `automation-pipeline` (latest commit `f10a772`; 6 commits ahead of `main`)
- **Local clone used during the work:** `C:\pottery-sfm\archaemetry`
- **Python venv:** `C:\pottery-sfm\pipeline\.venv` (Python 3.10, Windows)
- **Date of this handoff:** 2026-09 (dates in the original handoff are relative; this one is absolute)

---

## 1. The goal (unchanged)

Build a low-cost, field-portable photogrammetry (SfM/MVS) pipeline to digitise
archaeological pottery sherds, as proof of concept for a funding application. Per sherd the
deliverables are: a metrically accurate 3D mesh, a **publication-standard profile drawing
(cross-section with wall thickness)**, and — for decorated ware — a flattened surface
**rollout**. Validated cheaply first (consumer camera, DIY light tent, free/low-cost
software), with an explicit intent to scale hardware/software once funded.

The five things the user actually asked for, which frame all the work below:

1. Set up and test the whole toolchain (via the individual app UIs first).
2. Explore parameter configurations per tool and build a mapping between parameters and
   input→output behaviour, to find optimal profile-drawing settings.
3. Vet the toolchain: which tools can be substituted, given the chain came from a paper
   using GigaMesh.
4. Automate profile-drawing creation so a field user sets a few parameters and runs it.
5. Once tools/configs are frozen, package it to run independent of machine-specific compute
   (notebooks / hosted AMIs / a unified app).

---

## 2. How the idea evolved (the narrative — read this first)

The project **started as a linear chain of GUI apps** and evolved into a **two-lane
architecture that automates around a specialist tool**. The turning points:

1. **Starting point (original handoff).** A linear GUI pipeline:
   `RealityCapture → MeshLab → GigaMesh → Inkscape`. This chain came from the literature —
   GigaMesh (Hubert Mara et al.) for pottery profiles/rollouts, and the
   Stamatopoulos & Anagnostopoulos implementation. Every stage was a manual desktop app.

2. **Reframe 1 — the specialist-vs-automatable tension is *localised*.** We mapped each
   stage's headless/CLI capability and found the tension isn't spread across the chain — it
   sits almost entirely in **Stage 3 (GigaMesh)**. Stages 1, 2, 4 all have fully scriptable
   equivalents with no quality loss. GigaMesh's *profile SVG and rollout are GUI-only* (its
   CLI tools cover clean/info/feature-vectors/border only), so it is both the hardest tool
   to replace **and** the one step that resists headless automation.

3. **Reframe 2 — split GigaMesh's value.** GigaMesh's four capabilities are not equally
   special. Rollout (surface unwrapping) and MSII (faint-decoration enhancement) are
   genuinely hard to replicate — but they are only needed for **decorated fine ware**. The
   routine **profile drawing** needs only axis detection + plane-section, which are fully
   scriptable. → **Two lanes:** an automatable "profile lane" (open source, headless) and a
   specialist "GigaMesh station" (manual, GUI) for decorated ware. Package *around*
   GigaMesh, not through it. (We labelled this "architecture E".)

4. **Reframe 3 — accuracy is upstream and orthogonal to the automation choice.** The mm
   accuracy budget lives in capture → scale calibration → reconstruction, not in the
   profile tool. Whether Stage 3 is GigaMesh's GUI or a script, both intersect the *same*
   scaled mesh with a plane. So automating Stage 3 costs **draughting-convention polish and
   edge-case robustness**, *not millimetres*. This dissolved the false "automation vs
   accuracy" tradeoff.

5. **Reframe 4 — for fragments, axis estimation is the whole game.** We built the scripted
   lane and measured it. On a complete vessel it's silhouette-accurate. On a narrow rim
   sherd it fails the mm target — and the entire error traces to **estimating the symmetry
   axis from partial data**. That is precisely GigaMesh's specialist strength (axis from
   interior circle centres). We quantified a **~90° clean-rim-arc threshold**: above it,
   sub-degree axis recovery; below it, unreliable → route to the manual station.

6. **Reframe 5 — a profile is a *section*, thickness needs two walls.** The first drawings
   showed a single line. Root cause: the museum test mesh is an **exterior-only closed
   surface** (no interior wall in the data) *and* the extractor only drew one line. Fixed by
   splitting each band's radii into inner/outer walls; real broken sherds capture both
   surfaces, so thickness then appears (validated exact on a synthetic shell).

7. **Packaging insight (goal 5).** The whole profile lane is **CPU-only and open source**,
   so it packages trivially (notebook/Docker/AMI). Only Stage 1 (SfM) needs a GPU, which is
   the canonical cloud-notebook workload. Moving to cloud **does not reduce precision**
   (same math; precision is set by physics + settings, not the host) and can *raise* it by
   enabling higher-quality settings than the local 4 GB GPU.

**Net:** the "product" is the automatable open profile lane (with a confidence gate that
flags hard fragments); RealityCapture and GigaMesh become optional manual reference
stations, not dependencies.

---

## 3. The architecture we converged on

```
                     ┌──────────── AUTOMATABLE LANE (built, CPU-only) ────────────┐
  capture ─▶ SfM/MVS ─▶ clean_mesh ─▶ extract_profile ──────────▶ publish_svg ─▶ drawing.svg
  (rig)     COLMAP/     Stage 2       Stage 3                     Stage 4          + GO/REVIEW
            Meshroom    remove bg,    axis fit (pca|rim_arc),                       verdict
            (GPU)       keep sherd    inner/outer walls,
                                      thickness
                                    │
                                    └─▶ GigaMesh station (manual GUI, decorated ware only):
                                        rollout + MSII faint-decoration reading
```

**Two deployment shapes (both valid, choose per accuracy need):**

- **Bookend** — automate *up to* GigaMesh (SfM + cleanup + rough orientation) and *after*
  it (Inkscape/`publish_svg`), leaving the profile/rollout as manual GigaMesh clicks.
  Lowest risk; keeps GigaMesh's axis/profile quality; a human touches every sherd. Use for
  small-arc rim sherds and body sherds.
- **Full-auto** — replace GigaMesh's middle with `extract_profile` for plain ware. True
  walk-away, valid for complete/large vessels and rim sherds with ≳90° of clean rim arc.

**Why automate *around* GigaMesh rather than replace it:** its irreplaceable capabilities
(rollout, MSII) are decorated-ware only; forcing them into the automated path would break
packageability (Windows/GUI/licence) for a minority of cases. Keep them as a manual station.

---

## 4. Tool-by-tool decisions, rationale, and substitutes

For each stage: what it does, why chosen, whether it is GUI/CLI, GPU/CPU, packageable, and
what it can be substituted with.

### Stage 1 — Photogrammetry (images → mesh) — GPU-heavy
- **RealityCapture** *(reference / not packageable).* Chosen originally for speed (5–10×
  Meshroom on the same hardware) and because it sets scale + masks background internally.
  Windows-only GUI (has a CLI, still Windows). Pay-per-image after a free tier.
  **Cannot go to a Linux notebook** — it stays a local station. Present on the user's
  machine (a `test reality scan.rsproj` exists; model locked in `.dat`, needs OBJ export).
- **Meshroom (AliceVision)** *(open substitute, used for the sample).* Free, `meshroom_batch`
  CLI, headless Linux+CUDA → notebook-friendly. Slower on 4 GB VRAM. The sample sherd mesh
  came from a Meshroom run (a `MeshroomCache/` with a 68 MB `mesh.obj` exists on the user's
  Desktop).
- **COLMAP + OpenMVS** *(recommended open lane for packaging).* Fully open CLI, headless
  CUDA, and — crucially — **accepts camera pose priors**, which suits the Orbiter rig
  (below) and helps on featureless/glossy sherds. Best choice for a cloud/notebook lane.
- **Metashape** *(optional).* Python API, headless-capable, licensed; more robust on
  dark/glossy surfaces. 30-day trial / academic licence.
- **Scale:** RealityCapture sets metric scale from ArUco internally. The open lane needs an
  explicit **ArUco-scale step** (detect markers in images, apply calliper distances). Not
  yet built — this is where metric accuracy is anchored.

### Stage 2 — Mesh cleanup — CPU
- **MeshLab (GUI) → replaced by a script.** MeshLab 2025.07 is installed on the user's
  machine, but every operation it did (remove isolated pieces, crop background, close holes,
  orient, export) is available headless via **pymeshlab** / **Open3D**. So the manual
  MeshLab stage collapses into `clean_mesh.py`. We used **Open3D** for the connected-
  component logic (faster/robust) and pymeshlab optionally for hole-fill.
- **Key deterministic trick:** keep the **largest connected component by *face count***. A
  flat turntable is spatially large but *face-sparse*; the photographed sherd is spatially
  small but *face-dense* — so "largest by face count" cleanly separates sherd from
  turntable + noise. (Production guard: pair with a compactness/size sanity check.)

### Stage 3 — Profile + thickness (the crux) — CPU
- **GigaMesh (GUI) → substituted by `extract_profile.py` for plain ware; kept as station
  for decorated ware.** GigaMesh (portable build at
  `C:\Users\Santosh R\Downloads\gigamesh-240221-windows\bin` on the user's machine) does
  axis detection + profile SVG + rollout. Its **profile SVG and rollout are GUI-only**
  (confirmed: CLI tools are `gigamesh-borders/clean/featurevectors/info/sphere-profiles/
  gnsphere/togltf/tolegacy` — no profile/rollout CLI). Its irreplaceable value is
  **rollout** and **MSII** (faint decoration), both decorated-ware only.
- **Our substitute** does: axis fit (`pca` for complete/large; `rim_arc` for rim sherds),
  cylindrical projection, **inner/outer wall split → wall thickness**, metric SVG
  half-section. It is CPU-only and fully deterministic.

### Stage 4 — Publish — CPU
- **Inkscape (GUI) → `publish_svg.py` (portable SVG editing).** Inkscape 1.4.4 is installed
  (`C:\Program Files\Inkscape\bin\inkscape.exe`) and is used only to *render* SVG→PNG for
  previews. The deterministic conventions (metric scale bar, CVA 0.3 mm line weight,
  caption, centre axis) are done by editing SVG text directly — **no GUI dependency**, so
  the lane stays packageable. Hatching of the section cut is not yet implemented (Inkscape
  or SVG-pattern can do it later).

### Other tools present
- **Blender 3.6.1** (installed). A 2025 paper does pottery virtual-sections in Blender
  Geometry Nodes + Python — a credible headless substitute for Stage 3 we noted but did not
  pursue (our Open3D/numpy approach was lighter). Keep in mind as an alternative.
- **Open3D 0.19, numpy 2.2.6, matplotlib 3.10.9, PyYAML 6.0.2** — the actual runtime deps
  (pymeshlab optional, only for hole-fill). See `scripts/requirements.txt`.

---

## 5. Capture side — the Orbiter rig assessment

The user is evaluating **Orbiter** (RawMechatronicsOrg/Orbiter), a bench-top 2-axis
(azimuth + elevation) photogrammetry rig, ESP32-controlled with encoder feedback, that
outputs photo sets **with camera extrinsics as COLMAP SfM priors**.

- **Verdict: useful, not redundant.** It mechanises the exact AZ/EL ringed protocol in the
  original handoff (Low/Mid/High elevation rings × 10° azimuth). The **pose priors** are a
  real quality lever (faster, more robust SfM on featureless/glossy sherds) and bias Stage 1
  toward **COLMAP** (which ingests priors) — which is also the most packageable choice.
- **Two caveats.** (1) It does **not** solve underside/contact-surface occlusion (the sherd
  occludes its own base; still needs a flip-and-merge second session). (2) Its motion
  precision (0.0075°/microstep) far exceeds what SfM needs (10° steps) — surplus, harmless.
- **+90° overhead** is fine for flat sherds; for tall vessels the arm radius vs object
  height limits true nadir — a real constraint for tall pots, a non-issue for sherds.

Scale anchor throughout: **ArUco markers + calliper distances** (logged in
`data/reference/marker-measurements.csv`).

---

## 6. What was actually built (the repo)

All under `scripts/` on branch `automation-pipeline`. The whole lane is CPU-only, headless.

| Path | Stage | What it does |
|---|---|---|
| `scripts/run.py` | all | One-command orchestrator. Reads `sherd.yaml`, drives 2→3→4, aggregates confidence reports, prints **GO / REVIEW** verdict (flags fragments for the manual/GigaMesh route). |
| `scripts/clean_mesh.py` | 2 | Keep-largest-component cleanup (drops turntable + noise deterministically), optional capped hole-fill, JSON confidence report. |
| `scripts/extract_profile.py` | 3 | Axis fit (`--axis-method pca\|rim_arc`), cylindrical projection, **inner/outer wall split → thickness**, CVA half-section SVG + overlay + report. |
| `scripts/publish_svg.py` | 4 | Adds scale bar, caption, CVA line weight (portable SVG editing, no GUI). |
| `scripts/config/sherd.example.yaml` | — | The entire field-facing parameter surface (below). |
| `scripts/requirements.txt` | — | Pinned deps (numpy, open3d, matplotlib, pyyaml; pymeshlab optional). |
| `scripts/tools/diagnose_components.py` | — | Inspect connected-component structure of a raw mesh. |
| `scripts/tools/render_mesh.py` | — | Quick mesh→PNG for visual checks. |
| `scripts/tools/crop_wedge.py` | — | Crop a complete vessel to an angular wedge to simulate a sherd with ground truth. |
| `scripts/tools/compare_profiles.py` | — | Fragment vs full-vessel profile error (early harness; superseded by the oracle). |
| `scripts/tools/accuracy_oracle.py` | — | Ground-truth-registered accuracy vs rim-arc length (the trustworthy oracle). |
| `scripts/tools/make_synthetic_shell.py` | — | Generate a hollow shell with KNOWN wall thickness for thickness validation. |

**The parameter surface** (`sherd.example.yaml`) — a field user typically edits only
`images_dir`, the `scale` block, and `ware`:
```yaml
capture:  {images_dir, masking: auto, pose_priors: <Orbiter extrinsics or null>}
scale:    {marker_pair, distance_mm}          # metric anchor, REQUIRED
cleanup:  {keep_largest_only, min_faces, close_holes_max_mm}
profile:  {axis: auto, axis_method: pca|rim_arc, bands, thickness_interval_mm}
publish:  {line_weight_mm: 0.3, scale_bar, hatching, template: cva}
ware:     plain | decorated                   # decorated -> GigaMesh station
```

**Confidence report + GO/REVIEW gate.** Every run emits per-stage JSON
(`kept_fraction`, `compactness`, `axis_residual`, `mean_angular_coverage`,
`wall_thickness_mm`) and a verdict: a fragment whose axis could not be fixed from a clean
rim arc, or with very low angular coverage, is flagged **REVIEW → route to
GigaMesh/manual**, never silently drawn. This is the mechanism that makes "field user sets
a few params and walks away" safe.

---

## 7. Sample data used

1. **Meshroom test sherd** (the user's own). `MeshroomCache/.../mesh.obj`, ~753k verts /
   1.5M faces, **710 connected components**. It is a **thin body/wall sherd** (no rim,
   thickness/length ≈ 0.19). Used to: prove Stage-2 cleanup (710→1, kept 88.2%, turntable +
   708 noise islands removed) and to test that `rim_arc` **correctly falls back** on a real
   irregular-edge fragment (it did: `n_arcs: 0`). *Not* usable for meaningful profile
   quality (no rim, weak axis signal).
2. **Attic white-ground lekythos** — **Zenodo record 5102757**
   (`PT-PC-Athens-1814_3D01-holesFilled.ply`), *3D Archaeological Greek Pottery* dataset,
   **CC-BY-SA-4.0**. ~122k verts, **metric** (bbox 50×114×50 mm), one handle,
   **exterior-only closed surface**. Used as ground truth for Stage-3 validation and, via
   `crop_wedge.py`, for the sherd-partiality and accuracy-vs-arc experiments. (Open *broken
   rim-sherd* meshes are scarce — Zenodo pottery is complete vessels — so cropped wedges
   stand in for fragments, with known ground truth.)
3. **Synthetic hollow shell** — `make_synthetic_shell.py`, tapered frustum wall,
   inner radius 18→24 mm, **known 6 mm thickness**, height 60 mm. Used to validate thickness
   extraction (recovered 6.00 mm exactly).

---

## 8. Outputs generated (where to look)

Committed under `docs/validation/` (small PNGs/CSV kept in git; large meshes are gitignored):
- `lekythos_profile_overlay.png` — Stage-3 profile matches the vessel silhouette; handle
  auto-rejected.
- `rim_sherd_vs_truth.png` — sherd-partiality error (RMS 4.4 mm) from the early harness.
- `accuracy_vs_arc.png` + `.csv` — the ground-truth oracle: rim-arc length vs axis/radial error.
- `thickness_synthetic.png` — the two-walled half-section + flat 6 mm thickness curve.
- `example_drawing.svg` / `.png` — a finished CVA-style drawing from `run.py`.

Per-run outputs (not committed): `out/clean.obj`, `out/profile/profile.svg`,
`out/profile/profile_overlay.png`, `out/drawing.svg`, `out/run_report.json`.

---

## 9. Key empirical findings (with numbers)

1. **Cleanup is fully automatable.** 710 components → 1, deterministic, zero clicks
   (`kept_fraction 0.88`, `single_body true`).
2. **Stage 3 is silhouette-accurate on a complete vessel.** Axis auto-found
   `[0.03, 0.999, 0.01]`; profile traces foot/body/shoulder/neck/rim; handle rejected by the
   median-over-angle radius.
3. **Small fragment failure is axis-driven.** A 70° rim wedge gave **RMS 4.4 mm / max
   10.8 mm** vs truth; the whole error is the axis tilting ~7° when re-fit from a narrow arc.
4. **The rim-arc threshold.** `rim_arc` (best-arc plane normal, with span+planarity gates)
   reaches **sub-degree axis recovery from ~90° of clean rim arc onward**; PCA never beats
   ~5° on rim bands (its longest-extent seed flips on wider-than-tall bands). Below ~70°
   arc, `rim_arc` **refuses and falls back** (flag for manual) rather than guess.
5. **Thickness is exact given two-walled data.** Synthetic 6 mm wall → recovered
   **6.00 mm, 100 % of bands**. Museum meshes are exterior-only → correctly report no
   thickness (a single line is correct for that data, not a bug).
6. **The lane is CPU-only** (numpy/Open3D/SVG) → runs anywhere; only SfM needs GPU.

**Accuracy / error budget (where the millimetres come from — host-independent):**
camera optics/distortion (largest current risk on the AW100) > ArUco↔calliper scale
(~0.1–0.3 mm) > SfM/MVS noise (~0.05–0.2 mm) > mesh sampling/section (<0.1 mm) > axis fit
(degrees→mm at the rim) > draughting interpretation (human ±0.2–0.5 mm). A well-calibrated
pipeline lands ~0.1–0.5 mm — inside human inter-operator variance. **None of these is the
GigaMesh-vs-script choice**, and none is the cloud-vs-local choice.

---

## 10. Packaging (goal 5) — findings, not yet built

- **SfM → notebook/cloud: yes.** COLMAP+OpenMVS or `meshroom_batch` run headless on
  Colab/Vast/GPU-AMI. RealityCapture cannot (Windows). Entire pipeline can live in one Colab
  notebook: GPU cells for SfM, CPU cells for our lane, download the drawing.
- **Precision on cloud: unchanged.** Same software = same math; IEEE float is identical
  across x86; export precision (float32 ≈ 1e-4 mm on a 100 mm sherd) is far below method
  error. Cloud GPUs can *raise* the ceiling (higher-quality settings than the 4 GB RTX
  3050). Caveat: GPU dense-reconstruction kernels are slightly non-deterministic run-to-run
  (local *or* cloud) — that's *reproducibility*, not *precision*, and is captured by the
  3-session error protocol. Mitigation: **pin tool versions** (Dockerfile / pinned notebook).

---

## 11. What is pending (the backlog)

- **Stage 1 SfM wrapper** — COLMAP/Meshroom batch runner + per-image masking (SAM/rembg) +
  the **ArUco-scale step** (detect markers, apply calliper distances). The lane currently
  starts from a mesh.
- **Packaging** — a Colab notebook (images→drawing end to end) and/or a Dockerfile for an
  AMI. This is the immediate next thread (goal 5).
- **Validation on a real broken rim sherd** — current numbers are from cropped complete
  vessels (cleaner edges than real fractures). Needs rig captures (open broken-sherd meshes
  are scarce).
- **`inner_surface` axis method** for body sherds (the hardest case; currently they route to
  manual).
- **Hatching** of the section cut in `publish_svg.py` (scale bar + line weight done).
- **Decorated ware** — rollout + MSII stay in the GigaMesh manual station (deliberately not
  automated).
- **Original open threads** from `handoff.md` still stand: validate against the Swedish
  museum benchmark; test AW100 distortion vs a camera upgrade; run the 3-session
  reproducibility protocol; decide production processing path once funded.

---

## 12. How to run (environment)

```bash
# from the repo's scripts/ dir
python -m venv .venv && .venv/Scripts/activate      # Windows; bin/activate on *nix
pip install -r requirements.txt

# whole lane, one command (starts from a mesh):
python run.py --config config/sherd.example.yaml --input mesh.obj --outdir out/
#  -> out/clean.obj, out/profile/profile.svg, out/drawing.svg, out/run_report.json + GO/REVIEW

# validation reproductions:
python tools/make_synthetic_shell.py shell.ply --thick 6
python extract_profile.py shell.ply out/ --axis-method pca        # thickness -> 6.00 mm
python tools/accuracy_oracle.py lekythos.ply oracle/              # rim-arc vs accuracy curve
```

**Machine notes (user's setup):** Windows 11, AMD Ryzen 7, **RTX 3050 4 GB**. Installed:
MeshLab 2025.07, Blender 3.6.1, Inkscape 1.4.4, GigaMesh portable (in `Downloads`),
RealityCapture (Epic). **Work under a space-free path** — some CLI tools (GigaMesh
especially) are fragile with spaces in paths; that's why the working copy lives in
`C:\pottery-sfm\` rather than the Desktop project folder.

**Git:** commits authored `sansou465 <sansou465@gmail.com>` (a local identity set on the
clone; amend if the real name should appear). Branch `automation-pipeline` is pushed;
open/track the PR at
`https://github.com/Amudhan-05/archaemetry/pull/new/automation-pipeline`.

---

## 13. Open decisions for the next chat

1. **Packaging target:** Colab notebook (zero-install, free GPU, best for the "field user"
   story) vs Dockerfile+AMI (reproducible, production) vs both. Recommended: Colab first.
2. **Full-auto vs bookend by default:** ship bookend (safe, GigaMesh for the profile) and
   let the ≥90°-rim-arc gate promote fragments to full-auto? Recommended: yes.
3. **Camera upgrade** before shooting real sherds (AW100 wide-angle distortion is the
   largest accuracy risk) — mirrorless + macro per the original handoff.
4. **Which SfM engine to standardise** for the open lane: COLMAP+OpenMVS (best for pose
   priors + packaging) is the recommendation.

---

## 14. Pointers

- Original setup/capture handoff: [`docs/handoff.md`](handoff.md)
- Empirical results + figures: [`docs/AUTOMATION_VALIDATION.md`](AUTOMATION_VALIDATION.md)
- Automation architecture + usage: [`scripts/README.md`](../scripts/README.md)
- Parameter surface: [`scripts/config/sherd.example.yaml`](../scripts/config/sherd.example.yaml)
- Reference papers (on the user's machine): Stamatopoulos & Anagnostopoulos (the chain's
  source); Hubert Mara / GigaMesh papers (rollouts, MSII, profiles).
- Sample vessel: Zenodo 5102757 (CC-BY-SA-4.0).
