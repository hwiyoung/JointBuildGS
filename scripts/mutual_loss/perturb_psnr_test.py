"""Test photo redundancy hypothesis directly.

For Phase 2 Mutual ckpt, perturb primitive positions PERPENDICULAR to their
normals by varying magnitudes (0, 0.1, 0.5, 1.0, 2.0 m). Re-render eval views
and measure PSNR drop. If photo loss is "redundant" (uniform texture allows
positional ambiguity), PSNR should barely change for sub-meter perturbations.

Restrict to one building (e.g., bid=21) to keep timing reasonable.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import torch

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.stage2.model import GaussianModel2D, quat_to_rotmat
from src.stage2.dataloader import ColmapDataset
from src.stage2.renderer import render
from scripts.stage3_readout.obj_gt import parse_scene_obj
from scripts.stage3_readout.run_stage3 import _assign_primitives_to_buildings


def psnr(pred, gt):
    mse = ((pred - gt) ** 2).mean()
    return -10.0 * torch.log10(mse + 1e-12)


def make_model(centers, quats, log_scales, opacities_raw, sem_logits, sh0, shN, device, max_sh=3):
    """Construct a GaussianModel2D from explicit tensors (preserves all params)."""
    model = GaussianModel2D.__new__(GaussianModel2D)
    torch.nn.Module.__init__(model)
    model.means = torch.nn.Parameter(centers.contiguous())
    model.quats = torch.nn.Parameter(quats.contiguous())
    model.log_scales = torch.nn.Parameter(log_scales.contiguous())
    model.opacities_raw = torch.nn.Parameter(opacities_raw.contiguous())
    model.sh0 = torch.nn.Parameter(sh0.contiguous())
    model.shN = torch.nn.Parameter(shN.contiguous())
    model.sem_logits = torch.nn.Parameter(sem_logits.contiguous())
    model.active_sh_degree = max_sh
    model.max_sh_degree = max_sh
    model.num_classes = 4
    return model.to(device)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", default="results/phase2_ablation_citygml/mutual/ckpt/final.pt")
    ap.add_argument("--data-root", default="results/phase2_synthesis/dataset")
    ap.add_argument("--scene", default="results/phase2_synthesis/scene.obj")
    ap.add_argument("--bid", type=int, default=21,
                    help="building id whose primitives we perturb (Phase 2 only)")
    ap.add_argument("--all-prims", action="store_true",
                    help="perturb ALL primitives (use for Phase 1, no per-bldg GT)")
    ap.add_argument("--n-views", type=int, default=20,
                    help="number of eval views to render")
    ap.add_argument("--shifts", type=str, default="0,0.1,0.3,0.5,1.0,2.0")
    ap.add_argument("--out", default="results/phase2_ablation_citygml/_perturb_test")
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    device = "cuda"

    print(f"[perturb] loading ckpt {args.ckpt}")
    sd = torch.load(args.ckpt, map_location="cpu")["state_dict"]
    means_full = sd["means"].float()
    quats_full = sd["quats"].float()
    log_scales_full = sd["log_scales"].float()
    opa_full = sd["opacities_raw"].float()
    sem_full = sd["sem_logits"].float()
    # SH coefficients
    sh0 = sd["sh0"].float()
    shN = sd["shN"].float()
    R = quat_to_rotmat(quats_full)
    normals_full = R[..., :, 2]
    N = means_full.shape[0]
    print(f"  N_primitives = {N:,}")

    print(f"[perturb] loading dataset {args.data_root}")
    ds = ColmapDataset(root=args.data_root, downscale=1.0,
                       load_depth=False, load_normal=False, load_semantic=False)
    print(f"  frames = {len(ds)}")
    # use eval split (every 10th frame, same as train.py)
    test_idx = [i for i in range(len(ds)) if i % 10 == 9][: args.n_views]
    print(f"  using {len(test_idx)} eval views")

    # Identify primitives to perturb
    if args.all_prims:
        bldg_idxs = np.arange(N, dtype=np.int64)
        print(f"[perturb] perturbing ALL {N:,} primitives")
    else:
        print(f"[perturb] assigning primitives to bid={args.bid}")
        gt = parse_scene_obj(Path(args.scene))
        opa = torch.sigmoid(opa_full).numpy()
        asgn = _assign_primitives_to_buildings(
            {"centers": means_full.numpy(), "opacities": opa},
            gt, pad=2.0, opacity_thresh=0.05)
        bldg_idxs = asgn.get(args.bid, np.array([], dtype=np.int64))
        print(f"  bldg primitives = {len(bldg_idxs):,}")
        if len(bldg_idxs) == 0:
            return

    # Move to GPU
    means_full = means_full.to(device)
    quats_full = quats_full.to(device)
    log_scales_full = log_scales_full.to(device)
    opa_full = opa_full.to(device)
    sem_full = sem_full.to(device)
    sh0 = sh0.to(device)
    shN = shN.to(device)
    normals_full = normals_full.to(device)
    bldg_idxs_t = torch.tensor(bldg_idxs, device=device, dtype=torch.long)

    shifts = [float(s) for s in args.shifts.split(",")]
    results = {}

    for shift in shifts:
        print(f"\n[perturb] shift = {shift:.2f} m")
        # Perturb only target building's primitives, perpendicular to their normals
        means_p = means_full.clone()
        if shift > 0:
            n_b = normals_full[bldg_idxs_t]
            # Normalize (should already be unit, just safety)
            n_b = n_b / (n_b.norm(dim=-1, keepdim=True) + 1e-9)
            means_p[bldg_idxs_t] = means_full[bldg_idxs_t] + shift * n_b

        model = make_model(means_p, quats_full, log_scales_full, opa_full,
                            sem_full, sh0, shN, device)

        # Render eval views
        psnrs = []
        with torch.no_grad():
            for vi in test_idx:
                item = ds[vi]
                w2c = item["w2c"].to(device)
                K = item["K"].to(device)
                img_gt = item["rgb"].to(device)  # (H,W,3) in [0,1]
                H, W = item["height"], item["width"]
                out = render(model, w2c, K, W, H, sh_degree=3, render_mode="RGB+ED")
                rgb = out["rgb"]  # (H, W, 3) per renderer.py
                p = float(psnr(rgb, img_gt))
                psnrs.append(p)
        results[shift] = {
            "psnr_mean": float(np.mean(psnrs)),
            "psnr_min": float(np.min(psnrs)),
            "psnr_max": float(np.max(psnrs)),
            "n_views": len(psnrs),
        }
        print(f"  PSNR mean = {results[shift]['psnr_mean']:.3f} dB  (range {results[shift]['psnr_min']:.2f}-{results[shift]['psnr_max']:.2f})")

    # Summary table
    print("\n" + "="*60)
    print(f"{'Shift (m)':>12}  {'PSNR (dB)':>12}  {'ΔPSNR':>10}")
    print("="*60)
    base = results[0.0]["psnr_mean"]
    for s in shifts:
        r = results[s]
        d = r["psnr_mean"] - base
        print(f"{s:>12.2f}  {r['psnr_mean']:>12.3f}  {d:>+9.3f}")
    print("="*60)

    out_path = out_dir / f"perturb_bid{args.bid}.json"
    with open(out_path, "w") as f:
        json.dump({"shifts": shifts, "results": results, "ckpt": args.ckpt,
                    "bid": args.bid, "n_views": args.n_views}, f, indent=2)
    print(f"\nwrote {out_path}")


if __name__ == "__main__":
    main()
