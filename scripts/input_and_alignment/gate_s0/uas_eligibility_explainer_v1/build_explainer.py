#!/usr/bin/env python3
"""Build a compact, source-bound explanation of the frozen 199 -> 72 UAS scope."""

from __future__ import annotations

import csv
import html
import io
import json
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping


REPO = Path(__file__).resolve().parents[4]
OUT = REPO / "docs/research/preregistration/gate_s0/uas_eligibility_explainer_v1"
SOURCES = {
    "attrition": (
        "docs/research/preregistration/gate_s0/uas_reference_coverage_r1_v1/baseline_attrition_v1.csv",
        "63344a227c72eefcd8c550e08e123d1b7de050a3",
    ),
    "candidate_ledger": (
        "docs/research/preregistration/gate_s0/uas_reference_coverage_r1_v1/candidate_ledger_v1.csv",
        "6e5d6ab0698c0fdf3e67e74cbdd060bf785ea06b",
    ),
    "split": (
        "docs/research/preregistration/gate_s0/uas_reference_coverage_r1_v1/split_candidate_v1.csv",
        "f6db7b8accdbd7b57b4a221c441acfc5589fb592",
    ),
    "claim_scope": (
        "docs/research/preregistration/gate_s0/uas_reference_coverage_r1_v1/claim_scope_v1.json",
        "de7ca06632afe03b01b10c8e6894dab4b7773237",
    ),
    "coverage_config": (
        "configs/input_and_alignment/gate_s0/uas_reference_coverage_r1_v1/coverage_r1_v1.json",
        "64c7beaf5cd7780a4935b23fe96f7b2cd152db96",
    ),
}


def git_bytes(path: str, expected_blob: str) -> bytes:
    blob = subprocess.run(
        ["git", "-C", str(REPO), "rev-parse", f"HEAD:{path}"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if blob != expected_blob:
        raise RuntimeError(f"frozen source blob mismatch: {path}: {blob}")
    return subprocess.run(
        ["git", "-C", str(REPO), "show", f"HEAD:{path}"],
        check=True,
        capture_output=True,
    ).stdout


def csv_rows(data: bytes) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(data.decode("utf-8"), newline="")))


def truth(value: str) -> bool:
    return value.lower() == "true"


def reason_key(row: Mapping[str, str]) -> tuple[str, ...]:
    return tuple(value for value in row["candidate_exclusion_reason"].split(";") if value)


def support(row: Mapping[str, str], name: str) -> int:
    return int(row[name])


def choose_examples(rows: list[dict[str, str]]) -> list[tuple[str, str, dict[str, str]]]:
    eligible = sorted(
        (row for row in rows if truth(row["e_paired_candidate"])),
        key=lambda row: (support(row, "reference_candidate_score_cells"), row["stable_id"]),
    )
    examples: list[tuple[str, str, dict[str, str]]] = [
        ("P1", "통과·UAS 경계에 가장 가까움", eligible[0]),
        ("P2", "통과·UAS 지원량 중앙 사례", eligible[len(eligible) // 2]),
        ("P3", "통과·UAS 지원량 최대 사례", eligible[-1]),
    ]
    desired = [
        (("INSUFFICIENT_INDEPENDENT_UAS_REFERENCE_SUPPORT",), "F1", "불통과·UAS reference만 부족"),
        (("INSUFFICIENT_INDEPENDENT_UAS_REFERENCE_SUPPORT", "INSUFFICIENT_MVS_SUPPORT"), "F2", "불통과·UAS와 MVS 부족"),
        (("INSUFFICIENT_INDEPENDENT_UAS_REFERENCE_SUPPORT", "INSUFFICIENT_C4_SUPPORT"), "F3", "불통과·UAS와 C4 ALS 부족"),
        (("INSUFFICIENT_INDEPENDENT_UAS_REFERENCE_SUPPORT", "INSUFFICIENT_MVS_SUPPORT", "INSUFFICIENT_C4_SUPPORT"), "F4", "불통과·UAS/MVS/C4 모두 부족"),
    ]
    for reasons, label, description in desired:
        candidates = [row for row in rows if reason_key(row) == reasons]
        if not candidates:
            raise RuntimeError(f"required exclusion example is absent: {reasons}")
        chosen = max(
            candidates,
            key=lambda row: (
                support(row, "reference_candidate_score_cells"),
                support(row, "mvs_support_cells") + support(row, "c4_support_cells"),
                support(row, "current_image_view_support"),
                row["stable_id"],
            ),
        )
        examples.append((label, description, chosen))
    if len({row["stable_id"] for _, _, row in examples}) != len(examples):
        raise RuntimeError("example selection unexpectedly duplicated a building")
    return examples


def render_svg(
    rows: list[dict[str, str]],
    attrition: Mapping[str, int],
    examples: list[tuple[str, str, dict[str, str]]],
    aoi: list[float],
) -> str:
    width, height = 1440, 840
    x0, y0, x1, y1 = aoi
    map_x, map_y, map_w, map_h = 610.0, 98.0, 770.0, 660.0

    def project(x: float, y: float) -> tuple[float, float]:
        px = map_x + (x - x0) / (x1 - x0) * map_w
        py = map_y + map_h - (y - y0) / (y1 - y0) * map_h
        return px, py

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
        '<title id="title">UAS eligibility from 199 target buildings to 72 evaluation candidates</title>',
        '<desc id="desc">A branched quality funnel and an AOI map of eligible and excluded building bounding boxes.</desc>',
        '<rect width="100%" height="100%" fill="#fbfaf7"/>',
        '<style>text{font-family:Segoe UI,Arial,sans-serif;fill:#17202a}.title{font-size:26px;font-weight:700}.sub{font-size:15px;fill:#4b5563}.label{font-size:15px;font-weight:600}.count{font-size:22px;font-weight:700;fill:white}.small{font-size:12px;fill:#4b5563}</style>',
        '<text class="title" x="46" y="45">199동 전체 대상에서 72동 독립 UAS 평가 후보까지</text>',
        '<text class="sub" x="46" y="72">관측·품질 기반 분기이며, 건물 형태나 방법 성능을 보고 고른 것이 아님</text>',
        '<text class="label" x="46" y="112">관측·품질 흐름</text>',
    ]
    stages = [
        ("연구 대상 U_target", 199, "#334155"),
        ("UAS 1 m cell ≥4", attrition["raw_observed"], "#475569"),
        ("높이 ≥2.5 m", attrition["height"], "#64748b"),
        ("local plane RMSE ≤0.3 m", attrition["plane_rmse"], "#0284c7"),
        ("normal/roughness 통과", attrition["roughness"], "#0891b2"),
    ]
    top, full = 134, 500.0
    for index, (label, count, color) in enumerate(stages):
        bar_w = max(150.0, full * count / 199)
        x = 46 + (full - bar_w) / 2
        y = top + index * 76
        parts.extend([
            f'<rect x="{x:.1f}" y="{y}" width="{bar_w:.1f}" height="52" rx="8" fill="{color}"/>',
            f'<text class="count" x="{x + 16:.1f}" y="{y + 34}">{count}</text>',
            f'<text x="{x + 66:.1f}" y="{y + 32}" font-size="14" fill="white">{html.escape(label)}</text>',
        ])
    branch_y = top + len(stages) * 76 + 18
    parts.extend([
        f'<path d="M296 {top + 4 * 76 + 52} L296 {branch_y - 13} L170 {branch_y - 13} L170 {branch_y + 2}" fill="none" stroke="#64748b" stroke-width="2"/>',
        f'<path d="M296 {branch_y - 13} L420 {branch_y - 13} L420 {branch_y + 2}" fill="none" stroke="#64748b" stroke-width="2"/>',
        f'<rect x="68" y="{branch_y}" width="204" height="76" rx="10" fill="#0f766e"/>',
        f'<text class="count" x="86" y="{branch_y + 31}">{attrition["diagnostic_final"]}</text>',
        f'<text x="128" y="{branch_y + 29}" font-size="14" fill="white">평가 후보</text>',
        f'<text x="86" y="{branch_y + 55}" font-size="12" fill="white">smooth roof patch ≥20 cells</text>',
        f'<rect x="318" y="{branch_y}" width="204" height="76" rx="10" fill="#9a3412"/>',
        f'<text class="count" x="336" y="{branch_y + 31}">{attrition["baseline_final"]}</text>',
        f'<text x="378" y="{branch_y + 29}" font-size="14" fill="white">엄격 planar branch</text>',
        f'<text x="336" y="{branch_y + 55}" font-size="12" fill="white">component planar fraction ≥70%</text>',
        f'<text class="small" x="68" y="{branch_y + 103}">72는 평가용 후보, 10은 보수적 planar-component 진단값입니다.</text>',
        f'<rect x="{map_x}" y="{map_y}" width="{map_w}" height="{map_h}" fill="#f8fafc" stroke="#94a3b8"/>',
        f'<defs><clipPath id="aoi-clip"><rect x="{map_x}" y="{map_y}" width="{map_w}" height="{map_h}"/></clipPath></defs>',
        '<g clip-path="url(#aoi-clip)">',
    ])
    example_by_id = {row["stable_id"]: label for label, _, row in examples}
    for row in rows:
        bx0, by0 = project(float(row["bbox_min_x"]), float(row["bbox_min_y"]))
        bx1, by1 = project(float(row["bbox_max_x"]), float(row["bbox_max_y"]))
        rx, ry = min(bx0, bx1), min(by0, by1)
        rw, rh = max(2.0, abs(bx1 - bx0)), max(2.0, abs(by1 - by0))
        eligible = truth(row["e_paired_candidate"])
        color = "#0f766e" if eligible else "#cbd5e1"
        opacity = "0.72" if eligible else "0.48"
        parts.append(f'<rect x="{rx:.2f}" y="{ry:.2f}" width="{rw:.2f}" height="{rh:.2f}" fill="{color}" fill-opacity="{opacity}" stroke="{color}" stroke-width="0.6"/>')
        if row["stable_id"] in example_by_id:
            cx, cy = project(
                (float(row["bbox_min_x"]) + float(row["bbox_max_x"])) / 2,
                (float(row["bbox_min_y"]) + float(row["bbox_max_y"])) / 2,
            )
            label = example_by_id[row["stable_id"]]
            parts.extend([
                f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="7" fill="none" stroke="#dc2626" stroke-width="2"/>',
                f'<text x="{cx + 8:.2f}" y="{cy - 8:.2f}" font-size="11" font-weight="700" fill="#991b1b">{label}</text>',
            ])
    parts.extend([
        '</g>',
        '<rect x="610" y="88" width="390" height="32" fill="#fbfaf7" fill-opacity="0.92"/>',
        '<text class="label" x="618" y="110">AOI 내 건물 bbox 분포 (실제 지붕 형상 아님)</text>',
        '<rect x="620" y="778" width="14" height="14" fill="#0f766e"/><text x="642" y="790" font-size="13">72 평가 후보</text>',
        '<rect x="760" y="778" width="14" height="14" fill="#cbd5e1"/><text x="782" y="790" font-size="13">127 제외</text>',
        '<circle cx="892" cy="785" r="7" fill="none" stroke="#dc2626" stroke-width="2"/><text x="906" y="790" font-size="13">표의 사례 P/F</text>',
        f'<text class="small" x="1110" y="790">EPSG:25832 · {x0:.2f},{y0:.2f}–{x1:.2f},{y1:.2f}</text>',
        '</svg>',
    ])
    return "\n".join(parts) + "\n"


def md_table(headers: Iterable[str], rows: Iterable[Iterable[Any]]) -> str:
    header = list(headers)
    output = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    output.extend("| " + " | ".join(str(value) for value in row) + " |" for row in rows)
    return "\n".join(output)


def main() -> None:
    source_data = {name: git_bytes(*spec) for name, spec in SOURCES.items()}
    attrition_rows = csv_rows(source_data["attrition"])
    attrition = {row["stage"]: int(row["buildings_with_minimum_score_cells"]) for row in attrition_rows}
    rows = csv_rows(source_data["candidate_ledger"])
    split_rows = csv_rows(source_data["split"])
    claim_scope = json.loads(source_data["claim_scope"])
    config = json.loads(source_data["coverage_config"])
    if len(rows) != 199 or sum(truth(row["e_paired_candidate"]) for row in rows) != 72:
        raise RuntimeError("frozen candidate count differs from exact 199/72")
    if len(split_rows) != 72 or {row["stable_id"] for row in split_rows} != {
        row["stable_id"] for row in rows if truth(row["e_paired_candidate"])
    }:
        raise RuntimeError("split roster differs from exact 72 candidate IDs")
    split_counts = Counter(row["split"] for row in split_rows)
    group_counts = Counter(row["group_id"] for row in split_rows)
    if dict(split_counts) != {"development": 51, "validation": 11, "held_out": 10}:
        raise RuntimeError(f"unexpected split counts: {dict(split_counts)}")
    excluded = [row for row in rows if not truth(row["e_paired_candidate"])]
    exclusion_counts = Counter(reason_key(row) for row in excluded)
    if len(excluded) != 127 or any("INSUFFICIENT_INDEPENDENT_UAS_REFERENCE_SUPPORT" not in key for key in exclusion_counts):
        raise RuntimeError("exclusion evidence no longer has UAS reference as the common bottleneck")
    eligible = [row for row in rows if truth(row["e_paired_candidate"])]
    examples = choose_examples(rows)
    threshold = int(config["eligibility"]["minimum_condition_cells"])
    support_min = {
        "reference_candidate_score_cells": min(support(row, "reference_candidate_score_cells") for row in eligible),
        "current_image_view_support": min(support(row, "current_image_view_support") for row in eligible),
        "mvs_support_cells": min(support(row, "mvs_support_cells") for row in eligible),
        "c4_support_cells": min(support(row, "c4_support_cells") for row in eligible),
    }
    example_rows = []
    for label, description, row in examples:
        example_rows.append({
            "label": label,
            "description": description,
            "stable_id": row["stable_id"],
            "candidate": truth(row["e_paired_candidate"]),
            "reference_cells": support(row, "reference_candidate_score_cells"),
            "image_views": support(row, "current_image_view_support"),
            "mvs_cells": support(row, "mvs_support_cells"),
            "c4_cells": support(row, "c4_support_cells"),
            "bbox_width_m": round(float(row["bbox_max_x"]) - float(row["bbox_min_x"]), 3),
            "bbox_height_m": round(float(row["bbox_max_y"]) - float(row["bbox_min_y"]), 3),
            "exclusion_reason": row["candidate_exclusion_reason"] or "PASS_ALL_INPUT_SUPPORT_RULES",
        })
    manifest = {
        "schema": "jointbuildgs.gate_s0_uas_eligibility_explainer.v1",
        "status": "DESCRIPTIVE_REPRESENTATION_OF_FROZEN_R1_EVIDENCE",
        "decision_context": "DEC-P1-013",
        "counts": {
            "u_target": 199,
            "raw_uas_observed_buildings_min_4_cells": attrition["raw_observed"],
            "reference_candidate": 72,
            "excluded": 127,
            "strict_planar_branch": attrition["baseline_final"],
            "splits": dict(split_counts),
            "independent_groups": len(group_counts),
            "largest_group": max(group_counts.values()),
        },
        "thresholds": {
            "minimum_building_support_cells": threshold,
            "minimum_image_views": int(config["eligibility"]["minimum_image_views"]),
            "actual_minima_among_72": support_min,
        },
        "attrition": attrition,
        "exclusion_reason_combinations": {";".join(key): value for key, value in sorted(exclusion_counts.items())},
        "examples": example_rows,
        "claim_scope": {
            "status": claim_scope["status"],
            "all_72_effective_n_rho_0p05": claim_scope["metrics"]["all_e_paired"]["0.05"]["n_eff"],
            "held_out_effective_n_rho_0p05": claim_scope["metrics"]["held_out"]["0.05"]["n_eff"],
            "confirmatory_minimum_held_out_groups_pass": claim_scope["confirmatory_minimum_held_out_groups_pass"],
            "c5_lod1_scope": "LOD2_DERIVED_DIAGNOSTIC_ONLY_NOT_PRIMARY_C5_READY",
        },
        "sources": {name: {"path": path, "git_blob": blob} for name, (path, blob) in SOURCES.items()},
        "scientific_verdict": None,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "uas_eligibility_explainer_v1.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    with (OUT / "uas_eligibility_examples_v1.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(example_rows[0]))
        writer.writeheader()
        writer.writerows(example_rows)
    (OUT / "uas_eligibility_overview_v1.svg").write_text(
        render_svg(rows, attrition, examples, list(config["aoi"]["bbox"])), encoding="utf-8", newline="\n"
    )
    exclusion_table = []
    labels = {
        ("INSUFFICIENT_INDEPENDENT_UAS_REFERENCE_SUPPORT",): "UAS reference만 부족",
        ("INSUFFICIENT_INDEPENDENT_UAS_REFERENCE_SUPPORT", "INSUFFICIENT_MVS_SUPPORT"): "UAS reference + MVS 부족",
        ("INSUFFICIENT_INDEPENDENT_UAS_REFERENCE_SUPPORT", "INSUFFICIENT_C4_SUPPORT"): "UAS reference + C4 ALS 부족",
        ("INSUFFICIENT_INDEPENDENT_UAS_REFERENCE_SUPPORT", "INSUFFICIENT_MVS_SUPPORT", "INSUFFICIENT_C4_SUPPORT"): "UAS reference + MVS + C4 ALS 부족",
    }
    for reasons, count in sorted(exclusion_counts.items(), key=lambda item: (-item[1], item[0])):
        exclusion_table.append((labels.get(reasons, "; ".join(reasons)), count, f"{count / 199:.1%}"))
    examples_table = [
        (
            row["label"], row["stable_id"], row["reference_cells"], row["image_views"], row["mvs_cells"],
            row["c4_cells"], f"{row['bbox_width_m']}×{row['bbox_height_m']}", row["exclusion_reason"],
        )
        for row in example_rows
    ]
    report = f"""# Gate S0 UAS 평가대상 199→72 설명서 v1

## 한 문장 결론

**199동 모두에 UAS LiDAR가 충분히 관측된 것이 아니다.** 199동은 영상과 stable ID로
정한 전체 연구 대상이고, 그중 건물 bbox 안에 최소 4개의 1 m UAS 관측 cell이 있던
건물은 129동, 품질 필터를 통과한 독립 UAS 지붕 cell과 C1–C5 입력 지원을 함께 확보한
평가 후보는 72동이다. 이 선택은 방법 결과를 보기 전에 이루어졌다.

![199→72 관측·품질 흐름과 AOI 분포](uas_eligibility_overview_v1.svg)

## 숫자의 의미

{md_table(
    ("수", "의미", "현재 허용되는 해석"),
    (
        (199, "U_target: 선택 AOI의 영상+stable-ID 전체 대상", "coverage 분모"),
        (129, "각 건물 bbox 안에 raw UAS 1 m cell이 최소 4개", "UAS가 실제로 닿은 최소 관측 범위"),
        (94, "높이·분산·이웃·평면 RMSE·normal·roughness cell 품질을 통과", "아직 building evaluation roster는 아님"),
        (72, "20-cell 이상 smooth roof patch와 모든 condition support를 확보", "독립 UAS 평가가 가능한 pilot 후보"),
        (51, "72 중 development split", "DEC-P1-013의 C1/C2 실행 범위"),
        (11, "validation split", "C3 설계 동안 보호"),
        (10, "held-out split", "최종 확인 전까지 보호"),
    ),
)}

여기서 별도로 나타나는 `baseline_final=10`은 “평가 가능한 건물이 10동뿐”이라는 뜻이
아니다. 연결된 전체 component의 70% 이상이 planar cell이어야 한다는 매우 보수적인
reference-segmentation 진단 branch다. 현재 72 후보는 각 cell의 높이·local plane·normal·
roughness 검사를 유지하되, 그 70% component 비율 조건은 평가 roster 조건으로 쓰지 않은
`diagnostic_final` branch다. 따라서 72는 **pilot 평가 후보**이며 confirmatory 모집단으로
승격된 수가 아니다.

## 72동이 다른 점

각 후보 건물은 결과값과 무관하게 다음 입력 조건을 동시에 만족한다.

- 독립 UAS 지붕 reference cell: 계약상 최소 {threshold}개, 실제 72동의 최솟값은 {support_min['reference_candidate_score_cells']}개
- 현재 영상 관측: 계약상 최소 2 view, 실제 최솟값은 {support_min['current_image_view_support']} view
- 공통 MVS support: 계약상 최소 {threshold} cell, 실제 최솟값은 {support_min['mvs_support_cells']} cell
- C4 existing-ALS support: 계약상 최소 {threshold} cell, 실제 최솟값은 {support_min['c4_support_cells']} cell
- C5 LoD1 candidate 존재 및 입력 정합 준비. 단, 현재 것은 LoD2-derived
  `diagnostic-only`이며 이 조건만으로 primary C5 실행·평가가 READY가 되지는 않음

독립 UAS는 C2–C5의 reconstruction, registration, crop 또는 `R_derived` 생성에 들어가지
않고 **결과를 재는 자**로만 사용한다. C1은 같은 UAS 계열을 입력으로도 쓰므로
`SELF_REFERENCE_UPPER_BASELINE`으로 분리해 해석한다.

## 127동이 제외된 직접 이유

{md_table(("사유 조합", "건물", "U_target 비율"), exclusion_table)}

모든 제외 건물에 공통으로 독립 UAS reference 부족이 포함된다. 즉 현재 가장 큰 병목은
영상이나 LoD1이 아니라, 해당 building bbox 안에서 품질 필터를 통과한 UAS 지붕 cell이
{threshold}개 이상 남느냐이다. 일부는 MVS 또는 C4 ALS support도 함께 부족하다.

## 실제 통과·불통 사례

아래 bbox 크기는 건물의 대략적인 XY 범위를 보여 줄 뿐 실제 지붕 형상을 뜻하지 않는다.
현재 동결된 설명 자료에는 정사영상 crop이나 지붕 mesh가 없으므로, 형태가 쉬워 보여서
골랐다는 식의 사후 해석은 하지 않는다.

{md_table(
    ("표시", "building", "UAS cells", "image views", "MVS cells", "C4 cells", "bbox m", "판정/사유"),
    examples_table,
)}

전체 사례의 기계 판독 표는 `uas_eligibility_examples_v1.csv`, 전체 요약과 source binding은
`uas_eligibility_explainer_v1.json`에 있다.

## 이 72동으로 할 수 있는 것과 없는 것

- 가능: development 51동에서 C1/C2의 생성 성공, schema/semantic, 지붕 거리·높이·normal
  오차를 기술적으로 확인하고, 그 실패 유형을 바탕으로 C3 첫 학습전략 DRAFT를 설계한다.
- 불가: 72동을 72개의 완전히 독립적인 표본처럼 취급하거나, validation/held-out 결과로
  C3를 조정하거나, TUM2TWIN 전체에 대한 confirmatory 성능 결론을 내린다.
- 이유: 72동은 9개 공간/reference group이고 가장 큰 group에 47동이 몰려 있다. group 내
  상관을 0.05로 가정한 유효 표본수는 전체 {claim_scope['metrics']['all_e_paired']['0.05']['n_eff']:.2f},
  held-out {claim_scope['metrics']['held_out']['0.05']['n_eff']:.2f} 수준이며 held-out group은 2개뿐이다.

따라서 현재 순서는 `R4에서 C1/C2 102행 완성 → 독립 검토 → 관찰된 실패 유형으로 C3
전략 DRAFT`가 맞다. 더 넓은 일반화 주장은 별도의 독립 reference/group 확장이 필요하다.

## Source와 판정 상태

- 결정 근거: `DEC-P1-013`
- 입력: 기존 R1 promoted CSV/JSON과 동결 config의 exact Git blobs만 사용
- raw UAS, MVS, LoD1/LoD2, Images.zip, OPF.zip 재열기·재해시: 0
- 성능 결과 사용: 0
- scientific_verdict: `null`
"""
    (OUT / "UAS_199_TO_72_EXPLAINER_v1.md").write_text(report, encoding="utf-8", newline="\n")
    print(json.dumps({"status": "PASS", "output": OUT.as_posix(), "counts": manifest["counts"]}, sort_keys=True))


if __name__ == "__main__":
    main()
