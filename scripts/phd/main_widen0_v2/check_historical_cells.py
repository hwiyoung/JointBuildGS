"""Bind the cross-table's inherited twelve-cell labels to AXES71 artifacts."""
import json
import numpy as np
from preflight import PH,sha,dump
rows=[]
for site in ['B0_b10','B173nb_b10','R1rep_b10']:
    for prior in ['LoD2','ALS']:
        old=PH/'main_uncert_v1/PHD-MAIN-UNCERT-v1/patch_values'/f'{site}__{prior}__R1.5.npz'
        axes=PH/'main_axes71_v2/PHD-MAIN-AXES71-v2/work'/f'cells_{site}_{prior}.npz'
        with np.load(old) as a,np.load(axes) as b:
            assert np.array_equal(a['in_eval'],b['in_eval'])
            mask=a['in_eval'].astype(bool)
            assert np.array_equal(a['cell'][mask],b['cell'][mask]),(site,prior)
            rows.append(dict(site=site,prior=prior,evaluation_patches=int(mask.sum()),
                labels_equal=True,uncert_source=str(old),uncert_sha256=sha(old),axes_source=str(axes),axes_sha256=sha(axes)))
result=dict(status='PASS',rows=rows,scientific_verdict=None)
dump('/out/gates/historical_cells.json',result);dump('/docs/tables/기존_열두칸_출처검사.json',result)
print('six historical twelve-cell source checks PASS')
