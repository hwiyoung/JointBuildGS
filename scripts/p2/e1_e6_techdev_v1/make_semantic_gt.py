from __future__ import annotations

import argparse
import hashlib
import json
import random
from pathlib import Path

import imageio.v2 as imageio
import laspy
import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import binary_dilation
from scipy.spatial import cKDTree

from src.stage2.dataloader import ColmapDataset


WORLD_SHIFT = np.asarray([690953.0, 5336071.0, 604.0])
COLORS = {1: (255, 60, 60), 2: (70, 130, 255), 3: (80, 210, 90), 4: (255, 210, 60)}


def sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def pca(points: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    tree = cKDTree(points)
    normals = np.empty_like(points, dtype=np.float32)
    curvature = np.empty(len(points), dtype=np.float32)
    for start in range(0, len(points), 50_000):
        stop = min(start + 50_000, len(points))
        _distance, neighbors = tree.query(points[start:stop], k=20, workers=-1)
        local = points[neighbors]
        delta = local - local.mean(axis=1, keepdims=True)
        covariance = np.einsum("bni,bnj->bij", delta, delta) / 19.0
        values, vectors = np.linalg.eigh(covariance)
        normals[start:stop] = vectors[:, :, 0]
        curvature[start:stop] = values[:, 0] / np.maximum(values.sum(axis=1), 1.0e-12)
        print(f"[semantic PCA] {stop}/{len(points)}", flush=True)
    return normals, curvature


def project(points_local: np.ndarray, labels: np.ndarray, sample: dict) -> tuple[np.ndarray, np.ndarray]:
    k = sample["K"].numpy().astype(np.float64); w2c = sample["w2c"].numpy().astype(np.float64)
    camera = points_local @ w2c[:3, :3].T + w2c[:3, 3]
    front = camera[:, 2] > 0.1; uvw = camera @ k.T
    uv = np.zeros((len(points_local), 2), dtype=np.float64); uv[front] = uvw[front, :2] / uvw[front, 2:3]
    height, width = int(sample["height"]), int(sample["width"])
    inside = front & (uv[:, 0] >= 0) & (uv[:, 0] < width) & (uv[:, 1] >= 0) & (uv[:, 1] < height)
    selected = np.flatnonzero(inside)
    output = np.zeros((height, width), dtype=np.uint8); mask = np.zeros((height, width), dtype=np.uint8)
    if len(selected):
        x = np.rint(uv[selected, 0]).astype(np.int32).clip(0, width - 1); y = np.rint(uv[selected, 1]).astype(np.int32).clip(0, height - 1)
        key = y.astype(np.int64) * width + x; order = np.lexsort((camera[selected, 2], key)); first = np.r_[True, key[order][1:] != key[order][:-1]]; chosen = selected[order[first]]
        x = np.rint(uv[chosen, 0]).astype(np.int32).clip(0, width - 1); y = np.rint(uv[chosen, 1]).astype(np.int32).clip(0, height - 1)
        output[y, x] = labels[chosen]; mask[y, x] = 255
    return output, mask


def qa_sheet(rgb: np.ndarray, label: np.ndarray, mask: np.ndarray, seed: int, path: Path) -> None:
    image = Image.fromarray((np.clip(rgb, 0, 1) * 255).astype(np.uint8)).convert("RGBA")
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0)); draw = ImageDraw.Draw(overlay)
    y, x = np.nonzero(mask); indices = list(range(len(x))); random.Random(seed).shuffle(indices)
    for index in indices[:300]:
        colour = COLORS[int(label[y[index], x[index]])]
        draw.ellipse((int(x[index])-3, int(y[index])-3, int(x[index])+3, int(y[index])+3), fill=(*colour, 210))
    Image.alpha_composite(image, overlay).convert("RGB").save(path)


def colorize_labels(label: np.ndarray) -> np.ndarray:
    colorized = np.zeros((*label.shape, 3), dtype=np.uint8)
    for class_id, color in COLORS.items():
        colorized[label == class_id] = color
    return colorized


def ensure_colorized(labels_root: Path, colorized_root: Path) -> int:
    colorized_root.mkdir(parents=True, exist_ok=True)
    label_paths = sorted(labels_root.glob("*.png"))
    for label_path in label_paths:
        destination = colorized_root / label_path.name
        if destination.is_file():
            continue
        label = imageio.imread(label_path)
        imageio.imwrite(destination, colorize_labels(label))
    return len(list(colorized_root.glob("*.png")))


def semantic_overlay(rgb: np.ndarray, label: np.ndarray, mask: np.ndarray) -> Image.Image:
    base = (np.clip(rgb, 0, 1) * 255).astype(np.uint8)
    display_label = np.zeros_like(label)
    for class_id in COLORS:
        expanded = binary_dilation(label == class_id, iterations=1)
        display_label[(display_label == 0) & expanded] = class_id
    display_mask = display_label > 0
    colorized = colorize_labels(display_label)
    blended = base.copy()
    blended[display_mask] = np.rint(
        base[display_mask].astype(np.float32) * 0.35
        + colorized[display_mask].astype(np.float32) * 0.65
    ).astype(np.uint8)
    image = Image.fromarray(blended, mode="RGB")
    draw = ImageDraw.Draw(image, "RGBA")
    legend = ((1, "roof"), (2, "wall"), (3, "ground"), (4, "other"))
    draw.rounded_rectangle((12, 12, 124, 100), radius=6, fill=(0, 0, 0, 180))
    for row, (class_id, name) in enumerate(legend):
        y = 22 + row * 19
        draw.rectangle((22, y, 34, y + 12), fill=(*COLORS[class_id], 255))
        draw.text((42, y - 1), name, fill=(255, 255, 255, 255))
    return image


def ensure_overlays(
    artifact_root: Path,
    eval_names: list[str],
    labels_root: Path,
    masks_root: Path,
    overlays_root: Path,
) -> int:
    overlays_root.mkdir(parents=True, exist_ok=True)
    data_root = artifact_root / "phase-payloads/p0-audit/data/work/mvs/colmap_dense"
    dataset = ColmapDataset(
        data_root,
        downscale=1.0,
        load_depth=False,
        load_normal=False,
        load_semantic=False,
        visible_views=eval_names,
    )
    for index, frame in enumerate(dataset.frames):
        stem = Path(frame.name).stem
        destination = overlays_root / f"{stem}.png"
        if destination.is_file():
            continue
        sample = dataset[index]
        label = imageio.imread(labels_root / f"{stem}.png")
        mask = imageio.imread(masks_root / f"{stem}.png")
        semantic_overlay(sample["rgb"].numpy(), label, mask).save(destination)
    return len(list(overlays_root.glob("*.png")))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--classified-scan", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    output = args.output_root.resolve(); labels_root = output / "labels"; masks_root = output / "masks"; qa_root = output / "qa"; colorized_root = output / "colorized"; overlays_root = output / "overlays"
    receipt_path = output / "receipt.json"
    roles_path = output.parent / "view_roles.json"
    roles = json.loads(roles_path.read_text(encoding="utf-8")); eval_names = roles["eval_views"]
    if receipt_path.is_file() and len(list(labels_root.glob("*.png"))) == len(eval_names) and len(list(masks_root.glob("*.png"))) == len(eval_names):
        colorized_count = ensure_colorized(labels_root, colorized_root)
        overlay_count = ensure_overlays(args.artifact_root, eval_names, labels_root, masks_root, overlays_root)
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt["colorized_png_count"] = colorized_count
        receipt["colorized_palette_rgb"] = {str(key): list(value) for key, value in COLORS.items()}
        receipt["overlay_png_count"] = overlay_count
        receipt["overlay_alpha_semantic"] = 0.65
        receipt["overlay_display_dilation_pixels"] = 1
        receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
        return 0
    las = laspy.read(args.classified_scan)
    points_world = np.column_stack((las.x, las.y, las.z)).astype(np.float64)
    classification = np.asarray(las.classification)
    normals, curvature = pca(points_world)
    ground = classification == 2
    ground_tree = cKDTree(points_world[ground, :2]); _distance, ground_index = ground_tree.query(points_world[:, :2], k=1, workers=-1)
    ndsm = points_world[:, 2] - points_world[ground][ground_index, 2]
    labels = np.full(len(points_world), 4, dtype=np.uint8)
    labels[ground] = 3
    smooth = (~ground) & (curvature <= 0.05)
    labels[smooth & (np.abs(normals[:, 2]) < 0.30)] = 2
    labels[smooth & (np.abs(normals[:, 2]) > 0.70) & (ndsm > 2.0)] = 1
    labels[(~ground) & (curvature > 0.05)] = 4
    points_local = points_world - WORLD_SHIFT
    data_root = args.artifact_root / "phase-payloads/p0-audit/data/work/mvs/colmap_dense"
    dataset = ColmapDataset(data_root, downscale=1.0, load_depth=False, load_normal=False, load_semantic=False, visible_views=eval_names)
    labels_root.mkdir(parents=True, exist_ok=True); masks_root.mkdir(parents=True, exist_ok=True); qa_root.mkdir(parents=True, exist_ok=True); colorized_root.mkdir(parents=True, exist_ok=True); overlays_root.mkdir(parents=True, exist_ok=True)
    qa_indices = {0, len(dataset)//2, len(dataset)-1}
    valid_total = 0
    for index, frame in enumerate(dataset.frames):
        sample = dataset[index]; projected, mask = project(points_local, labels, sample); stem = Path(frame.name).stem
        imageio.imwrite(labels_root / f"{stem}.png", projected); imageio.imwrite(masks_root / f"{stem}.png", mask); imageio.imwrite(colorized_root / f"{stem}.png", colorize_labels(projected)); valid_total += int((mask > 0).sum())
        if index in qa_indices:
            qa_sheet(sample["rgb"].numpy(), projected, mask, 20260806 + index, qa_root / f"qa_{index:03d}_{stem}.png")
        if (index + 1) % 20 == 0: print(f"[semantic projection] {index + 1}/{len(dataset)}", flush=True)
    counts = {name: int((labels == value).sum()) for value, name in ((1,"roof"),(2,"wall"),(3,"ground"),(4,"other"))}
    receipt = {
        "schema": "jointbuildgs.p2.e1_e6.semantic_gt.v1",
        "source": {"path": str(args.classified_scan), "sha256": sha256(args.classified_scan), "role": "CURRENT_EVALUATION_SCAN_ONLY"},
        "classes": {"1":"roof","2":"wall","3":"ground","4":"other"},
        "ground_filter": "PDAL_CSF",
        "pca_neighbors": 20,
        "roughness_curvature_threshold": 0.05,
        "roof_ndsm_threshold_m": 2.0,
        "point_class_counts": counts,
        "held_out_view_count": len(dataset),
        "label_png_count": len(list(labels_root.glob("*.png"))),
        "mask_png_count": len(list(masks_root.glob("*.png"))),
        "colorized_png_count": len(list(colorized_root.glob("*.png"))),
        "colorized_palette_rgb": {str(key): list(value) for key, value in COLORS.items()},
        "overlay_png_count": ensure_overlays(args.artifact_root, eval_names, labels_root, masks_root, overlays_root),
        "overlay_alpha_semantic": 0.65,
        "overlay_display_dilation_pixels": 1,
        "total_valid_projected_pixels": valid_total,
        "qa_sheet_count": len(list(qa_root.glob("*.png"))),
        "training_label_source": "SEPARATE_FUTURE_FOOTPRINT_PLUS_MVS_RULE_PATH_NOT_GENERATED_HERE",
        "evaluation_scan_used_for_training": False,
        "scientific_verdict": None,
    }
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
