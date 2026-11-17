"""Case figures by correction 1 (덧붙임6_고침1_그림규칙.md): three panels per case - 1 photo (place as a filled outline, section line A-B), 2 the trained surface from the same
camera (light gray shading; red fill = surface farther than 0.5 m from any GT point near the place; red hatch = GT place points without a mesh vertex within 0.2 m),
3 the A-B section (GT gray, target blue, trained surface red; one arrow). Comparison cases split panels 2 and 3. CPU (open3d raycasting).
usage: a6_case.py <case> [...]   -> figures/case_<case>.png + .json (camera, crop, meshes), payload addendum6/case/case_<case>.npz (plotted points and masks)
Places come from the addendum 4 case definitions (a4_ba.case_def), the section frame from a4_ba.frame / window."""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1/addendum6'); sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1/addendum4')
from a6_common import *
import a4_ba as b
CS6 = A6O/'case'; FIG = A6D/'figures'; GTJ6 = A6O/'gtj/meshes'
GRAY, BLUE, RED = '#8c8c8c', '#1f4fff', '#e31a1c'
W, H = 1024, 741

def M_(p): return Path(p)/'final.ply'
CASES = {
    'floor_band': dict(cd='floor_band', title='통로 바닥이 있어야 할 자리에 표면이 없고, 통로 위를 덮는 면이 있다', meshes=[('30,000회', M_(O/'gtj/meshes/R1rep_b10__ALS__tl_own_30000'))],
                       missing=True, extra=3., arrow='바닥 자리'),
    'edge_back': dict(cd='edge_back', title='벽이 바닥과 만나는 띠에 표면이 없다', meshes=[('30,000회', M_(O/'gtj/meshes/B0_b10__LoD2__tl_own_30000'))], missing=True, extra=0., arrow='벽 아랫단'),
    'annex_under': dict(cd='annex_under', title='지붕 가장자리에서 아래 바닥까지 실제로 없는 비스듬한 면이 있다', meshes=[('30,000회', M_(A3O/'gtj/meshes/B0_b10__ALS__ba3_30000'))],
                        missing=False, extra=1.5, xray=True, arrow='없는 비스듬한 면'),
    'south_wall': dict(cd='south_wall', title='벽 뒤 건물 안쪽에 실제로 없는 면이 있다', meshes=[('30,000회', M_(TLC/'gtj/meshes/B0_b10__LoD2__tl_30000'))], missing=False, extra=4., xray=True, arrow='벽 뒤의 면'),
    'visible_wall': dict(cd='visible_wall', title='본 방법에는 벽의 표면이 없고, 가려진 화소의 감독을 끈 학습에는 있다',
                         meshes=[('본 방법', M_(TLC/'gtj/meshes/B0_b10__LoD2__tl_30000')), ('가려진 화소의 감독을 끈 학습', M_(A4O/'gtj/meshes/B0_b10__LoD2__sa2_30000'))],
                         extra_mesh=('본 방법, 표면 추출에서 가려진 화소 뺌', M_(GTJ6/'B0_b10__LoD2__ra6_tl_30000_occl_10'), M_(TLC/'gtj/meshes/B0_b10__LoD2__tl_30000')), missing=True, extra=0., arrow='벽'),
    'r1_wall1': dict(cd='ma_R1_1', title='7,000회에 있던 벽의 표면이 30,000회에 없다',
                     meshes=[('7,000회', M_(A4O/'gtj/meshes/R1rep_b10__LoD2__sb3_7000')), ('30,000회', M_(A4O/'gtj/meshes/R1rep_b10__LoD2__sb3_30000'))],
                     extra_mesh=('30,000회, 표면 추출에서 가려진 화소 뺌', M_(GTJ6/'R1rep_b10__LoD2__ra6_sb3_30000_occl_10'), M_(A4O/'gtj/meshes/R1rep_b10__LoD2__sb3_30000')), missing=True, extra=0., arrow='벽'),
    'floater': dict(cd='floater', title='건물 벽 바깥 허공에 실제로 없는 세로 면이 있다', meshes=[('30,000회', M_(TLM/'gtj/meshes/B173nb_b10__ALS__tl_30000'))], missing=False, extra=1., arrow='허공의 세로 면'),
    'fixed': dict(cd='fixed_a', title='목표면은 벽에서 떨어져 있는데 학습 뒤 표면은 벽에 있다', meshes=[('30,000회', M_(TLC/'gtj/meshes/B0_b10__LoD2__tl_30000'))], missing=False, extra=0., target_overlay=True, arrow='벽의 표면'),
}

def raycast(V, F, K, Wc, S=2):
    """rendered at S x the photo resolution (K scaled), shown over the same pixel extent."""
    import open3d as o3d
    K = np.asarray(K, 'f8').copy(); K[:2] *= S; K[0, 2] += (S-1)/2.; K[1, 2] += (S-1)/2.
    sc = o3d.t.geometry.RaycastingScene(); sc.add_triangles(o3d.core.Tensor(V.astype('f4')), o3d.core.Tensor(F.astype('u4')))
    rays = o3d.t.geometry.RaycastingScene.create_rays_pinhole(o3d.core.Tensor(K), o3d.core.Tensor(np.asarray(Wc, 'f8')), W*S, H*S)
    r = sc.cast_rays(rays); t = r['t_hit'].numpy(); n = r['primitive_normals'].numpy(); R = rays.numpy(); d = R[..., 3:]; dn = d/np.linalg.norm(d, axis=-1, keepdims=True)
    hit = np.isfinite(t); P = R[..., :3]+t[..., None]*d; shade = np.where(hit, .35+.6*np.abs((n*dn).sum(-1)), np.nan); return hit, P, shade

def proj(P, K, Wc):
    Pc = P@Wc[:3, :3].T+Wc[:3, 3]; z = Pc[:, 2]; zz = np.where(z > .2, z, np.nan); return K[0, 0]*Pc[:, 0]/zz+K[0, 2], K[1, 1]*Pc[:, 1]/zz+K[1, 2], z

def region(u, v, grow=4):
    from scipy.ndimage import binary_dilation, binary_closing, binary_fill_holes
    m = np.zeros((H, W), bool); ok = np.isfinite(u) & np.isfinite(v) & (u >= 0) & (u < W) & (v >= 0) & (v < H); m[v[ok].astype(int), u[ok].astype(int)] = True
    if not m.any(): return m
    m = binary_dilation(m, iterations=grow); m = binary_closing(m, iterations=6); return binary_fill_holes(m)

def outline(ax, m, color, lw=2.5, fill=None, hatch=None):
    if not m.any(): return
    if fill is not None:
        rgba = np.zeros((H, W, 4)); rgba[m] = list(fill); ax.imshow(rgba, extent=(0, W, H, 0), zorder=3)
    if hatch:
        import matplotlib as mpl; mpl.rcParams['hatch.color'] = color; mpl.rcParams['hatch.linewidth'] = 1.6
        ax.contourf(np.arange(W)+.5, np.arange(H)+.5, m.astype(float), levels=[.5, 1.5], hatches=[hatch], colors='none', zorder=4)
    ax.contour(np.arange(W)+.5, np.arange(H)+.5, m.astype(float), levels=[.5], colors=[color], linewidths=lw, zorder=5)

def ab(ax, ua, va, crop):
    ax.plot(ua, va, '-', color='yellow', lw=4.5, zorder=6); ax.plot(ua, va, '-', color='k', lw=1.2, zorder=7)
    for lab, x, y in zip('AB', ua, va):
        ax.text(x, y, lab, fontsize=20, weight='bold', color='k', ha='center', va='center', zorder=8, bbox=dict(boxstyle='circle', fc='yellow', ec='k'))

def draw(name):
    plt = korean_plt(); C = CASES[name]; cd = b.case_def(C['cd']); stem = cd['stem']; site = stem.split('__')[0]; o, h, e = b.frame(cd['X'], cd['N'], stem, cd['wall']); L, zr = b.window(cd, o, h, e)
    meshes = list(C['meshes']); note = {}
    if 'extra_mesh' in C:   # correction 1: add the occlusion-dropped re-extraction when it differs visibly from the base re-extraction (within-0.2 m share of the place points, >= 10 points)
        lab, pe, pb = C['extra_mesh']; Ve = b.mesh(pe); Vb = b.mesh(pb)
        if Ve is not None and Vb is not None:
            se = pct(np.isfinite(cKDTree(Ve[0]).query(cd['X'], distance_upper_bound=.2)[0])); sb_ = pct(np.isfinite(cKDTree(Vb[0]).query(cd['X'], distance_upper_bound=.2)[0])); note['occl_check'] = dict(base_pct=sb_, occl_10_pct=se)
            if abs(se-sb_) >= 10: meshes.append((lab, pe))
    if C.get('xray'):   # the place is a wrong surface: choose the view where the real surfaces within 2 m of it are visible in the image depth
        Gd = loadz(GT/'reference'/site/'dense.npz', ['xyz'])['xyz'].astype('f8'); nn_, _ = cKDTree(cd['X']).query(Gd, distance_upper_bound=2.); Xv = Gd[np.isfinite(nn_)]
        view = b.pick_views(stem, Xv if len(Xv) > 50 else cd['X'], 'visible')[0]
    else: view = b.pick_views(stem, cd['X'], 'visible' if cd['wall'] or name in ('floor_band', 'edge_back') else 'oblique')[0]
    mi = json.loads((maps_dir(stem, 'own')/'index.json').read_text())['views'][view]; K = np.asarray(mi['K']); Wc = np.asarray(mi['W2C'])
    from PIL import Image
    im = np.asarray(Image.open(Path('/s0/fork_inputs/s61')/site/'images'/f'{view}.jpg').convert('RGB').resize((W, H)))
    u, v, z = proj(cd['X'], K, Wc); place = region(u, v); ua, va, _ = proj(np.array([o-L*h, o+L*h]), K, Wc)
    n = len(meshes); figw, figh = 30, max(10, 8.5*n); asp = (.84/n-.04)*figh/(.3*figw)   # crop height / width = panel height / width
    near = np.linalg.norm(cd['X']-o, axis=1) <= max(L, 3.); nu, nv_, _ = proj(cd['X'][near], K, Wc); ok_ = np.isfinite(nu) & np.isfinite(nv_)
    cu, cv, _ = proj(o[None], K, Wc); cu, cv = float(cu[0]), float(cv[0]); lw_ = float(np.ptp(nu[ok_])) if ok_.sum() > 1 else 50.; lh_ = float(np.ptp(nv_[ok_])) if ok_.sum() > 1 else 50.
    cw = float(np.clip(max(lw_*3., lh_*3./asp, abs(ua[1]-ua[0])*1.6, abs(va[1]-va[0])*1.6/asp, 220), 220, W)); chh = cw*asp
    if chh > H: chh = H; cw = H/asp
    x0 = int(np.clip(cu-cw/2, 0, max(0, W-cw))); y0 = int(np.clip(cv-chh/2, 0, max(0, H-chh))); crop = [x0, int(x0+cw), y0, int(y0+chh)]
    G = loadz(GT/'reference'/site/'dense.npz', ['xyz'])['xyz'].astype('f8'); gtree = cKDTree(G)
    fig = plt.figure(figsize=(figw, figh)); out = dict(place_u=u, place_v=v, place_mask=place, ab_u=ua, ab_v=va)
    ax1 = fig.add_axes([.01, .06, .3, .84]); ax1.imshow(im, extent=(0, W, H, 0)); outline(ax1, place, '#ff00cc', fill=(1, 0, .8, .35)); ab(ax1, ua, va, crop)
    ax1.set_xlim(crop[0], crop[1]); ax1.set_ylim(crop[3], crop[2]); ax1.set_axis_off(); ax1.set_title('1. 사진 (분홍 = 이 자리)', fontsize=15, loc='left')
    for i, (lab, mp) in enumerate(meshes):
        VF = b.mesh(mp); top = .9-i*(.84/n); hh = .84/n-.04
        ax2 = fig.add_axes([.33, top-hh, .3, hh]); hit, P, shade = raycast(VF[0], VF[1], K, Wc)
        img = np.where(hit[..., None], shade[..., None]*np.array([.92, .92, .92]), 1.); ax2.imshow(np.clip(img, 0, 1), extent=(0, W, H, 0))
        red = np.zeros(hit.shape, bool)
        if C['extra'] > 0:
            hp = P[hit]; dg, _ = gtree.query(hp, distance_upper_bound=.5); dx, _ = cKDTree(cd['X']).query(hp, distance_upper_bound=C['extra'])
            rr = np.zeros(hit.sum(), bool); rr[(~np.isfinite(dg)) & np.isfinite(dx)] = True; red[hit] = rr
            rgba = np.zeros(hit.shape+(4,)); rgba[red] = [.89, .1, .11, .85]; ax2.imshow(rgba, extent=(0, W, H, 0), zorder=3)
        if C.get('xray'):   # surfaces hidden from this camera (behind a wall / under a roof): the wrong-surface mesh vertices drawn over everything
            V_ = VF[0]; nb, _ = cKDTree(cd['X']).query(V_, distance_upper_bound=C['extra']); cand = np.flatnonzero(np.isfinite(nb))
            if len(cand):
                dg_, _ = gtree.query(V_[cand], distance_upper_bound=.5); wv = V_[cand[~np.isfinite(dg_)]]
                if len(wv): xu, xv, _ = proj(wv, K, Wc); xm = region(xu, xv, grow=2); outline(ax2, xm, RED, lw=2, fill=(.89, .1, .11, .45)); out[f'm{i}__xray_mask'] = xm
        miss = np.zeros((H, W), bool)
        if C['missing']:
            dv, _ = cKDTree(VF[0]).query(cd['X'], distance_upper_bound=.2); lost = ~np.isfinite(dv)
            if lost.any(): mu, mv, _ = proj(cd['X'][lost], K, Wc); miss = region(mu, mv, grow=3); outline(ax2, miss, RED, lw=2, hatch='///')
            out[f'm{i}__lost_share_pct'] = pct(lost)
        if C.get('target_overlay'):
            T = Targets(stem); A = T.anchor[cd['vplace']]; tu, tv, _ = proj(A, K, Wc); outline(ax2, region(tu, tv, grow=6), BLUE, fill=(.12, .31, 1, .3))
        ab(ax2, ua, va, crop); ax2.set_xlim(crop[0], crop[1]); ax2.set_ylim(crop[3], crop[2]); ax2.set_axis_off(); ax2.set_title(f'2. 학습 뒤 표면 — {lab}' + (' (가려서 안 보이는 면도 빨강으로 겹쳐 그림)' if C.get('xray') else ''), fontsize=15, loc='left')
        out[f'm{i}__red_mask'] = red; out[f'm{i}__missing_mask'] = miss
        ax3 = fig.add_axes([.67, top-hh, .31, hh]); q = section(ax3, stem, o, h, e, L, zr, VF, C.get('target_overlay', True))
        rel = cd['X']-o; pm = (np.abs(rel@e) <= .25) & (np.abs(rel@h) <= L)
        sgm = q['surface_segments'].reshape(-1, 2, 2).mean(1) if len(q['surface_segments']) else np.zeros((0, 2))
        far = sgm[~np.isfinite(cKDTree(np.c_[q['gt_h'], q['gt_z']]).query(sgm, distance_upper_bound=.5)[0])] if (C.get('xray') and len(sgm) and len(q['gt_h'])) else np.zeros((0, 2))
        if len(far): px, pz = float(np.median(far[:, 0])), float(np.median(far[:, 1])); pm = np.ones(1, bool)
        elif pm.any(): px, pz = float(np.median((rel@h)[pm])), float(np.median(cd['X'][pm, 2]))
        if pm.any(): ax3.annotate(C['arrow'], xy=(px, pz), xytext=(px+.25*L, pz+.25*(zr[1]-zr[0])), arrowprops=dict(arrowstyle='->', lw=2), fontsize=14, weight='bold', bbox=dict(fc='white', ec='k'))
        ax3.set_title(f'3. A–B 단면 — {lab}', fontsize=15, loc='left'); out.update({f'm{i}__{k}': v_ for k, v_ in q.items()})
        if i == 0: ax3.legend(loc='upper right', fontsize=12)
    from matplotlib.patches import Patch
    hs = [Patch(fc=(1, 0, .8, .35), ec='#ff00cc', label='이 자리')]+([Patch(fc='white', ec=RED, hatch='///', label='있어야 하는데 없는 면')] if C['missing'] else [])+([Patch(color=RED, label='없어야 하는데 있는 면')] if C['extra'] > 0 else [])+([Patch(fc=(.12, .31, 1, .3), ec=BLUE, label='목표면')] if C.get('target_overlay') else [])
    fig.legend(handles=hs, loc='lower center', ncol=len(hs), fontsize=14, frameon=False); fig.suptitle(C['title'], fontsize=22, weight='bold')
    CS6.mkdir(parents=True, exist_ok=True); FIG.mkdir(parents=True, exist_ok=True); fig.savefig(FIG/f'case_{name}.png', dpi=90); plt.close(fig)
    from PIL import Image as I_; wpx = I_.open(FIG/f'case_{name}.png').width
    savez(CS6/f'case_{name}.npz', **{k: np.asarray(v_) for k, v_ in out.items()})
    dump(FIG/f'case_{name}.json', dict(at=now(), figure=f'case_{name}.png', width_px=wpx, title=C['title'], stem=stem, place=C['cd'], view=view, camera=dict(K=K.tolist(), W2C=Wc.tolist(), width=W, height=H), crop_xxyy=crop,
                                           meshes={lab: str(p).replace(str(PH), 'payload') for lab, p in meshes}, section=dict(A=(o-L*h).tolist(), B=(o+L*h).tolist(), h=h.tolist(), e=e.tolist(), slab_m=.25, z_range=list(zr)),
                                           red_rule='fill: mesh hit points > 0.5 m from every GT point and within the case radius of the place; hatch: place GT points without a mesh vertex within 0.2 m',
                                           **note, points_npz=f'payload addendum6/case/case_{name}.npz', scientific_verdict=None))
    print('CASE6', name, wpx, flush=True)

def section(ax, stem, o, h, e, L, zr, VF, target=True):
    from matplotlib.collections import LineCollection
    G = loadz(GT/'reference'/stem.split('__')[0]/'dense.npz', ['xyz'])['xyz'].astype('f8'); rel = G-o; m = (np.abs(rel@e) <= .25) & (np.abs(rel@h) <= L) & (G[:, 2] >= zr[0]) & (G[:, 2] <= zr[1])
    ax.scatter((rel@h)[m], G[m, 2], s=3, c=GRAY, lw=0, label='참값', zorder=1, rasterized=True); out = dict(gt_h=(rel@h)[m], gt_z=G[m, 2])
    T = Targets(stem); sg = b.disc_segments(T, np.arange(len(T.anchor)), o, h, e, L, zr)
    if target and len(sg): ax.add_collection(LineCollection(sg, colors=BLUE, linewidths=2.6, label='목표면', zorder=3))
    s2 = b.cut(VF, o, h, e, L, zr)
    if len(s2): ax.add_collection(LineCollection(s2, colors=RED, linewidths=2, label='학습 뒤 표면', zorder=4))
    out.update(target_segments=sg, surface_segments=s2)
    ax.set_xlim(-L, L); ax.set_ylim(*zr); ax.set_aspect('equal'); ax.grid(alpha=.25); ax.set_xticks([-L, 0, L]); ax.set_xticklabels(['A', '0', 'B'], fontsize=15, weight='bold')
    ax.set_xlabel(f'A에서 B로 (가로 {2*L:.0f} m, 단면 두께 ±0.25 m)', fontsize=12); ax.set_ylabel('높이 (m)', fontsize=12); return out

if __name__ == '__main__':
    for nm in sys.argv[1:]: draw(nm)
