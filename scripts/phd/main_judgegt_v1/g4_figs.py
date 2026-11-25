"""단계 3(정성): 그림 1~4 (세 실험 지역). 정답 색은 모든 그림에서 같다(설정 colours). 그림마다 같은 이름의 json(출처, 값).
1 정답 지도  2 정답 종류별 단면  3 옛 정답과 새 정답이 다른 곳  4 참값 무리가 둘 이상인 패치. 사용: GT_STAGE=ga g4_figs.py [1 2 3 4]"""
from common import *
import pandas as pd
from scipy.spatial import cKDTree
from scipy.sparse.csgraph import connected_components
from scipy.sparse import coo_matrix
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt; from matplotlib import font_manager as fm
from matplotlib.patches import Rectangle, Patch
for f in ['/fonts/NotoSansCJK-Regular.ttc', '/fonts/NotoSansCJK-Bold.ttc']: fm.fontManager.addfont(f)
plt.rcParams.update({'font.family': 'Noto Sans CJK JP', 'font.size': 7, 'axes.titlesize': 7.5, 'axes.linewidth': .5})
REVON = True; HLAB = 'h_M'; FD = D/'figures'; SUB = '가' if STAGE == 'ga' else '151동'; COL = None; SRC = {}
SITE_LIST = ['B0', 'B173 주변', 'R1']
def fsave(fig, name, meta):
    FD.mkdir(parents=True, exist_ok=True); fig.savefig(FD/f'{name}.png', dpi=300, bbox_inches='tight', pad_inches=.08); plt.close(fig)
    dump(FD/f'{name}.json', dict(at=now(), figure=name, stage=STAGE, sources=SRC, colours=COL, **meta, scientific_verdict=None)); print('FIG', name, flush=True)
def tables():
    sfx = '' if STAGE == 'full' else f'_{STAGE}'; F = {}; R = {}
    for p in PRIORS:
        F[p] = pd.read_csv(O/f'forward_{p}{sfx}.csv.gz'); SRC[f'forward_{p}'] = str(O/f'forward_{p}{sfx}.csv.gz')
        if REVON: R[p] = pd.read_csv(O/f'reverse_{p}{sfx}.csv.gz'); SRC[f'reverse_{p}'] = str(O/f'reverse_{p}{sfx}.csv.gz')
    return F, R
from functools import lru_cache
@lru_cache(None)
def geo(prior):
    P = loadz(inp('patches', prior=prior), ['centre', 'normal', 'tangent1', 'prior_height_m', 'tile', 'tiles', 'building', 'kind']); SRC[f'patches_{prior}'] = str(inp('patches', prior=prior)); return P
def tile_points(t, kind, box):
    """box = (xmin, xmax, ymin, ymax, zmin, zmax) -> points inside, float64"""
    X = np.load(WI/'points'/t/('gt_xyz.npy' if kind == 'gt' else 'mvs_a_xyz.npy'), mmap_mode='r'); out = []
    for s in range(0, len(X), 20_000_000):
        q = np.asarray(X[s:s+20_000_000], np.float64); m = (q[:, 0] >= box[0]) & (q[:, 0] <= box[1]) & (q[:, 1] >= box[2]) & (q[:, 1] <= box[3]) & (q[:, 2] >= box[4]) & (q[:, 2] <= box[5]); out.append(q[m])
    return np.concatenate(out)
# ---------- 1 정답 지도
def fig1(F, R):
    fig, axs = plt.subplots(3, 2, figsize=(7.2, 9.2), constrained_layout=True); meta = dict(panels=[])
    for si, site in enumerate(SITE_LIST):
        for pi, prior in enumerate(PRIORS):
            ax = axs[si, pi]; P = geo(prior); f = F[prior][F[prior].site == site]; i = f.patch_index.values; c = P['centre'][i] + np.nan_to_num(P['prior_height_m'][i])[:, None]*np.nan_to_num(P['normal'][i])
            Fl = F['LoD2'][F['LoD2'].site == site]; Pl = geo('LoD2') if prior == 'ALS' else P; cl = Pl['centre'][Fl.patch_index.values]
            x0, x1 = cl[:, 0].min() - 4, cl[:, 0].max() + 4; y0, y1 = cl[:, 1].min() - 4, cl[:, 1].max() + 4
            ts = sorted(set(Pl['tiles'][Pl['tile'][Fl.patch_index.values]])); g = np.concatenate([tile_points(t, 'gt', (x0, x1, y0, y1, -1e9, 1e9)) for t in ts])
            res = .25; nx, ny = int((x1 - x0)/res) + 1, int((y1 - y0)/res) + 1; Z = np.full((ny, nx), -np.inf); ix = ((g[:, 0] - x0)/res).astype(int); iy = ((g[:, 1] - y0)/res).astype(int)
            np.maximum.at(Z, (iy, ix), g[:, 2]); Z[~np.isfinite(Z)] = np.nan; Zf = np.where(np.isfinite(Z), Z, np.nanmin(Z))
            gy, gx = np.gradient(Zf, res); az, al = np.deg2rad(315), np.deg2rad(45); sl = np.arctan(np.hypot(gx, gy)); asp = np.arctan2(-gx, gy)
            hs = np.clip(np.sin(al)*np.cos(sl) + np.cos(al)*np.sin(sl)*np.cos(az - asp), 0, 1); hs[np.isnan(Z)] = 1
            ax.imshow(.55 + .45*hs, cmap='gray', vmin=0, vmax=1, origin='lower', extent=(x0, x1, y0, y1), interpolation='nearest')
            img = np.zeros((ny, nx, 4))
            for kk in [2, 1]:   # 벽 먼저, 지붕 나중
                m = f.kind.values == kk
                if not m.any(): continue
                jx = ((c[m, 0] - x0)/res).astype(int); jy = ((c[m, 1] - y0)/res).astype(int); ok = (jx >= 0) & (jx < nx) & (jy >= 0) & (jy < ny)
                rgb = np.array([matplotlib.colors.to_rgba(COL[a]) for a in f.answer.values[m]]); img[jy[ok], jx[ok]] = rgb[ok]
            ax.imshow(img, origin='lower', extent=(x0, x1, y0, y1), interpolation='nearest')
            r = R[prior] if REVON else pd.DataFrame(dict(x=[], y=[], answer=[], far=[]))
            r = r[r.far.astype(bool) & (r.x >= x0) & (r.x <= x1) & (r.y >= y0) & (r.y <= y1)]
            if REVON: ax.scatter(r.x, r.y, s=1.2, marker='s', facecolors='none', edgecolors=[COL[a] for a in r.answer], linewidths=.35)
            ax.set_xlim(x0, x1); ax.set_ylim(y0, y1); ax.set_aspect('equal'); ax.set_xticks([]); ax.set_yticks([])
            ax.set_title(f'{site} · {PN[prior]}'); A = f.area_m2.sum()
            ax.text(.0, -.02, f'정방향 {A:,.0f} m²' + (f' · 떨어진 역방향 {len(r):,}개' if REVON else ''), transform=ax.transAxes, va='top', fontsize=5.5, color='#444441')
            ax.plot([x1 - 12, x1 - 2], [y0 + 2, y0 + 2], color='k', lw=1); ax.text(x1 - 7, y0 + 2.6, '10 m', ha='center', fontsize=5.5)
            meta['panels'].append(dict(site=site, prior=prior, extent=[x0, x1, y0, y1], forward_area_m2=A, forward_area_by_answer={a: float(f.area_m2[f.answer == a].sum()) for a in FWD + [FWD_X]},
                                       reverse_far_by_answer={a: int((r.answer == a).sum()) for a in REV} if REVON else None, tiles=ts))
    hand = [Patch(color=COL[a], label=a) for a in FWD] + ([Patch(facecolor='none', edgecolor=COL[a], label=f'역방향 {a}') for a in REV] if REVON else [])
    fig.legend(handles=hand, loc='lower center', ncol=3, fontsize=6, frameon=False, bbox_to_anchor=(.5, -.045))
    fig.suptitle('세 실험 지역의 판단 정답(위에서 본 지도, 바탕 = 드론 LiDAR 음영)', fontsize=9)
    meta['include_reverse'] = REVON; fsave(fig, 'fig1_정답지도', meta)
# ---------- 예시 고르기
def comps(xyz, rad=.36):
    t = cKDTree(xyz); pr = t.query_pairs(rad, output_type='ndarray'); n = len(xyz)
    if len(pr) == 0: return np.arange(n)
    g = coo_matrix((np.ones(len(pr)), (pr[:, 0], pr[:, 1])), shape=(n, n)); return connected_components(g, directed=False)[1]
def pick(xyz, area, bld, k=2):
    """넓이가 큰 연결 모임에서 한 건물에 하나: 모임 무게 중심에 가장 가까운 패치."""
    if len(xyz) == 0: return []
    lab = comps(xyz); A = np.bincount(lab, weights=area); out = []; used = set()
    for L in np.argsort(-A):
        m = np.flatnonzero(lab == L); b = bld[m[0]]
        if b in used: continue
        ctr = xyz[m].mean(0); j = m[np.argmin(((xyz[m] - ctr)**2).sum(1))]; out.append((j, float(A[L]))); used.add(b)
        if len(out) == k: break
    return out
def fwd_examples(F, Pg, prior, mask, k=2):
    f = F[prior][mask]; i = f.patch_index.values; xyz = Pg['centre'][i]; return [(f.iloc[j], a) for j, a in pick(xyz, f.area_m2.values, f.building.values, k)]
def rev_examples(R, Pg, prior, ans, k=2):
    r = R[prior][R[prior].answer == ans]; xyz = r[['x', 'y', 'z']].values; b = Pg['building'][r.near_patch_index.values]
    return [(r.iloc[j], a) for j, a in pick(xyz, r.area_m2.values, b, k)]
def perp(n):
    a = np.array([0, 0, 1.]) if abs(n[2]) < .9 else np.array([1., 0, 0]); u = np.cross(a, n); return u/np.linalg.norm(u)
def ex_forward(row, Pg):
    i = int(row.patch_index); n = Pg['normal'][i]; ph = Pg['prior_height_m'][i]; ref = Pg['centre'][i] + np.nan_to_num(ph)*n; u = Pg['tangent1'][i] - (Pg['tangent1'][i]@n)*n; u /= np.linalg.norm(u)
    H = 5. if row.kind == 2 else 10.
    return dict(ref=ref, n=n, u=u, H=H, tau=row.tau_m, hM=row.h_M_m, tile=Pg['tiles'][Pg['tile'][i]], building=row.building, place=row.place, answer=row.answer, nb0=row.gt_band_prior, nbM=row.gt_band_image,
                patch_id=row.patch_id, surface=row.surface, clusters=[(row[f'cl{k}_n'], row[f'cl{k}_median_m']) for k in range(1, 7) if np.isfinite(row[f'cl{k}_n'])])
def ex_reverse(row, Pg):
    n = np.array([row.nx, row.ny, row.nz]); u = perp(n); H = 5. if row.surface == '벽' else 10.
    return dict(ref=np.array([row.x, row.y, row.z]), n=n, u=u, H=H, tau=row.tau_m, hM=np.nan, tile=row.tile, building=Pg['building'][int(row.near_patch_index)], place=f'옆 {row.near_lateral_m:.2f} m·법선 {row.near_normal_m:+.2f} m',
                answer=row.answer, nb0=row.gt_band, nbM=np.nan, patch_id=f'영상 쪽 {row.x:.2f},{row.y:.2f},{row.z:.2f}', surface=row.surface, clusters=[])
class Slices:
    """단면용 점: 구역마다 한 번 읽어 예시 주변만 남김."""
    def __init__(s, exs):
        s.cache = {}; by = {}
        for e in exs: by.setdefault(e['tile'], []).append(e)
        for t, es in by.items():
            P = np.array([e['ref'] for e in es]); lo = P.min(0) - 11; hi = P.max(0) + 11; box = (lo[0], hi[0], lo[1], hi[1], lo[2], hi[2])
            for kind in ['gt', 'mvs']:
                X = tile_points(t, kind, box); tr = cKDTree(X)
                for e in es: e[kind] = X[tr.query_ball_point(e['ref'], r=np.hypot(e['H'], 3.2))]
def draw(ax, e, Sp, extra=''):
    n, u, ref = e['n'], e['u'], e['ref']; v = np.cross(n, u); W = 3.0
    def loc(X):
        d = X - ref; t = d@n; a = d@u; b = d@v; m = (np.abs(b) <= .125) & (np.abs(a) <= W) & (np.abs(t) <= e['H']); return a[m], t[m]
    hM = e['hM']; lo = min(0, hM if np.isfinite(hM) else 0) - 2.0; hi = max(0, hM if np.isfinite(hM) else 0) + 2.0
    for (ca, cm) in e['clusters']: lo = min(lo, cm - 1); hi = max(hi, cm + 1)
    lo = max(lo, -e['H']); hi = min(hi, e['H'])
    ax.add_patch(Rectangle((-.125, -e['tau']), .25, 2*e['tau'], color='#7F77DD' if e.get('rev') else '#AFA9EC', alpha=.45, lw=0, zorder=1))
    if np.isfinite(hM): ax.add_patch(Rectangle((-.125, hM - e['tau']), .25, 2*e['tau'], color='#97C459', alpha=.5, lw=0, zorder=1))
    ax.axvline(-.125, color='#5F5E5A', lw=.4, ls='--', zorder=2); ax.axvline(.125, color='#5F5E5A', lw=.4, ls='--', zorder=2)
    a, t = loc(Sp['prior']); ax.scatter(a, t, s=2.5, color='#534AB7', lw=0, zorder=3, label='사전 정보 면')
    a, t = loc(e['mvs']); ax.scatter(a, t, s=.6, color='#3B6D11', lw=0, alpha=.6, zorder=4, label='영상 깊이 점')
    a, t = loc(e['gt']); ax.scatter(a, t, s=1.0, color='k', lw=0, zorder=5, label='드론 LiDAR')
    for (ca, cm) in e['clusters']: ax.plot([.18, .5], [cm, cm], color='#A32D2D', lw=.8, zorder=6); ax.text(.55, cm, f'{int(ca)}', fontsize=5, color='#A32D2D', va='center')
    ax.set_xlim(-W, W); ax.set_ylim(lo, hi); ax.tick_params(labelsize=5, length=2, width=.4)
    if e.get('blind'):   # 덧붙임 4 점검: 정답 이름·색·점 수를 칸에 적지 않음
        for sp in ax.spines.values(): sp.set_color('#5F5E5A'); sp.set_linewidth(.8)
        ax.set_title(e['label'], fontsize=6.5, fontweight='bold', color='#2C2C2A')
        ax.text(0, -.13, f"{e['building'].replace('DEBY_LOD2_', '')} · {e['place']} · {e['surface']} · τ {e['tau']:.2f}", transform=ax.transAxes, fontsize=4.6, va='top'); return
    for sp in ax.spines.values(): sp.set_color(COL[e['answer']]); sp.set_linewidth(1.6)
    hm = f"{hM:+.2f}" if np.isfinite(hM) else '없음'; nbM = f"{int(e['nbM'])}" if np.isfinite(e['nbM']) and e['nbM'] >= 0 else '-'
    ax.set_title(e['answer'] + extra, color=COL[e['answer']] if e['answer'] != '정답 없음' else '#5F5E5A', fontweight='bold', fontsize=6.5)
    ax.text(0, -.13, f"{e['building'].replace('DEBY_LOD2_', '')} · {e['place']} · {e['surface']}\nh_M {hm} · 0±τ {int(e['nb0'])} · h_M±τ {nbM} · τ {e['tau']:.2f}", transform=ax.transAxes, fontsize=4.6, va='top')
def prior_surface(Pg, prior):
    ok = np.isfinite(Pg['prior_height_m']) & np.isfinite(Pg['normal']).all(1); return Pg['centre'][ok] + Pg['prior_height_m'][ok][:, None]*Pg['normal'][ok]
def attach_prior(exs, S):
    tr = cKDTree(S)
    for e in exs: e['prior_pts'] = S[tr.query_ball_point(e['ref'], r=np.hypot(e['H'], 3.2))]
def grid(exs, nrow, ncol, title, name, meta, extras=None):
    fig, axs = plt.subplots(nrow, ncol, figsize=(1.45*ncol + .3, 1.75*nrow + .6), constrained_layout=True); axs = np.atleast_2d(axs)
    for k, ax in enumerate(axs.flat):
        if k >= len(exs) or exs[k] is None: ax.axis('off'); continue
        e = exs[k]; draw(ax, e, dict(prior=e['prior_pts']), extras[k] if extras else '')
    hd = [Patch(color='k', label='드론 LiDAR'), Patch(color='#534AB7', label='사전 정보 면'), Patch(color='#3B6D11', label='영상 깊이 점'), Patch(color='#AFA9EC', label='0 ± τ'), Patch(color='#97C459', label=HLAB + ' ± τ')]
    fig.legend(handles=hd, loc='lower center', ncol=5, fontsize=5.5, frameon=False, bbox_to_anchor=(.5, -.03)); fig.suptitle(title, fontsize=8.5)
    fig.supxlabel('패치 칸 옆 방향 (m)', fontsize=6); fig.supylabel('법선 방향 거리 (m, 사전 정보 = 0)', fontsize=6)
    meta['examples'] = [None if e is None else {k: (v if not isinstance(v, np.ndarray) else v.tolist()) for k, v in e.items() if k not in ['gt', 'mvs', 'prior_pts']} for e in exs]; fsave(fig, name, meta)
def fig2(F, R):
    for prior in PRIORS:
        Pg = geo(prior); S = prior_surface(Pg, prior); exs = []; info = []
        for a in FWD:
            got = fwd_examples(F, Pg, prior, F[prior].answer == a)
            for k in range(2): exs.append(ex_forward(got[k][0], Pg) if k < len(got) else None); info.append(dict(answer=a, component_area_m2=got[k][1] if k < len(got) else None))
        for a in (REV if REVON else []):
            got = rev_examples(R, Pg, prior, a)
            for k in range(2):
                e = ex_reverse(got[k][0], Pg) if k < len(got) else None
                if e is not None: e['rev'] = True
                exs.append(e); info.append(dict(answer=f'역방향 {a}', component_area_m2=got[k][1] if k < len(got) else None))
        Slices([e for e in exs if e is not None]); attach_prior([e for e in exs if e is not None], S)
        grid(exs, 3 if REVON else 2, 6, f'{PN[prior]}: 정답 종류마다 본보기 둘의 단면 (테두리 색 = 정답)', f'fig2_정답단면_{prior}', dict(prior=prior, picks=info))
def fig3(F, R):
    t = pd.read_csv(D/'tables'/SUB/'t5b_top_changes.csv'); SRC['t5b'] = str(D/'tables'/SUB/'t5b_top_changes.csv')
    for prior in PRIORS:
        Pg = geo(prior); S = prior_surface(Pg, prior); exs = []; ext = []; info = []
        for _, r in t[t.prior == PN[prior]].iterrows():
            f = F[prior]; m = (f.answer == r.new) & (np.array([STATE[int(x)] for x in f.initial_state]) == r.old); got = fwd_examples(F, Pg, prior, m)
            for k in range(2):
                exs.append(ex_forward(got[k][0], Pg) if k < len(got) else None); ext.append(f'\n(옛: {r.old})'); info.append(dict(old=r.old, new=r.new, cell_area_m2=r.area_m2))
        Slices([e for e in exs if e is not None]); attach_prior([e for e in exs if e is not None], S)
        grid(exs, 2, 3, f'{PN[prior]}: 옛 정답과 새 정답이 다른 곳 (넓이 큰 칸 셋 × 본보기 둘, 제목 = 새 정답)', f'fig3_옛새차이_{prior}', dict(prior=prior, picks=info), ext)
def fig4(F, R):
    exs = []; info = []
    for surf, priors in [('지붕', ['LoD2', 'ALS']), ('벽', ['LoD2'])]:
        cand = []
        for prior in priors:
            Pg = geo(prior); f = F[prior]; m = (f.gt_clusters >= 2) & (f.surface == surf)
            for row, a in fwd_examples(F, Pg, prior, m, k=3): cand.append((a, prior, row, Pg))
        cand.sort(key=lambda x: -x[0]); used = set(); n = 0
        for a, prior, row, Pg in cand:
            if row.building in used and len(cand) > 3: continue
            e = ex_forward(row, Pg); attach_prior([e], prior_surface(Pg, prior)); e['prior_name'] = prior; exs.append(e); info.append(dict(surface=surf, prior=prior, component_area_m2=a)); used.add(row.building); n += 1
            if n == 3: break
        while n < 3: exs.append(None); n += 1
    Slices([e for e in exs if e is not None])
    grid(exs, 2, 3, '참값 무리가 둘 이상인 패치 (위 지붕, 아래 벽; 빨간 금 = 무리 중앙값과 점 수)', 'fig4_참값무리', dict(picks=info), [f" · {PN[e['prior_name']]}" if e else '' for e in exs])
def main(which):
    global COL, REVON
    c = cfg(); COL = c['colours']; REVON = c.get('include_reverse', True); F, R = tables()
    for w in which: dict(zip('1234', [fig1, fig2, fig3, fig4]))[w](F, R)
if __name__ == '__main__': main(sys.argv[1:] or list('1234'))
