"""Figures of PHD-MAIN-TRAINUNIT-v1 with the GTJUDGE figure functions (colors, map_ax, multiview rule).

  python tu_figures.py <site> <prior> [ef]
(addendum 16: with 'ef' the filter families of ALS: 기준 ef_s0, 씨앗 반복 ef_s1, 가 campusef30k, 나 campusef120k, 다 cellsef; names <stem>_ef_*)
(1) tau in/out maps of all reference rows per run (기준, 씨앗 반복, 가, 다) with the original cell boundaries;
(2) three-view result meshes (top, two obliques) of the same runs in the GTJUDGE section ROI (±2 m), faces coloured by the
    nearest saved result sample's normal-line distance vs tau (GTJUDGE multiview rule);
(3) 판 다: a section across the cell boundary nearest to the box centre (perpendicular, 24 m, half width 0.6 m).
"""
import gc
import sys

sys.path.insert(0, '/repo/scripts/phd/main_gtjudge_v1')
import common as gcommon
from tu_common import *

gcommon.O = TU / 'gt'
gcommon.C = Path('/repo/configs/phd/main_gtjudge_v1')
gcommon.D = D
import figures as gf  # noqa: E402
from geometry_add1 import read_surface, section_segments, section_points  # noqa: E402
from scipy.spatial import cKDTree  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.collections import LineCollection  # noqa: E402

G = PH / 'main_gtjudge_v1/PHD-MAIN-GTJUDGE-v1'


def mesh_path(m):
    if m.startswith('/gtjudge/'):
        return str(TU / 'gt') + m[len('/gtjudge'):]
    if m.startswith('/out/'):
        return str(RS) + m[len('/out'):]
    return m


EFRUNS = [('기준', 'ef_s0'), ('씨앗 반복', 'ef_s1'), ('가', 'campusef30k_ALS_s0'), ('나', 'campusef120k_ALS_s0'), ('다', 'cellsef_ALS_s0')]


def runs(prior, ef=False):
    if ef:
        return EFRUNS   # addendum 16
    return [('기준', 'FINALTRAIN_30000'), ('씨앗 반복', 'seed1_s1'), ('가', f'campus30k_{prior}_s0'), ('다', f'cells_{prior}_s0')]


def boundary_lines(ax, cells, lo, hi):
    for sg in cells['boundaries']:
        a, b = np.array(sg['lo']), np.array(sg['hi'])
        a = np.clip(a, lo - 5, hi + 5); b = np.clip(b, lo - 5, hi + 5)
        ax.plot([a[0], b[0]], [a[1], b[1]], color='#00a0a0', lw=1.0, ls='--')


def save(fig, name, meta, sources):
    p = D / 'figures' / name
    p.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(p.with_suffix('.png'), dpi=200, facecolor='white')
    plt.close(fig)
    dump(p.with_suffix('.json'), dict(at=now(), **meta, dpi=200, crs='EPSG:25832; inherited local XY [690953,5336071]',
         sources=[dict(path=str(x), sha256=sha(x)) for x in sources if Path(x).exists()], script_sha256=sha(__file__), scientific_verdict=None))


def main(site, prior, ef=''):
    cfg()
    stem = f'{site}__{prior}'
    tag = stem + ('_ef' if ef else '')
    root = TU / 'gt/scenes' / stem
    row = loadz(root / 'rows.npz', ['xyz', 'row_tau_m'])
    P, tau = row['xyz'], row['row_tau_m']
    cells = json.loads((TU / 'cells/cells.json').read_text())
    have = [(l, m) for l, m in runs(prior, bool(ef)) if (root / 'distances' / f'{m}.npz').exists()]
    lo, hi = P[:, :2].min(0), P[:, :2].max(0)
    # (1) tau maps
    fig, axes = plt.subplots(1, len(have), figsize=(6.2 * len(have), 7.2), squeeze=False)
    fig.subplots_adjust(bottom=.2, top=.86, wspace=.25)
    srcs = [root / 'rows.npz']
    for ax, (label, m) in zip(axes[0], have):
        z = loadz(root / 'distances' / f'{m}.npz', ['row_s'])
        s = z['row_s']
        within = np.isfinite(s) & (abs(s) <= tau)
        gf.map_ax(ax, P, gf.colors(s, tau), f'{label} · {m}\nτ 안 {100 * within.mean():.1f} %')
        boundary_lines(ax, cells, lo, hi)
        ax.set(xlim=(lo[0] - 2, hi[0] + 2), ylim=(lo[1] - 2, hi[1] + 2))
        gf.legend(ax, gf.DIST)
        srcs.append(root / 'distances' / f'{m}.npz')
    fig.suptitle(f'{site} · {prior} · 참값 점의 τ 안/밖 (법선 측정선 거리) · 청록 점선 = 판 다의 원래 칸 경계')
    save(fig, f'{tag}_tau_maps', dict(runs=have), srcs)
    # (2) three views in the GTJUDGE section ROI
    sec = json.loads((G / 'scenes' / stem / 'section.json').read_text())
    if sec['status'] == 'PASS':
        from mpl_toolkits.mplot3d.art3d import Poly3DCollection
        ends = np.array([sec['start'], sec['end']]); rlo = ends.min(0) - 2; rhi = ends.max(0) + 2
        fig = plt.figure(figsize=(5.5 * len(have), 14)); zl = []; axs = []
        for j, (label, m) in enumerate(have):
            meta = json.loads((root / 'distances' / f'{m}.json').read_text())
            V, F = read_surface(mesh_path(meta['mesh']))
            mid = V[F].mean(1); keep = ((mid[:, :2] >= rlo) & (mid[:, :2] <= rhi)).all(1); tri = V[F[keep]]; del V, F, mid; gc.collect()
            if m == 'FINALTRAIN_30000':
                Ps = loadz(gcommon.score_dir(site, prior, m) / 'points.npz', ['sample_xyz'])['sample_xyz']
            else:
                Ps = loadz(root / 'distances' / f'{m}_samples.npz', ['xyz'])['xyz']
            z = loadz(root / 'distances' / f'{m}.npz', ['sample_s', 'sample_tau'])
            if len(tri):
                ii = cKDTree(Ps).query(tri.mean(1), workers=4)[1]; cc = gf.colors(z['sample_s'][ii], z['sample_tau'][ii])
                zl += [float(tri[:, :, 2].min()), float(tri[:, :, 2].max())]
            for i, (elev, azim) in enumerate([(90, -90), (35, -55), (35, 125)]):
                ax = fig.add_subplot(3, len(have), i * len(have) + j + 1, projection='3d')
                if len(tri):
                    ax.add_collection3d(Poly3DCollection(tri, facecolors=cc, edgecolors='none', rasterized=True))
                ax.view_init(elev, azim); ax.set(xlim=(rlo[0], rhi[0]), ylim=(rlo[1], rhi[1]), title=f'{label} · 시점 {i + 1}'); axs.append(ax)
            del tri, Ps, z; gc.collect()
        if zl:
            for ax in axs:
                ax.set_zlim(min(zl) - .2, max(zl) + .2); ax.set_box_aspect((rhi[0] - rlo[0], rhi[1] - rlo[1], max(zl) - min(zl) + .4))
        fig.suptitle(f'{stem} · 결과 메시 (GTJUDGE 단면 자리 ±2 m) · 흰색 τ 안 / 파랑 음 / 빨강 양 / 회색 면 없음')
        fig.subplots_adjust(top=.95, wspace=.12, hspace=.12)
        save(fig, f'{tag}_mesh_views', dict(runs=have, roi='GTJUDGE section.json ±2 m', section=sec, camera_angles=[[90, -90], [35, -55], [35, 125]]), srcs)
    # (3) section across the nearest cell boundary
    rel = next(r for r in cells['evaluation_boxes'] if r['site'] == site)
    sg = rel['nearest'][0]['segment']
    c = (np.array(rel['box_min']) + np.array(rel['box_max'])) / 2
    if sg['axis'] == 'x':
        x0 = sg['at']; ys = P[np.abs(P[:, 0] - x0) < 1., 1]
        y0 = float(np.median(ys)) if len(ys) else c[1]
        start, end = [x0 - 12, y0], [x0 + 12, y0]
    else:
        y0 = sg['at']; xs = P[np.abs(P[:, 1] - y0) < 1., 0]
        x0 = float(np.median(xs)) if len(xs) else c[0]
        start, end = [x0, y0 - 12], [x0, y0 + 12]
    bsec = dict(start=start, end=end, half_width=.6)
    fig, ax = plt.subplots(figsize=(13, 6)); fig.subplots_adjust(bottom=.22, top=.86)
    for (label, m), col in zip(have, ['#4B2E8A', '#999999', '#009e73', '#e69f00', '#d55e00'] if ef else ['#4B2E8A', '#999999', '#009e73', '#d55e00']):
        meta = json.loads((root / 'distances' / f'{m}.json').read_text())
        V, F = read_surface(mesh_path(meta['mesh']))
        ax.add_collection(LineCollection(section_segments(V, F, bsec), colors=col, lw=1, label=label)); del V, F; gc.collect()
    pp = section_points(P, bsec)
    ax.scatter(pp[:, 0], pp[:, 1], s=4, color='black', label='참값', zorder=5)
    ax.axvline(12, color='#00a0a0', ls='--', lw=1, label='원래 칸 경계')
    ax.axvspan(10, 14, color='#00a0a0', alpha=.08, label='경계 띠 ±2 m')
    ax.autoscale_view(); ax.set(xlim=(0, 24), xlabel='단면 거리 (m)', ylabel='지역 높이 (m)')
    ax.legend(loc='upper center', bbox_to_anchor=(.5, -.13), ncol=6, frameon=False)
    fig.suptitle(f'{stem} · 칸 경계({sg["axis"]} = {sg["at"]:.1f} m)를 가로지르는 단면 · 상자와 경계 거리 {rel["nearest_boundary_distance_m"]:.1f} m')
    save(fig, f'{tag}_cell_boundary_section', dict(runs=have, section=bsec, boundary=sg), srcs)
    print('FIGURES_DONE', stem, flush=True)


if __name__ == '__main__':
    main(*sys.argv[1:])
