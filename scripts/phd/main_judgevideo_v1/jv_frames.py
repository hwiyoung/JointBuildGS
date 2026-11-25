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

def quads_h(p, h):
    n = p['normal']; t1 = p['tangent1']; t2 = np.cross(n, t1); w = np.sqrt(p['area'])[:, None]/2; c = p['centre']+n*h[:, None]
    return np.stack([c-w*t1-w*t2, c+w*t1-w*t2, c+w*t1+w*t2, c-w*t1+w*t2], 1)

def shown_h(p, stage):
    """v2 (user 11-25: 'which target each step selects must show, e.g. the gable disappears and the flat roof is chosen'): the height each patch stands at
    after this stage. Not decided yet = prior height (so the first picture is the old prior roof). Decided = the target of its stored judgment
    (jv_prep target_h: agree / small difference = precision-weighted mean, image depth = mvs mean, prior = prior); at j3 the patches returned at j4 stand
    at the image depth, at j4 they go back to the prior height."""
    hP = p['prior_h']; hM = np.where(np.isfinite(p['mvs_h']), p['mvs_h'], hP); tg = np.where(np.isfinite(p['target_h']), p['target_h'], hP); step = p['step']
    k = -1 if stage == 'start' else STAGES.index(stage); h = hP.copy()
    if k >= 1: h[step == 2] = tg[step == 2]
    if k >= 2: m = step == 3; h[m] = tg[m]; m = np.isin(step, [31, 4]); h[m] = hM[m]
    if k >= 3: h[step == 4] = tg[step == 4]
    if k >= 4: h[step == 0] = tg[step == 0]
    return h

UNDEC_3D = '#F2B872'
RULE = {'j1': '근거: 패치 원통 안 영상 깊이 점이 4개 미만 → 영상 후보 없음, 사전 정보만 남김 (시선 검사로 지운 점 포함)',
        'j2': '근거: 두 후보의 차이 |d| 가 검출 한계 L 안 → 같은 면(일치), 두 후보의 가중 평균을 남김',
        'j3': '근거: 차이가 유의할 때 |d| < 1.10 m(혼합 경계) → 작은 차이, 일치 목표 / |d| ≥ 1.10 m → 영상 후보를 남김',
        'j4': '근거: 다시점 일치 점 < 4(광도 반박 아님) 또는 광도가 사전 정보 지지 → 되돌림',
        'res': '판단 결과: 패치마다 남은 후보 하나 = 학습의 깊이 목표'}
def layers(p, cat):
    """candidates shown for each category: 0 = both candidates faint (prior tan, image green); decided = the kept candidate in its judgment colour."""
    hP = p['prior_h']; hM = p['mvs_h']; tg = np.where(np.isfinite(p['target_h']), p['target_h'], hP); L = []
    m0 = cat == 0; L += [(m0, hP, UNDEC_3D, .45), (m0 & np.isfinite(hM), hM, cf.MVC, .45)]
    for k, h in [(1, hP), (11, hP), (2, tg), (3, tg), (31, hM), (4, hP), (5, tg)]: L.append((cat == k, h, SC[k], 1.))
    return L
def cand(p, cat, prevcat, new, a):
    """all quads of this frame: (h, rgb, alpha, patch index). Non-new patches: their layers. New: previous layers fading out, new layers fading in."""
    H, C, A, I = [], [], [], []
    for which, cc, f in [(~new, cat, 1.), (new, prevcat, 1-a), (new, cat, a)]:
        for m, h, col, al in layers(p, cc):
            mm = m & which & np.isfinite(h)
            if not mm.any() or al*f <= .01: continue
            ix = np.flatnonzero(mm); H.append(h[ix]); C.append(np.broadcast_to(to_rgb(col), (len(ix), 3))); A.append(np.full(len(ix), al*f)); I.append(ix)
    return np.concatenate(H), np.concatenate(C), np.concatenate(A), np.concatenate(I)
def paint_c(ax, S, p, cq, view=None, sel=None, new=None, zorder=9):
    H, C, A, I = cq
    if sel is not None: k = sel[I]; H, C, A, I = H[k], C[k], A[k], I[k]
    sub = {kk: p[kk][I] for kk in ('normal', 'tangent1', 'area', 'centre')}; Q = quads_h(sub, H); x, y, d = S.proj(Q.reshape(-1, 3), *(view or (None, None)))
    Q2 = np.stack([x, y], 1).reshape(-1, 4, 2); o = np.argsort(-d.reshape(-1, 4).mean(1)); nw = new[I] if new is not None else np.zeros(len(I), bool)
    ec = np.where(nw[:, None], .6*C, C)
    ax.add_collection(PolyCollection(Q2[o], facecolors=np.c_[C, A][o], edgecolors=np.c_[ec, A][o], linewidths=np.where(nw, .35, .1)[o], zorder=zorder))
def paint(ax, Q2, d, cat, new, alpha, lw_new=.35, zorder=9):
    """One painter-sorted collection (far first): not decided = prior colour at alpha .55, decided = its judgment colour, new = fading in with a darker edge;
    hatched categories get a hatch overlay."""
    o = np.argsort(-d); Q2, cat, new = Q2[o], cat[o], new[o]; ok = np.isfinite(Q2).all((1, 2)); Q2, cat, new = Q2[ok], cat[ok], new[ok]
    fc = np.array([to_rgb(UNDEC_3D) if c == 0 else to_rgb(SC[c]) for c in cat]); al = np.where(cat == 0, .55, np.where(new, .35+.65*alpha, 1.))
    ec = np.where(new[:, None], .62*fc, fc); lw = np.where(new, lw_new, .1)
    ax.add_collection(PolyCollection(Q2, facecolors=np.c_[fc, al], edgecolors=np.c_[ec, np.maximum(al, .5)], linewidths=lw, zorder=zorder))
    for k, hp in HATCH.items():
        m = cat == k
        if m.any(): ax.add_collection(PolyCollection(Q2[m], facecolors='none', edgecolors='#5F5E5A' if k == 11 else '#1F3F6F', linewidths=0, hatch=hp, zorder=zorder+.1))

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
    cat = stage_colours(p['step'], stage); new = np.isin(cat, NEW[stage])
    prevcat = np.zeros(len(cat), int) if stage == 'j1' else stage_colours(p['step'], STAGES[STAGES.index(stage)-1]); cq = cand(p, cat, prevcat, new, alpha)
    Q = quads_h(p, shown_h(p, stage))   # map xy and ① (kept candidate; not decided = no target yet)
    fig.text(16/W_, 1-24/H_, f'{BNAME} · {STITLE[stage]}', fontsize=19, color=NAVY, va='center', fontweight='bold')
    fig.text(330/W_, 1-24/H_, RULE[stage], fontsize=10.5, color='#2C2C2A', va='center')
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
    u, v, zc = S.pix(Q.reshape(-1, 3)); Qc = np.stack([u, v], 1).reshape(-1, 4, 2); zc = zc.reshape(-1, 4).mean(1); hz = Q.mean(1)[:, 2]-S.ground
    bi = np.clip(np.searchsorted(F.bins, hz, side='right')-1, 0, cf.NBIN-1); o = np.argsort(-zc); ok = (np.isfinite(Qc).all((1, 2)) & (cat > 0))[o]
    a.add_collection(PolyCollection(Qc[o][ok], facecolors=F.hcol[bi[o][ok]], edgecolors=F.hcol[bi[o][ok]], linewidths=.2, zorder=8))
    for k_, z in S.zones.items():
        ring = np.asarray(F.sj['zones'][str(k_)]['box_polygon_xy']); P_ = np.c_[ring, np.full(len(ring), F.sj['zones'][str(k_)]['outline_z'])]; uu, vv, _ = S.pix(P_)
        a.plot(np.r_[uu, uu[:1]], np.r_[vv, vv[:1]], color='white', lw=2.2, zorder=15); a.plot(np.r_[uu, uu[:1]], np.r_[vv, vv[:1]], color=NAVY, lw=1.0, zorder=16)
        F.badge(a, uu[np.argmax(vv)], vv.max()+14, k_) if k_ == 1 else F.badge(a, uu.mean(), vv.min()-14, k_)
    a.set_xlim(u0, u1); a.set_ylim(v1, v0)
    F.blank(F.axes(X0+pw+gap, Y0, pw, ph, '① 렌더')); F.blank(F.axes(X0+pw+gap, Y0+ph+24, pw, ph, '① 렌더 깊이'))
    ar = FancyArrowPatch(((X0+2*pw+gap+6)/W_, 1-(Y0+ph+12)/H_), ((X0+2*pw+gap+46)/W_, 1-(Y0+ph+12)/H_), transform=fig.transFigure, arrowstyle='-|>', mutation_scale=22, color=NAVY, lw=2); fig.patches.append(ar)
    # ② input 3D
    X2 = X0+2*pw+gap+56; w2 = (W_-16-X2-12)//2; h2 = 2*ph+24; ext = cache['ext']
    ag = F.axes(X2, Y0, w2, h2, '② 입력 3D: 패치마다 두 후보(사전 정보 · 영상 깊이) → 고른 후보만 남김')
    img, dep = cache['prior_overview']; ag.imshow(np.dstack([img, np.where(np.isfinite(dep), .22, 0.)]), extent=ext, zorder=1); ag.set_xlim(ext[0], ext[1]); ag.set_ylim(ext[2], ext[3]); ag.set_aspect('equal')
    F.mvs_points(ag, np.full_like(dep, np.inf), ext, w2, h2, 2, 1.2)
    x, y, d = S.proj(Q.reshape(-1, 3)); Q2 = np.stack([x, y], 1).reshape(-1, 4, 2)
    paint_c(ag, S, p, cq, new=new); F.zone_outline(ag, 1); F.zone_outline(ag, 2)
    if stage == 'j1':
        m = new.copy(); ag.scatter(Q2[m].mean(1)[:, 0], Q2[m].mean(1)[:, 1], s=60, facecolors='none', edgecolors=[SC[c_] for c_ in cat[m]], linewidths=1.1, alpha=alpha, zorder=12)
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
        a_s = F.axes(xs1, Y, ws, hz, f'③-{k} 본 방법 단면'); 
        zimg, zdep = cache[f'prior_zoom{k}']; a_g.imshow(np.dstack([zimg, np.where(np.isfinite(zdep), .22, 0.)]), extent=zext, zorder=1); F.mvs_points(a_g, np.full_like(zdep, np.inf), zext, wz, hz, 3, 5, zone=k, view=zv)
        zsel = cache[f'zsel{k}']; paint_c(a_g, S, p, cq, view=zv, sel=zsel, new=new); a_g.set_xlim(zext[0], zext[1]); a_g.set_ylim(zext[2], zext[3]); a_g.set_aspect('equal')
        F.section(a_s, k, layers=('gt', 'prior', 'mvs'))
        b = cache[f'band{k}']; Yf = lambda h: F.ymap(k, h); cb = cat[b['i']]
        if stage == 'j2':   # evidence of step 2: +-L band of every patch in the band (grey)
            ok = np.isfinite(b['L']); a_s.add_collection(PolyCollection([[(s0-b['w'][j], Yf(h-l)), (s0+b['w'][j], Yf(h-l)), (s0+b['w'][j], Yf(h+l)), (s0-b['w'][j], Yf(h+l))]
                                                                         for j, (s0, h, l) in enumerate(zip(b['s'], b['hp'], b['L']*b['nz'])) if ok[j]], facecolors='#9C9A92', edgecolors='none', alpha=.18, zorder=3.5))
        H, Cc, Aa, I = cq; pos = {int(i): j for j, i in enumerate(b['i'])}; kk = np.array([int(i) in pos for i in I])
        if kk.any():
            jj = np.array([pos[int(i)] for i in I[kk]]); nz = b['nz'][jj]; hh_ = (p['centre'][I[kk], 2]+p['normal'][I[kk], 2]*H[kk])-S.ground
            segs = [[(b['s'][j]-b['w'][j], Yf(h_)), (b['s'][j]+b['w'][j], Yf(h_))] for j, h_ in zip(jj, hh_)]; nw = new[I[kk]]
            a_s.add_collection(LineCollection(segs, colors=np.c_[Cc[kk], Aa[kk]], linewidths=np.where(nw, 3., 2.), zorder=6, capstyle='butt'))
        if stage == 'j3':   # evidence of step 3: +-1.10 m around the prior candidate of the significant patches
            sg = p['sig'][b['i']]; ok3 = sg & np.isfinite(b['hp'])
            a_s.add_collection(LineCollection([[(s0-b['w'][j], Yf(h+1.10*nz_)), (s0+b['w'][j], Yf(h+1.10*nz_))] for j, (s0, h, nz_) in enumerate(zip(b['s'], b['hp'], b['nz'])) if ok3[j]]
                                              + [[(s0-b['w'][j], Yf(h-1.10*nz_)), (s0+b['w'][j], Yf(h-1.10*nz_))] for j, (s0, h, nz_) in enumerate(zip(b['s'], b['hp'], b['nz'])) if ok3[j]], colors='#5F5E5A', linewidths=.6, zorder=5.5))
    ae = F.axes(xs2+50, 616+24, W_-16-xs2-60, 2*hz+226-hz-24-30, '④ 근거: 이 단계가 보는 값(장면 패치 넓이 분포)과 문턱' if stage != 'res' else '판단 결과: 판정 · 근거 · 넓이')
    evidence(ae, stage, p, cat, alpha, cache['Atot'])
    # legend
    lax = fig.add_axes([0, 0, 1, 34/H_]); lax.axis('off'); lax.set_xlim(0, W_); lax.set_ylim(0, 34); x = 16
    items = [('pt', GTC, '참값'), ('dash', PRC, '사전 정보'), ('pt', MVC, '영상 깊이'), ('box', SC[1], '결측'), ('hbox', 11, '제거(시선 검사)'), ('box', SC[2], '일치'), ('hbox', 3, '작은 차이(일치 목표)'),
             ('box', SC[31], '영상 따름(보정)'), ('box', SC[4], '되돌림(영상 점검)'), ('box', SC[5], '그 밖(L 없음)'), ('box', UNDEC_3D, '아직 안 정함(사전 정보 높이)'), ('edge', '#2C2C2A', '이번 단계'), ('lband', '#9C9A92', '±L'), ('line', NAVY, '구역 상자')]
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

def evidence(ax, stage, p, cat, alpha, Atot):
    A = p['area']; ax.tick_params(labelsize=8, colors='#5F5E5A'); ax.set_xticks([]); ax.set_yticks([])
    def hist(x, groups, bins, logx=False, thr=None, thr_lab='', xlab=''):
        bottom = np.zeros(len(bins)-1)
        for m, col, lab, hatch in groups:
            ok = m & np.isfinite(x); h, _ = np.histogram(x[ok], bins=bins, weights=A[ok]); h = 100*h/Atot
            ax.bar(bins[:-1], h, width=np.diff(bins), bottom=bottom, align='edge', color=col, edgecolor='white', lw=.3, hatch=hatch, label=f'{lab}  {100*A[ok].sum()/Atot:.1f} %'); bottom += h
        if logx: ax.set_xscale('log')
        if thr is not None:
            ax.axvline(thr, color=NAVY, lw=1.6, ls='--'); ax.text(thr, .55, f' {thr_lab}', transform=ax.get_xaxis_transform(), color=NAVY, fontsize=11, va='center', ha='left', fontweight='bold', bbox=dict(fc='white', ec='none', pad=1))
        ax.set_xlabel(xlab, fontsize=9, color='#2C2C2A'); ax.set_ylabel('넓이 %', fontsize=9, color='#2C2C2A'); ax.tick_params(axis='both', labelsize=8, length=2)
        ax.legend(loc='upper right', fontsize=9, frameon=False)
    sig = p['sig']; n = p['n'].astype(float); dabs = np.abs(p['d']); L = p['L']
    if stage == 'j1':
        hist(np.minimum(n, 40), [(n < 4, SC[1], '영상 점 < 4 → 사전 정보만', None), (n >= 4, '#C9C6BC', '영상 점 ≥ 4 → 다음 단계로', None)], np.arange(0, 41, 1), thr=4, thr_lab='문턱 4개', xlab='패치 원통 안 영상 깊이 점 수 (40 이상은 40)')
    elif stage == 'j2':
        r = dabs/L; inn = (n >= 4) & np.isfinite(r)
        hist(np.clip(r, .01, 100), [(inn & ~sig, SC[2], '|d| ≤ L: 일치 → 가중 평균', None), (inn & sig, '#C9C6BC', '|d| > L: 유의한 차이 → 다음 단계로', None)], np.logspace(-2, 2, 41), True, 1., '|d| = L', '두 후보 차이 ÷ 검출 한계 (|d| / L, 로그)')
    elif stage == 'j3':
        hist(np.clip(dabs, .02, 20), [(sig & (p['mix'] == 0), SC[3], '|d| < 1.10 m: 작은 차이 → 일치 목표', '..'), (sig & (p['mix'] == 1), SC[31], '|d| ≥ 1.10 m: 영상 후보를 남김', None)], np.logspace(np.log10(.02), np.log10(20), 41), True, 1.10, '1.10 m', '유의한 패치의 두 후보 차이 |d| m (로그)')
    elif stage == 'j4':
        big = sig & (p['mix'] == 1); a2 = np.minimum(p['a2n'].astype(float), 30); ph = p['photo']
        hist(a2, [(big & p['ret'] & (ph == '지지'), '#0B6E4F', '광도 검사가 사전 정보 지지 → 되돌림', None), (big & p['ret'] & (ph != '지지'), SC[4], '다시점 일치 점 < 4 → 되돌림', None),
                  (big & ~p['ret'] & (a2 < 4), '#B5532C', '일치 점 < 4지만 광도가 사전 정보 반박 → 영상 유지', None), (big & ~p['ret'] & (a2 >= 4), SC[31], '다시점 일치 점 ≥ 4 → 영상 유지', None)],
             np.arange(0, 31, 1), thr=4, thr_lab='문턱 4개', xlab='영상 후보의 다시점 일치 점 수 (일치 시점 ≥ 5, 30 이상은 30)')
    else:
        rows = [(1, '영상 점 < 4'), (11, '시선 검사로 영상 점 지움'), (2, '|d| ≤ L'), (3, '|d| > L, |d| < 1.10 m'), (31, '|d| ≥ 1.10 m, 다시점·광도 통과'), (4, '|d| ≥ 1.10 m, 다시점 부족 또는 광도 지지'), (5, '면 맞춤 불가(L 없음), 저장 판정')]
        keep = {1: '사전 정보', 11: '사전 정보', 2: '가중 평균', 3: '가중 평균', 31: '영상 깊이', 4: '사전 정보', 5: '저장 판정대로'}
        ax.set_xlim(0, 1); ax.set_ylim(len(rows)+.5, -.8); ax.axis('off')
        for x_, t in [(.02, '판정'), (.30, '근거'), (.72, '남긴 후보'), (.92, '넓이 %')]: ax.text(x_, -.4, t, fontsize=10, color=NAVY, fontweight='bold')
        for i, (k, why) in enumerate(rows):
            y = i+.5; ax.add_patch(plt.Rectangle((.0, y-.3), .015, .6, color=SC[k], hatch=HATCH.get(k)))
            ax.text(.02, y, SN[k], fontsize=10, va='center'); ax.text(.30, y, why, fontsize=10, va='center'); ax.text(.72, y, keep[k], fontsize=10, va='center')
            ax.text(.98, y, f'{100*A[cat == k].sum()/Atot:.1f}', fontsize=10, va='center', ha='right')

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

FADE = [i/8 for i in range(1, 8)]; FADE_FRAMES = 21; HOLD_FRAMES = 38; RES_FRAMES = 50   # v2: 0.84 s movement (7 x 3 frames) + 1.52 s hold
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
