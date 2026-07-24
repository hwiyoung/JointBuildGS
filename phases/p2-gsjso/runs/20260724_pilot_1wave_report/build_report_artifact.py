#!/usr/bin/env python3
"""Build the canonical data artifact for the Wave-1 technical readout."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


REPORT_DIR = Path(__file__).resolve().parent
REPO = REPORT_DIR.parents[3]
READOUT_DIR = REPO / "phases/p2-gsjso/runs/20260722_pilot_1wave_readout"
SUMMARY_CSV = READOUT_DIR / "pilot_1wave_summary.csv"
GATES_JSON = READOUT_DIR / "pilot_1wave_machine_gates.json"
DATUM_AUDIT_CSV = REPORT_DIR / "datum_shift_run_audit.csv"

ARM_LABELS = {
    "01": "① 표면",
    "02": "② +사진 통제",
    "03": "③ +평면 약",
    "04a": "④a +평면 강·vision",
    "04b": "④b +평면 강·GT 상한",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise RuntimeError(f"empty report dataset: {path}")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(rows[0]),
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def f(row: dict[str, str], field: str) -> float | None:
    value = row.get(field, "")
    return None if value == "" else float(value)


def i(row: dict[str, str], field: str) -> int | None:
    value = row.get(field, "")
    return None if value == "" else int(value)


def b(row: dict[str, str], field: str) -> bool | None:
    value = row.get(field, "").lower()
    if value == "":
        return None
    if value not in {"true", "false"}:
        raise RuntimeError(f"unexpected boolean {field}={value!r}")
    return value == "true"


def source(
    source_id: str,
    label: str,
    path: str,
    sql: str,
    description: str,
    tables_used: list[str],
    filters: list[str],
    metric_definitions: list[str],
) -> dict[str, Any]:
    return {
        "id": source_id,
        "label": label,
        "path": path,
        "query": {
            "engine": "duckdb",
            "language": "sql",
            "sql": sql,
            "description": description,
            "tables_used": tables_used,
            "filters": filters,
            "metric_definitions": metric_definitions,
        },
    }


def main() -> None:
    summary = [
        row
        for row in read_csv(SUMMARY_CSV)
        if row["stratum"] == "all"
        and row["source_role"] in {"honest", "seg_upperbound"}
    ]
    if len(summary) != 10:
        raise RuntimeError(f"expected 10 all-stratum candidate rows, got {len(summary)}")
    datum = {row["source_id"]: row for row in read_csv(DATUM_AUDIT_CSV)}
    gates = json.loads(GATES_JSON.read_text(encoding="utf-8"))

    arm_seed: list[dict[str, Any]] = []
    rms_comparison: list[dict[str, Any]] = []
    for row in sorted(summary, key=lambda value: value["source_id"]):
        audit = datum[row["source_id"]]
        run_label = f"{row['condition_id']}/{row['seed']}"
        role = "honest" if row["source_role"] == "honest" else "GT upper bound"
        item = {
            "run_label": run_label,
            "arm": ARM_LABELS[row["condition_id"]],
            "condition_id": row["condition_id"],
            "seed": row["seed"],
            "role": role,
            "population_n": i(row, "population_count"),
            "rms_measurable_n": i(row, "rms_measurable_count"),
            "published_rms_m": f(row, "roof_rms_median_m"),
            "datum_corrected_rms_m": float(audit["datum_corrected_rms_median_m"]),
            "datum_corrected_hausdorff_m": float(
                audit["datum_corrected_hausdorff_median_m"]
            ),
            "completeness_median": f(row, "roof_completeness_median"),
            "completeness_ge_0p9_n": i(row, "completeness_ge_0p9_count"),
            "val3dity_valid_n": i(row, "val3dity_valid_count"),
            "lod2_n": i(row, "lod2_count"),
            "rule_a": b(row, "rule_a_rms_below_dense_bar"),
            "rule_b": b(row, "rule_b_structural_improvement"),
            "rule_c": b(row, "rule_c_all_metrics_nonworse"),
            "rule_d": b(row, "rule_d_completeness_floor_0p9"),
            "rule_abcd": b(row, "rule_abcd"),
        }
        arm_seed.append(item)
        rms_comparison.extend(
            [
                {
                    "run_label": run_label,
                    "arm": item["arm"],
                    "seed": row["seed"],
                    "metric_treatment": "공개값 · Z shift 0m",
                    "rms_m": item["published_rms_m"],
                    "rms_measurable_n": item["rms_measurable_n"],
                },
                {
                    "run_label": run_label,
                    "arm": item["arm"],
                    "seed": row["seed"],
                    "metric_treatment": "독립감사 · Z shift -45.7m",
                    "rms_m": item["datum_corrected_rms_m"],
                    "rms_measurable_n": item["rms_measurable_n"],
                },
            ]
        )

    gate_status = [
        {
            "gate": "G1",
            "status": gates["G1"]["status"],
            "requirement": "10런 모두 30×30 결속·containment·SHA 통과",
            "observed": (
                "owner 188/300, zero-roof 112, off-diagonal 0, "
                "containment mismatch 296, SHA mismatch 0"
            ),
        },
        {
            "gate": "G2",
            "status": gates["G2"]["status"],
            "requirement": "honest 4조합 중 두 seed가 A–D를 통과한 유일 승자 1개",
            "observed": "eligible 조건 0, winner null",
        },
        {
            "gate": "G3",
            "status": gates["G3"]["status"],
            "requirement": "G2 승자의 두 seed 최악 RMS 중앙 < 2.0m",
            "observed": "G2 대상 없음 → published null",
        },
        {
            "gate": "G4",
            "status": gates["G4"]["status"],
            "requirement": "10런 20k 완료, collapse/divergence/guard/postprocess abort 0",
            "observed": "10/10 완료, 0/0/0/0",
        },
    ]

    acceptance_status = [
        {
            "rule": "A",
            "requirement": "RMS 30/30 측정 + 중앙 < dense bar 0.640884566m",
            "published_result": "0/8 honest 런",
            "datum_audit_effect": "0/8 유지: 중앙은 낮아졌으나 30/30 미달·bar 초과",
        },
        {
            "rule": "B",
            "requirement": "면수비 편차·valid·LoD2 중 1개가 dense보다 개선",
            "published_result": "5/8 honest 런",
            "datum_audit_effect": "거리 datum과 독립",
        },
        {
            "rule": "C",
            "requirement": "RMS·Hausdorff 포함 전 지표 비열화 없음 + 30/30",
            "published_result": "0/8 honest 런",
            "datum_audit_effect": "missing·valid·LoD2·completeness 실패는 유지",
        },
        {
            "rule": "D",
            "requirement": "전 30동 completeness ≥ max(dense, 0.9); 0.8/0.95 민감도",
            "published_result": "0/8; 민감도도 0/8",
            "datum_audit_effect": "거리 datum과 독립",
        },
        {
            "rule": "E",
            "requirement": "동일 honest 조건 두 seed 모두 A–D 통과",
            "published_result": "0/4 조건",
            "datum_audit_effect": "유지",
        },
    ]

    binding_long: list[dict[str, Any]] = []
    for run in gates["G1"]["runs"]:
        label = f"{run['condition_id']}/{run['seed']}"
        binding_long.extend(
            [
                {
                    "run_label": label,
                    "series": "실제 owner assignment",
                    "building_count": run["owner_assignments"],
                },
                {
                    "run_label": label,
                    "series": "요구값",
                    "building_count": 30,
                },
            ]
        )

    runtime_breakdown = [
        {
            "stage": "20k 학습 10런",
            "hours": 7.5158,
            "note": "2 GPU; canonical 10/10 complete",
        },
        {
            "stage": "체크포인트→기하 추출 10런",
            "hours": 11.157,
            "note": "host-RAM OOM 후 직렬 max_parallel=1",
        },
        {
            "stage": "classifier 실제 벽시계",
            "hours": 1.2211,
            "note": "순수 처리 0.1467h + receipt schema 복구",
        },
        {
            "stage": "Roofer 준비→최종화",
            "hours": 0.2271,
            "note": "Roofer 본체 합계는 0.0616h",
        },
        {
            "stage": "6지표 채점",
            "hours": 0.0783,
            "note": "10런 전체",
        },
        {
            "stage": "aggregate",
            "hours": 0.0998,
            "note": "성공 시도",
        },
        {
            "stage": "binding audit",
            "hours": 0.0694,
            "note": "300 + 9,000행",
        },
        {
            "stage": "publication",
            "hours": 0.0147,
            "note": "최종 발행",
        },
    ]

    seg_gap = [
        {
            "seed": "1001",
            "paired_rms_n": 14,
            "rms_median_delta_m": -2.979875509,
            "hausdorff_median_delta_m": -9.650,
            "completeness_median_delta": 0.1151,
            "lod2_count_delta": 7,
            "valid_count_delta": -7,
        },
        {
            "seed": "1002",
            "paired_rms_n": 15,
            "rms_median_delta_m": 1.915949884,
            "hausdorff_median_delta_m": 14.345,
            "completeness_median_delta": 0.0,
            "lod2_count_delta": -3,
            "valid_count_delta": -1,
        },
    ]

    loss_equivalence = [
        {
            "run_label": "04a/1001",
            "rows_in_0p5_to_2x": 29,
            "defined_rows": 200,
            "rate": 0.145,
            "first_iter": 100,
            "first_ratio": 1.4919,
        },
        {
            "run_label": "04a/1002",
            "rows_in_0p5_to_2x": 25,
            "defined_rows": 200,
            "rate": 0.125,
            "first_iter": 400,
            "first_ratio": 1.9171,
        },
        {
            "run_label": "04b/1001",
            "rows_in_0p5_to_2x": 19,
            "defined_rows": 200,
            "rate": 0.095,
            "first_iter": 100,
            "first_ratio": 1.4247,
        },
        {
            "run_label": "04b/1002",
            "rows_in_0p5_to_2x": 11,
            "defined_rows": 200,
            "rate": 0.055,
            "first_iter": 400,
            "first_ratio": 1.8014,
        },
    ]

    file_guide = [
        {
            "order": 1,
            "file": "pilot_1wave_manifest.json",
            "purpose": "전체 provenance·10개 checkpoint·Wave2 미발사 상태",
        },
        {
            "order": 2,
            "file": "pilot_1wave_machine_gates.json",
            "purpose": "G1–G4 기계 관문 원문",
        },
        {
            "order": 3,
            "file": "pilot_1wave_summary.csv",
            "purpose": "조합×seed 요약; 우선 stratum=all",
        },
        {
            "order": 4,
            "file": "datum_shift_run_audit.csv",
            "purpose": "공개 0m vs canonical -45.7m 독립 재계산",
        },
        {
            "order": 5,
            "file": "binding_audit_receipt.json / binding_audit.csv",
            "purpose": "zero-roof·owner·containment·SHA 결속",
        },
        {
            "order": 6,
            "file": "pilot_1wave_scores.csv",
            "purpose": "30동×13 source 동별 6지표와 missingness",
        },
        {
            "order": 7,
            "file": "pilot_1wave_winner.csv",
            "purpose": "honest 4조합의 2-seed eligibility와 winner null",
        },
        {
            "order": 8,
            "file": "pilot_1wave_seg_upperbound_gap.csv",
            "purpose": "④a vision vs ④b GT 상한 paired gap",
        },
        {
            "order": 9,
            "file": "pilot_1wave_loss_shares_receipt.json / pilot_1wave_loss_shares.csv",
            "purpose": "plane/photo 등가점 검증과 iter별 손실",
        },
        {
            "order": 10,
            "file": "training/pilot_1wave_driver_manifest.json / issues.md",
            "purpose": "학습 시간·guard·OOM 및 복구 이력",
        },
    ]

    headline = [
        {
            "canonical_runs": 10,
            "completed_20k_runs": 10,
            "passed_machine_gates": 1,
            "total_machine_gates": 4,
            "zero_roof_rows": 112,
            "calendar_hours": 33.733,
            "roofer_core_minutes": 3.699,
        }
    ]

    datasets = {
        "headline": headline,
        "gate_status": gate_status,
        "acceptance_status": acceptance_status,
        "arm_seed": arm_seed,
        "rms_comparison": rms_comparison,
        "binding_long": binding_long,
        "runtime_breakdown": runtime_breakdown,
        "seg_gap": seg_gap,
        "loss_equivalence": loss_equivalence,
        "file_guide": file_guide,
    }
    for name, rows in datasets.items():
        write_csv(REPORT_DIR / f"{name}.csv", rows)

    sources = [
        source(
            "published_summary",
            "Wave-1 published all-stratum summary",
            "pilot_1wave_summary.csv",
            (
                "SELECT * FROM read_csv_auto('pilot_1wave_summary.csv') "
                "WHERE stratum='all'"
            ),
            "Loads reviewed all-stratum control and arm-seed summary rows.",
            ["pilot_1wave_summary.csv"],
            ["stratum = all"],
            [
                "Roof RMS and Hausdorff are in metres.",
                "Completeness is a fraction over the locked 30-building population.",
            ],
        ),
        source(
            "machine_gates",
            "Wave-1 machine gates",
            "pilot_1wave_machine_gates.json",
            (
                "SELECT * FROM read_json_auto('pilot_1wave_machine_gates.json')"
            ),
            "Loads the published G1 through G4 gate receipt.",
            ["pilot_1wave_machine_gates.json"],
            [],
            ["All four gates must pass before Wave 2 can launch."],
        ),
        source(
            "datum_audit",
            "Independent canonical datum-shift audit",
            "datum_shift_run_audit.csv",
            "SELECT * FROM read_csv_auto('datum_shift_run_audit.csv')",
            "Recomputes the same published CityJSON with 0m and -45.7m Z shifts.",
            ["datum_shift_run_audit.csv", "datum_shift_building_audit.csv"],
            ["10 candidate arm-seed runs", "locked 30-building population"],
            [
                "Canonical GS-to-reference vertical shift is -45.7m.",
                "RMS medians use buildings that contain parsed roof surfaces.",
            ],
        ),
        source(
            "runtime_audit",
            "Observed Wave-1 runtime audit",
            "runtime_breakdown.csv",
            "SELECT * FROM read_csv_auto('runtime_breakdown.csv')",
            "Loads reviewed wall-clock durations from manifests and receipts.",
            ["runtime_breakdown.csv"],
            ["canonical run and successful postprocess boundaries"],
            [
                "Stage durations use wall-clock time and are not necessarily additive.",
                "Calendar duration from training start to final manifest is 33h44m.",
            ],
        ),
        source(
            "binding_audit",
            "Published binding audit",
            "binding_audit.csv",
            (
                "SELECT * FROM read_csv_auto('binding_audit.csv')"
            ),
            "Loads the 300 building-run binding audit rows.",
            ["binding_audit.csv", "binding_audit_spatial_matrix.csv"],
            ["30 buildings x 10 runs"],
            [
                "A passing run requires 30 diagonal owner assignments and containment.",
                "Receipt and crop-contract SHA mismatches must be zero.",
            ],
        ),
        source(
            "report_tables",
            "Derived review tables",
            "arm_seed.csv",
            "SELECT * FROM read_csv_auto('arm_seed.csv')",
            "Loads reviewed, source-backed rows used in this report.",
            [
                "arm_seed.csv",
                "acceptance_status.csv",
                "seg_gap.csv",
                "loss_equivalence.csv",
                "file_guide.csv",
            ],
            [],
            ["Derived rows preserve the values in the cited canonical receipts."],
        ),
    ]

    manifest = {
        "version": 1,
        "surface": "report",
        "title": "1파 확장 파일럿 기술 검수 보고서",
        "generatedAt": "2026-07-24T00:00:00+09:00",
        "cards": [
            {
                "id": "execution_card",
                "dataset": "headline",
                "sourceId": "machine_gates",
                "metrics": [
                    {
                        "label": "20k 완료 런",
                        "field": "completed_20k_runs",
                        "format": "number",
                    },
                    {
                        "label": "canonical 런",
                        "field": "canonical_runs",
                        "format": "number",
                    },
                ],
            },
            {
                "id": "gate_card",
                "dataset": "headline",
                "sourceId": "machine_gates",
                "metrics": [
                    {
                        "label": "통과 관문",
                        "field": "passed_machine_gates",
                        "format": "number",
                    },
                    {
                        "label": "전체 관문",
                        "field": "total_machine_gates",
                        "format": "number",
                    },
                ],
            },
            {
                "id": "binding_card",
                "dataset": "headline",
                "sourceId": "binding_audit",
                "metrics": [
                    {
                        "label": "zero-roof 행",
                        "field": "zero_roof_rows",
                        "format": "number",
                    }
                ],
            },
            {
                "id": "elapsed_card",
                "dataset": "headline",
                "sourceId": "runtime_audit",
                "metrics": [
                    {
                        "label": "달력 경과",
                        "field": "calendar_hours",
                        "format": "number",
                    },
                    {
                        "label": "Roofer 본체",
                        "field": "roofer_core_minutes",
                        "format": "number",
                    },
                ],
            },
        ],
        "charts": [
            {
                "id": "rms_treatment_chart",
                "title": "Arm-seed별 공개 RMS와 datum 보정 RMS",
                "type": "bar",
                "dataset": "rms_comparison",
                "sourceId": "datum_audit",
                "encodings": {
                    "x": {
                        "field": "run_label",
                        "type": "ordinal",
                        "label": "Arm / seed",
                    },
                    "y": {
                        "field": "rms_m",
                        "type": "quantitative",
                        "label": "RMS 중앙",
                        "unit": "m",
                    },
                    "color": {
                        "field": "metric_treatment",
                        "type": "nominal",
                        "label": "Z datum 처리",
                    },
                    "tooltip": [
                        {
                            "field": "rms_measurable_n",
                            "type": "quantitative",
                            "label": "RMS 측정 동",
                        }
                    ],
                },
                "legend": {"title": "Z datum 처리", "position": "bottom"},
            },
            {
                "id": "binding_chart",
                "title": "Arm-seed별 owner assignment 수",
                "type": "bar",
                "dataset": "binding_long",
                "sourceId": "binding_audit",
                "encodings": {
                    "x": {
                        "field": "run_label",
                        "type": "ordinal",
                        "label": "Arm / seed",
                    },
                    "y": {
                        "field": "building_count",
                        "type": "quantitative",
                        "label": "건물 수",
                        "unit": "동",
                    },
                    "color": {
                        "field": "series",
                        "type": "nominal",
                        "label": "구분",
                    },
                },
                "legend": {"title": "구분", "position": "bottom"},
            },
            {
                "id": "runtime_chart",
                "title": "파이프라인 단계별 관측 벽시계",
                "type": "bar",
                "dataset": "runtime_breakdown",
                "sourceId": "runtime_audit",
                "encodings": {
                    "x": {"field": "stage", "type": "ordinal", "label": "단계"},
                    "y": {
                        "field": "hours",
                        "type": "quantitative",
                        "label": "벽시계",
                        "unit": "시간",
                    },
                },
            },
        ],
        "tables": [
            {
                "id": "gate_table",
                "title": "조건부 2파 기계 관문",
                "dataset": "gate_status",
                "sourceId": "machine_gates",
                "defaultSort": {"field": "gate", "direction": "asc"},
                "columns": [
                    {"field": "gate", "label": "관문", "type": "text"},
                    {"field": "status", "label": "상태", "type": "text"},
                    {"field": "requirement", "label": "요구", "type": "text"},
                    {"field": "observed", "label": "관측", "type": "text"},
                ],
            },
            {
                "id": "acceptance_table",
                "title": "A–E 성공·승자 규칙",
                "dataset": "acceptance_status",
                "sourceId": "report_tables",
                "defaultSort": {"field": "rule", "direction": "asc"},
                "columns": [
                    {"field": "rule", "label": "규칙", "type": "text"},
                    {"field": "requirement", "label": "합격조건", "type": "text"},
                    {
                        "field": "published_result",
                        "label": "공개 결과",
                        "type": "text",
                    },
                    {
                        "field": "datum_audit_effect",
                        "label": "datum 감사 후",
                        "type": "text",
                    },
                ],
            },
            {
                "id": "arm_table",
                "title": "Arm-seed별 30동 결과",
                "dataset": "arm_seed",
                "sourceId": "published_summary",
                "defaultSort": {"field": "run_label", "direction": "asc"},
                "columns": [
                    {"field": "run_label", "label": "Arm/seed", "type": "text"},
                    {"field": "role", "label": "지위", "type": "text"},
                    {
                        "field": "rms_measurable_n",
                        "label": "RMS 측정",
                        "type": "number",
                        "unit": "/30",
                    },
                    {
                        "field": "datum_corrected_rms_m",
                        "label": "datum 보정 RMS",
                        "type": "number",
                        "format": "number",
                        "unit": "m",
                    },
                    {
                        "field": "completeness_median",
                        "label": "완전율 중앙",
                        "type": "percent",
                        "format": "percent",
                    },
                    {
                        "field": "val3dity_valid_n",
                        "label": "valid",
                        "type": "number",
                        "unit": "/30",
                    },
                    {
                        "field": "lod2_n",
                        "label": "LoD2",
                        "type": "number",
                        "unit": "/30",
                    },
                ],
            },
            {
                "id": "seg_gap_table",
                "title": "④b GT 상한 − ④a vision paired gap",
                "dataset": "seg_gap",
                "sourceId": "report_tables",
                "defaultSort": {"field": "seed", "direction": "asc"},
                "columns": [
                    {"field": "seed", "label": "Seed", "type": "text"},
                    {
                        "field": "paired_rms_n",
                        "label": "paired n",
                        "type": "number",
                    },
                    {
                        "field": "rms_median_delta_m",
                        "label": "RMS Δ 중앙",
                        "type": "number",
                        "format": "number",
                        "unit": "m",
                    },
                    {
                        "field": "hausdorff_median_delta_m",
                        "label": "Hausdorff Δ 중앙",
                        "type": "number",
                        "format": "number",
                        "unit": "m",
                    },
                    {
                        "field": "completeness_median_delta",
                        "label": "완전율 Δ 중앙",
                        "type": "number",
                    },
                    {
                        "field": "lod2_count_delta",
                        "label": "LoD2 Δ",
                        "type": "number",
                    },
                    {
                        "field": "valid_count_delta",
                        "label": "valid Δ",
                        "type": "number",
                    },
                ],
            },
            {
                "id": "loss_table",
                "title": "강 arm plane/photo 등가점 행",
                "dataset": "loss_equivalence",
                "sourceId": "report_tables",
                "defaultSort": {"field": "run_label", "direction": "asc"},
                "columns": [
                    {"field": "run_label", "label": "Arm/seed", "type": "text"},
                    {
                        "field": "rows_in_0p5_to_2x",
                        "label": "허용 행",
                        "type": "number",
                    },
                    {
                        "field": "defined_rows",
                        "label": "정의 행",
                        "type": "number",
                    },
                    {
                        "field": "rate",
                        "label": "유지율",
                        "type": "percent",
                        "format": "percent",
                    },
                    {
                        "field": "first_iter",
                        "label": "최초 iter",
                        "type": "number",
                    },
                    {
                        "field": "first_ratio",
                        "label": "최초 ratio",
                        "type": "number",
                        "format": "number",
                    },
                ],
            },
            {
                "id": "file_table",
                "title": "원본 파일 권장 읽기 순서",
                "dataset": "file_guide",
                "sourceId": "report_tables",
                "defaultSort": {"field": "order", "direction": "asc"},
                "columns": [
                    {"field": "order", "label": "#", "type": "number"},
                    {"field": "file", "label": "파일", "type": "text"},
                    {"field": "purpose", "label": "확인 내용", "type": "text"},
                ],
            },
        ],
        "sources": [
            {"id": item["id"], "label": item["label"], "path": item["path"]}
            for item in sources
        ],
        "blocks": [
            {
                "id": "title",
                "type": "markdown",
                "body": "# 1파 확장 파일럿 기술 검수 보고서",
            },
            {
                "id": "executive_summary",
                "type": "markdown",
                "body": (
                    "## 결론\n\n"
                    "**1파 계산과 후처리는 완료됐지만 합격은 아니다.** canonical 10런은 "
                    "모두 20k 학습·Roofer·채점을 끝냈고 G4는 통과했다. 그러나 G1 결속, "
                    "G2 유일 승자, G3 2m 관문이 실패해 2파는 발사되지 않았다.\n\n"
                    "또한 공개 RMS 44.8–48.8m는 GS에 필요한 -45.7m 수직 datum 변환을 "
                    "채점기가 적용하지 않은 값이다. 독립 재계산에서 0m 경로는 공개값과 "
                    "최대 5e-10m까지 일치했고, -45.7m 적용 후 ①–③은 0.90–1.61m였다. "
                    "따라서 공개 거리값을 성능 결론에 그대로 쓰면 안 된다. 다만 30동 "
                    "완결성, zero-roof, containment, valid·LoD2·completeness 실패는 datum과 "
                    "독립이므로 승자 없음과 2파 미발사는 유지된다."
                ),
            },
            {
                "id": "headline_metrics",
                "type": "metric-strip",
                "cardIds": [
                    "execution_card",
                    "gate_card",
                    "binding_card",
                    "elapsed_card",
                ],
            },
            {
                "id": "completion_scope",
                "type": "markdown",
                "body": (
                    "## 무엇이 완료됐고 무엇이 남았나\n\n"
                    "학습은 5조건×2seed=10런 모두 20k full-state checkpoint까지 완료됐다. "
                    "후처리도 추출·분류·Roofer 10회·val3dity·6지표·binding audit·발행까지 "
                    "끝났다. 즉 미완료는 계산이 아니라 **합격조건 충족과 과학적으로 유효한 "
                    "최종 재채점**이다. Wave 2 launch는 false다."
                ),
            },
            {
                "id": "gate_table_block",
                "type": "table",
                "tableId": "gate_table",
                "layout": "full",
            },
            {
                "id": "acceptance_heading",
                "type": "markdown",
                "body": (
                    "## 합격조건과 미충족 이유\n\n"
                    "A–D를 한 seed가 모두 만족하고, 같은 honest 조합의 두 seed가 이를 "
                    "재현해야 E가 성립한다. ④b는 GT 세그 상한이라 승자에서 제외된다."
                ),
            },
            {
                "id": "acceptance_table_block",
                "type": "table",
                "tableId": "acceptance_table",
                "layout": "full",
            },
            {
                "id": "datum_heading",
                "type": "markdown",
                "body": (
                    "## 거리 채점의 수직 datum 누락\n\n"
                    "canonical 거리 코드에는 GS prediction을 LoD2 reference에 맞추는 "
                    "-45.7m 이동이 잠겨 있다. 그러나 1파 scoring 경로는 prediction을 "
                    "그대로 compare_building에 넘기고 score_time_z_shift_m=0.0을 기록했다. "
                    "아래 재계산은 원본 CityJSON·참조·표본 순서를 그대로 두고 Z 이동만 "
                    "바꾼 읽기 전용 감사다."
                ),
            },
            {
                "id": "rms_chart_block",
                "type": "chart",
                "chartId": "rms_treatment_chart",
                "layout": "full",
            },
            {
                "id": "binding_heading",
                "type": "markdown",
                "body": (
                    "## G1 결속 관문\n\n"
                    "crop-contract와 receipt SHA 불일치는 0이고, 생성된 roof의 "
                    "off-diagonal owner assignment도 0이다. 즉 예전 crop/receipt 오결속은 "
                    "재현되지 않았다. 실패 원인은 300 building-run 중 112 zero-roof, "
                    "owner assignment 188/300, containment mismatch 296이다."
                ),
            },
            {
                "id": "binding_chart_block",
                "type": "chart",
                "chartId": "binding_chart",
                "layout": "full",
            },
            {
                "id": "arm_heading",
                "type": "markdown",
                "body": (
                    "## 전체 arm-seed 결과\n\n"
                    "RMS 측정 분모가 14–22/30으로 서로 다르므로 중앙값만으로 랭킹하면 "
                    "안 된다. datum 보정 후 measurable subset에서 ②가 0.903/0.907m로 "
                    "가장 낮지만, 18–20동만 측정됐고 A–D를 통과하지 않아 승자로 볼 수 없다."
                ),
            },
            {
                "id": "arm_table_block",
                "type": "table",
                "tableId": "arm_table",
                "layout": "full",
            },
            {
                "id": "seg_heading",
                "type": "markdown",
                "body": (
                    "## 세그 상한과 평면 손실\n\n"
                    "④b−④a gap은 seed 1001에서 개선, seed 1002에서 악화해 방향이 "
                    "일관되지 않았다. plane/photo roof-share 0.5–2× 행은 강 arm 네 런 "
                    "모두 최소 1개 있어 발주문의 존재 조건은 통과했다. 다만 유지율은 "
                    "5.5–14.5%라 지속적 등가점으로 해석할 수 없다."
                ),
            },
            {
                "id": "seg_table_block",
                "type": "table",
                "tableId": "seg_gap_table",
                "layout": "full",
            },
            {
                "id": "loss_table_block",
                "type": "table",
                "tableId": "loss_table",
                "layout": "full",
            },
            {
                "id": "runtime_heading",
                "type": "markdown",
                "body": (
                    "## 왜 오래 걸렸나\n\n"
                    "학습 시작부터 최종 manifest까지 약 33시간 44분이었다. 오류 없는 "
                    "현재 구조의 10런 전체 예상은 약 19시간 36분이다. 가장 큰 병목은 "
                    "Roofer가 아니라 체크포인트→장면 기하 추출 11시간 9분이다.\n\n"
                    "두 extractor를 GPU 0·1에서 병렬로 돌렸을 때 합산 host RSS가 약 "
                    "45.3GiB에 도달하고 swap이 소진되어 exit 137이 발생했다. CUDA VRAM "
                    "OOM이 아니라 host-RAM OOM이다. 복구 후 max_parallel=1, 런당 24GiB, "
                    "swap 0으로 10런을 직렬 재추출했다. Roofer 본체 10회 합계는 3분 "
                    "42초뿐이었다. classifier nested receipt 복구와 aggregate 반올림 "
                    "복구도 일회성 시간을 더했다."
                ),
            },
            {
                "id": "runtime_chart_block",
                "type": "chart",
                "chartId": "runtime_chart",
                "layout": "full",
            },
            {
                "id": "methodology",
                "type": "markdown",
                "body": (
                    "## 방법과 한계\n\n"
                    "공개 gate·summary·scores는 변경하지 않았다. datum 감사 CSV만 별도 "
                    "생성했으며 같은 188개 measurable building-run에서 공개 0m 계산을 "
                    "수치적으로 재현했다. corrected RMS는 공식 재발행값이 아니고 원인 "
                    "규명용이다. A–E와 G1–G4를 다시 판정하려면 scoring 코드에 canonical "
                    "shift를 적용하고 300행 전체를 재집계해야 한다. G1의 zero-roof와 "
                    "containment 실패는 이 거리 재채점으로 해결되지 않는다."
                ),
            },
            {
                "id": "next_steps",
                "type": "markdown",
                "body": (
                    "## 다음 작업\n\n"
                    "1. scoring 경로에 source별 canonical Z shift를 적용하고 기존 "
                    "CityJSON을 재채점한다. 재학습·Roofer 재실행은 필요 없다.\n\n"
                    "2. 112 zero-roof와 296 containment mismatch를 building/run별로 "
                    "분해해 readout·footprint geometry 문제를 고친다. 먼저 기존 "
                    "checkpoint/scene geometry로 재후처리하고, 입력 자체 결함이 확인될 "
                    "때만 해당 런 재학습을 검토한다.\n\n"
                    "3. G1 통과 후 A–E, G2, G3를 재집계한다. 그 전에는 ②를 포함한 어떤 "
                    "arm도 승자로 확정하지 않고 Wave 2를 발사하지 않는다."
                ),
            },
            {
                "id": "files_heading",
                "type": "markdown",
                "body": (
                    "## 봐야 할 파일\n\n"
                    "아래 순서로 보면 실행 완료 여부, 관문 실패, 조합별 결과, 결속과 "
                    "손실 로그를 가장 빠르게 대조할 수 있다. 원본 readout 파일은 "
                    "`../20260722_pilot_1wave_readout/`, datum 감사 파일은 이 보고서 "
                    "디렉터리에 있다."
                ),
            },
            {
                "id": "file_table_block",
                "type": "table",
                "tableId": "file_table",
                "layout": "full",
            },
            {
                "id": "further_questions",
                "type": "markdown",
                "body": (
                    "## 추가 확인 질문\n\n"
                    "남은 핵심은 두 가지다: containment mismatch가 CityJSON footprint "
                    "형상·좌표 문제인지, owner 판정 규칙 문제인지; zero-roof가 classifier "
                    "분류 소실인지 Roofer skip/fallback인지. 둘을 분리하면 재학습 없이 "
                    "복구 가능한 범위를 결정할 수 있다."
                ),
            },
        ],
    }

    artifact = {
        "surface": "report",
        "manifest": manifest,
        "snapshot": {
            "version": 1,
            "generatedAt": "2026-07-24T00:00:00+09:00",
            "status": "ready",
            "datasets": datasets,
        },
        "sources": sources,
        "package_info": {
            "artifact_id": "jointbuildgs-wave1-technical-readout-20260724",
            "source_readout": "20260722_pilot_1wave_readout",
            "assessment": "needs_revision",
        },
    }
    (REPORT_DIR / "artifact.json").write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
