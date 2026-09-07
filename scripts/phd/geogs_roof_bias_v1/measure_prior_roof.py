"""Area-uniform recovered-prior roof error, using shared samples before Z translation."""
from pathlib import Path
import csv,json,numpy as np
from scipy.spatial import cKDTree
from analyze import OriginalMesh,xyz_ply,stats,signed_distances
T=Path('/task');mesh=OriginalMesh(T/'provenance/original_mesh.npz')
gt=xyz_ply(T/'conditions/N/evaluation/gt_cropped.ply');kind,_=mesh.assign(gt);gt=gt[kind==1];tree=cKDTree(gt)
face=np.flatnonzero(mesh.kind==1);tri=mesh.v[mesh.f[face]];area=np.linalg.norm(np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]),axis=1)/2
rng=np.random.default_rng(0);chosen=rng.choice(len(face),size=200000,p=area/area.sum());uv=rng.random((len(chosen),2));u=np.sqrt(uv[:,0]);v=uv[:,1];tr=tri[chosen];p=(1-u[:,None])*tr[:,0]+(u*(1-v))[:,None]*tr[:,1]+(u*v)[:,None]*tr[:,2];normals=mesh.normals[face[chosen]]
rows=[]
for name,dz in [('N',0),('B+0.25',.25),('B+0.5',.5),('B+1.0',1.),('B-1.0',-1.)]:
 q=p.copy();q[:,2]+=dz;_,idx=tree.query(q,workers=8);e,normal=signed_distances(q-gt[idx],normals)
 rows.append(dict(condition=name,nominal_delta_z_m=dz,**stats(e),gt_roof_n=len(gt),source='recovered_mesh_proxy_only' if name=='N' else 'actual_shifted_recovered_mesh'))
 np.savez_compressed(T/'conditions'/name/'analysis/prior_roof_errors.npz',prediction=q,gt_nearest=gt[idx],signed_error=e,original_face_id=face[chosen])
with (T/'tables/prior_roof_error.csv').open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
(T/'provenance/prior_roof_measurement.json').write_text(json.dumps({'seed':0,'sample_n':200000,'sampling':'area-uniform original recovered target roof triangles; identical barycentric samples translated in Z across conditions','GT':'same fixed-crop GT, nearest-original-face roof label','signed_metric':'Euclidean nearest roof-GT distance signed by source roof normal; normal points up','N_limitation':'Recovered zero-shift mesh is a proxy; supplied original N author mesh is absent','scientific_verdict':None},indent=2))
print(json.dumps(rows,indent=2))
