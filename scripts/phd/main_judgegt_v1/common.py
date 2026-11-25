"""PHD-MAIN-JUDGEGT-v1 공통. 학습·렌더·메시 없음, CPU만. 판단 쪽 값은 읽기만 한다. scientific_verdict: null."""
import datetime as dt, hashlib, json, os, struct, subprocess, sys, time
from pathlib import Path
import numpy as np
C, D, O, R = Path('/cfg'), Path('/docs'), Path('/out'), Path('/repo')
PH = Path('/art/phase-payloads/phd')
HERE = Path(__file__).resolve().parent
STAGE = os.environ.get('GT_STAGE', 'ga')
PRIORS = ['LoD2', 'ALS']
PN = {'LoD2': 'LoD2', 'ALS': '항공 LiDAR'}
KN = {1: '지붕', 2: '벽'}
FWD = ['두 자료', '영상', '사전 정보(영상 틀림)', '사전 정보(영상 없음)', '둘 다 틀림', '정답 없음']
FWD_X = '사전 정보 높이 없음'
REV = ['영상 사용(새 면)', '버림', '정답 없음']
JUD = {0: '일치', 1: '사전정보 사용', 2: '영상 깊이 사용', 3: '제거', 4: '결측', 9: '미판정'}
STATE = {0: '두 자료 모두 유효', 1: '사전정보 오류', 2: '영상 깊이 오류', 4: '영상 깊이 결측', 3: '네 경우 밖', -2: '동률', -3: '참값 점 3개 미만', -9: '참값 없음'}
PLACE = {-1: '자리 없음', 0: '면 안쪽', 1: '면 경계', 2: '건물 가장자리'}
SITES = {'B0_b10': 'B0', 'B173nb_b10': 'B173 주변', 'R1rep_b10': 'R1'}
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
    p = Path(p); p.parent.mkdir(parents=True, exist_ok=True); t = p.with_name(p.name + '.tmp')
    t.write_text(json.dumps(jsafe(v), ensure_ascii=False, indent=1, allow_nan=False) + '\n'); os.replace(t, p)
def loadz(p, keys=None):
    with np.load(p, allow_pickle=False) as z: return {k: z[k] for k in (z.files if keys is None else keys)}
def savez(p, **v):
    p = Path(p); p.parent.mkdir(parents=True, exist_ok=True); t = p.with_name(p.name + '.tmp.npz'); np.savez(t, **v); os.replace(t, p)
def cfg():
    lock = json.loads((C/'judgegt_v1.lock.json').read_text()); assert sha(C/'judgegt_v1.json') == lock['config_sha256'], 'config changed after lock'
    return json.loads((C/'judgegt_v1.json').read_text())
def progress(s):
    with (D/'progress.md').open('a') as f: f.write(f'- {now()}: {s}\n')
def issue(s):
    with (D/'issues.md').open('a') as f: f.write(f'- {now()}: {s}\n')
class Timer:
    def __init__(s): s.t0 = time.monotonic()
    def s(s): return time.monotonic() - s.t0
def inp(k, **kw): return Path(cfg()['inputs'][k].format(**kw))
WI = PH/'main_widen0_v2/PHD-MAIN-WIDEN0-v2/holdout/internal'
def buildings(stage=None):
    rows = json.loads(inp('buildings').read_text())['rows']; stage = stage or STAGE
    if stage == 'ga': return {r['building']: r for r in rows if r['in_scope'] and r['group'] == 'experiment'}
    return {r['building']: r for r in rows if r['in_scope']}
def tau_table(): return json.loads(inp('tau').read_text())['values']
def tile_core(tile):
    e, n = map(int, tile.split('_')); sx, sy = 690953.0, 5336071.0
    return (e*100 - sx, e*100 + 100 - sx, n*100 - sy, n*100 + 100 - sy)
# ---- C++ tool
BIN = O/'bin/gtcols'
def build():
    BIN.parent.mkdir(parents=True, exist_ok=True); src = HERE/'gtcols.cpp'
    if BIN.exists() and (BIN.parent/'gtcols.build.json').exists() and json.loads((BIN.parent/'gtcols.build.json').read_text())['source_sha256'] == sha(src): return
    subprocess.run(['g++', '-O3', '-fopenmp', '-std=c++17', '-Wall', str(src), '-o', str(BIN)], check=True)
    dump(BIN.parent/'gtcols.build.json', dict(at=now(), source_sha256=sha(src), binary_sha256=sha(BIN), compiler=subprocess.check_output(['g++', '--version'], text=True).splitlines()[0]))
def run(mode, points, cores, tag):
    """points: .npy (N,3) f4/f8; cores: (nc, k) float64 -> (nc, ow) float64"""
    ow = {'cyl': 2, 'col': 17, 'pca': 8}[mode]; tmp = O/'tmp'; tmp.mkdir(exist_ok=True, parents=True)
    cf = tmp/f'{tag}.cores.bin'; of = tmp/f'{tag}.out.bin'; np.ascontiguousarray(cores, '<f8').tofile(cf)
    with Path(points).open('rb') as f:
        v = np.lib.format.read_magic(f); shape, order, dtype = np.lib.format._read_array_header(f, v); off = f.tell()
    assert not order and shape[1:] == (3,) and dtype in [np.dtype('<f4'), np.dtype('<f8')]
    subprocess.run([str(BIN), mode, str(points), str(off), str(shape[0]), str(cf), str(len(cores)), str(of), 'f4' if dtype.itemsize == 4 else 'f8'], check=True, stderr=subprocess.DEVNULL, env=dict(os.environ, OMP_NUM_THREADS=os.environ.get('GT_THREADS', '24')))
    out = np.fromfile(of, '<f8').reshape(len(cores), ow); cf.unlink(); of.unlink(); return out
# ---- cameras (training)
def rotation(q):
    w, x, y, z = q
    return np.array([[1-2*(y*y+z*z), 2*(x*y-w*z), 2*(x*z+w*y)], [2*(x*y+w*z), 1-2*(x*x+z*z), 2*(y*z-w*x)], [2*(x*z-w*y), 2*(y*z+w*x), 1-2*(x*x+y*y)]])
def camera_centres():
    out = {}
    with inp('cameras').open('rb') as f:
        count, = struct.unpack('<Q', f.read(8))
        for _ in range(count):
            iid, = struct.unpack('<i', f.read(4)); q = struct.unpack('<4d', f.read(32)); t = struct.unpack('<3d', f.read(24)); cid, = struct.unpack('<i', f.read(4)); name = bytearray()
            while True:
                c = f.read(1)
                if c == b'\0': break
                name.extend(c)
            n, = struct.unpack('<Q', f.read(8)); f.seek(n*24, 1); Rm = rotation(q); out[name.decode()] = -Rm.T@np.array(t)
    train = json.loads(inp('image_split').read_text())['train']
    return np.array([out[n] for n in train if n in out]), len(train)
def ans_codes(names, labels):
    m = {s: i for i, s in enumerate(names)}; return np.array([m.get(x, -1) for x in labels], np.int8)
