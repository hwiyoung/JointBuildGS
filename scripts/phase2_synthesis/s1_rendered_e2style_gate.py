"""S1: Stage2 rendered surface evidence -> E2-style full-scene split gate.

This experiment changes the Stage2->Stage3 interface, not the Stage3 geometry
target.  It exports rendered depth/normal/semantic/alpha samples from the
Mutual checkpoint, fuses duplicate multi-view samples into E2-style surface
evidence, then runs the existing E2 full-scene splitter/read-out on:

  A. E2 GT clean evidence
  B. Stage2 primitive evidence
  C. Stage2 rendered evidence

GT is used only for quality audit and post-generation matching.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
import sys
import traceback
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import torch
import yaml
from scipy.spatial import cKDTree
from shapely.geometry import LineString, Point, Polygon

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.phase2_synthesis.obj_gt import parse_scene_obj  # noqa: E402
import scripts.phase2_synthesis.e2_gt_fullscene_auto_split as e2  # noqa: E402
import scripts.phase2_synthesis.e3_stage2_oracle_split as e3  # noqa: E402
import scripts.phase2_synthesis.p1_4a_preflight_precision as pm  # noqa: E402
import scripts.phase2_synthesis.p1_4a_relation_readout as rr  # noqa: E402
from src.stage2.dataloader import ColmapDataset  # noqa: E402
from src.stage2.model import GaussianModel2D  # noqa: E402
from src.stage2.renderer import render, render_semantic  # noqa: E402


OUT_ROOT = ROOT / "results/stage3_rendered_evidence/S1_rendered_e2style_gate"
SCENE = ROOT / "results/phase2_synthesis/scene.obj"
MUTUAL_CKPT = ROOT / "results/phase2_ablation_citygml/mutual/ckpt/final.pt"
MUTUAL_CONFIG = ROOT / "configs/phase2_mutual.yaml"
E2_REFERENCE = ROOT / "results/stage3_typed_readout/E2_gt_fullscene_auto_split"
PRIMITIVE_NPZ = ROOT / "results/phase2_ablation_citygml/mutual/stage3/primitives.npz"

CLASSES = ["bg", "roof", "wall", "terrain"]
GRAVITY = np.array([0.0, 1.0, 0.0], dtype=np.float64)
TARGET_GROUPS = {
    "OK_CONTROL": [0, 1, 2, 8],
    "HIP": [6],
    "SHARED_WALL": [123, 126],
    "GROUND_EVIDENCE": [50, 104],
    "E2_UNMATCHED_GT": [111, 117],
}
TARGET_BIDS = [0, 1, 2, 8, 6, 123, 126, 50, 104, 111, 117]

ALPHA_MIN = 0.2
SEM_CONF_MIN = 0.2
VOXEL_SIZE_M = 0.05
NORMAL_BIN_STEP = 0.25
MATCH_IOU_THRESHOLD = e2.MATCH_IOU_THRESHOLD
FORMAL_VALIDITY_STATUS = "VAL3DITY_BLOCKED_DEPENDENCY"


def mkdir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def jsonable(obj):
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, np.generic):
        return obj.item()
    if isinstance(obj, (Point, Polygon, LineString)):
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
                    seen.add(key)
                    fields.append(key)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fields})


def fmt(value: object, nd: int = 3) -> str:
    if value is None or value == "":
        return "NA"
    try:
        x = float(value)
    except (TypeError, ValueError):
        return str(value)
    if math.isnan(x) or math.isinf(x):
        return "NA"
    return f"{x:.{nd}f}"


def md_table(headers: List[str], rows: List[List[object]]) -> str:
    out = ["| " + " | ".join(headers) + " |",
           "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in rows:
        out.append("| " + " | ".join(str(x) for x in row) + " |")
    return "\n".join(out)


def safe_float(value: object) -> Optional[float]:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(x) or math.isinf(x) else x


def stratum_for_bid(bid: int) -> str:
    for name, bids in TARGET_GROUPS.items():
        if int(bid) in bids:
            return name
    return "UNSTRATIFIED"


def assert_gravity() -> None:
    if not np.allclose(rr.GRAVITY, GRAVITY):
        raise AssertionError(f"Expected gravity=[0,1,0], got rr.GRAVITY={rr.GRAVITY}")


def class_counts(labels: np.ndarray) -> Dict[str, int]:
    return {
        "roof": int(np.sum(labels == 1)),
        "wall": int(np.sum(labels == 2)),
        "terrain": int(np.sum(labels == 3)),
        "bg": int(np.sum(labels == 0)),
    }


def entropy_rows(probs: np.ndarray) -> np.ndarray:
    if len(probs) == 0:
        return np.asarray([], dtype=np.float64)
    p = np.clip(probs, 1e-12, 1.0)
    return -np.sum(p * np.log(p), axis=1) / math.log(p.shape[1])


def downsample_balanced(labels: np.ndarray, max_points: int, seed: int) -> np.ndarray:
    if len(labels) <= max_points:
        return np.arange(len(labels), dtype=np.int64)
    rng = np.random.default_rng(seed)
    keep = []
    classes = [c for c in [1, 2, 3, 0] if np.any(labels == c)]
    base = max_points // max(len(classes), 1)
    remainder_pool = []
    for cls in classes:
        idx = np.where(labels == cls)[0]
        if len(idx) <= base:
            keep.append(idx)
        else:
            keep.append(rng.choice(idx, size=base, replace=False))
            remainder_pool.append(np.setdiff1d(idx, keep[-1], assume_unique=False))
    keep_arr = np.concatenate(keep) if keep else np.empty(0, dtype=np.int64)
    rem = max_points - len(keep_arr)
    if rem > 0:
        pool = np.concatenate(remainder_pool) if remainder_pool else np.setdiff1d(np.arange(len(labels)), keep_arr)
        if len(pool):
            keep_arr = np.concatenate([keep_arr, rng.choice(pool, size=min(rem, len(pool)), replace=False)])
    return np.sort(keep_arr.astype(np.int64))


def write_binary_ply(path: Path, evidence: Dict, extra: Optional[Dict[str, np.ndarray]] = None,
                     max_points: Optional[int] = None, seed: int = 0) -> None:
    pts = np.asarray(evidence["points"], dtype=np.float32)
    normals = np.asarray(evidence["normals"], dtype=np.float32)
    labels = np.asarray(evidence["classes"], dtype=np.int32)
    weights = np.asarray(evidence["weights"], dtype=np.float32)
    if max_points is not None and len(pts) > max_points:
        idx = downsample_balanced(labels, max_points, seed)
        pts, normals, labels, weights = pts[idx], normals[idx], labels[idx], weights[idx]
        extra = {k: np.asarray(v)[idx] for k, v in (extra or {}).items()}
    else:
        extra = extra or {}
    colors = np.asarray([rr.CLASS_COLOR.get(int(c), rr.CLASS_COLOR[0]) for c in labels], dtype=np.uint8)
    dtype = [
        ("x", "<f4"), ("y", "<f4"), ("z", "<f4"),
        ("nx", "<f4"), ("ny", "<f4"), ("nz", "<f4"),
        ("red", "u1"), ("green", "u1"), ("blue", "u1"),
        ("semantic_class", "<i4"), ("support_weight", "<f4"),
    ]
    extra_names = []
    for name, values in extra.items():
        arr = np.asarray(values)
        if arr.ndim == 1 and len(arr) == len(pts):
            dtype.append((name, "<f4" if np.issubdtype(arr.dtype, np.floating) else "<i4"))
            extra_names.append(name)
    data = np.empty(len(pts), dtype=dtype)
    data["x"], data["y"], data["z"] = pts[:, 0], pts[:, 1], pts[:, 2]
    data["nx"], data["ny"], data["nz"] = normals[:, 0], normals[:, 1], normals[:, 2]
    data["red"], data["green"], data["blue"] = colors[:, 0], colors[:, 1], colors[:, 2]
    data["semantic_class"] = labels
    data["support_weight"] = weights
    for name in extra_names:
        data[name] = np.asarray(extra[name])
    header = [
        "ply",
        "format binary_little_endian 1.0",
        f"element vertex {len(pts)}",
        "property float x", "property float y", "property float z",
        "property float nx", "property float ny", "property float nz",
        "property uchar red", "property uchar green", "property uchar blue",
        "property int semantic_class", "property float support_weight",
    ]
    for name in extra_names:
        kind = "float" if np.issubdtype(np.asarray(extra[name]).dtype, np.floating) else "int"
        header.append(f"property {kind} {name}")
    header.append("end_header")
    mkdir(path.parent)
    with path.open("wb") as f:
        f.write(("\n".join(header) + "\n").encode("ascii"))
        data.tofile(f)


def load_model_and_dataset(config_path: Path, ckpt_path: Path, render_downscale: float,
                           device: str) -> Tuple[GaussianModel2D, ColmapDataset, Dict]:
    cfg = yaml.safe_load(config_path.read_text())
    data_root = Path(cfg["data_root"])
    if not data_root.exists():
        data_root = ROOT / "results/phase2_synthesis/dataset"
    ds = ColmapDataset(
        root=data_root,
        downscale=float(cfg.get("downscale", 1.0)) * render_downscale,
        load_depth=False,
        load_normal=False,
        load_semantic=False,
    )
    model = GaussianModel2D(
        ds.points_xyz,
        ds.points_rgb,
        sh_degree=cfg.get("sh_degree", 3),
        device=device,
    ).to(device)
    sd = torch.load(ckpt_path, map_location=device, weights_only=False)["state_dict"]
    for name, p in list(model.named_parameters()):
        t = sd.get(name)
        if t is None:
            continue
        if p.shape != t.shape:
            obj = model
            parts = name.split(".")
            for pp in parts[:-1]:
                obj = getattr(obj, pp)
            setattr(obj, parts[-1], torch.nn.Parameter(t.clone()))
        else:
            p.data.copy_(t)
    model.eval()
    cfg["resolved_data_root"] = str(data_root)
    cfg["render_downscale_effective"] = float(ds.downscale)
    return model, ds, cfg


def unproject_pixels(u: np.ndarray, v: np.ndarray, depth: np.ndarray,
                     K: np.ndarray, w2c: np.ndarray) -> np.ndarray:
    fx, fy = K[0, 0], K[1, 1]
    cx, cy = K[0, 2], K[1, 2]
    x = (u.astype(np.float64) - cx) / fx * depth
    y = (v.astype(np.float64) - cy) / fy * depth
    pts_cam = np.stack([x, y, depth], axis=1)
    c2w = np.linalg.inv(w2c.astype(np.float64))
    pts_h = np.concatenate([pts_cam, np.ones((len(pts_cam), 1), dtype=np.float64)], axis=1)
    return (pts_h @ c2w.T)[:, :3]


def phase0_reference() -> Dict:
    out = OUT_ROOT / "phase0_e2_reference"
    mkdir(out)
    needed = {
        "scene_evidence_graph.json": "scene_evidence_graph.json",
        "component_to_gt_matching.csv": "component_to_gt_matching.csv",
        "component_metrics.csv": "component_metrics.csv",
        "split_components.png": "split_components.png",
    }
    for src_name, dst_name in needed.items():
        src = E2_REFERENCE / src_name
        if src.exists():
            shutil.copy2(src, out / dst_name)
    summary = read_json(E2_REFERENCE / "summary_metrics.json")
    instance = summary.get("instance_metrics", {})
    row = {
        "input": "E2_GT_clean_evidence",
        "n_gt": instance.get("n_gt"),
        "n_pred": instance.get("n_pred"),
        "matched": instance.get("matched"),
        "instance_recall": instance.get("instance_recall"),
        "instance_precision": instance.get("instance_precision"),
        "overmerge": instance.get("overmerge"),
        "oversplit": instance.get("oversplit"),
    }
    write_csv(out / "e2_reference_reproduction.csv", [row])
    snippet = [
        "# Phase 0 E2 Reference Reproduction",
        "",
        "The S1 gate reuses the existing E2 GT clean-evidence output generated by `scripts/phase2_synthesis/e2_gt_fullscene_auto_split.py`.",
        "This is the same E2 splitter/read-out implementation used below for B/C. GT is not used by the splitter/read-out path.",
        "",
        md_table(
            ["input", "n_gt", "n_pred", "matched", "instance_recall", "instance_precision", "overmerge", "oversplit"],
            [[
                row["input"], row["n_gt"], row["n_pred"], row["matched"],
                fmt(row["instance_recall"]), fmt(row["instance_precision"]),
                row["overmerge"], row["oversplit"],
            ]],
        ),
        "",
    ]
    (out / "REPORT_SNIPPET.md").write_text("\n".join(snippet))
    return row


def phase1_render_export(args: argparse.Namespace) -> Dict:
    out = OUT_ROOT / "phase1_render_export"
    mkdir(out)
    if (out / "raw_rendered_samples.npz").exists() and (out / "render_export_summary.csv").exists():
        rows = read_csv(out / "render_export_summary.csv")
        if rows:
            print("[S1 phase1] reusing existing rendered sample export", flush=True)
            return rows[0]
    device = "cuda" if torch.cuda.is_available() and args.device == "cuda" else "cpu"
    try:
        model, ds, cfg = load_model_and_dataset(MUTUAL_CONFIG, MUTUAL_CKPT, args.render_downscale, device)
        idxs = np.linspace(0, len(ds) - 1, min(args.max_views, len(ds)), dtype=int).tolist()
        all_rows = []
        view_rows = []
        for local_view_id, idx in enumerate(idxs):
            b = ds[idx]
            H, W = int(b["height"]), int(b["width"])
            with torch.no_grad():
                o = render(
                    model,
                    b["w2c"].to(device),
                    b["K"].to(device),
                    W,
                    H,
                    sh_degree=model.max_sh_degree,
                    render_mode="RGB+ED",
                )
                sem_logits = render_semantic(model, b["w2c"].to(device), b["K"].to(device), W, H)
                sem_prob = torch.softmax(sem_logits, dim=-1)
            depth = o["depth"].detach().cpu().numpy().astype(np.float32)
            alpha = o["alpha"].detach().cpu().numpy().astype(np.float32)
            normal = o["normal_render"].detach().cpu().numpy().astype(np.float32)
            prob = sem_prob.detach().cpu().numpy().astype(np.float32)
            ys = np.arange(0, H, args.pixel_stride, dtype=np.int32)
            xs = np.arange(0, W, args.pixel_stride, dtype=np.int32)
            vv, uu = np.meshgrid(ys, xs, indexing="ij")
            d = depth[vv, uu]
            a = alpha[vv, uu]
            p = prob[vv, uu]
            sem_conf = p.max(axis=-1)
            labels = p.argmax(axis=-1).astype(np.int64)
            n = normal[vv, uu]
            n_norm = np.linalg.norm(n, axis=-1)
            valid = (
                np.isfinite(d) &
                (d > 0.0) &
                (a > ALPHA_MIN) &
                (sem_conf > SEM_CONF_MIN) &
                (n_norm > 1e-5)
            )
            if np.any(valid):
                u_flat = uu[valid].reshape(-1)
                v_flat = vv[valid].reshape(-1)
                d_flat = d[valid].reshape(-1).astype(np.float64)
                xyz = unproject_pixels(
                    u_flat,
                    v_flat,
                    d_flat,
                    b["K"].cpu().numpy(),
                    b["w2c"].cpu().numpy(),
                )
                normals = n[valid].reshape(-1, 3).astype(np.float64)
                normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-12)
                all_rows.append({
                    "xyz": xyz.astype(np.float32),
                    "normal": normals.astype(np.float32),
                    "sem_prob": p[valid].reshape(-1, 4).astype(np.float32),
                    "label": labels[valid].reshape(-1).astype(np.int64),
                    "alpha": a[valid].reshape(-1).astype(np.float32),
                    "confidence": (a[valid].reshape(-1) * sem_conf[valid].reshape(-1)).astype(np.float32),
                    "view_id": np.full(int(np.sum(valid)), idx, dtype=np.int32),
                    "pixel_u": u_flat.astype(np.int32),
                    "pixel_v": v_flat.astype(np.int32),
                    "depth": d_flat.astype(np.float32),
                })
            view_rows.append({
                "view_id": idx,
                "local_view_id": local_view_id,
                "image_name": b["name"],
                "height": H,
                "width": W,
                "n_pixels_sampled": int(uu.size),
                "n_valid_samples": int(np.sum(valid)),
                "mean_alpha": float(np.mean(a[valid])) if np.any(valid) else 0.0,
                "mean_sem_conf": float(np.mean(sem_conf[valid])) if np.any(valid) else 0.0,
            })
            print(f"[S1 phase1] view {local_view_id + 1}/{len(idxs)} idx={idx} valid={int(np.sum(valid))}")
        if not all_rows:
            raise RuntimeError("No valid rendered samples were produced")
        raw = {k: np.concatenate([r[k] for r in all_rows], axis=0) for k in all_rows[0]}
        if len(raw["label"]) > args.max_raw_samples:
            keep = downsample_balanced(raw["label"], args.max_raw_samples, args.seed)
            raw = {k: v[keep] for k, v in raw.items()}
        np.savez_compressed(out / "raw_rendered_samples.npz", **raw)
        evidence = {
            "points": raw["xyz"],
            "normals": raw["normal"],
            "classes": raw["label"],
            "weights": raw["confidence"],
        }
        write_binary_ply(
            out / "raw_rendered_samples.ply",
            evidence,
            extra={"alpha": raw["alpha"], "confidence": raw["confidence"], "view_id": raw["view_id"]},
            max_points=args.max_ply_points,
            seed=args.seed,
        )
        counts = class_counts(raw["label"])
        row = {
            "n_views": len(idxs),
            "n_raw_samples": int(sum(r["n_pixels_sampled"] for r in view_rows)),
            "n_valid_samples": int(len(raw["label"])),
            "roof_samples": counts["roof"],
            "wall_samples": counts["wall"],
            "terrain_samples": counts["terrain"],
            "mean_alpha": float(np.mean(raw["alpha"])),
            "mean_sem_conf": float(np.mean(raw["sem_prob"].max(axis=1))),
            "render_downscale": args.render_downscale,
            "pixel_stride": args.pixel_stride,
            "max_raw_samples": args.max_raw_samples,
            "checkpoint": str(MUTUAL_CKPT.relative_to(ROOT)),
            "status": "OK",
        }
        write_csv(out / "render_export_summary.csv", [row])
        write_csv(out / "render_export_views.csv", view_rows)
        write_json(out / "render_export_policy.json", {
            "stage2_retraining_performed": False,
            "checkpoint": "Mutual",
            "ckpt_path": str(MUTUAL_CKPT.relative_to(ROOT)),
            "gt_filtering_used": False,
            "valid_pixel_rule": {
                "finite_depth": True,
                "depth_gt_0": True,
                "alpha_min": ALPHA_MIN,
                "semantic_conf_min": SEM_CONF_MIN,
            },
            "selected_views": idxs,
            "config": {
                "data_root": cfg.get("resolved_data_root"),
                "render_downscale_effective": cfg.get("render_downscale_effective"),
            },
        })
        return row
    except Exception as exc:
        row = {
            "n_views": 0,
            "n_raw_samples": 0,
            "n_valid_samples": 0,
            "roof_samples": 0,
            "wall_samples": 0,
            "terrain_samples": 0,
            "mean_alpha": None,
            "mean_sem_conf": None,
            "status": "RENDER_EXPORT_BLOCKED_DEPENDENCY_OR_RUNTIME",
            "exception_type": type(exc).__name__,
            "exception": str(exc),
        }
        write_csv(out / "render_export_summary.csv", [row])
        write_json(out / "render_export_error.json", row | {"traceback": traceback.format_exc(limit=8)})
        raise


def normal_bins(normals: np.ndarray) -> np.ndarray:
    n = np.asarray(normals, dtype=np.float64)
    n = n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
    idx = np.argmax(np.abs(n), axis=1)
    sign = np.sign(n[np.arange(len(n)), idx])
    sign[sign == 0] = 1.0
    canonical = n * sign[:, None]
    return np.round(canonical / NORMAL_BIN_STEP).astype(np.int32)


def fuse_groups(raw: Dict[str, np.ndarray], group_keys: np.ndarray, mode: str) -> Dict:
    labels = raw["label"].astype(np.int64)
    xyz = raw["xyz"].astype(np.float64)
    normals = raw["normal"].astype(np.float64)
    probs = raw["sem_prob"].astype(np.float64)
    weights = raw["confidence"].astype(np.float64)
    view_ids = raw["view_id"].astype(np.int64)
    uniq, inv = np.unique(group_keys, axis=0, return_inverse=True)
    n_groups = len(uniq)
    support = np.bincount(inv, weights=weights, minlength=n_groups)
    support_safe = np.maximum(support, 1e-12)
    points = np.stack([
        np.bincount(inv, weights=weights * xyz[:, d], minlength=n_groups) / support_safe
        for d in range(3)
    ], axis=1)
    sem_prob = np.stack([
        np.bincount(inv, weights=weights * probs[:, d], minlength=n_groups) / support_safe
        for d in range(4)
    ], axis=1)
    sem_prob = sem_prob / np.maximum(sem_prob.sum(axis=1, keepdims=True), 1e-12)
    out_labels = np.argmax(sem_prob, axis=1).astype(np.int64)

    m00 = np.bincount(inv, weights=weights * normals[:, 0] * normals[:, 0], minlength=n_groups)
    m01 = np.bincount(inv, weights=weights * normals[:, 0] * normals[:, 1], minlength=n_groups)
    m02 = np.bincount(inv, weights=weights * normals[:, 0] * normals[:, 2], minlength=n_groups)
    m11 = np.bincount(inv, weights=weights * normals[:, 1] * normals[:, 1], minlength=n_groups)
    m12 = np.bincount(inv, weights=weights * normals[:, 1] * normals[:, 2], minlength=n_groups)
    m22 = np.bincount(inv, weights=weights * normals[:, 2] * normals[:, 2], minlength=n_groups)
    mean_n = np.stack([
        np.bincount(inv, weights=weights * normals[:, d], minlength=n_groups) / support_safe
        for d in range(3)
    ], axis=1)
    out_normals = np.zeros((n_groups, 3), dtype=np.float64)
    consistency = np.zeros(n_groups, dtype=np.float64)
    for gi in range(n_groups):
        M = np.array([
            [m00[gi], m01[gi], m02[gi]],
            [m01[gi], m11[gi], m12[gi]],
            [m02[gi], m12[gi], m22[gi]],
        ], dtype=np.float64)
        vals, vecs = np.linalg.eigh(M)
        k = int(np.argmax(vals))
        n = vecs[:, k]
        if float(np.dot(n, mean_n[gi])) < 0:
            n = -n
        out_normals[gi] = n / max(np.linalg.norm(n), 1e-12)
        consistency[gi] = float(vals[k] / max(vals.sum(), 1e-12))
    sum_p2 = np.bincount(inv, weights=weights * np.sum(xyz * xyz, axis=1), minlength=n_groups) / support_safe
    pos_cov_trace = np.maximum(sum_p2 - np.sum(points * points, axis=1), 0.0)
    unique_pairs = np.unique(np.stack([inv, view_ids], axis=1), axis=0)
    view_count = np.bincount(unique_pairs[:, 0], minlength=n_groups).astype(np.int32)
    confidence = support / np.maximum(np.bincount(inv, minlength=n_groups), 1)
    return {
        "points": points.astype(np.float32),
        "normals": out_normals.astype(np.float32),
        "classes": out_labels.astype(np.int64),
        "weights": support.astype(np.float32),
        "sem_probs": sem_prob.astype(np.float32),
        "support_weight": support.astype(np.float32),
        "confidence": confidence.astype(np.float32),
        "view_count": view_count,
        "normal_consistency": consistency.astype(np.float32),
        "semantic_entropy": entropy_rows(sem_prob).astype(np.float32),
        "pos_cov_trace": pos_cov_trace.astype(np.float32),
        "fusion_mode": np.asarray(mode),
    }


def phase2_fusion(args: argparse.Namespace) -> Tuple[List[Dict], Dict[str, Dict]]:
    root = OUT_ROOT / "phase2_fusion"
    mkdir(root)
    if (root / "fusion_summary.csv").exists() and all((root / m / "rendered_evidence.npz").exists() for m in ["F0", "F1", "F2"]):
        print("[S1 phase2] reusing existing fusion outputs", flush=True)
        summaries = read_csv(root / "fusion_summary.csv")
        fused = {}
        for short in ["F0", "F1", "F2"]:
            data = np.load(root / short / "rendered_evidence.npz")
            fused[short] = {k: data[k] for k in data.files}
        return summaries, fused
    raw_npz = np.load(OUT_ROOT / "phase1_render_export/raw_rendered_samples.npz")
    raw = {k: raw_npz[k] for k in raw_npz.files}
    labels = raw["label"].astype(np.int64)
    xyz = raw["xyz"].astype(np.float64)
    voxel = np.floor(xyz / VOXEL_SIZE_M).astype(np.int32)

    summaries = []
    fused_by_mode: Dict[str, Dict] = {}
    mode_specs = {
        "F0": "F0_no_fusion_downsample",
        "F1": "F1_class_aware_voxel",
        "F2": "F2_class_normal_aware_voxel",
    }
    for short, mode in mode_specs.items():
        out = root / short
        mkdir(out)
        if short == "F0":
            keep = downsample_balanced(labels, args.max_f0_points, args.seed)
            ev = {
                "points": raw["xyz"][keep].astype(np.float32),
                "normals": raw["normal"][keep].astype(np.float32),
                "classes": labels[keep].astype(np.int64),
                "weights": raw["confidence"][keep].astype(np.float32),
                "sem_probs": raw["sem_prob"][keep].astype(np.float32),
                "support_weight": raw["confidence"][keep].astype(np.float32),
                "confidence": raw["confidence"][keep].astype(np.float32),
                "view_count": np.ones(len(keep), dtype=np.int32),
                "normal_consistency": np.ones(len(keep), dtype=np.float32),
                "semantic_entropy": entropy_rows(raw["sem_prob"][keep]).astype(np.float32),
                "pos_cov_trace": np.zeros(len(keep), dtype=np.float32),
            }
        elif short == "F1":
            keys = np.concatenate([voxel, labels[:, None].astype(np.int32)], axis=1)
            ev = fuse_groups(raw, keys, mode)
        else:
            keys = np.concatenate([voxel, labels[:, None].astype(np.int32), normal_bins(raw["normal"])], axis=1)
            ev = fuse_groups(raw, keys, mode)
        np.savez_compressed(out / "rendered_evidence.npz", **ev)
        write_binary_ply(
            out / "rendered_evidence_points.ply",
            ev,
            extra={
                "view_count": ev["view_count"],
                "confidence": ev["confidence"],
                "normal_consistency": ev["normal_consistency"],
                "semantic_entropy": ev["semantic_entropy"],
            },
            max_points=args.max_ply_points,
            seed=args.seed,
        )
        graph = {
            "gravity": [0, 1, 0],
            "evidence_type": "stage2_rendered_surface_evidence",
            "points_file": "rendered_evidence.npz",
            "ply_file": "rendered_evidence_points.ply",
            "classes": CLASSES,
            "fusion": {
                "mode": mode,
                "voxel_size_m": VOXEL_SIZE_M,
                "alpha_min": ALPHA_MIN,
                "semantic_conf_min": SEM_CONF_MIN,
                "normal_bin_step": NORMAL_BIN_STEP if short == "F2" else None,
                "default_for_split": short == "F2",
            },
        }
        write_json(out / "scene_evidence_graph.json", graph)
        counts = class_counts(ev["classes"])
        row = {
            "fusion": short,
            "mode": mode,
            "n_points": int(len(ev["classes"])),
            "roof": counts["roof"],
            "wall": counts["wall"],
            "terrain": counts["terrain"],
            "mean_view_count": float(np.mean(ev["view_count"])) if len(ev["classes"]) else 0.0,
            "mean_support": float(np.mean(ev["weights"])) if len(ev["classes"]) else 0.0,
            "normal_consistency_mean": float(np.mean(ev["normal_consistency"])) if len(ev["classes"]) else 0.0,
            "semantic_entropy_mean": float(np.mean(ev["semantic_entropy"])) if len(ev["classes"]) else 0.0,
        }
        summaries.append(row)
        fused_by_mode[short] = ev
    write_csv(root / "fusion_summary.csv", summaries)
    return summaries, fused_by_mode


def sample_gt_surfaces(buildings: List[Dict], bids: Optional[Iterable[int]] = None,
                       min_points: int = 32, density: float = 0.35) -> Dict:
    bid_set = set(int(b) for b in bids) if bids is not None else None
    pts, normals, labels, bid_arr = [], [], [], []
    face_ord = 0
    for b in buildings:
        bid = int(b["building_id"])
        if bid_set is not None and bid not in bid_set:
            continue
        for face in b["faces"]:
            samples = rr._sample_face(face, min_points=min_points, density=density, seed=93000 + face_ord)
            n = np.asarray(face["normal"], dtype=np.float64)
            n /= np.linalg.norm(n) + 1e-12
            cls = int(face.get("semantic_class", 0))
            pts.append(samples)
            normals.append(np.tile(n, (len(samples), 1)))
            labels.append(np.full(len(samples), cls, dtype=np.int64))
            bid_arr.append(np.full(len(samples), bid, dtype=np.int64))
            face_ord += 1
    if not pts:
        return {
            "points": np.empty((0, 3), dtype=np.float64),
            "normals": np.empty((0, 3), dtype=np.float64),
            "classes": np.empty(0, dtype=np.int64),
            "bids": np.empty(0, dtype=np.int64),
        }
    return {
        "points": np.concatenate(pts, axis=0),
        "normals": np.concatenate(normals, axis=0),
        "classes": np.concatenate(labels, axis=0),
        "bids": np.concatenate(bid_arr, axis=0),
    }


def confusion_and_quality(ev: Dict, gt_samples: Dict, fusion: str, max_eval: int,
                          seed: int) -> Tuple[Dict, List[Dict]]:
    if len(ev["points"]) == 0 or len(gt_samples["points"]) == 0:
        return {}, []
    labels = ev["classes"].astype(np.int64)
    idx = downsample_balanced(labels, max_eval, seed) if len(labels) > max_eval else np.arange(len(labels))
    pts = ev["points"][idx].astype(np.float64)
    normals = ev["normals"][idx].astype(np.float64)
    pred = labels[idx]
    tree = cKDTree(gt_samples["points"])
    dist, nn = tree.query(pts, workers=-1)
    gt_label = gt_samples["classes"][nn]
    gt_normal = gt_samples["normals"][nn]
    cos = np.abs(np.sum(normals * gt_normal, axis=1))
    rows = []
    for gt_cls in range(4):
        for pr_cls in range(4):
            rows.append({
                "fusion": fusion,
                "gt_class": CLASSES[gt_cls],
                "pred_class": CLASSES[pr_cls],
                "count": int(np.sum((gt_label == gt_cls) & (pred == pr_cls))),
            })
    ious = []
    for cls in [1, 2, 3]:
        tp = np.sum((gt_label == cls) & (pred == cls))
        fp = np.sum((gt_label != cls) & (pred == cls))
        fn = np.sum((gt_label == cls) & (pred != cls))
        den = tp + fp + fn
        ious.append(float(tp / den) if den else float("nan"))
    metrics = {
        "fusion": fusion,
        "normal_cosine_mean": float(np.mean(cos)),
        "semantic_accuracy": float(np.mean(gt_label == pred)),
        "mIoU": float(np.nanmean(ious)),
        "mean_view_count": float(np.mean(ev["view_count"])) if "view_count" in ev else None,
        "mean_support_weight": float(np.mean(ev["weights"])) if len(ev["weights"]) else None,
        "semantic_entropy_mean": float(np.mean(ev.get("semantic_entropy", entropy_rows(ev.get("sem_probs", np.eye(4)[labels]))))),
        "normal_consistency_mean": float(np.mean(ev.get("normal_consistency", np.ones(len(labels))))),
    }
    for cls, name in [(1, "roof"), (2, "wall"), (3, "terrain")]:
        m = gt_label == cls
        metrics[f"{name}_normal_cosine"] = float(np.mean(cos[m])) if np.any(m) else None
        metrics[f"{name}_accuracy"] = float(np.mean(pred[m] == cls)) if np.any(m) else None
    return metrics, rows


def boundary_samples(poly: Polygon, spacing: float = 0.25) -> np.ndarray:
    if poly is None or poly.is_empty:
        return np.empty((0, 2), dtype=np.float64)
    coords = np.asarray(list(poly.exterior.coords), dtype=np.float64)
    pts = []
    for a, b in zip(coords[:-1], coords[1:]):
        length = float(np.linalg.norm(b - a))
        n = max(2, int(math.ceil(length / spacing)))
        for t in np.linspace(0.0, 1.0, n, endpoint=False):
            pts.append(a * (1.0 - t) + b * t)
    return np.asarray(pts, dtype=np.float64)


def coverage_fraction(query: np.ndarray, evidence_points: np.ndarray, thresh: float) -> Optional[float]:
    if len(query) == 0:
        return None
    if len(evidence_points) == 0:
        return 0.0
    dist, _ = cKDTree(evidence_points).query(query, workers=-1)
    return float(np.mean(dist <= thresh))


def bid_quality(ev: Dict, buildings: List[Dict], bid: int) -> Dict:
    b = next(x for x in buildings if int(x["building_id"]) == int(bid))
    fp = pm.footprint_from_gt(b)
    pts = ev["points"].astype(np.float64)
    labels = ev["classes"].astype(np.int64)
    roof_pts = pts[labels == 1]
    wall_pts = pts[labels == 2]
    terrain_pts = pts[labels == 3]
    boundary_xz = boundary_samples(fp)
    boundary_query = np.c_[boundary_xz[:, 0], np.zeros(len(boundary_xz)), boundary_xz[:, 1]] if len(boundary_xz) else np.empty((0, 3))
    gt = sample_gt_surfaces([b], min_points=32, density=0.40)
    roof_gt = gt["points"][gt["classes"] == 1]
    wall_gt = gt["points"][gt["classes"] == 2]
    terrain_gt = gt["points"][gt["classes"] == 3]
    # Boundary coverage is measured in XZ, preserving the E2 split domain.
    wall_xz = wall_pts[:, [0, 2]] if len(wall_pts) else np.empty((0, 2))
    boundary_dist = np.asarray([], dtype=np.float64)
    if len(boundary_xz) and len(wall_xz):
        boundary_dist, _ = cKDTree(wall_xz).query(boundary_xz, workers=-1)
    return {
        "bid": f"B{bid}",
        "bid_int": int(bid),
        "stratum": stratum_for_bid(int(bid)),
        "boundary_recall_0p25": float(np.mean(boundary_dist <= 0.25)) if len(boundary_dist) else 0.0,
        "boundary_recall_0p50": float(np.mean(boundary_dist <= 0.50)) if len(boundary_dist) else 0.0,
        "boundary_recall_1p00": float(np.mean(boundary_dist <= 1.00)) if len(boundary_dist) else 0.0,
        "roof_area_coverage": coverage_fraction(roof_gt, roof_pts, 0.50),
        "wall_boundary_coverage": float(np.mean(boundary_dist <= 0.50)) if len(boundary_dist) else 0.0,
        "terrain_support_coverage": coverage_fraction(terrain_gt, terrain_pts, 0.75),
        "n_roof_evidence": int(len(roof_pts)),
        "n_wall_evidence": int(len(wall_pts)),
        "n_terrain_evidence": int(len(terrain_pts)),
    }


def diagnostic_label(row: Dict) -> str:
    flags = []
    if safe_float(row.get("semantic_accuracy")) is not None and safe_float(row.get("semantic_accuracy")) < 0.65:
        flags.append("SEMANTIC_NOISY")
    if safe_float(row.get("normal_cosine_mean")) is not None and safe_float(row.get("normal_cosine_mean")) < 0.75:
        flags.append("NORMAL_NOISY")
    if safe_float(row.get("roof_area_coverage")) is not None and safe_float(row.get("roof_area_coverage")) < 0.50:
        flags.append("ROOF_SUPPORT_INSUFFICIENT")
    if safe_float(row.get("wall_boundary_coverage")) is not None and safe_float(row.get("wall_boundary_coverage")) < 0.50:
        flags.append("WALL_BOUNDARY_INSUFFICIENT")
    if safe_float(row.get("terrain_support_coverage")) is not None and safe_float(row.get("terrain_support_coverage")) < 0.30:
        flags.append("TERRAIN_SUPPORT_INSUFFICIENT")
    return "GOOD_RENDERED_EVIDENCE" if not flags else "+".join(flags)


def plot_topdown(path: Path, ev: Dict, title: str, normal_color: bool = False,
                 max_points: int = 500_000, seed: int = 0) -> None:
    labels = ev["classes"]
    idx = downsample_balanced(labels, max_points, seed) if len(labels) > max_points else np.arange(len(labels))
    pts = ev["points"][idx]
    fig, ax = plt.subplots(figsize=(9, 8))
    if normal_color:
        colors = (ev["normals"][idx] * 0.5 + 0.5).clip(0, 1)
        ax.scatter(pts[:, 0], pts[:, 2], s=0.4, c=colors, alpha=0.65)
    else:
        for cls, color, name in [(2, "#2D5FD7", "wall"), (1, "#DC2828", "roof"), (3, "#2DA04B", "terrain"), (0, "#777777", "bg")]:
            m = labels[idx] == cls
            if np.any(m):
                ax.scatter(pts[m, 0], pts[m, 2], s=0.4, c=color, alpha=0.45, label=name)
        ax.legend(loc="best", fontsize=8)
    ax.set_aspect("equal", adjustable="box")
    ax.set_title(title)
    ax.grid(True, linewidth=0.2, alpha=0.25)
    fig.tight_layout()
    mkdir(path.parent)
    fig.savefig(path, dpi=180)
    plt.close(fig)


def plot_bid_overlay(path: Path, ev: Dict, building: Dict, bid_row: Dict) -> None:
    fp = pm.footprint_from_gt(building)
    labels = ev["classes"]
    pts = ev["points"]
    fig, ax = plt.subplots(figsize=(6, 6))
    for cls, color, name in [(2, "#2D5FD7", "wall"), (1, "#DC2828", "roof"), (3, "#2DA04B", "terrain")]:
        m = labels == cls
        sub = pts[m][:, [0, 2]]
        if len(sub):
            if fp is not None and not fp.is_empty:
                minx, minz, maxx, maxz = fp.buffer(3.0).bounds
                local = (sub[:, 0] >= minx) & (sub[:, 0] <= maxx) & (sub[:, 1] >= minz) & (sub[:, 1] <= maxz)
                sub = sub[local]
            ax.scatter(sub[:, 0], sub[:, 1], s=2, c=color, alpha=0.35, label=name)
    if fp is not None and not fp.is_empty:
        xy = np.asarray(list(fp.exterior.coords), dtype=np.float64)
        ax.plot(xy[:, 0], xy[:, 1], color="black", linewidth=1.5, label="GT footprint eval")
        boundary = boundary_samples(fp)
        wall_xz = pts[labels == 2][:, [0, 2]]
        if len(boundary) and len(wall_xz):
            dist, _ = cKDTree(wall_xz).query(boundary, workers=-1)
            sc = ax.scatter(boundary[:, 0], boundary[:, 1], c=dist, s=8, cmap="magma_r", vmin=0, vmax=1.0)
            fig.colorbar(sc, ax=ax, fraction=0.035, label="nearest wall evidence m")
    ax.set_aspect("equal", adjustable="box")
    ax.set_title(f"{bid_row['bid']} {bid_row.get('diagnostic', '')}")
    ax.grid(True, linewidth=0.2, alpha=0.25)
    ax.legend(loc="best", fontsize=7)
    fig.tight_layout()
    mkdir(path.parent)
    fig.savefig(path, dpi=160)
    plt.close(fig)


def phase3_quality_audit(fused_by_mode: Dict[str, Dict], args: argparse.Namespace) -> Tuple[List[Dict], List[Dict]]:
    root = OUT_ROOT / "phase3_quality_audit"
    overlays = root / "overlays"
    mkdir(overlays)
    if (root / "evidence_quality_by_fusion.csv").exists() and (root / "evidence_quality_by_bid.csv").exists():
        print("[S1 phase3] reusing existing quality audit outputs", flush=True)
        return read_csv(root / "evidence_quality_by_fusion.csv"), read_csv(root / "evidence_quality_by_bid.csv")
    buildings = parse_scene_obj(SCENE, frame="obj")["buildings"]
    gt_samples = sample_gt_surfaces(buildings, min_points=24, density=0.25)
    fusion_rows = []
    confusion_rows = []
    for short, ev in fused_by_mode.items():
        metrics, conf = confusion_and_quality(ev, gt_samples, short, args.audit_max_points, args.seed)
        counts = class_counts(ev["classes"])
        metrics.update({
            "n_points": int(len(ev["classes"])),
            "roof": counts["roof"],
            "wall": counts["wall"],
            "terrain": counts["terrain"],
        })
        fusion_rows.append(metrics)
        confusion_rows.extend(conf)
    f2 = fused_by_mode["F2"]
    bid_rows = []
    by_bid = {int(b["building_id"]): b for b in buildings}
    for bid in TARGET_BIDS:
        row = bid_quality(f2, buildings, bid)
        # Local semantic/normal audit for target bid.
        local_gt = sample_gt_surfaces([by_bid[bid]], min_points=24, density=0.35)
        local_metrics, _conf = confusion_and_quality(f2, local_gt, "F2", args.audit_max_points, args.seed + bid)
        for k in ["normal_cosine_mean", "semantic_accuracy", "mIoU", "roof_normal_cosine", "wall_normal_cosine", "terrain_normal_cosine"]:
            row[k] = local_metrics.get(k)
        row["diagnostic"] = diagnostic_label(row)
        bid_rows.append(row)
        plot_bid_overlay(overlays / f"B{bid:03d}_evidence_vs_gt_overlay.png", f2, by_bid[bid], row)
    write_csv(root / "evidence_quality_by_fusion.csv", fusion_rows)
    write_csv(root / "evidence_quality_by_bid.csv", bid_rows)
    write_csv(root / "confusion_matrix.csv", confusion_rows)
    plot_topdown(root / "rendered_evidence_topdown_semantic.png", f2, "F2 rendered evidence semantic topdown", seed=args.seed)
    plot_topdown(root / "rendered_evidence_normal_color.png", f2, "F2 rendered evidence normal color", normal_color=True, seed=args.seed)
    return fusion_rows, bid_rows


def primitive_evidence(max_points: Optional[int], seed: int) -> Dict:
    prims = e3.load_primitives("Mutual")
    idx = np.where(e3.active_mask(prims))[0]
    ev = e3.evidence_from_indices(prims, idx)
    return downsample_evidence(ev, max_points, seed)


def downsample_evidence(evidence: Dict, max_points: Optional[int], seed: int) -> Dict:
    if max_points is None or len(evidence["classes"]) <= max_points:
        return evidence
    keep = downsample_balanced(evidence["classes"], max_points, seed)
    n = len(evidence["classes"])
    return {
        k: v[keep] if isinstance(v, np.ndarray) and v.ndim > 0 and v.shape[0] == n else v
        for k, v in evidence.items()
    }


def split_components_payload(components: List[e2.SplitComponent]) -> List[Dict]:
    rows = []
    for comp in components:
        rows.append({
            "pred_id": comp.pred_id,
            "split_label": int(comp.label),
            "seed_polygon_xz": e2.polygon_to_json(comp.seed_polygon),
            "seed_area": float(comp.seed_area),
            "bbox_min": comp.bbox_min.tolist(),
            "bbox_max": comp.bbox_max.tolist(),
            "roof_sample_count": int(comp.roof_sample_count),
            "wall_sample_count": int(comp.wall_sample_count),
            "ground_sample_count": int(comp.ground_sample_count),
        })
    return rows


def capped_component(comp: e2.SplitComponent, evidence: Dict, max_points: Optional[int],
                     seed: int) -> e2.SplitComponent:
    if max_points is None:
        return comp
    groups = [comp.roof_indices, comp.wall_indices, comp.ground_indices]
    n_total = sum(len(g) for g in groups)
    if n_total <= max_points:
        return comp
    labels = np.concatenate([
        np.full(len(comp.roof_indices), 1, dtype=np.int64),
        np.full(len(comp.wall_indices), 2, dtype=np.int64),
        np.full(len(comp.ground_indices), 3, dtype=np.int64),
    ])
    all_indices = np.concatenate(groups)
    keep_local = downsample_balanced(labels, max_points, seed + int(comp.label))
    keep_indices = all_indices[keep_local]
    keep_classes = evidence["classes"][keep_indices]
    roof = keep_indices[keep_classes == 1]
    wall = keep_indices[keep_classes == 2]
    ground = keep_indices[keep_classes == 3]
    return e2.SplitComponent(
        pred_id=comp.pred_id,
        label=comp.label,
        seed_polygon=comp.seed_polygon,
        roof_indices=roof,
        wall_indices=wall,
        ground_indices=ground,
        bbox_min=comp.bbox_min,
        bbox_max=comp.bbox_max,
        roof_sample_count=int(len(roof)),
        wall_sample_count=int(len(wall)),
        ground_sample_count=int(len(ground)),
        seed_area=comp.seed_area,
    )


def patch_e2_out_root(out_dir: Path) -> None:
    e2.OUT_ROOT = out_dir
    e2.REPORT_PATH = out_dir / "REPORT.md"
    e2.SUMMARY_JSON = out_dir / "summary_metrics.json"
    e2.INSTANCE_CSV = out_dir / "instance_metrics.csv"
    e2.COMPONENT_CSV = out_dir / "component_metrics.csv"
    e2.MATCHING_CSV = out_dir / "component_to_gt_matching.csv"
    e2.RISK_CSV = out_dir / "risk_building_tracking.csv"


def run_e2_style_input(name: str, evidence: Dict, out_dir: Path, buildings: List[Dict],
                       max_component_points: Optional[int], seed: int) -> Dict:
    if out_dir.exists():
        shutil.rmtree(out_dir)
    mkdir(out_dir)
    mkdir(out_dir / "components")
    patch_e2_out_root(out_dir)
    np.savez_compressed(out_dir / "scene_evidence.npz", **evidence)
    write_binary_ply(out_dir / "scene_evidence.ply", evidence, max_points=600_000)
    rr.write_evidence_stats(out_dir / "scene_evidence_stats.csv", evidence)
    components, split_diag = e2.automatic_split(evidence)
    write_json(out_dir / "split_diagnostics.json", split_diag)
    write_json(out_dir / "split_components.json", {"input": name, "components": split_components_payload(components)})
    e2.write_scene_graph(components, split_diag)
    e2.plot_split_components(evidence, components)
    readout_rows = []
    readout_components = []
    for comp in components:
        rc = capped_component(comp, evidence, max_component_points, seed)
        readout_components.append(rc)
        print(f"[S1 phase4 {name}] read-out {rc.pred_id} roof={rc.roof_sample_count} wall={rc.wall_sample_count} ground={rc.ground_sample_count}", flush=True)
        readout_rows.append(e2.run_component_readout(evidence, rc))
    matching_rows, instance = e2.match_components_to_gt(readout_rows, components, buildings)
    component_rows = e2.attach_gt_metrics(readout_rows, readout_components, buildings, matching_rows)
    e2.attach_gt_type_eval_only(component_rows, buildings)
    risk_rows = e2.risk_tracking(buildings, component_rows, instance)
    write_csv(out_dir / "instance_metrics.csv", [instance])
    write_csv(out_dir / "component_to_gt_matching.csv", matching_rows)
    write_csv(out_dir / "component_metrics.csv", component_rows)
    write_csv(out_dir / "risk_building_tracking.csv", risk_rows)
    e2.plot_matching(buildings, component_rows, components)
    preview = build_semantic_face_graph(out_dir, evidence, component_rows, preview_only=True)
    write_json(out_dir / "semantic_faces_preview.json", preview["semantic_faces"])
    write_json(out_dir / "face_graph_preview.json", preview["face_graph"])
    write_json(out_dir / "summary_metrics.json", {
        "input": name,
        "split_diagnostics": split_diag,
        "instance_metrics": instance,
        "component_rows": component_rows,
        "matching_rows": matching_rows,
        "risk_rows": risk_rows,
        "face_graph_preview_metrics": preview["metrics"],
        "input_policy": {
            "gt_used_for_generation": False,
            "gt_used_for_post_generation_matching_only": True,
            "same_e2_splitter_readout": True,
        },
    })
    return {
        "input": name,
        "instance": instance,
        "components": component_rows,
        "matching": matching_rows,
        "face_graph_metrics": preview["metrics"],
    }


def copy_phase4_a_from_reference(out_dir: Path) -> Dict:
    mkdir(out_dir)
    for name in [
        "scene_evidence_graph.json", "component_to_gt_matching.csv", "component_metrics.csv",
        "split_components.png", "split_diagnostics.json", "scene_evidence.npz",
        "scene_evidence.ply", "scene_evidence_stats.csv", "split_merge_matching.png",
    ]:
        src = E2_REFERENCE / name
        if src.exists():
            shutil.copy2(src, out_dir / name)
    summary = read_json(E2_REFERENCE / "summary_metrics.json")
    rows = summary.get("component_rows", read_csv(E2_REFERENCE / "component_metrics.csv"))
    write_json(out_dir / "split_components.json", {
        "input": "A_gt_clean",
        "source": str(E2_REFERENCE.relative_to(ROOT)),
        "note": "Copied from existing E2 reference generated by the same splitter/read-out.",
    })
    preview = build_semantic_face_graph(E2_REFERENCE, None, rows, preview_only=True)
    write_json(out_dir / "semantic_faces_preview.json", preview["semantic_faces"])
    write_json(out_dir / "face_graph_preview.json", preview["face_graph"])
    return {
        "input": "A_gt_clean",
        "instance": summary.get("instance_metrics", {}),
        "components": rows,
        "matching": summary.get("matching_rows", read_csv(E2_REFERENCE / "component_to_gt_matching.csv")),
        "face_graph_metrics": preview["metrics"],
    }


def load_phase4_result(input_name: str, out_dir: Path) -> Optional[Dict]:
    summary_path = out_dir / "summary_metrics.json"
    if not summary_path.exists():
        return None
    summary = read_json(summary_path)
    print(f"[S1 phase4] reusing existing {input_name} split/read-out", flush=True)
    return {
        "input": input_name,
        "instance": summary.get("instance_metrics", {}),
        "components": summary.get("component_rows", read_csv(out_dir / "component_metrics.csv")),
        "matching": summary.get("matching_rows", read_csv(out_dir / "component_to_gt_matching.csv")),
        "face_graph_metrics": summary.get("face_graph_preview_metrics", {}),
    }


def cityjson_faces(path: Path, component_id: str) -> List[Dict]:
    if not path.exists():
        return []
    cj = json.loads(path.read_text())
    scale = np.asarray(cj.get("transform", {}).get("scale", [1, 1, 1]), dtype=np.float64)
    translate = np.asarray(cj.get("transform", {}).get("translate", [0, 0, 0]), dtype=np.float64)
    verts = np.asarray(cj.get("vertices", []), dtype=np.float64) * scale + translate
    out = []
    for obj_id, obj in cj.get("CityObjects", {}).items():
        for geom in obj.get("geometry", []):
            surfaces = geom.get("semantics", {}).get("surfaces", [])
            values = geom.get("semantics", {}).get("values", [[]])
            sem_values = values[0] if values else []
            shells = geom.get("boundaries", [])
            boundaries = shells[0] if shells else []
            for i, boundary in enumerate(boundaries):
                if not boundary:
                    continue
                ring = boundary[0]
                if len(ring) < 3:
                    continue
                sem_idx = sem_values[i] if i < len(sem_values) else None
                sem_type = surfaces[sem_idx].get("type", "UnknownSurface") if sem_idx is not None and sem_idx < len(surfaces) else "UnknownSurface"
                fv = verts[np.asarray(ring, dtype=np.int64)]
                out.append({
                    "face_id": f"{component_id}_face_{len(out):04d}",
                    "component_id": component_id,
                    "cityobject_id": obj_id,
                    "semantic_type": sem_type,
                    "vertices": fv,
                })
    return out


def newell_normal(vertices: np.ndarray) -> np.ndarray:
    n = np.zeros(3, dtype=np.float64)
    for i in range(len(vertices)):
        a = vertices[i]
        b = vertices[(i + 1) % len(vertices)]
        n[0] += (a[1] - b[1]) * (a[2] + b[2])
        n[1] += (a[2] - b[2]) * (a[0] + b[0])
        n[2] += (a[0] - b[0]) * (a[1] + b[1])
    return n / max(np.linalg.norm(n), 1e-12)


def planarity_residual(vertices: np.ndarray) -> float:
    if len(vertices) < 3:
        return 0.0
    n = newell_normal(vertices)
    d = float(np.dot(n, vertices[0]))
    return float(np.max(np.abs(vertices @ n - d)))


def qkey(v: np.ndarray, scale: float = 1e-4) -> Tuple[int, int, int]:
    return tuple(int(round(float(v[i]) / scale)) for i in range(3))


def build_semantic_face_graph(base_dir: Path, evidence: Optional[Dict], component_rows: List[Dict],
                              preview_only: bool = False) -> Dict:
    faces = []
    optional_cityjson = []
    for row in component_rows:
        if str(row.get("pipeline_success", "")).lower() not in {"true", "1"} and row.get("pipeline_success") is not True:
            continue
        pred_id = row.get("pred_id")
        cj_path = Path(row.get("cityjson_path", ""))
        if not cj_path.is_absolute():
            cj_path = base_dir / "components" / str(pred_id) / "relation_readout.city.json"
        c_faces = cityjson_faces(cj_path, str(pred_id))
        if c_faces:
            optional_cityjson.append(str(cj_path))
        for f in c_faces:
            verts = np.asarray(f["vertices"], dtype=np.float64)
            faces.append({
                "face_id": f["face_id"],
                "component_id": f["component_id"],
                "semantic_type": f["semantic_type"],
                "vertices": verts.tolist() if not preview_only else None,
                "n_vertices": int(len(verts)),
                "normal": newell_normal(verts).tolist(),
                "bbox_min": verts.min(axis=0).tolist(),
                "bbox_max": verts.max(axis=0).tolist(),
                "planarity_residual_max": planarity_residual(verts),
            })
    edge_to_faces: Dict[Tuple[Tuple[int, int, int], Tuple[int, int, int]], List[str]] = defaultdict(list)
    for f in faces:
        verts = np.asarray(f["vertices"], dtype=np.float64) if f["vertices"] is not None else None
        if verts is None:
            # Re-read exact vertices for preview graph construction.
            comp_dir = base_dir / "components" / f["component_id"] / "relation_readout.city.json"
            exact = [x for x in cityjson_faces(comp_dir, f["component_id"]) if x["face_id"] == f["face_id"]]
            if not exact:
                continue
            verts = exact[0]["vertices"]
        keys = [qkey(v) for v in verts]
        for i in range(len(keys)):
            a, b = keys[i], keys[(i + 1) % len(keys)]
            if a == b:
                continue
            edge = (a, b) if a < b else (b, a)
            edge_to_faces[edge].append(f["face_id"])
    graph_edges = []
    open_edges = 0
    nonmanifold_edges = 0
    for edge, fs in edge_to_faces.items():
        if len(fs) == 1:
            open_edges += 1
        elif len(fs) > 2:
            nonmanifold_edges += 1
        if len(fs) >= 2:
            for i in range(len(fs)):
                for j in range(i + 1, len(fs)):
                    graph_edges.append({"type": "face_adjacency", "faces": [fs[i], fs[j]], "edge_key": edge})
    counts = Counter(f["semantic_type"] for f in faces)
    metrics = {
        "n_faces": int(len(faces)),
        "n_roof_faces": int(counts.get("RoofSurface", 0)),
        "n_wall_faces": int(counts.get("WallSurface", 0)),
        "n_ground_faces": int(counts.get("GroundSurface", 0)),
        "face_planarity_max": max([float(f["planarity_residual_max"]) for f in faces], default=0.0),
        "open_edges": int(open_edges),
        "nonmanifold_edges": int(nonmanifold_edges),
        "edge_incidence_ok": bool(open_edges == 0 and nonmanifold_edges == 0 and len(faces) > 0),
        "roof_support_coverage": None,
        "wall_support_coverage": None,
        "ground_support_coverage": None,
        "optional_cityjson_export_status": "EXPORTED_COMPONENT_CITYJSON" if optional_cityjson else "NO_SUCCESSFUL_COMPONENT_CITYJSON",
    }
    return {
        "semantic_faces": {
            "gravity": [0, 1, 0],
            "primary_output": True,
            "preview_only": preview_only,
            "faces": faces,
        },
        "face_graph": {
            "gravity": [0, 1, 0],
            "primary_output": True,
            "nodes": [{"face_id": f["face_id"], "semantic_type": f["semantic_type"], "component_id": f["component_id"]} for f in faces],
            "edges": graph_edges,
            "diagnostics": {
                "open_edges": open_edges,
                "nonmanifold_edges": nonmanifold_edges,
            },
        },
        "metrics": metrics,
        "optional_cityjson": optional_cityjson,
    }


def phase4_split_comparison(fused_f2: Dict, args: argparse.Namespace) -> Tuple[List[Dict], List[Dict], Dict[str, Dict]]:
    root = OUT_ROOT / "phase4_e2style_split"
    mkdir(root)
    buildings = parse_scene_obj(SCENE, frame="obj")["buildings"]
    results = {}
    results["A_gt_clean"] = copy_phase4_a_from_reference(root / "A_gt_clean")
    cached_b = load_phase4_result("B_primitive", root / "B_primitive")
    if cached_b is not None:
        results["B_primitive"] = cached_b
    else:
        prim_ev = primitive_evidence(args.max_primitive_points, args.seed)
        write_json(root / "B_primitive/scene_evidence_graph.json", {
            "gravity": [0, 1, 0],
            "evidence_type": "stage2_primitive_evidence",
            "points_file": "scene_evidence.npz",
            "classes": CLASSES,
            "input_policy": {"gt_used_for_generation": False, "checkpoint": "Mutual"},
        })
        results["B_primitive"] = run_e2_style_input(
            "B_primitive", prim_ev, root / "B_primitive", buildings,
            args.max_component_readout_points, args.seed,
        )
    rendered_split_ev = downsample_evidence(fused_f2, args.max_rendered_split_points, args.seed)
    cached_c = load_phase4_result("C_rendered", root / "C_rendered")
    if cached_c is not None:
        results["C_rendered"] = cached_c
    else:
        results["C_rendered"] = run_e2_style_input(
            "C_rendered", rendered_split_ev, root / "C_rendered", buildings,
            args.max_component_readout_points, args.seed,
        )

    split_rows = []
    target_rows = []
    for input_name, res in results.items():
        inst = res["instance"]
        comps = res["components"]
        fvals = [safe_float(r.get("F_score")) for r in comps if r.get("matched_gt_bid") not in (None, "")]
        fvals = [v for v in fvals if v is not None]
        split_rows.append({
            "input": input_name,
            "n_pred": inst.get("n_pred"),
            "matched": inst.get("matched"),
            "instance_recall": inst.get("instance_recall"),
            "instance_precision": inst.get("instance_precision"),
            "overmerge": inst.get("overmerge"),
            "oversplit": inst.get("oversplit"),
            "matched_F_mean": float(np.mean(fvals)) if fvals else None,
            "matched_F_median": float(np.median(fvals)) if fvals else None,
        })
        by_bid = {}
        for r in comps:
            bid = r.get("matched_gt_bid")
            if bid not in (None, ""):
                by_bid[int(bid)] = r
        for bid in TARGET_BIDS:
            r = by_bid.get(bid, {})
            f = safe_float(r.get("F_score"))
            target_rows.append({
                "bid": f"B{bid}",
                "bid_int": bid,
                "stratum": stratum_for_bid(bid),
                "input": input_name,
                "matched_component": r.get("pred_id"),
                "match_IoU": r.get("match_IoU"),
                "F": f,
                "footprint_IoU": r.get("footprint_IoU"),
                "h_err": r.get("h_err"),
                "vol_ratio": r.get("vol_ratio"),
                "status": r.get("geometry_failure_reason", "UNMATCHED_GT"),
            })
    write_csv(root / "split_comparison_summary.csv", split_rows)
    write_csv(root / "target_bid_metrics.csv", target_rows)
    return split_rows, target_rows, results


def phase5_face_graph(c_result: Dict) -> Dict:
    root = OUT_ROOT / "phase5_face_graph"
    mkdir(root)
    mkdir(root / "optional_cityjson")
    base = OUT_ROOT / "phase4_e2style_split/C_rendered"
    preview = build_semantic_face_graph(base, None, c_result["components"], preview_only=False)
    write_json(root / "semantic_faces.json", preview["semantic_faces"])
    write_json(root / "face_graph.json", preview["face_graph"])
    for path_str in preview["optional_cityjson"]:
        src = Path(path_str)
        if src.exists():
            shutil.copy2(src, root / "optional_cityjson" / f"{src.parent.name}.city.json")
    shell_diag = {
        "formal_validity_status": FORMAL_VALIDITY_STATUS,
        "val3dity_valid": None,
        "geometry_metrics_are_primary": True,
        **preview["face_graph"]["diagnostics"],
    }
    write_json(root / "shell_diagnostics.json", shell_diag)
    write_csv(root / "metrics_face_graph.csv", [preview["metrics"]])
    return preview["metrics"]


def ok_control_passes(target_rows: List[Dict], input_name: str, threshold: float = 0.6) -> int:
    rows = [r for r in target_rows if r["input"] == input_name and int(r["bid_int"]) in TARGET_GROUPS["OK_CONTROL"]]
    return sum(1 for r in rows if safe_float(r.get("F")) is not None and safe_float(r.get("F")) > threshold)


def make_decision(split_rows: List[Dict], target_rows: List[Dict], face_metrics: Dict) -> Dict:
    by_input = {r["input"]: r for r in split_rows}
    a = by_input.get("A_gt_clean", {})
    b = by_input.get("B_primitive", {})
    c = by_input.get("C_rendered", {})
    c_recall = safe_float(c.get("instance_recall")) or 0.0
    b_recall = safe_float(b.get("instance_recall")) or 0.0
    a_recall = safe_float(a.get("instance_recall")) or 0.0
    c_f = safe_float(c.get("matched_F_mean")) or 0.0
    b_f = safe_float(b.get("matched_F_mean")) or 0.0
    improves = (c_recall > b_recall) and (c_f > b_f)
    ok_pass = ok_control_passes(target_rows, "C_rendered", 0.6)
    face_success = int(face_metrics.get("n_faces", 0) > 0)
    if c_recall >= 0.80 and ok_pass == 4 and face_success:
        rec = "S1_STRONG_GO_RENDERED_INTERFACE"
    elif improves and ok_pass >= 3 and a_recall > 0 and c_recall >= 0.70 * a_recall:
        rec = "S1_GO_RENDERED_INTERFACE"
    elif improves:
        rec = "S1_PARTIAL_GO_RENDERED_FIX_FUSION_OR_SPLITTER"
    else:
        rec = "S1_NG_RENDERED_EVIDENCE_RUN_G2_FEASIBILITY"
    return {
        "recommendation": rec,
        "C_improves_over_B_recall_and_F": bool(improves),
        "C_instance_recall": c_recall,
        "B_instance_recall": b_recall,
        "A_instance_recall": a_recall,
        "C_matched_F_mean": c_f,
        "B_matched_F_mean": b_f,
        "OK_CONTROL_F_gt_0p6": ok_pass,
        "C_recall_ge_70pct_A": bool(a_recall > 0 and c_recall >= 0.70 * a_recall),
        "face_graph_preview_has_faces": bool(face_success),
        "next_action": (
            "proceed to S2 Rendered Evidence Semantic Face Graph Read-out"
            if rec in {"S1_STRONG_GO_RENDERED_INTERFACE", "S1_GO_RENDERED_INTERFACE"}
            else "refine fusion/splitter, no Stage2 retraining yet"
            if rec == "S1_PARTIAL_GO_RENDERED_FIX_FUSION_OR_SPLITTER"
            else "run S3-pre G2 surface-group feasibility before any Stage2 retraining"
        ),
    }


def write_report(phase0_row: Dict, render_row: Dict, fusion_rows: List[Dict],
                 quality_rows: List[Dict], bid_quality_rows: List[Dict],
                 split_rows: List[Dict], target_rows: List[Dict],
                 face_metrics: Dict, decision: Dict, args: argparse.Namespace) -> None:
    report = [
        "# S1 Rendered Evidence E2-style Gate",
        "",
        "## 1. Purpose and research intent",
        "",
        "This experiment tests whether the current Mutual Stage2 checkpoint can be read as rendered full-scene surface evidence for Stage3. The target is not improved primitives; the target interface is semantic surface evidence that can feed a semantic face graph.",
        "",
        "## 2. Why E2-style evidence is the correct interface test",
        "",
        "E2 takes only position, normal, semantic class, and support weight. Replacing E2 clean evidence with Stage2 rendered evidence isolates the Stage2->Stage3 interface while keeping the splitter/read-out fixed.",
        "",
        "## 3. Fusion method and why F2 is default",
        "",
        f"F2 groups samples by voxel ({VOXEL_SIZE_M}m), semantic label, and normal bin. Class and normal bins prevent roof/wall/terrain and boundary-normal mixing; normals are aggregated with a second-moment principal direction.",
        "",
        "## 4. E2 reference reproduction",
        "",
        md_table(
            ["input", "n_gt", "n_pred", "matched", "instance_recall", "instance_precision", "overmerge", "oversplit"],
            [[phase0_row["input"], phase0_row["n_gt"], phase0_row["n_pred"], phase0_row["matched"], fmt(phase0_row["instance_recall"]), fmt(phase0_row["instance_precision"]), phase0_row["overmerge"], phase0_row["oversplit"]]],
        ),
        "",
        "## 5. Rendered evidence export summary",
        "",
        md_table(
            ["n_views", "n_raw_samples", "n_valid_samples", "roof_samples", "wall_samples", "terrain_samples", "mean_alpha", "mean_sem_conf"],
            [[render_row.get("n_views"), render_row.get("n_raw_samples"), render_row.get("n_valid_samples"), render_row.get("roof_samples"), render_row.get("wall_samples"), render_row.get("terrain_samples"), fmt(render_row.get("mean_alpha")), fmt(render_row.get("mean_sem_conf"))]],
        ),
        "",
        "## 6. Fusion comparison",
        "",
        md_table(
            ["fusion", "n_points", "roof", "wall", "terrain", "mean_view_count", "mean_support", "normal_consistency_mean", "semantic_entropy_mean"],
            [[r["fusion"], r["n_points"], r["roof"], r["wall"], r["terrain"], fmt(r["mean_view_count"]), fmt(r["mean_support"]), fmt(r["normal_consistency_mean"]), fmt(r["semantic_entropy_mean"])] for r in fusion_rows],
        ),
        "",
        "## 7. Evidence quality audit",
        "",
        md_table(
            ["fusion", "n_points", "normal_cosine_mean", "semantic_accuracy", "mIoU", "roof", "wall", "terrain"],
            [[r["fusion"], r["n_points"], fmt(r.get("normal_cosine_mean")), fmt(r.get("semantic_accuracy")), fmt(r.get("mIoU")), r.get("roof"), r.get("wall"), r.get("terrain")] for r in quality_rows],
        ),
        "",
        md_table(
            ["bid", "stratum", "boundary@0.5", "roof_cov", "wall_boundary", "terrain_cov", "normal_cos", "sem_acc", "diagnostic"],
            [[r["bid"], r["stratum"], fmt(r.get("boundary_recall_0p50")), fmt(r.get("roof_area_coverage")), fmt(r.get("wall_boundary_coverage")), fmt(r.get("terrain_support_coverage")), fmt(r.get("normal_cosine_mean")), fmt(r.get("semantic_accuracy")), r.get("diagnostic")] for r in bid_quality_rows],
        ),
        "",
        "Figures: `phase3_quality_audit/rendered_evidence_topdown_semantic.png`, `phase3_quality_audit/rendered_evidence_normal_color.png`, and `phase3_quality_audit/overlays/`.",
        "",
        "## 8. E2-style split comparison A/B/C",
        "",
        f"Implementation note: B/C split-read-out uses GT-free global caps for runtime control: primitive scene evidence max `{args.max_primitive_points}`, rendered F2 scene evidence max `{args.max_rendered_split_points}`, and component read-out evidence max `{args.max_component_readout_points}`. These are fixed globally and not tuned by building.",
        "",
        md_table(
            ["input", "n_pred", "matched", "instance_recall", "instance_precision", "overmerge", "oversplit", "matched_F_mean", "matched_F_median"],
            [[r["input"], r["n_pred"], r["matched"], fmt(r["instance_recall"]), fmt(r["instance_precision"]), r["overmerge"], r["oversplit"], fmt(r["matched_F_mean"]), fmt(r["matched_F_median"])] for r in split_rows],
        ),
        "",
        md_table(
            ["bid", "input", "matched_component", "match_IoU", "F", "footprint_IoU", "h_err", "vol_ratio", "status"],
            [[r["bid"], r["input"], r.get("matched_component") or "NA", fmt(r.get("match_IoU")), fmt(r.get("F")), fmt(r.get("footprint_IoU")), fmt(r.get("h_err")), fmt(r.get("vol_ratio")), r.get("status")] for r in target_rows],
        ),
        "",
        "## 9. Semantic face graph preview",
        "",
        md_table(
            ["n_faces", "n_roof_faces", "n_wall_faces", "n_ground_faces", "face_planarity_max", "open_edges", "nonmanifold_edges", "edge_incidence_ok", "optional_cityjson_export_status"],
            [[face_metrics.get("n_faces"), face_metrics.get("n_roof_faces"), face_metrics.get("n_wall_faces"), face_metrics.get("n_ground_faces"), fmt(face_metrics.get("face_planarity_max")), face_metrics.get("open_edges"), face_metrics.get("nonmanifold_edges"), face_metrics.get("edge_incidence_ok"), face_metrics.get("optional_cityjson_export_status")]],
        ),
        "",
        "## 10. GO/NG decision",
        "",
        md_table(
            ["criterion", "value"],
            [[k, fmt(v) if isinstance(v, float) else v] for k, v in decision.items()],
        ),
        "",
        "## 11. Recommendation for next experiment",
        "",
        f"Final recommendation: `{decision['recommendation']}`.",
        f"Next action: {decision['next_action']}.",
        "",
        "## Self-verification",
        "",
        "- PASS: gravity=[0,1,0] asserted.",
        "- PASS: Stage2 retraining was not performed; only Mutual checkpoint inference/export was used.",
        "- PASS: GT was not used in rendered evidence generation or split/read-out.",
        "- PASS: GT was used only for quality audit and post-generation matching.",
        "- PASS: F2 class-normal-aware voxel fusion is the default C_rendered input.",
        "- PASS: F0/F1 are diagnostic only.",
        "- PASS: A/B/C use the same E2 splitter/read-out implementation.",
        "- PASS: semantic_faces.json and face_graph.json are primary Phase 5 outputs.",
        "- PASS: val3dity dependency status is separate from structural metrics.",
    ]
    (OUT_ROOT / "REPORT.md").write_text("\n".join(report) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-views", type=int, default=56)
    ap.add_argument("--render-downscale", type=float, default=0.25)
    ap.add_argument("--pixel-stride", type=int, default=2)
    ap.add_argument("--max-raw-samples", type=int, default=3_000_000)
    ap.add_argument("--max-f0-points", type=int, default=450_000)
    ap.add_argument("--max-primitive-points", type=int, default=120_000)
    ap.add_argument("--max-rendered-split-points", type=int, default=300_000)
    ap.add_argument("--max-component-readout-points", type=int, default=2_500)
    ap.add_argument("--max-ply-points", type=int, default=750_000)
    ap.add_argument("--audit-max-points", type=int, default=450_000)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--device", choices=["cuda", "cpu"], default="cuda")
    args = ap.parse_args()

    assert_gravity()
    mkdir(OUT_ROOT)
    write_json(OUT_ROOT / "experiment_policy.json", {
        "gravity": [0, 1, 0],
        "checkpoint": "Mutual",
        "stage2_retraining_performed": False,
        "roofer_called": False,
        "polyfit_backend_called": False,
        "gt_used_for_generation": False,
        "gt_used_for_quality_audit_and_post_generation_matching_only": True,
        "cityjson_export_optional": True,
        "primary_outputs": ["semantic_faces.json", "face_graph.json", "evidence metrics"],
        "thresholds_global_fixed": True,
        "runtime_caps": {
            "max_primitive_points_for_B_split": args.max_primitive_points,
            "max_rendered_points_for_C_split": args.max_rendered_split_points,
            "max_component_readout_points": args.max_component_readout_points,
        },
        "val3dity_status": FORMAL_VALIDITY_STATUS,
    })
    phase0_row = phase0_reference()
    render_row = phase1_render_export(args)
    fusion_rows, fused = phase2_fusion(args)
    quality_rows, bid_quality_rows = phase3_quality_audit(fused, args)
    split_rows, target_rows, phase4_results = phase4_split_comparison(fused["F2"], args)
    face_metrics = phase5_face_graph(phase4_results["C_rendered"])
    decision = make_decision(split_rows, target_rows, face_metrics)
    write_json(OUT_ROOT / "decision.json", decision)
    write_report(phase0_row, render_row, fusion_rows, quality_rows, bid_quality_rows, split_rows, target_rows, face_metrics, decision, args)
    print(f"[S1] wrote {OUT_ROOT.relative_to(ROOT)} recommendation={decision['recommendation']}")


if __name__ == "__main__":
    main()
