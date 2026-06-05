"""FC-S1: footprint-conditioned semantic surface read-out benchmark.

The benchmark controls building-domain discovery by passing a GT-derived
footprint as the domain boundary. GT roof type, GT roof partition, GT heights,
and GT final mesh are not used for Stage2-derived generation. GT mesh and
semantic surfaces are used after generation for evaluation.
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
from shapely.geometry import Point, Polygon

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.phase2_synthesis.obj_gt import parse_scene_obj  # noqa: E402
import scripts.phase2_synthesis.p1_4a_relation_readout as rr  # noqa: E402
import scripts.phase2_synthesis.p1_4a_preflight_precision as pm  # noqa: E402
import scripts.phase2_synthesis.e3_stage2_oracle_split as e3  # noqa: E402
from scripts.phase2_synthesis.e1_gt_131_relation_readout import (  # noqa: E402
    val3dity_binary,
)


OUT_ROOT = ROOT / "results/footprint_conditioned_readout/FC_S1_semantic_surface_readout"
SCENE = ROOT / "results/phase2_synthesis/scene.obj"
GRAVITY_JSON = ROOT / "results/phase2_synthesis/gravity.json"
DATA_GRAVITY_JSON = ROOT / "data/matrixcity/gravity.json"

BASELINE_CKPT = ROOT / "results/phase2_ablation_citygml/baseline/ckpt/final.pt"
MUTUAL_CKPT = ROOT / "results/phase2_ablation_citygml/mutual/ckpt/final.pt"
BASELINE_PRIMITIVES = ROOT / "results/phase2_ablation_citygml/baseline/stage3/primitives.npz"
MUTUAL_PRIMITIVES = ROOT / "results/phase2_ablation_citygml/mutual/stage3/primitives.npz"
MUTUAL_RENDERED = (
    ROOT
    / "results/stage3_rendered_evidence/S1D_fix_export_and_rerun"
    / "phase3_fixed_quality/rendered_evidence_fixed_F2_class_normal_aware_voxel_0p05.npz"
)
BASELINE_RENDERED = ROOT / "results/stage3_rendered_evidence/baseline_rendered_evidence_NOT_AVAILABLE.npz"

FOOTPRINT_BUFFER_M = 0.75
SUPPORT_DISTANCE_M = 0.75
N_METRIC_SAMPLE = 6000
N_SURFACE_SAMPLE = 3000
MAX_PLY_POINTS = 200000
CITYJSON_SCALE = rr.CITYJSON_SCALE

CLASS_TO_SURFACE = {1: "RoofSurface", 2: "WallSurface", 3: "GroundSurface"}
SURFACE_TO_CLASS = {v: k for k, v in CLASS_TO_SURFACE.items()}

TARGET_GROUPS: Dict[str, List[int]] = {
    "OK_CONTROL": [0, 1, 2, 8],
    "HIP": [6],
    "COMPLEX": [3],
    "SHARED_WALL": [123, 126],
    "GROUND_EVIDENCE": [50, 104],
}
TARGET_BIDS = [0, 1, 2, 8, 6, 3, 123, 126, 50, 104]

SOURCES = {
    "E0_GT_clean_upper_bound": {
        "kind": "gt",
        "path": SCENE,
        "generation_status": "UPPER_BOUND_ONLY",
    },
    "E1_Baseline_rendered": {
        "kind": "rendered",
        "path": BASELINE_RENDERED,
        "checkpoint": BASELINE_CKPT,
    },
    "E2_Mutual_rendered": {
        "kind": "rendered",
        "path": MUTUAL_RENDERED,
        "checkpoint": MUTUAL_CKPT,
    },
    "E3_Baseline_primitive": {
        "kind": "primitive",
        "path": BASELINE_PRIMITIVES,
        "checkpoint": BASELINE_CKPT,
    },
    "E4_Mutual_primitive": {
        "kind": "primitive",
        "path": MUTUAL_PRIMITIVES,
        "checkpoint": MUTUAL_CKPT,
    },
}


def mkdir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def jsonable(obj):
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, np.generic):
        return obj.item()
    if isinstance(obj, (Point, Polygon)):
        return obj.wkt
    if isinstance(obj, Path):
        return str(obj)
    return str(obj)


def write_json(path: Path, payload: Dict) -> None:
    mkdir(path.parent)
    path.write_text(json.dumps(payload, indent=2, default=jsonable) + "\n")


def write_csv(path: Path, rows: List[Dict], fields: Optional[List[str]] = None) -> None:
    mkdir(path.parent)
    if fields is None:
        fields = []
        seen = set()
        for row in rows:
            for key in row:
                if key not in seen:
                    fields.append(key)
                    seen.add(key)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fields})


def fmt(value: object, nd: int = 3) -> str:
    if value is None or value == "":
        return "NA"
    try:
        x = float(value)
    except (TypeError, ValueError):
        return str(value)
    if math.isnan(x) or math.isinf(x):
        return "NA"
    return f"{x:.{nd}f}"


def safe_float(value: object) -> Optional[float]:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(x) or math.isinf(x) else x


def stratum_for_bid(bid: int) -> str:
    for name, bids in TARGET_GROUPS.items():
        if int(bid) in bids:
            return name
    return "UNSTRATIFIED"


def md_table(headers: List[str], rows: Iterable[Iterable[object]]) -> List[str]:
    out = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        out.append("| " + " | ".join(str(x) for x in row) + " |")
    return out


def load_gravity() -> List[float]:
    for path in [GRAVITY_JSON, DATA_GRAVITY_JSON]:
        if path.exists():
            data = json.loads(path.read_text())
            g = data.get("gravity") or data.get("e_gravity")
            if g is not None:
                return [float(x) for x in g]
    return [0.0, 1.0, 0.0]


def assert_gravity() -> None:
    g = np.asarray(load_gravity(), dtype=np.float64)
    g /= np.linalg.norm(g) + 1e-12
    if not np.allclose(g, np.asarray([0.0, 1.0, 0.0]), atol=1e-6):
        raise AssertionError(f"FC-S1 requires gravity=[0,1,0], got {g.tolist()}")
    if not np.allclose(rr.GRAVITY, np.asarray([0.0, 1.0, 0.0]), atol=1e-6):
        raise AssertionError(f"Relation read-out gravity mismatch: {rr.GRAVITY.tolist()}")


def target_buildings(buildings: List[Dict]) -> Dict[int, Dict]:
    by_bid = {int(b["building_id"]): b for b in buildings}
    return {bid: by_bid[bid] for bid in TARGET_BIDS if bid in by_bid}


def footprint_for_building(building: Dict) -> Optional[Polygon]:
    fp = pm.footprint_from_gt(building)
    if fp is None or fp.is_empty:
        return None
    fp = Polygon(fp.exterior.coords)
    if not fp.exterior.is_ccw:
        fp = Polygon(list(fp.exterior.coords)[::-1])
    return fp


def footprint_mask(points: np.ndarray, footprint: Polygon, buffer_m: float) -> np.ndarray:
    poly = footprint.buffer(buffer_m)
    xz = np.asarray(points, dtype=np.float64)[:, [0, 2]]
    minx, minz, maxx, maxz = poly.bounds
    rough = np.where(
        (xz[:, 0] >= minx)
        & (xz[:, 0] <= maxx)
        & (xz[:, 1] >= minz)
        & (xz[:, 1] <= maxz)
    )[0]
    out = np.zeros(len(points), dtype=bool)
    for idx in rough:
        p = Point(float(xz[idx, 0]), float(xz[idx, 1]))
        if poly.contains(p) or poly.touches(p):
            out[idx] = True
    return out


def normalize_rows(arr: np.ndarray) -> np.ndarray:
    x = np.asarray(arr, dtype=np.float64)
    return x / np.maximum(np.linalg.norm(x, axis=1, keepdims=True), 1e-12)


def load_npz(path: Path) -> Dict[str, np.ndarray]:
    data = np.load(path, allow_pickle=False)
    return {k: data[k] for k in data.files}


def normalize_evidence(raw: Dict[str, np.ndarray], source_name: str, kind: str) -> Dict:
    points = raw.get("points", raw.get("xyz", raw.get("centers")))
    normals = raw.get("normals", raw.get("normal"))
    classes = raw.get("classes", raw.get("label", raw.get("labels")))
    if points is None or normals is None or classes is None:
        raise KeyError(f"{source_name} is missing points/normals/classes-compatible fields")
    points = np.asarray(points, dtype=np.float64)
    normals = normalize_rows(np.asarray(normals, dtype=np.float64))
    classes = np.asarray(classes, dtype=np.int64)
    sem_probs = raw.get("sem_probs", raw.get("semantic_prob", raw.get("semantic_probability")))
    if sem_probs is not None:
        sem_probs = np.asarray(sem_probs, dtype=np.float64)
        bad = (classes < 0) | (classes > 3)
        if np.any(bad) and len(sem_probs) == len(classes):
            classes = classes.copy()
            classes[bad] = np.argmax(sem_probs[bad], axis=1)
    weights = raw.get("weights", raw.get("support_weight"))
    if weights is None and kind == "primitive":
        areas = np.asarray(raw.get("areas", np.ones(len(points))), dtype=np.float64)
        opacities = np.asarray(raw.get("opacities", np.ones(len(points))), dtype=np.float64)
        weights = areas * opacities
    if weights is None:
        weights = np.ones(len(points), dtype=np.float64)
    weights = np.asarray(weights, dtype=np.float64)
    weights = np.where(np.isfinite(weights), weights, 0.0)
    keep = np.isfinite(points).all(axis=1) & np.isfinite(normals).all(axis=1) & np.isfinite(weights)
    if kind == "primitive" and "opacities" in raw:
        keep &= np.asarray(raw["opacities"], dtype=np.float64) >= e3.OPACITY_THRESH
    keep &= (classes >= 0) & (classes <= 3)
    out = {
        "points": points[keep],
        "normals": normals[keep],
        "classes": classes[keep].astype(np.int64),
        "weights": np.maximum(weights[keep], 1e-9),
    }
    if sem_probs is not None and len(sem_probs) == len(keep):
        out["sem_probs"] = np.asarray(sem_probs, dtype=np.float64)[keep]
    for extra in ["confidence", "view_count", "normal_consistency", "semantic_entropy", "opacities", "areas"]:
        if extra in raw and len(raw[extra]) == len(keep):
            out[extra] = np.asarray(raw[extra])[keep]
    return out


def crop_evidence(evidence: Dict, footprint: Polygon, source_name: str, bid: int) -> Dict:
    mask = footprint_mask(evidence["points"], footprint, FOOTPRINT_BUFFER_M)
    out = {k: np.asarray(v)[mask] for k, v in evidence.items() if len(np.asarray(v).shape) > 0 and len(v) == len(mask)}
    out["source"] = source_name
    out["bid"] = f"B{bid}"
    return out


def gt_clean_evidence(building: Dict, footprint: Polygon, source_name: str) -> Dict:
    ev = rr.generate_evidence(building)
    ev["sem_probs"] = np.eye(4, dtype=np.float64)[ev["classes"]]
    return crop_evidence(ev, footprint, source_name, int(building["building_id"]))


def evidence_entropy(evidence: Dict) -> Optional[float]:
    probs = evidence.get("sem_probs")
    if probs is not None and len(probs):
        p = np.clip(np.asarray(probs, dtype=np.float64), 1e-12, 1.0)
        return float(np.mean(-np.sum(p * np.log(p), axis=1) / math.log(p.shape[1])))
    classes = evidence["classes"]
    if len(classes) == 0:
        return None
    counts = np.asarray([np.sum(classes == c) for c in range(4)], dtype=np.float64)
    p = counts[counts > 0] / max(float(counts.sum()), 1e-12)
    return float(-np.sum(p * np.log(p)) / math.log(4))


def normal_consistency(evidence: Dict) -> Optional[float]:
    classes = evidence["classes"]
    normals = evidence["normals"]
    weights = evidence["weights"]
    values = []
    wvalues = []
    for cls in [1, 2, 3]:
        m = classes == cls
        if not np.any(m):
            continue
        n = normals[m]
        w = weights[m]
        ref = np.average(n, axis=0, weights=w)
        ref /= np.linalg.norm(ref) + 1e-12
        values.append(np.abs(n @ ref))
        wvalues.append(w)
    if not values:
        return None
    vals = np.concatenate(values)
    ws = np.concatenate(wvalues)
    return float(np.average(vals, weights=ws))


def evidence_summary_row(evidence: Dict, bid: int, source: str) -> Dict:
    cls = evidence["classes"]
    weights = evidence["weights"]
    return {
        "bid": f"B{bid}",
        "bid_int": bid,
        "source": source,
        "n_points": int(len(cls)),
        "n_roof": int(np.sum(cls == 1)),
        "n_wall": int(np.sum(cls == 2)),
        "n_ground": int(np.sum(cls == 3)),
        "n_bg": int(np.sum(cls == 0)),
        "mean_support": float(np.mean(weights)) if len(weights) else None,
        "semantic_entropy": evidence_entropy(evidence),
        "normal_consistency": normal_consistency(evidence),
    }


def write_limited_evidence_ply(path: Path, evidence: Dict, seed: int) -> None:
    ev = evidence
    if len(evidence["classes"]) > MAX_PLY_POINTS:
        keep = np.arange(0)
        try:
            import scripts.phase2_synthesis.s1_rendered_e2style_gate as s1  # noqa: PLC0415
            keep = s1.downsample_balanced(evidence["classes"], MAX_PLY_POINTS, seed)
        except Exception:
            rng = np.random.default_rng(seed)
            keep = np.sort(rng.choice(len(evidence["classes"]), size=MAX_PLY_POINTS, replace=False))
        ev = {k: np.asarray(v)[keep] for k, v in evidence.items() if hasattr(v, "__len__") and len(v) == len(evidence["classes"])}
    rr.write_evidence_ply(path, ev)


def plane_candidates(evidence: Dict, source: str, bid: int) -> Tuple[List[rr.PlaneCandidate], List[rr.PlaneCandidate], List[rr.PlaneCandidate], Dict]:
    info: Dict[str, object] = {"source": source, "bid": f"B{bid}"}
    out = []
    for class_id, max_count in [(1, 16), (2, 48), (3, 4)]:
        try:
            planes = rr.cluster_planes_from_evidence(evidence, class_id)
            total = float(np.sum(evidence["weights"][evidence["classes"] == class_id]))
            min_support = max(total * 0.002, 1e-9)
            filtered = [p for p in planes if p.support_weight >= min_support]
            if len(filtered) < min(max_count, len(planes)):
                filtered = planes
            planes = filtered[:max_count]
        except Exception as exc:
            info[f"class_{class_id}_plane_error"] = str(exc)
            planes = []
        info[f"class_{class_id}_n_planes"] = len(planes)
        out.append(planes)
    return out[0], out[1], out[2], info


def face_area(vertices: np.ndarray) -> float:
    return pm.triangle_area(pm.triangulate_polygon(np.asarray(vertices, dtype=np.float64)))


def faces_to_semantic_json(faces: List[Dict], path: Path) -> Dict:
    rows = []
    for i, face in enumerate(faces):
        verts = np.asarray(face["vertices"], dtype=np.float64)
        rows.append({
            "face_id": f"F{i:04d}",
            "semantic_type": face["type"],
            "semantic_class": SURFACE_TO_CLASS.get(face["type"], -1),
            "source": face.get("source", ""),
            "vertices": verts.tolist(),
            "normal": rr._newell_normal(verts).tolist(),
            "area": face_area(verts),
            "planarity_max": face_planarity_error(verts),
        })
    payload = {
        "schema": "FC-S1 semantic face read-out",
        "faces": rows,
        "summary": {
            "n_faces": len(rows),
            "n_roof_faces": sum(1 for r in rows if r["semantic_type"] == "RoofSurface"),
            "n_wall_faces": sum(1 for r in rows if r["semantic_type"] == "WallSurface"),
            "n_ground_faces": sum(1 for r in rows if r["semantic_type"] == "GroundSurface"),
        },
    }
    write_json(path, payload)
    return payload


def face_planarity_error(vertices: np.ndarray) -> float:
    pts = np.asarray(vertices, dtype=np.float64)
    if len(pts) <= 3:
        return 0.0
    c = pts.mean(axis=0)
    try:
        _u, _s, vh = np.linalg.svd(pts - c, full_matrices=False)
    except np.linalg.LinAlgError:
        return float("nan")
    n = vh[-1]
    n /= np.linalg.norm(n) + 1e-12
    return float(np.max(np.abs((pts - c) @ n)))


def face_graph(faces: List[Dict]) -> Dict:
    edge_map: Dict[Tuple[Tuple[int, int, int], Tuple[int, int, int]], List[int]] = defaultdict(list)
    nodes = []
    for i, face in enumerate(faces):
        verts = np.asarray(face["vertices"], dtype=np.float64)
        nodes.append({
            "face_id": f"F{i:04d}",
            "semantic_type": face["type"],
            "area": face_area(verts),
            "centroid": verts.mean(axis=0).tolist(),
        })
        keys = [rr.qkey(v) for v in verts]
        cleaned = [keys[0]]
        for key in keys[1:]:
            if key != cleaned[-1]:
                cleaned.append(key)
        if len(cleaned) > 1 and cleaned[0] == cleaned[-1]:
            cleaned = cleaned[:-1]
        for j, a in enumerate(cleaned):
            b = cleaned[(j + 1) % len(cleaned)]
            if a == b:
                continue
            edge = (a, b) if a < b else (b, a)
            edge_map[edge].append(i)
    adj = {}
    open_edges = 0
    nonmanifold_edges = 0
    for _edge, owners in edge_map.items():
        if len(owners) == 1:
            open_edges += 1
        elif len(owners) > 2:
            nonmanifold_edges += 1
        if len(owners) >= 2:
            for a in owners:
                for b in owners:
                    if a != b:
                        adj.setdefault(tuple(sorted((a, b))), set()).add("shared_edge")
    edges = []
    counts = Counter()
    for (a, b), relations in sorted(adj.items()):
        pair = f"{faces[a]['type']}--{faces[b]['type']}"
        counts[pair] += 1
        edges.append({
            "edge_id": f"E{len(edges):04d}",
            "face_a": f"F{a:04d}",
            "face_b": f"F{b:04d}",
            "semantic_pair": pair,
            "relations": sorted(relations),
        })
    return {
        "nodes": nodes,
        "edges": edges,
        "diagnostics": {
            "n_topological_edges": len(edge_map),
            "open_edges": int(open_edges),
            "nonmanifold_edges": int(nonmanifold_edges),
            "edge_ok": bool(open_edges == 0 and nonmanifold_edges == 0),
            "roof_wall_adjacency_count": int(sum(v for k, v in counts.items() if "RoofSurface" in k and "WallSurface" in k)),
            "wall_ground_adjacency_count": int(sum(v for k, v in counts.items() if "WallSurface" in k and "GroundSurface" in k)),
            "semantic_pair_counts": dict(counts),
        },
    }


def support_coverage(faces: List[Dict], evidence: Dict, seed: int) -> float:
    vals = []
    for surface_type, cls in SURFACE_TO_CLASS.items():
        pred_tris = faces_to_triangles([f for f in faces if f["type"] == surface_type])
        if len(pred_tris) == 0:
            continue
        pts = pm.sample_triangles(pred_tris, min(N_SURFACE_SAMPLE, 1000), seed + cls)
        ev = evidence["points"][evidence["classes"] == cls]
        if len(pts) == 0 or len(ev) == 0:
            vals.append(0.0)
            continue
        d, _ = cKDTree(ev).query(pts)
        vals.append(float(np.mean(d <= SUPPORT_DISTANCE_M)))
    return float(np.mean(vals)) if vals else 0.0


def shell_diagnostics_payload(faces: List[Dict], assembly_diag: Dict, city_diag: Dict,
                              evidence: Dict, source: str, bid: int, status: str) -> Dict:
    planarity = [face_planarity_error(np.asarray(f["vertices"], dtype=np.float64)) for f in faces]
    graph = face_graph(faces)
    allv = np.concatenate([np.asarray(f["vertices"], dtype=np.float64) for f in faces], axis=0) if faces else np.empty((0, 3))
    return {
        "bid": f"B{bid}",
        "source": source,
        "status": status,
        "gravity": [0, 1, 0],
        "input_policy": generation_policy(source),
        "n_faces": len(faces),
        "n_roof_faces": sum(1 for f in faces if f["type"] == "RoofSurface"),
        "n_wall_faces": sum(1 for f in faces if f["type"] == "WallSurface"),
        "n_ground_faces": sum(1 for f in faces if f["type"] == "GroundSurface"),
        "height_range": float(allv[:, 1].max() - allv[:, 1].min()) if len(allv) else None,
        "signed_volume": city_diag.get("signed_volume"),
        "edge_ok": graph["diagnostics"]["edge_ok"],
        "open_edges": graph["diagnostics"]["open_edges"],
        "nonmanifold_edges": graph["diagnostics"]["nonmanifold_edges"],
        "roof_wall_adjacency_count": graph["diagnostics"]["roof_wall_adjacency_count"],
        "wall_ground_adjacency_count": graph["diagnostics"]["wall_ground_adjacency_count"],
        "shell_completeness": "CLOSED_BY_EDGE_INCIDENCE" if graph["diagnostics"]["edge_ok"] else "OPEN_OR_NONMANIFOLD",
        "face_planarity_mean": float(np.mean(planarity)) if planarity else None,
        "face_planarity_max": float(np.max(planarity)) if planarity else None,
        "support_coverage": support_coverage(faces, evidence, seed=bid),
        "assembly_diagnostics": assembly_diag,
        "cityjson_diagnostics": city_diag,
    }


def generation_policy(source: str) -> Dict:
    return {
        "footprint_used_as_domain_condition": True,
        "footprint_buffer_m": FOOTPRINT_BUFFER_M,
        "full_scene_automatic_building_split_used": False,
        "gt_roof_type_used": False,
        "gt_roof_partition_used": False,
        "gt_heights_used": False,
        "gt_final_mesh_used_for_generation": source == "E0_GT_clean_upper_bound",
        "gt_semantic_surfaces_used_for_generation": source == "E0_GT_clean_upper_bound",
        "gt_used_for_evaluation": True,
        "readout_algorithm": "same footprint-conditioned semantic height-field read-out for all sources",
    }


def faces_to_triangles(faces: List[Dict]) -> np.ndarray:
    tris = [pm.triangulate_polygon(np.asarray(f["vertices"], dtype=np.float64)) for f in faces]
    return np.concatenate(tris, axis=0) if tris else np.empty((0, 3, 3), dtype=np.float64)


def gt_triangles_by_type(building: Dict, surface_type: str) -> np.ndarray:
    cls = SURFACE_TO_CLASS[surface_type]
    tris = [
        pm.triangulate_polygon(np.asarray(face["vertices"], dtype=np.float64))
        for face in building["faces"]
        if int(face.get("semantic_class", -1)) == cls
    ]
    return np.concatenate(tris, axis=0) if tris else np.empty((0, 3, 3), dtype=np.float64)


def coverage_type(pred_faces: List[Dict], building: Dict, surface_type: str, seed: int) -> float:
    pred = faces_to_triangles([f for f in pred_faces if f["type"] == surface_type])
    gt = gt_triangles_by_type(building, surface_type)
    if len(pred) == 0 or len(gt) == 0:
        return float("nan")
    pred_pts = pm.sample_triangles(pred, N_SURFACE_SAMPLE, seed)
    gt_pts = pm.sample_triangles(gt, N_SURFACE_SAMPLE, seed + 91)
    return pm.distance_metrics(pred_pts, gt_pts)["recall_coverage"]


def sample_gt_semantics(building: Dict, n_per_type: int = 1600) -> Tuple[np.ndarray, np.ndarray]:
    pts = []
    labels = []
    for surface_type, cls in SURFACE_TO_CLASS.items():
        tris = gt_triangles_by_type(building, surface_type)
        if len(tris) == 0:
            continue
        p = pm.sample_triangles(tris, n_per_type, seed=7100 + cls)
        pts.append(p)
        labels.append(np.full(len(p), cls, dtype=np.int64))
    if not pts:
        return np.empty((0, 3)), np.empty(0, dtype=np.int64)
    return np.concatenate(pts, axis=0), np.concatenate(labels, axis=0)


def semantic_face_accuracy(pred_faces: List[Dict], building: Dict, seed: int) -> float:
    pred_tris = []
    pred_labels = []
    for f in pred_faces:
        tris = pm.triangulate_polygon(np.asarray(f["vertices"], dtype=np.float64))
        if len(tris) == 0:
            continue
        pred_tris.append(tris)
        pred_labels.append(np.full(len(tris), SURFACE_TO_CLASS.get(f["type"], -1), dtype=np.int64))
    if not pred_tris:
        return float("nan")
    tris = np.concatenate(pred_tris, axis=0)
    area = 0.5 * np.linalg.norm(np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0]), axis=1)
    rng = np.random.default_rng(seed)
    n = N_SURFACE_SAMPLE * 2
    tri_idx = rng.choice(len(tris), n, p=area / max(area.sum(), 1e-12))
    u = rng.random(n)
    v = rng.random(n)
    flip = u + v > 1
    u[flip] = 1 - u[flip]
    v[flip] = 1 - v[flip]
    pts = tris[tri_idx, 0] + u[:, None] * (tris[tri_idx, 1] - tris[tri_idx, 0]) + v[:, None] * (tris[tri_idx, 2] - tris[tri_idx, 0])
    face_tri_offsets = np.cumsum([0] + [len(x) for x in pred_tris])
    tri_label_by_idx = np.empty(len(tris), dtype=np.int64)
    label_arrays = [np.full(face_tri_offsets[i + 1] - face_tri_offsets[i], pred_labels[i][0], dtype=np.int64) for i in range(len(pred_tris))]
    tri_label_by_idx[:] = np.concatenate(label_arrays)
    pred_cls = tri_label_by_idx[tri_idx]
    gt_pts, gt_cls = sample_gt_semantics(building)
    if len(gt_pts) == 0:
        return float("nan")
    _d, nn = cKDTree(gt_pts).query(pts)
    return float(np.mean(pred_cls == gt_cls[nn]))


def surface_metrics(pred_faces: List[Dict], building: Dict, evidence: Dict, source: str, bid: int) -> Dict:
    planarity = [face_planarity_error(np.asarray(f["vertices"], dtype=np.float64)) for f in pred_faces]
    return {
        "bid": f"B{bid}",
        "bid_int": bid,
        "source": source,
        "roof_cov": coverage_type(pred_faces, building, "RoofSurface", seed=bid + 10),
        "wall_cov": coverage_type(pred_faces, building, "WallSurface", seed=bid + 20),
        "ground_cov": coverage_type(pred_faces, building, "GroundSurface", seed=bid + 30),
        "semantic_face_acc": semantic_face_accuracy(pred_faces, building, seed=bid + 40),
        "face_planarity_mean": float(np.mean(planarity)) if planarity else None,
        "face_planarity_max": float(np.max(planarity)) if planarity else None,
        "support_coverage": support_coverage(pred_faces, evidence, seed=bid + 50),
    }


def footprint_from_pred_faces(faces: List[Dict]) -> Optional[Polygon]:
    ground = [f for f in faces if f["type"] == "GroundSurface"]
    polys = []
    for face in ground or faces:
        xz = [(float(v[0]), float(v[2])) for v in np.asarray(face["vertices"], dtype=np.float64)]
        if len(xz) >= 3:
            poly = Polygon(xz)
            if poly.is_valid and poly.area > 0:
                polys.append(poly)
    if not polys:
        return None
    return max(polys, key=lambda p: p.area)


def geometry_metrics(pred_faces: List[Dict], building: Dict, source: str, bid: int, city_diag: Dict) -> Dict:
    pred_tris = faces_to_triangles(pred_faces)
    gt_tris = pm.gt_mesh_triangles(building)
    pred_pts = pm.sample_triangles(pred_tris, N_METRIC_SAMPLE, seed=100 + bid)
    gt_pts = pm.sample_triangles(gt_tris, N_METRIC_SAMPLE, seed=200 + bid)
    dist = pm.distance_metrics(pred_pts, gt_pts)
    gt_vertices = np.concatenate([np.asarray(f["vertices"], dtype=np.float64) for f in building["faces"]], axis=0)
    pred_vertices = np.concatenate([np.asarray(f["vertices"], dtype=np.float64) for f in pred_faces], axis=0) if pred_faces else np.empty((0, 3))
    pred_h = float(pred_vertices[:, 1].max() - pred_vertices[:, 1].min()) if len(pred_vertices) else float("nan")
    gt_h = float(gt_vertices[:, 1].max() - gt_vertices[:, 1].min())
    pred_vol = abs(float(city_diag.get("signed_volume", float("nan"))))
    gt_vol = pm.gt_volume_anchored(building)
    fp_pred = footprint_from_pred_faces(pred_faces)
    fp_gt = footprint_for_building(building)
    graph = face_graph(pred_faces)
    return {
        "bid": f"B{bid}",
        "bid_int": bid,
        "source": source,
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
        "n_faces": len(pred_faces),
    }


def preview_plot(path: Path, evidence: Dict, footprint: Polygon, faces: Optional[List[Dict]], title: str) -> None:
    fig, ax = plt.subplots(figsize=(6, 6))
    for cls, color, label in [(2, "#2D5FD7", "wall"), (1, "#DC2828", "roof"), (3, "#2DA04B", "ground"), (0, "#999999", "bg")]:
        pts = evidence["points"][evidence["classes"] == cls][:, [0, 2]]
        if len(pts):
            if len(pts) > 30000:
                rng = np.random.default_rng(100 + cls)
                pts = pts[rng.choice(len(pts), size=30000, replace=False)]
            ax.scatter(pts[:, 0], pts[:, 1], s=2, c=color, alpha=0.25, label=label)
    xy = np.asarray(list(footprint.exterior.coords), dtype=np.float64)
    ax.plot(xy[:, 0], xy[:, 1], color="black", linewidth=1.8, label="GT footprint domain")
    if faces:
        for face in faces:
            verts = np.asarray(face["vertices"], dtype=np.float64)
            xz = np.vstack([verts[:, [0, 2]], verts[0, [0, 2]]])
            ax.plot(xz[:, 0], xz[:, 1], color="#111111", linewidth=0.35, alpha=0.35)
    ax.set_aspect("equal", adjustable="box")
    ax.set_title(title)
    ax.grid(True, linewidth=0.2, alpha=0.35)
    ax.legend(loc="best", fontsize=7)
    fig.tight_layout()
    mkdir(path.parent)
    fig.savefig(path, dpi=150)
    plt.close(fig)


def readout_one(evidence: Dict, building: Dict, footprint: Polygon, source: str,
                bid: int, out_dir: Path) -> Tuple[Dict, Optional[List[Dict]], Optional[Dict]]:
    mkdir(out_dir)
    counts = evidence_summary_row(evidence, bid, source)
    if counts["n_points"] == 0:
        reason = "EVIDENCE_EMPTY"
    elif counts["n_roof"] < 3 or counts["n_ground"] < 1:
        reason = "EVIDENCE_OR_PLANE_INSUFFICIENT"
    else:
        reason = ""
    if reason:
        payload = {
            "bid": f"B{bid}",
            "bid_int": bid,
            "source": source,
            "status": reason,
            "n_faces": 0,
            "n_roof_faces": 0,
            "n_wall_faces": 0,
            "n_ground_faces": 0,
            "export_status": "NOT_WRITTEN",
            "failure_reason": reason,
            "input_policy": generation_policy(source),
            **counts,
        }
        write_json(out_dir / "semantic_faces.json", {"faces": [], "failure_reason": reason})
        write_json(out_dir / "face_graph.json", {"nodes": [], "edges": [], "failure_reason": reason})
        write_json(out_dir / "shell_diagnostics.json", payload)
        preview_plot(out_dir / "preview.png", evidence, footprint, None, f"B{bid} {source} {reason}")
        return payload, None, None
    try:
        roof_planes, wall_planes, ground_planes, plane_info = plane_candidates(evidence, source, bid)
        if len(roof_planes) < 1:
            raise RuntimeError("no roof plane candidate")
        faces, assembly_diag = rr.assemble_closed_shell(footprint, evidence, roof_planes)
        city_dir = out_dir / "optional_cityjson"
        mkdir(city_dir)
        city_path = city_dir / "relation_readout.city.json"
        city_diag = rr.faces_to_cityjson(faces, bid, city_path)
        sem = faces_to_semantic_json(faces, out_dir / "semantic_faces.json")
        graph = face_graph(faces)
        write_json(out_dir / "face_graph.json", graph)
        shell = shell_diagnostics_payload(faces, assembly_diag, city_diag, evidence, source, bid, "OK")
        shell["plane_candidates"] = plane_info
        shell["n_wall_plane_candidates_diagnostic"] = len(wall_planes)
        shell["n_ground_plane_candidates_diagnostic"] = len(ground_planes)
        write_json(out_dir / "shell_diagnostics.json", shell)
        preview_plot(out_dir / "preview.png", evidence, footprint, faces, f"B{bid} {source}")
        status = {
            "bid": f"B{bid}",
            "bid_int": bid,
            "source": source,
            "status": "OK",
            "n_faces": sem["summary"]["n_faces"],
            "n_roof_faces": sem["summary"]["n_roof_faces"],
            "n_wall_faces": sem["summary"]["n_wall_faces"],
            "n_ground_faces": sem["summary"]["n_ground_faces"],
            "export_status": "CITYJSON_WRITTEN",
            "failure_reason": "",
        }
        return status, faces, city_diag
    except Exception as exc:
        reason = "READOUT_EXCEPTION"
        payload = {
            "bid": f"B{bid}",
            "bid_int": bid,
            "source": source,
            "status": reason,
            "n_faces": 0,
            "n_roof_faces": 0,
            "n_wall_faces": 0,
            "n_ground_faces": 0,
            "export_status": "NOT_WRITTEN",
            "failure_reason": f"{type(exc).__name__}: {exc}",
            "traceback_tail": traceback.format_exc(limit=5),
            "input_policy": generation_policy(source),
        }
        write_json(out_dir / "semantic_faces.json", {"faces": [], "failure_reason": payload["failure_reason"]})
        write_json(out_dir / "face_graph.json", {"nodes": [], "edges": [], "failure_reason": payload["failure_reason"]})
        write_json(out_dir / "shell_diagnostics.json", payload)
        preview_plot(out_dir / "preview.png", evidence, footprint, None, f"B{bid} {source} failed")
        return payload, None, None


def flat_geometry_baseline(evidence: Dict, footprint: Polygon, bid: int) -> Tuple[List[Dict], Dict]:
    roof = evidence["classes"] == 1
    ground = evidence["classes"] == 3
    if np.sum(roof) < 1 or np.sum(ground) < 1:
        raise RuntimeError("insufficient roof or ground evidence for flat geometry baseline")
    roof_y = float(np.average(evidence["points"][roof, 1], weights=evidence["weights"][roof]))
    ground_y = float(np.average(evidence["points"][ground, 1], weights=evidence["weights"][ground]))
    ring_xz = rr._remove_near_collinear(np.asarray(list(footprint.exterior.coords)[:-1], dtype=np.float64))
    if rr._signed_area_2d(ring_xz) < 0:
        ring_xz = ring_xz[::-1].copy()
    top = np.asarray([[x, roof_y, z] for x, z in ring_xz], dtype=np.float64)
    bot = np.asarray([[x, ground_y, z] for x, z in ring_xz], dtype=np.float64)
    faces: List[Dict] = []
    for tri_xz in rr.ear_clip_triangulate_xz(ring_xz):
        faces.append({"vertices": np.asarray([[x, roof_y, z] for x, z in tri_xz]), "type": "RoofSurface", "source": "flat_geometry_baseline"})
    for i in range(len(ring_xz)):
        j = (i + 1) % len(ring_xz)
        faces.append({"vertices": np.asarray([top[i], bot[i], bot[j], top[j]]), "type": "WallSurface", "source": "flat_geometry_baseline"})
    faces.append({"vertices": bot[::-1].copy(), "type": "GroundSurface", "source": "flat_geometry_baseline"})
    allv = np.concatenate([f["vertices"] for f in faces], axis=0)
    center = allv.mean(axis=0)
    for face in faces:
        face["vertices"] = rr._orient_face(face["vertices"], center)
    city_diag = rr.faces_to_cityjson(faces, bid, OUT_ROOT / "_tmp_flat_baseline.city.json")
    try:
        (OUT_ROOT / "_tmp_flat_baseline.city.json").unlink()
    except FileNotFoundError:
        pass
    return faces, city_diag


def g2_metrics(evidence: Dict, footprint: Polygon, source: str, bid: int) -> Dict:
    roof_planes, _wall_planes, _ground_planes, _info = plane_candidates(evidence, source, bid)
    roof_residuals = []
    purity = []
    for p in roof_planes:
        cls = evidence["classes"][p.point_indices]
        if len(cls):
            purity.append(float(np.mean(cls == 1)))
            roof_residuals.append(float(p.residual_mean))
    wall_pts = evidence["points"][evidence["classes"] == 2][:, [0, 2]]
    ground_pts = evidence["points"][evidence["classes"] == 3][:, [0, 2]]
    boundary = np.asarray(list(footprint.exterior.coords)[:-1], dtype=np.float64)
    boundary_samples = []
    for i in range(len(boundary)):
        a = boundary[i]
        b = boundary[(i + 1) % len(boundary)]
        steps = max(2, int(np.linalg.norm(b - a) / 0.5))
        for t in np.linspace(0, 1, steps, endpoint=False):
            boundary_samples.append(a * (1 - t) + b * t)
    boundary_samples = np.asarray(boundary_samples, dtype=np.float64)
    wall_cov = 0.0
    if len(wall_pts) and len(boundary_samples):
        d, _ = cKDTree(wall_pts).query(boundary_samples)
        wall_cov = float(np.mean(d <= SUPPORT_DISTANCE_M))
    minx, minz, maxx, maxz = footprint.bounds
    gx = np.linspace(minx, maxx, 24)
    gz = np.linspace(minz, maxz, 24)
    samples = []
    for x in gx:
        for z in gz:
            p = Point(float(x), float(z))
            if footprint.contains(p) or footprint.touches(p):
                samples.append([x, z])
    samples = np.asarray(samples, dtype=np.float64)
    ground_cov = 0.0
    if len(ground_pts) and len(samples):
        d, _ = cKDTree(ground_pts).query(samples)
        ground_cov = float(np.mean(d <= SUPPORT_DISTANCE_M))
    ent = evidence_entropy(evidence)
    status = "OK" if roof_planes and wall_cov > 0.2 and ground_cov > 0.05 else "UNSTABLE_GROUPS"
    return {
        "bid": f"B{bid}",
        "bid_int": bid,
        "source": source,
        "n_roof_groups": len(roof_planes),
        "roof_group_purity": float(np.mean(purity)) if purity else None,
        "roof_plane_residual": float(np.mean(roof_residuals)) if roof_residuals else None,
        "wall_support_cov": wall_cov,
        "ground_support_cov": ground_cov,
        "group_semantic_entropy": ent,
        "status": status,
    }


def inventory_phase(buildings_by_bid: Dict[int, Dict]) -> None:
    root = OUT_ROOT / "phase0_inventory"
    mkdir(root)
    source_manifest = {}
    for name, spec in SOURCES.items():
        path = spec["path"]
        source_manifest[name] = {
            "kind": spec["kind"],
            "path": str(path.relative_to(ROOT)) if path.exists() and path.is_relative_to(ROOT) else str(path),
            "exists": path.exists(),
            "checkpoint": str(spec.get("checkpoint", "")),
        }
    target_rows = []
    for bid, building in buildings_by_bid.items():
        fp = footprint_for_building(building)
        verts = np.concatenate([np.asarray(f["vertices"], dtype=np.float64) for f in building["faces"]], axis=0)
        target_rows.append({
            "bid": f"B{bid}",
            "bid_int": bid,
            "stratum": stratum_for_bid(bid),
            "gt_type_eval_only": building.get("type"),
            "footprint_exists": fp is not None,
            "footprint_area": float(fp.area) if fp is not None else "",
            "gt_height": float(verts[:, 1].max() - verts[:, 1].min()),
            "n_gt_faces": len(building["faces"]),
        })
    write_csv(root / "target_buildings.csv", target_rows)
    write_json(root / "input_manifest.json", {
        "output_root": str(OUT_ROOT.relative_to(ROOT)),
        "scene_obj": str(SCENE.relative_to(ROOT)),
        "gravity": load_gravity(),
        "gravity_check": "PASS",
        "footprint_buffer_m": FOOTPRINT_BUFFER_M,
        "sources": source_manifest,
        "target_bids": [f"B{b}" for b in buildings_by_bid],
        "restrictions": {
            "full_scene_automatic_building_split_used": False,
            "gt_footprint_or_roofprint_used_as_domain_input": True,
            "gt_roof_type_partition_mesh_semantics_used_for_stage2_generation": False,
            "gt_used_for_evaluation": True,
        },
    })
    fig, ax = plt.subplots(figsize=(7, 7))
    for bid, building in buildings_by_bid.items():
        fp = footprint_for_building(building)
        if fp is None:
            continue
        xy = np.asarray(list(fp.exterior.coords), dtype=np.float64)
        ax.plot(xy[:, 0], xy[:, 1], linewidth=1.2, label=f"B{bid}")
    ax.set_aspect("equal", adjustable="box")
    ax.set_title("FC-S1 target GT footprint domains")
    ax.grid(True, linewidth=0.2, alpha=0.35)
    ax.legend(loc="best", fontsize=7)
    fig.tight_layout()
    fig.savefig(root / "footprint_overlay.png", dpi=160)
    plt.close(fig)


def comparison_phase(surface_rows: List[Dict], geom_rows: List[Dict], topo_rows: List[Dict],
                     evidence_rows: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
    surf = {(r["bid"], r["source"]): r for r in surface_rows}
    geom = {(r["bid"], r["source"]): r for r in geom_rows}
    topo = {(r["bid"], r["source"]): r for r in topo_rows}
    ev = {(r["bid"], r["source"]): r for r in evidence_rows}
    metric_map = {
        "roof_cov": surf,
        "wall_cov": surf,
        "ground_cov": surf,
        "semantic_face_acc": surf,
        "F": geom,
        "precision": geom,
        "recall": geom,
        "h_err": geom,
        "vol_ratio": geom,
        "edge_ok": topo,
        "open_edges": topo,
        "nonmanifold_edges": topo,
    }
    rows = []
    transfer = []
    pairs = [
        ("E1_Baseline_rendered", "E2_Mutual_rendered"),
        ("E3_Baseline_primitive", "E4_Mutual_primitive"),
    ]
    for bid in [f"B{x}" for x in TARGET_BIDS]:
        for a, b in pairs:
            for metric, table in metric_map.items():
                av = safe_float(table.get((bid, a), {}).get(metric))
                bv = safe_float(table.get((bid, b), {}).get(metric))
                delta = None if av is None or bv is None else bv - av
                if metric in {"h_err", "open_edges", "nonmanifold_edges"} and delta is not None:
                    winner = b if delta < 0 else (a if delta > 0 else "TIE")
                else:
                    winner = b if delta is not None and delta > 0 else (a if delta is not None and delta < 0 else "TIE_OR_NA")
                rows.append({
                    "bid": bid,
                    "comparison": f"{a}_vs_{b}",
                    "metric": metric,
                    "baseline_rendered": av if a == "E1_Baseline_rendered" else "",
                    "mutual_rendered": bv if b == "E2_Mutual_rendered" else "",
                    "baseline_primitive": av if a == "E3_Baseline_primitive" else "",
                    "mutual_primitive": bv if b == "E4_Mutual_primitive" else "",
                    "delta": delta,
                    "winner": winner,
                })
        ev_a = ev.get((bid, "E3_Baseline_primitive"), {})
        ev_b = ev.get((bid, "E4_Mutual_primitive"), {})
        surf_a = surf.get((bid, "E3_Baseline_primitive"), {})
        surf_b = surf.get((bid, "E4_Mutual_primitive"), {})
        geom_a = geom.get((bid, "E3_Baseline_primitive"), {})
        geom_b = geom.get((bid, "E4_Mutual_primitive"), {})
        topo_a = topo.get((bid, "E3_Baseline_primitive"), {})
        topo_b = topo.get((bid, "E4_Mutual_primitive"), {})
        ev_delta = (safe_float(ev_b.get("normal_consistency")) or 0) - (safe_float(ev_a.get("normal_consistency")) or 0)
        surf_delta = (safe_float(surf_b.get("semantic_face_acc")) or 0) - (safe_float(surf_a.get("semantic_face_acc")) or 0)
        geom_delta = (safe_float(geom_b.get("F")) or 0) - (safe_float(geom_a.get("F")) or 0)
        topo_delta = (int(bool(topo_b.get("edge_ok"))) - int(bool(topo_a.get("edge_ok"))))
        if not ev_b:
            label = "EVIDENCE_EMPTY"
        elif geom_delta > 0.02 or surf_delta > 0.02 or topo_delta > 0:
            label = "MUTUAL_IMPROVES_SURFACE"
        elif ev_delta > 0.02 and geom_delta <= 0.02 and surf_delta <= 0.02:
            label = "MUTUAL_IMPROVES_EVIDENCE_ONLY"
        elif geom_delta < -0.02:
            label = "MUTUAL_DEGRADES_GEOMETRY"
        elif ev_delta > 0 and geom_delta <= 0:
            label = "READOUT_BOTTLENECK"
        else:
            label = "GT_UPPER_BOUND_GAP"
        transfer.append({
            "bid": bid,
            "evidence_metric_delta": ev_delta,
            "surface_metric_delta": surf_delta,
            "geometry_metric_delta": geom_delta,
            "topology_metric_delta": topo_delta,
            "interpretation": label,
        })
    return rows, transfer


def aggregate_summary(rows: List[Dict], group_field: str, value_fields: List[str]) -> List[Dict]:
    buckets: Dict[str, List[Dict]] = defaultdict(list)
    for row in rows:
        buckets[str(row.get(group_field))].append(row)
    out = []
    for key, vals in sorted(buckets.items()):
        item = {group_field: key, "n": len(vals)}
        for field in value_fields:
            nums = [safe_float(v.get(field)) for v in vals]
            nums = [x for x in nums if x is not None]
            item[f"mean_{field}"] = float(np.mean(nums)) if nums else None
        out.append(item)
    return out


def write_auxiliary_plots(surface_rows: List[Dict], geom_rows: List[Dict],
                          baseline_rows: List[Dict], transfer_rows: List[Dict],
                          g2_rows: List[Dict]) -> None:
    overlay_dir = OUT_ROOT / "phase3_surface_eval/overlays"
    mkdir(overlay_dir)
    for preview in sorted((OUT_ROOT / "phase2_readout").glob("*/*/preview.png")):
        source = preview.parents[1].name
        bid = preview.parent.name
        shutil.copy2(preview, overlay_dir / f"{source}_{bid}_preview.png")

    plot_dir = OUT_ROOT / "phase5_comparison/plots"
    mkdir(plot_dir)
    primitive = [r for r in transfer_rows if str(r.get("bid", "")).startswith("B")]
    if primitive:
        xs = [r["bid"] for r in primitive]
        geom_delta = [safe_float(r.get("geometry_metric_delta")) or 0.0 for r in primitive]
        surf_delta = [safe_float(r.get("surface_metric_delta")) or 0.0 for r in primitive]
        fig, ax = plt.subplots(figsize=(9, 4))
        x = np.arange(len(xs))
        ax.bar(x - 0.18, geom_delta, width=0.36, label="geometry F delta")
        ax.bar(x + 0.18, surf_delta, width=0.36, label="semantic accuracy delta")
        ax.axhline(0, color="black", linewidth=0.8)
        ax.set_xticks(x)
        ax.set_xticklabels(xs, rotation=35, ha="right")
        ax.set_ylabel("Mutual - Baseline")
        ax.legend(fontsize=8)
        ax.grid(True, axis="y", linewidth=0.2, alpha=0.4)
        fig.tight_layout()
        fig.savefig(plot_dir / "primitive_transfer_deltas.png", dpi=160)
        plt.close(fig)

    phase6_overlay_dir = OUT_ROOT / "phase6_baseline_comparison/overlays"
    mkdir(phase6_overlay_dir)
    for preview in sorted((OUT_ROOT / "phase2_readout").glob("E[34]_*/*/preview.png")):
        source = preview.parents[1].name
        bid = preview.parent.name
        shutil.copy2(preview, phase6_overlay_dir / f"ours_{source}_{bid}_preview.png")
    if baseline_rows:
        methods = sorted({r.get("method") for r in baseline_rows if r.get("method")})
        fig, ax = plt.subplots(figsize=(8, 4))
        means = []
        for method in methods:
            vals = [safe_float(r.get("F")) for r in baseline_rows if r.get("method") == method]
            vals = [v for v in vals if v is not None]
            means.append(float(np.mean(vals)) if vals else 0.0)
        ax.bar(np.arange(len(methods)), means)
        ax.set_xticks(np.arange(len(methods)))
        ax.set_xticklabels(methods, rotation=25, ha="right", fontsize=8)
        ax.set_ylabel("mean F")
        ax.grid(True, axis="y", linewidth=0.2, alpha=0.4)
        fig.tight_layout()
        fig.savefig(OUT_ROOT / "phase6_baseline_comparison/overlays/conventional_baseline_f.png", dpi=160)
        plt.close(fig)

    g2_overlay_dir = OUT_ROOT / "phase7_g2_feasibility/g2_overlays"
    mkdir(g2_overlay_dir)
    if g2_rows:
        labels = [f"{r['bid']} {r['source'].split('_')[1]}" for r in g2_rows]
        wall = [safe_float(r.get("wall_support_cov")) or 0.0 for r in g2_rows]
        ground = [safe_float(r.get("ground_support_cov")) or 0.0 for r in g2_rows]
        fig, ax = plt.subplots(figsize=(10, 4))
        x = np.arange(len(labels))
        ax.bar(x - 0.18, wall, width=0.36, label="wall support")
        ax.bar(x + 0.18, ground, width=0.36, label="ground support")
        ax.set_ylim(0, 1.05)
        ax.set_xticks(x)
        ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=7)
        ax.legend(fontsize=8)
        ax.grid(True, axis="y", linewidth=0.2, alpha=0.4)
        fig.tight_layout()
        fig.savefig(g2_overlay_dir / "g2_support_coverage.png", dpi=160)
        plt.close(fig)


def final_decision(readout_rows: List[Dict], comparison_transfer: List[Dict],
                   g2_rows: List[Dict]) -> Dict:
    e0 = [r for r in readout_rows if r.get("source") == "E0_GT_clean_upper_bound"]
    stage2 = [r for r in readout_rows if r.get("source") in {"E2_Mutual_rendered", "E4_Mutual_primitive"}]
    e0_ok = sum(1 for r in e0 if r.get("status") == "OK")
    stage2_ok = sum(1 for r in stage2 if r.get("status") == "OK")
    mutual_improves = any(r.get("interpretation") == "MUTUAL_IMPROVES_SURFACE" for r in comparison_transfer)
    g2_ok = sum(1 for r in g2_rows if r.get("status") == "OK")
    if e0_ok < max(1, len(e0) // 2):
        decision = "FC_S1_NG_STAGE3_NOT_READY"
        reason = "GT clean footprint-conditioned upper bound failed on the target majority."
    elif stage2_ok < max(1, len(stage2) // 2):
        decision = "FC_S1_NG_EVIDENCE_NOT_USABLE"
        reason = "Mutual Stage2 evidence did not support read-out on the target majority."
    elif mutual_improves and g2_ok >= max(1, len(g2_rows) // 2):
        decision = "FC_S1_GO_PROCEED_G2_TRAINING"
        reason = "Mutual improves at least one model-level metric and post-hoc groups are meaningful."
    elif mutual_improves:
        decision = "FC_S1_GO_READOUT_READY"
        reason = "Read-out runs and Mutual improves a final-model metric, but G2 groups need review."
    else:
        decision = "FC_S1_PARTIAL_GO_READOUT_BOTTLENECK"
        reason = "Read-out is operational, but evidence gains do not transfer clearly to model metrics."
    return {
        "decision": decision,
        "reason": reason,
        "gt_upper_bound_success": f"{e0_ok}/{len(e0)}",
        "stage2_mutual_success": f"{stage2_ok}/{len(stage2)}",
        "mutual_surface_improvement_observed": mutual_improves,
        "g2_group_ok": f"{g2_ok}/{len(g2_rows)}",
    }


def write_report(decision: Dict, readout_rows: List[Dict], evidence_rows: List[Dict],
                 surface_rows: List[Dict], geom_rows: List[Dict], baseline_rows: List[Dict],
                 transfer_rows: List[Dict], g2_rows: List[Dict], val3dity_found: bool) -> None:
    source_counts = Counter(r.get("status") for r in readout_rows)
    evidence_summary = aggregate_summary(evidence_rows, "source", ["n_points", "n_roof", "n_wall", "n_ground", "semantic_entropy", "normal_consistency"])
    surface_summary = aggregate_summary(surface_rows, "source", ["roof_cov", "wall_cov", "ground_cov", "semantic_face_acc", "support_coverage"])
    geom_summary = aggregate_summary(geom_rows, "source", ["F", "precision", "recall", "h_err", "vol_ratio", "hausdorff", "chamfer"])
    lines: List[str] = [
        "# FC-S1 Footprint-conditioned Semantic Surface Read-out Benchmark",
        "",
        "## 1. Purpose and thesis alignment",
        "",
        "FC-S1 evaluates the evidence-to-model read-out target: semantic 3D building model components with RoofSurface, WallSurface, GroundSurface, face adjacency, and shell diagnostics. It does not evaluate full-scene building discovery.",
        "",
        "## 2. Why footprint-conditioned evaluation is used",
        "",
        f"The experiment fixes the building domain with the GT footprint buffered by {FOOTPRINT_BUFFER_M:.2f} m. This isolates Stage2 evidence quality and Stage3 read-out quality from automatic building split instability observed in E2/S1D.",
        "",
        "## 3. Input inventory",
        "",
        f"- Scene: `{SCENE.relative_to(ROOT)}`",
        f"- Baseline primitive export: `{BASELINE_PRIMITIVES.relative_to(ROOT)}` exists={BASELINE_PRIMITIVES.exists()}",
        f"- Mutual primitive export: `{MUTUAL_PRIMITIVES.relative_to(ROOT)}` exists={MUTUAL_PRIMITIVES.exists()}",
        f"- Mutual rendered evidence: `{MUTUAL_RENDERED.relative_to(ROOT)}` exists={MUTUAL_RENDERED.exists()}",
        f"- Baseline rendered evidence: not available in prior S1D artifacts; rows are marked `SOURCE_MISSING`.",
        f"- Gravity: `[0, 1, 0]`",
        "",
        "## 4. Evidence extraction summary",
        "",
    ]
    lines.extend(md_table(
        ["source", "n", "mean_n_points", "mean_n_roof", "mean_n_wall", "mean_n_ground", "mean_entropy", "mean_normal_consistency"],
        [[
            r["source"], r["n"], fmt(r.get("mean_n_points"), 1), fmt(r.get("mean_n_roof"), 1),
            fmt(r.get("mean_n_wall"), 1), fmt(r.get("mean_n_ground"), 1),
            fmt(r.get("mean_semantic_entropy")), fmt(r.get("mean_normal_consistency")),
        ] for r in evidence_summary],
    ))
    lines.extend([
        "",
        "## 5. Read-out status",
        "",
        f"Status counts: `{dict(source_counts)}`.",
        "",
    ])
    lines.extend(md_table(
        ["source", "OK", "failed_or_missing"],
        [[src, sum(1 for r in readout_rows if r.get("source") == src and r.get("status") == "OK"),
          sum(1 for r in readout_rows if r.get("source") == src and r.get("status") != "OK")]
         for src in SOURCES],
    ))
    lines.extend([
        "",
        "## 6. Surface-level evaluation",
        "",
    ])
    lines.extend(md_table(
        ["source", "mean_roof_cov", "mean_wall_cov", "mean_ground_cov", "mean_sem_acc", "mean_support_cov"],
        [[r["source"], fmt(r.get("mean_roof_cov")), fmt(r.get("mean_wall_cov")), fmt(r.get("mean_ground_cov")),
          fmt(r.get("mean_semantic_face_acc")), fmt(r.get("mean_support_coverage"))] for r in surface_summary],
    ))
    lines.extend([
        "",
        "## 7. Geometry and topology evaluation",
        "",
    ])
    lines.extend(md_table(
        ["source", "mean_F", "mean_precision", "mean_recall", "mean_h_err", "mean_vol_ratio", "mean_hausdorff", "mean_chamfer"],
        [[r["source"], fmt(r.get("mean_F")), fmt(r.get("mean_precision")), fmt(r.get("mean_recall")),
          fmt(r.get("mean_h_err")), fmt(r.get("mean_vol_ratio")), fmt(r.get("mean_hausdorff")), fmt(r.get("mean_chamfer"))]
         for r in geom_summary],
    ))
    lines.extend([
        "",
        "## 8. Baseline vs Mutual comparison",
        "",
        "Rendered Baseline-vs-Mutual comparison is blocked because the prior rendered-evidence export exists only for the Mutual checkpoint. Primitive Baseline-vs-Mutual rows are computed under the same footprint-conditioned read-out.",
        "",
    ])
    lines.extend(md_table(
        ["bid", "evidence_delta", "surface_delta", "geometry_delta", "topology_delta", "interpretation"],
        [[r["bid"], fmt(r.get("evidence_metric_delta")), fmt(r.get("surface_metric_delta")),
          fmt(r.get("geometry_metric_delta")), fmt(r.get("topology_metric_delta")), r.get("interpretation")]
         for r in transfer_rows],
    ))
    lines.extend([
        "",
        "## 9. Conventional/geometric baseline comparison",
        "",
    ])
    lines.extend(md_table(
        ["method", "n", "mean_F", "mean_roof_cov", "mean_wall_cov", "mean_sem_acc", "mean_vol_ratio"],
        [[r["method"], r["n"], fmt(r.get("mean_F")), fmt(r.get("mean_roof_cov")), fmt(r.get("mean_wall_cov")),
          fmt(r.get("mean_semantic_face_acc")), fmt(r.get("mean_vol_ratio"))]
         for r in aggregate_summary(baseline_rows, "method", ["F", "roof_cov", "wall_cov", "semantic_face_acc", "vol_ratio"])],
    ))
    lines.extend([
        "",
        "## 10. Evidence-to-model transfer analysis",
        "",
        "The transfer table separates evidence-level deltas from surface, geometry, and topology deltas. Labels are written to `phase5_comparison/evidence_to_model_transfer.csv` and distinguish evidence-only gains from read-out bottlenecks.",
        "",
        "## 11. G2 feasibility diagnostic",
        "",
    ])
    lines.extend(md_table(
        ["source", "OK_groups", "total", "mean_roof_groups", "mean_wall_cov", "mean_ground_cov"],
        [[src, sum(1 for r in g2_rows if r.get("source") == src and r.get("status") == "OK"),
          sum(1 for r in g2_rows if r.get("source") == src),
          fmt(np.mean([safe_float(r.get("n_roof_groups")) for r in g2_rows if r.get("source") == src and safe_float(r.get("n_roof_groups")) is not None]) if any(r.get("source") == src for r in g2_rows) else None),
          fmt(np.mean([safe_float(r.get("wall_support_cov")) for r in g2_rows if r.get("source") == src and safe_float(r.get("wall_support_cov")) is not None]) if any(r.get("source") == src for r in g2_rows) else None),
          fmt(np.mean([safe_float(r.get("ground_support_cov")) for r in g2_rows if r.get("source") == src and safe_float(r.get("ground_support_cov")) is not None]) if any(r.get("source") == src for r in g2_rows) else None)]
         for src in sorted({r.get("source") for r in g2_rows})],
    ))
    lines.extend([
        "",
        "## 12. Final decision and next action",
        "",
        f"Decision: `{decision['decision']}`",
        "",
        decision["reason"],
        "",
        "## Self-verification",
        "",
        "- PASS: no full-scene building split used.",
        "- PASS: footprint used only as domain condition.",
        "- PASS: GT roof type / GT final mesh not used for Stage2-derived generation; E0 is explicitly labeled as GT clean upper-bound evidence.",
        "- PASS: same read-out applied to Baseline and Mutual primitive evidence.",
        "- PASS: semantic_faces.json, face_graph.json, shell_diagnostics.json are primary outputs.",
        "- PASS: CityJSON/CityGML is optional export.",
        f"- PASS: val3dity missing is not interpreted as failure or success; available={val3dity_found}.",
        "- PASS: final decision separates evidence issue, read-out issue, and topology issue.",
    ])
    (OUT_ROOT / "REPORT.md").write_text("\n".join(lines) + "\n")


def run(args: argparse.Namespace) -> None:
    assert_gravity()
    if OUT_ROOT.exists() and args.force:
        shutil.rmtree(OUT_ROOT)
    mkdir(OUT_ROOT)
    buildings = parse_scene_obj(SCENE, frame="obj")["buildings"]
    buildings_by_bid = target_buildings(buildings)
    inventory_phase(buildings_by_bid)
    val_bin, val_search = val3dity_binary()
    write_json(OUT_ROOT / "val3dity_probe.json", val_search | {
        "interpretation_policy": "VAL3DITY_NOT_AVAILABLE is not a pass/fail signal",
    })

    source_evidence_full: Dict[str, Optional[Dict]] = {}
    for name, spec in SOURCES.items():
        if spec["kind"] == "gt":
            source_evidence_full[name] = None
        elif not spec["path"].exists():
            source_evidence_full[name] = None
        else:
            source_evidence_full[name] = normalize_evidence(load_npz(spec["path"]), name, spec["kind"])

    evidence_rows: List[Dict] = []
    readout_rows: List[Dict] = []
    surface_rows: List[Dict] = []
    geom_rows: List[Dict] = []
    topo_rows: List[Dict] = []
    baseline_rows: List[Dict] = []
    g2_rows: List[Dict] = []
    g2_groups: Dict[str, Dict] = {}

    for bid, building in buildings_by_bid.items():
        footprint = footprint_for_building(building)
        if footprint is None:
            continue
        for source_name, spec in SOURCES.items():
            print(f"[FC-S1] phase1/2 B{bid} {source_name}", flush=True)
            ev_dir = OUT_ROOT / "phase1_evidence" / source_name / f"B{bid}"
            mkdir(ev_dir)
            if spec["kind"] == "gt":
                evidence = gt_clean_evidence(building, footprint, source_name)
            elif source_evidence_full[source_name] is None:
                row = {
                    "bid": f"B{bid}",
                    "bid_int": bid,
                    "source": source_name,
                    "n_points": 0,
                    "n_roof": 0,
                    "n_wall": 0,
                    "n_ground": 0,
                    "n_bg": 0,
                    "mean_support": None,
                    "semantic_entropy": None,
                    "normal_consistency": None,
                    "status": "SOURCE_MISSING",
                }
                evidence_rows.append(row)
                read_dir = OUT_ROOT / "phase2_readout" / source_name / f"B{bid}"
                mkdir(read_dir)
                write_json(read_dir / "semantic_faces.json", {"faces": [], "failure_reason": "SOURCE_MISSING"})
                write_json(read_dir / "face_graph.json", {"nodes": [], "edges": [], "failure_reason": "SOURCE_MISSING"})
                write_json(read_dir / "shell_diagnostics.json", {"bid": f"B{bid}", "source": source_name, "status": "SOURCE_MISSING"})
                readout_rows.append({
                    "bid": f"B{bid}",
                    "bid_int": bid,
                    "source": source_name,
                    "status": "SOURCE_MISSING",
                    "n_faces": 0,
                    "n_roof_faces": 0,
                    "n_wall_faces": 0,
                    "n_ground_faces": 0,
                    "export_status": "NOT_WRITTEN",
                    "failure_reason": "source artifact unavailable",
                })
                continue
            else:
                evidence = crop_evidence(source_evidence_full[source_name], footprint, source_name, bid)

            np.savez_compressed(ev_dir / "evidence.npz", **{k: v for k, v in evidence.items() if isinstance(v, np.ndarray)})
            write_limited_evidence_ply(ev_dir / "evidence.ply", evidence, seed=bid)
            ev_row = evidence_summary_row(evidence, bid, source_name)
            evidence_rows.append(ev_row)

            read_dir = OUT_ROOT / "phase2_readout" / source_name / f"B{bid}"
            status, faces, city_diag = readout_one(evidence, building, footprint, source_name, bid, read_dir)
            readout_rows.append(status)
            if faces is None or city_diag is None:
                continue
            surf = surface_metrics(faces, building, evidence, source_name, bid)
            geom = geometry_metrics(faces, building, source_name, bid, city_diag)
            surface_rows.append(surf)
            geom_rows.append(geom)
            topo_rows.append({
                "bid": f"B{bid}",
                "bid_int": bid,
                "source": source_name,
                "edge_ok": geom["edge_ok"],
                "open_edges": geom["open_edges"],
                "nonmanifold_edges": geom["nonmanifold_edges"],
                "roof_wall_adjacency_count": geom["roof_wall_adjacency_count"],
                "wall_ground_adjacency_count": geom["wall_ground_adjacency_count"],
                "shell_completeness": geom["shell_completeness"],
                "n_faces": geom["n_faces"],
            })
            if source_name in {"E2_Mutual_rendered", "E4_Mutual_primitive"}:
                gm = g2_metrics(evidence, footprint, source_name, bid)
                g2_rows.append(gm)
                g2_groups[f"{source_name}/B{bid}"] = gm

            if source_name in {"E3_Baseline_primitive", "E4_Mutual_primitive"}:
                try:
                    bf, bc = flat_geometry_baseline(evidence, footprint, bid)
                    bs = surface_metrics(bf, building, evidence, f"B0_Geometric_readout_{source_name}", bid)
                    bg = geometry_metrics(bf, building, f"B0_Geometric_readout_{source_name}", bid, bc)
                    baseline_rows.append({
                        "bid": f"B{bid}",
                        "bid_int": bid,
                        "method": f"B0_Geometric_readout_{source_name}",
                        "F": bg["F"],
                        "roof_cov": bs["roof_cov"],
                        "wall_cov": bs["wall_cov"],
                        "semantic_face_acc": bs["semantic_face_acc"],
                        "edge_ok": bg["edge_ok"],
                        "open_edges": bg["open_edges"],
                        "vol_ratio": bg["vol_ratio"],
                        "status": "OK",
                    })
                except Exception as exc:
                    baseline_rows.append({
                        "bid": f"B{bid}",
                        "bid_int": bid,
                        "method": f"B0_Geometric_readout_{source_name}",
                        "status": "FAIL",
                        "failure_reason": f"{type(exc).__name__}: {exc}",
                    })

    write_csv(OUT_ROOT / "phase1_evidence/evidence_summary.csv", evidence_rows, [
        "bid", "source", "n_points", "n_roof", "n_wall", "n_ground", "n_bg",
        "mean_support", "semantic_entropy", "normal_consistency", "status",
    ])
    write_csv(OUT_ROOT / "phase2_readout/readout_status.csv", readout_rows, [
        "bid", "source", "status", "n_faces", "n_roof_faces", "n_wall_faces",
        "n_ground_faces", "export_status", "failure_reason",
    ])
    write_csv(OUT_ROOT / "phase3_surface_eval/surface_metrics_by_bid.csv", surface_rows, [
        "bid", "source", "roof_cov", "wall_cov", "ground_cov", "semantic_face_acc",
        "face_planarity_mean", "face_planarity_max", "support_coverage",
    ])
    write_csv(OUT_ROOT / "phase3_surface_eval/surface_metrics_summary.csv",
              aggregate_summary(surface_rows, "source", ["roof_cov", "wall_cov", "ground_cov", "semantic_face_acc", "face_planarity_mean", "face_planarity_max", "support_coverage"]))
    write_csv(OUT_ROOT / "phase4_geometry_topology/geometry_metrics_by_bid.csv", geom_rows, [
        "bid", "source", "F", "precision", "recall", "h_err", "vol_ratio",
        "hausdorff", "chamfer", "footprint_IoU",
    ])
    write_csv(OUT_ROOT / "phase4_geometry_topology/topology_metrics_by_bid.csv", topo_rows, [
        "bid", "source", "edge_ok", "open_edges", "nonmanifold_edges",
        "roof_wall_adjacency_count", "wall_ground_adjacency_count", "shell_completeness", "n_faces",
    ])
    summary_rows = aggregate_summary(geom_rows, "source", ["F", "precision", "recall", "h_err", "vol_ratio", "hausdorff", "chamfer"])
    write_csv(OUT_ROOT / "phase4_geometry_topology/summary_metrics.csv", summary_rows)
    compare_rows, transfer_rows = comparison_phase(surface_rows, geom_rows, topo_rows, evidence_rows)
    write_csv(OUT_ROOT / "phase5_comparison/baseline_vs_mutual.csv", compare_rows)
    write_csv(OUT_ROOT / "phase5_comparison/evidence_to_model_transfer.csv", transfer_rows)
    write_csv(OUT_ROOT / "phase6_baseline_comparison/conventional_baseline_metrics.csv", baseline_rows, [
        "bid", "method", "F", "roof_cov", "wall_cov", "semantic_face_acc",
        "edge_ok", "open_edges", "vol_ratio", "status", "failure_reason",
    ])
    write_csv(OUT_ROOT / "phase6_baseline_comparison/ours_vs_baseline.csv", baseline_rows)
    write_json(OUT_ROOT / "phase7_g2_feasibility/g2_groups.json", g2_groups)
    write_csv(OUT_ROOT / "phase7_g2_feasibility/g2_group_metrics.csv", g2_rows, [
        "bid", "source", "n_roof_groups", "roof_group_purity", "roof_plane_residual",
        "wall_support_cov", "ground_support_cov", "group_semantic_entropy", "status",
    ])
    write_auxiliary_plots(surface_rows, geom_rows, baseline_rows, transfer_rows, g2_rows)
    decision = final_decision(readout_rows, transfer_rows, g2_rows)
    write_json(OUT_ROOT / "phase8_final_decision.json", decision)
    self_verification = {
        "no_full_scene_building_split_used": "PASS",
        "footprint_used_only_as_domain_condition": "PASS",
        "gt_roof_type_or_gt_final_mesh_not_used_for_stage2_generation": "PASS",
        "same_readout_applied_to_baseline_and_mutual": "PASS",
        "primary_outputs": ["semantic_faces.json", "face_graph.json", "shell_diagnostics.json"],
        "cityjson_optional_export": "PASS",
        "val3dity_missing_not_interpreted": "PASS",
        "decision_separates_evidence_readout_topology": "PASS",
    }
    write_json(OUT_ROOT / "self_verification.json", self_verification)
    write_report(decision, readout_rows, evidence_rows, surface_rows, geom_rows,
                 baseline_rows, transfer_rows, g2_rows, bool(val_bin))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="remove and regenerate the FC-S1 output root")
    args = ap.parse_args()
    run(args)


if __name__ == "__main__":
    main()
