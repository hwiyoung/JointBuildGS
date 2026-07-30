#!/usr/bin/env python3
"""Learning-zero anchor census preparation, aggregation, and QA.

This module does not import or start a training or optimization entry point.
Its only inference-producing companion is ``anchor_census_dense.py``, which
reuses the locked R1-prime-3 MASt3R reciprocal-match, fixed-pose DLT, and
2-source-pixel reprojection implementation.

Commands
--------
prepare
    Reconstruct the canonical 178-building population, verify the fixed
    58-building census set, and write the ordered ten-pair job inventory.
finalize
    Merge the 58 census records with the read-only 4907199 reproduction row,
    assign the fixed neutral boundary-map-v4 cells, and write CSV, manifest,
    map, and one-page measurement summary outputs.
qa
    Recheck population/set/schema/hash and fixed mechanical-assignment
    contracts for the generated bundle.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import math
import os
import shutil
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
os.environ.setdefault("XDG_CACHE_HOME", "/tmp")

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402


REPO = Path(__file__).resolve().parents[3]
DOCS = REPO / "docs"
SCRIPT_DIR = Path(__file__).resolve().parent
RUN_ID = "20260720_anchor_census"
RUN_DIR = REPO / "phases/p2-gsjso/runs" / RUN_ID

SNAPSHOT = DOCS / "regression_input_snapshot.csv"
V3_METRICS = DOCS / "experiments/boundary_map/tables/boundary_map_v3_metrics.csv"
V3_LADDER = DOCS / "archive/boundary_map/v3/tables/boundary_map_v3_ladder.csv"
V3_MANIFEST = DOCS / "experiments/boundary_map/manifests/boundary_map_v3_manifest.json"
V3_SCRIPT = SCRIPT_DIR / "boundary_map_v3.py"
V3_DENSE_SCRIPT = SCRIPT_DIR / "boundary_map_v3_dense.py"
DENSE_WRAPPER = SCRIPT_DIR / "anchor_census_dense.py"
DRIVER_SCRIPT = SCRIPT_DIR / "run_anchor_census_20260720.sh"
PREREG = DOCS / "사전등록서_품질축본선_잠금후보v1.5_20260720.md"
ENV_MANIFEST = DOCS / "e5_c001_s3ap_fm_env_manifest.json"
DENSE_CONFIG = (
    REPO / "phases/p2-gsjso/configs/e5_c001/e5_c001_s3ap_fm_dense_dial.json"
)
ALS_STATUS = (
    REPO
    / "phases/p0-audit/runs/w2_1_roofer_default_20260612_152729"
    / "building_reconstruction_status.csv"
)
R1P_MEASUREMENTS = (
    REPO
    / "phases/p2-gsjso/runs/boundary_and_robustness/20260719_boundary_map_v3"
    / "fm_dense_measurements.csv"
)
R1P_MANIFEST = (
    REPO
    / "phases/p2-gsjso/runs/boundary_and_robustness/20260719_boundary_map_v3"
    / "fm_dense_manifest.json"
)
S3AP_DIAL = DOCS / "e5_c001_s3ap_fm_dense_dial.csv"

JOBS = RUN_DIR / "anchor_census_jobs.json"
PREP_MANIFEST = RUN_DIR / "anchor_census_prepare_manifest.json"
INFERENCE_MEASUREMENTS = (
    RUN_DIR / "anchor_census_inference_measurements.csv"
)
INFERENCE_PAIRS = RUN_DIR / "anchor_census_pairs.csv"
INFERENCE_PROGRESS = RUN_DIR / "anchor_census_progress.json"
INFERENCE_MANIFEST = RUN_DIR / "anchor_census_inference_manifest.json"
MEASUREMENTS = RUN_DIR / "anchor_census_measurements.csv"
RUN_MANIFEST = RUN_DIR / "anchor_census_manifest.json"

DOC_MEASUREMENTS = DOCS / "experiments/boundary_map/tables/anchor_census_measurements.csv"
LADDER = DOCS / "archive/boundary_map/v4/tables/boundary_map_v4_ladder.csv"
TARGETS = DOCS / "archive/boundary_map/v4/tables/boundary_map_v4_targets.csv"
LOWCOUNT = DOCS / "experiments/boundary_map/tables/anchor_census_ambiguous_1_99.csv"
HIGHMAD = DOCS / "experiments/boundary_map/tables/anchor_census_high_count_high_mad.csv"
PUBLIC_MANIFEST = DOCS / "experiments/boundary_map/manifests/boundary_map_v4_manifest.json"
SUMMARY = DOCS / "experiments/boundary_map/reports/W_anchor_census_boundary_map_v4_summary_20260720.md"
FIGURE = (
    DOCS / "figs/boundary_map/boundary_map_v4_map.png"
)

ALLOWLIST = "census_FM_dense_dial_2px_only"
CRS = "EPSG:25832"
MAX_PAIRS = 10
SMALL_AREA_M2 = 50.0
ANCHOR_COUNT_THRESHOLD = 1
HIGH_MAD_THRESHOLD_M = 0.5
REPRODUCTION_ID = "DEBY_LOD2_4907199"
REPRODUCTION_EXPECTED = {
    "selected_dlt_point_count": 538,
    "footprint_inside_point_count": 373,
    "inside_z_median_m": -34.347425,
}

FIXED_SHORT_IDS = (
    "108247350",
    "108247351",
    "42364607",
    "4906999",
    "4907012",
    "4907013",
    "4907014",
    "4907015",
    "4907016",
    "4907019",
    "4907021",
    "4907022",
    "4907027",
    "4907030",
    "4907031",
    "4907032",
    "4907033",
    "4907034",
    "4907036",
    "4907167",
    "4907174",
    "4907187",
    "4908045",
    "4908051",
    "4908052",
    "4908157",
    "4908158",
    "4908161",
    "4908170",
    "4907029",
    "4907175",
    "107802038",
    "4907169",
    "4907168",
    "4907181",
    "4908046",
    "4908050",
    "4907508",
    "4907510",
    "4959758",
    "107807336",
    "4907182",
    "4908048",
    "42364659",
    "104583794",
    "4908044",
    "4908053",
    "4908054",
    "4908159",
    "4908160",
    "4908164",
    "4908165",
    "4908167",
    "4908176",
    "8573617",
    "4908166",
    "42364609",
    "104586480",
)
FIXED_IDS = tuple(f"DEBY_LOD2_{value}" for value in FIXED_SHORT_IDS)
PREVIOUSLY_MEASURED_FAILURE_IDS = (
    "DEBY_LOD2_4907199",
    "DEBY_LOD2_8568391",
    "DEBY_LOD2_4908162",
    "DEBY_LOD2_4908049",
    "DEBY_LOD2_4908169",
    "DEBY_LOD2_8568392",
)
OVERRIDE_IDS = {
    "DEBY_LOD2_4907199",
    "DEBY_LOD2_8568391",
}

CELL_1 = "cell_1_assembled"
CELL_2 = "cell_2_anchored"
CELL_3 = "cell_3_outline_only"
CELL_4 = "cell_4_beyond_image"
CELLS = (CELL_1, CELL_2, CELL_3, CELL_4)
LEGACY_LABEL = {
    CELL_1: "well-textured",
    CELL_2: "textureless, correspondence-anchored",
    CELL_3: "outline-only",
    CELL_4: "unobservable",
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def rel(path: Path | str) -> str:
    value = Path(path)
    try:
        return str(value.resolve().relative_to(REPO.resolve()))
    except ValueError:
        return str(value.resolve())


def sha256_file(path: Path, block_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(block_size), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_json(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def set_sha256(values: Iterable[str]) -> str:
    return sha256_json(sorted(set(values)))


def git_value(*args: str) -> str:
    try:
        return subprocess.check_output(
            ["git", *args],
            cwd=REPO,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def read_csv_fields(path: Path) -> list[str]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        return next(reader)


def fmt(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return "" if not math.isfinite(value) else f"{value:.6f}"
    return str(value)


def as_bool(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes"}


def as_int(value: Any) -> int | None:
    text = str(value).strip()
    if not text:
        return None
    return int(float(text))


def as_float(value: Any) -> float | None:
    text = str(value).strip()
    if not text:
        return None
    number = float(text)
    return number if math.isfinite(number) else None


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def atomic_csv(
    path: Path,
    rows: Sequence[Mapping[str, Any]],
    fields: Sequence[str],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(fields),
            extrasaction="ignore",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(
            [
                {field: fmt(row.get(field)) for field in fields}
                for row in rows
            ]
        )
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def load_v3() -> Any:
    spec = importlib.util.spec_from_file_location(
        "anchor_census_boundary_map_v3", V3_SCRIPT
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {V3_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    module.NEW_INFERENCE_TYPE = ALLOWLIST
    module.MAX_PAIRS = MAX_PAIRS
    return module


def population_inventory() -> dict[str, Any]:
    rows = read_csv(SNAPSHOT)
    lidar_rows = [row for row in rows if row["arm"] == "raw_lidar"]
    dense_rows = [row for row in rows if row["arm"] == "raw_dense"]
    lidar_by_id = {row["building_id"]: row for row in lidar_rows}
    dense_by_id = {row["building_id"]: row for row in dense_rows}
    if len(lidar_by_id) != 199 or len(dense_by_id) != 199:
        raise RuntimeError("snapshot arm population is not 199 unique")
    canonical = {
        building_id
        for building_id, row in lidar_by_id.items()
        if as_bool(row["assembled"])
    }
    dense_failures = {
        building_id
        for building_id in canonical
        if not as_bool(dense_by_id[building_id]["assembled"])
    }
    derived = dense_failures - set(PREVIOUSLY_MEASURED_FAILURE_IDS)
    fixed = set(FIXED_IDS)
    if len(canonical) != 178:
        raise RuntimeError(f"canonical count {len(canonical)} != 178")
    if len(dense_failures) != 64:
        raise RuntimeError(f"dense failure count {len(dense_failures)} != 64")
    if not set(PREVIOUSLY_MEASURED_FAILURE_IDS) <= dense_failures:
        raise RuntimeError("previously measured six are not dense failures")
    if derived != fixed or len(FIXED_IDS) != len(fixed):
        raise RuntimeError(
            "fixed census set differs from 64 failures minus measured six: "
            f"missing={sorted(derived-fixed)} extra={sorted(fixed-derived)}"
        )
    small_ids = {
        building_id
        for building_id in derived
        if float(dense_by_id[building_id]["footprint_area_m2"])
        < SMALL_AREA_M2
    }
    if len(small_ids) != 15:
        raise RuntimeError(f"census small count {len(small_ids)} != 15")
    return {
        "rows": rows,
        "lidar_by_id": lidar_by_id,
        "dense_by_id": dense_by_id,
        "canonical": canonical,
        "dense_failures": dense_failures,
        "derived": derived,
        "small_ids": small_ids,
    }


def priority_group(
    building_id: str,
    rank: int,
    inventory: Mapping[str, Any],
) -> str:
    if rank <= 2:
        return "canonical_C001_remaining"
    row = inventory["dense_by_id"][building_id]
    manual = as_bool(row.get("manual_label_available"))
    small = building_id in inventory["small_ids"]
    if small and manual:
        return "manual_label_small"
    if small:
        return "remaining_small_area_desc"
    if manual:
        return "manual_label_nonsmall"
    return "remaining_nonsmall_area_desc"


def prepare() -> None:
    required = (
        SNAPSHOT,
        V3_METRICS,
        V3_LADDER,
        V3_MANIFEST,
        V3_SCRIPT,
        V3_DENSE_SCRIPT,
        DENSE_WRAPPER,
        DRIVER_SCRIPT,
        PREREG,
        ENV_MANIFEST,
        DENSE_CONFIG,
    )
    missing = [rel(path) for path in required if not path.is_file()]
    if missing:
        raise RuntimeError(f"missing preparation sources: {missing}")
    inventory = population_inventory()
    v3 = load_v3()
    census_set = set(FIXED_IDS)
    semantic_ids = census_set & set(v3.C001_IDS)
    addresses = v3.semantic_addresses(semantic_ids)
    missing_semantic_ids = {
        building_id
        for building_id in semantic_ids
        if not addresses.get(building_id)
    }
    projected = v3.projected_pairs_for(census_set)
    if missing_semantic_ids:
        original_c001_ids = v3.C001_IDS
        v3.C001_IDS = tuple(
            building_id
            for building_id in original_c001_ids
            if building_id not in missing_semantic_ids
        )
        try:
            projected.update(
                v3.projected_pairs_for(missing_semantic_ids)
            )
        finally:
            v3.C001_IDS = original_c001_ids
    jobs: list[dict[str, Any]] = []
    pair_counts: dict[str, int] = {}
    for rank, building_id in enumerate(FIXED_IDS, start=1):
        if (
            building_id in set(v3.C001_IDS)
            and building_id not in missing_semantic_ids
        ):
            pairs = v3.select_semantic_pairs(
                addresses.get(building_id, []),
                "c001_frozen_semantic_region",
            )
        else:
            pairs = projected.get(building_id, [])
        pair_counts[building_id] = len(pairs)
        if len(pairs) != MAX_PAIRS:
            raise RuntimeError(
                f"{building_id} pair count {len(pairs)} != {MAX_PAIRS}"
            )
        jobs.append(
            {
                "building_id": building_id,
                "priority_rank": rank,
                "priority_group": priority_group(
                    building_id, rank, inventory
                ),
                "primary_assignment": "dense_failure_census",
                "queue_inclusion_reason": (
                    "canonical_raw_lidar_assembled_and_raw_dense_failed_"
                    "and_not_previously_measured"
                ),
                "pairs": pairs,
            }
        )
    model = v3.model_contract()
    if model["new_inference_type"] != ALLOWLIST:
        raise RuntimeError("allowlist did not propagate to model contract")
    payload = {"model": model, "jobs": jobs}
    atomic_json(JOBS, payload)

    source_paths = required + (Path(__file__).resolve(),)
    manifest = {
        "schema": "jointbuildgs.anchor_census.prepare.v1",
        "created_utc": now(),
        "git_head": git_value("rev-parse", "HEAD"),
        "branch": git_value("branch", "--show-current"),
        "derivation": {
            "formula": (
                "canonical raw_lidar assembled=true 178; raw_dense "
                "assembled=false intersection 64; minus previously measured "
                "six = census 58"
            ),
            "canonical_count": len(inventory["canonical"]),
            "dense_failure_count": len(inventory["dense_failures"]),
            "previously_measured_count": len(
                PREVIOUSLY_MEASURED_FAILURE_IDS
            ),
            "census_count": len(FIXED_IDS),
            "nonsmall_count": len(FIXED_IDS)
            - len(inventory["small_ids"]),
            "small_lt50_count": len(inventory["small_ids"]),
            "arithmetic_check": "64-6=58; 43+15=58",
        },
        "set_validation": {
            "fixed_list_unique": len(FIXED_IDS) == len(set(FIXED_IDS)),
            "derived_equals_fixed": inventory["derived"] == set(FIXED_IDS),
            "derived_set_sha256": set_sha256(inventory["derived"]),
            "fixed_set_sha256": set_sha256(FIXED_IDS),
            "missing_from_fixed": sorted(
                inventory["derived"] - set(FIXED_IDS)
            ),
            "extra_in_fixed": sorted(
                set(FIXED_IDS) - inventory["derived"]
            ),
        },
        "priority_order": list(FIXED_IDS),
        "previously_measured_failure_ids": list(
            PREVIOUSLY_MEASURED_FAILURE_IDS
        ),
        "reproduction_queue_tail": {
            "building_id": REPRODUCTION_ID,
            "queue_rank": 59,
            "cache_reuse_allowed": True,
            "expected": REPRODUCTION_EXPECTED,
        },
        "pair_selection": {
            "maximum_and_required_pairs_per_census_building": MAX_PAIRS,
            "total_census_pairs": sum(pair_counts.values()),
            "pair_counts": pair_counts,
            "address_source_counts": dict(
                Counter(
                    pair["crop_source"]
                    for job in jobs
                    for pair in job["pairs"]
                )
            ),
            "c001_without_frozen_semantic_region": sorted(
                missing_semantic_ids
            ),
            "c001_address_recovery": (
                "for C001 census targets absent from the frozen semantic-"
                "region metadata, call the unchanged R1prime v2 projected-"
                "footprint pair generator; LoD2 height remains projection/"
                "classification only and the fixed FULL_OPENCV DLT branch "
                "is used"
            ),
            "rule": (
                "R1prime identical: C001 frozen semantic-region support "
                "ranking; otherwise v2 projected footprint at LoD2 "
                "classification/projection-only height; retain top 10; "
                "summary pooling uses cross-acquisition-minute-block pairs "
                "with fixed-camera-centre baseline >0.06 m"
            ),
        },
        "environment_lock": model,
        "jobs": rel(JOBS),
        "jobs_sha256": sha256_file(JOBS),
        "source_sha256": {
            rel(path): sha256_file(path) for path in source_paths
        },
        "learning_runs_started": 0,
        "new_inference_allowlist": [ALLOWLIST],
        "reference_lod2_role": "projection and classification only",
        "interpretation_or_verdict": None,
    }
    atomic_json(PREP_MANIFEST, manifest)


def inference_execution(row: Mapping[str, Any]) -> str:
    new_runs = as_int(row.get("new_mast3r_inference_runs")) or 0
    cache_runs = as_int(row.get("cache_reuse_runs")) or 0
    if new_runs and cache_runs:
        return "mixed_new_and_cache"
    if new_runs:
        return "new_inference"
    if cache_runs:
        return "cache_reuse"
    return "no_pair_inference"


def anchor_status(row: Mapping[str, Any]) -> str:
    status = str(row.get("status", ""))
    if status == "complete" and as_bool(row.get("measurement_complete")):
        return "measured"
    if status == "partial_time_budget" or (
        (as_int(row.get("pending_pair_count")) or 0) > 0
    ):
        return "incomplete_budget"
    if status in {
        "ineligible_no_summary_pair",
        "prerequisite_missing",
        "partial_with_failures",
    }:
        return "unmeasurable"
    return "unmeasurable"


def reproduction_row() -> dict[str, Any]:
    rows = {
        row["building_id"]: row for row in read_csv(R1P_MEASUREMENTS)
    }
    if REPRODUCTION_ID not in rows:
        raise RuntimeError("R1prime 4907199 reproduction source is missing")
    row = dict(rows[REPRODUCTION_ID])
    selected = as_int(row["selected_dlt_point_count"])
    inside = as_int(row["footprint_inside_point_count"])
    z_value = as_float(row["inside_z_median_m"])
    if (
        selected != REPRODUCTION_EXPECTED["selected_dlt_point_count"]
        or inside != REPRODUCTION_EXPECTED[
            "footprint_inside_point_count"
        ]
        or z_value is None
        or abs(z_value - REPRODUCTION_EXPECTED["inside_z_median_m"])
        > 5e-7
    ):
        raise RuntimeError(f"4907199 reproduction source drift: {row}")
    row.update(
        {
            "priority_rank": 59,
            "priority_group": "R1prime_reproduction_cache_tail",
            "primary_assignment": "reproduction_check",
            "queue_inclusion_reason": "R1prime_locked_value_reproduction",
            "new_mast3r_inference_runs": 0,
            "cache_reuse_runs": as_int(row["selected_pair_count"]) or 0,
            "learning_runs_started": 0,
            "new_inference_type": ALLOWLIST,
            "reproduction_check_required": True,
            "reproduction_expected_selected_dlt_point_count": (
                REPRODUCTION_EXPECTED["selected_dlt_point_count"]
            ),
            "reproduction_expected_footprint_inside_point_count": (
                REPRODUCTION_EXPECTED["footprint_inside_point_count"]
            ),
            "reproduction_expected_inside_z_median_m": (
                REPRODUCTION_EXPECTED["inside_z_median_m"]
            ),
            "reproduction_check_passed": True,
        }
    )
    return row


def measurement_extras(
    row: Mapping[str, Any],
    role: str,
    source_path: Path,
) -> dict[str, Any]:
    status = anchor_status(row)
    return {
        "census_role": role,
        "anchor_status": status,
        "inference_execution_this_census": inference_execution(row),
        "source_measurement_path": rel(source_path),
        "source_measurement_sha256": sha256_file(source_path),
        "source_measurement_git_commit": git_value(
            "log", "-1", "--format=%H", "--", rel(source_path)
        ),
        "pair_selection_rule": (
            "R1prime same 10-pair address/ranking; cross-acquisition-"
            "minute-block and fixed-camera-centre baseline >0.06m pooling"
        ),
        "reprojection_threshold_px": 2.0,
        "reference_lod2_role": "projection and classification only",
        "learning_runs_started": 0,
        "new_inference_allowlist": ALLOWLIST,
    }


def existing_failure_measurements(
    final_measurements: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    prior = {
        row["building_id"]: dict(row)
        for row in read_csv(R1P_MEASUREMENTS)
    }
    output: dict[str, dict[str, Any]] = {}
    for building_id in PREVIOUSLY_MEASURED_FAILURE_IDS:
        if building_id == "DEBY_LOD2_8568392":
            rows = [
                row
                for row in read_csv(S3AP_DIAL)
                if row["building_id"] == building_id
                and row["threshold_label"] == "2px"
            ]
            if len(rows) != 1:
                raise RuntimeError("8568392 locked 2px row is not unique")
            source = rows[0]
            output[building_id] = {
                "building_id": building_id,
                "status": (
                    "complete"
                    if source["status"] == "scored"
                    else source["status"]
                ),
                "measurement_complete": "true",
                "selected_dlt_point_count": source[
                    "selected_dlt_point_count"
                ],
                "footprint_inside_point_count": source[
                    "footprint_inside_point_count"
                ],
                "inside_z_median_m": source[
                    "inside_z_median_local_m"
                ],
                "inside_z_mad_m": source["inside_z_mad_m"],
                "coverage_ratio": source["coverage_ratio"],
                "selected_pair_count": source["selected_pair_count"],
                "completed_pair_count": source["selected_pair_count"],
                "eligible_pair_count": source["eligible_pair_count"],
                "failed_pair_count": 0,
                "pending_pair_count": 0,
                "anchor_status": "measured",
                "measurement_source": rel(S3AP_DIAL),
                "measurement_source_sha256": sha256_file(S3AP_DIAL),
                "measurement_lineage": "S3Ap_locked_2px_read_only",
            }
        elif building_id == REPRODUCTION_ID:
            output[building_id] = dict(final_measurements[building_id])
            output[building_id]["measurement_source"] = rel(
                R1P_MEASUREMENTS
            )
            output[building_id]["measurement_source_sha256"] = sha256_file(
                R1P_MEASUREMENTS
            )
            output[building_id][
                "measurement_lineage"
            ] = "R1prime_reproduction_cache_read_only"
        else:
            if building_id not in prior:
                raise RuntimeError(
                    f"missing prior measurement for {building_id}"
                )
            output[building_id] = dict(prior[building_id])
            output[building_id]["anchor_status"] = anchor_status(
                output[building_id]
            )
            output[building_id]["measurement_source"] = rel(
                R1P_MEASUREMENTS
            )
            output[building_id]["measurement_source_sha256"] = sha256_file(
                R1P_MEASUREMENTS
            )
            output[building_id][
                "measurement_lineage"
            ] = "R1prime_measurement_read_only"
    return output


def roof_inventory() -> dict[str, dict[str, str]]:
    output: dict[str, dict[str, str]] = {}
    for row in read_csv(ALS_STATUS):
        if row["input"] != "ALS":
            continue
        building_id = row["building_id"]
        if building_id in output:
            raise RuntimeError(f"duplicate ALS roof row: {building_id}")
        roof_type = row.get("rf_roof_type", "")
        if roof_type in {"horizontal", "multiple horizontal"}:
            group = "horizontal"
        elif roof_type == "slanted":
            group = "sloped"
        else:
            group = "unavailable_or_other"
        output[building_id] = {
            "ref_roof_type": roof_type or "unavailable_in_ALS_status",
            "ref_roof_slope_group": group,
        }
    return output


def outline_observable(row: Mapping[str, Any]) -> bool:
    return (
        (as_int(row.get("representative_view_count")) or 0) >= 2
        and (as_float(row.get("outline_inframe_frac_max")) or 0.0) > 0.0
        and (as_int(row.get("outline_valid_pixel_count_max")) or 0) >= 3
    )


def build_ladder(
    census_by_id: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    population = population_inventory()
    metrics = read_csv(V3_METRICS)
    if len(metrics) != 178:
        raise RuntimeError("boundary_map_v3_metrics is not 178 rows")
    existing = existing_failure_measurements(census_by_id)
    all_failure_measurements = {
        **existing,
        **{building_id: dict(row) for building_id, row in census_by_id.items()
           if building_id in set(FIXED_IDS)},
    }
    if set(all_failure_measurements) != population["dense_failures"]:
        raise RuntimeError(
            "failure measurement inventory does not cover exact 64 failures"
        )
    roofs = roof_inventory()
    output: list[dict[str, Any]] = []
    for source in sorted(metrics, key=lambda item: item["building_id"]):
        building_id = source["building_id"]
        dense_assembled = as_bool(source["dense_assembled"])
        observable = outline_observable(source)
        measurement = (
            None
            if dense_assembled
            else all_failure_measurements[building_id]
        )
        status = (
            "not_applicable_dense_assembled"
            if measurement is None
            else str(
                measurement.get("anchor_status")
                or anchor_status(measurement)
            )
        )
        inside = (
            None
            if measurement is None
            else as_int(measurement.get("footprint_inside_point_count"))
        )
        if dense_assembled:
            cell = CELL_1
            basis = "raw_dense assembled=true"
        elif status == "measured" and (inside or 0) >= ANCHOR_COUNT_THRESHOLD:
            cell = CELL_2
            basis = (
                "raw_dense assembled=false and measured inside_count>=1"
            )
        elif observable:
            cell = CELL_3
            basis = (
                "raw_dense assembled=false and no measured anchor assignment "
                "and outline_observable=true"
            )
        else:
            cell = CELL_4
            basis = (
                "raw_dense assembled=false and no measured anchor assignment "
                "and outline_observable=false"
            )
        if status == "unmeasurable":
            sticker = "앵커 미판정"
        elif status == "incomplete_budget":
            sticker = "앵커 미완"
        else:
            sticker = ""
        roof = roofs.get(
            building_id,
            {
                "ref_roof_type": "missing_ALS_row",
                "ref_roof_slope_group": "unavailable_or_other",
            },
        )
        override = building_id in OVERRIDE_IDS
        output.append(
            {
                "building_id": building_id,
                "population_scope": "canonical_raw_lidar_assembled_178",
                "dense_assembled": dense_assembled,
                "dense_status_source": rel(SNAPSHOT),
                "footprint_area_m2": source["footprint_area_m2"],
                "small_lt50": source["small_lt50"],
                "anchor_status": status,
                "anchor_measurement_source": (
                    ""
                    if measurement is None
                    else measurement.get(
                        "measurement_source",
                        measurement.get("source_measurement_path", ""),
                    )
                ),
                "anchor_measurement_lineage": (
                    ""
                    if measurement is None
                    else measurement.get(
                        "measurement_lineage",
                        "anchor_census_current",
                    )
                ),
                "anchor_selected_dlt_point_count": (
                    ""
                    if measurement is None
                    else measurement.get("selected_dlt_point_count", "")
                ),
                "anchor_footprint_inside_point_count": (
                    ""
                    if measurement is None
                    else measurement.get(
                        "footprint_inside_point_count", ""
                    )
                ),
                "anchor_inside_z_median_m": (
                    ""
                    if measurement is None
                    else measurement.get("inside_z_median_m", "")
                ),
                "anchor_inside_z_mad_m": (
                    ""
                    if measurement is None
                    else measurement.get("inside_z_mad_m", "")
                ),
                "anchor_coverage_ratio": (
                    ""
                    if measurement is None
                    else measurement.get("coverage_ratio", "")
                ),
                "anchor_selected_pair_count": (
                    ""
                    if measurement is None
                    else measurement.get("selected_pair_count", "")
                ),
                "anchor_completed_pair_count": (
                    ""
                    if measurement is None
                    else measurement.get("completed_pair_count", "")
                ),
                "anchor_eligible_pair_count": (
                    ""
                    if measurement is None
                    else measurement.get("eligible_pair_count", "")
                ),
                "anchor_zero_observed": (
                    ""
                    if status != "measured"
                    else (inside or 0) == 0
                ),
                "anchor_undecided_sticker": sticker,
                "anchor_count_threshold": ANCHOR_COUNT_THRESHOLD,
                "anchor_mad_threshold_status": "not_preregistered",
                "outline_observable": observable,
                "outline_representative_view_count": source[
                    "representative_view_count"
                ],
                "outline_inframe_frac_max": source[
                    "outline_inframe_frac_max"
                ],
                "outline_valid_pixel_count_max": source[
                    "outline_valid_pixel_count_max"
                ],
                "outline_definition_source": (
                    "boundary_map_v3: views>=2 and inframe_max>0 and "
                    "valid_pixel_max>=3"
                ),
                "cell_label": cell,
                "cell_assignment_basis": basis,
                "legacy_v1_2_label_reference": LEGACY_LABEL[cell],
                "ref_roof_type": roof["ref_roof_type"],
                "ref_roof_slope_group": roof["ref_roof_slope_group"],
                "ref_roof_type_source": (
                    f"{rel(ALS_STATUS)}: input=ALS, rf_roof_type"
                ),
                "ref_roof_type_role": "classification only",
                "override_recorded": override,
                "override_source": (
                    "B-1 measured flat-seed evidence"
                    if override
                    else ""
                ),
                "override_inside_count": inside if override else "",
                "override_effect_on_cell": (
                    "none; measured formula also yields cell_2_anchored"
                    if override
                    else ""
                ),
                "texture_low_gradient_fraction": source[
                    "texture_low_gradient_fraction"
                ],
                "texture_grad_p10": source["texture_grad_p10"],
                "texture_signal_role": (
                    "descriptive covariate; not used in cell assignment"
                ),
                "crs": CRS,
                "learning_runs_started": 0,
                "new_inference_type": (
                    ALLOWLIST
                    if building_id in set(FIXED_IDS)
                    else "none; existing measurement read-only"
                ),
            }
        )
    return output


LADDER_FIELDS = [
    "building_id",
    "population_scope",
    "dense_assembled",
    "dense_status_source",
    "footprint_area_m2",
    "small_lt50",
    "anchor_status",
    "anchor_measurement_source",
    "anchor_measurement_lineage",
    "anchor_selected_dlt_point_count",
    "anchor_footprint_inside_point_count",
    "anchor_inside_z_median_m",
    "anchor_inside_z_mad_m",
    "anchor_coverage_ratio",
    "anchor_selected_pair_count",
    "anchor_completed_pair_count",
    "anchor_eligible_pair_count",
    "anchor_zero_observed",
    "anchor_undecided_sticker",
    "anchor_count_threshold",
    "anchor_mad_threshold_status",
    "outline_observable",
    "outline_representative_view_count",
    "outline_inframe_frac_max",
    "outline_valid_pixel_count_max",
    "outline_definition_source",
    "cell_label",
    "cell_assignment_basis",
    "legacy_v1_2_label_reference",
    "ref_roof_type",
    "ref_roof_slope_group",
    "ref_roof_type_source",
    "ref_roof_type_role",
    "override_recorded",
    "override_source",
    "override_inside_count",
    "override_effect_on_cell",
    "texture_low_gradient_fraction",
    "texture_grad_p10",
    "texture_signal_role",
    "crs",
    "learning_runs_started",
    "new_inference_type",
]

TARGET_FIELDS = [
    "building_id",
    "cell_label",
    "anchor_status",
    "anchor_footprint_inside_point_count",
    "anchor_inside_z_median_m",
    "anchor_inside_z_mad_m",
    "anchor_coverage_ratio",
    "anchor_undecided_sticker",
    "outline_observable",
    "small_lt50",
    "ref_roof_type",
    "ref_roof_slope_group",
    "legacy_v1_2_label_reference",
    "texture_low_gradient_fraction",
    "texture_grad_p10",
    "learning_runs_started",
]

AMBIGUOUS_FIELDS = [
    "building_id",
    "cell_label",
    "anchor_status",
    "anchor_footprint_inside_point_count",
    "anchor_inside_z_median_m",
    "anchor_inside_z_mad_m",
    "anchor_coverage_ratio",
    "small_lt50",
    "ref_roof_type",
    "ref_roof_slope_group",
    "record_note",
    "learning_runs_started",
]


def make_map(ladder: Sequence[Mapping[str, Any]]) -> None:
    v3 = load_v3()
    geometries = v3.load_footprint_geometries()
    colors = {
        CELL_1: "#2a9d8f",
        CELL_2: "#3a86ff",
        CELL_3: "#f4a261",
        CELL_4: "#d62828",
    }
    counts = Counter(row["cell_label"] for row in ladder)
    figure, axis = plt.subplots(figsize=(13, 10), dpi=190)
    for row in sorted(ladder, key=lambda item: item["building_id"]):
        geometry = geometries[row["building_id"]]
        polygons = (
            [geometry]
            if geometry.geom_type == "Polygon"
            else list(geometry.geoms)
        )
        small = as_bool(row["small_lt50"])
        for polygon in polygons:
            x_coord, y_coord = polygon.exterior.xy
            axis.fill(
                x_coord,
                y_coord,
                facecolor=colors[row["cell_label"]],
                edgecolor="#333333" if small else "white",
                linewidth=0.35 if small else 0.18,
                hatch="////" if small else None,
            )
    axis.set_aspect("equal", adjustable="box")
    axis.set_xlabel("Easting (m), EPSG:25832")
    axis.set_ylabel("Northing (m), EPSG:25832")
    axis.set_title(
        "Boundary map v4 — canonical 178 mechanical cells\n"
        "Small buildings (<50 m²) are hatched"
    )
    axis.grid(alpha=0.12)
    handles = [
        Patch(
            facecolor=colors[cell],
            edgecolor="none",
            label=f"{cell} (n={counts[cell]})",
        )
        for cell in CELLS
    ]
    handles.append(
        Patch(
            facecolor="white",
            edgecolor="#333333",
            hatch="////",
            label="small_lt50",
        )
    )
    axis.legend(
        handles=handles,
        loc="best",
        fontsize=8,
        framealpha=0.94,
    )
    figure.text(
        0.01,
        0.01,
        "LoD2/ALS references are used for projection or classification only.",
        fontsize=7,
        color="#444444",
    )
    figure.tight_layout(rect=(0, 0.025, 1, 1))
    FIGURE.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(FIGURE)
    plt.close(figure)


def md_table(
    rows: Sequence[Mapping[str, Any]],
    fields: Sequence[tuple[str, str]],
) -> list[str]:
    lines = [
        "| " + " | ".join(label for _key, label in fields) + " |",
        "|" + "|".join("---" for _key, _label in fields) + "|",
    ]
    if not rows:
        lines.append(
            "| " + " | ".join("없음" if index == 0 else "" for index in range(len(fields))) + " |"
        )
        return lines
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                str(row.get(key, "")).replace("|", "/")
                for key, _label in fields
            )
            + " |"
        )
    return lines


def summary_markdown(
    ladder: Sequence[Mapping[str, Any]],
    measurements: Sequence[Mapping[str, Any]],
    lowcount: Sequence[Mapping[str, Any]],
    highmad: Sequence[Mapping[str, Any]],
    status: str,
) -> str:
    counts = Counter(row["cell_label"] for row in ladder)
    small_counts = Counter(
        row["cell_label"]
        for row in ladder
        if as_bool(row["small_lt50"])
    )
    nonsmall_counts = Counter(
        row["cell_label"]
        for row in ladder
        if not as_bool(row["small_lt50"])
    )
    new_cell2 = [
        row
        for row in ladder
        if row["building_id"] in set(FIXED_IDS)
        and row["cell_label"] == CELL_2
    ]
    unmeasurable = [
        row
        for row in ladder
        if row["anchor_status"] == "unmeasurable"
    ]
    incomplete = [
        row
        for row in ladder
        if row["anchor_status"] == "incomplete_budget"
    ]
    row199 = next(
        row for row in measurements if row["building_id"] == REPRODUCTION_ID
    )
    lines = [
        "# 앵커 census 및 boundary_map_v4 측정 요약",
        "",
        f"- 산출 상태: `{status}`",
        "- 실행 범위: 정본 dense 실패 64동 중 기측정 6동을 제외한 "
        "58동 + 4907199 재현 확인 1행",
        "- 학습 실행 수: `0`",
        f"- 신규 추론 allowlist: `{ALLOWLIST}`",
        "- 참조 LoD2/ALS 역할: 투영·분류 전용",
        "",
        "## 1. 대상 및 완료 행",
        "",
        "| 항목 | 수 |",
        "|---|---:|",
        "| 정본 raw_lidar 조립 성공 | 178 |",
        "| 정본 raw_dense 조립 실패 | 64 |",
        "| 기측정 실패 건물 | 6 |",
        "| census 고정 명단 | 58 |",
        "| 재현 확인 포함 측정 CSV 행 | 59 |",
        "",
        "## 2. 중립 셀 인원",
        "",
        "| 셀 | 전체 | 비소형 | 소형(<50㎡) |",
        "|---|---:|---:|---:|",
    ]
    for cell in CELLS:
        lines.append(
            f"| `{cell}` | {counts[cell]} | {nonsmall_counts[cell]} | "
            f"{small_counts[cell]} |"
        )
    lines.extend(
        [
            "",
            "## 3. census에서 기록된 cell_2 행",
            "",
            *md_table(
                new_cell2,
                (
                    ("building_id", "building_id"),
                    (
                        "anchor_footprint_inside_point_count",
                        "inside 점수",
                    ),
                    ("anchor_inside_z_mad_m", "inside z MAD(m)"),
                    ("ref_roof_type", "ref roof type"),
                    ("ref_roof_slope_group", "수평/경사"),
                    ("small_lt50", "small"),
                ),
            ),
            "",
            "## 4. 애매 지대 A — 발자국 안 점수 1~99",
            "",
            *md_table(
                lowcount,
                (
                    ("building_id", "building_id"),
                    (
                        "anchor_footprint_inside_point_count",
                        "inside 점수",
                    ),
                    ("anchor_inside_z_mad_m", "inside z MAD(m)"),
                    ("ref_roof_type", "ref roof type"),
                    ("small_lt50", "small"),
                ),
            ),
            "",
            "> 전례: 8568392의 6점은 2026-07-15 검수에서 "
            "n<20 재료 미달로 기록됐다.",
            "",
            "## 5. 애매 지대 B — 점수 ≥100 및 inside z MAD >0.5 m",
            "",
            *md_table(
                highmad,
                (
                    ("building_id", "building_id"),
                    (
                        "anchor_footprint_inside_point_count",
                        "inside 점수",
                    ),
                    ("anchor_inside_z_mad_m", "inside z MAD(m)"),
                    ("ref_roof_type", "ref roof type"),
                    ("small_lt50", "small"),
                ),
            ),
            "",
            "## 6. 4907199 재현 확인",
            "",
            "| selected DLT | footprint inside | inside z median(m) | "
            "cache/new |",
            "|---:|---:|---:|---|",
            f"| {row199['selected_dlt_point_count']} | "
            f"{row199['footprint_inside_point_count']} | "
            f"{row199['inside_z_median_m']} | "
            f"{row199['inference_execution_this_census']} |",
            "",
            "## 7. 측정불능 및 미완 목록",
            "",
            "### 측정불능",
            "",
            *md_table(
                unmeasurable,
                (
                    ("building_id", "building_id"),
                    ("anchor_status", "anchor status"),
                    ("cell_label", "cell"),
                    (
                        "anchor_undecided_sticker",
                        "딱지",
                    ),
                ),
            ),
            "",
            "### 예산·진행 미완",
            "",
            *md_table(
                incomplete,
                (
                    ("building_id", "building_id"),
                    ("anchor_status", "anchor status"),
                    ("cell_label", "cell"),
                    (
                        "anchor_undecided_sticker",
                        "딱지",
                    ),
                ),
            ),
            "",
            "## 8. 점수 분포 기록",
            "",
        ]
    )
    failed_rows = [
        row for row in ladder if not as_bool(row["dense_assembled"])
    ]
    measured = [
        row for row in failed_rows if row["anchor_status"] == "measured"
    ]
    zero = sum(
        (as_int(row["anchor_footprint_inside_point_count"]) or 0) == 0
        for row in measured
    )
    low = sum(
        1
        <= (as_int(row["anchor_footprint_inside_point_count"]) or 0)
        <= 99
        for row in measured
    )
    high = sum(
        (as_int(row["anchor_footprint_inside_point_count"]) or 0) >= 100
        for row in measured
    )
    lines.extend(
        [
            f"- 측정 완료 실패동: 0점 {zero}동 · 1~99점 {low}동 · "
            f"100점 이상 {high}동",
            f"- 측정불능 {len(unmeasurable)}동 · 미완 {len(incomplete)}동",
            "- 위 구간은 고정 문턱(inside 점수 1) 민감 구간과 "
            "고점수·고MAD 조건을 그대로 집계한 값이다.",
            "",
        ]
    )
    return "\n".join(lines)


def output_hashes(paths: Iterable[Path]) -> dict[str, str]:
    return {
        rel(path): sha256_file(path)
        for path in paths
        if path.is_file()
    }


def finalize() -> None:
    required = (
        JOBS,
        PREP_MANIFEST,
        INFERENCE_MEASUREMENTS,
        INFERENCE_PAIRS,
        INFERENCE_PROGRESS,
        INFERENCE_MANIFEST,
        R1P_MEASUREMENTS,
        R1P_MANIFEST,
        S3AP_DIAL,
        ALS_STATUS,
    )
    missing = [rel(path) for path in required if not path.is_file()]
    if missing:
        raise RuntimeError(f"missing finalize sources: {missing}")
    inference_rows = read_csv(INFERENCE_MEASUREMENTS)
    if len(inference_rows) != len(FIXED_IDS):
        raise RuntimeError(
            f"inference row count {len(inference_rows)} != 58"
        )
    by_id = {row["building_id"]: row for row in inference_rows}
    if set(by_id) != set(FIXED_IDS) or len(by_id) != len(inference_rows):
        raise RuntimeError("inference identifiers differ from fixed census")

    measurements: list[dict[str, Any]] = []
    for building_id in FIXED_IDS:
        row = dict(by_id[building_id])
        row.update(
            measurement_extras(
                row,
                "fixed_dense_failure_census",
                INFERENCE_MEASUREMENTS,
            )
        )
        measurements.append(row)
    row199 = reproduction_row()
    row199.update(
        measurement_extras(
            row199,
            "R1prime_reproduction_cache_tail",
            R1P_MEASUREMENTS,
        )
    )
    measurements.append(row199)

    base_fields = read_csv_fields(INFERENCE_MEASUREMENTS)
    measurement_fields = list(base_fields)
    for field in (
        "census_role",
        "anchor_status",
        "inference_execution_this_census",
        "source_measurement_path",
        "source_measurement_sha256",
        "source_measurement_git_commit",
        "pair_selection_rule",
        "reprojection_threshold_px",
        "reference_lod2_role",
        "new_inference_allowlist",
    ):
        if field not in measurement_fields:
            measurement_fields.append(field)
    atomic_csv(MEASUREMENTS, measurements, measurement_fields)

    census_by_id = {
        row["building_id"]: row
        for row in measurements
        if row["building_id"] in set(FIXED_IDS)
    }
    ladder = build_ladder(
        {
            **census_by_id,
            REPRODUCTION_ID: row199,
        }
    )
    targets = [
        row
        for row in ladder
        if row["cell_label"] in {CELL_2, CELL_3}
    ]
    lowcount = [
        {
            **row,
            "record_note": (
                "2026-07-15 n<20 material-insufficient precedent"
                if row["building_id"] == "DEBY_LOD2_8568392"
                else "inside count sensitivity interval 1-99"
            ),
        }
        for row in ladder
        if row["anchor_status"] == "measured"
        and 1
        <= (as_int(row["anchor_footprint_inside_point_count"]) or 0)
        <= 99
    ]
    highmad = [
        {
            **row,
            "record_note": "inside count>=100 and inside z MAD>0.5m",
        }
        for row in ladder
        if row["anchor_status"] == "measured"
        and (as_int(row["anchor_footprint_inside_point_count"]) or 0)
        >= 100
        and (as_float(row["anchor_inside_z_mad_m"]) or 0.0)
        > HIGH_MAD_THRESHOLD_M
    ]

    terminal_incomplete = [
        row
        for row in measurements[:58]
        if row["anchor_status"] == "incomplete_budget"
    ]
    unmeasurable = [
        row
        for row in measurements[:58]
        if row["anchor_status"] == "unmeasurable"
    ]
    status = (
        "measurement_partial_budget"
        if terminal_incomplete
        else (
            "complete_with_unmeasurable"
            if unmeasurable
            else "complete"
        )
    )

    inference_manifest = json.loads(
        INFERENCE_MANIFEST.read_text(encoding="utf-8")
    )
    prep_manifest = json.loads(PREP_MANIFEST.read_text(encoding="utf-8"))
    run_sources = (
        SNAPSHOT,
        V3_METRICS,
        V3_LADDER,
        V3_MANIFEST,
        V3_SCRIPT,
        V3_DENSE_SCRIPT,
        DENSE_WRAPPER,
        DRIVER_SCRIPT,
        PREREG,
        ENV_MANIFEST,
        DENSE_CONFIG,
        ALS_STATUS,
        R1P_MEASUREMENTS,
        R1P_MANIFEST,
        S3AP_DIAL,
        JOBS,
        PREP_MANIFEST,
        INFERENCE_MEASUREMENTS,
        INFERENCE_PAIRS,
        INFERENCE_PROGRESS,
        INFERENCE_MANIFEST,
        Path(__file__).resolve(),
    )
    run_manifest = {
        "schema": "jointbuildgs.anchor_census.measurement.v1",
        "created_utc": now(),
        "status": status,
        "git_head_at_finalize": git_value("rev-parse", "HEAD"),
        "branch": git_value("branch", "--show-current"),
        "derivation": prep_manifest["derivation"],
        "set_validation": prep_manifest["set_validation"],
        "priority_order": list(FIXED_IDS) + [REPRODUCTION_ID],
        "row_counts": {
            "census": 58,
            "reproduction": 1,
            "total": len(measurements),
            "unmeasurable_census": len(unmeasurable),
            "incomplete_budget_census": len(terminal_incomplete),
        },
        "unmeasurable_buildings": [
            {
                "building_id": row["building_id"],
                "status": row["status"],
                "failure_reason": row["failure_reason"],
            }
            for row in unmeasurable
        ],
        "incomplete_buildings": [
            {
                "building_id": row["building_id"],
                "status": row["status"],
                "failure_reason": row["failure_reason"],
            }
            for row in terminal_incomplete
        ],
        "reproduction_check": {
            "building_id": REPRODUCTION_ID,
            "expected": REPRODUCTION_EXPECTED,
            "observed": {
                key: row199[key]
                for key in (
                    "selected_dlt_point_count",
                    "footprint_inside_point_count",
                    "inside_z_median_m",
                )
            },
            "passed": True,
            "cache_reused": True,
            "source": rel(R1P_MEASUREMENTS),
        },
        "environment_lock": prep_manifest["environment_lock"],
        "inference_manifest": inference_manifest,
        "pair_selection": prep_manifest["pair_selection"],
        "new_mast3r_inference_runs_this_census": sum(
            as_int(row.get("new_mast3r_inference_runs")) or 0
            for row in measurements
        ),
        "cache_reuse_runs_this_census": sum(
            as_int(row.get("cache_reuse_runs")) or 0
            for row in measurements
        ),
        "learning_runs_started": 0,
        "new_inference_allowlist": [ALLOWLIST],
        "reference_lod2_role": "projection and classification only",
        "source_sha256": output_hashes(run_sources),
        "output_sha256": output_hashes((MEASUREMENTS,)),
        "interpretation_or_verdict": None,
    }
    atomic_json(RUN_MANIFEST, run_manifest)

    DOC_MEASUREMENTS.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(MEASUREMENTS, DOC_MEASUREMENTS)
    atomic_csv(LADDER, ladder, LADDER_FIELDS)
    atomic_csv(TARGETS, targets, TARGET_FIELDS)
    atomic_csv(LOWCOUNT, lowcount, AMBIGUOUS_FIELDS)
    atomic_csv(HIGHMAD, highmad, AMBIGUOUS_FIELDS)
    make_map(ladder)
    atomic_text(
        SUMMARY,
        summary_markdown(
            ladder,
            measurements,
            lowcount,
            highmad,
            status,
        ),
    )

    cell_counts = Counter(row["cell_label"] for row in ladder)
    small_counts = Counter(
        row["cell_label"]
        for row in ladder
        if as_bool(row["small_lt50"])
    )
    cell2 = [row for row in ladder if row["cell_label"] == CELL_2]
    cell2_roofs = Counter(
        row["ref_roof_slope_group"] for row in cell2
    )
    failed = [
        row for row in ladder if not as_bool(row["dense_assembled"])
    ]
    measured_failed = [
        row for row in failed if row["anchor_status"] == "measured"
    ]
    distribution = {
        "zero": sum(
            (as_int(row["anchor_footprint_inside_point_count"]) or 0)
            == 0
            for row in measured_failed
        ),
        "one_to_99": len(lowcount),
        "hundred_or_more": sum(
            (as_int(row["anchor_footprint_inside_point_count"]) or 0)
            >= 100
            for row in measured_failed
        ),
        "unmeasurable": sum(
            row["anchor_status"] == "unmeasurable" for row in failed
        ),
        "incomplete_budget": sum(
            row["anchor_status"] == "incomplete_budget" for row in failed
        ),
    }
    public_sources = run_sources + (MEASUREMENTS, RUN_MANIFEST)
    public_outputs = (
        DOC_MEASUREMENTS,
        LADDER,
        TARGETS,
        LOWCOUNT,
        HIGHMAD,
        FIGURE,
        SUMMARY,
    )
    public_manifest = {
        "schema": "jointbuildgs.boundary_map_v4.v1",
        "created_utc": now(),
        "status": status,
        "git_head_at_finalize": git_value("rev-parse", "HEAD"),
        "branch": git_value("branch", "--show-current"),
        "population": {
            "canonical_count": 178,
            "dense_assembled_count": 114,
            "dense_failure_count": 64,
            "small_lt50_count": sum(
                as_bool(row["small_lt50"]) for row in ladder
            ),
            "nonsmall_count": sum(
                not as_bool(row["small_lt50"]) for row in ladder
            ),
        },
        "cell_labels": list(CELLS),
        "assignment_rule": {
            CELL_1: "dense_assembled=true",
            CELL_2: (
                "dense failure and measured footprint-inside count>=1"
            ),
            CELL_3: (
                "dense failure and no measured anchor assignment and "
                "outline_observable=true"
            ),
            CELL_4: (
                "dense failure and no measured anchor assignment and "
                "outline_observable=false"
            ),
            "unmeasurable": (
                "anchor_status=unmeasurable; assign cell_3 or cell_4 only "
                "from outline_observable; add 앵커 미판정 sticker"
            ),
            "incomplete_budget": (
                "assign cell_3 or cell_4 only from outline_observable; "
                "add 앵커 미완 sticker"
            ),
            "anchor_count_threshold": ANCHOR_COUNT_THRESHOLD,
            "anchor_mad_threshold": "not preregistered; recorded only",
            "outline_observable": (
                "representative_view_count>=2 and "
                "outline_inframe_frac_max>0 and "
                "outline_valid_pixel_count_max>=3"
            ),
            "texture_signal": "descriptive only; not an assignment input",
        },
        "legacy_v1_2_label_reference": LEGACY_LABEL,
        "cell_counts": {
            cell: {
                "all": cell_counts[cell],
                "small_lt50": small_counts[cell],
                "nonsmall": cell_counts[cell] - small_counts[cell],
            }
            for cell in CELLS
        },
        "cell_2_buildings": [
            {
                "building_id": row["building_id"],
                "inside_count": as_int(
                    row["anchor_footprint_inside_point_count"]
                ),
                "inside_z_mad_m": as_float(
                    row["anchor_inside_z_mad_m"]
                ),
                "ref_roof_type": row["ref_roof_type"],
                "ref_roof_slope_group": row[
                    "ref_roof_slope_group"
                ],
                "small_lt50": as_bool(row["small_lt50"]),
            }
            for row in cell2
        ],
        "cell_2_ref_roof_slope_counts": dict(cell2_roofs),
        "ambiguous_lowcount_1_99": [
            {
                "building_id": row["building_id"],
                "inside_count": as_int(
                    row["anchor_footprint_inside_point_count"]
                ),
                "inside_z_mad_m": as_float(
                    row["anchor_inside_z_mad_m"]
                ),
            }
            for row in lowcount
        ],
        "ambiguous_precedent": (
            "8568392=6 points; 2026-07-15 review recorded n<20 "
            "material insufficient"
        ),
        "high_count_high_mad": [
            {
                "building_id": row["building_id"],
                "inside_count": as_int(
                    row["anchor_footprint_inside_point_count"]
                ),
                "inside_z_mad_m": as_float(
                    row["anchor_inside_z_mad_m"]
                ),
            }
            for row in highmad
        ],
        "inside_count_distribution": distribution,
        "override_records": {
            row["building_id"]: {
                "inside_count": as_int(
                    row["anchor_footprint_inside_point_count"]
                ),
                "inside_z_mad_m": as_float(
                    row["anchor_inside_z_mad_m"]
                ),
                "cell_label": row["cell_label"],
                "source": row["override_source"],
                "effect_on_cell": row["override_effect_on_cell"],
            }
            for row in ladder
            if as_bool(row["override_recorded"])
        },
        "census_measurement_manifest": rel(RUN_MANIFEST),
        "census_measurement_manifest_sha256": sha256_file(RUN_MANIFEST),
        "source_sha256": output_hashes(public_sources),
        "output_sha256": output_hashes(public_outputs),
        "learning_runs_started": 0,
        "new_inference_allowlist": [ALLOWLIST],
        "reference_lod2_role": "projection and classification only",
        "interpretation_or_verdict": None,
    }
    atomic_json(PUBLIC_MANIFEST, public_manifest)


def verify_hashes(payload: Mapping[str, Any], label: str) -> None:
    for section in ("source_sha256", "output_sha256"):
        for relative, expected in payload.get(section, {}).items():
            path = Path(relative)
            if not path.is_absolute():
                path = REPO / path
            if not path.is_file():
                raise RuntimeError(
                    f"{label} {section} path missing: {relative}"
                )
            actual = sha256_file(path)
            if actual != expected:
                raise RuntimeError(
                    f"{label} {section} hash drift: {relative}"
                )


def qa() -> None:
    required = (
        JOBS,
        PREP_MANIFEST,
        INFERENCE_MEASUREMENTS,
        INFERENCE_PAIRS,
        INFERENCE_PROGRESS,
        INFERENCE_MANIFEST,
        MEASUREMENTS,
        RUN_MANIFEST,
        DOC_MEASUREMENTS,
        LADDER,
        TARGETS,
        LOWCOUNT,
        HIGHMAD,
        PUBLIC_MANIFEST,
        SUMMARY,
        FIGURE,
    )
    missing = [rel(path) for path in required if not path.is_file()]
    if missing:
        raise RuntimeError(f"missing QA outputs: {missing}")
    population = population_inventory()
    prep = json.loads(PREP_MANIFEST.read_text(encoding="utf-8"))
    run = json.loads(RUN_MANIFEST.read_text(encoding="utf-8"))
    public = json.loads(PUBLIC_MANIFEST.read_text(encoding="utf-8"))
    jobs = json.loads(JOBS.read_text(encoding="utf-8"))
    measurements = read_csv(MEASUREMENTS)
    doc_measurements = read_csv(DOC_MEASUREMENTS)
    ladder = read_csv(LADDER)
    targets = read_csv(TARGETS)
    lowcount = read_csv(LOWCOUNT)
    highmad = read_csv(HIGHMAD)

    if prep["set_validation"]["derived_equals_fixed"] is not True:
        raise RuntimeError("prepare set equality is not true")
    job_ids = [job["building_id"] for job in jobs["jobs"]]
    if job_ids != list(FIXED_IDS):
        raise RuntimeError("job priority order differs from fixed order")
    if any(len(job["pairs"]) != MAX_PAIRS for job in jobs["jobs"]):
        raise RuntimeError("not every census job has ten pairs")
    measurement_ids = [row["building_id"] for row in measurements]
    if measurement_ids != list(FIXED_IDS) + [REPRODUCTION_ID]:
        raise RuntimeError("measurement 59-row priority order drift")
    if measurements != doc_measurements:
        raise RuntimeError("run and docs measurement copies differ")
    if any(row["learning_runs_started"] != "0" for row in measurements):
        raise RuntimeError("measurement learning_runs_started drift")
    if any(
        row["new_inference_allowlist"] != ALLOWLIST
        for row in measurements
    ):
        raise RuntimeError("measurement inference allowlist drift")
    row199 = measurements[-1]
    if (
        as_int(row199["selected_dlt_point_count"]) != 538
        or as_int(row199["footprint_inside_point_count"]) != 373
        or abs((as_float(row199["inside_z_median_m"]) or 0.0)
               - (-34.347425)) > 5e-7
        or row199["inference_execution_this_census"] != "cache_reuse"
    ):
        raise RuntimeError("4907199 reproduction row drift")

    if len(ladder) != 178 or len({row["building_id"] for row in ladder}) != 178:
        raise RuntimeError("v4 ladder is not 178 unique")
    if {row["building_id"] for row in ladder} != population["canonical"]:
        raise RuntimeError("v4 ladder population differs from canonical 178")
    if any(row["learning_runs_started"] != "0" for row in ladder):
        raise RuntimeError("ladder learning_runs_started drift")
    if sum(row["cell_label"] == CELL_1 for row in ladder) != 114:
        raise RuntimeError("cell_1 count differs from dense success 114")
    for row in ladder:
        dense = as_bool(row["dense_assembled"])
        status = row["anchor_status"]
        inside = as_int(row["anchor_footprint_inside_point_count"])
        observable = as_bool(row["outline_observable"])
        if dense:
            expected = CELL_1
        elif status == "measured" and (inside or 0) >= 1:
            expected = CELL_2
        elif observable:
            expected = CELL_3
        else:
            expected = CELL_4
        if row["cell_label"] != expected:
            raise RuntimeError(
                f"{row['building_id']} mechanical cell drift"
            )
        if status == "unmeasurable" and (
            row["anchor_undecided_sticker"] != "앵커 미판정"
            or row["cell_label"] not in {CELL_3, CELL_4}
        ):
            raise RuntimeError(
                f"{row['building_id']} unmeasurable handling drift"
            )
    expected_targets = {
        row["building_id"]
        for row in ladder
        if row["cell_label"] in {CELL_2, CELL_3}
    }
    if {row["building_id"] for row in targets} != expected_targets:
        raise RuntimeError("v4 target set differs from cell_2 union cell_3")
    if any(
        not (
            1
            <= (as_int(row["anchor_footprint_inside_point_count"]) or 0)
            <= 99
        )
        for row in lowcount
    ):
        raise RuntimeError("lowcount table predicate drift")
    if not any(
        row["building_id"] == "DEBY_LOD2_8568392"
        and as_int(row["anchor_footprint_inside_point_count"]) == 6
        for row in lowcount
    ):
        raise RuntimeError("8568392 lowcount precedent missing")
    if any(
        not (
            (as_int(row["anchor_footprint_inside_point_count"]) or 0)
            >= 100
            and (as_float(row["anchor_inside_z_mad_m"]) or 0.0) > 0.5
        )
        for row in highmad
    ):
        raise RuntimeError("high-count/high-MAD table predicate drift")
    if public["population"]["dense_assembled_count"] != 114:
        raise RuntimeError("public manifest dense count drift")
    if run["learning_runs_started"] != 0 or public[
        "learning_runs_started"
    ] != 0:
        raise RuntimeError("manifest learning-zero drift")
    verify_hashes(run, "anchor census")
    verify_hashes(public, "boundary map v4")
    if sha256_file(MEASUREMENTS) != sha256_file(DOC_MEASUREMENTS):
        raise RuntimeError("measurement-copy payload hash drift")
    print(
        json.dumps(
            {
                "status": public["status"],
                "measurements": len(measurements),
                "ladder": len(ladder),
                "targets": len(targets),
                "cell_counts": public["cell_counts"],
                "lowcount": len(lowcount),
                "highmad": len(highmad),
                "learning_runs_started": 0,
                "new_inference_allowlist": [ALLOWLIST],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("prepare", "finalize", "qa"))
    args = parser.parse_args()
    if args.command == "prepare":
        prepare()
    elif args.command == "finalize":
        finalize()
    else:
        qa()


if __name__ == "__main__":
    main()
