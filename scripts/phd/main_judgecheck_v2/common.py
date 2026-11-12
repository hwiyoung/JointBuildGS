"""PHD-MAIN-JUDGECHECK-v2 공통: 경로, 잠금, 기록. 학습 없음. scientific_verdict: null."""
import datetime as dt, hashlib, json, os, sys, time
from pathlib import Path
import numpy as np
C, D, O, R = Path('/cfg'), Path('/docs'), Path('/out'), Path('/repo')
PH = Path('/art/phase-payloads/phd')
W = PH/'main_widen0_v2/PHD-MAIN-WIDEN0-v2'
WI = W/'holdout/internal'
JA = PH/'main_judgeapply_v1/PHD-MAIN-JUDGEAPPLY-v1'
JC = PH/'main_judgecheck_v1/PHD-MAIN-JUDGECHECK-v1'
GJ = PH/'main_gtjudge_v1/PHD-MAIN-GTJUDGE-v1'
RS = PH/'main_rescore_v1/PHD-MAIN-RESCORE-v1'
FT = PH/'main_finaltrain_v1/PHD-MAIN-FINALTRAIN-v1'
DR = PH/'main_prep_discard_rule_v1/PHD-MAIN-PREP-DISCARD-RULE-v1'
UN = PH/'main_uncert_v1/PHD-MAIN-UNCERT-v1'
PC = PH/'main_photocheck_v1/PHD-MAIN-PHOTOCHECK-v1'
WP = PH/'main_wallphoto_v1/PHD-MAIN-WALLPHOTO-v1'
S1 = PH/'main_stage1_v1/PHD-MAIN-STAGE1-v1'
HERE = Path(__file__).parent
SITES = ['B0_b10', 'B173nb_b10', 'R1rep_b10']
REGIONS = ['SW', 'R1', 'R2', 'R3E', 'R4', 'R5', 'B0']
def now(): return dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(timespec='seconds')
def sha(p):
    h = hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda: f.read(8 << 20), b''): h.update(b)
    return h.hexdigest()
def jsafe(v):
    if isinstance(v, dict): return {str(k): jsafe(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)): return [jsafe(x) for x in v]
    if isinstance(v, (np.integer,)): return int(v)
    if isinstance(v, (np.floating, float)): return None if not np.isfinite(v) else float(v)
    if isinstance(v, np.ndarray): return jsafe(v.tolist())
    if isinstance(v, (np.bool_,)): return bool(v)
    return v
def dump(p, v):
    p = Path(p); p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(jsafe(v), ensure_ascii=False, indent=1, allow_nan=False) + '\n')
def loadz(p, keys=None):
    with np.load(p, allow_pickle=False) as z: return {k: z[k] for k in (z.files if keys is None else keys)}
def savez(p, **v):
    p = Path(p); p.parent.mkdir(parents=True, exist_ok=True); tmp = p.with_name(p.name + '.tmp.npz')
    np.savez_compressed(tmp, **v); os.replace(tmp, p)
def cfg():
    lock = json.loads((C/'judgecheck_v2.initial.lock.json').read_text())
    assert sha(C/'judgecheck_v2.json') == lock['config_sha256'], 'config changed after lock'
    return json.loads((C/'judgecheck_v2.json').read_text())
def progress(s):
    with (D/'progress.md').open('a') as f: f.write(f'- {now()}: {s}\n')
def issue(s):
    with (D/'issues.md').open('a') as f: f.write(f'- {now()}: {s}\n')
def tiles(): return [t['id'] for t in json.loads((W/'inputs/tiles.json').read_text())]
def tile_id(): return {t: i for i, t in enumerate(tiles())}
def nmad(x):
    x = np.asarray(x, float); x = x[np.isfinite(x)]
    return float(1.4826*np.median(np.abs(x - np.median(x)))) if len(x) else float('nan')
def wquantile(x, w, q):
    x = np.asarray(x, float); w = np.asarray(w, float); m = np.isfinite(x) & np.isfinite(w) & (w > 0)
    if not m.any(): return float('nan')
    o = np.argsort(x[m]); xs, ws = x[m][o], w[m][o]; c = np.cumsum(ws); c /= c[-1]
    return float(xs[np.searchsorted(c, q, side='left')])
class Timer:
    def __init__(s): s.t0 = time.monotonic(); s.marks = {}
    def mark(s, k): s.marks[k] = time.monotonic() - s.t0; return s.marks[k]
