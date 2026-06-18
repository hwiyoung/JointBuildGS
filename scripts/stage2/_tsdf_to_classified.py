"""Step 1c P-b2 helper — TSDF points (1 building, 25832) -> classified LAS.
Reuses P0 T4 classification: PDAL filters.smrf (ground=2) + filters.overlay
footprint (building=6), exactly as phases/p0-audit/scripts/04_classify.py:193-224.
Runs in P0 tools image (laspy + pdal CLI). EPSG:25832."""
import argparse, json, os, subprocess, numpy as np, laspy
from matplotlib.path import Path as MplPath

GROUND,BUILDING,UNCLASS=2,6,1
ap=argparse.ArgumentParser()
ap.add_argument("--bid",required=True)            # e.g. DEBY_LOD2_4906972
ap.add_argument("--buffer",type=float,default=15.0)
ap.add_argument("--outdir",default="/workspace/JointBuildGS/phases/p0-audit/runs/tum_e2e")
A=ap.parse_args()
ANA="/workspace/JointBuildGS/results/tum_transfer/analysis"
os.makedirs(A.outdir,exist_ok=True)

TS=np.load(f"{ANA}/tsdf_points.npz")["P_utm_clean"]
feats=json.load(open(f"{ANA}/footprints_aoi.geojson"))["features"]
fb=[f for f in feats if f["properties"]["building_id"]==A.bid]
geom=fb[0]["geometry"]
rings=[geom["coordinates"][0]] if geom["type"]=="Polygon" else [p[0] for p in geom["coordinates"]]
ring=np.array(rings[0])
x0,y0,x1,y1=ring[:,0].min(),ring[:,1].min(),ring[:,0].max(),ring[:,1].max()
m=(TS[:,0]>=x0-A.buffer)&(TS[:,0]<=x1+A.buffer)&(TS[:,1]>=y0-A.buffer)&(TS[:,1]<=y1+A.buffer)
P=TS[m]
print(f"[e2e] {A.bid}: TSDF pts in box+buf = {len(P)}")

# write raw LAS
raw=f"{A.outdir}/{A.bid}_tsdf_raw.las"
hdr=laspy.LasHeader(point_format=6,version="1.4")
hdr.offsets=[P[:,0].min(),P[:,1].min(),P[:,2].min()]; hdr.scales=[0.001,0.001,0.001]
las=laspy.LasData(hdr); las.x=P[:,0]; las.y=P[:,1]; las.z=P[:,2]
las.write(raw)

# footprint geojson with class=6 (PDAL overlay column)
fpg=f"{A.outdir}/{A.bid}_fp.geojson"
json.dump({"type":"FeatureCollection","features":[
    {"type":"Feature","properties":{"class":BUILDING},"geometry":geom}]}, open(fpg,"w"))

# PDAL pipeline (= 04_classify.py:193-224)
clf=f"{A.outdir}/{A.bid}_tsdf_classified.las"
pipe={"pipeline":[
    {"type":"readers.las","filename":raw},
    {"type":"filters.smrf","cell":1.0,"slope":0.15,"scalar":1.25,"threshold":0.5,"window":18.0,
     "ground_class":GROUND,"other_class":UNCLASS},
    {"type":"filters.overlay","dimension":"Classification","datasource":fpg,"column":"class",
     "where":f"Classification != {GROUND}"},
    {"type":"writers.las","filename":clf,"a_srs":"EPSG:25832","minor_version":4,"dataformat_id":3}]}
pj=f"{A.outdir}/{A.bid}_pipeline.json"; json.dump(pipe,open(pj,"w"),indent=2)
r=subprocess.run(["pdal","pipeline",pj],capture_output=True,text=True)
if r.returncode!=0: print("PDAL FAIL:",r.stderr[-500:]); raise SystemExit(1)

# class counts
c=laspy.read(clf)
cl=np.asarray(c.classification); u,n=np.unique(cl,return_counts=True)
print("[e2e] classified counts:", dict(zip(u.tolist(),n.tolist())))
print(f"[e2e] wrote {clf}")
