"""판정전(JUDGE trial) 1막 — 오차-주입 코리도 파일럿 (통제 실험, CPU).

Pre-registration: docs/experiments/phd/verification_trial_v1/JUDGE_TRIAL_PREREG_ko_v1.md §2.
Question: does render-vs-image agreement carry a δ-misalignment signal that the
cheap 3D residual channel (pre-measured near-blind: C2C AUC 0.573 @δ0.25, flat-roof
dS≈0.001) does not?

Design: raw registered ALS points (scene-local, with intensity) are translated by a
known δ east, z-buffer-projected into the sealed 55-view corridor cameras, and
scored per 1 m world cell (cell identity from UNSHIFTED coordinates so the same
physical patch is compared across δ):

  edge      — image-edge strength sampled at prior silhouette/discontinuity pixels
              (image-only judge; registration confidence forced to 1.0 so no 3D
              gate signal leaks into the judge)
  intensity — Pearson r between rendered ALS intensity and image luminance (2 m cells)
  depth3d   — |prior depth − MVS depth| median (the cheap-3D baseline, comparison only)

Readout: per-δ AUC (Mann-Whitney) of each channel separating δ=0 vs δ=d cell
populations + paired degradation share, stratified boundary/interior.
scientific_verdict: null. Synthetic-δ products are NOT a real ALS lineage.
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np
import yaml

REPO = Path("/workspace/JointBuildGS")
sys.path.insert(0, str(REPO))

from scripts.p2.c4_existing_als_v1 import prepare_prior as official  # noqa: E402
from src.stage2.dataloader import ColmapDataset  # noqa: E402

import laspy  # noqa: E402


def load_als_with_intensity(als_root: Path, low: np.ndarray, high: np.ndarray):
    """Mirror official.load_als (same hashes, datum shift, bbox, WORLD_SHIFT)
    but keep per-point intensity."""
    xyz_parts, inten_parts, rows = [], [], []
    for name, expected in official.ALS_HASHES.items():
        path = als_root / name
        actual = official.digest(path)
        if actual != expected:
            raise RuntimeError(f"raw ALS hash drift: {name} {actual}")
        selected = 0
        with laspy.open(path) as reader:
            for chunk in reader.chunk_iterator(2_000_000):
                x = np.asarray(chunk.x)
                y = np.asarray(chunk.y)
                z = np.asarray(chunk.z) + official.ALS_DATUM_SHIFT_M
                keep = (x >= low[0]) & (x <= high[0]) & (y >= low[1]) & (y <= high[1])
                if bool(keep.any()):
                    xyz_parts.append(np.column_stack((x[keep], y[keep], z[keep])) - official.WORLD_SHIFT)
                    inten_parts.append(np.asarray(chunk.intensity)[keep].astype(np.float32))
                    selected += int(keep.sum())
        rows.append({"path": str(path), "sha256": actual, "scene_selected_point_count": selected})
    if not xyz_parts:
        raise RuntimeError("no ALS points in corridor bounds")
    return np.concatenate(xyz_parts), np.concatenate(inten_parts), rows


def pool_max(a: np.ndarray, p: int) -> np.ndarray:
    h, w = (a.shape[0] // p) * p, (a.shape[1] // p) * p
    return a[:h, :w].reshape(h // p, p, w // p, p).max(axis=(1, 3))


def project_pooled(xyz: np.ndarray, k: np.ndarray, w2c: np.ndarray,
                   hp: int, wp: int, pool: int):
    """Z-buffer at pooled resolution; returns flat pooled pixel ids and winner
    point indices (needed for cell/intensity attribution — the sealed
    project_view does not expose winners, so this mirrors its z-buffer rule)."""
    cam = xyz @ w2c[:3, :3].T + w2c[:3, 3]
    front = cam[:, 2] > 0.1
    uvw = cam[front] @ k.T
    uv = uvw[:, :2] / uvw[:, 2:3]
    px = np.floor(uv[:, 0] / pool).astype(np.int64)
    py = np.floor(uv[:, 1] / pool).astype(np.int64)
    inside = (px >= 0) & (px < wp) & (py >= 0) & (py < hp)
    idx_front = np.flatnonzero(front)[inside]
    if not len(idx_front):
        return np.empty(0, np.int64), np.empty(0, np.int64), np.empty(0, np.float32)
    key = py[inside] * wp + px[inside]
    depth = cam[idx_front, 2]
    order = np.lexsort((depth, key))
    sk = key[order]
    first = np.r_[True, sk[1:] != sk[:-1]]
    return sk[first], idx_front[order[first]], depth[order[first]].astype(np.float32)


def rankdata(a: np.ndarray) -> np.ndarray:
    order = np.argsort(a, kind="mergesort")
    ranks = np.empty(len(a), dtype=np.float64)
    ranks[order] = np.arange(1, len(a) + 1)
    vals = a[order]
    i = 0
    while i < len(vals):
        j = i
        while j + 1 < len(vals) and vals[j + 1] == vals[i]:
            j += 1
        if j > i:
            ranks[order[i:j + 1]] = (i + j + 2) / 2.0
        i = j + 1
    return ranks


def auc_shifted_detect(s0: np.ndarray, sd: np.ndarray, higher_means_shifted: bool) -> float:
    """AUC of the score separating shifted (positive) from unshifted cells."""
    scores = np.concatenate([sd, s0])
    if not higher_means_shifted:
        scores = -scores
    r = rankdata(scores)
    n1, n0 = len(sd), len(s0)
    return float((r[:n1].sum() - n1 * (n1 + 1) / 2.0) / (n1 * n0))


def main() -> None:
    cfg = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    started = datetime.now(timezone.utc).isoformat()
    pool = int(cfg["pool_px"])
    out_root = Path(cfg["out_root"])
    out_root.mkdir(parents=True, exist_ok=True)

    base = yaml.safe_load((REPO / cfg["base_yaml"]).read_text())
    base.update(yaml.safe_load((REPO / cfg["fused_yaml"]).read_text())["overrides"])
    names = list(base["visible_views"])
    assert len(names) == 55, "frozen 55-view roles drifted"
    dataset = ColmapDataset(base["data_root"], downscale=1.0, load_depth=True,
                            load_normal=False, load_semantic=False, visible_views=names)
    seed = dataset.points_xyz.astype(np.float64)
    low = np.quantile(seed[:, :2], 0.001, axis=0) + official.WORLD_SHIFT[:2] - 10.0
    high = np.quantile(seed[:, :2], 0.999, axis=0) + official.WORLD_SHIFT[:2] + 10.0
    xyz0, inten, als_rows = load_als_with_intensity(Path(cfg["als_root"]), low, high)

    # v2: judge only the pre-registered unit — the prior patch on the target
    # building (footprint + buffer). Scene-wide scoring (v1) diluted the signal
    # with ground/vegetation cells and is kept as a negative control payload.
    # Note: rendering the patch alone ignores occlusion by surrounding
    # structures — acceptable for this corridor pilot, recorded here.
    from shapely import contains_xy
    from shapely.geometry import shape

    feat = json.loads(Path(cfg["footprint_geojson"]).read_text(encoding="utf-8"))["features"][0]
    poly_raw = shape(feat["geometry"])
    poly = poly_raw.buffer(float(cfg["footprint_buffer_m"]))
    world_xy = xyz0[:, :2] + official.WORLD_SHIFT[:2]
    keep = contains_xy(poly, world_xy[:, 0], world_xy[:, 1])
    if keep.sum() < 1000:
        raise RuntimeError(f"footprint patch too small: {int(keep.sum())} points")
    xyz0, inten = xyz0[keep], inten[keep]
    inten_n = (inten - inten.min()) / max(1.0, float(inten.max() - inten.min()))

    cell = float(cfg["cell_m"])
    cell_i = float(cfg["cell_intensity_m"])
    cell_id = (np.floor(xyz0[:, 0] / cell).astype(np.int64) << 32) \
        + np.floor(xyz0[:, 1] / cell).astype(np.int64)
    cell_id_i = (np.floor(xyz0[:, 0] / cell_i).astype(np.int64) << 32) \
        + np.floor(xyz0[:, 1] / cell_i).astype(np.int64)

    # Boundary-orientation strata: an eastward δ slides tangentially along
    # east-west outline segments (in-plane non-observability, 2D analogue) —
    # only δ-perpendicular boundary cells can carry edge signal. Classify each
    # 1 m cell by the local outline tangent at its nearest ring point.
    from shapely.geometry import Point
    uniq_cells, inv = np.unique(cell_id, return_inverse=True)
    counts = np.bincount(inv).astype(np.float64)
    cxs = np.bincount(inv, weights=xyz0[:, 0]) / counts
    cys = np.bincount(inv, weights=xyz0[:, 1]) / counts
    ring = poly_raw.exterior
    ring_len = ring.length
    cell_stratum = {}
    for u, cx, cy in zip(uniq_cells, cxs, cys):
        p = Point(cx + official.WORLD_SHIFT[0], cy + official.WORLD_SHIFT[1])
        if ring.distance(p) > 3.0:
            cell_stratum[int(u)] = "interior"
            continue
        s = ring.project(p)
        p0 = ring.interpolate((s - 0.7) % ring_len)
        p1 = ring.interpolate((s + 0.7) % ring_len)
        t = np.asarray([p1.x - p0.x, p1.y - p0.y])
        n = np.linalg.norm(t)
        ty = abs(t[1] / n) if n > 1e-9 else 0.0  # |tangent_y| = |normal·east|
        cell_stratum[int(u)] = "perp" if ty >= 0.7 else ("para" if ty <= 0.3 else "mid")

    # Per-view image products (δ-invariant): pooled edge strength + luminance + MVS depth.
    views = []
    for vi in range(len(dataset.frames)):
        s = dataset[vi]
        rgb = s["rgb"].numpy()
        gray = (0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]).astype(np.float32)
        # v2: Canny edges + distance transform — score = exp(-d/σ) at prior-edge
        # pixels. The v1 Sobel-magnitude sampling with dilation had an effective
        # tolerance wider than δ=1.0 (3.4 px) and was blind by construction.
        g8 = np.clip(gray * 255.0, 0, 255).astype(np.uint8)
        lo, hi = cfg["canny_thresholds"]
        canny = cv2.Canny(g8, int(lo), int(hi))
        cannyp = pool_max(canny.astype(np.float32), pool) > 0
        dist = cv2.distanceTransform((~cannyp).astype(np.uint8), cv2.DIST_L2, 3)
        escoremap = np.exp(-dist / float(cfg["edge_sigma_px"])).astype(np.float32)
        hp, wp = escoremap.shape
        lump = cv2.resize(gray, (wp, hp), interpolation=cv2.INTER_AREA)
        depth = s["depth"].numpy()
        mask = s["depth_mask"].numpy()
        d = np.where(mask, depth, np.nan)
        dp = cv2.resize(d, (wp, hp), interpolation=cv2.INTER_NEAREST)
        views.append({
            "k": s["K"].numpy().astype(np.float64), "w2c": s["w2c"].numpy().astype(np.float64),
            "hp": hp, "wp": wp, "edge": escoremap, "lum": lump, "mvs": dp,
            "gsd_pooled_m": None, "name": s["name"],
        })

    kernel = np.ones((3, 3), np.uint8)
    close_it = int(cfg["support_closing_iterations"])
    # v4: edge-channel silhouette must be the ROOF outline (the real jump edge
    # in the image), not the boundary of the buffered point apron (ground ring
    # ~2 m off the building edge — v3 defect). Roof = above ground + threshold.
    ground_z = float(np.quantile(xyz0[:, 2], 0.05))
    roof_mask = xyz0[:, 2] > ground_z + float(cfg["roof_above_ground_m"])
    if roof_mask.sum() < 500:
        raise RuntimeError(f"roof subset too small: {int(roof_mask.sum())}")
    off_px = int(cfg["margin_offset_px"])

    results = {}   # delta -> channel -> {cell: [view scores]}
    for delta in cfg["deltas_east_m"]:
        xyz = xyz0 + np.asarray([float(delta), 0.0, 0.0])
        acc = {"edge": {}, "edge_margin": {}, "intensity": {}, "depth3d": {}}
        for v in views:
            key, win, depth = project_pooled(xyz, v["k"], v["w2c"], v["hp"], v["wp"], pool)
            if not len(key):
                continue
            hp, wp = v["hp"], v["wp"]
            if v["gsd_pooled_m"] is None:
                v["gsd_pooled_m"] = float(np.median(depth) / v["k"][0, 0] * pool)
                # image-space direction of a world +east step at the patch (for
                # the margin offsets) — computed once per view
                c0 = xyz0.mean(axis=0)
                cam = np.stack([c0, c0 + [1.0, 0, 0]]) @ v["w2c"][:3, :3].T + v["w2c"][:3, 3]
                uv = (cam @ v["k"].T)
                uv = uv[:, :2] / uv[:, 2:3]
                dvec = (uv[1] - uv[0]) / max(np.linalg.norm(uv[1] - uv[0]), 1e-9)
                v["east_off"] = (int(round(dvec[1] * off_px)), int(round(dvec[0] * off_px)))

            # ---- edge channels on the roof subset ----
            key_r, win_r, depth_r = project_pooled(
                xyz[roof_mask], v["k"], v["w2c"], hp, wp, pool)
            if len(key_r):
                support = np.zeros((hp, wp), np.uint8)
                support.flat[key_r] = 1
                support = cv2.dilate(support, kernel)
                closed = cv2.morphologyEx(support, cv2.MORPH_CLOSE, kernel, iterations=close_it)
                closed = cv2.erode(closed, kernel)
                sil = cv2.morphologyEx(closed, cv2.MORPH_GRADIENT, kernel).astype(bool)
                dmap = np.full((hp, wp), np.nan, np.float32)
                dmap.flat[key_r] = depth_r
                with np.errstate(invalid="ignore"):
                    ddx = np.abs(np.diff(dmap, axis=1, prepend=dmap[:, :1]))
                    ddy = np.abs(np.diff(dmap, axis=0, prepend=dmap[:1, :]))
                disc = (np.nan_to_num(ddx) > cfg["depth_discontinuity_m"]) \
                    | (np.nan_to_num(ddy) > cfg["depth_discontinuity_m"])
                prior_edge = sil | disc

                is_edge_px = prior_edge.flat[key_r]
                cells_r = cell_id[roof_mask][win_r]
                py, px = key_r // wp, key_r % wp
                smap = v["edge"]
                escore = smap[py, px]
                oy, ox = v["east_off"]
                pyp = np.clip(py + oy, 0, hp - 1)
                pxp = np.clip(px + ox, 0, wp - 1)
                pym = np.clip(py - oy, 0, hp - 1)
                pxm = np.clip(px - ox, 0, wp - 1)
                margin = escore - 0.5 * (smap[pyp, pxp] + smap[pym, pxm])
                for cid in np.unique(cells_r[is_edge_px]):
                    m = is_edge_px & (cells_r == cid)
                    if m.sum() >= cfg["min_edge_px_per_cell_view"]:
                        acc["edge"].setdefault(int(cid), []).append(float(escore[m].mean()))
                        acc["edge_margin"].setdefault(int(cid), []).append(float(margin[m].mean()))

            lum = v["lum"].flat[key]
            pin = inten_n[win]
            cells_i = cell_id_i[win]
            for cid in np.unique(cells_i):
                m = cells_i == cid
                if m.sum() >= cfg["min_intensity_px_per_cell_view"]:
                    a, b = pin[m], lum[m]
                    if a.std() > 1e-6 and b.std() > 1e-6:
                        acc["intensity"].setdefault(int(cid), []).append(
                            float(np.corrcoef(a, b)[0, 1]))

            mvs = v["mvs"].flat[key]
            ok = np.isfinite(mvs)
            resid = np.abs(depth - mvs)
            cells = cell_id[win]
            for cid in np.unique(cells[ok]):
                m = ok & (cells == cid)
                if m.sum() >= cfg["min_edge_px_per_cell_view"]:
                    acc["depth3d"].setdefault(int(cid), []).append(float(np.median(resid[m])))
        min_views = int(cfg["min_views_per_cell"])
        results[str(delta)] = {
            ch: {cid: float(np.median(v)) for cid, v in d.items() if len(v) >= min_views}
            for ch, d in acc.items()
        }

    # Readout: AUC(δ=0 vs δ=d) per channel on the intersection of defined cells.
    base_key = str(cfg["deltas_east_m"][0])
    summary = {"cells_defined": {d: {ch: len(v) for ch, v in chs.items()}
                                 for d, chs in results.items()},
               "gsd_pooled_m_median": float(np.median([v["gsd_pooled_m"] for v in views
                                                       if v["gsd_pooled_m"]])),
               "auc": {}, "paired_worse_share": {}}
    higher_shifted = {"edge": False, "edge_margin": False,
                      "intensity": False, "depth3d": True}
    for d in cfg["deltas_east_m"][1:]:
        dk = str(d)
        summary["auc"][dk] = {}
        summary["paired_worse_share"][dk] = {}
        for ch in ("edge", "edge_margin", "intensity", "depth3d"):
            common = sorted(set(results[base_key][ch]) & set(results[dk][ch]))
            if len(common) < 20:
                summary["auc"][dk][ch] = None
                continue
            s0 = np.asarray([results[base_key][ch][c] for c in common])
            sd = np.asarray([results[dk][ch][c] for c in common])
            summary["auc"][dk][ch] = round(auc_shifted_detect(s0, sd, higher_shifted[ch]), 4)
            worse = (sd > s0) if higher_shifted[ch] else (sd < s0)
            summary["paired_worse_share"][dk][ch] = {
                "n_cells": len(common), "share": round(float(worse.mean()), 4)}
            if ch in ("edge", "edge_margin"):
                strata = {}
                for name in ("perp", "para", "mid", "interior"):
                    sel = [i for i, c in enumerate(common) if cell_stratum.get(c) == name]
                    if len(sel) >= 15:
                        strata[name] = {
                            "n": len(sel),
                            "auc": round(auc_shifted_detect(s0[sel], sd[sel], False), 4),
                            "worse_share": round(float(
                                (sd[sel] < s0[sel]).mean()), 4),
                        }
                    else:
                        strata[name] = {"n": len(sel), "auc": None}
                summary.setdefault(f"{ch}_orientation_strata", {})[dk] = strata

    (out_root / "cell_scores.json").write_text(
        json.dumps({"schema": "phd_judge_trial_act1_cell_scores_v1",
                    "results": results}, ensure_ascii=False), encoding="utf-8")
    receipt = {
        "schema": "phd_judge_trial_act1_receipt_v1",
        "task_id": cfg["task_id"],
        "started_at": started,
        "ended_at": datetime.now(timezone.utc).isoformat(),
        "config_sha256": hashlib.sha256(
            json.dumps(cfg, sort_keys=True).encode()).hexdigest(),
        "als_sources": als_rows,
        "raw_scene_point_count": int(len(xyz0)),
        "view_count": len(views),
        "delta_injection": {"deltas_east_m": cfg["deltas_east_m"], "synthetic": True,
                            "not_real_als_lineage": True},
        "judge_is_image_only": "registration/MVS gates excluded from edge & intensity channels",
        "summary": summary,
        "scientific_verdict": None,
    }
    (out_root / "receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
