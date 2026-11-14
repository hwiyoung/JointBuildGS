"""Work da figures: visible-wall weight by depth bin per model and pixel class; wrong-surface weight by depth bin and kind."""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1/addendum4')
from a4_common import *
FIG = A4D/'figures'
def main():
    plt = korean_plt(); fig, axes = plt.subplots(1, 3, figsize=(20, 6)); MK = ['record_7000', 'record_15000', 'record_30000', 'ba2b_15000', 'ba2b_30000']; MKO = ['기록 7,000', '기록 15,000', '기록 30,000', '재설정 끈 판 15,000', '재설정 끈 판 30,000']
    BN = ['목표 앞', '목표 ±1 m', '목표 뒤 1~5 m', '목표 뒤 5 m+']; BC = ['#d62728', '#2ca02c', '#1f77b4', '#9467bd']
    for ax, pl, ci, cn in [(axes[0], 'visible_low', 0, '앞에 다른 것'), (axes[1], 'visible_low', 1, '같음')]:
        bottom = np.zeros(len(MK))
        for bi, bn in enumerate(BN):
            vals = []
            for mk in MK:
                z = loadz(A4O/'da'/f'wall_{mk}.npz', [f'{pl}__bins', f'{pl}__pixels']); vals.append(z[f'{pl}__bins'][ci, bi].sum()/max(1, z[f'{pl}__pixels'][ci]))
            ax.bar(MKO, vals, bottom=bottom, color=BC[bi], label=bn); bottom += np.array(vals)
        ax.set_ylim(0, 1.05); ax.set_ylabel('화소당 렌더링 무게 (αT 합)'); ax.set_title(f'잘 보이는 벽 0~5 m · 화소 분류 "{cn}"\n(영상 깊이가 목표보다 1 m 넘게 앞 = 사진에서 앞에 다른 것)' if ci == 0 else f'잘 보이는 벽 0~5 m · 화소 분류 "{cn}"', fontsize=10)
        ax.tick_params(axis='x', rotation=20); ax.legend(fontsize=8)
    ax = axes[2]; labs = []; data = []
    for case, sn, lab in [('south', 'wrong', '남쪽 끝 벽 뒤 0.64 m+'), ('annex', 'wrong', '별채 지붕 아래 1 m+'), ('annex', 'right_roof', '대조: 별채 지붕 맞는 점')]:
        z = loadz(A4O/'da'/f'wrong_{case}.npz', [f'{sn}__w']); w = z[f'{sn}__w']; data.append(w.sum((2, 3)).mean(0)); labs.append(lab)
    data = np.array(data); bottom = np.zeros(len(labs))
    for bi, (bn, c) in enumerate(zip(['틀린 면보다 앞', '틀린 면 ±0.5 m', '틀린 면보다 뒤'], ['#d62728', '#2ca02c', '#1f77b4'])):
        ax.bar(labs, data[:, bi], bottom=bottom, color=c, label=bn); bottom += data[:, bi]
    ax.set_ylim(0, 1.05); ax.set_ylabel('그 점을 만든 영상 화소의 평균 무게'); ax.set_title('실제로 없는 면의 결과 점: 그 깊이에 가우시안이 있는가', fontsize=10); ax.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(FIG/'da_weights.png', dpi=100)
    dump(FIG/'da_weights.json', dict(at=now(), sources=[str(A4O/'da'/f'wall_{m}.npz') for m in MK]+[str(A4O/'da/wrong_south.npz'), str(A4O/'da/wrong_annex.npz')], scientific_verdict=None)); print('DAFIG', flush=True)
if __name__ == '__main__': main()
