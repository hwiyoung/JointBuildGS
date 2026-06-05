"""FC-S2 Phase A+: insert regenerated E1 into the Stage3 matrix.

This script is intentionally orchestration-only. It reuses the existing
FC-S1 Stage3-v0 read-out, Stage3-v1 read-out, Metric-v0 helpers, and
Metric-v1 audit evaluator without changing any algorithm or metric code.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import scripts.phase2_synthesis.fc_s1_semantic_surface_readout as fc  # noqa: E402
import scripts.phase2_synthesis.stage3_v1_auditable_readout_comparison as s3  # noqa: E402
from scripts.phase2_synthesis.obj_gt import parse_scene_obj  # noqa: E402
import scripts.phase2_synthesis.p1_4a_preflight_precision as pm  # noqa: E402


PHASE_A_ROOT = (
    ROOT
    / "results/footprint_conditioned_readout"
    / "FC_S2_baseline_rendered_recovery_stage3_v1c"
    / "phaseA_e1_recovery"
)
E1_SOURCE = "E1_Baseline_rendered"
E2_SOURCE = "E2_Mutual_rendered"
E1_NPZ = PHASE_A_ROOT / "E1_Baseline_rendered.npz"
STAGE3_V0 = s3.STAGE3_ALGO_V0
STAGE3_V1 = s3.STAGE3_ALGO_V1
METRIC_V0 = s3.METRIC_V0
METRIC_V1 = s3.METRIC_V1

SUPPORT_FIELDS = ["roof_support_cov", "wall_support_cov", "ground_support_cov"]
MATRIX_FIELDS = []
for field in s3.MATRIX_FIELDS:
    MATRIX_FIELDS.append(field)
    if field == "support_coverage":
        MATRIX_FIELDS.extend(SUPPORT_FIELDS)

COMPARISON_METRICS = [
    "roof_cov",
    "wall_cov",
    "ground_cov",
    "support_cov",
    "roof_support_cov",
    "wall_support_cov",
    "ground_support_cov",
    "F",
    "h_err",
    "vol_ratio",
    "chamfer",
    "edge_ok",
    "open_edges",
    "nonmanifold_edges",
    "roof_wall_adjacency_count",
    "wall_ground_adjacency_count",
]
FOCUS_BIDS = ["B2", "B6", "B104", "B3", "B123", "B126"]


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


def load_phase_a_evidence(source: str, bid: int) -> Optional[Dict]:
    path = PHASE_A_ROOT / "phase1_evidence" / source / f"B{bid}" / "evidence.npz"
    if not path.exists():
        return None
    data = np.load(path, allow_pickle=False)
    evidence = {k: data[k] for k in data.files}
    evidence["source"] = source
    evidence["bid"] = f"B{bid}"
    return evidence


def load_evidence(source: str, bid: int, building: Dict) -> Optional[Dict]:
    evidence = load_phase_a_evidence(source, bid)
    if evidence is not None:
        return evidence
    if source == E2_SOURCE:
        return s3.load_evidence_from_fc_s1(source, bid)
    if source != E1_SOURCE or not E1_NPZ.exists():
        return None
    raw = fc.load_npz(E1_NPZ)
    normalized = fc.normalize_evidence(raw, E1_SOURCE, "rendered")
    footprint = fc.footprint_for_building(building)
    return fc.crop_evidence(normalized, footprint, E1_SOURCE, bid)


def metric0_row(
    faces: List[Dict],
    status: Dict,
    city_diag: Optional[Dict],
    building: Dict,
    evidence: Optional[Dict],
    source: str,
    bid: int,
    stage3_algo: str,
    readout_dir: Path,
    metric_dir: Path,
) -> Dict:
    row = {
        "bid": f"B{bid}",
        "source": source,
        "stage3_algo_version": stage3_algo,
        "metric_version": METRIC_V0,
        "status": status.get("status", ""),
        "n_faces": status.get("n_faces", ""),
        "n_roof_faces": status.get("n_roof_faces", ""),
        "n_wall_faces": status.get("n_wall_faces", ""),
        "n_ground_faces": status.get("n_ground_faces", ""),
        "readout_artifact_dir": rel(readout_dir),
        "metric_artifact_dir": rel(metric_dir),
        "failure_reason": status.get("failure_reason", ""),
    }
    if status.get("status") == "OK" and faces and evidence is not None and city_diag is not None:
        surf = fc.surface_metrics(faces, building, evidence, source, bid)
        geom = fc.geometry_metrics(faces, building, source, bid, city_diag)
        row.update({k: surf.get(k, "") for k in [
            "roof_cov",
            "wall_cov",
            "ground_cov",
            "semantic_face_acc",
            "face_planarity_mean",
            "face_planarity_max",
            "support_coverage",
        ]})
        row.update(support_by_surface(faces, evidence, seed=9100 + bid))
        row.update({k: geom.get(k, "") for k in [
            "F",
            "precision",
            "recall",
            "h_err",
            "vol_ratio",
            "hausdorff",
            "chamfer",
            "footprint_IoU",
            "edge_ok",
            "open_edges",
            "nonmanifold_edges",
            "roof_wall_adjacency_count",
            "wall_ground_adjacency_count",
            "shell_completeness",
        ]})
    fc.write_json(metric_dir / "metric_v0_summary.json", row)
    return row


def metric1_row(
    faces: List[Dict],
    status: Dict,
    building: Dict,
    evidence: Optional[Dict],
    source: str,
    bid: int,
    stage3_algo: str,
    readout_dir: Path,
    audit_dir: Path,
) -> Dict:
    row = s3.metric_v1_evaluate(
        faces,
        building,
        evidence,
        source,
        bid,
        stage3_algo,
        status.get("status", ""),
        status.get("failure_reason", ""),
        audit_dir,
        readout_dir,
    )
    row.update(support_by_surface(faces, evidence, seed=9200 + bid))
    return row


def run_v0_readout(evidence: Optional[Dict], building: Dict, bid: int, source: str,
                   out_dir: Path) -> Tuple[Dict, List[Dict], Optional[Dict]]:
    if evidence is None:
        fc.mkdir(out_dir)
        status = {
            "bid": f"B{bid}",
            "bid_int": bid,
            "source": source,
            "stage3_algo_version": STAGE3_V0,
            "status": "SOURCE_MISSING",
            "n_faces": 0,
            "n_roof_faces": 0,
            "n_wall_faces": 0,
            "n_ground_faces": 0,
            "export_status": "NOT_WRITTEN",
            "failure_reason": "source artifact unavailable",
        }
        fc.write_json(out_dir / "semantic_faces.json", {"faces": [], "failure_reason": "SOURCE_MISSING"})
        fc.write_json(out_dir / "face_graph.json", {"nodes": [], "edges": [], "failure_reason": "SOURCE_MISSING"})
        fc.write_json(out_dir / "shell_diagnostics.json", status)
        return status, [], None
    footprint = fc.footprint_for_building(building)
    status, faces, city_diag = fc.readout_one(evidence, building, footprint, source, bid, out_dir)
    status["stage3_algo_version"] = STAGE3_V0
    shell_path = out_dir / "shell_diagnostics.json"
    if shell_path.exists():
        payload = json.loads(shell_path.read_text())
        payload["stage3_algo_version"] = STAGE3_V0
        fc.write_json(shell_path, payload)
    return status, faces or [], city_diag


def run_v1_readout(evidence: Optional[Dict], building: Dict, bid: int, source: str,
                   out_dir: Path) -> Tuple[Dict, List[Dict], Optional[Dict]]:
    footprint = fc.footprint_for_building(building)
    status, faces, city_diag, _patch_log = s3.stage3_v1_readout(
        evidence,
        building,
        footprint,
        source,
        bid,
        out_dir,
    )
    return status, faces or [], city_diag


def run_source_matrix(source: str, run_v0: bool, run_v1_metric0: bool) -> Tuple[List[Dict], List[Dict]]:
    buildings = parse_scene_obj(fc.SCENE, frame="obj")["buildings"]
    buildings_by_bid = fc.target_buildings(buildings)
    rows: List[Dict] = []
    status_rows: List[Dict] = []

    for bid in fc.TARGET_BIDS:
        bid_str = f"B{bid}"
        building = buildings_by_bid[bid]
        evidence = load_evidence(source, bid, building)

        if run_v0:
            print(f"[FC-S2 Phase A+] {bid_str} {source} {STAGE3_V0}", flush=True)
            v0_dir = PHASE_A_ROOT / "stage3_matrix_readout" / STAGE3_V0 / source / bid_str
            v0_status, v0_faces, v0_city = run_v0_readout(evidence, building, bid, source, v0_dir)
            status_rows.append({**v0_status, "readout_artifact_dir": rel(v0_dir)})
            rows.append(metric0_row(
                v0_faces,
                v0_status,
                v0_city,
                building,
                evidence,
                source,
                bid,
                STAGE3_V0,
                v0_dir,
                PHASE_A_ROOT / "stage3_matrix_metric_v0" / STAGE3_V0 / source / bid_str,
            ))
            rows.append(metric1_row(
                v0_faces,
                v0_status,
                building,
                evidence,
                source,
                bid,
                STAGE3_V0,
                v0_dir,
                PHASE_A_ROOT / "stage3_matrix_metric_v1" / STAGE3_V0 / source / bid_str,
            ))

        print(f"[FC-S2 Phase A+] {bid_str} {source} {STAGE3_V1}", flush=True)
        v1_dir = PHASE_A_ROOT / "stage3_matrix_readout" / STAGE3_V1 / source / bid_str
        v1_status, v1_faces, v1_city = run_v1_readout(evidence, building, bid, source, v1_dir)
        status_rows.append({**v1_status, "readout_artifact_dir": rel(v1_dir)})
        rows.append(metric1_row(
            v1_faces,
            v1_status,
            building,
            evidence,
            source,
            bid,
            STAGE3_V1,
            v1_dir,
            PHASE_A_ROOT / "stage3_matrix_metric_v1" / STAGE3_V1 / source / bid_str,
        ))
        if run_v1_metric0:
            rows.append(metric0_row(
                v1_faces,
                v1_status,
                v1_city,
                building,
                evidence,
                source,
                bid,
                STAGE3_V1,
                v1_dir,
                PHASE_A_ROOT / "stage3_matrix_metric_v0" / STAGE3_V1 / source / bid_str,
            ))
    return rows, status_rows


def indexed(rows: List[Dict]) -> Dict[Tuple[str, str, str, str], Dict]:
    return {
        (r.get("bid", ""), r.get("source", ""), r.get("stage3_algo_version", ""), r.get("metric_version", "")): r
        for r in rows
    }


def delta(a: object, b: object) -> object:
    ax = safe_float(a)
    bx = safe_float(b)
    if ax is None or bx is None:
        return ""
    return bx - ax


def comparison_rows(e1_rows: List[Dict], e2_rows: List[Dict]) -> List[Dict]:
    idx = indexed(e1_rows + e2_rows)
    bid_rows = []
    for bid in [f"B{x}" for x in fc.TARGET_BIDS]:
        b = idx.get((bid, E1_SOURCE, STAGE3_V1, METRIC_V1), {})
        m = idx.get((bid, E2_SOURCE, STAGE3_V1, METRIC_V1), {})
        row = {
            "row_type": "bid",
            "bid": bid,
            "baseline_status": b.get("status", ""),
            "mutual_status": m.get("status", ""),
            "both_ok": bool(b.get("status") == "OK" and m.get("status") == "OK"),
        }
        for metric in COMPARISON_METRICS:
            b_key = "support_coverage" if metric == "support_cov" else metric
            m_key = b_key
            row[f"baseline_{metric}"] = b.get(b_key, "")
            row[f"mutual_{metric}"] = m.get(m_key, "")
            row[f"delta_mutual_minus_baseline_{metric}"] = delta(b.get(b_key, ""), m.get(m_key, ""))
        bid_rows.append(row)

    e1_ok = sum(1 for r in bid_rows if r["baseline_status"] == "OK")
    e2_ok = sum(1 for r in bid_rows if r["mutual_status"] == "OK")
    both_ok = sum(1 for r in bid_rows if r["both_ok"])
    summary = {
        "row_type": "summary",
        "bid": "ALL",
        "baseline_status": f"OK {e1_ok}/{len(bid_rows)}",
        "mutual_status": f"OK {e2_ok}/{len(bid_rows)}",
        "both_ok": both_ok,
    }
    for metric in COMPARISON_METRICS:
        vals_b = [safe_float(r.get(f"baseline_{metric}")) for r in bid_rows]
        vals_m = [safe_float(r.get(f"mutual_{metric}")) for r in bid_rows]
        vals_d = [safe_float(r.get(f"delta_mutual_minus_baseline_{metric}")) for r in bid_rows]
        vals_b = [x for x in vals_b if x is not None]
        vals_m = [x for x in vals_m if x is not None]
        vals_d = [x for x in vals_d if x is not None]
        summary[f"baseline_{metric}"] = float(np.mean(vals_b)) if vals_b else ""
        summary[f"mutual_{metric}"] = float(np.mean(vals_m)) if vals_m else ""
        summary[f"delta_mutual_minus_baseline_{metric}"] = float(np.mean(vals_d)) if vals_d else ""
    return [summary] + bid_rows


def aggregate_matrix(rows: List[Dict]) -> List[Dict]:
    return s3.aggregate(rows, ["stage3_algo_version", "metric_version", "source"], [
        "roof_cov",
        "wall_cov",
        "ground_cov",
        "support_coverage",
        "F",
        "h_err",
        "vol_ratio",
        "chamfer",
        "open_edges",
        "nonmanifold_edges",
    ])


def write_report(e1_rows: List[Dict], comparison: List[Dict]) -> None:
    matrix_summary = aggregate_matrix(e1_rows)
    summary = comparison[0]
    focus = [r for r in comparison[1:] if r["bid"] in FOCUS_BIDS]
    lines = [
        "# Rendered Baseline vs Mutual Pre-v1c",
        "",
        "## Scope",
        "",
        f"- E1 artifact: `{rel(E1_NPZ)}`",
        f"- Output root: `{rel(PHASE_A_ROOT)}`",
        "- Stage3 algorithms were not modified.",
        "- Metric-v1 was not modified.",
        "- Track B patches were not started.",
        "- Footprint/domain, source definitions, gravity, and Stage2 evidence generation are unchanged.",
        "",
        "## E1 Stage3 matrix",
        "",
    ]
    lines.extend(fc.md_table(
        ["algo", "metric", "source", "rows", "OK", "mean_F", "mean_roof_cov", "mean_wall_cov", "mean_ground_cov", "mean_support_cov"],
        [[
            r["stage3_algo_version"],
            r["metric_version"],
            r["source"],
            r["n_rows"],
            r["n_ok"],
            fc.fmt(r.get("mean_F")),
            fc.fmt(r.get("mean_roof_cov")),
            fc.fmt(r.get("mean_wall_cov")),
            fc.fmt(r.get("mean_ground_cov")),
            fc.fmt(r.get("mean_support_coverage")),
        ] for r in matrix_summary],
    ))
    lines.extend([
        "",
        "## Rendered comparison",
        "",
        f"- E1 Baseline rendered OK count: `{summary['baseline_status']}`",
        f"- E2 Mutual rendered OK count: `{summary['mutual_status']}`",
        f"- Both OK count: `{summary['both_ok']}/10`",
        "",
    ])
    lines.extend(fc.md_table(
        ["metric", "baseline_mean", "mutual_mean", "delta_mutual_minus_baseline"],
        [[
            metric,
            fc.fmt(summary.get(f"baseline_{metric}")),
            fc.fmt(summary.get(f"mutual_{metric}")),
            fc.fmt(summary.get(f"delta_mutual_minus_baseline_{metric}")),
        ] for metric in COMPARISON_METRICS],
    ))
    lines.extend([
        "",
        "## Focus bid deltas",
        "",
        "Deltas are raw `mutual - baseline` values under `Stage3Algo-v1 + Metric-v1`.",
        "",
    ])
    lines.extend(fc.md_table(
        ["bid", "roof_cov", "wall_cov", "ground_cov", "support_cov", "F", "h_err", "vol_ratio", "chamfer", "open_edges"],
        [[
            r["bid"],
            fc.fmt(r.get("delta_mutual_minus_baseline_roof_cov")),
            fc.fmt(r.get("delta_mutual_minus_baseline_wall_cov")),
            fc.fmt(r.get("delta_mutual_minus_baseline_ground_cov")),
            fc.fmt(r.get("delta_mutual_minus_baseline_support_cov")),
            fc.fmt(r.get("delta_mutual_minus_baseline_F")),
            fc.fmt(r.get("delta_mutual_minus_baseline_h_err")),
            fc.fmt(r.get("delta_mutual_minus_baseline_vol_ratio")),
            fc.fmt(r.get("delta_mutual_minus_baseline_chamfer")),
            fc.fmt(r.get("delta_mutual_minus_baseline_open_edges")),
        ] for r in focus],
    ))
    lines.extend([
        "",
        "## Artifacts",
        "",
        "- `e1_stage3_matrix_metrics_by_bid.csv`",
        "- `e1_readout_status.csv`",
        "- `rendered_baseline_vs_mutual_pre_v1c.csv`",
        "",
        "## Conclusion",
        "",
        "E1_Baseline_rendered is integrated into the Stage3 matrix for the requested combinations. A rendered Baseline-vs-Mutual comparison is possible before Stage3-v1c patches because both rendered sources have Stage3Algo-v1 + Metric-v1 rows over the full FC-S1 target set.",
    ])
    (PHASE_A_ROOT / "RENDERED_COMPARISON_PRE_V1C.md").write_text("\n".join(lines) + "\n")


def write_outputs(e1_rows: List[Dict], status_rows: List[Dict], comparison: List[Dict]) -> None:
    fc.write_csv(PHASE_A_ROOT / "e1_stage3_matrix_metrics_by_bid.csv", e1_rows, MATRIX_FIELDS)
    fc.write_csv(PHASE_A_ROOT / "e1_readout_status.csv", status_rows, [
        "bid",
        "source",
        "stage3_algo_version",
        "status",
        "n_faces",
        "n_roof_faces",
        "n_wall_faces",
        "n_ground_faces",
        "export_status",
        "failure_reason",
        "patch_applied",
        "patch_reason",
        "readout_artifact_dir",
    ])
    fc.write_csv(PHASE_A_ROOT / "rendered_baseline_vs_mutual_pre_v1c.csv", comparison)
    write_report(e1_rows, comparison)
    fc.write_json(PHASE_A_ROOT / "phaseA_plus_stage3_matrix_manifest.json", {
        "experiment": "FC-S2 Phase A+ Stage3 matrix insertion",
        "e1_source_npz": rel(E1_NPZ),
        "phase_a_root": rel(PHASE_A_ROOT),
        "stage3_algorithms_modified": False,
        "metric_v1_modified": False,
        "track_b_started": False,
        "stage2_evidence_generation_modified": False,
        "footprint_buffer_m": fc.FOOTPRINT_BUFFER_M,
        "gravity": [0, 1, 0],
        "target_bids": [f"B{x}" for x in fc.TARGET_BIDS],
        "comparison": "E1_Baseline_rendered vs E2_Mutual_rendered under Stage3Algo-v1 + Metric-v1",
    })


def run(args: argparse.Namespace) -> None:
    fc.assert_gravity()
    if not E1_NPZ.exists():
        raise FileNotFoundError(f"Accepted E1 artifact is missing: {E1_NPZ}")
    for relative in [
        "stage3_matrix_readout",
        "stage3_matrix_metric_v0",
        "stage3_matrix_metric_v1",
    ]:
        path = PHASE_A_ROOT / relative
        if args.force and path.exists():
            shutil.rmtree(path)

    e1_rows, e1_status = run_source_matrix(E1_SOURCE, run_v0=True, run_v1_metric0=True)
    e2_rows, _e2_status = run_source_matrix(E2_SOURCE, run_v0=False, run_v1_metric0=False)
    comparison = comparison_rows(e1_rows, e2_rows)
    write_outputs(e1_rows, e1_status, comparison)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="regenerate Phase A+ intermediate readout/audit artifacts")
    args = ap.parse_args()
    run(args)


if __name__ == "__main__":
    main()
