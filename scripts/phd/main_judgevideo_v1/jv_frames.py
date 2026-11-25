"""PHD-MAIN-JUDGEVIDEO-v1 judgment frames (CPU, no training, no new judgment). The 'judgment' section between the input and iteration 0 of the TRAINLOG-v1
concept video v2 r6 (B173nb_b10, ALS). Same 1920 x 1080 layout, camera, oblique view, zones, section bands and colours as cv2_frames.py (CV2_VARIANT=r6):
the input-frame drawing functions of cv2_frames (Frame, raster, show_prior, mvs_points, section) are imported and used unchanged; this file only adds the
stored patch judgments (jv_prep.py -> /out/scene_patches_ALS.npz) on top.
  steps    1 image depth present (missing yellow, sight-check removed grey hatch) | 2 change detection (agree light blue) | 3 follow the image (small
           difference: light blue with dots = agree target; large: orange = image depth) | 4 image check (returned to the prior: green) | result.
           A patch decided in an earlier step keeps its colour; the patches decided in this step get a dark edge (bold). Not decided = not painted
           (grey in the map and the ① depth-target panel).
  ① depth target  this camera's target-height image in grey; decided patches projected into the camera (pinhole of cv2_frames.Static) in their colour.
  ② input 3D      prior surface (alpha 0.6) + image-depth points (as the input frame) + the patch squares (side sqrt(area), on the prior surface:
                  centre + normal x prior_height) in the oblique orthographic view, hidden ones (behind the prior surface by > 0.3 m) not drawn.
  ② map           the same squares seen from above (x east, y north), building scope, + a bar of the area share of each judgment decided so far.
  ③ sections      the input-frame section layers (GT, prior cut, image depth) + for every patch whose centre is within the 0.5 m band: from step 2 a grey
                  +-L band around the prior height (vertical extent L x |n_z|), and for the decided patches a short line at the target height of its
                  final judgment (agree / small difference: precision-weighted mean, image depth, prior) in its colour.
Fade: the new colour goes from alpha FADE[0] to 1 in FADE_FRAMES frames (0.5 s), then holds. scientific_verdict: null"""
import os, sys, json, time
sys.path.insert(0, '/repo/scripts/phd/main_trainlog_v1')
os.environ.setdefault('CV2_VARIANT', 'r6')
import cv2_frames as cf
from cv2_frames import *   # noqa: F401,F403  (np, plt, Path, loadz, sha, dump, now, in_zone, scope_mask ...)
from matplotlib.collections import PolyCollection, LineCollection
from matplotlib.patches import FancyArrowPatch
OUT = Path('/out'); JD = Path('/jdocs'); FRD = OUT/'frames'
SC = {1: '#E8B931', 11: '#B4B2A9', 2: '#7FA7D9', 3: '#7FA7D9', 31: '#D85A30', 4: '#1D9E75', 5: '#8C8A82'}
SN = {1: '결측', 11: '제거(시선 검사)', 2: '일치', 3: '작은 차이(일치 목표)', 31: '영상 따름', 4: '되돌림(영상 점검)', 5: '그 밖(L 없음)', 0: '아직 안 정함'}
HATCH = {11: '////', 3: '..'}
STAGES = ['j1', 'j2', 'j3', 'j4', 'res']
STITLE = {'j1': '판단 ① 영상 깊이 유무', 'j2': '판단 ② 변화 탐지', 'j3': '판단 ③ 영상 따름', 'j4': '판단 ④ 영상 점검', 'res': '판단 결과'}
NEW = {'j1': (1, 11), 'j2': (2,), 'j3': (3, 31), 'j4': (4,), 'res': ()}
UNDEC = '#DDDBD3'; BAR_ORDER = [1, 11, 2, 3, 31, 4, 5, 0]

def stage_colours(step, stage):
    """Category of each patch as shown at this stage (0 = not decided yet). At j3 the later-returned patches are still 'follow the image'."""
    k = STAGES.index(stage); c = np.zeros(len(step), int)
    if k >= 0: c[np.isin(step, [1, 11])] = step[np.isin(step, [1, 11])]
    if k >= 1: c[step == 2] = 2
    if k >= 2: c[step == 3] = 3; c[np.isin(step, [31, 4])] = 31
    if k >= 3: c[step == 4] = 4
    if k >= 4: c[step == 0] = 5   # result: the stored judgments that no step above names (rule in jv_prep / issues)
    return c

def quads(p):
    n = p['normal']; t1 = p['tangent1']; t2 = np.cross(n, t1); h = np.sqrt(p['area'])[:, None]/2; c = p['centre']+n*p['prior_h'][:, None]
    return np.stack([c-h*t1-h*t2, c+h*t1-h*t2, c+h*t1+h*t2, c-h*t1+h*t2], 1)

def put(ax, Q2, cat, new, alpha, vis=None, lw_new=.5, dark=False):
    """Q2: (N, 4, 2) screen quads; draw each category, new ones with alpha and a dark edge."""
    for k in BAR_ORDER[:-1]:
        m = cat == k
        if vis is not None: m &= vis
        if not m.any(): continue
        isnew = new & m; old = m & ~new
        for sel, a, ec, lw in [(old, 1., 'none', 0), (isnew, alpha, '#2C2C2A' if dark else tuple(.62*np.array(to_rgb(SC[k]))), lw_new)]:
            if not sel.any(): continue
            pc = PolyCollection(Q2[sel], facecolors=SC[k], edgecolors=ec if ec != 'none' else SC[k], linewidths=lw if lw else .15, alpha=a, zorder=9 if sel is isnew else 8)
            if k in HATCH: pc.set_hatch(HATCH[k]); pc.set_edgecolor('#5F5E5A' if k == 11 else '#1F3F6F')
            ax.add_collection(pc)

def visible(F, P, dep, ext, view=None):
    x, y, d = F.S.proj(P, *(view or (None, None))); Hp, Wp = dep.shape; x0, x1, y0, y1 = ext
    ci = np.clip(((x-x0)/(x1-x0)*Wp).astype(int), 0, Wp-1); ri = np.clip(((y1-y)/(y1-y0)*Hp).astype(int), 0, Hp-1)
    return (x >= x0) & (x <= x1) & (y >= y0) & (y <= y1) & (d <= dep[ri, ci]+.3)

def draw(F, stage, alpha, png, cache, p):
    S = F.S; st = F.st; t0 = time.monotonic(); fig = F.fig = plt.figure(figsize=(W_/100, H_/100), dpi=100, facecolor='white')
    cat = stage_colours(p['step'], stage); new = np.isin(cat, NEW[stage]); Q = cache['Q']
    fig.text(16/W_, 1-24/H_, f'{BNAME} · {STITLE[stage]}', fontsize=19, color=NAVY, va='center', fontweight='bold')
    # progress row: 입력, ①-④, 0 ... 30,000 (the r6 row with four dots inserted)
    labs = ['input', 'j1', 'j2', 'j3', 'j4']+cf.STATES; xs = np.linspace(1000, 1890, len(labs)); cur = labs.index('j4' if stage == 'res' else stage)
    ax = fig.add_axes([0, 1-44/H_, 1, 44/H_]); ax.set_xlim(0, W_); ax.set_ylim(44, 0); ax.axis('off'); ax.plot([xs[0], xs[-1]], [16, 16], color='#D3D1C7', lw=1, zorder=1)
    for i, (x, f) in enumerate(zip(xs, labs)):
        col, sz = (NAVY, 11) if i == cur else (('#9C9A92', 7) if i < cur else ('#E3E1D9', 7)); judge = f.startswith('j')
        ax.plot(x, 16, 's' if judge else 'o', ms=sz-(1 if judge else 0), color=col, mec='white' if i != cur else NAVY, zorder=3)
        t = {'input': '입력', 'j1': '①', 'j2': '②', 'j3': '③', 'j4': '④'}.get(f, f'{int(f):,}' if not judge and f != 'input' else f)
        ax.text(x, 36, t, ha='center', va='center', fontsize=8.5 if i != cur else 9.5, color=NAVY if i == cur else '#77756D', fontweight='bold' if i == cur else 'normal')
    fit = np.array([int(f) for f in cf.STATES], float)
    for n in cf.RESETS: ax.plot(np.interp(n, fit, xs[5:]), 5, 'v', ms=5.5, color=cf.RESC, mec='white', mew=.4, zorder=4)
    ax.text((xs[-2]+xs[-1])/2, 16, '≈', ha='center', va='center', fontsize=12, color='#77756D', zorder=5, bbox=dict(boxstyle='square,pad=.05', fc='white', ec='none'))
    # ① camera 2x2
    u0, v0, u1, v1 = st['crop']; ph = 250; pw = int(round(ph*(u1-u0)/(v1-v0))); X0, Y0 = 16, 66; gap = 8
    a = F.axes(X0, Y0, pw, ph, '① 사진'); F.cam(a, cache['photo'])
    a = F.axes(X0, Y0+ph+24, pw, ph, '① 깊이 목표'); F.cam(a, cache['grey'], zones=False)
    u, v, zc = S.pix(Q.reshape(-1, 3)); Qc = np.stack([u, v], 1).reshape(-1, 4, 2); okc = (zc.reshape(-1, 4) > 0).all(1)
    put(a, Qc, np.where(okc, cat, 0), new, alpha, lw_new=.3)
    for k_, z in S.zones.items():
        ring = np.asarray(F.sj['zones'][str(k_)]['box_polygon_xy']); P_ = np.c_[ring, np.full(len(ring), F.sj['zones'][str(k_)]['outline_z'])]; uu, vv, _ = S.pix(P_)
        a.plot(np.r_[uu, uu[:1]], np.r_[vv, vv[:1]], color='white', lw=2.2, zorder=15); a.plot(np.r_[uu, uu[:1]], np.r_[vv, vv[:1]], color=NAVY, lw=1.0, zorder=16)
        F.badge(a, uu[np.argmax(vv)], vv.max()+14, k_) if k_ == 1 else F.badge(a, uu.mean(), vv.min()-14, k_)
    a.set_xlim(u0, u1); a.set_ylim(v1, v0)
    F.blank(F.axes(X0+pw+gap, Y0, pw, ph, '① 렌더')); F.blank(F.axes(X0+pw+gap, Y0+ph+24, pw, ph, '① 렌더 깊이'))
    ar = FancyArrowPatch(((X0+2*pw+gap+6)/W_, 1-(Y0+ph+12)/H_), ((X0+2*pw+gap+46)/W_, 1-(Y0+ph+12)/H_), transform=fig.transFigure, arrowstyle='-|>', mutation_scale=22, color=NAVY, lw=2); fig.patches.append(ar)
    # ② input 3D
    X2 = X0+2*pw+gap+56; w2 = (W_-16-X2-12)//2; h2 = 2*ph+24; ext = cache['ext']
    ag = F.axes(X2, Y0, w2, h2, '② 입력 3D: 사전 정보 면 · 영상 깊이 점 · 패치 판정')
    img, dep = cache['prior_overview']; F.show_prior(ag, img, dep, ext); F.mvs_points(ag, dep, ext, w2, h2, 2, 1.2)
    x, y, d = S.proj(Q.reshape(-1, 3)); Q2 = np.stack([x, y], 1).reshape(-1, 4, 2); dd = d.reshape(-1, 4).mean(1); o = np.argsort(-dd)
    put(ag, Q2[o], cat[o], new[o], alpha, vis=cache['vis_ov'][o], lw_new=.35); F.zone_outline(ag, 1); F.zone_outline(ag, 2)
    if stage == 'j1':
        m = new & cache['vis_ov']; ag.scatter(Q2[m].mean(1)[:, 0], Q2[m].mean(1)[:, 1], s=60, facecolors='none', edgecolors=[SC[c_] for c_ in cat[m]], linewidths=1.1, alpha=alpha, zorder=12)
    # ② map (top view) + bar
    hm = h2-92; am = F.axes(X2+w2+12, Y0, w2, hm, '② 판정 지도 · 위에서 본 패치')
    M2 = Q[:, :, :2]; am.add_collection(PolyCollection(M2[cat == 0], facecolors=UNDEC, edgecolors=UNDEC, linewidths=.1, zorder=2))
    put(am, M2, cat, new, alpha, lw_new=.3)
    if stage == 'j1': am.scatter(M2[new].mean(1)[:, 0], M2[new].mean(1)[:, 1], s=40, facecolors='none', edgecolors=[SC[c_] for c_ in cat[new]], linewidths=1., alpha=alpha, zorder=12)
    fp = np.asarray(S.c['scope']['footprint']['coordinates'][0], float)[:, :2]; am.plot(fp[:, 0], fp[:, 1], color='#5F5E5A', lw=.7, ls=(0, (3, 2)), zorder=10)
    for k_ in (1, 2):
        ring = np.asarray(F.sj['zones'][str(k_)]['box_polygon_xy']); am.plot(np.r_[ring[:, 0], ring[:1, 0]], np.r_[ring[:, 1], ring[:1, 1]], color='white', lw=2.4, zorder=15)
        am.plot(np.r_[ring[:, 0], ring[:1, 0]], np.r_[ring[:, 1], ring[:1, 1]], color=NAVY, lw=1.1, zorder=16); F.badge(am, ring[:, 0].mean(), ring[:, 1].max()+2.5, k_, 10)
    mx = cache['map_ext']; am.set_xlim(mx[0], mx[1]); am.set_ylim(mx[2], mx[3]); am.set_aspect('equal')
    am.text(.99, .02, '↑ 북', transform=am.transAxes, ha='right', va='bottom', fontsize=8, color='#5F5E5A')
    ab = F.axes(X2+w2+12, Y0+hm+30, w2, 62, f'넓이 비율 (장면 패치 {cache["Atot"]:,.0f} m², 지금까지 정해진 판정)')
    A = p['area']; x0_ = 0.
    for k in BAR_ORDER:
        frac = A[cat == k].sum()/cache['Atot']
        if frac <= 0: continue
        r = plt.Rectangle((x0_, 0), frac, 1, fc=UNDEC if k == 0 else SC[k], ec='white', lw=.6, alpha=alpha if (k in NEW[stage] and k) else 1.)
        if k in HATCH: r.set_hatch(HATCH[k])
        ab.add_patch(r)
        if frac >= .035: ab.text(x0_+frac/2, .5, f'{100*frac:.1f} %', ha='center', va='center', fontsize=9, color='#2C2C2A' if k in (0, 1, 2, 3, 11) else 'white', fontweight='bold' if k in NEW[stage] else 'normal')
        x0_ += frac
    small = [f'{SN[k]} {100*A[cat == k].sum()/cache["Atot"]:.1f} %' for k in BAR_ORDER if 0 < A[cat == k].sum()/cache['Atot'] < .035]
    if small: fig.text((X2+w2+12+w2)/W_, 1-(Y0+hm+27)/H_, ' · '.join(small), ha='right', va='bottom', fontsize=8.5, color='#2C2C2A')
    ab.set_xlim(0, 1); ab.set_ylim(0, 1)
    # zone rows
    wz, ws, gz = 262, (W_-32-3*262-4*12)//2, 12; hz = 192
    for row, k in enumerate((1, 2)):
        Y = 616+row*226; zj = F.sj['zones'][str(k)]; zext = F.frame_ext(zj['zoom_extent'], wz, hz, .06); zv = (np.asarray(zj['zoom_basis']), np.asarray(zj['zoom_centre'])); cn = cf.COMP[k]['name']
        xg = 16; xm = xg+wz+gz; xs1 = xm+wz+gz; xs2 = xs1+ws+gz; xc = xs2+ws+gz
        a_g = F.axes(xg, Y, wz, hz, f'②-{k} 입력 확대 · {cf.ZNAME[k]}'); F.blank(F.axes(xm, Y, wz, hz, f'②-{k} 메시 확대'))
        a_s = F.axes(xs1, Y, ws, hz, f'③-{k} 본 방법 단면'); a_c = F.axes(xs2, Y, ws, hz, f'③-{k} 비교 단면 · {cn} · 판단 구간'); F.blank(a_c); F.blank(F.axes(xc, Y, wz, hz, f'③-{k} 비교 메시 확대 · {cn}'))
        zimg, zdep = cache[f'prior_zoom{k}']; F.show_prior(a_g, zimg, zdep, zext); F.mvs_points(a_g, zdep, zext, wz, hz, 3, 5, zone=k, view=zv)
        zsel = cache[f'zsel{k}']; x, y, d = S.proj(Q[zsel].reshape(-1, 3), *zv); Qz = np.stack([x, y], 1).reshape(-1, 4, 2); dz = d.reshape(-1, 4).mean(1); o = np.argsort(-dz)
        put(a_g, Qz[o], cat[zsel][o], new[zsel][o], alpha, vis=cache[f'vis_z{k}'][o], lw_new=.6, dark=True)
        F.section(a_s, k, layers=('gt', 'prior', 'mvs'))
        b = cache[f'band{k}']; Yf = lambda h: F.ymap(k, h); cb = cat[b['i']]
        if STAGES.index(stage) >= 1:   # +-L band of every patch in the band (grey)
            ok = np.isfinite(b['L']); a_s.add_collection(PolyCollection([[(s0-b['w'][j], Yf(h-l)), (s0+b['w'][j], Yf(h-l)), (s0+b['w'][j], Yf(h+l)), (s0-b['w'][j], Yf(h+l))]
                                                                         for j, (s0, h, l) in enumerate(zip(b['s'], b['hp'], b['L']*b['nz'])) if ok[j]], facecolors='#9C9A92', edgecolors='none', alpha=.18, zorder=3.5))
        segs, cols, lws = [], [], []
        for j in np.flatnonzero(cb > 0):
            segs.append([(b['s'][j]-b['w'][j], Yf(b['ht'][j])), (b['s'][j]+b['w'][j], Yf(b['ht'][j]))]); cols.append(SC[cb[j]] + ('' if not new[b['i'][j]] else '')); lws.append(2.4 if new[b['i'][j]] else 1.6)
        if segs:
            al = np.where(new[b['i']][cb > 0], alpha, 1.); rgba = [(*to_rgb(c_), a_) for c_, a_ in zip(cols, al)]
            a_s.add_collection(LineCollection(segs, colors=rgba, linewidths=lws, zorder=6, capstyle='butt'))
    # legend
    lax = fig.add_axes([0, 0, 1, 34/H_]); lax.axis('off'); lax.set_xlim(0, W_); lax.set_ylim(0, 34); x = 16
    items = [('pt', GTC, '참값'), ('dash', PRC, '사전 정보'), ('pt', MVC, '영상 깊이'), ('box', SC[1], '결측'), ('hbox', 11, '제거(시선 검사)'), ('box', SC[2], '일치'), ('hbox', 3, '작은 차이(일치 목표)'),
             ('box', SC[31], '영상 따름(보정)'), ('box', SC[4], '되돌림(영상 점검)'), ('box', SC[5], '그 밖(L 없음)'), ('box', UNDEC, '아직 안 정함'), ('edge', '#2C2C2A', '이번 단계'), ('lband', '#9C9A92', '±L'), ('line', NAVY, '구역 상자')]
    for kind, col, txt in items:
        if kind == 'pt': lax.plot(x+5, 17, 'o', ms=4.5, color=col)
        elif kind == 'box': lax.add_patch(plt.Rectangle((x, 11), 11, 12, color=col))
        elif kind == 'hbox': r = plt.Rectangle((x, 11), 11, 12, fc=SC[col], ec='#5F5E5A' if col == 11 else '#1F3F6F', lw=.5, hatch=HATCH[col]); lax.add_patch(r)
        elif kind == 'edge': lax.add_patch(plt.Rectangle((x, 11), 11, 12, fc='white', ec=col, lw=1.2))
        elif kind == 'lband': lax.add_patch(plt.Rectangle((x, 8), 11, 18, fc=col, alpha=.3, ec='none'))
        else: lax.plot([x, x+18], [17, 17], color=col, lw=1.6, ls={'dash': (0, (3, 2)), 'line': '-'}[kind])
        x += 14 if kind in ('pt', 'box', 'hbox', 'edge', 'lband') else 22; t = lax.text(x, 17, txt, fontsize=9, va='center', color='#2C2C2A'); x += t.get_window_extent(fig.canvas.get_renderer()).width+14
    png.parent.mkdir(parents=True, exist_ok=True); fig.savefig(png, dpi=100, facecolor='white'); plt.close(fig)
    return round(time.monotonic()-t0, 1)

def prepare(F):
    S = F.S; st = F.st; p = loadz(OUT/'scene_patches_ALS.npz'); cache = dict(p=p); Q = quads(p); cache['Q'] = Q; cache['Atot'] = float(p['area'].sum())
    inp = loadz(Path('/tl')/'concept/inputs.npz', ['photo']); cache['photo'] = inp['photo'].astype(float)/255.
    g = F.hrgb(st['ht']); lum = g@np.array([.3, .59, .11]); cache['grey'] = np.where(np.isfinite(st['ht'])[..., None], (.55+.4*lum)[..., None].repeat(3, -1), 1.)
    u0, v0, u1, v1 = st['crop']; ph = 250; pw = int(round(ph*(u1-u0)/(v1-v0))); X0 = 16; gap = 8; X2 = X0+2*pw+gap+56; w2 = (W_-16-X2-12)//2; h2 = 2*ph+24
    ext = F.frame_ext(F.sj['oblique']['overview_extent'], w2, h2, .03); cache['ext'] = ext
    cache['prior_overview'] = F.raster(F.PV, F.PFs, None, ext, w2, h2, 2, PRIOR_RGB); C0 = Q.mean(1)
    cache['vis_ov'] = visible(F, C0, cache['prior_overview'][1], ext)
    fp = np.asarray(S.c['scope']['footprint']['coordinates'][0], float)[:, :2]; bx = np.r_[fp.min(0)-3, fp.max(0)+3]; hm = h2-92
    cache['map_ext'] = F.frame_ext((bx[0], bx[2], bx[1], bx[3]), w2, hm, .02)
    wz, hz = 262, 192
    for k in (1, 2):
        zj = F.sj['zones'][str(k)]; zext = F.frame_ext(zj['zoom_extent'], wz, hz, .06); zv = (np.asarray(zj['zoom_basis']), np.asarray(zj['zoom_centre']))
        fsel = in_zone(F.PV[F.PF].mean(1), S.zones[k], S.zr); cache[f'prior_zoom{k}'] = F.raster(F.PV, F.PF[fsel], None, zext, wz, hz, 3, PRIOR_RGB, view=zv)
        zsel = in_zone(C0, S.zones[k], S.zr); cache[f'zsel{k}'] = zsel; cache[f'vis_z{k}'] = visible(F, C0[zsel], cache[f'prior_zoom{k}'][1], zext, zv)
        z = S.zones[k]; s, vv = cf.sv(C0, z); bi = np.flatnonzero((np.abs(vv) <= cf.BAND) & (s >= -.5) & (s <= z['L']+.5))
        n = p['normal'][bi]; hp = C0[bi, 2]-S.ground; ht = (p['centre'][bi]+n*p['target_h'][bi][:, None])[:, 2]-S.ground
        cache[f'band{k}'] = dict(i=bi, s=s[bi], hp=hp, ht=ht, L=p['L'][bi], nz=np.abs(n[:, 2]), w=np.sqrt(p['area'][bi])/2)
    return cache

FADE = [.2, .4, .6, .8]; FADE_FRAMES = 12; HOLD_FRAMES = 38; RES_FRAMES = 50
def main(mode):
    F = Frame(); t0 = time.monotonic(); cache = prepare(F); p = cache['p']; rec = dict(at=now(), rule=__doc__, frames=[], scientific_verdict=None)
    print('PREP', round(time.monotonic()-t0, 1), flush=True)
    if mode.startswith('test:'):
        for stage in mode[5:].split(','): print('TEST', stage, draw(F, stage, 1., OUT/'test'/f'{stage}.png', cache, p), flush=True)
        return
    stages = STAGES if mode == 'all' else mode.split(',')
    for stage in stages:
        if stage == 'res': plan = [(1., RES_FRAMES)]
        else: plan = [(a, FADE_FRAMES//len(FADE)) for a in FADE]+[(1., HOLD_FRAMES)]
        for i, (a, nrep) in enumerate(plan):
            png = FRD/f'{stage}_{i}.png'; s = draw(F, stage, a, png, cache, p); rec['frames'].append(dict(stage=stage, alpha=a, repeat=nrep, png=str(png), sha256=sha(png), seconds=s))
            print('FRAME', stage, a, s, flush=True)
    dump(OUT/f'frames_{mode.replace(",", "_")}.json', rec)

if __name__ == '__main__': main(sys.argv[1] if len(sys.argv) > 1 else 'all')
