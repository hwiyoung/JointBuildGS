"""A2: RANSAC plane proposal + Stage 3.

For each Phase 2 building:
  - Take Stage 2 primitives (within GT bbox)
  - Run multi-plane RANSAC: extract dominant planes iteratively
  - Each RANSAC plane carries inlier primitives' average semantic
  - Build "groups" dict (plane + prim_ids + class) compatible with process_building
  - Run Stage 3 with these groups (bypass cluster_primitives)
  - Run val3dity, compare to default + G2 results

Hypothesis: RANSAC gives sparse + accurate planes (similar to GT face centroids)
            → process_building reaches GT-input-like 96% ceiling
"""
import sys, json
from pathlib import Path
import numpy as np
import torch

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.stage2.model import quat_to_rotmat
from src.stage3.building_instance import process_building
from scripts.stage3_readout.obj_gt import parse_scene_obj
from scripts.stage3_readout.run_stage3 import _assign_primitives_to_buildings, _run_val3dity, _summarize_val3dity


def multi_plane_ransac(centers, normals, areas, labels,
                        n_planes_max=20,
                        min_inliers=30,
                        n_iters=200,
                        normal_cos_thresh=0.95,
                        plane_d_tol=0.20,
                        rng=None):
    """Iterative RANSAC to extract dominant planes.

    For each iteration:
      - Sample 3 primitives, fit plane (using ANY one's normal — they're 2DGS
        primitives, so each primitive *has* a plane).
      - Actually: each primitive IS a plane (n_i, d_i). So we don't need to
        fit, just pick a primitive's plane.
      - Score: count inliers (normal cos > thresh AND |n·c + d| < plane_d_tol).
      - Accept best in many trials.
      - Remove inliers, repeat until <min_inliers remaining or n_planes reached.

    Returns: list of group dicts {plane_normal, plane_d, prim_ids, class, area, center}
    """
    if rng is None:
        rng = np.random.default_rng(0)
    N = centers.shape[0]
    available = np.ones(N, dtype=bool)
    groups = []

    for _ in range(n_planes_max):
        avail_idx = np.where(available)[0]
        if avail_idx.size < min_inliers:
            break

        best_inliers = None
        best_score = 0
        # Random sample primitives, use their planes as candidates
        for _ in range(n_iters):
            i = rng.choice(avail_idx)
            n_i = normals[i] / (np.linalg.norm(normals[i]) + 1e-9)
            d_i = -(n_i @ centers[i])  # plane: n·x + d = 0
            # Inlier check on AVAILABLE primitives
            cos_v = np.abs(normals[avail_idx] @ n_i)
            offset = np.abs(centers[avail_idx] @ n_i + d_i)
            inlier_mask = (cos_v > normal_cos_thresh) & (offset < plane_d_tol)
            n_inliers = int(inlier_mask.sum())
            if n_inliers > best_score:
                best_score = n_inliers
                best_inliers_local = avail_idx[inlier_mask]
                best_n = n_i
        if best_score < min_inliers:
            break
        inliers = best_inliers_local

        # Refine plane: fit to inliers (weighted LS)
        ns = normals[inliers]
        # Flip to consistent direction
        flip = np.sign(ns @ best_n + 1e-12)
        ns = ns * flip[:, None]
        # weighted normal
        w = areas[inliers]
        n_fit = (ns * w[:, None]).sum(0)
        n_fit /= np.linalg.norm(n_fit) + 1e-9
        c_fit = (centers[inliers] * w[:, None]).sum(0) / w.sum()
        d_fit = -(n_fit @ c_fit)

        # Class: majority vote among inliers
        cls = int(np.bincount(labels[inliers]).argmax())
        if cls == 0:  # BG: drop
            available[inliers] = False
            continue

        groups.append({
            "plane_normal": n_fit,
            "plane_d": -d_fit,  # convention: n·x = d (matches groups_from_stage2_grouping)
            "class": cls,
            "prim_ids": inliers.tolist(),
            "center": c_fit,
            "area": float(w.sum()),
        })
        available[inliers] = False

    return groups


def main():
    ckpt = "results/phase2_ablation_citygml/mutual/ckpt/final.pt"
    out_dir = Path("results/phase2_ablation_citygml/_ransac_stage3_test")
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[A2] loading {ckpt}")
    sd = torch.load(ckpt, map_location="cpu")["state_dict"]
    means = sd["means"].float().numpy()
    quats = sd["quats"].float()
    log_scales = sd["log_scales"].float().numpy()
    sem_logits = sd["sem_logits"].float().numpy()
    opa = torch.sigmoid(sd["opacities_raw"]).float().numpy()
    R = quat_to_rotmat(torch.from_numpy(np.asarray(sd['quats'])).float())
    normals = R[..., :, 2].numpy()
    areas = np.exp(log_scales[:, 0]) * np.exp(log_scales[:, 1])
    sem_probs = np.exp(sem_logits - sem_logits.max(-1, keepdims=True))
    sem_probs /= sem_probs.sum(-1, keepdims=True)
    labels = sem_probs.argmax(-1)
    print(f"  N_primitives = {means.shape[0]:,}")

    print("[A2] parsing GT + assigning")
    gt = parse_scene_obj(_ROOT / "results/phase2_synthesis/scene.obj")
    asgn = _assign_primitives_to_buildings({"centers": means, "opacities": opa},
                                              gt, pad=2.0, opacity_thresh=0.05)

    test_bids = [1, 2, 6, 21, 22]
    results = {}

    for bid in test_bids:
        idxs = asgn.get(bid, np.array([], dtype=np.int64))
        keep = opa[idxs] >= 0.05
        idxs = idxs[keep]
        if idxs.size < 100:
            continue
        print(f"\n=== bid={bid}: {idxs.size} prims ===")

        b_centers = means[idxs]
        b_normals = normals[idxs]
        b_areas = areas[idxs]
        b_labels = labels[idxs]

        # Multi-plane RANSAC
        groups = multi_plane_ransac(b_centers, b_normals, b_areas, b_labels,
                                      n_planes_max=20, min_inliers=50,
                                      n_iters=200,
                                      normal_cos_thresh=0.95, plane_d_tol=0.20)
        print(f"  RANSAC: {len(groups)} planes")
        for gi, g in enumerate(groups[:8]):
            cls = {1: "Roof", 2: "Wall", 3: "Terr"}.get(g['class'], '?')
            print(f"    plane {gi:>2d}: {len(g['prim_ids']):>5d} inliers  cls={cls:>4s}  "
                  f"n=({g['plane_normal'][0]:+.2f},{g['plane_normal'][1]:+.2f},{g['plane_normal'][2]:+.2f})")

        # Build primitives dict with G2-like group_ids derived from RANSAC
        # Map prim_ids back to global indices for process_building call
        # process_building expects primitives['centers'] etc indexed by GLOBAL ids
        # and prim_ids provided as the building's global indices.
        # And use_stage2_groups requires 'group_ids' indexed globally.
        global_gid = np.full(means.shape[0], -1, dtype=np.int64)
        rep_normals_list = []
        for gi, g in enumerate(groups):
            local_pids = np.asarray(g['prim_ids'], dtype=np.int64)  # local (within bldg)
            global_pids = idxs[local_pids]
            global_gid[global_pids] = gi
            rep_normals_list.append(g['plane_normal'])
        rep_normals_arr = np.asarray(rep_normals_list) if rep_normals_list else np.zeros((0, 3))

        prims = {
            "centers": means,
            "normals": normals,
            "areas": areas,
            "semantic_probs": sem_probs,
            "group_ids": global_gid,
            "rep_normals": rep_normals_arr,
        }

        bdir = out_dir / f"bldg_{bid:03d}"
        bdir.mkdir(parents=True, exist_ok=True)
        try:
            result = process_building(
                building_id=bid, prim_ids=idxs, primitives=prims,
                out_dir=bdir, cos_thresh=0.85, hs_tol=0.10,
                method="convex", use_stage2_groups=True,
            )
        except Exception as e:
            import traceback
            traceback.print_exc()
            continue
        if result is None:
            print(f"  bid={bid}: result None"); continue

        cj_path = bdir / "building.city.json"
        v3d_summary = {"valid": False, "error_codes": []}
        if cj_path.exists():
            v3d = _run_val3dity(cj_path, bdir / "val3dity.json")
            v3d_summary = _summarize_val3dity(v3d)

        stat = {
            "n_ransac_planes": len(groups),
            "n_surfaces": result.get("n_surfaces"),
            "signed_volume": result.get("signed_volume"),
            "manifold": (result.get("n_edges_boundary", 1) == 0
                         and result.get("n_edges_nonmanifold", 1) == 0),
            "val3dity_valid": v3d_summary["valid"],
            "val3dity_errors": v3d_summary["error_codes"],
        }
        results[bid] = stat
        print(f"  bid={bid:>3d}: ransac_planes={stat['n_ransac_planes']}  "
              f"surf={stat['n_surfaces']:>2d}  vol={stat['signed_volume']:>8.2f}  "
              f"manifold={stat['manifold']}  val3dity_valid={stat['val3dity_valid']}")

    # Comparison vs G2 + default
    g2_path = _ROOT / "results/phase2_ablation_citygml/_g2_stage3_test/comparison.json"
    if g2_path.exists():
        prior = json.load(open(g2_path))
        print("\n" + "="*100)
        print(f"{'bid':>4} {'RANSAC v3d':>12} {'G2 v3d':>10} {'default v3d':>14} {'RANSAC vol':>12} {'G2 vol':>10} {'def vol':>10}")
        print("="*100)
        for bid in test_bids:
            r = results.get(bid, {})
            g2 = prior.get("G2", {}).get(str(bid), {})
            d  = prior.get("default", {}).get(str(bid), {})
            print(f"{bid:>4} {str(r.get('val3dity_valid','?')):>12} "
                  f"{str(g2.get('val3dity_valid','?')):>10} "
                  f"{str(d.get('val3dity_valid','?')):>14} "
                  f"{r.get('signed_volume', float('nan')):>12.2f} "
                  f"{g2.get('signed_volume', float('nan')):>10.2f} "
                  f"{d.get('signed_volume', float('nan')):>10.2f}")

    out_json = out_dir / "results.json"
    with open(out_json, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nwrote {out_json}")


if __name__ == "__main__":
    main()
