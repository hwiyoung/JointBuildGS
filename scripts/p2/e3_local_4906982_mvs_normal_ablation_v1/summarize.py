#!/usr/bin/env python3
"""Create compact measured comparison tables without a scientific verdict."""
from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path("/artifacts/JointBuildGS/phase-payloads/p2/e3_local_4906982_mvs_normal_ablation_v1/P2-E3-LOCAL-4906982-MVS-NORMAL-ABLATION-v1")
ARMS = ("FUSED_VIS_CONF", "FUSED_VIS_CONF_MVS_NORMAL")


def row(document: dict, arm: str, step: int = 20000) -> dict:
    return next(value for value in document["rows"] if value["arm"] == arm and int(value["completed_updates"]) == step)


def main() -> None:
    with (ROOT / "checkpoint_metrics.csv").open() as stream:
        checkpoint_rows = list(csv.DictReader(stream))
    surface = json.loads((ROOT / "mvs_surface_audit.json").read_text())
    lod2 = json.loads((ROOT / "lod2_fused_evaluation.json").read_text())
    output = []
    for arm in ARMS:
        checkpoint = next(value for value in checkpoint_rows if value["arm"] == arm and int(value["completed_updates"]) == 20000)
        mvs = row(surface, arm); reference = row(lod2, arm)
        output.append({
            "arm": arm,
            "gaussian_count": int(checkpoint["gaussian_count"]), "gaussian_z_gt_650": int(checkpoint["z_gt_650"]),
            "gaussian_z_p99_m": float(checkpoint["z_p99"]), "gaussian_z_max_m": float(checkpoint["z_max"]),
            "gaussian_above_seed_max": int(checkpoint["above_seed_max"]), "heldout_psnr_db": float(checkpoint["eval_psnr"]),
            "fusion_ge2": int(checkpoint["fusion_ge2"]), "fusion_ge3": int(checkpoint["fusion_ge3"]),
            "fusion_ge3_ratio": float(checkpoint["fusion_ge3_ratio"]), "roof_density": float(checkpoint["roof_density"]),
            "wall_density": float(checkpoint["wall_density"]), "roofer_success": checkpoint["roofer_success"].lower() == "true",
            "roofer_internal_rmse": float(checkpoint["roofer_rmse_lod22"]),
            "mvs_p2plane_median_m": float(mvs["ordinary_point_to_plane_m_median"]),
            "mvs_normal_median_deg": float(mvs["ordinary_normal_angle_deg_median"]),
            "mvs_wall_p2plane_median_m": float(mvs["wall_point_to_plane_m_median"]),
            "mvs_wall_normal_median_deg": float(mvs["wall_normal_angle_deg_median"]),
            "mvs_grid_coverage": float(mvs["ordinary_grid_coverage_of_mvs"]),
            "lod2_abs_dz_median_m": float(reference["abs_dz_m_median"]),
            "lod2_abs_dz_rmse_m": float(reference["abs_dz_m_rmse"]),
            "lod2_normal_median_deg": float(reference["normal_angle_deg_median"]),
            "lod2_normal_p95_deg": float(reference["normal_angle_deg_p95"]),
            "lod2_coherent_grid_coverage": float(reference["coherent_grid_coverage_fraction"]),
            "scientific_verdict": None,
        })
    fields = list(output[0])
    with (ROOT / "comparison_metrics.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader(); writer.writerows(output)
    control, target = output
    deltas = {key: target[key] - control[key] for key in fields if isinstance(control[key], (int, float)) and not isinstance(control[key], bool)}
    body = {"schema": "jointbuildgs.p2.e3_local_4906982_mvs_normal_ablation_v1.comparison.v1", "completed_updates": 20000,
            "rows": output, "delta_mvs_normal_minus_control": deltas, "observations_only": True, "scientific_verdict": None}
    (ROOT / "comparison_metrics.json").write_text(json.dumps(body, indent=2, sort_keys=True) + "\n")
    comparison = f"""# MVS depth versus MVS depth+normal — DEBY_LOD2_4906982

## Measured at 20k

| 분리 평가 | FUSED_VIS_CONF | + supported MVS normal | 변화 |
|---|---:|---:|---:|
| Z>650 m Gaussian | {control['gaussian_z_gt_650']:,} | {target['gaussian_z_gt_650']:,} | {deltas['gaussian_z_gt_650']:+,.0f} |
| Z p99 (m) | {control['gaussian_z_p99_m']:.3f} | {target['gaussian_z_p99_m']:.3f} | {deltas['gaussian_z_p99_m']:+.3f} |
| Z max (m) | {control['gaussian_z_max_m']:.3f} | {target['gaussian_z_max_m']:.3f} | {deltas['gaussian_z_max_m']:+.3f} |
| held-out PSNR (dB) | {control['heldout_psnr_db']:.3f} | {target['heldout_psnr_db']:.3f} | {deltas['heldout_psnr_db']:+.3f} |
| fusion >=2 views | {control['fusion_ge2']:,} | {target['fusion_ge2']:,} | {deltas['fusion_ge2']:+,.0f} |
| MVS p2plane median (m) | {control['mvs_p2plane_median_m']:.4f} | {target['mvs_p2plane_median_m']:.4f} | {deltas['mvs_p2plane_median_m']:+.4f} |
| MVS normal median (deg) | {control['mvs_normal_median_deg']:.3f} | {target['mvs_normal_median_deg']:.3f} | {deltas['mvs_normal_median_deg']:+.3f} |
| MVS wall normal median (deg) | {control['mvs_wall_normal_median_deg']:.3f} | {target['mvs_wall_normal_median_deg']:.3f} | {deltas['mvs_wall_normal_median_deg']:+.3f} |
| LoD2 abs dZ median (m, eval only) | {control['lod2_abs_dz_median_m']:.3f} | {target['lod2_abs_dz_median_m']:.3f} | {deltas['lod2_abs_dz_median_m']:+.3f} |
| LoD2 normal median (deg, eval only) | {control['lod2_normal_median_deg']:.3f} | {target['lod2_normal_median_deg']:.3f} | {deltas['lod2_normal_median_deg']:+.3f} |
| Roofer internal RMSE | {control['roofer_internal_rmse']:.3f} | {target['roofer_internal_rmse']:.3f} | {deltas['roofer_internal_rmse']:+.3f} |

## Observations

- 한 개의 새 학습 arm만 실행했다. 7k 상태는 control과 exact-equal이며 첫 학습 차이는 supported MVS normal이다.
- normal 추가 후 Z>650 m 수와 Z p99는 감소했지만 Z max와 seed-max 초과 수는 개선되지 않았다.
- held-out RGB와 multiview fusion point 수는 증가했다.
- filtered OpenMVS 대비 일반 표면 위치·normal 중앙값은 소폭 악화했고, wall 위치·normal 중앙값은 개선했다.
- evaluation-only LoD2 기준 height 중앙값은 사실상 동일하고 normal 중앙값 및 RMSE는 악화했다.
- Roofer는 양쪽 모두 성공했지만 새 normal arm의 내부 RMSE가 더 컸다.
- scientific_verdict: null
"""
    (ROOT / "comparison.md").write_text(comparison)
    contract_path = ROOT / "experiment_contract.json"; contract = json.loads(contract_path.read_text())
    contract.update({"status": "COMPLETE_MEASURED_VIEWER_PENDING", "training_experiments_completed": 1, "stage3_cases_completed": 8, "scientific_verdict": None})
    contract_path.write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n")
    print(json.dumps(body, indent=2, sort_keys=True))


if __name__ == "__main__": main()
