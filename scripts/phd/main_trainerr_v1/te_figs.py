"""Figures (order 7.2): one script for every cell x arm, fixed colours/legends, no text except cell name, axes and legend; json provenance.
argv: check1|check2|check3|check4 [tag]"""
import open3d as o3d
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
from matplotlib.collections import LineCollection
from PIL import Image
from common import *
FONT = '/fonts/NotoSansCJK-Regular.ttc'; fm.fontManager.addfont(FONT); plt.rcParams['font.family'] = fm.FontProperties(fname=FONT).get_name(); plt.rcParams['axes.unicode_minus'] = False
COL = {'1-마': '#7f7f7f', '1-나': '#bcbd22', '1-가': '#17becf', '1-다': '#9467bd', '1-라': '#d62728', '맞음(τ 안)': '#c7c7c7',
       '2-가': '#8c564b', '2-나': '#e377c2', '2-라': '#7f7f7f', '2-다': '#ff7f0e', '2-마': '#bcbd22', '2-바': '#2ca02c',
       '3-마': '#7f7f7f', '3-가': '#1f77b4', '3-나': '#ff7f0e', '3-다': '#9467bd', '3-라': '#d62728', '3-바': '#2ca02c', '3-사': '#8c564b',
       '4-마': '#7f7f7f', '4-라': '#c5b0d5', '4-나': '#ff7f0e', '4-가': '#1f77b4', '4-다': '#d62728', '4-확인불가': '#bcbd22', '대상 아님': '#e8e8e8'}
NAME = {'c1': '① B0 × LoD2 영상 깊이 오류', 'c2': '② R1 × 항공 LiDAR 영상 깊이 오류', 'c3': '③ B0 × LoD2 영상 깊이 결측'}
ARMN = {'own': '본 방법 판정', 'gt': '정답 판정'}
FIG = D/'figures'
_mesh_cache = {}

def mesh_arrays(path):
    if str(path) not in _mesh_cache:
        m = o3d.io.read_triangle_mesh(str(path)); _mesh_cache.clear(); _mesh_cache[str(path)] = (np.asarray(m.vertices), np.asarray(m.triangles))
    return _mesh_cache[str(path)]

def section_of(cell, stem, lostxyz):
    if cell in ('c1', 'c2'):
        s = json.loads((GT/'scenes'/stem/'section.json').read_text()); p0 = np.array(s['start']); p1 = np.array(s['end']); return p0, p1, float(s['half_width']), 'GTJUDGE section.json'
    from scipy.spatial import cKDTree
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    P = lostxyz; pairs = cKDTree(P).query_pairs(.6, output_type='ndarray'); A = coo_matrix((np.ones(len(pairs)), (pairs[:, 0], pairs[:, 1])), shape=(len(P), len(P)))
    _, lab = connected_components(A, directed=False); big = np.bincount(lab).argmax(); Q = P[lab == big, :2]; c = Q.mean(0); u, s_, vt = np.linalg.svd(Q-c, full_matrices=False); d = vt[0]
    t = (Q-c)@d; return c+(t.min()-1)*d, c+(t.max()+1)*d, .6, 'largest 0.6 m cluster of lost points, principal XY axis'

def cut_segments(path, p0, p1, half):
    V, F = mesh_arrays(path); d = (p1-p0)/np.linalg.norm(p1-p0); nrm = np.array([-d[1], d[0]]); L = np.linalg.norm(p1-p0)
    s = (V[:, :2]-p0)@nrm; t = (V[:, :2]-p0)@d; keep = (np.abs(s) <= half+2) & (t >= -2) & (t <= L+2)
    fs = F[keep[F].all(1)]; sv = s[fs]; cross = (sv.min(1) <= 0) & (sv.max(1) >= 0); fs = fs[cross]; segs = []
    for e0, e1 in [(0, 1), (1, 2), (2, 0)]:
        a, b = fs[:, e0], fs[:, e1]; sa, sb = s[a], s[b]; ok = (sa*sb <= 0) & (sa != sb); w = np.where(ok, sa/np.where(ok, sa-sb, 1), np.nan)
        P = V[a]+(V[b]-V[a])*w[:, None]; segs.append(np.c_[(P[:, :2]-p0)@d, P[:, 2]])
    S = np.stack(segs, 1); out = []
    for row in S:
        q = row[np.isfinite(row).all(1)]
        if len(q) >= 2: out.append(q[:2])
    return np.array(out) if out else np.zeros((0, 2, 2))

def slab(P, p0, p1, half):
    d = (p1-p0)/np.linalg.norm(p1-p0); nrm = np.array([-d[1], d[0]]); s = (P[:, :2]-p0)@nrm; t = (P[:, :2]-p0)@d
    return (np.abs(s) <= half) & (t >= 0) & (t <= np.linalg.norm(p1-p0)), t

def legend_handles(classes):
    from matplotlib.lines import Line2D
    return [Line2D([], [], marker='o', ls='', color=COL[k], label=k) for k in classes]

def save(fig, name, meta):
    FIG.mkdir(parents=True, exist_ok=True); p = FIG/f'{name}.png'; fig.savefig(p, dpi=200, bbox_inches='tight'); plt.close(fig)
    dump(p.with_suffix('.json'), dict(at=now(), figure=p.name, script='scripts/phd/main_trainerr_v1/te_figs.py', **meta, text_in_figure='cell name, axes, legend only', scientific_verdict=None))

def check1(tag=''):
    tau_rows = json.loads((D/'tables/tau.json').read_text())['rows']
    for cell in ['c1', 'c2', 'c3']:
        stem = STEMS[cell]; site = stem.split('__')[0]; ref = loadz(GT/'reference'/site/'dense.npz', ['xyz'])['xyz']
        for arm in ARMS:
            z = loadz(O/'checks'/f'{stem}__{arm}.npz'); m = z['cell'] == int(cell[1]); L = m & (z['set'] == 0); ap = arm_paths(stem, arm)
            p0, p1, half, srule = section_of(cell, stem, z['xyz'][L])
            fig, (a1, a2) = plt.subplots(1, 2, figsize=(13, 4.2), gridspec_kw=dict(width_ratios=[3.2, 1]))
            inr, tr = slab(ref, p0, p1, half); a1.scatter(tr[inr], ref[inr, 2], s=.3, c='#9a9a9a', lw=0, label='참값', rasterized=True)
            for path, col, lab in [(ap['target_mesh'], '#1f77b4', '목표면'), (ap['trained_mesh'], '#d62728', '학습 뒤 메시')]:
                seg = cut_segments(path, p0, p1, 0.); a1.add_collection(LineCollection(seg, colors=col, linewidths=.8, label=lab))
            il, tl = slab(z['xyz'], p0, p1, half); sel = L & il
            if 'first_hit' in z:
                fh = z['first_hit'][sel]; ok = np.isfinite(fh).all(1); d = (p1-p0)/np.linalg.norm(p1-p0)
                lines = np.stack([np.c_[tl[sel][ok], z['xyz'][sel][ok, 2]], np.c_[(fh[ok, :2]-p0)@d, fh[ok, 2]]], 1)
                a1.add_collection(LineCollection(lines, colors='#ff7f0e', linewidths=.5, label='측정선'))
            a1.scatter(tl[sel], z['xyz'][sel, 2], s=6, marker='x', c='k', lw=.6, label='잃은 점')
            zz = np.r_[ref[inr, 2], z['xyz'][sel, 2]] if inr.any() else z['xyz'][sel, 2]
            if len(zz): a1.set_ylim(np.quantile(zz, .005)-1.5, np.quantile(zz, .995)+3)
            a1.set_xlim(0, np.linalg.norm(p1-p0)); a1.set_aspect('equal', adjustable='datalim'); a1.set_xlabel('단면 위치 (m)'); a1.set_ylabel('높이 (m)'); a1.legend(loc='upper right', fontsize=7, markerscale=2)
            a1.set_title(f'{NAME[cell]} · {ARMN[arm]}', fontsize=9)
            tr_ = [r for r in tau_rows if r['cell'] == cell and r['arm'] == arm]
            a2.bar([str(r['tau_multiplier']) for r in tr_], [r['drop_pp'] for r in tr_], color='#555555'); a2.set_xlabel('τ 배수'); a2.set_ylabel('목표면 − 학습 뒤 (%p)'); a2.axhline(0, c='k', lw=.5)
            save(fig, f'check1_{cell}_{arm}', dict(cell=cell, arm=arm, section=dict(start=p0.tolist(), end=p1.tolist(), half_width=half, rule=srule), lost_in_slab=int(sel.sum()),
                 sources=dict(target_mesh=str(ap['target_mesh']), trained_mesh=str(ap['trained_mesh']), reference=str(GT/'reference'/site/'dense.npz'), tau_table='tables/tau.csv')))

def topmap(ax, z, L, K, key, classes, cell, arm):
    ax.scatter(z['xyz'][K, 0], z['xyz'][K, 1], s=.4, c='#dddddd', lw=0, rasterized=True)
    v = z[key][L]; xy = z['xyz'][L]
    for k in classes:
        s = v == k
        if s.any(): ax.scatter(xy[s, 0], xy[s, 1], s=3, c=COL[k], lw=0, label=k)
    ax.set_aspect('equal'); ax.set_xlabel('x (m)'); ax.set_ylabel('y (m)'); ax.set_title(f'{NAME[cell]} · {ARMN[arm]}', fontsize=9); ax.legend(fontsize=7, markerscale=3, loc='best')

def check2(tag=''):
    from te_checks import C2
    for cell in ['c1', 'c2']:
        stem = STEMS[cell]; site, prior = stem.split('__')
        views = [v for v in json.loads((GT/'views'/f'{site}.json').read_text())['views'] if not v['virtual']]
        for arm in ARMS:
            z = loadz(O/'checks'/f'{stem}__{arm}.npz'); pr = loadz(O/'views'/f'{stem}__{arm}.npz', ['point', 'view', 'u', 'v', 'facing']); m = z['cell'] == int(cell[1]); L = m & (z['set'] == 0); K = m & (z['set'] == 1)
            fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 5)); topmap(a1, z, L, K, 'check2', C2, cell, arm)
            vals = z['check2'][L]; vals = vals[vals != '대상 아님']; meta = dict(cell=cell, arm=arm)
            if len(vals):
                u_, c_ = np.unique(vals, return_counts=True); big = u_[np.argmax(c_)]; cand = np.flatnonzero(L & (z['check2'] == big) & (z['seen_views'] >= 1))
                if len(cand):
                    i = cand[np.lexsort((z['point_id'][cand], -z['seen_views'][cand]))[0]]; pp = np.flatnonzero(pr['point'] == i); j = pp[np.argmax(pr['facing'][pp])]; vw = views[pr['view'][j]]
                    im = np.asarray(Image.open(Path('/p/fork_inputs/s61')/site/f'scene_{prior}/images'/f'{vw["name"]}.jpg')); u, v = float(pr['u'][j]), float(pr['v'][j])
                    idx = json.loads((arm_paths(stem, arm)['target_dir']/'maps/index.json').read_text())['views'][vw['name']]
                    own = loadz(arm_paths(stem, arm)['target_dir']/'maps'/idx['file'], ['owner'])['owner']; r = 70; x0, x1 = int(max(0, u-r)), int(min(im.shape[1], u+r)); y0, y1 = int(max(0, v-r)), int(min(im.shape[0], v+r))
                    crop = im[y0:y1, x0:x1]; oc = own[y0:y1, x0:x1]; edge = np.zeros(oc.shape, bool); edge[:, :-1] |= oc[:, 1:] != oc[:, :-1]; edge[:-1, :] |= oc[1:, :] != oc[:-1, :]
                    mine = oc == z['patch_row'][i]; a2.imshow(crop); ov = np.zeros(crop.shape[:2]+(4,)); ov[edge] = [1, 1, 1, .9]; ov[mine & ~edge] = [1, .85, 0, .35]; a2.imshow(ov)
                    a2.plot([u-x0], [v-y0], 'o', mfc='none', mec='r', ms=8, mew=1.5); a2.set_xticks([]); a2.set_yticks([]); a2.set_title(big, fontsize=9)
                    meta.update(representative=dict(point_id=int(z['point_id'][i]), cls=str(big), view=vw['name'], uv=[u, v], patch_row=int(z['patch_row'][i]),
                                overlay='white = target-map owner boundaries, yellow = pixels whose owner is the point patch, red = point'))
            save(fig, f'check2_{cell}_{arm}', meta)

def check3(tag=''):
    from te_checks import C3, C3E
    for cell in ['c1', 'c2', 'c3']:
        stem = STEMS[cell]; site = stem.split('__')[0]; ref = loadz(GT/'reference'/site/'dense.npz', ['xyz'])['xyz']
        for arm in ARMS:
            z = loadz(O/'checks'/f'{stem}__{arm}.npz'); m = z['cell'] == int(cell[1]); L = m & (z['set'] == 0); K = m & (z['set'] == 1); ap = arm_paths(stem, arm)
            comb = np.where(z['check3'] != '대상 아님', z['check3'], z['check3_empty']); zz = dict(z); zz['comb'] = comb
            fig, (a1, a2) = plt.subplots(1, 2, figsize=(14, 5), gridspec_kw=dict(width_ratios=[1, 1.6])); topmap(a1, zz, L, K, 'comb', C3+C3E, cell, arm)
            p0, p1, half, srule = section_of(cell, stem, z['xyz'][L]); inr, tr = slab(ref, p0, p1, half); a2.scatter(tr[inr], ref[inr, 2], s=.3, c='#9a9a9a', lw=0, rasterized=True, label='참값')
            seg = cut_segments(ap['trained_mesh'], p0, p1, 0.); a2.add_collection(LineCollection(seg, colors='#444444', linewidths=.6, label='학습 뒤 메시'))
            snap = loadz(Path(ap['model'])/'target_monitor/snapshot_30000.npz', ['xyz']); il, _ = slab(z['xyz'], p0, p1, half); sel = L & il & (z['drawer'] >= 0)
            G_ = snap['xyz'][z['drawer'][sel]]; ig, tg_ = slab(G_, p0, p1, half+1.)
            for k in C3:
                s = (z['check3'][sel] == k)
                if s.any(): a2.scatter(tg_[s], G_[s, 2], s=8, c=COL[k], lw=0, label=k)
            a2.set_aspect('equal', adjustable='datalim'); a2.set_xlabel('단면 위치 (m)'); a2.set_ylabel('높이 (m)'); a2.legend(fontsize=7, markerscale=2, loc='upper right')
            zz_ = ref[inr, 2]
            if len(zz_): a2.set_ylim(np.quantile(zz_, .005)-1.5, np.quantile(zz_, .995)+3)
            save(fig, f'check3_{cell}_{arm}', dict(cell=cell, arm=arm, section=dict(start=p0.tolist(), end=p1.tolist(), half_width=half, rule=srule), drawers_in_slab=int(sel.sum()),
                 sources=dict(model_snapshot=str(Path(ap['model'])/'target_monitor/snapshot_30000.npz'), trained_mesh=str(ap['trained_mesh']))))

def check4(tag=''):
    from te_checks import C4
    for cell in ['c1', 'c2', 'c3']:
        stem = STEMS[cell]
        for arm in ARMS:
            z = loadz(O/'checks'/f'{stem}__{arm}.npz'); pr = loadz(O/'checks'/f'{stem}__{arm}_pairs.npz'); m = z['cell'] == int(cell[1]); L = m & (z['set'] == 0)
            vals = z['check4'][L]; vals = vals[vals != '대상 아님']; u_, c_ = np.unique(vals, return_counts=True); order = [str(x) for x in u_[np.argsort(-c_)]][:3]; reps = []
            for k in order:
                cand = np.flatnonzero(L & (z['check4'] == k)); i = cand[np.lexsort((z['point_id'][cand], -z['seen_views'][cand]))[0]]; reps.append((k, i))
            fig, axes = plt.subplots(1, max(1, len(reps)), figsize=(4.6*max(1, len(reps)), 3.6), squeeze=False)
            for ax, (k, i) in zip(axes[0], reps):
                pp = np.flatnonzero(pr['point'] == i); o = np.lexsort((pr['view'][pp], -pr['facing'][pp].astype(int))); pp = pp[o]; x = np.arange(len(pp)); ref = pr['ref_z'][pp].astype(float)
                for key, col, lab in [('target_z', '#2ca02c', '목표 깊이'), ('render_z', '#d62728', '학습 렌더 깊이'), ('mesh_z', '#1f77b4', '메시 첫 교차')]:
                    y = pr[key][pp].astype(float)-ref
                    if key == 'target_z': y = np.where(pr[key][pp] > 0, y, np.nan)
                    ax.plot(x, y, 'o', ms=3, c=col, label=lab)
                e = pr['empty'][pp]; ax.plot(x[e], np.zeros(e.sum()), 'x', c='#7f7f7f', label='렌더 빔')
                nf = int(pr['facing'][pp].sum()); ax.axvline(nf-.5, c='k', lw=.5, ls=':'); ax.axhline(0, c='k', lw=.6)
                ax.axhspan(-float(z['tau'][i]), float(z['tau'][i]), color='#eeeeee', zorder=0); ax.set_xlabel('보는 영상 (마주 봄 | 비스듬함)'); ax.set_ylabel('참값 깊이와의 차 (m)'); ax.set_title(f'{k}', fontsize=9)
                lim = np.nanquantile(np.abs(np.r_[pr['render_z'][pp]-ref, pr['mesh_z'][pp]-ref]), .95) if len(pp) else 1; ax.set_ylim(-max(1, 1.3*lim), max(1, 1.3*lim))
            axes[0][0].legend(fontsize=7, loc='best'); fig.suptitle(f'{NAME[cell]} · {ARMN[arm]}', fontsize=9)
            save(fig, f'check4_{cell}_{arm}', dict(cell=cell, arm=arm, representatives=[dict(cls=k, point_id=int(z['point_id'][i]), seen_views=int(z['seen_views'][i])) for k, i in reps],
                 rule='same-ray four depths per seen view; reference depth = point camera z (c1/c2) or reference z-buffer (c3)'))

RUNNAME = {'tl_R1_ALS_gt': ('R1rep_b10__ALS', 'gt'), 'tl_B0_LoD2_gt': ('B0_b10__LoD2', 'gt'), 'tl_R1_ALS_own': ('R1rep_b10__ALS', 'own'), 'tl_B0_LoD2_own': ('B0_b10__LoD2', 'own')}
KEYS = ['0', '100', '300', '1000', '2000', '3000_pre_reset', '3000', '5000', '7000', '10000', '15000', '20000', '30000']
C5 = ['5-가', '5-나', '5-다', '5-라', '5-마', '5-확인불가']
COL.update({'5-가': '#ff7f0e', '5-나': '#9467bd', '5-다': '#8c564b', '5-라': '#e377c2', '5-마': '#7f7f7f', '5-확인불가': '#bcbd22', '5-바': '#d62728', '5-사': '#1f77b4', '5-아': '#17becf'})
def check5(run):
    import glob, torch
    from te_check5 import model_of
    stem, arm = RUNNAME[run]; site = stem.split('__')[0]; m = model_of(run); z = loadz(O/'checks'/f'{stem}__{arm}__tl.npz'); c5 = loadz(O/'check5'/f'{run}.npz')['check5']
    tg = loadz(arm_paths(stem, arm)['targets'], ['target', 'normal']); d30 = torch.load(m/'trainlog/scene/30000.pt', map_location='cpu', weights_only=False); uid30 = d30['uid'].numpy()
    states = sorted(((int(Path(f).stem), f) for f in glob.glob(str(m/'trainlog/states/*.npz')) if Path(f).stem.isdigit()))
    ref = loadz(GT/'reference'/site/'dense.npz', ['xyz'])['xyz']
    for cell in sorted({f'c{x}' for x in z['cell'].tolist()}):
        L = (z['cell'] == int(cell[1])) & (z['set'] == 0); reps = []
        for k in C5:
            cand = np.flatnonzero(L & (c5 == k))
            if not len(cand): continue
            g, cnt = np.unique(z['drawer'][cand], return_counts=True); gi = int(g[np.lexsort((uid30[g], -cnt))[0]]); i = cand[z['drawer'][cand] == gi][0]; reps.append((k, gi, int(uid30[gi]), i))
        fig = plt.figure(figsize=(16, 9)); gs = fig.add_gridspec(3, 7, height_ratios=[1.2, 1, 1]); ax = fig.add_subplot(gs[0, :])
        for k, gi, u, i in reps:
            t = z['patch_row'][i]; n_ = tg['normal'][t]/np.linalg.norm(tg['normal'][t]); xs, ys = [], []
            for it, f in states:
                st = np.load(f); w = np.flatnonzero(st['uid'] == u)
                if len(w): xs.append(it); ys.append(float(n_@(st['xyz'][w[0]].astype(float)-tg['target'][t])))
            ax.plot(xs, ys, '-o', ms=2, c=COL[k], label=k)
        ax.set_yscale('symlog', linthresh=.5); ax.set_xlabel('반복'); ax.set_ylabel('목표면까지 거리 (m)'); ax.legend(fontsize=7); ax.set_title(f'{NAME[cell]} · {ARMN[arm]} · 기록 판', fontsize=9)
        p0, p1, half, srule = section_of(cell, stem, z['xyz'][L]); inr, tr = slab(ref, p0, p1, half)
        for j, name in enumerate(KEYS):
            a = fig.add_subplot(gs[1+j//7, j % 7])
            mp = O/'gtj/meshes'/f'{stem}__tl_{arm}_{name}'/'final.ply'
            a.scatter(tr[inr], ref[inr, 2], s=.2, c='#b0b0b0', lw=0, rasterized=True)
            if mp.exists(): a.add_collection(LineCollection(cut_segments(mp, p0, p1, 0.), colors='#d62728', linewidths=.5))
            a.set_title(name, fontsize=7); a.set_xticks([]); a.set_yticks([]); zz = ref[inr, 2]
            if len(zz): a.set_ylim(np.quantile(zz, .005)-1.5, np.quantile(zz, .995)+3)
            a.set_xlim(0, np.linalg.norm(p1-p0))
        save(fig, f'check5_{cell}_{arm}', dict(run=run, cell=cell, arm=arm, representatives=[dict(cls=k, gaussian=gi, uid=u, point=int(i)) for k, gi, u, i in reps], section=dict(start=p0.tolist(), end=p1.tolist(), rule=srule), keys=KEYS))

def splat(ax, mesh, box, az, el, res=900):
    V, F = mesh_arrays(mesh); ins = ((V >= box[0]) & (V <= box[1])).all(1); V = V[ins]
    if not len(V): return
    a, e = np.radians(az), np.radians(el); f = -np.array([np.cos(e)*np.cos(a), np.cos(e)*np.sin(a), np.sin(e)]); r = np.cross(f, [0, 0, 1.]); r = r/np.linalg.norm(r) if np.linalg.norm(r) > 1e-6 else np.array([1., 0, 0]); u = np.cross(r, f)
    q = (V-V.mean(0))@np.stack([r, u, f]).T; span = np.ptp(q[:, :2], 0).max()+1e-9; px = ((q[:, :2]-q[:, :2].min(0))/span*(res-1)).astype(int)
    order = np.argsort(q[:, 2])[::-1]; img = np.full((res, res), np.nan); dep = q[:, 2]
    img[px[order, 1], px[order, 0]] = dep[order]
    ax.imshow(img, origin='lower', cmap='viridis'); ax.set_xticks([]); ax.set_yticks([])

def check6(stem, arm, family, tag=''):
    ap = arm_paths(stem, arm); box = np.array(json.loads((GT/'views'/f'{stem.split("__")[0]}.json').read_text())['box']); reg = json.loads((O/'region'/f'{stem}.json').read_text())
    lo = np.asarray(reg['grid_origin']); hi = lo+np.asarray(reg['grid_shape'])*reg['voxel_m']; after = O/'gtj/meshes'/f'{stem}__{family}'/'final.ply'
    Z = loadz(O/'meshes'/f'{stem}__{family}'/'points.npz')
    for cell in sorted(k for k, v in STEMS.items() if v == stem):
        fig, axes = plt.subplots(2, 4, figsize=(16, 8))
        for row, (mesh, lab) in enumerate([(ap['trained_mesh'], '손대기 전'), (after, '손댄 뒤')]):
            for j, (az, el) in enumerate([(0, 90), (45, 35), (225, 35)]): splat(axes[row, j], mesh, (lo, hi), az, el); axes[row, j].set_title(f'{lab}', fontsize=8)
            ls = loadz(O/'sets'/f'{cell}_{arm}_lost.npz', ['xyz', 'point_id', 'normal', 'wall', 'tau_m']); a = axes[row, 3]
            if cell != 'c3':
                w = Z['reference__within_tau1'][ls['point_id']].astype(bool) if row == 1 else np.zeros(len(ls['xyz']), bool)
                a.scatter(ls['xyz'][~w, 0], ls['xyz'][~w, 1], s=2, c='#d62728', lw=0, label='τ 밖'); a.scatter(ls['xyz'][w, 0], ls['xyz'][w, 1], s=2, c='#2ca02c', lw=0, label='τ 안')
            else: a.scatter(ls['xyz'][:, 0], ls['xyz'][:, 1], s=1, c='#d62728', lw=0, label='잃은 결과 점(손대기 전)')
            a.set_aspect('equal'); a.legend(fontsize=7, markerscale=3)
        fig.suptitle(f'{NAME[cell]} · {ARMN[arm]} · {family}', fontsize=9)
        save(fig, f'check6_{cell}_{arm}_{family}', dict(stem=stem, arm=arm, cell=cell, family=family, before=str(ap['trained_mesh']), after=str(after), views='top, azimuth 45 / 225 elevation 35 (orthographic vertex depth splat inside the record range)'))

if __name__ == '__main__':
    globals()[sys.argv[1]](*sys.argv[2:])
