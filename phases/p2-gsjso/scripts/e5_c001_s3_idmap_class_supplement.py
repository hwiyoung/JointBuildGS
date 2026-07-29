#!/usr/bin/env python3
"""S3-A 07-14 T0-1 supplement: class/ID agreement and frozen crop repaint.

This is deliberately a *supplement* to ``e5_c001_s3_semantic_regions.py``.
It never reads the cached region arrays as a source and never creates or
rewrites a semantic-region NPZ.  Instead it:

1. fail-closes on the canonical manifest, every declared input hash, the 428
   cache hashes, and the 428 fixed semantic-label hashes;
2. reuses the producer's actual-source raycast (geoid 48.0 m,
   ``shift_z=556.0``) in memory for exactly 428 views;
3. compares the fixed class-roof mask with the raycast class+building-ID roof
   mask after a symmetric one-pixel Chebyshev boundary exclusion;
4. rewrites only the frozen nine priority crops and their contact sheet, adding
   the target building-ID boundary in lime.  The 27 full overlays are read-only.

The CSV contains one row per view, one pooled row, and one pooled row per exact
Arm-1-prime C00118 building.  The raycast arrays are discarded after each view.
No ray distance, intersection XYZ, LoD2 z, or LoD2 height is written.

All lineage locks remain fail-closed.  A replayed pixel count is not itself a
lineage lock: Open3D may choose a different primitive on a shared triangle edge
even with identical inputs.  Raw replay mismatch/agreement, their inventory
deltas, and the mismatch split inside/outside the locked 1 px exclusion are
therefore recorded rather than used as a pass/fail condition.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import math
import os
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
from PIL import Image as PILImage
from PIL import ImageDraw
from scipy import ndimage


REPO = Path(__file__).resolve().parents[3]
PRODUCER = REPO / "phases/p2-gsjso/scripts/e5_c001_s3_semantic_regions.py"
DEFAULT_MANIFEST = (
    REPO
    / "phases/p2-gsjso/runs/20260713_e5_c001_s3_track0/semantic_region_manifest.json"
)
OUTPUT_CSV = REPO / "docs/experiments/e5_c001_s3/tables/e5_c001_s3_idmap_class_agreement.csv"
OUTPUT_MANIFEST = REPO / "docs/experiments/e5_c001_s3/manifests/e5_c001_s3_idmap_class_agreement_manifest.json"


def _load_producer():
    spec = importlib.util.spec_from_file_location("s3_semantic_region_producer", PRODUCER)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import canonical producer: {PRODUCER}")
    module = importlib.util.module_from_spec(spec)
    # The producer owns dataclasses; registration is needed before exec_module.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


REGIONS = _load_producer()
MCL = REGIONS.MCL

SCHEMA = "jointbuildgs.s3a.idmap_class_agreement.v2"
DURABLE_MANIFEST_SCHEMA = "jointbuildgs.s3a.idmap_class_agreement_manifest.v1"
EXPECTED_RUN_ID = "20260713_e5_c001_s3a_semantic_regions"
EXPECTED_VIEWS = 428
EXPECTED_PRIORITY_CROPS = 9
EXPECTED_PRIORITY_UNIQUE_VIEWS = 6
ACTUAL_GEOID_M = 48.0
ACTUAL_SHIFT_Z_M = 556.0
OFFICIAL_GEOID_M = 45.7
OFFICIAL_SHIFT_Z_M = 558.3
XY_SHIFT_UTM_M = (690953.0, 5336071.0)
AOI_MARGIN_M = 200.0
BOUNDARY_EXCLUSION_PX = 1
ID_BOUNDARY_COLOR_RGB = (70, 255, 90)
ID_BOUNDARY_LABEL = (
    "Lime = actual-source 48.0/556.0 target building-ID boundary (address only)"
)
TARGET_ID_NOT_VISIBLE_LABEL = "TARGET ID NOT RAYCAST-VISIBLE | no boundary drawn"
TARGET_ID_BOUNDARY_OUTSIDE_LABEL = (
    "TARGET ID PRESENT; BOUNDARY OUTSIDE FROZEN CROP | no boundary drawn in crop"
)
TARGET_ID_OUTSIDE_CROP_LABEL = "TARGET ID OUTSIDE FROZEN CROP | no boundary drawn in crop"
MISSING_ID_ANNOTATION_COLOR_RGB = (255, 190, 70)
EXPECTED_PRIORITY_STATUS_COUNTS = {
    "target_id_boundary_visible_in_frozen_crop": 8,
    "target_id_not_raycast_visible": 1,
}
BOUNDARY_EXCLUSION_DEFINITION = (
    "exclude the union of pixels whose 3x3 Chebyshev neighborhood crosses either "
    "the fixed-class roof/nonroof transition or the raycast ID-roof/nonroof transition; "
    "this removes one pixel centre on each side of either transition; for per-building "
    "rows also exclude the same one-pixel band around that raycast building-ID support"
)
ARRAY_RETENTION_POLICY = (
    "per-view rays, class raster, and building-ID raster are in-memory only and deleted "
    "after counters and any frozen priority crop are emitted; no raycast array is cached"
)
REPLAY_VALIDATION_RULE = (
    "nonblocking pixel replay measurement after strict committed-manifest, producer, input, "
    "datum, mesh, fixed-class-PNG, cache, and container locks; raw class mismatch/agreement "
    "and replay-minus-inventory deltas are recorded; roof-membership disagreements inside "
    "the locked evaluable domain remain scored and are never hidden"
)

COUNT_FIELDS = (
    "domain_pixels",
    "boundary_excluded_pixels",
    "evaluable_pixels",
    "fixed_roof_pixels_before_exclusion",
    "idmap_roof_pixels_before_exclusion",
    "fixed_roof_pixels_evaluable",
    "idmap_roof_pixels_evaluable",
    "intersection_roof_pixels",
    "union_roof_pixels",
    "true_positive_pixels",
    "true_negative_pixels",
    "false_positive_pixels",
    "false_negative_pixels",
    "exact_match_pixels",
)

CSV_FIELDS = [
    "schema",
    "row_type",
    "aggregation",
    "building_id",
    "view_stem",
    "image_name",
    "views_total",
    "views_with_building_id",
    "views_evaluable",
    "evaluation_domain",
    "boundary_exclusion_px",
    "boundary_metric",
    "boundary_exclusion_definition",
    *COUNT_FIELDS,
    "binary_agreement",
    "roof_iou",
    "roof_dice",
    "fixed_roof_recall_by_idmap",
    "idmap_roof_precision_against_fixed",
    "metric_status",
    "actual_source_class_total_pixels",
    "actual_source_class_mismatch_pixels_inventory",
    "actual_source_class_mismatch_pixels_replay",
    "actual_source_class_mismatch_pixels_delta_replay_minus_inventory",
    "actual_source_class_agreement_inventory",
    "actual_source_class_agreement_replay",
    "actual_source_class_agreement_delta_replay_minus_inventory",
    "actual_source_roof_iou_inventory",
    "actual_source_roof_iou_replay",
    "actual_source_roof_iou_delta_replay_minus_inventory",
    "actual_source_replay_inventory_exact_match",
    "actual_source_roof_membership_mismatch_boundary_excluded_pixels_replay",
    "actual_source_roof_membership_mismatch_evaluable_pixels_replay",
    "actual_source_replay_validation_rule",
    "actual_source_geoid_m",
    "actual_source_shift_z_m",
    "raycast_building_id_role",
    "raycast_depth_or_height_supervision",
    "manifest_path",
    "manifest_sha256",
    "producer_script_path",
    "producer_script_sha256",
    "supplement_script_sha256",
    "fixed_class_png_sha256",
    "cache_npz_sha256",
    "semantic_png_set_sha256",
    "cache_npz_set_sha256",
    "manifest_input_hash_set_sha256",
    "manifest_input_hashes_json",
    "priority_gallery_contract_sha256",
    "priority_gallery_output_set_sha256",
    "array_retention_policy",
    "notes",
]


def _fail(message: str) -> None:
    raise RuntimeError(f"S3-A supplement provenance mismatch: {message}")


def _require(condition: bool, message: str) -> None:
    if not condition:
        _fail(message)


def repo_path(value: str | Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = REPO / path
    resolved = path.resolve()
    try:
        resolved.relative_to(REPO.resolve())
    except ValueError as exc:
        raise RuntimeError(f"path escapes repository: {value}") from exc
    return resolved


def rel(path: Path) -> str:
    return REGIONS.rel(path)


def _is_sha256(value: object) -> bool:
    text = str(value)
    return len(text) == 64 and all(character in "0123456789abcdef" for character in text.lower())


def one_pixel_transition_band(mask: np.ndarray) -> np.ndarray:
    """Symmetric one-pixel Chebyshev band around a binary transition.

    ``mode='nearest'`` intentionally does not invent a transition beyond the
    image frame.  At a straight internal transition, exactly one pixel centre
    on each side is excluded.
    """

    binary = np.asarray(mask, dtype=bool)
    if binary.ndim != 2:
        raise ValueError("boundary mask must be HxW")
    values = binary.astype(np.uint8, copy=False)
    high = ndimage.maximum_filter(values, size=3, mode="nearest")
    low = ndimage.minimum_filter(values, size=3, mode="nearest")
    return high != low


def agreement_counts(
    fixed_roof: np.ndarray,
    idmap_roof: np.ndarray,
    *,
    domain: np.ndarray | None = None,
    extra_boundary_masks: Iterable[np.ndarray] = (),
) -> dict[str, int]:
    """Return additive binary agreement counts under the locked exclusion."""

    fixed = np.asarray(fixed_roof, dtype=bool)
    id_roof = np.asarray(idmap_roof, dtype=bool)
    if fixed.shape != id_roof.shape or fixed.ndim != 2:
        raise ValueError("fixed_roof and idmap_roof must share one HxW shape")
    base = np.ones(fixed.shape, dtype=bool) if domain is None else np.asarray(domain, dtype=bool)
    if base.shape != fixed.shape:
        raise ValueError("agreement domain must match roof-mask shape")
    boundary = one_pixel_transition_band(fixed) | one_pixel_transition_band(id_roof)
    for mask in extra_boundary_masks:
        candidate = np.asarray(mask, dtype=bool)
        if candidate.shape != fixed.shape:
            raise ValueError("extra boundary mask must match roof-mask shape")
        boundary |= one_pixel_transition_band(candidate)
    evaluable = base & ~boundary
    tp = evaluable & fixed & id_roof
    tn = evaluable & ~fixed & ~id_roof
    fp = evaluable & ~fixed & id_roof
    fn = evaluable & fixed & ~id_roof
    counts = {
        "domain_pixels": int(base.sum()),
        "boundary_excluded_pixels": int((base & boundary).sum()),
        "evaluable_pixels": int(evaluable.sum()),
        "fixed_roof_pixels_before_exclusion": int((base & fixed).sum()),
        "idmap_roof_pixels_before_exclusion": int((base & id_roof).sum()),
        "fixed_roof_pixels_evaluable": int((evaluable & fixed).sum()),
        "idmap_roof_pixels_evaluable": int((evaluable & id_roof).sum()),
        "intersection_roof_pixels": int(tp.sum()),
        "union_roof_pixels": int((evaluable & (fixed | id_roof)).sum()),
        "true_positive_pixels": int(tp.sum()),
        "true_negative_pixels": int(tn.sum()),
        "false_positive_pixels": int(fp.sum()),
        "false_negative_pixels": int(fn.sum()),
        "exact_match_pixels": int((tp | tn).sum()),
    }
    if counts["evaluable_pixels"] != sum(
        counts[key]
        for key in (
            "true_positive_pixels",
            "true_negative_pixels",
            "false_positive_pixels",
            "false_negative_pixels",
        )
    ):
        raise AssertionError("agreement partition is not exhaustive")
    return counts


def empty_counts() -> dict[str, int]:
    return {field: 0 for field in COUNT_FIELDS}


def add_counts(total: dict[str, int], part: Mapping[str, int]) -> None:
    for field in COUNT_FIELDS:
        total[field] += int(part[field])


def agreement_metrics(counts: Mapping[str, int]) -> dict[str, float | str | None]:
    evaluable = int(counts["evaluable_pixels"])
    intersection = int(counts["intersection_roof_pixels"])
    union = int(counts["union_roof_pixels"])
    fixed = int(counts["fixed_roof_pixels_evaluable"])
    id_roof = int(counts["idmap_roof_pixels_evaluable"])
    if evaluable == 0:
        return {
            "binary_agreement": None,
            "roof_iou": None,
            "roof_dice": None,
            "fixed_roof_recall_by_idmap": None,
            "idmap_roof_precision_against_fixed": None,
            "metric_status": "no_evaluable_pixels",
        }
    return {
        "binary_agreement": float(int(counts["exact_match_pixels"]) / evaluable),
        "roof_iou": float(intersection / union) if union else 1.0,
        "roof_dice": float(2 * intersection / (fixed + id_roof)) if fixed + id_roof else 1.0,
        "fixed_roof_recall_by_idmap": float(intersection / fixed) if fixed else None,
        "idmap_roof_precision_against_fixed": float(intersection / id_roof) if id_roof else None,
        "metric_status": "ok",
    }


def actual_source_replay_audit(
    fixed_class: np.ndarray,
    actual_label: np.ndarray,
    actual_bidmap: np.ndarray,
    inventory: Mapping[str, str],
    *,
    mesh_building_count: int,
) -> dict[str, Any]:
    """Validate raycast structure strictly and report pixel replay nonblockingly.

    The producer inventory was measured in the producer process that created
    the cache.  It is evidence, not a cross-process bit-exactness contract.
    Structural impossibilities still fail: shape drift, an unknown class, a
    hit/class disagreement, or an out-of-range building index.
    """

    fixed = np.asarray(fixed_class)
    replay = np.asarray(actual_label)
    bidmap = np.asarray(actual_bidmap)
    if fixed.ndim != 2 or fixed.shape != replay.shape or fixed.shape != bidmap.shape:
        raise RuntimeError("actual-source replay arrays must share one HxW shape")
    labels = set(int(value) for value in np.unique(replay))
    if not labels.issubset({0, 1, 2, 3}):
        raise RuntimeError(f"actual-source replay contains unknown classes: {sorted(labels)}")
    hit = bidmap >= 0
    if np.any((replay > 0) != hit):
        raise RuntimeError("actual-source class/hit and building-ID validity disagree")
    if np.any(bidmap < -1) or np.any(bidmap >= int(mesh_building_count)):
        raise RuntimeError("actual-source building-ID index is outside the raycast mesh")

    alignment = REGIONS.class_alignment(fixed, replay)
    inventory_mismatch = int(inventory["actual_source_class_mismatch_pixels"])
    inventory_agreement = float(inventory["actual_source_class_agreement"])
    inventory_roof_iou = float(inventory["actual_source_roof_iou"])
    replay_mismatch = int(alignment["mismatch_pixels"])
    replay_agreement = float(alignment["class_agreement"])
    replay_roof_iou = float(alignment["roof_iou"])

    fixed_roof = fixed == 1
    idmap_roof = (replay == 1) & hit
    locked_boundary = one_pixel_transition_band(fixed_roof) | one_pixel_transition_band(
        idmap_roof
    )
    roof_membership_mismatch = fixed_roof ^ idmap_roof
    return {
        "actual_source_class_total_pixels": int(alignment["total_pixels"]),
        "actual_source_class_mismatch_pixels_inventory": inventory_mismatch,
        "actual_source_class_mismatch_pixels_replay": replay_mismatch,
        "actual_source_class_mismatch_pixels_delta_replay_minus_inventory": (
            replay_mismatch - inventory_mismatch
        ),
        "actual_source_class_agreement_inventory": inventory_agreement,
        "actual_source_class_agreement_replay": replay_agreement,
        "actual_source_class_agreement_delta_replay_minus_inventory": (
            replay_agreement - inventory_agreement
        ),
        "actual_source_roof_iou_inventory": inventory_roof_iou,
        "actual_source_roof_iou_replay": replay_roof_iou,
        "actual_source_roof_iou_delta_replay_minus_inventory": (
            replay_roof_iou - inventory_roof_iou
        ),
        "actual_source_replay_inventory_exact_match": (
            replay_mismatch == inventory_mismatch
            and math.isclose(replay_agreement, inventory_agreement, rel_tol=0.0, abs_tol=1e-15)
            and math.isclose(replay_roof_iou, inventory_roof_iou, rel_tol=0.0, abs_tol=1e-15)
        ),
        "actual_source_roof_membership_mismatch_boundary_excluded_pixels_replay": int(
            (roof_membership_mismatch & locked_boundary).sum()
        ),
        "actual_source_roof_membership_mismatch_evaluable_pixels_replay": int(
            (roof_membership_mismatch & ~locked_boundary).sum()
        ),
        "actual_source_replay_validation_rule": REPLAY_VALIDATION_RULE,
    }


def validate_manifest_fields(manifest: Mapping[str, Any]) -> None:
    """Pure fail-closed validation of the adjudicated producer contract."""

    _require(manifest.get("run_id") == EXPECTED_RUN_ID, "unexpected run_id")
    _require(manifest.get("script") == rel(PRODUCER), "unexpected producer path")
    _require(_is_sha256(manifest.get("script_sha256")), "invalid producer hash")
    _require(manifest.get("container_image") == "jointbuildgs:dev", "unexpected container image")
    image_id = str(manifest.get("container_image_id", ""))
    _require(image_id.startswith("sha256:") and _is_sha256(image_id[7:]), "invalid container image ID")

    inputs = manifest.get("inputs") or {}
    candidates = inputs.get("arm1p_candidate_buildings_assignment_order")
    _require(isinstance(candidates, list), "candidate building list missing")
    _require(len(candidates) == 18 and len(set(candidates)) == 18, "candidate list is not exact C00118")
    _require(candidates == sorted(candidates), "candidate assignment order is not lexical")
    input_hashes = inputs.get("hashes")
    _require(isinstance(input_hashes, dict) and input_hashes, "manifest input hashes missing")
    _require(all(_is_sha256(value) for value in input_hashes.values()), "invalid input hash")

    locks = manifest.get("locks") or {}
    expected_locks = {
        "crs": "EPSG:25832",
        "source_component_connectivity": 8,
        "source_component_min_pixels": 256,
        "cutline_half_width_px": 7,
        "loss_address_mode": "oracle_class_plus_raycast_building_id",
        "raycast_building_id_loss_role": "region address only",
        "l_nb_boundary_source": "class boundary only; no instance cutline",
    }
    for key, expected in expected_locks.items():
        _require(locks.get(key) == expected, f"lock changed: {key}")
    value_contract = locks.get("loss_value_contract") or {}
    _require(value_contract.get("lod2_depth_or_height_loss_input") is False, "LoD2 value leak")
    _require(value_contract.get("raycast_hit_distance_stored") is False, "ray distance leak")
    _require(value_contract.get("raycast_intersection_xyz_stored") is False, "intersection XYZ leak")

    datum = (manifest.get("datum_provenance") or {}).get("actual_label_source") or {}
    _require(math.isclose(float(datum.get("geoid_m", math.nan)), ACTUAL_GEOID_M), "actual-source geoid changed")
    _require(math.isclose(float(datum.get("shift_z_m", math.nan)), ACTUAL_SHIFT_Z_M), "actual-source shift changed")
    _require(datum.get("building_id_role") == "region address only", "building-ID role changed")

    oracle = manifest.get("oracle_id_address_aggregate") or {}
    _require(oracle.get("provenance") == "actual_label_source_legacy48p0_oracle_address", "oracle provenance changed")
    _require(oracle.get("building_id_is_loss_input") is True, "oracle ID address disabled")
    _require(oracle.get("loss_role") == "region address only", "oracle ID role changed")
    _require(oracle.get("lod2_depth_or_height_loss_input") is False, "oracle value leak")
    _require(int((oracle.get("totals") or {}).get("wrong", -1)) == 0, "oracle address integrity is not zero-wrong")

    outputs = manifest.get("outputs") or {}
    _require(int(outputs.get("cache_files", -1)) == EXPECTED_VIEWS, "cache count is not 428")
    _require(int(outputs.get("priority_crop_count", -1)) == EXPECTED_PRIORITY_CROPS, "priority crop count changed")
    _require(int(outputs.get("priority_contact_sheet_count", -1)) == 1, "contact-sheet count changed")
    _require(isinstance(outputs.get("output_sha256"), dict), "output hash inventory missing")


def validate_priority_artifact_contract(
    artifacts: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], dict[tuple[str, str], dict[str, Any]], dict[str, Any]]:
    """Freeze exactly the producer-selected 3x3 gallery (six unique views)."""

    priority = [dict(row) for row in artifacts if row.get("kind") == "priority_crop"]
    full = {
        (str(row.get("building_id")), str(row.get("view_stem"))): dict(row)
        for row in artifacts
        if row.get("kind") == "full_overlay"
    }
    contacts = [dict(row) for row in artifacts if row.get("kind") == "priority_contact_sheet"]
    _require(len(priority) == EXPECTED_PRIORITY_CROPS, "priority artifact list is not nine")
    _require(len(contacts) == 1, "priority contact artifact is not unique")
    expected_keys = {
        (building_id, rank)
        for building_id in REGIONS.TEXTURELESS3
        for rank in (1, 2, 3)
    }
    actual_keys = {(str(row.get("building_id")), int(row.get("rank", -1))) for row in priority}
    _require(actual_keys == expected_keys, "priority building/rank keys changed")
    unique_views = {str(row.get("view_stem")) for row in priority}
    _require(len(unique_views) == EXPECTED_PRIORITY_UNIQUE_VIEWS, "priority view set is not frozen six")
    for row in priority:
        key = (str(row["building_id"]), str(row["view_stem"]))
        _require(key in full, f"priority crop lacks full-overlay source: {key}")
        crop = row.get("crop_box_xyxy")
        _require(
            isinstance(crop, list)
            and len(crop) == 4
            and all(isinstance(value, int) for value in crop)
            and crop[0] < crop[2]
            and crop[1] < crop[3],
            f"invalid frozen crop box: {key}",
        )
    order = {building_id: index for index, building_id in enumerate(REGIONS.TEXTURELESS3)}
    priority.sort(key=lambda row: (order[str(row["building_id"])], int(row["rank"])))
    return priority, full, contacts[0]


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _hash_matches(path: Path, expected: str, label: str) -> None:
    _require(path.is_file(), f"missing {label}: {rel(path)}")
    observed = REGIONS.sha256_file(path)
    _require(observed == expected, f"{label} hash changed: {rel(path)}")


def _require_committed_head_copy(path: Path, observed_sha256: str) -> None:
    """Reject an edited/untracked manifest even if its internal JSON is plausible."""

    relative = rel(path)
    try:
        committed = subprocess.check_output(
            ["git", "show", f"HEAD:{relative}"], cwd=REPO
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError(f"canonical manifest is not readable from HEAD: {relative}") from exc
    committed_sha256 = hashlib.sha256(committed).hexdigest()
    _require(committed_sha256 == observed_sha256, "canonical manifest differs from committed HEAD")


def load_validated_context(manifest_path: Path) -> dict[str, Any]:
    """Validate all immutable producer inputs and cache files before raycasting."""

    manifest_path = manifest_path.resolve()
    _require(manifest_path == DEFAULT_MANIFEST.resolve(), "noncanonical manifest requested")
    _require(manifest_path.is_file(), "canonical manifest missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    validate_manifest_fields(manifest)
    manifest_sha = REGIONS.sha256_file(manifest_path)
    _require_committed_head_copy(manifest_path, manifest_sha)

    _hash_matches(PRODUCER, str(manifest["script_sha256"]), "producer script")
    for raw_path, expected in (manifest["inputs"]["hashes"] or {}).items():
        _hash_matches(repo_path(raw_path), str(expected), "declared producer input")

    expected_image_id = str(manifest["container_image_id"])
    live_image_id = os.environ.get(REGIONS.DOCKER_IMAGE_ID_ENV, "").strip()
    _require(live_image_id == expected_image_id, "container digest does not match producer manifest")

    outputs = manifest["outputs"]
    output_hashes = outputs["output_sha256"]
    inventory_path = repo_path(outputs["inventory_csv"])
    gate_path = repo_path(outputs["semantic_gate_csv"])
    _require(rel(inventory_path) in output_hashes, "inventory hash absent from manifest")
    _require(rel(gate_path) in output_hashes, "semantic-gate hash absent from manifest")
    _hash_matches(inventory_path, str(output_hashes[rel(inventory_path)]), "cache inventory CSV")
    _hash_matches(gate_path, str(output_hashes[rel(gate_path)]), "semantic-gate CSV")

    inventory = _read_csv(inventory_path)
    _require(len(inventory) == EXPECTED_VIEWS, "cache inventory row count changed")
    inventory_by_stem = {row["view_stem"]: row for row in inventory}
    _require(len(inventory_by_stem) == EXPECTED_VIEWS, "cache inventory stems are not unique")
    cache_dir = repo_path(outputs["cache_dir"])
    cache_paths = sorted(cache_dir.glob("*.npz"))
    _require(len(cache_paths) == EXPECTED_VIEWS, "live cache file count changed")
    _require({path.stem for path in cache_paths} == set(inventory_by_stem), "live cache stem set changed")

    semantic_hash_rows: list[dict[str, str]] = []
    cache_hash_rows: list[dict[str, str]] = []
    for stem in sorted(inventory_by_stem):
        row = inventory_by_stem[stem]
        _require(row.get("status") == "ok", f"cache inventory status is not ok: {stem}")
        _require(row.get("address_mode") == "oracle_class_plus_raycast_building_id", f"cache address changed: {stem}")
        _require(math.isclose(float(row["address_datum_geoid_m"]), ACTUAL_GEOID_M), f"cache geoid changed: {stem}")
        _require(math.isclose(float(row["address_datum_shift_z_m"]), ACTUAL_SHIFT_Z_M), f"cache shift changed: {stem}")
        _require(row.get("lod2_depth_or_height_loss_input") == "False", f"cache value-role changed: {stem}")
        cache_path = repo_path(row["cache_path"])
        semantic_path = repo_path(row["semantic_mask_path"])
        _require(cache_path.parent == cache_dir, f"cache path escaped canonical directory: {stem}")
        _hash_matches(cache_path, row["cache_sha256"], "semantic-region cache")
        _hash_matches(semantic_path, row["semantic_mask_sha256"], "fixed semantic PNG")
        cache_hash_rows.append({"view_stem": stem, "sha256": row["cache_sha256"]})
        semantic_hash_rows.append({"view_stem": stem, "sha256": row["semantic_mask_sha256"]})

    data_root = repo_path(manifest["inputs"]["data_root"])
    frames = REGIONS.load_frames(data_root)
    _require(len(frames) == EXPECTED_VIEWS, "COLMAP/image intersection is not 428")
    frame_by_stem = {frame.stem: frame for frame in frames}
    _require(len(frame_by_stem) == EXPECTED_VIEWS, "frame stems are not unique")
    _require(set(frame_by_stem) == set(inventory_by_stem), "frame/cache stem set mismatch")
    for stem, frame in frame_by_stem.items():
        _require(inventory_by_stem[stem]["image_name"] == frame.name, f"image-name mismatch: {stem}")
        expected_semantic = (data_root / "semantic" / f"{stem}.png").resolve()
        _require(repo_path(inventory_by_stem[stem]["semantic_mask_path"]) == expected_semantic, f"semantic path mismatch: {stem}")

    priority, full_sources, contact = validate_priority_artifact_contract(outputs["overlay_artifacts"])
    priority_dir = (repo_path(outputs["overlay_dir"]) / "priority").resolve()
    for artifact in priority:
        _require(repo_path(artifact["path"]).parent == priority_dir, "priority crop moved")
    _require(
        repo_path(contact["path"]) == priority_dir / "textureless3_contact_sheet.png",
        "priority contact-sheet path changed",
    )
    gate_rows = [
        row
        for row in _read_csv(gate_path)
        if row.get("row_type") == "view" and row.get("building_id") in REGIONS.TEXTURELESS3
    ]
    gate_by_key = {
        (row["building_id"], row["view_stem"], int(row["view_rank_by_ref_area"])): row
        for row in gate_rows
    }
    _require(len(gate_by_key) == EXPECTED_PRIORITY_CROPS, "frozen gate rows are not nine")
    for artifact in priority:
        key = (artifact["building_id"], artifact["view_stem"], int(artifact["rank"]))
        _require(key in gate_by_key, f"priority artifact/gate row mismatch: {key}")
        full = full_sources[(artifact["building_id"], artifact["view_stem"])]
        full_path = repo_path(full["path"])
        _hash_matches(full_path, str(full["sha256"]), "read-only full overlay")
        _require(full_path.parent == repo_path(outputs["overlay_dir"]), "full overlay moved")

    semantic_set_sha = REGIONS.sha256_json(semantic_hash_rows)
    cache_set_sha = REGIONS.sha256_json(cache_hash_rows)
    input_hash_set = {
        "manifest_sha256": manifest_sha,
        "producer_script_sha256": manifest["script_sha256"],
        "manifest_input_hashes": manifest["inputs"]["hashes"],
        "semantic_png_set_sha256": semantic_set_sha,
        "cache_npz_set_sha256": cache_set_sha,
        "inventory_csv_sha256": output_hashes[rel(inventory_path)],
        "semantic_gate_csv_sha256": output_hashes[rel(gate_path)],
    }
    priority_contract = [
        {
            "building_id": row["building_id"],
            "rank": int(row["rank"]),
            "view_stem": row["view_stem"],
            "path": row["path"],
            "crop_box_xyxy": row["crop_box_xyxy"],
            "full_overlay_sha256": full_sources[(row["building_id"], row["view_stem"])]["sha256"],
        }
        for row in priority
    ]
    return {
        "manifest_path": manifest_path,
        "manifest": manifest,
        "manifest_sha256": manifest_sha,
        "frames": frames,
        "frame_by_stem": frame_by_stem,
        "inventory_by_stem": inventory_by_stem,
        "data_root": data_root,
        "building_ids": list(manifest["inputs"]["arm1p_candidate_buildings_assignment_order"]),
        "priority": priority,
        "priority_by_stem": _group_priority_by_stem(priority),
        "full_sources": full_sources,
        "contact": contact,
        "gate_by_key": gate_by_key,
        "semantic_png_set_sha256": semantic_set_sha,
        "cache_npz_set_sha256": cache_set_sha,
        "input_hash_set": input_hash_set,
        "manifest_input_hash_set_sha256": REGIONS.sha256_json(input_hash_set),
        "priority_gallery_contract_sha256": REGIONS.sha256_json(priority_contract),
    }


def _group_priority_by_stem(rows: Sequence[Mapping[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["view_stem"])].append(dict(row))
    return dict(grouped)


def build_actual_source_scene(context: Mapping[str, Any]) -> tuple[Any, np.ndarray, np.ndarray, list[str]]:
    manifest = context["manifest"]
    datum = json.loads(repo_path(manifest["inputs"]["datum_config"]).read_text(encoding="utf-8"))
    _require(datum.get("geo_crs") == "EPSG:25832", "datum CRS changed")
    official_geoid = float(datum["orthometric_geoid_m"])
    ellipsoid_shift = float(datum["ellipsoid_shift_z_m"])
    official_shift = ellipsoid_shift - official_geoid
    _require(math.isclose(official_geoid, OFFICIAL_GEOID_M), "official geoid changed")
    _require(math.isclose(official_shift, OFFICIAL_SHIFT_Z_M), "official shift changed")
    _require(math.isclose(ellipsoid_shift - ACTUAL_GEOID_M, ACTUAL_SHIFT_Z_M), "actual shift derivation changed")

    frames = context["frames"]
    centers = np.asarray([-frame.R.T @ frame.t for frame in frames])
    aoi_min = centers[:, :2].min(axis=0) - AOI_MARGIN_M
    aoi_max = centers[:, :2].max(axis=0) + AOI_MARGIN_M
    shift_official = np.asarray([*XY_SHIFT_UTM_M, official_shift], dtype=np.float64)
    gml_paths = [repo_path(value) for value in manifest["inputs"]["gml"]]
    rings, ring_counts, buildings_scanned = MCL.extract_rings(
        gml_paths, shift_official, aoi_min, aoi_max
    )
    scene, tri_class, tri_bid, mesh_bids, degenerate = MCL.build_scene(rings)
    mesh = manifest["mesh"]
    _require(int(mesh["buildings_scanned"]) == int(buildings_scanned), "GML building scan count changed")
    _require(int(mesh["triangles"]) == len(tri_class), "raycast triangle count changed")
    _require(int(mesh["mesh_buildings"]) == len(mesh_bids), "raycast mesh building count changed")
    _require(int(mesh["degenerate_rings"]) == int(degenerate), "degenerate-ring count changed")
    _require(
        {str(key): int(value) for key, value in mesh["rings_kept"].items()}
        == {str(key): int(value) for key, value in ring_counts.items()},
        "raycast ring inventory changed",
    )
    missing = sorted(set(context["building_ids"]) - set(mesh_bids))
    _require(not missing, f"C00118 missing from raycast mesh: {missing}")
    return scene, tri_class, tri_bid, mesh_bids


def paint_id_boundary(
    base: PILImage.Image, target_id_mask: np.ndarray
) -> tuple[PILImage.Image, np.ndarray]:
    """Paint a visible three-pixel lime target-ID outline on a copy."""

    rgb = np.asarray(base.convert("RGB"), dtype=np.uint8).copy()
    mask = np.asarray(target_id_mask, dtype=bool)
    if mask.shape != rgb.shape[:2]:
        raise ValueError("target-ID mask and overlay dimensions differ")
    boundary = REGIONS.binary_boundary(mask)
    line = ndimage.binary_dilation(boundary, structure=np.ones((3, 3), dtype=bool), iterations=1)
    rgb[line] = np.asarray(ID_BOUNDARY_COLOR_RGB, dtype=np.uint8)
    return PILImage.fromarray(rgb), line


def _format_metric(row: Mapping[str, str], key: str, decimals: int = 3) -> str:
    value = row.get(key, "")
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "UNDEFINED"
    return f"{number:.{decimals}f}" if math.isfinite(number) else "UNDEFINED"


def render_priority_crop_with_id_boundary(
    out_path: Path,
    source_overlay: PILImage.Image,
    target_id_mask: np.ndarray,
    artifact: Mapping[str, Any],
    gate_row: Mapping[str, str],
) -> dict[str, Any]:
    target_mask = np.asarray(target_id_mask, dtype=bool)
    target_boundary = REGIONS.binary_boundary(target_mask)
    painted, line = paint_id_boundary(source_overlay, target_mask)
    crop_box = tuple(int(value) for value in artifact["crop_box_xyxy"])
    x0, y0, x1, y1 = crop_box
    _require(0 <= x0 < x1 <= painted.width and 0 <= y0 < y1 <= painted.height, "frozen crop leaves overlay")
    target_pixels_full = int(target_mask.sum())
    target_pixels_crop = int(target_mask[y0:y1, x0:x1].sum())
    boundary_pixels_full = int(target_boundary.sum())
    boundary_pixels_crop = int(target_boundary[y0:y1, x0:x1].sum())
    line_full = int(line.sum())
    line_in_crop = int(line[y0:y1, x0:x1].sum())
    if target_pixels_full == 0:
        target_status = "target_id_not_raycast_visible"
        target_annotation = TARGET_ID_NOT_VISIBLE_LABEL
        annotation_color = MISSING_ID_ANNOTATION_COLOR_RGB
    elif line_in_crop > 0:
        target_status = "target_id_boundary_visible_in_frozen_crop"
        target_annotation = ID_BOUNDARY_LABEL
        annotation_color = ID_BOUNDARY_COLOR_RGB
    elif target_pixels_crop > 0:
        target_status = "target_id_present_crop_boundary_not_visible"
        target_annotation = TARGET_ID_BOUNDARY_OUTSIDE_LABEL
        annotation_color = MISSING_ID_ANNOTATION_COLOR_RGB
    else:
        target_status = "target_id_present_full_outside_frozen_crop"
        target_annotation = TARGET_ID_OUTSIDE_CROP_LABEL
        annotation_color = MISSING_ID_ANNOTATION_COLOR_RGB
    crop = painted.crop(crop_box)
    header_height = 108
    canvas_width = max(crop.width, 650)
    canvas = PILImage.new("RGB", (canvas_width, crop.height + header_height), color=(12, 12, 12))
    canvas.paste(crop, ((canvas_width - crop.width) // 2, header_height))
    draw = ImageDraw.Draw(canvas)
    font = REGIONS._ui_font(14)
    short_id = str(artifact["building_id"]).removeprefix("DEBY_LOD2_")
    offset = (
        f"{_format_metric(gate_row, 'boundary_offset_px')} px / "
        f"{_format_metric(gate_row, 'boundary_offset_m')} m"
        if gate_row.get("boundary_offset_defined") == "True"
        else f"UNDEFINED ({gate_row.get('boundary_offset_status', 'unknown')})"
    )
    lines = [
        f"Building {short_id} | Rank {artifact['rank']} | {artifact['view_stem']}",
        f"{artifact.get('support_label', '')} | Selected low-support views: {artifact.get('selected_low_support_count', 0)}",
        (
            f"IoU {_format_metric(gate_row, 'iou', 4)} | Fragments "
            f"{gate_row.get('fragment_count_ge64', '')} | Offset {offset}"
            + (" | FRAME EDGE" if artifact.get("target_touches_frame") else "")
        ),
        target_annotation,
    ]
    y = 5
    for index, text in enumerate(lines):
        color = annotation_color if index == len(lines) - 1 else (255, 255, 255)
        draw.text((7, y), text, fill=color, font=font)
        bbox = draw.textbbox((7, y), text, font=font)
        y = bbox[3] + 4
    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_path)
    return {
        "building_id": artifact["building_id"],
        "rank": int(artifact["rank"]),
        "view_stem": artifact["view_stem"],
        "path": str(artifact["path"]),
        "crop_box_xyxy": list(crop_box),
        "target_id_status": target_status,
        "target_id_annotation": target_annotation,
        "target_id_pixels_full": target_pixels_full,
        "target_id_pixels_crop": target_pixels_crop,
        "target_id_boundary_pixels_full": boundary_pixels_full,
        "target_id_boundary_pixels_crop": boundary_pixels_crop,
        "target_id_painted_line_pixels_full": line_full,
        "target_id_painted_line_pixels_crop": line_in_crop,
        "boundary_fabricated": False,
        "sha256": REGIONS.sha256_file(out_path),
    }


def summarize_priority_gallery(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Aggregate the frozen-nine target-ID evidence without deduplicating views."""

    count_fields = (
        "target_id_pixels_full",
        "target_id_pixels_crop",
        "target_id_boundary_pixels_full",
        "target_id_boundary_pixels_crop",
        "target_id_painted_line_pixels_full",
        "target_id_painted_line_pixels_crop",
    )
    fabricated = sum(bool(record.get("boundary_fabricated")) for record in records)
    _require(fabricated == 0, "priority gallery attempted to fabricate an ID boundary")
    status_counts = dict(
        sorted(Counter(str(record["target_id_status"]) for record in records).items())
    )
    return {
        "aggregation": "sum_over_frozen_9_crops; repeated full views are intentionally repeated",
        "record_count": len(records),
        "status_counts": status_counts,
        "boundary_visible_crop_count": status_counts.get(
            "target_id_boundary_visible_in_frozen_crop", 0
        ),
        "not_raycast_visible_crop_count": status_counts.get(
            "target_id_not_raycast_visible", 0
        ),
        **{
            f"{field}_sum": sum(int(record[field]) for record in records)
            for field in count_fields
        },
        "boundary_fabricated_count": fabricated,
    }


def build_durable_output_manifest(
    context: Mapping[str, Any],
    *,
    staged_csv: Path,
    crop_records: Sequence[Mapping[str, Any]],
    contact_record: Mapping[str, Any],
    target_id_summary: Mapping[str, Any],
    gallery_output_set_sha256: str,
    supplement_script_sha256: str,
) -> dict[str, Any]:
    """Build the non-circular durable ledger for the fully staged bundle."""

    _require(len(crop_records) == EXPECTED_PRIORITY_CROPS, "durable manifest requires nine crops")
    _require(
        dict(target_id_summary.get("status_counts") or {})
        == EXPECTED_PRIORITY_STATUS_COUNTS,
        "canonical priority status summary is not the observed 8 visible / 1 not-visible",
    )
    _require(
        int(target_id_summary.get("boundary_fabricated_count", -1)) == 0,
        "durable manifest refuses a fabricated boundary",
    )
    _require(
        all(record.get("boundary_fabricated") is False for record in crop_records),
        "durable manifest crop record reports a fabricated boundary",
    )
    _require(
        contact_record.get("boundary_fabricated") is False,
        "durable manifest contact record reports a fabricated boundary",
    )
    _require(_is_sha256(gallery_output_set_sha256), "invalid gallery output-set hash")
    _require(_is_sha256(supplement_script_sha256), "invalid supplement script hash")

    order = {building_id: index for index, building_id in enumerate(REGIONS.TEXTURELESS3)}
    ordered_crops = sorted(
        (dict(record) for record in crop_records),
        key=lambda record: (order[str(record["building_id"])], int(record["rank"])),
    )
    csv_record = {
        "path": rel(OUTPUT_CSV),
        "sha256": REGIONS.sha256_file(staged_csv),
        "schema": SCHEMA,
        "rows": EXPECTED_VIEWS + 1 + 18,
    }
    artifact_set = {
        "csv": csv_record,
        "priority_crops": ordered_crops,
        "contact_sheet": dict(contact_record),
    }
    output_set_sha256 = REGIONS.sha256_json(artifact_set)
    strict_input_hash_set = dict(context["input_hash_set"])
    strict_input_hash_set_sha256 = REGIONS.sha256_json(strict_input_hash_set)
    _require(
        strict_input_hash_set_sha256 == context["manifest_input_hash_set_sha256"],
        "strict input hash-set digest changed while building durable manifest",
    )
    return {
        "schema": DURABLE_MANIFEST_SCHEMA,
        "measurement_csv_schema": SCHEMA,
        "claim_scope": (
            "S3-A oracle class+instance-address upper-bound supplement; ID is an address "
            "only and never depth or height supervision"
        ),
        "source_semantic_region_manifest": {
            "path": rel(context["manifest_path"]),
            "sha256": context["manifest_sha256"],
        },
        "supplement_script": {
            "path": rel(Path(__file__)),
            "sha256": supplement_script_sha256,
        },
        "strict_input_hash_set": strict_input_hash_set,
        "strict_input_hash_set_sha256": strict_input_hash_set_sha256,
        "replay_validation_rule": REPLAY_VALIDATION_RULE,
        "boundary_exclusion_definition": BOUNDARY_EXCLUSION_DEFINITION,
        "priority_target_id_summary": dict(target_id_summary),
        "boundary_fabricated_count": 0,
        "gallery_output_set_sha256": gallery_output_set_sha256,
        "outputs": {
            "manifest_path": rel(OUTPUT_MANIFEST),
            "artifact_set_excludes_manifest": True,
            "output_set_hash_definition": (
                "sha256 of canonical JSON for outputs.artifact_set; the durable manifest "
                "path and manifest bytes are deliberately excluded to avoid a hash cycle"
            ),
            "artifact_set": artifact_set,
            "output_set_sha256": output_set_sha256,
        },
    }


def validate_staged_output_bundle(
    payload: Mapping[str, Any],
    *,
    staged_csv: Path,
    staged_crops: Mapping[tuple[str, int], Path],
    staged_contact: Path,
) -> None:
    """Fail before any destination replace when a staged artifact drifts."""

    _require(payload.get("schema") == DURABLE_MANIFEST_SCHEMA, "durable manifest schema drift")
    _require(int(payload.get("boundary_fabricated_count", -1)) == 0, "fabricated boundary summary")
    outputs = payload.get("outputs") or {}
    _require(outputs.get("artifact_set_excludes_manifest") is True, "manifest-cycle lock missing")
    artifact_set = outputs.get("artifact_set") or {}
    _require(
        outputs.get("output_set_sha256") == REGIONS.sha256_json(artifact_set),
        "durable output-set hash mismatch",
    )
    _require(
        rel(OUTPUT_MANIFEST) not in json.dumps(artifact_set, sort_keys=True, ensure_ascii=False),
        "durable manifest was included in its own output set",
    )
    _require(
        (artifact_set.get("csv") or {}).get("sha256") == REGIONS.sha256_file(staged_csv),
        "staged CSV hash mismatch",
    )
    with staged_csv.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        _require(reader.fieldnames == CSV_FIELDS, "staged CSV columns changed")
        staged_csv_rows = sum(1 for _ in reader)
    _require(
        staged_csv_rows == int((artifact_set.get("csv") or {}).get("rows", -1)),
        "staged CSV row count changed",
    )
    crop_records = artifact_set.get("priority_crops") or []
    _require(len(crop_records) == EXPECTED_PRIORITY_CROPS, "staged crop record count changed")
    expected_keys = {
        (building_id, rank)
        for building_id in REGIONS.TEXTURELESS3
        for rank in (1, 2, 3)
    }
    _require(set(staged_crops) == expected_keys, "staged crop path keys changed")
    for record in crop_records:
        key = (str(record["building_id"]), int(record["rank"]))
        _require(key in staged_crops, f"durable crop record has unknown key: {key}")
        _require(
            record.get("sha256") == REGIONS.sha256_file(staged_crops[key]),
            f"staged priority crop hash mismatch: {key}",
        )
        _require(record.get("boundary_fabricated") is False, f"fabricated crop boundary: {key}")
    contact_record = artifact_set.get("contact_sheet") or {}
    _require(
        contact_record.get("sha256") == REGIONS.sha256_file(staged_contact),
        "staged contact-sheet hash mismatch",
    )
    _require(contact_record.get("boundary_fabricated") is False, "fabricated contact boundary")
    strict_hashes = payload.get("strict_input_hash_set") or {}
    _require(
        payload.get("strict_input_hash_set_sha256") == REGIONS.sha256_json(strict_hashes),
        "durable strict-input hash-set mismatch",
    )


def make_contact_sheet(
    crop_paths: Mapping[tuple[str, int], Path],
    out_path: Path,
    *,
    target_id_status_counts: Mapping[str, int] | None = None,
) -> PILImage.Image:
    expected = {
        (building_id, rank)
        for building_id in REGIONS.TEXTURELESS3
        for rank in (1, 2, 3)
    }
    if set(crop_paths) != expected:
        raise AssertionError("supplement contact-sheet crop keys changed")
    tile_width, tile_height = REGIONS.PRIORITY_CONTACT_TILE_WH
    title_height = 108
    sheet = PILImage.new(
        "RGB", (tile_width * 3, title_height + tile_height * 3), color=(245, 245, 245)
    )
    draw = ImageDraw.Draw(sheet)
    draw.text(
        (10, 7),
        "S3-A T0-1 textureless priority gallery (reference-only; no gate verdict)",
        fill=(0, 0, 0),
        font=REGIONS._ui_font(18),
    )
    draw.text(
        (10, 34),
        "Red = fixed clean roof; Cyan = official 45.7 LoD2 reference",
        fill=(0, 0, 0),
        font=REGIONS._ui_font(13),
    )
    draw.text(
        (10, 57), ID_BOUNDARY_LABEL, fill=ID_BOUNDARY_COLOR_RGB, font=REGIONS._ui_font(13)
    )
    draw.text(
        (10, 80),
        (
            "Frozen 9 crops / 6 views; no boundary synthesized; status: "
            + json.dumps(
                dict(sorted((target_id_status_counts or {}).items())),
                sort_keys=True,
                separators=(",", ":"),
            )
        ),
        fill=(0, 0, 0),
        font=REGIONS._ui_font(13),
    )
    resampling = getattr(PILImage, "Resampling", PILImage).LANCZOS
    for row_index, building_id in enumerate(REGIONS.TEXTURELESS3):
        for column_index, rank in enumerate((1, 2, 3)):
            with PILImage.open(crop_paths[(building_id, rank)]) as source:
                tile = source.convert("RGB")
            tile.thumbnail((tile_width - 12, tile_height - 12), resampling)
            x = column_index * tile_width + (tile_width - tile.width) // 2
            y = title_height + row_index * tile_height + (tile_height - tile.height) // 2
            sheet.paste(tile, (x, y))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out_path)
    return sheet


def _common_row(
    context: Mapping[str, Any], gallery_output_sha: str, script_sha: str
) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "boundary_exclusion_px": BOUNDARY_EXCLUSION_PX,
        "boundary_metric": "Chebyshev/8-neighbor 3x3 transition band",
        "boundary_exclusion_definition": BOUNDARY_EXCLUSION_DEFINITION,
        "actual_source_geoid_m": ACTUAL_GEOID_M,
        "actual_source_shift_z_m": ACTUAL_SHIFT_Z_M,
        "actual_source_replay_validation_rule": REPLAY_VALIDATION_RULE,
        "raycast_building_id_role": "region address only",
        "raycast_depth_or_height_supervision": "false",
        "manifest_path": rel(context["manifest_path"]),
        "manifest_sha256": context["manifest_sha256"],
        "producer_script_path": rel(PRODUCER),
        "producer_script_sha256": context["manifest"]["script_sha256"],
        "supplement_script_sha256": script_sha,
        "semantic_png_set_sha256": context["semantic_png_set_sha256"],
        "cache_npz_set_sha256": context["cache_npz_set_sha256"],
        "manifest_input_hash_set_sha256": context["manifest_input_hash_set_sha256"],
        "priority_gallery_contract_sha256": context["priority_gallery_contract_sha256"],
        "priority_gallery_output_set_sha256": gallery_output_sha,
        "array_retention_policy": ARRAY_RETENTION_POLICY,
    }


def _metric_row(counts: Mapping[str, int]) -> dict[str, Any]:
    return {**{key: int(counts[key]) for key in COUNT_FIELDS}, **agreement_metrics(counts)}


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="raise", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def run(manifest_path: Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    """Execute the canonical supplement after all immutable-input validation."""

    context = load_validated_context(manifest_path)
    scene, tri_class, tri_bid, mesh_bids = build_actual_source_scene(context)
    mesh_index = {building_id: index for index, building_id in enumerate(mesh_bids)}
    pooled = empty_counts()
    replay_pooled = {
        "total_pixels": 0,
        "inventory_mismatch_pixels": 0,
        "replay_mismatch_pixels": 0,
        "roof_mismatch_boundary_excluded_pixels": 0,
        "roof_mismatch_evaluable_pixels": 0,
    }
    building_totals = {building_id: empty_counts() for building_id in context["building_ids"]}
    building_views_visible = {building_id: 0 for building_id in context["building_ids"]}
    building_views_evaluable = {building_id: 0 for building_id in context["building_ids"]}
    view_rows: list[dict[str, Any]] = []
    script_sha = REGIONS.sha256_file(Path(__file__))

    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".s3-idmap-supplement-", dir=OUTPUT_CSV.parent) as tmp:
        stage = Path(tmp)
        staged_crops: dict[tuple[str, int], Path] = {}
        gallery_records: list[dict[str, Any]] = []
        for frame_index, frame in enumerate(context["frames"], start=1):
            inventory = context["inventory_by_stem"][frame.stem]
            fixed_path = repo_path(inventory["semantic_mask_path"])
            fixed_class = np.asarray(PILImage.open(fixed_path), dtype=np.uint8)
            expected_shape = (int(frame.camera.height), int(frame.camera.width))
            _require(fixed_class.shape == expected_shape, f"fixed class shape changed: {frame.stem}")
            fixed_roof = fixed_class == 1

            rays_official = MCL.frame_rays(
                frame.camera.K(), frame.R, frame.t, frame.camera.width, frame.camera.height
            )
            rays_actual = REGIONS.shifted_rays(rays_official, ACTUAL_SHIFT_Z_M, OFFICIAL_SHIFT_Z_M)
            actual_label, actual_bidmap = MCL.cast_labels(
                scene, tri_class, tri_bid, rays_actual, frame.camera.height, frame.camera.width
            )
            replay_audit = actual_source_replay_audit(
                fixed_class,
                actual_label,
                actual_bidmap,
                inventory,
                mesh_building_count=len(mesh_bids),
            )
            idmap_roof = (actual_label == 1) & (actual_bidmap >= 0)
            counts = agreement_counts(fixed_roof, idmap_roof)
            add_counts(pooled, counts)
            replay_pooled["total_pixels"] += int(
                replay_audit["actual_source_class_total_pixels"]
            )
            replay_pooled["inventory_mismatch_pixels"] += int(
                replay_audit["actual_source_class_mismatch_pixels_inventory"]
            )
            replay_pooled["replay_mismatch_pixels"] += int(
                replay_audit["actual_source_class_mismatch_pixels_replay"]
            )
            replay_pooled["roof_mismatch_boundary_excluded_pixels"] += int(
                replay_audit[
                    "actual_source_roof_membership_mismatch_boundary_excluded_pixels_replay"
                ]
            )
            replay_pooled["roof_mismatch_evaluable_pixels"] += int(
                replay_audit[
                    "actual_source_roof_membership_mismatch_evaluable_pixels_replay"
                ]
            )
            view_rows.append(
                {
                    "row_type": "view",
                    "aggregation": "one_view_all_pixels",
                    "building_id": "",
                    "view_stem": frame.stem,
                    "image_name": frame.name,
                    "views_total": 1,
                    "views_with_building_id": "",
                    "views_evaluable": int(counts["evaluable_pixels"] > 0),
                    "evaluation_domain": "entire image after symmetric roof-boundary exclusion",
                    **_metric_row(counts),
                    **replay_audit,
                    "fixed_class_png_sha256": inventory["semantic_mask_sha256"],
                    "cache_npz_sha256": inventory["cache_sha256"],
                    "manifest_input_hashes_json": "",
                    "notes": (
                        "fixed class PNG is authoritative; ID-roof = actual_label==1 and "
                        "actual_bidmap>=0; replay pixel delta is recorded, not a provenance gate"
                    ),
                }
            )

            for building_id in context["building_ids"]:
                support = actual_bidmap == mesh_index[building_id]
                if np.any(support):
                    building_views_visible[building_id] += 1
                part = agreement_counts(
                    fixed_roof,
                    idmap_roof,
                    domain=support,
                    extra_boundary_masks=(support,),
                )
                if part["evaluable_pixels"] > 0:
                    building_views_evaluable[building_id] += 1
                add_counts(building_totals[building_id], part)
                del support

            for artifact in context["priority_by_stem"].get(frame.stem, []):
                building_id = artifact["building_id"]
                full = context["full_sources"][(building_id, frame.stem)]
                full_path = repo_path(full["path"])
                with PILImage.open(full_path) as source:
                    source_overlay = source.convert("RGB")
                target_mask = actual_bidmap == mesh_index[building_id]
                staged_path = stage / f"crop_{len(staged_crops):02d}.png"
                gate_key = (building_id, frame.stem, int(artifact["rank"]))
                record = render_priority_crop_with_id_boundary(
                    staged_path,
                    source_overlay,
                    target_mask,
                    artifact,
                    context["gate_by_key"][gate_key],
                )
                staged_crops[(building_id, int(artifact["rank"]))] = staged_path
                gallery_records.append(record)
                del source_overlay, target_mask

            # Explicitly release every per-view raycast array before the next view.
            del (
                fixed_class,
                fixed_roof,
                rays_official,
                rays_actual,
                actual_label,
                actual_bidmap,
                idmap_roof,
            )
            if frame_index % 50 == 0 or frame_index == EXPECTED_VIEWS:
                print(f"[idmap-class] {frame_index}/{EXPECTED_VIEWS}", flush=True)

        _require(len(staged_crops) == EXPECTED_PRIORITY_CROPS, "did not repaint exactly nine priority crops")
        target_id_summary = summarize_priority_gallery(gallery_records)
        target_id_status_counts = target_id_summary["status_counts"]
        crop_records = [dict(record) for record in gallery_records]
        staged_contact = stage / "contact_sheet.png"
        make_contact_sheet(
            staged_crops,
            staged_contact,
            target_id_status_counts=target_id_status_counts,
        )
        contact_record = {
            "kind": "priority_contact_sheet",
            "path": context["contact"]["path"],
            "target_id_summary": target_id_summary,
            "boundary_fabricated": False,
            "sha256": REGIONS.sha256_file(staged_contact),
        }
        gallery_records.append(contact_record)
        gallery_output_sha = REGIONS.sha256_json(gallery_records)
        common = _common_row(context, gallery_output_sha, script_sha)
        rows = [{**common, **row} for row in view_rows]
        rows.append(
            {
                **common,
                "row_type": "pooled_aggregate",
                "aggregation": "pooled_pixels_over_428_views",
                "building_id": "ALL_MESH",
                "view_stem": "",
                "image_name": "",
                "views_total": EXPECTED_VIEWS,
                "views_with_building_id": EXPECTED_VIEWS,
                "views_evaluable": sum(int(row["views_evaluable"]) for row in view_rows),
                "evaluation_domain": "entire image after symmetric roof-boundary exclusion",
                **_metric_row(pooled),
                "actual_source_class_total_pixels": replay_pooled["total_pixels"],
                "actual_source_class_mismatch_pixels_inventory": replay_pooled[
                    "inventory_mismatch_pixels"
                ],
                "actual_source_class_mismatch_pixels_replay": replay_pooled[
                    "replay_mismatch_pixels"
                ],
                "actual_source_class_mismatch_pixels_delta_replay_minus_inventory": (
                    replay_pooled["replay_mismatch_pixels"]
                    - replay_pooled["inventory_mismatch_pixels"]
                ),
                "actual_source_class_agreement_inventory": (
                    1.0
                    - replay_pooled["inventory_mismatch_pixels"]
                    / replay_pooled["total_pixels"]
                ),
                "actual_source_class_agreement_replay": (
                    1.0
                    - replay_pooled["replay_mismatch_pixels"]
                    / replay_pooled["total_pixels"]
                ),
                "actual_source_class_agreement_delta_replay_minus_inventory": (
                    (
                        replay_pooled["inventory_mismatch_pixels"]
                        - replay_pooled["replay_mismatch_pixels"]
                    )
                    / replay_pooled["total_pixels"]
                ),
                # The inventory stores per-view roof IoU but not its additive
                # intersection/union, so a pooled inventory delta is intentionally blank.
                "actual_source_roof_iou_inventory": "",
                "actual_source_roof_iou_replay": "",
                "actual_source_roof_iou_delta_replay_minus_inventory": "",
                "actual_source_replay_inventory_exact_match": (
                    replay_pooled["replay_mismatch_pixels"]
                    == replay_pooled["inventory_mismatch_pixels"]
                ),
                "actual_source_roof_membership_mismatch_boundary_excluded_pixels_replay": replay_pooled[
                    "roof_mismatch_boundary_excluded_pixels"
                ],
                "actual_source_roof_membership_mismatch_evaluable_pixels_replay": replay_pooled[
                    "roof_mismatch_evaluable_pixels"
                ],
                "fixed_class_png_sha256": "",
                "cache_npz_sha256": "",
                "manifest_input_hashes_json": json.dumps(
                    context["input_hash_set"], sort_keys=True, ensure_ascii=False, separators=(",", ":")
                ),
                "notes": (
                    "pooled numerator/denominator counts; never mean of per-view ratios; "
                    "raw inventory/replay class agreement is recomputed from pooled mismatch pixels"
                ),
            }
        )
        for building_id in context["building_ids"]:
            rows.append(
                {
                    **common,
                    "row_type": "building_aggregate",
                    "aggregation": "pooled_pixels_over_428_views_with_exact_raycast_building_id",
                    "building_id": building_id,
                    "view_stem": "",
                    "image_name": "",
                    "views_total": EXPECTED_VIEWS,
                    "views_with_building_id": building_views_visible[building_id],
                    "views_evaluable": building_views_evaluable[building_id],
                    "evaluation_domain": (
                        "pixels addressed to this actual-source raycast building ID, after roof "
                        "and building-ID one-pixel boundary exclusions"
                    ),
                    **_metric_row(building_totals[building_id]),
                    "fixed_class_png_sha256": "",
                    "cache_npz_sha256": "",
                    "manifest_input_hashes_json": "",
                    "notes": "building-ID is used only to define the aggregation domain",
                }
            )

        staged_csv = stage / OUTPUT_CSV.name
        _write_csv(staged_csv, rows)
        durable_manifest = build_durable_output_manifest(
            context,
            staged_csv=staged_csv,
            crop_records=crop_records,
            contact_record=contact_record,
            target_id_summary=target_id_summary,
            gallery_output_set_sha256=gallery_output_sha,
            supplement_script_sha256=script_sha,
        )
        staged_manifest = stage / OUTPUT_MANIFEST.name
        staged_manifest.write_text(
            json.dumps(durable_manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        parsed_staged_manifest = json.loads(staged_manifest.read_text(encoding="utf-8"))
        _require(
            parsed_staged_manifest == durable_manifest,
            "durable manifest JSON round-trip changed the staged ledger",
        )
        validate_staged_output_bundle(
            parsed_staged_manifest,
            staged_csv=staged_csv,
            staged_crops=staged_crops,
            staged_contact=staged_contact,
        )
        durable_manifest_sha256 = REGIONS.sha256_file(staged_manifest)
        output_set_sha256 = durable_manifest["outputs"]["output_set_sha256"]

        # Every staged file has passed QA.  Remove an older commit marker first
        # so an interrupted replace can never leave a manifest claiming that a
        # partial new bundle is complete.  The new manifest is replaced last.
        if OUTPUT_MANIFEST.exists():
            os.replace(OUTPUT_MANIFEST, stage / "superseded_output_manifest.json")
        for artifact in context["priority"]:
            key = (artifact["building_id"], int(artifact["rank"]))
            destination = repo_path(artifact["path"])
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.replace(staged_crops[key], destination)
        contact_destination = repo_path(context["contact"]["path"])
        os.replace(staged_contact, contact_destination)
        os.replace(staged_csv, OUTPUT_CSV)
        os.replace(staged_manifest, OUTPUT_MANIFEST)

    return {
        "csv": rel(OUTPUT_CSV),
        "rows": len(rows),
        "view_rows": EXPECTED_VIEWS,
        "building_rows": len(context["building_ids"]),
        "priority_crops_repainted": EXPECTED_PRIORITY_CROPS,
        "priority_unique_views": len(context["priority_by_stem"]),
        "contact_sheet": context["contact"]["path"],
        "source_manifest_sha256": context["manifest_sha256"],
        "output_manifest": rel(OUTPUT_MANIFEST),
        "output_manifest_sha256": durable_manifest_sha256,
        "output_set_sha256": output_set_sha256,
        "gallery_output_set_sha256": gallery_output_sha,
        "priority_target_id_summary": target_id_summary,
        "priority_gallery_records": [
            record for record in gallery_records if "building_id" in record
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run(args.manifest)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
