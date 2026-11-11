"""PHD-MAIN-TRAINERR-v1 container paths and helpers. Inputs read-only; writes only /te (payload), /docs, /cfg (lock only)."""
import csv, datetime as dt, hashlib, json, os, sys, time
from pathlib import Path
import numpy as np
R, C, D, O = map(Path, ['/repo', '/cfg', '/docs', '/te'])
PH = Path('/art/phase-payloads/phd')
FT = PH/'main_finaltrain_v1/PHD-MAIN-FINALTRAIN-v1'
GT = PH/'main_gtjudge_v1/PHD-MAIN-GTJUDGE-v1'
RS = PH/'main_rescore_v1/PHD-MAIN-RESCORE-v1'
JA = PH/'main_judgeapply_v1/PHD-MAIN-JUDGEAPPLY-v1'
AX = PH/'main_axes71_v2/PHD-MAIN-AXES71-v2'
TG = PH/'main_target_v1/PHD-MAIN-TARGET-v1'
TL = PH/'main_trainlog_v1/PHD-MAIN-TRAINLOG-v1'
MAXID = TG/'r5/runtime/maxid_build/jbgs_target_r5_maxid.so'
STEMS = {'c1': 'B0_b10__LoD2', 'c2': 'R1rep_b10__ALS', 'c3': 'B0_b10__LoD2'}
CASE = {'c1': 2, 'c2': 2, 'c3': 4}
SCENES = ['B0_b10__LoD2', 'R1rep_b10__ALS']
ARMS = ['own', 'gt']
TARGET_METHOD = {'own': 'judgment_mesh', 'gt': 'gt_judgment_mesh'}
TRAINED_METHOD = {'own': 'FINALTRAIN_30000', 'gt': 'A1'}
SHIFT = np.array([690953., 5336071., 604.])

def now(): return dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat()
def sha(p):
    h = hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda: f.read(8 << 20), b''): h.update(b)
    return h.hexdigest()
def _default(x):
    if hasattr(x, 'item'): return x.item()
    if isinstance(x, np.ndarray): return x.tolist()
    return str(x)
def dump(p, v):
    p = Path(p); p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(v, ensure_ascii=False, indent=1, allow_nan=False, default=_default)+'\n')
def loadz(p, keys=None):
    with np.load(p, allow_pickle=False) as z: return {k: z[k] for k in (z.files if keys is None else keys)}
def savez(p, **v):
    p = Path(p); p.parent.mkdir(parents=True, exist_ok=True); np.savez_compressed(p, **v)
def cfg():
    p = C/'trainerr_v1.json'; lock = json.loads((C/'trainerr_v1.lock.json').read_text())
    assert sha(p) == lock['config_sha256'], 'TRAINERR config changed after lock'
    c = json.loads(p.read_text())
    # inherited speed renderer binding (FINALTRAIN finaltrain_v1.json 'renderer', also used by GTJUDGE/TRAINLOG); read-only
    c.setdefault('renderer', json.loads((R/'configs/phd/main_finaltrain_v1/finaltrain_v1.json').read_text())['renderer'])
    return c
def issue(s):
    with (D/'issues.md').open('a') as f: f.write(f'- {now()}: {s}\n')
def progress(s):
    with (D/'progress.md').open('a') as f: f.write(f'- {now()}: {s}\n')
def table(name, rows, folder=None):
    """csv + json side by side (order 7.1)."""
    keys = list(dict.fromkeys(k for r in rows for k in r)); p = (folder or D/'tables')/name; p.parent.mkdir(parents=True, exist_ok=True)
    with p.with_suffix('.csv').open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=keys, lineterminator='\n'); w.writeheader(); w.writerows(rows)
    dump(p.with_suffix('.json'), dict(rows=rows, scientific_verdict=None))
    return p.with_suffix('.csv')
def tau_of(site, prior):
    with (R/'docs/experiments/phd/main_release_v1/tables/stage0/tau_values.csv').open() as f:
        t = next(x for x in csv.DictReader(f) if x['site'] == site and x['prior'] == prior)
    return float(t['roof_tau_m']), float(t['wall_tau_m'])
def arm_paths(stem, arm):
    site, prior = stem.split('__')
    if arm == 'own':
        return dict(target_mesh=RS/'addendum3_stage2/meshes'/f'{stem}__judgment_mesh/primary.ply',
                    trained_mesh=RS/'addendum3_stage2/meshes'/f'{stem}__FINALTRAIN_30000/primary.ply',
                    model=FT/'runs'/site/f'ft_{prior}_s0/attempt1/model', targets=FT/'targets'/f'{stem}.npz', target_dir=FT/'stage1'/stem,
                    point_data=GT/'addendum11/final_data'/f'{stem}.npz')
    att = 'attempt2' if stem == 'B0_b10__LoD2' else 'attempt1'
    return dict(target_mesh=GT/'meshes'/f'{stem}__gt_judgment_mesh/final.ply', trained_mesh=GT/'meshes'/f'{stem}__A1/final.ply',
                model=GT/'runs'/site/f'gt_{prior}_s0'/att/'model', targets=GT/'targets_gt'/f'{stem}.npz', target_dir=GT/'stage1'/stem,
                point_data_target=GT/'addendum11/final_data'/f'{stem}.npz', point_data=GT/'addendum12/distance_A1'/f'{stem}.npz')
def valid_patch(t):
    return (t['region'] >= 0) & np.isfinite(t['target']).all(1) & np.isfinite(t['normal']).all(1) & np.isfinite(t['sigma']) & (t['sigma'] > 0)
class Timer:
    def __init__(self, name): self.name = name; self.t = time.monotonic()
    def done(self, **kw):
        s = time.monotonic()-self.t
        with (O/'logs/timing.jsonl').open('a') as f: f.write(json.dumps(dict(at=now(), step=self.name, seconds=s, **kw), default=_default)+'\n')
        return s
