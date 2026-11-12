"""그림 2 (건물별 분포), 3 (자리별), 4 (민감도). 표 파일에서 그린다. 그림마다 같은 이름의 json."""
from common import *
import pandas as pd
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
from matplotlib import font_manager
FONT = '/fonts/NotoSansCJK-Regular.ttc'; font_manager.fontManager.addfont(FONT); plt.rcParams.update({'font.family': font_manager.FontProperties(fname=FONT).get_name(), 'axes.unicode_minus': False, 'font.size': 9})
FIG = D/'figures'; TAB = D/'tables'
CASES = ['두 자료 모두 유효', '사전정보 오류', '영상 깊이 오류', '영상 깊이 결측']
COL = {'본 방법': '#1f4e9c', '사전 정보 단독': '#d9822b', '영상 단독': '#2e8b57'}
def save(fig, name, meta):
    FIG.mkdir(parents=True, exist_ok=True); fig.savefig(FIG/f'{name}.png', dpi=300, facecolor='white', bbox_inches='tight'); plt.close(fig)
    dump(FIG/f'{name}.json', dict(meta, png=f'{name}.png', dpi=300, scientific_verdict=None))
def fig2():
    for prior in ['LoD2', 'ALS']:
        b = pd.read_csv(TAB/f'c1_buildings_{prior}.csv'); fig, ax = plt.subplots(figsize=(7.5, 3.6))
        for k, c in enumerate(CASES):
            x = b[(b.case == c) & (b.n >= 200)]
            for off, v, col, a in [(-.22, 'prior_only', COL['사전 정보 단독'], .25), (.22, 'image_only', COL['영상 단독'], .25), (0, 'method', COL['본 방법'], .85)]:
                y = x[f'{v}_target_ok_pct']; jit = np.random.default_rng(k).uniform(-.06, .06, len(y))
                ax.scatter(k + off + jit, y, s=8 if v == 'method' else 5, c=col, alpha=a, lw=0)
            e = x[x.group == 'experiment']; ax.scatter(np.full(len(e), k) + np.random.default_rng(9).uniform(-.06, .06, len(e)), e['method_target_ok_pct'], s=26, facecolors='none', edgecolors='#c0392b', lw=1.1)
            ax.text(k, -9, f'{len(x)}동', ha='center', fontsize=7, color='#555')
        ax.set_xticks(range(4)); ax.set_xticklabels(CASES); ax.set_ylim(-12, 104); ax.set_ylabel('목표 맞음 (%)')
        ax.scatter([], [], c=COL['본 방법'], s=8, label='본 방법'); ax.scatter([], [], c=COL['사전 정보 단독'], alpha=.4, s=6, label='사전 정보 단독'); ax.scatter([], [], c=COL['영상 단독'], alpha=.4, s=6, label='영상 단독'); ax.scatter([], [], facecolors='none', edgecolors='#c0392b', s=26, label='세 실험 지역 건물')
        ax.legend(fontsize=7, ncol=4, loc='upper center', bbox_to_anchor=(.5, 1.13), frameon=False); ax.set_title(f'{prior}: 경우마다 건물별 목표 맞음 — 세 실험 지역 건물이 분포의 어디에 있나', fontsize=9, pad=22)
        q = {c: b[(b.case == c) & (b.n >= 200)]['method_target_ok_pct'].quantile([.25, .5, .75]).round(1).tolist() for c in CASES}
        fig.text(.01, -.04, '본 방법 건물별 사분위(25/50/75 %): ' + '; '.join(f'{c} {v}' for c, v in q.items()) + ' (참값 200개 이상 건물)', fontsize=6.5)
        save(fig, f'fig2_building_distribution_{prior}', dict(prior=prior, source=f'tables/c1_buildings_{prior}.csv', rule='건물 x 경우, 참값 200개 이상만', quartiles=q))
def fig3():
    for prior in ['LoD2', 'ALS']:
        s = pd.read_csv(TAB/f'c1_case_summary_{prior}.csv'); s = s[(s.group == '전체') & (s.surface == ('모두' if prior == 'LoD2' else '지붕'))]
        places = ['면 안쪽', '면 경계', '건물 가장자리']; fig, axs = plt.subplots(1, 3, figsize=(9, 3), sharey=True)
        for ax, pl in zip(axs, places):
            for i, (v, col) in enumerate(COL.items()):
                y = [s[(s.place == pl) & (s.variant == v) & (s.case == c)]['target_ok_pct'].values for c in CASES]; y = [x[0] if len(x) else np.nan for x in y]
                ax.bar(np.arange(4) + (i - 1)*.27, y, .26, color=col, label=v)
            ax.set_xticks(range(4)); ax.set_xticklabels(['유효', '사전정보\n오류', '영상깊이\n오류', '영상깊이\n결측'], fontsize=7); ax.set_title(pl, fontsize=9); ax.set_ylim(0, 100)
        axs[0].set_ylabel('목표 맞음 (%)'); axs[0].legend(fontsize=7, frameon=False)
        fig.suptitle(f'{prior}: 자리마다 경우별 목표 맞음 — 본 방법과 두 기준', fontsize=9.5)
        save(fig, f'fig3_place_{prior}', dict(prior=prior, source=f'tables/c1_case_summary_{prior}.csv'))
def fig4():
    s = pd.read_csv(TAB/'c2_sensitivity.csv'); s = s[s['kind'] != '패치']
    order = ['본값', '고리 1.0 m', '고리 3.0 m', '배수 1.645', '배수 2.576', '가운데 옮김', '건물마다 r', '같은 면 고리']
    for prior in ['LoD2', 'ALS']:
        fig, axs = plt.subplots(1, 4, figsize=(11, 3), sharey=True); x = s[s.prior == prior]
        for ax, pl in zip(axs, ['모든 자리', '면 안쪽', '면 경계', '건물 가장자리']):
            for c, col in zip(CASES, ['#555', '#c0392b', '#2e8b57', '#1f4e9c']):
                y = [x[(x.place == pl) & (x.variant == v) & (x.case == c)]['target_ok_pct'].values for v in order]; y = [a[0] if len(a) else np.nan for a in y]
                ax.plot(range(len(order)), y, '-o', ms=3, lw=1, color=col, label=c)
            ax.set_xticks(range(len(order))); ax.set_xticklabels(order, rotation=60, fontsize=6.5, ha='right'); ax.set_title(pl, fontsize=9); ax.set_ylim(0, 100)
        axs[0].set_ylabel('목표 맞음 (%)'); axs[0].legend(fontsize=6.5, frameon=False)
        fig.suptitle(f'{prior}: 설정을 하나씩 바꾼 판마다 경우별 목표 맞음', fontsize=9.5)
        save(fig, f'fig4_sensitivity_{prior}', dict(prior=prior, source='tables/c2_sensitivity.csv', variants=order))
if __name__ == '__main__':
    for f in sys.argv[1:]: globals()[f]()
