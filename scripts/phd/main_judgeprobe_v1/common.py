"""PHD-MAIN-JUDGEPROBE-v1 공통. 학습 없음, 새 광도 점수 없음, CPU만. scientific_verdict: null.
JUDGECHECK-v2(JC) 의 저장된 값만 읽는다. JC 코드(jc2_judge, 읽기·세기 함수)는 /repo 에서 옮겨 쓴다."""
import datetime as dt, hashlib, json, os, sys, time
from pathlib import Path
import numpy as np
C, D, O, R = Path('/cfg'), Path('/docs'), Path('/out'), Path('/repo')
PH = Path('/art/phase-payloads/phd')
JC = PH/'main_judgecheck_v2/PHD-MAIN-JUDGECHECK-v2'
W = PH/'main_widen0_v2/PHD-MAIN-WIDEN0-v2'; WI = W/'holdout/internal'
JCS = R/'scripts/phd/main_judgecheck_v2'
sys.path.insert(0, str(JCS)); sys.path.insert(0, str(JCS/'inherited'))
import jc2_judge as J   # JC 판정 함수 그대로
REGIONS = ['SW', 'R1', 'R2', 'R3E', 'R4', 'R5', 'B0']
UNITS = {'LoD2_roof': ('LoD2', 1), 'LoD2_wall': ('LoD2', 2), 'ALS_roof': ('ALS', 1)}
CASE = {0: '두 자료 모두 유효', 1: '사전정보 오류', 2: '영상 깊이 오류', 4: '영상 깊이 결측'}
MATCH = {0: 0, 1: 2, 2: 1, 4: 4}
PLACE = {0: '면 안쪽', 1: '면 경계', 2: '건물 가장자리'}
PCODE = {0: '지지', 1: '반박', 2: '둘 다 낮음', 3: '둘 다 높음', 4: 'MVS 면 없음', 5: '조각 부족', 6: '무늬 없음', 7: '사진 부족', 9: '셈 안 함'}
JUD = {0: '일치', 1: '사전정보 사용', 2: '영상 깊이 사용', 3: '제거', 4: '결측', 9: '미판정'}
def now(): return dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(timespec='seconds')
def sha(p):
    h = hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda: f.read(8 << 20), b''): h.update(b)
    return h.hexdigest()
def jsafe(v):
    if isinstance(v, dict): return {str(k): jsafe(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)): return [jsafe(x) for x in v]
    if isinstance(v, np.integer): return int(v)
    if isinstance(v, (np.floating, float)): return None if not np.isfinite(v) else float(v)
    if isinstance(v, np.ndarray): return jsafe(v.tolist())
    if isinstance(v, np.bool_): return bool(v)
    return v
def dump(p, v):
    p = Path(p); p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(jsafe(v), ensure_ascii=False, indent=1, allow_nan=False) + '\n')
def loadz(p, keys=None):
    with np.load(p, allow_pickle=False) as z: return {k: z[k] for k in (z.files if keys is None else keys)}
def savez(p, **v):
    p = Path(p); p.parent.mkdir(parents=True, exist_ok=True); tmp = p.with_name(p.name + '.tmp.npz'); np.savez(tmp, **v); os.replace(tmp, p)
def cfg():
    lock = json.loads((C/'judgeprobe_v1.lock.json').read_text()); assert sha(C/'judgeprobe_v1.json') == lock['config_sha256'], 'config changed after lock'
    return json.loads((C/'judgeprobe_v1.json').read_text())
def progress(s):
    with (D/'progress.md').open('a') as f: f.write(f'- {now()}: {s}\n')
def issue(s):
    with (D/'issues.md').open('a') as f: f.write(f'- {now()}: {s}\n')
def tiles(prior): return [p.stem.split('__')[0] for p in sorted((JC/'geometry_raw').glob(f'*__{prior}.npz'))]
def wq(x, w, q):
    """넓이 가중 분위 (JC jc2_judge.quantile 규칙)."""
    return J.quantile(np.asarray(x, float), np.asarray(w, float), q)
def wauc(xa, wa, xb, wb):
    """넓이 가중 AUC = P(a > b) + 0.5 P(a = b)."""
    ma = np.isfinite(xa) & (wa > 0); mb = np.isfinite(xb) & (wb > 0); xa, wa, xb, wb = xa[ma], wa[ma], xb[mb], wb[mb]
    if not len(xa) or not len(xb): return np.nan
    o = np.argsort(xb, kind='stable'); xb, wb = xb[o], wb[o]; cw = np.concatenate([[0.], np.cumsum(wb)])
    lo = np.searchsorted(xb, xa, 'left'); hi = np.searchsorted(xb, xa, 'right')
    return float(((cw[lo] + 0.5*(cw[hi] - cw[lo]))*wa).sum()/(wa.sum()*wb.sum()))
def plane_distance(x, g, c, n, h, wall):
    """JC s4_truth_exp.plane_distance 그대로."""
    p0 = c + h[:, None]*n; den = np.einsum('ij,ij->i', g, n)
    with np.errstate(divide='ignore', invalid='ignore'): t = np.einsum('ij,ij->i', p0 - x, n)/den
    lim = np.where(wall, 5., 10.); t[~np.isfinite(h) | (np.abs(den) < 1e-9) | (np.abs(t) > lim)] = np.nan
    return t
class Timer:
    def __init__(s): s.t0 = time.monotonic()
    def s(s): return time.monotonic() - s.t0
