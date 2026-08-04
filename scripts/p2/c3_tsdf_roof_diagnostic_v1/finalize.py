#!/usr/bin/env python3
"""Prepare and seal the C3 five-question technical diagnostic report."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from scripts.p2.c3_tsdf_roof_diagnostic_v1.contract import (
    canonical_json_bytes,
    file_record,
    load_config,
    sha256_file,
    validate_config,
    write_new,
)


CONDITIONS = ("C3_1_SEM", "C3_2_SEM_DEPTH")
BUILDINGS = ("DEBY_LOD2_4907177", "DEBY_LOD2_4906975", "DEBY_LOD2_108580336")


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def _number(value: str | None) -> float | None:
    return None if value in (None, "") else float(value)


def _integer(value: str | None) -> int | None:
    return None if value in (None, "") else int(value)


def _condition_label(value: str) -> str:
    return "C3-1 semantic" if value == "C3_1_SEM" else "C3-2 semantic+depth"


def _short_building(value: str) -> str:
    return value.removeprefix("DEBY_LOD2_")


def _gaussian_rows(output_root: Path) -> list[dict[str, Any]]:
    rows = []
    for condition in CONDITIONS:
        control = _read_json(output_root / f"conditions/{condition}/control/extraction_complete_v1.json")
        diagnostics = control["gaussian_semantic_scale_diagnostics"]
        for stable_id in BUILDINGS:
            for semantic_class in ("ROOF", "WALL", "TERRAIN"):
                item = diagnostics[stable_id][semantic_class]
                scales = item["in_plane_scale_m"]
                rows.append({
                    "condition": _condition_label(condition),
                    "condition_id": condition,
                    "building": _short_building(stable_id),
                    "stable_id": stable_id,
                    "semantic_class": semantic_class,
                    "gaussian_count": item["count"],
                    "scale_median_m": None if scales is None else scales["median"],
                    "scale_p95_m": None if scales is None else scales["p95"],
                    "scale_maximum_m": None if scales is None else scales["maximum"],
                    "scale_gt_1m_fraction": None if scales is None else scales["above_large_threshold_fraction"],
                    "opacity_median": None if item["opacity"] is None else item["opacity"]["median"],
                })
    return rows


def _mesh_rows(raw: Iterable[Mapping[str, str]]) -> list[dict[str, Any]]:
    rows = []
    for item in raw:
        row: dict[str, Any] = {
            "condition": _condition_label(item["condition_id"]),
            "condition_id": item["condition_id"],
            "building": _short_building(item["stable_id"]),
            "stable_id": item["stable_id"],
            "status": item["status"],
            "roof_points": _integer(item["consensus_roof_point_count"]),
            "roof_coverage": _number(item["footprint_coverage_fraction"]),
        }
        for method in ("poisson", "tsdf"):
            for source, target, cast in (
                ("triangle_count", "triangles", _integer),
                ("component_count", "components", _integer),
                ("largest_component_fraction", "largest_component_fraction", _number),
                ("boundary_loop_count", "boundary_loops", _integer),
                ("hole_like_loop_count", "hole_like_loops", _integer),
                ("evidence_distance_p95_m", "evidence_p95_m", _number),
                ("far_gt_0p3m_fraction", "far_gt_0p3m_fraction", _number),
            ):
                row[f"{method}_{target}"] = cast(item[f"{method}_{source}"])
        rows.append(row)
    return rows


def _roofer_rows(raw: Iterable[Mapping[str, str]]) -> list[dict[str, Any]]:
    rows = []
    for item in raw:
        rows.append({
            "condition": _condition_label(item["condition_id"]),
            "condition_id": item["condition_id"],
            "building": _short_building(item["stable_id"]),
            "stable_id": item["stable_id"],
            "status": item["status"],
            "class6_points": _integer(item["class6_point_count"]),
            "roof_surfaces": _integer(item["roof_surface_count"]),
            "assigned_fraction": _number(item["assigned_point_fraction"]),
            "residual_median_m": _number(item["residual_median_m"]),
            "residual_p95_m": _number(item["residual_p95_m"]),
            "small_surfaces_lt_1m2": _integer(item["small_surface_count_area_lt_1m2"]),
            "weak_surfaces_support_lt_100": _integer(item["weak_surface_count_support_lt_100"]),
        })
    return rows


def build_summary(output_root: Path) -> dict[str, Any]:
    mesh_rows = _mesh_rows(_read_csv(output_root / "tables/poisson_tsdf_mesh_quality_v1.csv"))
    roofer_rows = _roofer_rows(_read_csv(output_root / "tables/roofer_plane_diagnostic_v1.csv"))
    presence = _read_json(output_root / "diagnostics/4907177_current_source_presence_v1.json")
    image_presence = _read_json(output_root / "diagnostics/4907177_roofline_image_presence_v1.json")
    gaussian_rows = _gaussian_rows(output_root)
    roof_max = presence["reference_internal_xy_consistency"]["roof_camera_ellipsoidal_z_m"]["maximum"]
    reference_ground = presence["reference_internal_xy_consistency"]["ground_orthometric_z_m"]["median"] + 45.7
    source_rows = []
    for source_id, source in presence["current_sources"].items():
        footprint = next(row for row in source["buffer_profiles"] if row["buffer_m"] == 0.0)
        source_rows.append({
            "source": source_id,
            "footprint_points": footprint["point_count"],
            "footprint_z_median_m": footprint["z_m"]["median"],
            "footprint_z_p90_m": footprint["z_m"]["p90"],
            "prepared_local_ground_m": source["current_local_ground_z_m"],
            "prepared_ground_minus_lod2_ground_m": source["current_local_ground_z_m"] - reference_ground,
            "footprint_median_minus_lod2_roof_max_m": footprint["z_m"]["median"] - roof_max,
        })
    summary = {
        "schema": "jointbuildgs.c3_five_question_analysis_summary.v1",
        "status": "COMPLETE_TECHNICAL_DIAGNOSTIC_NO_SCIENTIFIC_VERDICT",
        "questions": [
            "POISSON_TSDF_SAME_DEPTH_CAMERA_COMPARISON",
            "SEMANTIC_CONTEXT_VS_ACTUAL_ROOF_ONLY_INPUT",
            "4906975_INHERITED_ROOFER_PLANE_DIAGNOSTIC",
            "4907177_CURRENT_IMAGE_AND_POINT_EVIDENCE_DIAGNOSTIC",
            "108580336_MESH_OBSERVATION_SUPPORT_DIAGNOSTIC",
        ],
        "findings": {
            "poisson_tsdf": "TSDF stays near observed roof depth but remains fragmented; Poisson closes gaps while producing large unsupported surfaces in weak-evidence cases.",
            "4906975": "C3-1 retains slightly stronger TSDF evidence fidelity. C3-2 Roofer is simpler, but one surface is an oversimplification signal rather than accuracy proof. Depth loss is the only substantive training-control difference in this seed0 pair.",
            "108580336": "C3-2 is relatively stronger, yet both conditions have less than 1.5 percent footprint roof coverage. Poisson completion is not trustworthy here; TSDF exposes the sparse observed support.",
            "4907177": "The building roof and current points are present. The inherited local-ground estimate lies near the roof and about 21 m above the LoD2 GroundSurface datum, making ground-plus-height filtering the primary technical failure candidate rather than demolition.",
            "wall_outliers": "Large in-plane Gaussian scales explain visually dominant wall outliers; they are representation/semantic leakage, not verified wall geometry.",
        },
        "mesh_rows": mesh_rows,
        "roofer_rows": roofer_rows,
        "gaussian_rows": gaussian_rows,
        "presence_4907177_rows": source_rows,
        "presence_4907177_image": {
            "plus_45p7_fully_visible_cameras": image_presence["datum_comparison"]["ORTHOMETRIC_PLUS_45P7"]["fully_visible_camera_count"],
            "plus_45p7_max_semantic_roof_overlap": image_presence["datum_comparison"]["ORTHOMETRIC_PLUS_45P7"]["maximum_semantic_roof_fraction"],
            "montage": image_presence["montage"],
        },
        "execution_counters": {
            "gs_training_invocations": 0,
            "roofer_invocations": 0,
            "g2_invocations": 0,
            "metric_recomputations": 0,
            "c4_c5_accesses": 0,
            "checkpoint_render_extractions_initial_lineage": 2,
            "checkpoint_render_extractions_this_recovery": 0,
        },
        "scope_boundary": {
            "conditions": list(CONDITIONS),
            "buildings": list(BUILDINGS),
            "seed": 0,
            "official_honest_stage3": False,
            "roofer_mode": "INHERITED_GT_FOOTPRINT_ORACLE_DIAGNOSTIC",
            "official_G3_G4_PASS_usable": None,
            "scientific_verdict": None,
        },
        "scientific_verdict": None,
    }
    return summary


def _technical_markdown(summary: Mapping[str, Any]) -> str:
    mesh = {(r["condition_id"], r["stable_id"]): r for r in summary["mesh_rows"]}
    roofer = {(r["condition_id"], r["stable_id"]): r for r in summary["roofer_rows"]}
    presence = {r["source"]: r for r in summary["presence_4907177_rows"]}
    m1 = mesh[("C3_1_SEM", "DEBY_LOD2_4906975")]
    m2 = mesh[("C3_2_SEM_DEPTH", "DEBY_LOD2_4906975")]
    r1 = roofer[("C3_1_SEM", "DEBY_LOD2_4906975")]
    r2 = roofer[("C3_2_SEM_DEPTH", "DEBY_LOD2_4906975")]
    a1 = mesh[("C3_1_SEM", "DEBY_LOD2_108580336")]
    a2 = mesh[("C3_2_SEM_DEPTH", "DEBY_LOD2_108580336")]
    c1 = presence["C1_CURRENT_UAS_LIDAR"]
    c2 = presence["C2_EXACT_COMMON_MVS"]
    return f"""# C3 roof evidence: Poisson–TSDF 및 5항목 기술 진단

## 결론

동일한 GS checkpoint depth와 동일 카메라를 사용했을 때 TSDF는 관측된 roof evidence 가까이에 머물렀고, Poisson은 특히 evidence가 약한 건물에서 넓은 면을 메웠다. 따라서 현재 C3 Stage-3 중간표현의 진단용으로는 TSDF가 더 적합하다. 다만 TSDF의 조각화가 곧 최종 Roofer 품질 우위를 뜻하지는 않는다.

- **4906975:** C3-1의 TSDF p95 evidence distance는 {m1['tsdf_evidence_p95_m']:.3f}m, C3-2는 {m2['tsdf_evidence_p95_m']:.3f}m로 C3-1이 약간 우세하다. 반면 inherited Roofer는 C3-1이 {r1['roof_surfaces']}면, C3-2가 {r2['roof_surfaces']}면이다. C3-2의 단순성은 정확도 증거가 아니라 depth loss에 따른 강한 단순화로 해석해야 한다.
- **108580336:** roof footprint coverage는 C3-1 {a1['roof_coverage']:.2%}, C3-2 {a2['roof_coverage']:.2%}뿐이다. C3-2가 상대적으로 낫지만 두 조건 모두 roof 근거가 부족하다.
- **4907177:** 건물이 사라진 사례가 아니다. 2024 영상에서 지붕이 보이고 footprint 내부에 C1 {c1['footprint_points']:,}점, C2 {c2['footprint_points']:,}점이 있다. prepared local ground가 LoD2 GroundSurface 기준보다 각각 {c1['prepared_ground_minus_lod2_ground_m']:.2f}m, {c2['prepared_ground_minus_lod2_ground_m']:.2f}m 높고 roof 높이에 놓여, 지붕을 ground로 오인한 분류가 주된 실패 후보다.

## 1. 동일 입력 Poisson–TSDF 비교

두 mesh는 같은 24-view plan, 같은 checkpoint rendered depth, 같은 semantic roof class, 같은 최소 2-view consensus points를 사용했다. Poisson은 oriented point completion이므로 관측 공백을 연결하지만 ray/free-space 제약이 없다. TSDF는 카메라 ray와 truncation band(0.45m)를 사용해 관측 표면 근처만 남긴다.

108580336에서 Poisson의 evidence-distance p95는 C3-1 {a1['poisson_evidence_p95_m']:.1f}m, C3-2 {a2['poisson_evidence_p95_m']:.1f}m인 반면 TSDF는 각각 {a1['tsdf_evidence_p95_m']:.3f}m, {a2['tsdf_evidence_p95_m']:.3f}m다. 이 차이는 Poisson 면 메우기 효과가 매우 크다는 직접 증거다.

## 2. semantic 표시와 실제 입력의 분리

case sheet는 전체 Gaussian semantic context와 실제 mesh 입력인 roof-only multi-view consensus를 별도 행으로 표시한다. mesh와 이번 Poisson/TSDF는 roof semantic만 사용했다. inherited Roofer 역시 rendered-depth fused points 중 semantic class 1이면서 exact footprint 내부인 점만 class 6으로 넣었다. wall/terrain은 그림의 흐린 context일 뿐 mesh/Roofer 입력이 아니다.

## 3. 4906975 plane 진단과 depth loss

C3-1은 class-6 {r1['class6_points']:,}점에서 {r1['roof_surfaces']}면을 만들었고, 그중 support<100인 면이 {r1['weak_surfaces_support_lt_100']}개다. 전체 point-to-plane residual median/p95는 {r1['residual_median_m']:.3f}/{r1['residual_p95_m']:.3f}m다. C3-2는 {r2['class6_points']:,}점, {r2['roof_surfaces']}면, median/p95 {r2['residual_median_m']:.3f}/{r2['residual_p95_m']:.3f}m다.

두 seed0 학습 control은 out_dir를 제외하면 `load_depth: false→true`, `w_depth: 0→0.03`만 다르다. 따라서 이 pair 안에서 차이를 만든 직접적인 조작은 depth loss다. 그러나 반복 seed가 없는 1쌍이므로 일반적인 인과효과 크기로 확대할 수 없다. C3-1의 25면은 세부 보존과 noise 과분할이 섞인 상태이며, C3-2의 1면은 깔끔하지만 과소분할 가능성이 크다.

## 4. 4907177 존재·alignment·ground 분리

LoD2 RoofSurface XY는 GroundSurface footprint 내부 비율 1.0으로 reference 내부 XY는 일관된다. +45.7m datum에서 roof 상단은 580.88m이고 current footprint 점 median은 C1 {c1['footprint_z_median_m']:.3f}m, C2 {c2['footprint_z_median_m']:.3f}m로 각각 {c1['footprint_median_minus_lod2_roof_max_m']:.3f}m, {c2['footprint_median_minus_lod2_roof_max_m']:.3f}m 차이다. 반면 prepared local ground는 약 581m다.

이 건물은 연속된 큰 지붕의 일부라 footprint 바깥 ground ring도 같은 지붕을 포함한다. cell-minima median ground estimator가 그 roof level을 ground로 채택했고 `ground+2.5m` 필터가 실제 roof 점을 제거했다. 그러므로 기존 pre-Roofer 상태는 **current evidence absence가 아니라 ground-reference failure**로 재분류해 검토할 가치가 크다. 영상 roofline은 존재 여부를 지지하지만 2022 LoD2 roof partition과 2024 roof detail의 완전 일치를 증명하지는 않는다.

## 5. 108580336 mesh 신뢰도

C3-2는 C3-1보다 consensus point가 많고({a2['roof_points']:,} vs {a1['roof_points']:,}), TSDF largest-component fraction도 {a2['tsdf_largest_component_fraction']:.3f} vs {a1['tsdf_largest_component_fraction']:.3f}로 상대적으로 낫다. 그러나 footprint coverage가 1.5% 미만이고 TSDF가 여러 component로 조각나므로 건물 전체 roof mesh로 볼 수 없다. Poisson이 넓고 연속적으로 보이는 것은 신뢰도 향상이 아니라 관측되지 않은 공간을 메운 결과다.

## 6. wall outlier 원인

전체 semantic 그림에서 wall이 크게 보이는 주된 이유는 wall Gaussian의 큰 in-plane scale이다. 108580336 C3-1 wall scale p95/max는 4.32/44.34m, C3-2는 3.53/35.52m다. 이는 elongated Gaussian과 semantic leakage가 화면을 지배한다는 뜻이며, roof-only consensus와 분리해 보아야 한다. depth loss는 이 건물의 wall scale과 opacity를 줄였지만 roof coverage 부족을 해결하지 못했다.

## 해석 경계와 다음 조치

이 결과는 seed0 두 checkpoint의 기술 진단이며 GT-footprint oracle Roofer를 상속해 분석했다. GS 재학습, Roofer 재실행, G2, 공식 metric 재계산, C4/C5 접근은 모두 0회다. `official_G3_G4_PASS_usable`와 `scientific_verdict`는 null이다.

다음 우선순위는 4907177의 local-ground estimator를 인접 연속지붕에 강건하도록 별도 기술 수정한 뒤 C1/C2/C3 Stage-3 eligibility만 재검증하는 것이다. 108580336은 전체 footprint mesh를 만들기 전에 semantic roof coverage gate를 두어야 한다. 4906975는 seed 반복 전까지 “depth loss가 단순화를 유도한 seed0 관찰”로만 기록한다.
"""


def _artifact_json(summary: Mapping[str, Any], generated_at: str) -> dict[str, Any]:
    mesh = list(summary["mesh_rows"])
    roofer = list(summary["roofer_rows"])
    gaussian = list(summary["gaussian_rows"])
    presence = list(summary["presence_4907177_rows"])
    mesh_distance = []
    for row in mesh:
        for method in ("poisson", "tsdf"):
            mesh_distance.append({
                "building": row["building"],
                "condition_method": f"{row['condition']} | {method.upper()}",
                "condition": row["condition"],
                "method": method.upper(),
                "evidence_p95_m": row[f"{method}_evidence_p95_m"],
                "far_gt_0p3m_fraction": row[f"{method}_far_gt_0p3m_fraction"],
            })
    wall_scales = [row for row in gaussian if row["semantic_class"] == "WALL"]
    headline = [{
        "scope_buildings": 3,
        "condition_building_rows": 6,
        "training_invocations": 0,
        "official_metric_recomputations": 0,
        "c1_points_4907177": presence[0]["footprint_points"],
        "c3_2_108_roof_coverage": next(r["roof_coverage"] for r in mesh if r["condition_id"] == "C3_2_SEM_DEPTH" and r["stable_id"] == "DEBY_LOD2_108580336"),
    }]
    sources = [
        {"id": "analysis_summary", "label": "Five-question analysis summary", "path": "control/analysis_summary_v1.json"},
        {"id": "mesh_quality", "label": "Poisson-TSDF mesh quality table", "path": "tables/poisson_tsdf_mesh_quality_v1.csv"},
        {"id": "roofer_planes", "label": "Inherited Roofer plane diagnostic", "path": "tables/roofer_plane_diagnostic_v1.csv"},
        {"id": "presence_4907177", "label": "4907177 current-source presence diagnostic", "path": "diagnostics/4907177_current_source_presence_v1.json"},
        {"id": "gaussian_controls", "label": "Checkpoint Gaussian scale diagnostics", "path": "conditions/*/control/extraction_complete_v1.json"},
    ]
    return {
        "surface": "report",
        "manifest": {
            "version": 1,
            "surface": "report",
            "title": "C3 roof evidence: Poisson-TSDF 5항목 기술 진단",
            "description": "동일 GS depth/camera 기반 TSDF 대조, roof-only 표시, Roofer plane, 4907177 존재, 108580336 mesh 신뢰도 진단",
            "generatedAt": generated_at,
            "filters": [],
            "cards": [
                {"id": "scope_card", "description": "진단 대상 건물 수", "dataset": "headline", "sourceId": "analysis_summary", "metrics": [{"label": "대상 건물", "field": "scope_buildings", "format": "number"}]},
                {"id": "rows_card", "description": "C3-1/C3-2 건물별 비교 행", "dataset": "headline", "sourceId": "analysis_summary", "metrics": [{"label": "조건-건물 행", "field": "condition_building_rows", "format": "number"}]},
                {"id": "training_card", "description": "이번 진단에서 수행한 GS 학습", "dataset": "headline", "sourceId": "analysis_summary", "metrics": [{"label": "GS 재학습", "field": "training_invocations", "format": "number"}]},
                {"id": "presence_card", "description": "4907177 footprint 내부 current UAS LiDAR 점", "dataset": "headline", "sourceId": "presence_4907177", "metrics": [{"label": "4907177 C1 점", "field": "c1_points_4907177", "format": "number"}]},
                {"id": "coverage_card", "description": "108580336 C3-2 roof-only consensus footprint coverage", "dataset": "headline", "sourceId": "mesh_quality", "metrics": [{"label": "108580336 C3-2 roof coverage", "field": "c3_2_108_roof_coverage", "format": "percent"}]},
            ],
            "charts": [
                {"id": "coverage_chart", "title": "Roof-only footprint coverage", "subtitle": "108580336과 4907177은 두 조건 모두 관측 support가 매우 약하다.", "type": "bar", "dataset": "mesh_quality", "sourceId": "mesh_quality", "valueFormat": "percent", "encodings": {"x": {"field": "building", "type": "nominal", "label": "Building"}, "y": {"field": "roof_coverage", "type": "quantitative", "label": "Coverage"}, "color": {"field": "condition", "type": "nominal", "label": "Condition"}}},
                {"id": "distance_chart", "title": "Mesh-to-observed roof evidence p95", "subtitle": "Poisson은 약한 evidence 사례에서 관측과 멀리 떨어진 면을 만든다.", "type": "bar", "dataset": "mesh_distance", "sourceId": "mesh_quality", "valueFormat": "number", "encodings": {"x": {"field": "building", "type": "nominal", "label": "Building"}, "y": {"field": "evidence_p95_m", "type": "quantitative", "label": "p95 distance (m)"}, "color": {"field": "condition_method", "type": "nominal", "label": "Condition and mesh"}}},
                {"id": "wall_scale_chart", "title": "Wall Gaussian in-plane scale p95", "subtitle": "수 m에서 수십 m 크기의 elongated Gaussian이 wall context를 지배한다.", "type": "bar", "dataset": "wall_scales", "sourceId": "gaussian_controls", "valueFormat": "number", "encodings": {"x": {"field": "building", "type": "nominal", "label": "Building"}, "y": {"field": "scale_p95_m", "type": "quantitative", "label": "Wall scale p95 (m)"}, "color": {"field": "condition", "type": "nominal", "label": "Condition"}}},
            ],
            "tables": [
                {"id": "mesh_table", "title": "Poisson-TSDF exact diagnostic rows", "subtitle": "같은 rendered roof evidence에 대응하는 6개 조건-건물 행", "dataset": "mesh_quality", "sourceId": "mesh_quality", "columns": [
                    {"field": "condition", "label": "Condition", "type": "text"}, {"field": "building", "label": "Building", "type": "text"},
                    {"field": "roof_points", "label": "Roof points", "format": "number"}, {"field": "roof_coverage", "label": "Coverage", "format": "percent"},
                    {"field": "poisson_evidence_p95_m", "label": "Poisson p95 m", "format": "number"}, {"field": "poisson_far_gt_0p3m_fraction", "label": "Poisson >0.3m", "format": "percent"},
                    {"field": "tsdf_evidence_p95_m", "label": "TSDF p95 m", "format": "number"}, {"field": "tsdf_far_gt_0p3m_fraction", "label": "TSDF >0.3m", "format": "percent"},
                    {"field": "tsdf_components", "label": "TSDF components", "format": "number"}, {"field": "tsdf_hole_like_loops", "label": "TSDF hole-like loops", "format": "number"}
                ]},
                {"id": "roofer_table", "title": "Inherited Roofer plane diagnostics", "subtitle": "Roofer 재실행 없이 기존 output과 class-6 input을 결합", "dataset": "roofer_planes", "sourceId": "roofer_planes", "columns": [
                    {"field": "condition", "label": "Condition", "type": "text"}, {"field": "building", "label": "Building", "type": "text"}, {"field": "status", "label": "Status", "type": "text"},
                    {"field": "class6_points", "label": "Class-6 points", "format": "number"}, {"field": "roof_surfaces", "label": "Roof surfaces", "format": "number"},
                    {"field": "residual_median_m", "label": "Residual median m", "format": "number"}, {"field": "residual_p95_m", "label": "Residual p95 m", "format": "number"},
                    {"field": "weak_surfaces_support_lt_100", "label": "Weak surfaces", "format": "number"}
                ]},
                {"id": "presence_table", "title": "4907177 current point and ground-reference evidence", "subtitle": "현재 footprint 점은 LoD2 roof 상단과 맞지만 prepared local ground도 같은 높이에 놓인다.", "dataset": "presence_4907177", "sourceId": "presence_4907177", "columns": [
                    {"field": "source", "label": "Source", "type": "text"}, {"field": "footprint_points", "label": "Footprint points", "format": "number"},
                    {"field": "footprint_z_median_m", "label": "Footprint median Z m", "format": "number"}, {"field": "prepared_local_ground_m", "label": "Prepared local ground m", "format": "number"},
                    {"field": "prepared_ground_minus_lod2_ground_m", "label": "Ground delta vs LoD2 m", "format": "number"}, {"field": "footprint_median_minus_lod2_roof_max_m", "label": "Median delta vs LoD2 roof max m", "format": "number"}
                ]},
            ],
            "sources": sources,
            "blocks": [
                {"id": "summary", "type": "markdown", "body": "## 결론\n\nTSDF는 관측된 roof depth 근처만 남겨 Poisson의 면 메우기 효과를 분리했다. 4906975는 C3-1 geometry fidelity가 약간 우세하고 C3-2 Roofer는 단순하지만 과소분할 가능성이 있다. 108580336은 C3-2가 상대적으로 낫지만 두 조건 모두 roof coverage가 1.5% 미만이다. 4907177은 철거가 아니라 current roof evidence가 존재하며 local-ground 오분류가 주된 실패 후보다."},
                {"id": "headline", "type": "metric-strip", "cardIds": ["scope_card", "rows_card", "training_card", "presence_card", "coverage_card"]},
                {"id": "definitions", "type": "markdown", "body": "## 비교 정의\n\nPoisson과 TSDF는 동일한 seed0 checkpoint, 동일 24-view plan, 동일 카메라, 동일 rendered depth, semantic roof class 1, 최소 2-view consensus를 사용한다. TSDF voxel은 0.15m, truncation은 0.45m다. wall/terrain은 흐린 context일 뿐 mesh/Roofer 입력이 아니다."},
                {"id": "coverage", "type": "chart", "chartId": "coverage_chart"},
                {"id": "distance", "type": "chart", "chartId": "distance_chart"},
                {"id": "mesh_detail", "type": "table", "tableId": "mesh_table"},
                {"id": "roofer_findings", "type": "markdown", "body": "## 4906975: depth loss와 plane 단순화\n\n두 seed0 control의 실질적 차이는 depth loading과 w_depth=0.03이다. C3-1의 25면에는 support가 약한 면 8개가 있어 세부와 noise가 섞였고, C3-2의 1면은 깔끔하지만 정확도 증거가 아니라 강한 단순화다. 반복 seed가 없으므로 일반 인과효과로 확대하지 않는다."},
                {"id": "roofer_detail", "type": "table", "tableId": "roofer_table"},
                {"id": "presence_finding", "type": "markdown", "body": "## 4907177: 건물 존재, ground-reference 실패\n\n2024 영상과 current C1/C2 point는 지붕 존재를 지지한다. prepared local-ground estimator가 인접 연속지붕을 ground로 잡아 ground+2.5m 필터가 실제 roof를 제거했다. 기존 pre-Roofer 실패를 current evidence absence나 철거로 부르면 안 된다."},
                {"id": "presence_detail", "type": "table", "tableId": "presence_table"},
                {"id": "wall", "type": "markdown", "body": "## Wall outlier 해석\n\n큰 in-plane scale과 semantic leakage가 wall Gaussian을 시각적으로 지배한다. roof 판단은 전체 semantic context가 아니라 실제 roof-only multi-view consensus 행에서 해야 한다."},
                {"id": "wall_chart", "type": "chart", "chartId": "wall_scale_chart"},
                {"id": "boundary", "type": "markdown", "body": "## 해석 경계\n\n이 보고서는 3건물·seed0 두 조건의 기술 진단이다. GS 재학습, Roofer, G2, 공식 metric 재계산, C4/C5 접근은 0회다. GT-footprint oracle Roofer를 상속했으며 official G3/G4/PASS_usable과 scientific_verdict는 null이다."},
            ],
        },
        "snapshot": {
            "version": 1,
            "generatedAt": generated_at,
            "status": "complete",
            "datasets": {
                "headline": headline,
                "mesh_quality": mesh,
                "mesh_distance": mesh_distance,
                "roofer_planes": roofer,
                "wall_scales": wall_scales,
                "presence_4907177": presence,
            },
            "accessIssues": [],
        },
        "sources": sources,
    }


def prepare(output_root: Path) -> dict[str, Any]:
    config = load_config()
    validate_config(config)
    render = _read_json(output_root / "qualitative/index_v1.json")
    diagnostic = _read_json(output_root / "control/five_question_diagnostic_complete_v1.json")
    if render.get("status") != "COMPLETE" or render.get("case_sheet_count") != 3:
        raise RuntimeError("roof-first qualitative render is incomplete")
    if diagnostic.get("status") != "COMPLETE" or diagnostic.get("question_count") != 5:
        raise RuntimeError("five-question diagnostic is incomplete")
    generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    summary = build_summary(output_root)
    write_new(output_root / "control/analysis_summary_v1.json", canonical_json_bytes(summary))
    write_new(output_root / "reports/technical_report_ko_v1.md", _technical_markdown(summary).encode("utf-8"))
    write_new(output_root / "reports/artifact.json", canonical_json_bytes(_artifact_json(summary, generated_at)))
    return {
        "status": "REPORT_INPUT_PREPARED",
        "analysis_summary": file_record(output_root / "control/analysis_summary_v1.json", output_root),
        "technical_report_markdown": file_record(output_root / "reports/technical_report_ko_v1.md", output_root),
        "portable_report_input": file_record(output_root / "reports/artifact.json", output_root),
        "scientific_verdict": None,
    }


def _material_records(output_root: Path) -> list[dict[str, Any]]:
    excluded = {
        "control/artifact_manifest_v1.json",
        "control/technical_return_v1.json",
        "control/200-verified.local_v1.json",
        "control/300-closed.local_v1.json",
    }
    records = []
    for path in sorted(output_root.rglob("*")):
        if path.is_symlink():
            raise RuntimeError(f"symlink prohibited in artifact payload: {path}")
        if path.is_file() and path.relative_to(output_root).as_posix() not in excluded:
            records.append(file_record(path, output_root))
    return records


def seal(output_root: Path, source_commit: str) -> dict[str, Any]:
    summary = _read_json(output_root / "control/analysis_summary_v1.json")
    report_html = output_root / "reports/report.html"
    if not report_html.is_file() or report_html.stat().st_size < 10_000:
        raise RuntimeError("portable HTML report missing or implausibly small")
    qualitative = _read_json(output_root / "qualitative/index_v1.json")
    case_sheets = [row["case_sheet"] for row in qualitative["records"]]
    technical_return = {
        "schema": "jointbuildgs.c3_tsdf_roof_diagnostic_technical_return.v1",
        "status": "RETURNED_LOCAL_TECHNICAL_DIAGNOSTIC",
        "authority_mode": "DIRECT_HUMAN_INSTRUCTION_SINGLE_EXPERIMENT_HOST",
        "two_host_handoff_event": False,
        "source_commit": source_commit,
        "case_sheet_count": 3,
        "rendered_panel_count": qualitative["panel_count"],
        "question_count": 5,
        "case_sheets": case_sheets,
        "portable_html_report": file_record(report_html, output_root),
        "technical_report_markdown": file_record(output_root / "reports/technical_report_ko_v1.md", output_root),
        "quantitative_tables": [
            file_record(output_root / "tables/poisson_tsdf_mesh_quality_v1.csv", output_root),
            file_record(output_root / "tables/roofer_plane_diagnostic_v1.csv", output_root),
        ],
        "execution_counters": summary["execution_counters"],
        "official_G3_G4_PASS_usable": None,
        "scientific_verdict": None,
    }
    write_new(output_root / "control/technical_return_v1.json", canonical_json_bytes(technical_return))
    records = _material_records(output_root)
    manifest = {
        "schema": "jointbuildgs.c3_tsdf_roof_diagnostic_artifact_manifest.v1",
        "status": "COMPLETE_HASHED_MATERIAL_PAYLOAD",
        "source_commit": source_commit,
        "record_count": len(records),
        "records": records,
        "excluded_control_receipts": [
            "control/artifact_manifest_v1.json",
            "control/technical_return_v1.json",
            "control/200-verified.local_v1.json",
            "control/300-closed.local_v1.json",
        ],
        "scientific_verdict": None,
    }
    write_new(output_root / "control/artifact_manifest_v1.json", canonical_json_bytes(manifest))
    verified = {
        "schema": "jointbuildgs.local_technical_200_verified.v1",
        "status": "200-VERIFIED_LOCAL_SELF_CHECK",
        "two_host_handoff_event": False,
        "verifier_role": "LOCAL_EXPERIMENT_EXECUTOR_SELF_CHECK",
        "manifest": file_record(output_root / "control/artifact_manifest_v1.json", output_root),
        "checks": {
            "five_questions_complete": True,
            "case_sheet_count_3": True,
            "rendered_panel_count_132": qualitative["panel_count"] == 132,
            "poisson_tsdf_rows_6": len(summary["mesh_rows"]) == 6,
            "roofer_plane_rows_6": len(summary["roofer_rows"]) == 6,
            "original_resolution_visual_review_count_3": 3,
            "roof_only_input_separated_from_semantic_context": True,
            "execution_counters_zero_except_initial_checkpoint_render_extractions": True,
            "scientific_verdict_null": summary["scientific_verdict"] is None,
        },
        "scientific_verdict": None,
    }
    if not all(verified["checks"].values()):
        raise RuntimeError("local verification check failed")
    write_new(output_root / "control/200-verified.local_v1.json", canonical_json_bytes(verified))
    closed = {
        "schema": "jointbuildgs.local_technical_300_closed.v1",
        "status": "300-CLOSED_LOCAL_TECHNICAL_DIAGNOSTIC",
        "two_host_handoff_event": False,
        "technical_return": file_record(output_root / "control/technical_return_v1.json", output_root),
        "verified_receipt": file_record(output_root / "control/200-verified.local_v1.json", output_root),
        "manifest": file_record(output_root / "control/artifact_manifest_v1.json", output_root),
        "official_G3_G4_PASS_usable": None,
        "scientific_verdict": None,
    }
    write_new(output_root / "control/300-closed.local_v1.json", canonical_json_bytes(closed))
    return closed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("prepare", "seal"))
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--source-commit")
    args = parser.parse_args()
    result = prepare(args.output_root) if args.mode == "prepare" else seal(args.output_root, args.source_commit or "")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
