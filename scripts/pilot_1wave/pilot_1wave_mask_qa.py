#!/usr/bin/env python3
"""Read-only P1W 04a/04b mask audit and evaluation-only pair QA.

The ``audit`` command validates both immutable BinaryMaskSet inventories and
prints a JSON report without writing.  ``write-qa`` repeats the same validation
and atomically writes a per-view CSV plus a provenance manifest in a separate
output directory.  Neither command performs inference, training, optimization,
or any mutation of the source masks/training configuration.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
from typing import Any, Mapping, Sequence

import numpy as np


REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.stage2.pilot_mask_schema import (  # noqa: E402
    BinaryMaskSet,
    FORBIDDEN_GT_NUMERIC_ARRAYS,
    MaskPurpose,
    MaskSchemaError,
    MaskSource,
    sha256_file,
)


RUN_ID = "20260721_pilot_1wave"
EXPECTED_VIEW_COUNT = 481
QA_SCHEMA = "jointbuildgs.pilot_1wave.mask_pair_qa.v1"
AUDIT_SCHEMA = "jointbuildgs.pilot_1wave.mask_pair_audit.v1"
DEFAULT_PREP = REPO / "phases/p2-gsjso/runs" / RUN_ID / "prep_artifacts"
DEFAULT_04A = DEFAULT_PREP / "plane_masks_04a/mask_manifest.json"
DEFAULT_04B = DEFAULT_PREP / "plane_masks_04b/mask_manifest.json"
DEFAULT_REFERENCE = DEFAULT_PREP / "photo_support_masks/mask_manifest.json"
DEFAULT_OUTPUT = DEFAULT_PREP / "plane_masks_04a_vs_04b_qa"
PRODUCER_LOCK = REPO / "phases/p2-gsjso/configs/pilot_1wave/pilot_1wave_mask_producer_lock.json"
EXPECTED_04A_PRODUCER_SCHEMA = (
    "jointbuildgs.pilot_1wave.04a_mask_producer_manifest.v1"
)
EXPECTED_04B_PRODUCER_SCHEMA = (
    "jointbuildgs.pilot_1wave.04b_mask_producer_manifest.v1"
)
EXPECTED_04B_FORBIDDEN_ARCHIVE_ARRAYS = frozenset(
    {
        "roof_z",
        "hit_depth",
        "face_ids",
        "building_ids",
        "semantic_class",
        "primitive_ids",
    }
)
CSV_FIELDS = (
    "view_id",
    "height",
    "width",
    "total_pixels",
    "positive_pixels_04a_vision",
    "positive_pixels_04b_gt",
    "intersection_pixels",
    "union_pixels",
    "false_positive_pixels",
    "false_negative_pixels",
    "iou",
    "precision",
    "recall",
    "recall_defined",
    "empty_04a",
    "empty_04b",
)


class MaskQaError(RuntimeError):
    """The mask pair is incomplete, inconsistent, or unsafe to compare."""


def require_docker() -> None:
    if not Path("/.dockerenv").exists():
        raise MaskQaError("P1W mask QA must run inside the pinned Docker runtime")


def _load_json_object(path: Path) -> dict[str, Any]:
    if path.is_symlink():
        raise MaskQaError(f"JSON input must not be a symlink: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MaskQaError(f"cannot read JSON input {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise MaskQaError(f"JSON input must be an object: {path}")
    return value


def _producer_manifest_path(mask_manifest: Path) -> Path:
    return mask_manifest.parent / "producer_manifest.json"


def _check_producer_manifest(
    path: Path,
    mask_manifest: Path,
    *,
    schema: str,
    source: MaskSource,
    expected_view_count: int,
) -> dict[str, Any]:
    value = _load_json_object(path)
    if stat.S_IMODE(path.stat().st_mode) != 0o444:
        raise MaskQaError(f"producer manifest must be immutable mode 0444: {path}")
    if stat.S_IMODE(mask_manifest.stat().st_mode) != 0o444:
        raise MaskQaError(f"mask manifest must be immutable mode 0444: {mask_manifest}")
    if value.get("schema") != schema or value.get("run_id") != RUN_ID:
        raise MaskQaError(f"producer schema/run_id mismatch: {path}")
    if value.get("source") != source.value:
        raise MaskQaError(f"producer source mismatch: {path}")
    if value.get("mask_manifest") != mask_manifest.name:
        raise MaskQaError(f"producer mask-manifest path mismatch: {path}")
    if value.get("mask_manifest_sha256") != sha256_file(mask_manifest):
        raise MaskQaError(f"producer mask-manifest SHA mismatch: {path}")
    if value.get("view_count") != expected_view_count:
        raise MaskQaError(f"producer view count mismatch: {path}")
    if value.get("learning_runs_started") != 0:
        raise MaskQaError(f"producer must report learning_runs_started=0: {path}")
    if value.get("producer_lock_sha256") != sha256_file(PRODUCER_LOCK):
        raise MaskQaError(f"producer lock SHA mismatch: {path}")
    return value


def _validate_inventory_contract(
    masks_04a: BinaryMaskSet,
    masks_04b: BinaryMaskSet,
    reference: BinaryMaskSet,
    *,
    expected_view_count: int,
) -> list[str]:
    if masks_04a.purpose is not MaskPurpose.PLANE_REGION:
        raise MaskQaError("04a mask purpose must be plane_region")
    if masks_04a.source is not MaskSource.VISION_GROUNDEDSAM_ROOF:
        raise MaskQaError("04a mask source must be vision_groundedsam_roof")
    if masks_04b.purpose is not MaskPurpose.PLANE_REGION:
        raise MaskQaError("04b mask purpose must be plane_region")
    if masks_04b.source is not MaskSource.LOD2_ROOFSURFACE_GT_UPPERBOUND:
        raise MaskQaError("04b mask source must be lod2_roofsurface_gt_upperbound")
    if reference.purpose is not MaskPurpose.PHOTO_SUPPORT:
        raise MaskQaError("geometry-reference mask purpose must be photo_support")
    if reference.source is not MaskSource.LOD2_GROUNDSURFACE_XY_SFM_HEIGHT:
        raise MaskQaError(
            "geometry-reference source must be lod2_groundsurface_xy_sfm_height"
        )
    if masks_04a.consumer_arms != ("04a_plane_medium_vision",):
        raise MaskQaError("04a consumer arm differs from the locked arm")
    if masks_04b.consumer_arms != ("04b_plane_medium_gt_upperbound",):
        raise MaskQaError("04b consumer arm differs from the locked arm")

    view_ids = sorted(masks_04a.records)
    if len(view_ids) != expected_view_count:
        raise MaskQaError(
            f"04a view count differs: {len(view_ids)} != {expected_view_count}"
        )
    for label, mask_set in (("04b", masks_04b), ("reference", reference)):
        other = sorted(mask_set.records)
        if other != view_ids:
            missing = sorted(set(view_ids) - set(other))
            outside = sorted(set(other) - set(view_ids))
            raise MaskQaError(
                f"{label} view inventory differs; missing={missing}, outside={outside}"
            )
    for view_id in view_ids:
        hashes = {
            masks_04a.records[view_id].geometry_sha256,
            masks_04b.records[view_id].geometry_sha256,
            reference.records[view_id].geometry_sha256,
        }
        if len(hashes) != 1:
            raise MaskQaError(f"geometry SHA mismatch for view {view_id}")
        if masks_04a.records[view_id].shape != masks_04b.records[view_id].shape:
            raise MaskQaError(f"04a/04b mask shape mismatch for view {view_id}")
        if masks_04a.records[view_id].shape != reference.records[view_id].shape:
            raise MaskQaError(f"mask/reference shape mismatch for view {view_id}")
    return view_ids


def _safe_ratio(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return float(numerator) / float(denominator)


def _numeric_summary(values: Sequence[int | float]) -> dict[str, int | float]:
    array = np.asarray(values, dtype=np.float64)
    if array.ndim != 1 or array.size == 0 or not np.isfinite(array).all():
        raise MaskQaError("numeric summary requires finite non-empty values")
    return {
        "count": int(array.size),
        "sum": float(array.sum()),
        "min": float(array.min()),
        "p25": float(np.percentile(array, 25.0)),
        "median": float(np.percentile(array, 50.0)),
        "p75": float(np.percentile(array, 75.0)),
        "p95": float(np.percentile(array, 95.0)),
        "max": float(array.max()),
        "mean": float(array.mean()),
    }


def audit_and_compare(
    manifest_04a: Path,
    manifest_04b: Path,
    reference_manifest: Path,
    *,
    expected_view_count: int = EXPECTED_VIEW_COUNT,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Fully load two mask sets, validate provenance, and compute QA rows."""

    manifest_04a = Path(manifest_04a)
    manifest_04b = Path(manifest_04b)
    reference_manifest = Path(reference_manifest)
    masks_04a = BinaryMaskSet(manifest_04a)
    masks_04b = BinaryMaskSet(manifest_04b)
    reference = BinaryMaskSet(reference_manifest)
    view_ids = _validate_inventory_contract(
        masks_04a,
        masks_04b,
        reference,
        expected_view_count=expected_view_count,
    )
    producer_04a_path = _producer_manifest_path(manifest_04a)
    producer_04b_path = _producer_manifest_path(manifest_04b)
    producer_04a = _check_producer_manifest(
        producer_04a_path,
        manifest_04a,
        schema=EXPECTED_04A_PRODUCER_SCHEMA,
        source=MaskSource.VISION_GROUNDEDSAM_ROOF,
        expected_view_count=expected_view_count,
    )
    producer_04b = _check_producer_manifest(
        producer_04b_path,
        manifest_04b,
        schema=EXPECTED_04B_PRODUCER_SCHEMA,
        source=MaskSource.LOD2_ROOFSURFACE_GT_UPPERBOUND,
        expected_view_count=expected_view_count,
    )
    if producer_04a.get("gt_read_for_selection") is not False:
        raise MaskQaError("04a producer must report gt_read_for_selection=false")
    if producer_04a.get("gt_iou_computed") is not False:
        raise MaskQaError("04a producer must report gt_iou_computed=false")
    expected_04a_attempts = {
        "prior_inference_runs_started": 1,
        "inference_runs_started": 2,
        "inference_runs_successful": 1,
        "inference_runs_failed": 1,
    }
    for key, expected in expected_04a_attempts.items():
        if producer_04a.get(key) != expected:
            raise MaskQaError(f"04a producer attempt counter mismatch: {key}")
    producer_04a_audit = producer_04a.get("audit")
    if not isinstance(producer_04a_audit, list) or len(producer_04a_audit) != expected_view_count:
        raise MaskQaError("04a producer audit does not cover the exact view inventory")
    for radius in (1, 0):
        count_key = f"small_core_{radius}px_fallback_count"
        ids_key = f"small_core_{radius}px_fallback_building_ids"
        event_key = f"small_core_{radius}px_fallback_building_event_count"
        view_count_key = f"small_core_{radius}px_fallback_view_count"
        view_ids_key = f"small_core_{radius}px_fallback_view_ids"
        rows_with_fallback = [
            row for row in producer_04a_audit
            if isinstance(row, dict) and int(row.get(count_key, -1)) > 0
        ]
        if any(len(row.get(ids_key, [])) != int(row.get(count_key, -1)) for row in rows_with_fallback):
            raise MaskQaError(f"04a {radius}px fallback per-view IDs/count differ")
        if producer_04a.get(event_key) != sum(int(row[count_key]) for row in rows_with_fallback):
            raise MaskQaError(f"04a {radius}px fallback aggregate event count differs")
        if producer_04a.get(view_count_key) != len(rows_with_fallback):
            raise MaskQaError(f"04a {radius}px fallback view count differs")
        if producer_04a.get(view_ids_key) != [row["view_id"] for row in rows_with_fallback]:
            raise MaskQaError(f"04a {radius}px fallback view IDs differ")
    if producer_04b.get("archive_arrays") != ["mask:bool"]:
        raise MaskQaError("04b producer archive contract must be mask:bool only")
    if set(producer_04b.get("forbidden_archive_arrays", [])) != set(
        EXPECTED_04B_FORBIDDEN_ARCHIVE_ARRAYS
    ):
        raise MaskQaError("04b forbidden archive-array disclosure differs")
    if producer_04b.get("inference_runs_started") != 1:
        raise MaskQaError("04b producer must report exactly one raycast run")
    if producer_04b.get("selected_building_roof_geometry_coverage_complete") is not True:
        raise MaskQaError("04b selected-building RoofSurface coverage is incomplete")
    if producer_04b.get("selected_building_roof_geometry_coverage_count") != 30:
        raise MaskQaError("04b selected-building RoofSurface coverage count must be 30")

    rows: list[dict[str, Any]] = []
    empty_04b: list[str] = []
    total_04a = 0
    total_04b = 0
    total_intersection = 0
    total_union = 0
    total_false_positive = 0
    total_false_negative = 0
    producer_audit_raw = producer_04b.get("audit")
    if not isinstance(producer_audit_raw, list):
        raise MaskQaError("04b producer audit must be a list")
    producer_audit = {
        item.get("view_id"): item
        for item in producer_audit_raw
        if isinstance(item, dict) and isinstance(item.get("view_id"), str)
    }
    if len(producer_audit) != expected_view_count:
        raise MaskQaError("04b producer audit does not cover the exact view inventory")

    for view_id in view_ids:
        mask_04a = masks_04a.load(view_id)
        mask_04b = masks_04b.load(view_id)
        if mask_04a.shape != mask_04b.shape:
            raise MaskQaError(f"loaded 04a/04b shape mismatch for view {view_id}")
        positive_04a = int(mask_04a.sum())
        positive_04b = int(mask_04b.sum())
        if positive_04a <= 0:
            raise MaskQaError(f"04a per-view mask is empty: {view_id}")
        if positive_04b == 0:
            empty_04b.append(view_id)
        intersection = int(np.logical_and(mask_04a, mask_04b).sum())
        union = int(np.logical_or(mask_04a, mask_04b).sum())
        false_positive = positive_04a - intersection
        false_negative = positive_04b - intersection
        height, width = (int(mask_04a.shape[0]), int(mask_04a.shape[1]))
        pixels = height * width
        audit_row = producer_audit.get(view_id)
        if audit_row is None:
            raise MaskQaError(f"04b producer audit is missing view {view_id}")
        if audit_row.get("roof_mask_pixels") != positive_04b:
            raise MaskQaError(f"04b producer positive-pixel audit differs: {view_id}")
        if audit_row.get("empty_view") is not (positive_04b == 0):
            raise MaskQaError(f"04b producer empty-view audit differs: {view_id}")
        rows.append(
            {
                "view_id": view_id,
                "height": height,
                "width": width,
                "total_pixels": pixels,
                "positive_pixels_04a_vision": positive_04a,
                "positive_pixels_04b_gt": positive_04b,
                "intersection_pixels": intersection,
                "union_pixels": union,
                "false_positive_pixels": false_positive,
                "false_negative_pixels": false_negative,
                "iou": _safe_ratio(intersection, union),
                "precision": _safe_ratio(intersection, positive_04a),
                "recall": _safe_ratio(intersection, positive_04b),
                "recall_defined": positive_04b > 0,
                "empty_04a": False,
                "empty_04b": positive_04b == 0,
            }
        )
        total_04a += positive_04a
        total_04b += positive_04b
        total_intersection += intersection
        total_union += union
        total_false_positive += false_positive
        total_false_negative += false_negative

    if total_04a <= 0 or total_04b <= 0:
        raise MaskQaError("04a and 04b must each have positive aggregate pixels")
    if producer_04b.get("total_roof_mask_pixels") != total_04b:
        raise MaskQaError("04b producer aggregate positive pixels differ")
    if producer_04b.get("empty_view_count") != len(empty_04b):
        raise MaskQaError("04b producer empty-view count differs")
    if producer_04b.get("empty_view_ids") != empty_04b:
        raise MaskQaError("04b producer empty-view IDs differ")

    recall_values = [float(row["recall"]) for row in rows if row["recall"] is not None]
    audit = {
        "schema": AUDIT_SCHEMA,
        "run_id": RUN_ID,
        "mode": "read_only_evaluation_preflight",
        "view_count": len(rows),
        "expected_view_count": expected_view_count,
        "view_inventory_exact": True,
        "geometry_sha_matches_04a_04b_reference": True,
        "shape_matches_04a_04b": True,
        "source_04a": masks_04a.source.value,
        "source_04b": masks_04b.source.value,
        "purpose_04a": masks_04a.purpose.value,
        "purpose_04b": masks_04b.purpose.value,
        "binary_archives_fully_loaded": True,
        "observed_archive_arrays": ["mask:bool"],
        "forbidden_gt_numeric_arrays": list(FORBIDDEN_GT_NUMERIC_ARRAYS),
        "forbidden_gt_arrays_found": [],
        "forbidden_gt_array_gate_passed": True,
        "aggregate_positive_gate_04a": total_04a > 0,
        "aggregate_positive_gate_04b": total_04b > 0,
        "empty_view_policy_04a": "forbidden_per_view",
        "empty_view_policy_04b": "allowed_per_view_but_aggregate_must_be_positive",
        "empty_view_count_04a": 0,
        "empty_view_count_04b": len(empty_04b),
        "empty_view_ids_04b": empty_04b,
        "input_manifests": {
            "04a": {
                "path": str(manifest_04a.resolve()),
                "sha256": sha256_file(manifest_04a),
                "inventory_sha256": masks_04a.inventory_sha256,
                "producer_manifest": str(producer_04a_path.resolve()),
                "producer_manifest_sha256": sha256_file(producer_04a_path),
            },
            "04b": {
                "path": str(manifest_04b.resolve()),
                "sha256": sha256_file(manifest_04b),
                "inventory_sha256": masks_04b.inventory_sha256,
                "producer_manifest": str(producer_04b_path.resolve()),
                "producer_manifest_sha256": sha256_file(producer_04b_path),
            },
            "geometry_reference": {
                "path": str(reference_manifest.resolve()),
                "sha256": sha256_file(reference_manifest),
                "inventory_sha256": reference.inventory_sha256,
            },
        },
        "metric_direction": "04a vision prediction versus 04b LoD2-GT upper-bound reference",
        "metric_denominator_policy": {
            "iou": "intersection/union; union is positive because 04a is nonempty",
            "precision": "intersection/04a_positive_pixels",
            "recall": "intersection/04b_positive_pixels; null for an empty 04b view",
        },
        "aggregate": {
            "positive_pixels_04a_vision": total_04a,
            "positive_pixels_04b_gt": total_04b,
            "intersection_pixels": total_intersection,
            "union_pixels": total_union,
            "false_positive_pixels": total_false_positive,
            "false_negative_pixels": total_false_negative,
            "micro_iou": _safe_ratio(total_intersection, total_union),
            "micro_precision": _safe_ratio(total_intersection, total_04a),
            "micro_recall": _safe_ratio(total_intersection, total_04b),
            "macro_iou": float(np.mean([float(row["iou"]) for row in rows])),
            "macro_precision": float(
                np.mean([float(row["precision"]) for row in rows])
            ),
            "macro_recall_defined_views": float(np.mean(recall_values)),
            "macro_recall_defined_view_count": len(recall_values),
        },
        "per_view_positive_pixel_summary": {
            "04a_vision": _numeric_summary(
                [int(row["positive_pixels_04a_vision"]) for row in rows]
            ),
            "04b_gt": _numeric_summary(
                [int(row["positive_pixels_04b_gt"]) for row in rows]
            ),
        },
        "inference_runs_started_by_qa": 0,
        "learning_runs_started": 0,
        "optimizer_steps": 0,
        "training_config_read": False,
        "training_config_modified": False,
        "source_masks_modified": False,
        "evaluation_only": True,
    }
    return audit, rows


def _csv_scalar(value: Any) -> str | int:
    if value is None:
        return ""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, float):
        return format(value, ".12g")
    if isinstance(value, (str, int)):
        return value
    raise TypeError(f"unsupported CSV value: {type(value).__name__}")


def _git_head() -> str:
    process = subprocess.run(
        [
            "git",
            "-c",
            f"safe.directory={REPO}",
            "-C",
            str(REPO),
            "rev-parse",
            "HEAD",
        ],
        check=False,
        text=True,
        capture_output=True,
    )
    if process.returncode != 0:
        raise MaskQaError("cannot resolve git HEAD for QA provenance")
    return process.stdout.strip()


def write_qa(
    output: Path,
    audit: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
) -> Path:
    """Atomically publish QA outputs without altering any input artifact."""

    output = Path(output)
    if output.exists() or output.is_symlink():
        raise MaskQaError(f"QA output must not already exist: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{output.name}.staging-", dir=output.parent)
    )
    try:
        csv_path = staging / "pilot_1wave_04a_vs_04b_mask_qa.csv"
        with csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, lineterminator="\n")
            writer.writeheader()
            for row in rows:
                writer.writerow({key: _csv_scalar(row[key]) for key in CSV_FIELDS})
        manifest = {
            "schema": QA_SCHEMA,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "run_id": RUN_ID,
            "mode": "evaluation_only_mask_pair_qa",
            "git_head": _git_head(),
            "qa_script": str(Path(__file__).resolve()),
            "qa_script_sha256": sha256_file(Path(__file__)),
            "csv": csv_path.name,
            "csv_sha256": sha256_file(csv_path),
            "row_count": len(rows),
            "audit": dict(audit),
            "inference_runs_started_by_qa": 0,
            "learning_runs_started": 0,
            "optimizer_steps": 0,
            "training_config_read": False,
            "training_config_modified": False,
            "source_masks_modified": False,
            "evaluation_only": True,
        }
        manifest_path = staging / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        os.chmod(csv_path, 0o444)
        os.chmod(manifest_path, 0o444)
        os.chmod(staging, 0o555)
        os.replace(staging, output)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return output / "manifest.json"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("audit", "write-qa"):
        command = sub.add_parser(name)
        command.add_argument("--manifest-04a", type=Path, default=DEFAULT_04A)
        command.add_argument("--manifest-04b", type=Path, default=DEFAULT_04B)
        command.add_argument(
            "--geometry-reference-manifest", type=Path, default=DEFAULT_REFERENCE
        )
        command.add_argument(
            "--expected-view-count", type=int, default=EXPECTED_VIEW_COUNT
        )
        if name == "write-qa":
            command.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
            command.add_argument("--execute-evaluation-only", action="store_true")
    args = parser.parse_args(argv)
    require_docker()
    audit, rows = audit_and_compare(
        args.manifest_04a,
        args.manifest_04b,
        args.geometry_reference_manifest,
        expected_view_count=args.expected_view_count,
    )
    if args.command == "audit":
        print(json.dumps(audit, ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    if not args.execute_evaluation_only:
        parser.error("write-qa requires --execute-evaluation-only")
    manifest = write_qa(args.output, audit, rows)
    print(
        json.dumps(
            {
                "status": "complete",
                "manifest": str(manifest.resolve()),
                "row_count": len(rows),
                "learning_runs_started": 0,
                "optimizer_steps": 0,
            },
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
