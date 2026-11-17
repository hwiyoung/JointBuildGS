"""덧붙임 2 그림 P1 (섞인 패치 본보기 넷), P2 (판마다 패치 단위와 점 단위 목표 맞음). 사용: c2_figs.py"""
import sys; sys.path.insert(0, '/repo/scripts/phd/main_judgeabl_v1'); sys.path.append('/repo/scripts/phd/main_judgeprobe_v1')
from common import *
import pandas as pd
import p7_figs as P7
import matplotlib.pyplot as plt
from scipy.spatial import cKDTree
FIG = D/'figures/addendum2'; TAB = D/'tables/addendum2'; A2 = O/'addendum2'; CN = [CASE[c] for c in CASES]
CC = {0: '#2ca02c', 1: '#ff7f0e', 2: '#1f77b4', 3: '#7f7f7f', 4: '#9467bd'}; CNAME = {**CASE, 3: '네 경우 밖'}
PN = {'LoD2': 'LoD2', 'ALS': '항공 LiDAR'}
def save(fig, name, meta): FIG.mkdir(parents=True, exist_ok=True); fig.savefig(FIG/f'{name}.png', dpi=300, facecolor='white', bbox_inches='tight'); plt.close(fig); dump(FIG/f'{name}.json', dict(meta, at=now(), scientific_verdict=None))
def p2():
    U = pd.read_csv(TAB/'p_patch_unit.csv'); M = pd.read_csv(D/'tables/s_main_summary.csv')
    for prior, sf in [('LoD2', '모두'), ('ALS', '지붕')]:
        q = U[(U.prior == prior) & (U.surface == sf)]; order = [v for v in M[M.prior == prior].variant if v in set(q.variant)] + sorted([v for v in q.variant if v.startswith('고정 ')], key=lambda v: int(v.split(' ')[1]))
        q = q.set_index('variant').loc[order]; y = np.arange(len(q))[::-1]
        fig, axs = plt.subplots(1, 4, figsize=(14, .22*len(q) + 1.5), sharey=True)
        for ax, c in zip(axs, CN):
            ax.hlines(y, q[f'point_ok_{c}'], q[f'patch_ok_{c}'], color='#bbbbbb', lw=.8)
            ax.plot(q[f'point_ok_{c}'], y, 'o', ms=3, color='#1f4e9c', label='점 단위'); ax.plot(q[f'patch_ok_{c}'], y, 's', ms=3, color='#d62728', label='패치 단위')
            ax.set_title(c, fontsize=8); ax.set_xlim(0, 100); ax.grid(axis='x', lw=.3, alpha=.5); ax.set_xlabel('목표 맞음 %')
        axs[0].set_yticks(y); axs[0].set_yticklabels(q.index, fontsize=5.5); axs[0].legend(fontsize=6, loc='lower left')
        fig.suptitle(f'{PN[prior]}: 판마다 점 단위와 패치 단위 목표 맞음 (패치 단위 = 넓이 가중, 다수 경우 점의 절반 이상이 τ 안)', fontsize=9, y=1.0); fig.tight_layout(rect=[0, 0, 1, .97])
        save(fig, f'figP2_patch_vs_point_{prior}', dict(prior=prior, surface=sf, variants=order, source='tables/addendum2/p_patch_unit.csv'))
def p1():
    for prior, case_ in [('ALS', 1), ('LoD2', 2)]:
        z = np.load(A2/f'patch_case_{prior}.npz'); pc, tot, share = z['pc'], z['tot'], z['share']
        d = loadz(JP/f'patch_{prior}.npz', ['tile', 'tiles', 'centre', 'normal', 'tangent1', 'prior_height_m', 'building', 'place', 'target_h', 'j_region', 'mvs_mean_m', 'd_for_check', 'L_m', 's_P', 's_M', 't'])
        g = loadz(JC/'analysis'/f'gt_{prior}.npz', ['xyz', 'case', 'gid', 'paired']); gtree = cKDTree(g['xyz'][:, :2]); ts = list(d['tiles']); pick = []
        for pl in [2, 0]:
            cand = np.flatnonzero((pc == case_) & (share < .8) & (d['place'] == pl)); cand = cand[np.argsort(-tot[cand], kind='stable')]; seen = set(); k = 0
            for i in cand:
                if d['building'][i] in seen: continue
                pick.append((pl, int(i))); seen.add(d['building'][i]); k += 1
                if k == 2: break
        fig, axs = plt.subplots(len(pick), 2, figsize=(9, 3.3*len(pick)), squeeze=False); meta = []
        for r, (pl, i) in enumerate(pick):
            c0 = d['centre'][i]; n = d['normal'][i]; t1 = d['tangent1'][i]; t2 = np.cross(n, t1); t2 /= np.linalg.norm(t2); hp = d['prior_height_m'][i]
            corners = c0 + hp*n + np.array([[-1, -1], [1, -1], [1, 1], [-1, 1]])[:, :1]*.125*t1 + np.array([[-1, -1], [1, -1], [1, 1], [-1, 1]])[:, 1:]*.125*t2
            mine = np.flatnonzero(g['paired'] & (g['gid'] == i)); X = np.r_[corners, g['xyz'][mine]]
            j = P7.oblique_view(X); cols = ['#ffe600']*4 + [CC.get(int(c), 'k') for c in g['case'][mine]]
            if j is None: axs[r, 0].text(.5, .5, '비스듬한 영상 없음', ha='center', transform=axs[r, 0].transAxes); axs[r, 0].axis('off')
            else: P7.draw_on_view(axs[r, 0], j, X, cols, pad=40)
            cnt = np.bincount(g['case'][mine].clip(0, 4), minlength=5)
            axs[r, 0].set_title(f"({PLACE[pl]}) {d['building'][i].replace('DEBY_LOD2_', '')} · 참값 점 {len(mine)} · 다수 비율 {share[i]*100:.0f} %", fontsize=6.5)
            B = axs[r, 1];             ht = d['target_h'][i, 4]; own = (g['xyz'][mine] - c0) @ n; ys = np.r_[own, [hp, ht]]; ys = ys[np.isfinite(ys)]
            ylo, yhi = (ys.min() - .5, ys.max() + .5) if len(ys) else (-1.5, 1.5)
            if yhi - ylo < 3: m_ = (ylo + yhi)/2; ylo, yhi = m_ - 1.5, m_ + 1.5
            sec = lambda Q: (np.abs((Q - c0) @ t2) <= .15) & (np.abs((Q - c0) @ t1) <= 1.5) & ((Q - c0) @ n >= ylo) & ((Q - c0) @ n <= yhi)
            nb = gtree.query_ball_point(c0[:2], 2.5); G = g['xyz'][nb]; gc = g['case'][nb]; sm = sec(G); G, gc = G[sm], gc[sm]
            M = P7.mvs_near(ts[d['tile'][i]], c0 - 2.5 + np.minimum(0, ylo)*np.abs(n), c0 + 2.5 + np.maximum(0, yhi)*np.abs(n)); M = M[sec(M)]
            if len(M) > 4000: M = M[np.random.default_rng(1).choice(len(M), 4000, replace=False)]
            B.scatter((M - c0) @ t1, (M - c0) @ n, s=.5, c='#9ecae1', lw=0, label='영상 깊이 점')
            for c in [0, 1, 2, 3, 4]:
                m = gc == c
                if m.any(): B.scatter((G[m] - c0) @ t1, (G[m] - c0) @ n, s=2, c=CC[c], lw=0, label=CNAME[c])
            B.plot([-1.5, 1.5], [hp, hp], color='#d9822b', lw=1, label='사전 정보')
            if np.isfinite(ht): B.plot([-.125, .125], [ht, ht], color='#1f4e9c', lw=2.2, label='본 방법 목표')
            for xv in [-.125, .125]: B.axvline(xv, color='k', ls=':', lw=.7)
            B.set_xlim(-1.5, 1.5); B.set_ylim(ylo, yhi); B.tick_params(labelsize=5)
            B.set_title('단면 ±0.15 m (점선 = 패치 경계, 세로 = 법선 방향)', fontsize=6.5)
            B.set_xlabel(f"경우별 점 수(유효·사전 오류·영상 오류·결측·밖) " + ' / '.join(str(cnt[c]) for c in [0, 1, 2, 4, 3]) + f"\n본 방법 {JUD.get(int(d['j_region'][i, 4]))}, d {d['d_for_check'][i]:.2f} L {d['L_m'][i]:.2f} s_P {d['s_P'][i]:.2f} s_M {d['s_M'][i]:.2f} t {d['t'][i]:.2f}", fontsize=5)
            if r == 0: B.legend(fontsize=4.5, loc='lower left', markerscale=3, frameon=False)
            meta.append(dict(place=PLACE[pl], patch_gid=i, building=str(d['building'][i]), gt_points=int(len(mine)), majority_share=float(share[i]), case_counts=cnt.tolist(), view=None if j is None else P7.cam().names[j]))
        fig.suptitle(f"{PN[prior]}: 섞인 패치 본보기 (패치의 경우 {CASE[case_]}, 다수 비율 < 80 %, 건물 가장자리 둘·면 안쪽 둘)", fontsize=8); fig.tight_layout(rect=[0, 0, 1, .98])
        save(fig, f'figP1_mixed_patch_{prior}', dict(prior=prior, patch_case=CASE[case_], rule='patch case = order case, majority share < 0.8, place 건물 가장자리 then 면 안쪽, most GT points first, one per building', patches=meta))
if __name__ == '__main__':
    p2(); p1(); progress('덧붙임 2 그림 P1·P2 끝')
