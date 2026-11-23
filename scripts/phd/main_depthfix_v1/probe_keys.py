import sys; sys.path.insert(0, '/repo/scripts/phd/main_depthfix_v1')
from df_common import *
GT = PH/'main_gtjudge_v1/PHD-MAIN-GTJUDGE-v1'
with np.load(GT/'addendum11/final_data/R1rep_b10__ALS.npz') as z: print([ (k, z[k].shape) for k in z.files][:80])
with np.load(PH/'main_wrongtarget_v1/PHD-MAIN-WRONGTARGET-v1/points/wt_R1rep_b10__ALS.npz') as z: print([(k, z[k].shape) for k in z.files])
