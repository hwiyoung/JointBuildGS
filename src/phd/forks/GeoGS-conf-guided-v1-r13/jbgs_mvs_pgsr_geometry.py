"""PGSR-style losses adapted to GeoGS expected ray/surface depth.

Reference: zju3dv/PGSR commit de24f1a38b350387e8d8fe381b2cd70c1ae946e7,
train.py:169-306, gaussian_renderer/__init__.py:118-159, utils/loss_utils.py.
This is a loss port, not PGSR's plane-parameter rasterizer. Camera-Z expected
surface depth plus a camera-facing normal define a local tangent plane with
signed equation n.X + d = 0. Its distance is derived, not independently rendered.

Differences from upstream: capped sampling also bounds geometric reprojection;
patches are microbatched; explicit finite/alpha/stencil/grazing/image-boundary
guards are applied; constant-image gradients and textureless patches are safe.
The caller REPLACES the existing normal consistency loss with ``svgeo``.
Weights and scheduling belong to the experiment contract, not this module.
No global RNG is consumed. Inputs are fixed calibrated cameras and real images;
only depth and rendered normal/alpha carry reconstruction gradients.
"""

import torch
import torch.nn.functional as F


def _hw(value, name):
    if value.ndim == 3 and value.shape[0] == 1:
        value = value[0]
    if value.ndim != 2:
        raise ValueError(f"{name} must be HxW or 1xHxW")
    return value


def _finite(value):
    return torch.where(torch.isfinite(value), value, torch.zeros_like(value))


def _pixels(height, width, like):
    yy, xx = torch.meshgrid(torch.arange(height, device=like.device, dtype=like.dtype),
                            torch.arange(width, device=like.device, dtype=like.dtype), indexing="ij")
    return torch.stack((xx, yy), dim=-1)


def _homogeneous(uv):
    return torch.cat((uv, torch.ones_like(uv[..., :1])), dim=-1)


def _grid(uv, height, width):
    return torch.stack((2 * uv[..., 0] / (width - 1) - 1,
                        2 * uv[..., 1] / (height - 1) - 1), dim=-1)


def _sample(value, uv):
    if value.ndim == 2:
        value = value[None]
    height, width = value.shape[-2:]
    original_shape = uv.shape[:-1]
    grid = _grid(uv, height, width).reshape(1, -1, 1, 2)
    sampled = F.grid_sample(value[None], grid, mode="bilinear", padding_mode="zeros", align_corners=True)
    return sampled[0, :, :, 0].T.reshape(*original_shape, value.shape[0])


def _inside(uv, height, width):
    return (torch.isfinite(uv).all(-1) & (uv[..., 0] >= 0) & (uv[..., 0] <= width - 1)
            & (uv[..., 1] >= 0) & (uv[..., 1] <= height - 1))


def _project(points, intrinsics, eps):
    projected = points @ intrinsics.T
    denominator = projected[..., 2:3]
    safe = torch.where(denominator.abs() > eps, denominator, torch.full_like(denominator, eps))
    return projected[..., :2] / safe


def pgsr_geometry_losses(depth_ref, normal_ref_world, alpha_ref, rgb_ref, K_ref, R_ref, t_ref,
                         *, depth_near=None, alpha_near=None, rgb_near=None, K_near=None,
                         R_near=None, t_near=None, max_samples=4096, microbatch_size=512,
                         patch_radius=3, reprojection_threshold=1.0, alpha_min=0.5,
                         grazing_cos_min=0.05, seed=0):
    """Return unweighted ``svgeo``, ``mvgeom``, ``mvrgb`` tensors and counts.

    Depth/alpha: HxW or 1xHxW. RGB/normal: 3xHxW. ``normal_ref_world`` is
    GeoGS's alpha-accumulated world normal, not an MVS normal. K: 3x3;
    world-to-camera transform: ``X_camera = R @ X_world + t``. Depth is
    expected camera-Z surface depth in the same units as camera translation.
    Near-view image dimensions may differ. All tensors must share dtype/device.
    Supplying no near view computes just single-view loss. All three losses
    remain differentiable zeros when no valid support survives.
    """
    if max_samples < 1 or microbatch_size < 1 or patch_radius < 1:
        raise ValueError("Sampling, microbatch and patch radius must be positive")
    if reprojection_threshold <= 0 or not 0 <= alpha_min <= 1 or not 0 <= grazing_cos_min < 1:
        raise ValueError("Invalid geometric support thresholds")
    depth_ref = _hw(depth_ref, "depth_ref")
    alpha_ref = _hw(alpha_ref, "alpha_ref")
    height, width = depth_ref.shape
    if min(height, width) < 3 or alpha_ref.shape != depth_ref.shape:
        raise ValueError("Reference shape mismatch or image smaller than 3x3")
    if normal_ref_world.shape != (3, height, width) or rgb_ref.shape != (3, height, width):
        raise ValueError("Reference normal and RGB must be 3xHxW")
    eps = max(1e-8, torch.finfo(depth_ref.dtype).eps)
    depth = _finite(depth_ref)
    normals_world = _finite(normal_ref_world)
    alpha = _finite(alpha_ref)
    rgb = _finite(rgb_ref.detach())
    K_ref, R_ref, t_ref = K_ref.detach(), R_ref.detach(), t_ref.detach().reshape(3)
    pixels = _pixels(height, width, depth)
    rays = _homogeneous(pixels) @ torch.linalg.inv(K_ref).T
    points = depth[..., None] * rays
    normal_camera = normals_world.permute(1, 2, 0) @ R_ref.T
    # Keep alpha-accumulated magnitude for the upstream single-view L1 term.
    # The sign choice is discrete; gradients flow through the selected normal.
    flip = torch.where((normal_camera * rays).sum(-1, keepdim=True) > 0, -1.0, 1.0)
    normal_camera = normal_camera * flip.detach()
    unit_normal = F.normalize(normal_camera, dim=-1, eps=eps)
    unit_ray = F.normalize(rays, dim=-1, eps=eps)
    grazing = (unit_normal * unit_ray).sum(-1).abs() >= grazing_cos_min
    valid = (torch.isfinite(depth_ref) & (depth > eps) & torch.isfinite(alpha_ref)
             & (alpha >= alpha_min) & torch.isfinite(normal_ref_world).all(0)
             & (normal_camera.norm(dim=-1) > eps) & torch.isfinite(rgb_ref).all(0) & grazing)
    zero = depth.sum() * 0 + normals_world.sum() * 0 + alpha.sum() * 0
    counts = {"reference_valid": int(valid.sum().item()), "sv_valid": 0,
              "mv_sampled": 0, "mv_projected": 0, "mv_valid": 0, "ncc_valid": 0}
    result = {"svgeo": zero, "mvgeom": zero, "mvrgb": zero, "counts": counts}

    dx = points[1:-1, 2:] - points[1:-1, :-2]
    dy = points[:-2, 1:-1] - points[2:, 1:-1]
    cross = torch.cross(dx, dy, dim=-1)
    depth_normal = F.normalize(cross, dim=-1, eps=eps)
    nd_flip = torch.where((depth_normal * rays[1:-1, 1:-1]).sum(-1, keepdim=True) > 0, -1.0, 1.0)
    depth_normal = depth_normal * nd_flip.detach()
    stencil = (valid[1:-1, 1:-1] & valid[1:-1, 2:] & valid[1:-1, :-2]
               & valid[2:, 1:-1] & valid[:-2, 1:-1] & (cross.norm(dim=-1) > eps))
    grad_x = (rgb[:, 1:-1, 2:] - rgb[:, 1:-1, :-2]).abs().mean(0)
    grad_y = (rgb[:, 2:, 1:-1] - rgb[:, :-2, 1:-1]).abs().mean(0)
    image_grad = torch.maximum(grad_x, grad_y)
    normalized_grad = (image_grad - image_grad.min()) / (image_grad.max() - image_grad.min()).clamp_min(eps)
    image_weight = ((1 - normalized_grad).clamp(0, 1) ** 2).detach()
    normal_error = (depth_normal * alpha[1:-1, 1:-1, None].detach()
                    - normal_camera[1:-1, 1:-1]).abs().sum(-1)
    counts["sv_valid"] = int(stencil.sum().item())
    if counts["sv_valid"]:
        result["svgeo"] = (image_weight * normal_error)[stencil].mean()

    if depth_near is None:
        return result
    if any(item is None for item in (alpha_near, rgb_near, K_near, R_near, t_near)):
        raise ValueError("All near-view tensors must be supplied together")
    depth_near = _hw(depth_near, "depth_near")
    alpha_near = _hw(alpha_near, "alpha_near")
    near_height, near_width = depth_near.shape
    if min(near_height, near_width) < 3 or alpha_near.shape != depth_near.shape:
        raise ValueError("Near depth/alpha shape mismatch")
    if rgb_near.shape != (3, near_height, near_width):
        raise ValueError("Near RGB must be 3xHxW")
    near_depth = _finite(depth_near)
    near_alpha = _finite(alpha_near)
    near_support = (torch.isfinite(depth_near) & (near_depth > eps)
                    & torch.isfinite(alpha_near) & (near_alpha >= alpha_min))
    K_near, R_near, t_near = K_near.detach(), R_near.detach(), t_near.detach().reshape(3)
    relative_rotation = R_near @ R_ref.T
    relative_translation = t_near - relative_rotation @ t_ref
    valid_indices = torch.nonzero(valid.reshape(-1), as_tuple=False).reshape(-1)
    if not valid_indices.numel():
        return result
    generator = torch.Generator(device="cpu")
    generator.manual_seed(int(seed))
    permutation = torch.randperm(valid_indices.numel(), generator=generator)[:max_samples]
    selected = valid_indices[permutation.to(valid_indices.device)]
    counts["mv_sampled"] = int(selected.numel())
    coeff = rgb.new_tensor([0.299, 0.587, 0.114])[:, None, None]
    gray_ref = (rgb * coeff).sum(0)
    gray_near = (_finite(rgb_near.detach()) * coeff).sum(0)
    rgb_near_valid = torch.isfinite(rgb_near).all(0).to(depth.dtype)
    rgb_ref_valid = torch.isfinite(rgb_ref).all(0).to(depth.dtype)
    offset_axis = torch.arange(-patch_radius, patch_radius + 1, device=depth.device, dtype=depth.dtype)
    offset_y, offset_x = torch.meshgrid(offset_axis, offset_axis, indexing="ij")
    offsets = torch.stack((offset_x, offset_y), -1).reshape(-1, 2)
    inv_K_ref = torch.linalg.inv(K_ref)
    geo_sum, ncc_sum = zero, zero
    for batch in selected.split(microbatch_size):
        uv = pixels.reshape(-1, 2)[batch]
        x_ref = points.reshape(-1, 3)[batch]
        x_near = x_ref @ relative_rotation.T + relative_translation
        uv_near = _project(x_near, K_near, eps)
        sampled_depth = _sample(near_depth, uv_near)[:, 0]
        sampled_support = _sample(near_support.to(depth.dtype), uv_near)[:, 0] > 0.999
        projected_valid = (_inside(uv_near, near_height, near_width) & (x_near[:, 2] > eps)
                           & sampled_support & (sampled_depth > eps))
        counts["mv_projected"] += int(projected_valid.sum().item())
        z_safe = x_near[:, 2:3].clamp_min(eps)
        x_near_reconstructed = x_near / z_safe * sampled_depth[:, None]
        x_ref_back = (x_near_reconstructed - relative_translation) @ relative_rotation
        uv_back = _project(x_ref_back, K_ref, eps)
        pixel_error = (uv_back - uv).norm(dim=-1)
        geometric_valid = (projected_valid & (x_ref_back[:, 2] > eps)
                           & torch.isfinite(pixel_error) & (pixel_error < reprojection_threshold))
        weights = torch.exp(-pixel_error).detach()
        count = int(geometric_valid.sum().item())
        counts["mv_valid"] += count
        if not count:
            continue
        geo_sum = geo_sum + (weights * pixel_error)[geometric_valid].sum()
        uv = uv[geometric_valid]
        x_ref = x_ref[geometric_valid]
        normals = unit_normal.reshape(-1, 3)[batch][geometric_valid]
        weights = weights[geometric_valid]
        # Facing normal => d > 0. Preserve this sign in H = K(R - t nT/d)K^-1.
        distance = -(normals * x_ref).sum(-1)
        homography = K_near[None] @ (relative_rotation[None]
                      - relative_translation[None, :, None] * normals[:, None, :]
                      / distance.clamp_min(eps)[:, None, None]) @ inv_K_ref[None]
        ref_patch = uv[:, None, :] + offsets[None]
        target_homogeneous = torch.einsum("bij,bpj->bpi", homography, _homogeneous(ref_patch))
        target_denominator = target_homogeneous[..., 2:3]
        target_patch = target_homogeneous[..., :2] / target_denominator.clamp_min(eps)
        patch_valid = (_inside(ref_patch, height, width).all(-1)
                       & _inside(target_patch, near_height, near_width).all(-1)
                       & (target_denominator[..., 0] > eps).all(-1) & (distance > eps)
                       & (_sample(rgb_ref_valid, ref_patch)[..., 0] > 0.999).all(-1)
                       & (_sample(rgb_near_valid, target_patch)[..., 0] > 0.999).all(-1))
        values_ref = _sample(gray_ref, ref_patch)[..., 0]
        values_near = _sample(gray_near, target_patch)[..., 0]
        centered_ref = values_ref - values_ref.mean(-1, keepdim=True)
        centered_near = values_near - values_near.mean(-1, keepdim=True)
        variance_ref = centered_ref.square().sum(-1)
        variance_near = centered_near.square().sum(-1)
        covariance = (centered_ref * centered_near).sum(-1)
        # Upstream LNCC squares covariance; it is not signed Pearson's 1-r.
        ncc = (1 - covariance.square() / (variance_ref * variance_near + 1e-8)).clamp(0, 2)
        ncc_valid = (patch_valid & (variance_ref > eps) & (variance_near > eps)
                     & torch.isfinite(ncc) & (ncc < 0.9))
        counts["ncc_valid"] += int(ncc_valid.sum().item())
        if ncc_valid.any():
            ncc_sum = ncc_sum + (weights * ncc)[ncc_valid].sum()
    if counts["mv_valid"]:
        result["mvgeom"] = geo_sum / counts["mv_valid"]
    if counts["ncc_valid"]:
        result["mvrgb"] = ncc_sum / counts["ncc_valid"]
    return result
