#!/usr/bin/env python3
"""T2 warp-NCC v1 on the T1 XY-column cells (design v2 appendix D-5 / D-6).

2D-a  inter-view photometric consistency of the current images through a candidate height field:
      candidates M (current MVS top layer) and P (Existing ALS top layer at delta0 = 0), plus synthetic
      shifted controls M+delta that measure the channel's own power.  Every candidate carries its own
      visibility (self occlusion of the hypothesised height field rendered at 3x resolution + outside-prism
      current MVS occluders).  Per (cell, candidate): weighted ZNCC over all valid view pairs; per cell:
      paired contrast on the common pairs.
2D-b  auxiliary: depth-edge pixels of the candidate height-field render versus the Canny edges of the image.
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

from scripts.phd.evidence_bank_v1 import run as eb
from src.stage2.colmap_io import read_cameras_bin, read_images_bin


REPO = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = REPO / "configs/phd/warp_ncc_v1/run_v1.json"
SCHEMA = "jointbuildgs.phd.warp_ncc.run.v1"
PROHIBITED_TOKENS = ("uas", "lod2", "footprint", "stable_id", "journal1", "roster")
STATE_NAMES = {1: "COMPATIBLE", 2: "PRIOR_ABOVE", 3: "CURRENT_ABOVE", 4: "PRIOR_ONLY", 5: "CURRENT_ONLY"}
N_CONTROLS = 4

CELL_DTYPE = np.dtype([
    ("ix", "<i4"), ("iy", "<i4"), ("state", "u1"), ("rough", "u1"), ("mvs_patch", "<i4"), ("als_patch", "<i4"),
    ("n_samples_m", "<u2"), ("n_samples_p", "<u2"), ("n_views_m", "<u2"), ("n_views_p", "<u2"),
    ("n_pairs_m", "<u4"), ("n_pairs_p", "<u4"),
    ("ncc_median_m", "<f4"), ("ncc_median_p", "<f4"), ("ncc_fisher_m", "<f4"), ("ncc_fisher_p", "<f4"),
    ("f_good_m", "<f4"), ("f_good_p", "<f4"), ("angle_median_m", "<f4"), ("angle_median_p", "<f4"),
    ("n_pairs_common", "<u4"), ("delta_median", "<f4"), ("f_m_over_p", "<f4"), ("f_p_over_m", "<f4"),
    ("n_pairs_wide_m", "<u4"), ("n_pairs_wide_p", "<u4"), ("ncc_median_wide_m", "<f4"), ("ncc_median_wide_p", "<f4"),
    ("n_pairs_common_wide", "<u4"), ("delta_median_wide", "<f4"),
    ("n_pairs_ctrl", "<u4", (N_CONTROLS,)), ("ncc_median_ctrl", "<f4", (N_CONTROLS,)),
    ("n_edge_px_m", "<u4"), ("edge_dist_median_px_m", "<f4"), ("edge_dist_median_m_m", "<f4"),
    ("n_edge_px_p", "<u4"), ("edge_dist_median_px_p", "<f4"), ("edge_dist_median_m_p", "<f4"),
    ("power_2da_m", "u1"), ("power_2da_p", "u1"), ("power_2da_any", "u1"), ("power_3da", "u1"), ("power_3db", "u1"),
    ("r_t1", "u1"), ("r_t2", "u1"),
    ("chip_view_a", "<i4"), ("chip_view_b", "<i4"), ("chip_angle_deg", "<f4"), ("chip_ncc_m", "<f4"), ("chip_ncc_p", "<f4"),
])
PAIR_DTYPE = np.dtype([
    ("mvs_patch", "<i4"), ("als_patch", "<i4"), ("state", "u1"), ("rough", "u1"), ("cells", "<u4"),
    ("cells_power_m", "<u4"), ("cells_power_p", "<u4"), ("n_pairs_m", "<u4"), ("n_pairs_p", "<u4"),
    ("ncc_median_m", "<f4"), ("ncc_median_p", "<f4"), ("n_pairs_common", "<u4"), ("delta_median", "<f4"), ("f_m_over_p", "<f4"),
    ("edge_dist_median_m_m", "<f4"), ("edge_dist_median_m_p", "<f4"), ("power_2da_any", "u1"), ("r_t2", "u1"),
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
        raise ValueError("warp-ncc config schema drift")
    if cfg.get("status") != "USER_APPROVED_DEVELOPMENT_NON_CONFIRMATORY":
        raise ValueError("run is not user-approved")
    if cfg.get("scientific_verdict", "missing") is not None:
        raise ValueError("scientific_verdict must remain null")
    serialized = json.dumps({"inputs": cfg["inputs"], "output": cfg["output_relative_root"]}).lower()
    for token in PROHIBITED_TOKENS:
        if token in serialized:
            raise ValueError(f"prohibited input token: {token}")
    alg = cfg["algorithm"]
    if len(alg["controls"]) != N_CONTROLS or any(c["base"] != "M" for c in alg["controls"]):
        raise ValueError("exactly four M-based control candidates are expected")
    if not (0 < alg["pairs"]["min_angle_deg"] < alg["pairs"]["max_angle_deg"] <= 90):
        raise ValueError("invalid pair angle window")
    if int(alg["visibility"]["zbuffer_supersample"]) < 1 or float(alg["visibility"]["tolerance_m"]) <= 0:
        raise ValueError("invalid visibility parameters")
    if int(alg["ncc"]["min_pairs_power"]) < 1 or float(alg["window"]["min_effective_samples"]) <= 0:
        raise ValueError("invalid ncc parameters")
    band = float(alg["ncc"]["summary_angle_max_deg"])
    if not (alg["pairs"]["min_angle_deg"] < band <= alg["pairs"]["max_angle_deg"]):
        raise ValueError("summary angle band must lie inside the pair angle window")
    return cfg


# ----------------------------------------------------------------------------
# geometry helpers
# ----------------------------------------------------------------------------

def height_grids(top: np.ndarray, nx: int, ny: int) -> dict[str, np.ndarray]:
    """(D-5a) top-layer candidate height fields on the cell-centre grid; NaN where the source has no top surface."""
    grids = {}
    for name, field in (("M", "mvs_z"), ("P", "als_z")):
        g = np.full((ny, nx), np.nan); g[top["iy"], top["ix"]] = np.where(np.isfinite(top[field]), top[field], np.nan)
        grids[name] = g
    return grids


def bilinear_grid(z: np.ndarray, x: np.ndarray, y: np.ndarray, low: np.ndarray, cell: float) -> np.ndarray:
    """(D-5a) height at continuous (x, y): bilinear on the four surrounding cell centres; if any corner is missing, the nearest cell's value (NaN when that cell is missing too, so the sample is dropped)."""
    ny, nx = z.shape
    fx = (x - low[0]) / cell - 0.5; fy = (y - low[1]) / cell - 0.5
    x0 = np.floor(fx).astype(np.int64); y0 = np.floor(fy).astype(np.int64); tx = fx - x0; ty = fy - y0
    out = np.full(len(x), np.nan)
    ok = (x0 >= 0) & (x0 + 1 < nx) & (y0 >= 0) & (y0 + 1 < ny)
    xa, ya = x0[ok], y0[ok]
    out[ok] = (z[ya, xa] * (1 - tx[ok]) * (1 - ty[ok]) + z[ya, xa + 1] * tx[ok] * (1 - ty[ok])
               + z[ya + 1, xa] * (1 - tx[ok]) * ty[ok] + z[ya + 1, xa + 1] * tx[ok] * ty[ok])
    nx_ = np.round(fx).astype(np.int64); ny_ = np.round(fy).astype(np.int64)
    inside = (nx_ >= 0) & (nx_ < nx) & (ny_ >= 0) & (ny_ < ny)
    near = np.full(len(x), np.nan); near[inside] = z[ny_[inside], nx_[inside]]
    bad = ~np.isfinite(out)
    out[bad] = near[bad]
    return out


def window_offsets(half: float, step: float, sigma: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(D-5c) square window sample offsets (row-major, y then x) and Gaussian weights."""
    g = np.arange(-half + step / 2, half, step)
    X, Y = np.meshgrid(g, g)
    w = np.exp(-(X ** 2 + Y ** 2) / (2 * sigma ** 2))
    return X.ravel(), Y.ravel(), w.ravel()


def project_pixels(points: np.ndarray, R: np.ndarray, t: np.ndarray, K: np.ndarray, width: int, height: int, s: int = 1):
    """Continuous image coordinates (u, v; COLMAP convention, pixel centres at +0.5), camera depth z, the integer pixel at
    supersample s (fine pixel = floor(s*u + s/2), so image pixel x covers fine pixels s*x .. s*x+s-1) and the inside mask."""
    cam = points @ R.T + t
    z = cam[:, 2]
    ok = z > 1e-6
    u = K[0, 0] * cam[:, 0] / np.where(ok, z, 1.0) + K[0, 2]
    v = K[1, 1] * cam[:, 1] / np.where(ok, z, 1.0) + K[1, 2]
    px = np.floor(s * u + s / 2).astype(np.int64); py = np.floor(s * v + s / 2).astype(np.int64)
    inside = ok & (px >= 0) & (px < s * width) & (py >= 0) & (py < s * height)
    return u, v, z, px, py, inside


def zbuffer_depth(points: np.ndarray, R: np.ndarray, t: np.ndarray, K: np.ndarray, width: int, height: int, s: int, splat: int) -> np.ndarray:
    """Nearest-depth buffer at supersample s with a square splat of ``splat`` fine pixels; inf = empty; float32 (s*height, s*width)."""
    _, _, z, px, py, inside = project_pixels(points, R, t, K, width, height, s)
    W, H = s * width, s * height
    depth = np.full(H * W, np.inf, dtype=np.float32)
    xs, ys, zs = px[inside], py[inside], z[inside].astype(np.float32)
    for dx in range(-splat, splat + 1):
        for dy in range(-splat, splat + 1):
            qx = xs + dx; qy = ys + dy
            keep = (qx >= 0) & (qx < W) & (qy >= 0) & (qy < H)
            np.minimum.at(depth, qy[keep] * W + qx[keep], zs[keep])
    return depth.reshape(H, W)


def bilinear_image(gray: np.ndarray, u: np.ndarray, v: np.ndarray) -> np.ndarray:
    """Grey value at continuous (u, v) with pixel centres at +0.5; callers guarantee u in [1, W-2), v in [1, H-2)."""
    fx = u - 0.5; fy = v - 0.5
    x0 = np.floor(fx).astype(np.int64); y0 = np.floor(fy).astype(np.int64)
    dx = (fx - x0).astype(np.float32); dy = (fy - y0).astype(np.float32)
    return (gray[y0, x0] * (1 - dx) * (1 - dy) + gray[y0, x0 + 1] * dx * (1 - dy)
            + gray[y0 + 1, x0] * (1 - dx) * dy + gray[y0 + 1, x0 + 1] * dx * dy)


def select_pairs(view_ids: list[int], centres: dict[int, np.ndarray], reference: np.ndarray,
                 min_angle: float, max_angle: float, max_ratio: float) -> list[tuple[int, int, float, float]]:
    """(D-5e) all view pairs whose rays to the reference point intersect at [min_angle, max_angle] degrees with distance ratio <= max_ratio."""
    out = []
    for a_idx in range(len(view_ids)):
        for b_idx in range(a_idx + 1, len(view_ids)):
            a, b = view_ids[a_idx], view_ids[b_idx]
            ra = centres[a] - reference; rb = centres[b] - reference
            na, nb = np.linalg.norm(ra), np.linalg.norm(rb)
            ang = float(np.degrees(np.arccos(np.clip(ra @ rb / (na * nb), -1.0, 1.0))))
            ratio = float(max(na, nb) / min(na, nb))
            if min_angle <= ang <= max_angle and ratio <= max_ratio:
                out.append((a_idx, b_idx, ang, ratio))
    return out


def weighted_zncc_batch(a: np.ndarray, b: np.ndarray, both: np.ndarray, weights: np.ndarray, valid_count: np.ndarray,
                        min_visible_fraction: float, min_neff: float, min_std: float) -> tuple[np.ndarray, np.ndarray]:
    """(D-5f) weighted ZNCC per row (cell). a, b: (n, S) grey samples; both: (n, S) visible in both views; weights: (S,);
    valid_count: (n,) number of window samples the candidate has at all.  Returns rho (NaN where invalid) and the validity mask."""
    w = weights[None, :] * both
    sw = w.sum(axis=1)
    vis_frac = both.sum(axis=1) / np.maximum(valid_count, 1)
    with np.errstate(invalid="ignore", divide="ignore"):
        ma = (w * a).sum(axis=1) / sw; mb = (w * b).sum(axis=1) / sw
        da = a - ma[:, None]; db = b - mb[:, None]
        va = (w * da * da).sum(axis=1); vb = (w * db * db).sum(axis=1); cov = (w * da * db).sum(axis=1)
        rho = cov / np.sqrt(va * vb)
        neff = sw * sw / (w * w).sum(axis=1)
        std_a = np.sqrt(va / sw); std_b = np.sqrt(vb / sw)
    valid = (valid_count > 0) & (vis_frac >= min_visible_fraction) & (neff >= min_neff) & (std_a >= min_std) & (std_b >= min_std) & np.isfinite(rho)
    rho = np.where(valid, rho, np.nan)
    return rho.astype(np.float32), valid


def fisher_mean(rho: np.ndarray, clip: float) -> float:
    return float(np.tanh(np.mean(np.arctanh(np.clip(rho, -clip, clip)))))


def rank_auc(positive: np.ndarray, negative: np.ndarray) -> float | None:
    """P(positive > negative) + 0.5 P(equal): the Mann-Whitney AUC of separating the unshifted from the shifted scores."""
    if len(positive) < 5 or len(negative) < 5:
        return None
    pos = positive[:, None]; neg = negative[None, :]
    return float(((pos > neg).sum() + 0.5 * (pos == neg).sum()) / (len(positive) * len(negative)))


def depth_edge_pixels(depth: np.ndarray, jump: float) -> tuple[np.ndarray, np.ndarray]:
    """(D-6a) pixels on the nearer side of a depth discontinuity > jump between two valid 4-neighbours; returns (rows, cols)."""
    valid = np.isfinite(depth)
    d = np.where(valid, depth, 0.0)
    rows, cols = [], []
    h = valid[:, :-1] & valid[:, 1:] & (np.abs(d[:, 1:] - d[:, :-1]) > jump)
    r, c = np.nonzero(h)
    nearer_right = depth[r, c + 1] < depth[r, c]
    rows.append(r); cols.append(np.where(nearer_right, c + 1, c))
    v = valid[:-1, :] & valid[1:, :] & (np.abs(d[1:, :] - d[:-1, :]) > jump)
    r, c = np.nonzero(v)
    nearer_down = depth[r + 1, c] < depth[r, c]
    rows.append(np.where(nearer_down, r + 1, r)); cols.append(c)
    return np.concatenate(rows), np.concatenate(cols)


def image_edge_distance(gray: np.ndarray, blur_sigma: float, low: int, high: int) -> np.ndarray:
    """(D-6b) distance transform (px) to the Canny edges of the blurred grey image."""
    import cv2
    blurred = cv2.GaussianBlur(gray, (0, 0), blur_sigma) if blur_sigma > 0 else gray
    edges = cv2.Canny(blurred, low, high)
    return cv2.distanceTransform((edges == 0).astype(np.uint8), cv2.DIST_L2, 5)


def eval_expectations(summary: dict[str, dict[str, Any]], controls: dict[str, Any], expectations: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    """Mechanical check of the pre-registered expectation table (D-5.8) against the per-state summary.  ``expectations[state]["delta_sign"]``
    (+1 default) says which candidate the images are expected to support in PRIOR_ABOVE cells: +1 = M (surface gone, pilot prism),
    -1 = P (MVS wrong / low, H_M site)."""
    result = {}
    sign = int((expectations or {}).get("PRIOR_ABOVE", {}).get("delta_sign", 1))
    def get(state, key):
        s = summary.get(state); return None if not s else s.get(key)
    checks: dict[str, dict[str, Any]] = {}
    c = get("COMPATIBLE", "planar")
    if c:
        checks["COMPATIBLE"] = {
            "visibility n_pairs(M) median < 10": None if c["n_pairs_m_median"] is None else bool(c["n_pairs_m_median"] < 10),
            "visibility P_2Da(M) majority": bool(c["power_m_fraction"] >= 0.5),
            "2D-a S_M >= 0.6": None if c["ncc_median_m"] is None else bool(c["ncc_median_m"] >= 0.6),
            "2D-a |delta| <= 0.1": None if c["delta_median"] is None else bool(abs(c["delta_median"]) <= 0.1),
            "2D-a f_M>P ~ f_P>M (both < 0.5)": None if c["f_m_over_p_median"] is None else bool(c["f_m_over_p_median"] < 0.5 and c["f_p_over_m_median"] < 0.5),
            "2D-b d_M ~ d_P (|diff| <= 1 px)": None if c["edge_dist_median_px_m"] is None or c["edge_dist_median_px_p"] is None else bool(abs(c["edge_dist_median_px_m"] - c["edge_dist_median_px_p"]) <= 1.0),
        }
    p = get("PRIOR_ABOVE", "planar")
    if p and sign >= 0:
        checks["PRIOR_ABOVE"] = {
            "visibility n_views(P) > n_views(M)": bool(p["n_views_p_median"] > p["n_views_m_median"]),
            "2D-a delta >= 0.2": None if p["delta_median"] is None else bool(p["delta_median"] >= 0.2),
            "2D-a f_M>P >= 0.7": None if p["f_m_over_p_median"] is None else bool(p["f_m_over_p_median"] >= 0.7),
            "2D-a S_P <= 0.5": None if p["ncc_median_p"] is None else bool(p["ncc_median_p"] <= 0.5),
            "2D-b d_P > d_M": None if p["edge_dist_median_px_m"] is None or p["edge_dist_median_px_p"] is None else bool(p["edge_dist_median_px_p"] > p["edge_dist_median_px_m"]),
        }
    elif p:  # H_M expectation: the images support the prior surface, not the (low / missing) MVS surface
        checks["PRIOR_ABOVE"] = {
            "visibility n_views(P) > n_views(M)": bool(p["n_views_p_median"] > p["n_views_m_median"]),
            "2D-a delta <= -0.2 (P explains images)": None if p["delta_median"] is None else bool(p["delta_median"] <= -0.2),
            "2D-a f_P>M >= 0.7": None if p["f_p_over_m_median"] is None else bool(p["f_p_over_m_median"] >= 0.7),
            "2D-a S_M <= 0.5": None if p["ncc_median_m"] is None else bool(p["ncc_median_m"] <= 0.5),
            "2D-b d_M > d_P": None if p["edge_dist_median_px_m"] is None or p["edge_dist_median_px_p"] is None else bool(p["edge_dist_median_px_m"] > p["edge_dist_median_px_p"]),
        }
    r = get("CURRENT_ABOVE", "rough")
    if r:
        checks["CURRENT_ABOVE"] = {"2D-a S_M <= 0.6 (rough)": None if r["ncc_median_m"] is None else bool(r["ncc_median_m"] <= 0.6)}
    o = get("PRIOR_ONLY", "all")
    if o:
        checks["PRIOR_ONLY"] = {"visibility n_pairs(M) = 0": bool((o["n_pairs_m_median"] or 0) == 0),
                                "2D-a S_P <= 0.5 or no power": True if o["ncc_median_p"] is None else bool(o["ncc_median_p"] <= 0.5)}
    ctrl = {}
    for name, target in (("M+z2", 0.9), ("M+z1", 0.75), ("M+z0.5", 0.6)):
        auc = controls.get(name, {}).get("auc")
        ctrl[f"AUC({name}) >= {target}"] = None if auc is None else bool(auc >= target)
    auc_x = controls.get("M+x1", {}).get("auc")
    ctrl["AUC(M+x1) ~ 0.5 (|AUC-0.5| <= 0.15)"] = None if auc_x is None else bool(abs(auc_x - 0.5) <= 0.15)
    checks["CONTROLS"] = ctrl
    paired = {}
    for name, target in (("M+z2", 0.65), ("M+z1", 0.6), ("M+z0.5", 0.4)):
        f = controls.get(name, {}).get("paired_f_m_over_ctrl")
        paired[f"paired f(M > {name}) >= {target}"] = None if f is None else bool(f >= target)
    fx = controls.get("M+x1", {}).get("paired_f_m_over_ctrl")
    paired["paired f(M > M+x1) <= 0.2"] = None if fx is None else bool(fx <= 0.2)
    checks["CONTROLS_PAIRED_r2"] = paired
    for state, items in checks.items():
        result[state] = {"checks": items, "met": int(sum(1 for v in items.values() if v is True)),
                         "total": int(sum(1 for v in items.values() if v is not None)), "undecidable": int(sum(1 for v in items.values() if v is None))}
    return result


# ----------------------------------------------------------------------------
# pipeline
# ----------------------------------------------------------------------------

def build_warp_ncc(cfg: dict[str, Any], t1_cells: np.ndarray, top: np.ndarray, tile_mvs: np.ndarray, cameras: dict, images: dict,
                   view_ids: list[int], image_loader, chip_writer=None, progress=None) -> dict[str, Any]:
    alg = cfg["algorithm"]; domain = cfg["domain"]; cell = float(alg["cell_size_m"])
    low, high = eb.domain_bounds(domain)
    nx = int(np.ceil((high[0] - low[0]) / cell)); ny = int(np.ceil((high[1] - low[1]) / cell))
    n_cells = len(t1_cells)
    if len(top) != n_cells or np.any(top["ix"] != t1_cells["ix"]) or np.any(top["iy"] != t1_cells["iy"]):
        raise RuntimeError("T1 cells and pairing top-layer cells are not the same ordered set")
    cell_of = np.full((ny, nx), -1, dtype=np.int64); cell_of[top["iy"], top["ix"]] = np.arange(n_cells)
    grids = height_grids(top, nx, ny)
    # ---- candidates (D-5a, D-5b): name -> (grid, shift)
    cands: list[tuple[str, np.ndarray, np.ndarray]] = [("M", grids["M"], np.zeros(3)), ("P", grids["P"], np.zeros(3))]
    for ctrl in alg["controls"]:
        cands.append((ctrl["name"], grids[ctrl["base"]], np.asarray(ctrl["shift_xyz_m"], dtype=np.float64)))
    names = [c[0] for c in cands]; n_cand = len(cands)
    # ---- window samples (D-5c)
    win = alg["window"]
    ox, oy, weights = window_offsets(float(win["half_size_m"]), float(win["sample_step_m"]), float(win["gaussian_sigma_m"]))
    S = len(weights); side = int(round(np.sqrt(S)))
    cx = low[0] + (t1_cells["ix"] + 0.5) * cell; cy = low[1] + (t1_cells["iy"] + 0.5) * cell
    sx = (cx[:, None] + ox[None, :]).ravel(); sy = (cy[:, None] + oy[None, :]).ravel()
    sample_xyz = []; sample_ok = []
    for name, grid, shift in cands:
        z = bilinear_grid(grid, sx, sy, low, cell)
        ok = np.isfinite(z).reshape(n_cells, S)
        xyz = np.column_stack((sx + shift[0], sy + shift[1], np.where(np.isfinite(z), z, 0.0) + shift[2]))
        sample_xyz.append(xyz); sample_ok.append(ok)
    valid_count = [ok.sum(axis=1) for ok in sample_ok]
    # ---- dense height-field renders (D-5d) and cell labels for the edge attribution (D-6a)
    vis = alg["visibility"]; hstep = float(vis["height_field_step_m"]); ss = int(vis["zbuffer_supersample"]); tol = float(vis["tolerance_m"])
    gx = np.arange(low[0] + hstep / 2, high[0], hstep); gy = np.arange(low[1] + hstep / 2, high[1], hstep)
    GX, GY = np.meshgrid(gx, gy); GX = GX.ravel(); GY = GY.ravel()
    gix = np.floor((GX - low[0]) / cell).astype(np.int64); giy = np.floor((GY - low[1]) / cell).astype(np.int64)
    dense_label_all = cell_of[np.clip(giy, 0, ny - 1), np.clip(gix, 0, nx - 1)]
    dense = []; dense_labels = []
    for name, grid, shift in cands:
        z = bilinear_grid(grid, GX, GY, low, cell); ok = np.isfinite(z)
        dense.append(np.column_stack((GX[ok] + shift[0], GY[ok] + shift[1], z[ok] + shift[2])))
        dense_labels.append(dense_label_all[ok])
    outside = tile_mvs[~eb.domain_mask(tile_mvs.astype(np.float64), domain)][::int(vis["outside_occluder_point_stride"])].astype(np.float64)
    # ---- per-view pass: luminance samples, visibility, edges
    cam0 = cameras[images[view_ids[0]].camera_id]; K = cam0.K(); W, H = cam0.width, cam0.height
    n_views = len(view_ids)
    lum = np.zeros((n_cand, n_views, n_cells, S), dtype=np.float16)
    seen = np.zeros((n_cand, n_views, n_cells, S), dtype=bool)
    view_valid = np.zeros((n_cand, n_views, n_cells), dtype=bool)
    centres: dict[int, np.ndarray] = {}
    edge_px_lists: list[dict[int, list[float]]] = [{}, {}]; edge_m_lists: list[dict[int, list[float]]] = [{}, {}]
    edge_cfg = alg["edges"]; focal = float(K[0, 0])
    view_records = []
    min_vis_frac = float(win["min_visible_fraction"])
    for vi, iid in enumerate(view_ids):
        im = images[iid]; cam = cameras[im.camera_id]
        if cam.width != W or cam.height != H:
            raise RuntimeError("all views must share the frozen camera model")
        R, t = im.R(), im.tvec; centres[iid] = -R.T @ t
        gray = image_loader(iid)
        z_out = zbuffer_depth(outside, R, t, K, W, H, 1, 0)
        dist_img = None
        rec = {"colmap_image_id": int(iid), "name": im.name}
        for ci, (name, grid, shift) in enumerate(cands):
            z_self = zbuffer_depth(dense[ci], R, t, K, W, H, ss, int(vis["self_splat_fine_px"]))
            u, v, z, pxf, pyf, inside_f = project_pixels(sample_xyz[ci], R, t, K, W, H, ss)
            px1 = np.floor(u + 0.5).astype(np.int64); py1 = np.floor(v + 0.5).astype(np.int64)
            inside = (z > 1e-6) & (u >= 1.0) & (u < W - 2.0) & (v >= 1.0) & (v < H - 2.0)
            pxf_c = np.clip(pxf, 0, ss * W - 1); pyf_c = np.clip(pyf, 0, ss * H - 1)
            px1_c = np.clip(px1, 0, W - 1); py1_c = np.clip(py1, 0, H - 1)
            self_occ = z > z_self[pyf_c, pxf_c] + tol
            out_occ = z > z_out[py1_c, px1_c] + tol
            visible = inside & ~self_occ & ~out_occ & sample_ok[ci].ravel()
            val = np.zeros(len(u), dtype=np.float32)
            val[inside] = bilinear_image(gray, u[inside], v[inside])
            lum[ci, vi] = val.reshape(n_cells, S).astype(np.float16)
            seen[ci, vi] = visible.reshape(n_cells, S)
            frac = seen[ci, vi].sum(axis=1) / np.maximum(valid_count[ci], 1)
            view_valid[ci, vi] = (valid_count[ci] > 0) & (frac >= min_vis_frac)
            rec[f"cells_valid_{name}"] = int(view_valid[ci, vi].sum())
            if ci < 2:  # 2D-b on the real candidates only
                depth_img = z_self.reshape(H, ss, W, ss).min(axis=(1, 3))
                _, label_img = eb.zbuffer(dense[ci], dense_labels[ci], R, t, K, W, H, 0)
                er, ec = depth_edge_pixels(depth_img, float(edge_cfg["depth_jump_m"]))
                if len(er):
                    if dist_img is None:
                        dist_img = image_edge_distance(gray, float(edge_cfg["blur_sigma_px"]), int(edge_cfg["canny_low"]), int(edge_cfg["canny_high"]))
                    labels = label_img[er, ec]
                    keep = labels >= 0
                    er, ec, labels = er[keep], ec[keep], labels[keep]
                    # only edges of surfaces that are not hidden behind outside occluders
                    keep = ~(depth_img[er, ec] > z_out[er, ec] + tol)
                    er, ec, labels = er[keep], ec[keep], labels[keep]
                    d_px = np.minimum(dist_img[er, ec], float(edge_cfg["max_distance_px"]))
                    d_m = d_px * depth_img[er, ec] / focal
                    order = np.argsort(labels, kind="stable")
                    for lab, dpx, dm in zip(labels[order], d_px[order], d_m[order]):
                        edge_px_lists[ci].setdefault(int(lab), []).append(float(dpx)); edge_m_lists[ci].setdefault(int(lab), []).append(float(dm))
                rec[f"edge_px_{name}"] = int(len(er))
        view_records.append(rec)
        if progress:
            progress(vi + 1, n_views)
    # ---- pairs (D-5e)
    ref = np.array([(low[0] + high[0]) / 2, (low[1] + high[1]) / 2, float(np.nanmedian(grids["M"]))])
    pr = alg["pairs"]
    pairs = select_pairs(view_ids, centres, ref, float(pr["min_angle_deg"]), float(pr["max_angle_deg"]), float(pr["max_distance_ratio"]))
    n_pairs = len(pairs)
    ncc_cfg = alg["ncc"]
    rho_all = np.full((n_pairs, n_cells, n_cand), np.nan, dtype=np.float16)
    for pi_, (ai, bi, ang, ratio) in enumerate(pairs):
        for ci in range(n_cand):
            both = seen[ci, ai] & seen[ci, bi]
            rows = np.flatnonzero(view_valid[ci, ai] & view_valid[ci, bi])
            if not len(rows):
                continue
            a = lum[ci, ai][rows].astype(np.float32); b = lum[ci, bi][rows].astype(np.float32)
            rho, ok = weighted_zncc_batch(a, b, both[rows], weights, valid_count[ci][rows], min_vis_frac,
                                          float(win["min_effective_samples"]), float(ncc_cfg["min_weighted_std_grey"]))
            rho_all[pi_, rows, ci] = rho.astype(np.float16)
    # ---- per-cell statistics (D-5g, D-5h, D-5i)
    pair_angles = np.array([p[2] for p in pairs], dtype=np.float64)
    rho64 = rho_all.astype(np.float32)
    cells = np.zeros(n_cells, dtype=CELL_DTYPE)
    for f in ("ix", "iy", "state", "rough", "mvs_patch", "als_patch"):
        cells[f] = t1_cells[f]
    cells["n_samples_m"], cells["n_samples_p"] = valid_count[0], valid_count[1]
    cells["n_views_m"], cells["n_views_p"] = view_valid[0].sum(axis=0), view_valid[1].sum(axis=0)
    good_thr = float(ncc_cfg["good_threshold"]); margin = float(ncc_cfg["contrast_margin"]); clip = float(ncc_cfg["fisher_clip"])
    min_pairs = int(ncc_cfg["min_pairs_power"]); target_angle = float(alg["chips"]["target_angle_deg"])
    band_max = float(ncc_cfg["summary_angle_max_deg"])
    band = pair_angles <= band_max  # (D-5g r2) summary statistics, power, controls and chips use the discriminative band; the bank keeps every pair
    for i in range(n_cells):
        rm_all = rho64[:, i, 0]; rp_all = rho64[:, i, 1]
        rm = np.where(band, rm_all, np.nan); rp = np.where(band, rp_all, np.nan)
        vm = np.isfinite(rm); vp = np.isfinite(rp)
        vmw = np.isfinite(rm_all); vpw = np.isfinite(rp_all)
        cells["n_pairs_wide_m"][i] = int(vmw.sum()); cells["n_pairs_wide_p"][i] = int(vpw.sum())
        cells["ncc_median_wide_m"][i] = np.median(rm_all[vmw]) if vmw.any() else np.nan
        cells["ncc_median_wide_p"][i] = np.median(rp_all[vpw]) if vpw.any() else np.nan
        cw = vmw & vpw; cells["n_pairs_common_wide"][i] = int(cw.sum())
        cells["delta_median_wide"][i] = np.median((rm_all - rp_all)[cw]) if cw.any() else np.nan
        for suffix, r_, v_ in (("m", rm, vm), ("p", rp, vp)):
            n = int(v_.sum()); cells[f"n_pairs_{suffix}"][i] = n
            if n:
                vals = r_[v_]
                cells[f"ncc_median_{suffix}"][i] = np.median(vals); cells[f"ncc_fisher_{suffix}"][i] = fisher_mean(vals, clip)
                cells[f"f_good_{suffix}"][i] = np.mean(vals >= good_thr); cells[f"angle_median_{suffix}"][i] = np.median(pair_angles[v_])
            else:
                cells[f"ncc_median_{suffix}"][i] = np.nan; cells[f"ncc_fisher_{suffix}"][i] = np.nan; cells[f"f_good_{suffix}"][i] = np.nan; cells[f"angle_median_{suffix}"][i] = np.nan
        common = vm & vp; nc = int(common.sum()); cells["n_pairs_common"][i] = nc
        if nc:
            d = rm[common] - rp[common]
            cells["delta_median"][i] = np.median(d); cells["f_m_over_p"][i] = np.mean(d > margin); cells["f_p_over_m"][i] = np.mean(d < -margin)
        else:
            cells["delta_median"][i] = np.nan; cells["f_m_over_p"][i] = np.nan; cells["f_p_over_m"][i] = np.nan
        for k in range(N_CONTROLS):
            rc = np.where(band, rho64[:, i, 2 + k], np.nan); vc = np.isfinite(rc); cells["n_pairs_ctrl"][i, k] = int(vc.sum())
            cells["ncc_median_ctrl"][i, k] = np.median(rc[vc]) if vc.any() else np.nan
        for ci, suffix in ((0, "m"), (1, "p")):
            lst = edge_px_lists[ci].get(i); lm = edge_m_lists[ci].get(i)
            cells[f"n_edge_px_{suffix}"][i] = len(lst) if lst else 0
            cells[f"edge_dist_median_px_{suffix}"][i] = np.median(lst) if lst else np.nan
            cells[f"edge_dist_median_m_{suffix}"][i] = np.median(lm) if lm else np.nan
        # chip pair: common pair with the angle closest to the target, else M-only, else P-only
        cells["chip_view_a"][i] = -1; cells["chip_view_b"][i] = -1; cells["chip_angle_deg"][i] = np.nan; cells["chip_ncc_m"][i] = np.nan; cells["chip_ncc_p"][i] = np.nan
        for mask in (common, vm, vp):
            if mask.any():
                idx = np.flatnonzero(mask); best = idx[np.argmin(np.abs(pair_angles[idx] - target_angle))]
                cells["chip_view_a"][i] = view_ids[pairs[best][0]]; cells["chip_view_b"][i] = view_ids[pairs[best][1]]
                cells["chip_angle_deg"][i] = pair_angles[best]; cells["chip_ncc_m"][i] = rm[best]; cells["chip_ncc_p"][i] = rp[best]
                if chip_writer is not None:
                    chip_writer(i, best, lum[0, pairs[best][0], i], seen[0, pairs[best][0], i], lum[0, pairs[best][1], i], seen[0, pairs[best][1], i],
                                lum[1, pairs[best][0], i], seen[1, pairs[best][0], i], lum[1, pairs[best][1], i], seen[1, pairs[best][1], i], side)
                break
    cells["power_2da_m"] = cells["n_pairs_m"] >= min_pairs; cells["power_2da_p"] = cells["n_pairs_p"] >= min_pairs
    cells["power_2da_any"] = cells["power_2da_m"] | cells["power_2da_p"]
    cells["power_3da"] = t1_cells["power_3da"]; cells["power_3db"] = t1_cells["power_3db"]; cells["r_t1"] = t1_cells["r"]
    cells["r_t2"] = cells["power_3da"].astype(int) + cells["power_3db"].astype(int) + cells["power_2da_any"].astype(int)
    # ---- patch pairs
    keys = sorted({(int(a), int(b)) for a, b in zip(t1_cells["mvs_patch"], t1_cells["als_patch"])})
    pair_rows = []
    for a, b in keys:
        sel = np.flatnonzero((cells["mvs_patch"] == a) & (cells["als_patch"] == b))
        c = cells[sel]
        if len(c) < 4:
            continue
        rec = np.zeros((), dtype=PAIR_DTYPE)
        rec["mvs_patch"], rec["als_patch"], rec["state"], rec["rough"], rec["cells"] = a, b, c["state"][0], int(c["rough"].max()), len(c)
        pm = c[c["power_2da_m"] == 1]; pp = c[c["power_2da_p"] == 1]; pc = c[c["n_pairs_common"] >= min_pairs]
        rec["cells_power_m"], rec["cells_power_p"] = len(pm), len(pp)
        rec["n_pairs_m"], rec["n_pairs_p"] = int(c["n_pairs_m"].sum()), int(c["n_pairs_p"].sum())
        rec["ncc_median_m"] = np.median(pm["ncc_median_m"]) if len(pm) else np.nan
        rec["ncc_median_p"] = np.median(pp["ncc_median_p"]) if len(pp) else np.nan
        rec["n_pairs_common"] = int(c["n_pairs_common"].sum())
        rec["delta_median"] = np.median(pc["delta_median"]) if len(pc) else np.nan
        rec["f_m_over_p"] = np.median(pc["f_m_over_p"]) if len(pc) else np.nan
        em = c["edge_dist_median_m_m"][np.isfinite(c["edge_dist_median_m_m"])]; ep = c["edge_dist_median_m_p"][np.isfinite(c["edge_dist_median_m_p"])]
        rec["edge_dist_median_m_m"] = np.median(em) if len(em) else np.nan; rec["edge_dist_median_m_p"] = np.median(ep) if len(ep) else np.nan
        rec["power_2da_any"] = int(len(pm) + len(pp) > 0)
        rec["r_t2"] = int(t1_cells["power_3da"][sel].any()) + int(t1_cells["power_3db"][sel].any()) + int(rec["power_2da_any"])
        pair_rows.append(rec)
    pairs_out = np.array(pair_rows, dtype=PAIR_DTYPE) if pair_rows else np.zeros(0, dtype=PAIR_DTYPE)
    # ---- summaries, controls, expectation checks
    summary = summarize(cells)
    controls = control_power(cells, rho64, pair_angles, band_max, names[2:], min_pairs, margin)
    stratified = angle_stratified(cells, rho64, pair_angles, names, margin)
    angle_hist = np.histogram(pair_angles, bins=[3, 10, 20, 30, 45, 60])[0].tolist() if n_pairs else []
    evaluation = eval_expectations(summary, controls, cfg.get("expectations_before_run"))
    return {"cells": cells, "pairs": pairs_out, "rho": rho_all, "views": view_records, "pair_list": [(view_ids[a], view_ids[b], ang, ratio) for a, b, ang, ratio in pairs],
            "summary": summary, "controls": controls, "stratified": stratified, "evaluation": evaluation,
            "angle_hist": {"bins_deg": [3, 10, 20, 30, 45, 60], "counts": angle_hist, "summary_band_max_deg": band_max},
            "candidate_names": names, "window_side": side}


def _nanmed(values: np.ndarray) -> float | None:
    v = values[np.isfinite(values)]
    return float(np.median(v)) if len(v) else None


def summarize(cells: np.ndarray) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for k, name in STATE_NAMES.items():
        st = cells[cells["state"] == k]
        if not len(st):
            continue
        out[name] = {}
        for split, sel in (("all", st), ("planar", st[st["rough"] == 0]), ("rough", st[st["rough"] == 1])):
            if not len(sel):
                continue
            pm = sel[sel["power_2da_m"] == 1]; pp = sel[sel["power_2da_p"] == 1]; pc = sel[sel["n_pairs_common"] >= 1]
            out[name][split] = {
                "cells": int(len(sel)), "area_m2": float(len(sel) * 0.25),
                "n_views_m_median": float(np.median(sel["n_views_m"])), "n_views_p_median": float(np.median(sel["n_views_p"])),
                "n_pairs_m_median": float(np.median(sel["n_pairs_m"])), "n_pairs_p_median": float(np.median(sel["n_pairs_p"])),
                "power_m_fraction": float(np.mean(sel["power_2da_m"])), "power_p_fraction": float(np.mean(sel["power_2da_p"])), "power_any_fraction": float(np.mean(sel["power_2da_any"])),
                "ncc_median_m": _nanmed(pm["ncc_median_m"]), "ncc_median_p": _nanmed(pp["ncc_median_p"]),
                "n_pairs_wide_m_median": float(np.median(sel["n_pairs_wide_m"])), "n_pairs_wide_p_median": float(np.median(sel["n_pairs_wide_p"])),
                "ncc_median_wide_m": _nanmed(sel["ncc_median_wide_m"][sel["n_pairs_wide_m"] >= 3]), "ncc_median_wide_p": _nanmed(sel["ncc_median_wide_p"][sel["n_pairs_wide_p"] >= 3]),
                "delta_median_wide": _nanmed(sel["delta_median_wide"][sel["n_pairs_common_wide"] >= 1]),
                "f_good_m_median": _nanmed(pm["f_good_m"]), "f_good_p_median": _nanmed(pp["f_good_p"]),
                "angle_median_m": _nanmed(pm["angle_median_m"]), "angle_median_p": _nanmed(pp["angle_median_p"]),
                "cells_with_common_pairs": int(len(pc)), "delta_median": _nanmed(pc["delta_median"]),
                "f_m_over_p_median": _nanmed(pc["f_m_over_p"]), "f_p_over_m_median": _nanmed(pc["f_p_over_m"]),
                "edge_dist_median_px_m": _nanmed(sel["edge_dist_median_px_m"]), "edge_dist_median_px_p": _nanmed(sel["edge_dist_median_px_p"]),
                "edge_dist_median_m_m": _nanmed(sel["edge_dist_median_m_m"]), "edge_dist_median_m_p": _nanmed(sel["edge_dist_median_m_p"]),
                "n_edge_px_m": int(sel["n_edge_px_m"].sum()), "n_edge_px_p": int(sel["n_edge_px_p"].sum()),
                "r_t1_distribution": {str(v): int(np.count_nonzero(sel["r_t1"] == v)) for v in range(4)},
                "r_t2_distribution": {str(v): int(np.count_nonzero(sel["r_t2"] == v)) for v in range(4)},
            }
    return out


def control_power(cells: np.ndarray, rho: np.ndarray, pair_angles: np.ndarray, band_max: float, control_names: list[str], min_pairs: int, margin: float) -> dict[str, Any]:
    """(D-5.7) on COMPATIBLE planar cells: cell-level rank AUC of S_M over S_ctrl (pre-registered form) and, since r2, the paired per-pair
    statistics in the summary band (median of rho_M - rho_ctrl over the pairs where both are valid and the fraction above the margin)."""
    comp = (cells["state"] == 1) & (cells["rough"] == 0)
    base_idx = np.flatnonzero(comp & (cells["power_2da_m"] == 1))
    band = pair_angles <= band_max
    out = {}
    for k, name in enumerate(control_names):
        sel = cells[base_idx][cells["n_pairs_ctrl"][base_idx, k] >= min_pairs]
        sm = sel["ncc_median_m"]; sc = sel["ncc_median_ctrl"][:, k]
        ok = np.isfinite(sm) & np.isfinite(sc)
        rm = rho[band][:, comp, 0]; rc = rho[band][:, comp, 2 + k]
        both = np.isfinite(rm) & np.isfinite(rc)
        d = (rm - rc)[both]
        out[name] = {"cells": int(ok.sum()), "auc": rank_auc(sm[ok], sc[ok]),
                     "paired_drop_fraction": float(np.mean(sc[ok] < sm[ok] - margin)) if ok.any() else None,
                     "ncc_median_m": _nanmed(sm[ok]), "ncc_median_ctrl": _nanmed(sc[ok]),
                     "paired_pairs": int(both.sum()), "paired_delta_median": float(np.median(d)) if len(d) else None,
                     "paired_f_m_over_ctrl": float(np.mean(d > margin)) if len(d) else None}
    out["note"] = ("AUC = P(S_M > S_ctrl) over COMPATIBLE planar cells with power for both (pre-registered form); paired_* = per view pair in the "
                   "summary band, pooled over COMPATIBLE planar cells. A horizontal shift of a horizontal plane is unobservable by design (§7).")
    out["summary_band_max_deg"] = float(band_max)
    out["cells_powered_planar_all_states"] = int(np.count_nonzero((cells["rough"] == 0) & (cells["power_2da_m"] == 1)))
    return out


def angle_stratified(cells: np.ndarray, rho: np.ndarray, pair_angles: np.ndarray, names: list[str], margin: float,
                     bins: tuple[float, ...] = (3, 10, 20, 30, 45, 60)) -> dict[str, Any]:
    """Per angle bin: valid counts, median rho per candidate, paired M-P contrast and paired M-control contrasts, for the two planar reference
    populations. This is the table that decided the r2 summary band and is the T3 calibration sample."""
    out: dict[str, Any] = {"bins_deg": list(bins), "populations": {}}
    for label, sel in (("COMPATIBLE_planar", (cells["state"] == 1) & (cells["rough"] == 0)), ("PRIOR_ABOVE_planar", (cells["state"] == 2) & (cells["rough"] == 0))):
        rows = []
        for lo, hi in zip(bins[:-1], bins[1:]):
            pm = (pair_angles >= lo) & (pair_angles < hi)
            r = rho[pm][:, sel, :]
            vm = np.isfinite(r[:, :, 0]); vp = np.isfinite(r[:, :, 1]); both = vm & vp
            row: dict[str, Any] = {"angle_deg": [float(lo), float(hi)], "valid_m": int(vm.sum()), "valid_p": int(vp.sum()),
                                   "rho_median_m": float(np.median(r[:, :, 0][vm])) if vm.any() else None,
                                   "rho_median_p": float(np.median(r[:, :, 1][vp])) if vp.any() else None,
                                   "common": int(both.sum())}
            if both.any():
                d = (r[:, :, 0] - r[:, :, 1])[both]
                row.update({"delta_median": float(np.median(d)), "f_m_over_p": float(np.mean(d > margin)), "f_p_over_m": float(np.mean(d < -margin))})
            for k, name in enumerate(names[2:], start=2):
                bc = vm & np.isfinite(r[:, :, k])
                if bc.any():
                    d = (r[:, :, 0] - r[:, :, k])[bc]
                    row[f"ctrl_{name}"] = {"pairs": int(bc.sum()), "delta_median": float(np.median(d)), "f_m_over_ctrl": float(np.mean(d > margin))}
            rows.append(row)
        out["populations"][label] = {"cells": int(sel.sum()), "rows": rows}
    return out


# ----------------------------------------------------------------------------
# I/O
# ----------------------------------------------------------------------------

def verify(path: Path, expected_sha: str, label: str) -> None:
    if not path.is_file() or sha256(path) != expected_sha:
        raise RuntimeError(f"input drift: {label}")


def resolve_inputs(cfg: dict[str, Any]) -> dict[str, Any]:
    root = Path(cfg["artifact_root"]); inp = cfg["inputs"]
    t1 = root / inp["evidence_bank_relative_root"]
    verify(t1 / "artifact_manifest.json", inp["evidence_bank_artifact_manifest_sha256"], "evidence bank manifest")
    verify(t1 / "validation_receipt.json", inp["evidence_bank_validation_receipt_sha256"], "evidence bank receipt")
    receipt = json.loads((t1 / "validation_receipt.json").read_text(encoding="utf-8"))
    if receipt.get("artifact_manifest_sha256") != sha256(t1 / "artifact_manifest.json") or any(v != "PASS" for v in receipt["checks"].values()):
        raise RuntimeError("evidence bank receipt not bound or not PASS")
    manifest = json.loads((t1 / "artifact_manifest.json").read_text(encoding="utf-8"))
    if manifest.get("task_id") != inp["evidence_bank_task_id"] or manifest.get("scientific_verdict", "missing") is not None:
        raise RuntimeError("evidence bank manifest contract drift")
    for name, item in manifest["outputs"].items():
        p = t1 / name
        if p.stat().st_size != int(item["bytes"]) or sha256(p) != item["sha256"]:
            raise RuntimeError(f"evidence bank output drift: {name}")
    pair_root = root / inp["pairing_relative_root"]
    verify(pair_root / "artifact_manifest.json", inp["pairing_artifact_manifest_sha256"], "pairing manifest")
    pm = json.loads((pair_root / "artifact_manifest.json").read_text(encoding="utf-8"))
    for name in ("pair_cells.npy",):
        item = pm["outputs"][name]; p = pair_root / name
        if p.stat().st_size != int(item["bytes"]) or sha256(p) != item["sha256"]:
            raise RuntimeError(f"pairing output drift: {name}")
    rel = root / inp["source_relation_relative_root"]
    verify(rel / inp["partitions"]["mvs"]["relative_path"], inp["partitions"]["mvs"]["sha256"], "partition mvs")
    cam = inp["current_cameras"]; cam_root = root / cam["camera_root_relative_path"]
    verify(cam_root / "sparse/cameras.bin", cam["cameras_bin_sha256"], "cameras.bin")
    verify(cam_root / "sparse/images.bin", cam["images_bin_sha256"], "images.bin")
    verify(REPO / cam["exact_937_crosswalk_git_relative_path"], cam["exact_937_crosswalk_sha256"], "crosswalk")
    return {"evidence_bank_root": str(t1), "pairing_root": str(pair_root), "relation_root": str(rel), "camera_root": str(cam_root),
            "evidence_bank_manifest_sha256": inp["evidence_bank_artifact_manifest_sha256"], "pairing_manifest_sha256": inp["pairing_artifact_manifest_sha256"]}


def load_everything(cfg: dict[str, Any], resolved: dict[str, Any]):
    inp = cfg["inputs"]
    t1 = Path(resolved["evidence_bank_root"]); pair_root = Path(resolved["pairing_root"]); rel = Path(resolved["relation_root"]); cam_root = Path(resolved["camera_root"])
    t1_cells = np.load(t1 / "evidence_cells.npy", allow_pickle=False)
    views_doc = json.loads((t1 / "evidence_views.json").read_text(encoding="utf-8"))
    view_ids = [int(v["colmap_image_id"]) for v in views_doc["views"]]
    view_hashes = {int(v["colmap_image_id"]): v["image_sha256"] for v in views_doc["views"]}
    pair_cells = np.load(pair_root / "pair_cells.npy", allow_pickle=False)
    top = pair_cells[pair_cells["layer"] == 0]
    tile_mvs = eb.read_xyz_bin(rel / inp["partitions"]["mvs"]["relative_path"])
    cameras = read_cameras_bin(cam_root / "sparse/cameras.bin"); images = read_images_bin(cam_root / "sparse/images.bin")
    crosswalk = json.loads((REPO / inp["current_cameras"]["exact_937_crosswalk_git_relative_path"]).read_text(encoding="utf-8"))
    members = {int(r["colmap_image_id"]) for r in crosswalk["rows"]}
    if not set(view_ids) <= members:
        raise RuntimeError("T1 view list is not a subset of the exact-937 crosswalk")
    return t1_cells, top, tile_mvs, cameras, images, view_ids, view_hashes


def make_image_loader(cam_root: Path, images: dict, expected: dict[int, str], hashes: dict[int, str]):
    import cv2

    def load(iid: int) -> np.ndarray:
        path = cam_root / "images" / images[iid].name
        digest = sha256(path)
        if expected.get(iid) not in (None, digest):
            raise RuntimeError(f"image bytes drift versus the T1 view list: {path.name}")
        hashes[iid] = digest
        bgr = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if bgr is None:
            raise RuntimeError(f"image decode failed: {path}")
        return cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    return load


def make_chip_writer(chip_dir: Path, tile_px: int, index: dict[str, Any]):
    """Writes one PNG per cell: [view a via M | view b via M | view a via P | view b via P] normalised grey tiles (NCC input)."""
    import cv2
    chip_dir.mkdir(parents=True, exist_ok=True)

    def tile(values: np.ndarray, mask: np.ndarray, side: int) -> np.ndarray:
        v = values.astype(np.float32).reshape(side, side); m = mask.reshape(side, side)
        out = np.full((side, side), 96, dtype=np.uint8)
        if m.sum() >= 2:
            lo, hi = float(v[m].min()), float(v[m].max())
            scaled = np.clip((v - lo) / max(hi - lo, 1e-3) * 235 + 10, 0, 255)
            out[m] = scaled[m].astype(np.uint8)
        up = cv2.resize(out, (tile_px, tile_px), interpolation=cv2.INTER_NEAREST)
        return np.flipud(up)  # window rows run south→north; show north up

    def write(cell_index: int, pair_index: int, am, am_ok, bm, bm_ok, ap, ap_ok, bp, bp_ok, side: int) -> None:
        sep = np.full((tile_px, 4), 255, dtype=np.uint8)
        strip = np.concatenate([tile(am, am_ok, side), sep, tile(bm, bm_ok, side), sep, tile(ap, ap_ok, side), sep, tile(bp, bp_ok, side)], axis=1)
        name = f"cell_{cell_index:04d}.png"
        ok, buf = cv2.imencode(".png", strip, [cv2.IMWRITE_PNG_COMPRESSION, 6])
        if not ok:
            raise RuntimeError("chip encode failed")
        atomic_bytes(chip_dir / name, buf.tobytes())
        index[str(cell_index)] = {"file": f"chips/{name}", "pair_index": int(pair_index)}
    return write


def chips_digest(chip_dir: Path) -> tuple[str, int]:
    value = hashlib.sha256(); count = 0
    for p in sorted(chip_dir.glob("cell_*.png")):
        value.update(p.name.encode()); value.update(p.read_bytes()); count += 1
    return value.hexdigest(), count


def cell_grid(cfg: dict[str, Any], cells: np.ndarray, values: np.ndarray, fill=np.nan) -> np.ndarray:
    dom = cfg["domain"]; cell = float(cfg["algorithm"]["cell_size_m"]); low, high = eb.domain_bounds(dom)
    nx = int(np.ceil((high[0] - low[0]) / cell)); ny = int(np.ceil((high[1] - low[1]) / cell))
    g = np.full((ny, nx), fill); g[cells["iy"], cells["ix"]] = values; return g


def write_preview(path: Path, cfg: dict[str, Any], cells: np.ndarray) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    dom = cfg["domain"]
    panels = [("2D-a S_M = median NCC through the current MVS surface", cells["ncc_median_m"], "viridis", -0.2, 1),
              ("2D-a S_P = median NCC through the Existing ALS surface", cells["ncc_median_p"], "viridis", -0.2, 1),
              ("2D-a delta = median(rho_M - rho_P) on common pairs", cells["delta_median"], "coolwarm", -0.8, 0.8),
              ("2D-a f(M > P) on common pairs", cells["f_m_over_p"], "Reds", 0, 1),
              ("valid pairs for M (log10)", np.log10(np.maximum(cells["n_pairs_m"], 0.5)), "magma", -0.3, 3),
              ("2D-b edge distance d_P - d_M (px, + = prior edges unexplained)", cells["edge_dist_median_px_p"] - cells["edge_dist_median_px_m"], "coolwarm", -10, 10)]
    fig, axes = plt.subplots(2, 3, figsize=(21, 13), dpi=100)
    for ax, (title, values, cmap, vmin, vmax) in zip(axes.ravel(), panels):
        im = ax.imshow(cell_grid(cfg, cells, values), origin="lower", extent=[dom["x"][0], dom["x"][1], dom["y"][0], dom["y"][1]], cmap=cmap, vmin=vmin, vmax=vmax)
        ax.set_title(title, fontsize=10); ax.set_aspect("equal"); fig.colorbar(im, ax=ax, fraction=0.046)
    fig.suptitle("T2 warp-NCC on the pilot prism (XY cells, top layer). Evidence only, no verdict.", fontsize=12)
    fig.tight_layout(); path.parent.mkdir(parents=True, exist_ok=True); fig.savefig(path); plt.close(fig)


def write_on_image(path: Path, cfg: dict[str, Any], cells: np.ndarray, top: np.ndarray, cameras: dict, images: dict, view_id: int, gray: np.ndarray) -> dict[str, Any]:
    """Paint per-cell 2D-a values on the current TOP image through the M height field (display only)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    alg = cfg["algorithm"]; cell = float(alg["cell_size_m"]); low, high = eb.domain_bounds(cfg["domain"])
    nx = int(np.ceil((high[0] - low[0]) / cell)); ny = int(np.ceil((high[1] - low[1]) / cell))
    grids = height_grids(top, nx, ny)
    step = 0.0625
    gx = np.arange(low[0] + step / 2, high[0], step); gy = np.arange(low[1] + step / 2, high[1], step)
    GX, GY = np.meshgrid(gx, gy); GX = GX.ravel(); GY = GY.ravel()
    z = bilinear_grid(grids["M"], GX, GY, low, cell); ok = np.isfinite(z)
    cell_of = np.full((ny, nx), -1, dtype=np.int64); cell_of[cells["iy"], cells["ix"]] = np.arange(len(cells))
    lab = cell_of[np.floor((GY[ok] - low[1]) / cell).astype(int), np.floor((GX[ok] - low[0]) / cell).astype(int)]
    im = images[view_id]; cam = cameras[im.camera_id]; K = cam.K(); W, H = cam.width, cam.height
    u, v, zc, px, py, inside = project_pixels(np.column_stack((GX[ok], GY[ok], z[ok])), im.R(), im.tvec, K, W, H, 1)
    keep = inside & (lab >= 0)
    px, py, lab = px[keep], py[keep], lab[keep]
    x0, x1 = max(0, px.min() - 20), min(W, px.max() + 20); y0, y1 = max(0, py.min() - 20), min(H, py.max() + 20)
    base = np.repeat(gray[y0:y1, x0:x1, None].astype(np.float32) / 255.0, 3, axis=2)
    panels = [("S_M (NCC through current MVS)", cells["ncc_median_m"], "viridis", -0.2, 1), ("S_P (NCC through Existing ALS)", cells["ncc_median_p"], "viridis", -0.2, 1),
              ("delta = rho_M - rho_P (common pairs)", cells["delta_median"], "coolwarm", -0.8, 0.8)]
    fig, axes = plt.subplots(1, 3, figsize=(24, 8.4), dpi=100)
    for ax, (title, values, cmap, vmin, vmax) in zip(axes, panels):
        val = values[lab].astype(np.float64); fin = np.isfinite(val)
        cm = plt.get_cmap(cmap); col = cm(np.clip((val - vmin) / (vmax - vmin), 0, 1))[:, :3]
        img = base.copy()
        r, c = py[fin] - y0, px[fin] - x0
        img[r, c] = 0.35 * img[r, c] + 0.65 * col[fin]
        ax.imshow(img); ax.set_title(title, fontsize=11); ax.set_xticks([]); ax.set_yticks([])
    fig.suptitle(f"T2 2D-a painted on the current TOP image (COLMAP {view_id}, {im.name}); display only, no verdict", fontsize=12)
    fig.tight_layout(); path.parent.mkdir(parents=True, exist_ok=True); fig.savefig(path); plt.close(fig)
    return {"colmap_image_id": int(view_id), "name": im.name, "roi_xyxy_half_open_px": [int(x0), int(y0), int(x1), int(y1)]}


def run(cfg: dict[str, Any], config_path: Path) -> dict[str, Any]:
    started = time.perf_counter()
    out = Path(cfg["artifact_root"]) / cfg["output_relative_root"]; out.mkdir(parents=True, exist_ok=True)
    resolved = resolve_inputs(cfg)
    t1_cells, top, tile_mvs, cameras, images, view_ids, view_hashes = load_everything(cfg, resolved)
    hashes: dict[int, str] = {}
    loader = make_image_loader(Path(resolved["camera_root"]), images, view_hashes, hashes)
    chip_index: dict[str, Any] = {}
    chip_dir = out / "chips"
    for old in chip_dir.glob("cell_*.png"):
        old.unlink()
    writer = make_chip_writer(chip_dir, int(cfg["algorithm"]["chips"]["tile_px"]), chip_index)
    def progress(done, total):
        if done % 10 == 0 or done == total:
            print(f"view {done}/{total} elapsed {time.perf_counter() - started:.0f}s", flush=True)
    result = build_warp_ncc(cfg, t1_cells, top, tile_mvs, cameras, images, view_ids, loader, chip_writer=writer, progress=progress)
    atomic_npy(out / "warp_ncc_cells.npy", result["cells"]); atomic_npy(out / "warp_ncc_pairs.npy", result["pairs"]); atomic_npy(out / "ncc_pair_values_f16.npy", result["rho"])
    atomic_json(out / "warp_ncc_views.json", {"schema": "jointbuildgs.phd.warp_ncc.views.v1", "view_count": len(view_ids), "candidate_names": result["candidate_names"],
                                              "views": [dict(v, image_sha256=hashes.get(v["colmap_image_id"])) for v in result["views"]],
                                              "pair_count": len(result["pair_list"]), "pair_angle_histogram": result["angle_hist"],
                                              "pairs": [{"a": a, "b": b, "angle_deg": round(ang, 3), "distance_ratio": round(ratio, 3)} for a, b, ang, ratio in result["pair_list"]]})
    atomic_json(out / "chips_index.json", {"schema": "jointbuildgs.phd.warp_ncc.chips.v1", "tile_px": int(cfg["algorithm"]["chips"]["tile_px"]),
                                           "layout": "[view a via M | view b via M | view a via P | view b via P], each tile normalised to its own visible min/max, north up",
                                           "window_side": result["window_side"], "cells": chip_index})
    atomic_json(out / "evaluation.json", {"schema": "jointbuildgs.phd.warp_ncc.evaluation.v1", "expectations_before_run": cfg["expectations_before_run"],
                                          "per_state_summary": result["summary"], "controls": result["controls"], "angle_stratified": result["stratified"],
                                          "expectation_checks": result["evaluation"], "pair_angle_histogram": result["angle_hist"],
                                          "revision_r2": cfg.get("revision_r2"), "scientific_verdict": None})
    write_preview(out / "warp_ncc_preview.png", cfg, result["cells"])
    def off_nadir(iid: int) -> float:
        return float(np.degrees(np.arccos(np.clip(-(images[iid].R().T @ np.array([0.0, 0.0, 1.0]))[2], -1.0, 1.0))))
    top_view = min(view_ids, key=lambda iid: (round(off_nadir(iid), 3), iid))  # most nadir view among the T1 views (display only)
    overlay = write_on_image(out / "warp_ncc_on_image.png", cfg, result["cells"], top, cameras, images, top_view, loader(top_view))
    digest, n_chips = chips_digest(chip_dir)
    technical = {
        "schema": "jointbuildgs.phd.warp_ncc.technical_return.v1", "task_id": cfg["task_id"],
        "status": "COMPLETE_DEVELOPMENT_NON_CONFIRMATORY", "generated_utc": utc_now(), "git_commit": git_head(),
        "config": {"path": str(config_path), "sha256": sha256(config_path)}, "driver": {"path": str(Path(__file__)), "sha256": sha256(Path(__file__))},
        "domain": cfg["domain"], "algorithm": cfg["algorithm"], "view_count": len(view_ids), "pair_count": len(result["pair_list"]),
        "pair_angle_histogram": result["angle_hist"], "per_state_summary": result["summary"], "controls": result["controls"],
        "angle_stratified": result["stratified"], "expectation_checks": result["evaluation"], "revision_r2": cfg.get("revision_r2"),
        "overlay_view": overlay, "chips": {"count": n_chips, "sha256": digest},
        "not_decided_here": cfg["not_decided_here"], "elapsed_seconds": time.perf_counter() - started, "prohibited_inputs_accessed": [], "scientific_verdict": None,
    }
    atomic_json(out / "technical_return.json", technical)
    outputs = {}
    for name in sorted(["warp_ncc_cells.npy", "warp_ncc_pairs.npy", "ncc_pair_values_f16.npy", "warp_ncc_views.json", "chips_index.json", "evaluation.json",
                        "warp_ncc_preview.png", "warp_ncc_on_image.png", "technical_return.json"]):
        p = out / name; outputs[name] = {"path": name, "bytes": p.stat().st_size, "sha256": sha256(p)}
    atomic_json(out / "artifact_manifest.json", {
        "schema": "jointbuildgs.phd.warp_ncc.artifact_manifest.v1", "task_id": cfg["task_id"], "status": "COMPLETE_DEVELOPMENT_NON_CONFIRMATORY",
        "generated_utc": utc_now(), "git_commit": technical["git_commit"], "config": technical["config"], "driver": technical["driver"],
        "inputs": resolved, "outputs": outputs, "chips": {"directory": "chips", "count": n_chips, "sha256": digest},
        "prohibited_inputs_accessed": [], "scientific_verdict": None})
    return technical


def validate(cfg: dict[str, Any], rerun: bool = True) -> dict[str, Any]:
    out = Path(cfg["artifact_root"]) / cfg["output_relative_root"]
    manifest = json.loads((out / "artifact_manifest.json").read_text(encoding="utf-8"))
    checks = {}
    for name, item in manifest["outputs"].items():
        p = out / name
        if p.stat().st_size != int(item["bytes"]) or sha256(p) != item["sha256"]:
            raise AssertionError(f"output hash drift: {name}")
    digest, count = chips_digest(out / "chips")
    if digest != manifest["chips"]["sha256"] or count != int(manifest["chips"]["count"]):
        raise AssertionError("chip digest drift")
    checks["output_hashes"] = "PASS"; checks["chips_digest"] = "PASS"
    resolved = resolve_inputs(cfg)
    checks["input_hashes_and_upstream_binding"] = "PASS"
    cells = np.load(out / "warp_ncc_cells.npy", allow_pickle=False)
    min_pairs = int(cfg["algorithm"]["ncc"]["min_pairs_power"])
    if np.any(cells["n_pairs_common"] > np.minimum(cells["n_pairs_m"], cells["n_pairs_p"])):
        raise AssertionError("common pairs exceed a candidate's pair count")
    if np.any(cells["n_pairs_m"] > cells["n_pairs_wide_m"]) or np.any(cells["n_pairs_p"] > cells["n_pairs_wide_p"]) or np.any(cells["n_pairs_common"] > cells["n_pairs_common_wide"]):
        raise AssertionError("summary-band pair counts exceed the wide-band counts")
    for f in ("f_good_m", "f_good_p", "f_m_over_p", "f_p_over_m"):
        v = cells[f][np.isfinite(cells[f])]
        if np.any(v < 0) or np.any(v > 1):
            raise AssertionError(f"fraction out of range: {f}")
    for f in ("ncc_median_m", "ncc_median_p"):
        v = cells[f][np.isfinite(cells[f])]
        if np.any(np.abs(v) > 1.0001):
            raise AssertionError(f"NCC out of range: {f}")
    if np.any(cells["power_2da_m"] != (cells["n_pairs_m"] >= min_pairs)) or np.any(cells["power_2da_p"] != (cells["n_pairs_p"] >= min_pairs)):
        raise AssertionError("2D-a power drift")
    if np.any(cells["r_t2"] != cells["power_3da"].astype(int) + cells["power_3db"].astype(int) + cells["power_2da_any"].astype(int)):
        raise AssertionError("r_t2 drift")
    if np.any(cells["n_pairs_m"][np.isfinite(cells["ncc_median_m"])] == 0) or np.any(cells["n_pairs_m"][~np.isfinite(cells["ncc_median_m"])] != 0):
        raise AssertionError("NCC / pair count inconsistency")
    checks["cell_consistency"] = "PASS"
    t1_cells = np.load(Path(resolved["evidence_bank_root"]) / "evidence_cells.npy", allow_pickle=False)
    if np.any(t1_cells["ix"] != cells["ix"]) or np.any(t1_cells["iy"] != cells["iy"]) or np.any(t1_cells["r"] != cells["r_t1"]):
        raise AssertionError("T1 cell binding drift")
    checks["t1_cell_binding"] = "PASS"
    if rerun:
        t1_cells, top, tile_mvs, cameras, images, view_ids, view_hashes = load_everything(cfg, resolved)
        loader = make_image_loader(Path(resolved["camera_root"]), images, view_hashes, {})
        again = build_warp_ncc(cfg, t1_cells, top, tile_mvs, cameras, images, view_ids, loader)
        for name, arr in (("warp_ncc_cells.npy", again["cells"]), ("warp_ncc_pairs.npy", again["pairs"]), ("ncc_pair_values_f16.npy", again["rho"])):
            if array_digest(arr) != array_digest(np.load(out / name, allow_pickle=False)):
                raise AssertionError(f"determinism drift: {name}")
        checks["determinism_rerun"] = "PASS"
    technical = json.loads((out / "technical_return.json").read_text(encoding="utf-8"))
    if technical.get("scientific_verdict", "missing") is not None or technical.get("prohibited_inputs_accessed") != []:
        raise AssertionError("technical return contract drift")
    checks["prohibited_inputs"] = "PASS"; checks["scientific_verdict_null"] = "PASS"
    receipt = {"schema": "jointbuildgs.phd.warp_ncc.validation.v1", "task_id": cfg["task_id"], "generated_utc": utc_now(),
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
        print(json.dumps({"views": technical["view_count"], "pairs": technical["pair_count"], "elapsed": technical["elapsed_seconds"],
                          "controls": technical["controls"], "checks": technical["expectation_checks"]}, indent=1))
    if args.command in {"validate", "run-and-validate"}:
        print(json.dumps(validate(cfg, rerun=not args.no_rerun)["checks"], indent=1))


if __name__ == "__main__":
    main()
