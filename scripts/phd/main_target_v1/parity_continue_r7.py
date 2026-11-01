"""Replay inherited AXES arrays before measuring new meshes."""
import sys,json
from pathlib import Path
import numpy as np
sys.path.insert(0,'/repo/scripts/phd/main_meshpatch_v1')
from axes_adapter import ax,aa,a3
from mesh_common import dump,sha,now
checks=[]
for prior in ['ALS','LoD2']:
 site='B173nb_b10';res=ax.results_of('twodgs',prior)[0];A=aa.arrays(site,prior,res);assert A['status']=='있음';expected=json.loads((ax.TAB/'a3_metrics.json').read_text())['data'][site+'/'+prior]['twodgs']['values'][res]
 for key in ['all']+ax.KEYS:
  if key in ax.VIRTUAL_CELLS:continue
  g=A['scene'] if key=='all' else aa.sel(A['rows'],aa.cell_sel(A['rows']['cell'],key,ax.SUMS));s=A['smp'] if key=='all' else aa.sel(A['smp'],aa.cell_sel(A['smp']['cell'],key,ax.SUMS));gb=aa.gt_block(g,with05=key=='all');rb=aa.res_block(s,place=key!='all',with05=key=='all');want=expected[key]
  for label,got,w in [('gt',gb,want['gt']),('res_E',rb['E'],want['res']['E'])]:
   for field in got:
    a,b=got[field],w[field];ok=(a is None and b is None) or (a is not None and b is not None and a==b);checks.append(dict(prior=prior,key=key,side=label,field=field,pass_check=bool(ok)))
assert checks and all(r['pass_check'] for r in checks)
dump(Path('/target/r7_continue/scoring/parity.json'),dict(status='PASS',at=now(),comparisons=len(checks),checks=checks,source_sha256=sha(ax.TAB/'a3_metrics.json'),new_worker_sha256=sha('/repo/scripts/phd/main_target_v1/axes_continue_r7.py'),virtual_cells='intentionally scored independently on specified current/final mesh; no mixed-mesh substitution',scientific_verdict=None));print('AXES_PARITY_PASS',len(checks),flush=True)
