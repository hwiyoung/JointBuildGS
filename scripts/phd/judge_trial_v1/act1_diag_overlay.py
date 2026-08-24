"""판정전 1막 진단 — δ=0 실루엣이 영상 윤곽 위에 있는가 (측정기 vs 신호 분리).

For 3 representative views and δ ∈ {0, 1, 2, 4} m east: project the roof-subset
prior, extract its silhouette, and (a) report the median pixel distance from
silhouette pixels to the nearest strong Canny edge, (b) save RGB overlays
(silhouette δ=0 green / δ=1 red / δ=4 yellow on the photo) for human inspection.

If d(δ=0) ≈ d(δ=4): the silhouette is not matched to any image structure —
projection/visibility defect (measurement broken). If d(δ=0) << d(δ=4) but the
probe AUC is flat: aggregation/formula kills real signal. scientific_verdict: null.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import numpy as np
import yaml

REPO = Path("/workspace/JointBuildGS")
sys.path.insert(0, str(REPO))
from scripts.p2.c4_existing_als_v1 import prepare_prior as official  # noqa: E402
from src.stage2.dataloader import ColmapDataset  # noqa: E402
from scripts.phd.judge_trial_v1.act1_delta_probe import (  # noqa: E402
    load_als_with_intensity, project_pooled)
from shapely import contains_xy  # noqa: E402
from shapely.geometry import shape  # noqa: E402

VIEW_PICKS = (5, 27, 45)
DELTAS = (0.0, 1.0, 2.0, 4.0)
COLORS = {0.0: (0, 255, 0), 1.0: (255, 0, 0), 2.0: (255, 128, 0), 4.0: (255, 255, 0)}


def main() -> None:
    cfg = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    out = Path(cfg["out_root"]).parent / "act1_diag"
    out.mkdir(parents=True, exist_ok=True)
    base = yaml.safe_load((REPO / cfg["base_yaml"]).read_text())
    base.update(yaml.safe_load((REPO / cfg["fused_yaml"]).read_text())["overrides"])
    dataset = ColmapDataset(base["data_root"], downscale=1.0, load_depth=False,
                            load_normal=False, load_semantic=False,
                            visible_views=list(base["visible_views"]))
    seed = dataset.points_xyz.astype(np.float64)
    low = np.quantile(seed[:, :2], 0.001, axis=0) + official.WORLD_SHIFT[:2] - 10.0
    high = np.quantile(seed[:, :2], 0.999, axis=0) + official.WORLD_SHIFT[:2] + 10.0
    xyz0, _, _ = load_als_with_intensity(Path(cfg["als_root"]), low, high)
    feat = json.loads(Path(cfg["footprint_geojson"]).read_text(encoding="utf-8"))["features"][0]
    poly = shape(feat["geometry"]).buffer(float(cfg["footprint_buffer_m"]))
    wxy = xyz0[:, :2] + official.WORLD_SHIFT[:2]
    xyz0 = xyz0[contains_xy(poly, wxy[:, 0], wxy[:, 1])]
    ground_z = float(np.quantile(xyz0[:, 2], 0.05))
    roof = xyz0[xyz0[:, 2] > ground_z + float(cfg["roof_above_ground_m"])]

    kernel = np.ones((3, 3), np.uint8)
    report = {}
    for vi in VIEW_PICKS:
        s = dataset[vi]
        rgb = (s["rgb"].numpy() * 255).astype(np.uint8)
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        lo, hi = cfg["canny_thresholds"]
        canny = cv2.Canny(gray, int(lo), int(hi))
        dist = cv2.distanceTransform((canny == 0).astype(np.uint8), cv2.DIST_L2, 3)
        k = s["K"].numpy().astype(np.float64)
        w2c = s["w2c"].numpy().astype(np.float64)
        hp, wp = int(s["height"]), int(s["width"])
        overlay = rgb.copy()
        row = {}
        for d in DELTAS:
            key, _, dep = project_pooled(roof + [d, 0.0, 0.0], k, w2c, hp, wp, 1)
            sup = np.zeros((hp, wp), np.uint8)
            sup.flat[key] = 1
            sup = cv2.dilate(sup, kernel)
            sup = cv2.morphologyEx(sup, cv2.MORPH_CLOSE, kernel,
                                   iterations=int(cfg["support_closing_iterations"]))
            sup = cv2.erode(sup, kernel)
            sil = cv2.morphologyEx(sup, cv2.MORPH_GRADIENT, kernel).astype(bool)
            dvals = dist[sil]
            row[str(d)] = {"sil_px": int(sil.sum()),
                           "dist_med_px": round(float(np.median(dvals)), 2) if len(dvals) else None,
                           "dist_p25": round(float(np.percentile(dvals, 25)), 2) if len(dvals) else None}
            overlay[sil] = COLORS[d]
        overlay[canny > 0] = np.clip(overlay[canny > 0].astype(int) + 60, 0, 255).astype(np.uint8)
        name = Path(s["name"]).stem
        cv2.imwrite(str(out / f"judge_diag_{name}.png"),
                    cv2.cvtColor(overlay, cv2.COLOR_RGB2BGR))
        report[name] = row
    (out / "diag_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
