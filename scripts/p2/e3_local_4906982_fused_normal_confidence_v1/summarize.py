#!/usr/bin/env python3
"""Compare depth-only and three fused-normal mask designs at 20k."""
from __future__ import annotations

import csv
import json
from pathlib import Path


AR = Path("/artifacts/JointBuildGS")
ROOT = AR / "phase-payloads/p2/e3_local_4906982_fused_normal_confidence_v1/P2-E3-LOCAL-4906982-FUSED-NORMAL-CONFIDENCE-v1"
FIXED = AR / "phase-payloads/p2/e3_local_4906982_fused_surface_normal_v1/P2-E3-LOCAL-4906982-FUSED-SURFACE-NORMAL-v1"
COMMON = AR / "phase-payloads/p2/e3_local_4906982_fused_dn_common_support_v1/P2-E3-LOCAL-4906982-FUSED-DN-COMMON-SUPPORT-v1"
ARMS = ("FUSED_VIS_CONF", "FUSED_VIS_CONF_FUSED_NORMAL", "FUSED_VIS_CONF_FUSED_NORMAL_COMMON_SUPPORT", "FUSED_VIS_CONF_FUSED_NORMAL_CONFIDENCE")
ROOT_FOR = {ARMS[0]: ROOT, ARMS[1]: FIXED, ARMS[2]: COMMON, ARMS[3]: ROOT}


def csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open() as stream:
        return list(csv.DictReader(stream))


def find(rows: list[dict], arm: str, step: int = 20000) -> dict:
    return next(row for row in rows if row["arm"] == arm and int(row["completed_updates"]) == step)


def main() -> None:
    roofer_surface = json.loads((ROOT / "roofer_surface_evaluation.json").read_text())["rows"]
    cache = {}
    for root in set(ROOT_FOR.values()):
        cache[root] = {
            "checkpoint": csv_rows(root / "checkpoint_metrics.csv"),
            "mvs": json.loads((root / "mvs_surface_audit.json").read_text())["rows"],
            "lod2": json.loads((root / "lod2_fused_evaluation.json").read_text())["rows"],
        }
    output = []
    for arm in ARMS:
        data = cache[ROOT_FOR[arm]]; checkpoint = find(data["checkpoint"], arm); mvs = find(data["mvs"], arm); lod = find(data["lod2"], arm); roof = find(roofer_surface, arm)
        output.append({
            "arm": arm, "gaussian_count": int(checkpoint["gaussian_count"]), "gaussian_z_gt_650": int(checkpoint["z_gt_650"]),
            "gaussian_z_p99_m": float(checkpoint["z_p99"]), "gaussian_z_max_m": float(checkpoint["z_max"]),
            "gaussian_above_seed_max": int(checkpoint["above_seed_max"]), "heldout_psnr_db": float(checkpoint["eval_psnr"]),
            "fusion_ge2": int(checkpoint["fusion_ge2"]), "fusion_ge3": int(checkpoint["fusion_ge3"]), "fusion_ge3_ratio": float(checkpoint["fusion_ge3_ratio"]),
            "roof_density": float(checkpoint["roof_density"]), "wall_density": float(checkpoint["wall_density"]),
            "roofer_success": checkpoint["roofer_success"].lower() == "true", "roofer_internal_rmse": float(checkpoint["roofer_rmse_lod22"]),
            "roofer_roof_planes": int(checkpoint["roofer_roof_planes"]),
            "roofer_roof_xy_coverage": float(roof["roofer_roof_xy_coverage_fraction"]),
            "roofer_surface_fscore_0p5m": float(roof["roofer_surface_fscore_0p5m"]),
            "roofer_surface_normal_median_deg": float(roof["roofer_surface_normal_angle_deg_median"]),
            "roofer_roof_surface_count": int(roof["roofer_roof_surface_count"]),
            "mvs_p2plane_median_m": float(mvs["ordinary_point_to_plane_m_median"]), "mvs_normal_median_deg": float(mvs["ordinary_normal_angle_deg_median"]),
            "mvs_wall_p2plane_median_m": float(mvs["wall_point_to_plane_m_median"]), "mvs_wall_normal_median_deg": float(mvs["wall_normal_angle_deg_median"]),
            "mvs_grid_coverage": float(mvs["ordinary_grid_coverage_of_mvs"]), "lod2_abs_dz_median_m": float(lod["abs_dz_m_median"]),
            "lod2_abs_dz_rmse_m": float(lod["abs_dz_m_rmse"]), "lod2_normal_median_deg": float(lod["normal_angle_deg_median"]),
            "lod2_normal_p95_deg": float(lod["normal_angle_deg_p95"]), "lod2_coherent_grid_coverage": float(lod["coherent_grid_coverage_fraction"]),
            "scientific_verdict": None,
        })
    with (ROOT / "comparison_metrics.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(output[0])); writer.writeheader(); writer.writerows(output)
    rows = {row["arm"]: row for row in output}; depth, fixed, common, confidence = (rows[arm] for arm in ARMS)
    numeric = lambda right, left: {key: right[key] - left[key] for key in left if isinstance(left[key], (int, float)) and not isinstance(left[key], bool)}
    definition = json.loads((ROOT / "fused_normal_confidence_definition.json").read_text())
    body = {
        "schema": "jointbuildgs.p2.e3_local_4906982_fused_normal_confidence_v1.comparison.v1", "completed_updates": 20000,
        "rows": output, "primary_delta_confidence_minus_common_support": numeric(confidence, common),
        "context_delta_confidence_minus_depth_only": numeric(confidence, depth),
        "mask_pixels": {"depth": definition["depth_mask_pixels"], "previous_fixed": definition["previous_normal_mask_pixels"], "common_support": definition["depth_mask_pixels"], "confidence": definition["target_valid_pixels"]},
        "observations_only": True, "scientific_verdict": None,
    }
    (ROOT / "comparison_metrics.json").write_text(json.dumps(body, indent=2, sort_keys=True) + "\n")
    d_common = body["primary_delta_confidence_minus_common_support"]
    report = f"""# Confidence-gated fused-normal comparison — DEBY_LOD2_4906982

## Mask measurements frozen before training

| mask | pixels | fraction of depth |
|---|---:|---:|
| depth | {definition['depth_mask_pixels']:,} | 100.0% |
| previous fused-normal raw-valid intersection | {definition['previous_normal_mask_pixels']:,} | {100*definition['previous_normal_mask_pixels']/definition['depth_mask_pixels']:.1f}% |
| common-support fused normal | {definition['depth_mask_pixels']:,} | 100.0% |
| confidence-gated fused normal | {definition['target_valid_pixels']:,} | {100*definition['new_fraction_of_depth']:.1f}% |

## 20k measurements

| separated measure | depth only | fixed mask | common support | confidence gate | confidence - common |
|---|---:|---:|---:|---:|---:|
| Z>650 m Gaussian | {depth['gaussian_z_gt_650']:,} | {fixed['gaussian_z_gt_650']:,} | {common['gaussian_z_gt_650']:,} | {confidence['gaussian_z_gt_650']:,} | {d_common['gaussian_z_gt_650']:+,.0f} |
| Z p99 (m) | {depth['gaussian_z_p99_m']:.3f} | {fixed['gaussian_z_p99_m']:.3f} | {common['gaussian_z_p99_m']:.3f} | {confidence['gaussian_z_p99_m']:.3f} | {d_common['gaussian_z_p99_m']:+.3f} |
| Z max (m) | {depth['gaussian_z_max_m']:.3f} | {fixed['gaussian_z_max_m']:.3f} | {common['gaussian_z_max_m']:.3f} | {confidence['gaussian_z_max_m']:.3f} | {d_common['gaussian_z_max_m']:+.3f} |
| held-out PSNR (dB) | {depth['heldout_psnr_db']:.3f} | {fixed['heldout_psnr_db']:.3f} | {common['heldout_psnr_db']:.3f} | {confidence['heldout_psnr_db']:.3f} | {d_common['heldout_psnr_db']:+.3f} |
| fusion >=2 views | {depth['fusion_ge2']:,} | {fixed['fusion_ge2']:,} | {common['fusion_ge2']:,} | {confidence['fusion_ge2']:,} | {d_common['fusion_ge2']:+,.0f} |
| MVS p2plane median (m) | {depth['mvs_p2plane_median_m']:.4f} | {fixed['mvs_p2plane_median_m']:.4f} | {common['mvs_p2plane_median_m']:.4f} | {confidence['mvs_p2plane_median_m']:.4f} | {d_common['mvs_p2plane_median_m']:+.4f} |
| MVS normal median (deg) | {depth['mvs_normal_median_deg']:.3f} | {fixed['mvs_normal_median_deg']:.3f} | {common['mvs_normal_median_deg']:.3f} | {confidence['mvs_normal_median_deg']:.3f} | {d_common['mvs_normal_median_deg']:+.3f} |
| LoD2 dZ RMSE (m, eval only) | {depth['lod2_abs_dz_rmse_m']:.3f} | {fixed['lod2_abs_dz_rmse_m']:.3f} | {common['lod2_abs_dz_rmse_m']:.3f} | {confidence['lod2_abs_dz_rmse_m']:.3f} | {d_common['lod2_abs_dz_rmse_m']:+.3f} |
| LoD2 normal median (deg, eval only) | {depth['lod2_normal_median_deg']:.3f} | {fixed['lod2_normal_median_deg']:.3f} | {common['lod2_normal_median_deg']:.3f} | {confidence['lod2_normal_median_deg']:.3f} | {d_common['lod2_normal_median_deg']:+.3f} |
| Roofer internal RMSE | {depth['roofer_internal_rmse']:.3f} | {fixed['roofer_internal_rmse']:.3f} | {common['roofer_internal_rmse']:.3f} | {confidence['roofer_internal_rmse']:.3f} | {d_common['roofer_internal_rmse']:+.3f} |
| Roofer roof XY coverage | {depth['roofer_roof_xy_coverage']:.3f} | {fixed['roofer_roof_xy_coverage']:.3f} | {common['roofer_roof_xy_coverage']:.3f} | {confidence['roofer_roof_xy_coverage']:.3f} | {d_common['roofer_roof_xy_coverage']:+.3f} |
| Roofer surface F-score @ 0.5 m | {depth['roofer_surface_fscore_0p5m']:.3f} | {fixed['roofer_surface_fscore_0p5m']:.3f} | {common['roofer_surface_fscore_0p5m']:.3f} | {confidence['roofer_surface_fscore_0p5m']:.3f} | {d_common['roofer_surface_fscore_0p5m']:+.3f} |
| Roofer normal median (deg) | {depth['roofer_surface_normal_median_deg']:.3f} | {fixed['roofer_surface_normal_median_deg']:.3f} | {common['roofer_surface_normal_median_deg']:.3f} | {confidence['roofer_surface_normal_median_deg']:.3f} | {d_common['roofer_surface_normal_median_deg']:+.3f} |

## Observations

- One new confidence-gated arm was trained. The other three arms are read-only comparators.
- Normal target values, normal loss and all depth supervision are unchanged; only the frozen normal mask changes in the primary comparison.
- LoD2 geometry was evaluation-only. Measurements and observations only; scientific_verdict remains null.
"""
    (ROOT / "comparison.md").write_text(report)
    contract_path = ROOT / "experiment_contract.json"; contract = json.loads(contract_path.read_text())
    contract.update({"status": "COMPLETE_MEASURED_VIEWER_PENDING", "training_experiments_completed": 1, "stage3_cases_completed": 8, "scientific_verdict": None})
    contract_path.write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n")
    print(json.dumps(body, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
