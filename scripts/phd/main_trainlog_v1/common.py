"""PHD-MAIN-TRAINLOG-v1 container paths and helpers. Inputs read-only; writes only /tl, /docs, /cfg(lock)."""
import csv, datetime as dt, hashlib, json, os
from pathlib import Path
import numpy as np
R, C, D, O = map(Path, ['/repo', '/cfg', '/docs', '/tl'])
PH = Path('/art/phase-payloads/phd')
FT = PH/'main_finaltrain_v1/PHD-MAIN-FINALTRAIN-v1'
PF = PH/'main_procfig_v1/PHD-MAIN-PROCFIG-v1'
GT = PH/'main_gtjudge_v1/PHD-MAIN-GTJUDGE-v1'
RS = PH/'main_rescore_v1/PHD-MAIN-RESCORE-v1'
S1 = PH/'main_stage1_v1/PHD-MAIN-STAGE1-v1'
JA = PH/'main_judgeapply_v1/PHD-MAIN-JUDGEAPPLY-v1'
SITE = 'B173nb_b10'; PRIOR = 'ALS'; STEM = SITE+'__'+PRIOR; CASE = 'c1_'+STEM
RUN = 'tl_B173nb_b10_ALS_s0'; ATTEMPT = 'attempt2'
RUNM = O/'runs'/SITE/RUN/ATTEMPT/'model'; DER = O/'runs'/SITE/RUN/'derived'
ORIG = FT/'runs'/SITE/'ft_ALS_s0/attempt1/model'
SHIFT = np.array([690953., 5336071., 604.])
def now(): return dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat()
def sha(p):
    h = hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda: f.read(8 << 20), b''): h.update(b)
    return h.hexdigest()
def dump(p, v):
    p = Path(p); p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(v, ensure_ascii=False, indent=2, allow_nan=False, default=lambda x: x.item() if hasattr(x, 'item') else str(x))+'\n')
def loadz(p, keys=None):
    with np.load(p, allow_pickle=False) as z: return {k: z[k] for k in (z.files if keys is None else keys)}
def savez(p, **v):
    p = Path(p); p.parent.mkdir(parents=True, exist_ok=True); np.savez_compressed(p, **v)
def cfg():
    p = C/'trainlog_v1.json'; lock = json.loads((C/'trainlog_v1.lock.json').read_text())
    assert sha(p) == lock['config_sha256'], 'TRAINLOG config changed after lock'
    return json.loads(p.read_text())
def issue(s):
    with (D/'issues.md').open('a') as f: f.write(f'- {now()}: {s}\n')
def progress(s):
    with (D/'progress.md').open('a') as f: f.write(f'- {now()}: {s}\n')
def table(name, rows, folder=None):
    keys = list(dict.fromkeys(k for r in rows for k in r)); p = (folder or D/'tables')/name; p.parent.mkdir(parents=True, exist_ok=True)
    with p.with_suffix('.csv').open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=keys, lineterminator='\n'); w.writeheader(); w.writerows(rows)
    return p.with_suffix('.csv')
