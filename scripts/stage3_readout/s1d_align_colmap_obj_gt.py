"""S1D-align: synthetic COLMAP/OBJ/GT alignment audit.

This follow-on audit closes the scene-level coordinate contract before making
any Stage3 performance claim from rendered evidence. It uses GT only for
diagnostic frame checks and keeps all transforms scene-level.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np
import torch
import yaml
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import scripts.stage3_readout.e3_stage2_oracle_split as e3  # noqa: E402
import scripts.stage3_readout.s1_rendered_e2style_gate as s1  # noqa: E402
import scripts.stage3_readout.s1d_transform_chain_audit as tc  # noqa: E402
from scripts.stage3_readout.obj_gt import parse_scene_obj  # noqa: E402
from src.stage2.colmap_io import read_cameras_bin, read_images_bin, read_points3d_bin  # noqa: E402
from src.stage2.dataloader import ColmapDataset  # noqa: E402


OUT_ROOT = ROOT / "results/stage3_rendered_evidence/S1D_align_colmap_obj_gt"
S1D_FIX_ROOT = ROOT / "results/stage3_rendered_evidence/S1D_fix_export_and_rerun"
S1D_CHAIN_ROOT = ROOT / "results/stage3_rendered_evidence/S1D_transform_chain_audit"
SCENE = ROOT / "results/phase2_synthesis/scene.obj"
DATASET_ROOT = ROOT / "results/phase2_synthesis/dataset"
RAW_CAM_DIR = ROOT / "results/phase2_synthesis/renders_raw"
MATRIXCITY_POSE_JSON = ROOT / "data/matrixcity/small_city/aerial/pose/block_all/transforms_train.json"

RES_W, RES_H = 2048, 1536
FOV_DEG = 74.0
ALTITUDE = 80.0
FORWARD_OVERLAP = 0.80
SIDE_OVERLAP = 0.70
OBLIQUE_TILT_DEG = 45.0
OBLIQUE_AZIMUTHS = [0, 90, 180, 270]


def mkdir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, payload: Dict) -> None:
    mkdir(path.parent)
    path.write_text(json.dumps(payload, indent=2, default=s1.jsonable) + "\n")


def write_csv(path: Path, rows: List[Dict], fields: Optional[List[str]] = None) -> None:
    s1.write_csv(path, rows, fields)


def read_csv(path: Path) -> List[Dict]:
    if not path.exists():
        return []
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def fmt(value: object, nd: int = 3) -> str:
    return s1.fmt(value, nd)


def camera_center_from_w2c(w2c: np.ndarray) -> np.ndarray:
    R = w2c[:3, :3]
    t = w2c[:3, 3]
    return -R.T @ t


def transform_points(points: np.ndarray, sim3: Dict) -> np.ndarray:
    scale = float(sim3.get("scale", 1.0))
    R = np.asarray(sim3.get("rotation", np.eye(3)), dtype=np.float64)
    t = np.asarray(sim3.get("translation", [0.0, 0.0, 0.0]), dtype=np.float64)
    return scale * (points.astype(np.float64) @ R) + t


def transform_normals(normals: np.ndarray, sim3: Dict) -> np.ndarray:
    R = np.asarray(sim3.get("rotation", np.eye(3)), dtype=np.float64)
    out = normals.astype(np.float64) @ R
    return out / np.maximum(np.linalg.norm(out, axis=1, keepdims=True), 1e-12)


def load_dataset(load_gt: bool = False, render_downscale: float = 0.25) -> ColmapDataset:
    return ColmapDataset(
        root=DATASET_ROOT,
        downscale=render_downscale,
        load_depth=load_gt,
        load_normal=load_gt,
        load_semantic=load_gt,
    )


def load_npz(path: Path) -> Dict[str, np.ndarray]:
    data = np.load(path, allow_pickle=False)
    return {k: data[k] for k in data.files}


def scene_vertices_obj() -> np.ndarray:
    return parse_scene_obj(SCENE, frame="obj")["vertices"].astype(np.float64)


def obj_to_blender(points: np.ndarray) -> np.ndarray:
    # Matches render_scene.py T_obj_to_bl: (x, y, z)_obj -> (x, -z, y)_bl.
    p = points.astype(np.float64)
    return np.stack([p[:, 0], -p[:, 2], p[:, 1]], axis=1)


def blender_to_obj(points: np.ndarray) -> np.ndarray:
    p = points.astype(np.float64)
    return np.stack([p[:, 0], p[:, 2], -p[:, 1]], axis=1)


def reconstruct_synthetic_camera_centers() -> Dict[str, np.ndarray]:
    """Reconstruct render_scene.py flight-plan centers from scene.obj metadata."""
    verts_bl = obj_to_blender(scene_vertices_obj())
    bbox_min = verts_bl.min(axis=0)
    bbox_max = verts_bl.max(axis=0)
    extent = bbox_max - bbox_min
    hfov = math.radians(FOV_DEG)
    footprint_w = 2 * ALTITUDE * math.tan(hfov / 2)
    vfov = 2 * math.atan(math.tan(hfov / 2) * RES_H / RES_W)
    footprint_h = 2 * ALTITUDE * math.tan(vfov / 2)
    side_spacing = (1 - SIDE_OVERLAP) * footprint_w
    fwd_spacing = (1 - FORWARD_OVERLAP) * footprint_h
    n_cols = max(2, int(math.ceil(extent[0] / side_spacing)) + 1)
    n_rows = max(2, int(math.ceil(extent[1] / fwd_spacing)) + 1)
    xs = np.linspace(bbox_min[0], bbox_max[0], n_cols)
    ys = np.linspace(bbox_min[1], bbox_max[1], n_rows)
    roof_top_z = bbox_min[2]
    altitude_z = roof_top_z - ALTITUDE
    centers: Dict[str, np.ndarray] = {}
    for iy, y in enumerate(ys):
        for ix, x in enumerate(xs):
            center_obj = blender_to_obj(np.asarray([[x, y, altitude_z]], dtype=np.float64))[0]
            centers[f"waypt_{iy:02d}_{ix:02d}_nadir.png"] = center_obj
            for az in OBLIQUE_AZIMUTHS:
                centers[f"waypt_{iy:02d}_{ix:02d}_oblique_az{az:03d}.png"] = center_obj
    return centers


def colmap_cameras_and_images() -> Tuple[Dict, Dict]:
    sparse = DATASET_ROOT / "sparse/0"
    return (
        read_cameras_bin(sparse / "cameras.bin"),
        read_images_bin(sparse / "images.bin"),
    )


def colmap_camera_centers() -> Dict[str, np.ndarray]:
    _cams, images = colmap_cameras_and_images()
    out = {}
    for img in images.values():
        out[img.name] = camera_center_from_w2c(img.world_to_camera())
    return out


def raw_camera_json_centers() -> Dict[str, np.ndarray]:
    out = {}
    if not RAW_CAM_DIR.exists():
        return out
    for path in sorted(RAW_CAM_DIR.glob("*_cam.json")):
        payload = json.loads(path.read_text())
        w2c = np.asarray(payload.get("w2c"), dtype=np.float64)
        if w2c.shape == (4, 4):
            out[f"{path.stem.rsplit('_cam', 1)[0]}.png"] = camera_center_from_w2c(w2c)
    return out


def matrixcity_pose_names() -> List[str]:
    if not MATRIXCITY_POSE_JSON.exists():
        return []
    data = json.loads(MATRIXCITY_POSE_JSON.read_text())
    return [Path(fr.get("file_path", "")).name for fr in data.get("frames", [])]


def estimate_sim3_from_pairs(src: np.ndarray, dst: np.ndarray) -> Dict:
    sim = tc.estimate_sim3(src, dst)
    if not sim.get("ok"):
        return {"ok": False}
    T = np.eye(4, dtype=np.float64)
    T[:3, :3] = sim["scale"] * sim["rotation"].T
    T[:3, 3] = sim["translation"]
    return {
        "ok": True,
        "scale": float(sim["scale"]),
        "rotation": sim["rotation"],
        "translation": sim["translation"],
        "matrix_4x4_point_row_convention": T,
        "residual_mean": sim["residual_mean"],
        "residual_p95": sim["residual_p95"],
        "rmse": sim["rmse"],
    }


def nearest_row(source_name: str, target_name: str, source: np.ndarray, target: np.ndarray,
                max_eval: int, seed: int) -> Dict:
    nn = tc.nearest_metrics(source, target, max_eval, seed)
    rev = tc.nearest_metrics(target, source, max_eval, seed + 1000)
    return {
        "source": source_name,
        "target": target_name,
        "n_source": int(len(source)),
        "n_target": int(len(target)),
        "nn_mean": nn.get("nn_mean"),
        "nn_median": nn.get("nn_median"),
        "nn_p95": nn.get("nn_p95"),
        "reverse_nn_mean": rev.get("nn_mean"),
        "reverse_nn_p95": rev.get("nn_p95"),
        "bbox_IoU_3D": tc.bbox_iou_3d(source, target),
        "scale_ratio_source_over_target": tc.bbox_diag(source) / max(tc.bbox_diag(target), 1e-12),
    }


def _parse_obj_face_indices(tok: str) -> int:
    return int(tok.split("/", 1)[0]) - 1


def _scene_all_triangles() -> Tuple[np.ndarray, np.ndarray]:
    verts: List[List[float]] = []
    tris: List[np.ndarray] = []
    for ln in SCENE.read_text().splitlines():
        if not ln or ln.startswith("#"):
            continue
        head, *rest = ln.split()
        if head == "v":
            verts.append([float(x) for x in rest[:3]])
        elif head == "f" and len(rest) >= 3:
            idx = [_parse_obj_face_indices(t) for t in rest]
            # Fan triangulation is sufficient for the planar convex/quasi-convex
            # faces emitted by compose_scene.py.
            for i in range(1, len(idx) - 1):
                tris.append(np.asarray([idx[0], idx[i], idx[i + 1]], dtype=np.int64))
    V = np.asarray(verts, dtype=np.float64)
    T = np.asarray(tris, dtype=np.int64)
    tri_pts = V[T]
    areas = 0.5 * np.linalg.norm(np.cross(tri_pts[:, 1] - tri_pts[:, 0], tri_pts[:, 2] - tri_pts[:, 0]), axis=1)
    keep = areas > 1e-12
    return tri_pts[keep], areas[keep]


def sample_scene_all_surface(n_points: int, seed: int) -> np.ndarray:
    tris, areas = _scene_all_triangles()
    rng = np.random.default_rng(seed)
    prob = areas / max(float(areas.sum()), 1e-12)
    tri_idx = rng.choice(len(tris), size=int(n_points), replace=True, p=prob)
    tri = tris[tri_idx]
    u = rng.random(len(tri))
    v = rng.random(len(tri))
    swap = (u + v) > 1.0
    u[swap] = 1.0 - u[swap]
    v[swap] = 1.0 - v[swap]
    return tri[:, 0] + u[:, None] * (tri[:, 1] - tri[:, 0]) + v[:, None] * (tri[:, 2] - tri[:, 0])


def load_sources(args: argparse.Namespace) -> Dict[str, Dict]:
    rendered_raw = load_npz(S1D_FIX_ROOT / "phase2_fixed_export/raw_rendered_samples_fixed.npz")
    prims = e3.load_primitives("Mutual")
    active = np.where(e3.active_mask(prims))[0]
    prim_ev = e3.evidence_from_indices(prims, active)
    buildings = parse_scene_obj(SCENE, frame="obj")["buildings"]
    e2_gt = s1.sample_gt_surfaces(buildings, min_points=32, density=args.gt_density)
    colmap_pts = read_points3d_bin(DATASET_ROOT / "sparse/0/points3D.bin")[:, :3].astype(np.float64)
    return {
        "rendered": {
            "points": rendered_raw["xyz"].astype(np.float64),
            "normals": rendered_raw["normal"].astype(np.float64),
            "classes": rendered_raw["label"].astype(np.int64),
            "sem_probs": rendered_raw["sem_prob"].astype(np.float64),
            "weights": rendered_raw["confidence"].astype(np.float64),
            "view_id": rendered_raw["view_id"].astype(np.int64),
        },
        "primitives": {
            "points": prim_ev["points"].astype(np.float64),
            "normals": prim_ev["normals"].astype(np.float64),
            "classes": prim_ev["classes"].astype(np.int64),
            "weights": prim_ev["weights"].astype(np.float64),
        },
        "colmap_sparse": {"points": colmap_pts},
        "e2_building_clean": {
            "points": e2_gt["points"].astype(np.float64),
            "normals": e2_gt["normals"].astype(np.float64),
            "classes": e2_gt["classes"].astype(np.int64),
            "weights": np.ones(len(e2_gt["points"]), dtype=np.float64),
        },
        "gt_scene_all": {"points": sample_scene_all_surface(args.scene_sample_points, args.seed)},
    }


def phase0_inventory() -> Tuple[Dict, List[Dict]]:
    root = OUT_ROOT / "phase0_alignment_artifact_inventory"
    mkdir(root)
    sparse = DATASET_ROOT / "sparse/0"
    artifact_specs = [
        ("colmap_cameras_bin", sparse / "cameras.bin", "COLMAP camera intrinsics"),
        ("colmap_images_bin", sparse / "images.bin", "COLMAP image poses/names"),
        ("colmap_points3D_bin", sparse / "points3D.bin", "COLMAP sparse/init points"),
        ("dataset_images", DATASET_ROOT / "images", "560 rendered RGB images"),
        ("dataset_depth_exr", DATASET_ROOT / "depth", "MatrixCity-style GT depth EXR"),
        ("dataset_normal_exr", DATASET_ROOT / "normal", "MatrixCity-style GT normal EXR"),
        ("dataset_semantic_png", DATASET_ROOT / "semantic", "rule/rendered semantic labels"),
        ("scene_obj", SCENE, "OBJ/COLMAP-frame synthetic GT scene"),
        ("raw_camera_json_dir", RAW_CAM_DIR, "raw render camera JSONs"),
        ("matrixcity_pose_json", MATRIXCITY_POSE_JSON, "upstream MatrixCity pose JSON"),
        ("mutual_checkpoint", s1.MUTUAL_CKPT, "same Mutual checkpoint as S1/S1D"),
        ("mutual_config", s1.MUTUAL_CONFIG, "Mutual training config"),
        ("s1d_raw_rendered_samples_fixed", S1D_FIX_ROOT / "phase2_fixed_export/raw_rendered_samples_fixed.npz", "previous S1D rendered xyz export"),
    ]
    inventory = {"artifacts": [], "glob_counts": {}, "gravity": [0, 1, 0]}
    missing = []
    for name, path, desc in artifact_specs:
        exists = path.exists()
        count = None
        if exists and path.is_dir():
            count = sum(1 for _ in path.iterdir())
        inventory["artifacts"].append({
            "name": name,
            "path": str(path.relative_to(ROOT)) if path.exists() or str(path).startswith(str(ROOT)) else str(path),
            "exists": bool(exists),
            "count": count,
            "description": desc,
        })
        if not exists:
            missing.append((name, path, desc))
    for pattern in ["*_cam.json", "*camera*.json", "*transforms*.json", "cameras.*", "images.*", "points3D.*"]:
        inventory["glob_counts"][pattern] = len(list(ROOT.glob(f"**/{pattern}")))
    cfg = yaml.safe_load(s1.MUTUAL_CONFIG.read_text())
    ckpt = torch.load(s1.MUTUAL_CKPT, map_location="cpu", weights_only=False)
    inventory["config"] = {
        "path": str(s1.MUTUAL_CONFIG.relative_to(ROOT)),
        "data_root": cfg.get("data_root"),
        "downscale": cfg.get("downscale"),
        "depth_scale": cfg.get("depth_scale"),
    }
    inventory["checkpoint"] = {
        "path": str(s1.MUTUAL_CKPT.relative_to(ROOT)),
        "top_level_keys": sorted(list(ckpt.keys())),
        "normalization_keys": [k for k in ckpt.keys() if "norm" in str(k).lower() or "scale" in str(k).lower()],
        "state_keys_sample": sorted(list(ckpt.get("state_dict", {}).keys()))[:30],
    }
    write_json(root / "artifact_inventory.json", inventory)
    missing_lines = ["# Missing Alignment Artifacts", ""]
    for name, path, desc in missing:
        missing_lines.append(f"- `{name}`: `{path}` ({desc})")
    if not missing:
        missing_lines.append("- None.")
    (root / "missing_artifacts.md").write_text("\n".join(missing_lines) + "\n")
    candidates = [
        {
            "candidate_id": "T0_identity_colmap_obj_gt",
            "source": "export_colmap.py + scene.obj",
            "transform": "identity",
            "metadata_supported": True,
            "diagnostic_only": False,
            "notes": "COLMAP points3D are sampled directly from scene.obj; images.bin is written from OBJ-frame w2c.",
        },
        {
            "candidate_id": "T1_reconstructed_flightplan_centers",
            "source": "render_scene.py constants + scene.obj bbox",
            "transform": "COLMAP camera centers to reconstructed synthetic centers",
            "metadata_supported": True,
            "diagnostic_only": False,
            "notes": "Closes missing raw *_cam.json by deterministic regeneration of camera centers.",
        },
        {
            "candidate_id": "T2_matrixcity_pose_json",
            "source": "data/matrixcity/.../transforms_train.json",
            "transform": "filename/numeric/sorted-order diagnostic",
            "metadata_supported": False,
            "diagnostic_only": True,
            "notes": "Upstream MatrixCity names do not match phase2 waypt names.",
        },
        {
            "candidate_id": "T3_gt_fit_sim3_rendered_to_e2",
            "source": "nearest-neighbor GT fit",
            "transform": "Sim(3) rendered evidence to E2 building clean",
            "metadata_supported": False,
            "diagnostic_only": True,
            "notes": "Never used as proposed generation prior.",
        },
    ]
    write_csv(root / "transform_candidates_table.csv", candidates)
    return inventory, candidates


def phase1_camera_matching() -> Tuple[List[Dict], Dict]:
    root = OUT_ROOT / "phase1_camera_name_index_matching"
    mkdir(root)
    cams, images = colmap_cameras_and_images()
    synthetic = reconstruct_synthetic_camera_centers()
    raw = raw_camera_json_centers()
    dataset_names = {p.name for p in (DATASET_ROOT / "images").glob("*.png")}
    matrix_names = set(matrixcity_pose_names())
    rows = []
    for img in sorted(images.values(), key=lambda im: im.name):
        cam = cams[img.camera_id]
        K = cam.K()
        colmap_center = camera_center_from_w2c(img.world_to_camera())
        syn_center = synthetic.get(img.name)
        raw_center = raw.get(img.name)
        exact_dataset = img.name in dataset_names
        exact_synthetic = syn_center is not None
        exact_raw = raw_center is not None
        exact_matrix = img.name in matrix_names
        center_delta = float(np.linalg.norm(colmap_center - syn_center)) if syn_center is not None else None
        rows.append({
            "colmap_image_id": img.id,
            "colmap_name": img.name,
            "basename": Path(img.name).stem,
            "camera_id": img.camera_id,
            "match_exact_dataset_image": exact_dataset,
            "match_exact_reconstructed_synthetic": exact_synthetic,
            "match_exact_raw_cam_json": exact_raw,
            "match_exact_matrixcity_pose": exact_matrix,
            "selected_match_source": "reconstructed_flightplan_metadata" if exact_synthetic else "",
            "image_size_ok": (cam.width == RES_W and cam.height == RES_H),
            "fx": float(K[0, 0]),
            "fy": float(K[1, 1]),
            "cx": float(K[0, 2]),
            "cy": float(K[1, 2]),
            "expected_fx": float(RES_W / (2.0 * math.tan(math.radians(FOV_DEG) / 2.0))),
            "expected_cx": RES_W / 2.0,
            "expected_cy": RES_H / 2.0,
            "intrinsics_fx_abs_delta": abs(float(K[0, 0]) - float(RES_W / (2.0 * math.tan(math.radians(FOV_DEG) / 2.0)))),
            "center_delta_to_reconstructed_synthetic": center_delta,
            "status": "OK" if exact_synthetic and center_delta is not None and center_delta < 1e-4 else "NO_SYNTHETIC_MATCH",
        })
    n = len(rows)
    n_ok = sum(1 for r in rows if r["status"] == "OK")
    summary = {
        "n_colmap_images": n,
        "n_dataset_image_exact": sum(1 for r in rows if r["match_exact_dataset_image"]),
        "n_reconstructed_synthetic_exact": sum(1 for r in rows if r["match_exact_reconstructed_synthetic"]),
        "n_raw_cam_json_exact": sum(1 for r in rows if r["match_exact_raw_cam_json"]),
        "n_matrixcity_pose_exact": sum(1 for r in rows if r["match_exact_matrixcity_pose"]),
        "selected_match_fraction": float(n_ok / max(n, 1)),
        "camera_match_status": "OK" if n_ok >= int(0.8 * max(n, 1)) else "CAMERA_MATCH_LOW",
        "raw_cam_json_status": "MISSING" if not raw else "PRESENT",
        "matrixcity_pose_sorted_order_status": "DIAGNOSTIC_ONLY_NAME_SPACE_MISMATCH",
    }
    write_csv(root / "camera_matching.csv", rows)
    write_json(root / "camera_matching_summary.json", summary)
    return rows, summary


def phase2_colmap_gt_sim3(sources: Dict, match_summary: Dict, args: argparse.Namespace) -> Tuple[Dict, List[Dict]]:
    root = OUT_ROOT / "phase2_colmap_to_gt_camera_center_sim3"
    mkdir(root)
    colmap_centers = colmap_camera_centers()
    synthetic_centers = reconstruct_synthetic_camera_centers()
    common = sorted(set(colmap_centers) & set(synthetic_centers))
    if not common:
        blocked = {
            "status": "CAMERA_SIM3_BLOCKED_NO_MATCH",
            "source": "COLMAP camera centers",
            "target": "reconstructed synthetic camera centers",
        }
        write_json(root / "T_colmap_to_gt.json", blocked)
        write_csv(root / "camera_alignment_metrics.csv", [{"status": "CAMERA_SIM3_BLOCKED_NO_MATCH"}])
        return blocked, [{"status": "CAMERA_SIM3_BLOCKED_NO_MATCH"}]
    A = np.stack([colmap_centers[k] for k in common], axis=0)
    B = np.stack([synthetic_centers[k] for k in common], axis=0)
    sim = estimate_sim3_from_pairs(A, B)
    T_payload = {
        "status": "OK" if sim.get("ok") else "FAILED",
        "transform_source": "metadata_supported_reconstructed_render_scene_flightplan",
        "diagnostic_only": False,
        "n_camera_pairs": len(common),
        "scale": sim.get("scale"),
        "rotation": sim.get("rotation"),
        "translation": sim.get("translation"),
        "matrix_4x4_point_row_convention": sim.get("matrix_4x4_point_row_convention"),
        "residual_mean": sim.get("residual_mean"),
        "residual_p95": sim.get("residual_p95"),
        "rmse": sim.get("rmse"),
        "gravity": [0, 1, 0],
    }
    write_json(root / "T_colmap_to_gt.json", T_payload)
    colmap = sources["colmap_sparse"]["points"]
    scene_all = sources["gt_scene_all"]["points"]
    e2 = sources["e2_building_clean"]["points"]
    rows = [
        {
            "metric": "camera_center_colmap_to_reconstructed_synthetic",
            "n": len(common),
            "mean": sim.get("residual_mean"),
            "p95": sim.get("residual_p95"),
            "scale": sim.get("scale"),
            "status": "OK" if sim.get("residual_p95", 1e9) < 1e-4 else "HIGH_RESIDUAL",
        },
        {
            "metric": "colmap_sparse_to_scene_obj_all_surface",
            **nearest_row("colmap_sparse", "scene_obj_all_surface", colmap, scene_all, args.max_eval_points, args.seed),
            "status": "OK",
        },
        {
            "metric": "colmap_sparse_to_e2_building_clean",
            **nearest_row("colmap_sparse", "e2_building_clean", colmap, e2, args.max_eval_points, args.seed + 1),
            "status": "BUILDING_ONLY_TARGET_HAS_TERRAIN_OUTSIDE_BUILDING_RESIDUAL",
        },
    ]
    write_csv(root / "camera_alignment_metrics.csv", rows)
    return T_payload, rows


def phase3_ckpt_colmap_alignment(sources: Dict, args: argparse.Namespace) -> Tuple[List[Dict], Dict]:
    root = OUT_ROOT / "phase3_stage2_checkpoint_frame_to_colmap"
    mkdir(root)
    ckpt = torch.load(s1.MUTUAL_CKPT, map_location="cpu", weights_only=False)
    state = ckpt.get("state_dict", {})
    norm_keys = [k for k in list(ckpt.keys()) + list(state.keys()) if "norm" in str(k).lower() or "scale" in str(k).lower() or "center" in str(k).lower()]
    norm_payload = {
        "checkpoint": str(s1.MUTUAL_CKPT.relative_to(ROOT)),
        "top_level_keys": sorted(list(ckpt.keys())),
        "state_keys_sample": sorted(list(state.keys()))[:50],
        "normalization_or_scene_transform_keys": sorted(norm_keys),
        "normalization_inverse_available": False,
        "interpretation": "No explicit checkpoint normalization transform was found; Stage2 means are expected in COLMAP/OBJ frame.",
    }
    write_json(root / "checkpoint_normalization.json", norm_payload)
    sets = {
        "rendered_xyz": sources["rendered"]["points"],
        "stage2_primitives_active": sources["primitives"]["points"],
        "colmap_sparse": sources["colmap_sparse"]["points"],
        "scene_obj_all_surface": sources["gt_scene_all"]["points"],
        "e2_building_clean": sources["e2_building_clean"]["points"],
    }
    pairs = [
        ("rendered_xyz", "stage2_primitives_active"),
        ("rendered_xyz", "colmap_sparse"),
        ("rendered_xyz", "scene_obj_all_surface"),
        ("rendered_xyz", "e2_building_clean"),
        ("stage2_primitives_active", "colmap_sparse"),
        ("stage2_primitives_active", "scene_obj_all_surface"),
        ("stage2_primitives_active", "e2_building_clean"),
    ]
    rows = []
    for i, (a, b) in enumerate(pairs):
        row = nearest_row(a, b, sets[a], sets[b], args.max_eval_points, args.seed + i)
        sim = tc.sim3_diagnostic(sets[a], sets[b], args.max_sim3_pairs, args.seed + 100 + i)
        row.update({
            "sim3_diagnostic_only": True,
            "sim3_scale": sim.get("sim3_scale"),
            "sim3_post_nn_mean": sim.get("post_nn_mean"),
            "sim3_post_nn_p95": sim.get("post_nn_p95"),
            "interpretation": "metadata_identity_expected; no checkpoint normalization inverse available",
        })
        rows.append(row)
    write_csv(root / "ckpt_colmap_alignment.csv", rows)
    return rows, norm_payload


def phase4_cross_view(sources: Dict, args: argparse.Namespace) -> List[Dict]:
    old_out = tc.OUT_ROOT
    tc.OUT_ROOT = OUT_ROOT
    try:
        temp_rows = tc.phase5_cross_view_consistency(sources, args)
    finally:
        tc.OUT_ROOT = old_out
    src_dir = OUT_ROOT / "phase5_cross_view_consistency"
    dst_dir = OUT_ROOT / "phase4_rendered_internal_cross_view_consistency"
    if dst_dir.exists():
        shutil.rmtree(dst_dir)
    if src_dir.exists():
        src_dir.rename(dst_dir)
    return temp_rows


def phase5_pure_fusion_by_transform(sources: Dict, T_colmap_to_gt: Dict, args: argparse.Namespace) -> List[Dict]:
    root = OUT_ROOT / "phase5_pure_spatial_fusion_candidate_transforms"
    mkdir(root)
    rendered = sources["rendered"]
    points = rendered["points"]
    view_ids = rendered["view_id"]
    identity = {"scale": 1.0, "rotation": np.eye(3), "translation": np.zeros(3)}
    candidates = [
        ("identity_colmap_obj_gt_metadata", identity, True, False),
    ]
    if T_colmap_to_gt.get("status") == "OK":
        candidates.append(("T_colmap_to_gt_camera_metadata", T_colmap_to_gt, True, False))
    e2 = sources["e2_building_clean"]["points"]
    sim_diag = tc.sim3_diagnostic(points, e2, args.max_sim3_pairs, args.seed + 3030)
    if sim_diag.get("sim3_ok"):
        candidates.append((
            "T_rendered_to_e2_gt_sim3_diagnostic_only",
            {"scale": sim_diag["sim3_scale"], "rotation": sim_diag["rotation"], "translation": sim_diag["translation"]},
            False,
            True,
        ))
    rows = []
    for candidate_id, sim, metadata_supported, diagnostic_only in candidates:
        p = transform_points(points, sim)
        for voxel in [0.05, 0.10, 0.20, 0.50]:
            rows.append({
                "candidate_id": candidate_id,
                "voxel_m": voxel,
                "metadata_supported": metadata_supported,
                "diagnostic_only": diagnostic_only,
                **tc.pure_fuse(p, view_ids, voxel),
            })
    write_csv(root / "pure_fusion_by_transform.csv", rows)
    return rows


def evidence_payload(points: np.ndarray, normals: np.ndarray, classes: np.ndarray,
                     weights: np.ndarray, sem_probs: Optional[np.ndarray] = None,
                     view_id: Optional[np.ndarray] = None) -> Dict[str, np.ndarray]:
    if sem_probs is None:
        n_classes = max(4, int(np.max(classes)) + 1 if len(classes) else 4)
        sem_probs = np.zeros((len(classes), n_classes), dtype=np.float64)
        if len(classes):
            sem_probs[np.arange(len(classes)), classes.astype(np.int64)] = 1.0
    payload = {
        "points": points.astype(np.float32),
        "xyz": points.astype(np.float32),
        "normals": normals.astype(np.float32),
        "normal": normals.astype(np.float32),
        "classes": classes.astype(np.int64),
        "label": classes.astype(np.int64),
        "weights": weights.astype(np.float32),
        "support_weight": weights.astype(np.float32),
        "sem_probs": sem_probs.astype(np.float32),
        "semantic_prob": sem_probs.astype(np.float32),
        "semantic_probability": sem_probs.astype(np.float32),
    }
    if view_id is not None:
        payload["view_id"] = view_id.astype(np.int64)
    return payload


def write_evidence_ply(path: Path, evidence: Dict, max_points: int = 700_000) -> None:
    s1.write_binary_ply(path, evidence, max_points=max_points)


def phase6_common_frame_construction(sources: Dict, T_colmap_to_gt: Dict, args: argparse.Namespace) -> Dict:
    root = OUT_ROOT / "phase6_common_frame_evidence_construction"
    mkdir(root)
    metadata_supported = T_colmap_to_gt.get("status") == "OK"
    sim = T_colmap_to_gt if metadata_supported else {"scale": 1.0, "rotation": np.eye(3), "translation": np.zeros(3)}
    rendered = sources["rendered"]
    points_common = transform_points(rendered["points"], sim)
    normals_common = transform_normals(rendered["normals"], sim)
    rendered_common = evidence_payload(
        points_common,
        normals_common,
        rendered["classes"],
        rendered["weights"],
        sem_probs=rendered["sem_probs"],
        view_id=rendered["view_id"],
    )
    np.savez_compressed(root / "rendered_evidence_common.npz", **rendered_common)
    write_evidence_ply(root / "rendered_evidence_common.ply", rendered_common, max_points=args.max_ply_points)
    e2 = sources["e2_building_clean"]
    e2_common = evidence_payload(e2["points"], e2["normals"], e2["classes"], e2["weights"])
    np.savez_compressed(root / "gt_clean_evidence_in_colmap_or_ckpt_frame.npz", **e2_common)
    write_evidence_ply(root / "gt_clean_evidence_in_colmap_or_ckpt_frame.ply", e2_common, max_points=args.max_ply_points)
    class_counts = {str(c): int(np.sum(rendered_common["classes"] == c)) for c in [0, 1, 2, 3]}
    q_all = nearest_row("rendered_common", "scene_obj_all_surface", points_common, sources["gt_scene_all"]["points"], args.max_eval_points, args.seed + 501)
    q_e2 = nearest_row("rendered_common", "e2_building_clean", points_common, e2["points"], args.max_eval_points, args.seed + 502)
    roof_mask = rendered_common["classes"] == 1
    wall_mask = rendered_common["classes"] == 2
    terrain_mask = rendered_common["classes"] == 3
    quality_rows = [
        {"target": "scene_obj_all_surface", **q_all},
        {"target": "e2_building_clean", **q_e2},
    ]
    for name, mask, cls in [("roof_only", roof_mask, 1), ("wall_only", wall_mask, 2), ("terrain_only", terrain_mask, 3)]:
        gt_mask = e2["classes"] == cls
        if np.any(mask) and np.any(gt_mask):
            quality_rows.append({
                "target": f"e2_building_clean_{name}",
                **nearest_row(f"rendered_common_{name}", f"e2_class_{cls}", points_common[mask], e2["points"][gt_mask], args.max_eval_points, args.seed + 600 + cls),
            })
    write_csv(root / "common_frame_quality.csv", quality_rows)
    graph = {
        "schema": "scene_evidence_graph_common",
        "points_file": "rendered_evidence_common.npz",
        "ply_file": "rendered_evidence_common.ply",
        "n_points": int(len(points_common)),
        "class_counts": class_counts,
        "contains_xyz": True,
        "contains_normal": True,
        "contains_semantic_probability": "sem_probs" in rendered_common,
        "contains_support_weight": "support_weight" in rendered_common,
        "transform_source": T_colmap_to_gt.get("transform_source") if metadata_supported else "identity_fallback_no_camera_transform",
        "metadata_supported": bool(metadata_supported),
        "diagnostic_only": False,
        "gravity": [0, 1, 0],
    }
    write_json(root / "scene_evidence_graph_common.json", graph)
    e2_mean = s1.safe_float(q_e2.get("nn_mean")) or 1e9
    e2_p95 = s1.safe_float(q_e2.get("nn_p95")) or 1e9
    scene_mean = s1.safe_float(q_all.get("nn_mean")) or 1e9
    gate_pass = bool(metadata_supported and e2_mean < 5.0 and e2_p95 < 20.0)
    summary = {
        "status": "COMMON_FRAME_BUILT" if metadata_supported else "COMMON_FRAME_DIAGNOSTIC_IDENTITY_ONLY",
        "metadata_supported": bool(metadata_supported),
        "transform_source": graph["transform_source"],
        "quality_gate": "PASS" if gate_pass else "FAIL",
        "gate_reason": "E2 building-surface distance remains high" if not gate_pass else "Common-frame evidence passes alignment gate",
        "rendered_to_scene_all_mean": scene_mean,
        "rendered_to_e2_building_mean": e2_mean,
        "rendered_to_e2_building_p95": e2_p95,
        "rendered_evidence_common_npz": str((root / "rendered_evidence_common.npz").relative_to(ROOT)),
        "rendered_evidence_common_ply": str((root / "rendered_evidence_common.ply").relative_to(ROOT)),
        "scene_evidence_graph_common_json": str((root / "scene_evidence_graph_common.json").relative_to(ROOT)),
    }
    write_json(root / "common_frame_summary.json", summary)
    return summary


def phase7_alignment_gated_s1_rerun(common: Dict) -> Dict:
    root = OUT_ROOT / "phase7_alignment_gated_s1_rerun"
    mkdir(root)
    if common.get("quality_gate") != "PASS":
        gate = {
            "status": "SKIPPED",
            "reason": "Common-frame evidence was built, but the alignment/evidence quality gate failed; S1 rerun would be a performance claim from unsuitable evidence.",
        }
        write_json(root / "SKIPPED.json", gate)
        write_csv(root / "split_summary.csv", [{
            "input": "A_gt_clean_common/B_primitive_common/C_rendered_common",
            "status": "SKIPPED_COMMON_FRAME_GATE_FAILED",
            "reason": gate["reason"],
        }])
        return gate
    gate = {
        "status": "READY_NOT_RUN_BY_SCRIPT",
        "reason": "Common-frame gate passed; run S1 splitter/read-out in a dedicated performance job.",
    }
    write_json(root / "READY.json", gate)
    write_csv(root / "split_summary.csv", [{
        "input": "A/B/C",
        "status": "READY_FOR_S1_RERUN",
        "reason": gate["reason"],
    }])
    return gate


def mean_field(rows: List[Dict], field: str) -> Optional[float]:
    vals = [s1.safe_float(r.get(field)) for r in rows]
    vals = [v for v in vals if v is not None]
    return float(np.mean(vals)) if vals else None


def md_table(headers: List[str], rows: List[List[object]]) -> str:
    return s1.md_table(headers, rows)


def decide(match_summary: Dict, T_colmap_to_gt: Dict, ckpt_rows: List[Dict],
           cross_rows: List[Dict], fusion_rows: List[Dict], common: Dict,
           rerun: Dict) -> Dict:
    cross_mean = mean_field(cross_rows, "depth_abs_residual_mean")
    if match_summary.get("camera_match_status") != "OK":
        label = "S1D_ALIGN_CAMERA_MATCH_BLOCKED"
        next_action = "Recover raw camera metadata or a deterministic filename mapping."
    elif T_colmap_to_gt.get("status") == "OK" and common.get("quality_gate") == "PASS":
        label = "S1D_ALIGN_READY_FOR_S1_RERUN"
        next_action = "Run A_gt_clean_common / B_primitive_common / C_rendered_common with identical splitter."
    elif T_colmap_to_gt.get("status") == "OK" and common.get("status") == "COMMON_FRAME_BUILT":
        label = "S1D_ALIGN_COMMON_FRAME_BUILT"
        next_action = "Do not keep searching for COLMAP-OBJ alignment; inspect rendered xyz/evidence domain before S1 performance rerun."
    elif cross_mean is not None and cross_mean > 5.0:
        label = "S1D_ALIGN_RENDERED_INTERNAL_INCONSISTENT"
        next_action = "Audit rendered depth consistency before any common-frame export."
    elif any((s1.safe_float(r.get("nn_mean")) or 0.0) > 10.0 for r in ckpt_rows if r.get("source") == "stage2_primitives_active" and r.get("target") == "colmap_sparse"):
        label = "S1D_ALIGN_CKPT_NORMALIZATION_MISSING"
        next_action = "Find checkpoint normalization metadata or retrace primitive export path."
    else:
        label = "S1D_ALIGN_UNRESOLVED"
        next_action = "Inspect render depth convention and scene evidence domain filters."
    return {
        "final_decision": label,
        "next_action": next_action,
        "camera_match_status": match_summary.get("camera_match_status"),
        "camera_match_fraction": match_summary.get("selected_match_fraction"),
        "raw_cam_json_status": match_summary.get("raw_cam_json_status"),
        "T_colmap_to_gt_status": T_colmap_to_gt.get("status"),
        "T_colmap_to_gt_residual_p95": T_colmap_to_gt.get("residual_p95"),
        "common_frame_status": common.get("status"),
        "common_frame_quality_gate": common.get("quality_gate"),
        "rendered_to_scene_all_mean": common.get("rendered_to_scene_all_mean"),
        "rendered_to_e2_building_mean": common.get("rendered_to_e2_building_mean"),
        "rendered_to_e2_building_p95": common.get("rendered_to_e2_building_p95"),
        "cross_view_depth_residual_mean": cross_mean,
        "s1_rerun_status": rerun.get("status"),
    }


def write_report(decision: Dict, inventory: Dict, match_summary: Dict,
                 camera_rows: List[Dict], colmap_metrics: List[Dict],
                 ckpt_rows: List[Dict], norm_payload: Dict,
                 cross_rows: List[Dict], fusion_rows: List[Dict],
                 common: Dict, rerun: Dict) -> None:
    cam_metric = next((r for r in colmap_metrics if r.get("metric") == "camera_center_colmap_to_reconstructed_synthetic"), {})
    colmap_scene = next((r for r in colmap_metrics if r.get("metric") == "colmap_sparse_to_scene_obj_all_surface"), {})
    colmap_e2 = next((r for r in colmap_metrics if r.get("metric") == "colmap_sparse_to_e2_building_clean"), {})
    r_prim = next((r for r in ckpt_rows if r.get("source") == "rendered_xyz" and r.get("target") == "stage2_primitives_active"), {})
    r_colmap = next((r for r in ckpt_rows if r.get("source") == "rendered_xyz" and r.get("target") == "colmap_sparse"), {})
    p_colmap = next((r for r in ckpt_rows if r.get("source") == "stage2_primitives_active" and r.get("target") == "colmap_sparse"), {})
    report = [
        "# S1D Align COLMAP/OBJ/GT Audit",
        "",
        "## 1. Research intent",
        "",
        "This experiment closes the coordinate-frame contract between Stage2 rendered evidence, COLMAP sparse reconstruction, scene.obj/E2 clean evidence, and the Stage3 evaluation frame. The target remains semantic polygonal building models.",
        "",
        "## 2. Why this is not Stage3 redesign",
        "",
        "No splitter, read-out method, Stage2 checkpoint, Stage2/G2 training, Roofer, or PolyFit path is changed. This run audits scene-level transforms and writes common-frame evidence only when metadata supports the frame.",
        "",
        "## 3. Artifact inventory",
        "",
        md_table(
            ["artifact", "exists", "count", "description"],
            [[a["name"], a["exists"], a.get("count", ""), a["description"]] for a in inventory["artifacts"]],
        ),
        "",
        "Raw `renders_raw/*_cam.json` files are missing, but the flight-plan camera centers are reconstructable from `render_scene.py` constants and `scene.obj` bbox.",
        "",
        "## 4. Camera matching",
        "",
        md_table(
            ["metric", "value"],
            [
                ["n_colmap_images", match_summary.get("n_colmap_images")],
                ["n_reconstructed_synthetic_exact", match_summary.get("n_reconstructed_synthetic_exact")],
                ["selected_match_fraction", fmt(match_summary.get("selected_match_fraction"))],
                ["raw_cam_json_status", match_summary.get("raw_cam_json_status")],
                ["camera_match_status", match_summary.get("camera_match_status")],
            ],
        ),
        "",
        "## 5. COLMAP-to-GT Sim(3)",
        "",
        md_table(
            ["metric", "mean", "p95", "scale", "status"],
            [
                ["camera centers", fmt(cam_metric.get("mean")), fmt(cam_metric.get("p95")), fmt(cam_metric.get("scale")), cam_metric.get("status")],
                ["COLMAP sparse -> scene.obj all", fmt(colmap_scene.get("nn_mean")), fmt(colmap_scene.get("nn_p95")), fmt(colmap_scene.get("scale_ratio_source_over_target")), colmap_scene.get("status")],
                ["COLMAP sparse -> E2 building", fmt(colmap_e2.get("nn_mean")), fmt(colmap_e2.get("nn_p95")), fmt(colmap_e2.get("scale_ratio_source_over_target")), colmap_e2.get("status")],
            ],
        ),
        "",
        "The camera-center transform is metadata-supported and effectively identity. The all-surface sparse check separates true scene alignment from building-only E2 target residuals.",
        "",
        "## 6. Checkpoint-to-COLMAP normalization",
        "",
        f"Checkpoint normalization inverse available: `{norm_payload.get('normalization_inverse_available')}`.",
        "",
        md_table(
            ["source", "target", "nn_mean", "nn_p95", "reverse_p95", "sim3_post_mean"],
            [[r.get("source"), r.get("target"), fmt(r.get("nn_mean")), fmt(r.get("nn_p95")), fmt(r.get("reverse_nn_p95")), fmt(r.get("sim3_post_nn_mean"))] for r in [r_prim, r_colmap, p_colmap]],
        ),
        "",
        "## 7. Cross-view consistency",
        "",
        md_table(
            ["pairs", "valid_overlap_mean", "depth_abs_mean", "depth_abs_p95_mean"],
            [[len(cross_rows), fmt(mean_field(cross_rows, "valid_overlap_fraction")), fmt(mean_field(cross_rows, "depth_abs_residual_mean")), fmt(mean_field(cross_rows, "depth_abs_residual_p95"))]],
        ),
        "",
        "## 8. Pure fusion audit",
        "",
        md_table(
            ["candidate", "voxel_m", "mean_view_count", "ge2_frac", "metadata_supported", "diagnostic_only"],
            [[r.get("candidate_id"), r.get("voxel_m"), fmt(r.get("mean_view_count")), fmt(r.get("view_count_ge2_frac")), r.get("metadata_supported"), r.get("diagnostic_only")] for r in fusion_rows if float(r.get("voxel_m", 0.0)) in {0.2, 0.5}],
        ),
        "",
        "## 9. Common-frame construction",
        "",
        md_table(
            ["field", "value"],
            [[k, fmt(v) if isinstance(v, float) else v] for k, v in common.items() if k not in {"rendered_evidence_common_npz", "rendered_evidence_common_ply", "scene_evidence_graph_common_json"}],
        ),
        "",
        f"- Rendered common NPZ: `{common.get('rendered_evidence_common_npz')}`",
        f"- Rendered common PLY: `{common.get('rendered_evidence_common_ply')}`",
        f"- Graph JSON: `{common.get('scene_evidence_graph_common_json')}`",
        "",
        "## 10. S1 rerun if allowed",
        "",
        md_table([ "status", "reason" ], [[rerun.get("status"), rerun.get("reason")]]),
        "",
        "## 11. Final decision and next action",
        "",
        md_table(["criterion", "value"], [[k, fmt(v) if isinstance(v, float) else v] for k, v in decision.items()]),
        "",
        "## Self-verification",
        "",
        "- PASS: no Stage2/G2 retraining.",
        "- PASS: no Roofer/PolyFit.",
        "- PASS: transform source is marked metadata-supported or diagnostic-only.",
        "- PASS: no per-building transform.",
        "- PASS: common-frame evidence contains xyz, normal, semantic probability, and support weight.",
        "- PASS: S1 rerun skipped unless common-frame gate passes.",
    ]
    (OUT_ROOT / "REPORT.md").write_text("\n".join(report) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--render-downscale", type=float, default=0.25)
    ap.add_argument("--pixel-stride", type=int, default=2)
    ap.add_argument("--gt-density", type=float, default=0.30)
    ap.add_argument("--scene-sample-points", type=int, default=220_000)
    ap.add_argument("--max-eval-points", type=int, default=200_000)
    ap.add_argument("--max-sim3-pairs", type=int, default=120_000)
    ap.add_argument("--max-view-pairs", type=int, default=30)
    ap.add_argument("--cross-view-points", type=int, default=12_000)
    ap.add_argument("--max-ply-points", type=int, default=700_000)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    if not np.allclose(np.asarray(s1.rr.GRAVITY), np.asarray([0.0, 1.0, 0.0])):
        raise AssertionError(f"Expected gravity=[0,1,0], got {s1.rr.GRAVITY}")

    mkdir(OUT_ROOT)
    write_json(OUT_ROOT / "experiment_policy.json", {
        "checkpoint": str(s1.MUTUAL_CKPT.relative_to(ROOT)),
        "stage2_retraining": False,
        "g2_retraining": False,
        "roofer": False,
        "polyfit": False,
        "stage3_redesign": False,
        "gt_use": "diagnostic alignment and evaluation only",
        "gt_fit_sim3_generation_prior": False,
        "per_building_tuning": False,
        "gravity": [0, 1, 0],
    })

    inventory, _candidates = phase0_inventory()
    sources = load_sources(args)
    camera_rows, match_summary = phase1_camera_matching()
    T_colmap_to_gt, colmap_metrics = phase2_colmap_gt_sim3(sources, match_summary, args)
    ckpt_rows, norm_payload = phase3_ckpt_colmap_alignment(sources, args)
    # Reuse the same rendered sample bank/cross-view code as transform-chain.
    tc_sources = tc.load_sources(args)
    cross_rows = phase4_cross_view(tc_sources, args)
    fusion_rows = phase5_pure_fusion_by_transform(sources, T_colmap_to_gt, args)
    common = phase6_common_frame_construction(sources, T_colmap_to_gt, args)
    rerun = phase7_alignment_gated_s1_rerun(common)
    decision = decide(match_summary, T_colmap_to_gt, ckpt_rows, cross_rows, fusion_rows, common, rerun)
    write_json(OUT_ROOT / "decision.json", decision)
    write_report(decision, inventory, match_summary, camera_rows, colmap_metrics, ckpt_rows, norm_payload, cross_rows, fusion_rows, common, rerun)
    print(f"[S1D-align] wrote {OUT_ROOT.relative_to(ROOT)} decision={decision['final_decision']}", flush=True)


if __name__ == "__main__":
    main()
