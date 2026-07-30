#!/usr/bin/env python3
"""P1W-SCORE: locked expanded-30 Roofer read-out and numeric scoring adapter.

The adapter is intentionally split at the reconstruction/scoring boundary:

* p0-tools prepares immutable Roofer argv without Docker access, a separate
  host executor runs the pinned image, and p0-tools finalizes raw CityJSONSeq;
* LoD2 reference geometry is opened only by the scoring path;
* the metric implementations are imported from ``e5_c001_8way.py`` and
  ``qs_baseline178_rescore.py`` instead of being redefined here;
* empty output files still carry fixed headers, population denominators and
  provenance locks before any learning result exists.

No training is performed by this module.  Its CSV/JSON outputs contain numeric
measurements and machine-readable rule fields only; human interpretation stays
outside the adapter.
"""
from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import importlib
import importlib.util
import json
import math
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

import numpy as np
try:  # p0-tools intentionally stays small; JSON configs need no YAML module.
    import yaml  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - exercised in the pinned tools image
    yaml = None


REPO = Path(__file__).resolve().parents[3]
SCRIPT_DIR = Path(__file__).resolve().parent
P2_SHARED_SCRIPT_DIR = REPO / "phases/p2-gsjso/scripts"
for import_path in (P2_SHARED_SCRIPT_DIR, SCRIPT_DIR):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from pilot_1wave_readout_lineage import (  # noqa: E402
    LINEAGE_SCHEMA as READOUT_LINEAGE_SCHEMA,
    validate_classification_receipt,
    validate_roofprint_file,
)

TASK_ID = "P1W-SCORE"
RUN_ID = "20260721_pilot_1wave"
SCHEMA_VERSION = "jointbuildgs.pilot_1wave.scoring.v1"
CRS = "EPSG:25832"
RUN_DIR = REPO / "phases/p2-gsjso/runs" / RUN_ID
PILOT_SET = RUN_DIR / "pilot_1wave_pilot_set.csv"
PILOT_MANIFEST = RUN_DIR / "pilot_1wave_pilot_set_manifest.json"
FOOTPRINT_SOURCE = REPO / "results/tum_transfer/analysis/footprints_aoi.geojson"
BASELINE_SCORES = REPO / "docs/experiments/evaluation/qs_baseline178/tables/qs_baseline178_scores.csv"
CHEAP_REFINE_SCORES = REPO / "docs/experiments/evaluation/qs_cheap_refine_sweep/tables/qs_cheap_refine_sweep.csv"
OBSERVATION_STRATA_SOURCE = REPO / "docs/regression_input_snapshot.csv"
LOD2_DIR = REPO / "phases/p0-audit/data/raw/lod2"
W2_SCRIPT = REPO / "phases/p0-audit/scripts/08_roofer_w2.py"
METRIC_SCRIPT = P2_SHARED_SCRIPT_DIR / "e5_c001_8way.py"
BASELINE_SCRIPT = P2_SHARED_SCRIPT_DIR / "qs_baseline178_rescore.py"

PILOT_SET_SHA256 = "db5ecb6c838499dd3a5f96a4b1abae85414c3d38318d976b7ee598982b566ffc"
PILOT_MANIFEST_SHA256 = "803d18862db926fff353c641e08a03c5938cedf3fb49cc4859751189e83855e2"
SELECTION_SHA256 = "e98daa670a0753198e8a54502b260a07bcefe2bca42976931c0a08b766c5b3cd"
ORDERED_IDS_SHA256 = "ae5cbc664941c3b8bb4238767f1d0833a1f7684928a03837047065f85093bb01"
FOOTPRINT_SOURCE_SHA256 = "ca7f5b13a52368e1d2ac47b77cc78f12887bad4d598d122ad57b882eb4920a82"
BASELINE_SCORES_SHA256 = "a3b89f1907e6e61aead702efe6b742b5c012615df77d90bdb2a859b5418d85ab"
CHEAP_REFINE_SCORES_SHA256 = "fb3fa5c82edca975018f6c08982e48e85ea7ccba623cce97166fc0c0ffb89fd8"
OBSERVATION_STRATA_SOURCE_SHA256 = "3cabed76b37625fdf8f9a72ed5c5b1f7c90ba23a839d6f1a61fc3727870cee82"
METRIC_SCRIPT_SHA256 = "12322a7fd49c0904eaf7160946c7ef3b521ed091038452f9a863bef37f0bcbdc"
BASELINE_SCRIPT_SHA256 = "0d752dade0b8677460b55d381a69db77f7bf611061fb7479710434358db33e9d"
W2_SCRIPT_SHA256 = "ae655090915c56bfeee2be830a28e27520c2430e97d19e515a0aa046e4c79e97"
SCORING_BBOX = (
    690722.296661349,
    5335966.948661349,
    690911.966338651,
    5336172.663338651,
)
DENSE_BAR_MEDIAN_M = 0.640884566
EXPECTED_POPULATION = 30
EXPECTED_SEEDS = (1001, 1002)
HONEST_CONDITIONS = ("01", "02", "03", "04a")
UPPERBOUND_CONDITION = "04b"
ALL_CONDITIONS = (*HONEST_CONDITIONS, UPPERBOUND_CONDITION)
CONDITION_ROLE = {
    "01": "honest",
    "02": "honest",
    "03": "honest",
    "04a": "honest",
    "04b": "seg_upperbound",
}
CONDITION_PILOT_ARM = {
    "01": "01_surface",
    "02": "02_photo_control",
    "03": "03_plane_soft",
    "04a": "04a_plane_medium_vision",
    "04b": "04b_plane_medium_gt_upperbound",
}
CONDITION_SEGMENTATION_SOURCE = {
    "01": "none",
    "02": "none",
    "03": "none_segmentation_free_geometry",
    "04a": "vision_groundedsam_roof",
    "04b": "lod2_roofsurface_gt_upperbound",
}
COMPLETENESS_THRESHOLDS = (0.8, 0.9, 0.95)
RMS_SPEC_THRESHOLDS_M = (0.3, 1.0)
MAX_ITER = 20_000
FULL_CHECKPOINT_STEPS = (5_000, 10_000, 15_000, 20_000)
FULL_STATE_MANIFEST_SCHEMA = "jointbuildgs.stage2.resume_manifest.v1"
ROOFER_PREPARE_SCHEMA = "jointbuildgs.pilot_1wave.roofer_prepare.v1"
ROOFER_ARGV_SCHEMA = "jointbuildgs.pilot_1wave.roofer_argv.v1"
ROOFER_EXECUTION_SCHEMA = "jointbuildgs.pilot_1wave.roofer_execution.v1"
ROOFER_MARKER_SCHEMA = "jointbuildgs.pilot_1wave.roofer_invocation.v2"
SCORE_MARKER_SCHEMA = "jointbuildgs.pilot_1wave.score_invocation.v1"
GUARD_STATUSES = (
    "not_triggered",
    "triggered_checkpoint_stop",
    "triggered_emergency_previous_checkpoint",
)
P0_TOOLS_IMAGE = "jointbuildgs-p0-tools:t0"
P0_TOOLS_IMAGE_ID = (
    "sha256:87bea02e5598a3d53a119b754191673497d52641bd8ea4106ffee653407579b0"
)
P0_TOOLS_SENTINEL_ENV = "P1W_INSIDE_P0_TOOLS"
P0_TOOLS_IMAGE_ID_ENV = "P1W_P0_TOOLS_IMAGE_ID"
DOCKER_SENTINEL = Path("/.dockerenv")
CHEAP_REFINE_CONDITION = "cell050_win2_pass1"

_metric_module: Any | None = None
_baseline_module: Any | None = None

ROOFER_IMAGE = (
    "3dgi/roofer@sha256:"
    "dd2c415aaee337502bde0dc1426dfa9c9f88e648f9d2f6340110c49932c251d2"
)
ROOFER_IMAGE_ID = (
    "sha256:9c980b97fba4c3fd30f5bb4afb8f2621be211d4e72e4333ea2053e8cd69b2dba"
)
ROOFER_ENTRYPOINT = ("roofer",)
ROOFER_CONTAINER_REPO = Path("/workspace/JointBuildGS")
ROOFER_CONTAINER_NAME_PREFIX = "jointbuildgs-p1w-20260722"
ROOFER_PARAMETER_ARGV = (
    "--id-attribute",
    "building_id",
    "--jobs",
    "3",
    "--srs",
    "EPSG:25832",
    "--bld-class",
    "6",
    "--grnd-class",
    "2",
    "--lod22",
)
ROOFER_PARAMETERS = " ".join(ROOFER_PARAMETER_ARGV)
VAL3DITY_VERSION = "2.6.0"
LOCKED_LOD2_SHA256 = {
    "690_5334.gml": "61d29e4617bfa961e811003b7af2bb2c826b3fab90f11731f5d22b8e4689e314",
    "690_5336.gml": "494282ee7be660401820af8efa4e2667fcaeb4d7ac8466b23be67e3347701674",
}

OUTPUT_NAMES = {
    "scores": "pilot_1wave_scores.csv",
    "summary": "pilot_1wave_summary.csv",
    "seg_gap": "pilot_1wave_seg_upperbound_gap.csv",
    "loss_shares": "pilot_1wave_loss_shares.csv",
    "winner": "pilot_1wave_winner.csv",
    "manifest": "pilot_1wave_manifest.json",
}

SCORE_FIELDS = (
    "schema_version",
    "row_type",
    "source_id",
    "source_role",
    "condition_id",
    "seed",
    "building_id",
    "selection_rank",
    "is_core10",
    "is_small_lt50m2",
    "observation_stratum",
    "size_area_stratum",
    "metric_available",
    "provenance_validated",
    "full_state_manifest_path",
    "full_state_manifest_sha256",
    "training_config_path",
    "training_config_sha256",
    "pilot_arm",
    "segmentation_source",
    "max_iter",
    "last_completed_steps",
    "process_completed_steps",
    "process_completed",
    "learning_runs_started",
    "latest_full_checkpoint_path",
    "latest_full_checkpoint_sha256",
    "latest_full_checkpoint_steps",
    "eligible_20k_full_state",
    "partial",
    "guard_status",
    "guard_reason",
    "input_kind",
    "input_path",
    "input_sha256",
    "cityjson_path",
    "cityjson_sha256",
    "roofer_invocation_count",
    "roofer_marker_path",
    "roofer_marker_sha256",
    "roofer_image",
    "roofer_parameters",
    "score_marker_path",
    "score_invocation_count",
    "val3dity_report",
    "val3dity_report_sha256",
    "val3dity_version",
    "val3dity_version_output",
    "val3dity_exit_code",
    "rf_success",
    "rf_pointcloud_unusable",
    "rf_extrusion_mode",
    "lod1_fallback",
    "geometry_has_lod22",
    "has_lod22",
    "val3dity_valid",
    "roof_face_count_model",
    "roof_face_count_ref",
    "face_count_ratio",
    "face_count_ratio_abs_error",
    "roof_rms_m",
    "rms_le_0p3",
    "rms_le_1p0",
    "roof_hausdorff_m",
    "roof_distance_samples",
    "roof_completeness",
    "completeness_ge_0p8",
    "completeness_ge_0p9",
    "completeness_ge_0p95",
    "dense_has_lod22",
    "dense_val3dity_valid",
    "dense_face_count_ratio",
    "dense_face_count_ratio_abs_error",
    "dense_roof_rms_m",
    "dense_roof_hausdorff_m",
    "dense_roof_completeness",
    "delta_has_lod22",
    "delta_val3dity_valid",
    "delta_face_count_ratio_abs_error",
    "delta_roof_rms_m",
    "delta_roof_hausdorff_m",
    "delta_roof_completeness",
    "rms_lt_dense",
    "als_roof_rms_m",
    "rms_gap_to_als_m",
    "als_gap_closed_fraction",
    "crs",
    "score_time_z_shift_m",
    "reference_role",
)

SUMMARY_FIELDS = (
    "schema_version",
    "row_type",
    "source_id",
    "source_role",
    "condition_id",
    "seed",
    "stratum",
    "population_count",
    "metric_available_count",
    "rms_measurable_count",
    "roof_rms_median_m",
    "roof_rms_max_m",
    "rms_le_0p3_count",
    "rms_le_0p3_rate",
    "rms_le_1p0_count",
    "rms_le_1p0_rate",
    "als_approach_measurable_count",
    "als_gap_closed_fraction_median",
    "rms_gap_to_als_m_median",
    "hausdorff_measurable_count",
    "roof_hausdorff_median_m",
    "roof_hausdorff_max_m",
    "face_count_ratio_measurable_count",
    "face_count_ratio_median",
    "face_count_ratio_target_abs_deviation",
    "completeness_measurable_count",
    "roof_completeness_min",
    "roof_completeness_median",
    "completeness_ge_0p8_count",
    "completeness_ge_0p8_rate",
    "completeness_ge_0p9_count",
    "completeness_ge_0p9_rate",
    "completeness_ge_0p95_count",
    "completeness_ge_0p95_rate",
    "val3dity_valid_count",
    "val3dity_valid_rate",
    "lod2_count",
    "lod2_rate",
    "rms_lt_dense_measurable_count",
    "rms_lt_dense_count",
    "rms_lt_dense_rate",
    "dense_bar_median_m",
    "run_provenance_validated",
    "run_eligible_20k_full_state",
    "run_partial",
    "run_guard_status",
    "run_last_completed_steps",
    "run_process_completed_steps",
    "rule_a_rms_below_dense_bar",
    "rule_b_structural_improvement",
    "rule_c_all_metrics_nonworse",
    "rule_d_completeness_floor_0p9",
    "rule_d_completeness_floor_0p8_sensitivity",
    "rule_d_completeness_floor_0p95_sensitivity",
    "rule_abcd",
)

SEG_GAP_FIELDS = (
    "schema_version",
    "row_type",
    "seed",
    "stratum",
    "building_id",
    "pair_state",
    "vision_run_state",
    "gt_run_state",
    "vision_partial",
    "gt_partial",
    "vision_metric_available",
    "gt_metric_available",
    "vision_roof_rms_m",
    "gt_roof_rms_m",
    "delta_gt_minus_vision_roof_rms_m",
    "vision_roof_hausdorff_m",
    "gt_roof_hausdorff_m",
    "delta_gt_minus_vision_roof_hausdorff_m",
    "vision_face_count_ratio_abs_error",
    "gt_face_count_ratio_abs_error",
    "delta_gt_minus_vision_face_count_ratio_abs_error",
    "vision_roof_completeness",
    "gt_roof_completeness",
    "delta_gt_minus_vision_roof_completeness",
    "vision_val3dity_valid",
    "gt_val3dity_valid",
    "delta_gt_minus_vision_val3dity_valid",
    "vision_has_lod22",
    "gt_has_lod22",
    "delta_gt_minus_vision_has_lod22",
)

LOSS_SHARE_FIELDS = (
    "schema_version",
    "condition_id",
    "seed",
    "checkpoint_step",
    "checkpoint_sha256",
    "iter",
    "term",
    "raw",
    "weighted",
    "share",
    "roof_share",
)

WINNER_FIELDS = (
    "schema_version",
    "row_type",
    "condition_id",
    "honest_candidate",
    "expected_seed_count",
    "complete_seed_count",
    "eligible_20k_seed_count",
    "rule_abcd_seed_count",
    "seed_1001_rule_abcd",
    "seed_1002_rule_abcd",
    "seed_1001_roof_rms_median_m",
    "seed_1002_roof_rms_median_m",
    "worst_seed_roof_rms_median_m",
    "eligible_two_seed_rule",
    "minimum_worst_rms_order",
    "co_minimum_count",
    "is_minimum_worst_rms",
)


@dataclass(frozen=True)
class PilotBuilding:
    building_id: str
    selection_rank: int
    is_core10: bool
    is_small_lt50m2: bool
    footprint_area_m2: float
    observation_stratum: str
    size_area_stratum: str


@dataclass(frozen=True)
class PilotLock:
    buildings: tuple[PilotBuilding, ...]
    scoring_bbox: tuple[float, float, float, float]
    selection_sha256: str
    ordered_ids_sha256: str
    dense_bar_median_m: float
    pilot_set_sha256: str
    pilot_manifest_sha256: str

    @property
    def ids(self) -> tuple[str, ...]:
        return tuple(item.building_id for item in self.buildings)

    @property
    def by_id(self) -> dict[str, PilotBuilding]:
        return {item.building_id: item for item in self.buildings}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_metric_module() -> Any:
    """Load the heavy geometry stack only for LAS/CityJSON metric commands."""

    global _metric_module
    if _metric_module is None:
        try:
            _metric_module = importlib.import_module("e5_c001_8way")
        except Exception:
            sys.modules.pop("e5_c001_8way", None)
            raise
    return _metric_module


def get_baseline_module() -> Any:
    """Load completeness helpers lazily so host-side assembly needs no laspy."""

    global _baseline_module
    if _baseline_module is None:
        try:
            _baseline_module = importlib.import_module("qs_baseline178_rescore")
        except Exception:
            sys.modules.pop("qs_baseline178_rescore", None)
            raise
    return _baseline_module


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


def canonical_json_sha256(payload: Any) -> str:
    data = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def bool_value(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def number(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"none", "nan", "na"}:
        return None
    try:
        result = float(text)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def format_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (float, np.floating)):
        return "" if not math.isfinite(float(value)) else f"{float(value):.9f}"
    return value


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    with temporary.open("rb") as handle:
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def atomic_csv(path: Path, rows: Sequence[Mapping[str, Any]], fields: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(fields),
            extrasaction="raise",
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            unknown = set(row) - set(fields)
            if unknown:
                raise RuntimeError(f"unknown CSV fields for {path.name}: {sorted(unknown)}")
            writer.writerow({field: format_value(row.get(field)) for field in fields})
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def atomic_json(path: Path, payload: Any) -> None:
    atomic_text(path, json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def require_equal(actual: Any, expected: Any, label: str) -> None:
    if actual != expected:
        raise RuntimeError(f"{label} drift: {actual!r} != {expected!r}")


def require_close(actual: float, expected: float, label: str, tolerance: float = 5e-10) -> None:
    if not math.isclose(float(actual), float(expected), rel_tol=0.0, abs_tol=tolerance):
        raise RuntimeError(f"{label} drift: {actual!r} != {expected!r}")


def load_pilot_lock(
    pilot_set: Path = PILOT_SET,
    pilot_manifest: Path = PILOT_MANIFEST,
) -> PilotLock:
    """Load the committed population only after strict whole-file SHA checks."""

    require_equal(sha256_file(METRIC_SCRIPT), METRIC_SCRIPT_SHA256, "distance metric script SHA256")
    require_equal(sha256_file(BASELINE_SCRIPT), BASELINE_SCRIPT_SHA256, "completeness script SHA256")
    require_equal(sha256_file(W2_SCRIPT), W2_SCRIPT_SHA256, "Roofer adapter script SHA256")
    require_equal(sha256_file(pilot_set), PILOT_SET_SHA256, "pilot-set SHA256")
    require_equal(sha256_file(pilot_manifest), PILOT_MANIFEST_SHA256, "pilot manifest SHA256")
    require_equal(
        sha256_file(OBSERVATION_STRATA_SOURCE),
        OBSERVATION_STRATA_SOURCE_SHA256,
        "observation/size strata source SHA256",
    )
    rows = read_csv(pilot_set)
    require_equal(len(rows), EXPECTED_POPULATION, "pilot population count")
    manifest = json.loads(pilot_manifest.read_text(encoding="utf-8"))
    require_equal(manifest.get("schema"), "jointbuildgs.pilot_1wave.pilot_set.v1", "pilot manifest schema")
    selection = manifest.get("selection") or {}
    require_equal(selection.get("selection_sha256"), SELECTION_SHA256, "selection SHA256")
    require_equal(selection.get("ordered_ids_sha256"), ORDERED_IDS_SHA256, "ordered IDs SHA256")
    manifest_bbox = tuple(float(value) for value in selection.get("scoring_selection_bbox", []))
    require_equal(len(manifest_bbox), 4, "scoring bbox coordinate count")
    for index, (actual, expected) in enumerate(zip(manifest_bbox, SCORING_BBOX, strict=True)):
        require_close(actual, expected, f"scoring bbox[{index}]")

    strata_by_id: dict[str, tuple[str, str]] = {}
    for source in read_csv(OBSERVATION_STRATA_SOURCE):
        building_id = str(source.get("building_id", ""))
        if source.get("arm") != "raw_dense" or building_id not in {
            str(row.get("building_id", "")) for row in rows
        }:
            continue
        if building_id in strata_by_id:
            raise RuntimeError(f"duplicate raw_dense strata row: {building_id}")
        observation = str(source.get("stratum_observation_recon_score", ""))
        size_area = str(source.get("stratum_size_area", ""))
        if observation not in {"low", "mid", "high"} or size_area not in {"low", "mid", "high"}:
            raise RuntimeError(f"invalid observation/size stratum: {building_id}")
        strata_by_id[building_id] = (observation, size_area)

    buildings: list[PilotBuilding] = []
    seen: set[str] = set()
    for expected_rank, row in enumerate(rows, 1):
        building_id = str(row.get("building_id", ""))
        if not building_id or building_id in seen:
            raise RuntimeError(f"pilot building ID cardinality drift: {building_id!r}")
        seen.add(building_id)
        require_equal(int(row["selection_rank"]), expected_rank, f"selection rank {building_id}")
        require_equal(row.get("selection_sha256"), SELECTION_SHA256, f"row selection SHA {building_id}")
        require_equal(row.get("crs"), CRS, f"row CRS {building_id}")
        row_bbox = tuple(
            float(row[field])
            for field in (
                "scoring_aoi_minx",
                "scoring_aoi_miny",
                "scoring_aoi_maxx",
                "scoring_aoi_maxy",
            )
        )
        for index, (actual, expected) in enumerate(zip(row_bbox, SCORING_BBOX, strict=True)):
            require_close(actual, expected, f"row scoring bbox {building_id}[{index}]")
        require_close(float(row["dense_bar_median_m"]), DENSE_BAR_MEDIAN_M, "dense bar")
        if building_id not in strata_by_id:
            raise RuntimeError(f"missing raw_dense observation/size strata: {building_id}")
        observation_stratum, size_area_stratum = strata_by_id[building_id]
        buildings.append(
            PilotBuilding(
                building_id=building_id,
                selection_rank=expected_rank,
                is_core10=bool_value(row["is_core10"]),
                is_small_lt50m2=bool_value(row["is_small_lt50m2"]),
                footprint_area_m2=float(row["footprint_area_m2"]),
                observation_stratum=observation_stratum,
                size_area_stratum=size_area_stratum,
            )
        )

    ordered_ids = [item.building_id for item in buildings]
    require_equal(ordered_ids, selection.get("selected_ids_in_rank_order"), "ordered pilot IDs")
    ordered_payload_sha = hashlib.sha256(("\n".join(ordered_ids) + "\n").encode("utf-8")).hexdigest()
    require_equal(ordered_payload_sha, ORDERED_IDS_SHA256, "ordered ID payload SHA256")
    require_equal(sum(item.is_core10 for item in buildings), 10, "core10 count")
    require_equal(sum(item.is_small_lt50m2 for item in buildings), 5, "small-building count")
    require_equal(
        {name: sum(item.observation_stratum == name for item in buildings) for name in ("low", "mid", "high")},
        {"low": 8, "mid": 10, "high": 12},
        "observation strata counts",
    )
    require_equal(
        {name: sum(item.size_area_stratum == name for item in buildings) for name in ("low", "mid", "high")},
        {"low": 8, "mid": 12, "high": 10},
        "size-area strata counts",
    )
    return PilotLock(
        buildings=tuple(buildings),
        scoring_bbox=SCORING_BBOX,
        selection_sha256=SELECTION_SHA256,
        ordered_ids_sha256=ORDERED_IDS_SHA256,
        dense_bar_median_m=DENSE_BAR_MEDIAN_M,
        pilot_set_sha256=PILOT_SET_SHA256,
        pilot_manifest_sha256=PILOT_MANIFEST_SHA256,
    )


def validate_condition_seed(condition_id: str, seed: int) -> None:
    if condition_id not in ALL_CONDITIONS:
        raise RuntimeError(f"unknown condition_id: {condition_id}")
    if int(seed) not in EXPECTED_SEEDS:
        raise RuntimeError(f"unknown seed: {seed}")


def _resolve_declared_path(value: Any, *, declaring_file: Path) -> Path:
    """Resolve an artifact path without silently accepting a different file."""

    text = str(value or "").strip()
    if not text:
        raise RuntimeError(f"empty path declared by {declaring_file}")
    declared = Path(text)
    candidates = (
        (declared,) if declared.is_absolute() else (declaring_file.parent / declared, REPO / declared)
    )
    existing = [candidate.resolve() for candidate in candidates if candidate.exists()]
    if not existing:
        raise FileNotFoundError(f"declared artifact does not exist: {text} ({declaring_file})")
    unique = {str(candidate) for candidate in existing}
    if len(unique) != 1:
        raise RuntimeError(f"ambiguous declared path: {text} -> {sorted(unique)}")
    return existing[0]


def _load_structured_config(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        if path.suffix.lower() == ".json":
            payload = json.load(handle)
        elif yaml is not None:
            payload = yaml.safe_load(handle)
        else:
            # Only locked top-level provenance keys are needed by this scorer.
            # This fallback is deliberately strict instead of pretending to be
            # a general YAML parser in the compact p0-tools image.
            payload = {}
            wanted = {"max_iter", "pilot_arm", "seed", "plane_region_mask_manifest"}
            for raw_line in handle:
                if not raw_line.strip() or raw_line.lstrip().startswith("#"):
                    continue
                if raw_line[:1].isspace() or ":" not in raw_line:
                    continue
                key, raw_value = raw_line.split(":", 1)
                key = key.strip()
                if key not in wanted:
                    continue
                value = raw_value.split(" #", 1)[0].strip()
                if value.lower() in {"null", "none", "~"}:
                    payload[key] = None
                elif value.lower() in {"true", "false"}:
                    payload[key] = value.lower() == "true"
                else:
                    try:
                        payload[key] = ast.literal_eval(value)
                    except (SyntaxError, ValueError):
                        payload[key] = value
    if not isinstance(payload, dict):
        raise RuntimeError(f"training config must be a mapping: {path}")
    return payload


def validate_full_state_manifest(
    condition_id: str,
    seed: int,
    manifest_path: Path,
    *,
    guard_status: str,
    guard_reason: str = "",
) -> dict[str, Any]:
    """Bind a score run to its immutable 20k/partial full-state lineage."""

    validate_condition_seed(condition_id, seed)
    if guard_status not in GUARD_STATUSES:
        raise RuntimeError(f"guard_status must be one of {GUARD_STATUSES}: {guard_status}")
    if guard_status != "not_triggered" and not str(guard_reason).strip():
        raise RuntimeError("triggered guard requires a nonempty guard_reason")
    manifest_path = manifest_path.resolve()
    if not manifest_path.is_file():
        raise FileNotFoundError(manifest_path)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    require_equal(payload.get("schema"), FULL_STATE_MANIFEST_SCHEMA, "full-state manifest schema")
    require_equal(int(payload.get("max_iter", -1)), MAX_ITER, "full-state max_iter")
    checkpoint_steps = tuple(int(value) for value in payload.get("checkpoint_steps", []))
    missing_steps = sorted(set(FULL_CHECKPOINT_STEPS) - set(checkpoint_steps))
    if missing_steps:
        raise RuntimeError(f"full-state checkpoint schedule missing: {missing_steps}")

    config_path = _resolve_declared_path(payload.get("config_path"), declaring_file=manifest_path)
    config_sha = sha256_file(config_path)
    require_equal(config_sha, payload.get("config_file_sha256"), "training config SHA256")
    config = _load_structured_config(config_path)
    require_equal(int(config.get("max_iter", -1)), MAX_ITER, "training config max_iter")
    require_equal(config.get("pilot_arm"), CONDITION_PILOT_ARM[condition_id], "training config pilot_arm")
    if config.get("seed") is not None:
        require_equal(int(config["seed"]), int(seed), "training config seed")

    segmentation_source = CONDITION_SEGMENTATION_SOURCE[condition_id]
    plane_manifest_record: dict[str, Any] | None = None
    if condition_id in {"04a", "04b"}:
        plane_path = _resolve_declared_path(
            config.get("plane_region_mask_manifest"), declaring_file=config_path
        )
        plane_payload = json.loads(plane_path.read_text(encoding="utf-8"))
        require_equal(plane_payload.get("source"), segmentation_source, "plane segmentation source")
        plane_manifest_record = {
            "path": rel(plane_path),
            "sha256": sha256_file(plane_path),
            "source": segmentation_source,
        }
    elif config.get("plane_region_mask_manifest") not in (None, ""):
        raise RuntimeError(f"condition {condition_id} forbids plane_region_mask_manifest")

    learning_runs_started = int(payload.get("learning_runs_started", 0))
    if learning_runs_started < 1:
        raise RuntimeError("full-state manifest does not prove a learning run started")
    last_steps = int(payload.get("last_completed_steps", 0))
    process_completed = bool(payload.get("process_completed", False))
    process_steps_raw = payload.get("process_completed_steps")
    process_steps = int(process_steps_raw) if process_steps_raw is not None else None
    latest = payload.get("latest_full_checkpoint")
    if not isinstance(latest, dict):
        raise RuntimeError("full-state manifest has no latest_full_checkpoint")
    checkpoint_path = _resolve_declared_path(latest.get("path"), declaring_file=manifest_path)
    checkpoint_sha = sha256_file(checkpoint_path)
    require_equal(checkpoint_sha, latest.get("sha256"), "latest full checkpoint SHA256")
    checkpoint_completed_steps = int(latest.get("completed_steps", -1))
    require_equal(checkpoint_completed_steps, last_steps, "latest checkpoint/last completed steps")
    if checkpoint_completed_steps not in checkpoint_steps:
        raise RuntimeError(
            f"latest checkpoint step {checkpoint_completed_steps} is outside the locked schedule"
        )
    eligible = (
        process_completed
        and process_steps == MAX_ITER
        and last_steps == MAX_ITER
        and checkpoint_completed_steps == MAX_ITER
    )
    return {
        "provenance_validated": True,
        "full_state_manifest_path": rel(manifest_path),
        "full_state_manifest_sha256": sha256_file(manifest_path),
        "training_config_path": rel(config_path),
        "training_config_sha256": config_sha,
        "pilot_arm": config["pilot_arm"],
        "segmentation_source": segmentation_source,
        "plane_region_mask_manifest": plane_manifest_record,
        "max_iter": MAX_ITER,
        "last_completed_steps": last_steps,
        "process_completed_steps": process_steps,
        "process_completed": process_completed,
        "learning_runs_started": learning_runs_started,
        "latest_full_checkpoint_path": rel(checkpoint_path),
        "latest_full_checkpoint_sha256": checkpoint_sha,
        "latest_full_checkpoint_steps": checkpoint_completed_steps,
        "eligible_20k_full_state": eligible,
        "partial": not eligible,
        "guard_status": guard_status,
        "guard_reason": str(guard_reason),
    }


def validate_roofer_marker(
    condition_id: str,
    seed: int,
    marker_path: Path,
    cityjson: Path,
    lock: PilotLock,
) -> dict[str, Any]:
    """Re-open the complete v2 prepare/raw/merge provenance chain."""

    require_p0_tools_runtime()
    validate_condition_seed(condition_id, seed)
    marker_path = marker_path.resolve()
    cityjson = cityjson.resolve()
    if not marker_path.is_file() or not cityjson.is_file():
        raise FileNotFoundError(marker_path if not marker_path.is_file() else cityjson)
    marker = json.loads(marker_path.read_text(encoding="utf-8"))
    if not isinstance(marker, dict):
        raise RuntimeError("Roofer marker root must be an object")
    require_equal(marker.get("schema"), ROOFER_MARKER_SCHEMA, "Roofer marker schema")
    require_equal(marker.get("condition_id"), condition_id, "Roofer marker condition")
    require_equal(int(marker.get("seed", -1)), int(seed), "Roofer marker seed")
    require_equal(marker.get("state"), "complete", "Roofer marker state")
    require_equal(int(marker.get("roofer_invocation_count", 0)), 1, "Roofer invocation count")

    prepare_record = marker.get("prepare_receipt")
    if not isinstance(prepare_record, Mapping):
        raise RuntimeError("Roofer v2 marker lacks prepare receipt binding")
    prepare_path = _resolve_declared_path(
        prepare_record.get("path"), declaring_file=marker_path
    )
    require_equal(
        sha256_file(prepare_path),
        prepare_record.get("sha256"),
        "Roofer prepare receipt SHA256",
    )
    prepared = validate_roofer_prepare_receipt(
        prepare_path,
        lock,
        expected_condition=condition_id,
        expected_seed=seed,
    )
    require_equal(prepared["outputs"]["marker_path"], marker_path, "prepare marker path")
    require_equal(prepared["outputs"]["merged_cityjson_path"], cityjson, "prepare CityJSON path")

    execution_record = marker.get("execution_receipt")
    if not isinstance(execution_record, Mapping):
        raise RuntimeError("Roofer v2 marker lacks execution receipt binding")
    execution_path = _resolve_declared_path(
        execution_record.get("path"), declaring_file=marker_path
    )
    require_equal(
        sha256_file(execution_path),
        execution_record.get("sha256"),
        "Roofer execution receipt SHA256",
    )
    executed = validate_roofer_execution_receipt(
        execution_path,
        prepared,
        expected_condition=condition_id,
        expected_seed=seed,
    )
    normalized_execution_record = {
        "path": rel(executed["path"]),
        "sha256": executed["sha256"],
    }
    require_equal(
        dict(execution_record),
        normalized_execution_record,
        "Roofer execution receipt record",
    )
    require_equal(
        marker.get("roofer_execution"),
        executed["normalized"],
        "Roofer normalized execution facts",
    )

    for field, expected in (
        ("runtime_contract", prepared["runtime_contract"]),
        ("roofer_image", ROOFER_IMAGE),
        ("roofer_parameters", ROOFER_PARAMETERS),
        ("selection_sha256", lock.selection_sha256),
        ("ordered_ids_sha256", lock.ordered_ids_sha256),
        ("ordered_building_ids", list(lock.ids)),
        ("roofer_argv", prepared["roofer_argv"]),
        ("pointcloud", prepared["pointcloud"]),
        ("classification_receipt", prepared["classification_receipt"]),
        ("readout_lineage", prepared["readout_lineage"]),
        ("crop_contract", prepared["crop_contract"]),
        ("footprints", prepared["footprints"]),
    ):
        require_equal(marker.get(field), expected, f"Roofer marker {field}")

    raw_inventory = inventory_roofer_jsonseq(
        prepared["outputs"]["raw_jsonseq_dir"], lock
    )
    require_equal(marker.get("raw_jsonseq"), raw_inventory, "Roofer raw JSONSeq bundle")
    merged_record = validate_merged_cityjson(cityjson, lock)
    require_equal(
        merged_record["child_count"],
        raw_inventory["child_count"],
        "raw/merged Roofer child count",
    )
    require_equal(marker.get("merged_cityjson"), merged_record, "Roofer merged CityJSON")
    require_equal(
        _resolve_declared_path(marker.get("cityjson_path"), declaring_file=marker_path),
        cityjson,
        "Roofer marker CityJSON path",
    )
    require_equal(marker.get("cityjson_sha256"), merged_record["sha256"], "Roofer CityJSON SHA256")

    classification = prepared["classification"]
    pointcloud = prepared["pointcloud_path"]
    receipt_path = prepared["classification_receipt_path"]
    return {
        "roofer_invocation_count": 1,
        "roofer_marker_path": rel(marker_path),
        "roofer_marker_sha256": sha256_file(marker_path),
        "roofer_image": ROOFER_IMAGE,
        "roofer_parameters": ROOFER_PARAMETERS,
        "cityjson_path": rel(cityjson),
        "cityjson_sha256": merged_record["sha256"],
        "pointcloud_path": rel(pointcloud),
        "pointcloud_sha256": marker.get("pointcloud_sha256"),
        "classification_receipt_path": rel(receipt_path),
        "classification_receipt_sha256": classification["sha256"],
        "scene_npz_path": rel(classification["scene_npz_path"]),
        "scene_npz_sha256": classification["scene_npz_sha256"],
        "readout_lineage": classification["readout_lineage"],
        "crop_contract": classification["crop_contract"],
        "roofprints": classification["roofprints"],
        "prepare_receipt_path": rel(prepare_path),
        "prepare_receipt_sha256": prepare_record.get("sha256"),
        "execution_receipt_path": rel(execution_path),
        "execution_receipt_sha256": executed["sha256"],
        "roofer_execution": executed["normalized"],
        "raw_jsonseq": raw_inventory,
        "merged_cityjson": merged_record,
    }


def bind_readout_lineage_to_run(
    condition_id: str,
    seed: int,
    run_provenance: Mapping[str, Any],
    roofer_provenance: Mapping[str, Any],
) -> dict[str, Any]:
    """Require the Roofer input to originate from the scored full state."""

    lineage = roofer_provenance.get("readout_lineage")
    if not isinstance(lineage, Mapping):
        raise RuntimeError("Roofer provenance lacks read-out lineage")
    require_equal(lineage.get("schema"), READOUT_LINEAGE_SCHEMA, "read-out lineage schema")
    require_equal(lineage.get("condition_id"), condition_id, "read-out condition")
    require_equal(int(lineage.get("seed", -1)), int(seed), "read-out seed")
    checkpoint = lineage.get("checkpoint")
    full_state = lineage.get("full_state_manifest")
    if not isinstance(checkpoint, Mapping) or not isinstance(full_state, Mapping):
        raise RuntimeError("read-out lineage lacks checkpoint/full-state records")
    require_equal(
        checkpoint.get("sha256"),
        run_provenance.get("latest_full_checkpoint_sha256"),
        "read-out/scored checkpoint SHA256",
    )
    require_equal(
        int(checkpoint.get("completed_steps", -1)),
        int(run_provenance.get("latest_full_checkpoint_steps", -1)),
        "read-out/scored checkpoint step",
    )
    require_equal(
        rel(Path(str(checkpoint.get("path")))),
        run_provenance.get("latest_full_checkpoint_path"),
        "read-out/scored checkpoint path",
    )
    require_equal(
        full_state.get("sha256"),
        run_provenance.get("full_state_manifest_sha256"),
        "read-out/scored full-state SHA256",
    )
    require_equal(
        rel(Path(str(full_state.get("path")))),
        run_provenance.get("full_state_manifest_path"),
        "read-out/scored full-state path",
    )
    require_equal(
        bool(lineage.get("eligible_20k_full_state")),
        bool(run_provenance.get("eligible_20k_full_state")),
        "read-out/scored 20k eligibility",
    )
    return dict(lineage)


def validate_score_marker(
    condition_id: str,
    seed: int,
    marker_path: Path,
) -> dict[str, Any]:
    """Re-open every artifact named by a completed one-shot score marker."""

    marker_path = marker_path.resolve()
    if not marker_path.is_file():
        raise FileNotFoundError(marker_path)
    marker = json.loads(marker_path.read_text(encoding="utf-8"))
    require_equal(marker.get("schema"), SCORE_MARKER_SCHEMA, "score marker schema")
    require_equal(marker.get("condition_id"), condition_id, "score marker condition")
    require_equal(int(marker.get("seed", -1)), int(seed), "score marker seed")
    require_equal(marker.get("state"), "complete", "score marker state")
    require_equal(int(marker.get("score_invocation_count", 0)), 1, "score invocation count")
    require_equal(marker.get("val3dity_version"), VAL3DITY_VERSION, "score marker val3dity version")
    cityjson = _resolve_declared_path(marker.get("cityjson_path"), declaring_file=marker_path)
    report = _resolve_declared_path(marker.get("val3dity_report"), declaring_file=marker_path)
    output = _resolve_declared_path(marker.get("score_output_path"), declaring_file=marker_path)
    full_state = _resolve_declared_path(
        marker.get("full_state_manifest_path"), declaring_file=marker_path
    )
    roofer_marker = _resolve_declared_path(
        marker.get("roofer_marker_path"), declaring_file=marker_path
    )
    for path, expected, label in (
        (cityjson, marker.get("cityjson_sha256"), "score marker CityJSON SHA256"),
        (report, marker.get("val3dity_report_sha256"), "score marker val3dity report SHA256"),
        (output, marker.get("score_output_sha256"), "score marker output SHA256"),
        (full_state, marker.get("full_state_manifest_sha256"), "score marker full-state SHA256"),
        (roofer_marker, marker.get("roofer_marker_sha256"), "score marker Roofer SHA256"),
    ):
        require_equal(sha256_file(path), expected, label)
    require_equal(len(read_csv(output)), EXPECTED_POPULATION, "score marker output row count")
    return {
        **marker,
        "score_marker_path": rel(marker_path),
        "score_marker_sha256": sha256_file(marker_path),
        "score_output_resolved": output,
    }


def _all_coordinate_lengths(value: Any) -> Iterable[int]:
    if isinstance(value, (list, tuple)):
        if value and all(isinstance(item, (int, float)) for item in value):
            yield len(value)
        else:
            for item in value:
                yield from _all_coordinate_lengths(item)


def materialize_locked_roofprints(lock: PilotLock, output: Path) -> dict[str, Any]:
    """Write only the selected 30 approved GroundSurface XY footprints."""

    require_equal(sha256_file(FOOTPRINT_SOURCE), FOOTPRINT_SOURCE_SHA256, "footprint source SHA256")
    payload = json.loads(FOOTPRINT_SOURCE.read_text(encoding="utf-8"))
    crs = str((payload.get("crs") or {}).get("properties", {}).get("name", ""))
    if "25832" not in crs:
        raise RuntimeError(f"footprint CRS drift: {crs}")
    by_id: dict[str, dict[str, Any]] = {}
    for feature in payload.get("features", []):
        building_id = str((feature.get("properties") or {}).get("building_id", ""))
        if building_id in lock.ids:
            if building_id in by_id:
                raise RuntimeError(f"duplicate footprint: {building_id}")
            lengths = list(_all_coordinate_lengths((feature.get("geometry") or {}).get("coordinates")))
            if not lengths or any(length != 2 for length in lengths):
                raise RuntimeError(f"footprint is not XY-only: {building_id}")
            by_id[building_id] = feature
    missing = [building_id for building_id in lock.ids if building_id not in by_id]
    if missing:
        raise RuntimeError(f"missing locked footprints: {missing}")
    features = []
    for item in lock.buildings:
        source = by_id[item.building_id]
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "building_id": item.building_id,
                    "selection_rank": item.selection_rank,
                    # Canonical PDAL overlay consumes ``column=class``.  The
                    # geometry remains approved GroundSurface XY only.
                    "class": 6,
                },
                "geometry": source["geometry"],
            }
        )
    result = {
        "type": "FeatureCollection",
        "name": "pilot_1wave_locked_30_groundsurface_xy",
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::25832"}},
        "features": features,
    }
    if any(feature["properties"].get("class") != 6 for feature in features):
        raise RuntimeError("locked roofprint PDAL class drift")
    atomic_text(output, json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n")
    validated = validate_roofprint_file(
        output, expected_building_ids=lock.ids
    )
    return {
        **validated,
        "path": rel(output),
        "source_path": rel(FOOTPRINT_SOURCE),
        "source_sha256": FOOTPRINT_SOURCE_SHA256,
    }


def _require_repo_path(path: Path, label: str) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(REPO.resolve())
    except ValueError as exc:
        raise RuntimeError(f"{label} must be inside repository: {resolved}") from exc
    return resolved


def require_p0_tools_runtime() -> dict[str, Any]:
    """Require explicit proof that this boundary is running in pinned p0-tools."""

    if not DOCKER_SENTINEL.is_file():
        raise RuntimeError("Roofer boundary requires the Docker sentinel /.dockerenv")
    if os.environ.get(P0_TOOLS_SENTINEL_ENV) != "1":
        raise RuntimeError(f"Roofer boundary lacks {P0_TOOLS_SENTINEL_ENV}=1")
    image_id = os.environ.get(P0_TOOLS_IMAGE_ID_ENV, "").strip()
    require_equal(image_id, P0_TOOLS_IMAGE_ID, "p0-tools image ID attestation")
    require_equal(sha256_file(W2_SCRIPT), W2_SCRIPT_SHA256, "Roofer W2 script SHA256")
    return {
        "docker_sentinel": str(DOCKER_SENTINEL),
        "p0_tools_image": P0_TOOLS_IMAGE,
        "p0_tools_expected_local_image_id": P0_TOOLS_IMAGE_ID,
        "p0_tools_attested_local_image_id": image_id,
        "scoring_script": {
            "path": rel(Path(__file__)),
            "sha256": sha256_file(Path(__file__)),
        },
        "w2_script": {
            "path": rel(W2_SCRIPT),
            "sha256": W2_SCRIPT_SHA256,
        },
    }


def _container_repo_path(path: Path, label: str) -> str:
    relative = _require_repo_path(path, label).relative_to(REPO.resolve())
    return str(ROOFER_CONTAINER_REPO / relative)


def roofer_argv_payload(
    condition_id: str,
    seed: int,
    pointcloud: Path,
    roofprints: Path,
    raw_jsonseq_dir: Path,
) -> dict[str, Any]:
    """Return immutable Roofer-container argv; never invoke Docker here."""

    validate_condition_seed(condition_id, seed)
    return {
        "schema": ROOFER_ARGV_SCHEMA,
        "condition_id": condition_id,
        "seed": int(seed),
        "image": ROOFER_IMAGE,
        "arguments": [
            *ROOFER_PARAMETER_ARGV,
            _container_repo_path(pointcloud, "pointcloud"),
            _container_repo_path(roofprints, "roofprints"),
            _container_repo_path(raw_jsonseq_dir, "raw JSONSeq output"),
        ],
    }


def validate_roofer_pointcloud(path: Path) -> dict[str, Any]:
    """Require the canonical EPSG and both classes consumed by Roofer."""

    if path.suffix.lower() not in {".las", ".laz"}:
        raise RuntimeError("Roofer pointcloud input must be LAS/LAZ")
    if not path.is_file():
        raise FileNotFoundError(path)
    try:
        metric_module = get_metric_module()
    except ModuleNotFoundError:
        if os.environ.get("P1W_INSIDE_P0_TOOLS") == "1":
            raise
        return validate_roofer_pointcloud_in_tools(path)
    classes: set[int] = set()
    with metric_module.laspy.open(path) as reader:
        crs = reader.header.parse_crs()
        epsg = crs.to_epsg() if crs is not None else None
        point_count = int(reader.header.point_count)
        dimensions = set(reader.header.point_format.dimension_names)
        if "classification" not in dimensions:
            raise RuntimeError("Roofer pointcloud has no classification dimension")
        for chunk in reader.chunk_iterator(1_000_000):
            classes.update(int(value) for value in np.unique(np.asarray(chunk.classification)))
            if {2, 6}.issubset(classes):
                break
    require_equal(epsg, 25832, "Roofer pointcloud EPSG")
    if point_count <= 0:
        raise RuntimeError("Roofer pointcloud is empty")
    if not {2, 6}.issubset(classes):
        raise RuntimeError(f"Roofer pointcloud class lock drift: observed={sorted(classes)} expected=[2, 6]")
    return {
        "path": rel(path),
        "sha256": sha256_file(path),
        "point_count": point_count,
        "epsg": epsg,
        "classes_required": [2, 6],
        "validation_runtime": "current_python",
    }


def validate_roofer_pointcloud_in_tools(path: Path) -> dict[str, Any]:
    """Run the LAS header/class gate in the pinned tools image from a lean host."""

    try:
        relative = path.resolve().relative_to(REPO.resolve())
    except ValueError as exc:
        raise RuntimeError("pointcloud must be inside repository for tools validation") from exc
    container_repo = Path("/workspace/JointBuildGS")
    command = [
        "docker",
        "run",
        "--rm",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "-e",
        "PYTHONDONTWRITEBYTECODE=1",
        "-e",
        "P1W_INSIDE_P0_TOOLS=1",
        "-v",
        f"{REPO}:{container_repo}:ro",
        "-w",
        str(container_repo),
        P0_TOOLS_IMAGE,
        "python3",
        str(container_repo / "scripts/pilot_1wave/pilot_1wave_scoring.py"),
        "validate-pointcloud",
        "--pointcloud",
        str(container_repo / relative),
    ]
    process = subprocess.run(
        command,
        cwd=REPO,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if process.returncode != 0:
        raise RuntimeError(
            f"p0-tools pointcloud validation failed exit={process.returncode}: {process.stdout}"
        )
    try:
        record = json.loads((process.stdout or "").strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"invalid p0-tools validator output: {process.stdout}") from exc
    require_equal(record.get("sha256"), sha256_file(path), "p0-tools pointcloud SHA256")
    require_equal(int(record.get("epsg", -1)), 25832, "p0-tools pointcloud EPSG")
    require_equal(record.get("classes_required"), [2, 6], "p0-tools pointcloud classes")
    record["path"] = rel(path)
    record["validation_runtime"] = P0_TOOLS_IMAGE
    return record


def _classification_receipt_binding(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "path": rel(record["path"]),
        "sha256": record["sha256"],
        "scene_npz_path": rel(record["scene_npz_path"]),
        "scene_npz_sha256": record["scene_npz_sha256"],
    }


def prepare_roofer(
    condition_id: str,
    seed: int,
    pointcloud: Path,
    classification_receipt: Path,
    output_dir: Path,
    lock: PilotLock,
) -> dict[str, Any]:
    """Validate inputs and publish immutable Roofer argv without executing it."""

    runtime_contract = require_p0_tools_runtime()
    validate_condition_seed(condition_id, seed)
    pointcloud = _require_repo_path(pointcloud, "pointcloud")
    classification_receipt = _require_repo_path(
        classification_receipt, "classification receipt"
    )
    output_dir = _require_repo_path(output_dir, "Roofer runtime output")
    if output_dir.exists():
        if not output_dir.is_dir():
            raise RuntimeError(f"Roofer runtime output is not a directory: {output_dir}")
        if any(output_dir.iterdir()):
            raise RuntimeError(f"Roofer runtime output is not empty: {output_dir}")
    else:
        output_dir.mkdir(parents=True)

    prepare_path = output_dir / "roofer_prepare.json"
    argv_path = output_dir / "roofer_argv.json"
    raw_jsonseq_dir = output_dir / "raw_jsonseq"
    cityjson = output_dir / "assembled.city.json"
    marker = output_dir / "roofer_invocation.json"
    raw_jsonseq_dir.mkdir()

    pointcloud_record = validate_roofer_pointcloud(pointcloud)
    classification = validate_classification_receipt(
        classification_receipt,
        pointcloud_path=pointcloud,
        expected_condition=condition_id,
        expected_seed=seed,
        expected_building_ids=lock.ids,
        require_verified_crop=True,
    )
    footprints = dict(classification["roofprints"])
    roofprint_path = _require_repo_path(Path(footprints["path"]), "roofprints")
    require_equal(tuple(footprints["building_ids"]), lock.ids, "Roofer roofprint order")
    require_equal(
        sha256_file(roofprint_path), footprints["sha256"], "Roofer roofprint SHA256"
    )

    argv_payload = roofer_argv_payload(
        condition_id, seed, pointcloud, roofprint_path, raw_jsonseq_dir
    )
    atomic_json(argv_path, argv_payload)
    argv_record = {
        "path": rel(argv_path),
        "sha256": sha256_file(argv_path),
        "schema": ROOFER_ARGV_SCHEMA,
        "image": ROOFER_IMAGE,
        "arguments": argv_payload["arguments"],
    }
    receipt = {
        "schema": ROOFER_PREPARE_SCHEMA,
        "state": "prepared",
        "condition_id": condition_id,
        "seed": int(seed),
        "created_utc": now(),
        "selection_sha256": lock.selection_sha256,
        "ordered_ids_sha256": lock.ordered_ids_sha256,
        "ordered_building_ids": list(lock.ids),
        "runtime_contract": runtime_contract,
        "roofer_image": ROOFER_IMAGE,
        "roofer_parameters": ROOFER_PARAMETERS,
        "roofer_argv": argv_record,
        "pointcloud_path": pointcloud_record["path"],
        "pointcloud_sha256": pointcloud_record["sha256"],
        "pointcloud": pointcloud_record,
        "classification_receipt": _classification_receipt_binding(classification),
        "readout_lineage": classification["readout_lineage"],
        "crop_contract": classification["crop_contract"],
        "footprints": footprints,
        "outputs": {
            "runtime_dir": rel(output_dir),
            "raw_jsonseq_dir": rel(raw_jsonseq_dir),
            "merged_cityjson_path": rel(cityjson),
            "marker_path": rel(marker),
        },
    }
    atomic_json(prepare_path, receipt)
    return {
        **receipt,
        "path": str(prepare_path),
        "sha256": sha256_file(prepare_path),
    }


def validate_roofer_prepare_receipt(
    prepare_path: Path,
    lock: PilotLock,
    *,
    expected_condition: str | None = None,
    expected_seed: int | None = None,
) -> dict[str, Any]:
    """Re-open every prepare-bound byte and rebuild the canonical argv."""

    runtime_contract = require_p0_tools_runtime()
    prepare_path = _require_repo_path(prepare_path, "Roofer prepare receipt")
    if not prepare_path.is_file():
        raise FileNotFoundError(prepare_path)
    require_equal(prepare_path.name, "roofer_prepare.json", "Roofer prepare filename")
    payload = json.loads(prepare_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("Roofer prepare receipt root must be an object")
    require_equal(payload.get("schema"), ROOFER_PREPARE_SCHEMA, "Roofer prepare schema")
    require_equal(payload.get("state"), "prepared", "Roofer prepare state")
    condition_id = str(payload.get("condition_id", ""))
    seed = int(payload.get("seed", -1))
    validate_condition_seed(condition_id, seed)
    if expected_condition is not None:
        require_equal(condition_id, expected_condition, "Roofer prepare condition")
    if expected_seed is not None:
        require_equal(seed, int(expected_seed), "Roofer prepare seed")
    require_equal(payload.get("selection_sha256"), lock.selection_sha256, "prepare selection SHA256")
    require_equal(payload.get("ordered_ids_sha256"), lock.ordered_ids_sha256, "prepare ordered IDs SHA256")
    require_equal(payload.get("ordered_building_ids"), list(lock.ids), "prepare ordered building IDs")
    require_equal(payload.get("runtime_contract"), runtime_contract, "prepare runtime contract")
    require_equal(payload.get("roofer_image"), ROOFER_IMAGE, "prepare Roofer image")
    require_equal(payload.get("roofer_parameters"), ROOFER_PARAMETERS, "prepare Roofer parameters")

    output_dir = prepare_path.parent.resolve()
    outputs = payload.get("outputs")
    if not isinstance(outputs, Mapping):
        raise RuntimeError("Roofer prepare receipt lacks output paths")
    expected_outputs = {
        "runtime_dir": output_dir,
        "raw_jsonseq_dir": output_dir / "raw_jsonseq",
        "merged_cityjson_path": output_dir / "assembled.city.json",
        "marker_path": output_dir / "roofer_invocation.json",
    }
    resolved_outputs: dict[str, Path] = {}
    for field, expected in expected_outputs.items():
        require_equal(outputs.get(field), rel(expected), f"prepare output {field}")
        resolved_outputs[field] = _require_repo_path(expected, f"prepare output {field}")
    if not resolved_outputs["raw_jsonseq_dir"].is_dir():
        raise RuntimeError("prepared raw JSONSeq output is not a directory")
    if (output_dir / "raw_jsonseq").is_symlink():
        raise RuntimeError("prepared raw JSONSeq output must not be a symlink")

    pointcloud = _resolve_declared_path(
        payload.get("pointcloud_path"), declaring_file=prepare_path
    )
    pointcloud_record = validate_roofer_pointcloud(pointcloud)
    require_equal(payload.get("pointcloud_sha256"), pointcloud_record["sha256"], "prepare pointcloud SHA256")
    require_equal(payload.get("pointcloud"), pointcloud_record, "prepare pointcloud record")

    receipt_binding = payload.get("classification_receipt")
    if not isinstance(receipt_binding, Mapping):
        raise RuntimeError("Roofer prepare lacks classification receipt binding")
    classification_receipt = _resolve_declared_path(
        receipt_binding.get("path"), declaring_file=prepare_path
    )
    classification = validate_classification_receipt(
        classification_receipt,
        pointcloud_path=pointcloud,
        expected_condition=condition_id,
        expected_seed=seed,
        expected_building_ids=lock.ids,
        require_verified_crop=True,
    )
    require_equal(
        receipt_binding,
        _classification_receipt_binding(classification),
        "prepare classification receipt",
    )
    for payload_field, classification_field in (
        ("readout_lineage", "readout_lineage"),
        ("crop_contract", "crop_contract"),
        ("footprints", "roofprints"),
    ):
        require_equal(
            payload.get(payload_field),
            classification[classification_field],
            f"prepare {payload_field}",
        )

    argv_record = payload.get("roofer_argv")
    if not isinstance(argv_record, Mapping):
        raise RuntimeError("Roofer prepare lacks argv binding")
    argv_path = _resolve_declared_path(argv_record.get("path"), declaring_file=prepare_path)
    require_equal(argv_path, output_dir / "roofer_argv.json", "Roofer argv path")
    require_equal(sha256_file(argv_path), argv_record.get("sha256"), "Roofer argv SHA256")
    argv_payload = json.loads(argv_path.read_text(encoding="utf-8"))
    roofprint_path = Path(classification["roofprints"]["path"])
    expected_argv = roofer_argv_payload(
        condition_id,
        seed,
        pointcloud,
        roofprint_path,
        resolved_outputs["raw_jsonseq_dir"],
    )
    require_equal(argv_payload, expected_argv, "Roofer argv contents")
    normalized_argv = {
        "path": rel(argv_path),
        "sha256": sha256_file(argv_path),
        "schema": ROOFER_ARGV_SCHEMA,
        "image": ROOFER_IMAGE,
        "arguments": expected_argv["arguments"],
    }
    require_equal(argv_record, normalized_argv, "Roofer argv record")
    return {
        "path": str(prepare_path),
        "sha256": sha256_file(prepare_path),
        "condition_id": condition_id,
        "seed": seed,
        "runtime_contract": runtime_contract,
        "roofer_argv": normalized_argv,
        "pointcloud_path": pointcloud,
        "pointcloud": pointcloud_record,
        "classification_receipt_path": classification_receipt,
        "classification_receipt": _classification_receipt_binding(classification),
        "classification": classification,
        "readout_lineage": classification["readout_lineage"],
        "crop_contract": classification["crop_contract"],
        "footprints": classification["roofprints"],
        "outputs": resolved_outputs,
    }


def _validate_execution_artifact_record(
    record: Any,
    *,
    declaring_file: Path,
    expected_path: Path,
    label: str,
    include_size: bool = False,
) -> dict[str, Any]:
    """Re-open one fixed execution artifact and normalize its byte binding."""

    if not isinstance(record, Mapping):
        raise RuntimeError(f"{label} must be an artifact record")
    if expected_path.is_symlink():
        raise RuntimeError(f"{label} must not be a symlink: {expected_path}")
    path = _resolve_declared_path(record.get("path"), declaring_file=declaring_file)
    expected_path = _require_repo_path(expected_path, label)
    require_equal(path, expected_path, f"{label} path")
    if not path.is_file():
        raise FileNotFoundError(path)
    digest = sha256_file(path)
    require_equal(record.get("sha256"), digest, f"{label} SHA256")
    normalized: dict[str, Any] = {"path": rel(path), "sha256": digest}
    if include_size:
        size = path.stat().st_size
        require_equal(int(record.get("size", -1)), size, f"{label} size")
        normalized["size"] = size
    require_equal(dict(record), normalized, f"{label} record")
    return normalized


def validate_repository_bind(
    binds: Any,
    launch: Mapping[str, Any],
) -> dict[str, str]:
    """Bind Docker's host path alias to the sealed ``docker create -v``.

    This validator runs inside p0-tools, where ``REPO`` is the container path
    ``/workspace/JointBuildGS``.  Docker inspect, however, reports the host
    source path.  The two path namespaces must not be compared for equality.
    """

    if not isinstance(binds, list) or len(binds) != 1 or not isinstance(binds[0], str):
        raise RuntimeError("Roofer repository bind must contain exactly one string")
    raw = binds[0]

    def parse(value: str, label: str) -> tuple[str, str, str]:
        parts = value.split(":")
        if len(parts) == 2:
            source_value, target_value = parts
            mode_value = ""
        elif len(parts) == 3:
            source_value, target_value, mode_value = parts
        else:
            raise RuntimeError(f"{label} has invalid syntax: {value!r}")
        if not source_value or not Path(source_value).is_absolute():
            raise RuntimeError(f"{label} source must be an absolute host path")
        require_equal(target_value, str(ROOFER_CONTAINER_REPO), f"{label} target")
        if mode_value not in {"", "rw"}:
            raise RuntimeError(
                f"{label} mode must be absent or rw: {mode_value!r}"
            )
        return source_value, target_value, "rw"

    source, target, mode = parse(raw, "Roofer repository bind")

    create_command = launch.get("create_command")
    if not isinstance(create_command, list) or any(
        not isinstance(value, str) for value in create_command
    ):
        raise RuntimeError("Roofer launch create_command must be a string array")
    volume_values: list[str] = []
    index = 0
    while index < len(create_command):
        value = create_command[index]
        if value in {"-v", "--volume"}:
            if index + 1 >= len(create_command):
                raise RuntimeError("Roofer launch create_command has a dangling volume flag")
            volume_values.append(create_command[index + 1])
            index += 2
            continue
        if value.startswith("--volume="):
            volume_values.append(value.partition("=")[2])
        index += 1
    require_equal(len(volume_values), 1, "Roofer launch repository bind count")
    launch_raw = volume_values[0]
    launch_source, launch_target, launch_mode = parse(
        launch_raw, "Roofer launch repository bind"
    )
    require_equal(launch_source, source, "Roofer launch/inspect bind source")
    require_equal(launch_target, target, "Roofer launch/inspect bind target")
    require_equal(launch_mode, mode, "Roofer launch/inspect bind mode")
    return {
        "source": source,
        "target": target,
        "mode": mode,
        "docker_value": raw,
        "launch_value": launch_raw,
    }


def validate_roofer_execution_receipt(
    execution_path: Path,
    prepared: Mapping[str, Any],
    *,
    expected_condition: str | None = None,
    expected_seed: int | None = None,
) -> dict[str, Any]:
    """Validate retained-container proof and every immutable evidence byte."""

    execution_path = _require_repo_path(execution_path, "Roofer execution receipt")
    output_dir = Path(str(prepared["path"])).resolve().parent
    expected_execution_path = output_dir / "roofer_execution_receipt.json"
    if expected_execution_path.is_symlink():
        raise RuntimeError(
            f"Roofer execution receipt must not be a symlink: {expected_execution_path}"
        )
    require_equal(
        execution_path,
        expected_execution_path,
        "Roofer execution receipt path",
    )
    if not execution_path.is_file():
        raise FileNotFoundError(execution_path)
    payload = json.loads(execution_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("Roofer execution receipt root must be an object")
    require_equal(payload.get("schema"), ROOFER_EXECUTION_SCHEMA, "Roofer execution schema")
    require_equal(payload.get("state"), "complete", "Roofer execution state")
    condition_id = str(payload.get("condition_id", ""))
    seed = int(payload.get("seed", -1))
    validate_condition_seed(condition_id, seed)
    require_equal(condition_id, prepared["condition_id"], "execution/prepare condition")
    require_equal(seed, int(prepared["seed"]), "execution/prepare seed")
    if expected_condition is not None:
        require_equal(condition_id, expected_condition, "Roofer execution condition")
    if expected_seed is not None:
        require_equal(seed, int(expected_seed), "Roofer execution seed")
    require_equal(
        int(payload.get("roofer_invocation_count", 0)),
        1,
        "Roofer execution invocation count",
    )
    expected_job_id = f"{condition_id}_seed{seed}"
    job_id = str(payload.get("job_id", "")).strip()
    require_equal(job_id, expected_job_id, "Roofer execution job_id")

    prepare_binding = payload.get("prepare_receipt")
    if not isinstance(prepare_binding, Mapping):
        raise RuntimeError("Roofer execution receipt lacks prepare receipt binding")
    normalized_prepare = {
        "path": rel(Path(str(prepared["path"]))),
        "sha256": prepared["sha256"],
    }
    require_equal(dict(prepare_binding), normalized_prepare, "execution prepare receipt")
    prepare_bound_path = _resolve_declared_path(
        prepare_binding.get("path"), declaring_file=execution_path
    )
    require_equal(
        prepare_bound_path,
        Path(str(prepared["path"])).resolve(),
        "execution prepare receipt path",
    )
    require_equal(
        sha256_file(prepare_bound_path),
        prepare_binding.get("sha256"),
        "execution prepare receipt SHA256",
    )

    argv_binding = payload.get("roofer_argv")
    if not isinstance(argv_binding, Mapping):
        raise RuntimeError("Roofer execution receipt lacks Roofer argv binding")
    normalized_argv = {
        "path": prepared["roofer_argv"]["path"],
        "sha256": prepared["roofer_argv"]["sha256"],
    }
    require_equal(dict(argv_binding), normalized_argv, "execution Roofer argv")
    argv_bound_path = _resolve_declared_path(
        argv_binding.get("path"), declaring_file=execution_path
    )
    require_equal(
        argv_bound_path,
        output_dir / "roofer_argv.json",
        "execution Roofer argv path",
    )
    require_equal(
        sha256_file(argv_bound_path),
        argv_binding.get("sha256"),
        "execution Roofer argv SHA256",
    )
    expected_arguments = list(prepared["roofer_argv"]["arguments"])
    expected_contract = {
        "job_id": expected_job_id,
        "prepare_sha256": prepared["sha256"],
        "argv_sha256": prepared["roofer_argv"]["sha256"],
        "image": ROOFER_IMAGE,
        "arguments": expected_arguments,
    }
    expected_contract_sha = canonical_json_sha256(expected_contract)
    expected_container_name = (
        f"{ROOFER_CONTAINER_NAME_PREFIX}-{condition_id}-seed{seed}-roofer"
    )
    container = payload.get("container")
    execution = payload.get("execution")
    if not isinstance(container, Mapping) or not isinstance(execution, Mapping):
        raise RuntimeError("Roofer execution receipt lacks container/execution facts")
    require_equal(container.get("image_reference"), ROOFER_IMAGE, "Roofer image reference")
    require_equal(container.get("image_id"), ROOFER_IMAGE_ID, "Roofer local image ID")
    require_equal(container.get("config_image"), ROOFER_IMAGE, "Roofer config image")
    require_equal(
        container.get("entrypoint"),
        list(ROOFER_ENTRYPOINT),
        "Roofer container entrypoint",
    )
    require_equal(container.get("cmd"), expected_arguments, "Roofer container command")
    labels = container.get("labels")
    if not isinstance(labels, Mapping):
        raise RuntimeError("Roofer container labels must be an object")
    require_equal(labels.get("jointbuildgs.p1w.job"), expected_job_id, "Roofer job label")
    require_equal(
        labels.get("jointbuildgs.p1w.contract"),
        expected_contract_sha,
        "Roofer contract label",
    )
    require_equal(
        container.get("network_mode"), "none", "Roofer container network mode"
    )
    require_equal(int(container.get("restart_count", -1)), 0, "Roofer restart count")
    container_id = str(container.get("id", ""))
    if re.fullmatch(r"[0-9a-f]{64}", container_id) is None:
        raise RuntimeError("Roofer execution container ID is invalid")
    container_name = str(container.get("name", "")).strip()
    require_equal(container_name, expected_container_name, "Roofer container name")
    require_equal(execution.get("docker_state"), "exited", "Roofer Docker state")
    require_equal(int(execution.get("wait_exit_code", -1)), 0, "Roofer wait exit code")
    require_equal(
        int(execution.get("start_attempt_count", 0)),
        1,
        "Roofer start attempt count",
    )
    start_attempts = execution.get("start_attempts")
    if not isinstance(start_attempts, list):
        raise RuntimeError("Roofer execution start-attempt ledger must be an array")
    require_equal(len(start_attempts), 1, "Roofer start-attempt ledger length")

    launch_record = _validate_execution_artifact_record(
        payload.get("launch_receipt"),
        declaring_file=execution_path,
        expected_path=output_dir / "container_launch.json",
        label="Roofer launch receipt",
    )
    process_record = _validate_execution_artifact_record(
        payload.get("process_receipt"),
        declaring_file=execution_path,
        expected_path=output_dir / "process_complete.json",
        label="Roofer process receipt",
    )
    log_record = _validate_execution_artifact_record(
        payload.get("logs"),
        declaring_file=execution_path,
        expected_path=output_dir / "container.log",
        label="Roofer immutable log",
        include_size=True,
    )
    launch = json.loads((output_dir / "container_launch.json").read_text(encoding="utf-8"))
    process = json.loads((output_dir / "process_complete.json").read_text(encoding="utf-8"))
    if not isinstance(launch, Mapping) or not isinstance(process, Mapping):
        raise RuntimeError("Roofer launch/process receipts must contain JSON objects")
    require_equal(launch.get("container_id"), container_id, "launch/container ID")
    require_equal(launch.get("container_name"), container_name, "launch/container name")
    require_equal(
        launch.get("contract_sha256"),
        expected_contract_sha,
        "launch contract SHA256",
    )
    require_equal(launch.get("start_attempts"), start_attempts, "launch start attempts")
    require_equal(int(launch.get("start_attempt_count", 0)), 1, "launch start attempt count")
    require_equal(process.get("container_name"), container_name, "process/container name")
    require_equal(process.get("contract_sha256"), launch.get("contract_sha256"), "process/launch contract SHA256")
    require_equal(int(process.get("exit_code", -1)), 0, "process exit code")
    require_equal(int(process.get("wait_exit_code", -1)), 0, "process wait exit code")

    require_equal(launch.get("job_id"), job_id, "launch job_id")
    require_equal(process.get("job_id"), job_id, "process job_id")
    repo_bind = validate_repository_bind(container.get("binds"), launch)
    normalized = {
        "schema": ROOFER_EXECUTION_SCHEMA,
        "state": "complete",
        "condition_id": condition_id,
        "seed": seed,
        "job_id": job_id,
        "roofer_invocation_count": 1,
        "prepare_receipt": normalized_prepare,
        "roofer_argv": normalized_argv,
        "roofer_image_reference": ROOFER_IMAGE,
        "roofer_local_image_id": ROOFER_IMAGE_ID,
        "container_id": container_id,
        "container_name": container_name,
        "roofer_entrypoint": list(ROOFER_ENTRYPOINT),
        "roofer_command": expected_arguments,
        "contract_sha256": expected_contract_sha,
        "container_labels": {
            "jointbuildgs.p1w.job": expected_job_id,
            "jointbuildgs.p1w.contract": expected_contract_sha,
        },
        "network_mode": "none",
        "repo_bind": repo_bind,
        "docker_state": "exited",
        "wait_exit_code": 0,
        "start_attempt_count": 1,
        "restart_count": 0,
        "launch_receipt": launch_record,
        "process_receipt": process_record,
        "logs": log_record,
    }
    return {
        "path": str(execution_path),
        "sha256": sha256_file(execution_path),
        "normalized": normalized,
    }


def _validate_cityobject_ownership(
    cityobjects: Any,
    expected_root_ids: Sequence[str],
    label: str,
) -> dict[str, Any]:
    if not isinstance(cityobjects, Mapping):
        raise RuntimeError(f"{label} CityObjects must be an object")
    objects = {str(key): value for key, value in cityobjects.items()}
    if any(not isinstance(value, Mapping) for value in objects.values()):
        raise RuntimeError(f"{label} CityObject must be an object")
    roots = [
        object_id
        for object_id, value in objects.items()
        if value.get("type") == "Building" and not value.get("parents")
    ]
    require_equal(set(roots), set(expected_root_ids), f"{label} root Building IDs")
    require_equal(len(roots), len(expected_root_ids), f"{label} root Building count")
    owners: dict[str, str] = {}
    for root_id in roots:
        children = objects[root_id].get("children") or []
        if not isinstance(children, list) or any(not isinstance(child, str) for child in children):
            raise RuntimeError(f"{label} root children are invalid: {root_id}")
        require_equal(len(children), len(set(children)), f"{label} duplicate children {root_id}")
        for child_id in children:
            if child_id not in objects:
                raise RuntimeError(f"{label} missing child object: {child_id}")
            if child_id in owners:
                raise RuntimeError(f"{label} shared child object: {child_id}")
            owners[child_id] = root_id
    non_roots = set(objects) - set(roots)
    require_equal(set(owners), non_roots, f"{label} orphan child objects")
    for child_id, owner in owners.items():
        parents = objects[child_id].get("parents")
        require_equal(parents, [owner], f"{label} child parent {child_id}")
    return {
        "root_building_count": len(roots),
        "root_building_ids": list(expected_root_ids),
        "child_count": len(owners),
        "child_ids": sorted(owners),
    }


def inventory_roofer_jsonseq(raw_jsonseq_dir: Path, lock: PilotLock) -> dict[str, Any]:
    """Hash and structurally validate every raw Roofer CityJSONSeq file."""

    raw_jsonseq_dir = _require_repo_path(raw_jsonseq_dir, "raw JSONSeq directory")
    if not raw_jsonseq_dir.is_dir():
        raise FileNotFoundError(raw_jsonseq_dir)
    entries = sorted(raw_jsonseq_dir.iterdir(), key=lambda path: path.name)
    unexpected = [
        path.name
        for path in entries
        if path.is_symlink() or not path.is_file() or not path.name.endswith(".city.jsonl")
    ]
    if unexpected:
        raise RuntimeError(f"unexpected raw JSONSeq entries: {unexpected}")
    files = [path.resolve() for path in entries]
    if not files:
        raise RuntimeError("raw JSONSeq bundle is missing")

    file_records: list[dict[str, Any]] = []
    feature_ids: list[str] = []
    child_ids: set[str] = set()
    object_ids: set[str] = set()
    for path in files:
        size = path.stat().st_size
        if size <= 0:
            raise RuntimeError(f"raw JSONSeq file is empty: {path}")
        file_records.append(
            {"path": rel(path), "size_bytes": size, "sha256": sha256_file(path)}
        )
        with path.open(encoding="utf-8") as stream:
            header_line = stream.readline()
            try:
                header = json.loads(header_line)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"invalid CityJSONSeq header: {path}") from exc
            if not isinstance(header, dict) or header.get("type") != "CityJSON":
                raise RuntimeError(f"invalid CityJSONSeq header object: {path}")
            require_equal(
                header.get("CityObjects"), {}, f"CityJSONSeq header CityObjects {path}"
            )
            require_equal(header.get("vertices"), [], f"CityJSONSeq header vertices {path}")
            file_feature_count = 0
            for line_number, line in enumerate(stream, 2):
                if not line.strip():
                    continue
                try:
                    feature = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise RuntimeError(
                        f"invalid CityJSONFeature JSON: {path}:{line_number}"
                    ) from exc
                if not isinstance(feature, dict) or feature.get("type") != "CityJSONFeature":
                    raise RuntimeError(f"invalid CityJSONFeature: {path}:{line_number}")
                feature_id = str(feature.get("id", ""))
                if not feature_id:
                    raise RuntimeError(f"CityJSONFeature lacks id: {path}:{line_number}")
                ownership = _validate_cityobject_ownership(
                    feature.get("CityObjects"), [feature_id], f"raw feature {feature_id}"
                )
                current_objects = set(str(key) for key in feature["CityObjects"])
                overlap = object_ids.intersection(current_objects)
                if overlap:
                    raise RuntimeError(f"duplicate raw CityObject IDs: {sorted(overlap)}")
                object_ids.update(current_objects)
                current_children = set(ownership["child_ids"])
                shared = child_ids.intersection(current_children)
                if shared:
                    raise RuntimeError(f"shared raw child ownership: {sorted(shared)}")
                child_ids.update(current_children)
                feature_ids.append(feature_id)
                file_feature_count += 1
            if file_feature_count == 0:
                raise RuntimeError(f"raw JSONSeq file has no CityJSONFeature: {path}")
    require_equal(len(feature_ids), EXPECTED_POPULATION, "raw CityJSONFeature count")
    require_equal(len(set(feature_ids)), EXPECTED_POPULATION, "raw CityJSONFeature unique IDs")
    require_equal(set(feature_ids), set(lock.ids), "raw CityJSONFeature IDs")
    return {
        "directory_path": rel(raw_jsonseq_dir),
        "file_count": len(file_records),
        "files": file_records,
        "bundle_sha256": canonical_json_sha256({"files": file_records}),
        "feature_count": len(feature_ids),
        "feature_ids_in_read_order": feature_ids,
        "root_building_count": EXPECTED_POPULATION,
        "root_building_ids": list(lock.ids),
        "child_count": len(child_ids),
    }


def validate_merged_cityjson(cityjson: Path, lock: PilotLock) -> dict[str, Any]:
    cityjson = _require_repo_path(cityjson, "merged CityJSON")
    if not cityjson.is_file():
        raise FileNotFoundError(cityjson)
    payload = json.loads(cityjson.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("type") != "CityJSON":
        raise RuntimeError("merged CityJSON root/type is invalid")
    ownership = _validate_cityobject_ownership(
        payload.get("CityObjects"), lock.ids, "merged CityJSON"
    )
    if not isinstance(payload.get("vertices"), list):
        raise RuntimeError("merged CityJSON vertices must be an array")
    return {
        "path": rel(cityjson),
        "sha256": sha256_file(cityjson),
        "size_bytes": cityjson.stat().st_size,
        "root_building_count": ownership["root_building_count"],
        "root_building_ids": ownership["root_building_ids"],
        "child_count": ownership["child_count"],
    }


def _roofer_marker_payload(
    prepared: Mapping[str, Any],
    executed: Mapping[str, Any],
    raw_inventory: Mapping[str, Any],
    merged_record: Mapping[str, Any],
    lock: PilotLock,
) -> dict[str, Any]:
    """Build the canonical completed marker after all bytes are validated."""

    classification = prepared["classification"]
    return {
        "schema": ROOFER_MARKER_SCHEMA,
        "state": "complete",
        "condition_id": prepared["condition_id"],
        "seed": prepared["seed"],
        "finalized_utc": now(),
        "roofer_invocation_count": 1,
        "selection_sha256": lock.selection_sha256,
        "ordered_ids_sha256": lock.ordered_ids_sha256,
        "ordered_building_ids": list(lock.ids),
        "runtime_contract": prepared["runtime_contract"],
        "roofer_image": ROOFER_IMAGE,
        "roofer_parameters": ROOFER_PARAMETERS,
        "prepare_receipt": {
            "path": rel(prepared["path"]),
            "sha256": prepared["sha256"],
        },
        "roofer_argv": prepared["roofer_argv"],
        "execution_receipt": {
            "path": rel(executed["path"]),
            "sha256": executed["sha256"],
        },
        "roofer_execution": executed["normalized"],
        "pointcloud_path": prepared["pointcloud"]["path"],
        "pointcloud_sha256": prepared["pointcloud"]["sha256"],
        "pointcloud": prepared["pointcloud"],
        "classification_receipt": prepared["classification_receipt"],
        "readout_lineage": classification["readout_lineage"],
        "crop_contract": classification["crop_contract"],
        "footprints": classification["roofprints"],
        "raw_jsonseq": dict(raw_inventory),
        "cityjson_path": merged_record["path"],
        "cityjson_sha256": merged_record["sha256"],
        "merged_cityjson": dict(merged_record),
    }


def finalize_roofer(
    prepare_path: Path,
    execution_receipt: Path,
    lock: PilotLock,
    *,
    expected_condition: str | None = None,
    expected_seed: int | None = None,
) -> tuple[Path, dict[str, Any]]:
    """Finalize or safely resume raw -> merged -> marker publication."""

    prepared = validate_roofer_prepare_receipt(
        prepare_path,
        lock,
        expected_condition=expected_condition,
        expected_seed=expected_seed,
    )
    executed = validate_roofer_execution_receipt(
        execution_receipt,
        prepared,
        expected_condition=expected_condition,
        expected_seed=expected_seed,
    )
    outputs = prepared["outputs"]
    cityjson = outputs["merged_cityjson_path"]
    marker = outputs["marker_path"]
    temporary = cityjson.with_name(f".{cityjson.name}.tmp")

    if marker.exists():
        if not marker.is_file() or marker.is_symlink():
            raise RuntimeError(f"completed Roofer marker is not a regular file: {marker}")
        if not cityjson.is_file() or cityjson.is_symlink():
            raise RuntimeError(
                "incomplete Roofer finalize state: marker exists without a regular merged CityJSON"
            )
        state = json.loads(marker.read_text(encoding="utf-8"))
        if not isinstance(state, dict):
            raise RuntimeError("completed Roofer marker root must be an object")
        validated = validate_roofer_marker(
            prepared["condition_id"], prepared["seed"], marker, cityjson, lock
        )
        require_equal(
            validated["execution_receipt_sha256"],
            executed["sha256"],
            "idempotent finalize execution receipt SHA256",
        )
        require_equal(
            validated["execution_receipt_path"],
            rel(executed["path"]),
            "idempotent finalize execution receipt path",
        )
        return cityjson, state

    if cityjson.exists() and temporary.exists():
        raise RuntimeError(
            "ambiguous Roofer finalize recovery state: merged CityJSON and merge temporary both exist"
        )

    raw_inventory = inventory_roofer_jsonseq(outputs["raw_jsonseq_dir"], lock)
    if cityjson.exists():
        if not cityjson.is_file() or cityjson.is_symlink():
            raise RuntimeError(
                "Roofer finalize recovery merged CityJSON is not a regular file"
            )
        merged_record = validate_merged_cityjson(cityjson, lock)
    elif temporary.exists():
        if not temporary.is_file() or temporary.is_symlink():
            raise RuntimeError(
                "Roofer finalize recovery temporary is not a regular file"
            )
        try:
            temporary_record = validate_merged_cityjson(temporary, lock)
            require_equal(
                temporary_record["child_count"],
                raw_inventory["child_count"],
                "recovery temporary/raw Roofer child count",
            )
        except Exception as exc:
            raise RuntimeError(
                f"Roofer finalize recovery temporary validation failed: {exc}"
            ) from exc
        require_equal(
            inventory_roofer_jsonseq(outputs["raw_jsonseq_dir"], lock),
            raw_inventory,
            "raw JSONSeq changed during temporary recovery",
        )
        os.replace(temporary, cityjson)
        merged_record = validate_merged_cityjson(cityjson, lock)
    else:
        raw_paths = [
            _resolve_declared_path(
                record["path"], declaring_file=Path(prepared["path"])
            )
            for record in raw_inventory["files"]
        ]
        w2 = load_module("pilot_1wave_w2_finalize", W2_SCRIPT)
        w2.combine_cityjsonseq(raw_paths, temporary)
        validate_merged_cityjson(temporary, lock)
        require_equal(
            inventory_roofer_jsonseq(outputs["raw_jsonseq_dir"], lock),
            raw_inventory,
            "raw JSONSeq changed during merge",
        )
        os.replace(temporary, cityjson)
        merged_record = validate_merged_cityjson(cityjson, lock)
    require_equal(
        merged_record["child_count"],
        raw_inventory["child_count"],
        "raw/merged Roofer child count",
    )
    state = _roofer_marker_payload(
        prepared, executed, raw_inventory, merged_record, lock
    )
    atomic_json(marker, state)
    validate_roofer_marker(
        prepared["condition_id"], prepared["seed"], marker, cityjson, lock
    )
    return cityjson, state


def load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def assert_val3dity_version() -> str:
    output = subprocess.check_output(
        ["val3dity", "--version"],
        cwd=REPO,
        text=True,
        stderr=subprocess.STDOUT,
    ).strip()
    match = re.search(r"\b(\d+\.\d+\.\d+)\b", output)
    if match is None or match.group(1) != VAL3DITY_VERSION:
        raise RuntimeError(f"val3dity version drift: {output}")
    return output


def run_val3dity(cityjson: Path, report: Path) -> tuple[dict[str, bool], int, str]:
    if report.exists() and report.stat().st_size > 0:
        raise RuntimeError(f"val3dity report already exists; stale reuse is forbidden: {report}")
    version = assert_val3dity_version()
    report.parent.mkdir(parents=True, exist_ok=True)
    process = subprocess.run(
        ["val3dity", cityjson.as_posix(), "--report", report.as_posix()],
        cwd=REPO,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    atomic_text(
        report.with_suffix(".log"),
        f"+ val3dity {cityjson} --report {report}\n{process.stdout or ''}",
    )
    if not report.is_file():
        raise RuntimeError(f"val3dity report missing exit={process.returncode}: {report}")
    return read_val3dity_report(report), int(process.returncode), version


def read_val3dity_report(report: Path) -> dict[str, bool]:
    payload = json.loads(report.read_text(encoding="utf-8"))
    return {
        str(feature["id"]): bool(feature.get("validity"))
        for feature in payload.get("features", [])
        if feature.get("id") is not None
    }


def load_locked_references(lock: PilotLock) -> dict[str, list[Any]]:
    metric_module = get_metric_module()
    with tempfile.TemporaryDirectory(prefix="p1w_lod2_") as temporary:
        directory = Path(temporary)
        for name, expected_sha in LOCKED_LOD2_SHA256.items():
            source = LOD2_DIR / name
            require_equal(sha256_file(source), expected_sha, f"LoD2 source SHA256 {name}")
            os.symlink(source, directory / name)
        return metric_module.parse_lod2_roofs(directory, set(lock.ids))


def cityjson_lod22_presence(path: Path, building_ids: Sequence[str]) -> dict[str, bool]:
    return get_baseline_module().cityjson_lod22_presence(path, building_ids)


def cityjson_reconstruction_state(
    path: Path, building_ids: Sequence[str]
) -> dict[str, dict[str, Any]]:
    """Preserve Roofer failure/fallback attributes and derive effective LoD2."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    cityobjects = payload.get("CityObjects") or {}
    geometry_lod22 = cityjson_lod22_presence(path, building_ids)
    output: dict[str, dict[str, Any]] = {}
    for building_id in building_ids:
        parent = cityobjects.get(building_id) or {}
        attributes = dict(parent.get("attributes") or {})
        if not attributes:
            for child_id in parent.get("children") or []:
                child_attributes = (cityobjects.get(child_id) or {}).get("attributes") or {}
                if child_attributes:
                    attributes.update(child_attributes)
        rf_success = attributes.get("rf_success")
        pointcloud_unusable = attributes.get("rf_pointcloud_unusable")
        extrusion_mode = str(attributes.get("rf_extrusion_mode", ""))
        fallback = extrusion_mode == "lod11_fallback"
        effective_lod2 = (
            bool(geometry_lod22[building_id])
            and rf_success is not False
            and pointcloud_unusable is not True
            and extrusion_mode not in {"skip", "lod11_fallback"}
        )
        output[building_id] = {
            "rf_success": rf_success,
            "rf_pointcloud_unusable": pointcloud_unusable,
            "rf_extrusion_mode": extrusion_mode,
            "lod1_fallback": fallback,
            "geometry_has_lod22": bool(geometry_lod22[building_id]),
            "has_lod22": effective_lod2,
        }
    return output


def _metric_bool(value: Any) -> bool | None:
    if value in (None, ""):
        return None
    return bool_value(value)


def _delta_numeric(value: Any, dense: Any) -> float | None:
    lhs = number(value)
    rhs = number(dense)
    if lhs is None or rhs is None:
        return None
    return lhs - rhs


def _dense_overlay(
    row: dict[str, Any],
    dense: Mapping[str, Any] | None,
    als: Mapping[str, Any] | None = None,
) -> None:
    rms = number(row.get("roof_rms_m"))
    row["rms_le_0p3"] = None if rms is None else rms <= 0.3
    row["rms_le_1p0"] = None if rms is None else rms <= 1.0
    als_rms = number(als.get("roof_rms_m")) if als is not None else None
    row["als_roof_rms_m"] = als_rms
    row["rms_gap_to_als_m"] = None if rms is None or als_rms is None else rms - als_rms
    if dense is None:
        for field in (
            "dense_has_lod22",
            "dense_val3dity_valid",
            "dense_face_count_ratio",
            "dense_face_count_ratio_abs_error",
            "dense_roof_rms_m",
            "dense_roof_hausdorff_m",
            "dense_roof_completeness",
            "delta_has_lod22",
            "delta_val3dity_valid",
            "delta_face_count_ratio_abs_error",
            "delta_roof_rms_m",
            "delta_roof_hausdorff_m",
            "delta_roof_completeness",
            "rms_lt_dense",
            "als_gap_closed_fraction",
        ):
            row[field] = None
        return
    row.update(
        {
            "dense_has_lod22": dense.get("has_lod22"),
            "dense_val3dity_valid": dense.get("val3dity_valid"),
            "dense_face_count_ratio": dense.get("face_count_ratio"),
            "dense_face_count_ratio_abs_error": dense.get("face_count_ratio_abs_error"),
            "dense_roof_rms_m": dense.get("roof_rms_m"),
            "dense_roof_hausdorff_m": dense.get("roof_hausdorff_m"),
            "dense_roof_completeness": dense.get("roof_completeness"),
        }
    )
    has_lod22 = _metric_bool(row.get("has_lod22"))
    dense_lod22 = _metric_bool(dense.get("has_lod22"))
    valid = _metric_bool(row.get("val3dity_valid"))
    dense_valid = _metric_bool(dense.get("val3dity_valid"))
    row["delta_has_lod22"] = None if has_lod22 is None or dense_lod22 is None else int(has_lod22) - int(dense_lod22)
    row["delta_val3dity_valid"] = None if valid is None or dense_valid is None else int(valid) - int(dense_valid)
    row["delta_face_count_ratio_abs_error"] = _delta_numeric(
        row.get("face_count_ratio_abs_error"), dense.get("face_count_ratio_abs_error")
    )
    row["delta_roof_rms_m"] = _delta_numeric(row.get("roof_rms_m"), dense.get("roof_rms_m"))
    row["delta_roof_hausdorff_m"] = _delta_numeric(
        row.get("roof_hausdorff_m"), dense.get("roof_hausdorff_m")
    )
    row["delta_roof_completeness"] = _delta_numeric(
        row.get("roof_completeness"), dense.get("roof_completeness")
    )
    dense_rms = number(dense.get("roof_rms_m"))
    row["rms_lt_dense"] = None if rms is None or dense_rms is None else rms < dense_rms
    denominator = None if dense_rms is None or als_rms is None else dense_rms - als_rms
    row["als_gap_closed_fraction"] = (
        None
        if rms is None or dense_rms is None or denominator is None or abs(denominator) <= 1e-12
        else (dense_rms - rms) / denominator
    )


def _base_score_row(
    lock: PilotLock,
    building_id: str,
    source_id: str,
    source_role: str,
    condition_id: str | None,
    seed: int | None,
) -> dict[str, Any]:
    building = lock.by_id[building_id]
    return {
        "schema_version": SCHEMA_VERSION,
        "row_type": "building_score",
        "source_id": source_id,
        "source_role": source_role,
        "condition_id": condition_id,
        "seed": seed,
        "building_id": building_id,
        "selection_rank": building.selection_rank,
        "is_core10": building.is_core10,
        "is_small_lt50m2": building.is_small_lt50m2,
        "observation_stratum": building.observation_stratum,
        "size_area_stratum": building.size_area_stratum,
    }


def score_cityjson(
    condition_id: str,
    seed: int,
    cityjson: Path,
    val3dity_report: Path,
    lock: PilotLock,
    references: Mapping[str, Sequence[Any]] | None = None,
    input_kind: str = "cityjson",
    input_path: Path | None = None,
    input_sha256: str | None = None,
    roofer_invocation_count: int = 0,
    run_provenance: Mapping[str, Any] | None = None,
    roofer_provenance: Mapping[str, Any] | None = None,
    score_marker_path: Path | None = None,
    val3dity_exit_code: int | None = None,
    val3dity_version_output: str | None = None,
) -> list[dict[str, Any]]:
    validate_condition_seed(condition_id, seed)
    if not cityjson.is_file() or not val3dity_report.is_file():
        raise FileNotFoundError(cityjson if not cityjson.is_file() else val3dity_report)
    metric_module = get_metric_module()
    baseline_module = get_baseline_module()
    reference_system = baseline_module.cityjson_crs(cityjson)
    if "25832" not in reference_system:
        raise RuntimeError(f"CityJSON CRS drift: {reference_system}")
    refs = dict(references) if references is not None else load_locked_references(lock)
    if set(refs) != set(lock.ids):
        raise RuntimeError("reference population mismatch")
    parsed = metric_module.parse_cityjson_roofs(cityjson, set(lock.ids))
    reconstruction = cityjson_reconstruction_state(cityjson, lock.ids)
    valid = read_val3dity_report(val3dity_report)
    missing_validity = sorted(set(lock.ids) - set(valid))
    if missing_validity:
        raise RuntimeError(f"val3dity report is missing locked buildings: {missing_validity}")
    cityjson_sha = sha256_file(cityjson)
    source_id = f"{condition_id}_seed{seed}"
    rows: list[dict[str, Any]] = []
    for building_id in lock.ids:
        prediction = list(parsed.get(building_id, []))
        reference = list(refs[building_id])
        comparison = metric_module.compare_building(reference, prediction)
        coverage = baseline_module.roof_xy_coverage(reference, prediction)
        state = reconstruction[building_id]
        model_faces = 1 if state["lod1_fallback"] else len(prediction)
        ref_faces = len(reference)
        face_ratio = model_faces / ref_faces if ref_faces else None
        completeness = coverage["roof_completeness"]
        row = _base_score_row(
            lock,
            building_id,
            source_id,
            CONDITION_ROLE[condition_id],
            condition_id,
            seed,
        )
        row.update(
            {
                "metric_available": True,
                "provenance_validated": bool(
                    run_provenance
                    and run_provenance.get("provenance_validated")
                    and roofer_provenance
                ),
                **{
                    field: (run_provenance or {}).get(field)
                    for field in (
                        "full_state_manifest_path",
                        "full_state_manifest_sha256",
                        "training_config_path",
                        "training_config_sha256",
                        "pilot_arm",
                        "segmentation_source",
                        "max_iter",
                        "last_completed_steps",
                        "process_completed_steps",
                        "process_completed",
                        "learning_runs_started",
                        "latest_full_checkpoint_path",
                        "latest_full_checkpoint_sha256",
                        "latest_full_checkpoint_steps",
                        "eligible_20k_full_state",
                        "partial",
                        "guard_status",
                        "guard_reason",
                    )
                },
                "input_kind": input_kind,
                "input_path": rel(input_path or cityjson),
                "input_sha256": input_sha256 or cityjson_sha,
                "cityjson_path": rel(cityjson),
                "cityjson_sha256": cityjson_sha,
                "roofer_invocation_count": int(
                    (roofer_provenance or {}).get(
                        "roofer_invocation_count", roofer_invocation_count
                    )
                ),
                "roofer_marker_path": (roofer_provenance or {}).get("roofer_marker_path"),
                "roofer_marker_sha256": (roofer_provenance or {}).get("roofer_marker_sha256"),
                "roofer_image": (roofer_provenance or {}).get("roofer_image"),
                "roofer_parameters": (roofer_provenance or {}).get("roofer_parameters"),
                "score_marker_path": rel(score_marker_path) if score_marker_path else None,
                "score_invocation_count": 1 if score_marker_path else 0,
                "val3dity_report": rel(val3dity_report),
                "val3dity_report_sha256": sha256_file(val3dity_report),
                "val3dity_version": VAL3DITY_VERSION,
                "val3dity_version_output": val3dity_version_output,
                "val3dity_exit_code": val3dity_exit_code,
                "rf_success": state["rf_success"],
                "rf_pointcloud_unusable": state["rf_pointcloud_unusable"],
                "rf_extrusion_mode": state["rf_extrusion_mode"],
                "lod1_fallback": state["lod1_fallback"],
                "geometry_has_lod22": state["geometry_has_lod22"],
                "has_lod22": state["has_lod22"],
                "val3dity_valid": bool(valid.get(building_id, False)),
                "roof_face_count_model": model_faces,
                "roof_face_count_ref": ref_faces,
                "face_count_ratio": face_ratio,
                "face_count_ratio_abs_error": None if face_ratio is None else abs(face_ratio - 1.0),
                "roof_rms_m": comparison["ref_rms_m"],
                "rms_le_0p3": (
                    comparison["ref_rms_m"] is not None
                    and comparison["ref_rms_m"] <= 0.3
                ),
                "rms_le_1p0": (
                    comparison["ref_rms_m"] is not None
                    and comparison["ref_rms_m"] <= 1.0
                ),
                "roof_hausdorff_m": comparison["ref_hausdorff_m"],
                "roof_distance_samples": comparison["ref_distance_samples"],
                "roof_completeness": completeness,
                "completeness_ge_0p8": None if completeness is None else completeness >= 0.8,
                "completeness_ge_0p9": None if completeness is None else completeness >= 0.9,
                "completeness_ge_0p95": None if completeness is None else completeness >= 0.95,
                "crs": CRS,
                "score_time_z_shift_m": 0.0,
                "reference_role": "LoD2 scoring only",
            }
        )
        rows.append(row)
    if len(rows) != EXPECTED_POPULATION:
        raise RuntimeError(f"candidate score row count drift: {len(rows)}")
    return rows


def score_bound_run_once(
    condition_id: str,
    seed: int,
    cityjson: Path,
    roofer_marker_path: Path,
    full_state_manifest_path: Path,
    output: Path,
    score_marker_path: Path,
    lock: PilotLock,
    *,
    guard_status: str,
    guard_reason: str = "",
    references: Mapping[str, Sequence[Any]] | None = None,
    val3dity_runner: Callable[[Path, Path], tuple[dict[str, bool], int, str]] = run_val3dity,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Score one bound run and invoke val3dity exactly once under a marker."""

    validate_condition_seed(condition_id, seed)
    for path, label in ((output, "score output"), (score_marker_path, "score marker")):
        if path.exists() and path.stat().st_size > 0:
            raise RuntimeError(f"{label} already exists and is nonempty: {path}")
    if score_marker_path.exists():
        raise RuntimeError(f"score marker path already exists: {score_marker_path}")
    report = output.with_suffix(".val3dity.json")
    if report.exists() and report.stat().st_size > 0:
        raise RuntimeError(f"stale external val3dity report is forbidden: {report}")

    run_provenance = validate_full_state_manifest(
        condition_id,
        seed,
        full_state_manifest_path,
        guard_status=guard_status,
        guard_reason=guard_reason,
    )
    roofer_provenance = validate_roofer_marker(
        condition_id, seed, roofer_marker_path, cityjson, lock
    )
    bound_readout_lineage = bind_readout_lineage_to_run(
        condition_id, seed, run_provenance, roofer_provenance
    )
    marker: dict[str, Any] = {
        "schema": SCORE_MARKER_SCHEMA,
        "condition_id": condition_id,
        "seed": seed,
        "state": "started",
        "started_utc": now(),
        "score_invocation_count": 1,
        "cityjson_path": rel(cityjson),
        "cityjson_sha256": sha256_file(cityjson),
        "roofer_marker_path": rel(roofer_marker_path),
        "roofer_marker_sha256": sha256_file(roofer_marker_path),
        "full_state_manifest_path": rel(full_state_manifest_path),
        "full_state_manifest_sha256": sha256_file(full_state_manifest_path),
        "classification_receipt_path": roofer_provenance[
            "classification_receipt_path"
        ],
        "classification_receipt_sha256": roofer_provenance[
            "classification_receipt_sha256"
        ],
        "readout_lineage": bound_readout_lineage,
        "guard_status": guard_status,
        "guard_reason": guard_reason,
        "val3dity_invocation_count": 0,
    }
    atomic_json(score_marker_path, marker)
    try:
        marker["val3dity_invocation_count"] = 1
        atomic_json(score_marker_path, marker)
        _validity, val_exit_code, version_output = val3dity_runner(cityjson, report)
        if not report.is_file():
            raise RuntimeError("val3dity runner returned without a report")
        rows = score_cityjson(
            condition_id,
            seed,
            cityjson,
            report,
            lock,
            references=references,
            input_kind="pointcloud",
            input_path=Path(str(roofer_provenance["pointcloud_path"])),
            input_sha256=str(roofer_provenance["pointcloud_sha256"]),
            roofer_invocation_count=1,
            run_provenance=run_provenance,
            roofer_provenance=roofer_provenance,
            score_marker_path=score_marker_path,
            val3dity_exit_code=val_exit_code,
            val3dity_version_output=version_output,
        )
        rows = attach_dense_controls(rows, load_control_rows(lock))
        atomic_csv(output, rows, SCORE_FIELDS)
        marker.update(
            {
                "state": "complete",
                "ended_utc": now(),
                "val3dity_report": rel(report),
                "val3dity_report_sha256": sha256_file(report),
                "val3dity_exit_code": int(val_exit_code),
                "val3dity_version": VAL3DITY_VERSION,
                "val3dity_version_output": version_output,
                "score_output_path": rel(output),
                "score_output_sha256": sha256_file(output),
                "score_output_row_count": len(rows),
                "eligible_20k_full_state": run_provenance["eligible_20k_full_state"],
                "partial": run_provenance["partial"],
            }
        )
        atomic_json(score_marker_path, marker)
        return rows, marker
    except Exception as exc:
        marker.update(
            {
                "state": "error",
                "ended_utc": now(),
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
        )
        atomic_json(score_marker_path, marker)
        raise


def _control_metric_values(source: Mapping[str, Any], prefix: str = "") -> dict[str, Any]:
    get = lambda name: source.get(prefix + name)  # noqa: E731
    face_ratio = number(get("face_count_ratio"))
    completeness = number(get("roof_completeness"))
    geometry_lod22 = _metric_bool(get("has_lod22"))
    extrusion_mode = str(get("rf_extrusion_mode") or "")
    fallback = bool_value(get("lod1_fallback")) or extrusion_mode == "lod11_fallback"
    effective_lod2 = (
        None
        if geometry_lod22 is None
        else geometry_lod22 and extrusion_mode != "skip" and not fallback
    )
    rms = number(get("roof_rms_m"))
    return {
        "rf_success": _metric_bool(get("rf_success")),
        "rf_pointcloud_unusable": _metric_bool(get("rf_pointcloud_unusable")),
        "rf_extrusion_mode": extrusion_mode,
        "lod1_fallback": fallback,
        "geometry_has_lod22": geometry_lod22,
        "has_lod22": effective_lod2,
        "val3dity_valid": _metric_bool(get("val3dity_valid")),
        "roof_face_count_model": number(get("roof_face_count_model")),
        "roof_face_count_ref": number(get("roof_face_count_ref")),
        "face_count_ratio": face_ratio,
        "face_count_ratio_abs_error": None if face_ratio is None else abs(face_ratio - 1.0),
        "roof_rms_m": rms,
        "rms_le_0p3": None if rms is None else rms <= 0.3,
        "rms_le_1p0": None if rms is None else rms <= 1.0,
        "roof_hausdorff_m": number(get("roof_hausdorff_m")),
        "roof_distance_samples": number(get("roof_distance_samples")),
        "roof_completeness": completeness,
        "completeness_ge_0p8": None if completeness is None else completeness >= 0.8,
        "completeness_ge_0p9": None if completeness is None else completeness >= 0.9,
        "completeness_ge_0p95": None if completeness is None else completeness >= 0.95,
    }


def load_control_rows(lock: PilotLock) -> list[dict[str, Any]]:
    """Load dense/ALS for 30 and prior MLS-default values without imputation."""

    require_equal(sha256_file(BASELINE_SCORES), BASELINE_SCORES_SHA256, "baseline score SHA256")
    require_equal(sha256_file(CHEAP_REFINE_SCORES), CHEAP_REFINE_SCORES_SHA256, "cheap-refine score SHA256")
    baseline_rows = read_csv(BASELINE_SCORES)
    by_role_id: dict[tuple[str, str], dict[str, str]] = {}
    for row in baseline_rows:
        role = str(row.get("role", ""))
        building_id = str(row.get("building_id", ""))
        if role in {"dense", "als"} and building_id in lock.ids:
            key = (role, building_id)
            if key in by_role_id:
                raise RuntimeError(f"duplicate baseline score: {key}")
            by_role_id[key] = row
    for role in ("dense", "als"):
        missing = [building_id for building_id in lock.ids if (role, building_id) not in by_role_id]
        if missing:
            raise RuntimeError(f"missing {role} controls: {missing}")

    rows: list[dict[str, Any]] = []
    dense_by_id: dict[str, dict[str, Any]] = {}
    als_by_id: dict[str, dict[str, Any]] = {}
    for role, source_id in (("dense", "dense_w2_1"), ("als", "als_w2_1")):
        for building_id in lock.ids:
            source = by_role_id[(role, building_id)]
            row = _base_score_row(lock, building_id, source_id, "control", None, None)
            row.update(
                {
                    "metric_available": True,
                    "input_kind": "existing_cityjson",
                    "input_path": source.get("cityjson_path"),
                    "input_sha256": source.get("cityjson_sha256"),
                    "cityjson_path": source.get("cityjson_path"),
                    "cityjson_sha256": source.get("cityjson_sha256"),
                    "roofer_invocation_count": 0,
                    "val3dity_report": source.get("val3dity_report"),
                    "val3dity_report_sha256": None,
                    "val3dity_version": VAL3DITY_VERSION,
                    **_control_metric_values(source),
                    "crs": CRS,
                    "score_time_z_shift_m": 0.0,
                    "reference_role": "LoD2 scoring only",
                }
            )
            rows.append(row)
            if role == "dense":
                dense_by_id[building_id] = row
            elif role == "als":
                als_by_id[building_id] = row

    cheap_rows = {
        str(row["building_id"]): row
        for row in read_csv(CHEAP_REFINE_SCORES)
        if row.get("condition_id") == CHEAP_REFINE_CONDITION and row.get("building_id") in lock.ids
    }
    for building_id in lock.ids:
        source = cheap_rows.get(building_id)
        row = _base_score_row(lock, building_id, "cheap_refine_mls_default", "control", None, None)
        if source is None:
            row.update(
                {
                    "metric_available": False,
                    "input_kind": "prior_c001_intersection",
                    "input_path": rel(CHEAP_REFINE_SCORES),
                    "input_sha256": CHEAP_REFINE_SCORES_SHA256,
                    "cityjson_path": None,
                    "cityjson_sha256": None,
                    "roofer_invocation_count": 0,
                    "val3dity_report": None,
                    "val3dity_report_sha256": None,
                    "val3dity_version": VAL3DITY_VERSION,
                    **{field: None for field in (
                        "rf_success", "rf_pointcloud_unusable", "rf_extrusion_mode",
                        "lod1_fallback", "geometry_has_lod22", "has_lod22",
                        "val3dity_valid", "roof_face_count_model",
                        "roof_face_count_ref", "face_count_ratio", "face_count_ratio_abs_error",
                        "roof_rms_m", "rms_le_0p3", "rms_le_1p0", "roof_hausdorff_m", "roof_distance_samples",
                        "roof_completeness", "completeness_ge_0p8", "completeness_ge_0p9",
                        "completeness_ge_0p95",
                    )},
                    "crs": CRS,
                    "score_time_z_shift_m": 0.0,
                    "reference_role": "LoD2 scoring only",
                }
            )
        else:
            row.update(
                {
                    "metric_available": True,
                    "input_kind": "prior_c001_intersection",
                    "input_path": source.get("refined_laz"),
                    "input_sha256": source.get("refined_laz_sha256"),
                    "cityjson_path": source.get("roofer_cityjson"),
                    "cityjson_sha256": source.get("roofer_cityjson_sha256"),
                    "roofer_invocation_count": 0,
                    "val3dity_report": source.get("val3dity_report"),
                    "val3dity_report_sha256": None,
                    "val3dity_version": VAL3DITY_VERSION,
                    **_control_metric_values(source),
                    "crs": CRS,
                    "score_time_z_shift_m": 0.0,
                    "reference_role": "LoD2 scoring only",
                }
            )
        rows.append(row)

    for row in rows:
        building_id = str(row["building_id"])
        _dense_overlay(row, dense_by_id.get(building_id), als_by_id.get(building_id))
    require_equal(len(rows), EXPECTED_POPULATION * 3, "control row count")
    require_equal(sum(bool(row["metric_available"]) for row in rows if row["source_id"] == "cheap_refine_mls_default"), 10, "cheap-refine intersection count")
    return rows


def attach_dense_controls(candidate_rows: Sequence[Mapping[str, Any]], controls: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    dense = {
        str(row["building_id"]): row
        for row in controls
        if row.get("source_id") == "dense_w2_1"
    }
    als = {
        str(row["building_id"]): row
        for row in controls
        if row.get("source_id") == "als_w2_1"
    }
    result: list[dict[str, Any]] = []
    for source in candidate_rows:
        row = dict(source)
        building_id = str(row["building_id"])
        _dense_overlay(row, dense.get(building_id), als.get(building_id))
        result.append(row)
    return result


def finite_values(rows: Sequence[Mapping[str, Any]], field: str) -> list[float]:
    result = [number(row.get(field)) for row in rows]
    return [float(value) for value in result if value is not None]


def _median(values: Sequence[float]) -> float | None:
    return float(np.median(np.asarray(values, dtype=float))) if values else None


def _maximum(values: Sequence[float]) -> float | None:
    return float(np.max(np.asarray(values, dtype=float))) if values else None


def _minimum(values: Sequence[float]) -> float | None:
    return float(np.min(np.asarray(values, dtype=float))) if values else None


def _all_nonworse(candidate: Sequence[float], dense: Sequence[float], lower_better: bool) -> bool:
    if len(candidate) != EXPECTED_POPULATION or len(dense) != EXPECTED_POPULATION:
        return False
    candidate_median = _median(candidate)
    dense_median = _median(dense)
    assert candidate_median is not None and dense_median is not None
    return candidate_median <= dense_median + 1e-12 if lower_better else candidate_median >= dense_median - 1e-12


def summarize_scores(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str, Any], list[Mapping[str, Any]]] = {}
    for row in rows:
        key = (
            str(row.get("source_id", "")),
            str(row.get("source_role", "")),
            str(row.get("condition_id") or ""),
            row.get("seed") or "",
        )
        groups.setdefault(key, []).append(row)
    output: list[dict[str, Any]] = []
    for (source_id, source_role, condition_id, seed), group in sorted(groups.items()):
        if len(group) != EXPECTED_POPULATION:
            raise RuntimeError(f"source population drift {source_id}/{seed}: {len(group)}")
        strata: dict[str, list[Mapping[str, Any]]] = {
            "all": list(group),
            "small_lt50m2": [row for row in group if bool_value(row.get("is_small_lt50m2"))],
            "non_small_ge50m2": [row for row in group if not bool_value(row.get("is_small_lt50m2"))],
        }
        for name in ("low", "mid", "high"):
            strata[f"observation_{name}"] = [
                row for row in group if row.get("observation_stratum") == name
            ]
            strata[f"size_area_{name}"] = [
                row for row in group if row.get("size_area_stratum") == name
            ]
        for observation in ("low", "mid", "high"):
            for size_area in ("low", "mid", "high"):
                subset = [
                    row
                    for row in group
                    if row.get("observation_stratum") == observation
                    and row.get("size_area_stratum") == size_area
                ]
                if subset:
                    strata[f"observation_{observation}__size_area_{size_area}"] = subset

        def consistent_run_value(field: str) -> Any:
            values = {
                str(row.get(field))
                for row in group
                if row.get(field) not in (None, "")
            }
            if len(values) > 1:
                raise RuntimeError(f"run provenance drift {source_id}/{seed}/{field}: {sorted(values)}")
            return next(iter(values)) if values else None

        provenance_value = consistent_run_value("provenance_validated")
        eligible_value = consistent_run_value("eligible_20k_full_state")
        partial_value = consistent_run_value("partial")
        guard_value = consistent_run_value("guard_status")
        last_steps_value = consistent_run_value("last_completed_steps")
        process_steps_value = consistent_run_value("process_completed_steps")
        for stratum, subset in strata.items():
            rms = finite_values(subset, "roof_rms_m")
            hausdorff = finite_values(subset, "roof_hausdorff_m")
            face = finite_values(subset, "face_count_ratio")
            face_target_deviation = (
                None if not face else abs(float(np.median(np.asarray(face, dtype=float))) - 1.0)
            )
            completeness = finite_values(subset, "roof_completeness")
            als_approach = finite_values(subset, "als_gap_closed_fraction")
            rms_gap_to_als = finite_values(subset, "rms_gap_to_als_m")
            available = [row for row in subset if bool_value(row.get("metric_available"))]
            valid_values = [_metric_bool(row.get("val3dity_valid")) for row in available]
            lod2_values = [_metric_bool(row.get("has_lod22")) for row in available]
            valid_values = [value for value in valid_values if value is not None]
            lod2_values = [value for value in lod2_values if value is not None]
            rms_lt = [_metric_bool(row.get("rms_lt_dense")) for row in available]
            rms_lt = [value for value in rms_lt if value is not None]
            threshold_counts = {
                threshold: sum(value >= threshold for value in completeness)
                for threshold in COMPLETENESS_THRESHOLDS
            }
            rms_spec_counts = {
                threshold: sum(value <= threshold for value in rms)
                for threshold in RMS_SPEC_THRESHOLDS_M
            }
            summary = {
                "schema_version": SCHEMA_VERSION,
                "row_type": "source_stratum_summary",
                "source_id": source_id,
                "source_role": source_role,
                "condition_id": condition_id or None,
                "seed": seed or None,
                "stratum": stratum,
                "population_count": len(subset),
                "metric_available_count": len(available),
                "rms_measurable_count": len(rms),
                "roof_rms_median_m": _median(rms),
                "roof_rms_max_m": _maximum(rms),
                "rms_le_0p3_count": rms_spec_counts[0.3],
                "rms_le_0p3_rate": rms_spec_counts[0.3] / len(rms) if rms else None,
                "rms_le_1p0_count": rms_spec_counts[1.0],
                "rms_le_1p0_rate": rms_spec_counts[1.0] / len(rms) if rms else None,
                "als_approach_measurable_count": len(als_approach),
                "als_gap_closed_fraction_median": _median(als_approach),
                "rms_gap_to_als_m_median": _median(rms_gap_to_als),
                "hausdorff_measurable_count": len(hausdorff),
                "roof_hausdorff_median_m": _median(hausdorff),
                "roof_hausdorff_max_m": _maximum(hausdorff),
                "face_count_ratio_measurable_count": len(face),
                "face_count_ratio_median": _median(face),
                "face_count_ratio_target_abs_deviation": face_target_deviation,
                "completeness_measurable_count": len(completeness),
                "roof_completeness_min": _minimum(completeness),
                "roof_completeness_median": _median(completeness),
                "completeness_ge_0p8_count": threshold_counts[0.8],
                "completeness_ge_0p8_rate": threshold_counts[0.8] / len(completeness) if completeness else None,
                "completeness_ge_0p9_count": threshold_counts[0.9],
                "completeness_ge_0p9_rate": threshold_counts[0.9] / len(completeness) if completeness else None,
                "completeness_ge_0p95_count": threshold_counts[0.95],
                "completeness_ge_0p95_rate": threshold_counts[0.95] / len(completeness) if completeness else None,
                "val3dity_valid_count": sum(bool(value) for value in valid_values),
                "val3dity_valid_rate": sum(bool(value) for value in valid_values) / len(valid_values) if valid_values else None,
                "lod2_count": sum(bool(value) for value in lod2_values),
                "lod2_rate": sum(bool(value) for value in lod2_values) / len(lod2_values) if lod2_values else None,
                "rms_lt_dense_measurable_count": len(rms_lt),
                "rms_lt_dense_count": sum(bool(value) for value in rms_lt),
                "rms_lt_dense_rate": sum(bool(value) for value in rms_lt) / len(rms_lt) if rms_lt else None,
                "dense_bar_median_m": DENSE_BAR_MEDIAN_M,
                "run_provenance_validated": (
                    None if provenance_value is None else bool_value(provenance_value)
                ),
                "run_eligible_20k_full_state": (
                    None if eligible_value is None else bool_value(eligible_value)
                ),
                "run_partial": None if partial_value is None else bool_value(partial_value),
                "run_guard_status": guard_value,
                "run_last_completed_steps": (
                    None if last_steps_value is None else int(last_steps_value)
                ),
                "run_process_completed_steps": (
                    None if process_steps_value is None else int(process_steps_value)
                ),
                "rule_a_rms_below_dense_bar": None,
                "rule_b_structural_improvement": None,
                "rule_c_all_metrics_nonworse": None,
                "rule_d_completeness_floor_0p9": None,
                "rule_d_completeness_floor_0p8_sensitivity": None,
                "rule_d_completeness_floor_0p95_sensitivity": None,
                "rule_abcd": None,
            }
            if source_role in {"honest", "seg_upperbound"} and stratum == "all":
                dense_rms = finite_values(subset, "dense_roof_rms_m")
                dense_haus = finite_values(subset, "dense_roof_hausdorff_m")
                dense_face = finite_values(subset, "dense_face_count_ratio")
                dense_face_target_deviation = (
                    None
                    if not dense_face
                    else abs(float(np.median(np.asarray(dense_face, dtype=float))) - 1.0)
                )
                candidate_valid = sum(bool(value) for value in valid_values)
                dense_valid = sum(bool_value(row.get("dense_val3dity_valid")) for row in subset)
                candidate_lod2 = sum(bool(value) for value in lod2_values)
                dense_lod2 = sum(bool_value(row.get("dense_has_lod22")) for row in subset)
                face_improved = (
                    len(face) == EXPECTED_POPULATION
                    and len(dense_face) == EXPECTED_POPULATION
                    and face_target_deviation is not None
                    and dense_face_target_deviation is not None
                    and face_target_deviation < dense_face_target_deviation - 1e-12
                )
                rms_median = _median(rms)
                rule_a = (
                    len(rms) == EXPECTED_POPULATION
                    and rms_median is not None
                    and rms_median < DENSE_BAR_MEDIAN_M
                )
                rule_b = face_improved or candidate_valid > dense_valid or candidate_lod2 > dense_lod2
                dense_completeness_by_id = {
                    str(row["building_id"]): number(row.get("dense_roof_completeness"))
                    for row in subset
                }

                def completeness_floor(threshold: float) -> bool:
                    if len(completeness) != EXPECTED_POPULATION:
                        return False
                    for row in subset:
                        value = number(row.get("roof_completeness"))
                        dense_value = dense_completeness_by_id[str(row["building_id"])]
                        if value is None or dense_value is None or value + 1e-12 < max(dense_value, threshold):
                            return False
                    return True

                rule_c = (
                    _all_nonworse(rms, dense_rms, lower_better=True)
                    and _all_nonworse(hausdorff, dense_haus, lower_better=True)
                    and len(face) == EXPECTED_POPULATION
                    and len(dense_face) == EXPECTED_POPULATION
                    and face_target_deviation is not None
                    and dense_face_target_deviation is not None
                    and face_target_deviation <= dense_face_target_deviation + 1e-12
                    and candidate_valid >= dense_valid
                    and candidate_lod2 >= dense_lod2
                    and completeness_floor(0.0)
                )
                rule_d_08 = completeness_floor(0.8)
                rule_d_09 = completeness_floor(0.9)
                rule_d_095 = completeness_floor(0.95)
                summary.update(
                    {
                        "rule_a_rms_below_dense_bar": rule_a,
                        "rule_b_structural_improvement": rule_b,
                        "rule_c_all_metrics_nonworse": rule_c,
                        "rule_d_completeness_floor_0p9": rule_d_09,
                        "rule_d_completeness_floor_0p8_sensitivity": rule_d_08,
                        "rule_d_completeness_floor_0p95_sensitivity": rule_d_095,
                        "rule_abcd": rule_a and rule_b and rule_c and rule_d_09,
                    }
                )
            output.append(summary)
    return output


def build_seg_gap(
    rows: Sequence[Mapping[str, Any]], lock: PilotLock | None = None
) -> list[dict[str, Any]]:
    lock = lock or load_pilot_lock()
    indexed: dict[tuple[str, int, str], Mapping[str, Any]] = {}
    for source in rows:
        if source.get("condition_id") not in {"04a", "04b"} or source.get("seed") in (None, ""):
            continue
        key = (
            str(source.get("condition_id")),
            int(source.get("seed")),
            str(source.get("building_id")),
        )
        if key in indexed:
            raise RuntimeError(f"duplicate segmentation-gap score row: {key}")
        indexed[key] = source

    def run_state(source: Mapping[str, Any] | None) -> str:
        if source is None:
            return "missing"
        if bool_value(source.get("partial")):
            return "partial"
        if bool_value(source.get("eligible_20k_full_state")):
            return "complete_20k"
        return "present_unbound"

    output: list[dict[str, Any]] = []
    for seed in EXPECTED_SEEDS:
        for building_id in lock.ids:
            vision = indexed.get(("04a", seed, building_id))
            gt = indexed.get(("04b", seed, building_id))
            if vision is None and gt is None:
                pair_state = "missing_both"
            elif vision is None:
                pair_state = "missing_vision"
            elif gt is None:
                pair_state = "missing_gt"
            elif bool_value(vision.get("partial")) or bool_value(gt.get("partial")):
                pair_state = "partial_pair"
            elif not bool_value(vision.get("metric_available")) or not bool_value(gt.get("metric_available")):
                pair_state = "metric_missing"
            else:
                pair_state = "available_pair"
            row = {
                "schema_version": SCHEMA_VERSION,
                "row_type": "building_gap",
                "seed": seed,
                "stratum": "building",
                "building_id": building_id,
                "pair_state": pair_state,
                "vision_run_state": run_state(vision),
                "gt_run_state": run_state(gt),
                "vision_partial": None if vision is None else bool_value(vision.get("partial")),
                "gt_partial": None if gt is None else bool_value(gt.get("partial")),
                "vision_metric_available": None if vision is None else bool_value(vision.get("metric_available")),
                "gt_metric_available": None if gt is None else bool_value(gt.get("metric_available")),
            }
            for name in (
                "roof_rms_m",
                "roof_hausdorff_m",
                "face_count_ratio_abs_error",
                "roof_completeness",
            ):
                vision_value = None if vision is None else number(vision.get(name))
                gt_value = None if gt is None else number(gt.get(name))
                row[f"vision_{name}"] = vision_value
                row[f"gt_{name}"] = gt_value
                row[f"delta_gt_minus_vision_{name}"] = (
                    None if vision_value is None or gt_value is None else gt_value - vision_value
                )
            for name in ("val3dity_valid", "has_lod22"):
                vision_value = None if vision is None else _metric_bool(vision.get(name))
                gt_value = None if gt is None else _metric_bool(gt.get(name))
                row[f"vision_{name}"] = vision_value
                row[f"gt_{name}"] = gt_value
                row[f"delta_gt_minus_vision_{name}"] = (
                    None if vision_value is None or gt_value is None else int(gt_value) - int(vision_value)
                )
            output.append(row)
    require_equal(len(output), len(EXPECTED_SEEDS) * EXPECTED_POPULATION, "segmentation gap row count")
    return output


def build_winner_rows(summary_rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    by_condition_seed = {
        (str(row.get("condition_id")), int(row.get("seed"))): row
        for row in summary_rows
        if row.get("source_role") == "honest"
        and row.get("stratum") == "all"
        and row.get("condition_id") in HONEST_CONDITIONS
        and row.get("seed") not in (None, "")
    }
    output: list[dict[str, Any]] = []
    for condition_id in HONEST_CONDITIONS:
        seed_rows = {seed: by_condition_seed.get((condition_id, seed)) for seed in EXPECTED_SEEDS}
        complete = [
            row
            for row in seed_rows.values()
            if row is not None
            and int(row.get("rms_measurable_count", 0)) == EXPECTED_POPULATION
        ]
        eligible_complete = [
            row for row in complete if bool_value(row.get("run_eligible_20k_full_state"))
        ]
        abcd = [row for row in eligible_complete if bool_value(row.get("rule_abcd"))]
        rms_values = {
            seed: number(row.get("roof_rms_median_m")) if row is not None else None
            for seed, row in seed_rows.items()
        }
        eligible = len(abcd) == len(EXPECTED_SEEDS)
        worst = max(value for value in rms_values.values() if value is not None) if eligible else None
        output.append(
            {
                "schema_version": SCHEMA_VERSION,
                "row_type": "honest_condition_numeric_rule",
                "condition_id": condition_id,
                "honest_candidate": True,
                "expected_seed_count": len(EXPECTED_SEEDS),
                "complete_seed_count": len(complete),
                "eligible_20k_seed_count": len(eligible_complete),
                "rule_abcd_seed_count": len(abcd),
                "seed_1001_rule_abcd": bool_value(seed_rows[1001].get("rule_abcd")) if seed_rows[1001] else None,
                "seed_1002_rule_abcd": bool_value(seed_rows[1002].get("rule_abcd")) if seed_rows[1002] else None,
                "seed_1001_roof_rms_median_m": rms_values[1001],
                "seed_1002_roof_rms_median_m": rms_values[1002],
                "worst_seed_roof_rms_median_m": worst,
                "eligible_two_seed_rule": eligible,
                "minimum_worst_rms_order": None,
                "co_minimum_count": 0,
                "is_minimum_worst_rms": False,
            }
        )
    eligible_rows = [row for row in output if bool(row["eligible_two_seed_rule"])]
    eligible_rows.sort(key=lambda row: float(row["worst_seed_roof_rms_median_m"]))
    if eligible_rows:
        minimum = float(eligible_rows[0]["worst_seed_roof_rms_median_m"])
        co_minimum = [
            row
            for row in eligible_rows
            if math.isclose(
                float(row["worst_seed_roof_rms_median_m"]),
                minimum,
                rel_tol=0.0,
                abs_tol=1e-12,
            )
        ]
        for row in output:
            row["co_minimum_count"] = len(co_minimum)
        distinct_values: list[float] = []
        for row in eligible_rows:
            value = float(row["worst_seed_roof_rms_median_m"])
            matching_rank = next(
                (
                    index + 1
                    for index, seen in enumerate(distinct_values)
                    if math.isclose(value, seen, rel_tol=0.0, abs_tol=1e-12)
                ),
                None,
            )
            if matching_rank is None:
                distinct_values.append(value)
                matching_rank = len(distinct_values)
            row["minimum_worst_rms_order"] = matching_rank
            row["is_minimum_worst_rms"] = matching_rank == 1
    if any(row["condition_id"] == UPPERBOUND_CONDITION for row in output):
        raise AssertionError("04b entered honest-only winner rows")
    require_equal([row["condition_id"] for row in output], list(HONEST_CONDITIONS), "winner condition set")
    return output


def initialize_output_schemas(output_dir: Path, lock: PilotLock) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    for name in OUTPUT_NAMES.values():
        path = output_dir / name
        if path.exists() and path.stat().st_size > 0:
            raise RuntimeError(f"refusing to overwrite existing nonempty output: {path}")
    schemas = {
        "scores": SCORE_FIELDS,
        "summary": SUMMARY_FIELDS,
        "seg_gap": SEG_GAP_FIELDS,
        "loss_shares": LOSS_SHARE_FIELDS,
        "winner": WINNER_FIELDS,
    }
    for key, fields in schemas.items():
        atomic_csv(output_dir / OUTPUT_NAMES[key], [], fields)
    outputs = {
        OUTPUT_NAMES[key]: {
            "row_count": 0,
            "fields": list(fields),
            "sha256": sha256_file(output_dir / OUTPUT_NAMES[key]),
        }
        for key, fields in schemas.items()
    }
    manifest = {
        "schema": "jointbuildgs.pilot_1wave.manifest.v1",
        "created_utc": now(),
        "task_id": TASK_ID,
        "run_id": RUN_ID,
        "state": "schema_initialized",
        "crs": CRS,
        "learning_runs_started": 0,
        "roofer_invocations_started": 0,
        "score_rows": 0,
        "guard_triggered": False,
        "partial_run_count": 0,
        "selection_lock": {
            "population_count": len(lock.ids),
            "small_lt50m2_count": sum(item.is_small_lt50m2 for item in lock.buildings),
            "non_small_ge50m2_count": sum(not item.is_small_lt50m2 for item in lock.buildings),
            "selection_sha256": lock.selection_sha256,
            "ordered_ids_sha256": lock.ordered_ids_sha256,
            "scoring_bbox": list(lock.scoring_bbox),
            "pilot_set_path": rel(PILOT_SET),
            "pilot_set_sha256": lock.pilot_set_sha256,
            "pilot_manifest_path": rel(PILOT_MANIFEST),
            "pilot_manifest_sha256": lock.pilot_manifest_sha256,
            "dense_bar_median_m": lock.dense_bar_median_m,
            "observation_size_strata_source_path": rel(OBSERVATION_STRATA_SOURCE),
            "observation_size_strata_source_sha256": OBSERVATION_STRATA_SOURCE_SHA256,
        },
        "conditions": {
            "honest": list(HONEST_CONDITIONS),
            "seg_upperbound": UPPERBOUND_CONDITION,
            "seeds": list(EXPECTED_SEEDS),
            "pilot_arm": CONDITION_PILOT_ARM,
            "segmentation_source": CONDITION_SEGMENTATION_SOURCE,
        },
        "run_states": {
            f"{condition}_seed{seed}": {
                "condition_id": condition,
                "seed": seed,
                "status": "not_scored",
                "learning_runs_started": 0,
                "eligible_20k_full_state": False,
                "partial": None,
                "guard_status": None,
                "pilot_arm": CONDITION_PILOT_ARM[condition],
                "segmentation_source": CONDITION_SEGMENTATION_SOURCE[condition],
                "training_config": None,
                "full_state_manifest": None,
                "latest_full_checkpoint": None,
                "roofer_marker": None,
                "score_marker": None,
            }
            for condition in ALL_CONDITIONS
            for seed in EXPECTED_SEEDS
        },
        "metrics": {
            "distance_definition": rel(METRIC_SCRIPT),
            "distance_definition_sha256": METRIC_SCRIPT_SHA256,
            "completeness_definition_source": rel(BASELINE_SCRIPT),
            "completeness_definition_source_sha256": BASELINE_SCRIPT_SHA256,
            "roof_completeness_definition": (
                "area(union(model roof XY) intersect union(reference roof XY)) / "
                "area(union(reference roof XY))"
            ),
            "face_count_ratio_definition": "model RoofSurface count / reference RoofSurface count",
            "face_count_ratio_target": 1.0,
            "completeness_thresholds": list(COMPLETENESS_THRESHOLDS),
            "rms_spec_thresholds_m": list(RMS_SPEC_THRESHOLDS_M),
            "als_gap_closed_fraction_definition": (
                "(dense_roof_rms_m - candidate_roof_rms_m) / "
                "(dense_roof_rms_m - als_roof_rms_m); 0=dense and 1=ALS"
            ),
            "effective_lod2_definition": (
                "lod=2.2 geometry present AND rf_success is not false AND "
                "rf_pointcloud_unusable is not true AND rf_extrusion_mode is neither skip nor lod11_fallback"
            ),
            "summary_denominators": {
                "all": EXPECTED_POPULATION,
                "small_lt50m2": sum(item.is_small_lt50m2 for item in lock.buildings),
                "non_small_ge50m2": sum(not item.is_small_lt50m2 for item in lock.buildings),
                "observation": {
                    name: sum(item.observation_stratum == name for item in lock.buildings)
                    for name in ("low", "mid", "high")
                },
                "size_area": {
                    name: sum(item.size_area_stratum == name for item in lock.buildings)
                    for name in ("low", "mid", "high")
                },
                "observation_x_size": {
                    f"{observation}__{size_area}": sum(
                        item.observation_stratum == observation
                        and item.size_area_stratum == size_area
                        for item in lock.buildings
                    )
                    for observation in ("low", "mid", "high")
                    for size_area in ("low", "mid", "high")
                    if any(
                        item.observation_stratum == observation
                        and item.size_area_stratum == size_area
                        for item in lock.buildings
                    )
                },
                "metric_rates": "metric-specific measurable_count; missing values are excluded",
                "completeness_threshold_rates": "completeness_measurable_count",
            },
            "val3dity_version": VAL3DITY_VERSION,
        },
        "numeric_rule": {
            "candidate_conditions": list(HONEST_CONDITIONS),
            "excluded_condition": UPPERBOUND_CONDITION,
            "rms_and_hausdorff_aggregate": "median across locked 30; lower is nonworse",
            "face_count_aggregate": "abs(median(model/reference) - 1); lower is nonworse",
            "validity_and_lod2_aggregate": "count across locked 30; higher is nonworse",
            "completeness_gate": "per building >= max(dense building value, threshold)",
            "primary_completeness_threshold": 0.9,
            "sensitivity_completeness_thresholds": [0.8, 0.95],
            "two_seed_order": "minimum of max(seed1001 RMS median, seed1002 RMS median)",
            "eligibility_gate": (
                "both seeds require max_iter=20000, process_completed_steps=20000, "
                "last_completed_steps=20000, and verified latest 20000 full checkpoint"
            ),
            "tie_rule": "all values equal within absolute tolerance 1e-12 are co-minima",
        },
        "controls": {
            "dense": {"path": rel(BASELINE_SCORES), "sha256": BASELINE_SCORES_SHA256, "expected_count": 30},
            "als": {"path": rel(BASELINE_SCORES), "sha256": BASELINE_SCORES_SHA256, "expected_count": 30},
            "cheap_refine_mls_default": {
                "path": rel(CHEAP_REFINE_SCORES),
                "sha256": CHEAP_REFINE_SCORES_SHA256,
                "condition_id": CHEAP_REFINE_CONDITION,
                "selected_population_measured_count": 10,
                "selected_population_missing_count": 20,
                "missing_value_policy": "empty; no substitution",
            },
        },
        "roofer": {"image": ROOFER_IMAGE, "parameters": ROOFER_PARAMETERS, "assembly_count_per_condition_seed": 1},
        "outputs": outputs,
        "interpretation_or_verdict": None,
    }
    atomic_json(output_dir / OUTPUT_NAMES["manifest"], manifest)
    return manifest


def _row_path(value: Any) -> Path:
    text = str(value or "").strip()
    if not text:
        raise RuntimeError("candidate provenance contains an empty path")
    path = Path(text)
    return path.resolve() if path.is_absolute() else (REPO / path).resolve()


def _csv_normalized(row: Mapping[str, Any]) -> dict[str, str]:
    return {field: str(format_value(row.get(field))) for field in SCORE_FIELDS}


def _group_candidate_rows(
    rows: Sequence[Mapping[str, Any]], lock: PilotLock
) -> dict[tuple[str, int], list[dict[str, Any]]]:
    groups: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for source in rows:
        condition = str(source.get("condition_id") or "")
        seed_value = source.get("seed")
        if condition not in ALL_CONDITIONS or seed_value in (None, ""):
            raise RuntimeError("aggregate input may contain candidate rows only")
        seed = int(seed_value)
        validate_condition_seed(condition, seed)
        groups.setdefault((condition, seed), []).append(dict(source))
    for (condition, seed), group in groups.items():
        ids = [str(row.get("building_id")) for row in group]
        require_equal(len(group), EXPECTED_POPULATION, f"candidate group count {condition}/{seed}")
        require_equal(len(set(ids)), EXPECTED_POPULATION, f"candidate unique IDs {condition}/{seed}")
        require_equal(set(ids), set(lock.ids), f"candidate population {condition}/{seed}")
    return groups


def _validate_candidate_group(
    condition: str,
    seed: int,
    group: Sequence[Mapping[str, Any]],
    lock: PilotLock,
) -> dict[str, Any]:
    """Validate a 30-row run against its score, Roofer, and full-state markers."""

    if len(group) != EXPECTED_POPULATION:
        raise RuntimeError(f"candidate group is not complete: {condition}/{seed}")
    for row in group:
        require_equal(row.get("source_id"), f"{condition}_seed{seed}", "candidate source_id")
        require_equal(row.get("source_role"), CONDITION_ROLE[condition], "candidate source_role")
        if not bool_value(row.get("provenance_validated")):
            raise RuntimeError(f"candidate row is not provenance validated: {condition}/{seed}")

    def one(field: str) -> str:
        values = {
            "" if row.get(field) in (None, "") else str(row.get(field))
            for row in group
        }
        if len(values) != 1 or not next(iter(values)):
            raise RuntimeError(f"candidate run field drift/empty {condition}/{seed}/{field}")
        return next(iter(values))

    score_marker_path = _row_path(one("score_marker_path"))
    score_marker = validate_score_marker(condition, seed, score_marker_path)
    marker_rows = read_csv(Path(score_marker["score_output_resolved"]))
    marker_by_id = {str(row["building_id"]): row for row in marker_rows}
    for row in group:
        building_id = str(row["building_id"])
        if marker_by_id.get(building_id) != _csv_normalized(row):
            raise RuntimeError(
                f"candidate row differs from score-marker output: {condition}/{seed}/{building_id}"
            )

    guard_status = one("guard_status")
    guard_reasons = {str(row.get("guard_reason") or "") for row in group}
    if len(guard_reasons) != 1:
        raise RuntimeError(f"candidate guard reason drift: {condition}/{seed}")
    full_state_path = _row_path(one("full_state_manifest_path"))
    run_provenance = validate_full_state_manifest(
        condition,
        seed,
        full_state_path,
        guard_status=guard_status,
        guard_reason=next(iter(guard_reasons)),
    )
    require_equal(
        run_provenance["full_state_manifest_sha256"],
        one("full_state_manifest_sha256"),
        "candidate full-state SHA256",
    )
    require_equal(
        bool_value(one("eligible_20k_full_state")),
        bool(run_provenance["eligible_20k_full_state"]),
        "candidate 20k eligibility",
    )
    cityjson_path = _row_path(one("cityjson_path"))
    roofer_marker_path = _row_path(one("roofer_marker_path"))
    roofer = validate_roofer_marker(condition, seed, roofer_marker_path, cityjson_path, lock)
    require_equal(roofer["roofer_marker_sha256"], one("roofer_marker_sha256"), "candidate Roofer SHA256")
    require_equal(score_marker.get("full_state_manifest_sha256"), one("full_state_manifest_sha256"), "score/full-state binding")
    require_equal(score_marker.get("roofer_marker_sha256"), one("roofer_marker_sha256"), "score/Roofer binding")
    return {
        **run_provenance,
        "roofer_marker": {
            "path": roofer["roofer_marker_path"],
            "sha256": roofer["roofer_marker_sha256"],
        },
        "score_marker": {
            "path": score_marker["score_marker_path"],
            "sha256": score_marker["score_marker_sha256"],
        },
    }


def write_numeric_outputs(
    output_dir: Path, rows: Sequence[Mapping[str, Any]], lock: PilotLock
) -> dict[str, Any]:
    """Upsert whole condition/seed runs without deleting prior completed runs."""

    manifest_path = output_dir / OUTPUT_NAMES["manifest"]
    if not manifest_path.exists():
        initialize_output_schemas(output_dir, lock)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    require_equal(manifest.get("schema"), "jointbuildgs.pilot_1wave.manifest.v1", "aggregate manifest schema")
    score_path = output_dir / OUTPUT_NAMES["scores"]
    existing_all = read_csv(score_path) if score_path.is_file() else []
    existing_candidates = [
        row for row in existing_all if row.get("condition_id") in ALL_CONDITIONS
    ]
    existing_groups = _group_candidate_rows(existing_candidates, lock) if existing_candidates else {}
    incoming_groups = _group_candidate_rows(rows, lock) if rows else {}
    existing_records = {
        key: _validate_candidate_group(*key, group, lock)
        for key, group in existing_groups.items()
    }
    incoming_records = {
        key: _validate_candidate_group(*key, group, lock)
        for key, group in incoming_groups.items()
    }

    merged_groups = dict(existing_groups)
    for key, incoming in incoming_groups.items():
        existing = existing_groups.get(key)
        if existing is not None:
            existing_eligible = bool(existing_records[key]["eligible_20k_full_state"])
            existing_normalized = sorted(
                (_csv_normalized(row) for row in existing), key=lambda row: row["building_id"]
            )
            incoming_normalized = sorted(
                (_csv_normalized(row) for row in incoming), key=lambda row: row["building_id"]
            )
            if existing_eligible and existing_normalized != incoming_normalized:
                raise RuntimeError(f"refusing to replace completed 20k run: {key}")
            if existing_eligible:
                continue
            old_steps = int(existing_records[key]["last_completed_steps"])
            new_steps = int(incoming_records[key]["last_completed_steps"])
            if new_steps < old_steps:
                raise RuntimeError(f"refusing candidate checkpoint regression {key}: {new_steps} < {old_steps}")
            if new_steps == old_steps and existing_normalized != incoming_normalized:
                raise RuntimeError(f"refusing ambiguous same-step candidate replacement: {key}")
        merged_groups[key] = [dict(row) for row in incoming]

    # Explicit deletion guard: every pre-existing run key must survive the merge.
    if not set(existing_groups).issubset(merged_groups):
        raise RuntimeError("aggregate merge would delete existing candidate runs")

    controls = load_control_rows(lock)
    candidates: list[dict[str, Any]] = []
    run_records: dict[tuple[str, int], dict[str, Any]] = {}
    for key in sorted(merged_groups, key=lambda value: (ALL_CONDITIONS.index(value[0]), value[1])):
        group = attach_dense_controls(merged_groups[key], controls)
        candidates.extend(sorted(group, key=lambda row: int(row["selection_rank"])))
        run_records[key] = _validate_candidate_group(*key, group, lock)
    all_rows = [*controls, *candidates]
    summary = summarize_scores(all_rows)
    seg_gap = build_seg_gap(candidates, lock)
    winner = build_winner_rows(summary)
    atomic_csv(score_path, all_rows, SCORE_FIELDS)
    atomic_csv(output_dir / OUTPUT_NAMES["summary"], summary, SUMMARY_FIELDS)
    atomic_csv(output_dir / OUTPUT_NAMES["seg_gap"], seg_gap, SEG_GAP_FIELDS)
    atomic_csv(output_dir / OUTPUT_NAMES["winner"], winner, WINNER_FIELDS)
    loss_path = output_dir / OUTPUT_NAMES["loss_shares"]
    if not loss_path.exists():
        atomic_csv(loss_path, [], LOSS_SHARE_FIELDS)

    run_states: dict[str, dict[str, Any]] = {}
    for condition in ALL_CONDITIONS:
        for seed in EXPECTED_SEEDS:
            key = (condition, seed)
            record = run_records.get(key)
            name = f"{condition}_seed{seed}"
            if record is None:
                run_states[name] = {
                    "condition_id": condition,
                    "seed": seed,
                    "status": "not_scored",
                    "learning_runs_started": 0,
                    "eligible_20k_full_state": False,
                    "partial": None,
                    "guard_status": None,
                    "pilot_arm": CONDITION_PILOT_ARM[condition],
                    "segmentation_source": CONDITION_SEGMENTATION_SOURCE[condition],
                    "training_config": None,
                    "full_state_manifest": None,
                    "latest_full_checkpoint": None,
                    "roofer_marker": None,
                    "score_marker": None,
                }
                continue
            run_states[name] = {
                "condition_id": condition,
                "seed": seed,
                "status": (
                    "scored_complete_20k"
                    if record["eligible_20k_full_state"]
                    else "scored_partial"
                ),
                "learning_runs_started": int(record["learning_runs_started"]),
                "eligible_20k_full_state": bool(record["eligible_20k_full_state"]),
                "partial": bool(record["partial"]),
                "guard_status": record["guard_status"],
                "guard_reason": record["guard_reason"],
                "max_iter": int(record["max_iter"]),
                "last_completed_steps": int(record["last_completed_steps"]),
                "process_completed": bool(record["process_completed"]),
                "process_completed_steps": record["process_completed_steps"],
                "pilot_arm": record["pilot_arm"],
                "segmentation_source": record["segmentation_source"],
                "plane_region_mask_manifest": record["plane_region_mask_manifest"],
                "training_config": {
                    "path": record["training_config_path"],
                    "sha256": record["training_config_sha256"],
                },
                "full_state_manifest": {
                    "path": record["full_state_manifest_path"],
                    "sha256": record["full_state_manifest_sha256"],
                },
                "latest_full_checkpoint": {
                    "path": record["latest_full_checkpoint_path"],
                    "sha256": record["latest_full_checkpoint_sha256"],
                    "completed_steps": int(record["latest_full_checkpoint_steps"]),
                },
                "roofer_marker": record["roofer_marker"],
                "score_marker": record["score_marker"],
            }

    manifest.update(
        {
            "updated_utc": now(),
            "state": "numeric_outputs_written",
            "run_states": run_states,
            "learning_runs_started": sum(
                int(record["learning_runs_started"]) for record in run_records.values()
            ),
            "learning_condition_seed_count": len(run_records),
            "roofer_invocations_started": len(run_records),
            "score_invocations_completed": len(run_records),
            "guard_triggered": any(
                record["guard_status"] != "not_triggered" for record in run_records.values()
            ),
            "partial_run_count": sum(bool(record["partial"]) for record in run_records.values()),
            "score_rows": len(all_rows),
            "candidate_score_rows": len(candidates),
            "summary_rows": len(summary),
            "seg_gap_rows": len(seg_gap),
            "winner_rows": len(winner),
        }
    )
    manifest["outputs"] = {
        name: {
            "sha256": sha256_file(output_dir / name),
            "row_count": len(read_csv(output_dir / name)),
        }
        for name in OUTPUT_NAMES.values()
        if name.endswith(".csv")
    }
    atomic_json(manifest_path, manifest)
    return manifest


def cli() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check-lock")
    init = sub.add_parser("init-schemas")
    init.add_argument("--output-dir", type=Path, default=RUN_DIR)
    footprints = sub.add_parser("prepare-roofprints")
    footprints.add_argument("--output", type=Path, required=True)
    validate_cloud = sub.add_parser("validate-pointcloud")
    validate_cloud.add_argument("--pointcloud", type=Path, required=True)
    prepare_roofer_parser = sub.add_parser("prepare-roofer")
    prepare_roofer_parser.add_argument(
        "--condition", choices=ALL_CONDITIONS, required=True
    )
    prepare_roofer_parser.add_argument(
        "--seed", choices=EXPECTED_SEEDS, type=int, required=True
    )
    prepare_roofer_parser.add_argument("--pointcloud", type=Path, required=True)
    prepare_roofer_parser.add_argument(
        "--classification-receipt", type=Path, required=True
    )
    prepare_roofer_parser.add_argument("--output-dir", type=Path, required=True)
    finalize_roofer_parser = sub.add_parser("finalize-roofer")
    finalize_roofer_parser.add_argument(
        "--condition", choices=ALL_CONDITIONS, required=True
    )
    finalize_roofer_parser.add_argument(
        "--seed", choices=EXPECTED_SEEDS, type=int, required=True
    )
    finalize_roofer_parser.add_argument(
        "--prepare-receipt", type=Path, required=True
    )
    finalize_roofer_parser.add_argument(
        "--execution-receipt", type=Path, required=True
    )
    score = sub.add_parser("score-cityjson")
    score.add_argument("--condition", choices=ALL_CONDITIONS, required=True)
    score.add_argument("--seed", choices=EXPECTED_SEEDS, type=int, required=True)
    score.add_argument("--cityjson", type=Path, required=True)
    score.add_argument("--roofer-marker", type=Path, required=True)
    score.add_argument("--full-state-manifest", type=Path, required=True)
    score.add_argument("--output", type=Path, required=True)
    score.add_argument("--score-marker", type=Path)
    score.add_argument("--guard-status", choices=GUARD_STATUSES, required=True)
    score.add_argument("--guard-reason", default="")
    aggregate = sub.add_parser("aggregate-scores")
    aggregate.add_argument("--output-dir", type=Path, default=RUN_DIR)
    aggregate.add_argument("--run-score", type=Path, action="append", required=True)
    return parser.parse_args()


def main() -> None:
    args = cli()
    lock = load_pilot_lock()
    if args.command == "check-lock":
        print(json.dumps({"population_count": len(lock.ids), "selection_sha256": lock.selection_sha256, "scoring_bbox": lock.scoring_bbox}))
        return
    if args.command == "init-schemas":
        initialize_output_schemas(args.output_dir, lock)
        return
    if args.command == "prepare-roofprints":
        print(json.dumps(materialize_locked_roofprints(lock, args.output), ensure_ascii=False))
        return
    if args.command == "validate-pointcloud":
        print(json.dumps(validate_roofer_pointcloud(args.pointcloud), ensure_ascii=False))
        return
    if args.command == "prepare-roofer":
        prepared = prepare_roofer(
            args.condition,
            args.seed,
            args.pointcloud,
            args.classification_receipt,
            args.output_dir,
            lock,
        )
        print(
            json.dumps(
                {
                    "prepare_receipt": rel(prepared["path"]),
                    "prepare_receipt_sha256": prepared["sha256"],
                    "roofer_argv": prepared["roofer_argv"],
                },
                ensure_ascii=False,
            )
        )
        return
    if args.command == "finalize-roofer":
        cityjson, state = finalize_roofer(
            args.prepare_receipt,
            args.execution_receipt,
            lock,
            expected_condition=args.condition,
            expected_seed=args.seed,
        )
        print(
            json.dumps(
                {
                    "cityjson": rel(cityjson),
                    "cityjson_sha256": state["cityjson_sha256"],
                    "roofer_marker": rel(
                        args.prepare_receipt.parent / "roofer_invocation.json"
                    ),
                },
                ensure_ascii=False,
            )
        )
        return
    if args.command == "score-cityjson":
        marker = args.score_marker or args.output.with_suffix(".score.json")
        score_bound_run_once(
            args.condition,
            args.seed,
            args.cityjson,
            args.roofer_marker,
            args.full_state_manifest,
            args.output,
            marker,
            lock,
            guard_status=args.guard_status,
            guard_reason=args.guard_reason,
        )
        print(json.dumps({"score_output": rel(args.output), "score_marker": rel(marker)}))
        return
    if args.command == "aggregate-scores":
        candidate_rows: list[dict[str, str]] = []
        for path in args.run_score:
            candidate_rows.extend(read_csv(path))
        write_numeric_outputs(args.output_dir, candidate_rows, lock)
        return
    raise AssertionError(args.command)


if __name__ == "__main__":
    main()
