"""Figures of work ga / na (addendum 4): release events (tangent vs normal distance), movement before release, gradient sign shares, na group bars.
  python a4_fig_gana.py   -> docs addendum4/figures/ga_release_*.png, na_groups.png (+ json sources)"""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1/addendum4')
from a4_common import *
FIG = A4D/'figures'
RUNKO = {'sa1_R1_ALS_record6000': 'R1 × 항공 LiDAR (사-1, 6,000회)', 'tl_R1_ALS_own': 'R1 × 항공 LiDAR (기록 판, 30,000회)', 'tl_B0_LoD2_own': 'B0 × LoD2 (기록 판)', 'ba3_B0_ALS_record': 'B0 × 항공 LiDAR (별채 기록 판)'}

def save(fig, name, meta):
    FIG.mkdir(parents=True, exist_ok=True); fig.savefig(FIG/f'{name}.png', dpi=110); dump(FIG/f'{name}.json', dict(meta, at=now(), scientific_verdict=None))

def release_fig():
    plt = korean_plt()
    sets = [('tl_R1_ALS_own', 'floor_band'), ('tl_R1_ALS_own', 'floor_control'), ('tl_B0_LoD2_own', 'edge_back'), ('tl_B0_LoD2_own', 'edge_back_control'), ('ba3_B0_ALS_record', 'annex_right'), ('ba3_B0_ALS_record', 'annex_wrong')]
    fig, axes = plt.subplots(2, 3, figsize=(16, 9.5)); src = {}
    for ax, (run, pl) in zip(axes.ravel(), sets):
        z = loadz(A4O/'ga'/f'events_{run}.npz'); k = f'{pl}_release__'
        if k+'tangent_m' not in z: ax.set_axis_off(); continue
        t = z[k+'tangent_m']; h = z[k+'normal_m']; how = z[k+'how']; n = len(t)
        for code, col, lab in [(0, '#1f77b4', '본인(사전 정보 씨앗)'), (1, '#7f7f7f', '본인(배경 씨앗)'), (2, '#ff7f0e', '자식(복제)'), (3, '#d62728', '자식(분할)')]:
            m = how == code
            if m.any(): ax.scatter(t[m], h[m], s=8, c=col, alpha=.6, label=f'{lab} {int(m.sum())}')
        ax.axvline(.5, color='k', ls='--', lw=1); ax.text(.52, ax.get_ylim()[1] if n else 1, '접선 0.5 m\n(후보 조건)', va='top', fontsize=8)
        ax.set_xlabel('풀릴 때 원래 목표 중심에서 접선 거리 (m)'); ax.set_ylabel('원래 목표면에서 법선 거리 (m, + = 바깥·카메라 쪽)')
        ax.set_title(f'{PLACE_KO.get(pl, pl)}\n{RUNKO[run]} · 풀림 {n}건', fontsize=10); ax.legend(fontsize=7, loc='lower right'); ax.grid(alpha=.3)
        src[f'{run}/{pl}'] = str(A4O/'ga'/f'events_{run}.npz')
    fig.suptitle('풀린 가우시안은 모두 목표 중심에서 접선으로 0.5 m 넘게 떨어진 순간 풀린다 (법선 쪽은 위치 제약 안)', fontsize=13); fig.tight_layout()
    save(fig, 'ga_release_position', dict(sources=src, rule='addendum4_b.json events: position of each release event relative to the previous target plane'))

def move_fig():
    plt = korean_plt(); fig, axes = plt.subplots(1, 2, figsize=(14, 5)); src = {}
    for ax, comp, lab in [(axes[0], 'move_tangent_m', '처음 놓인 자리에서 풀릴 때까지 접선 이동 (m)'), (axes[1], 'move_normal_m', '처음 놓인 자리에서 풀릴 때까지 법선 이동 (m, + = 바깥)')]:
        for run, pl, col in [('tl_R1_ALS_own', 'floor_band', '#d62728'), ('tl_R1_ALS_own', 'floor_control', '#7f7f7f'), ('sa1_R1_ALS_record6000', 'floor_band', '#ff9896')]:
            z = loadz(A4O/'ga'/f'events_{run}.npz'); v = z[f'{pl}_release__{comp}']; v = v[np.isfinite(v)]
            ax.hist(v, bins=np.linspace(-1, 3, 81) if 'normal' in comp else np.linspace(0, 3, 61), histtype='step', lw=1.6, color=col, label=f'{PLACE_KO[pl]} · {RUNKO[run]} ({len(v)})'); src[f'{run}/{pl}'] = str(A4O/'ga'/f'events_{run}.npz')
        ax.set_xlabel(lab); ax.set_ylabel('풀린 가우시안 수'); ax.legend(fontsize=8); ax.grid(alpha=.3)
    fig.suptitle('R1: 풀린 가우시안은 처음 자리에서 접선으로 약 0.9 m 움직였고, 법선으로는 거의 움직이지 않았다', fontsize=12); fig.tight_layout()
    save(fig, 'ga_release_movement', dict(sources=src))

def grad_fig():
    plt = korean_plt(); rows = json.loads((A4D/'tables/ga_grad_normal.json').read_text())['rows']; fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    W = ['0–200', '200–1000', '1000–3000', '3000–6000']
    for ax, pl in zip(axes, ['floor_band', 'floor_control']):
        for term, col in [('광도', '#1f77b4'), ('깊이', '#2ca02c')]:
            for grp, ls in [('released_by_6000', '-'), ('bound_to_6000', '--')]:
                y = [next((r['outward_pct_nonzero'] for r in rows if r['place'] == pl and r['term'] == term and r['window'] == w and r['group'] == grp), None) for w in W]
                ax.plot(W, y, ls, color=col, marker='o', label=f'{term} · {"6,000회 전에 풀린 것" if grp.startswith("rel") else "끝까지 묶인 것"}')
        ax.axhline(50, color='k', lw=.8); ax.set_ylim(0, 100); ax.set_ylabel('기울기가 바깥(카메라 쪽)으로 미는 비율 (%)'); ax.set_xlabel('반복 구간'); ax.set_title(PLACE_KO[pl]); ax.legend(fontsize=8); ax.grid(alpha=.3)
    fig.suptitle('R1 (사-1): 광도·깊이 손실의 목표 법선 방향 기울기는 바깥·안쪽이 반반이다 (기울기를 받은 표본만)', fontsize=12); fig.tight_layout()
    save(fig, 'ga_grad_normal_sign', dict(sources=dict(table=str(A4D/'tables/ga_grad_normal.json'))))

def na_fig():
    plt = korean_plt(); fig, axes = plt.subplots(1, 3, figsize=(17, 5.2)); src = {}
    sets = [('sa1_R1_ALS_record6000', 'floor_band'), ('sa1_R1_ALS_record6000', 'floor_control'), ('tl_B0_LoD2_own', 'edge_back'), ('tl_B0_LoD2_own', 'edge_back_control'), ('ba3_B0_ALS_record', 'annex_right')]
    labels = []; vals = {k: [] for k in ['open_view_share_median_3000_pre_reset', 'colour_weight_sum_median', 'n']}
    for run, pl in sets:
        rows = json.loads((A4D/'tables'/f'na_groups_{run}.json').read_text())['rows']; src[run] = str(A4D/'tables'/f'na_groups_{run}.json')
        for grp in ['살아남음', '제거됨']:
            r = next(x for x in rows if x['place'] == pl and x['group'] == grp); labels.append(f'{PLACE_KO[pl][:14]}\n{grp} {r["gaussians"]}')
            vals['open_view_share_median_3000_pre_reset'].append(100*(r.get('open_view_share_median_3000_pre_reset') or 0)); vals['colour_weight_sum_median'].append(r.get('colour_weight_sum_median') or 0); vals['n'].append(r['gaussians'])
    x = np.arange(len(labels)); cols = ['#2ca02c' if 'live' in l or '살아' in l else '#d62728' for l in labels]
    axes[0].bar(x, vals['open_view_share_median_3000_pre_reset'], color=cols); axes[0].set_ylabel('앞이 트인 영상 비율 (%, 중앙값)\n(가우시안 앞 누적 불투명도 < 0.5)')
    axes[1].bar(x, vals['colour_weight_sum_median'], color=cols); axes[1].set_ylabel('색에 쓰인 무게 αT 합 (모든 영상, 중앙값)')
    for ax in axes[:2]: ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=7, rotation=90); ax.grid(axis='y', alpha=.3)
    rows = json.loads((A4D/'tables/na_opacity_grad_sa1.json').read_text())['rows']; keys = [(pl, g) for pl in ['floor_band', 'floor_control'] for g in ['살아남음', '제거됨']]
    share = [100*sum(r['광도_nonzero'] for r in rows if (r['place'], r['group']) == k)/max(1, sum(r['alive'] for r in rows if (r['place'], r['group']) == k)) for k in keys]
    axes[2].bar(np.arange(len(keys)), share, color=['#2ca02c' if g == '살아남음' else '#d62728' for _, g in keys]); axes[2].set_xticks(np.arange(len(keys)))
    axes[2].set_xticklabels([f'{PLACE_KO[pl][:12]}\n{g}' for pl, g in keys], fontsize=8)
    axes[2].set_ylabel('3,000~6,000회 기록 반복에서 살아 있던 때 중\n광도 기울기를 받은 비율 (%)'); axes[2].grid(axis='y', alpha=.3)
    fig.suptitle('3,000회 재설정 직전 목표에 묶였던 가우시안: 초록 = 6,000회까지 살아남음, 빨강 = 제거됨', fontsize=12); fig.tight_layout()
    save(fig, 'na_groups', dict(sources=src, rule='addendum4_b.json na'))

if __name__ == '__main__':
    release_fig(); move_fig(); grad_fig(); na_fig(); print('FIGS done', flush=True)
