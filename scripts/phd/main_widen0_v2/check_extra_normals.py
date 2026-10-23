"""Verify the unchanged core retains unavailable planes for inherited zero normals."""
import ast
import json
from pathlib import Path
import warnings
import numpy as np
from scipy.spatial import cKDTree
import u_worker as W
from preflight import PH,sha,dump
for p in Path(__file__).parent.glob('*.py'):ast.parse(p.read_text())
assert sha(Path(__file__).parent/'u_core.py')==sha('/repo/scripts/phd/main_uncert_v1/u_core.py')
rng=np.random.default_rng(9)
inner=np.column_stack([rng.uniform(-.1,.1,(20,2)),np.zeros(20)])
angle=np.arange(30)*2*np.pi/30;outer=np.column_stack([.75*np.cos(angle),.75*np.sin(angle),np.zeros(30)])
X=np.concatenate([inner,outer])
W.G.update(X=X,V=None,data='gt',radii=[],site='6907_53359',pset='ALS',tree=cKDTree(X),levels={},
    c=np.zeros((1,3)),n=np.zeros((1,3)),roof=np.zeros(1,bool))
g=W.one_patch(0)[0];assert g['status']==3 and g['n_inner']==20
W.G.update(data='mvs_a',radii=[1.5],V=np.zeros(len(X),np.int16),gt={'status':np.array([3])})
with warnings.catch_warnings(record=True) as seen:
    warnings.simplefilter('always');v=W.one_patch(0)[1.5]
assert v['status']==3 and not np.isfinite(v.get('e',np.nan))
rows=[]
for site in ['B0_b10','B173nb_b10','R1rep_b10']:
    for prior in ['LoD2','ALS']:
        f=PH/'main_uncert_v1/PHD-MAIN-UNCERT-v1/patch_values'/f'{site}__{prior}__R1.5.npz'
        with np.load(f) as z:
            zero=(np.linalg.norm(z['normal'],axis=1)==0)&z['in_eval'].astype(bool)
            assert not np.any(z['gt_status'][zero]==0)
            assert not np.isfinite(z['mvs_a_e'][zero]).any()
            rows.append(dict(site=site,prior=prior,historical_zero_normals=int(zero.sum()),
                historical_area_m2=float(z['area'][zero].sum()),source=str(f)))
result=dict(status='PASS',synthetic_GT_status=int(g['status']),synthetic_MVS_status=int(v['status']),
    warnings=[str(w.message) for w in seen],historical_checks=rows,
    rule='Preserve inherited centroid fallback and zero normal; no imputed direction and no fabricated GT plane.',scientific_verdict=None)
dump('/out/gates/extra_normal_replay.json',result);dump('/docs/tables/extra_normal_replay.json',result)
print('inherited extra-normal handling PASS; original core unchanged')
