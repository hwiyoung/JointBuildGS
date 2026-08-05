#!/usr/bin/env python3
"""Compare two OpenMVS XYZRGB binary PLY files without loading them fully."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


POINT_DTYPE = np.dtype(
    [
        ("x", "<f4"),
        ("y", "<f4"),
        ("z", "<f4"),
        ("red", "u1"),
        ("green", "u1"),
        ("blue", "u1"),
    ]
)


def load_ply(path: Path) -> tuple[np.memmap, dict[str, object]]:
    with path.open("rb") as stream:
        header_lines: list[str] = []
        while True:
            raw = stream.readline()
            if not raw:
                raise ValueError(f"missing end_header in {path}")
            line = raw.decode("ascii").rstrip("\r\n")
            header_lines.append(line)
            if line == "end_header":
                break
        offset = stream.tell()

    if header_lines[:2] != ["ply", "format binary_little_endian 1.0"]:
        raise ValueError(f"unsupported PLY format in {path}")
    vertex_lines = [line for line in header_lines if line.startswith("element vertex ")]
    if len(vertex_lines) != 1:
        raise ValueError(f"expected one vertex declaration in {path}")
    count = int(vertex_lines[0].split()[-1])
    expected_properties = [
        "property float32 x",
        "property float32 y",
        "property float32 z",
        "property uint8 red",
        "property uint8 green",
        "property uint8 blue",
    ]
    properties = [line for line in header_lines if line.startswith("property ")]
    if properties != expected_properties:
        raise ValueError(f"unsupported PLY properties in {path}: {properties}")
    expected_size = offset + count * POINT_DTYPE.itemsize
    actual_size = path.stat().st_size
    if actual_size != expected_size:
        raise ValueError(
            f"unexpected PLY size for {path}: expected {expected_size}, got {actual_size}"
        )
    points = np.memmap(path, mode="r", dtype=POINT_DTYPE, offset=offset, shape=(count,))
    return points, {
        "path": str(path.resolve()),
        "point_count": count,
        "header_bytes": offset,
        "point_bytes": POINT_DTYPE.itemsize,
        "file_bytes": actual_size,
    }


def mix_hash(points: np.ndarray) -> np.ndarray:
    x = points["x"].view("<u4").astype(np.uint64)
    y = points["y"].view("<u4").astype(np.uint64)
    z = points["z"].view("<u4").astype(np.uint64)
    color = (
        points["red"].astype(np.uint64)
        | (points["green"].astype(np.uint64) << np.uint64(8))
        | (points["blue"].astype(np.uint64) << np.uint64(16))
    )
    value = (
        x * np.uint64(0x9E3779B185EBCA87)
        ^ y * np.uint64(0xC2B2AE3D27D4EB4F)
        ^ z * np.uint64(0x165667B19E3779F9)
        ^ color * np.uint64(0x85EBCA77C2B2AE63)
    )
    value ^= value >> np.uint64(30)
    value *= np.uint64(0xBF58476D1CE4E5B9)
    value ^= value >> np.uint64(27)
    value *= np.uint64(0x94D049BB133111EB)
    value ^= value >> np.uint64(31)
    return value


def summarize(points: np.memmap, chunk_size: int) -> dict[str, object]:
    coordinate_min = np.full(3, np.inf, dtype=np.float64)
    coordinate_max = np.full(3, -np.inf, dtype=np.float64)
    coordinate_sum = np.zeros(3, dtype=np.float64)
    coordinate_sum_squares = np.zeros(3, dtype=np.float64)
    color_sum = np.zeros(3, dtype=np.uint64)
    finite_count = 0
    hash_sum = np.uint64(0)
    hash_xor = np.uint64(0)
    hash_square_sum = np.uint64(0)

    for start in range(0, len(points), chunk_size):
        chunk = points[start : start + chunk_size]
        xyz = np.column_stack((chunk["x"], chunk["y"], chunk["z"])).astype(np.float64)
        rgb = np.column_stack((chunk["red"], chunk["green"], chunk["blue"]))
        finite = np.isfinite(xyz).all(axis=1)
        finite_xyz = xyz[finite]
        finite_count += int(finite.sum())
        if len(finite_xyz):
            coordinate_min = np.minimum(coordinate_min, finite_xyz.min(axis=0))
            coordinate_max = np.maximum(coordinate_max, finite_xyz.max(axis=0))
            coordinate_sum += finite_xyz.sum(axis=0, dtype=np.float64)
            coordinate_sum_squares += np.square(finite_xyz).sum(axis=0, dtype=np.float64)
        color_sum += rgb.sum(axis=0, dtype=np.uint64)
        hashes = mix_hash(chunk)
        hash_sum += hashes.sum(dtype=np.uint64)
        hash_xor ^= np.bitwise_xor.reduce(hashes, initial=np.uint64(0))
        hash_square_sum += np.square(hashes, dtype=np.uint64).sum(dtype=np.uint64)

    coordinate_mean = coordinate_sum / finite_count
    coordinate_variance = coordinate_sum_squares / finite_count - np.square(coordinate_mean)
    return {
        "finite_point_count": finite_count,
        "coordinate_min": coordinate_min.tolist(),
        "coordinate_max": coordinate_max.tolist(),
        "coordinate_mean": coordinate_mean.tolist(),
        "coordinate_stddev": np.sqrt(np.maximum(coordinate_variance, 0.0)).tolist(),
        "color_mean": (color_sum.astype(np.float64) / len(points)).tolist(),
        "order_independent_point_hash": {
            "sum_u64_hex": f"{int(hash_sum):016x}",
            "xor_u64_hex": f"{int(hash_xor):016x}",
            "square_sum_u64_hex": f"{int(hash_square_sum):016x}",
        },
    }


def compare_aligned(
    source: np.memmap, recovered: np.memmap, chunk_size: int
) -> dict[str, object]:
    limit = min(len(source), len(recovered))
    exact_rows = 0
    exact_xyz_rows = 0
    first_row_mismatch: int | None = None
    squared_distance_sum = 0.0
    max_distance = 0.0

    for start in range(0, limit, chunk_size):
        stop = min(start + chunk_size, limit)
        left = source[start:stop]
        right = recovered[start:stop]
        row_equal = left == right
        exact_rows += int(row_equal.sum())
        if first_row_mismatch is None and not row_equal.all():
            first_row_mismatch = start + int(np.flatnonzero(~row_equal)[0])
        left_xyz = np.column_stack((left["x"], left["y"], left["z"])).astype(np.float64)
        right_xyz = np.column_stack((right["x"], right["y"], right["z"])).astype(np.float64)
        xyz_equal = np.equal(left_xyz, right_xyz).all(axis=1)
        exact_xyz_rows += int(xyz_equal.sum())
        distances = np.linalg.norm(left_xyz - right_xyz, axis=1)
        squared_distance_sum += float(np.square(distances).sum(dtype=np.float64))
        max_distance = max(max_distance, float(distances.max(initial=0.0)))

    return {
        "aligned_point_count": limit,
        "exact_aligned_xyzrgb_rows": exact_rows,
        "exact_aligned_xyz_rows": exact_xyz_rows,
        "first_aligned_row_mismatch": first_row_mismatch,
        "aligned_coordinate_rmse": (squared_distance_sum / limit) ** 0.5,
        "aligned_coordinate_max_distance": max_distance,
        "note": "Index-aligned distances are diagnostic only if point ordering is stable.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--recovered", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--chunk-size", type=int, default=1_000_000)
    args = parser.parse_args()

    source, source_metadata = load_ply(args.source)
    recovered, recovered_metadata = load_ply(args.recovered)
    report = {
        "schema": "jointbuildgs.mvs_dense_ply_comparison.v1",
        "source": {**source_metadata, **summarize(source, args.chunk_size)},
        "recovered": {**recovered_metadata, **summarize(recovered, args.chunk_size)},
        "comparison": {
            "point_count_delta": len(recovered) - len(source),
            "point_count_delta_fraction": (len(recovered) - len(source)) / len(source),
            **compare_aligned(source, recovered, args.chunk_size),
        },
        "scientific_verdict": None,
    }
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
