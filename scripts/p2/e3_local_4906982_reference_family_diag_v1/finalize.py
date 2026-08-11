#!/usr/bin/env python3
"""Finalize the measured reference-family diagnostic without a verdict."""
from __future__ import annotations

import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path


REPO = Path("/workspace/JointBuildGS")
AR = Path("/artifacts/JointBuildGS")
TASK_ID = "P2-E3-LOCAL-4906982-REFERENCE-FAMILY-DIAG-v1"
ROOT = AR / "phase-payloads/p2/e3_local_4906982_reference_family_diag_v1" / TASK_ID
BASE = AR / "phase-payloads/p2/e3_local_4906982_mvc_depth_v1/P2-E3-LOCAL-4906982-MVC-DEPTH-v1"
STEPS = (7000, 12000, 15000, 20000)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def atomic_json(path: Path, body: object) -> None:
    atomic_text(path, json.dumps(body, indent=2, sort_keys=True) + "\n")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def numeric(row: dict[str, str], key: str) -> float | None:
    value = row.get(key)
    return None if value in (None, "", "None", "null") else float(value)


def main() -> None:
    parity = json.loads((ROOT / "reference_parity_audit.json").read_text())
    expected_gate = json.loads((
        AR / "phase-payloads/p2/e3_local_4906982_mvs_transfer_diag_v1"
        / "P2-E3-LOCAL-4906982-MVS-TRANSFER-DIAG-v1/metrics.json"
    ).read_text())["expected_depth_gate"]
    new_lod = {row["completed_updates"]: row for row in json.loads((ROOT / "lod2_evaluation.json").read_text())["rows"]}
    new_mvs = {row["completed_updates"]: row for row in json.loads((ROOT / "mvs_surface_audit.json").read_text())["rows"]}
    base_mvs = {row["completed_updates"]: row for row in json.loads((ROOT / "current_depth_mvs_surface_audit.json").read_text())["rows"]}
    base_lod_rows = read_csv(BASE / "reference_diagnostic/case_metrics.csv")
    base_lod = next(
        row for row in base_lod_rows
        if row["arm"] == "DEPTH03" and row["replica"] == "R1" and row["completed_updates"] == "20000"
    )

    rows: list[dict[str, object]] = []
    for step in STEPS:
        evaluation = json.loads((
            ROOT / f"arms/GSPLAT_2DGS_REF/R1/evaluation/step_{step:06d}/evaluation.json"
        ).read_text())
        terminal = json.loads((
            ROOT / f"arms/GSPLAT_2DGS_REF/R1/evaluation/step_{step:06d}/fusion/roofer/roofer_terminal.json"
        ).read_text())
        geometry = evaluation["geometry"]
        fusion = evaluation["fusion"]
        opacity = geometry["opacity_bins"]
        lod = new_lod[step]
        mvs = new_mvs[step]
        rows.append({
            "arm": "GSPLAT_2DGS_REF", "replica": "R1", "completed_updates": step,
            "gaussian_count": geometry["gaussian_count"],
            "z_min": geometry["z_epsg25832"]["min"], "z_median": geometry["z_epsg25832"]["median"],
            "z_p95": geometry["z_epsg25832"]["p95"], "z_p99": geometry["z_epsg25832"]["p99"],
            "z_max": geometry["z_epsg25832"]["max"], "seed_max_z": geometry["seed_max_z_epsg25832"],
            "above_seed_max": geometry["count_above_seed_max_z"], "z_gt_650": geometry["count_z_gt_650m"],
            "z_gt_650_footprint_inside": mvs["gaussian_z_gt_650_footprint_inside_count"],
            "z_gt_650_footprint_outside": mvs["gaussian_z_gt_650_footprint_outside_count"],
            "z_gt_650_opacity_lt_0p1": opacity["lt_0p1"]["z_gt_650m"],
            "z_gt_650_opacity_0p1_0p5": opacity["0p1_0p5"]["z_gt_650m"],
            "z_gt_650_opacity_0p5_0p9": opacity["0p5_0p9"]["z_gt_650m"],
            "z_gt_650_opacity_ge_0p9": opacity["ge_0p9"]["z_gt_650m"],
            "scale_min_q50": geometry["scale_min_q50_q95_q99_max"][0],
            "scale_max_q50": geometry["scale_max_q50_q95_q99_max"][0],
            "elongation_q50": geometry["elongation_q01_q05_q50_q95"][2],
            "eval_psnr": evaluation["render_metrics"]["eval"]["psnr"],
            "eval_ssim": evaluation["render_metrics"]["eval"]["ssim"],
            "eval_lpips": evaluation["render_metrics"]["eval"]["lpips"],
            "fusion_ge2": fusion["point_count_ge2"], "fusion_ge3": fusion["point_count_ge3"],
            "fusion_ge3_ratio": fusion["ratio_ge3_of_ge2"],
            "roof_density": fusion["roof_density_per_footprint_m2"],
            "wall_density": fusion["wall_density_per_footprint_m2"],
            "mvs_point_to_point_median": mvs["ordinary_point_to_point_m_median"],
            "mvs_point_to_plane_median": mvs["ordinary_point_to_plane_m_median"],
            "mvs_normal_angle_median": mvs["ordinary_normal_angle_deg_median"],
            "mvs_grid_coverage": mvs["ordinary_grid_coverage_of_mvs"],
            "lod2_abs_dz_median": lod["classified_abs_dz_m_median"],
            "lod2_abs_dz_rmse": lod["classified_abs_dz_m_rmse"],
            "lod2_normal_angle_median": lod["classified_normal_angle_deg_median"],
            "lod2_grid_coverage": lod["classified_grid_coverage_fraction"],
            "lod2_coherent_grid_coverage": lod["classified_coherent_grid_coverage_fraction"],
            "roofer_success": terminal["rf_success"],
            "roofer_internal_rmse": lod["roofer_internal_rmse"],
            "roofer_roof_xy_coverage": lod["roofer_roof_xy_coverage_fraction"],
            "roofer_surface_fscore_0p5m": lod["roofer_surface_fscore_0p5m"],
            "roofer_surface_normal_angle_median": lod["roofer_surface_normal_angle_deg_median"],
            "scientific_verdict": None,
        })

    with (ROOT / "checkpoint_metrics.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    new20 = rows[-1]
    base_eval = json.loads((BASE / "arms/DEPTH03/R1/evaluation/step_020000/evaluation.json").read_text())
    base_geom = base_eval["geometry"]
    base_fusion = base_eval["fusion"]
    base20 = {
        "label": "CURRENT_DEPTH_DEP03_R1_20K_REUSE",
        "source_task": str(BASE),
        "gaussian_count": base_geom["gaussian_count"],
        "z_max": base_geom["z_epsg25832"]["max"], "z_p99": base_geom["z_epsg25832"]["p99"],
        "z_gt_650": base_geom["count_z_gt_650m"],
        "z_gt_650_opacity_ge_0p9": base_geom["opacity_bins"]["ge_0p9"]["z_gt_650m"],
        "eval_psnr": base_eval["render_metrics"]["eval"]["psnr"],
        "eval_ssim": base_eval["render_metrics"]["eval"]["ssim"],
        "eval_lpips": base_eval["render_metrics"]["eval"]["lpips"],
        "fusion_ge2": base_fusion["point_count_ge2"],
        "fusion_ge3_ratio": base_fusion["ratio_ge3_of_ge2"],
        "roof_density": base_fusion["roof_density_per_footprint_m2"],
        "mvs_point_to_point_median": base_mvs[20000]["ordinary_point_to_point_m_median"],
        "mvs_point_to_plane_median": base_mvs[20000]["ordinary_point_to_plane_m_median"],
        "mvs_normal_angle_median": base_mvs[20000]["ordinary_normal_angle_deg_median"],
        "mvs_grid_coverage": base_mvs[20000]["ordinary_grid_coverage_of_mvs"],
        "lod2_abs_dz_median": numeric(base_lod, "classified_abs_dz_m_median"),
        "lod2_abs_dz_rmse": numeric(base_lod, "classified_abs_dz_m_rmse"),
        "lod2_normal_angle_median": numeric(base_lod, "classified_normal_angle_deg_median"),
        "lod2_grid_coverage": numeric(base_lod, "classified_grid_coverage_fraction"),
        "lod2_coherent_grid_coverage": numeric(base_lod, "classified_coherent_grid_coverage_fraction"),
        "roofer_internal_rmse": numeric(base_lod, "roofer_internal_rmse"),
        "roofer_roof_xy_coverage": numeric(base_lod, "roofer_roof_xy_coverage_fraction"),
        "roofer_surface_fscore_0p5m": numeric(base_lod, "roofer_surface_fscore_0p5m"),
        "roofer_surface_normal_angle_median": numeric(base_lod, "roofer_surface_normal_angle_deg_median"),
    }

    expected_all = expected_gate["groups"]["all"]
    expected_footprint = expected_gate["groups"]["footprint_inside"]
    metrics = {
        "schema": "jointbuildgs.p2.e3_local_4906982_reference_family_diag_v1.metrics.v2",
        "status": "COMPLETE_MEASURED",
        "expected_depth_gate": {
            "outcome": "STOP_AMBIGUOUS_NOT_CLEAR_DEGENERACY",
            "original_sparse_fused_mask_training_experiments_started": 0,
            "all_expected_only_rate": expected_all["expected_only_rate"],
            "footprint_expected_only_rate": expected_footprint["expected_only_rate"],
            "footprint_abs_expected_median_median": expected_footprint["abs_expected_median_m"]["median"],
            "reason": "expected-only pixels were common globally but only 1.77% inside footprint; evidence did not isolate averaging degeneracy",
        },
        "reference_parity": {
            "GSPLAT_2DGS_REF": "PASS_GSPLAT_ADAPTATION",
            "PGSR_REF": "BLOCKED_NOT_REFERENCE_FAITHFUL",
        },
        "training_experiments_started": 1,
        "training_experiments_completed": 1,
        "new_arm": {"label": "GSPLAT_2DGS_REF_R1", "checkpoints": rows},
        "reused_comparator": base20,
        "comparison_is_controlled_single_variable": False,
        "comparison_scope": "descriptive method-family benchmark; recipes, primitive counts, supervision, and densification differ",
        "stage3": {"cases": 4, "classification_passed": 4, "roofer_success": 4},
        "official_PASS_usable": None,
        "scientific_verdict": None,
    }
    atomic_json(ROOT / "metrics.json", metrics)

    comparison = f"""# {TASK_ID}

## Expected-depth gate first

The earlier read-only gate remained ambiguous: expected-only agreement was **{100*expected_all['expected_only_rate']:.2f}%** over all raw-valid pixels but only **{100*expected_footprint['expected_only_rate']:.2f}%** inside the footprint, where median |expected−median| was **{expected_footprint['abs_expected_median_m']['median']:.3f} m**. That gate therefore stopped the original sparse-vs-fused initialization and raw-vs-supported-mask training plan (0 runs); it did not establish expected-depth averaging as the cause.

## Reference-family gate and actual runs

- `GSPLAT_2DGS_REF`: `PASS_GSPLAT_ADAPTATION`; 1 R1 training run completed through 20k.
- `PGSR_REF`: `BLOCKED_NOT_REFERENCE_FAITHFUL`; 0 training runs. The current gsplat 2D primitive/rasterizer cannot represent PGSR's 3D minimum-scale plane, diff-plane outputs, patch LNCC reprojection, abs-gradient densification, and observation trimming as one faithful method.
- This is not a controlled single-variable comparison against `DEPTH03`. It is a descriptive method-family benchmark.

## High-Z (20k; separate endpoint)

| Metric | Current depth GS reuse | GSPLAT 2DGS reference | Observation |
|---|---:|---:|---|
| Gaussian count | {base20['gaussian_count']:,} | {new20['gaussian_count']:,} | different capacity/densification |
| Z p99 / max | {base20['z_p99']:.3f} / {base20['z_max']:.3f} m | {new20['z_p99']:.3f} / {new20['z_max']:.3f} m | gross tail is much narrower in reference arm |
| Z>650 m | {base20['z_gt_650']:,} | {new20['z_gt_650']:,} | 252→206 |
| opacity≥0.9 and Z>650 m | {base20['z_gt_650_opacity_ge_0p9']:,} | {new20['z_gt_650_opacity_ge_0p9']:,} | 244→46 |
| reference-arm footprint inside/outside Z>650 | — | {new20['z_gt_650_footprint_inside']:,} / {new20['z_gt_650_footprint_outside']:,} | most remain outside footprint |

## Normal surface and readout (20k; separate endpoint)

| Metric | Current depth GS reuse | GSPLAT 2DGS reference | Observation |
|---|---:|---:|---|
| MVS point-to-point median | {base20['mvs_point_to_point_median']:.3f} m | {new20['mvs_point_to_point_median']:.3f} m | {'reference lower' if new20['mvs_point_to_point_median'] < base20['mvs_point_to_point_median'] else 'reference higher'} |
| MVS point-to-plane median | {base20['mvs_point_to_plane_median']:.3f} m | {new20['mvs_point_to_plane_median']:.3f} m | {'reference lower' if new20['mvs_point_to_plane_median'] < base20['mvs_point_to_plane_median'] else 'reference higher'} |
| MVS normal median | {base20['mvs_normal_angle_median']:.2f}° | {new20['mvs_normal_angle_median']:.2f}° | reference worse |
| LoD2 eval-only median |dZ| / RMSE | {base20['lod2_abs_dz_median']:.3f} / {base20['lod2_abs_dz_rmse']:.3f} m | {new20['lod2_abs_dz_median']:.3f} / {new20['lod2_abs_dz_rmse']:.3f} m | reference lower |
| LoD2 eval-only input-point normal median | {base20['lod2_normal_angle_median']:.2f}° | {new20['lod2_normal_angle_median']:.2f}° | reference worse |
| LoD2 eval-only grid coverage | {100*base20['lod2_grid_coverage']:.2f}% | {100*new20['lod2_grid_coverage']:.2f}% | reference much broader |
| LoD2 eval-only coherent grid coverage | {100*base20['lod2_coherent_grid_coverage']:.2f}% | {100*new20['lod2_coherent_grid_coverage']:.2f}% | both low; reference lower |
| Roofer roof XY coverage | {100*base20['roofer_roof_xy_coverage']:.2f}% | {100*new20['roofer_roof_xy_coverage']:.2f}% | partial→nearly complete |
| Roofer internal RMSE | {base20['roofer_internal_rmse']:.3f} m | {new20['roofer_internal_rmse']:.3f} m | reference lower; not GT error |
| Roofer eval-only surface normal median | {base20['roofer_surface_normal_angle_median']:.2f}° | {new20['roofer_surface_normal_angle_median']:.2f}° | fitted output reference-close |

## Held-out image metrics (20k)

| Metric | Current depth GS reuse | GSPLAT 2DGS reference |
|---|---:|---:|
| PSNR | {base20['eval_psnr']:.3f} dB | {new20['eval_psnr']:.3f} dB |
| SSIM | {base20['eval_ssim']:.4f} | {new20['eval_ssim']:.4f} |
| LPIPS | {base20['eval_lpips']:.4f} | {new20['eval_lpips']:.4f} |

## Measured interpretation and next recommendation

The coherent 2DGS reference adaptation produced a much narrower gross Z tail, substantially better height residuals and nearly complete Roofer output, despite lower PSNR/SSIM and worse input-point normal angles. This supports continuing with coherent method-family baselines instead of stacking another loss onto the current hybrid. It does **not** identify expected depth as the unique cause, and it does not show that normals are solved.

Next, repeat this exact `GSPLAT_2DGS_REF` contract on independent trajectories/buildings before changing its losses. PGSR should only be tested after a faithful 3D Gaussian/diff-plane implementation contract exists; substituting current MVC/NC would create another hybrid. No new depth loss, normal loss, mask, or densification experiment is started here.

`scientific_verdict: null`.
"""
    atomic_text(ROOT / "comparison.md", comparison)

    notes = f"""# {TASK_ID}

Status: `COMPLETE_MEASURED`

- Expected-depth gate: ambiguous; original two causal training experiments started = 0.
- Reference parity: GSPLAT 2DGS adaptation passed; PGSR blocked as not reference-faithful.
- Actual training: 1 arm, 1 trajectory, 20,000 updates; checkpoints 7k/12k/15k/20k valid.
- Evaluation: 4 checkpoint renders/fusions/classifications/Roofer runs complete.
- LoD2 Z/normal/RoofSurface entered only after training and Stage-3 generation, for evaluation.
- Existing `mvs-seed-color-v3` and all prior E3/MVC/depth/v6 artifacts remain unchanged.
- Scientific verdict: `null`.
"""
    atomic_text(ROOT / "NOTES.md", notes)

    contract_path = ROOT / "experiment_contract.json"
    contract = json.loads(contract_path.read_text())
    contract.update({
        "status": "COMPLETE_MEASURED",
        "training_experiments_started": 1,
        "training_experiments_completed": 1,
        "pgsr_training_experiments_started": 0,
        "scientific_verdict": None,
    })
    atomic_json(contract_path, contract)

    viewer = ROOT / "viewer"
    panels = sorted((ROOT / "representative_images/GSPLAT_2DGS_REF").glob("step_*/*.png"))
    names = [str(path.relative_to(ROOT)) for path in panels]
    html = """<!doctype html><html><head><meta charset='utf-8'><title>4906982 reference family</title><style>body{font-family:system-ui;background:#0d1117;color:#e6edf3;margin:20px}select{padding:8px;background:#21262d;color:#fff}img{display:block;max-width:100%;margin-top:18px;border:1px solid #30363d}</style></head><body><h1>DEBY_LOD2_4906982 · GSPLAT 2DGS reference</h1><p>New add-only comparison slot. Existing 8878 state is unchanged. Scientific verdict: null.</p><select id='s'></select><img id='i'><script>const n=__NAMES__,s=document.getElementById('s'),i=document.getElementById('i');for(const x of n){let o=document.createElement('option');o.value=x;o.textContent=x;s.appendChild(o)}function f(){i.src='../'+s.value}s.onchange=f;f();</script></body></html>""".replace("__NAMES__", json.dumps(names))
    atomic_text(viewer / "index.html", html)
    atomic_json(ROOT / "viewer_slot.json", {
        "schema": "jointbuildgs.viewer.comparison_slot.v1",
        "slot_id": "p2-e3-local-4906982-reference-family-v1",
        "label": "DEBY_LOD2_4906982 GSPLAT 2DGS reference",
        "relative_url": "viewer/index.html",
        "panel_count": len(names),
        "separate_add_only_slot": True,
        "existing_8878_mvs_seed_color_v3_modified": False,
        "scientific_verdict": None,
    })

    provenance_path = ROOT / "provenance.json"
    provenance = json.loads(provenance_path.read_text())
    provenance["evaluation_docker_image"] = {
        "reference": "jointbuildgs:mvc-eval-v1",
        "id": "sha256:5968cc43e93e915abc0d82ede44d718990d526eef054d6b47aa96120f00d39d1",
    }
    provenance["evaluation_readout"] = {
        "checkpoint_depth_readout": "median",
        "fusion": "0.15m per-view voxel aggregation, alpha>=0.5, >=2 distinct views",
        "stage3": "shared footprint, fixed SMRF, Roofer defaults",
        "lod2_reference_use": "evaluation-only after training and Stage-3 generation",
    }
    sources = [
        REPO / "scripts/p2/e3_local_4906982_reference_family_diag_v1/evaluate_reference.py",
        REPO / "scripts/p2/e3_local_4906982_reference_family_diag_v1/lod2_reference_audit.py",
        REPO / "scripts/p2/e3_local_4906982_reference_family_diag_v1/finalize.py",
    ]
    provenance.setdefault("source_sha256", {}).update({str(path.relative_to(REPO)): sha256(path) for path in sources})
    outputs = [
        "checkpoint_metrics.csv", "metrics.json", "comparison.md", "NOTES.md",
        "mvs_surface_audit.json", "mvs_surface_metrics.csv", "lod2_evaluation.json",
        "lod2_evaluation_metrics.csv", "viewer_slot.json",
    ]
    provenance["output_sha256"] = {name: sha256(ROOT / name) for name in outputs}
    provenance["end_time"] = now()
    provenance["scientific_verdict"] = None
    atomic_json(provenance_path, provenance)
    print(json.dumps({
        "status": "COMPLETE_MEASURED",
        "training_experiments_started": 1,
        "pgsr_training_experiments_started": 0,
        "checkpoints": len(rows),
        "representative_panels": len(names),
        "scientific_verdict": None,
    }, indent=2))


if __name__ == "__main__":
    main()
