#!/usr/bin/env python3
"""Consolidate measurements and build the canonical technical-report artifact."""
from __future__ import annotations

import base64
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from PIL import Image


REPO = Path("/workspace/JointBuildGS")
ROOT = Path(
    "/artifacts/JointBuildGS/phase-payloads/p2/e4_local_4906982_55v_als_prior_v1/"
    "P2-E4-LOCAL-4906982-55V-ALS-PRIOR-v1"
)
ARMS = ("FUSED_VIS_CONF", "E4_ALS_PRIOR_ONLY")
LABELS = {"FUSED_VIS_CONF": "55-view control", "E4_ALS_PRIOR_ONLY": "55-view E4 + ALS"}
STEPS = (7000, 12000, 15000, 20000)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def number(row: dict[str, str], key: str) -> float:
    return float(row[key])


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def report_image(source: Path, destination: Path, width: int, quality: int = 78) -> str:
    image = Image.open(source).convert("RGB")
    if image.width > width:
        image.thumbnail((width, 10000), Image.Resampling.LANCZOS)
    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination, "JPEG", quality=quality, optimize=True, progressive=True)
    encoded = base64.b64encode(destination.read_bytes()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def image_html(uri: str, caption: str) -> str:
    return (
        '<figure style="margin:1rem 0"><img style="width:100%;height:auto" '
        f'src="{uri}" alt="{caption}"><figcaption>{caption}</figcaption></figure>'
    )


def main() -> None:
    checkpoint_rows = read_csv(ROOT / "checkpoint_metrics.csv")
    checkpoints = {(row["arm"], int(row["completed_updates"])): row for row in checkpoint_rows}
    mvs_rows = json.loads((ROOT / "mvs_surface_audit.json").read_text())["rows"]
    mvs = {(row["arm"], int(row["completed_updates"])): row for row in mvs_rows}
    lod2_fused_rows = json.loads((ROOT / "lod2_fused_evaluation.json").read_text())["rows"]
    lod2_fused = {(row["arm"], int(row["completed_updates"])): row for row in lod2_fused_rows}
    lod2_stage3 = {}
    for slug in ("fused_vis_conf", "e4_als_prior_only"):
        for row in json.loads((ROOT / f"lod2_evaluation_{slug}.json").read_text())["rows"]:
            lod2_stage3[(row["arm"], int(row["completed_updates"]))] = row
    smrf_docs = {
        "FUSED_VIS_CONF": json.loads((ROOT / "smrf_diagnostic/metrics.json").read_text()),
        "E4_ALS_PRIOR_ONLY": json.loads((ROOT / "smrf_diagnostic_e4_20k/metrics.json").read_text()),
    }

    final_rows = []
    highz_rows = []
    for step in STEPS:
        highz_rows.append({
            "checkpoint": f"{step // 1000}k",
            **{LABELS[arm]: int(number(checkpoints[(arm, step)], "z_gt_650")) for arm in ARMS},
        })
    for arm in ARMS:
        c = checkpoints[(arm, 20000)]
        m = mvs[(arm, 20000)]
        lf = lod2_fused[(arm, 20000)]
        l3 = lod2_stage3[(arm, 20000)]
        smrf = smrf_docs[arm]["metrics"]
        final_rows.append({
            "arm": LABELS[arm],
            "gaussians": int(number(c, "gaussian_count")),
            "z_p99_m": number(c, "z_p99"),
            "z_max_m": number(c, "z_max"),
            "z_gt_650": int(number(c, "z_gt_650")),
            "z_gt_650_inside": int(m["gaussian_z_gt_650_footprint_inside_count"]),
            "z_gt_650_outside": int(m["gaussian_z_gt_650_footprint_outside_count"]),
            "eval_psnr_db": number(c, "eval_psnr"),
            "eval_ssim": number(c, "eval_ssim"),
            "eval_lpips": number(c, "eval_lpips"),
            "fusion_ge2": int(number(c, "fusion_ge2")),
            "fusion_ge3_ratio": number(c, "fusion_ge3_ratio"),
            "roof_density": number(c, "roof_density"),
            "wall_density": number(c, "wall_density"),
            "mvs_p2point_median_m": float(m["ordinary_point_to_point_m_median"]),
            "mvs_p2plane_median_m": float(m["ordinary_point_to_plane_m_median"]),
            "mvs_p2plane_p95_m": float(m["ordinary_point_to_plane_m_p95"]),
            "mvs_normal_median_deg": float(m["ordinary_normal_angle_deg_median"]),
            "mvs_coverage": float(m["ordinary_grid_coverage_of_mvs"]),
            "lod2_abs_dz_median_m": float(lf["abs_dz_m_median"]),
            "lod2_abs_dz_p95_m": float(lf["abs_dz_m_p95"]),
            "lod2_signed_dz_median_m": float(lf["signed_dz_m_median"]),
            "lod2_normal_median_deg": float(lf["normal_angle_deg_median"]),
            "lod2_normal_p95_deg": float(lf["normal_angle_deg_p95"]),
            "lod2_within_0p5m": float(lf["within_0p5m_fraction"]),
            "lod2_coherent_coverage": float(lf["coherent_grid_coverage_fraction"]),
            "smrf_ground_count": int(smrf["inside_footprint"]["class2_ground_count"]),
            "smrf_ground_fraction": float(smrf["inside_footprint"]["class2_ground_fraction"]),
            "smrf_building_count": int(smrf["inside_footprint"]["class6_building_count"]),
            "smrf_building_fraction": float(smrf["inside_footprint"]["class6_building_fraction"]),
            "smrf_low_relief_fraction": float(smrf["local_surface_continuity"]["cell_relief_le_0_5m_fraction"]),
            "smrf_largest_ground_component_fraction": float(smrf["local_surface_continuity"]["largest_ground_component_fraction_of_occupied"]),
            "roofer_internal_rmse_m": float(l3["roofer_internal_rmse"]),
            "roofer_roof_planes": int(number(c, "roofer_roof_planes")),
            "roofer_xy_coverage": float(l3["roofer_roof_xy_coverage_fraction"]),
            "roofer_fscore_0p5m": float(l3["roofer_surface_fscore_0p5m"]),
            "roofer_precision_0p5m": float(l3["roofer_surface_precision_0p5m"]),
            "roofer_completeness_0p5m": float(l3["roofer_surface_completeness_0p5m"]),
        })

    control, e4 = final_rows
    smrf_rows = [{"arm": row["arm"], "ground_fraction": row["smrf_ground_fraction"], "building_fraction": row["smrf_building_fraction"]} for row in final_rows]
    roofer_rows = [{"arm": row["arm"], "XY coverage": row["roofer_xy_coverage"], "0.5 m F-score": row["roofer_fscore_0p5m"]} for row in final_rows]
    surface_rows = [{
        "arm": row["arm"],
        "MVS p2plane median m": row["mvs_p2plane_median_m"],
        "LoD2 abs dZ median m": row["lod2_abs_dz_median_m"],
        "LoD2 normal median deg": row["lod2_normal_median_deg"],
        "LoD2 coherent coverage": row["lod2_coherent_coverage"],
    } for row in final_rows]

    comparison_metrics = {
        "schema": "jointbuildgs.p2.e4_local_4906982_55v_als_prior_v1.comparison_metrics.v1",
        "building_id": "DEBY_LOD2_4906982",
        "comparison": "existing FUSED_VIS_CONF/R1 versus E4_ALS_PRIOR_ONLY/R1",
        "view_count": 55,
        "train_view_count": 47,
        "held_out_view_count": 8,
        "training_experiments_started": 1,
        "exact_equal_through_update": 7000,
        "rows_20k": final_rows,
        "high_z_by_checkpoint": highz_rows,
        "smrf_causal_chain": "continuous low-local-relief fused surface -> SMRF class2 -> overlay preserves class2 -> Roofer receives the remaining class6 evidence",
        "scientific_verdict": None,
    }
    (ROOT / "comparison_metrics.json").write_text(json.dumps(comparison_metrics, indent=2, sort_keys=True) + "\n")
    with (ROOT / "comparison_metrics.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(final_rows[0]))
        writer.writeheader(); writer.writerows(final_rows)

    comparison = f"""# P2-E4 55-view Existing-ALS diagnostic

## Technical summary

- The previous 84% ground result is a Stage-3 classification failure mode: the control cloud already has 49,981 footprint points, but SMRF labels 42,181 ({control['smrf_ground_fraction']:.2%}) as class 2 because they form a broad, connected, low-relief sheet. The overlay preserves class 2 and sends only the remaining class-6 fragments to Roofer.
- One E4 training experiment was run from the exact-equal 7k FUSED_VIS_CONF state through 20k. Only the registered Existing-ALS metric depth and sign-invariant normal prior were added; the 55 views, 47/8 roles, MVS depth, MVC/NC, seed, GPU and densification remained fixed.
- E4 does not reproduce the OpenMVS surface more closely: MVS point-to-plane median worsened {control['mvs_p2plane_median_m']:.3f} -> {e4['mvs_p2plane_median_m']:.3f} m. Against evaluation-only LoD2, height median also worsened {control['lod2_abs_dz_median_m']:.3f} -> {e4['lod2_abs_dz_median_m']:.3f} m, while normal median improved {control['lod2_normal_median_deg']:.2f} -> {e4['lod2_normal_median_deg']:.2f} degrees.
- Downstream Roofer geometry changed strongly despite SMRF still retaining {e4['smrf_ground_fraction']:.2%} as ground: roof XY coverage {control['roofer_xy_coverage']:.2%} -> {e4['roofer_xy_coverage']:.2%}, 0.5 m F-score {control['roofer_fscore_0p5m']:.3f} -> {e4['roofer_fscore_0p5m']:.3f}, internal RMSE {control['roofer_internal_rmse_m']:.2f} -> {e4['roofer_internal_rmse_m']:.2f} m.

## Why SMRF produced 84% ground

| measurement at 20k | control | E4 + ALS |
|---|---:|---:|
| footprint points before classification | {control['smrf_ground_count'] + control['smrf_building_count']:,} | {e4['smrf_ground_count'] + e4['smrf_building_count']:,} |
| class 2 ground | {control['smrf_ground_count']:,} ({control['smrf_ground_fraction']:.2%}) | {e4['smrf_ground_count']:,} ({e4['smrf_ground_fraction']:.2%}) |
| class 6 building | {control['smrf_building_count']:,} ({control['smrf_building_fraction']:.2%}) | {e4['smrf_building_count']:,} ({e4['smrf_building_fraction']:.2%}) |
| occupied 1 m cells with relief <=0.5 m | {control['smrf_low_relief_fraction']:.2%} | {e4['smrf_low_relief_fraction']:.2%} |
| largest connected ground component / occupied cells | {control['smrf_largest_ground_component_fraction']:.2%} | {e4['smrf_largest_ground_component_fraction']:.2%} |

Both fused GS clouds have no LiDAR return-number structure. The frozen pipeline applies SMRF first and then applies the footprint overlay only where `Classification != 2`; therefore false class-2 roof points are intentionally left untouched. The 84% is not evidence that 84% of the footprint lacked points.

## High-Z remains separate from the building surface

| metric at 20k | control | E4 + ALS | E4-control |
|---|---:|---:|---:|
| Gaussian count | {control['gaussians']:,} | {e4['gaussians']:,} | {e4['gaussians']-control['gaussians']:+,} |
| Z p99 (m) | {control['z_p99_m']:.2f} | {e4['z_p99_m']:.2f} | {e4['z_p99_m']-control['z_p99_m']:+.2f} |
| Z max (m) | {control['z_max_m']:.2f} | {e4['z_max_m']:.2f} | {e4['z_max_m']-control['z_max_m']:+.2f} |
| Z>650 m | {control['z_gt_650']:,} | {e4['z_gt_650']:,} | {e4['z_gt_650']-control['z_gt_650']:+,} |
| Z>650 inside / outside footprint | {control['z_gt_650_inside']:,} / {control['z_gt_650_outside']:,} | {e4['z_gt_650_inside']:,} / {e4['z_gt_650_outside']:,} | — |

E4 slightly reduces the global high-Z count and Z tail, but does not eliminate it. Every Z>650 Gaussian in both arms is outside the shared building footprint, so this tail and the usable building surface must not be treated as the same failure.

## Normal building surface

| metric at 20k | control | E4 + ALS | E4-control |
|---|---:|---:|---:|
| MVS point-to-point median (m) | {control['mvs_p2point_median_m']:.3f} | {e4['mvs_p2point_median_m']:.3f} | {e4['mvs_p2point_median_m']-control['mvs_p2point_median_m']:+.3f} |
| MVS point-to-plane median / p95 (m) | {control['mvs_p2plane_median_m']:.3f} / {control['mvs_p2plane_p95_m']:.3f} | {e4['mvs_p2plane_median_m']:.3f} / {e4['mvs_p2plane_p95_m']:.3f} | {e4['mvs_p2plane_median_m']-control['mvs_p2plane_median_m']:+.3f} median |
| MVS normal median (deg) | {control['mvs_normal_median_deg']:.2f} | {e4['mvs_normal_median_deg']:.2f} | {e4['mvs_normal_median_deg']-control['mvs_normal_median_deg']:+.2f} |
| MVS 1 m grid coverage | {control['mvs_coverage']:.2%} | {e4['mvs_coverage']:.2%} | {e4['mvs_coverage']-control['mvs_coverage']:+.2%} |
| LoD2 abs dZ median / p95 (m), eval-only | {control['lod2_abs_dz_median_m']:.3f} / {control['lod2_abs_dz_p95_m']:.3f} | {e4['lod2_abs_dz_median_m']:.3f} / {e4['lod2_abs_dz_p95_m']:.3f} | {e4['lod2_abs_dz_median_m']-control['lod2_abs_dz_median_m']:+.3f} median |
| LoD2 signed dZ median (m), eval-only | {control['lod2_signed_dz_median_m']:+.3f} | {e4['lod2_signed_dz_median_m']:+.3f} | {e4['lod2_signed_dz_median_m']-control['lod2_signed_dz_median_m']:+.3f} |
| LoD2 normal median / p95 (deg), eval-only | {control['lod2_normal_median_deg']:.2f} / {control['lod2_normal_p95_deg']:.2f} | {e4['lod2_normal_median_deg']:.2f} / {e4['lod2_normal_p95_deg']:.2f} | {e4['lod2_normal_median_deg']-control['lod2_normal_median_deg']:+.2f} median |

The ALS intervention trades agreement with current-image OpenMVS for better reference-normal alignment. It is therefore an absolute geometry/orientation constraint, not an OpenMVS denoiser.

## Fusion and Roofer

| metric at 20k | control | E4 + ALS | E4-control |
|---|---:|---:|---:|
| held-out PSNR / SSIM / LPIPS | {control['eval_psnr_db']:.3f} / {control['eval_ssim']:.3f} / {control['eval_lpips']:.3f} | {e4['eval_psnr_db']:.3f} / {e4['eval_ssim']:.3f} / {e4['eval_lpips']:.3f} | {e4['eval_psnr_db']-control['eval_psnr_db']:+.3f} dB PSNR |
| fusion >=2 views | {control['fusion_ge2']:,} | {e4['fusion_ge2']:,} | {e4['fusion_ge2']-control['fusion_ge2']:+,} |
| fusion >=3 ratio | {control['fusion_ge3_ratio']:.2%} | {e4['fusion_ge3_ratio']:.2%} | {e4['fusion_ge3_ratio']-control['fusion_ge3_ratio']:+.2%} |
| roof / wall density | {control['roof_density']:.2f} / {control['wall_density']:.3f} | {e4['roof_density']:.2f} / {e4['wall_density']:.3f} | — |
| Roofer roof planes | {control['roofer_roof_planes']} | {e4['roofer_roof_planes']} | {e4['roofer_roof_planes']-control['roofer_roof_planes']:+d} |
| Roofer roof XY coverage, eval-only | {control['roofer_xy_coverage']:.2%} | {e4['roofer_xy_coverage']:.2%} | {e4['roofer_xy_coverage']-control['roofer_xy_coverage']:+.2%} |
| Roofer surface F-score 0.5 m, eval-only | {control['roofer_fscore_0p5m']:.3f} | {e4['roofer_fscore_0p5m']:.3f} | {e4['roofer_fscore_0p5m']-control['roofer_fscore_0p5m']:+.3f} |
| Roofer internal RMSE (m) | {control['roofer_internal_rmse_m']:.2f} | {e4['roofer_internal_rmse_m']:.2f} | {e4['roofer_internal_rmse_m']-control['roofer_internal_rmse_m']:+.2f} |

The E4 Roofer result is a real geometry difference, not only the `success=true` flag: the actual CityJSONSeq covers the footprint and its evaluation-only surface F-score is much higher. However, SMRF still discards most footprint evidence as class 2, so the readout remains confounded by classification.

## Recommended next bounded check

Keep the completed 20k clouds frozen and compare only Stage-3 classification: current SMRF versus a shared-footprint building-class assignment, with identical Roofer parameters. This readout-only test would isolate whether SMRF is suppressing otherwise usable E4 geometry; it should not retrain, refusion, retune ALS, or add another loss. Run it only after approval.

For generalization, a later E4 replication should use another building whose ALS/image acquisition difference is independently judged negligible. The current single-building run is non-confirmatory.

scientific_verdict: null
"""
    (ROOT / "comparison.md").write_text(comparison)

    assets = ROOT / "report_assets"
    smrf_uri = report_image(ROOT / "smrf_diagnostic/representative_images/smrf_ground_cause.png", assets / "smrf_ground_cause.jpg", 1300)
    surface_uri = report_image(ROOT / "representative_images/final_comparison/ordinary_surface_3d_20k.png", assets / "ordinary_surface_3d_20k.jpg", 1450)
    roofer_uri = report_image(ROOT / "representative_images/final_comparison/classified_and_roofer_20k.png", assets / "classified_and_roofer_20k.jpg", 1450)
    heldout_uri = report_image(ROOT / "representative_images/final_comparison/heldout_views_20k.png", assets / "heldout_views_20k.jpg", 1650)
    now = datetime.now(timezone.utc).isoformat()
    source_prefix = "phase-payloads/p2/e4_local_4906982_55v_als_prior_v1/P2-E4-LOCAL-4906982-55V-ALS-PRIOR-v1"
    sources = [{
        "id": "comparison",
        "label": "Consolidated E4 55-view measurements",
        "path": f"{source_prefix}/comparison_metrics.json",
        "query": {
            "description": "Saved checkpoint, MVS-surface, SMRF, LoD2 evaluation-only and Roofer measurements",
            "engine": "artifact-json",
            "sql": "SELECT * FROM comparison_metrics WHERE building_id = 'DEBY_LOD2_4906982'",
            "language": "sql",
            "executed_at": now,
            "filters": ["building=DEBY_LOD2_4906982", "replica=R1", "completed_updates in 7000,12000,15000,20000"],
            "metric_definitions": [
                "high-Z: EPSG:25832 Z > 650 m",
                "MVS ordinary surface: inside shared footprint and Z <= filtered MVS max Z + 5 m",
                "SMRF ground fraction: class 2 / all fused points inside the shared footprint",
                "LoD2 metrics are evaluation-only with prediction Z shift -45.7 m",
            ],
            "tables_used": ["comparison_metrics.json", "checkpoint_metrics.csv", "mvs_surface_audit.json", "lod2_fused_evaluation.json", "lod2_evaluation_fused_vis_conf.json", "lod2_evaluation_e4_als_prior_only.json"],
        },
    }, {
        "id": "design",
        "label": "E4 exact-55 experimental contract and provenance",
        "path": f"{source_prefix}/experiment_contract.json",
        "query": {
            "description": "Exact 7k fork, ALS prior preflight, frozen config comparison and execution provenance",
            "engine": "artifact-json",
            "sql": "SELECT * FROM experiment_contract WHERE task_id = 'P2-E4-LOCAL-4906982-55V-ALS-PRIOR-v1'",
            "language": "sql",
            "executed_at": now,
            "filters": ["55 fixed views", "47 train", "8 held-out", "one new learning run"],
            "metric_definitions": ["E4 intervention comprises registered Existing-ALS metric depth and sign-invariant normal"],
            "tables_used": ["experiment_contract.json", "config_diff.txt", "provenance.json", "control/common_state_gate_7000.json"],
        },
    }]

    cards = [
        {"id": "smrf", "dataset": "final", "sourceId": "comparison", "metrics": [
            {"label": "Control SMRF ground", "field": "smrf_ground_fraction", "format": "percent"},
            {"label": "E4 SMRF ground", "field": "e4_smrf_ground_fraction", "format": "percent"},
        ]},
        {"id": "mvs", "dataset": "final", "sourceId": "comparison", "metrics": [
            {"label": "E4 MVS p2plane median", "field": "e4_mvs_p2plane", "format": "number", "unit": "m"},
            {"label": "Control", "field": "control_mvs_p2plane", "format": "number", "unit": "m"},
        ]},
        {"id": "roofer", "dataset": "final", "sourceId": "comparison", "metrics": [
            {"label": "E4 Roofer F-score", "field": "e4_roofer_fscore", "format": "number"},
            {"label": "Control", "field": "control_roofer_fscore", "format": "number"},
        ]},
        {"id": "highz", "dataset": "final", "sourceId": "comparison", "metrics": [
            {"label": "E4 Z>650", "field": "e4_highz", "format": "number"},
            {"label": "Control", "field": "control_highz", "format": "number"},
        ]},
    ]
    charts = [
        {"id": "highz", "title": "Global high-Z count by checkpoint", "subtitle": "EPSG:25832 Z > 650 m; all 20k cases are outside the footprint", "intent": "comparison", "question": "Did E4 remove the high-Z tail?", "rationale": "Grouped bars preserve the discrete exact-checkpoint comparison.", "type": "bar", "dataset": "highz", "sourceId": "comparison", "encodings": {"x": {"field": "checkpoint", "type": "ordinal", "label": "Completed updates"}, "y": {"fields": [LABELS[ARMS[0]], LABELS[ARMS[1]]], "type": "quantitative", "label": "Gaussian count", "format": "number"}}, "valueFormat": "number", "layout": "full"},
        {"id": "smrf", "title": "SMRF class composition inside the footprint", "subtitle": "Class 2 remains the majority in both fixed 20k clouds", "intent": "comparison", "question": "Was E4 enough to remove the SMRF ground failure?", "rationale": "A two-series bar directly shows the ground/building partition.", "type": "bar", "dataset": "smrf", "sourceId": "comparison", "encodings": {"x": {"field": "arm", "type": "nominal", "label": "Arm"}, "y": {"fields": ["ground_fraction", "building_fraction"], "type": "quantitative", "label": "Fraction", "format": "percent"}}, "valueFormat": "percent", "layout": "full"},
        {"id": "roofer", "title": "Evaluation-only Roofer coverage and 0.5 m F-score", "subtitle": "The actual E4 CityJSONSeq covers nearly the full reference roof XY", "intent": "comparison", "question": "Did the downstream roof geometry become usable?", "rationale": "Coverage and F-score share a 0-1 scale and can be compared together.", "type": "bar", "dataset": "roofer", "sourceId": "comparison", "encodings": {"x": {"field": "arm", "type": "nominal", "label": "Arm"}, "y": {"fields": ["XY coverage", "0.5 m F-score"], "type": "quantitative", "label": "Fraction", "format": "percent"}}, "valueFormat": "percent", "layout": "full"},
    ]
    tables = [
        {"id": "surface", "title": "20k surface measurements", "description": "Current-image MVS and evaluation-only LoD2 comparisons", "dataset": "surface", "sourceId": "comparison", "layout": "full", "density": "spacious", "defaultSort": {"field": "arm", "direction": "asc"}, "columns": [
            {"field": "arm", "label": "Arm", "type": "text"},
            {"field": "MVS p2plane median m", "label": "MVS p2plane med (m)", "format": "number"},
            {"field": "LoD2 abs dZ median m", "label": "LoD2 abs dZ med (m)", "format": "number"},
            {"field": "LoD2 normal median deg", "label": "LoD2 normal med (deg)", "format": "number"},
            {"field": "LoD2 coherent coverage", "label": "LoD2 coherent coverage", "format": "percent"},
        ]},
        {"id": "final", "title": "20k checkpoint and downstream audit", "description": "Exact values for the fixed control and E4 arm", "dataset": "final_rows", "sourceId": "comparison", "layout": "full", "density": "dense", "defaultSort": {"field": "arm", "direction": "asc"}, "columns": [
            {"field": "arm", "label": "Arm", "type": "text"}, {"field": "gaussians", "label": "Gaussians", "format": "number"},
            {"field": "z_gt_650", "label": "Z>650", "format": "number"}, {"field": "eval_psnr_db", "label": "PSNR dB", "format": "number"},
            {"field": "fusion_ge2", "label": "Fusion >=2", "format": "number"}, {"field": "smrf_ground_fraction", "label": "SMRF ground", "format": "percent"},
            {"field": "roofer_xy_coverage", "label": "Roofer XY coverage", "format": "percent"}, {"field": "roofer_fscore_0p5m", "label": "Roofer F-score", "format": "number"},
        ]},
    ]
    final_card = [{
        "smrf_ground_fraction": control["smrf_ground_fraction"], "e4_smrf_ground_fraction": e4["smrf_ground_fraction"],
        "e4_mvs_p2plane": e4["mvs_p2plane_median_m"], "control_mvs_p2plane": control["mvs_p2plane_median_m"],
        "e4_roofer_fscore": e4["roofer_fscore_0p5m"], "control_roofer_fscore": control["roofer_fscore_0p5m"],
        "e4_highz": e4["z_gt_650"], "control_highz": control["z_gt_650"],
    }]
    title = "DEBY_LOD2_4906982: 84% SMRF ground and 55-view E4 diagnostic"
    artifact = {
        "surface": "report",
        "manifest": {
            "version": 1, "surface": "report", "title": title,
            "description": "Stage-separated diagnosis of SMRF ground classification and a single 55-view Existing-ALS E4 run.",
            "generatedAt": now, "cards": cards, "charts": charts, "tables": tables, "sources": sources,
            "blocks": [
                {"id": "title", "type": "markdown", "body": f"# {title}"},
                {"id": "summary", "type": "markdown", "body": "## Technical summary\n\nThe 84% ground result comes from SMRF interpreting a dense, connected, locally flat GS fusion sheet as terrain and the overlay preserving that class. The 55-view E4 run improves LoD2 normal alignment and downstream Roofer coverage, but it moves away from the filtered OpenMVS surface and does not remove either the SMRF failure mode or the global high-Z tail. `scientific_verdict: null`"},
                {"id": "headline", "type": "metric-strip", "cardIds": ["smrf", "mvs", "roofer", "highz"]},
                {"id": "smrf-finding", "type": "markdown", "sourceId": "comparison", "body": f"## The 84% is a classification interpretation, not missing point coverage\n\nThe control has {control['smrf_ground_count']+control['smrf_building_count']:,} points inside the footprint. SMRF retains {control['smrf_ground_fraction']:.2%} as class 2, and {control['smrf_largest_ground_component_fraction']:.2%} of occupied 1 m cells belong to one connected ground-majority component. Because the overlay applies only where classification is not 2, those roof-sheet points never become building class 6."},
                {"id": "smrf-chart", "type": "chart", "chartId": "smrf"},
                {"id": "smrf-image-note", "type": "markdown", "body": "The diagnostic panel shows the same point cloud as class composition, exterior-relative height, connected ground cells and vertical profile. The large class-2 region is spatially continuous rather than a hole."},
                {"id": "smrf-image", "type": "html", "body": image_html(smrf_uri, "Control SMRF ground-cause diagnostic")},
                {"id": "experiment", "type": "markdown", "sourceId": "design", "body": "## E4 was one controlled 7k-to-20k intervention\n\nThe arm starts from the exact-equal FUSED_VIS_CONF 7k model, optimizer and RNG state. Only registered Existing-ALS metric depth and sign-invariant normal are added from update 7001. Crop, cameras, view roles, MVS depth, MVC/NC, loss schedules, seed, GPU and densification remain fixed."},
                {"id": "highz-note", "type": "markdown", "sourceId": "comparison", "body": f"## High-Z changes little and remains outside the building\n\nE4 changes Z>650 from {control['z_gt_650']} to {e4['z_gt_650']} and Z p99 from {control['z_p99_m']:.2f} to {e4['z_p99_m']:.2f} m. At 20k every high-Z Gaussian is outside the shared footprint, so high-Z and ordinary building-surface usability are reported separately."},
                {"id": "highz-chart", "type": "chart", "chartId": "highz"},
                {"id": "surface-note", "type": "markdown", "sourceId": "comparison", "body": f"## E4 trades MVS agreement for reference-normal alignment\n\nFiltered-MVS point-to-plane median worsens from {control['mvs_p2plane_median_m']:.3f} to {e4['mvs_p2plane_median_m']:.3f} m. Evaluation-only LoD2 normal median improves from {control['lod2_normal_median_deg']:.2f} to {e4['lod2_normal_median_deg']:.2f} degrees, while LoD2 absolute height median worsens from {control['lod2_abs_dz_median_m']:.3f} to {e4['lod2_abs_dz_median_m']:.3f} m. ALS therefore supplies a different absolute geometry/orientation constraint; it is not an OpenMVS denoiser."},
                {"id": "surface-table", "type": "table", "tableId": "surface"},
                {"id": "surface-image-note", "type": "markdown", "body": "The 3D panel is restricted to the shared footprint and rendered before SMRF. It shows the E4-local height structures that explain the worse MVS residual despite similar XY coverage."},
                {"id": "surface-image", "type": "html", "body": image_html(surface_uri, "Filtered OpenMVS, 55-view control and 55-view E4 fused surfaces")},
                {"id": "roofer-note", "type": "markdown", "sourceId": "comparison", "body": f"## Roofer geometry improves even though SMRF still keeps {e4['smrf_ground_fraction']:.2%} as ground\n\nThe actual E4 CityJSONSeq reaches {e4['roofer_xy_coverage']:.2%} roof XY coverage and {e4['roofer_fscore_0p5m']:.3f} surface F-score at 0.5 m, versus {control['roofer_xy_coverage']:.2%} and {control['roofer_fscore_0p5m']:.3f} for control. This is geometry evidence, not merely `success=true`. Classification still withholds most input points, so the readout remains classification-confounded."},
                {"id": "roofer-chart", "type": "chart", "chartId": "roofer"},
                {"id": "roofer-image-note", "type": "markdown", "body": "Top views overlay class-2/class-6 evidence and actual Roofer roof polygons; oblique views show the emitted CityJSONSeq geometry at matched axes."},
                {"id": "roofer-image", "type": "html", "body": image_html(roofer_uri, "SMRF evidence and actual Roofer geometry at 20k")},
                {"id": "heldout-note", "type": "markdown", "sourceId": "comparison", "body": f"## Held-out appearance changes slightly in the wrong direction\n\nE4 held-out PSNR changes {control['eval_psnr_db']:.3f} to {e4['eval_psnr_db']:.3f} dB, SSIM {control['eval_ssim']:.3f} to {e4['eval_ssim']:.3f}, and LPIPS {control['eval_lpips']:.3f} to {e4['eval_lpips']:.3f}. The matched panels show view-dependent blur and depth/normal shifts rather than a uniform visual improvement."},
                {"id": "heldout-image", "type": "html", "body": image_html(heldout_uri, "Three matched held-out views: control left, E4 right")},
                {"id": "definitions", "type": "markdown", "body": "## Scope, data and metric definitions\n\nThe cohort is one building, one replica and the fixed 55-view crop (47 train, 8 held-out). OpenMVS is a process-relative current-image reference, not independent ground truth. Existing ALS is a registered external survey prior, not LoD2-derived ground truth. LoD2 Z, RoofSurface and normals are used only after training for evaluation. High-Z means EPSG:25832 Z > 650 m."},
                {"id": "final-table", "type": "table", "tableId": "final"},
                {"id": "method", "type": "markdown", "body": "## Methodology and validation\n\nAll project execution occurred in Docker. The exact-55 ALS prior was reprojected from the frozen raw ALS sources because 46 of 55 old 937-view raster shapes did not match the fixed crop. Registration, confidence, gradient and GPU-memory preflights passed. The 7k equality gate passed for model, optimizer, strategy, grouping, RNG and loss cursor. Checkpoints at 7k, 12k, 15k and 20k were evaluated with identical fusion and Roofer parameters."},
                {"id": "limitations", "type": "markdown", "body": "## Limitations, uncertainty and robustness\n\nThis is a non-confirmatory single-building, single-replica comparison. The E4 intervention contains two coupled channels from one Existing-ALS prior: metric depth and sign-invariant normal. It therefore measures the E4 prior package, not separate depth-versus-normal effects. The LoD2 audit is evaluation-only. SMRF has no LiDAR return structure in the fused GS LAZ, and its current overlay rule preserves any false class-2 result."},
                {"id": "next", "type": "markdown", "body": "## Recommended next bounded check\n\nFreeze both 20k fused clouds and change only Stage-3 classification: current SMRF versus building-class assignment inside the already-authorized shared footprint, with identical Roofer parameters. This readout-only comparison isolates whether SMRF suppresses otherwise usable E4 geometry. Do not retrain, refusion, retune ALS or add another loss in that check; run it only after approval."},
                {"id": "questions", "type": "markdown", "body": "## Further questions\n\n- Does the E4 downstream improvement reproduce on another building with negligible ALS/image change?\n- After removing the SMRF readout confound, does E4 still retain nearly full Roofer coverage?\n- If a later experiment needs attribution, should ALS depth and ALS normal be separated as two approved single-variable arms?"},
            ],
        },
        "snapshot": {"version": 1, "generatedAt": now, "status": "ready", "datasets": {"final": final_card, "highz": highz_rows, "smrf": smrf_rows, "roofer": roofer_rows, "surface": surface_rows, "final_rows": final_rows}},
        "sources": sources,
        "scientific_verdict": None,
    }
    (ROOT / "artifact.json").write_text(json.dumps(artifact, indent=2) + "\n")
    (ROOT / "chart_map.json").write_text(json.dumps({
        "highz": {"segment": "global high-Z", "family": "grouped bar", "dataset": "checkpoint_metrics.csv", "fields": ["completed_updates", "z_gt_650"]},
        "smrf": {"segment": "SMRF classification", "family": "grouped bar", "dataset": "comparison_metrics.json", "fields": ["smrf_ground_fraction", "smrf_building_fraction"]},
        "roofer": {"segment": "downstream Roofer", "family": "grouped bar", "dataset": "comparison_metrics.json", "fields": ["roofer_xy_coverage", "roofer_fscore_0p5m"]},
        "visual_qa": "Static scientific panels were inspected at full report context; all chart values have exact table fallbacks.",
        "scientific_verdict": None,
    }, indent=2) + "\n")

    contract_path = ROOT / "experiment_contract.json"
    contract = json.loads(contract_path.read_text())
    contract.update({"status": "COMPLETE_MEASURED_REPORT_PENDING", "training_experiments_started": 1, "scientific_verdict": None})
    contract_path.write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n")
    notes = f"""# P2-E4-LOCAL-4906982-55V-ALS-PRIOR-v1

One new E4 arm completed from the exact-equal 7k FUSED_VIS_CONF state through 20k. All four checkpoints were evaluated and eight Stage-3 cases (two arms x four checkpoints) completed.

The previous control SMRF ground fraction is {control['smrf_ground_fraction']:.2%}; E4 remains {e4['smrf_ground_fraction']:.2%}. E4 MVS point-to-plane median is {e4['mvs_p2plane_median_m']:.3f} m versus {control['mvs_p2plane_median_m']:.3f} m control. Evaluation-only Roofer 0.5 m F-score is {e4['roofer_fscore_0p5m']:.3f} versus {control['roofer_fscore_0p5m']:.3f}.

The old 937-view E4 raster prior was not reused because 46/55 shapes did not match. Same raw ALS and registration rules were reprojected into the frozen 55 camera/crop geometry; crop, cameras and view roles were not regenerated.

scientific_verdict: null
"""
    (ROOT / "NOTES.md").write_text(notes)
    issues_path = ROOT / "issues.md"
    issues = issues_path.read_text()
    marker = "- SMRF readout confound:"
    if marker not in issues:
        issues += (
            "\n- SMRF readout confound: control/E4 retain 84.39%/82.76% of footprint points as class 2; the overlay preserves class 2, so Roofer sees only the residual class-6 evidence.\n"
            "- Evaluation adapter: fused LAZ stores `normal_x/y/z` while the frozen LoD2 metric helper resolves `NormalX/Y/Z`; a temporary, read-only alias copy was used and no source LAZ was modified.\n"
        )
    if "scientific_verdict: null" not in issues:
        issues += "\nscientific_verdict: null\n"
    issues_path.write_text(issues)
    print(comparison)


if __name__ == "__main__":
    main()
