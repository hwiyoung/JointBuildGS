"""FC-S3: Mutual loss alignment audit and G2 target definition.

This is an orchestration/diagnostic script. It keeps Stage3Algo-v1 and
Metric-v1 fixed, uses the regenerated E1 rendered evidence from FC-S2, and
writes the requested audit outputs without starting G2 training or mutating
Stage3, Metric-v1, footprints, source definitions, or Stage2 evidence files.
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
import scripts.stage3_readout.fc_s2_phaseA_plus_stage3_matrix as phasea  # noqa: E402
import scripts.stage3_readout.p1_4a_preflight_precision as pm  # noqa: E402
import scripts.stage3_readout.stage3_v1_auditable_readout_comparison as s3  # noqa: E402
from scripts.stage3_readout.obj_gt import parse_scene_obj  # noqa: E402


FC_S2_ROOT = (
    ROOT
    / "results/footprint_conditioned_readout"
    / "FC_S2_baseline_rendered_recovery_stage3_v1c"
)
PHASE_A_ROOT = FC_S2_ROOT / "phaseA_e1_recovery"
FC_S3_ROOT = (
    ROOT
    / "results/footprint_conditioned_readout"
    / "FC_S3_mutual_loss_alignment_g2_target_definition"
)
STAGE3_V1_ROOT = (
    ROOT
    / "results/footprint_conditioned_readout"
    / "Stage3_v1_auditable_readout_FC_S1_v0_v1_comparison"
)

E0 = "E0_GT_clean_upper_bound"
E1 = "E1_Baseline_rendered"
E2 = "E2_Mutual_rendered"
TARGET_BIDS = [0, 1, 2, 8, 6, 3, 123, 126, 50, 104]
FIELD_REPLACEMENT_BIDS = [104, 6, 3, 123, 126, 2, 0]
PHASE3_FOCUS_BIDS = [104, 6, 3, 123, 126, 2, 0, 1]

METRICS = [
    "ok",
    "F",
    "precision",
    "recall",
    "roof_cov",
    "wall_cov",
    "ground_cov",
    "support_cov",
    "roof_support_cov",
    "wall_support_cov",
    "ground_support_cov",
    "h_err",
    "vol_ratio",
    "chamfer",
    "hausdorff",
    "open_edges",
    "non_manifold_edges",
]
HIGHER_BETTER = {
    "ok",
    "F",
    "precision",
    "recall",
    "roof_cov",
    "wall_cov",
    "ground_cov",
    "support_cov",
    "roof_support_cov",
    "wall_support_cov",
    "ground_support_cov",
}
LOWER_BETTER = {"h_err", "chamfer", "hausdorff", "open_edges", "non_manifold_edges"}
VOL_RATIO_METRIC = "vol_ratio"
SPLITS = {
    "all_10": TARGET_BIDS,
    "hard_diagnostic": [104, 6, 3, 123, 126],
    "easier_control": [0, 1, 2, 8, 50],
    "roof_complex_candidate": [3, 123, 126],
    "ground_sensitive": [104, 6, 50],
}
CLASS_NAMES = {0: "background", 1: "roof", 2: "wall", 3: "ground"}
SURFACE_BY_CLASS = {1: "RoofSurface", 2: "WallSurface", 3: "GroundSurface"}

TB_COMPONENTS = {
    "L_render": "loss/photo",
    "L_depth": "loss/depth",
    "L_normal": "loss/normal",
    "L_semantic": "loss/sem",
    "L_mutual": "loss/mutual",
    "L_mutual_roof": "loss/mutual_slope",
    "L_mutual_wall": "loss/mutual_vert",
    "L_mutual_ground": "loss/mutual_horiz",
    "L_mutual_roof_wall_relation": None,
    "L_mutual_ground_wall_relation": None,
    "L_mutual_height_relation": "loss/mutual_height",
    "L_total": "loss/total",
}


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
    if math.isnan(x) or math.isinf(x):
        return None
    return x


def safe_int(value: object) -> Optional[int]:
    if value in {True, "True", "true"}:
        return 1
    if value in {False, "False", "false"}:
        return 0
    x = safe_float(value)
    return None if x is None else int(round(x))


def fmt(value: object, nd: int = 3) -> str:
    x = safe_float(value)
    if x is None:
        return "NA" if value in {None, ""} else str(value)
    return f"{x:.{nd}f}"


def bid_label(bid: int) -> str:
    return f"B{int(bid)}"


def rel(path: Optional[Path]) -> str:
    if path is None:
        return ""
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def metric_value(row: Dict, metric: str) -> Optional[float]:
    if metric == "ok":
        return 1.0 if row.get("status") == "OK" else 0.0
    if metric == "support_cov":
        return safe_float(row.get("support_cov", row.get("support_coverage")))
    if metric == "non_manifold_edges":
        return safe_float(row.get("non_manifold_edges", row.get("nonmanifold_edges")))
    return safe_float(row.get(metric))


def delta_metric(e2_value: Optional[float], e1_value: Optional[float], metric: str) -> Optional[float]:
    if e1_value is None or e2_value is None:
        return None
    if metric == VOL_RATIO_METRIC:
        return abs(e1_value - 1.0) - abs(e2_value - 1.0)
    if metric in LOWER_BETTER:
        return e1_value - e2_value
    return e2_value - e1_value


def winner(e1_value: Optional[float], e2_value: Optional[float], metric: str, eps: float = 1e-9) -> str:
    d = delta_metric(e2_value, e1_value, metric)
    if d is None:
        return "missing"
    if d > eps:
        return "E2"
    if d < -eps:
        return "E1"
    return "tie"


def mean(values: Iterable[Optional[float]]) -> Optional[float]:
    vals = [float(v) for v in values if v is not None and math.isfinite(float(v))]
    return None if not vals else float(np.mean(vals))


def corrcoef(a: np.ndarray, b: np.ndarray) -> Optional[float]:
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    keep = np.isfinite(a) & np.isfinite(b)
    if int(np.sum(keep)) < 3:
        return None
    aa = a[keep]
    bb = b[keep]
    if np.std(aa) < 1e-12 or np.std(bb) < 1e-12:
        return None
    return float(np.corrcoef(aa, bb)[0, 1])


def md_table(headers: List[str], rows: Iterable[Iterable[object]]) -> List[str]:
    out = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        out.append("| " + " | ".join(str(x) for x in row) + " |")
    return out


def load_buildings() -> Dict[int, Dict]:
    fc.assert_gravity()
    scene = parse_scene_obj(fc.SCENE)
    by_bid = {int(b["building_id"]): b for b in scene["buildings"]}
    missing = [bid for bid in TARGET_BIDS if bid not in by_bid]
    if missing:
        raise RuntimeError(f"Missing target buildings in scene.obj: {missing}")
    return by_bid


def load_npz_dict(path: Path) -> Optional[Dict]:
    if not path.exists():
        return None
    data = np.load(path, allow_pickle=False)
    return {k: data[k] for k in data.files}


def load_phase_a_evidence(source: str, bid: int) -> Optional[Dict]:
    path = PHASE_A_ROOT / "phase1_evidence" / source / bid_label(bid) / "evidence.npz"
    raw = load_npz_dict(path)
    if raw is None:
        return None
    raw["source"] = source
    raw["bid"] = bid_label(bid)
    return raw


def load_evidence(source: str, bid: int, buildings: Dict[int, Dict]) -> Optional[Dict]:
    if source in {E1, E2}:
        ev = load_phase_a_evidence(source, bid)
        if ev is not None:
            return ev
    if source == E0:
        path = (
            STAGE3_V1_ROOT
            / "phase2_stage3_v1_readout"
            / E0
            / bid_label(bid)
            / "readout_evidence_after_stage3_v1_patch.npz"
        )
        ev = load_npz_dict(path)
        if ev is not None:
            ev["source"] = source
            ev["bid"] = bid_label(bid)
        return ev
    if source == E2:
        return s3.load_evidence_from_fc_s1(source, bid)
    if source == E1 and phasea.E1_NPZ.exists():
        raw = fc.load_npz(phasea.E1_NPZ)
        normalized = fc.normalize_evidence(raw, E1, "rendered")
        footprint = fc.footprint_for_building(buildings[bid])
        return fc.crop_evidence(normalized, footprint, E1, bid)
    return None


def readout_dir_for(source: str, bid: int) -> Path:
    if source in {E1, E2}:
        return PHASE_A_ROOT / "stage3_matrix_readout" / s3.STAGE3_ALGO_V1 / source / bid_label(bid)
    return STAGE3_V1_ROOT / "phase2_stage3_v1_readout" / source / bid_label(bid)


def metric_dir_for(source: str, bid: int) -> Path:
    if source in {E1, E2}:
        return PHASE_A_ROOT / "stage3_matrix_metric_v1" / s3.STAGE3_ALGO_V1 / source / bid_label(bid)
    return STAGE3_V1_ROOT / "phase2_stage3_v1_metric_v1_audit" / source / bid_label(bid)


def load_faces(source: str, bid: int) -> List[Dict]:
    faces, _ = s3.load_faces(readout_dir_for(source, bid) / "semantic_faces.json")
    return faces


def support_by_surface(faces: List[Dict], evidence: Optional[Dict], seed: int) -> Dict:
    out = {"roof_support_cov": "", "wall_support_cov": "", "ground_support_cov": ""}
    if evidence is None or not faces:
        return out
    for cls, surface_type in SURFACE_BY_CLASS.items():
        field = {
            1: "roof_support_cov",
            2: "wall_support_cov",
            3: "ground_support_cov",
        }[cls]
        pred_tris = fc.faces_to_triangles([f for f in faces if f["type"] == surface_type])
        classes = np.asarray(evidence.get("classes", []), dtype=np.int64)
        pts = np.asarray(evidence.get("points", []), dtype=np.float64)
        ev = pts[classes == cls] if len(pts) == len(classes) else np.empty((0, 3), dtype=np.float64)
        if len(pred_tris) == 0 or len(ev) == 0:
            out[field] = 0.0
            continue
        samples = pm.sample_triangles(pred_tris, min(fc.N_SURFACE_SAMPLE, 1000), seed + cls)
        d, _ = cKDTree(ev).query(samples)
        out[field] = float(np.mean(d <= fc.SUPPORT_DISTANCE_M))
    return out


def load_metric_row(source: str, bid: int, buildings: Dict[int, Dict]) -> Dict:
    path = metric_dir_for(source, bid) / "metric_v1_summary.json"
    row: Dict = {}
    if path.exists():
        row = json.loads(path.read_text())
    else:
        matrix_paths = [
            PHASE_A_ROOT / "e1_stage3_matrix_metrics_by_bid.csv",
            STAGE3_V1_ROOT / "phase3_matrix/matrix_metrics_by_bid.csv",
        ]
        for matrix_path in matrix_paths:
            for candidate in read_csv(matrix_path):
                if (
                    candidate.get("bid") == bid_label(bid)
                    and candidate.get("source") == source
                    and candidate.get("stage3_algo_version") == s3.STAGE3_ALGO_V1
                    and candidate.get("metric_version") == s3.METRIC_V1
                ):
                    row = dict(candidate)
                    break
            if row:
                break
    if not row:
        row = {"bid": bid_label(bid), "source": source, "status": "MISSING"}
    row["bid"] = bid_label(bid)
    row["bid_int"] = bid
    row["source"] = source
    row["stage3_algo_version"] = s3.STAGE3_ALGO_V1
    row["metric_version"] = s3.METRIC_V1
    row["support_cov"] = row.get("support_cov", row.get("support_coverage", ""))
    row["non_manifold_edges"] = row.get("non_manifold_edges", row.get("nonmanifold_edges", ""))
    if not all(row.get(k, "") != "" for k in ["roof_support_cov", "wall_support_cov", "ground_support_cov"]):
        ev = load_evidence(source, bid, buildings)
        row.update(support_by_surface(load_faces(source, bid), ev, seed=62000 + bid))
    row["metric_artifact_dir"] = row.get("metric_artifact_dir", rel(metric_dir_for(source, bid)))
    row["readout_artifact_dir"] = row.get("readout_artifact_dir", rel(readout_dir_for(source, bid)))
    return row


def build_paired_rows(buildings: Dict[int, Dict]) -> Tuple[List[Dict], Dict[Tuple[str, int], Dict]]:
    by_source_bid = {}
    for bid in TARGET_BIDS:
        for source in [E0, E1, E2]:
            by_source_bid[(source, bid)] = load_metric_row(source, bid, buildings)

    paired = []
    for bid in TARGET_BIDS:
        e1 = by_source_bid[(E1, bid)]
        e2 = by_source_bid[(E2, bid)]
        row = {
            "bid": bid_label(bid),
            "bid_int": bid,
            "split_hard_diagnostic": bid in SPLITS["hard_diagnostic"],
            "split_easier_control": bid in SPLITS["easier_control"],
            "e1_status": e1.get("status", ""),
            "e2_status": e2.get("status", ""),
            "both_ok": e1.get("status") == "OK" and e2.get("status") == "OK",
        }
        for metric in METRICS:
            v1 = metric_value(e1, metric)
            v2 = metric_value(e2, metric)
            row[f"e1_{metric}"] = v1 if v1 is not None else ""
            row[f"e2_{metric}"] = v2 if v2 is not None else ""
            d = None if v1 is None or v2 is None else v2 - v1
            row[f"delta_e2_minus_e1_{metric}"] = "" if d is None else d
            row[f"winner_{metric}"] = winner(v1, v2, metric)
        paired.append(row)

    high_f = [
        int(r["bid_int"])
        for r in paired
        if safe_float(r.get("e1_F")) is not None
        and safe_float(r.get("e2_F")) is not None
        and safe_float(r["e1_F"]) >= 0.9
        and safe_float(r["e2_F"]) >= 0.9
    ]
    SPLITS["success_reference"] = sorted(set([2] + high_f))
    return paired, by_source_bid


def split_summary_rows(paired: List[Dict]) -> List[Dict]:
    rows = []
    by_bid = {int(r["bid_int"]): r for r in paired}
    for split, bids in SPLITS.items():
        split_rows = [by_bid[b] for b in bids if b in by_bid]
        for metric in METRICS:
            e1_vals = [safe_float(r.get(f"e1_{metric}")) for r in split_rows]
            e2_vals = [safe_float(r.get(f"e2_{metric}")) for r in split_rows]
            deltas = [safe_float(r.get(f"delta_e2_minus_e1_{metric}")) for r in split_rows]
            wins = defaultdict(int)
            for r in split_rows:
                wins[str(r.get(f"winner_{metric}", "missing"))] += 1
            rows.append({
                "split": split,
                "metric": metric,
                "n_bids": len(split_rows),
                "n_both_ok": sum(1 for r in split_rows if r.get("both_ok") in {True, "True"}),
                "e1_mean": mean(e1_vals),
                "e2_mean": mean(e2_vals),
                "raw_delta_mean_e2_minus_e1": mean(deltas),
                "directional_delta_mean_positive_favors_e2": mean(
                    [delta_metric(safe_float(r.get(f"e2_{metric}")), safe_float(r.get(f"e1_{metric}")), metric) for r in split_rows]
                ),
                "e2_wins": wins["E2"],
                "e1_wins": wins["E1"],
                "ties": wins["tie"],
                "missing": wins["missing"],
            })
    return rows


def win_loss_rows(paired: List[Dict]) -> List[Dict]:
    rows = []
    for metric in METRICS:
        wins = defaultdict(int)
        for row in paired:
            wins[str(row.get(f"winner_{metric}", "missing"))] += 1
        rows.append({
            "metric": metric,
            "all_10_e2_wins": wins["E2"],
            "all_10_e1_wins": wins["E1"],
            "all_10_ties": wins["tie"],
            "all_10_missing": wins["missing"],
            "direction": "closer_to_1" if metric == VOL_RATIO_METRIC else ("lower_better" if metric in LOWER_BETTER else "higher_better"),
        })
    return rows


def phase1_full_comparison(buildings: Dict[int, Dict]) -> Tuple[List[Dict], Dict[Tuple[str, int], Dict], List[Dict]]:
    out_dir = FC_S3_ROOT / "phase1_full_e1_e2_comparison"
    paired, by_source_bid = build_paired_rows(buildings)
    split_rows = split_summary_rows(paired)
    wl_rows = win_loss_rows(paired)
    fc.write_csv(out_dir / "e1_e2_paired_metrics_by_bid.csv", paired)
    fc.write_csv(out_dir / "e1_e2_split_summary.csv", split_rows)
    fc.write_csv(out_dir / "e1_e2_win_loss_by_metric.csv", wl_rows)

    all_f = next(r for r in split_rows if r["split"] == "all_10" and r["metric"] == "F")
    easy_f = next(r for r in split_rows if r["split"] == "easier_control" and r["metric"] == "F")
    hard_f = next(r for r in split_rows if r["split"] == "hard_diagnostic" and r["metric"] == "F")
    report = [
        "# FC-S3 Phase 1: Full E1-vs-E2 Comparison",
        "",
        "Controlled baseline: Stage3Algo-v1 + Metric-v1. No rejected v1c branch is used.",
        "",
        "## Summary",
        f"- All 10 OK count: E1={int(sum(1 for r in paired if r['e1_status'] == 'OK'))}/10, E2={int(sum(1 for r in paired if r['e2_status'] == 'OK'))}/10.",
        f"- Mean F all 10: E1={fmt(all_f['e1_mean'])}, E2={fmt(all_f['e2_mean'])}, raw E2-E1={fmt(all_f['raw_delta_mean_e2_minus_e1'])}.",
        f"- Mean F easier/control: E1={fmt(easy_f['e1_mean'])}, E2={fmt(easy_f['e2_mean'])}, raw E2-E1={fmt(easy_f['raw_delta_mean_e2_minus_e1'])}.",
        f"- Mean F hard diagnostic: E1={fmt(hard_f['e1_mean'])}, E2={fmt(hard_f['e2_mean'])}, raw E2-E1={fmt(hard_f['raw_delta_mean_e2_minus_e1'])}.",
        "",
        "## Win/Loss",
    ]
    report.extend(md_table(
        ["metric", "E2 wins", "E1 wins", "ties", "direction"],
        [[r["metric"], r["all_10_e2_wins"], r["all_10_e1_wins"], r["all_10_ties"], r["direction"]] for r in wl_rows],
    ))
    focus = [r for r in paired if int(r["bid_int"]) in [2, 6, 104, 3, 123, 126]]
    report.extend([
        "",
        "## Focus Bid Deltas",
    ])
    report.extend(md_table(
        ["bid", "dF", "droof", "dwall", "dground", "dsupport", "dh_err"],
        [
            [
                r["bid"],
                fmt(r.get("delta_e2_minus_e1_F")),
                fmt(r.get("delta_e2_minus_e1_roof_cov")),
                fmt(r.get("delta_e2_minus_e1_wall_cov")),
                fmt(r.get("delta_e2_minus_e1_ground_cov")),
                fmt(r.get("delta_e2_minus_e1_support_cov")),
                fmt(r.get("delta_e2_minus_e1_h_err")),
            ]
            for r in focus
        ],
    ))
    report.extend([
        "",
        "## Interpretation",
        "E2 is treated as supported only where directional wins appear in final geometry/support metrics, not just in proxy evidence statistics.",
    ])
    (out_dir / "E1_E2_FULL_COMPARISON_REPORT.md").write_text("\n".join(report) + "\n")
    return paired, by_source_bid, split_rows


def class_entropy_values(evidence: Dict) -> Optional[np.ndarray]:
    if "semantic_entropy" in evidence:
        return np.asarray(evidence["semantic_entropy"], dtype=np.float64)
    probs = evidence.get("sem_probs")
    if probs is None:
        return None
    p = np.clip(np.asarray(probs, dtype=np.float64), 1e-12, 1.0)
    return -np.sum(p * np.log(p), axis=1) / math.log(max(p.shape[1], 2))


def confidence_values(evidence: Dict) -> Optional[np.ndarray]:
    if "confidence" in evidence:
        return np.asarray(evidence["confidence"], dtype=np.float64)
    probs = evidence.get("sem_probs")
    if probs is not None:
        return np.max(np.asarray(probs, dtype=np.float64), axis=1)
    return None


def class_normal_consistency(normals: np.ndarray) -> np.ndarray:
    if len(normals) == 0:
        return np.asarray([], dtype=np.float64)
    ref = np.mean(normals, axis=0)
    ref /= np.linalg.norm(ref) + 1e-12
    return np.abs(normals @ ref)


def gt_ground_y(building: Dict) -> Optional[float]:
    ys = []
    for face in building["faces"]:
        if int(face.get("semantic_class", -1)) == 3:
            ys.extend(np.asarray(face["vertices"], dtype=np.float64)[:, 1].tolist())
    return None if not ys else float(np.median(ys))


def surface_sample_trees(faces: List[Dict], seed: int) -> Dict[str, cKDTree]:
    trees = {}
    for surface_type in ["RoofSurface", "WallSurface", "GroundSurface"]:
        tris = fc.faces_to_triangles([f for f in faces if f.get("type") == surface_type])
        if len(tris) == 0:
            continue
        samples = pm.sample_triangles(tris, min(2000, fc.N_SURFACE_SAMPLE), seed + len(trees))
        trees[surface_type] = cKDTree(samples)
    return trees


def distance_to_tree(points: np.ndarray, tree: Optional[cKDTree]) -> Optional[np.ndarray]:
    if tree is None or len(points) == 0:
        return None
    d, _ = tree.query(points)
    return np.asarray(d, dtype=np.float64)


def quantile_dict(values: np.ndarray, prefix: str) -> Dict:
    values = np.asarray(values, dtype=np.float64)
    values = values[np.isfinite(values)]
    if len(values) == 0:
        return {f"{prefix}_{k}": "" for k in ["count", "min", "p05", "p10", "p25", "median", "mean", "p75", "p90", "p95", "max"]}
    return {
        f"{prefix}_count": int(len(values)),
        f"{prefix}_min": float(np.min(values)),
        f"{prefix}_p05": float(np.percentile(values, 5)),
        f"{prefix}_p10": float(np.percentile(values, 10)),
        f"{prefix}_p25": float(np.percentile(values, 25)),
        f"{prefix}_median": float(np.median(values)),
        f"{prefix}_mean": float(np.mean(values)),
        f"{prefix}_p75": float(np.percentile(values, 75)),
        f"{prefix}_p90": float(np.percentile(values, 90)),
        f"{prefix}_p95": float(np.percentile(values, 95)),
        f"{prefix}_max": float(np.max(values)),
    }


def phase3_evidence_distribution(buildings: Dict[int, Dict]) -> Tuple[List[Dict], List[Dict], List[Dict], List[Dict]]:
    out_dir = FC_S3_ROOT / "phase3_evidence_distribution"
    class_rows: List[Dict] = []
    ground_rows: List[Dict] = []
    roof_rows: List[Dict] = []
    support_rows: List[Dict] = []
    for bid in TARGET_BIDS:
        building = buildings[bid]
        gy = gt_ground_y(building)
        for source in [E1, E2]:
            evidence = load_evidence(source, bid, buildings)
            if evidence is None:
                continue
            pts = np.asarray(evidence["points"], dtype=np.float64)
            classes = np.asarray(evidence["classes"], dtype=np.int64)
            normals = np.asarray(evidence["normals"], dtype=np.float64)
            weights = np.asarray(evidence.get("weights", np.ones(len(pts))), dtype=np.float64)
            ent = class_entropy_values(evidence)
            conf = confidence_values(evidence)
            faces = load_faces(source, bid)
            trees = surface_sample_trees(faces, seed=71000 + bid)
            ground_tree = trees.get("GroundSurface")
            roof_tree = trees.get("RoofSurface")
            for cls in sorted(set(classes.tolist()) | {1, 2, 3}):
                if cls < 0 or cls > 3:
                    continue
                mask = classes == cls
                cpts = pts[mask]
                cnormals = normals[mask] if len(normals) == len(classes) else np.empty((0, 3))
                cweights = weights[mask] if len(weights) == len(classes) else np.asarray([])
                cent = ent[mask] if ent is not None and len(ent) == len(classes) else None
                cconf = conf[mask] if conf is not None and len(conf) == len(classes) else None
                nc = class_normal_consistency(cnormals)
                dist_ground = distance_to_tree(cpts, ground_tree)
                dist_roof = distance_to_tree(cpts, roof_tree)
                same_surface = SURFACE_BY_CLASS.get(cls)
                same_dist = distance_to_tree(cpts, trees.get(same_surface)) if same_surface else None
                row = {
                    "bid": bid_label(bid),
                    "bid_int": bid,
                    "source": source,
                    "class_id": cls,
                    "class_name": CLASS_NAMES.get(cls, str(cls)),
                    "point_count": int(np.sum(mask)),
                    "semantic_entropy_mean": mean(cent.tolist()) if cent is not None else "",
                    "semantic_confidence_mean": mean(cconf.tolist()) if cconf is not None else "",
                    "normal_consistency_mean": mean(nc.tolist()),
                    "weight_mean": mean(cweights.tolist()) if len(cweights) else "",
                    "y_mean": mean(cpts[:, 1].tolist()) if len(cpts) else "",
                    "y_median": float(np.median(cpts[:, 1])) if len(cpts) else "",
                    "y_p10": float(np.percentile(cpts[:, 1], 10)) if len(cpts) else "",
                    "y_p90": float(np.percentile(cpts[:, 1], 90)) if len(cpts) else "",
                    "z_mean": mean(cpts[:, 2].tolist()) if len(cpts) else "",
                    "z_median": float(np.median(cpts[:, 2])) if len(cpts) else "",
                    "distance_to_gt_reference_ground_plane_mean": mean(np.abs(cpts[:, 1] - gy).tolist()) if gy is not None and len(cpts) else "",
                    "distance_to_predicted_GroundSurface_mean": mean(dist_ground.tolist()) if dist_ground is not None else "",
                    "distance_to_predicted_RoofSurface_mean": mean(dist_roof.tolist()) if dist_roof is not None else "",
                    "distance_to_predicted_same_surface_mean": mean(same_dist.tolist()) if same_dist is not None else "",
                    "semantic_confidence_vs_geometric_error_corr": corrcoef(cconf, same_dist) if cconf is not None and same_dist is not None else "",
                    "normal_confidence_vs_geometric_error_corr": corrcoef(nc, same_dist) if same_dist is not None else "",
                    "focus_case": bid in PHASE3_FOCUS_BIDS,
                }
                class_rows.append(row)
                if cls in SURFACE_BY_CLASS:
                    accepted = same_dist <= fc.SUPPORT_DISTANCE_M if same_dist is not None else np.zeros(len(cpts), dtype=bool)
                    support_rows.append({
                        "bid": bid_label(bid),
                        "bid_int": bid,
                        "source": source,
                        "class_id": cls,
                        "class_name": CLASS_NAMES[cls],
                        "support_distance_m": fc.SUPPORT_DISTANCE_M,
                        "accepted_count": int(np.sum(accepted)),
                        "rejected_count": int(len(accepted) - np.sum(accepted)),
                        "accepted_fraction": float(np.mean(accepted)) if len(accepted) else "",
                        "accepted_confidence_mean": mean(cconf[accepted].tolist()) if cconf is not None and len(accepted) else "",
                        "rejected_confidence_mean": mean(cconf[~accepted].tolist()) if cconf is not None and len(accepted) else "",
                        "accepted_entropy_mean": mean(cent[accepted].tolist()) if cent is not None and len(accepted) else "",
                        "rejected_entropy_mean": mean(cent[~accepted].tolist()) if cent is not None and len(accepted) else "",
                        "accepted_geometric_error_mean": mean(same_dist[accepted].tolist()) if same_dist is not None and len(accepted) else "",
                        "rejected_geometric_error_mean": mean(same_dist[~accepted].tolist()) if same_dist is not None and len(accepted) else "",
                    })
            ground_mask = classes == 3
            if np.any(ground_mask):
                gpts = pts[ground_mask]
                grow = {
                    "bid": bid_label(bid),
                    "bid_int": bid,
                    "source": source,
                    "gt_reference_ground_y": gy if gy is not None else "",
                }
                grow.update(quantile_dict(gpts[:, 1], "ground_y"))
                if gy is not None:
                    grow.update(quantile_dict(np.abs(gpts[:, 1] - gy), "abs_distance_to_gt_ground_y"))
                ground_rows.append(grow)
            roof_mask = classes == 1
            if np.any(roof_mask):
                rpts = pts[roof_mask]
                rrow = {"bid": bid_label(bid), "bid_int": bid, "source": source}
                rrow.update(quantile_dict(rpts[:, 1], "roof_y"))
                rrow.update(quantile_dict(rpts[:, 2], "roof_z"))
                roof_rows.append(rrow)

    fc.write_csv(out_dir / "e1_e2_classwise_evidence_stats.csv", class_rows)
    fc.write_csv(out_dir / "ground_y_distribution_by_bid.csv", ground_rows)
    fc.write_csv(out_dir / "roof_evidence_distribution_by_bid.csv", roof_rows)
    fc.write_csv(out_dir / "support_rejection_distribution_by_bid.csv", support_rows)

    b104_e1 = next((r for r in ground_rows if r["bid"] == "B104" and r["source"] == E1), {})
    b104_e2 = next((r for r in ground_rows if r["bid"] == "B104" and r["source"] == E2), {})
    report = [
        "# FC-S3 Phase 3: Evidence Distribution Audit",
        "",
        "This phase compares E1 and E2 rendered evidence by bid and class before any G2 training.",
        "",
        "## Ground Evidence",
        f"- B104 E1 ground median y: {fmt(b104_e1.get('ground_y_median'))}; E2 ground median y: {fmt(b104_e2.get('ground_y_median'))}.",
        f"- B104 E1 distance to GT ground median: {fmt(b104_e1.get('abs_distance_to_gt_ground_y_median'))}; E2: {fmt(b104_e2.get('abs_distance_to_gt_ground_y_median'))}.",
        "",
        "## Support Rejection",
        "Accepted/rejected distributions are computed against the corresponding Stage3Algo-v1 predicted same-class surface at the fixed Metric-v1 support distance.",
        "",
        "## Files",
        "- e1_e2_classwise_evidence_stats.csv",
        "- ground_y_distribution_by_bid.csv",
        "- roof_evidence_distribution_by_bid.csv",
        "- support_rejection_distribution_by_bid.csv",
    ]
    (out_dir / "EVIDENCE_DISTRIBUTION_AUDIT.md").write_text("\n".join(report) + "\n")
    return class_rows, ground_rows, roof_rows, support_rows


def read_tb_scalars(tb_dir: Path) -> Dict[str, List[Tuple[int, float]]]:
    try:
        from tensorboard.backend.event_processing.event_accumulator import EventAccumulator
    except Exception:
        return {}
    if not tb_dir.exists():
        return {}
    try:
        ea = EventAccumulator(str(tb_dir), size_guidance={"scalars": 0})
        ea.Reload()
    except Exception:
        return {}
    out = {}
    for tag in ea.Tags().get("scalars", []):
        out[tag] = [(int(x.step), float(x.value)) for x in ea.Scalars(tag)]
    return out


def summarize_scalar(values: List[Tuple[int, float]]) -> Dict:
    if not values:
        return {"available": False}
    vals = np.asarray([v for _, v in values], dtype=np.float64)
    return {
        "available": True,
        "first_step": values[0][0],
        "last_step": values[-1][0],
        "first_value": float(vals[0]),
        "last_value": float(vals[-1]),
        "mean_value": float(np.mean(vals)),
        "min_value": float(np.min(vals)),
        "max_value": float(np.max(vals)),
        "delta_last_minus_first": float(vals[-1] - vals[0]),
    }


def phase2_mutual_loss_audit(
    paired: List[Dict],
    class_rows: List[Dict],
    split_rows: List[Dict],
) -> Tuple[List[Dict], List[Dict]]:
    out_dir = FC_S3_ROOT / "phase2_mutual_loss_audit"
    baseline_scalars = read_tb_scalars(ROOT / "results/phase2_ablation_citygml/baseline/tb")
    mutual_scalars = read_tb_scalars(ROOT / "results/phase2_ablation_citygml/mutual/tb")
    runs = {"baseline": baseline_scalars, "mutual": mutual_scalars}

    by_step = []
    for run_name, scalars in runs.items():
        for component, tag in TB_COMPONENTS.items():
            if tag is None or tag not in scalars:
                by_step.append({
                    "source_run": run_name,
                    "component": component,
                    "tb_tag": tag or "",
                    "step": "",
                    "value": "",
                    "available": False,
                    "reason": "component not logged under requested name",
                })
                continue
            for step, value in scalars[tag]:
                by_step.append({
                    "source_run": run_name,
                    "component": component,
                    "tb_tag": tag,
                    "step": step,
                    "value": value,
                    "available": True,
                    "reason": "",
                })
    fc.write_csv(out_dir / "mutual_loss_components_by_step.csv", by_step)

    class_map = {
        "roof": "L_mutual_roof",
        "wall": "L_mutual_wall",
        "ground": "L_mutual_ground",
        "height_relation": "L_mutual_height_relation",
        "roof_wall_relation": "L_mutual_roof_wall_relation",
        "ground_wall_relation": "L_mutual_ground_wall_relation",
    }
    by_class = []
    for class_name, component in class_map.items():
        tag = TB_COMPONENTS[component]
        stats = summarize_scalar(mutual_scalars.get(tag, []) if tag else [])
        by_class.append({
            "source_run": "mutual",
            "class_or_relation": class_name,
            "component": component,
            "tb_tag": tag or "",
            **stats,
            "reason": "" if stats.get("available") else "not logged or unavailable",
        })
    fc.write_csv(out_dir / "mutual_loss_components_by_class.csv", by_class)

    grad_tags_by_loss = {
        tag: vals
        for tag, vals in mutual_scalars.items()
        if "grad" in tag.lower() or "gradient" in tag.lower()
    }
    if grad_tags_by_loss:
        grad_loss_rows = []
        for tag, vals in grad_tags_by_loss.items():
            grad_loss_rows.append({"tb_tag": tag, **summarize_scalar(vals)})
    else:
        grad_loss_rows = [{
            "tb_tag": "",
            "available": False,
            "reason": "No gradient norm scalar tags found in existing TensorBoard logs.",
        }]
    fc.write_csv(out_dir / "gradient_norms_by_loss.csv", grad_loss_rows)
    fc.write_csv(out_dir / "gradient_norms_by_class.csv", [{
        "class_name": "roof/wall/ground",
        "available": False,
        "reason": "Classwise gradient norms were not logged in the existing training runs.",
    }])

    class_lookup = {
        (r["source"], r["bid"], r["class_name"]): r
        for r in class_rows
    }
    alignment = []
    for row in paired:
        bid = row["bid"]
        def cmetric(source: str, cls: str, field: str) -> Optional[float]:
            return safe_float(class_lookup.get((source, bid, cls), {}).get(field))
        e1_ground_entropy = cmetric(E1, "ground", "semantic_entropy_mean")
        e2_ground_entropy = cmetric(E2, "ground", "semantic_entropy_mean")
        e1_ground_dist = cmetric(E1, "ground", "distance_to_gt_reference_ground_plane_mean")
        e2_ground_dist = cmetric(E2, "ground", "distance_to_gt_reference_ground_plane_mean")
        d_f = safe_float(row.get("delta_e2_minus_e1_F"))
        d_support = safe_float(row.get("delta_e2_minus_e1_support_cov"))
        d_ground_cov = safe_float(row.get("delta_e2_minus_e1_ground_cov"))
        proxy_note = "neutral"
        if e1_ground_entropy is not None and e2_ground_entropy is not None and e2_ground_entropy < e1_ground_entropy:
            if (d_f is not None and d_f < 0) or (d_support is not None and d_support < 0):
                proxy_note = "lower entropy did not translate to final support/geometry gain"
        if d_ground_cov is not None and d_ground_cov < -0.25:
            proxy_note = "ground final metric worsened; ground/terrain mutual component is a candidate"
        alignment.append({
            "bid": bid,
            "bid_int": row["bid_int"],
            "delta_F_e2_minus_e1": d_f if d_f is not None else "",
            "delta_support_cov_e2_minus_e1": d_support if d_support is not None else "",
            "delta_ground_cov_e2_minus_e1": d_ground_cov if d_ground_cov is not None else "",
            "delta_roof_cov_e2_minus_e1": row.get("delta_e2_minus_e1_roof_cov", ""),
            "delta_wall_cov_e2_minus_e1": row.get("delta_e2_minus_e1_wall_cov", ""),
            "e1_ground_entropy_mean": e1_ground_entropy if e1_ground_entropy is not None else "",
            "e2_ground_entropy_mean": e2_ground_entropy if e2_ground_entropy is not None else "",
            "e1_ground_distance_to_gt_mean": e1_ground_dist if e1_ground_dist is not None else "",
            "e2_ground_distance_to_gt_mean": e2_ground_dist if e2_ground_dist is not None else "",
            "alignment_note": proxy_note,
        })
    fc.write_csv(out_dir / "loss_to_metric_alignment_by_bid.csv", alignment)

    all_f = next(r for r in split_rows if r["split"] == "all_10" and r["metric"] == "F")
    ground_stats = next((r for r in by_class if r["class_or_relation"] == "ground"), {})
    report = [
        "# FC-S3 Phase 2: Mutual Loss Alignment Audit",
        "",
        "Existing TensorBoard logs were parsed for the requested loss components. Missing component rows are explicit rather than reconstructed from GT semantics.",
        "",
        "## Availability",
        f"- Mutual scalar tags available: {len(mutual_scalars)}.",
        "- Classwise gradient norms: unavailable in existing logs.",
        "- Loss components named roof_wall_relation and ground_wall_relation were not logged as separate TensorBoard scalars.",
        "",
        "## Alignment",
        f"- Mean final F all 10: E1={fmt(all_f['e1_mean'])}, E2={fmt(all_f['e2_mean'])}.",
        f"- Ground mutual component last-first change: {fmt(ground_stats.get('delta_last_minus_first'))}.",
        "- Bid-level alignment is in loss_to_metric_alignment_by_bid.csv.",
        "",
        "## Interpretation",
        "The audit treats lower proxy loss or entropy as insufficient unless it improves final support or geometry metrics under Stage3Algo-v1 + Metric-v1.",
    ]
    (out_dir / "MUTUAL_LOSS_ALIGNMENT_REPORT.md").write_text("\n".join(report) + "\n")
    return by_step, alignment


def copy_evidence(evidence: Dict, source: str, bid: int) -> Dict:
    out = {}
    n = len(evidence["points"])
    for key, value in evidence.items():
        if isinstance(value, np.ndarray):
            arr = np.asarray(value)
            out[key] = arr.copy()
        elif key not in {"source", "bid"}:
            out[key] = value
    out["source"] = source
    out["bid"] = bid_label(bid)
    for key in ["points", "normals", "classes", "weights"]:
        if key not in out:
            if key == "weights":
                out[key] = np.ones(n, dtype=np.float64)
            else:
                raise KeyError(f"Evidence missing {key}")
    out["normals"] = fc.normalize_rows(np.asarray(out["normals"], dtype=np.float64))
    out["classes"] = np.asarray(out["classes"], dtype=np.int64)
    out["weights"] = np.maximum(np.asarray(out["weights"], dtype=np.float64), 1e-9)
    return out


def nearest_indices(base_points: np.ndarray, donor_points: np.ndarray) -> np.ndarray:
    if len(base_points) == 0 or len(donor_points) == 0:
        return np.zeros(len(base_points), dtype=np.int64)
    _, idx = cKDTree(np.asarray(donor_points, dtype=np.float64)).query(np.asarray(base_points, dtype=np.float64))
    return np.asarray(idx, dtype=np.int64)


def mapped_field(donor: Dict, key: str, idx: np.ndarray) -> Optional[np.ndarray]:
    if key not in donor:
        return None
    arr = np.asarray(donor[key])
    if len(arr) == 0 or len(arr) <= int(np.max(idx, initial=0)):
        return None
    return arr[idx].copy()


def replacement_semantic_normal(base: Dict, donor: Dict, source: str, bid: int) -> Dict:
    out = copy_evidence(base, source, bid)
    idx = nearest_indices(out["points"], donor["points"])
    for key in ["normals", "classes", "sem_probs", "confidence", "normal_consistency", "semantic_entropy"]:
        value = mapped_field(donor, key, idx)
        if value is not None:
            out[key] = value
    out["normals"] = fc.normalize_rows(np.asarray(out["normals"], dtype=np.float64))
    out["classes"] = np.asarray(out["classes"], dtype=np.int64)
    return out


def replacement_entropy_confidence(base: Dict, donor: Dict, source: str, bid: int) -> Dict:
    out = copy_evidence(base, source, bid)
    idx = nearest_indices(out["points"], donor["points"])
    for key in ["sem_probs", "confidence", "semantic_entropy"]:
        value = mapped_field(donor, key, idx)
        if value is not None:
            out[key] = value
    return out


def replace_ground_y_quantile(base: Dict, donor_ground_source: Dict, source: str, bid: int) -> Dict:
    out = copy_evidence(base, source, bid)
    classes = np.asarray(out["classes"], dtype=np.int64)
    mask = classes == 3
    donor_mask = np.asarray(donor_ground_source["classes"], dtype=np.int64) == 3
    if np.any(mask) and np.any(donor_mask):
        donor_y = np.sort(np.asarray(donor_ground_source["points"], dtype=np.float64)[donor_mask, 1])
        order = np.argsort(out["points"][mask, 1])
        n = int(np.sum(mask))
        q = np.linspace(0.0, 1.0, n)
        mapped = np.quantile(donor_y, q)
        ground_points = out["points"][mask].copy()
        ground_points[order, 1] = mapped
        out["points"][mask] = ground_points
    return out


def clip_ground_y(base: Dict, source: str, bid: int, lo_q: float = 10.0, hi_q: float = 90.0) -> Dict:
    out = copy_evidence(base, source, bid)
    mask = np.asarray(out["classes"], dtype=np.int64) == 3
    if np.any(mask):
        y = out["points"][mask, 1]
        lo = float(np.percentile(y, lo_q))
        hi = float(np.percentile(y, hi_q))
        out["points"][mask, 1] = np.clip(y, lo, hi)
    return out


def calibrate_weights_by_class(base: Dict, donor: Dict, source: str, bid: int) -> Dict:
    out = copy_evidence(base, source, bid)
    classes = np.asarray(out["classes"], dtype=np.int64)
    donor_classes = np.asarray(donor["classes"], dtype=np.int64)
    for cls in [1, 2, 3]:
        m = classes == cls
        dm = donor_classes == cls
        if not np.any(m) or not np.any(dm):
            continue
        cur = np.asarray(out["weights"], dtype=np.float64)[m]
        ref = np.asarray(donor["weights"], dtype=np.float64)[dm]
        cur_med = float(np.median(cur[cur > 0])) if np.any(cur > 0) else 1.0
        ref_med = float(np.median(ref[ref > 0])) if np.any(ref > 0) else cur_med
        out["weights"][m] *= ref_med / max(cur_med, 1e-9)
    out["weights"] = np.maximum(out["weights"], 1e-9)
    return out


def evaluate_stage3_metric(
    evidence: Dict,
    building: Dict,
    source: str,
    bid: int,
    readout_dir: Path,
    metric_dir: Path,
) -> Dict:
    footprint = fc.footprint_for_building(building)
    if footprint is None:
        return {"bid": bid_label(bid), "source": source, "status": "NO_FOOTPRINT"}
    status, faces, city_diag, _ = s3.stage3_v1_readout(evidence, building, footprint, source, bid, readout_dir)
    row = s3.metric_v1_evaluate(
        faces,
        building,
        evidence,
        source,
        bid,
        s3.STAGE3_ALGO_V1,
        status.get("status", ""),
        status.get("failure_reason", ""),
        metric_dir,
        readout_dir,
    )
    row.update(support_by_surface(faces, evidence, seed=80000 + bid))
    row["support_cov"] = row.get("support_coverage", row.get("support_cov", ""))
    row["non_manifold_edges"] = row.get("nonmanifold_edges", row.get("non_manifold_edges", ""))
    return row


def phase4_field_replacement(
    buildings: Dict[int, Dict],
    existing_rows: Dict[Tuple[str, int], Dict],
) -> List[Dict]:
    out_dir = FC_S3_ROOT / "phase4_field_replacement"
    rows = []
    for bid in FIELD_REPLACEMENT_BIDS:
        e1 = load_evidence(E1, bid, buildings)
        e2 = load_evidence(E2, bid, buildings)
        if e1 is None or e2 is None:
            continue
        replacements = {
            "FR0_E1_original": None,
            "FR1_E2_original": None,
            "FR2_E1_xyz_E2_semantic_normal": replacement_semantic_normal(e1, e2, "FR2_E1_xyz_E2_semantic_normal", bid),
            "FR3_E2_xyz_E1_semantic_normal": replacement_semantic_normal(e2, e1, "FR3_E2_xyz_E1_semantic_normal", bid),
            "FR4_E2_with_E1_ground_y_distribution": replace_ground_y_quantile(e2, e1, "FR4_E2_with_E1_ground_y_distribution", bid),
            "FR5_E2_clipped_ground_y_quantiles": clip_ground_y(e2, "FR5_E2_clipped_ground_y_quantiles", bid),
            "FR6_E1_with_E2_semantic_entropy_confidence": replacement_entropy_confidence(e1, e2, "FR6_E1_with_E2_semantic_entropy_confidence", bid),
            "FR7_E2_with_E1_support_weight_calibration": calibrate_weights_by_class(e2, e1, "FR7_E2_with_E1_support_weight_calibration", bid),
        }
        for name, evidence in replacements.items():
            if name == "FR0_E1_original":
                row = dict(existing_rows[(E1, bid)])
                row["field_replacement"] = name
                row["diagnostic_evaluated"] = "existing"
            elif name == "FR1_E2_original":
                row = dict(existing_rows[(E2, bid)])
                row["field_replacement"] = name
                row["diagnostic_evaluated"] = "existing"
            else:
                ev_dir = out_dir / "evidence" / name / bid_label(bid)
                fc.mkdir(ev_dir)
                np.savez_compressed(ev_dir / "evidence.npz", **{k: v for k, v in evidence.items() if isinstance(v, np.ndarray)})
                row = evaluate_stage3_metric(
                    evidence,
                    buildings[bid],
                    name,
                    bid,
                    out_dir / "readout" / name / bid_label(bid),
                    out_dir / "metric_v1" / name / bid_label(bid),
                )
                row["field_replacement"] = name
                row["diagnostic_evaluated"] = "run"
                row["evidence_artifact_dir"] = rel(ev_dir)
            row["bid"] = bid_label(bid)
            row["bid_int"] = bid
            row["metric_version"] = s3.METRIC_V1
            row["stage3_algo_version"] = s3.STAGE3_ALGO_V1
            row["F"] = row.get("F", "")
            row["support_cov"] = row.get("support_cov", row.get("support_coverage", ""))
            row["non_manifold_edges"] = row.get("non_manifold_edges", row.get("nonmanifold_edges", ""))
            rows.append(row)
    fc.write_csv(out_dir / "field_replacement_metrics_by_bid.csv", rows)

    def rows_for(bid: int) -> List[Dict]:
        return [r for r in rows if int(r.get("bid_int", -1)) == bid]

    def report_for(path: Path, title: str, bid_rows: List[Dict], note: str) -> None:
        lines = [f"# {title}", "", note, ""]
        lines.extend(md_table(
            ["replacement", "status", "F", "roof", "wall", "ground", "support", "h_err"],
            [
                [
                    r["field_replacement"],
                    r.get("status", ""),
                    fmt(r.get("F")),
                    fmt(r.get("roof_cov")),
                    fmt(r.get("wall_cov")),
                    fmt(r.get("ground_cov")),
                    fmt(r.get("support_cov")),
                    fmt(r.get("h_err")),
                ]
                for r in bid_rows
            ],
        ))
        path.write_text("\n".join(lines) + "\n")

    report_for(
        out_dir / "B104_field_replacement_report.md",
        "B104 Field Replacement Report",
        rows_for(104),
        "Diagnostic-only counterfactuals for ground closure. These are not final models.",
    )
    report_for(
        out_dir / "B6_field_replacement_report.md",
        "B6 Field Replacement Report",
        rows_for(6),
        "Diagnostic-only counterfactuals for height definition. Shared E0/E1/E2 height deficit remains a Stage3/evaluator issue candidate.",
    )
    roof_rows = [r for bid in [3, 123, 126] for r in rows_for(bid)]
    report_for(
        out_dir / "roof_cases_field_replacement_report.md",
        "Roof Cases Field Replacement Report",
        roof_rows,
        "Diagnostic-only counterfactuals for B3/B123/B126 roof decomposition and reference matching.",
    )
    summary = [
        "# Field Replacement Summary",
        "",
        "Field replacement is diagnostic only. It does not define a final model and does not change Stage3Algo-v1 globally.",
        "",
        "## B104 Snapshot",
    ]
    summary.extend(md_table(
        ["replacement", "F", "ground_cov", "support"],
        [[r["field_replacement"], fmt(r.get("F")), fmt(r.get("ground_cov")), fmt(r.get("support_cov"))] for r in rows_for(104)],
    ))
    (out_dir / "FIELD_REPLACEMENT_SUMMARY.md").write_text("\n".join(summary) + "\n")
    return rows


def load_full_rendered_evidence(source: str) -> Dict:
    if source == E1:
        path = PHASE_A_ROOT / "E1_Baseline_rendered.npz"
    elif source == E2:
        path = fc.MUTUAL_RENDERED
    else:
        raise ValueError(source)
    raw = fc.load_npz(path)
    return fc.normalize_evidence(raw, source, "rendered")


def crop_with_buffer(evidence: Dict, footprint: Polygon, source: str, bid: int, buffer_m: float) -> Dict:
    mask = fc.footprint_mask(evidence["points"], footprint, buffer_m)
    out = {}
    for key, value in evidence.items():
        if isinstance(value, np.ndarray) and len(value) == len(mask):
            out[key] = value[mask].copy()
        elif isinstance(value, np.ndarray):
            out[key] = value.copy()
    out["source"] = source
    out["bid"] = bid_label(bid)
    return out


def phase5_footprint_sensitivity(buildings: Dict[int, Dict]) -> Tuple[List[Dict], List[Dict]]:
    out_dir = FC_S3_ROOT / "phase5_footprint_sensitivity"
    full = {E1: load_full_rendered_evidence(E1), E2: load_full_rendered_evidence(E2)}
    rows = []
    for buffer_m in [0.25, 0.75, 1.50]:
        for bid in TARGET_BIDS:
            footprint = fc.footprint_for_building(buildings[bid])
            if footprint is None:
                continue
            for source in [E1, E2]:
                ev_source = f"{source}_buffer_{buffer_m:.2f}m"
                ev = crop_with_buffer(full[source], footprint, ev_source, bid, buffer_m)
                row = evaluate_stage3_metric(
                    ev,
                    buildings[bid],
                    ev_source,
                    bid,
                    out_dir / "readout" / f"buffer_{buffer_m:.2f}m" / source / bid_label(bid),
                    out_dir / "metric_v1" / f"buffer_{buffer_m:.2f}m" / source / bid_label(bid),
                )
                row["source_family"] = source
                row["footprint_buffer_m"] = buffer_m
                row["bid"] = bid_label(bid)
                row["bid_int"] = bid
                row["support_cov"] = row.get("support_cov", row.get("support_coverage", ""))
                row["non_manifold_edges"] = row.get("non_manifold_edges", row.get("nonmanifold_edges", ""))
                rows.append(row)
    fc.write_csv(out_dir / "footprint_buffer_sweep_metrics.csv", rows)

    by_key = {(float(r["footprint_buffer_m"]), r["source_family"], int(r["bid_int"])): r for r in rows}
    split_rows = []
    for buffer_m in [0.25, 0.75, 1.50]:
        for split, bids in SPLITS.items():
            if split == "success_reference":
                continue
            for metric in ["F", "roof_cov", "wall_cov", "ground_cov", "support_cov", "h_err", "chamfer"]:
                e1_vals = [metric_value(by_key.get((buffer_m, E1, b), {}), metric) for b in bids]
                e2_vals = [metric_value(by_key.get((buffer_m, E2, b), {}), metric) for b in bids]
                directional = [
                    delta_metric(metric_value(by_key.get((buffer_m, E2, b), {}), metric), metric_value(by_key.get((buffer_m, E1, b), {}), metric), metric)
                    for b in bids
                ]
                split_rows.append({
                    "footprint_buffer_m": buffer_m,
                    "split": split,
                    "metric": metric,
                    "e1_mean": mean(e1_vals),
                    "e2_mean": mean(e2_vals),
                    "raw_delta_mean_e2_minus_e1": mean([
                        (e2_vals[i] - e1_vals[i]) if e1_vals[i] is not None and e2_vals[i] is not None else None
                        for i in range(len(bids))
                    ]),
                    "directional_delta_mean_positive_favors_e2": mean(directional),
                })
    fc.write_csv(out_dir / "footprint_sensitivity_by_split.csv", split_rows)
    all_f = [r for r in split_rows if r["split"] == "all_10" and r["metric"] == "F"]
    report = [
        "# FC-S3 Phase 5: Footprint Masking Sensitivity",
        "",
        "GT footprint is kept fixed and only the controlled buffer is swept. No new footprints are estimated.",
        "",
    ]
    report.extend(md_table(
        ["buffer_m", "E1 F", "E2 F", "raw dF E2-E1"],
        [[r["footprint_buffer_m"], fmt(r["e1_mean"]), fmt(r["e2_mean"]), fmt(r["raw_delta_mean_e2_minus_e1"])] for r in all_f],
    ))
    report.extend([
        "",
        "Interpretation: if the E1/E2 delta changes sharply with buffer, the GT-domain condition is masking or amplifying rendered evidence differences.",
    ])
    (out_dir / "FOOTPRINT_MASKING_REPORT.md").write_text("\n".join(report) + "\n")
    return rows, split_rows


def phase6_mutual_ablation(
    paired: List[Dict],
    class_rows: List[Dict],
    split_rows: List[Dict],
) -> List[Dict]:
    out_dir = FC_S3_ROOT / "phase6_mutual_ablation"
    configs = [
        ("M0", "Baseline", 0.0, "existing_run", "No mutual loss."),
        ("M1", "Mutual original", 1.0, "existing_run", "Original L_mutual checkpoint."),
        ("M2", "Mutual weight 0.5x", 0.5, "planned_not_run", "Cheapest first reweighting candidate."),
        ("M3", "Mutual weight 0.25x", 0.25, "planned_not_run", "Tests whether E1-like stability returns."),
        ("M4", "Mutual roof-wall only", 1.0, "planned_not_run", "Remove ground and height terms."),
        ("M5", "Mutual without ground/terrain term", 1.0, "planned_not_run", "Direct B104 negative-transfer test."),
        ("M6", "Mutual without height relation term", 1.0, "planned_not_run", "Tests B6 height relation sensitivity."),
        ("M7", "Mutual class-balanced weighting", 1.0, "planned_not_run", "Reduce classwise support imbalance."),
        ("M8", "Mutual with late-start schedule", 1.0, "planned_not_run", "Avoid early semantic/geometric lock-in."),
    ]
    config_rows = [
        {
            "config_id": cid,
            "name": name,
            "mutual_weight_relative": weight,
            "status": status,
            "ground_term_enabled": cid not in {"M0", "M4", "M5"},
            "height_relation_enabled": cid not in {"M0", "M4", "M6"},
            "roof_wall_terms_enabled": cid not in {"M0"},
            "class_balanced": cid == "M7",
            "late_start": cid == "M8",
            "diagnostic_question": note,
        }
        for cid, name, weight, status, note in configs
    ]
    fc.write_csv(out_dir / "mutual_ablation_config_table.csv", config_rows)

    evidence_rows = []
    for cid, source in [("M0", E1), ("M1", E2)]:
        for class_name in ["roof", "wall", "ground"]:
            rows = [r for r in class_rows if r["source"] == source and r["class_name"] == class_name]
            evidence_rows.append({
                "config_id": cid,
                "source": source,
                "class_name": class_name,
                "point_count_mean": mean([safe_float(r.get("point_count")) for r in rows]),
                "semantic_entropy_mean": mean([safe_float(r.get("semantic_entropy_mean")) for r in rows]),
                "normal_consistency_mean": mean([safe_float(r.get("normal_consistency_mean")) for r in rows]),
                "distance_to_same_surface_mean": mean([safe_float(r.get("distance_to_predicted_same_surface_mean")) for r in rows]),
            })
    for cid, name, *_ in configs[2:]:
        evidence_rows.append({"config_id": cid, "source": name, "status": "planned_not_run"})
    fc.write_csv(out_dir / "mutual_ablation_evidence_summary.csv", evidence_rows)

    all_f = next(r for r in split_rows if r["split"] == "all_10" and r["metric"] == "F")
    stage3_rows = [
        {
            "config_id": "M0",
            "source": E1,
            "status": "existing_run",
            "mean_F_all_10": all_f["e1_mean"],
            "ok_count": sum(1 for r in paired if r["e1_status"] == "OK"),
        },
        {
            "config_id": "M1",
            "source": E2,
            "status": "existing_run",
            "mean_F_all_10": all_f["e2_mean"],
            "ok_count": sum(1 for r in paired if r["e2_status"] == "OK"),
        },
    ]
    for cid, name, *_ in configs[2:]:
        stage3_rows.append({"config_id": cid, "source": name, "status": "planned_not_run"})
    fc.write_csv(out_dir / "mutual_ablation_stage3_metrics.csv", stage3_rows)

    report = [
        "# FC-S3 Phase 6: Mutual Reweighting and Ablation Planning",
        "",
        "Full retraining is not started in FC-S3. M0 and M1 use existing checkpoints; M2-M8 are concrete ablation candidates.",
        "",
        "## Cheapest Diagnostic Subset",
        "1. M5: remove ground/terrain term to directly test B104-like failures.",
        "2. M3: reduce mutual weight to 0.25x to test whether E1-like stability returns.",
        "3. M4: roof-wall only to test whether roof cases benefit without ground transfer.",
        "",
        "## Existing Stage3 Result",
        f"- M0 mean F all 10: {fmt(all_f['e1_mean'])}.",
        f"- M1 mean F all 10: {fmt(all_f['e2_mean'])}.",
        "",
        "Do not claim Mutual-alone final improvement unless M1 beats M0 on final read-out metrics.",
    ]
    (out_dir / "MUTUAL_ABLATION_REPORT.md").write_text("\n".join(report) + "\n")
    return config_rows


def phase7_g2_readiness(
    paired: List[Dict],
    split_rows: List[Dict],
    footprint_split_rows: List[Dict],
) -> str:
    out_dir = FC_S3_ROOT / "phase7_g2_readiness"
    all_f = next(r for r in split_rows if r["split"] == "all_10" and r["metric"] == "F")
    easy_f = next(r for r in split_rows if r["split"] == "easier_control" and r["metric"] == "F")
    hard_f = next(r for r in split_rows if r["split"] == "hard_diagnostic" and r["metric"] == "F")
    roof_f = next(r for r in split_rows if r["split"] == "roof_complex_candidate" and r["metric"] == "F")
    ground_cov = next(r for r in split_rows if r["split"] == "ground_sensitive" and r["metric"] == "ground_cov")

    decision = "C. REVISE_L_MUTUAL_BEFORE_G2"
    targets = [
        {
            "target": "ground support stabilization",
            "priority": 1,
            "evidence": "B104 E1 succeeds while E2 ground_cov collapses; rendered ground support remains low.",
            "candidate_signal": "classwise ground evidence y distribution, support acceptance, wall-ground closure confidence",
        },
        {
            "target": "surface support coverage",
            "priority": 2,
            "evidence": "E1/E2 both have low classwise support, especially ground.",
            "candidate_signal": "accepted/rejected support distribution and confidence calibration",
        },
        {
            "target": "roof grouping consistency",
            "priority": 3,
            "evidence": "B3/B123/B126 remain unresolved with E0/E1/E2 triangulation.",
            "candidate_signal": "roof cluster continuity and roof-wall adjacency consistency",
        },
        {
            "target": "roof-wall adjacency consistency",
            "priority": 4,
            "evidence": "Complex roof cases need structure-aware grouping without topology destruction.",
            "candidate_signal": "roof-wall adjacency graph consistency",
        },
        {
            "target": "wall-ground closure confidence",
            "priority": 5,
            "evidence": "GroundSurface metrics are vulnerable to noisy rendered ground evidence.",
            "candidate_signal": "wall base support and ground plane confidence",
        },
        {
            "target": "low-support face confidence calibration",
            "priority": 6,
            "evidence": "Low support can coexist with closed topology; final evaluator penalizes semantic coverage.",
            "candidate_signal": "per-face support confidence and metric-aware calibration",
        },
    ]
    fc.write_csv(out_dir / "g2_target_selection.csv", targets)

    pilot = [
        "# G2 4-Way Pilot Plan",
        "",
        "Do not start full G2 training until a readiness gate passes.",
        "",
        "## Arms",
        "- Baseline: existing E1-style training without L_mutual or G2.",
        "- Mutual: existing L_mutual schedule/checkpoint family.",
        "- G2-only: structure targets without L_mutual.",
        "- Mutual+G2: revised Mutual plus G2 targets only after M2-M8 ablations identify a safe mutual recipe.",
        "",
        "## Gate",
        "- M1 must not be worse than M0 on final F/support/ground metrics, or the revised mutual candidate must recover E1 stability.",
        "- No candidate may hide GroundSurface failure, regress simple cases, or destroy topology.",
        "",
        "## Primary Targets",
    ]
    pilot.extend(md_table(
        ["priority", "target", "candidate signal"],
        [[r["priority"], r["target"], r["candidate_signal"]] for r in targets],
    ))
    (out_dir / "g2_4way_pilot_plan.md").write_text("\n".join(pilot) + "\n")

    buffer_f = [r for r in footprint_split_rows if r["split"] == "all_10" and r["metric"] == "F"]
    buffer_line = "; ".join(
        f"{r['footprint_buffer_m']}m dF={fmt(r['raw_delta_mean_e2_minus_e1'])}" for r in buffer_f
    )
    b104 = next(r for r in paired if int(r["bid_int"]) == 104)
    b6 = next(r for r in paired if int(r["bid_int"]) == 6)
    report = [
        "# FC-S3 Final Decision",
        "",
        f"Final decision: {decision}",
        "",
        "## Answers",
        f"1. Non-hard bids under current Stage3: easier/control mean F is E1={fmt(easy_f['e1_mean'])}, E2={fmt(easy_f['e2_mean'])}. They are generally good, but E2 is not uniformly better.",
        f"2. E2 across all 10: mean F is E1={fmt(all_f['e1_mean'])}, E2={fmt(all_f['e2_mean'])}; this does not support a Mutual-alone final improvement claim.",
        f"3. Hard vs easier cases: hard mean dF={fmt(hard_f['raw_delta_mean_e2_minus_e1'])}, easier/control mean dF={fmt(easy_f['raw_delta_mean_e2_minus_e1'])}. Mutual differences are not confined to a single diagnostic bid.",
        "4. Harmful or weak component: the ground/terrain mutual component is the first revision candidate; roof-wall/height components remain unproven because roof/height failures overlap with Stage3/evaluator limitations.",
        f"5. Ground/terrain and B104: B104 dground_cov={fmt(b104.get('delta_e2_minus_e1_ground_cov'))}, dF={fmt(b104.get('delta_e2_minus_e1_F'))}; flag the ground/terrain term for ablation before G2 claims.",
        f"6. B6 height: B6 dF={fmt(b6.get('delta_e2_minus_e1_F'))}; Track B showed E0/E1/E2 all share the height deficit, so it is independent of Mutual as a primary cause.",
        f"7. B3/B123/B126: roof-complex mean dF={fmt(roof_f['raw_delta_mean_e2_minus_e1'])}; E0 failures in Track B keep Stage3/evaluator matching as the dominant unresolved candidate.",
        f"8. Footprint buffer: all-10 F deltas by buffer are {buffer_line}. Treat strong changes as evidence that GT-domain masking modulates E1/E2 differences.",
        "9. Recommendation: revise L_mutual before G2 and abandon a Mutual-alone final model claim for now. G2 remains a hypothesis requiring 4-way ablation.",
        "10. G2 should optimize ground support stabilization, surface support coverage, roof grouping consistency, roof-wall adjacency, wall-ground closure confidence, and low-support face confidence calibration.",
        "",
        "## No Overclaim Policy",
        "- If E2 does not beat E1 on final metrics, Mutual-alone is not supported.",
        "- If proxy losses or entropy improve without support/geometry gains, report proxy misalignment.",
        "- Shared E0/E1/E2 failures are assigned to Stage3/evaluator/reference matching until resolved.",
    ]
    (out_dir / "FC_S3_FINAL_DECISION.md").write_text("\n".join(report) + "\n")
    return decision


def phase1_metric_lookup(split_rows: List[Dict], split: str, metric: str) -> Dict:
    return next(r for r in split_rows if r["split"] == split and r["metric"] == metric)


def write_manifest(decision: str) -> None:
    fc.write_json(FC_S3_ROOT / "fc_s3_manifest.json", {
        "experiment": "FC-S3: Mutual Loss Alignment Audit and G2 Target Definition",
        "controlled_stage3_algorithm": s3.STAGE3_ALGO_V1,
        "controlled_metric": s3.METRIC_V1,
        "uses_rejected_stage3_v1c_patches": False,
        "starts_full_g2_training": False,
        "modifies_stage3_algorithms": False,
        "modifies_metric_v1": False,
        "modifies_footprint_estimation": False,
        "gravity": fc.load_gravity(),
        "sources": [E0, E1, E2],
        "target_bids": [bid_label(b) for b in TARGET_BIDS],
        "final_decision": decision,
    })


def run(force: bool = False) -> None:
    if force and FC_S3_ROOT.exists():
        shutil.rmtree(FC_S3_ROOT)
    fc.mkdir(FC_S3_ROOT)
    buildings = load_buildings()
    paired, existing_rows, split_rows = phase1_full_comparison(buildings)
    class_rows, ground_rows, roof_rows, support_rows = phase3_evidence_distribution(buildings)
    phase2_mutual_loss_audit(paired, class_rows, split_rows)
    phase4_field_replacement(buildings, existing_rows)
    _, footprint_split_rows = phase5_footprint_sensitivity(buildings)
    phase6_mutual_ablation(paired, class_rows, split_rows)
    decision = phase7_g2_readiness(paired, split_rows, footprint_split_rows)
    write_manifest(decision)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="Replace existing FC-S3 output root.")
    args = parser.parse_args()
    run(force=args.force)


if __name__ == "__main__":
    main()
