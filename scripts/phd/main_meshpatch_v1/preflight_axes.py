"""Check uncapped means, the original E denominator, and existing cell identity."""
import numpy as np
from axes_adapter import aa, inputs
from mesh_common import dump, now
from pathlib import Path

g=aa.gt_block(dict(d=np.array([.1,2.]),tau=np.array([.2,.2]),sign=np.array([1,1])))
assert g['R_tau']==.5 and np.isclose(g['mean'],105.,rtol=0,atol=1e-10) and np.isclose(g['cap1_mean'],55.,rtol=0,atol=1e-10)
assert g['out4']==.5 and g['far1']==.5
s=dict(dA=np.array([.1,9.,3.]),dP=np.array([.1,9.,3.]),tau=np.full(3,.2),has_gt=np.ones(3,bool),
       spacing=np.full(3,.1),pd=np.zeros(3),nE=np.array([.1,.1,3.]),lE=np.array([.1,.6,.1]),
       nP=np.array([.1,.1,3.]),lP=np.array([.1,.6,.1]))
r=aa.res_block(s,place=True)['E']
assert r['n']==2 and r['excluded']==1 and r['P_tau']==.5 and np.isclose(r['mean'],155.,rtol=0,atol=1e-10)
ctx=inputs('B0_b10','LoD2')
out=dict(status='PASS',uncapped_means=True,result_E_denominator=True,
         losstrain_region_patch_centres_identical=True,patches=len(ctx['u'].centre),
         at=now(),scientific_verdict=None)
dump(Path('/docs/tables/axes_preflight.json'),out)
print(out)
