"""Input inspection 3 (read-only): addendum2 work-ra point files, original sets, a target map file and the GT view list box."""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1/addendum3')
from a3_common import *
for f in sorted((A2O/'points').glob('ra_*__own.npz'))[:1]:
    with np.load(f) as z: print('RA', f.name, {k: (z[k].shape, str(z[k].dtype)) for k in z.files})
with np.load(O/'sets/c2_own_lost.npz') as z: print('SETS', {k: z[k].shape for k in z.files})
idx = json.loads((maps_dir('B0_b10__LoD2', 'own')/'index.json').read_text()); v = idx['views']['DJI_20241217094933_0013_D']; print('MAPIDX', {k: v[k] for k in v if k != 'sha256'})
vj = json.loads((GT/'views/B0_b10.json').read_text()); print('VIEWBOX', vj['box'], len(vj['views']))
print('RA groups', open('/repo/scripts/phd/main_trainerr_v1/addendum2/a2_ra.py').read()[:1500])
