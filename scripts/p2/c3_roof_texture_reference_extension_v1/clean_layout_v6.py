#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import html
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import cv2
import numpy as np

from scripts.p2.c1_c2_oracle_c3_extract_v1.contract import canonical_json_bytes, file_record, write_new
from scripts.p2.c3_roof_texture_bake_v1.bake import _records
from scripts.p2.c3_roof_texture_reference_extension_v1.recover_v5 import CONDITIONS, VIEWS, _compose_sheet
from scripts.p2.c3_tsdf_roof_diagnostic_v1.contract import resolve_artifact


REPO_ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = REPO_ROOT / "configs/p2/c3_roof_texture_reference_extension_v1/clean_layout_v6.json"


def load_config() -> dict[str, Any]:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def validate_config(config: Mapping[str, Any]) -> None:
    if config.get("schema") != "jointbuildgs.p2.c3_roof_texture_reference_extension_clean_layout.v1":
        raise RuntimeError("unexpected schema")
    if config.get("status") != "APPROVED_FOR_LOCAL_EXECUTION":
        raise RuntimeError("not activated")
    if tuple(config["views"]) != VIEWS or config["presentation"]["columns_per_sheet"] != 4:
        raise RuntimeError("layout contract drifted")
    if not config["presentation"]["short_titles_only"] or not config["presentation"]["separate_condition_sheets"]:
        raise RuntimeError("readability contract drifted")
    if any(int(value) != 0 for value in config["execution_counters"].values()):
        raise RuntimeError("presentation-only counters must all be zero")
    if config.get("scientific_verdict", "missing") is not None:
        raise RuntimeError("scientific_verdict must remain null")


def _short_view(view: str) -> str:
    return "SECTION" if view == "PRINCIPAL_SECTION" else view


def _retitle(source: Path, destination: Path, title: str, band_px: int) -> dict[str, Any]:
    image = cv2.imread(str(source), cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError(f"panel unreadable: {source}")
    image[:band_px, :] = 255
    (width, height), baseline = cv2.getTextSize(title, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
    x = max((image.shape[1] - width) // 2, 8)
    y = max((band_px + height - baseline) // 2, height + 2)
    cv2.putText(image, title, (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (25, 25, 25), 1, cv2.LINE_AA)
    ok, encoded = cv2.imencode(".png", image)
    if not ok:
        raise RuntimeError("panel encode failed")
    write_new(destination, encoded.tobytes())
    return {"source": file_record(source, source.parents[3]), "copy": file_record(destination, destination.parents[3]), "short_title": title}


def run(output_root: Path, artifact_root: Path, source_commit: str) -> dict[str, Any]:
    config = load_config()
    validate_config(config)
    source_root = resolve_artifact(artifact_root, config["source_relative_root"], "v5 source")
    if output_root.exists() and any(output_root.iterdir()):
        raise RuntimeError(f"add-once output is not empty: {output_root}")
    output_root.mkdir(parents=True, exist_ok=True)
    source_closed = json.loads((source_root / "control/300-closed.local_v1.json").read_text(encoding="utf-8"))
    if source_closed.get("status") != "300-CLOSED_LOCAL_C1_RECOVERY_AND_READABLE_TEXTURE_COMPARISON":
        raise RuntimeError("v5 source is not closed")
    source_index = json.loads((source_root / "qualitative/index_v1.json").read_text(encoding="utf-8"))
    coverage = {
        (case["stable_id"], sheet["condition_id"]): sheet
        for case in source_index["cases"] for sheet in case["sheets"]
    }
    lineage = []
    cases = []
    band_px = int(config["presentation"]["source_panel_title_band_replaced_px"])
    for stable_id in config["building_ids"]:
        source_panels = source_root / f"qualitative/{stable_id}/panels"
        output_panels = output_root / f"qualitative/{stable_id}/panels"
        common: dict[str, list[Path]] = {}
        for role, prefix, title in (
            ("RGB_ROOFLINE", "context", "RGB + roofline"),
            ("C1_ROOFER", "c1_roofer", "C1 Roofer"),
            ("LOD2_REFERENCE", "lod2_reference", "LoD2 2022"),
        ):
            common[role] = []
            for view in VIEWS:
                source = source_panels / f"{prefix}_{view.lower()}.png"
                destination = output_panels / source.name
                record = _retitle(source, destination, f"{title} | {_short_view(view)}", band_px)
                record.update({"stable_id": stable_id, "role": role, "view": view})
                lineage.append(record)
                common[role].append(destination)
        sheets = []
        for condition_id, condition_label in CONDITIONS:
            method_rows: dict[str, list[Path]] = {}
            for method, method_title in (("poisson", "Poisson"), ("tsdf", "TSDF")):
                for mode, mode_title in (("texture", "texture"), ("support", "support")):
                    key = f"{method.upper()}_{mode.upper()}"
                    method_rows[key] = []
                    for view in VIEWS:
                        source = source_panels / f"{method}_{mode}_{condition_id}_{view.lower()}.png"
                        destination = output_panels / source.name
                        record = _retitle(source, destination, f"{method_title} {mode_title} | {_short_view(view)}", band_px)
                        record.update({"stable_id": stable_id, "condition_id": condition_id, "role": key, "view": view})
                        lineage.append(record)
                        method_rows[key].append(destination)
            diagnostic = coverage[(stable_id, condition_id)]
            coverage_pct = 100.0 * float(diagnostic["footprint_roof_coverage_fraction"])
            c1_label = "C1 Roofer\nLoD2 ground-Z anchor" if stable_id == "DEBY_LOD2_4907177" else "C1 Roofer\ncurrent UAS LiDAR"
            tsdf_label = f"TSDF texture\nroof coverage {coverage_pct:.2f}%" if stable_id == "DEBY_LOD2_108580336" else "TSDF texture"
            primary_rows = [
                (c1_label, common["C1_ROOFER"]),
                ("LoD2 2022\nreference", common["LOD2_REFERENCE"]),
                ("Poisson texture", method_rows["POISSON_TEXTURE"]),
                (tsdf_label, method_rows["TSDF_TEXTURE"]),
            ]
            detail_rows = [
                ("RGB 2024 +\nLoD2 roofline", common["RGB_ROOFLINE"]),
                (c1_label, common["C1_ROOFER"]),
                ("LoD2 2022\nreference", common["LOD2_REFERENCE"]),
                ("Poisson texture", method_rows["POISSON_TEXTURE"]),
                ("Poisson support", method_rows["POISSON_SUPPORT"]),
                (tsdf_label, method_rows["TSDF_TEXTURE"]),
                (f"TSDF support\nroof coverage {coverage_pct:.2f}%", method_rows["TSDF_SUPPORT"]),
            ]
            slug = "c3_1" if condition_id == "C3_1_SEM" else "c3_2"
            primary = output_root / f"qualitative/{stable_id}/case_sheet_primary_compare_{slug}_v2.png"
            detail = output_root / f"qualitative/{stable_id}/case_sheet_detail_{slug}_v2.png"
            footer = "C1 Roofer vs textured roof meshes; short titles; scientific_verdict=null"
            _compose_sheet(primary, stable_id, condition_label, primary_rows, footer)
            _compose_sheet(detail, stable_id, condition_label, detail_rows, footer)
            sheets.append({
                "condition_id": condition_id,
                "roof_consensus_point_count": diagnostic["roof_consensus_point_count"],
                "footprint_roof_coverage_fraction": diagnostic["footprint_roof_coverage_fraction"],
                "primary_sheet": file_record(primary, output_root),
                "detail_sheet": file_record(detail, output_root),
            })
        cases.append({"stable_id": stable_id, "sheets": sheets})
    index = {
        "schema": "jointbuildgs.c3_roof_texture_reference_extension_v6_index.v1",
        "status": "COMPLETE_SHORT_TITLE_NO_OVERLAP_LAYOUT",
        "source_commit": source_commit,
        "source_v5_closure": file_record(source_root / "control/300-closed.local_v1.json", source_root),
        "case_count": 3,
        "primary_sheet_count": 6,
        "detail_sheet_count": 6,
        "layout": "SEPARATE_CONDITION_4_COLUMNS_SHORT_PANEL_TITLES",
        "lineage": lineage,
        "cases": cases,
        "execution_counters": config["execution_counters"],
        "scientific_verdict": None,
    }
    write_new(output_root / "qualitative/index_v1.json", canonical_json_bytes(index))
    report = """# C1 Roofer - C3 textured mesh clean layout v6

v5의 exact panel 내용을 상속하되 각 source panel의 긴 내부 제목 band만 짧은 역할/시점 제목으로 교체했다. 조건별 4열 판이므로 제목이 인접 셀과 겹치지 않는다. primary는 C1 Roofer / LoD2 / Poisson texture / TSDF texture, detail은 RGB+roofline과 support를 포함한다.

4907177 C1 Roofer 재실행 결과는 v5에서 정확히 1회 생성됐고 v6에서는 hash-identified raster만 상속했다. 해당 Roofer terminal은 성공이지만 형상은 낮은 면과 높고 좁은 면으로 분리되어 품질 성공을 뜻하지 않는다.

108580336 TSDF 공백은 roof-only evidence coverage가 C3-1 1.23%, C3-2 1.50%에 불과한 것을 충실하게 드러낸다. full-scene semantic TSDF는 수행하지 않았다.

v6 실행 계수는 Roofer/G2/GS/metric/Poisson/TSDF/C4/C5 모두 0이며 scientific_verdict는 null이다.
"""
    write_new(output_root / "reports/technical_report_ko_v1.md", report.encode("utf-8"))
    links = []
    for case in cases:
        links.append(f"<h2>{html.escape(case['stable_id'])}</h2>")
        for sheet in case["sheets"]:
            links.append(f"<h3>{html.escape(sheet['condition_id'])}</h3><img src=\"../{html.escape(sheet['primary_sheet']['path'])}\"><img src=\"../{html.escape(sheet['detail_sheet']['path'])}\">")
    write_new(output_root / "reports/case_index.html", ("<!doctype html><meta charset=utf-8><style>img{width:100%;margin-bottom:2rem}</style><h1>Clean C1 / textured mesh comparison</h1>" + "".join(links)).encode("utf-8"))
    returned = {
        "schema": "jointbuildgs.c3_roof_texture_reference_extension_v6_return.v1",
        "status": "RETURNED_LOCAL_COMPLETE_SHORT_TITLE_LAYOUT",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source_commit": source_commit,
        "case_count": 3,
        "primary_sheet_count": 6,
        "detail_sheet_count": 6,
        "execution_counters": config["execution_counters"],
        "scientific_verdict": None,
    }
    write_new(output_root / "control/technical_return_v1.json", canonical_json_bytes(returned))
    manifest = {
        "schema": "jointbuildgs.c3_roof_texture_reference_extension_v6_manifest.v1",
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
        "short_title_count_132": len(lineage) == 132,
        "all_v6_execution_counters_zero": all(int(value) == 0 for value in config["execution_counters"].values()),
        "scientific_verdict_null": index["scientific_verdict"] is None,
    }
    if not all(checks.values()):
        raise RuntimeError(f"v6 verification failed: {checks}")
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
        "status": "300-CLOSED_LOCAL_SHORT_TITLE_NO_OVERLAP_LAYOUT",
        "technical_return": file_record(output_root / "control/technical_return_v1.json", output_root),
        "verified": file_record(output_root / "control/200-verified.local_v1.json", output_root),
        "manifest": file_record(output_root / "control/artifact_manifest_v1.json", output_root),
        "scientific_verdict": None,
    }
    write_new(output_root / "control/300-closed.local_v1.json", canonical_json_bytes(closed))
    return closed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.output_root, args.artifact_root, args.source_commit), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
