"""Additive P2 planar-Gaussian development solver.

No decision is inferred here. Sample-supported geometry remains a conditional
representation; a missing certified surface budget never becomes an approval.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

import numpy as np
import torch
from torch import nn
from scipy.spatial import cKDTree

from src.stage2.model import quaternion_from_positive_z_normals, quat_to_rotmat
from src.stage2.renderer import render


def validate_handoff(row: dict, *, certified: bool) -> bool:
    """Strict handoff consumes actual area/component authority only."""
    key = "strict_current_use_action" if certified else "conditional_action"
    action = row.get(key, "ABSTAIN")
    if action == "ABSTAIN":
        return False
    if action not in {"IMAGE", "PRIOR", "FUSION"}:
        raise ValueError(f"Unknown action {action!r}")
    if certified and row.get("support_scope") != "certified_surface":
        raise ValueError("Sample support cannot authorize a finite surface")
    if action == "FUSION" and not row.get("selected_geometry"):
        raise ValueError("FUSION requires the exact tested combined geometry")
    return True


def representative_rows(xyz: np.ndarray, group: np.ndarray, spacing: float) -> np.ndarray:
    """One original row per source/unit-local voxel; never merges unit layers."""
    if spacing <= 0:
        raise ValueError("spacing must be positive")
    key = np.column_stack((group, np.floor(xyz / spacing).astype(np.int64)))
    _, rows = np.unique(key, axis=0, return_index=True)
    return np.sort(rows)


def estimate_frames(xyz: np.ndarray, group: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """PCA source normals and tangent spacing; no current-reference input."""
    normals = np.zeros_like(xyz, dtype=np.float32)
    scales = np.zeros(len(xyz), dtype=np.float32)
    for g in np.unique(group):
        ii = np.flatnonzero(group == g)
        p = xyz[ii]
        if len(p) < 3:
            raise ValueError("At least three source points required for a tangent frame")
        distance, neighbors = cKDTree(p).query(p, k=min(12, len(p)))
        for j in range(len(p)):
            local = p[neighbors[j]]
            _, _, vt = np.linalg.svd(local - local.mean(0), full_matrices=False)
            normal = vt[-1]
            if normal[2] < 0:
                normal = -normal
            normals[ii[j]] = normal
        scales[ii] = np.median(distance[:, 1:min(4, distance.shape[1])], axis=1) * 0.65
    return normals, np.clip(scales, 0.04, 0.45)


class SurfaceGaussians(nn.Module):
    """Normal displacement = per-unit affine structure + orthogonal detail.

    Tangential displacement, spin, orientation and topology remain fixed in v1.
    Detail is orthogonal to [1,u,v] per unit, so local motion cannot re-encode the
    unit's offset or tilt. This fixes a parameter gauge, not source authority.
    """
    active_sh_degree = 0

    def __init__(self, xyz, normal, scale, rgb, group, *, device="cuda", displacement_axis="normal"):
        super().__init__()
        self.register_buffer("base", torch.as_tensor(xyz, dtype=torch.float32, device=device))
        self.register_buffer("normal", torch.as_tensor(normal, dtype=torch.float32, device=device))
        if displacement_axis not in {"normal", "scene_z"}:
            raise ValueError(displacement_axis)
        direction = self.normal.clone()
        if displacement_axis == "scene_z":
            direction.zero_()
            direction[:, 2] = 1
        self.register_buffer("displacement_direction", direction)
        q = quaternion_from_positive_z_normals(self.normal)
        self.register_buffer("quats", q)
        self.register_buffer("group", torch.as_tensor(group, dtype=torch.long, device=device))
        self.group_rows = [torch.where(self.group == g)[0] for g in torch.unique(self.group)]
        self.designs = []
        self.pseudoinverses = []
        for ids in self.group_rows:
            local = self.base[ids] - self.base[ids].mean(0)
            frame = quat_to_rotmat(q[ids[0]])
            uv = local @ frame[:, :2]
            design = torch.cat((torch.ones((len(ids), 1), device=device), uv), dim=1)
            self.designs.append(design)
            self.pseudoinverses.append(torch.linalg.pinv(design))
        self.structure = nn.Parameter(torch.zeros((len(self.group_rows), 3), device=device))
        self.detail = nn.Parameter(torch.zeros(len(xyz), device=device))
        log_s = np.column_stack((np.log(scale), np.log(scale), np.full(len(scale), np.log(1e-6))))
        self.log_scales = nn.Parameter(torch.as_tensor(log_s, dtype=torch.float32, device=device))
        self.opacities_raw = nn.Parameter(torch.full((len(xyz),), 2.1972246, device=device))
        sh = (np.asarray(rgb) - 0.5) / 0.28209479177387814
        self.sh0 = nn.Parameter(torch.as_tensor(sh[:, None, :], dtype=torch.float32, device=device))

    def normal_displacements(self):
        result = torch.zeros_like(self.detail)
        for gi, ids in enumerate(self.group_rows):
            H, Hplus = self.designs[gi], self.pseudoinverses[gi]
            local = self.detail[ids]
            result[ids] = H @ self.structure[gi] + local - H @ (Hplus @ local)
        return result

    @property
    def means(self):
        return self.base + self.displacement_direction * self.normal_displacements()[:, None]

    @property
    def scales(self):
        return self.log_scales.exp()

    @property
    def opacities(self):
        return self.opacities_raw.sigmoid()

    def colors_sh(self):
        return self.sh0

    def geometry_parameters(self):
        return [self.structure, self.detail, self.log_scales, self.opacities_raw]


@dataclass
class View:
    image_id: int
    role: str
    image: torch.Tensor
    K: torch.Tensor
    viewmat: torch.Tensor
    width: int
    height: int
    provenance: dict


def render_view(model, view):
    return render(model, view.viewmat, view.K, view.width, view.height,
                  sh_degree=0, render_mode="RGB+ED", depth_mode="expected",
                  bg_color=torch.zeros(3, device=model.base.device))


def snapshot_geometry(model):
    return [p.detach().clone() for p in model.geometry_parameters()]


@torch.no_grad()
def restore_geometry(model, snapshot):
    for p, value in zip(model.geometry_parameters(), snapshot):
        p.copy_(value)


def surface_guard(initial, proposed, *, max_depth_m: float, alpha_threshold: float = 0.5):
    """Check fixed camera-ray surface, missingness, and support intrusion.

    This is a finite-view expected-depth certificate only. It is deliberately
    stricter than a mean loss and cannot certify an unseen continuous surface.
    """
    source = initial["alpha"] >= alpha_threshold
    target = proposed["alpha"] >= alpha_threshold
    removed = source & ~target
    added = target & ~source
    overlap = source & target
    delta = (proposed["depth"] - initial["depth"]).abs()
    maximum = float(delta[overlap].max()) if bool(overlap.any()) else None
    finite = bool(torch.isfinite(proposed["depth"][target]).all())
    passed = finite and not bool(removed.any()) and not bool(added.any())
    passed = passed and maximum is not None and maximum <= max_depth_m + 1e-6
    return {"pass": passed, "removed_pixels": int(removed.sum()), "added_pixels": int(added.sum()),
            "initial_pixels": int(source.sum()), "final_pixels": int(target.sum()),
            "overlap_pixels": int(overlap.sum()), "max_depth_displacement_m": maximum,
            "depth_tolerance_m": max_depth_m, "finite_depth": finite}


def extract_surface(rendered, view: View, base_xyz: np.ndarray, base_unit: np.ndarray,
                    alpha_threshold=0.5):
    """Back-project the same expected-depth definition used by surface_guard."""
    alpha = rendered["alpha"].detach().cpu().numpy()
    depth = rendered["depth"].detach().cpu().numpy()
    mask = (alpha >= alpha_threshold) & np.isfinite(depth) & (depth > 0)
    v, u = np.where(mask)
    K = view.K.detach().cpu().numpy()
    V = view.viewmat.detach().cpu().numpy()
    rays = np.column_stack((u + .5, v + .5, np.ones(len(u)))) @ np.linalg.inv(K).T
    xyz = (rays * depth[v, u, None] - V[:3, 3]) @ V[:3, :3]
    distance, rows = cKDTree(base_xyz).query(xyz)
    # The nearest-source association is a diagnostic; its distance is retained.
    return {"xyz": xyz.astype(np.float32), "unit_index": base_unit[rows],
            "reference_row": rows, "association_distance_m": distance.astype(np.float32),
            "image_id": np.full(len(xyz), view.image_id, dtype=np.int32),
            "pixel_uv": np.column_stack((u, v)).astype(np.int32),
            "alpha": alpha[v, u]}


def appearance_metrics(initial, final, view):
    """Fixed initial support denominator, plus explicit final disappearance."""
    mask = initial["alpha"] >= .5
    target = view.image
    count = int(mask.sum())
    if count == 0:
        return {"image_id": view.image_id, "pixels": 0, "mae": None, "psnr_db": None}
    error = final["rgb"][mask] - target[mask]
    mse = float(error.square().mean())
    return {"image_id": view.image_id, "pixels": count,
            "mae": float(error.abs().mean()), "psnr_db": -10 * np.log10(max(mse, 1e-12)),
            "missing_initial_support_pixels": int((mask & (final["alpha"] < .5)).sum())}


def optimize(model, train_views: list[View], *, arm: str, steps: int,
             guard_depth_m: float | None, warmup: int, lr_color=.025, lr_geometry=.005,
             prior_weight=1.0, progress=None, allow_affine_detail=False):
    """Four explicit arms; geometry budget None forces the constrained arm fixed.

    Optimizer moments are rolled back along with rejected geometry. Appearance
    updates remain valid because SH0 alone does not alter alpha/depth extraction.
    """
    if arm not in {"surface_texturing", "fixed_gs", "prior_loss_gs", "constrained_gs"}:
        raise ValueError(arm)
    with torch.no_grad():
        initial = [{k: v.detach().clone() for k, v in render_view(model, view).items()
                    if isinstance(v, torch.Tensor)} for view in train_views]
    if arm == "surface_texturing":
        return {"history": [], "accepted_geometry_steps": 0, "rejected_geometry_steps": 0,
                "geometry_status": "fixed_source_surfel_texture_projection"}
    if arm == "constrained_gs" and not allow_affine_detail:
        # The real A-v1 certificate is only one scene-Z translation per tested
        # candidate. It cannot license tilt, detail, scale, or opacity changes.
        model.detail.requires_grad_(False)
        model.log_scales.requires_grad_(False)
        model.opacities_raw.requires_grad_(False)
        model.structure.register_hook(lambda gradient: torch.cat((gradient[:, :1], torch.zeros_like(gradient[:, 1:])), dim=1))
    color_opt = torch.optim.Adam([model.sh0], lr=lr_color)
    geom_opt = torch.optim.Adam(model.geometry_parameters(), lr=lr_geometry)
    movable = arm == "prior_loss_gs" or (arm == "constrained_gs" and guard_depth_m is not None)
    accepted, rejected, history = 0, 0, []
    for step in range(steps):
        vi = step % len(train_views)
        view, baseline = train_views[vi], initial[vi]
        color_opt.zero_grad(set_to_none=True)
        geom_opt.zero_grad(set_to_none=True)
        current = render_view(model, view)
        support = baseline["alpha"] >= .5
        if not bool(support.any()):
            raise ValueError(f"No initial surface pixels in train view {view.image_id}")
        photo = (current["rgb"][support] - view.image[support]).abs().mean()
        loss = photo
        prior = current["depth"].sum() * 0
        if arm == "prior_loss_gs":
            difference = current["depth"][support] - baseline["depth"][support]
            prior = torch.nn.functional.smooth_l1_loss(difference, torch.zeros_like(difference), beta=.1)
            loss = loss + prior_weight * prior
        loss.backward()
        color_opt.step()
        geometry_step = movable and step >= warmup
        if geometry_step:
            before = snapshot_geometry(model)
            optimizer_before = copy.deepcopy(geom_opt.state_dict()) if arm == "constrained_gs" else None
            geom_opt.step()
            with torch.no_grad():
                model.log_scales[:, :2].clamp_(np.log(.02), np.log(.65))
                model.log_scales[:, 2].fill_(np.log(1e-6))
                model.opacities_raw.clamp_(-8, 8)
            if arm == "constrained_gs":
                with torch.no_grad():
                    checks = [surface_guard(b, render_view(model, v), max_depth_m=guard_depth_m)
                              for v, b in zip(train_views, initial)]
                direct_bound = float(model.normal_displacements().detach().abs().max()) <= guard_depth_m + 1e-6
                if direct_bound and all(check["pass"] for check in checks):
                    accepted += 1
                else:
                    restore_geometry(model, before)
                    geom_opt.load_state_dict(optimizer_before)
                    rejected += 1
            else:
                accepted += 1
        if step % max(1, steps // 10) == 0 or step == steps - 1:
            row = {"step": step + 1, "train_image_id": view.image_id,
                   "photo_l1": float(photo.detach()), "prior_loss": float(prior.detach()),
                   "accepted_geometry_steps": accepted, "rejected_geometry_steps": rejected}
            history.append(row)
            if progress:
                progress(row)
    return {"history": history, "accepted_geometry_steps": accepted,
            "rejected_geometry_steps": rejected, "geometry_status":
            "finite_view_conditional_guard" if arm == "constrained_gs" and movable else
            "soft_prior_unconstrained" if arm == "prior_loss_gs" else "fixed_geometry"}
