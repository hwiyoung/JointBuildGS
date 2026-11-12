"""Addendum 2 input check (read-only): stage1 cell fields, seeds.patch meaning, rows fields."""
import sys; sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1')
from common import *
for stem in ['B0_b10__LoD2', 'B0_b10__ALS']:
    with np.load(GT/'scenes'/stem/'stage1_cells.npz') as z: print(stem, 'cells', {k: (z[k].shape, str(z[k].dtype)) for k in z.files})
    with np.load(GT/'scenes'/stem/'rows.npz') as z: print(stem, 'rows', {k: (z[k].shape, str(z[k].dtype)) for k in z.files})
    with np.load(GT/'addendum11/final_data'/f'{stem}.npz') as z: print(stem, 'A11 n_ref', len(z['reference__xyz']), 'eligible', int(z['reference__eligible'].sum()), [k for k in z.files if k.startswith('reference__') and 'within' in k])
    ap = arm_paths(stem, 'own'); s = loadz(ap['target_dir']/'seeds.npz', ['patch', 'origin']); t = loadz(ap['targets'], ['region', 'judge_region'])
    print(stem, 'seeds patch range', s['patch'][s['origin'] == 1].min(), s['patch'][s['origin'] == 1].max(), 'bg patch', np.unique(s['patch'][s['origin'] == 0])[:3], 'targets', len(t['region']), 'judge', np.unique(t['judge_region'], return_counts=True))
    tg = loadz(arm_paths(stem, 'gt')['targets'], ['judge_region']); print(stem, 'gt judge', np.unique(tg['judge_region'], return_counts=True))
print(sorted(p.name for p in (GT/'addendum12/distance_A1').glob('*.npz')))
