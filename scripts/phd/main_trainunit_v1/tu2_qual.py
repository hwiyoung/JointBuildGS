"""PHD-MAIN-TRAINUNIT-v2 order 5.2 qualitative figures (run2_cpu.sh), the v1 tu_figures rules (GTJUDGE colors, map_ax, multiview,
section_segments) split so that one container reads one site x plan mesh (order 5.2: the v1 figure container died at 32 GiB).
Plans (ALS, all with the elongation filter): 건물단위 s0 ef_s0, 건물단위 s1 ef_s1, 전체 campusef30k_ALS_s0, 넷 cellsef_ALS_s0, 아홉 cells9ef_ALS_s0.

  python tu2_qual.py tau  <site>          # tau in/out maps of the reference rows, plans side by side, 넷 and 아홉 original cell boundaries
  python tu2_qual.py geom <site> <plan>   # one mesh: three views (top, two obliques) in the GTJUDGE section ROI (+-2 m) and the
                                          #   section lines across the nearest 넷 / 아홉 boundary at the box -> figures/_parts
  python tu2_qual.py join <site>          # mesh views side by side; one section figure per boundary plan (넷, 아홉) with every plan
A missing plan (no score yet) is written as '없음' in the figure json. Reference rows are used for colouring/figures only.
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
from tu2_stop import plt_ko  # noqa: E402

plt = plt_ko()
from matplotlib.collections import LineCollection  # noqa: E402

TU1 = Path('/tu1')
G = PH / 'main_gtjudge_v1/PHD-MAIN-GTJUDGE-v1'
PLANS = [('건물단위_s0', 'ef_s0'), ('건물단위_s1', 'ef_s1'), ('전체', 'campusef30k_ALS_s0'), ('넷', 'cellsef_ALS_s0'), ('아홉', 'cells9ef_ALS_s0')]
COL = {'건물단위_s0': '#4B2E8A', '건물단위_s1': '#999999', '전체': '#009e73', '넷': '#e69f00', '아홉': '#d55e00'}
BCELLS = {'넷': TU1 / 'cells/cells.json', '아홉': TU / 'cells/cells.json'}
BCOL = {'넷': '#00a0a0', '아홉': '#c000c0'}
VIEWS = [(90, -90), (35, -55), (35, 125)]
PARTS = D / 'figures/_parts'


def root(site):
    return TU / 'gt/scenes' / f'{site}__ALS'


def mesh_path(m):
    """/gtjudge/... of a score json: the v2 mirror first, then the v1 payload (ef_s0, ef_s1, cellsef were meshed by v1)."""
    assert m.startswith('/gtjudge/'), m
    for base in [TU / 'gt', TU1 / 'gt']:
        p = Path(str(base) + m[len('/gtjudge'):])
        if p.exists():
            return str(p)
    raise FileNotFoundError(m)


def have(site):
    return [(l, m) for l, m in PLANS if (root(site) / 'distances' / f'{m}.npz').exists()]


def save(fig, name, meta, sources, dpi=200):
    p = D / 'figures' / name
    p.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(p.with_suffix('.png'), dpi=dpi, facecolor='white')
    plt.close(fig)
    dump(p.with_suffix('.json'), dict(at=now(), **meta, dpi=dpi, crs='EPSG:25832; local XY = EPSG:25832 - [690953, 5336071]',
         sources=[dict(path=str(x), sha256=sha(x)) for x in sources if Path(x).exists()], script_sha256=sha(__file__), scientific_verdict=None))


def boundary_lines(ax, lo, hi):
    for name, cj in BCELLS.items():
        for k, sg in enumerate(json.loads(cj.read_text())['boundaries']):
            a = np.clip(np.array(sg['lo']), lo - 5, hi + 5); b = np.clip(np.array(sg['hi']), lo - 5, hi + 5)
            ax.plot([a[0], b[0]], [a[1], b[1]], color=BCOL[name], lw=1.0, ls='--', label=f'{name} 원래 칸 경계' if k == 0 else None)


def tau(site):
    cfg()
    r = root(site)
    row = loadz(r / 'rows.npz', ['xyz', 'row_tau_m'])
    P, t = row['xyz'], row['row_tau_m']
    lo, hi = P[:, :2].min(0), P[:, :2].max(0)
    hv = have(site)
    fig, axes = plt.subplots(1, len(PLANS), figsize=(6.2 * len(PLANS), 7.6), squeeze=False)
    fig.subplots_adjust(bottom=.2, top=.86, wspace=.25)
    srcs, info = [r / 'rows.npz'], []
    for ax, (label, m) in zip(axes[0], PLANS):
        if (label, m) not in hv:
            ax.text(.5, .5, f'{label}\n없음 (채점 결과 없음)', ha='center', va='center', transform=ax.transAxes); ax.set_axis_off()
            info.append(dict(plan=label, family=m, status='없음'))
            continue
        s = loadz(r / 'distances' / f'{m}.npz', ['row_s'])['row_s']
        within = np.isfinite(s) & (abs(s) <= t)
        gf.map_ax(ax, P, gf.colors(s, t), f'{label} · {m}\nτ 안 {100 * within.mean():.1f} %')
        boundary_lines(ax, lo, hi)
        ax.set(xlim=(lo[0] - 2, hi[0] + 2), ylim=(lo[1] - 2, hi[1] + 2))
        gf.legend(ax, gf.DIST)
        srcs.append(r / 'distances' / f'{m}.npz')
        info.append(dict(plan=label, family=m, status='있음', tau_within_pct=100 * float(within.mean()), rows=int(len(s))))
    axes[0][0].legend(loc='upper left', fontsize=7)
    fig.suptitle(f'{site} · 항공 LiDAR · 참값 점의 τ 안/밖 (법선 측정선 거리) · 점선 = 원래 칸 경계 (청록 넷, 자주 아홉)')
    save(fig, f'{site}_v2_tau_maps', dict(plans=info), srcs)
    print('TAU', site, flush=True)


def sections(site):
    """Per boundary plan: a 24 m section perpendicular to the nearest original boundary of that plan at the box (v1 rule)."""
    P = loadz(root(site) / 'rows.npz', ['xyz'])['xyz']
    out = {}
    for name, cj in BCELLS.items():
        rel = next(x for x in json.loads(cj.read_text())['evaluation_boxes'] if x['site'] == site)
        sg = rel['nearest'][0]['segment']
        c = (np.array(rel['box_min']) + np.array(rel['box_max'])) / 2
        if sg['axis'] == 'x':
            x0 = sg['at']; ys = P[np.abs(P[:, 0] - x0) < 1., 1]; y0 = float(np.median(ys)) if len(ys) else float(c[1])
            start, end = [x0 - 12, y0], [x0 + 12, y0]
        else:
            y0 = sg['at']; xs = P[np.abs(P[:, 1] - y0) < 1., 0]; x0 = float(np.median(xs)) if len(xs) else float(c[0])
            start, end = [x0, y0 - 12], [x0, y0 + 12]
        out[name] = dict(section=dict(start=start, end=end, half_width=.6), boundary=sg, box_distance_m=rel['nearest_boundary_distance_m'],
                         crosses_box=rel['boundary_crosses_box'])
    return out


def geom(site, plan):
    cfg()
    m = dict(PLANS)[plan]
    r = root(site)
    if not (r / 'distances' / f'{m}.npz').exists():
        dump(PARTS / f'{site}_{plan}.json', dict(at=now(), site=site, plan=plan, family=m, status='없음 (채점 결과 없음)', scientific_verdict=None))
        print('GEOM none', site, plan, flush=True)
        return
    meta = json.loads((r / 'distances' / f'{m}.json').read_text())
    mp = mesh_path(meta['mesh'])
    V, F = read_surface(mp)
    secs = sections(site)
    seg = {name: np.asarray(section_segments(V, F, s['section'])) for name, s in secs.items()}
    sec = json.loads((G / 'scenes' / f'{site}__ALS' / 'section.json').read_text())
    ends = np.array([sec['start'], sec['end']]); rlo = ends.min(0) - 2; rhi = ends.max(0) + 2
    mid = V[F].mean(1); keep = ((mid[:, :2] >= rlo) & (mid[:, :2] <= rhi)).all(1); tri = V[F[keep]]
    nfaces = int(len(F)); del V, F, mid; gc.collect()
    Ps = loadz(r / 'distances' / f'{m}_samples.npz', ['xyz'])['xyz']
    z = loadz(r / 'distances' / f'{m}.npz', ['sample_s', 'sample_tau'])
    # common z range of the ROI from the reference rows (figure only), the same for every plan
    P = loadz(r / 'rows.npz', ['xyz'])['xyz']
    inroi = ((P[:, :2] >= rlo) & (P[:, :2] <= rhi)).all(1)
    zlo, zhi = float(P[inroi, 2].min()) - 1., float(P[inroi, 2].max()) + 1.
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    fig = plt.figure(figsize=(5.5, 14))
    if len(tri):
        ii = cKDTree(Ps).query(tri.mean(1), workers=4)[1]; cc = gf.colors(z['sample_s'][ii], z['sample_tau'][ii])
    for i, (elev, azim) in enumerate(VIEWS):
        ax = fig.add_subplot(3, 1, i + 1, projection='3d')
        if len(tri):
            ax.add_collection3d(Poly3DCollection(tri, facecolors=cc, edgecolors='none', rasterized=True))
        ax.view_init(elev, azim)
        ax.set(xlim=(rlo[0], rhi[0]), ylim=(rlo[1], rhi[1]), zlim=(zlo, zhi), title=f'{plan} · 시점 {i + 1}')
        ax.set_box_aspect((rhi[0] - rlo[0], rhi[1] - rlo[1], zhi - zlo))
        ax.tick_params(labelsize=6)
        if i == 0:
            ax.set_zticks([])
    fig.subplots_adjust(top=.96, hspace=.1)
    PARTS.mkdir(parents=True, exist_ok=True)
    fig.savefig(PARTS / f'{site}_{plan}_views.png', dpi=200, facecolor='white'); plt.close(fig)
    np.savez_compressed(PARTS / f'{site}_{plan}_sections.npz', **{k: v for k, v in seg.items()})
    dump(PARTS / f'{site}_{plan}.json', dict(at=now(), site=site, plan=plan, family=m, status='있음', mesh=mp, mesh_faces=nfaces, roi_faces=int(len(tri)),
         roi=[rlo.tolist(), rhi.tolist()], z_range_from_reference=[zlo, zhi], sections=secs, section_segments={k: int(len(v)) for k, v in seg.items()},
         camera_angles=VIEWS, scientific_verdict=None))
    print('GEOM', site, plan, len(tri), flush=True)


def join(site):
    cfg()
    import matplotlib.image as mpimg
    parts = {l: json.loads((PARTS / f'{site}_{l}.json').read_text()) if (PARTS / f'{site}_{l}.json').exists() else dict(status='없음 (그리지 않음)') for l, _ in PLANS}
    # (1) mesh views side by side
    fig, axes = plt.subplots(1, len(PLANS), figsize=(5.5 * len(PLANS), 14.5))
    for ax, (l, m) in zip(axes, PLANS):
        ax.set_axis_off()
        p = PARTS / f'{site}_{l}_views.png'
        if parts[l].get('status') == '있음' and p.exists():
            ax.imshow(mpimg.imread(p)); ax.set_title(f'{l} · {m}', fontsize=13)
        else:
            ax.text(.5, .5, f'{l}\n{parts[l].get("status")}', ha='center', va='center', transform=ax.transAxes, fontsize=13)
    sec = json.loads((G / 'scenes' / f'{site}__ALS' / 'section.json').read_text())
    fig.suptitle(f'{site}__ALS · 결과 메시 세 시점 (GTJUDGE 단면 자리 ±2 m, z 범위는 참값으로 같게) · 흰색 τ 안 / 파랑 음 / 빨강 양 / 회색 면 없음', fontsize=14)
    fig.subplots_adjust(top=.95, wspace=.02, left=.01, right=.99, bottom=.01)
    save(fig, f'{site}_v2_mesh_views', dict(plans={l: parts[l] for l, _ in PLANS}, roi='GTJUDGE section.json +-2 m', section=sec, camera_angles=VIEWS),
         [PARTS / f'{site}_{l}_views.png' for l, _ in PLANS], dpi=110)
    # (2) sections across the nearest 넷 / 아홉 boundary
    secs = sections(site)
    P = loadz(root(site) / 'rows.npz', ['xyz'])['xyz']
    for name, s in secs.items():
        fig, ax = plt.subplots(figsize=(13, 6)); fig.subplots_adjust(bottom=.22, top=.86)
        drawn = []
        for l, m in PLANS:
            f = PARTS / f'{site}_{l}_sections.npz'
            if parts[l].get('status') != '있음' or not f.exists():
                continue
            seg = np.load(f)[name]
            ax.add_collection(LineCollection(seg, colors=COL[l], lw=1.6 if l in (name, '건물단위_s0') else 1.0, label=l))
            drawn.append(l)
        pp = section_points(P, s['section'])
        ax.scatter(pp[:, 0], pp[:, 1], s=4, color='black', label='참값', zorder=5)
        ax.axvline(12, color=BCOL[name], ls='--', lw=1, label=f'{name} 원래 칸 경계')
        ax.axvspan(10, 14, color=BCOL[name], alpha=.08, label='경계 띠 ±2 m')
        ax.autoscale_view(); ax.set(xlim=(0, 24), xlabel='단면 거리 (m)', ylabel='지역 높이 (m)')
        ax.legend(loc='upper center', bbox_to_anchor=(.5, -.13), ncol=8, frameon=False)
        sg = s['boundary']
        fig.suptitle(f'{site}__ALS · {name} 칸 경계({sg["axis"]} = {sg["at"]:.1f} m)를 가로지르는 단면 (24 m, 폭 ±0.6 m) · 상자와 경계 거리 {s["box_distance_m"]:.1f} m'
                     + ('' if len(drawn) == len(PLANS) else f' · 없음: {", ".join(l for l, _ in PLANS if l not in drawn)}'))
        save(fig, f'{site}_v2_section_{name}경계', dict(plans_drawn=drawn, plans_missing=[l for l, _ in PLANS if l not in drawn], **s),
             [root(site) / 'rows.npz'] + [PARTS / f'{site}_{l}_sections.npz' for l in drawn])
    print('JOIN', site, flush=True)


if __name__ == '__main__':
    dict(tau=tau, geom=geom, join=join)[sys.argv[1]](*sys.argv[2:])
