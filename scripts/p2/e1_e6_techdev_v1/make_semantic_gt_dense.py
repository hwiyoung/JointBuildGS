from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import imageio.v2 as imageio
import laspy
import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import binary_dilation, distance_transform_edt
from scipy.spatial import cKDTree

from scripts.p2.e1_e6_techdev_v1.make_semantic_gt import COLORS, WORLD_SHIFT, pca, sha256
from src.stage2.dataloader import ColmapDataset


SCHEMA = "jointbuildgs.p2.e1_e6.semantic_gt_dense.v1"
CACHE_SCHEMA = "jointbuildgs.p2.e1_e6.semantic_surface_cache.v1"
SURFEL_RADIUS_M = 0.30
MAX_SCREEN_RADIUS_PX = 6
BOUNDARY_IGNORE_PX = 2
DEPTH_EDGE_M = 1.0


def atomic_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def build_surface_cache(classified_scan: Path, cache_root: Path) -> tuple[Path, Path, dict]:
    cache_root.mkdir(parents=True, exist_ok=True)
    points_path = cache_root / "points_local_f32.npy"
    labels_path = cache_root / "labels_u8.npy"
    receipt_path = cache_root / "receipt.json"
    source_sha256 = sha256(classified_scan)
    if points_path.is_file() and labels_path.is_file() and receipt_path.is_file():
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        if receipt.get("schema") == CACHE_SCHEMA and receipt.get("source_sha256") == source_sha256:
            return points_path, labels_path, receipt

    las = laspy.read(classified_scan)
    points_world = np.column_stack((las.x, las.y, las.z)).astype(np.float64)
    classification = np.asarray(las.classification)
    normals, curvature = pca(points_world)
    ground = classification == 2
    if not np.any(ground):
        raise RuntimeError("CSF classified scan has no class-2 ground points")
    ground_tree = cKDTree(points_world[ground, :2])
    _distance, ground_index = ground_tree.query(points_world[:, :2], k=1, workers=-1)
    ndsm = points_world[:, 2] - points_world[ground][ground_index, 2]
    labels = np.full(len(points_world), 4, dtype=np.uint8)
    labels[ground] = 3
    smooth = (~ground) & (curvature <= 0.05)
    labels[smooth & (np.abs(normals[:, 2]) < 0.30)] = 2
    labels[smooth & (np.abs(normals[:, 2]) > 0.70) & (ndsm > 2.0)] = 1
    labels[(~ground) & (curvature > 0.05)] = 4
    points_local = (points_world - WORLD_SHIFT).astype(np.float32)
    np.save(points_path, points_local, allow_pickle=False)
    np.save(labels_path, labels, allow_pickle=False)
    counts = {
        name: int(np.count_nonzero(labels == class_id))
        for class_id, name in ((1, "roof"), (2, "wall"), (3, "ground"), (4, "other"))
    }
    receipt = {
        "schema": CACHE_SCHEMA,
        "source": str(classified_scan),
        "source_sha256": source_sha256,
        "point_count": int(len(points_local)),
        "point_class_counts": counts,
        "pca_neighbors": 20,
        "roughness_curvature_threshold": 0.05,
        "roof_ndsm_threshold_m": 2.0,
        "scientific_verdict": None,
    }
    atomic_json(receipt_path, receipt)
    return points_path, labels_path, receipt


def project_centres(
    points_local: np.ndarray,
    point_labels: np.ndarray,
    sample: dict,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    intrinsic = sample["K"].numpy().astype(np.float64)
    world_to_camera = sample["w2c"].numpy().astype(np.float64)
    camera = points_local @ world_to_camera[:3, :3].T + world_to_camera[:3, 3]
    front = camera[:, 2] > 0.1
    homogeneous = camera @ intrinsic.T
    uv = np.zeros((len(points_local), 2), dtype=np.float64)
    uv[front] = homogeneous[front, :2] / homogeneous[front, 2:3]
    height, width = int(sample["height"]), int(sample["width"])
    inside = front & (uv[:, 0] >= 0) & (uv[:, 0] < width) & (uv[:, 1] >= 0) & (uv[:, 1] < height)
    selected = np.flatnonzero(inside)
    centre_label = np.zeros((height, width), dtype=np.uint8)
    centre_depth = np.full((height, width), np.inf, dtype=np.float32)
    centre_radius = np.zeros((height, width), dtype=np.uint8)
    if len(selected) == 0:
        return centre_label, centre_depth, centre_radius

    x = np.rint(uv[selected, 0]).astype(np.int32).clip(0, width - 1)
    y = np.rint(uv[selected, 1]).astype(np.int32).clip(0, height - 1)
    key = y.astype(np.int64) * width + x
    order = np.lexsort((camera[selected, 2], key))
    first = np.r_[True, key[order][1:] != key[order][:-1]]
    chosen = selected[order[first]]
    x = np.rint(uv[chosen, 0]).astype(np.int32).clip(0, width - 1)
    y = np.rint(uv[chosen, 1]).astype(np.int32).clip(0, height - 1)
    depth = camera[chosen, 2].astype(np.float32)
    focal = float(np.sqrt(intrinsic[0, 0] * intrinsic[1, 1]))
    radius = np.ceil(focal * SURFEL_RADIUS_M / np.maximum(depth, 0.1))
    radius = np.clip(radius, 1, MAX_SCREEN_RADIUS_PX).astype(np.uint8)
    centre_label[y, x] = point_labels[chosen]
    centre_depth[y, x] = depth
    centre_radius[y, x] = radius
    return centre_label, centre_depth, centre_radius


def dense_surfel_raster(
    centre_label: np.ndarray,
    centre_depth: np.ndarray,
    centre_radius: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, dict]:
    centre_valid = centre_label > 0
    if not np.any(centre_valid):
        return centre_label.copy(), np.zeros_like(centre_label), {
            "sparse_valid_pixels": 0,
            "dense_candidate_pixels": 0,
            "dense_valid_pixels": 0,
            "boundary_ignore_pixels": 0,
        }
    distance, nearest = distance_transform_edt(~centre_valid, return_indices=True)
    nearest_label = centre_label[nearest[0], nearest[1]]
    nearest_depth = centre_depth[nearest[0], nearest[1]]
    nearest_radius = centre_radius[nearest[0], nearest[1]]
    candidate = distance <= nearest_radius
    dense_label = np.where(candidate, nearest_label, 0).astype(np.uint8)
    dense_depth = np.where(candidate, nearest_depth, np.inf).astype(np.float32)

    transition = np.zeros_like(candidate)
    depth_edge = np.zeros_like(candidate)
    for dy, dx in ((0, 1), (1, 0), (1, 1), (1, -1)):
        y0 = slice(max(0, dy), dense_label.shape[0] + min(0, dy))
        y1 = slice(max(0, -dy), dense_label.shape[0] + min(0, -dy))
        x0 = slice(max(0, dx), dense_label.shape[1] + min(0, dx))
        x1 = slice(max(0, -dx), dense_label.shape[1] + min(0, -dx))
        valid_pair = candidate[y0, x0] & candidate[y1, x1]
        class_change = valid_pair & (dense_label[y0, x0] != dense_label[y1, x1])
        z_delta = np.zeros_like(dense_depth[y0, x0])
        np.subtract(dense_depth[y0, x0], dense_depth[y1, x1], out=z_delta, where=valid_pair)
        z_change = valid_pair & (np.abs(z_delta) > DEPTH_EDGE_M)
        transition[y0, x0] |= class_change
        transition[y1, x1] |= class_change
        depth_edge[y0, x0] |= z_change
        depth_edge[y1, x1] |= z_change
    boundary = binary_dilation(transition | depth_edge, iterations=BOUNDARY_IGNORE_PX)
    valid = candidate & ~boundary
    output = np.where(valid, dense_label, 0).astype(np.uint8)
    mask = np.where(valid, 255, 0).astype(np.uint8)
    stats = {
        "sparse_valid_pixels": int(np.count_nonzero(centre_valid)),
        "dense_candidate_pixels": int(np.count_nonzero(candidate)),
        "dense_valid_pixels": int(np.count_nonzero(valid)),
        "boundary_ignore_pixels": int(np.count_nonzero(candidate & boundary)),
    }
    return output, mask, stats


def overlay_image(rgb: np.ndarray, label: np.ndarray, mask: np.ndarray) -> Image.Image:
    base = (np.clip(rgb, 0, 1) * 255).astype(np.uint8)
    colorized = np.zeros_like(base)
    for class_id, color in COLORS.items():
        colorized[label == class_id] = color
    valid = mask > 0
    blended = base.copy()
    blended[valid] = np.rint(
        base[valid].astype(np.float32) * 0.35 + colorized[valid].astype(np.float32) * 0.65
    ).astype(np.uint8)
    image = Image.fromarray(blended, mode="RGB")
    draw = ImageDraw.Draw(image, "RGBA")
    draw.rounded_rectangle((12, 12, 178, 122), radius=6, fill=(0, 0, 0, 185))
    draw.text((22, 20), "dense semantic v1", fill=(255, 255, 255, 255))
    for row, (class_id, name) in enumerate(((1, "roof"), (2, "wall"), (3, "ground"), (4, "other"))):
        y = 42 + row * 19
        draw.rectangle((22, y, 34, y + 12), fill=(*COLORS[class_id], 255))
        draw.text((42, y - 1), name, fill=(255, 255, 255, 255))
    return image


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--classified-scan", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--view-indices", nargs="+", type=int)
    parser.add_argument("--source-voxel-m", type=float, default=0.25)
    parser.add_argument("--source-role", default="CURRENT_EVALUATION_SCAN_ONLY")
    args = parser.parse_args()
    artifact_root = args.artifact_root.resolve()
    output_root = args.output_root.resolve()
    labels_root = output_root / "labels"
    masks_root = output_root / "masks"
    overlays_root = output_root / "overlays"
    qa_root = output_root / "qa"
    for path in (labels_root, masks_root, overlays_root, qa_root):
        path.mkdir(parents=True, exist_ok=True)
    roles = json.loads((output_root.parent / "view_roles.json").read_text(encoding="utf-8"))
    all_eval_names = roles["eval_views"]
    if args.view_indices is None:
        eval_names = all_eval_names
    else:
        if any(index < 0 or index >= len(all_eval_names) for index in args.view_indices):
            raise ValueError(f"view index outside [0, {len(all_eval_names) - 1}]")
        eval_names = [all_eval_names[index] for index in args.view_indices]
    receipt_path = output_root / "receipt.json"
    if receipt_path.is_file() and all(
        len(list(path.glob("*.png"))) == len(eval_names)
        for path in (labels_root, masks_root, overlays_root)
    ):
        return 0

    points_path, point_labels_path, cache_receipt = build_surface_cache(
        args.classified_scan.resolve(), output_root / "surface_cache"
    )
    points_local = np.load(points_path, mmap_mode="r")
    point_labels = np.load(point_labels_path, mmap_mode="r")
    data_root = artifact_root / "phase-payloads/p0-audit/data/work/mvs/colmap_dense"
    dataset = ColmapDataset(
        data_root,
        downscale=1.0,
        load_depth=False,
        load_normal=False,
        load_semantic=False,
        visible_views=eval_names,
    )
    progress_path = output_root / "progress.json"
    progress = json.loads(progress_path.read_text(encoding="utf-8")) if progress_path.is_file() else {"views": {}}
    qa_indices = {0, len(dataset) // 2, len(dataset) - 1}
    for index, frame in enumerate(dataset.frames):
        stem = Path(frame.name).stem
        required = [labels_root / f"{stem}.png", masks_root / f"{stem}.png", overlays_root / f"{stem}.png"]
        if stem in progress["views"] and all(path.is_file() for path in required):
            if index in qa_indices:
                qa_path = qa_root / f"qa_{index:03d}_{stem}.png"
                if not qa_path.is_file():
                    qa_path.write_bytes(required[2].read_bytes())
            continue
        sample = dataset[index]
        centre_label, centre_depth, centre_radius = project_centres(points_local, point_labels, sample)
        dense_label, dense_mask, stats = dense_surfel_raster(centre_label, centre_depth, centre_radius)
        imageio.imwrite(required[0], dense_label)
        imageio.imwrite(required[1], dense_mask)
        overlay_image(sample["rgb"].numpy(), dense_label, dense_mask).save(required[2])
        stats.update({
            "view": frame.name,
            "height": int(sample["height"]),
            "width": int(sample["width"]),
            "dense_valid_fraction": float(np.count_nonzero(dense_mask) / dense_mask.size),
            "class_pixel_counts": {
                name: int(np.count_nonzero((dense_label == class_id) & (dense_mask > 0)))
                for class_id, name in ((1, "roof"), (2, "wall"), (3, "ground"), (4, "other"))
            },
        })
        progress["views"][stem] = stats
        atomic_json(progress_path, progress)
        if index in qa_indices:
            (qa_root / f"qa_{index:03d}_{stem}.png").write_bytes(required[2].read_bytes())
        print(f"[dense semantic] {index + 1}/{len(dataset)} {stem} valid={stats['dense_valid_fraction']:.4f}", flush=True)

    view_stats = [progress["views"][Path(frame.name).stem] for frame in dataset.frames]
    receipt = {
        "schema": SCHEMA,
        "source": {
            "path": str(args.classified_scan.resolve()),
            "sha256": cache_receipt["source_sha256"],
            "role": args.source_role,
        },
        "method": "PCA20_RULE_CLASSES_PLUS_ADAPTIVE_SCREEN_SURFEL_ZBUFFER",
        "surface_support": {
            "source_voxel_m": args.source_voxel_m,
            "surfel_radius_m": SURFEL_RADIUS_M,
            "max_screen_radius_px": MAX_SCREEN_RADIUS_PX,
            "boundary_ignore_px": BOUNDARY_IGNORE_PX,
            "depth_edge_m": DEPTH_EDGE_M,
        },
        "classes": {"1": "roof", "2": "wall", "3": "ground", "4": "other", "0": "invalid_ignore"},
        "held_out_view_count": len(dataset),
        "label_png_count": len(list(labels_root.glob("*.png"))),
        "mask_png_count": len(list(masks_root.glob("*.png"))),
        "overlay_png_count": len(list(overlays_root.glob("*.png"))),
        "qa_sheet_count": len(list(qa_root.glob("*.png"))),
        "mean_sparse_valid_fraction": float(np.mean([item["sparse_valid_pixels"] / (item["height"] * item["width"]) for item in view_stats])),
        "mean_dense_valid_fraction": float(np.mean([item["dense_valid_fraction"] for item in view_stats])),
        "view_stats": view_stats,
        "training_label_source": "SEPARATE_FUTURE_FOOTPRINT_PLUS_MVS_RULE_PATH_NOT_GENERATED_HERE",
        "evaluation_scan_used_for_training": False,
        "scientific_verdict": None,
    }
    atomic_json(receipt_path, receipt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
