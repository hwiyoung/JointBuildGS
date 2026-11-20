"""Stage 3 note (CPU, read only): method-run table ra recount over all six scenes from TRAINERR addendum 6 causes files, two readings of 'back with median':
(a) this task's rule: not back with occl(_10 | _10_median) and back with median_depth; (b) addendum 6 cause shares among lost points (cause 2 / 3 / rest)."""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_gttarget_v1')
from gt_common import *
T = np.zeros(3); C = np.zeros(10)
for s in STEMS:
    z = loadz(TE/'addendum6/ba'/f'causes_{s}.npz'); m = z['group'] == 1; r = np.where(z['within_occl'][m], 0, np.where(z['within_median'][m], 1, 2)); T += np.bincount(r, minlength=3); C += np.bincount(z['cause'][m], minlength=10)
    print(s, int(m.sum()), np.bincount(r, minlength=3).tolist())
print('six scenes ra', T.tolist(), (100*T/T.sum()).round(1).tolist()); print('six scenes causes', C.tolist(), (100*C/C.sum()).round(1).tolist())
