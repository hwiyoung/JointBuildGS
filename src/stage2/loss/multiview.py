"""L_mvc — self-supervised multi-view geometric consistency (Phase B / B1).

Reprojects the SOURCE view's rendered depth into a NEIGHBOR (reference) view and
penalizes (a) relative depth disagreement and (b) normal disagreement, with an
occlusion inlier filter. NO ground-truth labels: the only signal is that the same
surface, seen from two posed cameras, must reproject consistently. This is the
external multi-view anchor that L_coplanar (cp) structurally lacks — cp can only
pull a Gaussian toward a plane fit from its OWN (possibly mislocated) group, so a
roof facet floating ±1~2.5 m off its true layer has no in-group neighbor to correct
it (grouping deliberately withholds the merge across >merge_d_tol=0.5 m steps).

Ported from legacy/planarsplat_ref/loss_util.py:276 (ULSR-GS, Li et al. ISPRS 2025),
adapted to:
  - this repo's w2c (world->cam) convention (legacy took c2w and inverted internally);
  - shape-robust src/ref (cameras may differ in resolution; shapes inferred from depth);
  - a per-term dict return (total / depth / normal / n_inlier) like l_structure.

Gradient: with the reference view rendered under no_grad (mvc_ref_detach=True, the
default and the legacy behaviour), depth_ref/normal_ref are constants and the gradient
flows through depth_src (-> Gaussian means/scales/quats via the differentiable rendered
depth) and normal_src. Over many random (src, ref) pairs every view is pulled toward
mutual consistency. Integer-pixel gather (nearest neighbour) is used for the reference
lookup as in the original; the height-correcting gradient travels through the depth
VALUES (z_exp from src, z_ren from ref), which is what moves geometry — not through the
(non-differentiable) pixel coordinate.
"""
from __future__ import annotations

import torch
import torch.nn.functional as F


def _zero_dict(device):
    z = torch.zeros((), device=device)
    return {"total": z, "depth": z.detach(), "normal": z.detach(), "n_inlier": 0}


def l_multiview_consistency(
    depth_src: torch.Tensor,      # (Hs, Ws) rendered expected depth, source view
    normal_src: torch.Tensor,     # (Hs, Ws, 3) world-frame rendered normal, source view
    K_src: torch.Tensor,          # (3,3)
    w2c_src: torch.Tensor,        # (4,4) world->cam, source
    depth_ref: torch.Tensor,      # (Hr, Wr) rendered expected depth, reference (neighbor) view
    normal_ref: torch.Tensor,     # (Hr, Wr, 3) world-frame rendered normal, reference
    K_ref: torch.Tensor,          # (3,3)
    w2c_ref: torch.Tensor,        # (4,4) world->cam, reference
    *,
    w_normal: float = 0.5,        # weight of the normal-consistency term relative to depth
    rel_thresh: float = 0.1,      # occlusion inlier: relative depth error must be < this
    min_depth: float = 0.1,       # valid-depth floor (GS-local metres)
    min_src: int = 100,           # need this many valid source pixels to fire
    min_inlier: int = 10,         # need this many inliers after occlusion filtering
):
    """Multi-view depth + normal consistency. Returns dict(total, depth, normal, n_inlier).

    Self-supervised: no labels. depth_src/normal_src carry gradient into geometry;
    depth_ref/normal_ref are typically detached (reference rendered under no_grad).
    """
    device = depth_src.device
    Hs, Ws = depth_src.shape
    Hr, Wr = depth_ref.shape

    src_valid = depth_src > min_depth
    if int(src_valid.sum()) < min_src:
        return _zero_dict(device)

    # pixel grid (source)
    v_coords, u_coords = torch.meshgrid(
        torch.arange(Hs, device=device, dtype=torch.float32),
        torch.arange(Ws, device=device, dtype=torch.float32),
        indexing="ij",
    )

    fx_s, fy_s = K_src[0, 0], K_src[1, 1]
    cx_s, cy_s = K_src[0, 2], K_src[1, 2]

    d_s = depth_src[src_valid]
    u_s = u_coords[src_valid]
    v_s = v_coords[src_valid]

    # unproject source pixels -> camera 3D -> world (differentiable via d_s)
    x_cam = (u_s - cx_s) / fx_s * d_s
    y_cam = (v_s - cy_s) / fy_s * d_s
    z_cam = d_s
    pts_cam = torch.stack([x_cam, y_cam, z_cam, torch.ones_like(d_s)], dim=-1)  # (M,4)
    c2w_src = torch.inverse(w2c_src)
    pts_world = (c2w_src @ pts_cam.T).T[:, :3]  # (M,3)

    # project into reference view
    pts_ref_cam = (w2c_ref[:3, :3] @ pts_world.T + w2c_ref[:3, 3:4]).T  # (M,3)
    z_ref = pts_ref_cam[:, 2]
    front = z_ref > min_depth
    if int(front.sum()) < min_src:
        return _zero_dict(device)

    u_ref = (K_ref[0, 0] * pts_ref_cam[front, 0] / z_ref[front] + K_ref[0, 2]).long()
    v_ref = (K_ref[1, 1] * pts_ref_cam[front, 1] / z_ref[front] + K_ref[1, 2]).long()

    in_bounds = (u_ref >= 0) & (u_ref < Wr) & (v_ref >= 0) & (v_ref < Hr)
    if int(in_bounds.sum()) < min_src:
        return _zero_dict(device)

    u_valid = u_ref[in_bounds]
    v_valid = v_ref[in_bounds]
    z_expected = z_ref[front][in_bounds]          # depth we EXPECT in the ref view
    z_rendered = depth_ref[v_valid, u_valid]      # depth the ref view actually rendered

    ref_valid = z_rendered > min_depth
    if int(ref_valid.sum()) < min_inlier:
        return _zero_dict(device)

    z_exp = z_expected[ref_valid]
    z_ren = z_rendered[ref_valid]
    depth_consistency = torch.abs(z_exp - z_ren) / torch.max(z_exp, z_ren).clamp(min=1.0)

    # occlusion filter: only penalize where the views roughly agree (drop occluded hits)
    inlier = depth_consistency < rel_thresh
    n_inlier = int(inlier.sum())
    if n_inlier < min_inlier:
        return _zero_dict(device)

    loss_depth = depth_consistency[inlier].mean()

    # normal consistency at the same inlier correspondences
    loss_normal = torch.zeros((), device=device)
    if w_normal > 0.0:
        src_idx_flat = torch.where(src_valid.reshape(-1))[0]
        sel = src_idx_flat[front][in_bounds][ref_valid][inlier]
        n_src = normal_src.reshape(-1, 3)[sel]
        n_ref = normal_ref[v_valid[ref_valid][inlier], u_valid[ref_valid][inlier]]
        n_src = F.normalize(n_src, dim=-1, eps=1e-6)
        n_ref = F.normalize(n_ref, dim=-1, eps=1e-6)
        both = (n_src.abs().sum(-1) > 0.1) & (n_ref.abs().sum(-1) > 0.1)
        if int(both.sum()) > min_inlier:
            loss_normal = (1.0 - (n_src[both] * n_ref[both]).sum(-1).abs()).mean()

    total = loss_depth + w_normal * loss_normal
    return {
        "total": total,
        "depth": loss_depth.detach(),
        "normal": loss_normal.detach(),
        "n_inlier": n_inlier,
    }
