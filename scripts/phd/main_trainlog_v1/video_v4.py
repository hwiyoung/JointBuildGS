"""Video v4 (user feedback 2026-11-11, after v3): order supervision -> Gaussians -> mesh (F Gaussians left, G mesh right);
fifth top panel = where the rendered depth departs from the depth supervision (>21 cm); mesh faces and bound Gaussians share the mid judgment tone.
Based on video v3: fixed camera (no rotation); E and F share the judgment palette;
row 1 = supervision and render side by side (photo | colour render | depth supervision target | rendered depth);
H reduced to one plot for the wrong-judgment place. CPU. Uses caches of video_v2 (static2d, gstatic, H)."""
import sys
from video_v2 import *
import proto_v2
proto_v2.JDARK.update(JC)   # bound Gaussians drawn in the same mid judgment tone as mesh faces
from scipy.spatial import cKDTree
from scipy.ndimage import binary_closing
V3 = O/'video_v4'; C3 = V3/'cache'; F3 = V3/'frames'; C3OLD = O/'video_v3/cache'; NEUTRAL = np.array(to_rgb('#E5E3DC')); DLO, DHI = 52., 68.
HOLD3 = ['0', '3000_pre_reset', '7000', '15000', '30000']

def prep3():
    S = Ctx(); C3.mkdir(parents=True, exist_ok=True); B = S.view(180); tree = cKDTree(S.pt[:, :2])
    for mk in sorted(set(S.mesh_of(n) for n in S.names)):
        if (C3/f'E_{mk}.npz').exists(): continue
        z = loadz(A/f'mesh_{mk}.npz', ['vertices', 'faces', 'vertex_error_m']); V = z['vertices'].astype(float); F = z['faces']; err = np.abs(z['vertex_error_m'][F].mean(1))
        cen = V[F].mean(1); n = np.cross(V[F[:, 1]]-V[F[:, 0]], V[F[:, 2]]-V[F[:, 0]]); n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
        dd, ii = tree.query(cen[:, :2]); reg = np.where((dd <= .5) & (np.abs(n[:, 2]) >= .5), S.pj[ii], -1)
        base = np.tile(NEUTRAL, (len(F), 1))
        for j, c in JC.items(): base[reg == j] = to_rgb(c)
        a = np.clip((err-TAU/100)/(1-TAU/100), 0, 1)[:, None]; col = np.where((err <= TAU/100)[:, None], base, P0*(1-a)+P1*a)
        m = S.mesh(mk); H = int(940*S.half[1]/S.half[0]); xs = np.linspace(-S.half[0], S.half[0], 940); ys = np.linspace(S.half[1], -S.half[1], H); X, Y = np.meshgrid(xs, ys)
        org = S.ctr+X[..., None]*B[0]+Y[..., None]*B[1]-400*B[2]; rays = np.concatenate([org, np.broadcast_to(B[2], org.shape)], -1).reshape(-1, 6).astype('f4')
        r = m['scene'].cast_rays(o3d.core.Tensor(rays)); hit = np.isfinite(r['t_hit'].numpy()); pid = r['primitive_ids'].numpy().clip(0, len(F)-1); nrm = r['primitive_normals'].numpy()
        img = np.where(hit[:, None], col[pid]*(.55+.45*np.abs(nrm@LT))[:, None], 1.).reshape(H, 940, 3); savez(C3/f'E_{mk}.npz', img=(np.clip(img, 0, 1)*255).astype('u1')); print('E3', mk, flush=True)
    return
    cams = {v['name']: v for v in json.loads((O/'renders/cameras.json').read_text())['training']}; v = cams[CAM]; K = np.asarray(v['K']); E = np.asarray(v['W2C']); W, Hh = v['width'], v['height']
    w = S.pgroup == 1; P = np.c_[S.pt[w, :2], S.pz[w]]; q = P@E[:3, :3].T+E[:3, 3]; u = K[0, 0]*q[:, 0]/q[:, 2]+K[0, 2]; vv = K[1, 1]*q[:, 1]/q[:, 2]+K[1, 2]; rp = S.pr[w]*K[0, 0]/q[:, 2]*3.0
    yy, xx = np.mgrid[0:Hh, 0:W]; mask = np.zeros((Hh, W), bool)
    for a_, b_, r_ in zip(u, vv, np.maximum(rp, 2)):
        x0, x1, y0, y1 = int(max(0, a_-r_)), int(min(W, a_+r_+1)), int(max(0, b_-r_)), int(min(Hh, b_+r_+1))
        if x1 > x0 and y1 > y0: mask[y0:y1, x0:x1] |= (xx[y0:y1, x0:x1]-a_)**2+(yy[y0:y1, x0:x1]-b_)**2 <= r_*r_
    from scipy.ndimage import binary_opening, label
    mask = binary_opening(binary_closing(mask, iterations=12), iterations=4); lab, nl = label(mask)
    if nl: sz = np.bincount(lab.ravel())[1:]; mask = np.isin(lab, 1+np.flatnonzero(sz >= .02*sz.max()))
    mp = loadz(FT/'stage1'/STEM/'maps'/f'{CAM}.npz', ['depth', 'owner']); target = mp['depth']; tj = np.full(target.shape, -1, 'i1'); has = mp['owner'] >= 0
    tj[has] = loadz(FT/'targets'/f'{STEM}.npz', ['judge_region'])['judge_region'][mp['owner'][has]]
    from scipy.ndimage import distance_transform_edt
    dist, (iy, ix) = distance_transform_edt(~has, return_indices=True); fill = tj[iy, ix].copy(); fill[dist > 8] = -1   # close gaps between target discs (<= 8 px)
    tj = fill
    from scipy.ndimage import uniform_filter
    cnt = np.stack([uniform_filter((tj == j).astype('f4'), 15) for j in [0, 2, 1, 4]]); maj = np.array([0, 2, 1, 4])[cnt.argmax(0)]; tmap = np.where((tj >= 0) | (cnt.max(0) > .3), maj, -1).astype('i1'); tmap[uniform_filter((tj >= 0).astype('f4'), 15) < .3] = -1
    savez(C3/'img2d.npz', wrong_mask=mask, target_depth=target.astype('f4'), target_judgment=tj, target_judgment_map=tmap)

def gray(depth, valid):
    v = np.clip((DHI-depth)/(DHI-DLO), 0, 1); g = .12+.83*v; img = np.repeat(g[..., None], 3, 2); return np.where(valid[..., None], img, 1.)

def frame3(S, n, prev, out, H):
    it = S.it[n]; B = S.view(180); st = loadz(CA/'static2d.npz'); gs = loadz(CA/'gstatic.npz'); i2 = loadz(C3OLD/'img2d.npz'); d = dict(loadz(DER/'gaussians'/f'{n}.npz')); d['_name'] = n
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
    bld = binary_dilation(tj >= 0, iterations=12); dimg = np.where(bld[..., None], dimg, .25*dimg+.75)   # outside the judgment regions (building) faded, not removed
    panels = [('A 색 감독 신호 (실제 사진)', st['photo'], False), ('B GS 렌더 (색)', rgb, False), ('C 깊이 감독 신호 (선 = 판정 영역)', cimg, True), ('D GS 렌더 깊이 (같은 선)', gray(dep, al & (dep > 0)), True),
              ('E 렌더 깊이가 감독과 다른 곳 |D−C|', dimg, True)]
    for i, (t, img, wr) in enumerate(panels):
        a = fig.add_axes([.004+i*.188, .715, .18, .22]); a.imshow(np.clip(img, 0, 1)); a.axis('off'); a.set_title(t, fontsize=10.5, loc='left', color='#2e3a48', pad=3)
        if wr:
            for j in [0, 2, 1, 4]: a.contour((tj == j).astype(float), levels=[.5], colors=JC[j], linewidths=.9)   # judgment regions as lines only, same on C and D
            a.contour(i2['wrong_mask'].astype(float), levels=[.5], colors=PINK, linewidths=1.3)
        if i == 2:
            a.text(.01, .02, '회색 = 목표 깊이 (D와 같은 눈금)\n선 색 = 깊이 출처 (1 m 안 다수 판정)\n 파랑 일치: 사전 정보·영상 둘 다 (가중 평균)\n 주황 보정: 영상(MVS) · 초록 보존·노랑 결측: 사전 정보\n선 밖: 배경, 영상(MVS)', transform=a.transAxes, fontsize=6.6, color='#2C2C2A', va='bottom',
                   bbox=dict(boxstyle='round,pad=.25', facecolor='white', edgecolor='none', alpha=.85))
        if i == 4:
            a.text(.01, .02, '연회색 = 21 cm 안 (감독을 따름)\n보라 = 21 cm 넘음 (1 m에서 가장 진함)\n건물(판정 영역) 밖은 옅게', transform=a.transAxes, fontsize=6.6, color='#2C2C2A', va='bottom',
                   bbox=dict(boxstyle='round,pad=.25', facecolor='white', edgecolor='none', alpha=.85))
    cb = fig.add_axes([.962, .73, .005, .19]); cb.imshow(np.linspace(1, 0, 100)[:, None]*.83+.12, cmap='gray', vmin=0, vmax=1, aspect='auto', extent=(0, 1, DLO, DHI)); cb.set_xticks([]); cb.yaxis.tick_right(); cb.tick_params(labelsize=7)
    cb.set_title('C·D 깊이\n(m)', fontsize=7, pad=2)
    aF = fig.add_axes([.006, .345, .49, .347]); aE = fig.add_axes([.504, .345, .49, .347]); mk = S.mesh_of(n); img = loadz(C3/f'E_{mk}.npz')['img'].astype(np.float32)/255; d30 = np.load(CA/'D30_180.npy').astype(float)
    draw_E(aE, S, img, B, S.gline, depth=d30); draw_F(aF, S, d, B, d30, prev, S.gline)
    aE.set_title('G 메시 표면 (가우시안으로 만든 결과)'+(f' · 메시: {S.it[mk]:,}회' if mk != n else ''), fontsize=11, loc='left', color='#2e3a48', pad=2); aF.set_title('F 가우시안 + 판정 영역', fontsize=11, loc='left', color='#2e3a48', pad=2)
    aG = fig.add_axes([.04, .105, .52, .195]); g = gs; kind, gl = gline_of(S, n); grd = S.ground
    for j in JC:
        q = g['tg_j'] == j; aG.errorbar(g['tg_s'][q], g['tg_z'][q]-grd, yerr=g['tg_w'][q], fmt='none', ecolor=PALEJ[j], elinewidth=3)
    aG.add_collection(LineCollection(np.stack([g['prior_seg'][:, :, 0], g['prior_seg'][:, :, 1]-grd], 2), colors=PINK, linewidths=1.2, linestyles=(0, (5, 3))))
    aG.scatter(g['gt_s'], g['gt_z']-grd, s=1.2, c='black', lw=0)
    if kind == 'mesh': aG.add_collection(LineCollection(np.stack([gl[:, :, 0], gl[:, :, 1]-grd], 2), colors=NAVY, linewidths=1.2))
    else: aG.plot(gl[0], gl[1]-grd, color=NAVY, lw=1.2)
    gp = d['xyz'].astype(float); pv = (gp[:, :2]-S.c2)@S.gnrm; gm = (pv >= S.gat) & (pv < S.gat+1); gsx = (gp[:, :2]-S.c2)@S.gax; wr = d['group33'] == 1; tag = d['target_tag']
    aG.scatter(gsx[gm & (tag == 0) & ~wr], gp[gm & (tag == 0) & ~wr, 2]-grd, s=3, c=GREYG, lw=0)
    aG.scatter(gsx[gm & (tag == 2) & ~wr], gp[gm & (tag == 2) & ~wr, 2]-grd, s=9, facecolors='none', edgecolors='#2C2C2A', linewidths=.5)
    for j in JC:
        q = gm & (tag == 1) & (d['judgment'] == j) & ~wr; aG.scatter(gsx[q], gp[q, 2]-grd, s=5, c=JDARK[j], lw=0)
    aG.scatter(gsx[gm & wr], gp[gm & wr, 2]-grd, s=22, c=PINK, edgecolors='white', linewidths=.6, zorder=6)
    aG.set_xlim(g['gt_s'].min()-1, g['gt_s'].max()+1); aG.set_ylim(12, 25.5); aG.set_xlabel('건물 가로 방향 (m)', fontsize=9); aG.set_ylabel('지면 위 높이 (m)', fontsize=9); aG.tick_params(labelsize=8)
    aG.set_title('H 가로 단면 (긴 방향 28 m) · 면 선: '+('메시' if kind == 'mesh' else '렌더 깊이'), fontsize=11, loc='left', color='#2e3a48', pad=2)
    hs = H['states']; nn = [m for m in S.names if not m.endswith('pre_reset')]; h = fig.add_axes([.63, .105, .31, .195])
    post = [m for m in S.names if 'wrong_site_fit_pct' in hs[m] and hs[m]['iteration'] in (3000, 6000, 9000, 12000) and not m.endswith('pre_reset')]
    for m in post:
        if hs[m]['iteration'] <= it: h.scatter([hs[m]['iteration']], [hs[m]['wrong_site_fit_pct']], s=30, facecolors='white', edgecolors=NAVY, zorder=5, label='되돌림 직후')
    kx = np.array([hs[m]['iteration'] for m in S.names if 'wrong_site_fit_pct' in hs[m] and m not in post], float); ky = np.array([hs[m]['wrong_site_fit_pct'] for m in S.names if 'wrong_site_fit_pct' in hs[m] and m not in post])
    o = np.argsort(kx, kind='stable'); kx, ky = kx[o], ky[o]; h.plot(kx, ky, color=NAVY, lw=1.6, marker='o', ms=3, alpha=.25); mm = kx <= it; h.plot(kx[mm], ky[mm], color=NAVY, lw=1.8, marker='o', ms=4, label='메시 면이 참값에 맞는 비율 (%)')
    h.set_ylim(0, 102); h.set_xlim(-300, 30300); h.axvline(it, color='#2e3a48', lw=1); h.set_xticks([0, 3000, 7000, 15000, 30000]); h.set_xticklabels(['0', '3,000', '7,000', '15,000', '30,000']); h.tick_params(labelsize=8)
    h2 = h.twinx(); xs = np.array([hs[m]['iteration'] for m in nn], float); ys = np.array([hs[m]['wrong_alive'] for m in nn], float); h2.plot(xs, ys, color=PINK, lw=1.4, ls='--', alpha=.25); m2 = xs <= it
    h2.plot(xs[m2], ys[m2], color=PINK, lw=1.6, ls='--', label='옛 지붕 출신 가우시안 수 (오른쪽)'); h2.set_ylim(0, 3700); h2.tick_params(labelsize=8, colors=PINK)
    a1_, b1_ = h.get_legend_handles_labels(); a2_, b2_ = h2.get_legend_handles_labels(); h.legend(a1_+a2_, b1_+b2_, fontsize=8, frameon=False, loc='center right')
    h.set_title('I 판단이 틀린 자리 (분홍 윤곽)', fontsize=11, loc='left', color='#2e3a48', pad=2)
    hd = [Patch(color=PALEJ[j], label=f'{JN[j]} 영역 (F 바탕)') for j in [0, 2, 1, 4]]+[Patch(color=JC[j], label=f'{JN[j]} 면·묶인 가우시안') for j in [0, 2, 1, 4]]
    hd += [Line2D([], [], marker='o', ls='', markerfacecolor='none', markeredgecolor='#2C2C2A', label='풀림'), Line2D([], [], marker='o', ls='', color=GREYG, label='자유'),
           Line2D([], [], marker='o', ls='', color=PINK, label='옛 지붕·틀린 판정 자리'), Line2D([], [], marker='x', ls='', color='#5F5E5A', label='지워짐'), Patch(color=NEUTRAL, label='판정 영역 밖 면'),
           Patch(color=P1, label='어긋남: 면은 참값에서, E는 감독에서 21 cm 넘게'), Line2D([], [], color=NAVY, label='면 · 단면 위치'), Line2D([], [], marker='o', ls='', color='black', ms=3, label='참값')]
    fig.legend(handles=hd, loc='lower center', ncol=9, frameon=False, fontsize=8.6, bbox_to_anchor=(.5, -.005), handlelength=1.1, columnspacing=.9)
    fig.savefig(out, facecolor='white'); plt.close(fig)

def frames3(k, nchunks):
    S = Ctx(); F3.mkdir(parents=True, exist_ok=True); H = json.loads((CA/'H.json').read_text()); items = []; prev = None
    for n in S.names: items.append(dict(name=n, prev=prev, hold=n in HOLD3, file=f'frames/{len(items):03d}_{n}.png')); prev = n
    for i, it_ in enumerate(items):
        if i % int(nchunks) != int(k) or (V3/it_['file']).exists(): continue
        frame3(S, it_['name'], it_['prev'], V3/it_['file'], H); print('FRAME3', i, it_['name'], flush=True)
    if int(k) == 0: dump(V3/'frames.json', dict(at=now(), items=items, fps=4, hold_s=1.5, camera='az 180 el 35 orthographic, fixed', plate='새 판 (다시 돌린 판)', scientific_verdict=None))

if __name__ == '__main__':
    a = sys.argv[1:]
    if a[0] == 'prep': prep3()
    elif a[0] == 'frames': frames3(a[1], a[2])
    elif a[0] == 'one':
        S = Ctx(); F3.mkdir(parents=True, exist_ok=True); frame3(S, a[1], a[2] if len(a) > 2 else None, V3/f'test_{a[1]}.png', json.loads((CA/'H.json').read_text()))
