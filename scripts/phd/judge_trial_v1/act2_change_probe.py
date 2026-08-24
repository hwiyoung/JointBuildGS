"""판정전 2막 — 변화-주입 통제 실험 (CPU, 1막 v5-④ 측정기 재사용).

Pre-registration: JUDGE_TRIAL_PREREG_ko_v1.md §3 (2026-08-24 확정): 4 blind-
deterministic C-tier sufficient-layer targets (top footprint area); three prior
deformations — uplift(east half z+3.0), demolish(west half z→ground q05),
gable(whole patch replaced by N-S ridge profile, amp +2.0); instrument = the
act-1 v5-④ multi-view photoconsistency judge (cell-plane 0.15 m dense grid,
full-res bilinear luminance, Fisher-z over baseline-band pairs); views are
auto-selected per target from the sealed full-scene triangulated model
(px/m ≥ 8, top 24). Readout per building×deform: within-run AUC (deformed vs
untouched cells), paired drop vs intact run, localization IoU at the intact-run
5% quantile threshold. Gate: ≥1 deform type with deformed-region AUC ≥ 0.75.

Judge is image-only; deformed priors are synthetic (NOT a real ALS lineage).
scientific_verdict: null.
"""

from __future__ import annotations

import hashlib
import json
import struct
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
from scripts.phd.judge_trial_v1.act1_photoconsistency_probe import project_points  # noqa: E402
from scripts.phd.judge_trial_v1.act1_photoconsistency_v2 import bilinear  # noqa: E402
from shapely import contains_xy  # noqa: E402
from shapely.geometry import shape  # noqa: E402


def read_all_images_bin(path: Path) -> dict:
    out = {}
    with open(path, "rb") as f:
        n = struct.unpack("<Q", f.read(8))[0]
        for _ in range(n):
            _iid = struct.unpack("<i", f.read(4))[0]
            q = struct.unpack("<dddd", f.read(32))
            t = struct.unpack("<ddd", f.read(24))
            cam = struct.unpack("<i", f.read(4))[0]
            name = b""
            while True:
                c = f.read(1)
                if c == b"\x00":
                    break
                name += c
            n2 = struct.unpack("<Q", f.read(8))[0]
            f.seek(24 * n2, 1)
            out[name.decode()] = {"q": np.asarray(q), "t": np.asarray(t), "cam": cam}
    return out


def deform(xyz: np.ndarray, kind: str, cx: float, ground_z: float,
           amp_uplift: float, amp_gable: float) -> tuple[np.ndarray, np.ndarray]:
    """Return deformed copy + boolean mask of deformed points (XY unchanged)."""
    out = xyz.copy()
    if kind == "intact":
        return out, np.zeros(len(xyz), bool)
    if kind == "uplift":
        m = xyz[:, 0] >= cx
        out[m, 2] += amp_uplift
        return out, m
    if kind == "demolish":
        m = xyz[:, 0] < cx
        out[m, 2] = ground_z
        return out, m
    if kind == "gable":
        half = max(1.0, float(np.percentile(np.abs(xyz[:, 0] - cx), 95)))
        base = float(np.median(xyz[:, 2]))
        out[:, 2] = base + amp_gable * np.clip(1 - np.abs(xyz[:, 0] - cx) / half, 0, 1)
        return out, np.ones(len(xyz), bool)
    raise ValueError(kind)


def densify(xyz: np.ndarray, cell: float, step: float, jump_thr: float):
    cid = (np.floor(xyz[:, 0] / cell).astype(np.int64) << 32) \
        + np.floor(xyz[:, 1] / cell).astype(np.int64)
    uniq, inv = np.unique(cid, return_inverse=True)
    pts, cids = [], []
    for ci, u in enumerate(uniq):
        p = xyz[inv == ci]
        if len(p) < 5:
            continue
        fit = p
        if p[:, 2].max() - p[:, 2].min() > jump_thr:
            fit = p[p[:, 2] >= np.median(p[:, 2])]
            if len(fit) < 5:
                continue
        A = np.column_stack([fit[:, 0], fit[:, 1], np.ones(len(fit))])
        try:
            coef, *_ = np.linalg.lstsq(A, fit[:, 2], rcond=None)
        except np.linalg.LinAlgError:
            continue
        ix = np.int64(u) >> 32
        iy = np.int64(u) - (ix << 32)
        gx = np.arange(ix * cell + step / 2, (ix + 1) * cell, step)
        gy = np.arange(iy * cell + step / 2, (iy + 1) * cell, step)
        GX, GY = np.meshgrid(gx, gy)
        GZ = coef[0] * GX + coef[1] * GY + coef[2]
        pts.append(np.column_stack([GX.ravel(), GY.ravel(), GZ.ravel()]))
        cids.append(np.full(GX.size, u, np.int64))
    return np.concatenate(pts), np.concatenate(cids)


def score_run(X, C, views, lums, pairs, min_pts, min_pairs):
    uniq, comp = np.unique(C, return_inverse=True)
    n_cells = len(uniq)
    proj = {}
    for nm, g in views.items():
        u, v, ok = project_points(X, g["R"], g["t"], g["cam"], 1.0)
        h, w = lums[nm].shape
        inside = ok & (u >= 0) & (u < w - 2) & (v >= 0) & (v < h - 2)
        lum = np.zeros(len(X), np.float32)
        lum[inside] = bilinear(lums[nm], u[inside], v[inside])
        proj[nm] = (inside, lum)
    zsum = np.zeros(n_cells)
    zcnt = np.zeros(n_cells, np.int64)
    for a, b, _ in pairs:
        ia, la = proj[a]
        ib, lb = proj[b]
        both = ia & ib
        cb = comp[both]
        x, y = la[both], lb[both]
        n = np.bincount(cb, minlength=n_cells).astype(np.float64)
        sx = np.bincount(cb, weights=x, minlength=n_cells)
        sy = np.bincount(cb, weights=y, minlength=n_cells)
        sxx = np.bincount(cb, weights=x * x, minlength=n_cells)
        syy = np.bincount(cb, weights=y * y, minlength=n_cells)
        sxy = np.bincount(cb, weights=x * y, minlength=n_cells)
        with np.errstate(invalid="ignore", divide="ignore"):
            cov = sxy - sx * sy / np.maximum(n, 1)
            vx = sxx - sx * sx / np.maximum(n, 1)
            vy = syy - sy * sy / np.maximum(n, 1)
            r = cov / np.sqrt(vx * vy)
        good = (n >= min_pts) & np.isfinite(r) & (vx > 1e-3) & (vy > 1e-3)
        idx = np.flatnonzero(good)
        zsum[idx] += np.arctanh(np.clip(r[idx], -0.999, 0.999))
        zcnt[idx] += 1
    ok_c = zcnt >= min_pairs
    return {int(uniq[i]): float(np.tanh(zsum[i] / zcnt[i])) for i in np.flatnonzero(ok_c)}


def main() -> None:
    cfg = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    started = datetime.now(timezone.utc).isoformat()
    out_root = Path(cfg["out_root"])
    out_root.mkdir(parents=True, exist_ok=True)
    cache = Path(cfg["image_cache"])
    cache.mkdir(parents=True, exist_ok=True)

    model = Path(cfg["triangulated_model"])
    cams = read_cameras_bin(model / "cameras.bin")
    poses = read_all_images_bin(model / "images.bin")

    fps = {f["properties"].get("stable_id") or f["properties"].get("gml_id"): f["geometry"]
           for f in json.loads(Path(cfg["footprints_geojson"]).read_text())["features"]}

    zf = zipfile.ZipFile(cfg["raw_images_zip"])
    zmap = {Path(n).name: n for n in zf.namelist() if n.upper().endswith(".JPG")}

    kinds = ("intact", "uplift", "demolish", "gable")
    all_out = {}
    for sid in cfg["targets"]:
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
        if len(roof) < 500:
            all_out[sid] = {"skipped": f"roof points {len(roof)}"}
            continue
        centroid = roof.mean(axis=0)
        cx = float(centroid[0])

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
            ppm = fx / float(c[2])
            if ppm >= float(cfg["min_px_per_m"]):
                cand.append((nm, ppm, R, t, cam))
        cand.sort(key=lambda r: -r[1])
        cand = cand[: int(cfg["max_views"])]
        if len(cand) < 6:
            all_out[sid] = {"skipped": f"views {len(cand)}"}
            continue
        views, lums = {}, {}
        for nm, ppm, R, t, cam in cand:
            dst = cache / nm
            if not dst.exists():
                dst.write_bytes(zf.read(zmap[nm]))
            g = cv2.cvtColor(cv2.imread(str(dst)), cv2.COLOR_BGR2GRAY)
            lums[nm] = g.astype(np.float32)
            views[nm] = {"R": R, "t": t, "cam": cam, "center": -R.T @ t,
                         "depth": float((centroid @ R.T + t)[2]), "px_per_m": ppm}
        pairs = []
        for a, b in combinations(sorted(views), 2):
            bz = float(np.linalg.norm(views[a]["center"] - views[b]["center"])) \
                / max(views[a]["depth"], views[b]["depth"])
            if cfg["pair_bz_min"] <= bz <= cfg["pair_bz_max"]:
                pairs.append((a, b, round(bz, 3)))
        pairs.sort(key=lambda p: -p[2])
        pairs = pairs[: int(cfg["max_pairs"])]

        cell = float(cfg["cell_m"])
        runs, deformed_cells = {}, {}
        for kind in kinds:
            pts, dmask = deform(roof, kind, cx, ground_z,
                                float(cfg["uplift_m"]), float(cfg["gable_amp_m"]))
            X, C = densify(pts, cell, float(cfg["dense_sample_m"]),
                           float(cfg["jump_cell_z_range_m"]))
            runs[kind] = score_run(X, C, views, lums, pairs,
                                   int(cfg["min_points_per_cell_pair"]),
                                   int(cfg["min_pairs_per_cell"]))
            dcid = (np.floor(roof[dmask, 0] / cell).astype(np.int64) << 32) \
                + np.floor(roof[dmask, 1] / cell).astype(np.int64)
            deformed_cells[kind] = set(int(v) for v in np.unique(dcid))

        intact = runs["intact"]
        if not intact:
            all_out[sid] = {"skipped": "no intact-scored cells (baseline unreliable)"}
            continue
        tau = float(np.quantile(np.asarray(list(intact.values())), 0.05))
        b_out = {"n_views": len(views), "n_pairs": len(pairs),
                 "px_per_m_max": round(cand[0][1], 1),
                 "n_cells_intact": len(intact), "tau_q05_intact": round(tau, 4),
                 "kinds": {}}
        for kind in kinds[1:]:
            run = runs[kind]
            dset = deformed_cells[kind]
            common = sorted(set(run) & set(intact))
            din = [c for c in common if c in dset]
            dout = [c for c in common if c not in dset]
            row = {"n_deformed_cells": len(din), "n_untouched_cells": len(dout)}
            if len(din) >= 10 and len(dout) >= 10:
                s_def = np.asarray([run[c] for c in din])
                s_unt = np.asarray([run[c] for c in dout])
                row["auc_within_run"] = round(auc_shifted_detect(s_unt, s_def, False), 4)
                row["med_deformed"] = round(float(np.median(s_def)), 3)
                row["med_untouched"] = round(float(np.median(s_unt)), 3)
            if din:
                drop = [run[c] - intact[c] for c in din if c in intact]
                row["paired_drop_med_deformed"] = round(float(np.median(drop)), 3) if drop else None
                flagged = {c for c in common if run[c] < tau}
                inter = len(flagged & set(din))
                union = len(flagged | set(din))
                row["iou_flag_vs_deformed"] = round(inter / union, 3) if union else None
                row["flagged_n"] = len(flagged)
            b_out["kinds"][kind] = row
        all_out[sid] = b_out
        (out_root / f"{sid}_cell_scores.json").write_text(
            json.dumps({"runs": runs,
                        "deformed_cells": {k: sorted(v) for k, v in deformed_cells.items()}},
                       ensure_ascii=False), encoding="utf-8")

    aucs = [row.get("auc_within_run") for b in all_out.values() if "kinds" in b
            for row in b["kinds"].values() if row.get("auc_within_run") is not None]
    gate = {"rule": ">=1 deform type with deformed-region AUC >= 0.75",
            "best_auc": max(aucs) if aucs else None,
            "passed": bool(aucs and max(aucs) >= 0.75)}
    receipt = {
        "schema": "phd_judge_trial_act2_change_receipt_v1",
        "task_id": cfg["task_id"],
        "started_at": started, "ended_at": datetime.now(timezone.utc).isoformat(),
        "config_sha256": hashlib.sha256(json.dumps(cfg, sort_keys=True).encode()).hexdigest(),
        "pre_registration": "JUDGE_TRIAL_PREREG_ko_v1.md §3 (2026-08-24 confirmed)",
        "deformation": {"uplift_m": cfg["uplift_m"], "gable_amp_m": cfg["gable_amp_m"],
                        "synthetic": True, "not_real_als_lineage": True},
        "buildings": all_out, "validity_gate": gate,
        "scientific_verdict": None,
    }
    (out_root / "receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"gate": gate,
                      "buildings": {s: {k: {kk: vv for kk, vv in r.items()
                                            if kk in ("auc_within_run", "med_deformed",
                                                      "med_untouched", "iou_flag_vs_deformed",
                                                      "paired_drop_med_deformed")}
                                        for k, r in b.get("kinds", {}).items()}
                                    for s, b in all_out.items()}},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
