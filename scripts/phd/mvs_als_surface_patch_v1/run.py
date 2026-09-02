#!/usr/bin/env python3
"""Build deterministic connected surface patches from frozen relation cores.

M3C2 is not recomputed here.  The frozen five-class relation map is treated as
per-core evidence.  Geometry-only, source-separated surface connectivity first
creates bounded over-segments; relation evidence is then aggregated per patch.
Small or mixed patches become NOT_COMPARABLE rather than being force-merged.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
from typing import Any, Iterable, Mapping

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree

from scripts.phd.mvs_als_source_relation_v1 import run as relation


REPO = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = REPO / "configs/phd/mvs_als_surface_patch_v1/run_v1.json"

PATCH_STATUS = {
    0: "UNASSIGNED_BRIDGE_INELIGIBLE",
    1: "STABLE_DOMINANT_RELATION",
    2: "SMALL_CONNECTED_ISLAND",
    3: "MIXED_RELATION_AMBIGUOUS",
    4: "DOMINANT_NOT_COMPARABLE",
}

UNASSIGNED_REASON = {
    0: "ASSIGNED_OR_NOT_APPLICABLE",
    1: "INVALID_NORMAL",
    2: "CLASS_5_NOT_COMPARABLE_EXCLUDED_FROM_BRIDGING",
    3: "HIGH_OR_NONFINITE_SURFACE_VARIATION",
}

MEMBERSHIP_DTYPE = np.dtype([
    ("core_index", "<u4"),
    ("patch_id", "<u4"),
    ("raw_relation_class", "u1"),
    ("patch_relation_class", "u1"),
    ("core_source", "u1"),
    ("patch_status", "u1"),
    ("unassigned_reason", "u1"),
    ("patch_core_count", "<u4"),
    ("patch_purity", "<f4"),
    ("patch_radius_m", "<f4"),
])

SUMMARY_DTYPE = np.dtype([
    ("patch_id", "<u4"),
    ("patch_uid", "S20"),
    ("core_source", "u1"),
    ("patch_relation_class", "u1"),
    ("patch_status", "u1"),
    ("dominant_raw_class", "u1"),
    ("core_count", "<u4"),
    ("cx", "<f4"), ("cy", "<f4"), ("cz", "<f4"),
    ("nx", "<f4"), ("ny", "<f4"), ("nz", "<f4"),
    ("radius_m", "<f4"), ("bbox_diagonal_m", "<f4"),
    ("plane_rmse_m", "<f4"), ("plane_p95_abs_residual_m", "<f4"),
    ("plane_max_abs_residual_m", "<f4"),
    ("normal_p95_deg", "<f4"), ("normal_max_deg", "<f4"),
    ("support_area_proxy_m2", "<f4"),
    ("relation_purity", "<f4"), ("robust_fraction", "<f4"),
    ("median_surface_variation", "<f4"),
    ("count_class_1", "<u4"), ("count_class_2", "<u4"),
    ("count_class_3", "<u4"), ("count_class_4", "<u4"),
    ("count_class_5", "<u4"),
])


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path, chunk_bytes: int = 8 << 20) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(chunk_bytes), b""):
            value.update(block)
    return value.hexdigest()


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


def load_config(path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    cfg = json.loads(path.read_text(encoding="utf-8"))
    if cfg.get("schema") != "jointbuildgs.phd.mvs_als_surface_patch.run.v1":
        raise ValueError("surface-patch config schema drift")
    if cfg.get("status") != "USER_APPROVED_DEVELOPMENT_NON_CONFIRMATORY":
        raise ValueError("surface-patch execution is not user-approved")
    if cfg.get("scientific_verdict", "missing") is not None:
        raise ValueError("scientific_verdict must remain null")
    if cfg["algorithm"].get("separate_core_source_surfaces") is not True:
        raise ValueError("MVS and ALS source surfaces must remain separate")
    if cfg["algorithm"].get("global_single_component_required") is not False:
        raise ValueError("global connectivity must not be required")
    serialized = json.dumps({"inputs": cfg["expected_inputs"], "root": cfg["input_relative_root"]}).lower()
    for token in ("uas", "lod2", "footprint", "stable_id", "journal1"):
        if token in serialized:
            raise ValueError(f"prohibited input token: {token}")
    return cfg


def verify_inputs(cfg: Mapping[str, Any]) -> tuple[Path, dict[str, Any]]:
    root = Path(str(cfg["artifact_root"])) / str(cfg["input_relative_root"])
    result: dict[str, Any] = {}
    for name, expected in cfg["expected_inputs"].items():
        path = root / name
        if not path.is_file() or path.is_symlink():
            raise FileNotFoundError(path)
        actual = sha256(path)
        if actual != expected:
            raise RuntimeError(f"input hash drift: {name}: {actual} != {expected}")
        result[name] = {"bytes": path.stat().st_size, "sha256": actual}
    return root, result


def normalized_normals(rows: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    normals = np.column_stack((rows["nx"], rows["ny"], rows["nz"])).astype(np.float64)
    lengths = np.linalg.norm(normals, axis=1)
    valid = np.all(np.isfinite(normals), axis=1) & np.isfinite(lengths) & (lengths > 1e-8)
    normals[valid] /= lengths[valid, None]
    normals[~valid] = np.nan
    return normals, valid


def bridge_eligibility(
    rows: np.ndarray, valid_normal: np.ndarray, profile: Mapping[str, Any],
) -> tuple[np.ndarray, np.ndarray]:
    """Select bridge cores without deleting any frozen relation-map row."""
    relation_class = rows["relation_class"].astype(np.uint8)
    variation = rows["surface_variation"].astype(np.float64)
    finite_low_variation = np.isfinite(variation) & (
        variation <= float(profile["maximum_bridge_surface_variation"])
    )
    eligible = valid_normal & (relation_class != 5) & finite_low_variation
    reason = np.zeros(len(rows), dtype=np.uint8)
    reason[~valid_normal] = 1
    reason[valid_normal & (relation_class == 5)] = 2
    reason[valid_normal & (relation_class != 5) & ~finite_low_variation] = 3
    return eligible, reason


def accepted_surface_edges(
    xyz: np.ndarray,
    normals: np.ndarray,
    valid: np.ndarray,
    source: np.ndarray,
    profile: Mapping[str, Any],
) -> np.ndarray:
    """Return global-index edges satisfying local source-surface continuity."""
    edge_parts: list[np.ndarray] = []
    radius = float(profile["neighbor_radius_m"])
    cosine = float(np.cos(np.deg2rad(float(profile["maximum_normal_angle_deg"]))))
    plane_limit = float(profile["maximum_symmetric_point_to_plane_m"])
    for source_id in (0, 1):
        global_ids = np.flatnonzero((source == source_id) & valid)
        if len(global_ids) < 2:
            continue
        points = xyz[global_ids]
        pairs = cKDTree(points).query_pairs(radius, output_type="ndarray")
        if len(pairs) == 0:
            continue
        gi = global_ids[pairs[:, 0]]
        gj = global_ids[pairs[:, 1]]
        delta = xyz[gj] - xyz[gi]
        dot = np.abs(np.einsum("ij,ij->i", normals[gi], normals[gj]))
        plane_i = np.abs(np.einsum("ij,ij->i", delta, normals[gi]))
        plane_j = np.abs(np.einsum("ij,ij->i", delta, normals[gj]))
        keep = (dot >= cosine) & (np.maximum(plane_i, plane_j) <= plane_limit)
        if np.any(keep):
            edge_parts.append(np.column_stack((gi[keep], gj[keep])).astype(np.uint32))
    if not edge_parts:
        return np.empty((0, 2), dtype=np.uint32)
    return np.concatenate(edge_parts)


def _find(parent: np.ndarray, value: int) -> int:
    while int(parent[value]) != value:
        parent[value] = parent[int(parent[value])]
        value = int(parent[value])
    return value


def _global_plane_guard(
    member_ids: list[int], xyz: np.ndarray, normals: np.ndarray, profile: Mapping[str, Any],
) -> tuple[bool, str]:
    points = xyz[member_ids]
    center = points.mean(axis=0)
    if float(np.max(np.linalg.norm(points - center, axis=1))) > float(profile["maximum_patch_radius_m"]):
        return False, "global_radius"
    if len(member_ids) < int(profile["minimum_plane_fit_cores"]):
        return True, "small_pre_fit"
    centered = points - center
    covariance = centered.T @ centered / len(points)
    eigenvalues, eigenvectors = np.linalg.eigh(covariance)
    if not np.all(np.isfinite(eigenvalues)) or eigenvalues[1] <= 1e-10:
        return False, "global_rank"
    plane_normal = eigenvectors[:, 0]
    residual = np.abs(centered @ plane_normal)
    rmse = float(np.sqrt(np.mean(residual * residual)))
    if rmse > float(profile["patch_plane_rmse_m"]):
        return False, "global_rmse"
    if float(np.max(residual)) > float(profile["patch_max_abs_residual_m"]):
        return False, "global_max_residual"
    angles = np.degrees(np.arccos(np.clip(np.abs(normals[member_ids] @ plane_normal), 0.0, 1.0)))
    if float(np.max(angles)) > float(profile["patch_max_local_normal_deg"]):
        return False, "global_normal"
    return True, "pass"


def guarded_kruskal_patches(
    xyz: np.ndarray,
    source: np.ndarray,
    valid: np.ndarray,
    edges: np.ndarray,
    normals: np.ndarray,
    profile: Mapping[str, Any],
) -> tuple[np.ndarray, dict[str, int]]:
    """Deterministic edge-ordered unions with whole-patch anti-chaining guards."""
    assignment = np.zeros(len(xyz), dtype=np.uint32)
    maximum_cores = int(profile["maximum_patch_cores"])
    parent = np.arange(len(xyz), dtype=np.int64)
    valid_ids = np.flatnonzero(valid)
    members: dict[int, list[int]] = {int(value): [int(value)] for value in valid_ids}
    diagnostics: Counter[str] = Counter()
    point_order = np.lexsort((
        normals[:, 2], normals[:, 1], normals[:, 0],
        xyz[:, 2], xyz[:, 1], xyz[:, 0], source,
    ))
    canonical_rank = np.empty(len(xyz), dtype=np.int64)
    canonical_rank[point_order] = np.arange(len(xyz), dtype=np.int64)
    if len(edges):
        left, right = edges[:, 0].astype(np.int64), edges[:, 1].astype(np.int64)
        delta = xyz[right] - xyz[left]
        distance = np.linalg.norm(delta, axis=1)
        normal_angle = np.degrees(np.arccos(np.clip(np.abs(np.einsum("ij,ij->i", normals[left], normals[right])), 0.0, 1.0)))
        plane_gap = np.maximum(
            np.abs(np.einsum("ij,ij->i", delta, normals[left])),
            np.abs(np.einsum("ij,ij->i", delta, normals[right])),
        )
        score = np.maximum.reduce((
            distance / float(profile["neighbor_radius_m"]),
            normal_angle / float(profile["maximum_normal_angle_deg"]),
            plane_gap / float(profile["maximum_symmetric_point_to_plane_m"]),
        ))
        edge_lo = np.minimum(canonical_rank[left], canonical_rank[right])
        edge_hi = np.maximum(canonical_rank[left], canonical_rank[right])
        order = np.lexsort((edge_hi, edge_lo, plane_gap, normal_angle, distance, np.round(score, 12)))
        for edge_index in order:
            a = _find(parent, int(left[edge_index]))
            b = _find(parent, int(right[edge_index]))
            if a == b:
                diagnostics["already_connected"] += 1
                continue
            combined = sorted(members[a] + members[b], key=lambda value: int(canonical_rank[value]))
            if len(combined) > maximum_cores:
                diagnostics["maximum_patch_cores"] += 1
                continue
            passes, reason = _global_plane_guard(combined, xyz, normals, profile)
            if not passes:
                diagnostics[reason] += 1
                continue
            if canonical_rank[members[a][0]] <= canonical_rank[members[b][0]]:
                root, other = a, b
            else:
                root, other = b, a
            parent[other] = root
            members[root] = combined
            del members[other]
            diagnostics["accepted_union"] += 1
    ordered_components = sorted(members.values(), key=lambda values: int(canonical_rank[values[0]]))
    for patch_id, component in enumerate(ordered_components, start=1):
        assignment[component] = patch_id
    diagnostics["final_patch_count"] = len(ordered_components)
    diagnostics["bridge_ineligible_cores"] = int(np.count_nonzero(~valid))
    return assignment, dict(diagnostics)


def _mean_normal(normals: np.ndarray) -> np.ndarray:
    if not len(normals):
        return np.full(3, np.nan, dtype=np.float64)
    aligned = normals.copy()
    reference = aligned[0]
    aligned[(aligned @ reference) < 0] *= -1
    value = aligned.mean(axis=0)
    length = np.linalg.norm(value)
    return value / length if length > 1e-8 else reference


def _patch_geometry_statistics(
    points: np.ndarray, local_normals: np.ndarray,
) -> tuple[np.ndarray, float, float, float, float, float]:
    center = points.mean(axis=0)
    normal = _mean_normal(local_normals)
    if len(points) >= 3:
        centered = points - center
        eigenvalues, eigenvectors = np.linalg.eigh(centered.T @ centered / len(points))
        if np.all(np.isfinite(eigenvalues)) and eigenvalues[1] > 1e-10:
            normal = eigenvectors[:, 0]
    residual = np.abs((points - center) @ normal)
    angles = np.degrees(np.arccos(np.clip(np.abs(local_normals @ normal), 0.0, 1.0)))
    return (
        normal,
        float(np.sqrt(np.mean(residual * residual))),
        float(np.quantile(residual, 0.95)),
        float(np.max(residual)),
        float(np.quantile(angles, 0.95)),
        float(np.max(angles)),
    )


def _patch_uid(
    ids: np.ndarray, xyz: np.ndarray, normals: np.ndarray, source: np.ndarray,
    profile: Mapping[str, Any],
) -> bytes:
    order = np.lexsort((
        normals[ids, 2], normals[ids, 1], normals[ids, 0],
        xyz[ids, 2], xyz[ids, 1], xyz[ids, 0], source[ids],
    ))
    ordered = ids[order]
    canonical = np.empty(len(ordered), dtype=np.dtype([
        ("source", "u1"),
        ("x", "<f4"), ("y", "<f4"), ("z", "<f4"),
        ("nx", "<f4"), ("ny", "<f4"), ("nz", "<f4"),
    ]))
    canonical["source"] = source[ordered]
    canonical["x"], canonical["y"], canonical["z"] = xyz[ordered].T
    canonical["nx"], canonical["ny"], canonical["nz"] = normals[ordered].T
    digest = hashlib.sha256()
    digest.update(b"jointbuildgs.surface_patch_uid.v1\0")
    digest.update(json.dumps(dict(profile), sort_keys=True, separators=(",", ":")).encode("utf-8"))
    digest.update(canonical.tobytes())
    return digest.hexdigest()[:20].encode("ascii")


def summarize_patches(
    rows: np.ndarray,
    xyz: np.ndarray,
    normals: np.ndarray,
    assignment: np.ndarray,
    profile: Mapping[str, Any],
    core_spacing_m: float,
    unassigned_reason: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    membership = np.zeros(len(rows), dtype=MEMBERSHIP_DTYPE)
    membership["core_index"] = np.arange(len(rows), dtype=np.uint32)
    membership["patch_id"] = assignment
    membership["raw_relation_class"] = rows["relation_class"]
    membership["patch_relation_class"] = 5
    membership["core_source"] = rows["core_source"]
    if unassigned_reason is None:
        unassigned_reason = np.where(assignment == 0, 1, 0).astype(np.uint8)
    membership["unassigned_reason"] = unassigned_reason
    minimum = int(profile["minimum_patch_cores"])
    purity_min = float(profile["minimum_dominant_relation_fraction"])
    summaries: list[np.void] = []
    for patch_id in np.unique(assignment[assignment > 0]):
        ids = np.flatnonzero(assignment == patch_id)
        labels = rows["relation_class"][ids].astype(np.int64)
        counts = np.bincount(labels, minlength=6)[1:6]
        dominant = int(np.flatnonzero(counts == counts.max())[0] + 1)
        purity = float(counts[dominant - 1] / len(ids))
        candidate_counts = counts[1:4]
        candidate_class = int(np.argmax(candidate_counts) + 2)
        candidate_fraction = float(candidate_counts.max() / len(ids))
        has_candidate = bool(candidate_counts.sum() > 0)
        if len(ids) < minimum:
            status, patch_label = 2, 5
        elif has_candidate and candidate_fraction >= purity_min:
            status, patch_label = 1, candidate_class
        elif has_candidate:
            status, patch_label = 3, 5
        elif dominant == 1:
            status, patch_label = 1, 1
        else:
            status, patch_label = 4, 5
        center = xyz[ids].mean(axis=0)
        radius = float(np.max(np.linalg.norm(xyz[ids] - center, axis=1)))
        diagonal = float(np.linalg.norm(xyz[ids].max(axis=0) - xyz[ids].min(axis=0)))
        normal, plane_rmse, plane_p95, plane_max, normal_p95, normal_max = _patch_geometry_statistics(
            xyz[ids], normals[ids],
        )
        record = np.zeros((), dtype=SUMMARY_DTYPE)
        record["patch_id"] = patch_id
        record["patch_uid"] = _patch_uid(
            ids, xyz, normals, rows["core_source"].astype(np.uint8), profile,
        )
        record["core_source"] = rows["core_source"][ids[0]]
        record["patch_relation_class"] = patch_label
        record["patch_status"] = status
        record["dominant_raw_class"] = dominant
        record["core_count"] = len(ids)
        record["cx"], record["cy"], record["cz"] = center
        record["nx"], record["ny"], record["nz"] = normal
        record["radius_m"] = radius
        record["bbox_diagonal_m"] = diagonal
        record["plane_rmse_m"] = plane_rmse
        record["plane_p95_abs_residual_m"] = plane_p95
        record["plane_max_abs_residual_m"] = plane_max
        record["normal_p95_deg"] = normal_p95
        record["normal_max_deg"] = normal_max
        record["support_area_proxy_m2"] = len(ids) * core_spacing_m * core_spacing_m
        record["relation_purity"] = purity
        record["robust_fraction"] = float(np.mean(rows["robust_significant"][ids]))
        record["median_surface_variation"] = float(np.nanmedian(rows["surface_variation"][ids]))
        for class_id in range(1, 6):
            record[f"count_class_{class_id}"] = counts[class_id - 1]
        summaries.append(record)
        membership["patch_relation_class"][ids] = patch_label
        membership["patch_status"][ids] = status
        membership["patch_core_count"][ids] = len(ids)
        membership["patch_purity"][ids] = purity
        membership["patch_radius_m"][ids] = radius
        membership["unassigned_reason"][ids] = 0
    invalid = assignment == 0
    membership["patch_status"][invalid] = 0
    return membership, np.asarray(summaries, dtype=SUMMARY_DTYPE)


def patch_adjacency(edges: np.ndarray, assignment: np.ndarray) -> np.ndarray:
    if len(edges) == 0:
        return np.empty((0, 2), dtype=np.uint32)
    left = assignment[edges[:, 0]]
    right = assignment[edges[:, 1]]
    keep = (left > 0) & (right > 0) & (left != right)
    if not np.any(keep):
        return np.empty((0, 2), dtype=np.uint32)
    pairs = np.sort(np.column_stack((left[keep], right[keep])), axis=1)
    return np.unique(pairs, axis=0).astype(np.uint32)


def quantiles(values: np.ndarray) -> dict[str, float | None]:
    if len(values) == 0:
        return {key: None for key in ("min", "p10", "median", "p90", "p99", "max")}
    result = np.quantile(values.astype(np.float64), [0, 0.1, 0.5, 0.9, 0.99, 1.0])
    return {key: float(value) for key, value in zip(("min", "p10", "median", "p90", "p99", "max"), result)}


def raw_component_metrics(rows: np.ndarray, edges: np.ndarray) -> dict[str, Any]:
    if len(rows) == 0:
        return {}
    same = edges[rows["relation_class"][edges[:, 0]] == rows["relation_class"][edges[:, 1]]]
    if len(same):
        rr = np.concatenate((same[:, 0], same[:, 1])).astype(np.int64)
        cc = np.concatenate((same[:, 1], same[:, 0])).astype(np.int64)
        graph = coo_matrix((np.ones(len(rr), dtype=np.uint8), (rr, cc)), shape=(len(rows), len(rows))).tocsr()
        _count, labels = connected_components(graph, directed=False, return_labels=True)
    else:
        labels = np.arange(len(rows), dtype=np.int64)
    result: dict[str, Any] = {}
    for class_id in range(1, 6):
        ids = np.flatnonzero(rows["relation_class"] == class_id)
        component_sizes = np.unique(labels[ids], return_counts=True)[1] if len(ids) else np.empty(0, dtype=np.int64)
        result[str(class_id)] = {
            "core_count": int(len(ids)),
            "component_count": int(len(component_sizes)),
            "singleton_core_fraction": float(np.sum(component_sizes[component_sizes == 1]) / len(ids)) if len(ids) else 0.0,
            "cores_in_components_lt5_fraction": float(np.sum(component_sizes[component_sizes < 5]) / len(ids)) if len(ids) else 0.0,
            "largest_component_core_fraction": float(component_sizes.max() / len(ids)) if len(ids) else 0.0,
            "component_size": quantiles(component_sizes),
        }
    return result


def profile_metrics(
    rows: np.ndarray,
    membership: np.ndarray,
    summaries: np.ndarray,
    edges: np.ndarray,
    adjacency: np.ndarray,
    valid_normal: np.ndarray,
    bridge_eligible: np.ndarray,
) -> dict[str, Any]:
    raw_counts = Counter(int(value) for value in rows["relation_class"])
    patched_counts = Counter(int(value) for value in membership["patch_relation_class"])
    stable = membership["patch_status"] == 1
    stable_summaries = summaries[summaries["patch_status"] == 1]
    return {
        "surface_edge_count": int(len(edges)),
        "patch_adjacency_edge_count": int(len(adjacency)),
        "valid_normal_cores": int(valid_normal.sum()),
        "valid_normal_fraction": float(valid_normal.mean()),
        "bridge_eligible_cores": int(bridge_eligible.sum()),
        "bridge_eligible_fraction": float(bridge_eligible.mean()),
        "patch_count": int(len(summaries)),
        "stable_patch_count": int(np.count_nonzero(summaries["patch_status"] == 1)),
        "stable_core_fraction": float(np.mean(stable)),
        "small_island_core_fraction": float(np.mean(membership["patch_status"] == 2)),
        "mixed_ambiguous_core_fraction": float(np.mean(membership["patch_status"] == 3)),
        "unassigned_core_fraction": float(np.mean(membership["patch_status"] == 0)),
        "unassigned_reason_counts": {
            str(reason): int(np.count_nonzero(membership["unassigned_reason"] == reason))
            for reason in range(1, 4)
        },
        "raw_to_patch_label_change_fraction": float(np.mean(membership["raw_relation_class"] != membership["patch_relation_class"])),
        "raw_class_counts": {str(key): int(raw_counts.get(key, 0)) for key in range(1, 6)},
        "patched_class_counts": {str(key): int(patched_counts.get(key, 0)) for key in range(1, 6)},
        "patch_core_count": quantiles(summaries["core_count"]),
        "patch_radius_m": quantiles(summaries["radius_m"]),
        "patch_relation_purity": quantiles(summaries["relation_purity"]),
        "patch_plane_rmse_m": quantiles(summaries["plane_rmse_m"]),
        "patch_plane_p95_abs_residual_m": quantiles(summaries["plane_p95_abs_residual_m"]),
        "patch_normal_p95_deg": quantiles(summaries["normal_p95_deg"]),
        "stable_patch_core_count": quantiles(stable_summaries["core_count"]),
        "stable_patch_radius_m": quantiles(stable_summaries["radius_m"]),
        "stable_patch_plane_rmse_m": quantiles(stable_summaries["plane_rmse_m"]),
        "stable_patch_plane_p95_abs_residual_m": quantiles(
            stable_summaries["plane_p95_abs_residual_m"]
        ),
        "stable_patch_normal_p95_deg": quantiles(stable_summaries["normal_p95_deg"]),
        "candidate_core_preservation_fraction": 1.0,
        "candidate_to_compatible_core_count": int(np.count_nonzero(
            np.isin(membership["raw_relation_class"], [2, 3, 4])
            & (membership["patch_relation_class"] == 1)
        )),
        "class_5_bridge_core_count": 0,
        "mixed_source_family_patch_count": 0,
        "raw_same_class_components": raw_component_metrics(rows, edges),
    }


def write_patch_ply(path: Path, rows: np.ndarray, membership: np.ndarray) -> None:
    dtype = np.dtype([
        ("x", "<f4"), ("y", "<f4"), ("z", "<f4"),
        ("red", "u1"), ("green", "u1"), ("blue", "u1"),
        ("raw_relation_class", "u1"), ("patch_relation_class", "u1"),
        ("core_source", "u1"), ("patch_status", "u1"), ("unassigned_reason", "u1"),
        ("patch_id", "<u4"), ("patch_core_count", "<u4"),
        ("patch_purity", "<f4"),
    ])
    output = np.empty(len(rows), dtype=dtype)
    for name in ("x", "y", "z"):
        output[name] = rows[name]
    for name in ("raw_relation_class", "patch_relation_class", "core_source", "patch_status", "unassigned_reason", "patch_id", "patch_core_count", "patch_purity"):
        output[name] = membership[name]
    rgb = relation.relation_rgb(membership["patch_relation_class"])
    output["red"], output["green"], output["blue"] = rgb.T
    header = [
        "ply", "format binary_little_endian 1.0", f"element vertex {len(output)}",
        "property float x", "property float y", "property float z",
        "property uchar red", "property uchar green", "property uchar blue",
        "property uchar raw_relation_class", "property uchar patch_relation_class",
        "property uchar core_source", "property uchar patch_status", "property uchar unassigned_reason",
        "property uint patch_id", "property uint patch_core_count", "property float patch_purity", "end_header",
    ]
    atomic_bytes(path, ("\n".join(header) + "\n").encode("ascii") + output.tobytes())


def write_summary_csv(path: Path, summaries: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with gzip.open(temporary, "wt", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(summaries.dtype.names)
        for row in summaries:
            values = []
            for name in summaries.dtype.names:
                value = row[name].item()
                values.append(value.decode("ascii") if isinstance(value, bytes) else value)
            writer.writerow(values)
    os.replace(temporary, path)


def _patch_id_rgb(patch_ids: np.ndarray) -> np.ndarray:
    values = patch_ids.astype(np.uint64)
    red = ((values * np.uint64(73) + 37) % 251).astype(np.float64) / 250.0
    green = ((values * np.uint64(151) + 83) % 251).astype(np.float64) / 250.0
    blue = ((values * np.uint64(199) + 131) % 251).astype(np.float64) / 250.0
    rgb = np.column_stack((red, green, blue))
    rgb[patch_ids == 0] = [0.55, 0.55, 0.55]
    return rgb


def write_preview(path: Path, rows: np.ndarray, membership: np.ndarray) -> None:
    maximum = 120_000
    ids = np.arange(len(rows)) if len(rows) <= maximum else np.linspace(0, len(rows) - 1, maximum, dtype=np.int64)
    x, y = rows["x"][ids], rows["y"][ids]
    raw_rgb = relation.relation_rgb(rows["relation_class"][ids]).astype(np.float64) / 255.0
    patched_rgb = relation.relation_rgb(membership["patch_relation_class"][ids]).astype(np.float64) / 255.0
    patch_rgb = _patch_id_rgb(membership["patch_id"][ids])
    fig, axes = plt.subplots(1, 3, figsize=(18, 6), dpi=150, constrained_layout=True)
    panels = [
        (raw_rgb, "before: frozen per-core relation"),
        (patched_rgb, "after: patch-aggregated relation"),
        (patch_rgb, "connected source-surface patch ID"),
    ]
    for axis, (colors, title) in zip(axes, panels):
        axis.scatter(x, y, s=0.8, c=colors, linewidths=0, rasterized=True)
        axis.set_title(title)
        axis.set_aspect("equal", adjustable="box")
        axis.set_xlabel("scene-local X (m)")
        axis.set_ylabel("scene-local Y (m)")
    fig.suptitle("MVS–Existing ALS relation cores: raw versus connected surface patches\nDEVELOPMENT_NON_CONFIRMATORY · scientific_verdict=null")
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, metadata={"Software": "JointBuildGS surface-patch v1"})
    plt.close(fig)


def git_head() -> str:
    supplied = os.environ.get("JBGS_SOURCE_GIT_HEAD", "").strip()
    if supplied:
        if len(supplied) != 40 or any(value not in "0123456789abcdef" for value in supplied.lower()):
            raise RuntimeError("JBGS_SOURCE_GIT_HEAD must be a full hexadecimal commit")
        return supplied
    return subprocess.check_output(
        ["git", "-c", f"safe.directory={REPO}", "rev-parse", "HEAD"],
        cwd=REPO,
        text=True,
    ).strip()


def output_record(path: Path, root: Path) -> dict[str, Any]:
    return {"path": path.relative_to(root).as_posix(), "bytes": path.stat().st_size, "sha256": sha256(path)}


def run(cfg: dict[str, Any], config_path: Path) -> dict[str, Any]:
    started = time.perf_counter()
    input_root, inputs = verify_inputs(cfg)
    output_root = Path(cfg["artifact_root"]) / cfg["output_relative_root"]
    output_root.mkdir(parents=True, exist_ok=True)
    rows = np.load(input_root / "relation_map.npy", allow_pickle=False)
    if rows.dtype != relation.OUTPUT_DTYPE:
        raise RuntimeError("relation map dtype drift")
    xyz = np.ascontiguousarray(np.column_stack((rows["x"], rows["y"], rows["z"])), dtype=np.float64)
    normals, valid_normal = normalized_normals(rows)
    source = rows["core_source"].astype(np.uint8)
    profile_results: dict[str, Any] = {}
    selected_membership = selected_summaries = selected_edges = selected_adjacency = None
    for profile_name, profile in cfg["algorithm"]["profiles"].items():
        profile_started = time.perf_counter()
        bridge_eligible, unassigned_reason = bridge_eligibility(rows, valid_normal, profile)
        edges = accepted_surface_edges(xyz, normals, bridge_eligible, source, profile)
        assignment, merge_diagnostics = guarded_kruskal_patches(
            xyz, source, bridge_eligible, edges, normals, profile,
        )
        membership, summaries = summarize_patches(
            rows, xyz, normals, assignment, profile, float(cfg["algorithm"]["core_spacing_m"]),
            unassigned_reason,
        )
        adjacency = patch_adjacency(edges, assignment)
        profile_results[profile_name] = {
            "parameters": profile,
            "metrics": profile_metrics(
                rows, membership, summaries, edges, adjacency, valid_normal, bridge_eligible,
            ),
            "merge_diagnostics": merge_diagnostics,
            "runtime_seconds": time.perf_counter() - profile_started,
        }
        if profile_name == cfg["algorithm"]["selected_profile"]:
            selected_membership, selected_summaries = membership, summaries
            selected_edges, selected_adjacency = edges, adjacency
    if any(value is None for value in (selected_membership, selected_summaries, selected_edges, selected_adjacency)):
        raise RuntimeError("selected profile was not produced")
    membership = selected_membership
    summaries = selected_summaries
    edges = selected_edges
    adjacency = selected_adjacency
    files = {
        "patch_membership.npy": output_root / "patch_membership.npy",
        "surface_patch_summary.npy": output_root / "surface_patch_summary.npy",
        "surface_patch_adjacency.npy": output_root / "surface_patch_adjacency.npy",
        "surface_patch_map.ply": output_root / "surface_patch_map.ply",
        "surface_patch_summary.csv.gz": output_root / "surface_patch_summary.csv.gz",
        "surface_patch_before_after.png": output_root / "surface_patch_before_after.png",
    }
    atomic_npy(files["patch_membership.npy"], membership)
    atomic_npy(files["surface_patch_summary.npy"], summaries)
    atomic_npy(files["surface_patch_adjacency.npy"], adjacency)
    write_patch_ply(files["surface_patch_map.ply"], rows, membership)
    write_summary_csv(files["surface_patch_summary.csv.gz"], summaries)
    write_preview(files["surface_patch_before_after.png"], rows, membership)
    selected = profile_results[cfg["algorithm"]["selected_profile"]]["metrics"]
    technical = {
        "schema": "jointbuildgs.phd.mvs_als_surface_patch.technical_return.v1",
        "task_id": cfg["task_id"],
        "status": "COMPLETE_DEVELOPMENT_NON_CONFIRMATORY",
        "created_utc": utc_now(),
        "purpose": cfg["purpose"],
        "relation_core_count": int(len(rows)),
        "selected_profile": cfg["algorithm"]["selected_profile"],
        "selected_metrics": selected,
        "profile_sensitivity": profile_results,
        "patch_status_names": {str(key): value for key, value in PATCH_STATUS.items()},
        "unassigned_reason_names": {str(key): value for key, value in UNASSIGNED_REASON.items()},
        "interpretation": {
            "m3c2_recomputed": False,
            "source_authority_decided": False,
            "temporal_change_decided": False,
            "patches_are_source_surface_oversegments": True,
            "small_or_mixed_patches_become_not_comparable": True,
            "candidate_evidence_is_never_smoothed_to_compatible": True,
            "class_5_is_not_a_connectivity_bridge": True,
            "high_surface_variation_is_not_a_connectivity_bridge": True,
            "global_single_component_required": False,
        },
        "runtime_seconds": time.perf_counter() - started,
        "prohibited_inputs_accessed": [],
        "scientific_verdict": None,
    }
    atomic_json(output_root / "technical_return.json", technical)
    outputs = {name: output_record(path, output_root) for name, path in files.items()}
    outputs["technical_return.json"] = output_record(output_root / "technical_return.json", output_root)
    manifest = {
        "schema": "jointbuildgs.phd.mvs_als_surface_patch.artifact_manifest.v1",
        "task_id": cfg["task_id"],
        "status": "COMPLETE_DEVELOPMENT_NON_CONFIRMATORY",
        "git_head": git_head(),
        "config": {"path": str(config_path), "sha256": sha256(config_path)},
        "driver": {"path": str(Path(__file__)), "sha256": sha256(Path(__file__))},
        "inputs": inputs,
        "outputs": outputs,
        "scientific_verdict": None,
    }
    atomic_json(output_root / "artifact_manifest.json", manifest)
    return technical


def validate(cfg: dict[str, Any], config_path: Path) -> dict[str, Any]:
    input_root, _inputs = verify_inputs(cfg)
    output_root = Path(cfg["artifact_root"]) / cfg["output_relative_root"]
    manifest = json.loads((output_root / "artifact_manifest.json").read_text(encoding="utf-8"))
    technical = json.loads((output_root / "technical_return.json").read_text(encoding="utf-8"))
    rows = np.load(input_root / "relation_map.npy", allow_pickle=False)
    membership = np.load(output_root / "patch_membership.npy", allow_pickle=False)
    summaries = np.load(output_root / "surface_patch_summary.npy", allow_pickle=False)
    adjacency = np.load(output_root / "surface_patch_adjacency.npy", allow_pickle=False)
    checks: dict[str, str] = {}
    if len(membership) != len(rows) or membership.dtype != MEMBERSHIP_DTYPE:
        raise AssertionError("membership row/dtype mismatch")
    if summaries.dtype != SUMMARY_DTYPE or adjacency.ndim != 2 or adjacency.shape[1] != 2:
        raise AssertionError("summary/adjacency schema mismatch")
    if not np.array_equal(membership["core_index"], np.arange(len(rows), dtype=np.uint32)):
        raise AssertionError("core index order drift")
    if not np.array_equal(membership["raw_relation_class"], rows["relation_class"]):
        raise AssertionError("raw relation provenance drift")
    if not set(np.unique(membership["patch_relation_class"])).issubset({1, 2, 3, 4, 5}):
        raise AssertionError("unknown patched relation class")
    referenced = set(map(int, np.unique(membership["patch_id"]))) - {0}
    available = set(map(int, summaries["patch_id"]))
    if referenced != available or len(available) != len(summaries):
        raise AssertionError("patch ID referential integrity failed")
    decoded_uids = [value.decode("ascii") for value in summaries["patch_uid"]]
    if any(len(value) != 20 for value in decoded_uids) or len(decoded_uids) != len(set(decoded_uids)):
        raise AssertionError("patch UID uniqueness failed")
    if np.any((membership["patch_id"] == 0) & (membership["patch_status"] != 0)):
        raise AssertionError("unassigned patch status drift")
    if np.any((membership["patch_status"] != 1) & (membership["patch_relation_class"] != 5)):
        raise AssertionError("non-stable patches must be NOT_COMPARABLE")
    class_5 = rows["relation_class"] == 5
    class_5_reasons = membership["unassigned_reason"][class_5]
    if (
        np.any(membership["patch_id"][class_5] != 0)
        or not set(map(int, np.unique(class_5_reasons))).issubset({1, 2})
    ):
        raise AssertionError("class 5 must be preserved but excluded from bridging")
    for patch_id in available:
        ids = np.flatnonzero(membership["patch_id"] == patch_id)
        if len(np.unique(membership["core_source"][ids])) != 1:
            raise AssertionError("mixed source-family patch")
    candidate = np.isin(rows["relation_class"], [2, 3, 4])
    if np.count_nonzero(candidate) != np.count_nonzero(np.isin(membership["raw_relation_class"], [2, 3, 4])):
        raise AssertionError("candidate core preservation failed")
    if np.any(membership["patch_relation_class"][candidate] == 1):
        raise AssertionError("candidate evidence was smoothed to compatible")
    for name, item in manifest["outputs"].items():
        path = output_root / item["path"]
        if not path.is_file() or path.stat().st_size != item["bytes"] or sha256(path) != item["sha256"]:
            raise AssertionError(f"output drift: {name}")
    if technical.get("scientific_verdict", "missing") is not None or manifest.get("scientific_verdict", "missing") is not None:
        raise AssertionError("scientific_verdict must remain null")
    if technical.get("prohibited_inputs_accessed") != []:
        raise AssertionError("prohibited input access must remain empty")
    checks.update({
        "input_hashes": "PASS",
        "membership_schema_and_order": "PASS",
        "raw_relation_provenance": "PASS",
        "patch_id_referential_integrity": "PASS",
        "patch_uid_unique": "PASS",
        "class_5_bridge_zero": "PASS",
        "mixed_source_family_patch_zero": "PASS",
        "candidate_core_preservation": "PASS",
        "candidate_to_compatible_zero": "PASS",
        "ambiguous_fail_closed": "PASS",
        "output_hashes": "PASS",
        "scientific_verdict_null": "PASS",
        "prohibited_inputs": "PASS",
    })
    receipt = {
        "schema": "jointbuildgs.phd.mvs_als_surface_patch.validation.v1",
        "task_id": cfg["task_id"],
        "checks": checks,
        "relation_core_count": len(rows),
        "patch_count": len(summaries),
        "config_sha256": sha256(config_path),
        "scientific_verdict": None,
    }
    atomic_json(output_root / "validation_receipt.json", receipt)
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("command", choices=("run", "validate", "run-and-validate"))
    args = parser.parse_args()
    config_path = args.config.resolve()
    cfg = load_config(config_path)
    if args.command in {"run", "run-and-validate"}:
        print(json.dumps(run(cfg, config_path), indent=2))
    if args.command in {"validate", "run-and-validate"}:
        print(json.dumps(validate(cfg, config_path), indent=2))


if __name__ == "__main__":
    main()
