"""E2: GT-derived full-scene automatic building split.

This is a geometry-only clean-evidence split sanity test.  The split stage sees
only scene-wide sampled evidence fields:

    points, normals, semantic class, support weight

GT building ids, GT footprints/roofprints/bboxes, roof type labels, and final
GT roof models are not used by the split or read-out stages.  GT is loaded only
after predicted components exist, for matching and evaluation.
"""
from __future__ import annotations

import csv
import json
import math
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
from scipy import ndimage
from scipy.optimize import linear_sum_assignment
from shapely.geometry import MultiPoint, Point, Polygon

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.phase2_synthesis.obj_gt import parse_scene_obj  # noqa: E402
import scripts.phase2_synthesis.p1_4a_relation_readout as rr  # noqa: E402
import scripts.phase2_synthesis.p1_4a_preflight_precision as pm  # noqa: E402
from scripts.phase2_synthesis.e1_gt_131_relation_readout import (  # noqa: E402
    eval_geometry as eval_readout_geometry,
    fmt,
    md_table,
    write_json,
)


SCENE = ROOT / "results/phase2_synthesis/scene.obj"
OUT_ROOT = ROOT / "results/stage3_typed_readout/E2_gt_fullscene_auto_split"
REPORT_PATH = OUT_ROOT / "REPORT.md"
SUMMARY_JSON = OUT_ROOT / "summary_metrics.json"
INSTANCE_CSV = OUT_ROOT / "instance_metrics.csv"
COMPONENT_CSV = OUT_ROOT / "component_metrics.csv"
MATCHING_CSV = OUT_ROOT / "component_to_gt_matching.csv"
RISK_CSV = OUT_ROOT / "risk_building_tracking.csv"
E1_SUMMARY = ROOT / "results/stage3_typed_readout/E1_gt_131_per_building/summary_metrics.json"

FORMAL_VALIDITY_STATUS = "VAL3DITY_BLOCKED_DEPENDENCY"
VAL3DITY_VALID = None

# Evidence-only split parameters.  These are fixed constants, not tuned from GT.
GRID_CELL_M = 0.25
ROOF_DILATE_ITERS = 3
WALL_BARRIER_DILATE_ITERS = 1
MIN_ROOF_SAMPLES = 20
MIN_SEED_AREA_M2 = 20.0
MAX_SEED_AREA_M2 = 1500.0
ATTACH_BUFFER_M = 0.80

MATCH_IOU_THRESHOLD = 0.25
OVERLAP_COVERAGE_THRESHOLD = 0.25
GO_INSTANCE_RECALL = 0.70
GO_INSTANCE_PRECISION = 0.70
GO_OVERMERGE_RATE = 0.20
GO_SIMPLE_MEDIUM_F_RATE = 0.60


@dataclass
class SplitComponent:
    pred_id: str
    label: int
    seed_polygon: Polygon
    roof_indices: np.ndarray
    wall_indices: np.ndarray
    ground_indices: np.ndarray
    bbox_min: np.ndarray
    bbox_max: np.ndarray
    roof_sample_count: int
    wall_sample_count: int
    ground_sample_count: int
    seed_area: float


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


def input_policy() -> Dict:
    return {
        "experiment_status": "geometry-only exploratory",
        "clean_evidence_split_sanity": True,
        "proposed_method_performance": False,
        "gt_building_id_used_for_split": False,
        "gt_building_id_used_for_readout": False,
        "gt_footprint_used_for_split": False,
        "gt_roofprint_used_for_split": False,
        "gt_bbox_used_for_split": False,
        "gt_roof_type_used_for_split": False,
        "gt_final_roof_model_used_for_split": False,
        "gt_used_for_matching_and_evaluation_only": True,
        "allowed_split_input_fields": [
            "x", "y", "z", "normal", "semantic_class", "support_weight",
        ],
        "formal_validity_status": FORMAL_VALIDITY_STATUS,
        "val3dity_valid": VAL3DITY_VALID,
    }


def generate_scene_evidence(buildings: List[Dict]) -> Dict:
    """Generate a single scene-wide evidence table without GT building ids.

    This intentionally does not call ``rr.generate_evidence`` because that E1
    helper seeds sampling with the GT building id for per-building reproducibility.
    Here the only deterministic seed is the scene-wide face ordinal.
    """
    rows = []
    face_ordinal = 0
    for building in buildings:
        for face in building["faces"]:
            samples = rr._sample_face(face, seed=50000 + face_ordinal)
            n = np.asarray(face["normal"], dtype=np.float64)
            n = n / (np.linalg.norm(n) + 1e-12)
            cls = int(face.get("semantic_class", 0))
            w = float(face["area"]) / max(len(samples), 1)
            rows.append({
                "points": samples,
                "normals": np.tile(n, (len(samples), 1)),
                "classes": np.full(len(samples), cls, dtype=np.int64),
                "weights": np.full(len(samples), w, dtype=np.float64),
            })
            face_ordinal += 1
    return {
        "points": np.concatenate([r["points"] for r in rows], axis=0),
        "normals": np.concatenate([r["normals"] for r in rows], axis=0),
        "classes": np.concatenate([r["classes"] for r in rows], axis=0),
        "weights": np.concatenate([r["weights"] for r in rows], axis=0),
    }


def evidence_counts(evidence: Dict) -> Dict:
    return {rr.CLASS_NAME[k]: int(np.sum(evidence["classes"] == k)) for k in (1, 2, 3)}


def point_mask_in_polygon(points_xz: np.ndarray, poly: Polygon, buffer_m: float) -> np.ndarray:
    if len(points_xz) == 0:
        return np.zeros(0, dtype=bool)
    geom = poly.buffer(buffer_m)
    minx, minz, maxx, maxz = geom.bounds
    rough = (
        (points_xz[:, 0] >= minx) & (points_xz[:, 0] <= maxx) &
        (points_xz[:, 1] >= minz) & (points_xz[:, 1] <= maxz)
    )
    out = np.zeros(len(points_xz), dtype=bool)
    for idx in np.where(rough)[0]:
        p = Point(float(points_xz[idx, 0]), float(points_xz[idx, 1]))
        out[idx] = geom.contains(p) or geom.touches(p)
    return out


def component_bbox(evidence: Dict, indices: Iterable[np.ndarray]) -> Tuple[np.ndarray, np.ndarray]:
    pts = np.concatenate([evidence["points"][idx] for idx in indices if len(idx)], axis=0)
    return pts.min(axis=0), pts.max(axis=0)


def automatic_split(evidence: Dict) -> Tuple[List[SplitComponent], Dict]:
    """Roof projected raster CCs, using wall evidence as scene-wide barriers."""
    points = evidence["points"]
    classes = evidence["classes"]
    roof_idx_all = np.where(classes == 1)[0]
    wall_idx_all = np.where(classes == 2)[0]
    ground_idx_all = np.where(classes == 3)[0]
    roof_xz = points[roof_idx_all][:, [0, 2]]
    wall_xz = points[wall_idx_all][:, [0, 2]]
    ground_xz = points[ground_idx_all][:, [0, 2]]

    origin = np.vstack([roof_xz, wall_xz, ground_xz]).min(axis=0) - 2.0
    roof_ij = np.floor((roof_xz - origin) / GRID_CELL_M).astype(np.int64)
    wall_ij = np.floor((wall_xz - origin) / GRID_CELL_M).astype(np.int64)
    shape = np.maximum(roof_ij.max(axis=0), wall_ij.max(axis=0)) + 3

    roof_grid = np.zeros((int(shape[0]), int(shape[1])), dtype=bool)
    wall_grid = np.zeros_like(roof_grid)
    roof_grid[roof_ij[:, 0], roof_ij[:, 1]] = True
    wall_grid[wall_ij[:, 0], wall_ij[:, 1]] = True
    roof_support_grid = roof_grid.copy()
    wall_barrier_grid = wall_grid.copy()
    if ROOF_DILATE_ITERS:
        roof_support_grid = ndimage.binary_dilation(
            roof_support_grid, structure=np.ones((3, 3), dtype=bool), iterations=ROOF_DILATE_ITERS)
    if WALL_BARRIER_DILATE_ITERS:
        wall_barrier_grid = ndimage.binary_dilation(
            wall_barrier_grid, structure=np.ones((3, 3), dtype=bool), iterations=WALL_BARRIER_DILATE_ITERS)
    split_grid = roof_support_grid & ~wall_barrier_grid
    labels, n_labels = ndimage.label(split_grid, structure=np.ones((3, 3), dtype=np.int8))
    roof_sample_labels = labels[roof_ij[:, 0], roof_ij[:, 1]]

    components: List[SplitComponent] = []
    filtered = Counter()
    for label in range(1, int(n_labels) + 1):
        local_roof = np.where(roof_sample_labels == label)[0]
        if len(local_roof) < MIN_ROOF_SAMPLES:
            filtered["min_roof_samples"] += 1
            continue
        cells = np.argwhere(labels == label)
        if len(cells) < 3:
            filtered["min_grid_cells"] += 1
            continue
        centers = origin + (cells.astype(np.float64) + 0.5) * GRID_CELL_M
        seed_poly = MultiPoint([tuple(c) for c in centers]).convex_hull
        if not isinstance(seed_poly, Polygon) or seed_poly.area <= 0:
            filtered["invalid_seed_polygon"] += 1
            continue
        if seed_poly.area < MIN_SEED_AREA_M2:
            filtered["min_seed_area"] += 1
            continue
        if seed_poly.area > MAX_SEED_AREA_M2:
            filtered["max_seed_area"] += 1
            continue

        wall_mask = point_mask_in_polygon(wall_xz, seed_poly, ATTACH_BUFFER_M)
        ground_mask = point_mask_in_polygon(ground_xz, seed_poly, ATTACH_BUFFER_M)
        roof_indices = roof_idx_all[local_roof]
        wall_indices = wall_idx_all[wall_mask]
        ground_indices = ground_idx_all[ground_mask]
        if len(wall_indices) < 3 or len(ground_indices) < 3:
            filtered["insufficient_attached_wall_or_ground"] += 1
            continue

        mn, mx = component_bbox(evidence, [roof_indices, wall_indices, ground_indices])
        pred_id = f"pred_{len(components):03d}"
        components.append(SplitComponent(
            pred_id=pred_id,
            label=label,
            seed_polygon=seed_poly,
            roof_indices=roof_indices,
            wall_indices=wall_indices,
            ground_indices=ground_indices,
            bbox_min=mn,
            bbox_max=mx,
            roof_sample_count=int(len(roof_indices)),
            wall_sample_count=int(len(wall_indices)),
            ground_sample_count=int(len(ground_indices)),
            seed_area=float(seed_poly.area),
        ))

    diag = {
        "algorithm": "roof_projection_raster_connected_components_with_wall_barriers",
        "grid_cell_m": GRID_CELL_M,
        "roof_dilate_iters": ROOF_DILATE_ITERS,
        "wall_barrier_dilate_iters": WALL_BARRIER_DILATE_ITERS,
        "min_roof_samples": MIN_ROOF_SAMPLES,
        "min_seed_area_m2": MIN_SEED_AREA_M2,
        "max_seed_area_m2": MAX_SEED_AREA_M2,
        "attach_buffer_m": ATTACH_BUFFER_M,
        "n_roof_samples": int(len(roof_idx_all)),
        "n_wall_samples": int(len(wall_idx_all)),
        "n_ground_samples": int(len(ground_idx_all)),
        "grid_shape": [int(shape[0]), int(shape[1])],
        "raw_grid_labels": int(n_labels),
        "n_predicted_components": len(components),
        "filtered_components": dict(filtered),
        "input_policy": input_policy(),
    }
    return components, diag


def component_evidence(evidence: Dict, comp: SplitComponent) -> Dict:
    indices = np.concatenate([comp.roof_indices, comp.wall_indices, comp.ground_indices])
    order = np.argsort(evidence["classes"][indices])
    indices = indices[order]
    return {
        "points": evidence["points"][indices],
        "normals": evidence["normals"][indices],
        "classes": evidence["classes"][indices],
        "weights": evidence["weights"][indices],
    }


def polygon_to_json(poly: Polygon) -> List[List[float]]:
    return [[float(x), float(z)] for x, z in list(poly.exterior.coords)[:-1]]


def write_component_split_payload(path: Path, comp: SplitComponent) -> None:
    write_json(path, {
        "pred_id": comp.pred_id,
        "split_label": int(comp.label),
        "seed_polygon_xz": polygon_to_json(comp.seed_polygon),
        "seed_area": comp.seed_area,
        "bbox_min": comp.bbox_min,
        "bbox_max": comp.bbox_max,
        "roof_sample_count": comp.roof_sample_count,
        "wall_sample_count": comp.wall_sample_count,
        "ground_sample_count": comp.ground_sample_count,
        "input_policy": input_policy(),
    })


def write_failure_payload(cdir: Path, comp: SplitComponent, reason: str, exc: Exception, stage: str) -> Dict:
    payload = {
        "pred_id": comp.pred_id,
        "pipeline_success": False,
        "failure_stage": stage,
        "geometry_failure_reason": reason,
        "exception_type": type(exc).__name__,
        "exception": str(exc),
        "traceback_tail": traceback.format_exc(limit=5),
        "formal_validity_status": FORMAL_VALIDITY_STATUS,
        "val3dity_valid": VAL3DITY_VALID,
        "seed_footprint_area": comp.seed_area,
        "roof_sample_count": comp.roof_sample_count,
        "wall_sample_count": comp.wall_sample_count,
        "ground_sample_count": comp.ground_sample_count,
        "input_policy": input_policy(),
    }
    write_json(cdir / "metrics.json", payload)
    return payload


def plot_component_overlay(cdir: Path, ev: Dict, footprint: Optional[Polygon]) -> None:
    fig, ax = plt.subplots(figsize=(5, 5))
    for cls, color, label in [(2, "#2D5FD7", "wall"), (1, "#DC2828", "roof"), (3, "#2DA04B", "ground")]:
        pts = ev["points"][ev["classes"] == cls][:, [0, 2]]
        if len(pts):
            ax.scatter(pts[:, 0], pts[:, 1], s=2, c=color, alpha=0.35, label=label)
    if footprint is not None and not footprint.is_empty:
        xy = np.asarray(list(footprint.exterior.coords), dtype=float)
        ax.plot(xy[:, 0], xy[:, 1], color="black", linewidth=1.5, label="read-out footprint")
    ax.set_aspect("equal", adjustable="box")
    ax.grid(True, linewidth=0.2, alpha=0.3)
    ax.legend(loc="best", fontsize=7)
    fig.tight_layout()
    fig.savefig(cdir / "fig_component_overlay.png", dpi=140)
    plt.close(fig)


def run_component_readout(evidence: Dict, comp: SplitComponent) -> Dict:
    cdir = OUT_ROOT / "components" / comp.pred_id
    mkdir(cdir)
    ev = component_evidence(evidence, comp)
    np.savez_compressed(cdir / "component_evidence.npz", **ev)
    rr.write_evidence_ply(cdir / "component_evidence.ply", ev)
    rr.write_evidence_stats(cdir / "evidence_stats.csv", ev)
    write_component_split_payload(cdir / "split_component.json", comp)
    footprint: Optional[Polygon] = None
    counts = evidence_counts(ev)
    try:
        if counts["roof"] < 3 or counts["wall"] < 3 or counts["ground"] < 3:
            raise RuntimeError(f"insufficient evidence counts: {counts}")
        wall_planes = rr.cluster_planes_from_evidence(ev, 2)
        roof_planes = rr.cluster_planes_from_evidence(ev, 1)
        ground_planes = rr.cluster_planes_from_evidence(ev, 3)
        if len(wall_planes) < 2 or len(roof_planes) < 1 or len(ground_planes) < 1:
            raise RuntimeError(
                f"insufficient plane candidates wall={len(wall_planes)} "
                f"roof={len(roof_planes)} ground={len(ground_planes)}"
            )
    except Exception as exc:
        plot_component_overlay(cdir, ev, None)
        return write_failure_payload(cdir, comp, "EVIDENCE_OR_PLANE_INSUFFICIENT", exc, "evidence")

    try:
        footprint, footprint_candidates, wall_segments = rr.build_footprint_candidates(ev, wall_planes)
        rr.write_footprint_graph_json(cdir / "footprint_graph.json", footprint, footprint_candidates, wall_segments)
        (cdir / "footprint_candidates.json").write_text(json.dumps({
            "selected_candidate_id": footprint_candidates[0]["id"],
            "candidates": footprint_candidates,
        }, indent=2, default=jsonable) + "\n")
        rr.write_footprint_plot(cdir / "footprint_candidates.png", footprint, footprint_candidates, ev)
    except Exception as exc:
        plot_component_overlay(cdir, ev, footprint)
        return write_failure_payload(cdir, comp, "FOOTPRINT_FAIL", exc, "footprint")

    try:
        graph_edges = rr.write_graph_json(cdir / "evidence_graph.json", wall_planes, roof_planes, ground_planes, wall_segments)
        roof_candidates = rr.roof_surface_candidates(roof_planes, footprint, ev)
        if not roof_candidates:
            raise RuntimeError("no roof surface candidates")
        write_json(cdir / "roof_surface_candidates.json", {
            "roof_surface_generation": "roof plane candidates clipped diagnostically; final shell uses relation height-field triangulation",
            "candidates": roof_candidates,
        })
        write_json(cdir / "roof_modes.json", {
            "roof_type_label_used": False,
            "roof_plane_candidates": [rr.plane_to_json(p) for p in roof_planes],
        })
        rr.write_roof_mode_plot(cdir / "roof_mode_plot.png", roof_planes)
    except Exception as exc:
        plot_component_overlay(cdir, ev, footprint)
        return write_failure_payload(cdir, comp, "ROOF_PARTITION_FAIL", exc, "roof_partition")

    try:
        faces, assembly_diag = rr.assemble_closed_shell(footprint, ev, roof_planes)
        city_diag = rr.faces_to_cityjson(faces, int(comp.pred_id.rsplit("_", 1)[1]), cdir / "relation_readout.city.json")
        selected = rr.selected_surfaces_payload(faces, assembly_diag, city_diag)
        write_json(cdir / "selected_surfaces.json", selected)
        archetype = rr.optional_roof_archetype(roof_planes, assembly_diag, ev)
        write_json(cdir / "optional_roof_archetype.json", archetype)
    except Exception as exc:
        plot_component_overlay(cdir, ev, footprint)
        return write_failure_payload(cdir, comp, "SHELL_ASSEMBLY_FAIL", exc, "shell_assembly")

    base = {
        "pred_id": comp.pred_id,
        "pipeline_success": True,
        "cityjson_path": str(cdir / "relation_readout.city.json"),
        "formal_validity_status": FORMAL_VALIDITY_STATUS,
        "val3dity_valid": VAL3DITY_VALID,
        "geometry_failure_reason": "PENDING_GT_MATCH",
        "seed_footprint_area": comp.seed_area,
        "readout_footprint_area": float(footprint.area),
        "roof_sample_count": comp.roof_sample_count,
        "wall_sample_count": comp.wall_sample_count,
        "ground_sample_count": comp.ground_sample_count,
        "n_wall_nodes": len(wall_planes),
        "n_roof_nodes": len(roof_planes),
        "n_ground_nodes": len(ground_planes),
        "n_relation_edges": len(graph_edges),
        "n_footprint_candidates": len(footprint_candidates),
        "selected_footprint_candidate": footprint_candidates[0]["id"],
        "selected_footprint_score": footprint_candidates[0]["score"],
        "n_roof_surfaces": int(selected["cityjson_diagnostics"]["surface_types"].get("RoofSurface", 0)),
        "optional_archetype": archetype["label"],
        "signed_volume": float(city_diag.get("signed_volume", float("nan"))),
        "input_policy": input_policy(),
    }
    write_json(cdir / "metrics_pre_match.json", base | {"cityjson_diagnostics": city_diag})
    plot_component_overlay(cdir, ev, footprint)
    return base


def gt_vertices(building: Dict) -> np.ndarray:
    return np.concatenate([f["vertices"] for f in building["faces"]], axis=0)


def pred_eval_geometry(row: Dict, comp: SplitComponent) -> Tuple[Optional[Polygon], np.ndarray]:
    cj_path = Path(row.get("cityjson_path", ""))
    if row.get("pipeline_success") and cj_path.exists():
        vertices, faces = pm.cityjson_faces(cj_path)
        fp = pm.footprint_from_cityjson_faces(faces)
        return fp, vertices
    return comp.seed_polygon, np.vstack([
        comp.bbox_min,
        comp.bbox_max,
    ])


def bbox_iou_vertices(a: np.ndarray, b: np.ndarray) -> float:
    return pm.bbox_iou(np.asarray(a, dtype=np.float64), np.asarray(b, dtype=np.float64))


def match_components_to_gt(readout_rows: List[Dict], components: List[SplitComponent],
                           buildings: List[Dict]) -> Tuple[List[Dict], Dict]:
    gt_fps = [pm.footprint_from_gt(b) for b in buildings]
    gt_vs = [gt_vertices(b) for b in buildings]
    pred_fps: List[Optional[Polygon]] = []
    pred_vs: List[np.ndarray] = []
    for row, comp in zip(readout_rows, components):
        fp, vertices = pred_eval_geometry(row, comp)
        pred_fps.append(fp)
        pred_vs.append(vertices)

    n_pred, n_gt = len(components), len(buildings)
    fp_iou = np.zeros((n_pred, n_gt), dtype=np.float64)
    bb_iou = np.zeros((n_pred, n_gt), dtype=np.float64)
    score = np.zeros((n_pred, n_gt), dtype=np.float64)
    for i in range(n_pred):
        for j in range(n_gt):
            fp_iou[i, j] = pm.polygon_iou(pred_fps[i], gt_fps[j])
            if math.isnan(fp_iou[i, j]):
                fp_iou[i, j] = 0.0
            bb_iou[i, j] = bbox_iou_vertices(pred_vs[i], gt_vs[j])
            if math.isnan(bb_iou[i, j]):
                bb_iou[i, j] = 0.0
            score[i, j] = fp_iou[i, j] + 0.05 * bb_iou[i, j]

    if n_pred and n_gt:
        row_ind, col_ind = linear_sum_assignment(-score)
    else:
        row_ind, col_ind = np.asarray([], dtype=int), np.asarray([], dtype=int)

    accepted: Dict[int, int] = {}
    for i, j in zip(row_ind, col_ind):
        if fp_iou[i, j] >= MATCH_IOU_THRESHOLD:
            accepted[int(i)] = int(j)

    matching_rows = []
    for i, comp in enumerate(components):
        j = accepted.get(i)
        best_j = int(np.argmax(score[i])) if n_gt else None
        matching_rows.append({
            "pred_id": comp.pred_id,
            "matched_gt_bid": int(buildings[j]["building_id"]) if j is not None else None,
            "match_IoU": float(fp_iou[i, j]) if j is not None else None,
            "match_score": float(score[i, j]) if j is not None else None,
            "bbox_IoU": float(bb_iou[i, j]) if j is not None else None,
            "best_gt_bid_before_threshold": int(buildings[best_j]["building_id"]) if best_j is not None else None,
            "best_footprint_IoU_before_threshold": float(fp_iou[i, best_j]) if best_j is not None else None,
            "best_bbox_IoU_before_threshold": float(bb_iou[i, best_j]) if best_j is not None else None,
            "iou_threshold": MATCH_IOU_THRESHOLD,
        })

    pred_overlaps: Dict[int, List[int]] = defaultdict(list)
    gt_overlaps: Dict[int, List[int]] = defaultdict(list)
    for i, p in enumerate(pred_fps):
        if p is None or p.is_empty or p.area <= 0:
            continue
        for j, g in enumerate(gt_fps):
            if g is None or g.is_empty or g.area <= 0:
                continue
            inter = float(p.intersection(g).area)
            if inter / max(float(g.area), 1e-9) >= OVERLAP_COVERAGE_THRESHOLD:
                pred_overlaps[i].append(j)
                gt_overlaps[j].append(i)

    overmerge_pred = [i for i, js in pred_overlaps.items() if len(js) > 1]
    oversplit_gt = [j for j, is_ in gt_overlaps.items() if len(is_) > 1]
    matched_gt = {j for j in accepted.values()}
    matched_pred = set(accepted.keys())
    instance = {
        "n_gt": n_gt,
        "n_pred": n_pred,
        "matched": len(accepted),
        "instance_recall": len(accepted) / max(n_gt, 1),
        "instance_precision": len(accepted) / max(n_pred, 1),
        "overmerge": len(overmerge_pred),
        "oversplit": len(oversplit_gt),
        "overmerge_rate": len(overmerge_pred) / max(n_pred, 1),
        "oversplit_rate": len(oversplit_gt) / max(n_gt, 1),
        "unmatched_gt": n_gt - len(matched_gt),
        "unmatched_pred": n_pred - len(matched_pred),
        "match_iou_threshold": MATCH_IOU_THRESHOLD,
        "overlap_coverage_threshold": OVERLAP_COVERAGE_THRESHOLD,
        "overmerge_pred_ids": [components[i].pred_id for i in overmerge_pred],
        "oversplit_gt_bids": [int(buildings[j]["building_id"]) for j in oversplit_gt],
    }
    return matching_rows, instance


def classify_component_geometry(row: Dict) -> str:
    if not row.get("pipeline_success"):
        return str(row.get("geometry_failure_reason", "PIPELINE_FAIL"))
    if row.get("matched_gt_bid") is None:
        return "UNMATCHED_PRED_COMPONENT"
    f = row.get("F_score")
    precision = row.get("pred_precision")
    recall = row.get("recall_coverage")
    vol_ratio = row.get("vol_ratio")
    if f is None or (isinstance(f, float) and math.isnan(f)):
        return "EVAL_FAIL"
    if f < 0.5:
        if precision is not None and recall is not None and precision < recall:
            return "LOW_PRECISION_OVERFILL"
        return "LOW_RECALL_UNDERFILL"
    if vol_ratio is not None and not math.isnan(float(vol_ratio)) and float(vol_ratio) > 2.0:
        return "LOW_PRECISION_OVERFILL"
    return "OK_GEOMETRY_ONLY"


def attach_gt_metrics(readout_rows: List[Dict], components: List[SplitComponent],
                      buildings: List[Dict], matching_rows: List[Dict]) -> List[Dict]:
    by_bid = {int(b["building_id"]): b for b in buildings}
    by_pred = {m["pred_id"]: m for m in matching_rows}
    final_rows = []
    for row, comp in zip(readout_rows, components):
        merged = dict(row)
        match = by_pred[comp.pred_id]
        merged.update(match)
        merged.setdefault("formal_validity_status", FORMAL_VALIDITY_STATUS)
        merged.setdefault("val3dity_valid", VAL3DITY_VALID)
        if merged.get("pipeline_success") and merged.get("matched_gt_bid") is not None:
            try:
                gt_building = by_bid[int(merged["matched_gt_bid"])]
                geom = eval_readout_geometry(
                    gt_building,
                    OUT_ROOT / "components" / comp.pred_id,
                    {"signed_volume": merged.get("signed_volume", float("nan"))},
                )
                merged.update(geom)
            except Exception as exc:
                merged["geometry_failure_reason"] = "EVAL_FAIL"
                merged["eval_exception"] = str(exc)
        merged["footprint_IoU"] = merged.get("match_IoU")
        merged["geometry_failure_reason"] = classify_component_geometry(merged)
        write_json(OUT_ROOT / "components" / comp.pred_id / "metrics.json", merged)
        final_rows.append(merged)
    return final_rows


def write_csv(path: Path, fields: List[str], rows: List[Dict]) -> None:
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fields})


def gt_touching_map(buildings: List[Dict]) -> Dict[int, int]:
    fps = {int(b["building_id"]): pm.footprint_from_gt(b) for b in buildings}
    out = {}
    for bid, fp in fps.items():
        out[bid] = sum(1 for other, ofp in fps.items() if other != bid and fp.distance(ofp) <= 0.05)
    return out


def risk_tracking(buildings: List[Dict], component_rows: List[Dict], instance: Dict) -> List[Dict]:
    e1_rows = []
    if E1_SUMMARY.exists():
        e1_rows = json.loads(E1_SUMMARY.read_text()).get("rows", [])
    e1_by_bid = {int(r["bid"]): r for r in e1_rows if "bid" in r}
    comp_by_gt = {int(r["matched_gt_bid"]): r for r in component_rows if r.get("matched_gt_bid") is not None}
    touching = gt_touching_map(buildings)
    rows = []
    for b in buildings:
        bid = int(b["building_id"])
        e1 = e1_by_bid.get(bid, {})
        comp = comp_by_gt.get(bid)
        if comp is None:
            status = "UNMATCHED_GT"
            pred_id = None
            e2_f = None
            comment = "not recovered by automatic split"
        else:
            pred_id = comp["pred_id"]
            e2_f = comp.get("F_score")
            status = "MATCHED_OK" if comp.get("geometry_failure_reason") == "OK_GEOMETRY_ONLY" else str(comp.get("geometry_failure_reason"))
            comment = "row-house/shared-wall context" if touching.get(bid, 0) else "isolated or low-touching context"
        rows.append({
            "bid": bid,
            "E1_failure_reason": e1.get("failure_reason", "E1_NOT_AVAILABLE"),
            "E1_F": e1.get("F_score"),
            "E2_split_status": status,
            "E2_matched_component": pred_id,
            "E2_F": e2_f,
            "comment": comment,
            "touching_neighbor_count_eval_only": touching.get(bid, 0),
        })
    return rows


def write_scene_graph(components: List[SplitComponent], split_diag: Dict) -> None:
    nodes = []
    edges = []
    for comp in components:
        nodes.append({
            "id": f"{comp.pred_id}_roof_seed",
            "node_type": "roof_evidence_node",
            "pred_id": comp.pred_id,
            "support_samples": comp.roof_sample_count,
            "support_area_proxy": comp.seed_area,
            "bbox_min": comp.bbox_min.tolist(),
            "bbox_max": comp.bbox_max.tolist(),
            "seed_polygon_xz": polygon_to_json(comp.seed_polygon),
        })
        nodes.append({
            "id": f"{comp.pred_id}_wall_support",
            "node_type": "wall_evidence_node",
            "pred_id": comp.pred_id,
            "support_samples": comp.wall_sample_count,
        })
        nodes.append({
            "id": f"{comp.pred_id}_ground_support",
            "node_type": "ground_support_node",
            "pred_id": comp.pred_id,
            "support_samples": comp.ground_sample_count,
        })
        edges.append({
            "type": "semantic_relation_roof_wall_attach",
            "nodes": [f"{comp.pred_id}_roof_seed", f"{comp.pred_id}_wall_support"],
            "pred_id": comp.pred_id,
        })
        edges.append({
            "type": "semantic_relation_roof_ground_support",
            "nodes": [f"{comp.pred_id}_roof_seed", f"{comp.pred_id}_ground_support"],
            "pred_id": comp.pred_id,
        })
    for i, a in enumerate(components):
        for b in components[i + 1:]:
            dist = float(a.seed_polygon.distance(b.seed_polygon))
            if dist <= 1.0:
                edges.append({
                    "type": "spatial_adjacency",
                    "nodes": [f"{a.pred_id}_roof_seed", f"{b.pred_id}_roof_seed"],
                    "distance_m": dist,
                })
    write_json(OUT_ROOT / "scene_evidence_graph.json", {
        "input_policy": input_policy(),
        "graph_representation": "aggregated evidence nodes; raw scene-wide samples are in scene_evidence.npz/ply",
        "split_diagnostics": split_diag,
        "nodes": nodes,
        "edges": edges,
        "summary": {
            "n_roof_evidence_nodes": len(components),
            "n_wall_evidence_nodes": len(components),
            "n_ground_support_nodes": len(components),
            "n_edges": len(edges),
            "n_spatial_adjacency_edges": sum(1 for e in edges if e["type"] == "spatial_adjacency"),
            "n_semantic_relation_edges": sum(1 for e in edges if e["type"].startswith("semantic_relation")),
        },
    })


def plot_split_components(evidence: Dict, components: List[SplitComponent]) -> None:
    fig, ax = plt.subplots(figsize=(9, 8))
    roof = evidence["points"][evidence["classes"] == 1][:, [0, 2]]
    ax.scatter(roof[:, 0], roof[:, 1], s=0.35, c="#b8b8b8", alpha=0.30, label="roof evidence")
    cmap = plt.get_cmap("tab20")
    for i, comp in enumerate(components):
        pts = evidence["points"][comp.roof_indices][:, [0, 2]]
        color = cmap(i % 20)
        ax.scatter(pts[:, 0], pts[:, 1], s=1.2, color=color, alpha=0.65)
        xy = np.asarray(list(comp.seed_polygon.exterior.coords), dtype=float)
        ax.plot(xy[:, 0], xy[:, 1], color=color, linewidth=0.5, alpha=0.75)
    ax.set_aspect("equal", adjustable="box")
    ax.set_title("E2 automatic split components (no GT overlay)")
    ax.grid(True, linewidth=0.2, alpha=0.25)
    fig.tight_layout()
    fig.savefig(OUT_ROOT / "split_components.png", dpi=180)
    plt.close(fig)


def plot_matching(buildings: List[Dict], component_rows: List[Dict], components: List[SplitComponent]) -> None:
    fig, ax = plt.subplots(figsize=(9, 8))
    for b in buildings:
        fp = pm.footprint_from_gt(b)
        if fp is not None and not fp.is_empty:
            xy = np.asarray(list(fp.exterior.coords), dtype=float)
            ax.plot(xy[:, 0], xy[:, 1], color="black", linewidth=0.35, alpha=0.45)
    by_pred = {r["pred_id"]: r for r in component_rows}
    for comp in components:
        row = by_pred[comp.pred_id]
        reason = row.get("geometry_failure_reason")
        if reason == "OK_GEOMETRY_ONLY":
            color = "#2DA04B"
        elif row.get("matched_gt_bid") is None:
            color = "#E6862A"
        else:
            color = "#D62728"
        fp, _vertices = pred_eval_geometry(row, comp)
        if fp is not None and not fp.is_empty:
            xy = np.asarray(list(fp.exterior.coords), dtype=float)
            ax.plot(xy[:, 0], xy[:, 1], color=color, linewidth=0.9, alpha=0.80)
    ax.set_aspect("equal", adjustable="box")
    ax.set_title("E2 split/merge matching overlay (GT used only for evaluation)")
    ax.grid(True, linewidth=0.2, alpha=0.25)
    fig.tight_layout()
    fig.savefig(OUT_ROOT / "split_merge_matching.png", dpi=180)
    plt.close(fig)


def decision(instance: Dict, component_rows: List[Dict]) -> Dict:
    matched_rows = [r for r in component_rows if r.get("matched_gt_bid") is not None]
    simple_medium = [
        r for r in matched_rows
        if r.get("matched_gt_type_eval_only") in {"flat", "gable", "tri-slope", None}
    ]
    # If type annotation was not attached, use all matched components as the conservative proxy.
    denom_rows = simple_medium if simple_medium else matched_rows
    f_pass = sum(1 for r in denom_rows if r.get("F_score") is not None and float(r.get("F_score")) > 0.5)
    f_rate = f_pass / max(len(denom_rows), 1)
    go = (
        instance["instance_recall"] >= GO_INSTANCE_RECALL and
        instance["instance_precision"] >= GO_INSTANCE_PRECISION and
        instance["overmerge_rate"] <= GO_OVERMERGE_RATE and
        f_rate >= GO_SIMPLE_MEDIUM_F_RATE
    )
    return {
        "geometry_only_go": bool(go),
        "decision": "E2_GO_STAGE2_ORACLE_SPLIT_E3_GEOMETRY_ONLY" if go else "E2_NG_REVIEW_SPLIT_FAILURES",
        "formal_decision": "FORMAL_VALIDITY_BLOCKED",
        "stage2_oracle_split_E3_can_proceed": bool(go),
        "stage2_oracle_split_E3_scope": "geometry_only_exploratory" if go else "blocked_pending_E2_review",
        "matched_simple_medium_F_gt_0p5_rate": f_rate,
        "go_thresholds": {
            "instance_recall": GO_INSTANCE_RECALL,
            "instance_precision": GO_INSTANCE_PRECISION,
            "overmerge_rate": GO_OVERMERGE_RATE,
            "matched_simple_medium_components_F_gt_0p5_rate": GO_SIMPLE_MEDIUM_F_RATE,
        },
    }


def attach_gt_type_eval_only(component_rows: List[Dict], buildings: List[Dict]) -> None:
    by_bid = {int(b["building_id"]): b.get("type") for b in buildings}
    for row in component_rows:
        bid = row.get("matched_gt_bid")
        row["matched_gt_type_eval_only"] = by_bid.get(int(bid)) if bid is not None else None


def write_report(instance: Dict, component_rows: List[Dict], risk_rows: List[Dict],
                 split_diag: Dict, dec: Dict, self_check: Dict) -> None:
    failure_dist = Counter(str(r.get("geometry_failure_reason", "UNKNOWN")) for r in component_rows)
    unmatched_gt = [r for r in risk_rows if r["E2_split_status"] == "UNMATCHED_GT"]
    row_house_failures = [
        r for r in risk_rows
        if r.get("touching_neighbor_count_eval_only", 0) > 0 and r["E2_split_status"] != "MATCHED_OK"
    ]
    matched_rows = [r for r in component_rows if r.get("matched_gt_bid") is not None]
    f_ok = sum(1 for r in matched_rows if r.get("F_score") is not None and float(r["F_score"]) > 0.5)
    lines = [
        "# E2 GT-derived Full-scene Automatic Building Split",
        "",
        "## 1. Experiment Status",
        "",
        "This is a clean-evidence split sanity, not proposed-method performance. The split/read-out input is scene-wide sampled geometry evidence only: position, normal, semantic class, and support weight.",
        "",
        "- GT building id, GT footprint, GT roofprint, GT bbox, GT roof type, and GT final roof model were not used as split/read-out input.",
        "- GT was used only after predicted components were generated, for component-to-building matching and geometry evaluation.",
        f"- Formal val3dity is blocked: `formal_validity_status={FORMAL_VALIDITY_STATUS}`, `val3dity_valid=null`.",
        "- Ninja or other visualization is not treated as validation pass.",
        f"- Output root: `{OUT_ROOT.relative_to(ROOT)}`",
        "",
        "## 2. Scene-wide Evidence Graph",
        "",
        f"- Scene evidence counts: roof={split_diag['n_roof_samples']}, wall={split_diag['n_wall_samples']}, ground={split_diag['n_ground_samples']}",
        f"- Aggregated graph: `{(OUT_ROOT / 'scene_evidence_graph.json').relative_to(ROOT)}`",
        f"- Split components: {instance['n_pred']} from {split_diag['raw_grid_labels']} raw roof-grid labels",
        f"- Split visualization: `{(OUT_ROOT / 'split_components.png').relative_to(ROOT)}`",
        f"- Split/merge matching visualization: `{(OUT_ROOT / 'split_merge_matching.png').relative_to(ROOT)}`",
        "",
        "## 3. Instance-level Metrics",
        "",
    ]
    lines.extend(md_table(
        ["n_gt", "n_pred", "matched", "instance_recall", "instance_precision", "overmerge", "oversplit", "unmatched_gt", "unmatched_pred"],
        [[
            instance["n_gt"],
            instance["n_pred"],
            instance["matched"],
            fmt(instance["instance_recall"], 3),
            fmt(instance["instance_precision"], 3),
            instance["overmerge"],
            instance["oversplit"],
            instance["unmatched_gt"],
            instance["unmatched_pred"],
        ]],
    ))
    lines.extend([
        "",
        f"- Match IoU threshold: {fmt(instance['match_iou_threshold'], 2)}",
        f"- Overmerge rate: {fmt(instance['overmerge_rate'], 3)}",
        f"- Oversplit rate: {fmt(instance['oversplit_rate'], 3)}",
        "",
        "## 4. Component-level Summary",
        "",
        f"- Component table: `{COMPONENT_CSV.relative_to(ROOT)}`",
        f"- Matching table: `{MATCHING_CSV.relative_to(ROOT)}`",
        f"- Matched components with F_score > 0.5: {f_ok}/{len(matched_rows)} ({fmt(f_ok / max(len(matched_rows), 1), 3)})",
        "",
    ])
    top_rows = sorted(component_rows, key=lambda r: (
        0 if r.get("geometry_failure_reason") != "OK_GEOMETRY_ONLY" else 1,
        str(r.get("pred_id")),
    ))[:20]
    lines.extend(md_table(
        ["pred_id", "matched_gt_bid", "match_IoU", "h_err", "recall", "precision", "F_score", "vol_ratio", "geometry_failure_reason"],
        [[
            r.get("pred_id"),
            "NA" if r.get("matched_gt_bid") is None else f"B{r.get('matched_gt_bid')}",
            fmt(r.get("match_IoU"), 3),
            fmt(r.get("h_err"), 3),
            fmt(r.get("recall_coverage"), 3),
            fmt(r.get("pred_precision"), 3),
            fmt(r.get("F_score"), 3),
            fmt(r.get("vol_ratio"), 3),
            r.get("geometry_failure_reason"),
        ] for r in top_rows],
    ))
    lines.extend([
        "",
        "## 5. Split/Merge Error Analysis",
        "",
    ])
    lines.extend(md_table(
        ["geometry_failure_reason", "n", "rate"],
        [[k, v, fmt(v / max(len(component_rows), 1), 3)] for k, v in failure_dist.most_common()],
    ))
    lines.extend([
        "",
        f"- Unmatched GT buildings: {len(unmatched_gt)}",
        f"- Shared-wall / row-house-context failures: {len(row_house_failures)}",
        f"- Overmerged predicted components: {', '.join(instance['overmerge_pred_ids'][:20]) if instance['overmerge_pred_ids'] else 'none'}",
        f"- Oversplit GT bids: {', '.join('B' + str(b) for b in instance['oversplit_gt_bids'][:30]) if instance['oversplit_gt_bids'] else 'none'}",
        "",
        "## 6. E1-risk Building Tracking",
        "",
        f"- Full tracking table: `{RISK_CSV.relative_to(ROOT)}`",
    ])
    risk_subset = [
        r for r in risk_rows
        if r["E1_failure_reason"] not in {"VAL3DITY_BLOCKED_DEPENDENCY", "E1_NOT_AVAILABLE"}
        or r["E2_split_status"] != "MATCHED_OK"
    ][:30]
    lines.extend(md_table(
        ["bid", "E1_failure_reason", "E1_F", "E2_split_status", "E2_component", "E2_F", "comment"],
        [[
            f"B{r['bid']}",
            r["E1_failure_reason"],
            fmt(r.get("E1_F"), 3),
            r["E2_split_status"],
            r.get("E2_matched_component") or "NA",
            fmt(r.get("E2_F"), 3),
            r["comment"],
        ] for r in risk_subset],
    ))
    lines.extend([
        "",
        "## 7. GO/NG For Geometry-only Exploratory",
        "",
        f"- Decision: `{dec['decision']}`",
        f"- Formal decision: `{dec['formal_decision']}`",
        f"- Stage2 oracle split E3 can proceed: `{dec['stage2_oracle_split_E3_can_proceed']}`",
        f"- E3 scope: `{dec['stage2_oracle_split_E3_scope']}`",
        f"- instance_recall >= 0.70: `{instance['instance_recall'] >= GO_INSTANCE_RECALL}` ({fmt(instance['instance_recall'], 3)})",
        f"- instance_precision >= 0.70: `{instance['instance_precision'] >= GO_INSTANCE_PRECISION}` ({fmt(instance['instance_precision'], 3)})",
        f"- overmerge_rate <= 0.20: `{instance['overmerge_rate'] <= GO_OVERMERGE_RATE}` ({fmt(instance['overmerge_rate'], 3)})",
        f"- matched simple/medium components with F_score > 0.5 >= 0.60: `{dec['matched_simple_medium_F_gt_0p5_rate'] >= GO_SIMPLE_MEDIUM_F_RATE}` ({fmt(dec['matched_simple_medium_F_gt_0p5_rate'], 3)})",
        "",
        "## 8. Self-verification",
        "",
    ])
    for key, value in self_check.items():
        status = "PASS" if value else "FAIL"
        lines.append(f"- {status}: {key}")
    lines.append("")
    REPORT_PATH.write_text("\n".join(lines) + "\n")


def self_verification(component_rows: List[Dict]) -> Dict:
    return {
        "GT building id not used for split input": input_policy()["gt_building_id_used_for_split"] is False,
        "GT footprint/roofprint not used for split input": (
            input_policy()["gt_footprint_used_for_split"] is False and
            input_policy()["gt_roofprint_used_for_split"] is False
        ),
        "All predicted components have read-out or failure_reason": all(
            r.get("pipeline_success") or r.get("geometry_failure_reason") for r in component_rows
        ),
        "Component-to-GT matching table generated": MATCHING_CSV.exists(),
        "Split/merge visualization generated": (OUT_ROOT / "split_merge_matching.png").exists(),
        "formal_validity_status and geometry_failure_reason are separate fields": all(
            "formal_validity_status" in r and "geometry_failure_reason" in r for r in component_rows
        ),
    }


def main() -> None:
    mkdir(OUT_ROOT)
    mkdir(OUT_ROOT / "components")
    gt = parse_scene_obj(SCENE, frame="obj")
    buildings = gt["buildings"]

    evidence = generate_scene_evidence(buildings)
    np.savez_compressed(OUT_ROOT / "scene_evidence.npz", **evidence)
    rr.write_evidence_ply(OUT_ROOT / "scene_evidence.ply", evidence)
    rr.write_evidence_stats(OUT_ROOT / "scene_evidence_stats.csv", evidence)

    components, split_diag = automatic_split(evidence)
    write_json(OUT_ROOT / "split_diagnostics.json", split_diag)
    write_scene_graph(components, split_diag)
    plot_split_components(evidence, components)

    readout_rows = []
    for comp in components:
        print(f"[E2] read-out {comp.pred_id} roof={comp.roof_sample_count} wall={comp.wall_sample_count} ground={comp.ground_sample_count}")
        readout_rows.append(run_component_readout(evidence, comp))

    matching_rows, instance = match_components_to_gt(readout_rows, components, buildings)
    component_rows = attach_gt_metrics(readout_rows, components, buildings, matching_rows)
    attach_gt_type_eval_only(component_rows, buildings)
    risk_rows = risk_tracking(buildings, component_rows, instance)
    dec = decision(instance, component_rows)

    write_csv(INSTANCE_CSV, [
        "n_gt", "n_pred", "matched", "instance_recall", "instance_precision",
        "overmerge", "oversplit", "unmatched_gt", "unmatched_pred",
        "overmerge_rate", "oversplit_rate", "match_iou_threshold",
    ], [instance])
    write_csv(MATCHING_CSV, [
        "pred_id", "matched_gt_bid", "match_IoU", "match_score", "bbox_IoU",
        "best_gt_bid_before_threshold", "best_footprint_IoU_before_threshold",
        "best_bbox_IoU_before_threshold", "iou_threshold",
    ], matching_rows)
    write_csv(COMPONENT_CSV, [
        "pred_id", "matched_gt_bid", "match_IoU", "h_err", "recall_coverage",
        "pred_precision", "F_score", "vol_ratio", "footprint_IoU",
        "geometry_failure_reason", "formal_validity_status", "val3dity_valid",
        "pipeline_success", "cityjson_path", "roof_sample_count",
        "wall_sample_count", "ground_sample_count", "seed_footprint_area",
        "readout_footprint_area", "optional_archetype",
    ], component_rows)
    write_csv(RISK_CSV, [
        "bid", "E1_failure_reason", "E1_F", "E2_split_status",
        "E2_matched_component", "E2_F", "comment", "touching_neighbor_count_eval_only",
    ], risk_rows)

    plot_matching(buildings, component_rows, components)
    self_check = self_verification(component_rows)
    write_json(OUT_ROOT / "self_verification.json", self_check)
    write_json(SUMMARY_JSON, {
        "experiment_status": "geometry-only exploratory clean-evidence split sanity",
        "input_policy": input_policy(),
        "split_diagnostics": split_diag,
        "instance_metrics": instance,
        "decision": dec,
        "self_verification": self_check,
        "component_rows": component_rows,
        "matching_rows": matching_rows,
        "risk_rows": risk_rows,
    })
    write_report(instance, component_rows, risk_rows, split_diag, dec, self_check)
    print(f"[E2] wrote {OUT_ROOT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
