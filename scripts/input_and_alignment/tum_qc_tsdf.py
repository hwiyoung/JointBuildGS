"""Step 1c P-b1 — per-building quality: GS-centers (1b) vs TSDF (depth-fusion) vs ALS.
Read-only analysis (P0 tools image). Observation only — NO verdict."""
import os,sys,json,numpy as np,laspy
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
from matplotlib.path import Path as MplPath
REPO="/workspace/JointBuildGS"; SHIFT=np.array([690953.0,5336071.0,604.0])
ANA=f"{REPO}/results/tum_transfer/analysis"; ALS_DIR=f"{REPO}/phases/p0-audit/data/raw/als"
FIG=f"{ANA}/figs"; os.makedirs(FIG,exist_ok=True)
REPS=["DEBY_LOD2_4906972","DEBY_LOD2_4906969","DEBY_LOD2_4908023"]

gz=np.load(f"{ANA}/gs_centers.npz"); CEN=gz["means"][gz["opacity"]>0.05]+SHIFT
TS=np.load(f"{ANA}/tsdf_points.npz")["P_utm_clean"]
feats=json.load(open(f"{ANA}/footprints_aoi.geojson"))["features"]
FP={}
for f in feats:
    g=f["geometry"]; rings=[g["coordinates"][0]] if g["type"]=="Polygon" else [p[0] for p in g["coordinates"]]
    FP.setdefault(f["properties"]["building_id"],[]).extend([np.array(r)[:,:2] for r in rings])
def inpoly(xy,rings):
    m=np.zeros(len(xy),bool)
    for r in rings: m|=MplPath(r).contains_points(xy)
    return m
def fpinfo(rings):
    allp=np.vstack(rings); a=0.0
    for r in rings:
        x,y=r[:,0],r[:,1]; a+=0.5*abs(np.dot(x,np.roll(y,1))-np.dot(y,np.roll(x,1)))
    return a,(allp[:,0].min(),allp[:,0].max(),allp[:,1].min(),allp[:,1].max())
def planerms(P):
    if len(P)<8: return float("nan")
    c=P.mean(0); X=P-c; C=(X.T@X)/len(X)          # 3x3 covariance (O(n))
    w,V=np.linalg.eigh(C); n=V[:,0]               # smallest-eigenvalue eigenvector = plane normal
    return float(np.sqrt(np.mean((X@n)**2)))
def metrics(P,area):
    if len(P)==0: return dict(n=0,dens=float("nan"),rms=float("nan"),fl=float("nan"))
    gz_=np.percentile(P[:,2],5); up=P[P[:,2]>gz_+1.5]; roof=up if len(up)>=8 else P
    ref=np.percentile(roof[:,2],50); fl=100.0*np.mean(P[:,2]>ref+3.0)
    return dict(n=len(P),dens=len(roof)/area if area>0 else float("nan"),rms=planerms(roof),fl=fl)
def clip(P,rings,bbox):
    x0,x1,y0,y1=bbox; m=(P[:,0]>=x0-1)&(P[:,0]<=x1+1)&(P[:,1]>=y0-1)&(P[:,1]<=y1+1)
    P=P[m]; return P[inpoly(P[:,:2],rings)] if len(P) else P
_ac={}
def als(bbox):
    x0,x1,y0,y1=bbox; out=[]
    for fn in os.listdir(ALS_DIR):
        if not fn.endswith(".laz"): continue
        tx,ty=fn[:-4].split("_"); tx,ty=int(tx)*1000,int(ty)*1000
        if tx<=x1 and tx+1000>=x0 and ty<=y1 and ty+1000>=y0:
            if fn not in _ac:
                la=laspy.read(f"{ALS_DIR}/{fn}"); _ac[fn]=np.column_stack([la.x,la.y,la.z,la.classification])
            out.append(_ac[fn])
    if not out: return np.empty((0,3))
    A=np.vstack(out); m=(A[:,0]>=x0-2)&(A[:,0]<=x1+2)&(A[:,1]>=y0-2)&(A[:,1]<=y1+2); A=A[m]
    b=A[A[:,3]==6]; return (b if len(b)>=8 else A)[:,:3]

print("## P-b1 QUALITY: GS-centers vs TSDF vs ALS (textured reps)")
print("| building | area_m2 | source | n_pts | roof_dens(pts/m2) | plane_RMS(m) | floater% |")
print("|---|---|---|---|---|---|---|")
for bid in REPS:
    rings=FP[bid]; area,bbox=fpinfo(rings); s=bid.replace("DEBY_LOD2_","")
    C=clip(CEN,rings,bbox); T=clip(TS,rings,bbox); Aa=als(bbox); Aa=Aa[inpoly(Aa[:,:2],rings)] if len(Aa) else Aa
    for nm,P in [("GS-center",C),("TSDF",T),("ALS",Aa)]:
        m=metrics(P,area)
        print(f"| {s} | {area:.0f} | {nm} | {m['n']} | {m['dens']:.2f} | {m['rms']:.3f} | {m['fl']:.1f} |")
    fig,ax=plt.subplots(2,3,figsize=(16,9))
    for j,(nm,P) in enumerate([("GS-center",C),("TSDF",T),("ALS",Aa)]):
        if len(P):
            Q=P[np.random.default_rng(0).choice(len(P),50000,replace=False)] if len(P)>50000 else P
            ax[0,j].scatter(Q[:,0],Q[:,1],c=Q[:,2],s=1,cmap="turbo"); ax[0,j].set_aspect("equal")
            ax[1,j].scatter(Q[:,0],Q[:,2],c=Q[:,2],s=1,cmap="turbo")
        ax[0,j].set_title(f"{nm} top  n={len(P)}"); ax[1,j].set_title(f"{nm} side (x-z)")
    fig.suptitle(f"{s} (area {area:.0f} m2) — top(row1)/side(row2): GS-center | TSDF | ALS")
    plt.tight_layout(); plt.savefig(f"{FIG}/tsdf_{s}.png",dpi=110); plt.close()
    print(f"[fig] tsdf_{s}.png")
print("[done]")
