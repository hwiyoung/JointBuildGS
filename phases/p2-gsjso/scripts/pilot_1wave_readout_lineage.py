#!/usr/bin/env python3
"""Fail-closed checkpoint lineage shared by the P1W read-out adapters.

This module is deliberately geometry-agnostic.  It binds a read-out artifact to
the exact full-state checkpoint declared by the trainer manifest, then lets the
classifier, Roofer adapter, and scorer re-open and verify the same bytes.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np


REPO = Path(__file__).resolve().parents[3]
CONTAINER_REPO = Path("/workspace/JointBuildGS")
LINEAGE_SCHEMA = "jointbuildgs.pilot_1wave.readout_lineage.v1"
CLASSIFICATION_SCHEMA = "jointbuildgs.pilot_1wave.scene_classification.v1"
FULL_STATE_MANIFEST_SCHEMA = "jointbuildgs.stage2.resume_manifest.v1"
FULL_STATE_CHECKPOINT_FORMAT = "jointbuildgs.stage2.full_state"
FULL_STATE_STEP_SEMANTICS = "completed_optimizer_updates"
FULL_STATE_STEPS = (5_000, 10_000, 15_000, 20_000)
MAX_ITER = 20_000
CONDITION_ARMS = {
    "01": "01_surface",
    "02": "02_photo_control",
    "03": "03_plane_soft",
    "04a": "04a_plane_medium_vision",
    "04b": "04b_plane_medium_gt_upperbound",
}
EXPECTED_SEEDS = (1001, 1002)
PILOT_CROP_CONTRACT_SCHEMA = "jointbuildgs.pilot_1wave.readout_crop_contract.v1"
PILOT_CROP_CONTRACT_SHA256 = (
    "6d0b4b9136a51e8a5483025fe45c3dba962c71d32dbdc97a11358ae8f0385dda"
)
PILOT_ORDERED_IDS_SHA256 = (
    "ae5cbc664941c3b8bb4238767f1d0833a1f7684928a03837047065f85093bb01"
)
PILOT_BUILDING_IDS = (
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
PILOT_CROP_CONTRACT = {
    "schema": PILOT_CROP_CONTRACT_SCHEMA,
    "crs": "EPSG:25832",
    "crop": {
        "mode": "single_locked_global_bbox",
        "bbox_utm": [690764.89, 5335918.4, 690964.53, 5336202.0],
        "area_m2": 56617.904,
    },
    "population": {
        "count": 30,
        "ordered_building_ids": list(PILOT_BUILDING_IDS),
        "ordered_ids_sha256": PILOT_ORDERED_IDS_SHA256,
    },
    "pilot_set_csv": {
        "path": (
            "phases/p2-gsjso/runs/20260721_pilot_1wave/"
            "pilot_1wave_pilot_set.csv"
        ),
        "sha256": "db5ecb6c838499dd3a5f96a4b1abae85414c3d38318d976b7ee598982b566ffc",
    },
    "pilot_set_manifest": {
        "path": (
            "phases/p2-gsjso/runs/20260721_pilot_1wave/"
            "pilot_1wave_pilot_set_manifest.json"
        ),
        "sha256": "803d18862db926fff353c641e08a03c5938cedf3fb49cc4859751189e83855e2",
    },
    "footprint_source": {
        "path": "results/tum_transfer/analysis/footprints_aoi.geojson",
        "sha256": "ca7f5b13a52368e1d2ac47b77cc78f12887bad4d598d122ad57b882eb4920a82",
        "allowed_content": "LoD2 GroundSurface XY only",
    },
    "materialized_input_inventory": {
        "path": (
            "phases/p2-gsjso/runs/20260721_pilot_1wave/calibration/scaffolds/"
            "materialized_input_inventory.json"
        ),
        "sha256": "30a3387275ee9ed29ad75bbdf7cb1979f2b8b2cd52640225e9dbe00895666450",
        "records_sha256": (
            "b99c38d31b37b59f1827537e520c20c76ca5a0ee0bfbc5baaaa879d4fff57271"
        ),
        "view_count": 481,
        "view_ids_sha256": (
            "25d691a8bda73f26e2b3513316918af625536bc867c164b41a18114c868365c9"
        ),
        "data_root": (
            "phases/p2-gsjso/runs/20260721_pilot_1wave/prep_artifacts/data"
        ),
    },
}


def sha256_file(path: Path, block_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(block_size), b""):
            digest.update(block)
    return digest.hexdigest()


def require_equal(actual: Any, expected: Any, label: str) -> None:
    if actual != expected:
        raise RuntimeError(f"{label} drift: {actual!r} != {expected!r}")


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _scalar_text(value: Any, label: str) -> str:
    encoded = np.asarray(value)
    if encoded.shape != () or encoded.dtype.kind not in {"U", "S"}:
        raise RuntimeError(f"{label} must be a non-object scalar string")
    raw = encoded.item()
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    return str(raw)


def validate_pilot_crop_contract(encoded: Any, digest: Any) -> dict[str, Any]:
    """Validate the exact committed expanded-pilot crop contract."""

    if not isinstance(encoded, str) or not isinstance(digest, str):
        raise RuntimeError("verified read-out lacks scalar crop contract JSON/SHA256")
    actual_digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    require_equal(actual_digest, digest, "crop contract JSON/SHA256")
    require_equal(digest, PILOT_CROP_CONTRACT_SHA256, "locked crop contract SHA256")
    try:
        payload = json.loads(encoded)
    except json.JSONDecodeError as exc:
        raise RuntimeError("crop contract JSON is invalid") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("crop contract JSON root must be an object")
    require_equal(payload, PILOT_CROP_CONTRACT, "locked crop contract contents")
    require_equal(canonical_json(payload), encoded, "canonical crop contract JSON")
    population = payload["population"]
    ordered_ids = tuple(str(value) for value in population["ordered_building_ids"])
    require_equal(ordered_ids, PILOT_BUILDING_IDS, "crop contract ordered building IDs")
    require_equal(len(set(ordered_ids)), len(PILOT_BUILDING_IDS), "crop contract unique IDs")
    return {
        "schema": PILOT_CROP_CONTRACT_SCHEMA,
        "json": encoded,
        "sha256": digest,
        "crs": "EPSG:25832",
        "population_count": len(PILOT_BUILDING_IDS),
        "ordered_building_ids": list(PILOT_BUILDING_IDS),
        "ordered_ids_sha256": PILOT_ORDERED_IDS_SHA256,
        "crop_bbox_utm": list(payload["crop"]["bbox_utm"]),
        "crop_area_m2": float(payload["crop"]["area_m2"]),
    }


def _all_coordinate_lengths(value: Any):
    if isinstance(value, list):
        if value and all(isinstance(item, (int, float)) for item in value):
            yield len(value)
        else:
            for item in value:
                yield from _all_coordinate_lengths(item)


def validate_roofprint_file(
    path: Path,
    *,
    expected_building_ids: tuple[str, ...] | list[str] | None = None,
    expected_count: int = 30,
) -> dict[str, Any]:
    """Re-open the exact XY/class-6 roofprint file used by PDAL and Roofer."""

    path = path.resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("roofprint root must be an object")
    features = payload.get("features")
    if not isinstance(features, list):
        raise RuntimeError("roofprint features must be an array")
    expected = tuple(expected_building_ids) if expected_building_ids is not None else None
    required_count = len(expected) if expected is not None else int(expected_count)
    require_equal(len(features), required_count, "roofprint population")
    crs_record = payload.get("crs")
    crs_properties = (
        crs_record.get("properties") if isinstance(crs_record, Mapping) else None
    )
    crs = str(
        crs_properties.get("name", "")
        if isinstance(crs_properties, Mapping)
        else ""
    )
    crs_code = (
        crs.rstrip("/").replace("::", ":").rsplit(":", 1)[-1].rsplit("/", 1)[-1]
    )
    if crs_code != "25832":
        raise RuntimeError(f"roofprint CRS drift: {crs!r}")
    building_ids: list[str] = []
    feature_properties: list[dict[str, Any]] = []
    ordered_geometry: list[dict[str, Any]] = []
    for feature in features:
        if not isinstance(feature, Mapping):
            raise RuntimeError("roofprint feature must be an object")
        properties = feature.get("properties")
        geometry = feature.get("geometry")
        if not isinstance(properties, Mapping) or not isinstance(geometry, Mapping):
            raise RuntimeError("roofprint properties/geometry must be objects")
        building_id = str(properties.get("building_id", ""))
        if not building_id:
            raise RuntimeError("roofprint without building_id")
        if properties.get("class") != 6:
            raise RuntimeError(
                f"roofprint overlay class drift for {building_id}: "
                f"{properties.get('class')!r} != 6"
            )
        if expected is not None:
            require_equal(
                building_id,
                expected[len(building_ids)],
                "roofprint ordered building IDs",
            )
            expected_properties = {
                "building_id": expected[len(building_ids)],
                "selection_rank": len(building_ids) + 1,
                "class": 6,
            }
            require_equal(
                dict(properties),
                expected_properties,
                f"roofprint properties {building_id}",
            )
        building_ids.append(building_id)
        feature_properties.append(dict(properties))
        ordered_geometry.append(
            {"building_id": building_id, "geometry": dict(geometry)}
        )
        lengths = list(
            _all_coordinate_lengths(geometry.get("coordinates"))
        )
        if not lengths or any(length != 2 for length in lengths):
            raise RuntimeError(f"roofprint is not XY-only: {building_id}")
    require_equal(len(set(building_ids)), len(building_ids), "roofprint unique building IDs")
    if expected is not None:
        require_equal(tuple(building_ids), expected, "roofprint ordered building IDs")
    return {
        "path": str(path),
        "sha256": sha256_file(path),
        "feature_count": len(features),
        "building_ids": building_ids,
        "feature_properties": feature_properties,
        "ordered_feature_geometry_sha256": hashlib.sha256(
            canonical_json(ordered_geometry).encode("utf-8")
        ).hexdigest(),
        "crs": "EPSG:25832",
        "coordinate_dimension": 2,
    }


def canonical_repo_path(path: Path, *, repo_root: Path = REPO) -> str:
    """Return one environment-independent repository-relative POSIX path."""

    resolved = path.resolve()
    root = repo_root.resolve()
    try:
        relative = resolved.relative_to(root)
    except ValueError as exc:
        raise RuntimeError(f"lineage artifact is outside repository: {resolved}") from exc
    if not relative.parts or ".." in relative.parts:
        raise RuntimeError(f"invalid repository-relative lineage path: {relative}")
    return relative.as_posix()


def resolve_declared_path(value: Any, *, declaring_file: Path) -> Path:
    """Resolve repository/container paths without accepting ambiguous bytes."""

    text = str(value or "").strip()
    if not text:
        raise RuntimeError(f"empty path declared by {declaring_file}")
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
    existing = [candidate.resolve() for candidate in candidates if candidate.exists()]
    unique = {str(candidate) for candidate in existing}
    if not unique:
        raise FileNotFoundError(
            f"declared artifact does not exist: {text} ({declaring_file})"
        )
    if len(unique) != 1:
        raise RuntimeError(f"ambiguous declared path: {text} -> {sorted(unique)}")
    return Path(next(iter(unique)))


def validate_condition_seed(condition_id: str, seed: int) -> None:
    if condition_id not in CONDITION_ARMS:
        raise RuntimeError(f"unknown condition_id: {condition_id}")
    if int(seed) not in EXPECTED_SEEDS:
        raise RuntimeError(f"unknown seed: {seed}")


def _load_config_identity(path: Path) -> dict[str, Any]:
    """Read only the locked top-level identity keys from JSON or simple YAML."""

    if path.suffix.lower() == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise RuntimeError(f"training config must be an object: {path}")
        return payload
    result: dict[str, Any] = {}
    wanted = {"max_iter", "pilot_arm", "seed"}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        if raw_line[:1].isspace() or ":" not in raw_line:
            continue
        key, raw_value = raw_line.split(":", 1)
        key = key.strip()
        if key not in wanted:
            continue
        value = raw_value.split(" #", 1)[0].strip().strip("'\"")
        if key in {"max_iter", "seed"}:
            try:
                result[key] = int(value)
            except ValueError as exc:
                raise RuntimeError(f"invalid {key} in training config: {path}") from exc
        else:
            result[key] = value
    return result


def validate_full_state_binding(
    *,
    checkpoint_path: Path,
    checkpoint_sha256: str,
    completed_steps: int,
    condition_id: str,
    seed: int,
    manifest_path: Path,
    checkpoint_binding_sha256: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Verify that one manifest declares these exact checkpoint bytes."""

    validate_condition_seed(condition_id, seed)
    checkpoint_path = checkpoint_path.resolve()
    manifest_path = manifest_path.resolve()
    if not checkpoint_path.is_file() or not manifest_path.is_file():
        raise FileNotFoundError(
            checkpoint_path if not checkpoint_path.is_file() else manifest_path
        )
    actual_checkpoint_sha = sha256_file(checkpoint_path)
    require_equal(actual_checkpoint_sha, checkpoint_sha256, "checkpoint SHA256")
    if int(completed_steps) not in FULL_STATE_STEPS:
        raise RuntimeError(f"checkpoint step is outside the locked schedule: {completed_steps}")

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("full-state manifest root must be an object")
    require_equal(
        payload.get("schema"), FULL_STATE_MANIFEST_SCHEMA, "full-state manifest schema"
    )
    require_equal(int(payload.get("max_iter", -1)), MAX_ITER, "full-state max_iter")
    require_equal(
        payload.get("step_semantics"),
        FULL_STATE_STEP_SEMANTICS,
        "full-state step semantics",
    )
    schedule = tuple(int(value) for value in payload.get("checkpoint_steps", []))
    missing = sorted(set(FULL_STATE_STEPS) - set(schedule))
    if missing:
        raise RuntimeError(f"full-state checkpoint schedule missing: {missing}")
    require_equal(
        int(payload.get("last_completed_steps", -1)),
        int(completed_steps),
        "manifest/checkpoint completed steps",
    )
    if int(payload.get("learning_runs_started", 0) or 0) < 1:
        raise RuntimeError("full-state manifest does not prove a learning run")

    latest = payload.get("latest_full_checkpoint")
    if not isinstance(latest, Mapping):
        raise RuntimeError("full-state manifest has no latest_full_checkpoint")
    declared_checkpoint = resolve_declared_path(
        latest.get("path"), declaring_file=manifest_path
    )
    require_equal(declared_checkpoint, checkpoint_path, "manifest checkpoint path")
    require_equal(
        int(latest.get("completed_steps", -1)),
        int(completed_steps),
        "manifest checkpoint step",
    )
    require_equal(latest.get("sha256"), actual_checkpoint_sha, "manifest checkpoint SHA256")

    config_path = resolve_declared_path(
        payload.get("config_path"), declaring_file=manifest_path
    )
    config_sha = sha256_file(config_path)
    require_equal(config_sha, payload.get("config_file_sha256"), "training config SHA256")
    config = _load_config_identity(config_path)
    require_equal(int(config.get("max_iter", -1)), MAX_ITER, "training config max_iter")
    require_equal(config.get("pilot_arm"), CONDITION_ARMS[condition_id], "training config arm")
    require_equal(int(config.get("seed", -1)), int(seed), "training config seed")

    manifest_binding = payload.get("binding_sha256")
    if checkpoint_binding_sha256 is not None:
        require_equal(
            dict(manifest_binding or {}),
            dict(checkpoint_binding_sha256),
            "checkpoint/manifest binding SHA256",
        )

    eligible_20k = (
        int(completed_steps) == MAX_ITER
        and payload.get("process_completed") is True
        and int(payload.get("process_completed_steps", -1)) == MAX_ITER
    )
    if int(completed_steps) == MAX_ITER and not eligible_20k:
        raise RuntimeError("20k checkpoint lacks the completed trainer epilogue")
    return {
        "schema": LINEAGE_SCHEMA,
        "condition_id": condition_id,
        "seed": int(seed),
        "checkpoint": {
            "format": FULL_STATE_CHECKPOINT_FORMAT,
            "path": canonical_repo_path(checkpoint_path),
            "sha256": actual_checkpoint_sha,
            "completed_steps": int(completed_steps),
            "step_semantics": FULL_STATE_STEP_SEMANTICS,
        },
        "full_state_manifest": {
            "path": canonical_repo_path(manifest_path),
            "sha256": sha256_file(manifest_path),
            "schema": FULL_STATE_MANIFEST_SCHEMA,
        },
        "training_config": {
            "path": canonical_repo_path(config_path),
            "sha256": config_sha,
            "pilot_arm": config["pilot_arm"],
        },
        "verified_full_state": True,
        "eligible_20k_full_state": eligible_20k,
    }


def validate_readout_lineage(
    lineage: Mapping[str, Any],
    *,
    expected_condition: str | None = None,
    expected_seed: int | None = None,
    allow_unverified_legacy: bool = False,
) -> dict[str, Any]:
    """Re-open and verify every immutable artifact named by a lineage record."""

    if not isinstance(lineage, Mapping):
        raise RuntimeError("read-out lineage must be an object")
    require_equal(lineage.get("schema"), LINEAGE_SCHEMA, "read-out lineage schema")
    condition_id = str(lineage.get("condition_id", ""))
    seed = int(lineage.get("seed", -1))
    validate_condition_seed(condition_id, seed)
    if expected_condition is not None:
        require_equal(condition_id, expected_condition, "read-out lineage condition")
    if expected_seed is not None:
        require_equal(seed, int(expected_seed), "read-out lineage seed")
    if lineage.get("geometry_only") is not True:
        raise RuntimeError("read-out lineage is not geometry-only")

    checkpoint = lineage.get("checkpoint")
    if not isinstance(checkpoint, Mapping):
        raise RuntimeError("read-out lineage lacks a checkpoint record")
    if lineage.get("verified_full_state") is False:
        if not allow_unverified_legacy:
            raise RuntimeError("read-out lineage is not a verified full state")
        require_equal(checkpoint.get("format"), "legacy_state_dict", "legacy checkpoint format")
        require_equal(
            checkpoint.get("step_semantics"), "legacy_iteration", "legacy checkpoint semantics"
        )
        legacy_path = resolve_declared_path(
            checkpoint.get("path"), declaring_file=REPO / "lineage.json"
        )
        require_equal(sha256_file(legacy_path), checkpoint.get("sha256"), "legacy checkpoint SHA256")
        if int(checkpoint.get("completed_steps", -1)) < 0:
            raise RuntimeError("legacy checkpoint completed steps are invalid")
        require_equal(lineage.get("full_state_manifest"), None, "legacy full-state manifest")
        require_equal(lineage.get("training_config"), None, "legacy training config")
        require_equal(
            lineage.get("eligible_20k_full_state"), False, "legacy 20k eligibility"
        )
        if lineage.get("crop_contract_json") is not None or lineage.get(
            "crop_contract_sha256"
        ) is not None:
            raise RuntimeError("unverified legacy lineage must not carry a crop contract")
        return {
            "schema": LINEAGE_SCHEMA,
            "condition_id": condition_id,
            "seed": seed,
            "checkpoint": {
                "format": "legacy_state_dict",
                "path": canonical_repo_path(legacy_path),
                "sha256": sha256_file(legacy_path),
                "completed_steps": int(checkpoint["completed_steps"]),
                "step_semantics": "legacy_iteration",
            },
            "full_state_manifest": None,
            "training_config": None,
            "verified_full_state": False,
            "eligible_20k_full_state": False,
            "geometry_only": True,
        }
    if lineage.get("verified_full_state") is not True:
        raise RuntimeError("read-out lineage verified_full_state must be true or false")

    manifest = lineage.get("full_state_manifest")
    if not isinstance(manifest, Mapping):
        raise RuntimeError("read-out lineage lacks a full-state manifest record")
    require_equal(
        checkpoint.get("format"), FULL_STATE_CHECKPOINT_FORMAT, "checkpoint format"
    )
    require_equal(
        checkpoint.get("step_semantics"),
        FULL_STATE_STEP_SEMANTICS,
        "checkpoint step semantics",
    )
    step = int(checkpoint.get("completed_steps", -1))
    checkpoint_path = resolve_declared_path(
        checkpoint.get("path"), declaring_file=REPO / "lineage.json"
    )
    manifest_path = resolve_declared_path(
        manifest.get("path"), declaring_file=REPO / "lineage.json"
    )
    require_equal(sha256_file(checkpoint_path), checkpoint.get("sha256"), "checkpoint SHA256")
    require_equal(
        sha256_file(manifest_path), manifest.get("sha256"), "full-state manifest SHA256"
    )
    normalized = validate_full_state_binding(
        checkpoint_path=checkpoint_path,
        checkpoint_sha256=str(checkpoint.get("sha256", "")),
        completed_steps=step,
        condition_id=condition_id,
        seed=seed,
        manifest_path=manifest_path,
    )
    require_equal(
        bool(lineage.get("eligible_20k_full_state")),
        bool(normalized["eligible_20k_full_state"]),
        "read-out lineage 20k eligibility",
    )
    crop_contract = validate_pilot_crop_contract(
        lineage.get("crop_contract_json"), lineage.get("crop_contract_sha256")
    )
    normalized["geometry_only"] = True
    normalized["crop_contract_json"] = crop_contract["json"]
    normalized["crop_contract_sha256"] = crop_contract["sha256"]
    return normalized


def validate_scene_npz_binding(
    npz_path: Path,
    *,
    expected_condition: str | None = None,
    expected_seed: int | None = None,
    allow_unverified_legacy: bool = False,
) -> dict[str, Any]:
    """Validate duplicated NPZ lineage/crop scalars without allowing pickle."""

    npz_path = npz_path.resolve()
    if not npz_path.is_file():
        raise FileNotFoundError(npz_path)
    try:
        with np.load(npz_path, allow_pickle=False) as npz:
            if "readout_lineage_json" not in npz:
                raise RuntimeError("source NPZ lacks readout_lineage_json")
            lineage_json = _scalar_text(
                npz["readout_lineage_json"], "source NPZ readout_lineage_json"
            )
            has_crop_json = "crop_contract_json" in npz
            has_crop_sha = "crop_contract_sha256" in npz
            crop_json = (
                _scalar_text(npz["crop_contract_json"], "source NPZ crop_contract_json")
                if has_crop_json
                else None
            )
            crop_sha = (
                _scalar_text(npz["crop_contract_sha256"], "source NPZ crop_contract_sha256")
                if has_crop_sha
                else None
            )
    except ValueError as exc:
        raise RuntimeError("source NPZ lineage/crop contract must not require pickle") from exc
    try:
        embedded_lineage = json.loads(lineage_json)
    except json.JSONDecodeError as exc:
        raise RuntimeError("source NPZ readout lineage is invalid JSON") from exc
    if not isinstance(embedded_lineage, dict):
        raise RuntimeError("source NPZ readout lineage must be an object")
    normalized = validate_readout_lineage(
        embedded_lineage,
        expected_condition=expected_condition,
        expected_seed=expected_seed,
        allow_unverified_legacy=allow_unverified_legacy,
    )
    if normalized["verified_full_state"]:
        if not has_crop_json or not has_crop_sha:
            raise RuntimeError("verified source NPZ lacks duplicated crop contract JSON/SHA256")
        crop_contract = validate_pilot_crop_contract(crop_json, crop_sha)
        require_equal(
            crop_json,
            embedded_lineage.get("crop_contract_json"),
            "source NPZ/lineage crop contract JSON",
        )
        require_equal(
            crop_sha,
            embedded_lineage.get("crop_contract_sha256"),
            "source NPZ/lineage crop contract SHA256",
        )
    else:
        if has_crop_json or has_crop_sha:
            raise RuntimeError("unverified legacy source NPZ must not carry a crop contract")
        crop_contract = None
    return {
        "path": str(npz_path),
        "sha256": sha256_file(npz_path),
        "readout_lineage": normalized,
        "crop_contract": crop_contract,
    }


def validate_classification_receipt(
    receipt_path: Path,
    *,
    pointcloud_path: Path,
    expected_condition: str,
    expected_seed: int,
    expected_building_ids: tuple[str, ...] | list[str] | None = None,
    require_verified_crop: bool = True,
) -> dict[str, Any]:
    """Bind LAS, crop contract, and the exact PDAL/Roofer roofprint bytes."""

    receipt_path = receipt_path.resolve()
    pointcloud_path = pointcloud_path.resolve()
    if not receipt_path.is_file() or not pointcloud_path.is_file():
        raise FileNotFoundError(
            receipt_path if not receipt_path.is_file() else pointcloud_path
        )
    payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("classification receipt root must be an object")
    require_equal(payload.get("schema"), CLASSIFICATION_SCHEMA, "classification schema")
    require_equal(payload.get("state"), "complete", "classification state")
    classified = payload.get("classified_las")
    source_npz = payload.get("source_scene_npz")
    if not isinstance(classified, Mapping) or not isinstance(source_npz, Mapping):
        raise RuntimeError("classification receipt lacks LAS/NPZ records")
    declared_las = resolve_declared_path(
        classified.get("path"), declaring_file=receipt_path
    )
    require_equal(declared_las, pointcloud_path, "classification LAS path")
    require_equal(
        sha256_file(pointcloud_path), classified.get("sha256"), "classification LAS SHA256"
    )
    npz_path = resolve_declared_path(source_npz.get("path"), declaring_file=receipt_path)
    require_equal(sha256_file(npz_path), source_npz.get("sha256"), "source NPZ SHA256")
    scene_binding = validate_scene_npz_binding(
        npz_path,
        expected_condition=expected_condition,
        expected_seed=expected_seed,
        allow_unverified_legacy=not require_verified_crop,
    )
    lineage = scene_binding["readout_lineage"]
    crop_contract = scene_binding["crop_contract"]
    if require_verified_crop and crop_contract is None:
        raise RuntimeError("P1W classification receipt requires a verified crop contract")
    require_equal(
        lineage,
        payload.get("readout_lineage"),
        "source NPZ/classification lineage",
    )
    require_equal(
        crop_contract,
        payload.get("crop_contract"),
        "source NPZ/classification crop contract",
    )

    receipt_roofprints = payload.get("roofprints")
    if not isinstance(receipt_roofprints, Mapping):
        raise RuntimeError("classification receipt lacks a roofprint record")
    roofprint_path = resolve_declared_path(
        receipt_roofprints.get("path"), declaring_file=receipt_path
    )
    crop_ids = (
        tuple(crop_contract["ordered_building_ids"])
        if crop_contract is not None
        else None
    )
    roofprints = validate_roofprint_file(
        roofprint_path,
        expected_building_ids=crop_ids,
    )
    for field in (
        "sha256",
        "feature_count",
        "building_ids",
        "feature_properties",
        "ordered_feature_geometry_sha256",
        "crs",
        "coordinate_dimension",
    ):
        require_equal(
            receipt_roofprints.get(field),
            roofprints[field],
            f"classification receipt roofprints {field}",
        )
    expected_ids = (
        tuple(expected_building_ids) if expected_building_ids is not None else None
    )
    if expected_ids is not None:
        require_equal(
            tuple(roofprints["building_ids"]),
            expected_ids,
            "classification/score ordered building IDs",
        )

    classification = payload.get("classification")
    if not isinstance(classification, Mapping):
        raise RuntimeError("classification receipt lacks a PDAL pipeline record")
    pipeline_path = resolve_declared_path(
        classification.get("pipeline_path"), declaring_file=receipt_path
    )
    require_equal(
        sha256_file(pipeline_path),
        classification.get("pipeline_sha256"),
        "classification pipeline SHA256",
    )
    pipeline_payload = json.loads(pipeline_path.read_text(encoding="utf-8"))
    stages = pipeline_payload.get("pipeline") if isinstance(pipeline_payload, dict) else None
    if not isinstance(stages, list):
        raise RuntimeError("classification PDAL pipeline stages are invalid")
    if any(not isinstance(stage, Mapping) for stage in stages):
        raise RuntimeError("classification PDAL pipeline stage must be an object")
    overlays = [stage for stage in stages if stage.get("type") == "filters.overlay"]
    writers = [stage for stage in stages if stage.get("type") == "writers.las"]
    require_equal(len(overlays), 1, "classification overlay stage count")
    require_equal(len(writers), 1, "classification LAS writer stage count")
    overlay_path = resolve_declared_path(
        overlays[0].get("datasource"), declaring_file=pipeline_path
    )
    writer_path = resolve_declared_path(
        writers[0].get("filename"), declaring_file=pipeline_path
    )
    require_equal(overlay_path, roofprint_path, "classification pipeline roofprint path")
    require_equal(writer_path, pointcloud_path, "classification pipeline LAS path")
    require_equal(overlays[0].get("dimension"), "Classification", "overlay dimension")
    require_equal(overlays[0].get("column"), "class", "overlay class column")
    require_equal(overlays[0].get("where"), "Classification != 2", "overlay ground gate")
    return {
        "path": str(receipt_path),
        "sha256": sha256_file(receipt_path),
        "scene_npz_path": str(npz_path),
        "scene_npz_sha256": source_npz.get("sha256"),
        "pointcloud_path": str(pointcloud_path),
        "pointcloud_sha256": classified.get("sha256"),
        "readout_lineage": lineage,
        "crop_contract": crop_contract,
        "roofprints": roofprints,
        "classification_pipeline_path": str(pipeline_path),
        "classification_pipeline_sha256": classification.get("pipeline_sha256"),
    }
