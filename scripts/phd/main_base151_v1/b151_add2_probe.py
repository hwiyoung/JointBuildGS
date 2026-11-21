"""PHD-MAIN-BASE151-v1 addendum 2: read-only probe of the inputs (keys and counts). Prints only. scientific_verdict: null"""
import json, sys
import numpy as np
sys.path.insert(0, '/b151s')
from b151_add1 import colmap_images, TU1, O, CELLS
g = np.load(O / 'gt151_ALS.npz'); print({k: (g[k].shape, str(g[k].dtype)) for k in g.files})
r = np.load(O / 'score151/b151_2DGS_s0__ALS/rows.npz'); print({k: (r[k].shape, str(r[k].dtype)) for k in r.files})
for k in g.files:
    if g[k].dtype.kind in 'USO': print(k, g[k][:3])
camp = colmap_images(TU1 / 'scenes/campus/scene_ALS/sparse/0/images.bin'); print('campus images', len(camp))
sp = json.loads((TU1 / 'scenes/campus/split.json').read_text()) if (TU1 / 'scenes/campus/split.json').exists() else None
print('campus split', None if sp is None else {k: len(v) for k, v in sp.items()})
import os; print(os.listdir(TU1 / 'scenes/campus'), os.listdir(TU1 / 'scenes/campus/scene_ALS'))
