"""Test Stage 3 pipeline on GT (scene.obj) — isolate method vs data quality.

Treats each GT face as a single "primitive" (center=face centroid, normal=face
normal, area=face area, class from material). If val3dity pass rate is also
low here, Stage 3 algorithm is the bottleneck — NOT Stage 2 primitive quality.

Usage:
    python scripts/stage3_readout/gt_stage3_test.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.stage3_readout.obj_gt import parse_scene_obj  # noqa: E402
from src.stage3.building_instance import process_building  # noqa: E402


def _run_val3dity(cj_path: Path, rp_path: Path) -> dict:
    try:
        proc = subprocess.run(
            ["val3dity", "--report", str(rp_path), str(cj_path)],
            capture_output=True, text=True, timeout=180,
        )
    except Exception as e:
        return {"error": str(e)}
    out = {"returncode": proc.returncode}
    if rp_path.exists():
        try:
            out["report"] = json.loads(rp_path.read_text())
        except Exception as e:
            out["report_parse_error"] = str(e)
    return out


def _is_valid(v: dict) -> bool:
    rep = v.get("report", {})
    feats = rep.get("features", [])
    if feats:
        return bool(feats[0].get("validity", False))
    return False


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--method", choices=["convex", "2_5d"], default="2_5d")
    ap.add_argument("--out", default="results/phase2_ablation_citygml/_gt_stage3_test")
    ap.add_argument("--cos-thresh", type=float, default=0.85,
                    help="grouping threshold. 1.0 = no merging (true ceiling test)")
    args = ap.parse_args()
    out_dir = ROOT / args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    print("[gt-test] loading GT scene.obj …")
    gt = parse_scene_obj(str(ROOT / "results/phase2_synthesis/scene.obj"))
    print(f"[gt-test] {len(gt['buildings'])} buildings")

    n_processed = 0
    n_valid = 0
    per_building = []
    for b in gt["buildings"]:
        bid = b["building_id"]
        faces = b["faces"]
        if len(faces) < 3:
            continue

        # Build "primitives" dict (1 per face)
        centers = np.array([f["centroid"] for f in faces])
        normals = np.array([f["normal"] for f in faces])
        areas = np.array([f["area"] for f in faces])
        # semantic_probs: one-hot from semantic_class
        sem_probs = np.zeros((len(faces), 4), dtype=np.float32)
        for i, f in enumerate(faces):
            cls = f["semantic_class"]
            sem_probs[i, cls] = 1.0

        prim_dict = {
            "centers": centers,
            "normals": normals,
            "areas": areas,
            "semantic_probs": sem_probs,
        }
        prim_ids = np.arange(len(faces))

        bdir = out_dir / f"building_{bid:03d}"
        bdir.mkdir(parents=True, exist_ok=True)
        try:
            result = process_building(
                bid, prim_ids, prim_dict, str(bdir),
                cos_thresh=args.cos_thresh, hs_tol=0.10, method=args.method,
            )
        except Exception as e:
            per_building.append({"bid": bid, "type": b["type"],
                                 "error": f"process_building: {type(e).__name__}"})
            continue

        if result is None:
            per_building.append({"bid": bid, "type": b["type"],
                                 "error": "process_building returned None"})
            continue

        n_processed += 1
        # val3dity
        cj_path = Path(result["cityjson_path"])
        rp_path = bdir / "val3dity.json"
        v3d = _run_val3dity(cj_path, rp_path)
        valid = _is_valid(v3d)
        if valid:
            n_valid += 1
        per_building.append({"bid": bid, "type": b["type"],
                             "n_surfaces": result["n_surfaces"],
                             "signed_volume": result["signed_volume"],
                             "val3dity_valid": valid,
                             "val3dity_errors": [e.get("code", "?") for e in
                                (v3d.get("report", {}).get("features", [{}])[0]
                                 .get("errors", []) if v3d.get("report", {}).get("features") else [])]})

    n_total = len(gt["buildings"])
    pass_rate = n_valid / n_total if n_total else 0
    print(f"\n[gt-test] summary:")
    print(f"  processed: {n_processed}/{n_total}")
    print(f"  val3dity VALID: {n_valid}/{n_total} = {pass_rate*100:.1f}%")

    # Per-type breakdown
    from collections import defaultdict
    by_type = defaultdict(lambda: [0, 0])
    for e in per_building:
        by_type[e["type"]][1] += 1
        if e.get("val3dity_valid"):
            by_type[e["type"]][0] += 1
    print(f"\n[gt-test] val3dity by roof type:")
    for t, (v, n) in sorted(by_type.items()):
        print(f"  {t:12s}: {v:3d}/{n:3d} = {100*v/max(n,1):.1f}%")

    summary = {
        "n_buildings_total": n_total,
        "n_processed": n_processed,
        "n_val3dity_valid": n_valid,
        "val3dity_pass_rate": pass_rate,
        "by_type": {t: {"valid": v, "total": n} for t, (v, n) in by_type.items()},
        "per_building": per_building,
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    print(f"\n[gt-test] saved {out_dir/'summary.json'}")


if __name__ == "__main__":
    main()
