"""Photo + Normal map 4-way compare for Mech1 + Mech2 evidence.

Both mechanisms act on primitive normals (n_i):
  - L_mutual: pushes Wall n_i → horizontal, Terrain n_i → vertical
  - L_structure: aligns n_i within a group to the group's representative normal

So a normal map rendering should directly reveal both improvements:
  - Baseline: walls show mixed/rainbow normals
  - Mutual/Both: walls show uniform color (consistent orientation)
  - Structure/Both: within-wall variation reduced (smoother color)

Also renders RGB photo to confirm photometric quality is preserved across conditions.

Output: for each view, a panel of 8 images (4 conds × {photo, normal}).
"""
from __future__ import annotations

import argparse
from pathlib import Path

import imageio.v2 as imageio
import numpy as np
import torch
import yaml

import sys; sys.path.insert(0, ".")
from src.stage2.dataloader import ColmapDataset
from src.stage2.model import GaussianModel2D
from src.stage2.renderer import render
from gsplat import rasterization_2dgs


def qn(q):
    q = q / np.maximum(np.linalg.norm(q, axis=1, keepdims=True), 1e-8)
    w, x, y, z = q[:, 0], q[:, 1], q[:, 2], q[:, 3]
    n = np.stack([2*(x*z+w*y), 2*(y*z-w*x), 1-2*(x*x+y*y)], axis=1)
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-8)
    return n


def normal_to_rgb(n):
    """Map normal (N,3) with components in [-1,1] to RGB in [0,1].
    Uses standard n → (n+1)/2 mapping so direction is preserved as color.
    """
    return (n * 0.5 + 0.5).astype(np.float32)


def load_model(ckpt, cfg, device, ds):
    m = GaussianModel2D(ds.points_xyz, ds.points_rgb,
                        sh_degree=cfg.get("sh_degree", 3), device=device).to(device)
    sd = torch.load(ckpt, map_location=device, weights_only=False)["state_dict"]
    for name, p in list(m.named_parameters()):
        t = sd.get(name)
        if t is None: continue
        if p.shape != t.shape:
            parts = name.split("."); obj = m
            for pp in parts[:-1]: obj = getattr(obj, pp)
            setattr(obj, parts[-1], torch.nn.Parameter(t.clone()))
        else:
            p.data.copy_(t)
    return m


def render_normal_map(model, w2c, K, W, H, device):
    """Render normal map by feeding per-primitive normals (as RGB) to gsplat as colors."""
    means = model.means.detach()
    quats = model.quats.detach()
    scales = model.scales.detach()
    opacities = model.opacities.detach()
    n_np = qn(quats.cpu().numpy())
    colors = torch.from_numpy(normal_to_rgb(n_np)).to(device).contiguous()
    out = rasterization_2dgs(
        means=means.contiguous(), quats=quats.contiguous(), scales=scales.contiguous(),
        opacities=opacities.contiguous(),
        colors=colors,
        viewmats=w2c.unsqueeze(0).to(device), Ks=K.unsqueeze(0).to(device),
        width=W, height=H,
        render_mode="RGB", sh_degree=None,
        backgrounds=torch.ones(1, 3, device=device),
    )
    return out[0][0].detach().clamp(0, 1).cpu().numpy()


def render_photo(model, w2c, K, W, H, device):
    out = render(model, w2c.to(device), K.to(device), W, H,
                 sh_degree=model.max_sh_degree, render_mode="RGB+ED")
    return out["rgb"].detach().clamp(0, 1).cpu().numpy()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="configs/matrixcity_step1_6.yaml")
    ap.add_argument("--views", nargs="+", type=int, default=[5083, 5528, 5368, 5328])
    ap.add_argument("--out-dir", default="results/phase1_ablation/figures/photo_normal_4way")
    args = ap.parse_args()

    cfg = yaml.safe_load(open(args.config))
    device = "cuda"
    ds = ColmapDataset(cfg["data_root"], downscale=cfg.get("downscale", 1.0),
                       load_depth=False, load_normal=False)

    conds = [
        ("Baseline", "results/phase1_semantic/run/ckpt/final.pt"),
        ("Mutual",   "results/phase1_mutual/run/ckpt/final.pt"),
        ("Structure","results/phase1_structure/run/ckpt/final.pt"),
        ("Both",     "results/phase1_ablation/run/ckpt/final.pt"),
    ]
    print("loading 4 models...")
    models = [(lbl, load_model(p, cfg, device, ds)) for lbl, p in conds]

    out = Path(args.out_dir); out.mkdir(parents=True, exist_ok=True)

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    for idx in args.views:
        b = ds[idx]
        gt_rgb = (b["rgb"].numpy() * 255).astype(np.uint8)
        w2c = b["w2c"]; K = b["K"]
        H, W = b["height"], b["width"]

        photos = []; normals = []
        for lbl, m in models:
            with torch.no_grad():
                rgb = render_photo(m, w2c, K, W, H, device)
                n_map = render_normal_map(m, w2c, K, W, H, device)
            photos.append((lbl, (rgb * 255).astype(np.uint8)))
            normals.append((lbl, (n_map * 255).astype(np.uint8)))
            imageio.imwrite(out / f"v{idx:04d}_{lbl}_photo.png", photos[-1][1])
            imageio.imwrite(out / f"v{idx:04d}_{lbl}_normal.png", normals[-1][1])

        # Compute diff maps: |normal - Baseline_normal|, amplified 3×
        base_n = normals[0][1].astype(np.int32)
        diff_normals = []
        for (lbl, nm) in normals[1:]:
            d = np.abs(nm.astype(np.int32) - base_n) * 3
            d = np.clip(d, 0, 255).astype(np.uint8)
            diff_normals.append((lbl, d))

        # 3-row matplotlib panel with labels
        fig, axes = plt.subplots(3, 5, figsize=(22, 9))
        axes[0, 0].imshow(gt_rgb); axes[0, 0].set_title("GT RGB", fontsize=12)
        for ax, (lbl, img) in zip(axes[0, 1:], photos):
            ax.imshow(img); ax.set_title(f"Photo — {lbl}", fontsize=12)
        axes[1, 0].axis("off"); axes[1, 0].text(0.5, 0.5, "(no GT normal)",
                                                 ha="center", va="center", fontsize=11, alpha=0.6)
        for ax, (lbl, img) in zip(axes[1, 1:], normals):
            ax.imshow(img); ax.set_title(f"Normal map — {lbl}", fontsize=12)
        axes[2, 0].axis("off"); axes[2, 0].text(0.5, 0.5, "Normal diff vs Baseline\n(3× amplified)",
                                                 ha="center", va="center", fontsize=11)
        # First diff slot empty (baseline vs baseline = 0)
        axes[2, 1].axis("off"); axes[2, 1].text(0.5, 0.5, "(baseline ref)",
                                                 ha="center", va="center", fontsize=11, alpha=0.6)
        for ax, (lbl, img) in zip(axes[2, 2:], diff_normals):
            ax.imshow(img); ax.set_title(f"Δnormal — {lbl} vs Baseline", fontsize=11)
        for ax in axes.flatten():
            ax.set_xticks([]); ax.set_yticks([])
        plt.tight_layout()
        plt.savefig(out / f"v{idx:04d}_panel.png", dpi=90, bbox_inches="tight")
        plt.close()
        print(f"wrote v{idx:04d}_panel.png")

    (out / "README.txt").write_text(
        "Layout per panel (3 rows × 5 cols):\n"
        "  Row 1 (photo):  GT | Baseline | Mutual | Structure | Both\n"
        "  Row 2 (normal): blank | Baseline | Mutual | Structure | Both\n"
        "  Row 3 (diff):   caption | (ref) | |Mutual-Base|×3 | |Structure-Base|×3 | |Both-Base|×3\n"
        "Normal map color: (n + 1) / 2 per component. Uniform color = consistent normal direction.\n"
        "Diff shows where each condition's normals deviate from baseline.\n"
    )


if __name__ == "__main__":
    main()
