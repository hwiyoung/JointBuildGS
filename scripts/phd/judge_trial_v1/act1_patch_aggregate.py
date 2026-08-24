"""판정전 1막 v5-⑤ — 판정 단위 상향: 셀 → 패치(연결 세그먼트) 집계 판독.

v5-④ raised per-cell power to a clean monotone dose-response (sloped AUC
0.49→0.71 across δ) but the δ=4 gate (0.75) is 0.04 short at CELL level.
The pre-registered consequence of the power analysis is to judge at PATCH
level: cells of a stratum are grouped into 4-connected grid segments and
their Fisher-z scores averaged. Reads v5-④ cell_scores.json; no image work.
Reports per δ: segment medians, paired sign test (all-segments-worse?), and
AUC when n allows. scientific_verdict: null.
"""

from __future__ import annotations

import json
import sys
from math import comb
from pathlib import Path

import numpy as np

REPO = Path("/workspace/JointBuildGS")
sys.path.insert(0, str(REPO))
from scripts.p2.c4_existing_als_v1 import prepare_prior as official  # noqa: E402
from scripts.phd.judge_trial_v1.act1_delta_probe import (  # noqa: E402
    auc_shifted_detect, load_als_with_intensity)
from shapely import contains_xy  # noqa: E402
from shapely.geometry import Point, shape  # noqa: E402


def main() -> None:
    cfg = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    scores = json.loads((Path(cfg["out_root"]) / "cell_scores.json").read_text())["results"]

    feat = json.loads(Path(cfg["footprint_geojson"]).read_text(encoding="utf-8"))["features"][0]
    poly_raw = shape(feat["geometry"])
    poly = poly_raw.buffer(float(cfg["footprint_buffer_m"]))
    bx = poly.bounds
    xyz0, _, _ = load_als_with_intensity(
        Path(cfg["als_root"]),
        np.asarray([bx[0] - 20, bx[1] - 20]), np.asarray([bx[2] + 20, bx[3] + 20]))
    wxy = xyz0[:, :2] + official.WORLD_SHIFT[:2]
    xyz0 = xyz0[contains_xy(poly, wxy[:, 0], wxy[:, 1])]
    gz = float(np.quantile(xyz0[:, 2], 0.05))
    xyz0 = xyz0[xyz0[:, 2] > gz + float(cfg["roof_above_ground_m"])]

    cell = float(cfg["cell_m"])
    cell_id = (np.floor(xyz0[:, 0] / cell).astype(np.int64) << 32) \
        + np.floor(xyz0[:, 1] / cell).astype(np.int64)
    uniq_cells, inv = np.unique(cell_id, return_inverse=True)
    zmin = np.full(len(uniq_cells), np.inf)
    zmax = np.full(len(uniq_cells), -np.inf)
    np.minimum.at(zmin, inv, xyz0[:, 2])
    np.maximum.at(zmax, inv, xyz0[:, 2])
    counts = np.bincount(inv).astype(np.float64)
    cxs = np.bincount(inv, weights=xyz0[:, 0]) / counts
    cys = np.bincount(inv, weights=xyz0[:, 1]) / counts
    ring = poly_raw.exterior
    ring_len = ring.length
    slope_thr = float(cfg["sloped_cell_z_range_m"])
    stratum = {}
    for i, (cx_, cy_) in enumerate(zip(cxs, cys)):
        p = Point(cx_ + official.WORLD_SHIFT[0], cy_ + official.WORLD_SHIFT[1])
        if ring.distance(p) <= 3.0:
            s = ring.project(p)
            p0 = ring.interpolate((s - 0.7) % ring_len)
            p1 = ring.interpolate((s + 0.7) % ring_len)
            tv = np.asarray([p1.x - p0.x, p1.y - p0.y])
            nv = np.linalg.norm(tv)
            ty = abs(tv[1] / nv) if nv > 1e-9 else 0.0
            stratum[i] = "edge_perp" if ty >= 0.7 else "edge_other"
        else:
            stratum[i] = "interior_sloped" if (zmax[i] - zmin[i]) >= slope_thr \
                else "interior_flat"

    ix = (uniq_cells >> 32).astype(np.int64)
    iy = (uniq_cells - (ix << 32)).astype(np.int64)
    coord_to_i = {(int(a), int(b)): i for i, (a, b) in enumerate(zip(ix, iy))}

    def segments(target: set[int]) -> list[list[int]]:
        seen, out = set(), []
        for i in target:
            if i in seen:
                continue
            comp, stack = [], [i]
            seen.add(i)
            while stack:
                j = stack.pop()
                comp.append(j)
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    k = coord_to_i.get((int(ix[j]) + dx, int(iy[j]) + dy))
                    if k is not None and k in target and k not in seen:
                        seen.add(k)
                        stack.append(k)
            out.append(comp)
        return out

    report = {}
    for st_name in ("interior_sloped", "edge_perp"):
        target = {i for i, s in stratum.items() if s == st_name
                  and str(scores["0.0"].get(str(i))) != "None" and str(i) in scores["0.0"]}
        segs = [c for c in segments(target) if len(c) >= int(cfg_seg_min)]
        rows = {}
        for dk in [k for k in scores if k != "0.0"]:
            s0v, sdv = [], []
            for comp in segs:
                z0 = [np.arctanh(np.clip(scores["0.0"][str(i)], -0.999, 0.999))
                      for i in comp if str(i) in scores["0.0"] and str(i) in scores[dk]]
                zd = [np.arctanh(np.clip(scores[dk][str(i)], -0.999, 0.999))
                      for i in comp if str(i) in scores["0.0"] and str(i) in scores[dk]]
                if len(z0) >= int(cfg_seg_min):
                    s0v.append(float(np.tanh(np.mean(z0))))
                    sdv.append(float(np.tanh(np.mean(zd))))
            n = len(s0v)
            if n < 3:
                rows[dk] = {"n_segments": n}
                continue
            s0a, sda = np.asarray(s0v), np.asarray(sdv)
            worse = int((sda < s0a).sum())
            p_sign = sum(comb(n, k) for k in range(worse, n + 1)) / 2 ** n
            rows[dk] = {
                "n_segments": n,
                "med_s0": round(float(np.median(s0a)), 3),
                "med_sd": round(float(np.median(sda)), 3),
                "worse": f"{worse}/{n}",
                "sign_test_p": round(p_sign, 5),
                "auc": round(auc_shifted_detect(s0a, sda, False), 4) if n >= 10 else None,
            }
        report[st_name] = {"n_segments_total": len(segs),
                           "segment_sizes": sorted((len(c) for c in segs), reverse=True),
                           "per_delta": rows}

    out = Path(cfg["out_root"]) / "patch_aggregate_readout.json"
    out.write_text(json.dumps({"schema": "phd_judge_trial_act1_patch_aggregate_v1",
                               "segment_min_cells": int(cfg_seg_min),
                               "report": report, "scientific_verdict": None},
                              ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


cfg_seg_min = 4

if __name__ == "__main__":
    main()
