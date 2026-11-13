"""Input inspection 2 (read-only): check-5 curve arrays, TRAINLOG case distance arrays, record-run mesh folders."""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1/addendum3')
from a3_common import *
with np.load(O/'curves/tl_R1_ALS_own__7000.npz') as z: print('CURVE', {k: z[k].shape for k in z.files})
with np.load(TLC/'gtj/scenes/B0_b10__LoD2/distances/tl_7000.npz') as z: print('TLDIST', {k: z[k].shape for k in z.files})
print('TLMESH', sorted(p.name for p in (TLC/'gtj/meshes').iterdir()))
print('TEMESH', sorted(p.name for p in (O/'gtj/meshes').iterdir())[:40])
print('TLVIEWS', sorted(p.name for p in (TLC/'gtj/views').iterdir()), sorted(p.name for p in (O/'gtj/views').iterdir()))
for p in sorted((TLC/'gtj/views').iterdir()): print(p.name, sha(p))
for p in sorted((O/'gtj/views').iterdir()): print(p.name, sha(p))
