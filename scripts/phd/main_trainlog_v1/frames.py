"""Order 5: per-state frames (result + all-Gaussians versions), panel crops, strip figure (CPU).
Layout from ref/trainlog_proto_v1.py, result panel first (5.1). Text = panel names, axes, legend, iteration only."""
import sys
from common import *
from tl_defs import Defs, TAU
from derive_states import scope_mask
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
from matplotlib.collections import EllipseCollection
from matplotlib.colors import to_rgb
from matplotlib.patches import Patch
from matplotlib.lines import Line2D
from scipy.spatial import cKDTree
P_ = '/fonts/NotoSansCJK-Regular.ttc'; fm.fontManager.addfont(P_); plt.rcParams['font.family'] = fm.FontProperties(fname=P_).get_name(); plt.rcParams['axes.unicode_minus'] = False
A = O/'analysis'; FR = O/'frames'; LT = np.array([-.35, -.45, .82]); LT /= np.linalg.norm(LT)
COL = {0: '#7FA7D9', 2: '#D85A30', 1: '#1D9E75', 4: '#E8B931'}; NEU = '#C9C7BE'; PINK = '#C2378A'; PALE = np.array(to_rgb('#EEECE6'))
GREY = np.array(to_rgb('#D3D1CA')); RED = np.array(to_rgb('#C0392B')); BLUE = np.array(to_rgb('#2E6DB4'))
HOLD = {0, 3000, 7000, 15000, 30000}

def saves(): return [json.loads(l) for l in (RUNM/'trainlog/saves.jsonl').read_text().splitlines()]
def state(name): return loadz(DER/'gaussians'/f'{name}.npz')
def qrot(q):
    w, x, y, z = q.T
    return np.stack([np.stack([1-2*(y*y+z*z), 2*(x*y+w*z), 2*(x*z-w*y)], 1), np.stack([2*(x*y-w*z), 1-2*(x*x+z*z), 2*(y*z+w*x)], 1), np.stack([2*(x*z+w*y), 2*(y*z-w*x), 1-2*(x*x+y*y)], 1)], 1)

class Ctx:
    def __init__(self):
        c = cfg(); self.c = c; self.key = c['key_iterations']; self.SV = saves(); self.names = [s['name'] for s in self.SV]; self.it = {s['name']: s['iteration'] for s in self.SV}
        self.d0 = state('0'); self.defs = Defs(self.d0); band = json.loads((A/'band.json').read_text()); self.b0 = band['b0']
        cam = json.loads((PF/'figures/proc_30000_1_a.json').read_text())['camera']; self.Bs = np.array(cam['basis']); self.ctr = np.array(cam['center'])
        ext = A/'extent.json'
        if not ext.exists():
            allp = np.concatenate([(state(n)['xyz']-self.ctr)@self.Bs[:2].T for n in self.names]); lo = np.percentile(allp, 1, 0)-1; hi = np.percentile(allp, 99, 0)+1
            dump(ext, dict(lo=lo.tolist(), hi=hi.tolist(), rule='all saved states, 1/99 percentile ±1 m (prototype 0.2/99.8 widened by floaters)', scientific_verdict=None))
        e = json.loads(ext.read_text()); self.lo = np.array(e['lo']); self.hi = np.array(e['hi'])
        self.curve = {r['state']: r for r in csv_rows(D/'tables/per_state_curve.csv')}
        self.scores = {}
        for k in self.key:
            p = O/'meshes'/f'tl_{k}'/'score.json'
            if p.exists(): self.scores[k] = {r['case_id']: r for r in json.loads(p.read_text())['rows']}
        self.pre_scores = {}
        for n in self.names:
            p = O/'meshes'/f'tl_{n}'/'score.json'
            if n.endswith('pre_reset') and p.exists(): self.pre_scores[n] = {r['case_id']: r for r in json.loads(p.read_text())['rows']}
        self.depth_err = json.loads((A/'depth_error.json').read_text())['states'] if (A/'depth_error.json').exists() else {}
        self.traj = json.loads((A/'trajectories.json').read_text())
        self.resets = sorted(set(int(x) for x in loadz(DER/'events/opacity_reset.npz')['iteration'])) if (DER/'events/opacity_reset.npz').exists() else []
        self.refs = dict(judgment=66.577, LGDM=(73.403, 78.109), GeoGS=(79.101, 49.293), original=(98.750, 72.524))

def csv_rows(p):
    import csv
    def num(v):
        if v in ('', 'None'): return None
        try: return float(v)
        except ValueError: return v
    return [{k: (v if k in ('state', 'drawing_rule') else num(v)) for k, v in r.items()} for r in csv.DictReader(open(p))]

# ---------------- precompute: meshes, lines, depth errors ----------------
def band_points(P, defs, b0):
    sd, u, v = defs.signed_points(P); m = (v >= b0) & (v < b0+1) & np.isfinite(sd); return u[m], sd[m]

def plane_section(V, Fc, defs, b0):
    """Exact cut of a triangle mesh by the vertical plane v = b0+0.5: one segment per crossing triangle -> (n,2,2) of (u, sd cm)."""
    vv = (V[:, :2]-defs.c2)@defs.a2-(b0+.5); s = np.sign(vv[Fc]); cross = (s.min(1) < 0) & (s.max(1) > 0); T = Fc[cross]; ends = []
    for a, b in [(0, 1), (1, 2), (2, 0)]:
        va, vb = vv[T[:, a]], vv[T[:, b]]; m = (va*vb) < 0; w = np.where(m, va/np.where(m, va-vb, 1), np.nan); ends.append(V[T[:, a]]+w[:, None]*(V[T[:, b]]-V[T[:, a]]))
    E = np.stack(ends, 1); ok = np.isfinite(E[:, :, 0]); keep = ok.sum(1) == 2; E = E[keep]; ok = ok[keep]
    P = np.stack([E[i][ok[i]] for i in range(len(E))]) if len(E) else np.zeros((0, 2, 3))
    if not len(P): return np.zeros((0, 2, 2))
    sd, u, _ = defs.signed_points(P.reshape(-1, 3)); seg = np.stack([u, sd], 1).reshape(-1, 2, 2); good = np.isfinite(seg).all((1, 2)); return seg[good]

def binned(u, sd, step=.1):
    if not len(u): return np.zeros(0), np.zeros(0)
    k = np.floor(u/step).astype(int); ks = np.unique(k); return (ks+.5)*step, np.array([np.median(sd[k == q]) for q in ks])

def prep_static(ctx):
    out = A/'static.npz'
    if out.exists(): return
    defs, b0 = ctx.defs, ctx.b0; z = loadz(S1/'defs'/SITE/'prior_ALS.npz', ['V', 'F']); pseg = plane_section(z['V'].astype(float), z['F'], defs, b0)
    rows = loadz(GT/'scenes'/STEM/'rows.npz', ['xyz']); gu, gs = band_points(rows['xyz'].astype(float), defs, b0)
    savez(out, prior_seg=pseg, gt_u=gu, gt_sd=gs); print('STATIC', len(pseg), len(gu), flush=True)

def prep_mesh(ctx, name, W=1200):
    out = A/f'mesh_{name}.npz'
    if out.exists(): return
    import open3d as o3d
    mesh = o3d.io.read_triangle_mesh(str(O/'gtj/meshes'/f'{STEM}__tl_{name}'/'final.ply')); V = np.asarray(mesh.vertices, float); Fc = np.asarray(mesh.triangles)
    cen = V[Fc].mean(1); keep = scope_mask(cen, ctx.c); Fc = Fc[keep]; used = np.unique(Fc); remap = np.full(len(V), -1); remap[used] = np.arange(len(used)); V = V[used]; Fc = remap[Fc]
    g = loadz(GT/'reference'/SITE/'dense.npz', ['xyz', 'normal']); gm = scope_mask(g['xyz'].astype(float), dict(scope=dict(ctx.c['scope'], z_min=ctx.c['scope']['z_min']-1, z_max=ctx.c['scope']['z_max']+1)))
    gx = g['xyz'][gm].astype(float); gn = g['normal'][gm].astype(float); gn[gn[:, 2] < 0] *= -1
    dist, idx = cKDTree(gx).query(V, workers=8); err = np.sign(((V-gx[idx])*gn[idx]).sum(1))*dist
    seg = plane_section(V, Fc, ctx.defs, ctx.b0)
    sc = o3d.t.geometry.RaycastingScene(); tm = o3d.t.geometry.TriangleMesh(); tm.vertex.positions = o3d.core.Tensor(V.astype('f4')); tm.triangle.indices = o3d.core.Tensor(Fc.astype('i4')); sc.add_triangles(tm)
    H = int(round(W*(ctx.hi[1]-ctx.lo[1])/(ctx.hi[0]-ctx.lo[0]))); xs = np.linspace(ctx.lo[0], ctx.hi[0], W); ys = np.linspace(ctx.hi[1], ctx.lo[1], H); X, Y = np.meshgrid(xs, ys)
    org = ctx.ctr+X[..., None]*ctx.Bs[0]+Y[..., None]*ctx.Bs[1]-400*ctx.Bs[2]; rays = np.concatenate([org, np.broadcast_to(ctx.Bs[2], org.shape)], -1).reshape(-1, 6).astype('f4')
    r = sc.cast_rays(o3d.core.Tensor(rays)); hit = np.isfinite(r['t_hit'].numpy()); pid = r['primitive_ids'].numpy(); nrm = r['primitive_normals'].numpy()
    fe = err[Fc].mean(1); e = np.where(hit, fe[pid.clip(0, len(fe)-1)], 0); a = np.clip((np.abs(e)-TAU/100)/(1-TAU/100), 0, 1)[:, None]
    col = np.where((np.abs(e) <= TAU/100)[:, None], GREY, np.where((e > 0)[:, None], GREY*(1-a)+RED*a, GREY*(1-a)+BLUE*a)); sh = .55+.45*np.abs(nrm@LT)
    img = np.where(hit[:, None], col*sh[:, None], 1.).reshape(H, W, 3)
    savez(out, image=(img*255).astype('u1'), section_seg=seg, vertex_error_m=err.astype('f4'), vertices=V.astype('f4'), faces=Fc.astype('i4'))
    dump(A/f'mesh_{name}.json', dict(name=name, faces_in_scope=int(len(Fc)), vertices=int(len(V)), vertex_error_abs_median_m=float(np.median(abs(err))), within_tau_fraction=float((abs(err) <= TAU/100).mean()),
         colour='|d|<=τ grey, >τ red (above), <-τ blue (below), saturates at ±1 m', sign='GT normal oriented nz>=0', scientific_verdict=None))
    print('MESHPREP', name, len(Fc), flush=True)

def prep_depth(ctx):
    """Depth error of the two training images vs GT (dense GT in scope, per-pixel nearest GT depth), and band lines."""
    out = A/'depth_error.json'; cams = json.loads((O/'renders/cameras.json').read_text())['training']
    g = loadz(GT/'reference'/SITE/'dense.npz', ['xyz']); gx = g['xyz'][scope_mask(g['xyz'].astype(float), ctx.c)].astype(float); zbuf = []
    for v in cams:
        E = np.asarray(v['W2C']); K = np.asarray(v['K']); q = gx@E[:3, :3].T+E[:3, 3]; f = q[:, 2] > 0; q = q[f]
        u = np.rint(K[0, 0]*q[:, 0]/q[:, 2]+K[0, 2]).astype(int); w = np.rint(K[1, 1]*q[:, 1]/q[:, 2]+K[1, 2]).astype(int); ok = (u >= 0) & (w >= 0) & (u < v['width']) & (w < v['height'])
        zb = np.full(v['height']*v['width'], np.inf); np.minimum.at(zb, w[ok]*v['width']+u[ok], q[ok, 2]); zbuf.append(zb.reshape(v['height'], v['width']))
    res = {}
    for name in ctx.names:
        p = O/'renders'/name/'data.npz'
        if not p.exists(): continue
        z = loadz(p, ['train1_depth', 'train1_alpha', 'train2_depth', 'train2_alpha']); r = {}; lu, ls = [], []
        for i, v in enumerate(cams):
            dep = z[f'train{i+1}_depth']; al = z[f'train{i+1}_alpha'].astype(float); m = np.isfinite(zbuf[i]) & (al > .5) & (dep > 0)
            r[f'train{i+1}_median_abs_cm'] = float(np.median(abs(dep[m]-zbuf[i][m]))*100) if m.any() else None
            E = np.asarray(v['W2C']); K = np.asarray(v['K']); yy, xx = np.nonzero((al > .5) & (dep > 0)); d = dep[yy, xx]
            Pc = np.c_[(xx-K[0, 2])*d/K[0, 0], (yy-K[1, 2])*d/K[1, 1], d]; Pw = (Pc-E[:3, 3])@E[:3, :3]
            vv = (Pw[:, :2]-ctx.defs.c2)@ctx.defs.a2; sel = (vv >= ctx.b0) & (vv < ctx.b0+1); u_, s_ = band_points(Pw[sel], ctx.defs, ctx.b0); lu.append(u_); ls.append(s_)
        bu, bs = binned(np.concatenate(lu), np.concatenate(ls)); savez(A/f'depthline_{name}.npz', u=bu, sd=bs)
        r['median_abs_cm'] = float(np.nanmean([r['train1_median_abs_cm'], r['train2_median_abs_cm']])) if None not in (r['train1_median_abs_cm'], r['train2_median_abs_cm']) else None; res[name] = r
    dump(out, dict(states=res, rule='per pixel nearest dense-GT depth in building scope (z-buffer of points), rendered surf_depth where alpha>0.5; median |Δ|; value = mean of the two images', scientific_verdict=None))

# ---------------- drawing ----------------
def drawing_uids(ctx, name):
    it = ctx.it[name]
    if ((it in ctx.key and not name.endswith('pre_reset')) or getattr(ctx, 'prefer_lineage', False)) and (O/'lineage'/f'{name}.npz').exists():
        z = loadz(O/'lineage'/f'{name}.npz'); return set(z['uid'][z['uid'] >= 0].tolist()), '계보(참값 행, 학습 영상 203장)'
    z = loadz(O/'renders'/name/'data.npz', ['train1_maxid_uid', 'train2_maxid_uid']); u = np.concatenate([z['train1_maxid_uid'].ravel(), z['train2_maxid_uid'].ravel()])
    return set(np.unique(u[u >= 0]).tolist()), '학습 영상 두 장 화소별 최대 α×T'

def mesh_for(ctx, name):
    it = ctx.it[name]
    if (A/f'mesh_{name}.npz').exists(): return it, loadz(A/f'mesh_{name}.npz', ['image', 'section_seg'])
    avail = [k for k in ctx.key if (k < it or (k == it and not name.endswith('pre_reset'))) and (A/f'mesh_{k}.npz').exists()]
    return (max(avail), loadz(A/f'mesh_{max(avail)}.npz', ['image', 'section_seg'])) if avail else (None, None)

def frame(ctx, name, mode='result', fig=None, axes=None, single=None):
    it = ctx.it[name]; d = state(name); defs = ctx.defs; draw, rule = drawing_uids(ctx, name); isd = np.isin(d['uid'], np.fromiter(draw, 'i8')) if draw else np.zeros(len(d['uid']), bool)
    mk, mz = mesh_for(ctx, name); st = loadz(A/'static.npz')
    own = fig is None
    if own:
        fig = plt.figure(figsize=(16, 9), dpi=120, facecolor='white')
        gs = fig.add_gridspec(3, 2, height_ratios=[1.45, 1.25, .85], width_ratios=[1.75, 1], hspace=.32, wspace=.10, left=.02, right=.95, top=.915, bottom=.075)
        gb = gs[2, :].subgridspec(1, 2, wspace=.22)
        axes = dict(surface=fig.add_subplot(gs[0, 0]), section=fig.add_subplot(gs[0, 1]), inner=fig.add_subplot(gs[1, 0]), traj=fig.add_subplot(gs[1, 1]), left=fig.add_subplot(gb[0]), right=fig.add_subplot(gb[1]))
        fig.text(.03, .96, f'B173 · 학습 {it:,}회'+(' (되돌림 직전)' if name.endswith('pre_reset') else ''), fontsize=20, fontweight='bold', color='#16263d', va='center')
        ax = fig.add_axes([.36, .948, .62, .022]); ax.barh(0, 30000, color='#E5E3DC', height=1); ax.barh(0, it, color='#5F5E5A', height=1); ax.set_xlim(0, 30000); ax.axis('off')
        for x in [0, 3000, 7000, 15000, 30000]: ax.plot([x, x], [-.5, .5], color='white', lw=1.5)
    ex = (ctx.lo[0], ctx.hi[0], ctx.lo[1], ctx.hi[1])
    if 'surface' in axes:
        A_ = axes['surface']
        if mz is not None: A_.imshow(mz['image'], extent=ex, interpolation='bilinear')
        A_.set_xlim(ex[0], ex[1]); A_.set_ylim(ex[2], ex[3]); A_.set_aspect('equal'); A_.axis('off')
        A_.set_title('표면 · 메시'+(f': {mk:,}회' if mk is not None and mk != it else ('' if mk is not None else ': 없음')), fontsize=13, loc='left', color='#2e3a48')
        A_.plot([ex[0]+1, ex[0]+6], [ex[2]+1, ex[2]+1], color='#2e3a48', lw=2); A_.text(ex[0]+3.5, ex[2]+1.6, '5 m', ha='center', fontsize=10, color='#2e3a48')
    if 'inner' in axes:
        A_ = axes['inner']; xyz = d['xyz'].astype(float); R_ = qrot(d['rotation']/np.linalg.norm(d['rotation'], axis=1, keepdims=True)); sc = d['scale']*.6
        t1 = R_[:, :, 0]*sc[:, :1]; t2 = R_[:, :, 1]*sc[:, 1:2]; M = np.stack([np.stack([t1@ctx.Bs[0], t2@ctx.Bs[0]], 1), np.stack([t1@ctx.Bs[1], t2@ctx.Bs[1]], 1)], 1)
        U, s, _ = np.linalg.svd(M); ang = np.degrees(np.arctan2(U[:, 1, 0], U[:, 0, 0])); p = (xyz-ctx.ctr)@ctx.Bs.T; order = np.argsort(-p[:, 2])
        bound = d['target_tag'] == 1; j = defs.placed(d); base = np.array([to_rgb(COL.get(int(x), NEU)) for x in j]); wrong = d['group33'] == 1; base[wrong] = to_rgb(PINK)
        base[~bound & ~wrong] = base[~bound & ~wrong]*.45+PALE*.55; shd = .55+.45*np.abs(d['normal']@LT); rgb = np.clip(base*shd[:, None], 0, 1)
        al = .25+.75*d['opacity'].astype(float); al = al if mode == 'all' else np.where(isd, al, .06)
        A_.add_collection(EllipseCollection(2*s[order, 0], 2*s[order, 1], ang[order], units='xy', offsets=p[order, :2], offset_transform=A_.transData, facecolors=np.c_[rgb[order], al[order]], edgecolors='none'))
        A_.set_xlim(ex[0], ex[1]); A_.set_ylim(ex[2], ex[3]); A_.set_aspect('equal'); A_.axis('off'); A_.set_title('속 · 가우시안 원반'+(' (모두)' if mode == 'all' else ''), fontsize=13, loc='left', color='#2e3a48')
        A_.plot([ex[0]+1, ex[0]+6], [ex[2]+1, ex[2]+1], color='#2e3a48', lw=2); A_.text(ex[0]+3.5, ex[2]+1.6, '5 m', ha='center', fontsize=10, color='#2e3a48')
    if 'section' in axes:
        B = axes['section']; q = defs.section(d); sm = (q['v'] >= ctx.b0) & (q['v'] < ctx.b0+1); dr = isd[q['index']]; wr = (d['group33'] == 1)[q['index']]; clip = lambda v: np.clip(v, -60, 40)
        B.axhspan(-defs.hw, defs.hw, color='#D85A30', alpha=.10, lw=0); B.axhline(0, color='#D85A30', lw=.8)
        for tt in (-TAU, TAU): B.axhline(tt, color='#16263d', lw=.8, ls=(0, (4, 3)))
        o = sm & ~dr & ~wr; B.scatter(q['u'][o], clip(q['sd'][o]), s=2, c='#DDDCD6', lw=0)
        from matplotlib.collections import LineCollection
        segc = lambda S_: np.stack([S_[:, :, 0], np.clip(S_[:, :, 1], -60, 40)], 2)
        B.add_collection(LineCollection(segc(st['prior_seg']), colors='#7A7A74', linewidths=1., linestyles=(0, (2, 2))))
        B.scatter(st['gt_u'], clip(st['gt_sd']), s=1.5, c='black', lw=0, alpha=.7)
        o = sm & dr & ~q['bound'] & ~wr; B.scatter(q['u'][o], clip(q['sd'][o]), s=9, c='#F0B49C', lw=0)
        o = sm & dr & q['bound'] & ~wr; B.scatter(q['u'][o], clip(q['sd'][o]), s=7, c='#D85A30', lw=0)
        o = sm & wr; B.scatter(q['u'][o], clip(q['sd'][o]), s=8, c=PINK, lw=0)
        if mz is not None and mk == it: B.add_collection(LineCollection(segc(mz['section_seg']), colors='#16263d', linewidths=1.1)); how = '메시'
        else:
            dl = A/f'depthline_{name}.npz'; how = '렌더 깊이'
            if dl.exists(): z = loadz(dl); B.plot(z['u'], clip(z['sd']), color='#16263d', lw=1.3)
        B.set_ylim(-63, 43); B.set_xlim(ctx.sec_xlim); B.set_title(f'단면 · 보정 자리 폭 1 m · 면 선: {how}', fontsize=12, loc='left', color='#2e3a48')
        B.set_ylabel('목표면에서 (cm)', fontsize=10); B.set_xlabel('지붕 긴 방향 (m)', fontsize=10); B.tick_params(labelsize=9)
    if 'traj' in axes:
        T_ = axes['traj']; cols = dict(wrong_lineage=PINK, moved_in='#E59A7A', background='#7FA7D9'); labs = dict(wrong_lineage='틀린 판정 계보', moved_in='옮겨 온 것', background='배경 출신')
        for k, rows in ctx.traj['trajectories'].items():
            if not rows: continue
            xs = [r['iteration'] for r in rows if r['alive'] and r['iteration'] <= it]; ys = [r['sd_cm'] for r in rows if r['alive'] and r['iteration'] <= it]
            T_.plot(xs, ys, color=cols[k], lw=1.6, label=labs[k]+f' {ctx.traj["picks"][k]}')
            dead = ctx.traj['death_iteration'].get(k)
            if dead is not None and dead <= it and xs: T_.scatter([dead], [ys[-1]], marker='x', s=60, color=cols[k], zorder=6)
        for tt in (-TAU, TAU): T_.axhline(tt, color='#16263d', lw=.7, ls=(0, (4, 3)))
        T_.set_yscale('symlog', linthresh=50); T_.set_xlim(-300, 30300); T_.set_ylim(-120, 700); T_.set_yticks([-100, -50, -21.2, 0, 21.2, 50, 100, 300, 600]); T_.set_yticklabels(['-100', '-50', '-τ', '0', 'τ', '50', '100', '300', '600']); T_.axvline(it, color='#2e3a48', lw=1.2); T_.set_title('개체 궤적 · 목표면까지 거리', fontsize=12, loc='left', color='#2e3a48')
        T_.set_ylabel('cm (±50 밖은 로그)', fontsize=10); T_.tick_params(labelsize=9); T_.legend(loc='lower right', fontsize=8.5, frameon=False); T_.set_xticks([0, 7000, 15000, 30000]); T_.set_xticklabels(['0', '7,000', '15,000', '30,000'])
    if 'left' in axes:
        L = axes['left']; ks = sorted(ctx.scores)
        for metric, ls_, lab in [('completeness_pct', '-', '완전성'), ('accuracy_pct', (0, (4, 2)), '정확성')]:
            ys = [ctx.scores[k][1][metric] for k in ks]; past = [k <= it for k in ks]
            L.plot(ks, ys, color='#D85A30', lw=1.2, ls=ls_, alpha=.35); L.plot([k for k, p in zip(ks, past) if p], [y for y, p in zip(ys, past) if p], color='#D85A30', lw=1.8, ls=ls_, marker='o', ms=4, label='본 방법 '+lab)
        for (lab, v), col in zip([('판단만', (ctx.refs['judgment'], None)), ('LGDM', ctx.refs['LGDM']), ('GeoGS', ctx.refs['GeoGS']), ('원래 판 30,000회', ctx.refs['original'])], ['#888780', '#1D9E75', '#7FA7D9', '#16263d']):
            L.axhline(v[0], color=col, lw=.9, label=lab+' 완전성')
            if v[1] is not None: L.axhline(v[1], color=col, lw=.9, ls=(0, (4, 2)))
        for nm, sc_ in ctx.pre_scores.items():
            if ctx.it[nm] <= it: L.scatter([ctx.it[nm]]*2, [sc_[1]['completeness_pct'], sc_[1]['accuracy_pct']], s=28, facecolors='white', edgecolors='#D85A30', zorder=6)
        L.axvline(it, color='#2e3a48', lw=1.2); L.set_xlim(-300, 30300); L.set_ylim(0, 102); L.set_ylabel('%', fontsize=10); L.tick_params(labelsize=9)
        L.set_title('사례 자리(사전 정보 오류) 완전성 · 정확성(점선)', fontsize=12, loc='left', color='#2e3a48'); L.legend(loc='lower right', fontsize=7.5, frameon=False, ncol=2)
        L.set_xticks([0, 3000, 7000, 15000, 30000]); L.set_xticklabels(['0', '3,000', '7,000', '15,000', '30,000'])
    if 'right' in axes:
        Rr = axes['right']; xs = [ctx.it[n] for n in ctx.names if not n.endswith('pre_reset')]; nn = [n for n in ctx.names if not n.endswith('pre_reset')]
        y1 = [ctx.curve[n].get('drawing_tau_in_pct') for n in nn]; y2 = [ctx.curve[n].get('all_tau_in_pct') for n in nn]; y3 = [ctx.depth_err.get(n, {}).get('median_abs_cm') for n in nn]
        for ys, col, lw, lab in [(y1, '#D85A30', 1.8, '면을 그리는 가우시안 τ 안'), (y2, '#E8B9A4', 1.4, '모든 가우시안 τ 안')]:
            xp = [x for x, y in zip(xs, ys) if y is not None]; yp = [y for y in ys if y is not None]
            Rr.plot(xp, yp, color=col, lw=lw, alpha=.3); Rr.plot([x for x in xp if x <= it], [y for x, y in zip(xp, yp) if x <= it], color=col, lw=lw, label=lab)
        Rr.set_ylim(0, 102); Rr.set_ylabel('보정 자리 τ 안 (%)', fontsize=10); R2 = Rr.twinx(); xp = [x for x, y in zip(xs, y3) if y is not None]; yp = [y for y in y3 if y is not None]
        R2.plot(xp, yp, color='#2e3a48', lw=1., alpha=.3); R2.plot([x for x in xp if x <= it], [y for x, y in zip(xp, yp) if x <= it], color='#2e3a48', lw=1.2, label='학습 영상 깊이 오차 중앙값')
        R2.set_yscale('log'); R2.set_ylabel('깊이 오차 cm', fontsize=10); R2.tick_params(labelsize=9); R2.set_ylim(1, 2000)
        Rr.axvspan(600, 14900, color='#F1EFE8', lw=0, zorder=0)
        for r_ in ctx.resets: Rr.plot([r_, r_], [0, 5], color='#5F5E5A', lw=1.5)
        Rr.axvline(it, color='#2e3a48', lw=1.2); Rr.set_xlim(-300, 30300); Rr.tick_params(labelsize=9); Rr.set_title('τ 안 비율 · 깊이 오차 (음영 = 밀도 제어, 눈금 = 불투명도 되돌림)', fontsize=12, loc='left', color='#2e3a48')
        h1, l1 = Rr.get_legend_handles_labels(); h2, l2 = R2.get_legend_handles_labels(); Rr.legend(h1+h2, l1+l2, loc='lower right', fontsize=8, frameon=False)
        Rr.set_xticks([0, 3000, 7000, 15000, 30000]); Rr.set_xticklabels(['0', '3,000', '7,000', '15,000', '30,000'])
    if own:
        h = [Patch(color=COL[0], label='일치'), Patch(color=COL[2], label='보정'), Patch(color=COL[1], label='보존'), Patch(color=COL[4], label='결측'), Patch(color=PINK, label='틀린 판정 계보'),
             Patch(color=NEU, label='가까운 목표 없음'), Patch(color=tuple(np.array(to_rgb(COL[2]))*.45+PALE*.55), label='흐린 색 = 묶이지 않음'),
             Line2D([], [], marker='o', ls='', color='#D85A30', label='진한 점 = 면을 그리는 가우시안'), Patch(color=GREY, label='표면 τ 안'), Patch(color=RED, label='표면 위로 1 m'), Patch(color=BLUE, label='표면 아래로 1 m'),
             Line2D([], [], color='black', marker='o', ls='', ms=3, label='참값 점'), Line2D([], [], color='#7A7A74', ls=(0, (2, 2)), label='옛 항공 LiDAR')]
        fig.legend(handles=h, loc='lower center', ncol=13, frameon=False, fontsize=9.5, bbox_to_anchor=(.5, .003), handlelength=1.2, columnspacing=1.)
    return fig, axes, dict(state=name, iteration=it, drawing_rule=rule, drawing_uids=len(draw), mesh_iteration=mk, surface_line='mesh' if (mk == it) else 'render depth', mode=mode)

def boxes(fig, axes):
    W, H = fig.canvas.get_width_height(); out = {}
    for k in ['surface', 'section']:
        bb = axes[k].get_tightbbox(fig.canvas.get_renderer())
        x0, y0, x1, y1 = bb.x0, bb.y0, bb.x1, bb.y1; out[k] = [max(0, int(x0)-6), max(0, int(H-y1)-6), min(W, int(x1)+6), min(H, int(H-y0)+6)]
    return out

def main(step='frames', *names):
    ctx = Ctx(); FR.mkdir(parents=True, exist_ok=True)
    if step == 'static': return prep_static(ctx)
    if step == 'mesh':
        for n in names: prep_mesh(ctx, n)
        return
    if step == 'depth': return prep_depth(ctx)
    st = loadz(A/'static.npz'); s30 = ctx.defs.section(state('30000')); u = s30['u'][(s30['v'] >= ctx.b0) & (s30['v'] < ctx.b0+1)]
    ctx.sec_xlim = (float(min(u.min(), st['gt_u'].min()))-1, float(max(u.max(), st['gt_u'].max()))+1)
    order = sorted(ctx.names, key=lambda n: (ctx.it[n], 0 if n.endswith('pre_reset') else 1)); sel = list(names) or order; recs = []
    for mode in (['result', 'all'] if step == 'frames' else [step]):
        out = FR/mode; out.mkdir(exist_ok=True)
        for i, n in enumerate(order):
            if n not in sel: continue
            fig, axes, rec = frame(ctx, n, mode); fig.canvas.draw(); rec['crop'] = boxes(fig, axes); p = out/f'{i:03d}_{n}.png'; fig.savefig(p, facecolor='white'); plt.close(fig)
            rec.update(file=str(p.relative_to(O)), order=i, hold=ctx.it[n] in HOLD and not n.endswith('pre_reset')); recs.append(rec); print('FRAME', mode, n, flush=True)
    dump(FR/f'frames_{step}.json', dict(at=now(), frames=recs, camera=dict(basis=ctx.Bs.tolist(), center=ctx.ctr.tolist(), extent_lo=ctx.lo.tolist(), extent_hi=ctx.hi.tolist(), azimuth=180, elevation=35, projection='orthographic'),
         band=dict(b0=ctx.b0, width_m=1, axis='v = second principal axis of reference targets'), colours=dict(COL={str(k): v for k, v in COL.items()}, none=NEU, wrong=PINK, pale='#EEECE6'),
         plate='새 판 (tl_B173nb_b10_ALS_s0 attempt2)', scientific_verdict=None))

if __name__ == '__main__': main(*sys.argv[1:])
