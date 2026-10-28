"""Compare current main-view surf_depth to actual frozen TSDF input arrays."""
import json
import numpy as np
from common import *
rows=[]
for site in SITES:
    result='lt_dynnow_ALS_s0';folder=LT/'runs'/site/result/'post/tiled_tsdf/inputs'
    if not (folder/'depth_masked.npy').exists():
        rows.append(dict(site=site,result=result,status='UNAVAILABLE',reason='original TSDF depth arrays not retained'));continue
    with np.load(folder/'cams.npz') as f:names=f['names'];ext=f['extrinsic']
    old=np.load(folder/'depth_masked.npy',mmap_mode='r')
    chosen=json.loads((CFG/f'photos_{site}_ALS.json').read_text())['cases']
    for name in sorted({x['main']['view'] for x in chosen if x['main']}):
        index=int(np.flatnonzero(names==name)[0]);original=np.array(old[index]);valid=original>0
        path=OUT/'four_depths'/site/result/(name+'.npz')
        with np.load(path) as f:current=f['surf_depth'];mean=f['opacity_mean']
        assert original.shape==current.shape
        difference=np.abs(original[valid]-current[valid]);exact=np.array_equal(original[valid],current[valid])
        assert exact,(site,name,float(difference.max()))
        rows.append(dict(site=site,result=result,view=name,status='PASS',pixels=int(valid.sum()),
            tsdf_masked_zero_pixels=int((~valid).sum()),bit_identical_TSDF_input_surf_and_mean=bool(exact and np.array_equal(current,mean)),
            max_difference_m=float(difference.max()),TSDF_input=str(folder/'depth_masked.npy'),camera_index=index,
            original_binding=str(folder/'binding.json'),original_binding_sha256=sha(folder/'binding.json')))
    del old
save(DOC/'provenance/actual_tsdf_depth_comparison.json',dict(at=now(),rows=rows,scientific_verdict=None))
print('saved TSDF inputs vs exact training mean depth',[(r['site'],r['status']) for r in rows],flush=True)
