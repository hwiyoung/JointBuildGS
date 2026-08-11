#!/usr/bin/env python3
"""Finalize the add-only raw-vs-OpenMVS-surface metric-depth report."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from PIL import Image


ROOT = Path("/artifacts/JointBuildGS/phase-payloads/p2/e3_local_4906982_mvs_surface_depth_v1/P2-E3-LOCAL-4906982-MVS-SURFACE-DEPTH-v1")
REPO = Path("/workspace/JointBuildGS")
TASK_ID = "P2-E3-LOCAL-4906982-MVS-SURFACE-DEPTH-v1"
ARMS = ("RAW_DEPTH", "MVS_SURFACE_METRIC")


def atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value)
    temporary.replace(path)


def atomic_json(path: Path, value: object) -> None:
    atomic_text(path, json.dumps(value, indent=2, sort_keys=True) + "\n")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def number(value: object) -> float | None:
    if value in (None, "", "None"):
        return None
    return float(value)


def normalize_scientific_verdict(value: object) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "scientific_verdict":
                value[key] = None
            else:
                normalize_scientific_verdict(child)
    elif isinstance(value, list):
        for child in value:
            normalize_scientific_verdict(child)


def fmt(value: float | None, digits: int = 3) -> str:
    return "NA" if value is None else f"{value:.{digits}f}"


def main() -> None:
    metrics_path = ROOT / "metrics.json"
    mvs_path = ROOT / "mvs_surface_audit.json"
    reference_path = ROOT / "reference_diagnostic/case_metrics.csv"
    for path in (metrics_path, mvs_path, reference_path):
        if not path.is_file():
            raise FileNotFoundError(path)
    metrics = json.loads(metrics_path.read_text())
    mvs = json.loads(mvs_path.read_text())
    reference_rows = list(csv.DictReader(reference_path.open()))
    mvs20 = {row["arm"]: row for row in mvs["rows"] if int(row["completed_updates"]) == 20000}
    ref20 = {row["arm"]: row for row in reference_rows if int(row["completed_updates"]) == 20000}
    if set(mvs20) != set(ARMS) or set(ref20) != set(ARMS):
        raise RuntimeError("20k evaluation-only rows are incomplete")
    aggregate = metrics["aggregates"]["20000"]
    checkpoint_evaluations = {
        arm: json.loads((ROOT / f"arms/{arm}/R1/evaluation/step_020000/evaluation.json").read_text())
        for arm in ARMS
    }

    def a(arm: str, key: str) -> float | None:
        return number(aggregate[arm][key]["mean"])

    def s(arm: str, key: str) -> float | None:
        return number(mvs20[arm].get(key))

    def r(arm: str, key: str) -> float | None:
        return number(ref20[arm].get(key))

    input_definition = json.loads((ROOT / "mvs_surface_depth_definition.json").read_text())
    metrics["task_id"] = TASK_ID
    metrics["comparison"] = "MVS_SURFACE_METRIC minus RAW_DEPTH"
    metrics["combined_intervention"] = {
        "selection": "positive finite nearest OpenMVS mesh ray hits",
        "target": "nearest OpenMVS mesh camera-Z metres",
        "causal_limit": "selection and target-value effects are not separated",
    }
    metrics["input_depth_comparison"] = {
        "view_count": input_definition["view_count"],
        "mesh_valid_fraction": input_definition["mesh_valid_fraction"],
        "raw_mesh_abs_median_m_across_views": input_definition["raw_mesh_abs_median_m_across_views"],
    }
    metrics["mvs_surface_audit_20k"] = mvs20
    metrics["lod2_evaluation_only_20k"] = ref20
    metrics["training_experiments_started"] = 1
    metrics["training_experiments_completed"] = 1
    metrics["scientific_verdict"] = None
    normalize_scientific_verdict(metrics)
    atomic_json(metrics_path, metrics)

    high_z_lines = []
    for label, key, digits in (
        ("Gaussian Z p99 (m)", "z_p99", 3),
        ("Gaussian Z max (m)", "z_max", 3),
        ("Z>650 count", "z_gt_650", 0),
        ("Z>650 share", "z_gt_650_ratio", 6),
        ("Above sparse-seed max count", "above_seed_max", 0),
        ("High-opacity Z>650 count", "high_z_opacity_ge_0p9", 0),
    ):
        left, right = a(ARMS[0], key), a(ARMS[1], key)
        delta = None if left is None or right is None else right - left
        high_z_lines.append(f"| {label} | {fmt(left, digits)} | {fmt(right, digits)} | {fmt(delta, digits)} |")

    surface_lines = []
    for label, key, digits in (
        ("Ordinary point-to-plane median (m)", "ordinary_point_to_plane_m_median", 4),
        ("Ordinary point-to-plane p95 (m)", "ordinary_point_to_plane_m_p95", 4),
        ("Ordinary point-to-point median (m)", "ordinary_point_to_point_m_median", 4),
        ("Ordinary normal median (deg)", "ordinary_normal_angle_deg_median", 3),
        ("Ordinary normal p95 (deg)", "ordinary_normal_angle_deg_p95", 3),
        ("MVS grid coverage", "ordinary_grid_coverage_of_mvs", 5),
        ("Roof point-to-plane median (m)", "roof_point_to_plane_m_median", 4),
        ("Roof normal median (deg)", "roof_normal_angle_deg_median", 3),
        ("Wall point-to-plane median (m)", "wall_point_to_plane_m_median", 4),
        ("Wall normal median (deg)", "wall_normal_angle_deg_median", 3),
    ):
        left, right = s(ARMS[0], key), s(ARMS[1], key)
        delta = None if left is None or right is None else right - left
        surface_lines.append(f"| {label} | {fmt(left, digits)} | {fmt(right, digits)} | {fmt(delta, digits)} |")

    downstream_lines = []
    for label, source, key, digits in (
        ("Held-out PSNR (dB)", "aggregate", "eval_psnr", 3),
        ("Held-out SSIM", "aggregate", "eval_ssim", 4),
        ("Held-out LPIPS", "aggregate", "eval_lpips", 4),
        ("Fusion >=2-view points", "aggregate", "fusion_ge2", 0),
        ("Fusion >=3-view share", "aggregate", "fusion_ge3_ratio", 5),
        ("Roof-normal density (pts/m2)", "aggregate", "roof_density", 3),
        ("Roofer internal RMSE", "aggregate", "roofer_rmse_lod22", 3),
        ("LoD2 eval classified abs-dZ median (m)", "reference", "classified_abs_dz_m_median", 3),
        ("LoD2 eval classified abs-dZ p95 (m)", "reference", "classified_abs_dz_m_p95", 3),
        ("LoD2 eval classified abs-dZ RMSE (m)", "reference", "classified_abs_dz_m_rmse", 3),
        ("LoD2 eval classified normal median (deg)", "reference", "classified_normal_angle_deg_median", 3),
        ("LoD2 eval classified grid coverage", "reference", "classified_grid_coverage_fraction", 5),
        ("LoD2 eval Roofer XY coverage", "reference", "roofer_roof_xy_coverage_fraction", 5),
        ("LoD2 eval Roofer F-score 0.5m", "reference", "roofer_surface_fscore_0p5m", 5),
    ):
        left = a(ARMS[0], key) if source == "aggregate" else r(ARMS[0], key)
        right = a(ARMS[1], key) if source == "aggregate" else r(ARMS[1], key)
        delta = None if left is None or right is None else right - left
        downstream_lines.append(f"| {label} | {fmt(left, digits)} | {fmt(right, digits)} | {fmt(delta, digits)} |")
    raw_depth_loss = number((checkpoint_evaluations[ARMS[0]]["training_scalars"].get("loss/depth") or {}).get("value"))
    fused_depth_loss = number((checkpoint_evaluations[ARMS[1]]["training_scalars"].get("loss/depth") or {}).get("value"))
    raw_depth_weight = number((checkpoint_evaluations[ARMS[0]]["training_scalars"].get("loss_weight/depth") or {}).get("value"))
    fused_depth_weight = number((checkpoint_evaluations[ARMS[1]]["training_scalars"].get("loss_weight/depth") or {}).get("value"))

    comparison = f"""# {TASK_ID}

## Input depth comparison

- Same 55 cameras and metric camera-Z convention.
- OpenMVS mesh-hit coverage across views: min `{100*input_definition['mesh_valid_fraction']['min']:.2f}%`, median `{100*input_definition['mesh_valid_fraction']['median']:.2f}%`, max `{100*input_definition['mesh_valid_fraction']['max']:.2f}%`.
- Median across views of the overlapping-pixel raw-vs-mesh absolute-depth median: `{input_definition['raw_mesh_abs_median_m_across_views']:.3f} m`.
- The intervention changes both the target value and valid-pixel selection. It is a direct transfer test, not a target-vs-selection causal separation.

## High-Z — 20k

| Endpoint | RAW_DEPTH | MVS_SURFACE_METRIC | Delta |
|---|---:|---:|---:|
{chr(10).join(high_z_lines)}

## Ordinary MVS surface — 20k

The filtered fused MVS seed is a transfer reference, not independent ground truth.

| Endpoint | RAW_DEPTH | MVS_SURFACE_METRIC | Delta |
|---|---:|---:|---:|
{chr(10).join(surface_lines)}

## Held-out / fusion / Roofer — 20k

LoD2 rows are evaluation-only and were not available to training, masking, or view selection.

| Endpoint | RAW_DEPTH | MVS_SURFACE_METRIC | Delta |
|---|---:|---:|---:|
{chr(10).join(downstream_lines)}

The latest logged 20k-adjacent unweighted depth L1 values were `{fmt(raw_depth_loss, 5)}` for RAW_DEPTH and `{fmt(fused_depth_loss, 5)}` for MVS_SURFACE_METRIC; their effective weights were `{fmt(raw_depth_weight, 3)}` and `{fmt(fused_depth_weight, 3)}`.

## Measurement scope

- One building, one seed, one exact common 7k full-state continuation per arm.
- `RAW_DEPTH` is the previously completed DEPTH03/R1 control, linked read-only into this add-only namespace.
- `MVS_SURFACE_METRIC` uses sparse initialization and differs after 7k only in its depth payload: nearest OpenMVS surface camera-Z at mesh-hit pixels.
- Expected rendered depth, L1, weight, schedule, MVC, normal consistency, densification, views, and GPU are unchanged.
- The permission failure recorded in `issues.md` occurred before the training container launched and completed zero optimizer updates.
- `scientific_verdict: null`.
"""
    atomic_text(ROOT / "comparison.md", comparison)

    paired = ROOT / "representative_images/paired"
    paired.mkdir(parents=True, exist_ok=True)
    for step in (7000, 12000, 15000, 20000):
        left_dir = ROOT / f"representative_images/{ARMS[0]}/step_{step:06d}"
        right_dir = ROOT / f"representative_images/{ARMS[1]}/step_{step:06d}"
        for left_path in sorted(left_dir.glob("*.png")):
            right_path = right_dir / left_path.name
            if not right_path.is_file():
                raise FileNotFoundError(right_path)
            left = Image.open(left_path).convert("RGB")
            right = Image.open(right_path).convert("RGB")
            canvas = Image.new("RGB", (left.width + right.width, max(left.height, right.height)), "white")
            canvas.paste(left, (0, 0)); canvas.paste(right, (left.width, 0))
            canvas.save(paired / f"step_{step:06d}__{left_path.name}")
    names = sorted(path.name for path in paired.glob("*.png"))
    viewer = ROOT / "viewer"
    viewer.mkdir(exist_ok=True)
    html = '''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>4906982 raw vs fused-surface depth</title><style>body{font-family:system-ui;background:#0d1117;color:#e6edf3;margin:0;padding:20px}header{max-width:1600px;margin:auto}select,a{padding:8px;margin:4px;background:#21262d;color:#e6edf3;border:1px solid #30363d;border-radius:5px}img{display:block;max-width:100%;margin:18px auto;border:1px solid #30363d}small{color:#8b949e}</style></head><body><header><h1>DEBY_LOD2_4906982 - RAW_DEPTH vs MVS_SURFACE_METRIC</h1><p>Left is the reused raw COLMAP control; right is the OpenMVS mesh-surface metric-depth continuation.</p><label>Panel <select id="panel"></select></label><a href="../comparison.md">comparison.md</a><br><small>Scientific verdict: null</small></header><img id="view"><script>const names=__NAMES__;const s=document.getElementById('panel'),v=document.getElementById('view');for(const n of names){const o=document.createElement('option');o.value=n;o.textContent=n;s.appendChild(o)}function show(){v.src='../representative_images/paired/'+s.value}s.onchange=show;show();</script></body></html>'''.replace("__NAMES__", json.dumps(names))
    atomic_text(viewer / "index.html", html)
    atomic_json(ROOT / "viewer_slot.json", {
        "schema": "jointbuildgs.viewer.comparison_slot.v1",
        "slot_id": "p2-e3-local-4906982-mvs-surface-depth-v1",
        "label": "DEBY_LOD2_4906982 raw depth vs MVS surface metric depth",
        "relative_url": "viewer/index.html",
        "panel_count": len(names),
        "separate_add_only_slot": True,
        "legacy_mvs_seed_color_v3_modified": False,
        "scientific_verdict": None,
    })
    contract = json.loads((ROOT / "experiment_contract.json").read_text())
    contract["status"] = "COMPLETE_MEASURED"
    contract["training_experiments_started"] = 1
    contract["training_experiments_completed"] = 1
    contract["scientific_verdict"] = None
    atomic_json(ROOT / "experiment_contract.json", contract)
    notes = f"""# {TASK_ID}

Status: `COMPLETE_MEASURED`.

- Training experiments completed: 1 new continuation; 1 frozen raw control reused read-only.
- Checkpoint render/fusion/classification/Roofer: 8/8 complete.
- MVS ordinary-surface and LoD2 evaluation-only diagnostics: complete.
- Input raw-vs-fused panels: 3; paired held-out checkpoint panels: {len(names)}.
- Existing viewer state was not modified; `viewer/` is a separate comparison slot.
- Scientific verdict: `null`.
"""
    atomic_text(ROOT / "NOTES.md", notes)
    provenance = json.loads((ROOT / "provenance.json").read_text())
    provenance["ended_utc"] = provenance.get("ended_utc") or __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
    source_paths = [
        REPO / "scripts/p2/e3_local_4906982_mvs_surface_depth_v1/run.py",
        REPO / "scripts/p2/e3_local_4906982_mvs_surface_depth_v1/inside.py",
        REPO / "scripts/p2/e3_local_4906982_mvs_surface_depth_v1/finalize_report.py",
        REPO / "configs/p2/e3_local_4906982_mvs_surface_depth_v1/common.yaml",
        REPO / "configs/p2/e3_local_4906982_mvs_surface_depth_v1/projection.yaml",
        REPO / "configs/p2/e3_local_4906982_mvs_surface_depth_v1/mvs_surface_metric.yaml",
        REPO / "configs/p2/e3_local_4906982_mvc_depth_v1/depth03.yaml",
        REPO / "src/stage2/train.py",
        REPO / "src/stage2/renderer.py",
        REPO / "src/stage2/loss/data_fitting.py",
        REPO / "src/stage2/loss/multiview.py",
    ]
    provenance["source_config_sha256"] = {
        str(path.relative_to(REPO)): sha256(path) for path in source_paths
    }
    outputs = ["experiment_contract.json", "input_hashes.json", "config_diff.txt", "mvs_surface_depth_definition.json", "mvs_surface_depth_metrics.csv", "checkpoint_metrics.csv", "paired_checkpoint_deltas.csv", "metrics.json", "mvs_surface_audit.json", "mvs_surface_metrics.csv", "comparison.md", "NOTES.md", "issues.md", "viewer_slot.json"]
    provenance["output_index_sha256"] = {name: sha256(ROOT / name) for name in outputs}
    provenance["scientific_verdict"] = None
    atomic_json(ROOT / "provenance.json", provenance)
    print(json.dumps({"status": "COMPLETE_MEASURED", "comparison": str(ROOT / "comparison.md"), "paired_panels": len(names), "viewer": str(viewer / "index.html"), "scientific_verdict": None}, indent=2))


if __name__ == "__main__":
    main()
