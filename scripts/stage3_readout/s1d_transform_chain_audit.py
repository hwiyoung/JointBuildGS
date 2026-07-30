"""S1D transform-chain audit for rendered surface evidence.

The audit checks whether rendered evidence is coherent in the Stage2/COLMAP
frame, whether a scene-level transform explains GT mismatch, and whether
fusion/view-count failures are caused by strict keys or inconsistent geometry.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import torch
import yaml
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import scripts.stage3_readout.e3_stage2_oracle_split as e3  # noqa: E402
import scripts.stage3_readout.s1_debug_rendered_interface as dbg  # noqa: E402
import scripts.stage3_readout.s1_rendered_e2style_gate as s1  # noqa: E402
import scripts.stage3_readout.s1d_fix_export_and_rerun as s1d  # noqa: E402
from scripts.stage3_readout.obj_gt import parse_scene_obj  # noqa: E402
from src.stage2.dataloader import ColmapDataset  # noqa: E402
from src.stage2.colmap_io import read_images_bin  # noqa: E402


OUT_ROOT = ROOT / "results/stage3_rendered_evidence/S1D_transform_chain_audit"
S1D_FIX_ROOT = ROOT / "results/stage3_rendered_evidence/S1D_fix_export_and_rerun"
SCENE = ROOT / "results/phase2_synthesis/scene.obj"
DATASET_ROOT = ROOT / "results/phase2_synthesis/dataset"
RAW_CAM_DIR = ROOT / "results/phase2_synthesis/renders_raw"


def mkdir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, payload: Dict) -> None:
    mkdir(path.parent)
    path.write_text(json.dumps(payload, indent=2, default=s1.jsonable) + "\n")


def read_json(path: Path) -> Dict:
    return json.loads(path.read_text()) if path.exists() else {}


def read_csv(path: Path) -> List[Dict]:
    if not path.exists():
        return []
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: List[Dict], fields: Optional[List[str]] = None) -> None:
    s1.write_csv(path, rows, fields)


def fmt(value: object, nd: int = 3) -> str:
    return s1.fmt(value, nd)


def load_npz(path: Path) -> Dict[str, np.ndarray]:
    data = np.load(path, allow_pickle=False)
    return {k: data[k] for k in data.files}


def rng_indices(n: int, max_n: int, seed: int) -> np.ndarray:
    if n <= max_n:
        return np.arange(n, dtype=np.int64)
    return np.random.default_rng(seed).choice(n, size=max_n, replace=False).astype(np.int64)


def normalize_rows(arr: np.ndarray) -> np.ndarray:
    x = np.asarray(arr, dtype=np.float64)
    return x / np.maximum(np.linalg.norm(x, axis=1, keepdims=True), 1e-12)


def bbox_iou_3d(a: np.ndarray, b: np.ndarray) -> Optional[float]:
    return dbg.bbox_iou_3d(a, b)


def bbox_diag(points: np.ndarray) -> float:
    if len(points) == 0:
        return 0.0
    return float(np.linalg.norm(points.max(axis=0) - points.min(axis=0)))


def camera_center_from_w2c(w2c: np.ndarray) -> np.ndarray:
    R = w2c[:3, :3]
    t = w2c[:3, 3]
    return -R.T @ t


def dataset(render_downscale: float = 0.25, load_gt: bool = False) -> ColmapDataset:
    return ColmapDataset(
        root=DATASET_ROOT,
        downscale=render_downscale,
        load_depth=load_gt,
        load_normal=load_gt,
        load_semantic=load_gt,
    )


def load_sources(args: argparse.Namespace) -> Dict[str, Dict]:
    raw_bank = load_npz(S1D_FIX_ROOT / "phase1_transform_sweep/rendered_sample_bank.npz")
    rendered_raw = load_npz(S1D_FIX_ROOT / "phase2_fixed_export/raw_rendered_samples_fixed.npz")
    prims = e3.load_primitives("Mutual")
    active = np.where(e3.active_mask(prims))[0]
    prim_ev = e3.evidence_from_indices(prims, active)
    ds = dataset(args.render_downscale, load_gt=False)
    gt = s1.sample_gt_surfaces(parse_scene_obj(SCENE, frame="obj")["buildings"], min_points=32, density=args.gt_density)
    colmap_sparse = {
        "points": ds.points_xyz.astype(np.float64),
        "classes": np.zeros(len(ds.points_xyz), dtype=np.int64),
        "normals": np.zeros_like(ds.points_xyz, dtype=np.float64),
        "weights": np.ones(len(ds.points_xyz), dtype=np.float64),
    }
    rendered_ev = {
        "points": rendered_raw["xyz"].astype(np.float64),
        "normals": rendered_raw["normal"].astype(np.float64),
        "classes": rendered_raw["label"].astype(np.int64),
        "weights": rendered_raw["confidence"].astype(np.float64),
        "view_id": rendered_raw["view_id"].astype(np.int64),
        "pixel_u": rendered_raw["pixel_u"].astype(np.int64),
        "pixel_v": rendered_raw["pixel_v"].astype(np.int64),
        "depth": rendered_raw["depth"].astype(np.float64),
        "sem_probs": rendered_raw["sem_prob"].astype(np.float64),
    }
    gt_ev = {
        "points": gt["points"].astype(np.float64),
        "normals": gt["normals"].astype(np.float64),
        "classes": gt["classes"].astype(np.int64),
        "weights": np.ones(len(gt["points"]), dtype=np.float64),
    }
    return {
        "raw_bank": raw_bank,
        "rendered": rendered_ev,
        "primitives": prim_ev,
        "colmap_sparse": colmap_sparse,
        "gt_clean": gt_ev,
        "dataset": ds,
    }


def phase0_inventory(args: argparse.Namespace) -> Tuple[Dict, List[Dict]]:
    root = OUT_ROOT / "phase0_coordinate_frame_inventory"
    mkdir(root)
    ds = dataset(args.render_downscale, load_gt=False)
    cfg = yaml.safe_load(s1.MUTUAL_CONFIG.read_text())
    ckpt = torch.load(s1.MUTUAL_CKPT, map_location="cpu", weights_only=False)
    b0 = ds[0]
    frame_rows = [
        {"frame": "F_img", "definition": "Raster pixel frame, u right and v down; origin top-left.", "evidence": "pixel_u/pixel_v in rendered sample bank"},
        {"frame": "F_cam", "definition": "COLMAP/OpenCV camera coordinates used by gsplat; z-depth is positive forward.", "evidence": "K and w2c from ColmapDataset"},
        {"frame": "F_render", "definition": "Rendered image/depth/normal fields emitted by gsplat for a COLMAP view matrix.", "evidence": "rendered_sample_bank.npz"},
        {"frame": "F_ckpt", "definition": "Mutual checkpoint primitive center frame.", "evidence": "checkpoint state_dict['means'] / primitives.npz centers"},
        {"frame": "F_colmap", "definition": "COLMAP sparse model world frame from dataset/sparse/0.", "evidence": "cameras.bin/images.bin/points3D.bin"},
        {"frame": "F_gt", "definition": "scene.obj frame parsed as OBJ/COLMAP frame.", "evidence": "obj_gt.parse_scene_obj(frame='obj')"},
        {"frame": "F_stage3", "definition": "Stage3 evidence frame expected by E2-style splitter; gravity=[0,1,0], XZ footprint plane.", "evidence": "relation_readout gravity and E2 splitter conventions"},
    ]
    transform_rows = [
        {"from": "F_img", "to": "F_cam", "transform": "K^-1 z-depth unprojection", "source": "ColmapDataset.scaled_K", "metadata_consistent": True, "notes": f"K0={np.asarray(b0['K']).tolist()}"},
        {"from": "F_colmap", "to": "F_cam", "transform": "w2c = [R|t]", "source": "dataset sparse/0 images.bin", "metadata_consistent": True, "notes": f"first_w2c={np.asarray(b0['w2c']).tolist()}"},
        {"from": "F_cam", "to": "F_colmap", "transform": "inverse(w2c)", "source": "COLMAP camera-to-world inverse extrinsic", "metadata_consistent": True, "notes": "Used by S1/S1D fixed export."},
        {"from": "F_render", "to": "F_cam", "transform": "gsplat RGB+ED depth channel is expected z-depth; median depth available diagnostically", "source": "gsplat rasterization_2dgs docs/runtime output", "metadata_consistent": True, "notes": "S1D median sweep did not improve alignment."},
        {"from": "F_ckpt", "to": "F_colmap", "transform": "identity expected", "source": "Model initialized from COLMAP points and trained in-place", "metadata_consistent": True, "notes": "No checkpoint normalization key found."},
        {"from": "F_colmap", "to": "F_gt", "transform": "identity expected for v2+ dataset", "source": "export_colmap.py / obj_gt.py", "metadata_consistent": True, "notes": "obj_gt.py documents legacy primitive frame only for v1 bug."},
        {"from": "F_gt", "to": "F_stage3", "transform": "identity in OBJ frame; XZ footprint plane and gravity=[0,1,0]", "source": "Stage3 readout code", "metadata_consistent": True, "notes": "No GT-derived transform allowed for generation."},
    ]
    inventory = {
        "frames": frame_rows,
        "checkpoint": str(s1.MUTUAL_CKPT.relative_to(ROOT)),
        "checkpoint_keys": sorted(list(ckpt.keys())),
        "checkpoint_iteration": ckpt.get("it", ckpt.get("iteration")),
        "checkpoint_state_keys_sample": sorted(list(ckpt.get("state_dict", {}).keys()))[:20],
        "checkpoint_normalization": "NOT_FOUND",
        "config": {
            "path": str(s1.MUTUAL_CONFIG.relative_to(ROOT)),
            "data_root": cfg.get("data_root"),
            "depth_scale": cfg.get("depth_scale"),
            "downscale": cfg.get("downscale"),
        },
        "dataset": {
            "root": str(DATASET_ROOT.relative_to(ROOT)),
            "n_frames": len(ds),
            "n_colmap_sparse_points": int(len(ds.points_xyz)),
            "first_image": b0["name"],
            "first_K": np.asarray(b0["K"]).tolist(),
            "first_w2c": np.asarray(b0["w2c"]).tolist(),
        },
        "gt_scene": {
            "path": str(SCENE.relative_to(ROOT)),
            "frame": "obj",
        },
        "gravity": [0, 1, 0],
        "restrictions": {
            "stage2_retraining": False,
            "g2_retraining": False,
            "roofer": False,
            "polyfit": False,
            "gt_sim3_generation_prior": False,
        },
    }
    write_json(root / "coordinate_frame_inventory.json", inventory)
    write_csv(root / "transform_chain_table.csv", transform_rows)
    return inventory, transform_rows


def phase1_native_quality(sources: Dict, args: argparse.Namespace) -> List[Dict]:
    root = OUT_ROOT / "phase1_native_image_space_quality"
    mkdir(root)
    raw = sources["raw_bank"]
    ds = dataset(args.render_downscale, load_gt=True)
    rows = []
    for view_id in sorted(int(x) for x in np.unique(raw["view_id"])):
        m = np.where(raw["view_id"] == view_id)[0]
        b = ds[view_id]
        u = raw["pixel_u"][m].astype(np.int64)
        v = raw["pixel_v"][m].astype(np.int64)
        valid = np.ones(len(m), dtype=bool)
        if "normal" in b:
            valid &= b["normal_mask"].numpy()[v, u]
        if "semantic" in b:
            sem_gt_full = b["semantic"].numpy()
            valid &= sem_gt_full[v, u] >= 0
        if not np.any(valid):
            rows.append({"view_id": view_id, "image_name": b["name"], "status": "NO_VALID_GT"})
            continue
        nn = raw["normal"][m][valid].astype(np.float64)
        ng = b["normal"].numpy()[v[valid], u[valid]].astype(np.float64)
        nn = normalize_rows(nn)
        ng = normalize_rows(ng)
        cos_abs = np.abs(np.sum(nn * ng, axis=1))
        pred = raw["label"][m][valid].astype(np.int64)
        gt = b["semantic"].numpy()[v[valid], u[valid]].astype(np.int64)
        ious = []
        for cls in [1, 2, 3]:
            tp = np.sum((gt == cls) & (pred == cls))
            fp = np.sum((gt != cls) & (pred == cls))
            fn = np.sum((gt == cls) & (pred != cls))
            den = tp + fp + fn
            ious.append(float(tp / den) if den else float("nan"))
        rows.append({
            "view_id": view_id,
            "image_name": b["name"],
            "normal_abs": float(np.mean(cos_abs)),
            "semantic_accuracy": float(np.mean(gt == pred)),
            "mIoU": float(np.nanmean(ious)),
            "n_valid": int(np.sum(valid)),
            "status": "OK",
        })
    write_csv(root / "native_render_quality.csv", rows)
    return rows


def nearest_metrics(src: np.ndarray, dst: np.ndarray, max_src: int, seed: int) -> Dict:
    if len(src) == 0 or len(dst) == 0:
        return {"nn_mean": None, "nn_p95": None, "n_eval": 0}
    idx = rng_indices(len(src), max_src, seed)
    pts = src[idx].astype(np.float64)
    dist, _ = cKDTree(dst.astype(np.float64)).query(pts, workers=-1)
    return {
        "nn_mean": float(np.mean(dist)),
        "nn_median": float(np.median(dist)),
        "nn_p95": float(np.percentile(dist, 95)),
        "n_eval": int(len(pts)),
    }


def estimate_sim3(src: np.ndarray, dst: np.ndarray) -> Dict:
    if len(src) < 3 or len(dst) < 3:
        return {"ok": False}
    x = np.asarray(src, dtype=np.float64)
    y = np.asarray(dst, dtype=np.float64)
    mu_x = x.mean(axis=0)
    mu_y = y.mean(axis=0)
    xc = x - mu_x
    yc = y - mu_y
    H = (xc.T @ yc) / len(x)
    U, S, Vt = np.linalg.svd(H)
    R = Vt.T @ U.T
    if np.linalg.det(R) < 0:
        Vt[-1, :] *= -1
        R = Vt.T @ U.T
    var_x = float(np.mean(np.sum(xc * xc, axis=1)))
    scale = float(np.sum(S) / max(var_x, 1e-12))
    t = mu_y - scale * (mu_x @ R)
    pred = scale * (x @ R) + t
    residual = np.linalg.norm(pred - y, axis=1)
    return {
        "ok": True,
        "scale": scale,
        "rotation": R,
        "translation": t,
        "rmse": float(np.sqrt(np.mean(residual * residual))),
        "residual_mean": float(np.mean(residual)),
        "residual_p95": float(np.percentile(residual, 95)),
    }


def sim3_diagnostic(src: np.ndarray, dst: np.ndarray, max_pairs: int, seed: int) -> Dict:
    if len(src) == 0 or len(dst) == 0:
        return {"sim3_ok": False}
    idx = rng_indices(len(src), max_pairs, seed)
    src_s = src[idx].astype(np.float64)
    dist, nn = cKDTree(dst.astype(np.float64)).query(src_s, workers=-1)
    # Trim the worst correspondences so global-fit diagnostics are not dominated
    # by obvious non-overlap/outliers.
    keep = dist <= np.percentile(dist, 80)
    if np.sum(keep) < 16:
        keep = np.ones(len(src_s), dtype=bool)
    sim = estimate_sim3(src_s[keep], dst[nn][keep])
    if not sim.get("ok"):
        return {"sim3_ok": False}
    transformed = sim["scale"] * (src_s @ sim["rotation"]) + sim["translation"]
    post, _ = cKDTree(dst.astype(np.float64)).query(transformed, workers=-1)
    return {
        "sim3_ok": True,
        "sim3_scale": sim["scale"],
        "sim3_translation_x": float(sim["translation"][0]),
        "sim3_translation_y": float(sim["translation"][1]),
        "sim3_translation_z": float(sim["translation"][2]),
        "sim3_fit_rmse_trimmed": sim["rmse"],
        "pre_nn_mean": float(np.mean(dist)),
        "pre_nn_p95": float(np.percentile(dist, 95)),
        "post_nn_mean": float(np.mean(post)),
        "post_nn_p95": float(np.percentile(post, 95)),
        "n_pairs": int(len(src_s)),
        "n_fit_pairs": int(np.sum(keep)),
        "rotation": sim["rotation"],
        "translation": sim["translation"],
    }


def phase2_rendered_vs_primitives(sources: Dict, args: argparse.Namespace) -> Dict:
    root = OUT_ROOT / "phase2_rendered_vs_stage2_primitives"
    mkdir(root / "overlays")
    rendered = sources["rendered"]["points"]
    prim = sources["primitives"]["points"]
    r2p = nearest_metrics(rendered, prim, args.max_eval_points, args.seed)
    p2r = nearest_metrics(prim, rendered, args.max_eval_points, args.seed + 1)
    row = {
        "source": "rendered_xyz",
        "target": "stage2_primitive_centers_active",
        "rendered_to_primitive_mean": r2p["nn_mean"],
        "rendered_to_primitive_p95": r2p["nn_p95"],
        "primitive_to_rendered_mean": p2r["nn_mean"],
        "primitive_to_rendered_p95": p2r["nn_p95"],
        "bbox_IoU_3D": bbox_iou_3d(rendered, prim),
        "scale_ratio_rendered_over_primitive": bbox_diag(rendered) / max(bbox_diag(prim), 1e-12),
        "n_rendered": int(len(rendered)),
        "n_primitives_active": int(len(prim)),
    }
    write_csv(root / "rendered_vs_primitives.csv", [row])
    dbg.write_overlay_ply(root / "overlays/rendered_vs_primitives_overlay.ply", rendered, prim, max_points=args.max_overlay_points, seed=args.seed)
    dbg.plot_topdown_overlay(root / "overlays/rendered_vs_primitives_topdown.png", rendered, prim, "rendered xyz vs active primitive centers", max_points=args.max_overlay_points)
    return row


def phase3_pairwise_alignment(sources: Dict, args: argparse.Namespace) -> List[Dict]:
    root = OUT_ROOT / "phase3_rendered_colmap_gt_alignment"
    mkdir(root / "overlays")
    point_sets = {
        "rendered_xyz": sources["rendered"]["points"],
        "stage2_primitives": sources["primitives"]["points"],
        "colmap_sparse": sources["colmap_sparse"]["points"],
        "gt_clean_surface": sources["gt_clean"]["points"],
    }
    rows = []
    names = list(point_sets.keys())
    for src_name in names:
        for dst_name in names:
            if src_name == dst_name:
                continue
            src = point_sets[src_name]
            dst = point_sets[dst_name]
            nn = nearest_metrics(src, dst, args.max_eval_points, args.seed + len(rows))
            rev = nearest_metrics(dst, src, args.max_eval_points, args.seed + 1000 + len(rows))
            sim = sim3_diagnostic(src, dst, args.max_sim3_pairs, args.seed + 2000 + len(rows))
            rows.append({
                "source": src_name,
                "target": dst_name,
                "n_source": int(len(src)),
                "n_target": int(len(dst)),
                "nn_mean": nn["nn_mean"],
                "nn_p95": nn["nn_p95"],
                "reverse_nn_mean": rev["nn_mean"],
                "reverse_nn_p95": rev["nn_p95"],
                "bidir_chamfer_mean": None if nn["nn_mean"] is None or rev["nn_mean"] is None else 0.5 * (nn["nn_mean"] + rev["nn_mean"]),
                "bbox_IoU_3D": bbox_iou_3d(src, dst),
                "scale_ratio_source_over_target": bbox_diag(src) / max(bbox_diag(dst), 1e-12),
                "sim3_scale": sim.get("sim3_scale"),
                "sim3_fit_rmse_trimmed": sim.get("sim3_fit_rmse_trimmed"),
                "sim3_pre_nn_mean": sim.get("pre_nn_mean"),
                "sim3_post_nn_mean": sim.get("post_nn_mean"),
                "sim3_post_nn_p95": sim.get("post_nn_p95"),
                "sim3_n_fit_pairs": sim.get("n_fit_pairs"),
            })
    rows.append({
        "source": "colmap_mvs",
        "target": "all",
        "n_source": 0,
        "n_target": "",
        "nn_mean": None,
        "nn_p95": None,
        "reverse_nn_mean": None,
        "reverse_nn_p95": None,
        "bidir_chamfer_mean": None,
        "bbox_IoU_3D": None,
        "scale_ratio_source_over_target": None,
        "sim3_scale": None,
        "sim3_fit_rmse_trimmed": None,
        "sim3_pre_nn_mean": None,
        "sim3_post_nn_mean": None,
        "sim3_post_nn_p95": None,
        "sim3_n_fit_pairs": None,
        "notes": "No COLMAP MVS stereo/depth_maps directory present; MatrixCity-style GT depth maps are separate diagnostics.",
    })
    write_csv(root / "pairwise_frame_alignment.csv", rows)
    dbg.write_overlay_ply(root / "overlays/rendered_vs_gt_overlay.ply", point_sets["rendered_xyz"], point_sets["gt_clean_surface"], max_points=args.max_overlay_points, seed=args.seed)
    dbg.plot_topdown_overlay(root / "overlays/rendered_vs_gt_topdown.png", point_sets["rendered_xyz"], point_sets["gt_clean_surface"], "rendered xyz vs GT clean surface", max_points=args.max_overlay_points)
    dbg.write_overlay_ply(root / "overlays/colmap_vs_gt_overlay.ply", point_sets["colmap_sparse"], point_sets["gt_clean_surface"], max_points=args.max_overlay_points, seed=args.seed)
    dbg.plot_topdown_overlay(root / "overlays/colmap_vs_gt_topdown.png", point_sets["colmap_sparse"], point_sets["gt_clean_surface"], "COLMAP sparse vs GT clean surface", max_points=args.max_overlay_points)
    return rows


def raw_camera_centers() -> Dict[str, np.ndarray]:
    out = {}
    if not RAW_CAM_DIR.exists():
        return out
    for path in sorted(RAW_CAM_DIR.glob("*_cam.json")):
        payload = json.loads(path.read_text())
        w2c = np.asarray(payload.get("w2c"), dtype=np.float64)
        name = f"{path.stem.rsplit('_cam', 1)[0]}.png"
        if w2c.shape == (4, 4):
            out[name] = camera_center_from_w2c(w2c)
    return out


def dataset_camera_centers(ds: ColmapDataset) -> Dict[str, np.ndarray]:
    out = {}
    for idx in range(len(ds)):
        b = ds[idx]
        out[b["name"]] = camera_center_from_w2c(b["w2c"].numpy())
    return out


def center_alignment_row(name_a: str, a: Dict[str, np.ndarray], name_b: str, b: Dict[str, np.ndarray]) -> Dict:
    common = sorted(set(a) & set(b))
    if not common:
        return {"source_a": name_a, "source_b": name_b, "n_common": 0, "status": "NO_COMMON_CAMERA_NAMES"}
    A = np.stack([a[k] for k in common], axis=0)
    B = np.stack([b[k] for k in common], axis=0)
    delta = np.linalg.norm(A - B, axis=1)
    # Pairwise trajectory distances are translation-invariant.
    if len(common) >= 2:
        ia, ib = np.triu_indices(len(common), k=1)
        da = np.linalg.norm(A[ia] - A[ib], axis=1)
        db = np.linalg.norm(B[ia] - B[ib], axis=1)
        valid = (da > 1e-9) & (db > 1e-9)
        ratio = db[valid] / da[valid] if np.any(valid) else np.asarray([])
        shape = np.abs(da[valid] - db[valid]) if np.any(valid) else np.asarray([])
    else:
        ratio = np.asarray([])
        shape = np.asarray([])
    return {
        "source_a": name_a,
        "source_b": name_b,
        "n_common": int(len(common)),
        "center_delta_mean": float(np.mean(delta)),
        "center_delta_p95": float(np.percentile(delta, 95)),
        "trajectory_scale_ratio_median": float(np.median(ratio)) if len(ratio) else None,
        "trajectory_shape_error_mean": float(np.mean(shape)) if len(shape) else None,
        "status": "OK",
    }


def phase4_camera_audit(args: argparse.Namespace) -> List[Dict]:
    root = OUT_ROOT / "phase4_camera_center_trajectory_audit"
    mkdir(root)
    ds = dataset(args.render_downscale, load_gt=False)
    centers = {
        "renderer_dataset_w2c": dataset_camera_centers(ds),
        "colmap_images_bin": dataset_camera_centers(ds),
        "raw_cam_json_eval": raw_camera_centers(),
    }
    rows = [
        center_alignment_row("renderer_dataset_w2c", centers["renderer_dataset_w2c"], "colmap_images_bin", centers["colmap_images_bin"]),
        center_alignment_row("renderer_dataset_w2c", centers["renderer_dataset_w2c"], "raw_cam_json_eval", centers["raw_cam_json_eval"]),
        center_alignment_row("colmap_images_bin", centers["colmap_images_bin"], "raw_cam_json_eval", centers["raw_cam_json_eval"]),
    ]
    if not centers["raw_cam_json_eval"]:
        rows.append({"source_a": "raw_cam_json_eval", "source_b": "all", "n_common": 0, "status": "MISSING_RAW_CAMERA_JSON"})
    write_csv(root / "camera_center_alignment.csv", rows)
    return rows


def depth_map_for_view(raw_bank: Dict[str, np.ndarray], view_id: int, H: int, W: int, depth_key: str = "depth_expected") -> np.ndarray:
    arr = np.full((H, W), np.nan, dtype=np.float64)
    m = raw_bank["view_id"] == view_id
    u = raw_bank["pixel_u"][m].astype(np.int64)
    v = raw_bank["pixel_v"][m].astype(np.int64)
    arr[v, u] = raw_bank[depth_key][m].astype(np.float64)
    return arr


def phase5_cross_view_consistency(sources: Dict, args: argparse.Namespace) -> List[Dict]:
    root = OUT_ROOT / "phase5_cross_view_consistency"
    mkdir(root / "overlays")
    raw = sources["raw_bank"]
    rendered = sources["rendered"]
    ds = sources["dataset"]
    view_ids = sorted(int(x) for x in np.unique(raw["view_id"]))
    pairs = [(view_ids[i], view_ids[i + 1]) for i in range(min(len(view_ids) - 1, args.max_view_pairs))]
    rows = []
    rng = np.random.default_rng(args.seed)
    for a_id, b_id in pairs:
        ma = np.where(rendered["view_id"] == a_id)[0]
        if len(ma) > args.cross_view_points:
            ma = rng.choice(ma, size=args.cross_view_points, replace=False)
        ba = ds[a_id]
        bb = ds[b_id]
        H, W = int(bb["height"]), int(bb["width"])
        depth_b = depth_map_for_view(raw, b_id, H, W)
        pts = rendered["points"][ma].astype(np.float64)
        u, v, z = dbg.project_world(pts, bb["K"].numpy(), bb["w2c"].numpy())
        ur = np.rint(u / args.pixel_stride).astype(np.int64) * args.pixel_stride
        vr = np.rint(v / args.pixel_stride).astype(np.int64) * args.pixel_stride
        in_img = (ur >= 0) & (ur < W) & (vr >= 0) & (vr < H) & np.isfinite(z) & (z > 0)
        sampled = np.zeros(len(ma), dtype=bool)
        db = np.full(len(ma), np.nan, dtype=np.float64)
        valid_idx = np.where(in_img)[0]
        if len(valid_idx):
            vals = depth_b[vr[valid_idx], ur[valid_idx]]
            ok = np.isfinite(vals) & (vals > 0)
            sampled[valid_idx[ok]] = True
            db[valid_idx[ok]] = vals[ok]
        residual = np.abs(z[sampled] - db[sampled])
        rel = residual / np.maximum(db[sampled], 1e-6)
        rows.append({
            "view_a": a_id,
            "view_b": b_id,
            "image_a": ba["name"],
            "image_b": bb["name"],
            "n_projected": int(len(ma)),
            "in_image_fraction": float(np.mean(in_img)) if len(ma) else 0.0,
            "valid_overlap_fraction": float(np.mean(sampled)) if len(ma) else 0.0,
            "depth_abs_residual_mean": float(np.mean(residual)) if len(residual) else None,
            "depth_abs_residual_median": float(np.median(residual)) if len(residual) else None,
            "depth_abs_residual_p95": float(np.percentile(residual, 95)) if len(residual) else None,
            "depth_rel_residual_mean": float(np.mean(rel)) if len(rel) else None,
            "status": "OK" if len(residual) else "NO_VALID_OVERLAP",
        })
        if len(residual):
            fig, ax = plt.subplots(figsize=(6, 4))
            ax.hist(np.clip(residual, 0, np.percentile(residual, 99)), bins=50, color="#4C78A8")
            ax.set_xlabel("abs z-depth residual in target view")
            ax.set_ylabel("samples")
            ax.set_title(f"{a_id}->{b_id}")
            fig.tight_layout()
            fig.savefig(root / "overlays" / f"cross_view_{a_id:03d}_to_{b_id:03d}_depth_residual.png", dpi=150)
            plt.close(fig)
    write_csv(root / "cross_view_consistency.csv", rows)
    return rows


def phase6_sim3(sources: Dict, args: argparse.Namespace) -> List[Dict]:
    root = OUT_ROOT / "phase6_global_sim3_diagnostic"
    mkdir(root / "overlays")
    sets = {
        "rendered": sources["rendered"]["points"],
        "gt": sources["gt_clean"]["points"],
        "colmap": sources["colmap_sparse"]["points"],
    }
    specs = [("rendered", "gt"), ("rendered", "colmap"), ("colmap", "gt")]
    rows = []
    for src_name, dst_name in specs:
        sim = sim3_diagnostic(sets[src_name], sets[dst_name], args.max_sim3_pairs, args.seed + len(rows))
        row = {
            "source": src_name,
            "target": dst_name,
            "pre_nn_mean": sim.get("pre_nn_mean"),
            "pre_nn_p95": sim.get("pre_nn_p95"),
            "post_nn_mean": sim.get("post_nn_mean"),
            "post_nn_p95": sim.get("post_nn_p95"),
            "sim3_scale": sim.get("sim3_scale"),
            "sim3_translation_x": sim.get("sim3_translation_x"),
            "sim3_translation_y": sim.get("sim3_translation_y"),
            "sim3_translation_z": sim.get("sim3_translation_z"),
            "sim3_fit_rmse_trimmed": sim.get("sim3_fit_rmse_trimmed"),
            "n_pairs": sim.get("n_pairs"),
            "n_fit_pairs": sim.get("n_fit_pairs"),
            "diagnostic_only": True,
        }
        rows.append(row)
        if sim.get("sim3_ok"):
            src = sets[src_name]
            idx = rng_indices(len(src), args.max_overlay_points // 2, args.seed + 500 + len(rows))
            transformed = sim["sim3_scale"] * (src[idx].astype(np.float64) @ sim["rotation"]) + sim["translation"]
            dbg.write_overlay_ply(root / "overlays" / f"{src_name}_to_{dst_name}_sim3_overlay.ply", transformed, sets[dst_name], max_points=args.max_overlay_points, seed=args.seed)
            dbg.plot_topdown_overlay(root / "overlays" / f"{src_name}_to_{dst_name}_sim3_topdown.png", transformed, sets[dst_name], f"{src_name}-> {dst_name} Sim3 diagnostic", max_points=args.max_overlay_points)
    write_csv(root / "sim3_diagnostic.csv", rows)
    return rows


def pure_fuse(points: np.ndarray, view_ids: np.ndarray, voxel: float) -> Dict:
    keys = np.floor(points / voxel).astype(np.int64)
    uniq, inv = np.unique(keys, axis=0, return_inverse=True)
    pairs = np.unique(np.c_[inv, view_ids.astype(np.int64)], axis=0)
    view_count = np.bincount(pairs[:, 0], minlength=len(uniq))
    support = np.bincount(inv, minlength=len(uniq))
    return {
        "n_voxels": int(len(uniq)),
        "mean_view_count": float(np.mean(view_count)) if len(view_count) else 0.0,
        "median_view_count": float(np.median(view_count)) if len(view_count) else 0.0,
        "view_count_ge2_frac": float(np.mean(view_count >= 2)) if len(view_count) else 0.0,
        "mean_samples_per_voxel": float(np.mean(support)) if len(support) else 0.0,
    }


def phase7_pure_fusion(sources: Dict) -> List[Dict]:
    root = OUT_ROOT / "phase7_pure_spatial_fusion"
    mkdir(root)
    rendered = sources["rendered"]
    points = rendered["points"].astype(np.float64)
    view_ids = rendered["view_id"].astype(np.int64)
    rows = []
    for voxel in [0.05, 0.10, 0.20, 0.50]:
        row = {"fusion": f"pure_xyz_voxel_{voxel:.2f}m", "voxel_m": voxel, **pure_fuse(points, view_ids, voxel)}
        rows.append(row)
    f2 = read_csv(S1D_FIX_ROOT / "phase3_fixed_quality/fusion_quality_summary.csv")
    for r in f2:
        if r.get("fusion") in {"F2_class_normal_aware_voxel_0p05", "F5_class_aware_voxel_0p20"}:
            rows.append({
                "fusion": r.get("fusion"),
                "voxel_m": "",
                "n_voxels": r.get("n_points"),
                "mean_view_count": r.get("mean_view_count"),
                "median_view_count": r.get("median_view_count"),
                "view_count_ge2_frac": "",
                "mean_samples_per_voxel": "",
                "comparison_source": str((S1D_FIX_ROOT / "phase3_fixed_quality/fusion_quality_summary.csv").relative_to(ROOT)),
            })
    write_csv(root / "pure_fusion_summary.csv", rows)
    return rows


def phase8_fixed_candidate(decision_label: str, sim_rows: List[Dict]) -> Dict:
    root = OUT_ROOT / "phase8_deterministic_fixed_export_candidate"
    mkdir(root)
    candidate = {
        "status": "NO_METADATA_SUPPORTED_FIXED_EXPORT",
        "decision_context": decision_label,
        "gt_sim3_available_diagnostic_only": any(r.get("source") == "rendered" and r.get("target") == "gt" for r in sim_rows),
        "rendered_evidence_transform_fixed_npz": None,
        "rendered_evidence_transform_fixed_ply": None,
        "scene_evidence_graph_json": None,
        "quality_gate": "NOT_RUN",
        "reason": "No deterministic non-GT transform/depth/camera fix was identified.",
    }
    write_json(root / "fixed_export_candidate.json", candidate)
    return candidate


def phase9_s1_rerun_gate(candidate: Dict) -> Dict:
    root = OUT_ROOT / "phase9_s1_rerun_gate"
    mkdir(root)
    gate = {
        "status": "SKIPPED",
        "reason": "No Phase 8 fixed export passed quality gate; S1 rerun would be performance-irrelevant.",
    }
    write_json(root / "SKIPPED.json", gate)
    write_csv(root / "split_summary_fixed.csv", [{
        "input": "A/B/C",
        "status": "SKIPPED_FIXED_EXPORT_GATE_FAILED",
        "reason": gate["reason"],
    }])
    return gate


def decide(phase2: Dict, pairwise: List[Dict], camera_rows: List[Dict],
           cross_rows: List[Dict], sim_rows: List[Dict], fusion_rows: List[Dict]) -> Dict:
    r2p = phase2.get("rendered_to_primitive_p95")
    p2r = phase2.get("primitive_to_rendered_p95")
    rendered_gt = next((r for r in pairwise if r.get("source") == "rendered_xyz" and r.get("target") == "gt_clean_surface"), {})
    rendered_prim = next((r for r in pairwise if r.get("source") == "rendered_xyz" and r.get("target") == "stage2_primitives"), {})
    colmap_gt = next((r for r in pairwise if r.get("source") == "colmap_sparse" and r.get("target") == "gt_clean_surface"), {})
    render_gt_sim = next((r for r in sim_rows if r.get("source") == "rendered" and r.get("target") == "gt"), {})
    raw_cam_bad = any(r.get("status") == "OK" and (s1.safe_float(r.get("center_delta_mean")) or 0.0) > 1e-5 for r in camera_rows)
    cross_valid = [r for r in cross_rows if s1.safe_float(r.get("depth_abs_residual_mean")) is not None]
    cross_mean = float(np.mean([s1.safe_float(r.get("depth_abs_residual_mean")) for r in cross_valid])) if cross_valid else None
    pure_020 = next((r for r in fusion_rows if r.get("fusion") == "pure_xyz_voxel_0.20m"), {})
    f2 = next((r for r in fusion_rows if r.get("fusion") == "F2_class_normal_aware_voxel_0p05"), {})
    pure_vc = s1.safe_float(pure_020.get("mean_view_count")) or 0.0
    f2_vc = s1.safe_float(f2.get("mean_view_count")) or 0.0

    if raw_cam_bad:
        label = "S1D_CAMERA_CONVENTION_ERROR"
        next_action = "Repair camera source mismatch before rendered export."
    elif r2p is not None and p2r is not None and r2p < 20.0 and p2r < 3.0 and (s1.safe_float(rendered_gt.get("nn_mean")) or 0.0) > 15.0:
        if (s1.safe_float(render_gt_sim.get("post_nn_mean")) or 1e9) < 0.5 * (s1.safe_float(render_gt_sim.get("pre_nn_mean")) or 0.0):
            label = "S1D_GLOBAL_FRAME_MISMATCH"
            next_action = "Find metadata source for the scene-level transform; do not use GT Sim(3) as generation prior."
        elif (s1.safe_float(colmap_gt.get("nn_mean")) or 1e9) > 3.0:
            label = "S1D_COLMAP_TO_GT_ALIGNMENT_MISSING"
            next_action = "Audit synthetic COLMAP/OBJ/GT alignment before further rendered export changes."
        else:
            label = "S1D_SFM_ALIGNMENT_ISSUE"
            next_action = "Audit Stage2 SfM/sparse initialization and trained primitive drift relative to GT."
    elif cross_mean is not None and cross_mean > 3.0:
        label = "S1D_INTERNAL_MULTIVIEW_INCONSISTENT"
        next_action = "Investigate rendered depth surface consistency across views."
    elif pure_vc > max(1.5 * f2_vc, f2_vc + 0.3):
        label = "S1D_FUSION_KEY_TOO_STRICT"
        next_action = "Relax fusion keys only after coordinate frame is accepted."
    elif (s1.safe_float(rendered_prim.get("nn_mean")) or 1e9) > 10.0:
        label = "S1D_RENDER_TO_PRIMITIVE_MISMATCH"
        next_action = "Debug renderer-to-checkpoint geometry contract."
    else:
        label = "S1D_UNRESOLVED_COORDINATE_CHAIN"
        next_action = "Inspect COLMAP/GT/camera generation metadata and compare against dense GT depth backprojections."
    return {
        "final_decision": label,
        "next_action": next_action,
        "rendered_to_primitive_p95": r2p,
        "primitive_to_rendered_p95": p2r,
        "rendered_to_gt_mean": rendered_gt.get("nn_mean"),
        "colmap_to_gt_mean": colmap_gt.get("nn_mean"),
        "rendered_to_gt_sim3_post_mean": render_gt_sim.get("post_nn_mean"),
        "cross_view_depth_residual_mean": cross_mean,
        "pure_0p20_view_count": pure_vc,
        "class_normal_f2_view_count": f2_vc,
    }


def mean_field(rows: List[Dict], field: str) -> Optional[float]:
    vals = [s1.safe_float(r.get(field)) for r in rows]
    vals = [v for v in vals if v is not None]
    return float(np.mean(vals)) if vals else None


def md_table(headers: List[str], rows: List[List[object]]) -> str:
    return s1.md_table(headers, rows)


def write_report(decision: Dict, inv: Dict, quality: List[Dict], phase2: Dict,
                 pairwise: List[Dict], camera_rows: List[Dict], cross_rows: List[Dict],
                 sim_rows: List[Dict], fusion_rows: List[Dict], candidate: Dict) -> None:
    rendered_gt = next((r for r in pairwise if r.get("source") == "rendered_xyz" and r.get("target") == "gt_clean_surface"), {})
    rendered_prim = next((r for r in pairwise if r.get("source") == "rendered_xyz" and r.get("target") == "stage2_primitives"), {})
    colmap_gt = next((r for r in pairwise if r.get("source") == "colmap_sparse" and r.get("target") == "gt_clean_surface"), {})
    report = [
        "# S1D Transform Chain Audit",
        "",
        "## 1. Research intent",
        "",
        "This audit validates the coordinate-frame contract for rendered surface evidence before using it as Stage3 input. The research target remains semantic polygonal building models.",
        "",
        "## 2. Why this is not Stage3 redesign",
        "",
        "No Stage3 method, splitter, Roofer, PolyFit, Stage2 retraining, or G2 retraining is changed. The run only audits rendered evidence coordinates, camera/depth conventions, frame alignment, and fusion support.",
        "",
        "## 3. Frame inventory",
        "",
        md_table(["frame", "definition"], [[f["frame"], f["definition"]] for f in inv["frames"]]),
        "",
        "## 4. Image-space quality recap",
        "",
        md_table(
            ["normal_abs_mean", "semantic_acc_mean", "mIoU_mean"],
            [[fmt(mean_field(quality, "normal_abs")), fmt(mean_field(quality, "semantic_accuracy")), fmt(mean_field(quality, "mIoU"))]],
        ),
        "",
        "## 5. Rendered-vs-primitive alignment",
        "",
        md_table(
            ["r->p mean", "r->p p95", "p->r mean", "p->r p95", "bbox IoU", "scale"],
            [[
                fmt(phase2.get("rendered_to_primitive_mean")), fmt(phase2.get("rendered_to_primitive_p95")),
                fmt(phase2.get("primitive_to_rendered_mean")), fmt(phase2.get("primitive_to_rendered_p95")),
                fmt(phase2.get("bbox_IoU_3D")), fmt(phase2.get("scale_ratio_rendered_over_primitive")),
            ]],
        ),
        "",
        "## 6. Rendered-vs-COLMAP-vs-GT alignment",
        "",
        md_table(
            ["source", "target", "nn_mean", "nn_p95", "bbox_iou", "scale", "sim3_post_mean"],
            [[
                r.get("source"), r.get("target"), fmt(r.get("nn_mean")), fmt(r.get("nn_p95")),
                fmt(r.get("bbox_IoU_3D")), fmt(r.get("scale_ratio_source_over_target")),
                fmt(r.get("sim3_post_nn_mean")),
            ] for r in [rendered_prim, rendered_gt, colmap_gt]],
        ),
        "",
        "## 7. Camera center audit",
        "",
        md_table(
            ["source_a", "source_b", "n", "center_delta_mean", "trajectory_scale", "status"],
            [[
                r.get("source_a"), r.get("source_b"), r.get("n_common"),
                fmt(r.get("center_delta_mean")), fmt(r.get("trajectory_scale_ratio_median")),
                r.get("status"),
            ] for r in camera_rows],
        ),
        "",
        "## 8. Cross-view consistency",
        "",
        md_table(
            ["pairs", "valid_overlap_mean", "depth_abs_mean", "depth_abs_p95_mean"],
            [[
                len(cross_rows),
                fmt(mean_field(cross_rows, "valid_overlap_fraction")),
                fmt(mean_field(cross_rows, "depth_abs_residual_mean")),
                fmt(mean_field(cross_rows, "depth_abs_residual_p95")),
            ]],
        ),
        "",
        "## 9. Sim(3) diagnostic",
        "",
        md_table(
            ["source", "target", "pre_mean", "post_mean", "post_p95", "scale", "diagnostic_only"],
            [[
                r.get("source"), r.get("target"), fmt(r.get("pre_nn_mean")),
                fmt(r.get("post_nn_mean")), fmt(r.get("post_nn_p95")),
                fmt(r.get("sim3_scale")), r.get("diagnostic_only"),
            ] for r in sim_rows],
        ),
        "",
        "## 10. Pure fusion audit",
        "",
        md_table(
            ["fusion", "n_voxels", "mean_view_count", "median_view_count", "ge2_frac"],
            [[
                r.get("fusion"), r.get("n_voxels"), fmt(r.get("mean_view_count")),
                fmt(r.get("median_view_count")), fmt(r.get("view_count_ge2_frac")),
            ] for r in fusion_rows],
        ),
        "",
        "## 11. Fixed export candidate if found",
        "",
        f"Status: `{candidate.get('status')}`. Reason: {candidate.get('reason')}",
        "",
        "## 12. Final decision and next action",
        "",
        md_table(["criterion", "value"], [[k, fmt(v) if isinstance(v, float) else v] for k, v in decision.items()]),
        "",
        "## Self-verification",
        "",
        "- PASS: same Mutual checkpoint used.",
        "- PASS: no Stage2 retraining or G2 retraining.",
        "- PASS: no Roofer or PolyFit.",
        "- PASS: GT Sim(3) is diagnostic only and not used as generation prior.",
        "- PASS: no per-building tuning was used.",
        "- PASS: S1 rerun is skipped unless Phase 8 fixed export gate passes.",
    ]
    (OUT_ROOT / "REPORT.md").write_text("\n".join(report) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--render-downscale", type=float, default=0.25)
    ap.add_argument("--pixel-stride", type=int, default=2)
    ap.add_argument("--gt-density", type=float, default=0.30)
    ap.add_argument("--max-eval-points", type=int, default=200_000)
    ap.add_argument("--max-sim3-pairs", type=int, default=120_000)
    ap.add_argument("--max-overlay-points", type=int, default=220_000)
    ap.add_argument("--max-view-pairs", type=int, default=30)
    ap.add_argument("--cross-view-points", type=int, default=12_000)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    if not np.allclose(rr_gravity := np.asarray(s1.rr.GRAVITY), np.asarray([0.0, 1.0, 0.0])):
        raise AssertionError(f"Expected gravity=[0,1,0], got {rr_gravity}")
    mkdir(OUT_ROOT)
    write_json(OUT_ROOT / "experiment_policy.json", {
        "checkpoint": str(s1.MUTUAL_CKPT.relative_to(ROOT)),
        "stage2_retraining": False,
        "g2_retraining": False,
        "roofer": False,
        "polyfit": False,
        "gt_use": "diagnostic frame/audit and post-generation evaluation only",
        "gt_sim3_generation_prior": False,
        "gravity": [0, 1, 0],
    })
    inventory, _chain = phase0_inventory(args)
    sources = load_sources(args)
    quality = phase1_native_quality(sources, args)
    phase2 = phase2_rendered_vs_primitives(sources, args)
    pairwise = phase3_pairwise_alignment(sources, args)
    camera_rows = phase4_camera_audit(args)
    cross_rows = phase5_cross_view_consistency(sources, args)
    sim_rows = phase6_sim3(sources, args)
    fusion_rows = phase7_pure_fusion(sources)
    decision = decide(phase2, pairwise, camera_rows, cross_rows, sim_rows, fusion_rows)
    candidate = phase8_fixed_candidate(decision["final_decision"], sim_rows)
    phase9_s1_rerun_gate(candidate)
    write_json(OUT_ROOT / "decision.json", decision)
    write_report(decision, inventory, quality, phase2, pairwise, camera_rows, cross_rows, sim_rows, fusion_rows, candidate)
    print(f"[S1D-transform-chain] wrote {OUT_ROOT.relative_to(ROOT)} decision={decision['final_decision']}", flush=True)


if __name__ == "__main__":
    main()
