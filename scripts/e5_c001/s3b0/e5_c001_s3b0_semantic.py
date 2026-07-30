#!/usr/bin/env python3
"""S3-B step-0e semantic lineage audit and one-model non-GT mask measurement."""
from __future__ import annotations

import argparse
import json
import math
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
os.environ.setdefault("XDG_CACHE_HOME", "/tmp")

import cv2
import matplotlib
import numpy as np
import open3d as o3d
import torch
import yaml
from PIL import Image
from shapely import contains_xy

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from src.stage2.colmap_io import read_points3d_bin

import e5_c001_s3b0_common as common


MASK_FIELDS = [
    "building_id",
    "view_stem",
    "region_scope",
    "current_pixels",
    "non_gt_pixels",
    "intersection_pixels",
    "union_pixels",
    "iou",
    "projected_target_pixels",
    "target_sam_score",
    "target_projection_iou",
    "target_candidate_index",
    "neighbor_prompt_count",
    "neighbor_candidate_count",
    "mask_npz",
    "mask_npz_sha256",
    "current_cache_role",
    "non_gt_input_rule",
    "gt_used_for_non_gt_inference",
    "lod2_used_for_non_gt_inference",
    "als_used_for_non_gt_inference",
    "learning_runs_started",
    "new_2d_segmentation_inference_models",
    "status",
]


def input_height_inventory(
    building_ids: list[str],
    footprints: dict[str, Any],
    sparse_path: Path,
    dense_path: Path,
    offset: np.ndarray,
) -> dict[str, dict[str, Any]]:
    sparse_payload = read_points3d_bin(sparse_path)
    if isinstance(sparse_payload, dict):
        sparse = np.asarray([point.xyz for point in sparse_payload.values()], dtype=np.float64)
    else:
        sparse = np.asarray(sparse_payload, dtype=np.float64)[:, :3]
    dense = np.asarray(o3d.io.read_point_cloud(str(dense_path)).points, dtype=np.float64)
    all_points = np.vstack([sparse, dense])
    x = all_points[:, 0] + offset[0]
    y = all_points[:, 1] + offset[1]
    output: dict[str, dict[str, Any]] = {}
    for bid in building_ids:
        geom = footprints[bid]
        minx, miny, maxx, maxy = geom.bounds
        box = (x >= minx) & (x <= maxx) & (y >= miny) & (y <= maxy)
        index = np.flatnonzero(box)
        inside = np.zeros(len(all_points), dtype=bool)
        if len(index):
            inside[index] = contains_xy(geom, x[index], y[index])
        z = all_points[inside, 2]
        output[bid] = {
            "source_count": int(len(z)),
            "z_median_local_m": float(np.median(z)) if len(z) else None,
            "source": "zero-iteration COLMAP sparse plus DIM dense-init inside supplied footprint",
        }
    return output


def farthest_points(mask: np.ndarray, count: int = 5) -> np.ndarray:
    work = np.asarray(mask, dtype=np.uint8)
    if not np.any(work):
        return np.zeros((0, 2), dtype=np.float32)
    distance = cv2.distanceTransform(work, cv2.DIST_L2, 5)
    points: list[tuple[float, float]] = []
    mutable = distance.copy()
    radius = max(4, int(round(math.sqrt(float(work.sum())) / 5.0)))
    for _ in range(count):
        _min, maximum, _minloc, maxloc = cv2.minMaxLoc(mutable)
        if maximum <= 0:
            break
        points.append((float(maxloc[0]), float(maxloc[1])))
        cv2.circle(mutable, maxloc, radius, 0.0, thickness=-1)
    return np.asarray(points, dtype=np.float32)


def prompt_box(mask: np.ndarray, padding: int) -> np.ndarray | None:
    y, x = np.nonzero(mask)
    if not len(x):
        return None
    height, width = mask.shape
    return np.asarray(
        [
            max(0, int(x.min()) - padding),
            max(0, int(y.min()) - padding),
            min(width - 1, int(x.max()) + padding),
            min(height - 1, int(y.max()) + padding),
        ],
        dtype=np.float32,
    )


def sam_mask(
    predictor: Any,
    projected: np.ndarray,
    box_padding: int,
) -> tuple[np.ndarray, dict[str, Any]]:
    box = prompt_box(projected, box_padding)
    if box is None or int(projected.sum()) < 3:
        return np.zeros_like(projected), {
            "status": "empty_projection",
            "candidate_index": None,
            "sam_score": None,
            "projection_iou": None,
            "selection_score": None,
        }
    points = farthest_points(projected, count=5)
    labels = np.ones(len(points), dtype=np.int32)
    masks, scores, _logits = predictor.predict(
        point_coords=points if len(points) else None,
        point_labels=labels if len(points) else None,
        box=box,
        multimask_output=True,
    )
    best_index = 0
    best_selection = -float("inf")
    best_projection_iou = 0.0
    for index, mask in enumerate(masks):
        _intersection, _union, projection_iou = common.iou(mask, projected)
        selection = 0.70 * float(scores[index]) + 0.30 * projection_iou
        if selection > best_selection:
            best_index = index
            best_selection = selection
            best_projection_iou = projection_iou
    return np.asarray(masks[best_index], dtype=bool), {
        "status": "measured",
        "candidate_index": int(best_index),
        "sam_score": float(scores[best_index]),
        "projection_iou": float(best_projection_iou),
        "selection_score": float(best_selection),
        "prompt_box_xyxy": box.tolist(),
        "positive_points_xy": points.tolist(),
    }


def current_masks(context: dict[str, Any]) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    payload = np.load(context["semantic_region_path"], allow_pickle=False)
    region_ids = np.asarray(payload["region_ids"], dtype=np.int32)
    cutline = np.asarray(payload["cutline_mask"], dtype=bool)
    metadata = json.loads(str(payload["metadata_json"].item()))
    target_ids = [
        int(region_id)
        for region_id, row in metadata["regions"].items()
        if str(row.get("building_id")) == context["building_id"]
    ]
    target = np.isin(region_ids, target_ids) & (~cutline)
    neighbor = (region_ids > 0) & (~np.isin(region_ids, target_ids)) & (~cutline)
    return target, neighbor, {
        "target_region_ids": sorted(target_ids),
        "cache_schema": metadata.get("schema"),
        "loss_address_mode": metadata.get("loss_address_mode"),
        "raycast_building_id_is_loss_input": metadata.get("raycast_building_id_is_loss_input"),
    }


def write_lineage(path: Path, source_hash: dict[str, str]) -> None:
    rows = [
        (
            "현행 semantic class",
            "scripts/evidence_and_attributes/p2_gsjso/make_clean_labels.py",
            "CityGML LoD2 Roof/Wall/GroundSurface와 COLMAP pose",
            "LoD2 mesh raycast class PNG",
            "semantic class 전체 픽셀",
        ),
        (
            "현행 semantic_region ID",
            "scripts/e5_c001/p2_gsjso/e5_c001_s3_semantic_regions.py",
            "동일 LoD2 raycast의 building ID와 고정 class-1 PNG",
            "region_ids, cutline_mask, region-to-building mapping",
            "target/neighbor 영역 주소",
        ),
        (
            "Phase-2 crop",
            "phases/p2-gsjso/scripts/e5_c001/e5_c001_s3ap_phase2_prepare.py",
            "현행 semantic PNG와 semantic_region NPZ",
            "native-pixel crop",
            "학습 crop의 class와 instance 주소",
        ),
        (
            "target-region 선택",
            "src/stage2/train.py::_target_region_mask",
            "metadata.regions의 building_id",
            "target_region_mask와 target_region_ids",
            "mono-depth/mono-normal target-region 주소",
        ),
        (
            "semantic geometry regularizer",
            "src/stage2/loss/semantic_guided.py",
            "oracle-instance-split region_ids와 cutline",
            "region별 smooth/plane/boundary 주소",
            "semantic-guided geometry loss 주소",
        ),
        (
            "S3-B 구속 영역에 현행 캐시를 재사용할 경우",
            "미구현 설계 입력",
            "위 region_ids와 target building ID",
            "semantic∩footprint 구속 대상과 이웃 마스크",
            "LoD2 class+정답 ID 의존이 P_r 대상 선택과 photo 이웃 마스킹까지 전파",
        ),
    ]
    lines = [
        "# S3-B 0-e semantic 마스크 계보 감사",
        "",
        "- 범위: 현행 캐시 계보의 소스 추적과 비-GT SAM ViT-B 마스크의 IoU 측정.",
        "- 학습 실행: `learning_runs_started=0`.",
        "- 현행 캐시의 역할: 계보 감사와 IoU 채점 전용. 비-GT SAM 프롬프트·추론 입력에는 사용하지 않음.",
        "- 비-GT 프롬프트: 공급 footprint XY, 영상 유래 FM 평면, zero-iteration SfM+DIM 높이만 사용.",
        "",
        "## 의존 표",
        "",
        "| 단계 | 구현 | 읽는 항목 | 생성 항목 | 의존 전파 |",
        "|---|---|---|---|---|",
    ]
    lines.extend(f"| {a} | `{b}` | {c} | {d} | {e} |" for a, b, c, d, e in rows)
    lines.extend(
        [
            "",
            "## 의존 항목 목록",
            "",
            "- LoD2 표면 기하: class 레이캐스트와 building-ID 레이캐스트에 사용.",
            "- 정답 building ID: `metadata.regions`의 target 선택과 이웃 분리에 사용.",
            "- 공급 footprint: 현행 v3 loss 주소 자체가 아니라 과거 defect baseline과 crop QA에 사용되며, 본 0-e 비-GT 프롬프트에서는 허용된 2D 공간 입력으로 사용.",
            "- 전파 범위: semantic class → instance region → target mask/cutline → mono target-region 및 semantic geometry regularizer. 같은 캐시를 S3-B에 연결하면 구속 스플랫 주소와 이웃 photo 마스킹까지 이어짐.",
            "",
            "## 비-GT 대체 측정 규격",
            "",
            "- 모델: Meta Segment Anything ViT-B, 공식 checkpoint `sam_vit_b_01ec64.pth`.",
            "- target prompt 높이: footprint 내부 영상 대응점으로 적합한 FM 평면.",
            "- neighbor prompt 높이: C00118 각 footprint 내부 zero-iteration COLMAP sparse + DIM dense-init z 중앙값.",
            "- 후보 선택: `0.70 × SAM predicted IoU + 0.30 × projected-footprint IoU` 최대 후보.",
            "- IoU 비교 대상: 현행 LoD2-raycast cache의 target/neighbor/합집합 마스크. 이 비교는 score-only.",
            "",
            "## 소스 SHA256",
            "",
        ]
    )
    lines.extend(f"- `{name}`: `{digest}`" for name, digest in sorted(source_hash.items()))
    common.atomic_text(path, "\n".join(lines) + "\n")


def make_figure(
    path: Path,
    image: np.ndarray,
    current_target: np.ndarray,
    current_neighbor: np.ndarray,
    model_target: np.ndarray,
    model_neighbor: np.ndarray,
    building_id: str,
    stem: str,
) -> None:
    def overlay(base: np.ndarray, target: np.ndarray, neighbor: np.ndarray) -> np.ndarray:
        value = base.astype(np.float32).copy()
        colors = [(target, np.asarray([220, 70, 55], dtype=np.float32)), (neighbor, np.asarray([55, 145, 210], dtype=np.float32))]
        for mask, color in colors:
            value[mask] = 0.42 * value[mask] + 0.58 * color
        value[common.boundary(target)] = np.asarray([255, 235, 80], dtype=np.float32)
        value[common.boundary(neighbor)] = np.asarray([80, 245, 235], dtype=np.float32)
        return np.clip(value, 0, 255).astype(np.uint8)

    fig, axes = plt.subplots(1, 3, figsize=(12, 4), dpi=170)
    axes[0].imshow(image)
    axes[0].set_title("crop image")
    axes[1].imshow(overlay(image, current_target, current_neighbor))
    axes[1].set_title("current cache (score-only)")
    axes[2].imshow(overlay(image, model_target, model_neighbor))
    axes[2].set_title("SAM ViT-B non-GT")
    for axis in axes:
        axis.axis("off")
    fig.suptitle(f"{building_id} | {stem} | red=target, blue=neighbor | learning 0", fontsize=10)
    fig.tight_layout(rect=[0, 0, 1, 0.92])
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.stem + ".tmp" + path.suffix)
    fig.savefig(tmp)
    plt.close(fig)
    os.replace(tmp, path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lock", type=Path, default=common.DEFAULT_LOCK)
    parser.add_argument("--device", default="cuda")
    args = parser.parse_args()
    lock = common.load_lock(args.lock.resolve())
    if lock["new_inference"]["semantic_model_count"] != 1:
        raise RuntimeError("0-e requires exactly one semantic inference model")

    sources = {key: common.resolve(value) for key, value in lock["sources"].items()}
    outputs = {key: common.resolve(value) for key, value in lock["outputs"].items()}
    semantic = lock["semantic_0e"]
    model_cfg = semantic["model"]
    model_repo = common.resolve(model_cfg["runtime_repo"])
    weights = common.resolve(model_cfg["weights"])
    if not model_repo.exists() or not weights.exists():
        raise FileNotFoundError("SAM runtime repository or weights missing; run the bootstrap wrapper")
    revision = subprocess.check_output(["git", "-C", str(model_repo), "rev-parse", "HEAD"], text=True).strip()
    if revision != model_cfg["revision"]:
        raise RuntimeError(f"SAM repository revision drift: {revision}")
    if common.sha256_file(weights) != model_cfg["weights_sha256"] or weights.stat().st_size != model_cfg["weights_bytes"]:
        raise RuntimeError("SAM weights hash/size drift")
    sys.path.insert(0, str(model_repo))
    from segment_anything import SamPredictor, sam_model_registry  # noqa: E402

    run_dir = outputs["semantic_run"]
    mask_dir = outputs["semantic_masks"]
    figure_dir = outputs["semantic_figure_dir"]
    run_dir.mkdir(parents=True, exist_ok=True)
    mask_dir.mkdir(parents=True, exist_ok=True)
    figure_dir.mkdir(parents=True, exist_ok=True)
    log_path = run_dir / "run.log"
    common.atomic_text(log_path, "")

    def log(message: str) -> None:
        line = f"{common.now()} {message}"
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        print(line, flush=True)

    if args.device.startswith("cuda") and not torch.cuda.is_available():
        raise RuntimeError("CUDA device requested but unavailable")
    device = torch.device(args.device)
    sam = sam_model_registry[model_cfg["model_type"]](checkpoint=str(weights))
    sam.to(device=device)
    sam.eval()
    predictor = SamPredictor(sam)
    log(f"model_loaded name={model_cfg['name']} revision={revision} device={device} learning=0")

    c00118 = yaml.safe_load(sources["c00118_config"].read_text(encoding="utf-8"))["seed_log_buildings"]
    c00118 = [common.full_id(value) for value in c00118]
    footprints = common.load_footprints(sources["footprints"], c00118)
    offset = common.load_world_offset(sources["train_manifest"])
    fm = common.load_fm_summaries(sources["fm_rescore_csv"])
    height_inventory = input_height_inventory(
        c00118, footprints, sources["sparse_points"], sources["dense_init"], offset
    )
    contexts = common.load_crop_contexts(sources["prepared_root"], lock["targets"])

    rows: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    generated: list[Path] = []
    prompt_rule = semantic["prompt_rule"]
    for sequence, context in enumerate(contexts, start=1):
        image = np.asarray(Image.open(context["image_path"]).convert("RGB"), dtype=np.uint8)
        height, width = image.shape[:2]
        predictor.set_image(image)
        short = context["short"]
        target_bid = context["building_id"]
        target_plane = fm[short]["plane"]
        projected_target, _target_uvs, _target_depths = common.project_geometry_mask(
            footprints[target_bid], target_plane, context["view"], offset, (height, width)
        )
        target_mask, target_audit = sam_mask(
            predictor, projected_target, int(prompt_rule["box_padding_px"])
        )

        neighbor_mask = np.zeros((height, width), dtype=bool)
        neighbor_prompts: list[dict[str, Any]] = []
        for neighbor_bid in c00118:
            if neighbor_bid == target_bid:
                continue
            inventory = height_inventory[neighbor_bid]
            if inventory["z_median_local_m"] is None:
                continue
            neighbor_plane = np.asarray([0.0, 0.0, inventory["z_median_local_m"]], dtype=np.float64)
            projected, _uvs, _depths = common.project_geometry_mask(
                footprints[neighbor_bid], neighbor_plane, context["view"], offset, (height, width)
            )
            projected_pixels = int(projected.sum())
            if projected_pixels < int(prompt_rule["neighbor_min_projected_pixels"]):
                continue
            predicted, audit = sam_mask(predictor, projected, int(prompt_rule["box_padding_px"]))
            neighbor_mask |= predicted
            neighbor_prompts.append(
                {
                    "building_id": neighbor_bid,
                    "projected_pixels": projected_pixels,
                    "predicted_pixels": int(predicted.sum()),
                    **audit,
                }
            )
        neighbor_mask &= ~target_mask
        current_target, current_neighbor, current_audit = current_masks(context)

        metadata = {
            "schema": "jointbuildgs.s3b0.semantic_mask.v1",
            "building_id": target_bid,
            "view_stem": context["stem"],
            "crs": lock["crs"],
            "model": {
                "name": model_cfg["name"],
                "revision": revision,
                "weights_sha256": model_cfg["weights_sha256"],
            },
            "target_prompt": {
                "source": "supplied footprint plus image-derived FM fitted plane",
                "fm_plane_ax_by_c": target_plane.tolist(),
                "projected_pixels": int(projected_target.sum()),
                **target_audit,
            },
            "neighbor_prompts": neighbor_prompts,
            "current_cache": {
                "role": "score_only",
                **current_audit,
            },
            "gt_used_for_non_gt_inference": False,
            "lod2_used_for_non_gt_inference": False,
            "als_used_for_non_gt_inference": False,
            "learning_runs_started": 0,
            "new_2d_segmentation_inference_models": 1,
        }
        output_path = mask_dir / f"{target_bid}_{context['stem']}.npz"
        common.atomic_deterministic_npz(
            output_path,
            {
                "metadata_json": np.asarray(json.dumps(metadata, ensure_ascii=False, sort_keys=True)),
                "neighbor_mask": neighbor_mask.astype(np.bool_),
                "projected_target_mask": projected_target.astype(np.bool_),
                "target_mask": target_mask.astype(np.bool_),
            },
        )
        generated.append(output_path)
        output_hash = common.sha256_file(output_path)
        scopes = [
            ("target_roof", current_target, target_mask),
            ("neighbor_roof", current_neighbor, neighbor_mask),
            ("target_or_neighbor", current_target | current_neighbor, target_mask | neighbor_mask),
        ]
        for scope, current, predicted in scopes:
            intersection, union, score = common.iou(current, predicted)
            rows.append(
                {
                    "building_id": target_bid,
                    "view_stem": context["stem"],
                    "region_scope": scope,
                    "current_pixels": int(current.sum()),
                    "non_gt_pixels": int(predicted.sum()),
                    "intersection_pixels": intersection,
                    "union_pixels": union,
                    "iou": score,
                    "projected_target_pixels": int(projected_target.sum()),
                    "target_sam_score": target_audit.get("sam_score"),
                    "target_projection_iou": target_audit.get("projection_iou"),
                    "target_candidate_index": target_audit.get("candidate_index"),
                    "neighbor_prompt_count": len(neighbor_prompts),
                    "neighbor_candidate_count": int(sum(row["predicted_pixels"] > 0 for row in neighbor_prompts)),
                    "mask_npz": common.rel(output_path),
                    "mask_npz_sha256": output_hash,
                    "current_cache_role": "LoD2-raycast class+building-ID score-only",
                    "non_gt_input_rule": "image + supplied footprint + image-derived FM plane + zero-iteration SfM/DIM neighbor heights",
                    "gt_used_for_non_gt_inference": False,
                    "lod2_used_for_non_gt_inference": False,
                    "als_used_for_non_gt_inference": False,
                    "learning_runs_started": 0,
                    "new_2d_segmentation_inference_models": 1,
                    "status": target_audit["status"],
                }
            )
        records.append(
            {
                "context": context,
                "image": image,
                "current_target": current_target,
                "current_neighbor": current_neighbor,
                "target_mask": target_mask,
                "neighbor_mask": neighbor_mask,
                "projected_pixels": int(projected_target.sum()),
                "output": output_path,
            }
        )
        log(
            f"view={sequence}/{len(contexts)} building={target_bid} stem={context['stem']} "
            f"projected={int(projected_target.sum())} target={int(target_mask.sum())} "
            f"neighbor={int(neighbor_mask.sum())} prompts={len(neighbor_prompts)} learning=0"
        )

    common.atomic_csv(outputs["mask_iou_csv"], rows, MASK_FIELDS)
    generated.append(outputs["mask_iou_csv"])
    for short in lock["targets"]:
        choices = [row for row in records if row["context"]["short"] == short]
        representative = max(choices, key=lambda row: (row["projected_pixels"], row["context"]["stem"]))
        figure_path = figure_dir / f"{representative['context']['building_id']}_{representative['context']['stem']}.png"
        make_figure(
            figure_path,
            representative["image"],
            representative["current_target"],
            representative["current_neighbor"],
            representative["target_mask"],
            representative["neighbor_mask"],
            representative["context"]["building_id"],
            representative["context"]["stem"],
        )
        generated.append(figure_path)

    lineage_sources = [
        common.REPO / "scripts/evidence_and_attributes/p2_gsjso/make_clean_labels.py",
        common.REPO / "scripts/e5_c001/p2_gsjso/e5_c001_s3_semantic_regions.py",
        common.REPO / "phases/p2-gsjso/scripts/e5_c001/e5_c001_s3ap_phase2_prepare.py",
        common.REPO / "src/stage2/train.py",
        common.REPO / "src/stage2/loss/semantic_guided.py",
    ]
    lineage_hashes = common.source_hashes(lineage_sources)
    write_lineage(outputs["semantic_lineage_md"], lineage_hashes)
    generated.append(outputs["semantic_lineage_md"])

    source_paths = [
        args.lock.resolve(),
        sources["footprints"],
        sources["train_manifest"],
        sources["sparse_points"],
        sources["dense_init"],
        sources["c00118_config"],
        sources["fm_rescore_csv"],
        weights,
        *lineage_sources,
        *(context["image_path"] for context in contexts),
        *(context["semantic_region_path"] for context in contexts),
        *(context["manifest_path"] for context in contexts),
    ]
    manifest = {
        "schema": "jointbuildgs.s3b0.semantic_measurement.v1",
        "created_utc": common.now(),
        "task": "0-e semantic lineage audit and one-model non-GT mask IoU",
        "crs": lock["crs"],
        "git": {
            "head": common.git_value("rev-parse", "HEAD"),
            "branch": common.git_value("branch", "--show-current"),
            "dirty": bool(common.git_value("status", "--porcelain")),
        },
        "runtime": {
            "python": platform.python_version(),
            "torch": torch.__version__,
            "cuda_available": torch.cuda.is_available(),
            "cuda_device": torch.cuda.get_device_name(device) if device.type == "cuda" else None,
            "docker_image": lock["containers"]["main_image"],
            "docker_image_id": lock["containers"]["main_image_id"],
        },
        "model": {
            **model_cfg,
            "resolved_revision": revision,
        },
        "input_height_inventory": height_inventory,
        "counts": {
            "building_view_count": len(contexts),
            "iou_row_count": len(rows),
            "mask_npz_count": len([path for path in generated if path.suffix == ".npz"]),
            "figure_count": len([path for path in generated if path.suffix == ".png"]),
        },
        "source_sha256": common.source_hashes(source_paths),
        "output_sha256": common.source_hashes(generated),
        "gt_boundary": {
            "current_semantic_region_cache": "score_only",
            "gt_used_for_non_gt_inference": False,
            "lod2_used_for_non_gt_inference": False,
            "als_used_for_non_gt_inference": False,
        },
        "learning_runs_started": 0,
        "new_2d_segmentation_inference_models": 1,
        "status": "measured",
    }
    manifest_path = run_dir / "manifest.json"
    common.atomic_json(manifest_path, manifest)
    log(f"complete rows={len(rows)} masks={len(contexts)} manifest={common.rel(manifest_path)} learning=0")


if __name__ == "__main__":
    main()
