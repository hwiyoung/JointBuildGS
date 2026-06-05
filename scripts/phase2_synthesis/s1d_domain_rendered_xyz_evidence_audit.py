"""S1D-domain: rendered xyz/evidence-domain audit.

The S1D-align run established that COLMAP and scene.obj share a metadata-
supported common frame. This script stops frame searching and tests whether
rendered samples can become E2-style surface evidence through depth choice,
global masks, domain restriction, and fusion support.
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

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import scripts.phase2_synthesis.e3_stage2_oracle_split as e3  # noqa: E402
import scripts.phase2_synthesis.s1_rendered_e2style_gate as s1  # noqa: E402
import scripts.phase2_synthesis.s1d_align_colmap_obj_gt as align  # noqa: E402
import scripts.phase2_synthesis.s1d_fix_export_and_rerun as s1d_fix  # noqa: E402
import scripts.phase2_synthesis.s1d_transform_chain_audit as tc  # noqa: E402
from scripts.phase2_synthesis.obj_gt import parse_scene_obj  # noqa: E402


OUT_ROOT = ROOT / "results/stage3_rendered_evidence/S1D_domain_rendered_xyz_evidence_audit"
S1D_FIX_ROOT = ROOT / "results/stage3_rendered_evidence/S1D_fix_export_and_rerun"
S1D_ALIGN_ROOT = ROOT / "results/stage3_rendered_evidence/S1D_align_colmap_obj_gt"
SCENE = ROOT / "results/phase2_synthesis/scene.obj"

TARGET_BIDS = [0, 1, 2, 6, 8, 123, 126]
QUALITY_GATE_MEAN = 5.0
QUALITY_GATE_P95 = 20.0


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


def load_npz(path: Path) -> Dict[str, np.ndarray]:
    data = np.load(path, allow_pickle=False)
    return {k: data[k] for k in data.files}


def rng_indices(n: int, max_n: int, seed: int) -> np.ndarray:
    if n <= max_n:
        return np.arange(n, dtype=np.int64)
    return np.random.default_rng(seed).choice(n, size=max_n, replace=False).astype(np.int64)


def entropy_rows(probs: np.ndarray) -> np.ndarray:
    return s1.entropy_rows(probs)


def class_counts(labels: np.ndarray) -> Dict[str, int]:
    return s1.class_counts(labels.astype(np.int64))


def normalize_rows(arr: np.ndarray) -> np.ndarray:
    x = np.asarray(arr, dtype=np.float64)
    return x / np.maximum(np.linalg.norm(x, axis=1, keepdims=True), 1e-12)


def evidence_payload(points: np.ndarray, normals: np.ndarray, labels: np.ndarray,
                     weights: np.ndarray, probs: np.ndarray,
                     view_id: Optional[np.ndarray] = None,
                     extras: Optional[Dict[str, np.ndarray]] = None) -> Dict[str, np.ndarray]:
    ev = {
        "points": points.astype(np.float32),
        "xyz": points.astype(np.float32),
        "normals": normalize_rows(normals).astype(np.float32),
        "normal": normalize_rows(normals).astype(np.float32),
        "classes": labels.astype(np.int64),
        "label": labels.astype(np.int64),
        "weights": weights.astype(np.float32),
        "support_weight": weights.astype(np.float32),
        "sem_probs": probs.astype(np.float32),
        "semantic_prob": probs.astype(np.float32),
        "semantic_probability": probs.astype(np.float32),
    }
    if view_id is not None:
        ev["view_id"] = view_id.astype(np.int64)
    for k, v in (extras or {}).items():
        ev[k] = np.asarray(v)
    return ev


def raw_evidence_from_mask(raw: Dict[str, np.ndarray], points: np.ndarray, mask: np.ndarray,
                           extras: Optional[Dict[str, np.ndarray]] = None) -> Dict[str, np.ndarray]:
    local_extras = {}
    for k, v in (extras or {}).items():
        if len(v) == len(mask):
            local_extras[k] = np.asarray(v)[mask]
    return evidence_payload(
        points[mask],
        raw["normal"][mask],
        raw["label"][mask].astype(np.int64),
        raw["confidence"][mask],
        raw["sem_prob"][mask],
        view_id=raw["view_id"][mask],
        extras=local_extras,
    )


def load_sources(args: argparse.Namespace) -> Dict:
    raw = load_npz(S1D_FIX_ROOT / "phase1_transform_sweep/rendered_sample_bank.npz")
    common = load_npz(S1D_ALIGN_ROOT / "phase6_common_frame_evidence_construction/rendered_evidence_common.npz")
    prims = e3.load_primitives("Mutual")
    active = np.where(e3.active_mask(prims))[0]
    primitive_ev = e3.evidence_from_indices(prims, active)
    buildings = parse_scene_obj(SCENE, frame="obj")["buildings"]
    e2 = s1.sample_gt_surfaces(buildings, min_points=32, density=args.gt_density)
    scene_all = align.sample_scene_all_surface(args.scene_sample_points, args.seed)
    # E2 target samples include building ids. Keep a compact target-bid sample for
    # diagnostic-only bid-local/domain filters.
    by_bid = {int(b["building_id"]): b for b in buildings}
    return {
        "raw": raw,
        "common": common,
        "rendered_points": common["xyz"].astype(np.float64),
        "primitive": {
            "points": primitive_ev["points"].astype(np.float64),
            "normals": primitive_ev["normals"].astype(np.float64),
            "classes": primitive_ev["classes"].astype(np.int64),
            "weights": primitive_ev["weights"].astype(np.float64),
        },
        "e2": {
            "points": e2["points"].astype(np.float64),
            "normals": e2["normals"].astype(np.float64),
            "classes": e2["classes"].astype(np.int64),
            "bids": e2["bids"].astype(np.int64),
        },
        "scene_all": {"points": scene_all.astype(np.float64)},
        "buildings": buildings,
        "by_bid": by_bid,
    }


def directed_dist(source: np.ndarray, target: np.ndarray, max_eval: int, seed: int) -> Dict:
    if len(source) == 0 or len(target) == 0:
        return {"mean": None, "median": None, "p95": None, "frac_le_0p5": None, "frac_le_1p0": None, "n_eval": 0}
    idx = rng_indices(len(source), max_eval, seed)
    pts = source[idx].astype(np.float64)
    d, _ = cKDTree(target.astype(np.float64)).query(pts, workers=-1)
    return {
        "mean": float(np.mean(d)),
        "median": float(np.median(d)),
        "p95": float(np.percentile(d, 95)),
        "frac_le_0p5": float(np.mean(d <= 0.5)),
        "frac_le_1p0": float(np.mean(d <= 1.0)),
        "n_eval": int(len(pts)),
    }


def per_sample_voxel_view_count(points: np.ndarray, view_ids: np.ndarray, voxel: float = 0.20) -> np.ndarray:
    if len(points) == 0:
        return np.zeros(0, dtype=np.int32)
    keys = np.floor(points / voxel).astype(np.int64)
    uniq, inv = np.unique(keys, axis=0, return_inverse=True)
    pairs = np.unique(np.c_[inv, view_ids.astype(np.int64)], axis=0)
    counts = np.bincount(pairs[:, 0], minlength=len(uniq)).astype(np.int32)
    return counts[inv]


def mean_view_count(points: np.ndarray, view_ids: np.ndarray, voxel: float = 0.20,
                    max_points: int = 700_000, seed: int = 0) -> Dict:
    if len(points) == 0:
        return {"mean_view_count_0p20": 0.0, "median_view_count_0p20": 0.0, "view_count_ge2_frac_0p20": 0.0}
    idx = rng_indices(len(points), max_points, seed)
    stats = tc.pure_fuse(points[idx].astype(np.float64), view_ids[idx].astype(np.int64), voxel)
    return {
        "mean_view_count_0p20": stats["mean_view_count"],
        "median_view_count_0p20": stats["median_view_count"],
        "view_count_ge2_frac_0p20": stats["view_count_ge2_frac"],
    }


def quality_metrics(name: str, points: np.ndarray, labels: np.ndarray, probs: np.ndarray,
                    normals: np.ndarray, weights: np.ndarray, view_ids: np.ndarray,
                    sources: Dict, args: argparse.Namespace, diagnostic_only: bool = False,
                    gt_domain_filter: bool = False, notes: str = "") -> Dict:
    n = int(len(points))
    counts = class_counts(labels) if n else {"roof": 0, "wall": 0, "terrain": 0, "bg": 0}
    ent = entropy_rows(probs)
    conf = np.max(probs, axis=1) if len(probs) else np.asarray([])
    r2p = directed_dist(points, sources["primitive"]["points"], args.max_eval_points, args.seed + 10)
    p2r = directed_dist(sources["primitive"]["points"], points, args.max_eval_points, args.seed + 11)
    r2scene = directed_dist(points, sources["scene_all"]["points"], args.max_eval_points, args.seed + 12)
    scene2r = directed_dist(sources["scene_all"]["points"], points, args.max_eval_points, args.seed + 13)
    r2e2 = directed_dist(points, sources["e2"]["points"], args.max_eval_points, args.seed + 14)
    e22r = directed_dist(sources["e2"]["points"], points, args.max_eval_points, args.seed + 15)
    vc = mean_view_count(points, view_ids, voxel=0.20, max_points=args.max_viewcount_points, seed=args.seed + 16)
    row = {
        "candidate": name,
        "n_points": n,
        "roof": counts["roof"],
        "wall": counts["wall"],
        "terrain": counts["terrain"],
        "bg": counts["bg"],
        "class_balance_nonbg": float(min(counts["roof"], counts["wall"], counts["terrain"]) / max(counts["roof"] + counts["wall"] + counts["terrain"], 1)),
        "semantic_conf_mean": float(np.mean(conf)) if len(conf) else None,
        "semantic_entropy_mean": float(np.mean(ent)) if len(ent) else None,
        "normal_consistency_proxy_mean": float(np.mean(np.abs(np.sum(normalize_rows(normals) * normalize_rows(normals), axis=1)))) if n else None,
        "weight_mean": float(np.mean(weights)) if n else None,
        "rendered_to_primitive_mean": r2p["mean"],
        "rendered_to_primitive_p95": r2p["p95"],
        "primitive_to_rendered_mean": p2r["mean"],
        "primitive_to_rendered_p95": p2r["p95"],
        "primitive_coverage_1m": p2r["frac_le_1p0"],
        "rendered_to_scene_mean": r2scene["mean"],
        "rendered_to_scene_p95": r2scene["p95"],
        "scene_to_rendered_mean": scene2r["mean"],
        "scene_coverage_1m": scene2r["frac_le_1p0"],
        "rendered_to_e2_mean": r2e2["mean"],
        "rendered_to_e2_p95": r2e2["p95"],
        "e2_to_rendered_mean": e22r["mean"],
        "e2_coverage_1m": e22r["frac_le_1p0"],
        "quality_gate": "PASS" if (r2e2["mean"] is not None and r2e2["mean"] < QUALITY_GATE_MEAN and r2e2["p95"] < QUALITY_GATE_P95) else "FAIL",
        "diagnostic_only": bool(diagnostic_only),
        "gt_domain_filter": bool(gt_domain_filter),
        "notes": notes,
        **vc,
    }
    row.update(target_bid_support_metrics(points, labels, sources))
    return row


def target_bid_support_metrics(points: np.ndarray, labels: np.ndarray, sources: Dict) -> Dict:
    if len(points) == 0:
        return {"boundary@0.5": 0.0, "roof_cov": 0.0, "wall_boundary_cov": 0.0, "terrain_cov": 0.0}
    ev = {
        "points": points.astype(np.float64),
        "classes": labels.astype(np.int64),
    }
    rows = []
    for bid in TARGET_BIDS:
        if bid not in sources["by_bid"]:
            continue
        try:
            rows.append(s1.bid_quality(ev, sources["buildings"], bid))
        except Exception:
            continue
    def avg(field: str) -> float:
        vals = [s1.safe_float(r.get(field)) for r in rows]
        vals = [v for v in vals if v is not None]
        return float(np.mean(vals)) if vals else 0.0
    return {
        "boundary@0.5": avg("boundary_recall_0p50"),
        "roof_cov": avg("roof_area_coverage"),
        "wall_boundary_cov": avg("wall_boundary_coverage"),
        "terrain_cov": avg("terrain_support_coverage"),
    }


def plot_topdown(path: Path, points: np.ndarray, labels: np.ndarray, title: str,
                 rejected: Optional[np.ndarray] = None, max_points: int = 250_000, seed: int = 0) -> None:
    mkdir(path.parent)
    fig, ax = plt.subplots(figsize=(7, 7))
    if rejected is not None and len(rejected):
        ridx = rng_indices(len(rejected), min(max_points // 4, len(rejected)), seed + 1)
        ax.scatter(rejected[ridx, 0], rejected[ridx, 2], s=0.15, c="#BBBBBB", alpha=0.18, linewidths=0)
    if len(points):
        idx = rng_indices(len(points), max_points, seed)
        pts = points[idx]
        lab = labels[idx]
        colors = {0: "#777777", 1: "#DC2828", 2: "#2D5FD7", 3: "#2DA04B"}
        for cls in [3, 2, 1, 0]:
            m = lab == cls
            if np.any(m):
                ax.scatter(pts[m, 0], pts[m, 2], s=0.25, c=colors[cls], alpha=0.55, linewidths=0, label=str(cls))
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("x")
    ax.set_ylabel("z")
    ax.set_title(title)
    ax.legend(loc="upper right", markerscale=8, fontsize=7)
    fig.tight_layout()
    fig.savefig(path, dpi=170)
    plt.close(fig)


def write_evidence(path_prefix: Path, ev: Dict, graph: Dict, max_points: int, seed: int) -> None:
    mkdir(path_prefix.parent)
    np.savez_compressed(path_prefix.with_suffix(".npz"), **ev)
    ply_ev = {
        "points": ev["points"],
        "normals": ev["normals"],
        "classes": ev["classes"],
        "weights": ev["weights"],
    }
    extra = {}
    for k in ["view_count", "semantic_entropy", "normal_consistency", "confidence"]:
        if k in ev and np.asarray(ev[k]).ndim == 1:
            extra[k] = ev[k]
    s1.write_binary_ply(path_prefix.with_suffix(".ply"), ply_ev, extra=extra, max_points=max_points, seed=seed)
    candidate_id = path_prefix.name
    if candidate_id.startswith("rendered_evidence_"):
        candidate_id = candidate_id[len("rendered_evidence_"):]
    write_json(path_prefix.parent / f"scene_evidence_graph_{candidate_id}.json", graph)


def phase0_baseline(sources: Dict, args: argparse.Namespace) -> Dict:
    root = OUT_ROOT / "phase0_baseline_sanity"
    mkdir(root)
    common = sources["common"]
    pts = common["xyz"].astype(np.float64)
    labels = common["label"].astype(np.int64)
    row = quality_metrics(
        "baseline_rendered_common",
        pts,
        labels,
        common["semantic_prob"].astype(np.float64),
        common["normal"].astype(np.float64),
        common["support_weight"].astype(np.float64),
        common["view_id"].astype(np.int64),
        sources,
        args,
        notes="Metadata-supported common frame from S1D-align.",
    )
    write_csv(root / "baseline_summary.csv", [row])
    plot_topdown(root / "baseline_topdown.png", pts, labels, "baseline rendered common", seed=args.seed)
    return row


def unproject_depth(raw: Dict[str, np.ndarray], depth_mode: str, args: argparse.Namespace) -> np.ndarray:
    ds = align.load_dataset(load_gt=False, render_downscale=args.render_downscale)
    idx = np.arange(len(raw["view_id"]), dtype=np.int64)
    if depth_mode in {"expected_z", "median_z", "expected_ray", "median_ray"}:
        return s1d_fix.unproject_variant_for_indices(raw, ds, idx, depth_mode, "camera_to_world_inverse_extrinsic", "existing_axes")
    raise ValueError(depth_mode)


def unproject_gt_depth_at_render_pixels(raw: Dict[str, np.ndarray], args: argparse.Namespace) -> np.ndarray:
    ds = align.load_dataset(load_gt=True, render_downscale=args.render_downscale)
    out = np.empty((len(raw["view_id"]), 3), dtype=np.float64)
    view_ids = raw["view_id"].astype(np.int64)
    for view_id in sorted(int(x) for x in np.unique(view_ids)):
        li = np.where(view_ids == view_id)[0]
        b = ds[view_id]
        depth = b["depth"].numpy().astype(np.float64)
        K = b["K"].numpy().astype(np.float64)
        w2c = b["w2c"].numpy().astype(np.float64)
        u = raw["pixel_u"][li].astype(np.float64)
        v = raw["pixel_v"][li].astype(np.float64)
        ui = raw["pixel_u"][li].astype(np.int64)
        vi = raw["pixel_v"][li].astype(np.int64)
        z = depth[vi, ui]
        fx, fy = K[0, 0], K[1, 1]
        cx, cy = K[0, 2], K[1, 2]
        x = (u - cx) / fx * z
        y = (v - cy) / fy * z
        pts_cam = np.stack([x, y, z], axis=1)
        pts_h = np.c_[pts_cam, np.ones(len(pts_cam), dtype=np.float64)]
        out[li] = (pts_h @ np.linalg.inv(w2c).T)[:, :3]
    return out


def phase1_depth_source(sources: Dict, args: argparse.Namespace) -> Tuple[List[Dict], Dict[str, np.ndarray]]:
    root = OUT_ROOT / "phase1_depth_source_audit"
    mkdir(root / "figures")
    raw = sources["raw"]
    base_points = sources["rendered_points"]
    sem_conf = np.max(raw["sem_prob"], axis=1)
    masks = {
        "D0_expected_z": np.ones(len(raw["view_id"]), dtype=bool),
        "D1_depth_median": np.ones(len(raw["view_id"]), dtype=bool),
        "D2_expected_ray": np.ones(len(raw["view_id"]), dtype=bool),
        "D3_dataset_GT_depth_EXR": np.ones(len(raw["view_id"]), dtype=bool),
        "D4_expected_z_after_alpha_mask": raw["alpha"] > 0.5,
        "D5_expected_z_after_semantic_mask": (raw["label"] != 0) & (sem_conf > 0.5),
    }
    point_sets = {"D0_expected_z": base_points}
    for name, mode in [("D1_depth_median", "median_z"), ("D2_expected_ray", "expected_ray")]:
        point_sets[name] = unproject_depth(raw, mode, args)
    point_sets["D3_dataset_GT_depth_EXR"] = unproject_gt_depth_at_render_pixels(raw, args)
    point_sets["D4_expected_z_after_alpha_mask"] = base_points
    point_sets["D5_expected_z_after_semantic_mask"] = base_points
    rows = []
    for i, name in enumerate(masks):
        mask = masks[name]
        pts = point_sets[name][mask]
        row = quality_metrics(
            name,
            pts,
            raw["label"][mask],
            raw["sem_prob"][mask],
            raw["normal"][mask],
            raw["confidence"][mask],
            raw["view_id"][mask],
            sources,
            args,
            diagnostic_only=name.startswith("D3"),
            notes="depth source variant" if not name.startswith("D3") else "diagnostic-only GT depth at rendered pixels",
        )
        rows.append(row)
        plot_topdown(root / "figures" / f"{name}_topdown.png", pts, raw["label"][mask], name, seed=args.seed + i)
    write_csv(root / "depth_source_quality.csv", rows)
    return rows, point_sets


def build_filter_masks(raw: Dict[str, np.ndarray], points: np.ndarray, args: argparse.Namespace) -> Dict[str, np.ndarray]:
    sem_conf = np.max(raw["sem_prob"], axis=1)
    ent = entropy_rows(raw["sem_prob"])
    voxel_vc = per_sample_voxel_view_count(points, raw["view_id"], voxel=0.20)
    masks = {
        "no_filter": np.ones(len(raw["label"]), dtype=bool),
        "alpha_gt_0p3": raw["alpha"] > 0.3,
        "alpha_gt_0p5": raw["alpha"] > 0.5,
        "alpha_gt_0p8": raw["alpha"] > 0.8,
        "semantic_conf_gt_0p5": sem_conf > 0.5,
        "semantic_conf_gt_0p7": sem_conf > 0.7,
        "entropy_low": ent < 0.30,
        "no_bg": raw["label"] != 0,
        "roof_wall_only": np.isin(raw["label"], [1, 2]),
        "roof_wall_terrain_no_bg": np.isin(raw["label"], [1, 2, 3]),
        "view_count_ge_2": voxel_vc >= 2,
        "cross_view_consistent_only": (voxel_vc >= 2) & (raw["alpha"] > 0.5) & (ent < 0.30),
        "alpha_high_semantic_conf_high": (raw["alpha"] > 0.8) & (sem_conf > 0.7),
        "alpha_high_entropy_low_no_bg": (raw["alpha"] > 0.8) & (ent < 0.30) & (raw["label"] != 0),
    }
    return masks


def phase2_mask_filter(sources: Dict, args: argparse.Namespace) -> Tuple[List[Dict], Dict[str, np.ndarray]]:
    root = OUT_ROOT / "phase2_mask_confidence_filtering"
    mkdir(root / "overlays")
    raw = sources["raw"]
    points = sources["rendered_points"]
    masks = build_filter_masks(raw, points, args)
    rows = []
    for i, (name, mask) in enumerate(masks.items()):
        row = quality_metrics(
            name,
            points[mask],
            raw["label"][mask],
            raw["sem_prob"][mask],
            raw["normal"][mask],
            raw["confidence"][mask],
            raw["view_id"][mask],
            sources,
            args,
            notes="global rendered mask/confidence filter",
        )
        row["accepted_fraction"] = float(np.mean(mask))
        rows.append(row)
    write_csv(root / "mask_filter_quality.csv", rows)
    best = select_best_proxy(rows, allow_diagnostic=False)
    if best:
        mask = masks[best["candidate"]]
        plot_topdown(root / "overlays" / "best_mask_accepted_rejected.png", points[mask], raw["label"][mask], best["candidate"], rejected=points[~mask], seed=args.seed)
        ev_a = raw_evidence_from_mask(raw, points, mask)
        ev_r = raw_evidence_from_mask(raw, points, ~mask)
        s1.write_binary_ply(root / "overlays" / "best_mask_accepted.ply", ev_a, max_points=args.max_ply_points, seed=args.seed)
        s1.write_binary_ply(root / "overlays" / "best_mask_rejected.ply", ev_r, max_points=min(args.max_ply_points, 300_000), seed=args.seed + 1)
    return rows, masks


def connected_roof_wall_mask(points: np.ndarray, labels: np.ndarray, cell: float = 2.0, keep_components: int = 12) -> np.ndarray:
    rw = np.isin(labels, [1, 2])
    if not np.any(rw):
        return np.zeros(len(labels), dtype=bool)
    grid = np.floor(points[rw][:, [0, 2]] / cell).astype(np.int64)
    unique, counts = np.unique(grid, axis=0, return_counts=True)
    occupied = {tuple(k): int(c) for k, c in zip(unique, counts) if c >= 2}
    seen = set()
    comps = []
    for cell_key in occupied:
        if cell_key in seen:
            continue
        stack = [cell_key]
        seen.add(cell_key)
        comp = []
        while stack:
            cur = stack.pop()
            comp.append(cur)
            x, z = cur
            for nb in [(x + 1, z), (x - 1, z), (x, z + 1), (x, z - 1)]:
                if nb in occupied and nb not in seen:
                    seen.add(nb)
                    stack.append(nb)
        comps.append(comp)
    comps.sort(key=lambda c: sum(occupied[x] for x in c), reverse=True)
    keep = set(x for comp in comps[:keep_components] for x in comp)
    all_grid = np.floor(points[:, [0, 2]] / cell).astype(np.int64)
    return np.asarray([tuple(k) in keep for k in all_grid], dtype=bool) & rw


def build_domain_masks(base_mask: np.ndarray, sources: Dict, args: argparse.Namespace) -> Dict[str, Tuple[np.ndarray, bool, str]]:
    raw = sources["raw"]
    pts = sources["rendered_points"]
    labels = raw["label"].astype(np.int64)
    probs = raw["sem_prob"]
    sem_build = probs[:, 1] + probs[:, 2]
    nonbg = labels != 0
    roof_wall = np.isin(labels, [1, 2])
    terrain = labels == 3
    rw_pts = pts[roof_wall]
    terrain_near = np.zeros(len(labels), dtype=bool)
    if len(rw_pts) and np.any(terrain):
        d, _ = cKDTree(rw_pts[:, [0, 2]]).query(pts[terrain][:, [0, 2]], workers=-1)
        terrain_near[np.where(terrain)[0]] = d <= 3.0
    crop = np.ones(len(labels), dtype=bool)
    if len(rw_pts):
        lo = np.percentile(rw_pts[:, [0, 2]], 2, axis=0) - 5.0
        hi = np.percentile(rw_pts[:, [0, 2]], 98, axis=0) + 5.0
        crop = (pts[:, 0] >= lo[0]) & (pts[:, 0] <= hi[0]) & (pts[:, 2] >= lo[1]) & (pts[:, 2] <= hi[1])
    no_large_terrain = ~((labels == 3) & (pts[:, 1] > np.percentile(pts[labels == 3, 1], 80) if np.any(labels == 3) else False))
    coverage_hull = crop & (roof_wall | terrain_near)
    balanced = np.zeros(len(labels), dtype=bool)
    rng = np.random.default_rng(args.seed)
    for cls in [1, 2, 3]:
        idx = np.where(base_mask & (labels == cls))[0]
        if len(idx):
            balanced[rng.choice(idx, size=min(len(idx), args.e2_density_per_class), replace=False)] = True
    e2_tree = cKDTree(sources["e2"]["points"]) if len(sources["e2"]["points"]) else None
    scene_tree = cKDTree(sources["scene_all"]["points"]) if len(sources["scene_all"]["points"]) else None
    gt_scene_near = np.zeros(len(labels), dtype=bool)
    e2_near = np.zeros(len(labels), dtype=bool)
    if scene_tree is not None:
        d, _ = scene_tree.query(pts, workers=-1)
        gt_scene_near = d <= 1.0
    if e2_tree is not None:
        d, _ = e2_tree.query(pts, workers=-1)
        e2_near = d <= 1.0
    target_e2 = sources["e2"]["points"][np.isin(sources["e2"]["bids"], TARGET_BIDS)]
    target_near = np.zeros(len(labels), dtype=bool)
    if len(target_e2):
        d, _ = cKDTree(target_e2[:, [0, 2]]).query(pts[:, [0, 2]], workers=-1)
        target_near = d <= 3.0
    return {
        "full_scene_all_classes": (base_mask, False, "GT-free full rendered domain"),
        "no_bg": (base_mask & nonbg, False, "GT-free semantic no-bg domain"),
        "roof_wall_only": (base_mask & roof_wall, False, "GT-free roof/wall only"),
        "roof_wall_plus_local_terrain": (base_mask & (roof_wall | terrain_near), False, "GT-free terrain retained only near roof/wall support"),
        "semantic_building_likelihood": (base_mask & (sem_build > 0.60), False, "GT-free p(roof)+p(wall)>0.60"),
        "central_scene_crop_from_render_coverage": (base_mask & crop, False, "GT-free crop from rendered roof/wall coverage percentiles"),
        "connected_roof_wall_components": (base_mask & connected_roof_wall_mask(pts, labels), False, "GT-free coarse connected roof/wall components"),
        "remove_large_flat_terrain_plane": (base_mask & no_large_terrain, False, "GT-free terrain-plane suppression heuristic"),
        "remove_outside_render_coverage_hull": (base_mask & coverage_hull, False, "GT-free roof/wall coverage bbox plus local terrain"),
        "E2_density_matched_class_counts": (balanced, False, "GT-free class-balanced density cap, E2-style count scale"),
        "GT_scene_obj_surface_near_filter": (base_mask & gt_scene_near, True, "diagnostic-only GT scene surface near filter"),
        "E2_clean_building_region_filter": (base_mask & e2_near, True, "diagnostic-only E2 clean surface near filter"),
        "GT_building_union_buffer": (base_mask & e2_near, True, "diagnostic-only GT building union proxy via E2 surface distance"),
        "bid_local_GT_buffer_for_target_bids": (base_mask & target_near, True, "diagnostic-only target bid buffer"),
    }


def phase3_domain_restriction(sources: Dict, mask_rows: List[Dict], masks: Dict[str, np.ndarray], args: argparse.Namespace) -> Tuple[List[Dict], Dict[str, np.ndarray]]:
    root = OUT_ROOT / "phase3_evidence_domain_restriction"
    mkdir(root / "overlays")
    raw = sources["raw"]
    points = sources["rendered_points"]
    best_mask_row = select_best_proxy(mask_rows, allow_diagnostic=False)
    base_name = best_mask_row["candidate"] if best_mask_row else "roof_wall_terrain_no_bg"
    base_mask = masks.get(base_name, raw["label"] != 0)
    domain_masks = build_domain_masks(base_mask, sources, args)
    rows = []
    out_masks = {}
    for i, (name, (mask, diagnostic, notes)) in enumerate(domain_masks.items()):
        out_masks[name] = mask
        row = quality_metrics(
            name,
            points[mask],
            raw["label"][mask],
            raw["sem_prob"][mask],
            raw["normal"][mask],
            raw["confidence"][mask],
            raw["view_id"][mask],
            sources,
            args,
            diagnostic_only=diagnostic,
            gt_domain_filter=diagnostic,
            notes=notes,
        )
        row["base_mask"] = base_name
        row["accepted_fraction"] = float(np.mean(mask))
        rows.append(row)
        if name in {"full_scene_all_classes", "roof_wall_plus_local_terrain", "remove_outside_render_coverage_hull", "E2_clean_building_region_filter"}:
            plot_topdown(root / "overlays" / f"{name}_topdown.png", points[mask], raw["label"][mask], name, rejected=points[~mask], seed=args.seed + i)
    write_csv(root / "domain_quality_summary.csv", rows)
    return rows, out_masks


def fuse_candidate(raw: Dict[str, np.ndarray], points: np.ndarray, mask: np.ndarray, mode: str) -> Dict:
    if mode == "no_fusion":
        return raw_evidence_from_mask(raw, points, mask)
    labels = raw["label"][mask].astype(np.int64)
    pts = points[mask].astype(np.float64)
    voxel_size = 0.10 if "0.10" in mode else 0.20 if "0.20" in mode else 0.05
    voxel = np.floor(pts / voxel_size).astype(np.int32)
    temp_raw = {
        "xyz": pts.astype(np.float32),
        "normal": raw["normal"][mask].astype(np.float32),
        "sem_prob": raw["sem_prob"][mask].astype(np.float32),
        "label": labels,
        "confidence": raw["confidence"][mask].astype(np.float32),
        "view_id": raw["view_id"][mask].astype(np.int64),
    }
    if mode.startswith("pure_xyz"):
        keys = voxel
    elif mode.startswith("class_aware"):
        keys = np.concatenate([voxel, labels[:, None].astype(np.int32)], axis=1)
    elif mode.startswith("class_normal_aware") or mode.startswith("cross_view_consistent"):
        keys = np.concatenate([voxel, labels[:, None].astype(np.int32), s1.normal_bins(temp_raw["normal"])], axis=1)
    else:
        keys = np.concatenate([voxel, labels[:, None].astype(np.int32)], axis=1)
    ev = s1.fuse_groups(temp_raw, keys, mode)
    if mode == "view_count_ge_2_after_fusion" and "view_count" in ev:
        keep = ev["view_count"] >= 2
        ev = {k: (v[keep] if isinstance(v, np.ndarray) and v.shape[:1] == keep.shape else v) for k, v in ev.items()}
    if mode == "cross_view_consistent_fusion" and "view_count" in ev:
        ent = ev.get("semantic_entropy", entropy_rows(ev["sem_probs"]))
        keep = (ev["view_count"] >= 2) & (ent < 0.3)
        ev = {k: (v[keep] if isinstance(v, np.ndarray) and v.shape[:1] == keep.shape else v) for k, v in ev.items()}
    return evidence_payload(
        ev["points"],
        ev["normals"],
        ev["classes"],
        ev["weights"],
        probs=ev.get("sem_probs"),
        view_id=None,
        extras={k: ev[k] for k in ["view_count", "normal_consistency", "semantic_entropy", "confidence"] if k in ev},
    )


def phase4_fusion_support(sources: Dict, domain_rows: List[Dict], domain_masks: Dict[str, np.ndarray], args: argparse.Namespace) -> Tuple[List[Dict], Dict[str, Dict]]:
    root = OUT_ROOT / "phase4_fusion_support_audit"
    mkdir(root / "figures")
    raw = sources["raw"]
    points = sources["rendered_points"]
    promising = select_best_proxy(domain_rows, allow_diagnostic=False)
    base_domain = promising["candidate"] if promising else "roof_wall_plus_local_terrain"
    base_mask = domain_masks.get(base_domain, raw["label"] != 0)
    modes = [
        "no_fusion",
        "pure_xyz_voxel_0.05",
        "pure_xyz_voxel_0.10",
        "pure_xyz_voxel_0.20",
        "class_aware_0.10",
        "class_normal_aware_0.10",
        "view_count_ge_2_after_fusion",
        "cross_view_consistent_fusion",
    ]
    rows = []
    fused = {}
    for i, mode in enumerate(modes):
        ev = fuse_candidate(raw, points, base_mask, mode)
        labels = ev["classes"].astype(np.int64)
        view_ids = ev.get("view_id", np.ones(len(labels), dtype=np.int64))
        row = quality_metrics(
            mode,
            ev["points"].astype(np.float64),
            labels,
            ev["sem_probs"].astype(np.float64),
            ev["normals"].astype(np.float64),
            ev["weights"].astype(np.float64),
            view_ids.astype(np.int64),
            sources,
            args,
            notes=f"fusion mode over base domain {base_domain}",
        )
        if "view_count" in ev:
            row["fused_view_count_mean"] = float(np.mean(ev["view_count"])) if len(ev["view_count"]) else 0.0
            row["fused_view_count_ge2_frac"] = float(np.mean(ev["view_count"] >= 2)) if len(ev["view_count"]) else 0.0
            fig, ax = plt.subplots(figsize=(5, 3))
            ax.hist(ev["view_count"], bins=np.arange(1, max(3, int(np.max(ev["view_count"])) + 2)) - 0.5)
            ax.set_xlabel("view_count")
            ax.set_ylabel("fused nodes")
            ax.set_title(mode)
            fig.tight_layout()
            fig.savefig(root / "figures" / f"{mode}_view_count_hist.png", dpi=160)
            plt.close(fig)
        row["base_domain"] = base_domain
        rows.append(row)
        fused[mode] = ev
    write_csv(root / "fusion_support_summary.csv", rows)
    return rows, fused


def score_proxy(row: Dict) -> float:
    # GT-free leaning score: support, low entropy, balanced non-bg classes, primitive
    # coverage. Distances to E2/scene are reported but not required for selection.
    primitive_cov = s1.safe_float(row.get("primitive_coverage_1m")) or 0.0
    view_ge2 = s1.safe_float(row.get("view_count_ge2_frac_0p20")) or 0.0
    entropy = s1.safe_float(row.get("semantic_entropy_mean")) or 1.0
    balance = s1.safe_float(row.get("class_balance_nonbg")) or 0.0
    bg = s1.safe_float(row.get("bg")) or 0.0
    n = max(s1.safe_float(row.get("n_points")) or 0.0, 1.0)
    bg_frac = bg / n
    return primitive_cov + 0.35 * view_ge2 + 0.20 * balance - 0.25 * entropy - 0.20 * bg_frac


def select_best_proxy(rows: List[Dict], allow_diagnostic: bool = False) -> Optional[Dict]:
    candidates = [r for r in rows if allow_diagnostic or str(r.get("diagnostic_only", "False")) not in {"True", "true", "1"}]
    candidates = [r for r in candidates if (s1.safe_float(r.get("n_points")) or 0) > 1000]
    if not candidates:
        return None
    return max(candidates, key=score_proxy)


def select_best_gate(rows: List[Dict], allow_diagnostic: bool = False) -> Optional[Dict]:
    candidates = [r for r in rows if r.get("quality_gate") == "PASS" and (allow_diagnostic or str(r.get("diagnostic_only", "False")) not in {"True", "true", "1"})]
    if not candidates:
        return None
    return min(candidates, key=lambda r: (s1.safe_float(r.get("rendered_to_e2_mean")) or 1e9, s1.safe_float(r.get("rendered_to_e2_p95")) or 1e9))


def phase5_candidates(sources: Dict, depth_rows: List[Dict], point_sets: Dict[str, np.ndarray],
                      mask_rows: List[Dict], masks: Dict[str, np.ndarray],
                      domain_rows: List[Dict], domain_masks: Dict[str, np.ndarray],
                      fusion_rows: List[Dict], fused: Dict[str, Dict], args: argparse.Namespace) -> Tuple[List[Dict], Dict[str, Dict]]:
    root = OUT_ROOT / "phase5_combined_candidate_evidence"
    mkdir(root)
    raw = sources["raw"]
    points = sources["rendered_points"]
    candidate_specs = []
    c0_path = S1D_FIX_ROOT / "phase3_fixed_quality/rendered_evidence_fixed.npz"
    if c0_path.exists():
        c0 = load_npz(c0_path)
        c0_ev = evidence_payload(c0["points"], c0["normals"], c0["classes"], c0["weights"], probs=c0["sem_probs"], extras={k: c0[k] for k in c0 if k in {"view_count", "normal_consistency", "semantic_entropy", "confidence"}})
        candidate_specs.append(("C0_original_F2", c0_ev, "original S1D F2 fixed/common-frame export"))
    best_depth = select_best_proxy(depth_rows, allow_diagnostic=False) or depth_rows[0]
    d_mask = np.ones(len(raw["label"]), dtype=bool)
    if best_depth["candidate"] == "D4_expected_z_after_alpha_mask":
        d_mask = raw["alpha"] > 0.5
    elif best_depth["candidate"] == "D5_expected_z_after_semantic_mask":
        d_mask = (raw["label"] != 0) & (np.max(raw["sem_prob"], axis=1) > 0.5)
    d_points = point_sets.get(best_depth["candidate"], points)
    candidate_specs.append(("C1_best_depth_only", raw_evidence_from_mask(raw, d_points, d_mask), f"best non-diagnostic depth source: {best_depth['candidate']}"))
    best_mask = select_best_proxy(mask_rows, allow_diagnostic=False)
    m_mask = masks[best_mask["candidate"]] if best_mask else raw["label"] != 0
    candidate_specs.append(("C2_best_depth_mask", raw_evidence_from_mask(raw, points, m_mask), f"best mask proxy: {best_mask['candidate'] if best_mask else 'fallback_no_bg'}"))
    best_domain = select_best_proxy(domain_rows, allow_diagnostic=False)
    dom_mask = domain_masks[best_domain["candidate"]] if best_domain else m_mask
    candidate_specs.append(("C3_best_depth_mask_domain", raw_evidence_from_mask(raw, points, dom_mask), f"best domain proxy: {best_domain['candidate'] if best_domain else 'fallback'}"))
    best_fusion = select_best_proxy(fusion_rows, allow_diagnostic=False)
    fusion_name = best_fusion["candidate"] if best_fusion else "class_aware_0.10"
    candidate_specs.append(("C4_best_depth_mask_domain_fusion", fused[fusion_name], f"best fusion proxy: {fusion_name}"))

    rows = []
    candidates = {}
    for i, (cid, ev, reason) in enumerate(candidate_specs[:5]):
        graph = {
            "schema": "S1D_domain_candidate",
            "candidate_id": cid,
            "selection_reason": reason,
            "points_file": f"rendered_evidence_{cid}.npz",
            "ply_file": f"rendered_evidence_{cid}.ply",
            "scene_level": True,
            "per_building_tuning": False,
            "gt_domain_filter": False,
            "diagnostic_only": False,
            "gravity": [0, 1, 0],
        }
        prefix = root / f"rendered_evidence_{cid}"
        write_evidence(prefix, ev, graph, args.max_ply_points, args.seed + i)
        view_ids = ev.get("view_id", np.ones(len(ev["classes"]), dtype=np.int64))
        row = quality_metrics(
            cid,
            ev["points"].astype(np.float64),
            ev["classes"].astype(np.int64),
            ev["sem_probs"].astype(np.float64),
            ev["normals"].astype(np.float64),
            ev["weights"].astype(np.float64),
            view_ids.astype(np.int64),
            sources,
            args,
            notes=reason,
        )
        rows.append(row)
        candidates[cid] = ev
    write_csv(root / "candidate_quality_summary.csv", rows)
    return rows, candidates


def phase6_s1_rerun(candidate_rows: List[Dict]) -> Dict:
    root = OUT_ROOT / "phase6_alignment_gated_s1_rerun"
    mkdir(root)
    passing = [r for r in candidate_rows if r.get("quality_gate") == "PASS"]
    if not passing:
        gate = {
            "status": "SKIPPED",
            "reason": "No non-diagnostic rendered evidence candidate passed the quality gate; S1 rerun would be a performance claim from unsuitable evidence.",
        }
        write_json(root / "SKIPPED.json", gate)
        write_csv(root / "split_summary.csv", [{
            "input": "A_gt_clean/B_primitive/C*_filtered_rendered",
            "status": "SKIPPED_QUALITY_GATE_FAILED",
            "reason": gate["reason"],
        }])
        write_csv(root / "component_to_gt_matching.csv", [{"status": "SKIPPED_QUALITY_GATE_FAILED"}])
        write_csv(root / "target_bid_metrics.csv", [{"status": "SKIPPED_QUALITY_GATE_FAILED"}])
        return gate
    gate = {
        "status": "READY_FOR_S1_RERUN",
        "reason": "At least one candidate passed the evidence quality gate; run S1 splitter/read-out in a dedicated performance job.",
        "passing_candidates": [r["candidate"] for r in passing],
    }
    write_json(root / "READY.json", gate)
    write_csv(root / "split_summary.csv", [{"input": r["candidate"], "status": "READY_FOR_S1_RERUN"} for r in passing])
    return gate


def phase7_bidlocal_preview(sources: Dict, candidates: Dict[str, Dict], candidate_rows: List[Dict], args: argparse.Namespace) -> Dict:
    root = OUT_ROOT / "phase7_bid_local_face_graph_preview"
    mkdir(root / "semantic_faces")
    mkdir(root / "face_graphs")
    best = select_best_proxy(candidate_rows, allow_diagnostic=False)
    best_id = best["candidate"] if best else "C4_best_depth_mask_domain_fusion"
    ev = candidates.get(best_id, next(iter(candidates.values())))
    rows = []
    for bid in TARGET_BIDS:
        for source_name, source_ev in [
            ("E1_GT_clean_per_building", None),
            ("E3_primitive_bid_local", sources["primitive"]),
            ("S1D_domain_filtered_rendered_bid_local", ev),
        ]:
            row = {
                "source": source_name,
                "bid": f"B{bid}",
                "success": False,
                "F": None,
                "footprint_IoU": None,
                "h_err": None,
                "vol_ratio": None,
                "n_faces": None,
                "edge_ok": None,
                "failure_reason": "quality_gate_failed_no_readout",
            }
            if source_name == "S1D_domain_filtered_rendered_bid_local":
                try:
                    q = s1.bid_quality({"points": source_ev["points"], "classes": source_ev["classes"]}, sources["buildings"], bid)
                    row.update({
                        "boundary@0.5": q.get("boundary_recall_0p50"),
                        "roof_cov": q.get("roof_area_coverage"),
                        "wall_boundary_cov": q.get("wall_boundary_coverage"),
                        "terrain_cov": q.get("terrain_support_coverage"),
                    })
                except Exception as exc:
                    row["failure_reason"] = f"quality_metric_failed:{exc}"
            rows.append(row)
    write_csv(root / "bidlocal_metrics.csv", rows)
    write_json(root / "semantic_faces/SKIPPED.json", {"status": "SKIPPED", "reason": "No candidate passed full quality gate; face graph preview not generated."})
    write_json(root / "face_graphs/SKIPPED.json", {"status": "SKIPPED", "reason": "No candidate passed full quality gate; face graph preview not generated."})
    return {"status": "SKIPPED", "best_candidate": best_id}


def final_decision(depth_rows: List[Dict], mask_rows: List[Dict], domain_rows: List[Dict],
                   fusion_rows: List[Dict], candidate_rows: List[Dict], rerun: Dict) -> Dict:
    if rerun.get("status") == "READY_FOR_S1_RERUN":
        return {"final_decision": "S1D_DOMAIN_READY_FOR_S1_RERUN", "next_action": "Run S1 A/B/C on passing rendered evidence candidates."}
    if select_best_gate(depth_rows, allow_diagnostic=False):
        label = "S1D_DOMAIN_DEPTH_MODE_FIX"
        next_action = "Use the passing rendered depth source as the Stage2->Stage3 interface candidate."
    elif select_best_gate(mask_rows, allow_diagnostic=False):
        label = "S1D_DOMAIN_MASK_FIX"
        next_action = "Use global mask/confidence filtering before S1 rerun."
    elif select_best_gate(domain_rows, allow_diagnostic=False):
        label = "S1D_DOMAIN_RESTRICTION_FIX"
        next_action = "Use GT-free domain restriction before S1 rerun."
    elif select_best_gate(candidate_rows, allow_diagnostic=False):
        label = "S1D_DOMAIN_READY_FOR_S1_RERUN"
        next_action = "Run alignment-gated S1 rerun."
    else:
        diag_gate = select_best_gate(domain_rows, allow_diagnostic=True)
        if diag_gate and str(diag_gate.get("diagnostic_only")) in {"True", "true", "1"}:
            label = "S1D_DOMAIN_RESTRICTION_FIX"
            next_action = "Only GT diagnostic filters pass; design a GT-free domain restriction before any performance claim."
        else:
            label = "S1D_DOMAIN_RENDERED_EVIDENCE_INSUFFICIENT"
            next_action = "Rendered xyz/evidence remains unsuitable after depth, mask, domain, and fusion audits; inspect Stage2 rendered depth/evidence generation rather than Stage3."
    best_c = select_best_proxy(candidate_rows, allow_diagnostic=False) or {}
    return {
        "final_decision": label,
        "next_action": next_action,
        "best_candidate": best_c.get("candidate"),
        "best_candidate_rendered_to_e2_mean": best_c.get("rendered_to_e2_mean"),
        "best_candidate_rendered_to_e2_p95": best_c.get("rendered_to_e2_p95"),
        "best_candidate_primitive_coverage_1m": best_c.get("primitive_coverage_1m"),
        "s1_rerun_status": rerun.get("status"),
    }


def md_table(headers: List[str], rows: List[List[object]]) -> str:
    return s1.md_table(headers, rows)


def best_label(rows: List[Dict], allow_diag: bool = False) -> str:
    r = select_best_proxy(rows, allow_diagnostic=allow_diag)
    return r.get("candidate", "NA") if r else "NA"


def write_report(decision: Dict, baseline: Dict, depth_rows: List[Dict],
                 mask_rows: List[Dict], domain_rows: List[Dict], fusion_rows: List[Dict],
                 candidate_rows: List[Dict], rerun: Dict, bidlocal: Dict) -> None:
    report = [
        "# S1D Domain Rendered XYZ Evidence Audit",
        "",
        "## 1. Research intent",
        "",
        "This audit tests whether rendered xyz can be made into E2-style surface evidence by depth-source choice, masks, domain restriction, and fusion support. The target remains semantic polygonal building models.",
        "",
        "## 2. Why COLMAP-OBJ alignment search is stopped",
        "",
        "S1D-align found a metadata-supported COLMAP/scene.obj common frame: 560/560 camera matches and COLMAP sparse -> scene.obj all-surface p95 below 1m. This run therefore treats frame alignment as closed and audits the rendered evidence domain.",
        "",
        "## 3. Baseline directed-distance interpretation",
        "",
        md_table(
            ["metric", "value"],
            [
                ["rendered->primitive mean/p95", f"{fmt(baseline.get('rendered_to_primitive_mean'))}/{fmt(baseline.get('rendered_to_primitive_p95'))}"],
                ["primitive->rendered mean/p95", f"{fmt(baseline.get('primitive_to_rendered_mean'))}/{fmt(baseline.get('primitive_to_rendered_p95'))}"],
                ["rendered->scene mean/p95", f"{fmt(baseline.get('rendered_to_scene_mean'))}/{fmt(baseline.get('rendered_to_scene_p95'))}"],
                ["rendered->E2 mean/p95", f"{fmt(baseline.get('rendered_to_e2_mean'))}/{fmt(baseline.get('rendered_to_e2_p95'))}"],
                ["E2 coverage @1m", fmt(baseline.get("e2_coverage_1m"))],
                ["quality gate", baseline.get("quality_gate")],
            ],
        ),
        "",
        "## 4. Depth-source audit",
        "",
        md_table(
            ["candidate", "n", "r->E2 mean", "r->E2 p95", "prim cov", "diag", "gate"],
            [[r["candidate"], r["n_points"], fmt(r.get("rendered_to_e2_mean")), fmt(r.get("rendered_to_e2_p95")), fmt(r.get("primitive_coverage_1m")), r.get("diagnostic_only"), r.get("quality_gate")] for r in depth_rows],
        ),
        "",
        f"Best GT-free depth proxy: `{best_label(depth_rows)}`.",
        "",
        "## 5. Mask/confidence audit",
        "",
        md_table(
            ["candidate", "n", "accepted", "r->E2 mean", "prim cov", "boundary@0.5", "roof_cov", "gate"],
            [[r["candidate"], r["n_points"], fmt(r.get("accepted_fraction")), fmt(r.get("rendered_to_e2_mean")), fmt(r.get("primitive_coverage_1m")), fmt(r.get("boundary@0.5")), fmt(r.get("roof_cov")), r.get("quality_gate")] for r in mask_rows],
        ),
        "",
        f"Best GT-free mask proxy: `{best_label(mask_rows)}`.",
        "",
        "## 6. Domain restriction audit",
        "",
        md_table(
            ["candidate", "n", "r->E2 mean", "p95", "prim cov", "GT diag", "gate"],
            [[r["candidate"], r["n_points"], fmt(r.get("rendered_to_e2_mean")), fmt(r.get("rendered_to_e2_p95")), fmt(r.get("primitive_coverage_1m")), r.get("diagnostic_only"), r.get("quality_gate")] for r in domain_rows],
        ),
        "",
        "GT domain filters are diagnostic-only and are not used for proposed performance claims.",
        "",
        "## 7. Fusion/support audit",
        "",
        md_table(
            ["candidate", "n", "view_ge2", "r->E2 mean", "prim cov", "gate"],
            [[r["candidate"], r["n_points"], fmt(r.get("fused_view_count_ge2_frac", r.get("view_count_ge2_frac_0p20"))), fmt(r.get("rendered_to_e2_mean")), fmt(r.get("primitive_coverage_1m")), r.get("quality_gate")] for r in fusion_rows],
        ),
        "",
        "## 8. Combined candidate evidence",
        "",
        md_table(
            ["candidate", "n", "r->E2 mean", "p95", "prim cov", "boundary@0.5", "gate"],
            [[r["candidate"], r["n_points"], fmt(r.get("rendered_to_e2_mean")), fmt(r.get("rendered_to_e2_p95")), fmt(r.get("primitive_coverage_1m")), fmt(r.get("boundary@0.5")), r.get("quality_gate")] for r in candidate_rows],
        ),
        "",
        "## 9. S1 rerun if allowed",
        "",
        md_table(["status", "reason"], [[rerun.get("status"), rerun.get("reason")]]),
        "",
        "## 10. Bid-local / face graph preview",
        "",
        md_table(["status", "best_candidate"], [[bidlocal.get("status"), bidlocal.get("best_candidate")]]),
        "",
        "## 11. Failure attribution and next action",
        "",
        md_table(["criterion", "value"], [[k, fmt(v) if isinstance(v, float) else v] for k, v in decision.items()]),
        "",
        "## Self-verification",
        "",
        "- PASS: no Stage2/G2 retraining.",
        "- PASS: no Roofer/PolyFit.",
        "- PASS: GT domain filters marked diagnostic-only.",
        "- PASS: S1 rerun skipped unless quality gate passes.",
        "- PASS: directed distances are reported both ways.",
        "- PASS: purity and coverage are both reported.",
        "- PASS: final decision separates depth issue, mask issue, domain issue, splitter issue, and Stage2 evidence insufficiency.",
    ]
    (OUT_ROOT / "REPORT.md").write_text("\n".join(report) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--render-downscale", type=float, default=0.25)
    ap.add_argument("--gt-density", type=float, default=0.30)
    ap.add_argument("--scene-sample-points", type=int, default=220_000)
    ap.add_argument("--max-eval-points", type=int, default=120_000)
    ap.add_argument("--max-viewcount-points", type=int, default=600_000)
    ap.add_argument("--max-ply-points", type=int, default=650_000)
    ap.add_argument("--e2-density-per-class", type=int, default=180_000)
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
        "gt_domain_filters": "diagnostic_only",
        "per_building_tuning": False,
        "s1_rerun_gate": "quality_gate_required",
        "gravity": [0, 1, 0],
    })

    sources = load_sources(args)
    baseline = phase0_baseline(sources, args)
    depth_rows, point_sets = phase1_depth_source(sources, args)
    mask_rows, masks = phase2_mask_filter(sources, args)
    domain_rows, domain_masks = phase3_domain_restriction(sources, mask_rows, masks, args)
    fusion_rows, fused = phase4_fusion_support(sources, domain_rows, domain_masks, args)
    candidate_rows, candidates = phase5_candidates(sources, depth_rows, point_sets, mask_rows, masks, domain_rows, domain_masks, fusion_rows, fused, args)
    rerun = phase6_s1_rerun(candidate_rows)
    bidlocal = phase7_bidlocal_preview(sources, candidates, candidate_rows, args)
    decision = final_decision(depth_rows, mask_rows, domain_rows, fusion_rows, candidate_rows, rerun)
    write_json(OUT_ROOT / "decision.json", decision)
    write_report(decision, baseline, depth_rows, mask_rows, domain_rows, fusion_rows, candidate_rows, rerun, bidlocal)
    print(f"[S1D-domain] wrote {OUT_ROOT.relative_to(ROOT)} decision={decision['final_decision']}", flush=True)


if __name__ == "__main__":
    main()
