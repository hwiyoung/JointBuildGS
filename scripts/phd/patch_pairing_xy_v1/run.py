#!/usr/bin/env python3
"""XY-column (2.5D) pairing of per-source surface patches, with a wall exception.

Same place = same XY cell.  Per cell the TOP surface of each source (and a BOTTOM
surface when a second layer exists) is paired; dz = z_prior - z_current gives a
descriptive state (compatible / prior above / current above / prior only /
current only).  Vertical patches are paired by 3D proximity instead.
No source authority, change, registration or responsibility is decided here.
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
from scipy.spatial import cKDTree


REPO = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = REPO / "configs/phd/patch_pairing_xy_v1/run_v1.json"
SCHEMA = "jointbuildgs.phd.patch_pairing_xy.run.v1"
STATE_EMPTY, STATE_COMPATIBLE, STATE_PRIOR_ABOVE, STATE_CURRENT_ABOVE, STATE_PRIOR_ONLY, STATE_CURRENT_ONLY = 0, 1, 2, 3, 4, 5
STATE_NAMES = {0: "EMPTY", 1: "COMPATIBLE", 2: "PRIOR_ABOVE", 3: "CURRENT_ABOVE", 4: "PRIOR_ONLY", 5: "CURRENT_ONLY"}
STATE_COLORS = {1: "#22c55e", 2: "#ef4444", 3: "#f97316", 4: "#a855f7", 5: "#06b6d4"}
WALL_NONE, WALL_PAIRED, WALL_ONLY = 0, 1, 2
WALL_NAMES = {0: "NOT_A_WALL", 1: "WALL_PAIRED_3D", 2: "WALL_SINGLE_SOURCE"}
PROHIBITED_TOKENS = ("uas", "lod2", "footprint", "stable_id", "journal1", "roster")

CELL_DTYPE = np.dtype([
    ("ix", "<i4"), ("iy", "<i4"), ("layer", "u1"),
    ("mvs_patch", "<i4"), ("als_patch", "<i4"), ("mvs_z", "<f4"), ("als_z", "<f4"), ("dz_m", "<f4"),
    ("state", "u1"), ("rough", "u1"), ("mvs_points", "<u4"), ("als_points", "<u4"),
])
PAIR_DTYPE = np.dtype([
    ("mvs_patch", "<i4"), ("als_patch", "<i4"), ("layer", "u1"), ("cells", "<u4"),
    ("dz_median_m", "<f4"), ("dz_mad_m", "<f4"), ("state", "u1"), ("rough", "u1"),
])
WALL_DTYPE = np.dtype([("source", "u1"), ("patch", "<i4"), ("wall_state", "u1"), ("partner_patch", "<i4"),
                       ("fraction_within", "<f4"), ("points", "<u4")])


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
        raise ValueError("pairing config schema drift")
    if cfg.get("status") != "USER_APPROVED_DEVELOPMENT_NON_CONFIRMATORY":
        raise ValueError("run is not user-approved")
    if cfg.get("scientific_verdict", "missing") is not None:
        raise ValueError("scientific_verdict must remain null")
    serialized = json.dumps({"inputs": {k: v for k, v in cfg["inputs"].items() if k != "display_only_current_image"},
                             "output": cfg["output_relative_root"]}).lower()
    for token in PROHIBITED_TOKENS:
        if token in serialized:
            raise ValueError(f"prohibited input token: {token}")
    a = cfg["algorithm"]
    for key in ("cell_size_m", "layer_gap_m", "wall_pair_distance_m", "same_surface_tolerance_m"):
        if float(a[key]) <= 0:
            raise ValueError(f"{key} must be positive")
    return cfg


# ----------------------------------------------------------------------------
# core
# ----------------------------------------------------------------------------

def column_surfaces(xy: np.ndarray, z: np.ndarray, patch: np.ndarray, is_cluster: np.ndarray, origin: np.ndarray,
                    cell: float, min_points: int, layer_gap: float) -> dict[tuple[int, int], dict[str, Any]]:
    """Per XY cell: TOP and (optional) BOTTOM surface of one source.  Points with patch 0 (noise) are ignored."""
    keep = patch > 0
    if not np.any(keep):
        return {}
    keys = np.floor((xy[keep] - origin) / cell).astype(np.int64)
    pk = patch[keep]; zk = z[keep]; ck = is_cluster[keep]
    combined = np.column_stack((keys, pk))
    order = np.lexsort((zk, pk, keys[:, 1], keys[:, 0]))
    combined = combined[order]; zs = zk[order]; cs = ck[order]
    change = np.ones(len(order), dtype=bool); change[1:] = np.any(combined[1:] != combined[:-1], axis=1)
    starts = np.flatnonzero(change); ends = np.append(starts[1:], len(order))
    out: dict[tuple[int, int], dict[str, Any]] = {}
    for s, e in zip(starts, ends):
        if e - s < min_points:
            continue
        ix, iy, pid = (int(v) for v in combined[s])
        median = float(zs[(s + e) // 2]) if (e - s) % 2 else float(0.5 * (zs[(s + e) // 2 - 1] + zs[(s + e) // 2]))
        entry = out.setdefault((ix, iy), {"patches": []})
        entry["patches"].append((median, pid, int(e - s), bool(cs[s])))
    for entry in out.values():
        entry["patches"].sort(key=lambda t: (-t[0], t[1]))
        top = entry["patches"][0]; bottom = entry["patches"][-1]
        entry["top"] = top
        entry["bottom"] = bottom if (top[0] - bottom[0] > layer_gap) else None
    return out


def pair_columns(mvs_cols: dict, als_cols: dict, tolerance: float) -> np.ndarray:
    keys = sorted(set(mvs_cols) | set(als_cols))
    records = []
    for key in keys:
        m = mvs_cols.get(key); a = als_cols.get(key)
        layers = [("top", 0)]
        if m and a and m["bottom"] is not None and a["bottom"] is not None:
            layers.append(("bottom", 1))
        for name, layer in layers:
            mt = m[name] if m else None; at = a[name] if a else None
            if mt is None and at is None:
                continue
            rec = np.zeros((), dtype=CELL_DTYPE)
            rec["ix"], rec["iy"], rec["layer"] = key[0], key[1], layer
            rec["mvs_patch"] = mt[1] if mt else 0; rec["als_patch"] = at[1] if at else 0
            rec["mvs_z"] = mt[0] if mt else np.nan; rec["als_z"] = at[0] if at else np.nan
            rec["mvs_points"] = mt[2] if mt else 0; rec["als_points"] = at[2] if at else 0
            rec["rough"] = int((mt[3] if mt else False) or (at[3] if at else False))
            if mt and at:
                dz = at[0] - mt[0]; rec["dz_m"] = dz
                rec["state"] = STATE_COMPATIBLE if abs(dz) <= tolerance else (STATE_PRIOR_ABOVE if dz > 0 else STATE_CURRENT_ABOVE)
            else:
                rec["dz_m"] = np.nan
                rec["state"] = STATE_PRIOR_ONLY if at else STATE_CURRENT_ONLY
            records.append(rec)
    return np.array(records, dtype=CELL_DTYPE) if records else np.zeros(0, dtype=CELL_DTYPE)


def aggregate_pairs(cells: np.ndarray, tolerance: float, min_cells: int) -> np.ndarray:
    both = cells[(cells["mvs_patch"] > 0) & (cells["als_patch"] > 0)]
    if not len(both):
        return np.zeros(0, dtype=PAIR_DTYPE)
    keys = np.column_stack((both["mvs_patch"], both["als_patch"], both["layer"])).astype(np.int64)
    uniq, inverse = np.unique(keys, axis=0, return_inverse=True)
    out = []
    for i, (mp, ap, layer) in enumerate(uniq):
        sel = both[inverse.ravel() == i]
        if len(sel) < min_cells:
            continue
        dz = sel["dz_m"].astype(np.float64); med = float(np.median(dz)); mad = float(np.median(np.abs(dz - med)))
        rec = np.zeros((), dtype=PAIR_DTYPE)
        rec["mvs_patch"], rec["als_patch"], rec["layer"], rec["cells"] = mp, ap, layer, len(sel)
        rec["dz_median_m"], rec["dz_mad_m"] = med, mad
        rec["state"] = STATE_COMPATIBLE if abs(med) <= tolerance else (STATE_PRIOR_ABOVE if med > 0 else STATE_CURRENT_ABOVE)
        rec["rough"] = int(np.any(sel["rough"] == 1))
        out.append(rec)
    return np.array(out, dtype=PAIR_DTYPE) if out else np.zeros(0, dtype=PAIR_DTYPE)


def pair_walls(walls_xyz: dict[int, np.ndarray], other_xyz: np.ndarray, other_patch: np.ndarray,
               distance: float, min_fraction: float, source: int, other_eligible: np.ndarray | None = None) -> np.ndarray:
    """3D proximity pairing for vertical patches.  Only partner patches that are not near-horizontal
    (walls, steep faces, scattered clusters) are eligible: the ground next to a wall foot is not its pair."""
    out = []
    if other_eligible is not None and len(other_xyz):
        keep = other_eligible[other_patch]
        other_xyz = other_xyz[keep]; other_patch = other_patch[keep]
    tree = cKDTree(other_xyz) if len(other_xyz) else None
    for pid, pts in sorted(walls_xyz.items()):
        rec = np.zeros((), dtype=WALL_DTYPE)
        rec["source"], rec["patch"], rec["points"] = source, pid, len(pts)
        rec["wall_state"], rec["partner_patch"], rec["fraction_within"] = WALL_ONLY, 0, 0.0
        if tree is not None:
            d, idx = tree.query(pts, k=1, distance_upper_bound=distance)
            hit = np.isfinite(d)
            if np.any(hit):
                partners = other_patch[idx[hit]]; partners = partners[partners > 0]
                if len(partners):
                    ids, counts = np.unique(partners, return_counts=True)
                    best = int(np.argmax(counts)); fraction = counts[best] / len(pts)
                    rec["fraction_within"] = fraction
                    if fraction >= min_fraction:
                        rec["wall_state"], rec["partner_patch"] = WALL_PAIRED, int(ids[best])
        out.append(rec)
    return np.array(out, dtype=WALL_DTYPE) if out else np.zeros(0, dtype=WALL_DTYPE)


def run_pairing(points: dict[str, np.ndarray], per_point: dict[str, np.ndarray], patches: dict[str, np.ndarray],
                domain: dict[str, Any], alg: dict[str, Any]) -> dict[str, Any]:
    origin = np.array([domain["x"][0], domain["y"][0]])
    cell = float(alg["cell_size_m"])
    cols = {}; walls_xyz = {}; wall_ids = {}
    for s in ("mvs", "als"):
        pt = patches[s]; pp = per_point[s]; xyz = points[s]
        is_wall_patch = np.zeros(int(pt["patch_id"].max()) + 1, dtype=bool)
        is_cluster_patch = np.zeros(int(pt["patch_id"].max()) + 1, dtype=bool)
        is_wall_patch[pt["patch_id"]] = (pt["type"] == 1) & (pt["tilt_from_up_deg"] > float(alg["wall_tilt_deg"]))
        is_cluster_patch[pt["patch_id"]] = pt["kind"] == 2
        lab = pp["patch_id"]
        wall_mask = is_wall_patch[lab]
        wall_ids[s] = np.flatnonzero(is_wall_patch)
        walls_xyz[s] = {int(pid): xyz[lab == pid] for pid in wall_ids[s]}
        column_label = np.where(wall_mask, 0, lab)  # walls leave the columns
        cols[s] = column_surfaces(xyz[:, :2], xyz[:, 2], column_label, is_cluster_patch[lab], origin, cell,
                                  int(alg["min_points_per_cell_patch"]), float(alg["layer_gap_m"]))
    cells = pair_columns(cols["mvs"], cols["als"], float(alg["same_surface_tolerance_m"]))
    pairs = aggregate_pairs(cells, float(alg["same_surface_tolerance_m"]), int(alg["min_cells_per_patch_pair"]))
    eligible = {}
    for s in ("mvs", "als"):
        pt = patches[s]; arr = np.zeros(int(pt["patch_id"].max()) + 1, dtype=bool)
        arr[pt["patch_id"]] = (pt["kind"] == 2) | (pt["tilt_from_up_deg"] >= float(alg["wall_partner_min_tilt_deg"]))
        eligible[s] = arr
    walls = np.concatenate([
        pair_walls(walls_xyz["mvs"], points["als"], per_point["als"]["patch_id"], float(alg["wall_pair_distance_m"]), float(alg["wall_pair_min_fraction"]), 0, eligible["als"]),
        pair_walls(walls_xyz["als"], points["mvs"], per_point["mvs"]["patch_id"], float(alg["wall_pair_distance_m"]), float(alg["wall_pair_min_fraction"]), 1, eligible["mvs"]),
    ]) if (walls_xyz["mvs"] or walls_xyz["als"]) else np.zeros(0, dtype=WALL_DTYPE)
    top = cells[cells["layer"] == 0]
    area = cell * cell
    accounting = {
        "cells_top_layer": int(len(top)), "cells_with_second_layer_pair": int(np.count_nonzero(cells["layer"] == 1)),
        "state_area_m2_top": {STATE_NAMES[k]: float(area * np.count_nonzero(top["state"] == k)) for k in range(1, 6)},
        "state_area_m2_top_rough_flagged": {STATE_NAMES[k]: float(area * np.count_nonzero((top["state"] == k) & (top["rough"] == 1))) for k in range(1, 6)},
        "dz_quantiles_both_present_m": {q: float(np.percentile(top["dz_m"][np.isfinite(top["dz_m"])], p)) for q, p in (("p10", 10), ("p50", 50), ("p90", 90))} if np.any(np.isfinite(top["dz_m"])) else {},
        "patch_pairs": int(len(pairs)), "patch_pair_states": {STATE_NAMES[k]: int(np.count_nonzero(pairs["state"] == k)) for k in (1, 2, 3)},
        "walls": {"mvs": int(len(wall_ids["mvs"])), "als": int(len(wall_ids["als"])),
                  "paired_3d": int(np.count_nonzero(walls["wall_state"] == WALL_PAIRED)) if len(walls) else 0,
                  "single_source": int(np.count_nonzero(walls["wall_state"] == WALL_ONLY)) if len(walls) else 0},
    }
    return {"cells": cells, "pairs": pairs, "walls": walls, "accounting": accounting}


# ----------------------------------------------------------------------------
# I/O, preview, run, validate
# ----------------------------------------------------------------------------

def read_xyz_bin(path: Path) -> np.ndarray:
    if path.stat().st_size % 12:
        raise ValueError(f"{path}: invalid xyz_f32le byte count")
    return np.fromfile(path, dtype="<f4").reshape(-1, 3)


def resolve_inputs(cfg: dict[str, Any]) -> tuple[dict[str, Any], Path]:
    root = Path(cfg["artifact_root"])
    patch_root = root / cfg["inputs"]["surface_patch_relative_root"]
    manifest_path = patch_root / "artifact_manifest.json"; receipt_path = patch_root / "validation_receipt.json"
    if sha256(manifest_path) != cfg["inputs"]["surface_patch_artifact_manifest_sha256"]:
        raise RuntimeError("surface-patch artifact manifest drift")
    if sha256(receipt_path) != cfg["inputs"]["surface_patch_validation_receipt_sha256"]:
        raise RuntimeError("surface-patch validation receipt drift")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")); receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if manifest.get("task_id") != cfg["inputs"]["surface_patch_task_id"] or receipt.get("artifact_manifest_sha256") != sha256(manifest_path):
        raise RuntimeError("surface-patch receipt is not bound to its manifest")
    if any(v != "PASS" for v in receipt["checks"].values()):
        raise RuntimeError("surface-patch validation not all PASS")
    resolved = {"surface_patch_artifact_manifest": {"path": str(manifest_path), "sha256": sha256(manifest_path)}}
    for name, item in manifest["outputs"].items():
        p = patch_root / name
        if p.stat().st_size != int(item["bytes"]) or sha256(p) != item["sha256"]:
            raise RuntimeError(f"surface-patch output drift: {name}")
    rel = root / cfg["inputs"]["source_relation_relative_root"]
    for s, item in cfg["inputs"]["partitions"].items():
        p = rel / item["relative_path"]
        if p.stat().st_size != int(item["bytes"]) or sha256(p) != item["sha256"]:
            raise RuntimeError(f"partition drift: {s}")
        resolved[f"partition_{s}"] = {"path": str(p), "sha256": item["sha256"]}
    return resolved, patch_root


def load_sources(cfg: dict[str, Any], patch_root: Path) -> tuple[dict, dict, dict]:
    root = Path(cfg["artifact_root"]); rel = root / cfg["inputs"]["source_relation_relative_root"]
    points, per_point, patches = {}, {}, {}
    for s in ("mvs", "als"):
        xyz = read_xyz_bin(rel / cfg["inputs"]["partitions"][s]["relative_path"])
        rows = np.load(patch_root / f"point_rows_{s}.npy", allow_pickle=False)
        points[s] = xyz[rows].astype(np.float64)
        per_point[s] = np.load(patch_root / f"points_{s}.npy", allow_pickle=False)
        patches[s] = np.load(patch_root / f"patches_{s}.npy", allow_pickle=False)
    return points, per_point, patches


def write_preview(path: Path, cfg: dict[str, Any], result: dict[str, Any], points: dict, per_point: dict) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import to_rgb
    import cv2
    from src.stage2.colmap_io import read_cameras_bin, read_images_bin
    cells = result["cells"]; top = cells[cells["layer"] == 0]
    alg = cfg["algorithm"]; dom = cfg["domain"]; cell = float(alg["cell_size_m"])
    root = Path(cfg["artifact_root"]); disp = cfg["inputs"]["display_only_current_image"]
    cam_root = root / disp["camera_root_relative_path"]
    for name, key in (("sparse/cameras.bin", "cameras_bin_sha256"), ("sparse/images.bin", "images_bin_sha256")):
        if sha256(cam_root / name) != disp[key]:
            raise RuntimeError(f"display camera file drift: {name}")
    rgb_path = root / disp["rgb_crop_relative_path"]
    if sha256(rgb_path) != disp["rgb_crop_sha256"]:
        raise RuntimeError("display rgb crop drift")
    cameras = read_cameras_bin(cam_root / "sparse/cameras.bin"); images = read_images_bin(cam_root / "sparse/images.bin")
    image = images[int(disp["colmap_image_id"])]; camera = cameras[image.camera_id]
    ds = float(disp["downscale"]); K = camera.K().copy(); K[0, :] *= ds; K[1, :] *= ds
    x0, y0, x1, y1 = disp["roi_xyxy_half_open_px"]
    rgb = cv2.cvtColor(cv2.imread(str(rgb_path)), cv2.COLOR_BGR2RGB).astype(float) / 255
    # cell-state lookup
    origin = np.array([dom["x"][0], dom["y"][0]])
    nx = int(np.ceil((dom["x"][1] - dom["x"][0]) / cell)); ny = int(np.ceil((dom["y"][1] - dom["y"][0]) / cell))
    state_grid = np.zeros((ny, nx), dtype=np.uint8); state_grid[top["iy"], top["ix"]] = top["state"]
    palette = np.zeros((6, 3)); palette[0] = [0, 0, 0]
    for k, c in STATE_COLORS.items():
        palette[k] = to_rgb(c)

    def overlay(s: str, dilate: int) -> np.ndarray:
        pts = points[s]; lab = per_point[s]["patch_id"]
        keys = np.floor((pts[:, :2] - origin) / cell).astype(int)
        inside = (keys[:, 0] >= 0) & (keys[:, 0] < nx) & (keys[:, 1] >= 0) & (keys[:, 1] < ny) & (lab > 0)
        st = np.zeros(len(pts), dtype=np.uint8); st[inside] = state_grid[keys[inside, 1], keys[inside, 0]]
        cam = pts @ image.R().T + image.tvec; z = cam[:, 2]; ok = z > 1e-6
        u = K[0, 0] * cam[:, 0] / np.where(ok, z, 1) + K[0, 2]; v = K[1, 1] * cam[:, 1] / np.where(ok, z, 1) + K[1, 2]
        px = np.floor(u + 0.5).astype(int) - x0; py = np.floor(v + 0.5).astype(int) - y0
        h, w = y1 - y0, x1 - x0
        vis = ok & (px >= 0) & (px < w) & (py >= 0) & (py < h) & (st > 0)
        zbuf = np.full(h * w, np.inf); idx = py[vis] * w + px[vis]; np.minimum.at(zbuf, idx, z[vis])
        near = vis.copy(); near[vis] = z[vis] <= zbuf[idx] + 0.5
        img = np.zeros((h, w, 3)); hit = np.zeros((h, w), bool)
        img[py[near], px[near]] = palette[st[near]]; hit[py[near], px[near]] = True
        if dilate:
            k = np.ones((3, 3), np.uint8)
            hit = cv2.dilate(hit.astype(np.uint8), k, iterations=dilate).astype(bool)
            img = cv2.dilate((img * 255).astype(np.uint8), k, iterations=dilate).astype(float) / 255
        out = rgb.copy(); out[hit] = 0.4 * rgb[hit] + 0.6 * img[hit]
        return out

    fig, axes = plt.subplots(1, 3, figsize=(24, 8.2), dpi=100)
    grid_rgb = palette[state_grid]
    axes[0].imshow(grid_rgb, origin="lower", extent=[dom["x"][0], dom["x"][1], dom["y"][0], dom["y"][1]])
    axes[0].set_title(f"pair state per {cell} m XY cell (top layer), scene-local XY"); axes[0].set_aspect("equal")
    axes[1].imshow(overlay("mvs", 0)); axes[1].set_title("MVS (2024) points painted with their cell pair state, on the current image")
    axes[2].imshow(overlay("als", 2)); axes[2].set_title("Existing ALS (2022) points painted with their cell pair state, on the current image")
    for ax in axes[1:]:
        ax.set_xticks([]); ax.set_yticks([])
    acc = result["accounting"]["state_area_m2_top"]
    handles = [plt.Line2D([], [], marker="s", linestyle="", color=STATE_COLORS[k], markersize=12,
                          label=f"{STATE_NAMES[k]}  {acc[STATE_NAMES[k]]:.0f} m²") for k in range(1, 6)]
    fig.legend(handles=handles, loc="lower center", ncol=5, fontsize=11, frameon=False)
    fig.suptitle("XY-column pairing of surface patches (descriptive height-offset state; not a source or change verdict). dz = z_prior - z_current, tolerance "
                 f"{alg['same_surface_tolerance_m']} m", fontsize=12)
    fig.tight_layout(rect=(0, 0.06, 1, 1)); path.parent.mkdir(parents=True, exist_ok=True); fig.savefig(path); plt.close(fig)


def run(cfg: dict[str, Any], config_path: Path) -> dict[str, Any]:
    started = time.perf_counter()
    out = Path(cfg["artifact_root"]) / cfg["output_relative_root"]; out.mkdir(parents=True, exist_ok=True)
    resolved, patch_root = resolve_inputs(cfg)
    points, per_point, patches = load_sources(cfg, patch_root)
    result = run_pairing(points, per_point, patches, cfg["domain"], cfg["algorithm"])
    for name in ("cells", "pairs", "walls"):
        atomic_npy(out / f"pair_{name}.npy", result[name])
    write_preview(out / "pairing_preview.png", cfg, result, points, per_point)
    technical = {
        "schema": "jointbuildgs.phd.patch_pairing_xy.technical_return.v1", "task_id": cfg["task_id"],
        "status": "COMPLETE_DEVELOPMENT_NON_CONFIRMATORY", "generated_utc": utc_now(), "git_commit": git_head(),
        "config": {"path": str(config_path), "sha256": sha256(config_path)}, "driver": {"path": str(Path(__file__)), "sha256": sha256(Path(__file__))},
        "domain": cfg["domain"], "algorithm": cfg["algorithm"], "accounting": result["accounting"],
        "state_names": STATE_NAMES, "wall_state_names": WALL_NAMES, "not_decided_here": cfg["not_decided_here"],
        "display_only_current_image_used_for_preview_only": True,
        "elapsed_seconds": time.perf_counter() - started, "prohibited_inputs_accessed": [], "scientific_verdict": None,
    }
    atomic_json(out / "technical_return.json", technical)
    outputs = {}
    for name in sorted(["pair_cells.npy", "pair_pairs.npy", "pair_walls.npy", "pairing_preview.png", "technical_return.json"]):
        p = out / name; outputs[name] = {"path": name, "bytes": p.stat().st_size, "sha256": sha256(p)}
    atomic_json(out / "artifact_manifest.json", {
        "schema": "jointbuildgs.phd.patch_pairing_xy.artifact_manifest.v1", "task_id": cfg["task_id"],
        "status": "COMPLETE_DEVELOPMENT_NON_CONFIRMATORY", "generated_utc": utc_now(), "git_commit": technical["git_commit"],
        "config": technical["config"], "driver": technical["driver"], "inputs": resolved, "outputs": outputs,
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
    checks["output_hashes"] = "PASS"
    resolved, patch_root = resolve_inputs(cfg)
    checks["input_hashes_and_upstream_receipt_binding"] = "PASS"
    cells = np.load(out / "pair_cells.npy", allow_pickle=False); pairs = np.load(out / "pair_pairs.npy", allow_pickle=False)
    tol = float(cfg["algorithm"]["same_surface_tolerance_m"])
    both = (cells["mvs_patch"] > 0) & (cells["als_patch"] > 0)
    if np.any(cells["state"][both & (np.abs(cells["dz_m"]) <= tol)] != STATE_COMPATIBLE):
        raise AssertionError("state/dz inconsistency")
    if np.any(cells["state"][~both] == STATE_COMPATIBLE) or np.any((cells["mvs_patch"] == 0) & (cells["als_patch"] == 0)):
        raise AssertionError("single-source cell state drift")
    if np.any(np.isin(cells["state"], [STATE_PRIOR_ABOVE, STATE_CURRENT_ABOVE]) & ~both):
        raise AssertionError("offset state without both sources")
    checks["cell_state_consistency"] = "PASS"
    if len(pairs) and np.any(pairs["cells"] < int(cfg["algorithm"]["min_cells_per_patch_pair"])):
        raise AssertionError("patch pair below minimum cells")
    checks["patch_pair_integrity"] = "PASS"
    if rerun:
        points, per_point, patches = load_sources(cfg, patch_root)
        again = run_pairing(points, per_point, patches, cfg["domain"], cfg["algorithm"])
        for name in ("cells", "pairs", "walls"):
            if array_digest(again[name]) != array_digest(np.load(out / f"pair_{name}.npy", allow_pickle=False)):
                raise AssertionError(f"determinism drift: {name}")
        checks["determinism_rerun"] = "PASS"
    technical = json.loads((out / "technical_return.json").read_text(encoding="utf-8"))
    if technical.get("scientific_verdict", "missing") is not None or technical.get("prohibited_inputs_accessed") != []:
        raise AssertionError("technical return contract drift")
    checks["prohibited_inputs"] = "PASS"; checks["scientific_verdict_null"] = "PASS"
    receipt = {"schema": "jointbuildgs.phd.patch_pairing_xy.validation.v1", "task_id": cfg["task_id"], "generated_utc": utc_now(),
               "checks": checks, "artifact_manifest_sha256": sha256(out / "artifact_manifest.json"),
               "prohibited_inputs_accessed": [], "scientific_verdict": None}
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
        print(json.dumps(run(cfg, args.config.resolve())["accounting"], indent=2))
    if args.command in {"validate", "run-and-validate"}:
        print(json.dumps(validate(cfg, rerun=not args.no_rerun)["checks"], indent=2))


if __name__ == "__main__":
    main()
