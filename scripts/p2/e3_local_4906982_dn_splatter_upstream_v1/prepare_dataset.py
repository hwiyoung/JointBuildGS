#!/usr/bin/env python3
"""Create a deterministic Nerfstudio adapter for the fixed 4906982 crop.

The adapter reads, but never rewrites, the existing crop, cameras, roles,
sparse seed, and COLMAP geometric depth.  Derived NPY/PLY/JSON files are owned
by the new upstream-DN artifact namespace.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

import numpy as np
import yaml

from src.stage2.colmap_io import (
    read_array,
    read_cameras_bin,
    read_images_bin,
    read_points3d_bin,
)


OPENGL_CAMERA_AXES = np.diag([1.0, -1.0, -1.0, 1.0])


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def atomic_bytes(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(value)
    if path.exists() and path.read_bytes() != value:
        raise RuntimeError(f"existing derived file drift: {path}")
    if path.exists():
        temporary.unlink()
    else:
        os.replace(temporary, path)


def atomic_json(path: Path, body: object) -> None:
    atomic_bytes(path, (json.dumps(body, indent=2, sort_keys=True) + "\n").encode())


def save_npy(path: Path, value: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("wb") as stream:
        np.save(stream, value, allow_pickle=False)
    if path.exists() and digest(path) != digest(temporary):
        raise RuntimeError(f"existing depth adapter drift: {path}")
    if path.exists():
        temporary.unlink()
    else:
        os.replace(temporary, path)


def ply_bytes(points: np.ndarray) -> bytes:
    header = (
        "ply\nformat ascii 1.0\n"
        f"element vertex {len(points)}\n"
        "property float x\nproperty float y\nproperty float z\n"
        "property uchar red\nproperty uchar green\nproperty uchar blue\n"
        "end_header\n"
    )
    lines = [
        f"{row[0]:.9g} {row[1]:.9g} {row[2]:.9g} {int(row[3])} {int(row[4])} {int(row[5])}\n"
        for row in points
    ]
    return header.encode() + "".join(lines).encode()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--crop", type=Path, required=True)
    parser.add_argument("--roles", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--container-crop", type=Path, required=True)
    parser.add_argument("--container-output", type=Path, required=True)
    args = parser.parse_args()

    roles = yaml.safe_load(args.roles.read_text())
    visible = list(roles["visible_views"])
    train = list(roles["train_views"])
    held_out = list(roles["eval_views"])
    if len(visible) != 55 or len(train) != 47 or len(held_out) != 8:
        raise RuntimeError("fixed 55/47/8 role count drift")
    if set(train) & set(held_out) or set(train) | set(held_out) != set(visible):
        raise RuntimeError("fixed view role membership drift")

    sparse = args.crop / "sparse/0"
    cameras = read_cameras_bin(sparse / "cameras.bin")
    images = read_images_bin(sparse / "images.bin")
    by_name = {value.name: value for value in images.values()}
    if set(by_name) != set(visible):
        raise RuntimeError("COLMAP image membership differs from fixed visible views")

    frames = []
    depth_records = {}
    for name in visible:
        image = by_name[name]
        camera = cameras[image.camera_id]
        source_depth = args.crop / "stereo/depth_maps" / f"{name}.geometric.bin"
        raw = read_array(source_depth).astype(np.float32)
        valid = np.isfinite(raw) & (raw > 0.0)
        adapted = np.where(valid, raw, 0.0).astype(np.float32)
        depth_path = args.output / "depths" / f"{Path(name).stem}.npy"
        save_npy(depth_path, adapted)

        c2w_cv = np.linalg.inv(image.world_to_camera())
        c2w_gl = c2w_cv @ OPENGL_CAMERA_AXES
        K = camera.K()
        frame = {
            "file_path": str(args.container_crop / "images" / name),
            "depth_file_path": str(args.container_output / "depths" / f"{Path(name).stem}.npy"),
            "transform_matrix": c2w_gl.tolist(),
            "fl_x": float(K[0, 0]),
            "fl_y": float(K[1, 1]),
            "cx": float(K[0, 2]),
            "cy": float(K[1, 2]),
            "w": int(camera.width),
            "h": int(camera.height),
            "distortion_params": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        }
        frames.append(frame)
        depth_records[name] = {
            "source_sha256": digest(source_depth),
            "adapted_sha256": digest(depth_path),
            "shape": list(adapted.shape),
            "valid_count": int(valid.sum()),
            "valid_fraction": float(valid.mean()),
            "valid_min_m": float(raw[valid].min()),
            "valid_median_m": float(np.median(raw[valid])),
            "valid_max_m": float(raw[valid].max()),
        }

    points = read_points3d_bin(sparse / "points3D.bin")
    ply = args.output / "sparse_pc.ply"
    atomic_bytes(ply, ply_bytes(points))
    image_paths = {name: str(args.container_crop / "images" / name) for name in visible}
    transforms = {
        "camera_model": "OPENCV",
        "orientation_override": "none",
        "frames": frames,
        "train_filenames": [image_paths[name] for name in train],
        "val_filenames": [image_paths[name] for name in held_out],
        "test_filenames": [image_paths[name] for name in held_out],
        "ply_file_path": "sparse_pc.ply",
    }
    atomic_json(args.output / "transforms.json", transforms)

    inputs = {
        "schema": "jointbuildgs.p2.e3_local_4906982_dn_splatter_upstream_v1.dataset_receipt.v1",
        "crop": str(args.crop),
        "view_roles": str(args.roles),
        "view_roles_sha256": digest(args.roles),
        "camera_sha256": digest(sparse / "cameras.bin"),
        "images_bin_sha256": digest(sparse / "images.bin"),
        "sparse_points_sha256": digest(sparse / "points3D.bin"),
        "sparse_ply_sha256": digest(ply),
        "transforms_sha256": digest(args.output / "transforms.json"),
        "view_counts": {"visible": len(visible), "train": len(train), "held_out": len(held_out)},
        "depth": depth_records,
        "coordinate_transform": "camera OpenCV c2w right-multiplied by diag(1,-1,-1,1); world and sparse XYZ unchanged",
        "scientific_verdict": None,
    }
    atomic_json(args.output.parent / "dataset_adapter_receipt.json", inputs)
    print(json.dumps({"views": len(frames), "points": len(points), "output": str(args.output)}, indent=2))


if __name__ == "__main__":
    main()
