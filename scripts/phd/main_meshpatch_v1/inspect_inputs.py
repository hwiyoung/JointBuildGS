"""Read-only structural inventory; no source values are modified."""
import json
from pathlib import Path
import numpy as np
import scipy, numba, open3d

PH=Path('/ph')
W=PH/'main_widen0_v2/PHD-MAIN-WIDEN0-v2'
S=PH/'main_stage1_v1/PHD-MAIN-STAGE1-v1'
print('versions',np.__version__,scipy.__version__,numba.__version__,open3d.__version__)
for prior in ['ALS','LoD2']:
    fs=sorted((W/'patch_values').glob(f'*__{prior}__R1.5.npz'))
    receipts=[json.loads(f.with_suffix('.json').read_text()) for f in fs]
    print(prior,'files',len(fs),'patches',sum(x['patches'] for x in receipts),'area',sum(x['area_m2'] for x in receipts))
    with np.load(max(fs,key=lambda f:f.stat().st_size)) as d:
        print('PATCH_SCHEMA',prior,{k:[str(d[k].dtype),list(d[k].shape)] for k in d.files})
        print('sample', {k:d[k][:2].tolist() for k in ['patch_id','centre','raw_centre','kind','roof_type','face_ext','building']})
    with np.load(S/'regions_v3'/f'regions_ext_v3_B0_b10_{prior}.npz') as d:
        print('REGION_SCHEMA',prior,{k:[str(d[k].dtype),list(d[k].shape)] for k in d.files})
        print('region sample',{k:d[k][:2].tolist() for k in ['centre','center','code_ext_v3','in_eval','area','kind','state','views'] if k in d.files})
print('RANGES', (PH/'main_prep_measure_v1/PHD-MAIN-PREP-MEASURE-v1/step01/ranges.json').read_text()[:6000])
print('BOXES', (PH/'main_prep_measure_v1/PHD-MAIN-PREP-MEASURE-v1/step06/boxes_v1.json').read_text()[:3000])
