"""Video v5 (user feedback 2026-11-11 after v4): show the inputs so the roof change reads.
Row 2 = [inputs: old roof of the prior (ALS mesh, pink) + image MVS per patch (dark grey discs)] [F Gaussians + judgment] [G mesh], one fixed camera;
no permanent wrong-place emphasis (pink outline removed); places 1-3 = the thesis figure places of B173 (spots_v5.py: wing, unseen long wall, glass skylight)
drawn as dashed outlines; camera azimuth from spots_v5.json (largest smallest-visible-share); H adds the image MVS of the same band;
I = where the prior is wrong (GTJUDGE case 1, the changed roof): mesh completeness at the key meshes + Gaussians placed on the old roof. CPU."""
import sys
import video_v2
video_v2.ASPECT = 624/375   # row-2 panels .325 x .347 of 1920 x 1080
from video_v4 import *
import proto_v2
proto_v2.wrong_outline = lambda *a, **k: None
from matplotlib.collections import EllipseCollection, PolyCollection
from scipy.spatial import ConvexHull
V5 = O/'video_v5'; C5 = V5/'cache'; F5 = V5/'frames'; SPJ = json.loads((O/'analysis/spots_v5/spots_v5.json').read_text()); AZ = int(SPJ['chosen_azimuth'])
MVSC = '#444441'; PRIORC = np.array(to_rgb('#ED93B1')); SPOTC = '#2C2C2A'; SPOTN = {'wing': '① 날개', 'wall': '② 긴 벽', 'glass': '③ 유리 채광창'}

def spot_corners(S):
    out = {}; g = S.c['scope']['ground_z']
    for k in ['wing', 'glass']:
        s = SPJ['places'][k]['section']; c = np.array(s['centre'][:2]); t = np.array(s['t'], float); t /= np.linalg.norm(t); nn = np.array([-t[1], t[0]]); hw = s['window_half_width_m']
        P = np.load(O/f'analysis/spots_v5/{k}.npz')['points']; zt = float(np.percentile(P[:, 2], 99))+.5; zb = float(np.percentile(P[:, 2], 1))-.5
        xy = [c+a*t*s['L']/2+b*nn*hw for a in (-1, 1) for b in (-1, 1)]; out[k] = np.array([[x, y, z] for x, y in xy for z in (zb, zt)])
    f = SPJ['places']['wall']['face']; c = np.array(f['centre']); t = np.array(f['t']); out['wall'] = np.array([c+s_*t+np.array([0, 0, z-c[2]]) for s_ in f['s_range'] for z in f['z_range']])
    return out

def prep5():
    S = Ctx(); C5.mkdir(parents=True, exist_ok=True); B = S.view(AZ); tree = cKDTree(S.pt[:, :2])
    np.save(C5/'D30.npy', S.raster(S.m30, B, 940)[1].astype('f4'))
    for mk in sorted(set(S.mesh_of(n) for n in S.names)):
        if (C5/f'E_{mk}.npz').exists(): continue
        z = loadz(A/f'mesh_{mk}.npz', ['vertices', 'faces', 'vertex_error_m']); V = z['vertices'].astype(float); F = z['faces']; err = np.abs(z['vertex_error_m'][F].mean(1))
        cen = V[F].mean(1); n = np.cross(V[F[:, 1]]-V[F[:, 0]], V[F[:, 2]]-V[F[:, 0]]); n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
        dd, ii = tree.query(cen[:, :2]); reg = np.where((dd <= .5) & (np.abs(n[:, 2]) >= .5), S.pj[ii], -1); base = np.tile(NEUTRAL, (len(F), 1))
        for j, c in JC.items(): base[reg == j] = to_rgb(c)
        a = np.clip((err-TAU/100)/(1-TAU/100), 0, 1)[:, None]; col = np.where((err <= TAU/100)[:, None], base, P0*(1-a)+P1*a); m = S.mesh(mk)
        img, hit, pid, nrm = cast(S, m['scene'], B); img = np.where(hit[:, None], col[pid.clip(0, len(F)-1)]*(.55+.45*np.abs(nrm@LT))[:, None], 1.)
        savez(C5/f'E_{mk}.npz', img=(np.clip(img.reshape(-1, 940, 3), 0, 1)*255).astype('u1')); print('E5', mk, flush=True)
    pr = loadz(S1/'defs'/SITE/'prior_ALS.npz', ['V', 'F']); V = pr['V'].astype(float); F = pr['F']; cen = V[F].mean(1)
    fnz = np.cross(V[F[:, 1]]-V[F[:, 0]], V[F[:, 2]]-V[F[:, 0]]); fnz = np.abs(fnz[:, 2])/np.maximum(np.linalg.norm(fnz, axis=1), 1e-12)
    keep = scope_mask(cen, dict(S.c, scope=dict(S.c['scope'], z_min=S.c['scope']['ground_z']+2.))) & (fnz >= .3); F = F[keep]   # roof-like faces only (the ALS TIN hangs curtains down the walls)
    sc = o3d.t.geometry.RaycastingScene(); tm = o3d.t.geometry.TriangleMesh(); tm.vertex.positions = o3d.core.Tensor(V.astype('f4')); tm.triangle.indices = o3d.core.Tensor(F.astype('i4')); sc.add_triangles(tm)
    img, hit, pid, nrm = cast(S, sc, B); rgba = np.zeros((len(hit), 4)); nh = nrm[hit]*np.sign(nrm[hit][:, 2:3]+1e-9); rgba[hit, :3] = PRIORC*(.35+.65*np.clip(nh@LT, 0, 1))[:, None]; rgba[hit, 3] = .42
    t = loadz(FT/'targets'/f'{STEM}.npz', ['centre', 'normal', 'mvs_mean_m']); mv = t['centre'][S.pid]+t['normal'][S.pid]*t['mvs_mean_m'][S.pid][:, None]; ok = np.isfinite(mv).all(1)
    corners = spot_corners(S)
    savez(C5/'inputs.npz', prior_rgba=(rgba.reshape(-1, 940, 4)*255).astype('u1'), mvs_xyz=mv[ok], mvs_n=S.pn[ok], mvs_r=S.pr[ok], prior_faces=len(F),
          **{f'spot_{k}': v for k, v in corners.items()})
    dump(C5/'prep5.json', dict(at=now(), azimuth=AZ, elevation=35, half_extent_m=list(S.half), prior_roof_faces_in_scope_above_ground_2m_nz_ge_0p3=int(len(F)), mvs_patches=int(ok.sum()), scientific_verdict=None)); print('PREP5', flush=True)

def cast(S, scene, B, W=940):
    H = int(W*S.half[1]/S.half[0]); xs = np.linspace(-S.half[0], S.half[0], W); ys = np.linspace(S.half[1], -S.half[1], H); X, Y = np.meshgrid(xs, ys)
    org = S.ctr+X[..., None]*B[0]+Y[..., None]*B[1]-400*B[2]; rays = np.concatenate([org, np.broadcast_to(B[2], org.shape)], -1).reshape(-1, 6).astype('f4')
    r = scene.cast_rays(o3d.core.Tensor(rays)); hit = np.isfinite(r['t_hit'].numpy()); return None, hit, r['primitive_ids'].numpy(), r['primitive_normals'].numpy()

def discs(S, P, N, R, B):
    n = N/np.linalg.norm(N, axis=1)[:, None]; t1 = np.cross(n, [0, 0, 1.]); bad = np.linalg.norm(t1, axis=1) < 1e-6; t1[bad] = [1, 0, 0]; t1 /= np.linalg.norm(t1, axis=1)[:, None]; t2 = np.cross(n, t1)
    M = np.stack([np.stack([t1@B[0], t2@B[0]], 1), np.stack([t1@B[1], t2@B[1]], 1)], 1)*R[:, None, None]; U, s, _ = np.linalg.svd(M); return s, np.degrees(np.arctan2(U[:, 1, 0], U[:, 0, 0]))

def draw_inputs(axP, axM, S, B, inp, d30):
    """Two stacked panels from the same camera: the prior's roof-like faces alone (opaque shading shows the old gable), and the image MVS per patch alone
    (discs drawn horizontal on roof-like patches: the MVS height is a point per patch, its own slope is not stored)."""
    rgba = inp['prior_rgba'].astype(np.float32)/255; rgba[..., 3] = (rgba[..., 3] > 0).astype(np.float32)
    axP.imshow(rgba, extent=(-S.half[0], S.half[0], -S.half[1], S.half[1]))
    P = inp['mvs_xyz'].astype(float); N = inp['mvs_n'].astype(float).copy(); N[np.abs(N[:, 2]) >= .3] = [0, 0, 1.]; vis, x, y = S.visible(P, B, d30, .6); _, _, dd = S.proj(P, B); s, ang = discs(S, P, N, inp['mvs_r'].astype(float)*1.15, B)
    o = np.flatnonzero(vis)[np.argsort(-dd[vis])]; sh = .55+.45*np.abs(N@LT); col = np.array(to_rgb(MVSC))[None]*0+np.c_[sh, sh, sh]*np.array(to_rgb('#5F5E5A'))[None]
    axM.add_collection(EllipseCollection(2*s[o, 0], 2*s[o, 1], ang[o], units='xy', offsets=np.c_[x[o], y[o]], offset_transform=axM.transData, facecolors=np.clip(col[o], 0, 1), edgecolors='none'))
    for ax in (axP, axM): ax.set_xlim(-S.half[0], S.half[0]); ax.set_ylim(-S.half[1], S.half[1]); ax.set_aspect('equal'); ax.axis('off')

def draw_spots(ax, S, B, inp):
    for k, lab in SPOTN.items():
        x, y, _ = S.proj(inp[f'spot_{k}'].astype(float), B); pts = np.c_[x, y]; h = ConvexHull(pts); poly = pts[h.vertices]
        ax.add_collection(PolyCollection([poly], facecolors='none', edgecolors=SPOTC, linewidths=1.3, linestyles=(0, (4, 2)), zorder=8))
        i = np.argmax(poly[:, 1]); ax.text(poly[i, 0], poly[i, 1]+.6, lab, fontsize=9, color=SPOTC, ha='center', va='bottom', zorder=9, bbox=dict(boxstyle='round,pad=.15', facecolor='white', edgecolor='none', alpha=.8))

def key_case1():
    out = {}
    for p in sorted((O/'meshes').glob('tl_*/score.json')):
        r = [x for x in json.loads(p.read_text())['rows'] if str(x['case_id']) == '1']
        if r: out[p.parent.name[3:]] = r[0]['completeness_pct']
    return out

def frame5(S, n, prev, out, H, inp, KC):
    it = S.it[n]; B = S.view(AZ); st = loadz(CA/'static2d.npz'); gs = loadz(CA/'gstatic.npz'); i2 = loadz(C3OLD/'img2d.npz'); d = dict(loadz(DER/'gaussians'/f'{n}.npz')); d['_name'] = n
    fig = plt.figure(figsize=(16, 9), dpi=120, facecolor='white')
    stage = '불투명도 되돌림 직전' if n.endswith('pre_reset') else ('불투명도 되돌림 직후' if it in [3000, 6000, 9000, 12000] else ('밀도 제어 전' if it < 600 else ('밀도 제어 중' if it <= 14900 else '밀도 제어 끝')))
    fig.text(.012, .968, f'B173 · 학습 {it:,}회', fontsize=19, fontweight='bold', color=NAVY, va='center'); fig.text(.215, .968, stage, fontsize=12, color='#5F5E5A', va='center')
    ax = fig.add_axes([.44, .958, .55, .02]); ax.barh(0, 30000, color='#E5E3DC', height=1); ax.barh(0, it, color='#5F5E5A', height=1); ax.set_xlim(0, 30000); ax.axis('off')
    for x in [0, 3000, 7000, 15000, 30000]: ax.plot([x, x], [-.5, .5], color='white', lw=1.5)
    r = loadz(O/'renders'/n/'data.npz', ['train1_depth', 'train1_alpha']); dep = r['train1_depth'].astype(float); al = r['train1_alpha'].astype(float) > .5
    rgb = np.asarray(Image.open(O/'renders'/n/'train1_rgb.png').convert('RGB'), np.float32)/255; tgt = i2['target_depth'].astype(float)
    cimg = gray(tgt, np.isfinite(tgt) & (tgt > 0)); tj = i2['target_judgment_map']
    okd = al & (dep > 0) & np.isfinite(tgt) & (tgt > 0); dd_ = np.abs(dep-tgt); dimg = np.where(okd[..., None], ramp(dd_, TAU/100, 1., dd_ <= TAU/100), 1.)
    from scipy.ndimage import binary_dilation
    bld = binary_dilation(tj >= 0, iterations=12); dimg = np.where(bld[..., None], dimg, .25*dimg+.75)
    panels = [('A 색 감독 신호 (실제 사진)', st['photo'], False), ('B GS 렌더 (색)', rgb, False), ('C 깊이 감독 신호 (선 = 판정 영역)', cimg, True), ('D GS 렌더 깊이 (같은 선)', gray(dep, al & (dep > 0)), True),
              ('E 렌더 깊이가 감독과 다른 곳 |D−C|', dimg, True)]
    for i, (t_, img, wr) in enumerate(panels):
        a = fig.add_axes([.004+i*.188, .715, .18, .22]); a.imshow(np.clip(img, 0, 1)); a.axis('off'); a.set_title(t_, fontsize=10.5, loc='left', color='#2e3a48', pad=3)
        if wr:
            for j in [0, 2, 1, 4]: a.contour((tj == j).astype(float), levels=[.5], colors=JC[j], linewidths=.9)
        if i == 2:
            a.text(.01, .02, '회색 = 목표 깊이 (D와 같은 눈금)\n선 색 = 깊이 출처 (1 m 안 다수 판정)\n 파랑 일치: 사전 정보·영상 둘 다 (가중 평균)\n 주황 보정: 영상(MVS) · 초록 보존·노랑 결측: 사전 정보\n선 밖: 배경, 영상(MVS)', transform=a.transAxes, fontsize=6.6, color='#2C2C2A', va='bottom',
                   bbox=dict(boxstyle='round,pad=.25', facecolor='white', edgecolor='none', alpha=.85))
        if i == 4:
            a.text(.01, .02, '연회색 = 21 cm 안 (감독을 따름)\n보라 = 21 cm 넘음 (1 m에서 가장 진함)\n건물(판정 영역) 밖은 옅게', transform=a.transAxes, fontsize=6.6, color='#2C2C2A', va='bottom',
                   bbox=dict(boxstyle='round,pad=.25', facecolor='white', edgecolor='none', alpha=.85))
    cb = fig.add_axes([.962, .73, .005, .19]); cb.imshow(np.linspace(1, 0, 100)[:, None]*.83+.12, cmap='gray', vmin=0, vmax=1, aspect='auto', extent=(0, 1, DLO, DHI)); cb.set_xticks([]); cb.yaxis.tick_right(); cb.tick_params(labelsize=7)
    cb.set_title('C·D 깊이\n(m)', fontsize=7, pad=2)
    d30 = np.load(C5/'D30.npy').astype(float); aIP = fig.add_axes([.004, .345, .162, .347]); aIM = fig.add_axes([.169, .345, .162, .347]); aF = fig.add_axes([.338, .345, .325, .347]); aG = fig.add_axes([.670, .345, .325, .347])
    draw_inputs(aIP, aIM, S, B, inp, d30); mk = S.mesh_of(n); img = loadz(C5/f'E_{mk}.npz')['img'].astype(np.float32)/255
    draw_E(aG, S, img, B, S.gline, depth=d30); draw_F(aF, S, d, B, d30, prev, S.gline)
    x_, y_, _ = S.proj(S.gline, B)
    for a in (aIP, aIM): a.plot(x_, y_, color=NAVY, lw=1.5, zorder=7)
    for a in (aF, aG): draw_spots(a, S, B, inp)
    xs_, ys_ = [], []
    for P_ in [S.corners]+[inp[f'spot_{k}'] for k in SPOTN]: x__, y__, _ = S.proj(np.asarray(P_, float), B); xs_ += list(x__); ys_ += list(y__)
    bx = np.array([min(xs_), max(xs_)]); by = np.array([min(ys_), max(ys_)]); mx, my = .04*np.ptp(bx), .06*np.ptp(by)
    for a in (aIP, aIM, aF, aG): a.set_xlim(bx[0]-mx, bx[1]+mx); a.set_ylim(by[0]-my, by[1]+my+1.5)
    aIP.set_title('입력 1: 사전 정보 (옛 항공 LiDAR)', fontsize=9.5, loc='left', color='#2e3a48', pad=1); aIM.set_title('입력 2: 영상 MVS (패치마다)', fontsize=9.5, loc='left', color='#2e3a48', pad=1)
    aF.set_title('F 가우시안 + 판정 영역', fontsize=11, loc='left', color='#2e3a48', pad=2)
    aG.set_title('G 메시 (가우시안으로 만든 결과)'+(f' · 메시: {S.it[mk]:,}회' if mk != n else ''), fontsize=11, loc='left', color='#2e3a48', pad=2)
    aH = fig.add_axes([.04, .105, .52, .195]); g = gs; kind, gl = gline_of(S, n); grd = S.ground
    for j in JC:
        q = g['tg_j'] == j; aH.errorbar(g['tg_s'][q], g['tg_z'][q]-grd, yerr=g['tg_w'][q], fmt='none', ecolor=PALEJ[j], elinewidth=3)
    aH.add_collection(LineCollection(np.stack([g['prior_seg'][:, :, 0], g['prior_seg'][:, :, 1]-grd], 2), colors=PINK, linewidths=1.2, linestyles=(0, (5, 3))))
    M = inp['mvs_xyz'].astype(float); pv = (M[:, :2]-S.c2)@S.gnrm; mb = (pv >= S.gat) & (pv < S.gat+1); aH.scatter((M[mb, :2]-S.c2)@S.gax, M[mb, 2]-grd, s=6, c=MVSC, marker='s', lw=0, zorder=2)
    aH.scatter(g['gt_s'], g['gt_z']-grd, s=1.2, c='black', lw=0)
    if kind == 'mesh': aH.add_collection(LineCollection(np.stack([gl[:, :, 0], gl[:, :, 1]-grd], 2), colors=NAVY, linewidths=1.2))
    else: aH.plot(gl[0], gl[1]-grd, color=NAVY, lw=1.2)
    gp = d['xyz'].astype(float); pv = (gp[:, :2]-S.c2)@S.gnrm; gm = (pv >= S.gat) & (pv < S.gat+1); gsx = (gp[:, :2]-S.c2)@S.gax; wr = d['group33'] == 1; tag = d['target_tag']
    aH.scatter(gsx[gm & (tag == 0) & ~wr], gp[gm & (tag == 0) & ~wr, 2]-grd, s=3, c=GREYG, lw=0)
    aH.scatter(gsx[gm & (tag == 2) & ~wr], gp[gm & (tag == 2) & ~wr, 2]-grd, s=9, facecolors='none', edgecolors='#2C2C2A', linewidths=.5)
    for j in JC:
        q = gm & (tag == 1) & (d['judgment'] == j) & ~wr; aH.scatter(gsx[q], gp[q, 2]-grd, s=5, c=JC[j], lw=0)
    aH.scatter(gsx[gm & wr], gp[gm & wr, 2]-grd, s=22, c=PINK, edgecolors='white', linewidths=.6, zorder=6)
    aH.set_xlim(g['gt_s'].min()-1, g['gt_s'].max()+1); aH.set_ylim(12, 25.5); aH.set_xlabel('건물 가로 방향 (m)', fontsize=9); aH.set_ylabel('지면 위 높이 (m)', fontsize=9); aH.tick_params(labelsize=8)
    aH.set_title('H 가로 단면 (남색 선 자리) · 분홍 점선 사전 정보 · 진회색 영상 MVS · 면 선: '+('메시' if kind == 'mesh' else '렌더 깊이'), fontsize=11, loc='left', color='#2e3a48', pad=2)
    hs = H['states']; nn = [m for m in S.names if not m.endswith('pre_reset')]; h = fig.add_axes([.63, .105, .31, .195])
    kx = np.array([S.it[m] for m in KC], float); ky = np.array([KC[m] for m in KC]); o = np.lexsort((np.array([0 if m.endswith('pre_reset') else 1 for m in KC]), kx)); kx, ky = kx[o], ky[o]; kn = np.array(list(KC))[o]
    reset = np.array([(S.it[m] in (3000, 6000, 9000, 12000)) and not m.endswith('pre_reset') for m in kn]); main_ = ~reset
    h.plot(kx[main_], ky[main_], color=NAVY, lw=1.6, marker='o', ms=3, alpha=.25); mm = main_ & (kx <= it); h.plot(kx[mm], ky[mm], color=NAVY, lw=1.8, marker='o', ms=4, label='메시가 지금 지붕을 덮는 비율 (%)')
    rr = reset & (kx <= it)
    if rr.any(): h.scatter(kx[rr], ky[rr], s=30, facecolors='white', edgecolors=NAVY, zorder=5, label='되돌림 직후')
    h.set_ylim(0, 102); h.set_xlim(-300, 30300); h.axvline(it, color='#2e3a48', lw=1); h.set_xticks([0, 3000, 7000, 15000, 30000]); h.set_xticklabels(['0', '3,000', '7,000', '15,000', '30,000']); h.tick_params(labelsize=8)
    h2 = h.twinx(); xs = np.array([hs[m]['iteration'] for m in nn], float); ys = np.array([hs[m]['wrong_alive'] for m in nn], float); h2.plot(xs, ys, color=PINK, lw=1.4, ls='--', alpha=.25); m2 = xs <= it
    h2.plot(xs[m2], ys[m2], color=PINK, lw=1.6, ls='--', label='옛 지붕에 놓인 가우시안 수 (오른쪽)'); h2.set_ylim(0, 3700); h2.tick_params(labelsize=8, colors=PINK)
    a1_, b1_ = h.get_legend_handles_labels(); a2_, b2_ = h2.get_legend_handles_labels(); h.legend(a1_+a2_, b1_+b2_, fontsize=8, frameon=False, loc='center right')
    h.set_title('I 지붕이 바뀐 곳 (사전 정보가 틀린 곳, 참값 기준)', fontsize=11, loc='left', color='#2e3a48', pad=2)
    hd = [Patch(facecolor=PRIORC, alpha=.7, label='사전 정보: 옛 항공 LiDAR 지붕면'), Line2D([], [], marker='o', ls='', color='#5F5E5A', label='영상 MVS (패치마다)')]
    hd += [Patch(color=PALEJ[j], label=f'{JN[j]} 영역 (F 바탕)') for j in [0, 2, 1, 4]]+[Patch(color=JC[j], label=f'{JN[j]} 면·묶인 가우시안') for j in [0, 2, 1, 4]]
    hd += [Line2D([], [], marker='o', ls='', markerfacecolor='none', markeredgecolor='#2C2C2A', label='풀림'), Line2D([], [], marker='o', ls='', color=GREYG, label='자유'),
           Line2D([], [], marker='o', ls='', color=PINK, label='옛 지붕에 놓인 가우시안'), Line2D([], [], marker='x', ls='', color='#5F5E5A', label='지워짐'), Patch(color=NEUTRAL, label='판정 영역 밖 면'),
           Patch(color=P1, label='어긋남: 면은 참값에서, E는 감독에서 21 cm 넘게'), Line2D([], [], color=NAVY, label='단면 자리 · 면'), Line2D([], [], color=SPOTC, ls='--', label='논문 그림 자리'),
           Line2D([], [], marker='o', ls='', color='black', ms=3, label='참값')]
    fig.legend(handles=hd, loc='lower center', ncol=11, frameon=False, fontsize=8, bbox_to_anchor=(.5, -.005), handlelength=1.0, columnspacing=.6)
    fig.savefig(out, facecolor='white'); plt.close(fig)

def frames5(k, nchunks):
    S = Ctx(); F5.mkdir(parents=True, exist_ok=True); H = json.loads((CA/'H.json').read_text()); inp = dict(np.load(C5/'inputs.npz')); KC = key_case1(); items = []; prev = None
    for n in S.names: items.append(dict(name=n, prev=prev, hold=n in HOLD3, file=f'frames/{len(items):03d}_{n}.png')); prev = n
    for i, it_ in enumerate(items):
        if i % int(nchunks) != int(k) or (V5/it_['file']).exists(): continue
        frame5(S, it_['name'], it_['prev'], V5/it_['file'], H, inp, KC); print('FRAME5', i, it_['name'], flush=True)
    if int(k) == 0: dump(V5/'frames.json', dict(at=now(), items=items, fps=4, hold_s=1.5, camera=f'az {AZ} el 35 orthographic, fixed (spots_v5.json rule)', plate='새 판 (다시 돌린 판)', scientific_verdict=None))

if __name__ == '__main__':
    a = sys.argv[1:]
    if a[0] == 'prep': prep5()
    elif a[0] == 'frames': frames5(a[1], a[2])
    elif a[0] == 'one':
        S = Ctx(); F5.mkdir(parents=True, exist_ok=True); frame5(S, a[1], a[2] if len(a) > 2 else None, V5/f'test_{a[1]}.png', json.loads((CA/'H.json').read_text()), dict(np.load(C5/'inputs.npz')), key_case1())
