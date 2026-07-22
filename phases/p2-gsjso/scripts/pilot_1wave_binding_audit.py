#!/usr/bin/env python3
"""P1W-BINDING-AUDIT: fail-closed crop-to-score identity audit.

This program is deliberately independent of training, Roofer, and the metric
implementation.  It re-opens the immutable receipts produced by those stages,
checks their byte hashes, and proves that the ordered pilot population is the
same population at every boundary:

    crop contract -> classified scene receipt -> Roofer roofprints
    -> raw CityJSONSeq feature/root Building -> merged CityJSON parent
    -> per-building score row

Names and set equality alone are not sufficient.  A 30 x 30 spatial ownership
matrix compares every locked footprint with every output parent's union of
``RoofSurface`` XY (the parent plus its uniquely-owned children).  Consequently
two buildings whose labels were exchanged fail even when all 30 labels remain
present.  Empty/fallback outputs are reported explicitly and are never assigned
invented geometry.

The script is CPU-only and imports neither torch nor Roofer.  It is intended to
run in the pinned ``jointbuildgs-p0-tools:t0`` image.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
from shapely.geometry import GeometryCollection, MultiPolygon, Polygon, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union
from shapely.validation import make_valid


REPO = Path(__file__).resolve().parents[3]
CONTAINER_REPO = Path("/workspace/JointBuildGS")
TASK_ID = "P1W-BINDING-AUDIT"
SCHEMA_VERSION = "jointbuildgs.pilot_1wave.binding_audit.v1"
MATRIX_SCHEMA_VERSION = "jointbuildgs.pilot_1wave.binding_matrix.v1"
RECEIPT_SCHEMA_VERSION = "jointbuildgs.pilot_1wave.binding_receipt.v1"
CRS = "EPSG:25832"
EXPECTED_POPULATION = 30
EXPECTED_CONDITIONS = ("01", "02", "03", "04a", "04b")
EXPECTED_SEEDS = (1001, 1002)
ROOFER_EXECUTION_SCHEMA = "jointbuildgs.pilot_1wave.roofer_execution.v1"
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

PILOT_SET_SHA256 = (
    "db5ecb6c838499dd3a5f96a4b1abae85414c3d38318d976b7ee598982b566ffc"
)
PILOT_MANIFEST_SHA256 = (
    "803d18862db926fff353c641e08a03c5938cedf3fb49cc4859751189e83855e2"
)
ORDERED_IDS_SHA256 = (
    "ae5cbc664941c3b8bb4238767f1d0833a1f7684928a03837047065f85093bb01"
)
PILOT_CROP_CONTRACT_SHA256 = (
    "6d0b4b9136a51e8a5483025fe45c3dba962c71d32dbdc97a11358ae8f0385dda"
)
SELECTION_SHA256 = (
    "e98daa670a0753198e8a54502b260a07bcefe2bca42976931c0a08b766c5b3cd"
)
LOCKED_CROP_BBOX = (690764.89, 5335918.4, 690964.53, 5336202.0)
LOCKED_CROP_AREA_M2 = 56_617.904
LOCKED_IDS = (
    "DEBY_LOD2_4906966",
    "DEBY_LOD2_4907178",
    "DEBY_LOD2_4907183",
    "DEBY_LOD2_4907184",
    "DEBY_LOD2_4907185",
    "DEBY_LOD2_4907186",
    "DEBY_LOD2_4907188",
    "DEBY_LOD2_4907195",
    "DEBY_LOD2_4907196",
    "DEBY_LOD2_4907198",
    "DEBY_LOD2_4907201",
    "DEBY_LOD2_4907202",
    "DEBY_LOD2_4907204",
    "DEBY_LOD2_4907205",
    "DEBY_LOD2_4907206",
    "DEBY_LOD2_4908168",
    "DEBY_LOD2_4908178",
    "DEBY_LOD2_60098",
    "DEBY_LOD2_4907207",
    "DEBY_LOD2_4907165",
    "DEBY_LOD2_4907177",
    "DEBY_LOD2_4907179",
    "DEBY_LOD2_42364665",
    "DEBY_LOD2_4906965",
    "DEBY_LOD2_42364667",
    "DEBY_LOD2_4907176",
    "DEBY_LOD2_4907180",
    "DEBY_LOD2_4906967",
    "DEBY_LOD2_4908023",
    "DEBY_LOD2_4908024",
)

BUILDING_FIELDS = (
    "schema_version",
    "condition_id",
    "seed",
    "selection_rank",
    "expected_building_id",
    "crop_contract_sha256",
    "scene_npz_path",
    "scene_npz_sha256",
    "scene_provenance_path",
    "scene_provenance_sha256",
    "classification_receipt_path",
    "classification_receipt_sha256",
    "roofprint_prepare_marker_path",
    "roofprint_prepare_marker_sha256",
    "roofprint_path",
    "roofprint_sha256",
    "roofprint_feature_index",
    "roofprint_building_id",
    "roofprint_geometry_sha256",
    "classified_pointcloud_path",
    "classified_pointcloud_sha256",
    "roofer_marker_path",
    "roofer_marker_sha256",
    "roofer_execution_receipt_path",
    "roofer_execution_receipt_sha256",
    "jsonseq_path",
    "jsonseq_sha256",
    "jsonseq_line_number",
    "jsonseq_feature_id",
    "jsonseq_feature_sha256",
    "merged_cityjson_path",
    "merged_cityjson_sha256",
    "merged_parent_id",
    "merged_parent_record_sha256",
    "owned_child_ids",
    "owned_child_count",
    "roof_union_area_m2",
    "zero_roof",
    "fallback_flag",
    "fallback_reason",
    "raw_merged_geometry_match",
    "score_marker_path",
    "score_marker_sha256",
    "score_csv_path",
    "score_csv_sha256",
    "score_row_index",
    "score_building_id",
    "score_row_sha256",
    "crop_contract_sha_match",
    "classification_receipt_sha_match",
    "crop_id_match",
    "receipt_id_match",
    "roofprint_id_match",
    "jsonseq_id_match",
    "merged_parent_id_match",
    "score_id_match",
    "spatial_owner_candidate_count",
    "spatial_owner_building_id",
    "spatial_owner_selection_rank",
    "spatial_owner_ratio",
    "spatial_owner_unique",
    "spatial_owner_matches_parent",
    "cityjson_owner_match",
    "containment_tolerance_m2",
    "outside_owner_area_m2",
    "owner_containment_ratio",
    "owner_contained",
    "strongest_offdiag_building_id",
    "strongest_offdiag_ratio",
    "all_four_match",
    "binding_gate_pass",
)

MATRIX_FIELDS = (
    "schema_version",
    "condition_id",
    "seed",
    "locked_selection_rank",
    "locked_building_id",
    "output_selection_rank",
    "output_parent_id",
    "locked_footprint_area_m2",
    "output_roof_union_area_m2",
    "intersection_area_m2",
    "intersection_over_output_roof",
    "is_diagonal",
    "output_zero_roof",
    "argmax_candidate_count",
    "is_column_argmax",
    "owner_assignment",
    "assigned_owner_building_id",
    "assigned_owner_selection_rank",
    "containment_tolerance_m2",
    "outside_assigned_owner_area_m2",
    "assigned_owner_containment_ratio",
    "assigned_owner_contained",
)


@dataclass(frozen=True)
class RunInputs:
    condition_id: str
    seed: int
    pilot_set: Path
    pilot_manifest: Path
    scene_npz: Path
    scene_provenance: Path
    classification_receipt: Path
    roofprint_prepare_marker: Path
    roofer_marker: Path
    merged_cityjson: Path
    score_marker: Path
    score_csv: Path


@dataclass(frozen=True)
class PilotLock:
    ids: tuple[str, ...]
    ranks: tuple[int, ...]
    pilot_set_path: Path
    pilot_set_sha256: str
    manifest_path: Path
    manifest_sha256: str
    selection_sha256: str
    ordered_ids_sha256: str


@dataclass(frozen=True)
class RawFeature:
    building_id: str
    source_path: Path
    source_sha256: str
    line_number: int
    feature_sha256: str
    roof_union: BaseGeometry


_SHA256_CACHE: dict[tuple[str, int, int, int], str] = {}
SHA256_CACHE_MIN_BYTES = 64 * 1024 * 1024


def sha256_file(path: Path, block_size: int = 1 << 20) -> str:
    path = path.resolve()
    stat = path.stat()
    cache_key = (str(path), int(stat.st_ino), int(stat.st_size), int(stat.st_mtime_ns))
    if stat.st_size >= SHA256_CACHE_MIN_BYTES:
        cached = _SHA256_CACHE.get(cache_key)
        if cached is not None:
            return cached
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(block_size), b""):
            digest.update(block)
    value = digest.hexdigest()
    if stat.st_size >= SHA256_CACHE_MIN_BYTES:
        _SHA256_CACHE[cache_key] = value
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def require_equal(actual: Any, expected: Any, label: str) -> None:
    if actual != expected:
        raise RuntimeError(f"{label} drift: {actual!r} != {expected!r}")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def require_exact_unique_ids(
    actual: Sequence[str], expected: Sequence[str], label: str
) -> None:
    require_equal(len(actual), len(expected), f"{label} count")
    require_equal(len(set(actual)), len(actual), f"{label} uniqueness")
    require_equal(set(actual), set(expected), f"{label} set")


def load_json(path: Path, label: str) -> dict[str, Any]:
    path = path.resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{label} is invalid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"{label} root must be an object: {path}")
    return value


def resolve_declared_path(value: Any, *, declaring_file: Path) -> Path:
    text = str(value or "").strip()
    if not text:
        raise RuntimeError(f"empty artifact path declared by {declaring_file}")
    declared = Path(text)
    candidates: list[Path] = []
    if declared.is_absolute():
        candidates.append(declared)
        try:
            candidates.append(REPO / declared.relative_to(CONTAINER_REPO))
        except ValueError:
            pass
    else:
        candidates.extend((declaring_file.parent / declared, REPO / declared))
    existing = {candidate.resolve() for candidate in candidates if candidate.exists()}
    if not existing:
        raise FileNotFoundError(f"declared artifact is missing: {text} ({declaring_file})")
    if len(existing) != 1:
        raise RuntimeError(f"ambiguous artifact path: {text} -> {sorted(map(str, existing))}")
    return next(iter(existing))


def resolve_and_hash(
    record: Mapping[str, Any],
    *,
    declaring_file: Path,
    label: str,
    path_key: str = "path",
    sha_key: str = "sha256",
) -> Path:
    if path_key not in record or sha_key not in record:
        raise RuntimeError(f"{label} must declare {path_key} and {sha_key}")
    path = resolve_declared_path(record[path_key], declaring_file=declaring_file)
    require_equal(sha256_file(path), record[sha_key], f"{label} SHA256")
    return path


def _verify_nested_artifacts(value: Any, *, declaring_file: Path, label: str = "root") -> None:
    """Re-open every conventional path/SHA pair in a receipt.

    This is supplemental to semantic validation below.  Both nested
    ``{"path", "sha256"}`` records and flat ``foo_path``/``foo_sha256`` pairs
    are recognized.  Embedded checkpoint/config records are therefore checked
    too, rather than trusting an earlier validation process.
    """

    if isinstance(value, Mapping):
        if "path" in value and "sha256" in value:
            resolve_and_hash(value, declaring_file=declaring_file, label=label)
        for key, raw_path in value.items():
            if key.endswith("_path"):
                sha_key = key[: -len("_path")] + "_sha256"
                if sha_key in value and raw_path not in (None, ""):
                    path = resolve_declared_path(raw_path, declaring_file=declaring_file)
                    require_equal(
                        sha256_file(path), value[sha_key], f"{label}.{key} SHA256"
                    )
        for key, child in value.items():
            _verify_nested_artifacts(child, declaring_file=declaring_file, label=f"{label}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _verify_nested_artifacts(
                child, declaring_file=declaring_file, label=f"{label}[{index}]"
            )


def read_csv(path: Path, label: str) -> list[dict[str, str]]:
    path = path.resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None:
            raise RuntimeError(f"{label} has no header: {path}")
        rows = [dict(row) for row in reader]
    return rows


def load_pilot_lock(
    pilot_set: Path,
    manifest_path: Path,
    *,
    strict_locked_population: bool = True,
) -> PilotLock:
    pilot_set = pilot_set.resolve()
    manifest_path = manifest_path.resolve()
    pilot_sha = sha256_file(pilot_set)
    manifest_sha = sha256_file(manifest_path)
    rows = read_csv(pilot_set, "pilot set")
    require(bool(rows), "pilot set is empty")
    try:
        ranks = tuple(int(row["selection_rank"]) for row in rows)
        ids = tuple(str(row["building_id"]) for row in rows)
    except (KeyError, ValueError) as exc:
        raise RuntimeError("pilot set lacks valid selection_rank/building_id") from exc
    require_equal(ranks, tuple(range(1, len(rows) + 1)), "pilot selection ranks")
    require_equal(len(set(ids)), len(ids), "pilot building ID uniqueness")
    require(all(ids), "pilot set contains an empty building ID")

    manifest = load_json(manifest_path, "pilot manifest")
    selection = manifest.get("selection")
    if not isinstance(selection, Mapping):
        raise RuntimeError("pilot manifest lacks selection")
    require_equal(
        tuple(str(value) for value in selection.get("selected_ids_in_rank_order", [])),
        ids,
        "pilot CSV/manifest ordered IDs",
    )
    require_equal(int(selection.get("selection_count", -1)), len(ids), "pilot count")
    selection_sha = str(selection.get("selection_sha256", ""))
    ordered_sha = str(selection.get("ordered_ids_sha256", ""))
    require(bool(selection_sha and ordered_sha), "pilot manifest lacks selection hashes")
    if strict_locked_population:
        require_equal(len(ids), EXPECTED_POPULATION, "locked pilot population")
        require_equal(ids, LOCKED_IDS, "locked pilot ordered IDs")
        require_equal(pilot_sha, PILOT_SET_SHA256, "locked pilot CSV SHA256")
        require_equal(manifest_sha, PILOT_MANIFEST_SHA256, "locked pilot manifest SHA256")
        require_equal(selection_sha, SELECTION_SHA256, "locked selection SHA256")
        require_equal(ordered_sha, ORDERED_IDS_SHA256, "locked ordered-ID SHA256")
    return PilotLock(
        ids=ids,
        ranks=ranks,
        pilot_set_path=pilot_set,
        pilot_set_sha256=pilot_sha,
        manifest_path=manifest_path,
        manifest_sha256=manifest_sha,
        selection_sha256=selection_sha,
        ordered_ids_sha256=ordered_sha,
    )


def _npz_scalar_text(payload: Mapping[str, Any], key: str) -> str:
    if key not in payload:
        raise RuntimeError(f"scene NPZ lacks {key}")
    value = np.asarray(payload[key])
    if value.shape != () or value.dtype.kind not in {"U", "S"}:
        raise RuntimeError(f"scene NPZ {key} must be a scalar non-object string")
    scalar = value.item()
    if isinstance(scalar, bytes):
        scalar = scalar.decode("utf-8")
    return str(scalar)


def validate_crop_and_provenance(
    inputs: RunInputs,
    lock: PilotLock,
    *,
    strict_locked_population: bool,
) -> dict[str, Any]:
    scene_npz = inputs.scene_npz.resolve()
    if not scene_npz.is_file():
        raise FileNotFoundError(scene_npz)
    try:
        with np.load(scene_npz, allow_pickle=False) as payload:
            crop_json = _npz_scalar_text(payload, "crop_contract_json")
            crop_sha = _npz_scalar_text(payload, "crop_contract_sha256")
            lineage_json = _npz_scalar_text(payload, "readout_lineage_json")
    except ValueError as exc:
        raise RuntimeError("scene NPZ provenance must not require pickle") from exc
    require_equal(
        hashlib.sha256(crop_json.encode("utf-8")).hexdigest(),
        crop_sha,
        "scene crop contract JSON/SHA256",
    )
    if strict_locked_population:
        require_equal(crop_sha, PILOT_CROP_CONTRACT_SHA256, "locked crop-contract SHA256")
    try:
        crop = json.loads(crop_json)
        lineage = json.loads(lineage_json)
    except json.JSONDecodeError as exc:
        raise RuntimeError("scene NPZ contains invalid crop/lineage JSON") from exc
    if not isinstance(crop, Mapping) or not isinstance(lineage, Mapping):
        raise RuntimeError("scene crop/lineage JSON roots must be objects")
    population = crop.get("population")
    crop_record = crop.get("crop")
    if not isinstance(population, Mapping) or not isinstance(crop_record, Mapping):
        raise RuntimeError("crop contract lacks crop/population records")
    crop_ids = tuple(str(value) for value in population.get("ordered_building_ids", []))
    require_equal(crop_ids, lock.ids, "crop contract ordered IDs")
    require_equal(int(population.get("count", -1)), len(lock.ids), "crop population")
    require_equal(
        population.get("ordered_ids_sha256"), lock.ordered_ids_sha256, "crop ordered-ID SHA256"
    )
    pilot_record = crop.get("pilot_set_csv")
    if not isinstance(pilot_record, Mapping):
        raise RuntimeError("crop contract lacks pilot_set_csv")
    require_equal(
        pilot_record.get("sha256"), lock.pilot_set_sha256, "crop/pilot CSV SHA256"
    )
    manifest_record = crop.get("pilot_set_manifest")
    if not isinstance(manifest_record, Mapping):
        raise RuntimeError("crop contract lacks pilot_set_manifest")
    require_equal(
        manifest_record.get("sha256"),
        lock.manifest_sha256,
        "crop/pilot manifest SHA256",
    )
    bbox = tuple(float(value) for value in crop_record.get("bbox_utm", []))
    require_equal(len(bbox), 4, "crop bbox coordinate count")
    require_equal(str(crop.get("crs")), CRS, "crop CRS")
    require_equal(str(crop_record.get("mode")), "single_locked_global_bbox", "crop mode")
    if strict_locked_population:
        require_equal(bbox, LOCKED_CROP_BBOX, "locked global crop bbox")
        require(
            math.isclose(
                float(crop_record.get("area_m2", math.nan)),
                LOCKED_CROP_AREA_M2,
                rel_tol=0.0,
                abs_tol=1e-6,
            ),
            "locked global crop area drift",
        )
    require_equal(str(lineage.get("condition_id")), inputs.condition_id, "NPZ condition")
    require_equal(int(lineage.get("seed", -1)), inputs.seed, "NPZ seed")
    require_equal(lineage.get("crop_contract_sha256"), crop_sha, "lineage crop SHA256")
    require_equal(lineage.get("crop_contract_json"), crop_json, "lineage crop JSON")

    provenance_path = inputs.scene_provenance.resolve()
    provenance = load_json(provenance_path, "scene provenance")
    require_equal(provenance.get("state"), "complete", "scene provenance state")
    require_equal(provenance.get("geometry_only"), True, "scene geometry-only flag")
    require_equal(provenance.get("crs"), CRS, "scene provenance CRS")
    output_npz = provenance.get("output_npz")
    if not isinstance(output_npz, Mapping):
        raise RuntimeError("scene provenance lacks output_npz")
    declared_npz = resolve_and_hash(
        output_npz, declaring_file=provenance_path, label="scene provenance output NPZ"
    )
    require_equal(declared_npz, scene_npz, "scene provenance NPZ path")
    require_equal(provenance.get("crop_contract_json"), crop_json, "provenance crop JSON")
    require_equal(provenance.get("crop_contract_sha256"), crop_sha, "provenance crop SHA256")
    require_equal(provenance.get("readout_lineage"), lineage, "NPZ/provenance lineage")
    _verify_nested_artifacts(provenance, declaring_file=provenance_path, label="scene_provenance")
    return {
        "crop": dict(crop),
        "crop_json": crop_json,
        "crop_sha256": crop_sha,
        "lineage": dict(lineage),
        "scene_npz_path": scene_npz,
        "scene_npz_sha256": sha256_file(scene_npz),
        "provenance_path": provenance_path,
        "provenance_sha256": sha256_file(provenance_path),
    }


def _crs_is_25832(payload: Mapping[str, Any]) -> bool:
    crs = payload.get("crs")
    if not isinstance(crs, Mapping):
        return False
    properties = crs.get("properties")
    if not isinstance(properties, Mapping):
        return False
    name = str(properties.get("name", ""))
    return name.rstrip("/").replace("::", ":").rsplit(":", 1)[-1].rsplit("/", 1)[-1] == "25832"


def _polygonal(value: BaseGeometry, label: str) -> BaseGeometry:
    if value.is_empty:
        return GeometryCollection()
    fixed = make_valid(value) if not value.is_valid else value
    if isinstance(fixed, (Polygon, MultiPolygon)):
        return fixed
    if isinstance(fixed, GeometryCollection):
        parts = [item for item in fixed.geoms if isinstance(item, (Polygon, MultiPolygon))]
        if parts:
            return unary_union(parts)
    raise RuntimeError(f"{label} is not polygonal after validity repair")


def _coordinate_dimensions(value: Any) -> Iterable[int]:
    if isinstance(value, list):
        if value and all(isinstance(item, (int, float)) for item in value):
            yield len(value)
        else:
            for item in value:
                yield from _coordinate_dimensions(item)


def load_roofprints(path: Path, expected_ids: Sequence[str]) -> dict[str, Any]:
    payload = load_json(path, "roofprints")
    require(payload.get("type") == "FeatureCollection", "roofprints must be a FeatureCollection")
    require(_crs_is_25832(payload), "roofprint CRS is not EPSG:25832")
    features = payload.get("features")
    if not isinstance(features, list):
        raise RuntimeError("roofprint features must be an array")
    ids: list[str] = []
    polygons: list[BaseGeometry] = []
    geometry_hashes: list[str] = []
    geometry_identity_records: list[dict[str, Any]] = []
    feature_properties: list[Mapping[str, Any]] = []
    for index, feature in enumerate(features):
        if not isinstance(feature, Mapping):
            raise RuntimeError(f"roofprint feature {index} is not an object")
        require_equal(feature.get("type"), "Feature", f"roofprint feature type {index}")
        properties = feature.get("properties")
        geometry = feature.get("geometry")
        if not isinstance(properties, Mapping) or not isinstance(geometry, Mapping):
            raise RuntimeError(f"roofprint feature {index} lacks properties/geometry")
        building_id = str(properties.get("building_id", ""))
        require(bool(building_id), f"roofprint feature {index} has no building_id")
        require_equal(
            dict(properties),
            {
                "building_id": building_id,
                "selection_rank": index + 1,
                "class": 6,
            },
            f"roofprint properties for {building_id}",
        )
        require(
            geometry.get("type") in {"Polygon", "MultiPolygon"},
            f"roofprint geometry type drift for {building_id}",
        )
        dimensions = list(_coordinate_dimensions(geometry.get("coordinates")))
        require(
            bool(dimensions) and all(value == 2 for value in dimensions),
            f"roofprint is not XY-only: {building_id}",
        )
        ids.append(building_id)
        try:
            polygon = _polygonal(shape(dict(geometry)), f"roofprint {building_id}")
        except (TypeError, ValueError) as exc:
            raise RuntimeError(f"invalid roofprint geometry for {building_id}") from exc
        require(not polygon.is_empty and polygon.area > 0.0, f"empty roofprint: {building_id}")
        require(math.isfinite(float(polygon.area)), f"non-finite roofprint area: {building_id}")
        polygons.append(polygon)
        geometry_hashes.append(sha256_json(geometry))
        geometry_identity_records.append(
            {"building_id": building_id, "geometry": dict(geometry)}
        )
        feature_properties.append(dict(properties))
    require_equal(tuple(ids), tuple(expected_ids), "roofprint ordered building IDs")
    require_equal(len(set(ids)), len(ids), "roofprint building ID uniqueness")
    return {
        "path": path.resolve(),
        "sha256": sha256_file(path.resolve()),
        "ids": tuple(ids),
        "polygons": tuple(polygons),
        "geometry_hashes": tuple(geometry_hashes),
        "ordered_feature_geometry_sha256": sha256_json(geometry_identity_records),
        "feature_properties": tuple(feature_properties),
    }


def validate_roofprint_record(
    record: Mapping[str, Any],
    roofprints: Mapping[str, Any],
    expected_ids: Sequence[str],
    *,
    label: str,
) -> None:
    """Compare all normalized footprint fields, including per-feature identity."""

    require_equal(record.get("sha256"), roofprints["sha256"], f"{label} SHA256")
    count = record.get("feature_count", record.get("count"))
    require_equal(int(count if count is not None else -1), len(expected_ids), f"{label} count")
    ids = record.get("building_ids", record.get("ordered_building_ids"))
    require_equal(tuple(str(value) for value in (ids or [])), tuple(expected_ids), f"{label} IDs")
    require_equal(record.get("crs"), CRS, f"{label} CRS")
    dimension = record.get("coordinate_dimension")
    require_equal(int(dimension if dimension is not None else -1), 2, f"{label} coordinate dimension")
    declared_geometry_hash = record.get("ordered_feature_geometry_sha256")
    if isinstance(declared_geometry_hash, list):
        require_equal(
            tuple(str(value) for value in declared_geometry_hash),
            roofprints["geometry_hashes"],
            f"{label} ordered feature geometry SHA256 list",
        )
    else:
        require_equal(
            declared_geometry_hash,
            roofprints["ordered_feature_geometry_sha256"],
            f"{label} ordered feature geometry SHA256",
        )
    properties = record.get("feature_properties")
    require_equal(
        tuple(dict(value) for value in (properties or [])),
        roofprints["feature_properties"],
        f"{label} feature properties",
    )


def _record_path_sha(
    payload: Mapping[str, Any],
    *,
    declaring_file: Path,
    label: str,
    nested_keys: Sequence[str],
    flat_prefixes: Sequence[str],
) -> tuple[Path, str]:
    """Read one mandatory artifact record while allowing v2's named nesting."""

    for key in nested_keys:
        record = payload.get(key)
        if isinstance(record, Mapping) and "path" in record and "sha256" in record:
            path = resolve_and_hash(record, declaring_file=declaring_file, label=label)
            return path, str(record["sha256"])
    for prefix in flat_prefixes:
        path_key = f"{prefix}_path"
        sha_key = f"{prefix}_sha256"
        if path_key in payload and sha_key in payload:
            path = resolve_declared_path(payload[path_key], declaring_file=declaring_file)
            digest = sha256_file(path)
            require_equal(digest, payload[sha_key], f"{label} SHA256")
            return path, digest
    raise RuntimeError(f"{label} path/SHA record is missing")


def validate_prepare_marker(
    marker_path: Path,
    lock: PilotLock,
    *,
    expected_condition: str,
    expected_seed: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    marker_path = marker_path.resolve()
    marker = load_json(marker_path, "roofprint prepare marker")
    require_equal(marker.get("state"), "prepared", "roofprint prepare state")
    require_equal(
        marker.get("schema"),
        "jointbuildgs.pilot_1wave.roofer_prepare.v1",
        "roofprint prepare schema",
    )
    require_equal(
        str(marker.get("condition_id", "")), expected_condition, "prepare condition"
    )
    require_equal(int(marker.get("seed", -1)), int(expected_seed), "prepare seed")
    _verify_nested_artifacts(marker, declaring_file=marker_path, label="roofprint_prepare")
    output_path, output_sha = _record_path_sha(
        marker,
        declaring_file=marker_path,
        label="prepared roofprints",
        nested_keys=("footprints", "roofprints", "output_roofprints", "output"),
        flat_prefixes=("roofprints", "output_roofprints", "output"),
    )
    roofprints = load_roofprints(output_path, lock.ids)
    require_equal(roofprints["sha256"], output_sha, "prepared roofprint SHA256")
    marker_roofprints = next(
        (
            marker[key]
            for key in ("footprints", "roofprints", "output_roofprints", "output")
            if isinstance(marker.get(key), Mapping)
            and marker[key].get("path") is not None
        ),
        None,
    )
    if not isinstance(marker_roofprints, Mapping):
        raise RuntimeError("roofprint prepare marker lacks normalized footprint record")
    validate_roofprint_record(
        marker_roofprints, roofprints, lock.ids, label="prepared roofprints"
    )
    require_equal(marker.get("selection_sha256"), lock.selection_sha256, "prepare selection SHA256")
    require_equal(marker.get("ordered_ids_sha256"), lock.ordered_ids_sha256, "prepare ordered-ID SHA256")
    marker_ids = marker.get("ordered_building_ids")
    if marker_ids is None:
        for key in ("roofprints", "output_roofprints", "output"):
            record = marker.get(key)
            if isinstance(record, Mapping) and record.get("building_ids") is not None:
                marker_ids = record.get("building_ids")
                break
    require_equal(tuple(str(value) for value in (marker_ids or [])), lock.ids, "prepare ordered IDs")
    return marker, roofprints


def validate_argv_record(
    record_value: Any,
    *,
    declaring_file: Path,
    label: str,
    expected_condition: str,
    expected_seed: int,
) -> dict[str, Any]:
    if not isinstance(record_value, Mapping):
        raise RuntimeError(f"{label} must be an artifact record")
    path = resolve_and_hash(
        record_value, declaring_file=declaring_file, label=label
    )
    payload = load_json(path, label)
    require_equal(
        payload.get("schema"),
        "jointbuildgs.pilot_1wave.roofer_argv.v1",
        f"{label} schema",
    )
    require_equal(payload.get("condition_id"), expected_condition, f"{label} condition")
    require_equal(int(payload.get("seed", -1)), int(expected_seed), f"{label} seed")
    require_equal(payload.get("image"), ROOFER_IMAGE, f"{label} image")
    for field in ("schema", "image", "arguments"):
        require_equal(record_value.get(field), payload.get(field), f"{label} {field}")
    require(isinstance(payload.get("arguments"), list), f"{label} arguments must be an array")
    return {"path": path, "sha256": sha256_file(path), "payload": payload}


def repo_relative(path: Path) -> str:
    path = path.resolve()
    try:
        return path.relative_to(REPO.resolve()).as_posix()
    except ValueError as exc:
        raise RuntimeError(f"binding artifact is outside repository: {path}") from exc


def validate_execution_artifact_record(
    value: Any,
    *,
    declaring_file: Path,
    expected_path: Path,
    label: str,
    include_size: bool = False,
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise RuntimeError(f"{label} must be an artifact record")
    expected_path = expected_path.resolve()
    require(not expected_path.is_symlink(), f"{label} must not be a symlink")
    path = resolve_and_hash(value, declaring_file=declaring_file, label=label)
    require_equal(path, expected_path, f"{label} path")
    normalized: dict[str, Any] = {
        "path": repo_relative(path),
        "sha256": sha256_file(path),
    }
    if include_size:
        normalized["size"] = path.stat().st_size
    require_equal(dict(value), normalized, f"{label} record")
    return normalized


def validate_execution_binding(
    marker: Mapping[str, Any],
    *,
    marker_path: Path,
    inputs: RunInputs,
    prepare_path: Path,
    prepare_sha256: str,
    argv: Mapping[str, Any],
) -> dict[str, Any]:
    """Re-open the retained-container receipt and normalized execution facts."""

    execution_record = marker.get("execution_receipt")
    if not isinstance(execution_record, Mapping):
        raise RuntimeError("Roofer v2 marker lacks execution_receipt")
    output_dir = marker_path.resolve().parent
    execution_path = resolve_and_hash(
        execution_record,
        declaring_file=marker_path,
        label="Roofer execution receipt",
    )
    require_equal(
        execution_path,
        output_dir / "roofer_execution_receipt.json",
        "Roofer execution receipt path",
    )
    require_equal(
        dict(execution_record),
        {"path": repo_relative(execution_path), "sha256": sha256_file(execution_path)},
        "Roofer execution receipt record",
    )
    payload = load_json(execution_path, "Roofer execution receipt")
    require_equal(payload.get("schema"), ROOFER_EXECUTION_SCHEMA, "execution schema")
    require_equal(payload.get("state"), "complete", "execution state")
    require_equal(str(payload.get("condition_id", "")), inputs.condition_id, "execution condition")
    require_equal(int(payload.get("seed", -1)), inputs.seed, "execution seed")
    require_equal(int(payload.get("roofer_invocation_count", -1)), 1, "execution invocation count")
    expected_job_id = f"{inputs.condition_id}_seed{inputs.seed}"
    job_id = str(payload.get("job_id", "")).strip()
    require_equal(job_id, expected_job_id, "Roofer execution job_id")

    normalized_prepare = {
        "path": repo_relative(prepare_path),
        "sha256": prepare_sha256,
    }
    require_equal(payload.get("prepare_receipt"), normalized_prepare, "execution prepare receipt")
    normalized_argv = {
        "path": repo_relative(Path(str(argv["path"]))),
        "sha256": str(argv["sha256"]),
    }
    require_equal(payload.get("roofer_argv"), normalized_argv, "execution Roofer argv")
    expected_arguments = list(argv["payload"]["arguments"])
    expected_contract_sha = sha256_json(
        {
            "job_id": expected_job_id,
            "prepare_sha256": prepare_sha256,
            "argv_sha256": str(argv["sha256"]),
            "image": ROOFER_IMAGE,
            "arguments": expected_arguments,
        }
    )
    expected_container_name = (
        f"{ROOFER_CONTAINER_NAME_PREFIX}-{inputs.condition_id}-seed{inputs.seed}-roofer"
    )
    expected_repo_bind = f"{REPO.resolve()}:{ROOFER_CONTAINER_REPO}"

    container = payload.get("container")
    execution = payload.get("execution")
    if not isinstance(container, Mapping) or not isinstance(execution, Mapping):
        raise RuntimeError("Roofer execution receipt lacks container/execution facts")
    require_equal(container.get("image_reference"), ROOFER_IMAGE, "execution image reference")
    require_equal(container.get("image_id"), ROOFER_IMAGE_ID, "execution local image ID")
    require_equal(container.get("config_image"), ROOFER_IMAGE, "execution config image")
    require_equal(
        container.get("entrypoint"),
        list(ROOFER_ENTRYPOINT),
        "execution container entrypoint",
    )
    require_equal(container.get("cmd"), expected_arguments, "execution container command")
    labels = container.get("labels")
    require(isinstance(labels, Mapping), "execution container labels must be an object")
    require_equal(labels.get("jointbuildgs.p1w.job"), expected_job_id, "execution job label")
    require_equal(
        labels.get("jointbuildgs.p1w.contract"),
        expected_contract_sha,
        "execution contract label",
    )
    require_equal(container.get("network_mode"), "none", "execution network mode")
    require_equal(container.get("binds"), [expected_repo_bind], "execution repository bind")
    require_equal(int(container.get("restart_count", -1)), 0, "execution restart count")
    container_id = str(container.get("id", ""))
    require(
        re.fullmatch(r"[0-9a-f]{64}", container_id) is not None,
        "Roofer execution container ID is invalid",
    )
    container_name = str(container.get("name", "")).strip()
    require_equal(container_name, expected_container_name, "Roofer execution container name")
    require_equal(execution.get("docker_state"), "exited", "execution Docker state")
    require_equal(int(execution.get("wait_exit_code", -1)), 0, "execution wait exit code")
    require_equal(int(execution.get("start_attempt_count", -1)), 1, "execution start count")
    start_attempts = execution.get("start_attempts")
    require(isinstance(start_attempts, list), "execution start_attempts must be an array")
    require_equal(len(start_attempts), 1, "execution start-attempt ledger length")

    launch_record = validate_execution_artifact_record(
        payload.get("launch_receipt"),
        declaring_file=execution_path,
        expected_path=output_dir / "container_launch.json",
        label="Roofer launch receipt",
    )
    process_record = validate_execution_artifact_record(
        payload.get("process_receipt"),
        declaring_file=execution_path,
        expected_path=output_dir / "process_complete.json",
        label="Roofer process receipt",
    )
    log_record = validate_execution_artifact_record(
        payload.get("logs"),
        declaring_file=execution_path,
        expected_path=output_dir / "container.log",
        label="Roofer immutable log",
        include_size=True,
    )
    launch = load_json(output_dir / "container_launch.json", "Roofer launch receipt")
    process = load_json(output_dir / "process_complete.json", "Roofer process receipt")
    require_equal(launch.get("container_id"), container_id, "launch/container ID")
    require_equal(launch.get("container_name"), container_name, "launch/container name")
    require_equal(
        launch.get("contract_sha256"), expected_contract_sha, "launch contract SHA256"
    )
    require_equal(launch.get("start_attempts"), start_attempts, "launch start attempts")
    require_equal(int(launch.get("start_attempt_count", -1)), 1, "launch start count")
    require_equal(process.get("container_name"), container_name, "process/container name")
    require_equal(
        process.get("contract_sha256"), launch.get("contract_sha256"), "process/launch contract"
    )
    require_equal(int(process.get("exit_code", -1)), 0, "process exit code")
    require_equal(int(process.get("wait_exit_code", -1)), 0, "process wait exit code")
    require_equal(launch.get("job_id"), job_id, "launch job_id")
    require_equal(process.get("job_id"), job_id, "process job_id")
    normalized = {
        "schema": ROOFER_EXECUTION_SCHEMA,
        "state": "complete",
        "condition_id": inputs.condition_id,
        "seed": inputs.seed,
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
        "repo_bind": expected_repo_bind,
        "docker_state": "exited",
        "wait_exit_code": 0,
        "start_attempt_count": 1,
        "restart_count": 0,
        "launch_receipt": launch_record,
        "process_receipt": process_record,
        "logs": log_record,
    }
    require_equal(marker.get("roofer_execution"), normalized, "normalized Roofer execution")
    return {
        "path": execution_path,
        "sha256": sha256_file(execution_path),
        "normalized": normalized,
    }


def validate_classification(
    receipt_path: Path,
    inputs: RunInputs,
    lock: PilotLock,
    crop: Mapping[str, Any],
    roofprints: Mapping[str, Any],
) -> dict[str, Any]:
    receipt_path = receipt_path.resolve()
    receipt = load_json(receipt_path, "classification receipt")
    require_equal(receipt.get("state"), "complete", "classification state")
    require_equal(receipt.get("crs"), CRS, "classification CRS")
    _verify_nested_artifacts(receipt, declaring_file=receipt_path, label="classification")
    source = receipt.get("source_scene_npz")
    classified = receipt.get("classified_las")
    receipt_roofprints = receipt.get("roofprints")
    if not all(isinstance(value, Mapping) for value in (source, classified, receipt_roofprints)):
        raise RuntimeError("classification receipt lacks NPZ/LAS/roofprint records")
    source_path = resolve_and_hash(source, declaring_file=receipt_path, label="classification scene NPZ")
    require_equal(source_path, inputs.scene_npz.resolve(), "classification scene NPZ path")
    classified_path = resolve_and_hash(
        classified, declaring_file=receipt_path, label="classified pointcloud"
    )
    footprint_path = resolve_and_hash(
        receipt_roofprints, declaring_file=receipt_path, label="classification roofprints"
    )
    require_equal(footprint_path, roofprints["path"], "classification/prepared roofprint path")
    validate_roofprint_record(
        receipt_roofprints, roofprints, lock.ids, label="classification roofprints"
    )
    receipt_crop = receipt.get("crop_contract")
    if not isinstance(receipt_crop, Mapping):
        raise RuntimeError("classification receipt lacks crop_contract")
    require_equal(
        receipt_crop.get("sha256"), crop["crop_sha256"], "classification crop SHA256"
    )
    require_equal(
        tuple(str(value) for value in receipt_crop.get("ordered_building_ids", [])),
        lock.ids,
        "classification crop IDs",
    )
    require_equal(receipt.get("readout_lineage"), crop["lineage"], "classification lineage")
    return {
        "payload": receipt,
        "path": receipt_path,
        "sha256": sha256_file(receipt_path),
        "pointcloud_path": classified_path,
        "pointcloud_sha256": sha256_file(classified_path),
    }


def _semantic_surface_entries(geometry: Mapping[str, Any]) -> Iterable[tuple[Any, Any]]:
    boundaries = geometry.get("boundaries")
    semantics = geometry.get("semantics")
    if not isinstance(semantics, Mapping):
        return
    values = semantics.get("values")
    geom_type = str(geometry.get("type", ""))
    if geom_type in {"MultiSurface", "CompositeSurface"}:
        if not isinstance(boundaries, list) or not isinstance(values, list):
            return
        require_equal(len(values), len(boundaries), "MultiSurface semantics length")
        for surface, semantic_index in zip(boundaries, values):
            yield surface, semantic_index
    elif geom_type == "Solid":
        if not isinstance(boundaries, list) or not isinstance(values, list):
            return
        require_equal(len(values), len(boundaries), "Solid semantics shell count")
        for shell, shell_values in zip(boundaries, values):
            if not isinstance(shell, list) or not isinstance(shell_values, list):
                continue
            require_equal(len(shell_values), len(shell), "Solid semantics surface count")
            for surface, semantic_index in zip(shell, shell_values):
                yield surface, semantic_index
    elif geom_type in {"MultiSolid", "CompositeSolid"}:
        if not isinstance(boundaries, list) or not isinstance(values, list):
            return
        require_equal(len(values), len(boundaries), "MultiSolid semantics solid count")
        for solid, solid_values in zip(boundaries, values):
            if not isinstance(solid, list) or not isinstance(solid_values, list):
                continue
            require_equal(len(solid_values), len(solid), "MultiSolid semantics shell count")
            for shell, shell_values in zip(solid, solid_values):
                if not isinstance(shell, list) or not isinstance(shell_values, list):
                    continue
                require_equal(
                    len(shell_values), len(shell), "MultiSolid semantics surface count"
                )
                for surface, semantic_index in zip(shell, shell_values):
                    yield surface, semantic_index


def absolute_vertices(payload: Mapping[str, Any]) -> np.ndarray:
    raw = np.asarray(payload.get("vertices", []), dtype=np.float64)
    if raw.size == 0:
        return np.empty((0, 3), dtype=np.float64)
    if raw.ndim != 2 or raw.shape[1] < 2:
        raise RuntimeError(f"CityJSON vertices must be Nx2/Nx3, got {raw.shape}")
    if raw.shape[1] == 2:
        raw = np.column_stack((raw, np.zeros(len(raw), dtype=np.float64)))
    transform = payload.get("transform") or {}
    if not isinstance(transform, Mapping):
        raise RuntimeError("CityJSON transform must be an object")
    scale = np.asarray(transform.get("scale", [1.0, 1.0, 1.0]), dtype=np.float64)
    translate = np.asarray(transform.get("translate", [0.0, 0.0, 0.0]), dtype=np.float64)
    if scale.shape != (3,) or translate.shape != (3,):
        raise RuntimeError("CityJSON transform scale/translate must have length 3")
    vertices = raw[:, :3] * scale + translate
    require(bool(np.isfinite(vertices).all()), "CityJSON vertices are non-finite")
    return vertices


def _ring_polygon(surface: Any, vertices: np.ndarray, label: str) -> BaseGeometry:
    if not isinstance(surface, list) or not surface:
        return GeometryCollection()
    rings: list[list[tuple[float, float]]] = []
    for ring in surface:
        if not isinstance(ring, list) or len(ring) < 3:
            continue
        try:
            indices = np.asarray(ring, dtype=np.int64)
        except (TypeError, ValueError) as exc:
            raise RuntimeError(f"{label} has non-integer vertex indices") from exc
        if bool((indices < 0).any()) or bool((indices >= len(vertices)).any()):
            raise RuntimeError(f"{label} vertex index is out of bounds")
        xy = vertices[indices, :2]
        if len(np.unique(xy, axis=0)) < 3:
            continue
        rings.append([(float(x), float(y)) for x, y in xy])
    if not rings:
        return GeometryCollection()
    polygon = Polygon(rings[0], holes=rings[1:])
    if polygon.is_empty or polygon.area <= 0.0:
        return GeometryCollection()
    return _polygonal(polygon, label)


def object_roof_union(
    object_ids: Sequence[str],
    cityobjects: Mapping[str, Any],
    vertices: np.ndarray,
) -> BaseGeometry:
    polygons: list[BaseGeometry] = []
    for object_id in object_ids:
        obj = cityobjects.get(object_id)
        if not isinstance(obj, Mapping):
            raise RuntimeError(f"missing CityObject: {object_id}")
        geometries = obj.get("geometry", [])
        if not isinstance(geometries, list):
            raise RuntimeError(f"CityObject geometry must be an array: {object_id}")
        for geometry_index, geometry in enumerate(geometries):
            if not isinstance(geometry, Mapping):
                raise RuntimeError(f"invalid geometry for {object_id}")
            semantics = geometry.get("semantics")
            surfaces = semantics.get("surfaces", []) if isinstance(semantics, Mapping) else []
            if not isinstance(surfaces, list):
                raise RuntimeError(f"invalid semantics surfaces for {object_id}")
            for surface_index, (rings, semantic_index) in enumerate(
                _semantic_surface_entries(geometry)
            ):
                if semantic_index is None:
                    continue
                try:
                    semantic = surfaces[int(semantic_index)]
                except (IndexError, TypeError, ValueError) as exc:
                    raise RuntimeError(f"invalid semantic index for {object_id}") from exc
                if not isinstance(semantic, Mapping) or semantic.get("type") != "RoofSurface":
                    continue
                polygon = _ring_polygon(
                    rings,
                    vertices,
                    f"{object_id}/geometry{geometry_index}/surface{surface_index}",
                )
                if not polygon.is_empty:
                    polygons.append(polygon)
    return unary_union(polygons) if polygons else GeometryCollection()


def validate_ownership_graph(
    cityobjects: Mapping[str, Any],
    expected_parent_ids: Sequence[str],
    *,
    label: str,
) -> dict[str, tuple[str, ...]]:
    parent_ids_in_serialization_order = tuple(
        str(object_id)
        for object_id, obj in cityobjects.items()
        if isinstance(obj, Mapping) and obj.get("type") == "Building"
    )
    expected_parent_ids = tuple(str(value) for value in expected_parent_ids)
    require_exact_unique_ids(
        parent_ids_in_serialization_order,
        expected_parent_ids,
        f"{label} parent IDs",
    )
    ownership: dict[str, tuple[str, ...]] = {}
    child_owner: dict[str, str] = {}
    # CityObjects is an object, so insertion order is serialization detail rather
    # than identity.  Build the audit mapping in the locked order after proving
    # the exact unique parent-ID population.
    for parent_id in expected_parent_ids:
        parent = cityobjects[parent_id]
        children_raw = parent.get("children", [])
        if not isinstance(children_raw, list):
            raise RuntimeError(f"{label} parent children must be an array: {parent_id}")
        children = tuple(str(value) for value in children_raw)
        require_equal(len(set(children)), len(children), f"{label} duplicate child {parent_id}")
        for child_id in children:
            child = cityobjects.get(child_id)
            if not isinstance(child, Mapping):
                raise RuntimeError(f"{label} missing child {child_id} of {parent_id}")
            require_equal(child.get("type"), "BuildingPart", f"{label} child type {child_id}")
            child_parents = child.get("parents", [])
            require_equal(child_parents, [parent_id], f"{label} child parent {child_id}")
            if child_id in child_owner:
                raise RuntimeError(
                    f"{label} shared child {child_id}: {child_owner[child_id]} and {parent_id}"
                )
            child_owner[child_id] = parent_id
        ownership[parent_id] = children
    all_parts = {
        str(object_id)
        for object_id, obj in cityobjects.items()
        if isinstance(obj, Mapping) and obj.get("type") == "BuildingPart"
    }
    orphan_parts = sorted(all_parts - set(child_owner))
    if orphan_parts:
        raise RuntimeError(f"{label} orphan BuildingPart objects: {orphan_parts}")
    unexpected = sorted(
        set(cityobjects) - set(parent_ids_in_serialization_order) - all_parts
    )
    if unexpected:
        raise RuntimeError(f"{label} unexpected CityObject types/IDs: {unexpected}")
    return ownership


def parse_cityjsonseq_file(path: Path) -> list[tuple[int, dict[str, Any]]]:
    records: list[tuple[int, dict[str, Any]]] = []
    with path.open(encoding="utf-8") as stream:
        for line_number, raw in enumerate(stream, start=1):
            text = raw.strip().lstrip("\x1e").strip()
            if not text:
                continue
            try:
                value = json.loads(text)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"invalid CityJSONSeq JSON at {path}:{line_number}") from exc
            if not isinstance(value, dict):
                raise RuntimeError(f"CityJSONSeq record is not an object at {path}:{line_number}")
            records.append((line_number, value))
    require(bool(records), f"empty CityJSONSeq file: {path}")
    return records


def _jsonseq_records_from_marker(marker: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    for key in ("jsonseq_files", "raw_cityjsonseq_files", "cityjsonseq_files"):
        records = marker.get(key)
        if isinstance(records, list):
            if not all(isinstance(record, Mapping) for record in records):
                raise RuntimeError(f"Roofer marker {key} entries must be objects")
            return list(records)
    raw = marker.get("raw_jsonseq") or marker.get("raw_cityjsonseq")
    if isinstance(raw, Mapping) and isinstance(raw.get("files"), list):
        records = raw["files"]
        if not all(isinstance(record, Mapping) for record in records):
            raise RuntimeError("Roofer marker raw_cityjsonseq files must be objects")
        return list(records)
    raise RuntimeError("Roofer v2 marker lacks raw CityJSONSeq file records")


def load_raw_features(
    marker: Mapping[str, Any],
    marker_path: Path,
    expected_ids: Sequence[str],
) -> tuple[
    tuple[RawFeature, ...],
    tuple[dict[str, Any], ...],
    tuple[str, ...],
]:
    records = _jsonseq_records_from_marker(marker)
    declared_paths = [str(record.get("path", "")) for record in records]
    require_equal(declared_paths, sorted(declared_paths), "Roofer JSONSeq file order")
    features: list[RawFeature] = []
    raw_payloads: list[dict[str, Any]] = []
    for file_index, record in enumerate(records):
        path = resolve_and_hash(
            record,
            declaring_file=marker_path,
            label=f"Roofer JSONSeq file {file_index}",
        )
        file_sha = sha256_file(path)
        header: dict[str, Any] | None = None
        feature_count = 0
        for line_number, value in parse_cityjsonseq_file(path):
            if value.get("type") == "CityJSON":
                if header is not None:
                    raise RuntimeError(f"multiple CityJSONSeq headers in {path}")
                header = value
                continue
            require_equal(value.get("type"), "CityJSONFeature", "CityJSONSeq record type")
            if header is None:
                raise RuntimeError(f"CityJSONFeature precedes header in {path}:{line_number}")
            feature_id = str(value.get("id", ""))
            cityobjects = value.get("CityObjects")
            if not isinstance(cityobjects, Mapping):
                raise RuntimeError(f"CityJSONFeature lacks CityObjects: {path}:{line_number}")
            ownership = validate_ownership_graph(
                cityobjects, (feature_id,), label=f"raw feature {feature_id}"
            )
            parent = cityobjects[feature_id]
            attributes = parent.get("attributes", {})
            if isinstance(attributes, Mapping) and attributes.get("building_id") is not None:
                require_equal(
                    str(attributes.get("building_id")), feature_id, "raw feature attribute ID"
                )
            feature_payload = dict(value)
            feature_payload["transform"] = header.get("transform")
            vertices = absolute_vertices(feature_payload)
            child_ids = ownership[feature_id]
            roof_union = object_roof_union((feature_id, *child_ids), cityobjects, vertices)
            features.append(
                RawFeature(
                    building_id=feature_id,
                    source_path=path,
                    source_sha256=file_sha,
                    line_number=line_number,
                    feature_sha256=sha256_json(value),
                    roof_union=roof_union,
                )
            )
            raw_payloads.append(value)
            feature_count += 1
        if record.get("feature_count") is not None:
            require_equal(
                int(record["feature_count"]), feature_count, f"JSONSeq feature count {path}"
            )
    feature_ids_in_read_order = tuple(feature.building_id for feature in features)
    expected_ids = tuple(str(value) for value in expected_ids)
    require_exact_unique_ids(
        feature_ids_in_read_order,
        expected_ids,
        "raw CityJSONSeq feature/root IDs",
    )
    feature_by_id = {feature.building_id: feature for feature in features}
    payload_by_id = {
        feature.building_id: payload for feature, payload in zip(features, raw_payloads)
    }
    return (
        tuple(feature_by_id[building_id] for building_id in expected_ids),
        tuple(payload_by_id[building_id] for building_id in expected_ids),
        feature_ids_in_read_order,
    )


def _fallback(parent: Mapping[str, Any], zero_roof: bool) -> tuple[bool, str]:
    attributes = parent.get("attributes")
    attributes = attributes if isinstance(attributes, Mapping) else {}
    reasons: list[str] = []
    mode = str(attributes.get("rf_extrusion_mode", ""))
    if mode in {"skip", "lod11_fallback"}:
        reasons.append(f"rf_extrusion_mode={mode}")
    if attributes.get("rf_pointcloud_unusable") is True:
        reasons.append("rf_pointcloud_unusable=true")
    if zero_roof:
        reasons.append("zero_roofsurface_xy")
    return bool(reasons), ";".join(reasons)


def validate_roofer(
    marker_path: Path,
    merged_cityjson: Path,
    inputs: RunInputs,
    lock: PilotLock,
    crop: Mapping[str, Any],
    classification: Mapping[str, Any],
    prepare_marker_path: Path,
    prepare_marker_sha: str,
    prepare_payload: Mapping[str, Any],
    roofprints: Mapping[str, Any],
) -> dict[str, Any]:
    marker_path = marker_path.resolve()
    marker = load_json(marker_path, "Roofer marker")
    require_equal(marker.get("state"), "complete", "Roofer marker state")
    require_equal(
        marker.get("schema"),
        "jointbuildgs.pilot_1wave.roofer_invocation.v2",
        "Roofer marker schema",
    )
    require_equal(str(marker.get("condition_id")), inputs.condition_id, "Roofer condition")
    require_equal(int(marker.get("seed", -1)), inputs.seed, "Roofer seed")
    require_equal(int(marker.get("roofer_invocation_count", -1)), 1, "Roofer invocation count")
    require_equal(marker.get("selection_sha256"), lock.selection_sha256, "Roofer selection SHA256")
    require_equal(marker.get("ordered_ids_sha256"), lock.ordered_ids_sha256, "Roofer ordered-ID SHA256")
    require_equal(
        tuple(str(value) for value in marker.get("ordered_building_ids", [])),
        lock.ids,
        "Roofer ordered building IDs",
    )
    _verify_nested_artifacts(marker, declaring_file=marker_path, label="roofer_marker")

    receipt_record = marker.get("classification_receipt")
    if not isinstance(receipt_record, Mapping):
        raise RuntimeError("Roofer marker lacks classification_receipt")
    receipt_path = resolve_and_hash(
        receipt_record, declaring_file=marker_path, label="Roofer classification receipt"
    )
    require_equal(receipt_path, classification["path"], "Roofer classification receipt path")
    pointcloud_path, pointcloud_sha = _record_path_sha(
        marker,
        declaring_file=marker_path,
        label="Roofer pointcloud",
        nested_keys=("pointcloud", "classified_pointcloud"),
        flat_prefixes=("pointcloud", "classified_pointcloud"),
    )
    require_equal(pointcloud_path, classification["pointcloud_path"], "Roofer pointcloud path")
    require_equal(pointcloud_sha, classification["pointcloud_sha256"], "Roofer pointcloud SHA256")
    marker_footprints = marker.get("footprints") or marker.get("roofprints")
    if not isinstance(marker_footprints, Mapping):
        raise RuntimeError("Roofer marker lacks footprint record")
    marker_footprint_path = resolve_and_hash(
        marker_footprints, declaring_file=marker_path, label="Roofer roofprints"
    )
    require_equal(marker_footprint_path, roofprints["path"], "Roofer/prepared roofprint path")
    validate_roofprint_record(
        marker_footprints, roofprints, lock.ids, label="Roofer roofprints"
    )
    require_equal(marker.get("crop_contract"), classification["payload"].get("crop_contract"), "Roofer crop contract")
    require_equal(marker.get("readout_lineage"), crop["lineage"], "Roofer readout lineage")
    require_equal(
        marker_footprints,
        prepare_payload.get("footprints"),
        "prepare/final Roofer footprint record",
    )
    for field in (
        "condition_id",
        "seed",
        "selection_sha256",
        "ordered_ids_sha256",
        "ordered_building_ids",
        "runtime_contract",
        "roofer_image",
        "roofer_parameters",
        "pointcloud_path",
        "pointcloud_sha256",
        "pointcloud",
        "classification_receipt",
        "readout_lineage",
        "crop_contract",
        "footprints",
    ):
        require_equal(marker.get(field), prepare_payload.get(field), f"prepare/final {field}")

    prepare_record = (
        marker.get("prepare_receipt")
        or marker.get("roofprint_prepare_marker")
        or marker.get("prepare_marker")
    )
    if not isinstance(prepare_record, Mapping):
        raise RuntimeError("Roofer marker lacks roofprint prepare-marker binding")
    declared_prepare = resolve_and_hash(
        prepare_record, declaring_file=marker_path, label="Roofer roofprint prepare marker"
    )
    require_equal(declared_prepare, prepare_marker_path.resolve(), "Roofer prepare-marker path")
    require_equal(str(prepare_record.get("sha256")), prepare_marker_sha, "Roofer prepare-marker SHA256")
    prepare_argv = validate_argv_record(
        prepare_payload.get("roofer_argv"),
        declaring_file=prepare_marker_path.resolve(),
        label="prepare Roofer argv",
        expected_condition=inputs.condition_id,
        expected_seed=inputs.seed,
    )
    final_argv = validate_argv_record(
        marker.get("roofer_argv"),
        declaring_file=marker_path,
        label="final Roofer argv",
        expected_condition=inputs.condition_id,
        expected_seed=inputs.seed,
    )
    require_equal(final_argv["path"], prepare_argv["path"], "prepare/final argv path")
    require_equal(final_argv["sha256"], prepare_argv["sha256"], "prepare/final argv SHA256")
    execution_binding = validate_execution_binding(
        marker,
        marker_path=marker_path,
        inputs=inputs,
        prepare_path=prepare_marker_path.resolve(),
        prepare_sha256=prepare_marker_sha,
        argv=final_argv,
    )

    outputs = prepare_payload.get("outputs")
    if not isinstance(outputs, Mapping):
        raise RuntimeError("Roofer prepare receipt lacks outputs")
    expected_runtime_dir = marker_path.parent.resolve()
    expected_outputs = {
        "runtime_dir": expected_runtime_dir,
        "raw_jsonseq_dir": expected_runtime_dir / "raw_jsonseq",
        "merged_cityjson_path": merged_cityjson.resolve(),
        "marker_path": marker_path,
    }
    for field, expected_path in expected_outputs.items():
        declared = resolve_declared_path(outputs.get(field), declaring_file=prepare_marker_path)
        require_equal(declared, expected_path, f"prepare output {field}")

    cityjson_path, cityjson_sha = _record_path_sha(
        marker,
        declaring_file=marker_path,
        label="merged CityJSON",
        nested_keys=("merged_cityjson", "cityjson"),
        flat_prefixes=("merged_cityjson", "cityjson"),
    )
    require_equal(cityjson_path, merged_cityjson.resolve(), "Roofer merged CityJSON path")
    raw_features, _raw_payloads, raw_feature_ids_in_read_order = load_raw_features(
        marker, marker_path, lock.ids
    )
    raw_record = marker.get("raw_jsonseq")
    if not isinstance(raw_record, Mapping):
        raise RuntimeError("Roofer v2 marker lacks raw_jsonseq")
    require_equal(int(raw_record.get("feature_count", -1)), len(lock.ids), "raw JSONSeq feature count")
    file_records = raw_record.get("files")
    if not isinstance(file_records, list):
        raise RuntimeError("raw_jsonseq.files must be an array")
    require_equal(int(raw_record.get("file_count", -1)), len(file_records), "raw JSONSeq file count")
    raw_directory = resolve_declared_path(
        raw_record.get("directory_path"), declaring_file=marker_path
    )
    require(raw_directory.is_dir(), "raw JSONSeq directory is not a directory")
    canonical_file_records: list[dict[str, Any]] = []
    for index, value in enumerate(file_records):
        if not isinstance(value, Mapping):
            raise RuntimeError(f"raw JSONSeq file record {index} is not an object")
        require_equal(
            set(value), {"path", "size_bytes", "sha256"}, f"raw JSONSeq file record fields {index}"
        )
        path = resolve_and_hash(
            value, declaring_file=marker_path, label=f"raw JSONSeq file {index}"
        )
        require_equal(path.parent, raw_directory, f"raw JSONSeq parent directory {index}")
        require_equal(int(value["size_bytes"]), path.stat().st_size, f"raw JSONSeq size {index}")
        canonical_file_records.append(
            {
                "path": str(value["path"]),
                "size_bytes": int(value["size_bytes"]),
                "sha256": str(value["sha256"]),
            }
        )
    require_equal(
        [Path(value["path"]).name for value in canonical_file_records],
        sorted(Path(value["path"]).name for value in canonical_file_records),
        "raw JSONSeq filename order",
    )
    require_equal(
        raw_record.get("bundle_sha256"),
        sha256_json({"files": canonical_file_records}),
        "raw JSONSeq bundle SHA256",
    )
    marker_feature_ids_in_read_order = tuple(
        str(value) for value in raw_record.get("feature_ids_in_read_order", [])
    )
    require_exact_unique_ids(
        marker_feature_ids_in_read_order,
        lock.ids,
        "raw JSONSeq marker feature IDs",
    )
    require_equal(
        marker_feature_ids_in_read_order,
        raw_feature_ids_in_read_order,
        "raw JSONSeq marker/read order",
    )
    require_equal(int(raw_record.get("root_building_count", -1)), len(lock.ids), "raw root count")
    raw_root_ids = tuple(str(value) for value in raw_record.get("root_building_ids", []))
    require_exact_unique_ids(
        raw_root_ids,
        lock.ids,
        "raw root Building IDs",
    )

    merged = load_json(cityjson_path, "merged CityJSON")
    require_equal(merged.get("type"), "CityJSON", "merged CityJSON type")
    cityobjects = merged.get("CityObjects")
    if not isinstance(cityobjects, Mapping):
        raise RuntimeError("merged CityJSON lacks CityObjects")
    merged_root_ids_in_serialization_order = tuple(
        str(object_id)
        for object_id, obj in cityobjects.items()
        if isinstance(obj, Mapping) and obj.get("type") == "Building"
    )
    ownership = validate_ownership_graph(cityobjects, lock.ids, label="merged CityJSON")
    merged_record = marker.get("merged_cityjson")
    if not isinstance(merged_record, Mapping):
        raise RuntimeError("Roofer v2 marker lacks merged_cityjson")
    require_equal(
        int(merged_record.get("size_bytes", -1)),
        cityjson_path.stat().st_size,
        "merged CityJSON size",
    )
    require_equal(int(merged_record.get("root_building_count", -1)), len(lock.ids), "merged root count")
    merged_marker_root_ids = tuple(
        str(value) for value in merged_record.get("root_building_ids", [])
    )
    require_exact_unique_ids(
        merged_marker_root_ids,
        lock.ids,
        "merged root Building IDs",
    )
    child_count = sum(len(value) for value in ownership.values())
    require_equal(int(raw_record.get("child_count", -1)), child_count, "raw child count")
    require_equal(int(merged_record.get("child_count", -1)), child_count, "merged child count")
    vertices = absolute_vertices(merged)
    unions: list[BaseGeometry] = []
    fallback_flags: list[bool] = []
    fallback_reasons: list[str] = []
    raw_matches: list[bool] = []
    parent_hashes: list[str] = []
    for index, building_id in enumerate(lock.ids):
        parent = cityobjects[building_id]
        attributes = parent.get("attributes", {})
        if isinstance(attributes, Mapping) and attributes.get("building_id") is not None:
            require_equal(
                str(attributes.get("building_id")), building_id, "merged parent attribute ID"
            )
        roof_union = object_roof_union(
            (building_id, *ownership[building_id]), cityobjects, vertices
        )
        unions.append(roof_union)
        zero_roof = roof_union.is_empty or float(roof_union.area) <= 1e-12
        fallback_flag, fallback_reason = _fallback(parent, zero_roof)
        fallback_flags.append(fallback_flag)
        fallback_reasons.append(fallback_reason)
        raw_union = raw_features[index].roof_union
        both_zero = raw_union.is_empty and roof_union.is_empty
        if both_zero:
            geometry_match = True
        elif raw_union.is_empty != roof_union.is_empty:
            geometry_match = False
        else:
            symmetric = float(raw_union.symmetric_difference(roof_union).area)
            tolerance = max(1e-6, float(roof_union.area) * 1e-8)
            geometry_match = symmetric <= tolerance
        require(geometry_match, f"raw/merged roof geometry drift for {building_id}")
        raw_matches.append(geometry_match)
        parent_hashes.append(
            sha256_json(
                {
                    "parent": parent,
                    "children": {
                        child_id: cityobjects[child_id] for child_id in ownership[building_id]
                    },
                }
            )
        )
    return {
        "payload": marker,
        "path": marker_path,
        "sha256": sha256_file(marker_path),
        "cityjson_path": cityjson_path,
        "cityjson_sha256": cityjson_sha,
        "cityobjects": cityobjects,
        "ownership": ownership,
        "roof_unions": tuple(unions),
        "fallback_flags": tuple(fallback_flags),
        "fallback_reasons": tuple(fallback_reasons),
        "raw_matches": tuple(raw_matches),
        "parent_hashes": tuple(parent_hashes),
        "raw_features": raw_features,
        "raw_feature_ids_in_read_order": raw_feature_ids_in_read_order,
        "raw_marker_root_ids": raw_root_ids,
        "merged_root_ids_in_serialization_order": merged_root_ids_in_serialization_order,
        "merged_marker_root_ids": merged_marker_root_ids,
        "execution_receipt_path": execution_binding["path"],
        "execution_receipt_sha256": execution_binding["sha256"],
        "roofer_execution": execution_binding["normalized"],
    }


def validate_scores(
    marker_path: Path,
    score_csv: Path,
    inputs: RunInputs,
    lock: PilotLock,
    roofer: Mapping[str, Any],
    classification: Mapping[str, Any],
) -> dict[str, Any]:
    marker_path = marker_path.resolve()
    marker = load_json(marker_path, "score marker")
    require_equal(marker.get("state"), "complete", "score marker state")
    require_equal(str(marker.get("condition_id")), inputs.condition_id, "score condition")
    require_equal(int(marker.get("seed", -1)), inputs.seed, "score seed")
    require_equal(int(marker.get("score_invocation_count", -1)), 1, "score invocation count")
    _verify_nested_artifacts(marker, declaring_file=marker_path, label="score_marker")
    marker_roofer_path, marker_roofer_sha = _record_path_sha(
        marker,
        declaring_file=marker_path,
        label="score Roofer marker",
        nested_keys=("roofer_marker",),
        flat_prefixes=("roofer_marker",),
    )
    require_equal(marker_roofer_path, roofer["path"], "score/Roofer marker path")
    require_equal(marker_roofer_sha, roofer["sha256"], "score/Roofer marker SHA256")
    marker_city_path, marker_city_sha = _record_path_sha(
        marker,
        declaring_file=marker_path,
        label="score merged CityJSON",
        nested_keys=("merged_cityjson", "cityjson"),
        flat_prefixes=("merged_cityjson", "cityjson"),
    )
    require_equal(marker_city_path, roofer["cityjson_path"], "score/Roofer CityJSON path")
    require_equal(marker_city_sha, roofer["cityjson_sha256"], "score/Roofer CityJSON SHA256")
    receipt_record = marker.get("classification_receipt")
    if isinstance(receipt_record, Mapping):
        receipt_path = resolve_and_hash(
            receipt_record, declaring_file=marker_path, label="score classification receipt"
        )
        require_equal(receipt_path, classification["path"], "score classification receipt path")
    elif marker.get("classification_receipt_path") is not None:
        receipt_path, receipt_sha = _record_path_sha(
            marker,
            declaring_file=marker_path,
            label="score classification receipt",
            nested_keys=(),
            flat_prefixes=("classification_receipt",),
        )
        require_equal(receipt_path, classification["path"], "score classification receipt path")
        require_equal(receipt_sha, classification["sha256"], "score classification receipt SHA256")
    else:
        raise RuntimeError("score marker lacks classification receipt binding")
    output_path, output_sha = _record_path_sha(
        marker,
        declaring_file=marker_path,
        label="score CSV",
        nested_keys=("score_output", "score_csv"),
        flat_prefixes=("score_output", "score_csv"),
    )
    require_equal(output_path, score_csv.resolve(), "score marker CSV path")
    rows = read_csv(output_path, "score CSV")
    require_equal(len(rows), len(lock.ids), "score row count")
    score_ids = tuple(str(row.get("building_id", "")) for row in rows)
    require_equal(len(set(score_ids)), len(score_ids), "score building ID uniqueness")
    require_equal(score_ids, lock.ids, "score ordered building IDs")
    for index, (row, expected_id) in enumerate(zip(rows, lock.ids), start=1):
        require_equal(str(row.get("condition_id", "")), inputs.condition_id, "score row condition")
        require_equal(int(row.get("seed", -1)), inputs.seed, "score row seed")
        require_equal(int(row.get("selection_rank", -1)), index, "score row selection rank")
        require_equal(str(row.get("building_id", "")), expected_id, "score row building ID")
        row_city_sha = row.get("cityjson_sha256")
        if row_city_sha not in (None, ""):
            require_equal(row_city_sha, roofer["cityjson_sha256"], "score row CityJSON SHA256")
    if marker.get("score_output_row_count") is not None:
        require_equal(int(marker["score_output_row_count"]), len(rows), "score marker row count")
    return {
        "payload": marker,
        "path": marker_path,
        "sha256": sha256_file(marker_path),
        "csv_path": output_path,
        "csv_sha256": output_sha,
        "rows": tuple(rows),
        "row_hashes": tuple(sha256_json(row) for row in rows),
    }


def build_matrix(
    inputs: RunInputs,
    lock: PilotLock,
    footprints: Sequence[BaseGeometry],
    roof_unions: Sequence[BaseGeometry],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    require_equal(len(footprints), len(lock.ids), "matrix footprint count")
    require_equal(len(roof_unions), len(lock.ids), "matrix roof count")
    rows: list[dict[str, Any]] = []
    columns: list[dict[str, Any]] = []
    for output_index, (output_id, roof) in enumerate(zip(lock.ids, roof_unions), start=1):
        roof_area = float(roof.area) if not roof.is_empty else 0.0
        require(math.isfinite(roof_area) and roof_area >= 0.0, f"invalid roof area: {output_id}")
        intersections = [
            float(footprint.intersection(roof).area) if roof_area > 0.0 else 0.0
            for footprint in footprints
        ]
        containment_tolerance = max(1e-6, roof_area * 1e-8)
        argmax_indices: list[int] = []
        if roof_area > 1e-12:
            maximum = max(intersections)
            tolerance = max(1e-9, abs(maximum) * 1e-9)
            if maximum > 1e-12:
                argmax_indices = [
                    index
                    for index, value in enumerate(intersections)
                    if abs(value - maximum) <= tolerance
                ]
            if len(argmax_indices) == 1:
                owner_index = argmax_indices[0]
                owner_id = lock.ids[owner_index]
                owner_ratio: float | None = intersections[owner_index] / roof_area
                owner_unique = True
                outside_owner_area = float(roof.difference(footprints[owner_index]).area)
                owner_contained = outside_owner_area <= containment_tolerance
                owner_containment_ratio: float | None = max(
                    0.0, min(1.0, 1.0 - outside_owner_area / roof_area)
                )
            else:
                owner_index = None
                owner_id = ""
                owner_ratio = None
                owner_unique = False
                outside_owner_area = roof_area
                owner_containment_ratio = 0.0
                owner_contained = False
        else:
            owner_index = None
            owner_id = ""
            owner_ratio = None
            owner_unique = False
            outside_owner_area = 0.0
            owner_containment_ratio = None
            owner_contained = False
        if roof_area > 1e-12:
            offdiag = [
                (value / roof_area, index)
                for index, value in enumerate(intersections)
                if index != output_index - 1
            ]
            strongest_ratio = max((value for value, _index in offdiag), default=0.0)
            strongest_index = min(
                (
                    index
                    for value, index in offdiag
                    if math.isclose(value, strongest_ratio, rel_tol=0.0, abs_tol=1e-15)
                ),
                default=-1,
            )
        else:
            strongest_ratio, strongest_index = 0.0, -1
        columns.append(
            {
                "owner_index": owner_index,
                "owner_id": owner_id,
                "owner_ratio": owner_ratio,
                "owner_unique": owner_unique,
                "owner_matches": owner_id == output_id if owner_index is not None else None,
                "owner_candidate_count": len(argmax_indices),
                "containment_tolerance_m2": containment_tolerance,
                "outside_owner_area_m2": outside_owner_area,
                "owner_containment_ratio": owner_containment_ratio,
                "owner_contained": owner_contained,
                "strongest_offdiag_id": lock.ids[strongest_index] if strongest_index >= 0 else "",
                "strongest_offdiag_ratio": strongest_ratio,
            }
        )
        for locked_index, (locked_id, footprint, intersection) in enumerate(
            zip(lock.ids, footprints, intersections), start=1
        ):
            rows.append(
                {
                    "schema_version": MATRIX_SCHEMA_VERSION,
                    "condition_id": inputs.condition_id,
                    "seed": inputs.seed,
                    "locked_selection_rank": locked_index,
                    "locked_building_id": locked_id,
                    "output_selection_rank": output_index,
                    "output_parent_id": output_id,
                    "locked_footprint_area_m2": float(footprint.area),
                    "output_roof_union_area_m2": roof_area,
                    "intersection_area_m2": intersection,
                    "intersection_over_output_roof": (
                        intersection / roof_area if roof_area > 1e-12 else None
                    ),
                    "is_diagonal": locked_index == output_index,
                    "output_zero_roof": roof_area <= 1e-12,
                    "argmax_candidate_count": len(argmax_indices),
                    "is_column_argmax": locked_index - 1 in argmax_indices,
                    "owner_assignment": owner_index == locked_index - 1,
                    "assigned_owner_building_id": owner_id,
                    "assigned_owner_selection_rank": (
                        owner_index + 1 if owner_index is not None else None
                    ),
                    "containment_tolerance_m2": containment_tolerance,
                    "outside_assigned_owner_area_m2": outside_owner_area,
                    "assigned_owner_containment_ratio": owner_containment_ratio,
                    "assigned_owner_contained": owner_contained,
                }
            )
    require_equal(len(rows), len(lock.ids) ** 2, "spatial matrix row count")
    diagonal_sum = sum(
        int(bool(row["owner_assignment"]))
        for row in rows
        if bool(row["is_diagonal"])
    )
    offdiagonal_sum = sum(
        int(bool(row["owner_assignment"]))
        for row in rows
        if not bool(row["is_diagonal"])
    )
    full_column_sums = {
        index: sum(
            int(bool(row["owner_assignment"]))
            for row in rows
            if int(row["output_selection_rank"]) == index
        )
        for index in range(1, len(lock.ids) + 1)
    }
    full_row_sums = {
        index: sum(
            int(bool(row["owner_assignment"]))
            for row in rows
            if int(row["locked_selection_rank"]) == index
        )
        for index in range(1, len(lock.ids) + 1)
    }
    gate = {
        "row_sums": full_row_sums,
        "column_sums": full_column_sums,
        "all_row_sums_equal_1": all(value == 1 for value in full_row_sums.values()),
        "all_column_sums_equal_1": all(
            value == 1 for value in full_column_sums.values()
        ),
        "diagonal_sum": diagonal_sum,
        "offdiagonal_sum": offdiagonal_sum,
        "expected_diagonal_sum": len(lock.ids),
        "containment_match_count": sum(
            int(bool(column["owner_contained"])) for column in columns
        ),
        "containment_mismatch_count": sum(
            not bool(column["owner_contained"]) for column in columns
        ),
        "all_assigned_roofs_contained": all(
            bool(column["owner_contained"]) for column in columns
        ),
    }
    gate["pass"] = bool(
        gate["all_row_sums_equal_1"]
        and gate["all_column_sums_equal_1"]
        and diagonal_sum == len(lock.ids)
        and offdiagonal_sum == 0
        and gate["containment_mismatch_count"] == 0
    )
    return rows, columns, gate


def _csv_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        if not math.isfinite(value):
            raise RuntimeError("non-finite value cannot be serialized")
        return f"{value:.12f}"
    return value


def csv_bytes(rows: Sequence[Mapping[str, Any]], fields: Sequence[str]) -> bytes:
    import io

    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(fields), lineterminator="\n")
    writer.writeheader()
    for row in rows:
        require_equal(set(row), set(fields), "audit CSV row fields")
        writer.writerow({field: _csv_value(row[field]) for field in fields})
    return stream.getvalue().encode("utf-8")


def write_deterministic(path: Path, payload: bytes) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        require_equal(path.read_bytes(), payload, f"existing deterministic output {path}")
        return
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def audit_run(
    inputs: RunInputs,
    *,
    building_output: Path,
    matrix_output: Path,
    receipt_output: Path,
    strict_locked_population: bool = True,
) -> dict[str, Any]:
    _SHA256_CACHE.clear()
    if strict_locked_population:
        require(inputs.condition_id in EXPECTED_CONDITIONS, "unknown pilot condition")
        require(int(inputs.seed) in EXPECTED_SEEDS, "unknown pilot seed")
    lock = load_pilot_lock(
        inputs.pilot_set,
        inputs.pilot_manifest,
        strict_locked_population=strict_locked_population,
    )
    crop = validate_crop_and_provenance(
        inputs, lock, strict_locked_population=strict_locked_population
    )
    prepare_marker, roofprints = validate_prepare_marker(
        inputs.roofprint_prepare_marker,
        lock,
        expected_condition=inputs.condition_id,
        expected_seed=inputs.seed,
    )
    prepare_sha = sha256_file(inputs.roofprint_prepare_marker.resolve())
    classification = validate_classification(
        inputs.classification_receipt, inputs, lock, crop, roofprints
    )
    roofer = validate_roofer(
        inputs.roofer_marker,
        inputs.merged_cityjson,
        inputs,
        lock,
        crop,
        classification,
        inputs.roofprint_prepare_marker,
        prepare_sha,
        prepare_marker,
        roofprints,
    )
    scores = validate_scores(
        inputs.score_marker,
        inputs.score_csv,
        inputs,
        lock,
        roofer,
        classification,
    )
    matrix_rows, matrix_columns, matrix_gate = build_matrix(
        inputs, lock, roofprints["polygons"], roofer["roof_unions"]
    )

    building_rows: list[dict[str, Any]] = []
    for index, building_id in enumerate(lock.ids):
        raw = roofer["raw_features"][index]
        child_ids = roofer["ownership"][building_id]
        column = matrix_columns[index]
        roof_area = float(roofer["roof_unions"][index].area)
        zero_roof = roof_area <= 1e-12
        crop_match = crop["crop"]["population"]["ordered_building_ids"][index] == building_id
        receipt_match = (
            classification["payload"]["crop_contract"]["ordered_building_ids"][index]
            == building_id
        )
        roofprint_match = roofprints["ids"][index] == building_id
        raw_match = raw.building_id == building_id
        merged_match = list(roofer["ownership"])[index] == building_id
        score_match = scores["rows"][index]["building_id"] == building_id
        all_four = all(
            (crop_match, receipt_match, roofprint_match, raw_match, merged_match, score_match)
        ) and column["owner_matches"] is True
        building_rows.append(
            {
                "schema_version": SCHEMA_VERSION,
                "condition_id": inputs.condition_id,
                "seed": inputs.seed,
                "selection_rank": index + 1,
                "expected_building_id": building_id,
                "crop_contract_sha256": crop["crop_sha256"],
                "scene_npz_path": str(crop["scene_npz_path"]),
                "scene_npz_sha256": crop["scene_npz_sha256"],
                "scene_provenance_path": str(crop["provenance_path"]),
                "scene_provenance_sha256": crop["provenance_sha256"],
                "classification_receipt_path": str(classification["path"]),
                "classification_receipt_sha256": classification["sha256"],
                "roofprint_prepare_marker_path": str(inputs.roofprint_prepare_marker.resolve()),
                "roofprint_prepare_marker_sha256": prepare_sha,
                "roofprint_path": str(roofprints["path"]),
                "roofprint_sha256": roofprints["sha256"],
                "roofprint_feature_index": index,
                "roofprint_building_id": roofprints["ids"][index],
                "roofprint_geometry_sha256": roofprints["geometry_hashes"][index],
                "classified_pointcloud_path": str(classification["pointcloud_path"]),
                "classified_pointcloud_sha256": classification["pointcloud_sha256"],
                "roofer_marker_path": str(roofer["path"]),
                "roofer_marker_sha256": roofer["sha256"],
                "roofer_execution_receipt_path": str(
                    roofer["execution_receipt_path"]
                ),
                "roofer_execution_receipt_sha256": roofer[
                    "execution_receipt_sha256"
                ],
                "jsonseq_path": str(raw.source_path),
                "jsonseq_sha256": raw.source_sha256,
                "jsonseq_line_number": raw.line_number,
                "jsonseq_feature_id": raw.building_id,
                "jsonseq_feature_sha256": raw.feature_sha256,
                "merged_cityjson_path": str(roofer["cityjson_path"]),
                "merged_cityjson_sha256": roofer["cityjson_sha256"],
                "merged_parent_id": building_id,
                "merged_parent_record_sha256": roofer["parent_hashes"][index],
                "owned_child_ids": ";".join(child_ids),
                "owned_child_count": len(child_ids),
                "roof_union_area_m2": roof_area,
                "zero_roof": zero_roof,
                "fallback_flag": roofer["fallback_flags"][index],
                "fallback_reason": roofer["fallback_reasons"][index],
                "raw_merged_geometry_match": roofer["raw_matches"][index],
                "score_marker_path": str(scores["path"]),
                "score_marker_sha256": scores["sha256"],
                "score_csv_path": str(scores["csv_path"]),
                "score_csv_sha256": scores["csv_sha256"],
                "score_row_index": index,
                "score_building_id": scores["rows"][index]["building_id"],
                "score_row_sha256": scores["row_hashes"][index],
                "crop_contract_sha_match": True,
                "classification_receipt_sha_match": True,
                "crop_id_match": crop_match,
                "receipt_id_match": receipt_match,
                "roofprint_id_match": roofprint_match,
                "jsonseq_id_match": raw_match,
                "merged_parent_id_match": merged_match,
                "score_id_match": score_match,
                "spatial_owner_candidate_count": column["owner_candidate_count"],
                "spatial_owner_building_id": column["owner_id"],
                "spatial_owner_selection_rank": (
                    column["owner_index"] + 1 if column["owner_index"] is not None else None
                ),
                "spatial_owner_ratio": column["owner_ratio"],
                "spatial_owner_unique": column["owner_unique"],
                "spatial_owner_matches_parent": column["owner_matches"],
                "cityjson_owner_match": column["owner_matches"],
                "containment_tolerance_m2": column["containment_tolerance_m2"],
                "outside_owner_area_m2": column["outside_owner_area_m2"],
                "owner_containment_ratio": column["owner_containment_ratio"],
                "owner_contained": column["owner_contained"],
                "strongest_offdiag_building_id": column["strongest_offdiag_id"],
                "strongest_offdiag_ratio": column["strongest_offdiag_ratio"],
                "all_four_match": all_four,
                "binding_gate_pass": matrix_gate["pass"],
            }
        )

    require_equal(len(building_rows), len(lock.ids), "building audit row count")
    building_payload = csv_bytes(building_rows, BUILDING_FIELDS)
    matrix_payload = csv_bytes(matrix_rows, MATRIX_FIELDS)
    write_deterministic(building_output, building_payload)
    write_deterministic(matrix_output, matrix_payload)
    receipt = {
        "schema": RECEIPT_SCHEMA_VERSION,
        "task_id": TASK_ID,
        "state": "complete",
        "condition_id": inputs.condition_id,
        "seed": int(inputs.seed),
        "crs": CRS,
        "population_count": len(lock.ids),
        "matrix_shape": [len(lock.ids), len(lock.ids)],
        "hard_gate_passed": matrix_gate["pass"],
        "owner_assignment_gate": matrix_gate,
        "ordered_building_ids": list(lock.ids),
        "ordered_ids_sha256": lock.ordered_ids_sha256,
        "selection_sha256": lock.selection_sha256,
        "roofer_output_orders": {
            "raw_feature_ids_in_read_order": list(
                roofer["raw_feature_ids_in_read_order"]
            ),
            "raw_marker_root_ids": list(roofer["raw_marker_root_ids"]),
            "merged_root_ids_in_serialization_order": list(
                roofer["merged_root_ids_in_serialization_order"]
            ),
            "merged_marker_root_ids": list(roofer["merged_marker_root_ids"]),
            "audit_rows_reordered_to_locked_ids": True,
        },
        "zero_roof_count": sum(bool(value) for value in (row["zero_roof"] for row in building_rows)),
        "containment_mismatch_count": matrix_gate["containment_mismatch_count"],
        "source_artifacts": {
            "pilot_set": {"path": str(lock.pilot_set_path), "sha256": lock.pilot_set_sha256},
            "pilot_manifest": {"path": str(lock.manifest_path), "sha256": lock.manifest_sha256},
            "scene_npz": {"path": str(crop["scene_npz_path"]), "sha256": crop["scene_npz_sha256"]},
            "scene_provenance": {"path": str(crop["provenance_path"]), "sha256": crop["provenance_sha256"]},
            "classification_receipt": {"path": str(classification["path"]), "sha256": classification["sha256"]},
            "roofprint_prepare_marker": {"path": str(inputs.roofprint_prepare_marker.resolve()), "sha256": prepare_sha},
            "roofprints": {"path": str(roofprints["path"]), "sha256": roofprints["sha256"]},
            "classified_pointcloud": {"path": str(classification["pointcloud_path"]), "sha256": classification["pointcloud_sha256"]},
            "roofer_marker": {"path": str(roofer["path"]), "sha256": roofer["sha256"]},
            "roofer_execution_receipt": {
                "path": str(roofer["execution_receipt_path"]),
                "sha256": roofer["execution_receipt_sha256"],
            },
            "merged_cityjson": {"path": str(roofer["cityjson_path"]), "sha256": roofer["cityjson_sha256"]},
            "score_marker": {"path": str(scores["path"]), "sha256": scores["sha256"]},
            "score_csv": {"path": str(scores["csv_path"]), "sha256": scores["csv_sha256"]},
        },
        "raw_cityjsonseq_files": [
            {"path": str(path), "sha256": digest}
            for path, digest in dict(
                (feature.source_path, feature.source_sha256)
                for feature in roofer["raw_features"]
            ).items()
        ],
        "outputs": {
            "building_audit_csv": {
                "path": str(building_output.resolve()),
                "sha256": hashlib.sha256(building_payload).hexdigest(),
                "row_count": len(building_rows),
            },
            "spatial_matrix_csv": {
                "path": str(matrix_output.resolve()),
                "sha256": hashlib.sha256(matrix_payload).hexdigest(),
                "row_count": len(matrix_rows),
            },
        },
        "learning_runs_started_by_this_audit": 0,
        "gpu_required": False,
        "roofer_invocations_by_this_audit": 0,
        "score_invocations_by_this_audit": 0,
    }
    receipt_payload = (json.dumps(receipt, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
    write_deterministic(receipt_output, receipt_payload)
    return receipt


def _run_inputs_from_spec(value: Any, *, spec_path: Path) -> RunInputs:
    if not isinstance(value, Mapping):
        raise RuntimeError("batch run specification must be an object")
    required_paths = (
        "pilot_set",
        "pilot_manifest",
        "scene_npz",
        "scene_provenance",
        "classification_receipt",
        "roofprint_prepare_marker",
        "roofer_marker",
        "merged_cityjson",
        "score_marker",
        "score_csv",
    )
    missing = [key for key in ("condition_id", "seed", *required_paths) if key not in value]
    if missing:
        raise RuntimeError(f"batch run specification lacks fields: {missing}")
    resolved = {
        key: resolve_declared_path(value[key], declaring_file=spec_path)
        for key in required_paths
    }
    return RunInputs(
        condition_id=str(value["condition_id"]),
        seed=int(value["seed"]),
        **resolved,
    )


def audit_batch(
    spec_path: Path,
    output_dir: Path,
    *,
    strict_expected_runs: bool = True,
    strict_locked_population: bool = True,
) -> dict[str, Any]:
    """Validate and deterministically merge an ordered collection of run audits."""

    spec_path = spec_path.resolve()
    spec = load_json(spec_path, "binding batch specification")
    runs_raw = spec.get("runs")
    if not isinstance(runs_raw, list):
        raise RuntimeError("binding batch specification lacks a runs array")
    run_inputs = tuple(
        _run_inputs_from_spec(value, spec_path=spec_path) for value in runs_raw
    )
    actual_order = tuple((value.condition_id, value.seed) for value in run_inputs)
    expected_order = tuple(
        (condition_id, seed)
        for condition_id in EXPECTED_CONDITIONS
        for seed in EXPECTED_SEEDS
    )
    require_equal(len(set(actual_order)), len(actual_order), "batch condition/seed uniqueness")
    if strict_expected_runs:
        require_equal(actual_order, expected_order, "batch condition/seed order")
    require(bool(run_inputs), "binding batch has no runs")

    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    all_building_rows: list[dict[str, Any]] = []
    all_matrix_rows: list[dict[str, Any]] = []
    per_run: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix=".binding_batch_", dir=output_dir) as temporary:
        scratch = Path(temporary)
        for ordinal, inputs in enumerate(run_inputs):
            run_dir = scratch / f"{ordinal:02d}_{inputs.condition_id}_{inputs.seed}"
            run_dir.mkdir(parents=True)
            run_receipt = audit_run(
                inputs,
                building_output=run_dir / "binding.csv",
                matrix_output=run_dir / "matrix.csv",
                receipt_output=run_dir / "receipt.json",
                strict_locked_population=strict_locked_population,
            )
            building_rows = read_csv(run_dir / "binding.csv", "per-run binding audit")
            matrix_rows = read_csv(run_dir / "matrix.csv", "per-run spatial matrix")
            all_building_rows.extend(building_rows)
            all_matrix_rows.extend(matrix_rows)
            per_run.append(
                {
                    "condition_id": inputs.condition_id,
                    "seed": inputs.seed,
                    "population_count": int(run_receipt["population_count"]),
                    "matrix_row_count": len(matrix_rows),
                    "zero_roof_count": int(run_receipt["zero_roof_count"]),
                    "hard_gate_passed": bool(run_receipt["hard_gate_passed"]),
                    "owner_assignment_gate": run_receipt["owner_assignment_gate"],
                }
            )

    population = len(
        load_pilot_lock(
            run_inputs[0].pilot_set,
            run_inputs[0].pilot_manifest,
            strict_locked_population=strict_locked_population,
        ).ids
    )
    require_equal(len(all_building_rows), len(run_inputs) * population, "batch building row count")
    require_equal(len(all_matrix_rows), len(run_inputs) * population * population, "batch matrix row count")
    if strict_expected_runs and strict_locked_population:
        require_equal(len(all_building_rows), 300, "locked batch building row count")
        require_equal(len(all_matrix_rows), 9_000, "locked batch matrix row count")

    building_output = output_dir / "binding_audit.csv"
    matrix_output = output_dir / "binding_audit_spatial_matrix.csv"
    receipt_output = output_dir / "binding_audit_receipt.json"
    building_payload = csv_bytes(all_building_rows, BUILDING_FIELDS)
    matrix_payload = csv_bytes(all_matrix_rows, MATRIX_FIELDS)
    write_deterministic(building_output, building_payload)
    write_deterministic(matrix_output, matrix_payload)
    global_gate = {
        "run_count": len(run_inputs),
        "pass_run_count": sum(int(value["hard_gate_passed"]) for value in per_run),
        "fail_run_count": sum(not value["hard_gate_passed"] for value in per_run),
        "zero_roof_count": sum(int(value["zero_roof_count"]) for value in per_run),
        "containment_mismatch_count": sum(
            int(value["owner_assignment_gate"]["containment_mismatch_count"])
            for value in per_run
        ),
        "owner_assignment_count": sum(
            str(row["owner_assignment"]).lower() == "true" for row in all_matrix_rows
        ),
        "diagonal_assignment_count": sum(
            str(row["owner_assignment"]).lower() == "true"
            and str(row["is_diagonal"]).lower() == "true"
            for row in all_matrix_rows
        ),
        "offdiagonal_assignment_count": sum(
            str(row["owner_assignment"]).lower() == "true"
            and str(row["is_diagonal"]).lower() != "true"
            for row in all_matrix_rows
        ),
    }
    global_gate["pass"] = bool(
        global_gate["pass_run_count"] == len(run_inputs)
        and global_gate["fail_run_count"] == 0
        and global_gate["zero_roof_count"] == 0
        and global_gate["containment_mismatch_count"] == 0
        and global_gate["owner_assignment_count"] == len(run_inputs) * population
        and global_gate["diagonal_assignment_count"] == len(run_inputs) * population
        and global_gate["offdiagonal_assignment_count"] == 0
    )
    receipt = {
        "schema": "jointbuildgs.pilot_1wave.binding_batch_receipt.v1",
        "task_id": TASK_ID,
        "state": "complete",
        "crs": CRS,
        "batch_spec": {"path": str(spec_path), "sha256": sha256_file(spec_path)},
        "condition_seed_order": [
            {"condition_id": condition_id, "seed": seed}
            for condition_id, seed in actual_order
        ],
        "run_count": len(run_inputs),
        "building_row_count": len(all_building_rows),
        "spatial_matrix_row_count": len(all_matrix_rows),
        "per_run": per_run,
        "global_g1": global_gate,
        "hard_gate_passed": global_gate["pass"],
        "outputs": {
            "binding_audit_csv": {
                "path": str(building_output),
                "sha256": hashlib.sha256(building_payload).hexdigest(),
                "row_count": len(all_building_rows),
            },
            "spatial_matrix_csv": {
                "path": str(matrix_output),
                "sha256": hashlib.sha256(matrix_payload).hexdigest(),
                "row_count": len(all_matrix_rows),
            },
        },
        "learning_runs_started_by_this_audit": 0,
        "gpu_required": False,
        "roofer_invocations_by_this_audit": 0,
        "score_invocations_by_this_audit": 0,
    }
    write_deterministic(
        receipt_output,
        (json.dumps(receipt, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode(
            "utf-8"
        ),
    )
    return receipt


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    one = commands.add_parser("run", help="audit one condition/seed")
    one.add_argument("--condition", required=True, choices=EXPECTED_CONDITIONS)
    one.add_argument("--seed", required=True, type=int, choices=EXPECTED_SEEDS)
    one.add_argument("--pilot-set", required=True, type=Path)
    one.add_argument("--pilot-manifest", required=True, type=Path)
    one.add_argument("--scene-npz", required=True, type=Path)
    one.add_argument("--scene-provenance", required=True, type=Path)
    one.add_argument("--classification-receipt", required=True, type=Path)
    one.add_argument("--roofprint-prepare-marker", required=True, type=Path)
    one.add_argument("--roofer-marker", required=True, type=Path)
    one.add_argument("--merged-cityjson", required=True, type=Path)
    one.add_argument("--score-marker", required=True, type=Path)
    one.add_argument("--score-csv", required=True, type=Path)
    one.add_argument("--building-output", required=True, type=Path)
    one.add_argument("--matrix-output", required=True, type=Path)
    one.add_argument("--receipt-output", required=True, type=Path)
    batch = commands.add_parser("batch", help="audit and merge the exact ten pilot runs")
    batch.add_argument("--spec", required=True, type=Path)
    batch.add_argument("--output-dir", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.command == "batch":
        receipt = audit_batch(args.spec, args.output_dir)
        print(json.dumps(receipt["outputs"], ensure_ascii=False, sort_keys=True))
        return
    receipt = audit_run(
        RunInputs(
            condition_id=args.condition,
            seed=args.seed,
            pilot_set=args.pilot_set,
            pilot_manifest=args.pilot_manifest,
            scene_npz=args.scene_npz,
            scene_provenance=args.scene_provenance,
            classification_receipt=args.classification_receipt,
            roofprint_prepare_marker=args.roofprint_prepare_marker,
            roofer_marker=args.roofer_marker,
            merged_cityjson=args.merged_cityjson,
            score_marker=args.score_marker,
            score_csv=args.score_csv,
        ),
        building_output=args.building_output,
        matrix_output=args.matrix_output,
        receipt_output=args.receipt_output,
        strict_locked_population=True,
    )
    print(json.dumps(receipt["outputs"], ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
