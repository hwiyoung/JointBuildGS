"""Compute Phase 2 mIoU on rendered semantic vs GT segmentation."""
import sys, json
from pathlib import Path
import numpy as np
import torch

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.stage2.model import quat_to_rotmat
from src.stage2.dataloader import ColmapDataset
from src.stage2.renderer import render_semantic
from scripts.mutual_loss.perturb_psnr_test import make_model

CONDS = {
    "Baseline":  "results/phase2_ablation_citygml/baseline/ckpt/final.pt",
    "Mutual":    "results/phase2_ablation_citygml/mutual/ckpt/final.pt",
    "Structure": "results/phase2_ablation_citygml/structure/ckpt/final.pt",
    "Both":      "results/phase2_ablation_citygml/both/ckpt/final.pt",
}
K_CLASSES = 4  # BG, Roof, Wall, Terrain


def per_class_iou(pred, gt, K=K_CLASSES, ignore=0):
    """Both (H,W) int. Returns list[float] of K-1 (excluding ignore)."""
    ious = {}
    for c in range(1, K):
        p = (pred == c)
        g = (gt == c)
        valid = (gt != ignore)
        p = p & valid; g = g & valid
        inter = (p & g).sum()
        union = (p | g).sum()
        if union == 0:
            ious[c] = float('nan')
        else:
            ious[c] = float(inter) / float(union)
    return ious


def evaluate(ckpt, ds, eval_idx, device="cuda", n_max=20):
    sd = torch.load(ckpt, map_location="cpu")["state_dict"]
    means = sd["means"].float().to(device)
    quats = sd["quats"].float().to(device)
    log_scales = sd["log_scales"].float().to(device)
    opa_raw = sd["opacities_raw"].float().to(device)
    sem = sd["sem_logits"].float().to(device)
    sh0 = sd["sh0"].float().to(device)
    shN = sd["shN"].float().to(device)
    model = make_model(means, quats, log_scales, opa_raw, sem, sh0, shN, device)

    iou_per_class = {1: [], 2: [], 3: []}
    pixel_acc_list = []
    n = 0
    for vi in eval_idx:
        if n >= n_max:
            break
        item = ds[vi]
        if "semantic" not in item:
            continue
        H, W = item["height"], item["width"]
        w2c = item["w2c"].to(device)
        K = item["K"].to(device)
        gt = item["semantic"].cpu().numpy()  # (H, W)
        with torch.no_grad():
            sem_logits_render = render_semantic(model, w2c, K, W, H)  # (H, W, K)
        pred = sem_logits_render.argmax(-1).cpu().numpy()
        ious = per_class_iou(pred, gt)
        for c, v in ious.items():
            if not np.isnan(v):
                iou_per_class[c].append(v)
        # pixel-wise (excluding BG)
        valid = gt != 0
        if valid.any():
            pixel_acc_list.append(float((pred[valid] == gt[valid]).mean()))
        n += 1

    out = {
        "n_views": n,
        "iou_roof": float(np.mean(iou_per_class[1])) if iou_per_class[1] else float("nan"),
        "iou_wall": float(np.mean(iou_per_class[2])) if iou_per_class[2] else float("nan"),
        "iou_terrain": float(np.mean(iou_per_class[3])) if iou_per_class[3] else float("nan"),
        "pixel_acc": float(np.mean(pixel_acc_list)) if pixel_acc_list else float("nan"),
    }
    out["miou"] = float(np.nanmean([out["iou_roof"], out["iou_wall"], out["iou_terrain"]]))
    return out


def main():
    device = "cuda"
    ds = ColmapDataset(root="results/phase2_synthesis/dataset", downscale=1.0,
                       load_depth=False, load_normal=False, load_semantic=True)
    eval_idx = [i for i in range(len(ds)) if i % 10 == 9]
    print(f"[mIoU] {len(ds)} frames, {len(eval_idx)} eval views")

    results = {}
    for cond, ck in CONDS.items():
        if not (_ROOT / ck).exists():
            print(f"  {cond}: SKIP")
            continue
        print(f"\n=== {cond} ===")
        r = evaluate(str(_ROOT / ck), ds, eval_idx, device=device, n_max=20)
        print(f"  mIoU={r['miou']:.4f}   roof={r['iou_roof']:.4f}  wall={r['iou_wall']:.4f}  terrain={r['iou_terrain']:.4f}   pixel_acc={r['pixel_acc']:.4f}")
        results[cond] = r

    out = Path("results/phase2_ablation_citygml/_miou")
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "phase2_miou.json", "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nwrote {out}/phase2_miou.json")

    print("\n" + "="*70)
    print(f"{'Cond':<11} {'mIoU':>7} {'Roof':>8} {'Wall':>8} {'Terrain':>9} {'PixelAcc':>9}")
    print("="*70)
    for cond, r in results.items():
        print(f"{cond:<11} {r['miou']:>7.4f} {r['iou_roof']:>8.4f} {r['iou_wall']:>8.4f} {r['iou_terrain']:>9.4f} {r['pixel_acc']:>9.4f}")
    print("\nReference (Phase 1 Step 1-3 ablation REPORT):")
    print("  Baseline   0.635   roof 0.704  wall 0.616  terrain 0.585")
    print("  Mutual     0.626")
    print("  Structure  0.640")
    print("  Both       0.625")


if __name__ == "__main__":
    main()
