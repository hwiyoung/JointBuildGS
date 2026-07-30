"""FC-S6 rendered-evidence Stage3Algo-v1 + Metric-v1 evaluation adapter.

This script reuses the FC-S5 rendered-evidence export and Stage3/Metric-v1
helpers without changing them. It only changes the experiment bookkeeping:
arbitrary FC-S6 arms are merged into phase-level CSVs and augmented with
run-level TensorBoard diagnostics plus per-bid terrain evidence quantiles.
"""
from __future__ import annotations

import argparse
import csv
import math
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import scripts.stage3_readout.fc_s5_stage3_metric_v1_eval as base  # noqa: E402


OUT_ROOT = ROOT / "results/FC_S6_componentwise_revised_lmutual_design_validation"
BASELINE_CSV = (
    ROOT
    / "results/footprint_conditioned_readout"
    / "FC_S3_mutual_loss_alignment_g2_target_definition"
    / "phase1_full_e1_e2_comparison/e1_e2_paired_metrics_by_bid.csv"
)

SPLITS = {
    "all_10": base.TARGET_BIDS,
    "easy_control": base.EASY_CONTROL_BIDS,
    "hard_diagnostic": base.HARD_DIAGNOSTIC_BIDS,
    "guard_bids": base.GUARD_BIDS,
    "roof_complex": ["B3", "B123", "B126"],
    "terrain_sensitive": ["B104", "B6", "B50"],
}

EXTRA_FIELDS = [
    "n_faces",
    "n_roof_faces",
    "n_wall_faces",
    "n_ground_faces",
    "terrain_y_p10",
    "terrain_y_p50",
    "terrain_y_p90",
    "mutual_mass_roof",
    "mutual_mass_wall",
    "mutual_mass_terrain",
    "entropy_roof",
    "entropy_wall",
    "entropy_terrain",
    "height_roof_p10",
    "height_roof_p50",
    "height_roof_p90",
    "height_wall_p10",
    "height_wall_p50",
    "height_wall_p90",
    "height_terrain_p10",
    "height_terrain_p50",
    "height_terrain_p90",
    "grad_norm_base",
    "grad_norm_mutual",
    "grad_cosine_mutual_depth",
    "grad_cosine_mutual_normal",
    "grad_cosine_mutual_semantic",
    "grad_cosine_mutual_photo",
]
METRIC_FIELDS = base.METRIC_FIELDS + [f for f in EXTRA_FIELDS if f not in base.METRIC_FIELDS]

TB_TAG_TO_FIELD = {
    "mutual/mass_roof": "mutual_mass_roof",
    "mutual/mass_wall": "mutual_mass_wall",
    "mutual/mass_terrain": "mutual_mass_terrain",
    "entropy/roof": "entropy_roof",
    "entropy/wall": "entropy_wall",
    "entropy/terrain": "entropy_terrain",
    "mutual/height_roof_p10": "height_roof_p10",
    "mutual/height_roof_p50": "height_roof_p50",
    "mutual/height_roof_p90": "height_roof_p90",
    "mutual/height_wall_p10": "height_wall_p10",
    "mutual/height_wall_p50": "height_wall_p50",
    "mutual/height_wall_p90": "height_wall_p90",
    "mutual/height_terrain_p10": "height_terrain_p10",
    "mutual/height_terrain_p50": "height_terrain_p50",
    "mutual/height_terrain_p90": "height_terrain_p90",
    "grad_norm/base": "grad_norm_base",
    "grad_norm/mutual": "grad_norm_mutual",
    "grad_cosine(mutual, depth)": "grad_cosine_mutual_depth",
    "grad_cosine(mutual, normal)": "grad_cosine_mutual_normal",
    "grad_cosine(mutual, semantic)": "grad_cosine_mutual_semantic",
    "grad_cosine(mutual, photo)": "grad_cosine_mutual_photo",
}


def rel(path: Optional[Path]) -> str:
    if path is None:
        return ""
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def read_csv(path: Path) -> List[Dict[str, str]]:
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


def mean_field(rows: Iterable[Dict], field: str) -> Optional[float]:
    vals = [safe_float(r.get(field)) for r in rows]
    vals = [v for v in vals if v is not None]
    return float(np.mean(vals)) if vals else None


def latest_tb_scalars(run_out_dir: Path) -> Dict[str, float]:
    tb_dir = run_out_dir / "tb"
    if not tb_dir.exists():
        return {}
    try:
        from tensorboard.backend.event_processing.event_accumulator import EventAccumulator
    except Exception:
        return {}
    values: Dict[str, float] = {}
    for event_path in sorted(tb_dir.glob("events.out.tfevents.*")):
        try:
            ea = EventAccumulator(str(event_path), size_guidance={"scalars": 0})
            ea.Reload()
            tags = ea.Tags().get("scalars", [])
            for tag, field in TB_TAG_TO_FIELD.items():
                if tag not in tags:
                    continue
                events = ea.Scalars(tag)
                if events:
                    values[field] = float(events[-1].value)
        except Exception:
            continue
    return values


def terrain_y_quantiles(local_ev: Dict) -> Dict[str, object]:
    points = local_ev.get("points")
    classes = local_ev.get("classes")
    if points is None or classes is None:
        return {"terrain_y_p10": "", "terrain_y_p50": "", "terrain_y_p90": ""}
    mask = classes == 3
    if not np.any(mask):
        return {"terrain_y_p10": "", "terrain_y_p50": "", "terrain_y_p90": ""}
    y = points[mask, 1].astype(np.float64)
    return {
        "terrain_y_p10": float(np.quantile(y, 0.10)),
        "terrain_y_p50": float(np.quantile(y, 0.50)),
        "terrain_y_p90": float(np.quantile(y, 0.90)),
    }


def face_counts(faces: List[Dict]) -> Dict[str, int]:
    return {
        "n_faces": len(faces),
        "n_roof_faces": sum(1 for f in faces if f.get("type") == "RoofSurface"),
        "n_wall_faces": sum(1 for f in faces if f.get("type") == "WallSurface"),
        "n_ground_faces": sum(1 for f in faces if f.get("type") == "GroundSurface"),
    }


def merge_run_rows(out_csv: Path, run_name: str, rows: List[Dict]) -> None:
    old = [r for r in read_csv(out_csv) if r.get("run") != run_name]
    write_csv(out_csv, old + rows, METRIC_FIELDS)


def write_pending(out_csv: Path, run_name: str, config_path: Path, reason: str) -> None:
    rows = []
    for bid in base.TARGET_BIDS:
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
    merge_run_rows(out_csv, run_name, rows)


def update_split_summary(metrics_csv: Path, split_csv: Path) -> None:
    rows = read_csv(metrics_csv)
    runs = sorted({r.get("run", "") for r in rows if r.get("run")})
    summary_rows = []
    mean_fields = [
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
        "n_faces",
        "n_roof_faces",
        "n_wall_faces",
        "n_ground_faces",
        "terrain_y_p50",
        "mutual_mass_terrain",
        "entropy_terrain",
        "grad_norm_mutual",
    ]
    for run in runs:
        run_rows = [r for r in rows if r.get("run") == run]
        for split_name, bids in SPLITS.items():
            wanted = set(bids)
            part = [r for r in run_rows if r.get("bid") in wanted]
            ok = [r for r in part if r.get("status") == "OK"]
            if len(ok) == len(bids):
                status = "OK"
                note = "completed Stage3Algo-v1 + Metric-v1 rows"
            elif any(r.get("status") == "PENDING" for r in part) or len(part) < len(bids):
                status = "PENDING"
                note = "pending completed Stage2/rendered evidence/Stage3 metrics"
            else:
                status = "INCOMPLETE_OR_FAILED"
                note = "one or more rows failed or are incomplete"
            row = {
                "run": run,
                "split": split_name,
                "n_bids": len(bids),
                "ok_count": len(ok),
                "status": status,
                "note": note,
            }
            for field in mean_fields:
                row[f"mean_{field}"] = mean_field(ok, field)
            summary_rows.append(row)
    write_csv(split_csv, summary_rows)


def update_win_loss(metrics_csv: Path, win_loss_csv: Path) -> None:
    rows = read_csv(metrics_csv)
    baseline = {r["bid"]: r for r in read_csv(BASELINE_CSV)}
    out = []
    for run in sorted({r.get("run", "") for r in rows if r.get("run")}):
        ok = [r for r in rows if r.get("run") == run and r.get("status") == "OK"]
        wins = losses = ties = compared = 0
        for row in ok:
            bid = row.get("bid", "")
            value = safe_float(row.get("F"))
            base_value = safe_float(baseline.get(bid, {}).get("e1_F"))
            if value is None or base_value is None:
                continue
            compared += 1
            diff = value - base_value
            if abs(diff) <= 0.005:
                ties += 1
            elif diff > 0:
                wins += 1
            else:
                losses += 1
        out.append({
            "run": run,
            "metric": "F_vs_E1_baseline",
            "compared_bids": compared,
            "wins": wins,
            "ties_practical_0p005": ties,
            "losses": losses,
            "status": "OK" if compared == len(base.TARGET_BIDS) else "PENDING_OR_INCOMPLETE",
        })
    write_csv(win_loss_csv, out)


def evaluate_run(
    run_name: str,
    config_path: Path,
    checkpoint: Path,
    evidence_root: Path,
    out_csv: Path,
    args: argparse.Namespace,
) -> List[Dict]:
    evidence_npz = base.export_rendered_evidence(config_path, checkpoint, evidence_root, args)
    evidence = base.load_rendered_evidence(evidence_npz)
    run_out_dir = config_path.parent
    try:
        import yaml

        cfg = yaml.safe_load(config_path.read_text())
        run_out_dir = Path(cfg.get("out_dir", run_out_dir))
        if not run_out_dir.is_absolute():
            run_out_dir = ROOT / run_out_dir
    except Exception:
        pass
    tb_scalars = latest_tb_scalars(run_out_dir)
    buildings = base.parse_scene_obj(base.fc.SCENE, frame="obj")["buildings"]
    by_bid = {int(b["building_id"]): b for b in buildings}
    rows = []
    for bid in base.TARGET_BIDS_INT:
        building = by_bid[bid]
        footprint = base.fc.footprint_for_building(building)
        local_ev = base.fc.crop_evidence(evidence, footprint, run_name, bid)
        readout_dir = evidence_root / "stage3_readout" / run_name / f"B{bid}"
        metric_dir = evidence_root / "metric_v1" / run_name / f"B{bid}"
        try:
            status, faces, _city_diag, _patch_log = base.s3.stage3_v1_readout(
                local_ev,
                building,
                footprint,
                run_name,
                bid,
                readout_dir,
            )
            metric = base.s3.metric_v1_evaluate(
                faces,
                building,
                local_ev,
                run_name,
                bid,
                base.s3.STAGE3_ALGO_V1,
                status.get("status", ""),
                status.get("failure_reason", ""),
                metric_dir,
                readout_dir,
            )
            row = base.metric_row_from_v1(run_name, config_path, bid, status, metric, faces, local_ev)
            row.update(face_counts(faces))
            row.update(terrain_y_quantiles(local_ev))
            row.update(tb_scalars)
            rows.append(row)
        except Exception as exc:  # noqa: BLE001
            row = {field: "" for field in METRIC_FIELDS}
            row.update({
                "run": run_name,
                "bid": f"B{bid}",
                "job_status": "COMPLETED",
                "config_path": rel(config_path),
                "status": "EVAL_EXCEPTION",
                "failure_reason": f"{type(exc).__name__}: {exc}",
            })
            row.update(tb_scalars)
            rows.append(row)
    merge_run_rows(out_csv, run_name, rows)
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-name", required=True)
    ap.add_argument("--config", required=True)
    ap.add_argument("--checkpoint", required=True)
    ap.add_argument("--rendered-evidence-root", required=True)
    ap.add_argument("--out-csv", required=True)
    ap.add_argument("--split-summary-csv")
    ap.add_argument("--win-loss-csv")
    ap.add_argument("--max-views", type=int, default=56)
    ap.add_argument("--render-downscale", type=float, default=0.25)
    ap.add_argument("--pixel-stride", type=int, default=2)
    ap.add_argument("--max-raw-samples", type=int, default=3_000_000)
    ap.add_argument("--max-ply-points", type=int, default=750_000)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--device", choices=["cuda", "cpu"], default="cuda")
    ap.add_argument("--force-render-export", action="store_true")
    args = ap.parse_args()

    if not np.allclose(base.s1.GRAVITY, np.array([0.0, 1.0, 0.0])):
        raise AssertionError(f"Expected gravity=[0,1,0], got {base.s1.GRAVITY}")

    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = ROOT / config_path
    checkpoint = Path(args.checkpoint)
    if not checkpoint.is_absolute():
        checkpoint = ROOT / checkpoint
    evidence_root = Path(args.rendered_evidence_root)
    if not evidence_root.is_absolute():
        evidence_root = ROOT / evidence_root
    out_csv = Path(args.out_csv)
    if not out_csv.is_absolute():
        out_csv = ROOT / out_csv

    if not config_path.exists():
        write_pending(out_csv, args.run_name, config_path, f"config missing: {config_path}")
        raise SystemExit(f"[fc-s6-eval] config missing: {config_path}")
    if not checkpoint.exists():
        write_pending(out_csv, args.run_name, config_path, f"checkpoint missing: {checkpoint}")
        if args.split_summary_csv:
            update_split_summary(out_csv, ROOT / args.split_summary_csv)
        if args.win_loss_csv:
            update_win_loss(out_csv, ROOT / args.win_loss_csv)
        raise SystemExit(f"[fc-s6-eval] checkpoint missing: {checkpoint}")

    evaluate_run(args.run_name, config_path, checkpoint, evidence_root, out_csv, args)
    if args.split_summary_csv:
        update_split_summary(out_csv, ROOT / args.split_summary_csv)
    if args.win_loss_csv:
        update_win_loss(out_csv, ROOT / args.win_loss_csv)


if __name__ == "__main__":
    main()
