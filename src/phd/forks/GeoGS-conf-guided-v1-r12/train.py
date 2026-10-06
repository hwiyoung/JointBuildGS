#
# Copyright (C) 2023, Inria
# GRAPHDECO research group, https://team.inria.fr/graphdeco
# All rights reserved.
#
# This software is free for non-commercial, research and evaluation use
# under the terms of the LICENSE.md file.
#
# For inquiries contact  george.drettakis@inria.fr
#

"""
GeoGS Training Script (Anchoring Stage: LoD2 depth -> Refinement Stage: DA3 visual depth)

Goal:
  1) The Anchoring Stage uses a reliable but architecturally coarse depth (LoD2) to
     stabilize building geometry and protect it via proximity-based gradient attenuation.
  2) The Refinement Stage keeps a light LoD2 anchor while adding dense DA3 depth
     (optionally confidence-weighted) to recover façade details and the surrounding scene.

Example:
  python train.py \
    -s data/building1/building1_15 \
    -m output/building1_geogs \
    --lod_depth_path data/building1/building1_15/lod2_prior \
    --da_depth_path  data/building1/building1_15/da3_prior \
    --da_conf_path   data/building1/building1_15/da3_prior/da3_conf/raw_conf \
    --stage_switch_iter 8000 \
    --lambda_lod_init 0.08 \
    --lambda_lod_anchor 0.005 \
    --lambda_da_depth 0.05
"""

import os
import sys
import uuid
import cv2
import torch
import numpy as np
from pathlib import Path
from random import randint
from tqdm import tqdm
from argparse import ArgumentParser, Namespace
from plyfile import PlyData

from utils.loss_utils import l1_loss, ssim
from gaussian_renderer import render, network_gui
from scene import Scene, GaussianModel
from utils.general_utils import safe_state
from utils.image_utils import psnr, render_net_image
from lpipsPyTorch import lpips
from arguments import ModelParams, PipelineParams, OptimizationParams

try:
    from torch.utils.tensorboard import SummaryWriter
    TENSORBOARD_FOUND = True
except ImportError:
    TENSORBOARD_FOUND = False


def prepare_output_and_logger(args):
    if not args.model_path:
        if os.getenv("OAR_JOB_ID"):
            unique_str = os.getenv("OAR_JOB_ID")
        else:
            unique_str = str(uuid.uuid4())
        args.model_path = os.path.join("./output/", unique_str[0:10])

    print(f"Output folder: {args.model_path}")
    os.makedirs(args.model_path, exist_ok=True)
    with open(os.path.join(args.model_path, "cfg_args"), "w") as cfg_log_f:
        cfg_log_f.write(str(Namespace(**vars(args))))

    tb_writer = None
    if TENSORBOARD_FOUND:
        tb_writer = SummaryWriter(args.model_path)
    else:
        print("Tensorboard not available: not logging progress")
    return tb_writer


def training_report(tb_writer, iteration, L1_loss, loss, l1_loss, elapsed, testing_iterations,
                    scene: Scene, renderFunc, renderArgs, txt_path=None):
    if tb_writer:
        tb_writer.add_scalar("train_loss_patches/l1_loss", L1_loss.item(), iteration)
        tb_writer.add_scalar("train_loss_patches/total_loss", loss.item(), iteration)
        tb_writer.add_scalar("iter_time", elapsed, iteration)
        tb_writer.add_scalar("total_points", scene.gaussians.get_xyz.shape[0], iteration)

    if iteration in testing_iterations:
        torch.cuda.empty_cache()
        validation_configs = (
            {"name": "test", "cameras": scene.getTestCameras()},
            {"name": "train", "cameras": [scene.getTrainCameras()[idx % len(scene.getTrainCameras())] for idx in range(5, 30, 5)]},
        )

        for config in validation_configs:
            if not config["cameras"]:
                continue

            l1_test = 0.0
            psnr_test = 0.0
            ssim_test = 0.0
            lpips_test = 0.0

            if txt_path is not None and config["name"] == "test":
                elements = txt_path.split("/")
                base_dir = "/".join(elements[:-1])

                iter_dir = os.path.join(base_dir, f"iteration_{iteration:05d}")
                os.makedirs(iter_dir, exist_ok=True)

                render_path = os.path.join(iter_dir, "render")
                depth_path = os.path.join(iter_dir, "depth")
                normal_path = os.path.join(iter_dir, "normal")
                os.makedirs(render_path, exist_ok=True)
                os.makedirs(depth_path, exist_ok=True)
                os.makedirs(normal_path, exist_ok=True)

            for idx, viewpoint in enumerate(config["cameras"]):
                render_pkg = renderFunc(viewpoint, scene.gaussians, *renderArgs)
                image = torch.clamp(render_pkg["render"], 0.0, 1.0).to("cuda")
                gt_image = torch.clamp(viewpoint.original_image.to("cuda"), 0.0, 1.0)

                if txt_path is not None and config["name"] == "test":
                    import torchvision.utils
                    from utils.general_utils import colormap

                    render_image_path = os.path.join(render_path, f"{idx:03d}_render.png")
                    gt_image_path = os.path.join(render_path, f"{idx:03d}_gt.png")
                    torchvision.utils.save_image(image, render_image_path)
                    torchvision.utils.save_image(gt_image, gt_image_path)

                    depth = render_pkg["surf_depth"]
                    norm = depth.max()
                    depth = depth / norm if norm > 0 else depth
                    depth_np = depth.cpu().numpy()[0]
                    depth_colored = colormap(depth_np, cmap="turbo")
                    depth_path_file = os.path.join(depth_path, f"{idx:03d}_depth.png")
                    torchvision.utils.save_image(depth_colored, depth_path_file)

                    try:
                        surf_normal = render_pkg["surf_normal"] * 0.5 + 0.5
                        rend_normal = render_pkg["rend_normal"] * 0.5 + 0.5

                        surf_normal_path = os.path.join(normal_path, f"{idx:03d}_surf_normal.png")
                        rend_normal_path = os.path.join(normal_path, f"{idx:03d}_rend_normal.png")

                        torchvision.utils.save_image(surf_normal, surf_normal_path)
                        torchvision.utils.save_image(rend_normal, rend_normal_path)
                    except Exception as e:
                        print(f"Error saving normals: {e}")

                if tb_writer and (idx < 5):
                    from utils.general_utils import colormap

                    depth = render_pkg["surf_depth"]
                    norm = depth.max()
                    depth = depth / norm
                    depth = colormap(depth.cpu().numpy()[0], cmap="turbo")
                    tb_writer.add_images(f"{config['name']}_view_{viewpoint.image_name}/depth", depth[None], global_step=iteration)
                    tb_writer.add_images(f"{config['name']}_view_{viewpoint.image_name}/render", image[None], global_step=iteration)

                    try:
                        rend_alpha = render_pkg["rend_alpha"]
                        rend_normal = render_pkg["rend_normal"] * 0.5 + 0.5
                        surf_normal = render_pkg["surf_normal"] * 0.5 + 0.5
                        tb_writer.add_images(f"{config['name']}_view_{viewpoint.image_name}/rend_normal", rend_normal[None], global_step=iteration)
                        tb_writer.add_images(f"{config['name']}_view_{viewpoint.image_name}/surf_normal", surf_normal[None], global_step=iteration)
                        tb_writer.add_images(f"{config['name']}_view_{viewpoint.image_name}/rend_alpha", rend_alpha[None], global_step=iteration)

                        rend_dist = render_pkg["rend_dist"]
                        from utils.general_utils import colormap as cmap_fn

                        rend_dist = cmap_fn(rend_dist.cpu().numpy()[0])
                        tb_writer.add_images(f"{config['name']}_view_{viewpoint.image_name}/rend_dist", rend_dist[None], global_step=iteration)
                    except Exception:
                        pass

                    if iteration == testing_iterations[0]:
                        tb_writer.add_images(f"{config['name']}_view_{viewpoint.image_name}/ground_truth", gt_image[None], global_step=iteration)

                l1_test += l1_loss(image, gt_image).mean().double()
                psnr_test += psnr(image, gt_image).mean().double()
                ssim_test += ssim(image, gt_image).mean().double()
                lpips_test += lpips(image, gt_image).mean().double()

            psnr_test /= len(config["cameras"])
            l1_test /= len(config["cameras"])
            ssim_test /= len(config["cameras"])
            lpips_test /= len(config["cameras"])

            print(f"\n[ITER {iteration}] Evaluating {config['name']}: L1 {l1_test} PSNR {psnr_test}")

            if config["name"] == "test":
                with open(txt_path, "a") as fp:
                    print(f"{iteration}_{psnr_test:.6f}_{ssim_test:.6f}_{lpips_test:.6f}", file=fp)

            if txt_path is not None and config["name"] == "test":
                elements = txt_path.split("/")
                base_dir = "/".join(elements[:-1])
                metrics_path = os.path.join(base_dir, f"metrics_{iteration:05d}.txt")

                with open(metrics_path, "w") as f:
                    f.write(f"Iteration: {iteration}\n")
                    f.write(f"L1 Loss: {l1_test:.6f}\n")
                    f.write(f"PSNR: {psnr_test:.6f}\n")
                    f.write(f"SSIM: {ssim_test:.6f}\n")
                    f.write(f"LPIPS: {lpips_test:.6f}\n")

            if tb_writer:
                tb_writer.add_scalar(f"{config['name']}/loss_viewpoint - l1_loss", l1_test, iteration)
                tb_writer.add_scalar(f"{config['name']}/loss_viewpoint - psnr", psnr_test, iteration)
                tb_writer.add_scalar(f"{config['name']}/loss_viewpoint - ssim", ssim_test, iteration)
                tb_writer.add_scalar(f"{config['name']}/loss_viewpoint - lpips", lpips_test, iteration)

        torch.cuda.empty_cache()


def load_depth_set(depth_root, cameras, target_size, device="cuda"):
    """
    Load depth maps for all cameras from a directory containing raw_depth/*.npy.
    Returns a dict image_name -> torch.Tensor[H, W].
    """
    depth_dir = Path(depth_root) / "raw_depth"
    if not depth_dir.exists():
        print(f"[Warning] Depth directory not found: {depth_dir}")
        return {}

    target_h, target_w = target_size
    depth_maps = {}

    for cam in cameras:
        name = cam.image_name
        depth_path = depth_dir / f"{name}.npy"
        if not depth_path.exists():
            continue
        try:
            depth = np.load(depth_path)
            depth_resized = cv2.resize(depth, (target_w, target_h), interpolation=cv2.INTER_LINEAR)
            depth_maps[name] = torch.tensor(depth_resized, dtype=torch.float32, device=device)
        except Exception as e:
            print(f"[Warning] Failed to load depth for {name}: {e}")
    print(f"Loaded {len(depth_maps)} depth maps from {depth_dir}")
    return depth_maps


def load_confidence_set(conf_root, cameras, target_size, device="cuda"):
    """
    Load confidence maps directly without normalization.
    Expects confidence values in reasonable range (e.g., [0, 1]).
    """
    conf_dir = Path(conf_root)
    if conf_dir.is_dir() and (conf_dir / "raw_conf").exists():
        conf_dir = conf_dir / "raw_conf"
    if not conf_dir.exists():
        print(f"[Info] Confidence directory not found: {conf_dir}")
        return {}

    target_h, target_w = target_size
    conf_maps = {}

    for cam in cameras:
        name = cam.image_name
        conf_path = conf_dir / f"{name}.npy"
        if not conf_path.exists():
            continue
        try:
            conf = np.load(conf_path)
            conf_resized = cv2.resize(conf, (target_w, target_h), interpolation=cv2.INTER_LINEAR)
            conf_maps[name] = torch.tensor(conf_resized, dtype=torch.float32, device=device)
        except Exception as e:
            print(f"[Warning] Failed to load confidence for {name}: {e}")
    print(f"Loaded {len(conf_maps)} confidence maps from {conf_dir}")
    return conf_maps


def compute_depth_loss(pred_depth, gt_depth, conf_map=None, mask=None, use_scale_invariant=False):
    """
    Depth loss with optional scale-invariant alignment and confidence weighting.

    For metric depth (LoD2, aligned DA3), set use_scale_invariant=False to enforce
    absolute scale supervision. For unaligned monocular depth, use scale_invariant=True.

    Args:
        pred_depth: [1, H, W] predicted depth
        gt_depth: [H, W] ground truth depth
        conf_map: [H, W] optional confidence map
        mask: [H, W] optional binary mask
        use_scale_invariant: if True, align pred to gt via median ratio before loss
    """
    if gt_depth is None:
        return torch.tensor(0.0, device="cuda")

    pred = pred_depth.squeeze(0)  # [H, W]
    valid_mask = torch.isfinite(gt_depth) & torch.isfinite(pred) & (gt_depth > 0)
    if mask is not None:
        valid_mask = valid_mask & (mask > 0)
    if valid_mask.sum() == 0:
        return torch.tensor(0.0, device="cuda")

    pred_valid = pred[valid_mask]
    gt_valid = gt_depth[valid_mask]

    if use_scale_invariant:
        # Scale-invariant: align prediction to GT via median ratio
        # Use this only for unaligned monocular depth predictions
        if pred_valid.median() > 0 and gt_valid.median() > 0:
            scale_ratio = gt_valid.median() / (pred_valid.median() + 1e-6)
        else:
            scale_ratio = 1.0
        diff = torch.abs(pred_valid * scale_ratio - gt_valid)
    else:
        # Metric depth: direct L1 loss preserving absolute scale
        # Use this for LoD2 depth and aligned DA3 depth
        diff = torch.abs(pred_valid - gt_valid)

    if conf_map is not None:
        conf_valid = conf_map[valid_mask]
        weight_sum = conf_valid.sum()
        if weight_sum > 0:
            return (diff * conf_valid).sum() / (weight_sum + 1e-6)

    return diff.mean()


def load_lod2_pcd(ply_path, max_points=None, device="cuda"):
    """
    Load LoD2 point cloud from a PLY file. Optionally subsample for efficiency.
    Returns tuple (xyz, normals) where:
        - xyz: torch.Tensor [N,3] on device, or None if unavailable
        - normals: torch.Tensor [N,3] on device, or None if not available in PLY
    """
    if not ply_path:
        return None, None
    if not os.path.exists(ply_path):
        print(f"[Warning] LoD2 PCD not found: {ply_path}")
        return None, None
    try:
        plydata = PlyData.read(ply_path)
        verts = plydata.elements[0]
        xyz = np.stack((np.asarray(verts["x"]), np.asarray(verts["y"]), np.asarray(verts["z"])), axis=1).astype(np.float32)

        # Try to load normals if available
        normals = None
        if all(name in verts.data.dtype.names for name in ["nx", "ny", "nz"]):
            normals = np.stack((np.asarray(verts["nx"]), np.asarray(verts["ny"]), np.asarray(verts["nz"])), axis=1).astype(np.float32)
            print(f"[LoD2] Loaded normals from PLY file")

        # Subsample if needed
        if max_points is not None and xyz.shape[0] > max_points:
            orig = xyz.shape[0]
            idx = np.random.choice(xyz.shape[0], max_points, replace=False)
            xyz = xyz[idx]
            if normals is not None:
                normals = normals[idx]
            print(f"[LoD2] Subsampled to {max_points} points from {orig} original.")

        xyz_t = torch.tensor(xyz, device=device)
        normals_t = torch.tensor(normals, device=device) if normals is not None else None
        print(f"[LoD2] Loaded point cloud with {xyz_t.shape[0]} points from {ply_path}")
        return xyz_t, normals_t
    except Exception as e:
        print(f"[Error] Failed to load LoD2 PCD: {e}")
        return None, None


def find_building_mask_from_pcd(gaussians: GaussianModel, lod2_points, dist_thresh, chunk_size=20000):
    """
    Mark gaussians whose centers lie within dist_thresh of any LoD2 point.
    Returns a boolean mask over gaussians.get_xyz.
    """
    if lod2_points is None or lod2_points.numel() == 0:
        return None
    xyz = gaussians.get_xyz
    lod2 = lod2_points.to(xyz.device)
    n = xyz.shape[0]
    mask = torch.zeros(n, device=xyz.device, dtype=torch.bool)
    # Two-level chunking to avoid OOM: split gaussians and LoD2 points
    for start in range(0, n, chunk_size):
        end = min(start + chunk_size, n)
        xyz_chunk = xyz[start:end]
        min_dist = None
        for l_start in range(0, lod2.shape[0], chunk_size):
            l_end = min(l_start + chunk_size, lod2.shape[0])
            dists = torch.cdist(xyz_chunk, lod2[l_start:l_end])
            chunk_min = dists.min(dim=1).values
            if min_dist is None:
                min_dist = chunk_min
            else:
                min_dist = torch.minimum(min_dist, chunk_min)
        mask[start:end] = min_dist < dist_thresh
    return mask


def find_uncovered_lod2_points(gaussians: GaussianModel, lod2_points, dist_thresh, chunk_size=20000):
    """
    Find LoD2 points that are not covered by any Gaussian (reverse matching).
    Returns a boolean mask where True indicates the LoD2 point is uncovered.
    """
    if lod2_points is None or lod2_points.numel() == 0:
        return None
    xyz = gaussians.get_xyz  # [N_gauss, 3]
    lod2 = lod2_points.to(xyz.device)  # [M_lod2, 3]
    m = lod2.shape[0]
    uncovered_mask = torch.ones(m, device=lod2.device, dtype=torch.bool)

    # For each LoD2 point, find distance to nearest Gaussian
    for start in range(0, m, chunk_size):
        end = min(start + chunk_size, m)
        lod2_chunk = lod2[start:end]
        min_dist = None

        for g_start in range(0, xyz.shape[0], chunk_size):
            g_end = min(g_start + chunk_size, xyz.shape[0])
            dists = torch.cdist(lod2_chunk, xyz[g_start:g_end])
            chunk_min = dists.min(dim=1).values
            if min_dist is None:
                min_dist = chunk_min
            else:
                min_dist = torch.minimum(min_dist, chunk_min)

        uncovered_mask[start:end] = min_dist >= dist_thresh

    return uncovered_mask


def normal_to_quaternion(normals: torch.Tensor) -> torch.Tensor:
    """
    Convert normal vectors to quaternions for 2D Gaussian rotation.
    Assumes default surfel normal is [0, 0, 1] (z-up).

    Uses half-angle formula for numerical stability.

    Args:
        normals: [N, 3] normal vectors (will be normalized internally)
    Returns:
        quaternions: [N, 4] unit quaternions (w, x, y, z)
    """
    N = normals.shape[0]
    device = normals.device

    # Ensure normals are normalized (PLY normals may not be unit length)
    normals = normals / (normals.norm(dim=1, keepdim=True) + 1e-8)

    # Default surfel normal points in +Z direction
    # We want rotation R such that R @ [0,0,1] = normal

    # Extract normal components
    nx = normals[:, 0]
    ny = normals[:, 1]
    nz = normals[:, 2]

    # For normals pointing downward (nz < -0.99), use 180-degree rotation around X-axis
    # quaternion for 180-deg around X: [0, 1, 0, 0]
    downward_mask = nz < -0.99

    # For other normals, use the standard formula:
    # rotation axis = normalize(cross([0,0,1], normal)) = normalize([-ny, nx, 0])
    # rotation angle = acos(dot([0,0,1], normal)) = acos(nz)
    # quaternion: [cos(angle/2), sin(angle/2) * axis]

    # Using half-angle identities:
    # cos(angle/2) = sqrt((1 + cos(angle))/2) = sqrt((1 + nz)/2)
    # sin(angle/2) = sqrt((1 - cos(angle))/2) = sqrt((1 - nz)/2)

    # For numerical stability, compute:
    # w = sqrt((1 + nz) / 2)
    # s = sqrt((1 - nz) / 2)  # sin(angle/2)
    # axis = [-ny, nx, 0] / sqrt(nx^2 + ny^2) = [-ny, nx, 0] / sqrt(1 - nz^2)
    # But sqrt(1 - nz^2) = sqrt((1-nz)(1+nz)), and s = sqrt((1-nz)/2)
    # So axis * s = [-ny, nx, 0] * sqrt((1-nz)/2) / sqrt((1-nz)(1+nz))
    #             = [-ny, nx, 0] / sqrt(2(1+nz))

    # Final quaternion components:
    w = torch.sqrt((1 + nz) / 2 + 1e-8)  # [N]
    denom = torch.sqrt(2 * (1 + nz) + 1e-8)  # [N]
    qx = -ny / denom
    qy = nx / denom
    qz = torch.zeros_like(nx)

    # Stack into quaternion [w, x, y, z]
    q = torch.stack([w, qx, qy, qz], dim=1)  # [N, 4]

    # Handle downward-pointing normals (180-degree rotation around X-axis)
    if downward_mask.any():
        q[downward_mask] = torch.tensor([0., 1., 0., 0.], device=device)

    # Normalize to ensure unit quaternion
    q = q / (q.norm(dim=1, keepdim=True) + 1e-8)

    return q


def complete_building_gaussians(gaussians: GaussianModel, uncovered_points, building_mask,
                                 min_opacity=0.3, k_neighbors=3, initial_opacity=0.1,
                                 uncovered_normals=None, scale_multiplier=1.0):
    """
    Add new Gaussians at uncovered LoD2 point locations, inheriting attributes
    from nearest building Gaussians.

    Args:
        uncovered_points: [U, 3] positions where new Gaussians should be added
        building_mask: [N] boolean mask identifying existing building Gaussians
        min_opacity: minimum opacity threshold for source Gaussians
        k_neighbors: number of nearest neighbors to inherit attributes from
        initial_opacity: initial opacity for new Gaussians (0-1)
        uncovered_normals: [U, 3] optional normals for rotation initialization
    Returns:
        num_added: number of Gaussians added
    """
    # 1. Filter high-quality building Gaussians as sources
    opacity = gaussians.get_opacity.squeeze()
    quality_mask = building_mask & (opacity >= min_opacity)
    candidate_indices = torch.where(quality_mask)[0]

    if candidate_indices.shape[0] == 0:
        print("[Warning] No valid source Gaussians for completion")
        return 0

    candidate_xyz = gaussians.get_xyz[candidate_indices]
    U = uncovered_points.shape[0]
    k = min(k_neighbors, candidate_indices.shape[0])

    # 2. Find k nearest source Gaussians for each uncovered point
    dists = torch.cdist(uncovered_points, candidate_xyz)
    _, topk_local = dists.topk(k, dim=1, largest=False)
    src_indices = candidate_indices[topk_local]  # [U, k]

    # 3. Inherit attributes from nearest neighbors
    new_xyz = uncovered_points.clone()

    # Color features: average of k neighbors
    new_features_dc = gaussians._features_dc[src_indices].mean(dim=1)
    new_features_rest = gaussians._features_rest[src_indices].mean(dim=1)

    # Scaling: average of k neighbors, with optional multiplier
    new_scaling = gaussians._scaling[src_indices].mean(dim=1)
    if scale_multiplier > 1.0:
        import math
        new_scaling = new_scaling + math.log(scale_multiplier)
        print(f"    Applied scale multiplier {scale_multiplier}x (log-space offset: {math.log(scale_multiplier):.3f})")

    # Rotation: use LoD2 normals if available, otherwise inherit from nearest neighbor
    if uncovered_normals is not None:
        new_rotation = normal_to_quaternion(uncovered_normals)
        print(f"    Initialized rotation from LoD2 normals")
    else:
        new_rotation = gaussians._rotation[src_indices[:, 0]]
        print(f"    Inherited rotation from nearest neighbors")

    # Opacity: use fixed initial value, let training adjust
    new_opacities = torch.full((U, 1),
                               gaussians.inverse_opacity_activation(torch.tensor(initial_opacity)).item(),
                               device="cuda")

    # 4. Add new Gaussians using standard method
    gaussians.densification_postfix(
        new_xyz, new_features_dc, new_features_rest,
        new_opacities, new_scaling, new_rotation
    )

    # Sync and check for CUDA errors immediately
    torch.cuda.synchronize()
    print(f"    Densification completed successfully, total Gaussians: {gaussians.get_xyz.shape[0]}")

    return U


def freeze_gaussians(gaussians: GaussianModel, freeze_mask: torch.Tensor):
    """
    Freeze a subset of Gaussians by zeroing gradients via hooks and clearing optimizer state.
    """
    def hook_mask(mask):
        def _hook(grad):
            if grad is None:
                return grad
            mask_view = mask.view(mask.shape[0], *([1] * (grad.dim() - 1)))
            grad = grad.clone()
            grad[mask_view.expand_as(grad)] = 0
            return grad
        return _hook

    for tensor in [gaussians._xyz, gaussians._features_dc, gaussians._features_rest, gaussians._opacity, gaussians._scaling, gaussians._rotation]:
        tensor.register_hook(hook_mask(freeze_mask))

    # Clear optimizer momentum for frozen entries to avoid residual updates.
    for group in gaussians.optimizer.param_groups:
        param = group["params"][0]
        state = gaussians.optimizer.state.get(param, None)
        if state is None:
            continue
        for key in ("exp_avg", "exp_avg_sq"):
            buf = state.get(key, None)
            if buf is None or not torch.is_tensor(buf):
                continue
            mask_view = freeze_mask.view(freeze_mask.shape[0], *([1] * (buf.dim() - 1)))
            buf[mask_view.expand_as(buf)] = 0

    print(f"[Freeze] Frozen {freeze_mask.sum().item()} gaussians based on LoD2 matches.")


def attenuate_building_xyz_lr(gaussians: GaussianModel, building_mask: torch.Tensor, scale: float):
    """
    Reduce xyz gradient magnitude for building gaussians by a factor (0<scale<=1).
    """
    def hook_mask(mask, factor):
        def _hook(grad):
            if grad is None:
                return grad
            mask_view = mask.view(mask.shape[0], *([1] * (grad.dim() - 1)))
            grad = grad.clone()
            grad[mask_view.expand_as(grad)] *= factor
            return grad
        return _hook

    gaussians._xyz.register_hook(hook_mask(building_mask, scale))
    print(f"[LoD2] Applied xyz LR scale {scale} to {building_mask.sum().item()} building gaussians.")


def attenuate_building_other_lr(gaussians: GaussianModel, building_mask: torch.Tensor, scale: float, apply_rotation=True, apply_scaling=True):
    """
    Reduce rotation/scaling gradients for building gaussians.
    """
    def hook_mask(mask, factor):
        def _hook(grad):
            if grad is None:
                return grad
            mask_view = mask.view(mask.shape[0], *([1] * (grad.dim() - 1)))
            grad = grad.clone()
            grad[mask_view.expand_as(grad)] *= factor
            return grad
        return _hook

    if apply_rotation:
        gaussians._rotation.register_hook(hook_mask(building_mask, scale))
    if apply_scaling:
        gaussians._scaling.register_hook(hook_mask(building_mask, scale))
    print(f"[LoD2] Applied rotation/scale LR scale {scale} to {building_mask.sum().item()} building gaussians.")


def attenuate_building_rotation_differentiated(
    gaussians: GaussianModel,
    building_mask: torch.Tensor,
    completed_mask: torch.Tensor,
    regular_scale: float,
    completion_scale: float
):
    """
    Apply different rotation gradient scales to regular building Gaussians vs completed Gaussians.
    - Regular building Gaussians: gradient × regular_scale (e.g., 0.01)
    - Completed Gaussians: gradient × completion_scale (e.g., 0.1)
    """
    # Create differentiated scale array
    n = gaussians.get_xyz.shape[0]
    scale_array = torch.ones(n, device="cuda")

    # Building Gaussians get regular_scale
    scale_array[building_mask] = regular_scale

    # Non-building Gaussians keep scale = 1.0 (already set)

    # Completed Gaussians get completion_scale (overrides regular_scale)
    scale_array[completed_mask] = completion_scale

    def hook_differentiated(scale_arr):
        def _hook(grad):
            if grad is None:
                return grad
            scale_view = scale_arr.view(scale_arr.shape[0], *([1] * (grad.dim() - 1)))
            return grad * scale_view.expand_as(grad)
        return _hook

    gaussians._rotation.register_hook(hook_differentiated(scale_array))

    n_completed = completed_mask.sum().item()
    n_regular = building_mask.sum().item() - n_completed
    print(f"[LoD2] Rotation LR: {n_regular} regular building @ {regular_scale}, {n_completed} completed @ {completion_scale}")


import jbgs_state
import jbgs_mvs_pgsr
import jbgs_judgment  # [jbgs_judgment]


def training(dataset, opt, pipe, args, testing_iterations, saving_iterations, checkpoint_iterations, checkpoint):
    first_iter = 0
    tb_writer = prepare_output_and_logger(dataset)
    mvs_pgsr_control = jbgs_mvs_pgsr.from_environment(dataset, opt, pipe, args)
    gaussians = GaussianModel(dataset.sh_degree)
    scene = Scene(dataset, gaussians)

    gaussians.training_setup(opt)
    if checkpoint:
        (model_params, first_iter) = torch.load(checkpoint)
        gaussians.restore(model_params, opt)

    bg_color = [1, 1, 1] if dataset.white_background else [0, 0, 0]
    background = torch.tensor(bg_color, dtype=torch.float32, device="cuda")
    # [jbgs_judgment] judgment-guided optimization (ORDER section 4); None keeps the native path
    judgment = jbgs_judgment.Judgment(args, opt, scene, gaussians, tb_writer, render_fn=render, pipe=pipe, background=background) if args.jbgs_judgment != "off" else None  # [jbgs_judgment r6] E renders the training views (fix 1)

    iter_start = torch.cuda.Event(enable_timing=True)
    iter_end = torch.cuda.Event(enable_timing=True)

    viewpoint_stack = None
    ema_loss_for_log = 0.0
    ema_dist_for_log = 0.0
    ema_normal_for_log = 0.0
    ema_lod_loss = 0.0
    ema_da_loss = 0.0

    # Stage configuration
    stage_switch_iter = args.stage_switch_iter
    lambda_lod_init = args.lambda_lod_init
    lambda_lod_anchor = args.lambda_lod_anchor
    lambda_da_depth = args.lambda_da_depth
    use_confidence = args.use_confidence
    dynamic_stage = args.dynamic_stage_switch
    dynamic_window = args.dynamic_window
    dynamic_threshold = args.dynamic_threshold
    dynamic_check_interval = args.dynamic_check_interval
    dynamic_min_iter = args.dynamic_min_iter
    dynamic_max_iter = args.dynamic_max_iter
    dynamic_da = args.dynamic_depth_weight

    # Load depth maps for all train/test cameras once
    all_cameras = scene.getTrainCameras() + scene.getTestCameras()
    target_size = (all_cameras[0].image_height, all_cameras[0].image_width)

    lod_depth_maps = load_depth_set(args.lod_depth_path, all_cameras, target_size)
    # Legacy da variables now contain explicitly bound MVS supervision.
    da_depth_maps = mvs_pgsr_control.load_mvs_depth_set(
        all_cameras, target_size,
        train_camera_names=[camera.image_name for camera in scene.getTrainCameras()])
    da_conf_maps = {}
    if use_confidence and args.da_conf_path:
        da_conf_maps = load_confidence_set(args.da_conf_path, all_cameras, target_size)

    # Prepare LoD2 point cloud (for stage switch freezing)
    lod2_pcd, lod2_normals = load_lod2_pcd(args.lod2_pcd_path, args.lod2_max_points)
    building_freeze_mask = None
    freeze_done = False
    # completed_mask is now tracked inside gaussians (gaussians.completed_mask)
    dynamic_switch_triggered = False
    dynamic_switch_iter = None
    dynamic_switch_forced = False
    lod_loss_history = []
    last_dynamic_check = 0
    # Dynamic DA weight state
    PHASE_INITIAL = 0
    PHASE_CONVERGED = 1
    PHASE_DECAYING = 2
    PHASE_LOCKED = 3
    da_phase = PHASE_INITIAL
    da_weight = opt.depth_initial_weight if dynamic_da else lambda_da_depth
    da_depth_history = []
    da_monitor_depth = []
    da_monitor_rgb = []
    da_last_check = None
    da_consecutive = 0
    da_locked_weight = None

    print("-" * 80)
    print("Dual-depth training schedule:")
    if args.use_scale_invariant:
        print("  Depth loss mode: SCALE-INVARIANT (aligns pred to gt via median ratio)")
    else:
        print("  Depth loss mode: METRIC (direct L1, preserves absolute scale)")
    if dynamic_stage:
        print(f"  Stage 1: LoD2-only depth @ {lambda_lod_init} until LoD2 loss converges (dynamic)")
        print(f"  Dynamic switch: window={dynamic_window}, threshold={dynamic_threshold}, check_interval={dynamic_check_interval}, min_iter={dynamic_min_iter}, max_iter={dynamic_max_iter}")
        print(f"  Stage 2: LoD2 anchor @ {lambda_lod_anchor} + DA3 depth @ {lambda_da_depth}")
    else:
        print(f"  Stage 1 (1 → {stage_switch_iter}): LoD2-only depth @ {lambda_lod_init}")
        print(f"  Stage 2 ({stage_switch_iter+1} → end): LoD2 anchor @ {lambda_lod_anchor} + DA3 depth @ {lambda_da_depth}")
    if use_confidence and da_conf_maps:
        print(f"  DA3 confidence weighting enabled ({len(da_conf_maps)} maps loaded)")
    else:
        print("  DA3 confidence weighting disabled or maps missing")
    print("  Distortion weight activates at 3000, normal weight at 7000 (same as base)")
    print("-" * 80)

    if args.jbgs_resume_full:
        jbgs_restored = jbgs_state.restore_state(args.jbgs_resume_full, locals(), globals())
        first_iter = jbgs_restored["first_iter"]
        building_freeze_mask = jbgs_restored["building_freeze_mask"]
        viewpoint_stack = jbgs_restored["viewpoint_stack"]
        ema_loss_for_log = jbgs_restored["ema_loss_for_log"]
        ema_dist_for_log = jbgs_restored["ema_dist_for_log"]
        ema_normal_for_log = jbgs_restored["ema_normal_for_log"]
        ema_lod_loss = jbgs_restored["ema_lod_loss"]
        ema_da_loss = jbgs_restored["ema_da_loss"]
        freeze_done = jbgs_restored["freeze_done"]
        dynamic_switch_triggered = jbgs_restored["dynamic_switch_triggered"]
        dynamic_switch_iter = jbgs_restored["dynamic_switch_iter"]
        dynamic_switch_forced = jbgs_restored["dynamic_switch_forced"]
        lod_loss_history = jbgs_restored["lod_loss_history"]
        last_dynamic_check = jbgs_restored["last_dynamic_check"]
        da_phase = jbgs_restored["da_phase"]
        da_weight = jbgs_restored["da_weight"]
        da_depth_history = jbgs_restored["da_depth_history"]
        da_monitor_depth = jbgs_restored["da_monitor_depth"]
        da_monitor_rgb = jbgs_restored["da_monitor_rgb"]
        da_last_check = jbgs_restored["da_last_check"]
        da_consecutive = jbgs_restored["da_consecutive"]
        da_locked_weight = jbgs_restored["da_locked_weight"]

    progress_bar = tqdm(range(first_iter, opt.iterations), desc="Training progress")
    first_iter += 1
    for iteration in range(first_iter, opt.iterations + 1):
        iter_start.record()
        gaussians.update_learning_rate(iteration)
        if judgment is not None and judgment.due_E(iteration):  # [jbgs_judgment] E at 0 and every e_interval
            judgment.update_E(iteration, gaussians)

        if iteration % 1000 == 0:
            gaussians.oneupSHdegree()

        if not viewpoint_stack:
            viewpoint_stack = scene.getTrainCameras().copy()

        viewpoint_cam = viewpoint_stack.pop(randint(0, len(viewpoint_stack) - 1))

        cam_name = viewpoint_cam.image_name
        lod_depth = lod_depth_maps.get(cam_name, None)
        da_depth = da_depth_maps.get(cam_name, None)
        da_conf = da_conf_maps.get(cam_name, None)

        # Confidence weighting: normalize by mean to preserve overall loss magnitude
        da_conf_weight = None
        if use_confidence and da_conf is not None:
            da_conf_weight = da_conf / (da_conf.mean() + 1e-6)

        render_pkg = render(viewpoint_cam, gaussians, pipe, background)
        image = render_pkg["render"]
        viewspace_point_tensor = render_pkg["viewspace_points"]
        visibility_filter = render_pkg["visibility_filter"]
        radii = render_pkg["radii"]

        gt_image = viewpoint_cam.original_image.cuda()

        # Depth losses (use_scale_invariant=False by default for metric depth)
        lod_depth_loss = compute_depth_loss(
            render_pkg["surf_depth"], lod_depth,
            use_scale_invariant=args.use_scale_invariant
        )
        da_depth_loss = compute_depth_loss(
            render_pkg["surf_depth"],
            da_depth,
            conf_map=da_conf_weight if use_confidence else None,
            use_scale_invariant=args.use_scale_invariant
        )

        # RGB loss (full image)
        Ll1 = l1_loss(image, gt_image)
        rgb_loss = (1.0 - opt.lambda_dssim) * Ll1 + opt.lambda_dssim * (1.0 - ssim(image, gt_image))

        # Regularizers
        lambda_normal_default = opt.lambda_normal if iteration > 7000 else 0.0
        lambda_dist = opt.lambda_dist if iteration > 3000 else 0.0

        rend_dist = render_pkg["rend_dist"]
        rend_normal = render_pkg["rend_normal"]
        surf_normal = render_pkg["surf_normal"]
        normal_error = (1 - (rend_normal * surf_normal).sum(dim=0))[None]

        normal_loss = lambda_normal_default * (normal_error).mean()
        dist_loss = lambda_dist * (rend_dist).mean()

        if judgment is not None:  # [jbgs_judgment] weighted MVS term + truncated prior term
            mvs_term, prior_term, _jstats = judgment.losses(cam_name, render_pkg)
            total_loss = rgb_loss + dist_loss + normal_loss + judgment.lambda_mvs * mvs_term + judgment.lambda_prior * prior_term
            lod_depth_loss = prior_term
            da_depth_loss = mvs_term
            current_lod_weight = judgment.lambda_prior
            current_da_weight = judgment.lambda_mvs
            just_switched = False
            stage2_active = True
        else:
            # Stage switching (fixed or dynamic)
            just_switched = False
            stage2_active = False

            if dynamic_stage:
                # Track LoD loss history for convergence detection
                lod_loss_val = lod_depth_loss.item() if isinstance(lod_depth_loss, torch.Tensor) else float(lod_depth_loss)
                lod_loss_history.append(lod_loss_val)
                if len(lod_loss_history) > dynamic_window:
                    lod_loss_history.pop(0)

                if (not dynamic_switch_triggered) and iteration >= dynamic_min_iter and (iteration - last_dynamic_check) >= dynamic_check_interval:
                    last_dynamic_check = iteration
                    if len(lod_loss_history) == dynamic_window:
                        mid = dynamic_window // 2
                        first_med = np.median(lod_loss_history[:mid])
                        last_med = np.median(lod_loss_history[mid:])
                        rel_change = abs(first_med - last_med) / max(first_med, 1e-6)
                        if rel_change < dynamic_threshold:
                            dynamic_switch_triggered = True
                            dynamic_switch_iter = iteration
                            dynamic_switch_forced = False
                            just_switched = True
                            print(f"\n[Dynamic Switch] LoD2 loss converged at iter {iteration}: rel_change={rel_change:.4f} (<{dynamic_threshold}). Entering Stage 2.")
                # Force switch if exceeded dynamic_max_iter without convergence
                if (not dynamic_switch_triggered) and (iteration >= dynamic_max_iter):
                    dynamic_switch_triggered = True
                    dynamic_switch_iter = iteration
                    dynamic_switch_forced = True
                    just_switched = True
                    print(f"\n[Dynamic Switch] Forced switch at iter {iteration} (>= dynamic_max_iter={dynamic_max_iter}). Entering Stage 2.")

            # Stage 1/2 flag
            if dynamic_stage:
                stage2_active = dynamic_switch_triggered
            else:
                stage2_active = iteration > stage_switch_iter
                if iteration == stage_switch_iter:
                    just_switched = True

            # Stage-based weighting
            if not stage2_active:
                total_loss = rgb_loss + dist_loss + normal_loss + lambda_lod_init * lod_depth_loss
                current_lod_weight = lambda_lod_init
                current_da_weight = 0.0
            else:
                # Dynamic DA depth weight update (only in stage2)
                if dynamic_da and (da_depth is not None):
                    da_loss_val = da_depth_loss.item() if isinstance(da_depth_loss, torch.Tensor) else float(da_depth_loss)
                    da_depth_history.append(da_loss_val)
                    if len(da_depth_history) > opt.depth_convergence_window:
                        da_depth_history.pop(0)

                    if da_phase == PHASE_INITIAL:
                        if len(da_depth_history) == opt.depth_convergence_window:
                            mid = opt.depth_convergence_window // 2
                            med_first = np.median(da_depth_history[:mid])
                            med_last = np.median(da_depth_history[mid:])
                            rel_change = abs(med_first - med_last) / max(med_first, 1e-6)
                            if rel_change < opt.depth_convergence_threshold:
                                da_phase = PHASE_CONVERGED
                                da_last_check = iteration
                                da_monitor_depth.clear()
                                da_monitor_rgb.clear()
                                print(f"\n[Dynamic DA] Converged at iter {iteration}: rel_change={rel_change:.4f} (<{opt.depth_convergence_threshold})")
                    elif da_phase == PHASE_CONVERGED:
                        da_monitor_depth.append(da_loss_val)
                        da_monitor_rgb.append(rgb_loss.item())
                        if len(da_monitor_depth) >= opt.depth_monitor_window:
                            da_phase = PHASE_DECAYING
                            print(f"[Dynamic DA] Monitoring window filled ({opt.depth_monitor_window}), start decay checks")
                    elif da_phase == PHASE_DECAYING:
                        da_monitor_depth.append(da_loss_val)
                        da_monitor_rgb.append(rgb_loss.item())
                        if len(da_monitor_depth) > opt.depth_monitor_window:
                            da_monitor_depth.pop(0)
                            da_monitor_rgb.pop(0)
                        if da_last_check is None:
                            da_last_check = iteration
                        if (iteration - da_last_check) >= opt.depth_decay_check_interval and len(da_monitor_depth) == opt.depth_monitor_window:
                            W = opt.depth_monitor_window
                            df = np.median(da_monitor_depth[: W // 2])
                            dl = np.median(da_monitor_depth[W // 2 :])
                            depth_trend = (dl - df) / max(df, 1e-8)

                            rf = np.median(da_monitor_rgb[: W // 2])
                            rl = np.median(da_monitor_rgb[W // 2 :])
                            rgb_trend = (rl - rf) / max(rf, 1e-8)

                            depth_guard_pass = depth_trend <= opt.depth_guard_threshold
                            rgb_improving = rgb_trend < opt.rgb_benefit_threshold
                            rgb_stable = rgb_trend <= opt.rgb_stable_threshold

                            if not depth_guard_pass:
                                da_phase = PHASE_LOCKED
                                da_locked_weight = da_weight
                                da_consecutive = 0
                                print(f"[Dynamic DA] Guard failed, lock at {da_locked_weight:.5f} (depth trend {depth_trend*100:+.2f}%)")
                            elif rgb_improving:
                                da_consecutive += 1
                                if da_consecutive >= opt.depth_hysteresis_count:
                                    new_w = max(da_weight * opt.depth_decay_factor, opt.depth_min_weight)
                                    print(f"[Dynamic DA] Decay: {da_weight:.5f}->{new_w:.5f}, depth {depth_trend*100:+.2f}%, RGB {rgb_trend*100:+.2f}%")
                                    da_weight = new_w
                                    da_consecutive = 0
                                    if da_weight <= opt.depth_min_weight:
                                        da_phase = PHASE_LOCKED
                                        da_locked_weight = da_weight
                                        print(f"[Dynamic DA] Reached min weight, locked at {da_weight:.5f}")
                                else:
                                    print(f"[Dynamic DA] Hysteresis {da_consecutive}/{opt.depth_hysteresis_count}, keep weight {da_weight:.5f}")
                            else:
                                da_consecutive = 0
                                if rgb_stable:
                                    print(f"[Dynamic DA] Maintain weight {da_weight:.5f} (depth safe, rgb stable)")
                                else:
                                    print(f"[Dynamic DA] Maintain weight {da_weight:.5f} (depth safe, rgb degrading)")
                            da_last_check = iteration
                    elif da_phase == PHASE_LOCKED:
                        if da_locked_weight is not None:
                            da_weight = da_locked_weight

                normal_loss = mvs_pgsr_control.geometry_loss(
                    viewpoint_cam, render_pkg, gaussians, pipe, background, iteration,
                    native_normal_loss=normal_loss)
                total_loss = rgb_loss + dist_loss + normal_loss
                if lod_depth is not None:
                    total_loss += lambda_lod_anchor * lod_depth_loss
                if da_depth is not None:
                    total_loss += (da_weight if dynamic_da else lambda_da_depth) * da_depth_loss
                current_lod_weight = lambda_lod_anchor
                current_da_weight = (da_weight if dynamic_da else lambda_da_depth) if da_depth is not None else 0.0

        mvs_pgsr_control.training_trace(
            iteration=iteration, camera=cam_name, prior_loss=lod_depth_loss,
            visual_loss=da_depth_loss, prior_weight=current_lod_weight,
            visual_weight=current_da_weight, geometry_loss=normal_loss,
            rgb_loss=rgb_loss)
        gaussians.optimizer.zero_grad(set_to_none=True)
        total_loss.backward()
        mvs_pgsr_control.after_backward(iteration, gaussians)
        if judgment is not None:  # [jbgs_judgment] remember locked rows before the Adam step
            judgment.before_step(gaussians)
        gaussians.optimizer.step()
        if judgment is not None:  # [jbgs_judgment] locked disks keep lock_lr_scale of the step; opacity floor
            judgment.after_step(gaussians)

        # Apply opacity floor protection for completed Gaussians
        if gaussians.completed_mask is not None and args.completion_opacity_floor > 0:
            with torch.no_grad():
                if gaussians.completed_mask.any():
                    # Convert opacity floor (0-1) to logit space
                    opacity_floor_logit = gaussians.inverse_opacity_activation(
                        torch.tensor(args.completion_opacity_floor, device="cuda")
                    ).item()
                    # Clamp completed Gaussian opacities to the floor
                    gaussians._opacity.data[gaussians.completed_mask] = torch.clamp(
                        gaussians._opacity.data[gaussians.completed_mask],
                        min=opacity_floor_logit
                    )

        iter_end.record()

        with torch.no_grad():
            # Progress bar
            ema_loss_for_log = 0.4 * rgb_loss.item() + 0.6 * ema_loss_for_log
            ema_dist_for_log = 0.4 * dist_loss.item() + 0.6 * ema_dist_for_log
            ema_normal_for_log = 0.4 * normal_loss.item() + 0.6 * ema_normal_for_log
            ema_lod_loss = 0.4 * lod_depth_loss.item() + 0.6 * ema_lod_loss
            ema_da_loss = 0.4 * da_depth_loss.item() + 0.6 * ema_da_loss

            if iteration % 10 == 0:
                loss_dict = {
                    "Loss": f"{ema_loss_for_log:.5f}",
                    "distort": f"{ema_dist_for_log:.5f}",
                    "normal": f"{ema_normal_for_log:.5f}",
                    "lod": f"{ema_lod_loss:.5f}",
                    "da": f"{ema_da_loss:.5f}",
                    "Points": f"{len(gaussians.get_xyz)}",
                }
                progress_bar.set_postfix(loss_dict)
                progress_bar.update(10)

            if iteration == opt.iterations:
                progress_bar.close()

            if tb_writer is not None:
                tb_writer.add_scalar("train_loss_patches/rgb_loss", ema_loss_for_log, iteration)
                tb_writer.add_scalar("train_loss_patches/dist_loss", ema_dist_for_log, iteration)
                tb_writer.add_scalar("train_loss_patches/normal_loss", ema_normal_for_log, iteration)
                tb_writer.add_scalar("dual_depth/lod_depth_loss", ema_lod_loss, iteration)
                tb_writer.add_scalar("dual_depth/da_depth_loss", ema_da_loss, iteration)
                if dynamic_da and da_depth is not None:
                    tb_writer.add_scalar("dual_depth/da_depth_weight", current_da_weight, iteration)

                if iteration == 1 or iteration % 100 == 0:
                    tb_writer.add_scalar("loss_weights/rgb_weight", 1.0, iteration)
                    tb_writer.add_scalar("loss_weights/lod_weight", current_lod_weight, iteration)
                    tb_writer.add_scalar("loss_weights/da_weight", current_da_weight, iteration)
                    tb_writer.add_scalar("loss_weights/dist_weight", lambda_dist, iteration)
                    tb_writer.add_scalar("loss_weights/normal_weight", lambda_normal_default, iteration)

            if judgment is not None:  # [jbgs_judgment] monitoring, read-outs, snapshots, dumps
                if iteration % args.jbgs_log_interval == 0 or iteration == 1:
                    judgment.log_scalars(iteration, dict(rgb=rgb_loss.item(), mvs=da_depth_loss.item(), prior=lod_depth_loss.item(),
                                                        normal=normal_loss.item(), dist=dist_loss.item(), total=total_loss.item(),
                                                        lambda_mvs=current_da_weight, lambda_prior=current_lod_weight), gaussians)
                _snap = iteration in args.jbgs_snapshot_iterations
                _dump = iteration in args.jbgs_dump_iterations
                if iteration % args.jbgs_readout_interval == 0 or _snap or _dump or iteration == opt.iterations:
                    judgment.readout(iteration, gaussians, render, pipe, background, snapshot=_snap, dump=_dump)

            training_report(
                tb_writer,
                iteration,
                Ll1,
                total_loss,
                l1_loss,
                iter_start.elapsed_time(iter_end),
                testing_iterations,
                scene,
                render,
                (pipe, background),
                txt_path=os.path.join(args.model_path, "metric.txt"),
            )

            if iteration in saving_iterations:
                print(f"\n[ITER {iteration}] Saving Gaussians")
                scene.save(iteration)

            # Densification
            densify_allowed = (iteration < opt.densify_until_iter) and (not freeze_done)
            if densify_allowed:
                gaussians.max_radii2D[visibility_filter] = torch.max(
                    gaussians.max_radii2D[visibility_filter], radii[visibility_filter]
                )
                gaussians.add_densification_stats(viewspace_point_tensor, visibility_filter)

                if iteration > opt.densify_from_iter and iteration % opt.densification_interval == 0:
                    size_threshold = 20 if iteration > opt.opacity_reset_interval else None
                    gaussians.densify_and_prune(opt.densify_grad_threshold, opt.opacity_cull, scene.cameras_extent, size_threshold)
                    # densify_and_prune replaces _xyz/_rotation/_scaling with new nn.Parameter objects,
                    # which destroys any previously registered gradient hooks. Re-apply attenuation so
                    # building Gaussians remain protected throughout Stage 2.
                    if building_freeze_mask is not None and gaussians.frozen_mask is not None and gaussians.frozen_mask.any():
                        attenuate_building_xyz_lr(gaussians, gaussians.frozen_mask, args.lod2_building_xyz_lr_scale)
                        if args.protect_bldg:
                            has_completed = gaussians.completed_mask is not None and gaussians.completed_mask.any()
                            if has_completed and args.completion_rotation_lr_scale != args.protect_bldg_lr_scale:
                                attenuate_building_rotation_differentiated(
                                    gaussians, gaussians.frozen_mask, gaussians.completed_mask,
                                    regular_scale=args.protect_bldg_lr_scale,
                                    completion_scale=args.completion_rotation_lr_scale
                                )
                                attenuate_building_other_lr(
                                    gaussians, gaussians.frozen_mask, args.protect_bldg_lr_scale,
                                    apply_rotation=False, apply_scaling=True
                                )
                            else:
                                attenuate_building_other_lr(
                                    gaussians, gaussians.frozen_mask, args.protect_bldg_lr_scale,
                                    apply_rotation=True, apply_scaling=True
                                )

                if iteration % opt.opacity_reset_interval == 0 or (dataset.white_background and iteration == opt.densify_from_iter):
                    gaussians.reset_opacity(exempt_mask=judgment.exempt_mask(gaussians) if judgment is not None else None)  # [jbgs_judgment]

            if iteration in checkpoint_iterations:
                print(f"\n[ITER {iteration}] Saving Checkpoint")
                torch.save((gaussians.capture(), iteration), scene.model_path + "/chkpnt" + str(iteration) + ".pth")

            # After Stage 1: match & attenuate/freeze building gaussians using LoD2 PCD
            if just_switched and (not freeze_done) and (lod2_pcd is not None):
                torch.cuda.synchronize()

                # ========== Step 1: Gaussian completion (optional) ==========
                if args.enable_gaussian_completion:
                    print(f"\n[ITER {iteration}] Step 1: Building Gaussian completion...")

                    # 1a. Forward matching: find existing building Gaussians
                    building_mask_temp = find_building_mask_from_pcd(
                        gaussians, lod2_pcd, args.lod2_match_thresh,
                        chunk_size=args.lod2_match_chunk
                    )

                    # 1b. Reverse matching: find uncovered LoD2 points
                    uncovered_mask = find_uncovered_lod2_points(
                        gaussians, lod2_pcd,
                        dist_thresh=args.completion_dist_thresh,
                        chunk_size=args.lod2_match_chunk
                    )

                    if uncovered_mask is not None and building_mask_temp is not None:
                        uncovered_points = lod2_pcd[uncovered_mask]
                        uncovered_normals = lod2_normals[uncovered_mask] if lod2_normals is not None else None
                        n_uncovered = uncovered_points.shape[0]

                        # Limit maximum completion count
                        if n_uncovered > args.completion_max_points:
                            indices = torch.randperm(n_uncovered, device=uncovered_points.device)[:args.completion_max_points]
                            uncovered_points = uncovered_points[indices]
                            if uncovered_normals is not None:
                                uncovered_normals = uncovered_normals[indices]

                        print(f"    Found {n_uncovered} uncovered LoD2 points, completing {uncovered_points.shape[0]}")

                        if uncovered_points.shape[0] > 0 and building_mask_temp.sum() > 0:
                            # Record start index before completion
                            completion_start_idx = gaussians.get_xyz.shape[0]

                            num_added = complete_building_gaussians(
                                gaussians, uncovered_points, building_mask_temp,
                                min_opacity=args.completion_min_opacity,
                                k_neighbors=args.completion_k_neighbors,
                                initial_opacity=args.completion_initial_opacity,
                                uncovered_normals=uncovered_normals,
                                scale_multiplier=args.completion_scale_multiplier
                            )
                            print(f"    Added {num_added} new Gaussians for building completion")

                            # Mark completed Gaussians using mask (auto-updates with prune)
                            if num_added > 0 and args.completion_opacity_floor > 0:
                                completion_end_idx = gaussians.get_xyz.shape[0]
                                gaussians.mark_completed_range(completion_start_idx, completion_end_idx)
                                print(f"    Marked completed Gaussians [{completion_start_idx}, {completion_end_idx}) for opacity floor protection")
                    else:
                        print("    Skipped: no uncovered points or no building Gaussians")
                # ========== End of completion ==========

                # Step 2: Re-match and freeze (new Gaussians will be included)
                print(f"\n[ITER {iteration}] {'Step 2: ' if args.enable_gaussian_completion else ''}Matching Gaussians to LoD2 PCD to freeze buildings...")
                building_freeze_mask = find_building_mask_from_pcd(
                    gaussians, lod2_pcd, args.lod2_match_thresh, chunk_size=args.lod2_match_chunk
                )
                if building_freeze_mask is not None:
                    attenuate_building_xyz_lr(gaussians, building_freeze_mask, args.lod2_building_xyz_lr_scale)
                    if args.protect_bldg:
                        # Apply differentiated rotation LR for completed Gaussians
                        has_completed = gaussians.completed_mask is not None and gaussians.completed_mask.any()
                        if has_completed and args.completion_rotation_lr_scale != args.protect_bldg_lr_scale:
                            attenuate_building_rotation_differentiated(
                                gaussians, building_freeze_mask, gaussians.completed_mask,
                                regular_scale=args.protect_bldg_lr_scale,
                                completion_scale=args.completion_rotation_lr_scale
                            )
                            # Scaling still uses uniform scale
                            attenuate_building_other_lr(
                                gaussians, building_freeze_mask, args.protect_bldg_lr_scale,
                                apply_rotation=False, apply_scaling=True
                            )
                        else:
                            attenuate_building_other_lr(
                                gaussians, building_freeze_mask, args.protect_bldg_lr_scale,
                                apply_rotation=True, apply_scaling=True
                            )
                    if args.freeze_onlybldg:
                        gaussians.set_frozen_mask(building_freeze_mask)
                        freeze_done = False
                    else:
                        gaussians.set_frozen_mask(None)
                        freeze_done = True
                else:
                    print("[Warning] Building freeze skipped (no LoD2 PCD or mask empty).")

        if jbgs_state.after_step(locals()):
            break

        with torch.no_grad():
            if network_gui.conn is None:
                network_gui.try_connect(dataset.render_items)
            while network_gui.conn is not None:
                try:
                    net_image_bytes = None
                    custom_cam, do_training, keep_alive, scaling_modifer, render_mode = network_gui.receive()
                    if custom_cam is not None:
                        render_pkg = render(custom_cam, gaussians, pipe, background, scaling_modifer)
                        net_image = render_net_image(render_pkg, dataset.render_items, render_mode, custom_cam)
                        net_image_bytes = memoryview(
                            (torch.clamp(net_image, min=0, max=1.0) * 255)
                            .byte()
                            .permute(1, 2, 0)
                            .contiguous()
                            .cpu()
                            .numpy()
                        )
                    metrics_dict = {"#": gaussians.get_opacity.shape[0], "loss": ema_loss_for_log}
                    network_gui.send(net_image_bytes, dataset.source_path, metrics_dict)
                    if do_training and ((iteration < int(opt.iterations)) or not keep_alive):
                        break
                except Exception:
                    network_gui.conn = None

    # Persist training summary
    summary_path = Path(args.model_path) / "training_lod.txt"
    try:
        with open(summary_path, "w") as f:
            f.write("Dual-depth Training Summary\n")
            f.write("---------------------------\n")
            f.write(f"Depth loss mode: {'scale-invariant' if args.use_scale_invariant else 'metric (direct L1)'}\n")
            f.write(f"Stage switch mode: {'dynamic' if dynamic_stage else 'fixed'}\n")
            if dynamic_stage:
                f.write(f"Dynamic params: window={dynamic_window}, threshold={dynamic_threshold}, check_interval={dynamic_check_interval}, min_iter={dynamic_min_iter}, max_iter={dynamic_max_iter}\n")
                f.write(f"Stage2 start iter: {dynamic_switch_iter if dynamic_switch_iter is not None else 'not triggered'}\n")
                if dynamic_switch_iter is not None and dynamic_switch_forced:
                    f.write("Stage2 start reason: forced by dynamic_max_iter\n")
                elif dynamic_switch_iter is not None:
                    f.write("Stage2 start reason: LoD2 loss convergence\n")
            else:
                f.write(f"Fixed stage switch iter: {stage_switch_iter}\n")
            f.write(f"Lambda LoD init: {lambda_lod_init}\n")
            f.write(f"Lambda LoD anchor: {lambda_lod_anchor}\n")
            f.write(f"Lambda DA depth: {lambda_da_depth}\n")
            f.write(f"Use confidence: {use_confidence}\n")
            f.write(f"LoD2 PCD path: {args.lod2_pcd_path if args.lod2_pcd_path else 'None'}\n")
            f.write(f"LoD2 match thresh: {args.lod2_match_thresh}\n")
            f.write(f"LoD2 match chunk: {args.lod2_match_chunk}\n")
            f.write(f"LoD2 building xyz lr scale: {args.lod2_building_xyz_lr_scale}\n")
            f.write(f"Protect building geometry (rotation/scale lr): {args.protect_bldg}, scale={args.protect_bldg_lr_scale}, completion_rotation={args.completion_rotation_lr_scale}\n")
            f.write(f"Densify stopped after switch: {freeze_done}\n")
            f.write(f"Freeze only building: {args.freeze_onlybldg}\n")
            f.write(f"Dynamic DA depth weight: {args.dynamic_depth_weight}\n")
            f.write(f"Gaussian completion enabled: {args.enable_gaussian_completion}\n")
            if args.enable_gaussian_completion:
                f.write(f"Completion dist thresh: {args.completion_dist_thresh}\n")
                f.write(f"Completion max points: {args.completion_max_points}\n")
                f.write(f"Completion min opacity: {args.completion_min_opacity}\n")
                f.write(f"Completion k neighbors: {args.completion_k_neighbors}\n")
                f.write(f"Completion initial opacity: {args.completion_initial_opacity}\n")
                f.write(f"Completion opacity floor: {args.completion_opacity_floor}\n")
                f.write(f"LoD2 normals available: {lod2_normals is not None}\n")
        print(f"[Info] Training summary saved to {summary_path}")
    except Exception as e:
        print(f"[Warning] Failed to save training summary: {e}")


if __name__ == "__main__":
    parser = ArgumentParser(description="Dual-depth training script (LoD2 anchor + DA3 refinement)")
    lp = ModelParams(parser)
    op = OptimizationParams(parser)
    pp = PipelineParams(parser)
    parser.add_argument("--ip", type=str, default="127.0.0.1")
    parser.add_argument("--port", type=int, default=6009)
    parser.add_argument("--detect_anomaly", action="store_true", default=False)
    parser.add_argument("--test_iterations", nargs="+", type=int, default=[8_000, 30_000])
    parser.add_argument("--save_iterations", nargs="+", type=int, default=[8_000, 30_000])
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--checkpoint_iterations", nargs="+", type=int, default=[])
    parser.add_argument("--start_checkpoint", type=str, default=None)

    # Dual-depth specific arguments
    parser.add_argument("--lod_depth_path", type=str, required=True, help="Path to coarse/LoD depth (dir with raw_depth)")
    parser.add_argument("--da_depth_path", type=str, required=True, help="Path to DA3 depth (dir with raw_depth)")
    parser.add_argument("--da_conf_path", type=str, default="", help="Path to DA3 confidence (raw_conf or parent dir)")
    parser.add_argument("--use_confidence", action="store_true", default=False, help="Enable DA3 confidence weighting")
    parser.add_argument("--use_scale_invariant", action="store_true", default=False,
                        help="Use scale-invariant depth loss (align pred to gt via median ratio). "
                             "Default is False for metric depth (LoD2/aligned DA3). "
                             "Set True only for unaligned monocular depth.")

    parser.add_argument("--stage_switch_iter", type=int, default=8000, help="Iteration to switch from Stage1 to Stage2")
    parser.add_argument("--lambda_lod_init", type=float, default=0.08, help="LoD depth weight during Stage1")
    parser.add_argument("--lambda_lod_anchor", type=float, default=0.005, help="LoD anchor weight during Stage2")
    parser.add_argument("--lambda_da_depth", type=float, default=0.05, help="DA3 depth weight during Stage2")

    # LoD2 PCD based building freeze
    parser.add_argument("--lod2_pcd_path", type=str, default="", help="Path to LoD2 point cloud (PLY) for building freeze")
    parser.add_argument("--lod2_max_points", type=int, default=1000000, help="Subsample LoD2 points for matching (None for all)")
    parser.add_argument("--lod2_match_thresh", type=float, default=0.2, help="Distance threshold (meters) to mark Gaussians as building")
    parser.add_argument("--lod2_match_chunk", type=int, default=10000, help="Chunk size for cdist during LoD2 matching (applied to both gaussians and LoD2)")
    parser.add_argument("--lod2_building_xyz_lr_scale", type=float, default=0.01, help="Scale factor for xyz gradient on building gaussians (1.0=no change)")
    parser.add_argument("--freeze_onlybldg", action="store_true", help="If set, only building gaussians stop densify/prune; otherwise stage2 stops densify/prune globally")
    parser.add_argument("--protect_bldg", action="store_true", help="Attenuate rotation/scale lr for building gaussians to preserve geometry")
    parser.add_argument("--protect_bldg_lr_scale", type=float, default=0.01, help="LR scale for rotation/scale when protect_bldg is enabled")

    # Gaussian completion arguments
    parser.add_argument("--enable_gaussian_completion", action="store_true",
        help="Enable building Gaussian completion at stage switch")
    parser.add_argument("--completion_dist_thresh", type=float, default=0.15,
        help="Distance threshold to consider LoD2 point covered (meters)")
    parser.add_argument("--completion_max_points", type=int, default=50000,
        help="Maximum number of Gaussians to add during completion")
    parser.add_argument("--completion_min_opacity", type=float, default=0.3,
        help="Minimum opacity for source Gaussians")
    parser.add_argument("--completion_k_neighbors", type=int, default=3,
        help="Number of nearest neighbors to inherit attributes from")
    parser.add_argument("--completion_initial_opacity", type=float, default=0.5,
        help="Initial opacity for new Gaussians (0-1)")
    parser.add_argument("--completion_opacity_floor", type=float, default=0.3,
        help="Minimum opacity floor for completed Gaussians (0-1). Set to 0 to disable.")
    parser.add_argument("--completion_rotation_lr_scale", type=float, default=0.1,
        help="LR scale for rotation of completed Gaussians (higher than protect_bldg_lr_scale to allow adjustment)")
    parser.add_argument("--completion_scale_multiplier", type=float, default=3.0,
        help="Scale multiplier for completion Gaussians (>1 makes them larger to improve coverage)")

    # Dynamic stage switch (optional)
    parser.add_argument("--dynamic_stage_switch", action="store_true", help="Enable dynamic stage switch based on LoD2 loss convergence")
    parser.add_argument("--dynamic_window", type=int, default=600, help="Window size for LoD2 loss convergence detection")
    parser.add_argument("--dynamic_threshold", type=float, default=0.015, help="Relative change threshold to declare LoD2 loss converged")
    parser.add_argument("--dynamic_check_interval", type=int, default=100, help="Check interval (iters) for dynamic switch")
    parser.add_argument("--dynamic_min_iter", type=int, default=3000, help="Minimum iter before allowing dynamic switch")
    parser.add_argument("--dynamic_max_iter", type=int, default=12000, help="Force stage switch if not converged by this iter")
    
    parser.add_argument("--dynamic_depth_weight", action="store_true", help="Enable dynamic DA3 depth weight (dual-gate control)")
    parser.add_argument("--lod_init", action="store_true", help="Use sparse_lod/0 instead of sparse/0 for COLMAP inputs")
    parser.add_argument("--sparse_dir_name", type=str, default="",
                        help="Override sparse directory name (overrides --lod_init default)")

    jbgs_state.register_args(parser)
    jbgs_judgment.register_args(parser)  # [jbgs_judgment]
    args = parser.parse_args(sys.argv[1:])
    jbgs_state.validate_args(args)
    args.save_iterations.append(args.iterations)

    # Initialize system state (RNG)
    safe_state(args.quiet)
    jbgs_judgment.apply_seed(args)  # [jbgs_judgment r12] --jbgs_seed (0 = safe_state's seed)

    # Start GUI server, configure and run training
    network_gui.init(args.ip, args.port)
    torch.autograd.set_detect_anomaly(args.detect_anomaly)

    # Extract default param groups then attach dual-depth config
    dataset = lp.extract(args)
    opt = op.extract(args)
    pipe = pp.extract(args)

    dataset.model_path = args.model_path
    dataset.lod_depth_path = args.lod_depth_path
    dataset.da_depth_path = args.da_depth_path
    dataset.da_conf_path = args.da_conf_path
    if args.sparse_dir_name:
        dataset.sparse_dir_name = args.sparse_dir_name
    else:
        dataset.sparse_dir_name = "sparse_lod" if args.lod_init else "sparse"

    training(dataset, opt, pipe, args, args.test_iterations, args.save_iterations, args.checkpoint_iterations, args.start_checkpoint)

    print("\nTraining complete.")
