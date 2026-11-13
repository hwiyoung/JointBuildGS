"""Work ga (order 2): Gaussian tracking per saved state of the record runs (addendum3.json work_ga, common).
  run <run>  : every saved state -> addendum3/ga/<run>.npz (per place x state values) + section slabs at the strip times (addendum3/ga/<run>_strips.npz)
  tables     : tables/ga_values.csv (place x state), ga_events.csv, ga_largest_drop.csv
  figures    : figures/ga_curve_<place>.png, ga_strip_<place>.png (+ json sources)"""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1/addendum3')
from a3_common import *
import time
GA = A3O/'ga'

def section_frame(P):
    """origin = densest place point (most neighbours within 1 m); h axis = place out (walls) or the minor XY principal axis near the origin; slab normal = up x h."""
    tr = cKDTree(P['xyz']); cnt = np.array([len(q) for q in tr.query_ball_point(P['xyz'], 1.)]); o = P['xyz'][int(np.argmax(cnt))]
    near = P['xyz'][np.linalg.norm(P['xyz'][:, :2]-o[:2], axis=1) <= 3.]; wall = np.mean(np.abs(P['out'][:, 2]) < .5) >= .5
    if P['u'] is not None: h = np.asarray(P['u'], 'f8')
    elif wall: h = P['out'][np.abs(P['out'][:, 2]) < .5].mean(0); h[2] = 0
    else:
        q = near[:, :2]-near[:, :2].mean(0); w, V = np.linalg.eigh(q.T@q if len(q) > 2 else np.eye(2)); h = np.r_[V[:, 0], 0.]
    h = h/np.linalg.norm(h); e = np.cross([0, 0, 1.], h); e /= np.linalg.norm(e)
    return dict(origin=o, h=h, e=e, wall=bool(wall))

def match(P, X):
    """per Gaussian centre X: nearest place point in tangent distance among 16 nearest; returns j (-1 none), s (signed offset to its column-patch plane)."""
    j = np.full(len(X), -1, 'i8'); s = np.full(len(X), np.nan)
    if not len(X): return j, s
    k = min(16, len(P['xyz'])); d, jj = cKDTree(P['xyz']).query(X, k=k, distance_upper_bound=3.2)
    if k == 1: d, jj = d[:, None], jj[:, None]
    ok = jj < len(P['xyz']); jc = np.where(ok, jj, 0); diff = X[:, None, :]-P['xyz'][jc]; n = P['out'][jc]
    sn = (diff*n).sum(-1); tang = np.linalg.norm(diff-sn[..., None]*n, axis=-1); tang[~ok] = np.inf
    b = np.argmin(tang, 1); tb = tang[np.arange(len(X)), b]; good = tb <= .5; jb = jc[np.arange(len(X)), b]
    j[good] = jb[good]; s[good] = ((X[good]-P['anchor'][jb[good]])*P['out'][jb[good]]).sum(1); return j, s

def state_of(S, g, v_col):
    t = S['tag'][g]; return np.where(t == 1, np.where(S['tidx'][g] == v_col, 0, 1), np.where(t == 2, 2, 3)).astype('i1')

def values(P, S, cull):
    Sp = np.unique(P['v'][P['v'] >= 0]); out = {}
    b = (S['tag'] == 1) & np.isin(S['tidx'], Sp); op = S['opacity'][b]; out['bound_n'] = int(b.sum()); out['bound_per_m2'] = out['bound_n']/P['area_m2']
    out['bound_op_median'] = float(np.median(op)) if len(op) else None; out['bound_op_ge05_pct'] = 100*float((op >= .5).mean()) if len(op) else None
    out['bound_op_lt_cull_pct'] = 100*float((op < cull).mean()) if len(op) else None; out['bound_op_sum'] = float(op.sum())
    lo = P['xyz'].min(0)-3.6; hi = P['xyz'].max(0)+3.6; cand = np.flatnonzero(np.all((S['xyz'] >= lo) & (S['xyz'] <= hi), 1))
    j, s = match(P, S['xyz'][cand]); m = j >= 0; g = cand[m]; s = s[m]; st = state_of(S, g, P['v'][j[m]]); opg = S['opacity'][g]
    for side, sel in [('front', (s > .2) & (s <= 3.)), ('back', (s >= -3.) & (s < -.2))]:
        for k, nm in enumerate(STATE_NAMES):
            q = sel & (st == k); out[f'{side}_n_{nm}'] = int(q.sum()); out[f'{side}_op_{nm}'] = float(opg[q].sum())
        out[f'{side}_n'] = int(sel.sum()); out[f'{side}_op'] = float(opg[sel].sum())
    return out, Sp

def events_between(E, Sp, seq0, seq1):
    out = {}
    d = E['delete']; m = (d['seq'] > seq0) & (d['seq'] <= seq1) & (d['tag'] == 1) & np.isin(d['target_index'], Sp)
    for r, nm in REASON_NAMES.items(): out[f'deleted_{nm}'] = int((m & (d['reason'] == r)).sum())
    out['deleted'] = int(m.sum())
    r_ = E['release']; out['released'] = int(((r_['seq'] > seq0) & (r_['seq'] <= seq1) & np.isin(r_['previous_target_index'], Sp)).sum()) if len(r_) else 0
    t = E['retarget']
    if len(t):
        w = (t['seq'] > seq0) & (t['seq'] <= seq1); a = np.isin(t['old'], Sp); b = np.isin(t['new'], Sp)
        out['retarget_out'] = int((w & a & ~b).sum()); out['retarget_in'] = int((w & ~a & b).sum()); out['retarget_within'] = int((w & a & b).sum())
    else: out['retarget_out'] = out['retarget_in'] = out['retarget_within'] = 0
    return out
REASON_NAMES = {1: 'opacity', 2: 'world_size', 3: 'screen_size', 4: 'other', 5: 'split_parent'}

def completeness(run, P, name):
    """share of place points within tau on the mesh of that state, or None."""
    info = RUNS[run]
    if 'short' in info:   # work ba runs: meshes ba<k>_<name> in the addendum3 shadow
        f = A3O/'gtj/scenes/B0_b10__LoD2/distances'/f"{info['short']}_{name}.npz"
        if not f.exists(): return None, None
        rs = loadz(f, ['row_s'])['row_s']; tau = loadz(GT/'scenes/B0_b10__LoD2/rows.npz', ['row_tau_m'])['row_tau_m']; v = rs[P['point_id']]
        return 100*float((np.isfinite(v) & (np.abs(v) <= tau[P['point_id']])).mean()), str(f)
    if run == 'tl_B0_b10_LoD2_s0':
        for root in [A3O/'gtj', TLC/'gtj']:
            f = root/'scenes/B0_b10__LoD2/distances'/f'tl_{name}.npz'
            if f.exists():
                rs = loadz(f, ['row_s'])['row_s']; tau = loadz(GT/'scenes/B0_b10__LoD2/rows.npz', ['row_tau_m'])['row_tau_m']; v = rs[P['point_id']]
                return 100*float((np.isfinite(v) & (np.abs(v) <= tau[P['point_id']])).mean()), str(f)
        return None, None
    tag = 'tl_B0_LoD2_own' if run == 'tl_B0_LoD2_own' else 'tl_R1_ALS_own'; f = O/'curves'/f'{tag}__{name}.npz'
    if f.exists():
        sv = loadz(f, [f"{P['cell']}_{P['set']}_s"])[f"{P['cell']}_{P['set']}_s"][P['set_index']]; return 100*float((np.isfinite(sv) & (np.abs(sv) <= P['tau'])).mean()), str(f)
    if name == '30000':
        f = O/'meshes'/f"{info['stem']}__tl_own_30000/points.npz"; w = loadz(f, ['reference__within_tau1'])['reference__within_tau1']
        if P['cell']: return 100*float(w[P['point_id']].astype(bool).mean()), str(f)
    return None, None

def mesh_of(run, name):
    if 'short' in RUNS[run]:
        f = A3O/'gtj/meshes'/f"B0_b10__LoD2__{RUNS[run]['short']}_{name}/final.ply"; return f if f.exists() else None
    if run == 'tl_B0_b10_LoD2_s0':
        for root in [A3O/'gtj', TLC/'gtj']:
            f = root/'meshes'/f'B0_b10__LoD2__tl_{name}/final.ply'
            if f.exists(): return f
        return None
    stem = RUNS[run]['stem']; f = O/'gtj/meshes'/f'{stem}__tl_own_{name}/final.ply'; return f if f.exists() else None

def load_mesh(path):
    m = o3d.io.read_triangle_mesh(str(path)); V = np.asarray(m.vertices); T = np.asarray(m.triangles); del m; return V, T

def mesh_section(VT, F_, win):
    """triangle-plane intersection segments of the slab centre plane (x - o).e = 0 inside the window, in (h, z) coordinates."""
    V, T = VT
    o, h, e = F_['origin'], F_['h'], F_['e']; d = (V-o)@e; hh = (V-o)@h; zz = V[:, 2]
    dv = d[T]; cross = (dv.min(1) < 0) & (dv.max(1) > 0)   # every triangle crossing the plane (no vertex-distance prefilter: large faces)
    hv, zv = hh[T], zz[T]; cross &= (hv.max(1) >= win[0]-1) & (hv.min(1) <= win[1]+1) & (zv.max(1) >= win[2]-1) & (zv.min(1) <= win[3]+1)
    T = T[cross]; dv = dv[cross]; segs = []
    if not len(T): return np.zeros((0, 2, 2))
    for a, b in [(0, 1), (1, 2), (2, 0)]:
        da, db = dv[:, a], dv[:, b]; c = (da*db) < 0; t = np.where(c, da/(da-db+1e-30), np.nan)
        P = V[T[:, a]]+(V[T[:, b]]-V[T[:, a]])*t[:, None]; segs.append(np.where(c[:, None], np.c_[(P-o)@h, P[:, 2]], np.nan))
    S = np.stack(segs, 1); out = []
    for row in S:
        q = row[np.isfinite(row[:, 0])]
        if len(q) >= 2: out.append(q[:2])
    return np.asarray(out) if out else np.zeros((0, 2, 2))

def disc_section(T, F_, win):
    """chords of the target discs (anchor, normal, radius sqrt(area/pi); the discs the target maps are drawn from) cut by the slab centre plane, (h, z)."""
    o, h, e = F_['origin'], F_['h'], F_['e']; c = T.anchor; n = T.normal; r = T.radius
    dc = (c-o)@e; hh = (c-o)@h; k = (np.abs(dc) <= r) & (hh >= win[0]-r) & (hh <= win[1]+r) & (c[:, 2] >= win[2]-r) & (c[:, 2] <= win[3]+r)
    c, n, r, dc = c[k], n[k], r[k], dc[k]; en = n@e; w = e[None]-en[:, None]*n; ww = np.einsum('ij,ij->i', w, w); ok = ww > 1e-9
    c, n, r, dc, w, ww = c[ok], n[ok], r[ok], dc[ok], w[ok], ww[ok]; p0 = c-(dc/ww)[:, None]*w; u = np.cross(n, e[None]); u /= np.linalg.norm(u, axis=1)[:, None]
    hl2 = r**2-((p0-c)**2).sum(1); m = hl2 > 0; hl = np.sqrt(hl2[m]); a = p0[m]-hl[:, None]*u[m]; b = p0[m]+hl[:, None]*u[m]
    return np.stack([np.c_[(a-o)@h, a[:, 2]], np.c_[(b-o)@h, b[:, 2]]], 1)

def run(run_name):
    c = ccfg(); info = RUNS[run_name]; model = info['model']; GA.mkdir(parents=True, exist_ok=True); t0 = time.monotonic(); cull = .05
    places = {p: place_points(p) for p in info['places']}
    for p, P in places.items():
        print('PLACE', p, len(P['xyz']), 'area', P['area_m2'], 'no patch', int((P['v'] < 0).sum()), 'rules', dict(zip(*np.unique(P['rule'], return_counts=True))), flush=True)
    E = load_events(model); sv = saves(model); rows = []; strips = {}; frames = {p: section_frame(P) for p, P in places.items()}
    strip_times = c['work_ga']['strip_times']; ref = a11_ref(info['stem']); refx = ref['xyz'].astype('f8')
    tmesh = 'target discs of the FINALTRAIN targets (anchor, normal, sqrt(area/pi))'; TT = Targets(info['stem']); tseg = {}
    for p, P in places.items():
        Fr = frames[p]; hv = (P['xyz']-Fr['origin'])@Fr['h']; win = [min(hv.min(), 0)-4, max(hv.max(), 0)+4, P['xyz'][:, 2].min()-3, P['xyz'][:, 2].max()+3]; Fr['win'] = win
        tseg[p] = disc_section(TT, Fr, win)
        g = refx[(np.abs((refx-Fr['origin'])@Fr['e']) <= .25)]; gh = (g-Fr['origin'])@Fr['h']; k = (gh >= win[0]) & (gh <= win[1]) & (g[:, 2] >= win[2]) & (g[:, 2] <= win[3]); Fr['gt'] = np.c_[gh[k], g[k, 2]]
    prev = None
    for k_, s in enumerate(sv):
        name = s['name']; S = load_state(model, name, info['kind']); mesh = mesh_of(run_name, name) if name in strip_times else None; mVT = load_mesh(mesh) if mesh is not None else None
        for p, P in places.items():
            v, Sp = values(P, S, cull); ev = events_between(E, Sp, prev['seq'], s['seq']) if prev else {}
            if prev: ev['born'] = int(((S['tag'] == 1) & np.isin(S['tidx'], Sp) & (S['born_at'] > prev['iteration']) & (S['born_at'] <= s['iteration'])).sum())
            comp, src = completeness(run_name, P, name)
            rows.append(dict(run=run_name, place=p, name=name, iteration=s['iteration'], pre_reset=name.endswith('pre_reset'), seq=s['seq'], counted_from=info['kind'], **v, **ev,
                             completeness_pct=comp, completeness_source=src, gt_points=len(P['xyz']), area_m2=P['area_m2']))
            if name in strip_times:
                Fr = frames[p]; win = Fr['win']; x = S['xyz']; d = (x-Fr['origin'])@Fr['e']; hh = (x-Fr['origin'])@Fr['h']
                q = np.flatnonzero((np.abs(d) <= .25) & (hh >= win[0]) & (hh <= win[1]) & (x[:, 2] >= win[2]) & (x[:, 2] <= win[3]))
                tg = S['tag'][q]; st = np.where(tg == 1, np.where(np.isin(S['tidx'][q], Sp), 0, 1), np.where(tg == 2, 2, 3)).astype('i1')
                strips[f'{p}__{name}__g'] = np.c_[hh[q], x[q, 2], S['opacity'][q], st].astype('f4')
                if mVT is not None: strips[f'{p}__{name}__mesh'] = mesh_section(mVT, Fr, win).astype('f4'); strips[f'{p}__{name}__mesh_path'] = np.array(str(mesh))
        prev = s; print('STATE', run_name, name, len(S['xyz']), round(time.monotonic()-t0), flush=True); del S, mVT
    for p in places:
        Fr = frames[p]; strips[f'{p}__frame'] = np.r_[Fr['origin'], Fr['h'], Fr['e'], Fr['win']].astype('f8'); strips[f'{p}__gt'] = Fr['gt'].astype('f4'); strips[f'{p}__target'] = tseg[p].astype('f4')
    savez(GA/f'{run_name}_strips.npz', **strips)
    keys = list(dict.fromkeys(k for r in rows for k in r)); dump(GA/f'{run_name}.json', dict(at=now(), run=run_name, rows=rows, seconds=time.monotonic()-t0, target_mesh=str(tmesh), scientific_verdict=None))
    savez(GA/f'{run_name}.npz', **{k: np.array([r.get(k) if r.get(k) is not None else np.nan for r in rows]) if not isinstance(rows[0].get(k, 0), str) else np.array([str(r.get(k)) for r in rows]) for k in keys})
    print('GA_DONE', run_name, len(rows), round(time.monotonic()-t0), flush=True)

if __name__ == '__main__':
    a = sys.argv[1:]
    if a[0] == 'run': run(a[1])
    else: raise SystemExit(a)
