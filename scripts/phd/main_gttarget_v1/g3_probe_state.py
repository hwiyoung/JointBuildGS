"""Stage 3 note (CPU, read only): addendum 6 point-state shares by group (method run) next to this run's state step, R1 x ALS."""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_gttarget_v1')
from gt_common import *
s = 'R1rep_b10__ALS'; S = loadz(TE/'addendum6/points'/f'sel_{s}.npz', ['group', 'state']); print('A6 method', {g: np.bincount(S['state'][S['group'] == g], minlength=5).tolist() for g in range(4)})
P = loadz(O/'points'/f'ga_{s}.npz', ['group_gtt']); C = loadz(O/'ca'/f'state_{s}_gtt_s0.npz'); print('GTT', {g: np.bincount(C['state'][P['group_gtt'] == g], minlength=5).tolist() for g in range(4)})
print('spot_n q', np.quantile(C['spot_n'], [.1, .5, .9]))
