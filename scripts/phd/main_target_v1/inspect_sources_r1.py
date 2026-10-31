"""Read-only geometry/schema inventory before experimental photo ownership."""
import numpy as np
from scipy.spatial import cKDTree
from common import *

c,_=locked()
W=PH/'main_widen0_v2/PHD-MAIN-WIDEN0-v2'
LT=PH/'main_losstrain_v1/PHD-MAIN-LOSSTRAIN-v1/direct_stage1_v2'
for prior in c['priors']:
    pieces=[]
    for f in sorted((W/'patch_values').glob(f'*__{prior}__R1.5.npz')):
        with np.load(f) as z:
            x=z['centre'];shift=np.array(json.loads(f.with_suffix('.json').read_text())['frame_shift'])
            pieces.append((x,x-shift,z['normal'],z['kind']))
    registered=np.concatenate([p[0] for p in pieces]);raw=np.concatenate([p[1] for p in pieces]);norm=np.concatenate([p[2] for p in pieces]);kind=np.concatenate([p[3] for p in pieces])
    tree=cKDTree(registered);rawtree=cKDTree(raw)
    for site in c['sites']+c['deferred_sites']:
        with np.load(S1/'regions_v3'/f'regions_ext_v3_{site}_{prior}.npz') as r:
            x=r['centre'];shift=r['frame_shift'];ev=r['in_eval'];print('REGION',site,prior,'keys',r.files,'shift',shift.tolist(),'codes',np.unique(r['code_ext_v3'],return_counts=True),flush=True)
        d,ix=tree.query(x);dr,ir=rawtree.query(x-shift)
        print('PHOTO_GEOMETRY',site,prior,'registered_exact',int((d<1e-8).sum()),'raw_exact',int((dr<1e-8).sum()),'n',len(x),'registered_dist',np.quantile(d,[0,.5,.95,1]).tolist(),'raw_dist',np.quantile(dr,[0,.5,.95,1]).tolist(),flush=True)
        f=LT/f'{site}__{prior}/evaluation.npz'
        if f.exists():
            with np.load(f) as z:print('EVAL',site,prior,len(z['cell']),'keys',z.files,'samecentre',np.array_equal(x,z['centre']),flush=True)
