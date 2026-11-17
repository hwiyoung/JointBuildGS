"""PHD-MAIN-TRAINUNIT-v2 figures (run2_cpu.sh).

  python tu2_figs.py cells     -> figures/cells_partition.png|json (넷 and 아홉: original and expanded boundaries, cameras, boxes, footprints)
"""
import sys

from tu_common import *
from tu_campus import CAMPUS
from tu2_cells import TU1, centres, footprints
from tu2_stop import plt_ko


def cells():
    plt = plt_ko()
    from matplotlib.patches import Rectangle, Polygon
    split = json.loads((CAMPUS / 'split.json').read_text())
    _, cent = centres(split['train'])
    C = np.array([cent[n][:2] for n in split['train']])
    fp = footprints()
    boxes = {s: json.loads((PH / 'main_gtjudge_v1/PHD-MAIN-GTJUDGE-v1/views' / f'{s}.json').read_text())['box'] for s in SITES}
    plans = [('넷 (2 × 2)', json.loads((TU1 / 'cells/cells.json').read_text())), ('아홉 (3 × 3)', json.loads((TU / 'cells/cells.json').read_text()))]
    lo, hi = np.array(plans[0][1]['outer_limits_sfm_p05_p995'])
    fig, ax = plt.subplots(1, 2, figsize=(16, 8.5))
    data = {}
    for a, (title, cj) in zip(ax, plans):
        for f in fp.values():
            a.add_patch(Polygon(f['vertices'][:, :2], closed=False, fc='none', ec='0.6', lw=.4))
        a.scatter(C[:, 0], C[:, 1], s=3, c='tab:blue', alpha=.5, label='학습 카메라 위치(지면 투영)')
        for c in cj['cells']:
            ol, oh = np.clip(c['original_min'], lo, hi), np.clip(c['original_max'], lo, hi)
            el, eh = np.clip(c['expanded_min'], lo, hi), np.clip(c['expanded_max'], lo, hi)
            a.add_patch(Rectangle(ol, *(oh - ol), fc='none', ec='k', lw=1.6))
            a.add_patch(Rectangle(el, *(eh - el), fc='none', ec='tab:red', lw=.9, ls='--'))
            a.text(*(ol + oh) / 2, f'칸 {c["id"]}\n{len(c["images"])}장', ha='center', va='center', fontsize=9,
                   bbox=dict(fc='white', ec='none', alpha=.7))
        for s, b in boxes.items():
            a.add_patch(Rectangle(b[0][:2], b[1][0] - b[0][0], b[1][1] - b[0][1], fc='tab:green', alpha=.35, ec='tab:green', lw=1.2))
            a.text(b[1][0], b[1][1], s.replace('_b10', ''), color='darkgreen', fontsize=9)
        a.set_xlim(lo[0] - 20, hi[0] + 20); a.set_ylim(lo[1] - 20, hi[1] + 20); a.set_aspect('equal')
        a.set_title(f'{title}: 검은 실선 = 넓히기 전 경계, 빨간 점선 = 넓힌 경계(20 %), 초록 = 평가 상자')
        a.set_xlabel('x (m, EPSG:25832 − 690953)'); a.set_ylabel('y (m, EPSG:25832 − 5336071)')
        data[title] = dict(cells=[{k: c[k] for k in ['id', 'original_min', 'original_max', 'expanded_min', 'expanded_max']} | dict(images=len(c['images'])) for c in cj['cells']])
    ax[0].legend(loc='lower left', fontsize=8)
    fig.suptitle('칸 나누기 (안쪽 경계는 카메라 수가 같게, 바깥 경계는 SfM 0.5–99.5 % 범위에서 자름; 회색 = LoD2 바닥 윤곽)')
    fig.tight_layout()
    out = D / 'figures/cells_partition'
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out.with_suffix('.png'), dpi=120)
    dump(out.with_suffix('.json'), dict(plans=data, boxes=boxes, outer_limits=[lo.tolist(), hi.tolist()], cameras=len(C), scientific_verdict=None))
    print('FIG cells', flush=True)


if __name__ == '__main__':
    dict(cells=cells)[sys.argv[1]](*sys.argv[2:])
