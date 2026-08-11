#!/usr/bin/env python3
"""Build a portable report artifact for the C2 MVS improvement census."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


TRACK_LABELS = {
    "MVS_RAW_GEOMETRY_SUPPORT": "MVS raw support",
    "GEOMETRY_REFERENCE_ACCURACY": "Reference accuracy",
    "GEOMETRY_INPUT_FIT": "Input-fit geometry",
    "ROOFER_ASSEMBLY_TOPOLOGY": "Assembly/topology",
    "CLASSIFICATION_SUPPORT": "Classification support",
    "CLASSIFICATION_CLIPPING": "Classification/clipping",
    "NO_MAJOR_TECHNICAL_FLAG": "No major technical flag",
}

FLAG_LABELS = {
    "RAW_MVS_SUPPORT_LOW": "Raw MVS support <90%",
    "ROOFER_POINTCLOUD_UNUSABLE": "Roofer point cloud unusable",
    "CURRENT_UAS_ACCURACY_CANDIDATE_FAIL": "Current-UAS accuracy candidate fail",
    "INPUT_FIT_RMSE_HIGH": "Input-fit RMSE ≥2m",
    "CLASS6_SUPPORT_LOSS": "Class-6 support gap ≥10pp",
    "CLIP_SENSITIVE": "No-clip coverage gain ≥10pp",
    "NO_CLIP_TOPOLOGY_INVALID": "No-clip topology invalid",
    "INPUT_FIT_RMSE_SEVERE": "Input-fit RMSE ≥4m",
}


def value(row: dict[str, str], name: str) -> float | None:
    return float(row[name]) if row.get(name) else None


def build(root: Path) -> None:
    summary = json.loads((root / "results/summary_v1.json").read_text(encoding="utf-8"))
    rows = list(csv.DictReader((root / "results/c2_mvs_improvement_census_199_v1.csv").open(encoding="utf-8")))
    internal = [row for row in rows if row["fully_inside_roofer_aoi"] == "True"]
    tracks = [
        {"track": TRACK_LABELS.get(name, name), "count": count}
        for name, count in summary["primary_improvement_track_counts_full_aoi_152"].items()
    ]
    flags = [
        {"flag": FLAG_LABELS[name], "count": summary["nonexclusive_flag_counts_full_aoi_152"].get(name, 0)}
        for name in FLAG_LABELS
    ]
    buildings = []
    for row in internal:
        buildings.append({
            "building": row["stable_id"].removeprefix("DEBY_LOD2_"),
            "track": TRACK_LABELS.get(row["primary_improvement_track"], row["primary_improvement_track"]),
            "raw_support": value(row, "all_point_coverage_0p5m"),
            "class6_support": value(row, "class6_coverage_0p5m"),
            "no_clip_coverage": value(row, "no_clip_lod22_xy_coverage"),
            "input_fit_rmse_m": value(row, "no_clip_input_fit_rmse_m"),
            "current_uas_surface_rmse_m": value(row, "current_uas_surface_rmse_m"),
            "current_uas_rmsxy_m": value(row, "current_uas_rmsxy_m"),
            "current_uas_accuracy_candidate": row["current_uas_accuracy_candidate"] or "not assessed",
            "flags": row["improvement_flags"].replace(";", ", "),
        })
    buildings.sort(key=lambda row: (row["track"] == "No major technical flag", row["track"], row["building"]))
    ref = summary["current_uas_reference"]
    headline = [{
        "improvement_flagged": 152 - summary["primary_improvement_track_counts_full_aoi_152"].get("NO_MAJOR_TECHNICAL_FLAG", 0),
        "no_major_flag": summary["primary_improvement_track_counts_full_aoi_152"].get("NO_MAJOR_TECHNICAL_FLAG", 0),
        "reference_eligible": ref["exact_no_clip_reference_eligible_count_full_aoi"],
        "reference_fail": ref["accuracy_candidate_fail_count"],
        "reference_pass": ref["accuracy_candidate_pass_count"],
    }]
    source = {
        "id": "improvement_census",
        "label": "C2 MVS improvement census 199",
        "path": "results/c2_mvs_improvement_census_199_v1.csv",
        "query": {
            "engine": "duckdb", "language": "sql",
            "description": "Loads the reviewed exact 199-building improvement census.",
            "sql": "SELECT * FROM read_csv_auto('results/c2_mvs_improvement_census_199_v1.csv', header=true)",
            "tables_used": ["results/c2_mvs_improvement_census_199_v1.csv"],
        },
    }
    title = "C2 MVS 개선 필요 건물 199동 전수조사"
    artifact: dict[str, Any] = {
        "surface": "report",
        "manifest": {
            "version": 1, "surface": "report", "title": title,
            "description": "동결 C2 MVS no-clip 결과의 건물별 개선 플래그와 평가 공백을 분리한 비확증 기술 전수조사",
            "sources": [source],
            "cards": [{
                "id": "headline", "dataset": "headline", "sourceId": "improvement_census",
                "description": "역사적 Roofer AOI 내부 152동의 기술 진단",
                "metrics": [
                    {"label": "개선 플래그 있음", "field": "improvement_flagged", "format": "number"},
                    {"label": "주요 기술 플래그 없음", "field": "no_major_flag", "format": "number"},
                    {"label": "current-UAS 평가 가능", "field": "reference_eligible", "format": "number"},
                    {"label": "accuracy candidate fail", "field": "reference_fail", "format": "number"},
                ],
            }],
            "charts": [
                {
                    "id": "tracks", "title": "주 개선 트랙", "subtitle": "AOI 내부 152동, 중복 플래그 중 가장 앞선 개선 단계",
                    "type": "horizontalBar", "dataset": "tracks", "sourceId": "improvement_census",
                    "encodings": {"x": {"field": "track", "type": "nominal", "label": "개선 트랙"}, "y": {"field": "count", "type": "quantitative", "label": "건물 수"}},
                    "yAxisTitle": "건물 수", "valueFormat": "number", "layout": "full",
                },
                {
                    "id": "flags", "title": "비배타 개선 플래그", "subtitle": "한 건물에 여러 원인이 동시에 표시될 수 있음",
                    "type": "horizontalBar", "dataset": "flags", "sourceId": "improvement_census",
                    "encodings": {"x": {"field": "flag", "type": "nominal", "label": "플래그"}, "y": {"field": "count", "type": "quantitative", "label": "건물 수"}},
                    "yAxisTitle": "건물 수", "valueFormat": "number", "layout": "full",
                },
            ],
            "tables": [{
                "id": "buildings", "title": "AOI 내부 152동 전수표", "subtitle": "정렬 가능한 진단 목록; 공식 성공 판정이 아님",
                "dataset": "buildings", "sourceId": "improvement_census", "layout": "full", "density": "compact",
                "defaultSort": {"field": "track", "direction": "asc"},
                "columns": [
                    {"field": "building", "label": "건물", "type": "text"},
                    {"field": "track", "label": "주 개선 트랙", "type": "text"},
                    {"field": "raw_support", "label": "raw 지원", "format": "percent"},
                    {"field": "class6_support", "label": "class-6 지원", "format": "percent"},
                    {"field": "no_clip_coverage", "label": "no-clip 면적", "format": "percent"},
                    {"field": "input_fit_rmse_m", "label": "입력-fit RMSE", "format": "number", "unit": "m"},
                    {"field": "current_uas_surface_rmse_m", "label": "current-UAS RMSE", "format": "number", "unit": "m"},
                    {"field": "current_uas_rmsxy_m", "label": "current-UAS RMSXY", "format": "number", "unit": "m"},
                    {"field": "current_uas_accuracy_candidate", "label": "accuracy candidate", "type": "text"},
                    {"field": "flags", "label": "비배타 플래그", "type": "text"},
                ],
            }],
            "blocks": [
                {"id": "title", "type": "markdown", "body": f"# {title}"},
                {"id": "summary", "type": "markdown", "sourceId": "improvement_census", "body": "## 결론\n\n기존 진단 보고서는 199동 전체의 분류지원·clipping·Roofer 조립을 본 1차 전수조사였다. 이 확장판은 AOI 내부 152동 중 **119동에 하나 이상의 주요 개선 플래그**를 부여하고, 나머지 33동은 `주요 기술 플래그 없음`으로 남겼다. 이는 공식 성공 판정이 아니며, 47동은 AOI 경계 때문에 별도 replay가 필요하다."},
                {"id": "metrics", "type": "metric-strip", "cardIds": ["headline"]},
                {"id": "track_text", "type": "markdown", "sourceId": "improvement_census", "body": "## 어디를 먼저 개선해야 하나\n\n주 개선 트랙은 `raw MVS support 73동`, `reference accuracy 22동`, `input-fit geometry 13동`, `assembly/topology 8동`, `classification support 2동`, `classification/clipping 1동`이다. 이 값은 원인을 배타적으로 지우지 않고, 파이프라인에서 가장 앞선 병목을 대표 트랙으로 선택한 것이다."},
                {"id": "track_chart", "type": "chart", "chartId": "tracks", "layout": "full"},
                {"id": "flag_text", "type": "markdown", "sourceId": "improvement_census", "body": "## 복합 실패는 비배타 플래그로 보존한다\n\nAOI 내부에서 raw support 부족 73동, pointcloud unusable 38동, current-UAS accuracy candidate fail 29동, 입력-fit RMSE 2m 이상 34동, class-6 support 손실 24동, clip 민감 23동, no-clip topology invalid 13동이 관찰됐다. 합계가 152를 넘는 것은 한 건물이 여러 개선을 동시에 요구하기 때문이다."},
                {"id": "flag_chart", "type": "chart", "chartId": "flags", "layout": "full"},
                {"id": "case_4906982", "type": "markdown", "sourceId": "improvement_census", "body": "## 4906982의 위치가 달라졌다\n\n4906982는 raw 지원 100%, class-6 지원 35.0%, no-clip 면적 99.997%, 입력-fit RMSE 4.024m다. 그러나 temporal unchanged current-UAS 767 cells와 비교한 exact no-clip surface RMSE는 **0.506m**, P95는 **1.019m**로 candidate accuracy band를 통과했다. 따라서 이 건물의 핵심 개선은 최종 지붕이 4m 틀렸다는 것이 아니라, **SMRF 분류손실과 terrain clipping에 대한 Roofer의 민감도 및 높은 입력 잔차**다."},
                {"id": "reference_limits", "type": "markdown", "sourceId": "improvement_census", "body": "## Reference 평가 가능 범위\n\ncurrent-UAS reference가 존재하는 건물은 79동이지만, temporal unchanged·최소 20 cells·AOI 내부·no-clip RoofSurface 조건을 모두 만족한 것은 40동이다. 그중 candidate band 통과 11동, 실패 29동이다. 나머지 건물은 정확도 실패가 아니라 **reference assessment gap**으로 남겼다."},
                {"id": "table", "type": "table", "tableId": "buildings", "layout": "full"},
                {"id": "method", "type": "markdown", "sourceId": "improvement_census", "body": "## 방법과 한계\n\n동결 199동 clip/no-clip 결과를 재사용했고 MVS·분류·Roofer를 다시 실행하지 않았다. current-UAS는 평가 전용으로만 사용했다. 입력-fit RMSE와 current-UAS surface RMSE는 기준점 집합이 다르므로 직접 동일시할 수 없다. 모든 band는 비확증 진단 기준이며 공식 G3/G4/PASS_usable과 scientific verdict는 null이다."},
                {"id": "next", "type": "markdown", "body": "## 다음 실행 우선순위\n\n1. AOI 경계 47동을 footprint-complete box로 replay한다.\n2. raw support 부족 73동을 texture/view-support와 dense MVS 결손으로 분해한다.\n3. class-6·clip 복합군은 분류 보정 arm과 no-clip 안전장치를 비교한다.\n4. assembly/topology 8동은 Roofer shell 오류를 유형화한다.\n5. reference accuracy fail 29동은 높이·경사·경계 오차를 분해한다."},
            ],
        },
        "snapshot": {"version": 1, "status": "ready", "datasets": {"headline": headline, "tracks": tracks, "flags": flags, "buildings": buildings}},
        "sources": [source],
    }
    reports = root / "reports"
    reports.mkdir(exist_ok=True)
    (reports / "artifact.json").write_text(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (reports / "TECHNICAL_RETURN.md").write_text(
        "# C2 MVS improvement census 199 technical return\n\n"
        f"- population: 199\n- full AOI: 152\n- major improvement flag: {headline[0]['improvement_flagged']}\n"
        f"- no major technical flag: {headline[0]['no_major_flag']}\n- current-UAS eligible: {ref['exact_no_clip_reference_eligible_count_full_aoi']}\n"
        f"- current-UAS candidate pass/fail: {ref['accuracy_candidate_pass_count']}/{ref['accuracy_candidate_fail_count']}\n"
        "- official_PASS_usable: null\n- scientific_verdict: null\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    build(args.output_root.resolve())


if __name__ == "__main__":
    main()
