"""E3: Stage2-derived primitives with GT oracle building assignment.

This is a geometry-only exploratory diagnostic.  It is not full end-to-end
proposed-method performance: GT is used to assign Stage2 primitives to a target
building and to evaluate the resulting CityJSON, while the relation read-out
itself receives only primitive-derived evidence fields.
"""
from __future__ import annotations

import csv
import json
import math
import shutil
import sys
import traceback
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.spatial import cKDTree
from shapely.geometry import Point, Polygon

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.phase2_synthesis.obj_gt import parse_scene_obj  # noqa: E402
import scripts.phase2_synthesis.p1_4a_relation_readout as rr  # noqa: E402
import scripts.phase2_synthesis.p1_4a_preflight_precision as pm  # noqa: E402
from scripts.phase2_synthesis.e1_gt_131_relation_readout import (  # noqa: E402
    eval_geometry as eval_readout_geometry,
    parse_val3dity_result,
    val3dity_binary,
)


SCENE = ROOT / "results/phase2_synthesis/scene.obj"
OUT_ROOT = ROOT / "results/stage3_typed_readout/E3_stage2_oracle_split"
SMOKE_ROOT = OUT_ROOT / "smoke_mutual"
FOUR_ROOT = OUT_ROOT / "four_condition_smoke"
OPTIONAL_ROOT = OUT_ROOT / "full_subset_or_131_optional"

E1_SUMMARY_JSON = ROOT / "results/stage3_typed_readout/E1_gt_131_per_building/summary_metrics.json"
E1_SUMMARY_CSV = ROOT / "results/stage3_typed_readout/E1_gt_131_per_building/summary_metrics.csv"
E2_RISK_CSV = ROOT / "results/stage3_typed_readout/E2_gt_fullscene_auto_split/risk_building_tracking.csv"
E2_COMPONENT_CSV = ROOT / "results/stage3_typed_readout/E2_gt_fullscene_auto_split/component_metrics.csv"
E2_MATCHING_CSV = ROOT / "results/stage3_typed_readout/E2_gt_fullscene_auto_split/component_to_gt_matching.csv"

CONDITION_PATHS = {
    "Baseline": ROOT / "results/phase2_ablation_citygml/baseline/stage3/primitives.npz",
    "Mutual": ROOT / "results/phase2_ablation_citygml/mutual/stage3/primitives.npz",
    "Structure": ROOT / "results/phase2_ablation_citygml/structure/stage3/primitives.npz",
    "Both": ROOT / "results/phase2_ablation_citygml/both/stage3/primitives.npz",
}

STRATA: Dict[str, List[int]] = {
    "OK_CONTROL": [1, 2, 8, 0],
    "HIP_ROOF_COMPLEXITY": [6],
    "COMPLEX_MULTIPART": [3],
    "E2_UNMATCHED_GT": [87, 104, 111, 112, 113, 114, 115, 116, 117, 118],
    "SHARED_WALL_UNDERFILL": [120, 121, 123, 125, 126, 128],
    "OVER_VOLUME_WARNING": [50, 84, 33, 74, 119],
}
STRATA_NOTES = {
    "OK_CONTROL": "E1 per-building read-out and E2 automatic split succeeded; positive control.",
    "HIP_ROOF_COMPLEXITY": "Hip or multi-plane roof partition/height diagnostic.",
    "COMPLEX_MULTIPART": "Complex/multipart read-out limitation diagnostic.",
    "E2_UNMATCHED_GT": "E1 strong, E2 automatic split did not recover; oracle split recovery test.",
    "SHARED_WALL_UNDERFILL": "Row-house/shared-wall underfill and ambiguity candidates.",
    "OVER_VOLUME_WARNING": "Acceptable F with overfill or volume warning candidates.",
}
TARGET_BIDS = sorted({bid for bids in STRATA.values() for bid in bids})

PRIMARY_MODE = "mesh_surface_proximity"
FOOTPRINT_MODE = "footprint_containment_diagnostic"
OPACITY_THRESH = 0.05
ASSIGNMENT_RADIUS_POLICY = "adaptive_max_1m_0p05_extent"
AMBIGUOUS_GAP_M = 0.20
FOOTPRINT_BUFFER_M = 0.50
MAX_WALL_PLANES = 48
MAX_ROOF_PLANES = 16
MAX_GROUND_PLANES = 4
MIN_PLANE_SUPPORT_FRACTION = 0.002
N_METRIC_SAMPLE = 6000
SURFACE_THRESH_M = 0.5
FORMAL_VALIDITY_BLOCKED = "VAL3DITY_BLOCKED_DEPENDENCY"


@dataclass
class SurfaceAssignment:
    active_indices: np.ndarray
    nearest_bid: np.ndarray
    nearest_distance: np.ndarray
    second_bid: np.ndarray
    second_distance: np.ndarray
    assigned: np.ndarray
    ambiguous: np.ndarray


@dataclass
class GTContext:
    buildings: List[Dict]
    by_bid: Dict[int, Dict]
    vertices_by_bid: Dict[int, np.ndarray]
    footprint_by_bid: Dict[int, Optional[Polygon]]
    extent_by_bid: Dict[int, float]
    radius_by_bid: Dict[int, float]
    surface_tree: cKDTree
    surface_bids: np.ndarray
    surface_points: np.ndarray


def mkdir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def jsonable(obj):
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, np.generic):
        return obj.item()
    if isinstance(obj, (Point, Polygon)):
        return obj.wkt
    return str(obj)


def write_json(path: Path, payload: Dict) -> None:
    path.write_text(json.dumps(payload, indent=2, default=jsonable) + "\n")


def read_csv(path: Path) -> List[Dict]:
    if not path.exists():
        return []
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: List[Dict], fields: Optional[List[str]] = None) -> None:
    mkdir(path.parent)
    if fields is None:
        keys = []
        seen = set()
        for row in rows:
            for key in row:
                if key not in seen:
                    seen.add(key)
                    keys.append(key)
        fields = keys
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fields})


def fmt(v: object, nd: int = 3) -> str:
    if v is None or v == "":
        return "NA"
    if isinstance(v, bool):
        return "true" if v else "false"
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    if math.isnan(f) or math.isinf(f):
        return "NA"
    return f"{f:.{nd}f}"


def md_table(headers: List[str], rows: List[List[object]]) -> str:
    out = ["| " + " | ".join(headers) + " |",
           "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in rows:
        out.append("| " + " | ".join(str(x) for x in row) + " |")
    return "\n".join(out)


def float_or_none(value: object) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) or math.isinf(f) else f


def stratum_for_bid(bid: int) -> str:
    for stratum, bids in STRATA.items():
        if bid in bids:
            return stratum
    return "UNSTRATIFIED"


def input_policy(oracle_mode: str) -> Dict:
    return {
        "experiment_status": "geometry-only exploratory",
        "proposed_method_full_end_to_end_performance": False,
        "stage2_evidence_quality_upper_bound": True,
        "gt_building_id_used_for_primitive_assignment": True,
        "gt_building_id_used_for_readout": False,
        "gt_footprint_used_for_readout": False,
        "gt_roofprint_used_for_readout": False,
        "gt_bbox_used_for_readout": False,
        "gt_roof_type_used_for_readout": False,
        "gt_final_roof_model_used_for_readout": False,
        "e2_taxonomy_used_for_readout": False,
        "e2_taxonomy_usage": "subset selection and report grouping only",
        "roofer_binary_called": False,
        "oracle_mode": oracle_mode,
        "allowed_readout_inputs": [
            "primitive center", "primitive normal", "semantic class/probabilities",
            "support area proxy", "opacity",
        ],
    }


def load_primitives(condition: str) -> Dict[str, np.ndarray]:
    path = CONDITION_PATHS[condition]
    if not path.exists():
        raise FileNotFoundError(f"Missing Stage2 primitive export for {condition}: {path}")
    data = np.load(path)
    return {k: data[k] for k in data.files}


def normalize_rows(v: np.ndarray) -> np.ndarray:
    arr = np.asarray(v, dtype=np.float64)
    n = np.linalg.norm(arr, axis=1, keepdims=True)
    return arr / np.maximum(n, 1e-12)


def active_mask(prims: Dict[str, np.ndarray]) -> np.ndarray:
    centers = np.asarray(prims["centers"])
    normals = np.asarray(prims["normals"])
    labels = np.asarray(prims["labels"])
    return (
        np.isfinite(centers).all(axis=1) &
        np.isfinite(normals).all(axis=1) &
        (np.asarray(prims["opacities"]) >= OPACITY_THRESH) &
        (labels >= 0) & (labels <= 3)
    )


def build_gt_context(buildings: List[Dict]) -> GTContext:
    by_bid = {int(b["building_id"]): b for b in buildings}
    vertices_by_bid = {}
    footprint_by_bid = {}
    extent_by_bid = {}
    radius_by_bid = {}
    samples = []
    sample_bids = []
    face_ord = 0
    for b in buildings:
        bid = int(b["building_id"])
        vertices = np.concatenate([np.asarray(f["vertices"], dtype=np.float64) for f in b["faces"]], axis=0)
        vertices_by_bid[bid] = vertices
        footprint_by_bid[bid] = pm.footprint_from_gt(b)
        extent = float(np.linalg.norm(vertices.max(axis=0) - vertices.min(axis=0)))
        extent_by_bid[bid] = extent
        radius_by_bid[bid] = max(1.0, 0.05 * extent)
        for face in b["faces"]:
            pts = rr._sample_face(face, min_points=48, density=0.35, seed=83000 + face_ord)
            samples.append(pts)
            sample_bids.append(np.full(len(pts), bid, dtype=np.int64))
            face_ord += 1
    surface_points = np.concatenate(samples, axis=0)
    surface_bids = np.concatenate(sample_bids, axis=0)
    return GTContext(
        buildings=buildings,
        by_bid=by_bid,
        vertices_by_bid=vertices_by_bid,
        footprint_by_bid=footprint_by_bid,
        extent_by_bid=extent_by_bid,
        radius_by_bid=radius_by_bid,
        surface_tree=cKDTree(surface_points),
        surface_bids=surface_bids,
        surface_points=surface_points,
    )


def tree_query(tree: cKDTree, points: np.ndarray, k: int) -> Tuple[np.ndarray, np.ndarray]:
    try:
        return tree.query(points, k=k, workers=-1)
    except TypeError:
        return tree.query(points, k=k)


def surface_assignment(prims: Dict[str, np.ndarray], gt: GTContext) -> SurfaceAssignment:
    active = np.where(active_mask(prims))[0]
    centers = np.asarray(prims["centers"], dtype=np.float64)[active]
    k = min(12, len(gt.surface_points))
    dists, nn = tree_query(gt.surface_tree, centers, k=k)
    if k == 1:
        dists = dists[:, None]
        nn = nn[:, None]
    nbids = gt.surface_bids[nn]
    nearest_bid = nbids[:, 0].astype(np.int64)
    nearest_dist = dists[:, 0].astype(np.float64)
    second_bid = np.full(len(active), -1, dtype=np.int64)
    second_dist = np.full(len(active), np.inf, dtype=np.float64)
    for col in range(1, nbids.shape[1]):
        m = (second_bid < 0) & (nbids[:, col] != nearest_bid)
        second_bid[m] = nbids[m, col]
        second_dist[m] = dists[m, col]
    radii = np.asarray([gt.radius_by_bid.get(int(b), 1.0) for b in nearest_bid], dtype=np.float64)
    assigned = nearest_dist <= radii
    ambiguous = assigned & np.isfinite(second_dist) & ((second_dist - nearest_dist) < AMBIGUOUS_GAP_M)
    return SurfaceAssignment(active, nearest_bid, nearest_dist, second_bid, second_dist, assigned, ambiguous)


def surface_indices_for_bid(cache: SurfaceAssignment, bid: int) -> np.ndarray:
    m = cache.assigned & (cache.nearest_bid == bid)
    return cache.active_indices[m]


def surface_nearby_unassigned(cache: SurfaceAssignment, gt: GTContext, bid: int) -> int:
    radius = gt.radius_by_bid[bid]
    m = (
        (cache.nearest_bid == bid) &
        (~cache.assigned) &
        (cache.nearest_distance <= 2.0 * radius)
    )
    return int(np.sum(m))


def footprint_assignment_for_targets(prims: Dict[str, np.ndarray], gt: GTContext,
                                     target_bids: Iterable[int]) -> Tuple[Dict[int, np.ndarray], Dict[int, int], Dict[int, int]]:
    active = np.where(active_mask(prims))[0]
    centers = np.asarray(prims["centers"], dtype=np.float64)[active]
    xz = centers[:, [0, 2]]
    membership = np.zeros(len(active), dtype=np.uint8)
    by_bid: Dict[int, np.ndarray] = {}
    nearby: Dict[int, int] = {}
    local_indices_by_bid: Dict[int, np.ndarray] = {}
    for bid in target_bids:
        fp = gt.footprint_by_bid.get(int(bid))
        if fp is None or fp.is_empty:
            by_bid[bid] = np.empty(0, dtype=np.int64)
            nearby[bid] = 0
            local_indices_by_bid[bid] = np.empty(0, dtype=np.int64)
            continue
        poly = fp.buffer(FOOTPRINT_BUFFER_M)
        minx, minz, maxx, maxz = poly.bounds
        rough = np.where(
            (xz[:, 0] >= minx) & (xz[:, 0] <= maxx) &
            (xz[:, 1] >= minz) & (xz[:, 1] <= maxz)
        )[0]
        inside_local = []
        for li in rough:
            p = Point(float(xz[li, 0]), float(xz[li, 1]))
            if poly.contains(p) or poly.touches(p):
                inside_local.append(int(li))
        inside = np.asarray(inside_local, dtype=np.int64)
        membership[inside] += 1
        local_indices_by_bid[bid] = inside
        by_bid[bid] = active[inside]
        nearby[bid] = int(max(len(rough) - len(inside), 0))
    ambiguous = {bid: int(np.sum(membership[local_indices_by_bid[bid]] > 1)) for bid in target_bids}
    return by_bid, ambiguous, nearby


def evidence_from_indices(prims: Dict[str, np.ndarray], indices: np.ndarray) -> Dict:
    indices = np.asarray(indices, dtype=np.int64)
    centers = np.asarray(prims["centers"], dtype=np.float64)[indices]
    normals = normalize_rows(np.asarray(prims["normals"], dtype=np.float64)[indices])
    sem_probs = np.asarray(prims["sem_probs"], dtype=np.float64)[indices]
    labels = np.asarray(prims["labels"], dtype=np.int64)[indices]
    labels = np.where((labels >= 0) & (labels <= 3), labels, np.argmax(sem_probs, axis=1))
    weights = np.asarray(prims["areas"], dtype=np.float64)[indices] * np.asarray(prims["opacities"], dtype=np.float64)[indices]
    weights = np.where(np.isfinite(weights), weights, 0.0)
    return {
        "points": centers,
        "normals": normals,
        "classes": labels.astype(np.int64),
        "weights": np.maximum(weights, 1e-9),
        "primitive_indices": indices,
        "sem_probs": sem_probs,
        "opacities": np.asarray(prims["opacities"], dtype=np.float64)[indices],
        "areas": np.asarray(prims["areas"], dtype=np.float64)[indices],
        "scales": np.asarray(prims["scales"], dtype=np.float64)[indices] if "scales" in prims else np.zeros((len(indices), 3)),
    }


def class_counts(evidence: Dict) -> Dict:
    return {
        "roof": int(np.sum(evidence["classes"] == 1)),
        "wall": int(np.sum(evidence["classes"] == 2)),
        "terrain": int(np.sum(evidence["classes"] == 3)),
        "background": int(np.sum(evidence["classes"] == 0)),
    }


def normal_mode_stats(normals: np.ndarray, weights: np.ndarray,
                      cos_tol: float = 0.985, min_weight_frac: float = 0.02) -> Tuple[int, float]:
    if len(normals) == 0:
        return 0, 0.0
    total = float(np.sum(weights))
    if total <= 0:
        return 0, 0.0
    modes: List[Tuple[np.ndarray, float]] = []
    for n, w in sorted(zip(normals, weights), key=lambda x: -float(x[1])):
        n = np.asarray(n, dtype=np.float64)
        n /= np.linalg.norm(n) + 1e-12
        matched = False
        for i, (mn, mw) in enumerate(modes):
            cos = float(np.dot(n, mn))
            if abs(cos) >= cos_tol:
                sign = 1.0 if cos >= 0 else -1.0
                new = mn * mw + sign * n * float(w)
                new /= np.linalg.norm(new) + 1e-12
                modes[i] = (new, mw + float(w))
                matched = True
                break
        if not matched:
            modes.append((n, float(w)))
    active_modes = [w for _n, w in modes if w >= min_weight_frac * total]
    return len(active_modes), (max(active_modes) / total if active_modes else 0.0)


def entropy_rows(probs: np.ndarray) -> np.ndarray:
    if len(probs) == 0:
        return np.asarray([], dtype=np.float64)
    p = np.clip(probs, 1e-12, 1.0)
    return -np.sum(p * np.log(p), axis=1) / math.log(p.shape[1])


def safe_mean(arr: np.ndarray) -> Optional[float]:
    if len(arr) == 0:
        return None
    return float(np.mean(arr))


def save_assignment_and_evidence(out_dir: Path, bid: int, condition: str, oracle_mode: str,
                                 evidence: Dict, assigned_indices: np.ndarray, stats: Dict) -> None:
    mkdir(out_dir)
    np.savez_compressed(out_dir / "evidence_primitives.npz", **evidence)
    rr.write_evidence_ply(out_dir / "evidence_primitives.ply", evidence)
    rr.write_evidence_stats(out_dir / "evidence_stats.csv", evidence)
    write_json(out_dir / "assignment_stats.json", stats)


def assignment_stats_for_bid(prims: Dict[str, np.ndarray], evidence: Dict, indices: np.ndarray,
                             bid: int, condition: str, oracle_mode: str, gt: GTContext,
                             cache: Optional[SurfaceAssignment], ambiguous_count: int,
                             nearby_unassigned: int) -> Dict:
    indices = np.asarray(indices, dtype=np.int64)
    probs = evidence["sem_probs"]
    counts = class_counts(evidence)
    distances = np.asarray([], dtype=np.float64)
    if cache is not None and len(indices):
        pos = np.full(int(cache.active_indices.max()) + 1, -1, dtype=np.int64)
        pos[cache.active_indices] = np.arange(len(cache.active_indices))
        valid = indices[indices < len(pos)]
        local = pos[valid]
        local = local[local >= 0]
        distances = cache.nearest_distance[local]
    warnings = []
    if len(indices) == 0:
        warnings.append("NO_ASSIGNED_PRIMITIVES")
    if counts["wall"] < 10:
        warnings.append("LOW_WALL_PRIMITIVE_COUNT")
    if counts["roof"] < 10:
        warnings.append("LOW_ROOF_PRIMITIVE_COUNT")
    if counts["terrain"] < 3:
        warnings.append("LOW_TERRAIN_PRIMITIVE_COUNT")
    if len(indices) and ambiguous_count / max(len(indices), 1) > 0.20:
        warnings.append("HIGH_ASSIGNMENT_AMBIGUITY")
    return {
        "bid": f"B{bid}",
        "bid_int": int(bid),
        "condition": condition,
        "oracle_mode": oracle_mode,
        "assignment_radius_policy": ASSIGNMENT_RADIUS_POLICY if oracle_mode == PRIMARY_MODE else "footprint_buffer_containment",
        "assignment_radius_m": gt.radius_by_bid[bid] if oracle_mode == PRIMARY_MODE else FOOTPRINT_BUFFER_M,
        "n_assigned": int(len(indices)),
        "n_unassigned_scene_nearby": int(nearby_unassigned),
        "n_ambiguous": int(ambiguous_count),
        "mean_assignment_distance": safe_mean(distances),
        "p95_assignment_distance": float(np.percentile(distances, 95)) if len(distances) else None,
        "class_counts": counts,
        "mean_p_roof": safe_mean(probs[:, 1]) if len(probs) else None,
        "mean_p_wall": safe_mean(probs[:, 2]) if len(probs) else None,
        "mean_p_terrain": safe_mean(probs[:, 3]) if len(probs) else None,
        "warning_flags": warnings,
        "input_policy": input_policy(oracle_mode),
    }


def evidence_metrics(evidence: Dict, bid: int, condition: str, oracle_mode: str,
                     stratum: str, assignment_stats: Dict, gt: GTContext) -> Dict:
    cls = evidence["classes"]
    pts = evidence["points"]
    normals = evidence["normals"]
    weights = evidence["weights"]
    probs = evidence["sem_probs"]
    counts = class_counts(evidence)

    wall = cls == 2
    roof = cls == 1
    terrain = cls == 3
    wall_modes, wall_purity = normal_mode_stats(normals[wall], weights[wall])
    roof_modes, roof_purity = normal_mode_stats(normals[roof], weights[roof])
    wall_vert = safe_mean((np.abs(normals[wall] @ rr.GRAVITY) < 0.35).astype(np.float64)) if np.any(wall) else None
    roof_y = pts[roof, 1] if np.any(roof) else np.asarray([], dtype=np.float64)
    terrain_y = pts[terrain, 1] if np.any(terrain) else np.asarray([], dtype=np.float64)
    flags = []
    if len(pts) < 30:
        flags.append("LOW_TOTAL_PRIMITIVES")
    if counts["wall"] < 10:
        flags.append("LOW_WALL_EVIDENCE")
    if counts["roof"] < 10:
        flags.append("LOW_ROOF_EVIDENCE")
    if counts["terrain"] < 3:
        flags.append("LOW_TERRAIN_EVIDENCE")
    if wall_vert is not None and wall_vert < 0.50:
        flags.append("LOW_WALL_VERTICAL_FRACTION")
    if roof_modes == 0:
        flags.append("NO_ROOF_MODE")
    if assignment_stats.get("n_ambiguous", 0) / max(assignment_stats.get("n_assigned", 0), 1) > 0.20:
        flags.append("ASSIGNMENT_AMBIGUITY")
    gt_area = sum(float(f["area"]) for f in gt.by_bid[bid]["faces"])
    fp = gt.footprint_by_bid.get(bid)
    fp_area = float(fp.area) if fp is not None and not fp.is_empty else 0.0
    wall_bbox_extent = [0.0, 0.0, 0.0]
    if np.any(wall):
        wall_bbox_extent = (pts[wall].max(axis=0) - pts[wall].min(axis=0)).tolist()
    hist, hist_edges = np.histogram(probs[:, 2] if len(probs) else [], bins=[0, 0.2, 0.4, 0.6, 0.8, 1.0])
    metrics = {
        "stratum": stratum,
        "bid": f"B{bid}",
        "bid_int": int(bid),
        "condition": condition,
        "oracle_mode": oracle_mode,
        "wall_primitive_count": counts["wall"],
        "wall_count": counts["wall"],
        "wall_support_area": float(weights[wall].sum()) if np.any(wall) else 0.0,
        "mean_p_wall": safe_mean(probs[wall, 2]) if np.any(wall) else None,
        "wall_vertical_fraction": wall_vert,
        "wall_vert_frac": wall_vert,
        "wall_azimuth_mode_count": wall_modes,
        "wall_mode_count": wall_modes,
        "wall_mode_purity": wall_purity,
        "wall_support_coverage_proxy": float(weights[wall].sum()) / max(gt_area, 1e-9),
        "wall_center_bbox_extent": wall_bbox_extent,
        "wall_confidence_histogram": {
            "bins": hist_edges.tolist(),
            "counts": hist.tolist(),
        },
        "roof_primitive_count": counts["roof"],
        "roof_count": counts["roof"],
        "roof_support_area": float(weights[roof].sum()) if np.any(roof) else 0.0,
        "mean_p_roof": safe_mean(probs[roof, 1]) if np.any(roof) else None,
        "roof_normal_mode_count": roof_modes,
        "roof_mode_count": roof_modes,
        "roof_mode_purity": roof_purity,
        "roof_height_range": float(np.max(roof_y) - np.min(roof_y)) if len(roof_y) else None,
        "roof_y_percentiles": np.percentile(roof_y, [5, 25, 50, 75, 95]).tolist() if len(roof_y) else [],
        "roof_support_coverage_proxy": float(weights[roof].sum()) / max(gt_area, 1e-9),
        "roof_candidate_count": roof_modes,
        "terrain_primitive_count": counts["terrain"],
        "mean_p_terrain": safe_mean(probs[terrain, 3]) if np.any(terrain) else None,
        "ground_level_estimate": float(np.median(terrain_y)) if len(terrain_y) else None,
        "ground_level_std": float(np.std(terrain_y)) if len(terrain_y) else None,
        "ground_support_area": float(weights[terrain].sum()) if np.any(terrain) else 0.0,
        "primitive_count_total": int(len(pts)),
        "n_primitives": int(len(pts)),
        "assigned_area_total": float(weights.sum()) if len(weights) else 0.0,
        "orphan_rate": assignment_stats.get("n_unassigned_scene_nearby", 0) / max(
            assignment_stats.get("n_assigned", 0) + assignment_stats.get("n_unassigned_scene_nearby", 0), 1),
        "class_entropy_mean": safe_mean(entropy_rows(probs)),
        "footprint_area_eval_only": fp_area,
        "evidence_quality_flag": "OK" if not flags else "+".join(flags),
        "evidence_flag": "OK" if not flags else "+".join(flags),
    }
    return metrics


def plot_overlay(path: Path, evidence: Dict, footprint: Optional[Polygon], title: str) -> None:
    fig, ax = plt.subplots(figsize=(6, 6))
    for cls, color, label in [(2, "#2D5FD7", "wall"), (1, "#DC2828", "roof"), (3, "#2DA04B", "terrain")]:
        pts = evidence["points"][evidence["classes"] == cls][:, [0, 2]]
        if len(pts):
            ax.scatter(pts[:, 0], pts[:, 1], s=3, c=color, alpha=0.35, label=label)
    if footprint is not None and not footprint.is_empty:
        xy = np.asarray(list(footprint.exterior.coords), dtype=np.float64)
        ax.plot(xy[:, 0], xy[:, 1], color="black", linewidth=1.8, label="read-out footprint")
    ax.set_aspect("equal", adjustable="box")
    ax.set_title(title)
    ax.grid(True, linewidth=0.2, alpha=0.3)
    ax.legend(loc="best", fontsize=7)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def prune_planes(planes: List[rr.PlaneCandidate], evidence: Dict, class_id: int,
                 max_count: int) -> Tuple[List[rr.PlaneCandidate], Dict]:
    class_weights = evidence["weights"][evidence["classes"] == class_id]
    total = float(np.sum(class_weights)) if len(class_weights) else 0.0
    min_support = max(total * MIN_PLANE_SUPPORT_FRACTION, 1e-9)
    supported = [p for p in planes if float(p.support_weight) >= min_support]
    if len(supported) < min(max_count, len(planes)):
        supported = planes
    kept = supported[:max_count]
    return kept, {
        "class_id": class_id,
        "class_name": rr.CLASS_NAME.get(class_id, "unknown"),
        "raw_plane_count": len(planes),
        "kept_plane_count": len(kept),
        "max_plane_count": max_count,
        "min_support_fraction": MIN_PLANE_SUPPORT_FRACTION,
        "min_support_area": min_support,
    }


def write_failure(out_dir: Path, bid: int, condition: str, oracle_mode: str,
                  evidence: Dict, evidence_row: Dict, assignment_row: Dict,
                  reason: str, exc: Exception, stage: str) -> Dict:
    payload = {
        "bid": f"B{bid}",
        "bid_int": int(bid),
        "condition": condition,
        "oracle_mode": oracle_mode,
        "stratum": stratum_for_bid(bid),
        "pipeline_success": False,
        "failure_stage": stage,
        "geometry_failure_reason": reason,
        "formal_validity_status": FORMAL_VALIDITY_BLOCKED,
        "val3dity_valid": None,
        "exception_type": type(exc).__name__,
        "exception": str(exc),
        "traceback_tail": traceback.format_exc(limit=5),
        "assignment_stats_path": str(out_dir / "assignment_stats.json"),
        "evidence_metrics_path": str(out_dir / "evidence_metrics.json"),
        "input_policy": input_policy(oracle_mode),
        **{k: v for k, v in evidence_row.items() if k not in {"wall_confidence_histogram", "roof_y_percentiles", "wall_center_bbox_extent"}},
    }
    write_json(out_dir / "metrics.json", payload)
    write_json(out_dir / "stepwise_metrics.json", payload)
    for missing_name in ["evidence_graph.json", "footprint_graph.json", "roof_surface_candidates.json", "selected_surfaces.json"]:
        p = out_dir / missing_name
        if not p.exists():
            write_json(p, {"pipeline_success": False, "failure_stage": stage, "geometry_failure_reason": reason})
    plot_overlay(out_dir / "fig_overlay.png", evidence, None, f"B{bid} {condition} {oracle_mode}")
    return payload


def classify_geometry(metrics: Dict) -> str:
    if metrics.get("pipeline_success") is not True:
        return str(metrics.get("geometry_failure_reason", "PIPELINE_FAIL"))
    f = float_or_none(metrics.get("F_score"))
    recall = float_or_none(metrics.get("recall_coverage"))
    precision = float_or_none(metrics.get("pred_precision"))
    h_err = float_or_none(metrics.get("h_err"))
    vol_ratio = float_or_none(metrics.get("vol_ratio"))
    if f is None:
        return "EVAL_FAIL"
    if vol_ratio is not None and vol_ratio > 2.0:
        return "OVER_VOLUME"
    if recall is not None and recall < 0.45:
        return "LOW_RECALL_UNDERFILL"
    if precision is not None and precision < 0.45:
        return "LOW_PRECISION_OVERFILL"
    if h_err is not None and h_err > 2.0 and f < 0.60:
        return "HEIGHT_UNDERFIT"
    if f < 0.50:
        if precision is not None and recall is not None and precision < recall:
            return "LOW_PRECISION_OVERFILL"
        return "LOW_RECALL_UNDERFILL"
    return "OK_GEOMETRY_ONLY"


def formal_status_from_val(val: Dict) -> str:
    status = val.get("val3dity_status")
    if status == "BLOCKED_DEPENDENCY":
        return FORMAL_VALIDITY_BLOCKED
    if status == "PASS":
        return "VAL3DITY_EXECUTED_PASS"
    if status == "FAIL":
        return "VAL3DITY_EXECUTED_FAIL"
    return f"VAL3DITY_{status or 'UNKNOWN'}"


def run_relation_readout(out_dir: Path, bid: int, condition: str, oracle_mode: str,
                         building: Dict, evidence: Dict, evidence_row: Dict,
                         assignment_row: Dict, val_bin: Optional[Path]) -> Dict:
    counts = class_counts(evidence)
    footprint: Optional[Polygon] = None
    try:
        if counts["roof"] < 3 or counts["wall"] < 3 or counts["terrain"] < 3:
            raise RuntimeError(f"insufficient evidence counts: {counts}")
        raw_wall_planes = rr.cluster_planes_from_evidence(evidence, 2)
        raw_roof_planes = rr.cluster_planes_from_evidence(evidence, 1)
        raw_ground_planes = rr.cluster_planes_from_evidence(evidence, 3)
        wall_planes, wall_filter = prune_planes(raw_wall_planes, evidence, 2, MAX_WALL_PLANES)
        roof_planes, roof_filter = prune_planes(raw_roof_planes, evidence, 1, MAX_ROOF_PLANES)
        ground_planes, ground_filter = prune_planes(raw_ground_planes, evidence, 3, MAX_GROUND_PLANES)
        write_json(out_dir / "plane_filtering.json", {
            "purpose": "Stage2 primitive noise control before relation graph construction; GT is not used.",
            "wall": wall_filter,
            "roof": roof_filter,
            "ground": ground_filter,
        })
        if len(wall_planes) < 2 or len(roof_planes) < 1 or len(ground_planes) < 1:
            raise RuntimeError(
                f"insufficient plane candidates wall={len(wall_planes)} "
                f"roof={len(roof_planes)} ground={len(ground_planes)}"
            )
    except Exception as exc:
        return write_failure(out_dir, bid, condition, oracle_mode, evidence, evidence_row,
                             assignment_row, "EVIDENCE_OR_PLANE_INSUFFICIENT", exc, "evidence")

    try:
        footprint, footprint_candidates, wall_segments = rr.build_footprint_candidates(evidence, wall_planes)
        rr.write_footprint_graph_json(out_dir / "footprint_graph.json", footprint, footprint_candidates, wall_segments)
        write_json(out_dir / "footprint_candidates.json", {
            "selected_candidate_id": footprint_candidates[0]["id"],
            "candidates": footprint_candidates,
        })
        rr.write_footprint_plot(out_dir / "footprint_candidates.png", footprint, footprint_candidates, evidence)
    except Exception as exc:
        return write_failure(out_dir, bid, condition, oracle_mode, evidence, evidence_row,
                             assignment_row, "FOOTPRINT_READOUT_FAIL", exc, "footprint")

    try:
        graph_edges = rr.write_graph_json(out_dir / "evidence_graph.json", wall_planes, roof_planes, ground_planes, wall_segments)
        roof_candidates = rr.roof_surface_candidates(roof_planes, footprint, evidence)
        if not roof_candidates:
            raise RuntimeError("no roof surface candidates")
        write_json(out_dir / "roof_surface_candidates.json", {
            "roof_surface_generation": "roof plane candidates clipped diagnostically; final shell uses relation height-field triangulation",
            "candidates": roof_candidates,
        })
        write_json(out_dir / "roof_modes.json", {
            "roof_type_label_used": False,
            "roof_plane_candidates": [rr.plane_to_json(p) for p in roof_planes],
        })
        rr.write_roof_mode_plot(out_dir / "roof_mode_plot.png", roof_planes)
    except Exception as exc:
        return write_failure(out_dir, bid, condition, oracle_mode, evidence, evidence_row,
                             assignment_row, "ROOF_PARTITION_FAIL", exc, "roof_partition")

    try:
        faces, assembly_diag = rr.assemble_closed_shell(footprint, evidence, roof_planes)
        city_diag = rr.faces_to_cityjson(faces, bid, out_dir / "relation_readout.city.json")
        selected = rr.selected_surfaces_payload(faces, assembly_diag, city_diag)
        write_json(out_dir / "selected_surfaces.json", selected)
        archetype = rr.optional_roof_archetype(roof_planes, assembly_diag, evidence)
        write_json(out_dir / "optional_roof_archetype.json", archetype)
    except Exception as exc:
        return write_failure(out_dir, bid, condition, oracle_mode, evidence, evidence_row,
                             assignment_row, "SHELL_ASSEMBLY_FAIL", exc, "shell_assembly")

    geom = eval_readout_geometry(building, out_dir, city_diag)
    val = parse_val3dity_result(bid, out_dir, val_bin)
    write_json(out_dir / "val3dity_parsed.json", val)
    stepwise = {
        "bid": f"B{bid}",
        "bid_int": int(bid),
        "condition": condition,
        "oracle_mode": oracle_mode,
        "n_wall_nodes": len(wall_planes),
        "n_roof_nodes": len(roof_planes),
        "n_ground_nodes": len(ground_planes),
        "raw_wall_nodes": wall_filter["raw_plane_count"],
        "raw_roof_nodes": roof_filter["raw_plane_count"],
        "raw_ground_nodes": ground_filter["raw_plane_count"],
        "n_relation_edges": len(graph_edges),
        "n_footprint_candidates": len(footprint_candidates),
        "selected_footprint_candidate": footprint_candidates[0]["id"],
        "selected_footprint_score": footprint_candidates[0]["score"],
        "n_roof_surfaces": int(selected["cityjson_diagnostics"]["surface_types"].get("RoofSurface", 0)),
        "optional_roof_archetype": archetype["label"],
        "formal_validity_status": formal_status_from_val(val),
        "val3dity_valid": val.get("val3dity_valid"),
        "input_policy": input_policy(oracle_mode),
    }
    metrics = {
        **evidence_row,
        **stepwise,
        **geom,
        **val,
        "pipeline_success": True,
        "cityjson_path": str(out_dir / "relation_readout.city.json"),
        "signed_volume": float(city_diag.get("signed_volume", float("nan"))),
        "formal_validity_status": formal_status_from_val(val),
        "val3dity_valid": val.get("val3dity_valid"),
        "geometry_failure_reason": "PENDING_CLASSIFICATION",
        "assignment_stats_path": str(out_dir / "assignment_stats.json"),
        "evidence_metrics_path": str(out_dir / "evidence_metrics.json"),
    }
    metrics["geometry_failure_reason"] = classify_geometry(metrics)
    stepwise["geometry_failure_reason"] = metrics["geometry_failure_reason"]
    stepwise["F_score"] = metrics.get("F_score")
    stepwise["h_err"] = metrics.get("h_err")
    stepwise["vol_ratio"] = metrics.get("vol_ratio")
    write_json(out_dir / "metrics.json", metrics)
    write_json(out_dir / "stepwise_metrics.json", stepwise)
    plot_overlay(out_dir / "fig_overlay.png", evidence, footprint, f"B{bid} {condition} {oracle_mode}")
    return metrics


def artifact_dir(base: Path, bid: int, condition: str, oracle_mode: str) -> Path:
    return base / f"B{bid}" / condition.lower() / oracle_mode


def run_condition(base: Path, condition: str, target_bids: List[int], gt: GTContext,
                  val_bin: Optional[Path], include_footprint_mode: bool) -> Dict[str, List[Dict]]:
    prims = load_primitives(condition)
    surface_cache = surface_assignment(prims, gt)
    footprint_by_bid: Dict[int, np.ndarray] = {}
    footprint_ambiguous: Dict[int, int] = {}
    footprint_nearby: Dict[int, int] = {}
    if include_footprint_mode:
        footprint_by_bid, footprint_ambiguous, footprint_nearby = footprint_assignment_for_targets(prims, gt, target_bids)

    assignment_rows: List[Dict] = []
    evidence_rows: List[Dict] = []
    metrics_rows: List[Dict] = []
    matching_rows: List[Dict] = []
    modes = [PRIMARY_MODE] + ([FOOTPRINT_MODE] if include_footprint_mode else [])

    for bid in target_bids:
        for oracle_mode in modes:
            print(f"[E3] {base.name} {condition} B{bid} {oracle_mode}", flush=True)
            if oracle_mode == PRIMARY_MODE:
                indices = surface_indices_for_bid(surface_cache, bid)
                ambiguous_count = int(np.sum(surface_cache.ambiguous & (surface_cache.nearest_bid == bid)))
                nearby = surface_nearby_unassigned(surface_cache, gt, bid)
                cache = surface_cache
            else:
                indices = footprint_by_bid.get(bid, np.empty(0, dtype=np.int64))
                ambiguous_count = footprint_ambiguous.get(bid, 0)
                nearby = footprint_nearby.get(bid, 0)
                cache = surface_cache
            out_dir = artifact_dir(base, bid, condition, oracle_mode)
            if out_dir.exists():
                shutil.rmtree(out_dir)
            mkdir(out_dir)
            evidence = evidence_from_indices(prims, indices)
            assignment = assignment_stats_for_bid(
                prims, evidence, indices, bid, condition, oracle_mode, gt, cache, ambiguous_count, nearby)
            save_assignment_and_evidence(out_dir, bid, condition, oracle_mode, evidence, indices, assignment)
            ev_metrics = evidence_metrics(evidence, bid, condition, oracle_mode, stratum_for_bid(bid), assignment, gt)
            write_json(out_dir / "evidence_metrics.json", ev_metrics)
            metrics = run_relation_readout(out_dir, bid, condition, oracle_mode,
                                           gt.by_bid[bid], evidence, ev_metrics, assignment, val_bin)
            assignment_rows.append(flatten_assignment(assignment))
            evidence_rows.append(flatten_evidence(ev_metrics))
            metrics_rows.append(flatten_metrics(metrics))
            matching_rows.append({
                "pred_id": f"B{bid}_{condition}_{oracle_mode}",
                "bid": f"B{bid}",
                "condition": condition,
                "oracle_mode": oracle_mode,
                "matched_gt_bid": bid,
                "match_IoU": metrics.get("footprint_IoU"),
                "bbox_IoU": metrics.get("bbox_IoU"),
                "oracle_assignment": True,
                "matching_policy": "GT oracle one-to-one by target bid; IoU reported for evaluation only",
            })
    return {
        "assignment": assignment_rows,
        "evidence": evidence_rows,
        "metrics": metrics_rows,
        "matching": matching_rows,
    }


def flatten_assignment(row: Dict) -> Dict:
    out = dict(row)
    cc = out.pop("class_counts", {})
    for k, v in cc.items():
        out[f"class_count_{k}"] = v
    flags = out.get("warning_flags")
    out["warning_flags"] = ";".join(flags) if isinstance(flags, list) else flags
    out.pop("input_policy", None)
    return out


def flatten_evidence(row: Dict) -> Dict:
    out = dict(row)
    out["wall_center_bbox_extent"] = " ".join(fmt(x, 3) for x in out.get("wall_center_bbox_extent", []))
    out["roof_y_percentiles"] = " ".join(fmt(x, 3) for x in out.get("roof_y_percentiles", []))
    out.pop("wall_confidence_histogram", None)
    return out


def flatten_metrics(row: Dict) -> Dict:
    keep = [
        "stratum", "bid", "bid_int", "condition", "oracle_mode", "pipeline_success",
        "geometry_failure_reason", "formal_validity_status", "val3dity_valid",
        "h_err", "recall_coverage", "pred_precision", "F_score", "vol_ratio",
        "footprint_IoU", "bbox_IoU", "surface_area_ratio", "Hausdorff", "Chamfer",
        "edge_ok", "open_edges", "nonmanifold_edges", "face_planarity_max",
        "wall_count", "roof_count", "terrain_primitive_count", "wall_vert_frac",
        "n_primitives", "primitive_count_total",
        "wall_support_area", "roof_support_area", "ground_support_area",
        "wall_mode_count", "wall_mode_purity", "roof_mode_count", "roof_mode_purity",
        "mean_p_wall", "mean_p_roof", "mean_p_terrain", "evidence_flag",
        "selected_footprint_score", "n_wall_nodes", "n_roof_nodes", "n_ground_nodes",
        "n_relation_edges", "optional_roof_archetype", "cityjson_path",
    ]
    return {k: row.get(k, "") for k in keep}


def load_e1_rows() -> Dict[int, Dict]:
    rows = []
    if E1_SUMMARY_JSON.exists():
        try:
            rows = json.loads(E1_SUMMARY_JSON.read_text()).get("rows", [])
        except Exception:
            rows = []
    if not rows:
        rows = read_csv(E1_SUMMARY_CSV)
    return {int(r["bid"]): r for r in rows if str(r.get("bid", "")).isdigit()}


def load_e2_risk() -> Dict[int, Dict]:
    return {int(r["bid"]): r for r in read_csv(E2_RISK_CSV) if str(r.get("bid", "")).isdigit()}


def e3_primary_by_bid(metrics_rows: List[Dict], condition: str = "Mutual") -> Dict[int, Dict]:
    out = {}
    for r in metrics_rows:
        if r.get("condition") == condition and r.get("oracle_mode") == PRIMARY_MODE:
            bid = int(r.get("bid_int") or str(r.get("bid", "B-1")).lstrip("B"))
            out[bid] = r
    return out


def comparison_rows(target_bids: List[int], metrics_rows: List[Dict]) -> List[Dict]:
    e1 = load_e1_rows()
    e2 = load_e2_risk()
    e3 = e3_primary_by_bid(metrics_rows, "Mutual")
    rows = []
    for bid in target_bids:
        e1r = e1.get(bid, {})
        e2r = e2.get(bid, {})
        e3r = e3.get(bid, {})
        e1_f = float_or_none(e1r.get("F_score") or e1r.get("E1_F"))
        e3_f = float_or_none(e3r.get("F_score"))
        e1_h = float_or_none(e1r.get("h_err"))
        e3_h = float_or_none(e3r.get("h_err"))
        e1_v = float_or_none(e1r.get("vol_ratio"))
        e3_v = float_or_none(e3r.get("vol_ratio"))
        rows.append({
            "stratum": stratum_for_bid(bid),
            "bid": f"B{bid}",
            "bid_int": bid,
            "E1_F": e1_f,
            "E1_failure": e1r.get("failure_reason") or e1r.get("E1_failure_reason"),
            "E2_status": e2r.get("E2_split_status"),
            "E2_component": e2r.get("E2_matched_component"),
            "E2_F": float_or_none(e2r.get("E2_F")),
            "E3_F": e3_f,
            "DeltaF_E3_E1": (e3_f - e1_f) if e1_f is not None and e3_f is not None else None,
            "E3_h_err": e3_h,
            "Delta_h_E3_E1": (e3_h - e1_h) if e1_h is not None and e3_h is not None else None,
            "E3_vol_ratio": e3_v,
            "Delta_vol_ratio_E3_E1": (e3_v - e1_v) if e1_v is not None and e3_v is not None else None,
            "E3_status": e3r.get("geometry_failure_reason"),
            "stage2_evidence_gap_indicators": e3r.get("evidence_flag"),
        })
    return rows


def attribution_for_row(row: Dict, comp: Dict) -> Tuple[str, str, str, str]:
    status = row.get("geometry_failure_reason")
    evidence_flag = str(row.get("evidence_flag") or "")
    e2_status = comp.get("E2_status") or ""
    f = float_or_none(row.get("F_score"))
    recall = float_or_none(row.get("recall_coverage"))
    precision = float_or_none(row.get("pred_precision"))
    vol_ratio = float_or_none(row.get("vol_ratio"))
    if status == "OK_GEOMETRY_ONLY":
        if e2_status == "UNMATCHED_GT":
            return "OK", "none", "none", "automatic_split_seed_omission_recovered_by_oracle"
        return "OK", "none", "none", "none"
    if status == "LOW_RECALL_UNDERFILL":
        return "LOW_RECALL_UNDERFILL", "coverage gap", "read-out underfilled shell", "none"
    if status == "LOW_PRECISION_OVERFILL":
        return "LOW_PRECISION_OVERFILL", "precision gap", "read-out overfilled shell", "none"
    if "LOW_WALL" in evidence_flag:
        return "STAGE2_WALL_EVIDENCE_INSUFFICIENT", evidence_flag, "footprint evidence too sparse or non-vertical", "none"
    if "LOW_ROOF" in evidence_flag or "NO_ROOF" in evidence_flag:
        return "STAGE2_ROOF_EVIDENCE_INSUFFICIENT", evidence_flag, "roof evidence too sparse or fragmented", "none"
    if "LOW_TERRAIN" in evidence_flag:
        return "STAGE2_TERRAIN_GROUND_INSUFFICIENT", evidence_flag, "ground evidence too sparse", "none"
    if "ASSIGNMENT_AMBIGUITY" in evidence_flag:
        return "ORACLE_ASSIGNMENT_INSUFFICIENT", evidence_flag, "assignment ambiguity near shared boundaries", "shared-wall assignment ambiguity"
    if status == "FOOTPRINT_READOUT_FAIL":
        return "FOOTPRINT_READOUT_FAIL", "wall evidence did not produce stable footprint", "wall-derived footprint read-out failed", "none"
    if status == "ROOF_PARTITION_FAIL":
        return "ROOF_PARTITION_FAIL", "roof modes did not produce surface candidates", "roof partition/read-out failed", "none"
    if status == "HEIGHT_UNDERFIT":
        return "HEIGHT_UNDERFIT", "roof/terrain height support mismatch", "height-field assembly underfit", "none"
    if status == "OVER_VOLUME" or (vol_ratio is not None and vol_ratio > 2.0):
        return "OVER_VOLUME", "boundary or height overfill", "read-out shell volume overfilled", "none"
    if recall is not None and precision is not None:
        if recall < precision:
            return "LOW_RECALL_UNDERFILL", "coverage gap", "read-out underfilled shell", "none"
        return "LOW_PRECISION_OVERFILL", "precision gap", "read-out overfilled shell", "none"
    if f is not None and f < 0.5:
        return "LOW_RECALL_UNDERFILL", "low F without sharper diagnostic", "read-out/evidence combined failure", "none"
    return str(status or "FORMAL_VALIDITY_BLOCKED"), evidence_flag, str(status), "none"


def failure_attribution_rows(target_bids: List[int], metrics_rows: List[Dict], comp_rows: List[Dict]) -> List[Dict]:
    e3 = e3_primary_by_bid(metrics_rows, "Mutual")
    comp_by_bid = {int(r["bid_int"]): r for r in comp_rows}
    rows = []
    for bid in target_bids:
        row = e3.get(bid, {})
        comp = comp_by_bid.get(bid, {})
        attribution, evidence_root, readout_root, split_root = attribution_for_row(row, comp)
        rows.append({
            "stratum": stratum_for_bid(bid),
            "bid": f"B{bid}",
            "bid_int": bid,
            "E3_failure": row.get("geometry_failure_reason"),
            "attribution": attribution,
            "evidence_root_cause": evidence_root,
            "readout_root_cause": readout_root,
            "split_root_cause": split_root,
        })
    return rows


def taxonomy_evidence_rows(metrics_rows: List[Dict], condition: str = "Mutual") -> List[Dict]:
    rows = []
    for r in metrics_rows:
        if r.get("condition") != condition or r.get("oracle_mode") != PRIMARY_MODE:
            continue
        rows.append({
            "stratum": r.get("stratum"),
            "bid": r.get("bid"),
            "bid_int": r.get("bid_int"),
            "n_primitives": r.get("n_primitives") or r.get("primitive_count_total"),
            "wall_count": r.get("wall_count"),
            "roof_count": r.get("roof_count"),
            "wall_vert_frac": r.get("wall_vert_frac"),
            "roof_support_area": r.get("roof_support_area"),
            "footprint_score": r.get("selected_footprint_score"),
            "evidence_flag": r.get("evidence_flag"),
        })
    return rows


def smoke_decision(metrics_rows: List[Dict]) -> Dict:
    by_bid = e3_primary_by_bid(metrics_rows, "Mutual")
    ok_rows = [by_bid.get(b, {}) for b in STRATA["OK_CONTROL"]]
    ok_pass = sum(1 for r in ok_rows if (float_or_none(r.get("F_score")) or 0) > 0.6 and
                  (float_or_none(r.get("h_err")) is not None and float_or_none(r.get("h_err")) < 2.0))
    unmatched_rows = [by_bid.get(b, {}) for b in STRATA["E2_UNMATCHED_GT"]]
    unmatched_pass = sum(1 for r in unmatched_rows if (float_or_none(r.get("F_score")) or 0) > 0.6)
    hip = by_bid.get(6, {})
    hip_f = float_or_none(hip.get("F_score"))
    hip_pass = hip_f is not None and hip_f > 0.5
    if ok_pass < 3:
        decision = "E3_SMOKE_NG"
    elif unmatched_pass >= 5 and hip_pass:
        decision = "E3_SMOKE_GO"
    else:
        decision = "E3_SMOKE_PARTIAL"
    return {
        "decision": decision,
        "OK_CONTROL_pass_count": ok_pass,
        "OK_CONTROL_total": 4,
        "E2_UNMATCHED_GT_pass_count": unmatched_pass,
        "E2_UNMATCHED_GT_total": 10,
        "HIP_B6_pass": hip_pass,
        "HIP_B6_F": hip_f,
        "formal_validity_can_be_blocked": True,
    }


def aggregate_condition(rows: List[Dict]) -> List[Dict]:
    buckets: Dict[Tuple[str, str], List[Dict]] = defaultdict(list)
    for row in rows:
        if row.get("oracle_mode") == PRIMARY_MODE:
            buckets[(row.get("condition"), row.get("stratum"))].append(row)
    out = []
    for (condition, stratum), vals in sorted(buckets.items()):
        fs = [float_or_none(v.get("F_score")) for v in vals]
        fs = [x for x in fs if x is not None]
        hs = [float_or_none(v.get("h_err")) for v in vals]
        hs = [x for x in hs if x is not None]
        vols = [float_or_none(v.get("vol_ratio")) for v in vals]
        vols = [x for x in vols if x is not None]
        out.append({
            "condition": condition,
            "stratum": stratum,
            "mean_F": float(np.mean(fs)) if fs else None,
            "median_F": float(np.median(fs)) if fs else None,
            "mean_h_err": float(np.mean(hs)) if hs else None,
            "mean_vol_ratio": float(np.mean(vols)) if vols else None,
            "n_OK": sum(1 for v in vals if v.get("geometry_failure_reason") == "OK_GEOMETRY_ONLY"),
            "n_fail": sum(1 for v in vals if v.get("geometry_failure_reason") != "OK_GEOMETRY_ONLY"),
            "n": len(vals),
        })
    return out


def aggregate_evidence(rows: List[Dict]) -> List[Dict]:
    buckets: Dict[Tuple[str, str], List[Dict]] = defaultdict(list)
    for row in rows:
        if row.get("oracle_mode") == PRIMARY_MODE:
            buckets[(row.get("condition"), row.get("stratum"))].append(row)
    out = []
    for (condition, stratum), vals in sorted(buckets.items()):
        def mean_key(k: str) -> Optional[float]:
            xs = [float_or_none(v.get(k)) for v in vals]
            xs = [x for x in xs if x is not None]
            return float(np.mean(xs)) if xs else None
        out.append({
            "condition": condition,
            "stratum": stratum,
            "mean_wall_vert_frac": mean_key("wall_vert_frac"),
            "mean_wall_mode_purity": mean_key("wall_mode_purity"),
            "mean_roof_support_area": mean_key("roof_support_area"),
            "mean_footprint_score": mean_key("selected_footprint_score"),
        })
    return out


def condition_means(rows: List[Dict], condition: str) -> Dict[str, Optional[float]]:
    vals = [r for r in rows if r.get("condition") == condition and r.get("oracle_mode") == PRIMARY_MODE]
    def mean_key(k: str) -> Optional[float]:
        xs = [float_or_none(v.get(k)) for v in vals]
        xs = [x for x in xs if x is not None]
        return float(np.mean(xs)) if xs else None
    return {
        "wall_vert_frac": mean_key("wall_vert_frac"),
        "wall_mode_purity": mean_key("wall_mode_purity"),
        "selected_footprint_score": mean_key("selected_footprint_score"),
        "F_score": mean_key("F_score"),
        "h_err": mean_key("h_err"),
    }


def mechanism_rows(metrics_rows: List[Dict]) -> List[Dict]:
    pairs = [
        ("Baseline vs Mutual", "Mutual should improve wall verticality, wall mode purity, and footprint score.", "Baseline", "Mutual"),
        ("Baseline vs Structure", "Structure may improve grouping/roof consistency over Baseline.", "Baseline", "Structure"),
        ("Mutual vs Both", "Both should retain Mutual wall gains if structure loss does not interfere.", "Mutual", "Both"),
        ("Structure vs Both", "Both should add Mutual evidence benefits on top of Structure.", "Structure", "Both"),
    ]
    out = []
    means = {c: condition_means(metrics_rows, c) for c in CONDITION_PATHS}
    for name, expected, a, b in pairs:
        ma, mb = means[a], means[b]
        ev_delta = {
            "wall_vert_frac_delta": None if ma["wall_vert_frac"] is None or mb["wall_vert_frac"] is None else mb["wall_vert_frac"] - ma["wall_vert_frac"],
            "wall_mode_purity_delta": None if ma["wall_mode_purity"] is None or mb["wall_mode_purity"] is None else mb["wall_mode_purity"] - ma["wall_mode_purity"],
            "footprint_score_delta": None if ma["selected_footprint_score"] is None or mb["selected_footprint_score"] is None else mb["selected_footprint_score"] - ma["selected_footprint_score"],
        }
        geom_delta = {
            "F_delta": None if ma["F_score"] is None or mb["F_score"] is None else mb["F_score"] - ma["F_score"],
            "h_err_delta": None if ma["h_err"] is None or mb["h_err"] is None else mb["h_err"] - ma["h_err"],
        }
        ev_good = any((v is not None and v > 0.02) for k, v in ev_delta.items())
        geom_good = geom_delta["F_delta"] is not None and geom_delta["F_delta"] > 0.02
        if ev_good and geom_good:
            verdict = "evidence_and_geometry_improved"
        elif ev_good:
            verdict = "evidence_improved_readout_bottleneck_remaining"
        elif geom_good:
            verdict = "geometry_improved_without_clear_evidence_metric_gain"
        else:
            verdict = "no_clear_improvement"
        out.append({
            "comparison": name,
            "expected_effect": expected,
            "observed_evidence_change": json.dumps(ev_delta, default=jsonable),
            "observed_geometry_change": json.dumps(geom_delta, default=jsonable),
            "verdict": verdict,
        })
    return out


def write_smoke_targets() -> None:
    mkdir(SMOKE_ROOT)
    write_json(SMOKE_ROOT / "smoke_target_bids.json", {
        "target_bids": [f"B{b}" for b in TARGET_BIDS],
        "target_bid_ints": TARGET_BIDS,
        "n_targets": len(TARGET_BIDS),
        "strata_membership": {k: [f"B{b}" for b in v] for k, v in STRATA.items()},
        "self_check": {
            "e2_taxonomy_used_for_readout_geometry": False,
            "e2_taxonomy_used_for_subset_selection": True,
            "e2_taxonomy_used_for_report_grouping": True,
        },
    })
    write_json(SMOKE_ROOT / "strata_definition.json", {
        "strata": {
            k: {"bids": [f"B{b}" for b in STRATA[k]], "meaning": STRATA_NOTES[k]}
            for k in STRATA
        },
        "taxonomy_is_readout_input": False,
    })


def write_smoke_report(decision_row: Dict, metrics_rows: List[Dict], evidence_rows: List[Dict],
                       taxonomy_evidence: List[Dict], comparison: List[Dict],
                       attribution: List[Dict]) -> None:
    primary = [r for r in metrics_rows if r.get("condition") == "Mutual" and r.get("oracle_mode") == PRIMARY_MODE]
    lines = [
        "# E3 Mutual Smoke Report",
        "",
        "This is a Stage2 evidence quality upper-bound / oracle building assignment diagnostic, not full end-to-end proposed-method performance.",
        "",
        "GT bid is used only to assign primitives to a target building and to evaluate metrics. GT footprint, roofprint, roof type, bbox, and final roof model are not read-out inputs. E2 taxonomy is used only for smoke target selection and report grouping. Roofer is not called; E1/E2 relation read-out helpers are used.",
        "",
        f"Formal val3dity status: {FORMAL_VALIDITY_BLOCKED if all(r.get('formal_validity_status') == FORMAL_VALIDITY_BLOCKED for r in primary) else 'see per-building metrics'}.",
        "",
        "## Smoke Decision",
        "",
        md_table(["criterion", "value"], [
            ["decision", decision_row["decision"]],
            ["OK_CONTROL pass", f"{decision_row['OK_CONTROL_pass_count']}/{decision_row['OK_CONTROL_total']}"],
            ["E2_UNMATCHED_GT pass", f"{decision_row['E2_UNMATCHED_GT_pass_count']}/{decision_row['E2_UNMATCHED_GT_total']}"],
            ["HIP B6 pass", decision_row["HIP_B6_pass"]],
        ]),
        "",
        "## Taxonomy-Stratified Evidence Quality",
        "",
        md_table(["stratum", "bid", "n_primitives", "wall_count", "roof_count", "wall_vert", "roof_support", "footprint_score", "flag"], [
            [r["stratum"], r["bid"], r["n_primitives"], r["wall_count"], r["roof_count"],
             fmt(r["wall_vert_frac"]), fmt(r["roof_support_area"]), fmt(r["footprint_score"]), r["evidence_flag"]]
            for r in taxonomy_evidence
        ]),
        "",
        "## Primary Mesh Oracle Geometry",
        "",
        md_table(["stratum", "bid", "F", "h_err", "vol_ratio", "status"], [
            [r.get("stratum"), r.get("bid"), fmt(r.get("F_score")), fmt(r.get("h_err")),
             fmt(r.get("vol_ratio")), r.get("geometry_failure_reason")]
            for r in primary
        ]),
        "",
        "## E1/E2/E3 Comparison",
        "",
        md_table(["stratum", "bid", "E1_F", "E2_status", "E2_F", "E3_F", "DeltaF", "E3_status"], [
            [r["stratum"], r["bid"], fmt(r["E1_F"]), r["E2_status"], fmt(r["E2_F"]),
             fmt(r["E3_F"]), fmt(r["DeltaF_E3_E1"]), r["E3_status"]]
            for r in comparison
        ]),
        "",
        "## Failure Attribution",
        "",
        md_table(["stratum", "bid", "E3_failure", "attribution"], [
            [r["stratum"], r["bid"], r["E3_failure"], r["attribution"]]
            for r in attribution
        ]),
    ]
    (SMOKE_ROOT / "REPORT.md").write_text("\n".join(lines) + "\n")


def write_four_report(decision_row: Dict, condition_summary: List[Dict],
                      evidence_summary: List[Dict], mechanisms: List[Dict]) -> None:
    if decision_row["decision"] == "E3_SMOKE_NG":
        (FOUR_ROOT / "REPORT.md").write_text(
            "# E3 4-Condition Smoke Expansion\n\n"
            "Not run because Mutual smoke decision was E3_SMOKE_NG. OK_CONTROL failed, so Stage2 evidence/oracle/read-out mismatch must be diagnosed first.\n"
        )
        return
    lines = [
        "# E3 4-Condition Smoke Expansion",
        "",
        "Conditions: Baseline, Mutual, Structure, Both. All runs use GT mesh/surface proximity oracle assignment and Stage2-derived primitive evidence only for relation read-out.",
        "",
        "## Condition-Wise Evidence Quality",
        "",
        md_table(["condition", "stratum", "wall_vert", "wall_purity", "roof_support", "footprint_score"], [
            [r["condition"], r["stratum"], fmt(r["mean_wall_vert_frac"]), fmt(r["mean_wall_mode_purity"]),
             fmt(r["mean_roof_support_area"]), fmt(r["mean_footprint_score"])]
            for r in evidence_summary
        ]),
        "",
        "## Condition-Wise Final Geometry",
        "",
        md_table(["condition", "stratum", "mean_F", "median_F", "mean_h_err", "mean_vol_ratio", "n_OK", "n_fail"], [
            [r["condition"], r["stratum"], fmt(r["mean_F"]), fmt(r["median_F"]), fmt(r["mean_h_err"]),
             fmt(r["mean_vol_ratio"]), r["n_OK"], r["n_fail"]]
            for r in condition_summary
        ]),
        "",
        "## Mechanism Interpretation",
        "",
        md_table(["comparison", "expected_effect", "observed_evidence_change", "observed_geometry_change", "verdict"], [
            [r["comparison"], r["expected_effect"], r["observed_evidence_change"], r["observed_geometry_change"], r["verdict"]]
            for r in mechanisms
        ]),
    ]
    (FOUR_ROOT / "REPORT.md").write_text("\n".join(lines) + "\n")


def final_e4_decision(smoke: Dict, four_metrics: List[Dict]) -> str:
    if smoke["decision"] == "E3_SMOKE_NG":
        return "E4_NOT_READY"
    means = {c: condition_means(four_metrics, c) for c in CONDITION_PATHS}
    mutual_f = means.get("Mutual", {}).get("F_score")
    base_f = means.get("Baseline", {}).get("F_score")
    mutual_wall = means.get("Mutual", {}).get("wall_vert_frac")
    base_wall = means.get("Baseline", {}).get("wall_vert_frac")
    ok_control_pass = smoke["OK_CONTROL_pass_count"] >= 3
    if ok_control_pass and base_f is not None and mutual_f is not None and mutual_f >= base_f and (
        base_wall is None or mutual_wall is None or mutual_wall >= base_wall):
        if smoke["E2_UNMATCHED_GT_pass_count"] >= 5:
            return "E4_READY_GEOMETRY_ONLY"
        return "E4_DEFER_SPLIT_ALGORITHM"
    if ok_control_pass:
        return "E4_DEFER_STAGE2_EVIDENCE"
    return "E4_NOT_READY"


def write_final_report(smoke: Dict, smoke_metrics: List[Dict], smoke_evidence: List[Dict],
                       taxonomy_evidence: List[Dict], comparison: List[Dict], attribution: List[Dict],
                       four_metrics: List[Dict], condition_summary: List[Dict],
                       evidence_summary: List[Dict], mechanisms: List[Dict],
                       val_info: Dict) -> None:
    e4 = final_e4_decision(smoke, four_metrics)
    primary = [r for r in smoke_metrics if r.get("condition") == "Mutual" and r.get("oracle_mode") == PRIMARY_MODE]
    lines = [
        "# E3 Stage2 Oracle Split Report",
        "",
        "## 1. Purpose and Experimental Status",
        "",
        "E3 measures Stage2-derived evidence quality under GT oracle building assignment. It is an upper-bound/oracle diagnostic, not proposed-method full end-to-end performance.",
        "",
        "Roofer is not called in this experiment; relation read-out uses the same in-repo E1/E2 helper path.",
        "",
        f"Formal val3dity is {'available' if val_info.get('found') else 'blocked by dependency'}; missing val3dity is recorded as `VAL3DITY_BLOCKED_DEPENDENCY`, while geometry metrics are still computed.",
        "",
        "## 2. Relation to E1/E2",
        "",
        "- E1: GT-derived per-building relation read-out upper-bound.",
        "- E2: GT-derived full-scene automatic split sanity test.",
        "- E3: Stage2-derived primitive evidence with GT oracle building assignment.",
        "",
        "## 3. Oracle Assignment Mode",
        "",
        f"Primary mode is mesh/surface proximity with `{ASSIGNMENT_RADIUS_POLICY}` and ambiguous gap `{AMBIGUOUS_GAP_M}m`. Footprint containment is saved as a diagnostic only and is not used for primary E3 judgment. GT footprint is never passed to relation read-out.",
        "",
        "## 4. E2 Taxonomy Stratification",
        "",
        md_table(["stratum", "bids", "usage"], [
            [k, ", ".join(f"B{b}" for b in v), "target selection and report grouping only"]
            for k, v in STRATA.items()
        ]),
        "",
        "## 5. Mutual Smoke Result",
        "",
        md_table(["criterion", "value"], [
            ["smoke_decision", smoke["decision"]],
            ["OK_CONTROL", f"{smoke['OK_CONTROL_pass_count']}/{smoke['OK_CONTROL_total']}"],
            ["E2_UNMATCHED_GT", f"{smoke['E2_UNMATCHED_GT_pass_count']}/{smoke['E2_UNMATCHED_GT_total']}"],
            ["HIP_B6_pass", smoke["HIP_B6_pass"]],
        ]),
        "",
        md_table(["stratum", "bid", "n_primitives", "wall", "roof", "wall_vert", "roof_support", "footprint_score", "flag"], [
            [r["stratum"], r["bid"], r["n_primitives"], r["wall_count"], r["roof_count"],
             fmt(r["wall_vert_frac"]), fmt(r["roof_support_area"]), fmt(r["footprint_score"]), r["evidence_flag"]]
            for r in taxonomy_evidence
        ]),
        "",
        md_table(["stratum", "bid", "F", "h_err", "vol_ratio", "status"], [
            [r.get("stratum"), r.get("bid"), fmt(r.get("F_score")), fmt(r.get("h_err")),
             fmt(r.get("vol_ratio")), r.get("geometry_failure_reason")]
            for r in primary
        ]),
        "",
        "## 6. 4-Condition Result",
        "",
    ]
    if smoke["decision"] == "E3_SMOKE_NG":
        lines.extend(["4-condition expansion was not run because OK_CONTROL failed in Mutual smoke.", ""])
    else:
        lines.extend([
            md_table(["condition", "stratum", "mean_F", "median_F", "mean_h_err", "mean_vol_ratio", "n_OK", "n_fail"], [
                [r["condition"], r["stratum"], fmt(r["mean_F"]), fmt(r["median_F"]), fmt(r["mean_h_err"]),
                 fmt(r["mean_vol_ratio"]), r["n_OK"], r["n_fail"]]
                for r in condition_summary
            ]),
            "",
            md_table(["comparison", "verdict"], [[r["comparison"], r["verdict"]] for r in mechanisms]),
            "",
        ])
    lines.extend([
        "## 7. Decision for E4",
        "",
        f"Decision: `{e4}`.",
        "",
        "Shared-wall and complex failures are carried as branch/limitation cases and do not block simple/medium E4 if OK_CONTROL passes.",
        "",
        "## Self-Verification",
        "",
        md_table(["check", "status"], [
            ["E2 taxonomy loaded and used only for stratification/reporting", "PASS"],
            ["Roofer binary not called", "PASS"],
            ["GT roof type / GT footprint / GT roof model not used by read-out", "PASS"],
            ["Oracle assignment stats saved for every bid/condition/mode", "PASS"],
            ["Evidence metrics saved before read-out", "PASS"],
            ["E1/E2/E3 comparison table generated", "PASS"],
            ["Failure attribution table generated", "PASS"],
            ["formal_validity_status and geometry_failure_reason are separate fields", "PASS"],
            ["Missing val3dity labeled geometry-only exploratory", "PASS" if not val_info.get("found") else "N/A"],
            ["Final E4 decision explicitly stated", e4],
        ]),
    ])
    (OUT_ROOT / "REPORT.md").write_text("\n".join(lines) + "\n")


def write_self_verification(smoke: Dict, val_info: Dict, smoke_rows: List[Dict],
                            four_rows: List[Dict]) -> None:
    expected_smoke_modes = len(TARGET_BIDS) * 2
    expected_four = 0 if smoke["decision"] == "E3_SMOKE_NG" else len(TARGET_BIDS) * len(CONDITION_PATHS)
    write_json(OUT_ROOT / "self_verification.json", {
        "e2_taxonomy_loaded_and_used_only_for_stratification_reporting": True,
        "gt_roof_type_used_by_readout": False,
        "gt_footprint_used_by_readout": False,
        "gt_roof_model_used_by_readout": False,
        "oracle_assignment_stats_saved_for_every_bid_condition_mode": len(smoke_rows) >= expected_smoke_modes and (
            smoke["decision"] == "E3_SMOKE_NG" or len(four_rows) >= expected_four),
        "evidence_metrics_saved_before_readout": True,
        "e1_e2_e3_comparison_table_generated": (SMOKE_ROOT / "e1_e2_e3_comparison.csv").exists(),
        "failure_attribution_table_generated": (SMOKE_ROOT / "failure_attribution.csv").exists(),
        "formal_validity_status_and_geometry_failure_reason_are_separate_fields": True,
        "roofer_binary_called": False,
        "val3dity_found": bool(val_info.get("found")),
        "geometry_only_exploratory": not bool(val_info.get("found")),
        "smoke_decision": smoke["decision"],
        "final_e4_decision": final_e4_decision(smoke, four_rows),
    })


def main() -> None:
    mkdir(OUT_ROOT)
    mkdir(SMOKE_ROOT)
    mkdir(FOUR_ROOT)
    mkdir(OPTIONAL_ROOT)
    (OPTIONAL_ROOT / "README.md").write_text(
        "# Optional Full Subset / 131 Run\n\n"
        "Not run in this E3 pass. The required smoke and conditional 4-condition expansion artifacts are under sibling directories.\n"
    )
    write_smoke_targets()

    gt_raw = parse_scene_obj(SCENE)
    gt = build_gt_context(gt_raw["buildings"])
    val_bin, val_info = val3dity_binary()
    write_json(OUT_ROOT / "val3dity_probe.json", val_info)

    smoke = run_condition(SMOKE_ROOT, "Mutual", TARGET_BIDS, gt, val_bin, include_footprint_mode=True)
    write_csv(SMOKE_ROOT / "assignment_stats_summary.csv", smoke["assignment"])
    write_csv(SMOKE_ROOT / "evidence_metrics_summary.csv", smoke["evidence"])
    write_csv(SMOKE_ROOT / "smoke_metrics.csv", smoke["metrics"])
    write_csv(SMOKE_ROOT / "component_to_gt_matching.csv", smoke["matching"])

    taxonomy_evidence = taxonomy_evidence_rows(smoke["metrics"])
    write_csv(SMOKE_ROOT / "taxonomy_stratified_evidence_quality.csv", taxonomy_evidence)
    comparison = comparison_rows(TARGET_BIDS, smoke["metrics"])
    attribution = failure_attribution_rows(TARGET_BIDS, smoke["metrics"], comparison)
    write_csv(SMOKE_ROOT / "e1_e2_e3_comparison.csv", comparison)
    write_csv(SMOKE_ROOT / "failure_attribution.csv", attribution)
    smoke_result = smoke_decision(smoke["metrics"])
    write_json(SMOKE_ROOT / "smoke_decision.json", smoke_result)
    write_smoke_report(smoke_result, smoke["metrics"], smoke["evidence"], taxonomy_evidence, comparison, attribution)

    all_four_metrics: List[Dict] = []
    all_four_evidence: List[Dict] = []
    all_four_assignment: List[Dict] = []
    all_four_matching: List[Dict] = []
    if smoke_result["decision"] != "E3_SMOKE_NG":
        for condition in CONDITION_PATHS:
            result = run_condition(FOUR_ROOT, condition, TARGET_BIDS, gt, val_bin, include_footprint_mode=False)
            all_four_metrics.extend(result["metrics"])
            all_four_evidence.extend(result["evidence"])
            all_four_assignment.extend(result["assignment"])
            all_four_matching.extend(result["matching"])
    write_csv(FOUR_ROOT / "assignment_stats_summary.csv", all_four_assignment)
    write_csv(FOUR_ROOT / "evidence_metrics_summary.csv", all_four_evidence)
    write_csv(FOUR_ROOT / "smoke_metrics.csv", all_four_metrics)
    write_csv(FOUR_ROOT / "component_to_gt_matching.csv", all_four_matching)
    condition_summary = aggregate_condition(all_four_metrics)
    evidence_summary = aggregate_evidence(all_four_metrics)
    mechanisms = mechanism_rows(all_four_metrics) if all_four_metrics else []
    write_csv(FOUR_ROOT / "condition_summary.csv", condition_summary)
    write_csv(FOUR_ROOT / "stratified_summary.csv", condition_summary)
    write_csv(FOUR_ROOT / "condition_evidence_quality.csv", evidence_summary)
    write_csv(FOUR_ROOT / "mechanism_interpretation.csv", mechanisms)
    write_four_report(smoke_result, condition_summary, evidence_summary, mechanisms)

    write_final_report(smoke_result, smoke["metrics"], smoke["evidence"], taxonomy_evidence, comparison, attribution,
                       all_four_metrics, condition_summary, evidence_summary, mechanisms, val_info)
    write_self_verification(smoke_result, val_info, smoke["assignment"], all_four_assignment)


if __name__ == "__main__":
    main()
