#!/usr/bin/env python3
"""Build a five-class whole-space MVS/Existing-ALS relation map.

This is a development, non-confirmatory candidate detector for downstream
current-view rendering.  It never reads UAS LiDAR, LoD2, footprints, building
IDs, or the Journal1 roster, and it never interprets discrepancy as temporal
change or source correctness.

Workflow::

    prepare  -> hash/partition exact inputs into deterministic 250 m tiles
    tile     -> standard local-normal M3C2 + bidirectional support labels
    merge    -> PLY/NPZ relation map and 2/3/4 rendering queue
    run-all  -> prepare, every tile, merge

The primary LoD95 arm uses local roughness only (registration error 0 m) to
retain high recall.  A second LoD95 field uses the frozen 0.5 m C4 gate
envelope only as a sensitivity/priority flag; it is not a fitted covariance.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import os
import resource
import shutil
import struct
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

# PCA uses millions of tiny 3x3 eigendecompositions.  Let cKDTree own the
# requested parallelism and prevent BLAS from spawning a nested thread team for
# every tiny matrix.
for _thread_env in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[_thread_env] = "1"

import laspy
import numpy as np
from scipy.spatial import cKDTree


DEFAULT_CONFIG = Path("configs/phd/mvs_als_source_relation_v1/run_v1.json")

CLASS_NAMES = {
    1: "COMPATIBLE_WITHIN_LOD",
    2: "SIGNIFICANT_DISCREPANCY",
    3: "MVS_ONLY_SUPPORT",
    4: "PRIOR_ONLY_SUPPORT",
    5: "NOT_COMPARABLE",
}
SOURCE_MVS = 0
SOURCE_ALS = 1

REASON_OK = 0
REASON_NORMAL_INSUFFICIENT = 1
REASON_OWN_SUPPORT_INSUFFICIENT = 2
REASON_OTHER_SUPPORT_SPARSE = 3
REASON_SOURCE_BOUNDARY = 4
REASON_NONFINITE = 5
REASON_RECIPROCAL_BOTH_SUPPORT = 6
REASON_NAMES = {
    REASON_OK: "OK",
    REASON_NORMAL_INSUFFICIENT: "NORMAL_INSUFFICIENT",
    REASON_OWN_SUPPORT_INSUFFICIENT: "OWN_SUPPORT_INSUFFICIENT",
    REASON_OTHER_SUPPORT_SPARSE: "OTHER_SUPPORT_SPARSE",
    REASON_SOURCE_BOUNDARY: "SOURCE_BOUNDARY",
    REASON_NONFINITE: "NONFINITE",
    REASON_RECIPROCAL_BOTH_SUPPORT: "RECIPROCAL_BOTH_SUPPORT_SKIPPED",
}

OUTPUT_DTYPE = np.dtype(
    [
        ("x", "<f4"), ("y", "<f4"), ("z", "<f4"),
        ("nx", "<f4"), ("ny", "<f4"), ("nz", "<f4"),
        ("relation_class", "u1"), ("core_source", "u1"),
        ("reason", "<u2"), ("n_mvs", "<u4"), ("n_als", "<u4"),
        ("m3c2_signed_m", "<f4"), ("lod95_local_m", "<f4"),
        ("lod95_reg_upper_m", "<f4"), ("significance_ratio", "<f4"),
        ("sigma_mvs_m", "<f4"), ("sigma_als_m", "<f4"),
        ("robust_significant", "u1"), ("pm_valid", "u1"),
        ("normal_point_count", "<u2"), ("surface_variation", "<f4"),
    ]
)

PLY_DTYPES = {
    "char": "i1", "uchar": "u1", "int8": "i1", "uint8": "u1",
    "short": "<i2", "ushort": "<u2", "int16": "<i2", "uint16": "<u2",
    "int": "<i4", "uint": "<u4", "int32": "<i4", "uint32": "<u4",
    "float": "<f4", "float32": "<f4", "double": "<f8", "float64": "<f8",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_config(path: Path) -> dict[str, Any]:
    cfg = json.loads(path.read_text(encoding="utf-8"))
    if cfg.get("scientific_verdict", "missing") is not None:
        raise ValueError("scientific_verdict must remain null")
    text = json.dumps(cfg, sort_keys=True).lower()
    for forbidden in ("uas", "lod2", "footprint", "stable_id", "journal1"):
        if forbidden in text:
            # These words are allowed only inside the explicit prohibited list
            # and purpose/boundary text; no path may contain them.
            paths = json.dumps(cfg["inputs"], sort_keys=True).lower()
            if forbidden in paths:
                raise ValueError(f"prohibited input token in inputs: {forbidden}")
    return cfg


def digest(path: Path, chunk_bytes: int = 8 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_bytes), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def git_head(repo: Path) -> str:
    result = subprocess.run(
        ["git", "-c", f"safe.directory={repo}", "rev-parse", "HEAD"], cwd=repo, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else "UNKNOWN"


def parse_binary_ply_vertices(path: Path) -> tuple[np.memmap, list[str], int]:
    """Return a memory-mapped binary little-endian PLY vertex table."""
    with path.open("rb") as handle:
        lines: list[str] = []
        offset = 0
        while True:
            raw = handle.readline()
            if not raw:
                raise ValueError(f"{path}: truncated PLY header")
            offset += len(raw)
            line = raw.decode("ascii").strip()
            lines.append(line)
            if line == "end_header":
                break
    if "format binary_little_endian 1.0" not in lines:
        raise ValueError(f"{path}: only binary_little_endian PLY is supported")
    count = 0
    props: list[tuple[str, str]] = []
    in_vertex = False
    for line in lines:
        tok = line.split()
        if tok[:2] == ["element", "vertex"]:
            count = int(tok[2]); in_vertex = True
        elif tok and tok[0] == "element" and tok[1] != "vertex":
            in_vertex = False
        elif in_vertex and tok[:1] == ["property"]:
            if len(tok) != 3 or tok[1] == "list":
                raise ValueError(f"{path}: unsupported PLY property {line!r}")
            if tok[1] not in PLY_DTYPES:
                raise ValueError(f"{path}: unsupported PLY scalar {tok[1]!r}")
            props.append((tok[2], PLY_DTYPES[tok[1]]))
    names = [name for name, _ in props]
    if not {"x", "y", "z"}.issubset(names):
        raise ValueError(f"{path}: x/y/z properties are required")
    dtype = np.dtype(props)
    expected = offset + count * dtype.itemsize
    if path.stat().st_size != expected:
        raise ValueError(f"{path}: size mismatch {path.stat().st_size} != {expected}")
    return np.memmap(path, dtype=dtype, mode="r", offset=offset, shape=(count,)), names, offset


def tile_id(ix: int, iy: int) -> str:
    return f"x{ix:03d}_y{iy:03d}"


def tile_indices(cfg: dict[str, Any], world_xy: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    origin = np.asarray(cfg["tiling"]["world_xy_origin_m"], dtype=np.float64)
    size = float(cfg["tiling"]["tile_size_m"])
    ij = np.floor((world_xy - origin) / size).astype(np.int32)
    return ij[:, 0], ij[:, 1]


def in_domain(cfg: dict[str, Any], world_xy: np.ndarray) -> np.ndarray:
    x0, y0, x1, y1 = map(float, cfg["domain"]["world_xy_bbox_m"])
    return ((world_xy[:, 0] >= x0) & (world_xy[:, 0] < x1) &
            (world_xy[:, 1] >= y0) & (world_xy[:, 1] < y1))


def append_partition(
    cfg: dict[str, Any], handles: dict[str, Any], xyz_local: np.ndarray,
) -> Counter:
    shift = np.asarray(cfg["frame"]["world_shift_xyz_m"], dtype=np.float64)
    world_xy = xyz_local[:, :2].astype(np.float64) + shift[:2]
    keep = in_domain(cfg, world_xy)
    if not bool(keep.any()):
        return Counter()
    xyz_local = np.asarray(xyz_local[keep], dtype="<f4")
    world_xy = world_xy[keep]
    ix, iy = tile_indices(cfg, world_xy)
    nx, ny = map(int, cfg["tiling"]["tile_count_xy"])
    valid = (ix >= 0) & (ix < nx) & (iy >= 0) & (iy < ny)
    xyz_local, ix, iy = xyz_local[valid], ix[valid], iy[valid]
    counts: Counter = Counter()
    key = iy.astype(np.int64) * nx + ix.astype(np.int64)
    for value in np.unique(key):
        rows = key == value
        tx, ty = int(value % nx), int(value // nx)
        name = tile_id(tx, ty)
        xyz_local[rows].tofile(handles[name])
        counts[name] += int(rows.sum())
    return counts


def open_partition_handles(root: Path, source: str, cfg: dict[str, Any]) -> dict[str, Any]:
    target = root / "partition" / source
    target.mkdir(parents=True, exist_ok=True)
    nx, ny = map(int, cfg["tiling"]["tile_count_xy"])
    return {
        tile_id(ix, iy): (target / f"{tile_id(ix, iy)}.xyz_f32le.bin").open("wb")
        for iy in range(ny) for ix in range(nx)
    }


def prepare(cfg: dict[str, Any], config_path: Path, repo: Path, root: Path) -> dict[str, Any]:
    started = time.perf_counter()
    if (root / "partition").exists():
        shutil.rmtree(root / "partition")
    root.mkdir(parents=True, exist_ok=True)
    artifact_root = Path(cfg["artifact_root"])
    mvs_cfg = cfg["inputs"]["mvs"]
    mvs_path = artifact_root / mvs_cfg["relative_path"]
    actual = digest(mvs_path)
    if actual != mvs_cfg["sha256"]:
        raise RuntimeError(f"MVS hash drift: {actual}")
    als_cfg = cfg["inputs"]["existing_als"]
    als_root = artifact_root / als_cfg["relative_root"]
    als_hashes = {}
    for name, expected in als_cfg["files"].items():
        value = digest(als_root / name)
        if value != expected:
            raise RuntimeError(f"ALS hash drift {name}: {value}")
        als_hashes[name] = value

    chunk_n = int(cfg["tiling"]["partition_chunk_points"])
    mvs_handles = open_partition_handles(root, "mvs", cfg)
    mvs_counts: Counter = Counter()
    vertices, _, _ = parse_binary_ply_vertices(mvs_path)
    shift = np.asarray(cfg["frame"]["world_shift_xyz_m"], dtype=np.float64)
    try:
        for start in range(0, len(vertices), chunk_n):
            rows = vertices[start:start + chunk_n]
            xyz = np.column_stack((rows["x"], rows["y"], rows["z"]))
            mvs_counts.update(append_partition(cfg, mvs_handles, xyz))
    finally:
        for handle in mvs_handles.values():
            handle.close()

    als_handles = open_partition_handles(root, "als", cfg)
    als_counts: Counter = Counter()
    try:
        for name in sorted(als_cfg["files"]):
            with laspy.open(als_root / name) as reader:
                for chunk in reader.chunk_iterator(chunk_n):
                    xyz = np.column_stack((
                        np.asarray(chunk.x), np.asarray(chunk.y),
                        np.asarray(chunk.z) + float(als_cfg["z_shift_m"]),
                    )) - shift
                    als_counts.update(append_partition(cfg, als_handles, xyz))
    finally:
        for handle in als_handles.values():
            handle.close()

    nx, ny = map(int, cfg["tiling"]["tile_count_xy"])
    rows = []
    for iy in range(ny):
        for ix in range(nx):
            name = tile_id(ix, iy)
            rows.append({
                "tile_id": name, "ix": ix, "iy": iy,
                "mvs_points": int(mvs_counts[name]), "als_points": int(als_counts[name]),
            })
    receipt = {
        "schema": "jointbuildgs.phd.mvs_als_source_relation.partition.v1",
        "task_id": cfg["task_id"], "created_at": utc_now(),
        "config_path": str(config_path), "config_sha256": digest(config_path),
        "git_commit": git_head(repo),
        "inputs": {
            "mvs": {"path": str(mvs_path), "sha256": actual, "points_total": len(vertices)},
            "als": {"root": str(als_root), "sha256_by_name": als_hashes},
        },
        "domain": cfg["domain"], "tiling": cfg["tiling"],
        "counts": {
            "mvs_in_domain": int(sum(mvs_counts.values())),
            "als_in_domain": int(sum(als_counts.values())),
        },
        "tiles": rows, "elapsed_seconds": time.perf_counter() - started,
        "prohibited_inputs_accessed": [], "scientific_verdict": None,
    }
    write_json(root / "partition_receipt.json", receipt)
    return receipt


def read_xyz_bin(path: Path) -> np.ndarray:
    if not path.exists() or path.stat().st_size == 0:
        return np.empty((0, 3), dtype=np.float32)
    if path.stat().st_size % 12:
        raise ValueError(f"{path}: invalid xyz_f32le byte count")
    return np.fromfile(path, dtype="<f4").reshape(-1, 3)


def load_tile_halo(root: Path, source: str, ix: int, iy: int, cfg: dict[str, Any]) -> np.ndarray:
    nx, ny = map(int, cfg["tiling"]["tile_count_xy"])
    parts = []
    for yy in range(max(0, iy - 1), min(ny, iy + 2)):
        for xx in range(max(0, ix - 1), min(nx, ix + 2)):
            arr = read_xyz_bin(root / "partition" / source / f"{tile_id(xx, yy)}.xyz_f32le.bin")
            if len(arr):
                parts.append(arr)
    if not parts:
        return np.empty((0, 3), dtype=np.float32)
    xyz = np.concatenate(parts)
    shift = np.asarray(cfg["frame"]["world_shift_xyz_m"], dtype=np.float64)
    origin = np.asarray(cfg["tiling"]["world_xy_origin_m"], dtype=np.float64) - shift[:2]
    size = float(cfg["tiling"]["tile_size_m"])
    halo = float(cfg["tiling"]["halo_m"])
    low = origin + np.array([ix * size - halo, iy * size - halo])
    high = origin + np.array([(ix + 1) * size + halo, (iy + 1) * size + halo])
    keep = ((xyz[:, 0] >= low[0]) & (xyz[:, 0] < high[0]) &
            (xyz[:, 1] >= low[1]) & (xyz[:, 1] < high[1]))
    return xyz[keep]


def inner_mask(xyz: np.ndarray, ix: int, iy: int, cfg: dict[str, Any]) -> np.ndarray:
    shift = np.asarray(cfg["frame"]["world_shift_xyz_m"], dtype=np.float64)
    origin = np.asarray(cfg["tiling"]["world_xy_origin_m"], dtype=np.float64) - shift[:2]
    size = float(cfg["tiling"]["tile_size_m"])
    low = origin + np.array([ix * size, iy * size])
    high = origin + np.array([(ix + 1) * size, (iy + 1) * size])
    world_xy = xyz[:, :2].astype(np.float64) + shift[:2]
    return ((xyz[:, 0] >= low[0]) & (xyz[:, 0] < high[0]) &
            (xyz[:, 1] >= low[1]) & (xyz[:, 1] < high[1]) &
            in_domain(cfg, world_xy))


def voxel_representatives(xyz: np.ndarray, spacing: float) -> np.ndarray:
    """Deterministic first-point representative in a global 3-D voxel grid."""
    if not len(xyz):
        return np.empty((0, 3), dtype=np.float32)
    ijk = np.floor(xyz.astype(np.float64) / spacing).astype(np.int64)
    bias = 1 << 20
    if np.any(np.abs(ijk) >= bias):
        raise ValueError("voxel index exceeds 21-bit packing range")
    key = ((ijk[:, 0] + bias).astype(np.uint64) << np.uint64(42))
    key |= ((ijk[:, 1] + bias).astype(np.uint64) << np.uint64(21))
    key |= (ijk[:, 2] + bias).astype(np.uint64)
    _, index = np.unique(key, return_index=True)
    return np.asarray(xyz[np.sort(index)], dtype=np.float32)


def estimate_normals(
    samples: np.ndarray, cores: np.ndarray, radius: float, min_points: int, workers: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    normals = np.full((len(cores), 3), np.nan, dtype=np.float32)
    counts = np.zeros(len(cores), dtype=np.uint16)
    variation = np.full(len(cores), np.nan, dtype=np.float32)
    if not len(samples) or not len(cores):
        return normals, counts, variation
    tree = cKDTree(samples.astype(np.float64), compact_nodes=True, balanced_tree=True)
    batches = tree.query_ball_point(cores.astype(np.float64), radius, workers=workers)
    for i, ids in enumerate(batches):
        counts[i] = min(len(ids), np.iinfo(np.uint16).max)
        if len(ids) < min_points:
            continue
        pts = samples[np.asarray(ids, dtype=np.int64)].astype(np.float64)
        centered = pts - pts.mean(axis=0)
        cov = centered.T @ centered / max(1, len(pts) - 1)
        values, vectors = np.linalg.eigh(cov)
        if not np.all(np.isfinite(values)) or values[-1] <= 1e-12:
            continue
        n = vectors[:, 0]
        # Sign is not used by the five-class decision; make it deterministic.
        axis = int(np.argmax(np.abs(n)))
        if n[axis] < 0:
            n = -n
        normals[i] = n.astype(np.float32)
        variation[i] = float(max(0.0, values[0]) / max(values.sum(), 1e-12))
    return normals, counts, variation


def projection_stats(
    tree: cKDTree | None, points: np.ndarray, core: np.ndarray, normal: np.ndarray,
    radius: float, half_length: float,
) -> tuple[int, float, float]:
    if tree is None:
        return 0, math.nan, math.nan
    search = math.sqrt(radius * radius + half_length * half_length)
    ids = tree.query_ball_point(core.astype(np.float64), search)
    if not ids:
        return 0, math.nan, math.nan
    delta = points[np.asarray(ids, dtype=np.int64)].astype(np.float64) - core
    t = delta @ normal.astype(np.float64)
    radial2 = np.einsum("ij,ij->i", delta, delta) - t * t
    keep = (np.abs(t) <= half_length) & (radial2 <= radius * radius + 1e-9)
    t = t[keep]
    if not len(t):
        return 0, math.nan, math.nan
    return len(t), float(t.mean()), float(t.std(ddof=1)) if len(t) > 1 else 0.0


def lod95(sigma_mvs: float, n_mvs: int, sigma_als: float, n_als: int,
          z_score: float, registration_error_m: float) -> float:
    if n_mvs <= 0 or n_als <= 0:
        return math.nan
    sampling = math.sqrt(sigma_mvs * sigma_mvs / n_mvs + sigma_als * sigma_als / n_als)
    return z_score * (sampling + registration_error_m)


def boundary_interior(core: np.ndarray, cfg: dict[str, Any]) -> bool:
    shift = np.asarray(cfg["frame"]["world_shift_xyz_m"], dtype=np.float64)
    x, y = core[:2].astype(np.float64) + shift[:2]
    x0, y0, x1, y1 = map(float, cfg["domain"]["world_xy_bbox_m"])
    margin = float(cfg["domain"]["boundary_margin_m"])
    return x >= x0 + margin and x < x1 - margin and y >= y0 + margin and y < y1 - margin


def make_record(core: np.ndarray, normal: np.ndarray, core_source: int,
                normal_n: int, variation: float) -> np.void:
    rec = np.zeros((), dtype=OUTPUT_DTYPE)
    rec["x"], rec["y"], rec["z"] = core
    rec["nx"], rec["ny"], rec["nz"] = normal
    rec["relation_class"] = 5
    rec["core_source"] = core_source
    rec["reason"] = REASON_OK
    for name in ("m3c2_signed_m", "lod95_local_m", "lod95_reg_upper_m",
                 "significance_ratio", "sigma_mvs_m", "sigma_als_m"):
        rec[name] = np.nan
    rec["normal_point_count"] = min(normal_n, np.iinfo(np.uint16).max)
    rec["surface_variation"] = variation
    return rec


def classify_core(
    core: np.ndarray, normal: np.ndarray, core_source: int,
    normal_n: int, variation: float,
    mvs_tree: cKDTree | None, mvs: np.ndarray,
    als_tree: cKDTree | None, als: np.ndarray,
    cfg: dict[str, Any], reciprocal: bool = False,
) -> np.void | None:
    p = cfg["m3c2"]
    rec = make_record(core, normal, core_source, normal_n, variation)
    if not np.all(np.isfinite(normal)):
        rec["reason"] = REASON_NORMAL_INSUFFICIENT
        return rec
    radius = float(p["projection_diameter_m"]) / 2.0
    half = float(p["projection_half_length_m"])
    nm, mm, sm = projection_stats(mvs_tree, mvs, core, normal, radius, half)
    na, ma, sa = projection_stats(als_tree, als, core, normal, radius, half)
    rec["n_mvs"], rec["n_als"] = nm, na
    rec["sigma_mvs_m"], rec["sigma_als_m"] = sm, sa
    minimum = int(p["minimum_projection_points"])

    own = nm if core_source == SOURCE_MVS else na
    other = na if core_source == SOURCE_MVS else nm
    if own < minimum:
        rec["reason"] = REASON_OWN_SUPPORT_INSUFFICIENT
        return rec
    if other >= minimum:
        if reciprocal:
            return None  # MVS-core pass owns all both-support records.
        distance = ma - mm
        local = lod95(sm, nm, sa, na, float(p["z_score"]),
                      float(p["primary_registration_error_m"]))
        upper = lod95(sm, nm, sa, na, float(p["z_score"]),
                      float(p["registration_sensitivity_upper_m"]))
        if not all(math.isfinite(v) for v in (distance, local, upper)):
            rec["reason"] = REASON_NONFINITE
            return rec
        rec["m3c2_signed_m"] = distance
        rec["lod95_local_m"] = local
        rec["lod95_reg_upper_m"] = upper
        rec["significance_ratio"] = abs(distance) / max(local, 1e-9)
        significant = abs(distance) > local
        rec["relation_class"] = 2 if significant else 1
        rec["robust_significant"] = int(abs(distance) > upper)
        return rec
    if 0 < other < minimum:
        rec["reason"] = REASON_OTHER_SUPPORT_SPARSE
        return rec
    if not boundary_interior(core, cfg):
        rec["reason"] = REASON_SOURCE_BOUNDARY
        return rec
    rec["relation_class"] = 3 if core_source == SOURCE_MVS else 4
    return rec


def run_tile(cfg: dict[str, Any], root: Path, ix: int, iy: int, workers: int) -> dict[str, Any]:
    started = time.perf_counter()
    name = tile_id(ix, iy)
    out_dir = root / "tiles" / name
    out_dir.mkdir(parents=True, exist_ok=True)
    mvs = load_tile_halo(root, "mvs", ix, iy, cfg)
    als = load_tile_halo(root, "als", ix, iy, cfg)
    p = cfg["m3c2"]
    normal_voxel = float(p["normal_sampling_voxel_m"])
    core_spacing = float(p["core_spacing_m"])
    normal_radius = float(p["normal_diameter_m"]) / 2.0
    min_normal = int(p["minimum_normal_points"])

    mvs_samples = voxel_representatives(mvs, normal_voxel)
    als_samples = voxel_representatives(als, normal_voxel)
    mvs_cores_all = voxel_representatives(mvs_samples, core_spacing)
    als_cores_all = voxel_representatives(als_samples, core_spacing)
    mvs_cores = mvs_cores_all[inner_mask(mvs_cores_all, ix, iy, cfg)]
    als_cores = als_cores_all[inner_mask(als_cores_all, ix, iy, cfg)]
    mvs_normals, mvs_nn, mvs_var = estimate_normals(
        mvs_samples, mvs_cores, normal_radius, min_normal, workers,
    )
    als_normals, als_nn, als_var = estimate_normals(
        als_samples, als_cores, normal_radius, min_normal, workers,
    )
    mvs_tree = cKDTree(mvs.astype(np.float64), compact_nodes=True, balanced_tree=True) if len(mvs) else None
    als_tree = cKDTree(als.astype(np.float64), compact_nodes=True, balanced_tree=True) if len(als) else None
    records = []
    for core, normal, nn, var in zip(mvs_cores, mvs_normals, mvs_nn, mvs_var):
        records.append(classify_core(
            core, normal, SOURCE_MVS, int(nn), float(var),
            mvs_tree, mvs, als_tree, als, cfg, reciprocal=False,
        ))
    for core, normal, nn, var in zip(als_cores, als_normals, als_nn, als_var):
        rec = classify_core(
            core, normal, SOURCE_ALS, int(nn), float(var),
            mvs_tree, mvs, als_tree, als, cfg, reciprocal=True,
        )
        if rec is not None:
            records.append(rec)
    result = np.asarray(records, dtype=OUTPUT_DTYPE)
    np.save(out_dir / "relation.npy", result, allow_pickle=False)
    counts = Counter(int(v) for v in result["relation_class"])
    reasons = Counter(int(v) for v in result["reason"])
    receipt = {
        "schema": "jointbuildgs.phd.mvs_als_source_relation.tile.v1",
        "task_id": cfg["task_id"], "tile_id": name, "created_at": utc_now(),
        "inputs": {"mvs_halo_points": len(mvs), "als_halo_points": len(als)},
        "sampling": {
            "mvs_normal_points": len(mvs_samples), "als_normal_points": len(als_samples),
            "mvs_inner_cores": len(mvs_cores), "als_inner_cores": len(als_cores),
        },
        "class_counts": {CLASS_NAMES[k]: int(counts[k]) for k in CLASS_NAMES},
        "reason_counts": {REASON_NAMES[k]: int(reasons[k]) for k in REASON_NAMES if reasons[k]},
        "robust_significant_count": int(result["robust_significant"].sum()) if len(result) else 0,
        "output": {"path": str(out_dir / "relation.npy"), "rows": len(result),
                   "sha256": digest(out_dir / "relation.npy")},
        "runtime": {
            "elapsed_seconds": time.perf_counter() - started,
            "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "workers": workers,
        },
        "prohibited_inputs_accessed": [], "scientific_verdict": None,
    }
    write_json(out_dir / "receipt.json", receipt)
    return receipt


def relation_rgb(labels: np.ndarray) -> np.ndarray:
    palette = np.asarray([
        [0, 0, 0], [40, 180, 90], [230, 60, 50],
        [50, 120, 230], [240, 170, 30], [150, 150, 150],
    ], dtype=np.uint8)
    return palette[labels]


def write_relation_ply(path: Path, rows: np.ndarray) -> None:
    rgb = relation_rgb(rows["relation_class"])
    dtype = np.dtype([
        ("x", "<f4"), ("y", "<f4"), ("z", "<f4"),
        ("red", "u1"), ("green", "u1"), ("blue", "u1"),
        ("relation_class", "u1"), ("core_source", "u1"),
        ("m3c2_signed_m", "<f4"), ("lod95_local_m", "<f4"),
        ("lod95_reg_upper_m", "<f4"), ("robust_significant", "u1"),
    ])
    out = np.empty(len(rows), dtype=dtype)
    for key in ("x", "y", "z", "relation_class", "core_source", "m3c2_signed_m",
                "lod95_local_m", "lod95_reg_upper_m", "robust_significant"):
        out[key] = rows[key]
    out["red"], out["green"], out["blue"] = rgb[:, 0], rgb[:, 1], rgb[:, 2]
    props = [
        "property float x", "property float y", "property float z",
        "property uchar red", "property uchar green", "property uchar blue",
        "property uchar relation_class", "property uchar core_source",
        "property float m3c2_signed_m", "property float lod95_local_m",
        "property float lod95_reg_upper_m", "property uchar robust_significant",
    ]
    header = ("ply\nformat binary_little_endian 1.0\n" +
              f"element vertex {len(out)}\n" + "\n".join(props) + "\nend_header\n")
    with path.open("wb") as handle:
        handle.write(header.encode("ascii")); handle.write(out.tobytes())


def write_relation_preview(path: Path, rows: np.ndarray, world_shift: np.ndarray) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    if len(rows) > 120_000:
        index = np.linspace(0, len(rows) - 1, 120_000, dtype=np.int64)
        view = rows[index]
    else:
        view = rows
    world = np.c_[view["x"], view["y"], view["z"]].astype(np.float64) + world_shift
    rgb = relation_rgb(view["relation_class"]).astype(np.float64) / 255.0
    fig = plt.figure(figsize=(16, 5.2), constrained_layout=True)
    ax0 = fig.add_subplot(1, 3, 1)
    ax0.scatter(world[:, 0], world[:, 1], s=0.6, c=rgb, linewidths=0, rasterized=True)
    ax0.set_title("Whole-space source relation (XY)")
    ax0.set_xlabel("EPSG:25832 X (m)"); ax0.set_ylabel("EPSG:25832 Y (m)")
    ax0.set_aspect("equal", adjustable="box")

    ax1 = fig.add_subplot(1, 3, 2, projection="3d")
    sample = slice(None, None, 2)
    ax1.scatter(world[sample, 0], world[sample, 1], world[sample, 2],
                s=0.4, c=rgb[sample], linewidths=0, depthshade=False, rasterized=True)
    ax1.set_title("3D relation cores")
    ax1.set_xlabel("X"); ax1.set_ylabel("Y"); ax1.set_zlabel("Z")
    ax1.view_init(elev=28, azim=-58)

    ax2 = fig.add_subplot(1, 3, 3)
    candidate = np.isin(view["relation_class"], [2, 3, 4])
    robust = view["robust_significant"].astype(bool)
    ax2.scatter(world[candidate, 0], world[candidate, 1], s=0.5,
                c="#bdbdbd", linewidths=0, rasterized=True, label="render queue")
    ax2.scatter(world[robust, 0], world[robust, 1], s=1.4,
                c="#7f0000", linewidths=0, rasterized=True, label="robust discrepancy")
    ax2.set_title("Rendering queue / robust priority")
    ax2.set_xlabel("EPSG:25832 X (m)"); ax2.set_ylabel("EPSG:25832 Y (m)")
    ax2.set_aspect("equal", adjustable="box"); ax2.legend(loc="best", markerscale=5)

    palette = relation_rgb(np.arange(1, 6, dtype=np.uint8)).astype(np.float64) / 255.0
    handles = [Line2D([0], [0], marker="o", color="none", markerfacecolor=palette[i - 1],
                      markeredgecolor="none", markersize=6, label=f"{i} {CLASS_NAMES[i]}")
               for i in range(1, 6)]
    fig.legend(handles=handles, loc="lower center", ncol=5, frameon=False)
    fig.suptitle("PHD-MVS-ALS-SOURCE-RELATION-v1 — development / non-confirmatory")
    fig.savefig(path, dpi=220)
    plt.close(fig)


def validate_outputs(cfg: dict[str, Any], root: Path) -> dict[str, Any]:
    technical_path = root / "technical_return.json"
    technical = json.loads(technical_path.read_text(encoding="utf-8"))
    if technical.get("scientific_verdict", "missing") is not None:
        raise AssertionError("scientific_verdict must remain null")
    if technical.get("prohibited_inputs_accessed") != []:
        raise AssertionError("prohibited input access is not empty")
    for name, metadata in technical["outputs"].items():
        path = root / name
        if not path.is_file() or digest(path) != metadata["sha256"]:
            raise AssertionError(f"output hash mismatch: {name}")
    rows = np.load(root / "relation_map.npy", allow_pickle=False)
    queue = np.load(root / "render_queue.npy", allow_pickle=False)
    if len(rows) != int(technical["rows"]):
        raise AssertionError("relation row count mismatch")
    if len(queue) != int(technical["render_queue_rows"]):
        raise AssertionError("render queue row count mismatch")
    if not set(np.unique(rows["relation_class"])).issubset(CLASS_NAMES):
        raise AssertionError("unknown relation class")
    if not set(np.unique(queue["relation_class"])).issubset(set(cfg["render_queue_classes"])):
        raise AssertionError("render queue contains a non-candidate class")
    both = np.isin(rows["relation_class"], [1, 2])
    if not np.isfinite(rows["m3c2_signed_m"][both]).all():
        raise AssertionError("both-support class lacks finite M3C2 distance")
    if not np.isfinite(rows["lod95_local_m"][both]).all():
        raise AssertionError("both-support class lacks finite LoD95")
    if np.any(rows["reason"][rows["relation_class"] == 5] == REASON_OK):
        raise AssertionError("NOT_COMPARABLE lacks a reason")
    if np.any(rows["pm_valid"]):
        raise AssertionError("precision-aware result was populated without a frozen model")
    expected = Counter(int(v) for v in rows["relation_class"])
    for key, name in CLASS_NAMES.items():
        if int(technical["class_counts"][name]) != expected[key]:
            raise AssertionError(f"class count mismatch: {name}")
    ply = root / "relation_map.ply"
    raw = ply.read_bytes()
    offset = raw.index(b"end_header\n") + len(b"end_header\n")
    header = raw[:offset].decode("ascii")
    vertex_count = int(next(line.split()[-1] for line in header.splitlines()
                            if line.startswith("element vertex")))
    if vertex_count != len(rows) or len(raw) - offset != vertex_count * 30:
        raise AssertionError("relation PLY header/body mismatch")
    receipt = {
        "schema": "jointbuildgs.phd.mvs_als_source_relation.validation.v1",
        "task_id": cfg["task_id"], "validated_at": utc_now(),
        "checks": {
            "output_hashes": "PASS", "class_counts": "PASS",
            "required_fields": "PASS", "render_queue_allowlist": "PASS",
            "precision_leakage": "PASS", "ply_header_body": "PASS",
            "scientific_verdict_null": "PASS", "prohibited_inputs": "PASS",
        },
        "rows": len(rows), "render_queue_rows": len(queue),
        "scientific_verdict": None,
    }
    write_json(root / "validation_receipt.json", receipt)
    return receipt


def merge(cfg: dict[str, Any], config_path: Path, repo: Path, root: Path) -> dict[str, Any]:
    started = time.perf_counter()
    nx, ny = map(int, cfg["tiling"]["tile_count_xy"])
    arrays, tile_receipts = [], []
    for iy in range(ny):
        for ix in range(nx):
            target = root / "tiles" / tile_id(ix, iy)
            npy, receipt = target / "relation.npy", target / "receipt.json"
            if not npy.exists() or not receipt.exists():
                raise RuntimeError(f"missing tile output: {tile_id(ix, iy)}")
            arrays.append(np.load(npy, mmap_mode="r", allow_pickle=False))
            tile_receipts.append(json.loads(receipt.read_text(encoding="utf-8")))
    rows = np.concatenate(arrays) if arrays else np.empty(0, dtype=OUTPUT_DTYPE)
    np.save(root / "relation_map.npy", rows, allow_pickle=False)
    write_relation_ply(root / "relation_map.ply", rows)
    queue_mask = np.isin(rows["relation_class"], np.asarray(cfg["render_queue_classes"], dtype=np.uint8))
    queue = rows[queue_mask]
    np.save(root / "render_queue.npy", queue, allow_pickle=False)
    write_relation_ply(root / "render_queue.ply", queue)
    write_relation_preview(
        root / "relation_map_preview.png", rows,
        np.asarray(cfg["frame"]["world_shift_xyz_m"], dtype=np.float64),
    )

    with gzip.open(root / "relation_elements.csv.gz", "wt", encoding="utf-8", newline="") as handle:
        fieldnames = list(OUTPUT_DTYPE.names or ())
        writer = csv.DictWriter(handle, fieldnames=fieldnames); writer.writeheader()
        for row in rows:
            writer.writerow({name: row[name].item() for name in fieldnames})

    counts = Counter(int(v) for v in rows["relation_class"])
    reason_counts = Counter(int(v) for v in rows["reason"])
    summary = {
        "schema": "jointbuildgs.phd.mvs_als_source_relation.summary.v1",
        "task_id": cfg["task_id"], "created_at": utc_now(),
        "status": "COMPLETE_DEVELOPMENT_NON_CONFIRMATORY",
        "method_scope": "SOURCE_DIFFERENCE_CANDIDATE_MAP_FOR_CURRENT_VIEW_RENDERING",
        "not_interpretable_as": ["TEMPORAL_CHANGE_VERDICT", "SOURCE_CORRECTNESS_VERDICT"],
        "config": {"path": str(config_path), "sha256": digest(config_path)},
        "git_commit": git_head(repo), "script_sha256": digest(Path(__file__)),
        "rows": len(rows), "render_queue_rows": len(queue),
        "class_counts": {CLASS_NAMES[k]: int(counts[k]) for k in CLASS_NAMES},
        "reason_counts": {REASON_NAMES[k]: int(reason_counts[k]) for k in REASON_NAMES if reason_counts[k]},
        "robust_significant_count": int(rows["robust_significant"].sum()) if len(rows) else 0,
        "precision_aware_variant": {"valid": False, "reason": cfg["m3c2"]["precision_aware_variant"]["reason"]},
        "outputs": {}, "tile_runtime_seconds": {
            "total": sum(float(r["runtime"]["elapsed_seconds"]) for r in tile_receipts),
            "max": max(float(r["runtime"]["elapsed_seconds"]) for r in tile_receipts),
            "median": float(np.median([r["runtime"]["elapsed_seconds"] for r in tile_receipts])),
        },
        "merge_elapsed_seconds": time.perf_counter() - started,
        "prohibited_inputs_accessed": [], "scientific_verdict": None,
    }
    for name in ("relation_map.npy", "relation_map.ply", "render_queue.npy",
                 "render_queue.ply", "relation_elements.csv.gz", "relation_map_preview.png"):
        path = root / name
        summary["outputs"][name] = {"bytes": path.stat().st_size, "sha256": digest(path)}
    write_json(root / "technical_return.json", summary)
    return summary


def resolve_root(cfg: dict[str, Any]) -> Path:
    return Path(cfg["artifact_root"]) / cfg["output_relative_root"]


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--workers", type=int, default=max(1, min(16, os.cpu_count() or 1)))
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("prepare")
    tile_parser = sub.add_parser("tile")
    tile_parser.add_argument("--ix", type=int, required=True)
    tile_parser.add_argument("--iy", type=int, required=True)
    sub.add_parser("merge")
    sub.add_parser("run-all")
    sub.add_parser("run-pending")
    sub.add_parser("validate")
    args = parser.parse_args(argv)
    config_path = args.config.resolve()
    cfg = load_config(config_path)
    repo = Path(__file__).resolve().parents[3]
    root = resolve_root(cfg)
    nx, ny = map(int, cfg["tiling"]["tile_count_xy"])
    if args.command in {"prepare", "run-all"}:
        print(json.dumps(prepare(cfg, config_path, repo, root), indent=2))
    if args.command == "tile":
        if not (0 <= args.ix < nx and 0 <= args.iy < ny):
            raise ValueError("tile index out of range")
        print(json.dumps(run_tile(cfg, root, args.ix, args.iy, args.workers), indent=2))
    if args.command == "run-all":
        for iy in range(ny):
            for ix in range(nx):
                receipt = run_tile(cfg, root, ix, iy, args.workers)
                print(json.dumps({"tile_id": receipt["tile_id"], "class_counts": receipt["class_counts"],
                                  "runtime": receipt["runtime"]}))
    if args.command == "run-pending":
        for iy in range(ny):
            for ix in range(nx):
                target = root / "tiles" / tile_id(ix, iy)
                if (target / "relation.npy").exists() and (target / "receipt.json").exists():
                    continue
                receipt = run_tile(cfg, root, ix, iy, args.workers)
                print(json.dumps({"tile_id": receipt["tile_id"], "class_counts": receipt["class_counts"],
                                  "runtime": receipt["runtime"]}))
    if args.command in {"merge", "run-all", "run-pending"}:
        print(json.dumps(merge(cfg, config_path, repo, root), indent=2))
    if args.command == "validate":
        print(json.dumps(validate_outputs(cfg, root), indent=2))


if __name__ == "__main__":
    main()
