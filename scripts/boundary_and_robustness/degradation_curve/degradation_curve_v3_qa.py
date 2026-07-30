#!/usr/bin/env python3
"""Independent QA for the degradation-curve CSV/manifest/figure bundle."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
from statistics import median
from typing import Any, Iterable, Mapping, Sequence

from PIL import Image


REPO = Path(__file__).resolve().parents[3]
DOCS = REPO / "docs"
SNAPSHOT = DOCS / "regression_input_snapshot.csv"
LADDER = DOCS / "boundary_map_v4_1_ladder.csv"
MEASUREMENTS = DOCS / "experiments/degradation_curve/tables/degradation_curve_measurements.csv"
SUMMARY = DOCS / "experiments/degradation_curve/tables/degradation_curve_summary.csv"
MANIFEST = DOCS / "experiments/degradation_curve/manifests/degradation_curve_manifest.json"
SUMMARY_MD = DOCS / "experiments/degradation_curve/reports/W_degradation_curve_summary_20260721.md"
NOISE_FIGURE = DOCS / "figs/degradation_curve/degradation_curve_noise.png"
DENSITY_FIGURE = DOCS / "figs/degradation_curve/degradation_curve_density.png"
RECOVERY_SCRIPT = REPO / "scripts/boundary_and_robustness/degradation_curve/degradation_curve_v3_recovery.py"
RECOVERY_INCIDENT = (
    REPO
    / "phases/p2-gsjso/runs/20260721_degradation_curve"
    / "degradation_curve_recovery_incident.json"
)
RECOVERY_ROOT = (
    REPO
    / "phases/p2-gsjso/runs/20260721_degradation_curve/runtime/recovery"
)
EXPECTED_POPULATION = 178
SEED_NAMESPACE = "jointbuildgs.degradation_curve.v3"

STAGES = [
    ("baseline", 0, "baseline", 0.0, 1.0, False),
    ("noise_sigma_0p05", 1, "noise", 0.05, 1.0, False),
    ("noise_sigma_0p10", 2, "noise", 0.10, 1.0, False),
    ("noise_sigma_0p20", 3, "noise", 0.20, 1.0, False),
    ("noise_sigma_0p40", 4, "noise", 0.40, 1.0, False),
    ("noise_sigma_0p80", 5, "noise", 0.80, 1.0, False),
    ("density_retain_1of2", 6, "density", 0.0, 0.5, False),
    ("density_retain_1of4", 7, "density", 0.0, 0.25, False),
    ("density_retain_1of10", 8, "density", 0.0, 0.10, False),
    ("density_retain_1of20", 9, "density", 0.0, 0.05, False),
    (
        "combo_sigma_0p20_retain_1of4",
        10,
        "combination",
        0.20,
        0.25,
        True,
    ),
    (
        "combo_sigma_0p40_retain_1of10",
        11,
        "combination",
        0.40,
        0.10,
        True,
    ),
]


def sha256_file(path: Path, block_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(block_size), b""):
            digest.update(block)
    return digest.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def as_bool(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes"}


def as_float(value: Any) -> float | None:
    text = str(value or "").strip()
    if not text or text.lower() in {"none", "nan"}:
        return None
    try:
        result = float(text)
    except ValueError:
        return None
    return result if math.isfinite(result) else None


def seed_for(building_id: str, stage_index: int) -> int:
    payload = f"{SEED_NAMESPACE}|{building_id}|{stage_index}"
    return int.from_bytes(
        hashlib.sha256(payload.encode("utf-8")).digest()[:8],
        "big",
        signed=False,
    )


def clean_values(
    rows: Iterable[Mapping[str, str]], field: str
) -> list[float]:
    return [
        value
        for value in (as_float(row.get(field)) for row in rows)
        if value is not None
    ]


def assert_close(
    observed: float | None,
    expected: float | None,
    field: str,
    tolerance: float = 5e-9,
) -> None:
    if observed is None or expected is None:
        if observed != expected:
            raise AssertionError(
                f"{field} none mismatch observed={observed} expected={expected}"
            )
        return
    if abs(observed - expected) > tolerance:
        raise AssertionError(
            f"{field} mismatch observed={observed} expected={expected}"
        )


def scope_stage_ids(scope: str) -> list[str]:
    return [row[0] for row in STAGES[:6]] if scope == "noise" else [
        row[0] for row in STAGES
    ]


def population() -> list[str]:
    rows = read_csv(SNAPSHOT)
    ids = sorted(
        row["building_id"]
        for row in rows
        if row["arm"] == "raw_lidar" and as_bool(row["assembled"])
    )
    if len(ids) != EXPECTED_POPULATION or len(set(ids)) != len(ids):
        raise AssertionError("canonical population drift")
    return ids


def validate(scope: str) -> dict[str, Any]:
    required = [
        MEASUREMENTS,
        SUMMARY,
        MANIFEST,
        SUMMARY_MD,
        NOISE_FIGURE,
    ]
    if scope == "full":
        required.append(DENSITY_FIGURE)
    missing = [str(path.relative_to(REPO)) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"outputs missing {missing}")

    canonical = population()
    canonical_set = set(canonical)
    ladder_rows = read_csv(LADDER)
    ladder = {row["building_id"]: row for row in ladder_rows}
    if len(ladder_rows) != EXPECTED_POPULATION or set(ladder) != canonical_set:
        raise AssertionError("ladder population drift")

    expected_stage_ids = scope_stage_ids(scope)
    measurements = read_csv(MEASUREMENTS)
    expected_rows = len(expected_stage_ids) * EXPECTED_POPULATION
    if len(measurements) != expected_rows:
        raise AssertionError(
            f"measurement rows {len(measurements)} != {expected_rows}"
        )
    keys = {(row["stage_id"], row["building_id"]) for row in measurements}
    if len(keys) != len(measurements):
        raise AssertionError("duplicate stage-building rows")
    if {row["stage_id"] for row in measurements} != set(expected_stage_ids):
        raise AssertionError("measurement stage set drift")
    for stage_id in expected_stage_ids:
        stage_rows = [
            row for row in measurements if row["stage_id"] == stage_id
        ]
        if (
            len(stage_rows) != EXPECTED_POPULATION
            or {row["building_id"] for row in stage_rows} != canonical_set
        ):
            raise AssertionError(f"stage population drift {stage_id}")

    stage_spec = {row[0]: row for row in STAGES}
    for row in measurements:
        stage_id, stage_index, axis, sigma, retention, is_combo = stage_spec[
            row["stage_id"]
        ]
        if int(row["stage_index"]) != stage_index:
            raise AssertionError("stage index drift")
        if row["stage_axis"] != axis:
            raise AssertionError("stage axis drift")
        assert_close(as_float(row["nominal_sigma_m"]), sigma, "sigma")
        assert_close(
            as_float(row["nominal_retention"]), retention, "retention"
        )
        if as_bool(row["is_combination"]) != is_combo:
            raise AssertionError("combination flag drift")
        if int(row["seed_uint64"]) != seed_for(
            row["building_id"], stage_index
        ):
            raise AssertionError(
                f"seed drift {row['stage_id']} {row['building_id']}"
            )
        if row["cell_label"] != ladder[row["building_id"]]["cell_label"]:
            raise AssertionError("cell join drift")
        if as_bool(row["small_lt50"]) != as_bool(
            ladder[row["building_id"]]["small_lt50"]
        ):
            raise AssertionError("size join drift")
        if row["ref_roof_slope_group"] != ladder[
            row["building_id"]
        ]["ref_roof_slope_group"]:
            raise AssertionError("roof-slope join drift")
        if row["crs"] != "EPSG:25832":
            raise AssertionError("CRS drift")
        if (
            row["learning_runs_started"] != "0"
            or row["new_inference_runs"] != "0"
        ):
            raise AssertionError("learning/inference flag drift")
        source_count = int(row["source_point_count"])
        retained = int(row["retained_member_point_count"])
        degraded = int(row["degraded_point_count"])
        if source_count <= 0 or retained < 0 or degraded < 0:
            raise AssertionError("point-count domain drift")
        if retained > source_count:
            raise AssertionError("retained count exceeds source")

    baseline = [
        row for row in measurements if row["stage_id"] == "baseline"
    ]
    all_rms = clean_values(baseline, "roof_rms_m")
    pilot = [row for row in baseline if as_bool(row["pilot10"])]
    if len(all_rms) != 178:
        raise AssertionError("zero-stage RMS support drift")
    if sum(as_bool(row["assembly_success"]) for row in baseline) != 178:
        raise AssertionError("zero-stage assembly hard stop")
    if round(median(all_rms), 3) != 0.421:
        raise AssertionError("zero-stage RMS hard stop")
    if len(pilot) != 10:
        raise AssertionError("pilot10 cardinality drift")
    pilot_checks = [
        sum(as_bool(row["assembly_success"]) for row in pilot) == 10,
        sum(as_bool(row["val3dity_valid"]) for row in pilot) == 9,
        round(median(clean_values(pilot, "roof_rms_m")), 3) == 0.337,
        abs(median(clean_values(pilot, "face_count_ratio")) - 1.875)
        <= 1e-12,
        round(median(clean_values(pilot, "roof_completeness")), 4)
        == 0.9999,
    ]
    if not all(pilot_checks):
        raise AssertionError("pilot10 zero-stage hard stop")

    summary = read_csv(SUMMARY)
    aggregates = [row for row in summary if row["row_type"] == "stage_aggregate"]
    expected_aggregate_rows = len(expected_stage_ids) * 10
    if len(aggregates) != expected_aggregate_rows:
        raise AssertionError(
            f"aggregate rows {len(aggregates)} != {expected_aggregate_rows}"
        )
    aggregate_keys = {
        (row["stage_id"], row["stratum_type"], row["stratum_value"])
        for row in aggregates
    }
    if len(aggregate_keys) != len(aggregates):
        raise AssertionError("aggregate key duplicate")
    for stage_id in expected_stage_ids:
        stage_rows = [
            row for row in measurements if row["stage_id"] == stage_id
        ]
        overall = next(
            row
            for row in aggregates
            if row["stage_id"] == stage_id
            and row["stratum_type"] == "overall"
            and row["stratum_value"] == "all"
        )
        if int(overall["population_count"]) != 178:
            raise AssertionError("overall population denominator drift")
        if int(overall["measurement_count"]) != 178:
            raise AssertionError("overall measurement denominator drift")
        if int(overall["assembly_count"]) != sum(
            as_bool(row["assembly_success"]) for row in stage_rows
        ):
            raise AssertionError(f"assembly aggregate drift {stage_id}")
        if int(overall["lod1_fallback_count"]) != sum(
            as_bool(row["lod1_fallback"]) for row in stage_rows
        ):
            raise AssertionError(f"fallback aggregate drift {stage_id}")
        if int(overall["val3dity_valid_count"]) != sum(
            as_bool(row["val3dity_valid"]) for row in stage_rows
        ):
            raise AssertionError(f"validity aggregate drift {stage_id}")
        for source_field, summary_field in (
            ("face_count_ratio", "face_count_ratio_median"),
            ("roof_rms_m", "roof_rms_median_m"),
            ("roof_hausdorff_m", "roof_hausdorff_median_m"),
            ("roof_completeness", "roof_completeness_median"),
            (
                "degraded_point_density_m2",
                "degraded_point_density_m2_median",
            ),
        ):
            values = clean_values(stage_rows, source_field)
            expected = None if not values else median(values)
            assert_close(
                as_float(overall[summary_field]),
                expected,
                f"{stage_id}.{summary_field}",
            )

    group_expected = {
        ("ladder_cell", "cell_1_assembled"): 114,
        ("ladder_cell", "cell_2_anchored"): 23,
        ("ladder_cell", "cell_3_outline_only"): 41,
        ("ladder_cell", "cell_4_beyond_image"): 0,
        ("size", "small_lt50"): 37,
        ("size", "non_small_ge50"): 141,
        ("fixed_subset", "pilot10"): 10,
    }
    baseline_aggregates = [
        row for row in aggregates if row["stage_id"] == "baseline"
    ]
    for key, count in group_expected.items():
        row = next(
            candidate
            for candidate in baseline_aggregates
            if (
                candidate["stratum_type"],
                candidate["stratum_value"],
            )
            == key
        )
        if int(row["population_count"]) != count:
            raise AssertionError(f"group count drift {key}")
    roof_group_total = sum(
        int(row["population_count"])
        for row in baseline_aggregates
        if row["stratum_type"] == "ref_roof_slope_group"
    )
    if roof_group_total != 178:
        raise AssertionError("roof-slope groups do not sum to 178")

    zero_rows = [
        row for row in summary if row["row_type"] == "zero_stage_reproduction"
    ]
    if len(zero_rows) != 8 or any(
        not as_bool(row["comparison_match"]) for row in zero_rows
    ):
        raise AssertionError("zero-stage validation rows drift")
    monotonic_rows = [
        row for row in summary if row["row_type"] == "monotonicity_detection"
    ]
    expected_monotonic_rows = 7 if scope == "noise" else 14
    if len(monotonic_rows) != expected_monotonic_rows:
        raise AssertionError("monotonicity row count drift")

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    expected_status = "partial_noise_axis" if scope == "noise" else "complete"
    if manifest["completion_status"] != expected_status:
        raise AssertionError("manifest completion status drift")
    if manifest["completed_stage_ids"] != expected_stage_ids:
        raise AssertionError("manifest completed stage order drift")
    if manifest["measurement_rows"] != expected_rows:
        raise AssertionError("manifest measurement row drift")
    if manifest["population_count"] != 178:
        raise AssertionError("manifest population drift")
    if manifest["learning_runs_started"] != 0:
        raise AssertionError("manifest learning flag drift")
    if manifest["new_inference_runs"] != 0:
        raise AssertionError("manifest inference flag drift")
    if manifest["image_inputs_used"] != 0:
        raise AssertionError("manifest image-input flag drift")
    if manifest["interpretation_or_verdict"] is not None:
        raise AssertionError("manifest verdict field must be null")
    if manifest["zero_stage_validation"]["all_metric_mismatch_count"] != 0:
        raise AssertionError("manifest zero-stage metric mismatch")
    pipeline_hashes = manifest["pipeline_sha256"]
    recovery_script_key = str(RECOVERY_SCRIPT.relative_to(REPO))
    legacy_recovery_script_key = (
        "phases/p2-gsjso/scripts/degradation_curve_v3_recovery.py"
    )
    recorded_recovery_hash = pipeline_hashes.get(
        recovery_script_key,
        pipeline_hashes.get(legacy_recovery_script_key),
    )
    if recorded_recovery_hash != sha256_file(RECOVERY_SCRIPT):
        raise AssertionError("recovery script pipeline hash drift")

    recovery_qa: dict[str, Any] | None = None
    if "noise_sigma_0p80" in expected_stage_ids:
        roofer_meta = manifest["stage_artifacts"]["noise_sigma_0p80"][
            "roofer"
        ]
        if roofer_meta.get("execution_mode") != (
            "isolated_per_building_same_parameters"
        ):
            raise AssertionError("sigma0.80 recovery execution mode drift")
        recovery_manifest_path = REPO / str(
            roofer_meta.get("recovery_manifest", "")
        )
        if not recovery_manifest_path.is_file():
            raise AssertionError("sigma0.80 recovery manifest missing")
        if sha256_file(recovery_manifest_path) != roofer_meta.get(
            "recovery_manifest_sha256"
        ):
            raise AssertionError("sigma0.80 recovery manifest hash drift")
        recovery = json.loads(
            recovery_manifest_path.read_text(encoding="utf-8")
        )
        if (
            recovery.get("status") != "complete"
            or recovery.get("population_count") != 178
            or recovery.get("successful_parts") != 178
            or recovery.get("reconstruction_parameter_change_count") != 0
            or recovery.get("learning_runs_started") != 0
            or recovery.get("new_inference_runs") != 0
        ):
            raise AssertionError("sigma0.80 recovery manifest contract drift")
        isolated_csv = REPO / recovery["isolated_measurements_csv"]
        isolated_rows = read_csv(isolated_csv)
        if (
            len(isolated_rows) != 178
            or {row["building_id"] for row in isolated_rows} != canonical_set
            or len({row["building_id"] for row in isolated_rows}) != 178
            or any(row["status"] != "success" for row in isolated_rows)
            or any(
                row["execution_mode"]
                != "isolated_per_building_same_parameters"
                for row in isolated_rows
            )
            or any(
                row["learning_runs_started"] != "0"
                or row["new_inference_runs"] != "0"
                for row in isolated_rows
            )
        ):
            raise AssertionError("sigma0.80 isolated measurement grain drift")
        for row in isolated_rows:
            output = REPO / row["accepted_output_path"]
            if (
                not output.is_file()
                or sha256_file(output) != row["accepted_output_sha256"]
            ):
                raise AssertionError(
                    f"sigma0.80 isolated output hash drift {row['building_id']}"
                )
        if not RECOVERY_INCIDENT.is_file():
            raise AssertionError("recovery incident record missing")
        recovery_qa = {
            "execution_mode": recovery["execution_mode"],
            "isolated_rows": len(isolated_rows),
            "successful_parts": recovery["successful_parts"],
            "failed_attempt_records": recovery["failed_attempt_records"],
            "manifest_sha256": sha256_file(recovery_manifest_path),
            "incident_sha256": sha256_file(RECOVERY_INCIDENT),
        }

    output_hash_mismatches = []
    for path_text, expected in manifest["output_sha256"].items():
        path = REPO / path_text
        observed = sha256_file(path) if path.is_file() else None
        if observed != expected:
            output_hash_mismatches.append(
                {
                    "path": path_text,
                    "expected": expected,
                    "observed": observed,
                }
            )
    if output_hash_mismatches:
        raise AssertionError(
            f"output hash mismatches {output_hash_mismatches[:3]}"
        )
    source_hash_mismatches = []
    for path_text, expected in manifest["source_sha256"].items():
        path = REPO / path_text
        observed = sha256_file(path) if path.is_file() else None
        if observed != expected:
            source_hash_mismatches.append(
                {
                    "path": path_text,
                    "expected": expected,
                    "observed": observed,
                }
            )
    if source_hash_mismatches:
        raise AssertionError(
            f"source hash mismatches {source_hash_mismatches[:3]}"
        )

    figure_info = {}
    for path in (
        [NOISE_FIGURE, DENSITY_FIGURE]
        if scope == "full"
        else [NOISE_FIGURE]
    ):
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            width, height = image.size
        if width < 1000 or height < 900:
            raise AssertionError(f"figure dimensions too small {path}")
        figure_info[str(path.relative_to(REPO))] = {
            "width": width,
            "height": height,
            "sha256": sha256_file(path),
        }

    return {
        "scope": scope,
        "measurement_rows": len(measurements),
        "stage_count": len(expected_stage_ids),
        "population_count": 178,
        "aggregate_rows": len(aggregates),
        "zero_stage_validation_rows": len(zero_rows),
        "monotonicity_rows": len(monotonic_rows),
        "manifest_output_hash_mismatches": len(output_hash_mismatches),
        "manifest_source_hash_mismatches": len(source_hash_mismatches),
        "figures": figure_info,
        "sigma0p80_recovery": recovery_qa,
        "learning_runs_started": 0,
        "new_inference_runs": 0,
        "qa_passed": True,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope", choices=("noise", "full"), required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    print(json.dumps(validate(args.scope), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
