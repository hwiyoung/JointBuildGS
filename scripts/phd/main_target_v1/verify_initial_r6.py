"""CPU check: the actual new pilot initialization equals the accepted r4n initialization."""
import numpy as np
from common import *
def main():
 rows=[]
 for prior in ['ALS','LoD2']:
  a=OUT/'r4n/runs'/f'tg_B173nb_b10_{prior}_s0/model/target_monitor/snapshot_0.npz';b=OUT/'r6/runs'/f'tg_B173nb_b10_{prior}_s0_r6/model/target_monitor/snapshot_0.npz'
  with np.load(a) as old,np.load(b) as new:
   fields=['xyz','init_id','origin','opacity','scale','rotation','anchor','normal','sigma','region','initial_scale','initial_large_background']
   for k in fields:assert np.array_equal(old[k],new[k],equal_nan=True),(prior,k)
   assert np.array_equal(new['target_tag'],new['origin']);assert (new['target_released_at']==-1).all()
   ix=new['target_index'][new['target_tag']==1]
   assert np.max(abs(new['xyz'][new['target_tag']==1]-new['patch_anchor'][ix]))<=1e-5
   rows.append(dict(prior=prior,status='PASS_IDENTICAL_ACTUAL_INITIALIZATION',fields=fields,gaussians=len(new['xyz']),
    opacity_prior=float(np.median(new['opacity'][new['origin']==1])),opacity_background=float(np.median(new['opacity'][new['origin']==0])),
    r4n_snapshot_sha256=sha(a),r6_snapshot_sha256=sha(b)))
 result=dict(at=stamp(),status='PASS_R6_INITIALIZATION',rows=rows,scientific_verdict=None)
 dump(OUT/'r6/verification/initial.json',result);dump(DOC/'tables/initial_r6.json',result);print(json.dumps(result),flush=True)
if __name__=='__main__':main()
