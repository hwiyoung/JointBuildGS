#!/usr/bin/env python3
"""P2 make-or-break — per-config 2DGS surface point extraction over the 11 make-or-break buildings.

Generalises scripts/stage2/tum_tsdf_extract.py: same median-depth render -> backproject ->
voxel fusion (multi-view consensus min-obs) -> SOR, but clips to the union of the 11
make-or-break footprint boxes (from footprints_aoi.geojson) instead of 3 hardcoded boxes.

Run in the dev container (GPU). Engine logic unchanged (standalone analysis script using gsplat).
Frame: points GS-LOCAL; EPSG:25832 = local + [690953,5336071,604].
"""
import argparse, json, sys
from pathlib import Path
import numpy as np, torch
sys.path.insert(0, "/workspace/JointBuildGS")
from gsplat import rasterization_2dgs
from src.stage2.colmap_io import read_cameras_bin, read_images_bin

REPO = "/workspace/JointBuildGS"
DENSE = f"{REPO}/phases/p0-audit/data/work/mvs/colmap_dense"
SHIFT = np.array([690953.0, 5336071.0, 604.0])
TARGETS = ["42364609", "42364659", "42364663", "4907182", "4907510", "4908050",
           "4908166", "4908176", "4906969", "4908023", "4906972"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--downscale", type=float, default=1.0)
    ap.add_argument("--voxel", type=float, default=0.05)
    ap.add_argument("--alpha", type=float, default=0.5)
    ap.add_argument("--min-obs", type=int, default=3)
    ap.add_argument("--buffer", type=float, default=15.0)
    ap.add_argument("--geojson", default=f"{REPO}/results/tum_transfer/analysis/footprints_aoi.geojson")
    ap.add_argument("--max-views", type=int, default=0)
    ap.add_argument("--sh-degree", type=int, default=3)
    A = ap.parse_args()
    dev = "cuda"

    # boxes from footprints (UTM -> local), union of the 11 targets
    feats = json.load(open(A.geojson))["features"]
    tg = {f"DEBY_LOD2_{t}" for t in TARGETS}
    boxes = []
    for f in feats:
        if f["properties"].get("building_id") in tg:
            g = f["geometry"]
            ring = np.asarray(g["coordinates"][0] if g["type"] == "Polygon" else g["coordinates"][0][0])
            x0, y0 = ring[:, 0].min() - A.buffer, ring[:, 1].min() - A.buffer
            x1, y1 = ring[:, 0].max() + A.buffer, ring[:, 1].max() + A.buffer
            boxes.append([x0 - SHIFT[0], y0 - SHIFT[1], x1 - SHIFT[0], y1 - SHIFT[1]])
    print(f"[boxes] {len(boxes)} target footprint boxes")
    ZLO, ZHI = -120.0, 80.0

    ck = torch.load(A.ckpt, map_location=dev, weights_only=False)
    sd = ck["state_dict"]
    means = sd["means"].to(dev); quats = sd["quats"].to(dev)
    scales = torch.exp(sd["log_scales"]).to(dev); opac = torch.sigmoid(sd["opacities_raw"]).to(dev).ravel()
    colors = torch.cat([sd["sh0"], sd["shN"]], dim=1).to(dev)
    print(f"[model] N={means.shape[0]} ckpt={A.ckpt}")

    cam = list(read_cameras_bin(f"{DENSE}/sparse/cameras.bin").values())[0]
    K0 = cam.K(); W0, H0 = cam.width, cam.height
    imgs = list(read_images_bin(f"{DENSE}/sparse/images.bin").values())
    if A.max_views:
        imgs = imgs[:A.max_views]

    s = 1.0 / A.downscale; W, H = int(round(W0 * s)), int(round(H0 * s))
    K = K0.copy(); K[:2, :] *= s
    Kt = torch.tensor(K, dtype=torch.float32, device=dev)
    uu, vv = np.meshgrid(np.arange(W), np.arange(H)); uu = uu.ravel(); vv = vv.ravel()
    ud = torch.tensor((uu - K[0, 2]) / K[0, 0], dtype=torch.float32, device=dev)
    vd = torch.tensor((vv - K[1, 2]) / K[1, 1], dtype=torch.float32, device=dev)

    keylist = []; OFF = 1 << 20; MUL = 1 << 21
    def add_keys(P):
        q = torch.floor(P / A.voxel).to(torch.int64) + OFF
        k = (q[:, 0] * MUL + q[:, 1]) * MUL + q[:, 2]
        keylist.append(torch.unique(k).cpu())

    n_surf = 0
    for i, im in enumerate(imgs):
        R = torch.tensor(im.R(), dtype=torch.float32, device=dev); t = torch.tensor(im.tvec, dtype=torch.float32, device=dev)
        vm = torch.eye(4, device=dev); vm[:3, :3] = R; vm[:3, 3] = t
        with torch.no_grad():
            out = rasterization_2dgs(means=means, quats=quats, scales=scales, opacities=opac, colors=colors,
                viewmats=vm.unsqueeze(0), Ks=Kt.unsqueeze(0), width=W, height=H,
                near_plane=0.01, far_plane=1e10, render_mode="RGB+ED", depth_mode="expected", sh_degree=A.sh_degree)
        alpha = out[1][0, ..., 0].reshape(-1); med = out[5][0, ..., 0].reshape(-1)
        m = (alpha > A.alpha) & (med > 0) & (med < 500)
        if m.sum() == 0:
            continue
        d = med[m]; xc = ud[m] * d; yc = vd[m] * d; Xc = torch.stack([xc, yc, d], 1)
        Xw = (Xc - t) @ R
        sel = (Xw[:, 2] >= ZLO) & (Xw[:, 2] <= ZHI)
        inbox = torch.zeros_like(sel)
        for bx in boxes:
            inbox |= (Xw[:, 0] >= bx[0]) & (Xw[:, 0] <= bx[2]) & (Xw[:, 1] >= bx[1]) & (Xw[:, 1] <= bx[3])
        Xw = Xw[sel & inbox]
        if len(Xw):
            add_keys(Xw); n_surf += len(Xw)
        if (i + 1) % 200 == 0:
            print(f"  view {i+1}/{len(imgs)}", flush=True)

    allk = torch.cat(keylist)
    uk, cnt = torch.unique(allk, return_counts=True)
    n_total = len(uk)
    uk = uk[cnt >= A.min_obs]
    print(f"[consensus] min_obs={A.min_obs}: kept {len(uk)}/{n_total} voxels")
    k = uk.numpy(); iz = (k % MUL) - OFF; k //= MUL; iy = (k % MUL) - OFF; ix = (k // MUL) - OFF
    P_local = (np.stack([ix, iy, iz], 1).astype(np.float64) + 0.5) * A.voxel
    P_utm = P_local + SHIFT
    try:
        import open3d as o3d
        pc = o3d.geometry.PointCloud(); pc.points = o3d.utility.Vector3dVector(P_utm)
        pc2, _ = pc.remove_statistical_outlier(nb_neighbors=20, std_ratio=2.0)
        P_utm_clean = np.asarray(pc2.points); print(f"[sor] kept {len(P_utm_clean)}/{len(P_utm)}")
    except Exception as e:
        P_utm_clean = P_utm; print("[sor] skipped:", repr(e))
    Path(A.out).parent.mkdir(parents=True, exist_ok=True)
    np.savez(A.out, P_utm=P_utm, P_utm_clean=P_utm_clean, voxel=A.voxel, downscale=A.downscale)
    print(f"[done] surf_backproj={n_surf} fused={len(P_local)} -> {A.out}")


if __name__ == "__main__":
    main()
