"""FC-S5 rendered-evidence Stage3Algo-v1 + Metric-v1 evaluation.

This adapter keeps Stage3 and Metric-v1 code unchanged.  It exports rendered
Stage2 evidence from a completed FC-S5 diagnostic checkpoint using the same
E1/E2 rendered-evidence convention, then runs the existing Stage3Algo-v1
read-out and Metric-v1 audit helpers over the controlled FC-S5 building set.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import torch
import yaml
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import scripts.phase2_synthesis.fc_s1_semantic_surface_readout as fc  # noqa: E402
import scripts.phase2_synthesis.stage3_v1_auditable_readout_comparison as s3  # noqa: E402
import scripts.phase2_synthesis.s1_rendered_e2style_gate as s1  # noqa: E402
import scripts.phase2_synthesis.s1d_fix_export_and_rerun as s1d  # noqa: E402
import scripts.phase2_synthesis.p1_4a_preflight_precision as pm  # noqa: E402
from scripts.phase2_synthesis.obj_gt import parse_scene_obj  # noqa: E402


TARGET_BIDS_INT = [0, 1, 2, 8, 6, 3, 123, 126, 50, 104]
TARGET_BIDS = [f"B{x}" for x in TARGET_BIDS_INT]
EASY_CONTROL_BIDS = ["B0", "B1", "B2", "B8", "B50"]
HARD_DIAGNOSTIC_BIDS = ["B6", "B3", "B123", "B126", "B104"]
GUARD_BIDS = ["B104", "B6", "B3", "B123", "B126", "B2", "B0", "B1"]
RUN_CONFIGS = {
    "M3": ROOT / "configs/fc_s5/M3_reduced_mutual.yaml",
    "M5": ROOT / "configs/fc_s5/M5_terrain_off.yaml",
    "M10": ROOT / "configs/fc_s5/M10_ramped_mutual.yaml",
}
OUT_ROOT = ROOT / "results/FC_S5_loss_ledger_instrumentation"
DIAG_ROOT = OUT_ROOT / "phase2_diagnostics"
BASELINE_CSV = (
    ROOT
    / "results/footprint_conditioned_readout"
    / "FC_S3_mutual_loss_alignment_g2_target_definition"
    / "phase1_full_e1_e2_comparison/e1_e2_paired_metrics_by_bid.csv"
)

METRIC_FIELDS = [
    "run",
    "bid",
    "job_status",
    "config_path",
    "status",
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
    "failure_reason",
]


def rel(path: Optional[Path]) -> str:
    if path is None:
        return ""
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def write_json(path: Path, payload: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=jsonable) + "\n")


def jsonable(obj):
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, np.generic):
        return obj.item()
    if isinstance(obj, Path):
        return rel(obj)
    return str(obj)


def read_csv(path: Path) -> List[Dict]:
    if not path.exists():
        return []
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: List[Dict], fields: Optional[List[str]] = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fields is None:
        fields = []
        seen = set()
        for row in rows:
            for key in row:
                if key not in seen:
                    seen.add(key)
                    fields.append(key)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fields})


def safe_float(value: object) -> Optional[float]:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(x) or math.isinf(x) else x


def mean_field(rows: List[Dict], field: str) -> Optional[float]:
    vals = [safe_float(r.get(field)) for r in rows]
    vals = [v for v in vals if v is not None]
    return float(np.mean(vals)) if vals else None


def status_for_run_csv(out_csv: Path) -> str:
    rows = read_csv(out_csv)
    if not rows:
        return "PENDING"
    statuses = {r.get("status", "") for r in rows}
    if statuses == {"OK"}:
        return "OK"
    if "PENDING" in statuses:
        return "PENDING"
    return "INCOMPLETE"


def write_pending(out_csv: Path, run_name: str, config_path: Path, reason: str) -> None:
    rows = []
    for bid in TARGET_BIDS:
        row = {field: "" for field in METRIC_FIELDS}
        row.update({
            "run": run_name,
            "bid": bid,
            "job_status": "PENDING",
            "config_path": rel(config_path),
            "status": "PENDING",
            "failure_reason": reason,
        })
        rows.append(row)
    write_csv(out_csv, rows, METRIC_FIELDS)
    update_diagnostic_summaries()


def render_sample_bank(
    config_path: Path,
    checkpoint: Path,
    evidence_root: Path,
    args: argparse.Namespace,
) -> Dict[str, np.ndarray]:
    root = evidence_root / "phase1_render_export"
    bank_path = root / "rendered_sample_bank.npz"
    if bank_path.exists() and not args.force_render_export:
        data = np.load(bank_path, allow_pickle=False)
        return {k: data[k] for k in data.files}

    root.mkdir(parents=True, exist_ok=True)
    device = "cuda" if torch.cuda.is_available() and args.device == "cuda" else "cpu"
    model, ds, cfg = s1.load_model_and_dataset(config_path, checkpoint, args.render_downscale, device)
    idxs = s1d.selected_view_indices(ds, args.max_views)
    all_rows = []
    view_rows = []
    for local_id, idx in enumerate(idxs):
        b = ds[idx]
        H, W = int(b["height"]), int(b["width"])
        with torch.no_grad():
            out = s1.render(
                model,
                b["w2c"].to(device),
                b["K"].to(device),
                W,
                H,
                sh_degree=model.max_sh_degree,
                render_mode="RGB+ED",
            )
            sem_logits = s1.render_semantic(model, b["w2c"].to(device), b["K"].to(device), W, H)
            sem_prob = torch.softmax(sem_logits, dim=-1)
        depth_expected = out["depth"].detach().cpu().numpy().astype(np.float32)
        depth_median = out["depth_median"].detach().cpu().numpy().astype(np.float32)
        alpha = out["alpha"].detach().cpu().numpy().astype(np.float32)
        normal = out["normal_render"].detach().cpu().numpy().astype(np.float32)
        prob = sem_prob.detach().cpu().numpy().astype(np.float32)
        ys = np.arange(0, H, args.pixel_stride, dtype=np.int32)
        xs = np.arange(0, W, args.pixel_stride, dtype=np.int32)
        vv, uu = np.meshgrid(ys, xs, indexing="ij")
        de = depth_expected[vv, uu]
        dm = depth_median[vv, uu]
        a = alpha[vv, uu]
        p = prob[vv, uu]
        sem_conf = p.max(axis=-1)
        labels = p.argmax(axis=-1).astype(np.int64)
        n = normal[vv, uu]
        n_norm = np.linalg.norm(n, axis=-1)
        valid = (
            np.isfinite(de)
            & np.isfinite(dm)
            & ((de > 0.0) | (dm > 0.0))
            & (a > s1.ALPHA_MIN)
            & (sem_conf > s1.SEM_CONF_MIN)
            & (n_norm > 1e-5)
        )
        if np.any(valid):
            normals = s1d.normalize_rows(n[valid].reshape(-1, 3).astype(np.float64)).astype(np.float32)
            all_rows.append({
                "depth_expected": de[valid].reshape(-1).astype(np.float32),
                "depth_median": dm[valid].reshape(-1).astype(np.float32),
                "normal": normals,
                "sem_prob": p[valid].reshape(-1, 4).astype(np.float32),
                "label": labels[valid].reshape(-1).astype(np.int64),
                "alpha": a[valid].reshape(-1).astype(np.float32),
                "confidence": (a[valid].reshape(-1) * sem_conf[valid].reshape(-1)).astype(np.float32),
                "view_id": np.full(int(np.sum(valid)), idx, dtype=np.int32),
                "pixel_u": uu[valid].reshape(-1).astype(np.int32),
                "pixel_v": vv[valid].reshape(-1).astype(np.int32),
            })
        view_rows.append({
            "view_id": idx,
            "local_view_id": local_id,
            "image_name": b["name"],
            "height": H,
            "width": W,
            "n_pixels_sampled": int(uu.size),
            "n_valid_samples": int(np.sum(valid)),
            "mean_alpha": float(np.mean(a[valid])) if np.any(valid) else 0.0,
            "mean_sem_conf": float(np.mean(sem_conf[valid])) if np.any(valid) else 0.0,
        })
        print(f"[fc-s5-render] view {local_id + 1}/{len(idxs)} idx={idx} valid={int(np.sum(valid))}", flush=True)

    if not all_rows:
        raise RuntimeError("No valid rendered samples were produced")
    raw = {k: np.concatenate([r[k] for r in all_rows], axis=0) for k in all_rows[0]}
    if len(raw["label"]) > args.max_raw_samples:
        keep = s1.downsample_balanced(raw["label"], args.max_raw_samples, args.seed)
        raw = {k: v[keep] for k, v in raw.items()}
    np.savez_compressed(bank_path, **raw)
    write_csv(root / "rendered_sample_bank_views.csv", view_rows)
    write_json(root / "rendered_sample_bank_metadata.json", {
        "checkpoint": rel(checkpoint),
        "config": rel(config_path),
        "n_views": len(idxs),
        "selected_views": idxs,
        "n_samples": int(len(raw["label"])),
        "render_downscale": args.render_downscale,
        "pixel_stride": args.pixel_stride,
        "depth_outputs": ["expected_z_depth", "median_z_depth"],
        "config_data_root": cfg.get("resolved_data_root"),
        "gravity": [0, 1, 0],
        "gt_used_for_generation": False,
    })
    return raw


def fixed_raw_from_expected_z(raw: Dict[str, np.ndarray], config_path: Path, args: argparse.Namespace) -> Dict:
    cfg = yaml.safe_load(config_path.read_text())
    data_root = Path(cfg["data_root"])
    if not data_root.is_absolute():
        data_root = ROOT / data_root
    if not data_root.exists():
        data_root = ROOT / "results/phase2_synthesis/dataset"
    ds = s1.ColmapDataset(
        root=data_root,
        downscale=float(cfg.get("downscale", 1.0)) * args.render_downscale,
        load_depth=False,
        load_normal=False,
        load_semantic=False,
    )
    idx = np.arange(len(raw["label"]), dtype=np.int64)
    candidate = {
        "depth_mode": "expected_z",
        "camera_mode": "camera_to_world_inverse_extrinsic",
        "axis_mode": "existing_axes",
    }
    pts = s1d.unproject_variant_for_indices(raw, ds, idx, **candidate)
    return {
        "xyz": pts.astype(np.float32),
        "normal": raw["normal"].astype(np.float32),
        "sem_prob": raw["sem_prob"].astype(np.float32),
        "label": raw["label"].astype(np.int64),
        "alpha": raw["alpha"].astype(np.float32),
        "confidence": raw["confidence"].astype(np.float32),
        "view_id": raw["view_id"].astype(np.int32),
        "pixel_u": raw["pixel_u"].astype(np.int32),
        "pixel_v": raw["pixel_v"].astype(np.int32),
        "depth": raw["depth_expected"].astype(np.float32),
    }


def fuse_fixed_evidence(raw_fixed: Dict[str, np.ndarray], evidence_root: Path, args: argparse.Namespace) -> Dict:
    root = evidence_root / "phase3_fixed_quality"
    root.mkdir(parents=True, exist_ok=True)
    out_npz = root / "rendered_evidence_fixed_F2_class_normal_aware_voxel_0p05.npz"
    if out_npz.exists() and not args.force_render_export:
        data = np.load(out_npz, allow_pickle=False)
        return {k: data[k] for k in data.files}

    labels = raw_fixed["label"].astype(np.int64)
    vox = np.floor(raw_fixed["xyz"].astype(np.float64) / 0.05).astype(np.int32)
    keys = np.concatenate([vox, labels[:, None].astype(np.int32), s1.normal_bins(raw_fixed["normal"])], axis=1)
    raw_for_fuse = {
        "xyz": raw_fixed["xyz"],
        "normal": raw_fixed["normal"],
        "sem_prob": raw_fixed["sem_prob"],
        "label": raw_fixed["label"],
        "confidence": raw_fixed["confidence"],
        "view_id": raw_fixed["view_id"],
    }
    ev = s1.fuse_groups(raw_for_fuse, keys, "F2_class_normal_aware_voxel_0p05")
    np.savez_compressed(out_npz, **ev)
    np.savez_compressed(root / "rendered_evidence_fixed.npz", **ev)
    s1.write_binary_ply(root / "rendered_evidence_fixed_F2_class_normal_aware_voxel_0p05.ply", ev, extra={
        "view_count": ev.get("view_count", np.ones(len(ev["classes"]), dtype=np.int32)),
        "confidence": ev.get("confidence", ev["weights"]),
        "normal_consistency": ev.get("normal_consistency", np.ones(len(ev["classes"]), dtype=np.float32)),
        "semantic_entropy": ev.get("semantic_entropy", np.zeros(len(ev["classes"]), dtype=np.float32)),
    }, max_points=args.max_ply_points, seed=args.seed)
    write_json(root / "scene_evidence_graph_fixed_F2_class_normal_aware_voxel_0p05.json", {
        "gravity": [0, 1, 0],
        "evidence_type": "stage2_rendered_surface_evidence_fixed",
        "points_file": "rendered_evidence_fixed_F2_class_normal_aware_voxel_0p05.npz",
        "fusion": "F2_class_normal_aware_voxel_0p05",
        "voxel_size_m": 0.05,
        "class_normal_aware": True,
        "gt_used_for_generation": False,
    })
    return ev


def export_rendered_evidence(config_path: Path, checkpoint: Path, evidence_root: Path, args: argparse.Namespace) -> Path:
    evidence_root.mkdir(parents=True, exist_ok=True)
    final_npz = evidence_root / "phase3_fixed_quality/rendered_evidence_fixed.npz"
    if final_npz.exists() and not args.force_render_export:
        return final_npz
    raw = render_sample_bank(config_path, checkpoint, evidence_root, args)
    fixed_root = evidence_root / "phase2_fixed_export"
    fixed_root.mkdir(parents=True, exist_ok=True)
    fixed = fixed_raw_from_expected_z(raw, config_path, args)
    np.savez_compressed(fixed_root / "raw_rendered_samples_fixed.npz", **fixed)
    write_json(fixed_root / "fixed_export_metadata.json", {
        "checkpoint": rel(checkpoint),
        "config": rel(config_path),
        "depth_convention": "expected_z",
        "camera_convention": "camera_to_world_inverse_extrinsic",
        "axis_convention": "existing_axes",
        "normal_frame": "gsplat_render_normals_world_frame_N0_exported",
        "scene_normalization_inverse_applied": False,
        "gravity": [0, 1, 0],
        "gt_used_for_generation": False,
    })
    fuse_fixed_evidence(fixed, evidence_root, args)
    return final_npz


def support_by_surface(faces: List[Dict], evidence: Optional[Dict], seed: int) -> Dict:
    out = {
        "roof_support_cov": "",
        "wall_support_cov": "",
        "ground_support_cov": "",
    }
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


def load_rendered_evidence(evidence_npz: Path) -> Dict:
    raw = fc.load_npz(evidence_npz)
    return fc.normalize_evidence(raw, evidence_npz.stem, "rendered")


def metric_row_from_v1(
    run_name: str,
    config_path: Path,
    bid: int,
    status: Dict,
    metric: Dict,
    faces: List[Dict],
    evidence: Optional[Dict],
) -> Dict:
    row = {field: "" for field in METRIC_FIELDS}
    row.update({
        "run": run_name,
        "bid": f"B{bid}",
        "job_status": "COMPLETED",
        "config_path": rel(config_path),
        "status": status.get("status", ""),
        "failure_reason": status.get("failure_reason", metric.get("failure_reason", "")),
    })
    mapping = {
        "support_cov": "support_coverage",
        "non_manifold_edges": "nonmanifold_edges",
    }
    for field in METRIC_FIELDS:
        if field in row and row[field] != "":
            continue
        source_field = mapping.get(field, field)
        if source_field in metric:
            row[field] = metric.get(source_field, "")
    row.update(support_by_surface(faces, evidence, seed=9400 + bid))
    return row


def evaluate_run(
    run_name: str,
    config_path: Path,
    checkpoint: Path,
    evidence_root: Path,
    out_csv: Path,
    args: argparse.Namespace,
) -> List[Dict]:
    evidence_npz = export_rendered_evidence(config_path, checkpoint, evidence_root, args)
    evidence = load_rendered_evidence(evidence_npz)
    buildings = parse_scene_obj(fc.SCENE, frame="obj")["buildings"]
    by_bid = {int(b["building_id"]): b for b in buildings}
    rows = []
    for bid in TARGET_BIDS_INT:
        building = by_bid[bid]
        footprint = fc.footprint_for_building(building)
        local_ev = fc.crop_evidence(evidence, footprint, run_name, bid)
        readout_dir = evidence_root / "stage3_readout" / run_name / f"B{bid}"
        metric_dir = evidence_root / "metric_v1" / run_name / f"B{bid}"
        try:
            status, faces, _city_diag, _patch_log = s3.stage3_v1_readout(
                local_ev,
                building,
                footprint,
                run_name,
                bid,
                readout_dir,
            )
            metric = s3.metric_v1_evaluate(
                faces,
                building,
                local_ev,
                run_name,
                bid,
                s3.STAGE3_ALGO_V1,
                status.get("status", ""),
                status.get("failure_reason", ""),
                metric_dir,
                readout_dir,
            )
            rows.append(metric_row_from_v1(run_name, config_path, bid, status, metric, faces, local_ev))
        except Exception as exc:  # noqa: BLE001
            rows.append({
                "run": run_name,
                "bid": f"B{bid}",
                "job_status": "COMPLETED",
                "config_path": rel(config_path),
                "status": "EVAL_EXCEPTION",
                "failure_reason": f"{type(exc).__name__}: {exc}",
            })
    write_csv(out_csv, rows, METRIC_FIELDS)
    update_diagnostic_summaries()
    return rows


def baseline_by_bid() -> Dict[str, Dict]:
    return {r["bid"]: r for r in read_csv(BASELINE_CSV)}


def split_rows(rows: List[Dict], bids: List[str]) -> List[Dict]:
    wanted = set(bids)
    return [r for r in rows if r.get("bid") in wanted]


def topology_regression(rows: List[Dict], baseline: Dict[str, Dict], field: str) -> str:
    regressions = []
    base_field = f"e1_{field}"
    for row in rows:
        bid = row.get("bid", "")
        value = safe_float(row.get(field))
        base = safe_float(baseline.get(bid, {}).get(base_field))
        if value is not None and base is not None and value > base:
            regressions.append(bid)
    return ";".join(regressions)


def update_diagnostic_summaries() -> None:
    baseline = baseline_by_bid()
    summary_rows = []
    split_defs = {
        "all_10": TARGET_BIDS,
        "easy_control": EASY_CONTROL_BIDS,
        "hard_diagnostic": HARD_DIAGNOSTIC_BIDS,
        "guard_bids": GUARD_BIDS,
    }
    for run in ["M3", "M5", "M10"]:
        rows = read_csv(DIAG_ROOT / f"{run}_metrics_by_bid.csv")
        for split_name, bids in split_defs.items():
            part = split_rows(rows, bids)
            ok = [r for r in part if r.get("status") == "OK"]
            if len(ok) == len(bids):
                status = "OK"
                note = "completed Stage3Algo-v1 + Metric-v1 rows"
            elif any(r.get("status") == "PENDING" for r in part) or not part:
                status = "PENDING_NO_COMPLETED_RUN"
                note = "pending completed Stage3 metrics"
            else:
                status = "INCOMPLETE_OR_FAILED"
                note = "one or more rows failed or are incomplete"
            summary_rows.append({
                "run": run,
                "split": split_name,
                "n_bids": len(bids),
                "mean_F": mean_field(ok, "F"),
                "mean_ground_cov": mean_field(ok, "ground_cov"),
                "mean_ground_support_cov": mean_field(ok, "ground_support_cov"),
                "open_edges_regression": topology_regression(ok, baseline, "open_edges"),
                "non_manifold_regression": topology_regression(ok, baseline, "non_manifold_edges"),
                "status": status,
                "note": note,
            })
    write_csv(DIAG_ROOT / "diagnostic_split_summary.csv", summary_rows)

    b104_rows = []
    for run in ["M3", "M5", "M10"]:
        rows = read_csv(DIAG_ROOT / f"{run}_metrics_by_bid.csv")
        b104 = next((r for r in rows if r.get("bid") == "B104"), None)
        if not b104 or b104.get("status") != "OK":
            b104_rows.append({
                "run": run,
                "job_status": "PENDING_NO_COMPLETED_RUN",
                "B104_ground_cov": "",
                "B104_ground_support_cov": "",
                "B104_h_err": "",
                "terrain_drift_status": "PENDING",
                "note": "B104 terrain drift requires completed rendered evidence and Stage3 read-out metrics.",
            })
            continue
        ground = safe_float(b104.get("ground_cov"))
        e1_ground = safe_float(baseline.get("B104", {}).get("e1_ground_cov"))
        e2_ground = safe_float(baseline.get("B104", {}).get("e2_ground_cov"))
        if ground is not None and e1_ground is not None and ground >= e1_ground - 1e-6:
            terrain_status = "RECOVERED_TO_E1"
        elif ground is not None and e2_ground is not None and ground > e2_ground:
            terrain_status = "IMPROVED_OVER_E2"
        else:
            terrain_status = "NOT_RECOVERED"
        b104_rows.append({
            "run": run,
            "job_status": "COMPLETED",
            "B104_ground_cov": b104.get("ground_cov", ""),
            "B104_ground_support_cov": b104.get("ground_support_cov", ""),
            "B104_h_err": b104.get("h_err", ""),
            "terrain_drift_status": terrain_status,
            "note": "Compared against FC-S3 E1/E2 B104 ground_cov baselines.",
        })
    write_csv(DIAG_ROOT / "B104_terrain_drift_summary.csv", b104_rows)


def resolve_config(run_name: str, config_arg: Optional[str]) -> Path:
    if config_arg:
        return (ROOT / config_arg).resolve() if not Path(config_arg).is_absolute() else Path(config_arg)
    if run_name in RUN_CONFIGS:
        return RUN_CONFIGS[run_name]
    raise SystemExit(f"[fc-s5-eval] --config required for unknown run name {run_name!r}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-name", required=True)
    ap.add_argument("--config")
    ap.add_argument("--checkpoint", required=True)
    ap.add_argument("--rendered-evidence-root", required=True)
    ap.add_argument("--out-csv", required=True)
    ap.add_argument("--max-views", type=int, default=56)
    ap.add_argument("--render-downscale", type=float, default=0.25)
    ap.add_argument("--pixel-stride", type=int, default=2)
    ap.add_argument("--max-raw-samples", type=int, default=3_000_000)
    ap.add_argument("--max-ply-points", type=int, default=750_000)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--device", choices=["cuda", "cpu"], default="cuda")
    ap.add_argument("--force-render-export", action="store_true")
    args = ap.parse_args()

    run_name = args.run_name
    config_path = resolve_config(run_name, args.config)
    ckpt = Path(args.checkpoint)
    evidence_root = Path(args.rendered_evidence_root)
    out_csv = Path(args.out_csv)

    if not np.allclose(s1.GRAVITY, np.array([0.0, 1.0, 0.0])):
        raise AssertionError(f"Expected gravity=[0,1,0], got {s1.GRAVITY}")
    if not config_path.exists():
        write_pending(out_csv, run_name, config_path, f"config missing: {config_path}")
        raise SystemExit(f"[fc-s5-eval] config missing: {config_path}")
    if not ckpt.exists():
        write_pending(out_csv, run_name, config_path, f"checkpoint missing: {ckpt}")
        raise SystemExit(f"[fc-s5-eval] checkpoint missing: {ckpt}")

    evaluate_run(run_name, config_path, ckpt, evidence_root, out_csv, args)


if __name__ == "__main__":
    main()
