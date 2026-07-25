#!/usr/bin/env python3
"""Fusion W1 P0-prime: validate seed classes, assemble, and score.

This method consumes the actual per-building ALS seed published by the W1
preprocessor.  The classification stage is deliberately a validating
passthrough: it does not rerun SMRF, overlay a footprint, move a point, change
a class, or convert the vertical datum.  Roofer and scoring run one building
at a time.  LoD2 assembly and val3dity are reported as independent fields.

The shell wrapper owns Docker/cgroup execution.  This module owns contracts,
receipts, canonical helper calls, incremental CSV publication, and the final
manifest-last rule.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import fcntl
import hashlib
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import traceback
from typing import Any, Iterable, Mapping, Sequence


REPO = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = (
    REPO
    / "phases/p2-gsjso/configs/fusion_w1_seed_p0prime_20260725.json"
)
SCHEMA = "jointbuildgs.fusion_w1.seed_p0prime.lock.v1"
SCORE_SCHEMA = "jointbuildgs.fusion_w1.seed_p0prime.score.v1"
BUILDING_RECEIPT_SCHEMA = (
    "jointbuildgs.fusion_w1.seed_p0prime.building_receipt.v1"
)


class P0PrimeError(RuntimeError):
    """Fail-closed contract or execution error."""


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def sha256_file(path: Path, block_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(block_size), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


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
        raise P0PrimeError(f"absolute repository path is forbidden: {raw}")
    candidate = (REPO / raw).resolve()
    try:
        candidate.relative_to(REPO.resolve())
    except ValueError as exc:
        raise P0PrimeError(f"path escapes repository: {raw}") from exc
    return candidate


def repo_relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO.resolve()))
    except ValueError as exc:
        raise P0PrimeError(f"path is outside repository: {path}") from exc


def resolve_declared_path(value: Any, *, declaring_file: Path) -> Path:
    if not isinstance(value, str) or not value:
        raise P0PrimeError(f"missing declared path in {repo_relative(declaring_file)}")
    raw = Path(value)
    if raw.is_absolute():
        raise P0PrimeError(f"absolute declared path is forbidden: {value}")
    repo_candidate = (REPO / raw).resolve()
    local_candidate = (declaring_file.parent / raw).resolve()
    candidates = []
    for candidate in (repo_candidate, local_candidate):
        try:
            candidate.relative_to(REPO.resolve())
        except ValueError:
            continue
        if candidate not in candidates:
            candidates.append(candidate)
    existing = [candidate for candidate in candidates if candidate.exists()]
    if len(existing) == 1:
        return existing[0]
    if len(existing) > 1 and existing[0] != existing[1]:
        raise P0PrimeError(
            f"ambiguous declared path {value!r} in {repo_relative(declaring_file)}"
        )
    if candidates:
        return candidates[0]
    raise P0PrimeError(f"declared path escapes repository: {value}")


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise P0PrimeError(f"missing/non-regular JSON: {repo_relative(path)}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise P0PrimeError(f"JSON root is not an object: {repo_relative(path)}")
    return value


def atomic_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("xb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    atomic_bytes(path, canonical_json(dict(payload)))


def exclusive_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def append_jsonl(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = canonical_json(dict(payload))
    with path.open("ab") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file() or path.is_symlink():
        raise P0PrimeError(f"missing/non-regular CSV: {repo_relative(path)}")
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise P0PrimeError(f"CSV has no header: {repo_relative(path)}")
        return [dict(row) for row in reader]


def truth(value: Any) -> bool:
    return value is True or str(value).strip().lower() in {"true", "1"}


def falsehood(value: Any) -> bool:
    return value is False or str(value).strip().lower() in {"false", "0"}


def csv_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, float):
        return "" if not math.isfinite(value) else f"{value:.9f}"
    return value


def atomic_csv(
    path: Path,
    rows: Sequence[Mapping[str, Any]],
    fields: Sequence[str],
) -> None:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(
        output,
        fieldnames=list(fields),
        extrasaction="ignore",
        lineterminator="\n",
    )
    writer.writeheader()
    for row in rows:
        writer.writerow({field: csv_value(row.get(field)) for field in fields})
    atomic_bytes(path, output.getvalue().encode("utf-8"))


def load_config(path: Path) -> dict[str, Any]:
    config = load_json(path)
    if config.get("schema") != SCHEMA:
        raise P0PrimeError(f"unexpected config schema: {config.get('schema')}")
    if config["score_contract"].get("learning_runs_started") != 0:
        raise P0PrimeError("learning counter lock is not zero")
    if config["score_contract"].get("new_inference_runs") != 0:
        raise P0PrimeError("inference counter lock is not zero")
    if config["roofer"].get("outer_parallelism") != 1:
        raise P0PrimeError("outer Roofer parallelism must be one")
    if config["resource_lock"].get("serial_buildings") is not True:
        raise P0PrimeError("serial building lock is absent")
    return config


def output_paths(config: Mapping[str, Any]) -> dict[str, Path]:
    return {
        key: repo_path(value)
        for key, value in config["outputs"].items()
        if key not in {"building_dir_template"}
    }


def building_dir(config: Mapping[str, Any], building_id: str) -> Path:
    return repo_path(
        config["outputs"]["building_dir_template"].format(
            building_id=building_id
        )
    )


def target_rows(config: Mapping[str, Any]) -> list[dict[str, str]]:
    contract = config["targets_csv"]
    path = repo_path(contract["path"])
    if sha256_file(path) != contract["sha256"]:
        raise P0PrimeError("w1_targets.csv SHA256 drift")
    rows = read_csv(path)
    if len(rows) != int(contract["expected_population"]):
        raise P0PrimeError(f"target population drift: {len(rows)}")
    id_field = contract["id_field"]
    order_field = contract["order_field"]
    ids = [row[id_field] for row in rows]
    orders = [int(row[order_field]) for row in rows]
    if len(ids) != len(set(ids)):
        raise P0PrimeError("duplicate W1 target building ID")
    if sorted(orders) != list(range(1, len(rows) + 1)):
        raise P0PrimeError("W1 processing_order is not a 1..N permutation")
    return sorted(rows, key=lambda row: int(row[order_field]))


def target_row(
    config: Mapping[str, Any], building_id: str
) -> dict[str, str]:
    matches = [
        row
        for row in target_rows(config)
        if row[config["targets_csv"]["id_field"]] == building_id
    ]
    if len(matches) != 1:
        raise P0PrimeError(f"building is not a unique W1 target: {building_id}")
    return matches[0]


def verify_static_inputs(config: Mapping[str, Any]) -> dict[str, str]:
    locks: list[tuple[str, str]] = [
        (
            config["targets_csv"]["path"],
            config["targets_csv"]["sha256"],
        ),
        (
            config["footprint"]["path"],
            config["footprint"]["sha256"],
        ),
        (
            config["p0_refl_baseline"]["path"],
            config["p0_refl_baseline"]["sha256"],
        ),
    ]
    for helper in config["canonical_helpers"].values():
        locks.append((helper["path"], helper["sha256"]))
    locks.extend(config["reference"]["locked_files"].items())
    observed: dict[str, str] = {}
    for value, expected in locks:
        path = repo_path(value)
        if not path.is_file() or path.is_symlink():
            raise P0PrimeError(f"locked input missing/non-regular: {value}")
        actual = sha256_file(path)
        if actual != expected:
            raise P0PrimeError(f"locked SHA drift: {value}")
        observed[value] = actual
    baseline = config["p0_refl_baseline"]
    baseline_rows = [
        row
        for row in read_csv(repo_path(baseline["path"]))
        if row.get("model_id") == baseline["model_id"]
        and row.get("role") == baseline["role"]
    ]
    baseline_ids = [row.get("building_id", "") for row in baseline_rows]
    if (
        len(baseline_rows) != int(baseline["expected_population"])
        or len(baseline_ids) != len(set(baseline_ids))
        or any(not building_id for building_id in baseline_ids)
    ):
        raise P0PrimeError("P0 Ref-L baseline population contract drift")
    lod2_count = sum(truth(row.get("has_lod22")) for row in baseline_rows)
    if lod2_count != int(baseline["expected_lod2_count"]):
        raise P0PrimeError("P0 Ref-L baseline LoD2 count drift")
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
        raise P0PrimeError(
            process.stderr.strip()
            or process.stdout.strip()
            or "git command failed"
        )
    return process


def verify_git_runtime(config: Mapping[str, Any]) -> dict[str, Any]:
    branch = git("branch", "--show-current").stdout.strip()
    head = git("rev-parse", "HEAD").stdout.strip()
    if branch != config["branch"]:
        raise P0PrimeError(f"branch mismatch: {branch}")
    records = []
    for value in config.get("implementation_files", []):
        tracked = bool(git("ls-files", "--", value).stdout.strip())
        at_head = (
            git("cat-file", "-e", f"{head}:{value}", check=False).returncode
            == 0
        )
        worktree_blob = git("hash-object", "--", value).stdout.strip()
        head_blob = git("rev-parse", f"{head}:{value}", check=False)
        unchanged = head_blob.returncode == 0 and worktree_blob == head_blob.stdout.strip()
        if not tracked or not at_head or not unchanged:
            raise P0PrimeError(f"implementation is not committed at HEAD: {value}")
        records.append(
            {
                "path": value,
                "tracked_at_head": True,
                "worktree_matches_head": True,
                "git_blob": worktree_blob,
            }
        )
    return {"branch": branch, "head": head, "implementation_files": records}


def preprocess_resolution(
    config: Mapping[str, Any], building_id: str
) -> dict[str, Any]:
    """Resolve one building only through the stable preprocess run manifest."""

    contract = config["preprocess_consumer"]
    stable_path = repo_path(contract["run_manifest"])
    stable = load_json(stable_path)
    if stable.get("schema") != contract["run_schema"]:
        raise P0PrimeError("stable preprocess run schema mismatch")
    if stable.get("status") not in set(contract["allowed_run_status"]):
        raise P0PrimeError("stable preprocess run status is not consumable")
    cache = stable.get("cache_binding")
    if not isinstance(cache, Mapping):
        raise P0PrimeError("stable preprocess manifest lacks cache_binding")
    namespace = cache.get("namespace")
    cache_dir_value = cache.get("cache_dir")
    if not isinstance(namespace, str) or not namespace:
        raise P0PrimeError("preprocess cache namespace is missing")
    cache_dir = resolve_declared_path(
        cache_dir_value,
        declaring_file=stable_path,
    )
    if cache_dir.name != namespace or not cache_dir.is_dir():
        raise P0PrimeError("preprocess cache_dir/namespace mismatch")

    def bound_file(name: str) -> tuple[Path, dict[str, Any]]:
        record = cache.get(name)
        if not isinstance(record, Mapping):
            raise P0PrimeError(f"cache_binding.{name} is missing")
        path = resolve_declared_path(record.get("path"), declaring_file=stable_path)
        if not path.is_file() or path.is_symlink():
            raise P0PrimeError(f"cache-bound file missing/non-regular: {name}")
        if sha256_file(path) != record.get("sha256"):
            raise P0PrimeError(f"cache-bound file SHA drift: {name}")
        try:
            path.resolve().relative_to(cache_dir.resolve())
        except ValueError as exc:
            raise P0PrimeError(f"cache-bound file escapes cache_dir: {name}") from exc
        return path, dict(record)

    cache_run_path, cache_run_record = bound_file("cache_run_manifest")
    index_path, index_record = bound_file("preprocess_index")
    cache_run = load_json(cache_run_path)
    if cache_run.get("schema") != contract["run_schema"]:
        raise P0PrimeError("cache preprocess run schema mismatch")
    required_columns = set(contract["index_required_columns"])
    with index_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not required_columns.issubset(reader.fieldnames):
            raise P0PrimeError("preprocess index columns do not satisfy contract")
        index_rows = [dict(row) for row in reader]
    matches = [row for row in index_rows if row["building_id"] == building_id]
    if len(matches) != 1:
        raise P0PrimeError(
            f"preprocess index building row is not unique: {building_id}"
        )
    index_row = matches[0]
    if index_row["status"] != contract["required_status"]:
        raise P0PrimeError("preprocess index building status is not PASSED")
    building_path = resolve_declared_path(
        index_row["building_manifest_path"],
        declaring_file=index_path,
    )
    try:
        building_path.resolve().relative_to(cache_dir.resolve())
    except ValueError as exc:
        raise P0PrimeError("building manifest escapes preprocess cache_dir") from exc
    if not building_path.is_file() or building_path.is_symlink():
        raise P0PrimeError("resolved preprocess building manifest is missing")
    building_sha = sha256_file(building_path)
    if building_sha != index_row["building_manifest_sha256"]:
        raise P0PrimeError("preprocess index/building manifest SHA mismatch")

    stable_buildings = stable.get("buildings")
    if isinstance(stable_buildings, list):
        stable_matches = [
            row
            for row in stable_buildings
            if isinstance(row, Mapping)
            and row.get("building_id") == building_id
        ]
        if len(stable_matches) != 1:
            raise P0PrimeError("stable manifest building record is not unique")
        stable_record = stable_matches[0]
        stable_building_path = resolve_declared_path(
            stable_record.get("building_manifest_path"),
            declaring_file=stable_path,
        )
        if stable_building_path != building_path:
            raise P0PrimeError("stable/index building manifest path mismatch")
        if stable_record.get("building_manifest_sha256") != building_sha:
            raise P0PrimeError("stable/index building manifest SHA mismatch")

    return {
        "stable_run_manifest_path": stable_path,
        "stable_run_manifest_sha256": sha256_file(stable_path),
        "stable_run_manifest": stable,
        "cache_namespace": namespace,
        "cache_dir": cache_dir,
        "cache_run_manifest_path": cache_run_path,
        "cache_run_manifest_sha256": cache_run_record["sha256"],
        "preprocess_index_path": index_path,
        "preprocess_index_sha256": index_record["sha256"],
        "index_row": index_row,
        "building_manifest_path": building_path,
        "building_manifest_sha256": building_sha,
    }


def preprocess_manifest_path(
    config: Mapping[str, Any], building_id: str
) -> Path:
    return preprocess_resolution(config, building_id)["building_manifest_path"]


def validate_preprocess_payload(
    payload: Mapping[str, Any],
    *,
    expected_building_id: str,
    expected_target: Mapping[str, str],
    config: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate schema fields without opening LAS; useful to both run and test."""

    contract = config["preprocess_consumer"]
    if payload.get("schema") != contract["schema"]:
        raise P0PrimeError("preprocess building schema mismatch")
    if payload.get("status") != contract["required_status"]:
        raise P0PrimeError("preprocess building status is not PASSED")
    building = payload.get("building")
    if not isinstance(building, Mapping):
        raise P0PrimeError("preprocess manifest lacks building object")
    if building.get("building_id") != expected_building_id:
        raise P0PrimeError("preprocess building_id mismatch")
    expected_order = int(expected_target[config["targets_csv"]["order_field"]])
    if int(building.get("processing_order", -1)) != expected_order:
        raise P0PrimeError("preprocess processing_order mismatch")
    if building.get("tier") != expected_target.get("tier"):
        raise P0PrimeError("preprocess tier mismatch")
    if building.get("cohort") != expected_target.get("cohort"):
        raise P0PrimeError("preprocess cohort mismatch")

    seed = payload.get("seed")
    if not isinstance(seed, Mapping):
        raise P0PrimeError("preprocess manifest lacks seed object")
    source_n = int(seed.get("source_points_n", -1))
    output_n = int(seed.get("output_points_n", -1))
    if source_n <= 0 or output_n <= 0:
        raise P0PrimeError("seed point counts are not positive")
    if (
        contract["require_source_output_point_count_equal"]
        and source_n != output_n
    ):
        raise P0PrimeError("preprocess point count changed")
    if bool(seed.get("downsample_applied")) != bool(
        contract["require_downsample_applied"]
    ):
        raise P0PrimeError("preprocess downsample flag mismatch")
    counts_raw = seed.get("classification_counts")
    if not isinstance(counts_raw, Mapping):
        raise P0PrimeError("seed classification_counts missing")
    try:
        counts = {str(int(key)): int(value) for key, value in counts_raw.items()}
    except (TypeError, ValueError) as exc:
        raise P0PrimeError("invalid seed classification_counts") from exc
    required = {str(value) for value in contract["required_classes"]}
    if set(counts) != required:
        raise P0PrimeError(f"seed classes differ from {sorted(required)}")
    if any(counts[key] <= 0 for key in required):
        raise P0PrimeError("seed lacks nonzero class-2 or class-6 support")
    if sum(counts.values()) != output_n:
        raise P0PrimeError("seed class counts do not sum to output_points_n")

    base = seed.get("base_las")
    if not isinstance(base, Mapping):
        raise P0PrimeError("seed.base_las missing")
    if base.get("crs") != contract["required_crs"]:
        raise P0PrimeError("base LAS declared CRS mismatch")
    if base.get("vertical_datum") != contract["required_vertical_datum"]:
        raise P0PrimeError("base LAS vertical datum mismatch")
    if Path(str(base.get("path", ""))).name != contract["base_las_filename"]:
        raise P0PrimeError("base LAS filename mismatch")
    digest = str(base.get("sha256", ""))
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise P0PrimeError("base LAS SHA256 is malformed")
    return {
        "building": dict(building),
        "seed": dict(seed),
        "base_las": dict(base),
        "declared_class_counts": counts,
        "source_points_n": source_n,
        "output_points_n": output_n,
    }


def inspect_las(path: Path) -> dict[str, Any]:
    try:
        import laspy
        import numpy as np
    except ImportError as exc:
        raise P0PrimeError("laspy/numpy are required in the tools image") from exc

    counts: dict[str, int] = {}
    with laspy.open(path) as reader:
        point_count = int(reader.header.point_count)
        crs = reader.header.parse_crs()
        epsg = crs.to_epsg() if crs is not None else None
        version = str(reader.header.version)
        point_format = int(reader.header.point_format.id)
        dimensions = {
            str(name).lower()
            for name in reader.header.point_format.dimension_names
        }
        for chunk in reader.chunk_iterator(1_000_000):
            values, numbers = np.unique(
                np.asarray(chunk.classification, dtype=np.uint8),
                return_counts=True,
            )
            for value, number in zip(values, numbers, strict=True):
                key = str(int(value))
                counts[key] = counts.get(key, 0) + int(number)
    return {
        "point_count": point_count,
        "epsg": epsg,
        "version": version,
        "point_format": point_format,
        "dimensions": sorted(dimensions),
        "class_counts": counts,
    }


def validate_preprocess_building(
    config: Mapping[str, Any],
    target: Mapping[str, str],
    *,
    deep: bool,
) -> dict[str, Any]:
    building_id = target[config["targets_csv"]["id_field"]]
    resolution = preprocess_resolution(config, building_id)
    manifest_path = resolution["building_manifest_path"]
    index_row = resolution["index_row"]
    if int(index_row["processing_order"]) != int(target["processing_order"]):
        raise P0PrimeError("preprocess index processing_order mismatch")
    if index_row["tier"] != target["tier"]:
        raise P0PrimeError("preprocess index tier mismatch")
    if index_row["cohort"] != target["cohort"]:
        raise P0PrimeError("preprocess index cohort mismatch")
    payload = load_json(manifest_path)
    validated = validate_preprocess_payload(
        payload,
        expected_building_id=building_id,
        expected_target=target,
        config=config,
    )
    base_path = resolve_declared_path(
        validated["base_las"]["path"],
        declaring_file=manifest_path,
    )
    if not base_path.is_file() or base_path.is_symlink():
        raise P0PrimeError(f"base LAS missing/non-regular: {repo_relative(base_path)}")
    actual_sha = sha256_file(base_path)
    if actual_sha != validated["base_las"]["sha256"]:
        raise P0PrimeError("base LAS SHA256 mismatch")
    actual: dict[str, Any] | None = None
    if deep:
        actual = inspect_las(base_path)
        contract = config["preprocess_consumer"]
        if actual["point_count"] != validated["output_points_n"]:
            raise P0PrimeError("base LAS point count differs from manifest")
        if actual["epsg"] != 25832:
            raise P0PrimeError(f"base LAS EPSG drift: {actual['epsg']}")
        if actual["version"] != "1.4":
            raise P0PrimeError(f"base LAS version drift: {actual['version']}")
        if actual["point_format"] != 3:
            raise P0PrimeError(
                f"base LAS point format drift: {actual['point_format']}"
            )
        if actual["class_counts"] != validated["declared_class_counts"]:
            raise P0PrimeError("base LAS actual class counts differ from manifest")
        if contract["require_rgb_dimensions"]:
            missing_rgb = {"red", "green", "blue"} - set(actual["dimensions"])
            if missing_rgb:
                raise P0PrimeError(
                    f"base LAS lacks RGB dimensions: {sorted(missing_rgb)}"
                )
    return {
        "resolution": resolution,
        "manifest_path": manifest_path,
        "manifest_sha256": sha256_file(manifest_path),
        "payload": payload,
        **validated,
        "base_las_path": base_path,
        "base_las_sha256": actual_sha,
        "actual_las": actual,
    }


def load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise P0PrimeError(f"cannot load canonical helper: {repo_relative(path)}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_helpers(config: Mapping[str, Any]) -> tuple[Any, Any, Any]:
    verify_static_inputs(config)
    helper = config["canonical_helpers"]
    w2 = load_module("fusion_w1_p0prime_w2", repo_path(helper["roofer_status"]["path"]))
    metric = load_module(
        "fusion_w1_p0prime_metric",
        repo_path(helper["roof_metrics"]["path"]),
    )
    coverage = load_module(
        "fusion_w1_p0prime_coverage",
        repo_path(helper["coverage_and_xy"]["path"]),
    )
    return w2, metric, coverage


def write_footprint_subset(
    config: Mapping[str, Any],
    building_id: str,
    output: Path,
) -> dict[str, Any]:
    if output.exists() or output.is_symlink():
        raise P0PrimeError(f"refusing to overwrite footprint: {repo_relative(output)}")
    source = repo_path(config["footprint"]["path"])
    output.parent.mkdir(parents=True, exist_ok=True)
    escaped = building_id.replace("'", "''")
    process = subprocess.run(
        [
            "ogr2ogr",
            "-f",
            "GPKG",
            output.as_posix(),
            source.as_posix(),
            config["footprint"]["layer"],
            "-where",
            f"{config['footprint']['id_field']} = '{escaped}'",
            "-nln",
            "p0prime_footprint",
            "-a_srs",
            config["footprint"]["crs"],
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if process.returncode or not output.is_file():
        raise P0PrimeError(
            f"ogr2ogr footprint subset failed exit={process.returncode}: "
            f"{process.stdout[-1000:]}"
        )
    info = subprocess.run(
        [
            "ogrinfo",
            "-ro",
            "-so",
            output.as_posix(),
            "p0prime_footprint",
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if (
        info.returncode
        or "Feature Count: 1" not in info.stdout
        or "25832" not in info.stdout
    ):
        raise P0PrimeError("per-building footprint is not one EPSG:25832 feature")
    return {
        "path": repo_relative(output),
        "sha256": sha256_file(output),
        "feature_count": 1,
        "crs": "EPSG:25832",
        "source_path": config["footprint"]["path"],
        "source_sha256": config["footprint"]["sha256"],
        "source_role": config["footprint"]["role"],
    }


def validate_receipt_file(
    path: Path,
    *,
    schema: str,
    state: str,
) -> dict[str, Any]:
    payload = load_json(path)
    if payload.get("schema") != schema or payload.get("state") != state:
        raise P0PrimeError(f"receipt contract mismatch: {repo_relative(path)}")
    return payload


def refuse_after_final_manifest(config: Mapping[str, Any]) -> None:
    final = repo_path(config["outputs"]["final_manifest"])
    if final.exists() or final.is_symlink():
        raise P0PrimeError("P0-prime final manifest already exists; work is frozen")


def update_progress(config: Mapping[str, Any], stage: str) -> None:
    paths = output_paths(config)
    score_path = paths["scores_csv"]
    rows = read_csv(score_path) if score_path.is_file() else []
    failures = 0
    failure_path = paths["failures_jsonl"]
    if failure_path.is_file():
        failures = sum(
            1
            for line in failure_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    payload = {
        "schema": "jointbuildgs.fusion_w1.seed_p0prime.progress.v1",
        "updated_utc": now_iso(),
        "stage": stage,
        "completed_buildings": len(rows),
        "failure_records": failures,
        "scores_csv": (
            {
                "path": repo_relative(score_path),
                "sha256": sha256_file(score_path),
            }
            if score_path.is_file()
            else None
        ),
        "learning_runs_started": 0,
        "new_inference_runs": 0,
        "outer_parallelism": 1,
    }
    atomic_json(paths["progress"], payload)


def check(
    config: Mapping[str, Any],
    *,
    building_id: str | None,
    deep: bool,
) -> dict[str, Any]:
    static = verify_static_inputs(config)
    targets = target_rows(config)
    selected = (
        [target_row(config, building_id)]
        if building_id
        else targets
    )
    ready = []
    missing = []
    invalid = []
    for target in selected:
        bid = target[config["targets_csv"]["id_field"]]
        try:
            manifest = preprocess_manifest_path(config, bid)
            if not manifest.is_file():
                missing.append(bid)
                continue
            record = validate_preprocess_building(config, target, deep=deep)
            ready.append(
                {
                    "building_id": bid,
                    "processing_order": int(target["processing_order"]),
                    "manifest": repo_relative(record["manifest_path"]),
                    "manifest_sha256": record["manifest_sha256"],
                    "base_las": repo_relative(record["base_las_path"]),
                    "base_las_sha256": record["base_las_sha256"],
                }
            )
        except Exception as exc:  # check reports every invalid manifest
            invalid.append({"building_id": bid, "error": str(exc)})
    return {
        "schema": "jointbuildgs.fusion_w1.seed_p0prime.check.v1",
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
    }


def prepare_one(
    config: Mapping[str, Any],
    building_id: str,
) -> dict[str, Any]:
    refuse_after_final_manifest(config)
    verify_static_inputs(config)
    target = target_row(config, building_id)
    job = building_dir(config, building_id)
    job.mkdir(parents=True, exist_ok=True)
    claim = job / "start.json"
    exclusive_json(
        claim,
        {
            "schema": BUILDING_RECEIPT_SCHEMA,
            "state": "STARTED",
            "stage": "classify",
            "created_utc": now_iso(),
            "building_id": building_id,
            "processing_order": int(target["processing_order"]),
            "classification_method": config["preprocess_consumer"][
                "classification_stage"
            ],
            "learning_runs_started": 0,
            "new_inference_runs": 0,
        },
    )
    seed = validate_preprocess_building(config, target, deep=True)
    footprint = write_footprint_subset(
        config,
        building_id,
        job / "footprint.gpkg",
    )
    actual = seed["actual_las"]
    assert actual is not None
    receipt = {
        "schema": (
            "jointbuildgs.fusion_w1.seed_p0prime.classification_receipt.v1"
        ),
        "state": "PASSED",
        "created_utc": now_iso(),
        "building_id": building_id,
        "processing_order": int(target["processing_order"]),
        "tier": target["tier"],
        "cohort": target["cohort"],
        "method": config["preprocess_consumer"]["classification_stage"],
        "mutation": {
            "geometry_changed": False,
            "classification_changed": False,
            "vertical_datum_changed": False,
            "file_rewritten": False,
            "smrf_runs_started": 0,
            "overlay_runs_started": 0,
        },
        "preprocess_manifest": {
            "path": repo_relative(seed["manifest_path"]),
            "sha256": seed["manifest_sha256"],
            "schema": seed["payload"]["schema"],
            "status": seed["payload"]["status"],
        },
        "preprocess_resolver": {
            "stable_run_manifest": {
                "path": repo_relative(
                    seed["resolution"]["stable_run_manifest_path"]
                ),
                "sha256": seed["resolution"]["stable_run_manifest_sha256"],
            },
            "cache_namespace": seed["resolution"]["cache_namespace"],
            "cache_run_manifest": {
                "path": repo_relative(
                    seed["resolution"]["cache_run_manifest_path"]
                ),
                "sha256": seed["resolution"][
                    "cache_run_manifest_sha256"
                ],
            },
            "preprocess_index": {
                "path": repo_relative(
                    seed["resolution"]["preprocess_index_path"]
                ),
                "sha256": seed["resolution"]["preprocess_index_sha256"],
            },
        },
        "classified_seed_las": {
            "path": repo_relative(seed["base_las_path"]),
            "sha256": seed["base_las_sha256"],
            "point_count": actual["point_count"],
            "class_counts": actual["class_counts"],
            "epsg": actual["epsg"],
            "vertical_datum": "orthometric",
            "las_version": actual["version"],
            "point_format": actual["point_format"],
            "rgb_dimensions_present": all(
                name in set(actual["dimensions"])
                for name in ("red", "green", "blue")
            ),
        },
        "footprint": footprint,
        "footprint_used_for_classification": False,
        "footprint_role_for_next_stage": "Roofer GroundSurface XY input",
        "learning_runs_started": 0,
        "new_inference_runs": 0,
    }
    exclusive_json(job / "classification_receipt.json", receipt)
    update_progress(config, f"classification_complete:{building_id}")
    return receipt


def roofer_argv(
    config: Mapping[str, Any],
    *,
    classified_las: str,
    footprint: str,
    output_dir: str,
) -> list[str]:
    return [
        *[str(value) for value in config["roofer"]["parameters"]],
        classified_las,
        footprint,
        output_dir,
    ]


def authorize_roofer(
    config: Mapping[str, Any], building_id: str
) -> dict[str, Any]:
    refuse_after_final_manifest(config)
    job = building_dir(config, building_id)
    classification_path = job / "classification_receipt.json"
    classification = validate_receipt_file(
        classification_path,
        schema=(
            "jointbuildgs.fusion_w1.seed_p0prime.classification_receipt.v1"
        ),
        state="PASSED",
    )
    seed = classification["classified_seed_las"]
    footprint = classification["footprint"]
    seed_path = repo_path(seed["path"])
    footprint_path = repo_path(footprint["path"])
    if sha256_file(seed_path) != seed["sha256"]:
        raise P0PrimeError("classified seed changed after validation")
    if sha256_file(footprint_path) != footprint["sha256"]:
        raise P0PrimeError("P0-prime footprint changed after validation")
    roofer_output = job / "roofer"
    if roofer_output.exists() or roofer_output.is_symlink():
        raise P0PrimeError("Roofer output path already exists before authorization")
    roofer_output.mkdir()
    invocation = {
        "schema": "jointbuildgs.fusion_w1.seed_p0prime.roofer_invocation.v1",
        "state": "AUTHORIZED",
        "created_utc": now_iso(),
        "building_id": building_id,
        "image": config["roofer"]["image"],
        "argv": roofer_argv(
            config,
            classified_las=seed["path"],
            footprint=footprint["path"],
            output_dir=repo_relative(roofer_output),
        ),
        "classified_las": seed,
        "classification_receipt": {
            "path": repo_relative(classification_path),
            "sha256": sha256_file(classification_path),
        },
        "footprint": footprint,
        "output_dir": repo_relative(roofer_output),
        "resource_contract": config["resource_lock"],
        "outer_parallelism": 1,
        "learning_runs_started": 0,
        "new_inference_runs": 0,
    }
    exclusive_json(job / "roofer_invocation.json", invocation)
    update_progress(config, f"roofer_authorized:{building_id}")
    return invocation


def accept_roofer(
    config: Mapping[str, Any],
    building_id: str,
    *,
    wall_seconds: float,
) -> dict[str, Any]:
    refuse_after_final_manifest(config)
    job = building_dir(config, building_id)
    invocation_path = job / "roofer_invocation.json"
    invocation = validate_receipt_file(
        invocation_path,
        schema="jointbuildgs.fusion_w1.seed_p0prime.roofer_invocation.v1",
        state="AUTHORIZED",
    )
    output_dir = repo_path(invocation["output_dir"])
    files = sorted(output_dir.glob("*.city.jsonl"))
    if not files:
        raise P0PrimeError("Roofer produced no CityJSONSeq output")
    file_records = [
        {
            "path": repo_relative(path),
            "sha256": sha256_file(path),
            "size": path.stat().st_size,
        }
        for path in files
        if path.is_file() and not path.is_symlink()
    ]
    if len(file_records) != len(files):
        raise P0PrimeError("Roofer output includes non-regular files")
    receipt = {
        "schema": "jointbuildgs.fusion_w1.seed_p0prime.roofer_receipt.v1",
        "state": "COMPLETE",
        "created_utc": now_iso(),
        "building_id": building_id,
        "invocation": {
            "path": repo_relative(invocation_path),
            "sha256": sha256_file(invocation_path),
        },
        "image": config["roofer"]["image"],
        "argv": invocation["argv"],
        "jsonseq_outputs": file_records,
        "wall_seconds": float(wall_seconds),
        "outer_parallelism": 1,
        "memory_limit": config["resource_lock"]["memory"],
        "learning_runs_started": 0,
        "new_inference_runs": 0,
    }
    exclusive_json(job / "roofer_receipt.json", receipt)
    update_progress(config, f"roofer_complete:{building_id}")
    return receipt


def roofer_paths(
    config: Mapping[str, Any], building_id: str
) -> tuple[str, str, str]:
    invocation = validate_receipt_file(
        building_dir(config, building_id) / "roofer_invocation.json",
        schema="jointbuildgs.fusion_w1.seed_p0prime.roofer_invocation.v1",
        state="AUTHORIZED",
    )
    classified = invocation["classified_las"]["path"]
    footprint = invocation["footprint"]["path"]
    output_dir = invocation["output_dir"]
    for value in (classified, footprint, output_dir):
        repo_path(value)
    return str(classified), str(footprint), str(output_dir)


def val3dity_version(expected: str) -> str:
    process = subprocess.run(
        ["val3dity", "--version"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    value = process.stdout.strip()
    if process.returncode or expected not in value:
        raise P0PrimeError(f"val3dity version drift: {value}")
    return value


def run_val3dity(
    cityjson: Path,
    report: Path,
) -> tuple[int, dict[str, dict[str, Any]], Path]:
    if report.exists() or report.is_symlink():
        raise P0PrimeError("refusing to overwrite val3dity report")
    report.parent.mkdir(parents=True, exist_ok=True)
    process = subprocess.run(
        [
            "val3dity",
            cityjson.as_posix(),
            "--report",
            report.as_posix(),
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    log_path = report.with_suffix(".log")
    atomic_bytes(
        log_path,
        (
            f"+ val3dity {cityjson} --report {report}\n"
            f"{process.stdout or ''}"
        ).encode("utf-8"),
    )
    if not report.is_file():
        raise P0PrimeError(
            f"val3dity emitted no report exit={process.returncode}"
        )
    payload = load_json(report)
    by_id = {
        str(feature.get("id")): dict(feature)
        for feature in payload.get("features", [])
        if isinstance(feature, Mapping) and feature.get("id") is not None
    }
    return int(process.returncode), by_id, log_path


def assembly_flags(
    roofer_feature: Mapping[str, Any] | None,
    *,
    val3dity_feature: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Keep LoD2 assembly independent from val3dity validity."""

    roofer_present = roofer_feature is not None
    attributes = (
        dict(roofer_feature.get("attributes") or {})
        if roofer_feature is not None
        else {}
    )
    rf_success = attributes.get("rf_success")
    unusable = attributes.get("rf_pointcloud_unusable")
    mode = str(attributes.get("rf_extrusion_mode", ""))
    has_lod22 = bool(
        roofer_feature.get("has_lod22") if roofer_feature is not None else False
    )
    lod1_fallback = mode == "lod11_fallback"
    assembly = bool(
        roofer_present
        and not falsehood(rf_success)
        and not truth(unusable)
        and mode not in {"skip", "lod11_fallback"}
        and has_lod22
    )
    val_present = val3dity_feature is not None
    val_valid = (
        bool(val3dity_feature.get("validity"))
        if val3dity_feature is not None
        else False
    )
    if assembly:
        assembly_reason = "lod22_geometry_present"
    elif not roofer_present:
        assembly_reason = "missing_roofer_feature"
    elif falsehood(rf_success):
        assembly_reason = "rf_success_false"
    elif truth(unusable):
        assembly_reason = "rf_pointcloud_unusable"
    elif mode == "lod11_fallback":
        assembly_reason = "lod11_fallback"
    elif mode == "skip":
        assembly_reason = "roofer_skip"
    else:
        assembly_reason = "missing_lod22_geometry"
    return {
        "roofer_feature_present": roofer_present,
        "rf_success": rf_success,
        "rf_pointcloud_unusable": unusable,
        "rf_extrusion_mode": mode,
        "has_lod22_geometry": has_lod22,
        "lod1_fallback": lod1_fallback,
        "assembly_lod2_success": assembly,
        "assembly_reason": assembly_reason,
        "val3dity_report_feature_present": val_present,
        "val3dity_valid": val_valid,
    }


def plane_f1(precision: Any, recall: Any) -> float | None:
    if precision is None or recall is None:
        return None
    p = float(precision)
    r = float(recall)
    if p + r <= 0:
        return 0.0
    return 2.0 * p * r / (p + r)


def cityjson_lod22_presence(path: Path, building_id: str) -> bool:
    payload = load_json(path)
    objects = payload.get("CityObjects") or {}
    parent = objects.get(building_id) or {}
    object_ids = [building_id, *(parent.get("children") or [])]
    return any(
        str(geometry.get("lod")) == "2.2"
        for object_id in object_ids
        for geometry in (objects.get(object_id) or {}).get("geometry", [])
    )


def baseline_row(
    config: Mapping[str, Any],
    building_id: str,
) -> dict[str, str]:
    baseline = config["p0_refl_baseline"]
    rows = [
        row
        for row in read_csv(repo_path(baseline["path"]))
        if row.get("building_id") == building_id
        and row.get("model_id") == baseline["model_id"]
        and row.get("role") == baseline["role"]
    ]
    if len(rows) != 1:
        raise P0PrimeError(f"P0 Ref-L baseline row is not unique: {building_id}")
    return rows[0]


def optional_float(value: Any) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    return float(value)


SCORE_FIELDS = [
    "schema",
    "row_type",
    "task_id",
    "building_id",
    "processing_order",
    "tier",
    "cohort",
    "preprocess_manifest",
    "preprocess_manifest_sha256",
    "seed_las",
    "seed_las_sha256",
    "seed_point_count",
    "seed_class2_count",
    "seed_class6_count",
    "seed_downsample_applied",
    "seed_crs",
    "seed_vertical_datum",
    "classification_method",
    "classification_geometry_changed",
    "classification_classes_changed",
    "classification_receipt",
    "classification_receipt_sha256",
    "footprint",
    "footprint_sha256",
    "roofer_image",
    "roofer_parameters",
    "roofer_invocation",
    "roofer_invocation_sha256",
    "roofer_receipt",
    "roofer_receipt_sha256",
    "roofer_wall_seconds",
    "roofer_feature_present",
    "rf_success",
    "rf_pointcloud_unusable",
    "rf_extrusion_mode",
    "assembly_lod2_success",
    "assembly_reason",
    "has_lod22_geometry",
    "lod1_fallback",
    "canonical_combined_status",
    "canonical_combined_reason",
    "val3dity_report_feature_present",
    "val3dity_valid",
    "val3dity_exit_code",
    "val3dity_report",
    "val3dity_report_sha256",
    "cityjson",
    "cityjson_sha256",
    "cityjson_crs",
    "geometry_roof_surface_present",
    "plane_match_count",
    "plane_precision",
    "plane_recall",
    "plane_f1",
    "roof_face_count_model",
    "roof_face_count_ref",
    "face_count_ratio",
    "roof_rms_m",
    "roof_hausdorff_m",
    "roof_distance_samples",
    "roof_completeness",
    "model_roof_xy_area_m2",
    "reference_roof_xy_area_m2",
    "roof_overlap_xy_area_m2",
    "xy_alignment",
    "xy_overlap_ratio",
    "score_time_z_shift_m",
    "p0_refl_has_lod22",
    "p0_refl_val3dity_valid",
    "p0_refl_roof_rms_m",
    "p0_refl_roof_completeness",
    "p0_refl_face_count_ratio",
    "assembly_lod2_matches_p0_refl",
    "delta_roof_rms_vs_p0_refl_m",
    "delta_roof_completeness_vs_p0_refl",
    "delta_face_count_ratio_vs_p0_refl",
    "processing_difference_observation",
    "reference_role",
    "reference_absolute_metric_caveat",
    "learning_runs_started",
    "new_inference_runs",
    "outer_parallelism",
    "score_wall_seconds",
    "status",
]


def score_one(
    config: Mapping[str, Any],
    building_id: str,
) -> dict[str, Any]:
    refuse_after_final_manifest(config)
    started = time.monotonic()
    target = target_row(config, building_id)
    job = building_dir(config, building_id)
    score_started = job / "score_started.json"
    exclusive_json(
        score_started,
        {
            "schema": BUILDING_RECEIPT_SCHEMA,
            "state": "STARTED",
            "stage": "score",
            "created_utc": now_iso(),
            "building_id": building_id,
        },
    )
    classification_path = job / "classification_receipt.json"
    classification = validate_receipt_file(
        classification_path,
        schema=(
            "jointbuildgs.fusion_w1.seed_p0prime.classification_receipt.v1"
        ),
        state="PASSED",
    )
    roofer_invocation_path = job / "roofer_invocation.json"
    roofer_receipt_path = job / "roofer_receipt.json"
    invocation = validate_receipt_file(
        roofer_invocation_path,
        schema="jointbuildgs.fusion_w1.seed_p0prime.roofer_invocation.v1",
        state="AUTHORIZED",
    )
    roofer_receipt = validate_receipt_file(
        roofer_receipt_path,
        schema="jointbuildgs.fusion_w1.seed_p0prime.roofer_receipt.v1",
        state="COMPLETE",
    )
    for record in roofer_receipt["jsonseq_outputs"]:
        path = repo_path(record["path"])
        if sha256_file(path) != record["sha256"]:
            raise P0PrimeError("Roofer JSONSeq changed before scoring")

    w2, metric, coverage_helper = load_helpers(config)
    cityjson = job / "cityjson" / "seed_p0prime.city.json"
    cityjson.parent.mkdir(parents=True, exist_ok=True)
    if cityjson.exists() or cityjson.is_symlink():
        raise P0PrimeError("refusing to overwrite combined CityJSON")
    jsonseq = [
        repo_path(record["path"])
        for record in roofer_receipt["jsonseq_outputs"]
    ]
    w2.combine_cityjsonseq(jsonseq, cityjson)
    val_version = val3dity_version(config["tools"]["val3dity_version"])
    val_exit, val_by_id, val_log = run_val3dity(
        cityjson,
        job / "val3dity" / "seed_p0prime.report.json",
    )
    val_report = job / "val3dity" / "seed_p0prime.report.json"
    roofer_by_id = w2.parse_roofer_features(jsonseq)
    canonical_rows = w2.classify_buildings(
        "P0PRIME",
        [building_id],
        roofer_by_id,
        val_by_id,
    )
    if len(canonical_rows) != 1:
        raise P0PrimeError("canonical Roofer status row count drift")
    canonical = canonical_rows[0]
    flags = assembly_flags(
        roofer_by_id.get(building_id),
        val3dity_feature=val_by_id.get(building_id),
    )
    measured_geometry_lod22 = cityjson_lod22_presence(cityjson, building_id)
    if measured_geometry_lod22 != flags["has_lod22_geometry"]:
        raise P0PrimeError("Roofer JSONSeq/combined CityJSON LoD2 mismatch")

    reference = metric.parse_lod2_roofs(
        repo_path(config["reference"]["lod2_dir"]),
        {building_id},
    )
    if building_id not in reference:
        raise P0PrimeError(f"reference roof is missing: {building_id}")
    parsed = metric.parse_cityjson_roofs(cityjson, {building_id})
    prediction = metric.shift_surface_z(
        list(parsed.get(building_id, [])),
        float(config["reference"]["score_time_z_shift_m"]),
    )
    refs = list(reference[building_id])
    comparison = metric.compare_building(refs, prediction)
    coverage = coverage_helper.roof_xy_coverage(refs, prediction)
    xy_alignment, xy_overlap = coverage_helper.xy_check(refs, prediction)
    precision = comparison["correctness"]
    recall = comparison["completeness"]
    f1 = plane_f1(precision, recall)
    fallback = bool(flags["lod1_fallback"])
    model_faces = 1 if fallback and prediction else len(prediction)
    ref_faces = len(refs)

    baseline = baseline_row(config, building_id)
    baseline_lod2 = truth(baseline["has_lod22"])
    baseline_rms = optional_float(baseline["roof_rms_m"])
    baseline_completeness = optional_float(baseline["roof_completeness"])
    baseline_face_ratio = optional_float(baseline["face_count_ratio"])
    current_rms = optional_float(comparison["ref_rms_m"])
    current_completeness = optional_float(coverage["roof_completeness"])
    current_face_ratio = model_faces / ref_faces if ref_faces else None
    matches_refl = bool(flags["assembly_lod2_success"]) == baseline_lod2
    if matches_refl:
        difference_observation = "none_at_lod2_boolean"
    else:
        difference_observation = (
            "lod2_boolean_diff_with_point_count_classes_and_datum_preserved;"
            "inspect_per_building_crop_support_and_roofer_receipts"
        )

    seed_las = classification["classified_seed_las"]
    preprocess = classification["preprocess_manifest"]
    footprint = classification["footprint"]
    row: dict[str, Any] = {
        "schema": SCORE_SCHEMA,
        "row_type": "building_seed_p0prime",
        "task_id": config["task_id"],
        "building_id": building_id,
        "processing_order": int(target["processing_order"]),
        "tier": target["tier"],
        "cohort": target["cohort"],
        "preprocess_manifest": preprocess["path"],
        "preprocess_manifest_sha256": preprocess["sha256"],
        "seed_las": seed_las["path"],
        "seed_las_sha256": seed_las["sha256"],
        "seed_point_count": seed_las["point_count"],
        "seed_class2_count": seed_las["class_counts"]["2"],
        "seed_class6_count": seed_las["class_counts"]["6"],
        "seed_downsample_applied": False,
        "seed_crs": "EPSG:25832",
        "seed_vertical_datum": "orthometric",
        "classification_method": classification["method"],
        "classification_geometry_changed": False,
        "classification_classes_changed": False,
        "classification_receipt": repo_relative(classification_path),
        "classification_receipt_sha256": sha256_file(classification_path),
        "footprint": footprint["path"],
        "footprint_sha256": footprint["sha256"],
        "roofer_image": config["roofer"]["image"],
        "roofer_parameters": " ".join(config["roofer"]["parameters"]),
        "roofer_invocation": repo_relative(roofer_invocation_path),
        "roofer_invocation_sha256": sha256_file(roofer_invocation_path),
        "roofer_receipt": repo_relative(roofer_receipt_path),
        "roofer_receipt_sha256": sha256_file(roofer_receipt_path),
        "roofer_wall_seconds": float(roofer_receipt["wall_seconds"]),
        **flags,
        "canonical_combined_status": canonical.get("status", ""),
        "canonical_combined_reason": canonical.get("reason", ""),
        "val3dity_exit_code": val_exit,
        "val3dity_report": repo_relative(val_report),
        "val3dity_report_sha256": sha256_file(val_report),
        "cityjson": repo_relative(cityjson),
        "cityjson_sha256": sha256_file(cityjson),
        "cityjson_crs": coverage_helper.cityjson_crs(cityjson),
        "geometry_roof_surface_present": bool(prediction),
        "plane_match_count": comparison["match_count"],
        "plane_precision": precision,
        "plane_recall": recall,
        "plane_f1": f1,
        "roof_face_count_model": model_faces,
        "roof_face_count_ref": ref_faces,
        "face_count_ratio": current_face_ratio,
        "roof_rms_m": current_rms,
        "roof_hausdorff_m": comparison["ref_hausdorff_m"],
        "roof_distance_samples": comparison["ref_distance_samples"],
        **coverage,
        "xy_alignment": xy_alignment,
        "xy_overlap_ratio": xy_overlap,
        "score_time_z_shift_m": config["reference"]["score_time_z_shift_m"],
        "p0_refl_has_lod22": baseline_lod2,
        "p0_refl_val3dity_valid": truth(baseline["val3dity_valid"]),
        "p0_refl_roof_rms_m": baseline_rms,
        "p0_refl_roof_completeness": baseline_completeness,
        "p0_refl_face_count_ratio": baseline_face_ratio,
        "assembly_lod2_matches_p0_refl": matches_refl,
        "delta_roof_rms_vs_p0_refl_m": (
            current_rms - baseline_rms
            if current_rms is not None and baseline_rms is not None
            else None
        ),
        "delta_roof_completeness_vs_p0_refl": (
            current_completeness - baseline_completeness
            if current_completeness is not None
            and baseline_completeness is not None
            else None
        ),
        "delta_face_count_ratio_vs_p0_refl": (
            current_face_ratio - baseline_face_ratio
            if current_face_ratio is not None
            and baseline_face_ratio is not None
            else None
        ),
        "processing_difference_observation": difference_observation,
        "reference_role": config["reference"]["role"],
        "reference_absolute_metric_caveat": config["reference"][
            "absolute_metric_caveat"
        ],
        "learning_runs_started": 0,
        "new_inference_runs": 0,
        "outer_parallelism": 1,
        "score_wall_seconds": 0.0,
        "status": "MEASURED",
    }
    row["score_wall_seconds"] = time.monotonic() - started
    score_receipt_path = job / "score_receipt.json"
    score_receipt = {
        "schema": "jointbuildgs.fusion_w1.seed_p0prime.score_receipt.v1",
        "state": "MEASURED",
        "created_utc": now_iso(),
        "building_id": building_id,
        "row": row,
        "row_sha256": sha256_bytes(canonical_json(row)),
        "canonical_helpers": config["canonical_helpers"],
        "val3dity_version": val_version,
        "val3dity_log": {
            "path": repo_relative(val_log),
            "sha256": sha256_file(val_log),
        },
        "assembly_lod2_success_excludes_val3dity": True,
        "reference_opened_only_after_roofer_output_frozen": True,
        "learning_runs_started": 0,
        "new_inference_runs": 0,
    }
    exclusive_json(score_receipt_path, score_receipt)
    upsert_score_row(config, row)
    score_path = repo_path(config["outputs"]["scores_csv"])
    complete = {
        "schema": BUILDING_RECEIPT_SCHEMA,
        "state": "COMPLETE",
        "created_utc": now_iso(),
        "building_id": building_id,
        "processing_order": int(target["processing_order"]),
        "score_receipt": {
            "path": repo_relative(score_receipt_path),
            "sha256": sha256_file(score_receipt_path),
        },
        "scores_csv_at_completion": {
            "path": repo_relative(score_path),
            "sha256": sha256_file(score_path),
            "row_count": len(read_csv(score_path)),
        },
        "assembly_lod2_success": flags["assembly_lod2_success"],
        "val3dity_valid": flags["val3dity_valid"],
        "manifest_written_after_incremental_scores_csv": True,
        "learning_runs_started": 0,
        "new_inference_runs": 0,
    }
    exclusive_json(job / "complete.json", complete)
    update_progress(config, f"building_complete:{building_id}")
    return complete


def upsert_score_row(
    config: Mapping[str, Any], row: Mapping[str, Any]
) -> None:
    path = repo_path(config["outputs"]["scores_csv"])
    lock = path.with_suffix(path.suffix + ".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open("a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        rows: list[dict[str, Any]] = (
            [dict(value) for value in read_csv(path)] if path.is_file() else []
        )
        building_id = str(row["building_id"])
        existing = [value for value in rows if value.get("building_id") == building_id]
        if existing:
            raise P0PrimeError(
                f"incremental score row already exists: {building_id}"
            )
        rows.append(dict(row))
        rows.sort(key=lambda value: int(value["processing_order"]))
        atomic_csv(path, rows, SCORE_FIELDS)
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def record_failure(
    config: Mapping[str, Any],
    *,
    building_id: str | None,
    stage: str,
    message: str,
    detail: str = "",
) -> dict[str, Any]:
    paths = output_paths(config)
    payload = {
        "schema": "jointbuildgs.fusion_w1.seed_p0prime.failure.v1",
        "created_utc": now_iso(),
        "building_id": building_id,
        "stage": stage,
        "message": message,
        "detail": detail[-12000:],
        "learning_runs_started": 0,
        "new_inference_runs": 0,
    }
    append_jsonl(paths["failures_jsonl"], payload)
    if building_id:
        job = building_dir(config, building_id)
        job.mkdir(parents=True, exist_ok=True)
        token = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        exclusive_json(job / f"failure_{token}.json", payload)
    update_progress(config, f"failure:{stage}")
    return payload


def list_ready(config: Mapping[str, Any]) -> list[str]:
    ids = []
    for target in target_rows(config):
        building_id = target[config["targets_csv"]["id_field"]]
        try:
            if preprocess_manifest_path(config, building_id).is_file():
                ids.append(building_id)
        except P0PrimeError:
            continue
    return ids


def list_pending(config: Mapping[str, Any]) -> list[str]:
    pending = []
    for building_id in list_ready(config):
        job = building_dir(config, building_id)
        if not (job / "start.json").exists():
            pending.append(building_id)
    return pending


def finalize(
    config: Mapping[str, Any],
    *,
    require_all: bool,
) -> dict[str, Any]:
    refuse_after_final_manifest(config)
    paths = output_paths(config)
    scores = read_csv(paths["scores_csv"]) if paths["scores_csv"].is_file() else []
    targets = target_rows(config)
    target_ids = {
        row[config["targets_csv"]["id_field"]]
        for row in targets
    }
    score_ids = [row["building_id"] for row in scores]
    if len(score_ids) != len(set(score_ids)):
        raise P0PrimeError("duplicate building score rows")
    if not set(score_ids).issubset(target_ids):
        raise P0PrimeError("score CSV contains a non-target building")
    completion_records = []
    for row in scores:
        complete_path = building_dir(config, row["building_id"]) / "complete.json"
        complete = validate_receipt_file(
            complete_path,
            schema=BUILDING_RECEIPT_SCHEMA,
            state="COMPLETE",
        )
        score_receipt = repo_path(complete["score_receipt"]["path"])
        if sha256_file(score_receipt) != complete["score_receipt"]["sha256"]:
            raise P0PrimeError("score receipt changed after building completion")
        completion_records.append(
            {
                "building_id": row["building_id"],
                "processing_order": int(row["processing_order"]),
                "complete_receipt": repo_relative(complete_path),
                "complete_receipt_sha256": sha256_file(complete_path),
            }
        )
    if require_all and len(scores) != len(targets):
        raise P0PrimeError(
            f"require-all requested but complete={len(scores)}/{len(targets)}"
        )
    update_progress(config, "finalize_pre_manifest")
    manifest = {
        "schema": "jointbuildgs.fusion_w1.seed_p0prime.manifest.v1",
        "state": "COMPLETE" if len(scores) == len(targets) else "PARTIAL",
        "created_utc": now_iso(),
        "task_id": config["task_id"],
        "population": {
            "target_count": len(targets),
            "completed_count": len(scores),
            "assembly_lod2_success_count": sum(
                truth(row["assembly_lod2_success"]) for row in scores
            ),
            "val3dity_valid_count": sum(
                truth(row["val3dity_valid"]) for row in scores
            ),
            "assembly_and_val3dity_are_independent": True,
        },
        "scores_csv": {
            "path": repo_relative(paths["scores_csv"]),
            "sha256": sha256_file(paths["scores_csv"]),
            "row_count": len(scores),
        },
        "progress": {
            "path": repo_relative(paths["progress"]),
            "sha256": sha256_file(paths["progress"]),
        },
        "completion_records": completion_records,
        "roofer": config["roofer"],
        "resource_lock": config["resource_lock"],
        "canonical_helpers": config["canonical_helpers"],
        "input_schema_assumptions": config["input_schema_assumptions"],
        "reference": config["reference"],
        "learning_runs_started": 0,
        "new_inference_runs": 0,
        "manifest_written_last": True,
    }
    exclusive_json(paths["final_manifest"], manifest)
    return manifest


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
    print(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        flush=True,
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    config_path = repo_path(args.config) if not Path(args.config).is_absolute() else Path(args.config)
    config = load_config(config_path)
    command = args.command
    building_id = getattr(args, "building_id", None)
    try:
        if command == "check":
            print_json(
                check(
                    config,
                    building_id=building_id,
                    deep=bool(args.deep),
                )
            )
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
        elif command == "accept-roofer":
            verify_git_runtime(config)
            print_json(
                accept_roofer(
                    config,
                    building_id,
                    wall_seconds=float(args.wall_seconds),
                )
            )
        elif command == "roofer-paths":
            for value in roofer_paths(config, building_id):
                print(value)
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
            raise P0PrimeError(f"unknown command: {command}")
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
