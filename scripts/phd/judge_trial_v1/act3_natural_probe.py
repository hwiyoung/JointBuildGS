"""판정전 3막(b) — 자연 낡음 심문 (실전 사례 시리즈, CPU, 무학습).

Pre-registration: JUDGE_TRIAL_PREREG_ko_v1.md §4(b) (2026-08-24 확정판).
Judge the INTACT ALS hypothesis on the N=12 buildings with the act-1 v5-④
photoconsistency instrument (image-only). Evaluation reference (never a method
input): the E1-based staleness map — cells where |median_z(ALS roof) −
median_z(E1 cls6)| > 1 m. Candidates (7) should show low support on stale
cells; ALS-current controls (5) calibrate the false-alarm threshold
(pooled control q05). Canopy contamination of E1 cls6 is a registered caveat.
scientific_verdict: null.
"""

from __future__ import annotations

import hashlib
import json
import sys
import zipfile
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path

import cv2
import numpy as np

REPO = Path("/workspace/JointBuildGS")
sys.path.insert(0, str(REPO))
from scripts.p2.c4_existing_als_v1 import prepare_prior as official  # noqa: E402
from scripts.phd.judge_trial_v1.act1_delta_probe import (  # noqa: E402
    auc_shifted_detect, load_als_with_intensity)
from scripts.phd.judge_trial_v1.act1_fullres_probe import (  # noqa: E402
    quat_to_R, read_cameras_bin)
from scripts.phd.judge_trial_v1.act2_change_probe import (  # noqa: E402
    densify, read_all_images_bin, score_run)
from scripts.phd.judge_trial_v1.act3_natural_staleness_screen import (  # noqa: E402
    E1_CROP_DIR, E1_LOCAL_SHIFT, cell_median_z, read_ply)
from shapely import contains_xy  # noqa: E402
from shapely.geometry import shape  # noqa: E402


def main() -> None:
    cfg = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    started = datetime.now(timezone.utc).isoformat()
    out_root = Path(cfg["out_root"])
    out_root.mkdir(parents=True, exist_ok=True)
    cache = Path(cfg["image_cache"])
    cache.mkdir(parents=True, exist_ok=True)

    screen = json.loads(Path(cfg["staleness_screen"]).read_text(encoding="utf-8"))["report"]
    model = Path(cfg["triangulated_model"])
    cams = read_cameras_bin(model / "cameras.bin")
    poses = read_all_images_bin(model / "images.bin")
    fps = {f["properties"].get("stable_id") or f["properties"].get("gml_id"): f["geometry"]
           for f in json.loads(Path(cfg["footprints_geojson"]).read_text())["features"]}
    zf = zipfile.ZipFile(cfg["raw_images_zip"])
    zmap = {Path(n).name: n for n in zf.namelist() if n.upper().endswith(".JPG")}

    cell = float(cfg["cell_m"])
    per_building = {}
    control_scores_pool = []
    for sid in cfg["targets"]:
        role = "candidate" if screen.get(sid, {}).get("natural_positive_candidate") else "control"
        poly_raw = shape(fps[sid])
        poly = poly_raw.buffer(float(cfg["footprint_buffer_m"]))
        bx = poly.bounds
        xyz0, _, _ = load_als_with_intensity(
            Path(cfg["als_root"]),
            np.asarray([bx[0] - 20, bx[1] - 20]), np.asarray([bx[2] + 20, bx[3] + 20]))
        wxy = xyz0[:, :2] + official.WORLD_SHIFT[:2]
        xyz0 = xyz0[contains_xy(poly, wxy[:, 0], wxy[:, 1])]
        ground_z = float(np.quantile(xyz0[:, 2], 0.05))
        roof = xyz0[xyz0[:, 2] > ground_z + float(cfg["roof_above_ground_m"])]
        if len(roof) < 200:
            roof = xyz0
        centroid = roof.mean(axis=0)

        cand = []
        for nm, pose in poses.items():
            cam = cams[pose["cam"]]
            R, t = quat_to_R(pose["q"]), pose["t"]
            c = centroid @ R.T + t
            if c[2] <= 0.1:
                continue
            fx, fy, cx_i, cy_i = cam["params"][:4]
            u = fx * c[0] / c[2] + cx_i
            v = fy * c[1] / c[2] + cy_i
            if not (0 <= u < cam["w"] and 0 <= v < cam["h"]):
                continue
            if fx / float(c[2]) >= float(cfg["min_px_per_m"]):
                cand.append((nm, fx / float(c[2]), R, t, cam))
        cand.sort(key=lambda r: -r[1])
        cand = cand[: int(cfg["max_views"])]
        if len(cand) < 6:
            per_building[sid] = {"role": role, "skipped": f"views {len(cand)}"}
            continue
        views, lums = {}, {}
        for nm, ppm, R, t, cam in cand:
            dst = cache / nm
            if not dst.exists():
                dst.write_bytes(zf.read(zmap[nm]))
            g = cv2.cvtColor(cv2.imread(str(dst)), cv2.COLOR_BGR2GRAY)
            lums[nm] = g.astype(np.float32)
            views[nm] = {"R": R, "t": t, "cam": cam, "center": -R.T @ t,
                         "depth": float((centroid @ R.T + t)[2])}
        pairs = []
        for a, b in combinations(sorted(views), 2):
            bz = float(np.linalg.norm(views[a]["center"] - views[b]["center"])) \
                / max(views[a]["depth"], views[b]["depth"])
            if cfg["pair_bz_min"] <= bz <= cfg["pair_bz_max"]:
                pairs.append((a, b, round(bz, 3)))
        pairs.sort(key=lambda p: -p[2])
        pairs = pairs[: int(cfg["max_pairs"])]

        X, C = densify(roof, cell, float(cfg["dense_sample_m"]),
                       float(cfg["jump_cell_z_range_m"]))
        scores = score_run(X, C, views, lums, pairs,
                           int(cfg["min_points_per_cell_pair"]),
                           int(cfg["min_pairs_per_cell"]))

        # evaluation-only staleness labels: |cell z(ALS roof) − cell z(E1 cls6)| > 1 m
        crops = sorted(E1_CROP_DIR.glob(f"B*_{sid}.points.ply"))
        labels = {}
        if crops:
            a = read_ply(crops[0])
            e1 = np.column_stack([np.asarray(a["x"], np.float64),
                                  np.asarray(a["y"], np.float64),
                                  np.asarray(a["z"], np.float64)]) + E1_LOCAL_SHIFT
            if "classification" in a.dtype.names:
                e1 = e1[np.asarray(a["classification"]) == 6]
            e1 = e1[contains_xy(poly, e1[:, 0], e1[:, 1])]
            e1_local = e1 - official.WORLD_SHIFT
            ca = cell_median_z(roof[:, :2], roof[:, 2])
            ce = cell_median_z(e1_local[:, :2], e1_local[:, 2])
            for c_ in set(ca) & set(ce):
                labels[c_] = abs(ca[c_] - ce[c_]) > float(cfg["dz_stale_m"])

        common = sorted(set(scores) & set(labels))
        stale = [c for c in common if labels[c]]
        cur = [c for c in common if not labels[c]]
        row = {"role": role, "n_views": len(views), "n_pairs": len(pairs),
               "n_cells_scored": len(scores), "n_eval_cells": len(common),
               "n_stale_cells": len(stale), "n_current_cells": len(cur)}
        if len(stale) >= 10 and len(cur) >= 10:
            s_st = np.asarray([scores[c] for c in stale])
            s_cu = np.asarray([scores[c] for c in cur])
            row["auc_stale_vs_current"] = round(auc_shifted_detect(s_cu, s_st, False), 4)
            row["med_score_stale"] = round(float(np.median(s_st)), 3)
            row["med_score_current"] = round(float(np.median(s_cu)), 3)
        if role == "control":
            control_scores_pool += [scores[c] for c in common]
        per_building[sid] = row
        (out_root / f"{sid}_scores.json").write_text(
            json.dumps({"scores": {str(k): v for k, v in scores.items()},
                        "stale_cells": [str(c) for c in stale]}, ensure_ascii=False),
            encoding="utf-8")

    tau = float(np.quantile(np.asarray(control_scores_pool), 0.05)) \
        if len(control_scores_pool) >= 100 else None
    if tau is not None:
        for sid, row in per_building.items():
            if "skipped" in row:
                continue
            sc = json.loads((out_root / f"{sid}_scores.json").read_text())
            scores = {k: v for k, v in sc["scores"].items()}
            stale_set = set(sc["stale_cells"])
            flagged = {k for k, v in scores.items() if v < tau}
            evald = set(scores) & (stale_set | {k for k in scores if k not in stale_set})
            row["flag_share_all"] = round(len(flagged) / max(1, len(scores)), 3)
            if stale_set:
                row["flag_recall_on_stale"] = round(
                    len(flagged & stale_set) / len(stale_set), 3)

    receipt = {
        "schema": "phd_judge_trial_act3_natural_receipt_v1",
        "task_id": cfg["task_id"],
        "started_at": started, "ended_at": datetime.now(timezone.utc).isoformat(),
        "config_sha256": hashlib.sha256(json.dumps(cfg, sort_keys=True).encode()).hexdigest(),
        "pre_registration": "JUDGE_TRIAL_PREREG_ko_v1.md §4(b) 확정판",
        "evaluation_reference": "E1-based staleness map — evaluation only (invariant 9), "
                                "canopy-contamination caveat registered",
        "tau_control_q05": tau,
        "buildings": per_building,
        "scientific_verdict": None,
    }
    (out_root / "receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"tau": tau, "buildings": per_building}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
