#!/usr/bin/env python3
"""P2 make-or-break v6 — Phase 2 pre-check (must pass before the ~95min runs).

Mirrors src/stage2/train.py's init + semantic-render path EXACTLY and asserts:
  (1) init is filled with the MVS cloud   -> model.num_points ~= sfm + seed count
  (2) detach is RELEASED                   -> with ONLY L_sem, 1 backward => seed means.grad != 0
                                              (and the contrast: sem_detach_geometry=true => grad 0)
  (3) labels load + L_sem computes         -> loss_sem is a finite number on a real frame

Run in the dev container (GPU):
  docker compose run --rm -T dev python scripts/input_and_alignment/tum_transfer/seed_precheck.py \
      --config configs/input_and_alignment/tum_mob/gs_seed_dense.yaml
Observation only. Engine logic unchanged (standalone probe reusing engine modules).
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import torch
import yaml

sys.path.insert(0, "/workspace/JointBuildGS")
from src.stage2.dataloader import ColmapDataset
from src.stage2.model import GaussianModel2D
from src.stage2.pointcloud_io import read_init_pointcloud
from src.stage2.renderer import render_semantic
from src.stage2.loss import data_fitting as L


def build_model(cfg, device):
    ds = ColmapDataset(
        root=cfg["data_root"],
        downscale=cfg.get("downscale", 1.0),
        load_depth=False, load_normal=False,
        load_semantic=cfg.get("load_semantic", True),
    )
    n_sfm = ds.points_xyz.shape[0]
    points_xyz, points_rgb, points_sem = ds.points_xyz, ds.points_rgb, None
    n_seed = 0
    init_pc = cfg.get("init_pointcloud")
    if init_pc:
        mode = cfg.get("init_pointcloud_mode", "concat")
        seed_xyz = read_init_pointcloud(init_pc)
        n_seed = len(seed_xyz)
        scene_rgb = ds.points_rgb.mean(axis=0)
        seed_rgb = np.broadcast_to(scene_rgb, (n_seed, 3)).astype(np.float32).copy()
        if mode == "replace":
            points_xyz, points_rgb = seed_xyz.astype(np.float32), seed_rgb
        else:
            points_xyz = np.concatenate([points_xyz, seed_xyz], 0).astype(np.float32)
            points_rgb = np.concatenate([points_rgb, seed_rgb], 0).astype(np.float32)
    model = GaussianModel2D(points_xyz=points_xyz, points_rgb=points_rgb,
                            sh_degree=cfg.get("sh_degree", 3), device=device,
                            points_sem=points_sem).to(device)
    return ds, model, n_sfm, n_seed


def first_semantic_frame(ds, device):
    n = len(ds)
    train_idx = [i for i in range(n) if i % 10 != 9]
    for i in train_idx:
        b = ds[i]
        if "semantic" in b:
            sg = b["semantic"]
            if int((sg > 0).sum()) > 1000:   # has enough non-ignore (roof/wall/terrain) pixels
                return b, i, int((sg > 0).sum())
    raise RuntimeError("no frame with semantic GT found")


def sem_grad_norm(model, batch, device, detach):
    model.zero_grad(set_to_none=True)
    w2c = batch["w2c"].to(device); K = batch["K"].to(device)
    Hh, Ww = batch["height"], batch["width"]
    sem_pred = render_semantic(model, w2c, K, Ww, Hh, sem_detach_geometry=detach)
    sem_gt = batch["semantic"].to(device)
    loss_sem = L.l_sem(sem_pred, sem_gt, ignore_index=0)
    loss_sem.backward()
    def gnorm(p):
        return float(p.grad.norm().item()) if (p.grad is not None) else 0.0
    return float(loss_sem.item()), gnorm(model.means), gnorm(model.quats)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    A = ap.parse_args()
    cfg = yaml.safe_load(Path(A.config).read_text())
    device = "cuda"
    torch.manual_seed(int(cfg.get("seed", 0)))

    print(f"[precheck] config={A.config}")
    ds, model, n_sfm, n_seed = build_model(cfg, device)
    N = model.num_points
    print(f"\n(1) INIT FILLED  sfm={n_sfm}  seed={n_seed}  -> model.num_points={N}")
    if cfg.get("init_pointcloud"):
        exp = n_sfm + n_seed if cfg.get("init_pointcloud_mode", "concat") == "concat" else n_seed
        ok1 = (N == exp)
        print(f"    expected={exp}  match={ok1}  (means~=input: seed dominates {n_seed}/{N}="
              f"{100*n_seed/max(N,1):.1f}%)")
    else:
        ok1 = (N == n_sfm)
        print(f"    sparse arm: default COLMAP init, expected={n_sfm}  match={ok1}")

    batch, fidx, npx = first_semantic_frame(ds, device)
    print(f"\n(3) LABELS LOAD  frame_idx={fidx}  non-ignore px={npx}")

    cfg_detach = bool(cfg.get("sem_detach_geometry", True))
    ls_cfg, gm_cfg, gq_cfg = sem_grad_norm(model, batch, device, cfg_detach)
    print(f"    loss_sem={ls_cfg:.4f}  (finite={np.isfinite(ls_cfg)})")

    print(f"\n(2) DETACH RELEASE  (config sem_detach_geometry={cfg_detach})")
    print(f"    detach={cfg_detach:<5} -> means.grad={gm_cfg:.3e}  quats.grad={gq_cfg:.3e}")
    ls_t, gm_t, gq_t = sem_grad_norm(model, batch, device, True)
    print(f"    detach=True  -> means.grad={gm_t:.3e}  quats.grad={gq_t:.3e}  (must be ~0)")
    ls_f, gm_f, gq_f = sem_grad_norm(model, batch, device, False)
    print(f"    detach=False -> means.grad={gm_f:.3e}  quats.grad={gq_f:.3e}  (must be >0)")

    ok2 = (gm_f > 0 or gq_f > 0) and (gm_t == 0 and gq_t == 0)
    ok3 = np.isfinite(ls_cfg) and ls_cfg > 0
    print("\n===== PRECHECK SUMMARY =====")
    print(f"  (1) init filled      : {'PASS' if ok1 else 'FAIL'}")
    print(f"  (2) detach released  : {'PASS' if ok2 else 'FAIL'}  "
          f"(false grad={gm_f:.2e}/{gq_f:.2e} ; true grad={gm_t:.2e}/{gq_t:.2e})")
    print(f"  (3) labels + L_sem   : {'PASS' if ok3 else 'FAIL'}  (loss_sem={ls_cfg:.4f})")
    allok = ok1 and ok2 and ok3
    print(f"  ALL: {'PASS' if allok else 'FAIL'}")
    sys.exit(0 if allok else 1)


if __name__ == "__main__":
    main()
