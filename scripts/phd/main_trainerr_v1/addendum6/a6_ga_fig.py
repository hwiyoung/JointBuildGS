"""Work ga figures (order 10 value figures, kept as in 10; correction 1 applies to the case figures only). CPU.
  -> figures/ga_patch_course.png (share of the points' patches with >= 1 bound Gaussian at every whole-scene dump, four groups, six scenes)
     figures/ga_exit_paths.png  (main path of the points' patches and the share of exits by path, four groups, six scenes)
     + json sources and payload addendum6/ga/fig_*.npz (the plotted values)"""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1/addendum6')
from a6_common import *
GA6 = A6O/'ga'; PTS = A6O/'points'; FIG = A6D/'figures'
COL = ['#9e9e9e', '#1f5fd6', '#2ca02c', '#d62728']; SC_KO = {'R1rep_b10__LoD2': 'R1 × LoD2', 'R1rep_b10__ALS': 'R1 × 항공 LiDAR', 'B0_b10__LoD2': 'B0 × LoD2', 'B0_b10__ALS': 'B0 × 항공 LiDAR',
                                                           'B173nb_b10__ALS': 'B173 × 항공 LiDAR', 'B173nb_b10__LoD2': 'B173 × LoD2'}
PATH_KO = ['풀림', '재할당', '재설정 뒤 제거', '그 밖의 제거', '분할로 대체']; PCOL = ['#ff7f0e', '#1f77b4', '#d62728', '#8c564b', '#9467bd']

def main():
    sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1/addendum3'); plt = korean_plt(); scenes = cfg6()['points']['scenes']; out = {}; src = {}
    fig, axs = plt.subplots(2, 3, figsize=(24, 12), sharey=True); axs = axs.ravel()
    for ax, stem in zip(axs, scenes):
        z = loadz(GA6/f'patch_{stem}.npz'); S = loadz(PTS/f'sel_{stem}.npz'); P = z['patches']; pos = np.full(int(P.max())+1, -1); pos[P] = np.arange(len(P)); it = z['iterations']
        x = np.where(it == 0, 50, it)
        for gk in range(4):
            v = S['v'][(S['group'] == gk) & (S['v'] >= 0)]; q = pos[v]; y = 100*(z['counts'][:, q] > 0).mean(1)
            ax.plot(x, y, color=COL[gk], lw=2.4 if gk == 1 else 1.6, label=f'{GROUP_KO[gk]} ({len(q):,}점)'); out[f'{stem}__{gk}'] = y
        out[f'{stem}__it'] = it; ax.set_xscale('log'); ax.set_xlim(40, 33000); ax.set_ylim(0, 102); ax.grid(alpha=.3)
        ax.set_xticks([50, 100, 300, 1000, 3000, 7000, 15000, 30000]); ax.set_xticklabels(['0', '100', '300', '1,000', '3,000', '7,000', '15,000', '30,000'])
        for r in [3000, 6000, 9000, 12000]: ax.axvline(r, color='k', lw=.6, ls=':')
        k = int(np.argmin(np.abs(it-300))); ax.annotate('300회', (x[k], 100*(z['counts'][k, pos[S['v'][(S['group'] == 1) & (S['v'] >= 0)]]] > 0).mean()), xytext=(600, 85), arrowprops=dict(arrowstyle='->'), fontsize=11)
        ax.set_title(SC_KO[stem], fontsize=13, loc='left'); ax.set_xlabel('반복 (로그 눈금, 점선 = 불투명도 재설정)'); src[stem] = dict(run=cfg6()['runs'][stem]['run'], dumps=len(it))
    axs[0].set_ylabel('그 점의 목표 조각에 묶인 가우시안이 하나 이상인 점 (%)'); axs[3].set_ylabel('그 점의 목표 조각에 묶인 가우시안이 하나 이상인 점 (%)'); axs[0].legend(fontsize=10, loc='lower left')
    fig.suptitle('잃은 점의 조각은 몇 회에 비고, 지킨 점의 조각은 비지 않는다 \n값: 300회에 네 무리 모두 절반 가까운 조각이 비어 있고, 3,000회 재설정 뒤에는 잃은 점의 조각이 지킨 점의 조각보다 더 많이 빈다', fontsize=16, weight='bold')
    fig.tight_layout(rect=(0, 0, 1, .95)); FIG.mkdir(parents=True, exist_ok=True); fig.savefig(FIG/'ga_patch_course.png', dpi=110); plt.close(fig)
    savez(GA6/'fig_patch_course.npz', **out); dump(FIG/'ga_patch_course.json', dict(at=now(), figure='ga_patch_course.png', runs=src, values='payload addendum6/ga/fig_patch_course.npz', table='tables/ga_stage_counts.csv',
                                                                                    rule='per point the patch (FINALTRAIN group); bound = target_tag 1 and target_index = the patch, at every whole-scene dump', scientific_verdict=None))
    fig, axs = plt.subplots(2, 3, figsize=(24, 12), sharey=True); axs = axs.ravel(); out = {}
    rows = json.loads((A6D/'tables/ga_paths.json').read_text())['rows']
    for ax, stem in zip(axs, scenes):
        rr = {r['group']: r for r in rows if r['stem'] == stem and r['definition'] == 'FINALTRAIN' and r['state'] == '전체'}
        for gk in range(4):
            r = rr[GROUP_KO[gk]]; left = 0
            for i, nm in enumerate(PATH_KO):
                v = r.get(f'main_{nm}_pct') or 0; ax.barh(3-gk+.18, v, left=left, height=.34, color=PCOL[i], label=nm if (stem == scenes[0] and gk == 0) else None); left += v
            left = 0
            for i, nm in enumerate(PATH_KO):
                v = r.get(f'exits_{nm}_share_pct') or 0; ax.barh(3-gk-.18, v, left=left, height=.34, color=PCOL[i], alpha=.45); left += v
            out[f'{stem}__{gk}'] = np.array([[r.get(f'main_{nm}_pct') or 0 for nm in PATH_KO], [r.get(f'exits_{nm}_share_pct') or 0 for nm in PATH_KO]])
        ax.set_yticks([3, 2, 1, 0]); ax.set_yticklabels([f'{GROUP_KO[g]}\n위: 조각의 주된 길 / 아래: 나간 사건' for g in range(4)], fontsize=9); ax.set_xlim(0, 100); ax.set_title(SC_KO[stem], fontsize=13, loc='left'); ax.set_xlabel('%'); ax.grid(axis='x', alpha=.3)
    axs[0].legend(loc='lower left', bbox_to_anchor=(0, 1.08), ncol=5, fontsize=11, frameon=False)
    fig.suptitle('잃은 점의 조각에서 가우시안이 나간 길의 비율 (네 무리 나란히)', fontsize=16, weight='bold'); fig.tight_layout(rect=(0, 0, 1, .93)); fig.savefig(FIG/'ga_exit_paths.png', dpi=110); plt.close(fig)
    savez(GA6/'fig_exit_paths.npz', **out); dump(FIG/'ga_exit_paths.json', dict(at=now(), figure='ga_exit_paths.png', values='payload addendum6/ga/fig_exit_paths.npz', table='tables/ga_paths.csv', scientific_verdict=None))
    print('GA6_FIG', flush=True)

if __name__ == '__main__': main()
