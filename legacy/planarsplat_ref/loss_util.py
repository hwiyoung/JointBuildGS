import torch
import torch.nn as nn
import torch.nn.functional as F

def metric_depth_loss(depth_pred, depth_gt, mask, max_depth=4.0, weight=None, depth_scale=1.0):
    """Metric depth loss (MAE), optionally normalized by depth_scale.

    Args:
        depth_scale: normalizing constant (e.g., scene_bounding_sphere) to make
            the loss scale-invariant. Default 1.0 preserves original behavior.
    """
    depth_mask = torch.logical_and(depth_gt<=max_depth, depth_gt>0)
    depth_mask = torch.logical_and(depth_mask, mask)
    if depth_mask.sum() == 0:
        depth_loss = torch.tensor([0.]).mean().cuda()
    else:
        if weight is None:
            depth_loss = torch.mean(torch.abs((depth_pred - depth_gt)[depth_mask])) / depth_scale
        else:
            depth_loss = torch.mean((weight * torch.abs(depth_pred - depth_gt))[depth_mask]) / depth_scale
    return depth_loss

def normal_loss(normal_pred, normal_gt, mask):
    normal_pred = F.normalize(normal_pred, dim=-1)
    normal_gt = F.normalize(normal_gt, dim=-1)
    l1 = torch.abs(normal_pred - normal_gt).sum(dim=-1)[mask].mean()
    cos = (1. - torch.sum(normal_pred * normal_gt, dim=-1))[mask].mean()
    return l1, cos


# ==================== Phase 3-B': Photometric loss ====================

def photo_loss(rendered_rgb, gt_rgb, mask=None, lambda_ssim=0.2):
    """L_photo: L1 + SSIM photometric loss.

    Args:
        rendered_rgb: (3, H, W) rendered RGB image
        gt_rgb: (H*W, 3) or (3, H, W) ground truth RGB
        mask: (H*W,) valid pixel mask (optional)
        lambda_ssim: SSIM weight (default 0.2)

    Returns:
        loss scalar
    """
    H, W = rendered_rgb.shape[1], rendered_rgb.shape[2]

    # Normalize GT to [0, 1]
    if gt_rgb.dim() == 2:
        gt_img = gt_rgb.reshape(H, W, 3).permute(2, 0, 1)  # (3, H, W)
    else:
        gt_img = gt_rgb
    if gt_img.max() > 1.0:
        gt_img = gt_img / 255.0

    pred_img = rendered_rgb  # (3, H, W), already [0,1] from sigmoid

    if mask is not None:
        mask_2d = mask.reshape(H, W)
        # Apply mask: zero out invalid regions
        pred_masked = pred_img * mask_2d.unsqueeze(0)
        gt_masked = gt_img * mask_2d.unsqueeze(0)
    else:
        pred_masked = pred_img
        gt_masked = gt_img
        mask_2d = torch.ones(H, W, device=rendered_rgb.device, dtype=torch.bool)

    # L1 loss (only on valid pixels)
    n_valid = mask_2d.sum().clamp(min=1)
    l1 = (pred_masked - gt_masked).abs().sum() / (n_valid * 3)

    # SSIM loss (window-based, tolerates some masked regions)
    ssim_val = _ssim(pred_masked.unsqueeze(0), gt_masked.unsqueeze(0))

    loss = (1.0 - lambda_ssim) * l1 + lambda_ssim * (1.0 - ssim_val)
    return loss


def _ssim(img1, img2, window_size=11):
    """Compute SSIM between two (1, 3, H, W) images."""
    C1 = 0.01 ** 2
    C2 = 0.03 ** 2
    channel = img1.shape[1]

    # Gaussian window
    kernel_1d = torch.exp(-torch.arange(window_size, dtype=torch.float32, device=img1.device)
                          .sub(window_size // 2).pow(2) / (2 * 1.5 ** 2))
    kernel_1d = kernel_1d / kernel_1d.sum()
    kernel_2d = kernel_1d.unsqueeze(1) * kernel_1d.unsqueeze(0)
    window = kernel_2d.expand(channel, 1, window_size, window_size).contiguous()

    pad = window_size // 2
    mu1 = F.conv2d(img1, window, padding=pad, groups=channel)
    mu2 = F.conv2d(img2, window, padding=pad, groups=channel)

    mu1_sq = mu1 ** 2
    mu2_sq = mu2 ** 2
    mu1_mu2 = mu1 * mu2

    sigma1_sq = F.conv2d(img1 * img1, window, padding=pad, groups=channel) - mu1_sq
    sigma2_sq = F.conv2d(img2 * img2, window, padding=pad, groups=channel) - mu2_sq
    sigma12 = F.conv2d(img1 * img2, window, padding=pad, groups=channel) - mu1_mu2

    ssim_map = ((2 * mu1_mu2 + C1) * (2 * sigma12 + C2)) / \
               ((mu1_sq + mu2_sq + C1) * (sigma1_sq + sigma2_sq + C2))
    return ssim_map.mean()


# ==================== Phase 2-B: Semantic losses ====================

def semantic_loss(rendered_features, seg_gt, mask=None):
    """L_sem: CrossEntropyLoss with ignore_index=0 (background).

    Args:
        rendered_features: (C, H, W) raw alpha-blended features from rasterizer
        seg_gt: (H*W,) long tensor of class indices (0=bg, 1=roof, 2=wall, 3=ground)
        mask: optional (H*W,) bool mask for valid pixels

    Returns:
        loss scalar
    """
    C, H, W = rendered_features.shape
    # CrossEntropyLoss expects (N, C) logits, (N,) targets
    logits = rendered_features.permute(1, 2, 0).reshape(-1, C)  # (H*W, C)
    targets = seg_gt.reshape(-1)  # (H*W,)

    if mask is not None:
        logits = logits[mask]
        targets = targets[mask]

    if targets.numel() == 0:
        return torch.tensor(0., device=rendered_features.device, requires_grad=True)

    ce = F.cross_entropy(logits, targets, ignore_index=0, reduction='mean')
    return ce


# ==================== Phase 3-A: L_mutual ====================

def mutual_loss(semantic_features, plane_normals, e_gravity, tau=0.15, mode='full'):
    """L_mutual: bidirectional geometric-semantic consistency loss.

    Per-primitive loss encouraging consistency between semantic class
    probabilities (from f_i) and geometric normal orientations (from R_i).
    Operates directly at the primitive level (no rendering involved).

    Three geometric terms:
      - L_vert(n)  = (n . e_gravity)^2         -- 0 when horizontal (walls)
      - L_horiz(n) = (1 - |n . e_gravity|)^2   -- 0 when vertical (ground)
      - L_slope(n) = relu(tau - (n.e_gravity)^2)^2  -- one-sided wall exclusion (roofs)

    L_mutual = mean_i [ p_wall * L_vert + p_roof * L_slope + p_ground * L_horiz ]

    Args:
        semantic_features: (N, C) raw semantic logits, C=4 (bg/roof/wall/ground)
        plane_normals: (N, 3) per-primitive normal vectors in world frame
        e_gravity: (3,) gravity direction unit vector, e.g. [0, -1, 0]
        tau: threshold for L_slope (default 0.15)
        mode: 'full' -- bidirectional gradient (no detach)
              'sem2geo' -- detach softmax(f_i), only R_i gets gradient
              'geo2sem' -- detach n_i, only f_i gets gradient
              'none' -- returns zero (disabled)

    Returns:
        loss scalar
    """
    if mode == 'none':
        return torch.tensor(0., device=semantic_features.device, requires_grad=True)

    # Class probabilities: (N, C) where C=4 (bg=0, roof=1, wall=2, ground=3)
    p = F.softmax(semantic_features, dim=-1)
    p_roof = p[:, 1]
    p_wall = p[:, 2]
    p_ground = p[:, 3]

    if mode == 'sem2geo':
        # Only R_i gets gradient (semantics -> geometry direction)
        p_roof = p_roof.detach()
        p_wall = p_wall.detach()
        p_ground = p_ground.detach()

    # Per-primitive normal dot gravity
    n = F.normalize(plane_normals, dim=-1)
    if mode == 'geo2sem':
        # Only f_i gets gradient (geometry -> semantics direction)
        n = n.detach()

    dot = (n * e_gravity.to(n.device)).sum(dim=-1)  # (N,)

    # Geometric terms
    L_vert = dot ** 2                          # 0 when horizontal
    L_horiz = (1.0 - dot.abs()) ** 2           # 0 when vertical
    L_slope = F.relu(tau - dot ** 2) ** 2      # one-sided wall exclusion

    # Weighted sum per primitive, mean over all primitives
    loss = (p_wall * L_vert + p_roof * L_slope + p_ground * L_horiz).mean()

    return loss


def prim_normal_loss(plane_normals, plane_centers, gt_normals_map, gt_depth_map,
                     intrinsic, c2w, img_h, img_w):
    """L_prim_normal: per-primitive normal supervision.

    Projects each primitive center to its view, samples the GT normal at that pixel,
    and compares with the primitive's 3D normal. Operates at primitive level, not
    rendering level — directly constrains individual primitive normals.

    Args:
        plane_normals: (N, 3) differentiable primitive normals (world frame)
        plane_centers: (N, 3) primitive centers (world frame)
        gt_normals_map: (H*W, 3) GT normals in world frame
        gt_depth_map: (H*W,) GT depth
        intrinsic: (3, 3) or (4, 4) camera intrinsic
        c2w: (4, 4) camera-to-world matrix
        img_h, img_w: image dimensions

    Returns:
        loss scalar, n_valid (number of primitives with valid projection)
    """
    N = plane_normals.shape[0]
    device = plane_normals.device

    # World → camera: w2c = c2w.inverse()
    w2c = torch.inverse(c2w)
    R_w2c = w2c[:3, :3]
    t_w2c = w2c[:3, 3]

    # Project primitive centers to camera space
    centers_cam = (R_w2c @ plane_centers.T + t_w2c.unsqueeze(1)).T  # (N, 3)
    z_cam = centers_cam[:, 2]

    # Filter: must be in front of camera
    valid = z_cam > 0.1

    # Project to pixel coordinates
    K = intrinsic[:3, :3]
    centers_pix = (K @ centers_cam[valid].T).T  # (M, 3)
    u = (centers_pix[:, 0] / centers_pix[:, 2]).long()
    v = (centers_pix[:, 1] / centers_pix[:, 2]).long()

    # Filter: must be within image bounds
    in_bounds = (u >= 0) & (u < img_w) & (v >= 0) & (v < img_h)

    if in_bounds.sum() == 0:
        return torch.tensor(0., device=device, requires_grad=True), 0

    u_valid = u[in_bounds]
    v_valid = v[in_bounds]
    pix_idx = v_valid * img_w + u_valid

    # Get GT normal at projected pixels
    gt_n = gt_normals_map[pix_idx]  # (M', 3)
    gt_depth = gt_depth_map[pix_idx]  # (M',)

    # Filter: GT must be valid (non-zero normal and depth)
    gt_valid = (gt_n.abs().sum(dim=-1) > 0.1) & (gt_depth.abs() > 0)
    if gt_valid.sum() == 0:
        return torch.tensor(0., device=device, requires_grad=True), 0

    # Get corresponding primitive normals
    valid_indices = torch.where(valid)[0][in_bounds][gt_valid]
    prim_n = plane_normals[valid_indices]  # (K, 3)
    gt_n_valid = gt_n[gt_valid]  # (K, 3)

    # Normalize
    prim_n = F.normalize(prim_n, dim=-1)
    gt_n_valid = F.normalize(gt_n_valid, dim=-1)

    # Cosine loss: 1 - |cos(angle)| to handle normal direction ambiguity
    cos_sim = (prim_n * gt_n_valid).sum(dim=-1).abs()
    loss = (1.0 - cos_sim).mean()

    return loss, int(gt_valid.sum().item())


def multi_view_consistency_loss(depth_src, normal_src, intrinsic_src, c2w_src,
                                 depth_ref, normal_ref, intrinsic_ref, c2w_ref,
                                 img_h, img_w):
    """L_mvc: Multi-view depth and normal consistency loss.

    Reprojects pixels from source view to reference view via depth unproject,
    then compares the reprojected depth/normal with reference rendered values.
    Penalizes inconsistency between views — forces primitives to converge to
    positions/orientations consistent across multiple viewpoints.

    Based on ULSR-GS (Li et al., ISPRS 2025) geometric consistency loss.

    Args:
        depth_src: (H, W) rendered depth from source view
        normal_src: (H, W, 3) rendered normal in world frame from source view
        intrinsic_src: (3,3) or (4,4) source camera intrinsic
        c2w_src: (4,4) source camera-to-world
        depth_ref: (H, W) rendered depth from reference view
        normal_ref: (H, W, 3) rendered normal in world frame from reference view
        intrinsic_ref: (3,3) or (4,4) reference camera intrinsic
        c2w_ref: (4,4) reference camera-to-world
        img_h, img_w: image dimensions

    Returns:
        loss scalar
    """
    H, W = img_h, img_w
    device = depth_src.device

    # Source valid mask
    src_valid = depth_src > 0.1

    if src_valid.sum() < 100:
        return torch.tensor(0., device=device, requires_grad=True)

    # Pixel grid
    v_coords, u_coords = torch.meshgrid(
        torch.arange(H, device=device, dtype=torch.float32),
        torch.arange(W, device=device, dtype=torch.float32), indexing='ij')

    # Unproject source pixels to 3D world coords
    K_src = intrinsic_src[:3, :3]
    fx_s, fy_s = K_src[0, 0], K_src[1, 1]
    cx_s, cy_s = K_src[0, 2], K_src[1, 2]

    d_s = depth_src[src_valid]
    u_s = u_coords[src_valid]
    v_s = v_coords[src_valid]

    x_cam = (u_s - cx_s) / fx_s * d_s
    y_cam = (v_s - cy_s) / fy_s * d_s
    z_cam = d_s
    pts_cam = torch.stack([x_cam, y_cam, z_cam, torch.ones_like(d_s)], dim=-1)
    pts_world = (c2w_src @ pts_cam.T).T[:, :3]  # (M, 3)

    # Project to reference view
    w2c_ref = torch.inverse(c2w_ref)
    pts_ref_cam = (w2c_ref[:3, :3] @ pts_world.T + w2c_ref[:3, 3:4]).T  # (M, 3)
    z_ref = pts_ref_cam[:, 2]

    # Filter: in front of reference camera
    front = z_ref > 0.1
    if front.sum() < 100:
        return torch.tensor(0., device=device, requires_grad=True)

    K_ref = intrinsic_ref[:3, :3]
    u_ref = (K_ref[0, 0] * pts_ref_cam[front, 0] / z_ref[front] + K_ref[0, 2]).long()
    v_ref = (K_ref[1, 1] * pts_ref_cam[front, 1] / z_ref[front] + K_ref[1, 2]).long()

    # Filter: within image bounds
    in_bounds = (u_ref >= 0) & (u_ref < W) & (v_ref >= 0) & (v_ref < H)
    if in_bounds.sum() < 100:
        return torch.tensor(0., device=device, requires_grad=True)

    u_valid = u_ref[in_bounds]
    v_valid = v_ref[in_bounds]
    z_expected = z_ref[front][in_bounds]  # depth we expect in ref view

    # Get reference rendered depth at these pixels
    z_ref_rendered = depth_ref[v_valid, u_valid]

    # Filter: reference has valid depth
    ref_valid = z_ref_rendered > 0.1
    if ref_valid.sum() < 50:
        return torch.tensor(0., device=device, requires_grad=True)

    # Depth consistency: |expected_depth - rendered_depth| / max(expected, rendered)
    z_exp = z_expected[ref_valid]
    z_ren = z_ref_rendered[ref_valid]
    depth_consistency = torch.abs(z_exp - z_ren) / torch.max(z_exp, z_ren).clamp(min=1.0)

    # Filter outliers (occlusion): only penalize if relative error < threshold
    inlier = depth_consistency < 0.1  # within 10% relative depth
    if inlier.sum() < 10:
        return torch.tensor(0., device=device, requires_grad=True)

    loss_depth = depth_consistency[inlier].mean()

    # Normal consistency (optional, if normals available)
    if normal_src is not None and normal_ref is not None:
        # Get source normals at valid pixels
        src_indices = torch.where(src_valid.reshape(-1))[0]
        front_indices = src_indices[front][in_bounds][ref_valid][inlier]
        n_src_valid = normal_src.reshape(-1, 3)[front_indices]
        n_ref_valid = normal_ref[v_valid[ref_valid][inlier], u_valid[ref_valid][inlier]]

        n_src_norm = F.normalize(n_src_valid, dim=-1)
        n_ref_norm = F.normalize(n_ref_valid, dim=-1)

        # Only compare where both normals are valid
        both_valid = (n_src_norm.abs().sum(-1) > 0.1) & (n_ref_norm.abs().sum(-1) > 0.1)
        if both_valid.sum() > 10:
            loss_normal = (1.0 - (n_src_norm[both_valid] * n_ref_norm[both_valid]).sum(dim=-1).abs()).mean()
            loss = loss_depth + 0.5 * loss_normal
        else:
            loss = loss_depth
    else:
        loss = loss_depth

    return loss


def normal_consistency_loss(depth, normal_rendered, intrinsic, mask=None):
    """L_geo (L_normal_consistency): rendered normal vs depth-derived normal.

    Computes normals from depth via finite difference, then compares with
    rendered normals. Excludes depth discontinuity edges (large depth gradient).

    Based on 2DGS/PGSR standard implementation.

    Args:
        depth: (H, W) rendered depth map
        normal_rendered: (H, W, 3) rendered normal in camera frame
        intrinsic: (3, 3) or (4, 4) camera intrinsic matrix
        mask: optional (H, W) bool mask

    Returns:
        loss scalar
    """
    H, W = depth.shape
    device = depth.device

    # Unproject depth to 3D points in camera frame
    fx = intrinsic[0, 0]
    fy = intrinsic[1, 1]
    cx = intrinsic[0, 2]
    cy = intrinsic[1, 2]

    v, u = torch.meshgrid(torch.arange(H, device=device, dtype=torch.float32),
                           torch.arange(W, device=device, dtype=torch.float32), indexing='ij')
    x = (u - cx) / fx * depth
    y = (v - cy) / fy * depth
    points = torch.stack([x, y, depth], dim=-1)  # (H, W, 3)

    # Finite difference normals
    # dx = points[i, j+1] - points[i, j-1], dy = points[i+1, j] - points[i-1, j]
    dx = torch.zeros_like(points)
    dy = torch.zeros_like(points)
    dx[:, 1:-1] = points[:, 2:] - points[:, :-2]
    dy[1:-1, :] = points[2:, :] - points[:-2, :]

    normal_derived = torch.cross(dx, dy, dim=-1)  # (H, W, 3)
    normal_derived = F.normalize(normal_derived, dim=-1)

    # Depth discontinuity mask: exclude edges where depth changes rapidly
    depth_grad_x = torch.zeros_like(depth)
    depth_grad_y = torch.zeros_like(depth)
    depth_grad_x[:, 1:-1] = (depth[:, 2:] - depth[:, :-2]).abs()
    depth_grad_y[1:-1, :] = (depth[2:, :] - depth[:-2, :]).abs()
    depth_grad = torch.max(depth_grad_x, depth_grad_y)
    # Threshold: relative to local depth (2DGS convention)
    edge_mask = depth_grad < (depth * 0.05)

    # Valid mask: combine with input mask, exclude borders, require positive depth
    valid = (depth > 0.01) & edge_mask
    valid[:1, :] = False
    valid[-1:, :] = False
    valid[:, :1] = False
    valid[:, -1:] = False
    if mask is not None:
        valid = valid & mask

    if valid.sum() == 0:
        return torch.tensor(0., device=device, requires_grad=True)

    # Normal consistency: 1 - dot(n_render, n_derived)
    normal_r = F.normalize(normal_rendered, dim=-1)
    cos_sim = (normal_r * normal_derived).sum(dim=-1)
    loss = (1.0 - cos_sim)[valid].mean()
    return loss