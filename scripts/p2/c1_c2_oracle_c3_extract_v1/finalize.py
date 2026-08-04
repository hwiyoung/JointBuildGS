#!/usr/bin/env python3
"""Validate and finalize the corrected C1/C2 oracle and C3 extraction payload."""

from __future__ import annotations

import argparse
import csv
import html
import io
import json
from pathlib import Path
from typing import Any

from scripts.p2.c1_c2_oracle_c3_extract_v1.contract import (
    canonical_json_bytes,
    file_record,
    load_config,
    validate_config,
    write_new,
)
from src.visualization.fixed_view_qualitative import load_cityjsonseq


def finalize(output_root: Path, *, source_commit: str, run_id: str) -> dict[str, Any]:
    config = load_config()
    validate_config(config, require_activation=True)
    unit_rows = [
        json.loads(line)
        for line in (output_root / "freeze/c1_c2_execution_units_v1.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if len(unit_rows) != 6 or len({row["operation_unit_id"] for row in unit_rows}) != 6:
        raise RuntimeError("six unique C1/C2 building-method records are required")
    summaries = []
    artifact_records = []
    for row in unit_rows:
        terminal_path = output_root / row["work_directory"] / "roofer_terminal_v1.json"
        if row.get("roofer_eligible"):
            terminal = json.loads(terminal_path.read_text(encoding="utf-8"))
            if terminal.get("status") != "COMPLETED" or len(terminal.get("outputs") or ()) != 1:
                raise RuntimeError(f"C1/C2 terminal incomplete: {row['operation_unit_id']}")
            if terminal.get("scientific_verdict") is not None or terminal.get("official_honest_stage3") is not False:
                raise RuntimeError("C1/C2 interpretation boundary drifted")
            output_path = output_root / terminal["outputs"][0]["path"]
            surfaces = load_cityjsonseq(output_path)
            semantic_counts = {name: sum(surface.semantic == name for surface in surfaces) for name in ("RoofSurface", "WallSurface", "GroundSurface")}
            output_sha256 = terminal["outputs"][0]["sha256"]
            runtime_seconds = int(terminal["runtime_seconds"])
            status = "COMPLETED"
            artifact_records.extend((terminal["outputs"][0], file_record(terminal_path, output_root)))
        else:
            if not row.get("pre_roofer_failure") or terminal_path.exists():
                raise RuntimeError(f"invalid pre-Roofer failure record: {row['operation_unit_id']}")
            semantic_counts = {name: None for name in ("RoofSurface", "WallSurface", "GroundSurface")}
            output_sha256 = None
            runtime_seconds = 0
            status = "PRE_ROOFER_REFERENCE_ID_ALIGNMENT_FAILURE"
        summaries.append({
            "condition_id": row["condition_id"],
            "stable_id": row["stable_id"],
            "class6_point_count": int(row["classification"]["building_class6_count"]),
            "class2_point_count": int(row["classification"]["ground_class2_count"]),
            "local_ground_z": float(row["classification"]["local_ground_z"]),
            "status": status,
            "roof_surface_count": semantic_counts["RoofSurface"],
            "wall_surface_count": semantic_counts["WallSurface"],
            "ground_surface_count": semantic_counts["GroundSurface"],
            "runtime_seconds": runtime_seconds,
            "input_sha256": row["input"]["sha256"],
            "footprint_sha256": row["footprint"]["sha256"],
            "output_sha256": output_sha256,
            "oracle_diagnostic": True,
            "official_honest_stage3": False,
            "scientific_verdict": None,
        })
        artifact_records.extend((row["input"], row["footprint"]))
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=list(summaries[0]))
    writer.writeheader()
    writer.writerows(summaries)
    summary_path = output_root / "tables/c1_c2_oracle_operation_summary_v1.csv"
    write_new(summary_path, buffer.getvalue().encode("utf-8"))
    c12_index = json.loads((output_root / "qualitative/c1_c2/index_v1.json").read_text(encoding="utf-8"))
    c3_index = json.loads((output_root / "qualitative/c3/index_v1.json").read_text(encoding="utf-8"))
    if c12_index.get("case_sheet_count") != 3 or c12_index.get("panel_count") != 72:
        raise RuntimeError("C1/C2 qualitative count drifted")
    if c3_index.get("case_sheet_count") != 6 or c3_index.get("panel_count") != 120:
        raise RuntimeError("C3 qualitative count drifted")
    if c3_index.get("roofline_role") != "CURRENT_RGB_PROJECTION_CONTEXT_ONLY":
        raise RuntimeError("C3 roofline context row is missing")
    if c3_index.get("footprint_role") != "GT_GROUNDSURFACE_XY_DISPLAY_ONLY_ON_ALL_3D_ROWS":
        raise RuntimeError("C3 footprint display is missing")
    if c3_index.get("gaussian_representation") != "ORIENTED_2D_ELLIPSES_FROM_CHECKPOINT_QUATERNION_SCALE_OPACITY_NOT_CENTER_POINTS":
        raise RuntimeError("C3 Gaussian representation drifted")
    expected_mesh_role = "ROOF_SEMANTIC_CLASS_1_WITHIN_GT_GROUNDSURFACE_XY_1M_BUFFER_POISSON_OR_EXPLICIT_INSUFFICIENT_EVIDENCE"
    if c3_index.get("mesh_role") != expected_mesh_role:
        raise RuntimeError("C3 roof-semantic mesh role drifted")
    mesh_recovery_path = output_root / "control/c3_roof_semantic_mesh_recovery_v1.json"
    mesh_recovery = json.loads(mesh_recovery_path.read_text(encoding="utf-8"))
    if mesh_recovery.get("result_count") != 6 or mesh_recovery.get("completed_mesh_count") != 5:
        raise RuntimeError("C3 roof-semantic mesh completion count drifted")
    if mesh_recovery.get("insufficient_evidence_count") != 1:
        raise RuntimeError("C3 roof-semantic mesh insufficient-evidence count drifted")
    insufficient = [row for row in mesh_recovery["results"] if row["status"] == "INSUFFICIENT_ROOF_SEMANTIC_EVIDENCE"]
    if [(row["condition_id"], row["stable_id"], row["selected_roof_point_count"]) for row in insufficient] != [
        ("C3_2_SEM_DEPTH", "DEBY_LOD2_4907177", 1)
    ]:
        raise RuntimeError("C3 roof-semantic insufficient-evidence identity drifted")
    artifact_records.append(file_record(mesh_recovery_path, output_root))
    for row in mesh_recovery["results"]:
        if row["roof_points"] is not None:
            artifact_records.extend((row["roof_points"], row["roof_mesh"]))
    c3_exports = []
    c3_surfaces = []
    for condition in config["c3_training_provenance"]["conditions"]:
        condition_id = condition["condition_id"]
        export_path = output_root / f"c3/{condition_id}/control/gaussian_export_complete_v1.json"
        surface_path = output_root / f"c3/{condition_id}/control/surface_extraction_complete_v1.json"
        export = json.loads(export_path.read_text(encoding="utf-8"))
        surface = json.loads(surface_path.read_text(encoding="utf-8"))
        if export.get("training_invocations") != 0 or surface.get("training_invocations") != 0:
            raise RuntimeError("C3 extraction unexpectedly trained")
        if export.get("checkpoint", {}).get("sha256") != condition["sha256"] or surface.get("checkpoint_sha256") != condition["sha256"]:
            raise RuntimeError("C3 checkpoint binding drifted")
        if len(surface.get("building_results") or ()) != 3 or surface.get("not_tsdf") is not True:
            raise RuntimeError("C3 surface extraction result drifted")
        c3_exports.append(export)
        c3_surfaces.append(surface)
        artifact_records.extend((file_record(export_path, output_root), file_record(surface_path, output_root)))
    report = f"""# C1/C2 oracle 재실행 및 C3 결과 재추출 기술 보고서 v1

## 실행 결과

- C1/C2: `4906975`, `108580336` × 두 방법 = 4개 독립 Roofer operation 완료
- `4907177`: C1 25점/C2 0점으로 2개 pre-Roofer reference/ID alignment failure
- C1 입력: current UAS LAZ 원점군 crop + GT GroundSurface XY footprint
- C2 입력: exact common-base dense MVS PLY 원점군 crop + 동일 footprint
- C3: current RGB+LoD2 roofline 행, quaternion/scale/opacity 기반 oriented Gaussian ellipse 행, rendered-depth fused point cloud, roof semantic class 1 전용 Poisson mesh 표시
- 이번 작업의 C3 학습: 0회
- Roofer: recovery-v2에서 완료한 exact 4개를 hash 검증 후 계승, 이번 recovery 추가 실행 0회
- Roofer lineage total/G2/GS training/metric/C4-C5: 4/0/0/0/0

## C3 과거 학습 횟수와 시간

성공한 독립 학습은 4회가 아니라 2회다. C3-1 seed0 1회가 129.9분, C3-2 seed0
1회가 86.6분이며 순차 합계는 216.5분(03:36:30)이다. 과거 recovery 디렉터리는
독립 반복으로 세지 않았다.

## 해석 경계

C1/C2는 GT GroundSurface XY를 Roofer footprint로 사용했으므로 official honest Stage 3가
아닌 oracle diagnostic이다. RoofSurface XYZ, LoD2 Z, roof type과 final model은 Roofer 입력에
사용하지 않았다. `DEBY_LOD2_4907177`의 RGB roofline 불일치는 C1/C2 또는 Roofer 실패가
아니라 `REFERENCE/ID ALIGNMENT REVIEW`로 유지한다.

C3 full Gaussian PLY는 모든 primitive와 quaternion/scale/opacity/SH/semantic logits를
보존한다. display proxy는 center point scatter가 아니라 quaternion/scale/opacity를 적용한
oriented 2D Gaussian ellipse로 표시한다. proxy만 명시적 opacity/scale/AOI 필터를 사용한다.
mesh는 이전의 Gaussian별 quad mesh가 아니며, 계승한 rendered-depth fused point에서 semantic
class 1(roof)이고 GT GroundSurface XY의 1 m buffer 안에 있는 점만 골라 만든 Poisson surface다.
`DEBY_LOD2_4907177/C3_2_SEM_DEPTH`는 선택 지붕점이 1점뿐이어서 mesh를 만들지 않고
`INSUFFICIENT_ROOF_SEMANTIC_EVIDENCE`로 표시한다. TSDF라고 표기하지 않는다.

모든 결과의 `scientific_verdict`, official G3/G4/PASS는 null이다.
"""
    report_path = output_root / "reports/technical_report_ko_v1.md"
    write_new(report_path, report.encode("utf-8"))
    links = []
    for record in c12_index["records"]:
        p = record["case_sheet"]["path"]
        links.append(f"<li><a href='../{html.escape(p)}'>{html.escape(record['stable_id'])} C1/C2</a></li>")
    for record in c3_index["records"]:
        p = record["case_sheet"]["path"]
        links.append(f"<li><a href='../{html.escape(p)}'>{html.escape(record['stable_id'])} {html.escape(record['condition_id'])}</a></li>")
    index_html = "<!doctype html><meta charset='utf-8'><title>C1/C2 oracle + C3 extraction</title><h1>C1/C2 oracle + C3 extraction</h1><p>scientific_verdict: null</p><ul>" + "".join(links) + "</ul>"
    html_path = output_root / "qualitative/index.html"
    write_new(html_path, index_html.encode("utf-8"))
    manifest = {
        "schema": "jointbuildgs.c1_c2_oracle_c3_extract_manifest.v1",
        "task_id": config["task_id"],
        "handoff_id": config["handoff_id"],
        "execution_record_id": config["execution_record_id"],
        "execution_authority": config["execution_authority"],
        "source_commit": source_commit,
        "run_id": run_id,
        "status": "FINALIZED_TECHNICAL",
        "scope": config["scope"],
        "c1_c2_building_method_record_count": 6,
        "c1_c2_roofer_operation_count": 4,
        "c1_c2_pre_roofer_reference_alignment_failure_count": 2,
        "c1_c2_unique_input_hash_count": len({row["input_sha256"] for row in summaries}),
        "c1_c2_unique_output_hash_count": len({row["output_sha256"] for row in summaries if row["output_sha256"]}),
        "c1_c2_summary": summaries,
        "c1_c2_case_sheet_count": 3,
        "c1_c2_panel_count": 72,
        "c3_case_sheet_count": 6,
        "c3_panel_count": 120,
        "c3_completed_independent_training_runs_before_this_task": 2,
        "c3_successful_training_runtime_minutes_before_this_task": 216.5,
        "c3_roof_semantic_mesh_recovery": mesh_recovery,
        "execution_counters": {
            "roofer_invocations_this_recovery": 0,
            "roofer_invocations_total_lineage": 4,
            "pre_roofer_reference_alignment_failures": 2,
            "g2_invocations": 0,
            "gs_training_invocations": 0,
            "c3_extraction_invocations_this_recovery": 0,
            "c3_completed_extractions_total_lineage": 2,
            "c3_roof_mesh_postprocess_attempts_this_recovery": 6,
            "c3_roof_mesh_postprocess_completed_this_recovery": 5,
            "metric_recomputations": 0,
            "c4_c5_accesses": 0,
        },
        "c3_exports": c3_exports,
        "c3_surface_extractions": c3_surfaces,
        "records": artifact_records + [file_record(summary_path, output_root), file_record(report_path, output_root), file_record(html_path, output_root)],
        "official_G3_G4_PASS_usable": None,
        "scientific_verdict": None,
    }
    manifest_path = output_root / "artifact_manifest_v1.json"
    write_new(manifest_path, canonical_json_bytes(manifest))
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    result = finalize(args.output_root, source_commit=args.source_commit, run_id=args.run_id)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
