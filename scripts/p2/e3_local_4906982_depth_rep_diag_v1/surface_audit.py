#!/usr/bin/env python3
"""Compare frozen GS fused surfaces to the filtered OpenMVS seed.

This is evaluation-only.  It reads existing fused LAZ files and the previously
verified task-local MVS NPY; it does not render, train, fuse, or use LoD2.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import laspy
import numpy as np
import torch
from scipy.spatial import cKDTree
from shapely import contains_xy
from shapely.geometry import shape


SHIFT = np.asarray([690953.0, 5336071.0, 604.0], dtype=np.float64)
ARMS = ("EXPECTED", "MEDIAN")
STEPS = (7000, 12000, 15000, 20000)
NORMAL_K = 16
GRID_M = 1.0
ORDINARY_Z_MARGIN_M = 5.0


def stats(values: np.ndarray, prefix: str) -> dict[str, float | int | None]:
    finite = np.asarray(values, dtype=np.float64)
    finite = finite[np.isfinite(finite)]
    if not len(finite):
        return {f"{prefix}_count": 0, f"{prefix}_median": None, f"{prefix}_p95": None, f"{prefix}_p99": None, f"{prefix}_mean": None}
    return {
        f"{prefix}_count": int(len(finite)),
        f"{prefix}_median": float(np.quantile(finite, 0.5)),
        f"{prefix}_p95": float(np.quantile(finite, 0.95)),
        f"{prefix}_p99": float(np.quantile(finite, 0.99)),
        f"{prefix}_mean": float(np.mean(finite)),
    }


def estimate_normals(points: np.ndarray, k: int) -> np.ndarray:
    tree = cKDTree(points)
    _, index = tree.query(points, k=k, workers=-1)
    normals = np.empty_like(points)
    block = 4096
    for start in range(0, len(points), block):
        neighbors = points[index[start : start + block]]
        centered = neighbors - neighbors.mean(axis=1, keepdims=True)
        covariance = np.einsum("bni,bnj->bij", centered, centered) / float(k)
        _, vectors = np.linalg.eigh(covariance)
        normals[start : start + block] = vectors[:, :, 0]
    normals /= np.linalg.norm(normals, axis=1, keepdims=True).clip(1e-12)
    return normals


def grid_cells(points: np.ndarray, bounds: tuple[float, float, float, float]) -> set[tuple[int, int]]:
    x0, y0, _, _ = bounds
    ij = np.floor((points[:, :2] - np.asarray([x0, y0])) / GRID_M).astype(np.int64)
    return set(map(tuple, ij.tolist()))


def read_fused(path: Path) -> tuple[np.ndarray, np.ndarray | None]:
    cloud = laspy.read(path)
    points = np.column_stack([cloud.x, cloud.y, cloud.z]).astype(np.float64)
    names = set(cloud.point_format.dimension_names)
    normals = None
    if {"normal_x", "normal_y", "normal_z"}.issubset(names):
        normals = np.column_stack([cloud.normal_x, cloud.normal_y, cloud.normal_z]).astype(np.float64)
        normals /= np.linalg.norm(normals, axis=1, keepdims=True).clip(1e-12)
    return points, normals


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-root", type=Path, required=True)
    parser.add_argument("--mvs-npy", type=Path, required=True)
    parser.add_argument("--footprint", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-csv", type=Path, required=True)
    parser.add_argument("--arms", nargs="+", default=list(ARMS))
    parser.add_argument("--steps", nargs="+", type=int, default=list(STEPS))
    args = parser.parse_args()

    feature = json.loads(args.footprint.read_text())["features"][0]
    footprint = shape(feature["geometry"])
    mvs = np.load(args.mvs_npy).astype(np.float64) + SHIFT
    mvs = mvs[contains_xy(footprint, mvs[:, 0], mvs[:, 1])]
    if len(mvs) < NORMAL_K:
        raise RuntimeError("insufficient MVS reference points inside footprint")
    mvs_normals = estimate_normals(mvs, NORMAL_K)
    mvs_tree = cKDTree(mvs)
    mvs_cells = grid_cells(mvs, footprint.bounds)
    mvs_max_z = float(mvs[:, 2].max())

    rows: list[dict[str, object]] = []
    for arm in args.arms:
        for step in args.steps:
            checkpoint = torch.load(
                args.task_root / f"arms/{arm}/R1/ckpt/step_{step:06d}.pt",
                map_location="cpu",
                weights_only=False,
            )
            state = checkpoint["model"]["state_dict"]
            gaussian_xyz = state["means"].detach().cpu().numpy().astype(np.float64) + SHIFT
            gaussian_opacity = torch.sigmoid(state["opacities_raw"].detach().cpu()).numpy().reshape(-1)
            high_z = gaussian_xyz[:, 2] > 650.0
            high_z_inside = contains_xy(
                footprint, gaussian_xyz[high_z, 0], gaussian_xyz[high_z, 1]
            )
            path = args.task_root / f"arms/{arm}/R1/evaluation/step_{step:06d}/fusion/fused_surface.laz"
            points, normals = read_fused(path)
            inside = contains_xy(footprint, points[:, 0], points[:, 1])
            points = points[inside]
            normals = normals[inside] if normals is not None else None
            distance, nearest = mvs_tree.query(points, k=1, workers=-1)
            reference_normals = mvs_normals[nearest]
            delta = points - mvs[nearest]
            plane = np.abs(np.einsum("ni,ni->n", delta, reference_normals))
            angles = None
            if normals is not None:
                cosine = np.abs(np.einsum("ni,ni->n", normals, reference_normals)).clip(0.0, 1.0)
                angles = np.degrees(np.arccos(cosine))
            ordinary = points[:, 2] <= mvs_max_z + ORDINARY_Z_MARGIN_M
            roof = np.abs(reference_normals[:, 2]) >= 0.7
            wall = np.abs(reference_normals[:, 2]) <= 0.3
            fused_cells = grid_cells(points[ordinary], footprint.bounds)
            common = fused_cells & mvs_cells
            row: dict[str, object] = {
                "arm": arm,
                "replica": "R1",
                "completed_updates": step,
                "fused_inside_footprint_count": int(len(points)),
                "ordinary_surface_count": int(ordinary.sum()),
                "ordinary_z_max_definition_m": mvs_max_z + ORDINARY_Z_MARGIN_M,
                "mvs_inside_footprint_count": int(len(mvs)),
                "mvs_max_z_m": mvs_max_z,
                "gaussian_z_gt_650_count": int(high_z.sum()),
                "gaussian_z_gt_650_footprint_inside_count": int(high_z_inside.sum()),
                "gaussian_z_gt_650_footprint_outside_count": int(high_z.sum() - high_z_inside.sum()),
                "gaussian_z_gt_650_opacity_lt_0p1": int((high_z & (gaussian_opacity < 0.1)).sum()),
                "gaussian_z_gt_650_opacity_0p1_0p5": int((high_z & (gaussian_opacity >= 0.1) & (gaussian_opacity < 0.5)).sum()),
                "gaussian_z_gt_650_opacity_0p5_0p9": int((high_z & (gaussian_opacity >= 0.5) & (gaussian_opacity < 0.9)).sum()),
                "gaussian_z_gt_650_opacity_ge_0p9": int((high_z & (gaussian_opacity >= 0.9)).sum()),
                "ordinary_grid_coverage_of_mvs": len(common) / len(mvs_cells) if mvs_cells else None,
                "ordinary_grid_hole_fraction_vs_mvs": 1.0 - len(common) / len(mvs_cells) if mvs_cells else None,
                "ordinary_fused_cell_count": len(fused_cells),
                "mvs_cell_count": len(mvs_cells),
            }
            row.update(stats(distance[ordinary], "ordinary_point_to_point_m"))
            row.update(stats(plane[ordinary], "ordinary_point_to_plane_m"))
            row.update(stats(distance[ordinary & roof], "roof_point_to_point_m"))
            row.update(stats(plane[ordinary & roof], "roof_point_to_plane_m"))
            row.update(stats(distance[ordinary & wall], "wall_point_to_point_m"))
            row.update(stats(plane[ordinary & wall], "wall_point_to_plane_m"))
            if angles is not None:
                row.update(stats(angles[ordinary], "ordinary_normal_angle_deg"))
                row.update(stats(angles[ordinary & roof], "roof_normal_angle_deg"))
                row.update(stats(angles[ordinary & wall], "wall_normal_angle_deg"))
            rows.append(row)

    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.output_csv.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    body = {
        "schema": "jointbuildgs.p2.e3_local_4906982_depth_rep_diag_v1.mvs_surface_audit.v1",
        "reference": "verified filtered 0.40m OpenMVS building seed",
        "reference_is_independent_ground_truth": False,
        "ordinary_surface_definition": "inside shared footprint XY and Z <= filtered MVS seed max Z + 5m",
        "normal_estimator": {"method": "local PCA smallest eigenvector", "k": NORMAL_K, "sign_invariant_angle": True},
        "grid_size_m": GRID_M,
        "rows": rows,
        "scientific_verdict": None,
    }
    args.output_json.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"rows": len(rows), "mvs_points": len(mvs), "output": str(args.output_json)}, indent=2))


if __name__ == "__main__":
    main()
