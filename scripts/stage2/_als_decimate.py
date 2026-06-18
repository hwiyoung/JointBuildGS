"""Step 1c P-a helper — decimate/noise classified ALS to a target density, write LAS.
Runs in P0 tools image (laspy). Preserves classification (ground=2, building=6).
EPSG:25832 (ALS native frame). Used to measure the Roofer density/noise floor."""
import argparse, os, numpy as np, laspy

ap=argparse.ArgumentParser()
ap.add_argument("--box", nargs=4, type=float, required=True)   # x0 y0 x1 y1 (utm)
ap.add_argument("--density", type=float, required=True)        # target pts/m2
ap.add_argument("--noise", type=float, default=0.0)            # gaussian z noise sigma (m)
ap.add_argument("--als-dir", default="/workspace/JointBuildGS/phases/p0-audit/data/raw/als")
ap.add_argument("--out", required=True)
ap.add_argument("--seed", type=int, default=0)
A=ap.parse_args()
x0,y0,x1,y1=A.box

xs=[];ys=[];zs=[];cs=[]
for fn in os.listdir(A.als_dir):
    if not fn.endswith(".laz"): continue
    tx,ty=fn[:-4].split("_"); tx,ty=int(tx)*1000,int(ty)*1000
    if tx<=x1 and tx+1000>=x0 and ty<=y1 and ty+1000>=y0:
        la=laspy.read(f"{A.als_dir}/{fn}")
        X,Y,Z,C=np.asarray(la.x),np.asarray(la.y),np.asarray(la.z),np.asarray(la.classification)
        m=(X>=x0)&(X<=x1)&(Y>=y0)&(Y<=y1)
        xs.append(X[m]);ys.append(Y[m]);zs.append(Z[m]);cs.append(C[m])
X=np.concatenate(xs);Y=np.concatenate(ys);Z=np.concatenate(zs);C=np.concatenate(cs)
keep=(C==2)|(C==6); X,Y,Z,C=X[keep],Y[keep],Z[keep],C[keep]
area=(x1-x0)*(y1-y0); n0=len(X); dens0=n0/area
target=int(A.density*area)
rng=np.random.default_rng(A.seed)
if target<n0:
    idx=rng.choice(n0,size=target,replace=False); X,Y,Z,C=X[idx],Y[idx],Z[idx],C[idx]
if A.noise>0: Z=Z+rng.normal(0,A.noise,size=len(Z))
dens=len(X)/area
print(f"[decimate] box_area={area:.0f}m2 src_n={n0}(dens {dens0:.1f}) -> out_n={len(X)}(dens {dens:.2f}) noise={A.noise}")

hdr=laspy.LasHeader(point_format=6, version="1.4")
hdr.offsets=[X.min(),Y.min(),Z.min()]; hdr.scales=[0.001,0.001,0.001]
las=laspy.LasData(hdr)
las.x=X; las.y=Y; las.z=Z; las.classification=C.astype(np.uint8)
os.makedirs(os.path.dirname(A.out),exist_ok=True)
las.write(A.out)
print(f"[decimate] wrote {A.out}  achieved_density={dens:.2f}")
