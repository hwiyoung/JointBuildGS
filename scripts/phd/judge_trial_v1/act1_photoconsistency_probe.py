"""판정전 1막 v5-③ — 다중-뷰 광도 일관성 채널 (이론 정합 신호, CPU).

Edge-proximity scoring was refuted (v5-②: correct, splatted, visually-verified
silhouettes still fail the δ=4 gate — the true roof boundary is low-contrast
while clutter (solar grids, stains) dominates the Canny landscape). This probe
switches to the signal the joint optimization itself would use: multi-view
photometric consistency of the hypothesis surface.

Mechanism: a hypothesis 3D point is sampled in two views. If the geometry is
right, both rays hit the same physical spot → luminances correlate (per-cell
Pearson removes local gain/offset). Under an injected δ the point floats off
the true surface wherever the surface is sloped or discontinuous → the two
views sample different physical content → decorrelation. Structural blind spot
(pre-registered): flat-interior cells are invariant under in-plane δ — the
shifted point still lies on the same plane. The sawtooth (sloped) roof of the
corridor building is therefore the live test bed.

Judge is image-only; occlusion is approximated (aerial roof views). All δ
products synthetic. scientific_verdict: null.
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
from shapely import contains_xy  # noqa: E402
from shapely.geometry import Point, shape  # noqa: E402


def project_points(xyz, R, t, cam, scale):
    """Per-point distorted pixel (no z-buffer; float coords at `scale`)."""
    fx, fy, cx, cy, k1, k2, p1, p2, k3, k4, k5, k6 = cam["params"]
    c = xyz @ R.T + t
    ok = c[:, 2] > 0.1
    x = np.where(ok, c[:, 0] / np.where(ok, c[:, 2], 1.0), 0.0)
    y = np.where(ok, c[:, 1] / np.where(ok, c[:, 2], 1.0), 0.0)
    r2 = x * x + y * y
    radial = (1 + k1 * r2 + k2 * r2 ** 2 + k3 * r2 ** 3) \
        / (1 + k4 * r2 + k5 * r2 ** 2 + k6 * r2 ** 3)
    xd = x * radial + 2 * p1 * x * y + p2 * (r2 + 2 * x * x)
    yd = y * radial + p1 * (r2 + 2 * y * y) + 2 * p2 * x * y
    u = (fx * xd + cx) * scale
    v = (fy * yd + cy) * scale
    return u, v, ok


def main() -> None:
    cfg = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    started = datetime.now(timezone.utc).isoformat()
    out_root = Path(cfg["out_root"])
    out_root.mkdir(parents=True, exist_ok=True)
    scale = float(cfg["luminance_scale"])

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

    # strata: outline orientation + interior; plus local slope from ALS z-range
    uniq_cells, inv = np.unique(cell_id, return_inverse=True)
    counts = np.bincount(inv).astype(np.float64)
    cxs = np.bincount(inv, weights=xyz0[:, 0]) / counts
    cys = np.bincount(inv, weights=xyz0[:, 1]) / counts
    zmin = np.full(len(uniq_cells), np.inf)
    zmax = np.full(len(uniq_cells), -np.inf)
    np.minimum.at(zmin, inv, xyz0[:, 2])
    np.maximum.at(zmax, inv, xyz0[:, 2])
    ring = poly_raw.exterior
    ring_len = ring.length
    cell_stratum = {}
    slope_thr = float(cfg["sloped_cell_z_range_m"])
    for u, cx_, cy_, z0, z1 in zip(uniq_cells, cxs, cys, zmin, zmax):
        p = Point(cx_ + official.WORLD_SHIFT[0], cy_ + official.WORLD_SHIFT[1])
        if ring.distance(p) <= 3.0:
            s = ring.project(p)
            p0 = ring.interpolate((s - 0.7) % ring_len)
            p1 = ring.interpolate((s + 0.7) % ring_len)
            tv = np.asarray([p1.x - p0.x, p1.y - p0.y])
            nv = np.linalg.norm(tv)
            ty = abs(tv[1] / nv) if nv > 1e-9 else 0.0
            cell_stratum[int(u)] = "edge_perp" if ty >= 0.7 else "edge_other"
        else:
            cell_stratum[int(u)] = "interior_sloped" if (z1 - z0) >= slope_thr \
                else "interior_flat"

    # used views + luminance cache (half-res uint8)
    lums, view_geo = {}, {}
    for nm in names:
        pose = poses[nm]
        cam = cams[pose["cam"]]
        R, t = quat_to_R(pose["q"]), pose["t"]
        d_c = float((centroid @ R.T + t)[2])
        if d_c <= 0.1:
            continue
        px_per_m = float(cam["params"][0] / d_c)
        if px_per_m < float(cfg["min_px_per_m"]):
            continue
        g = cv2.cvtColor(cv2.imread(str(Path(cfg["image_cache"]) / nm)), cv2.COLOR_BGR2GRAY)
        g = cv2.resize(g, (int(g.shape[1] * scale), int(g.shape[0] * scale)),
                       interpolation=cv2.INTER_AREA)
        lums[nm] = g
        view_geo[nm] = {"R": R, "t": t, "cam": cam,
                        "center": -R.T @ t, "depth": d_c}

    used = sorted(lums)
    pairs = []
    for a, b in combinations(used, 2):
        bz = float(np.linalg.norm(view_geo[a]["center"] - view_geo[b]["center"])) \
            / max(view_geo[a]["depth"], view_geo[b]["depth"])
        if cfg["pair_bz_min"] <= bz <= cfg["pair_bz_max"]:
            pairs.append((a, b, round(bz, 3)))
    pairs.sort(key=lambda p: -p[2])
    pairs = pairs[: int(cfg["max_pairs"])]
    if len(pairs) < 5:
        raise RuntimeError(f"only {len(pairs)} usable pairs")

    deltas = [float(d) for d in cfg["deltas_east_m"]]
    min_pts = int(cfg["min_points_per_cell_pair"])
    min_pairs = int(cfg["min_pairs_per_cell"])
    acc = {str(d): {} for d in deltas}
    for d in deltas:
        xyz = xyz0 + np.asarray([d, 0.0, 0.0])
        proj = {}
        for nm in used:
            g = view_geo[nm]
            u, v, ok = project_points(xyz, g["R"], g["t"], g["cam"], scale)
            h, w = lums[nm].shape
            inside = ok & (u >= 0) & (u < w - 1) & (v >= 0) & (v < h - 1)
            lum = np.zeros(len(xyz), np.float32)
            ui, vi = u[inside].astype(int), v[inside].astype(int)
            lum[inside] = lums[nm][vi, ui]
            proj[nm] = (inside, lum)
        a_d = acc[str(d)]
        for a, b, _bz in pairs:
            ia, la = proj[a]
            ib, lb = proj[b]
            both = ia & ib
            cells = cell_id[both]
            la_, lb_ = la[both], lb[both]
            order = np.argsort(cells, kind="mergesort")
            cells_s, la_s, lb_s = cells[order], la_[order], lb_[order]
            bounds = np.r_[0, np.flatnonzero(cells_s[1:] != cells_s[:-1]) + 1, len(cells_s)]
            for i0, i1 in zip(bounds[:-1], bounds[1:]):
                if i1 - i0 < min_pts:
                    continue
                x, y = la_s[i0:i1], lb_s[i0:i1]
                if x.std() < 1e-6 or y.std() < 1e-6:
                    continue
                a_d.setdefault(int(cells_s[i0]), []).append(
                    float(np.corrcoef(x, y)[0, 1]))

    results = {d: {cid: float(np.median(v)) for cid, v in cd.items()
                   if len(v) >= min_pairs} for d, cd in acc.items()}
    base_key = str(deltas[0])
    summary = {"views_used": len(used), "pairs_used": len(pairs),
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
    best = max([summary["auc"].get(gate_d) or 0.0] + gate_vals) if gate_vals else summary["auc"].get(gate_d)
    summary["validity_gate"] = {"delta_m": float(cfg["validity_gate_delta"]),
                                "best_auc": best,
                                "passed": bool(best is not None and best >= 0.75)}

    (out_root / "cell_scores.json").write_text(
        json.dumps({"schema": "phd_judge_trial_act1_photoconsistency_scores_v1",
                    "results": results}, ensure_ascii=False), encoding="utf-8")
    receipt = {
        "schema": "phd_judge_trial_act1_photoconsistency_receipt_v1",
        "task_id": cfg["task_id"],
        "started_at": started,
        "ended_at": datetime.now(timezone.utc).isoformat(),
        "config_sha256": hashlib.sha256(json.dumps(cfg, sort_keys=True).encode()).hexdigest(),
        "signal": "multi-view photometric consistency of hypothesis points "
                  "(per-cell Pearson across view pairs) — the joint-optimization photo-loss proxy",
        "als_sources": als_rows,
        "roof_points": int(len(xyz0)),
        "pairs": [{"a": a, "b": b, "bz": bz} for a, b, bz in pairs],
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
