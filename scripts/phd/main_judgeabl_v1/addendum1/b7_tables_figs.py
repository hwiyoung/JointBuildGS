"""덧붙임 1: 표본 표(확인 5의 2, 6, 7, 8), 그림 A1·A2, 보고서 앞 표 둘. 사용: b7_tables_figs.py"""
import sys; sys.path.insert(0, '/repo/scripts/phd/main_judgeabl_v1'); sys.path.insert(0, '/repo/scripts/phd/main_judgeabl_v1/addendum1')
from common import *
import pandas as pd
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
from matplotlib import font_manager
import b1_checks as B1
FONT = '/fonts/NotoSansCJK-Regular.ttc'; font_manager.fontManager.addfont(FONT); plt.rcParams.update({'font.family': font_manager.FontProperties(fname=FONT).get_name(), 'axes.unicode_minus': False, 'font.size': 7})
TAB = D/'tables/addendum1'; FIG = D/'figures/addendum1'; A1 = O/'addendum1'; CN = [CASE[c] for c in CASES]
write = B1.write
def wq_(x, w, q):
    m = np.isfinite(x) & np.isfinite(w) & (w > 0); return J.quantile(np.asarray(x, float)[m], np.asarray(w, float)[m], q) if m.any() else np.nan
def nmad(x): x = np.asarray(x, float); x = x[np.isfinite(x)]; return 1.4826*np.median(np.abs(x - np.median(x))) if len(x) else np.nan
def save(fig, name, meta): FIG.mkdir(parents=True, exist_ok=True); fig.savefig(FIG/f'{name}.png', dpi=300, facecolor='white', bbox_inches='tight'); plt.close(fig); dump(FIG/f'{name}.json', dict(meta, at=now(), scientific_verdict=None))
def main():
    T = Timer(); SP = pd.concat([pd.read_csv(A1/f'sample_points_{p}.csv') for p in ['LoD2', 'ALS'] if (A1/f'sample_points_{p}.csv').exists()], ignore_index=True)
    PR = pd.concat([pd.read_csv(A1/f'sample_pairs_{p}.csv') for p in ['LoD2', 'ALS'] if (A1/f'sample_pairs_{p}.csv').exists()], ignore_index=True)
    VW = pd.concat([pd.read_csv(A1/f'sample_views_{p}.csv') for p in ['LoD2', 'ALS'] if (A1/f'sample_views_{p}.csv').exists()], ignore_index=True)
    c5 = pd.read_csv(TAB/'check5_texture.csv'); R52, R6, R7, R8 = [], [], [], []
    write('check9_photo_codes', pd.concat([pd.read_csv(O/f'check9_photo_codes_{p}.csv') for p in ['LoD2', 'ALS']]), '확인 9: 광도 결과를 쓰는 패치(한계 밖, u_M 없음)의 참값 점에서 경우마다 광도 결과 여덟의 비율 %.')
    write('check9_t', pd.concat([pd.read_csv(O/f'check9_t_{p}.csv') for p in ['LoD2', 'ALS']]), '확인 9: 판마다 쓴 기준 t (탐색 지역 x 사전 정보 x 지붕·벽).')
    # 5의 2
    for (u, reg), q in list(SP.groupby(['unit', 'region'])) + [((u, '전체'), q) for u, q in SP.groupby('unit')]:
        sn = q['sigma_n'].median(); t = q['t'].median(); thr2 = sn*np.sqrt(t/(1 - t)) if np.isfinite(t) and 0 < t < 1 else np.nan
        r1 = c5[(c5.unit == u) & (c5.region == reg)]
        R52.append(dict(unit=u, region=reg, sample_points=len(q), sigma_n_q10=q['sigma_n'].quantile(.1), sigma_n_q50=sn, sigma_n_q90=q['sigma_n'].quantile(.9), t=t, rule2_threshold=thr2 if np.isfinite(thr2) else np.nan,
                        rule2_note='' if np.isfinite(thr2) else '구할 수 없음(t ≤ 0)', rule1_threshold=float(r1['rule1_threshold'].iloc[0]) if len(r1) else np.nan, threshold_now=5,
                        textureless_area_pct_now=float(r1['textureless_area_pct_now'].iloc[0]) if len(r1) else np.nan,
                        corr_s_full_vs_stored=q[['s_P_full', 's_P_stored']].corr().iloc[0, 1], corr_texture_full_vs_stored=q[['texture_full', 'texture_stored']].corr().iloc[0, 1]))
    write('check5_texture_rules', pd.DataFrame(R52), '확인 5: 규칙 1(저장 값, s_P < t 비율이 10 % 아래로) 문턱, 규칙 2(표본, σ_n √(t/(1−t))) 문턱, 지금 5. σ_n = 사진 쌍마다 일차식 맞춘 뒤 남은 차이 표준 편차 ÷ √2 의 중앙값(회색 0~255). 표본은 조각 전체(마스크 없음)로 다시 셈; 저장 값과의 상관 함께.')
    # 6
    bins = [0, 20, 30, 40, 50, 60, 70, 80]
    for (u, rg), q in [((u, '전체'), q) for u, q in PR.groupby('unit')] + list(PR.groupby(['unit', 'region'])):
        v = VW[VW.unit == u] if rg == '전체' else VW.iloc[:0]; base = q[q.max_angle < 40]['ncc'].median(); first = None
        for a, b in zip(bins[:-1], bins[1:]):
            m = q[(q.max_angle >= a) & (q.max_angle < b)]; vv = v[(v.angle >= a) & (v.angle < b)]
            med = m['ncc'].median() if len(m) else np.nan
            if first is None and a >= 40 and np.isfinite(med) and med < base - .1: first = f'{a}~{b}'
            R6.append(dict(unit=u, region=rg, angle_bin=f'{a}~{b}°', pairs=len(m), ncc_q10=m['ncc'].quantile(.1) if len(m) else np.nan, ncc_q50=med, ncc_q90=m['ncc'].quantile(.9) if len(m) else np.nan,
                           below_t_pct=100*m['below_t'].mean() if len(m) else np.nan, footprint_q50_m=vv['footprint_m'].median() if len(vv) else np.nan, footprint_over_2cm=vv['footprint_m'].median()/.02 if len(vv) else np.nan))
        R6.append(dict(unit=u, region=rg, angle_bin='0~40° 중앙값 − 0.1 아래 첫 구간', pairs=np.nan, ncc_q50=base, note=first or '없음'))
    write('check6_view_angle', pd.DataFrame(R6), '확인 6: 표본 사진 점, 80°까지 넓힌 사진(가림 = MVS 깊이 0.5 m)의 모든 쌍. 각 = 두 사진 가운데 큰 쪽. 화소 크기 = (거리 ÷ 초점) × 2^단계 ÷ cos 각.')
    # 7
    k10 = SP[SP.filter(like='s_k10').notna().any(axis=1)] if 's_k10' in SP else SP.iloc[:0]
    for (u, rg), q in [((u, '전체'), q) for u, q in k10.groupby('unit')] + list(k10.groupby(['unit', 'region'])):
        ref = nmad(q['s_k9'] - q['s_k10']); found = None
        for k in range(2, 11):
            dlt = q[f's_k{k}'] - q['s_k10']; nm = nmad(dlt)
            if found is None and k < 10 and np.isfinite(nm) and nm < 1.5*ref: found = k
            R7.append(dict(unit=u, region=rg, k=k, points=int(dlt.notna().sum()), diff_median=float(dlt.median()), diff_nmad=nm))
        R7.append(dict(unit=u, region=rg, k='편차 < 1.5 × (9와 10 사이) 인 가장 작은 k', points=len(q), diff_nmad=ref, note=found))
    for prior in ['LoD2', 'ALS']:
        Ph = loadz(JP/f'photo_{prior}.npz', ['kind', 'area', 'all_within', 'n_selected'])
        for kind in ([1, 2] if prior == 'LoD2' else [1]):
            m = (Ph['kind'] == kind) & Ph['all_within']; ns = Ph['n_selected'][:, 0]
            for k in range(0, 11): R7.append(dict(region='전체', unit=f"{'LoD2' if prior == 'LoD2' else '항공 LiDAR'} {'지붕' if kind == 1 else '벽'}", k=f'본값 사진 수 {k}장', area_pct=100*Ph['area'][m & (ns == k)].sum()/Ph['area'][m].sum()))
    write('check7_view_count', pd.DataFrame(R7), '확인 7: 고른 사진 10장인 표본 점에서 저장 차례(첫 장 = 가장 정면, 다음은 방향이 가장 다른 것)로 앞 k장만 쓴 s_P(k) − s_P(10). 본값 사진 수별 넓이 비율(한계 안 사진 점).')
    # 8
    for (u, rg), q in [((u, '전체'), q) for u, q in SP.groupby('unit')] + list(SP.groupby(['unit', 'region'])):
        cl = q['corr_len_m']; R8.append(dict(unit=u, region=rg, item='무늬 닮는 거리(1/e, m)', q10=cl.quantile(.1), q50=cl.median(), q90=cl.quantile(.9), note=f'조각 안 독립 표본 수 ≈ {(0.5/cl.median())**2:.0f}' if cl.median() > 0 else ''))
        fp = q['footprint_m']; R8.append(dict(unit=u, region=rg, item='화소 크기(면 위, m)', q10=fp.quantile(.1), q50=fp.median(), q90=fp.quantile(.9), note=f'÷ 2 cm 중앙값 {fp.median()/.02:.2f}'))
        for k in [15, 20]:
            dd = q[f's_P_{k}'] - q['s_P_full']; R8.append(dict(unit=u, region=rg, item=f'조각 {k}x{k} − 25x25 s_P 차이', q10=dd.quantile(.1), q50=dd.median(), q90=dd.quantile(.9), note=f'NMAD {nmad(dd):.4f}'))
    VS = pd.read_csv(TAB/'variogram_summary.csv')
    for prior, kind, lab in B1.UNITS3:
        d = B1.load(prior); inl = (d['geometry'] == 0) & (d['kind'] == kind) & np.isfinite(d['m_ninner']); L50 = VS[(VS.unit == lab) & (VS.region == '전체')]['L50'].iloc[0]
        x = d['m_ninner']; ne = np.minimum(x, np.pi*.25/L50**2)
        R8.append(dict(unit=lab, region='전체', item='고리 안쪽 원 점 수 (한계 안)', q10=wq_(x, d['area']*inl, .1), q50=wq_(x, d['area']*inl, .5), q90=wq_(x, d['area']*inl, .9), note=f'유효 표본 수 = min(n, π 0.5² ÷ L50²), L50 {L50:.3f} m → {float(np.pi*.25/L50**2):.2f}'))
    write('check8_patch_inner', pd.DataFrame(R8), '확인 8: 표본 사진 점의 조각(25 x 25, 2 cm)과 고리 안쪽 원.')
    # ---- 그림 A1
    VG = pd.read_csv(TAB/'variogram_bins.csv'); C1 = pd.read_csv(TAB/'check1_conditions.csv'); BD = np.load(A1/'boundary_dist.npz')
    fig, axs = plt.subplots(1, 3, figsize=(12, 3.4))
    for lab, col in zip(['LoD2 지붕', 'LoD2 벽', '항공 LiDAR 지붕'], ['#1f77b4', '#ff7f0e', '#2ca02c']):
        q = VG[(VG.unit == lab) & (VG.region == '전체')]; s = VS[(VS.unit == lab) & (VS.region == '전체')].iloc[0]
        axs[0].plot(q.bin_mid, q.semivariance/s.plateau, '-o', ms=2, color=col, label=f'{lab} (L50 {s.L50:.2f}, L95 {s.L95:.2f} m)')
    for R, ls in [(1.0, ':'), (1.5, '--'), (3.0, '-.')]: axs[0].axvline((.5 + R)/2, color='k', ls=ls, lw=.8, label=f'고리 가운데 반지름 (R {R:g})')
    axs[0].axhline(.95, color='grey', lw=.5); axs[0].axhline(.5, color='grey', lw=.5); axs[0].set_xlabel('패치 사이 거리 (m)'); axs[0].set_ylabel('반변동도 ÷ 고원'); axs[0].legend(fontsize=5); axs[0].set_title('(가) (d − r) 이 닮는 거리', fontsize=8)
    for prior, kind, lab, col in [('LoD2', 1, 'LoD2 지붕', '#1f77b4'), ('LoD2', 2, 'LoD2 벽', '#ff7f0e'), ('ALS', 1, '항공 LiDAR 지붕', '#2ca02c')]:
        r = C1[(C1.unit == lab) & (C1.region == '전체') & (C1.R == 1.5) & (C1.ring.str.startswith('영상'))].iloc[0]
        axs[1].plot([r.sigma_over_u_q10, r.sigma_over_u_q90], [lab]*2, color=col, lw=3, alpha=.4); axs[1].plot(r.sigma_over_u_q50, lab, 'o', color=col)
        axs[1].plot([r.sigma_eff_over_u_q10, r.sigma_eff_over_u_q90], [lab + ' (N_유효)']*2, color=col, lw=3, alpha=.4); axs[1].plot(r.sigma_eff_over_u_q50, lab + ' (N_유효)', 's', color=col)
    axs[1].axvline(1/3, color='k', ls='--', lw=.8); axs[1].set_xscale('log'); axs[1].set_xlabel('σ_면 ÷ u_M (R 1.5, 10–50–90 %)'); axs[1].set_title('(나) 고리 평면의 흔들림 (점선 = 1/3)', fontsize=8)
    for prior, kind, lab, col in [('LoD2', 1, 'LoD2 지붕', '#1f77b4'), ('LoD2', 2, 'LoD2 벽', '#ff7f0e'), ('ALS', 1, '항공 LiDAR 지붕', '#2ca02c')]:
        d = loadz(JP/f'patch_{prior}.npz', ['kind', 'geometry', 'area']); x = BD[prior]; m = (d['kind'] == kind) & (d['geometry'] == 0) & np.isfinite(x)
        o = np.argsort(x[m]); cw = np.cumsum(d['area'][m][o]); axs[2].plot(x[m][o], cw/cw[-1], color=col, label=lab)
    axs[2].axvline(1.5, color='k', ls='--', lw=.8); axs[2].set_xlim(0, 8); axs[2].set_xlabel('면 경계까지 거리 (m)'); axs[2].set_ylabel('넓이 누적 비율'); axs[2].legend(fontsize=6); axs[2].set_title('(다) 한 면의 크기 (점선 = 1.5 m)', fontsize=8)
    fig.suptitle('그림 A1: 고리 바깥 반지름의 세 조건 (한계 안 패치, 전체)', fontsize=9); fig.tight_layout(); save(fig, 'figA1_ring_radius', dict(source='tables/addendum1/variogram_*.csv, check1_conditions.csv, check1_boundary.csv'))
    # ---- 그림 A2
    fig, axs = plt.subplots(1, 3, figsize=(12, 3.4)); R52d = pd.DataFrame(R52)
    for ax, lab in zip(axs, ['LoD2 지붕', 'LoD2 벽', '항공 LiDAR 지붕']):
        q = c5[(c5.unit == lab) & (c5.region == '전체')]; x = np.arange(len(q))
        ax.vlines(x, q['s_P_q10'], q['s_P_q90'], color='#9ecae1', lw=4); ax.plot(x, q['s_P_q50'], 'o', color='#1f4e9c', ms=3)
        ax.set_xticks(x); ax.set_xticklabels(q['texture_bin'], rotation=60, fontsize=5); ax.set_xlabel('무늬 세기 구간'); ax.set_ylabel('s_P (10–50–90 %)')
        ax2 = ax.twinx(); ax2.plot(x, q['below_t_pct'], 'r-', lw=.8); ax2.axhline(10, color='r', ls=':', lw=.6); ax2.set_ylabel('s_P < t 비율 %', color='r')
        lo = list(q['lo']); k5 = lo.index(5) if 5 in lo else None
        if k5 is not None: ax.axvline(k5 - .5, color='k', ls='--', lw=.8)
        r = R52d[(R52d.unit == lab) & (R52d.region == '전체')]
        ttl = f"{lab}: 규칙 1 {q['rule1_threshold'].iloc[0]:g}, 규칙 2 {r['rule2_threshold'].iloc[0]:.2f}" if len(r) else lab
        xs = np.r_[np.array(lo, float), 25.]
        for val, col_, nm_ in [(q['rule1_threshold'].iloc[0], '#d62728', '규칙 1'), (r['rule2_threshold'].iloc[0] if len(r) else np.nan, '#2ca02c', '규칙 2')]:
            if np.isfinite(val): ax.axvline(np.interp(val, xs, np.arange(len(xs))) - .5, color=col_, ls='-.', lw=1, label=nm_)
        ax.legend(fontsize=5, loc='lower right')
        ax.set_title(ttl + ', 지금 5(검은 점선)', fontsize=7)
    fig.suptitle('그림 A2: 무늬 세기에 따른 s_P 분포와 s_P < t 비율 (한계 안 사진 점)', fontsize=9); fig.tight_layout(); save(fig, 'figA2_texture', dict(source='tables/addendum1/check5_texture.csv, check5_texture_rules.csv'))
    # ---- 그림 A2b: 표본의 (무늬 세기, s_P)와 기댓값 곡선 E = T^2 / (T^2 + σ_n^2)
    fig, axs = plt.subplots(1, 3, figsize=(12, 3.4)); meta = {}
    for ax, lab in zip(axs, ['LoD2 지붕', 'LoD2 벽', '항공 LiDAR 지붕']):
        q = SP[(SP.unit == lab) & SP.texture_full.notna() & SP.s_P_full.notna()]; sn = q['sigma_n'].median(); t = q['t'].median()
        ax.scatter(q.texture_full, q.s_P_full, s=1, alpha=.3, color='#1f77b4', lw=0, label='표본 사진 점'); tx = np.linspace(0, 40, 200); ax.plot(tx, tx**2/(tx**2 + sn**2), 'k-', lw=1, label=f'기댓값 (σ_n {sn:.1f})')
        ax.axhline(t, color='r', ls=':', lw=.8, label=f't 중앙값 {t:.2f}'); ax.axvline(5, color='k', ls='--', lw=.8, label='지금 문턱 5')
        if 0 < t < 1: ax.axvline(sn*np.sqrt(t/(1 - t)), color='#2ca02c', ls='-.', lw=1, label='규칙 2')
        ax.set_xlim(0, 40); ax.set_ylim(-.5, 1); ax.set_xlabel('무늬 세기 (조각 전체, 회색 단위)'); ax.set_ylabel('s_P (조각 전체)'); ax.set_title(lab, fontsize=8); ax.legend(fontsize=5, loc='lower right')
        meta[lab] = dict(points=len(q), sigma_n_median=sn, t_median=t)
    fig.suptitle('그림 A2b: 무늬 세기와 s_P (표본), 사진 잡음에서 나온 기댓값 곡선', fontsize=9); fig.tight_layout(); save(fig, 'figA2b_texture_noise', dict(source='addendum1/sample_points_*.csv', units=meta))
    # ---- 보고서 앞 표 (값을 바꾼 판정)
    S = pd.read_csv(D/'tables/s_all_variants.csv'); S = S[(S.scope == '전체') & (((S.prior == 'LoD2') & (S.surface == '모두')) | (S.prior == 'ALS'))]
    rows = []
    for v in ['본 방법'] + sorted([x for x in S.variant.unique() if x.startswith('고정 ')], key=lambda x: int(x.split(' ')[1])):
        r = dict(variant=v)
        for p in ['LoD2', 'ALS']:
            q = S[(S.prior == p) & (S.variant == v)].iloc[0]; r[f'{p} 네 경우'] = ' / '.join(f"{q[f'ok_{c}']:.1f}" for c in CN); r[f'{p} 차이 %p'] = ' / '.join(f"{q[f'diff_pp_{c}']:+.1f}" for c in CN)
        rows.append(r)
    write('front_fixed_value_variants', pd.DataFrame(rows), '값을 바꾼 판정: 네 경우(두 자료 모두 유효 / 사전정보 오류 / 영상 깊이 오류 / 영상 깊이 결측)의 목표 맞음 %와 본값과의 차이. LoD2 = 지붕과 벽 합침.')
    progress(f'덧붙임 1 표·그림 끝 ({round(T.s())} 초)')
if __name__ == '__main__': main()
