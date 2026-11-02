"""Check GeoGS text sparse camera representation against initially locked binaries."""
import importlib.util
import numpy as np
from common import *
def main():
 spec=importlib.util.spec_from_file_location('camera_file_reader','/source/scene/colmap_loader.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);cfg=json.loads((CFG/'screen_sim.json').read_text());rows=[]
 for row in cfg['states']:
  if row['family']!='geogs':continue
  scene=Path(row['scene']);a=scene/'sparse/0';b=scene/'sparse_lod/0';binary=m.read_extrinsics_binary(a/'images.bin');text=m.read_extrinsics_text(b/'images.txt');aa={r.name.rsplit('.',1)[0]:r for r in binary.values()};bb={r.name.rsplit('.',1)[0]:r for r in text.values()};errors=[]
  for name in cfg['views']:
   x,y=aa[name],bb[name];errors.append(max(float(np.max(np.abs(x.qvec-y.qvec))),float(np.max(np.abs(x.tvec-y.tvec)))));assert x.camera_id==y.camera_id
  ia=m.read_intrinsics_binary(a/'cameras.bin');ib=m.read_intrinsics_text(b/'cameras.txt');intr=[]
  for k in {aa[n].camera_id for n in cfg['views']}:
   x,y=ia[k],ib[k];assert (x.model,x.width,x.height)==(y.model,y.width,y.height);intr.append(float(np.max(np.abs(x.params-y.params))))
  assert max(errors)<1e-10 and max(intr)<1e-10
  rows.append(dict(state=row['key'],training_views=len(errors),pose_max_abs_difference=max(errors),intrinsic_max_abs_difference=max(intr),status='PASS_EQUIVALENT_REPRESENTATION',note='Actual sparse_lod uses text; initial lock contains corresponding binary cameras. Equality is numerical, not byte identity.',files={str(p):sha(p) for p in [a/'images.bin',a/'cameras.bin',b/'images.txt',b/'cameras.txt',scene/'jbgs_calibration.json']},scientific_verdict=None))
 dump(OUT/'screen_sim/geogs_camera_binding.json',dict(rows=rows,scientific_verdict=None));dump(DOC/'screen_sim/tables/geogs_camera_binding.json',dict(rows=rows,scientific_verdict=None));print('GEOGS_CAMERA_BINDING',[(r['state'],r['pose_max_abs_difference'],r['intrinsic_max_abs_difference']) for r in rows])
if __name__=='__main__':main()
