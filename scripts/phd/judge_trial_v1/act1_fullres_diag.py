"""풀해상도 진단 오버레이 — 근접 뷰에서 δ=0(초록)/δ=4(노랑) 실루엣 + 강에지."""
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
from scripts.phd.judge_trial_v1.act1_delta_probe import load_als_with_intensity  # noqa: E402
from scripts.phd.judge_trial_v1.act1_fullres_probe import (  # noqa: E402
    project_full_opencv, quat_to_R, read_cameras_bin, read_images_bin)
from shapely import contains_xy  # noqa: E402
from shapely.geometry import shape  # noqa: E402

VIEWS = ("DJI_20241217084813_0170_D.JPG", "DJI_20241217090833_0019_D.JPG")
DELTAS = {0.0: (0, 255, 0), 4.0: (0, 255, 255)}  # BGR: green, yellow


def main() -> None:
    cfg = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    out = Path(cfg["out_root"]) / "diag"
    out.mkdir(parents=True, exist_ok=True)
    model = Path(cfg["triangulated_model"])
    cams = read_cameras_bin(model / "cameras.bin")
    poses = read_images_bin(model / "images.bin", set(VIEWS))
    feat = json.loads(Path(cfg["footprint_geojson"]).read_text(encoding="utf-8"))["features"][0]
    poly = shape(feat["geometry"]).buffer(float(cfg["footprint_buffer_m"]))
    bx = poly.bounds
    xyz0, _, _ = load_als_with_intensity(
        Path(cfg["als_root"]),
        np.asarray([bx[0] - 20, bx[1] - 20]), np.asarray([bx[2] + 20, bx[3] + 20]))
    wxy = xyz0[:, :2] + official.WORLD_SHIFT[:2]
    xyz0 = xyz0[contains_xy(poly, wxy[:, 0], wxy[:, 1])]
    gz = float(np.quantile(xyz0[:, 2], 0.05))
    roof = xyz0[xyz0[:, 2] > gz + float(cfg["roof_above_ground_m"])]
    kernel = np.ones((3, 3), np.uint8)
    report = {}
    for nm in VIEWS:
        pose = poses[nm]
        cam = cams[pose["cam"]]
        R, t = quat_to_R(pose["q"]), pose["t"]
        img = cv2.imread(str(Path(cfg["image_cache"]) / nm))
        lo, hi = cfg["canny_thresholds"]
        canny = cv2.Canny(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), int(lo), int(hi))
        img[canny > 0] = np.clip(img[canny > 0].astype(int) + 70, 0, 255).astype(np.uint8)
        h, w = canny.shape
        dist = cv2.distanceTransform((canny == 0).astype(np.uint8), cv2.DIST_L2, 3)
        centroid = roof.mean(axis=0)
        depth_c = float((centroid @ R.T + t)[2])
        px_per_m = float(cam["params"][0] / depth_c)
        r_px = max(2, int(round(0.3 * px_per_m)))
        row = {"px_per_m": round(px_per_m, 1), "r_px": r_px}
        allx, ally = [], []
        for d, color in DELTAS.items():
            key, _, _ = project_full_opencv(roof + [d, 0.0, 0.0], R, t, cam)
            sup = np.zeros((h, w), np.uint8)
            pys, pxs = (key // w).astype(int), (key % w).astype(int)
            for yy, xx in zip(pys, pxs):
                cv2.circle(sup, (int(xx), int(yy)), r_px, 1, -1)
            sup = cv2.morphologyEx(sup, cv2.MORPH_CLOSE, kernel,
                                   iterations=int(cfg["support_closing_iterations"]))
            sil = cv2.morphologyEx(sup, cv2.MORPH_GRADIENT, kernel).astype(bool)
            sil = cv2.dilate(sil.astype(np.uint8), kernel).astype(bool)  # visibility
            img[sil] = color
            dv = dist[sil]
            row[str(d)] = {"sil_px": int(sil.sum()),
                           "dist_med_px": round(float(np.median(dv)), 2) if len(dv) else None}
            ys, xs = np.nonzero(sil)
            if len(ys):
                allx += [xs.min(), xs.max()]
                ally += [ys.min(), ys.max()]
        if allx:
            m = 120
            x0, x1 = max(0, min(allx) - m), min(w, max(allx) + m)
            y0, y1 = max(0, min(ally) - m), min(h, max(ally) + m)
            crop = img[y0:y1, x0:x1]
            if crop.shape[1] > 2000:
                s = 2000 / crop.shape[1]
                crop = cv2.resize(crop, (2000, int(crop.shape[0] * s)), interpolation=cv2.INTER_AREA)
            cv2.imwrite(str(out / f"fullres_diag_{Path(nm).stem}.png"), crop)
        report[nm] = row
    (out / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
