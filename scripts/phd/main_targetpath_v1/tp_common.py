"""PHD-MAIN-TARGETPATH-v1 container paths and helpers (counting only: no training, no model/target/lock change).
Container mounts (launch.py): /repo ro, /art ro, /tp rw (payload), /docs rw (docs/experiments/phd/main_targetpath_v1)."""
import csv, datetime as dt, hashlib, json, math, os, sys, time
from pathlib import Path
import numpy as np

R, D, O = Path('/repo'), Path('/docs'), Path('/tp')
PH = Path('/art/phase-payloads/phd')
FT = PH/'main_finaltrain_v1/PHD-MAIN-FINALTRAIN-v1'
GTT = PH/'main_gttarget_v1/PHD-MAIN-GTTARGET-v1'
GJ = PH/'main_gtjudge_v1/PHD-MAIN-GTJUDGE-v1'
TE = PH/'main_trainerr_v1/PHD-MAIN-TRAINERR-v1'
RS = PH/'main_rescore_v1/PHD-MAIN-RESCORE-v1'
WT = PH/'main_wrongtarget_v1/PHD-MAIN-WRONGTARGET-v1'
S0 = PH/'main_stage0_v1/PHD-MAIN-STAGE0-v1'
TITLE = '목표 전달 셈(PHD-MAIN-TARGETPATH-v1)'
STEMS = ['R1rep_b10__ALS', 'B173nb_b10__ALS', 'B0_b10__ALS', 'R1rep_b10__LoD2', 'B173nb_b10__LoD2', 'B0_b10__LoD2']
STEM_KO = {'R1rep_b10__ALS': 'R1 × 항공 LiDAR', 'B173nb_b10__ALS': 'B173 주변 × 항공 LiDAR', 'B0_b10__ALS': 'B0 × 항공 LiDAR',
           'R1rep_b10__LoD2': 'R1 × LoD2', 'B173nb_b10__LoD2': 'B173 주변 × LoD2', 'B0_b10__LoD2': 'B0 × LoD2'}
RUN_KO = {'ft': '본 방법 판(FINALTRAIN-v1 30,000회)', 'gtt': '참값 목표 판(GTTARGET-v1 씨앗 0, 30,000회)'}
# point groups (order 1)
GRP = ['가: 잃음', '가: 지킴', '나: 고침', '나: 고치지 못함', '대조: 잃음', '대조: 지킴']
KIND = ['1. 맞는 목표', '2. 앞의 다른 목표', '3. 영상 깊이 목표', '4. 뒤의 목표', '5. 감독 없음']
REGION = {0: '일치', 1: '보존', 2: '보정', 3: '보정(빈 공간)', 4: '결측', 9: '미판정', -1: '조각 없음'}
POS3 = ['앞', 'τ 안', '뒤']
GKIND = ['같은 목표에 위치 제약', '다른 목표에 위치 제약', '제약 해제', '제약 없음']
SEED = 20261123
SAMPLE = 5000

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
def _clean(v):
    if isinstance(v, float) and not math.isfinite(v): return None
    if isinstance(v, dict): return {k: _clean(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)): return [_clean(x) for x in v]
    return v
def dump(p, v):
    p = Path(p); p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(_clean(v), ensure_ascii=False, indent=1, allow_nan=False, default=_default)+'\n')
def loadz(p, keys=None):
    with np.load(p, allow_pickle=False) as z: return {k: z[k] for k in (z.files if keys is None else keys)}
def savez(p, **v):
    p = Path(p); p.parent.mkdir(parents=True, exist_ok=True); np.savez_compressed(p, **v)
def issue(s):
    with (D/'issues.md').open('a') as f: f.write(f'- {now()}: {s}\n')
def progress(s):
    with (D/'progress.md').open('a') as f: f.write(f'- {now()}: {s}\n')
def table(name, rows, folder=None):
    keys = list(dict.fromkeys(k for r in rows for k in r)); p = (folder or D/'tables')/name; p.parent.mkdir(parents=True, exist_ok=True)
    with p.with_suffix('.csv').open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=keys, lineterminator='\n'); w.writeheader(); w.writerows([_clean(r) for r in rows])
    dump(p.with_suffix('.json'), dict(title=TITLE, rows=rows, scientific_verdict=None))
    return p.with_suffix('.csv')
def ply_read(p, keep=None):
    with open(p, 'rb') as f:
        h = b''
        while not h.endswith(b'end_header\n'): h += f.readline()
        n = int(h.split(b'element vertex ')[1].split()[0])
        props = [(l.split()[1].decode(), l.split()[-1].decode()) for l in h.split(b'\n') if l.startswith(b'property')]
        dt_ = np.dtype([(nm, '<f4' if t == 'float' else '<i4') for t, nm in props]); a = np.frombuffer(f.read(n*dt_.itemsize), dt_)
    return {k: np.asarray(a[k]) for k in (keep or a.dtype.names)}

# ---------------- runs, models, maps, renders ----------------
def ft_model(stem):
    site, prior = stem.split('__'); return FT/'runs'/site/f'ft_{prior}_s0'/'attempt1/model'
def gtt_model(stem): return GTT/'runs'/stem/'gtt_s0'/'model'
def model_of(stem, run): return ft_model(stem) if run == 'ft' else gtt_model(stem)
def maps_of(stem, run): return (FT if run == 'ft' else GTT)/'stage1'/stem/'maps'
def has_run(stem, run):
    return (model_of(stem, run)/'point_cloud/iteration_30000/point_cloud.ply').exists() and (maps_of(stem, run)/'index.json').exists()
def render_dir(stem, run):
    """30,000 base render (2DGS depth_ratio 0, inherited render_model box mask) of the run; None if not stored."""
    if run == 'gtt':
        p = GTT/'gtj/renders'/f'{stem}__gtt_s0_base'; return p if (p/'receipt.json').exists() else None
    for p in [RS/'addendum3_stage2/renders'/f'{stem}__FINALTRAIN_30000', RS/'addendum3_stage1/renders'/f'{stem}__FINALTRAIN_30000', TE/'addendum6/gtj/renders'/f'{stem}__ra6_ft_base']:
        if (p/'receipt.json').exists(): return p
    return None
def gt_reference(stem):
    """GTJUDGE addendum11 final data rows (= point_id of the wrong-target point files)."""
    return np.load(GJ/'addendum11/final_data'/f'{stem}.npz')
def tau_of(site, prior):
    with (R/'docs/experiments/phd/main_release_v1/tables/stage0/tau_values.csv').open() as f:
        t = next(x for x in csv.DictReader(f) if x['site'] == site and x['prior'] == prior)
    return float(t['roof_tau_m']), float(t['wall_tau_m'])
def view_box(site): return np.array(json.loads((GJ/'views'/f'{site}.json').read_text())['box'])
def gt_points(site):
    a = loadz(GJ/'reference'/site/'dense.npz', ['xyz']); b = loadz(GJ/'reference'/site/'normal_points.npz', ['xyz'])
    P = np.r_[a['xyz'], b['xyz'].astype('f8')]; box = view_box(site); return P[((P >= box[0]) & (P <= box[1])).all(1)]
def project(X, K, M):
    Xc = X@M[:3, :3].T+M[:3, 3]; z = Xc[:, 2]; ok = z > .2; zz = np.where(ok, z, 1.)
    return K[0, 0]*Xc[:, 0]/zz+K[0, 2], K[1, 1]*Xc[:, 1]/zz+K[1, 2], z, ok
def cam_centre(M): return -M[:3, :3].T@M[:3, 3]
def pct(m):
    m = np.asarray(m, bool); return round(100*float(m.mean()), 2) if len(m) else None
def q(v, qs=(25, 50, 75)):
    v = np.asarray(v, float); v = v[np.isfinite(v)]
    return [round(float(x), 4) for x in np.percentile(v, qs)] if len(v) else [None]*len(qs)
