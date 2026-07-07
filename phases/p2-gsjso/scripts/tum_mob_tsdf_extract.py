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
    ap.add_argument("--data-root", default=DENSE,
                    help="COLMAP data root with images/sparse[/0] (default: original dense scene)")
    ap.add_argument("--max-views", type=int, default=0)
    ap.add_argument("--sh-degree", type=int, default=3)
    ap.add_argument("--targets", nargs="*", default=None,
                    help="building IDs to extract (default: the 11 make-or-break TARGETS)")
    ap.add_argument("--no-sem", action="store_true",
                    help="disable the GS-semantic feature pass (default: carry per-voxel class if ckpt has sem_logits)")
    A = ap.parse_args()
    dev = "cuda"
    KC = 4  # engine semantic classes: 0 BG / 1 Roof / 2 Wall / 3 Terrain (model.py num_classes)

    # boxes from footprints (UTM -> local), union of the target buildings (default 11; --targets to extend)
    target_list = A.targets if getattr(A, "targets", None) else TARGETS
    feats = json.load(open(A.geojson))["features"]
    tg = {f"DEBY_LOD2_{t}" for t in target_list}
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
    # P2-D Lever 3: per-Gaussian semantic logits for the GS-semantic classification read-out.
    sem = sd.get("sem_logits")
    do_sem = (sem is not None) and (not A.no_sem)
    if do_sem:
        sem = sem.to(dev)
        sem = sem.unsqueeze(0) if sem.ndim == 2 else sem   # (1,N,K) gsplat feature-color layout
        print(f"[sem] GS-semantic feature pass ON (K={sem.shape[-1]})")
    else:
        print("[sem] GS-semantic OFF (no sem_logits in ckpt or --no-sem); XYZ-only fusion")
    print(f"[model] N={means.shape[0]} ckpt={A.ckpt}")

    data_root = Path(A.data_root)
    sparse_dir = data_root / "sparse"
    if (sparse_dir / "0" / "cameras.bin").exists():
        sparse_dir = sparse_dir / "0"
    cams = read_cameras_bin(sparse_dir / "cameras.bin")
    imgs = list(read_images_bin(sparse_dir / "images.bin").values())
    if A.max_views:
        imgs = imgs[:A.max_views]

    keylist = []; clslist = []; OFF = 1 << 20; MUL = 1 << 21
    def add_keys(P, cls=None):
        q = torch.floor(P / A.voxel).to(torch.int64) + OFF
        k = (q[:, 0] * MUL + q[:, 1]) * MUL + q[:, 2]
        if cls is None:
            keylist.append(torch.unique(k).cpu()); return
        # one vote per (view, voxel): majority class among this view's pixels in the voxel.
        uk_v, inv_v = torch.unique(k, return_inverse=True)
        hist = torch.zeros((uk_v.shape[0], KC), device=P.device)
        hist.index_add_(0, inv_v, torch.nn.functional.one_hot(cls, KC).float())
        keylist.append(uk_v.cpu()); clslist.append(hist.argmax(1).to(torch.int64).cpu())

    n_surf = 0
    for i, im in enumerate(imgs):
        cam = cams[im.camera_id]
        K0 = cam.K(); W0, H0 = cam.width, cam.height
        s = 1.0 / A.downscale; W, H = int(round(W0 * s)), int(round(H0 * s))
        K = K0.copy(); K[:2, :] *= s
        Kt = torch.tensor(K, dtype=torch.float32, device=dev)
        uu, vv = np.meshgrid(np.arange(W), np.arange(H)); uu = uu.ravel(); vv = vv.ravel()
        ud = torch.tensor((uu - K[0, 2]) / K[0, 0], dtype=torch.float32, device=dev)
        vd = torch.tensor((vv - K[1, 2]) / K[1, 1], dtype=torch.float32, device=dev)
        R = torch.tensor(im.R(), dtype=torch.float32, device=dev); t = torch.tensor(im.tvec, dtype=torch.float32, device=dev)
        vm = torch.eye(4, device=dev); vm[:3, :3] = R; vm[:3, 3] = t
        with torch.no_grad():
            out = rasterization_2dgs(means=means, quats=quats, scales=scales, opacities=opac, colors=colors,
                viewmats=vm.unsqueeze(0), Ks=Kt.unsqueeze(0), width=W, height=H,
                near_plane=0.01, far_plane=1e10, render_mode="RGB+ED", depth_mode="expected", sh_degree=A.sh_degree)
            cls_pix = None
            if do_sem:
                # Same view/intrinsics → semantic logits land on the same pixels as the median-depth
                # surface; argmax of the alpha-composited logits = surface class for that pixel.
                fout = rasterization_2dgs(means=means, quats=quats, scales=scales, opacities=opac, colors=sem,
                    viewmats=vm.unsqueeze(0), Ks=Kt.unsqueeze(0), width=W, height=H,
                    near_plane=0.01, far_plane=1e10, render_mode="RGB", sh_degree=None)
                cls_pix = fout[0][0].reshape(-1, sem.shape[-1]).argmax(-1)  # (H*W,)
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
        keepm = sel & inbox
        Xw = Xw[keepm]
        if len(Xw):
            if do_sem:
                add_keys(Xw, cls_pix[m][keepm]); n_surf += len(Xw)
            else:
                add_keys(Xw); n_surf += len(Xw)
        if (i + 1) % 200 == 0:
            print(f"  view {i+1}/{len(imgs)}", flush=True)

    allk = torch.cat(keylist)
    if do_sem:
        allc = torch.cat(clslist)                                  # one class vote per (view, voxel)
        uk_all, inv_all = torch.unique(allk, return_inverse=True)
        cnt = torch.bincount(inv_all, minlength=uk_all.shape[0])
        hist = torch.zeros((uk_all.shape[0], KC))
        hist.index_add_(0, inv_all, torch.nn.functional.one_hot(allc, KC).float())
        vox_cls = hist.argmax(1)                                   # majority class across views
        n_total = len(uk_all); keep = cnt >= A.min_obs
        uk = uk_all[keep]; vox_cls = vox_cls[keep]
    else:
        uk, cnt = torch.unique(allk, return_counts=True)
        n_total = len(uk); uk = uk[cnt >= A.min_obs]; vox_cls = None
    print(f"[consensus] min_obs={A.min_obs}: kept {len(uk)}/{n_total} voxels")
    k = uk.numpy(); iz = (k % MUL) - OFF; k //= MUL; iy = (k % MUL) - OFF; ix = (k // MUL) - OFF
    P_local = (np.stack([ix, iy, iz], 1).astype(np.float64) + 0.5) * A.voxel
    P_utm = P_local + SHIFT
    P_class = vox_cls.numpy().astype(np.int32) if vox_cls is not None else None
    P_class_clean = P_class
    try:
        import open3d as o3d
        pc = o3d.geometry.PointCloud(); pc.points = o3d.utility.Vector3dVector(P_utm)
        pc2, ind = pc.remove_statistical_outlier(nb_neighbors=20, std_ratio=2.0)
        P_utm_clean = np.asarray(pc2.points)
        if P_class is not None:
            P_class_clean = P_class[np.asarray(ind, dtype=np.int64)]   # carry class through SOR reindex
        print(f"[sor] kept {len(P_utm_clean)}/{len(P_utm)}")
    except Exception as e:
        P_utm_clean = P_utm; print("[sor] skipped:", repr(e))
    Path(A.out).parent.mkdir(parents=True, exist_ok=True)
    save = dict(P_utm=P_utm, P_utm_clean=P_utm_clean, voxel=A.voxel, downscale=A.downscale)
    if P_class is not None:
        save.update(P_class=P_class, P_class_clean=P_class_clean,
                    class_names=np.array(["BG", "Roof", "Wall", "Terrain"]))
        u, c = np.unique(P_class_clean, return_counts=True)
        names = ["BG", "Roof", "Wall", "Terrain"]
        print("[sem] fused class dist:", {names[int(a)]: int(b) for a, b in zip(u, c)})
    np.savez(A.out, **save)
    print(f"[done] surf_backproj={n_surf} fused={len(P_local)} -> {A.out}")


if __name__ == "__main__":
    main()
