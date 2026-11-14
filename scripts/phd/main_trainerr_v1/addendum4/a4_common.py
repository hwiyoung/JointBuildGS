"""PHD-MAIN-TRAINERR-v1 addendum 4 helpers. Inherits addendum 3 (a3_common: places, record runs, states, events).
Adds the places of addendum4_b.json (annex box of B0 x ALS, edge floater of B173 x ALS) and the record runs of addendum 4."""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1/addendum3')
from a3_common import *
A4O = O/'addendum4'; A4D = D/'addendum4'
TLM = PH/'main_trainlog_v1/PHD-MAIN-TRAINLOG-v1'
RUNS4 = {
    'tl_R1_ALS_own': dict(stem='R1rep_b10__ALS', model=O/'runs/R1rep_b10/tl_R1_ALS_own/attempt1/model', kind='states', places=['floor_band', 'floor_control'], last='30000'),
    'sa1_R1_ALS_record6000': dict(stem='R1rep_b10__ALS', model=A4O/'runs/R1rep_b10/sa1_R1_ALS_record6000/attempt1/model', kind='states', places=['floor_band', 'floor_control'], last='6000'),
    'ba3_B0_ALS_record': dict(stem='B0_b10__ALS', model=A3O/'runs/B0_b10/ba3_B0_ALS_record/attempt1/model', kind='states', places=['annex_wrong', 'annex_right'], last='30000'),
    'tl_B0_LoD2_own': dict(stem='B0_b10__LoD2', model=O/'runs/B0_b10/tl_B0_LoD2_own/attempt1/model', kind='states', places=['edge_back', 'edge_annex', 'edge_back_control', 'edge_annex_control'], last='30000'),
    'tl_B173nb_b10_ALS_s0': dict(stem='B173nb_b10__ALS', model=TLM/'runs/B173nb_b10/tl_B173nb_b10_ALS_s0/attempt2/model', kind='scene', places=['floater', 'floater_control'], last='30000'),
    'tl_B0_b10_LoD2_s0': dict(stem='B0_b10__LoD2', model=TLC/'runs/B0_b10/tl_B0_b10_LoD2_s0/attempt1/model', kind='scene', places=['edge_back', 'edge_annex', 'edge_back_control', 'edge_annex_control'], last='30000'),
}
PLACE_KO.update({'annex_wrong': '별채 상자: 틀린 목표(참값 1 m 밖)', 'annex_right': '대조: 별채 상자 맞는 목표(참값 0.2 m 안)', 'floater': '가장자리 뜬 면', 'floater_control': '대조: 건물 안 맞는 면',
                 'floor_control': '대조: 옆의 정상 바닥·지붕(기록 범위 안 지킨 점)'})
CONTROL_OF.update({'annex_wrong': 'annex_right', 'floater': 'floater_control'})
ANNEX = dict(x=[86, 98], y=[-1, 7], z=[-46, -30])

def bcfg():
    p = R/'configs/phd/main_trainerr_v1/addendum4_b.json'; assert sha(p) == json.loads(p.with_name('addendum4_b.lock.json').read_text())['config_sha256']; return json.loads(p.read_text())
def acfg():
    p = R/'configs/phd/main_trainerr_v1/addendum4.json'; assert sha(p) == json.loads(p.with_name('addendum4.lock.json').read_text())['config_sha256']; return json.loads(p.read_text())
def dtable(name, rows): return table(name, rows, folder=A4D/'tables')
def dprogress(s):
    with (A4D/'progress.md').open('a') as f: f.write(f'- {now()}: {s}\n')
def dissue(s):
    with (A4D/'issues.md').open('a') as f: f.write(f'- {now()}: {s}\n')

def annex_patches(which):
    """valid-row indices (Gaussian target_index space) of the B0 x ALS own patches with anchor in the annex box; wrong = > 1 m from GT reference, right = <= 0.2 m."""
    T = Targets('B0_b10__ALS'); a = T.anchor; b = ANNEX
    inb = (a[:, 0] >= b['x'][0]) & (a[:, 0] <= b['x'][1]) & (a[:, 1] >= b['y'][0]) & (a[:, 1] <= b['y'][1]) & (a[:, 2] >= b['z'][0]) & (a[:, 2] <= b['z'][1])
    ref = a11_ref('B0_b10__ALS'); d = np.full(len(a), np.inf); ii = np.flatnonzero(inb); d[ii] = cKDTree(ref['xyz'].astype('f8')).query(a[ii])[0]
    sel = inb & (d > 1.) if which == 'annex_wrong' else inb & (d <= .2)
    return np.flatnonzero(sel), T, d

def place_patches(place):
    """dict: v (valid-row target indices of the place), T, P (place_points dict when GT-point defined, else None), out (outward normal per valid row of v)."""
    if place.startswith('annex'):
        v, T, d = annex_patches(place); out, rule = outward('B0_b10__ALS', T.anchor[v], T.normal[v]); return dict(v=v, T=T, P=None, out=out, stem='B0_b10__ALS', gt_dist=d[v])
    if place.startswith('floater'): return dict(v=np.zeros(0, 'i8'), T=Targets('B173nb_b10__ALS'), P=None, out=np.zeros((0, 3)), stem='B173nb_b10__ALS')
    P = place_points(place); v = np.unique(P['v'][P['v'] >= 0]); T = P['T']
    first = {int(x): i for i, x in reversed(list(enumerate(P['v']))) if x >= 0}; out = np.stack([P['out'][first[int(x)]] for x in v]) if len(v) else np.zeros((0, 3))
    return dict(v=v, T=T, P=P, out=out, stem=P['stem'])

def floater_centres(which):
    z = loadz(A3O/'ma/points.npz'); key = 'edge_face_centres' if which == 'floater' else 'control_vertices'   # addendum3 ma stores 200,000 sampled control-face vertices, not centres
    C = z[key].astype('f8')
    if len(C) > 20000: C = C[np.sort(np.random.default_rng(20261115).choice(len(C), 20000, replace=False))]
    return C

def med(x): x = np.asarray(x, 'f8'); x = x[np.isfinite(x)]; return float(np.median(x)) if len(x) else None
def pct(m): m = np.asarray(m); return 100*float(m.mean()) if m.size else None
def raw_state(model, name): return loadz(model/'trainlog/states'/f'{name}.npz')
PLACE_KO.update({'edge_back_control': '대조: 같은 범위의 지킨 점(뒤쪽 벽 아랫단 쪽)', 'edge_annex_control': '대조: 같은 범위의 지킨 점(별채 평지붕 쪽)',
                 'floor_control': '대조: 옆의 정상 바닥·지붕', 'edge_back': '가장자리 띠: 뒤쪽 벽 맨 아랫단', 'edge_annex': '가장자리 띠: 별채 평지붕 가장자리'})

def place_points_cached(place):
    """place_points computed once in the CPU image (shapely) and cached in addendum4/places/<place>.npz for the GPU image."""
    p = A4O/'places'/f'{place}.npz'
    if not p.exists():
        P = place_points(place); p.parent.mkdir(parents=True, exist_ok=True)
        savez(p, **{k: np.asarray(v) for k, v in P.items() if k not in ('T', 'rule') and v is not None}, has_u=np.asarray(P['u'] is not None))
    z = loadz(p); P = {k: z[k] for k in z if k != 'has_u'}; P['stem'] = str(P['stem']); P['area_m2'] = float(P['area_m2'])
    if not bool(z['has_u']): P['u'] = None
    P['T'] = Targets(P['stem']); return P

if __name__ == '__main__' and len(sys.argv) > 2 and sys.argv[1] == 'cache':
    for pl in sys.argv[2:]: place_points_cached(pl); print('CACHED', pl, flush=True)
