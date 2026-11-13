"""Concept video, another case (TL_CASE=B0_b10__LoD2, 2026-11-13, user: '가우시안/메시 확대와 단면도가 어디를 가리키는지 모르겠어'): one locator figure.
Read-only on every input; writes /docs/locator_v1.png + locator_v1.json. No new geometry, no scoring; the video frames are not touched.
Top row, the same ours-30,000 mesh (concept_v2/meshcol/ours_30000.npz) and photo as the video:
  plan (seen from straight above, north up), overview (the ② view of the video), photo 0031 (the ① photo, same crop).
  Each zone k: section line = cv2_case_zones.py line (origin = 6 m inside the wall, 12 m along the outward wall normal); its vertical cut plane =
  that line x scope z_min..z_max (filled, zone colour); dot = the section's 0 m end; arrow = the ② zoom view direction (azimuth = outward wall normal,
  elevation 35, aimed at the box centre), drawn outside the 12 m line; thin rectangle = zone box (counting box of the numbers table).
  Photo: zone 1 plane filled, zone 2 plane (behind the building from this camera) dashed outline only.
Bottom row per zone: ②-k mesh zoom of 30,000 (exactly the video's view and box crop) with the cut plane drawn (it is seen edge-on: the view direction
lies in the section plane, so it is a vertical line), and ③-k this-method section of 30,000 (the video's section) framed in the zone colour.
Text: panel names, one legend line. scientific_verdict: null"""
from cv2_frames import *
from matplotlib.patches import Polygon as MPoly
assert TL_CASE, 'case only'
ZC = {1: '#C2185B', 2: '#00838F'}

def plane(S, k):
    z = S.zones[k]; zb, zt = S.zr; a, b = z['o'], z['o']+z['L']*z['t']
    return np.array([[*a, zb], [*b, zb], [*b, zt], [*a, zt]])

def arrow3d(S, sj, k, d0=16., d1=8.):
    z = S.zones[k]; zj = sj['zones'][str(k)]; ctr = np.asarray(zj['zoom_centre'], float); B = np.asarray(zj['zoom_basis'], float); back = -B[2]   # toward the zoom camera
    return np.array([ctr+d0*back, ctr+d1*back]), ctr

def badge(ax, x, y, k, fs=9):
    ax.text(x, y, str(k), fontsize=fs, color='white', ha='center', va='center', fontweight='bold', bbox=dict(boxstyle='circle,pad=.18', fc=ZC[k], ec='white', lw=.8), zorder=30, clip_on=True)

def draw_marks(F, ax, fn, k, fill=True, dashed=False, arrow=True, box=True, dot=True):
    S = F.S; Q = plane(S, k); x, y = fn(Q)
    if fill: ax.add_patch(MPoly(np.c_[x, y], closed=True, fc=ZC[k], ec='none', alpha=.33, zorder=17))
    ax.add_patch(MPoly(np.c_[x, y], closed=True, fc='none', ec=ZC[k], lw=1.6, ls=(0, (3, 2)) if dashed else '-', zorder=18))
    z = S.zones[k]; zb = S.zr[0]
    if box:
        ring = np.asarray(F.sj['zones'][str(k)]['box_polygon_xy']); bx, by = fn(np.c_[ring, np.full(len(ring), zb)]); ax.plot(np.r_[bx, bx[:1]], np.r_[by, by[:1]], color=NAVY, lw=.8, zorder=16)
    if dot: px, py = fn(np.array([[*z['o'], zb]])); ax.plot(px, py, 'o', ms=6, color=ZC[k], mec='white', mew=1, zorder=19)
    if arrow:
        A, _ = arrow3d(S, F.sj, k); ax_, ay_ = fn(A)
        ax.add_patch(FancyArrowPatch((ax_[0], ay_[0]), (ax_[1], ay_[1]), arrowstyle='-|>', mutation_scale=16, color=NAVY, lw=2.2, zorder=20))
    return x, y

def main():
    t0 = time.monotonic(); F = Frame(); S = F.S; rec = dict(at=now(), rule=__doc__, sources={}, scientific_verdict=None)
    F.fig = fig = plt.figure(figsize=(W_/100, H_/100), dpi=100, facecolor='white')
    fig.text(16/W_, 1-24/H_, f'{BNAME} · 확대 그림과 단면이 가리키는 곳', fontsize=19, color=NAVY, va='center', fontweight='bold')
    mz = loadz(V2/'meshcol'/'ours_30000.npz'); rec['sources']['mesh'] = F.h(V2/'meshcol'/'ours_30000.npz'); C = mz['C'].astype(float)
    # plan
    up = np.asarray(S.c['coordinates']['up'], float); Bp = basis(up, 270., 89.5)
    from shapely.geometry import shape
    fp = shape(S.c['scope']['buffered_footprint']); cxy = np.asarray(fp.centroid.coords[0]); cp = np.r_[cxy, S.ground+12.]
    fn_p = lambda P: S.proj(P, Bp, cp)[:2]
    pts = [np.c_[np.asarray(fp.exterior.coords), np.full(len(fp.exterior.coords), S.ground)]]
    for k in (1, 2): pts += [plane(S, k), arrow3d(S, F.sj, k)[0]]
    px, py = fn_p(np.vstack(pts)); Y0 = 70; hA = 470; wA = 520
    extp = F.frame_ext((px.min(), px.max(), py.min(), py.max()), wA, hA, .08)
    a = F.axes(16, Y0, wA, hA, '평면 · 위에서 본 30,000회 메시 (위 = 북)'); img, _ = F.raster(mz['V'], mz['F'], C, extp, wA, hA, 2, view=(Bp, cp)); F.show(a, img, extp)
    fx, fy = fn_p(np.c_[np.asarray(fp.exterior.coords), np.full(len(fp.exterior.coords), S.ground)]); a.plot(fx, fy, color='#9C9A92', lw=.6, zorder=10)
    for k in (1, 2):
        x, y = draw_marks(F, a, fn_p, k); badge(a, x[1], y[1], k, 10)
    # overview (the ② view)
    wB = 760; ext = F.frame_ext(F.sj['oblique']['overview_extent'], wB, hA, .03)
    b = F.axes(16+wA+16, Y0, wB, hA, '개관 · 영상 ② 칸과 같은 방향'); img, _ = F.raster(mz['V'], mz['F'], C, ext, wB, hA, 2); F.show(b, img, ext)
    fn_o = lambda P: S.proj(P)[:2]
    for k in (1, 2):
        x, y = draw_marks(F, b, fn_o, k); badge(b, x[2], y[2], k, 10)
    # photo (the ① photo)
    u0, v0, u1, v1 = F.st['crop']; wC = int(round(hA*(u1-u0)/(v1-v0))); xC = W_-16-wC
    c = F.axes(xC, Y0, wC, hA, f'① 사진 {CAM.split("_")[-2]}'); photo = loadz(O/'concept/inputs.npz', ['photo'])['photo'].astype(float)/255.; F.cam(c, photo, zones=False)
    rec['sources']['photo'] = F.h(O/'concept/inputs.npz'); fn_c = lambda P: S.pix(P)[:2]
    for k in (1, 2):
        x, y = draw_marks(F, c, fn_c, k, fill=(k == 1), dashed=(k == 2), arrow=False, box=False, dot=False)
        badge(c, np.clip(x.mean(), u0+12, u1-12), np.clip(y.min()+16, v0+12, v1-12), k, 9)
    rec['layout_note'] = dict(photo_width_px=wC, overview_extent=list(ext), plan_extent=list(extp))
    # bottom row: zoom + section per zone
    Yb = 600; hb = 400; wz = 330
    for i, k in enumerate((1, 2)):
        x0 = 16+i*952; ws = 952-16-wz-12 if i == 0 else W_-16-(x0+wz+12)
        zj = F.sj['zones'][str(k)]; zext = F.frame_ext(zj['zoom_extent'], wz, hb, .06); zv = (np.asarray(zj['zoom_basis']), np.asarray(zj['zoom_centre']))
        az = F.axes(x0, Yb, wz, hb, f'②-{k} 메시 확대 · {ZNAME[k]} · 30,000회')
        fsel = in_zone(mz['V'][mz['F']].mean(1).astype(float), S.zones[k], S.zr); img, _ = F.raster(mz['V'], mz['F'][fsel], C, zext, wz, hb, 3, view=zv); F.show(az, img, zext)
        Q = plane(S, k); qx, qy, _ = S.proj(Q, *zv); az.plot([qx.mean(), qx.mean()], [qy.min(), qy.max()], color='white', lw=4, zorder=17); az.plot([qx.mean(), qx.mean()], [qy.min(), qy.max()], color=ZC[k], lw=2, zorder=18)
        rec[f'zone{k}_cut_line_in_zoom_x_spread_m'] = float(qx.max()-qx.min())   # ~0: the plane is seen edge-on
        for s_ in az.spines.values(): s_.set_color(ZC[k]); s_.set_linewidth(2)
        asx = F.axes(x0+wz+12, Yb, ws, hb, f'③-{k} 본 방법 단면 · 30,000회'); sp = SECD/'ours_30000.npz'; rec['sources'][f'section{k}'] = F.h(sp)
        F.section(asx, k, sec=loadz(sp), layers=('gtband',)); asx.plot(0, .02, 'o', ms=7, color=ZC[k], mec='white', mew=1, zorder=20, clip_on=False)
        for s_ in asx.spines.values(): s_.set_color(ZC[k]); s_.set_linewidth(2)
    # legend (one line)
    lax = fig.add_axes([0, 0, 1, 30/H_]); lax.set_xlim(0, W_); lax.set_ylim(0, 30); lax.axis('off'); x = 16
    for kind, col, txt in [('fill', ZC[1], '구역 1'), ('fill', ZC[2], '구역 2 단면 면(③이 자르는 수직 면)'), ('dot', '#5F5E5A', '단면의 0 m 끝'),
                           ('arrow', NAVY, '② 확대를 보는 방향'), ('box', NAVY, '구역 상자(바닥)'), ('band', GTB, '참값'), ('line', MSC, '메시')]:
        if kind == 'fill': lax.add_patch(plt.Rectangle((x, 9), 20, 12, fc=col, alpha=.5, ec=col)); x += 26
        elif kind == 'dot': lax.plot(x+6, 15, 'o', ms=7, color=col, mec='white'); x += 16
        elif kind == 'arrow': lax.add_patch(FancyArrowPatch((x, 15), (x+24, 15), arrowstyle='-|>', mutation_scale=12, color=col, lw=2)); x += 30
        elif kind == 'box': lax.add_patch(plt.Rectangle((x, 9), 20, 12, fc='none', ec=col, lw=.8)); x += 26
        elif kind == 'band': lax.add_patch(plt.Rectangle((x, 11), 20, 8, fc=col, ec='none')); x += 26
        else: lax.plot([x, x+20], [15, 15], color=col, lw=1.4); x += 26
        lax.text(x, 15, txt, fontsize=9, va='center', color=NAVY); x += 9.5*len(txt)+24
    png = D/'locator_v1.png'; fig.savefig(png, dpi=100, facecolor='white'); plt.close(fig)
    rec['png'] = str(png); rec['seconds'] = round(time.monotonic()-t0, 1); dump(D/'locator_v1.json', rec); print('LOCATOR', png, rec['seconds'], flush=True)

if __name__ == '__main__': main()
