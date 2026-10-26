import sys
sys.path.insert(0, '/repo/scripts/phd/main_regionfig_v1')
from common import *
import resource

for prior in ['ALS','LoD2']:
    with np.load(PAY/'input'/f'{prior}_sites.npz', allow_pickle=False) as z:
        print(prior, [(k,str(z[k].dtype),z[k].shape) for k in z.files])
        print('patch_id examples', z['patch_id'][:3])
        print('buildings',np.unique(z['building'],return_counts=True))
w=PH/'main_widen0_v2/PHD-MAIN-WIDEN0-v2/patch_values'
sample=w/'6909_53360__LoD2__R1.5.npz'
with np.load(sample,allow_pickle=False) as z:
    print('W keys',z.files)
    for k in ['patch_id','centre','normal','building']:
        if k in z:print(k,z[k].shape,z[k].dtype,z[k][:3])
print('max_rss_KiB',resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
