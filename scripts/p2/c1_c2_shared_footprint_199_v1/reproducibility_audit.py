#!/usr/bin/env python3
"""Compute and compare deterministic geometry digests for the 199-building Roofer run."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence


SCHEMA = "jointbuildgs.p2.c1_c2_shared_footprint_199.reproducibility_geometry_manifest.v1"


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            size += len(chunk)
            digest.update(chunk)
    return size, digest.hexdigest()


def canonical_cityjson_geometry(path: Path) -> dict[str, Any]:
    header_transform: Mapping[str, Any] | None = None
    features: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if record.get("type") == "CityJSON":
            header_transform = record.get("transform")
            continue
        if record.get("type") != "CityJSONFeature":
            raise RuntimeError(f"unsupported CityJSONSeq record in {path}")
        objects = {}
        for object_id, city_object in sorted((record.get("CityObjects") or {}).items()):
            objects[object_id] = {
                key: city_object[key]
                for key in ("type", "parents", "children", "geometry")
                if key in city_object
            }
        features.append({
            "id": record.get("id"),
            "vertices": record.get("vertices"),
            "CityObjects": objects,
        })
    if header_transform is None or not features:
        raise RuntimeError(f"incomplete CityJSONSeq: {path}")
    normalized = {
        "normalization": "DROP_METADATA_AND_ALL_CITYOBJECT_ATTRIBUTES_KEEP_TRANSFORM_VERTICES_GEOMETRY_SEMANTICS",
        "transform": header_transform,
        "features": features,
    }
    return {
        "canonical_geometry_sha256": sha256_bytes(canonical_bytes(normalized)),
        "feature_count": len(features),
        "lod22_present": any(
            str(geometry.get("lod")) == "2.2"
            for feature in features
            for city_object in feature["CityObjects"].values()
            for geometry in city_object.get("geometry", [])
        ),
    }


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def normalized_result_row(task_root: Path, row: Mapping[str, Any]) -> dict[str, Any]:
    outputs = []
    for output in row.get("outputs") or []:
        path = task_root / str(output["path"])
        size, digest = sha256_file(path)
        if size != int(output["bytes"]) or digest != str(output["sha256"]):
            raise RuntimeError(f"Roofer output identity drift: {path}")
        outputs.append(canonical_cityjson_geometry(path))
    normalized = {
        "operation_unit_id": row["operation_unit_id"],
        "condition_id": row["condition_id"],
        "population_index": int(row["population_index"]),
        "stable_id": row["stable_id"],
        "status": row["status"],
        "classification": row.get("classification"),
        "pre_roofer_failure": row.get("pre_roofer_failure"),
        "input_sha256": (row.get("input") or {}).get("sha256"),
        "shared_footprint_sha256": row["shared_footprint"]["sha256"],
        "outputs": outputs,
    }
    return {**normalized, "canonical_operation_sha256": sha256_bytes(canonical_bytes(normalized))}


def build_manifest(task_root: Path, config_path: Path) -> dict[str, Any]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    result_path = task_root / "results/building_method_results_v1.jsonl"
    rows = read_jsonl(result_path)
    if len(rows) != 398:
        raise RuntimeError(f"expected 398 result rows, received {len(rows)}")
    normalized_rows = [normalized_result_row(task_root, row) for row in rows]
    normalized_rows.sort(key=lambda row: (row["condition_id"], row["population_index"]))
    if len({row["operation_unit_id"] for row in normalized_rows}) != 398:
        raise RuntimeError("operation IDs are duplicated")
    counts = Counter((row["condition_id"], row["status"]) for row in normalized_rows)
    lod22_counts = Counter(
        row["condition_id"]
        for row in normalized_rows
        if any(output["lod22_present"] for output in row["outputs"])
    )
    population_geometry_sha256 = sha256_bytes(canonical_bytes(normalized_rows))
    config_size, config_sha256 = sha256_file(config_path)
    return {
        "schema": SCHEMA,
        "task_id": config["task_id"],
        "decision_id": config["decision_id"],
        "status": "DETERMINISTIC_GEOMETRY_DIGEST_COMPLETE",
        "normalization": {
            "ignored_as_volatile": ["CityJSON metadata including referenceDate", "all CityObject attributes including rf_t_run", "runtime logs", "receipt timestamps"],
            "retained": ["input and shared-footprint hashes", "preparation classification", "status and missingness", "CityJSON transform", "vertices", "geometry boundaries", "semantics"],
        },
        "execution_lock": {
            "config": {"bytes": config_size, "sha256": config_sha256},
            "project_image": config["execution"]["project_image"],
            "project_image_id": config["execution"]["project_image_id"],
            "roofer_image": config["roofer"]["image"],
            "roofer_image_id": config["roofer"]["image_id"],
            "roofer_command_args": config["roofer"]["command_args"],
        },
        "row_count": len(normalized_rows),
        "counts_by_method_status": {
            method: {status: count for (row_method, status), count in sorted(counts.items()) if row_method == method}
            for method in config["methods"]
        },
        "lod22_geometry_count_by_method": {method: lod22_counts[method] for method in config["methods"]},
        "population_geometry_sha256": population_geometry_sha256,
        "rows": normalized_rows,
        "scientific_verdict": None,
    }


def write_or_verify(path: Path, data: bytes) -> str:
    if path.exists():
        if not path.is_file() or path.is_symlink() or path.read_bytes() != data:
            raise RuntimeError(f"existing reproducibility manifest differs: {path}")
        return "VERIFIED_EXISTING_IDENTICAL"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(data)
    return "WRITTEN_NEW"


def run(task_root: Path, config_path: Path, reference: Path | None) -> dict[str, Any]:
    manifest = build_manifest(task_root, config_path)
    output = task_root / "control/reproducibility_geometry_manifest_v1.json"
    write_status = write_or_verify(output, canonical_bytes(manifest))
    comparison = "NOT_REQUESTED"
    if reference is not None:
        reference_manifest = json.loads(reference.read_text(encoding="utf-8"))
        if reference_manifest.get("schema") != SCHEMA:
            raise RuntimeError("reference reproducibility manifest schema mismatch")
        if reference_manifest.get("population_geometry_sha256") != manifest["population_geometry_sha256"]:
            raise RuntimeError("REPRODUCIBILITY_MISMATCH: population geometry digest differs")
        comparison = "MATCH_REFERENCE_POPULATION_GEOMETRY_SHA256"
    return {
        "manifest": str(output),
        "write_status": write_status,
        "comparison": comparison,
        "population_geometry_sha256": manifest["population_geometry_sha256"],
        "scientific_verdict": None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-root", type=Path, required=True)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/p2/c1_c2_shared_footprint_199_v1/run_v1.json"),
    )
    parser.add_argument("--reference", type=Path)
    args = parser.parse_args()
    print(json.dumps(run(args.task_root.resolve(), args.config.resolve(), args.reference.resolve() if args.reference else None), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
