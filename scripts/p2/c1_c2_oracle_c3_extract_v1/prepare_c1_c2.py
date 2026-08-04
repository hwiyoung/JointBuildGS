#!/usr/bin/env python3
"""Prepare six add-once building-specific C1/C2 Roofer oracle jobs."""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import struct
from typing import Any, Mapping, Sequence

import numpy as np

from scripts.p2.c1_c2_oracle_c3_extract_v1.contract import (
    CONDITIONS,
    canonical_json_bytes,
    classify_oracle_crop,
    file_record,
    footprint_geojson,
    load_building_references,
    load_config,
    sha256_file,
    validate_config,
    write_las,
    write_new,
)


def _validate_exact(path: Path, spec: Mapping[str, Any], *, hash_content: bool) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(f"exact input missing/non-regular: {path}")
    observed_size = path.stat().st_size
    if observed_size != int(spec["bytes"]):
        raise RuntimeError(f"exact input size drift: {path}")
    if hash_content:
        size, digest = sha256_file(path)
        if size != int(spec["bytes"]) or digest != str(spec["sha256"]):
            raise RuntimeError(f"exact input digest drift: {path}")
        return {"path": path.as_posix(), "bytes": size, "sha256": digest, "full_hash_passes": 1}
    return {
        "path": path.as_posix(),
        "bytes": observed_size,
        "sha256": str(spec["sha256"]),
        "full_hash_passes": 0,
        "verification": "PREVIOUSLY_FROZEN_DIGEST_SIZE_CHECK_THIS_PROCESS",
    }


def _bounds(reference: Any, buffer_m: float) -> tuple[float, float, float, float]:
    x0, y0, x1, y1 = reference.footprint.bounds
    return x0 - buffer_m, y0 - buffer_m, x1 + buffer_m, y1 + buffer_m


def collect_laz(path: Path, references: Mapping[str, Any], buffer_m: float) -> dict[str, np.ndarray]:
    import laspy

    chunks: dict[str, list[np.ndarray]] = defaultdict(list)
    bounds = {stable_id: _bounds(reference, buffer_m) for stable_id, reference in references.items()}
    with laspy.open(path) as stream:
        for points in stream.chunk_iterator(2_000_000):
            x = np.asarray(points.x)
            y = np.asarray(points.y)
            z = np.asarray(points.z)
            for stable_id, (x0, y0, x1, y1) in bounds.items():
                keep = (x >= x0) & (x <= x1) & (y >= y0) & (y <= y1)
                if np.any(keep):
                    chunks[stable_id].append(np.column_stack((x[keep], y[keep], z[keep])))
    output = {}
    for stable_id in references:
        if not chunks[stable_id]:
            raise RuntimeError(f"C1 source crop is empty: {stable_id}")
        output[stable_id] = np.vstack(chunks[stable_id])
    return output


def _binary_ply_layout(path: Path) -> tuple[int, int, np.dtype]:
    with path.open("rb") as stream:
        header_lines = []
        while True:
            line = stream.readline()
            if not line:
                raise RuntimeError("truncated PLY header")
            header_lines.append(line.decode("ascii").strip())
            if header_lines[-1] == "end_header":
                break
        offset = stream.tell()
    if "format binary_little_endian 1.0" not in header_lines:
        raise RuntimeError("C2 source must be binary little-endian PLY")
    vertex_line = next((line for line in header_lines if line.startswith("element vertex ")), None)
    if vertex_line is None:
        raise RuntimeError("PLY vertex count missing")
    count = int(vertex_line.split()[-1])
    properties = [line.split() for line in header_lines if line.startswith("property ")]
    type_map = {
        "float": "<f4", "float32": "<f4", "double": "<f8", "float64": "<f8",
        "uchar": "u1", "uint8": "u1", "char": "i1", "int8": "i1",
        "ushort": "<u2", "uint16": "<u2", "int": "<i4", "int32": "<i4",
        "uint": "<u4", "uint32": "<u4",
    }
    fields = []
    for tokens in properties:
        if len(tokens) != 3 or tokens[1] not in type_map:
            raise RuntimeError(f"unsupported PLY property: {' '.join(tokens)}")
        fields.append((tokens[2], type_map[tokens[1]]))
    dtype = np.dtype(fields)
    expected = offset + count * dtype.itemsize
    if expected != path.stat().st_size:
        raise RuntimeError(f"PLY size/layout mismatch: expected={expected} actual={path.stat().st_size}")
    return offset, count, dtype


def collect_mvs(
    path: Path,
    references: Mapping[str, Any],
    buffer_m: float,
    shift_xyz: Sequence[float],
) -> dict[str, np.ndarray]:
    offset, count, dtype = _binary_ply_layout(path)
    data = np.memmap(path, mode="r", dtype=dtype, offset=offset, shape=(count,))
    shift = np.asarray(shift_xyz, dtype=np.float64)
    chunks: dict[str, list[np.ndarray]] = defaultdict(list)
    bounds = {stable_id: _bounds(reference, buffer_m) for stable_id, reference in references.items()}
    batch_size = 2_000_000
    for start in range(0, count, batch_size):
        rows = data[start:min(count, start + batch_size)]
        x = np.asarray(rows["x"], dtype=np.float64) + shift[0]
        y = np.asarray(rows["y"], dtype=np.float64) + shift[1]
        z = np.asarray(rows["z"], dtype=np.float64) + shift[2]
        for stable_id, (x0, y0, x1, y1) in bounds.items():
            keep = (x >= x0) & (x <= x1) & (y >= y0) & (y <= y1)
            if np.any(keep):
                chunks[stable_id].append(np.column_stack((x[keep], y[keep], z[keep])))
    output = {}
    for stable_id in references:
        if not chunks[stable_id]:
            raise RuntimeError(f"C2 source crop is empty: {stable_id}")
        output[stable_id] = np.vstack(chunks[stable_id])
    return output


def _prepare_method(
    output_root: Path,
    method: str,
    crops: Mapping[str, np.ndarray],
    references: Mapping[str, Any],
    config: Mapping[str, Any],
) -> list[dict[str, Any]]:
    prep = config["c1_c2_preparation"]
    records = []
    for stable_id in config["scope"]["building_ids"]:
        building, ground, stats = classify_oracle_crop(
            crops[stable_id],
            references[stable_id],
            crop_buffer_m=float(prep["crop_buffer_m"]),
            ground_ring_inner_buffer_m=float(prep["ground_ring_inner_buffer_m"]),
            minimum_building_height_m=float(prep["minimum_building_height_above_local_ground_m"]),
            ground_cell_m=float(prep["ground_height_cell_m"]),
            ground_keep_above_m=float(prep["ground_keep_above_local_ground_m"]),
            voxel_m=float(prep["deterministic_voxel_m"]),
        )
        operation_id = f"{method}|{stable_id}"
        minimum_class6 = int(prep["minimum_roofer_class6_points"])
        eligible = len(building) >= minimum_class6
        work = output_root / "operations" / method / stable_id / "work"
        input_path = work / "input.las"
        footprint_path = work / "gt_footprint_oracle.geojson"
        write_las(input_path, building, ground)
        write_new(footprint_path, canonical_json_bytes(footprint_geojson(references[stable_id])))
        record = {
            "operation_unit_id": operation_id,
            "condition_id": method,
            "stable_id": stable_id,
            "work_directory": work.relative_to(output_root).as_posix(),
            "output_directory": (work / "out").relative_to(output_root).as_posix(),
            "input": file_record(input_path, output_root),
            "footprint": file_record(footprint_path, output_root),
            "classification": stats,
            "roofer_eligible": eligible,
            "pre_roofer_failure": None if eligible else {
                "code": "PRE_ROOFER_REFERENCE_ID_ALIGNMENT_FAILURE",
                "reason": "GT GroundSurface XY contains fewer than the fixed minimum class-6 observations in current evidence",
                "observed_class6_points": int(len(building)),
                "minimum_class6_points": minimum_class6,
            },
            "oracle_diagnostic": True,
            "official_honest_stage3": False,
            "roofsurface_used_as_roofer_input": False,
            "scientific_verdict": None,
        }
        write_new(work / "prepared_v1.json", canonical_json_bytes(record))
        records.append(record)
    return records


def prepare(
    *,
    output_root: Path,
    c1_path: Path,
    c2_path: Path,
    lod2_path: Path,
    hash_inputs: bool,
) -> dict[str, Any]:
    config = load_config()
    validate_config(config, require_activation=True)
    if output_root.exists():
        raise RuntimeError(f"add-once output namespace already exists: {output_root}")
    output_root.mkdir(parents=True)
    input_specs = config["inputs"]
    source_records = {
        "c1": _validate_exact(c1_path, input_specs["c1_current_uas_lidar"], hash_content=hash_inputs),
        "c2": _validate_exact(c2_path, input_specs["c2_exact_common_mvs"], hash_content=hash_inputs),
        "lod2": _validate_exact(lod2_path, input_specs["gt_footprint_and_display_lod2"], hash_content=hash_inputs),
    }
    references = load_building_references(lod2_path, config["scope"]["building_ids"])
    prep = config["c1_c2_preparation"]
    c1_crops = collect_laz(c1_path, references, float(prep["crop_buffer_m"]))
    c2_crops = collect_mvs(
        c2_path,
        references,
        float(prep["crop_buffer_m"]),
        config["frame"]["world_shift_xyz"],
    )
    rows = []
    rows.extend(_prepare_method(output_root, CONDITIONS[0], c1_crops, references, config))
    rows.extend(_prepare_method(output_root, CONDITIONS[1], c2_crops, references, config))
    if len(rows) != 6 or len({row["operation_unit_id"] for row in rows}) != 6:
        raise RuntimeError("expected six unique C1/C2 building-method records")
    jobs = [row for row in rows if row["roofer_eligible"]]
    failures = [row for row in rows if not row["roofer_eligible"]]
    if len(jobs) != 4 or len(failures) != 2:
        raise RuntimeError(
            f"fixed representative alignment outcome drifted: jobs={len(jobs)} failures={len(failures)}"
        )
    if {row["stable_id"] for row in failures} != {"DEBY_LOD2_4907177"}:
        raise RuntimeError("unexpected building entered the pre-Roofer alignment-failure set")
    write_new(
        output_root / "freeze/c1_c2_execution_units_v1.jsonl",
        b"".join(canonical_json_bytes(row) for row in rows),
    )
    tsv = "operation_unit_id\twork_directory\n" + "".join(
        f"{row['operation_unit_id']}\t{row['work_directory']}\n" for row in jobs
    )
    write_new(output_root / "freeze/c1_c2_execution_units_v1.tsv", tsv.encode("utf-8"))
    body = {
        "schema": "jointbuildgs.c1_c2_oracle_preparation.v1",
        "status": "PREPARED_FOUR_ROOFER_OPERATIONS_TWO_ALIGNMENT_FAILURES",
        "source_records": source_records,
        "source_read_passes": {"C1_current_UAS_LAZ": 1, "C2_exact_common_MVS_PLY": 1},
        "building_method_record_count": 6,
        "roofer_operation_count": 4,
        "pre_roofer_reference_alignment_failure_count": 2,
        "operation_ids": [row["operation_unit_id"] for row in jobs],
        "alignment_failure_ids": [row["operation_unit_id"] for row in failures],
        "oracle_diagnostic": True,
        "official_honest_stage3": False,
        "roofer_invocations_so_far": 0,
        "scientific_verdict": None,
    }
    write_new(output_root / "control/c1_c2_prepared_v1.json", canonical_json_bytes(body))
    return body


def record_terminal(output_root: Path, operation_unit_id: str, exit_code: int, runtime_seconds: int) -> dict[str, Any]:
    rows = [
        json.loads(line)
        for line in (output_root / "freeze/c1_c2_execution_units_v1.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    matches = [row for row in rows if row["operation_unit_id"] == operation_unit_id]
    if len(matches) != 1:
        raise RuntimeError(f"unknown operation unit: {operation_unit_id}")
    row = matches[0]
    work = output_root / row["work_directory"]
    terminal = work / "roofer_terminal_v1.json"
    if terminal.exists():
        raise RuntimeError(f"terminal already exists: {terminal}")
    outputs = sorted((work / "out").glob("*.city.jsonl")) if (work / "out").is_dir() else []
    status = "COMPLETED" if exit_code == 0 and len(outputs) == 1 else "FAILED"
    body = {
        "schema": "jointbuildgs.c1_c2_oracle_roofer_terminal.v1",
        "status": status,
        "operation_unit_id": operation_unit_id,
        "condition_id": row["condition_id"],
        "stable_id": row["stable_id"],
        "exit_code": int(exit_code),
        "runtime_seconds": int(runtime_seconds),
        "input": row["input"],
        "footprint": row["footprint"],
        "outputs": [file_record(path, output_root) for path in outputs],
        "oracle_diagnostic": True,
        "official_honest_stage3": False,
        "scientific_verdict": None,
    }
    write_new(terminal, canonical_json_bytes(body))
    if status != "COMPLETED":
        raise RuntimeError(f"Roofer operation failed: {operation_unit_id} exit={exit_code} outputs={len(outputs)}")
    return body


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="mode", required=True)
    sub.add_parser("preflight")
    prepare_parser = sub.add_parser("prepare")
    prepare_parser.add_argument("--output-root", type=Path, required=True)
    prepare_parser.add_argument("--c1", type=Path, required=True)
    prepare_parser.add_argument("--c2", type=Path, required=True)
    prepare_parser.add_argument("--lod2", type=Path, required=True)
    prepare_parser.add_argument("--hash-inputs", action="store_true")
    record_parser = sub.add_parser("record-terminal")
    record_parser.add_argument("--output-root", type=Path, required=True)
    record_parser.add_argument("--operation-unit-id", required=True)
    record_parser.add_argument("--exit-code", type=int, required=True)
    record_parser.add_argument("--runtime-seconds", type=int, required=True)
    args = parser.parse_args()
    if args.mode == "preflight":
        result = validate_config(require_activation=False)
    elif args.mode == "prepare":
        result = prepare(
            output_root=args.output_root,
            c1_path=args.c1,
            c2_path=args.c2,
            lod2_path=args.lod2,
            hash_inputs=args.hash_inputs,
        )
    else:
        result = record_terminal(args.output_root, args.operation_unit_id, args.exit_code, args.runtime_seconds)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
