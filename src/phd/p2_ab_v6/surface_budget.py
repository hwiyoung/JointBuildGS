"""Normal-only surface updates constrained by observational A intervals.

These intervals are conditional image evidence, not calibrated absolute truth.
The additional guard measures actual rendered surfaces, not Gaussian centres.
"""
from __future__ import annotations
import numpy as np
import torch
from scipy.ndimage import binary_erosion
from scipy.spatial import cKDTree
from gsplat import rasterization_2dgs
from src.phd.p2_ab_v3.appearance_sh import StructuredGaussians as ColorGaussians


def allowable_interval(low, high, epsilon):
    """sup_{x in [low,high]} |candidate-x| <= epsilon, NOT membership in X."""
    return high - epsilon, low + epsilon


class SurfaceGaussians(ColorGaussians):
    def __init__(self, seed, cfg, device="cuda"):
        super().__init__(seed, cfg, device)
        self.normal_offset = torch.nn.Parameter(torch.zeros(len(self.base), device=device))

    @property
    def means(self):
        return self.base + self.normals * self.normal_offset[:, None]

    @torch.no_grad()
    def state_arrays(self, seed):
        state = super().state_arrays(seed)
        state["normal_offset_m"] = self.normal_offset.cpu().numpy()
        state["detail_displacement"] = (self.normals * self.normal_offset[:, None]).cpu().numpy()
        return state

    def trainable(self, geometry):
        for name, parameter in self.named_parameters():
            parameter.requires_grad_(name in {"sh0", "sh_rest"} or (geometry and name == "normal_offset"))


class Evidence:
    def __init__(self, handoff, profiles, seed, device="cuda"):
        if not np.array_equal(handoff["seed_id"], seed["seed_id"]):
            raise ValueError("A handoff does not bind exact B seed order")
        self.observable = torch.as_tensor(handoff["observable"], device=device, dtype=torch.bool)
        self.initial_eligible = torch.as_tensor(handoff["initial_eligible"], device=device, dtype=torch.bool)
        for name in ("observation_low_m", "observation_high_m", "allowed_low_m", "allowed_high_m", "target_m"):
            value = np.asarray(handoff[name], np.float32)
            if not np.isfinite(value[np.asarray(handoff["observable"], bool)]).all():
                raise ValueError("nonfinite observable A interval")
            setattr(self, name, torch.as_tensor(np.where(np.isfinite(value), value, 0), device=device))
        self.anchor = torch.as_tensor(np.maximum(handoff["anchor_id"], 0), device=device, dtype=torch.long)
        self.grid = torch.as_tensor(profiles["offsets_m"], device=device, dtype=torch.float32)
        self.cost = torch.as_tensor(np.nan_to_num(profiles["cost"], nan=1., posinf=1.), device=device, dtype=torch.float32)
        if self.cost.ndim != 3 or self.cost.shape[0] != 2 or self.cost.shape[2] != len(self.grid):
            raise ValueError("A cost layout must be [2,anchors,offsets]")
        self.zero = torch.zeros_like(self.target_m)

    def cost_at(self, offset):
        p = ((offset-self.grid[0])/(self.grid[1]-self.grid[0])).clamp(0, len(self.grid)-1.00001)
        lo = p.long(); frac = p-lo
        return self.cost[:, self.anchor, lo]*(1-frac)[None] + self.cost[:, self.anchor, lo+1]*frac[None]

    def loss(self, offset):
        cost = self.cost_at(offset)
        return cost[:, self.observable].mean() if bool(self.observable.any()) else offset.sum()*0

    @torch.no_grad()
    def constrain(self, proposal):
        result = torch.maximum(torch.minimum(proposal, self.allowed_high_m), self.allowed_low_m)
        return torch.where(self.observable, result, self.zero)

    @torch.no_grad()
    def dynamic_accept(self, before, proposal, tolerance=1e-7):
        old, new = self.cost_at(before), self.cost_at(proposal)
        return self.observable & (new <= old+tolerance).all(0) & (new < old-tolerance).any(0)

    @torch.no_grad()
    def retain_jointly_valid_changes(self, before, proposal, tolerance=1e-7):
        """Recheck the actual post-backtracking proposal; unresolved bases may stay.

        A correction-needed point outside the interval is never made eligible by
        falling back to its original position. That fallback remains unresolved.
        """
        inside=(proposal>=self.allowed_low_m-1e-7)&(proposal<=self.allowed_high_m+1e-7)
        old,new=self.cost_at(before),self.cost_at(proposal)
        valid=self.observable & inside & (new<=old+tolerance).all(0)
        return torch.where(valid,proposal,before)


@torch.no_grad()
def geometry_render(model, view):
    g = rasterization_2dgs(means=model.means, quats=model.quats, scales=model.scales,
        opacities=model.opacities, colors=torch.zeros((len(model.base),8),device=model.base.device),
        viewmats=view.viewmat[None], Ks=view.K[None], width=view.width, height=view.height,
        sh_degree=None, render_mode="RGB", near_plane=.01, far_plane=1e10)
    mass = g[1][0,...,0]
    depth = torch.where(mass>1e-8, g[5][0,...,0]/mass.clamp_min(1e-8), torch.zeros_like(mass))
    return depth, mass


class SurfaceGuard:
    """Frozen train-ray budget, derived from remaining A normal-error budget.

    A nearest local plane associates a ray with an interval. This spatial transfer
    is approximate; the depth/presence check itself uses the actual renderer.
    It is explicitly an observational development contract, not an error certificate.
    """
    @torch.no_grad()
    def __init__(self, model, views, seed, evidence, cfg):
        self.rows = []; self.cfg = cfg
        tree = cKDTree(seed["xyz"])
        lo = evidence.observation_low_m.cpu().numpy()
        hi = evidence.observation_high_m.cpu().numpy()
        eligible = (evidence.observable & evidence.initial_eligible).cpu().numpy()
        budget = np.maximum(0, cfg["epsilon_m"]-np.maximum(np.abs(lo),np.abs(hi)))
        for view in views:
            depth, mass = geometry_render(model, view)
            valid = (view.mask & (mass>=.7)).cpu().numpy()
            valid = binary_erosion(valid, iterations=2)
            sample = np.zeros_like(valid); sample[::cfg["guard_stride"],::cfg["guard_stride"]] = True
            y,x = np.where(valid & sample)
            K,V = view.K.cpu().numpy(),view.viewmat.cpu().numpy()
            ray_camera = np.column_stack((x+.5,y+.5,np.ones(len(x)))) @ np.linalg.inv(K).T
            ray_world = ray_camera @ V[:3,:3]
            z = depth.cpu().numpy()[y,x]
            world = (ray_camera*z[:,None]-V[:3,3]) @ V[:3,:3]
            distance, ids = tree.query(world,workers=2)
            dot = np.abs((seed["normals"][ids]*ray_world).sum(1))
            keep = eligible[ids] & (distance<=cfg["guard_association_m"]) & (dot>=.2) & (budget[ids]>1e-5)
            y,x,ids,dot = y[keep],x[keep],ids[keep],dot[keep]
            bound = budget[ids]/dot
            idx = torch.as_tensor(y*view.width+x,device=model.base.device,dtype=torch.long)
            self.rows.append(dict(view=view,index=idx,initial=depth.reshape(-1)[idx].clone(),
                limit=torch.as_tensor(bound,device=model.base.device,dtype=torch.float32),count=len(idx)))

    @torch.no_grad()
    def check(self, model):
        missing=violations=total=0; max_excess=0.; sums=0.; rows=[]
        for row in self.rows:
            if not row["count"]: continue
            depth,mass=geometry_render(model,row["view"]);idx=row["index"]
            d=(depth.reshape(-1)[idx]-row["initial"]).abs()
            bad_mass=mass.reshape(-1)[idx]<.5
            excess=d-row["limit"]
            bad=bad_mass | (excess>self.cfg["guard_numeric_tolerance_m"])
            n=int(bad.sum());miss=int(bad_mass.sum());total+=row["count"];violations+=n;missing+=miss
            max_excess=max(max_excess,float(excess.max()));sums+=float(d.sum())
            rows.append(dict(image_id=row["view"].image_id,pixels=row["count"],violations=n,missing=miss))
        return dict(passed=violations==0 and total>0,protected_pixels=total,violations=violations,
            missing=missing,max_excess_m=max_excess,mean_depth_change_m=sums/max(total,1),views=rows)

    @torch.no_grad()
    def project(self, model, before, evidence=None):
        proposal=model.normal_offset.detach().clone()
        attempts=[]
        for i in range(9):
            factor=2.**(-i)
            candidate=before+(proposal-before)*factor
            if evidence is not None:
                candidate=evidence.retain_jointly_valid_changes(before,candidate)
            model.normal_offset.copy_(candidate)
            check=self.check(model);attempts.append(dict(factor=factor,violations=check["violations"]))
            if check["passed"]:return dict(accepted_factor=factor,attempts=attempts,check=check)
        model.normal_offset.copy_(before)
        check=self.check(model)
        if not check["passed"]:raise ValueError("previous accepted surface violates its own guard")
        return dict(accepted_factor=0.,attempts=attempts,check=check)
