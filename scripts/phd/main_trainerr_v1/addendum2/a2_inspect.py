"""Addendum 2 input inspection (read-only): keys and shapes of the inputs the four works use."""
import sys; sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1'); sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1/addendum1')
from common import *
def show(p):
    p = Path(p)
    if not p.exists(): print('MISSING', p); return
    with np.load(p, allow_pickle=False) as z: print(p.name, {k: (z[k].shape, str(z[k].dtype)) for k in z.files})
for arm in ARMS:
    ap = arm_paths('B0_b10__LoD2', arm); show(ap['targets'])
    m = ap['model']; print(arm, m); show(m/'target_monitor/snapshot_30000.npz')
    show(ap['target_dir']/'seeds.npz'); show(ap['target_dir']/'maps/DJI_20241217094933_0013_D.npz')
show(S0 if False else Path('/s0/fork_inputs/s61/B0_b10/maps/mvs/DJI_20241217094933_0013_D.npy').with_suffix('.npy')) if False else None
x = np.load('/s0/fork_inputs/s61/B0_b10/maps/mvs/DJI_20241217094933_0013_D.npy'); c = np.load('/s0/fork_inputs/s61/B0_b10/maps/conf/DJI_20241217094933_0013_D.npy'); print('mvs', x.shape, x.dtype, np.nanmin(x), np.nanmax(x), np.isfinite(x).mean(), 'conf', c.dtype, np.unique(c)[:10])
with np.load(GT/'addendum11/final_data/B0_b10__LoD2.npz') as z: print('A11', [k for k in z.files][:80])
for f in sorted((O/'sets').glob('*'))[:12]: print('sets', f.name)
show(O/'sets/c1_own_lost.npz'); show(O/'sets/c2_own_lost.npz')
for f in sorted((O/'addendum1/points').glob('*')): print('a1pts', f.name)
show(O/'addendum1/points/na_wall_own.npz')
t = loadz(arm_paths('B0_b10__LoD2', 'own')['targets']); print('region', np.unique(t['region'], return_counts=True))
print(json.dumps({k: v for k, v in json.loads((FT/'targets/B0_b10__LoD2.json').read_text()).items() if k != 'x'}, ensure_ascii=False)[:2500] if (FT/'targets/B0_b10__LoD2.json').exists() else 'no targets json')
