"""Stage 3 note (CPU, read only): keys and lengths of the inputs table ga reads (GTJUDGE addendum11 final_data, gtt mesh points.npz, addendum2 points)."""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_gttarget_v1')
from gt_common import *
s = 'R1rep_b10__ALS'
A = np.load(GT/'addendum11/final_data'/f'{s}.npz'); print('A11', len(A['reference__point_id']), [k for k in A.files])
for k in ['R1rep_b10__ALS__gtt_target', 'R1rep_b10__ALS__gtt_s0_base']:
    z = np.load(O/'meshes'/k/'points.npz'); print(k, {f: z[f].shape for f in z.files}); print(json.loads((O/'meshes'/k/'score.json').read_text()).keys())
z = np.load(TE/'addendum2/points'/f'ra_{s}__own.npz'); print('A2', {f: z[f].shape for f in z.files})
z = np.load(TE/'addendum6/points'/f'sel_{s}.npz'); print('SEL', {f: z[f].shape for f in z.files})
sc = json.loads((O/'meshes/R1rep_b10__ALS__gtt_s0_base/score.json').read_text()); print([ (r.get('surface'),r.get('case_id')) for r in sc['rows']][:30]); print(sc['rows'][0])
