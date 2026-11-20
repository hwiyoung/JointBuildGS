"""PHD-MAIN-MVSFILTER-v1 공통: 경로, 잠금, 기록, 카메라 읽기. 학습 없음, 새 광도 점수 없음. scientific_verdict: null."""
import datetime as dt, hashlib, json, os, struct, sys, time
from pathlib import Path
import numpy as np
C, D, O, R = Path('/cfg'), Path('/docs'), Path('/out'), Path('/repo')
PH = Path('/art/phase-payloads/phd')
W = PH/'main_widen0_v2/PHD-MAIN-WIDEN0-v2'; WS = W/'mvs/full'; WI = W/'holdout/internal'
JC = PH/'main_judgecheck_v2/PHD-MAIN-JUDGECHECK-v2'
JS = PH/'main_judgestruct_v1/PHD-MAIN-JUDGESTRUCT-v1'
JP = PH/'main_judgeprobe_v1/PHD-MAIN-JUDGEPROBE-v1'
JABL = PH/'main_judgeabl_v1/PHD-MAIN-JUDGEABL-v1'
METHODS = ['none', 'A', 'B_orig', 'B_view', 'C']
MNAME = {'none': '지금 점군', 'A': '방법 A (COLMAP 2단계)', 'B_orig': '방법 B-원문 (Wolff 외)', 'B_view': '방법 B-시점 (세션 판)', 'C': '방법 C (통계적, 참고)', 'A2': '방법 A2 (일치 시점 수 c≥5, 세션 판)', 'A2d0p5': '방법 A2-깊이 0.5 % (세션 판)', 'A2d0p2': '방법 A2-깊이 0.2 % (세션 판)', 'A2d0p1': '방법 A2-깊이 0.1 % (세션 판)'}
H, Wd = 741, 1024
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
    p = Path(p); p.parent.mkdir(parents=True, exist_ok=True); tmp = p.with_name(p.name + '.tmp')
    tmp.write_text(json.dumps(jsafe(v), ensure_ascii=False, indent=1, allow_nan=False) + '\n'); os.replace(tmp, p)
def loadz(p, keys=None):
    with np.load(p, allow_pickle=False) as z: return {k: z[k] for k in (z.files if keys is None else keys)}
def savez(p, **v):
    p = Path(p); p.parent.mkdir(parents=True, exist_ok=True); tmp = p.with_name(p.name + '.tmp.npz')
    np.savez_compressed(tmp, **v); os.replace(tmp, p)
class Timer:
    def __init__(self): self.t0 = time.monotonic(); self.marks = {}
    def s(self): return time.monotonic() - self.t0
    def mark(self, k): self.marks[k] = self.s(); return self.marks[k]
def cfg():
    lock = json.loads((C/'mvsfilter_v1.lock.json').read_text()); assert sha(C/'mvsfilter_v1.json') == lock['config_sha256'], 'config changed after lock'
    return json.loads((C/'mvsfilter_v1.json').read_text())
def progress(s):
    with (D/'progress.md').open('a') as f: f.write(f'- {now()}: {s}\n')
def issue(s):
    with (D/'issues.md').open('a') as f: f.write(f'- {now()}: {s}\n')
def poses(path):
    out = {}
    with Path(path).open('rb') as f:
        count, = struct.unpack('<Q', f.read(8))
        for _ in range(count):
            iid, = struct.unpack('<i', f.read(4)); q = struct.unpack('<4d', f.read(32)); t = struct.unpack('<3d', f.read(24)); cid, = struct.unpack('<i', f.read(4)); name = bytearray()
            while True:
                c = f.read(1)
                if c == b'\0': break
                name.extend(c)
            n, = struct.unpack('<Q', f.read(8)); f.seek(n*24, 1); out[name.decode()] = (q, t)
    return out
def image_ids(path):
    out = {}
    with Path(path).open('rb') as f:
        count, = struct.unpack('<Q', f.read(8))
        for _ in range(count):
            iid, = struct.unpack('<i', f.read(4)); f.seek(32+24+4, 1); name = bytearray()
            while True:
                c = f.read(1)
                if c == b'\0': break
                name.extend(c)
            n, = struct.unpack('<Q', f.read(8)); f.seek(n*24, 1); out[name.decode()] = iid
    return out
def rotation(q):
    w, x, y, z = q
    return np.array([[1-2*(y*y+z*z), 2*(x*y-w*z), 2*(x*z+w*y)], [2*(x*y+w*z), 1-2*(x*x+z*z), 2*(y*z-w*x)], [2*(x*z-w*y), 2*(y*z+w*x), 1-2*(x*x+y*y)]])
def read_bin(path):
    raw = Path(path).read_bytes(); end = 0
    for _ in range(3): end = raw.find(b'&', end, 100) + 1
    w, h, c = map(int, raw[:end].split(b'&')[:3])
    a = np.frombuffer(raw, dtype='<f4', offset=end, count=w*h*c).reshape((c, h, w)).transpose(1, 2, 0)   # COLMAP: column-major per channel
    return a[..., 0] if c == 1 else a
def read_depth(path):
    raw = Path(path).read_bytes(); end = 0
    for _ in range(3): end = raw.find(b'&', end, 100) + 1
    w, h, c = map(int, raw[:end].split(b'&')[:3]); assert c == 1
    return np.frombuffer(raw, dtype='<f4', offset=end, count=w*h).reshape((w, h), order='F').T
def cam_world(name, rows):
    q, tt = rows[name]; Wm = np.eye(4, dtype=np.float32); Wm[:3, :3] = rotation(q); Wm[:3, 3] = tt
    return Wm, np.linalg.inv(Wm.astype(float))
def unproject(view, pix, names, rows, K, depth_cache=None):
    """화소(영상 번호, 행*1024+열) -> WIDEN0 mvs_points 와 같은 float32 세계 좌표 (점 원점 690953, 5336071 뺀 좌표)."""
    fx, fy, cx, cy = K; out = np.empty((len(view), 3), np.float32)
    for v in np.unique(view):
        m = np.flatnonzero(view == v); name = names[int(v)]
        z = depth_cache[int(v)] if depth_cache is not None else read_depth(WS/'stereo/depth_maps'/f'{name}.geometric.bin')
        vv, uu = np.divmod(pix[m].astype(np.int64), 1024); dd = z[vv, uu].astype(float)
        cam = np.column_stack([(uu-cx)/fx*dd, (vv-cy)/fy*dd, dd]); _, Cm = cam_world(name, rows)
        out[m] = (cam@Cm[:3, :3].T + Cm[:3, 3]).astype(np.float32)
    return out
def intrinsics():
    return json.loads((O/'pixmap/valid_counts.json').read_text())['intrinsics']
def tiles():
    return [t['id'] for t in json.loads((W/'inputs/tiles.json').read_text())]
def load_mask(method):
    """방법의 살아남은 화소: (819, 741*1024) bool. none = 깊이 > 0 화소 모두."""
    p = O/'masks'/f'{method}.npy'
    return np.unpackbits(np.load(p), axis=1, count=H*Wd).astype(bool)
def save_mask(method, m):
    (O/'masks').mkdir(parents=True, exist_ok=True); np.save(O/'masks'/f'{method}.npy', np.packbits(m.reshape(len(m), -1), axis=1))
