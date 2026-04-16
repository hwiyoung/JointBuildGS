"""Stage-2 vanilla 2DGS training loop.

Usage (inside container):
    python -m src.stage2.train --config configs/vanilla.yaml

The config file specifies data root, output dir, max iterations, loss weights,
and densification schedule. This Phase-1 Step-1-1 trainer uses only the
data-fitting losses: L_photo, L_depth, L_normal, L_nc.
"""
from __future__ import annotations

import argparse
import math
import os
import random
import time
from pathlib import Path
from typing import Dict

import numpy as np
import torch
import yaml
from torch.utils.tensorboard import SummaryWriter
from tqdm import tqdm

from .dataloader import SeongsuDataset
from .densification import build_optimizers, build_param_dict, build_strategy
from .loss import data_fitting as L
from .model import GaussianModel2D
from .renderer import render


# Map from gsplat strategy dict keys -> model attribute names
_STRATEGY_TO_MODEL = {
    "means": "means",
    "scales": "log_scales",
    "quats": "quats",
    "opacities": "opacities_raw",
    "sh0": "sh0",
    "shN": "shN",
}


def _sync_params_to_model(params: Dict[str, torch.nn.Parameter], model: GaussianModel2D):
    """After gsplat DefaultStrategy grow/prune, params dict entries may have been
    replaced with new nn.Parameters. Sync them back into the model so model.means etc.
    reflect the updated tensors."""
    for strategy_key, model_attr in _STRATEGY_TO_MODEL.items():
        p = params.get(strategy_key)
        if p is None:
            continue
        current = getattr(model, model_attr, None)
        if current is not p:
            setattr(model, model_attr, p)


def set_seed(seed: int):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def psnr(a: torch.Tensor, b: torch.Tensor) -> float:
    mse = ((a - b) ** 2).mean().item()
    return 20 * math.log10(1.0) - 10 * math.log10(max(mse, 1e-10))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    args = ap.parse_args()
    with open(args.config) as f:
        cfg = yaml.safe_load(f)

    set_seed(cfg.get("seed", 0))
    device = cfg.get("device", "cuda")
    out_dir = Path(cfg["out_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "ckpt").mkdir(exist_ok=True)
    (out_dir / "renders").mkdir(exist_ok=True)

    # ---------- data ----------
    ds = SeongsuDataset(
        root=cfg["data_root"],
        downscale=cfg.get("downscale", 0.5),
        load_depth=True,
        load_normal=True,
    )
    print(f"[data] frames={len(ds)}  pts_init={ds.points_xyz.shape[0]}")

    # train/test split (last 10% as test)
    n = len(ds)
    test_idx = list(range(max(1, int(n * 0.9)), n))
    train_idx = [i for i in range(n) if i not in test_idx]

    # ---------- model ----------
    model = GaussianModel2D(
        points_xyz=ds.points_xyz,
        points_rgb=ds.points_rgb,
        sh_degree=cfg.get("sh_degree", 3),
        device=device,
    )
    model = model.to(device)

    params = build_param_dict(model)
    optimizers = build_optimizers(
        model,
        lr_means=cfg.get("lr_means", 1.6e-4),
        lr_scales=cfg.get("lr_scales", 5e-3),
        lr_quats=cfg.get("lr_quats", 1e-3),
        lr_opacities=cfg.get("lr_opacities", 5e-2),
        lr_sh0=cfg.get("lr_sh0", 2.5e-3),
        lr_shN=cfg.get("lr_shN", 1.25e-4),
    )

    # scene scale (for DefaultStrategy)
    scene_scale = float(np.linalg.norm(ds.points_xyz - ds.points_xyz.mean(0), axis=1).mean())

    strategy = build_strategy(
        prune_opa=cfg.get("prune_opa", 0.005),
        grow_grad2d=cfg.get("grow_grad2d", 2e-4),
        grow_scale3d=cfg.get("grow_scale3d", 0.01),
        prune_scale3d=cfg.get("prune_scale3d", 0.1),
        refine_start_iter=cfg.get("refine_start_iter", 500),
        refine_stop_iter=cfg.get("refine_stop_iter", 15000),
        refine_every=cfg.get("refine_every", 100),
        reset_every=cfg.get("reset_every", 3000),
    )
    strategy.check_sanity(params, optimizers)
    strategy_state = strategy.initialize_state(scene_scale=scene_scale)

    # ---------- logging ----------
    writer = SummaryWriter(out_dir / "tb")

    # ---------- loss weights ----------
    w_photo = cfg.get("w_photo", 1.0)
    w_depth = cfg.get("w_depth", 1.0)
    w_normal = cfg.get("w_normal", 0.05)
    w_nc = cfg.get("w_nc", 0.05)
    w_distort = cfg.get("w_distort", 100.0)   # 2DGS distortion reg
    photo_lam = cfg.get("photo_lam", 0.2)

    max_iter = int(cfg["max_iter"])
    sh_up_every = int(cfg.get("sh_up_every", 1000))

    print(f"[train] max_iter={max_iter}  out={out_dir}")
    pbar = tqdm(range(max_iter), desc="train")
    t0 = time.time()

    for it in pbar:
        # pick a random training view
        idx = train_idx[it % len(train_idx)] if cfg.get("sequential", False) else random.choice(train_idx)
        batch = ds[idx]
        rgb_gt = batch["rgb"].to(device)
        w2c = batch["w2c"].to(device)
        K = batch["K"].to(device)
        H, W = batch["height"], batch["width"]

        out = render(model, w2c, K, W, H, sh_degree=model.active_sh_degree, render_mode="RGB+ED")
        rgb_pred = out["rgb"]
        depth_pred = out["depth"]
        n_render = out["normal_render"]
        n_surf = out["normal_surf"]
        alpha = out["alpha"]
        distort = out["distort"]
        meta = out["meta"]

        # track grad for densification (gsplat DefaultStrategy hook)
        strategy.step_pre_backward(params, optimizers, strategy_state, it, meta)

        # losses
        loss_photo = L.l_photo(rgb_pred, rgb_gt, lam=photo_lam)
        loss_total = w_photo * loss_photo

        if "depth" in batch:
            d_gt = batch["depth"].to(device)
            d_m = batch["depth_mask"].to(device)
            loss_depth = L.l_depth(depth_pred, d_gt, d_m)
            loss_total = loss_total + w_depth * loss_depth
        else:
            loss_depth = torch.tensor(0.0, device=device)

        if "normal" in batch:
            n_gt = batch["normal"].to(device)
            n_m = batch["normal_mask"].to(device)
            loss_n = L.l_normal(n_render, n_gt, w2c, n_m)
            loss_total = loss_total + w_normal * loss_n
        else:
            loss_n = torch.tensor(0.0, device=device)

        loss_nc = L.l_nc(n_render, n_surf, alpha=alpha.detach())
        loss_total = loss_total + w_nc * loss_nc

        loss_dist = distort.mean()
        loss_total = loss_total + w_distort * loss_dist

        # backward
        for opt in optimizers.values():
            opt.zero_grad(set_to_none=True)
        loss_total.backward()

        strategy.step_post_backward(params, optimizers, strategy_state, it, meta)

        # sync params dict -> model (gsplat strategy may replace nn.Parameters on grow/prune)
        _sync_params_to_model(params, model)

        for opt in optimizers.values():
            opt.step()

        # SH warmup
        if (it + 1) % sh_up_every == 0:
            model.oneup_sh_degree()

        # logging
        if it % 10 == 0:
            with torch.no_grad():
                p = psnr(rgb_pred.clamp(0, 1), rgb_gt)
            writer.add_scalar("loss/total", loss_total.item(), it)
            writer.add_scalar("loss/photo", loss_photo.item(), it)
            writer.add_scalar("loss/depth", loss_depth.item(), it)
            writer.add_scalar("loss/normal", loss_n.item(), it)
            writer.add_scalar("loss/nc", loss_nc.item(), it)
            writer.add_scalar("loss/distort", loss_dist.item(), it)
            writer.add_scalar("metric/psnr_train", p, it)
            writer.add_scalar("stats/n_primitives", model.num_points, it)
            pbar.set_postfix(loss=f"{loss_total.item():.4f}", psnr=f"{p:.2f}", N=model.num_points)

        # periodic eval + render sample
        if it % cfg.get("eval_every", 2000) == 0 and it > 0:
            _eval_and_save(model, ds, test_idx, device, writer, out_dir, it)

        if it % cfg.get("ckpt_every", 5000) == 0 and it > 0:
            torch.save({
                "it": it,
                "state_dict": model.state_dict(),
                "n_prim": model.num_points,
            }, out_dir / "ckpt" / f"step_{it:06d}.pt")

    # final
    torch.save({
        "it": max_iter,
        "state_dict": model.state_dict(),
        "n_prim": model.num_points,
    }, out_dir / "ckpt" / "final.pt")
    _eval_and_save(model, ds, test_idx, device, writer, out_dir, max_iter, tag="final")
    dt = time.time() - t0
    print(f"[done] {max_iter} iter in {dt/60:.1f} min.  final N={model.num_points}")


@torch.no_grad()
def _eval_and_save(model, ds, test_idx, device, writer, out_dir, it, tag: str = ""):
    psnrs, depth_maes, normal_coses = [], [], []
    for k, idx in enumerate(test_idx[:4]):
        b = ds[idx]
        rgb_gt = b["rgb"].to(device)
        w2c = b["w2c"].to(device)
        K = b["K"].to(device)
        H, W = b["height"], b["width"]
        out = render(model, w2c, K, W, H, sh_degree=model.active_sh_degree, render_mode="RGB+ED")
        rgb_p = out["rgb"].clamp(0, 1)
        mse = ((rgb_p - rgb_gt) ** 2).mean().item()
        psnrs.append(20 * math.log10(1.0) - 10 * math.log10(max(mse, 1e-10)))
        if "depth" in b:
            d_gt = b["depth"].to(device)
            d_m = b["depth_mask"].to(device)
            mae = ((out["depth"] - d_gt).abs() * d_m.float()).sum() / d_m.sum().clamp_min(1)
            depth_maes.append(mae.item())
        if "normal" in b:
            n_gt = b["normal"].to(device)
            n_m = b["normal_mask"].to(device)
            R = w2c[:3, :3]
            np_pred = out["normal_render"] @ R.T
            np_pred = torch.nn.functional.normalize(np_pred, dim=-1, eps=1e-6)
            ng = torch.nn.functional.normalize(n_gt, dim=-1, eps=1e-6)
            c = (np_pred * ng).sum(-1).abs()
            normal_coses.append((c * n_m.float()).sum().item() / n_m.sum().clamp_min(1).item())

        # save sample renders
        import imageio.v2 as imageio
        rgb8 = (rgb_p.cpu().numpy() * 255).astype(np.uint8)
        imageio.imwrite(out_dir / "renders" / f"it{it:06d}_v{k}_rgb.png", rgb8)

    writer.add_scalar("eval/psnr", float(np.mean(psnrs)), it)
    if depth_maes:
        writer.add_scalar("eval/depth_mae", float(np.mean(depth_maes)), it)
    if normal_coses:
        writer.add_scalar("eval/normal_cos", float(np.mean(normal_coses)), it)


if __name__ == "__main__":
    main()
