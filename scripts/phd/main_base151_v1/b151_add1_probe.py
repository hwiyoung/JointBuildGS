"""PHD-MAIN-BASE151-v1 addendum 1: field probe (read-only). scientific_verdict: null"""
import numpy as np, json, glob, os
g = np.load('/gtjudge/gt151_ALS.npz')
r = np.load('/gtjudge/scenes/B173nb_b10__ALS/rows.npz'); print('site rows', {k: (r[k].shape, r[k].dtype) for k in r.files})
for f in ['2DGS_30000', 'b151_2DGS_s0', 'mvs', 'prior', 'FINALTRAIN_30000']:
    z = np.load(f'/gtjudge/scenes/B173nb_b10__ALS/distances/{f}.npz'); print(f, {k: (z[k].shape, z[k].dtype) for k in z.files})
m = (g['site'] == 'B173nb_b10'); print('gt151 site rows', m.sum(), 'src', np.unique(g['src'][m]), 'src1 n', (g['src'] == 1).sum())
print(os.path.realpath('/gtjudge/scenes/B173nb_b10__ALS/distances/2DGS_30000.npz'))
T = '/art/phase-payloads/phd/main_trainunit_v1/PHD-MAIN-TRAINUNIT-v1/runs/ef/cellsef_ALS_s0_cell3'
for p in sorted(glob.glob(T + '/*'))[:20]: print(p)
