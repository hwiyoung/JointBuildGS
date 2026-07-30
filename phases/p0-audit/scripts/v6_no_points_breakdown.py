#!/usr/bin/env python3
"""W4c — decompose the 46 DIM no_points buildings into (a) not-captured / (b) textureless /
(c) sparse / (d) impossible. Reuses T9 (09_failure_surface_cause.py) validated geometry+texture
verbatim (import). Read-only, CPU, P0 tools container (/workspace = phases/p0-audit). Observation only.

Rule (thresholds derived from DIM-success controls, disclosed):
  a not-captured : all_view_count <= 2 (~0 registered views = outside flight)
  c sparse       : captured but near_nadir < near_min (few near-nadir; more imaging adds them)
  (near_nadir >= near_min):
    textured (near_texture >= tex_low) : 기타 (had texture+nadir yet 0 pts — overlap/baseline)
    textureless (near_texture < tex_low):
      d impossible : near_nadir >= 2*near_min (abundant near-nadir, still textureless = sensor limit)
      b textureless: near_min <= near_nadir < 2*near_min (textureless, prior/method may help)
ALS point presence reported (ALS sees from above -> distinguishes UAV-flight gap from absence).
"""
import csv as _csv
import importlib.util
import json
import math
import sys
from pathlib import Path

import numpy as np

from p0_paths import P0_EVIDENCE

ROOT = Path("/workspace")
DATA = ROOT / "data"
DOCS = P0_EVIDENCE
STATUS_CSV = ROOT / "runs/w2_1_roofer_default_20260612_152729/building_reconstruction_status.csv"
N_CONTROL = 40

spec = importlib.util.spec_from_file_location("t9", str(ROOT / "scripts/09_failure_surface_cause.py"))
t9 = importlib.util.module_from_spec(spec)
sys.modules["t9"] = t9   # register before exec so @dataclass can resolve cls.__module__
spec.loader.exec_module(t9)


def main():
    rows = list(_csv.DictReader(open(STATUS_CSV)))
    failure_ids = [r["building_id"] for r in rows
                   if r["reason"] == "pointcloud_unusable_no_points" and r["input"] == "DIM"]
    succ = [r["building_id"] for r in rows if r["reason"] == "success" and r["input"] == "DIM"]
    control_ids = succ[:N_CONTROL]
    print(f"[w4c] failures(no_points)={len(failure_ids)}  controls(DIM-success)={len(control_ids)}")

    scratch = ROOT / "runs/v6c_no_points/scratch"; scratch.mkdir(parents=True, exist_ok=True)
    geojson = scratch / "lod2_ground_plan.geojson"
    gpkg = DATA / "work/footprints/lod2_ground_plan.gpkg"
    t9.convert_gpkg_to_geojson(gpkg, geojson, t9.FOOTPRINT_LAYER)
    fp = t9.load_footprints(geojson, set(failure_ids + control_ids))
    missing = [b for b in failure_ids if b not in fp]
    failure_ids = [b for b in failure_ids if b in fp]
    control_ids = [b for b in control_ids if b in fp]
    print(f"[w4c] footprints loaded={len(fp)}  failures-with-footprint={len(failure_ids)}  missing={len(missing)}")

    als = t9.read_cloud("ALS", sorted((DATA / "raw/als").glob("*.laz")),
                        t9.combined_bbox(list(fp.values()), 20.0))
    surf = {b: t9.surface_metrics(als, fp[b]) for b in fp}

    cam_model = t9.parse_camera_model(DATA / "work/colmap/sparse/0/cameras.txt")
    scene_ref = t9.read_json(DATA / "work/opf/opf/scene_reference_frame.json")
    cameras = t9.parse_colmap_cameras(DATA / "work/colmap/sparse/0/images.txt", scene_ref)
    print(f"[w4c] cameras={len(cameras)}")

    vc = t9.build_view_candidates(failure_ids, control_ids, fp, surf, cameras, cam_model, scene_ref)
    counts = t9.count_views(vc)
    sel = t9.select_texture_candidates(vc)
    print(f"[w4c] view candidates={len(vc)}  texture crops to measure={len(sel)} (loading images...)")
    crops = t9.measure_crop_metrics(ROOT / t9.IMAGE_DIR, sel)
    met = t9.summarize_crop_metrics(crops)
    thr = t9.derive_thresholds(control_ids, counts, met)
    near_min = thr["near_nadir_view_count_min"]; tex_low = thr["texture_gradient_low_max"]
    # oblique texture threshold from controls (oblique gradient has different magnitude than near-nadir)
    ob_ctrl = [met.get(b, {}).get("oblique_texture_gradient_mean", math.nan) for b in control_ids]
    ob_low = t9.percentile([v for v in ob_ctrl], 10.0)
    print(f"[w4c] thresholds: near_nadir_view_count_min={near_min:.1f}  "
          f"near_texture_low={tex_low:.5f}  oblique_texture_low(ctrl p10)={ob_low:.5f}")

    def classify(allv, nn, tex, ob_tex):
        # a: not captured (~0 views)
        if allv <= 2:
            return "a_not_captured"
        # near-nadir present & sufficient -> judge by near-nadir texture
        if nn >= near_min:
            if not np.isfinite(tex) or tex >= tex_low:
                return "e_other_textured"          # near-nadir + texture yet 0 pts (overlap/baseline)
            return "d_impossible" if nn >= 2 * near_min else "b_textureless"
        # near-nadir deficient (mostly 0) but captured obliquely -> use OBLIQUE texture
        if np.isfinite(ob_tex) and ob_tex < ob_low:
            return "b_textureless"                 # textureless even obliquely -> prior needed
        return "c_nearnadir_gap"                    # oblique texture ok -> re-fly nadir solves

    out = []
    for b in failure_ids:
        c = counts.get(b, {}); m = met.get(b, {}); s = surf[b]
        allv = int(c.get("all_view_count", 0)); nn = int(c.get("near_nadir_view_count", 0))
        ob = int(c.get("oblique_view_count", 0))
        tex = float(m.get("near_nadir_texture_gradient_mean", math.nan))
        obtex = float(m.get("oblique_texture_gradient_mean", math.nan))
        inc = float(m.get("near_nadir_incidence_deg", math.nan))
        shd = float(m.get("near_nadir_shadow_ratio", math.nan))
        cls = classify(allv, nn, tex, obtex)
        out.append({"building_id": b, "all_views": allv, "near_nadir": nn, "oblique": ob,
                    "near_nadir_incid_deg": round(inc, 1) if np.isfinite(inc) else "",
                    "near_texture_grad": round(tex, 5) if np.isfinite(tex) else "",
                    "oblique_texture_grad": round(obtex, 5) if np.isfinite(obtex) else "",
                    "near_shadow_ratio": round(shd, 3) if np.isfinite(shd) else "",
                    "als_point_count": int(s.point_count),
                    "als_density_pts_m2": round(s.density_pts_m2, 1),
                    "classification": cls})
    for b in missing:
        out.append({"building_id": b, "all_views": "", "near_nadir": "", "oblique": "",
                    "near_nadir_incid_deg": "", "near_texture_grad": "", "near_shadow_ratio": "",
                    "als_point_count": "", "als_density_pts_m2": "", "classification": "x_no_footprint"})

    from collections import Counter
    cc = Counter(r["classification"] for r in out)
    DOCS.mkdir(parents=True, exist_ok=True)
    keys = list(out[0].keys())
    with open(DOCS / "W4c_no_points_breakdown.csv", "w", newline="") as f:
        w = _csv.DictWriter(f, fieldnames=keys); w.writeheader(); w.writerows(out)
    json.dump({"counts": dict(cc), "thresholds": thr, "n_failures": len(out),
               "control_n": len(control_ids)},
              open(DOCS / "W4c_no_points_breakdown_meta.json", "w"), indent=1)
    print("\n=== W4c counts ===")
    for k in sorted(cc): print(f"  {k}: {cc[k]}")
    print(f"[done] -> {DOCS}/W4c_no_points_breakdown.csv (+ _meta.json)")


if __name__ == "__main__":
    main()
