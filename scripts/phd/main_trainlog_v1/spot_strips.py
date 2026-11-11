"""Spot strips (user decision 2026-11-11): one figure per thesis place of B173 (spots_v5.json: 1 wing, 2 unseen long wall, 3 glass skylight).
Columns: [입력·감독] + key iterations 0, 1000, 2000, 3000 직전, 7000, 10000, 15000, 30000.
Rows: 가우시안 (each Gaussian as its 2D disc at 2 sigma, alpha = opacity; colour = role: bound -> its judgment tone, released -> hollow, free -> grey, placed on the old roof -> pink),
      메시 (faces coloured like video G: judgment tone if within TAU of the dense GT, purple beyond; GT for scoring/colouring only),
      단면 (stage-1 section of the place, band +-0.25 m; wall: a cut through the face centre along the wall normal).
First column: row 1 = inputs (old prior roof, pink; image MVS per patch, dark grey), row 2 = supervision targets (target discs in judgment colour), row 3 = section of the inputs.
Close-up cameras: wing and glass = the video camera direction (az from spots_v5.json, el 35); wall = facing the wall (az of its normal, el 12), s in [-12, 12] m.
Measurements per place and key iteration -> /docs/tables/spot_strip_measures.csv. CPU, no training."""
import sys
from video_v2 import *
from src.phd.prior_propagation_v6.orientation import axes_of_quat
from matplotlib.collections import EllipseCollection, LineCollection
from scipy.spatial import cKDTree
SPJ = json.loads((O/'analysis/spots_v5/spots_v5.json').read_text()); AZ = int(SPJ['chosen_azimuth']); OUT = O/'spot_strips'; OUT.mkdir(exist_ok=True)
KEYS = ['0', '1000', '2000', '3000_pre_reset', '7000', '10000', '15000', '30000']; KLAB = ['0', '1,000', '2,000', '3,000 직전', '7,000', '10,000', '15,000', '30,000']
MVSC = '#444441'; PRIORC = np.array(to_rgb('#ED93B1')); NEUTRAL = np.array(to_rgb('#E5E3DC')); T = TAU/100; WALL_HALF = 12.
TITLE = {'wing': '① 날개 — 옛 박공지붕(사전 정보)이 7 m 낮은 평지붕이 된 곳 (1단계 장면 1)', 'wall': '② 긴 벽 — 영상이 보지 못한 벽을 무엇이 채우는가 (1단계 장면 3, 면 53, 가운데 24 m)',
         'glass': '③ 유리 채광창 — 여러 영상이 똑같이 틀리게 본 곳 (1단계 장면 5)'}

def places(S):
    P = {}
    for k in ['wing', 'glass']:
        s = SPJ['places'][k]['section']; c = np.array(s['centre'][:2]); t = np.array(s['t'], float); t /= np.linalg.norm(t); nn = np.array([-t[1], t[0]])
        P[k] = dict(c=c, ax=t, nn=nn, L=s['L'], hw=s['window_half_width_m'], sec_hw=s['half_width_m'], az=AZ, el=35, kind='roof')
    f = SPJ['places']['wall']['face']; c = np.array(f['centre']); n = np.array(f['normal'], float); t = np.array(f['t'], float)
    P['wall'] = dict(c=c[:2], ax=n[:2]/np.linalg.norm(n[:2]), nn=t[:2], L=12., hw=WALL_HALF, sec_hw=.25, az=int(round(np.degrees(np.arctan2(n[1], n[0])))) % 360, el=12, kind='wall', z=f['z_range'], wall_c=c, wall_n=n, wall_t=t)
    return P

def in_win(p, xy, z=None, margin=1.):
    if p['kind'] == 'roof': return (np.abs((xy-p['c'])@p['ax']) <= p['L']/2+margin) & (np.abs((xy-p['c'])@p['nn']) <= p['hw']+margin)
    return (np.abs((xy-p['c'])@p['ax']) <= 3.+margin) & (np.abs((xy-p['c'])@p['nn']) <= p['hw']+margin)

def camera(S, p, pts):
    B = basis(S.c, p['az'], p['el']); ctr = pts.mean(0); q = (pts-ctr)@B[:2].T; lo, hi = q.min(0), q.max(0); m = (hi-lo)*.06; lo, hi = lo-m, hi+m
    w, h = hi-lo; AR = 1.45
    if w/h < AR: e = (h*AR-w)/2; lo[0] -= e; hi[0] += e
    else: e = (w/AR-h)/2; lo[1] -= e; hi[1] += e
    return dict(B=B, ctr=ctr, lo=lo, hi=hi)

def proj(cam, P): q = (P-cam['ctr'])@cam['B'].T; return q[:, 0], q[:, 1], q[:, 2]

def cast(cam, scene, W=520):
    H = int(W*(cam['hi'][1]-cam['lo'][1])/(cam['hi'][0]-cam['lo'][0])); xs = np.linspace(cam['lo'][0], cam['hi'][0], W); ys = np.linspace(cam['hi'][1], cam['lo'][1], H); X, Y = np.meshgrid(xs, ys); B = cam['B']
    org = cam['ctr']+X[..., None]*B[0]+Y[..., None]*B[1]-400*B[2]; rays = np.concatenate([org, np.broadcast_to(B[2], org.shape)], -1).reshape(-1, 6).astype('f4')
    r = scene.cast_rays(o3d.core.Tensor(rays)); t = r['t_hit'].numpy(); return np.isfinite(t), r['primitive_ids'].numpy(), r['primitive_normals'].numpy(), (H, W), np.where(np.isfinite(t), t-400, np.inf).reshape(H, W)

def scene_of(V, F):
    sc = o3d.t.geometry.RaycastingScene(); tm = o3d.t.geometry.TriangleMesh(); tm.vertex.positions = o3d.core.Tensor(V.astype('f4')); tm.triangle.indices = o3d.core.Tensor(F.astype('i4')); sc.add_triangles(tm); return sc

def show(ax, cam, img=None):
    if img is not None: ax.imshow(img, extent=(cam['lo'][0], cam['hi'][0], cam['lo'][1], cam['hi'][1]), interpolation='bilinear')
    ax.set_xlim(cam['lo'][0], cam['hi'][0]); ax.set_ylim(cam['lo'][1], cam['hi'][1]); ax.set_aspect('equal'); ax.set_xticks([]); ax.set_yticks([])
    for s_ in ax.spines.values(): s_.set_color('#D3D1C7')

def ell(cam, P, a1, a2):
    B = cam['B']; M = np.stack([np.stack([a1@B[0], a2@B[0]], 1), np.stack([a1@B[1], a2@B[1]], 1)], 1); U, s, _ = np.linalg.svd(M); return s, np.degrees(np.arctan2(U[:, 1, 0], U[:, 0, 0]))

def visible(cam, P, depth, tol=.4):
    x, y, d = proj(cam, P); H, W = depth.shape; col = np.clip(((x-cam['lo'][0])/(cam['hi'][0]-cam['lo'][0])*(W-1)).round().astype(int), 0, W-1); row = np.clip(((cam['hi'][1]-y)/(cam['hi'][1]-cam['lo'][1])*(H-1)).round().astype(int), 0, H-1)
    return d <= depth[row, col]+tol

def section_cut(V, F, p):
    """Plane through p['c'] with horizontal normal p['nn']; returns segments as (s along p['ax'], z)."""
    vv = (V[:, :2]-p['c'])@p['nn']; sg = np.sign(vv[F]); Tt = F[(sg.min(1) < 0) & (sg.max(1) > 0)]; E = []
    for a, b in [(0, 1), (1, 2), (2, 0)]:
        va, vb = vv[Tt[:, a]], vv[Tt[:, b]]; m = (va*vb) < 0; w = np.where(m, va/np.where(m, va-vb, 1), np.nan); E.append(V[Tt[:, a]]+w[:, None]*(V[Tt[:, b]]-V[Tt[:, a]]))
    if not len(Tt): return np.zeros((0, 2, 2))
    E = np.stack(E, 1); ok = np.isfinite(E[:, :, 0]); keep = ok.sum(1) == 2; E = E[keep]; ok = ok[keep]; Q = np.stack([E[i][ok[i]] for i in range(len(E))])
    s = (Q[:, :, :2]-p['c'])@p['ax']; m = (np.abs(s) <= p['L']/2).all(1); return np.stack([s[m], Q[m][:, :, 2]], 2)

def main(cams_only=False):
    S = Ctx(); P = places(S); g0 = S.c['scope']['ground_z']; t = loadz(FT/'targets'/f'{STEM}.npz', ['centre', 'normal', 'mvs_mean_m', 'prior_height_m', 'target', 'judge_region', 'target_sigma_m', 'area'])
    tc = t['centre']; mvs = tc+t['normal']*t['mvs_mean_m'][:, None]; tgt = t['target']; tj = t['judge_region']; tr = np.sqrt(t['area']/np.pi); ok_t = np.isfinite(tgt).all(1) & (tj >= 0)
    gt = loadz(GT/'reference'/SITE/'dense.npz', ['xyz', 'normal']); gx = gt['xyz'].astype(float); gn = gt['normal'].astype(float); gn[gn[:, 2] < 0] *= -1; gtree = cKDTree(gx)
    rows = gx[::3]   # dense GT (every third point) for sections; includes walls and the layers under glass
    pr = loadz(S1/'defs'/SITE/'prior_ALS.npz', ['V', 'F']); PV = pr['V'].astype(float); PF_ = pr['F']; pcen = PV[PF_].mean(1); pfn = np.cross(PV[PF_[:, 1]]-PV[PF_[:, 0]], PV[PF_[:, 2]]-PV[PF_[:, 0]]); proof = np.abs(pfn[:, 2])/np.maximum(np.linalg.norm(pfn, axis=1), 1e-12) >= .3
    cams, crops = {}, {}; ptree = cKDTree(S.pt[:, :2])
    global WALLP; uw = loadz(S1/'defs'/SITE/'unseen.npz', ['centre', 'surf_ext']); WALLP = uw['centre'][uw['surf_ext'] == SPJ['places']['wall']['face']['surf_ext']].astype(float)
    for k, p in P.items():
        if p['kind'] == 'roof':
            w = in_win(p, tc[:, :2], margin=0.) & ok_t; pts = np.r_[tgt[w], mvs[w & np.isfinite(mvs).all(1)], tc[w]+t['normal'][w]*t['prior_height_m'][w][:, None]]; pts = pts[np.isfinite(pts).all(1)]
        else:
            c = p['wall_c']; pts = np.array([c+s_*p['wall_t']+np.array([0, 0, z-c[2]]) for s_ in (-WALL_HALF, WALL_HALF) for z in p['z']])
        cams[k] = camera(S, p, pts); print('CAM', k, p['az'], p['el'], flush=True)
    dump(O/'analysis/spot_strips_cams.json', dict(at=now(), cams={k: dict(B=v['B'].tolist(), ctr=v['ctr'].tolist(), lo=v['lo'].tolist(), hi=v['hi'].tolist()) for k, v in cams.items()},
         rule='close-up orthographic box per place (spot_strips.camera)', scientific_verdict=None))
    if cams_only: return
    sel = {k: in_win(p, pcen[:, :2], margin=2.) for k, p in P.items()}; psc = {k: scene_of(PV, PF_[sel[k] & proof]) for k in P}   # roof-like prior faces only (the ALS TIN hangs curtains down the walls)
    figs = {}
    for k, p in P.items():
        fig, axs = plt.subplots(3, 9, figsize=(22, 6.9), facecolor='white', gridspec_kw=dict(height_ratios=[1, 1, .9], hspace=.16, wspace=.04)); figs[k] = (fig, axs)
        cam = cams[k]; hit, pid, nrm, (H, W), dep = cast(cam, psc[k]); rgba = np.zeros((H*W, 4)); rgba[hit, :3] = PRIORC*(.6+.4*np.abs(nrm[hit]@LT))[:, None]; rgba[hit, 3] = .42
        a = axs[0, 0]; show(a, cam); w = in_win(p, tc[:, :2]) & np.isfinite(mvs).all(1)
        s, ang = ell(cam, mvs[w], *tang(t['normal'][w], tr[w])); x, y, d = proj(cam, mvs[w]); o = np.argsort(-d)
        a.add_collection(EllipseCollection(2*s[o, 0], 2*s[o, 1], ang[o], units='xy', offsets=np.c_[x[o], y[o]], offset_transform=a.transData, facecolors=MVSC, edgecolors='none', alpha=.75))
        a.imshow(rgba.reshape(H, W, 4), extent=(cam['lo'][0], cam['hi'][0], cam['lo'][1], cam['hi'][1]), zorder=3); a.set_title('입력: 사전 정보 지붕면(분홍) · 영상 MVS(진회색)', fontsize=9, loc='left')
        a = axs[1, 0]; show(a, cam); w = in_win(p, tc[:, :2]) & ok_t; s, ang = ell(cam, tgt[w], *tang(t['normal'][w], tr[w])); x, y, d = proj(cam, tgt[w]); o = np.argsort(-d)
        a.add_collection(EllipseCollection(2*s[o, 0], 2*s[o, 1], ang[o], units='xy', offsets=np.c_[x[o], y[o]], offset_transform=a.transData, facecolors=[JC.get(int(j), '#B4B2A9') for j in tj[w][o]], edgecolors='none'))
        a.set_title('감독 목표 (판정색)', fontsize=9, loc='left')
        if p['kind'] == 'wall':
            wv = w & (np.abs(t['normal'][:, 2]) <= .3); a.text(.03, .05, f'벽 면 목표 {int(wv.sum())}개', transform=a.transAxes, fontsize=9, color='#2C2C2A')
        a = axs[2, 0]; a._first = True; sec_inputs(a, p, PV, PF_, mvs, tgt, tj, t['target_sigma_m'], tc, rows, g0); a.set_title('단면: 입력과 목표', fontsize=9, loc='left')
    meas = []
    for ci, (n, lab) in enumerate(zip(KEYS, KLAB), start=1):
        z = loadz(A/f'mesh_{n}.npz', ['vertices', 'faces', 'vertex_error_m']); V = z['vertices'].astype(float); F = z['faces']; cen = V[F].mean(1)
        d = loadz(DER/'gaussians'/f'{n}.npz'); gxyz = d['xyz'].astype(float); ax3 = axes_of_quat(d['rotation']); sc_ = d['scale'].astype(float); op = d['opacity'].astype(float); tag = d['target_tag']; jd = d['judgment']; wr = d['group33'] == 1
        full_idx = d['full_gaussian_index'].astype(np.int64); f_ord = np.argsort(full_idx); f_sorted = full_idx[f_ord]; pos_of = lambda v: f_ord[np.searchsorted(f_sorted, v)]
        for k, p in P.items():
            fig, axs = figs[k]; cam = cams[k]; wf = in_win(p, cen[:, :2], margin=2.); Fk = F[wf]; sc = scene_of(V, Fk); hit, pid, nrm, (H, W), dep = cast(cam, sc)
            fe = z['vertex_error_m'][Fk].mean(1); fc = cen[wf]; fn = np.cross(V[Fk[:, 1]]-V[Fk[:, 0]], V[Fk[:, 2]]-V[Fk[:, 0]]); ar = .5*np.linalg.norm(fn, axis=1); fn /= np.maximum(2*ar, 1e-12)[:, None]
            dd, ii = ptree.query(fc[:, :2]); reg = np.where((dd <= .5) & (np.abs(fn[:, 2]) >= .5), S.pj[ii], -1); base = np.tile(NEUTRAL, (len(Fk), 1))
            for j, c in JC.items(): base[reg == j] = to_rgb(c)
            al_ = np.clip((np.abs(fe)-T)/(1-T), 0, 1)[:, None]; col = np.where((np.abs(fe) <= T)[:, None], base, P0*(1-al_)+P1*al_)
            img = np.where(hit[:, None], col[pid.clip(0, len(Fk)-1)]*(.55+.45*np.abs(nrm@LT))[:, None], 1.).reshape(H, W, 3)
            a = axs[1, ci]; show(a, cam, np.clip(img, 0, 1))
            wg = in_win(p, gxyz[:, :2], margin=.5)
            if p['kind'] == 'wall': wg &= (gxyz[:, 2] >= p['z'][0]-.5) & (gxyz[:, 2] <= p['z'][1]+1.)
            vz = loadz(O/'spot_strips/visible'/f'{n}__{k}.npz'); vid = vz['ids']; row = np.full(len(vid), -1); hit_ = np.isin(vid, full_idx); row[hit_] = pos_of(vid[hit_])
            vx = vz['xyz'].astype(float); vax = axes_of_quat(vz['quat'].astype('f4')); vs = vz['scale'].astype(float); vop = vz['opacity'].astype(float)
            vtag = np.where(row >= 0, tag[row.clip(0)], -1); vj = np.where(row >= 0, jd[row.clip(0)], -1); vwr = (row >= 0) & wr[row.clip(0)]
            a = axs[0, ci]; show(a, cam); s, ang = ell(cam, vx, vax[0]*vs[:, 0:1]*2, vax[1]*vs[:, 1:2]*2); x, y, dz = proj(cam, vx); o = np.argsort(-dz)
            fcol = np.array([to_rgb(JC.get(int(j), '#888780')) if tg == 1 else (to_rgb('#888780') if tg == 0 else ((1, 1, 1) if tg == 2 else to_rgb('#D3D1C7'))) for j, tg in zip(vj, vtag)]).reshape(-1, 3)
            if len(fcol): fcol[vwr] = to_rgb(PINK)
            ecol = np.where((vtag == 2)[:, None], np.array(to_rgb('#2C2C2A'))[None], fcol); alpha = np.clip(vop, .15, 1)
            a.add_collection(EllipseCollection(2*s[o, 0], 2*s[o, 1], ang[o], units='xy', offsets=np.c_[x[o], y[o]], offset_transform=a.transData, facecolors=np.c_[fcol[o], alpha[o]], edgecolors=np.c_[ecol[o], alpha[o]], linewidths=.4))
            a.text(.98, .03, f'보이는 원반 {len(vid):,}', transform=a.transAxes, ha='right', fontsize=7.5, color='#5F5E5A')
            a = axs[2, ci]; sec_iter(a, p, V, F[in_win(p, cen[:, :2], margin=1.)], gxyz, tag, jd, wr, op, PV, PF_, rows, g0)
            seg = section_cut(V, F[in_win(p, cen[:, :2], margin=1.)], p)
            if len(seg):
                P3 = np.c_[(p['c'][None, :]+seg[:, :, 0].reshape(-1, 1)*p['ax'][None, :]), seg[:, :, 1].reshape(-1)]; px, py, _ = proj(cam, P3)
                for a_ in (axs[0, ci], axs[1, ci]): a_.add_collection(LineCollection(np.stack([px.reshape(-1, 2), py.reshape(-1, 2)], 2), colors=NAVY, linewidths=1.0, zorder=9))
            axs[0, ci].set_title(lab, fontsize=11, fontweight='bold', color=NAVY)
            if p['kind'] == 'roof':
                mw = in_win(p, fc[:, :2], margin=0.) & (np.abs(fn[:, 2]) >= .5) & (fc[:, 2] >= g0+10.)
                gq = in_win(p, gx[:, :2], margin=0.) & (np.abs(gn[:, 2]) >= .5) & (gx[:, 2] >= g0+10.); gd = sc.compute_distance(o3d.core.Tensor(gx[gq].astype('f4'))).numpy()
                comp = float(100*(gd <= T).mean()) if gq.any() else None; rule = 'roof: GT points |nz|>=.5, >=10 m above ground, within TAU of the mesh; faces likewise, |err|<=TAU by area'
            else:
                wpt = WALLP[np.abs((WALLP[:, :2]-p['c'])@p['nn']) <= p['hw']]; gd = sc.compute_distance(o3d.core.Tensor(wpt.astype('f4'))).numpy(); comp = float(100*(gd <= .25).mean())
                mw = (np.abs((fc[:, :2]-p['c'])@p['ax']) <= 1.) & (np.abs((fc[:, :2]-p['c'])@p['nn']) <= p['hw']) & (np.abs(fn[:, 2]) <= .3) & (fc[:, 2] <= p['z'][1]-.5)
                rule = 'wall: unseen-face patches (surf 53) with the mesh within 0.25 m (main_baselines wall count); faces vertical within 1 m of the face, below the roof edge'
            m_fit = float(100*ar[mw & (np.abs(fe) <= T)].sum()/max(ar[mw].sum(), 1e-9)) if mw.any() else None; gw = wg & (in_win(p, gxyz[:, :2], margin=0.))
            meas.append(dict(place=k, state=n, iteration=S.it[n], completeness_pct=round(comp, 2) if comp is not None else None, mesh_area_m2=round(float(ar[mw].sum()), 2), mesh_fit_pct=round(m_fit, 2) if m_fit is not None else None, rule=rule, gaussians=int(gw.sum()), bound=int((gw & (tag == 1)).sum()), released=int((gw & (tag == 2)).sum()),
                             free=int((gw & (tag == 0)).sum()), on_old_roof=int((gw & wr).sum()), opacity_median=round(float(np.median(op[gw])), 3) if gw.any() else None,
                             opacity_gt_0p5_pct=round(float(100*(op[gw] > .5).mean()), 1) if gw.any() else None, short_axis_median_cm=round(float(100*np.median(sc_[gw].min(1))), 2) if gw.any() else None,
                             long_axis_median_cm=round(float(100*np.median(sc_[gw].max(1))), 2) if gw.any() else None))
            print('MEAS', meas[-1], flush=True)
    for k, (fig, axs) in figs.items():
        axs[0, 0].set_ylabel('가우시안', fontsize=12); axs[1, 0].set_ylabel('메시', fontsize=12); axs[2, 0].set_ylabel('단면 (지면 위 m)', fontsize=11)
        fig.suptitle(TITLE[k], fontsize=15, x=.01, ha='left', y=1.035, color=NAVY)
        fig.text(.01, .985, '남색 선 = 단면 자리(메시를 자른 선, 셋째 줄과 같은 곳). 단면은 그 자리 ±25 cm만 자른 것이고, 위 두 줄은 자리 전체를 보인다.'
                 + (' 메시는 실제 영상 203장의 시점에서 렌더한 깊이를 합쳐 만든다: 이 벽은 그 시점들에서 보이지 않아, 벽 앞에 원반이 있어도 메시에 들어가지 않는다.' if k == 'wall' else ''), fontsize=10, color='#444441', ha='left')
        hd = [Patch(facecolor=PRIORC, alpha=.7, label='사전 정보: 옛 항공 LiDAR'), Line2D([], [], marker='o', ls='', color=MVSC, label='영상 MVS')]+[Patch(color=JC[j], label=f'{JN[j]} (목표·묶인 원반·맞는 면)') for j in [0, 2, 1, 4]]
        hd += [Line2D([], [], marker='o', ls='', markerfacecolor='white', markeredgecolor='#2C2C2A', label='풀린 원반'), Line2D([], [], marker='o', ls='', color='#888780', label='자유 원반 · 판정 밖 면'), Line2D([], [], marker='o', ls='', color='#D3D1C7', label='건물 범위 밖 원반'),
               Line2D([], [], marker='o', ls='', color=PINK, label='옛 지붕에 놓인 원반'), Patch(color=P1, label='참값에서 21 cm 넘게 벗어난 면'), Line2D([], [], color=NAVY, label='메시 단면 · 단면 자리'), Line2D([], [], color=PINK, ls='--', label='사전 정보 단면 (첫 열)'),
               Line2D([], [], marker='o', ls='', color='#B4B2A9', ms=3, label='참값 (밀집 점)')]
        fig.legend(handles=hd, loc='lower center', ncol=11, frameon=False, fontsize=8.6, bbox_to_anchor=(.5, -.005))
        fig.text(.995, .005, '가우시안 칸: 같은 시점 실제 렌더에서 화소마다 가장 많이 기여한 원반만 (벽은 벽 면 ±3 m 원반만 렌더) (2σ, 진하기 = 불투명도) · 분홍 점선(사전 정보)은 첫 열에만 · 첫 열은 학습 전 입력과 감독', ha='right', fontsize=8, color='#5F5E5A')
        fig.savefig(OUT/f'{k}.png', dpi=110, bbox_inches='tight', facecolor='white'); plt.close(fig); print('FIG', k, flush=True)
    import csv
    with open('/docs/tables/spot_strip_measures.csv', 'w', newline='') as f: wri = csv.DictWriter(f, fieldnames=list(meas[0])); wri.writeheader(); wri.writerows(meas)
    dump(OUT/'spot_strips.json', dict(at=now(), places={k: dict((kk, (vv.tolist() if isinstance(vv, np.ndarray) else vv)) for kk, vv in p.items()) for k, p in P.items()}, keys=KEYS, measures=meas,
         rule=__doc__, scientific_verdict=None))

def tang(N, R):
    n = N/np.linalg.norm(N, axis=1)[:, None]; t1 = np.cross(n, [0, 0, 1.]); bad = np.linalg.norm(t1, axis=1) < 1e-6; t1[bad] = [1, 0, 0]; t1 /= np.linalg.norm(t1, axis=1)[:, None]; t2 = np.cross(n, t1)
    return t1*R[:, None], t2*R[:, None]

def band(p, xy): return np.abs((xy-p['c'])@p['nn']) <= p['sec_hw']

def sec_base(a, p, PV, PF_, rows, g0, prior=True):
    ps = section_cut(PV, PF_, p) if prior else np.zeros((0, 2, 2)); a.add_collection(LineCollection(np.stack([ps[:, :, 0], ps[:, :, 1]-g0], 2), colors=PINK, linewidths=1.1, linestyles=(0, (5, 3))))
    m = band(p, rows[:, :2]) & (np.abs((rows[:, :2]-p['c'])@p['ax']) <= p['L']/2); a.scatter((rows[m, :2]-p['c'])@p['ax'], rows[m, 2]-g0, s=1, c='#B4B2A9', lw=0, zorder=1)
    a.set_xlim(-p['L']/2, p['L']/2); a.tick_params(labelsize=7)
    if not getattr(a, '_first', False): a.set_yticklabels([])
    if p['kind'] == 'wall': a.set_ylim(p['z'][0]-g0-1, p['z'][1]-g0+7)
    else: a.set_ylim(max(0, np.nanmin(rows[m, 2]-g0)-3) if m.any() else 0, (np.nanmax(rows[m, 2]-g0)+9) if m.any() else 30)

def sec_inputs(a, p, PV, PF_, mvs, tgt, tj, tsig, tc, rows, g0):
    sec_base(a, p, PV, PF_, rows, g0); m = band(p, tc[:, :2]) & (np.abs((tc[:, :2]-p['c'])@p['ax']) <= p['L']/2)
    mm = m & np.isfinite(mvs).all(1); a.scatter((mvs[mm, :2]-p['c'])@p['ax'], mvs[mm, 2]-g0, s=7, c=MVSC, marker='s', lw=0)
    for j in JC:
        q = m & (tj == j) & np.isfinite(tgt).all(1); a.errorbar((tgt[q, :2]-p['c'])@p['ax'], tgt[q, 2]-g0, yerr=1.96*tsig[q], fmt='none', ecolor=JC[j], elinewidth=2, alpha=.8)

def sec_iter(a, p, V, F, gxyz, tag, jd, wr, op, PV, PF_, rows, g0):
    sec_base(a, p, PV, PF_, rows, g0, prior=False); seg = section_cut(V, F, p); a.add_collection(LineCollection(np.stack([seg[:, :, 0], seg[:, :, 1]-g0], 2), colors=NAVY, linewidths=1.7, zorder=7))
    m = band(p, gxyz[:, :2]) & (np.abs((gxyz[:, :2]-p['c'])@p['ax']) <= p['L']/2); s = (gxyz[:, :2]-p['c'])@p['ax']; zz = gxyz[:, 2]-g0; al = np.clip(op, .05, 1)
    q = m & (tag == 0) & ~wr; a.scatter(s[q], zz[q], s=3, c=[(*to_rgb('#888780'), v) for v in al[q]], lw=0)
    q = m & (tag == 2) & ~wr; a.scatter(s[q], zz[q], s=8, facecolors='none', edgecolors=[(*to_rgb('#2C2C2A'), v) for v in al[q]], linewidths=.5)
    for j in JC:
        q = m & (tag == 1) & (jd == j) & ~wr; a.scatter(s[q], zz[q], s=5, c=[(*to_rgb(JC[j]), v) for v in al[q]], lw=0)
    q = m & wr; a.scatter(s[q], zz[q], s=16, c=[(*to_rgb(PINK), v) for v in al[q]], edgecolors='white', linewidths=.5, zorder=6)

if __name__ == '__main__': main(cams_only=sys.argv[1:] == ['cams'])
