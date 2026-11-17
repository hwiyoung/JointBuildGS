"""PHD-MAIN-TRAINERR-v1 addendum 5 helpers (addendum5.json, locked). Inherits addendum 4 (a4_common -> a3_common: places, record runs, states, events).
Groups are defined by place (problem group / control group), re-defined at each stage; kinds are counted inside the group."""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1/addendum4')
from a4_common import *
A5O = O/'addendum5'; A5D = D/'addendum5'
KIND_KO = ['같은 목표에 묶인 것', '다른 목표에 묶인 것', '풀린 것', '묶이지 않은 것']
HOW_KO = {0: '사전 정보 씨앗', 1: '배경 씨앗', 2: '복제', 3: '분할'}
REASON_KO = {1: '불투명도 문턱', 2: '크기 문턱(공간)', 3: '크기 문턱(화면)', 4: '그 밖의 정리', 5: '분할로 대체된 부모'}

def cfg5():
    p = R/'configs/phd/main_trainerr_v1/addendum5.json'; assert sha(p) == json.loads(p.with_name('addendum5.lock.json').read_text())['config_sha256'], 'addendum5 config changed after lock'
    return json.loads(p.read_text())
def table5(name, rows): return table(name, rows, folder=A5D/'tables')
def progress5(s):
    with (A5D/'progress.md').open('a') as f: f.write(f'- {now()}: {s}\n')

def place_points5(place):
    """addendum 4 cached place points (read only); a missing cache is computed here and stored under addendum5/places."""
    p4 = A4O/'places'/f'{place}.npz'
    if p4.exists(): return place_points_cached(place)
    p = A5O/'places'/f'{place}.npz'
    if not p.exists():
        P = place_points(place); p.parent.mkdir(parents=True, exist_ok=True)
        savez(p, **{k: np.asarray(v) for k, v in P.items() if k not in ('T', 'rule') and v is not None}, has_u=np.asarray(P['u'] is not None))
    z = loadz(p); P = {k: z[k] for k in z if k != 'has_u'}; P['stem'] = str(P['stem']); P['area_m2'] = float(P['area_m2'])
    if not bool(z['has_u']): P['u'] = None
    P['T'] = Targets(P['stem']); return P

class Band:
    """problem/control group geometry: Gaussian centre with normal offset dn in [lo, hi] above the target plane of a place point and tangent offset <= tan from it."""
    def __init__(self, P, lo=.2, hi=3., tan=.25):
        self.P = P; self.lo, self.hi, self.tan = lo, hi, tan; self.tree = cKDTree(P['xyz'].astype('f8'))
        self.vset = np.unique(P['v'][P['v'] >= 0]); self.box = (P['xyz'].min(0)-hi-tan, P['xyz'].max(0)+hi+tan)
    def offsets(self, X, k=48):
        """dn (normal offset above the nearest-in-tangent place point's target plane) and dt; nan where no place point within tan."""
        X = np.asarray(X, 'f8'); n = len(X); dn = np.full(n, np.nan); dt = np.full(n, np.nan); pj = np.full(n, -1, 'i8')
        inb = np.all((X >= self.box[0]) & (X <= self.box[1]), 1); ii = np.flatnonzero(inb)
        if not len(ii): return dn, dt, pj
        r = float(np.hypot(self.hi+.05, self.tan)); P = self.P
        for s in range(0, len(ii), 200000):
            jj = ii[s:s+200000]; d, j = self.tree.query(X[jj], k=k, distance_upper_bound=r); ok = np.isfinite(d); jc = np.clip(j, 0, len(P['xyz'])-1)
            e = X[jj][:, None]-P['xyz'][jc]; o = P['out'][jc]; en = (e*o).sum(2); t = np.linalg.norm(e-en[..., None]*o, axis=2)
            n_ = ((X[jj][:, None]-P['anchor'][jc])*o).sum(2); t = np.where(ok & (t <= self.tan), t, np.inf); b = t.argmin(1); bt = t[np.arange(len(jj)), b]
            has = np.isfinite(bt); dn[jj[has]] = n_[np.arange(len(jj)), b][has]; dt[jj[has]] = bt[has]; pj[jj[has]] = jc[np.arange(len(jj)), b][has]
        return dn, dt, pj
    def member(self, X):
        dn, dt, pj = self.offsets(X); m = np.isfinite(dn) & (dn >= self.lo) & (dn <= self.hi); return m, dn, pj

def kind_of5(tag, tidx, vset):
    tag = np.asarray(tag); tidx = np.asarray(tidx)
    return np.where(tag == 1, np.where(np.isin(tidx, vset), 0, 1), np.where(tag == 2, 2, 3)).astype('i1')

def state_name(it):
    """interval boundary -> saved state name (3000 -> the state before the reset)."""
    it = int(it); return '3000_pre_reset' if it == 3000 else str(it)

def run_model(run): return RUNS4[run]['model']
def start_info(run): return json.loads((run_model(run)/'trainlog/start.json').read_text())
def record_region_mask(run, X):
    """the record range of a run: its region file (te path mapped to the payload root)."""
    rf = start_info(run)['region_file']; p = Path(rf.replace('/te/', str(O)+'/')); reg = json.loads(p.read_text())
    v = float(reg['voxel_m']); lo = np.asarray(reg['grid_origin']); shp = np.asarray(reg['grid_shape']); occ = np.zeros(tuple(shp), bool)
    for b in reg['boxes']:
        b = np.asarray(b[:6], float); i0 = np.floor((b[[0, 2, 4]]-lo)/v+1e-9).astype(int); i1 = np.ceil((b[[1, 3, 5]]-lo)/v-1e-9).astype(int); occ[i0[0]:i1[0], i0[1]:i1[1], i0[2]:i1[2]] = True
    k = np.floor((np.asarray(X)-lo)/v).astype(int); ok = np.all((k >= 0) & (k < shp), 1); out = np.zeros(len(k), bool); out[ok] = occ[k[ok, 0], k[ok, 1], k[ok, 2]]; return out

def q4(x):
    x = np.asarray(x, 'f8'); x = x[np.isfinite(x)]
    return [float(v) for v in np.quantile(x, [.25, .5, .75])] if len(x) else [None, None, None]

# ---------------- addendum-5 places (R1 x LoD2 wall 1, edge floater) ----------------
def _finish(stem, xyz, normal, point_id, u=None):
    rp = gt_row_patch(stem)[point_id]; P = dict(stem=stem, xyz=xyz, normal=normal, point_id=point_id, patch_row=rp, u=u)
    T = Targets(stem); v = T.v_of_rows(rp); P['v'] = v; ok = v >= 0
    nrm = np.where(ok[:, None], T.normal[np.clip(v, 0, None)], normal); out, rule = outward(stem, xyz, nrm, u)
    P['out'] = out; P['rule'] = rule; P['anchor'] = np.where(ok[:, None], T.anchor[np.clip(v, 0, None)], xyz); P['T'] = T
    P['area_m2'] = len(np.unique(np.floor(xyz/.25).astype('i8'), axis=0))*.0625; return P

def place_points_a5(place):
    """r1_lod2_wall1: addendum4 ma cluster 1 lost points of R1rep_b10__LoD2; r1_lod2_wall_control: kept wall points (judgment mesh and FINALTRAIN 30000 both within tau)
    within 30 m of cluster 1's centre."""
    stem = 'R1rep_b10__LoD2'; A = np.load(GT/'addendum11/final_data'/f'{stem}.npz'); ref = a11_ref(stem)
    el = A['reference__eligible'].astype(bool); tw = A['reference__judgment_mesh__within_tau1'].astype(bool); rw = A['reference__FINALTRAIN_30000__within_tau1'].astype(bool)
    z = loadz(A4O/'ma/R1rep_b10__LoD2.npz'); c1 = z['cluster_rank'] == 1; ce = z['xyz'][c1].astype('f8').mean(0)
    if place == 'r1_lod2_wall1':
        pid = z['point_id'][c1]; idx = {int(p): i for i, p in enumerate(ref['point_id'])}; ii = np.array([idx[int(p)] for p in pid])
    else:
        X = ref['xyz'].astype('f8'); ii = np.flatnonzero(el & tw & rw & ref['wall'].astype(bool) & (np.linalg.norm(X-ce, axis=1) <= 30.))
    return _finish(stem, ref['xyz'][ii].astype('f8'), ref['normal'][ii].astype('f8'), ref['point_id'][ii])

_place_points5_base = place_points5
def place_points5(place):
    if not place.startswith('r1_lod2'): return _place_points5_base(place)
    p = A5O/'places'/f'{place}.npz'
    if not p.exists():
        P = place_points_a5(place); p.parent.mkdir(parents=True, exist_ok=True)
        savez(p, **{k: np.asarray(v) for k, v in P.items() if k not in ('T', 'rule', 'u') and v is not None})
    z = loadz(p); P = {k: z[k] for k in z}; P['stem'] = str(P['stem']); P['area_m2'] = float(P['area_m2']); P['u'] = None; P['T'] = Targets(P['stem']); return P

class Near:
    """floater groups: Gaussian centre within r of a point set (addendum3 ma floater face centres / control vertices)."""
    def __init__(self, C, r=.5): self.C = np.asarray(C, 'f8'); self.r = r; self.tree = cKDTree(self.C); self.vset = np.zeros(0, 'i8')
    def member(self, X):
        d, j = self.tree.query(np.asarray(X, 'f8'), distance_upper_bound=self.r); m = np.isfinite(d); return m, np.where(m, d, np.nan), np.where(m, j, -1)
    def offsets(self, X):
        d, j = self.tree.query(np.asarray(X, 'f8'), distance_upper_bound=50.); return np.where(np.isfinite(d), d, np.nan), np.zeros(len(d)), j

STAGE_IT = {'0': 0, '1000': 1000, '3000_pre_reset': 3000, '5000': 5000, '7000': 7000, '15000': 15000, '30000': 30000}
class PixG:
    """pixel-defined group (a5_pix.py group files): membership by uid in the group of the latest computed stage at or before the state.
    vset = the place patches (annex wrong / right patches, south wall / long wall column patches); dn = distance to the nearest of those target anchors."""
    def __init__(self, run, case, which):
        self.run, self.case, self.which = run, case, which; self.files = {}
        for st, it in STAGE_IT.items():
            p = A5O/'pix'/f'group_{run}_{case}_{st}.npz'
            if p.exists(): self.files[it] = p
        pl = {('annex', 'problem'): 'annex_wrong', ('annex', 'control'): 'annex_right', ('south', 'problem'): 'south_wall', ('south', 'control'): 'long_wall'}[(case, which)]
        pp = place_patches(pl) if pl.startswith('annex') else None
        if pp is not None: self.vset = pp['v']; A = pp['T'].anchor[pp['v']]; self.out = pp['out']
        else: P = place_points5(pl); self.vset = np.unique(P['v'][P['v'] >= 0]); A = P['anchor']; self.out = P['out']
        self.tree = cKDTree(np.asarray(A, 'f8'))
    def uids(self, it):
        ks = [k for k in self.files if k <= int(it)]
        if not ks: return None, None
        k = max(ks); z = loadz(self.files[k], [f'{self.which}__uid']); return z[f'{self.which}__uid'], k
    def member_state(self, S, it):
        u, k = self.uids(it)
        if u is None: return np.zeros(len(S['uid']), bool), np.full(len(S['uid']), np.nan), k
        m = np.isin(S['uid'], u); d, j = self.tree.query(np.asarray(S['xyz'], 'f8')); self.last_j = j; return m, d, k

def groups_for(place, control, run):
    """problem / control group objects of a place (addendum5.json places)."""
    if place in ('annex_under', 'south_wall_behind'):
        case = 'annex' if place == 'annex_under' else 'south'; return {'문제 무리': PixG(run, case, 'problem'), '대조 무리': PixG(run, case, 'control')}
    if place == 'floater': return {'문제 무리': Near(floater_centres('floater')), '대조 무리': Near(floater_centres('floater_control'))}
    return {'문제 무리': Band(place_points5(place)), '대조 무리': Band(place_points5(control))}

def member_of(B, S, it):
    """mask, distance-to-target, stage used (pixel groups) for a state dict with xyz / uid."""
    if isinstance(B, PixG): return B.member_state(S, it)
    m, dn, pj = B.member(np.asarray(S['xyz'], 'f8')); B.last_j = pj; return m, dn, None

def out_normal(B, idx):
    """outward normal used for the position component (Band: the place point's patch; PixG: the nearest place patch); None = no target plane (floater)."""
    if isinstance(B, Band): return B.P['out'][np.clip(idx, 0, None)]
    if isinstance(B, PixG): return B.out[np.clip(idx, 0, len(B.out)-1)]
    return None

def dist_seed(B, X):
    if isinstance(B, Band): return B.offsets(X)[0]
    if isinstance(B, PixG): return B.tree.query(np.asarray(X, 'f8'))[0]
    return B.offsets(X)[0]

# addendum-5 record runs (addendum5_b.json) and the addendum-3 annex record run, in the RUNS4 layout
for _site, _run, _stem in [('B173nb_b10', 'sc1_B173_ALS_signed', 'B173nb_b10__ALS'), ('R1rep_b10', 'sc2_R1_LoD2_signed', 'R1rep_b10__LoD2'),
                           ('B0_b10', 'sc3_B0_ALS_signed', 'B0_b10__ALS'), ('B0_b10', 'sc4_B0_LoD2_signed', 'B0_b10__LoD2')]:
    RUNS4[_run] = dict(stem=_stem, model=A5O/'runs'/_site/_run/'attempt1/model', kind='states', places=[], last='30000')
RUNS4.setdefault('ba3_B0_ALS_record', dict(stem='B0_b10__ALS', model=A3O/'runs/B0_b10/ba3_B0_ALS_record/attempt1/model', kind='states', places=[], last='30000'))
