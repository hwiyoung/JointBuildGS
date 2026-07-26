#!/usr/bin/env python3
"""A-prime T3 P0-prime assembly baseline (learning=0).

The only geometry inputs are the A-prime preprocessor's visibility-filtered
class-6 LAS and its separately published, original class-2 ground LAS.  They
are concatenated in source row order, checked at semantic-row granularity,
and passed to Roofer with the approved GroundSurface XY footprint.  The
existing P0-prime execution engine is reused only for the locked Roofer,
CityJSON, val3dity, metric, and incremental-publication conventions.

No old arm-A preprocessing, training, readout, or P0-prime result is read as
a numeric input.  Reference GML remains evaluation-only and is opened only
after Roofer output is frozen.  This driver records measurements, not a
verdict.
"""
from __future__ import annotations

import argparse
import copy
import csv
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import traceback
from typing import Any, Mapping, Sequence


REPO = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = (
    REPO
    / "phases/p2-gsjso/configs/fusion_w1_aprime_p0prime_20260726.json"
)
CONFIG_SCHEMA = "jointbuildgs.fusion_w1_aprime.p0prime.config.v1"
BUILDING_RECEIPT_SCHEMA = (
    "jointbuildgs.fusion_w1_aprime.p0prime.building_receipt.v1"
)
CHECK_SCHEMA = "jointbuildgs.fusion_w1_aprime.p0prime.check.v1"
JOIN_SCHEMA = "jointbuildgs.fusion_w1_aprime.p0prime.join_receipt.v1"
SCORE_SCHEMA = "jointbuildgs.fusion_w1_aprime.p0prime.score.v1"
REFERENCE_SCHEMA = (
    "jointbuildgs.fusion_w1_aprime.p0prime.reference_receipt.v1"
)
FAILURE_SCHEMA = "jointbuildgs.fusion_w1_aprime.p0prime.failure.v1"
FINAL_SCHEMA = "jointbuildgs.fusion_w1_aprime.p0prime.manifest.v1"


class AprimeP0PrimeError(RuntimeError):
    """Fail-closed T3 input, row-preservation, or execution error."""


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def sha256_file(path: Path, block_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(block_size), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_json(payload: Any) -> bytes:
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def repo_path(value: str | Path) -> Path:
    raw = Path(value)
    if raw.is_absolute():
        raise AprimeP0PrimeError(f"absolute repository path forbidden: {raw}")
    result = (REPO / raw).resolve()
    try:
        result.relative_to(REPO.resolve())
    except ValueError as exc:
        raise AprimeP0PrimeError(f"path escapes repository: {raw}") from exc
    return result


def repo_relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO.resolve()))
    except ValueError as exc:
        raise AprimeP0PrimeError(f"path outside repository: {path}") from exc


def resolve_declared_path(value: Any, *, declaring_file: Path) -> Path:
    if not isinstance(value, str) or not value:
        raise AprimeP0PrimeError(
            f"missing declared path in {repo_relative(declaring_file)}"
        )
    raw = Path(value)
    if raw.is_absolute():
        raise AprimeP0PrimeError(f"absolute declared path forbidden: {value}")
    candidates = [
        (REPO / raw).resolve(),
        (declaring_file.parent / raw).resolve(),
    ]
    valid: list[Path] = []
    for candidate in candidates:
        try:
            candidate.relative_to(REPO.resolve())
        except ValueError:
            continue
        if candidate not in valid:
            valid.append(candidate)
    existing = [path for path in valid if path.exists()]
    if len(existing) == 1:
        return existing[0]
    if len(existing) > 1 and existing[0] != existing[1]:
        raise AprimeP0PrimeError(
            f"ambiguous declared path {value!r} in {repo_relative(declaring_file)}"
        )
    if valid:
        return valid[0]
    raise AprimeP0PrimeError(f"declared path escapes repository: {value}")


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise AprimeP0PrimeError(
            f"missing/non-regular JSON: {repo_relative(path)}"
        )
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise AprimeP0PrimeError(f"JSON root is not object: {repo_relative(path)}")
    return payload


def load_config(path: Path) -> dict[str, Any]:
    config = load_json(path)
    if config.get("schema") != CONFIG_SCHEMA:
        raise AprimeP0PrimeError(f"unexpected config schema: {config.get('schema')}")
    score = config.get("score_contract", {})
    if score.get("learning_runs_started") != 0:
        raise AprimeP0PrimeError("T3 learning counter lock is not zero")
    if score.get("new_inference_runs") != 0:
        raise AprimeP0PrimeError("T3 inference counter lock is not zero")
    if score.get("interpretation_or_verdict") is not None:
        raise AprimeP0PrimeError("T3 verdict field must remain null")
    if config["roofer"].get("default_reconstruction_parameters_preserved") is not True:
        raise AprimeP0PrimeError("Roofer default reconstruction lock is absent")
    if config["roofer"].get("reconstruction_parameter_overrides") != []:
        raise AprimeP0PrimeError("Roofer reconstruction override list is not empty")
    if config["resource_lock"].get("serial_buildings") is not True:
        raise AprimeP0PrimeError("serial-building resource lock is absent")
    join = config["join_contract"]
    if join.get("class_order") != [6, 2]:
        raise AprimeP0PrimeError("T3 class concatenation order drift")
    for key in (
        "geometry_changed",
        "classification_changed",
        "row_order_changed_within_source",
        "downsample_applied",
    ):
        if join.get(key) is not False:
            raise AprimeP0PrimeError(f"T3 join mutation lock drift: {key}")
    if int(join.get("rows_removed", -1)) != 0 or int(join.get("rows_added", -1)) != 0:
        raise AprimeP0PrimeError("T3 join row-count lock drift")
    return config


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file() or path.is_symlink():
        raise AprimeP0PrimeError(f"missing/non-regular CSV: {repo_relative(path)}")
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise AprimeP0PrimeError(f"CSV has no header: {repo_relative(path)}")
        return [dict(row) for row in reader]


def target_rows(config: Mapping[str, Any]) -> list[dict[str, str]]:
    contract = config["targets"]
    path = repo_path(contract["path"])
    if sha256_file(path) != contract["sha256"]:
        raise AprimeP0PrimeError("A-prime target CSV SHA drift")
    rows = read_csv(path)
    if len(rows) != int(contract["expected_population"]):
        raise AprimeP0PrimeError(f"A-prime target population drift: {len(rows)}")
    id_field = contract["id_field"]
    order_field = contract["order_field"]
    ids = [row[id_field] for row in rows]
    orders = [int(row[order_field]) for row in rows]
    if len(ids) != len(set(ids)):
        raise AprimeP0PrimeError("duplicate A-prime target building ID")
    if sorted(orders) != list(range(1, len(rows) + 1)):
        raise AprimeP0PrimeError("A-prime order is not a 1..N permutation")
    adapted = []
    for row in sorted(rows, key=lambda value: int(value[order_field])):
        value = dict(row)
        value["processing_order"] = value[order_field]
        adapted.append(value)
    return adapted


def target_row(config: Mapping[str, Any], building_id: str) -> dict[str, str]:
    matches = [
        row
        for row in target_rows(config)
        if row[config["targets"]["id_field"]] == building_id
    ]
    if len(matches) != 1:
        raise AprimeP0PrimeError(
            f"building is not a unique A-prime target: {building_id}"
        )
    return matches[0]


def static_locks(config: Mapping[str, Any]) -> list[tuple[str, str]]:
    locks = [
        (config["targets"]["path"], config["targets"]["sha256"]),
        (config["prereg_lock"]["path"], config["prereg_lock"]["sha256"]),
        (config["footprint"]["path"], config["footprint"]["sha256"]),
        (
            config["p0_refl_baseline"]["path"],
            config["p0_refl_baseline"]["sha256"],
        ),
    ]
    for helper in config["canonical_helpers"].values():
        locks.append((helper["path"], helper["sha256"]))
    locks.extend(config["reference"]["locked_files"].items())
    return locks


def verify_static_inputs(config: Mapping[str, Any]) -> dict[str, str]:
    observed: dict[str, str] = {}
    for logical, expected in static_locks(config):
        path = repo_path(logical)
        if not path.is_file() or path.is_symlink():
            raise AprimeP0PrimeError(f"locked input missing/non-regular: {logical}")
        actual = sha256_file(path)
        if actual != expected:
            raise AprimeP0PrimeError(f"locked SHA drift: {logical}")
        observed[logical] = actual
    baseline = config["p0_refl_baseline"]
    rows = [
        row
        for row in read_csv(repo_path(baseline["path"]))
        if row.get("model_id") == baseline["model_id"]
        and row.get("role") == baseline["role"]
    ]
    ids = [row.get("building_id", "") for row in rows]
    if (
        len(rows) != int(baseline["expected_population"])
        or len(ids) != len(set(ids))
        or any(not value for value in ids)
    ):
        raise AprimeP0PrimeError("P0 Ref-L attribution-control population drift")
    lod2 = sum(str(row.get("has_lod22", "")).lower() in {"true", "1"} for row in rows)
    if lod2 != int(baseline["expected_lod2_count"]):
        raise AprimeP0PrimeError("P0 Ref-L attribution-control LoD2 count drift")
    prereg = load_json(repo_path(config["prereg_lock"]["path"]))
    if (
        prereg.get("schema") != "jointbuildgs.fusion_w1_aprime.prereg_lock.v1"
        or prereg.get("verdict") is not None
        or prereg.get("run_id") != config["run_id"]
    ):
        raise AprimeP0PrimeError("A-prime prereg lock/verdict state drift")
    return observed


def git(*arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    process = subprocess.run(
        [
            "git",
            "-c",
            f"safe.directory={REPO}",
            "-C",
            str(REPO),
            *arguments,
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and process.returncode:
        raise AprimeP0PrimeError(
            process.stderr.strip() or process.stdout.strip() or "git command failed"
        )
    return process


def verify_git_runtime(config: Mapping[str, Any]) -> dict[str, Any]:
    branch = git("branch", "--show-current").stdout.strip()
    head = git("rev-parse", "HEAD").stdout.strip()
    if branch != config["branch"]:
        raise AprimeP0PrimeError(f"branch mismatch: {branch}")
    records = []
    for logical in config["implementation_files"]:
        tracked = bool(git("ls-files", "--", logical).stdout.strip())
        at_head = git("cat-file", "-e", f"{head}:{logical}", check=False).returncode == 0
        worktree = git("hash-object", "--", logical).stdout.strip()
        head_blob = git("rev-parse", f"{head}:{logical}", check=False)
        unchanged = head_blob.returncode == 0 and worktree == head_blob.stdout.strip()
        if not tracked or not at_head or not unchanged:
            raise AprimeP0PrimeError(f"implementation not committed at HEAD: {logical}")
        records.append(
            {
                "path": logical,
                "tracked_at_head": True,
                "worktree_matches_head": True,
                "git_blob": worktree,
            }
        )
    return {"branch": branch, "head": head, "implementation_files": records}


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _forbid_old_input(config: Mapping[str, Any], path: Path) -> None:
    for logical in config["preprocess_consumer"]["old_arm_a_inputs_forbidden"]:
        if _inside(path, repo_path(logical)):
            raise AprimeP0PrimeError(
                f"old arm-A numeric input forbidden: {repo_relative(path)}"
            )


def preprocess_resolution(
    config: Mapping[str, Any], building_id: str
) -> dict[str, Any]:
    """Resolve one building through only the A-prime stable run publication."""

    contract = config["preprocess_consumer"]
    stable_path = repo_path(contract["stable_run_manifest"])
    stable = load_json(stable_path)
    if stable.get("schema") != contract["run_schema"]:
        raise AprimeP0PrimeError("A-prime stable preprocess schema mismatch")
    if stable.get("status") not in set(contract["allowed_run_status"]):
        raise AprimeP0PrimeError("A-prime stable preprocess status not consumable")
    target_binding = stable.get("target_binding") or {}
    if target_binding.get("sha256") != config["targets"]["sha256"]:
        raise AprimeP0PrimeError("A-prime stable preprocess target SHA drift")
    if int(target_binding.get("population_n", -1)) != int(
        config["targets"]["expected_population"]
    ):
        raise AprimeP0PrimeError("A-prime stable preprocess target population drift")
    pose = stable.get("pose_binding") or {}
    if pose.get("corrected_images_sha256") != contract["required_pose_sha256"]:
        raise AprimeP0PrimeError("A-prime stable preprocess pose SHA drift")
    if int(pose.get("transform_application_count", -1)) != int(
        contract["required_transform_application_count"]
    ):
        raise AprimeP0PrimeError("A-prime stable preprocess pose application drift")
    if int(pose.get("additional_transform_application_count", -1)) != int(
        contract["required_additional_transform_application_count"]
    ):
        raise AprimeP0PrimeError("A-prime stable preprocess extra transform detected")

    cache = stable.get("cache_binding")
    if not isinstance(cache, Mapping):
        raise AprimeP0PrimeError("A-prime stable preprocess lacks cache_binding")
    namespace = str(cache.get("namespace", ""))
    if namespace != contract["required_cache_namespace"]:
        raise AprimeP0PrimeError("A-prime preprocess cache namespace drift")
    cache_dir = resolve_declared_path(cache.get("cache_dir"), declaring_file=stable_path)
    if cache_dir.name != namespace or not cache_dir.is_dir():
        raise AprimeP0PrimeError("A-prime cache_dir/namespace mismatch")
    _forbid_old_input(config, cache_dir)

    index_record = stable.get("preprocess_index")
    if not isinstance(index_record, Mapping):
        raise AprimeP0PrimeError("A-prime stable preprocess lacks index record")
    index_path = resolve_declared_path(index_record.get("path"), declaring_file=stable_path)
    if not _inside(index_path, cache_dir):
        raise AprimeP0PrimeError("A-prime preprocess index escapes cache")
    if sha256_file(index_path) != index_record.get("sha256"):
        raise AprimeP0PrimeError("A-prime preprocess index SHA drift")
    index_rows = read_csv(index_path)
    matches = [row for row in index_rows if row.get("building_id") == building_id]
    if len(matches) != 1:
        raise AprimeP0PrimeError(
            f"A-prime preprocess index row is not unique: {building_id}"
        )
    index_row = matches[0]
    if index_row.get("status") != contract["required_building_status"]:
        raise AprimeP0PrimeError("A-prime preprocess building is not PASSED")
    manifest_path = resolve_declared_path(
        index_row.get("building_manifest_path"), declaring_file=index_path
    )
    if not _inside(manifest_path, cache_dir):
        raise AprimeP0PrimeError("A-prime building manifest escapes cache")
    if sha256_file(manifest_path) != index_row.get("building_manifest_sha256"):
        raise AprimeP0PrimeError("A-prime index/building manifest SHA drift")
    published = [
        row
        for row in (stable.get("buildings") or [])
        if isinstance(row, Mapping) and row.get("building_id") == building_id
    ]
    if len(published) != 1:
        raise AprimeP0PrimeError("A-prime stable building record is not unique")
    if published[0].get("building_manifest_sha256") != sha256_file(manifest_path):
        raise AprimeP0PrimeError("A-prime stable/index manifest binding drift")
    return {
        "stable_path": stable_path,
        "stable_sha256": sha256_file(stable_path),
        "stable": stable,
        "cache_namespace": namespace,
        "cache_dir": cache_dir,
        "index_path": index_path,
        "index_sha256": sha256_file(index_path),
        "index_row": index_row,
        "manifest_path": manifest_path,
        "manifest_sha256": sha256_file(manifest_path),
    }


def _artifact_record(
    payload: Mapping[str, Any], dotted: str
) -> Mapping[str, Any]:
    value: Any = payload
    for key in dotted.split("."):
        if not isinstance(value, Mapping):
            raise AprimeP0PrimeError(f"manifest record missing: {dotted}")
        value = value.get(key)
    if not isinstance(value, Mapping):
        raise AprimeP0PrimeError(f"manifest record missing: {dotted}")
    return value


def validate_building_payload(
    payload: Mapping[str, Any],
    *,
    config: Mapping[str, Any],
    target: Mapping[str, str],
) -> dict[str, Any]:
    contract = config["preprocess_consumer"]
    building_id = target[config["targets"]["id_field"]]
    if payload.get("schema") != contract["building_schema"]:
        raise AprimeP0PrimeError("A-prime building preprocess schema mismatch")
    if payload.get("status") != contract["required_building_status"]:
        raise AprimeP0PrimeError("A-prime building preprocess status mismatch")
    building = payload.get("building") or {}
    if building.get("building_id") != building_id:
        raise AprimeP0PrimeError("A-prime building_id mismatch")
    if int(building.get("aprime_order", -1)) != int(target["aprime_order"]):
        raise AprimeP0PrimeError("A-prime building order mismatch")
    for field in ("tier", "cohort", "target_role"):
        if building.get(field) != target.get(field):
            raise AprimeP0PrimeError(f"A-prime building target field drift: {field}")
    pose = payload.get("pose_binding") or {}
    if pose.get("corrected_images_sha256") != contract["required_pose_sha256"]:
        raise AprimeP0PrimeError("A-prime building pose SHA drift")
    if int(pose.get("transform_application_count", -1)) != int(
        contract["required_transform_application_count"]
    ):
        raise AprimeP0PrimeError("A-prime building pose application drift")
    if int(pose.get("additional_transform_application_count", -1)) != int(
        contract["required_additional_transform_application_count"]
    ):
        raise AprimeP0PrimeError("A-prime building extra transform detected")
    target_binding = payload.get("target_binding") or {}
    if (
        target_binding.get("sha256") != config["targets"]["sha256"]
        or target_binding.get("machine_join_verified") is not True
        or target_binding.get("manual_id_entry") is not False
    ):
        raise AprimeP0PrimeError("A-prime building target binding drift")

    seed = payload.get("seed") or {}
    seed_n = int(seed.get("filtered_points_n", -1))
    if seed_n < 0:
        raise AprimeP0PrimeError("A-prime filtered class-6 count invalid")
    if seed.get("classification_counts") != {"6": seed_n}:
        raise AprimeP0PrimeError("A-prime seed is not exactly class 6")
    if int(seed.get("class2_rows_n", -1)) != 0 or int(seed.get("sfm_rows_n", -1)) != 0:
        raise AprimeP0PrimeError("class-2 or SfM rows entered A-prime seed")
    if bool(seed.get("downsample_applied")) != bool(
        contract["required_downsample_applied"]
    ):
        raise AprimeP0PrimeError("A-prime seed downsample flag drift")
    if not contract["allow_seed_too_small"] and bool(seed.get("seed_too_small")):
        raise AprimeP0PrimeError("seed-too-small tag unexpectedly blocks T3")

    ground = payload.get("ground_readout_only") or {}
    ground_n = int(ground.get("points_n", -1))
    if ground_n <= 0 or ground.get("classification_counts") != {"2": ground_n}:
        raise AprimeP0PrimeError("A-prime readout ground is not nonempty class 2")
    if ground.get("coordinate_rows_unaltered") is not contract[
        "required_ground_coordinate_rows_unaltered"
    ]:
        raise AprimeP0PrimeError("A-prime ground coordinate-row contract drift")
    if ground.get("source_row_order_preserved") is not contract[
        "required_ground_source_row_order_preserved"
    ]:
        raise AprimeP0PrimeError("A-prime ground upstream row-order contract drift")
    if ground.get("row_order_note") != contract["ground_preprocess_row_order_note"]:
        raise AprimeP0PrimeError("A-prime ground upstream row-order note drift")
    if ground.get("downsample_applied") is not False:
        raise AprimeP0PrimeError("A-prime ground was downsampled")
    if ground.get("trainer_path_reference") is not contract[
        "required_ground_trainer_path_reference"
    ]:
        raise AprimeP0PrimeError("A-prime ground trainer isolation drift")
    if ground.get("role") != contract["ground_role"]:
        raise AprimeP0PrimeError("A-prime ground role drift")

    seed_record = _artifact_record(payload, contract["seed_record"])
    ground_record = _artifact_record(payload, contract["ground_record"])
    for label, record in (("seed", seed_record), ("ground", ground_record)):
        if record.get("crs") != contract["required_crs"]:
            raise AprimeP0PrimeError(f"A-prime {label} LAS declared CRS drift")
        if not re.fullmatch(r"[0-9a-f]{64}", str(record.get("sha256", ""))):
            raise AprimeP0PrimeError(f"A-prime {label} LAS SHA malformed")
    publication = payload.get("publication") or {}
    for counter in (
        "learning_runs_started",
        "readout_runs_started",
        "roofer_runs_started",
        "scoring_runs_started",
    ):
        if publication.get(counter) != 0:
            raise AprimeP0PrimeError(
                f"A-prime preprocess publication counter not zero: {counter}"
            )
    return {
        "building_id": building_id,
        "seed_n": seed_n,
        "ground_n": ground_n,
        "seed_too_small": bool(seed.get("seed_too_small")),
        "seed_record": dict(seed_record),
        "ground_record": dict(ground_record),
    }


def inspect_source_las(
    path: Path,
    *,
    expected_class: int,
    expected_count: int,
    config: Mapping[str, Any],
) -> dict[str, Any]:
    try:
        import laspy
        import numpy as np
    except ImportError as exc:
        raise AprimeP0PrimeError("laspy/numpy required in tools image") from exc
    if not path.is_file() or path.is_symlink():
        raise AprimeP0PrimeError(f"source LAS missing/non-regular: {repo_relative(path)}")
    las = laspy.read(path)
    crs = las.header.parse_crs()
    epsg = crs.to_epsg() if crs is not None else None
    dimensions = {
        str(name).lower() for name in las.header.point_format.dimension_names
    }
    classes = np.asarray(las.classification, dtype=np.uint8)
    if len(las.points) != expected_count:
        raise AprimeP0PrimeError(
            f"source class-{expected_class} LAS count drift: {len(las.points)}"
        )
    if len(classes) and np.any(classes != expected_class):
        raise AprimeP0PrimeError(f"source LAS includes non-class-{expected_class} row")
    if str(las.header.version) != config["join_contract"]["las_version"]:
        raise AprimeP0PrimeError("source LAS version drift")
    if int(las.header.point_format.id) != int(config["join_contract"]["point_format"]):
        raise AprimeP0PrimeError("source LAS point-format drift")
    if epsg != 25832:
        raise AprimeP0PrimeError(f"source LAS EPSG drift: {epsg}")
    if config["join_contract"]["require_rgb"]:
        missing = {"red", "green", "blue"} - dimensions
        if missing:
            raise AprimeP0PrimeError(f"source LAS lacks RGB: {sorted(missing)}")
    return {
        "las": las,
        "point_count": len(las.points),
        "epsg": epsg,
        "version": str(las.header.version),
        "point_format": int(las.header.point_format.id),
        "dimensions": sorted(dimensions),
        "class_counts": {str(expected_class): int(len(classes))},
    }


def _semantic_row_digest(lases: Sequence[Any]) -> str:
    """Hash global millimetre XYZ plus every non-XYZ packed LAS attribute."""

    import numpy as np

    digest = hashlib.sha256()
    digest.update(b"jointbuildgs.aprime.p0prime.semantic_las_rows.v1\0")
    xyz_parts = []
    packed_parts = []
    for las in lases:
        xyz = np.column_stack([las.x, las.y, las.z]).astype(np.float64)
        xyz_parts.append(np.rint(xyz * 1000.0).astype("<i8"))
        packed = np.asarray(las.points.array).copy()
        for name in ("X", "Y", "Z"):
            packed[name] = 0
        packed_parts.append(packed)
    xyz_rows = np.concatenate(xyz_parts, axis=0)
    packed_rows = np.concatenate(packed_parts, axis=0)
    digest.update(np.asarray([len(packed_rows)], dtype="<i8").tobytes())
    digest.update(xyz_rows.tobytes(order="C"))
    digest.update(packed_rows.tobytes(order="C"))
    return digest.hexdigest()


def join_source_lases(
    seed_path: Path,
    ground_path: Path,
    output: Path,
    *,
    seed_n: int,
    ground_n: int,
    config: Mapping[str, Any],
) -> dict[str, Any]:
    """Concatenate class-6 then class-2 semantic rows without source mutation."""

    try:
        import laspy
        import numpy as np
        from pyproj import CRS
    except ImportError as exc:
        raise AprimeP0PrimeError("laspy/numpy/pyproj required in tools image") from exc
    if output.exists() or output.is_symlink():
        raise AprimeP0PrimeError(f"refusing to overwrite joined LAS: {repo_relative(output)}")
    seed_info = inspect_source_las(
        seed_path,
        expected_class=int(config["preprocess_consumer"]["required_seed_class"]),
        expected_count=seed_n,
        config=config,
    )
    ground_info = inspect_source_las(
        ground_path,
        expected_class=int(config["preprocess_consumer"]["required_ground_class"]),
        expected_count=ground_n,
        config=config,
    )
    seed_las = seed_info["las"]
    ground_las = ground_info["las"]
    if seed_las.points.array.dtype != ground_las.points.array.dtype:
        raise AprimeP0PrimeError("source LAS packed row dtypes differ")
    expected_xyz = np.concatenate(
        [
            np.column_stack([seed_las.x, seed_las.y, seed_las.z]),
            np.column_stack([ground_las.x, ground_las.y, ground_las.z]),
        ],
        axis=0,
    ).astype(np.float64)
    scales = np.asarray(config["join_contract"]["scale_m"], dtype=np.float64)
    offsets = (
        np.floor(np.min(expected_xyz, axis=0))
        if len(expected_xyz)
        else np.zeros(3, dtype=np.float64)
    )
    source_digest = _semantic_row_digest([seed_las, ground_las])
    point_arrays = []
    for source in (seed_las, ground_las):
        points = laspy.ScaleAwarePointRecord(
            source.points.array.copy(),
            source.header.point_format,
            source.header.scales,
            source.header.offsets,
        )
        points.change_scaling(scales=scales, offsets=offsets)
        point_arrays.append(points.array)
    joined_array = np.concatenate(point_arrays, axis=0)
    header = laspy.LasHeader(
        point_format=int(config["join_contract"]["point_format"]),
        version=config["join_contract"]["las_version"],
    )
    header.scales = scales
    header.offsets = offsets
    header.add_crs(CRS.from_epsg(25832))
    joined = laspy.LasData(header)
    joined.points = laspy.ScaleAwarePointRecord(
        joined_array,
        header.point_format,
        scales,
        offsets,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.{os.getpid()}.tmp")
    joined.write(temporary)
    with temporary.open("rb+") as handle:
        os.fsync(handle.fileno())
    os.replace(temporary, output)
    directory_fd = os.open(output.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)

    observed = laspy.read(output)
    observed_xyz = np.column_stack([observed.x, observed.y, observed.z]).astype(np.float64)
    if observed_xyz.shape != expected_xyz.shape:
        raise AprimeP0PrimeError("joined LAS XYZ shape drift")
    maximum_error = (
        float(np.max(np.abs(observed_xyz - expected_xyz)))
        if len(expected_xyz)
        else 0.0
    )
    tolerance = float(config["join_contract"]["coordinate_equality_tolerance_m"])
    if maximum_error > tolerance:
        raise AprimeP0PrimeError(
            f"joined LAS moved a source coordinate: max_error={maximum_error}"
        )
    expected_classes = np.concatenate(
        [
            np.full(seed_n, 6, dtype=np.uint8),
            np.full(ground_n, 2, dtype=np.uint8),
        ]
    )
    if not np.array_equal(
        np.asarray(observed.classification, dtype=np.uint8), expected_classes
    ):
        raise AprimeP0PrimeError("joined LAS class/order drift")
    observed_digest = _semantic_row_digest([observed])
    if observed_digest != source_digest:
        raise AprimeP0PrimeError("joined LAS semantic-row digest differs from sources")
    return {
        "schema": JOIN_SCHEMA,
        "state": "PASSED",
        "created_utc": now_iso(),
        "method": config["join_contract"]["method"],
        "source_order": ["filtered_class6_seed", "original_class2_ground"],
        "source_ranges": {
            "filtered_class6_seed": [0, seed_n],
            "original_class2_ground": [seed_n, seed_n + ground_n],
        },
        "source_rows_n": {"6": seed_n, "2": ground_n},
        "output_rows_n": seed_n + ground_n,
        "source_semantic_rows_sha256": source_digest,
        "output_semantic_rows_sha256": observed_digest,
        "semantic_row_digest_equal": True,
        "maximum_coordinate_difference_m": maximum_error,
        "coordinate_equality_tolerance_m": tolerance,
        "class_order_verified": True,
        "within_source_row_order_preserved": True,
        "packed_non_xyz_attributes_preserved": True,
        "geometry_changed": False,
        "classification_changed": False,
        "rows_removed": 0,
        "rows_added": 0,
        "downsample_applied": False,
        "crs": "EPSG:25832",
        "vertical_datum": config["preprocess_consumer"]["required_vertical_datum"],
        "las_version": str(observed.header.version),
        "point_format": int(observed.header.point_format.id),
        "scale_m": observed.header.scales.astype(float).tolist(),
        "offset_m": observed.header.offsets.astype(float).tolist(),
        "output": {
            "path": repo_relative(output),
            "sha256": sha256_file(output),
            "size": output.stat().st_size,
        },
        "learning_runs_started": 0,
        "new_inference_runs": 0,
        "interpretation_or_verdict": None,
    }


def load_execution_engine(config: Mapping[str, Any]) -> Any:
    record = config["canonical_helpers"]["p0prime_execution_engine"]
    path = repo_path(record["path"])
    if sha256_file(path) != record["sha256"]:
        raise AprimeP0PrimeError("locked P0-prime execution-engine SHA drift")
    spec = importlib.util.spec_from_file_location("fusion_w1_aprime_p0prime_engine", path)
    if spec is None or spec.loader is None:
        raise AprimeP0PrimeError("cannot load locked P0-prime execution engine")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def compatibility_config(config: Mapping[str, Any]) -> dict[str, Any]:
    """Present the old engine only the conventions it is authorized to reuse."""

    result = {
        "schema": "jointbuildgs.fusion_w1.seed_p0prime.lock.v1",
        "task_id": config["task_id"],
        "branch": config["branch"],
        "implementation_files": list(config["implementation_files"]),
        "targets_csv": {
            "path": config["targets"]["path"],
            "sha256": config["targets"]["sha256"],
            "id_field": config["targets"]["id_field"],
            "order_field": config["targets"]["order_field"],
            "expected_population": config["targets"]["expected_population"],
        },
        "preprocess_consumer": {
            "classification_stage": config["join_contract"]["method"],
            "classification_mutates_geometry_or_classes": False,
        },
        "footprint": copy.deepcopy(config["footprint"]),
        "reference": copy.deepcopy(config["reference"]),
        "canonical_helpers": {
            key: copy.deepcopy(config["canonical_helpers"][key])
            for key in ("roofer_status", "roof_metrics", "coverage_and_xy")
        },
        "p0_refl_baseline": copy.deepcopy(config["p0_refl_baseline"]),
        "roofer": copy.deepcopy(config["roofer"]),
        "tools": copy.deepcopy(config["tools"]),
        "resource_lock": copy.deepcopy(config["resource_lock"]),
        "score_contract": copy.deepcopy(config["score_contract"]),
        "outputs": copy.deepcopy(config["outputs"]),
        "publication": copy.deepcopy(config["publication"]),
        "input_schema_assumptions": list(config["input_schema_assumptions"]),
    }
    return result


def configured_engine(config: Mapping[str, Any]) -> tuple[Any, dict[str, Any]]:
    engine = load_execution_engine(config)
    compat = compatibility_config(config)
    engine.REPO = REPO
    engine.SCORE_SCHEMA = SCORE_SCHEMA
    engine.BUILDING_RECEIPT_SCHEMA = BUILDING_RECEIPT_SCHEMA
    engine.target_rows = lambda _unused: target_rows(config)
    engine.target_row = lambda _unused, bid: target_row(config, bid)
    engine.verify_static_inputs = lambda _unused: verify_static_inputs(config)
    engine.verify_git_runtime = lambda _unused: verify_git_runtime(config)
    return engine, compat


def validate_consumed_building(
    config: Mapping[str, Any], building_id: str, *, deep: bool
) -> dict[str, Any]:
    target = target_row(config, building_id)
    resolution = preprocess_resolution(config, building_id)
    payload = load_json(resolution["manifest_path"])
    valid = validate_building_payload(payload, config=config, target=target)
    seed_path = resolve_declared_path(
        valid["seed_record"].get("path"), declaring_file=resolution["manifest_path"]
    )
    ground_path = resolve_declared_path(
        valid["ground_record"].get("path"), declaring_file=resolution["manifest_path"]
    )
    for label, path, record in (
        ("seed", seed_path, valid["seed_record"]),
        ("ground", ground_path, valid["ground_record"]),
    ):
        if not _inside(path, resolution["cache_dir"]):
            raise AprimeP0PrimeError(f"A-prime {label} LAS escapes cache")
        _forbid_old_input(config, path)
        if sha256_file(path) != record["sha256"]:
            raise AprimeP0PrimeError(f"A-prime {label} LAS SHA drift")
        artifact = payload.get("artifact_sha256") or {}
        if artifact.get(repo_relative(path)) != record["sha256"]:
            raise AprimeP0PrimeError(f"A-prime {label} LAS artifact binding drift")
    seed_info = ground_info = None
    if deep:
        seed_info = inspect_source_las(
            seed_path,
            expected_class=6,
            expected_count=valid["seed_n"],
            config=config,
        )
        ground_info = inspect_source_las(
            ground_path,
            expected_class=2,
            expected_count=valid["ground_n"],
            config=config,
        )
    return {
        "target": target,
        "resolution": resolution,
        "payload": payload,
        **valid,
        "seed_path": seed_path,
        "ground_path": ground_path,
        "seed_info": seed_info,
        "ground_info": ground_info,
    }


def check(
    config: Mapping[str, Any], *, building_id: str | None, deep: bool
) -> dict[str, Any]:
    static = verify_static_inputs(config)
    selected = [target_row(config, building_id)] if building_id else target_rows(config)
    ready = []
    missing = []
    invalid = []
    for target in selected:
        bid = target["building_id"]
        try:
            record = validate_consumed_building(config, bid, deep=deep)
            ready.append(
                {
                    "building_id": bid,
                    "aprime_order": int(target["aprime_order"]),
                    "preprocess_manifest": repo_relative(record["resolution"]["manifest_path"]),
                    "preprocess_manifest_sha256": record["resolution"]["manifest_sha256"],
                    "filtered_class6_las": repo_relative(record["seed_path"]),
                    "filtered_class6_las_sha256": sha256_file(record["seed_path"]),
                    "filtered_class6_rows_n": record["seed_n"],
                    "seed_too_small": record["seed_too_small"],
                    "original_class2_ground_las": repo_relative(record["ground_path"]),
                    "original_class2_ground_las_sha256": sha256_file(record["ground_path"]),
                    "original_class2_ground_rows_n": record["ground_n"],
                }
            )
        except FileNotFoundError:
            missing.append(bid)
        except AprimeP0PrimeError as exc:
            if "missing/non-regular JSON" in str(exc):
                missing.append(bid)
            else:
                invalid.append({"building_id": bid, "error": str(exc)})
    return {
        "schema": CHECK_SCHEMA,
        "created_utc": now_iso(),
        "static_input_sha256": static,
        "selected_count": len(selected),
        "ready_count": len(ready),
        "missing_count": len(missing),
        "invalid_count": len(invalid),
        "deep_las_validation": deep,
        "ready": ready,
        "missing": missing,
        "invalid": invalid,
        "learning_runs_started": 0,
        "new_inference_runs": 0,
        "interpretation_or_verdict": None,
    }


def prepare_one(config: Mapping[str, Any], building_id: str) -> dict[str, Any]:
    verify_static_inputs(config)
    engine, compat = configured_engine(config)
    engine.refuse_after_final_manifest(compat)
    record = validate_consumed_building(config, building_id, deep=True)
    target = record["target"]
    job = engine.building_dir(compat, building_id)
    job.mkdir(parents=True, exist_ok=True)
    engine.exclusive_json(
        job / "start.json",
        {
            "schema": BUILDING_RECEIPT_SCHEMA,
            "state": "STARTED",
            "stage": "join_class6_class2",
            "created_utc": now_iso(),
            "building_id": building_id,
            "aprime_order": int(target["aprime_order"]),
            "learning_runs_started": 0,
            "new_inference_runs": 0,
            "interpretation_or_verdict": None,
        },
    )
    joined_path = (
        job / "assembly_input" / config["join_contract"]["output_filename"]
    )
    join_receipt = join_source_lases(
        record["seed_path"],
        record["ground_path"],
        joined_path,
        seed_n=record["seed_n"],
        ground_n=record["ground_n"],
        config=config,
    )
    join_receipt.update(
        {
            "building_id": building_id,
            "aprime_order": int(target["aprime_order"]),
            "preprocess_manifest": {
                "path": repo_relative(record["resolution"]["manifest_path"]),
                "sha256": record["resolution"]["manifest_sha256"],
                "schema": record["payload"]["schema"],
                "status": record["payload"]["status"],
            },
            "filtered_class6_source": {
                "path": repo_relative(record["seed_path"]),
                "sha256": sha256_file(record["seed_path"]),
                "rows_n": record["seed_n"],
                "role": config["preprocess_consumer"]["seed_role"],
            },
            "original_class2_ground_source": {
                "path": repo_relative(record["ground_path"]),
                "sha256": sha256_file(record["ground_path"]),
                "rows_n": record["ground_n"],
                "role": config["preprocess_consumer"]["ground_role"],
                "source": config["preprocess_consumer"]["ground_source"],
                "trainer_path_reference": False,
                "coordinate_rows_unaltered_by_preprocess": True,
                "source_row_order_preserved_by_preprocess": False,
                "preprocess_row_order_note": config["preprocess_consumer"][
                    "ground_preprocess_row_order_note"
                ],
                "published_las_row_order_preserved_by_T3": True,
            },
            "old_arm_a_numeric_inputs_read": [],
        }
    )
    join_receipt_path = job / "join_receipt.json"
    engine.exclusive_json(join_receipt_path, join_receipt)
    footprint = engine.write_footprint_subset(
        compat, building_id, job / "footprint.gpkg"
    )
    classification = {
        "schema": "jointbuildgs.fusion_w1.seed_p0prime.classification_receipt.v1",
        "state": "PASSED",
        "created_utc": now_iso(),
        "building_id": building_id,
        "processing_order": int(target["aprime_order"]),
        "tier": target["tier"],
        "cohort": target["cohort"],
        "target_role": target["target_role"],
        "method": config["join_contract"]["method"],
        "mutation": {
            "geometry_changed": False,
            "classification_changed": False,
            "vertical_datum_changed": False,
            "source_rows_reordered_within_class": False,
            "rows_removed": 0,
            "rows_added": 0,
            "downsample_runs_started": 0,
            "smrf_runs_started": 0,
            "overlay_runs_started": 0,
        },
        "preprocess_manifest": {
            "path": repo_relative(record["resolution"]["manifest_path"]),
            "sha256": record["resolution"]["manifest_sha256"],
            "schema": record["payload"]["schema"],
            "status": record["payload"]["status"],
        },
        "preprocess_resolver": {
            "stable_run_manifest": {
                "path": repo_relative(record["resolution"]["stable_path"]),
                "sha256": record["resolution"]["stable_sha256"],
            },
            "cache_namespace": record["resolution"]["cache_namespace"],
            "preprocess_index": {
                "path": repo_relative(record["resolution"]["index_path"]),
                "sha256": record["resolution"]["index_sha256"],
            },
        },
        "classified_seed_las": {
            "path": repo_relative(joined_path),
            "sha256": sha256_file(joined_path),
            "point_count": record["seed_n"] + record["ground_n"],
            "class_counts": {"2": record["ground_n"], "6": record["seed_n"]},
            "epsg": 25832,
            "vertical_datum": config["preprocess_consumer"]["required_vertical_datum"],
            "las_version": config["join_contract"]["las_version"],
            "point_format": config["join_contract"]["point_format"],
            "rgb_dimensions_present": True,
        },
        "join_receipt": {
            "path": repo_relative(join_receipt_path),
            "sha256": sha256_file(join_receipt_path),
            "semantic_row_digest_equal": True,
        },
        "footprint": footprint,
        "footprint_used_for_classification": False,
        "footprint_role_for_next_stage": "Roofer GroundSurface XY input",
        "P0prime_Aprime_reference": True,
        "learning_runs_started": 0,
        "new_inference_runs": 0,
        "interpretation_or_verdict": None,
    }
    engine.exclusive_json(job / "classification_receipt.json", classification)
    engine.update_progress(compat, f"join_complete:{building_id}")
    return classification


def authorize_roofer(config: Mapping[str, Any], building_id: str) -> dict[str, Any]:
    engine, compat = configured_engine(config)
    return engine.authorize_roofer(compat, building_id)


def roofer_paths(config: Mapping[str, Any], building_id: str) -> tuple[str, str, str]:
    engine, compat = configured_engine(config)
    return engine.roofer_paths(compat, building_id)


def accept_roofer(
    config: Mapping[str, Any], building_id: str, *, wall_seconds: float
) -> dict[str, Any]:
    engine, compat = configured_engine(config)
    return engine.accept_roofer(compat, building_id, wall_seconds=wall_seconds)


def score_one(config: Mapping[str, Any], building_id: str) -> dict[str, Any]:
    engine, compat = configured_engine(config)
    complete = engine.score_one(compat, building_id)
    job = engine.building_dir(compat, building_id)
    score_receipt_path = job / "score_receipt.json"
    score_receipt = load_json(score_receipt_path)
    row = score_receipt.get("row") or {}
    if row.get("schema") != SCORE_SCHEMA or row.get("building_id") != building_id:
        raise AprimeP0PrimeError("T3 score receipt schema/building drift")
    join_receipt_path = job / "join_receipt.json"
    reference = {
        "schema": REFERENCE_SCHEMA,
        "state": "MEASURED",
        "created_utc": now_iso(),
        "building_id": building_id,
        "baseline_role": config["score_contract"]["baseline_role"],
        "rms_role": config["score_contract"]["rms_role"],
        "learning_runs_started": 0,
        "new_inference_runs": 0,
        "join_receipt": {
            "path": repo_relative(join_receipt_path),
            "sha256": sha256_file(join_receipt_path),
        },
        "score_receipt": {
            "path": repo_relative(score_receipt_path),
            "sha256": sha256_file(score_receipt_path),
        },
        "measurements": {
            key: row.get(key)
            for key in (
                "assembly_lod2_success",
                "assembly_reason",
                "has_lod22_geometry",
                "lod1_fallback",
                "val3dity_valid",
                "plane_precision",
                "plane_recall",
                "plane_f1",
                "roof_rms_m",
                "roof_hausdorff_m",
                "roof_completeness",
                "face_count_ratio",
            )
        },
        "reference_role": config["reference"]["role"],
        "reference_opened_only_after_roofer_output_frozen": True,
        "old_arm_a_numeric_inputs_read": [],
        "interpretation_or_verdict": None,
    }
    reference_path = job / "t3_reference_receipt.json"
    engine.exclusive_json(reference_path, reference)
    return {
        "complete": complete,
        "T3_reference_receipt": {
            "path": repo_relative(reference_path),
            "sha256": sha256_file(reference_path),
        },
    }


def record_failure(
    config: Mapping[str, Any],
    *,
    building_id: str | None,
    stage: str,
    message: str,
    detail: str = "",
) -> dict[str, Any]:
    engine, compat = configured_engine(config)
    payload = {
        "schema": FAILURE_SCHEMA,
        "created_utc": now_iso(),
        "building_id": building_id,
        "stage": stage,
        "message": message,
        "detail": detail[-12000:],
        "learning_runs_started": 0,
        "new_inference_runs": 0,
        "interpretation_or_verdict": None,
    }
    failure_path = repo_path(config["outputs"]["failures_jsonl"])
    engine.append_jsonl(failure_path, payload)
    if building_id:
        job = engine.building_dir(compat, building_id)
        job.mkdir(parents=True, exist_ok=True)
        token = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        engine.exclusive_json(job / f"failure_{token}.json", payload)
    engine.update_progress(compat, f"failure:{stage}")
    return payload


def list_ready(config: Mapping[str, Any]) -> list[str]:
    ready = []
    for target in target_rows(config):
        try:
            validate_consumed_building(config, target["building_id"], deep=False)
            ready.append(target["building_id"])
        except (AprimeP0PrimeError, FileNotFoundError):
            continue
    return ready


def list_pending(config: Mapping[str, Any]) -> list[str]:
    engine, compat = configured_engine(config)
    return [
        building_id
        for building_id in list_ready(config)
        if not (engine.building_dir(compat, building_id) / "start.json").exists()
    ]


def finalize(config: Mapping[str, Any], *, require_all: bool) -> dict[str, Any]:
    engine, compat = configured_engine(config)
    engine.refuse_after_final_manifest(compat)
    scores_path = repo_path(config["outputs"]["scores_csv"])
    scores = read_csv(scores_path) if scores_path.is_file() else []
    targets = target_rows(config)
    target_ids = {row["building_id"] for row in targets}
    score_ids = [row["building_id"] for row in scores]
    if len(score_ids) != len(set(score_ids)) or not set(score_ids).issubset(target_ids):
        raise AprimeP0PrimeError("T3 score population contains duplicate/non-target ID")
    if require_all and len(scores) != len(targets):
        raise AprimeP0PrimeError(
            f"require-all requested but T3 complete={len(scores)}/{len(targets)}"
        )
    records = []
    for row in scores:
        job = engine.building_dir(compat, row["building_id"])
        complete_path = job / "complete.json"
        complete = load_json(complete_path)
        if complete.get("schema") != BUILDING_RECEIPT_SCHEMA or complete.get("state") != "COMPLETE":
            raise AprimeP0PrimeError("T3 building completion receipt drift")
        reference_path = job / "t3_reference_receipt.json"
        reference = load_json(reference_path)
        if reference.get("schema") != REFERENCE_SCHEMA or reference.get("state") != "MEASURED":
            raise AprimeP0PrimeError("T3 reference receipt drift")
        records.append(
            {
                "building_id": row["building_id"],
                "aprime_order": int(row["processing_order"]),
                "complete_receipt": repo_relative(complete_path),
                "complete_receipt_sha256": sha256_file(complete_path),
                "reference_receipt": repo_relative(reference_path),
                "reference_receipt_sha256": sha256_file(reference_path),
            }
        )
    engine.update_progress(compat, "finalize_pre_manifest")
    progress = repo_path(config["outputs"]["progress"])
    final = {
        "schema": FINAL_SCHEMA,
        "state": "COMPLETE" if len(scores) == len(targets) else "PARTIAL",
        "created_utc": now_iso(),
        "task_id": config["task_id"],
        "run_id": config["run_id"],
        "baseline_role": config["score_contract"]["baseline_role"],
        "population": {
            "target_count": len(targets),
            "completed_count": len(scores),
            "assembly_lod2_success_count": sum(
                str(row.get("assembly_lod2_success", "")).lower() in {"true", "1"}
                for row in scores
            ),
            "val3dity_valid_count": sum(
                str(row.get("val3dity_valid", "")).lower() in {"true", "1"}
                for row in scores
            ),
            "assembly_and_val3dity_are_independent": True,
        },
        "scores_csv": (
            {
                "path": repo_relative(scores_path),
                "sha256": sha256_file(scores_path),
                "row_count": len(scores),
            }
            if scores_path.is_file()
            else None
        ),
        "progress": {
            "path": repo_relative(progress),
            "sha256": sha256_file(progress),
        },
        "building_records": records,
        "roofer": config["roofer"],
        "resource_lock": config["resource_lock"],
        "learning_runs_started": 0,
        "new_inference_runs": 0,
        "partial_buildings_reviewable": True,
        "manifest_written_last": True,
        "interpretation_or_verdict": None,
    }
    engine.exclusive_json(repo_path(config["outputs"]["final_manifest"]), final)
    return final


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("--config", default=str(DEFAULT_CONFIG))
    commands = result.add_subparsers(dest="command", required=True)
    check_parser = commands.add_parser("check")
    check_parser.add_argument("--building-id")
    check_parser.add_argument("--deep", action="store_true")
    commands.add_parser("list-ready")
    commands.add_parser("list-pending")
    for name in ("prepare-one", "authorize-roofer", "score-one"):
        sub = commands.add_parser(name)
        sub.add_argument("--building-id", required=True)
    paths = commands.add_parser("roofer-paths")
    paths.add_argument("--building-id", required=True)
    accept = commands.add_parser("accept-roofer")
    accept.add_argument("--building-id", required=True)
    accept.add_argument("--wall-seconds", required=True, type=float)
    failure = commands.add_parser("record-failure")
    failure.add_argument("--building-id")
    failure.add_argument("--stage", required=True)
    failure.add_argument("--message", required=True)
    failure.add_argument("--detail", default="")
    final = commands.add_parser("finalize")
    final.add_argument("--require-all", action="store_true")
    return result


def print_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), flush=True)


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    raw_config = Path(args.config)
    config_path = repo_path(raw_config) if not raw_config.is_absolute() else raw_config
    config = load_config(config_path)
    command = args.command
    building_id = getattr(args, "building_id", None)
    try:
        if command == "check":
            print_json(check(config, building_id=building_id, deep=bool(args.deep)))
        elif command == "list-ready":
            for value in list_ready(config):
                print(value)
        elif command == "list-pending":
            for value in list_pending(config):
                print(value)
        elif command == "prepare-one":
            verify_git_runtime(config)
            print_json(prepare_one(config, building_id))
        elif command == "authorize-roofer":
            verify_git_runtime(config)
            print_json(authorize_roofer(config, building_id))
        elif command == "roofer-paths":
            for value in roofer_paths(config, building_id):
                print(value)
        elif command == "accept-roofer":
            verify_git_runtime(config)
            print_json(
                accept_roofer(
                    config, building_id, wall_seconds=float(args.wall_seconds)
                )
            )
        elif command == "score-one":
            verify_git_runtime(config)
            print_json(score_one(config, building_id))
        elif command == "record-failure":
            verify_git_runtime(config)
            print_json(
                record_failure(
                    config,
                    building_id=building_id,
                    stage=args.stage,
                    message=args.message,
                    detail=args.detail,
                )
            )
        elif command == "finalize":
            verify_git_runtime(config)
            print_json(finalize(config, require_all=bool(args.require_all)))
        else:  # pragma: no cover
            raise AprimeP0PrimeError(f"unknown command: {command}")
        return 0
    except Exception as exc:
        if command in {
            "prepare-one",
            "authorize-roofer",
            "accept-roofer",
            "score-one",
        }:
            try:
                record_failure(
                    config,
                    building_id=building_id,
                    stage=command,
                    message=str(exc),
                    detail=traceback.format_exc(),
                )
            except Exception:
                pass
        raise


if __name__ == "__main__":
    raise SystemExit(main())
