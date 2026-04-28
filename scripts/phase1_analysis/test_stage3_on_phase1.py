"""8.1 Run Stage 3 on a region of Phase 1 ckpt.

Pick a spatial region of MatrixCity Phase 1 primitives, run Stage 3 process_building,
compare output to local rendered depth (proxy for GT).

Goal: determine if Stage 3 algorithm produces sensible polytopes given
clean primitive input (Phase 1 σ_coplanar 7-9mm).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import torch
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D  # noqa
from matplotlib.collections import LineCollection

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.stage2.model import quat_to_rotmat
from src.stage3.building_instance import process_building


def main():
    ckpt = "results/phase1_ablation/run/ckpt/final.pt"  # Phase 1 Both
    out_dir = Path("results/phase1_analysis/stage3_test")
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[stage3-phase1] loading {ckpt}")
    sd = torch.load(ckpt, map_location="cpu")["state_dict"]
    means = sd["means"].float().numpy()
    quats = sd["quats"].float()
    log_scales = sd["log_scales"].float().numpy()
    sem_logits = sd["sem_logits"].float().numpy()
    opa = torch.sigmoid(sd["opacities_raw"]).float().numpy()
    R = quat_to_rotmat(quats)
    normals = R[..., :, 2].numpy()
    areas = np.exp(log_scales[:, 0]) * np.exp(log_scales[:, 1])
    sem_probs = np.exp(sem_logits - sem_logits.max(axis=1, keepdims=True))
    sem_probs /= sem_probs.sum(axis=1, keepdims=True)

    print(f"  N_primitives = {means.shape[0]:,}")
    print(f"  bbox: X=[{means[:,0].min():.1f},{means[:,0].max():.1f}]  "
          f"Y=[{means[:,1].min():.1f},{means[:,1].max():.1f}]  "
          f"Z=[{means[:,2].min():.1f},{means[:,2].max():.1f}]")

    # Filter by opacity first
    keep = opa > 0.3
    means = means[keep]; normals = normals[keep]; areas = areas[keep]
    sem_probs = sem_probs[keep]
    print(f"  after opa>0.3: {means.shape[0]:,}")

    # Pick a small region: a 30m × 30m × 50m bbox in the middle-ish
    # MatrixCity often has buildings between roads. Pick where Wall+Roof primitives cluster.
    labels = sem_probs.argmax(axis=1)
    wall_mask = labels == 2
    roof_mask = labels == 1
    bldg_mask = wall_mask | roof_mask
    bldg_centers = means[bldg_mask]
    if bldg_centers.shape[0] == 0:
        print("no bldg primitives")
        return
    print(f"  building primitives (Roof+Wall): {bldg_centers.shape[0]:,}")
    # Find dense region: histogram on xz
    H, edges_x, edges_z = np.histogram2d(bldg_centers[:, 0], bldg_centers[:, 2], bins=50)
    xi, zi = np.unravel_index(H.argmax(), H.shape)
    cx = (edges_x[xi] + edges_x[xi+1]) / 2
    cz = (edges_z[zi] + edges_z[zi+1]) / 2
    print(f"  densest XZ bin: ({cx:.1f}, {cz:.1f})")

    # Build region: 8m × 8m × 20m around that bin (single building scale)
    half_xz = 4.0
    half_y = 10.0
    in_region = (
        (means[:, 0] > cx - half_xz) & (means[:, 0] < cx + half_xz) &
        (means[:, 2] > cz - half_xz) & (means[:, 2] < cz + half_xz)
    )
    print(f"  primitives in region (no Y filter): {in_region.sum():,}")
    # Y filter: focus on building height range. Find Y of bldg primitives in region.
    if in_region.any():
        bldg_in = bldg_mask & in_region
        if bldg_in.sum() > 100:
            y_b = means[bldg_in, 1]
            cy = np.median(y_b)
            print(f"  bldg Y median in region: {cy:.1f}")
            in_region = in_region & (means[:, 1] > cy - half_y) & (means[:, 1] < cy + half_y)

    region_centers = means[in_region]
    region_normals = normals[in_region]
    region_areas = areas[in_region]
    region_labels = labels[in_region]
    region_sem = sem_probs[in_region]
    print(f"  primitives in region: {region_centers.shape[0]:,}")

    # Subsample for Stage 3 (cluster_primitives is O(N^2) memory)
    N_max = 15000
    if region_centers.shape[0] > N_max:
        rng = np.random.default_rng(42)
        sel = rng.choice(region_centers.shape[0], N_max, replace=False)
        region_centers = region_centers[sel]
        region_normals = region_normals[sel]
        region_areas = region_areas[sel]
        region_labels = region_labels[sel]
        region_sem = region_sem[sel]
        print(f"  subsampled to {region_centers.shape[0]:,}")
    print(f"  region label hist: BG={(region_labels==0).sum()} Roof={(region_labels==1).sum()} "
          f"Wall={(region_labels==2).sum()} Terrain={(region_labels==3).sum()}")

    if region_centers.shape[0] < 100:
        print("region too small")
        return

    # Run Stage 3
    print("\n[stage3-phase1] running process_building")
    prims = {
        "centers": region_centers,
        "normals": region_normals,
        "areas": region_areas,
        "semantic_probs": region_sem,
    }
    prim_ids = np.arange(region_centers.shape[0])
    process_out_dir = out_dir / "process_out"
    process_out_dir.mkdir(parents=True, exist_ok=True)
    try:
        result = process_building(building_id=999, prim_ids=prim_ids, primitives=prims,
                                    out_dir=process_out_dir, cos_thresh=0.85, hs_tol=0.10,
                                    method="convex", use_stage2_groups=False)
    except Exception as e:
        import traceback; traceback.print_exc()
        return

    if result is None:
        print("  process_building returned None")
        return
    cj = result.get("cityjson") if isinstance(result, dict) else None
    if cj is None and isinstance(result, dict):
        # try other keys
        for k, v in result.items():
            if isinstance(v, dict) and "vertices" in v:
                cj = v
                break

    print(f"  result keys: {list(result.keys()) if isinstance(result, dict) else type(result)}")
    if isinstance(result, dict):
        for k, v in result.items():
            try:
                if hasattr(v, '__len__'):
                    print(f"    {k}: len={len(v)}")
                else:
                    print(f"    {k}: {v}")
            except Exception:
                print(f"    {k}: {type(v)}")

    # Visualize: primitives + extracted polytope
    fig = plt.figure(figsize=(20, 8))
    fig.suptitle(f"Phase 1 Both ckpt — Stage 3 test on region (XZ {cx:.0f},{cz:.0f}; "
                 f"size 30×30×50m)  N_prims={region_centers.shape[0]}", fontsize=12)

    # 3D
    ax3d = fig.add_subplot(131, projection='3d')
    cls_color = {0: 'lightgrey', 1: 'red', 2: 'blue', 3: 'green'}
    cs = np.array([cls_color[c] for c in region_labels])
    ax3d.scatter(region_centers[:, 0], region_centers[:, 1], region_centers[:, 2],
                 c=cs, s=2, alpha=0.5)
    ax3d.set_xlabel('X'); ax3d.set_ylabel('Y(UP?)'); ax3d.set_zlabel('Z')
    ax3d.set_title("primitives by class (red=Roof, blue=Wall, green=Terrain)")

    # top-down XZ
    ax_top = fig.add_subplot(132)
    ax_top.scatter(region_centers[:, 0], region_centers[:, 2], c=cs, s=2, alpha=0.5)
    ax_top.set_aspect('equal'); ax_top.grid(alpha=0.3)
    ax_top.set_xlabel('X'); ax_top.set_ylabel('Z')
    ax_top.set_title("top-down XZ")

    # side XY
    ax_side = fig.add_subplot(133)
    ax_side.scatter(region_centers[:, 0], region_centers[:, 1], c=cs, s=2, alpha=0.5)
    ax_side.set_aspect('equal'); ax_side.grid(alpha=0.3)
    ax_side.set_xlabel('X'); ax_side.set_ylabel('Y')
    ax_side.set_title("side XY")

    fig.tight_layout()
    fig_path = out_dir / "stage3_phase1_input.png"
    fig.savefig(fig_path, dpi=120, bbox_inches='tight')
    plt.close(fig)
    print(f"\n[stage3-phase1] wrote {fig_path}")

    # Try to extract polytope vertices from result
    vertices = None
    faces = None
    if isinstance(result, dict):
        if "vertices" in result and "faces" in result:
            vertices = np.asarray(result["vertices"])
            faces = result["faces"]
        elif "polytope" in result and isinstance(result["polytope"], dict):
            vertices = np.asarray(result["polytope"].get("vertices", []))
            faces = result["polytope"].get("faces")

    if vertices is not None and faces is not None and len(vertices) > 0:
        fig2 = plt.figure(figsize=(15, 6))
        ax = fig2.add_subplot(121, projection='3d')
        ax.scatter(region_centers[:, 0], region_centers[:, 1], region_centers[:, 2],
                   c='lightgrey', s=1, alpha=0.3)
        # plot vertices
        ax.scatter(vertices[:, 0], vertices[:, 1], vertices[:, 2], c='red', s=20)
        # plot faces if list of vertex indices
        if isinstance(faces, list):
            for face in faces[:50]:
                if isinstance(face, (list, tuple)) and len(face) >= 3:
                    fv = vertices[list(face) + [face[0]]]
                    ax.plot(fv[:, 0], fv[:, 1], fv[:, 2], 'r-', linewidth=0.8)
        ax.set_title("polytope output (3D)")

        ax2 = fig2.add_subplot(122)
        ax2.scatter(region_centers[:, 0], region_centers[:, 2], c='lightgrey', s=1, alpha=0.3)
        ax2.scatter(vertices[:, 0], vertices[:, 2], c='red', s=20)
        ax2.set_aspect('equal'); ax2.grid(alpha=0.3)
        ax2.set_title("top-down")

        fig2.tight_layout()
        fig_out = out_dir / "stage3_phase1_polytope.png"
        fig2.savefig(fig_out, dpi=120, bbox_inches='tight')
        plt.close(fig2)
        print(f"[stage3-phase1] wrote {fig_out}")
    else:
        print("[stage3-phase1] no polytope vertices in result; cannot visualize output")


if __name__ == "__main__":
    main()
