#!/usr/bin/env python3
"""Independent QA for the E-PRIMARY4 public bundle."""
from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import laspy
import numpy as np

REPO = Path(__file__).resolve().parents[3]
CONFIG = REPO / "phases/p2-gsjso/configs/primary4_assembly_validation_v2.json"
RUN_DIR = REPO / "phases/p2-gsjso/runs/20260721_primary4_assembly_validation"
CSV_PATH = REPO / "docs/experiments/primary4_assembly_validation/tables/primary4_assembly_validation_measurements.csv"
SUMMARY = REPO / "docs/experiments/primary4_assembly_validation/reports/W_primary4_assembly_validation_summary_20260721.md"
MANIFEST = REPO / "docs/experiments/primary4_assembly_validation/manifests/primary4_assembly_validation_manifest.json"


def sha256_file(path: Path, block_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(block_size), b""):
            digest.update(block)
    return digest.hexdigest()


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def boolean(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1"}


def number(value: Any) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    result = float(value)
    if not math.isfinite(result):
        raise RuntimeError(f"non-finite number: {value}")
    return result


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> None:
    for path in (CONFIG, CSV_PATH, SUMMARY, MANIFEST):
        require(path.is_file(), f"missing required artifact: {path.relative_to(REPO)}")
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    measured = rows(CSV_PATH)
    expected_ids = [f"DEBY_LOD2_{short}" for short in config["targets_in_output_order"]]
    observed_ids = [row["building_id"] for row in measured]
    require(len(measured) == 4, f"measurement row count {len(measured)} != 4")
    require(observed_ids == expected_ids, f"measurement order/key drift: {observed_ids}")
    require(len(set(observed_ids)) == 4, "duplicate building rows")

    by_short = {row["building_id"].removeprefix("DEBY_LOD2_"): row for row in measured}
    formula = config["success_gauge"]["formula"]
    threshold = float(config["success_gauge"]["max_abs_signed_delta_z_median_m"])
    gauge_true = 0
    lod22_true = 0
    fallback_true = 0
    valid_true = 0
    for short, expected in config["anchor_lock"].items():
        row = by_short[short]
        require(row["anchor_inside_z_median_m"] == expected["anchor_inside_z_median_m"], f"z lock drift {short}")
        require(
            row["anchor_footprint_inside_point_count"]
            == expected["anchor_footprint_inside_point_count"],
            f"inside-count lock drift {short}",
        )
        require(row["anchor_inside_z_mad_m"] == expected["anchor_inside_z_mad_m"], f"MAD lock drift {short}")
        require(row["ref_roof_type"] == expected["ref_roof_type"], f"roof-type drift {short}")
        require(row["row_role"] == expected["row_role"], f"row-role drift {short}")
        require(number(row["grid_m"]) == 0.5, f"grid drift {short}")
        require(number(row["nominal_density_pt_m2"]) == 4.0, f"density drift {short}")
        require(row["crs"] == "EPSG:25832", f"CRS drift {short}")
        require(row["roofer_parameters"] == config["roofer"]["parameters"], f"Roofer parameter drift {short}")
        require(row["learning_runs_started"] == "0", f"learning drift {short}")
        require(row["new_inference_runs"] == "0", f"inference drift {short}")
        require(row["image_inputs_used"] == "0", f"image-input drift {short}")
        require(not boolean(row["gpu_used"]), f"GPU drift {short}")
        require(not boolean(row["reference_used_for_input_generation"]), f"reference input leak {short}")
        require(row["status"] == "measured", f"status drift {short}")
        has_lod22 = boolean(row["has_lod22"])
        assembly = boolean(row["assembly_success"])
        geometry = boolean(row["has_lod22_geometry"])
        signed = number(row["signed_delta_z_median_m"])
        expected_gauge = bool(has_lod22 and signed is not None and abs(signed) <= threshold)
        require(assembly == has_lod22, f"assembly/has_lod22 mismatch {short}")
        require(not has_lod22 or geometry, f"accepted LoD2 without lod=2.2 geometry {short}")
        require(row["success_gauge_formula"] == formula, f"gauge formula drift {short}")
        require(boolean(row["success_gauge_true"]) == expected_gauge, f"gauge boolean drift {short}")
        require(number(row["success_gauge_max_abs_error_m"]) == threshold, f"gauge threshold drift {short}")
        require(0.0 <= float(row["roof_completeness"]) <= 1.0, f"completeness range drift {short}")
        require(int(row["roof_face_count_ref"]) >= 1, f"reference face count missing {short}")
        require(int(row["flat_point_count"]) >= 1, f"flat point count missing {short}")
        point_path = REPO / row["flat_points_npz"]
        require(sha256_file(point_path) == row["flat_points_npz_sha256"], f"point NPZ hash drift {short}")
        with np.load(point_path, allow_pickle=False) as archive:
            xyz = np.ascontiguousarray(np.asarray(archive["xyz"], dtype=np.float32))
        require(len(xyz) == int(row["flat_point_count"]), f"point payload count drift {short}")
        require(
            hashlib.sha256(xyz.view(np.uint8)).hexdigest() == row["flat_xyz_payload_sha256"],
            f"point payload hash drift {short}",
        )
        gauge_true += int(expected_gauge)
        lod22_true += int(has_lod22)
        fallback_true += int(boolean(row["lod1_fallback"]))
        valid_true += int(boolean(row["val3dity_valid"]))

    prepared = json.loads((RUN_DIR / "prepared.json").read_text(encoding="utf-8"))
    for group, group_spec in prepared["groups"].items():
        laz_path = REPO / group_spec["classified_laz"]
        roofprint_path = REPO / group_spec["roofprint_geojson"]
        require(sha256_file(laz_path) == group_spec["classified_laz_sha256"], f"LAZ hash drift {group}")
        require(
            sha256_file(roofprint_path) == group_spec["roofprint_geojson_sha256"],
            f"roofprint hash drift {group}",
        )
        cloud = laspy.read(laz_path)
        crs = cloud.header.parse_crs()
        require(crs is not None and crs.to_epsg() == 25832, f"LAZ CRS drift {group}")
        classes = np.asarray(cloud.classification)
        require(set(np.unique(classes).tolist()) == {2, 6}, f"LAZ class drift {group}")
        expected_points = sum(
            int(prepared["flat_points"][short]["point_count"])
            for short in group_spec["targets"]
        )
        require(int(np.sum(classes == 6)) == expected_points, f"roof class count drift {group}")
        require(int(np.sum(classes == 2)) == expected_points, f"ground class count drift {group}")

    reproduction = json.loads((RUN_DIR / "reproduction_check.json").read_text(encoding="utf-8"))
    require(reproduction["passed"] is True, "199 reproduction hard stop did not pass")
    require(all(reproduction["checks"].values()), "199 reproduction subcheck false")
    row199 = by_short["4907199"]
    expected199 = config["reproduction_hard_stop"]
    tolerance = float(expected199["numeric_tolerance_m"])
    require(
        abs(float(row199["signed_delta_z_median_m"]) - float(expected199["expected_b1_assembly_signed_delta_z_median_m"]))
        <= tolerance,
        "199 signed median drift",
    )
    require(
        abs(float(row199["roof_rms_m"]) - float(expected199["expected_b1_roof_rms_m"]))
        <= tolerance,
        "199 RMS drift",
    )

    require(manifest["targets"] == config["targets_in_output_order"], "manifest target order drift")
    require(manifest["input_z_lock_all_match"] is True, "manifest z lock false")
    require(manifest["reproduction_check"]["passed"] is True, "manifest reproduction false")
    require(manifest["learning_runs_started"] == 0, "manifest learning drift")
    require(manifest["new_inference_runs"] == 0, "manifest inference drift")
    require(manifest["image_inputs_used"] == 0, "manifest image-input drift")
    require(manifest["gpu_used"] is False, "manifest GPU drift")
    require(manifest["interpretation_or_verdict"] is None, "manifest verdict field populated")
    result_counts = manifest["result_counts"]
    require(result_counts["rows"] == 4, "manifest row count drift")
    require(result_counts["has_lod22_true"] == lod22_true, "manifest LoD2 count drift")
    require(result_counts["lod1_fallback_true"] == fallback_true, "manifest fallback count drift")
    require(result_counts["val3dity_valid_true"] == valid_true, "manifest validity count drift")
    require(result_counts["success_gauge_true"] == gauge_true, "manifest gauge count drift")

    output_hash_mismatches = []
    for relative, expected_hash in manifest["output_sha256"].items():
        path = REPO / relative
        if not path.is_file() or sha256_file(path) != expected_hash:
            output_hash_mismatches.append(relative)
    source_hash_mismatches = []
    for relative, expected_hash in manifest["source_sha256"].items():
        path = REPO / relative
        if not path.is_file() or sha256_file(path) != expected_hash:
            source_hash_mismatches.append(relative)
    require(not output_hash_mismatches, f"output hash mismatches: {output_hash_mismatches}")
    require(not source_hash_mismatches, f"source hash mismatches: {source_hash_mismatches}")

    summary = SUMMARY.read_text(encoding="utf-8")
    require(all(short in summary for short in config["targets_in_output_order"]), "summary target omission")
    require("눈금 b" in summary and "1.0 m" in summary, "summary gauge omission")
    require("학습 0" in summary and "신규 추론 0" in summary and "GPU 0" in summary, "summary lock omission")

    print(
        json.dumps(
            {
                "assessment": "ready_to_share_measurement_bundle",
                "rows": len(measured),
                "unique_building_keys": len(set(observed_ids)),
                "target_order_match": True,
                "anchor_lock_match": True,
                "reproduction_passed": True,
                "has_lod22_true": lod22_true,
                "lod1_fallback_true": fallback_true,
                "val3dity_valid_true": valid_true,
                "success_gauge_true": gauge_true,
                "output_hash_mismatches": 0,
                "source_hash_mismatches": 0,
                "learning_runs_started": 0,
                "new_inference_runs": 0,
                "image_inputs_used": 0,
                "gpu_used": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
