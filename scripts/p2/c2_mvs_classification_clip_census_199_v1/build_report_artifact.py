#!/usr/bin/env python3
"""Build the canonical Data Analytics report artifact for the C2 clip census."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


def write_new(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        stream.write("\n")


def number(row: dict[str, str], field: str) -> float | None:
    return float(row[field]) if row.get(field) else None


def selected_case(rows: list[dict[str, str]], stable_id: str, note: str) -> dict[str, Any]:
    row = next(value for value in rows if value["stable_id"] == stable_id)
    return {
        "building": stable_id.removeprefix("DEBY_LOD2_"),
        "raw_coverage": number(row, "all_point_coverage_0p5m"),
        "class6_coverage": number(row, "class6_coverage_0p5m"),
        "clip_true_coverage": number(row, "clip_true_lod22_xy_coverage"),
        "no_clip_coverage": number(row, "clip_false_lod22_xy_coverage"),
        "no_clip_rmse_m": number(row, "clip_false_rf_rmse_lod22"),
        "no_clip_result": row["clip_false_reason"],
        "diagnostic_role": note,
    }


def build(output_root: Path) -> None:
    summary = json.loads((output_root / "results/summary_v1.json").read_text(encoding="utf-8"))
    rows = list(csv.DictReader((output_root / "results/building_classification_clip_census_v1.csv").open(encoding="utf-8")))
    support = summary["support_grid_full_aoi"]
    clip = summary["clip_effect_full_aoi"]
    rmse = summary["rmse_input_fit_full_aoi"]
    transitions = summary["matched_status_transition_counts_full_aoi"]

    denominator = summary["fully_inside_roofer_aoi_count"]
    valid_both = transitions["technical_valid_lod22->technical_valid_lod22"]
    unusable_both = transitions["rf_pointcloud_unusable->rf_pointcloud_unusable"]
    valid_recovery = transitions["missing_lod22_geometry->technical_valid_lod22"] + transitions["val3dity_invalid->technical_valid_lod22"]
    invalid_after = transitions["missing_lod22_geometry->val3dity_invalid"] + transitions["technical_valid_lod22->val3dity_invalid"] + transitions["val3dity_invalid->val3dity_invalid"]
    outcome_rows = [
        {"outcome": "Valid in both arms", "count": valid_both, "share": valid_both / denominator},
        {"outcome": "Point cloud unusable in both", "count": unusable_both, "share": unusable_both / denominator},
        {
            "outcome": "Valid only after no-clip",
            "count": valid_recovery,
            "share": valid_recovery / denominator,
        },
        {
            "outcome": "Invalid after no-clip",
            "count": invalid_after,
            "share": invalid_after / denominator,
        },
    ]
    sensitivity_rows = []
    for threshold in (10, 25, 50):
        sensitivity_rows.extend([
            {
                "threshold": f"≥{threshold} pp",
                "series": "All-point minus class-6 support gap",
                "count": support["coverage_gap_sensitivity_counts"][f"ge_{threshold}pp"],
                "denominator": 152,
            },
            {
                "threshold": f"≥{threshold} pp",
                "series": "No-clip LoD2 coverage gain",
                "count": clip["coverage_gain_sensitivity_counts"][f"ge_{threshold}pp"],
                "denominator": 152,
            },
        ])
    transition_rows = [
        {"clip_true": key.split("->", 1)[0], "clip_false": key.split("->", 1)[1], "count": count}
        for key, count in transitions.items()
    ]
    cases = [
        selected_case(rows, "DEBY_LOD2_42364663", "No-clip valid recovery but 12.11 m input-fit RMSE"),
        selected_case(rows, "DEBY_LOD2_4907508", "No-clip valid recovery but 4.65 m input-fit RMSE"),
        selected_case(rows, "DEBY_LOD2_42364659", "Severe class-support loss; full coverage but 4.09 m RMSE"),
        selected_case(rows, "DEBY_LOD2_4906982", "Severe class-support loss and clip-driven fragmentation"),
        selected_case(rows, "DEBY_LOD2_4908048", "Low raw support; no-clip reaches full area but remains invalid"),
        selected_case(rows, "DEBY_LOD2_4907515", "Full raw/class-6 support; topology remains invalid"),
    ]
    headline = [{
        "valid_recoveries": clip["valid_lod22_recovery_count"],
        "validity_losses": clip["valid_lod22_loss_count"],
        "severe_class_support_loss": support["high_raw_ge_90pct_and_class6_lt_50pct_count"],
        "rmse_no_clip_median_m": rmse["clip_false_median_m"],
        "rmse_clip_true_median_m": rmse["clip_true_median_m"],
        "full_aoi_denominator": summary["fully_inside_roofer_aoi_count"],
    }]

    source_summary = {
        "id": "census_summary",
        "label": "C2 classification and clip census summary",
        "path": "results/summary_v1.json",
        "query": {
            "engine": "duckdb",
            "language": "sql",
            "description": "Loads the reviewed census summary snapshot.",
            "sql": "SELECT * FROM read_json_auto('results/summary_v1.json')",
            "tables_used": ["results/summary_v1.json"],
        },
    }
    source_buildings = {
        "id": "census_buildings",
        "label": "C2 building-level classification and clip census",
        "path": "results/building_classification_clip_census_v1.csv",
        "query": {
            "engine": "duckdb",
            "language": "sql",
            "description": "Loads the reviewed 199-row building census.",
            "sql": "SELECT * FROM read_csv_auto('results/building_classification_clip_census_v1.csv', header=true)",
            "tables_used": ["results/building_classification_clip_census_v1.csv"],
        },
    }
    title = "MVS 분류와 terrain clipping: 199동 진단"
    artifact = {
        "surface": "report",
        "manifest": {
            "version": 1,
            "surface": "report",
            "title": title,
            "description": "동결 C2 MVS class-2/6 입력에서 terrain clipping과 분류지원 손실을 분리한 비확증 기술 진단",
            "generatedAt": summary["created_utc"],
            "sources": [source_summary, source_buildings],
            "cards": [
                {
                    "id": "valid_recovery",
                    "description": "역사적 AOI 내부 152동에서 no-clip으로 val3dity-valid LoD2.2가 된 건물 수",
                    "dataset": "headline",
                    "sourceId": "census_summary",
                    "metrics": [
                        {"label": "Valid LoD2 회복", "field": "valid_recoveries", "format": "number"},
                        {"label": "반대로 validity 손실", "field": "validity_losses", "format": "number"},
                    ],
                },
                {
                    "id": "class_support_loss",
                    "description": "전체점 격자지원은 90% 이상이지만 class-6 지원은 50% 미만인 건물 수",
                    "dataset": "headline",
                    "sourceId": "census_summary",
                    "metrics": [
                        {"label": "심한 분류지원 손실", "field": "severe_class_support_loss", "format": "number"},
                        {"label": "AOI 내부 분모", "field": "full_aoi_denominator", "format": "number"},
                    ],
                },
                {
                    "id": "rmse_no_clip",
                    "description": "양쪽 arm 모두 RMSE가 있는 AOI 내부 114동의 Roofer 입력 적합도 중앙값",
                    "dataset": "headline",
                    "sourceId": "census_summary",
                    "metrics": [
                        {"label": "No-clip RMSE 중앙값", "field": "rmse_no_clip_median_m", "format": "number", "unit": "m"},
                        {"label": "Clip=true 중앙값", "field": "rmse_clip_true_median_m", "format": "number", "unit": "m"},
                    ],
                },
            ],
            "charts": [
                {
                    "id": "matched_outcomes",
                    "title": "Matched clip 결과 분해",
                    "subtitle": "역사적 Roofer AOI 안에 완전히 포함된 152동",
                    "type": "horizontalBar",
                    "dataset": "outcomes",
                    "sourceId": "census_summary",
                    "encodings": {
                        "x": {"field": "outcome", "type": "nominal", "label": "결과"},
                        "y": {"field": "count", "type": "quantitative", "label": "건물 수"},
                        "tooltip": [{"field": "share", "type": "quantitative", "label": "비율", "format": "percent"}],
                    },
                    "yAxisTitle": "건물 수",
                    "valueFormat": "number",
                    "layout": "full",
                },
                {
                    "id": "sensitivity",
                    "title": "분류지원 손실과 no-clip 면적 회복 민감도",
                    "subtitle": "10·25·50 percentage-point 진단 band, 분모 152동",
                    "type": "bar",
                    "dataset": "sensitivity",
                    "sourceId": "census_summary",
                    "encodings": {
                        "x": {"field": "threshold", "type": "ordinal", "label": "진단 band"},
                        "y": {"field": "count", "type": "quantitative", "label": "건물 수"},
                        "color": {"field": "series", "type": "nominal", "label": "지표"},
                    },
                    "yAxisTitle": "건물 수",
                    "valueFormat": "number",
                    "layout": "full",
                },
            ],
            "tables": [
                {
                    "id": "diagnostic_cases",
                    "title": "대표 진단 건물",
                    "subtitle": "면적 회복과 RMSE·topology가 서로 다른 사례",
                    "dataset": "cases",
                    "sourceId": "census_buildings",
                    "defaultSort": {"field": "no_clip_rmse_m", "direction": "desc"},
                    "density": "comfortable",
                    "layout": "full",
                    "columns": [
                        {"field": "building", "label": "건물", "type": "text"},
                        {"field": "raw_coverage", "label": "전체점 지원", "format": "percent"},
                        {"field": "class6_coverage", "label": "class-6 지원", "format": "percent"},
                        {"field": "clip_true_coverage", "label": "clip 면적", "format": "percent"},
                        {"field": "no_clip_coverage", "label": "no-clip 면적", "format": "percent"},
                        {"field": "no_clip_rmse_m", "label": "no-clip RMSE", "format": "number", "unit": "m"},
                        {"field": "no_clip_result", "label": "no-clip 결과", "type": "text"},
                        {"field": "diagnostic_role", "label": "해석", "type": "text"},
                    ],
                },
                {
                    "id": "transition_detail",
                    "title": "Matched 상태 전이",
                    "subtitle": "clip=true에서 clip=false로 바뀐 AOI 내부 152동",
                    "dataset": "transitions",
                    "sourceId": "census_summary",
                    "defaultSort": {"field": "count", "direction": "desc"},
                    "density": "compact",
                    "layout": "full",
                    "columns": [
                        {"field": "clip_true", "label": "clip=true", "type": "text"},
                        {"field": "clip_false", "label": "clip=false", "type": "text"},
                        {"field": "count", "label": "건물 수", "format": "number"},
                    ],
                },
            ],
            "blocks": [
                {"id": "title", "type": "markdown", "body": f"# {title}"},
                {
                    "id": "technical_summary",
                    "type": "markdown",
                    "sourceId": "census_summary",
                    "body": "## 핵심 결론\n\n**No-clip은 실패 15동의 LoD2 면적을 복구하지만, 정확도를 일반적으로 개선하지는 않는다.** 전체 199동에서 technical-valid LoD2.2는 103동에서 114동으로 늘었다. 원인 귀속이 가능한 AOI 내부 152동에서는 10동이 valid로 전환되고 2동은 반대로 invalid가 되어 순증가는 8동이다. 그러나 RMSE 중앙값은 1.360m에서 1.466m로 소폭 증가했고, no-clip 뒤에도 RMSE 4m 이상인 건물이 5동 남았다. 따라서 면적 회복, topology validity, 입력 적합도는 별도 지표로 다뤄야 한다.",
                },
                {"id": "headline_metrics", "type": "metric-strip", "cardIds": ["valid_recovery", "class_support_loss", "rmse_no_clip"]},
                {
                    "id": "outcome_interpretation",
                    "type": "markdown",
                    "sourceId": "census_summary",
                    "body": "## No-clip은 10동을 valid로 바꾸지만 38동의 point-support 실패는 건드리지 못한다\n\nAOI 내부 152동은 `양쪽 valid 91 / pointcloud_unusable 유지 38 / no-clip valid 전환 10 / no-clip에서도 invalid 13`으로 정확히 분해된다. `rf_pointcloud_unusable` 38동이 그대로 남았다는 것은 clip 설정이 분류 후 class-6 지원 부족을 고치는 수단이 아니라는 뜻이다. 반대로 no-clip에서 valid가 된 10동은 terrain clipping이 실패 전환에 직접 관여한 후보군이다.",
                },
                {"id": "outcome_chart", "type": "chart", "chartId": "matched_outcomes", "layout": "full"},
                {
                    "id": "classification_interpretation",
                    "type": "markdown",
                    "sourceId": "census_summary",
                    "body": "## 분류지원 손실과 clip 민감도는 강하게 겹치지만 같은 문제는 아니다\n\n전체점 대비 class-6 격자지원 손실이 10/25/50%p 이상인 건물은 24/20/10동이고, no-clip LoD2 면적 증가가 같은 기준 이상인 건물은 23/22/20동이다. 두 집합의 중복은 각각 18/15/7동이다. SMRF 오분류가 terrain clipping을 유발하는 경로는 뚜렷하지만, 모든 clip 민감 건물이 심한 class-support 손실을 보이는 것은 아니며 모든 분류손실이 no-clip으로 해결되는 것도 아니다.",
                },
                {"id": "sensitivity_chart", "type": "chart", "chartId": "sensitivity", "layout": "full"},
                {
                    "id": "case_interpretation",
                    "type": "markdown",
                    "sourceId": "census_buildings",
                    "body": "## 4906982는 면적 회복과 형상 정확도가 분리되는 대표 사례다\n\n4906982는 전체점 지원 100%인데 class-6 지원은 35.0%다. clip=true에서는 6 parts와 14.78% 면적, RMSE 6.5477m였고 no-clip에서는 1 part와 거의 100% 면적, RMSE 4.0239m였다. 반면 4907515는 전체점과 class-6 지원이 모두 100%인데 양쪽 모두 topology invalid이고, 4908048은 전체점 지원부터 40.1%라 no-clip으로 면적만 채워도 invalid shell이 남는다.",
                },
                {"id": "case_table", "type": "table", "tableId": "diagnostic_cases", "layout": "full"},
                {
                    "id": "scope_definitions",
                    "type": "markdown",
                    "sourceId": "census_summary",
                    "body": "## 비교 범위와 지표 정의\n\n모집단은 동결 `U_target=199`이며, 역사적 Roofer AOI에 완전히 포함된 152동을 원인 귀속 분모로 사용했다. 경계를 가로지르는 47동은 표에는 보존하되 귀속 집계에서는 제외했다. `전체점 지원`은 동결 classified MVS cloud의 모든 class가 footprint 내부 0.5m 격자를 차지한 비율이고, `class-6 지원`은 그중 building=6 점이 차지한 비율이다. LoD2 면적은 출력 GroundSurface XY와 같은 shared footprint XY의 교차면적 비율이다.",
                },
                {
                    "id": "methodology",
                    "type": "markdown",
                    "sourceId": "census_summary",
                    "body": "## 동일 입력 matched diagnostic\n\nMVS dense geometry와 SMRF 분류는 다시 실행하지 않았다. 동일한 동결 class-2/6 LAZ, 동일한 199 footprint, 동일한 Roofer 1.0.0 image와 `jobs=1`을 사용하고 `clip-terrain`만 true/false로 바꿨다. formal 결과와 새 clip=true 재현은 199동 상태가 모두 일치했다. RMSE 최대 차이는 0.0011m, 면적 최대 차이는 0.58%p로 상태 해석을 바꾸지 않았다.",
                },
                {"id": "transition_table", "type": "table", "tableId": "transition_detail", "layout": "full"},
                {
                    "id": "limitations",
                    "type": "markdown",
                    "sourceId": "census_summary",
                    "body": "## 한계와 robustness\n\n이 분석은 분류와 clipping의 기술적 영향만 진단한다. 0.5m support gap은 SMRF 분류손실 proxy이며 모든 비-class-6 점이 실제 지붕이라는 뜻은 아니다. `rf_rmse_lod22`는 출력과 입력 cloud의 적합도이지 독립 LoD2 GT 오차가 아니다. 따라서 no-clip valid 114동을 곧바로 성공 건물로 세면 안 되며, completeness·reference RMSE·roof-structure와 함께 평가해야 한다. 과학적 판정과 공식 `PASS_usable`은 모두 null이다.",
                },
                {
                    "id": "next_steps",
                    "type": "markdown",
                    "body": "## 다음 단계\n\n1. `pointcloud_unusable` 50동은 raw-support 부족과 class-6 손실을 먼저 분리한다.\n2. no-clip valid 전환 10동은 reference completeness와 독립 RMSE를 계산해 실제 성공 전환 여부를 확인한다.\n3. no-clip에서도 invalid인 13동은 Roofer assembly/topology 군으로 별도 처리한다.\n4. MVS 전용 classifier는 개발군에서 전역 파라미터를 동결한 별도 best-effort arm으로 추가하고 현재 공통-SMRF arm은 유지한다.",
                },
                {
                    "id": "further_questions",
                    "type": "markdown",
                    "body": "## 남은 질문\n\n- `pointcloud_unusable` 중 raw MVS가 충분한데 class-6만 부족한 건물은 정확히 몇 동인가?\n- no-clip valid 전환 10동 중 reference completeness와 독립 RMSE까지 개선되는 건물은 몇 동인가?\n- class-support gap과 texture/시점 지원 부족을 결합하면 50동의 미사용 원인을 얼마나 더 분해할 수 있는가?",
                },
            ],
        },
        "snapshot": {
            "version": 1,
            "generatedAt": summary["created_utc"],
            "status": "ready",
            "datasets": {
                "headline": headline,
                "outcomes": outcome_rows,
                "sensitivity": sensitivity_rows,
                "transitions": transition_rows,
                "cases": cases,
            },
        },
        "sources": [source_summary, source_buildings],
        "package_info": {
            "task_id": summary["task_id"],
            "snapshot_sha256": "4465d9e0053ea012358b88216c75e2a4c05721dd687cb68deb87387b195ae414",
        },
    }
    notes = {
        "audience": "technical",
        "delivery_mode": "html",
        "delivery_reason": "Work Mode detected; full Sites lifecycle is unavailable",
        "required_structure_mapping": {
            "title": "title",
            "technical_summary": "technical_summary",
            "key_findings_with_visual_evidence": ["outcome_interpretation", "outcome_chart", "classification_interpretation", "sensitivity_chart", "case_interpretation", "case_table"],
            "scope_data_metric_definitions": "scope_definitions",
            "methodology": ["methodology", "transition_table"],
            "limitations_uncertainty_robustness": "limitations",
            "recommended_next_steps": "next_steps",
            "further_questions": "further_questions",
        },
        "chart_map": [
            {
                "section": "matched outcomes",
                "question": "How do fully-contained buildings partition after changing only clip-terrain?",
                "family": "comparison",
                "type": "horizontalBar",
                "fields": ["outcome", "count", "share"],
                "claim": "No-clip recovers 10 valid buildings but leaves 38 pointcloud-unusable and 13 invalid",
                "palette": "single-root preferred",
            },
            {
                "section": "classification and clip sensitivity",
                "question": "How many buildings exceed 10/25/50pp diagnostic bands?",
                "family": "grouped comparison",
                "type": "bar",
                "fields": ["threshold", "series", "count", "denominator"],
                "claim": "Class-support loss and clip recovery overlap but are not equivalent",
                "palette": "hard two-root cap",
            },
        ],
        "validation": {
            "data_quality": "PASS: 199 rows and unique IDs; 20 missing features all AOI-crossing; status totals and receipt hashes reconciled",
            "formal_replay": "199/199 status reasons match; max RMSE difference 0.0010232m; max coverage difference 0.5704pp",
            "confidence": "share with caveats",
        },
        "omissions": {
            "reference_completeness_and_independent_rmse": "not computed in this clip/classification diagnostic",
            "raw_vs_class cause for all pointcloud_unusable rows": "requires a second-stage support attribution beyond Roofer status",
        },
    }
    write_new(output_root / "reports/artifact.json", artifact)
    write_new(output_root / "reports/source_notes_v1.json", notes)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    build(args.output_root)


if __name__ == "__main__":
    main()
