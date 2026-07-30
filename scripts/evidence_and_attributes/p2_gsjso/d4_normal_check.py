#!/usr/bin/env python3
"""D4 점검1(나) — GT MVS normal map vs GS-rendered normal, 3 views over the AOI.
RGB = (n_world+1)/2. Goal: is the L_normal target (COLMAP PatchMatch normal_maps) clean+aligned,
or noisy? Read-only. Dev container (gsplat). EPSG:25832. GS-LOCAL frame; both world-frame normals.
"""
import sys, json
import numpy as np, torch
sys.path.insert(0, "/workspace/JointBuildGS")
from gsplat import rasterization_2dgs
from src.stage2.colmap_io import read_cameras_bin, read_images_bin, read_array
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

REPO = "/workspace/JointBuildGS"
DENSE = f"{REPO}/phases/p0-audit/data/work/mvs/colmap_dense"
MOB = f"{REPO}/results/tum_transfer/mob"
SHIFT = np.array([690953.0, 5336071.0, 604.0])
OUT = f"{REPO}/docs/figs/W_D_qual/d4_normals.png"


def rgb_n(n, mask=None):
    img = (n * 0.5 + 0.5).clip(0, 1)
    if mask is not None:
        img = img * mask[..., None]
    return img


def main():
    dev = "cuda"
    ck = torch.load(f"{MOB}/gs_prior_full_dense/ckpt/final.pt", map_location=dev, weights_only=False)["state_dict"]
    means = ck["means"].to(dev); quats = ck["quats"].to(dev)
    scales = torch.exp(ck["log_scales"]).to(dev); opac = torch.sigmoid(ck["opacities_raw"]).to(dev).ravel()
    colors = torch.cat([ck["sh0"], ck["shN"]], dim=1).to(dev)

    cam = list(read_cameras_bin(f"{DENSE}/sparse/cameras.bin").values())[0]
    K0 = cam.K(); W0, H0 = cam.width, cam.height
    imgs = list(read_images_bin(f"{DENSE}/sparse/images.bin").values())

    # AOI centre (UTM->local) and pick 3 views whose camera centre is nearest in XY
    base = json.load(open(f"{MOB}/baselines.json"))
    bcs = np.array([base[b]["bbox_utm"] for b in base])
    aoi = np.array([(bcs[:, 0].mean() + bcs[:, 2].mean()) / 2, (bcs[:, 1].mean() + bcs[:, 3].mean()) / 2]) - SHIFT[:2]
    cc = []
    for im in imgs:
        R = im.R(); t = im.tvec
        C = -R.T @ t
        cc.append(C[:2])
    cc = np.array(cc)
    order = np.argsort(((cc - aoi) ** 2).sum(1))
    pick = [imgs[i] for i in order[:9][::3][:3]]  # 3 spread among the 9 nearest

    fig, ax = plt.subplots(3, 2, figsize=(11, 12))
    for r, im in enumerate(pick):
        gtp = f"{DENSE}/stereo/normal_maps/{im.name}.geometric.bin"
        n_cam = read_array(gtp)  # (h,w,3) camera-frame
        h, w = n_cam.shape[:2]
        nn = np.linalg.norm(n_cam, axis=-1, keepdims=True)
        mask = nn[..., 0] > 1e-3
        n_cam = np.where(nn > 1e-6, n_cam / np.maximum(nn, 1e-6), 0.0)
        R = im.R(); R_c2w = R.T
        n_gt = (n_cam @ R_c2w.T).astype(np.float32)  # world frame (dataloader convention)
        # render GS normal at the same (w,h)
        s = w / W0
        K = K0.copy(); K[:2, :] *= s
        Kt = torch.tensor(K, dtype=torch.float32, device=dev)
        t = torch.tensor(im.tvec, dtype=torch.float32, device=dev)
        vm = torch.eye(4, device=dev); vm[:3, :3] = torch.tensor(R, dtype=torch.float32, device=dev); vm[:3, 3] = t
        with torch.no_grad():
            out = rasterization_2dgs(means=means, quats=quats, scales=scales, opacities=opac, colors=colors,
                viewmats=vm.unsqueeze(0), Ks=Kt.unsqueeze(0), width=w, height=h,
                near_plane=0.01, far_plane=1e10, render_mode="RGB+ED", depth_mode="expected", sh_degree=3)
        n_render = out[2][0].cpu().numpy()  # (h,w,3) world-frame
        nr = np.linalg.norm(n_render, axis=-1, keepdims=True)
        n_render = np.where(nr > 1e-6, n_render / np.maximum(nr, 1e-6), 0.0)
        cov = float(mask.mean())
        ax[r, 0].imshow(rgb_n(n_gt, mask)); ax[r, 0].set_title(f"{im.name[:22]}  GT MVS normal (valid {cov*100:.0f}%)", fontsize=9)
        ax[r, 1].imshow(rgb_n(n_render)); ax[r, 1].set_title("GS rendered normal", fontsize=9)
        for c in (0, 1):
            ax[r, c].set_xticks([]); ax[r, c].set_yticks([])
    fig.suptitle("D4 점검1(나): GT MVS PatchMatch normal vs GS render  (RGB=normal dir)", fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, 0.98))
    fig.savefig(OUT, dpi=105); print(f"[fig] -> {OUT}")


if __name__ == "__main__":
    main()
