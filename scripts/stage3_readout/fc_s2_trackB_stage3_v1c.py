"""FC-S2 Track B: targeted Stage3-v1c diagnosis and patch ablation.

Track B keeps Stage2 evidence, footprint/domain assumptions, and Metric-v1
fixed. Patch branches are implemented as isolated read-out variants so the
Stage3-v1 baseline remains reproducible.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np
from scipy.spatial import cKDTree
from shapely.geometry import Polygon

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import scripts.stage3_readout.fc_s1_semantic_surface_readout as fc  # noqa: E402
import scripts.stage3_readout.p1_4a_relation_readout as rr  # noqa: E402
import scripts.stage3_readout.p1_4a_preflight_precision as pm  # noqa: E402
import scripts.stage3_readout.stage3_v1_auditable_readout_comparison as s3  # noqa: E402
from scripts.stage3_readout.obj_gt import parse_scene_obj  # noqa: E402


FC_S2_ROOT = (
    ROOT
    / "results/footprint_conditioned_readout"
    / "FC_S2_baseline_rendered_recovery_stage3_v1c"
)
PHASE_A_ROOT = FC_S2_ROOT / "phaseA_e1_recovery"
STAGE3_V1_ROOT = (
    ROOT
    / "results/footprint_conditioned_readout"
    / "Stage3_v1_auditable_readout_FC_S1_v0_v1_comparison"
)
FC_S1_ROOT = fc.OUT_ROOT

E0 = "E0_GT_clean_upper_bound"
E1 = "E1_Baseline_rendered"
E2 = "E2_Mutual_rendered"
E4 = "E4_Mutual_primitive"
RENDERED_TRIANGULATION = [E0, E1, E2]
TARGET_BIDS = fc.TARGET_BIDS
SIMPLE_BIDS = ["B0", "B1", "B2", "B8"]
FOCUS_BIDS = ["B104", "B6", "B3", "B123", "B126"]

BASE_ALGO = s3.STAGE3_ALGO_V1
METRIC_V1 = s3.METRIC_V1
BRANCH_GROUND = "Stage3Algo-v1c-ground"
BRANCH_HEIGHT = "Stage3Algo-v1c-height-definition"
BRANCH_ROOF_MERGE = "Stage3Algo-v1c-roof-merge-prune"
BRANCH_ROOF_EVAL = "Stage3Algo-v1c-roof-evaluator-matching"
BRANCH_SUPPORT = "Stage3Algo-v1c-support-attribution"
BRANCH_COMBINED = "Stage3Algo-v1c-combined-selected"

SUPPORT_FIELDS = ["roof_support_cov", "wall_support_cov", "ground_support_cov"]
MATRIX_FIELDS = []
for field in s3.MATRIX_FIELDS:
    MATRIX_FIELDS.append(field)
    if field == "support_coverage":
        MATRIX_FIELDS.extend(SUPPORT_FIELDS)
MATRIX_FIELDS.extend(["patch_branch", "patch_status", "patch_reason", "ground_y_strategy"])


def rel(path: Optional[Path]) -> str:
    if path is None:
        return ""
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def read_csv(path: Path) -> List[Dict]:
    if not path.exists():
        return []
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def safe_float(value: object) -> Optional[float]:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(x) or math.isinf(x) else x


def fmt(value: object, nd: int = 3) -> str:
    x = safe_float(value)
    if x is None:
        return "NA" if value in ("", None) else str(value)
    return f"{x:.{nd}f}"


def mean_value(rows: Iterable[Dict], key: str) -> object:
    vals = [safe_float(r.get(key)) for r in rows]
    vals = [x for x in vals if x is not None]
    return float(np.mean(vals)) if vals else ""


def support_by_surface(faces: List[Dict], evidence: Optional[Dict], seed: int) -> Dict:
    out = {field: "" for field in SUPPORT_FIELDS}
    if evidence is None or not faces:
        return out
    for surface_type, cls in fc.SURFACE_TO_CLASS.items():
        field = {
            "RoofSurface": "roof_support_cov",
            "WallSurface": "wall_support_cov",
            "GroundSurface": "ground_support_cov",
        }[surface_type]
        pred_tris = fc.faces_to_triangles([f for f in faces if f["type"] == surface_type])
        ev = evidence["points"][evidence["classes"] == cls]
        if len(pred_tris) == 0 or len(ev) == 0:
            out[field] = 0.0
            continue
        pts = pm.sample_triangles(pred_tris, min(fc.N_SURFACE_SAMPLE, 1000), seed + cls)
        d, _ = cKDTree(ev).query(pts)
        out[field] = float(np.mean(d <= fc.SUPPORT_DISTANCE_M))
    return out


def metric_row_from_faces(
    faces: List[Dict],
    status: Dict,
    building: Dict,
    evidence: Optional[Dict],
    source: str,
    bid: int,
    algo: str,
    readout_dir: Path,
    audit_dir: Path,
    branch: str,
    patch_status: str,
    patch_reason: str,
    ground_y_strategy: str = "",
) -> Dict:
    row = s3.metric_v1_evaluate(
        faces,
        building,
        evidence,
        source,
        bid,
        algo,
        status.get("status", ""),
        status.get("failure_reason", ""),
        audit_dir,
        readout_dir,
    )
    row.update(support_by_surface(faces, evidence, seed=9300 + bid))
    row.update({
        "patch_branch": branch,
        "patch_status": patch_status,
        "patch_reason": patch_reason,
        "ground_y_strategy": ground_y_strategy,
    })
    return row


def source_evidence_path(source: str, bid: int) -> Path:
    if source in {E1, E2}:
        return PHASE_A_ROOT / "phase1_evidence" / source / f"B{bid}" / "evidence.npz"
    return FC_S1_ROOT / "phase1_evidence" / source / f"B{bid}" / "evidence.npz"


def load_evidence(source: str, bid: int) -> Optional[Dict]:
    path = source_evidence_path(source, bid)
    if not path.exists():
        return None
    data = np.load(path, allow_pickle=False)
    evidence = {k: data[k] for k in data.files}
    evidence["source"] = source
    evidence["bid"] = f"B{bid}"
    return evidence


def readout_dir(source: str, bid_str: str) -> Path:
    if source in {E1, E2}:
        return PHASE_A_ROOT / "stage3_matrix_readout" / BASE_ALGO / source / bid_str
    return STAGE3_V1_ROOT / "phase2_stage3_v1_readout" / source / bid_str


def metric_dir(source: str, bid_str: str) -> Path:
    if source == E1:
        return PHASE_A_ROOT / "stage3_matrix_metric_v1" / BASE_ALGO / source / bid_str
    if source == E2 and (PHASE_A_ROOT / "stage3_matrix_metric_v1" / BASE_ALGO / source / bid_str).exists():
        return PHASE_A_ROOT / "stage3_matrix_metric_v1" / BASE_ALGO / source / bid_str
    return STAGE3_V1_ROOT / "phase2_stage3_v1_metric_v1_audit" / source / bid_str


def load_faces(source: str, bid: int) -> Tuple[List[Dict], Dict]:
    return s3.load_faces(readout_dir(source, f"B{bid}") / "semantic_faces.json")


def load_json(path: Path) -> Dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def base_metric_rows() -> List[Dict]:
    rows = []
    phase_a = read_csv(PHASE_A_ROOT / "e1_stage3_matrix_metrics_by_bid.csv")
    old = read_csv(STAGE3_V1_ROOT / "phase3_matrix/matrix_metrics_by_bid.csv")
    for row in phase_a:
        if row.get("source") == E1 and row.get("stage3_algo_version") == BASE_ALGO and row.get("metric_version") == METRIC_V1:
            row = dict(row)
            row.update({"patch_branch": "Stage3Algo-v1", "patch_status": "BASELINE", "patch_reason": "", "ground_y_strategy": "weighted_mean"})
            rows.append(row)
    for row in old:
        if row.get("source") in {E0, E2, E4} and row.get("stage3_algo_version") == BASE_ALGO and row.get("metric_version") == METRIC_V1:
            row = dict(row)
            source = row["source"]
            bid = int(row["bid"][1:])
            evidence = load_evidence(source, bid)
            faces, _payload = load_faces(source, bid)
            row.update(support_by_surface(faces, evidence, seed=9300 + bid))
            row.update({"patch_branch": "Stage3Algo-v1", "patch_status": "BASELINE", "patch_reason": "", "ground_y_strategy": "weighted_mean"})
            rows.append(row)
    return rows


def gt_stats(building: Dict) -> Dict:
    verts = np.concatenate([np.asarray(f["vertices"], dtype=np.float64) for f in building["faces"]], axis=0)
    out = {
        "gt_y_min": float(np.min(verts[:, 1])),
        "gt_y_max": float(np.max(verts[:, 1])),
        "gt_height": float(np.max(verts[:, 1]) - np.min(verts[:, 1])),
    }
    for surface_type, cls in fc.SURFACE_TO_CLASS.items():
        y = []
        n = 0
        for face in building["faces"]:
            if int(face.get("semantic_class", -1)) == cls:
                v = np.asarray(face["vertices"], dtype=np.float64)
                y.extend(v[:, 1].tolist())
                n += 1
        key = surface_type.replace("Surface", "").lower()
        out[f"gt_{key}_faces"] = n
        if y:
            out[f"gt_{key}_y_min"] = float(np.min(y))
            out[f"gt_{key}_y_max"] = float(np.max(y))
            out[f"gt_{key}_y_median"] = float(np.median(y))
    return out


def face_stats(faces: List[Dict]) -> Dict:
    out: Dict[str, object] = {}
    if faces:
        verts = np.concatenate([np.asarray(f["vertices"], dtype=np.float64) for f in faces], axis=0)
        out["pred_y_min"] = float(np.min(verts[:, 1]))
        out["pred_y_max"] = float(np.max(verts[:, 1]))
        out["pred_height"] = float(np.max(verts[:, 1]) - np.min(verts[:, 1]))
    for surface_type in ["RoofSurface", "WallSurface", "GroundSurface"]:
        y = []
        n = 0
        area = 0.0
        for face in faces:
            if face.get("type") == surface_type:
                v = np.asarray(face["vertices"], dtype=np.float64)
                y.extend(v[:, 1].tolist())
                area += fc.face_area(v)
                n += 1
        key = surface_type.replace("Surface", "").lower()
        out[f"pred_{key}_faces"] = n
        out[f"pred_{key}_area"] = area
        if y:
            out[f"pred_{key}_y_min"] = float(np.min(y))
            out[f"pred_{key}_y_max"] = float(np.max(y))
            out[f"pred_{key}_y_median"] = float(np.median(y))
    return out


def evidence_y_stats(evidence: Optional[Dict]) -> Dict:
    out: Dict[str, object] = {}
    if evidence is None:
        return out
    for cls, name in [(1, "roof"), (2, "wall"), (3, "ground")]:
        y = evidence["points"][evidence["classes"] == cls, 1]
        out[f"evidence_{name}_n"] = int(len(y))
        if len(y):
            out[f"evidence_{name}_y_mean"] = float(np.mean(y))
            out[f"evidence_{name}_y_median"] = float(np.median(y))
            out[f"evidence_{name}_y_p05"] = float(np.percentile(y, 5))
            out[f"evidence_{name}_y_p95"] = float(np.percentile(y, 95))
            out[f"evidence_{name}_y_min"] = float(np.min(y))
            out[f"evidence_{name}_y_max"] = float(np.max(y))
    return out


def write_diagnostics(buildings_by_bid: Dict[int, Dict], base_rows: List[Dict]) -> List[Dict]:
    idx = {(r["bid"], r["source"]): r for r in base_rows}
    diagnostics = []
    inspected = {
        "B104": [E0, E1, E2, E4],
        "B6": [E0, E1, E2],
        "B3": [E0, E1, E2],
        "B123": [E0, E1, E2],
        "B126": [E0, E1, E2],
    }
    for bid_str, sources in inspected.items():
        bid = int(bid_str[1:])
        building = buildings_by_bid[bid]
        gt = gt_stats(building)
        for source in sources:
            faces, _payload = load_faces(source, bid)
            evidence = load_evidence(source, bid)
            shell = load_json(readout_dir(source, bid_str) / "shell_diagnostics.json")
            metric = idx.get((bid_str, source), {})
            row = {
                "bid": bid_str,
                "source": source,
                "status": metric.get("status", shell.get("status", "")),
                "classification_hint": "",
                "readout_artifact_dir": rel(readout_dir(source, bid_str)),
                "metric_artifact_dir": rel(metric_dir(source, bid_str)),
                "ground_y": shell.get("assembly_diagnostics", {}).get("ground_y", ""),
                "edge_ok": metric.get("edge_ok", shell.get("edge_ok", "")),
                "open_edges": metric.get("open_edges", shell.get("open_edges", "")),
                "nonmanifold_edges": metric.get("nonmanifold_edges", shell.get("nonmanifold_edges", "")),
            }
            for key in [
                "roof_cov", "wall_cov", "ground_cov", "support_coverage",
                "roof_support_cov", "wall_support_cov", "ground_support_cov",
                "F", "h_err", "vol_ratio", "chamfer",
                "roof_wall_adjacency_count", "wall_ground_adjacency_count",
            ]:
                row[key] = metric.get(key, "")
            row.update(gt)
            row.update(face_stats(faces))
            row.update(evidence_y_stats(evidence))
            diagnostics.append(row)
    fc.write_csv(FC_S2_ROOT / "phaseB_diagnostics_by_case.csv", diagnostics)
    return diagnostics


def weighted_quantile(values: np.ndarray, weights: np.ndarray, q: float) -> float:
    values = np.asarray(values, dtype=np.float64)
    weights = np.asarray(weights, dtype=np.float64)
    order = np.argsort(values)
    values = values[order]
    weights = np.maximum(weights[order], 0.0)
    if np.sum(weights) <= 1e-12:
        return float(np.quantile(values, q))
    cdf = np.cumsum(weights) / np.sum(weights)
    return float(values[min(int(np.searchsorted(cdf, q, side="left")), len(values) - 1)])


def choose_ground_y(evidence: Dict, strategy: str) -> Tuple[float, str]:
    mask = evidence["classes"] == 3
    y = evidence["points"][mask, 1]
    w = evidence["weights"][mask]
    if len(y) == 0:
        raise RuntimeError("v1c-ground requires explicit ground evidence; refusing to synthesize hidden GroundSurface")
    if strategy == "weighted_median":
        return weighted_quantile(y, w, 0.5), "weighted_median_of_explicit_ground_evidence"
    if strategy == "upper_trimmed_median":
        p25 = np.percentile(y, 25)
        keep = y >= p25
        return weighted_quantile(y[keep], w[keep], 0.5), "weighted_median_after_lower_quartile_trim"
    return float(np.average(y, weights=w)), "weighted_mean_of_explicit_ground_evidence"


def assemble_closed_shell_ground_strategy(
    footprint: Polygon,
    evidence: Dict,
    roof_planes: List[rr.PlaneCandidate],
    ground_strategy: str,
) -> Tuple[List[Dict], Dict]:
    roof_faces, roof_faces_xz = rr.make_roof_mesh(footprint, evidence)
    if not roof_faces:
        raise RuntimeError("No roof faces generated from relation read-out")
    height = rr.fit_roof_interpolators(evidence)
    ground_y, reason = choose_ground_y(evidence, ground_strategy)
    ring_xz = rr._remove_near_collinear(np.asarray(list(footprint.exterior.coords)[:-1], dtype=np.float64))
    if rr._signed_area_2d(ring_xz) < 0:
        ring_xz = ring_xz[::-1].copy()
    top_ring = np.asarray([[x, height(x, z), z] for x, z in ring_xz], dtype=np.float64)
    bottom_ring = np.asarray([[x, ground_y, z] for x, z in ring_xz], dtype=np.float64)
    faces: List[Dict] = []
    for verts in roof_faces:
        faces.append({"vertices": verts, "type": "RoofSurface", "source": "roof_height_field"})
    for i in range(len(ring_xz)):
        j = (i + 1) % len(ring_xz)
        verts = np.asarray([top_ring[i], bottom_ring[i], bottom_ring[j], top_ring[j]], dtype=np.float64)
        if np.linalg.norm(verts[0] - verts[3]) < 1e-5:
            continue
        faces.append({"vertices": verts, "type": "WallSurface", "source": "wall_boundary_segment"})
    faces.append({"vertices": bottom_ring[::-1].copy(), "type": "GroundSurface", "source": "ground_boundary"})
    allv = np.concatenate([f["vertices"] for f in faces], axis=0)
    center = allv.mean(axis=0)
    for face in faces:
        face["vertices"] = rr._orient_face(face["vertices"], center)
    diag = rr.edge_incidence_diagnostics(faces)
    diag.update({
        "n_roof_faces": sum(1 for f in faces if f["type"] == "RoofSurface"),
        "n_wall_faces": sum(1 for f in faces if f["type"] == "WallSurface"),
        "n_ground_faces": sum(1 for f in faces if f["type"] == "GroundSurface"),
        "ground_y": ground_y,
        "ground_y_strategy": reason,
        "boundary_vertices": int(len(ring_xz)),
        "roof_plane_candidates_used_for_height_field": [p.node_id for p in roof_planes],
    })
    return faces, diag


def branch_ground_readout(
    evidence: Optional[Dict],
    building: Dict,
    footprint: Polygon,
    source: str,
    bid: int,
    out_dir: Path,
    strategy: str,
) -> Tuple[Dict, List[Dict], Optional[Dict], str]:
    fc.mkdir(out_dir)
    if evidence is None:
        status = {
            "bid": f"B{bid}",
            "bid_int": bid,
            "source": source,
            "stage3_algo_version": BRANCH_GROUND,
            "status": "SOURCE_MISSING",
            "n_faces": 0,
            "n_roof_faces": 0,
            "n_wall_faces": 0,
            "n_ground_faces": 0,
            "export_status": "NOT_WRITTEN",
            "failure_reason": "source artifact unavailable",
        }
        fc.write_json(out_dir / "shell_diagnostics.json", status)
        fc.write_json(out_dir / "semantic_faces.json", {"faces": [], "failure_reason": status["failure_reason"]})
        fc.write_json(out_dir / "face_graph.json", {"nodes": [], "edges": [], "failure_reason": status["failure_reason"]})
        return status, [], None, "SOURCE_MISSING"
    counts = fc.evidence_summary_row(evidence, bid, source)
    if counts["n_points"] == 0 or counts["n_roof"] < 3 or counts["n_ground"] < 1:
        reason = "EVIDENCE_OR_PLANE_INSUFFICIENT"
        status = {
            "bid": f"B{bid}",
            "bid_int": bid,
            "source": source,
            "stage3_algo_version": BRANCH_GROUND,
            "status": reason,
            "n_faces": 0,
            "n_roof_faces": 0,
            "n_wall_faces": 0,
            "n_ground_faces": 0,
            "export_status": "NOT_WRITTEN",
            "failure_reason": reason,
            **counts,
        }
        fc.write_json(out_dir / "shell_diagnostics.json", status)
        fc.write_json(out_dir / "semantic_faces.json", {"faces": [], "failure_reason": reason})
        fc.write_json(out_dir / "face_graph.json", {"nodes": [], "edges": [], "failure_reason": reason})
        return status, [], None, reason
    try:
        roof_planes, wall_planes, ground_planes, plane_info = fc.plane_candidates(evidence, source, bid)
        faces, assembly_diag = assemble_closed_shell_ground_strategy(footprint, evidence, roof_planes, strategy)
        city_dir = out_dir / "optional_cityjson"
        fc.mkdir(city_dir)
        city_diag = rr.faces_to_cityjson(faces, bid, city_dir / "relation_readout.city.json")
        sem = fc.faces_to_semantic_json(faces, out_dir / "semantic_faces.json")
        graph = fc.face_graph(faces)
        fc.write_json(out_dir / "face_graph.json", graph)
        shell = fc.shell_diagnostics_payload(faces, assembly_diag, city_diag, evidence, source, bid, "OK")
        shell.update({
            "stage3_algo_version": BRANCH_GROUND,
            "stage3_v1c_patch": {
                "patch_branch": "v1c-ground",
                "patch_applied": True,
                "ground_y_strategy": assembly_diag.get("ground_y_strategy"),
                "ground_y": assembly_diag.get("ground_y"),
                "uses_gt_height": False,
                "uses_gt_ground": False,
                "uses_stage2_evidence_change": False,
            },
            "plane_candidates": plane_info,
            "n_wall_plane_candidates_diagnostic": len(wall_planes),
            "n_ground_plane_candidates_diagnostic": len(ground_planes),
        })
        fc.write_json(out_dir / "shell_diagnostics.json", shell)
        fc.preview_plot(out_dir / "preview.png", evidence, footprint, faces, f"B{bid} {source} v1c-ground")
        status = {
            "bid": f"B{bid}",
            "bid_int": bid,
            "source": source,
            "stage3_algo_version": BRANCH_GROUND,
            "status": "OK",
            "n_faces": sem["summary"]["n_faces"],
            "n_roof_faces": sem["summary"]["n_roof_faces"],
            "n_wall_faces": sem["summary"]["n_wall_faces"],
            "n_ground_faces": sem["summary"]["n_ground_faces"],
            "export_status": "CITYJSON_WRITTEN",
            "failure_reason": "",
        }
        return status, faces, city_diag, assembly_diag.get("ground_y_strategy", strategy)
    except Exception as exc:  # noqa: BLE001
        reason = f"{type(exc).__name__}: {exc}"
        status = {
            "bid": f"B{bid}",
            "bid_int": bid,
            "source": source,
            "stage3_algo_version": BRANCH_GROUND,
            "status": "READOUT_EXCEPTION",
            "n_faces": 0,
            "n_roof_faces": 0,
            "n_wall_faces": 0,
            "n_ground_faces": 0,
            "export_status": "NOT_WRITTEN",
            "failure_reason": reason,
        }
        fc.write_json(out_dir / "shell_diagnostics.json", status)
        fc.write_json(out_dir / "semantic_faces.json", {"faces": [], "failure_reason": reason})
        fc.write_json(out_dir / "face_graph.json", {"nodes": [], "edges": [], "failure_reason": reason})
        return status, [], None, reason


def run_ground_branch(buildings_by_bid: Dict[int, Dict], branch_name: str, strategy: str) -> List[Dict]:
    rows: List[Dict] = []
    sources = [E0, E1, E2]
    for source in sources:
        for bid in TARGET_BIDS:
            bid_str = f"B{bid}"
            print(f"[FC-S2 Track B] {branch_name} {bid_str} {source}", flush=True)
            evidence = load_evidence(source, bid)
            building = buildings_by_bid[bid]
            footprint = fc.footprint_for_building(building)
            out_dir = FC_S2_ROOT / "phaseC_stage3_v1c_ablation" / "readout" / branch_name / source / bid_str
            status, faces, _city_diag, ground_reason = branch_ground_readout(
                evidence, building, footprint, source, bid, out_dir, strategy
            )
            row = metric_row_from_faces(
                faces,
                status,
                building,
                evidence,
                source,
                bid,
                branch_name,
                out_dir,
                FC_S2_ROOT / "phaseC_stage3_v1c_ablation" / "metric_v1" / branch_name / source / bid_str,
                branch_name,
                "APPLIED",
                "explicit ground y estimated by robust quantile; no Stage2 evidence mutation",
                ground_reason,
            )
            rows.append(row)
    return rows


def no_op_branch_rows(base_rows: List[Dict], branch: str, reason: str) -> List[Dict]:
    out = []
    for row in base_rows:
        if row.get("source") not in {E0, E1, E2}:
            continue
        r = dict(row)
        r["stage3_algo_version"] = branch
        r["patch_branch"] = branch
        r["patch_status"] = "REJECTED_NO_OP"
        r["patch_reason"] = reason
        out.append(r)
    return out


def row_key(row: Dict) -> Tuple[str, str]:
    return row.get("bid", ""), row.get("source", "")


def summarize_branch(base_rows: List[Dict], branch_rows: List[Dict], branch: str) -> Dict:
    base = {row_key(r): r for r in base_rows if r.get("source") in {E0, E1, E2}}
    rows = [r for r in branch_rows if r.get("patch_branch") == branch]
    deltas = []
    simple_regressions = 0
    edge_regressions = 0
    hidden_ground_failures = 0
    for row in rows:
        b = base.get(row_key(row), {})
        d = {
            "bid": row.get("bid"),
            "source": row.get("source"),
            "branch": branch,
            "base_status": b.get("status", ""),
            "branch_status": row.get("status", ""),
        }
        for metric in [
            "roof_cov", "wall_cov", "ground_cov", "support_coverage",
            "roof_support_cov", "wall_support_cov", "ground_support_cov",
            "F", "h_err", "vol_ratio", "chamfer", "open_edges", "nonmanifold_edges",
        ]:
            bx = safe_float(b.get(metric))
            rx = safe_float(row.get(metric))
            d[f"base_{metric}"] = bx if bx is not None else ""
            d[f"branch_{metric}"] = rx if rx is not None else ""
            d[f"delta_{metric}"] = (rx - bx) if bx is not None and rx is not None else ""
        deltas.append(d)
        if row.get("bid") in SIMPLE_BIDS:
            base_f = safe_float(b.get("F"))
            row_f = safe_float(row.get("F"))
            base_roof = safe_float(b.get("roof_cov"))
            row_roof = safe_float(row.get("roof_cov"))
            if (base_f is not None and row_f is not None and row_f < base_f - 0.01) or (
                base_roof is not None and row_roof is not None and row_roof < base_roof - 0.02
            ):
                simple_regressions += 1
        bo = safe_float(b.get("open_edges")) or 0.0
        ro = safe_float(row.get("open_edges")) or 0.0
        bn = safe_float(b.get("nonmanifold_edges")) or 0.0
        rn = safe_float(row.get("nonmanifold_edges")) or 0.0
        if ro > bo or rn > bn:
            edge_regressions += 1
        if row.get("status") == "OK" and safe_float(row.get("ground_cov")) == 0.0 and safe_float(row.get("ground_support_cov")) == 0.0:
            hidden_ground_failures += 1
    summary = {
        "patch_branch": branch,
        "n_rows": len(rows),
        "n_ok": sum(1 for r in rows if r.get("status") == "OK"),
        "mean_delta_F": mean_value(deltas, "delta_F"),
        "mean_delta_roof_cov": mean_value(deltas, "delta_roof_cov"),
        "mean_delta_ground_cov": mean_value(deltas, "delta_ground_cov"),
        "mean_delta_support_coverage": mean_value(deltas, "delta_support_coverage"),
        "simple_case_regressions": simple_regressions,
        "edge_regressions": edge_regressions,
        "hidden_ground_failures": hidden_ground_failures,
        "selected_for_combined": False,
        "decision": "REJECT",
        "decision_reason": "",
    }
    if branch == BRANCH_GROUND:
        b104 = [d for d in deltas if d["bid"] == "B104" and d["source"] == E2]
        b104_ground = safe_float(b104[0].get("delta_ground_cov")) if b104 else None
        if b104_ground is not None and b104_ground > 0.5 and simple_regressions == 0 and edge_regressions == 0:
            summary.update({
                "selected_for_combined": True,
                "decision": "ACCEPT",
                "decision_reason": "B104/E2 ground coverage recovered without simple-case or topology regressions.",
            })
        else:
            summary["decision_reason"] = "Robust ground branch did not satisfy recovery/no-regression gate."
    else:
        summary["decision_reason"] = "No confirmed safe Stage3 algorithm patch for this branch; kept as diagnostic no-op."
    return summary, deltas


def write_rows(path: Path, rows: List[Dict], fields: Optional[List[str]] = None) -> None:
    fc.write_csv(path, rows, fields)


def write_issue_reports(diagnostics: List[Dict], branch_summaries: List[Dict], ablation_deltas: List[Dict]) -> None:
    diag_by = defaultdict(list)
    for row in diagnostics:
        diag_by[row["bid"]].append(row)

    def mtable(rows: List[Dict], metrics: List[str]) -> List[List[object]]:
        out = []
        for r in rows:
            out.append([r["source"]] + [fmt(r.get(k)) for k in metrics])
        return out

    ground_dir = FC_S2_ROOT / "phaseB_ground_closure"
    fc.mkdir(ground_dir)
    b104 = diag_by["B104"]
    ground_summary = next((r for r in branch_summaries if r.get("patch_branch") == BRANCH_GROUND), {})
    lines = [
        "# B104 Ground Closure Report",
        "",
        "## Triangulation",
        "",
    ]
    lines.extend(fc.md_table(
        ["source", "ground_cov", "ground_y", "gt_ground_y", "evidence_ground_mean", "evidence_ground_median", "F", "h_err", "edge_ok", "open_edges"],
        [[
            r["source"], fmt(r.get("ground_cov")), fmt(r.get("ground_y")),
            fmt(r.get("gt_ground_y_median")), fmt(r.get("evidence_ground_y_mean")),
            fmt(r.get("evidence_ground_y_median")), fmt(r.get("F")), fmt(r.get("h_err")),
            r.get("edge_ok"), r.get("open_edges"),
        ] for r in b104],
    ))
    lines.extend([
        "",
        "## Classification",
        "",
        "B104 is classified as a `Stage3 algorithm issue` with a contributing rendered evidence/support issue. E0 is perfect and E1 is acceptable, while E2 and E4 produce closed shells with GroundSurface present but ground coverage at 0. The concrete Stage3 weakness is the weighted-mean ground height rule over noisy class-3 rendered points.",
        "",
        "## Intervention",
        "",
        "`v1c-ground` changes only the read-out ground height estimator to a robust weighted median of explicit class-3 evidence. It does not synthesize ground when class-3 evidence is absent and does not modify Stage2 evidence.",
        "",
        "## Ablation Outcome",
        "",
        f"`v1c-ground` decision: `{ground_summary.get('decision', 'NA')}`. Reason: {ground_summary.get('decision_reason', 'not evaluated')}",
    ])
    (ground_dir / "B104_GROUND_CLOSURE_REPORT.md").write_text("\n".join(lines) + "\n")

    height_dir = FC_S2_ROOT / "phaseB_height_definition"
    fc.mkdir(height_dir)
    b6 = diag_by["B6"]
    lines = [
        "# B6 Height Definition Report",
        "",
        "## Triangulation",
        "",
    ]
    lines.extend(fc.md_table(
        ["source", "F", "h_err", "gt_height", "pred_height", "roof_cov", "ground_cov", "edge_ok", "open_edges"],
        [[
            r["source"], fmt(r.get("F")), fmt(r.get("h_err")),
            fmt(r.get("gt_height")), fmt(r.get("pred_height")),
            fmt(r.get("roof_cov")), fmt(r.get("ground_cov")),
            r.get("edge_ok"), r.get("open_edges"),
        ] for r in b6],
    ))
    lines.extend([
        "",
        "## Classification",
        "",
        "B6 is classified as a `Stage3 algorithm issue`, but no safe minimal v1c patch is selected. E0, E1, and E2 all show the same height deficit pattern with closed topology, which rules out rendered-only evidence as the primary cause. The current height-field roof triangulation misses interior roof extrema; adding that safely would require a constrained roof-mesh change beyond the allowed minimal branch.",
        "",
        "## Branch Decision",
        "",
        "`v1c-height-definition` is rejected as a no-op in this run rather than changing Metric-v1 or adding a risky roof triangulation rewrite.",
    ])
    (height_dir / "B6_HEIGHT_DEFINITION_REPORT.md").write_text("\n".join(lines) + "\n")

    roof_dir = FC_S2_ROOT / "phaseB_roof_decomposition"
    fc.mkdir(roof_dir)
    roof_rows = diag_by["B3"] + diag_by["B123"] + diag_by["B126"]
    lines = [
        "# Roof Decomposition Report",
        "",
        "## E0/E1/E2 Triangulation",
        "",
    ]
    lines.extend(fc.md_table(
        ["bid", "source", "roof_cov", "n_roof_faces", "gt_roof_faces", "F", "chamfer", "edge_ok", "open_edges"],
        [[
            r["bid"], r["source"], fmt(r.get("roof_cov")),
            r.get("pred_roof_faces"), r.get("gt_roof_faces"),
            fmt(r.get("F")), fmt(r.get("chamfer")),
            r.get("edge_ok"), r.get("open_edges"),
        ] for r in roof_rows],
    ))
    lines.extend([
        "",
        "## Classification",
        "",
        "B3/B123/B126 are classified as `unresolved` between Stage3 roof decomposition and evaluator/reference matching. E0 clean upper-bound rows already have low roof coverage while topology remains closed, so the failure is not specific to rendered evidence or Mutual training. A roof merge/prune patch is not selected because it can improve a scalar roof metric by destroying meaningful roof topology.",
        "",
        "## Branch Decision",
        "",
        "`v1c-roof-merge-prune` and `v1c-roof-evaluator-matching` are diagnostic no-ops. Metric-v1 is kept unchanged.",
    ])
    (roof_dir / "ROOF_DECOMPOSITION_REPORT.md").write_text("\n".join(lines) + "\n")

    support_dir = FC_S2_ROOT / "phaseB_support_attribution"
    fc.mkdir(support_dir)
    support_rows = [r for r in diagnostics if r["source"] in {E1, E2}]
    lines = [
        "# Rendered Support Attribution Report",
        "",
        "## Classwise Support",
        "",
    ]
    lines.extend(fc.md_table(
        ["bid", "source", "support_cov", "roof_support_cov", "wall_support_cov", "ground_support_cov", "F"],
        [[
            r["bid"], r["source"], fmt(r.get("support_coverage")),
            fmt(r.get("roof_support_cov")), fmt(r.get("wall_support_cov")),
            fmt(r.get("ground_support_cov")), fmt(r.get("F")),
        ] for r in support_rows],
    ))
    lines.extend([
        "",
        "## Classification",
        "",
        "Rendered support attribution is classified as a `Stage2 rendered evidence/support issue`. E1 and E2 often have closed shells and reasonable GT metrics while classwise support, especially ground support, remains low because rendered class-3 evidence is sparse or vertically noisy. No Stage3 patch is selected for support attribution.",
    ])
    (support_dir / "RENDERED_SUPPORT_ATTRIBUTION_REPORT.md").write_text("\n".join(lines) + "\n")


def write_ablation_report(base_rows: List[Dict], all_branch_rows: List[Dict],
                          summaries: List[Dict], deltas: List[Dict]) -> None:
    out_dir = FC_S2_ROOT / "phaseC_stage3_v1c_ablation"
    fc.mkdir(out_dir)
    write_rows(out_dir / "patch_ablation_metrics_by_bid.csv", all_branch_rows, MATRIX_FIELDS)
    write_rows(out_dir / "patch_ablation_deltas_by_bid.csv", deltas)
    write_rows(out_dir / "patch_ablation_summary.csv", summaries)
    lines = [
        "# Patch Ablation Report",
        "",
        "## Branch Decisions",
        "",
    ]
    lines.extend(fc.md_table(
        ["branch", "rows", "OK", "mean_delta_F", "mean_delta_ground_cov", "simple_regressions", "edge_regressions", "decision", "reason"],
        [[
            r["patch_branch"], r["n_rows"], r["n_ok"],
            fmt(r.get("mean_delta_F")), fmt(r.get("mean_delta_ground_cov")),
            r["simple_case_regressions"], r["edge_regressions"],
            r["decision"], r["decision_reason"],
        ] for r in summaries],
    ))
    lines.extend([
        "",
        "## Rejection Gates",
        "",
        "- Regress good/simple cases: enforced by B0/B1/B2/B8 F and roof coverage deltas.",
        "- Increase open/non-manifold edges: enforced from Metric-v1 topology diagnostics.",
        "- Hide GroundSurface failure: v1c-ground refuses to synthesize ground when explicit class-3 evidence is absent.",
        "- Improve roof_cov by destroying topology: roof merge/prune branch is rejected as no-op.",
        "- Change Stage2 evidence or footprint/domain assumptions: not performed.",
        "",
        "## Selected Combination",
        "",
        "`v1c-combined-selected` includes only accepted branches. In this run that means `v1c-ground` if its summary decision is ACCEPT; otherwise combined remains identical to Stage3Algo-v1.",
    ])
    (out_dir / "PATCH_ABLATION_REPORT.md").write_text("\n".join(lines) + "\n")


def write_final_decision(summaries: List[Dict]) -> None:
    out_dir = FC_S2_ROOT / "phaseD_final_decision"
    fc.mkdir(out_dir)
    selected = [r for r in summaries if r.get("selected_for_combined") is True or str(r.get("selected_for_combined")) == "True"]
    selected_names = [r["patch_branch"] for r in selected]
    unresolved = [
        "B6 height-field interior extrema",
        "B3/B123/B126 roof decomposition versus reference matching",
        "rendered evidence support attribution",
    ]
    ready = len(selected_names) > 0
    lines = [
        "# G2 Readiness Decision",
        "",
        "## Decision",
        "",
        f"G2 readiness after Track B: `{'READY_WITH_SELECTED_V1C_GROUND_PATCH' if ready else 'NOT_READY_FOR_STAGE3_V1C_SELECTION'}`.",
        "",
        "## Selected Stage3-v1c Branches",
        "",
    ]
    if selected_names:
        lines.extend([f"- `{name}`" for name in selected_names])
    else:
        lines.append("- None")
    lines.extend([
        "",
        "## Conditions Preserved",
        "",
        "- Stage2 evidence was not modified.",
        "- Metric-v1 was not modified.",
        "- Footprint/domain assumptions and gravity were not changed.",
        "- Patches are branch-local and auditable.",
        "",
        "## Remaining Risks",
        "",
    ])
    lines.extend([f"- {item}" for item in unresolved])
    lines.extend([
        "",
        "## Practical Recommendation",
        "",
    ])
    if selected_names:
        lines.append("Use the selected combined branch for G2 only if the downstream experiment can tolerate the unresolved roof decomposition/reference-matching risks. Otherwise defer G2 until the roof evaluator and constrained roof-mesh questions are separated.")
    else:
        lines.append("Do not advance G2 on a Stage3-v1c-selected branch from this run. Keep the pre-v1c rendered comparison as diagnostic evidence and separate the roof evaluator, constrained roof-mesh, and rendered support-attribution questions before selecting a v1c branch.")
    (out_dir / "G2_READINESS_DECISION.md").write_text("\n".join(lines) + "\n")


def run(args: argparse.Namespace) -> None:
    fc.assert_gravity()
    if args.force:
        for subdir in [
            "phaseB_ground_closure",
            "phaseB_height_definition",
            "phaseB_roof_decomposition",
            "phaseB_support_attribution",
            "phaseC_stage3_v1c_ablation",
            "phaseD_final_decision",
        ]:
            path = FC_S2_ROOT / subdir
            if path.exists():
                shutil.rmtree(path)
    buildings = parse_scene_obj(fc.SCENE, frame="obj")["buildings"]
    buildings_by_bid = fc.target_buildings(buildings)
    base_rows = base_metric_rows()
    diagnostics = write_diagnostics(buildings_by_bid, base_rows)

    ground_rows = run_ground_branch(buildings_by_bid, BRANCH_GROUND, "weighted_median")
    branch_rows = list(ground_rows)
    branch_rows.extend(no_op_branch_rows(base_rows, BRANCH_HEIGHT, "height issue confirmed but no safe minimal Stage3 patch selected"))
    branch_rows.extend(no_op_branch_rows(base_rows, BRANCH_ROOF_MERGE, "roof merge/prune risks topology destruction; rejected"))
    branch_rows.extend(no_op_branch_rows(base_rows, BRANCH_ROOF_EVAL, "Metric-v1/reference matching held fixed; diagnostic no-op"))
    branch_rows.extend(no_op_branch_rows(base_rows, BRANCH_SUPPORT, "support attribution is rendered evidence/support issue; no Stage3 patch"))

    summaries = []
    all_deltas = []
    for branch in [BRANCH_GROUND, BRANCH_HEIGHT, BRANCH_ROOF_MERGE, BRANCH_ROOF_EVAL, BRANCH_SUPPORT]:
        summary, deltas = summarize_branch(base_rows, branch_rows, branch)
        summaries.append(summary)
        all_deltas.extend(deltas)

    selected = [s for s in summaries if s.get("selected_for_combined")]
    if selected:
        combined = []
        for row in ground_rows:
            r = dict(row)
            r["stage3_algo_version"] = BRANCH_COMBINED
            r["patch_branch"] = BRANCH_COMBINED
            r["patch_status"] = "APPLIED_SELECTED"
            r["patch_reason"] = "combined-selected currently equals accepted v1c-ground branch"
            combined.append(r)
    else:
        combined = no_op_branch_rows(base_rows, BRANCH_COMBINED, "no branch accepted")
    branch_rows.extend(combined)
    summary, deltas = summarize_branch(base_rows, branch_rows, BRANCH_COMBINED)
    if selected:
        summary["decision"] = "ACCEPT"
        summary["selected_for_combined"] = True
        summary["decision_reason"] = "Combined branch contains accepted v1c-ground patch only."
    summaries.append(summary)
    all_deltas.extend(deltas)

    write_issue_reports(diagnostics, summaries, all_deltas)
    write_ablation_report(base_rows, branch_rows, summaries, all_deltas)
    write_final_decision(summaries)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="regenerate Track B outputs")
    args = ap.parse_args()
    run(args)


if __name__ == "__main__":
    main()
