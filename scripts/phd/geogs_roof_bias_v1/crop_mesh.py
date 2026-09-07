"""Exact triangle clipping to one pre-result original-building XY bounding rectangle."""
import json,sys
from pathlib import Path
import numpy as np
import open3d as o3d
from plyfile import PlyData
T=Path('/task');name=sys.argv[1];root=T/'conditions'/name;dest=root/'evaluation';dest.mkdir(exist_ok=True)
z=np.load(T/'provenance/original_mesh.npz');v=z['vertices'];f=z['faces'][z['target_face_mask']];pts=v[f].reshape(-1,3);lo=pts.min(0);hi=pts.max(0)
contract={'source':'unbiased recovered CityGML DEBY_LOD2_4959323','xy_min':lo[:2].tolist(),'xy_max':hi[:2].tolist(),'z_unbounded':True,'crop_geometry':'exact triangle clipping to fixed XY bounding rectangle','scientific_verdict':None}
contract_path=T/'provenance/crop_contract.json'
if contract_path.exists():assert json.loads(contract_path.read_text())==contract
else:contract_path.write_text(json.dumps(contract,indent=2))
mesh_path=root/'model/train/ours_30000/fuse_post.ply';mesh=o3d.io.read_triangle_mesh(str(mesh_path));mv=np.asarray(mesh.vertices);mf=np.asarray(mesh.triangles);out=[];faces=[]
for tri in mv[mf]:
 if np.any(tri[:,:2].max(0)<lo[:2]) or np.any(tri[:,:2].min(0)>hi[:2]):continue
 p=list(tri)
 for axis,bound,sign in [(0,lo[0],1),(0,hi[0],-1),(1,lo[1],1),(1,hi[1],-1)]:
  q=[]
  for i,a in enumerate(p):
   b=p[(i+1)%len(p)];ia=(a[axis]-bound)*sign>=0;ib=(b[axis]-bound)*sign>=0
   if ia:q.append(a)
   if ia!=ib:q.append(a+(b-a)*((bound-a[axis])/(b[axis]-a[axis])))
  p=q
  if not p:break
 if len(p)>=3:
  start=len(out);out.extend(p)
  for i in range(1,len(p)-1):faces.append([start,start+i,start+i+1])
assert faces,'crop produced no faces'
clipped=o3d.geometry.TriangleMesh(o3d.utility.Vector3dVector(np.array(out)),o3d.utility.Vector3iVector(np.array(faces,dtype=np.int32)))
clipped.remove_degenerate_triangles();clipped.compute_vertex_normals();o3d.io.write_triangle_mesh(str(dest/'fuse_post_cropped.ply'),clipped)
ref=Path('/reference/r1_b1_sub002_transformed.ply');gt=o3d.io.read_point_cloud(str(ref));g=np.asarray(gt.points);mask=np.all((g[:,:2]>=lo[:2])&(g[:,:2]<=hi[:2]),axis=1);o3d.io.write_point_cloud(str(dest/'gt_cropped.ply'),gt.select_by_index(np.flatnonzero(mask)))
(dest/'crop_receipt.json').write_text(json.dumps(dict(contract,input_triangles=len(mf),output_triangles=len(clipped.triangles),gt_before=len(g),gt_after=int(mask.sum())),indent=2))
print('crop PASS',len(clipped.triangles),int(mask.sum()))
