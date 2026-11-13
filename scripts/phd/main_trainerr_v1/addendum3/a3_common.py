"""PHD-MAIN-TRAINERR-v1 addendum 3 helpers: locked config, folders, record runs (saved states, events), places (GT points, column patches,
outward normals, place masks), Gaussian state per saved state. Inherits addendum 1/2 helpers (a2_common -> a1_common -> common)."""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1/addendum2')
from a2_common import *
A3O = O/'addendum3'; A3D = D/'addendum3'
TLC = PH/'main_trainlog_v1/PHD-MAIN-TRAINLOG-v1/concept_v2/case_B0_b10__LoD2'
TL_CASE_CFG = R/'docs/experiments/phd/main_trainlog_v1/figures_concept_v2/case_B0_b10__LoD2/config/trainlog_v1.json'
RUNS = {'tl_B0_b10_LoD2_s0': dict(stem='B0_b10__LoD2', model=TLC/'runs/B0_b10/tl_B0_b10_LoD2_s0/attempt1/model', kind='scene', places=['visible_low', 'visible_high', 'visible_side', 'south_wall', 'long_wall']),
        'tl_B0_LoD2_own': dict(stem='B0_b10__LoD2', model=O/'runs/B0_b10/tl_B0_LoD2_own/attempt1/model', kind='states', places=['edge_back', 'edge_annex', 'edge_back_control', 'edge_annex_control']),
        'tl_R1_ALS_own': dict(stem='R1rep_b10__ALS', model=O/'runs/R1rep_b10/tl_R1_ALS_own/attempt1/model', kind='states', places=['floor_band', 'floor_control']),
        'ba1_B0_LoD2_nonormal': dict(stem='B0_b10__LoD2', model=A3O/'runs/B0_b10/ba1_B0_LoD2_nonormal/attempt1/model', kind='scene', places=['visible_low', 'visible_high', 'visible_side', 'south_wall', 'long_wall'], short='ba1'),
        'ba2_B0_LoD2_noreset': dict(stem='B0_b10__LoD2', model=A3O/'runs/B0_b10/ba2_B0_LoD2_noreset/attempt1/model', kind='scene', places=['visible_low', 'visible_high', 'visible_side', 'south_wall', 'long_wall'], short='ba2')}
CONTROL_OF = {'visible_low': 'visible_side', 'visible_high': 'visible_side', 'south_wall': 'long_wall', 'edge_back': 'edge_back_control', 'edge_annex': 'edge_annex_control', 'floor_band': 'floor_control'}
PLACE_KO = {'visible_low': '잘 보이는 벽 0~5 m', 'visible_high': '잘 보이는 벽 5~10 m', 'visible_side': '대조: 모서리 옆벽', 'south_wall': '남쪽 끝 벽', 'long_wall': '대조: 길 쪽 긴 벽',
            'edge_back': '가장자리 띠: 뒤쪽 벽 맨 아랫단', 'edge_annex': '가장자리 띠: 별채 평지붕 가장자리', 'edge_back_control': '대조: 칸 ① 대조 점(뒤쪽 벽 아랫단)',
            'edge_annex_control': '대조: 칸 ① 대조 점(별채 평지붕 가장자리)', 'floor_band': 'R1 바닥 띠', 'floor_control': '대조: 칸 ② 대조 점'}
STATE_NAMES = ['same_patch', 'other_patch', 'released', 'background']

def ccfg():
    p = R/'configs/phd/main_trainerr_v1/addendum3.json'; lock = json.loads(p.with_name('addendum3.lock.json').read_text())
    assert sha(p) == lock['config_sha256'], 'addendum3 config changed after lock'
    return json.loads(p.read_text())
def ctable(name, rows): return table(name, rows, folder=A3D/'tables')
def cprogress(s):
    with (A3D/'progress.md').open('a') as f: f.write(f'- {now()}: {s}\n')
def cissue(s):
    with (A3D/'issues.md').open('a') as f: f.write(f'- {now()}: {s}\n')

# ---------------- targets ----------------
class Targets:
    """FINALTRAIN own targets of a scene: valid rows (Gaussian target_index space), anchor, normal, sigma, judgment."""
    def __init__(self, stem):
        t = loadz(targets_of(stem, 'own'), ['target', 'normal', 'sigma', 'region', 'judge_region', 'patch_id', 'area'])
        self.valid = np.flatnonzero(valid_patch(t)); self.vidx = np.full(len(t['target']), -1, 'i8'); self.vidx[self.valid] = np.arange(len(self.valid))
        self.anchor = t['target'][self.valid].astype('f8'); self.normal = t['normal'][self.valid].astype('f8'); self.sigma = t['sigma'][self.valid].astype('f8')
        self.judge = t['judge_region'][self.valid]; self.n_rows = len(t['target']); self.radius = np.sqrt(t['area'][self.valid]/np.pi)   # target disc radius (prepare_inputs rule)
    def v_of_rows(self, rows): rows = np.asarray(rows, 'i8'); return np.where(rows >= 0, self.vidx[np.clip(rows, 0, None)], -1)

def lod2_solid(site):
    pz = loadz(PH/'main_stage1_v1/PHD-MAIN-STAGE1-v1/defs'/site/'prior_LoD2.npz', ['V', 'F']); return scene_from(pz['V'], pz['F'])
def occupancy(sc, P):
    return sc.compute_occupancy(o3d.core.Tensor(np.asarray(P, np.float32))).numpy() > .5

def outward(stem, P, N, u=None):
    """addendum3.json common.outward_normal: place direction u for the named walls; else non-walls up, walls by the LoD2 solid occupancy test."""
    N = np.asarray(N, 'f8').copy()
    if u is not None:
        u = np.asarray(u, 'f8'); s = np.sign(N@u); s[s == 0] = 1; return N*s[:, None], np.full(len(N), 'place_direction')
    rule = np.full(len(N), 'up', dtype=object); wall = np.abs(N[:, 2]) < .5
    up = ~wall & (N[:, 2] < 0); N[up] *= -1
    if wall.any():
        sc = lod2_solid(stem.split('__')[0]); a = occupancy(sc, P[wall]+.5*N[wall]); b = occupancy(sc, P[wall]-.5*N[wall])
        flip = a & ~b; keep = ~a & b; Nw = N[wall]; Nw[flip] *= -1; N[wall] = Nw
        r = np.where(flip | keep, 'lod2_solid', 'stored_normal'); rule[np.flatnonzero(wall)] = r
    return N, rule

# ---------------- places ----------------
def a11_ref(stem):
    a = np.load(GT/'addendum11/final_data'/f'{stem}.npz')
    out = {k: a[f'reference__{k}'] for k in ['point_id', 'xyz', 'normal', 'case_id', 'wall', 'tau_m']}; a.close(); return out
def region_mask(stem, xyz):
    reg = json.loads((O/'region'/f'{stem}.json').read_text()); v = float(reg['voxel_m']); lo = np.asarray(reg['grid_origin']); shp = np.asarray(reg['grid_shape'])
    occ = np.zeros(tuple(shp), bool)
    for b in reg['boxes']:
        b = np.asarray(b[:6], float); i0 = np.floor((b[[0, 2, 4]]-lo)/v+1e-9).astype(int); i1 = np.ceil((b[[1, 3, 5]]-lo)/v-1e-9).astype(int); occ[i0[0]:i1[0], i0[1]:i1[1], i0[2]:i1[2]] = True
    k = np.floor((np.asarray(xyz)-lo)/v).astype(int); ok = np.all((k >= 0) & (k < shp), 1); out = np.zeros(len(k), bool); out[ok] = occ[k[ok, 0], k[ok, 1], k[ok, 2]]; return out

def place_points(place):
    """dict: stem, xyz, normal (GT), point_id, patch_row (column patch target row), out (oriented normal of the column patch), rule, u."""
    c = ccfg(); cases = json.loads((TLC/'concept_v2/case_zones.json').read_text())['zones']['2']
    if place.startswith('visible') or place in ('south_wall', 'long_wall'):
        stem = 'B0_b10__LoD2'; ref = a11_ref(stem); x = ref['xyz'].astype('f8'); n = ref['normal'].astype('f8'); w = ref['wall'].astype(bool)
        if place.startswith('visible'):
            from shapely.geometry import Polygon
            u = np.array(cases['wall_normal_out_xy']+[0.]); poly = Polygon(cases['box_polygon_xy']); g0 = json.loads(TL_CASE_CFG.read_text())['scope']['ground_z']
            import shapely; inside = shapely.contains_xy(poly, x[:, 0], x[:, 1]); h = x[:, 2]-g0; dotu = np.abs(n@u)
            sel = {'visible_low': w & inside & (dotu > .9) & (h >= 0) & (h < 5), 'visible_high': w & inside & (dotu > .9) & (h >= 5) & (h < 10),
                   'visible_side': w & inside & (dotu < .3) & (h >= 0) & (h < 10)}[place]
            if place == 'visible_side': u = None
        else:
            which = 'south' if place == 'south_wall' else 'long'; a_, d_, m = wall_coords(x, which); sel = w & m & (np.abs(d_) <= 1.); u = wall_normal(which)
        ii = np.flatnonzero(sel); rp = gt_row_patch(stem)[ref['point_id'][ii]]
        P = dict(stem=stem, xyz=x[ii], normal=n[ii], point_id=ref['point_id'][ii], patch_row=rp, u=u)
    elif place.startswith('edge'):
        stem = 'B0_b10__LoD2'; which = 'back_wall_bottom' if place.startswith('edge_back') else 'annex_roof_edge'
        if place.endswith('control'):
            s = loadz(O/'sets_tl/c1_own_control.npz'); m = place_mask(s['xyz'], which)
            if m.sum() < 50: m = region_mask(stem, s['xyz'])
        else: s = loadz(O/'sets_tl/c1_own_lost.npz'); m = place_mask(s['xyz'], which)
        ii = np.flatnonzero(m); P = dict(stem=stem, xyz=s['xyz'][ii], normal=s['normal'][ii], point_id=s['point_id'][ii], patch_row=s['patch_row'][ii], u=None, set_index=ii, cell='c1', set='control' if place.endswith('control') else 'lost', tau=s['tau_m'][ii])
    elif place.startswith('floor'):
        stem = 'R1rep_b10__ALS'; s = loadz(O/('sets_tl/c2_own_lost.npz' if place == 'floor_band' else 'sets_tl/c2_own_control.npz'))
        m = np.ones(len(s['xyz']), bool) if place == 'floor_band' else region_mask(stem, s['xyz'])
        ii = np.flatnonzero(m); P = dict(stem=stem, xyz=s['xyz'][ii], normal=s['normal'][ii], point_id=s['point_id'][ii], patch_row=s['patch_row'][ii], u=None, set_index=ii, cell='c2', set='lost' if place == 'floor_band' else 'control', tau=s['tau_m'][ii])
    else: raise ValueError(place)
    T = Targets(P['stem']); v = T.v_of_rows(P['patch_row']); P['v'] = v; ok = v >= 0
    nrm = np.where(ok[:, None], T.normal[np.clip(v, 0, None)], P['normal']); out, rule = outward(P['stem'], P['xyz'], nrm, P['u'])
    P['out'] = out; P['rule'] = rule; P['anchor'] = np.where(ok[:, None], T.anchor[np.clip(v, 0, None)], P['xyz']); P['T'] = T
    vox = np.unique(np.floor(P['xyz']/.25).astype('i8'), axis=0); P['area_m2'] = len(vox)*.0625
    return P

# ---------------- record runs ----------------
def saves(model):
    rows = [json.loads(l) for l in (model/'trainlog/saves.jsonl').read_text().splitlines() if l.strip()]
    def key(r): return (r['iteration'], 0 if r['name'].endswith('pre_reset') else 1)
    return sorted(rows, key=key)
def load_state(model, name, kind):
    """activated fields of all Gaussians (scene .pt) or the in-range Gaussians (states .npz)."""
    if kind == 'scene':
        import torch
        s = torch.load(model/'trainlog/scene'/f'{name}.pt', map_location='cpu', weights_only=False)
        return dict(xyz=s['xyz'].double().numpy(), opacity=torch.sigmoid(s['opacity'][:, 0]).numpy(), size=torch.exp(s['scaling']).max(1).values.numpy(),
                    tag=s['target_tag'].numpy(), tidx=s['target_index'].numpy(), uid=s['uid'].numpy(), born_at=s['born_at'].numpy(), origin=s['origin'].numpy())
    z = loadz(model/'trainlog/states'/f'{name}.npz')
    return dict(xyz=z['xyz'].astype('f8'), opacity=z['opacity'], size=z['scale'].max(1), tag=z['target_tag'], tidx=z['target_index'], uid=z['uid'], born_at=z['born_at'], origin=z['origin'])
def load_events(model, kinds=('delete', 'release', 'retarget', 'birth')):
    out = {}
    for k in kinds:
        parts = [loadz(f) for f in sorted((model/'trainlog/events').glob(f'{k}_*.npz'))]
        out[k] = {f: np.concatenate([p[f] for p in parts]) for f in parts[0]} if parts else {}
    return out

def korean_plt():
    import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt; from matplotlib import font_manager as fm
    F = '/fonts/NotoSansCJK-Regular.ttc'; fm.fontManager.addfont(F); plt.rcParams['font.family'] = fm.FontProperties(fname=F).get_name(); plt.rcParams['axes.unicode_minus'] = False
    return plt
