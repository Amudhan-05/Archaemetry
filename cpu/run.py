"""One-command orchestrator for the automatable profile lane.

Reads a sherd config (see config/sherd.example.yaml) and drives:
  Stage 2  clean_mesh.py       -> clean.obj (+ report)
  Stage 3  extract_profile.py  -> profile.svg (+ overlay + report)
  Stage 4  publish_svg.py      -> drawing.svg (scale bar, CVA line weight)

Aggregates the per-stage confidence reports into run_report.json and prints a
GO / REVIEW verdict: a fragment whose axis could not be fixed from a clean rim
arc, or whose angular coverage is very low, is flagged for the manual / GigaMesh
route instead of silently producing a questionable drawing.

Stage 1 (SfM/MVS) is not run here yet - start from a mesh. Usage:
  python run.py --config sherd.yaml --input mesh.obj --outdir out/
"""
import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable


def load_config(path):
    try:
        import yaml
        with open(path) as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"[warn] could not read config ({e}); using defaults")
        return {}


def run(cmd):
    print("  $", " ".join(os.path.basename(c) if c.endswith(".py") else c for c in cmd))
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout); print(r.stderr)
        raise SystemExit(f"stage failed: {cmd[1]}")
    return r.stdout


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=os.path.join(HERE, "config", "sherd.example.yaml"))
    ap.add_argument("--input", required=True, help="input mesh (obj/ply)")
    ap.add_argument("--outdir", required=True)
    args = ap.parse_args()
    cfg = load_config(args.config) or {}
    os.makedirs(args.outdir, exist_ok=True)

    cleanup = cfg.get("cleanup", {})
    profile = cfg.get("profile", {})
    publish = cfg.get("publish", {})

    clean_obj = os.path.join(args.outdir, "clean.obj")
    clean_rep = os.path.join(args.outdir, "clean_report.json")
    prof_dir = os.path.join(args.outdir, "profile")
    drawing = os.path.join(args.outdir, "drawing.svg")

    print("Stage 2 - cleanup")
    cmd = [PY, os.path.join(HERE, "clean_mesh.py"), args.input, clean_obj,
           "--report", clean_rep]
    if cleanup.get("min_faces"):
        cmd += ["--min-faces", str(cleanup["min_faces"])]
    if cleanup.get("close_holes_max_mm"):
        cmd += ["--close-holes-max", str(int(cleanup["close_holes_max_mm"]))]
    run(cmd)

    print("Stage 3 - profile extraction")
    run([PY, os.path.join(HERE, "extract_profile.py"), clean_obj, prof_dir,
         "--axis-method", str(profile.get("axis_method", "pca")),
         "--bands", str(profile.get("bands", 300))])

    print("Stage 4 - publish")
    run([PY, os.path.join(HERE, "publish_svg.py"),
         os.path.join(prof_dir, "profile.svg"),
         os.path.join(prof_dir, "profile_report.json"), drawing,
         "--line-weight-mm", str(publish.get("line_weight_mm", 0.3))])

    # aggregate + verdict
    prof_rep = json.load(open(os.path.join(prof_dir, "profile_report.json")))
    clean = json.load(open(clean_rep))
    axis_method = prof_rep.get("axis_method", "")
    fell_back = "fallback" in str(prof_rep.get("axis_info", {}).get("method", axis_method))
    coverage = prof_rep.get("mean_angular_coverage", 0)
    flags = []
    if profile.get("axis_method") == "rim_arc" and fell_back:
        flags.append("rim_arc could not fix axis from a clean rim arc")
    if coverage < 0.25:
        flags.append(f"very low angular coverage ({coverage})")
    verdict = "REVIEW (route to GigaMesh / manual axis)" if flags else "GO"

    report = {
        "input": args.input,
        "verdict": verdict,
        "flags": flags,
        "cleanup": {k: clean.get(k) for k in
                    ("components_before", "kept_fraction", "compactness_ratio")},
        "profile": {k: prof_rep.get(k) for k in
                    ("axis_method", "axis_dir", "height_mm", "max_radius_mm",
                     "mean_angular_coverage", "wall_thickness_mm")},
        "outputs": {"clean": clean_obj, "drawing": drawing},
    }
    with open(os.path.join(args.outdir, "run_report.json"), "w") as f:
        json.dump(report, f, indent=2)
    print("\n==== RUN VERDICT:", verdict, "====")
    for fl in flags:
        print("  ! ", fl)
    print("drawing:", drawing)


if __name__ == "__main__":
    main()
