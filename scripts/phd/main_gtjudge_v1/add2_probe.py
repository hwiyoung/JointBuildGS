import numpy as np
from common import *
for site in SITES:
    stem=site+'__LoD2';t=loadz(FT/'targets'/f'{stem}.npz');c=loadz(JA/'core_points'/f'{stem}.npz')
    raw=loadz(PH/'main_target_v1/PHD-MAIN-TARGET-v1/stage0_r1/inputs'/f'{site}_LoD2.npz')
    print(site,'CORE',[(k,str(v.dtype),v.shape) for k,v in c.items() if k in ['building','b','bid','surf','source_index','kind','reason','region','photo_code']])
    print('RAW_KEYS',list(raw),'CORE_KEYS',list(c))
    print('TARGET',len(t['patch_id']),'INVALID',int((np.isfinite(t['prior_height_m'])&np.isfinite(t['normal']).all(1)&(np.linalg.norm(t['normal'],axis=1)==0)).sum()))
    print('KIND',np.unique(t['kind'],return_counts=True),'REASON',np.unique(c['reason'][5],return_counts=True))
