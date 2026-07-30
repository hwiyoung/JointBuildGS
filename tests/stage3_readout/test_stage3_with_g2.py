"""A1: G2 + Stage 3 — P1-2 missing step.

Apply G2 grouping to Phase 2 Mutual ckpt, pass G2 group_ids to process_building
(via use_stage2_groups=True), compare to default cluster_primitives baseline.
"""
import sys, json, subprocess
from pathlib import Path
import numpy as np
import torch

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.stage2.model import quat_to_rotmat
from src.stage2.grouping import group_primitives_g2
from src.stage3.building_instance import process_building
from scripts.stage3_readout.obj_gt import parse_scene_obj
from scripts.stage3_readout.run_stage3 import _assign_primitives_to_buildings, _run_val3dity, _summarize_val3dity


def main():
    ckpt = "results/phase2_ablation_citygml/mutual/ckpt/final.pt"
    out_dir = Path("results/phase2_ablation_citygml/_g2_stage3_test")
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[A1] loading {ckpt}")
    sd = torch.load(ckpt, map_location="cpu")["state_dict"]
    means = sd["means"].float()
    quats = sd["quats"].float()
    log_scales = sd["log_scales"].float()
    sem_logits = sd["sem_logits"].float()
    opa = torch.sigmoid(sd["opacities_raw"]).float()
    R = quat_to_rotmat(quats)
    normals = R[..., :, 2]
    scales = torch.exp(log_scales)
    print(f"  N_primitives = {means.shape[0]:,}")

    print("[A1] running G2 on full ckpt ...")
    gid, rep_n, rep_d = group_primitives_g2(
        centers=means, normals=normals, sem_logits=sem_logits, scales=scales,
        voxel_size=2.0, n_directions=12,
        merge_n_cos=0.92, merge_d_tol=0.5, min_group_size=30,
    )
    print(f"  G2: {int(rep_n.shape[0])} groups, {int((gid >= 0).sum())}/{means.shape[0]} grouped")

    # Build numpy primitive dict
    means_np = means.numpy()
    normals_np = normals.numpy()
    log_s = log_scales.numpy()
    areas_np = np.exp(log_s[:, 0]) * np.exp(log_s[:, 1])
    sem_probs_np = torch.softmax(sem_logits, dim=-1).numpy()

    prims_np = {
        "centers": means_np,
        "normals": normals_np,
        "areas": areas_np,
        "semantic_probs": sem_probs_np,
        "opacities": opa.numpy(),
        # G2 outputs:
        "group_ids": gid.numpy(),
        "rep_normals": rep_n.numpy(),
        "rep_d": rep_d.numpy(),
    }

    print("[A1] parsing GT + assigning to buildings (GT bbox for instance separation)")
    gt = parse_scene_obj(_ROOT / "results/phase2_synthesis/scene.obj")
    asgn = _assign_primitives_to_buildings(prims_np, gt, pad=2.0, opacity_thresh=0.05)

    test_bids = [1, 2, 6, 21, 22]
    results_g2 = {}
    results_default = {}

    for use_g2 in [True, False]:
        tag = "G2" if use_g2 else "default"
        print(f"\n=== {tag} (use_stage2_groups={use_g2}) ===")
        for bid in test_bids:
            idxs = asgn.get(bid, np.array([], dtype=np.int64))
            if idxs.size < 100:
                continue
            bdir = out_dir / tag / f"bldg_{bid:03d}"
            bdir.mkdir(parents=True, exist_ok=True)
            try:
                result = process_building(
                    building_id=bid, prim_ids=idxs, primitives=prims_np,
                    out_dir=bdir, cos_thresh=0.85, hs_tol=0.10,
                    method="convex", use_stage2_groups=use_g2,
                )
            except Exception as e:
                import traceback
                traceback.print_exc()
                continue
            if result is None:
                print(f"  bid={bid}: result None"); continue
            cj_path = bdir / "building.city.json"
            if cj_path.exists():
                v3d = _run_val3dity(cj_path, bdir / "val3dity.json")
                v3d_summary = _summarize_val3dity(v3d)
            else:
                v3d_summary = {"valid": False, "error_codes": []}

            stat = {
                "n_surfaces": result.get("n_surfaces"),
                "n_vertices": result.get("n_vertices"),
                "signed_volume": result.get("signed_volume"),
                "manifold": (result.get("n_edges_boundary", 1) == 0
                             and result.get("n_edges_nonmanifold", 1) == 0),
                "val3dity_valid": v3d_summary["valid"],
                "val3dity_errors": v3d_summary["error_codes"],
            }
            (results_g2 if use_g2 else results_default)[bid] = stat
            print(f"  bid={bid:>3d}: surf={stat['n_surfaces']:>2d}  "
                  f"vol={stat['signed_volume']:>8.2f}  manifold={stat['manifold']}  "
                  f"val3dity_valid={stat['val3dity_valid']}")

    # Summary
    print("\n" + "="*80)
    print(f"{'bid':>4} {'G2 vol':>10} {'def vol':>10} {'G2 manif':>9} {'def manif':>9} {'G2 v3d':>7} {'def v3d':>7}")
    print("="*80)
    for bid in test_bids:
        rg2 = results_g2.get(bid, {})
        rd = results_default.get(bid, {})
        print(f"{bid:>4} {rg2.get('signed_volume', float('nan')):>10.2f} "
              f"{rd.get('signed_volume', float('nan')):>10.2f} "
              f"{str(rg2.get('manifold', '?')):>9} "
              f"{str(rd.get('manifold', '?')):>9} "
              f"{str(rg2.get('val3dity_valid', '?')):>7} "
              f"{str(rd.get('val3dity_valid', '?')):>7}")

    out_json = out_dir / "comparison.json"
    with open(out_json, "w") as f:
        json.dump({"G2": results_g2, "default": results_default}, f, indent=2)
    print(f"\nwrote {out_json}")


if __name__ == "__main__":
    main()
