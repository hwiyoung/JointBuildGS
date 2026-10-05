import json
from pathlib import Path
import numpy as np
import open3d as o3d
from plyfile import PlyData
T=Path('/task');A=Path('/artifacts/JointBuildGS');old=A/'phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/native_example'
def xyz(p):
 v=PlyData.read(str(p))['vertex'];return np.column_stack([v[k] for k in 'xyz']).astype(float)
gt=xyz(old/'evaluation_reference/r1_b1_sub002_transformed.ply');print('GT bbox',gt.min(0),gt.max(0),np.median(gt,0))
z=np.load(T/'provenance/mesh_recovery_candidate.npz');v=z['vertices_global']+z['shift'];f=z['faces'];labs=z['labels'];ids=z['building_ids']
prior=xyz(old/'scene/lod2_pcd.ply')[::10]
mesh=o3d.geometry.TriangleMesh(o3d.utility.Vector3dVector(v),o3d.utility.Vector3iVector(f));scene=o3d.t.geometry.RaycastingScene();scene.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(mesh));ans=scene.compute_closest_points(o3d.core.Tensor(prior.astype('float32')))
q=ans['points'].numpy();d=np.linalg.norm(prior-q,axis=1);ii=ans['primitive_ids'].numpy();res=prior-q
for label in np.unique(labs):
 m=labs[ii]==label;print(label,int(m.sum()),'dist',np.quantile(d[m],[.25,.5,.75,.9]),'res',np.quantile(res[m],[.1,.5,.9],axis=0))
center=np.median(gt,0);tri=v[f];xylo=tri[:,:,:2].min(1);xyhi=tri[:,:,:2].max(1)
near=np.all(xyhi>=gt.min(0)[:2],axis=1)&np.all(xylo<=gt.max(0)[:2],axis=1)
print('building candidates')
for bid in np.unique(ids[near]):
 m=ids==bid;p=tri[m].reshape(-1,3);pm=ids[ii]==bid
 print(bid, 'bounds',p.min(0),p.max(0), 'prior count',int(pm.sum()),'prior med',float(np.median(d[pm])) if pm.any() else None)
