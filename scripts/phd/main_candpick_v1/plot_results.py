"""Source-backed static research plots; identical scales across cases."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
from matplotlib.ticker import PercentFormatter
import numpy as np
from input_audit import sha
from result_io import save

FONT = Path('/out/assets/NotoSansCJK-Regular.ttc')
COLORS = {'equal': '#286c9e', 'right': '#bc8425', 'wrong': '#a34a70'}
START = {'equal': '출발 같음', 'right': '출발 맞음', 'wrong': '출발 틀림'}
GROUP = {'a': '가 · 사진 정보 있음', 'b': '나 · 사진 정보 약함', 'c': '다 · 사진이 속음'}
SIDE = {'all': '앞뒤 전체', 'front': '맞는 후보가 앞', 'back': '맞는 후보가 뒤'}


def setup():
    assert FONT.exists(), FONT
    plt.rcParams.update({'font.family': FontProperties(fname=str(FONT)).get_name(),
        'axes.unicode_minus': False, 'font.size': 12, 'axes.titlesize': 14,
        'axes.spines.top': False, 'axes.spines.right': False, 'savefig.facecolor': 'white'})
    from matplotlib import font_manager
    font_manager.fontManager.addfont(str(FONT))


def write(fig, path):
    fig.savefig(path.with_suffix('.png'), dpi=180, bbox_inches='tight')
    fig.savefig(path.with_suffix('.pdf'), bbox_inches='tight')
    plt.close(fig)


def main():
    setup()
    root = Path('/docs/results'); dest = Path('/docs/figures'); dest.mkdir(exist_ok=True)
    curves = json.loads((root / 'opacity_curves.json').read_text())['rows']
    outcomes = json.loads((root / 'outcomes.json').read_text())['rows']
    cfg = json.loads(Path('/config/candpick_v1.json').read_text()); created = []
    order = [('equal', 3), ('wrong', 3), ('right', 3), ('equal', 0), ('wrong', 0), ('right', 0)]
    for unit in cfg['units']:
        if len({r['arm'] for r in outcomes if r['unit'] == unit}) != 6: continue
        fig, axes = plt.subplots(3, 2, figsize=(15, 12), sharex=True, sharey=True)
        for i, group in enumerate(['a', 'b', 'c']):
            for j, side in enumerate(['front', 'back']):
                ax = axes[i, j]
                source = [r for r in outcomes if r['unit'] == unit and r['group'] == group and r['side'] == side and r['subset'] == 'all'][0]
                for start, degree in order:
                    values = [r for r in curves if r['unit'] == unit and r['group'] == group and r['side'] == side and r['start'] == start and r['sh_degree'] == degree]
                    values.sort(key=lambda r: r['iteration'])
                    if source['points']:
                        ax.plot([r['iteration'] for r in values], [r['mean_right_minus_wrong'] for r in values],
                            color=COLORS[start], linestyle='-' if degree == 3 else '--', linewidth=1.8,
                            label=START[start] + f' · SH{degree}')
                if not source['points']: ax.text(.5, .5, '해당 점 없음', transform=ax.transAxes, ha='center')
                ax.axhline(0, color='#666666', linewidth=.8)
                ax.set_title(f"{GROUP[group]} / {SIDE[side]}\n{source['points']:,}점 · {source['area_m2']:.2f} m²")
                ax.set_xlim(0, 3000); ax.set_ylim(-1, 1); ax.set_xticks([0, 500, 1000, 1500, 2000, 2500, 3000])
                ax.grid(axis='y', alpha=.18)
                if j == 0: ax.set_ylabel('평균 불투명도 차 (맞는 쪽 − 틀린 쪽)')
                if i == 2: ax.set_xlabel('최적화 반복')
        from matplotlib.lines import Line2D
        handles = [Line2D([], [], color=COLORS[s], linestyle='-' if d == 3 else '--', label=START[s] + f' · SH{d}') for s, d in order]
        fig.legend(handles=handles, loc='upper center', bbox_to_anchor=(.5, .96), ncol=3, frameon=False)
        fig.suptitle(unit.replace('_', ' · ') + ' — 후보 불투명도 변화', y=1.01, fontsize=19)
        fig.text(.5, -.005, '각 후보의 4개 가우시안 불투명도를 먼저 평균한 뒤 점별 차이를 평균함. 실선 SH3 / 점선 SH0. seed 0.', ha='center', fontsize=11)
        fig.tight_layout(rect=[0, .02, 1, .91]); path = dest / (unit + '_opacity_curves'); write(fig, path); created.append(path.name + '.png')
        for subset in ['all', 'occlusion_over_30pct']:
            fig, axes = plt.subplots(1, 3, figsize=(17, 6), sharey=True)
            palette = ['#286c9e', '#bf703d', '#8c8c8c', '#ededed']
            labels = ['맞게 남음', '틀리게 남음', '둘 다 남음', '둘 다 사라짐']
            for ax, side in zip(axes, ['all', 'front', 'back']):
                chosen = [next(r for r in outcomes if r['unit'] == unit and r['subset'] == subset and r['group'] == 'a' and r['side'] == side and r['start'] == s and r['sh_degree'] == d) for s, d in order]
                bottom = np.zeros(6)
                for state, color, label in zip(['right_only', 'wrong_only', 'both', 'neither'], palette, labels):
                    values = np.array([r[state + '_area_fraction'] if r['area_m2'] else 0 for r in chosen])
                    ax.bar(np.arange(6), values, bottom=bottom, color=color, label=label,
                           edgecolor='#555555', linewidth=.4, hatch='//' if state == 'neither' else None)
                    bottom += values
                if not chosen[0]['points']: ax.text(.5, .5, '해당 점 없음', transform=ax.transAxes, ha='center')
                ax.set_xticks(range(6), ['같음\nSH3', '틀림\nSH3', '맞음\nSH3', '같음\nSH0', '틀림\nSH0', '맞음\nSH0'])
                ax.set_ylim(0, 1); ax.yaxis.set_major_formatter(PercentFormatter(1)); ax.set_title(SIDE[side] + f"\n{chosen[0]['points']:,}점 · {chosen[0]['area_m2']:.2f} m²")
            axes[0].set_ylabel('묶음 가의 넓이 비율')
            handles, labels = axes[0].get_legend_handles_labels(); fig.legend(handles, labels, loc='upper center', ncol=4, frameon=False, bbox_to_anchor=(.5, 1.02))
            label = '전체' if subset == 'all' else '가림 30% 초과 점'
            fig.suptitle(unit.replace('_', ' · ') + f' — {label}, 3,000회 뒤', y=1.10, fontsize=19)
            fig.text(.5, -.02, '판정 문턱: 후보별 평균 불투명도 0.5. 넓이는 원본 지붕 패치의 면적 합. 결과 없음은 0%로 대체하지 않음.', ha='center', fontsize=11)
            fig.tight_layout(rect=[0, .02, 1, .94]); path = dest / (unit + '_outcomes_' + subset); write(fig, path); created.append(path.name + '.png')
    save(dest / 'quantitative_index.json', dict(files=created, source_hashes={p.name: sha(p) for p in [root / 'opacity_curves.json', root / 'outcomes.json']},
        font_sha256=sha(FONT), script_sha256=sha(__file__), scientific_verdict=None))
    print('Created', len(created), 'quantitative figures')


if __name__ == '__main__': main()
