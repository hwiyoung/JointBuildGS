"""G2 sanity test: load a Stage 2 ckpt, call group_primitives_g2(), verify.

Checks (RESEARCH_CONTEXT §15.2 Step 2):
  1. groups/building in 5-15 range  (G1 baseline ~154/bldg)
  2. timing  <60s on 988K primitives
  3. per-building dump: group count, top groups by class, normal stats
  4. (optional) PLY export of group colours for visual verification

Usage:
    python scripts/stage3_readout/sanity_g2.py \
        --ckpt results/phase2_ablation_citygml/baseline/ckpt/final.pt \
        --scene results/phase2_synthesis/scene.obj \
        --out results/phase2_ablation_citygml/_sanity_g2 \
        [--bids 1,2,6,21,22] [--ply]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Dict, List

import numpy as np
import torch

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.stage2.model import GaussianModel2D, quat_to_rotmat  # noqa: E402
from src.stage2.grouping import group_primitives, group_primitives_g2  # noqa: E402
from scripts.stage3_readout.obj_gt import parse_scene_obj  # noqa: E402
from scripts.stage3_readout.run_stage3 import _assign_primitives_to_buildings  # noqa: E402


def load_ckpt(ckpt_path: Path) -> Dict[str, torch.Tensor]:
    sd = torch.load(ckpt_path, map_location="cpu")["state_dict"]
    means = sd["means"].float()
    quats = sd["quats"].float()
    log_scales = sd["log_scales"].float()
    opacities = torch.sigmoid(sd["opacities_raw"]).float()
    sem_logits = sd["sem_logits"].float()
    R = quat_to_rotmat(quats)
    normals = R[..., :, 2]
    scales = torch.exp(log_scales)
    return {
        "means": means, "normals": normals, "scales": scales,
        "opacities": opacities, "sem_logits": sem_logits,
    }


# 24-hue palette  (skip very dark / very pale; -1 group always grey)
_PALETTE = np.array([
    [228, 26, 28], [55, 126, 184], [77, 175, 74], [152, 78, 163],
    [255, 127, 0], [255, 255, 51], [166, 86, 40], [247, 129, 191],
    [102, 194, 165], [252, 141, 98], [141, 160, 203], [231, 138, 195],
    [166, 216, 84], [255, 217, 47], [229, 196, 148], [179, 179, 179],
    [27, 158, 119], [217, 95, 2], [117, 112, 179], [231, 41, 138],
    [102, 166, 30], [230, 171, 2], [166, 118, 29], [102, 102, 102],
], dtype=np.uint8)


def _color_for_group(gid: int) -> np.ndarray:
    if gid < 0:
        return np.array([80, 80, 80], dtype=np.uint8)
    return _PALETTE[gid % len(_PALETTE)]


def write_ply(path: Path, xyz: np.ndarray, rgb: np.ndarray) -> None:
    n = xyz.shape[0]
    with open(path, "w") as f:
        f.write("ply\nformat ascii 1.0\n")
        f.write(f"element vertex {n}\n")
        f.write("property float x\nproperty float y\nproperty float z\n")
        f.write("property uchar red\nproperty uchar green\nproperty uchar blue\n")
        f.write("end_header\n")
        for i in range(n):
            f.write(f"{xyz[i,0]:.4f} {xyz[i,1]:.4f} {xyz[i,2]:.4f} "
                    f"{int(rgb[i,0])} {int(rgb[i,1])} {int(rgb[i,2])}\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--scene", default="results/phase2_synthesis/scene.obj")
    ap.add_argument("--out", required=True)
    ap.add_argument("--bids", default="1,2,6,21,22",
                    help="comma-separated building ids for per-bldg dump")
    ap.add_argument("--voxel-size", type=float, default=2.0)
    ap.add_argument("--merge-n-cos", type=float, default=0.92)
    ap.add_argument("--merge-d-tol", type=float, default=0.5)
    ap.add_argument("--min-group-size", type=int, default=30)
    ap.add_argument("--opa-thresh", type=float, default=0.05)
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    ap.add_argument("--also-g1", action="store_true",
                    help="also run G1 for side-by-side comparison")
    ap.add_argument("--ply", action="store_true",
                    help="export per-bldg PLY (group_ids → colour)")
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[sanity_g2] ckpt={args.ckpt}")
    state = load_ckpt(Path(args.ckpt))
    means      = state["means"].to(args.device)
    normals    = state["normals"].to(args.device)
    scales     = state["scales"].to(args.device)
    opacities  = state["opacities"].to(args.device)
    sem_logits = state["sem_logits"].to(args.device)
    N = means.shape[0]
    print(f"[sanity_g2] N_primitives = {N:,}  device={args.device}")

    # ---- G2 timing ------------------------------------------------------
    if args.device == "cuda":
        torch.cuda.synchronize()
    t0 = time.perf_counter()
    gid_g2, rep_n_g2, rep_d_g2 = group_primitives_g2(
        centers=means, normals=normals, sem_logits=sem_logits, scales=scales,
        voxel_size=args.voxel_size,
        merge_n_cos=args.merge_n_cos,
        merge_d_tol=args.merge_d_tol,
        min_group_size=args.min_group_size,
        exclude_bg=True,
    )
    if args.device == "cuda":
        torch.cuda.synchronize()
    t_g2 = time.perf_counter() - t0
    G_g2 = int(rep_n_g2.shape[0])
    n_grouped_g2 = int((gid_g2 >= 0).sum().item())
    print(f"[sanity_g2] G2: {G_g2} groups, {n_grouped_g2:,}/{N:,} grouped, "
          f"{t_g2:.2f}s  (target <60s)")

    summary: Dict = {
        "ckpt": str(args.ckpt),
        "n_primitives": N,
        "g2": {
            "voxel_size": args.voxel_size,
            "merge_n_cos": args.merge_n_cos,
            "merge_d_tol": args.merge_d_tol,
            "min_group_size": args.min_group_size,
            "n_groups_total": G_g2,
            "n_grouped": n_grouped_g2,
            "timing_sec": round(t_g2, 3),
        },
    }

    # ---- Optional G1 reference -----------------------------------------
    if args.also_g1:
        if args.device == "cuda":
            torch.cuda.synchronize()
        t0 = time.perf_counter()
        gid_g1, rep_n_g1, rep_d_g1 = group_primitives(
            centers=means, normals=normals, sem_logits=sem_logits, scales=scales,
            voxel_size=0.05, n_directions=12, min_group_size=5, exclude_bg=True,
        )
        if args.device == "cuda":
            torch.cuda.synchronize()
        t_g1 = time.perf_counter() - t0
        G_g1 = int(rep_n_g1.shape[0])
        n_grouped_g1 = int((gid_g1 >= 0).sum().item())
        print(f"[sanity_g2] G1: {G_g1} groups, {n_grouped_g1:,}/{N:,} grouped, "
              f"{t_g1:.2f}s")
        summary["g1"] = {
            "n_groups_total": G_g1,
            "n_grouped": n_grouped_g1,
            "timing_sec": round(t_g1, 3),
        }

    # ---- Per-building dump ---------------------------------------------
    print(f"[sanity_g2] parsing {args.scene}")
    gt = parse_scene_obj(Path(args.scene))
    print(f"[sanity_g2] {len(gt['buildings'])} GT buildings")

    # Move primitives to cpu numpy for assignment
    prims_np = {
        "centers": means.cpu().numpy(),
        "opacities": opacities.cpu().numpy(),
    }
    assignment = _assign_primitives_to_buildings(
        prims_np, gt, pad=2.0, opacity_thresh=args.opa_thresh,
    )
    gid_g2_np = gid_g2.cpu().numpy()
    labels_np = sem_logits.argmax(dim=-1).cpu().numpy()

    bid_set = {int(x) for x in args.bids.split(",") if x.strip()}
    per_bldg: List[Dict] = []
    for b in gt["buildings"]:
        bid = b["building_id"]
        idxs = assignment.get(bid, np.array([], dtype=np.int64))
        if idxs.size == 0:
            per_bldg.append({"bid": bid, "n_prims": 0, "n_groups": 0})
            continue
        gids_b = gid_g2_np[idxs]
        unique_gids = np.unique(gids_b[gids_b >= 0])
        # per-group: size + dominant class
        groups_info = []
        for g in unique_gids:
            mg = gids_b == g
            cls_b = labels_np[idxs[mg]]
            cls_dom = int(np.bincount(cls_b).argmax())
            groups_info.append({
                "gid": int(g),
                "size": int(mg.sum()),
                "class": cls_dom,
            })
        groups_info.sort(key=lambda x: -x["size"])
        n_ungrouped = int((gids_b == -1).sum())
        per_bldg.append({
            "bid": bid,
            "n_prims": int(idxs.size),
            "n_groups": int(unique_gids.size),
            "n_ungrouped": n_ungrouped,
            "top_groups": groups_info[:8],
        })

        if bid in bid_set:
            print(f"  bid={bid:3d}  N_prims={idxs.size:6d}  "
                  f"N_groups={unique_gids.size:3d}  "
                  f"ungrouped={n_ungrouped:5d}  "
                  f"top sizes={[g['size'] for g in groups_info[:5]]}")

            if args.ply:
                xyz = prims_np["centers"][idxs]
                rgb = np.array([_color_for_group(int(g)) for g in gids_b],
                               dtype=np.uint8)
                ply_path = out_dir / f"bldg_{bid:03d}_g2.ply"
                write_ply(ply_path, xyz, rgb)
                print(f"    wrote {ply_path}")

    # Aggregate stats over non-empty buildings
    nonempty = [b for b in per_bldg if b["n_prims"] > 0]
    n_groups_arr = np.array([b["n_groups"] for b in nonempty])
    summary["per_bldg_stats"] = {
        "n_buildings": len(per_bldg),
        "n_buildings_nonempty": len(nonempty),
        "n_groups_per_bldg_mean":   float(n_groups_arr.mean()) if len(n_groups_arr) else 0.0,
        "n_groups_per_bldg_median": float(np.median(n_groups_arr)) if len(n_groups_arr) else 0.0,
        "n_groups_per_bldg_min":    int(n_groups_arr.min()) if len(n_groups_arr) else 0,
        "n_groups_per_bldg_max":    int(n_groups_arr.max()) if len(n_groups_arr) else 0,
        "in_5_15_range_count": int(((n_groups_arr >= 5) & (n_groups_arr <= 15)).sum())
            if len(n_groups_arr) else 0,
    }
    summary["per_bldg"] = per_bldg

    # Print summary verdict
    s = summary["per_bldg_stats"]
    print(f"\n[sanity_g2] groups/bldg: median={s['n_groups_per_bldg_median']:.1f}, "
          f"mean={s['n_groups_per_bldg_mean']:.1f}, "
          f"min={s['n_groups_per_bldg_min']}, max={s['n_groups_per_bldg_max']}")
    print(f"[sanity_g2] {s['in_5_15_range_count']}/{s['n_buildings_nonempty']} "
          f"buildings in target 5-15 range")
    verdict_groups  = "OK" if 5 <= s["n_groups_per_bldg_median"] <= 15 else "NG"
    verdict_timing  = "OK" if t_g2 < 60.0 else "NG"
    print(f"[sanity_g2] verdict — groups/bldg median: {verdict_groups},  "
          f"timing: {verdict_timing}")
    summary["verdict"] = {"groups": verdict_groups, "timing": verdict_timing}

    out_path = out_dir / "g2_sanity_summary.json"
    with open(out_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"[sanity_g2] wrote {out_path}")


if __name__ == "__main__":
    main()
