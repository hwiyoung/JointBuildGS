"""Order 5 tables, summary and figures (CPU, reads /tp/fill). usage: tp11_fill_out.py
tables/tp_fill.csv (scene x extraction x fill), 채움_요약.md, figures/fill_<place>.png (+json): R1 바닥 띠 (R1 x ALS), R1 x LoD2 1번 벽,
B0 잘 보이는 벽 (B0 x LoD2, 0-5 m and 5-10 m together), B173 주변 날개 (B173 x ALS, the largest cluster of fixed points).
Three panels per fill (before | 채움 1 | 채움 2 | 채움 3 as rows): photo with the filled discs (centres) of that fill, top view (GT points, filled discs:
target right = green, wrong = red), section +-0.25 m (GT, result surface of the base extraction, filled discs)."""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_targetpath_v1')
from tp_common import *
from scipy import ndimage
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt; from matplotlib import font_manager as fm
fm.fontManager.addfont('/fonts/NotoSansCJK-Regular.ttc'); plt.rcParams['font.family'] = fm.FontProperties(fname='/fonts/NotoSansCJK-Regular.ttc').get_name(); plt.rcParams['axes.unicode_minus'] = False
from PIL import Image
VAR = ['채움 1', '채움 2', '채움 3']

def md(head, rows): return '\n'.join(['| '+' | '.join(head)+' |', '|'+'---|'*len(head)]+['| '+' | '.join(r)+' |' for r in rows])
def f(v, d=2): return '·' if v in (None, '') else f'{float(v):.{d}f}'

def place_points(name):
    if name == 'floor_band': z = loadz(TE/'addendum4/places/floor_band.npz'); return 'R1rep_b10__ALS', 'R1 바닥 띠', z['xyz'].astype('f8'), z['normal'].astype('f8')
    if name == 'r1_lod2_wall1': z = loadz(TE/'addendum5/places/r1_lod2_wall1.npz'); return 'R1rep_b10__LoD2', 'R1 × LoD2 1번 벽', z['xyz'].astype('f8'), z['normal'].astype('f8')
    if name == 'b0_visible_wall':
        a = loadz(TE/'addendum4/places/visible_low.npz'); b = loadz(TE/'addendum4/places/visible_high.npz')
        return 'B0_b10__LoD2', 'B0 잘 보이는 벽', np.r_[a['xyz'], b['xyz']].astype('f8'), np.r_[a['normal'], b['normal']].astype('f8')
    P = loadz(O/'points'/'sel_B173nb_b10__ALS.npz'); idx = np.flatnonzero(P['group'] == 2); xy = P['xyz'][idx, :2]; lo = xy.min(0); ij = np.floor(xy-lo).astype(int)
    G = np.zeros(ij.max(0)+1, bool); G[ij[:, 0], ij[:, 1]] = True; lab, n = ndimage.label(G, np.ones((3, 3))); l = lab[ij[:, 0], ij[:, 1]]; big = np.bincount(l)[1:].argmax()+1
    m = idx[l == big]; return 'B173nb_b10__ALS', 'B173 주변 날개(고친 점이 많은 자리)', P['xyz'][m].astype('f8'), P['normal'][m].astype('f8')

def figure(key):
    stem, title, X, Nx = place_points(key); site, prior = stem.split('__'); F = loadz(O/'fill'/f'{stem}.npz'); T = loadz(FT/'targets'/f'{stem}.npz', ['target', 'normal', 'area'])
    A = gt_reference(stem); RX = A['reference__xyz'].astype('f8'); RN = A['reference__normal'].astype('f8'); s0 = A['reference__FINALTRAIN_30000__s_m'].astype('f8')
    c0 = np.median(X, 0); lo = X.min(0)-2; hi = X.max(0)+2; box = lambda P: ((P >= lo) & (P <= hi)).all(1)
    nrm = np.median(Nx, 0); hv = nrm[:2].copy()
    if np.linalg.norm(hv) < .3: e, V = np.linalg.eigh(np.cov((X[:, :2]-c0[:2]).T)); hv = V[:, 0]
    hv = hv/np.linalg.norm(hv); perp = np.array([-hv[1], hv[0]])
    idx = json.loads((maps_of(stem, 'ft')/'index.json').read_text())['views']; best = None
    for nm, v in idx.items():
        K = np.asarray(v['K']); M = np.asarray(v['W2C']); u, w, z, ok = project(X, K, M); inn = ok & (u >= 0) & (u < 1024) & (w >= 0) & (w < 741)
        cs = ((cam_centre(M)[None]-X)*Nx).sum(1)/np.linalg.norm(cam_centre(M)[None]-X, axis=1); sc = (inn & (cs > 0)).mean()*max(np.median(cs), 0)
        if best is None or sc > best[0]: best = (sc, nm)
    nm = best[1]; v = idx[nm]; K = np.asarray(v['K']); M = np.asarray(v['W2C']); img = np.asarray(Image.open(S0/'fork_inputs/s61'/site/f'scene_{prior}'/'images'/f'{nm}.jpg').convert('RGB').resize((1024, 741)))
    u, w, z, _ = project(X, K, M); x0, x1 = int(max(0, u.min()-80)), int(min(1024, u.max()+80)); y0, y1 = int(max(0, w.min()-80)), int(min(741, w.max()+80))
    gm = box(RX); fig, axs = plt.subplots(4, 3, figsize=(16, 18)); info = dict(figure=f'fill_{key}.png', scene=STEM_KO[stem], place=title, view=nm, rows={})
    for ri, vn in enumerate(['채우기 앞'] + VAR):
        a0, a1, a2 = axs[ri]
        a0.imshow(img[y0:y1, x0:x1]); a0.scatter(u-x0, w-y0, s=1, c='yellow', lw=0, alpha=.5)
        a1.scatter(RX[gm, 0], RX[gm, 1], s=.3, c='#BBBBBB', lw=0); a1.scatter(X[:, 0], X[:, 1], s=.5, c='y', lw=0)
        dsec = (RX[:, :2]-c0[:2])@perp; ssec = (RX[:, :2]-c0[:2])@hv; sl = gm & (np.abs(dsec) <= .25)
        a2.scatter(ssec[sl], RX[sl, 2], s=2, c='k', lw=0, label='참값')
        ok = sl & np.isfinite(s0); Y = RX[ok]+s0[ok, None]*RN[ok]; a2.scatter((Y[:, :2]-c0[:2])@hv, Y[:, 2], s=2, c='#1F77B4', lw=0, label='결과 면(기준 추출)')
        r = dict()
        if vn != '채우기 앞':
            p = F[f'{vn}__patches']; wr = F[f'{vn}__wrong']; C = T['target'][p]; inb = box(C); p, wr, C = p[inb], wr[inb], C[inb]
            uc, wc, zc, okc = project(C, K, M); vis = okc & (uc >= x0) & (uc < x1) & (wc >= y0) & (wc < y1)
            a0.scatter(uc[vis & ~wr]-x0, wc[vis & ~wr]-y0, s=6, c='#2CA02C', lw=0); a0.scatter(uc[vis & wr]-x0, wc[vis & wr]-y0, s=8, c='#D62728', lw=0)
            a1.scatter(C[~wr, 0], C[~wr, 1], s=4, c='#2CA02C', lw=0, label='채운 원반(목표 맞음)'); a1.scatter(C[wr, 0], C[wr, 1], s=6, c='#D62728', lw=0, label='채운 원반(목표 틀림)')
            ds = (C[:, :2]-c0[:2])@perp; ss = (C[:, :2]-c0[:2])@hv; cs_ = np.abs(ds) <= .3
            for k in np.flatnonzero(cs_):
                n_ = T['normal'][p[k]]; rad = np.sqrt(T['area'][p[k]]/np.pi); tvec = np.cross(n_, [perp[0], perp[1], 0]); tvec = tvec/max(np.linalg.norm(tvec), 1e-9)
                e1, e2 = C[k]-rad*tvec, C[k]+rad*tvec; a2.plot([(e1[:2]-c0[:2])@hv, (e2[:2]-c0[:2])@hv], [e1[2], e2[2]], c='#D62728' if wr[k] else '#2CA02C', lw=2)
            r = dict(filled_in_place=int(len(p)), wrong_in_place=int(wr.sum()), area_in_place_m2=float(T['area'][p].sum()))
        a0.set_title(f'{vn} · 사진', fontsize=9); a1.set_title(f'{vn} · 위에서 본 자리', fontsize=9); a1.set_aspect('equal'); a2.set_title(f'{vn} · 단면 ±0.25 m', fontsize=9)
        a2.set_xlim(-8, 8); a2.set_xlabel('단면 방향 거리 (m)'); a2.set_ylabel('높이 (m)')
        if ri == 1: a1.legend(fontsize=7, markerscale=3); a2.legend(fontsize=7, markerscale=3)
        for a in [a0]: a.set_xticks([]); a.set_yticks([])
        info['rows'][vn] = r
    fig.suptitle(f'{STEM_KO[stem]} · {title} · 채우기 앞과 뒤 (초록 = 목표가 참값의 τ 안, 빨강 = 밖) · 영상 {nm}', fontsize=11); fig.tight_layout(rect=(0, 0, 1, .975))
    p = D/'figures'/f'fill_{key}.png'; fig.savefig(p, dpi=110); plt.close(fig)
    dump(p.with_suffix('.json'), dict(info, colours={'목표 맞음': '#2CA02C', '목표 틀림': '#D62728', '결과 면': '#1F77B4', '참값': 'k', '자리 점': 'yellow'},
                                      note='채운 원반은 규칙(가우시안 없음·그려지지 않음)으로 골랐고, 맞음/틀림 색만 참값으로 칠했다(채점).', scientific_verdict=None))
    print('FILL_FIG', key, flush=True)

def main():
    rows = []
    for stem in STEMS:
        p = O/'fill'/f'{stem}.json'
        if p.exists(): rows += json.loads(p.read_text())['rows']
    table('tp_fill', rows)
    out = ['### 채우기 표 (5절)', '', '규칙에 참값을 쓰지 않았다. 채운 면의 맞음·틀림과 완전성·정확성만 참값으로 셌다. 원반을 TSDF를 거치지 않고 추출 면에 바로 더한 모의다(`issues.md`).', '',
           md(['장면', '추출', '판', '조각', '넓이 m²', '완전성 앞→뒤 %', '정확성 앞→뒤 %', '채운 면 τ 안 %', '틀린 조각(넓이 m²)', '틀린 조각 중 고친 점 든 조각(넓이 m²)'],
              [[r['stem'], r['extraction'], r['fill'], str(r['patches']), f(r['area_m2'], 1), f"{f(r['completeness_before_pct'])} → {f(r['completeness_after_pct'])}", f"{f(r['accuracy_before_pct'])} → {f(r['accuracy_after_pct'])}",
                f(r['filled_area_within_tau_pct'], 1), f"{r['wrong_patches']} ({f(r['wrong_area_m2'], 1)})", f"{r['wrong_with_fixed_points']} ({f(r['wrong_with_fixed_area_m2'], 2)})"] for r in rows]), '',
           '네 경우의 완전성(%) 앞 → 뒤:', '',
           md(['장면', '추출', '판', '둘 다 맞음', '사전 정보가 틀린 곳', '영상이 틀린 곳', '영상 없음', '둘 다 틀림'],
              [[r['stem'], r['extraction'], r['fill']]+[f"{f(r[f'case_{k}_before_pct'])} → {f(r[f'case_{k}_after_pct'])}" for k in ['둘 다 맞음', '사전 정보가 틀린 곳', '영상이 틀린 곳', '영상 없음', '둘 다 틀림']] for r in rows]), '',
           '채운 조각의 판단 영역(넓이 %):', '',
           md(['장면', '판', '일치', '보존', '보정', '보정(빈 공간)', '결측', '미판정'], [[r['stem'], r['fill']]+[f(r[f'region_{k}_area_pct'], 1) for k in ['일치', '보존', '보정', '보정(빈 공간)', '결측', '미판정']] for r in rows if r['extraction'] == '기준']), '',
           '- 고친 점 쪽: 완전성 규칙(점의 법선을 따라 가장 가까운 면)에서는 면을 더해도 이미 τ 안인 점이 τ 밖으로 바뀌지 않는다. 그래서 고친 점에 미치는 값은 "틀린 목표 원반이 다시 놓인 조각 수와 넓이"와 정확성으로 본다.']
    (D/'채움_요약.md').write_text('\n'.join(out)+'\n')
    for k in ['floor_band', 'r1_lod2_wall1', 'b0_visible_wall', 'b173_wing']:
        try: figure(k)
        except Exception as e: print('FILL_FIG_FAIL', k, repr(e), flush=True); issue(f'5절 그림 {k} 실패: {e!r}')
    print('TP11_DONE', len(rows), flush=True)

if __name__ == '__main__': main()
