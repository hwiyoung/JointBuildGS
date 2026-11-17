"""그림 1·2·5 (발주 6절, 묶음 가). 표 s_all_variants 에서 그린다. 그림마다 json."""
from common import *
import pandas as pd
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
from matplotlib import font_manager
FONT = '/fonts/NotoSansCJK-Regular.ttc'; font_manager.fontManager.addfont(FONT); plt.rcParams.update({'font.family': font_manager.FontProperties(fname=FONT).get_name(), 'axes.unicode_minus': False, 'font.size': 7})
FIG = D/'figures'; TAB = D/'tables'; CN = [CASE[c] for c in CASES]
CCOL = {'두 자료 모두 유효': '#2ca02c', '사전정보 오류': '#ff7f0e', '영상 깊이 오류': '#1f77b4', '영상 깊이 결측': '#9467bd'}
VCOL = {'사전 정보 단독': '#d9822b', '영상 단독': '#2e8b57', '본 방법': '#1f4e9c', '패치 다수결 상한': '#ffffff'}
OLD = [('기존 1 T=0.5 m', '기존 1 (0.5 m)', '#b0b0b0'), ('기존 1 T=1 m', '기존 1 (1.0 m)', '#8a8a8a'), ('기존 2 대표(저장된 L)', '기존 2', '#c5a3d6'), ('기존 3 아래 5 %', '기존 3', '#e3b505'),
       ('기존 5 T=0.5 m', '기존 5 (0.5 m)', '#d98880'), ('기존 5 T=L', '기존 5 (L)', '#a93226')]
SHORT = {'사전 정보 단독': '사전 정보 단독', '영상 단독': '영상 단독', '본 방법': '본 방법', '패치 다수결 상한': '상한', '기존 4 결합(세 실험 지역)': '기존 4', '기존 4 결합(전 건물)': '기존 4'}
PSURF = {'LoD2': '모두', 'ALS': '지붕'}; PNAME = {'LoD2': 'LoD2', 'ALS': '항공 LiDAR'}
def save(fig, name, meta):
    FIG.mkdir(parents=True, exist_ok=True); fig.savefig(FIG/f'{name}.png', dpi=300, facecolor='white', bbox_inches='tight'); plt.close(fig); dump(FIG/f'{name}.json', dict(meta, at=now(), scientific_verdict=None))
def rows(S, prior, scope='전체'): return S[(S['prior'] == prior) & (S['surface'] == PSURF[prior]) & (S['scope'] == scope)].set_index('variant')
def bars(ax, q, items, xs):
    w = .8/len(items)
    for i, (v, lab, col) in enumerate(items):
        if v not in q.index: continue
        y = [q.loc[v, f'ok_{c}'] for c in xs]
        ax.bar(np.arange(len(xs)) + (i - (len(items) - 1)/2)*w, y, w*.95, color=col, ec='k' if v == '패치 다수결 상한' else 'none', lw=.6, label=lab, hatch='//' if v == '패치 다수결 상한' else None)
    ax.set_xticks(range(len(xs))); ax.set_xticklabels(xs); ax.set_ylim(0, 100); ax.set_ylabel('목표 맞음 %'); ax.grid(axis='y', lw=.3, alpha=.5)
def fig1(S, fus_all):
    for prior in ['LoD2', 'ALS']:
        q = rows(S, prior); q3 = rows(S, prior, '세 실험 지역 결합 범위'); xs = CN + ['전체']
        items = [('사전 정보 단독', '사전 정보 단독', VCOL['사전 정보 단독']), ('영상 단독', '영상 단독', VCOL['영상 단독'])] + OLD
        if fus_all: items.append(('기존 4 결합(전 건물)', '기존 4', '#5dade2'))
        items += [('본 방법', '본 방법', VCOL['본 방법']), ('패치 다수결 상한', '상한', 'white')]
        fig, axs = plt.subplots(1, 2, figsize=(11, 3.2), gridspec_kw=dict(width_ratios=[2.6, 1.2]))
        bars(axs[0], q.rename(columns={'ok_전체': 'ok_전체'}), items, xs); axs[0].set_title(f'{PNAME[prior]}: 전 건물', fontsize=8); axs[0].legend(fontsize=5.5, ncol=6, loc='upper center', bbox_to_anchor=(.5, -.1), framealpha=.9)
        it3 = [('사전 정보 단독', '사전 정보 단독', VCOL['사전 정보 단독']), ('영상 단독', '영상 단독', VCOL['영상 단독']), ('기존 4 결합(세 실험 지역)', '기존 4', '#5dade2'), ('본 방법', '본 방법', VCOL['본 방법']), ('패치 다수결 상한', '상한', 'white')]
        bars(axs[1], q3, it3, xs); axs[1].set_title('세 실험 지역만 (기존 4가 있는 참값 점)', fontsize=8); axs[1].legend(fontsize=5.5, ncol=3, loc='upper center', bbox_to_anchor=(.5, -.18), framealpha=.9); axs[1].tick_params(axis='x', labelsize=5.5, labelrotation=20)
        b = q.loc['본 방법']; fig.suptitle(f'{PNAME[prior]}: 기존 방법과 본 방법의 경우별 목표 맞음', fontsize=9)
        fig.text(.01, -.16, '본 방법 ' + ' / '.join(f'{b[f"ok_{c}"]:.1f}' for c in CN) + f' %, 전체 {b["ok_전체"]:.1f} %' + ('' if fus_all else '. 기존 4는 묶음 가에서 세 실험 지역 값만'), fontsize=6.5)
        meta = dict(figure=1, prior=prior, surface=PSURF[prior], items=[i[0] for i in items], values={v: {c: float(q.loc[v, f'ok_{c}']) for c in xs} for v, _, _ in items if v in q.index},
                    three_region={v: {c: float(q3.loc[v, f'ok_{c}']) for c in xs} for v, _, _ in it3 if v in q3.index}, n={c: int(b[f'n_{c}']) for c in CN}, source='tables/s_all_variants.csv')
        save(fig, f'fig1_old_vs_method_{prior}', meta)
def fig2(S):
    groups = [('검출', '검출'), ('식별', '식별'), ('유보', '유보'), ('처리', '처리'), ('가시성', '가시성')] + ([('고정', '고정 값')] if (S['family'] == 'fix').any() else [])
    for prior in ['LoD2', 'ALS']:
        q = rows(S, prior); b = q.loc['본 방법']
        vs = {g: sorted([v for v in q.index if v.startswith(g + ' ')], key=lambda v: (int(v.split(' ')[1]) if v.split(' ')[1].isdigit() else 0, v)) for g, _ in groups}
        fig, axs = plt.subplots(1, len(groups), figsize=(13 + 4*(len(groups) > 5), 3.6), sharey=True, gridspec_kw=dict(width_ratios=[max(len(vs[g]), 1) + .6 for g, _ in groups]))
        meta = dict(figure=2, prior=prior, surface=PSURF[prior], base={c: float(b[f'ok_{c}']) for c in CN}, values={})
        for ax, (g, lab) in zip(axs, groups):
            for c in CN: ax.axhline(b[f'ok_{c}'], color=CCOL[c], lw=.8, ls='--', alpha=.8)
            for i, v in enumerate(vs[g]):
                for j, c in enumerate(CN):
                    ax.plot(i + (j - 1.5)*.08, q.loc[v, f'ok_{c}'], 'o', ms=4, color=CCOL[c], mec='k', mew=.3)
                meta['values'][v] = {c: float(q.loc[v, f'ok_{c}']) for c in CN}
            ax.set_xticks(range(len(vs[g]))); ax.set_xticklabels([v.split(' ', 2)[1] if len(v.split(' ')) > 1 else v for v in vs[g]], fontsize=6)
            ax.set_xlim(-.6, len(vs[g]) - .4); ax.set_title(lab, fontsize=8); ax.grid(axis='y', lw=.3, alpha=.5)
        axs[0].set_ylabel('목표 맞음 %'); axs[0].set_ylim(0, 100)
        for c in CN: axs[-1].plot([], [], 'o', color=CCOL[c], label=c)
        axs[-1].plot([], [], 'k--', lw=.8, label='본값(점선)'); axs[-1].legend(fontsize=5.5, loc='lower right')
        fig.suptitle(f'{PNAME[prior]}: 판단 요소를 하나씩 바꾼 판의 경우별 목표 맞음 (점선 = 본값)', fontsize=9)
        fig.text(.01, -.06, '판 번호: ' + ', '.join(f'{g} {v.split(" ", 2)[1]} = {v.split(" ", 2)[2] if len(v.split(" ")) > 2 else ""}' for g, _ in groups for v in vs[g]), fontsize=5, wrap=True)
        save(fig, f'fig2_ablation_{prior}', meta)
def fig5(S, fus_all):
    fams = [('old1', '기존 1 (T)', '#8a8a8a'), ('old2', '기존 2 (배수)', '#9b59b6'), ('old3', '기존 3 (분위)', '#e3b505')]
    pts = [('사전 정보 단독', VCOL['사전 정보 단독'], 's'), ('영상 단독', VCOL['영상 단독'], 's'), ('기존 5 T=0.5 m', '#d98880', 'D'), ('기존 5 T=L', '#a93226', 'D'), ('본 방법', VCOL['본 방법'], '*'), ('패치 다수결 상한', 'k', 'P')]
    for prior in ['LoD2', 'ALS']:
        q = rows(S, prior); q3 = rows(S, prior, '세 실험 지역 결합 범위')
        fig, axs = plt.subplots(1, 2, figsize=(9, 4)); meta = dict(figure=5, prior=prior, surface=PSURF[prior], lines={}, points={})
        for ax, yc in zip(axs, ['영상 깊이 오류', '두 자료 모두 유효']):
            for fam, lab, col in fams:
                f = q[(q['family'] == fam) & ~q['gt_selected'].astype(bool)]
                f = f.assign(val=[float(v.split('=')[-1].split(' ')[0]) if fam == 'old1' else float(v.split(' ')[-1]) if fam == 'old2' else float(v.split(' ')[-2]) for v in f.index]).sort_values('val')
                ax.plot(f['ok_사전정보 오류'], f[f'ok_{yc}'], '-o', ms=2.5, lw=1, color=col, label=lab)
                for v, r in f.iterrows(): ax.annotate(f"{r['val']:g}", (r['ok_사전정보 오류'], r[f'ok_{yc}']), fontsize=4.5, xytext=(2, 2), textcoords='offset points', color=col)
                meta['lines'][fam] = {v: [float(r['ok_사전정보 오류']), float(r['ok_영상 깊이 오류']), float(r['ok_두 자료 모두 유효'])] for v, r in f.iterrows()}
            for v, col, mk in pts + ([('기존 4 결합(전 건물)', '#5dade2', 'X')] if fus_all else []):
                if v in q.index:
                    ax.plot(q.loc[v, 'ok_사전정보 오류'], q.loc[v, f'ok_{yc}'], mk, ms=8 if mk == '*' else 5.5, color=col, mec='k', mew=.4, label=SHORT.get(v, v.replace('기존 5 T=', '기존 5 ')))
                    meta['points'][v] = [float(q.loc[v, 'ok_사전정보 오류']), float(q.loc[v, 'ok_영상 깊이 오류']), float(q.loc[v, 'ok_두 자료 모두 유효'])]
            v = '기존 4 결합(세 실험 지역)'
            if v in q3.index:
                ax.plot(q3.loc[v, 'ok_사전정보 오류'], q3.loc[v, f'ok_{yc}'], 'X', ms=6, mfc='none', mec='#2471a3', mew=1, label='기존 4 (세 실험 지역만)')
                meta['points'][v + ' (세 실험 지역 범위)'] = [float(q3.loc[v, 'ok_사전정보 오류']), float(q3.loc[v, 'ok_영상 깊이 오류']), float(q3.loc[v, 'ok_두 자료 모두 유효'])]
            ax.set_xlabel('사전정보 오류의 목표 맞음 %'); ax.set_ylabel(f'{yc}의 목표 맞음 %'); ax.set_xlim(-2, 102); ax.set_ylim(-2, 102); ax.grid(lw=.3, alpha=.5)
        axs[0].legend(fontsize=5.5, loc='lower left', framealpha=.9)
        b = q.loc['본 방법']; fig.suptitle(f'{PNAME[prior]}: 사전정보 오류를 맞히는 만큼 다른 경우가 얼마나 틀리는가', fontsize=9)
        fig.text(.01, -.03, f"본 방법 사전정보 오류 {b['ok_사전정보 오류']:.1f}, 영상 깊이 오류 {b['ok_영상 깊이 오류']:.1f}, 두 자료 모두 유효 {b['ok_두 자료 모두 유효']:.1f} %. 선 위 숫자 = 문턱 T(m)·배수·분위(%)", fontsize=6.5)
        save(fig, f'fig5_tradeoff_{prior}', meta)
def main():
    S = pd.read_csv(TAB/'s_all_variants.csv'); fus_all = (S['variant'] == '기존 4 결합(전 건물)').any()
    fig1(S, fus_all); fig2(S); fig5(S, fus_all); progress('그림 1·2·5 끝')
if __name__ == '__main__': main()
