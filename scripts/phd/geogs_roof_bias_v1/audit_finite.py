import json
from pathlib import Path
import numpy as np
from plyfile import PlyData
T=Path('/task');out={}
for name in ['N','B+0.25','B+0.5','B+1.0','B-1.0']:
 out[name]={}
 for it in [8000,30000]:
  p=PlyData.read(str(T/'conditions'/name/f'model/point_cloud/iteration_{it}/point_cloud.ply'))['vertex']
  bad=~np.isfinite(np.column_stack([p[k] for k in ['x','y','z']])).all(1)
  fields={k:int((~np.isfinite(p[k])).sum()) for k in p.data.dtype.names if np.issubdtype(p[k].dtype,np.floating)}
  x={'total':len(p.data),'nonfinite_xyz':int(bad.sum()),'nonfinite_fields':{k:v for k,v in fields.items() if v}}
  mask=T/'conditions'/name/'observations/frozen_mask_30000.npy'
  if it==30000 and mask.exists():
   m=np.load(mask);x['nonfinite_xyz_protected']=int((bad&m).sum());x['nonfinite_xyz_unprotected']=int((bad&~m).sum())
  out[name][str(it)]=x
print(json.dumps(out,indent=2));(T/'provenance/checkpoint_finite_audit.json').write_text(json.dumps(out,indent=2))
