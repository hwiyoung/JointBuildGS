"""Cell partition figure (판 다): camera centres by own cell, original and expanded cell edges, evaluation boxes;
and per-iteration time / Gaussian count curves of the stopped cell runs, the campus attempt and the FINALTRAIN runs.

  python tu_fig_cells.py
"""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import Rectangle

from tu_common import *
from tu_campus import cameras

font_manager.fontManager.addfont('/fonts/NotoSansCJK-Regular.ttc')
plt.rcParams.update({'font.family': 'Noto Sans CJK JP', 'axes.unicode_minus': False, 'font.size': 10})
COL = ['#0072b2', '#e69f00', '#009e73', '#cc79a7']


def curve(p):
    rows = [json.loads(l) for l in Path(p).read_text().splitlines() if l.strip()]
    it = np.array([r['iteration'] for r in rows]); el = np.array([r['elapsed_seconds'] for r in rows]); g = np.array([r['gaussians'] for r in rows])
    return it, el, g


def main():
    cfg()
    cells = json.loads((TU / 'cells/cells.json').read_text())
    split = json.loads((TU / 'scenes/campus/split.json').read_text())
    cams = {c['name']: c for c in cameras(split['train'])}
    cen = {n: -np.asarray(c['W2C'], float)[:3, :3].T @ np.asarray(c['W2C'], float)[:3, 3] for n, c in cams.items()}
    P = np.array([cen[n] for n in split['train']])
    lo, hi = P[:, :2].min(0) - 30, P[:, :2].max(0) + 30
    fig, ax = plt.subplots(figsize=(10, 9))
    for c in cells['cells']:
        olo = np.clip(c['original_min'], lo, hi); ohi = np.clip(c['original_max'], lo, hi)
        own = [n for n in split['train'] if c['original_min'][0] <= cen[n][0] < c['original_max'][0] and c['original_min'][1] <= cen[n][1] < c['original_max'][1]]
        q = np.array([cen[n] for n in own])
        ax.scatter(q[:, 0], q[:, 1], s=5, color=COL[c['id']], label=f'칸{c["id"]}: 자기 카메라 {len(own)} · 학습 영상 {len(c["images"])}')
        elo = np.clip(c['expanded_min'], lo, hi); ehi = np.clip(c['expanded_max'], lo, hi)
        ax.add_patch(Rectangle(elo, *(ehi - elo), fill=False, ec=COL[c['id']], ls=':', lw=1))
    for sg in cells['boundaries']:
        a = np.clip(sg['lo'], lo, hi); b = np.clip(sg['hi'], lo, hi)
        ax.plot([a[0], b[0]], [a[1], b[1]], color='#333333', lw=1.2)
    for r in cells['evaluation_boxes']:
        ax.add_patch(Rectangle(r['box_min'], r['box_max'][0] - r['box_min'][0], r['box_max'][1] - r['box_min'][1], fill=False, ec='#d55e00', lw=2))
        ax.text(r['box_min'][0], r['box_max'][1] + 2, f"{r['site']} (칸 {','.join(map(str, r['cells']))})", color='#d55e00', fontsize=9)
    ax.set_aspect('equal'); ax.set(xlim=(lo[0], hi[0]), ylim=(lo[1], hi[1]), xlabel='지역 X (m)', ylabel='지역 Y (m)')
    ax.legend(loc='upper center', bbox_to_anchor=(.5, -.08), ncol=2, frameon=False, fontsize=9)
    ax.set_title('판 다의 칸 나누기: 검정 = 원래 칸 경계, 점선 = 20 % 넓힌 칸, 주황 = 평가 상자')
    fig.subplots_adjust(bottom=.2)
    out = D / 'figures'; out.mkdir(parents=True, exist_ok=True)
    fig.savefig(out / 'cells_partition.png', dpi=200, facecolor='white'); plt.close(fig)
    dump(out / 'cells_partition.json', dict(at=now(), source=str(TU / 'cells/cells.json'), source_sha256=sha(TU / 'cells/cells.json'), scientific_verdict=None))
    # iteration-time curves
    runs = [('FINALTRAIN B0 ALS', FT / 'runs/B0_b10/ft_ALS_s0/attempt1/model/target_monitor/curve.jsonl', '#999999'),
            ('FINALTRAIN B173 주변 ALS', FT / 'runs/B173nb_b10/ft_ALS_s0/attempt1/model/target_monitor/curve.jsonl', '#bbbbbb'),
            ('씨앗 반복 B0 ALS', TU / 'runs/B0_b10/seed1_ALS/attempt1/model/target_monitor/curve.jsonl', '#555555'),
            ('가 ALS 시도 1 (메모리 부족)', TU / 'runs/campus/campus30k_ALS_s0/attempt1/model/target_monitor/curve.jsonl', '#d55e00'),
            ('다 ALS 칸0 (멈춤·저장)', TU / 'runs/cells/cells_ALS_s0/cell0/attempt1/model/target_monitor/curve.jsonl', COL[0]),
            ('다 ALS 칸1 (멈춤·저장)', TU / 'runs/cells/cells_ALS_s0/cell1/attempt1/model/target_monitor/curve.jsonl', COL[1])]
    fig, axes = plt.subplots(1, 2, figsize=(14, 5.5))
    rec = []
    for name, p, col in runs:
        if not Path(p).exists():
            continue
        it, el, g = curve(p)
        sp = np.diff(el) / np.maximum(np.diff(it), 1)
        axes[0].plot(it[1:], sp, color=col, lw=1, label=name)
        axes[1].plot(it, g / 1e6, color=col, lw=1, label=name)
        rec.append(dict(run=name, source=str(p), last_iteration=int(it[-1]), last_gaussians=int(g[-1]), elapsed_at_1_s=float(el[0]),
                        elapsed_last_s=float(el[-1]), s_per_it_last_1000=float((el[-1] - el[max(0, len(el) - 11)]) / max(1, it[-1] - it[max(0, len(it) - 11)]))))
    axes[0].set(yscale='log', xlabel='반복', ylabel='반복당 초 (100회 평균)', title='반복당 시간'); axes[0].grid(alpha=.3)
    axes[1].set(xlabel='반복', ylabel='가우시안 수 (백만)', title='가우시안 수'); axes[1].grid(alpha=.3)
    axes[1].legend(fontsize=8)
    fig.tight_layout(); fig.savefig(out / 'iteration_time_curves.png', dpi=200, facecolor='white'); plt.close(fig)
    dump(out / 'iteration_time_curves.json', dict(at=now(), runs=rec, scientific_verdict=None))
    dump(D / 'tables/iteration_time.json', dict(rows=rec, scientific_verdict=None))
    print('CELL_FIGS_DONE', flush=True)


if __name__ == '__main__':
    main()
