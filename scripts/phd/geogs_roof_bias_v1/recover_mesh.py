"""Recover original-coordinate LoD2 surfaces and verify against author prior, not GT."""
import json,sys
from pathlib import Path
import xml.etree.ElementTree as etree
import numpy as np
import open3d as o3d
from shapely.geometry import Polygon
from shapely.ops import triangulate
from plyfile import PlyData
A=Path('/artifacts/JointBuildGS');T=Path('/task');out=T/'provenance';out.mkdir(exist_ok=True)
old=A/'phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1'
v=PlyData.read(str(old/'native_example/scene/lod2_pcd.ply'))['vertex']
prior=np.column_stack([v[k] for k in 'xyz']).astype(float)
# Rounded candidate is derived from shared camera translations, then tested against prior geometry.
shift=np.array([-690955.,-5336042.,-604.+45.66])
lo=prior.min(0)-shift-1;hi=prior.max(0)-shift+1
vertices=[];faces=[];labels=[];ids=[];hole_count=0;repaired_count=0
ns={'g':'http://www.opengis.net/gml','b':'http://www.opengis.net/citygml/building/2.0'}
for path in sorted((A/'phase-payloads/p0-audit/data/raw/lod2').glob('*.gml')):
 for _,b in etree.iterparse(str(path),events=('end',)):
  if not b.tag.endswith('}Building'):continue
  bid=b.get('{http://www.opengis.net/gml}id')
  for surf in (x for x in b.iter() if x.tag.split('}')[-1] in ('RoofSurface','WallSurface','GroundSurface')):
   kind=surf.tag.split('}')[-1]
   for poly in surf.findall('.//g:Polygon',ns):
    ring=poly.find('.//{http://www.opengis.net/gml}exterior//{http://www.opengis.net/gml}posList')
    if ring is None:continue
    xyz=np.fromstring(ring.text,sep=' ').reshape(-1,3)
    if np.any(xyz.max(0)<lo) or np.any(xyz.min(0)>hi):continue
    if np.linalg.norm(xyz[0]-xyz[-1])<1e-8:xyz=xyz[:-1]
    if len(xyz)<3:continue
    origin=xyz[0];_,s,vh=np.linalg.svd(xyz-origin,full_matrices=False)
    if s[1]<1e-8:continue
    uv=(xyz-origin)@vh[:2].T
    holes=[]
    for ring in poly.findall('.//g:interior//g:posList',ns):
     h=np.fromstring(ring.text,sep=' ').reshape(-1,3)
     holes.append((h-origin)@vh[:2].T)
    hole_count+=len(holes)
    p=Polygon(uv,holes)
    if not p.is_valid:p=p.buffer(0);repaired_count+=1
    for tri in triangulate(p):
     if not p.covers(tri):continue
     q=np.array(tri.exterior.coords)[:3]@vh[:2]+origin
     normal=np.sum(np.cross(xyz,np.roll(xyz,-1,axis=0)),axis=0)
     if np.dot(np.cross(q[1]-q[0],q[2]-q[0]),normal)<0:q=q[[0,2,1]]
     start=len(vertices);vertices.extend(q);faces.append([start,start+1,start+2]);labels.append(kind);ids.append(bid)
  b.clear()
vertices=np.array(vertices);faces=np.array(faces,dtype=np.int32)
mesh=o3d.geometry.TriangleMesh(o3d.utility.Vector3dVector(vertices+shift),o3d.utility.Vector3iVector(faces))
scene=o3d.t.geometry.RaycastingScene();scene.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(mesh))
sample=prior[::10];ans=scene.compute_closest_points(o3d.core.Tensor(sample.astype('float32')))
closest=ans['points'].numpy();d=np.linalg.norm(sample-closest,axis=1)
report={'candidate_global_to_example_shift_including_datum':shift.tolist(),'n_faces':len(faces),'n_prior_check':len(d),'distance_quantiles':np.quantile(d,[0,.5,.9,.95,.99,1]).tolist(),'fraction_under_1cm':float(np.mean(d<.01)),'nearest_residual_median':np.median(sample-closest,0).tolist(),'reference_source':'OPF frame plus shared camera translation and official 45.66m datum offset; candidate only until geometry verification','scientific_verdict':None}
report.update(interior_rings_preserved=hole_count,invalid_polygons_repaired=repaired_count)
(out/'mesh_recovery_candidate.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
np.savez(out/'mesh_recovery_candidate.npz',vertices_global=vertices,faces=faces,labels=np.array(labels),building_ids=np.array(ids),shift=shift)
