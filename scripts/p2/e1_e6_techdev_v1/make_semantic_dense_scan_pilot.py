from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import imageio.v2 as imageio
import laspy
import numpy as np
from PIL import Image, ImageDraw
from scipy.spatial import cKDTree

from scripts.p2.e1_e6_techdev_v1.make_semantic_gt import COLORS, WORLD_SHIFT, sha256
from scripts.p2.e1_e6_techdev_v1.make_semantic_gt_dense import dense_surfel_raster
from src.stage2.dataloader import ColmapDataset


SCHEMA = "jointbuildgs.p2.e1_e6.semantic_dense_scan_pilot.v1"
CROP = (690791.740, 691154.650, 5335864.050, 5336353.850)
CHUNK_POINTS = 1_000_000


def atomic_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def overlay(rgb: np.ndarray, label: np.ndarray, mask: np.ndarray) -> Image.Image:
    base = np.rint(np.clip(rgb, 0, 1) * 255).astype(np.uint8)
    colour = np.zeros_like(base)
    for class_id, value in COLORS.items():
        colour[label == class_id] = value
    valid = mask > 0
    base[valid] = np.rint(base[valid] * 0.35 + colour[valid] * 0.65).astype(np.uint8)
    image = Image.fromarray(base, mode="RGB")
    draw = ImageDraw.Draw(image, "RGBA")
    draw.rounded_rectangle((12, 12, 236, 132), radius=6, fill=(0, 0, 0, 190))
    draw.text((22, 20), "raw-scan semantic pilot", fill=(255, 255, 255, 255))
    for row, (class_id, name) in enumerate(((1, "roof"), (2, "wall"), (3, "ground"), (4, "other"))):
        y = 43 + row * 19
        draw.rectangle((22, y, 34, y + 12), fill=(*COLORS[class_id], 255))
        draw.text((42, y - 1), name, fill=(255, 255, 255, 255))
    return image


def update_zbuffer(
    points_local: np.ndarray,
    labels: np.ndarray,
    sample: dict,
    centre_label: np.ndarray,
    centre_depth: np.ndarray,
    centre_radius: np.ndarray,
) -> int:
    intrinsic = sample["K"].numpy().astype(np.float64)
    world_to_camera = sample["w2c"].numpy().astype(np.float64)
    camera = points_local @ world_to_camera[:3, :3].T + world_to_camera[:3, 3]
    front = camera[:, 2] > 0.1
    homogeneous = camera @ intrinsic.T
    uv = np.zeros((len(points_local), 2), dtype=np.float64)
    uv[front] = homogeneous[front, :2] / homogeneous[front, 2:3]
    height, width = centre_label.shape
    inside = front & (uv[:, 0] >= 0) & (uv[:, 0] < width) & (uv[:, 1] >= 0) & (uv[:, 1] < height)
    selected = np.flatnonzero(inside)
    if not len(selected):
        return 0
    x = np.rint(uv[selected, 0]).astype(np.int32).clip(0, width - 1)
    y = np.rint(uv[selected, 1]).astype(np.int32).clip(0, height - 1)
    key = y.astype(np.int64) * width + x
    order = np.lexsort((camera[selected, 2], key))
    first = np.r_[True, key[order][1:] != key[order][:-1]]
    chosen = selected[order[first]]
    x = np.rint(uv[chosen, 0]).astype(np.int32).clip(0, width - 1)
    y = np.rint(uv[chosen, 1]).astype(np.int32).clip(0, height - 1)
    depth = camera[chosen, 2].astype(np.float32)
    replace = depth < centre_depth[y, x]
    if np.any(replace):
        x = x[replace]
        y = y[replace]
        depth = depth[replace]
        chosen = chosen[replace]
        focal = float(np.sqrt(intrinsic[0, 0] * intrinsic[1, 1]))
        radius = np.ceil(focal * 0.30 / np.maximum(depth, 0.1))
        centre_label[y, x] = labels[chosen]
        centre_depth[y, x] = depth
        centre_radius[y, x] = np.clip(radius, 1, 6).astype(np.uint8)
    return int(len(selected))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--task-root", type=Path, required=True)
    parser.add_argument("--raw-scan", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--view-indices", nargs="+", type=int, default=[0, 58, 116])
    parser.add_argument("--anchor-root", type=Path)
    parser.add_argument("--label-transfer-max-distance-m", type=float, default=0.45)
    parser.add_argument("--source-role", default="CURRENT_EVALUATION_RAW_ULS_IMAGE_LABEL_PILOT_REQUIRES_HUMAN_REVIEW")
    parser.add_argument("--anchor-source-voxel-m", type=float, default=0.25)
    parser.add_argument(
        "--controlled-change",
        default="PROJECT_RAW_EVALUATION_ULS_AFTER_NEAREST_ANCHOR_LABEL_TRANSFER; KEEP_EXISTING_ZBUFFER_SURFEL_RULES",
    )
    args = parser.parse_args()

    artifact_root = args.artifact_root.resolve()
    task_root = args.task_root.resolve()
    output_root = args.output_root.resolve()
    labels_root = output_root / "labels"
    masks_root = output_root / "masks"
    overlays_root = output_root / "overlays"
    for path in (labels_root, masks_root, overlays_root):
        path.mkdir(parents=True, exist_ok=True)

    roles = json.loads((task_root / "prep/view_roles.json").read_text(encoding="utf-8"))
    all_eval_names = roles["eval_views"]
    view_names = [all_eval_names[index] for index in args.view_indices]
    receipt_path = output_root / "receipt.json"
    if receipt_path.is_file() and all(
        (root / f"{Path(name).stem}.png").is_file()
        for root in (labels_root, masks_root, overlays_root)
        for name in view_names
    ):
        return 0

    anchor_root = (
        args.anchor_root.resolve()
        if args.anchor_root is not None
        else task_root / "prep/semantic_gt_dense/surface_cache"
    )
    anchor_points = np.load(anchor_root / "points_local_f32.npy", mmap_mode="r")
    anchor_labels = np.load(anchor_root / "labels_u8.npy", mmap_mode="r")
    anchor_tree = cKDTree(anchor_points)
    data_root = artifact_root / "phase-payloads/p0-audit/data/work/mvs/colmap_dense"
    dataset = ColmapDataset(
        data_root,
        downscale=1.0,
        load_depth=False,
        load_normal=False,
        load_semantic=False,
        visible_views=view_names,
    )
    samples = [dataset[index] for index in range(len(dataset))]
    buffers = []
    for sample in samples:
        height, width = int(sample["height"]), int(sample["width"])
        buffers.append({
            "label": np.zeros((height, width), dtype=np.uint8),
            "depth": np.full((height, width), np.inf, dtype=np.float32),
            "radius": np.zeros((height, width), dtype=np.uint8),
            "projected_candidates": 0,
        })

    scanned = 0
    cropped = 0
    transferred = 0
    xmin, xmax, ymin, ymax = CROP
    with laspy.open(args.raw_scan.resolve()) as reader:
        source_point_count = int(reader.header.point_count)
        for chunk_index, chunk in enumerate(reader.chunk_iterator(CHUNK_POINTS), start=1):
            scanned += len(chunk)
            x = np.asarray(chunk.x)
            y = np.asarray(chunk.y)
            inside_crop = (x >= xmin) & (x <= xmax) & (y >= ymin) & (y <= ymax)
            if not np.any(inside_crop):
                continue
            points_local = np.column_stack((x[inside_crop], y[inside_crop], np.asarray(chunk.z)[inside_crop])) - WORLD_SHIFT
            cropped += len(points_local)
            distance, anchor_index = anchor_tree.query(points_local, k=1, workers=-1)
            valid = distance <= args.label_transfer_max_distance_m
            if not np.any(valid):
                continue
            points_local = points_local[valid]
            labels = np.asarray(anchor_labels[anchor_index[valid]], dtype=np.uint8)
            transferred += len(points_local)
            for sample, buffer in zip(samples, buffers):
                buffer["projected_candidates"] += update_zbuffer(
                    points_local,
                    labels,
                    sample,
                    buffer["label"],
                    buffer["depth"],
                    buffer["radius"],
                )
            if chunk_index % 10 == 0:
                print(
                    f"[raw semantic] scanned={scanned}/{source_point_count} "
                    f"cropped={cropped} transferred={transferred}",
                    flush=True,
                )

    view_stats = []
    for frame, sample, buffer in zip(dataset.frames, samples, buffers):
        stem = Path(frame.name).stem
        label, mask, stats = dense_surfel_raster(buffer["label"], buffer["depth"], buffer["radius"])
        imageio.imwrite(labels_root / f"{stem}.png", label)
        imageio.imwrite(masks_root / f"{stem}.png", mask)
        overlay(sample["rgb"].numpy(), label, mask).save(overlays_root / f"{stem}.png")
        stats.update({
            "view": frame.name,
            "projected_candidates_before_zbuffer": buffer["projected_candidates"],
            "raw_zbuffer_valid_pixels": int(np.count_nonzero(buffer["label"])),
            "output_valid_fraction": float(np.count_nonzero(mask) / mask.size),
        })
        view_stats.append(stats)
        print(f"[raw semantic] {stem} valid={stats['output_valid_fraction']:.4f}", flush=True)

    anchor_receipt = json.loads((anchor_root / "receipt.json").read_text(encoding="utf-8"))
    receipt = {
        "schema": SCHEMA,
        "role": args.source_role,
        "source": {
            "path": str(args.raw_scan.resolve()),
            "sha256": sha256(args.raw_scan.resolve()),
            "point_count": source_point_count,
            "crs_interpretation": "EPSG:25832_OVERRIDE_MATCHING_FROZEN_PIPELINE",
        },
        "semantic_anchor": {
            "path": str(anchor_root),
            "source_voxel_m": args.anchor_source_voxel_m,
            "point_count": anchor_receipt["point_count"],
            "receipt_sha256": sha256(anchor_root / "receipt.json"),
        },
        "controlled_change": args.controlled_change,
        "label_transfer_max_distance_m": args.label_transfer_max_distance_m,
        "crop_bounds_epsg25832": [xmin, xmax, ymin, ymax],
        "scanned_point_count": scanned,
        "cropped_point_count": cropped,
        "transferred_point_count": transferred,
        "view_indices": args.view_indices,
        "view_names": view_names,
        "view_stats": view_stats,
        "evaluation_only": True,
        "training_label_source": False,
        "human_review_complete": False,
        "scientific_verdict": None,
    }
    atomic_json(receipt_path, receipt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
