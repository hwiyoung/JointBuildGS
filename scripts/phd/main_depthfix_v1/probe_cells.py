import sys; sys.path.insert(0, '/repo/scripts/phd/main_depthfix_v1')
from df_common import *
for st in ['R1rep_b10__LoD2', 'R1rep_b10__ALS']:
    site, prior = st.split('__')
    with np.load(TG/'stage0_r1/inputs'/f'{site}_{prior}.npz') as z: print(st, 'inputs', {k: (z[k].shape, str(z[k].dtype)) for k in z.files})
    with np.load(S0/'fork_inputs/s61'/site/f'store_{prior}.npz') as z: print(st, 'store', {k: (z[k].shape, str(z[k].dtype)) for k in z.files})
