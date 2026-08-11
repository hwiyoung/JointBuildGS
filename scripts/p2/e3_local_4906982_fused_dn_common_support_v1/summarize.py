#!/usr/bin/env python3
"""Compare depth-only, fixed raw-valid normal mask, and common fused support."""
from __future__ import annotations

import csv
import json
from pathlib import Path


AR = Path("/artifacts/JointBuildGS")
ROOT = AR / "phase-payloads/p2/e3_local_4906982_fused_dn_common_support_v1/P2-E3-LOCAL-4906982-FUSED-DN-COMMON-SUPPORT-v1"
FIXED = AR / "phase-payloads/p2/e3_local_4906982_fused_surface_normal_v1/P2-E3-LOCAL-4906982-FUSED-SURFACE-NORMAL-v1"
ARMS = ("FUSED_VIS_CONF", "FUSED_VIS_CONF_FUSED_NORMAL", "FUSED_VIS_CONF_FUSED_NORMAL_COMMON_SUPPORT")


def csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open() as stream:
        return list(csv.DictReader(stream))


def find(rows: list[dict], arm: str, step: int = 20000) -> dict:
    return next(row for row in rows if row["arm"] == arm and int(row["completed_updates"]) == step)


def main() -> None:
    new_ckpt = csv_rows(ROOT / "checkpoint_metrics.csv"); fixed_ckpt = csv_rows(FIXED / "checkpoint_metrics.csv")
    new_mvs = json.loads((ROOT / "mvs_surface_audit.json").read_text())["rows"]
    fixed_mvs = json.loads((FIXED / "mvs_surface_audit.json").read_text())["rows"]
    new_lod = json.loads((ROOT / "lod2_fused_evaluation.json").read_text())["rows"]
    fixed_lod = json.loads((FIXED / "lod2_fused_evaluation.json").read_text())["rows"]
    output = []
    for arm in ARMS:
        external = arm == "FUSED_VIS_CONF_FUSED_NORMAL"
        checkpoint = find(fixed_ckpt if external else new_ckpt, arm)
        mvs = find(fixed_mvs if external else new_mvs, arm)
        lod = find(fixed_lod if external else new_lod, arm)
        output.append({
            "arm": arm, "gaussian_count": int(checkpoint["gaussian_count"]), "gaussian_z_gt_650": int(checkpoint["z_gt_650"]),
            "gaussian_z_p99_m": float(checkpoint["z_p99"]), "gaussian_z_max_m": float(checkpoint["z_max"]),
            "gaussian_above_seed_max": int(checkpoint["above_seed_max"]), "heldout_psnr_db": float(checkpoint["eval_psnr"]),
            "fusion_ge2": int(checkpoint["fusion_ge2"]), "fusion_ge3": int(checkpoint["fusion_ge3"]),
            "fusion_ge3_ratio": float(checkpoint["fusion_ge3_ratio"]), "roof_density": float(checkpoint["roof_density"]),
            "wall_density": float(checkpoint["wall_density"]), "roofer_success": checkpoint["roofer_success"].lower() == "true",
            "roofer_internal_rmse": float(checkpoint["roofer_rmse_lod22"]), "roofer_roof_planes": int(checkpoint["roofer_roof_planes"]),
            "mvs_p2plane_median_m": float(mvs["ordinary_point_to_plane_m_median"]), "mvs_normal_median_deg": float(mvs["ordinary_normal_angle_deg_median"]),
            "mvs_wall_p2plane_median_m": float(mvs["wall_point_to_plane_m_median"]), "mvs_wall_normal_median_deg": float(mvs["wall_normal_angle_deg_median"]),
            "mvs_grid_coverage": float(mvs["ordinary_grid_coverage_of_mvs"]), "lod2_abs_dz_median_m": float(lod["abs_dz_m_median"]),
            "lod2_abs_dz_rmse_m": float(lod["abs_dz_m_rmse"]), "lod2_normal_median_deg": float(lod["normal_angle_deg_median"]),
            "lod2_normal_p95_deg": float(lod["normal_angle_deg_p95"]), "lod2_coherent_grid_coverage": float(lod["coherent_grid_coverage_fraction"]),
            "scientific_verdict": None,
        })
    with (ROOT / "comparison_metrics.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(output[0])); writer.writeheader(); writer.writerows(output)
    rows = {row["arm"]: row for row in output}; fixed = rows[ARMS[1]]; common = rows[ARMS[2]]
    delta = {key: common[key] - fixed[key] for key in fixed if isinstance(fixed[key], (int, float)) and not isinstance(fixed[key], bool)}
    definition = json.loads((ROOT / "fused_dn_common_support_target_definition.json").read_text())
    body = {"schema": "jointbuildgs.p2.e3_local_4906982_fused_dn_common_support_v1.comparison.v1", "completed_updates": 20000,
            "rows": output, "primary_delta_common_support_minus_fixed_raw_valid_mask": delta,
            "mask_pixels": {"fixed_raw_valid": definition["prior_raw_normal_target_valid_pixels"], "common_fused_support": definition["target_valid_pixels"]},
            "observations_only": True, "scientific_verdict": None}
    (ROOT / "comparison_metrics.json").write_text(json.dumps(body, indent=2, sort_keys=True) + "\n")
    comparison = f"""# Fused depth/normal common-support comparison — DEBY_LOD2_4906982

## 20k measurements

| separated measure | depth only | fused N on raw-valid mask | fused N on common support | common - fixed |
|---|---:|---:|---:|---:|
| normal supervised pixels | 0 | {definition['prior_raw_normal_target_valid_pixels']:,} | {definition['target_valid_pixels']:,} | {definition['target_valid_pixels']-definition['prior_raw_normal_target_valid_pixels']:+,} |
| Z>650 m Gaussian | {output[0]['gaussian_z_gt_650']:,} | {fixed['gaussian_z_gt_650']:,} | {common['gaussian_z_gt_650']:,} | {delta['gaussian_z_gt_650']:+,.0f} |
| Z p99 (m) | {output[0]['gaussian_z_p99_m']:.3f} | {fixed['gaussian_z_p99_m']:.3f} | {common['gaussian_z_p99_m']:.3f} | {delta['gaussian_z_p99_m']:+.3f} |
| Z max (m) | {output[0]['gaussian_z_max_m']:.3f} | {fixed['gaussian_z_max_m']:.3f} | {common['gaussian_z_max_m']:.3f} | {delta['gaussian_z_max_m']:+.3f} |
| held-out PSNR (dB) | {output[0]['heldout_psnr_db']:.3f} | {fixed['heldout_psnr_db']:.3f} | {common['heldout_psnr_db']:.3f} | {delta['heldout_psnr_db']:+.3f} |
| fusion >=2 views | {output[0]['fusion_ge2']:,} | {fixed['fusion_ge2']:,} | {common['fusion_ge2']:,} | {delta['fusion_ge2']:+,.0f} |
| fusion >=3 ratio | {output[0]['fusion_ge3_ratio']:.3f} | {fixed['fusion_ge3_ratio']:.3f} | {common['fusion_ge3_ratio']:.3f} | {delta['fusion_ge3_ratio']:+.3f} |
| MVS p2plane median (m) | {output[0]['mvs_p2plane_median_m']:.4f} | {fixed['mvs_p2plane_median_m']:.4f} | {common['mvs_p2plane_median_m']:.4f} | {delta['mvs_p2plane_median_m']:+.4f} |
| MVS normal median (deg) | {output[0]['mvs_normal_median_deg']:.3f} | {fixed['mvs_normal_median_deg']:.3f} | {common['mvs_normal_median_deg']:.3f} | {delta['mvs_normal_median_deg']:+.3f} |
| LoD2 abs dZ RMSE (m, eval only) | {output[0]['lod2_abs_dz_rmse_m']:.3f} | {fixed['lod2_abs_dz_rmse_m']:.3f} | {common['lod2_abs_dz_rmse_m']:.3f} | {delta['lod2_abs_dz_rmse_m']:+.3f} |
| LoD2 normal median (deg, eval only) | {output[0]['lod2_normal_median_deg']:.3f} | {fixed['lod2_normal_median_deg']:.3f} | {common['lod2_normal_median_deg']:.3f} | {delta['lod2_normal_median_deg']:+.3f} |
| Roofer internal RMSE | {output[0]['roofer_internal_rmse']:.3f} | {fixed['roofer_internal_rmse']:.3f} | {common['roofer_internal_rmse']:.3f} | {delta['roofer_internal_rmse']:+.3f} |

## Observations

- One new arm was trained. Depth-only and fixed-mask fused-normal arms are read-only comparators.
- The fused-normal target values are unchanged; only normal mask coverage expands to the exact depth support.
- Measurements and observations only; scientific_verdict remains null.
"""
    (ROOT / "comparison.md").write_text(comparison)
    contract_path = ROOT / "experiment_contract.json"; contract = json.loads(contract_path.read_text())
    contract.update({"status": "COMPLETE_MEASURED_VIEWER_PENDING", "training_experiments_completed": 1, "stage3_cases_completed": 8, "scientific_verdict": None})
    contract_path.write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n")
    print(json.dumps(body, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
