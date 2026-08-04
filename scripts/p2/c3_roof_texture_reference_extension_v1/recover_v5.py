#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import html
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import cv2
import numpy as np

from scripts.p2.c1_c2_oracle_c3_extract_v1.contract import (
    canonical_json_bytes,
    contains_xy,
    deterministic_voxel_one,
    file_record,
    footprint_geojson,
    load_building_references,
    sha256_file,
    write_las,
    write_new,
)
from scripts.p2.c1_c2_oracle_c3_extract_v1.prepare_c1_c2 import collect_laz
from scripts.p2.c1_c2_oracle_c3_extract_v1.render_results import _bbox, _panel, _rings_xy
from scripts.p2.c3_roof_texture_bake_v1.bake import _records
from scripts.p2.c3_tsdf_roof_diagnostic_v1.contract import resolve_artifact
from src.visualization.fixed_view_qualitative import load_cityjsonseq


REPO_ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = REPO_ROOT / "configs/p2/c3_roof_texture_reference_extension_v1/recovery_v5.json"
VIEWS = ("TOP", "OBLIQUE_1", "OBLIQUE_2", "PRINCIPAL_SECTION")
CONDITIONS = (("C3_1_SEM", "C3-1 semantic"), ("C3_2_SEM_DEPTH", "C3-2 semantic + depth"))


def load_config() -> dict[str, Any]:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def validate_config(config: Mapping[str, Any]) -> None:
    if config.get("schema") != "jointbuildgs.p2.c3_roof_texture_reference_extension_recovery.v1":
        raise RuntimeError("unexpected config schema")
    if config.get("status") != "APPROVED_FOR_LOCAL_EXECUTION":
        raise RuntimeError("config is not activated")
    if tuple(config["scope"]["views"]) != VIEWS:
        raise RuntimeError("view contract drifted")
    if config["presentation"]["columns_per_sheet"] != 4 or not config["presentation"]["separate_condition_sheets"]:
        raise RuntimeError("readable layout contract drifted")
    counters = config["execution_counters"]
    if counters["roofer_invocations"] != 1 or any(
        int(value) != 0 for key, value in counters.items() if key != "roofer_invocations"
    ):
        raise RuntimeError("execution counter contract drifted")
    if config.get("scientific_verdict", "missing") is not None:
        raise RuntimeError("scientific_verdict must remain null")


def _exact(path: Path) -> dict[str, Any]:
    size, digest = sha256_file(path)
    return {"path": path.as_posix(), "bytes": size, "sha256": digest}


def prepare(output_root: Path, artifact_root: Path, source_commit: str) -> dict[str, Any]:
    config = load_config()
    validate_config(config)
    if output_root.exists() and any(output_root.iterdir()):
        raise RuntimeError(f"add-once partial is not empty: {output_root}")
    output_root.mkdir(parents=True, exist_ok=True)
    source = config["source"]
    laz = resolve_artifact(artifact_root, source["c1_current_uas_lidar_relative_path"], "C1 UAS LiDAR")
    lod2 = resolve_artifact(artifact_root, source["lod2_relative_path"], "LoD2")
    cfg = config["c1_4907177_recovery"]
    stable_id = cfg["stable_id"]
    reference = load_building_references(lod2, [stable_id])[stable_id]
    native_ground_values = np.concatenate([ring[:, 2] for ring in reference.ground_rings_xyz])
    native_ground_z = float(np.median(native_ground_values))
    current_ground_z = native_ground_z + float(cfg["lod2_groundsurface_to_current_z_shift_m"])
    points = collect_laz(laz, {stable_id: reference}, float(cfg["crop_buffer_m"]))[stable_id]
    inside = contains_xy(reference.footprint, points[:, 0], points[:, 1])
    outside_inner = ~contains_xy(reference.footprint.buffer(float(cfg["ground_ring_inner_buffer_m"])), points[:, 0], points[:, 1])
    building = points[inside & (points[:, 2] >= current_ground_z + float(cfg["minimum_building_height_above_ground_m"]))]
    ground = points[(~inside) & outside_inner & (points[:, 2] <= current_ground_z + float(cfg["ground_keep_above_ground_m"]))]
    building = deterministic_voxel_one(building, float(cfg["deterministic_voxel_m"]))
    ground = deterministic_voxel_one(ground, float(cfg["deterministic_voxel_m"]))
    if len(building) < int(cfg["minimum_class6_points"]):
        raise RuntimeError(f"class-6 support remains insufficient: {len(building)}")
    if not len(ground):
        raise RuntimeError("class-2 terrain support is empty")
    work = output_root / "operations/C1_LIDAR_LOD2_GROUND_Z_ORACLE/DEBY_LOD2_4907177/work"
    input_path = work / "input.las"
    footprint_path = work / "gt_footprint_oracle.geojson"
    write_las(input_path, building, ground)
    write_new(footprint_path, canonical_json_bytes(footprint_geojson(reference)))
    stats = {
        "source_crop_point_count": int(len(points)),
        "inside_footprint_raw_point_count": int(np.count_nonzero(inside)),
        "building_class6_count": int(len(building)),
        "ground_class2_count": int(len(ground)),
        "lod2_groundsurface_native_z_min_m": float(np.min(native_ground_values)),
        "lod2_groundsurface_native_z_median_m": native_ground_z,
        "lod2_groundsurface_native_z_max_m": float(np.max(native_ground_values)),
        "lod2_to_current_z_shift_m": float(cfg["lod2_groundsurface_to_current_z_shift_m"]),
        "current_ground_anchor_z_m": current_ground_z,
        "building_z_min_m": float(np.min(building[:, 2])),
        "building_z_median_m": float(np.median(building[:, 2])),
        "building_z_max_m": float(np.max(building[:, 2])),
        "ground_z_min_m": float(np.min(ground[:, 2])),
        "ground_z_median_m": float(np.median(ground[:, 2])),
        "ground_z_max_m": float(np.max(ground[:, 2])),
    }
    record = {
        "schema": "jointbuildgs.c1_4907177_lod2_ground_z_preparation.v1",
        "status": "PREPARED_FOR_ONE_ROOFER_INVOCATION",
        "source_commit": source_commit,
        "stable_id": stable_id,
        "input": file_record(input_path, output_root),
        "footprint": file_record(footprint_path, output_root),
        "sources": {"c1_current_uas_lidar": _exact(laz), "lod2": _exact(lod2)},
        "classification": stats,
        "oracle_boundary": cfg["oracle_boundary"],
        "roofsurface_xyz_used_as_roofer_input": False,
        "official_honest_stage3": False,
        "scientific_verdict": None,
    }
    write_new(work / "prepared_v1.json", canonical_json_bytes(record))
    write_new(output_root / "control/c1_4907177_prepared_v1.json", canonical_json_bytes(record))
    return record


def record_terminal(output_root: Path, exit_code: int, runtime_seconds: int) -> dict[str, Any]:
    work = output_root / "operations/C1_LIDAR_LOD2_GROUND_Z_ORACLE/DEBY_LOD2_4907177/work"
    prepared = json.loads((work / "prepared_v1.json").read_text(encoding="utf-8"))
    outputs = sorted((work / "out").glob("*.city.jsonl")) if (work / "out").is_dir() else []
    status = "COMPLETED" if exit_code == 0 and len(outputs) == 1 else "FAILED"
    body = {
        "schema": "jointbuildgs.c1_4907177_lod2_ground_z_roofer_terminal.v1",
        "status": status,
        "exit_code": int(exit_code),
        "runtime_seconds": int(runtime_seconds),
        "input": prepared["input"],
        "footprint": prepared["footprint"],
        "outputs": [file_record(path, output_root) for path in outputs],
        "roofer_invocations": 1,
        "oracle_diagnostic": True,
        "official_honest_stage3": False,
        "scientific_verdict": None,
    }
    runtime_path = work / "runtime.log"
    if runtime_path.is_file():
        body["runtime_log"] = file_record(runtime_path, output_root)
    internal_path = work / "roofer.log.json"
    if internal_path.is_file():
        body["roofer_internal_log"] = file_record(internal_path, output_root)
    write_new(work / "roofer_terminal_v1.json", canonical_json_bytes(body))
    if status != "COMPLETED":
        raise RuntimeError(f"Roofer failed: exit={exit_code} outputs={len(outputs)}")
    return body


def _copy(source: Path, destination: Path, source_root: Path, output_root: Path) -> dict[str, Any]:
    write_new(destination, source.read_bytes())
    source_record = file_record(source, source_root)
    copy_record = file_record(destination, output_root)
    if source_record["sha256"] != copy_record["sha256"]:
        raise RuntimeError(f"copy hash mismatch: {source}")
    return {"source": source_record, "copy": copy_record}


def _put_lines(canvas: np.ndarray, lines: Sequence[str], x: int, y: int, *, scale: float, color: tuple[int, int, int], thickness: int = 1, step: int = 34) -> None:
    for index, line in enumerate(lines):
        cv2.putText(canvas, line, (x, y + index * step), cv2.FONT_HERSHEY_SIMPLEX, scale, color, thickness, cv2.LINE_AA)


def _compose_sheet(path: Path, stable_id: str, condition_label: str, rows: Sequence[tuple[str, Sequence[Path]]], footer: str) -> None:
    cell_w, cell_h, label_w, header_h, footer_h = 960, 720, 390, 150, 72
    canvas = np.full((header_h + len(rows) * cell_h + footer_h, label_w + 4 * cell_w, 3), 255, np.uint8)
    _put_lines(canvas, [stable_id], 20, 42, scale=0.9, color=(20, 20, 20), thickness=2)
    _put_lines(canvas, [condition_label], label_w + 20, 42, scale=0.78, color=(70, 38, 28), thickness=2)
    for column, view in enumerate(VIEWS):
        cv2.putText(canvas, view.replace("PRINCIPAL_SECTION", "SECTION"), (label_w + column * cell_w + 20, 112), cv2.FONT_HERSHEY_SIMPLEX, 0.72, (20, 20, 20), 2, cv2.LINE_AA)
    for row_index, (label, panels) in enumerate(rows):
        if len(panels) != 4:
            raise RuntimeError("separate-condition sheet requires four panels per row")
        y0 = header_h + row_index * cell_h
        cv2.rectangle(canvas, (0, y0), (label_w - 1, y0 + cell_h - 1), (242, 244, 247), -1)
        _put_lines(canvas, label.split("\n"), 18, y0 + 60, scale=0.63, color=(25, 25, 25), thickness=2, step=40)
        for column, panel in enumerate(panels):
            image = cv2.imread(str(panel), cv2.IMREAD_COLOR)
            if image is None:
                raise RuntimeError(f"panel unreadable: {panel}")
            if image.shape[1] != cell_w or image.shape[0] != cell_h:
                image = cv2.resize(image, (cell_w, cell_h), interpolation=cv2.INTER_AREA)
            x0 = label_w + column * cell_w
            canvas[y0:y0 + cell_h, x0:x0 + cell_w] = image
    cv2.putText(canvas, footer, (20, canvas.shape[0] - 25), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (65, 65, 65), 1, cv2.LINE_AA)
    ok, encoded = cv2.imencode(".png", canvas)
    if not ok:
        raise RuntimeError("sheet PNG encode failed")
    write_new(path, encoded.tobytes())


def _coverage_rows(diagnostic_root: Path) -> dict[tuple[str, str], dict[str, str]]:
    output: dict[tuple[str, str], dict[str, str]] = {}
    with (diagnostic_root / "tables/poisson_tsdf_mesh_quality_v1.csv").open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            output[(row["condition_id"], row["stable_id"])] = row
    return output


def render_and_finalize(output_root: Path, artifact_root: Path, source_commit: str) -> dict[str, Any]:
    config = load_config()
    validate_config(config)
    v4_root = resolve_artifact(artifact_root, config["source"]["reference_extension_v4_relative_root"], "v4 extension")
    diagnostic_root = resolve_artifact(artifact_root, config["source"]["tsdf_diagnostic_relative_root"], "TSDF diagnostic")
    lod2 = resolve_artifact(artifact_root, config["source"]["lod2_relative_path"], "LoD2")
    terminal_path = output_root / "operations/C1_LIDAR_LOD2_GROUND_Z_ORACLE/DEBY_LOD2_4907177/work/roofer_terminal_v1.json"
    terminal = json.loads(terminal_path.read_text(encoding="utf-8"))
    if terminal.get("status") != "COMPLETED" or len(terminal.get("outputs") or ()) != 1:
        raise RuntimeError("4907177 recovered Roofer terminal is incomplete")
    output_cityjson = output_root / terminal["outputs"][0]["path"]
    surfaces = load_cityjsonseq(output_cityjson)
    references = load_building_references(lod2, config["scope"]["building_ids"])
    recovered_panel_paths: dict[str, Path] = {}
    reference = references["DEBY_LOD2_4907177"]
    for view in VIEWS:
        destination = output_root / f"qualitative/DEBY_LOD2_4907177/panels/c1_roofer_{view.lower()}.png"
        _panel(
            destination,
            view=view,
            bbox=_bbox(reference),
            points=None,
            surfaces=surfaces,
            footprint_rings=_rings_xy(reference),
            title=f"C1 Roofer | {view.replace('PRINCIPAL_SECTION', 'SECTION')}",
        )
        recovered_panel_paths[view] = destination
    coverage = _coverage_rows(diagnostic_root)
    lineage: list[dict[str, Any]] = []
    cases = []
    for stable_id in config["scope"]["building_ids"]:
        case_root = output_root / f"qualitative/{stable_id}"
        source_panel_root = v4_root / f"qualitative/{stable_id}/panels"
        common: dict[str, list[Path]] = {}
        for role, prefix in (("RGB_ROOFLINE", "context"), ("LOD2_REFERENCE", "lod2_reference")):
            paths = []
            for view in VIEWS:
                source_path = source_panel_root / f"{prefix}_{view.lower()}.png"
                destination = case_root / "panels" / source_path.name
                record = _copy(source_path, destination, v4_root, output_root)
                record.update({"stable_id": stable_id, "role": role, "view": view})
                lineage.append(record)
                paths.append(destination)
            common[role] = paths
        if stable_id == "DEBY_LOD2_4907177":
            common["C1_ROOFER"] = [recovered_panel_paths[view] for view in VIEWS]
        else:
            paths = []
            for view in VIEWS:
                source_path = source_panel_root / f"c1_roofer_{view.lower()}.png"
                destination = case_root / "panels" / source_path.name
                record = _copy(source_path, destination, v4_root, output_root)
                record.update({"stable_id": stable_id, "role": "C1_ROOFER", "view": view})
                lineage.append(record)
                paths.append(destination)
            common["C1_ROOFER"] = paths
        sheets = []
        for condition_id, condition_label in CONDITIONS:
            mesh_rows: dict[str, list[Path]] = {}
            for method in ("poisson", "tsdf"):
                for mode in ("texture", "support"):
                    key = f"{method.upper()}_{mode.upper()}"
                    paths = []
                    for view in VIEWS:
                        source_path = source_panel_root / f"{method}_{mode}_{condition_id}_{view.lower()}.png"
                        destination = case_root / "panels" / source_path.name
                        record = _copy(source_path, destination, v4_root, output_root)
                        record.update({"stable_id": stable_id, "condition_id": condition_id, "role": key, "view": view})
                        lineage.append(record)
                        paths.append(destination)
                    mesh_rows[key] = paths
            coverage_row = coverage[(condition_id, stable_id)]
            coverage_pct = 100.0 * float(coverage_row["footprint_coverage_fraction"])
            c1_label = "C1 Roofer\nLoD2 ground-Z anchor" if stable_id == "DEBY_LOD2_4907177" else "C1 Roofer\ncurrent UAS LiDAR"
            tsdf_label = f"TSDF texture\nroof coverage {coverage_pct:.2f}%" if stable_id == "DEBY_LOD2_108580336" else "TSDF texture"
            primary_rows = [
                (c1_label, common["C1_ROOFER"]),
                ("LoD2 2022\nreference", common["LOD2_REFERENCE"]),
                ("Poisson texture", mesh_rows["POISSON_TEXTURE"]),
                (tsdf_label, mesh_rows["TSDF_TEXTURE"]),
            ]
            detail_rows = [
                ("RGB 2024 +\nLoD2 roofline", common["RGB_ROOFLINE"]),
                (c1_label, common["C1_ROOFER"]),
                ("LoD2 2022\nreference", common["LOD2_REFERENCE"]),
                ("Poisson texture", mesh_rows["POISSON_TEXTURE"]),
                ("Poisson support", mesh_rows["POISSON_SUPPORT"]),
                (tsdf_label, mesh_rows["TSDF_TEXTURE"]),
                (f"TSDF support\nroof coverage {coverage_pct:.2f}%", mesh_rows["TSDF_SUPPORT"]),
            ]
            slug = "c3_1" if condition_id == "C3_1_SEM" else "c3_2"
            primary_path = case_root / f"case_sheet_primary_compare_{slug}_v1.png"
            detail_path = case_root / f"case_sheet_detail_{slug}_v1.png"
            footer = "C1 Roofer vs textured roof meshes; LoD2 is epoch reference; scientific_verdict=null"
            _compose_sheet(primary_path, stable_id, condition_label, primary_rows, footer)
            _compose_sheet(detail_path, stable_id, condition_label, detail_rows, footer)
            sheets.append({
                "condition_id": condition_id,
                "roof_consensus_point_count": int(coverage_row["consensus_roof_point_count"]),
                "footprint_roof_coverage_fraction": float(coverage_row["footprint_coverage_fraction"]),
                "tsdf_largest_component_fraction": float(coverage_row["tsdf_largest_component_fraction"]),
                "tsdf_evidence_distance_p95_m": float(coverage_row["tsdf_evidence_distance_p95_m"]),
                "primary_sheet": file_record(primary_path, output_root),
                "detail_sheet": file_record(detail_path, output_root),
            })
        cases.append({"stable_id": stable_id, "sheets": sheets})
    preparation = json.loads((output_root / "control/c1_4907177_prepared_v1.json").read_text(encoding="utf-8"))
    counters = dict(config["execution_counters"])
    index = {
        "schema": "jointbuildgs.c3_roof_texture_reference_extension_v5_index.v1",
        "status": "COMPLETE_READABLE_SEPARATE_CONDITION_COMPARISON",
        "source_commit": source_commit,
        "case_count": 3,
        "condition_sheet_count": 6,
        "primary_sheet_count": 6,
        "detail_sheet_count": 6,
        "layout": {"primary": "4_ROWS_X_4_VIEWS", "detail": "7_ROWS_X_4_VIEWS", "separate_conditions": True},
        "c1_4907177_recovery": preparation["classification"],
        "lineage": lineage,
        "cases": cases,
        "execution_counters": counters,
        "official_G3_G4_PASS_usable": None,
        "scientific_verdict": None,
    }
    write_new(output_root / "qualitative/index_v1.json", canonical_json_bytes(index))
    report = f"""# C1 Roofer - C3 textured mesh readable comparison v5

## 4907177 C1 recovery

- 기존 실패는 Roofer 실행 실패가 아니라 local-ground가 roof level로 잡혀 class 6가 0점이 된 전처리 실패였다.
- 이번 진단은 LoD2 GroundSurface native Z {preparation['classification']['lod2_groundsurface_native_z_median_m']:.2f} m에 기존 epoch-to-current shift +45.7 m를 적용해 current ground anchor {preparation['classification']['current_ground_anchor_z_m']:.2f} m를 사용했다.
- 그 결과 class 6 building {preparation['classification']['building_class6_count']}점, class 2 terrain {preparation['classification']['ground_class2_count']}점이 만들어졌고 Roofer를 정확히 1회 실행했다.
- LoD2 RoofSurface XYZ, roof type, final roof model은 Roofer 입력으로 사용하지 않았다. 따라서 이 결과는 GroundSurface Z oracle diagnostic이며 official honest Stage 3 결과가 아니다.

## 108580336 TSDF interpretation

- TSDF가 지붕을 임의로 지운 것이 아니다. roof-only multi-view consensus가 C3-1 833점 / C3-2 1,191점이고 footprint coverage가 각각 1.23% / 1.50%뿐이다.
- TSDF는 관측 근처만 유지하므로 이 희소성을 그대로 드러낸다. evidence distance p95는 C3-1 0.301 m / C3-2 0.304 m이다.
- 반대로 Poisson은 비관측 영역을 연결해 지붕처럼 보이게 만들 수 있으므로, 보기 좋은 면과 관측 근거를 분리해서 봐야 한다.
- full-scene semantic TSDF 재구성은 이번 실행에 포함하지 않았다. 현재 판은 동일한 기존 roof-only evidence의 Poisson/TSDF 비교다.

## Layout

- 조건별 4열(TOP / OBLIQUE 1 / OBLIQUE 2 / SECTION)로 분리해 8열 축소에서 생긴 글자 겹침을 제거했다.
- primary 판은 C1 Roofer, 2022 LoD2, Poisson texture, TSDF texture만 직접 비교한다.
- detail 판은 RGB+roofline과 Poisson/TSDF support를 추가한다.

scientific_verdict는 null이다.
"""
    write_new(output_root / "reports/technical_report_ko_v1.md", report.encode("utf-8"))
    links = []
    for case in cases:
        links.append(f"<h2>{html.escape(case['stable_id'])}</h2>")
        for sheet in case["sheets"]:
            links.append(f"<h3>{html.escape(sheet['condition_id'])}</h3><img src=\"../{html.escape(sheet['primary_sheet']['path'])}\"><img src=\"../{html.escape(sheet['detail_sheet']['path'])}\">")
    write_new(output_root / "reports/case_index.html", ("<!doctype html><meta charset=utf-8><style>img{width:100%;margin-bottom:2rem}</style><h1>C1 Roofer / textured mesh comparison</h1>" + "".join(links)).encode("utf-8"))
    returned = {
        "schema": "jointbuildgs.c3_roof_texture_reference_extension_v5_return.v1",
        "status": "RETURNED_LOCAL_COMPLETE_READABLE_COMPARISON",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source_commit": source_commit,
        "case_count": 3,
        "primary_sheet_count": 6,
        "detail_sheet_count": 6,
        "execution_counters": counters,
        "scientific_verdict": None,
    }
    write_new(output_root / "control/technical_return_v1.json", canonical_json_bytes(returned))
    manifest = {
        "schema": "jointbuildgs.c3_roof_texture_reference_extension_v5_manifest.v1",
        "status": "COMPLETE_HASHED_MATERIAL_PAYLOAD",
        "source_commit": source_commit,
        "records": _records(output_root),
        "scientific_verdict": None,
    }
    manifest["record_count"] = len(manifest["records"])
    write_new(output_root / "control/artifact_manifest_v1.json", canonical_json_bytes(manifest))
    checks = {
        "case_count_3": len(cases) == 3,
        "primary_sheet_count_6": sum(len(case["sheets"]) for case in cases) == 6,
        "detail_sheet_count_6": sum(len(case["sheets"]) for case in cases) == 6,
        "separate_condition_four_column_layout": all(len(case["sheets"]) == 2 for case in cases),
        "c1_4907177_roofer_completed": terminal["status"] == "COMPLETED",
        "c1_4907177_class6_positive": preparation["classification"]["building_class6_count"] > 0,
        "source_copy_hashes_match": all(row["source"]["sha256"] == row["copy"]["sha256"] for row in lineage),
        "only_one_roofer_invocation": counters["roofer_invocations"] == 1,
        "other_prohibited_counters_zero": all(int(value) == 0 for key, value in counters.items() if key != "roofer_invocations"),
        "scientific_verdict_null": index["scientific_verdict"] is None,
    }
    if not all(checks.values()):
        raise RuntimeError(f"v5 verification failed: {checks}")
    verified = {
        "schema": "jointbuildgs.local_technical_200_verified.v1",
        "status": "200-VERIFIED_LOCAL_SELF_CHECK",
        "checks": checks,
        "manifest": file_record(output_root / "control/artifact_manifest_v1.json", output_root),
        "scientific_verdict": None,
    }
    write_new(output_root / "control/200-verified.local_v1.json", canonical_json_bytes(verified))
    closed = {
        "schema": "jointbuildgs.local_technical_300_closed.v1",
        "status": "300-CLOSED_LOCAL_C1_RECOVERY_AND_READABLE_TEXTURE_COMPARISON",
        "technical_return": file_record(output_root / "control/technical_return_v1.json", output_root),
        "verified": file_record(output_root / "control/200-verified.local_v1.json", output_root),
        "manifest": file_record(output_root / "control/artifact_manifest_v1.json", output_root),
        "scientific_verdict": None,
    }
    write_new(output_root / "control/300-closed.local_v1.json", canonical_json_bytes(closed))
    return closed


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="mode", required=True)
    prepare_parser = sub.add_parser("prepare")
    prepare_parser.add_argument("--output-root", type=Path, required=True)
    prepare_parser.add_argument("--artifact-root", type=Path, required=True)
    prepare_parser.add_argument("--source-commit", required=True)
    terminal_parser = sub.add_parser("record-terminal")
    terminal_parser.add_argument("--output-root", type=Path, required=True)
    terminal_parser.add_argument("--exit-code", type=int, required=True)
    terminal_parser.add_argument("--runtime-seconds", type=int, required=True)
    render_parser = sub.add_parser("render-and-finalize")
    render_parser.add_argument("--output-root", type=Path, required=True)
    render_parser.add_argument("--artifact-root", type=Path, required=True)
    render_parser.add_argument("--source-commit", required=True)
    args = parser.parse_args()
    if args.mode == "prepare":
        result = prepare(args.output_root, args.artifact_root, args.source_commit)
    elif args.mode == "record-terminal":
        result = record_terminal(args.output_root, args.exit_code, args.runtime_seconds)
    else:
        result = render_and_finalize(args.output_root, args.artifact_root, args.source_commit)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
