#!/usr/bin/env python3
"""T1 evidence bank v1 on XY-column pairs (design v2 appendix D-3 / D-7).

3D-a  frozen M3C2 relation cores aggregated per XY cell / patch pair
3D-b  free-space ray statistics: per exact camera framing the prism, nearest-depth
      z-buffers of the MVS and Existing ALS prism points (splats), a tile-wide MVS
      occluder buffer, ray classes AGREE / PENETRATE / BLOCK / MVS_ONLY / NO_LANDING /
      OCCLUDED attributed to the cell of the surface they test
2D-c  texture (local grey std), unoccluded view count, best incidence angle; power
      flags and r = number of channels with power
Evidence only: nothing here decides responsibility, weights, registration or change.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
from typing import Any

import numpy as np

from src.stage2.colmap_io import read_cameras_bin, read_images_bin


REPO = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = REPO / "configs/phd/evidence_bank_v1/run_v1.json"
SCHEMA = "jointbuildgs.phd.evidence_bank.run.v1"
RAY_AGREE, RAY_PENETRATE, RAY_BLOCK, RAY_MVS_ONLY, RAY_NO_LANDING, RAY_OCCLUDED = 0, 1, 2, 3, 4, 5
RAY_NAMES = {0: "AGREE", 1: "PENETRATE", 2: "BLOCK", 3: "MVS_ONLY", 4: "NO_LANDING", 5: "OCCLUDED"}
PROHIBITED_TOKENS = ("uas", "lod2", "footprint", "stable_id", "journal1", "roster")

CELL_DTYPE = np.dtype([
    ("ix", "<i4"), ("iy", "<i4"), ("state", "u1"), ("rough", "u1"), ("mvs_patch", "<i4"), ("als_patch", "<i4"),
    ("n_cores", "<u4"), ("core_d_median_m", "<f4"), ("core_lod_median_m", "<f4"),
    ("core_class_1", "<u2"), ("core_class_2", "<u2"), ("core_class_3", "<u2"), ("core_class_4", "<u2"), ("core_class_5", "<u2"),
    ("n_agree", "<u4"), ("n_penetrate", "<u4"), ("n_block", "<u4"), ("n_mvs_only", "<u4"), ("n_no_landing", "<u4"), ("n_occluded", "<u4"),
    ("n_views_tested", "<u2"), ("f_agree", "<f4"), ("f_penetrate", "<f4"), ("f_block", "<f4"),
    ("texture_median", "<f4"), ("n_views_unoccluded", "<u2"), ("incidence_best_deg", "<f4"),
    ("power_3da", "u1"), ("power_3db", "u1"), ("power_2da", "u1"), ("r", "u1"),
])
PAIR_DTYPE = np.dtype([
    ("mvs_patch", "<i4"), ("als_patch", "<i4"), ("state", "u1"), ("rough", "u1"), ("cells", "<u4"),
    ("n_cores", "<u4"), ("core_d_median_m", "<f4"), ("n_tested", "<u4"), ("f_agree", "<f4"), ("f_penetrate", "<f4"), ("f_block", "<f4"),
    ("n_mvs_only", "<u4"), ("n_no_landing", "<u4"), ("n_occluded", "<u4"), ("texture_median", "<f4"), ("n_views_unoccluded_median", "<f4"),
    ("incidence_best_deg", "<f4"), ("power_3da", "u1"), ("power_3db", "u1"), ("power_2da", "u1"), ("r", "u1"),
])


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            value.update(block)
    return value.hexdigest()


def array_digest(array: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(array).tobytes()).hexdigest()


def atomic_bytes(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp"); tmp.write_bytes(value); os.replace(tmp, path)


def atomic_json(path: Path, value: Any) -> None:
    atomic_bytes(path, (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8"))


def atomic_npy(path: Path, value: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("wb") as stream:
        np.save(stream, value, allow_pickle=False)
    os.replace(tmp, path)


def git_head() -> str:
    env = os.environ.get("JBGS_SOURCE_GIT_HEAD")
    if env:
        return env
    try:
        return subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    except Exception:  # noqa: BLE001
        return "UNKNOWN"


def load_config(path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    cfg = json.loads(path.read_text(encoding="utf-8"))
    if cfg.get("schema") != SCHEMA:
        raise ValueError("evidence bank config schema drift")
    if cfg.get("status") != "USER_APPROVED_DEVELOPMENT_NON_CONFIRMATORY":
        raise ValueError("run is not user-approved")
    if cfg.get("scientific_verdict", "missing") is not None:
        raise ValueError("scientific_verdict must remain null")
    serialized = json.dumps({"inputs": cfg["inputs"], "output": cfg["output_relative_root"]}).lower()
    for token in PROHIBITED_TOKENS:
        if token in serialized:
            raise ValueError(f"prohibited input token: {token}")
    if float(cfg["algorithm"]["rays"]["tolerance_m"]) <= 0 or int(cfg["algorithm"]["rays"]["min_tested_rays"]) < 1:
        raise ValueError("invalid ray parameters")
    return cfg


# ----------------------------------------------------------------------------
# geometry helpers
# ----------------------------------------------------------------------------

def read_xyz_bin(path: Path) -> np.ndarray:
    if path.stat().st_size % 12:
        raise ValueError(f"{path}: invalid xyz_f32le byte count")
    return np.fromfile(path, dtype="<f4").reshape(-1, 3)


def domain_bounds(domain: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    return (np.array([domain["x"][0], domain["y"][0], domain["z"][0]], dtype=np.float64),
            np.array([domain["x"][1], domain["y"][1], domain["z"][1]], dtype=np.float64))


def domain_mask(xyz: np.ndarray, domain: dict[str, Any]) -> np.ndarray:
    low, high = domain_bounds(domain)
    return np.all((xyz >= low) & (xyz < high), axis=1)


def cell_index(xy: np.ndarray, domain: dict[str, Any], cell: float) -> tuple[np.ndarray, np.ndarray]:
    low, _ = domain_bounds(domain)
    ix = np.floor((xy[:, 0] - low[0]) / cell).astype(np.int64)
    iy = np.floor((xy[:, 1] - low[1]) / cell).astype(np.int64)
    return ix, iy


def project(points: np.ndarray, R: np.ndarray, t: np.ndarray, K: np.ndarray, width: int, height: int) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """pixel x, y (int), camera depth z, and the mask of points inside the frame."""
    cam = points @ R.T + t
    z = cam[:, 2]
    ok = z > 1e-6
    u = K[0, 0] * cam[:, 0] / np.where(ok, z, 1.0) + K[0, 2]
    v = K[1, 1] * cam[:, 1] / np.where(ok, z, 1.0) + K[1, 2]
    x = np.floor(u + 0.5).astype(np.int64); y = np.floor(v + 0.5).astype(np.int64)
    inside = ok & (x >= 0) & (x < width) & (y >= 0) & (y < height)
    return x, y, z, inside


def zbuffer(points: np.ndarray, labels: np.ndarray, R: np.ndarray, t: np.ndarray, K: np.ndarray, width: int, height: int,
            splat: int, want_labels: bool = True) -> tuple[np.ndarray, np.ndarray]:
    """Nearest-depth buffer with a square splat of radius ``splat`` px; label buffer = label of the nearest point
    (ties: smallest label value).  Returns depth (inf = empty) and labels (-1 = empty), both (height, width)."""
    x, y, z, inside = project(points, R, t, K, width, height)
    depth = np.full(height * width, np.inf, dtype=np.float64)
    label = np.full(height * width, np.iinfo(np.int64).max, dtype=np.int64)
    xs, ys, zs, ls = x[inside], y[inside], z[inside], labels[inside].astype(np.int64)
    offsets = range(-splat, splat + 1)
    for dx in offsets:
        for dy in offsets:
            px = xs + dx; py = ys + dy
            keep = (px >= 0) & (px < width) & (py >= 0) & (py < height)
            idx = py[keep] * width + px[keep]
            np.minimum.at(depth, idx, zs[keep])
    if not want_labels:
        return depth.reshape(height, width), np.full((height, width), -1, dtype=np.int64)
    for dx in offsets:  # second pass: label of the nearest point per pixel
        for dy in offsets:
            px = xs + dx; py = ys + dy
            keep = (px >= 0) & (px < width) & (py >= 0) & (py < height)
            idx = py[keep] * width + px[keep]
            nearest = zs[keep] <= depth[idx] + 1e-9
            np.minimum.at(label, idx[nearest], ls[keep][nearest])
    label[label == np.iinfo(np.int64).max] = -1
    return depth.reshape(height, width), label.reshape(height, width)


def classify_rays(z_m: np.ndarray, z_p: np.ndarray, z_occ: np.ndarray, tolerance: float) -> np.ndarray:
    """(D-3a) ray class per pixel; -1 where neither source lands."""
    out = np.full(z_m.shape, -1, dtype=np.int8)
    has_m = np.isfinite(z_m); has_p = np.isfinite(z_p)
    z_m = np.where(has_m, z_m, 0.0); z_p = np.where(has_p, z_p, 0.0)  # avoid inf-inf warnings; masks carry presence
    front = np.minimum(np.where(has_m, z_m, np.inf), np.where(has_p, z_p, np.inf))
    occluded = (has_m | has_p) & np.isfinite(z_occ) & (z_occ < front - tolerance)
    both = has_m & has_p & ~occluded
    out[both & (np.abs(z_m - z_p) <= tolerance)] = RAY_AGREE
    out[both & (z_p < z_m - tolerance)] = RAY_PENETRATE
    out[both & (z_m < z_p - tolerance)] = RAY_BLOCK
    out[has_m & ~has_p & ~occluded] = RAY_MVS_ONLY
    out[has_p & ~has_m & ~occluded] = RAY_NO_LANDING
    out[occluded] = RAY_OCCLUDED
    return out


def texture_map(gray: np.ndarray, window: int) -> np.ndarray:
    """Local standard deviation of an 8-bit grey image over a window x window box (D-7a)."""
    import cv2
    g = gray.astype(np.float32)
    mean = cv2.blur(g, (window, window)); sq = cv2.blur(g * g, (window, window))
    return np.sqrt(np.maximum(sq - mean * mean, 0.0))


def eval_expectations(summary: dict[str, dict[str, float]], expectations: dict[str, dict[str, str]]) -> dict[str, dict[str, Any]]:
    """Mechanical check of the pre-registered expectation table against the per-state summary."""
    result = {}
    for state, exp in expectations.items():
        s = summary.get(state)
        if not s:
            result[state] = {"present": False}
            continue
        checks = {}
        if state == "COMPATIBLE":
            checks["3D-a median |d| <= 0.3"] = bool(abs(s["core_d_median_m"]) <= 0.3) if s["core_d_median_m"] is not None else None
            checks["3D-b AGREE >= 0.70"] = bool(s["f_agree_mean"] >= 0.70)
            checks["r >= 3 majority"] = bool(s["r_ge3_fraction"] >= 0.5)
        elif state == "PRIOR_ABOVE":
            checks["3D-a median d in [1,5] m"] = bool(1.0 <= s["core_d_median_m"] <= 5.0) if s["core_d_median_m"] is not None else None
            checks["3D-b PENETRATE >= 0.50"] = bool(s["f_penetrate_mean"] >= 0.50)
            checks["r >= 3 majority"] = bool(s["r_ge3_fraction"] >= 0.5)
        elif state == "CURRENT_ABOVE":
            checks["3D-b BLOCK >= PENETRATE"] = bool(s["f_block_mean"] >= s["f_penetrate_mean"])
            checks["r <= 2 majority"] = bool(s["r_ge3_fraction"] < 0.5)
        elif state == "PRIOR_ONLY":
            checks["3D-b NO_LANDING dominant"] = bool(s["n_no_landing"] > s["n_tested"])
            checks["r <= 1 majority"] = bool(s["r_le1_fraction"] >= 0.5)
        elif state == "CURRENT_ONLY":
            checks["3D-b MVS_ONLY dominant"] = bool(s["n_mvs_only"] > s["n_tested"])
        result[state] = {"present": True, "expected": exp, "checks": checks,
                         "met": int(sum(1 for v in checks.values() if v is True)), "total": len(checks)}
    return result


# ----------------------------------------------------------------------------
# pipeline
# ----------------------------------------------------------------------------

def select_views(cameras: dict, images: dict, members: set[int], domain: dict[str, Any]) -> list[int]:
    low, high = domain_bounds(domain)
    corners = np.array([[x, y, z] for x in (low[0], high[0]) for y in (low[1], high[1]) for z in (low[2], high[2])])
    chosen = []
    for iid in sorted(images):
        if iid not in members:
            continue
        im = images[iid]; cam = cameras[im.camera_id]
        x, y, z, inside = project(corners, im.R(), im.tvec, cam.K(), cam.width, cam.height)
        if np.all(inside):
            chosen.append(int(iid))
    return chosen


def build_evidence(cfg: dict[str, Any], pair_cells: np.ndarray, pair_pairs: np.ndarray, patches: dict[str, np.ndarray],
                   points: dict[str, np.ndarray], per_point: dict[str, np.ndarray], tile_mvs: np.ndarray,
                   cores: np.ndarray, cameras: dict, images: dict, views: list[int],
                   image_loader) -> dict[str, Any]:
    alg = cfg["algorithm"]; domain = cfg["domain"]; cell = float(alg["cell_size_m"])
    low, high = domain_bounds(domain)
    nx = int(np.ceil((high[0] - low[0]) / cell)); ny = int(np.ceil((high[1] - low[1]) / cell))
    top = pair_cells[pair_cells["layer"] == 0]
    cell_of = np.full((ny, nx), -1, dtype=np.int64); cell_of[top["iy"], top["ix"]] = np.arange(len(top))
    n_cells = len(top)
    # ---- per-point cell ids (flattened cell index in the top list; -1 if not a top cell)
    cell_id = {}
    for s in ("mvs", "als"):
        ix, iy = cell_index(points[s][:, :2], domain, cell)
        ok = (ix >= 0) & (ix < nx) & (iy >= 0) & (iy < ny) & (per_point[s]["patch_id"] > 0)
        cid = np.full(len(points[s]), -1, dtype=np.int64); cid[ok] = cell_of[iy[ok], ix[ok]]
        cell_id[s] = cid
    # ---- 3D-a cores -> cells
    cores_xyz = np.column_stack((cores["x"], cores["y"], cores["z"])).astype(np.float64)
    inside = domain_mask(cores_xyz, domain)
    cix, ciy = cell_index(cores_xyz[:, :2], domain, cell)
    core_cell = np.full(len(cores), -1, dtype=np.int64)
    ok = inside & (cix >= 0) & (cix < nx) & (ciy >= 0) & (ciy < ny)
    core_cell[ok] = cell_of[ciy[ok], cix[ok]]
    counts = np.zeros((n_cells, 6), dtype=np.int64)
    d_lists: dict[int, list[float]] = {}; lod_lists: dict[int, list[float]] = {}
    for k in np.flatnonzero(core_cell >= 0):
        c = int(core_cell[k]); cls = int(cores["relation_class"][k])
        counts[c, cls] += 1
        if np.isfinite(cores["m3c2_signed_m"][k]):
            d_lists.setdefault(c, []).append(float(cores["m3c2_signed_m"][k]))
            lod_lists.setdefault(c, []).append(float(cores["lod95_local_m"][k]))
    # ---- 3D-b rays and 2D-c texture over views
    ray_counts = np.zeros((n_cells, 6), dtype=np.int64)
    views_tested = np.zeros(n_cells, dtype=np.int64)
    views_unocc = np.zeros(n_cells, dtype=np.int64)
    texture_per_view: dict[int, list[float]] = {}
    incidence_best = np.full(n_cells, np.nan)
    tol = float(alg["rays"]["tolerance_m"]); stride = int(alg["rays"]["occluder_point_stride"])
    occluder = tile_mvs[::stride].astype(np.float64)
    labels_m = cell_id["mvs"]; labels_p = cell_id["als"]
    top_normal = np.full((n_cells, 3), np.nan)
    pm = patches["mvs"]; normal_of_patch = {int(p["patch_id"]): (np.array([p["nx"], p["ny"], p["nz"]]) if p["kind"] == 1 else None) for p in pm}
    for i in range(n_cells):
        nrm = normal_of_patch.get(int(top["mvs_patch"][i]))
        if nrm is not None:
            top_normal[i] = nrm
    cell_centres = np.column_stack((low[0] + (top["ix"] + 0.5) * cell, low[1] + (top["iy"] + 0.5) * cell,
                                    np.where(np.isfinite(top["mvs_z"]), top["mvs_z"], top["als_z"])))
    view_records = []
    for iid in views:
        im = images[iid]; cam = cameras[im.camera_id]; K = cam.K(); W, H = cam.width, cam.height
        R, t = im.R(), im.tvec
        z_m, l_m = zbuffer(points["mvs"], labels_m, R, t, K, W, H, int(alg["rays"]["splat_px_mvs"]))
        z_p, l_p = zbuffer(points["als"], labels_p, R, t, K, W, H, int(alg["rays"]["splat_px_als"]))
        z_occ, _ = zbuffer(occluder, np.zeros(len(occluder), dtype=np.int64), R, t, K, W, H, 0, want_labels=False)
        cls = classify_rays(z_m, z_p, z_occ, tol)
        # attribution: PENETRATE / NO_LANDING -> prior cell, others -> MVS cell
        target = np.where(np.isin(cls, [RAY_PENETRATE, RAY_NO_LANDING]), l_p, l_m)
        target = np.where((target < 0) & (cls >= 0), np.where(np.isfinite(z_m), l_m, l_p), target)
        valid = (cls >= 0) & (target >= 0)
        flat_t = target[valid]; flat_c = cls[valid].astype(np.int64)
        np.add.at(ray_counts, (flat_t, flat_c), 1)
        tested_mask = np.isin(flat_c, [RAY_AGREE, RAY_PENETRATE, RAY_BLOCK])
        tested_cells = np.unique(flat_t[tested_mask]); views_tested[tested_cells] += 1
        # 2D-c: texture at unoccluded MVS pixels
        unocc_m = np.isfinite(z_m) & (l_m >= 0) & ~((np.isfinite(z_occ)) & (z_occ < z_m - tol))
        gray = image_loader(iid)
        tex = texture_map(gray, int(alg["observability"]["texture_window_px"]))
        cells_here = l_m[unocc_m]; tex_here = tex[unocc_m]
        order = np.argsort(cells_here, kind="stable"); cells_sorted = cells_here[order]; tex_sorted = tex_here[order]
        uniq, start, count = np.unique(cells_sorted, return_index=True, return_counts=True)
        min_px = int(alg["observability"]["min_pixels_per_view"])
        for u, s0, n in zip(uniq, start, count):
            if n >= min_px:
                views_unocc[u] += 1
                texture_per_view.setdefault(int(u), []).append(float(np.median(tex_sorted[s0:s0 + n])))
        # incidence: angle between viewing ray (camera centre -> cell centre) and top patch normal
        centre_cam = -R.T @ t
        rays = cell_centres - centre_cam; rays /= np.linalg.norm(rays, axis=1, keepdims=True)
        cosang = np.abs(np.einsum("ij,ij->i", rays, np.nan_to_num(top_normal)))
        ang = np.degrees(np.arccos(np.clip(cosang, 0, 1)))
        seen = np.zeros(n_cells, dtype=bool); seen[uniq[count >= min_px]] = True
        has_normal = np.isfinite(top_normal[:, 0])
        cand = seen & has_normal
        incidence_best[cand] = np.fmin(incidence_best[cand], ang[cand])
        view_records.append({"colmap_image_id": int(iid), "name": im.name, "rays_tested": int(tested_mask.sum()),
                             "penetrate": int((flat_c == RAY_PENETRATE).sum()), "block": int((flat_c == RAY_BLOCK).sum()),
                             "agree": int((flat_c == RAY_AGREE).sum()), "occluded": int((flat_c == RAY_OCCLUDED).sum())})
    # ---- assemble cells
    cells = np.zeros(n_cells, dtype=CELL_DTYPE)
    cells["ix"], cells["iy"], cells["state"], cells["rough"] = top["ix"], top["iy"], top["state"], top["rough"]
    cells["mvs_patch"], cells["als_patch"] = top["mvs_patch"], top["als_patch"]
    cells["n_cores"] = counts[:, 1:].sum(axis=1)
    for k in range(1, 6):
        cells[f"core_class_{k}"] = counts[:, k]
    cells["core_d_median_m"] = [np.median(d_lists[i]) if i in d_lists else np.nan for i in range(n_cells)]
    cells["core_lod_median_m"] = [np.median(lod_lists[i]) if i in lod_lists else np.nan for i in range(n_cells)]
    names = ["n_agree", "n_penetrate", "n_block", "n_mvs_only", "n_no_landing", "n_occluded"]
    for k, name in enumerate(names):
        cells[name] = ray_counts[:, k]
    tested = ray_counts[:, :3].sum(axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        cells["f_agree"] = np.where(tested > 0, ray_counts[:, 0] / np.maximum(tested, 1), np.nan)
        cells["f_penetrate"] = np.where(tested > 0, ray_counts[:, 1] / np.maximum(tested, 1), np.nan)
        cells["f_block"] = np.where(tested > 0, ray_counts[:, 2] / np.maximum(tested, 1), np.nan)
    cells["n_views_tested"] = views_tested
    cells["texture_median"] = [np.median(texture_per_view[i]) if i in texture_per_view else np.nan for i in range(n_cells)]
    cells["n_views_unoccluded"] = views_unocc
    cells["incidence_best_deg"] = incidence_best
    obs = alg["observability"]
    cells["power_3da"] = cells["n_cores"] >= int(alg["cores"]["min_cores_cell"])
    cells["power_3db"] = tested >= int(alg["rays"]["min_tested_rays"])
    cells["power_2da"] = (np.nan_to_num(cells["texture_median"], nan=0.0) >= float(obs["texture_min_gray_std"])) & \
                         (cells["n_views_unoccluded"] >= int(obs["min_views"])) & (np.nan_to_num(cells["incidence_best_deg"], nan=999.0) <= float(obs["max_incidence_deg"]))
    cells["r"] = cells["power_3da"].astype(int) + cells["power_3db"].astype(int) + cells["power_2da"].astype(int)
    # ---- patch pairs (top layer only: ray evidence is attributed to the surfaces rays reach first)
    pair_pairs = pair_pairs[pair_pairs["layer"] == 0]
    pairs = np.zeros(len(pair_pairs), dtype=PAIR_DTYPE)
    for j, pp in enumerate(pair_pairs):
        sel = (cells["mvs_patch"] == pp["mvs_patch"]) & (cells["als_patch"] == pp["als_patch"])
        c = cells[sel]; rec = pairs[j]
        rec["mvs_patch"], rec["als_patch"], rec["state"], rec["rough"], rec["cells"] = pp["mvs_patch"], pp["als_patch"], pp["state"], pp["rough"], len(c)
        rec["n_cores"] = c["n_cores"].sum()
        ds = c["core_d_median_m"][np.isfinite(c["core_d_median_m"])]
        rec["core_d_median_m"] = np.median(ds) if len(ds) else np.nan
        t_ = int(c["n_agree"].sum() + c["n_penetrate"].sum() + c["n_block"].sum()); rec["n_tested"] = t_
        rec["f_agree"] = c["n_agree"].sum() / t_ if t_ else np.nan
        rec["f_penetrate"] = c["n_penetrate"].sum() / t_ if t_ else np.nan
        rec["f_block"] = c["n_block"].sum() / t_ if t_ else np.nan
        rec["n_mvs_only"], rec["n_no_landing"], rec["n_occluded"] = c["n_mvs_only"].sum(), c["n_no_landing"].sum(), c["n_occluded"].sum()
        tx = c["texture_median"][np.isfinite(c["texture_median"])]; rec["texture_median"] = np.median(tx) if len(tx) else np.nan
        rec["n_views_unoccluded_median"] = float(np.median(c["n_views_unoccluded"])) if len(c) else np.nan
        inc = c["incidence_best_deg"][np.isfinite(c["incidence_best_deg"])]; rec["incidence_best_deg"] = inc.min() if len(inc) else np.nan
        rec["power_3da"] = rec["n_cores"] >= int(alg["cores"]["min_cores_pair"]); rec["power_3db"] = t_ >= int(alg["rays"]["min_tested_rays"])
        rec["power_2da"] = (np.nan_to_num(rec["texture_median"], nan=0.0) >= float(obs["texture_min_gray_std"])) and \
                           (np.nan_to_num(rec["n_views_unoccluded_median"], nan=0.0) >= int(obs["min_views"])) and (np.nan_to_num(rec["incidence_best_deg"], nan=999.0) <= float(obs["max_incidence_deg"]))
        rec["r"] = int(rec["power_3da"]) + int(rec["power_3db"]) + int(rec["power_2da"])
    # ---- per-state summary (for the expectation check)
    state_names = {1: "COMPATIBLE", 2: "PRIOR_ABOVE", 3: "CURRENT_ABOVE", 4: "PRIOR_ONLY", 5: "CURRENT_ONLY"}
    summary = {}
    for k, name in state_names.items():
        sel = cells[cells["state"] == k]
        if not len(sel):
            continue
        t_ = sel["n_agree"] + sel["n_penetrate"] + sel["n_block"]
        ds = sel["core_d_median_m"][np.isfinite(sel["core_d_median_m"])]
        summary[name] = {
            "cells": int(len(sel)), "area_m2": float(len(sel) * cell * cell), "rough_cells": int(sel["rough"].sum()),
            "n_cores": int(sel["n_cores"].sum()), "core_d_median_m": float(np.median(ds)) if len(ds) else None,
            "core_lod_median_m": float(np.nanmedian(sel["core_lod_median_m"])) if np.any(np.isfinite(sel["core_lod_median_m"])) else None,
            "core_class_counts": {str(c): int(sel[f"core_class_{c}"].sum()) for c in range(1, 6)},
            "n_tested": int(t_.sum()), "n_mvs_only": int(sel["n_mvs_only"].sum()), "n_no_landing": int(sel["n_no_landing"].sum()), "n_occluded": int(sel["n_occluded"].sum()),
            "f_agree_mean": float(sel["n_agree"].sum() / max(1, t_.sum())), "f_penetrate_mean": float(sel["n_penetrate"].sum() / max(1, t_.sum())), "f_block_mean": float(sel["n_block"].sum() / max(1, t_.sum())),
            "cells_with_ray_power": int(sel["power_3db"].sum()), "texture_median": float(np.nanmedian(sel["texture_median"])) if np.any(np.isfinite(sel["texture_median"])) else None,
            "views_unoccluded_median": float(np.median(sel["n_views_unoccluded"])), "incidence_best_median_deg": float(np.nanmedian(sel["incidence_best_deg"])) if np.any(np.isfinite(sel["incidence_best_deg"])) else None,
            "r_distribution": {str(v): int(np.count_nonzero(sel["r"] == v)) for v in range(4)},
            "r_ge3_fraction": float(np.mean(sel["r"] >= 3)), "r_le1_fraction": float(np.mean(sel["r"] <= 1)),
        }
    evaluation = eval_expectations(summary, cfg["expectations_before_run"])
    return {"cells": cells, "pairs": pairs, "summary": summary, "evaluation": evaluation, "views": view_records}


# ----------------------------------------------------------------------------
# I/O
# ----------------------------------------------------------------------------

def verify(path: Path, expected_sha: str, label: str) -> None:
    if not path.is_file() or sha256(path) != expected_sha:
        raise RuntimeError(f"input drift: {label}")


def resolve_inputs(cfg: dict[str, Any]) -> dict[str, Any]:
    root = Path(cfg["artifact_root"]); inp = cfg["inputs"]
    pair_root = root / inp["pairing_relative_root"]
    verify(pair_root / "artifact_manifest.json", inp["pairing_artifact_manifest_sha256"], "pairing manifest")
    verify(pair_root / "validation_receipt.json", inp["pairing_validation_receipt_sha256"], "pairing receipt")
    receipt = json.loads((pair_root / "validation_receipt.json").read_text(encoding="utf-8"))
    if receipt.get("artifact_manifest_sha256") != sha256(pair_root / "artifact_manifest.json") or any(v != "PASS" for v in receipt["checks"].values()):
        raise RuntimeError("pairing receipt not bound or not PASS")
    pm = json.loads((pair_root / "artifact_manifest.json").read_text(encoding="utf-8"))
    for name, item in pm["outputs"].items():
        p = pair_root / name
        if p.stat().st_size != int(item["bytes"]) or sha256(p) != item["sha256"]:
            raise RuntimeError(f"pairing output drift: {name}")
    patch_root = root / inp["surface_patch_relative_root"]
    verify(patch_root / "artifact_manifest.json", inp["surface_patch_artifact_manifest_sha256"], "patch manifest")
    ppm = json.loads((patch_root / "artifact_manifest.json").read_text(encoding="utf-8"))
    for name, item in ppm["outputs"].items():
        p = patch_root / name
        if p.stat().st_size != int(item["bytes"]) or sha256(p) != item["sha256"]:
            raise RuntimeError(f"patch output drift: {name}")
    rel = root / inp["source_relation_relative_root"]
    verify(rel / inp["relation_map"]["relative_path"], inp["relation_map"]["sha256"], "relation map")
    for s, item in inp["partitions"].items():
        verify(rel / item["relative_path"], item["sha256"], f"partition {s}")
    cam = inp["current_cameras"]; cam_root = root / cam["camera_root_relative_path"]
    verify(cam_root / "sparse/cameras.bin", cam["cameras_bin_sha256"], "cameras.bin")
    verify(cam_root / "sparse/images.bin", cam["images_bin_sha256"], "images.bin")
    verify(REPO / cam["exact_937_crosswalk_git_relative_path"], cam["exact_937_crosswalk_sha256"], "crosswalk")
    return {"pairing_root": str(pair_root), "patch_root": str(patch_root), "relation_root": str(rel), "camera_root": str(cam_root),
            "pairing_manifest_sha256": inp["pairing_artifact_manifest_sha256"], "patch_manifest_sha256": inp["surface_patch_artifact_manifest_sha256"]}


def load_everything(cfg: dict[str, Any], resolved: dict[str, Any]):
    inp = cfg["inputs"]
    pair_root = Path(resolved["pairing_root"]); patch_root = Path(resolved["patch_root"]); rel = Path(resolved["relation_root"]); cam_root = Path(resolved["camera_root"])
    pair_cells = np.load(pair_root / "pair_cells.npy", allow_pickle=False); pair_pairs = np.load(pair_root / "pair_pairs.npy", allow_pickle=False)
    patches, points, per_point = {}, {}, {}
    tile_mvs = None
    for s in ("mvs", "als"):
        xyz = read_xyz_bin(rel / inp["partitions"][s]["relative_path"])
        if s == "mvs":
            tile_mvs = xyz
        rows = np.load(patch_root / f"point_rows_{s}.npy", allow_pickle=False)
        points[s] = xyz[rows].astype(np.float64)
        per_point[s] = np.load(patch_root / f"points_{s}.npy", allow_pickle=False)
        patches[s] = np.load(patch_root / f"patches_{s}.npy", allow_pickle=False)
    cores = np.load(rel / inp["relation_map"]["relative_path"], allow_pickle=False)
    cameras = read_cameras_bin(cam_root / "sparse/cameras.bin"); images = read_images_bin(cam_root / "sparse/images.bin")
    crosswalk = json.loads((REPO / inp["current_cameras"]["exact_937_crosswalk_git_relative_path"]).read_text(encoding="utf-8"))
    members = {int(r["colmap_image_id"]) for r in crosswalk["rows"]}
    return pair_cells, pair_pairs, patches, points, per_point, tile_mvs, cores, cameras, images, members


def make_image_loader(cam_root: Path, images: dict, hashes: dict[int, str]):
    import cv2

    def load(iid: int) -> np.ndarray:
        path = cam_root / "images" / images[iid].name
        hashes[iid] = sha256(path)
        bgr = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if bgr is None:
            raise RuntimeError(f"image decode failed: {path}")
        return cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    return load


def write_preview(path: Path, cfg: dict[str, Any], cells: np.ndarray) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    dom = cfg["domain"]; cell = float(cfg["algorithm"]["cell_size_m"])
    low, high = domain_bounds(dom)
    nx = int(np.ceil((high[0] - low[0]) / cell)); ny = int(np.ceil((high[1] - low[1]) / cell))
    def grid(values, fill=np.nan):
        g = np.full((ny, nx), fill); g[cells["iy"], cells["ix"]] = values; return g
    fig, axes = plt.subplots(2, 3, figsize=(21, 13), dpi=100)
    panels = [("3D-b penetrate fraction (prior surface crossed by rays)", grid(cells["f_penetrate"]), "Reds", 0, 1),
              ("3D-b agree fraction", grid(cells["f_agree"]), "Greens", 0, 1),
              ("3D-b block fraction (current surface in front)", grid(cells["f_block"]), "Oranges", 0, 1),
              ("3D-a median signed distance d = ALS - MVS (m)", grid(cells["core_d_median_m"]), "coolwarm", -4, 4),
              ("2D-c texture (local grey std, median over views)", grid(cells["texture_median"]), "viridis", 0, 30),
              ("r = channels with power (0..3)", grid(cells["r"].astype(float)), "magma", 0, 3)]
    for ax, (title, g, cmap, vmin, vmax) in zip(axes.ravel(), panels):
        im = ax.imshow(g, origin="lower", extent=[dom["x"][0], dom["x"][1], dom["y"][0], dom["y"][1]], cmap=cmap, vmin=vmin, vmax=vmax)
        ax.set_title(title, fontsize=10); ax.set_aspect("equal"); fig.colorbar(im, ax=ax, fraction=0.046)
    fig.suptitle("T1 evidence bank on the pilot prism (XY cells, top layer). Evidence only, no verdict.", fontsize=12)
    fig.tight_layout(); path.parent.mkdir(parents=True, exist_ok=True); fig.savefig(path); plt.close(fig)


def run(cfg: dict[str, Any], config_path: Path) -> dict[str, Any]:
    started = time.perf_counter()
    out = Path(cfg["artifact_root"]) / cfg["output_relative_root"]; out.mkdir(parents=True, exist_ok=True)
    resolved = resolve_inputs(cfg)
    pair_cells, pair_pairs, patches, points, per_point, tile_mvs, cores, cameras, images, members = load_everything(cfg, resolved)
    views = select_views(cameras, images, members, cfg["domain"])
    hashes: dict[int, str] = {}
    loader = make_image_loader(Path(resolved["camera_root"]), images, hashes)
    result = build_evidence(cfg, pair_cells, pair_pairs, patches, points, per_point, tile_mvs, cores, cameras, images, views, loader)
    atomic_npy(out / "evidence_cells.npy", result["cells"]); atomic_npy(out / "evidence_pairs.npy", result["pairs"])
    atomic_json(out / "evidence_views.json", {"schema": "jointbuildgs.phd.evidence_bank.views.v1", "view_count": len(views),
                                              "views": [dict(v, image_sha256=hashes.get(v["colmap_image_id"])) for v in result["views"]]})
    atomic_json(out / "evaluation.json", {"schema": "jointbuildgs.phd.evidence_bank.evaluation.v1",
                                          "expectations_before_run": cfg["expectations_before_run"],
                                          "per_state_summary": result["summary"], "expectation_checks": result["evaluation"],
                                          "scientific_verdict": None})
    write_preview(out / "evidence_preview.png", cfg, result["cells"])
    technical = {
        "schema": "jointbuildgs.phd.evidence_bank.technical_return.v1", "task_id": cfg["task_id"],
        "status": "COMPLETE_DEVELOPMENT_NON_CONFIRMATORY", "generated_utc": utc_now(), "git_commit": git_head(),
        "config": {"path": str(config_path), "sha256": sha256(config_path)}, "driver": {"path": str(Path(__file__)), "sha256": sha256(Path(__file__))},
        "domain": cfg["domain"], "algorithm": cfg["algorithm"], "view_count": len(views),
        "per_state_summary": result["summary"], "expectation_checks": result["evaluation"],
        "ray_class_names": RAY_NAMES, "not_decided_here": cfg["not_decided_here"],
        "elapsed_seconds": time.perf_counter() - started, "prohibited_inputs_accessed": [], "scientific_verdict": None,
    }
    atomic_json(out / "technical_return.json", technical)
    outputs = {}
    for name in sorted(["evidence_cells.npy", "evidence_pairs.npy", "evidence_views.json", "evaluation.json", "evidence_preview.png", "technical_return.json"]):
        p = out / name; outputs[name] = {"path": name, "bytes": p.stat().st_size, "sha256": sha256(p)}
    atomic_json(out / "artifact_manifest.json", {
        "schema": "jointbuildgs.phd.evidence_bank.artifact_manifest.v1", "task_id": cfg["task_id"], "status": "COMPLETE_DEVELOPMENT_NON_CONFIRMATORY",
        "generated_utc": utc_now(), "git_commit": technical["git_commit"], "config": technical["config"], "driver": technical["driver"],
        "inputs": resolved, "outputs": outputs, "prohibited_inputs_accessed": [], "scientific_verdict": None})
    return technical


def validate(cfg: dict[str, Any], rerun: bool = True) -> dict[str, Any]:
    out = Path(cfg["artifact_root"]) / cfg["output_relative_root"]
    manifest = json.loads((out / "artifact_manifest.json").read_text(encoding="utf-8"))
    checks = {}
    for name, item in manifest["outputs"].items():
        p = out / name
        if p.stat().st_size != int(item["bytes"]) or sha256(p) != item["sha256"]:
            raise AssertionError(f"output hash drift: {name}")
    checks["output_hashes"] = "PASS"
    resolved = resolve_inputs(cfg)
    checks["input_hashes_and_upstream_binding"] = "PASS"
    cells = np.load(out / "evidence_cells.npy", allow_pickle=False)
    tested = cells["n_agree"] + cells["n_penetrate"] + cells["n_block"]
    f = np.nan_to_num(cells["f_agree"]) + np.nan_to_num(cells["f_penetrate"]) + np.nan_to_num(cells["f_block"])
    if np.any(np.abs(f[tested > 0] - 1.0) > 1e-5):
        raise AssertionError("ray fractions do not sum to one")
    if np.any(cells["r"] != cells["power_3da"].astype(int) + cells["power_3db"].astype(int) + cells["power_2da"].astype(int)):
        raise AssertionError("r drift")
    if np.any(cells["power_3db"] != (tested >= int(cfg["algorithm"]["rays"]["min_tested_rays"]))):
        raise AssertionError("3D-b power drift")
    checks["cell_consistency"] = "PASS"
    if rerun:
        pair_cells, pair_pairs, patches, points, per_point, tile_mvs, cores, cameras, images, members = load_everything(cfg, resolved)
        views = select_views(cameras, images, members, cfg["domain"])
        loader = make_image_loader(Path(resolved["camera_root"]), images, {})
        again = build_evidence(cfg, pair_cells, pair_pairs, patches, points, per_point, tile_mvs, cores, cameras, images, views, loader)
        for name, arr in (("evidence_cells.npy", again["cells"]), ("evidence_pairs.npy", again["pairs"])):
            if array_digest(arr) != array_digest(np.load(out / name, allow_pickle=False)):
                raise AssertionError(f"determinism drift: {name}")
        checks["determinism_rerun"] = "PASS"
    technical = json.loads((out / "technical_return.json").read_text(encoding="utf-8"))
    if technical.get("scientific_verdict", "missing") is not None or technical.get("prohibited_inputs_accessed") != []:
        raise AssertionError("technical return contract drift")
    checks["prohibited_inputs"] = "PASS"; checks["scientific_verdict_null"] = "PASS"
    receipt = {"schema": "jointbuildgs.phd.evidence_bank.validation.v1", "task_id": cfg["task_id"], "generated_utc": utc_now(),
               "checks": checks, "artifact_manifest_sha256": sha256(out / "artifact_manifest.json"), "prohibited_inputs_accessed": [], "scientific_verdict": None}
    atomic_json(out / "validation_receipt.json", receipt)
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--no-rerun", action="store_true")
    parser.add_argument("command", choices=("run", "validate", "run-and-validate"))
    args = parser.parse_args()
    cfg = load_config(args.config.resolve())
    if args.command in {"run", "run-and-validate"}:
        technical = run(cfg, args.config.resolve())
        print(json.dumps({"views": technical["view_count"], "elapsed": technical["elapsed_seconds"], "summary": technical["per_state_summary"], "checks": technical["expectation_checks"]}, indent=1))
    if args.command in {"validate", "run-and-validate"}:
        print(json.dumps(validate(cfg, rerun=not args.no_rerun)["checks"], indent=1))


if __name__ == "__main__":
    main()
