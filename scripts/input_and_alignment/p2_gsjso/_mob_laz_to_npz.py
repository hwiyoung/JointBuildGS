import sys, json, glob, numpy as np, laspy
REPO="/workspace/JointBuildGS"
SHIFT=np.array([690953.0,5336071.0,604.0])
TARGETS=["42364609","42364659","42364663","4907182","4907510","4908050","4908166","4908176","4906969","4908023","4906972"]
geo=json.load(open(f"{REPO}/results/tum_transfer/analysis/footprints_aoi.geojson"))["features"]
boxes=[]
for t in TARGETS:
    g=[f for f in geo if f["properties"]["building_id"]==f"DEBY_LOD2_{t}"][0]["geometry"]
    r=np.asarray(g["coordinates"][0] if g["type"]=="Polygon" else g["coordinates"][0][0])[:,:2]
    boxes.append([r[:,0].min()-20,r[:,1].min()-20,r[:,0].max()+20,r[:,1].max()+20])
src,out=sys.argv[1],sys.argv[2]
pts=[]
for laz in glob.glob(src):
    las=laspy.read(laz); X,Y,Z=np.asarray(las.x),np.asarray(las.y),np.asarray(las.z)
    keep=np.zeros(len(X),bool)
    for b in boxes: keep |= (X>=b[0])&(X<=b[2])&(Y>=b[1])&(Y<=b[3])
    if keep.any(): pts.append(np.column_stack([X[keep],Y[keep],Z[keep]]))
P=np.concatenate(pts) if pts else np.zeros((0,3))
np.savez(out,P_utm=P,P_utm_clean=P,voxel=0.0,downscale=1.0)
print(f"{out}: {len(P)} pts")
