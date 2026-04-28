"""Direct over-merge demonstration:
1. Tightly filter primitives (opa>0.5, no bbox pad)
2. Label each primitive by closest GT face (point-to-face distance < 0.5m)
3. Run cluster_primitives
4. Check if cluster boundaries align with GT face labels
   - If not aligned → over-merge confirmed
"""
import sys, json, numpy as np, torch
sys.path.insert(0, '/workspace/JointBuildGS' if 'workspace' in __file__ else '.')
from pathlib import Path
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.cm as cm

from src.stage2.model import quat_to_rotmat
from src.stage3.clustering import cluster_primitives
from scripts.phase2_synthesis.obj_gt import parse_scene_obj
from scripts.phase2_synthesis.run_stage3 import _assign_primitives_to_buildings


def closest_gt_face(prim_centers, prim_normals, faces, max_dist=1.0, max_normal_angle_deg=30):
    """For each primitive, find closest GT face by point-to-plane + normal cos.
    Returns: face_idx for each prim, -1 if no match within thresholds.
    """
    n_max_cos = np.cos(np.deg2rad(max_normal_angle_deg))
    N = prim_centers.shape[0]
    out = np.full(N, -1, dtype=np.int64)
    best_d = np.full(N, np.inf)
    for fi, f in enumerate(faces):
        fn = np.asarray(f['normal']); fn /= np.linalg.norm(fn)+1e-9
        fc = np.asarray(f['centroid'])
        d = np.abs((prim_centers - fc) @ fn)
        # also require normal alignment
        cos_n = np.abs(prim_normals @ fn)
        ok = (d < max_dist) & (cos_n > n_max_cos)
        # want closest match
        better = ok & (d < best_d)
        out[better] = fi
        best_d[better] = d[better]
    return out


def main():
    ckpt = "results/phase2_ablation_citygml/mutual/ckpt/final.pt"
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
    labels = sem_probs.argmax(axis=1)

    gt = parse_scene_obj(Path("results/phase2_synthesis/scene.obj"))
    b21 = next(b for b in gt['buildings'] if b['building_id']==21)

    # TIGHT filter: opa>0.5, primitives that match a GT face
    asgn = _assign_primitives_to_buildings({'centers': means, 'opacities': opa},
                                              gt, pad=0.5, opacity_thresh=0.5)
    idxs = asgn[21]
    print(f"bid=21 tightly filtered: {idxs.size} prims")

    # GT-face labels
    gt_face_labels = closest_gt_face(means[idxs], normals[idxs], b21['faces'],
                                       max_dist=0.5, max_normal_angle_deg=20)
    has_match = gt_face_labels >= 0
    print(f"  matched to GT face: {has_match.sum()} ({has_match.sum()/idxs.size*100:.0f}%)")
    print(f"  per-face count:")
    for fi in np.unique(gt_face_labels[has_match]):
        f = b21['faces'][fi]
        n = (gt_face_labels == fi).sum()
        print(f"    face {fi:>2d} ({f['material']:>7s}): {n:>4d} prims  area={f['area']:.1f}m^2")

    # IMPORTANT: cluster ALL bbox primitives (matching real Stage 3 pipeline),
    # NOT just GT-face-matched ones. Then check cross-tab.
    matched = idxs               # use all bbox prims
    matched_face = gt_face_labels  # already aligned with idxs

    # Run cluster_primitives on ALL primitives (real Stage 3 input)
    print(f"\nrunning cluster_primitives on ALL {matched.size} bbox prims")
    groups = cluster_primitives(means[matched], normals[matched], areas[matched],
                                  labels[matched], cos_thresh=0.85)
    print(f"  output: {len(groups)} clusters")

    # Now compute cross-tab: cluster_id vs GT face_id
    cluster_id = np.full(matched.size, -1, dtype=np.int64)
    for ci, g in enumerate(groups):
        for pid in g['prim_ids']:
            cluster_id[pid] = ci

    print(f"\n  cluster x GT face counts (incl. -1 = no GT face match):")
    print(f"  {'':>10s}", end='')
    unique_faces = sorted(set(matched_face[cluster_id >= 0].tolist()))
    for fi in unique_faces:
        if fi < 0:
            print(f"  {'no_gt':>9s}", end=''); continue
        f_mat = b21['faces'][fi]['material'][:4]
        print(f"  f{fi:>2d}({f_mat})", end='')
    print(f"   total  unmatched%")
    for ci, g in enumerate(groups):
        if not g['prim_ids']:
            continue
        cls_name = {1:'Roof', 2:'Wall', 3:'Terr'}.get(g['class'], '?')
        print(f"  cluster {ci:>2d} ({cls_name:>4s})", end='')
        for fi in unique_faces:
            mask = (cluster_id == ci) & (matched_face == fi)
            cnt = mask.sum()
            print(f"  {cnt:>8d}", end='')
        total = (cluster_id == ci).sum()
        unmatched = ((cluster_id == ci) & (matched_face < 0)).sum()
        print(f"   {total:>5d}   {unmatched/total*100:>5.0f}%")

    # Visualize: cluster vs GT face
    fig, axes = plt.subplots(2, 2, figsize=(18, 14))
    fig.suptitle(f'bid=21 tightly-filtered prims ({matched.size}): cluster_primitives vs GT face labels', fontsize=12)

    # color by cluster
    n_clusters = len(groups)
    cluster_colors = cm.tab20(np.arange(n_clusters) / max(1, n_clusters))
    cl_color = cluster_colors[cluster_id.clip(min=0)]
    cl_color[cluster_id < 0] = [0.5, 0.5, 0.5, 0.5]

    # color by GT face
    n_faces = len(unique_faces)
    face_to_idx = {fi: i for i, fi in enumerate(unique_faces)}
    face_colors = cm.viridis(np.arange(n_faces) / max(1, n_faces))
    f_color = np.array([face_colors[face_to_idx.get(fi, 0)] for fi in matched_face])
    f_color[matched_face < 0] = [0.5, 0.5, 0.5, 0.5]

    cs = means[matched]
    for row, (color_arr, title) in enumerate([
        (cl_color, f"colored by CLUSTER ID ({n_clusters} clusters from cluster_primitives)"),
        (f_color, f"colored by GT FACE ID ({n_faces} faces — ground truth surface labels)")
    ]):
        for col, (axes_pair, view) in enumerate([((0, 2), 'top XZ'), ((0, 1), 'front XY')]):
            ax = axes[row, col]
            a, b = axes_pair
            # GT mesh outline
            for f in b21['faces']:
                v = f['vertices']
                v_close = np.vstack([v, v[:1]])
                ax.plot(v_close[:, a], v_close[:, b], color='black', linewidth=0.8, alpha=0.6)
            ax.scatter(cs[:, a], cs[:, b], c=color_arr, s=8, alpha=0.8)
            ax.set_xlabel(['X', 'Y', 'Z'][a]); ax.set_ylabel(['X', 'Y', 'Z'][b])
            ax.set_title(f"{view} — {title}")
            ax.set_aspect('equal'); ax.grid(alpha=0.3)

    fig.tight_layout()
    out = Path("results/phase2_ablation_citygml/_cluster_inspect")
    out.mkdir(parents=True, exist_ok=True)
    fig.savefig(out / "bid21_cluster_vs_gtface.png", dpi=120, bbox_inches='tight')
    print(f"\nsaved {out}/bid21_cluster_vs_gtface.png")


if __name__ == "__main__":
    main()
