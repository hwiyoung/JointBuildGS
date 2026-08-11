#!/usr/bin/env python3
"""Merge the new arm with read-only control/raw-normal measurements."""
from __future__ import annotations

import csv
import json
from pathlib import Path


AR = Path("/artifacts/JointBuildGS")
ROOT = AR / "phase-payloads/p2/e3_local_4906982_fused_surface_normal_v1/P2-E3-LOCAL-4906982-FUSED-SURFACE-NORMAL-v1"
RAW_ROOT = AR / "phase-payloads/p2/e3_local_4906982_mvs_normal_ablation_v1/P2-E3-LOCAL-4906982-MVS-NORMAL-ABLATION-v1"
ARMS = ("FUSED_VIS_CONF", "FUSED_VIS_CONF_MVS_NORMAL", "FUSED_VIS_CONF_FUSED_NORMAL")


def csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open() as stream: return list(csv.DictReader(stream))


def find(rows: list[dict], arm: str, step: int = 20000) -> dict:
    return next(row for row in rows if row["arm"] == arm and int(row["completed_updates"]) == step)


def main() -> None:
    new_ckpt = csv_rows(ROOT / "checkpoint_metrics.csv"); raw_ckpt = csv_rows(RAW_ROOT / "checkpoint_metrics.csv")
    new_mvs = json.loads((ROOT / "mvs_surface_audit.json").read_text())["rows"]
    raw_mvs = json.loads((RAW_ROOT / "mvs_surface_audit.json").read_text())["rows"]
    new_lod = json.loads((ROOT / "lod2_fused_evaluation.json").read_text())["rows"]
    raw_lod = json.loads((RAW_ROOT / "lod2_fused_evaluation.json").read_text())["rows"]
    output = []
    for arm in ARMS:
        source_ckpt = raw_ckpt if arm == "FUSED_VIS_CONF_MVS_NORMAL" else new_ckpt
        source_mvs = raw_mvs if arm == "FUSED_VIS_CONF_MVS_NORMAL" else new_mvs
        source_lod = raw_lod if arm == "FUSED_VIS_CONF_MVS_NORMAL" else new_lod
        checkpoint = find(source_ckpt, arm); mvs = find(source_mvs, arm); lod = find(source_lod, arm)
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
    fields = list(output[0])
    with (ROOT / "comparison_metrics.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader(); writer.writerows(output)
    by_arm = {row["arm"]: row for row in output}; raw = by_arm["FUSED_VIS_CONF_MVS_NORMAL"]; fused = by_arm["FUSED_VIS_CONF_FUSED_NORMAL"]
    delta = {key: fused[key] - raw[key] for key in fields if isinstance(raw[key], (int, float)) and not isinstance(raw[key], bool)}
    body = {"schema": "jointbuildgs.p2.e3_local_4906982_fused_surface_normal_v1.comparison.v1", "completed_updates": 20000,
            "rows": output, "primary_delta_fused_normal_minus_raw_normal": delta, "observations_only": True, "scientific_verdict": None}
    (ROOT / "comparison_metrics.json").write_text(json.dumps(body, indent=2, sort_keys=True) + "\n")
    comparison = f"""# Raw/native/fused normal transfer — DEBY_LOD2_4906982

## 20k measurements

| separated measure | depth only | + raw COLMAP normal | + fused surface normal | fused - raw |
|---|---:|---:|---:|---:|
| Z>650 m Gaussian | {output[0]['gaussian_z_gt_650']:,} | {raw['gaussian_z_gt_650']:,} | {fused['gaussian_z_gt_650']:,} | {delta['gaussian_z_gt_650']:+,.0f} |
| Z p99 (m) | {output[0]['gaussian_z_p99_m']:.3f} | {raw['gaussian_z_p99_m']:.3f} | {fused['gaussian_z_p99_m']:.3f} | {delta['gaussian_z_p99_m']:+.3f} |
| Z max (m) | {output[0]['gaussian_z_max_m']:.3f} | {raw['gaussian_z_max_m']:.3f} | {fused['gaussian_z_max_m']:.3f} | {delta['gaussian_z_max_m']:+.3f} |
| held-out PSNR (dB) | {output[0]['heldout_psnr_db']:.3f} | {raw['heldout_psnr_db']:.3f} | {fused['heldout_psnr_db']:.3f} | {delta['heldout_psnr_db']:+.3f} |
| fusion >=2 views | {output[0]['fusion_ge2']:,} | {raw['fusion_ge2']:,} | {fused['fusion_ge2']:,} | {delta['fusion_ge2']:+,.0f} |
| fusion >=3 ratio | {output[0]['fusion_ge3_ratio']:.3f} | {raw['fusion_ge3_ratio']:.3f} | {fused['fusion_ge3_ratio']:.3f} | {delta['fusion_ge3_ratio']:+.3f} |
| MVS p2plane median (m) | {output[0]['mvs_p2plane_median_m']:.4f} | {raw['mvs_p2plane_median_m']:.4f} | {fused['mvs_p2plane_median_m']:.4f} | {delta['mvs_p2plane_median_m']:+.4f} |
| MVS normal median (deg) | {output[0]['mvs_normal_median_deg']:.3f} | {raw['mvs_normal_median_deg']:.3f} | {fused['mvs_normal_median_deg']:.3f} | {delta['mvs_normal_median_deg']:+.3f} |
| MVS wall normal median (deg) | {output[0]['mvs_wall_normal_median_deg']:.3f} | {raw['mvs_wall_normal_median_deg']:.3f} | {fused['mvs_wall_normal_median_deg']:.3f} | {delta['mvs_wall_normal_median_deg']:+.3f} |
| LoD2 abs dZ median (m, eval only) | {output[0]['lod2_abs_dz_median_m']:.3f} | {raw['lod2_abs_dz_median_m']:.3f} | {fused['lod2_abs_dz_median_m']:.3f} | {delta['lod2_abs_dz_median_m']:+.3f} |
| LoD2 normal median (deg, eval only) | {output[0]['lod2_normal_median_deg']:.3f} | {raw['lod2_normal_median_deg']:.3f} | {fused['lod2_normal_median_deg']:.3f} | {delta['lod2_normal_median_deg']:+.3f} |
| Roofer internal RMSE | {output[0]['roofer_internal_rmse']:.3f} | {raw['roofer_internal_rmse']:.3f} | {fused['roofer_internal_rmse']:.3f} | {delta['roofer_internal_rmse']:+.3f} |
| Roofer roof planes | {output[0]['roofer_roof_planes']} | {raw['roofer_roof_planes']} | {fused['roofer_roof_planes']} | {delta['roofer_roof_planes']:+.0f} |

## Observations

- One new arm was trained. The prior depth-only and raw-normal arms are read-only comparators.
- Raw-normal and fused-normal arms have exact-equal model/optimizer/RNG state through 7k, the same depth target/mask, the same normal mask, and the same loss weights/schedules. Only normal values differ after 7k.
- Input target audit: raw-to-fused normal median/p90 disagreement is 15.63/70.90 degrees; native-filtered-to-fused is 7.48/29.90 degrees.
- Measurements and observations only; scientific_verdict remains null.
"""
    (ROOT / "comparison.md").write_text(comparison)
    contract_path = ROOT / "experiment_contract.json"; contract = json.loads(contract_path.read_text())
    contract.update({"status": "COMPLETE_MEASURED_VIEWER_PENDING", "training_experiments_completed": 1, "stage3_cases_completed": 8, "scientific_verdict": None})
    contract_path.write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n")
    print(json.dumps(body, indent=2, sort_keys=True))


if __name__ == "__main__": main()
