"""Order 5 (simulation, CPU): fill target discs where the 30,000 model has no Gaussian and see what is gained and lost. usage: tp10_fill.py <stem>
No GT in the fill rules. Patches = FINALTRAIN target rows with a surface (surface_exists, finite target); patch point = target position.
  near   : a Gaussian with opacity >= 0.1 within 0.2 m of the patch point (30,000 ply)
  drawn  : per training view whose frame holds the patch point (z > 0.2): NOT (rendered mean depth < z - 1.96 sigma or accumulated opacity < 0.5
           or no splat). Rendered by the CPU copy of the 2DGS compositing (tp4_contrib.contrib).
  채움 1 = no near and drawn in 0 views; 채움 2 = no near; 채움 3 = no near and drawn in fewer than 3 views.
Filled surface = the target disc (radius sqrt(area/pi), plane = target normal) as a 16-gon. Simplification (issues.md): the disc is added to the
extraction directly instead of passing through the judgment-mesh render + TSDF path.
Scoring = the GTJUDGE rules: rows by normal_line.measure (5 rays x 2 signs, limit 10 m / walls 5 m) on the disc mesh, combined with the stored
row distance of the extraction by the nearer crossing; result samples = 400 per m2 on the discs (seeded), kept inside the stage-1 grid cells,
normal oriented to the nearest GT normal (ALS: upward), cylinder distance (GTJUDGE cylinder.cpp, reference radius, 10 m / walls 5 m),
eligible = nearest GT point <= 1 m and (LoD2 or |nz| >= 0.5). Extractions: base (addendum11 FINALTRAIN_30000) and occlusion-excluded
(TRAINERR addendum6 ra6_ft_occl_10). Writes /tp/fill/<stem>.npz/json."""
import sys, ctypes, subprocess
sys.path.insert(0, '/repo/scripts/phd/main_targetpath_v1'); sys.path.insert(0, '/repo/scripts/phd/main_gtjudge_v1'); sys.path.insert(0, '/repo')
from tp_common import *
import tp4_contrib as T4
from normal_line import measure
from src.phd.metrics_v3.surface import MeshScene
from scipy.spatial import cKDTree
from concurrent.futures import ProcessPoolExecutor
H, W = 741, 1024
S1 = PH/'main_stage1_v1/PHD-MAIN-STAGE1-v1'
VAR = ['채움 1', '채움 2', '채움 3']

class Cyl:   # GTJUDGE cylinder.py with the library built into this task's folder
    def __init__(self, points):
        src = R/'scripts/phd/main_gtjudge_v1/cylinder.cpp'; lib = O/'bin'/f'cylinder_{sha(src)[:12]}.so'; lib.parent.mkdir(exist_ok=True)
        if not lib.exists(): subprocess.run(['g++', '-O3', '-std=c++17', '-fopenmp', '-shared', '-fPIC', str(src), '-o', str(lib)], check=True)
        self.p = np.ascontiguousarray(points, 'f8'); self.lib = ctypes.CDLL(str(lib)); self.lib.build.argtypes = [ctypes.c_void_p, ctypes.c_int]; self.lib.build.restype = ctypes.c_void_p
        self.lib.query.argtypes = [ctypes.c_void_p]*4+[ctypes.c_int, ctypes.c_double, ctypes.c_void_p, ctypes.c_void_p]; self.t = self.lib.build(self.p.ctypes.data, len(self.p))
    def query(self, P, N, L, r):
        P = np.ascontiguousarray(P, 'f8'); N = np.ascontiguousarray(N, 'f8'); L = np.ascontiguousarray(L, 'f8'); out = np.full(len(P), np.nan); idx = np.full(len(P), -1, 'i4')
        self.lib.query(self.t, P.ctypes.data, N.ctypes.data, L.ctypes.data, len(P), r, out.ctypes.data, idx.ctypes.data); return out, idx

def in_cells(site, P):   # GTJUDGE geometry_add1.Grid
    b = loadz(S1/'defs'/site/'bsurf.npz'); x = np.floor((P[:, 0]+690953-float(b['e0']))/float(b['res'])).astype('i8'); y = np.floor((P[:, 1]+5336071-float(b['n0']))/float(b['res'])).astype('i8')
    return np.isin(y*int(b['nx'])+x, b['keys'])

def discs(C, Nn, rad, k=16):
    a = np.cross(Nn, np.eye(3)[np.argmin(np.abs(Nn), 1)]); a /= np.linalg.norm(a, axis=1, keepdims=True); b = np.cross(Nn, a)
    th = 2*np.pi*np.arange(k)/k; ring = C[:, None]+rad[:, None, None]*(np.cos(th)[None, :, None]*a[:, None]+np.sin(th)[None, :, None]*b[:, None])
    V = np.concatenate([C[:, None], ring], 1).reshape(-1, 3); base = (np.arange(len(C))*(k+1))[:, None]
    F = np.stack([np.broadcast_to(base, (len(C), k)), base+1+np.arange(k), base+1+(np.arange(k)+1) % k], -1).reshape(-1, 3)
    return V, F

def sample_discs(C, Nn, rad, rng):
    n = np.maximum(1, np.round(np.pi*rad**2*400).astype(int)); owner = np.repeat(np.arange(len(C)), n)
    a = np.cross(Nn, np.eye(3)[np.argmin(np.abs(Nn), 1)]); a /= np.linalg.norm(a, axis=1, keepdims=True); b = np.cross(Nn, a)
    r = rad[owner]*np.sqrt(rng.random(len(owner))); t = 2*np.pi*rng.random(len(owner))
    return C[owner]+(r*np.cos(t))[:, None]*a[owner]+(r*np.sin(t))[:, None]*b[owner], Nn[owner], owner

def drawn_view(j):
    nm = T4.G['names'][j]; mm = T4.G['views'][nm]; K = np.asarray(mm['K']); M = np.asarray(mm['W2C'])
    u, v, z, okz = project(T4.G['X'], K, M); i = np.flatnonzero(okz & (u >= 0) & (u < W) & (v >= 0) & (v < H))
    if not len(i): return None
    px = np.floor(u[i]).astype('i8'); py = np.floor(v[i]).astype('i8'); C = T4.contrib(px, py, K, M); n = len(i)
    p = C[:, 0].astype('i8'); acc = np.bincount(p, C[:, 2], n); mean = np.where(acc > 0, np.bincount(p, C[:, 2]*C[:, 3], n)/np.maximum(acc, 1e-12), np.nan)
    sg = T4.G['sig'][i]; drawn = ~((~np.isfinite(mean)) | (mean < z[i]-1.96*sg) | (acc < .5))
    return i, drawn

def main(stem):
    t0 = time.monotonic(); site, prior = stem.split('__'); rng = np.random.default_rng(SEED+STEMS.index(stem))
    T = loadz(FT/'targets'/f'{stem}.npz', ['target', 'normal', 'area', 'target_sigma_m', 'surface_exists', 'judge_region'])
    valid = np.flatnonzero(T['surface_exists'] & np.isfinite(T['target']).all(1)); X = T['target'][valid]
    ply = ft_model(stem)/'point_cloud/iteration_30000/point_cloud.ply'
    g = ply_read(ply, ['x', 'y', 'z', 'scale_0', 'scale_1', 'rot_0', 'rot_1', 'rot_2', 'rot_3', 'opacity']); xyz = np.c_[g['x'], g['y'], g['z']].astype('f8'); op = 1/(1+np.exp(-g['opacity'].astype('f8')))
    d, _ = cKDTree(xyz[op >= .1]).query(X, distance_upper_bound=.2, workers=8); near = np.isfinite(d)
    cand = np.flatnonzero(~near); print('FILL_CAND', stem, len(valid), len(cand), round(time.monotonic()-t0), flush=True)
    # renderer state for tp4 contrib (box crop like the stored renders)
    box = view_box(site); inside = ((xyz >= box[0]) & (xyz <= box[1])).all(1); gid = np.flatnonzero(inside)
    s = np.exp(np.c_[g['scale_0'], g['scale_1']].astype('f8'))[gid]; R_ = T4.qrot(np.c_[g['rot_0'], g['rot_1'], g['rot_2'], g['rot_3']].astype('f8')[gid])
    T4.G.update(L=np.stack([R_[:, :, 0]*s[:, :1], R_[:, :, 1]*s[:, 1:2]], 1), xyz=xyz[gid], op=op[gid], gid=gid, X=X[cand], sig=T['target_sigma_m'][valid][cand].astype('f8'))
    idx = json.loads((maps_of(stem, 'ft')/'index.json').read_text()); T4.G['views'] = idx['views']; T4.G['names'] = list(idx['views']); del g, xyz
    nd = np.zeros(len(cand), 'i4'); nin = np.zeros(len(cand), 'i4')
    with ProcessPoolExecutor(int(os.environ.get('TP_WORKERS', 12))) as ex:
        for r in ex.map(drawn_view, range(len(T4.G['names'])), chunksize=1):
            if r is None: continue
            i, dr = r; np.add.at(nd, i, dr.astype('i4')); np.add.at(nin, i, 1)
    print('FILL_DRAWN', stem, round(time.monotonic()-t0), flush=True)
    crow = valid[cand]   # candidate positions in 'valid' -> target rows
    sel = {VAR[0]: crow[nd == 0], VAR[1]: crow, VAR[2]: crow[nd < 3]}
    # GT rows and reference
    A = gt_reference(stem); RX = A['reference__xyz'].astype('f8'); RN = A['reference__normal'].astype('f8'); wall = A['reference__wall'].astype(bool); tau = A['reference__tau_m'].astype('f8')
    el = A['reference__eligible'].astype(bool); case = A['reference__case_id']
    old = {'기준': A['reference__FINALTRAIN_30000__s_m'].astype('f8'), '가림 제외': loadz(TE/'addendum6/meshes'/f'{stem}__ra6_ft_occl_10/points.npz', ['reference__s_m'])['reference__s_m'].astype('f8')}
    res_old = {'기준': (A['result__FINALTRAIN_30000__eligible_new'].astype(bool), A['result__FINALTRAIN_30000__within_tau1'].astype(bool))}
    zo = loadz(TE/'addendum6/meshes'/f'{stem}__ra6_ft_occl_10/points.npz', ['result__eligible_new', 'result__within_tau1']); res_old['가림 제외'] = (zo['result__eligible_new'].astype(bool), zo['result__within_tau1'].astype(bool))
    ref = loadz(GJ/'reference'/site/'dense.npz'); cyl = Cyl(ref['xyz']); rtree = cKDTree(ref['xyz']); radius = float(ref['radius'])
    roof_tau, wall_tau = tau_of(site, prior)
    # fixed points (wrong-target point file, group 2) and their method patches; patch target right/wrong is judged from the disc samples (scoring only)
    Wp = loadz(WT/'points'/f'wt_{stem}.npz', ['group', 'case_id', 'method_target_ok', 'patch_row']); fixed_rows = set(Wp['patch_row'][(Wp['group'] == 2) & (Wp['case_id'] == 1) & ~Wp['method_target_ok']].tolist())
    rows, out = [], dict(valid=valid, near=near, cand_rows=crow, drawn_views=nd, frame_views=nin)
    for vn in VAR:
        p = sel[vn]; C = T['target'][p].astype('f8'); Nn = T['normal'][p].astype('f8'); rad = np.sqrt(T['area'][p]/np.pi)
        V, F = discs(C, Nn, rad); sc = MeshScene(V, F); snew, _ = measure(sc, RX, RN, wall)
        P_, N_, own = sample_discs(C, Nn, rad, rng); fin = np.isfinite(P_).all(1) & np.isfinite(N_).all(1); keep = fin.copy(); keep[fin] = in_cells(site, P_[fin]); nan_samples = int((~fin).sum()); P_, N_, own = P_[keep], N_[keep], own[keep]
        eu, ii = rtree.query(P_, workers=8); rn = ref['normal'][ii].astype('f8').copy()
        if prior == 'ALS': rn[rn[:, 2] < 0] *= -1
        N_ = N_*np.where((N_*rn).sum(1) < 0, -1., 1.)[:, None]; wl = ref['wall'][ii].astype(bool) if prior == 'LoD2' else np.zeros(len(P_), bool)
        elig = eu <= 1.; qs = np.full(len(P_), np.nan)
        if elig.any(): qs[elig], _ = cyl.query(P_[elig], N_[elig], np.where(wl[elig], 5., 10.), radius)
        qt = np.where(wl, wall_tau, roof_tau); swithin = np.isfinite(qs) & (np.abs(qs) <= qt); selig = elig & ((prior == 'LoD2') | (np.abs(N_[:, 2]) >= .5))
        np_ = len(p); pw = np.bincount(own, swithin & selig, np_); pe = np.bincount(own, selig, np_); wrong = (pe > 0) & (pw/np.maximum(pe, 1) < .5)
        has_fixed = np.isin(p, list(fixed_rows)) if fixed_rows else np.zeros(np_, bool)
        out[f'{vn}__patches'] = p; out[f'{vn}__wrong'] = wrong
        for ex, so in old.items():
            comb = np.where(np.isfinite(snew) & (~np.isfinite(so) | (np.abs(snew) < np.abs(so))), snew, so); wi = np.isfinite(comb) & (np.abs(comb) <= tau); w0 = np.isfinite(so) & (np.abs(so) <= tau)
            e0, r0 = res_old[ex]
            r = dict(title=TITLE, stem=STEM_KO[stem], extraction=ex, fill=vn, patches=np_, area_m2=float(T['area'][p].sum()),
                     completeness_before_pct=pct(w0[el]), completeness_after_pct=pct(wi[el]),
                     accuracy_before_pct=round(100*(e0 & r0).sum()/max(1, e0.sum()), 3), accuracy_after_pct=round(100*((e0 & r0).sum()+(selig & swithin).sum())/max(1, e0.sum()+selig.sum()), 3),
                     added_samples_eligible=int(selig.sum()), filled_area_within_tau_pct=pct(swithin[selig]) if selig.any() else None,
                     wrong_patches=int(wrong.sum()), wrong_area_m2=float(T['area'][p][wrong].sum()), wrong_with_fixed_points=int((wrong & has_fixed).sum()),
                     wrong_with_fixed_area_m2=float(T['area'][p][wrong & has_fixed].sum()), patches_with_fixed_points=int(has_fixed.sum()), samples_nan=nan_samples, samples_in_cells=int(keep.sum()), samples_drawn=int(len(keep)))
            for cid, nm in [(0, '둘 다 맞음'), (1, '사전 정보가 틀린 곳'), (2, '영상이 틀린 곳'), (4, '영상 없음'), (3, '둘 다 틀림')]:
                m = el & (case == cid); r[f'case_{nm}_rows'] = int(m.sum()); r[f'case_{nm}_before_pct'] = pct(w0[m]); r[f'case_{nm}_after_pct'] = pct(wi[m])
            jr = T['judge_region'][p]; ar = T['area'][p]
            for rg, nm in [(0, '일치'), (1, '보존'), (2, '보정'), (3, '보정(빈 공간)'), (4, '결측'), (9, '미판정')]: r[f'region_{nm}_area_pct'] = round(100*ar[jr == rg].sum()/max(ar.sum(), 1e-12), 2)
            fx = (Wp['group'] == 2) & (Wp['case_id'] == 1) & ~Wp['method_target_ok']
            r['fixed_points'] = int(fx.sum())
            rows.append(r); out[f'{vn}__{ex}__within'] = wi.astype('u1')
        print('FILL_VAR', stem, vn, np_, round(time.monotonic()-t0), flush=True)
    savez(O/'fill'/f'{stem}.npz', **out)
    dump(O/'fill'/f'{stem}.json', dict(at=now(), stem=stem, rows=rows, candidates=len(cand), valid=len(valid), seconds=time.monotonic()-t0, scientific_verdict=None))
    print('FILL_DONE', stem, round(time.monotonic()-t0), flush=True)

if __name__ == '__main__': main(sys.argv[1])
