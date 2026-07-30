"""Step 1c P-b1 — standard 2DGS surface point extraction from the 7k checkpoint.

depth render (median depth, accumulated opacity >0.5 = the 2DGS surface;
renderer.py:67,92) -> per-view backprojection -> voxel fusion -> floater removal.
This is the "fused depth points" path (faithful to 2DGS surface extraction);
no Open3D TSDF volume because the scene is ~500 m (uniform TSDF would blow up).
No retraining; depth rendered at native res (downscale-independent).

Frame: points stay GS-LOCAL; EPSG:25832 = local + [690953,5336071,604].
Engine logic unchanged — this is a standalone analysis script using gsplat directly.
"""
import os, sys, argparse, numpy as np, torch
from pathlib import Path
sys.path.insert(0, "/workspace/JointBuildGS")
from gsplat import rasterization_2dgs
from src.stage2.colmap_io import read_cameras_bin, read_images_bin

ap = argparse.ArgumentParser()
ap.add_argument("--downscale", type=float, default=1.0)   # 1.0 = native 1400x1013
ap.add_argument("--voxel", type=float, default=0.05)
ap.add_argument("--alpha", type=float, default=0.5)       # accumulated-opacity surface threshold
ap.add_argument("--max-views", type=int, default=0)       # 0 = all
ap.add_argument("--min-obs", type=int, default=1)         # multi-view consensus: keep voxels seen by >= N views
ap.add_argument("--ckpt", default="")                     # checkpoint path (default = 7k smoke run)
ap.add_argument("--sh-degree", type=int, default=3)
ap.add_argument("--out", default="/workspace/JointBuildGS/results/tum_transfer/analysis/tsdf_points.npz")
A = ap.parse_args()

REPO="/workspace/JointBuildGS"; DENSE=f"{REPO}/phases/p0-audit/data/work/mvs/colmap_dense"
SHIFT=np.array([690953.0,5336071.0,604.0])
dev="cuda"
CKPT=A.ckpt if getattr(A,"ckpt",None) else f"{REPO}/results/tum_transfer/run/ckpt/final.pt"
ck=torch.load(CKPT, map_location=dev, weights_only=False)
sd=ck["state_dict"]
means=sd["means"].to(dev); quats=sd["quats"].to(dev)
scales=torch.exp(sd["log_scales"]).to(dev); opac=torch.sigmoid(sd["opacities_raw"]).to(dev).ravel()
colors=torch.cat([sd["sh0"],sd["shN"]],dim=1).to(dev)     # (N,16,3) SH
print(f"[model] N={means.shape[0]}")

cam=list(read_cameras_bin(f"{DENSE}/sparse/cameras.bin").values())[0]
K0=cam.K(); W0,H0=cam.width,cam.height
imgs=list(read_images_bin(f"{DENSE}/sparse/images.bin").values())
if A.max_views: imgs=imgs[:A.max_views]

# Clip to the 3 textured-rep building boxes (+15 m ground-context buffer), utm -> local.
# Tight boxes keep the fused cloud small; z kept wide to still capture floaters above roofs.
BUF=15.0
BOXES_UTM=[[690933.23,5335923.58,690964.54,5335948.06],   # 4906972
           [690916.69,5336008.57,690935.67,5336025.35],   # 4906969
           [690906.287,5336108.243,690911.891,5336115.248]]# 4908023
BOXES=[[b[0]-BUF-SHIFT[0],b[1]-BUF-SHIFT[1],b[2]+BUF-SHIFT[0],b[3]+BUF-SHIFT[1]] for b in BOXES_UTM]
ZLO,ZHI=-60.0,80.0

s=1.0/A.downscale; W,H=int(round(W0*s)),int(round(H0*s))
K=K0.copy(); K[:2,:]*=s
Kt=torch.tensor(K,dtype=torch.float32,device=dev)
uu,vv=np.meshgrid(np.arange(W),np.arange(H)); uu=uu.ravel(); vv=vv.ravel()
ud=torch.tensor((uu-K[0,2])/K[0,0],dtype=torch.float32,device=dev)
vd=torch.tensor((vv-K[1,2])/K[1,1],dtype=torch.float32,device=dev)

keylist=[]; OFF=1<<20; MUL=1<<21
def add_keys(P):  # P (M,3) local float -> per-view-unique packed int64 voxel keys (kept on CPU)
    q=torch.floor(P/A.voxel).to(torch.int64)+OFF
    k=(q[:,0]*MUL+q[:,1])*MUL+q[:,2]
    keylist.append(torch.unique(k).cpu())   # per-view unique -> count over views = multi-view consensus

n_surf=0
for i,im in enumerate(imgs):
    R=torch.tensor(im.R(),dtype=torch.float32,device=dev); t=torch.tensor(im.tvec,dtype=torch.float32,device=dev)
    vm=torch.eye(4,device=dev); vm[:3,:3]=R; vm[:3,3]=t
    with torch.no_grad():
        out=rasterization_2dgs(means=means,quats=quats,scales=scales,opacities=opac,colors=colors,
            viewmats=vm.unsqueeze(0),Ks=Kt.unsqueeze(0),width=W,height=H,
            near_plane=0.01,far_plane=1e10,render_mode="RGB+ED",depth_mode="expected",sh_degree=A.sh_degree)
    alpha=out[1][0,...,0].reshape(-1); med=out[5][0,...,0].reshape(-1)
    m=(alpha>A.alpha)&(med>0)&(med<500)
    if m.sum()==0: continue
    d=med[m]; xc=ud[m]*d; yc=vd[m]*d; Xc=torch.stack([xc,yc,d],1)
    Xw=(Xc-t)@R                      # local world = R^T (Xc - t)
    sel=(Xw[:,2]>=ZLO)&(Xw[:,2]<=ZHI)
    inbox=torch.zeros_like(sel)
    for bx in BOXES:
        inbox |= (Xw[:,0]>=bx[0])&(Xw[:,0]<=bx[2])&(Xw[:,1]>=bx[1])&(Xw[:,1]<=bx[3])
    Xw=Xw[sel&inbox]
    if len(Xw): add_keys(Xw); n_surf+=len(Xw)
    if (i+1)%100==0: print(f"  view {i+1}/{len(imgs)}  view_key_chunks={len(keylist)}",flush=True)

allk=torch.cat(keylist)                                    # all per-view-unique voxel keys
uk,cnt=torch.unique(allk,return_counts=True)               # cnt = number of views observing each voxel
n_total=len(uk)
uk=uk[cnt>=A.min_obs]
print(f"[consensus] min_obs={A.min_obs}: kept {len(uk)}/{n_total} voxels (dropped sparsely-observed = floaters)")
k=uk.numpy(); iz=(k%MUL)-OFF; k//=MUL; iy=(k%MUL)-OFF; ix=(k//MUL)-OFF
P_local=(np.stack([ix,iy,iz],1).astype(np.float64)+0.5)*A.voxel
P_utm=P_local+SHIFT
print(f"[fuse] surf_backproj={n_surf}  fused_voxels(min_obs>={A.min_obs})={len(P_local)}  @ {A.voxel}m")

# floater removal (statistical outlier) via open3d if available
try:
    import open3d as o3d
    pc=o3d.geometry.PointCloud(); pc.points=o3d.utility.Vector3dVector(P_utm)
    pc2,ind=pc.remove_statistical_outlier(nb_neighbors=20,std_ratio=2.0)
    P_utm_clean=np.asarray(pc2.points); print(f"[sor] kept {len(P_utm_clean)}/{len(P_utm)} after outlier removal")
except Exception as e:
    P_utm_clean=P_utm; print("[sor] skipped:",repr(e))

Path(A.out).parent.mkdir(parents=True,exist_ok=True)
np.savez(A.out, P_utm=P_utm, P_utm_clean=P_utm_clean, voxel=A.voxel, downscale=A.downscale)
print(f"[done] saved {A.out}")
