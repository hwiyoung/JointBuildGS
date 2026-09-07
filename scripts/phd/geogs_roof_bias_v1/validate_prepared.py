import json,sys
from pathlib import Path
import numpy as np
from plyfile import PlyData
T=Path('/task');O=Path('/original_scene');a=json.loads((T/'provenance/axis_validation.json').read_text());assert a['status']=='PASS_UP_AXIS'
p=PlyData.read(str(O/'lod2_pcd.ply'))['vertex'].data
results=[]
for name,dz in [('B+0.25',.25),('B+0.5',.5),('B+1.0',1),('B-1.0',-1)]:
 s=T/'conditions'/name/'scene';q=PlyData.read(str(s/'lod2_pcd.ply'))['vertex'].data
 assert len(p)==len(q)
 for key in p.dtype.names:
  if key=='z':assert np.max(np.abs(q[key].astype(float)-p[key].astype(float)-dz))<1e-5
  else:assert np.array_equal(p[key],q[key]),key
 for key in ['images','da3_prior','sparse']:assert (s/key).is_symlink()
 for key in ['images.bin','cameras.bin']:assert (s/'sparse_lod/0'/key).read_bytes()==(O/'sparse/0'/key).read_bytes()
 assert len(list((s/'images').iterdir()))==15
 results.append({'condition':name,'protected_point_count':len(p),'delta_z_m':dz,'preserved_other_attributes':True,'camera_pose_bytes_identical':True})
(T/'provenance/prepared_validation.json').write_text(json.dumps({'status':'PASS','checks':results,'scientific_verdict':None},indent=2));print('PASS prepared inputs: biased protection clouds, unchanged images/DA3/poses, 15 views each')
