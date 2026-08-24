"""판정전 1막 v5-① — 풀해상도 오차-주입 검정 (해상도 변수 분리, CPU).

The crop-rig pilot (act1_delta_probe) died of resolution: effective 0.29 m/px
put δ ≤ 1 m at/below one pixel and the δ=4 m validity control was invisible
(zero statistical power — ACT1_PILOT_READOUT_ko_v1.md). This probe removes ONLY
the resolution variable: raw 5280×3956 originals + the sealed full-resolution
triangulated model (FULL_OPENCV; same scene-local frame as the crop rig,
verified by exact camera-center agreement), applying lens distortion on the
projection side so no new image derivative is created (raw stays immutable;
views are cached read-only).

Validity gate first: δ=4 m must separate before any fine-δ reading. Judge is
image-only. scientific_verdict: null; all δ products synthetic.
"""

from __future__ import annotations

import hashlib
import json
import struct
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np
import yaml

REPO = Path("/workspace/JointBuildGS")
sys.path.insert(0, str(REPO))
from scripts.p2.c4_existing_als_v1 import prepare_prior as official  # noqa: E402
from scripts.phd.judge_trial_v1.act1_delta_probe import (  # noqa: E402
    auc_shifted_detect, load_als_with_intensity)
from shapely import contains_xy  # noqa: E402
from shapely.geometry import Point, shape  # noqa: E402


def read_cameras_bin(path: Path) -> dict:
    n_params = {0: 3, 1: 4, 2: 4, 3: 5, 4: 8, 5: 8, 6: 12}
    cams = {}
    with open(path, "rb") as f:
        n = struct.unpack("<Q", f.read(8))[0]
        for _ in range(n):
            cid, model, w, h = struct.unpack("<iiQQ", f.read(24))
            params = struct.unpack("<" + "d" * n_params[model], f.read(8 * n_params[model]))
            cams[cid] = {"model": model, "w": int(w), "h": int(h), "params": params}
    return cams


def read_images_bin(path: Path, wanted: set[str]) -> dict:
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
            nm = name.decode()
            if nm in wanted:
                out[nm] = {"q": np.asarray(q), "t": np.asarray(t), "cam": cam}
    return out


def quat_to_R(q: np.ndarray) -> np.ndarray:
    w, x, y, z = q
    return np.asarray([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def project_full_opencv(xyz: np.ndarray, R: np.ndarray, t: np.ndarray, cam: dict):
    """world(scene-local)→raw distorted pixel via FULL_OPENCV; z-buffer winners."""
    fx, fy, cx, cy, k1, k2, p1, p2, k3, k4, k5, k6 = cam["params"]
    c = xyz @ R.T + t
    front = c[:, 2] > 0.1
    x = c[front, 0] / c[front, 2]
    y = c[front, 1] / c[front, 2]
    r2 = x * x + y * y
    radial = (1 + k1 * r2 + k2 * r2 ** 2 + k3 * r2 ** 3) \
        / (1 + k4 * r2 + k5 * r2 ** 2 + k6 * r2 ** 3)
    xd = x * radial + 2 * p1 * x * y + p2 * (r2 + 2 * x * x)
    yd = y * radial + p1 * (r2 + 2 * y * y) + 2 * p2 * x * y
    u = fx * xd + cx
    v = fy * yd + cy
    w, h = cam["w"], cam["h"]
    px = np.floor(u).astype(np.int64)
    py = np.floor(v).astype(np.int64)
    inside = (px >= 0) & (px < w) & (py >= 0) & (py < h)
    idx = np.flatnonzero(front)[inside]
    if not len(idx):
        return (np.empty(0, np.int64),) * 2 + (np.empty(0, np.float32),)
    key = py[inside] * w + px[inside]
    depth = c[idx, 2]
    order = np.lexsort((depth, key))
    sk = key[order]
    first = np.r_[True, sk[1:] != sk[:-1]]
    return sk[first], idx[order[first]], depth[order[first]].astype(np.float32)


def main() -> None:
    cfg = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    started = datetime.now(timezone.utc).isoformat()
    out_root = Path(cfg["out_root"])
    out_root.mkdir(parents=True, exist_ok=True)
    cache = Path(cfg["image_cache"])
    cache.mkdir(parents=True, exist_ok=True)

    base = yaml.safe_load((REPO / cfg["base_yaml"]).read_text())
    base.update(yaml.safe_load((REPO / cfg["fused_yaml"]).read_text())["overrides"])
    names = list(base["visible_views"])
    assert len(names) == 55

    model = Path(cfg["triangulated_model"])
    cams = read_cameras_bin(model / "cameras.bin")
    poses = read_images_bin(model / "images.bin", set(names))
    if len(poses) != 55:
        raise RuntimeError(f"triangulated poses found for {len(poses)}/55 views")

    with zipfile.ZipFile(cfg["raw_images_zip"]) as z:
        zmap = {Path(n).name: n for n in z.namelist() if n.upper().endswith(".JPG")}
        for nm in names:
            dst = cache / nm
            if not dst.exists():
                dst.write_bytes(z.read(zmap[nm]))

    feat = json.loads(Path(cfg["footprint_geojson"]).read_text(encoding="utf-8"))["features"][0]
    poly_raw = shape(feat["geometry"])
    poly = poly_raw.buffer(float(cfg["footprint_buffer_m"]))
    bx = poly.bounds
    low = np.asarray([bx[0] - 20.0, bx[1] - 20.0])
    high = np.asarray([bx[2] + 20.0, bx[3] + 20.0])
    xyz0, inten, als_rows = load_als_with_intensity(Path(cfg["als_root"]), low, high)
    wxy = xyz0[:, :2] + official.WORLD_SHIFT[:2]
    keep = contains_xy(poly, wxy[:, 0], wxy[:, 1])
    xyz0, inten = xyz0[keep], inten[keep]
    inten_n = (inten - inten.min()) / max(1.0, float(inten.max() - inten.min()))
    ground_z = float(np.quantile(xyz0[:, 2], 0.05))
    roof_mask = xyz0[:, 2] > ground_z + float(cfg["roof_above_ground_m"])
    centroid = xyz0.mean(axis=0)

    cell = float(cfg["cell_m"])
    cell_i = float(cfg["cell_intensity_m"])
    cell_id = (np.floor(xyz0[:, 0] / cell).astype(np.int64) << 32) \
        + np.floor(xyz0[:, 1] / cell).astype(np.int64)
    cell_id_i = (np.floor(xyz0[:, 0] / cell_i).astype(np.int64) << 32) \
        + np.floor(xyz0[:, 1] / cell_i).astype(np.int64)

    # orientation strata (δ ⟂/∥ outline; interior)
    uniq_cells, inv = np.unique(cell_id, return_inverse=True)
    counts = np.bincount(inv).astype(np.float64)
    cxs = np.bincount(inv, weights=xyz0[:, 0]) / counts
    cys = np.bincount(inv, weights=xyz0[:, 1]) / counts
    ring = poly_raw.exterior
    ring_len = ring.length
    cell_stratum = {}
    for u, cx_, cy_ in zip(uniq_cells, cxs, cys):
        p = Point(cx_ + official.WORLD_SHIFT[0], cy_ + official.WORLD_SHIFT[1])
        if ring.distance(p) > 3.0:
            cell_stratum[int(u)] = "interior"
            continue
        s = ring.project(p)
        p0 = ring.interpolate((s - 0.7) % ring_len)
        p1 = ring.interpolate((s + 0.7) % ring_len)
        tv = np.asarray([p1.x - p0.x, p1.y - p0.y])
        nv = np.linalg.norm(tv)
        ty = abs(tv[1] / nv) if nv > 1e-9 else 0.0
        cell_stratum[int(u)] = "perp" if ty >= 0.7 else ("para" if ty <= 0.3 else "mid")

    kernel = np.ones((3, 3), np.uint8)
    close_it = int(cfg["support_closing_iterations"])
    deltas = [float(d) for d in cfg["deltas_east_m"]]
    acc = {str(d): {"edge": {}, "edge_margin": {}, "intensity": {}} for d in deltas}
    view_rows = []

    for nm in names:
        pose = poses[nm]
        cam = cams[pose["cam"]]
        R = quat_to_R(pose["q"])
        t = pose["t"]
        depth_c = float((centroid @ R.T + t)[2])
        if depth_c <= 0.1:
            view_rows.append({"name": nm, "px_per_m": None, "used": False})
            continue
        px_per_m = float(cam["params"][0] / depth_c)
        used = px_per_m >= float(cfg["min_px_per_m"])
        view_rows.append({"name": nm, "px_per_m": round(px_per_m, 2), "used": used})
        if not used:
            continue

        bgr = cv2.imread(str(cache / nm))
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        lo, hi = cfg["canny_thresholds"]
        canny = cv2.Canny(gray, int(lo), int(hi))
        dist = cv2.distanceTransform((canny == 0).astype(np.uint8), cv2.DIST_L2, 3)
        smap = np.exp(-dist / float(cfg["edge_sigma_px"])).astype(np.float32)
        lum = gray.astype(np.float32) / 255.0
        h, w = gray.shape
        del bgr, canny, dist

        # image-space east direction & margin offset for this view
        pts = np.stack([centroid, centroid + [1.0, 0, 0]])
        cpts = pts @ R.T + t
        fx, fy, cx, cy = cam["params"][:4]
        uv = np.stack([fx * cpts[:, 0] / cpts[:, 2] + cx, fy * cpts[:, 1] / cpts[:, 2] + cy], 1)
        dvec = uv[1] - uv[0]
        dvec = dvec / max(np.linalg.norm(dvec), 1e-9)
        off = max(2, int(round(float(cfg["margin_offset_m"]) * px_per_m)))
        oy, ox = int(round(dvec[1] * off)), int(round(dvec[0] * off))

        # world-radius disk splatting: at 62 px/m the 0.22 m ALS spacing is a
        # 13-px gap — morphology cannot bridge it (v5-① porous-mask finding).
        # Splat radius scales with the view's px/m so the mask is a surface;
        # the same pass paints a compact cell-id map for silhouette attribution.
        r_px = max(2, int(round(float(cfg["splat_radius_m"]) * px_per_m)))
        cells_roof_all = cell_id[roof_mask]
        uniq_roof, compact_all = np.unique(cells_roof_all, return_inverse=True)
        for d in deltas:
            xyz = xyz0 + np.asarray([d, 0.0, 0.0])
            key_r, win_r, depth_r = project_full_opencv(xyz[roof_mask], R, t, cam)
            if not len(key_r):
                continue
            cellmap = np.full((h, w), -1, np.int32)
            pys, pxs = (key_r // w).astype(int), (key_r % w).astype(int)
            cvals = compact_all[win_r]
            for yy, xx, cv_ in zip(pys, pxs, cvals):
                cv2.circle(cellmap, (int(xx), int(yy)), r_px, int(cv_), -1)
            support = (cellmap >= 0).astype(np.uint8)
            closed = cv2.morphologyEx(support, cv2.MORPH_CLOSE, kernel, iterations=close_it)
            sil = cv2.morphologyEx(closed, cv2.MORPH_GRADIENT, kernel).astype(bool) \
                & (cellmap >= 0)
            sy, sx = np.nonzero(sil)
            if not len(sy):
                continue
            sc = cellmap[sy, sx]
            escore = smap[sy, sx]
            syp = np.clip(sy + oy, 0, h - 1)
            sxp = np.clip(sx + ox, 0, w - 1)
            sym = np.clip(sy - oy, 0, h - 1)
            sxm = np.clip(sx - ox, 0, w - 1)
            margin = escore - 0.5 * (smap[syp, sxp] + smap[sym, sxm])
            a = acc[str(d)]
            for ci in np.unique(sc):
                m = sc == ci
                if m.sum() >= cfg["min_edge_px_per_cell_view"]:
                    cid = int(uniq_roof[ci])
                    a["edge"].setdefault(cid, []).append(float(escore[m].mean()))
                    a["edge_margin"].setdefault(cid, []).append(float(margin[m].mean()))

            key_f, win_f, _ = project_full_opencv(xyz, R, t, cam)
            lum_f = lum.flat[key_f]
            pin = inten_n[win_f]
            cells_i = cell_id_i[win_f]
            for cid in np.unique(cells_i):
                m = cells_i == cid
                if m.sum() >= cfg["min_intensity_px_per_cell_view"]:
                    aa, bb = pin[m], lum_f[m]
                    if aa.std() > 1e-6 and bb.std() > 1e-6:
                        a["intensity"].setdefault(int(cid), []).append(
                            float(np.corrcoef(aa, bb)[0, 1]))
        del smap, lum

    min_views = int(cfg["min_views_per_cell"])
    results = {d: {ch: {cid: float(np.median(v)) for cid, v in chd.items()
                        if len(v) >= min_views}
                   for ch, chd in chs.items()}
               for d, chs in acc.items()}

    summary = {
        "views_used": sum(1 for r in view_rows if r["used"]),
        "px_per_m": {r["name"]: r["px_per_m"] for r in view_rows},
        "cells_defined": {d: {ch: len(v) for ch, v in chs.items()} for d, chs in results.items()},
        "auc": {}, "edge_orientation_strata": {}, "edge_margin_orientation_strata": {},
    }
    base_key = str(deltas[0])
    for d in deltas[1:]:
        dk = str(d)
        summary["auc"][dk] = {}
        for ch in ("edge", "edge_margin", "intensity"):
            common = sorted(set(results[base_key][ch]) & set(results[dk][ch]))
            if len(common) < 20:
                summary["auc"][dk][ch] = None
                continue
            s0 = np.asarray([results[base_key][ch][c] for c in common])
            sd = np.asarray([results[dk][ch][c] for c in common])
            summary["auc"][dk][ch] = round(auc_shifted_detect(s0, sd, False), 4)
            if ch in ("edge", "edge_margin"):
                strata = {}
                for name_ in ("perp", "para", "mid", "interior"):
                    sel = [i for i, c in enumerate(common) if cell_stratum.get(c) == name_]
                    strata[name_] = ({"n": len(sel),
                                      "auc": round(auc_shifted_detect(s0[sel], sd[sel], False), 4)}
                                     if len(sel) >= 15 else {"n": len(sel), "auc": None})
                summary[f"{ch}_orientation_strata"][dk] = strata

    gate_d = str(float(cfg["validity_gate_delta"]))
    gate_auc = max(v for v in (summary["auc"].get(gate_d) or {}).values() if v is not None)
    summary["validity_gate"] = {
        "delta_m": float(cfg["validity_gate_delta"]),
        "best_auc": gate_auc,
        "passed": bool(gate_auc is not None and gate_auc >= 0.75),
        "rule": "fine-δ readings are meaningful only if the coarse control separates (best AUC >= 0.75)",
    }

    (out_root / "cell_scores.json").write_text(
        json.dumps({"schema": "phd_judge_trial_act1_fullres_scores_v1", "results": results},
                   ensure_ascii=False), encoding="utf-8")
    receipt = {
        "schema": "phd_judge_trial_act1_fullres_receipt_v1",
        "task_id": cfg["task_id"],
        "started_at": started,
        "ended_at": datetime.now(timezone.utc).isoformat(),
        "config_sha256": hashlib.sha256(json.dumps(cfg, sort_keys=True).encode()).hexdigest(),
        "camera": {"model": "FULL_OPENCV", "size": [5280, 3956],
                   "source": str(model / "cameras.bin")},
        "frame_check": "triangulated centers == crop centers (scene-local), verified 2026-08-23",
        "als_sources": als_rows,
        "patch_points": int(len(xyz0)), "roof_points": int(roof_mask.sum()),
        "delta_injection": {"deltas_east_m": deltas, "synthetic": True,
                            "not_real_als_lineage": True},
        "view_filter": {"min_px_per_m": cfg["min_px_per_m"], "rows": view_rows},
        "summary": summary,
        "scientific_verdict": None,
    }
    (out_root / "receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
