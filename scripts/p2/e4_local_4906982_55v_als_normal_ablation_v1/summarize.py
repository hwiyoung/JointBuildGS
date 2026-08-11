#!/usr/bin/env python3
"""Seal the three-arm ALS-normal ablation measurements without a scientific verdict."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone


ARTIFACT_ROOT = Path("/artifacts/JointBuildGS")
TASK_ID = "P2-E4-LOCAL-4906982-55V-ALS-NORMAL-ABLATION-v1"
TASK_ROOT = ARTIFACT_ROOT / "phase-payloads/p2/e4_local_4906982_55v_als_normal_ablation_v1" / TASK_ID
FULL_ROOT = ARTIFACT_ROOT / "phase-payloads/p2/e4_local_4906982_55v_als_prior_v1/P2-E4-LOCAL-4906982-55V-ALS-PRIOR-v1"
VIEWER_DATA = ARTIFACT_ROOT / "phase-payloads/p2/e3_local_review_v1/P2-E3-LOCAL-4906982-INPUT-REVIEW-v3/viewer/e4-normal-ablation-roofer-v1/data"
ARMS = (
    ("FUSED_VIS_CONF", FULL_ROOT, "FUSED_VIS_CONF", "lod2_evaluation_fused_vis_conf.json"),
    ("ALS_DEPTH_ONLY", TASK_ROOT, "ALS_DEPTH_ONLY", "lod2_evaluation_als_depth_only.json"),
    ("E4_ALS_PRIOR_ONLY", FULL_ROOT, "E4_ALS_PRIOR_ONLY", "lod2_evaluation_e4_als_prior_only.json"),
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def row(path: Path, arm: str, step: int = 20000) -> dict:
    return next(value for value in json.loads(path.read_text())["rows"] if value.get("arm") == arm and value.get("completed_updates") == step)


def aggregate(root: Path, arm: str, step: int = 20000) -> dict:
    return json.loads((root / "metrics.json").read_text())["aggregates"][str(step)][arm]


def delta(right: dict, left: dict, keys: list[str]) -> dict:
    return {key: right[key] - left[key] for key in keys}


def f(value, digits=3) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def main() -> None:
    rows = []
    for visible_arm, root, source_arm, roofer_name in ARMS:
        mvs = row(root / "mvs_surface_audit.json", source_arm)
        lod2 = row(root / "lod2_fused_evaluation.json", source_arm)
        roofer = row(root / roofer_name, source_arm)
        metrics = aggregate(root, source_arm)
        solid = json.loads((VIEWER_DATA / f"{visible_arm}_020000.json").read_text())["metrics"]
        rows.append({
            "arm": visible_arm, "completed_updates": 20000,
            "gaussian_count": int(metrics["gaussian_count"]["mean"]), "gaussian_z_gt_650_count": int(metrics["z_gt_650"]["mean"]),
            "gaussian_z_max_m": metrics["z_max"]["mean"], "gaussian_z_p99_m": metrics["z_p99"]["mean"],
            "mvs_p2plane_median_m": mvs["ordinary_point_to_plane_m_median"], "mvs_normal_median_deg": mvs["ordinary_normal_angle_deg_median"],
            "mvs_grid_coverage": mvs["ordinary_grid_coverage_of_mvs"], "lod2_abs_height_median_m": lod2["abs_dz_m_median"],
            "lod2_normal_median_deg": lod2["normal_angle_deg_median"], "lod2_grid_coverage": lod2["grid_coverage_fraction"],
            "fusion_point_count": lod2["point_count"], "fusion_z_gt_650_count": lod2["z_gt_650_count"],
            "roofer_roof_xy_coverage": roofer["roofer_roof_xy_coverage_fraction"], "roofer_fscore_0p5m": roofer["roofer_surface_fscore_0p5m"],
            "roofer_internal_rmse_m": roofer["roofer_internal_rmse"], "roofer_reference_normal_median_deg": roofer["roofer_surface_normal_angle_deg_median"],
            "roofer_roof_surface_count": roofer["roofer_roof_surface_count"], "roofer_vertex_z_gt_650_count": roofer["roofer_vertex_z_gt_650_count"],
            "roofer_ground_z_m": solid["roofer_ground_z"], "reference_ground_z_m": solid["reference_ground_z"],
            "roofer_ground_z_error_m": solid["roofer_ground_z_error"],
            "roofer_exterior_wall_height_median_m": solid["roofer_exterior_wall_height_median"],
            "roofer_exterior_wall_height_max_m": solid["roofer_exterior_wall_height_max"],
            "reference_building_height_m": solid["reference_building_height"],
            "scientific_verdict": None,
        })
    by_arm = {value["arm"]: value for value in rows}
    keys = [key for key in rows[0] if key not in ("arm", "completed_updates", "scientific_verdict")]
    effects = {
        "als_depth_package_minus_control": delta(by_arm["ALS_DEPTH_ONLY"], by_arm["FUSED_VIS_CONF"], keys),
        "als_normal_addition_full_e4_minus_depth_only": delta(by_arm["E4_ALS_PRIOR_ONLY"], by_arm["ALS_DEPTH_ONLY"], keys),
    }
    body = {
        "schema": "jointbuildgs.p2.e4_local_4906982_55v_als_normal_ablation_v1.three_arm_metrics.v1",
        "task_id": TASK_ID, "building_id": "DEBY_LOD2_4906982", "completed_updates": 20000,
        "training_experiments_started": 1, "training_experiments_completed": 1,
        "comparison_contract": {
            "control_vs_depth_only": "ALS depth package effect; full-E4 is not involved",
            "depth_only_vs_full_e4": "ALS normal addition effect; normal weight is the only scientific config difference",
            "exact_equal_at_7000": True,
        },
        "rows": rows, "effects": effects,
        "observations": [
            "ALS depth-only did not reproduce full-E4 Roofer roof-surface recovery.",
            "Adding ALS normal to the same ALS depth package coincided with near-complete Roofer roof XY coverage and lower Roofer roof reference-normal error.",
            "The roof-only recovery does not extend to the full LoD2 solid: every arm placed Roofer ground approximately 24 m above the evaluation reference and produced shallow exterior walls.",
            "High-Z Gaussians remained in all arms and all were outside the footprint at 20k; Roofer vertices above 650 m were zero in all arms.",
            "Full-E4 fused ordinary-surface location and input-normal summary were not uniformly better than depth-only; the roof-output jump therefore cannot be reduced to point-height or input-normal median alone.",
        ],
        "limitations": ["single building, seed, and continuation", "technical-development comparison, not confirmatory inference", "LoD2 reference evaluation-only after training", "Roofer ground-height/classification failure confounds full-solid usability"],
        "official_PASS_usable": None, "scientific_verdict": None,
    }
    (TASK_ROOT / "three_arm_metrics.json").write_text(json.dumps(body, indent=2, sort_keys=True) + "\n")
    with (TASK_ROOT / "three_arm_metrics.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)

    highz = "\n".join(f"| {r['arm']} | {r['gaussian_z_gt_650_count']} | {f(r['gaussian_z_p99_m'],2)} | {f(r['gaussian_z_max_m'],2)} | {r['fusion_z_gt_650_count']} | {r['roofer_vertex_z_gt_650_count']} |" for r in rows)
    surface = "\n".join(f"| {r['arm']} | {f(r['mvs_p2plane_median_m'])} | {f(r['mvs_normal_median_deg'],2)} | {f(r['lod2_abs_height_median_m'])} | {f(r['lod2_normal_median_deg'],2)} | {100*r['lod2_grid_coverage']:.2f}% |" for r in rows)
    roof = "\n".join(f"| {r['arm']} | {100*r['roofer_roof_xy_coverage']:.2f}% | {f(r['roofer_fscore_0p5m'])} | {f(r['roofer_internal_rmse_m'],2)} | {f(r['roofer_reference_normal_median_deg'],2)}° | {r['roofer_roof_surface_count']} |" for r in rows)
    solid = "\n".join(f"| {r['arm']} | {f(r['roofer_ground_z_m'],2)} | {f(r['reference_ground_z_m'],2)} | {f(r['roofer_ground_z_error_m'],2)} | {f(r['roofer_exterior_wall_height_median_m'],2)} | {f(r['roofer_exterior_wall_height_max_m'],2)} | {f(r['reference_building_height_m'],2)} |" for r in rows)
    comparison = f"""# {TASK_ID}

## 측정 질문

55-view E4의 Roofer 회복이 ALS metric depth만으로 발생했는지, 같은 depth에 ALS normal을 더한 효과인지 분리했다. 새 학습은 `ALS_DEPTH_ONLY` 한 arm이며, Control과 기존 full E4는 read-only로 재사용했다. 7k model/optimizer/scheduler/RNG/strategy 상태는 exact-equal이었다.

## High-Z — 20k

| arm | Gaussian Z>650 | Gaussian Z p99 | Gaussian Z max | fused Z>650 | Roofer vertex Z>650 |
|---|---:|---:|---:|---:|---:|
{highz}

## 정상 표면 — 20k

| arm | MVS p2plane median (m) | MVS normal median | LoD2 height median (m) | LoD2 normal median | LoD2 grid coverage |
|---|---:|---:|---:|---:|---:|
{surface}

## Roofer — 20k

아래 표는 **지붕 상면만** 평가한다. full LoD2 solid의 성공으로 해석하지 않는다.

| arm | roof XY coverage | F-score @0.5m | internal RMSE (m) | reference normal median | roof surfaces |
|---|---:|---:|---:|---:|---:|
{roof}

## Full LoD2 solid — 20k

| arm | Roofer ground Z (m) | reference ground Z (m) | ground Z error (m) | exterior wall median (m) | exterior wall max (m) | reference building height (m) |
|---|---:|---:|---:|---:|---:|---:|
{solid}

## 관찰

- ALS depth-only는 Control보다 Roofer roof coverage와 roof F-score가 낮고 internal RMSE가 높아, full E4의 **지붕 상면 회복**을 재현하지 못했다.
- ALS normal을 추가한 full E4는 depth-only 대비 roof coverage가 `{100*(by_arm['E4_ALS_PRIOR_ONLY']['roofer_roof_xy_coverage']-by_arm['ALS_DEPTH_ONLY']['roofer_roof_xy_coverage']):.2f}` percentage points, roof F-score가 `{by_arm['E4_ALS_PRIOR_ONLY']['roofer_fscore_0p5m']-by_arm['ALS_DEPTH_ONLY']['roofer_fscore_0p5m']:.3f}` 증가했고 roof reference-normal median은 `{by_arm['ALS_DEPTH_ONLY']['roofer_reference_normal_median_deg']-by_arm['E4_ALS_PRIOR_ONLY']['roofer_reference_normal_median_deg']:.2f}°` 감소했다.
- 그러나 세 arm 모두 Roofer ground Z가 evaluation-only reference보다 약 24 m 높고 외벽 중앙값이 1 m 미만이다. 따라서 예측 CityJSON에 WallSurface가 존재해도 **full LoD2 건물 체적은 복원되지 않았다**.
- high-Z Gaussian은 세 arm 모두 남았지만 footprint 밖에 있었고 최종 Roofer vertex에는 전달되지 않았다. Roofer 회복과 high-Z 제거는 별도 현상이다.
- full E4가 point-height, point-to-plane, 입력 normal 요약에서 일괄 우세한 것은 아니다. 큰 roof-output 차이는 Roofer의 비선형 plane 선택·footprint 외삽 문턱을 통과했을 가능성과 일치하며, 입력 normal이 직접 원인이라는 증거는 아니다.

정성 비교: `representative_images/roofer_3arm_20k_top.png`; 3D viewer: `e4-normal-ablation-roofer-v1/index.html`.

scientific_verdict: null
"""
    (TASK_ROOT / "comparison.md").write_text(comparison, encoding="utf-8")
    contract_path = TASK_ROOT / "experiment_contract.json"; contract = json.loads(contract_path.read_text()); contract.update({"status": "COMPLETE_MEASURED_VIEWER_PUBLISHED", "training_experiments_started": 1, "training_experiments_completed": 1, "scientific_verdict": None}); contract_path.write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n")
    issues = """# Issues

- No training, checkpoint, fusion, classification, or Roofer case failed.
- Critical interpretation issue: the published Roofer coverage/F-score metrics are roof-surface-only. They overstate full-LoD2 usability because all arms estimated ground near roof elevation and produced shallow exterior walls.
- The shared SMRF classification retained many roof-like footprint points as class 2; Roofer's terrain-height read-out is therefore classification-confounded. LoD2 reference ground Z was evaluation-only and was not used to alter reconstruction.
- The comparison has one building, one seed, and one continuation; no confirmatory inference is made.
- The viewer triangulates CityJSON outer rings for display only; all numerical Roofer metrics use the source CityJSONSeq directly.
- Existing full-E4 and viewer-root files were read-only; only a separate add-only viewer subdirectory was created.

scientific_verdict: null
"""
    (TASK_ROOT / "issues.md").write_text(issues, encoding="utf-8")
    notes_path = TASK_ROOT / "NOTES.md"
    notes = notes_path.read_text().replace("Status: `PREFLIGHT_BOUND`", "Status: `COMPLETE_MEASURED_VIEWER_PUBLISHED`")
    note_line = "One new training experiment completed. Three-arm 20k comparison is in `three_arm_metrics.json`; interactive Roofer evidence is in the separate 8878 slot."
    correction_line = "Interpretation correction: Roofer roof-surface recovery is reported separately from the failed full-LoD2 ground/wall solid."
    for line in (note_line, correction_line):
        if line not in notes:
            notes = notes.rstrip() + "\n\n" + line + "\n"
    notes_path.write_text(notes)
    provenance_path = TASK_ROOT / "provenance.json"; provenance = json.loads(provenance_path.read_text()); provenance["ended_utc"] = datetime.now(timezone.utc).isoformat(); provenance["evaluation_commands"] = ["checkpoint rendering/fusion", "shared SMRF classification and Roofer", "MVS surface audit", "evaluation-only LoD2 fused and Roofer audit", "add-only 8878 viewer build"]; provenance["output_sha256"] = {name: sha256(TASK_ROOT / name) for name in ("three_arm_metrics.json", "three_arm_metrics.csv", "comparison.md", "viewer_slot.json", "representative_images/roofer_3arm_20k_top.png")}; provenance["scientific_verdict"] = None; provenance_path.write_text(json.dumps(provenance, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": contract["status"], "rows": len(rows), "scientific_verdict": None}, indent=2))


if __name__ == "__main__":
    main()
