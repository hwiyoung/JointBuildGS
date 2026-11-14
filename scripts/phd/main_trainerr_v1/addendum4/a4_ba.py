"""Work ba (order 7): four figures + one summary per case (place photo, section, stage sections, curve). CPU image (open3d, torch, PIL).
  case <name> : figures/ba_<name>_{photo,section,stages,curve,summary}.png + json sources
Cases: see CASES. Place points come from GT (or from the result points that define the case); section frame = densest place point, h axis across the
surface (walls: horizontal normal, sign = camera side; others: minor principal XY axis), slab +-0.25 m."""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1/addendum4')
from a4_common import *
import time
RS = PH/'main_rescore_v1/PHD-MAIN-RESCORE-v1'; TLCASE = TLC/'runs/B0_b10/tl_B0_b10_LoD2_s0/attempt1/model'; FIG = A4D/'figures'; BA = A4O/'ba'
STAGES = ['1000', '3000_pre_reset', '5000', '7000', '15000', '30000']; STAGE_KO = {'1000': '1,000회', '3000_pre_reset': '3,000회 재설정 직전', '5000': '5,000회', '7000': '7,000회', '15000': '15,000회', '30000': '30,000회'}
KCOL = ['#1f77b4', '#9467bd', '#ff7f0e', '#7f7f7f']; KNAME = ['이 자리 목표에 묶임', '다른 목표에 묶임', '풀린 것', '묶이지 않은 것(배경 씨앗과 자식)']

def final_mesh(stem): return RS/('addendum3_stage1' if stem.startswith('B173') else 'addendum3_stage2')/'meshes'/f'{stem}__FINALTRAIN_30000/primary.ply'
def twodgs_mesh(stem): return RS/('addendum3_stage1' if stem.startswith('B173') else 'addendum3_stage2')/'meshes'/f'{stem}__2DGS_30000/primary.ply'
def run_info(run):
    if run == 'tl_R1_ALS_own': return O/'runs/R1rep_b10/tl_R1_ALS_own/attempt1/model', lambda n: O/'gtj/meshes'/f'R1rep_b10__ALS__tl_own_{n}'/'final.ply'
    if run == 'tl_B0_LoD2_own': return O/'runs/B0_b10/tl_B0_LoD2_own/attempt1/model', lambda n: O/'gtj/meshes'/f'B0_b10__LoD2__tl_own_{n}'/'final.ply'
    if run == 'tlcase': return TLCASE, lambda n: TLC/'gtj/meshes'/f'B0_b10__LoD2__tl_{n}'/'final.ply'
    if run == 'ba3': return A3O/'runs/B0_b10/ba3_B0_ALS_record/attempt1/model', lambda n: A3O/'gtj/meshes'/f'B0_b10__ALS__ba3_{n}'/'final.ply'
    if run == 'tlb173': return TLM/'runs/B173nb_b10/tl_B173nb_b10_ALS_s0/attempt2/model', lambda n: TLM/'gtj/meshes'/f'B173nb_b10__ALS__tl_{n}'/'final.ply'
    return None, None

_MC = {}
def mesh(path):
    if path is None or not Path(path).exists(): return None
    k = str(path)
    if k not in _MC:
        m = o3d.io.read_triangle_mesh(k); _MC.clear(); _MC[k] = (np.asarray(m.vertices, 'f8'), np.asarray(m.triangles, 'i8'))
    return _MC[k]

def frame(X, N, stem, wall):
    tr = cKDTree(X); cnt = np.array([len(q) for q in tr.query_ball_point(X, 1.)]); o = X[int(np.argmax(cnt))]
    if wall:
        h = N[np.abs(N[:, 2]) < .6].mean(0) if (np.abs(N[:, 2]) < .6).any() else N.mean(0); h[2] = 0; h /= np.linalg.norm(h)
        cams = camera_centres(stem); s = np.sign(((cams-o)@h).mean()); h *= s if s != 0 else 1
    else:
        near = X[np.linalg.norm(X[:, :2]-o[:2], axis=1) <= 3.]; q = near[:, :2]-near[:, :2].mean(0); w, Vv = np.linalg.eigh(q.T@q if len(q) > 2 else np.eye(2)); h = np.r_[Vv[:, 0], 0.]
    e = np.cross([0, 0, 1.], h); e /= np.linalg.norm(e); return o, h, e

_CAM = {}
def camera_centres(stem):
    if stem not in _CAM:
        mi = json.loads((maps_dir(stem, 'own')/'index.json').read_text())['views']; c = []
        for m in mi.values():
            M = np.asarray(m['W2C']); c.append(-M[:3, :3].T@M[:3, 3])
        _CAM[stem] = np.array(c)
    return _CAM[stem]

def cut(VF, o, h, e, L, zr):
    if VF is None: return np.zeros((0, 2, 2))
    V, F = VF; rel = V-o; a = rel@h; b = rel@e; z = V[:, 2]
    keepv = (np.abs(a) <= L+1) & (np.abs(b) <= 2) & (z >= zr[0]-1) & (z <= zr[1]+1)
    f = F[keepv[F].all(1)]; db = b[f]; s = np.sign(db); cross = (s.min(1) < 0) & (s.max(1) > 0); f = f[cross]; db = db[cross]; segs = []
    for (i0, i1, i2), d in zip(f, db):
        pts = []
        for (p, q), (dp, dq) in [((i0, i1), (d[0], d[1])), ((i1, i2), (d[1], d[2])), ((i2, i0), (d[2], d[0]))]:
            if (dp < 0) != (dq < 0):
                t = dp/(dp-dq); P = V[p]+t*(V[q]-V[p]); pts.append([(P-o)@h, P[2]])
        if len(pts) == 2: segs.append(pts)
    return np.array(segs) if segs else np.zeros((0, 2, 2))

def disc_segments(T, rows, o, h, e, L, zr, half=.25):
    a = T.anchor[rows]; n = T.normal[rows]; r = T.radius[rows]; d = (a-o)@e; ok = (np.abs(d) < r) & (np.abs((a-o)@h) <= L+1) & (a[:, 2] >= zr[0]-1) & (a[:, 2] <= zr[1]+1)
    segs = []
    for ai, ni, ri, di in zip(a[ok], n[ok], r[ok], d[ok]):
        u = np.cross(e, ni); nu = np.linalg.norm(u)
        if nu < 1e-6: continue
        u /= nu; hl = np.sqrt(max(ri**2-di**2, 0)); c = ai-di*e; p0 = c-hl*u; p1 = c+hl*u; segs.append([[(p0-o)@h, p0[2]], [(p1-o)@h, p1[2]]])
    return np.array(segs) if segs else np.zeros((0, 2, 2))

def load_state(model, name):
    import torch
    p = model/'trainlog/scene'/f'{name}.pt'
    if not p.exists(): return None
    s = torch.load(p, map_location='cpu', weights_only=False)
    return dict(xyz=s['xyz'].double().numpy(), opacity=torch.sigmoid(s['opacity'][:, 0]).numpy(), tag=s['target_tag'].numpy(), tidx=s['target_index'].numpy(), size=torch.exp(s['scaling']).max(1).values.numpy())

def snap_state(stem, it):
    p = model_dir(stem, 'own')/'target_monitor'/f'snapshot_{it}.npz'
    if not p.exists(): return None
    z = loadz(p, ['xyz', 'opacity', 'target_tag', 'target_index', 'scale']); return dict(xyz=z['xyz'].astype('f8'), opacity=z['opacity'], tag=z['target_tag'], tidx=z['target_index'], size=z['scale'].max(1))

def kinds(S, vplace):
    return np.where(S['tag'] == 1, np.where(np.isin(S['tidx'], vplace), 0, 1), np.where(S['tag'] == 2, 2, 3))

# ---------------- cases ----------------
def case_def(name):
    """returns dict: stem, title, X (place points), N (normals), wall, vplace (target rows), run, stages, control (optional points), photo2 (bool), legend for the place."""
    if name in ('floor_band', 'edge_back', 'edge_annex', 'south_wall', 'visible_wall'):
        pls = ['visible_low', 'visible_high'] if name == 'visible_wall' else [name]; Ps = [place_points_cached(p) for p in pls]
        X = np.concatenate([P['xyz'] for P in Ps]); N = np.concatenate([P['out'] for P in Ps]); v = np.unique(np.concatenate([P['v'][P['v'] >= 0] for P in Ps])); stem = Ps[0]['stem']
        run = {'floor_band': 'tl_R1_ALS_own', 'edge_back': 'tl_B0_LoD2_own', 'edge_annex': 'tl_B0_LoD2_own'}.get(name, 'tlcase')
        title = {'floor_band': 'R1 바닥 띠: 목표는 맞는데 학습 뒤 바닥 면이 없어짐', 'edge_back': 'B0 가장자리 띠(뒤쪽 벽 맨 아랫단): 목표는 맞는데 면이 없어짐',
                 'edge_annex': 'B0 가장자리 띠(별채 평지붕 가장자리): 목표는 맞는데 면이 없어짐', 'south_wall': 'B0 남쪽 끝 벽: 벽 뒤에 없는 면이 생김',
                 'visible_wall': 'B0 잘 보이는 벽: 가우시안은 있는데 0~10 m 벽 면이 추출되지 않음'}[name]
        return dict(stem=stem, title=title, X=X, N=N, wall=name != 'floor_band', vplace=v, run=run, photo2=name in ('south_wall', 'visible_wall'), place_label='이 자리(참값 점)')
    if name == 'annex_under':
        VF = mesh(A3O/'gtj/meshes/B0_b10__ALS__ba3_30000/final.ply'); V = VF[0]; b = ANNEX
        inb = (V[:, 0] >= b['x'][0]) & (V[:, 0] <= b['x'][1]) & (V[:, 1] >= b['y'][0]) & (V[:, 1] <= b['y'][1]) & (V[:, 2] >= b['z'][0]) & (V[:, 2] <= b['z'][1])
        G = loadz(GT/'reference/B0_b10/dense.npz', ['xyz']); ii = np.flatnonzero(inb); d, _ = cKDTree(G['xyz'].astype('f8')).query(V[ii]); X = V[ii[d > 1.]]
        X = X[np.random.default_rng(0).choice(len(X), min(len(X), 20000), replace=False)]; v, T, _ = annex_patches('annex_wrong')
        return dict(stem='B0_b10__ALS', title='B0 별채 지붕 아래: 실제로 없는 면이 생김 (항공 LiDAR)', X=X, N=np.tile([0, 0, 1.], (len(X), 1)), wall=False, vplace=v, run='ba3', photo2=False, place_label='틀린 결과 점(참값 1 m 밖)')
    if name == 'floater':
        C = floater_centres('floater'); C = C[np.random.default_rng(0).choice(len(C), min(len(C), 20000), replace=False)]
        return dict(stem='B173nb_b10__ALS', title='B173 가장자리 뜬 면: 건물 윤곽 바깥 0~3 m, 12 m 위 허공에 면이 생김', X=C, N=np.tile([0, 0, 1.], (len(C), 1)), wall=False, vplace=np.zeros(0, 'i8'),
                    run='tlb173', photo2=False, place_label='뜬 면(학습 메시)', oblique=True)
    if name.startswith('fixed_'):
        z = loadz(A4O/'ba'/'fixed_cases.npz'); k = name.split('_', 1)[1]; X = z[f'{k}__xyz']; P = dict(stem='B0_b10__LoD2')
        T = Targets('B0_b10__LoD2'); v = np.unique(T.v_of_rows(gt_row_patch('B0_b10__LoD2')[z[f'{k}__pid']])); v = v[v >= 0]
        ref = a11_ref('B0_b10__LoD2'); lut = {int(p): i for i, p in enumerate(ref['point_id'])}; N = np.array([ref['normal'][lut[int(p)]] for p in z[f'{k}__pid']])
        return dict(stem='B0_b10__LoD2', title=f'B0 × LoD2 학습 뒤 고쳐진 자리 ({str(z[k+"__label"])}): 목표는 틀렸는데 결과 면은 맞음', X=X, N=N, wall=bool(np.mean(np.abs(N[:, 2]) < .5) >= .5), vplace=v, run='tlcase', photo2=False, place_label='고친 점(참값 점)')
    if name.startswith('ma_'):
        _, stem_key, rank = name.split('_', 2); stem = {'R1': 'R1rep_b10__LoD2', 'B173': 'B173nb_b10__LoD2'}[stem_key]; z = loadz(A4O/'ma'/f'{stem}.npz'); m = z['cluster_rank'] == int(rank)
        X = z['xyz'][m].astype('f8'); ref = a11_ref(stem); lut = {int(p): i for i, p in enumerate(ref['point_id'])}; N = np.array([ref['normal'][lut[int(p)]] for p in z['point_id'][m]])
        T = Targets(stem); v = np.unique(T.v_of_rows(gt_row_patch(stem)[z['point_id'][m]])); v = v[v >= 0]
        return dict(stem=stem, title=f'{stem.split("_")[0]} × LoD2 잃은 점 덩어리 {rank}: 판단 메시는 맞는데 학습 뒤 면이 없음', X=X, N=N, wall=bool(z['wall'][m].mean() >= .5), vplace=v, run=None, photo2=False, place_label='잃은 점(참값 점)')
    raise ValueError(name)

def pick_views(stem, X, mode, n=1):
    md = maps_dir(stem, 'own'); mi = json.loads((md/'index.json').read_text())['views']; site = stem.split('__')[0]; sc = []
    Xs = X[np.random.default_rng(1).choice(len(X), min(len(X), 3000), replace=False)]; cen = X.mean(0)
    for nm, m in sorted(mi.items()):
        K = np.asarray(m['K']); M = np.asarray(m['W2C']); Xc = Xs@M[:3, :3].T+M[:3, 3]; z = Xc[:, 2]; okz = z > .2
        u = np.floor(K[0, 0]*Xc[:, 0]/np.where(okz, z, 1)+K[0, 2]).astype('i8'); v = np.floor(K[1, 1]*Xc[:, 1]/np.where(okz, z, 1)+K[1, 2]).astype('i8'); ins = okz & (u >= 20) & (u < 1004) & (v >= 20) & (v < 721)
        if ins.sum() < 20: continue
        if mode in ('visible', 'occluded'):
            mv = np.load(Path('/s0/fork_inputs/s61')/site/'maps/mvs'/f'{nm}.npy'); d = mv[v[ins], u[ins]]; okd = np.isfinite(d) & (d > 0)
            vis = int((okd & (np.abs(d-z[ins]) <= 1.)).sum()); occ = int((okd & (d < z[ins]-1.)).sum())
            span = (np.ptp(u[ins])+np.ptp(v[ins]))
            sc.append((vis*(1+span/500) if mode == 'visible' else occ, nm))
        else:
            c = -M[:3, :3].T@M[:3, 3]; dv = c-cen; el = np.degrees(np.arctan2(dv[2], np.linalg.norm(dv[:2])))
            if 20 <= el <= 60: sc.append((int(ins.sum()), nm))
    sc.sort(reverse=True); return [s[1] for s in sc[:n]]

def photo_panel(ax, cd, view, o, h, L, label):
    from PIL import Image
    stem = cd['stem']; site = stem.split('__')[0]; mi = json.loads((maps_dir(stem, 'own')/'index.json').read_text())['views'][view]; K = np.asarray(mi['K']); M = np.asarray(mi['W2C'])
    im = np.asarray(Image.open(Path('/s0/fork_inputs/s61')/site/'images'/f'{view}.jpg').convert('RGB').resize((1024, 741))).astype('f4')
    def proj(P):
        Pc = P@M[:3, :3].T+M[:3, 3]; return K[0, 0]*Pc[:, 0]/Pc[:, 2]+K[0, 2], K[1, 1]*Pc[:, 1]/Pc[:, 2]+K[1, 2], Pc[:, 2]
    u, v, z = proj(cd['X']); ok = (z > .2) & (u >= 0) & (u < 1024) & (v >= 0) & (v < 741); ov = im.copy()
    ui, vi = u[ok].astype(int), v[ok].astype(int); mask = np.zeros((741, 1024), bool); mask[vi, ui] = True
    from scipy.ndimage import binary_dilation
    mask = binary_dilation(mask, iterations=2); ov[mask] = .5*ov[mask]+.5*np.array([255, 0, 200])
    if ok.any():
        x0, x1 = max(0, int(ui.min())-120), min(1024, int(ui.max())+120); y0, y1 = max(0, int(vi.min())-100), min(741, int(vi.max())+100)
    else: x0, x1, y0, y1 = 0, 1024, 0, 741
    ax.imshow(ov[y0:y1, x0:x1].astype('u1'), extent=(x0, x1, y1, y0)); ax.set_axis_off()
    a, b = o-L*h, o+L*h; ua, va, za = proj(np.array([a, b]))
    if (za > .2).all(): ax.plot(ua, va, '-', color='yellow', lw=2.5, label='단면을 자른 선'); ax.plot(ua, va, '--', color='k', lw=1)
    ax.set_xlim(x0, x1); ax.set_ylim(y1, y0); ax.set_title(label, fontsize=10)
    from matplotlib.patches import Patch
    ax.legend(handles=[Patch(color=(1, 0, .8), label=cd['place_label']), Patch(color='yellow', label='단면을 자른 선')], loc='lower left', fontsize=8, framealpha=.85)

def minimap(fig, rect, cd):
    stem = cd['stem']; G = loadz(GT/'reference'/stem.split('__')[0]/'dense.npz', ['xyz'])['xyz']; c = cd['X'].mean(0)
    G = G[np.random.default_rng(0).choice(len(G), min(len(G), 150000), replace=False)]; m = np.linalg.norm(G[:, :2]-c[:2], axis=1) <= 45; G = G[m]
    ax = fig.add_axes(rect); ax.scatter(G[:, 0], G[:, 1], s=.2, c=G[:, 2], cmap='Greys', lw=0, rasterized=True); ax.scatter(cd['X'][:, 0], cd['X'][:, 1], s=1.5, c='#ff00cc', lw=0)
    ax.set_aspect('equal'); ax.set_xticks([]); ax.set_yticks([]); ax.set_title('위에서 본 자리(분홍)', fontsize=8)
    ax.annotate('북', xy=(.92, .95), xytext=(.92, .78), xycoords='axes fraction', arrowprops=dict(arrowstyle='->'), fontsize=8, ha='center')

def section_axes(ax, cd, o, h, e, L, zr, S=None, VF=None, VF2=None, gt=True, target=True, title='', show_gauss=False):
    stem = cd['stem']; G = loadz(GT/'reference'/stem.split('__')[0]/'dense.npz', ['xyz'])['xyz'].astype('f8'); rel = G-o; m = (np.abs(rel@e) <= .25) & (np.abs(rel@h) <= L) & (G[:, 2] >= zr[0]) & (G[:, 2] <= zr[1])
    if gt: ax.scatter((rel@h)[m], G[m, 2], s=1.2, c='#9e9e9e', lw=0, label='참값', zorder=1, rasterized=True)
    if target:
        T = Targets(stem); rows = np.arange(len(T.anchor)); sg = disc_segments(T, rows, o, h, e, L, zr)
        from matplotlib.collections import LineCollection
        if len(sg): ax.add_collection(LineCollection(sg, colors='#1f4fff', linewidths=2.2, label='목표면', zorder=3))
    from matplotlib.collections import LineCollection
    if VF is not None:
        sg = cut(VF, o, h, e, L, zr)
        if len(sg): ax.add_collection(LineCollection(sg, colors='#e31a1c', linewidths=1.4, label=cd.get('mesh_label', '학습 뒤 표면'), zorder=4))
    if VF2 is not None:
        sg = cut(VF2, o, h, e, L, zr)
        if len(sg): ax.add_collection(LineCollection(sg, colors='#2ca02c', linewidths=1.2, label='사진만 쓴 2DGS 표면', zorder=2))
    if S is not None:
        r2 = S['xyz']-o; mm = (np.abs(r2@e) <= .25) & (np.abs(r2@h) <= L) & (S['xyz'][:, 2] >= zr[0]) & (S['xyz'][:, 2] <= zr[1]); k = kinds(S, cd['vplace'])
        for ki in range(4):
            q = mm & (k == ki)
            if q.any(): ax.scatter((r2@h)[q], S['xyz'][q, 2], s=4+40*S['opacity'][q], c=KCOL[ki], alpha=.75, lw=0, label=f'{KNAME[ki]} {int(q.sum())}', zorder=5)
    pm = (np.abs((cd['X']-o)@e) <= .25) & (np.abs((cd['X']-o)@h) <= L)
    if pm.any() and not show_gauss: ax.scatter(((cd['X']-o)@h)[pm], cd['X'][pm, 2], s=6, c='#ff00cc', lw=0, label=cd['place_label'], zorder=6)
    ax.set_xlim(-L, L); ax.set_ylim(*zr); ax.set_aspect('equal'); ax.set_xlabel('단면 가로 위치 (m)'); ax.set_ylabel('높이 (m, 학습 좌표)')
    ax.annotate('카메라 쪽(바깥) →' if cd['wall'] else '위 = 바깥(카메라 쪽) ↑', xy=(.98, .03), xycoords='axes fraction', ha='right', fontsize=9, bbox=dict(fc='white', ec='k', alpha=.8))
    ax.set_title(title, fontsize=10); ax.grid(alpha=.25)

def window(cd, o, h, e):
    rel = cd['X']-o; L = float(np.clip(np.quantile(np.abs(rel@h), .9)+2, 3, 8)); zc = cd['X'][:, 2]; zr = (float(np.quantile(zc, .05)-2.5), float(np.quantile(zc, .95)+2.5))
    if zr[1]-zr[0] < 6: c_ = sum(zr)/2; zr = (c_-3, c_+3)
    return L, zr

def curve(cd, run):
    model, meshof = run_info(run); rows = []
    if model is not None:
        names = sorted({p.stem for p in (model/'trainlog/scene').glob('*.pt')}, key=lambda n: (int(n.split('_')[0]), 0 if 'pre' in n else 1))
    else: names = ['7000', '15000', '30000']
    tr = cKDTree(cd['X']); stem = cd['stem']
    for n in names:
        S = load_state(model, n) if model is not None else snap_state(stem, n)
        if S is None: continue
        d, _ = tr.query(S['xyz'], distance_upper_bound=.5); near = np.isfinite(d); k = kinds(S, cd['vplace'])
        r = dict(state=n, iteration=int(n.split('_')[0]), bound_place=int(((S['tag'] == 1) & np.isin(S['tidx'], cd['vplace'])).sum()), **{f'near_{i}': int((near & (k == i)).sum()) for i in range(4)},
                 near_opacity_sum=float(S['opacity'][near].sum()))
        mp = meshof(n) if meshof else (final_mesh(stem) if n == '30000' else None); VF = mesh(mp) if mp is not None else None
        if VF is not None: dv, _ = cKDTree(VF[0]).query(cd['X'], distance_upper_bound=.2); r['place_covered_pct'] = pct(np.isfinite(dv))
        rows.append(r)
    return rows

def draw_curve(ax3, rows, cd):
    it = [r['iteration'] for r in rows]
    for i in range(4): ax3[0].plot(it, [r[f'near_{i}'] for r in rows], '-o', ms=2.5, color=KCOL[i], label=KNAME[i])
    ax3[0].set_ylabel('자리 0.5 m 안 가우시안 수'); ax3[0].legend(fontsize=7, loc='upper right')
    ax3[1].plot(it, [r['bound_place'] for r in rows], '-o', ms=2.5, color='#1f77b4', label='이 자리 목표에 묶인 수'); ax3[1].set_ylabel('이 자리 목표에 묶인 수')
    ax3b = ax3[1].twinx(); ax3b.plot(it, [r['near_opacity_sum'] for r in rows], '-', color='#d62728', label='자리 0.5 m 안 불투명도 합'); ax3b.set_ylabel('불투명도 합', color='#d62728')
    q = [(r['iteration'], r['place_covered_pct']) for r in rows if r.get('place_covered_pct') is not None]
    if q: ax3[2].plot(*zip(*q), '-o', color='#e31a1c');
    ax3[2].set_ylabel('자리 점 0.2 m 안에\n학습 메시가 있는 비율 (%)'); ax3[2].set_ylim(-3, 103); ax3[2].set_xlabel('반복 수 (점선: 불투명도 재설정 3,000·6,000·9,000·12,000 / 초록: 7,000 법선 항 / 보라: 15,000 늘리기 끝)')
    for a in ax3:
        for x in [3000, 6000, 9000, 12000]: a.axvline(x, color='k', ls=':', lw=.8)
        a.axvline(7000, color='#009e73', ls='--', lw=1); a.axvline(15000, color='#7b3294', ls='--', lw=1); a.grid(alpha=.3)

def make(name):
    t0 = time.monotonic(); plt = korean_plt(); FIG.mkdir(parents=True, exist_ok=True); cd = case_def(name); stem = cd['stem']; o, h, e = frame(cd['X'], cd['N'], stem, cd['wall']); L, zr = window(cd, o, h, e)
    model, meshof = run_info(cd['run']); final_p = meshof('30000') if meshof else final_mesh(stem); VF = mesh(final_p); VF2 = mesh(twodgs_mesh(stem)); src = dict(final_mesh=str(final_p), photo_only_2dgs=str(twodgs_mesh(stem)), model=str(model) if model else str(model_dir(stem, 'own')))
    # 1 photo
    views = pick_views(stem, cd['X'], 'oblique' if cd.get('oblique') else 'visible'); occ = pick_views(stem, cd['X'], 'occluded') if cd['photo2'] else []
    ncol = 2 if occ else 1; fig = plt.figure(figsize=(9*ncol, 7.5)); axs = [fig.add_axes([0.02+i/ncol, .02, 1/ncol-.04, .9]) for i in range(ncol)]
    photo_panel(axs[0], cd, views[0], o, h, L, f'자리가 가장 잘 보이는 영상 ({views[0][-9:-2]})' if not cd.get('oblique') else f'비스듬히 본 영상 ({views[0][-9:-2]})')
    if occ: photo_panel(axs[1], cd, occ[0], o, h, L, f'벽 앞을 다른 물체가 가린 영상 ({occ[0][-9:-2]}): 영상 깊이가 목표보다 1 m 넘게 앞')
    minimap(fig, [0.80 if ncol == 1 else .88, .66, .17 if ncol == 1 else .1, .28], cd); fig.suptitle(cd['title'], fontsize=12)
    fig.savefig(FIG/f'ba_{name}_photo.png', dpi=100, bbox_inches='tight'); plt.close(fig); dump(FIG/f'ba_{name}_photo.json', dict(at=now(), views=views+occ, rule='pick_views: most place points with image depth within 1 m (visible), most with image depth > 1 m in front (occluded), elevation 20-60 deg (oblique)', **src, scientific_verdict=None))
    # 2 section
    w_ = 2*L; hgt = zr[1]-zr[0]; sc_ = 10/max(w_, hgt); fig, ax = plt.subplots(figsize=(max(6, w_*sc_+2), max(5, hgt*sc_+1.5)))
    cd['mesh_label'] = '30,000회 학습 표면'; section_axes(ax, cd, o, h, e, L, zr, VF=VF, VF2=VF2, title=cd['title']); ax.legend(loc='upper left', fontsize=8, framealpha=.9)
    fig.tight_layout(); fig.savefig(FIG/f'ba_{name}_section.png', dpi=110, bbox_inches='tight'); plt.close(fig); dump(FIG/f'ba_{name}_section.json', dict(at=now(), origin=o.tolist(), h=h.tolist(), slab_m=.25, **src, scientific_verdict=None))
    # 3 stages
    stages = STAGES if model is not None else ['7000', '15000', '30000']
    fig, axes = plt.subplots(2, 3, figsize=(18, 11)) if len(stages) == 6 else plt.subplots(1, 3, figsize=(18, 6)); axes = np.atleast_1d(axes).ravel()
    for ax, st in zip(axes, stages):
        S = load_state(model, st) if model is not None else snap_state(stem, st); mp = meshof(st) if meshof else (final_mesh(stem) if st == '30000' else None); VFs = mesh(mp) if mp else None
        cd['mesh_label'] = '그 단계의 학습 표면'; section_axes(ax, cd, o, h, e, L, zr, S=S, VF=VFs, gt=True, title=STAGE_KO[st]+('' if VFs is not None else ' (이 단계 메시 없음)'), show_gauss=True)
        ax.legend(loc='upper left', fontsize=6.5, framealpha=.85)
    fig.suptitle(cd['title']+'\n점 = 가우시안 중심(색 = 종류, 크기 = 불투명도), 파랑 = 목표면, 빨강 = 그 단계 표면', fontsize=11); fig.tight_layout()
    fig.savefig(FIG/f'ba_{name}_stages.png', dpi=90, bbox_inches='tight'); plt.close(fig); dump(FIG/f'ba_{name}_stages.json', dict(at=now(), stages=stages, **src, scientific_verdict=None))
    # 4 curve
    rows = curve(cd, cd['run']); fig, ax3 = plt.subplots(3, 1, figsize=(11, 10), sharex=True); draw_curve(ax3, rows, cd); fig.suptitle(cd['title'], fontsize=11); fig.tight_layout()
    fig.savefig(FIG/f'ba_{name}_curve.png', dpi=100); plt.close(fig); dump(FIG/f'ba_{name}_curve.json', dict(at=now(), rows=rows, **src, scientific_verdict=None))
    summary(name); print('BA', name, round(time.monotonic()-t0), flush=True)

def summary(name):
    """2 x 2 grid, each part scaled to fit (contain) a 900 x 760 px cell; width 1800 px."""
    from PIL import Image, ImageDraw
    ims = [Image.open(FIG/f'ba_{name}_{k}.png').convert('RGB') for k in ['photo', 'section', 'stages', 'curve']]; CW, CH = 900, 760
    out = Image.new('RGB', (2*CW, 2*CH), 'white')
    for i, im in enumerate(ims):
        s_ = min(CW/im.width, CH/im.height); im2 = im.resize((max(1, int(im.width*s_)), max(1, int(im.height*s_)))); x0 = (i % 2)*CW+(CW-im2.width)//2; y0 = (i//2)*CH+(CH-im2.height)//2; out.paste(im2, (x0, y0))
    d = ImageDraw.Draw(out); d.line([(CW, 0), (CW, 2*CH)], fill=(200, 200, 200), width=2); d.line([(0, CH), (2*CW, CH)], fill=(200, 200, 200), width=2); out.save(FIG/f'ba_{name}_summary.png')
    dump(FIG/f'ba_{name}_summary.json', dict(at=now(), parts=[f'ba_{name}_{k}.png' for k in ['photo', 'section', 'stages', 'curve']], width_px=2*CW, scientific_verdict=None))

if __name__ == '__main__':
    for n in sys.argv[2:]: summary(n) if sys.argv[1] == 'summary' else make(n)
