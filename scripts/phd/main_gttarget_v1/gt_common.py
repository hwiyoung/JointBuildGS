"""PHD-MAIN-GTTARGET-v1 container paths and helpers. Inputs read-only; writes only /gt (payload), /docs, /cfg (lock only)."""
import csv, datetime as dt, hashlib, json, os, sys, time
from pathlib import Path
import numpy as np
R, C, D, O = map(Path, ['/repo', '/cfg', '/docs', '/gt'])
PH = Path('/art/phase-payloads/phd')
FT = PH/'main_finaltrain_v1/PHD-MAIN-FINALTRAIN-v1'
GT = PH/'main_gtjudge_v1/PHD-MAIN-GTJUDGE-v1'
TE = PH/'main_trainerr_v1/PHD-MAIN-TRAINERR-v1'
S0 = PH/'main_stage0_v1/PHD-MAIN-STAGE0-v1'
SITES = ['B0_b10', 'B173nb_b10', 'R1rep_b10']
STEMS = ['R1rep_b10__ALS', 'R1rep_b10__LoD2', 'B0_b10__LoD2', 'B173nb_b10__LoD2', 'B173nb_b10__ALS', 'B0_b10__ALS']
TITLE = '참값 목표 판(진단용)'

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
def cfg(stage=None):
    """locked config; stage n requires lock file gttarget_v1.stage<n>.lock.json written before the stage's first computation."""
    p = C/'gttarget_v1.json'
    if stage is not None:
        lock = json.loads((C/f'gttarget_v1.stage{stage}.lock.json').read_text())
        assert sha(p) == lock['config_sha256'], f'config changed after stage {stage} lock'
    return json.loads(p.read_text())
def issue(s):
    with (D/'issues.md').open('a') as f: f.write(f'- {now()}: {s}\n')
def progress(s):
    with (D/'progress.md').open('a') as f: f.write(f'- {now()}: {s}\n')
def table(name, rows, folder=None):
    keys = list(dict.fromkeys(k for r in rows for k in r)); p = (folder or D/'tables')/name; p.parent.mkdir(parents=True, exist_ok=True)
    with p.with_suffix('.csv').open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=keys, lineterminator='\n'); w.writeheader(); w.writerows(rows)
    dump(p.with_suffix('.json'), dict(title=TITLE, rows=rows, scientific_verdict=None))
    return p.with_suffix('.csv')
def tau_of(site, prior):
    with (R/'docs/experiments/phd/main_release_v1/tables/stage0/tau_values.csv').open() as f:
        t = next(x for x in csv.DictReader(f) if x['site'] == site and x['prior'] == prior)
    return float(t['roof_tau_m']), float(t['wall_tau_m'])
def view_box(site):
    return np.array(json.loads((GT/'views'/f'{site}.json').read_text())['box'])
