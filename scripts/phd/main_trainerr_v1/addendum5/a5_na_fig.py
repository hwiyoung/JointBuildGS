"""Work na (order 9 '정성: 일 나의 대표 화소 그림'): representative supervised pixels of each place's problem group (30,000), from the work-na pixel records.
Pixel choice (fixed before looking): among the problem group's supervised pixels, the pixels at the 25 / 50 / 75 % quantiles of the group's weight (alpha*T) in the pixel,
the same rule as the south-wall figure of work ba. Each pixel is one stacked bar: weight in front of / within +-1.96 sigma of / behind the target depth, split into the group and the rest.
usage: a5_na_fig.py <run>:<label> [...]   -> figures/na_rep_pixels.png + .json, payload addendum5/na/na_rep_pixels.npz.  CPU image."""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1/addendum5'); sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1/addendum4')
from a5_common import *
NA5 = A5O/'na'; FIG5 = A5D/'figures'
OWN = ['그 자리의 목표 원판', '다른 면의 목표 원판', '목표 원판 없음(영상 깊이가 목표)']
PARTS = [('w_front', 'gw_front', '목표 앞'), ('w_within', 'gw_within', '허용 구간 안'), ('w_behind', 'gw_behind', '목표 뒤')]
COL = {'목표 앞': '#4c78a8', '허용 구간 안': '#54a24b', '목표 뒤': '#b279a2'}

def main(*specs):
    plt = korean_plt(); state = '30000'; rows = []; out = {}
    fig, axs = plt.subplots(len(specs), 1, figsize=(26, 2.8*len(specs)+1.6), squeeze=False); axs = axs[:, 0]
    for si, (ax, spec) in enumerate(zip(axs, specs)):
        run, label = spec.split(':', 1); z = loadz(NA5/f'pix_{run}_{state}.npz')
        sup = np.isfinite(z['td']) & (z['td'] > 0) & (z['wmap'] > 0) & np.isfinite(z['mean']) & (z['mean'] > 0)
        idx = np.flatnonzero((z['group'] == 0) & sup); gw = z['gw'][idx]; order = idx[np.argsort(gw, kind='stable')]
        pick = [int(order[min(len(order)-1, int(round(q*(len(order)-1))))]) for q in (.25, .5, .75)]
        for k, i in enumerate(pick):
            y = 2-k; left = 0.
            for wk, gk, nm in PARTS:
                g = float(z[gk][i]); o = float(z[wk][i])-g
                ax.barh(y, o, left=left, color=COL[nm], alpha=.35, edgecolor='k', lw=.5, label=f'{nm}: 다른 가우시안' if (si == 0 and k == 0) else None); left += o
                ax.barh(y, g, left=left, color=COL[nm], alpha=1., edgecolor='k', lw=.5, hatch='//', label=f'{nm}: 문제 무리' if (si == 0 and k == 0) else None); left += g
            dd = float(z['mean'][i]-z['td'][i]); tol = float(1.96*z['sig'][i])
            ax.text(1.01, y, f'{("25", "50", "75")[k]} % 분위 화소 · 무리 무게 {gw_i(z, i):.2f} · 그린 깊이 − 목표 {dd:+.2f} m (허용 ±{tol:.2f}) · 목표: {OWN[int(z["own"][i])]} · 화소 무게 {float(z["wmap"][i]):.2f}',
                    transform=ax.get_yaxis_transform(), va='center', fontsize=11)
            rows.append(dict(place=label, run=run, iteration=30000, quantile=(25, 50, 75)[k], pixel_record=i, view=int(z['view'][i]), group_weight=gw_i(z, i), opacity_sum=float(z['acc'][i]),
                             rendered_minus_target_m=dd, tolerance_m=tol, within_tolerance=bool(abs(dd) <= tol), target_owner=OWN[int(z['own'][i])], pixel_weight=float(z['wmap'][i]),
                             **{f'{nm} 전체': float(z[wk][i]) for wk, gk, nm in PARTS}, **{f'{nm} 문제 무리': float(z[gk][i]) for wk, gk, nm in PARTS}, supervised_pixels=int(len(idx))))
        ax.set_yticks([2, 1, 0]); ax.set_yticklabels(['25 %', '50 %', '75 %']); ax.set_xlim(0, 1.0); ax.set_ylim(-.6, 2.6)
        ax.set_title(f'{label} (감독 화소 {len(idx):,}개 가운데)', fontsize=12, loc='left'); ax.grid(axis='x', alpha=.3)
        out[f'{si}__pick'] = np.array(pick)
    axs[-1].set_xlabel('화소의 무게 αT (그 화소를 그린 모든 가우시안의 합, 0~1)')
    axs[0].legend(loc='lower left', bbox_to_anchor=(0, 1.18), ncol=6, fontsize=10, frameon=False)
    fig.suptitle('문제 무리가 무게를 주는 감독 화소 셋(무리 무게 25·50·75 % 분위)에서, 화소 무게가 목표 앞·허용 구간 안·목표 뒤에 나뉜 모양', fontsize=15, weight='bold')
    fig.tight_layout(rect=(0, 0, .5, .95))
    FIG5.mkdir(parents=True, exist_ok=True); fig.savefig(FIG5/'na_rep_pixels.png', dpi=160, bbox_inches='tight', pad_inches=.3)
    from PIL import Image; W = Image.open(FIG5/'na_rep_pixels.png').width
    table('na_rep_pixels', rows, folder=A5D/'tables')
    dump(FIG5/'na_rep_pixels.json', dict(at=now(), figure='na_rep_pixels.png', width_px=W, state=state, specs=list(specs), rule='problem group supervised pixels; 25/50/75 % quantiles of the group weight (alpha*T) in the pixel',
                                          table='tables/na_rep_pixels.csv', points_npz='payload addendum5/na/na_rep_pixels.npz', scientific_verdict=None))
    savez(NA5/'na_rep_pixels.npz', **out); print('NA_FIG', W, len(rows), flush=True)

def gw_i(z, i): return float(z['gw'][i])

if __name__ == '__main__': main(*sys.argv[1:])
