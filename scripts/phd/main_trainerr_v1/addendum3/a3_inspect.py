"""Input inspection before the addendum 3 config (read-only, prints field names, shapes and a few facts)."""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1/addendum2')
from a2_common import *
TLC = PH/'main_trainlog_v1/PHD-MAIN-TRAINLOG-v1/concept_v2/case_B0_b10__LoD2'
def keys(p):
    with np.load(p, allow_pickle=False) as z: return {k: (z[k].shape, str(z[k].dtype)) for k in z.files}
stem = 'B0_b10__LoD2'
print('ROWS', keys(GT/'scenes'/stem/'rows.npz'))
a = np.load(GT/'addendum11/final_data'/f'{stem}.npz'); print('A11', [k for k in a.files if k.startswith('reference__')][:40]); a.close()
print('SETS_TL c1 lost', keys(O/'sets_tl/c1_own_lost.npz'))
print('TARGETS', keys(targets_of(stem, 'own')))
m = O/'runs/B0_b10/tl_B0_LoD2_own/attempt1/model/trainlog'
print('STATE npz', keys(m/'states/9000.npz'))
print('GRADS', keys(m/'grads/9000.npz'))
for k in ['delete', 'release', 'retarget', 'birth', 'range', 'opacity_reset']:
    f = sorted((m/'events').glob(f'{k}_*.npz'))[0]; print('EV', k, keys(f))
print('SAVES', (m/'saves.jsonl').read_text().splitlines()[:2])
import torch
s = torch.load(TLC/'runs/B0_b10/tl_B0_b10_LoD2_s0/attempt1/model/trainlog/scene/9000.pt', weights_only=False)
print('SCENE pt', {k: (tuple(v.shape), str(v.dtype)) if torch.is_tensor(v) else v for k, v in s.items()})
r = loadz(GT/'scenes'/stem/'rows.npz')
for k in ['row_area_m2', 'area', 'cell_m', 'spacing']:
    if k in r: print('ROWAREA', k, float(np.median(r[k])))
reg = json.loads((O/'region/B0_b10__LoD2.json').read_text()); print('REGION', {k: v for k, v in reg.items() if k != 'boxes'}, len(reg['boxes']))
tl = json.loads((TLC/'runs/B0_b10/tl_B0_b10_LoD2_s0/attempt1/model/trainlog/start.json').read_text()); print('TL start', tl['box'], tl['z'], tl['inside'])
print('A11 rows/point', len(r['row_owner']))
