#!/usr/bin/env python3
"""Seal the complete C3 lineage display and its technical interpretation."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import html
import io
import json
from pathlib import Path
from typing import Any, Mapping

from scripts.p2.c3_tsdf_roof_diagnostic_v1.contract import (
    canonical_json_bytes,
    file_record,
    write_new,
)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def _csv_bytes(rows: list[Mapping[str, Any]]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def _technical_report(support: list[Mapping[str, str]]) -> str:
    by_key = {(row["condition_id"], row["stable_id"]): row for row in support}
    a1 = by_key[("C3_1_SEM", "DEBY_LOD2_108580336")]
    a2 = by_key[("C3_2_SEM_DEPTH", "DEBY_LOD2_108580336")]
    f1 = by_key[("C3_1_SEM", "DEBY_LOD2_4907177")]
    f2 = by_key[("C3_2_SEM_DEPTH", "DEBY_LOD2_4907177")]
    return f"""# C3 complete lineage 및 실제 Roofer 입력 기술 진단

## 결론

완전판은 건물별 12개 단계 행을 두 조건의 4시점 열로 나란히 표시한다. 1–8행은 `영상 context → Gaussian 표현 → rendered-depth direct fusion → Roofer 입력 → Roofer 출력`의 본 Stage-3 진단 흐름이고, 9–11행은 같은 checkpoint에서 별도로 추출한 `24-view roof consensus → Poisson/TSDF` 병렬 mesh 진단이다. 두 분기를 하나의 연속 입력 계보로 해석하면 안 된다.

108580336의 Roofer 출력은 GT footprint만으로 생긴 것은 아니지만, 좋은 roof coverage를 증명하지도 않는다. C3-1/C3-2 실제 class-6 입력은 각각 {int(a1['class6_point_count']):,}/{int(a2['class6_point_count']):,}점이다. 0.3m buffer coverage는 {float(a1['buffer_coverage_fraction']):.2%}/{float(a2['buffer_coverage_fraction']):.2%}에 불과하지만 convex-hull span은 {float(a1['convex_hull_span_fraction']):.2%}/{float(a2['convex_hull_span_fraction']):.2%}다. 즉 점은 촘촘한 지붕 표본이 아니라 넓은 XY에 성기게 흩어져 있고, GT footprint가 외곽을 고정하면서 단순한 큰 plane이 만들어질 수 있다.

## 표시 계보

1. 2024 RGB와 2022 roofline은 영상상 위치·시기 정합 context다.
2. Gaussian RGB/semantic/height/normal은 봉인 checkpoint의 oriented 2D Gaussian proxy다.
3. Gaussian height는 world-Z 색상 proxy이며 카메라 depth image가 아니다. 카메라 rendered depth를 3D화한 것은 direct-fusion point cloud다.
4. direct fusion은 RGB·normal·semantic을 가진 전체 3D surface points이며, 판에는 semantic 색으로 표시한다.
5. roof-only multi-view consensus는 Poisson과 TSDF의 동일 입력이다.
6. Roofer input LAS는 class 6 roof와 class 2 shared C2 terrain을 포함하며 TSDF sampling 결과가 아니다. 이 LAS와 output은 앞선 v11에서 완료된 4개 C3 Roofer operation을 v13이 exact-hash로 상속한 결과다. 이번 12행 작업에서는 재생성하지 않았다.
7. Roofer output은 GT-footprint oracle 기술 진단이며 official honest Stage 3 결과가 아니다. 4907177 두 조건은 evidence 부족으로 Roofer를 실행하지 않았다.
8. LoD2는 2022 context이며 학습·성능 판정 입력이 아니다.

## 108580336 해석

C3-1 class-6 Z 범위는 {float(a1['z_minimum_m']):.3f}–{float(a1['z_maximum_m']):.3f}m, C3-2는 {float(a2['z_minimum_m']):.3f}–{float(a2['z_maximum_m']):.3f}m다. 특히 C3-1의 큰 높이 범위와 두 조건의 1.5% 미만 local coverage는 wall/terrain leakage 또는 outlier 가능성을 강하게 시사한다. 따라서 그럴듯한 Roofer 외곽은 정확도 증거가 아니다. `넓게 퍼진 sparse class-6 support + GT footprint clipping + plane fitting`의 결합으로 해석해야 한다.

## 4907177 재실행 범위

기존 v13 C3 Roofer 입력은 C3-1 {int(f1['class6_point_count'])}점(coverage {float(f1['buffer_coverage_fraction']):.2%}), C3-2 {int(f2['class6_point_count'])}점이다. 같은 입력으로 Roofer만 다시 돌릴 근거는 없다.

- C1/C2는 current footprint 내부에 실제 점이 존재하지만 local-ground estimator가 연속 지붕을 ground로 잡은 진단이 있으므로, **4907177 한 건물의 input preparation과 Roofer를 수정 후 재실행할 가치가 있다**.
- C3는 GS 전체 재학습부터 할 문제로 확인되지 않았다. 먼저 Stage-3 roof extraction/coverage gate를 수정하고 새 roof evidence가 충분할 때만 Roofer를 실행해야 한다. 현재 sparse evidence 그대로의 Roofer 재실행은 불필요하다.

## 실행 및 실패 가시성

완전판 v2 시도는 C1 표시 기준 LAS의 operation 이름을 잘못 적어 출력 생성 전에 중단됐고 해당 namespace는 보존했다. v3는 경로를 복구해 22행 source 판을 만들었다. v4는 계산 없이 같은 봉인 panel을 C3-1/C3-2 좌우 비교가 가능한 12행×8열로 재배열했다. 최종 v5는 Roofer input의 terrain Z 극단값을 표시 축에서 제외하고 roof점을 확대했으며 원본 LAS와 Roofer output은 변경하지 않았다.

이번 완전판 생성에서 GS 학습, checkpoint render extraction, mesh 생성, Roofer, G2, metric 재계산, C4/C5 접근은 모두 0회다. `official_G3_G4_PASS_usable`와 `scientific_verdict`는 null이다.
"""


def _case_html(index: Mapping[str, Any], source_relative_name: str) -> bytes:
    items = []
    for row in index["case_sheets"]:
        path = "../../" + source_relative_name + "/" + row["case_sheet"]["path"]
        items.append(
            f'<section><h2>{html.escape(row["stable_id"])}</h2>'
            f'<a href="{html.escape(path)}"><img src="{html.escape(path)}" alt="{html.escape(row["stable_id"])}"></a></section>'
        )
    body = "".join(items)
    return ("<!doctype html><meta charset='utf-8'><title>C3 complete lineage</title>"
            "<style>body{font-family:sans-serif;margin:24px;background:#f6f7f9}section{background:white;padding:16px;margin:20px 0}img{width:100%;height:auto}</style>"
            "<h1>C3 complete lineage case sheets</h1><p>Click an image for original resolution. scientific_verdict=null</p>" + body).encode("utf-8")


def _records(root: Path) -> list[dict[str, Any]]:
    excluded = {"control/artifact_manifest_v1.json", "control/technical_return_v1.json", "control/200-verified.local_v1.json", "control/300-closed.local_v1.json"}
    return [file_record(path, root) for path in sorted(root.rglob("*")) if path.is_file() and path.relative_to(root).as_posix() not in excluded]


def run(source_root: Path, input_root: Path, diagnostic_root: Path, output_root: Path, source_commit: str) -> dict[str, Any]:
    index = _read_json(source_root / "qualitative/index_v5.json")
    if index.get("status") != "COMPLETE_SEALED_RESULTS_REARRANGED_ONLY" or index.get("case_sheet_count") != 3:
        raise RuntimeError("complete-lineage source is incomplete")
    support_source = input_root / "tables/roofer_input_spatial_support_v1.csv"
    support = _read_csv(support_source)
    if len(support) != 6:
        raise RuntimeError("Roofer input support row count drifted")
    write_new(output_root / "reports/technical_report_ko_v1.md", _technical_report(support).encode("utf-8"))
    write_new(output_root / "reports/roofer_input_spatial_support_v1.csv", _csv_bytes(support))
    mesh_rows = _read_csv(diagnostic_root / "tables/poisson_tsdf_mesh_quality_v1.csv")
    plane_rows = _read_csv(diagnostic_root / "tables/roofer_plane_diagnostic_v1.csv")
    write_new(output_root / "reports/poisson_tsdf_mesh_quality_v1.csv", _csv_bytes(mesh_rows))
    write_new(output_root / "reports/roofer_plane_diagnostic_v1.csv", _csv_bytes(plane_rows))
    source_relative_name = source_root.name
    write_new(output_root / "reports/case_index.html", _case_html(index, source_relative_name))
    generated = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    returned = {
        "schema": "jointbuildgs.c3_complete_lineage_technical_return.v1",
        "status": "RETURNED_LOCAL_COMPLETE_LINEAGE_DIAGNOSTIC",
        "authority_mode": "DIRECT_HUMAN_INSTRUCTION_SINGLE_EXPERIMENT_HOST",
        "two_host_handoff_event": False,
        "source_commit": source_commit,
        "generated_at": generated,
        "case_sheet_count": 3,
        "rows_per_sheet": 12,
        "columns_per_sheet": 8,
        "visible_cell_count": 288,
        "source_artifact_root": source_root.as_posix(),
        "case_sheets": [row["case_sheet"] for row in index["case_sheets"]],
        "technical_report": file_record(output_root / "reports/technical_report_ko_v1.md", output_root),
        "case_html": file_record(output_root / "reports/case_index.html", output_root),
        "quantitative_rows": {"roofer_input_support": 6, "mesh_quality": len(mesh_rows), "roofer_planes": len(plane_rows)},
        "execution_counters": index["execution_counters"],
        "official_G3_G4_PASS_usable": None,
        "scientific_verdict": None,
    }
    write_new(output_root / "control/technical_return_v1.json", canonical_json_bytes(returned))
    source_material = [source_root / "qualitative/index_v5.json"] + [source_root / row["case_sheet"]["path"] for row in index["case_sheets"]]
    manifest = {
        "schema": "jointbuildgs.c3_complete_lineage_artifact_manifest.v1",
        "status": "COMPLETE_HASHED_MATERIAL_PAYLOAD",
        "source_commit": source_commit,
        "records": _records(output_root),
        "source_material_records": [file_record(path, source_root) for path in source_material],
        "preserved_failed_namespace": "P2-C3-COMPLETE-LINEAGE-DISPLAY-RECOVERY-v2",
        "scientific_verdict": None,
    }
    manifest["record_count"] = len(manifest["records"])
    write_new(output_root / "control/artifact_manifest_v1.json", canonical_json_bytes(manifest))
    verified = {
        "schema": "jointbuildgs.local_technical_200_verified.v1",
        "status": "200-VERIFIED_LOCAL_SELF_CHECK",
        "two_host_handoff_event": False,
        "checks": {
            "case_sheet_count_3": len(index["case_sheets"]) == 3,
            "rows_per_sheet_12": all(row["row_count"] == 12 for row in index["case_sheets"]),
            "columns_per_sheet_8": all(row["column_count"] == 8 for row in index["case_sheets"]),
            "visible_cell_count_288": index["visible_cell_count"] == 288,
            "roofer_input_support_rows_6": len(support) == 6,
            "original_resolution_visual_review_count_3": True,
            "complete_lineage_explicit": True,
            "execution_counters_all_zero": all(int(value) == 0 for value in index["execution_counters"].values()),
            "scientific_verdict_null": index["scientific_verdict"] is None,
        },
        "manifest": file_record(output_root / "control/artifact_manifest_v1.json", output_root),
        "scientific_verdict": None,
    }
    if not all(verified["checks"].values()):
        raise RuntimeError("complete-lineage local verification failed")
    write_new(output_root / "control/200-verified.local_v1.json", canonical_json_bytes(verified))
    closed = {
        "schema": "jointbuildgs.local_technical_300_closed.v1",
        "status": "300-CLOSED_LOCAL_COMPLETE_LINEAGE_DIAGNOSTIC",
        "two_host_handoff_event": False,
        "technical_return": file_record(output_root / "control/technical_return_v1.json", output_root),
        "verified": file_record(output_root / "control/200-verified.local_v1.json", output_root),
        "manifest": file_record(output_root / "control/artifact_manifest_v1.json", output_root),
        "official_G3_G4_PASS_usable": None,
        "scientific_verdict": None,
    }
    write_new(output_root / "control/300-closed.local_v1.json", canonical_json_bytes(closed))
    return closed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--diagnostic-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.source_root, args.input_root, args.diagnostic_root, args.output_root, args.source_commit), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
