"""판정전 1막 v5-④ — 광도 일관성 채널의 집계 검정력 상향 (신호 불변, CPU).

v5-③ found the first real signal (sloped-cell correlation 0.191 collapsing ~4×
under any injected δ, exactly the pre-registered observability map) but per-cell
variance kept AUC at 0.52–0.59: sparse ≥12-point samples, half-res luminance,
40 pairs, median aggregation. This probe raises statistical power WITHOUT
changing the signal definition:

  densify   — fit a local plane per 1 m cell (the method's own planar-patch
              hypothesis in miniature; jump cells fit the upper/roof cluster)
              and sample a 0.15 m grid on it (~49 samples/cell instead of ~12)
  sharpen   — full-resolution luminance, bilinear (sub-pixel) sampling
  aggregate — all view pairs in the baseline band (~150) with Fisher-z mean

Everything else (population, strata, validity gate δ=4, image-only judge,
synthetic-δ labeling) is unchanged. scientific_verdict: null.
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path

import cv2
import numpy as np
import yaml

REPO = Path("/workspace/JointBuildGS")
sys.path.insert(0, str(REPO))
from scripts.p2.c4_existing_als_v1 import prepare_prior as official  # noqa: E402
from scripts.phd.judge_trial_v1.act1_delta_probe import (  # noqa: E402
    auc_shifted_detect, load_als_with_intensity)
from scripts.phd.judge_trial_v1.act1_fullres_probe import (  # noqa: E402
    quat_to_R, read_cameras_bin, read_images_bin)
from scripts.phd.judge_trial_v1.act1_photoconsistency_probe import project_points  # noqa: E402
from shapely import contains_xy  # noqa: E402
from shapely.geometry import Point, shape  # noqa: E402


def bilinear(img: np.ndarray, u: np.ndarray, v: np.ndarray) -> np.ndarray:
    x0 = np.floor(u).astype(np.int64)
    y0 = np.floor(v).astype(np.int64)
    dx = (u - x0).astype(np.float32)
    dy = (v - y0).astype(np.float32)
    i = img
    return (i[y0, x0] * (1 - dx) * (1 - dy) + i[y0, x0 + 1] * dx * (1 - dy)
            + i[y0 + 1, x0] * (1 - dx) * dy + i[y0 + 1, x0 + 1] * dx * dy)


def main() -> None:
    cfg = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    started = datetime.now(timezone.utc).isoformat()
    out_root = Path(cfg["out_root"])
    out_root.mkdir(parents=True, exist_ok=True)

    base = yaml.safe_load((REPO / cfg["base_yaml"]).read_text())
    base.update(yaml.safe_load((REPO / cfg["fused_yaml"]).read_text())["overrides"])
    names = list(base["visible_views"])
    model = Path(cfg["triangulated_model"])
    cams = read_cameras_bin(model / "cameras.bin")
    poses = read_images_bin(model / "images.bin", set(names))

    feat = json.loads(Path(cfg["footprint_geojson"]).read_text(encoding="utf-8"))["features"][0]
    poly_raw = shape(feat["geometry"])
    poly = poly_raw.buffer(float(cfg["footprint_buffer_m"]))
    bx = poly.bounds
    xyz0, _, als_rows = load_als_with_intensity(
        Path(cfg["als_root"]),
        np.asarray([bx[0] - 20, bx[1] - 20]), np.asarray([bx[2] + 20, bx[3] + 20]))
    wxy = xyz0[:, :2] + official.WORLD_SHIFT[:2]
    xyz0 = xyz0[contains_xy(poly, wxy[:, 0], wxy[:, 1])]
    gz = float(np.quantile(xyz0[:, 2], 0.05))
    xyz0 = xyz0[xyz0[:, 2] > gz + float(cfg["roof_above_ground_m"])]
    centroid = xyz0.mean(axis=0)

    cell = float(cfg["cell_m"])
    cell_id = (np.floor(xyz0[:, 0] / cell).astype(np.int64) << 32) \
        + np.floor(xyz0[:, 1] / cell).astype(np.int64)
    uniq_cells, inv = np.unique(cell_id, return_inverse=True)

    # --- per-cell plane fit → dense 0.15 m sample grid (planar-patch miniature)
    step = float(cfg["dense_sample_m"])
    jump_thr = float(cfg["jump_cell_z_range_m"])
    dense_pts, dense_cid = [], []
    plane_stats = {"fit": 0, "jump_upper": 0, "skipped": 0}
    for ci, u in enumerate(uniq_cells):
        pts = xyz0[inv == ci]
        if len(pts) < 5:
            plane_stats["skipped"] += 1
            continue
        z0, z1 = pts[:, 2].min(), pts[:, 2].max()
        fit_pts = pts
        if (z1 - z0) > jump_thr:
            fit_pts = pts[pts[:, 2] >= np.median(pts[:, 2])]
            plane_stats["jump_upper"] += 1
            if len(fit_pts) < 5:
                plane_stats["skipped"] += 1
                continue
        A = np.column_stack([fit_pts[:, 0], fit_pts[:, 1], np.ones(len(fit_pts))])
        try:
            coef, *_ = np.linalg.lstsq(A, fit_pts[:, 2], rcond=None)
        except np.linalg.LinAlgError:
            plane_stats["skipped"] += 1
            continue
        plane_stats["fit"] += 1
        ix = np.int64(u) >> 32
        iy = np.int64(u) - (ix << 32)
        gx = np.arange(ix * cell + step / 2, (ix + 1) * cell, step)
        gy = np.arange(iy * cell + step / 2, (iy + 1) * cell, step)
        GX, GY = np.meshgrid(gx, gy)
        GZ = coef[0] * GX + coef[1] * GY + coef[2]
        dense_pts.append(np.column_stack([GX.ravel(), GY.ravel(), GZ.ravel()]))
        dense_cid.append(np.full(GX.size, ci, np.int64))
    X = np.concatenate(dense_pts)
    C = np.concatenate(dense_cid)
    n_cells = len(uniq_cells)

    # strata (same as v5-③)
    counts = np.bincount(inv).astype(np.float64)
    cxs = np.bincount(inv, weights=xyz0[:, 0]) / counts
    cys = np.bincount(inv, weights=xyz0[:, 1]) / counts
    zmin = np.full(n_cells, np.inf)
    zmax = np.full(n_cells, -np.inf)
    np.minimum.at(zmin, inv, xyz0[:, 2])
    np.maximum.at(zmax, inv, xyz0[:, 2])
    ring = poly_raw.exterior
    ring_len = ring.length
    slope_thr = float(cfg["sloped_cell_z_range_m"])
    cell_stratum = {}
    for i, (u, cx_, cy_) in enumerate(zip(uniq_cells, cxs, cys)):
        p = Point(cx_ + official.WORLD_SHIFT[0], cy_ + official.WORLD_SHIFT[1])
        if ring.distance(p) <= 3.0:
            s = ring.project(p)
            p0 = ring.interpolate((s - 0.7) % ring_len)
            p1 = ring.interpolate((s + 0.7) % ring_len)
            tv = np.asarray([p1.x - p0.x, p1.y - p0.y])
            nv = np.linalg.norm(tv)
            ty = abs(tv[1] / nv) if nv > 1e-9 else 0.0
            cell_stratum[i] = "edge_perp" if ty >= 0.7 else "edge_other"
        else:
            cell_stratum[i] = "interior_sloped" if (zmax[i] - zmin[i]) >= slope_thr \
                else "interior_flat"

    # luminance cache (full-res float32 kept as uint8→float on the fly)
    lums, view_geo = {}, {}
    for nm in names:
        pose = poses[nm]
        cam = cams[pose["cam"]]
        R, t = quat_to_R(pose["q"]), pose["t"]
        d_c = float((centroid @ R.T + t)[2])
        if d_c <= 0.1 or cam["params"][0] / d_c < float(cfg["min_px_per_m"]):
            continue
        g = cv2.cvtColor(cv2.imread(str(Path(cfg["image_cache"]) / nm)), cv2.COLOR_BGR2GRAY)
        lums[nm] = g.astype(np.float32)
        view_geo[nm] = {"R": R, "t": t, "cam": cam, "center": -R.T @ t, "depth": d_c}
    used = sorted(lums)

    pairs = []
    for a, b in combinations(used, 2):
        bz = float(np.linalg.norm(view_geo[a]["center"] - view_geo[b]["center"])) \
            / max(view_geo[a]["depth"], view_geo[b]["depth"])
        if cfg["pair_bz_min"] <= bz <= cfg["pair_bz_max"]:
            pairs.append((a, b, round(bz, 3)))
    pairs.sort(key=lambda p: -p[2])
    pairs = pairs[: int(cfg["max_pairs"])]

    deltas = [float(d) for d in cfg["deltas_east_m"]]
    min_pts = int(cfg["min_points_per_cell_pair"])
    min_pairs = int(cfg["min_pairs_per_cell"])
    results = {}
    for d in deltas:
        Xs = X + np.asarray([d, 0.0, 0.0])
        proj = {}
        for nm in used:
            g = view_geo[nm]
            u, v, ok = project_points(Xs, g["R"], g["t"], g["cam"], 1.0)
            h, w = lums[nm].shape
            inside = ok & (u >= 0) & (u < w - 2) & (v >= 0) & (v < h - 2)
            lum = np.zeros(len(Xs), np.float32)
            lum[inside] = bilinear(lums[nm], u[inside], v[inside])
            proj[nm] = (inside, lum)
        zsum = np.zeros(n_cells)
        zcnt = np.zeros(n_cells, np.int64)
        for a, b, _bz in pairs:
            ia, la = proj[a]
            ib, lb = proj[b]
            both = ia & ib
            cidb = C[both]
            x, y = la[both], lb[both]
            n = np.bincount(cidb, minlength=n_cells).astype(np.float64)
            sx = np.bincount(cidb, weights=x, minlength=n_cells)
            sy = np.bincount(cidb, weights=y, minlength=n_cells)
            sxx = np.bincount(cidb, weights=x * x, minlength=n_cells)
            syy = np.bincount(cidb, weights=y * y, minlength=n_cells)
            sxy = np.bincount(cidb, weights=x * y, minlength=n_cells)
            with np.errstate(invalid="ignore", divide="ignore"):
                cov = sxy - sx * sy / np.maximum(n, 1)
                vx = sxx - sx * sx / np.maximum(n, 1)
                vy = syy - sy * sy / np.maximum(n, 1)
                r = cov / np.sqrt(vx * vy)
            good = (n >= min_pts) & np.isfinite(r) & (vx > 1e-3) & (vy > 1e-3)
            rz = np.arctanh(np.clip(r[good], -0.999, 0.999))
            idx = np.flatnonzero(good)
            zsum[idx] += rz
            zcnt[idx] += 1
        ok_cells = zcnt >= min_pairs
        results[str(d)] = {int(i): float(np.tanh(zsum[i] / zcnt[i]))
                           for i in np.flatnonzero(ok_cells)}

    base_key = str(deltas[0])
    summary = {"views_used": len(used), "pairs_used": len(pairs),
               "dense_samples": int(len(X)), "plane_stats": plane_stats,
               "cells_defined": {d: len(v) for d, v in results.items()},
               "auc": {}, "strata": {}}
    for d in deltas[1:]:
        dk = str(d)
        common = sorted(set(results[base_key]) & set(results[dk]))
        if len(common) < 20:
            summary["auc"][dk] = None
            continue
        s0 = np.asarray([results[base_key][c] for c in common])
        sd = np.asarray([results[dk][c] for c in common])
        summary["auc"][dk] = round(auc_shifted_detect(s0, sd, False), 4)
        strata = {}
        for name_ in ("edge_perp", "edge_other", "interior_sloped", "interior_flat"):
            sel = [i for i, c in enumerate(common) if cell_stratum.get(c) == name_]
            strata[name_] = ({"n": len(sel),
                              "auc": round(auc_shifted_detect(s0[sel], sd[sel], False), 4),
                              "med_s0": round(float(np.median(s0[sel])), 3),
                              "med_sd": round(float(np.median(sd[sel])), 3)}
                             if len(sel) >= 15 else {"n": len(sel), "auc": None})
        summary["strata"][dk] = strata

    gate_d = str(float(cfg["validity_gate_delta"]))
    gate_vals = [v["auc"] for v in (summary["strata"].get(gate_d) or {}).values()
                 if v.get("auc") is not None]
    best = max([summary["auc"].get(gate_d) or 0.0] + gate_vals) if gate_vals \
        else summary["auc"].get(gate_d)
    summary["validity_gate"] = {"delta_m": float(cfg["validity_gate_delta"]),
                                "best_auc": best,
                                "passed": bool(best is not None and best >= 0.75)}

    (out_root / "cell_scores.json").write_text(
        json.dumps({"schema": "phd_judge_trial_act1_photoconsistency_v2_scores_v1",
                    "results": results}, ensure_ascii=False), encoding="utf-8")
    receipt = {
        "schema": "phd_judge_trial_act1_photoconsistency_v2_receipt_v1",
        "task_id": cfg["task_id"],
        "started_at": started,
        "ended_at": datetime.now(timezone.utc).isoformat(),
        "config_sha256": hashlib.sha256(json.dumps(cfg, sort_keys=True).encode()).hexdigest(),
        "signal": "multi-view photoconsistency, power-raised: cell-plane 0.15 m dense grid, "
                  "full-res bilinear luminance, Fisher-z over all band pairs",
        "als_sources": als_rows,
        "delta_injection": {"deltas_east_m": deltas, "synthetic": True,
                            "not_real_als_lineage": True},
        "summary": summary,
        "scientific_verdict": None,
    }
    (out_root / "receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
