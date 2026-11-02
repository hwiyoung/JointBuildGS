"""Additional conservation/bounds checks, without changing any computed result."""
import numpy as np
from scipy.spatial import cKDTree
from common import *
def main():
 root=OUT/'screen_sim';cfg=json.loads((CFG/'screen_sim.json').read_text());b=json.loads(Path(cfg['boundaries']).read_text());oldc=np.array([r['xyz'] for r in b['cameras']]);tree=cKDTree(oldc);rows=[]
 for row in cfg['states']:
  p=root/'states'/row['key'];a=np.load(p/'gaussians.npz');g=np.load(p/'groups.npz');s=a['total_contribution'];r=a['roi_contribution'];m=a['max_contribution'];assert np.isfinite(s).all() and np.isfinite(r).all() and np.isfinite(m).all();assert (s>=0).all() and (r>=0).all() and (m>=0).all();assert (m<=.990001).all();assert np.all(r<=s+1e-8);assert np.all(m<=s+1e-8);assert np.array_equal(m==0,s==0)
  old=tree.query(a['xyz'],workers=4)[0];difference=np.abs(old-g['nearest_camera_distance_m']);changed=int(np.count_nonzero((old<=30)!=g['near30']));assert changed==0,(row['key'],changed)
  z=dict(state=row['key'],status='PASS',finite_nonnegative=True,max_weight_le_099=True,roi_sum_le_total=True,max_le_total=True,zero_max_equals_zero_sum=True,old_camera_formula_vs_inverse_max_distance_delta_m=float(difference.max()),near30_membership_changes=changed,scientific_verdict=None);rows.append(z);print('EXTRA_CHECK',row['key'],flush=True)
 dump(root/'extra_checks.json',dict(rows=rows,scientific_verdict=None));dump(DOC/'screen_sim/tables/extra_checks.json',dict(rows=rows,scientific_verdict=None))
if __name__=='__main__':main()
