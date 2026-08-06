from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import open3d as o3d


VOXEL_M = 0.40


def sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def cloud_values(path: Path) -> tuple[np.ndarray, np.ndarray | None]:
    cloud = o3d.io.read_point_cloud(str(path))
    points = np.asarray(cloud.points, dtype=np.float32)
    colours = np.asarray(cloud.colors, dtype=np.float32) if cloud.has_colors() else None
    if not len(points) or not np.isfinite(points).all():
        raise RuntimeError(f"invalid seed input: {path}")
    return points, colours


def voxel_codes(points: np.ndarray, origin: np.ndarray) -> np.ndarray:
    index = np.floor((points - origin) / VOXEL_M).astype(np.int64)
    if (index < 0).any() or (index >= 2**21).any():
        raise RuntimeError("voxel code range exceeded")
    return index[:, 0] | (index[:, 1] << 21) | (index[:, 2] << 42)


def dense_priority_union(
    dense_path: Path, prior_path: Path, output: Path, *, prior_voxel_m: float | None = None
) -> dict:
    dense, dense_colour = cloud_values(dense_path)
    prior, _prior_colour = cloud_values(prior_path)
    original_prior_count = len(prior)
    if prior_voxel_m is not None:
        prior_cloud = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(prior))
        prior = np.asarray(prior_cloud.voxel_down_sample(prior_voxel_m).points, dtype=np.float32)
    origin = np.minimum(dense.min(axis=0), prior.min(axis=0)) - 1.0
    dense_codes = np.unique(voxel_codes(dense, origin))
    prior_codes = voxel_codes(prior, origin)
    keep = ~np.isin(prior_codes, dense_codes, assume_unique=False)
    points = np.concatenate([dense, prior[keep]])
    cloud = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(points))
    if dense_colour is not None:
        prior_colour = np.full((int(keep.sum()), 3), 0.5, dtype=np.float32)
        cloud.colors = o3d.utility.Vector3dVector(np.concatenate([dense_colour, prior_colour]))
    if not o3d.io.write_point_cloud(str(output), cloud, write_ascii=False):
        raise RuntimeError(f"failed to write {output}")
    return {
        "dense_point_count": int(len(dense)),
        "prior_source_point_count": int(original_prior_count),
        "prior_downsample_voxel_m": prior_voxel_m,
        "prior_downsampled_point_count": int(len(prior)),
        "prior_duplicate_voxel_rejected": int((~keep).sum()),
        "output_point_count": int(len(points)),
        "output_sha256": sha256(output),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prep-root", type=Path, required=True)
    args = parser.parse_args()
    prep = args.prep_root.resolve()
    dense = prep / "seed_dense.ply"
    outputs = {
        "seed_dense_lidar.ply": (prep / "existing_als_synthetic_local_voxel030.ply", 0.75),
        "seed_dense_lod.ply": (prep / "lod_surface_samples_synthetic_local.ply", None),
    }
    receipt_path = prep / "seed_unions.receipt.json"
    if receipt_path.is_file() and all((prep / name).is_file() for name in outputs):
        return 0
    receipt = {
        "schema": "jointbuildgs.p2.e1_e6.seed_unions.v1",
        "voxel_size_m": VOXEL_M,
        "duplicate_policy": "DENSE_MVS_PRIORITY",
        "outputs": {},
        "scientific_verdict": None,
    }
    for name, (prior, prior_voxel_m) in outputs.items():
        output = prep / name
        receipt["outputs"][name] = dense_priority_union(
            dense, prior, output, prior_voxel_m=prior_voxel_m
        )
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
