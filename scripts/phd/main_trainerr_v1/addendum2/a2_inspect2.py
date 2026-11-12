"""Addendum 2 input checks (read-only): record-run state fields (lineage), seed/child order rule on record runs, s_m sign on the trained mesh."""
import sys; sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1'); sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1/addendum1')
from a1_common import *
st = sorted((O/'runs/B0_b10/tl_B0_LoD2_own/attempt1/model/trainlog/states').glob('*.npz'))
print('states', [p.name for p in st][-4:]); z = loadz(st[-1]); print({k: (v.shape, str(v.dtype)) for k, v in z.items()})
for f in ['start.json']:
    print(f, (O/'runs/B0_b10/tl_B0_LoD2_own/attempt1/model/trainlog'/f).read_text()[:600])
# order rule: original rows are a prefix with strictly increasing init_id
for run in ['B0_b10/tl_B0_LoD2_own', 'R1rep_b10/tl_R1_ALS_gt']:
    s = loadz(sorted((O/'runs'/run/'attempt1/model/trainlog/states').glob('30000.npz'))[0])
    ii = s['init_id']; dec = np.flatnonzero(np.diff(ii) <= 0); M = int(dec[0])+1 if len(dec) else len(ii)
    born = s.get('born'); print(run, 'rows', len(ii), 'prefix M', M, 'born keys', [k for k in s if 'born' in k or 'uid' in k or 'parent' in k])
    if born is not None: print(' rule_seed vs born==0 agree', float(((np.arange(len(ii)) < M) == (born == 0)).mean()), 'born==0 count', int((born == 0).sum()))
for arm in ARMS:
    sn = loadz(arm_paths('B0_b10__LoD2', arm)['model']/'target_monitor/snapshot_30000.npz', ['init_id', 'xyz', 'opacity'])
    ii = sn['init_id']; dec = np.flatnonzero(np.diff(ii) <= 0); print(arm, 'snapshot rows', len(ii), 'prefix', int(dec[0])+1 if len(dec) else len(ii), 'first init ids', ii[:5])
    from plyfile import PlyData
    v = PlyData.read(str(arm_paths('B0_b10__LoD2', arm)['model']/'point_cloud/iteration_30000/point_cloud.ply'))['vertex']; xyz = np.c_[v['x'], v['y'], v['z']]
    print(' ply rows', len(xyz), 'xyz equal', bool(len(xyz) == len(sn['xyz']) and np.allclose(xyz, sn['xyz'])), 'opacity sigmoid equal', bool(np.allclose(1/(1+np.exp(-np.asarray(v['opacity']))), sn['opacity'], atol=1e-6)))
    for cell in ['c1', 'c2']:
        stem = STEMS[cell]; sc = scene_ply(trained_mesh(stem, arm)); zz = loadz(O/'sets'/f'{cell}_{arm}_lost.npz', ['xyz', 'normal', 'trained_s_m'])
        k = np.flatnonzero(np.isfinite(zz['trained_s_m']))[:300]; P = zz['xyz'][k]+zz['trained_s_m'][k, None]*zz['normal'][k]
        d = sc.compute_distance(o3d.core.Tensor(P.astype(np.float32))).numpy(); Pm = zz['xyz'][k]-zz['trained_s_m'][k, None]*zz['normal'][k]; dm = sc.compute_distance(o3d.core.Tensor(Pm.astype(np.float32))).numpy()
        print(' ', arm, cell, 'X+s n on mesh median', float(np.median(d)), 'X-s n', float(np.median(dm)), 'finite', int(np.isfinite(zz['trained_s_m']).sum()), '/', len(zz['trained_s_m']))
