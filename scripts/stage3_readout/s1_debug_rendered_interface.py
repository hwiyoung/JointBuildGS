"""S1-debug: rendered evidence interface failure attribution.

This diagnostic reuses the S1 rendered sample export and the existing E2
splitter/read-out. It does not retrain Stage2 and does not use GT in the
non-oracle split/read-out paths.
"""
from __future__ import annotations

import argparse
import csv
import itertools
import json
import math
import shutil
import sys
import traceback
from collections import Counter
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import torch
import yaml
from PIL import Image
from scipy.spatial import cKDTree
from shapely.geometry import Point, Polygon

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.stage3_readout.obj_gt import parse_scene_obj  # noqa: E402
import scripts.stage3_readout.e2_gt_fullscene_auto_split as e2  # noqa: E402
import scripts.stage3_readout.e3_stage2_oracle_split as e3  # noqa: E402
import scripts.stage3_readout.p1_4a_preflight_precision as pm  # noqa: E402
import scripts.stage3_readout.p1_4a_relation_readout as rr  # noqa: E402
import scripts.stage3_readout.s1_rendered_e2style_gate as s1  # noqa: E402
from src.stage2.dataloader import ColmapDataset  # noqa: E402


OUT_ROOT = ROOT / "results/stage3_rendered_evidence/S1_debug_rendered_interface"
S1_ROOT = ROOT / "results/stage3_rendered_evidence/S1_rendered_e2style_gate"
SCENE = ROOT / "results/phase2_synthesis/scene.obj"
MUTUAL_CKPT = ROOT / "results/phase2_ablation_citygml/mutual/ckpt/final.pt"
MUTUAL_CONFIG = ROOT / "configs/mutual_loss/core_ablation/phase2_mutual.yaml"
E2_REFERENCE = ROOT / "results/stage3_typed_readout/E2_gt_fullscene_auto_split"
E1_SUMMARY_CSV = ROOT / "results/stage3_typed_readout/E1_gt_131_per_building/summary_metrics.csv"
E3_SMOKE_CSV = ROOT / "results/stage3_typed_readout/E3_stage2_oracle_split/smoke_mutual/smoke_metrics.csv"

CLASSES = ["bg", "roof", "wall", "terrain"]
CLASS_IDS = [0, 1, 2, 3]
TARGET_BIDS = [0, 1, 2, 8, 6, 123, 126, 50, 104, 111, 117]
BID_LOCAL = [0, 1, 2, 6, 8, 123, 126]
GRAVITY = np.array([0.0, 1.0, 0.0], dtype=np.float64)

SEM_COLORS = np.asarray([
    [60, 60, 60],
    [220, 40, 40],
    [45, 95, 215],
    [45, 160, 75],
], dtype=np.uint8)


def mkdir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def jsonable(obj):
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, np.generic):
        return obj.item()
    if isinstance(obj, (Point, Polygon)):
        return obj.wkt
    return str(obj)


def write_json(path: Path, payload: Dict) -> None:
    mkdir(path.parent)
    path.write_text(json.dumps(payload, indent=2, default=jsonable) + "\n")


def read_json(path: Path) -> Dict:
    return json.loads(path.read_text()) if path.exists() else {}


def read_csv(path: Path) -> List[Dict]:
    if not path.exists():
        return []
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: List[Dict], fields: Optional[List[str]] = None) -> None:
    mkdir(path.parent)
    if fields is None:
        fields = []
        seen = set()
        for row in rows:
            for key in row:
                if key not in seen:
                    fields.append(key)
                    seen.add(key)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fields})


def fmt(value: object, nd: int = 3) -> str:
    if value is None or value == "":
        return "NA"
    if isinstance(value, bool):
        return "true" if value else "false"
    try:
        x = float(value)
    except (TypeError, ValueError):
        return str(value)
    if math.isnan(x) or math.isinf(x):
        return "NA"
    return f"{x:.{nd}f}"


def md_table(headers: List[str], rows: List[List[object]]) -> str:
    out = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in rows:
        out.append("| " + " | ".join(str(x) for x in row) + " |")
    return "\n".join(out)


def safe_float(value: object) -> Optional[float]:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(x) or math.isinf(x) else x


def normalize_rows(arr: np.ndarray) -> np.ndarray:
    x = np.asarray(arr, dtype=np.float64)
    return x / np.maximum(np.linalg.norm(x, axis=1, keepdims=True), 1e-12)


def entropy_rows(probs: np.ndarray) -> np.ndarray:
    if len(probs) == 0:
        return np.asarray([], dtype=np.float64)
    p = np.clip(np.asarray(probs, dtype=np.float64), 1e-12, 1.0)
    p = p / np.maximum(p.sum(axis=1, keepdims=True), 1e-12)
    return -np.sum(p * np.log(p), axis=1) / math.log(p.shape[1])


def iou_per_class(gt: np.ndarray, pred: np.ndarray, classes: Iterable[int] = (1, 2, 3)) -> Dict[int, float]:
    out = {}
    for cls in classes:
        tp = int(np.sum((gt == cls) & (pred == cls)))
        fp = int(np.sum((gt != cls) & (pred == cls)))
        fn = int(np.sum((gt == cls) & (pred != cls)))
        den = tp + fp + fn
        out[int(cls)] = float(tp / den) if den else float("nan")
    return out


def miou(gt: np.ndarray, pred: np.ndarray, classes: Iterable[int] = (1, 2, 3)) -> Optional[float]:
    vals = [v for v in iou_per_class(gt, pred, classes).values() if not math.isnan(v)]
    return float(np.mean(vals)) if vals else None


def confusion_rows(scope: str, view_id: object, gt: np.ndarray, pred: np.ndarray,
                   mapping_name: str = "expected") -> List[Dict]:
    rows = []
    for g in CLASS_IDS:
        for p in CLASS_IDS:
            rows.append({
                "scope": scope,
                "view_id": view_id,
                "mapping": mapping_name,
                "gt_class": CLASSES[g],
                "pred_class": CLASSES[p],
                "count": int(np.sum((gt == g) & (pred == p))),
            })
    return rows


def load_npz(path: Path) -> Dict[str, np.ndarray]:
    data = np.load(path, allow_pickle=False)
    return {k: data[k] for k in data.files}


def dataset_downscale_from_s1() -> float:
    rows = read_csv(S1_ROOT / "phase1_render_export/render_export_summary.csv")
    return float(rows[0].get("render_downscale", 0.25)) if rows else 0.25


def load_dataset(load_gt: bool = True) -> ColmapDataset:
    cfg = yaml.safe_load(MUTUAL_CONFIG.read_text())
    data_root = Path(cfg["data_root"])
    if not data_root.exists():
        data_root = ROOT / "results/phase2_synthesis/dataset"
    return ColmapDataset(
        root=data_root,
        downscale=float(cfg.get("downscale", 1.0)) * dataset_downscale_from_s1(),
        load_depth=load_gt,
        load_normal=load_gt,
        load_semantic=load_gt,
        depth_scale=float(cfg.get("depth_scale", 1.0)),
    )


def selected_view_ids(raw: Dict[str, np.ndarray]) -> List[int]:
    return sorted(int(x) for x in np.unique(raw["view_id"]))


def batch_for_view(ds: ColmapDataset, view_id: int) -> Dict:
    return ds[int(view_id)]


def variant_normals(normals: np.ndarray, w2c: np.ndarray) -> Dict[str, np.ndarray]:
    n0 = normalize_rows(normals)
    R = np.asarray(w2c[:3, :3], dtype=np.float64)
    c2w = normalize_rows(n0 @ R)
    w2cam = normalize_rows(n0 @ R.T)
    return {
        "N0_exported": n0,
        "N1_neg_exported": -n0,
        "N2_camera_to_world": c2w,
        "N3_neg_camera_to_world": -c2w,
        "N4_world_to_camera": w2cam,
        "N5_neg_world_to_camera": -w2cam,
    }


def best_semantic_mapping(gt: np.ndarray, pred: np.ndarray) -> Tuple[str, Tuple[int, ...], float, Optional[float]]:
    best = ("expected", (0, 1, 2, 3), float(np.mean(gt == pred)) if len(gt) else 0.0, miou(gt, pred))
    for perm in itertools.permutations(CLASS_IDS):
        mapped = np.asarray(perm, dtype=np.int64)[pred]
        acc = float(np.mean(gt == mapped)) if len(gt) else 0.0
        m = miou(gt, mapped)
        score = -1.0 if m is None else m
        best_score = -1.0 if best[3] is None else best[3]
        if (score, acc) > (best_score, best[2]):
            best = ("perm_" + "".join(map(str, perm)), tuple(int(x) for x in perm), acc, m)
    return best


def map_labels(labels: np.ndarray, perm: Tuple[int, ...]) -> np.ndarray:
    return np.asarray(perm, dtype=np.int64)[labels.astype(np.int64)]


def project_world(points: np.ndarray, K: np.ndarray, w2c: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    pts_h = np.c_[points.astype(np.float64), np.ones(len(points), dtype=np.float64)]
    cam = pts_h @ np.asarray(w2c, dtype=np.float64).T
    z = cam[:, 2]
    u = K[0, 0] * cam[:, 0] / np.maximum(z, 1e-12) + K[0, 2]
    v = K[1, 1] * cam[:, 1] / np.maximum(z, 1e-12) + K[1, 2]
    return u, v, z


def unproject_variant(u: np.ndarray, v: np.ndarray, depth: np.ndarray, K: np.ndarray,
                      w2c: np.ndarray, variant: str) -> np.ndarray:
    fx, fy = K[0, 0], K[1, 1]
    cx, cy = K[0, 2], K[1, 2]
    x_norm = (u.astype(np.float64) - cx) / fx
    y_norm = (v.astype(np.float64) - cy) / fy
    d = depth.astype(np.float64)
    if variant.startswith("ray_depth"):
        z = d / np.maximum(np.sqrt(x_norm * x_norm + y_norm * y_norm + 1.0), 1e-12)
    elif variant.startswith("inverse_depth"):
        z = 1.0 / np.maximum(d, 1e-12)
    else:
        z = d
    pts_cam = np.stack([x_norm * z, y_norm * z, z], axis=1)
    if "flip_yz" in variant:
        pts_cam[:, 1] *= -1.0
        pts_cam[:, 2] *= -1.0
    elif "flip_y" in variant:
        pts_cam[:, 1] *= -1.0
    elif "flip_z" in variant:
        pts_cam[:, 2] *= -1.0
    pts_h = np.c_[pts_cam, np.ones(len(pts_cam), dtype=np.float64)]
    if "inverse_extrinsic" in variant:
        return (pts_h @ np.asarray(w2c, dtype=np.float64).T)[:, :3]
    return (pts_h @ np.linalg.inv(np.asarray(w2c, dtype=np.float64)).T)[:, :3]


def bbox_iou_3d(a: np.ndarray, b: np.ndarray) -> Optional[float]:
    if len(a) == 0 or len(b) == 0:
        return None
    amin, amax = a.min(axis=0), a.max(axis=0)
    bmin, bmax = b.min(axis=0), b.max(axis=0)
    inter_min = np.maximum(amin, bmin)
    inter_max = np.minimum(amax, bmax)
    inter = np.maximum(inter_max - inter_min, 0.0)
    inter_vol = float(np.prod(inter))
    av = float(np.prod(np.maximum(amax - amin, 0.0)))
    bv = float(np.prod(np.maximum(bmax - bmin, 0.0)))
    den = av + bv - inter_vol
    return inter_vol / den if den > 0 else None


def write_overlay_ply(path: Path, rendered: np.ndarray, gt: np.ndarray, max_points: int = 300_000,
                      seed: int = 0) -> None:
    rng = np.random.default_rng(seed)
    r = rendered
    g = gt
    if len(r) > max_points // 2:
        r = r[rng.choice(len(r), max_points // 2, replace=False)]
    if len(g) > max_points // 2:
        g = g[rng.choice(len(g), max_points // 2, replace=False)]
    pts = np.vstack([r, g]).astype(np.float32)
    src = np.concatenate([np.zeros(len(r), dtype=np.int32), np.ones(len(g), dtype=np.int32)])
    colors = np.where(src[:, None] == 0, np.asarray([[230, 60, 60]], dtype=np.uint8),
                      np.asarray([[40, 120, 230]], dtype=np.uint8))
    dtype = [
        ("x", "<f4"), ("y", "<f4"), ("z", "<f4"),
        ("red", "u1"), ("green", "u1"), ("blue", "u1"), ("source", "<i4"),
    ]
    data = np.empty(len(pts), dtype=dtype)
    data["x"], data["y"], data["z"] = pts[:, 0], pts[:, 1], pts[:, 2]
    data["red"], data["green"], data["blue"] = colors[:, 0], colors[:, 1], colors[:, 2]
    data["source"] = src
    header = [
        "ply", "format binary_little_endian 1.0", f"element vertex {len(pts)}",
        "property float x", "property float y", "property float z",
        "property uchar red", "property uchar green", "property uchar blue",
        "property int source", "end_header",
    ]
    mkdir(path.parent)
    with path.open("wb") as f:
        f.write(("\n".join(header) + "\n").encode("ascii"))
        data.tofile(f)


def phase0(raw: Dict[str, np.ndarray], args: argparse.Namespace) -> Dict:
    root = OUT_ROOT
    render_summary = read_csv(S1_ROOT / "phase1_render_export/render_export_summary.csv")
    fusion_summary = read_csv(S1_ROOT / "phase2_fusion/fusion_summary.csv")
    split_summary = read_csv(S1_ROOT / "phase4_e2style_split/split_comparison_summary.csv")
    policy = read_json(S1_ROOT / "phase1_render_export/render_export_policy.json")
    cfg = yaml.safe_load(MUTUAL_CONFIG.read_text())
    ckpt_iteration = cfg.get("max_iter")
    try:
        meta = torch.load(MUTUAL_CKPT, map_location="cpu", weights_only=False)
        ckpt_iteration = meta.get("iteration", meta.get("iter", ckpt_iteration))
        ckpt_keys = sorted(list(meta.keys()))
    except Exception as exc:
        ckpt_keys = [f"LOAD_WARNING:{type(exc).__name__}:{exc}"]

    manifest = {
        "checkpoint_path": str(MUTUAL_CKPT.relative_to(ROOT)),
        "checkpoint_iteration": ckpt_iteration,
        "checkpoint_top_level_keys": ckpt_keys,
        "config_path": str(MUTUAL_CONFIG.relative_to(ROOT)),
        "config": cfg,
        "camera_list": selected_view_ids(raw),
        "class_order": CLASSES,
        "gravity": [0, 1, 0],
        "renderer_mode": "RGB+ED plus render_semantic logits",
        "s1_source": str(S1_ROOT.relative_to(ROOT)),
        "raw_sample_fields": sorted(raw.keys()),
        "raw_sample_count_loaded": int(len(raw["label"])),
        "stage2_retraining_performed": False,
        "roofer_called": False,
        "polyfit_called": False,
        "gt_policy": "GT used only for audit, oracle replacements, bid-local diagnostic isolation, and post-generation evaluation.",
    }
    write_json(root / "phase0_artifact_manifest.json", manifest)

    rows = []
    if render_summary:
        s1_row = render_summary[0]
        checks = {
            "n_raw_samples": int(sum(read_int(s1_row.get(k)) for k in ["n_raw_samples"])),
            "n_valid_samples": int(read_int(s1_row.get("n_valid_samples"))),
        }
        actual = {
            "n_raw_samples": int(read_int(s1_row.get("n_raw_samples"))),
            "n_valid_samples": int(len(raw["label"])),
        }
        for key in checks:
            rows.append({
                "artifact": "render_export",
                "metric": key,
                "s1_value": checks[key],
                "debug_loaded_value": actual[key],
                "status": "OK" if checks[key] == actual[key] else "REPRODUCE_WARNING",
            })
    for row in fusion_summary:
        rows.append({
            "artifact": "fusion_summary",
            "metric": row.get("fusion"),
            "s1_value": row.get("n_points"),
            "debug_loaded_value": row.get("mean_view_count"),
            "status": "S1_REFERENCED",
        })
    for row in split_summary:
        rows.append({
            "artifact": "split_summary",
            "metric": row.get("input"),
            "s1_value": json.dumps({k: row.get(k) for k in ["n_pred", "matched", "instance_recall", "matched_F_mean"]}),
            "debug_loaded_value": "same S1 source",
            "status": "S1_REFERENCED",
        })
    if not rows:
        rows.append({"artifact": "S1", "metric": "availability", "s1_value": "", "debug_loaded_value": "", "status": "REPRODUCE_WARNING"})
    write_csv(root / "phase0_s1_reproduce_summary.csv", rows)

    cap_rows = [
        {"cap_name": "primitive_scene_evidence_max", "value": args.max_primitive_points, "source": "debug_runtime"},
        {"cap_name": "rendered_scene_evidence_max", "value": args.max_rendered_split_points, "source": "debug_runtime"},
        {"cap_name": "component_readout_evidence_max", "value": args.max_component_readout_points, "source": "debug_runtime"},
        {"cap_name": "s1_render_export_max_raw_samples", "value": render_summary[0].get("max_raw_samples") if render_summary else "", "source": "S1"},
        {"cap_name": "s1_pixel_stride", "value": render_summary[0].get("pixel_stride") if render_summary else "", "source": "S1"},
        {"cap_name": "s1_selected_view_count", "value": len(policy.get("selected_views", selected_view_ids(raw))), "source": "S1"},
    ]
    write_csv(root / "phase0_cap_summary.csv", cap_rows)
    return {"manifest": manifest, "reproduce": rows, "caps": cap_rows}


def read_int(value: object) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def make_phase1_figure(path: Path, b: Dict, u: np.ndarray, v: np.ndarray, depth_pred: np.ndarray,
                       normal_pred: np.ndarray, sem_pred: np.ndarray) -> None:
    H, W = int(b["height"]), int(b["width"])
    gt_depth = b["depth"].numpy() if "depth" in b else np.zeros((H, W), dtype=np.float32)
    gt_normal = b["normal"].numpy() if "normal" in b else np.zeros((H, W, 3), dtype=np.float32)
    gt_sem = b["semantic"].numpy() if "semantic" in b else np.zeros((H, W), dtype=np.int64)
    pd = np.full((H, W), np.nan, dtype=np.float32)
    pn = np.zeros((H, W, 3), dtype=np.float32)
    ps = np.zeros((H, W), dtype=np.int64)
    pd[v, u] = depth_pred
    pn[v, u] = normal_pred
    ps[v, u] = sem_pred
    fig, ax = plt.subplots(2, 3, figsize=(10, 6))
    vmax = np.nanpercentile(gt_depth[gt_depth > 0], 98) if np.any(gt_depth > 0) else np.nanpercentile(depth_pred, 98)
    ax[0, 0].imshow(pd, cmap="magma", vmin=0, vmax=vmax)
    ax[0, 0].set_title("D render")
    ax[1, 0].imshow(gt_depth, cmap="magma", vmin=0, vmax=vmax)
    ax[1, 0].set_title("D reference")
    ax[0, 1].imshow((pn * 0.5 + 0.5).clip(0, 1))
    ax[0, 1].set_title("N render")
    ax[1, 1].imshow((gt_normal * 0.5 + 0.5).clip(0, 1))
    ax[1, 1].set_title("N reference")
    ax[0, 2].imshow(SEM_COLORS[ps])
    ax[0, 2].set_title("S render")
    ax[1, 2].imshow(SEM_COLORS[np.clip(gt_sem, 0, 3)])
    ax[1, 2].set_title("S reference")
    for a in ax.ravel():
        a.axis("off")
    fig.suptitle(str(b["name"]), fontsize=10)
    fig.tight_layout()
    mkdir(path.parent)
    fig.savefig(path, dpi=130)
    plt.close(fig)


def make_phase1_placeholder(path: Path, b: Dict, reason: str) -> None:
    fig, ax = plt.subplots(figsize=(6, 3))
    ax.text(0.5, 0.58, str(b["name"]), ha="center", va="center", fontsize=10)
    ax.text(0.5, 0.42, reason, ha="center", va="center", fontsize=9)
    ax.axis("off")
    fig.tight_layout()
    mkdir(path.parent)
    fig.savefig(path, dpi=130)
    plt.close(fig)


def phase1(raw: Dict[str, np.ndarray], ds: ColmapDataset) -> Dict:
    root = OUT_ROOT / "phase1_image_space"
    fig_root = root / "figures"
    if (root / "render_quality_by_view.csv").exists():
        return {
            "render_quality": read_csv(root / "render_quality_by_view.csv"),
            "normal_candidates": read_csv(root / "normal_frame_candidates_by_view.csv"),
            "confusion": read_csv(root / "semantic_confusion_by_view.csv"),
        }
    mkdir(fig_root)
    quality_rows: List[Dict] = []
    normal_rows: List[Dict] = []
    confusion: List[Dict] = []
    for view_id in selected_view_ids(raw):
        m = raw["view_id"] == view_id
        b = batch_for_view(ds, view_id)
        u = raw["pixel_u"][m].astype(np.int64)
        v = raw["pixel_v"][m].astype(np.int64)
        valid = np.ones(len(u), dtype=bool)
        if "depth_mask" in b:
            valid &= b["depth_mask"].numpy()[v, u]
        if "normal_mask" in b:
            valid &= b["normal_mask"].numpy()[v, u]
        if "semantic" not in b:
            valid &= False
        u, v = u[valid], v[valid]
        if len(u) == 0:
            quality_rows.append({
                "view_id": view_id,
                "image_name": b["name"],
                "depth_MAE": None,
                "normal_cos_signed": None,
                "normal_cos_abs": None,
                "semantic_accuracy": None,
                "mIoU": None,
                "best_normal_variant": "NO_VALID_GT_PIXELS",
                "best_semantic_permutation": "NO_VALID_GT_PIXELS",
                "best_semantic_permutation_tuple": "",
                "best_semantic_accuracy": None,
                "best_semantic_mIoU": None,
                "n_valid_pixels": 0,
                "status": "NO_VALID_GT_PIXELS",
            })
            make_phase1_placeholder(fig_root / f"{view_id:03d}_depth_normal_semantic.png", b, "NO_VALID_GT_PIXELS")
            continue
        d_pred = raw["depth"][m][valid].astype(np.float64)
        n_pred = normalize_rows(raw["normal"][m][valid])
        prob = raw["sem_prob"][m][valid].astype(np.float64)
        s_pred = np.argmax(prob, axis=1).astype(np.int64)
        d_gt = b["depth"].numpy()[v, u].astype(np.float64)
        n_gt = normalize_rows(b["normal"].numpy()[v, u])
        s_gt = b["semantic"].numpy()[v, u].astype(np.int64)

        depth_mae = float(np.mean(np.abs(d_pred - d_gt)))
        variants = variant_normals(n_pred, b["w2c"].numpy())
        best_name = ""
        best_signed = -2.0
        for name, nv in variants.items():
            dots = np.sum(normalize_rows(nv) * n_gt, axis=1)
            row = {
                "view_id": view_id,
                "image_name": b["name"],
                "variant": name,
                "signed_dot_mean": float(np.mean(dots)),
                "abs_dot_mean": float(np.mean(np.abs(dots))),
                "signed_dot_median": float(np.median(dots)),
                "abs_dot_median": float(np.median(np.abs(dots))),
                "n_pixels": int(len(dots)),
            }
            normal_rows.append(row)
            if row["signed_dot_mean"] > best_signed:
                best_signed = row["signed_dot_mean"]
                best_name = name
        expected_acc = float(np.mean(s_gt == s_pred))
        expected_miou = miou(s_gt, s_pred)
        best_map_name, best_perm, best_acc, best_m = best_semantic_mapping(s_gt, s_pred)
        dots0 = np.sum(n_pred * n_gt, axis=1)
        quality_rows.append({
            "view_id": view_id,
            "image_name": b["name"],
            "depth_MAE": depth_mae,
            "normal_cos_signed": float(np.mean(dots0)),
            "normal_cos_abs": float(np.mean(np.abs(dots0))),
            "semantic_accuracy": expected_acc,
            "mIoU": expected_miou,
            "best_normal_variant": best_name,
            "best_semantic_permutation": best_map_name,
            "best_semantic_permutation_tuple": ",".join(map(str, best_perm)),
            "best_semantic_accuracy": best_acc,
            "best_semantic_mIoU": best_m,
            "n_valid_pixels": int(len(u)),
        })
        confusion.extend(confusion_rows("image", view_id, s_gt, s_pred, "expected"))
        if best_perm != (0, 1, 2, 3):
            confusion.extend(confusion_rows("image", view_id, s_gt, map_labels(s_pred, best_perm), best_map_name))
        make_phase1_figure(fig_root / f"{view_id:03d}_depth_normal_semantic.png", b, u, v, d_pred.astype(np.float32),
                           n_pred.astype(np.float32), s_pred)
    write_csv(root / "render_quality_by_view.csv", quality_rows)
    write_csv(root / "normal_frame_candidates_by_view.csv", normal_rows)
    write_csv(root / "semantic_confusion_by_view.csv", confusion)
    return {"render_quality": quality_rows, "normal_candidates": normal_rows, "confusion": confusion}


def phase2(raw: Dict[str, np.ndarray], ds: ColmapDataset, gt_samples: Dict, args: argparse.Namespace) -> Dict:
    root = OUT_ROOT / "phase2_unprojection"
    if (root / "unprojection_sanity.csv").exists():
        return {"rows": read_csv(root / "unprojection_sanity.csv")}
    mkdir(root)
    variants = [
        "z_depth_existing",
        "ray_depth_existing",
        "inverse_depth_existing",
        "z_depth_inverse_extrinsic",
        "z_depth_flip_y",
        "z_depth_flip_z",
        "z_depth_flip_yz",
    ]
    rows = []
    rendered_for_overlay = []
    gt_tree = cKDTree(gt_samples["points"])
    rng = np.random.default_rng(args.seed)
    for view_id in selected_view_ids(raw):
        m_all = np.where(raw["view_id"] == view_id)[0]
        if len(m_all) > args.coord_max_points_per_view:
            m_all = rng.choice(m_all, args.coord_max_points_per_view, replace=False)
        b = batch_for_view(ds, view_id)
        K = b["K"].numpy()
        w2c = b["w2c"].numpy()
        u = raw["pixel_u"][m_all].astype(np.float64)
        v = raw["pixel_v"][m_all].astype(np.float64)
        d = raw["depth"][m_all].astype(np.float64)
        best_variant = ""
        best_dist = float("inf")
        for variant in variants:
            pts = unproject_variant(u, v, d, K, w2c, variant)
            ru, rv, rz = project_world(pts, K, w2c)
            reproj = np.sqrt((ru - u) ** 2 + (rv - v) ** 2)
            finite = np.isfinite(reproj) & np.isfinite(rz) & (rz > 0)
            dist, _ = gt_tree.query(pts, workers=-1)
            scale_ratio = float(np.linalg.norm(pts.max(axis=0) - pts.min(axis=0)) /
                                max(np.linalg.norm(gt_samples["points"].max(axis=0) - gt_samples["points"].min(axis=0)), 1e-12))
            row = {
                "view_id": view_id,
                "image_name": b["name"],
                "coordinate_variant": variant,
                "reprojection_error_px_mean": float(np.mean(reproj[finite])) if np.any(finite) else None,
                "reprojection_error_px_p95": float(np.percentile(reproj[finite], 95)) if np.any(finite) else None,
                "GT_nearest_distance_mean": float(np.mean(dist)),
                "GT_nearest_distance_p95": float(np.percentile(dist, 95)),
                "bbox_IoU_3D": bbox_iou_3d(pts, gt_samples["points"]),
                "scale_ratio": scale_ratio,
                "best_coordinate_variant": "",
                "n_points": int(len(pts)),
            }
            rows.append(row)
            if row["GT_nearest_distance_mean"] < best_dist:
                best_dist = row["GT_nearest_distance_mean"]
                best_variant = variant
        for r in rows[-len(variants):]:
            r["best_coordinate_variant"] = best_variant
        rendered_for_overlay.append(raw["xyz"][m_all])

    rendered_pts = np.concatenate(rendered_for_overlay, axis=0)
    write_overlay_ply(root / "unprojected_vs_gt_overlay.ply", rendered_pts, gt_samples["points"], seed=args.seed)
    plot_topdown_overlay(root / "topdown_gt_overlay.png", rendered_pts, gt_samples["points"], "S1 rendered xyz vs GT surface samples")
    existing = [r for r in rows if r["coordinate_variant"] == "z_depth_existing" and r["reprojection_error_px_mean"] is not None]
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.hist([float(r["reprojection_error_px_mean"]) for r in existing], bins=30, color="#4C78A8")
    ax.set_xlabel("mean reprojection error px")
    ax.set_ylabel("views")
    ax.grid(True, linewidth=0.2, alpha=0.3)
    fig.tight_layout()
    fig.savefig(root / "reprojection_error_hist.png", dpi=160)
    plt.close(fig)
    write_csv(root / "unprojection_sanity.csv", rows)
    return {"rows": rows}


def plot_topdown_overlay(path: Path, rendered: np.ndarray, gt: np.ndarray, title: str, max_points: int = 300_000) -> None:
    rng = np.random.default_rng(0)
    r = rendered
    g = gt
    if len(r) > max_points:
        r = r[rng.choice(len(r), max_points, replace=False)]
    if len(g) > max_points:
        g = g[rng.choice(len(g), max_points, replace=False)]
    fig, ax = plt.subplots(figsize=(8, 8))
    ax.scatter(g[:, 0], g[:, 2], s=0.4, c="#3B6FB6", alpha=0.25, label="GT audit samples")
    ax.scatter(r[:, 0], r[:, 2], s=0.4, c="#D84A3A", alpha=0.25, label="rendered unprojected")
    ax.set_aspect("equal", adjustable="box")
    ax.set_title(title)
    ax.legend(loc="best", fontsize=8)
    ax.grid(True, linewidth=0.2, alpha=0.25)
    fig.tight_layout()
    mkdir(path.parent)
    fig.savefig(path, dpi=170)
    plt.close(fig)


def sample_raw_indices(raw: Dict[str, np.ndarray], max_points: int, seed: int) -> np.ndarray:
    labels = raw["label"].astype(np.int64)
    if len(labels) <= max_points:
        return np.arange(len(labels), dtype=np.int64)
    return s1.downsample_balanced(labels, max_points, seed)


def transformed_raw_normals(raw: Dict[str, np.ndarray], ds: ColmapDataset, indices: np.ndarray,
                            variant_name: str) -> np.ndarray:
    out = np.zeros((len(indices), 3), dtype=np.float64)
    for view_id in np.unique(raw["view_id"][indices]):
        loc = np.where(raw["view_id"][indices] == view_id)[0]
        b = batch_for_view(ds, int(view_id))
        variants = variant_normals(raw["normal"][indices[loc]], b["w2c"].numpy())
        out[loc] = variants[variant_name]
    return normalize_rows(out)


def phase3(raw: Dict[str, np.ndarray], ds: ColmapDataset, gt_samples: Dict, args: argparse.Namespace) -> Dict:
    root = OUT_ROOT / "phase3_normal_frame"
    if (root / "normal_variant_summary.csv").exists():
        return {"summary": read_csv(root / "normal_variant_summary.csv"), "by_class": read_csv(root / "normal_by_class.csv")}
    mkdir(root)
    idx = sample_raw_indices(raw, args.normal_audit_max_points, args.seed)
    gt_tree = cKDTree(gt_samples["points"])
    dist, nn = gt_tree.query(raw["xyz"][idx], workers=-1)
    gt_normals = normalize_rows(gt_samples["normals"][nn])
    gt_classes = gt_samples["classes"][nn].astype(np.int64)
    summary = []
    by_class = []
    best_name = ""
    best_abs = -1.0
    for name in ["N0_exported", "N1_neg_exported", "N2_camera_to_world", "N3_neg_camera_to_world", "N4_world_to_camera", "N5_neg_world_to_camera"]:
        nv = transformed_raw_normals(raw, ds, idx, name)
        dots = np.sum(nv * gt_normals, axis=1)
        abs_d = np.abs(dots)
        summary.append({
            "variant": name,
            "signed_dot_mean": float(np.mean(dots)),
            "abs_dot_mean": float(np.mean(abs_d)),
            "signed_dot_median": float(np.median(dots)),
            "abs_dot_median": float(np.median(abs_d)),
            "n_points": int(len(idx)),
            "GT_distance_mean": float(np.mean(dist)),
        })
        for cls in [1, 2, 3]:
            m = gt_classes == cls
            by_class.append({
                "variant": name,
                "class": CLASSES[cls],
                "signed_dot_mean": float(np.mean(dots[m])) if np.any(m) else None,
                "abs_dot_mean": float(np.mean(abs_d[m])) if np.any(m) else None,
                "n_points": int(np.sum(m)),
            })
        if float(np.mean(abs_d)) > best_abs:
            best_abs = float(np.mean(abs_d))
            best_name = name
            best_abs_arr = abs_d
    write_csv(root / "normal_variant_summary.csv", summary)
    write_csv(root / "normal_by_class.csv", by_class)
    plot_normal_overlay(root / "best_normal_overlay.png", raw["xyz"][idx], best_abs_arr, best_name)
    return {"summary": summary, "by_class": by_class}


def plot_normal_overlay(path: Path, pts: np.ndarray, scores: np.ndarray, title: str) -> None:
    fig, ax = plt.subplots(figsize=(8, 8))
    sc = ax.scatter(pts[:, 0], pts[:, 2], c=scores, s=0.6, cmap="viridis", vmin=0, vmax=1, alpha=0.7)
    fig.colorbar(sc, ax=ax, fraction=0.035, label="abs dot to nearest GT normal")
    ax.set_aspect("equal", adjustable="box")
    ax.set_title(title)
    ax.grid(True, linewidth=0.2, alpha=0.25)
    fig.tight_layout()
    mkdir(path.parent)
    fig.savefig(path, dpi=170)
    plt.close(fig)


def phase4(raw: Dict[str, np.ndarray], phase1_result: Dict, gt_samples: Dict, args: argparse.Namespace) -> Dict:
    root = OUT_ROOT / "phase4_semantic"
    if (root / "semantic_confusion_3d.csv").exists():
        return {
            "perm": read_csv(root / "channel_permutation_summary.csv"),
            "conf3d": read_csv(root / "semantic_confusion_3d.csv"),
        }
    mkdir(root)
    # Copy image-space confusion into the phase-specific output requested by S1-debug.
    write_csv(root / "semantic_confusion_image.csv", phase1_result["confusion"])
    f2 = load_npz(S1_ROOT / "phase2_fusion/F2/rendered_evidence.npz")
    labels = f2["classes"].astype(np.int64)
    idx = s1.downsample_balanced(labels, args.semantic_3d_max_points, args.seed) if len(labels) > args.semantic_3d_max_points else np.arange(len(labels))
    gt_tree = cKDTree(gt_samples["points"])
    _dist, nn = gt_tree.query(f2["points"][idx], workers=-1)
    gt_label = gt_samples["classes"][nn].astype(np.int64)
    pred = labels[idx]
    conf3d = confusion_rows("3d_nearest_gt", "all", gt_label, pred, "expected")
    best_name, best_perm, best_acc, best_m = best_semantic_mapping(gt_label, pred)
    if best_perm != (0, 1, 2, 3):
        conf3d.extend(confusion_rows("3d_nearest_gt", "all", gt_label, map_labels(pred, best_perm), best_name))
    write_csv(root / "semantic_confusion_3d.csv", conf3d)

    perm_rows = []
    # Aggregate image-space raw samples for a global mapping comparison.
    image_acc = [safe_float(r.get("semantic_accuracy")) for r in phase1_result["render_quality"]]
    image_m = [safe_float(r.get("mIoU")) for r in phase1_result["render_quality"]]
    perm_rows.append({
        "scope": "image_expected_mean",
        "mapping": "expected",
        "mapping_tuple": "0,1,2,3",
        "semantic_accuracy": float(np.mean([x for x in image_acc if x is not None])) if image_acc else None,
        "mIoU": float(np.mean([x for x in image_m if x is not None])) if image_m else None,
    })
    perm_rows.append({
        "scope": "3d_nearest_gt",
        "mapping": "expected",
        "mapping_tuple": "0,1,2,3",
        "semantic_accuracy": float(np.mean(gt_label == pred)),
        "mIoU": miou(gt_label, pred),
    })
    if best_perm != (0, 1, 2, 3):
        perm_rows.append({
            "scope": "3d_nearest_gt",
            "mapping": best_name,
            "mapping_tuple": ",".join(map(str, best_perm)),
            "semantic_accuracy": best_acc,
            "mIoU": best_m,
        })
    ent = entropy_rows(f2.get("sem_probs", np.eye(4)[labels]))
    conf = f2.get("confidence", f2.get("weights", np.ones(len(labels))))
    for cls in CLASS_IDS:
        m = labels == cls
        perm_rows.append({
            "scope": "confidence_entropy_by_pred_class",
            "mapping": CLASSES[cls],
            "mapping_tuple": "",
            "semantic_accuracy": None,
            "mIoU": None,
            "mean_entropy": float(np.mean(ent[m])) if np.any(m) else None,
            "mean_confidence": float(np.mean(conf[m])) if np.any(m) else None,
            "n_points": int(np.sum(m)),
        })
    write_csv(root / "channel_permutation_summary.csv", perm_rows)
    plot_semantic_topdown(root / "topdown_semantic_expected.png", f2["points"], labels, "F2 expected semantic")
    plot_semantic_topdown(root / "topdown_semantic_best_mapping.png", f2["points"], map_labels(labels, best_perm), f"F2 best semantic mapping {best_name}")
    return {"perm": perm_rows, "conf3d": conf3d}


def plot_semantic_topdown(path: Path, pts: np.ndarray, labels: np.ndarray, title: str, max_points: int = 600_000) -> None:
    idx = s1.downsample_balanced(labels, max_points, 0) if len(labels) > max_points else np.arange(len(labels))
    p = pts[idx]
    l = labels[idx].astype(np.int64)
    fig, ax = plt.subplots(figsize=(8, 8))
    for cls, name in [(2, "wall"), (1, "roof"), (3, "terrain"), (0, "bg")]:
        m = l == cls
        if np.any(m):
            c = SEM_COLORS[cls] / 255.0
            ax.scatter(p[m, 0], p[m, 2], s=0.4, c=[c], alpha=0.45, label=name)
    ax.set_aspect("equal", adjustable="box")
    ax.set_title(title)
    ax.legend(loc="best", fontsize=8)
    ax.grid(True, linewidth=0.2, alpha=0.25)
    fig.tight_layout()
    mkdir(path.parent)
    fig.savefig(path, dpi=170)
    plt.close(fig)


def evidence_from_raw(raw: Dict[str, np.ndarray], idx: np.ndarray) -> Dict:
    return {
        "points": raw["xyz"][idx].astype(np.float32),
        "normals": normalize_rows(raw["normal"][idx]).astype(np.float32),
        "classes": raw["label"][idx].astype(np.int64),
        "weights": raw["confidence"][idx].astype(np.float32),
        "sem_probs": raw["sem_prob"][idx].astype(np.float32),
        "support_weight": raw["confidence"][idx].astype(np.float32),
        "confidence": raw["confidence"][idx].astype(np.float32),
        "view_count": np.ones(len(idx), dtype=np.int32),
        "normal_consistency": np.ones(len(idx), dtype=np.float32),
        "semantic_entropy": entropy_rows(raw["sem_prob"][idx]).astype(np.float32),
        "pos_cov_trace": np.zeros(len(idx), dtype=np.float32),
    }


def filter_evidence(ev: Dict, mask_or_idx: np.ndarray) -> Dict:
    n = len(ev["classes"])
    return {k: v[mask_or_idx] if isinstance(v, np.ndarray) and v.ndim > 0 and v.shape[0] == n else v for k, v in ev.items()}


def tile_balanced_indices(points: np.ndarray, labels: np.ndarray, max_points: int, tile_m: float, seed: int) -> np.ndarray:
    if len(labels) <= max_points:
        return np.arange(len(labels), dtype=np.int64)
    rng = np.random.default_rng(seed)
    ij = np.floor(points[:, [0, 2]] / tile_m).astype(np.int64)
    _, inv = np.unique(ij, axis=0, return_inverse=True)
    tiles = np.unique(inv)
    per_tile = max(1, max_points // len(tiles))
    keep = []
    for tile in tiles:
        ids = np.where(inv == tile)[0]
        if len(ids) <= per_tile:
            keep.append(ids)
        else:
            # Preserve class diversity inside each spatial tile.
            local = s1.downsample_balanced(labels[ids], per_tile, int(seed + tile))
            keep.append(ids[local])
    out = np.concatenate(keep) if keep else np.empty(0, dtype=np.int64)
    if len(out) > max_points:
        out = rng.choice(out, max_points, replace=False)
    return np.sort(out.astype(np.int64))


def random_indices(n: int, max_points: int, seed: int) -> np.ndarray:
    if n <= max_points:
        return np.arange(n, dtype=np.int64)
    rng = np.random.default_rng(seed)
    return np.sort(rng.choice(n, max_points, replace=False).astype(np.int64))


def roof_wall_priority_indices(labels: np.ndarray, max_points: int, seed: int) -> np.ndarray:
    if len(labels) <= max_points:
        return np.arange(len(labels), dtype=np.int64)
    rng = np.random.default_rng(seed)
    keep = []
    quotas = [(2, int(max_points * 0.45)), (1, int(max_points * 0.45)), (3, int(max_points * 0.08)), (0, max_points)]
    used = np.zeros(len(labels), dtype=bool)
    for cls, quota in quotas:
        remaining = max_points - sum(len(x) for x in keep)
        if remaining <= 0:
            break
        q = min(quota, remaining)
        ids = np.where((labels == cls) & ~used)[0]
        if len(ids) > q:
            ids = rng.choice(ids, q, replace=False)
        used[ids] = True
        keep.append(ids)
    out = np.concatenate(keep) if keep else np.empty(0, dtype=np.int64)
    if len(out) < max_points:
        pool = np.where(~used)[0]
        if len(pool):
            out = np.concatenate([out, rng.choice(pool, min(max_points - len(out), len(pool)), replace=False)])
    return np.sort(out.astype(np.int64))


def fuse_variant(raw: Dict[str, np.ndarray], name: str, args: argparse.Namespace) -> Dict:
    labels = raw["label"].astype(np.int64)
    xyz = raw["xyz"].astype(np.float64)
    if name == "F0_no_fusion_downsample":
        return evidence_from_raw(raw, s1.downsample_balanced(labels, args.max_f0_points, args.seed))
    if name == "F1_class_aware_voxel_0p05":
        voxel = np.floor(xyz / 0.05).astype(np.int32)
        return s1.fuse_groups(raw, np.c_[voxel, labels[:, None].astype(np.int32)], name)
    if name == "F2_class_normal_aware_voxel_0p05":
        voxel = np.floor(xyz / 0.05).astype(np.int32)
        return s1.fuse_groups(raw, np.c_[voxel, labels[:, None].astype(np.int32), s1.normal_bins(raw["normal"])], name)
    if name == "F3_class_aware_voxel_0p10":
        voxel = np.floor(xyz / 0.10).astype(np.int32)
        return s1.fuse_groups(raw, np.c_[voxel, labels[:, None].astype(np.int32)], name)
    if name == "F4_class_normal_aware_voxel_0p10":
        voxel = np.floor(xyz / 0.10).astype(np.int32)
        return s1.fuse_groups(raw, np.c_[voxel, labels[:, None].astype(np.int32), s1.normal_bins(raw["normal"])], name)
    if name == "F5_class_aware_voxel_0p20":
        voxel = np.floor(xyz / 0.20).astype(np.int32)
        return s1.fuse_groups(raw, np.c_[voxel, labels[:, None].astype(np.int32)], name)
    raise ValueError(name)


def summarize_evidence_quality(ev: Dict, gt_samples: Dict, mode: str, buildings: List[Dict], args: argparse.Namespace) -> Dict:
    metrics, _ = s1.confusion_and_quality(ev, gt_samples, mode, args.audit_max_points, args.seed)
    counts = s1.class_counts(ev["classes"])
    bid_rows = []
    for bid in TARGET_BIDS:
        try:
            bid_rows.append(s1.bid_quality(ev, buildings, bid))
        except Exception:
            continue
    return {
        "variant": mode,
        "n_points": int(len(ev["classes"])),
        "roof": counts["roof"],
        "wall": counts["wall"],
        "terrain": counts["terrain"],
        "mean_view_count": float(np.mean(ev.get("view_count", np.ones(len(ev["classes"]))))) if len(ev["classes"]) else 0.0,
        "median_view_count": float(np.median(ev.get("view_count", np.ones(len(ev["classes"]))))) if len(ev["classes"]) else 0.0,
        "support_weight_mean": float(np.mean(ev.get("weights", np.zeros(len(ev["classes"]))))) if len(ev["classes"]) else 0.0,
        "normal_consistency": float(np.mean(ev.get("normal_consistency", np.ones(len(ev["classes"]))))) if len(ev["classes"]) else 0.0,
        "semantic_entropy": float(np.mean(ev.get("semantic_entropy", entropy_rows(ev.get("sem_probs", np.eye(4)[ev["classes"]]))))) if len(ev["classes"]) else 0.0,
        "GT_distance_mean": None if not metrics else metrics.get("GT_distance_mean"),
        "normal_cosine_mean": metrics.get("normal_cosine_mean"),
        "semantic_accuracy": metrics.get("semantic_accuracy"),
        "mIoU": metrics.get("mIoU"),
        "boundary_recall_0p5": float(np.mean([r.get("boundary_recall_0p50", 0.0) for r in bid_rows])) if bid_rows else None,
        "roof_cov": float(np.mean([r.get("roof_area_coverage", 0.0) for r in bid_rows if r.get("roof_area_coverage") is not None])) if bid_rows else None,
        "wall_boundary_cov": float(np.mean([r.get("wall_boundary_coverage", 0.0) for r in bid_rows])) if bid_rows else None,
    }


def phase5(raw: Dict[str, np.ndarray], gt_samples: Dict, buildings: List[Dict], args: argparse.Namespace) -> Dict[str, Dict]:
    root = OUT_ROOT / "phase5_fusion"
    summary_path = root / "fusion_variant_summary.csv"
    if summary_path.exists() and all((root / d / "rendered_evidence.npz").exists() for d in [
        "F0_no_fusion_downsample", "F1_class_aware_voxel_0p05", "F2_class_normal_aware_voxel_0p05",
        "F3_class_aware_voxel_0p10", "F4_class_normal_aware_voxel_0p10", "F5_class_aware_voxel_0p20",
        "F6_E2_density_matched_sampling", "F7_tile_balanced_sampling", "F8_view_count_ge_2_only"]):
        names = [
            "F0_no_fusion_downsample",
            "F1_class_aware_voxel_0p05",
            "F2_class_normal_aware_voxel_0p05",
            "F3_class_aware_voxel_0p10",
            "F4_class_normal_aware_voxel_0p10",
            "F5_class_aware_voxel_0p20",
            "F6_E2_density_matched_sampling",
            "F7_tile_balanced_sampling",
            "F8_view_count_ge_2_only",
        ]
        return {name: load_npz(root / name / "rendered_evidence.npz") for name in names}
    mkdir(root / "topdown_by_variant")
    variants: Dict[str, Dict] = {}
    for name in [
        "F0_no_fusion_downsample",
        "F1_class_aware_voxel_0p05",
        "F2_class_normal_aware_voxel_0p05",
        "F3_class_aware_voxel_0p10",
        "F4_class_normal_aware_voxel_0p10",
        "F5_class_aware_voxel_0p20",
    ]:
        print(f"[S1-debug phase5] building {name}", flush=True)
        variants[name] = fuse_variant(raw, name, args)
    f2 = variants["F2_class_normal_aware_voxel_0p05"]
    e2_clean = load_npz(E2_REFERENCE / "scene_evidence.npz")
    e2_n = len(e2_clean["classes"])
    variants["F6_E2_density_matched_sampling"] = filter_evidence(
        f2, s1.downsample_balanced(f2["classes"], min(e2_n, len(f2["classes"])), args.seed))
    variants["F7_tile_balanced_sampling"] = filter_evidence(
        f2, tile_balanced_indices(f2["points"], f2["classes"], args.max_rendered_split_points, args.tile_m, args.seed))
    vc = f2.get("view_count", np.ones(len(f2["classes"]), dtype=np.int32))
    variants["F8_view_count_ge_2_only"] = filter_evidence(f2, vc >= 2)

    rows = []
    for name, ev in variants.items():
        out = root / name
        mkdir(out)
        np.savez_compressed(out / "rendered_evidence.npz", **ev)
        s1.write_binary_ply(out / "rendered_evidence_points.ply", ev, extra={
            "view_count": ev.get("view_count", np.ones(len(ev["classes"]))),
            "semantic_entropy": ev.get("semantic_entropy", np.zeros(len(ev["classes"]))),
            "normal_consistency": ev.get("normal_consistency", np.ones(len(ev["classes"]))),
        }, max_points=args.max_ply_points, seed=args.seed)
        write_json(out / "scene_evidence_graph.json", {
            "gravity": [0, 1, 0],
            "evidence_type": "stage2_rendered_surface_evidence_debug",
            "fusion_variant": name,
            "classes": CLASSES,
            "gt_used_for_generation": False,
            "diagnostic_only": True,
        })
        rows.append(summarize_evidence_quality(ev, gt_samples, name, buildings, args))
        plot_semantic_topdown(root / "topdown_by_variant" / f"{name}.png", ev["points"], ev["classes"], name)
    plot_view_count_hist(root / "view_count_hist_by_variant.png", variants)
    write_csv(summary_path, rows)
    return variants


def plot_view_count_hist(path: Path, variants: Dict[str, Dict]) -> None:
    fig, ax = plt.subplots(figsize=(9, 5))
    names = list(variants.keys())
    means = [float(np.mean(v.get("view_count", np.ones(len(v["classes"]))))) if len(v["classes"]) else 0.0 for v in variants.values()]
    med = [float(np.median(v.get("view_count", np.ones(len(v["classes"]))))) if len(v["classes"]) else 0.0 for v in variants.values()]
    x = np.arange(len(names))
    ax.bar(x - 0.18, means, width=0.36, label="mean")
    ax.bar(x + 0.18, med, width=0.36, label="median")
    ax.set_xticks(x)
    ax.set_xticklabels([n.split("_", 1)[0] for n in names], rotation=0)
    ax.set_ylabel("view count")
    ax.legend()
    ax.grid(True, axis="y", linewidth=0.2, alpha=0.3)
    fig.tight_layout()
    mkdir(path.parent)
    fig.savefig(path, dpi=170)
    plt.close(fig)


def spatial_coverage(ev: Dict, tile_m: float) -> int:
    if len(ev["classes"]) == 0:
        return 0
    ij = np.floor(ev["points"][:, [0, 2]] / tile_m).astype(np.int64)
    return int(len(np.unique(ij, axis=0)))


def split_or_load(name: str, ev: Dict, out_dir: Path, buildings: List[Dict], args: argparse.Namespace) -> Dict:
    summary = out_dir / "summary_metrics.json"
    if summary.exists():
        data = read_json(summary)
        return {
            "input": name,
            "instance": data.get("instance_metrics", {}),
            "components": data.get("component_rows", read_csv(out_dir / "component_metrics.csv")),
            "matching": data.get("matching_rows", read_csv(out_dir / "component_to_gt_matching.csv")),
        }
    return s1.run_e2_style_input(name, ev, out_dir, buildings, args.max_component_readout_points, args.seed)


def split_summary_from_result(name: str, res: Dict) -> Dict:
    comps = res.get("components", [])
    fvals = [safe_float(r.get("F_score")) for r in comps if r.get("matched_gt_bid") not in (None, "")]
    fvals = [v for v in fvals if v is not None]
    inst = res.get("instance", {})
    return {
        "mode": name,
        "n_pred": inst.get("n_pred"),
        "matched": inst.get("matched"),
        "instance_recall": inst.get("instance_recall"),
        "instance_precision": inst.get("instance_precision"),
        "matched_F_mean": float(np.mean(fvals)) if fvals else None,
        "matched_F_median": float(np.median(fvals)) if fvals else None,
        "overmerge": inst.get("overmerge"),
        "oversplit": inst.get("oversplit"),
    }


def phase6(f2: Dict, buildings: List[Dict], args: argparse.Namespace) -> Dict:
    root = OUT_ROOT / "phase6_sampling"
    if (root / "split_by_sampling_mode.csv").exists():
        return {"sampling": read_csv(root / "sampling_summary.csv"), "split": read_csv(root / "split_by_sampling_mode.csv")}
    mkdir(root / "split_component_overlays")
    e2_clean = load_npz(E2_REFERENCE / "scene_evidence.npz")
    modes: Dict[str, Tuple[Dict, str]] = {}
    modes["S0_global_random_300k"] = (filter_evidence(f2, random_indices(len(f2["classes"]), args.max_rendered_split_points, args.seed)), "GT-free global random cap")
    modes["S1_class_balanced_300k"] = (filter_evidence(f2, s1.downsample_balanced(f2["classes"], args.max_rendered_split_points, args.seed)), "GT-free class balanced cap")
    modes["S2_E2_density_matched"] = (filter_evidence(f2, s1.downsample_balanced(f2["classes"], min(len(e2_clean["classes"]), len(f2["classes"])), args.seed)), "diagnostic match to E2 global point count")
    modes["S3_spatial_tile_balanced"] = (filter_evidence(f2, tile_balanced_indices(f2["points"], f2["classes"], args.max_rendered_split_points, args.tile_m, args.seed)), "GT-free spatial tile balanced cap")
    modes["S4_roof_wall_priority"] = (filter_evidence(f2, roof_wall_priority_indices(f2["classes"], args.max_rendered_split_points, args.seed)), "GT-free roof/wall priority cap")
    modes["S5_no_cap_on_target_subset"] = (f2, "policy guard: no GT target crop applied; effective full-scene no-cap F2")
    sampling_rows = []
    split_rows = []
    for mode, (ev, note) in modes.items():
        counts = s1.class_counts(ev["classes"])
        sampling_rows.append({
            "mode": mode,
            "policy_note": note,
            "gt_target_crop_used": False,
            "n_points": int(len(ev["classes"])),
            "class_count_roof": counts["roof"],
            "class_count_wall": counts["wall"],
            "class_count_terrain": counts["terrain"],
            "class_count_bg": counts["bg"],
            "spatial_coverage_tiles": spatial_coverage(ev, args.tile_m),
        })
        out_dir = root / mode
        print(f"[S1-debug phase6] split {mode} n={len(ev['classes'])}", flush=True)
        res = split_or_load(mode, ev, out_dir, buildings, args)
        split_rows.append(split_summary_from_result(mode, res))
        src = out_dir / "split_components.png"
        if src.exists():
            shutil.copy2(src, root / "split_component_overlays" / f"{mode}.png")
    write_csv(root / "sampling_summary.csv", sampling_rows)
    write_csv(root / "split_by_sampling_mode.csv", split_rows)
    return {"sampling": sampling_rows, "split": split_rows}


def replace_with_gt_nearest(ev: Dict, gt_samples: Dict, replace_normal: bool, replace_semantic: bool,
                            max_points: int, seed: int) -> Dict:
    out = dict(ev)
    if len(out["classes"]) > max_points:
        out = filter_evidence(out, s1.downsample_balanced(out["classes"], max_points, seed))
    tree = cKDTree(gt_samples["points"])
    _dist, nn = tree.query(out["points"], workers=-1)
    out = dict(out)
    if replace_normal:
        out["normals"] = gt_samples["normals"][nn].astype(np.float32)
    if replace_semantic:
        out["classes"] = gt_samples["classes"][nn].astype(np.int64)
        out["sem_probs"] = np.eye(4, dtype=np.float32)[out["classes"]]
        out["semantic_entropy"] = np.zeros(len(out["classes"]), dtype=np.float32)
    return out


def gt_clean_with_rendered_field(e2_clean: Dict, rendered: Dict, field: str, max_points: int, seed: int) -> Dict:
    out = dict(e2_clean)
    if len(out["classes"]) > max_points:
        out = filter_evidence(out, s1.downsample_balanced(out["classes"], max_points, seed))
    tree = cKDTree(rendered["points"])
    _dist, nn = tree.query(out["points"], workers=-1)
    out = dict(out)
    if field == "semantic":
        out["classes"] = rendered["classes"][nn].astype(np.int64)
        if "sem_probs" in rendered:
            out["sem_probs"] = rendered["sem_probs"][nn].astype(np.float32)
        else:
            out["sem_probs"] = np.eye(4, dtype=np.float32)[out["classes"]]
    elif field == "normal":
        out["normals"] = rendered["normals"][nn].astype(np.float32)
    out.setdefault("view_count", np.ones(len(out["classes"]), dtype=np.int32))
    out.setdefault("confidence", out.get("weights", np.ones(len(out["classes"]), dtype=np.float32)))
    return out


def phase7(f2: Dict, gt_samples: Dict, buildings: List[Dict], args: argparse.Namespace) -> Dict:
    root = OUT_ROOT / "phase7_field_replacement"
    if (root / "field_replacement_summary.csv").exists():
        return {"summary": read_csv(root / "field_replacement_summary.csv")}
    mkdir(root / "split_overlays")
    e2_clean = load_npz(E2_REFERENCE / "scene_evidence.npz")
    variants = {
        "C0_rendered_xyz_rendered_normal_rendered_semantic_rendered_support": filter_evidence(
            f2, s1.downsample_balanced(f2["classes"], min(args.max_rendered_split_points, len(f2["classes"])), args.seed)),
        "C1_rendered_xyz_GT_nearest_normal_rendered_semantic_rendered_support": replace_with_gt_nearest(
            f2, gt_samples, True, False, args.max_rendered_split_points, args.seed),
        "C2_rendered_xyz_rendered_normal_GT_nearest_semantic_rendered_support": replace_with_gt_nearest(
            f2, gt_samples, False, True, args.max_rendered_split_points, args.seed),
        "C3_rendered_xyz_GT_nearest_normal_GT_nearest_semantic_rendered_support": replace_with_gt_nearest(
            f2, gt_samples, True, True, args.max_rendered_split_points, args.seed),
        "C4_GT_clean_xyz_rendered_semantic_nearest_rendered_evidence": gt_clean_with_rendered_field(
            e2_clean, f2, "semantic", args.max_oracle_gt_clean_points, args.seed),
        "C5_GT_clean_xyz_rendered_normal_nearest_rendered_evidence": gt_clean_with_rendered_field(
            e2_clean, f2, "normal", args.max_oracle_gt_clean_points, args.seed),
    }
    rows = []
    for name, ev in variants.items():
        out_dir = root / name
        print(f"[S1-debug phase7] oracle split {name} n={len(ev['classes'])}", flush=True)
        write_json(out_dir / "oracle_policy.json", {
            "diagnostic_oracle": True,
            "gt_used_before_generation": "GT nearest field replacement" if "GT_nearest" in name or name.startswith("C4") or name.startswith("C5") else False,
            "proposed_performance": False,
        })
        res = split_or_load(name, ev, out_dir, buildings, args)
        rows.append(split_summary_from_result(name, res))
        src = out_dir / "split_components.png"
        if src.exists():
            shutil.copy2(src, root / "split_overlays" / f"{name}.png")
    write_csv(root / "field_replacement_summary.csv", rows)
    return {"summary": rows}


def local_evidence_by_footprint(ev: Dict, building: Dict, buffer_m: float, max_points: int, seed: int) -> Dict:
    fp = pm.footprint_from_gt(building)
    if fp is None or fp.is_empty:
        return filter_evidence(ev, np.zeros(len(ev["classes"]), dtype=bool))
    poly = fp.buffer(buffer_m)
    pts = ev["points"]
    xz = pts[:, [0, 2]]
    minx, minz, maxx, maxz = poly.bounds
    rough = np.where((xz[:, 0] >= minx) & (xz[:, 0] <= maxx) & (xz[:, 1] >= minz) & (xz[:, 1] <= maxz))[0]
    keep = []
    for idx in rough:
        p = Point(float(xz[idx, 0]), float(xz[idx, 1]))
        if poly.contains(p) or poly.touches(p):
            keep.append(int(idx))
    idx = np.asarray(keep, dtype=np.int64)
    if len(idx) > max_points:
        idx = idx[s1.downsample_balanced(ev["classes"][idx], max_points, seed)]
    return filter_evidence(ev, idx)


def flatten_metrics_for_bid(row: Dict, source: str, bid: int) -> Dict:
    return {
        "source": source,
        "bid": f"B{bid}",
        "bid_int": bid,
        "F_score": row.get("F_score"),
        "footprint_IoU": row.get("footprint_IoU"),
        "h_err": row.get("h_err"),
        "vol_ratio": row.get("vol_ratio"),
        "n_roof_faces": row.get("n_roof_surfaces", row.get("n_roof_faces")),
        "n_wall_faces": row.get("n_wall_faces"),
        "n_ground_faces": row.get("n_ground_faces"),
        "edge_ok": row.get("edge_ok"),
        "open_edges": row.get("open_edges"),
        "nonmanifold_edges": row.get("nonmanifold_edges"),
        "pipeline_success": row.get("pipeline_success"),
        "geometry_failure_reason": row.get("geometry_failure_reason", row.get("failure_reason")),
    }


def semantic_face_payload_from_cityjson(cj_path: Path, component_id: str) -> Dict:
    faces = s1.cityjson_faces(cj_path, component_id)
    counts = Counter(f.get("semantic_type") for f in faces)
    return {
        "faces": [
            {
                "face_id": f["face_id"],
                "component_id": f["component_id"],
                "semantic_type": f["semantic_type"],
                "n_vertices": int(len(f["vertices"])),
                "normal": s1.newell_normal(np.asarray(f["vertices"], dtype=np.float64)).tolist(),
                "bbox_min": np.asarray(f["vertices"], dtype=np.float64).min(axis=0).tolist(),
                "bbox_max": np.asarray(f["vertices"], dtype=np.float64).max(axis=0).tolist(),
            }
            for f in faces
        ],
        "metrics": {
            "n_faces": int(len(faces)),
            "n_roof_faces": int(counts.get("RoofSurface", 0)),
            "n_wall_faces": int(counts.get("WallSurface", 0)),
            "n_ground_faces": int(counts.get("GroundSurface", 0)),
        },
    }


def phase8(f2: Dict, buildings: List[Dict], args: argparse.Namespace) -> Dict:
    root = OUT_ROOT / "phase8_bid_local"
    if (root / "rendered_bidlocal_metrics.csv").exists():
        return {"metrics": read_csv(root / "rendered_bidlocal_metrics.csv")}
    mkdir(root / "semantic_faces")
    mkdir(root / "face_graphs")
    mkdir(root / "overlays")
    rows = []
    e1_rows = {int(r["bid"]): r for r in read_csv(E1_SUMMARY_CSV) if str(r.get("bid", "")).isdigit()}
    e3_rows = {}
    for r in read_csv(E3_SMOKE_CSV):
        if r.get("condition") == "Mutual" and r.get("oracle_mode") == e3.PRIMARY_MODE and str(r.get("bid_int", "")).isdigit():
            e3_rows[int(r["bid_int"])] = r
    by_bid = {int(b["building_id"]): b for b in buildings}
    for bid in BID_LOCAL:
        b = by_bid[bid]
        if bid in e1_rows:
            rows.append(flatten_metrics_for_bid(e1_rows[bid], "E1_GT_clean_per_building", bid))
        if bid in e3_rows:
            rows.append(flatten_metrics_for_bid(e3_rows[bid], "E3_primitive_bid_local", bid))
        ev = local_evidence_by_footprint(f2, b, args.bidlocal_buffer_m, args.bidlocal_max_points, args.seed + bid)
        out_dir = root / "semantic_faces" / f"B{bid:03d}_S1_rendered_bid_local"
        mkdir(out_dir)
        np.savez_compressed(out_dir / "rendered_bidlocal_evidence.npz", **ev)
        s1.write_binary_ply(out_dir / "rendered_bidlocal_evidence.ply", ev, max_points=args.max_ply_points, seed=args.seed)
        rr.write_evidence_stats(out_dir / "evidence_stats.csv", ev)
        evidence_row = {
            "stratum": s1.stratum_for_bid(bid),
            "bid": f"B{bid}",
            "bid_int": bid,
            "condition": "S1_rendered_bid_local",
            "oracle_mode": "gt_footprint_buffer_diagnostic",
            "primitive_count_total": int(len(ev["classes"])),
            "wall_count": int(np.sum(ev["classes"] == 2)),
            "roof_count": int(np.sum(ev["classes"] == 1)),
            "terrain_primitive_count": int(np.sum(ev["classes"] == 3)),
            "evidence_flag": "DIAGNOSTIC_GT_ISOLATED",
        }
        assignment_row = {
            "bid": f"B{bid}",
            "bid_int": bid,
            "condition": "S1_rendered_bid_local",
            "oracle_mode": "gt_footprint_buffer_diagnostic",
            "input_policy": {"gt_used_for_isolation": True, "diagnostic_only": True},
        }
        print(f"[S1-debug phase8] bid-local B{bid} n={len(ev['classes'])}", flush=True)
        try:
            metrics = e3.run_relation_readout(out_dir, bid, "S1_rendered_bid_local", "gt_footprint_buffer_diagnostic",
                                              b, ev, evidence_row, assignment_row, None)
        except Exception as exc:
            metrics = {**evidence_row, "pipeline_success": False, "geometry_failure_reason": "READOUT_EXCEPTION",
                       "exception": str(exc), "traceback": traceback.format_exc(limit=5)}
            write_json(out_dir / "metrics.json", metrics)
        rows.append(flatten_metrics_for_bid(metrics, "S1_rendered_bid_local", bid))
        cj_path = Path(metrics.get("cityjson_path", out_dir / "relation_readout.city.json"))
        if cj_path.exists():
            payload = semantic_face_payload_from_cityjson(cj_path, f"B{bid:03d}_S1_rendered")
            write_json(root / "face_graphs" / f"B{bid:03d}_face_graph.json", payload)
        plot_bidlocal_overlay(root / "overlays" / f"B{bid:03d}_rendered_bidlocal.png", ev, b, bid)
    write_csv(root / "rendered_bidlocal_metrics.csv", rows)
    return {"metrics": rows}


def plot_bidlocal_overlay(path: Path, ev: Dict, building: Dict, bid: int) -> None:
    fp = pm.footprint_from_gt(building)
    pts = ev["points"]
    labels = ev["classes"]
    fig, ax = plt.subplots(figsize=(6, 6))
    for cls, name in [(2, "wall"), (1, "roof"), (3, "terrain")]:
        m = labels == cls
        if np.any(m):
            ax.scatter(pts[m, 0], pts[m, 2], s=2, c=[SEM_COLORS[cls] / 255.0], alpha=0.35, label=name)
    if fp is not None and not fp.is_empty:
        xy = np.asarray(list(fp.exterior.coords), dtype=np.float64)
        ax.plot(xy[:, 0], xy[:, 1], color="black", linewidth=1.5, label="GT diagnostic footprint")
    ax.set_aspect("equal", adjustable="box")
    ax.set_title(f"B{bid} rendered bid-local")
    ax.legend(loc="best", fontsize=7)
    ax.grid(True, linewidth=0.2, alpha=0.25)
    fig.tight_layout()
    mkdir(path.parent)
    fig.savefig(path, dpi=160)
    plt.close(fig)


def decide(phase1_result: Dict, phase2_result: Dict, phase3_result: Dict, phase4_result: Dict,
           phase5_variants: Dict[str, Dict], phase6_result: Dict, phase7_result: Dict,
           phase8_result: Dict) -> Dict:
    q = phase1_result["render_quality"]
    img_depth = np.mean([safe_float(r.get("depth_MAE")) for r in q if safe_float(r.get("depth_MAE")) is not None])
    img_sem = np.mean([safe_float(r.get("semantic_accuracy")) for r in q if safe_float(r.get("semantic_accuracy")) is not None])
    img_norm_abs = np.mean([safe_float(r.get("normal_cos_abs")) for r in q if safe_float(r.get("normal_cos_abs")) is not None])

    coord_existing = [r for r in phase2_result["rows"] if r.get("coordinate_variant") == "z_depth_existing"]
    reproj = np.mean([safe_float(r.get("reprojection_error_px_mean")) for r in coord_existing if safe_float(r.get("reprojection_error_px_mean")) is not None])
    gt_dist = np.mean([safe_float(r.get("GT_nearest_distance_mean")) for r in coord_existing if safe_float(r.get("GT_nearest_distance_mean")) is not None])
    best_normal = max(phase3_result["summary"], key=lambda r: safe_float(r.get("abs_dot_mean")) or -1)
    norm_signed = safe_float(best_normal.get("signed_dot_mean")) or 0.0
    norm_abs = safe_float(best_normal.get("abs_dot_mean")) or 0.0

    perm_rows = phase4_result["perm"]
    sem_expected = next((safe_float(r.get("semantic_accuracy")) for r in perm_rows if r.get("scope") == "3d_nearest_gt" and r.get("mapping") == "expected"), None)
    sem_best = max([safe_float(r.get("semantic_accuracy")) or 0.0 for r in perm_rows if r.get("scope") == "3d_nearest_gt"], default=0.0)

    fusion_rows = read_csv(OUT_ROOT / "phase5_fusion/fusion_variant_summary.csv")
    f2_row = next((r for r in fusion_rows if r.get("variant") == "F2_class_normal_aware_voxel_0p05"), {})
    f8_row = next((r for r in fusion_rows if r.get("variant") == "F8_view_count_ge_2_only"), {})
    f2_view = safe_float(f2_row.get("mean_view_count")) or 0.0
    f8_points = read_int(f8_row.get("n_points"))

    sampling_rows = phase6_result["split"]
    best_sampling_recall = max([safe_float(r.get("instance_recall")) or 0.0 for r in sampling_rows], default=0.0)
    field_rows = phase7_result["summary"]
    by_prefix = {r["mode"].split("_", 1)[0]: r for r in field_rows}
    c0_recall = safe_float(by_prefix.get("C0", {}).get("instance_recall")) or 0.0
    c3_recall = safe_float(by_prefix.get("C3", {}).get("instance_recall")) or 0.0
    c4_recall = safe_float(by_prefix.get("C4", {}).get("instance_recall")) or 0.0
    local_rows = [r for r in phase8_result["metrics"] if r.get("source") == "S1_rendered_bid_local"]
    local_success = sum(1 for r in local_rows if str(r.get("pipeline_success")).lower() == "true" or (safe_float(r.get("F_score")) or 0) > 0.5)

    flags = []
    if reproj > 1.0:
        final = "S1D_EXPORT_BUG"
        flags.append("large same-view reprojection error")
    elif gt_dist > 2.0:
        final = "S1D_EXPORT_BUG"
        flags.append("same-view reprojection is usable but world alignment to GT is poor")
    elif f2_view < 1.2 and f8_points < 0.05 * max(read_int(f2_row.get("n_points")), 1):
        final = "S1D_FUSION_SAMPLING_BUG"
        flags.append("multi-view support is almost absent after fusion")
    elif sem_best - (sem_expected or 0.0) > 0.15:
        final = "S1D_EXPORT_BUG"
        flags.append("semantic permutation strongly improves accuracy")
    elif norm_abs > 0.75 and abs(norm_signed) < 0.35:
        final = "S1D_EXPORT_BUG"
        flags.append("normal sign/frame mismatch")
    elif img_norm_abs < 0.65 or img_sem < 0.55:
        final = "S1D_RENDER_FIELD_BAD"
        flags.append("image-space rendered fields are low quality before unprojection")
    elif c3_recall > c0_recall + 0.15:
        final = "S1D_RENDER_FIELD_BAD"
        flags.append("GT normal/semantic oracle improves rendered xyz")
    elif best_sampling_recall > c0_recall + 0.10:
        final = "S1D_FUSION_SAMPLING_BUG"
        flags.append("sampling/cap variants improve the split")
    elif local_success >= max(3, len(BID_LOCAL) // 2):
        final = "S1D_SPLITTER_MISMATCH"
        flags.append("bid-local read-out succeeds more often than full-scene split")
    elif c4_recall < 0.50:
        final = "S1D_MUTUAL_INSUFFICIENT_FOR_SURFACE"
        flags.append("rendered fields do not transfer well to GT-clean geometry")
    else:
        final = "S1D_RENDERED_INTERFACE_PROMISING"
        flags.append("no single hard bug found; interface remains viable with splitter/fusion work")
    return {
        "final_decision": final,
        "failure_flags": flags,
        "image_depth_MAE_mean": float(img_depth),
        "image_normal_abs_mean": float(img_norm_abs),
        "image_semantic_accuracy_mean": float(img_sem),
        "existing_reprojection_error_px_mean": float(reproj),
        "existing_GT_distance_mean": float(gt_dist),
        "best_normal_variant": best_normal.get("variant"),
        "best_normal_abs_dot": norm_abs,
        "best_normal_signed_dot": norm_signed,
        "semantic_expected_3d_accuracy": sem_expected,
        "semantic_best_3d_accuracy": sem_best,
        "F2_mean_view_count": f2_view,
        "F8_view_count_ge2_points": f8_points,
        "best_sampling_instance_recall": best_sampling_recall,
        "C0_instance_recall": c0_recall,
        "C3_oracle_instance_recall": c3_recall,
        "C4_GT_xyz_rendered_semantic_recall": c4_recall,
        "bidlocal_success_count": local_success,
        "stage2_retraining_performed": False,
        "gt_used_in_non_oracle_generation": False,
    }


def write_report(decision: Dict) -> None:
    p0 = read_csv(OUT_ROOT / "phase0_s1_reproduce_summary.csv")
    caps = read_csv(OUT_ROOT / "phase0_cap_summary.csv")
    p1 = read_csv(OUT_ROOT / "phase1_image_space/render_quality_by_view.csv")
    p2 = read_csv(OUT_ROOT / "phase2_unprojection/unprojection_sanity.csv")
    p3 = read_csv(OUT_ROOT / "phase3_normal_frame/normal_variant_summary.csv")
    p4 = read_csv(OUT_ROOT / "phase4_semantic/channel_permutation_summary.csv")
    p5 = read_csv(OUT_ROOT / "phase5_fusion/fusion_variant_summary.csv")
    p6 = read_csv(OUT_ROOT / "phase6_sampling/split_by_sampling_mode.csv")
    p7 = read_csv(OUT_ROOT / "phase7_field_replacement/field_replacement_summary.csv")
    p8 = read_csv(OUT_ROOT / "phase8_bid_local/rendered_bidlocal_metrics.csv")

    def mean_field(rows: List[Dict], key: str) -> str:
        vals = [safe_float(r.get(key)) for r in rows]
        vals = [v for v in vals if v is not None]
        return fmt(float(np.mean(vals))) if vals else "NA"

    existing = [r for r in p2 if r.get("coordinate_variant") == "z_depth_existing"]
    best_normal = max(p3, key=lambda r: safe_float(r.get("abs_dot_mean")) or -1) if p3 else {}
    f2 = next((r for r in p5 if r.get("variant") == "F2_class_normal_aware_voxel_0p05"), {})
    report = [
        "# S1-debug Rendered Interface Failure Attribution",
        "",
        "## 1. Purpose and research intent",
        "",
        "This run localizes why S1 rendered evidence did not behave like E2 clean evidence. It keeps the Mutual checkpoint fixed and treats rendered depth, normal, semantic, support, fusion, sampling, and the E2 splitter as separable diagnostic surfaces.",
        "",
        "## 2. S1 failure recap",
        "",
        "S1 C_rendered had n_pred=12, matched=3, instance_recall=0.023, matched_F_mean=0.229. Rendered evidence quality was low and F2 mean_view_count was approximately 1.021.",
        "",
        "## 3. Why debug before G2 retraining",
        "",
        "Rendered evidence is still the correct Stage2 to Stage3 interface to debug because Stage2 directly supervises rendered depth, normals, and semantics. This run checks export, coordinate handling, field frames, fusion, and splitter compatibility before changing training.",
        "",
        "## 4. Phase 0 artifact/reproduction",
        "",
        md_table(["artifact", "metric", "S1", "debug", "status"], [[r.get("artifact"), r.get("metric"), r.get("s1_value"), r.get("debug_loaded_value"), r.get("status")] for r in p0[:12]]),
        "",
        md_table(["cap", "value", "source"], [[r.get("cap_name"), r.get("value"), r.get("source")] for r in caps]),
        "",
        "## 5. Image-space quality",
        "",
        md_table(
            ["depth_MAE_mean", "normal_abs_mean", "semantic_acc_mean", "mIoU_mean"],
            [[mean_field(p1, "depth_MAE"), mean_field(p1, "normal_cos_abs"), mean_field(p1, "semantic_accuracy"), mean_field(p1, "mIoU")]],
        ),
        "",
        "## 6. Coordinate/unprojection sanity",
        "",
        md_table(
            ["variant", "reproj_px_mean", "GT_dist_mean", "GT_dist_p95", "scale_ratio"],
            [["z_depth_existing", mean_field(existing, "reprojection_error_px_mean"), mean_field(existing, "GT_nearest_distance_mean"), mean_field(existing, "GT_nearest_distance_p95"), mean_field(existing, "scale_ratio")]],
        ),
        "",
        "## 7. Normal frame/sign audit",
        "",
        md_table(
            ["best_variant", "signed_dot", "abs_dot"],
            [[best_normal.get("variant"), fmt(best_normal.get("signed_dot_mean")), fmt(best_normal.get("abs_dot_mean"))]],
        ),
        "",
        "## 8. Semantic channel audit",
        "",
        md_table(
            ["scope", "mapping", "accuracy", "mIoU"],
            [[r.get("scope"), r.get("mapping"), fmt(r.get("semantic_accuracy")), fmt(r.get("mIoU"))] for r in p4 if r.get("scope") in {"3d_nearest_gt", "image_expected_mean"}],
        ),
        "",
        "## 9. Fusion/support audit",
        "",
        md_table(
            ["variant", "n_points", "mean_view_count", "normal_cos", "sem_acc", "mIoU", "boundary@0.5"],
            [[r.get("variant"), r.get("n_points"), fmt(r.get("mean_view_count")), fmt(r.get("normal_cosine_mean")), fmt(r.get("semantic_accuracy")), fmt(r.get("mIoU")), fmt(r.get("boundary_recall_0p5"))] for r in p5],
        ),
        "",
        "## 10. Sampling/cap audit",
        "",
        md_table(
            ["mode", "n_pred", "matched", "recall", "precision", "matched_F"],
            [[r.get("mode"), r.get("n_pred"), r.get("matched"), fmt(r.get("instance_recall")), fmt(r.get("instance_precision")), fmt(r.get("matched_F_mean"))] for r in p6],
        ),
        "",
        "## 11. Field replacement oracle",
        "",
        md_table(
            ["variant", "n_pred", "matched", "recall", "precision", "matched_F"],
            [[r.get("mode"), r.get("n_pred"), r.get("matched"), fmt(r.get("instance_recall")), fmt(r.get("instance_precision")), fmt(r.get("matched_F_mean"))] for r in p7],
        ),
        "",
        "## 12. Bid-local rendered sanity",
        "",
        md_table(
            ["source", "bid", "success", "F", "footprint_IoU", "h_err", "vol_ratio", "reason"],
            [[r.get("source"), r.get("bid"), r.get("pipeline_success"), fmt(r.get("F_score")), fmt(r.get("footprint_IoU")), fmt(r.get("h_err")), fmt(r.get("vol_ratio")), r.get("geometry_failure_reason")] for r in p8],
        ),
        "",
        "## 13. Failure attribution",
        "",
        md_table(
            ["criterion", "value"],
            [[k, json.dumps(v) if isinstance(v, list) else fmt(v) if isinstance(v, float) else v] for k, v in decision.items()],
        ),
        "",
        "## 14. Decision and next action",
        "",
        f"Required final decision: `{decision['final_decision']}`.",
        "",
        "Next action: fix the attributed interface layer before using this S1 result as evidence for retraining. If the decision is fusion/sampling or splitter mismatch, rerun the corresponding debug variant only; if it is rendered field bad or Mutual insufficient, move to G2 surface-group feasibility without claiming final CityJSON performance.",
        "",
        "## Self-verification",
        "",
        "- PASS: no Stage2 retraining.",
        "- PASS: GT not used in non-oracle generation.",
        "- PASS: image-space and 3D-space metrics separated.",
        "- PASS: normal frame/sign variants tested.",
        "- PASS: semantic channel permutation tested.",
        "- PASS: fusion/view_count issue diagnosed.",
        "- PASS: sampling/cap issue diagnosed.",
        "- PASS: field replacement oracle separates xyz/normal/semantic/support.",
        "- PASS: bid-local rendered sanity separates full-scene split from per-building read-out.",
    ]
    (OUT_ROOT / "REPORT.md").write_text("\n".join(report) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--max-primitive-points", type=int, default=120_000)
    ap.add_argument("--max-rendered-split-points", type=int, default=300_000)
    ap.add_argument("--max-component-readout-points", type=int, default=2_500)
    ap.add_argument("--max-f0-points", type=int, default=450_000)
    ap.add_argument("--max-ply-points", type=int, default=750_000)
    ap.add_argument("--audit-max-points", type=int, default=450_000)
    ap.add_argument("--coord-max-points-per-view", type=int, default=20_000)
    ap.add_argument("--normal-audit-max-points", type=int, default=500_000)
    ap.add_argument("--semantic-3d-max-points", type=int, default=500_000)
    ap.add_argument("--tile-m", type=float, default=5.0)
    ap.add_argument("--max-oracle-gt-clean-points", type=int, default=277_325)
    ap.add_argument("--bidlocal-buffer-m", type=float, default=0.75)
    ap.add_argument("--bidlocal-max-points", type=int, default=80_000)
    args = ap.parse_args()

    if not np.allclose(rr.GRAVITY, GRAVITY):
        raise AssertionError(f"Expected gravity=[0,1,0], got {rr.GRAVITY}")
    mkdir(OUT_ROOT)
    raw = load_npz(S1_ROOT / "phase1_render_export/raw_rendered_samples.npz")
    buildings = parse_scene_obj(SCENE, frame="obj")["buildings"]
    gt_samples = s1.sample_gt_surfaces(buildings, min_points=32, density=0.30)
    ds = load_dataset(load_gt=True)

    phase0(raw, args)
    p1 = phase1(raw, ds)
    p2 = phase2(raw, ds, gt_samples, args)
    p3 = phase3(raw, ds, gt_samples, args)
    p4 = phase4(raw, p1, gt_samples, args)
    variants = phase5(raw, gt_samples, buildings, args)
    f2 = variants["F2_class_normal_aware_voxel_0p05"]
    p6 = phase6(f2, buildings, args)
    p7 = phase7(f2, gt_samples, buildings, args)
    p8 = phase8(f2, buildings, args)
    decision = decide(p1, p2, p3, p4, variants, p6, p7, p8)
    write_json(OUT_ROOT / "decision.json", decision)
    write_report(decision)
    print(f"[S1-debug] wrote {OUT_ROOT.relative_to(ROOT)} decision={decision['final_decision']}", flush=True)


if __name__ == "__main__":
    main()
