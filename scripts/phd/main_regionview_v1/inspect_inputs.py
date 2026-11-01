"""Read-only schema discovery. Never print sealed patch values or identifiers."""
import json
from pathlib import Path
import numpy as np

P = Path('/art/phase-payloads/phd')
T = P/'main_target_v1/PHD-MAIN-TARGET-v1'
S = P/'main_stage0_v1/PHD-MAIN-STAGE0-v1'
W = P/'main_widen0_v2/PHD-MAIN-WIDEN0-v2'
J = P/'main_judgenum_v1/PHD-MAIN-JUDGENUM-v1'
D = P/'main_prep_discard_rule_v1/PHD-MAIN-PREP-DISCARD-RULE-v1'
for path in [T/'r2/targets/B173nb_b10_ALS.npz', T/'r2/targets/B173nb_b10_LoD2.npz',
             S/'s61/box/B173nb_b10/LoD2/units.npz',
             next((T/'r2/stage0/development').glob('*.npz')),
             next((J/'inputs').glob('*.npz')),
             next((W/'holdout/internal/patch_geometry').glob('*LoD2.npz'))]:
    with np.load(path) as z:
        print(str(path), {k:(z[k].shape,str(z[k].dtype)) for k in z.files})
        if 'r2/targets' in str(path):
            print('building_nonempty',int(np.sum(z['building']!='')),'unique',len(np.unique(z['building'])), 'surf_range', [int(z['surf'].min()),int(z['surf'].max())])
            print('public_buildings',np.unique(z['building']).tolist())
for path in [D/'s02_box/B173nb_b10/lod2_surfaces.json', S/'s61/box/B173nb_b10/LoD2/summary.json',
             S/'fork_inputs/s61/B173nb_b10/scene_LoD2/jbgs_calibration.json',
             Path('/repo/configs/phd/main_prep_measure_v1/prep_v5.json')]:
    d=json.loads(path.read_text())
    print(str(path),list(d))
    if 'surfaces' in d: print('first_surface',d['surfaces'][0])
    if 'registration' in d and 'shift_applied' in d['registration']: print('shift',d['registration']['shift_applied'])
    if 'frame' in d: print('frame',d['frame'])
    if 'jbgs_calibration' in str(path):print('calibration',str(d)[:1800])
print('train_files',[str(p.relative_to(S)) for p in (S/'fork_inputs/s61/B173nb_b10').glob('*')])
cfg=json.loads(Path('/repo/configs/phd/main_judgenum_v1/judgenum_v1.json').read_text())
print('judgenum_scope_keys',list(cfg['scope']), 'development_count',len(cfg['scope']['development']))
print('r7_candidates',[str(p) for p in T.glob('*r7*')])
