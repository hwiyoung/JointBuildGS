"""Step 1b — building-level GS quality + spike-target coverage (read-only analysis).

Runs in the P0 tools image (laspy + GDAL/ogr2ogr + matplotlib; no torch).
Consumes GS centers dumped by tum_qc_dump.py. Observation only — NO verdict.

Frames: GS centers are OPF-LOCAL. EPSG:25832 = local + SHIFT (pure translation,
scene_reference_frame.json base_to_canonical.shift; 02_opf2colmap.py:201-211).
"""
import os, sys, json, subprocess, math
import numpy as np
import laspy
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
from matplotlib.path import Path as MplPath

sys.path.insert(0, os.getcwd())
from src.stage2.colmap_io import read_cameras_bin, read_images_bin  # numpy-only

REPO = "/workspace/JointBuildGS"
SHIFT = np.array([690953.0, 5336071.0, 604.0])   # local + SHIFT = EPSG:25832
DENSE = f"{REPO}/phases/p0-audit/data/work/mvs/colmap_dense"
FP_GPKG = f"{REPO}/phases/p0-audit/data/work/w2/footprints_scene_aoi.gpkg"
ALS_DIR = f"{REPO}/phases/p0-audit/data/raw/als"
ANA = f"{REPO}/results/tum_transfer/analysis"
FIG = f"{REPO}/results/tum_transfer/analysis/figs"
os.makedirs(FIG, exist_ok=True)

TEXTURED = ["DEBY_LOD2_4906972", "DEBY_LOD2_4908023", "DEBY_LOD2_4906969"]
FAIL8 = ["DEBY_LOD2_42364609","DEBY_LOD2_42364659","DEBY_LOD2_42364663","DEBY_LOD2_4907182",
         "DEBY_LOD2_4907510","DEBY_LOD2_4908050","DEBY_LOD2_4908166","DEBY_LOD2_4908176"]

# ---------- load GS centers (-> utm) ----------
gz = np.load(f"{ANA}/gs_centers.npz")
m_local = gz["means"]; op = gz["opacity"]
keep = op > 0.05
m_utm = m_local[keep] + SHIFT
print(f"[gs] N_all={m_local.shape[0]} kept(op>0.05)={keep.sum()}")
gs_bbox = (m_utm[:,0].min(), m_utm[:,0].max(), m_utm[:,1].min(), m_utm[:,1].max())
print(f"[gs] utm bbox X[{gs_bbox[0]:.0f},{gs_bbox[1]:.0f}] Y[{gs_bbox[2]:.0f},{gs_bbox[3]:.0f}]")

# ---------- footprints -> geojson ----------
GJ = f"{ANA}/footprints_aoi.geojson"
if not os.path.exists(GJ):
    subprocess.run(["ogr2ogr","-f","GeoJSON",GJ,FP_GPKG], check=True)
feats = json.load(open(GJ))["features"]
def poly_xy(geom):
    rings=[]
    if geom["type"]=="Polygon": rings=[geom["coordinates"][0]]
    elif geom["type"]=="MultiPolygon": rings=[p[0] for p in geom["coordinates"]]
    return [np.array(r)[:,:2] for r in rings]
FP = {}
for f in feats:
    bid=f["properties"]["building_id"]
    FP.setdefault(bid, []).extend(poly_xy(f["geometry"]))
print(f"[fp] buildings in AOI gpkg: {len(FP)}")

def in_poly(xy, rings):
    m=np.zeros(len(xy),bool)
    for r in rings: m |= MplPath(r).contains_points(xy)
    return m
def fp_props(rings):
    allp=np.vstack(rings)
    cx,cy=allp[:,0].mean(),allp[:,1].mean()
    area=0.0
    for r in rings:
        x,y=r[:,0],r[:,1]; area+=0.5*abs(np.dot(x,np.roll(y,1))-np.dot(y,np.roll(x,1)))
    return cx,cy,area,(allp[:,0].min(),allp[:,0].max(),allp[:,1].min(),allp[:,1].max())

# ---------- poses (local frame) ----------
cams=read_cameras_bin(f"{DENSE}/sparse/cameras.bin"); cam=list(cams.values())[0]
K=cam.K(); fx,fy,cx0,cy0=K[0,0],K[1,1],K[0,2],K[1,2]; W,H=cam.width,cam.height
imgs=read_images_bin(f"{DENSE}/sparse/images.bin")
Rs=np.array([im.R() for im in imgs.values()]); ts=np.array([im.tvec for im in imgs.values()])
Cs=np.einsum("nij,nj->ni", np.transpose(Rs,(0,2,1)), -ts)  # cam centers, local
ground_local_z = float(np.median(m_local[keep][:,2]))      # scene ground proxy (local)

def coverage(cx,cy,z_utm):
    """Reproject building centroid (utm, real roof z) across all views -> views + off-nadir."""
    Xl=np.array([cx-SHIFT[0], cy-SHIFT[1], z_utm-SHIFT[2]])      # utm centroid -> local
    Xc=np.einsum("nij,j->ni",Rs,Xl)+ts                          # to each cam
    front=Xc[:,2]>0
    u=fx*Xc[:,0]/np.where(front,Xc[:,2],1)+cx0
    v=fy*Xc[:,1]/np.where(front,Xc[:,2],1)+cy0
    vis=front&(u>=0)&(u<W)&(v>=0)&(v<H)
    if vis.sum()==0: return 0,0,0,float("nan")
    vec=Cs[vis]-Xl                                              # building -> cam (local)
    ang=np.degrees(np.arccos(np.clip(vec[:,2]/np.linalg.norm(vec,axis=1),-1,1)))  # off-nadir
    return int(vis.sum()), int((ang<20).sum()), int((ang>=20).sum()), float(np.median(ang))

# ---------- ALS tiles ----------
_alscache={}
def als_tiles_for(bbox):
    x0,x1,y0,y1=bbox; out=[]
    for fn in os.listdir(ALS_DIR):
        if not fn.endswith(".laz"): continue
        tx,ty=fn[:-4].split("_"); tx=int(tx)*1000; ty=int(ty)*1000
        if tx<=x1 and tx+1000>=x0 and ty<=y1 and ty+1000>=y0: out.append(fn)
    return out
def als_points(bbox):
    x0,x1,y0,y1=bbox; xs=[];ys=[];zs=[];cs=[]
    for fn in als_tiles_for(bbox):
        if fn not in _alscache:
            la=laspy.read(f"{ALS_DIR}/{fn}")
            _alscache[fn]=(np.asarray(la.x),np.asarray(la.y),np.asarray(la.z),np.asarray(la.classification))
        X,Y,Z,C=_alscache[fn]
        msk=(X>=x0-2)&(X<=x1+2)&(Y>=y0-2)&(Y<=y1+2)
        xs.append(X[msk]);ys.append(Y[msk]);zs.append(Z[msk]);cs.append(C[msk])
    if not xs: return np.empty((0,3)),np.empty(0,int)
    return np.column_stack([np.concatenate(xs),np.concatenate(ys),np.concatenate(zs)]),np.concatenate(cs)

def als_ref_z(rings, bbox):
    """Real per-building roof z (utm) from ALS, for the coverage sight-angle."""
    P,Cl=als_points(bbox)
    if len(P)==0: return None
    ins=in_poly(P[:,:2],rings); P=P[ins]; Cl=Cl[ins]
    if len(P)==0: return None
    Pb=P[Cl==6] if (Cl==6).sum()>=8 else P
    return float(np.percentile(Pb[:,2],50))
def plane_rms(P):
    if len(P)<8: return float("nan")
    c=P.mean(0); _,_,Vt=np.linalg.svd(P-c); n=Vt[-1]
    return float(np.sqrt(np.mean(((P-c)@n)**2)))
def roof_metrics(P, area):
    """P=(M,3). returns dict: n, density, roof_rms, floater_pct."""
    if len(P)==0: return dict(n=0,dens=float("nan"),rms=float("nan"),floater=float("nan"))
    gz=np.percentile(P[:,2],5); up=P[P[:,2]>gz+1.5]
    roof=up if len(up)>=8 else P
    ref=np.percentile(roof[:,2],50)
    floater=float(100.0*np.mean(P[:,2]>ref+3.0))
    return dict(n=len(P), dens=len(roof)/area if area>0 else float("nan"),
                rms=plane_rms(roof), floater=floater, ref_z=ref)

# ================= (2) COVERAGE =================
print("\n## COVERAGE (reproject footprint centroid across 937 views)")
print("| building | group | in_AOI | roof_z_src | n_views | near-nadir(<20deg) | oblique(>=20) | median_offnadir |")
print("|---|---|---|---|---|---|---|---|")
cov_rows=[]
for grp,ids in [("fail8",FAIL8),("textured",TEXTURED)]:
    for bid in ids:
        if bid not in FP: print(f"| {bid} | {grp} | NO-FP | - | - | - | - | - |"); continue
        cxx,cyy,area,bbox=fp_props(FP[bid])
        in_aoi = (gs_bbox[0]-50<=cxx<=gs_bbox[1]+50) and (gs_bbox[2]-50<=cyy<=gs_bbox[3]+50)
        zref=als_ref_z(FP[bid], bbox); zsrc="ALS" if zref is not None else "proxy"
        zutm=zref if zref is not None else (ground_local_z+SHIFT[2])
        nv,nn,no,ma=coverage(cxx,cyy,zutm)
        cov_rows.append((bid,grp,in_aoi,zsrc,nv,nn,no,ma))
        print(f"| {bid.replace('DEBY_LOD2_','')} | {grp} | {'yes' if in_aoi else 'NO'} | {zsrc} | {nv} | {nn} | {no} | {ma:.1f} |")

# ================= (1) QUALITY GS vs ALS (textured reps) =================
print("\n## QUALITY GS vs ALS (textured representatives)")
print("| building | area_m2 | src | n_pts | roof_dens(pts/m2) | roof_plane_RMS(m) | floater% |")
print("|---|---|---|---|---|---|---|")
for bid in TEXTURED:
    if bid not in FP: print(f"| {bid} | NO-FP |||||"); continue
    rings=FP[bid]; cxx,cyy,area,bbox=fp_props(rings)
    # GS
    gmask=in_poly(m_utm[:,:2], rings); G=m_utm[gmask]
    gm=roof_metrics(G, area)
    # ALS
    P,Cl=als_points(bbox)
    if len(P):
        am_in=in_poly(P[:,:2], rings); P=P[am_in]; Cl=Cl[am_in]
        Pb = P[Cl==6] if (Cl==6).sum()>=8 else P   # building class if present
    else: Pb=P
    al=roof_metrics(Pb, area)
    print(f"| {bid.replace('DEBY_LOD2_','')} | {area:.0f} | GS  | {gm['n']} | {gm['dens']:.2f} | {gm['rms']:.3f} | {gm['floater']:.1f} |")
    print(f"| {bid.replace('DEBY_LOD2_','')} | {area:.0f} | ALS | {al['n']} | {al['dens']:.2f} | {al['rms']:.3f} | {al['floater']:.1f} |")
    # figure: GS top/side + ALS top/side
    fig,ax=plt.subplots(2,2,figsize=(12,10))
    def scat(a,P,ttl,view):
        if len(P)==0: a.set_title(ttl+" (empty)"); return
        if view=="top": a.scatter(P[:,0],P[:,1],c=P[:,2],s=2,cmap="turbo"); a.set_aspect("equal")
        else: a.scatter(P[:,0],P[:,2],c=P[:,2],s=2,cmap="turbo")
        a.set_title(ttl)
    short=bid.replace('DEBY_LOD2_','')
    scat(ax[0,0],G,f"GS top  n={gm['n']} dens={gm['dens']:.1f} rms={gm['rms']:.2f}","top")
    scat(ax[0,1],G,"GS side (x-z)","side")
    scat(ax[1,0],Pb,f"ALS top n={al['n']} dens={al['dens']:.1f} rms={al['rms']:.2f}","top")
    scat(ax[1,1],Pb,"ALS side (x-z)","side")
    fig.suptitle(f"{short} (area {area:.0f} m2) — GS(top) vs ALS(bottom)")
    plt.tight_layout(); plt.savefig(f"{FIG}/qc_{short}.png",dpi=110); plt.close()
    print(f"[fig] saved qc_{short}.png")

print("\n[done] analysis complete")
