"""Conditional prior-surface 2D Gaussian reconstruction development solver.

Source trust regions are declared solver controls, never current-use certificates.
No reference geometry is accepted by this module.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
import numpy as np
import torch
from torch import nn
from torch.nn import functional as F
from scipy.spatial import cKDTree
from scipy.ndimage import binary_erosion, distance_transform_edt
from src.stage2.model import quaternion_from_positive_z_normals, quat_to_rotmat
from src.stage2.renderer import render
from src.stage2.loss.data_fitting import l_photo
from gsplat import rasterization_2dgs


def prepare_geometry(xyz, normals, patch, native_rows, unit, cfg):
    """Keep source membership, construct local affine gauges and spacing controls."""
    xyz, normals = np.asarray(xyz, np.float32), np.asarray(normals, np.float32).copy()
    good = np.isfinite(xyz).all(1) & np.isfinite(normals).all(1)
    good &= np.linalg.norm(normals, axis=1) > 1e-5
    rows = np.flatnonzero(good)
    spacing = float(cfg["seed_voxel_m"])
    if spacing > 0:
        key = np.column_stack((patch[rows], np.floor(xyz[rows] / spacing).astype(np.int64)))
        _, keep = np.unique(key, axis=0, return_index=True)
        rows = rows[np.sort(keep)]
    xyz, normals = xyz[rows], normals[rows]
    normals /= np.linalg.norm(normals, axis=1, keepdims=True)
    normals[normals[:, 2] < 0] *= -1
    key = np.column_stack((patch[rows], np.floor(xyz / cfg["structure_cell_m"]).astype(np.int64)))
    _, group = np.unique(key, axis=0, return_inverse=True)
    H = np.zeros((len(xyz), 3), np.float32)
    group_count = int(group.max()) + 1
    pinv = np.zeros((group_count, 3, 3), np.float32)
    scale = np.zeros(len(xyz), np.float32)
    residual = np.zeros(group_count, np.float32)
    group_counts = np.bincount(group)
    for g in range(group_count):
        ii = np.flatnonzero(group == g)
        points = xyz[ii]
        mean_normal = normals[ii].mean(0)
        mean_normal /= np.linalg.norm(mean_normal)
        ref = np.array([1., 0, 0]) if abs(mean_normal[0]) < .9 else np.array([0., 1, 0])
        tangent = np.cross(mean_normal, ref); tangent /= np.linalg.norm(tangent)
        bitangent = np.cross(mean_normal, tangent)
        local = points - points.mean(0)
        H[ii, 0] = 1
        H[ii, 1] = local @ tangent / cfg["structure_cell_m"]
        H[ii, 2] = local @ bitangent / cfg["structure_cell_m"]
        pinv[g] = np.linalg.pinv(H[ii].T @ H[ii], rcond=1e-5)
        residual[g] = np.sqrt(np.mean((local @ mean_normal) ** 2))
    # Source-local neighborhoods cannot bridge unrelated native patches.
    for p in np.unique(patch[rows]):
        ii = np.flatnonzero(patch[rows] == p)
        if len(ii) >= 4:
            distances, _ = cKDTree(xyz[ii]).query(xyz[ii], k=4)
            scale[ii] = np.median(distances[:, 1:], axis=1) * cfg["scale_spacing_factor"]
        else:
            scale[ii] = cfg["minimum_scale_m"]
    scale = np.clip(scale, cfg["minimum_scale_m"], cfg["maximum_scale_m"])
    return dict(xyz=xyz, normals=normals, scale=scale, group=group.astype(np.int64),
                H=H, gram_pinv=pinv, group_counts=group_counts, plane_residual_m=residual,
                seed_id=rows, native_row=np.asarray(native_rows)[rows], unit_index=np.asarray(unit)[rows],
                native_patch_id=np.asarray(patch)[rows], original_input_count=np.array(len(good)))


def quat_product(a, b):
    aw, av = a[..., :1], a[..., 1:]
    bw, bv = b[..., :1], b[..., 1:]
    return torch.cat((aw * bw - (av * bv).sum(-1, keepdim=True),
                      aw * bv + bw * av + torch.cross(av, bv, dim=-1)), -1)


def subdivide_seed(seed, cfg):
    """Four fixed tangent children inside each original Gaussian footprint.

    This creates representation samples, not additional native observations.
    Parent source identity is retained, and no optimization result drives it.
    """
    normals=torch.as_tensor(seed["normals"])
    frames=quat_to_rotmat(quaternion_from_positive_z_normals(normals)).numpy()
    signs=np.array([[-1,-1],[-1,1],[1,-1],[1,1]],np.float32)
    offsets=np.einsum("nci,ki->nkc",frames[:,:,:2],signs)*seed["scale"][:,None,None]*.5
    xyz=(seed["xyz"][:,None,:]+offsets).reshape(-1,3)
    dense=prepare_geometry(xyz,np.repeat(seed["normals"],4,axis=0),
        np.repeat(seed["native_patch_id"],4),np.repeat(seed["native_row"],4),np.repeat(seed["unit_index"],4),
        dict(cfg,seed_voxel_m=0))
    dense["scale"]=np.repeat(seed["scale"]*.5,4)
    dense["parent_id"]=np.repeat(seed["seed_id"],4)
    dense["interpolated"]=np.ones(len(xyz),np.uint8)
    dense["native_input_count"]=seed["original_input_count"]
    return dense


class StructuredGaussians(nn.Module):
    active_sh_degree = 0

    def __init__(self, seed, cfg, device="cuda"):
        super().__init__()
        self.cfg = cfg
        for key in ["xyz", "normals", "H", "gram_pinv", "scale"]:
            self.register_buffer("base" if key == "xyz" else key,
                                 torch.as_tensor(seed[key], dtype=torch.float32, device=device))
        self.register_buffer("group", torch.as_tensor(seed["group"], dtype=torch.long, device=device))
        self.register_buffer("counts", torch.as_tensor(seed["group_counts"], dtype=torch.float32, device=device))
        self.register_buffer("q0", quaternion_from_positive_z_normals(self.normals))
        self.register_buffer("observations", torch.zeros(len(self.base), device=device))
        self.register_buffer("observable", torch.ones(len(self.base), device=device))
        self.register_buffer("detail_bound", (self.scale * cfg["detail_spacing_factor"]).clamp(
            cfg["minimum_detail_bound_m"], cfg["maximum_detail_bound_m"]))
        self.structure = nn.Parameter(torch.zeros((len(self.counts), 3, 3), device=device))
        self.detail = nn.Parameter(torch.zeros_like(self.base))
        self.rotation = nn.Parameter(torch.zeros_like(self.base))
        self.log_scales = nn.Parameter(self.scale.log()[:, None].repeat(1, 2))
        self.opacity_raw = nn.Parameter(torch.full((len(self.base),),
            float(np.log(cfg["initial_opacity"] / (1 - cfg["initial_opacity"]))), device=device))
        self.sh0 = nn.Parameter(torch.zeros((len(self.base), 1, 3), device=device))

    def project_detail(self, raw):
        # Zero low-order moments on observable points; unsupported points stay zero.
        value = raw * self.observable[:, None]
        moments = torch.zeros((len(self.counts), 3, 3), device=raw.device, dtype=raw.dtype)
        moments.index_add_(0, self.group, self.H[:, :, None] * value[:, None, :])
        coefficients = torch.bmm(self.gram_pinv, moments)
        return value - torch.einsum("ni,nij->nj", self.H, coefficients[self.group]) * self.observable[:, None]

    def coarse_displacement(self):
        return torch.einsum("ni,nij->nj", self.H, self.structure[self.group])

    @property
    def means(self):
        return self.base + self.coarse_displacement() + self.project_detail(self.detail)

    @property
    def quats(self):
        vector = self.rotation * self.observable[:, None]
        angle = torch.linalg.vector_norm(vector, dim=1, keepdim=True)
        # sinc avoids the zero-angle derivative singularity.
        delta = torch.cat((torch.cos(angle / 2), vector * .5 * torch.sinc(angle / (2 * torch.pi))), 1)
        return F.normalize(quat_product(delta, self.q0), dim=-1)

    @property
    def scales(self):
        return torch.cat((self.log_scales.exp(), torch.full_like(self.log_scales[:, :1], 1e-6)), 1)

    @property
    def opacities(self):
        return self.opacity_raw.sigmoid()

    def colors_sh(self):
        return self.sh0

    @torch.no_grad()
    def set_observations(self, counts):
        self.observations.copy_(torch.as_tensor(counts, device=self.base.device))
        self.observable.copy_((self.observations >= self.cfg["minimum_detail_views"]).float())
        grams = torch.zeros_like(self.gram_pinv)
        grams.index_add_(0, self.group, self.H[:, :, None] * self.H[:, None, :] * self.observable[:, None, None])
        self.gram_pinv.copy_(torch.linalg.pinv(grams, rtol=1e-5))

    def coarse_rotation(self):
        value = torch.zeros((len(self.counts), 3), device=self.base.device)
        value.index_add_(0, self.group, self.rotation * self.observable[:, None])
        observed = torch.zeros_like(self.counts)
        observed.index_add_(0, self.group, self.observable)
        return value / observed[:, None].clamp_min(1)

    def prior_loss(self):
        coarse = self.coarse_displacement()
        position = F.smooth_l1_loss(coarse / self.cfg["structure_translation_bound_m"], torch.zeros_like(coarse), beta=1.)
        r = self.coarse_rotation() / np.deg2rad(self.cfg["structure_rotation_bound_deg"])
        orientation = F.smooth_l1_loss(r, torch.zeros_like(r), beta=1.)
        return position + orientation

    @torch.no_grad()
    def enforce_domain(self, structured):
        """Projected Adam step; nonzero feasible steps survive. Counts are explicit."""
        before = self.means.detach().clone()
        coarse = self.coarse_displacement()
        maximum = torch.zeros(len(self.counts), device=self.base.device)
        maximum.scatter_reduce_(0, self.group, coarse.norm(dim=1), reduce="amax", include_self=True)
        limit = self.cfg["structure_translation_bound_m"] if structured else self.cfg["unconstrained_domain_m"]
        factor = (limit / maximum.clamp_min(1e-8)).clamp(max=1.)
        self.structure.mul_(factor[:, None, None])
        detail = self.project_detail(self.detail)
        ratio = detail.norm(dim=1) / self.detail_bound
        group_ratio = torch.ones(len(self.counts), device=self.base.device)
        group_ratio.scatter_reduce_(0, self.group, ratio, reduce="amax", include_self=True)
        self.detail.div_(group_ratio[self.group, None])
        self.detail.mul_(self.observable[:, None])
        r = self.coarse_rotation()
        angular_bound = np.deg2rad(self.cfg["structure_rotation_bound_deg"] if structured else self.cfg["normal_domain_deg"])
        rf = (angular_bound / r.norm(dim=1).clamp_min(1e-8)).clamp(max=1.)
        self.rotation.sub_((r * (1 - rf[:, None]))[self.group])
        angle = self.rotation.norm(dim=1, keepdim=True)
        self.rotation.mul_((np.deg2rad(self.cfg["normal_domain_deg"]) / angle.clamp_min(1e-8)).clamp(max=1))
        self.rotation.mul_(self.observable[:, None])
        # Per-point clipping can move the group mean; final uniform contraction
        # satisfies both convex bounds, including partially observed groups.
        mean_after = self.coarse_rotation()
        final_rf = (angular_bound / mean_after.norm(dim=1).clamp_min(1e-8)).clamp(max=1.)
        self.rotation.mul_(final_rf[self.group, None])
        base_log = self.scale.log()[:, None]
        self.log_scales.copy_(torch.maximum(torch.minimum(self.log_scales, base_log + np.log(self.cfg["scale_max_ratio"])),
                                            base_log + np.log(self.cfg["scale_min_ratio"])))
        self.opacity_raw.clamp_(float(np.log(.05 / .95)), float(np.log(.995 / .005)))
        self.sh0.clamp_(-.5 / .28209479177387814, .5 / .28209479177387814)
        if not all(bool(torch.isfinite(p).all()) for p in self.parameters()):
            raise FloatingPointError("nonfinite projected parameter; do not repair silently")
        return {"coarse_projected_groups": int((factor < 1).sum()), "detail_projected_groups": int((group_ratio > 1).sum()),
                "rotation_projected_groups": int((rf < 1).sum()),
                "projection_correction_m_mean": float((self.means - before).norm(dim=1).mean())}

    @torch.no_grad()
    def state_arrays(self, seed):
        state = dict(xyz=self.means, scales=self.scales, quats=self.quats, opacity=self.opacities,
                     rgb=(self.sh0[:, 0] * .28209479177387814 + .5).clamp(0, 1), group=self.group,
                     sh0=self.sh0,
                     detail_displacement=self.project_detail(self.detail), coarse_displacement=self.coarse_displacement(),
                     observation_count=self.observations, normals=quat_to_rotmat(self.quats)[:, :, 2])
        result = {k: v.detach().cpu().numpy() for k, v in state.items()}
        for key in ["seed_id", "native_row", "unit_index", "native_patch_id"]:
            result[key] = seed[key]
        for key in ["parent_id", "interpolated"]:
            if key in seed: result[key]=seed[key]
        return result

    @torch.no_grad()
    def dof_metrics(self):
        detail, coarse = self.project_detail(self.detail), self.coarse_displacement()
        return {"coarse_displacement_max_m": float(coarse.norm(dim=1).max()),
                "coarse_displacement_rms_m": float(coarse.square().sum(1).mean().sqrt()),
                "detail_displacement_max_m": float(detail.norm(dim=1).max()),
                "detail_displacement_rms_m": float(detail.square().sum(1).mean().sqrt()),
                "detail_nonzero_gt1mm_count": int((detail.norm(dim=1) > .001).sum()),
                "rotation_mean_deg": float(self.rotation.norm(dim=1).mean() * 180 / torch.pi),
                "rotation_max_deg": float(self.rotation.norm(dim=1).max() * 180 / torch.pi),
                "scale_relative_change_mean": float((self.log_scales.exp() / self.scale[:, None] - 1).abs().mean()),
                "opacity_change_mean": float((self.opacities - self.cfg["initial_opacity"]).abs().mean()),
                "observable_seed_count": int(self.observable.sum())}


@dataclass
class View:
    image_id: int
    role: str
    image: torch.Tensor
    valid: torch.Tensor
    K: torch.Tensor
    viewmat: torch.Tensor
    width: int
    height: int
    provenance: dict
    mask: torch.Tensor | None = None
    initial_depth: torch.Tensor | None = None
    context_depth: torch.Tensor | None = None
    foreground: torch.Tensor | None = None
    source_mask: torch.Tensor | None = None
    rgb_source_mask: torch.Tensor | None = None


def render_view(model, view):
    if os.environ.get("JBGS_P2_GEOMETRY_ADAPTER")!="c4_c8_v1":
        raise RuntimeError("Corrected v2 requires the audited independent C4/C8 geometry adapter")
    out = render(model, view.viewmat, view.K, view.width, view.height, sh_degree=0,
                 render_mode="RGB+ED", bg_color=torch.zeros(3, device=model.base.device),
                 surface_normal_depth_mode="gsplat_expected")
    geometry=rasterization_2dgs(means=model.means,quats=model.quats,scales=model.scales,
        opacities=model.opacities,colors=torch.zeros((len(model.base),8),device=model.base.device),
        viewmats=view.viewmat[None],Ks=view.K[None],width=view.width,height=view.height,
        sh_degree=None,render_mode="RGB",near_plane=.01,far_plane=1e10)
    out["depth_center_expected"] = out["depth"]
    out["geometry_mass"]=geometry[1][0,...,0]
    out["geometry_depth_sum"]=geometry[5][0,...,0]
    mass=out["geometry_mass"]
    out["depth"]=torch.where(mass>1e-8,out["geometry_depth_sum"]/mass.clamp_min(1e-8),torch.zeros_like(mass))
    out["normal_rgb"]=out["normal_render"]
    out["normal_render"]=geometry[2][0]
    # The generic historical helper uses integer pixels. This v2 path matches
    # the gsplat CUDA pixel centers (+0.5) used for intersection and extraction.
    v,u=torch.meshgrid(torch.arange(view.height,device=model.base.device,dtype=torch.float32),
                       torch.arange(view.width,device=model.base.device,dtype=torch.float32),indexing="ij")
    rays=torch.stack((u+.5,v+.5,torch.ones_like(u)),dim=-1) @ torch.linalg.inv(view.K).T
    points=rays*out["depth"][...,None]
    dx=points[:-1,1:]-points[:-1,:-1];dy=points[1:,:-1]-points[:-1,:-1]
    normal=F.normalize(torch.cross(dx,dy,dim=-1),dim=-1,eps=1e-6)
    normal=torch.cat((normal,normal[:,-1:]),dim=1);normal=torch.cat((normal,normal[-1:]),dim=0)
    out["normal_surf"]=normal @ view.viewmat[:3,:3]
    return out


def crop_view(view, xy, dimension):
    width, height = min(dimension, view.width), min(dimension, view.height)
    x = min(max(int(xy[0] - width // 2), 0), view.width - width)
    y = min(max(int(xy[1] - height // 2), 0), view.height - height)
    K = view.K.clone(); K[0, 2] -= x; K[1, 2] -= y
    return View(view.image_id, view.role, view.image[y:y+height, x:x+width], view.valid[y:y+height, x:x+width],
                K, view.viewmat, width, height, dict(view.provenance, tile_xywh=[x,y,width,height]),
                view.mask[y:y+height, x:x+width] if view.mask is not None else None,
                view.initial_depth[y:y+height, x:x+width] if view.initial_depth is not None else None)


def normal_consistency(out, mask):
    # Interior support avoids finite differences across explicit missing pixels.
    geometric_support=mask & (out["geometry_mass"].detach()>.5) & (out["depth"].detach()>0)
    interior = F.avg_pool2d(geometric_support.float()[None, None], 3, stride=1, padding=1)[0, 0] > .999
    d = out["depth"].detach()
    discontinuity = torch.zeros_like(d, dtype=torch.bool)
    discontinuity[1:] |= (d[1:] - d[:-1]).abs() > .5
    discontinuity[:, 1:] |= (d[:, 1:] - d[:, :-1]).abs() > .5
    valid = interior & ~discontinuity & (out["geometry_mass"].detach() > .5)
    valid &= (out["normal_render"].detach().norm(dim=-1)>1e-5)&(out["normal_surf"].detach().norm(dim=-1)>1e-5)
    nr, ns = F.normalize(out["normal_render"], dim=-1), F.normalize(out["normal_surf"], dim=-1)
    error = 1 - (nr * ns).sum(-1).abs().clamp(max=1)
    return error[valid].mean() if bool(valid.any()) else error.sum() * 0


def multiview_loss(source, out, target, reference, stride=4):
    """Train-view reprojection geometry and image warp; no independent evidence."""
    v, u = torch.meshgrid(torch.arange(0, source.height, stride, device=source.K.device),
                          torch.arange(0, source.width, stride, device=source.K.device), indexing="ij")
    z = out["depth"][v, u]
    rays = torch.stack((u + .5, v + .5, torch.ones_like(u)), -1).float() @ torch.linalg.inv(source.K).T
    world = (rays * z[..., None] - source.viewmat[:3, 3]) @ source.viewmat[:3, :3]
    cam = world @ target.viewmat[:3, :3].T + target.viewmat[:3, 3]
    p = cam @ target.K.T
    uv = p[..., :2] / p[..., 2:].clamp_min(.01)
    grid = torch.stack((2 * uv[..., 0] / target.width - 1, 2 * uv[..., 1] / target.height - 1), -1)[None]
    def sample(value):
        if value.ndim == 2: value = value[..., None]
        return F.grid_sample(value.permute(2, 0, 1)[None], grid, align_corners=False, padding_mode="zeros")[0].permute(1, 2, 0)
    zd = sample(reference["depth"].detach())[..., 0]
    alpha = sample(reference["geometry_mass"].detach())[..., 0]
    target_valid = sample((target.valid & target.mask & (reference["geometry_mass"].detach()>.5)).float())[..., 0] > .999
    valid = source.mask[v, u] & (out["geometry_mass"][v, u].detach() > .5) & target_valid & (alpha > .5)
    valid &= (cam[..., 2].detach() > 0) & ((zd - cam[..., 2]).detach().abs() < .5)
    valid &= (out["normal_render"][v,u].detach().norm(dim=-1)>1e-5)
    valid &= (sample(reference["normal_render"].detach()).norm(dim=-1)>1e-5)
    if int(valid.sum()) < 32:
        return z.sum() * 0, {"mvc_valid_pixels": int(valid.sum()), "mvc_depth": 0., "mvc_photo": 0.}
    dl = F.smooth_l1_loss(cam[..., 2][valid], zd[valid], beta=.1)
    photo = (source.image[v, u] - sample(target.image)).abs()[valid].mean()
    nr = F.normalize(out["normal_render"][v, u], dim=-1)
    nt = F.normalize(sample(reference["normal_render"].detach()), dim=-1)
    nl = (1 - (nr * nt).sum(-1).abs().clamp(max=1))[valid].mean()
    return dl + .1 * nl + .1 * photo, {"mvc_valid_pixels": int(valid.sum()),
         "mvc_depth": float(dl.detach()), "mvc_photo": float(photo.detach()), "mvc_normal": float(nl.detach())}


def fitting_loss(model, view, out, cfg, geometry_active, prior_active, reference=None):
    mask = view.mask & view.valid
    photo = l_photo(out["rgb"], view.image, lam=cfg["ssim_fraction"], mask=mask)
    coverage = F.relu(cfg["coverage_alpha_target"] - out["geometry_mass"])[mask].mean()
    normal = normal_consistency(out, mask) if geometry_active else photo * 0
    prior = model.prior_loss() if prior_active else photo * 0
    mvc, mvc_row = photo * 0, {}
    if geometry_active and reference is not None:
        mvc, mvc_row = multiview_loss(view, out, reference[0], reference[1], cfg["mvc_pixel_stride"])
    total = photo + cfg["coverage_weight"] * coverage + cfg["normal_weight"] * normal
    total = total + cfg["multiview_weight"] * mvc + cfg["soft_prior_weight"] * prior
    return total, {"loss": float(total.detach()), "photo": float(photo.detach()),
         "coverage": float(coverage.detach()), "normal": float(normal.detach()), "prior": float(prior.detach()),
         "multiview": float(mvc.detach()), "train_mask_pixels": int(mask.sum()), **mvc_row}


@torch.no_grad()
def appearance_geometry_metrics(initial, current, view):
    a0, a1 = initial["geometry_mass"], current["geometry_mass"]
    support = view.valid & (a0 >= .5)
    common = support & (a1 >= .5)
    error = (current["rgb"].clamp(0, 1) - view.image).abs()
    def measure(mask):
        if not bool(mask.any()): return {"pixels": 0, "mae": None, "psnr": None}
        mse = ((current["rgb"].clamp(0, 1) - view.image) ** 2)[mask].mean()
        return {"pixels": int(mask.sum()), "mae": float(error[mask].mean()),
                "psnr": float(-10 * torch.log10(mse.clamp_min(1e-12)))}
    nr0, nr1 = F.normalize(initial["normal_render"], dim=-1), F.normalize(current["normal_render"], dim=-1)
    angular = torch.acos((nr0 * nr1).sum(-1).abs().clamp(0, 1)) * 180 / torch.pi
    depth = (current["depth"] - initial["depth"]).abs()
    initial_np=support.cpu().numpy()
    final_np=(view.valid & (a1>=.5)).cpu().numpy()
    e0=initial_np & ~binary_erosion(initial_np)
    e1=final_np & ~binary_erosion(final_np)
    boundary={"initial_boundary_pixels":int(e0.sum()),"final_boundary_pixels":int(e1.sum()),
              "symmetric_boundary_distance_mean_px":None,"symmetric_boundary_distance_p90_px":None}
    if e0.any() and e1.any():
        distances=np.concatenate((distance_transform_edt(~e0)[e1],distance_transform_edt(~e1)[e0]))
        boundary.update(symmetric_boundary_distance_mean_px=float(distances.mean()),
                        symmetric_boundary_distance_p90_px=float(np.quantile(distances,.9)))
    return {"image_id": view.image_id, "fixed_initial_support": measure(support),
            "boundary": boundary,
            "conditional_observation_support": measure(support & view.mask),
            "whole_valid_crop": measure(view.valid), "retained_support": measure(common),
            "removed_initial_pixels": int((support & (a1 < .5)).sum()),
            "added_pixels": int((view.valid & (a0 < .5) & (a1 >= .5)).sum()),
            "final_alpha_coverage_valid_fraction": float(((current["alpha"] >= .5) & view.valid).sum() / view.valid.sum()),
            "final_geometry_presence_valid_fraction": float(((a1 >= .5) & view.valid).sum() / view.valid.sum()),
            "rgb_present_geometry_missing_pixels":int((view.valid&(current["alpha"]>=.5)&(a1<.5)).sum()),
            "surface_depth_abs_change_mean_m": float(depth[common].mean()) if bool(common.any()) else None,
            "surface_depth_abs_change_p90_m": float(depth[common].quantile(.9)) if bool(common.any()) else None,
            "render_normal_change_mean_deg": float(angular[common].mean()) if bool(common.any()) else None}


def extract_surface(out, view, seed, stride=2):
    depth = out["depth"].detach().cpu().numpy()
    alpha = out["geometry_mass"].detach().cpu().numpy()
    valid = view.valid.detach().cpu().numpy() & (alpha >= .5) & np.isfinite(depth) & (depth > 0)
    sampling = np.zeros_like(valid); sampling[::stride, ::stride] = True
    v, u = np.where(valid & sampling)
    K, V = view.K.cpu().numpy(), view.viewmat.cpu().numpy()
    rays = np.column_stack((u + .5, v + .5, np.ones(len(u)))) @ np.linalg.inv(K).T
    xyz = (rays * depth[v, u, None] - V[:3, 3]) @ V[:3, :3]
    distance, ids = cKDTree(seed["xyz"]).query(xyz)
    return {"xyz": xyz.astype(np.float32), "unit_index": seed["unit_index"][ids],
            "group": seed["group"][ids], "association_distance_m": distance.astype(np.float32),
            "image_id": np.full(len(xyz), view.image_id, np.int32), "pixel_uv": np.column_stack((u, v)).astype(np.int32),
            "normal": out["normal_render"].detach().cpu().numpy()[v, u].astype(np.float32)}
