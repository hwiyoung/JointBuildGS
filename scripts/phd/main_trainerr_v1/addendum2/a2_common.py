"""PHD-MAIN-TRAINERR-v1 addendum 2 helpers: locked config, folders, Gaussian snapshot fields (state, born kind, size), spot queries, column patches, patch case."""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1/addendum1')
from a1_common import *
from scipy.spatial import cKDTree
A2O = O/'addendum2'; A2D = D/'addendum2'
STATES = ['same_patch', 'other_patch', 'released', 'background']
STATE_KO = {'same_patch': '묶임(같은 패치)', 'other_patch': '묶임(다른 패치)', 'released': '풀림', 'background': '배경'}
BORN = ['patch_seed', 'patch_child', 'background_seed', 'background_child']
BORN_KO = {'patch_seed': '패치 씨앗', 'patch_child': '패치 자식', 'background_seed': '배경 씨앗', 'background_child': '배경 자식'}
JNAME = {0: '일치', 1: '보존', 2: '보정', 3: '빈 공간 보정', 4: '결측', 9: '셀 수 없음', -1: '패치 없음'}
CNAME = {-1: '없음', 0: '두 자료 모두 유효', 1: '사전정보 오류', 2: '영상 깊이 오류', 3: '둘 다 틀림', 4: '영상 깊이 결측'}
SCENES6 = ['B0_b10__ALS', 'B0_b10__LoD2', 'B173nb_b10__ALS', 'B173nb_b10__LoD2', 'R1rep_b10__ALS', 'R1rep_b10__LoD2']

def bcfg():
    p = R/'configs/phd/main_trainerr_v1/addendum2.json'; lock = json.loads(p.with_name('addendum2.lock.json').read_text())
    assert sha(p) == lock['config_sha256'], 'addendum2 config changed after lock'
    return json.loads(p.read_text())
def btable(name, rows): return table(name, rows, folder=A2D/'tables')
def bprogress(s):
    with (A2D/'progress.md').open('a') as f: f.write(f'- {now()}: {s}\n')
def bissue(s):
    with (A2D/'issues.md').open('a') as f: f.write(f'- {now()}: {s}\n')

def available(stem, arm):
    if arm == 'gt' and not (GT/'addendum12/distance_A1'/f'{stem}.npz').exists(): return False
    return True
def model_dir(stem, arm):
    site, prior = stem.split('__')
    if arm == 'own': return FT/'runs'/site/f'ft_{prior}_s0/attempt1/model'
    for a in ['attempt2', 'attempt1']:
        p = GT/'runs'/site/f'gt_{prior}_s0'/a/'model'
        if (p/'point_cloud/iteration_30000/point_cloud.ply').exists() and (p/'target_monitor/snapshot_30000.npz').exists(): return p
def targets_of(stem, arm): return (FT/'targets' if arm == 'own' else GT/'targets_gt')/f'{stem}.npz'
def maps_dir(stem, arm): return (FT if arm == 'own' else GT)/'stage1'/stem/'maps'

class Snap:
    """30000 snapshot: per-Gaussian bound patch (target row), state helpers, born kind, size; KD tree on opacity >= 0.1 centres."""
    def __init__(self, stem, arm, opacity_min=0.1):
        self.path = model_dir(stem, arm)/'target_monitor/snapshot_30000.npz'
        s = loadz(self.path, ['xyz', 'init_id', 'origin', 'opacity', 'scale', 'target_tag', 'target_index', 'patch_ids', 'patch_anchor', 'patch_normal', 'patch_sigma'])
        self.xyz = s['xyz'].astype('f8'); self.opacity = s['opacity']; self.tag = s['target_tag']; self.origin = s['origin']; self.size = s['scale'].max(1)
        ti = s['target_index']; bound = self.tag == 1; self.patch = np.full(len(ti), -1, 'i8'); self.patch[bound] = s['patch_ids'][ti[bound]]
        self.h = np.full(len(ti), np.nan); self.band = np.full(len(ti), np.nan)
        b = np.flatnonzero(bound); self.h[b] = ((s['xyz'][b].astype('f8')-s['patch_anchor'][ti[b]])*s['patch_normal'][ti[b]]).sum(1); self.band[b] = 1.96*s['patch_sigma'][ti[b]]
        ii = s['init_id']; dec = np.flatnonzero(np.diff(ii) <= 0); self.n_seed_rows = int(dec[0])+1 if len(dec) else len(ii)
        seed = np.arange(len(ii)) < self.n_seed_rows
        self.born = np.where(self.origin == 1, np.where(seed, 0, 1), np.where(seed, 2, 3)).astype('i1')
        self.vis = np.flatnonzero(self.opacity >= opacity_min); self.tree = cKDTree(self.xyz[self.vis])
    def state(self, g, col_patch):
        """state code per Gaussian g relative to the point's column patch: 0 same, 1 other, 2 released, 3 background."""
        t = self.tag[g]; return np.where(t == 1, np.where(self.patch[g] == col_patch, 0, 1), np.where(t == 2, 2, 3)).astype('i1')
    def spots(self, P, r=0.2):
        """list of Gaussian row arrays within r of each spot (opacity >= min)."""
        return [self.vis[np.asarray(q, 'i8')] for q in self.tree.query_ball_point(np.asarray(P, 'f8'), r, workers=8)]

def spot_values(S, spots, col_patch):
    """per-spot summary over its Gaussians: counts and opacity sums per state, born counts, opacity max/sum, size median, bound |h| and band (median over bound)."""
    n = len(spots); out = {f'n_{k}': np.zeros(n, 'i4') for k in STATES}
    out.update({f'op_{k}': np.zeros(n, 'f4') for k in STATES}); out.update({f'born_{k}': np.zeros(n, 'i4') for k in BORN})
    out.update(n_all=np.zeros(n, 'i4'), op_max=np.full(n, np.nan, 'f4'), op_sum=np.zeros(n, 'f4'), size_median=np.full(n, np.nan, 'f4'), bound_abs_h_median=np.full(n, np.nan, 'f4'), bound_band_median=np.full(n, np.nan, 'f4'))
    lens = np.array([len(g) for g in spots]); flat = np.concatenate(spots) if n and lens.sum() else np.zeros(0, 'i8'); owner = np.repeat(np.arange(n), lens)
    if len(flat):
        st = S.state(flat, np.asarray(col_patch)[owner]); op = S.opacity[flat]
        for k, nm in enumerate(STATES): m = st == k; out[f'n_{nm}'] = np.bincount(owner[m], minlength=n).astype('i4'); out[f'op_{nm}'] = np.bincount(owner[m], weights=op[m], minlength=n).astype('f4')
        for k, nm in enumerate(BORN): m = S.born[flat] == k; out[f'born_{nm}'] = np.bincount(owner[m], minlength=n).astype('i4')
        out['n_all'] = lens.astype('i4'); out['op_sum'] = np.bincount(owner, weights=op, minlength=n).astype('f4')
        o = np.argsort(owner, kind='stable'); b = np.searchsorted(owner[o], np.arange(n+1))
        for i in np.flatnonzero(lens):
            g = flat[o[b[i]:b[i+1]]]; out['op_max'][i] = S.opacity[g].max(); out['size_median'][i] = np.median(S.size[g]); bb = S.tag[g] == 1
            if bb.any(): out['bound_abs_h_median'][i] = np.median(np.abs(S.h[g[bb]])); out['bound_band_median'][i] = np.median(S.band[g[bb]])
    return out, flat, owner

def valid_rows(stem, arm):
    return np.flatnonzero(valid_patch(loadz(targets_of(stem, arm), ['target', 'normal', 'sigma', 'region'])))
def gt_row_patch(stem):
    """GT rows -> column patch target row (no validity filter)."""
    rows = loadz(GT/'scenes'/stem/'rows.npz', ['row_owner']); core = loadz(JA/'core_points'/f'{stem}.npz', ['source_index']); ro = rows['row_owner']
    return np.where(ro >= 0, core['source_index'][np.clip(ro, 0, None)], -1)
def result_patch(stem, arm, xyz, point_id, tag):
    """result samples -> column patch target row (no validity filter); A1 from the stored GTJUDGE owner, others s0_sets.columns (cache in addendum2/columns)."""
    from s0_sets import columns
    core = loadz(JA/'core_points'/f'{stem}.npz')
    if arm == 'gt': own = loadz(GT/'scenes'/stem/'distances/A1_samples.npz', ['owner'])['owner'][point_id]
    else: own, _ = columns(np.asarray(xyz, 'f8'), core, A2O/'columns'/f'{tag}_{stem}_{arm}')
    return np.where(own >= 0, core['source_index'][np.clip(own, 0, None)], -1)
def patch_case(stem, npatch):
    """modal stage1 case of the patch's GT rows (ties smaller case; addendum1 rule); -1 none."""
    cells = loadz(GT/'scenes'/stem/'stage1_cells.npz', ['case_id']); rp = gt_row_patch(stem); pc = np.full(npatch, -1, 'i1'); k = rp >= 0
    key = rp[k]*10+cells['case_id'][k].astype(int); u, cc = np.unique(key, return_counts=True); pq = u//10; cs = u % 10; o = np.lexsort((cs, -cc, pq)); f = np.r_[True, pq[o][1:] != pq[o][:-1]]
    pc[pq[o][f]] = cs[o][f]; return pc
def wall_zone_patches(stem, arm):
    """addendum1 4.4: valid patches whose target centre lies in the zone with |d| <= 1 m -> dict south/long -> target rows."""
    c = acfg(); t = loadz(targets_of(stem, arm), ['target', 'normal', 'sigma', 'region']); vp = np.flatnonzero(valid_patch(t)); out = {}
    for which in ['south', 'long']:
        a_, d_, _ = wall_coords(t['target'][vp], which); pl = c['places']['south_wall' if which == 'south' else 'long_wall']
        m = (a_ >= pl['along_m'][0]) & (a_ <= pl['along_m'][1]) & (t['target'][vp, 2] >= pl['z_m'][0]) & (t['target'][vp, 2] <= pl['z_m'][1]) & (np.abs(d_) <= 1.)
        out[which] = vp[m]
    return out
def qs(v, q=(10, 25, 50, 75, 90)):
    v = np.asarray(v, float); v = v[np.isfinite(v)]
    return {f'p{k}': (float(np.percentile(v, k)) if len(v) else None) for k in q}
def med(v):
    v = np.asarray(v, float); v = v[np.isfinite(v)]; return float(np.median(v)) if len(v) else None
def pct(m): m = np.asarray(m); return 100*float(m.mean()) if len(m) else None
