"""Locked representative sections and candidate-opacity 3D captures, CPU only."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import to_rgba
from matplotlib.lines import Line2D
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
import numpy as np
from plot_results import setup, write
from input_audit import sha
from result_io import save

OUT, DOC = Path('/out'), Path('/docs')
COLORS = ['#bc8425', '#286c9e']
NAMES = {'B173_wing': 'B173 날개 · 영상이 맞고 뒤에 있음',
         'R1_stairs': 'R1 계단 지붕 · 영상이 맞고 앞에 있음',
         'leaf_flat_roof': '낙엽 지붕 요청의 대체 자리 · 사전 정보가 맞고 뒤에 있음'}


def main():
    setup(); records = []
    reps = json.loads((DOC / 'representatives_v1.json').read_text())['rows']
    dest = DOC / 'figures/representatives'; dest.mkdir(parents=True, exist_ok=True)
    for rep in reps:
        if rep['selection'] is None:
            records.append(dict(id=rep['id'], status=rep['status'], files=[])); continue
        unit = rep['unit']; roots = {sh: OUT / 'runs' / f'cp_wrong_sh{sh}_{unit}' for sh in [3, 0]}
        if not all((p / 'complete.json').exists() for p in roots.values()):
            records.append(dict(id=rep['id'], status='WAIT_TRAINING', files=[])); continue
        with np.load(OUT / 'places' / (unit + '.npz')) as z: d = {k: z[k] for k in z.files}
        ids = np.flatnonzero(np.isin(d['point_id'], rep['selection']['point_ids']))
        seed = np.flatnonzero(d['point_id'] == rep['selection']['seed_point_id'])[0]
        origin = d['centre'][seed]; frame = np.stack([d['tangent1'][seed], d['tangent2'][seed], d['normal'][seed]])
        centre = d['centre'][ids]; normal = d['normal'][ids]
        local = (centre - origin) @ frame.T
        mv = (centre + normal * d['mvs_p'][ids, None] - origin) @ frame.T
        gt = (centre + normal * d['gt_p'][ids, None] - origin) @ frame.T
        central = np.abs(local[:, 1]) <= .251
        assert central.any(), rep['id']
        snapshots = {}
        for degree, root in roots.items():
            for step in [0, 500, 3000]:
                with np.load(root / f'candidate_{step}.npz') as z:
                    snapshots[degree, step] = z['opacity'].reshape(-1, 2, 4)[ids]
        order = np.argsort(local[central, 0]); selected = np.flatnonzero(central)[order]
        ylo = min(local[:, 2].min(), mv[:, 2].min(), gt[:, 2].min()) - .35
        yhi = max(local[:, 2].max(), mv[:, 2].max(), gt[:, 2].max()) + .35
        fig, axes = plt.subplots(2, 3, figsize=(15, 8), sharex=True, sharey=True)
        for row, degree in enumerate([3, 0]):
            for col, step in enumerate([0, 500, 3000]):
                ax = axes[row, col]
                ax.plot(local[selected, 0], local[selected, 2], color='#555555', linewidth=1, label='사전 정보 면')
                ax.scatter(mv[selected, 0], mv[selected, 2], marker='x', color=COLORS[1], s=40)
                ax.scatter(gt[selected, 0], gt[selected, 2], marker='D', color='#151515', facecolors='none', s=40)
                alpha = snapshots[degree, step].mean(2)
                for i in selected:
                    for kind, points in enumerate([local, mv]):
                        x, h = points[i, [0, 2]]
                        ax.plot([x - .19, x + .19], [h, h], color=COLORS[kind],
                                linewidth=8, alpha=float(alpha[i, kind]), solid_capstyle='butt')
                        ax.text(x, h + max(.07, .035 * (yhi - ylo)), f'{alpha[i, kind]:.2f}', fontsize=9, ha='center', color=COLORS[kind])
                ax.set_title(f'SH{degree} · {step:,}회'); ax.set_ylim(ylo, yhi)
                ax.grid(alpha=.15); ax.set_xlabel('접선 u (m)')
                if col == 0: ax.set_ylabel('기준 법선 방향 높이 h (m)')
        handles = [Line2D([], [], color=COLORS[0], lw=6, label='사전 정보 후보'), Line2D([], [], color=COLORS[1], lw=6, label='영상 후보'),
                   Line2D([], [], color='#555555', lw=1, label='사전 정보 면'), Line2D([], [], color=COLORS[1], marker='x', ls='', label='MVS'),
                   Line2D([], [], color='#151515', marker='D', markerfacecolor='none', ls='', label='참값 중앙값')]
        fig.legend(handles=handles, loc='upper center', bbox_to_anchor=(.5, 1), ncol=5, frameon=False)
        fig.suptitle(NAMES[rep['id']] + ' — 출발 틀림', y=1.06, fontsize=18)
        fig.text(.5, -.02, f'선의 진하기·숫자: 후보별 4개 가우시안의 평균 불투명도. 고정 대표 {len(ids)}점 중 |v| ≤ 0.251m 단면 {len(selected)}점.\n표시값은 소수 둘째 자리 반올림이며, 결과 분류는 반올림 전 값과 0.5를 비교함.', ha='center', fontsize=11)
        fig.tight_layout(rect=[0, .02, 1, .94]); path = dest / (rep['id'] + '_sections'); write(fig, path)
        files = [path.name + '.png']
        files += draw_3d(rep, d, ids, origin, frame, local, mv, gt, snapshots, dest)
        records.append(dict(id=rep['id'], status='COMPLETE', unit=unit, files=files,
            section_point_ids=d['point_id'][ids[selected]].tolist(), section_rule='abs(v)<=0.251m relative to locked seed tangent frame',
            snapshots={f'sh{degree}_{step}': sha(root / f'candidate_{step}.npz') for degree, root in roots.items() for step in [0, 500, 3000]}))
    save(dest / 'index.json', dict(representatives=records, script_sha256=sha(__file__), scientific_verdict=None))
    print([(r['id'], r['status']) for r in records])


def draw_3d(rep, d, ids, origin, frame, local, mv, gt, snapshots, dest):
    unit = rep['unit']
    with np.load(OUT / 'scenes' / unit / 'candidate_geometry.npz') as z:
        centres = z['means'].reshape(-1, 2, 4, 3)[ids]
    angle = np.linspace(0, 2 * np.pi, 33)[:-1]
    polygons = []
    for i, point in enumerate(ids):
        for kind in range(2):
            for k in range(4):
                ellipse = centres[i, kind, k] + .25 * (np.cos(angle)[:, None] * d['tangent1'][point] + np.sin(angle)[:, None] * d['tangent2'][point])
                polygons.append((ellipse - origin) @ frame.T)
    vertices = np.concatenate(polygons + [gt]); low = vertices.min(0) - .2; high = vertices.max(0) + .2
    views = [(25, -65), (25, 35), (55, 145)]; files = []
    for degree in [3, 0]:
        fig = plt.figure(figsize=(15, 16))
        for i, (elev, azim) in enumerate(views):
            for j, step in enumerate([0, 500, 3000]):
                ax = fig.add_subplot(3, 3, i * 3 + j + 1, projection='3d')
                opacity = snapshots[degree, step]
                facecolors = [to_rgba(COLORS[kind], float(opacity[p, kind, k])) for p in range(len(ids)) for kind in range(2) for k in range(4)]
                ax.add_collection3d(Poly3DCollection(polygons, facecolors=facecolors, edgecolors='none', zsort='average'))
                ax.scatter(gt[:, 0], gt[:, 1], gt[:, 2], color='#151515', marker='D', s=10, depthshade=False)
                ax.scatter(mv[:, 0], mv[:, 1], mv[:, 2], color=COLORS[1], marker='x', s=12, depthshade=False)
                ax.scatter(local[:, 0], local[:, 1], local[:, 2], color='#555555', marker='.', s=12, depthshade=False)
                ax.set_xlim(low[0], high[0]); ax.set_ylim(low[1], high[1]); ax.set_zlim(low[2], high[2])
                ax.set_box_aspect(high - low); ax.view_init(elev=elev, azim=azim)
                from matplotlib.ticker import MaxNLocator
                ax.xaxis.set_major_locator(MaxNLocator(nbins=3)); ax.yaxis.set_major_locator(MaxNLocator(nbins=3))
                ax.zaxis.set_major_locator(MaxNLocator(nbins=5))
                ax.set_xlabel('u (m)', labelpad=1); ax.set_ylabel('v (m)', labelpad=1); ax.set_zlabel('h (m)', labelpad=4)
                ax.tick_params(labelsize=9, pad=0); ax.set_title(f'{step:,}회 · 시점 {i + 1}', pad=10)
        fig.suptitle(NAMES[rep['id']] + f'\n출발 틀림 · SH{degree} · 후보 불투명도 3D', fontsize=17, y=.99)
        fig.text(.5, .015, '황색=사전 정보 후보 · 청색=영상 후보 · 검정 마름모=참값 중앙값. 면 진하기=가우시안별 불투명도.\n타원은 2σ 범위 표시이며 실제 렌더의 절단 경계가 아님. 고정 대표 자리 전체를 같은 축 범위로 표시.', ha='center', fontsize=11)
        fig.subplots_adjust(top=.91, bottom=.09, wspace=.12, hspace=.55)
        path = dest / f"{rep['id']}_3d_sh{degree}"; write(fig, path); files.append(path.name + '.png')
    return files


if __name__ == '__main__': main()
