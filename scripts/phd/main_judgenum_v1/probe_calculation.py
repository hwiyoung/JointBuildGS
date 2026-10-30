import importlib.util
import json
from pathlib import Path
import shutil
import numpy as np

print('numba',bool(importlib.util.find_spec('numba')),'g++',shutil.which('g++'))
for prior in ['LoD2','ALS']:
    p=Path('/out/inputs/6908_53359__'+prior+'.npz')
    with np.load(p) as z:
        print(prior,'patches',len(z['normal']),'surfaces',len(np.unique(z['surf'])),
          'unique_normals',len(np.unique(np.round(z['normal'],8),axis=0)))
cfg=json.loads(Path('/cfg/judgenum_v1.json').read_text())
rows=json.loads(Path('/out/input_join.json').read_text())['rows']
totals={}
for r in rows:totals[r['tile']]=totals.get(r['tile'],0)+r['patches']
print('tile_patch_counts',json.dumps(totals))
