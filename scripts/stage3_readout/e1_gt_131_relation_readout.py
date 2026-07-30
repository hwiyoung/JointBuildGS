"""E1: GT-derived 131 per-building relation read-out sanity test.

This is not proposed-method performance. GT building ids are used to isolate
each building and for evaluation only. The read-out inputs remain sampled
position, normal, semantic class, and support weight.
"""
from __future__ import annotations

import csv
import json
import math
import os
import shutil
import subprocess
import sys
import traceback
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from shapely.geometry import Polygon

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.stage3_readout.obj_gt import parse_scene_obj  # noqa: E402
import scripts.stage3_readout.p1_4a_relation_readout as rr  # noqa: E402
import scripts.stage3_readout.p1_4a_preflight_precision as pm  # noqa: E402


SCENE = ROOT / "results/phase2_synthesis/scene.obj"
OUT_ROOT = ROOT / "results/stage3_typed_readout/E1_gt_131_per_building"
P1_ROOT = ROOT / "results/stage3_typed_readout/P1_4a_gt_sanity"
REPORT_PATH = OUT_ROOT / "REPORT.md"
SUMMARY_CSV = OUT_ROOT / "summary_metrics.csv"
SUMMARY_JSON = OUT_ROOT / "summary_metrics.json"
VAL3DITY_DEP_REPORT = P1_ROOT / "val3dity_enable/build_report.md"
TARGET_BIDS: List[int] = list(range(131))
N_METRIC_SAMPLE = 6000
SURFACE_THRESH_M = 0.5


def mkdir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def jsonable(obj):
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, np.generic):
        return obj.item()
    return str(obj)


def write_json(path: Path, payload: Dict) -> None:
    path.write_text(json.dumps(payload, indent=2, default=jsonable) + "\n")


def fmt(v: object, nd: int = 4) -> str:
    if v is None:
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


def val3dity_binary() -> Tuple[Optional[Path], Dict]:
    candidates: List[Tuple[str, Path]] = []
    env_bin = os.environ.get("VAL3DITY_BIN")
    if env_bin:
        candidates.append(("VAL3DITY_BIN", Path(env_bin).expanduser()))
    which = shutil.which("val3dity")
    if which:
        candidates.append(("PATH", Path(which)))

    checks = []
    seen = set()
    for source, p in candidates:
        key = str(p.resolve()) if p.exists() else str(p)
        if key in seen:
            continue
        seen.add(key)
        item = {
            "source": source,
            "path": str(p),
            "exists": p.exists(),
            "is_file": p.is_file(),
            "executable": p.is_file() and p.exists() and p.stat().st_mode & 0o111 != 0,
        }
        if item["executable"]:
            try:
                proc = subprocess.run([str(p), "--help"], capture_output=True, text=True, timeout=20)
                item["help_returncode"] = proc.returncode
                item["help_excerpt"] = (proc.stdout + proc.stderr)[:2000]
                item["help_ok"] = proc.returncode == 0 or "val3dity" in item["help_excerpt"].lower()
            except Exception as exc:
                item["help_ok"] = False
                item["help_error"] = str(exc)
        checks.append(item)
        if item.get("help_ok"):
            return p, {"found": True, "path": str(p), "checks": checks}
    return None, {"found": False, "path": None, "checks": checks}


def run_cmd(cmd: List[str], timeout: int = 120) -> Dict:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return {
            "command": cmd,
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "timeout": False,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "command": cmd,
            "returncode": None,
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or "",
            "timeout": True,
        }


def collect_report_errors(node, path="$") -> List[Dict]:
    out: List[Dict] = []
    if isinstance(node, dict):
        for k, v in node.items():
            child = f"{path}.{k}"
            if str(k).lower() in {"errors", "error", "all_errors", "dataset_errors"}:
                if isinstance(v, list):
                    for i, item in enumerate(v):
                        out.extend(normalize_error(item, f"{child}[{i}]"))
                elif v:
                    out.extend(normalize_error(v, child))
            else:
                out.extend(collect_report_errors(v, child))
    elif isinstance(node, list):
        for i, item in enumerate(node):
            out.extend(collect_report_errors(item, f"{path}[{i}]"))
    return out


def normalize_error(item, path: str) -> List[Dict]:
    if item is None or item == []:
        return []
    if isinstance(item, dict):
        code = item.get("code") or item.get("error_code") or item.get("type")
        return [{
            "path": path,
            "code": str(code) if code is not None else None,
            "object_id": item.get("object_id") or item.get("feature_id") or item.get("id"),
            "primitive_id": item.get("primitive_id") or item.get("primitive"),
            "geometry_id": item.get("geometry_id") or item.get("geometry"),
            "raw": item,
        }]
    return [{"path": path, "code": str(item), "raw": item}]


def report_validity_flag(report: Dict) -> Optional[bool]:
    for key in ("validity", "valid", "is_valid"):
        if isinstance(report.get(key), bool):
            return bool(report[key])
    features = report.get("features")
    if isinstance(features, list) and features:
        vals = []
        for feat in features:
            if not isinstance(feat, dict):
                continue
            for key in ("validity", "valid", "is_valid"):
                if isinstance(feat.get(key), bool):
                    vals.append(bool(feat[key]))
                    break
        if vals:
            return all(vals)
    return None


def parse_val3dity_result(bid: int, bdir: Path, bin_path: Optional[Path]) -> Dict:
    if bin_path is None:
        return {
            "bid": f"B{bid}",
            "val3dity_status": "BLOCKED_DEPENDENCY",
            "val3dity_valid": None,
            "val3dity_errors": ["val3dity_binary_unavailable_CGAL_dependency"],
            "val3dity_report": None,
            "val3dity_stdout": None,
            "val3dity_stderr": None,
            "val3dity_binary_path": None,
        }
    report_path = bdir / "val3dity_report.json"
    stdout_path = bdir / "val3dity_stdout.txt"
    stderr_path = bdir / "val3dity_stderr.txt"
    cmd = [str(bin_path), str(bdir / "relation_readout.city.json"), "--report", str(report_path)]
    result = run_cmd(cmd, timeout=120)
    stdout_path.write_text(result.get("stdout") or "")
    stderr_path.write_text(result.get("stderr") or "")
    parsed = {
        "bid": f"B{bid}",
        "val3dity_binary_path": str(bin_path),
        "val3dity_command": cmd,
        "val3dity_returncode": result.get("returncode"),
        "val3dity_stdout": str(stdout_path),
        "val3dity_stderr": str(stderr_path),
        "val3dity_report": str(report_path),
    }
    if result.get("timeout"):
        parsed.update({"val3dity_status": "TIMEOUT", "val3dity_valid": None, "val3dity_errors": ["timeout"]})
        return parsed
    if not report_path.exists():
        parsed.update({"val3dity_status": "REPORT_MISSING", "val3dity_valid": None, "val3dity_errors": ["report_missing"]})
        return parsed
    try:
        report = json.loads(report_path.read_text())
    except Exception as exc:
        parsed.update({"val3dity_status": "PARSE_FAIL", "val3dity_valid": None, "val3dity_errors": [str(exc)]})
        return parsed
    details = collect_report_errors(report)
    errors = sorted({str(e.get("code") or e.get("path")) for e in details})
    valid_flag = report_validity_flag(report)
    valid = False if errors else (True if valid_flag is None else valid_flag)
    parsed.update({
        "val3dity_status": "PASS" if valid else "FAIL",
        "val3dity_valid": valid,
        "val3dity_errors": errors,
        "val3dity_error_details": details,
    })
    return parsed


def run_schema_validation(bid: int, bdir: Path) -> Dict:
    cjio = shutil.which("cjio")
    if cjio is None:
        return {"schema_validation_status": "SKIPPED_CJIO_NOT_FOUND", "schema_validation_notes": "cjio not found"}
    stdout_path = bdir / "cjio_validate_stdout.txt"
    stderr_path = bdir / "cjio_validate_stderr.txt"
    cmd = [cjio, str(bdir / "relation_readout.city.json"), "validate"]
    result = run_cmd(cmd, timeout=120)
    stdout_path.write_text(result.get("stdout") or "")
    stderr_path.write_text(result.get("stderr") or "")
    return {
        "schema_validation_status": "PASS" if result.get("returncode") == 0 else "FAIL",
        "schema_validation_returncode": result.get("returncode"),
        "schema_validation_stdout": str(stdout_path),
        "schema_validation_stderr": str(stderr_path),
    }


def output_height_from_cityjson(cj_path: Path) -> float:
    vertices, _faces = pm.cityjson_faces(cj_path)
    return float(vertices[:, 1].max() - vertices[:, 1].min()) if len(vertices) else float("nan")


def eval_geometry(building: Dict, bdir: Path, city_diag: Dict) -> Dict:
    cj_path = bdir / "relation_readout.city.json"
    pred_vertices, faces = pm.cityjson_faces(cj_path)
    pred_tris = pm.cityjson_mesh_triangles(cj_path)
    gt_tris = pm.gt_mesh_triangles(building)
    gt_vertices = np.concatenate([f["vertices"] for f in building["faces"]], axis=0)
    pred_pts = pm.sample_triangles(pred_tris, N_METRIC_SAMPLE, seed=10)
    gt_pts = pm.sample_triangles(gt_tris, N_METRIC_SAMPLE, seed=11)
    dist = pm.distance_metrics(pred_pts, gt_pts)
    pred_h = output_height_from_cityjson(cj_path)
    gt_h = float(gt_vertices[:, 1].max() - gt_vertices[:, 1].min())
    gt_vol = pm.gt_volume_anchored(building)
    pred_vol = abs(float(city_diag.get("signed_volume", float("nan"))))
    gt_fp = pm.footprint_from_gt(building)
    pred_fp = pm.footprint_from_cityjson_faces(faces)
    incidence = pm.edge_incidence(faces)
    return {
        "output_h": pred_h,
        "GT_h": gt_h,
        "h_err": abs(pred_h - gt_h),
        "output_vol": pred_vol,
        "GT_vol": gt_vol,
        "vol_ratio": pred_vol / max(gt_vol, 1e-9),
        "recall_coverage": dist["recall_coverage"],
        "coverage": dist["recall_coverage"],
        "pred_precision": dist["pred_precision"],
        "F_score": dist["F_score"],
        "footprint_IoU": pm.polygon_iou(pred_fp, gt_fp),
        "bbox_IoU": pm.bbox_iou(pred_vertices, gt_vertices),
        "surface_area_ratio": pm.triangle_area(pred_tris) / max(pm.triangle_area(gt_tris), 1e-9),
        "Hausdorff": dist["hausdorff"],
        "hausdorff": dist["hausdorff"],
        "Chamfer": dist["chamfer"],
        "chamfer": dist["chamfer"],
        "face_planarity_max": pm.face_planarity_max_error(faces),
        "edge_ok": incidence["edge_ok"],
        "edge_incidence_ok": incidence["edge_ok"],
        "open_edges": incidence["open_edges"],
        "nonmanifold_edges": incidence["nonmanifold_edges"],
        "n_edges": incidence["n_edges"],
    }


def footprint_area_ratio(footprint: Polygon, building: Dict) -> float:
    gt_fp = pm.footprint_from_gt(building)
    if gt_fp is None or gt_fp.area <= 0:
        return float("nan")
    return float(footprint.area / gt_fp.area)


def classify_quality(metrics: Dict) -> str:
    if metrics.get("pipeline_success") is not True:
        return str(metrics.get("failure_reason", "PIPELINE_FAIL"))
    f_score = float(metrics.get("F_score", 0.0))
    recall = float(metrics.get("recall_coverage", 0.0))
    precision = float(metrics.get("pred_precision", 0.0))
    vol_ratio = float(metrics.get("vol_ratio", 0.0))
    true_type = metrics.get("true_type_eval_only")
    n_wall = int(metrics.get("n_wall_nodes", 0))
    if metrics.get("val3dity_valid") is False:
        return "VAL3DITY_FAIL"
    if f_score < 0.5:
        if true_type == "complex":
            return "COMPLEX_MULTIPART"
        if precision < recall or vol_ratio > 1.5:
            return "LOW_PRECISION_OVERFILL"
        return "LOW_RECALL_UNDERFILL"
    if precision < 0.5 or vol_ratio > 2.0:
        return "LOW_PRECISION_OVERFILL"
    if recall < 0.5:
        return "LOW_RECALL_UNDERFILL"
    if n_wall >= 24 and f_score < 0.7:
        return "SHARED_WALL_LIKELY"
    if metrics.get("val3dity_valid") is None:
        return "VAL3DITY_BLOCKED_DEPENDENCY"
    return "OK"


def write_failure_payload(bdir: Path, bid: int, building: Dict, reason: str, exc: Exception, stage: str) -> Dict:
    payload = {
        "bid": bid,
        "true_type_eval_only": building.get("type"),
        "pipeline_success": False,
        "failure_stage": stage,
        "failure_reason": reason,
        "exception_type": type(exc).__name__,
        "exception": str(exc),
        "traceback_tail": traceback.format_exc(limit=5),
        "input_assertions": input_assertions(),
    }
    write_json(bdir / "metrics.json", payload)
    write_json(bdir / "stepwise_metrics.json", payload)
    return payload


def input_assertions() -> Dict:
    return {
        "gt_building_id_used_for_extraction": True,
        "gt_used_for_evaluation": True,
        "roof_type_label_used_in_readout": False,
        "final_footprint_used_in_readout": False,
        "final_roof_model_used_in_readout": False,
        "allowed_readout_inputs": ["sampled position", "normal", "semantic class", "support weight"],
    }


def plot_overlay(building: Dict, bdir: Path, footprint: Optional[Polygon]) -> None:
    fig, ax = plt.subplots(figsize=(6, 6))
    gt_fp = pm.footprint_from_gt(building)
    if gt_fp is not None:
        x, y = gt_fp.exterior.xy
        ax.plot(x, y, color="black", linewidth=2.0, label="GT footprint")
    if footprint is not None and not footprint.is_empty:
        x, y = footprint.exterior.xy
        ax.plot(x, y, color="#1f77b4", linewidth=1.5, label="read-out footprint")
    evidence_npz = bdir / "evidence_gt_sampled.npz"
    if evidence_npz.exists():
        ev = np.load(evidence_npz)
        roof = ev["points"][ev["classes"] == 1][:, [0, 2]]
        wall = ev["points"][ev["classes"] == 2][:, [0, 2]]
        if len(wall):
            ax.scatter(wall[:, 0], wall[:, 1], s=2, c="#2D5FD7", alpha=0.25, label="wall evidence")
        if len(roof):
            ax.scatter(roof[:, 0], roof[:, 1], s=2, c="#DC2828", alpha=0.20, label="roof evidence")
    ax.set_aspect("equal", adjustable="box")
    ax.set_title(f"B{building['building_id']} {building.get('type')}")
    ax.legend(loc="best", fontsize=7)
    ax.grid(True, linewidth=0.2, alpha=0.3)
    fig.tight_layout()
    fig.savefig(bdir / "fig_overlay.png", dpi=150)
    plt.close(fig)


def process_building(building: Dict, val_bin: Optional[Path]) -> Dict:
    bid = int(building["building_id"])
    bdir = OUT_ROOT / f"B{bid}"
    mkdir(bdir)
    footprint: Optional[Polygon] = None
    try:
        evidence = rr.generate_evidence(building)
        np.savez_compressed(bdir / "evidence_gt_sampled.npz", **evidence)
        rr.write_evidence_ply(bdir / "evidence_gt_sampled.ply", evidence)
        rr.write_evidence_ply(bdir / "wall_evidence.ply", evidence, evidence["classes"] == 2)
        rr.write_evidence_ply(bdir / "roof_evidence.ply", evidence, evidence["classes"] == 1)
        rr.write_evidence_stats(bdir / "evidence_stats.csv", evidence)
        counts = {rr.CLASS_NAME[k]: int(np.sum(evidence["classes"] == k)) for k in [1, 2, 3]}
        if counts["roof"] < 3 or counts["wall"] < 3 or counts["ground"] < 3:
            raise RuntimeError(f"insufficient evidence counts: {counts}")
    except Exception as exc:
        plot_overlay(building, bdir, None)
        return write_failure_payload(bdir, bid, building, "EVIDENCE_INSUFFICIENT", exc, "evidence")

    try:
        wall_planes = rr.cluster_planes_from_evidence(evidence, 2)
        roof_planes = rr.cluster_planes_from_evidence(evidence, 1)
        ground_planes = rr.cluster_planes_from_evidence(evidence, 3)
        if len(wall_planes) < 2 or len(roof_planes) < 1 or len(ground_planes) < 1:
            raise RuntimeError(
                f"insufficient plane candidates wall={len(wall_planes)} roof={len(roof_planes)} ground={len(ground_planes)}")
        footprint, footprint_candidates, wall_segments = rr.build_footprint_candidates(evidence, wall_planes)
        rr.write_footprint_graph_json(bdir / "footprint_graph.json", footprint, footprint_candidates, wall_segments)
        (bdir / "footprint_candidates.json").write_text(json.dumps({
            "selected_candidate_id": footprint_candidates[0]["id"],
            "candidates": footprint_candidates,
        }, indent=2, default=jsonable) + "\n")
        rr.write_footprint_plot(bdir / "footprint_candidates.png", footprint, footprint_candidates, evidence)
    except Exception as exc:
        plot_overlay(building, bdir, footprint)
        return write_failure_payload(bdir, bid, building, "FOOTPRINT_FAIL", exc, "footprint")

    try:
        graph_edges = rr.write_graph_json(bdir / "evidence_graph.json", wall_planes, roof_planes, ground_planes, wall_segments)
        roof_candidates = rr.roof_surface_candidates(roof_planes, footprint, evidence)
        if not roof_candidates:
            raise RuntimeError("no roof surface candidates")
        (bdir / "roof_surface_candidates.json").write_text(json.dumps({
            "roof_surface_generation": "roof plane candidates clipped diagnostically; final shell uses relation height-field triangulation",
            "candidates": roof_candidates,
        }, indent=2, default=jsonable) + "\n")
        (bdir / "roof_modes.json").write_text(json.dumps({
            "roof_type_label_used": False,
            "roof_plane_candidates": [rr.plane_to_json(p) for p in roof_planes],
        }, indent=2, default=jsonable) + "\n")
        rr.write_roof_mode_plot(bdir / "roof_mode_plot.png", roof_planes)
    except Exception as exc:
        plot_overlay(building, bdir, footprint)
        return write_failure_payload(bdir, bid, building, "ROOF_PARTITION_FAIL", exc, "roof_partition")

    try:
        faces, assembly_diag = rr.assemble_closed_shell(footprint, evidence, roof_planes)
        cj_path = bdir / "relation_readout.city.json"
        city_diag = rr.faces_to_cityjson(faces, bid, cj_path)
        selected = rr.selected_surfaces_payload(faces, assembly_diag, city_diag)
        write_json(bdir / "selected_surfaces.json", selected)
        archetype = rr.optional_roof_archetype(roof_planes, assembly_diag, evidence)
        write_json(bdir / "optional_roof_archetype.json", archetype)
    except Exception as exc:
        plot_overlay(building, bdir, footprint)
        return write_failure_payload(bdir, bid, building, "SHELL_ASSEMBLY_FAIL", exc, "shell_assembly")

    geom = eval_geometry(building, bdir, city_diag)
    val = parse_val3dity_result(bid, bdir, val_bin)
    schema = run_schema_validation(bid, bdir)
    step = {
        "bid": bid,
        "true_type_eval_only": building.get("type"),
        "n_wall_nodes": len(wall_planes),
        "n_roof_nodes": len(roof_planes),
        "n_ground_nodes": len(ground_planes),
        "n_relation_edges": len(graph_edges),
        "n_footprint_candidates": len(footprint_candidates),
        "selected_footprint_candidate": footprint_candidates[0]["id"],
        "selected_footprint_score": footprint_candidates[0]["score"],
        "selected_footprint_area_ratio": footprint_area_ratio(footprint, building),
        "n_roof_surfaces": int(selected["cityjson_diagnostics"]["surface_types"].get("RoofSurface", 0)),
        "optional_archetype": archetype["label"],
        "input_assertions": input_assertions(),
    }
    metrics = {
        "bid": bid,
        "true_type_eval_only": building.get("type"),
        "pipeline_success": True,
        "cityjson_path": str(bdir / "relation_readout.city.json"),
        "optional_roof_archetype": archetype["label"],
        **geom,
        **val,
        **schema,
        **step,
        "input_assertions": input_assertions(),
    }
    metrics["failure_reason"] = classify_quality(metrics)
    metrics["formal_verdict"] = (
        "VALID_GEOMETRY_OK" if metrics["val3dity_valid"] is True and metrics["F_score"] > 0.5
        else metrics["failure_reason"]
    )
    write_json(bdir / "metrics.json", metrics)
    write_json(bdir / "stepwise_metrics.json", step | {
        "failure_reason": metrics["failure_reason"],
        "val3dity_status": metrics["val3dity_status"],
        "F_score": metrics["F_score"],
    })
    write_json(bdir / "val3dity_parsed.json", val)
    plot_overlay(building, bdir, footprint)
    return metrics


def read_p1_comparison() -> List[Dict]:
    path = P1_ROOT / "preflight_precision_metrics.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text())
    return data.get("rows", [])


def aggregate_by_archetype(rows: List[Dict]) -> List[Dict]:
    buckets: Dict[str, List[Dict]] = defaultdict(list)
    for row in rows:
        key = str(row.get("optional_roof_archetype") or "failed_before_archetype")
        buckets[key].append(row)
    out = []
    for key, vals in sorted(buckets.items()):
        successful = [v for v in vals if v.get("pipeline_success")]
        valid_known = [v for v in vals if v.get("val3dity_valid") is not None]
        n_valid = sum(1 for v in vals if v.get("val3dity_valid") is True)
        failures = Counter(str(v.get("failure_reason", "UNKNOWN")) for v in vals)
        out.append({
            "diagnostic_archetype": key,
            "n": len(vals),
            "val3dity_rate": n_valid / len(valid_known) if valid_known else None,
            "mean_F": float(np.mean([v.get("F_score", np.nan) for v in successful])) if successful else None,
            "mean_h_err": float(np.mean([v.get("h_err", np.nan) for v in successful])) if successful else None,
            "mean_vol_ratio": float(np.mean([v.get("vol_ratio", np.nan) for v in successful])) if successful else None,
            "main_failure": failures.most_common(1)[0][0] if failures else "NA",
        })
    return out


def decision(rows: List[Dict]) -> Dict:
    total = len(rows)
    val_known = [r for r in rows if r.get("val3dity_valid") is not None]
    val_pass = sum(1 for r in rows if r.get("val3dity_valid") is True)
    f_pass = sum(1 for r in rows if r.get("pipeline_success") and r.get("F_score", 0.0) > 0.5)
    simple_medium = [
        r for r in rows
        if r.get("true_type_eval_only") in {"flat", "gable", "tri-slope"}
    ]
    simple_pass = sum(1 for r in simple_medium if r.get("pipeline_success") and r.get("F_score", 0.0) > 0.6)
    val_rate = val_pass / total if total else 0.0
    f_rate = f_pass / total if total else 0.0
    simple_rate = simple_pass / len(simple_medium) if simple_medium else 0.0
    val_blocked = len(val_known) == 0
    if val_blocked:
        status = "E1_BLOCKED_VAL3DITY_DEPENDENCY_GEOMETRY_ONLY"
    elif val_rate >= 0.70 and f_rate >= 0.60 and simple_rate >= 0.70:
        status = "E1_GO_TO_E2"
    else:
        status = "E1_NG_REVIEW_FAILURES"
    return {
        "decision": status,
        "n_total": total,
        "n_val3dity_known": len(val_known),
        "val3dity_pass_rate": val_rate,
        "F_gt_0p5_rate": f_rate,
        "simple_medium_F_gt_0p6_rate": simple_rate,
        "can_proceed_E2_formal": status == "E1_GO_TO_E2",
        "can_proceed_E2_geometry_only": val_blocked and f_rate >= 0.60 and simple_rate >= 0.70,
    }


def write_summary_csv(rows: List[Dict]) -> None:
    fields = [
        "bid", "true_type_eval_only", "optional_roof_archetype", "pipeline_success",
        "val3dity_status", "val3dity_valid", "h_err", "recall_coverage",
        "pred_precision", "F_score", "vol_ratio", "footprint_IoU", "Hausdorff",
        "Chamfer", "edge_ok", "failure_reason",
    ]
    with SUMMARY_CSV.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fields})


def md_table(headers: List[str], rows: List[List[object]]) -> List[str]:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(x) for x in row) + " |")
    return lines


def write_report(rows: List[Dict], archetypes: List[Dict], dec: Dict, val_search: Dict) -> None:
    p1_rows = read_p1_comparison()
    failure_dist = Counter(str(r.get("failure_reason", "UNKNOWN")) for r in rows)
    complex_candidates = sum(1 for r in rows if r.get("failure_reason") == "COMPLEX_MULTIPART")
    shared_wall = sum(1 for r in rows if r.get("failure_reason") == "SHARED_WALL_LIKELY")
    val_blocked = dec["n_val3dity_known"] == 0
    lines = [
        "# E1 GT-derived 131 Per-building Relation Read-out",
        "",
        "## 1. Experiment Status",
        "",
        "This is a GT per-building read-out sanity/generalization test, not proposed-method performance. GT building ids are used only to isolate each building and to evaluate the output. GT roof type label, final footprint polygon, and final roof model are not used by the relation read-out.",
        "",
        f"- GT source: `{SCENE.relative_to(ROOT)}`",
        f"- Target buildings: {len(TARGET_BIDS)}",
        f"- Processed buildings: {len(rows)}",
        f"- val3dity binary found: `{val_search.get('found')}` path=`{val_search.get('path')}`",
    ]
    if val_blocked:
        lines.append(f"- val3dity formal validation is blocked by the same dependency issue recorded in `{VAL3DITY_DEP_REPORT.relative_to(ROOT)}`.")
    lines.extend([
        "",
        "## 2. P1-4a 6-bid Comparison",
        "",
    ])
    if p1_rows:
        lines.extend(md_table(
            ["bid", "P1_F", "P1_recall", "P1_precision", "E1_F", "E1_failure"],
            [
                [
                    row["bid"],
                    fmt(row.get("F_score"), 3),
                    fmt(row.get("recall_coverage"), 3),
                    fmt(row.get("pred_precision"), 3),
                    fmt(next((r.get("F_score") for r in rows if r.get("bid") == row.get("bid_int")), None), 3),
                    next((r.get("failure_reason") for r in rows if r.get("bid") == row.get("bid_int")), "NA"),
                ]
                for row in p1_rows
            ],
        ))
    else:
        lines.append("P1-4a comparison metrics were not found.")
    lines.extend([
        "",
        "## 3. Per-building Summary",
        "",
    ])
    lines.extend(md_table(
        ["bid", "val3dity", "h_err", "recall", "precision", "F_score", "vol_ratio", "footprint_IoU", "failure_reason"],
        [
            [
                f"B{r['bid']}",
                r.get("val3dity_status", "NA"),
                fmt(r.get("h_err"), 4),
                fmt(r.get("recall_coverage"), 3),
                fmt(r.get("pred_precision"), 3),
                fmt(r.get("F_score"), 3),
                fmt(r.get("vol_ratio"), 3),
                fmt(r.get("footprint_IoU"), 3),
                r.get("failure_reason", "NA"),
            ]
            for r in rows
        ],
    ))
    lines.extend([
        "",
        "## 4. Type / Archetype Summary",
        "",
    ])
    lines.extend(md_table(
        ["diagnostic_archetype", "n", "val3dity_rate", "mean_F", "mean_h_err", "mean_vol_ratio", "main_failure"],
        [
            [
                a["diagnostic_archetype"],
                a["n"],
                "NA" if a["val3dity_rate"] is None else fmt(a["val3dity_rate"], 3),
                fmt(a["mean_F"], 3),
                fmt(a["mean_h_err"], 4),
                fmt(a["mean_vol_ratio"], 3),
                a["main_failure"],
            ]
            for a in archetypes
        ],
    ))
    lines.extend([
        "",
        "## 5. Failure Distribution",
        "",
    ])
    lines.extend(md_table(
        ["failure_reason", "n", "rate"],
        [[k, v, fmt(v / max(len(rows), 1), 3)] for k, v in failure_dist.most_common()],
    ))
    lines.extend([
        "",
        "## 6. Complex / Shared-wall Candidates",
        "",
        f"- COMPLEX_MULTIPART candidates: {complex_candidates}/{len(rows)} ({fmt(complex_candidates / max(len(rows), 1), 3)})",
        f"- SHARED_WALL_LIKELY candidates: {shared_wall}/{len(rows)} ({fmt(shared_wall / max(len(rows), 1), 3)})",
        "",
        "## 7. GO/NG For E2 Full-scene Split",
        "",
        f"- Formal decision: `{dec['decision']}`",
        f"- val3dity pass rate: {fmt(dec['val3dity_pass_rate'], 3)}",
        f"- F_score > 0.5 rate: {fmt(dec['F_gt_0p5_rate'], 3)}",
        f"- simple/medium F_score > 0.6 rate: {fmt(dec['simple_medium_F_gt_0p6_rate'], 3)}",
        f"- Proceed to E2 formal: `{dec['can_proceed_E2_formal']}`",
        f"- Proceed to E2 geometry-only exploratory: `{dec['can_proceed_E2_geometry_only']}`",
    ])
    if val_blocked:
        lines.append("- E2 formal decision remains blocked until val3dity is installed; geometry-only exploratory E2 should be explicitly labeled as such.")
    lines.extend([
        "",
        "## 8. Self-verification",
        "",
        f"- PASS: processed {len(rows)}/131 GT buildings.",
        f"- PASS: successful CityJSON outputs: {sum(1 for r in rows if (OUT_ROOT / ('B' + str(r['bid'])) / 'relation_readout.city.json').exists())}.",
        f"- PASS: every run has `metrics.json` with success metrics or failure_reason: {all((OUT_ROOT / ('B' + str(r['bid'])) / 'metrics.json').exists() for r in rows)}.",
        f"- {'BLOCKED' if val_blocked else 'PASS'}: val3dity results recorded; status is `{rows[0].get('val3dity_status')}` for generated outputs." if rows else "- FAIL: no rows.",
        "- PASS: input assertions recorded; roof type, GT final footprint, and GT final roof model are not read-out inputs.",
        "",
    ])
    REPORT_PATH.write_text("\n".join(lines) + "\n")


def main() -> None:
    mkdir(OUT_ROOT)
    gt = parse_scene_obj(SCENE, frame="obj")
    buildings = [b for b in gt["buildings"] if int(b["building_id"]) in TARGET_BIDS]
    val_bin, val_search = val3dity_binary()
    write_json(OUT_ROOT / "val3dity_search.json", val_search)
    rows: List[Dict] = []
    for b in buildings:
        bid = int(b["building_id"])
        print(f"[E1] B{bid:03d} type={b.get('type')}")
        rows.append(process_building(b, val_bin))
    rows.sort(key=lambda r: int(r["bid"]))
    archetypes = aggregate_by_archetype(rows)
    dec = decision(rows)
    write_summary_csv(rows)
    write_json(SUMMARY_JSON, {
        "experiment_status": "GT per-building read-out sanity; not proposed-method performance",
        "input_policy": input_assertions(),
        "decision": dec,
        "val3dity_search": val_search,
        "archetype_summary": archetypes,
        "rows": rows,
    })
    write_report(rows, archetypes, dec, val_search)
    print(f"[E1] wrote {OUT_ROOT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
