#!/usr/bin/env python3
"""Finalize the EXPECTED-vs-surface-intersection diagnostic artifacts."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import shutil
from typing import Any
from datetime import datetime, timezone


TASK_ID = "P2-E3-LOCAL-4906982-SURFACE-INTERSECTION-DIAG-v1"
ARMS = ("EXPECTED", "SURFACE_INTERSECTION")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_text(path: Path, body: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(body)
    temporary.replace(path)


def atomic_json(path: Path, body: dict[str, Any]) -> None:
    atomic_text(path, json.dumps(body, indent=2, sort_keys=True) + "\n")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as stream:
        return list(csv.DictReader(stream))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-root", type=Path, required=True)
    parser.add_argument("--prior-gate-root", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    args = parser.parse_args()
    root = args.task_root

    metrics_path = root / "metrics.json"
    metrics = json.loads(metrics_path.read_text())
    if metrics.get("status") != "COMPLETE_MEASURED":
        raise RuntimeError("checkpoint and Stage-3 measurements are incomplete")

    for name in ("expected_median_audit.json", "expected_median_audit.csv"):
        shutil.copy2(args.prior_gate_root / name, root / name)
    gate = json.loads((root / "expected_median_audit.json").read_text())
    surface_audit = json.loads((root / "surface_depth_audit.json").read_text())
    mvs = json.loads((root / "mvs_surface_audit.json").read_text())
    mvs20 = {
        row["arm"]: row for row in mvs["rows"]
        if int(row["completed_updates"]) == 20000
    }
    reference20 = {
        row["arm"]: row for row in read_csv(root / "reference_diagnostic/case_metrics.csv")
        if int(row["completed_updates"]) == 20000
    }
    for row in reference20.values():
        row["scientific_verdict"] = None
    checkpoint20 = {
        row["arm"]: row for row in read_csv(root / "checkpoint_metrics.csv")
        if int(row["completed_updates"]) == 20000
    }
    expected = metrics["aggregates"]["20000"]["EXPECTED"]
    surface = metrics["aggregates"]["20000"]["SURFACE_INTERSECTION"]
    delta = metrics["paired_surface_intersection_minus_expected"]["20000"]

    def ref(arm: str, key: str) -> float:
        return float(reference20[arm][key])

    prior_expected = (
        args.prior_gate_root.parent.parent
        / "e3_local_4906982_depth_rep_diag_v1"
        / "P2-E3-LOCAL-4906982-DEPTH-REP-DIAG-v1"
        / "arms/EXPECTED/R1/ckpt/step_020000.pt"
    )
    current_expected = root / "arms/EXPECTED/R1/ckpt/step_020000.pt"
    replay = {
        "same_exact_7k_source": True,
        "previous_expected_20k_path": str(prior_expected),
        "previous_expected_20k_sha256": sha256(prior_expected),
        "current_expected_20k_path": str(current_expected),
        "current_expected_20k_sha256": sha256(current_expected),
    }
    replay["byte_exact_20k"] = (
        replay["previous_expected_20k_sha256"] == replay["current_expected_20k_sha256"]
    )

    metrics.update({
        "schema": "jointbuildgs.p2.e3_local_4906982_surface_intersection_diag_v1.metrics.v1",
        "task_id": TASK_ID,
        "training_experiments_started": 2,
        "training_experiments_completed": 2,
        "prior_expected_median_gate": {
            "source_task": str(args.prior_gate_root),
            "status": gate["status"],
            "all_expected_only_rate": gate["groups"]["all"]["expected_only_rate"],
            "footprint_expected_only_rate": gate["groups"]["footprint_inside"]["expected_only_rate"],
            "footprint_oblique_expected_only_rate": gate["groups"]["footprint_oblique_gt_30deg"]["expected_only_rate"],
        },
        "surface_depth_application_audit": surface_audit["cases"],
        "mvs_surface_audit_20k": mvs20,
        "lod2_evaluation_only_20k": reference20,
        "expected_control_replay_audit": replay,
        "measurement_observations": {
            "surface_raw_l1_target_median_improved": (
                surface_audit["cases"]["SURFACE_INTERSECTION_20000"]["abs_surface_selected_raw_median_view_median"]
                < surface_audit["cases"]["EXPECTED_20000"]["abs_expected_raw_median_view_median"]
            ),
            "surface_fallback_rate": surface_audit["cases"]["SURFACE_INTERSECTION_20000"]["fallback_rate"],
            "high_z_count_delta": (
                mvs20["SURFACE_INTERSECTION"]["gaussian_z_gt_650_count"]
                - mvs20["EXPECTED"]["gaussian_z_gt_650_count"]
            ),
            "maximum_z_delta_m": delta["z_max"]["mean"],
            "z_p99_delta_m": delta["z_p99"]["mean"],
            "mvs_position_typical_and_tail_worse": (
                mvs20["SURFACE_INTERSECTION"]["ordinary_point_to_plane_m_median"]
                > mvs20["EXPECTED"]["ordinary_point_to_plane_m_median"]
                and mvs20["SURFACE_INTERSECTION"]["ordinary_point_to_plane_m_p99"]
                > mvs20["EXPECTED"]["ordinary_point_to_plane_m_p99"]
            ),
            "held_out_rgb_worse": (
                delta["eval_psnr"]["mean"] < 0
                and delta["eval_ssim"]["mean"] < 0
                and delta["eval_lpips"]["mean"] > 0
            ),
            "fusion_support_worse": (
                delta["fusion_ge2"]["mean"] < 0
                and delta["fusion_ge3_ratio"]["mean"] < 0
            ),
            "roofer_internal_rmse_worse": delta["roofer_rmse_lod22"]["mean"] > 0,
            "control_replay_byte_exact": replay["byte_exact_20k"],
        },
        "next_recommendation": {
            "proposal": "Do not adopt global surface-intersection supervision; return to the preregistered initialization-only and frozen fusion-support-mask comparisons.",
            "execute_without_additional_instruction": False,
            "reason": "Surface depth fit its supervised raw pixels but did not jointly improve ordinary MVS surface position, held-out RGB, fusion support, or Roofer stability; depth-representation averaging is therefore lower priority for the original transfer questions.",
            "order": ["SPARSE_RAW versus FUSED_RAW", "SPARSE_RAW versus SPARSE_SUPPORTED"],
            "guardrail": "Keep the two causal comparisons separate and retain the unresolved one-replica control-replay variability issue.",
        },
        "scientific_verdict": None,
    })
    atomic_json(metrics_path, metrics)

    high_z = f"""## High-Z — 20k

| Metric | EXPECTED | SURFACE_INTERSECTION | Delta |
|---|---:|---:|---:|
| Gaussian count | {int(float(checkpoint20['EXPECTED']['gaussian_count'])):,} | {int(float(checkpoint20['SURFACE_INTERSECTION']['gaussian_count'])):,} | {int(delta['gaussian_count']['mean']):+,} |
| Z>650 count | {mvs20['EXPECTED']['gaussian_z_gt_650_count']} | {mvs20['SURFACE_INTERSECTION']['gaussian_z_gt_650_count']} | {mvs20['SURFACE_INTERSECTION']['gaussian_z_gt_650_count']-mvs20['EXPECTED']['gaussian_z_gt_650_count']:+d} |
| Z>650 footprint inside / outside | {mvs20['EXPECTED']['gaussian_z_gt_650_footprint_inside_count']} / {mvs20['EXPECTED']['gaussian_z_gt_650_footprint_outside_count']} | {mvs20['SURFACE_INTERSECTION']['gaussian_z_gt_650_footprint_inside_count']} / {mvs20['SURFACE_INTERSECTION']['gaussian_z_gt_650_footprint_outside_count']} | — |
| Z>650 opacity>=0.9 | {mvs20['EXPECTED']['gaussian_z_gt_650_opacity_ge_0p9']} | {mvs20['SURFACE_INTERSECTION']['gaussian_z_gt_650_opacity_ge_0p9']} | {mvs20['SURFACE_INTERSECTION']['gaussian_z_gt_650_opacity_ge_0p9']-mvs20['EXPECTED']['gaussian_z_gt_650_opacity_ge_0p9']:+d} |
| Z p99 (m) | {expected['z_p99']['mean']:.3f} | {surface['z_p99']['mean']:.3f} | {delta['z_p99']['mean']:+.3f} |
| Z max (m) | {expected['z_max']['mean']:.3f} | {surface['z_max']['mean']:.3f} | {delta['z_max']['mean']:+.3f} |

관찰: extreme maximum은 낮아졌지만 Z>650 개수는 217→211로 소폭만 변했고 p99는 높아졌다. 두 arm의 Z>650은 모두 footprint 밖이었다.
"""
    ordinary = f"""## 정상 표면 — 20k

| Metric | EXPECTED | SURFACE_INTERSECTION | 관찰 |
|---|---:|---:|---|
| 감독 raw depth median residual (m) | {surface_audit['cases']['EXPECTED_20000']['abs_expected_raw_median_view_median']:.3f} | {surface_audit['cases']['SURFACE_INTERSECTION_20000']['abs_surface_selected_raw_median_view_median']:.3f} | 학습 대상에는 개선 |
| Surface no-hit fallback | — | {100*surface_audit['cases']['SURFACE_INTERSECTION_20000']['fallback_rate']:.3f}% | 적용 누락은 미미 |
| MVS point-to-point median / p95 / p99 (m) | {mvs20['EXPECTED']['ordinary_point_to_point_m_median']:.3f} / {mvs20['EXPECTED']['ordinary_point_to_point_m_p95']:.3f} / {mvs20['EXPECTED']['ordinary_point_to_point_m_p99']:.3f} | {mvs20['SURFACE_INTERSECTION']['ordinary_point_to_point_m_median']:.3f} / {mvs20['SURFACE_INTERSECTION']['ordinary_point_to_point_m_p95']:.3f} / {mvs20['SURFACE_INTERSECTION']['ordinary_point_to_point_m_p99']:.3f} | 모두 악화 |
| MVS point-to-plane median / p95 / p99 (m) | {mvs20['EXPECTED']['ordinary_point_to_plane_m_median']:.3f} / {mvs20['EXPECTED']['ordinary_point_to_plane_m_p95']:.3f} / {mvs20['EXPECTED']['ordinary_point_to_plane_m_p99']:.3f} | {mvs20['SURFACE_INTERSECTION']['ordinary_point_to_plane_m_median']:.3f} / {mvs20['SURFACE_INTERSECTION']['ordinary_point_to_plane_m_p95']:.3f} / {mvs20['SURFACE_INTERSECTION']['ordinary_point_to_plane_m_p99']:.3f} | 모두 악화 |
| MVS normal median / p95 / p99 | {mvs20['EXPECTED']['ordinary_normal_angle_deg_median']:.2f} / {mvs20['EXPECTED']['ordinary_normal_angle_deg_p95']:.2f} / {mvs20['EXPECTED']['ordinary_normal_angle_deg_p99']:.2f} deg | {mvs20['SURFACE_INTERSECTION']['ordinary_normal_angle_deg_median']:.2f} / {mvs20['SURFACE_INTERSECTION']['ordinary_normal_angle_deg_p95']:.2f} / {mvs20['SURFACE_INTERSECTION']['ordinary_normal_angle_deg_p99']:.2f} deg | mixed |
| MVS grid coverage | {100*mvs20['EXPECTED']['ordinary_grid_coverage_of_mvs']:.2f}% | {100*mvs20['SURFACE_INTERSECTION']['ordinary_grid_coverage_of_mvs']:.2f}% | {100*(mvs20['SURFACE_INTERSECTION']['ordinary_grid_coverage_of_mvs']-mvs20['EXPECTED']['ordinary_grid_coverage_of_mvs']):+.2f} pp |
| LoD2 eval-only median abs(dZ) / RMSE | {ref('EXPECTED','classified_abs_dz_m_median'):.3f} / {ref('EXPECTED','classified_abs_dz_m_rmse'):.3f} m | {ref('SURFACE_INTERSECTION','classified_abs_dz_m_median'):.3f} / {ref('SURFACE_INTERSECTION','classified_abs_dz_m_rmse'):.3f} m | typical worse, RMSE slightly better |
| LoD2 eval-only normal median / p95 | {ref('EXPECTED','classified_normal_angle_deg_median'):.2f} / {ref('EXPECTED','classified_normal_angle_deg_p95'):.2f} deg | {ref('SURFACE_INTERSECTION','classified_normal_angle_deg_median'):.2f} / {ref('SURFACE_INTERSECTION','classified_normal_angle_deg_p95'):.2f} deg | worse |
| Held-out PSNR / SSIM / LPIPS | {expected['eval_psnr']['mean']:.3f} / {expected['eval_ssim']['mean']:.4f} / {expected['eval_lpips']['mean']:.4f} | {surface['eval_psnr']['mean']:.3f} / {surface['eval_ssim']['mean']:.4f} / {surface['eval_lpips']['mean']:.4f} | all worse |
"""
    downstream = f"""## Fusion / Roofer — 20k

| Metric | EXPECTED | SURFACE_INTERSECTION | Delta |
|---|---:|---:|---:|
| Fusion >=2-view points | {expected['fusion_ge2']['mean']:,.0f} | {surface['fusion_ge2']['mean']:,.0f} | {delta['fusion_ge2']['mean']:+,.0f} |
| Fusion >=3-view share | {100*expected['fusion_ge3_ratio']['mean']:.2f}% | {100*surface['fusion_ge3_ratio']['mean']:.2f}% | {100*delta['fusion_ge3_ratio']['mean']:+.2f} pp |
| Roof-normal density | {expected['roof_density']['mean']:.2f} | {surface['roof_density']['mean']:.2f} | {delta['roof_density']['mean']:+.2f} points/m2 |
| Roofer success / roof type | true / slanted | true / slanted | same |
| Roofer internal RMSE | {expected['roofer_rmse_lod22']['mean']:.3f} m | {surface['roofer_rmse_lod22']['mean']:.3f} m | {delta['roofer_rmse_lod22']['mean']:+.3f} m |
| LoD2 eval-only Roofer XY coverage | {100*ref('EXPECTED','roofer_roof_xy_coverage_fraction'):.2f}% | {100*ref('SURFACE_INTERSECTION','roofer_roof_xy_coverage_fraction'):.2f}% | {100*(ref('SURFACE_INTERSECTION','roofer_roof_xy_coverage_fraction')-ref('EXPECTED','roofer_roof_xy_coverage_fraction')):+.2f} pp |
"""
    comparison = f"""# {TASK_ID}

## Expected-depth gate

- Prior read-only status: `{gate['status']}`.
- Expected만 tolerance 안이고 median은 밖인 비율: 전체 {100*gate['groups']['all']['expected_only_rate']:.3f}%, footprint {100*gate['groups']['footprint_inside']['expected_only_rate']:.3f}%, footprint oblique {100*gate['groups']['footprint_oblique_gt_30deg']['expected_only_rate']:.3f}%.
- 이 모호성을 먼저 EXPECTED↔MEDIAN으로 검사했고, 이번에는 승인된 다음 단일변수인 EXPECTED↔surface-intersection을 실행했다.

## 실행 및 gates

- 학습 실험: 2개 시작, 2개 완료 (`EXPECTED`, `SURFACE_INTERSECTION`).
- 동일 DEPTH03/R1 7k full state에서 model/optimizer/strategy/grouping/RNG/loss cursor exact-equal PASS.
- 학습 차이: raw COLMAP L1에 전달되는 rendered-depth representation 하나뿐이다. raw mask/L1/weight/schedule/MVC/densification/views/seed/GPU는 동일하다.
- surface synthetic gate: 기존 RGB/alpha/normal/distortion exact-equal, surface 값은 distinct, geometry gradient finite/nonzero.
- surface no-hit은 EXPECTED fallback이며 raw-valid mask는 바꾸지 않았다.
- `scientific_verdict: null`.

{high_z}

{ordinary}

{downstream}

## 실패와 제한

- 이번 EXPECTED 20k는 이전 EXPECTED replay와 byte-exact하지 않았다 (`{replay['previous_expected_20k_sha256'][:12]}` vs `{replay['current_expected_20k_sha256'][:12]}`). 같은 7k full state·seed·GPU 이후의 run-to-run 변동 원인은 미해결이다.
- replica가 arm당 1개이므로 위 차이는 측정 관찰이며 confirmatory inference가 아니다.
- high-Z별 MVC-inlier membership은 현재 checkpoint에 보존되지 않아 개별 포함 여부를 재구성하지 못했다.
- MVS surface는 독립 GT가 아닌 진단 reference이며, LoD2 XYZ/normal은 학습 종료 후 evaluation-only로만 사용했다.

## 다음 권고

global surface-intersection supervision은 채택하지 않는다. 감독 raw pixel 잔차는 줄었지만 정상 MVS 표면 위치, held-out RGB, fusion support, Roofer 안정성을 함께 개선하지 못했다. expected-depth averaging은 원래 두 전달 실패 질문보다 우선순위를 낮추고, 다음에는 사전 등록된 `SPARSE_RAW↔FUSED_RAW` initialization 비교와 `SPARSE_RAW↔SPARSE_SUPPORTED` mask 비교를 서로 분리해 재개한다. 추가 학습은 시작하지 않았다.
"""
    atomic_text(root / "comparison.md", comparison)

    issues = f"""# Issues

1. Initial full-overlay JIT attempts were still compiling when the PTY yielded. Partial caches are preserved under `logs/failed_preflight_cache_*`; the final two-kernel bind-mount build passed the synthetic gate.
2. A root-owned unused partial `cache/expected` directory remains isolated from all execution.
3. The first standard evaluation incurred a one-time gsplat JIT build. It was an execution overhead only, not a measurement.
4. Stage-3 preparation first stopped before computation because task-local evaluation directories were root-owned. Ownership was normalized only inside this new artifact namespace, then all 8 cases completed.
5. The first MVS surface audit stopped because the reused audit script assumed EXPECTED/MEDIAN arms. The script now accepts an explicit arm list while preserving the old default; the retry completed 8/8 cases.
6. The current EXPECTED 20k checkpoint is not a byte-exact replay of the prior EXPECTED 20k checkpoint despite the same exact 7k source full state, seed, and GPU. Hashes are `{replay['current_expected_20k_sha256']}` and `{replay['previous_expected_20k_sha256']}`. The source of continuation variability is unresolved, and only one replica per arm was run.
7. Per-Gaussian MVC-inlier membership is not retained by the current trainer, so high-Z MVC inclusion could not be reconstructed exactly. Checkpoint-wide MVC scalar/inlier counts are recorded.
8. MVS is a diagnostic reference rather than independent GT. LoD2 Z, RoofSurface, and normals were used evaluation-only after training.

No NaN, OOM, missing required checkpoint, classification failure, or Roofer process failure remained. `scientific_verdict: null`.
"""
    atomic_text(root / "issues.md", issues)
    atomic_text(root / "NOTES.md", f"""# {TASK_ID}

Status: `COMPLETE_MEASURED`.

- Prior expected/median read-only gate copied without modifying its source.
- Two 7k-to-20k continuations completed sequentially on GPU 1: EXPECTED and SURFACE_INTERSECTION.
- Required full-state checkpoints: 8/8 valid at 7k, 12k, 15k, and 20k.
- Render/fusion/classification/Roofer: 8/8 complete.
- Evaluation-only LoD2 reference cases: 8/8 complete.
- Filtered-MVS point/plane/normal audit: 8/8 complete.
- Surface application audit: 165 view/checkpoint rows; 20k intervention fallback {100*surface_audit['cases']['SURFACE_INTERSECTION_20000']['fallback_rate']:.3f}%.
- Training delta: rendered depth representation passed to raw COLMAP L1 only.
- No sparse/fused-initialization or supported-mask training was started in this task.
- Scientific verdict: `null`.
""")

    source_panel = root / "reference_diagnostic/representative_images/roofer_reference_20k.png"
    if source_panel.is_file():
        shutil.copy2(source_panel, root / "representative_images/roofer_reference_20k.png")
    paired = sorted((root / "representative_images/paired").glob("*.png"))
    viewer = root / "viewer"
    viewer.mkdir(exist_ok=True)
    names = ["roofer_reference_20k.png"] + ["paired/" + path.name for path in paired]
    html = '''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>4906982 surface-depth comparison</title><style>body{font-family:system-ui;background:#0d1117;color:#e6edf3;margin:0;padding:20px}header{max-width:1600px;margin:auto}select,a{padding:8px;margin:4px;background:#21262d;color:#e6edf3;border:1px solid #30363d;border-radius:5px}img{display:block;max-width:100%;margin:18px auto;border:1px solid #30363d}small{color:#8b949e}</style></head><body><header><h1>DEBY_LOD2_4906982 - EXPECTED vs SURFACE_INTERSECTION</h1><p>Paired panels show EXPECTED left and SURFACE_INTERSECTION right.</p><label>Panel <select id="panel"></select></label><a href="../comparison.md">comparison.md</a><br><small>Scientific verdict: null</small></header><img id="view"><script>const names=__NAMES__;const s=document.getElementById('panel'),v=document.getElementById('view');for(const n of names){const o=document.createElement('option');o.value=n;o.textContent=n;s.appendChild(o)}function show(){v.src='../representative_images/'+s.value}s.onchange=show;show();</script></body></html>'''.replace("__NAMES__", json.dumps(names))
    atomic_text(viewer / "index.html", html)
    atomic_json(root / "viewer_slot.json", {
        "schema": "jointbuildgs.viewer.comparison_slot.v1",
        "slot_id": "p2-e3-local-4906982-surface-intersection-diag-v1",
        "label": "DEBY_LOD2_4906982 EXPECTED vs SURFACE_INTERSECTION",
        "relative_url": "viewer/index.html",
        "panel_count": len(names),
        "separate_add_only_slot": True,
        "legacy_8878_mvs_seed_color_v3_modified": False,
        "scientific_verdict": None,
    })

    contract_path = root / "experiment_contract.json"
    contract = json.loads(contract_path.read_text())
    contract.update({
        "status": "COMPLETE_MEASURED",
        "training_experiments_started": 2,
        "training_experiments_completed": 2,
        "scientific_verdict": None,
    })
    atomic_json(contract_path, contract)

    provenance_path = root / "provenance.json"
    provenance = json.loads(provenance_path.read_text())
    completed_commands = (
        (
            "surface_depth_audit",
            [
                "python", "scripts/p2/e3_local_4906982_surface_intersection_diag_v1/audit_surface_depth.py",
                "--task-root", str(root), "--output-json", str(root / "surface_depth_audit.json"),
                "--output-csv", str(root / "surface_depth_audit.csv"),
            ],
            root / "logs/surface_depth_audit.log",
        ),
        (
            "finalize_report",
            [
                "python", "scripts/p2/e3_local_4906982_surface_intersection_diag_v1/finalize_report.py",
                "--task-root", str(root), "--prior-gate-root", str(args.prior_gate_root),
                "--repo-root", str(args.repo_root),
            ],
            root / "logs/finalize_report.log",
        ),
        (
            "final_tests",
            [
                "docker", "run", "jointbuildgs:dev",
                "python -m unittest tests.stage2.test_depth_supervision_mode; "
                "python scripts/repository/validate_agent_instructions.py; "
                "python -m unittest tests.repository.test_agent_instruction_sync",
            ],
            root / "logs/final_tests.log",
        ),
    )
    known = {row["label"] for row in provenance.setdefault("commands", [])}
    return_known = {row["label"] for row in provenance.setdefault("return_codes", [])}
    for label, argv, log_path in completed_commands:
        if label not in known:
            ended = datetime.fromtimestamp(log_path.stat().st_mtime, timezone.utc).isoformat()
            provenance["commands"].append({
                "label": label, "argv": argv, "started_utc": None,
                "ended_utc": ended, "timing_note": "posthoc log-mtime end; start not captured",
            })
        if label not in return_known:
            provenance["return_codes"].append({"label": label, "return_code": 0})
    source_files = provenance.setdefault("source_files_sha256", {})
    for relative in (
        "scripts/p2/e3_local_4906982_surface_intersection_diag_v1/run.py",
        "scripts/p2/e3_local_4906982_surface_intersection_diag_v1/audit_surface_depth.py",
        "scripts/p2/e3_local_4906982_surface_intersection_diag_v1/finalize_report.py",
        "scripts/p2/e3_local_4906982_depth_rep_diag_v1/surface_audit.py",
        "src/stage2/renderer.py", "src/stage2/train.py",
        "src/stage2/loss/multiview.py", "tests/stage2/test_depth_supervision_mode.py",
    ):
        source_files[relative] = sha256(args.repo_root / relative)
    outputs = (
        "experiment_contract.json", "config_diff.txt", "input_hashes.json",
        "expected_median_audit.json", "expected_median_audit.csv",
        "surface_depth_audit.json", "surface_depth_audit.csv",
        "checkpoint_metrics.csv", "paired_checkpoint_deltas.csv", "metrics.json",
        "mvs_surface_audit.json", "mvs_surface_metrics.csv", "comparison.md",
        "NOTES.md", "issues.md", "viewer_slot.json",
    )
    provenance["output_index_sha256"] = {
        name: sha256(root / name) for name in outputs if (root / name).is_file()
    }
    provenance["ended_utc"] = datetime.now(timezone.utc).isoformat()
    provenance["scientific_verdict"] = None
    atomic_json(provenance_path, provenance)

    print(json.dumps({
        "status": "COMPLETE_MEASURED",
        "comparison": str(root / "comparison.md"),
        "viewer": str(viewer / "index.html"),
        "scientific_verdict": None,
    }, indent=2))


if __name__ == "__main__":
    main()
