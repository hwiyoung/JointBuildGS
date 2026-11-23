"""PHD-MAIN-DEPTHFIX-v1 container paths and helpers. Inputs read-only; writes only /df (payload), /docs, /cfg (lock only)."""
import ast, csv, ctypes, datetime as dt, hashlib, json, subprocess, sys, time
from pathlib import Path
import numpy as np
R, C, D, O = map(Path, ['/repo', '/cfg', '/docs', '/df'])
PH = Path('/art/phase-payloads/phd')
FT = PH/'main_finaltrain_v1/PHD-MAIN-FINALTRAIN-v1'
S0 = PH/'main_stage0_v1/PHD-MAIN-STAGE0-v1'
TG = PH/'main_target_v1/PHD-MAIN-TARGET-v1'
JP = PH/'main_judgeprobe_v1/PHD-MAIN-JUDGEPROBE-v1'
NA5 = O/'input/na5'
STEMS = ['R1rep_b10__LoD2', 'R1rep_b10__ALS', 'B173nb_b10__ALS', 'B173nb_b10__LoD2']
STEM_KO = {'R1rep_b10__LoD2': 'R1 × LoD2', 'R1rep_b10__ALS': 'R1 × 항공 LiDAR', 'B173nb_b10__ALS': 'B173 주변 × 항공 LiDAR', 'B173nb_b10__LoD2': 'B173 주변 × LoD2'}
# target type (order 1): 0 가중 평균, 1 영상 깊이, 2 되돌림, 3 결측, -1 목표 없음
TYPE_KO = {0: '가중 평균', 1: '영상 깊이', 2: '되돌림', 3: '결측', -1: '목표 없음'}
JN = {'일치': 0, '사전정보 사용': 1, '영상 깊이 사용': 2, '제거': 3, '결측': 4, '미판정': 9}   # 나5 판정 글 → FINALTRAIN judge_region 번호
TITLE = '깊이 지시 판'

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
def cfg(locked=True):
    p = C/'depthfix_v1.json'
    if locked:
        lock = json.loads((C/'depthfix_v1.lock.json').read_text()); assert sha(p) == lock['config_sha256'], 'config changed after lock'
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
def named(path, names, env):
    """load only the named top-level functions of an existing script, unchanged."""
    tree = ast.parse(Path(path).read_text()); nodes = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name in names]
    assert len(nodes) == len(names), (path, names); exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), env); return env
def ft_calculate():
    env = named(R/'scripts/phd/main_finaltrain_v1/targets.py', ['calculate'], dict(np=np)); return env['calculate']
def rasterizer_env():
    src = R/'scripts/phd/main_target_v1/prepare_maps_r7.py'
    env = named(src, ['rasterizer', 'draw'], dict(np=np, ctypes=ctypes, subprocess=subprocess, Path=Path, __file__=str(src), OUT=O/'tmp/raster'))
    (O/'tmp/raster/tmp').mkdir(parents=True, exist_ok=True); return env, src
def cam_centre(M): M = np.asarray(M, float); return -M[:3, :3].T@M[:3, 3]
