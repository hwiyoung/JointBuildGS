"""그림 1 (판정 지도)과 그림 6의 캠퍼스 지도. 바탕 = 드론 LiDAR 색 정사영상(0.25 m, s9_ortho). 위에서 보이는 지붕·땅만 칠함(벽은 위에서 안 보여 칠하지 않음).
그림 1 대상: 세 실험 지역 장면 + 나머지 건물에서 규칙으로 고른 여섯 동(진짜 판정 오류 넓이 상위 셋, 네 경우 밖 넓이 상위 셋, 겹치면 다음 차례)."""
from common import *
import pandas as pd
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
from matplotlib.colors import to_rgba
from matplotlib.patches import Patch
from matplotlib import font_manager
import jc2_judge as J
from s7_tables import MATCH, area
FONT = '/fonts/NotoSansCJK-Regular.ttc'; font_manager.fontManager.addfont(FONT); plt.rcParams.update({'font.family': font_manager.FontProperties(fname=FONT).get_name(), 'axes.unicode_minus': False, 'font.size': 8})
FIG = D/'figures'
NINE_C = ['#bdbdbd', '#ff7f0e', '#9467bd', '#1f77b4', '#d62728', '#8c564b', '#17becf', '#e377c2', '#111111']
NINE_N = ['두 자료 유효', '영상 깊이 오류', '영상 깊이 결측', '사전정보 오류', '밖1', '밖2', '밖3', '밖4', '밖5']
JUD_C = {0: '#bdbdbd', 1: '#ff7f0e', 2: '#2ca02c', 4: '#9467bd', 3: '#111111', 9: '#ffff33'}; JUD_N = {0: '일치', 1: '사전정보 사용', 2: '영상 깊이 사용', 4: '결측', 3: '제거', 9: '미판정'}
TGT_C = {0: '#a6d96a', 1: '#fdae61', 2: '#d7191c'}; TGT_N = {0: '목표 맞음', 1: '목표 틀림', 2: '진짜 판정 오류'}
def ortho():
    z = loadz(O/'figures_cache/ortho_campus.npz', ['rgb', 'x0', 'y0', 'res']); return z['rgb'], float(z['x0']), float(z['y0']), float(z['res'])
def paint(ax, xy, val, colors, ext, res=.25, alpha=.75):
    x0, x1, y0, y1 = ext; W = int(np.ceil((x1 - x0)/res)); H = int(np.ceil((y1 - y0)/res)); img = np.zeros((H, W, 4))
    ix = ((xy[:, 0] - x0)/res).astype(int); iy = ((xy[:, 1] - y0)/res).astype(int); ok = (ix >= 0) & (iy >= 0) & (ix < W) & (iy < H)
    for k, c in colors.items():
        m = ok & (val == k)
        if m.any(): img[iy[m], ix[m]] = to_rgba(c, alpha)
    ax.imshow(img, origin='lower', extent=[x0, x0 + W*res, y0, y0 + H*res], interpolation='nearest')
def background(ax, ext, O_):
    rgb, X0, Y0, res = O_; x0, x1, y0, y1 = ext; i0 = max(int((x0 - X0)/res), 0); i1 = int((x1 - X0)/res); j0 = max(int((y0 - Y0)/res), 0); j1 = int((y1 - Y0)/res)
    ax.imshow(rgb[j0:j1, i0:i1], origin='lower', extent=[X0 + i0*res, X0 + i1*res, Y0 + j0*res, Y0 + j1*res], interpolation='bilinear')
    ax.set_xlim(x0, x1); ax.set_ylim(y0, y1); ax.set_aspect('equal'); ax.set_xticks([]); ax.set_yticks([])
def patch_arrays(prior):
    A = []
    for p in sorted((O/'geometry_raw').glob(f'*__{prior}.npz')):
        g = loadz(p, ['centre', 'kind', 'building', 'area', 'prior_height_m', 'normal']); j = loadz(O/'judge/base'/p.name, ['region']); g['region'] = j['region'][J.VARIANTS.index('method')]; A.append(g)
    return {k: np.concatenate([a[k] for a in A]) for k in A[0]}
def targets(prior, d):
    mi = J.VARIANTS.index('method'); four = d['paired'] & np.isin(d['case'], [0, 1, 2, 4]); match = np.array([MATCH.get(int(c), -9) for c in d['case']])
    te = four & (d['region_v'][mi] != match) & ~d['target_ok_v'][mi]; out = d['paired'] & (d['nine'] >= 4)
    rest = d['paired'] & (d['group'] == 'rest'); rows = []
    for b in sorted(set(d['building'][rest])):
        m = rest & (d['building'] == b); rows.append(dict(building=b, true_error_area=area(d['cell'][m & te]), outside_area=area(d['cell'][m & out])))
    df = pd.DataFrame(rows); chosen = []
    for col in ['true_error_area', 'outside_area']:
        k = 0
        for b in df.sort_values(col, ascending=False)['building']:
            if b in chosen: continue
            chosen.append(b); k += 1
            if k == 3: break
    return chosen, te, df
def fig1():
    O_ = ortho()
    for prior in ['LoD2', 'ALS']:
        d = loadz(O/'analysis'/f'gt_{prior}.npz'); P = patch_arrays(prior); mi = J.VARIANTS.index('method')
        chosen, te, df = targets(prior, d); scenes = []
        for site in SITES:
            m = (d['src'] == 1) & (d['site'] == site); xy = d['xyz'][m, :2]; scenes.append((site, m, [xy[:, 0].min() - 3, xy[:, 0].max() + 3, xy[:, 1].min() - 3, xy[:, 1].max() + 3]))
        for b in chosen:
            m = d['paired'] & (d['building'] == b); pm = P['building'] == b; xy = np.r_[d['xyz'][m, :2], P['centre'][pm, :2]]; scenes.append((b.replace('DEBY_LOD2_', ''), m, [xy[:, 0].min() - 3, xy[:, 0].max() + 3, xy[:, 1].min() - 3, xy[:, 1].max() + 3]))
        fig, axs = plt.subplots(len(scenes), 3, figsize=(10, 3.2*len(scenes))); meta = []
        for r, (name, m, ext) in enumerate(scenes):
            top = m & (d['gt_kind'] != 2); pin = (P['kind'] == 1) & (P['centre'][:, 0] >= ext[0]) & (P['centre'][:, 0] <= ext[1]) & (P['centre'][:, 1] >= ext[2]) & (P['centre'][:, 1] <= ext[3])
            tv = np.where(te[top], 2, np.where(d['target_ok_v'][mi][top], 0, 1))
            for c, (title, xy, val, cols) in enumerate([('(가) 아홉 조합', d['xyz'][top, :2], d['nine'][top], dict(enumerate(NINE_C))),
                                                        ('(나) 본 방법 판정', P['centre'][pin, :2] + np.nan_to_num(P['prior_height_m'][pin])[:, None]*0, P['region'][pin], JUD_C),
                                                        ('(다) 목표 맞음·틀림', d['xyz'][top, :2], tv, TGT_C)]):
                ax = axs[r, c]; background(ax, ext, O_); paint(ax, xy, val, cols, ext); ax.set_title(f'{name} {title}' if c == 0 else title, fontsize=8)
            n4 = m & np.isin(d['case'], [0, 1, 2, 4]); axs[r, 0].set_xlabel(f'참값 점 {int(m.sum()):,} · 진짜 판정 오류 {area(d["cell"][m & te]):.0f} m² · 네 경우 밖 {area(d["cell"][m & (d["nine"] >= 4)]):.0f} m²', fontsize=7)
            meta.append(dict(scene=name, extent=ext, gt_points=int(m.sum()), patches=int(pin.sum())))
        h = [Patch(color=c, label=n) for c, n in zip(NINE_C, NINE_N)] + [Patch(color=JUD_C[k], label=JUD_N[k]) for k in JUD_C] + [Patch(color=TGT_C[k], label=TGT_N[k]) for k in TGT_C]
        fig.legend(handles=h, ncol=7, fontsize=6.5, loc='lower center', bbox_to_anchor=(.5, -.01), frameon=False)
        fig.suptitle(f'{prior}: 판정 지도 — 세 실험 지역과 규칙으로 고른 여섯 동, 아홉 조합·본 방법 판정·목표 맞음', fontsize=10, y=1.0)
        fig.tight_layout(rect=[0, .02, 1, .99]); fig.savefig(FIG/f'fig1_judgment_map_{prior}.png', dpi=300, facecolor='white', bbox_inches='tight'); plt.close(fig)
        dump(FIG/f'fig1_judgment_map_{prior}.json', dict(prior=prior, scenes=meta, chosen_rule='rest buildings: top 3 true-error area, top 3 outside-four area (nine 4-8), next on overlap', chosen=chosen, selection_table=json.loads(df.to_json(orient='records')), colours=dict(nine=NINE_C, judgment=JUD_C, target=TGT_C), ortho='figures_cache/ortho_campus.npz', scientific_verdict=None))
def campus_map():
    O_ = ortho(); rgb, X0, Y0, res = O_
    for prior in ['LoD2', 'ALS']:
        b = pd.read_csv(D/'tables'/f'c5_buildings_outside_{prior}.csv'); P = patch_arrays(prior); fig, ax = plt.subplots(figsize=(8, 8))
        H, Wd = rgb.shape[:2]; ax.imshow(rgb, origin='lower', extent=[X0, X0 + Wd*res, Y0, Y0 + H*res]); vals = dict(zip(b.building, b.outside_pct))
        cm = plt.get_cmap('magma_r'); v = np.array([vals.get(x, np.nan) for x in P['building']]); ok = np.isfinite(v) & (P['kind'] == 1)
        sc = ax.scatter(P['centre'][ok, 0], P['centre'][ok, 1], c=v[ok], s=.05, cmap=cm, vmin=0, vmax=max(20, np.nanpercentile(v[ok], 99)), lw=0)
        xy = P['centre'][P['kind'] == 1, :2]; ax.set_xlim(xy[:, 0].min() - 10, xy[:, 0].max() + 10); ax.set_ylim(xy[:, 1].min() - 10, xy[:, 1].max() + 10); ax.set_aspect('equal'); ax.set_xticks([]); ax.set_yticks([])
        plt.colorbar(sc, ax=ax, shrink=.6, label='네 경우 밖 비율 (%)'); ax.set_title(f'{prior}: 건물마다 네 경우 밖(아홉 조합 4~8) 참값 점 비율', fontsize=9)
        fig.savefig(FIG/f'fig6_campus_map_{prior}.png', dpi=300, facecolor='white', bbox_inches='tight'); plt.close(fig)
        dump(FIG/f'fig6_campus_map_{prior}.json', dict(prior=prior, source=f'tables/c5_buildings_outside_{prior}.csv', scientific_verdict=None))
if __name__ == '__main__':
    for f in sys.argv[1:]: globals()[f]()
