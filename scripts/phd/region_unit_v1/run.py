#!/usr/bin/env python3
"""T0 region unit v1 — data-defined decision units (design v2 appendix D-1, r1.1).

One continuous responsibility later attaches to each unit.  Units are defined
once, outside the optimisation loop, on frozen source bytes only:

  D-1.1  working cells      per-source voxel cells of the frozen partition bytes
  D-1.2  cell normals       PCA normal and surface variation per cell
  D-1.3  planar segments    deterministic FIFO region growing (guarded refits)
                            + crease-band absorption by plane distance
  D-1.4  extent cap         grid split (planar: in-plane PCA axes; rough: 3D)
                            + connected children + small-child merge
  D-1.5  rough regions      residual connected components (+ small attach)
  D-1.6  pairing            Existing ALS cells paired into MVS units through the
                            frozen M3C2 window measured along the ALS cell normal
                            (D-1e'); prior-layer split (D-1k); prior-only units
                            from the ALS segmentation (D-1f)
  D-1.7  ids / lineage      integer ordering, input-bound uid, adjacency (D-1i),
                            relation core -> unit by cell key (D-1j)
  D-1.8  resolver           Gaussian centre -> unit over ALL member cells

Nothing here decides source authority, temporal change, registration delta,
responsibility or Gaussian weights.  ``scientific_verdict`` stays null.
"""
from __future__ import annotations

import argparse
import colorsys
from collections import Counter, deque
import csv
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import time
from typing import Any

import numpy as np
import scipy
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree


REPO = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = REPO / "configs/phd/region_unit_v1/run_v1.json"
SCHEMA = "jointbuildgs.phd.region_unit.run.v1"
UID_NAMESPACE = "jbgs.region_unit.v1"

SOURCE_MVS, SOURCE_ALS = 0, 1
SOURCE_NAMES = {SOURCE_MVS: "MVS", SOURCE_ALS: "EXISTING_ALS"}
KIND_PLANAR, KIND_ROUGH = 0, 1
KIND_NAMES = {KIND_PLANAR: "PLANAR", KIND_ROUGH: "ROUGH"}
ROLE_PLANAR_CORE, ROLE_ROUGH_MEMBER, ROLE_ABSORBED = 0, 1, 2
ROLE_NAMES = {ROLE_PLANAR_CORE: "PLANAR_CORE", ROLE_ROUGH_MEMBER: "ROUGH_MEMBER", ROLE_ABSORBED: "ABSORBED_SMALL"}
PAIR_NONE, PAIR_PLANAR_ALS_NORMAL, PAIR_PLANAR_SEGMENT_NORMAL, PAIR_PLANAR_EUCLIDEAN_FALLBACK = 0, 1, 2, 3
PAIR_ROUGH_CYLINDER, PAIR_ROUGH_EUCLIDEAN_FALLBACK, PAIR_ABSORBED_SMALL_PRIOR = 4, 5, 6
PAIR_RULE_NAMES = {PAIR_NONE: "NONE_PRIOR_ONLY_ZONE", PAIR_PLANAR_ALS_NORMAL: "PLANAR_ALONG_OWN_ALS_NORMAL",
                   PAIR_PLANAR_SEGMENT_NORMAL: "PLANAR_ALONG_ALS_SEGMENT_NORMAL",
                   PAIR_PLANAR_EUCLIDEAN_FALLBACK: "PLANAR_EUCLIDEAN_FALLBACK_NO_NORMAL",
                   PAIR_ROUGH_CYLINDER: "ROUGH_CYLINDER_ALONG_ALS_NORMAL", PAIR_ROUGH_EUCLIDEAN_FALLBACK: "ROUGH_EUCLIDEAN_FALLBACK_NO_NORMAL",
                   PAIR_ABSORBED_SMALL_PRIOR: "ABSORBED_SMALL_PRIOR_COMPONENT_INTO_MVS_UNIT"}
SPLIT_NONE, SPLIT_EXTENT, SPLIT_PRIOR_LAYER = 0, 1, 2
SPLIT_REASON_NAMES = {SPLIT_NONE: "NONE", SPLIT_EXTENT: "EXTENT_CAP", SPLIT_PRIOR_LAYER: "PRIOR_LAYER"}
CORE_RULE_NAMES = {0: "UNRESOLVED", 1: "OWN_SOURCE_CELL_KEY", 2: "OWN_SOURCE_NEAREST_CELL_FALLBACK"}
PROHIBITED_TOKENS = ("uas", "lod2", "footprint", "stable_id", "journal1", "roster")

CELL_DTYPE = np.dtype([
    ("cell_index", "<u4"), ("source", "u1"),
    ("kx", "<i4"), ("ky", "<i4"), ("kz", "<i4"),
    ("x", "<f4"), ("y", "<f4"), ("z", "<f4"), ("point_count", "<u4"),
    ("nx", "<f4"), ("ny", "<f4"), ("nz", "<f4"),
    ("surface_variation", "<f4"), ("normal_valid", "u1"),
    ("segment_id", "<u4"), ("unit_id", "<u4"), ("role", "u1"),
    ("pair_distance_m", "<f4"), ("pair_rule", "u1"),
])

UNIT_DTYPE = np.dtype([
    ("unit_id", "<u4"), ("unit_uid", "S16"), ("primary_source", "u1"), ("kind", "u1"),
    ("small", "u1"), ("split_child", "u1"), ("split_reason", "u1"), ("mixed_prior", "u1"),
    ("absorbed_cell_count", "<u4"),
    ("mvs_cell_count", "<u4"), ("mvs_point_count", "<u4"),
    ("als_cell_count", "<u4"), ("als_point_count", "<u4"),
    ("area_m2", "<f4"),
    ("cx", "<f4"), ("cy", "<f4"), ("cz", "<f4"),
    ("nx", "<f4"), ("ny", "<f4"), ("nz", "<f4"), ("plane_d", "<f4"),
    ("plane_rmse_m", "<f4"), ("plane_p95_abs_residual_m", "<f4"),
    ("extent_e1_m", "<f4"), ("extent_e2_m", "<f4"),
    ("tilt_from_up_deg", "<f4"), ("normal_vs_parent_deg", "<f4"), ("prior_support_fraction", "<f4"),
    ("paired_als_segment_count", "<u4"), ("component_count", "<u4"),
    ("prior_segment_count", "<u4"), ("prior_offset_median_m", "<f4"), ("prior_offset_spread_m", "<f4"),
    ("prior_nx", "<f4"), ("prior_ny", "<f4"), ("prior_nz", "<f4"), ("prior_d", "<f4"), ("prior_plane_rmse_m", "<f4"),
    ("core_count_total", "<u4"), ("core_count_class_1", "<u4"), ("core_count_class_2", "<u4"),
    ("core_count_class_3", "<u4"), ("core_count_class_4", "<u4"), ("core_count_class_5", "<u4"),
    ("bbox_min_x", "<f4"), ("bbox_min_y", "<f4"), ("bbox_min_z", "<f4"),
    ("bbox_max_x", "<f4"), ("bbox_max_y", "<f4"), ("bbox_max_z", "<f4"),
])

ADJACENCY_DTYPE = np.dtype([
    ("unit_a", "<u4"), ("unit_b", "<u4"), ("contact_pairs", "<u4"), ("same_primary", "u1"),
    ("contact_mvs_mvs", "<u4"), ("contact_als_als", "<u4"), ("contact_cross", "<u4"),
])

CORE_DTYPE = np.dtype([
    ("core_row", "<u4"), ("core_source", "u1"), ("relation_class", "u1"),
    ("cell_index", "<u4"), ("unit_id", "<u4"), ("core_rule", "u1"),
])


# ----------------------------------------------------------------------------
# generic helpers
# ----------------------------------------------------------------------------

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path, chunk_bytes: int = 8 << 20) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(chunk_bytes), b""):
            value.update(block)
    return value.hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def array_digest(array: np.ndarray) -> str:
    return sha256_bytes(np.ascontiguousarray(array).tobytes())


def atomic_bytes(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(value)
    os.replace(temporary, path)


def atomic_json(path: Path, value: Any) -> None:
    atomic_bytes(path, (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8"))


def atomic_npy(path: Path, value: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("wb") as stream:
        np.save(stream, value, allow_pickle=False)
    os.replace(temporary, path)


def git_head() -> str:
    env = os.environ.get("JBGS_SOURCE_GIT_HEAD")
    if env:
        return env
    try:
        return subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], check=True,
                              capture_output=True, text=True).stdout.strip()
    except Exception:  # noqa: BLE001 - lineage only
        return "UNKNOWN"


REQUIRED_PROFILE_KEYS = (
    "cell_size_m", "normal_radius_m", "normal_min_neighbors", "seed_max_surface_variation",
    "grow_max_normal_angle_deg", "grow_max_plane_distance_m", "grow_radius_m", "refit_condition_ratio",
    "minimum_unit_area_m2", "maximum_unit_extent_m", "rough_component_radius_m", "rough_attach_radius_m",
    "pair_normal_half_length_m", "pair_rough_radius_m", "pair_inplane_radius_m",
    "prior_layer_split_offset_m", "prior_layer_min_cells", "resolver_radius_m", "adjacency_radius_m",
)


def load_config(path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    cfg = json.loads(path.read_text(encoding="utf-8"))
    if cfg.get("schema") != SCHEMA:
        raise ValueError("region unit config schema drift")
    if cfg.get("status") != "USER_APPROVED_DEVELOPMENT_NON_CONFIRMATORY":
        raise ValueError("region unit run is not user-approved")
    if cfg.get("scientific_verdict", "missing") is not None:
        raise ValueError("scientific_verdict must remain null")
    profiles = cfg["algorithm"]["profiles"]
    if cfg["algorithm"]["selected_profile"] not in profiles:
        raise ValueError("selected profile is not defined")
    serialized = json.dumps({"inputs": cfg["inputs"], "output": cfg["output_relative_root"]}).lower()
    for token in PROHIBITED_TOKENS:
        if token in serialized:
            raise ValueError(f"prohibited input token: {token}")
    domain = cfg["domain"]
    for axis in ("x", "y", "z"):
        low, high = map(float, domain[axis])
        if not high > low:
            raise ValueError(f"domain {axis} is empty")
    for name, profile in profiles.items():
        missing = [key for key in REQUIRED_PROFILE_KEYS if key not in profile]
        if missing:
            raise ValueError(f"profile {name} misses {missing}")
        for key in ("cell_size_m", "normal_radius_m", "grow_radius_m", "minimum_unit_area_m2",
                    "maximum_unit_extent_m", "pair_normal_half_length_m", "resolver_radius_m",
                    "pair_inplane_radius_m", "prior_layer_split_offset_m", "rough_component_radius_m",
                    "rough_attach_radius_m", "pair_rough_radius_m", "adjacency_radius_m", "refit_condition_ratio"):
            if float(profile[key]) <= 0:
                raise ValueError(f"profile {name}: {key} must be positive")
        if int(profile["normal_min_neighbors"]) < 4 or int(profile["prior_layer_min_cells"]) < 1:
            raise ValueError(f"profile {name}: neighbour/cell minimums are too small")
        if float(profile["grow_radius_m"]) < float(profile["cell_size_m"]) * np.sqrt(3.0):
            raise ValueError(f"profile {name}: grow radius smaller than the cell diagonal")
        if float(profile["adjacency_radius_m"]) != float(profile["grow_radius_m"]):
            raise ValueError(f"profile {name}: D-1i requires adjacency_radius_m == grow_radius_m")
    gravity = cfg["inputs"]["gravity_checkpoint"]
    if len(gravity.get("sha256", "")) != 64:
        raise ValueError("gravity checkpoint hash must be pinned")
    return cfg


# ----------------------------------------------------------------------------
# D-1.1 domain and working cells
# ----------------------------------------------------------------------------

def domain_bounds(domain: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    low = np.asarray([domain["x"][0], domain["y"][0], domain["z"][0]], dtype=np.float64)
    high = np.asarray([domain["x"][1], domain["y"][1], domain["z"][1]], dtype=np.float64)
    return low, high


def domain_mask(xyz: np.ndarray, low: np.ndarray, high: np.ndarray) -> np.ndarray:
    return np.all((xyz >= low) & (xyz < high), axis=1)


def read_xyz_bin(path: Path) -> np.ndarray:
    if path.stat().st_size % 12:
        raise ValueError(f"{path}: invalid xyz_f32le byte count")
    return np.fromfile(path, dtype="<f4").reshape(-1, 3)


def cell_keys(xyz: np.ndarray, origin: np.ndarray, cell_size: float) -> np.ndarray:
    return np.floor((np.asarray(xyz, dtype=np.float64) - origin) / cell_size).astype(np.int64)


def voxelize(xyz: np.ndarray, origin: np.ndarray, cell_size: float) -> dict[str, np.ndarray]:
    """Working cells (D-1.1).  Cells ordered by (kx, ky, kz); every point maps to one cell.
    Centroids are summed in a canonical point order so the result is invariant to input permutation."""
    pts = np.asarray(xyz, dtype=np.float64)
    if len(pts) == 0:
        return {"keys": np.zeros((0, 3), np.int64), "centroids": np.zeros((0, 3)), "counts": np.zeros(0, np.int64),
                "point_cell": np.zeros(0, np.int64)}
    keys = cell_keys(pts, origin, cell_size)
    order = np.lexsort((pts[:, 2], pts[:, 1], pts[:, 0], keys[:, 2], keys[:, 1], keys[:, 0]))
    sorted_keys = keys[order]
    change = np.ones(len(order), dtype=bool)
    change[1:] = np.any(sorted_keys[1:] != sorted_keys[:-1], axis=1)
    cell_of_sorted = np.cumsum(change) - 1
    point_cell = np.empty(len(order), dtype=np.int64)
    point_cell[order] = cell_of_sorted
    starts = np.flatnonzero(change)
    counts = np.diff(np.append(starts, len(order)))
    sorted_pts = pts[order]
    centroids = np.add.reduceat(sorted_pts, starts, axis=0) / counts[:, None]
    return {"keys": sorted_keys[change], "centroids": centroids, "counts": counts, "point_cell": point_cell}


# ----------------------------------------------------------------------------
# D-1.2 normals
# ----------------------------------------------------------------------------

def orient_normals(normals: np.ndarray) -> np.ndarray:
    """Deterministic sign: n_z >= 0, ties broken by n_x >= 0 then n_y >= 0."""
    out = np.array(normals, dtype=np.float64, copy=True)
    tie_z = np.isclose(out[:, 2], 0.0)
    tie_x = tie_z & np.isclose(out[:, 0], 0.0)
    flip = np.where(tie_x, out[:, 1] < 0, np.where(tie_z, out[:, 0] < 0, out[:, 2] < 0))
    out[flip] *= -1.0
    return out


def estimate_normals(centroids: np.ndarray, radius: float, min_neighbors: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """PCA normal, surface variation and validity per cell (D-1a)."""
    count = len(centroids)
    normals = np.zeros((count, 3), dtype=np.float64)
    variation = np.full(count, np.nan, dtype=np.float64)
    valid = np.zeros(count, dtype=bool)
    if count == 0:
        return normals, variation, valid
    tree = cKDTree(centroids)
    pairs = tree.query_pairs(radius, output_type="ndarray")
    rows = np.concatenate([pairs[:, 0], pairs[:, 1], np.arange(count)])
    cols = np.concatenate([pairs[:, 1], pairs[:, 0], np.arange(count)])
    neighbors = np.bincount(rows, minlength=count)
    mean = np.zeros((count, 3))
    for axis in range(3):
        mean[:, axis] = np.bincount(rows, weights=centroids[cols, axis], minlength=count) / neighbors
    diff = centroids[cols] - mean[rows]
    cov = np.zeros((count, 3, 3))
    for a in range(3):
        for b in range(a, 3):
            cov[:, a, b] = np.bincount(rows, weights=diff[:, a] * diff[:, b], minlength=count) / neighbors
            cov[:, b, a] = cov[:, a, b]
    ok = neighbors >= int(min_neighbors)
    if np.any(ok):
        values, vectors = np.linalg.eigh(cov[ok])  # ascending eigenvalues
        total = np.sum(values, axis=1)
        normals[ok] = vectors[:, :, 0]
        variation[ok] = np.where(total > 0, values[:, 0] / np.maximum(total, 1e-30), np.nan)
        valid[ok] = np.isfinite(variation[ok]) & (total > 0)
    normals = orient_normals(normals)
    normals[~valid] = 0.0
    return normals, variation, valid


# ----------------------------------------------------------------------------
# plane / frame / area helpers (D-1c)
# ----------------------------------------------------------------------------

def _orthonormal_frame(normal: np.ndarray, major_hint: np.ndarray | None) -> tuple[np.ndarray, np.ndarray]:
    normal = normal / max(np.linalg.norm(normal), 1e-12)
    e1 = None
    if major_hint is not None:
        candidate = major_hint - normal * (normal @ major_hint)
        if np.linalg.norm(candidate) > 1e-9:
            e1 = candidate / np.linalg.norm(candidate)
    if e1 is None:
        base = np.array([1.0, 0.0, 0.0]) if abs(normal[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
        e1 = base - normal * (normal @ base)
        e1 /= np.linalg.norm(e1)
    if (e1[1] < 0) if np.isclose(e1[0], 0.0) else (e1[0] < 0):
        e1 = -e1
    e2 = np.cross(normal, e1)
    return e1, e2


def pca_plane(points: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """centroid, ascending eigenvalues, eigenvectors (columns) of the point covariance."""
    pts = np.asarray(points, dtype=np.float64)
    centre = pts.mean(axis=0)
    cov = np.cov((pts - centre).T, bias=True)
    values, vectors = np.linalg.eigh(cov)
    return centre, values, vectors


def fit_plane(points: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Unguarded PCA plane: centroid, oriented normal, in-plane axes e1 (major), e2."""
    pts = np.asarray(points, dtype=np.float64)
    if len(pts) < 3:
        centre = pts.mean(axis=0) if len(pts) else np.zeros(3)
        normal = np.array([0.0, 0.0, 1.0])
        e1, e2 = _orthonormal_frame(normal, None)
        return centre, normal, e1, e2
    centre, values, vectors = pca_plane(pts)
    normal = orient_normals(vectors[:, 0][None])[0]
    e1, e2 = _orthonormal_frame(normal, vectors[:, 2])
    return centre, normal, e1, e2


def guarded_refit(points: np.ndarray, current_normal: np.ndarray, seed_normal: np.ndarray,
                  cos_max: float, condition_ratio: float) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, bool]:
    """(D-1b) refit accepted only if the in-plane fit is conditioned and stays within theta_max of the seed."""
    pts = np.asarray(points, dtype=np.float64)
    centre = pts.mean(axis=0)
    accepted = False
    normal = current_normal
    major = None
    if len(pts) >= 3:
        _, values, vectors = pca_plane(pts)
        candidate = orient_normals(vectors[:, 0][None])[0]
        conditioned = values[1] >= condition_ratio * max(values[2], 1e-30)
        if conditioned and abs(float(candidate @ seed_normal)) >= cos_max:
            normal = candidate
            accepted = True
        major = vectors[:, 2]
    e1, e2 = _orthonormal_frame(normal, major)
    return centre, normal, e1, e2, accepted


def reference_frame(points: np.ndarray, reference_normal: np.ndarray | None, profile: dict[str, Any]) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Unit-level frame.  With a reference (the guarded region-growing normal of the parent segment) the PCA
    refit is accepted only under the D-1b guards, otherwise the reference normal is kept (thin slivers of a
    ground plane can no longer turn into 'walls')."""
    if reference_normal is None:
        return fit_plane(points)
    pts = np.asarray(points, dtype=np.float64)
    if len(pts) < 3:  # too few cells for any PCA: keep the parent normal outright
        normal = np.asarray(reference_normal, dtype=np.float64)
        e1, e2 = _orthonormal_frame(normal, None)
        return (pts.mean(axis=0) if len(pts) else np.zeros(3)), normal, e1, e2
    cos_max = float(np.cos(np.deg2rad(float(profile["grow_max_normal_angle_deg"]))))
    centre, normal, e1, e2, _ = guarded_refit(points, np.asarray(reference_normal, dtype=np.float64),
                                              np.asarray(reference_normal, dtype=np.float64), cos_max,
                                              float(profile["refit_condition_ratio"]))
    return centre, normal, e1, e2


def in_plane_cells(points: np.ndarray, centre: np.ndarray, e1: np.ndarray, e2: np.ndarray, cell_size: float) -> np.ndarray:
    local = np.asarray(points, dtype=np.float64) - centre
    return np.floor(np.column_stack((local @ e1, local @ e2)) / cell_size).astype(np.int64)


def projected_area(points: np.ndarray, centre: np.ndarray, e1: np.ndarray, e2: np.ndarray, cell_size: float) -> float:
    """(D-1c) occupied in-plane 2D cells x cell_size^2."""
    if len(points) == 0:
        return 0.0
    ij = in_plane_cells(points, centre, e1, e2, cell_size)
    return float(cell_size * cell_size * len(np.unique(ij, axis=0)))


def rough_area(cell_count: int, cell_size: float) -> float:
    """(D-1d) surface proxy for rough components."""
    return float(cell_size * cell_size * int(cell_count))


def component_labels(points: np.ndarray, radius: float) -> np.ndarray:
    """Connected components under a fixed radius, labelled by first occurrence (deterministic)."""
    count = len(points)
    if count == 0:
        return np.zeros(0, dtype=np.int64)
    pairs = cKDTree(points).query_pairs(radius, output_type="ndarray")
    graph = coo_matrix((np.ones(len(pairs), dtype=np.int8), (pairs[:, 0], pairs[:, 1])), shape=(count, count))
    _, labels = connected_components(graph, directed=False)
    uniq, first = np.unique(labels, return_index=True)
    rank = np.argsort(np.argsort(first, kind="stable"), kind="stable")
    remap = np.empty(int(uniq.max()) + 1, dtype=np.int64)
    remap[uniq] = rank
    return remap[labels]


# ----------------------------------------------------------------------------
# D-1.3 region growing
# ----------------------------------------------------------------------------

def _first_refit_size(min_neighbors: int) -> int:
    size = 4
    while size < max(4, int(min_neighbors)):
        size *= 2
    return size


def region_growing(centroids: np.ndarray, normals: np.ndarray, variation: np.ndarray, valid: np.ndarray,
                   profile: dict[str, Any]) -> tuple[np.ndarray, list[dict[str, Any]]]:
    """Deterministic FIFO plane region growing (D-1b).  Returns segment id per cell (0 = residual)."""
    count = len(centroids)
    segment = np.zeros(count, dtype=np.int64)
    segments: list[dict[str, Any]] = []
    if count == 0:
        return segment, segments
    cell = float(profile["cell_size_m"])
    radius = float(profile["grow_radius_m"])
    cos_max = float(np.cos(np.deg2rad(float(profile["grow_max_normal_angle_deg"]))))
    tau = float(profile["grow_max_plane_distance_m"])
    sigma_seed = float(profile["seed_max_surface_variation"])
    area_min = float(profile["minimum_unit_area_m2"])
    condition_ratio = float(profile["refit_condition_ratio"])
    first_refit = _first_refit_size(int(profile["normal_min_neighbors"]))
    tree = cKDTree(centroids)
    neighbor_lists = tree.query_ball_point(centroids, radius)
    neighbor_arrays = [np.sort(np.asarray(items, dtype=np.int64)) for items in neighbor_lists]
    seed_order = np.lexsort((np.arange(count), np.where(valid, variation, np.inf)))
    seed_failed = np.zeros(count, dtype=bool)
    for seed in seed_order:
        if not valid[seed] or not variation[seed] <= sigma_seed:
            break
        if segment[seed] != 0 or seed_failed[seed]:
            continue
        seed_normal = normals[seed].copy()
        plane_n = seed_normal.copy()
        plane_d = float(plane_n @ centroids[seed])
        members = [int(seed)]
        pending_id = len(segments) + 1
        segment[seed] = pending_id
        queue = deque([int(seed)])
        next_refit = first_refit
        while queue:
            current = queue.popleft()
            for other in neighbor_arrays[current]:
                if segment[other] != 0 or not valid[other]:
                    continue
                if abs(float(normals[other] @ plane_n)) < cos_max:
                    continue
                if abs(float(plane_n @ centroids[other] - plane_d)) > tau:
                    continue
                segment[other] = pending_id
                members.append(int(other))
                queue.append(int(other))
                if len(members) >= next_refit:
                    centre, plane_n, _, _, _ = guarded_refit(centroids[members], plane_n, seed_normal, cos_max, condition_ratio)
                    plane_d = float(plane_n @ centre)
                    next_refit *= 2
        member_index = np.asarray(members, dtype=np.int64)
        centre, plane_n, e1, e2, _ = guarded_refit(centroids[member_index], plane_n, seed_normal, cos_max, condition_ratio)
        area = projected_area(centroids[member_index], centre, e1, e2, cell)
        if area < area_min:
            segment[member_index] = 0
            seed_failed[seed] = True
            continue
        segments.append({"id": pending_id, "members": member_index, "centre": centre, "normal": plane_n,
                         "seed_normal": seed_normal, "e1": e1, "e2": e2, "area": area})
    absorb_residual_cells(centroids, segment, segments, neighbor_arrays, profile)
    return segment, segments


def absorb_residual_cells(centroids: np.ndarray, segment: np.ndarray, segments: list[dict[str, Any]],
                          neighbor_arrays: list[np.ndarray], profile: dict[str, Any]) -> int:
    """(D-1b step 2) crease bands: residual cells adjacent (r_g) to a kept segment whose plane distance is
    within tau join the closest such plane regardless of their own (blurred) normal.  Bounded rings."""
    if not segments:
        return 0
    tau = float(profile["grow_max_plane_distance_m"])
    rings = int(np.ceil(float(profile["normal_radius_m"]) / float(profile["grow_radius_m"]))) + 1
    cos_max = float(np.cos(np.deg2rad(float(profile["grow_max_normal_angle_deg"]))))
    condition_ratio = float(profile["refit_condition_ratio"])
    by_id = {item["id"]: item for item in segments}
    cell = float(profile["cell_size_m"])
    absorbed_total = 0
    for _ring in range(rings):
        snapshot = segment.copy()
        additions: dict[int, list[int]] = {}
        for index in np.flatnonzero(snapshot == 0):
            best_id, best_d = 0, tau
            for other in neighbor_arrays[index]:
                sid = int(snapshot[other])
                if sid == 0 or sid not in by_id:
                    continue
                item = by_id[sid]
                d = abs(float(item["normal"] @ centroids[index] - item["normal"] @ item["centre"]))
                if d < best_d or (d == best_d and best_id and sid < best_id):
                    best_id, best_d = sid, d
            if best_id:
                additions.setdefault(best_id, []).append(int(index))
        if not additions:
            break
        for sid, cells in additions.items():
            segment[cells] = sid
            absorbed_total += len(cells)
        for sid in additions:
            item = by_id[sid]
            item["members"] = np.sort(np.concatenate([item["members"], np.asarray(additions[sid], dtype=np.int64)]))
            centre, normal, e1, e2, _ = guarded_refit(centroids[item["members"]], item["normal"], item["seed_normal"],
                                                      cos_max, condition_ratio)
            item.update({"centre": centre, "normal": normal, "e1": e1, "e2": e2,
                         "area": projected_area(centroids[item["members"]], centre, e1, e2, cell)})
    return absorbed_total


# ----------------------------------------------------------------------------
# D-1.4 extent cap and small-child merge
# ----------------------------------------------------------------------------

def child_area(child: np.ndarray, centroids: np.ndarray, kind: int, cell: float, profile: dict[str, Any] | None = None,
               reference_normal: np.ndarray | None = None) -> float:
    if kind == KIND_PLANAR and len(child) >= 3:
        if profile is not None:
            centre, _, e1, e2 = reference_frame(centroids[child], reference_normal, profile)
        else:
            centre, _, e1, e2 = fit_plane(centroids[child])
        return projected_area(centroids[child], centre, e1, e2, cell)
    return rough_area(len(child), cell)


def merge_small_children(children: list[np.ndarray], centroids: np.ndarray, profile: dict[str, Any],
                         kind: int, reference_normal: np.ndarray | None = None) -> list[dict[str, Any]]:
    """Children below A_min merge into the touching child with the largest area (ties: smaller index)."""
    cell = float(profile["cell_size_m"])
    area_min = float(profile["minimum_unit_area_m2"])
    radius = max(float(profile["grow_radius_m"]), float(profile["rough_component_radius_m"]))
    children = [np.sort(np.asarray(child, dtype=np.int64)) for child in children if len(child)]
    areas = [child_area(child, centroids, kind, cell, profile, reference_normal) for child in children]
    alive = [True] * len(children)
    trees = [cKDTree(centroids[child]) for child in children]
    contact = np.zeros((len(children), len(children)), dtype=bool)
    for i in range(len(children)):
        for j in range(i + 1, len(children)):
            if any(len(hits) for hits in trees[i].query_ball_tree(trees[j], radius)):
                contact[i, j] = contact[j, i] = True
    order = sorted(range(len(children)), key=lambda i: (areas[i], i))
    for i in order:
        if not alive[i] or areas[i] >= area_min:
            continue
        candidates = [j for j in range(len(children)) if alive[j] and j != i and contact[i, j]]
        if not candidates:
            continue
        target = max(candidates, key=lambda j: (areas[j], -j))
        children[target] = np.sort(np.concatenate([children[target], children[i]]))
        contact[target] |= contact[i]
        contact[:, target] |= contact[:, i]
        contact[target, target] = False
        areas[target] = child_area(children[target], centroids, kind, cell, profile, reference_normal)
        alive[i] = False
    return [{"members": children[i], "small": int(areas[i] < area_min)} for i in range(len(children)) if alive[i]]


def connected_children(members: np.ndarray, centroids: np.ndarray, profile: dict[str, Any],
                       partition: np.ndarray | None = None) -> list[np.ndarray]:
    """Connected components (max(r_g, r_c)) inside each partition label of a member set."""
    radius = max(float(profile["grow_radius_m"]), float(profile["rough_component_radius_m"]))
    labels = np.zeros(len(members), dtype=np.int64) if partition is None else np.asarray(partition)
    children = []
    for key in np.unique(labels):
        idx = np.flatnonzero(labels == key)
        comp = component_labels(centroids[members[idx]], radius)
        for label in np.unique(comp):
            children.append(members[idx[comp == label]])
    return children


def split_segment(members: np.ndarray, centroids: np.ndarray, profile: dict[str, Any],
                  kind: int = KIND_PLANAR, reference_normal: np.ndarray | None = None) -> list[dict[str, Any]]:
    """(D-1.4) extent cap.  PLANAR: grid along in-plane PCA axes; ROUGH: axis-aligned 3D grid."""
    extent_max = float(profile["maximum_unit_extent_m"])
    pts = centroids[members]
    if kind == KIND_PLANAR:
        centre, _, e1, e2 = reference_frame(pts, reference_normal, profile)
        local = pts - centre
        coords = np.column_stack((local @ e1, local @ e2))
    else:
        coords = pts.copy()
    extent = float(np.max(np.ptp(coords, axis=0))) if len(pts) else 0.0
    if extent <= extent_max:
        area = child_area(np.asarray(members), centroids, kind, float(profile["cell_size_m"]), profile, reference_normal)
        return [{"members": np.sort(members), "split_child": 0, "small": int(area < float(profile["minimum_unit_area_m2"]))}]
    grid = np.floor((coords - coords.min(axis=0)) / extent_max).astype(np.int64)
    grid_key = grid[:, 0] * 10**10 + grid[:, 1] * 10**5 + (grid[:, 2] if grid.shape[1] > 2 else 0)
    children = connected_children(np.asarray(members), centroids, profile, partition=grid_key)
    return [{"members": item["members"], "split_child": 1, "small": item["small"]}
            for item in merge_small_children(children, centroids, profile, kind, reference_normal)]


# ----------------------------------------------------------------------------
# D-1.5 rough regions and per-source unitisation
# ----------------------------------------------------------------------------

def unitize_source(centroids: np.ndarray, normals: np.ndarray, variation: np.ndarray, valid: np.ndarray,
                   profile: dict[str, Any]) -> tuple[np.ndarray, np.ndarray, list[dict[str, Any]]]:
    """D-1.3 + D-1.4 + D-1.5 on one source.  Returns (segment id per cell, role per cell, segments)."""
    cell = float(profile["cell_size_m"])
    area_min = float(profile["minimum_unit_area_m2"])
    count = len(centroids)
    role = np.full(count, ROLE_ROUGH_MEMBER, dtype=np.int64)
    segment_of = np.zeros(count, dtype=np.int64)
    segments: list[dict[str, Any]] = []
    raw_segment, raw_segments = region_growing(centroids, normals, variation, valid, profile)
    for raw in raw_segments:
        for child in split_segment(raw["members"], centroids, profile, reference_normal=raw["normal"]):
            segments.append({"kind": KIND_PLANAR, "members": child["members"], "small": child["small"],
                             "split_child": child["split_child"],
                             "split_reason": SPLIT_EXTENT if child["split_child"] else SPLIT_NONE,
                             "parent": int(raw["id"]), "parent_normal": raw["normal"],
                             "absorbed": np.zeros(0, dtype=np.int64)})
    for index, item in enumerate(segments, start=1):
        segment_of[item["members"]] = index
        role[item["members"]] = ROLE_PLANAR_CORE
    residual = np.flatnonzero(segment_of == 0)
    if len(residual):
        labels = component_labels(centroids[residual], float(profile["rough_component_radius_m"]))
        large_components = []
        small_components = []
        for label in np.unique(labels):
            comp = residual[labels == label]
            if rough_area(len(comp), cell) >= area_min:
                large_components.append(comp)
            else:
                small_components.append(comp)
        for comp in large_components:
            for child in split_segment(np.sort(comp), centroids, profile, kind=KIND_ROUGH):
                segments.append({"kind": KIND_ROUGH, "members": child["members"], "small": child["small"],
                                 "split_child": child["split_child"],
                                 "split_reason": SPLIT_EXTENT if child["split_child"] else SPLIT_NONE,
                                 "parent": 0, "parent_normal": None,
                                 "absorbed": np.zeros(0, dtype=np.int64)})
                segment_of[child["members"]] = len(segments)
                role[child["members"]] = ROLE_ROUGH_MEMBER
        host_cells = np.flatnonzero(segment_of != 0)
        host_tree = cKDTree(centroids[host_cells]) if len(host_cells) else None
        attach_radius = float(profile["rough_attach_radius_m"])
        for comp in small_components:
            attached = False
            if host_tree is not None:
                distance, nearest = host_tree.query(centroids[comp], k=1)
                best = int(np.argmin(distance))
                if distance[best] <= attach_radius:
                    host = int(segment_of[host_cells[nearest[best]]])
                    segments[host - 1]["absorbed"] = np.sort(np.concatenate([segments[host - 1]["absorbed"], comp]))
                    segment_of[comp] = host
                    role[comp] = ROLE_ABSORBED
                    attached = True
            if not attached:
                segments.append({"kind": KIND_ROUGH, "members": np.sort(comp), "small": 1, "split_child": 0,
                                 "split_reason": SPLIT_NONE, "parent": 0, "parent_normal": None,
                                 "absorbed": np.zeros(0, dtype=np.int64)})
                segment_of[comp] = len(segments)
                role[comp] = ROLE_ROUGH_MEMBER
    for item in segments:
        item["all_members"] = np.sort(np.concatenate([item["members"], item["absorbed"]]))
    if np.any(segment_of == 0):
        raise RuntimeError("coverage failure: a working cell has no segment")
    return segment_of, role, segments


# ----------------------------------------------------------------------------
# D-1.6 pairing (D-1e')
# ----------------------------------------------------------------------------

def planar_frame(segment: dict[str, Any], centroids: np.ndarray, profile: dict[str, Any] | None = None) -> dict[str, Any]:
    core = centroids[segment["members"]]
    if profile is not None:
        centre, normal, e1, e2 = reference_frame(core, segment.get("parent_normal"), profile)
    else:
        centre, normal, e1, e2 = fit_plane(core)
    local = core - centre
    plane_2d = np.column_stack((local @ e1, local @ e2))
    return {"centre": centre, "normal": normal, "d": float(normal @ centre), "e1": e1, "e2": e2,
            "tree2d": cKDTree(plane_2d), "bbox_min": core.min(axis=0), "bbox_max": core.max(axis=0)}


def effective_als_normals(als_normals: np.ndarray, als_valid: np.ndarray, als_segment_of: np.ndarray,
                          als_segments: list[dict[str, Any]], als_centroids: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Per ALS cell: own valid normal (source 1), else the plane normal of its planar ALS segment (source 2),
    else none (source 0)."""
    normals = np.array(als_normals, dtype=np.float64, copy=True)
    source = np.where(als_valid, 1, 0).astype(np.int64)
    segment_normal: dict[int, np.ndarray] = {}
    for index, segment in enumerate(als_segments, start=1):
        if segment["kind"] == KIND_PLANAR and len(segment["members"]) >= 3:
            reference = segment.get("parent_normal")
            segment_normal[index] = np.asarray(reference, dtype=np.float64) if reference is not None else fit_plane(als_centroids[segment["members"]])[1]
    for cell_index in np.flatnonzero(~als_valid):
        normal = segment_normal.get(int(als_segment_of[cell_index]))
        if normal is not None:
            normals[cell_index] = normal
            source[cell_index] = 2
    return normals, source


def pair_als_cells(mvs_segments: list[dict[str, Any]], mvs_centroids: np.ndarray, als_centroids: np.ndarray,
                   als_normals: np.ndarray, als_valid: np.ndarray, profile: dict[str, Any],
                   normal_source: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(D-1e') returns (mvs segment index per ALS cell, 0 = prior-only zone), pair distance, pair rule.
    ``normal_source`` (0 none / 1 own / 2 borrowed from the ALS segment) selects the rule label; cells
    without any normal use the Euclidean fallback against planar core cells and rough cells."""
    half = float(profile["pair_normal_half_length_m"])
    rho_rough = float(profile["pair_rough_radius_m"])
    rho_pair = float(profile["pair_inplane_radius_m"])
    tau_same_surface = float(profile["grow_max_plane_distance_m"])
    count = len(als_centroids)
    paired = np.zeros(count, dtype=np.int64)
    distance = np.full(count, np.inf, dtype=np.float64)
    inplane = np.full(count, np.inf, dtype=np.float64)
    rule = np.zeros(count, dtype=np.int64)
    if count == 0:
        return paired, distance, rule
    if normal_source is None:
        normal_source = np.where(als_valid, 1, 0).astype(np.int64)
    has_normal = normal_source > 0
    planar_candidates: dict[int, list[tuple[float, float, int]]] = {}
    planar_cells, planar_owner = [], []
    for index, segment in enumerate(mvs_segments, start=1):
        if segment["kind"] != KIND_PLANAR:
            continue
        planar_cells.append(segment["members"])
        planar_owner.append(np.full(len(segment["members"]), index, dtype=np.int64))
        frame = planar_frame(segment, mvs_centroids, profile)
        low = frame["bbox_min"] - (half + rho_pair)
        high = frame["bbox_max"] + (half + rho_pair)
        candidates = np.flatnonzero(np.all((als_centroids >= low) & (als_centroids <= high), axis=1) & has_normal)
        if not len(candidates):
            continue
        n_u, d_u = frame["normal"], frame["d"]
        x_p = als_centroids[candidates]
        n_p = als_normals[candidates]
        cosine = n_p @ n_u
        usable = np.abs(cosine) >= 1e-6
        if not np.any(usable):
            continue
        t = np.full(len(candidates), np.inf)
        t[usable] = (d_u - x_p[usable] @ n_u) / cosine[usable]
        within = np.abs(t) <= half
        if not np.any(within):
            continue
        hit = x_p[within] + t[within, None] * n_p[within]
        local = hit - frame["centre"]
        plane_2d = np.column_stack((local @ frame["e1"], local @ frame["e2"]))
        d2, _ = frame["tree2d"].query(plane_2d, k=1, distance_upper_bound=rho_pair)
        within_rows = np.flatnonzero(within)
        for local_row in np.flatnonzero(np.isfinite(d2)):
            row = within_rows[local_row]
            p = int(candidates[row])
            planar_candidates.setdefault(p, []).append((float(abs(t[row])), float(d2[local_row]), index))
    # (D-1e') argmin |t| over ALL planar candidates; same-surface ties (within tau) decided by in-plane distance, then index
    for p, items in planar_candidates.items():
        best_along = min(item[0] for item in items)
        along, d2_best, index = min((item for item in items if item[0] <= best_along + tau_same_surface),
                                    key=lambda item: (item[1], item[2]))
        distance[p] = along
        inplane[p] = d2_best
        paired[p] = index
        rule[p] = PAIR_PLANAR_ALS_NORMAL if normal_source[p] == 1 else PAIR_PLANAR_SEGMENT_NORMAL
    no_normal = np.flatnonzero(~has_normal)
    if planar_cells and len(no_normal):
        cells = np.concatenate(planar_cells)
        owner = np.concatenate(planar_owner)
        tree = cKDTree(mvs_centroids[cells])
        d, nearest = tree.query(als_centroids[no_normal], k=1, distance_upper_bound=rho_rough)
        for row in np.flatnonzero(np.isfinite(d)):
            p = int(no_normal[row])
            if d[row] < distance[p]:
                distance[p] = float(d[row])
                paired[p] = int(owner[nearest[row]])
                rule[p] = PAIR_PLANAR_EUCLIDEAN_FALLBACK
    rough_cells, rough_owner = [], []
    for index, segment in enumerate(mvs_segments, start=1):
        if segment["kind"] == KIND_ROUGH:
            rough_cells.append(segment["all_members"])
            rough_owner.append(np.full(len(segment["all_members"]), index, dtype=np.int64))
    if rough_cells:
        cells = np.concatenate(rough_cells)
        owner = np.concatenate(rough_owner)
        rough_xyz = mvs_centroids[cells]
        tree = cKDTree(rough_xyz)
        search = float(np.sqrt(half * half + rho_rough * rho_rough))
        hits = tree.query_ball_point(als_centroids, search)
        for p in range(count):
            found = np.asarray(hits[p], dtype=np.int64)
            if not len(found):
                continue
            delta = rough_xyz[found] - als_centroids[p]
            if has_normal[p]:
                axial = delta @ als_normals[p]
                radial = np.linalg.norm(delta - axial[:, None] * als_normals[p][None, :], axis=1)
                ok = (np.abs(axial) <= half) & (radial <= rho_rough)
                if not np.any(ok):
                    continue
                measure = np.abs(axial[ok])
                rule_here = PAIR_ROUGH_CYLINDER
            else:
                euclid = np.linalg.norm(delta, axis=1)
                ok = euclid <= rho_rough
                if not np.any(ok):
                    continue
                measure = euclid[ok]
                rule_here = PAIR_ROUGH_EUCLIDEAN_FALLBACK
            candidates_owner = owner[found[ok]]
            order = np.lexsort((candidates_owner, measure))
            best = order[0]
            if measure[best] < distance[p]:
                distance[p] = float(measure[best])
                paired[p] = int(candidates_owner[best])
                rule[p] = rule_here
    distance[~np.isfinite(distance)] = np.nan
    return paired, distance, rule


# ----------------------------------------------------------------------------
# D-1.6b prior-layer split (D-1k)
# ----------------------------------------------------------------------------

def prior_layer_statistics(frame: dict[str, Any], als_centroids: np.ndarray, paired_cells: np.ndarray,
                           als_segment_of: np.ndarray, profile: dict[str, Any]) -> dict[str, Any]:
    """Per-unit prior side: per-ALS-segment median offsets, spread, layer groups (D-1k)."""
    tau_split = float(profile["prior_layer_split_offset_m"])
    k_split = int(profile["prior_layer_min_cells"])
    offsets = als_centroids[paired_cells] @ frame["normal"] - frame["d"]
    groups = {}
    for sid in np.unique(als_segment_of[paired_cells]):
        sel = paired_cells[als_segment_of[paired_cells] == sid]
        if len(sel) >= k_split:
            groups[int(sid)] = {"cells": sel, "offset": float(np.median(als_centroids[sel] @ frame["normal"] - frame["d"]))}
    result = {"segment_count": int(len(np.unique(als_segment_of[paired_cells]))) if len(paired_cells) else 0,
              "offset_median": float(np.median(offsets)) if len(offsets) else np.nan,
              "spread": 0.0, "layers": [], "reference": 0}
    if not groups:
        return result
    reference = max(groups, key=lambda sid: (len(groups[sid]["cells"]), -sid))
    ref_offset = groups[reference]["offset"]
    values = [g["offset"] for g in groups.values()]
    result["spread"] = float(max(values) - min(values)) if len(values) > 1 else 0.0
    result["reference"] = reference
    for sid in sorted(groups, key=lambda s: (-len(groups[s]["cells"]), s)):
        if sid != reference and abs(groups[sid]["offset"] - ref_offset) > tau_split:
            result["layers"].append({"segment": sid, "cells": groups[sid]["cells"], "offset": groups[sid]["offset"]})
    return result


def prior_layer_split(mvs_segments: list[dict[str, Any]], mvs_centroids: np.ndarray, als_centroids: np.ndarray,
                      als_segment_of: np.ndarray, paired: np.ndarray, pair_distance: np.ndarray, pair_rule: np.ndarray,
                      profile: dict[str, Any]) -> tuple[list[dict[str, Any]], np.ndarray, np.ndarray, np.ndarray]:
    """(D-1k) carve planar MVS segments whose prior side holds an offset ALS layer with area >= A_min.
    Layers are detected and carved on the whole parent (pre-extent-split) segment so a layer that straddles
    grid children stays one unit; carved pieces are then extent-capped again.  Returns the new segment list
    and re-indexed pairing arrays."""
    cell = float(profile["cell_size_m"])
    area_min = float(profile["minimum_unit_area_m2"])
    new_segments: list[dict[str, Any]] = []
    new_paired = np.zeros_like(paired)
    handled = np.zeros(len(mvs_segments), dtype=bool)
    parents: dict[int, list[int]] = {}
    for index, segment in enumerate(mvs_segments):
        if segment["kind"] == KIND_PLANAR and segment.get("parent", 0):
            parents.setdefault(int(segment["parent"]), []).append(index)

    def emit(segment: dict[str, Any], als_cells: np.ndarray) -> None:
        new_segments.append(segment)
        new_paired[als_cells] = len(new_segments)

    for parent in sorted(parents):
        members_index = parents[parent]
        als_cells = np.flatnonzero(np.isin(paired, [i + 1 for i in members_index]))
        core = np.sort(np.concatenate([mvs_segments[i]["members"] for i in members_index]))
        absorbed = np.sort(np.concatenate([mvs_segments[i]["absorbed"] for i in members_index]))
        if not len(als_cells):
            continue
        parent_normal = mvs_segments[members_index[0]].get("parent_normal")
        frame = planar_frame({"members": core, "parent_normal": parent_normal}, mvs_centroids, profile)
        stats = prior_layer_statistics(frame, als_centroids, als_cells, als_segment_of, profile)
        core_keys = in_plane_cells(mvs_centroids[core], frame["centre"], frame["e1"], frame["e2"], cell)
        core_key_set = set(map(tuple, core_keys.tolist()))
        assignment = np.zeros(len(core), dtype=np.int64)  # 0 = remainder, k = layer k
        layer_number = 0
        uncarved = 0
        for layer in stats["layers"]:
            keys = in_plane_cells(als_centroids[layer["cells"]], frame["centre"], frame["e1"], frame["e2"], cell)
            footprint = set()
            for i, j in keys.tolist():
                for di in (-1, 0, 1):
                    for dj in (-1, 0, 1):
                        if (i + di, j + dj) in core_key_set:
                            footprint.add((i + di, j + dj))
            if cell * cell * len(footprint) < area_min:
                uncarved += 1
                continue
            layer_number += 1
            mask = np.fromiter(((int(i), int(j)) in footprint for i, j in core_keys), dtype=bool, count=len(core))
            assignment[mask & (assignment == 0)] = layer_number
        if not layer_number:
            if uncarved:
                for i in members_index:
                    mvs_segments[i]["mixed_prior"] = 1
            continue
        for i in members_index:
            handled[i] = True
        pieces: list[dict[str, Any]] = []
        for label in range(layer_number + 1):
            part = core[assignment == label]
            if not len(part):
                continue
            children = connected_children(part, mvs_centroids, profile)
            for item in merge_small_children(children, mvs_centroids, profile, KIND_PLANAR, parent_normal):
                for child in split_segment(item["members"], mvs_centroids, profile, reference_normal=parent_normal):
                    pieces.append({"kind": KIND_PLANAR, "members": child["members"],
                                   "small": int(child["small"] or item["small"]),
                                   "split_child": 1, "split_reason": SPLIT_PRIOR_LAYER,
                                   "parent": parent, "parent_normal": parent_normal,
                                   "mixed_prior": int(uncarved > 0),
                                   "absorbed": np.zeros(0, dtype=np.int64)})
        piece_trees = [cKDTree(mvs_centroids[piece["members"]]) for piece in pieces]
        if len(absorbed):
            dist = np.column_stack([tree.query(mvs_centroids[absorbed], k=1)[0] for tree in piece_trees])
            owner = np.argmin(dist, axis=1)
            for k, piece in enumerate(pieces):
                piece["absorbed"] = np.sort(absorbed[owner == k])
        local = als_centroids[als_cells] - frame["centre"]
        als_2d = np.column_stack((local @ frame["e1"], local @ frame["e2"]))
        dist2d = []
        for piece in pieces:
            core_local = mvs_centroids[piece["members"]] - frame["centre"]
            dist2d.append(cKDTree(np.column_stack((core_local @ frame["e1"], core_local @ frame["e2"]))).query(als_2d, k=1)[0])
        owner = np.argmin(np.column_stack(dist2d), axis=1)
        first_id = len(new_segments) + 1
        for piece in pieces:
            new_segments.append(piece)
        new_paired[als_cells] = first_id + owner
    for index, segment in enumerate(mvs_segments):
        if handled[index]:
            continue
        emit(dict(segment), np.flatnonzero(paired == index + 1))
    for item in new_segments:
        item["all_members"] = np.sort(np.concatenate([item["members"], item["absorbed"]]))
    return new_segments, new_paired, pair_distance, pair_rule


# ----------------------------------------------------------------------------
# unit assembly (D-1.6 f/g, D-1.7)
# ----------------------------------------------------------------------------

def plane_statistics(points: np.ndarray, cell: float, reference_normal: np.ndarray | None = None,
                     profile: dict[str, Any] | None = None) -> dict[str, Any]:
    if profile is not None and reference_normal is not None:
        centre, normal, e1, e2 = reference_frame(points, reference_normal, profile)
    else:
        centre, normal, e1, e2 = fit_plane(points)
    local = points - centre
    residual = local @ normal
    a, b = local @ e1, local @ e2
    return {
        "centre": centre, "normal": normal, "e1": e1, "e2": e2,
        "plane_d": float(normal @ centre),
        "rmse": float(np.sqrt(np.mean(residual ** 2))) if len(points) else float("nan"),
        "p95": float(np.percentile(np.abs(residual), 95)) if len(points) else float("nan"),
        "extent_e1": float(a.max() - a.min()) if len(points) else 0.0,
        "extent_e2": float(b.max() - b.min()) if len(points) else 0.0,
        "area": projected_area(points, centre, e1, e2, cell),
    }


def tilt_from_up(normal: np.ndarray, up: np.ndarray) -> float:
    cosine = min(1.0, abs(float(np.dot(normal, up)) / max(np.linalg.norm(normal) * np.linalg.norm(up), 1e-12)))
    return float(np.degrees(np.arccos(cosine)))


def _min_key(keys: np.ndarray) -> tuple[int, int, int]:
    if len(keys) == 0:
        return (2**31, 2**31, 2**31)
    order = np.lexsort((keys[:, 2], keys[:, 1], keys[:, 0]))
    return tuple(int(v) for v in keys[order[0]])


def assemble_units(mvs: dict[str, Any], als: dict[str, Any], mvs_segments: list[dict[str, Any]],
                   als_segments: list[dict[str, Any]], als_segment_of: np.ndarray, als_role: np.ndarray,
                   mvs_role: np.ndarray, paired: np.ndarray, profile: dict[str, Any], up: np.ndarray,
                   namespace: str) -> dict[str, Any]:
    """Prior-only units (D-1f), f_P (D-1g), prior-layer statistics (D-1k), ordering/uids (D-1.7)."""
    cell = float(profile["cell_size_m"])
    area_min = float(profile["minimum_unit_area_m2"])
    rough_radius = float(profile["pair_rough_radius_m"])
    comp_radius = max(float(profile["rough_component_radius_m"]), float(profile["grow_radius_m"]))
    tau_split = float(profile["prior_layer_split_offset_m"])
    attach_radius = float(profile["rough_attach_radius_m"])
    mvs_c, als_c = mvs["centroids"], als["centroids"]
    als_unit_pre = paired.copy()
    als_absorbed_into_mvs = np.zeros(len(als_c), dtype=bool)
    prior_units: list[dict[str, Any]] = []
    host_trees: dict[int, cKDTree] = {}
    als_absorb_distance = np.full(len(als_c), np.nan, dtype=np.float64)
    mvs_cell_segment = np.zeros(len(mvs_c), dtype=np.int64)
    for index, segment in enumerate(mvs_segments, start=1):
        mvs_cell_segment[segment["all_members"]] = index
    mvs_tree = cKDTree(mvs_c) if len(mvs_c) else None

    def host_distance(segment_index: int, cell_ids: np.ndarray) -> np.ndarray:
        # host proximity is measured against every member of the host unit: its MVS cells and its paired ALS cells
        if segment_index not in host_trees:
            host_points = np.concatenate([mvs_c[mvs_segments[segment_index - 1]["all_members"]],
                                          als_c[np.flatnonzero(paired == segment_index)]])
            host_trees[segment_index] = cKDTree(host_points)
        d, _ = host_trees[segment_index].query(als_c[cell_ids], k=1)
        return d

    def within_host(segment_index: int, cell_ids: np.ndarray) -> bool:
        return bool(np.any(host_distance(segment_index, cell_ids) <= attach_radius))

    def nearest_mvs_segment(cell_ids: np.ndarray) -> int:
        if mvs_tree is None:
            return 0
        d, nearest = mvs_tree.query(als_c[cell_ids], k=1, distance_upper_bound=attach_radius)
        if not np.any(np.isfinite(d)):
            return 0
        best = int(np.argmin(np.where(np.isfinite(d), d, np.inf)))
        return int(mvs_cell_segment[nearest[best]])
    for s_index, segment in enumerate(als_segments, start=1):
        members = segment["all_members"]
        only = members[paired[members] == 0]
        if not len(only):
            continue
        labels = component_labels(als_c[only], comp_radius)
        paired_members = members[paired[members] != 0]
        majority = 0
        if len(paired_members):
            majority = int(sorted(Counter(paired[paired_members].tolist()).items(), key=lambda kv: (-kv[1], kv[0]))[0][0])
        for label in np.unique(labels):
            comp = only[labels == label]
            core = comp[als_role[comp] == ROLE_PLANAR_CORE]
            if segment["kind"] == KIND_PLANAR and len(core) >= 3:
                area = plane_statistics(als_c[core], cell)["area"]
                kind = KIND_PLANAR
            else:
                area = rough_area(len(comp), cell)
                kind = KIND_ROUGH
            if area >= area_min:
                prior_units.append({"kind": kind, "members": np.sort(comp), "small": 0, "als_segment": s_index})
                continue
            host = majority if (majority and within_host(majority, comp)) else nearest_mvs_segment(comp)
            if host:
                als_unit_pre[comp] = host
                als_absorbed_into_mvs[comp] = True
                als_absorb_distance[comp] = host_distance(host, comp)
            else:
                prior_units.append({"kind": kind, "members": np.sort(comp), "small": 1, "als_segment": s_index})
    provisional = []
    for index, segment in enumerate(mvs_segments, start=1):
        als_cells = np.flatnonzero(als_unit_pre == index)
        provisional.append({"primary": SOURCE_MVS, "kind": segment["kind"], "mvs_cells": segment["all_members"],
                            "mvs_core": segment["members"], "als_cells": als_cells,
                            "small": int(segment["small"]), "split_child": int(segment["split_child"]),
                            "split_reason": int(segment.get("split_reason", SPLIT_NONE)),
                            "mixed_from_carve": int(segment.get("mixed_prior", 0)),
                            "reference_normal": segment.get("parent_normal"),
                            "absorbed": len(segment["absorbed"]) + int(np.count_nonzero(als_absorbed_into_mvs[als_cells]))})
    for unit in prior_units:
        core = unit["members"][als_role[unit["members"]] == ROLE_PLANAR_CORE]
        provisional.append({"primary": SOURCE_ALS, "kind": unit["kind"], "mvs_cells": np.zeros(0, np.int64),
                            "mvs_core": np.zeros(0, np.int64), "als_cells": unit["members"],
                            "als_core": core if (unit["kind"] == KIND_PLANAR and len(core) >= 3) else unit["members"],
                            "small": unit["small"], "split_child": 0, "split_reason": SPLIT_NONE, "absorbed": 0,
                            "mixed_from_carve": 0,
                            "reference_normal": als_segments[unit["als_segment"] - 1].get("parent_normal")})
    records = []
    for unit in provisional:
        if unit["primary"] == SOURCE_MVS:
            core_points = mvs_c[unit["mvs_core"]]
            all_primary = mvs_c[unit["mvs_cells"]]
            core_keys = mvs["keys"][unit["mvs_core"]]
        else:
            core_points = als_c[unit["als_core"]]
            all_primary = als_c[unit["als_cells"]]
            core_keys = als["keys"][unit["als_core"]]
        if unit["kind"] == KIND_PLANAR and len(core_points) >= 3:
            stats = plane_statistics(core_points, cell, unit.get("reference_normal"), profile)
            area = stats["area"]
        elif unit["kind"] == KIND_PLANAR and unit.get("reference_normal") is not None and len(all_primary):
            stats = plane_statistics(all_primary, cell, unit.get("reference_normal"), profile)  # tiny planar leftovers keep the parent frame
            area = stats["area"]
        else:
            stats = plane_statistics(all_primary, cell) if len(all_primary) >= 3 else None
            area = rough_area(len(all_primary), cell)
        unit.update({"stats": stats, "area": area, "centroid": all_primary.mean(axis=0),
                     "sort_key": (unit["primary"], unit["kind"], -len(core_points), _min_key(core_keys))})
        records.append(unit)
    records.sort(key=lambda u: u["sort_key"])
    mvs_unit = np.zeros(len(mvs_c), dtype=np.int64)
    als_unit = np.zeros(len(als_c), dtype=np.int64)
    units = np.zeros(len(records), dtype=UNIT_DTYPE)
    composition: dict[str, dict[str, int]] = {}
    for unit_id, unit in enumerate(records, start=1):
        mvs_unit[unit["mvs_cells"]] = unit_id
        als_unit[unit["als_cells"]] = unit_id
        keys = [f"M:{k[0]},{k[1]},{k[2]}" for k in mvs["keys"][unit["mvs_cells"]].tolist()]
        keys += [f"P:{k[0]},{k[1]},{k[2]}" for k in als["keys"][unit["als_cells"]].tolist()]
        uid = hashlib.sha256(("|".join([namespace, str(unit["primary"]), str(unit["kind"])] + sorted(keys))).encode("ascii")).hexdigest()[:16]
        stats = unit["stats"]
        row = units[unit_id - 1]
        row["unit_id"] = unit_id
        row["unit_uid"] = uid.encode("ascii")
        row["primary_source"] = unit["primary"]
        row["kind"] = unit["kind"]
        row["small"] = int(bool(unit["small"]) or unit["area"] < area_min)
        row["split_child"] = unit["split_child"]
        row["split_reason"] = unit["split_reason"]
        row["absorbed_cell_count"] = unit["absorbed"]
        row["mvs_cell_count"] = len(unit["mvs_cells"])
        row["mvs_point_count"] = int(mvs["counts"][unit["mvs_cells"]].sum()) if len(unit["mvs_cells"]) else 0
        row["als_cell_count"] = len(unit["als_cells"])
        row["als_point_count"] = int(als["counts"][unit["als_cells"]].sum()) if len(unit["als_cells"]) else 0
        row["area_m2"] = unit["area"]
        row["cx"], row["cy"], row["cz"] = unit["centroid"]
        if stats is not None:
            row["nx"], row["ny"], row["nz"] = stats["normal"]
            row["plane_d"] = stats["plane_d"]
            row["plane_rmse_m"] = stats["rmse"] if unit["kind"] == KIND_PLANAR else np.nan
            row["plane_p95_abs_residual_m"] = stats["p95"] if unit["kind"] == KIND_PLANAR else np.nan
            row["extent_e1_m"], row["extent_e2_m"] = stats["extent_e1"], stats["extent_e2"]
            row["tilt_from_up_deg"] = tilt_from_up(stats["normal"], up)
            reference = unit.get("reference_normal")
            row["normal_vs_parent_deg"] = tilt_from_up(stats["normal"], np.asarray(reference)) if (reference is not None and unit["kind"] == KIND_PLANAR) else np.nan
        else:
            for name in ("nx", "ny", "nz", "plane_d", "plane_rmse_m", "plane_p95_abs_residual_m",
                         "extent_e1_m", "extent_e2_m", "tilt_from_up_deg", "normal_vs_parent_deg"):
                row[name] = np.nan
        if unit["primary"] == SOURCE_MVS:
            core_cells = unit["mvs_cells"][mvs_role[unit["mvs_cells"]] != ROLE_ABSORBED]
            core_points = mvs_c[core_cells] if len(core_cells) else mvs_c[unit["mvs_cells"]]
        else:
            core_points = als_c[unit["als_cells"]]
        row["component_count"] = len(np.unique(component_labels(core_points, comp_radius)))
        bbox_points = np.concatenate([mvs_c[unit["mvs_cells"]], als_c[unit["als_cells"]]])
        row["bbox_min_x"], row["bbox_min_y"], row["bbox_min_z"] = bbox_points.min(axis=0)
        row["bbox_max_x"], row["bbox_max_y"], row["bbox_max_z"] = bbox_points.max(axis=0)
        for name in ("prior_nx", "prior_ny", "prior_nz", "prior_d", "prior_plane_rmse_m",
                     "prior_offset_median_m", "prior_offset_spread_m"):
            row[name] = np.nan
        row["mixed_prior"] = 0
        if unit["primary"] == SOURCE_MVS:
            als_cells = unit["als_cells"]
            segs = Counter(als_segment_of[als_cells].tolist())
            row["paired_als_segment_count"] = len(segs)
            row["prior_segment_count"] = len(segs)
            composition[str(unit_id)] = {str(k): int(v) for k, v in sorted(segs.items())}
            if stats is not None and unit["kind"] == KIND_PLANAR and len(unit["mvs_core"]) >= 3:
                own = set(map(tuple, in_plane_cells(mvs_c[unit["mvs_core"]], stats["centre"], stats["e1"], stats["e2"], rough_radius).tolist()))
                if len(als_cells):
                    hit = set(map(tuple, in_plane_cells(als_c[als_cells], stats["centre"], stats["e1"], stats["e2"], rough_radius).tolist()))
                    row["prior_support_fraction"] = len(own & hit) / max(len(own), 1)
                    frame = {"normal": stats["normal"], "d": stats["plane_d"]}
                    layer = prior_layer_statistics(frame, als_c, als_cells, als_segment_of, profile)
                    row["prior_offset_median_m"] = layer["offset_median"]
                    row["prior_offset_spread_m"] = layer["spread"]
                    # planar: mixed means a detected layer that could not be carved (footprint < A_min), D-1k
                    row["mixed_prior"] = int(unit["mixed_from_carve"] or (layer["spread"] > tau_split and unit["split_reason"] != SPLIT_PRIOR_LAYER))
                else:
                    row["prior_support_fraction"] = 0.0
            else:
                if len(als_cells) and len(unit["mvs_cells"]):
                    tree = cKDTree(als_c[als_cells])
                    d, _ = tree.query(mvs_c[unit["mvs_cells"]], k=1, distance_upper_bound=rough_radius)
                    row["prior_support_fraction"] = float(np.count_nonzero(np.isfinite(d)) / len(unit["mvs_cells"]))
                    if stats is not None:
                        frame = {"normal": stats["normal"], "d": stats["plane_d"]}
                        layer = prior_layer_statistics(frame, als_c, als_cells, als_segment_of, profile)
                        row["prior_offset_median_m"] = layer["offset_median"]
                        row["prior_offset_spread_m"] = layer["spread"]
                        row["mixed_prior"] = int(layer["spread"] > tau_split)  # rough units: recorded, never carved
                else:
                    row["prior_support_fraction"] = 0.0
            if len(als_cells) >= 3:
                prior_stats = plane_statistics(als_c[als_cells], cell)
                row["prior_nx"], row["prior_ny"], row["prior_nz"] = prior_stats["normal"]
                row["prior_d"] = prior_stats["plane_d"]
                row["prior_plane_rmse_m"] = prior_stats["rmse"]
        else:
            row["paired_als_segment_count"] = 0
            row["prior_segment_count"] = 0
            row["prior_support_fraction"] = np.nan
    return {"units": units, "mvs_unit": mvs_unit, "als_unit": als_unit, "composition": composition,
            "als_absorbed_into_mvs": als_absorbed_into_mvs, "als_absorb_distance": als_absorb_distance}


def unit_adjacency(all_centroids: np.ndarray, unit_of: np.ndarray, primary_of_unit: np.ndarray, radius: float,
                   source_of: np.ndarray | None = None) -> np.ndarray:
    """(D-1i) undirected unit adjacency with contact counts and a source-pair breakdown of the contacts."""
    if len(all_centroids) == 0:
        return np.zeros(0, dtype=ADJACENCY_DTYPE)
    pairs = cKDTree(all_centroids).query_pairs(radius, output_type="ndarray")
    ua, ub = unit_of[pairs[:, 0]], unit_of[pairs[:, 1]]
    keep = ua != ub
    lo, hi = np.minimum(ua[keep], ub[keep]), np.maximum(ua[keep], ub[keep])
    if not len(lo):
        return np.zeros(0, dtype=ADJACENCY_DTYPE)
    base = int(unit_of.max()) + 1
    combined = lo.astype(np.int64) * base + hi
    values, inverse, counts = np.unique(combined, return_inverse=True, return_counts=True)
    out = np.zeros(len(values), dtype=ADJACENCY_DTYPE)
    out["unit_a"] = values // base
    out["unit_b"] = values % base
    out["contact_pairs"] = counts
    out["same_primary"] = (primary_of_unit[out["unit_a"] - 1] == primary_of_unit[out["unit_b"] - 1]).astype(np.uint8)
    if source_of is not None:
        sa, sb = source_of[pairs[keep, 0]], source_of[pairs[keep, 1]]
        both_mvs = (sa == SOURCE_MVS) & (sb == SOURCE_MVS)
        both_als = (sa == SOURCE_ALS) & (sb == SOURCE_ALS)
        out["contact_mvs_mvs"] = np.bincount(inverse, weights=both_mvs, minlength=len(values)).astype(np.uint32)
        out["contact_als_als"] = np.bincount(inverse, weights=both_als, minlength=len(values)).astype(np.uint32)
        out["contact_cross"] = np.bincount(inverse, weights=~(both_mvs | both_als), minlength=len(values)).astype(np.uint32)
    return out


# ----------------------------------------------------------------------------
# D-1j relation core -> unit
# ----------------------------------------------------------------------------

def map_relation_cores(cores: dict[str, np.ndarray], cells: np.ndarray, origin: np.ndarray,
                       cell_size: float) -> np.ndarray:
    """(D-1j) core -> own-source cell by key (fallback: nearest own-source cell within one cell diagonal)."""
    count = len(cores["xyz"])
    out = np.zeros(count, dtype=CORE_DTYPE)
    if count == 0:
        return out
    out["core_row"] = cores["row"]
    out["core_source"] = cores["source"]
    out["relation_class"] = cores["relation_class"]
    keys = cell_keys(cores["xyz"], origin, cell_size)
    cell_xyz = np.column_stack((cells["x"], cells["y"], cells["z"])).astype(np.float64)
    for source in (SOURCE_MVS, SOURCE_ALS):
        cell_index = np.flatnonzero(cells["source"] == source)
        lookup = {(int(cells["kx"][i]), int(cells["ky"][i]), int(cells["kz"][i])): int(i) for i in cell_index}
        tree = cKDTree(cell_xyz[cell_index]) if len(cell_index) else None
        for k in np.flatnonzero(cores["source"] == source):
            key = tuple(int(v) for v in keys[k])
            hit = lookup.get(key)
            if hit is not None:
                out["cell_index"][k], out["unit_id"][k], out["core_rule"][k] = hit, cells["unit_id"][hit], 1
            elif tree is not None:
                d, nearest = tree.query(cores["xyz"][k], k=1, distance_upper_bound=cell_size * np.sqrt(3.0))
                if np.isfinite(d):
                    hit = int(cell_index[nearest])
                    out["cell_index"][k], out["unit_id"][k], out["core_rule"][k] = hit, cells["unit_id"][hit], 2
    return out


def core_crosstab(core_map: np.ndarray, cells: np.ndarray, units: np.ndarray) -> dict[str, dict[str, int]]:
    table: dict[str, dict[str, int]] = {}
    for class_id in range(1, 6):
        sel = core_map[core_map["relation_class"] == class_id]
        row = {"cores": int(len(sel)), "unresolved": int(np.count_nonzero(sel["unit_id"] == 0))}
        resolved = sel[sel["unit_id"] > 0]
        mvs = resolved[resolved["core_source"] == SOURCE_MVS]
        als = resolved[resolved["core_source"] == SOURCE_ALS]
        row["mvs_core_unit_with_prior_side"] = int(np.count_nonzero(units["als_cell_count"][mvs["unit_id"] - 1] > 0)) if len(mvs) else 0
        row["mvs_core_unit_without_prior_side"] = int(len(mvs)) - row["mvs_core_unit_with_prior_side"]
        row["als_core_cell_paired"] = int(np.count_nonzero(cells["pair_rule"][als["cell_index"]] > 0)) if len(als) else 0
        row["als_core_cell_prior_only"] = int(len(als)) - row["als_core_cell_paired"]
        table[str(class_id)] = row
    return table


# ----------------------------------------------------------------------------
# D-1.8 resolver
# ----------------------------------------------------------------------------

class UnitResolver:
    """Gaussian centre -> unit id (0 = UNRESOLVED) over ALL member cells within resolver_radius_m (D-1h).
    ``delta`` (3-vector) shifts the Existing ALS cells by T(δ) before the query; T0 uses δ = 0."""

    def __init__(self, cells: np.ndarray, units: np.ndarray, radius: float, delta: np.ndarray | None = None):
        xyz = np.column_stack((cells["x"], cells["y"], cells["z"])).astype(np.float64)
        if delta is not None:
            xyz[cells["source"] == SOURCE_ALS] += np.asarray(delta, dtype=np.float64)
        self.radius = float(radius)
        self.sets = []
        for source in (SOURCE_MVS, SOURCE_ALS):
            index = np.flatnonzero(cells["source"] == source)
            if len(index):
                self.sets.append((cKDTree(xyz[index]), cells["unit_id"][index].astype(np.int64), index))

    def resolve(self, points: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        pts = np.atleast_2d(np.asarray(points, dtype=np.float64))
        best_d = np.full(len(pts), np.inf)
        best_u = np.zeros(len(pts), dtype=np.int64)
        for tree, unit_ids, _index in self.sets:  # MVS first, so equal distances keep the MVS answer
            d, nearest = tree.query(pts, k=1, distance_upper_bound=self.radius + 1e-9)
            ok = np.isfinite(d) & ((d < best_d) | (np.isclose(d, best_d) & (unit_ids[np.minimum(nearest, len(unit_ids) - 1)] < best_u)))
            best_d[ok] = d[ok]
            best_u[ok] = unit_ids[nearest[ok]]
        best_d[~np.isfinite(best_d)] = np.nan
        return best_u, best_d


# ----------------------------------------------------------------------------
# whole pipeline
# ----------------------------------------------------------------------------

def build_region_units(mvs_xyz: np.ndarray, als_xyz: np.ndarray, domain: dict[str, Any], profile: dict[str, Any],
                       up: np.ndarray, namespace: str, cores: dict[str, np.ndarray] | None = None) -> dict[str, Any]:
    """Run D-1 on in-domain points of both sources; returns arrays and accounting."""
    low, high = domain_bounds(domain)
    cell = float(profile["cell_size_m"])
    keep_m = domain_mask(mvs_xyz, low, high)
    keep_p = domain_mask(als_xyz, low, high)
    rows_m = np.flatnonzero(keep_m).astype(np.uint32)
    rows_p = np.flatnonzero(keep_p).astype(np.uint32)
    mvs = voxelize(mvs_xyz[keep_m], low, cell)
    als = voxelize(als_xyz[keep_p], low, cell)
    per_source = {}
    for name, data in (("mvs", mvs), ("als", als)):
        normals, variation, valid = estimate_normals(data["centroids"], float(profile["normal_radius_m"]),
                                                     int(profile["normal_min_neighbors"]))
        segment_of, role, segments = unitize_source(data["centroids"], normals, variation, valid, profile)
        per_source[name] = {"normals": normals, "variation": variation, "valid": valid,
                            "segment_of": segment_of, "role": role, "segments": segments}
    als_pair_normals, als_normal_source = effective_als_normals(
        per_source["als"]["normals"], per_source["als"]["valid"], per_source["als"]["segment_of"],
        per_source["als"]["segments"], als["centroids"])
    paired, pair_distance, pair_rule = pair_als_cells(per_source["mvs"]["segments"], mvs["centroids"], als["centroids"],
                                                      als_pair_normals, per_source["als"]["valid"], profile,
                                                      normal_source=als_normal_source)
    mvs_segments, paired, pair_distance, pair_rule = prior_layer_split(
        per_source["mvs"]["segments"], mvs["centroids"], als["centroids"], per_source["als"]["segment_of"],
        paired, pair_distance, pair_rule, profile)
    mvs_segment_of = np.zeros(len(mvs["centroids"]), dtype=np.int64)
    for index, item in enumerate(mvs_segments, start=1):
        mvs_segment_of[item["all_members"]] = index
    assembled = assemble_units(mvs, als, mvs_segments, per_source["als"]["segments"], per_source["als"]["segment_of"],
                               per_source["als"]["role"], per_source["mvs"]["role"], paired, profile, up, namespace)
    units = assembled["units"]
    absorbed = assembled["als_absorbed_into_mvs"]
    pair_rule = np.where(absorbed, PAIR_ABSORBED_SMALL_PRIOR, pair_rule)
    pair_distance = np.where(absorbed, assembled["als_absorb_distance"], pair_distance)
    cells = np.zeros(len(mvs["centroids"]) + len(als["centroids"]), dtype=CELL_DTYPE)
    offset = 0
    for source, data, name, unit_of, seg_of in ((SOURCE_MVS, mvs, "mvs", assembled["mvs_unit"], mvs_segment_of),
                                                 (SOURCE_ALS, als, "als", assembled["als_unit"], per_source["als"]["segment_of"])):
        n = len(data["centroids"])
        block = cells[offset:offset + n]
        block["cell_index"] = np.arange(offset, offset + n)
        block["source"] = source
        block["kx"], block["ky"], block["kz"] = data["keys"].T
        block["x"], block["y"], block["z"] = data["centroids"].T
        block["point_count"] = data["counts"]
        block["nx"], block["ny"], block["nz"] = per_source[name]["normals"].T
        block["surface_variation"] = per_source[name]["variation"]
        block["normal_valid"] = per_source[name]["valid"].astype(np.uint8)
        block["segment_id"] = seg_of
        block["unit_id"] = unit_of
        block["role"] = per_source[name]["role"]
        block["pair_distance_m"] = np.nan if source == SOURCE_MVS else pair_distance
        block["pair_rule"] = 0 if source == SOURCE_MVS else pair_rule
        offset += n
    if np.any(cells["unit_id"] == 0):
        raise RuntimeError("coverage failure: a working cell has no unit")
    all_centroids = np.column_stack((cells["x"], cells["y"], cells["z"])).astype(np.float64)
    adjacency = unit_adjacency(all_centroids, cells["unit_id"].astype(np.int64), units["primary_source"],
                               float(profile["adjacency_radius_m"]), source_of=cells["source"].astype(np.int64))
    core_map = map_relation_cores(cores, cells, low, cell) if cores is not None else np.zeros(0, dtype=CORE_DTYPE)
    if len(core_map):
        for class_id in range(1, 6):
            counts = np.bincount(core_map["unit_id"][core_map["relation_class"] == class_id], minlength=len(units) + 1)[1:]
            units[f"core_count_class_{class_id}"] = counts
        units["core_count_total"] = np.bincount(core_map["unit_id"], minlength=len(units) + 1)[1:]
    point_cell_mvs = mvs["point_cell"].astype(np.uint32)
    point_cell_als = (als["point_cell"] + len(mvs["centroids"])).astype(np.uint32)
    accounting = coverage_accounting(cells, units, adjacency, core_map, profile, len(rows_m), len(rows_p))
    return {
        "cells": cells, "units": units, "adjacency": adjacency, "core_map": core_map,
        "point_rows_mvs": rows_m, "point_rows_als": rows_p,
        "point_cell_mvs": point_cell_mvs, "point_cell_als": point_cell_als,
        "composition": assembled["composition"], "accounting": accounting,
        "unit_set_sha256": array_digest(np.column_stack((cells["cell_index"], cells["unit_id"])).astype("<u4")),
    }


def coverage_accounting(cells: np.ndarray, units: np.ndarray, adjacency: np.ndarray, core_map: np.ndarray,
                        profile: dict[str, Any], n_points_mvs: int, n_points_als: int) -> dict[str, Any]:
    if len(units) == 0 or len(cells) == 0:
        raise RuntimeError("no working cells in domain")
    area_min = float(profile["minimum_unit_area_m2"])
    extent_cap = 2.0 * float(profile["maximum_unit_extent_m"])
    tau_split = float(profile["prior_layer_split_offset_m"])
    mvs_units = units[units["primary_source"] == SOURCE_MVS]
    prior_units = units[units["primary_source"] == SOURCE_ALS]
    als_cells = cells[cells["source"] == SOURCE_ALS]

    def kind_counts(rows: np.ndarray) -> dict[str, int]:
        return {KIND_NAMES[k]: int(np.count_nonzero(rows["kind"] == k)) for k in (KIND_PLANAR, KIND_ROUGH)}

    def quantiles(values: np.ndarray, names=(("p10", 10), ("p50", 50), ("p90", 90))) -> dict[str, float | None]:
        values = np.asarray(values, dtype=np.float64)
        values = values[np.isfinite(values)]
        return {q: (float(np.percentile(values, p)) if len(values) else None) for q, p in names}

    area = units["area_m2"].astype(np.float64)
    extents = np.nan_to_num(np.column_stack((units["extent_e1_m"], units["extent_e2_m"])).astype(np.float64), nan=0.0)
    extent = np.max(extents, axis=1)
    planar_units = mvs_units[mvs_units["kind"] == KIND_PLANAR]
    spread = planar_units["prior_offset_spread_m"].astype(np.float64)
    layered = np.isfinite(spread) & (spread > tau_split)
    unflagged = layered & (planar_units["split_reason"] != SPLIT_PRIOR_LAYER) & (planar_units["mixed_prior"] != 1)
    return {
        "criterion_1_connected_area": {
            "units_with_one_component": int(np.count_nonzero(units["component_count"] == 1)),
            "units_total": int(len(units)),
            "max_unit_normal_vs_parent_deg": float(np.nanmax(units["normal_vs_parent_deg"])) if np.any(np.isfinite(units["normal_vs_parent_deg"])) else None,
            "area_m2_quantiles": quantiles(area, (("p10", 10), ("p50", 50), ("p90", 90), ("max", 100))),
        },
        "criterion_2_coverage": {
            "mvs_cells": int(np.count_nonzero(cells["source"] == SOURCE_MVS)),
            "als_cells": int(len(als_cells)),
            "cells_assigned": int(np.count_nonzero(cells["unit_id"] > 0)),
            "cells_unassigned": int(np.count_nonzero(cells["unit_id"] == 0)),
            "mvs_points_in_domain": int(n_points_mvs),
            "als_points_in_domain": int(n_points_als),
            "deleted": 0,
            "role_counts": {ROLE_NAMES[r]: int(np.count_nonzero(cells["role"] == r)) for r in ROLE_NAMES},
        },
        "criterion_3_scale": {
            "units_below_minimum_area": int(np.count_nonzero(area < area_min)),
            "units_below_minimum_area_flagged_small": int(np.count_nonzero((area < area_min) & (units["small"] == 1))),
            "units_over_extent_cap": int(np.count_nonzero(extent > extent_cap + 1e-6)),
            "small_units": int(np.count_nonzero(units["small"] == 1)),
            "split_children": int(np.count_nonzero(units["split_child"] == 1)),
            "split_reason_counts": {SPLIT_REASON_NAMES[k]: int(np.count_nonzero(units["split_reason"] == k)) for k in SPLIT_REASON_NAMES},
        },
        "criterion_3b_prior_layer": {
            "scope": "PLANAR_MVS_UNITS (rough units record spread only)",
            "mvs_units_with_layer_spread": int(np.count_nonzero(layered)),
            "mvs_units_split_by_prior_layer": int(np.count_nonzero(planar_units["split_reason"] == SPLIT_PRIOR_LAYER)),
            "mvs_units_flagged_mixed_prior": int(np.count_nonzero(planar_units["mixed_prior"] == 1)),
            "mvs_units_layered_but_unflagged": int(np.count_nonzero(unflagged)),
            "rough_mvs_units_with_layer_spread": int(np.count_nonzero(np.nan_to_num(mvs_units["prior_offset_spread_m"][mvs_units["kind"] == KIND_ROUGH]) > tau_split)),
            "prior_offset_spread_quantiles": quantiles(spread),
            "prior_offset_median_quantiles": quantiles(planar_units["prior_offset_median_m"]),
        },
        "criterion_4_pairing": {
            "als_cells_paired": int(np.count_nonzero(als_cells["pair_rule"] > 0)),
            "als_cells_prior_only_zone": int(np.count_nonzero(als_cells["pair_rule"] == 0)),
            "pair_rule_counts": {PAIR_RULE_NAMES[k]: int(np.count_nonzero(als_cells["pair_rule"] == k)) for k in PAIR_RULE_NAMES},
            "mvs_primary_units": int(len(mvs_units)),
            "mvs_primary_kind_counts": kind_counts(mvs_units),
            "prior_only_units": int(len(prior_units)),
            "prior_only_kind_counts": kind_counts(prior_units),
            "mvs_units_without_prior_side": int(np.count_nonzero(mvs_units["als_cell_count"] == 0)),
            "prior_support_fraction_quantiles": quantiles(mvs_units["prior_support_fraction"]),
            "pair_distance_quantiles_m": quantiles(als_cells["pair_distance_m"]),
            "bank_core_crosstab": core_crosstab(core_map, cells, units) if len(core_map) else {},
        },
        "criterion_6_lineage": {
            "unit_ids_contiguous": bool(np.array_equal(units["unit_id"], np.arange(1, len(units) + 1))),
            "uids_unique": bool(len(set(map(bytes, units["unit_uid"]))) == len(units)),
            "adjacency_edges": int(len(adjacency)),
            "adjacency_same_primary_edges": int(np.count_nonzero(adjacency["same_primary"] == 1)),
            "adjacency_edges_with_mvs_mvs_contact": int(np.count_nonzero(adjacency["contact_mvs_mvs"] > 0)) if len(adjacency) else 0,
            "adjacency_edges_cross_source_only": int(np.count_nonzero((adjacency["contact_mvs_mvs"] == 0) & (adjacency["contact_als_als"] == 0))) if len(adjacency) else 0,
            "relation_cores_in_domain": int(len(core_map)),
            "relation_cores_unresolved": int(np.count_nonzero(core_map["unit_id"] == 0)) if len(core_map) else 0,
            "relation_core_rule_counts": {CORE_RULE_NAMES[k]: int(np.count_nonzero(core_map["core_rule"] == k)) for k in CORE_RULE_NAMES} if len(core_map) else {},
            "units_with_zero_cores": int(np.count_nonzero(units["core_count_total"] == 0)) if len(core_map) else None,
        },
    }


# ----------------------------------------------------------------------------
# outputs
# ----------------------------------------------------------------------------

def uid_rgb(uid: bytes) -> tuple[int, int, int]:
    digest = hashlib.sha256(uid).digest()
    r, g, b = colorsys.hls_to_rgb(digest[0] / 255.0, 0.55, 0.72)
    return int(r * 255), int(g * 255), int(b * 255)


def write_unit_ply(path: Path, cells: np.ndarray, units: np.ndarray) -> None:
    dtype = np.dtype([
        ("x", "<f4"), ("y", "<f4"), ("z", "<f4"),
        ("red", "u1"), ("green", "u1"), ("blue", "u1"),
        ("source", "u1"), ("unit_id", "<u4"), ("kind", "u1"), ("role", "u1"),
    ])
    out = np.empty(len(cells), dtype=dtype)
    out["x"], out["y"], out["z"] = cells["x"], cells["y"], cells["z"]
    colors = np.array([uid_rgb(bytes(u)) for u in units["unit_uid"]], dtype=np.uint8)
    rgb = colors[cells["unit_id"] - 1]
    out["red"], out["green"], out["blue"] = rgb.T
    out["source"] = cells["source"]
    out["unit_id"] = cells["unit_id"]
    out["kind"] = units["kind"][cells["unit_id"] - 1]
    out["role"] = cells["role"]
    header = ("ply\nformat binary_little_endian 1.0\n" + f"element vertex {len(out)}\n" +
              "\n".join(["property float x", "property float y", "property float z",
                         "property uchar red", "property uchar green", "property uchar blue",
                         "property uchar source", "property uint unit_id", "property uchar kind",
                         "property uchar role"]) + "\nend_header\n")
    atomic_bytes(path, header.encode("ascii") + out.tobytes())


def write_units_csv(path: Path, units: np.ndarray) -> None:
    buffer = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=buffer, mtime=0) as gz:
        text = io.TextIOWrapper(gz, encoding="utf-8", newline="")
        writer = csv.writer(text)
        writer.writerow(units.dtype.names)
        for row in units:
            writer.writerow([bytes(v).decode("ascii") if isinstance(v, bytes) else (float(v) if isinstance(v, np.floating) else int(v)) for v in row])
        text.flush()
        text.detach()
    atomic_bytes(path, buffer.getvalue())


def write_preview(path: Path, cells: np.ndarray, units: np.ndarray, domain: dict[str, Any]) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    colors = np.array([uid_rgb(bytes(u)) for u in units["unit_uid"]], dtype=np.float64) / 255.0
    fig, axes = plt.subplots(1, 3, figsize=(18, 6.4), dpi=130)
    titles = ("MVS cells · unit uid", "ALS cells · unit uid (paired = MVS unit colour)", "unit kind / primary")
    for axis, title in zip(axes, titles):
        axis.set_title(title, fontsize=10)
        axis.set_xlim(domain["x"]); axis.set_ylim(domain["y"]); axis.set_aspect("equal"); axis.grid(alpha=0.2)
    m = cells["source"] == SOURCE_MVS
    axes[0].scatter(cells["x"][m], cells["y"][m], s=1.2, c=colors[cells["unit_id"][m] - 1], linewidths=0)
    p = ~m
    axes[1].scatter(cells["x"][p], cells["y"][p], s=2.2, c=colors[cells["unit_id"][p] - 1], linewidths=0)
    kind = units["kind"][cells["unit_id"] - 1]
    primary = units["primary_source"][cells["unit_id"] - 1]
    palette = {(0, 0): "#22c55e", (0, 1): "#f97316", (1, 0): "#a855f7", (1, 1): "#ef4444"}
    labels = {(0, 0): "MVS planar", (0, 1): "MVS rough", (1, 0): "prior-only planar", (1, 1): "prior-only rough"}
    for key, color in palette.items():
        sel = (primary == key[0]) & (kind == key[1])
        axes[2].scatter(cells["x"][sel], cells["y"][sel], s=1.5, c=color, linewidths=0, label=f"{labels[key]} ({int(sel.sum())})")
    axes[2].legend(loc="upper right", fontsize=7, markerscale=5)
    fig.suptitle("T0 region unit v1 — pilot prism top view (development, non-confirmatory; no verdict)", fontsize=11)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)


def adjusted_rand_index(a: np.ndarray, b: np.ndarray) -> float:
    """Adjusted Rand index between two labelings (numpy only)."""
    a = np.asarray(a); b = np.asarray(b)
    if len(a) == 0:
        return float("nan")
    _, ia = np.unique(a, return_inverse=True)
    _, ib = np.unique(b, return_inverse=True)
    pair = ia.astype(np.int64) * (int(ib.max()) + 1) + ib
    _, nij = np.unique(pair, return_counts=True)
    ai = np.bincount(ia); bj = np.bincount(ib)
    comb = lambda x: (x.astype(np.float64) * (x - 1.0)) / 2.0  # noqa: E731
    sum_ij, sum_a, sum_b = comb(nij).sum(), comb(ai).sum(), comb(bj).sum()
    total = comb(np.asarray([len(a)]))[0]
    expected = sum_a * sum_b / total if total else 0.0
    maximum = (sum_a + sum_b) / 2.0
    return float((sum_ij - expected) / (maximum - expected)) if maximum != expected else 1.0


def cell_size_sensitivity(mvs_xyz: np.ndarray, als_xyz: np.ndarray, domain: dict[str, Any], base_profile: dict[str, Any],
                          up: np.ndarray, sweep: list[dict[str, Any]], selected_name: str) -> dict[str, Any]:
    """(D-1.9 / D-1.11) rerun the pipeline with the working-cell size changed and compare point-level
    membership (ARI) against the selected profile.  Raw region-growing labels isolate the segmentation
    sensitivity from the extent-cap grid; the planar/rough role isolates the classification sensitivity."""
    low, high = domain_bounds(domain)
    keep_m = domain_mask(mvs_xyz, low, high); keep_p = domain_mask(als_xyz, low, high)
    runs = {}
    for item in [{"cell_size_m": float(base_profile["cell_size_m"]), "grow_radius_m": float(base_profile["grow_radius_m"]), "label": selected_name}] + sweep:
        profile = dict(base_profile)
        profile["cell_size_m"] = float(item["cell_size_m"])
        for key in ("grow_radius_m", "rough_component_radius_m", "adjacency_radius_m"):
            profile[key] = float(item["grow_radius_m"])
        started = time.perf_counter()
        built = build_region_units(mvs_xyz, als_xyz, domain, profile, up, f"sensitivity|{item['cell_size_m']}")
        cells, units = built["cells"], built["units"]
        raw_labels = {}
        role_labels = {}
        for name, pts, rows in (("mvs", mvs_xyz[keep_m], built["point_cell_mvs"]), ("als", als_xyz[keep_p], built["point_cell_als"])):
            data = voxelize(pts, low, float(profile["cell_size_m"]))
            normals, variation, valid = estimate_normals(data["centroids"], float(profile["normal_radius_m"]), int(profile["normal_min_neighbors"]))
            raw_segment, _ = region_growing(data["centroids"], normals, variation, valid, profile)
            raw_labels[name] = raw_segment[data["point_cell"]]
            role_labels[name] = (cells["role"][rows] == ROLE_PLANAR_CORE).astype(np.int64)
        acc = built["accounting"]
        runs[str(item["cell_size_m"])] = {
            "label": item.get("label", ""), "grow_radius_m": float(item["grow_radius_m"]),
            "cells": int(len(cells)), "units": int(len(units)),
            "mvs_planar_units": int(np.count_nonzero((units["primary_source"] == SOURCE_MVS) & (units["kind"] == KIND_PLANAR))),
            "mvs_rough_units": int(np.count_nonzero((units["primary_source"] == SOURCE_MVS) & (units["kind"] == KIND_ROUGH))),
            "prior_only_units": int(np.count_nonzero(units["primary_source"] == SOURCE_ALS)),
            "small_units": int(np.count_nonzero(units["small"] == 1)),
            "layer_split_units": acc["criterion_3b_prior_layer"]["mvs_units_split_by_prior_layer"],
            "als_paired_fraction": acc["criterion_4_pairing"]["als_cells_paired"] / max(1, len(cells[cells["source"] == SOURCE_ALS])),
            "rough_cell_fraction": acc["criterion_2_coverage"]["role_counts"]["ROUGH_MEMBER"] / max(1, len(cells)),
            "planar_area_sum_m2": float(units["area_m2"][(units["primary_source"] == SOURCE_MVS) & (units["kind"] == KIND_PLANAR)].sum()),
            "area_p50_m2": acc["criterion_1_connected_area"]["area_m2_quantiles"]["p50"],
            "elapsed_seconds": time.perf_counter() - started,
            "_unit_labels": (cells["unit_id"][built["point_cell_mvs"]], cells["unit_id"][built["point_cell_als"]]),
            "_raw_labels": (raw_labels["mvs"], raw_labels["als"]),
            "_role_labels": (role_labels["mvs"], role_labels["als"]),
        }
    ref = runs[str(float(base_profile["cell_size_m"]))]
    for key, run_item in runs.items():
        for kind, field in (("unit", "_unit_labels"), ("raw_segment", "_raw_labels"), ("planar_role", "_role_labels")):
            run_item[f"ari_{kind}_mvs_points"] = adjusted_rand_index(ref[field][0], run_item[field][0])
            run_item[f"ari_{kind}_als_points"] = adjusted_rand_index(ref[field][1], run_item[field][1])
        run_item["planar_role_agreement_mvs_points"] = float(np.mean(ref["_role_labels"][0] == run_item["_role_labels"][0]))
    for run_item in runs.values():  # drop the label arrays only after every comparison used the reference
        for field in ("_unit_labels", "_raw_labels", "_role_labels"):
            del run_item[field]
    return {"reference_cell_size_m": float(base_profile["cell_size_m"]), "runs": runs,
            "note": "ARI = adjusted Rand index of point-level membership versus the selected cell size; unit = final units (includes the extent-cap grid), raw_segment = region-growing segments before the grid, planar_role = planar-core vs rough/absorbed."}


def resolve_inputs(cfg: dict[str, Any]) -> dict[str, Any]:
    root = Path(cfg["artifact_root"])
    relation_root = root / cfg["inputs"]["source_relation_relative_root"]
    resolved = {}

    def verify(path: Path, item: dict[str, Any], label: str) -> None:
        if not path.is_file() or path.stat().st_size != int(item["bytes"]) or sha256(path) != item["sha256"]:
            raise RuntimeError(f"input drift: {label}")

    receipt = cfg["inputs"]["partition_receipt"]
    path = relation_root / receipt["relative_path"]
    verify(path, receipt, "partition receipt")
    resolved["partition_receipt"] = {"path": str(path), "bytes": int(receipt["bytes"]), "sha256": receipt["sha256"]}
    for key in ("mvs", "existing_als"):
        item = cfg["inputs"]["partitions"][key]
        path = relation_root / item["relative_path"]
        verify(path, item, f"partition {key}")
        resolved[key] = {"path": str(path), "bytes": int(item["bytes"]), "sha256": item["sha256"],
                         "point_count": int(item["point_count"])}
    relation = cfg["inputs"]["relation_map"]
    path = relation_root / relation["relative_path"]
    verify(path, relation, "relation map")
    resolved["relation_map"] = {"path": str(path), "bytes": int(relation["bytes"]), "sha256": relation["sha256"],
                                "use": relation["use"]}
    gravity = cfg["inputs"]["gravity_checkpoint"]
    path = root / gravity["relative_path"]
    verify(path, gravity, "gravity checkpoint")
    payload = json.loads(path.read_text(encoding="utf-8"))["payload"]["gravity"]
    if payload.get("hardcoded_gravity") is not False:
        raise RuntimeError("gravity checkpoint is not an estimated gravity")
    resolved["gravity"] = {"path": str(path), "bytes": int(gravity["bytes"]), "sha256": gravity["sha256"],
                           "up": [float(v) for v in payload["up"]], "hardcoded_gravity": False,
                           "use": gravity["use"]}
    return resolved


def load_cores(path: Path, domain: dict[str, Any]) -> dict[str, np.ndarray]:
    rows = np.load(path, allow_pickle=False)
    xyz = np.column_stack((rows["x"], rows["y"], rows["z"])).astype(np.float32)
    low, high = domain_bounds(domain)
    keep = domain_mask(xyz.astype(np.float64), low, high)
    index = np.flatnonzero(keep)
    return {"row": index.astype(np.uint32), "xyz": xyz[index], "source": rows["core_source"][index].astype(np.int64),
            "relation_class": rows["relation_class"][index].astype(np.int64)}


def uid_namespace(resolved: dict[str, Any], domain: dict[str, Any], profile: dict[str, Any], profile_name: str) -> str:
    low, _ = domain_bounds(domain)
    return "|".join([UID_NAMESPACE, resolved["mvs"]["sha256"], resolved["existing_als"]["sha256"],
                     ",".join(f"{v:.6f}" for v in low), f"{float(profile['cell_size_m']):.6f}", profile_name])


def run(cfg: dict[str, Any], config_path: Path) -> dict[str, Any]:
    started = time.perf_counter()
    root = Path(cfg["artifact_root"])
    out = root / cfg["output_relative_root"]
    out.mkdir(parents=True, exist_ok=True)
    resolved = resolve_inputs(cfg)
    atomic_json(out / "resolved_input_manifest.json", {"schema": "jointbuildgs.phd.region_unit.resolved_inputs.v1",
                                                       "task_id": cfg["task_id"], "inputs": resolved,
                                                       "prohibited_inputs_accessed": [], "scientific_verdict": None})
    mvs_xyz = read_xyz_bin(Path(resolved["mvs"]["path"]))
    als_xyz = read_xyz_bin(Path(resolved["existing_als"]["path"]))
    if len(mvs_xyz) != resolved["mvs"]["point_count"] or len(als_xyz) != resolved["existing_als"]["point_count"]:
        raise RuntimeError("partition point count drift")
    cores = load_cores(Path(resolved["relation_map"]["path"]), cfg["domain"])
    up = np.asarray(resolved["gravity"]["up"], dtype=np.float64)
    profiles = cfg["algorithm"]["profiles"]
    selected = cfg["algorithm"]["selected_profile"]
    sensitivity = {}
    result = None
    for name in sorted(profiles):
        t0 = time.perf_counter()
        built = build_region_units(mvs_xyz, als_xyz, cfg["domain"], profiles[name], up,
                                   uid_namespace(resolved, cfg["domain"], profiles[name], name), cores)
        sensitivity[name] = {"elapsed_seconds": time.perf_counter() - t0, "unit_count": int(len(built["units"])),
                             "accounting": built["accounting"]}
        if name == selected:
            result = built
    assert result is not None
    outputs = {
        "cells.npy": result["cells"], "units.npy": result["units"], "unit_adjacency.npy": result["adjacency"],
        "unit_cores.npy": result["core_map"],
        "point_rows_mvs.npy": result["point_rows_mvs"], "point_rows_als.npy": result["point_rows_als"],
        "point_cell_mvs.npy": result["point_cell_mvs"], "point_cell_als.npy": result["point_cell_als"],
    }
    for name, array in outputs.items():
        atomic_npy(out / name, array)
    atomic_json(out / "unit_prior_composition.json", {"schema": "jointbuildgs.phd.region_unit.prior_composition.v1",
                                                     "unit_to_als_segment_cell_counts": result["composition"]})
    write_units_csv(out / "units.csv.gz", result["units"])
    write_unit_ply(out / "region_unit_map.ply", result["cells"], result["units"])
    write_preview(out / "region_unit_preview.png", result["cells"], result["units"], cfg["domain"])
    atomic_json(out / "profile_sensitivity.json", {"schema": "jointbuildgs.phd.region_unit.profile_sensitivity.v1",
                                                  "selected_profile": selected, "profiles": sensitivity,
                                                  "note": "fine/coarse are parameter-sensitivity diagnostics; no profile is chosen by a score-only reference"})
    cell_sweep = cfg["algorithm"].get("cell_size_sensitivity", [])
    if cell_sweep:
        sensitivity_v = cell_size_sensitivity(mvs_xyz, als_xyz, cfg["domain"], profiles[selected], up, cell_sweep, selected)
        atomic_json(out / "cell_size_sensitivity.json", {"schema": "jointbuildgs.phd.region_unit.cell_size_sensitivity.v1",
                                                        "selected_profile": selected, **sensitivity_v})
    technical = {
        "schema": "jointbuildgs.phd.region_unit.technical_return.v1",
        "task_id": cfg["task_id"], "status": "COMPLETE_DEVELOPMENT_NON_CONFIRMATORY",
        "generated_utc": utc_now(), "git_commit": git_head(),
        "config": {"path": str(config_path), "sha256": sha256(config_path)},
        "driver": {"path": str(Path(__file__)), "sha256": sha256(Path(__file__))},
        "environment": {"numpy": np.__version__, "scipy": scipy.__version__},
        "design_reference": cfg["design_reference"],
        "domain": cfg["domain"], "frame": cfg["frame"], "selected_profile": selected,
        "profile": profiles[selected],
        "gravity": {"sha256": resolved["gravity"]["sha256"], "up": resolved["gravity"]["up"], "use": resolved["gravity"]["use"]},
        "accounting": result["accounting"],
        "unit_count": int(len(result["units"])), "cell_count": int(len(result["cells"])),
        "unit_set_sha256": result["unit_set_sha256"],
        "source_names": SOURCE_NAMES, "kind_names": KIND_NAMES, "role_names": ROLE_NAMES,
        "pair_rule_names": PAIR_RULE_NAMES, "split_reason_names": SPLIT_REASON_NAMES, "core_rule_names": CORE_RULE_NAMES,
        "not_decided_here": cfg["not_decided_here"],
        "interpretation": {
            "units_are_defined_on_frozen_source_data_only": True,
            "relation_map_used_only_as_post_hoc_index": True,
            "gaussians_render_residuals_or_learned_colors_used": False,
            "registration_delta_estimated": False,
            "source_authority_decided": False,
            "temporal_change_decided": False,
        },
        "elapsed_seconds": time.perf_counter() - started,
        "prohibited_inputs_accessed": [], "scientific_verdict": None,
    }
    atomic_json(out / "technical_return.json", technical)
    manifest_outputs = {}
    for name in sorted(list(outputs) + ["unit_prior_composition.json", "units.csv.gz", "region_unit_map.ply",
                                        "region_unit_preview.png", "profile_sensitivity.json", "technical_return.json",
                                        "resolved_input_manifest.json"] + (["cell_size_sensitivity.json"] if cell_sweep else [])):
        path = out / name
        manifest_outputs[name] = {"path": name, "bytes": path.stat().st_size, "sha256": sha256(path)}
    manifest = {
        "schema": "jointbuildgs.phd.region_unit.artifact_manifest.v1",
        "task_id": cfg["task_id"], "status": "COMPLETE_DEVELOPMENT_NON_CONFIRMATORY",
        "generated_utc": utc_now(), "git_commit": technical["git_commit"],
        "config": technical["config"], "driver": technical["driver"],
        "inputs": resolved, "outputs": manifest_outputs,
        "unit_count": technical["unit_count"], "cell_count": technical["cell_count"],
        "unit_set_sha256": technical["unit_set_sha256"],
        "prohibited_inputs_accessed": [], "scientific_verdict": None,
    }
    atomic_json(out / "artifact_manifest.json", manifest)
    return technical


def validate(cfg: dict[str, Any], rerun: bool = True) -> dict[str, Any]:
    root = Path(cfg["artifact_root"])
    out = root / cfg["output_relative_root"]
    manifest = json.loads((out / "artifact_manifest.json").read_text(encoding="utf-8"))
    checks: dict[str, str] = {}
    for name, item in manifest["outputs"].items():
        path = out / name
        if path.stat().st_size != int(item["bytes"]) or sha256(path) != item["sha256"]:
            raise AssertionError(f"output hash drift: {name}")
    checks["output_hashes"] = "PASS"
    resolved = resolve_inputs(cfg)
    checks["input_hashes_and_gravity_not_hardcoded"] = "PASS"
    cells = np.load(out / "cells.npy", allow_pickle=False)
    units = np.load(out / "units.npy", allow_pickle=False)
    adjacency = np.load(out / "unit_adjacency.npy", allow_pickle=False)
    core_map = np.load(out / "unit_cores.npy", allow_pickle=False)
    profile = cfg["algorithm"]["profiles"][cfg["algorithm"]["selected_profile"]]
    if np.any(cells["unit_id"] == 0) or np.any(cells["unit_id"] > len(units)):
        raise AssertionError("coverage: a cell has no unit")
    if not np.array_equal(units["unit_id"], np.arange(1, len(units) + 1)):
        raise AssertionError("unit ids are not contiguous")
    if len(set(map(bytes, units["unit_uid"]))) != len(units):
        raise AssertionError("unit uids are not unique")
    if np.any(np.bincount(cells["unit_id"], minlength=len(units) + 1)[1:] == 0):
        raise AssertionError("a unit has no member cell")
    checks["criterion_2_complete_coverage"] = "PASS"
    if np.any(units["component_count"] != 1):
        raise AssertionError("criterion 1: a unit is not connected")
    checks["criterion_1_connected_units"] = "PASS"
    area = units["area_m2"].astype(np.float64)
    if np.any((area < float(profile["minimum_unit_area_m2"])) & (units["small"] != 1)):
        raise AssertionError("criterion 3: an unflagged unit is below the minimum area")
    extents = np.nan_to_num(np.column_stack((units["extent_e1_m"], units["extent_e2_m"])).astype(np.float64), nan=0.0)
    if np.any(np.max(extents, axis=1) > 2.0 * float(profile["maximum_unit_extent_m"]) + 1e-6):
        raise AssertionError("criterion 3: a unit exceeds twice the extent cap")
    checks["criterion_3_scale_flags_and_extent_cap"] = "PASS"
    mvs_units = units[units["primary_source"] == SOURCE_MVS]
    planar_units = mvs_units[mvs_units["kind"] == KIND_PLANAR]
    spread = planar_units["prior_offset_spread_m"].astype(np.float64)
    layered = np.isfinite(spread) & (spread > float(profile["prior_layer_split_offset_m"]))
    if np.any(layered & (planar_units["split_reason"] != SPLIT_PRIOR_LAYER) & (planar_units["mixed_prior"] != 1)):
        raise AssertionError("criterion 3b: a layered prior side is neither split nor flagged")
    deviation = units["normal_vs_parent_deg"].astype(np.float64)
    if np.any(np.nan_to_num(deviation, nan=0.0) > float(profile["grow_max_normal_angle_deg"]) + 1e-6):
        raise AssertionError("D-1b guard: a unit frame deviates from its parent segment normal by more than theta_max")
    checks["d1b_unit_frames_within_theta_of_parent"] = "PASS"
    checks["criterion_3b_prior_layer_split_or_flagged"] = "PASS"
    for name, rows in (("mvs", "point_rows_mvs.npy"), ("als", "point_rows_als.npy")):
        point_rows = np.load(out / rows, allow_pickle=False)
        point_cell = np.load(out / f"point_cell_{name}.npy", allow_pickle=False)
        if len(point_rows) != len(point_cell) or np.any(point_cell >= len(cells)):
            raise AssertionError(f"point lineage drift: {name}")
        expected = SOURCE_MVS if name == "mvs" else SOURCE_ALS
        if np.any(cells["source"][point_cell] != expected):
            raise AssertionError(f"point lineage source drift: {name}")
    checks["criterion_6_point_cell_unit_lineage"] = "PASS"
    if len(adjacency) and (np.any(adjacency["unit_a"] >= adjacency["unit_b"]) or np.any(adjacency["unit_b"] > len(units))):
        raise AssertionError("adjacency integrity drift")
    if len(adjacency) and np.any(adjacency["contact_mvs_mvs"] + adjacency["contact_als_als"] + adjacency["contact_cross"] != adjacency["contact_pairs"]):
        raise AssertionError("adjacency contact breakdown does not sum to contact_pairs")
    checks["adjacency_integrity"] = "PASS"
    if np.any(core_map["unit_id"] == 0):
        raise AssertionError("D-1j: a relation core inside the domain has no unit")
    if np.any(cells["source"][core_map["cell_index"]] != core_map["core_source"]):
        raise AssertionError("D-1j: a core was mapped to a cell of the other source")
    checks["criterion_6_relation_core_lineage"] = "PASS"
    resolver = UnitResolver(cells, units, float(profile["resolver_radius_m"]))
    xyz = np.column_stack((cells["x"], cells["y"], cells["z"]))
    resolved_ids, _ = resolver.resolve(xyz)
    if np.any(resolved_ids != cells["unit_id"]):
        raise AssertionError("resolver does not map every cell to its own unit")
    if resolver.resolve(np.array([[1e6, 1e6, 1e6]]))[0][0] != 0:
        raise AssertionError("resolver must return 0 outside the domain")
    checks["resolver_all_cells_self_and_unresolved"] = "PASS"
    technical = json.loads((out / "technical_return.json").read_text(encoding="utf-8"))
    if technical.get("scientific_verdict", "missing") is not None or technical.get("prohibited_inputs_accessed") != []:
        raise AssertionError("technical return contract drift")
    if technical["interpretation"]["registration_delta_estimated"] or technical["interpretation"]["source_authority_decided"]:
        raise AssertionError("T0 must not decide delta or authority")
    checks["scope_contract"] = "PASS"
    if rerun:
        mvs_xyz = read_xyz_bin(Path(resolved["mvs"]["path"]))
        als_xyz = read_xyz_bin(Path(resolved["existing_als"]["path"]))
        cores = load_cores(Path(resolved["relation_map"]["path"]), cfg["domain"])
        name = cfg["algorithm"]["selected_profile"]
        rebuilt = build_region_units(mvs_xyz, als_xyz, cfg["domain"], profile, np.asarray(resolved["gravity"]["up"]),
                                     uid_namespace(resolved, cfg["domain"], profile, name), cores)
        for file_name, array in (("cells.npy", rebuilt["cells"]), ("units.npy", rebuilt["units"]),
                                 ("unit_adjacency.npy", rebuilt["adjacency"]), ("unit_cores.npy", rebuilt["core_map"])):
            if array_digest(array) != array_digest(np.load(out / file_name, allow_pickle=False)):
                raise AssertionError(f"determinism drift on rerun: {file_name}")
        checks["criterion_6_determinism_rerun"] = "PASS"
    checks["prohibited_inputs"] = "PASS"
    checks["scientific_verdict_null"] = "PASS"
    receipt = {
        "schema": "jointbuildgs.phd.region_unit.validation.v1", "task_id": cfg["task_id"],
        "generated_utc": utc_now(), "checks": checks,
        "artifact_manifest_sha256": sha256(out / "artifact_manifest.json"),
        "unit_set_sha256": manifest["unit_set_sha256"],
        "unit_count": int(len(units)), "cell_count": int(len(cells)),
        "prohibited_inputs_accessed": [], "scientific_verdict": None,
    }
    atomic_json(out / "validation_receipt.json", receipt)
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--no-rerun", action="store_true", help="skip the determinism rerun inside validate")
    parser.add_argument("command", choices=("run", "validate", "run-and-validate"))
    args = parser.parse_args()
    config_path = args.config.resolve()
    cfg = load_config(config_path)
    if args.command in {"run", "run-and-validate"}:
        technical = run(cfg, config_path)
        print(json.dumps({"unit_count": technical["unit_count"], "cell_count": technical["cell_count"],
                          "elapsed_seconds": technical["elapsed_seconds"], "accounting": technical["accounting"]}, indent=2))
    if args.command in {"validate", "run-and-validate"}:
        print(json.dumps(validate(cfg, rerun=not args.no_rerun), indent=2))


if __name__ == "__main__":
    main()
