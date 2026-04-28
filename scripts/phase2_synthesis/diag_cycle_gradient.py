"""Diag: per-loss gradient norm at variable level (cycle 검증 Track A).

Loads converged Structure (or Both) ckpt, runs ONE forward + per-loss backward
to measure ‖∂L_x / ∂θ‖ for each (loss, parameter).

Quantifies "cycle 고리 1: L_structure → n_i" strength relative to other losses.

Usage:
    python scripts/phase2_synthesis/diag_cycle_gradient.py \
        --config configs/phase2_structure.yaml \
        --ckpt   results/phase2_ablation_citygml/structure/ckpt/final.pt \
        --out    results/phase2_ablation_citygml/_diag/cycle_gradient_structure.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import torch
import yaml

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.stage2.dataloader import ColmapDataset
from src.stage2.grouping import group_primitives
from src.stage2.loss.data_fitting import l_photo, l_depth, l_normal, l_sem, l_nc
from src.stage2.loss.mutual import l_mutual
from src.stage2.loss.structure import l_structure
from src.stage2.model import GaussianModel2D, quat_to_rotmat
from src.stage2.renderer import render


def _load_into_model(ckpt_path: Path, sh_degree: int) -> GaussianModel2D:
    sd = torch.load(ckpt_path, map_location="cpu", weights_only=False)["state_dict"]
    n = sd["means"].shape[0]
    # Bootstrap with dummy points; we'll overwrite all params from ckpt.
    dummy_xyz = np.zeros((n, 3), dtype=np.float32)
    dummy_rgb = np.full((n, 3), 0.5, dtype=np.float32)
    model = GaussianModel2D(points_xyz=dummy_xyz, points_rgb=dummy_rgb,
                            sh_degree=sh_degree, device="cpu")
    with torch.no_grad():
        for k in ["means", "quats", "log_scales", "opacities_raw", "sh0", "sem_logits"]:
            if k in sd:
                getattr(model, k).data.copy_(sd[k])
        if "shN" in sd and hasattr(model, "shN"):
            if model.shN is None:
                model.shN = torch.nn.Parameter(sd["shN"].clone())
            elif model.shN.shape != sd["shN"].shape:
                model.shN = torch.nn.Parameter(sd["shN"].clone())
            else:
                model.shN.data.copy_(sd["shN"])
        model.active_sh_degree = sh_degree
    return model


def _grad(p):
    return float(p.grad.detach().norm().item()) if p is not None and p.grad is not None else 0.0


def _zero(model):
    for p in [model.means, model.quats, model.log_scales,
              model.opacities_raw, model.sh0, model.sem_logits]:
        if p.grad is not None:
            p.grad.detach_(); p.grad.zero_()
    if hasattr(model, "shN") and model.shN is not None and model.shN.grad is not None:
        model.shN.grad.detach_(); model.shN.grad.zero_()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--n-batches", type=int, default=4)
    ap.add_argument("--device", default="cuda")
    args = ap.parse_args()

    device = torch.device(args.device)
    cfg = yaml.safe_load(open(args.config))

    ds = ColmapDataset(
        root=cfg["data_root"],
        downscale=cfg.get("downscale", 1.0),
        load_depth=cfg.get("load_depth", True),
        load_normal=cfg.get("load_normal", True),
        load_semantic=cfg.get("load_semantic", False),
        depth_scale=cfg.get("depth_scale", 1.0),
    )
    n_views = len(ds)
    rng = np.random.RandomState(0)
    batch_idxs = rng.choice(n_views, size=min(args.n_batches, n_views), replace=False)

    model = _load_into_model(Path(args.ckpt), sh_degree=cfg.get("sh_degree", 0)).to(device)
    print(f"[diag] loaded {model.num_points} primitives from {args.ckpt}")

    LOSS_TARGETS = ["photo", "normal", "nc", "sem", "mutual",
                    "structure_na", "structure_cp"]
    PARAMS = ["means", "quats", "sem_logits"]

    accum = {lt: {pn: [] for pn in PARAMS} for lt in LOSS_TARGETS}
    loss_vals = {lt: [] for lt in LOSS_TARGETS}

    e_gravity = torch.tensor([0.0, -1.0, 0.0], device=device)  # default; override if cfg has

    for bi, idx in enumerate(batch_idxs):
        b = ds[int(idx)]
        rgb_gt = b["rgb"].to(device)
        w2c = b["w2c"].to(device)
        K = b["K"].to(device)
        H, W = int(b["height"]), int(b["width"])
        d_gt = b["depth"].to(device) if "depth" in b else None
        d_m = b["depth_mask"].to(device) if "depth_mask" in b else None
        n_gt = b["normal"].to(device) if "normal" in b else None
        n_m = b["normal_mask"].to(device) if "normal_mask" in b else None
        seg_gt = b["seg"].to(device) if "seg" in b else None

        for lt in LOSS_TARGETS:
            _zero(model)
            try:
                out = render(model, w2c, K, W, H,
                            sh_degree=model.active_sh_degree, render_mode="RGB+ED")
            except Exception as e:
                print(f"  batch {bi} {lt}: render failed ({type(e).__name__}: {e})")
                continue
            rgb_p = out["rgb"].clamp(0, 1)
            n_render = out["normal_render"]

            if lt == "photo":
                loss = l_photo(rgb_p, rgb_gt)
            elif lt == "normal" and n_gt is not None and n_m is not None:
                loss = l_normal(n_render, n_gt, n_m)
            elif lt == "nc":
                loss = l_nc(n_render, n_render.detach())  # placeholder; n_surf usually depth-derived
            elif lt == "sem" and seg_gt is not None and "sem_render" in out:
                loss = l_sem(out["sem_render"], seg_gt)
            elif lt == "mutual":
                normals_now = quat_to_rotmat(model.quats)[..., :, 2]
                terms = l_mutual(normals_now, model.means, model.sem_logits, e_gravity)
                loss = terms["total"]
            elif lt in ("structure_na", "structure_cp"):
                normals_now = quat_to_rotmat(model.quats)[..., :, 2]
                with torch.no_grad():
                    gid, rep_n, rep_d = group_primitives(
                        centers=model.means.detach(),
                        normals=normals_now.detach(),
                        sem_logits=model.sem_logits.detach(),
                        scales=torch.exp(model.log_scales).detach(),
                        voxel_size=cfg.get("structure_voxel_size", 0.05),
                        n_directions=cfg.get("structure_n_directions", 12),
                        min_group_size=cfg.get("structure_min_group", 5),
                    )
                terms = l_structure(normals_now, model.means, gid, rep_n, rep_d)
                key = "normal_align" if lt == "structure_na" else "coplanar"
                loss = terms[key]
                # need to make it a real loss with grads
                if not loss.requires_grad:
                    # re-derive scalar from inputs
                    mask = gid >= 0
                    n_i = normals_now[mask]
                    n_k = rep_n[gid[mask]].detach()
                    if lt == "structure_na":
                        cos = (n_i * n_k).sum(-1)
                        loss = ((1.0 - cos.abs()) ** 2).mean()
                    else:
                        c_i = model.means[mask]
                        sd_ = (n_k * c_i).sum(-1) + rep_d[gid[mask]].detach()
                        loss = (sd_ ** 2).mean()
            else:
                continue

            if not torch.isfinite(loss):
                continue
            loss.backward()
            loss_vals[lt].append(float(loss.detach().cpu()))
            for pn in PARAMS:
                accum[lt][pn].append(_grad(getattr(model, pn, None)))

    # aggregate
    means_per_loss_per_param = {
        lt: {pn: float(np.mean(vs)) if vs else 0.0 for pn, vs in d.items()}
        for lt, d in accum.items()
    }
    means_per_loss = {lt: float(np.mean(loss_vals[lt])) if loss_vals[lt] else 0.0
                      for lt in LOSS_TARGETS}

    out = {
        "ckpt": str(args.ckpt),
        "n_batches": int(args.n_batches),
        "loss_value": means_per_loss,
        "grad_norm_per_loss_per_param": means_per_loss_per_param,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=2))

    print()
    print("=" * 78)
    print(f"Mean ‖grad‖ per (loss, param)  — {args.n_batches} batches")
    print("=" * 78)
    print(f"{'loss':<14} {'val':>12}" + "".join(f"{pn:>14}" for pn in PARAMS))
    for lt in LOSS_TARGETS:
        v = means_per_loss[lt]
        row = "".join(f"{means_per_loss_per_param[lt][pn]:>14.4e}" for pn in PARAMS)
        print(f"{lt:<14} {v:>12.4e}" + row)

    print()
    print("=" * 78)
    print("RATIOS — quats (n_i proxy) and sem_logits (f_i)")
    print("=" * 78)
    for var in ["quats", "sem_logits"]:
        g = {lt: means_per_loss_per_param[lt][var] for lt in LOSS_TARGETS}
        st = g["structure_na"] + g["structure_cp"]
        non_st = sum(g[lt] for lt in LOSS_TARGETS if lt not in ("structure_na", "structure_cp"))
        print(f"{var}:")
        print(f"  L_structure / (others) = {st/max(non_st,1e-12)*100:.4f}%")
        if g["mutual"] > 0:
            print(f"  L_structure_na / L_mutual = {g['structure_na']/g['mutual']*100:.4f}%")
        if g["photo"] > 0:
            print(f"  L_structure_cp / L_photo  = {g['structure_cp']/g['photo']*100:.4f}%")
            print(f"  L_mutual       / L_photo  = {g['mutual']/g['photo']*100:.4f}%")


if __name__ == "__main__":
    main()
