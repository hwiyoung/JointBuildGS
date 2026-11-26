"""덧붙임 2 그림(표 tables/마 에서만): fig_d1_matrix4_v2, fig_d3_trace_LoD2_v2, fig_d3_trace_ALS_v2. 모양은 덧붙임 1(g16)과 같고, 추적 그림에 묶음 다 목표 선을 연하게 더함.
사용: GT_STAGE=ga3 g21_figs_add2.py"""
from common import *
import pandas as pd
from target_check import J4
from g11_figs import save
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from matplotlib.lines import Line2D
TD = D/'tables/마'; UNITS = [('LoD2', '지붕'), ('LoD2', '벽'), ('항공 LiDAR', '지붕')]; SC = {'지붕': '#378ADD', '벽': '#D85A30'}
def fig1(plan='판 4'):
    mx = pd.read_csv(TD/'t1_matrix4_v2.csv'); mx = mx[(mx.plan == plan) & (mx.version == '전체') & (mx.unit == '넓이') & mx.in_matrix]
    fig, axs = plt.subplots(len(UNITS), 2, figsize=(9.5, 3.3*len(UNITS))); meta = {}
    for r, (p, s) in enumerate(UNITS):
        g = mx[(mx.prior == p) & (mx.surface == s)].set_index('truth').reindex(J4)
        for cc, (suf, ttl) in enumerate([(' 줄 %', '줄 안 비율 % (대각선 = 판단 정확도)'), (' 목표 맞음 줄 %', '목표가 맞은 넓이의 줄 안 % (줄 합 = 목표 정확도)')]):
            A = g[[f'{j}{suf}' for j in J4]].to_numpy(float); ax = axs[r, cc]; ax.imshow(np.nan_to_num(A), cmap='Blues', vmin=0, vmax=100)
            for i in range(4):
                for j in range(4): ax.text(j, i, '' if not np.isfinite(A[i, j]) else f'{A[i, j]:.1f}', ha='center', va='center', fontsize=7, color='w' if np.nan_to_num(A[i, j]) > 60 else 'k')
                ax.add_patch(Rectangle((i - .5, i - .5), 1, 1, fill=False, ec='k', lw=2))
            other = g[f'그 밖{suf}'].to_numpy(float); rs = np.nansum(A, 1) + np.nan_to_num(other)
            ax.set_xticks(range(4)); ax.set_xticklabels([x.replace('사전 정보·', '사전 정보\n') for x in J4], fontsize=6); ax.set_yticks(range(4))
            ax.set_yticklabels([f"{x.replace('사전 정보·', '사전 정보 ')}\n{g.total.iloc[i]:,.0f} m² · 합 {rs[i]:.1f}" for i, x in enumerate(J4)], fontsize=6)
            ax.set_xlabel('판정', fontsize=6.5); ax.set_title(f'{p} {s} · {ttl}', fontsize=7); meta[f'{p} {s} {suf.strip()}'] = A.tolist()
    fig.suptitle(f'{plan} 4 × 4 오류 행렬 v2(목표 h_M = 저장 mvs_mean_m, 줄 = 정답, 칸 = 판정, 같은 이름·차례, 넓이, 전체). 줄 끝 합에는 그 밖 칸 포함', fontsize=8); fig.tight_layout(); save(fig, 'fig_d1_matrix4_v2', dict(plan=plan, values=meta))
def fig3():
    tr = pd.read_csv(TD/'t3_trace_v2.csv'); tr = tr[(tr.version == '전체') & (tr.unit == '넓이')]; tr1 = pd.read_csv(D/'tables/다/t3_trace.csv'); tr1 = tr1[(tr1.version == '전체') & (tr1.unit == '넓이')]; X = ['①만 (판 1)', '② 더함 (판 2)', '③ 더함 (판 4)']
    for p in ['LoD2', '항공 LiDAR']:
        fig, axs = plt.subplots(1, 5, figsize=(14, 3.2), sharey=True); meta = {}
        for ax, cn in zip(axs, J4 + ['전체(채점한 넓이)']):
            for s in (['지붕', '벽'] if p == 'LoD2' else ['지붕']):
                g = tr[(tr.prior == p) & (tr.surface == s) & (tr.case == cn)].set_index('accuracy')
                if not len(g): continue
                for acc, ls in [('판단', '-'), ('목표', '--')]:
                    y = g.loc[acc, X].to_numpy(float); ax.plot(range(3), y, ls=ls, marker='o', ms=3, color=SC[s], lw=1.2); meta[f'{s} {cn} {acc}'] = y.tolist()
                    for xi, yi in enumerate(y): ax.text(xi, yi + 1.5, f'{yi:.0f}', fontsize=5, ha='center', color=SC[s])
                    if acc == '목표':
                        g1 = tr1[(tr1.prior == p) & (tr1.surface == s) & (tr1.case == cn)].set_index('accuracy'); y1 = g1.loc['목표', X].to_numpy(float); ax.plot(range(3), y1, ls=':', color=SC[s], lw=.8, alpha=.45); meta[f'{s} {cn} 목표 v1'] = y1.tolist()
                tot = g.case_total.iloc[0]; ax.text(.02, .02 + (.07 if s == '벽' else 0), f'{s} {tot:,.0f} m²', transform=ax.transAxes, fontsize=5.5, color=SC[s])
            ax.set_xticks(range(3)); ax.set_xticklabels(['①만', '② 더함', '③ 더함'], fontsize=6); ax.set_ylim(0, 105); ax.set_title(cn, fontsize=7); ax.grid(axis='y', lw=.3)
        axs[0].set_ylabel('정확도 % (넓이)'); h = [Line2D([], [], color='k', ls='-', label='판단 정확도'), Line2D([], [], color='k', ls='--', label='목표 정확도 v2'), Line2D([], [], color='k', ls=':', alpha=.45, label='목표 정확도 묶음 다')] + [Line2D([], [], color=SC[s], label=s) for s in (['지붕', '벽'] if p == 'LoD2' else ['지붕'])]
        fig.legend(handles=h, loc='lower center', ncol=4, frameon=False, bbox_to_anchor=(.5, -.06), fontsize=6.5); fig.suptitle(f'{p} 경우별 추적 v2: 판단 정확도(실선), 목표 정확도 v2(점선, h_M = 저장 mvs_mean_m), 묶음 다 목표(연한 점선)', fontsize=8)
        save(fig, f"fig_d3_trace_{'LoD2' if p == 'LoD2' else 'ALS'}_v2", dict(values=meta))
def main(): fig1(); fig3()
if __name__ == '__main__': main()
