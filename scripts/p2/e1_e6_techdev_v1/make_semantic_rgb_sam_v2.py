from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import imageio.v2 as imageio
import numpy as np
import torch
from PIL import Image, ImageDraw
from scipy.ndimage import binary_closing, binary_dilation, label as connected_components
from skimage.segmentation import slic

from scripts.p2.e1_e6_techdev_v1.make_semantic_gt import COLORS
from src.stage2.dataloader import ColmapDataset


SCHEMA = "jointbuildgs.p2.e1_e6.semantic_rgb_sam_pseudogt.v2"
SLIC_SEGMENTS = 3000
SLIC_COMPACTNESS = 12.0
SLIC_MIN_SEEDS = 16
SLIC_MIN_SEED_FRACTION = 0.08
SLIC_MIN_PURITY = 0.98
SAM_CLASSES = (1, 2, 4)
SAM_MIN_COMPONENT_PIXELS = 200
SAM_MAX_COMPONENTS_PER_CLASS = 10
SAM_MIN_SUPPORT_PIXELS = 100
SAM_MIN_SEED_PURITY = 0.97
SAM_MIN_COMPONENT_RECALL = 0.65
SAM_MIN_PREDICTED_IOU = 0.75
SAM_BOX_PADDING_PX = 10


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def slic_expand(rgb: np.ndarray, seed_label: np.ndarray, seed_valid: np.ndarray) -> tuple[np.ndarray, dict]:
    segments = slic(
        rgb,
        n_segments=SLIC_SEGMENTS,
        compactness=SLIC_COMPACTNESS,
        sigma=1.0,
        start_label=0,
        channel_axis=-1,
    )
    segment_count = int(segments.max()) + 1
    total = np.bincount(segments.ravel(), minlength=segment_count)
    class_counts = np.zeros((5, segment_count), dtype=np.int64)
    for class_id in range(1, 5):
        selected = seed_valid & (seed_label == class_id)
        class_counts[class_id] = np.bincount(segments[selected], minlength=segment_count)
    seed_count = class_counts.sum(axis=0)
    winner = class_counts.argmax(axis=0).astype(np.uint8)
    winner_count = class_counts[winner, np.arange(segment_count)]
    purity = np.divide(winner_count, seed_count, out=np.zeros_like(seed_count, dtype=np.float64), where=seed_count > 0)
    seed_fraction = np.divide(seed_count, total, out=np.zeros_like(seed_count, dtype=np.float64), where=total > 0)
    accepted = (
        (seed_count >= SLIC_MIN_SEEDS)
        & (seed_fraction >= SLIC_MIN_SEED_FRACTION)
        & (purity >= SLIC_MIN_PURITY)
    )
    assignment = np.where(accepted, winner, 0).astype(np.uint8)
    expanded = assignment[segments]
    return expanded, {
        "segment_count": segment_count,
        "accepted_segment_count": int(np.count_nonzero(accepted)),
    }


def prompt_points(component: np.ndarray, other_seed: np.ndarray, box: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    positive_yx = np.argwhere(component)
    positive_indices = np.linspace(0, len(positive_yx) - 1, min(6, len(positive_yx)), dtype=np.int64)
    positive = positive_yx[positive_indices][:, ::-1]
    x0, y0, x1, y1 = box.astype(np.int32)
    negative_yx = np.argwhere(other_seed[y0 : y1 + 1, x0 : x1 + 1])
    if len(negative_yx):
        negative_indices = np.linspace(0, len(negative_yx) - 1, min(12, len(negative_yx)), dtype=np.int64)
        negative = negative_yx[negative_indices]
        negative[:, 0] += y0
        negative[:, 1] += x0
        negative = negative[:, ::-1]
        coordinates = np.concatenate((positive, negative)).astype(np.float32)
        labels = np.concatenate((np.ones(len(positive)), np.zeros(len(negative)))).astype(np.int32)
    else:
        coordinates = positive.astype(np.float32)
        labels = np.ones(len(positive), dtype=np.int32)
    return coordinates, labels


def sam_expand(predictor, seed_label: np.ndarray, seed_valid: np.ndarray) -> tuple[np.ndarray, dict]:
    height, width = seed_label.shape
    assignments = np.zeros_like(seed_label)
    scores = np.zeros(seed_label.shape, dtype=np.float32)
    attempted = 0
    accepted = 0
    accepted_by_class = {str(class_id): 0 for class_id in SAM_CLASSES}
    for class_id in SAM_CLASSES:
        class_seed = seed_valid & (seed_label == class_id)
        closed = binary_closing(class_seed, iterations=1)
        components, component_count = connected_components(closed)
        ranked = []
        for component_id in range(1, component_count + 1):
            area = int(np.count_nonzero(components == component_id))
            if area >= SAM_MIN_COMPONENT_PIXELS:
                ranked.append((area, component_id))
        for _area, component_id in sorted(ranked, reverse=True)[:SAM_MAX_COMPONENTS_PER_CLASS]:
            component = components == component_id
            y, x = np.nonzero(component)
            x0 = max(0, int(x.min()) - SAM_BOX_PADDING_PX)
            y0 = max(0, int(y.min()) - SAM_BOX_PADDING_PX)
            x1 = min(width - 1, int(x.max()) + SAM_BOX_PADDING_PX)
            y1 = min(height - 1, int(y.max()) + SAM_BOX_PADDING_PX)
            box = np.asarray([x0, y0, x1, y1], dtype=np.float32)
            points, point_labels = prompt_points(component, seed_valid & (seed_label != class_id), box)
            masks, predicted_iou, _logits = predictor.predict(
                point_coords=points,
                point_labels=point_labels,
                box=box,
                multimask_output=True,
            )
            attempted += 1
            best = None
            for mask, model_score in zip(masks, predicted_iou):
                valid_inside = seed_valid & mask
                same_inside = valid_inside & (seed_label == class_id)
                support = int(np.count_nonzero(same_inside))
                purity = support / max(1, int(np.count_nonzero(valid_inside)))
                recall = int(np.count_nonzero(mask & component)) / max(1, int(np.count_nonzero(component)))
                composite = float(model_score) * purity * recall
                candidate = (composite, mask, support, purity, recall, float(model_score))
                if best is None or candidate[0] > best[0]:
                    best = candidate
            assert best is not None
            composite, mask, support, purity, recall, model_score = best
            if (
                support >= SAM_MIN_SUPPORT_PIXELS
                and purity >= SAM_MIN_SEED_PURITY
                and recall >= SAM_MIN_COMPONENT_RECALL
                and model_score >= SAM_MIN_PREDICTED_IOU
            ):
                replace = mask & (composite > scores)
                assignments[replace] = class_id
                scores[replace] = composite
                accepted += 1
                accepted_by_class[str(class_id)] += 1
    return assignments, {
        "attempted_prompt_count": attempted,
        "accepted_mask_count": accepted,
        "accepted_masks_by_class": accepted_by_class,
    }


def preserve_uncertain_boundaries(label: np.ndarray, original_valid: np.ndarray) -> np.ndarray:
    transition = np.zeros_like(original_valid)
    valid = label > 0
    for dy, dx in ((0, 1), (1, 0)):
        y0 = slice(dy, label.shape[0])
        y1 = slice(0, label.shape[0] - dy) if dy else slice(0, label.shape[0])
        x0 = slice(dx, label.shape[1])
        x1 = slice(0, label.shape[1] - dx) if dx else slice(0, label.shape[1])
        pair = valid[y0, x0] & valid[y1, x1] & (label[y0, x0] != label[y1, x1])
        transition[y0, x0] |= pair
        transition[y1, x1] |= pair
    uncertain = binary_dilation(transition, iterations=1) & ~original_valid
    return np.where(uncertain, 0, label).astype(np.uint8)


def overlay(rgb: np.ndarray, label: np.ndarray, original_valid: np.ndarray) -> Image.Image:
    colorized = np.zeros_like(rgb)
    for class_id, color in COLORS.items():
        colorized[label == class_id] = color
    valid = label > 0
    blended = rgb.copy()
    blended[valid] = np.rint(
        rgb[valid].astype(np.float32) * 0.35 + colorized[valid].astype(np.float32) * 0.65
    ).astype(np.uint8)
    grown = valid & ~original_valid
    edge = binary_dilation(grown, iterations=1) & ~grown
    blended[edge] = np.asarray([255, 255, 255], dtype=np.uint8)
    image = Image.fromarray(blended, mode="RGB")
    draw = ImageDraw.Draw(image, "RGBA")
    draw.rounded_rectangle((12, 12, 220, 132), radius=6, fill=(0, 0, 0, 190))
    draw.text((22, 20), "RGB/SAM pseudo-GT v2", fill=(255, 255, 255, 255))
    for row, (class_id, name) in enumerate(((1, "roof"), (2, "wall"), (3, "ground"), (4, "other"))):
        y = 43 + row * 19
        draw.rectangle((22, y, 34, y + 12), fill=(*COLORS[class_id], 255))
        draw.text((42, y - 1), name, fill=(255, 255, 255, 255))
    draw.text((22, 120), "white edge = grown region", fill=(255, 255, 255, 255))
    return image


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--task-root", type=Path, required=True)
    parser.add_argument("--sam-source", type=Path, required=True)
    parser.add_argument("--sam-checkpoint", type=Path, required=True)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--view-limit", type=int, default=0)
    parser.add_argument("--dense-root", type=Path)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--view-names", nargs="*")
    args = parser.parse_args()
    artifacts = args.artifact_root.resolve()
    task = args.task_root.resolve()
    dense_root = args.dense_root.resolve() if args.dense_root else task / "prep/semantic_gt_dense"
    output_root = args.output_root.resolve() if args.output_root else task / "prep/semantic_gt_rgb_sam_v2"
    labels_root = output_root / "labels"
    masks_root = output_root / "masks"
    overlays_root = output_root / "overlays"
    qa_root = output_root / "qa"
    for path in (labels_root, masks_root, overlays_root, qa_root):
        path.mkdir(parents=True, exist_ok=True)

    roles = json.loads((task / "prep/view_roles.json").read_text(encoding="utf-8"))
    eval_names = args.view_names or roles["eval_views"]
    if args.view_limit:
        eval_names = eval_names[: args.view_limit]
    receipt_path = output_root / "receipt.json"
    if receipt_path.is_file() and all(
        len(list(path.glob("*.png"))) == len(eval_names)
        for path in (labels_root, masks_root, overlays_root)
    ):
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        if receipt.get("schema") == SCHEMA and receipt.get("view_count") == len(eval_names):
            return 0

    sam_source = args.sam_source.resolve()
    checkpoint = args.sam_checkpoint.resolve()
    if not (sam_source / "segment_anything").is_dir() or not checkpoint.is_file():
        raise FileNotFoundError("SAM source or checkpoint missing")
    revision = subprocess.check_output(["git", "-C", str(sam_source), "rev-parse", "HEAD"], text=True).strip()
    sys.path.insert(0, str(sam_source))
    from segment_anything import SamPredictor, sam_model_registry  # noqa: E402

    if args.device.startswith("cuda") and not torch.cuda.is_available():
        raise RuntimeError("CUDA requested but unavailable")
    model = sam_model_registry["vit_b"](checkpoint=str(checkpoint))
    model.to(device=args.device)
    model.eval()
    predictor = SamPredictor(model)
    data_root = artifacts / "phase-payloads/p0-audit/data/work/mvs/colmap_dense"
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
        seed_label = imageio.imread(dense_root / "labels" / f"{stem}.png").astype(np.uint8)
        seed_mask = imageio.imread(dense_root / "masks" / f"{stem}.png") > 0
        sample = dataset[index]
        rgb = np.rint(np.clip(sample["rgb"].numpy(), 0, 1) * 255).astype(np.uint8)
        slic_label, slic_stats = slic_expand(rgb, seed_label, seed_mask)
        output = seed_label.copy()
        slic_fill = (~seed_mask) & (slic_label > 0)
        output[slic_fill] = slic_label[slic_fill]
        predictor.set_image(rgb)
        sam_label, sam_stats = sam_expand(predictor, seed_label, seed_mask)
        sam_fill = (output == 0) & (sam_label > 0)
        output[sam_fill] = sam_label[sam_fill]
        output = preserve_uncertain_boundaries(output, seed_mask)
        valid = output > 0
        imageio.imwrite(required[0], output)
        imageio.imwrite(required[1], np.where(valid, 255, 0).astype(np.uint8))
        overlay(rgb, output, seed_mask).save(required[2])
        stats = {
            "view": frame.name,
            "height": int(output.shape[0]),
            "width": int(output.shape[1]),
            "seed_valid_fraction": float(np.count_nonzero(seed_mask) / seed_mask.size),
            "output_valid_fraction": float(np.count_nonzero(valid) / valid.size),
            "slic_added_pixels": int(np.count_nonzero(slic_fill)),
            "sam_added_pixels": int(np.count_nonzero(sam_fill)),
            **slic_stats,
            **sam_stats,
        }
        progress["views"][stem] = stats
        atomic_json(progress_path, progress)
        if index in qa_indices:
            (qa_root / f"qa_{index:03d}_{stem}.png").write_bytes(required[2].read_bytes())
        print(
            f"[semantic RGB/SAM] {index + 1}/{len(dataset)} {stem} "
            f"valid={stats['output_valid_fraction']:.4f} sam={stats['accepted_mask_count']}",
            flush=True,
        )

    view_stats = [progress["views"][Path(frame.name).stem] for frame in dataset.frames]
    receipt = {
        "schema": SCHEMA,
        "role": "RGB_SAM_ASSISTED_PSEUDO_GT_REQUIRES_HUMAN_REVIEW",
        "view_count": len(dataset),
        "source_geometry_labels": str(dense_root),
        "source_geometry_receipt_sha256": sha256(dense_root / "receipt.json"),
        "rgb_role": "HELD_OUT_EVALUATION_IMAGE_EDGE_AND_REGION_GUIDANCE_ONLY",
        "sam": {
            "source": str(sam_source),
            "revision": revision,
            "checkpoint": str(checkpoint),
            "checkpoint_sha256": sha256(checkpoint),
            "model_type": "vit_b",
            "learning": 0,
        },
        "parameters": {
            "slic_segments": SLIC_SEGMENTS,
            "slic_compactness": SLIC_COMPACTNESS,
            "slic_min_seeds": SLIC_MIN_SEEDS,
            "slic_min_seed_fraction": SLIC_MIN_SEED_FRACTION,
            "slic_min_purity": SLIC_MIN_PURITY,
            "sam_classes": list(SAM_CLASSES),
            "sam_min_component_pixels": SAM_MIN_COMPONENT_PIXELS,
            "sam_max_components_per_class": SAM_MAX_COMPONENTS_PER_CLASS,
            "sam_min_support_pixels": SAM_MIN_SUPPORT_PIXELS,
            "sam_min_seed_purity": SAM_MIN_SEED_PURITY,
            "sam_min_component_recall": SAM_MIN_COMPONENT_RECALL,
            "sam_min_predicted_iou": SAM_MIN_PREDICTED_IOU,
            "sam_box_padding_px": SAM_BOX_PADDING_PX,
        },
        "mean_seed_valid_fraction": float(np.mean([item["seed_valid_fraction"] for item in view_stats])),
        "mean_output_valid_fraction": float(np.mean([item["output_valid_fraction"] for item in view_stats])),
        "total_slic_added_pixels": int(sum(item["slic_added_pixels"] for item in view_stats)),
        "total_sam_added_pixels": int(sum(item["sam_added_pixels"] for item in view_stats)),
        "total_sam_accepted_masks": int(sum(item["accepted_mask_count"] for item in view_stats)),
        "qa_count": len(list(qa_root.glob("*.png"))),
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
