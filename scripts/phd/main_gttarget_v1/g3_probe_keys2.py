"""Stage 3 note (CPU, read only): GTJUDGE addendum11 final_data keys for 'reference__*__within_tau1' per scene (which runs have per-point scores)."""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_gttarget_v1')
from gt_common import *
for s in STEMS:
    A = np.load(GT/'addendum11/final_data'/f'{s}.npz'); print(s, len(A['reference__point_id']), int(A['reference__eligible'].sum()), [k.split('__')[1] for k in A.files if k.startswith('reference__') and k.endswith('within_tau1')])
