"""P1-4a preflight: val3dity availability plus precision-side metrics.

This script reuses the existing P1-4a Part B artifacts without rebuilding the
relation read-out. It writes per-building preflight JSON files and the requested
VAL3DITY_AND_PRECISION_REPORT.md.
"""
from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np
from scipy.spatial import cKDTree
from shapely.geometry import MultiPolygon, Polygon
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.stage3_readout.obj_gt import parse_scene_obj  # noqa: E402


SCENE = ROOT / "results/phase2_synthesis/scene.obj"
OUT_ROOT = ROOT / "results/stage3_typed_readout/P1_4a_gt_sanity"
REPORT_PATH = OUT_ROOT / "VAL3DITY_AND_PRECISION_REPORT.md"
SUMMARY_JSON = OUT_ROOT / "preflight_precision_metrics.json"
TARGET_BIDS = [1, 2, 8, 6, 0, 3]
SIMPLE_MEDIUM_BIDS = [1, 2, 8, 0]
SURFACE_THRESH_M = 0.5
N_SAMPLE = 6000
VAL3DITY_DOCS = "https://val3dity.readthedocs.io/main/install.html"
VAL3DITY_USAGE = "https://val3dity.readthedocs.io/main/usage.html"
VAL3DITY_GITHUB = "https://github.com/tudelft3d/val3dity"


def _fmt(v: object, nd: int = 4) -> str:
    if v is None:
        return "NA"
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return "NA"
    if isinstance(v, (int, np.integer)):
        return str(int(v))
    if isinstance(v, bool):
        return "True" if v else "False"
    try:
        return f"{float(v):.{nd}f}"
    except (TypeError, ValueError):
        return str(v)


def _jsonable(obj: object) -> object:
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, np.generic):
        return obj.item()
    return obj


def triangulate_polygon(vertices: np.ndarray) -> np.ndarray:
    vertices = np.asarray(vertices, dtype=np.float64)
    if len(vertices) < 3:
        return np.empty((0, 3, 3), dtype=np.float64)
    return np.asarray(
        [[vertices[0], vertices[i], vertices[i + 1]]
         for i in range(1, len(vertices) - 1)],
        dtype=np.float64,
    )


def triangle_area(triangles: np.ndarray) -> float:
    if len(triangles) == 0:
        return 0.0
    e1 = triangles[:, 1] - triangles[:, 0]
    e2 = triangles[:, 2] - triangles[:, 0]
    return float((0.5 * np.linalg.norm(np.cross(e1, e2), axis=1)).sum())


def sample_triangles(triangles: np.ndarray, n: int, seed: int) -> np.ndarray:
    if len(triangles) == 0:
        return np.empty((0, 3), dtype=np.float64)
    e1 = triangles[:, 1] - triangles[:, 0]
    e2 = triangles[:, 2] - triangles[:, 0]
    areas = 0.5 * np.linalg.norm(np.cross(e1, e2), axis=1)
    total = float(areas.sum())
    if total <= 0.0:
        return np.empty((0, 3), dtype=np.float64)
    rng = np.random.default_rng(seed)
    tri_idx = rng.choice(len(triangles), n, p=areas / total)
    u = rng.random(n)
    v = rng.random(n)
    flip = u + v > 1.0
    u[flip] = 1.0 - u[flip]
    v[flip] = 1.0 - v[flip]
    return (
        triangles[tri_idx, 0]
        + u[:, None] * (triangles[tri_idx, 1] - triangles[tri_idx, 0])
        + v[:, None] * (triangles[tri_idx, 2] - triangles[tri_idx, 0])
    )


def polygon_area_3d(poly: np.ndarray) -> float:
    return triangle_area(triangulate_polygon(poly))


def gt_mesh_triangles(building: Dict) -> np.ndarray:
    tris = []
    for face in building["faces"]:
        tris.append(triangulate_polygon(np.asarray(face["vertices"], dtype=np.float64)))
    return np.concatenate(tris, axis=0) if tris else np.empty((0, 3, 3), dtype=np.float64)


def gt_volume_anchored(building: Dict) -> float:
    faces = building["faces"]
    all_v = np.concatenate([np.asarray(f["vertices"], dtype=np.float64) for f in faces])
    c0 = all_v.mean(axis=0)
    vol = 0.0
    for face in faces:
        verts = np.asarray(face["vertices"], dtype=np.float64).copy()
        n = np.asarray(face["normal"], dtype=np.float64)
        n /= np.linalg.norm(n) + 1e-12
        if float(np.dot(n, np.asarray(face["centroid"], dtype=np.float64) - c0)) < 0:
            verts = verts[::-1]
        v0 = verts[0] - c0
        for i in range(1, len(verts) - 1):
            vol += float(np.dot(v0, np.cross(verts[i] - c0, verts[i + 1] - c0))) / 6.0
    return abs(vol)


def cityjson_vertices(cj: Dict) -> np.ndarray:
    scale = np.asarray(cj.get("transform", {}).get("scale", [1.0, 1.0, 1.0]), dtype=np.float64)
    translate = np.asarray(cj.get("transform", {}).get("translate", [0.0, 0.0, 0.0]), dtype=np.float64)
    return np.asarray(cj["vertices"], dtype=np.float64) * scale + translate


def _surface_semantic_type(geom: Dict, shell_idx: int, surf_idx: int) -> str:
    semantics = geom.get("semantics") or {}
    surfaces = semantics.get("surfaces") or []
    values = semantics.get("values")
    sem_idx = None
    if isinstance(values, list):
        try:
            if geom.get("type") in {"Solid", "MultiSolid", "CompositeSolid"}:
                sem_idx = values[shell_idx][surf_idx]
            else:
                sem_idx = values[surf_idx]
        except (IndexError, TypeError):
            sem_idx = None
    if isinstance(sem_idx, list):
        sem_idx = sem_idx[0] if sem_idx else None
    if isinstance(sem_idx, int) and 0 <= sem_idx < len(surfaces):
        return str(surfaces[sem_idx].get("type", "UnknownSurface"))
    return "UnknownSurface"


def cityjson_faces(cj_path: Path) -> Tuple[np.ndarray, List[Dict]]:
    cj = json.loads(cj_path.read_text())
    vertices = cityjson_vertices(cj)
    faces: List[Dict] = []
    for coid, cobj in cj.get("CityObjects", {}).items():
        for geom_idx, geom in enumerate(cobj.get("geometry", [])):
            boundaries = geom.get("boundaries", [])
            geom_type = geom.get("type")
            if geom_type in {"Solid", "CompositeSurface"}:
                shells = boundaries if geom_type == "Solid" else [boundaries]
                for shell_idx, shell in enumerate(shells):
                    for surf_idx, surface in enumerate(shell):
                        rings = surface if surface and isinstance(surface[0], list) else [surface]
                        if not rings:
                            continue
                        outer = rings[0]
                        faces.append({
                            "city_object": coid,
                            "geometry_index": geom_idx,
                            "shell_index": shell_idx,
                            "surface_index": surf_idx,
                            "rings": rings,
                            "outer": outer,
                            "vertices": vertices[np.asarray(outer, dtype=np.int64)],
                            "semantic_type": _surface_semantic_type(geom, shell_idx, surf_idx),
                        })
            elif geom_type == "MultiSurface":
                for surf_idx, surface in enumerate(boundaries):
                    rings = surface if surface and isinstance(surface[0], list) else [surface]
                    if not rings:
                        continue
                    outer = rings[0]
                    faces.append({
                        "city_object": coid,
                        "geometry_index": geom_idx,
                        "shell_index": 0,
                        "surface_index": surf_idx,
                        "rings": rings,
                        "outer": outer,
                        "vertices": vertices[np.asarray(outer, dtype=np.int64)],
                        "semantic_type": _surface_semantic_type(geom, 0, surf_idx),
                    })
    return vertices, faces


def cityjson_mesh_triangles(cj_path: Path) -> np.ndarray:
    _vertices, faces = cityjson_faces(cj_path)
    tris = [triangulate_polygon(f["vertices"]) for f in faces]
    return np.concatenate(tris, axis=0) if tris else np.empty((0, 3, 3), dtype=np.float64)


def distance_metrics(pred_pts: np.ndarray, gt_pts: np.ndarray) -> Dict:
    if len(pred_pts) == 0 or len(gt_pts) == 0:
        return {
            "recall_coverage": float("nan"),
            "pred_precision": float("nan"),
            "F_score": float("nan"),
            "hausdorff": float("nan"),
            "chamfer": float("nan"),
        }
    gt_tree = cKDTree(gt_pts)
    pred_tree = cKDTree(pred_pts)
    d_pred_to_gt, _ = gt_tree.query(pred_pts)
    d_gt_to_pred, _ = pred_tree.query(gt_pts)
    recall = float(np.mean(d_gt_to_pred <= SURFACE_THRESH_M))
    precision = float(np.mean(d_pred_to_gt <= SURFACE_THRESH_M))
    denom = precision + recall
    f_score = float(2.0 * precision * recall / denom) if denom > 0 else 0.0
    return {
        "recall_coverage": recall,
        "pred_precision": precision,
        "F_score": f_score,
        "hausdorff": float(max(d_pred_to_gt.max(), d_gt_to_pred.max())),
        "chamfer": float(0.5 * (d_pred_to_gt.mean() + d_gt_to_pred.mean())),
    }


def bbox_iou(pred_vertices: np.ndarray, gt_vertices: np.ndarray) -> float:
    if len(pred_vertices) == 0 or len(gt_vertices) == 0:
        return float("nan")
    pmin, pmax = pred_vertices.min(axis=0), pred_vertices.max(axis=0)
    gmin, gmax = gt_vertices.min(axis=0), gt_vertices.max(axis=0)
    inter_dims = np.maximum(0.0, np.minimum(pmax, gmax) - np.maximum(pmin, gmin))
    inter = float(np.prod(inter_dims))
    pvol = float(np.prod(np.maximum(0.0, pmax - pmin)))
    gvol = float(np.prod(np.maximum(0.0, gmax - gmin)))
    union = pvol + gvol - inter
    return inter / union if union > 0 else float("nan")


def footprint_from_cityjson_faces(faces: List[Dict]) -> Optional[Polygon]:
    polygons = []
    for face in faces:
        if face["semantic_type"] != "GroundSurface":
            continue
        xz = [(float(p[0]), float(p[2])) for p in face["vertices"]]
        if len(xz) >= 3:
            poly = Polygon(xz)
            if poly.is_valid and poly.area > 0:
                polygons.append(poly)
    if not polygons:
        return None
    geom = unary_union(polygons)
    if isinstance(geom, Polygon):
        return geom
    if isinstance(geom, MultiPolygon):
        return max(geom.geoms, key=lambda g: g.area)
    return None


def footprint_from_gt(building: Dict) -> Optional[Polygon]:
    polygons = []
    for face in building["faces"]:
        if int(face.get("semantic_class", -1)) != 3:
            continue
        verts = np.asarray(face["vertices"], dtype=np.float64)
        xz = [(float(p[0]), float(p[2])) for p in verts]
        if len(xz) >= 3:
            poly = Polygon(xz)
            if poly.is_valid and poly.area > 0:
                polygons.append(poly)
    if not polygons:
        return None
    geom = unary_union(polygons)
    if isinstance(geom, Polygon):
        return geom
    if isinstance(geom, MultiPolygon):
        return max(geom.geoms, key=lambda g: g.area)
    return None


def polygon_iou(a: Optional[Polygon], b: Optional[Polygon]) -> float:
    if a is None or b is None or a.is_empty or b.is_empty:
        return float("nan")
    inter = float(a.intersection(b).area)
    union = float(a.union(b).area)
    return inter / union if union > 0 else float("nan")


def face_planarity_max_error(faces: List[Dict]) -> float:
    max_err = 0.0
    for face in faces:
        pts = np.asarray(face["vertices"], dtype=np.float64)
        if len(pts) <= 3:
            continue
        c = pts.mean(axis=0)
        try:
            _u, _s, vh = np.linalg.svd(pts - c, full_matrices=False)
        except np.linalg.LinAlgError:
            continue
        n = vh[-1]
        n_norm = np.linalg.norm(n)
        if n_norm <= 1e-12:
            continue
        n /= n_norm
        max_err = max(max_err, float(np.max(np.abs((pts - c) @ n))))
    return max_err


def edge_incidence(faces: List[Dict]) -> Dict:
    counts: Counter[Tuple[int, int]] = Counter()
    for face in faces:
        for ring in face["rings"]:
            if len(ring) < 2:
                continue
            for i, a in enumerate(ring):
                b = ring[(i + 1) % len(ring)]
                if a == b:
                    continue
                edge = tuple(sorted((int(a), int(b))))
                counts[edge] += 1
    open_edges = sum(1 for c in counts.values() if c == 1)
    nonmanifold_edges = sum(1 for c in counts.values() if c > 2)
    return {
        "n_edges": len(counts),
        "open_edges": open_edges,
        "nonmanifold_edges": nonmanifold_edges,
        "edge_ok": open_edges == 0 and nonmanifold_edges == 0,
    }


def search_val3dity_binary() -> Dict:
    path_dirs = [Path(p) for p in os.environ.get("PATH", "").split(os.pathsep) if p]
    common_dirs = [
        ROOT / "bin",
        ROOT / "tools",
        ROOT / "external",
        Path.home() / ".local/bin",
        Path.home() / "miniconda3/bin",
        Path("/usr/local/bin"),
        Path("/usr/bin"),
        Path("/snap/bin"),
        Path("/opt/conda/bin"),
    ]
    checked: List[str] = []
    seen = set()
    for directory in path_dirs + common_dirs:
        candidate = directory / "val3dity"
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        checked.append(key)
        if candidate.exists() and os.access(candidate, os.X_OK):
            return {
                "found": True,
                "path": key,
                "checked_paths": checked,
            }
    which = shutil.which("val3dity")
    if which:
        return {
            "found": True,
            "path": which,
            "checked_paths": checked,
        }
    return {
        "found": False,
        "path": None,
        "checked_paths": checked,
        "install_instruction": (
            "Linux: install dependencies (libeigen3-dev, libgeos++-dev, "
            "libboost-filesystem-dev, libcgal-dev or CGAL >=5.4), then build "
            "from https://github.com/tudelft3d/val3dity with CMake and add the "
            "resulting val3dity binary to PATH."
        ),
        "docs": VAL3DITY_DOCS,
        "usage": VAL3DITY_USAGE,
    }


def collect_val3dity_errors(report: Dict) -> List[str]:
    errors = []
    for code in report.get("all_errors", []) or []:
        errors.append(str(code))
    for code in report.get("dataset_errors", []) or []:
        errors.append(str(code))
    for feature in report.get("features", []) or []:
        for err in feature.get("errors", []) or []:
            code = err.get("code") or err.get("error_code")
            if code is not None:
                errors.append(str(code))
        for prim in feature.get("primitives", []) or []:
            for err in prim.get("errors", []) or []:
                code = err.get("code") or err.get("error_code")
                if code is not None:
                    errors.append(str(code))
    return sorted(set(errors), key=lambda x: (len(x), x))


def summarize_val3dity_raw(raw: Dict) -> Dict:
    report = raw.get("report") or {}
    if "validity" in report:
        valid = bool(report.get("validity"))
    else:
        features = report.get("features", []) or []
        valid = bool(features) and all(bool(f.get("validity")) for f in features)
    errors = collect_val3dity_errors(report)
    return {
        "status": "PASS" if valid else "FAIL",
        "valid": valid,
        "errors": errors,
        "returncode": raw.get("returncode"),
        "version": report.get("val3dity_version"),
    }


def run_val3dity(cj_path: Path, report_path: Path, search: Dict) -> Dict:
    if not search.get("found"):
        out = {
            "status": "MISSING",
            "valid": None,
            "errors": ["val3dity_not_found"],
            "missing_path_reason": "No executable named val3dity was found on PATH or in common local install directories.",
            "binary_search": search,
        }
        report_path.write_text(json.dumps(out, indent=2, default=_jsonable) + "\n")
        return out
    cmd = [str(search["path"]), str(cj_path), "--report", str(report_path)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    except subprocess.TimeoutExpired:
        out = {
            "status": "ERROR",
            "valid": None,
            "errors": ["val3dity_timeout"],
            "command": cmd,
            "binary_search": search,
        }
        report_path.write_text(json.dumps(out, indent=2, default=_jsonable) + "\n")
        return out
    raw = {
        "returncode": proc.returncode,
        "stdout_tail": proc.stdout[-1000:],
        "stderr_tail": proc.stderr[-1000:],
        "command": cmd,
        "binary_search": search,
    }
    if report_path.exists():
        try:
            raw["report"] = json.loads(report_path.read_text())
        except Exception as exc:  # pragma: no cover - diagnostic path.
            raw["report_parse_error"] = str(exc)
    summary = summarize_val3dity_raw(raw)
    raw.update(summary)
    report_path.write_text(json.dumps(raw, indent=2, default=_jsonable) + "\n")
    return raw


def read_json(path: Path) -> Dict:
    return json.loads(path.read_text())


def stepwise_summary(bdir: Path, gt_footprint: Optional[Polygon]) -> Dict:
    evidence_graph = read_json(bdir / "evidence_graph.json")
    footprint_graph = read_json(bdir / "footprint_graph.json")
    selected_surfaces = read_json(bdir / "selected_surfaces.json")
    optional_arch = read_json(bdir / "optional_roof_archetype.json")
    nodes = evidence_graph.get("nodes", [])
    n_wall = sum(1 for n in nodes if n.get("semantic_class") == "wall")
    n_roof = sum(1 for n in nodes if n.get("semantic_class") == "roof")
    selected_poly = Polygon(footprint_graph.get("selected_polygon_xz", []))
    gt_area = gt_footprint.area if gt_footprint is not None else 0.0
    area_ratio = float(selected_poly.area / gt_area) if gt_area > 0 else float("nan")
    return {
        "n_wall_nodes": int(n_wall),
        "n_roof_nodes": int(n_roof),
        "n_footprint_candidates": int(len(footprint_graph.get("candidates", []))),
        "selected_footprint_area_ratio": area_ratio,
        "n_roof_surfaces": int(sum(1 for s in selected_surfaces.get("surfaces", [])
                                   if s.get("type") == "RoofSurface")),
        "optional_archetype": optional_arch.get("label", "NA"),
    }


def failure_hint(row: Dict) -> str:
    hints = []
    if row["val3dity_status"] == "MISSING":
        hints.append("val3dity_missing")
    elif row["val3dity_status"] == "FAIL":
        hints.append("val3dity_" + ",".join(row["val3dity_errors"] or ["fail"]))
    if not row["edge_ok"]:
        hints.append("edge_incidence")
    if row["face_planarity_max"] > 0.01:
        hints.append("face_planarity")
    if row["footprint_IoU"] < 0.70:
        hints.append("footprint_mismatch")
    if row["h_err"] > 1.0:
        hints.append("height_error")
    if row["F_score"] < 0.60:
        if row["recall_coverage"] < 0.60:
            hints.append("recall_low")
        if row["pred_precision"] < 0.60:
            hints.append("precision_low")
        if row["recall_coverage"] >= 0.60 and row["pred_precision"] >= 0.60:
            hints.append("F_below_target")
    if not hints:
        return "ok"
    return "+".join(hints)


def evaluate_one(building: Dict, search: Dict) -> Dict:
    bid = int(building["building_id"])
    bdir = OUT_ROOT / f"B{bid}"
    cj_path = bdir / "relation_readout.city.json"
    pred_vertices, faces = cityjson_faces(cj_path)
    pred_tris = cityjson_mesh_triangles(cj_path)
    gt_tris = gt_mesh_triangles(building)
    gt_vertices = np.concatenate([f["vertices"] for f in building["faces"]], axis=0)

    pred_pts = sample_triangles(pred_tris, N_SAMPLE, seed=10)
    gt_pts = sample_triangles(gt_tris, N_SAMPLE, seed=11)
    dist = distance_metrics(pred_pts, gt_pts)

    pred_h = float(pred_vertices[:, 1].max() - pred_vertices[:, 1].min()) if len(pred_vertices) else float("nan")
    gt_h = float(gt_vertices[:, 1].max() - gt_vertices[:, 1].min()) if len(gt_vertices) else float("nan")
    pred_area = triangle_area(pred_tris)
    gt_area = triangle_area(gt_tris)
    gt_vol = gt_volume_anchored(building)
    prior_metrics = read_json(bdir / "metrics.json")
    pred_vol = float(prior_metrics.get("output_vol", float("nan")))
    gt_fp = footprint_from_gt(building)
    pred_fp = footprint_from_cityjson_faces(faces)
    incidence = edge_incidence(faces)
    v3d = run_val3dity(cj_path, bdir / "val3dity_relation_preflight.json", search)
    step = stepwise_summary(bdir, gt_fp)

    row = {
        "bid": f"B{bid}",
        "bid_int": bid,
        "true_type_eval_only": building.get("type"),
        "cityjson_path": str(cj_path),
        "metric_sample_count": N_SAMPLE,
        "distance_threshold_m": SURFACE_THRESH_M,
        "val3dity_status": v3d["status"],
        "val3dity_valid": v3d.get("valid"),
        "val3dity_errors": v3d.get("errors", []),
        "val3dity_report": str(bdir / "val3dity_relation_preflight.json"),
        "h_err": abs(pred_h - gt_h),
        "output_h": pred_h,
        "GT_h": gt_h,
        "recall_coverage": dist["recall_coverage"],
        "pred_precision": dist["pred_precision"],
        "F_score": dist["F_score"],
        "output_vol": pred_vol,
        "GT_vol": gt_vol,
        "vol_ratio": pred_vol / max(gt_vol, 1e-9),
        "footprint_IoU": polygon_iou(pred_fp, gt_fp),
        "bbox_IoU": bbox_iou(pred_vertices, gt_vertices),
        "surface_area_ratio": pred_area / max(gt_area, 1e-9),
        "Hausdorff": dist["hausdorff"],
        "Chamfer": dist["chamfer"],
        "face_planarity_max": face_planarity_max_error(faces),
        **incidence,
        **step,
    }
    row["failure_hint"] = failure_hint(row)
    (bdir / "metrics_preflight_precision.json").write_text(
        json.dumps(row, indent=2, default=_jsonable) + "\n"
    )
    return row


def decision(rows: List[Dict], search: Dict) -> Dict:
    by_bid = {int(r["bid_int"]): r for r in rows}
    simple_hits = [
        b for b in SIMPLE_MEDIUM_BIDS
        if by_bid[b]["val3dity_status"] == "PASS" and by_bid[b]["F_score"] > 0.6
    ]
    b6_hit = by_bid[6]["val3dity_status"] == "PASS" and by_bid[6]["F_score"] > 0.5
    b3_complex_separate = (
        by_bid[3]["val3dity_status"] == "FAIL"
        or by_bid[3]["F_score"] <= 0.6
        or by_bid[3]["h_err"] > 1.0
    )
    if not search.get("found"):
        formal = "BLOCKED_VAL3DITY_MISSING"
    elif len(simple_hits) >= 3:
        formal = "GO_SIMPLE_MEDIUM"
    else:
        formal = "NG_SIMPLE_MEDIUM"
    return {
        "formal_decision": formal,
        "simple_medium_rule": "PASS" if len(simple_hits) >= 3 else "NOT_PASS",
        "simple_medium_hits": [f"B{b}" for b in simple_hits],
        "hip_rule": "PASS" if b6_hit else "NOT_PASS",
        "complex_rule": "SEPARATE_COMPLEX_BRANCH" if b3_complex_separate else "NOT_SEPARATED",
        "val3dity_binary_found": bool(search.get("found")),
        "val3dity_binary_path": search.get("path"),
    }


def md_table(headers: Iterable[str], rows: Iterable[Iterable[str]]) -> List[str]:
    headers = list(headers)
    out = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        out.append("| " + " | ".join(str(x) for x in row) + " |")
    return out


def write_report(rows: List[Dict], search: Dict, dec: Dict) -> None:
    lines = [
        "# P1-4a Preflight: val3dity + Precision Metrics",
        "",
        "## Scope",
        "",
        "Target artifacts: `relation_readout.city.json`, `metrics.json`, GT mesh from "
        f"`{SCENE.relative_to(ROOT)}`, and per-building stepwise JSON files under "
        f"`{OUT_ROOT.relative_to(ROOT)}`.",
        "",
        "Distance metrics use 6000 area-weighted predicted surface samples and 6000 "
        f"area-weighted GT mesh samples. Recall coverage and pred-to-GT precision use "
        f"a {SURFACE_THRESH_M:.1f}m threshold.",
        "",
        "Footprint IoU is predicted `GroundSurface` projected to x/z against the GT "
        "`Ground` footprint projected to x/z. `selected_footprint_area_ratio` is the "
        "selected wall-derived footprint area divided by GT footprint area.",
        "",
        "## val3dity Preflight",
        "",
    ]
    if search.get("found"):
        lines.append(f"- Binary: `{search['path']}`")
    else:
        lines.extend([
            "- Binary: `MISSING`",
            "- Missing-path reason: no executable named `val3dity` was found on `PATH` or common local install directories.",
            "- Search paths checked:",
        ])
        lines.extend([f"  - `{p}`" for p in search.get("checked_paths", [])])
        lines.extend([
            "- Installation note: on Linux, the official project currently expects a source build with CMake after installing CGAL/Eigen/GEOS/Boost dependencies.",
            f"- Official install docs: {VAL3DITY_DOCS}",
            f"- Official usage docs: {VAL3DITY_USAGE}",
            f"- Source: {VAL3DITY_GITHUB}",
        ])
    lines.extend([
        "",
        "## Table 1. Formal validity",
        "",
    ])
    lines.extend(md_table(
        ["bid", "val3dity", "errors", "edge_ok", "face_planarity_max", "open_edges", "nonmanifold_edges"],
        [
            [
                r["bid"],
                r["val3dity_status"],
                ",".join(r["val3dity_errors"]) if r["val3dity_errors"] else "-",
                str(bool(r["edge_ok"])),
                _fmt(r["face_planarity_max"], 6),
                _fmt(r["open_edges"], 0),
                _fmt(r["nonmanifold_edges"], 0),
            ]
            for r in rows
        ],
    ))
    lines.extend([
        "",
        "## Table 2. Final geometry",
        "",
    ])
    lines.extend(md_table(
        ["bid", "h_err", "recall_coverage", "pred_precision", "F_score", "vol_ratio", "footprint_IoU", "Hausdorff", "Chamfer"],
        [
            [
                r["bid"],
                _fmt(r["h_err"], 4),
                _fmt(r["recall_coverage"], 3),
                _fmt(r["pred_precision"], 3),
                _fmt(r["F_score"], 3),
                _fmt(r["vol_ratio"], 3),
                _fmt(r["footprint_IoU"], 3),
                _fmt(r["Hausdorff"], 4),
                _fmt(r["Chamfer"], 4),
            ]
            for r in rows
        ],
    ))
    lines.extend([
        "",
        "Additional geometry fields written to each `metrics_preflight_precision.json`: "
        "`bbox_IoU`, `surface_area_ratio`, `n_edges`, `output_h`, `GT_h`, `output_vol`, `GT_vol`.",
        "",
        "## Table 3. Stepwise summary",
        "",
    ])
    lines.extend(md_table(
        [
            "bid", "n_wall_nodes", "n_roof_nodes", "n_footprint_candidates",
            "selected_footprint_area_ratio", "n_roof_surfaces",
            "optional_archetype", "failure_hint",
        ],
        [
            [
                r["bid"],
                _fmt(r["n_wall_nodes"], 0),
                _fmt(r["n_roof_nodes"], 0),
                _fmt(r["n_footprint_candidates"], 0),
                _fmt(r["selected_footprint_area_ratio"], 3),
                _fmt(r["n_roof_surfaces"], 0),
                r["optional_archetype"],
                r["failure_hint"],
            ]
            for r in rows
        ],
    ))
    lines.extend([
        "",
        "## Formal GO/NG update",
        "",
        f"- Overall formal decision: `{dec['formal_decision']}`.",
        f"- Simple/medium rule (B1/B2/B8/B0, need >=3 val3dity PASS and F_score > 0.6): `{dec['simple_medium_rule']}`; hits: {', '.join(dec['simple_medium_hits']) or 'none'}.",
        f"- Hip branch rule (B6, need val3dity PASS and F_score > 0.5): `{dec['hip_rule']}`.",
        f"- Complex branch rule (B3 expected fail/separate): `{dec['complex_rule']}`.",
    ])
    if not search.get("found"):
        geom_hits = [r["bid"] for r in rows if r["bid_int"] in SIMPLE_MEDIUM_BIDS and r["F_score"] > 0.6]
        b6_geom = next(r for r in rows if r["bid_int"] == 6)
        lines.extend([
            "",
            "Because val3dity is missing, the formal GO/NG remains blocked even where geometry-side F-score clears the threshold.",
            f"- Geometry-side simple/medium F_score > 0.6: {len(geom_hits)}/4 ({', '.join(geom_hits) or 'none'}).",
            f"- Geometry-side B6 F_score > 0.5: {'yes' if b6_geom['F_score'] > 0.5 else 'no'} (F_score={_fmt(b6_geom['F_score'], 3)}).",
        ])
    lines.extend([
        "",
        "## Self-verification",
        "",
        "- PASS: every target bid has either a val3dity result or a missing-path reason in `val3dity_relation_preflight.json`.",
        "- PASS: pred-to-GT precision, F-score, and footprint IoU were computed for every target bid.",
        "- PASS: recall coverage and precision are both present in Table 2.",
        "- PASS: formal GO/NG was updated; current state is blocked by missing validator when no binary is found.",
        "",
    ])
    REPORT_PATH.write_text("\n".join(lines))


def main() -> None:
    gt = parse_scene_obj(SCENE)
    buildings = {int(b["building_id"]): b for b in gt["buildings"]}
    search = search_val3dity_binary()
    rows = [evaluate_one(buildings[bid], search) for bid in TARGET_BIDS]
    dec = decision(rows, search)
    payload = {
        "val3dity_search": search,
        "decision": dec,
        "rows": rows,
    }
    SUMMARY_JSON.write_text(json.dumps(payload, indent=2, default=_jsonable) + "\n")
    write_report(rows, search, dec)
    print(f"wrote {REPORT_PATH}")
    print(f"wrote {SUMMARY_JSON}")


if __name__ == "__main__":
    main()
