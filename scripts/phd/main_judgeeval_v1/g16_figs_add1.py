"""덧붙임 1 그림(표 tables/다 와 judge4_<prior>.npz 에서만, 참값 점은 5절 단면 그림에만).
fig_d1_matrix4: 판 4 의 4 x 4 행렬 두 장(왼쪽 줄 안 %, 오른쪽 목표 맞음 줄 안 %), 대각선 굵은 테두리, LoD2 지붕·벽, 항공 LiDAR 지붕(전체, 넓이).
fig_d3_trace_<prior>: 경우마다 작은 선 그림(가로 단계 ①만·② 더함·③ 더함, 실선 판단, 점선 목표), 지붕·벽 색.
fig_d5_scatter: |h_I| 대 L(점 = 패치, 대각선 |h_I| = L, 목표 맞음 색), fig_d5_sections: (가)·(나) 본보기 단면 하나씩.
사용: GT_STAGE=ga3 g16_figs_add1.py"""
from common import *
import pandas as pd
from target_check import J4
from g11_figs import save, load, section_pts
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from matplotlib.lines import Line2D
TD = D/'tables/다'; UNITS = [('LoD2', '지붕'), ('LoD2', '벽'), ('항공 LiDAR', '지붕')]; SC = {'지붕': '#378ADD', '벽': '#D85A30'}
def fig1(plan='판 4'):
    mx = pd.read_csv(TD/'t1_matrix4.csv'); mx = mx[(mx.plan == plan) & (mx.version == '전체') & (mx.unit == '넓이') & mx.in_matrix]
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
    fig.suptitle(f'{plan} 4 × 4 오류 행렬(줄 = 정답, 칸 = 판정, 같은 이름·차례, 넓이, 전체). 줄 끝 합에는 그 밖 칸 포함', fontsize=8); fig.tight_layout(); save(fig, 'fig_d1_matrix4', dict(plan=plan, values=meta))
def fig3():
    tr = pd.read_csv(TD/'t3_trace.csv'); tr = tr[(tr.version == '전체') & (tr.unit == '넓이')]; X = ['①만 (판 1)', '② 더함 (판 2)', '③ 더함 (판 4)']
    for p in ['LoD2', '항공 LiDAR']:
        fig, axs = plt.subplots(1, 5, figsize=(14, 3.2), sharey=True); meta = {}
        for ax, cn in zip(axs, J4 + ['전체(채점한 넓이)']):
            for s in (['지붕', '벽'] if p == 'LoD2' else ['지붕']):
                g = tr[(tr.prior == p) & (tr.surface == s) & (tr.case == cn)].set_index('accuracy')
                if not len(g): continue
                for acc, ls in [('판단', '-'), ('목표', '--')]:
                    y = g.loc[acc, X].to_numpy(float); ax.plot(range(3), y, ls=ls, marker='o', ms=3, color=SC[s], lw=1.2); meta[f'{s} {cn} {acc}'] = y.tolist()
                    for xi, yi in enumerate(y): ax.text(xi, yi + 1.5, f'{yi:.0f}', fontsize=5, ha='center', color=SC[s])
                tot = g.case_total.iloc[0]; ax.text(.02, .02 + (.07 if s == '벽' else 0), f'{s} {tot:,.0f} m²', transform=ax.transAxes, fontsize=5.5, color=SC[s])
            ax.set_xticks(range(3)); ax.set_xticklabels(['①만', '② 더함', '③ 더함'], fontsize=6); ax.set_ylim(0, 105); ax.set_title(cn, fontsize=7); ax.grid(axis='y', lw=.3)
        axs[0].set_ylabel('정확도 % (넓이)'); h = [Line2D([], [], color='k', ls='-', label='판단 정확도'), Line2D([], [], color='k', ls='--', label='목표 정확도')] + [Line2D([], [], color=SC[s], label=s) for s in (['지붕', '벽'] if p == 'LoD2' else ['지붕'])]
        fig.legend(handles=h, loc='lower center', ncol=4, frameon=False, bbox_to_anchor=(.5, -.06), fontsize=6.5); fig.suptitle(f'{p} 경우별 추적: 단계를 더할 때 경우마다 판단 정확도(실선)와 목표 정확도(점선)', fontsize=8)
        save(fig, f"fig_d3_trace_{'LoD2' if p == 'LoD2' else 'ALS'}", dict(values=meta))
def fig5():
    fig, axs = plt.subplots(1, 3, figsize=(12, 3.8)); meta = {}; picks = {}
    for ax, (p, s) in zip(axs, UNITS):
        pr = 'LoD2' if p == 'LoD2' else 'ALS'; F = loadz(O/'work'/STAGE/f'judge4_{pr}.npz'); Z = loadz(O/'work'/STAGE/f'truth_{pr}.npz', ['h_I']); S1 = loadz(O/'work'/STAGE/f'step1_{pr}.npz', ['L_m', 'd_mean'])
        kind = loadz(inp('patches', prior=pr), ['kind'])['kind'][F['patch_index']]; m = (F['answer'] == 2) & (F['J4_판 4'] == 0) & (kind == (1 if s == '지붕' else 2))
        a = np.abs(Z['h_I'][:, 0]); L = S1['L_m']; ok = F['ok_판 4']
        ax.scatter(a[m & ok], L[m & ok], s=3, color='#1D9E75', lw=0, label=f'목표 맞음 {int((m & ok).sum())}'); ax.scatter(a[m & ~ok], L[m & ~ok], s=3, color='#A32D2D', lw=0, label=f'목표 틀림 {int((m & ~ok).sum())}')
        mm = max(np.nanmax(a[m]) if m.any() else 1, np.nanmax(L[m]) if m.any() else 1); ax.plot([0, mm], [0, mm], color='k', lw=.6); ax.set_xlabel('|h_I| (정답의 영상 자리, m)'); ax.set_ylabel('① 한계 L (m)')
        ax.set_title(f'{p} {s} · 패치 {int(m.sum())} · 대각선 위 = (가) |h_I| ≤ L', fontsize=7); ax.legend(fontsize=6); meta[f'{p} {s}'] = dict(patches=int(m.sum()), ga=int((m & (a <= L)).sum()), na=int((m & (a > L)).sum()))
        if pr == 'LoD2' and s == '지붕':
            rng = np.random.default_rng(A1seed()); g1 = np.flatnonzero(m & (a <= L) & (a > .3)); g2 = np.flatnonzero(m & (a > L))
            picks = {'(가) |h_I| ≤ L': g1[rng.integers(len(g1))] if len(g1) else None, '(나) |h_I| > L': g2[rng.integers(len(g2))] if len(g2) else None}
    fig.tight_layout(); save(fig, 'fig_d5_scatter', dict(values=meta))
    L_ = load('LoD2'); F = loadz(O/'work'/STAGE/'judge4_LoD2.npz'); S1 = loadz(O/'work'/STAGE/'step1_LoD2.npz', ['L_m', 'd_mean', 'Hs']); Z = loadz(O/'work'/STAGE/'truth_LoD2.npz', ['h_I', 'tau_P', 'tau_I'])
    fig, axs = plt.subplots(1, 2, figsize=(8.5, 5)); meta = []
    for ax, (nm, k) in zip(axs, picks.items()):
        if k is None: ax.axis('off'); continue
        ref, n, u, v, P = section_pts(L_, k, 1.5, 10.); a, t, _, _ = P['mvs']; ax.scatter(a, t, s=1, color='#97C459', lw=0, label='영상 깊이 점'); a, t, _, _ = P['gt']; ax.scatter(a, t, s=1.4, color='k', lw=0, label='드론 LiDAR')
        hI = Z['h_I'][k, 0]; tp = Z['tau_P'][k, 0]; ti = Z['tau_I'][k, 0]; dk = S1['d_mean'][k, 2]; Lk = S1['L_m'][k]; hT = F['hT_판 4'][k]; tT = F['tauT_판 4'][k]
        ax.axhspan(-tp, tp, color='#AFA9EC', alpha=.4, label='0 ± τ_P'); ax.axhspan(hI - ti, hI + ti, color='#97C459', alpha=.35, label='h_I ± τ_I (정답 영상 자리)')
        ax.axhspan(dk - Lk, dk + Lk, xmin=.0, xmax=.08, color='#D85A30', alpha=.5, label='① d ± L (왼쪽 띠)'); ax.axhline(dk, color='#D85A30', lw=.8, ls=':', label=f'① d {dk:+.2f}')
        ax.axhline(hT, color='#185FA5', lw=1.2, label=f'목표 h_T {hT:+.2f} (± {tT:.2f})'); ax.axhline(0, color='#534AB7', lw=1); ax.axvline(-.125, color='#5F5E5A', lw=.4, ls='--'); ax.axvline(.125, color='#5F5E5A', lw=.4, ls='--')
        lo = min(0, hI, dk - Lk) - 1; hi = max(0, hI, dk + Lk) + 1; ax.set_ylim(lo, hi); ax.set_xlim(-1.5, 1.5); ax.set_xlabel('옆 거리 (m)'); ax.set_ylabel('법선 거리 (m, 사전 정보 = 0)')
        ax.set_title(f"{nm} · {L_['b'][k].replace('DEBY_LOD2_', '')} · |h_I| {abs(hI):.2f} · L {Lk:.2f} · 목표 {'맞음' if F['ok_판 4'][k] else '틀림'}", fontsize=7); ax.legend(fontsize=5, loc='upper right')
        meta.append(dict(case=nm, patch_index=int(L_['i'][k]), h_I=float(hI), d=float(dk), L=float(Lk), h_T=float(hT), target_ok=bool(F['ok_판 4'][k])))
    fig.suptitle('5절 본보기: 정답 사전 정보·영상 틀림인데 ①이 같다로 끝낸 패치(LoD2 지붕, 단면 옆 ±1.5 m, 두께 ±0.125 m)', fontsize=8); fig.tight_layout(); save(fig, 'fig_d5_sections', dict(examples=meta))
def A1seed(): return json.loads((C/'judgeeval_v1_add1.json').read_text())['step2_check']['seed']
def main(): fig1(); fig3(); fig5()
if __name__ == '__main__': main()
