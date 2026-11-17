"""Work ba (order 8): one figure per case, each showing one sentence (title), with arrows; GT gray, target blue, surface red (at most three line kinds);
equal x/z scale; place >= 1/4 of the width; >= 1,600 px wide; json source + npz point data per figure. CPU image (open3d, torch), except 'rays' (GPU).
  rays          : GPU, B0 south wall: three representative pixels of the behind-wall pixels (TRAINLOG record 30,000): splat weight along the ray -> addendum5/ba/rays_south.npz
  case <name>.. : figures/bb_<name>.png + .json, payload addendum5/ba/bb_<name>.npz
Cases: edge_back, edge_annex, annex_under, south_wall, visible_wall, fixed, floater, r1_lod2_wall1."""
import sys, time
sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1/addendum5'); sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1/addendum4')
from a5_common import *
BA5 = A5O/'ba'; FIG5 = A5D/'figures'
GRAY, BLUE, RED = '#8c8c8c', '#1f4fff', '#e31a1c'
KCOL = ['#1f77b4', '#9467bd', '#ff7f0e', '#4d4d4d']

def B():
    import a4_ba; return a4_ba

def save(name, fig, src, pts):
    FIG5.mkdir(parents=True, exist_ok=True); BA5.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG5/f'bb_{name}.png', dpi=160, bbox_inches='tight', pad_inches=.3)
    from PIL import Image; W = Image.open(FIG5/f'bb_{name}.png').width
    import matplotlib.pyplot as plt; plt.close(fig)
    dump(FIG5/f'bb_{name}.json', dict(at=now(), figure=f'bb_{name}.png', width_px=W, points_npz=f'payload addendum5/ba/bb_{name}.npz', **src, scientific_verdict=None))
    savez(BA5/f'bb_{name}.npz', **{k: np.asarray(v) for k, v in pts.items()}); print('BB', name, W, flush=True)

def sec_lines(ax, stem, o, h, e, L, zr, VF, slab=.25, gt=True, target=True, lw=1.8):
    b = B(); from matplotlib.collections import LineCollection; out = {}
    if gt:
        G = loadz(GT/'reference'/stem.split('__')[0]/'dense.npz', ['xyz'])['xyz'].astype('f8'); rel = G-o
        m = (np.abs(rel@e) <= slab) & (np.abs(rel@h) <= L) & (G[:, 2] >= zr[0]) & (G[:, 2] <= zr[1]); ax.scatter((rel@h)[m], G[m, 2], s=2, c=GRAY, lw=0, label='참값', zorder=1, rasterized=True)
        out['gt_h'] = (rel@h)[m]; out['gt_z'] = G[m, 2]
    if target:
        T = Targets(stem); sg = b.disc_segments(T, np.arange(len(T.anchor)), o, h, e, L, zr)
        if len(sg): ax.add_collection(LineCollection(sg, colors=BLUE, linewidths=2.6, label='목표면', zorder=3))
        out['target_segments'] = sg
    if VF is not None:
        sg = b.cut(VF, o, h, e, L, zr)
        if len(sg): ax.add_collection(LineCollection(sg, colors=RED, linewidths=lw, label='학습 뒤 표면', zorder=4))
        out['surface_segments'] = sg
    ax.set_xlim(-L, L); ax.set_ylim(*zr); ax.set_aspect('equal'); ax.grid(alpha=.25); return out

def axis_labels(ax, wall):
    ax.set_xlabel('단면 가로 위치 (m)' + ('  → 카메라 쪽(바깥)' if wall else '')); ax.set_ylabel('높이 (m)')

def arrow(ax, xy, text, dxy=(.6, .6), color='k'):
    ax.annotate(text, xy=xy, xytext=(xy[0]+dxy[0], xy[1]+dxy[1]), arrowprops=dict(arrowstyle='->', color=color, lw=1.8), fontsize=12, color=color, weight='bold',
                bbox=dict(fc='white', ec=color, alpha=.9))

def frame_of(cd):
    b = B(); return b.frame(cd['X'], cd['N'], cd['stem'], cd['wall'])

# ---------------- cases ----------------
def edge_back():
    b = B(); plt = korean_plt(); cd = b.case_def('edge_back'); o, h, e = frame_of(cd); L = 1.; zr = (o[2]-1., o[2]+1.)
    mp = O/'gtj/meshes/B0_b10__LoD2__tl_own_30000/final.ply'; VF = b.mesh(mp)
    fig, ax = plt.subplots(figsize=(13, 13)); pts = sec_lines(ax, cd['stem'], o, h, e, L, zr, VF)
    rel = cd['X']-o; pm = (np.abs(rel@e) <= .25) & (np.abs(rel@h) <= L); px, pz = (rel@h)[pm], cd['X'][pm, 2]
    if len(px): arrow(ax, (float(np.median(px)), float(np.median(pz))), '이 자리: 벽이 바닥과 만나는 곳', (.35, -.55))
    ax.legend(loc='upper left', fontsize=12); axis_labels(ax, True)
    fig.suptitle('벽이 바닥과 만나는 자리에 목표면은 있는데, 학습 뒤 표면은 그 위에서 끝난다', fontsize=17, weight='bold')
    ax.set_title('B0 × LoD2 뒤쪽 벽 맨 아랫단, 본 방법을 다시 학습한 판 30,000회, 단면 두께 ±0.25 m, 가로 2 m × 세로 2 m', fontsize=11)
    save('edge_back', fig, dict(case='edge_back', mesh=str(mp), origin=o.tolist(), h=h.tolist(), e=e.tolist(), window_m=[2*L, zr[1]-zr[0]]), dict(place_h=px, place_z=pz, **pts))

def edge_annex():
    b = B(); plt = korean_plt(); cd = b.case_def('edge_annex'); o, h, e = frame_of(cd); L = 1.0; zr = (o[2]-1.0, o[2]+1.0)
    runs = [('학습 1 (본 결과)', b.final_mesh('B0_b10__LoD2')), ('학습 2', O/'gtj/meshes/B0_b10__LoD2__tl_own_30000/final.ply'),
            ('학습 3', TLC/'gtj/meshes/B0_b10__LoD2__tl_30000/final.ply'), ('학습 4', A5O/'gtj/meshes/B0_b10__LoD2__sc4_30000/final.ply')]
    RUNKEY = {'학습 1 (본 결과)': 'FINALTRAIN', '학습 2': 'TRAINERR tl_B0_LoD2_own', '학습 3': 'TRAINLOG tl_B0_b10_LoD2_s0', '학습 4': 'addendum5 sc4_B0_LoD2_signed'}
    runs = [(n, p) for n, p in runs if Path(p).exists()]
    fig, axs = plt.subplots(1, len(runs), figsize=(max(16, 5.2*len(runs)), 6.8)); axs = np.atleast_1d(axs); pts = {}
    rel = cd['X']-o; pm = (np.abs(rel@e) <= .25) & (np.abs(rel@h) <= L); px = (rel@h)[pm]; lo_, hi_ = (float(px.min()), float(px.max())) if len(px) else (-.2, .2)
    for i, (ax, (nm, p)) in enumerate(zip(axs, runs)):
        VF = b.mesh(p); q = sec_lines(ax, 'B0_b10__LoD2', o, h, e, L, zr, VF); ax.axvspan(lo_, hi_, color='#ffd400', alpha=.35, zorder=0, label='이 자리')
        cov = None
        if VF is not None:
            dv, _ = cKDTree(VF[0]).query(cd['X'], distance_upper_bound=.2); cov = pct(np.isfinite(dv))
        ax.set_title(f'{nm}\n자리 점 0.2 m 안 표면 {cov:.0f} %' if cov is not None else nm, fontsize=12); axis_labels(ax, True)
        pts.update({f'run{i}__{k}': v for k, v in q.items()}); pts[f'run{i}__coverage_pct'] = np.float64(cov if cov is not None else np.nan)
        ax.annotate('이 자리', xy=((lo_+hi_)/2, zr[0]+.15*(zr[1]-zr[0])), xytext=((lo_+hi_)/2-.75, zr[0]+.05*(zr[1]-zr[0])), arrowprops=dict(arrowstyle='->', lw=1.8), fontsize=12, weight='bold', bbox=dict(fc='white', ec='k'))
        if i == 0: ax.legend(loc='upper left', fontsize=10)
    fig.suptitle('같은 설정의 학습에서 별채 평지붕 가장자리의 표면이 있기도 하고 없기도 하다', fontsize=17, weight='bold'); fig.tight_layout(rect=(0, 0, 1, .92))
    save('edge_annex', fig, dict(case='edge_annex', meshes={n: str(p) for n, p in runs}, run_names={n: RUNKEY[n] for n, _ in runs}, place_width_share=float((hi_-lo_)/(2*L)), origin=o.tolist(), h=h.tolist(), note='같은 설정 30,000회 메시가 있는 판은 넷(issues.md)'), dict(place_lo_hi=np.array([lo_, hi_]), **pts))

def disk_segments(S, rows, o, h, e, L, zr, k=2.):
    """2DGS disks of the given rows cut by the section plane (normal e): segment along d = n x e, half length k * radius of the ellipse along d."""
    import torch
    from scipy.spatial.transform import Rotation as Rr
    q = S['rotation'][rows].numpy(); q = q/np.linalg.norm(q, axis=1, keepdims=True); R = Rr.from_quat(q[:, [1, 2, 3, 0]]).as_matrix(); sc = np.exp(S['scaling'][rows].numpy())
    X = S['xyz'][rows].double().numpy(); segs = []; keep = []
    for i in range(len(rows)):
        t1, t2, n = R[i][:, 0], R[i][:, 1], R[i][:, 2]; d = np.cross(n, e); nd = np.linalg.norm(d)
        if nd < 1e-6: continue
        d /= nd; r = 1/np.sqrt((d@t1/sc[i, 0])**2+(d@t2/sc[i, 1])**2); p0 = X[i]-k*r*d; p1 = X[i]+k*r*d
        segs.append([[(p0-o)@h, p0[2]], [(p1-o)@h, p1[2]]]); keep.append(i)
    return np.array(segs) if segs else np.zeros((0, 2, 2)), np.array(keep, 'i8')

def disc_segments_slab(T, o, h, e, L, zr, slab):
    """target discs passing through the section slab |d| <= slab, drawn as their chord at the plane nearest to the disc centre (same slab as the GT points)."""
    a = T.anchor; n = T.normal; r = T.radius; d = (a-o)@e; ok = (np.abs(d) < r+slab) & (np.abs((a-o)@h) <= L+1) & (a[:, 2] >= zr[0]-1) & (a[:, 2] <= zr[1]+1); segs = []
    for ai, ni, ri, di in zip(a[ok], n[ok], r[ok], d[ok]):
        u = np.cross(e, ni); nu = np.linalg.norm(u)
        if nu < 1e-6: continue
        u /= nu; dd = max(abs(di)-slab, 0.); hl = np.sqrt(max(ri**2-dd**2, 0)); c = ai-di*e; p0 = c-hl*u; p1 = c+hl*u; segs.append([[(p0-o)@h, p0[2]], [(p1-o)@h, p1[2]]])
    return np.array(segs) if segs else np.zeros((0, 2, 2))

def annex_under():
    b = B(); plt = korean_plt(); cd = b.case_def('annex_under'); import torch
    S = torch.load(RUNS4['ba3_B0_ALS_record']['model']/'trainlog/scene/30000.pt', map_location='cpu', weights_only=False)
    g = loadz(A5O/'pix/group_ba3_B0_ALS_record_annex_30000.npz'); rows = g['problem__row']; W_ = g['problem__weight_sum']
    X = S['xyz'].double().numpy()[rows]; c = np.average(X, axis=0, weights=W_); N = np.tile([0, 0, 1.], (len(cd['X']), 1))
    # section: the addendum-4 annex_under section frame (figures/ba_annex_under_section.json of addendum 4), widened to the roof and the ground
    fr = json.loads((A4D/'figures/ba_annex_under_section.json').read_text()); o = np.asarray(fr['origin']); h = np.asarray(fr['h']); e = np.cross([0, 0, 1.], h); e /= np.linalg.norm(e)
    L = 6.; zr = (-44., -32.)
    VF = b.mesh(A3O/'gtj/meshes/B0_b10__ALS__ba3_30000/final.ply')
    fig, ax = plt.subplots(figsize=(16, 11)); pts = sec_lines(ax, 'B0_b10__ALS', o, h, e, L, zr, VF, target=False)
    T = Targets('B0_b10__ALS'); tsg = disc_segments_slab(T, o, h, e, L, zr, .25)
    from matplotlib.collections import LineCollection
    if len(tsg): ax.add_collection(LineCollection(tsg, colors=BLUE, linewidths=2.6, label='목표면', zorder=3))
    pts['target_segments'] = tsg; print('ANNEX_TARGET_SEGMENTS', len(tsg), flush=True)
    rel = X-o; near = (np.abs(rel@e) <= 1.5) & (np.abs(rel@h) <= L) & (X[:, 2] >= zr[0]) & (X[:, 2] <= zr[1]); sg, kk = disk_segments(S, rows[near], o, h, e, L, zr)
    from matplotlib.collections import LineCollection
    if len(sg): ax.add_collection(LineCollection(sg, colors='#ff7f0e', linewidths=4, alpha=.8, label=f'틀린 면을 그리는 가우시안의 원판 (2σ, 단면 ±1.5 m 안 {len(sg)}개)', zorder=5))
    ax.scatter((rel@h)[near], X[near, 2], s=30, c='#ff7f0e', edgecolors='k', zorder=6)
    sz = np.exp(S['scaling'][rows].numpy()).max(1)
    if len(sg): arrow(ax, tuple(sg[int(np.argmax(np.linalg.norm(sg[:, 1]-sg[:, 0], axis=1)))].mean(0)), f'비스듬한 틀린 면: 큰 가우시안 {len(rows)}개\n(최대 크기 중앙값 {np.median(sz):.2f} m)', (-4.2, -4.6))
    ax.legend(loc='upper left', fontsize=11); ax.set_xlabel('단면 가로 위치 (m)  → 카메라 쪽(바깥)'); ax.set_ylabel('높이 (m)')
    fig.suptitle('지붕은 맞는데, 지붕 가장자리에서 아래 바닥까지 비스듬한 면이 하나 더 있고, 그 면은 큰 가우시안 몇 개의 원판이다', fontsize=16, weight='bold')
    ax.set_title('B0 × 항공 LiDAR 별채, 기록을 더한 학습 30,000회, 단면 두께 ±0.25 m (목표면은 그 두께를 지나는 원판, 가우시안 원판은 ±1.5 m 안)', fontsize=11)
    save('annex_under', fig, dict(case='annex_under', model=str(RUNS4['ba3_B0_ALS_record']['model']), group='pixel group (addendum4 work da 4.3 pixels)', origin=o.tolist(), h=h.tolist(), e=e.tolist()),
         dict(disk_segments=sg, gauss_h=(rel@h)[near], gauss_z=X[near, 2], gauss_size=sz, **pts))

def rays():
    """GPU: three behind-wall pixels with the largest wall and behind weight both > 0.2 (record 30,000): every splat on the ray."""
    import torch
    import a4_da as D4
    camera = D4.gpu_setup(); z = loadz(A5O/'pix/pixels_south.npz'); names = [str(x) for x in z['view_names']]; md, mi = D4.views_of('B0_b10__LoD2')
    S = D4.load_pt(TLC/'runs/B0_b10/tl_B0_b10_LoD2_s0/attempt1/model', '30000'); out = {}; cands = []
    with torch.no_grad():
        g = D4.gmodel(S); view = z['problem__view']; sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1/addendum1'); import a1_common as A1
        for j in np.unique(view):
            sel = np.flatnonzero(view == j); nm = names[j]; mm = mi[nm]
            with np.load(md/mm['file']) as zz: H, W = zz['owner'].shape; td = zz['depth']
            C = D4.contrib(g, camera(W, H, np.asarray(mm['K']), np.asarray(mm['W2C']), nm), z['problem__u'][sel], z['problem__v'][sel], wmin=1e-5)
            if not len(C): continue
            acc, mean, medd = D4.per_pixel(C, len(sel))
            for k in range(len(sel)):
                c = C[C[:, 0] == k]; zp = z['problem__zpt'][sel[k]]; wf = c[np.abs(c[:, 3]-zp) <= .5, 2].sum()   # weight at the behind-face depth +- 0.5 m
                cands.append((wf, j, sel[k], c, mean[k], medd[k], float(td[z['problem__v'][sel[k]], z['problem__u'][sel[k]]]), zp))
    # representative = the pixels at the 25 / 50 / 75 % quantiles of the weight at the behind-face depth (no selection towards either reading)
    cands.sort(key=lambda t: t[0]); top = [cands[int(q*(len(cands)-1))] for q in (.25, .5, .75)]
    for i, (sc, j, s, c, mn, mdd, tdv, zp) in enumerate(top):
        out.update({f'p{i}__depth': c[:, 3], f'p{i}__weight': c[:, 2], f'p{i}__tag': S['target_tag'].numpy()[c[:, 1].astype('i8')], f'p{i}__mean': np.float64(mn), f'p{i}__median': np.float64(mdd),
                    f'p{i}__target': np.float64(tdv), f'p{i}__behind_point': np.float64(zp), f'p{i}__view': np.array(names[j]), f'p{i}__uv': np.array([z['problem__u'][s], z['problem__v'][s]])})
    BA5.mkdir(parents=True, exist_ok=True); savez(BA5/'rays_south.npz', **out); print('RAYS', len(top), flush=True)

def south_wall():
    plt = korean_plt(); z = loadz(BA5/'rays_south.npz'); n = len([k for k in z if k.endswith('__mean')])
    fig, axs = plt.subplots(n, 1, figsize=(16, 4.2*n), sharex=False); axs = np.atleast_1d(axs); pts = {}
    for i, ax in enumerate(axs):
        d = z[f'p{i}__depth']; w = z[f'p{i}__weight']; t = z[f'p{i}__target']; m = float(z[f'p{i}__mean']); md = float(z[f'p{i}__median']); bp = float(z[f'p{i}__behind_point'])
        lo, hi = min(t, m, md, bp)-3, max(t, m, md, bp)+3; sel = (d >= lo) & (d <= hi); bins = np.arange(lo, hi+.1, .1); hst, _ = np.histogram(d[sel], bins, weights=w[sel])
        ax.bar(bins[:-1]+.05, hst, width=.09, color='#7f7f7f', label='시선 위 가우시안 무게(0.1 m 칸 합)')
        ax.axvline(t, color=BLUE, lw=2.5, label=f'목표 깊이 {t:.2f} m'); ax.axvline(m, color=RED, lw=2.5, label=f'평균 깊이(메시에 쓰임) {m:.2f} m'); ax.axvline(md, color='k', lw=2, ls='--', label=f'중앙 깊이 {md:.2f} m')
        ax.annotate('벽 뒤로 튀어나온 면의 자리', xy=(bp, max(hst.max()*.05, 1e-3)), xytext=(bp+.8, hst.max()*.6), arrowprops=dict(arrowstyle='->', lw=1.8), fontsize=12, weight='bold', bbox=dict(fc='white', ec='k'))
        wf = float(w[np.abs(d-bp) <= .5].sum())
        ax.set_xlim(lo, hi); ax.set_ylabel('무게 αT'); ax.set_xlabel('카메라에서 깊이 (m)  → 벽 뒤'); ax.legend(loc='upper left', fontsize=10); ax.grid(alpha=.3)
        ax.set_title(f'대표 화소 {i+1} (영상 {str(z[f"p{i}__view"])[-9:-2]}): 튀어나온 면 깊이 ±0.5 m의 무게 {wf:.2f} ({["25","50","75"][i]} % 분위 화소)', fontsize=12)
        pts.update({f'p{i}__bin_left': bins[:-1], f'p{i}__bin_weight': hst})
    fig.suptitle('벽 뒤로 튀어나온 면의 자리에는 가우시안이 거의 없고, 벽의 가우시안과 그 뒤 가우시안 사이에 평균 깊이가 놓인다', fontsize=16, weight='bold')
    fig.text(.5, .93, '(대표 화소는 튀어나온 면 깊이 ±0.5 m 무게의 25·50·75 % 분위 화소, 앞 분석에서 고른 화소 635개 가운데)', ha='center', fontsize=11, color='#444'); fig.tight_layout(rect=(0, 0, 1, .91))
    save('south_wall', fig, dict(case='south_wall', model='TRAINLOG 기록 판 30,000회', pixels='payload addendum5/ba/rays_south.npz (튀어나온 면 깊이 ±0.5 m 무게의 25·50·75 % 분위 화소 셋)'), pts)

def visible_wall():
    b = B(); plt = korean_plt(); cd = b.case_def('visible_wall'); o, h, e = frame_of(cd); L, zr = b.window(cd, o, h, e); L = min(L, 4.)
    runs = [('본 방법', TLC/'gtj/meshes/B0_b10__LoD2__tl_30000/final.ply'), ('가려진 화소의 깊이 감독을 끈 학습', A4O/'gtj/meshes/B0_b10__LoD2__sa2_30000/final.ply')]
    fig = plt.figure(figsize=(16, 15)); pts = {}
    for i, (nm, p) in enumerate(runs):
        ax = fig.add_axes([.06+i*.48, .42, .42, .5]); q = sec_lines(ax, 'B0_b10__LoD2', o, h, e, L, zr, b.mesh(p)); axis_labels(ax, True)
        VF = b.mesh(p); dv, _ = cKDTree(VF[0]).query(cd['X'], distance_upper_bound=.2) if VF is not None else (np.full(len(cd['X']), np.inf), None)
        ax.set_title(f'{nm}, 30,000회\n벽 0~10 m 참값 점 0.2 m 안 표면 {pct(np.isfinite(dv)):.0f} %', fontsize=12); pts.update({f'run{i}__{k}': v for k, v in q.items()})
        if i == 0: ax.legend(loc='upper left', fontsize=10)
        rel = cd['X']-o; pm = (np.abs(rel@e) <= .25) & (np.abs(rel@h) <= L)
        if pm.any(): arrow(ax, (float(np.median((rel@h)[pm])), float(np.quantile(cd['X'][pm, 2], .3))), '벽', (1., .8))
    occ = b.pick_views('B0_b10__LoD2', cd['X'], 'occluded'); ax = fig.add_axes([.2, .02, .6, .36]); b.photo_panel(ax, cd, occ[0], o, h, L, f'벽 앞을 다른 물체가 가린 영상 ({occ[0][-9:-2]})')
    fig.suptitle('가려진 화소의 깊이 감독을 끈 학습에서는 벽을 따라 표면이 있고, 본 방법에서는 없다', fontsize=17, weight='bold')
    save('visible_wall', fig, dict(case='visible_wall', meshes={n: str(p) for n, p in runs}, photo=occ[0], origin=o.tolist(), h=h.tolist()), pts)

def fixed():
    b = B(); plt = korean_plt(); import torch; z = loadz(A4O/'ba/fixed_cases.npz'); k = 'a'; X = z[f'{k}__xyz'].astype('f8'); stem = 'B0_b10__LoD2'
    T = Targets(stem); vfix = np.unique(T.v_of_rows(gt_row_patch(stem)[z[f'{k}__pid']])); vfix = vfix[vfix >= 0]
    S = torch.load(TLC/'runs/B0_b10/tl_B0_b10_LoD2_s0/attempt1/model/trainlog/scene/30000.pt', map_location='cpu', weights_only=False); G = S['xyz'].double().numpy()
    d, _ = cKDTree(X).query(G, distance_upper_bound=.2); near = np.isfinite(d); tag = S['target_tag'].numpy(); ti = S['target_index'].numpy()
    cls = np.where(tag == 1, np.where(np.isin(ti, vfix), 0, 1), 2); c = X.mean(0); R = float(np.clip(np.ptp(X[:, :2], 0).max()/2+2, 3, 12))
    A = T.anchor; win = np.all(np.abs(A[:, :2]-c[:2]) <= R, 1); fig, ax = plt.subplots(figsize=(16, 14))
    from matplotlib.patches import Circle
    for i in np.flatnonzero(win):
        ax.add_patch(Circle(A[i, :2], T.radius[i], fc=('#fdb3b3' if i in set(vfix.tolist()) else '#bfe5bf'), ec='none', alpha=.7, zorder=1))
    ax.scatter(X[:, 0], X[:, 1], s=4, c=GRAY, lw=0, label='고친 점(참값 점)', zorder=2)
    col = ['#d62728', '#2ca02c', '#4d4d4d']; lab = ['틀린 목표에 묶인 가우시안', '옆의 맞는 목표에 묶인 가우시안', '풀린 것·묶이지 않은 것']
    for q in range(3):
        m = near & (cls == q)
        if m.any(): ax.scatter(G[m, 0], G[m, 1], s=18, c=col[q], edgecolors='k', lw=.3, label=f'{lab[q]} {int(m.sum())}', zorder=3)
    from matplotlib.patches import Patch
    h_, l_ = ax.get_legend_handles_labels(); h_ += [Patch(color='#fdb3b3', label='틀린 목표 조각'), Patch(color='#bfe5bf', label='이웃의 맞는 목표 조각')]
    ax.legend(handles=h_, loc='upper left', fontsize=11); ax.set_xlim(c[0]-R, c[0]+R); ax.set_ylim(c[1]-R, c[1]+R); ax.set_aspect('equal'); ax.set_xlabel('x (m, 학습 좌표)'); ax.set_ylabel('y (m)  ↑ 북'); ax.grid(alpha=.25)
    m1 = near & (cls == 1)
    if m1.any(): arrow(ax, tuple(G[m1, :2].mean(0)), '표면을 그리는 것은\n옆 목표에 묶인 가우시안', (R*.3, R*.3))
    fig.suptitle('틀린 목표면에서 떨어진 실제 면에, 옆의 맞는 목표에 묶인 가우시안이 놓여 표면을 만든다', fontsize=17, weight='bold')
    ax.set_title(f'B0 × LoD2 학습 후 고쳐진 자리 ({str(z[k+"__label"])}), 30,000회, 위에서 본 그림, 고친 점 0.2 m 안 가우시안', fontsize=11)
    save('fixed', fig, dict(case='fixed_a', model='TRAINLOG 기록 판 30,000회', rule='가우시안 중심이 고친 점 0.2 m 안'), dict(points=X, gauss_xyz=G[near], gauss_class=cls[near], wrong_patches=vfix))

def floater():
    b = B(); plt = korean_plt(); import torch; C = floater_centres('floater'); stem = 'B173nb_b10__ALS'; model = TLM/'runs/B173nb_b10/tl_B173nb_b10_ALS_s0/attempt2/model'
    tr = cKDTree(C); names = sorted({p.stem for p in (model/'trainlog/scene').glob('*.pt')}, key=lambda n: (int(n.split('_')[0]), 0 if 'pre' in n else 1)); its, cnt = [], []
    for n in names:
        s = torch.load(model/'trainlog/scene'/f'{n}.pt', map_location='cpu', weights_only=False); d, _ = tr.query(s['xyz'].double().numpy(), distance_upper_bound=.5); its.append(int(n.split('_')[0])); cnt.append(int(np.isfinite(d).sum()))
    # vertical section across the densest floater part, perpendicular to the nearest building wall
    G = loadz(GT/'reference/B173nb_b10/dense.npz', ['xyz', 'wall']); Gw = G['xyz'][G['wall'].astype(bool)].astype('f8')
    tc = cKDTree(C); cnt_ = np.array([len(q) for q in tc.query_ball_point(C, 1.)]); o = C[int(np.argmax(cnt_))]
    _, j = cKDTree(Gw[:, :2]).query(o[:2]); hvec = np.r_[o[:2]-Gw[j, :2], 0.]; hvec /= max(np.linalg.norm(hvec), 1e-9); e = np.cross([0, 0, 1.], hvec)
    L = 6.; zr = (o[2]-8., o[2]+3.); VF = b.mesh(TLM/'gtj/meshes'/'B173nb_b10__ALS__tl_30000'/'final.ply')
    fig = plt.figure(figsize=(18, 10)); ax = fig.add_axes([.05, .08, .55, .82]); pts = sec_lines(ax, stem, o-0*hvec, hvec, e, L, zr, VF)
    wl = (Gw[j]-o)@hvec; ax.axvline(wl, color='k', ls='--', lw=1.5); arrow(ax, (wl, o[2]-5.5), '건물 벽 자리(참값 벽 점에서 가장 가까운 곳)', (1.2, -1.2)); arrow(ax, (0., o[2]), '허공에 세로로 선 면', (1.5, 1.2))
    ax.legend(loc='upper left', fontsize=11); ax.set_xlabel('벽에 수직인 가로 위치 (m)  → 건물 바깥'); ax.set_ylabel('높이 (m)')
    ax2 = fig.add_axes([.67, .15, .3, .7]); ax2.plot(its, cnt, '-o', ms=3, color='#ff7f0e'); ax2.axvline(15000, color='#7b3294', ls='--'); ax2.text(15200, max(cnt)*.9, '15,000회\n늘리기 끝', fontsize=11)
    ax2.set_xlabel('반복 수'); ax2.set_ylabel('뜬 면 0.5 m 안 가우시안 수'); ax2.grid(alpha=.3)
    fig.suptitle('건물 벽 바깥 허공에 세로로 선 면이 있고, 그 면의 가우시안은 15,000회까지 계속 늘어난다', fontsize=17, weight='bold')
    save('floater', fig, dict(case='floater', model='TRAINLOG B173 × 항공 LiDAR 기록 판', origin=o.tolist(), h=hvec.tolist()), dict(iteration=np.array(its), count=np.array(cnt), **pts))

def r1_lod2_wall1():
    b = B(); plt = korean_plt(); import torch; cd = b.case_def('ma_R1_1'); o, h, e = frame_of(cd); L, zr = b.window(cd, o, h, e); L = min(L, 5.)
    P = place_points5('r1_lod2_wall1'); Bd = Band(P); model = RUNS4['sb3_R1_LoD2_record']['model']; fig, axs = plt.subplots(1, 2, figsize=(18, 9)); pts = {}
    for i, st in enumerate(['7000', '30000']):
        ax = axs[i]; VF = b.mesh(A4O/'gtj/meshes'/f'R1rep_b10__LoD2__sb3_{st}'/'final.ply'); q = sec_lines(ax, 'R1rep_b10__LoD2', o, h, e, L, zr, VF)
        S = torch.load(model/'trainlog/scene'/f'{st}.pt', map_location='cpu', weights_only=False); X = S['xyz'].double().numpy(); m, dn, _ = Bd.member(X)
        rel = X-o; mm = m & (np.abs(rel@e) <= .25) & (np.abs(rel@h) <= L); kd = kind_of5(S['target_tag'].numpy(), S['target_index'].numpy(), Bd.vset)
        for kk in range(4):
            s_ = mm & (kd == kk)
            if s_.any(): ax.scatter((rel@h)[s_], X[s_, 2], s=22, c=KCOL[kk], edgecolors='k', lw=.3, label=f'벽 앞 0.2~3 m: {KIND_KO[kk]} {int(s_.sum())}', zorder=5)
        dv, _ = cKDTree(VF[0]).query(cd['X'], distance_upper_bound=.2) if VF is not None else (np.full(len(cd['X']), np.inf), None)
        ax.set_title(f'{int(st):,}회: 잃은 점 0.2 m 안 표면 {pct(np.isfinite(dv)):.0f} %, 벽 앞 0.2~3 m 가우시안 {int(m.sum())}', fontsize=12); axis_labels(ax, True); ax.legend(loc='upper left', fontsize=9)
        pts.update({f's{st}__{k}': v for k, v in q.items()}); pts[f's{st}__gauss_h'] = (rel@h)[mm]; pts[f's{st}__gauss_z'] = X[mm, 2]; pts[f's{st}__gauss_kind'] = kd[mm]
    rel = cd['X']-o; pm = (np.abs(rel@e) <= .25) & (np.abs(rel@h) <= L)
    if pm.any(): arrow(axs[1], (float(np.median((rel@h)[pm])), float(np.median(cd['X'][pm, 2]))), '잃은 벽', (1.2, .8))
    fig.suptitle('7,000회에 벽을 따라 있던 표면이 30,000회에는 벽 앞 1~3 m로 옮겨 가 있다', fontsize=17, weight='bold')
    fig.text(.5, .905, '(발주문의 문장. 이 단면에서 30,000회 표면은 벽 아래쪽에서 벽 앞으로 낮게 뻗고, 벽 높이에는 거의 없다. 값은 축 제목)', ha='center', fontsize=11, color='#444')
    fig.tight_layout(rect=(0, 0, 1, .89))
    save('r1_lod2_wall1', fig, dict(case='r1_lod2_wall1', model=str(model), meshes='addendum4 gtj sb3_7000 / sb3_30000', origin=o.tolist(), h=h.tolist()), pts)

CASES = dict(edge_back=edge_back, edge_annex=edge_annex, annex_under=annex_under, south_wall=south_wall, visible_wall=visible_wall, fixed=fixed, floater=floater, r1_lod2_wall1=r1_lod2_wall1)
if __name__ == '__main__':
    a = sys.argv[1:]
    if a[0] == 'rays': rays()
    else:
        for n in a[1:]: CASES[n]()
