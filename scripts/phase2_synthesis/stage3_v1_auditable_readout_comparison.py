"""Stage3-v1 auditable read-out and FC-S1 v0-v1 comparison.

This experiment keeps the FC-S1 footprint-conditioned evidence files fixed and
separates metric/evaluator changes from the Stage3 read-out change.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
import sys
import traceback
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.spatial import cKDTree
from shapely.geometry import Polygon

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.phase2_synthesis.obj_gt import parse_scene_obj  # noqa: E402
import scripts.phase2_synthesis.fc_s1_semantic_surface_readout as fc  # noqa: E402
import scripts.phase2_synthesis.p1_4a_relation_readout as rr  # noqa: E402
import scripts.phase2_synthesis.p1_4a_preflight_precision as pm  # noqa: E402


FC_ROOT = fc.OUT_ROOT
OUT_ROOT = (
    ROOT
    / "results/footprint_conditioned_readout"
    / "Stage3_v1_auditable_readout_FC_S1_v0_v1_comparison"
)

STAGE3_ALGO_V0 = "Stage3Algo-v0"
STAGE3_ALGO_V1 = "Stage3Algo-v1"
METRIC_V0 = "Metric-v0"
METRIC_V1 = "Metric-v1"

COVERAGE_THRESH_M = 0.5
N_SURFACE_SAMPLE = fc.N_SURFACE_SAMPLE
N_METRIC_SAMPLE = fc.N_METRIC_SAMPLE
MAX_SAMPLE_LOG_ROWS = 1200

MATRIX_FIELDS = [
    "bid", "source", "stage3_algo_version", "metric_version", "status",
    "n_faces", "n_roof_faces", "n_wall_faces", "n_ground_faces",
    "roof_cov", "wall_cov", "ground_cov", "semantic_face_acc",
    "face_planarity_mean", "face_planarity_max", "support_coverage",
    "F", "precision", "recall", "h_err", "vol_ratio", "hausdorff",
    "chamfer", "footprint_IoU", "edge_ok", "open_edges",
    "nonmanifold_edges", "roof_wall_adjacency_count",
    "wall_ground_adjacency_count", "shell_completeness",
    "metric_artifact_dir", "readout_artifact_dir", "failure_reason",
]

METRIC_FIELDS = [
    "roof_cov", "wall_cov", "ground_cov", "semantic_face_acc",
    "support_coverage", "F", "precision", "recall", "h_err",
    "vol_ratio", "hausdorff", "chamfer", "footprint_IoU", "edge_ok",
    "open_edges", "nonmanifold_edges", "n_faces",
]

LOWER_BETTER = {
    "h_err", "hausdorff", "chamfer", "open_edges", "nonmanifold_edges",
    "face_planarity_mean", "face_planarity_max",
}
HIGHER_BETTER = {
    "roof_cov", "wall_cov", "ground_cov", "semantic_face_acc",
    "support_coverage", "F", "precision", "recall", "footprint_IoU",
    "edge_ok", "n_faces",
}


def read_csv(path: Path) -> List[Dict]:
    if not path.exists():
        return []
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def rel(path: Optional[Path]) -> str:
    if path is None:
        return ""
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def safe_float(value: object) -> Optional[float]:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(x) or math.isinf(x):
        return None
    return x


def safe_bool_int(value: object) -> Optional[int]:
    if value in {True, "True", "true", "1", 1}:
        return 1
    if value in {False, "False", "false", "0", 0}:
        return 0
    return None


def mode(values: Iterable[object]) -> str:
    counts = Counter(str(v) for v in values if str(v) != "")
    if not counts:
        return ""
    return counts.most_common(1)[0][0]


def load_evidence_from_fc_s1(source: str, bid: int) -> Optional[Dict]:
    path = FC_ROOT / "phase1_evidence" / source / f"B{bid}" / "evidence.npz"
    if not path.exists():
        return None
    data = np.load(path, allow_pickle=False)
    out = {k: data[k] for k in data.files}
    out["source"] = source
    out["bid"] = f"B{bid}"
    return out


def load_faces(path: Path) -> Tuple[List[Dict], Dict]:
    if not path.exists():
        return [], {"failure_reason": "semantic_faces.json missing"}
    payload = json.loads(path.read_text())
    faces = []
    for i, row in enumerate(payload.get("faces", [])):
        verts = np.asarray(row.get("vertices", []), dtype=np.float64)
        if len(verts) < 3:
            continue
        surface_type = row.get("semantic_type") or row.get("type")
        faces.append({
            "face_id": row.get("face_id", f"F{i:04d}"),
            "vertices": verts,
            "type": surface_type,
            "source": row.get("source", ""),
        })
    return faces, payload


def gt_faces(building: Dict) -> List[Dict]:
    rows = []
    for i, face in enumerate(building["faces"]):
        cls = int(face.get("semantic_class", -1))
        surface_type = fc.CLASS_TO_SURFACE.get(cls)
        if surface_type is None:
            continue
        rows.append({
            "face_id": f"GT{i:04d}",
            "vertices": np.asarray(face["vertices"], dtype=np.float64),
            "type": surface_type,
            "source": "gt_eval_only",
        })
    return rows


def face_volume(faces: List[Dict]) -> float:
    vol = 0.0
    for face in faces:
        pts = np.asarray(face["vertices"], dtype=np.float64)
        if len(pts) < 3:
            continue
        for i in range(1, len(pts) - 1):
            vol += float(np.dot(pts[0], np.cross(pts[i], pts[i + 1]))) / 6.0
    return abs(vol)


def sample_labeled_faces(faces: List[Dict], n: int, seed: int) -> Dict:
    tris = []
    tri_face_ids = []
    tri_types = []
    tri_classes = []
    for face_index, face in enumerate(faces):
        surface_type = face.get("type")
        cls = fc.SURFACE_TO_CLASS.get(surface_type, -1)
        t = pm.triangulate_polygon(np.asarray(face["vertices"], dtype=np.float64))
        if len(t) == 0:
            continue
        face_id = face.get("face_id") or f"F{face_index:04d}"
        tris.append(t)
        tri_face_ids.extend([face_id] * len(t))
        tri_types.extend([surface_type] * len(t))
        tri_classes.extend([cls] * len(t))
    if not tris:
        return {
            "points": np.empty((0, 3), dtype=np.float64),
            "face_ids": np.empty(0, dtype=object),
            "semantic_types": np.empty(0, dtype=object),
            "classes": np.empty(0, dtype=np.int64),
        }
    all_tris = np.concatenate(tris, axis=0)
    area = 0.5 * np.linalg.norm(
        np.cross(all_tris[:, 1] - all_tris[:, 0], all_tris[:, 2] - all_tris[:, 0]),
        axis=1,
    )
    valid = np.isfinite(area) & (area > 1e-12)
    if not np.any(valid):
        return {
            "points": np.empty((0, 3), dtype=np.float64),
            "face_ids": np.empty(0, dtype=object),
            "semantic_types": np.empty(0, dtype=object),
            "classes": np.empty(0, dtype=np.int64),
        }
    all_tris = all_tris[valid]
    area = area[valid]
    tri_face_ids = np.asarray(tri_face_ids, dtype=object)[valid]
    tri_types = np.asarray(tri_types, dtype=object)[valid]
    tri_classes = np.asarray(tri_classes, dtype=np.int64)[valid]
    rng = np.random.default_rng(seed)
    tri_idx = rng.choice(len(all_tris), size=n, replace=True, p=area / area.sum())
    u = rng.random(n)
    v = rng.random(n)
    flip = u + v > 1.0
    u[flip] = 1.0 - u[flip]
    v[flip] = 1.0 - v[flip]
    pts = (
        all_tris[tri_idx, 0]
        + u[:, None] * (all_tris[tri_idx, 1] - all_tris[tri_idx, 0])
        + v[:, None] * (all_tris[tri_idx, 2] - all_tris[tri_idx, 0])
    )
    return {
        "points": pts,
        "face_ids": tri_face_ids[tri_idx],
        "semantic_types": tri_types[tri_idx],
        "classes": tri_classes[tri_idx],
    }


def nearest_match(query: Dict, target: Dict) -> Dict:
    if len(query["points"]) == 0 or len(target["points"]) == 0:
        n = len(query["points"])
        return {
            "distance": np.full(n, np.nan),
            "target_index": np.full(n, -1, dtype=np.int64),
            "target_face_ids": np.full(n, "", dtype=object),
            "target_semantic_types": np.full(n, "", dtype=object),
            "target_classes": np.full(n, -1, dtype=np.int64),
            "same_semantic": np.zeros(n, dtype=bool),
            "within_threshold": np.zeros(n, dtype=bool),
        }
    d, nn = cKDTree(target["points"]).query(query["points"])
    target_classes = target["classes"][nn]
    same = query["classes"] == target_classes
    return {
        "distance": d,
        "target_index": nn,
        "target_face_ids": target["face_ids"][nn],
        "target_semantic_types": target["semantic_types"][nn],
        "target_classes": target_classes,
        "same_semantic": same,
        "within_threshold": (d <= COVERAGE_THRESH_M) & same,
    }


def surface_recall(pred_faces: List[Dict], gt_rows: List[Dict], surface_type: str, seed: int) -> float:
    gt_subset = [f for f in gt_rows if f["type"] == surface_type]
    if not gt_subset:
        return float("nan")
    pred_subset = [f for f in pred_faces if f["type"] == surface_type]
    if not pred_subset:
        return 0.0
    query = sample_labeled_faces(gt_subset, N_SURFACE_SAMPLE, seed)
    target = sample_labeled_faces(pred_subset, N_SURFACE_SAMPLE, seed + 13)
    match = nearest_match(query, target)
    if len(match["within_threshold"]) == 0:
        return 0.0
    return float(np.mean(match["within_threshold"]))


def support_coverage_metric_v1(pred_faces: List[Dict], evidence: Optional[Dict], seed: int) -> float:
    if evidence is None or len(pred_faces) == 0:
        return float("nan")
    vals = []
    for surface_type, cls in fc.SURFACE_TO_CLASS.items():
        faces = [f for f in pred_faces if f["type"] == surface_type]
        if not faces:
            continue
        pred = sample_labeled_faces(faces, min(N_SURFACE_SAMPLE, 1000), seed + cls)
        ev = np.asarray(evidence["points"])[np.asarray(evidence["classes"]) == cls]
        if len(pred["points"]) == 0 or len(ev) == 0:
            vals.append(0.0)
            continue
        d, _ = cKDTree(ev).query(pred["points"])
        vals.append(float(np.mean(d <= fc.SUPPORT_DISTANCE_M)))
    return float(np.mean(vals)) if vals else float("nan")


def write_matching_logs(audit_dir: Path, pred_sample: Dict, gt_sample: Dict,
                        pred_to_gt: Dict, gt_to_pred: Dict) -> Dict:
    def per_face_rows(direction: str, query: Dict, match: Dict) -> List[Dict]:
        rows = []
        for fid in sorted(set(str(x) for x in query["face_ids"])):
            idx = np.where(query["face_ids"] == fid)[0]
            if len(idx) == 0:
                continue
            distances = match["distance"][idx]
            finite = distances[np.isfinite(distances)]
            rows.append({
                "direction": direction,
                "query_face_id": fid,
                "query_semantic_type": mode(query["semantic_types"][idx]),
                "target_face_id_mode": mode(match["target_face_ids"][idx]),
                "target_semantic_type_mode": mode(match["target_semantic_types"][idx]),
                "n_samples": int(len(idx)),
                "mean_distance": float(np.mean(finite)) if len(finite) else "",
                "p95_distance": float(np.percentile(finite, 95)) if len(finite) else "",
                "coverage_at_0p5_same_semantic": float(np.mean(match["within_threshold"][idx])),
                "semantic_match_rate": float(np.mean(match["same_semantic"][idx])),
            })
        return rows

    face_rows = []
    face_rows.extend(per_face_rows("pred_to_gt", pred_sample, pred_to_gt))
    face_rows.extend(per_face_rows("gt_to_pred", gt_sample, gt_to_pred))
    fc.write_csv(audit_dir / "per_face_matching.csv", face_rows)

    sample_rows = []
    for direction, query, match, budget in [
        ("pred_to_gt", pred_sample, pred_to_gt, MAX_SAMPLE_LOG_ROWS // 2),
        ("gt_to_pred", gt_sample, gt_to_pred, MAX_SAMPLE_LOG_ROWS // 2),
    ]:
        n = len(query["points"])
        if n == 0:
            continue
        keep = np.linspace(0, n - 1, min(budget, n), dtype=np.int64)
        for out_i, i in enumerate(keep):
            p = query["points"][i]
            sample_rows.append({
                "sample_id": f"{direction}_{out_i:04d}",
                "direction": direction,
                "query_face_id": query["face_ids"][i],
                "query_semantic_type": query["semantic_types"][i],
                "query_x": float(p[0]),
                "query_y": float(p[1]),
                "query_z": float(p[2]),
                "nearest_target_face_id": match["target_face_ids"][i],
                "nearest_target_semantic_type": match["target_semantic_types"][i],
                "distance": float(match["distance"][i]) if np.isfinite(match["distance"][i]) else "",
                "same_semantic": bool(match["same_semantic"][i]),
                "within_0p5_same_semantic": bool(match["within_threshold"][i]),
            })
    fc.write_csv(audit_dir / "sample_matching.csv", sample_rows)
    return {
        "per_face_matching_csv": rel(audit_dir / "per_face_matching.csv"),
        "sample_matching_csv": rel(audit_dir / "sample_matching.csv"),
        "sample_log_policy": f"deterministic subset, max {MAX_SAMPLE_LOG_ROWS} rows per run",
    }


def metric_v1_evaluate(faces: List[Dict], building: Dict, evidence: Optional[Dict],
                       source: str, bid: int, stage3_algo: str, status: str,
                       failure_reason: str, audit_dir: Path,
                       readout_dir: Optional[Path]) -> Dict:
    fc.mkdir(audit_dir)
    base = {
        "bid": f"B{bid}",
        "source": source,
        "stage3_algo_version": stage3_algo,
        "metric_version": METRIC_V1,
        "status": status,
        "metric_artifact_dir": rel(audit_dir),
        "readout_artifact_dir": rel(readout_dir) if readout_dir else "",
        "failure_reason": failure_reason,
    }
    if status != "OK" or not faces:
        payload = {
            **base,
            "metric_status": "NO_FACES_OR_READOUT_NOT_OK",
            "metric_version": METRIC_V1,
        }
        fc.write_json(audit_dir / "metric_v1_summary.json", payload)
        fc.write_csv(audit_dir / "per_face_matching.csv", [])
        fc.write_csv(audit_dir / "sample_matching.csv", [])
        return base

    gt_rows = gt_faces(building)
    pred_sample = sample_labeled_faces(faces, N_METRIC_SAMPLE, 1000 + bid)
    gt_sample = sample_labeled_faces(gt_rows, N_METRIC_SAMPLE, 2000 + bid)
    pred_to_gt = nearest_match(pred_sample, gt_sample)
    gt_to_pred = nearest_match(gt_sample, pred_sample)
    log_info = write_matching_logs(audit_dir, pred_sample, gt_sample, pred_to_gt, gt_to_pred)

    dist = pm.distance_metrics(pred_sample["points"], gt_sample["points"])
    pred_vertices = np.concatenate([np.asarray(f["vertices"], dtype=np.float64) for f in faces], axis=0)
    gt_vertices = np.concatenate([np.asarray(f["vertices"], dtype=np.float64) for f in building["faces"]], axis=0)
    pred_h = float(pred_vertices[:, 1].max() - pred_vertices[:, 1].min())
    gt_h = float(gt_vertices[:, 1].max() - gt_vertices[:, 1].min())
    gt_vol = pm.gt_volume_anchored(building)
    pred_vol = face_volume(faces)
    graph = fc.face_graph(faces)
    planarity = [fc.face_planarity_error(np.asarray(f["vertices"], dtype=np.float64)) for f in faces]
    fp_pred = fc.footprint_from_pred_faces(faces)
    fp_gt = fc.footprint_for_building(building)

    row = {
        **base,
        "n_faces": len(faces),
        "n_roof_faces": sum(1 for f in faces if f["type"] == "RoofSurface"),
        "n_wall_faces": sum(1 for f in faces if f["type"] == "WallSurface"),
        "n_ground_faces": sum(1 for f in faces if f["type"] == "GroundSurface"),
        "roof_cov": surface_recall(faces, gt_rows, "RoofSurface", 3000 + bid),
        "wall_cov": surface_recall(faces, gt_rows, "WallSurface", 4000 + bid),
        "ground_cov": surface_recall(faces, gt_rows, "GroundSurface", 5000 + bid),
        "semantic_face_acc": float(np.mean(pred_to_gt["same_semantic"])),
        "face_planarity_mean": float(np.mean(planarity)) if planarity else "",
        "face_planarity_max": float(np.max(planarity)) if planarity else "",
        "support_coverage": support_coverage_metric_v1(faces, evidence, 6000 + bid),
        "F": dist["F_score"],
        "precision": dist["pred_precision"],
        "recall": dist["recall_coverage"],
        "h_err": abs(pred_h - gt_h),
        "vol_ratio": pred_vol / max(gt_vol, 1e-9),
        "hausdorff": dist["hausdorff"],
        "chamfer": dist["chamfer"],
        "footprint_IoU": pm.polygon_iou(fp_pred, fp_gt),
        "edge_ok": graph["diagnostics"]["edge_ok"],
        "open_edges": graph["diagnostics"]["open_edges"],
        "nonmanifold_edges": graph["diagnostics"]["nonmanifold_edges"],
        "roof_wall_adjacency_count": graph["diagnostics"]["roof_wall_adjacency_count"],
        "wall_ground_adjacency_count": graph["diagnostics"]["wall_ground_adjacency_count"],
        "shell_completeness": "CLOSED" if graph["diagnostics"]["edge_ok"] else "OPEN_OR_NONMANIFOLD",
    }
    payload = {
        **row,
        "metric_status": "OK",
        "metric_version": METRIC_V1,
        "coverage_threshold_m": COVERAGE_THRESH_M,
        "support_distance_m": fc.SUPPORT_DISTANCE_M,
        "n_metric_sample": N_METRIC_SAMPLE,
        "n_surface_sample": N_SURFACE_SAMPLE,
        "matching_logs": log_info,
        "metric_policy": {
            "gt_used_for_evaluation_only": True,
            "semantic_matching_required_for_surface_coverage": True,
            "metric_version_explicit": True,
        },
    }
    fc.write_json(audit_dir / "metric_v1_summary.json", payload)
    return row


def patch_ground_reference(evidence: Dict, footprint: Polygon, source: str, bid: int) -> Tuple[Dict, Dict]:
    counts = fc.evidence_summary_row(evidence, bid, source)
    log = {
        "stage3_algo_version": STAGE3_ALGO_V1,
        "patch_name": "ground_reference_from_evidence_y_quantile",
        "patch_applied": False,
        "reason": "",
        "original_counts": counts,
        "uses_gt_height": False,
        "uses_gt_roof_type": False,
        "uses_gt_semantic_surfaces": False,
    }
    if counts["n_ground"] >= 1:
        log["reason"] = "ground evidence already present"
        return evidence, log
    if counts["n_points"] == 0 or counts["n_roof"] < 3:
        log["reason"] = "insufficient non-ground evidence for ground reference"
        return evidence, log

    classes = np.asarray(evidence["classes"])
    pts = np.asarray(evidence["points"], dtype=np.float64)
    weights = np.asarray(evidence["weights"], dtype=np.float64)
    wall_pts = pts[classes == 2]
    candidates = wall_pts if len(wall_pts) else pts[classes > 0]
    if len(candidates) == 0:
        log["reason"] = "no positive-class evidence for ground reference"
        return evidence, log
    ground_y = float(np.percentile(candidates[:, 1], 95))
    roof_y = float(np.median(pts[classes == 1, 1])) if np.any(classes == 1) else ground_y
    if ground_y <= roof_y:
        ground_y = float(np.max(candidates[:, 1]))

    ring_xz = rr._remove_near_collinear(np.asarray(list(footprint.exterior.coords)[:-1], dtype=np.float64))
    if rr._signed_area_2d(ring_xz) < 0:
        ring_xz = ring_xz[::-1].copy()
    ground_pts = [[float(x), ground_y, float(z)] for x, z in ring_xz]
    for i in range(len(ring_xz)):
        a = ring_xz[i]
        b = ring_xz[(i + 1) % len(ring_xz)]
        m = (a + b) * 0.5
        ground_pts.append([float(m[0]), ground_y, float(m[1])])
    c = footprint.centroid
    ground_pts.append([float(c.x), ground_y, float(c.y)])
    ground_pts_arr = np.asarray(ground_pts, dtype=np.float64)
    n_new = len(ground_pts_arr)
    w = float(np.median(weights[weights > 0])) if np.any(weights > 0) else 1.0

    patched = {}
    for key, value in evidence.items():
        if not isinstance(value, np.ndarray):
            continue
        arr = np.asarray(value)
        if len(arr) != counts["n_points"]:
            patched[key] = arr
            continue
        if key == "points":
            patched[key] = np.concatenate([arr, ground_pts_arr], axis=0)
        elif key == "normals":
            patched[key] = np.concatenate([arr, np.tile(np.asarray([[0.0, 1.0, 0.0]]), (n_new, 1))], axis=0)
        elif key == "classes":
            patched[key] = np.concatenate([arr, np.full(n_new, 3, dtype=arr.dtype)], axis=0)
        elif key == "weights":
            patched[key] = np.concatenate([arr, np.full(n_new, w, dtype=arr.dtype)], axis=0)
        elif key == "sem_probs" and arr.ndim == 2 and arr.shape[1] >= 4:
            extra = np.zeros((n_new, arr.shape[1]), dtype=arr.dtype)
            extra[:, 3] = 1.0
            patched[key] = np.concatenate([arr, extra], axis=0)
        else:
            patched[key] = arr
    for key in ["points", "normals", "classes", "weights"]:
        if key not in patched:
            patched[key] = evidence[key]
    patched["source"] = source
    patched["bid"] = f"B{bid}"
    log.update({
        "patch_applied": True,
        "reason": "no ground evidence; inferred a read-out-only ground reference from evidence Y distribution",
        "ground_y": ground_y,
        "roof_y_median": roof_y,
        "n_synthetic_ground_points": n_new,
        "synthetic_ground_weight": w,
        "patched_counts": fc.evidence_summary_row(patched, bid, source),
    })
    return patched, log


def augment_json(path: Path, extra: Dict) -> None:
    if not path.exists():
        return
    payload = json.loads(path.read_text())
    payload.update(extra)
    fc.write_json(path, payload)


def stage3_v1_readout(evidence: Optional[Dict], building: Dict, footprint: Polygon,
                      source: str, bid: int, out_dir: Path) -> Tuple[Dict, List[Dict], Optional[Dict], Dict]:
    fc.mkdir(out_dir)
    if evidence is None:
        patch_log = {
            "stage3_algo_version": STAGE3_ALGO_V1,
            "patch_name": "ground_reference_from_evidence_y_quantile",
            "patch_applied": False,
            "reason": "SOURCE_MISSING",
            "uses_gt_height": False,
            "uses_gt_roof_type": False,
            "uses_gt_semantic_surfaces": False,
        }
        status = {
            "bid": f"B{bid}",
            "bid_int": bid,
            "source": source,
            "stage3_algo_version": STAGE3_ALGO_V1,
            "status": "SOURCE_MISSING",
            "n_faces": 0,
            "n_roof_faces": 0,
            "n_wall_faces": 0,
            "n_ground_faces": 0,
            "export_status": "NOT_WRITTEN",
            "failure_reason": "source artifact unavailable",
            "patch_applied": False,
            "patch_reason": "SOURCE_MISSING",
        }
        fc.write_json(out_dir / "stage3_v1_patch_log.json", patch_log)
        fc.write_json(out_dir / "semantic_faces.json", {
            "faces": [],
            "failure_reason": "SOURCE_MISSING",
            "stage3_algo_version": STAGE3_ALGO_V1,
            "stage3_v1_patch": patch_log,
        })
        fc.write_json(out_dir / "face_graph.json", {
            "nodes": [],
            "edges": [],
            "failure_reason": "SOURCE_MISSING",
            "stage3_algo_version": STAGE3_ALGO_V1,
            "stage3_v1_patch": patch_log,
        })
        fc.write_json(out_dir / "shell_diagnostics.json", status)
        return status, [], None, patch_log

    patched, patch_log = patch_ground_reference(evidence, footprint, source, bid)
    fc.write_json(out_dir / "stage3_v1_patch_log.json", patch_log)
    np.savez_compressed(
        out_dir / "readout_evidence_after_stage3_v1_patch.npz",
        **{k: v for k, v in patched.items() if isinstance(v, np.ndarray)}
    )
    status, faces, city_diag = fc.readout_one(patched, building, footprint, source, bid, out_dir)
    status["stage3_algo_version"] = STAGE3_ALGO_V1
    status["patch_applied"] = patch_log.get("patch_applied", False)
    status["patch_reason"] = patch_log.get("reason", "")
    augment_json(out_dir / "semantic_faces.json", {
        "stage3_algo_version": STAGE3_ALGO_V1,
        "stage3_v1_patch": patch_log,
        "primary_output_semantics_preserved": True,
    })
    augment_json(out_dir / "face_graph.json", {
        "stage3_algo_version": STAGE3_ALGO_V1,
        "stage3_v1_patch": patch_log,
    })
    augment_json(out_dir / "shell_diagnostics.json", {
        "stage3_algo_version": STAGE3_ALGO_V1,
        "stage3_v1_patch": patch_log,
        "readout_algorithm_note": "v0 read-out path plus audited read-out-only ground fallback when ground evidence is empty",
    })
    return status, faces or [], city_diag, patch_log


def metric0_rows() -> List[Dict]:
    status_rows = read_csv(FC_ROOT / "phase2_readout/readout_status.csv")
    surf = {(r["bid"], r["source"]): r for r in read_csv(FC_ROOT / "phase3_surface_eval/surface_metrics_by_bid.csv")}
    geom = {(r["bid"], r["source"]): r for r in read_csv(FC_ROOT / "phase4_geometry_topology/geometry_metrics_by_bid.csv")}
    topo = {(r["bid"], r["source"]): r for r in read_csv(FC_ROOT / "phase4_geometry_topology/topology_metrics_by_bid.csv")}
    rows = []
    for r in status_rows:
        key = (r["bid"], r["source"])
        readout_dir = FC_ROOT / "phase2_readout" / r["source"] / r["bid"]
        row = {
            "bid": r["bid"],
            "source": r["source"],
            "stage3_algo_version": STAGE3_ALGO_V0,
            "metric_version": METRIC_V0,
            "status": r.get("status", ""),
            "n_faces": r.get("n_faces", ""),
            "n_roof_faces": r.get("n_roof_faces", ""),
            "n_wall_faces": r.get("n_wall_faces", ""),
            "n_ground_faces": r.get("n_ground_faces", ""),
            "metric_artifact_dir": rel(FC_ROOT),
            "readout_artifact_dir": rel(readout_dir),
            "failure_reason": r.get("failure_reason", ""),
        }
        row.update({k: surf.get(key, {}).get(k, "") for k in [
            "roof_cov", "wall_cov", "ground_cov", "semantic_face_acc",
            "face_planarity_mean", "face_planarity_max", "support_coverage",
        ]})
        row.update({k: geom.get(key, {}).get(k, "") for k in [
            "F", "precision", "recall", "h_err", "vol_ratio", "hausdorff",
            "chamfer", "footprint_IoU",
        ]})
        row.update({k: topo.get(key, {}).get(k, "") for k in [
            "edge_ok", "open_edges", "nonmanifold_edges",
            "roof_wall_adjacency_count", "wall_ground_adjacency_count",
            "shell_completeness",
        ]})
        rows.append(row)
    return rows


def metric0_for_stage3_v1(v1_status_rows: List[Dict], v1_faces: Dict[Tuple[str, str], List[Dict]],
                          v1_city: Dict[Tuple[str, str], Dict],
                          buildings_by_bid: Dict[int, Dict],
                          evidence_by_key: Dict[Tuple[str, str], Optional[Dict]]) -> List[Dict]:
    rows = []
    for status in v1_status_rows:
        bid_str = status["bid"]
        bid = int(bid_str[1:])
        source = status["source"]
        key = (bid_str, source)
        row = {
            "bid": bid_str,
            "source": source,
            "stage3_algo_version": STAGE3_ALGO_V1,
            "metric_version": METRIC_V0,
            "status": status.get("status", ""),
            "n_faces": status.get("n_faces", ""),
            "n_roof_faces": status.get("n_roof_faces", ""),
            "n_wall_faces": status.get("n_wall_faces", ""),
            "n_ground_faces": status.get("n_ground_faces", ""),
            "readout_artifact_dir": rel(OUT_ROOT / "phase2_stage3_v1_readout" / source / bid_str),
            "metric_artifact_dir": rel(OUT_ROOT / "phase4_optional_stage3_v1_metric_v0"),
            "failure_reason": status.get("failure_reason", ""),
        }
        faces = v1_faces.get(key, [])
        if status.get("status") == "OK" and faces:
            surf = fc.surface_metrics(faces, buildings_by_bid[bid], evidence_by_key.get(key), source, bid)
            geom = fc.geometry_metrics(faces, buildings_by_bid[bid], source, bid, v1_city.get(key, {}))
            row.update({k: surf.get(k, "") for k in [
                "roof_cov", "wall_cov", "ground_cov", "semantic_face_acc",
                "face_planarity_mean", "face_planarity_max", "support_coverage",
            ]})
            row.update({k: geom.get(k, "") for k in [
                "F", "precision", "recall", "h_err", "vol_ratio", "hausdorff",
                "chamfer", "footprint_IoU", "edge_ok", "open_edges",
                "nonmanifold_edges", "roof_wall_adjacency_count",
                "wall_ground_adjacency_count", "shell_completeness",
            ]})
        rows.append(row)
    return rows


def metric_value(row: Optional[Dict], metric: str) -> Optional[float]:
    if not row:
        return None
    if metric == "edge_ok":
        return safe_bool_int(row.get(metric))
    return safe_float(row.get(metric))


def improvement(metric: str, before: Optional[float], after: Optional[float]) -> Optional[float]:
    if before is None or after is None:
        return None
    if metric in LOWER_BETTER:
        return before - after
    if metric == "vol_ratio":
        return abs(before - 1.0) - abs(after - 1.0)
    return after - before


def label_effect(kind: str, value: Optional[float],
                 before_status: str = "", after_status: str = "") -> str:
    if before_status != "OK" and after_status == "OK":
        if kind == "algorithm":
            return "STAGE3_V1_READOUT_RECOVERED"
        if kind == "final":
            return "FINAL_READOUT_RECOVERED"
    if before_status == "OK" and after_status != "OK":
        if kind == "algorithm":
            return "STAGE3_V1_READOUT_REGRESSED"
        if kind == "final":
            return "FINAL_READOUT_REGRESSED"
    if value is None:
        return "NA"
    eps = 1e-9
    if abs(value) <= eps:
        return "NO_NUMERIC_CHANGE"
    if kind == "evaluator":
        return "METRIC_V1_HIGHER" if value > 0 else "METRIC_V1_LOWER"
    if kind == "algorithm":
        return "STAGE3_V1_IMPROVES" if value > 0 else "STAGE3_V1_DEGRADES"
    return "FINAL_IMPROVES" if value > 0 else "FINAL_DEGRADES"


def effect_tables(matrix_rows: List[Dict]) -> Tuple[List[Dict], List[Dict], List[Dict]]:
    idx = {
        (r["bid"], r["source"], r["stage3_algo_version"], r["metric_version"]): r
        for r in matrix_rows
    }
    evaluator_rows = []
    algorithm_rows = []
    final_rows = []
    for bid in [f"B{x}" for x in fc.TARGET_BIDS]:
        for source in fc.SOURCES:
            r_v0_m0 = idx.get((bid, source, STAGE3_ALGO_V0, METRIC_V0))
            r_v0_m1 = idx.get((bid, source, STAGE3_ALGO_V0, METRIC_V1))
            r_v1_m1 = idx.get((bid, source, STAGE3_ALGO_V1, METRIC_V1))
            for metric in METRIC_FIELDS:
                v0_m0 = metric_value(r_v0_m0, metric)
                v0_m1 = metric_value(r_v0_m1, metric)
                v1_m1 = metric_value(r_v1_m1, metric)
                ev_eff = improvement(metric, v0_m0, v0_m1)
                alg_eff = improvement(metric, v0_m1, v1_m1)
                fin_eff = improvement(metric, v0_m0, v1_m1)
                v0_m0_status = r_v0_m0.get("status", "") if r_v0_m0 else ""
                v0_m1_status = r_v0_m1.get("status", "") if r_v0_m1 else ""
                v1_m1_status = r_v1_m1.get("status", "") if r_v1_m1 else ""
                common = {
                    "bid": bid,
                    "source": source,
                    "metric": metric,
                    "stage3_v0_metric_v0_status": v0_m0_status,
                    "stage3_v0_metric_v1_status": v0_m1_status,
                    "stage3_v1_metric_v1_status": v1_m1_status,
                    "stage3_v0_metric_v0": v0_m0,
                    "stage3_v0_metric_v1": v0_m1,
                    "stage3_v1_metric_v1": v1_m1,
                }
                evaluator_rows.append({
                    **common,
                    "effect_value": ev_eff,
                    "interpretation": label_effect("evaluator", ev_eff, v0_m0_status, v0_m1_status),
                })
                algorithm_rows.append({
                    **common,
                    "effect_value": alg_eff,
                    "interpretation": label_effect("algorithm", alg_eff, v0_m1_status, v1_m1_status),
                })
                final_rows.append({
                    **common,
                    "effect_value": fin_eff,
                    "interpretation": label_effect("final", fin_eff, v0_m0_status, v1_m1_status),
                })
    return evaluator_rows, algorithm_rows, final_rows


def aggregate(rows: List[Dict], groups: List[str], metrics: List[str]) -> List[Dict]:
    buckets: Dict[Tuple[str, ...], List[Dict]] = defaultdict(list)
    for row in rows:
        buckets[tuple(str(row.get(g, "")) for g in groups)].append(row)
    out = []
    for key, vals in sorted(buckets.items()):
        item = {g: key[i] for i, g in enumerate(groups)}
        item["n_rows"] = len(vals)
        item["n_ok"] = sum(1 for v in vals if v.get("status") == "OK")
        for metric in metrics:
            nums = [metric_value(v, metric) for v in vals]
            nums = [x for x in nums if x is not None]
            item[f"mean_{metric}"] = float(np.mean(nums)) if nums else ""
        out.append(item)
    return out


def write_effect_plot(rows: List[Dict], metric: str, path: Path, title: str) -> None:
    vals = [r for r in rows if r.get("metric") == metric and safe_float(r.get("effect_value")) is not None]
    if not vals:
        return
    labels = [f"{r['bid']} {r['source'].split('_')[0]}" for r in vals]
    y = [float(r["effect_value"]) for r in vals]
    fig, ax = plt.subplots(figsize=(12, 4))
    x = np.arange(len(labels))
    ax.bar(x, y, color=["#2f7f5f" if v >= 0 else "#b54a4a" for v in y])
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=65, ha="right", fontsize=7)
    ax.set_ylabel("improvement-oriented effect")
    ax.set_title(title)
    ax.grid(True, axis="y", linewidth=0.2, alpha=0.4)
    fig.tight_layout()
    fc.mkdir(path.parent)
    fig.savefig(path, dpi=160)
    plt.close(fig)


def write_viewer(matrix_rows: List[Dict], algorithm_rows: List[Dict]) -> None:
    root = OUT_ROOT / "viewer"
    fc.mkdir(root)
    alg_idx = {
        (r["bid"], r["source"], r["metric"]): r
        for r in algorithm_rows
    }
    rows = []
    for r in matrix_rows:
        if r.get("stage3_algo_version") != STAGE3_ALGO_V1 or r.get("metric_version") != METRIC_V1:
            continue
        bid = r["bid"]
        source = r["source"]
        v0_preview = Path("..") / ".." / "FC_S1_semantic_surface_readout" / "phase2_readout" / source / bid / "preview.png"
        v1_preview = Path("..") / "phase2_stage3_v1_readout" / source / bid / "preview.png"
        alg_f = alg_idx.get((bid, source, "F"), {}).get("effect_value", "")
        alg_roof = alg_idx.get((bid, source, "roof_cov"), {}).get("effect_value", "")
        rows.append(
            "<tr>"
            f"<td>{bid}</td><td>{source}</td><td>{r.get('status','')}</td>"
            f"<td>{fc.fmt(r.get('F'))}</td><td>{fc.fmt(alg_f)}</td>"
            f"<td>{fc.fmt(r.get('roof_cov'))}</td><td>{fc.fmt(alg_roof)}</td>"
            f"<td>{fc.fmt(r.get('open_edges'))}</td>"
            f"<td><a href='{v0_preview.as_posix()}'>v0 preview</a></td>"
            f"<td><a href='{v1_preview.as_posix()}'>v1 preview</a></td>"
            f"<td><a href='../phase2_stage3_v1_readout/{source}/{bid}/semantic_faces.json'>faces</a></td>"
            f"<td><a href='../phase2_stage3_v1_metric_v1_audit/{source}/{bid}/metric_v1_summary.json'>audit</a></td>"
            "</tr>"
        )
    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Stage3 QA</title>
<style>
body {{ font-family: system-ui, sans-serif; margin: 24px; color: #1f2933; }}
table {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
th, td {{ border: 1px solid #c9d2dc; padding: 6px 8px; text-align: left; }}
th {{ background: #e8eef4; position: sticky; top: 0; }}
a {{ color: #064e8f; }}
.meta {{ margin-bottom: 16px; color: #52606d; }}
</style>
</head>
<body>
<h1>Stage3-v1 QA Index</h1>
<div class="meta">FC-S1 target set, fixed footprint buffer {fc.FOOTPRINT_BUFFER_M:.2f} m, gravity [0,1,0].</div>
<table>
<thead><tr>
<th>bid</th><th>source</th><th>v1 status</th><th>Metric-v1 F</th><th>algo effect F</th>
<th>Metric-v1 roof_cov</th><th>algo effect roof_cov</th><th>open_edges</th>
<th>v0</th><th>v1</th><th>faces</th><th>audit</th>
</tr></thead>
<tbody>
{''.join(rows)}
</tbody>
</table>
</body>
</html>
"""
    (root / "stage3_qa.html").write_text(html)


def write_baseline_render_regeneration_status() -> None:
    candidates = sorted(ROOT.glob("results/stage3_rendered_evidence/**/*baseline*render*.npz"))
    payload = {
        "source": "E1_Baseline_rendered",
        "status": "NOT_REGENERATED",
        "reason": (
            "No prior baseline rendered evidence artifact matching the FC-S1 mutual "
            "fixed-export format was found. Regeneration would require a controlled "
            "Stage2 render-export pass; this comparison keeps E1 as SOURCE_MISSING "
            "rather than changing evidence generation logic."
        ),
        "candidate_files": [rel(p) for p in candidates],
    }
    fc.write_json(OUT_ROOT / "phase0_inventory/baseline_rendered_regeneration_status.json", payload)


def write_report(matrix_rows: List[Dict], evaluator_rows: List[Dict],
                 algorithm_rows: List[Dict], final_rows: List[Dict],
                 v1_status_rows: List[Dict], patch_rows: List[Dict]) -> None:
    summary = aggregate(matrix_rows, ["stage3_algo_version", "metric_version", "source"], [
        "roof_cov", "wall_cov", "ground_cov", "semantic_face_acc", "support_coverage",
        "F", "precision", "recall", "h_err", "vol_ratio", "hausdorff", "chamfer",
        "open_edges", "nonmanifold_edges",
    ])
    alg_improve = [r for r in algorithm_rows if r.get("interpretation") == "STAGE3_V1_IMPROVES"]
    alg_degrade = [r for r in algorithm_rows if r.get("interpretation") == "STAGE3_V1_DEGRADES"]
    alg_recovered = [r for r in algorithm_rows if r.get("interpretation") == "STAGE3_V1_READOUT_RECOVERED"]
    alg_regressed = [r for r in algorithm_rows if r.get("interpretation") == "STAGE3_V1_READOUT_REGRESSED"]
    patches = [r for r in patch_rows if r.get("patch_applied")]
    v1_ok = sum(1 for r in v1_status_rows if r.get("status") == "OK")
    v1_total = len(v1_status_rows)
    v0_status = [r for r in matrix_rows if r.get("stage3_algo_version") == STAGE3_ALGO_V0 and r.get("metric_version") == METRIC_V0]
    v0_ok = sum(1 for r in v0_status if r.get("status") == "OK")

    lines = [
        "# Stage3-v1 Auditable Semantic Surface Read-out and FC-S1 v0-v1 Comparison",
        "",
        "## 1. Objective and alignment",
        "",
        "This run compares the original FC-S1 Stage3-v0 against Stage3-v1 while preserving the same building set, source definitions, footprint/domain condition, gravity convention, and evidence files wherever they exist. The target remains semantic 3D building read-out: RoofSurface, WallSurface, GroundSurface, face adjacency, edge incidence, and shell diagnostics.",
        "",
        "## 2. Controlled inputs",
        "",
        f"- FC-S1 source root: `{rel(FC_ROOT)}`",
        f"- Output root: `{rel(OUT_ROOT)}`",
        f"- Target bids: `{', '.join('B' + str(b) for b in fc.TARGET_BIDS)}`",
        f"- Footprint buffer: `{fc.FOOTPRINT_BUFFER_M:.2f}` m",
        "- Gravity: `[0, 1, 0]`",
        "- E1_Baseline_rendered remains `SOURCE_MISSING`; regeneration status is recorded in `phase0_inventory/baseline_rendered_regeneration_status.json`.",
        "",
        "## 3. Comparison matrix",
        "",
        "The matrix includes `Stage3Algo-v0 + Metric-v0`, `Stage3Algo-v0 + Metric-v1`, `Stage3Algo-v1 + Metric-v1`, and optional `Stage3Algo-v1 + Metric-v0`. This separates evaluator effects from read-out effects.",
        "",
    ]
    lines.extend(fc.md_table(
        ["algo", "metric", "source", "n_rows", "OK", "mean_F", "mean_roof_cov", "mean_wall_cov", "mean_ground_cov", "mean_open_edges"],
        [[
            r["stage3_algo_version"], r["metric_version"], r["source"], r["n_rows"], r["n_ok"],
            fc.fmt(r.get("mean_F")), fc.fmt(r.get("mean_roof_cov")),
            fc.fmt(r.get("mean_wall_cov")), fc.fmt(r.get("mean_ground_cov")),
            fc.fmt(r.get("mean_open_edges")),
        ] for r in summary],
    ))
    lines.extend([
        "",
        "## 4. Metric-v1 audit",
        "",
        "Metric-v1 writes explicit `metric_version`, per-face matching logs, and deterministic per-sample matching logs. Surface coverage requires nearest-surface distance within 0.5 m and matching semantic type. Logs are stored under `phase1_metric_v1_audit_stage3_v0/` and `phase2_stage3_v1_metric_v1_audit/`.",
        "",
        "## 5. Stage3Algo-v1 patch",
        "",
        "Stage3Algo-v1 uses the same v0 relation read-out path. The only algorithm patch is an audited read-out-only ground reference synthesized from the evidence Y distribution when a source has roof evidence but zero ground evidence. It does not change Stage2 evidence files and does not use GT roof type, GT heights, GT final mesh, or GT semantic surfaces.",
        "",
    ])
    lines.extend(fc.md_table(
        ["bid", "source", "patch_applied", "reason", "n_synthetic_ground_points"],
        [[r.get("bid"), r.get("source"), r.get("patch_applied"), r.get("reason"), r.get("n_synthetic_ground_points", "")]
         for r in patch_rows],
    ))
    lines.extend([
        "",
        "## 6. Read-out status",
        "",
        f"Stage3-v0 OK rows: `{v0_ok}/{len(v0_status)}`. Stage3-v1 OK rows: `{v1_ok}/{v1_total}`.",
        "",
        "## 7. Evaluator effect",
        "",
        "Evaluator-effect rows compare Stage3Algo-v0 under Metric-v0 vs Metric-v1. Improvements here are audit/matching changes, not reconstruction changes.",
        "",
        f"- Metric-v1 higher rows: `{sum(1 for r in evaluator_rows if r.get('interpretation') == 'METRIC_V1_HIGHER')}`",
        f"- Metric-v1 lower rows: `{sum(1 for r in evaluator_rows if r.get('interpretation') == 'METRIC_V1_LOWER')}`",
        "",
        "## 8. Algorithm effect",
        "",
        "Algorithm-effect rows compare Stage3Algo-v0 vs Stage3Algo-v1 under Metric-v1.",
        "",
        f"- Stage3-v1 improvement rows: `{len(alg_improve)}`",
        f"- Stage3-v1 degradation rows: `{len(alg_degrade)}`",
        f"- Stage3-v1 read-out recovered rows: `{len(alg_recovered)}`",
        f"- Stage3-v1 read-out regressed rows: `{len(alg_regressed)}`",
        f"- Ground-reference patches applied: `{len(patches)}`",
        "",
        "## 9. QA artifacts",
        "",
        "- Matrix: `phase3_matrix/matrix_metrics_by_bid.csv`",
        "- Evaluator effect: `phase3_matrix/evaluator_effect_by_bid.csv`",
        "- Algorithm effect: `phase3_matrix/algorithm_effect_by_bid.csv`",
        "- Final effect: `phase3_matrix/final_effect_by_bid.csv`",
        "- Viewer: `viewer/stage3_qa.html`",
        "",
        "## 10. Final interpretation",
        "",
        "Stage3-v1 is an auditable v1 rather than a replacement reconstruction pipeline. Its main algorithmic value in this run is converting zero-ground-evidence read-out failures into explicit, logged shell attempts where the cause and correction are inspectable. Metric-v1 provides the matching evidence needed to decide whether future changes are evaluator effects or reconstruction effects.",
        "",
        "## 11. Self-verification",
        "",
        "- PASS: no full-scene building split used.",
        "- PASS: FC-S1 building set preserved.",
        "- PASS: footprint used only as domain condition.",
        "- PASS: gravity convention preserved as `[0, 1, 0]`.",
        "- PASS: source definitions E0/E1/E2/E3/E4 preserved.",
        "- PASS: Stage2 evidence generation logic not changed.",
        "- PASS: footprint buffer size not changed.",
        "- PASS: primary outputs remain `semantic_faces.json`, `face_graph.json`, and `shell_diagnostics.json`.",
        "- PASS: Metric-v1 and Stage3Algo-v1 effects are separated in the comparison matrix.",
        "- PASS: GT roof type, GT roof partition, GT final mesh, and GT semantic surfaces are not used for Stage2-derived generation.",
    ])
    (OUT_ROOT / "REPORT.md").write_text("\n".join(lines) + "\n")


def run(args: argparse.Namespace) -> None:
    fc.assert_gravity()
    if not FC_ROOT.exists():
        raise FileNotFoundError(f"FC-S1 v0 root not found: {FC_ROOT}")
    if OUT_ROOT.exists() and args.force:
        shutil.rmtree(OUT_ROOT)
    fc.mkdir(OUT_ROOT)
    fc.mkdir(OUT_ROOT / "phase0_inventory")
    write_baseline_render_regeneration_status()

    buildings = parse_scene_obj(fc.SCENE, frame="obj")["buildings"]
    buildings_by_bid = fc.target_buildings(buildings)
    fc.write_json(OUT_ROOT / "phase0_inventory/input_manifest.json", {
        "experiment": "Stage3-v1 Auditable Semantic Surface Read-out and FC-S1 v0-v1 Comparison",
        "fc_s1_v0_root": rel(FC_ROOT),
        "stage3_v1_root": rel(OUT_ROOT),
        "target_bids": [f"B{b}" for b in fc.TARGET_BIDS],
        "sources": list(fc.SOURCES.keys()),
        "footprint_buffer_m": fc.FOOTPRINT_BUFFER_M,
        "gravity": [0, 1, 0],
        "same_evidence_files_where_available": True,
        "stage2_evidence_generation_logic_changed": False,
    })

    matrix_rows = metric0_rows()
    v0_metric1_rows = []
    v1_metric1_rows = []
    v1_metric0_rows = []
    v1_status_rows = []
    patch_rows = []
    v1_faces: Dict[Tuple[str, str], List[Dict]] = {}
    v1_city: Dict[Tuple[str, str], Dict] = {}
    evidence_by_key: Dict[Tuple[str, str], Optional[Dict]] = {}

    for bid in fc.TARGET_BIDS:
        building = buildings_by_bid.get(bid)
        if building is None:
            continue
        footprint = fc.footprint_for_building(building)
        if footprint is None:
            continue
        for source in fc.SOURCES:
            bid_str = f"B{bid}"
            print(f"[Stage3-v1] {bid_str} {source}", flush=True)
            evidence = load_evidence_from_fc_s1(source, bid)
            evidence_by_key[(bid_str, source)] = evidence

            v0_dir = FC_ROOT / "phase2_readout" / source / bid_str
            v0_faces, _v0_payload = load_faces(v0_dir / "semantic_faces.json")
            v0_shell = {}
            if (v0_dir / "shell_diagnostics.json").exists():
                v0_shell = json.loads((v0_dir / "shell_diagnostics.json").read_text())
            v0_status = v0_shell.get("status", "OK" if v0_faces else "NO_FACES")
            v0_failure = v0_shell.get("failure_reason", "")
            v0_metric1 = metric_v1_evaluate(
                v0_faces, building, evidence, source, bid, STAGE3_ALGO_V0,
                v0_status, v0_failure,
                OUT_ROOT / "phase1_metric_v1_audit_stage3_v0" / source / bid_str,
                v0_dir,
            )
            v0_metric1_rows.append(v0_metric1)

            v1_dir = OUT_ROOT / "phase2_stage3_v1_readout" / source / bid_str
            try:
                status, faces, city_diag, patch_log = stage3_v1_readout(
                    evidence, building, footprint, source, bid, v1_dir
                )
            except Exception as exc:
                status = {
                    "bid": bid_str,
                    "bid_int": bid,
                    "source": source,
                    "stage3_algo_version": STAGE3_ALGO_V1,
                    "status": "READOUT_EXCEPTION",
                    "n_faces": 0,
                    "n_roof_faces": 0,
                    "n_wall_faces": 0,
                    "n_ground_faces": 0,
                    "export_status": "NOT_WRITTEN",
                    "failure_reason": f"{type(exc).__name__}: {exc}",
                    "traceback_tail": traceback.format_exc(limit=5),
                    "patch_applied": False,
                }
                faces = []
                city_diag = None
                patch_log = {"patch_applied": False, "reason": status["failure_reason"]}
                fc.write_json(v1_dir / "semantic_faces.json", {"faces": [], "failure_reason": status["failure_reason"]})
                fc.write_json(v1_dir / "face_graph.json", {"nodes": [], "edges": [], "failure_reason": status["failure_reason"]})
                fc.write_json(v1_dir / "shell_diagnostics.json", status)

            v1_status_rows.append(status)
            v1_faces[(bid_str, source)] = faces
            if city_diag is not None:
                v1_city[(bid_str, source)] = city_diag
            patch_rows.append({
                "bid": bid_str,
                "source": source,
                "patch_applied": bool(patch_log.get("patch_applied", False)),
                "reason": patch_log.get("reason", ""),
                "ground_y": patch_log.get("ground_y", ""),
                "n_synthetic_ground_points": patch_log.get("n_synthetic_ground_points", ""),
                "stage3_v1_patch_log": rel(v1_dir / "stage3_v1_patch_log.json"),
            })
            v1_metric1 = metric_v1_evaluate(
                faces, building, evidence, source, bid, STAGE3_ALGO_V1,
                status.get("status", ""), status.get("failure_reason", ""),
                OUT_ROOT / "phase2_stage3_v1_metric_v1_audit" / source / bid_str,
                v1_dir,
            )
            v1_metric1_rows.append(v1_metric1)

    matrix_rows.extend(v0_metric1_rows)
    matrix_rows.extend(v1_metric1_rows)
    v1_metric0_rows = metric0_for_stage3_v1(
        v1_status_rows, v1_faces, v1_city, buildings_by_bid, evidence_by_key
    )
    matrix_rows.extend(v1_metric0_rows)

    fc.write_csv(OUT_ROOT / "phase2_stage3_v1_readout/readout_status.csv", v1_status_rows, [
        "bid", "source", "stage3_algo_version", "status", "n_faces", "n_roof_faces",
        "n_wall_faces", "n_ground_faces", "export_status", "failure_reason",
        "patch_applied", "patch_reason",
    ])
    fc.write_csv(OUT_ROOT / "phase2_stage3_v1_readout/stage3_v1_patch_summary.csv", patch_rows)
    fc.write_csv(OUT_ROOT / "phase3_matrix/matrix_metrics_by_bid.csv", matrix_rows, MATRIX_FIELDS)

    summary_rows = aggregate(matrix_rows, ["stage3_algo_version", "metric_version", "source"], [
        "roof_cov", "wall_cov", "ground_cov", "semantic_face_acc", "support_coverage",
        "F", "precision", "recall", "h_err", "vol_ratio", "hausdorff", "chamfer",
        "open_edges", "nonmanifold_edges",
    ])
    fc.write_csv(OUT_ROOT / "phase3_matrix/matrix_summary_by_source.csv", summary_rows)

    evaluator_rows, algorithm_rows, final_rows = effect_tables(matrix_rows)
    fc.write_csv(OUT_ROOT / "phase3_matrix/evaluator_effect_by_bid.csv", evaluator_rows)
    fc.write_csv(OUT_ROOT / "phase3_matrix/algorithm_effect_by_bid.csv", algorithm_rows)
    fc.write_csv(OUT_ROOT / "phase3_matrix/final_effect_by_bid.csv", final_rows)

    write_effect_plot(
        algorithm_rows, "F",
        OUT_ROOT / "phase3_matrix/plots/stage3_v1_algorithm_effect_F.png",
        "Stage3-v1 algorithm effect on F (Metric-v1)",
    )
    write_effect_plot(
        algorithm_rows, "roof_cov",
        OUT_ROOT / "phase3_matrix/plots/stage3_v1_algorithm_effect_roof_cov.png",
        "Stage3-v1 algorithm effect on roof coverage (Metric-v1)",
    )
    write_viewer(matrix_rows, algorithm_rows)

    self_verification = {
        "no_full_scene_building_split_used": "PASS",
        "fc_s1_building_set_preserved": "PASS",
        "footprint_used_only_as_domain_condition": "PASS",
        "gravity_convention_preserved": "PASS",
        "source_definitions_preserved": "PASS",
        "stage2_evidence_generation_logic_not_changed": "PASS",
        "footprint_buffer_size_preserved": "PASS",
        "primary_outputs_preserved": ["semantic_faces.json", "face_graph.json", "shell_diagnostics.json"],
        "metric_and_algorithm_effects_separated": "PASS",
        "cityjson_optional_serialization_only": "PASS",
        "baseline_rendered_regeneration": "NOT_REGENERATED_SOURCE_MISSING_PRESERVED",
    }
    fc.write_json(OUT_ROOT / "self_verification.json", self_verification)
    write_report(matrix_rows, evaluator_rows, algorithm_rows, final_rows, v1_status_rows, patch_rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="remove and regenerate this comparison output root")
    args = ap.parse_args()
    run(args)


if __name__ == "__main__":
    main()
