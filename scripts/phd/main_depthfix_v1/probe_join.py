"""inspection: keys of the JUDGEPROBE patch file (csv patch_index rows)."""
import sys; sys.path.insert(0, '/repo/scripts/phd/main_depthfix_v1')
from df_common import *
for p in ['ALS', 'LoD2']:
    with np.load(JP/f'patch_{p}.npz') as z: print(p, {k: (z[k].shape, z[k].dtype) for k in z.files})
