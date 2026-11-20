"""PHD-MAIN-BASE151-v1 order 5.2 qualitative figures not drawn by b151_figs.py (GTJUDGE environment, gt_cpu; /gtjudge = OUT/gt, /b151 = OUT ro).
Rules are those of PHD-MAIN-TRAINUNIT-v2 tu2_qual.py (GTJUDGE colours: white |s| <= tau, blue s < -tau, red s > tau, grey no surface;
three views (top, two obliques) of the GTJUDGE section ROI +-2 m, z range from the reference rows of the ROI, the same for every result).

  python b151_qual.py geom <site> <prior> <run>   # 4.1 scene: one mesh, three views -> /gtjudge/figs_b151/_parts
  python b151_qual.py join <site> <prior>         # mesh views of every run of the prior side by side + tau maps (b151_figs scenes) side by side
  python b151_qual.py dist <prior>                # per method: building completeness / accuracy distributions, four cases + scene (t42_buildings)
  python b151_qual.py top5 <prior> <run>          # the five buildings (rule below): this run's mesh, three views of the building box +-2 m
  python b151_qual.py top5join <prior>            # per building: every run's views side by side + one photo
Top five rule (order 5.2): buildings outside the three evaluation regions (JUDGECHECK-v2 group != 'experiment') with >= 2,000 GT points of
the prior; rank by max - min over the methods of the scene completeness (t42_buildings, 완전성_장면 전체), largest first.
Photo rule: among the training views of the building's cell units (/gtjudge/views/<unit>.json), the view whose projection of the building GT
centre is nearest to the image centre (all eight box corners in front of the camera). GT is used for colouring, the ROI and the photo choice only.
A run without a mesh or score is written as '없음'. scientific_verdict: null
"""
import gc
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from scipy.spatial import cKDTree  # noqa: E402

sys.path.insert(0, '/repo/scripts/phd/main_gtjudge_v1')
from inherited import O, dump, now, sha  # noqa: E402
from geometry_add1 import read_surface  # noqa: E402

for f in ['/fonts/NotoSansCJK-Regular.ttc', '/fonts/NotoSerifCJK-Regular.ttc']:
    if Path(f).exists():
        font_manager.fontManager.addfont(f)
        plt.rcParams['font.family'] = font_manager.FontProperties(fname=f).get_name()
        break
plt.rcParams['axes.unicode_minus'] = False

FIG = O / 'figs_b151'
PARTS = FIG / '_parts'
G = Path('/ph/main_gtjudge_v1/PHD-MAIN-GTJUDGE-v1/scenes')
IMG = Path('/ph/main_trainunit_v1/PHD-MAIN-TRAINUNIT-v1/scenes/campus/images')
JC2_BLD = Path('/ph/main_judgecheck_v2/PHD-MAIN-JUDGECHECK-v2/stage0/buildings.json')
VIEWS = [(90, -90), (35, -55), (35, 125)]
RUNS = {'ALS': [('2DGS', 'b151_2DGS_s0'), ('GeoGS', 'b151_GeoGS_ALS_s0'), ('CDGS', 'b151_CDGS_ALS_s0'), ('LGDM', 'b151_LGDM_ALS')],
        'LoD2': [('2DGS', 'b151_2DGS_s0'), ('GeoGS', 'b151_GeoGS_LoD2_s0'), ('CDGS', 'b151_CDGS_LoD2_s0'), ('LGDM', 'b151_LGDM_LoD2')]}
CASES = ['두 자료 모두 유효', '사전정보 오류', '영상 깊이 오류', '영상 깊이 결측', '장면 전체']
LEG = '흰색 τ 안 / 파랑 −τ보다 작음 / 빨강 +τ보다 큼 / 회색 면 없음'


def colors(s, tau):
    out = np.full(len(s), '#ffffff', dtype='U8')
    out[s < -tau] = '#2166ac'; out[s > tau] = '#b2182b'; out[~np.isfinite(s)] = '#999999'
    return out


def save(fig, path, meta, sources, dpi=150):
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path.with_suffix('.png'), dpi=dpi, facecolor='white'); plt.close(fig)
    dump(path.with_suffix('.json'), dict(at=now(), **meta, dpi=dpi, crs='EPSG:25832; local XY = EPSG:25832 - [690953, 5336071]',
         sources=[dict(path=str(x), sha256=sha(x)) for x in sources if Path(x).exists()], script_sha256=sha(__file__), scientific_verdict=None))


def views_png(tri, cc, lo, hi, zlo, zhi, title, out):
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    fig = plt.figure(figsize=(5.5, 14))
    for i, (elev, azim) in enumerate(VIEWS):
        ax = fig.add_subplot(3, 1, i + 1, projection='3d')
        if len(tri):
            ax.add_collection3d(Poly3DCollection(tri, facecolors=cc, edgecolors='none', rasterized=True))
        ax.view_init(elev, azim)
        ax.set(xlim=(lo[0], hi[0]), ylim=(lo[1], hi[1]), zlim=(zlo, zhi), title=f'{title} · 시점 {i + 1}')
        ax.set_box_aspect((hi[0] - lo[0], hi[1] - lo[1], zhi - zlo))
        ax.tick_params(labelsize=6)
        if i == 0:
            ax.set_zticks([])
    fig.subplots_adjust(top=.96, hspace=.1)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=200, facecolor='white'); plt.close(fig)


def crop(V, F, lo, hi):
    mid = V[F].mean(1)
    keep = ((mid[:, :2] >= lo) & (mid[:, :2] <= hi)).all(1)
    return V[F[keep]]


def geom(site, prior, run):
    d = O / 'scenes' / f'{site}__{prior}' / 'distances'
    tag = f'{site}__{prior}__{run}'
    if not (d / f'{run}.npz').exists():
        dump(PARTS / f'{tag}.json', dict(at=now(), site=site, prior=prior, run=run, status='없음 (채점 결과 없음)', scientific_verdict=None))
        print('GEOM none', tag, flush=True); return
    meta = json.loads((d / f'{run}.json').read_text())
    sec = json.loads((G / f'{site}__{prior}' / 'section.json').read_text())
    ends = np.array([sec['start'], sec['end']])[:, :2]; lo = ends.min(0) - 2; hi = ends.max(0) + 2
    V, F = read_surface(meta['mesh']); nf = int(len(F))
    tri = crop(V, F, lo, hi); del V, F; gc.collect()
    zs = np.load(d / f'{run}_samples.npz'); z = np.load(d / f'{run}.npz')
    Ps = zs['xyz'] if 'xyz' in zs.files else zs['sample_xyz']
    P = np.load(O / 'scenes' / f'{site}__{prior}' / 'rows.npz')['xyz']
    roi = ((P[:, :2] >= lo) & (P[:, :2] <= hi)).all(1)
    zlo, zhi = float(P[roi, 2].min()) - 1., float(P[roi, 2].max()) + 1.
    cc = []
    if len(tri):
        ii = cKDTree(Ps).query(tri.mean(1), workers=4)[1]; cc = colors(z['sample_s'][ii], z['sample_tau'][ii])
    views_png(tri, cc, lo, hi, zlo, zhi, run, PARTS / f'{tag}_views.png')
    dump(PARTS / f'{tag}.json', dict(at=now(), site=site, prior=prior, run=run, status='있음', mesh=meta['mesh'], mesh_faces=nf, roi_faces=int(len(tri)),
         roi=[lo.tolist(), hi.tolist()], z_range_from_reference=[zlo, zhi], camera_angles=VIEWS, section=str(G / f'{site}__{prior}' / 'section.json'),
         colour_rule='nearest accuracy sample of the result (distances/<run>_samples.npz, sample_s, sample_tau)', scientific_verdict=None))
    print('GEOM', tag, len(tri), flush=True)


def join(site, prior):
    import matplotlib.image as mpimg
    runs = RUNS[prior]
    # (1) mesh views side by side
    fig, axes = plt.subplots(1, len(runs), figsize=(5.5 * len(runs), 14.5))
    parts = {}
    for ax, (m, run) in zip(axes, runs):
        ax.set_axis_off()
        j = PARTS / f'{site}__{prior}__{run}.json'
        parts[run] = json.loads(j.read_text()) if j.exists() else dict(status='없음 (그리지 않음)')
        p = PARTS / f'{site}__{prior}__{run}_views.png'
        if parts[run].get('status') == '있음' and p.exists():
            ax.imshow(mpimg.imread(p)); ax.set_title(f'{m} · {run}', fontsize=13)
        else:
            ax.text(.5, .5, f'{m}\n{parts[run].get("status")}', ha='center', va='center', transform=ax.transAxes, fontsize=13)
    fig.suptitle(f'{site} · {prior} 참값 · 결과 메시 세 시점 (GTJUDGE 단면 자리 ±2 m, z 범위는 참값으로 같게) · {LEG}', fontsize=14)
    fig.subplots_adjust(top=.95, wspace=.02, left=.01, right=.99, bottom=.01)
    save(fig, FIG / 'scenes_join' / f'{site}__{prior}__mesh_views', dict(site=site, prior=prior, runs=parts, camera_angles=VIEWS),
         [PARTS / f'{site}__{prior}__{r}_views.png' for _, r in runs], dpi=110)
    # (2) tau maps (b151_figs scenes, this task's 2 x 2 runs) side by side
    fig, axes = plt.subplots(len(runs), 1, figsize=(14, 6.8 * len(runs)))
    used = {}
    for ax, (m, run) in zip(axes, runs):
        ax.set_axis_off()
        p = FIG / 'scenes' / f'{site}__{prior}__{run}.png'
        used[run] = '있음' if p.exists() else '없음'
        if p.exists():
            ax.imshow(mpimg.imread(p))
        else:
            ax.text(.5, .5, f'{m} · {run}\n없음', ha='center', va='center', transform=ax.transAxes, fontsize=13)
    fig.suptitle(f'{site} · {prior} 참값 · 방법별 참값 점 오차 지도 (왼쪽 s, 오른쪽 τ 안 비율; b151_figs.py scenes)', fontsize=13)
    fig.subplots_adjust(top=.97, hspace=.02, left=.01, right=.99, bottom=.01)
    save(fig, FIG / 'scenes_join' / f'{site}__{prior}__tau_maps', dict(site=site, prior=prior, runs=used),
         [FIG / 'scenes' / f'{site}__{prior}__{r}.png' for _, r in runs], dpi=110)
    print('JOIN', site, prior, flush=True)


def t42_buildings(prior):
    rows = json.loads((O / 'tables_b151' / 't42_buildings.json').read_text())['rows']
    return [r for r in rows if r['prior'] == prior]


def dist(prior):
    rows = t42_buildings(prior)
    methods = [m for m, _ in RUNS[prior]]
    fig, axes = plt.subplots(2, len(CASES), figsize=(4.2 * len(CASES), 8.5), sharey=True)
    counts = {}
    for i, (key, lab) in enumerate([('완전성', '완전성 %'), ('정확성', '정확성 %')]):
        for j, c in enumerate(CASES):
            ax = axes[i, j]
            data, names = [], []
            for m in methods:
                v = [r[f'{key}_{c}'] for r in rows if r['method'] == m and r.get(f'{key}_{c}') is not None]
                data.append(v); names.append(m); counts[f'{key}_{c}_{m}'] = len(v)
            ax.boxplot([d if d else [np.nan] for d in data], labels=names, showfliers=False)
            for k, d in enumerate(data):
                if d:
                    x = k + 1 + (np.random.default_rng(k).random(len(d)) - .5) * .35
                    ax.scatter(x, d, s=5, color='#333333', alpha=.5, zorder=3)
            ax.set_title(f'{c}', fontsize=10)
            if j == 0:
                ax.set_ylabel(lab)
            ax.set_ylim(-2, 102)
    fig.suptitle(f'151동 · {prior} 참값 · 건물별 완전성(위)과 정확성(아래)의 분포 (점 = 건물, 상자 = 사분위, 값이 없는 건물은 빠짐; t42_buildings)', fontsize=12)
    fig.subplots_adjust(top=.9, hspace=.25, wspace=.05, left=.05, right=.99)
    save(fig, FIG / 'dist' / f'buildings__{prior}', dict(prior=prior, methods=methods, cases=CASES, buildings_drawn=counts,
         rule='one value per building and case from t42_buildings (n_gt of the case > 0)'), [O / 'tables_b151' / 't42_buildings.json'])
    print('DIST', prior, flush=True)


def pick(prior):
    rows = t42_buildings(prior)
    methods = [m for m, _ in RUNS[prior]]
    by = {}
    for r in rows:
        if r['group'] == 'experiment' or (r.get('n_gt_장면 전체') or 0) < 2000 or r.get('완전성_장면 전체') is None:
            continue
        by.setdefault(r['building'], {})[r['method']] = r['완전성_장면 전체']
    cand = [(max(v.values()) - min(v.values()), b, v) for b, v in by.items() if all(m in v for m in methods)]
    cand.sort(key=lambda t: (-t[0], t[1]))
    return [dict(building=b, spread_pp=s, values=v) for s, b, v in cand[:5]], len(cand)


def building_box(prior, name):
    g = np.load(Path('/b151/gt') / f'gt151_{prior}.npz')
    sel = g['building'] == name
    P = g['xyz'][sel]
    cell = int(np.bincount(g['building_cell'][sel]).argmax())
    return P, P[:, :2].min(0) - 2, P[:, :2].max(0) + 2, float(P[:, 2].min()) - 1, float(P[:, 2].max()) + 1, cell


def layout():
    return json.loads((O / 'units/layout.json').read_text())['units']


def units_of(cell, lo, hi):
    return [u['unit'] for u in layout() if u['cell'] == cell and (np.array(u['rect_min']) <= hi).all() and (np.array(u['rect_max']) >= lo).all()]


def top5(prior, run):
    picks, _ = pick(prior)
    P_ = 'ALS' if run.split('_')[1] == '2DGS' else run.split('_')[2]
    sm = O / 'score151' / f'{run}__{prior}' / 'samples.npz'
    S = np.load(sm) if sm.exists() else None
    for k, pk in enumerate(picks):
        name = pk['building']; tag = f'{prior}__{k + 1}_{name}__{run}'
        P, lo, hi, zlo, zhi, cell = building_box(prior, name)
        tris, meshes = [], []
        for u in units_of(cell, lo, hi):
            mp = O / 'meshes' / f'{u}__{P_}__{run}' / 'final.ply'
            if mp.exists():
                V, F = read_surface(mp); tris.append(crop(V, F, lo, hi)); meshes.append(str(mp)); del V, F; gc.collect()
        tri = np.concatenate(tris) if tris else np.zeros((0, 3, 3))
        if S is None or not meshes:
            dump(PARTS / 'top5' / f'{tag}.json', dict(at=now(), prior=prior, run=run, building=name, status='없음 (메시 또는 채점 없음)', scientific_verdict=None))
            continue
        x = S['sample_xyz']; inb = ((x[:, :2] >= lo) & (x[:, :2] <= hi)).all(1)
        cc = []
        if len(tri) and inb.any():
            ii = cKDTree(x[inb]).query(tri.mean(1), workers=4)[1]
            cc = colors(S['sample_s'][inb][ii], S['sample_tau'][inb][ii])
        elif len(tri):
            cc = np.full(len(tri), '#999999', dtype='U8')
        views_png(tri, cc, lo, hi, zlo, zhi, run, PARTS / 'top5' / f'{tag}_views.png')
        dump(PARTS / 'top5' / f'{tag}.json', dict(at=now(), prior=prior, run=run, building=name, cell=cell, status='있음', meshes=meshes,
             box=[lo.tolist(), hi.tolist()], z_range_from_reference=[zlo, zhi], faces=int(len(tri)), samples_in_box=int(inb.sum()),
             colour_rule='nearest accuracy sample of the run (score151 samples.npz) inside the box', camera_angles=VIEWS, scientific_verdict=None))
        print('TOP5', tag, len(tri), flush=True)


def photo(prior, name, P, lo, hi, zlo, zhi, cell):
    c = np.r_[P.mean(0)]
    corners = np.array([[x, y, z] for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (zlo, zhi)])
    best = None
    for u in units_of(cell, lo, hi):
        for v in json.loads((O / 'views' / f'{u}.json').read_text())['views']:
            if v.get('virtual'):
                continue
            K, W2C = np.array(v['K']), np.array(v['W2C'])
            q = (W2C[:3, :3] @ corners.T).T + W2C[:3, 3]
            if (q[:, 2] <= 0).any():
                continue
            pc = W2C[:3, :3] @ c + W2C[:3, 3]; uv = (K @ pc)[:2] / pc[2]
            d = float(np.hypot(uv[0] - v['width'] / 2, uv[1] - v['height'] / 2))
            if best is None or d < best[0]:
                best = (d, v, u)
    return best


def top5join(prior):
    import matplotlib.image as mpimg
    from matplotlib.patches import Polygon
    picks, ncand = pick(prior)
    runs = RUNS[prior]
    for k, pk in enumerate(picks):
        name = pk['building']
        P, lo, hi, zlo, zhi, cell = building_box(prior, name)
        fig, axes = plt.subplots(1, len(runs) + 1, figsize=(5.5 * len(runs) + 9, 14.5), gridspec_kw=dict(width_ratios=[1] * len(runs) + [1.7]))
        parts = {}
        for ax, (m, run) in zip(axes, runs):
            ax.set_axis_off()
            tag = f'{prior}__{k + 1}_{name}__{run}'
            j = PARTS / 'top5' / f'{tag}.json'
            parts[run] = json.loads(j.read_text()) if j.exists() else dict(status='없음 (그리지 않음)')
            p = PARTS / 'top5' / f'{tag}_views.png'
            if parts[run].get('status') == '있음' and p.exists():
                ax.imshow(mpimg.imread(p)); ax.set_title(f'{m} · 완전성 {pk["values"][m]:.1f} %', fontsize=13)
            else:
                ax.text(.5, .5, f'{m}\n{parts[run].get("status")}', ha='center', va='center', transform=ax.transAxes, fontsize=13)
        ax = axes[-1]; ax.set_axis_off()
        b = photo(prior, name, P, lo, hi, zlo, zhi, cell)
        ph = dict(status='없음 (상자가 다 보이는 학습 영상 없음)')
        if b is not None:
            d, v, u = b
            ip = IMG / f'{v["name"]}.jpg'
            if ip.exists():
                im = mpimg.imread(ip); sx = im.shape[1] / v['width']; sy = im.shape[0] / v['height']
                K, W2C = np.array(v['K']), np.array(v['W2C'])
                ring = np.array([[lo[0], lo[1]], [hi[0], lo[1]], [hi[0], hi[1]], [lo[0], hi[1]]])
                q = (W2C[:3, :3] @ np.c_[ring, np.full(4, zhi - 1)].T).T + W2C[:3, 3]
                uv = (K @ q.T).T; uv = uv[:, :2] / uv[:, 2:3] * [sx, sy]
                ax.imshow(im); ax.add_patch(Polygon(uv, closed=True, fill=False, ec='#ffcc00', lw=2))
                ax.set_title(f'사진 {v["name"]} (단위 {u}, 노란 선 = 건물 상자의 지붕 높이 테두리)', fontsize=11)
                ph = dict(status='있음', image=str(ip), image_sha256=sha(ip), view=v['name'], unit=u, centre_offset_px=d)
            else:
                ph = dict(status=f'없음 (영상 파일 없음 {ip})', view=v['name'])
        if ph['status'] != '있음':
            ax.text(.5, .5, f'사진\n{ph["status"]}', ha='center', va='center', transform=ax.transAxes, fontsize=13)
        fig.suptitle(f'{prior} 참값 · 방법 사이 장면 전체 완전성 차이 {k + 1}위 {name} (최대 − 최소 {pk["spread_pp"]:.1f} %p, 참값 점 {len(P):,}) · 상자 ±2 m · {LEG}', fontsize=14)
        fig.subplots_adjust(top=.95, wspace=.02, left=.01, right=.99, bottom=.01)
        save(fig, FIG / 'top5' / f'{prior}__{k + 1}_{name}', dict(prior=prior, rank=k + 1, building=name, spread_pp=pk['spread_pp'], completeness_scene=pk['values'],
             candidates=ncand, rule='group != experiment, GT >= 2000, max - min of 완전성_장면 전체 over the four methods', runs=parts, photo=ph,
             photo_rule='training view of the cell units with all box corners in front, building GT centre nearest the image centre'),
             [O / 'tables_b151' / 't42_buildings.json'] + [PARTS / 'top5' / f'{prior}__{k + 1}_{name}__{r}_views.png' for _, r in runs], dpi=100)
        print('TOP5JOIN', prior, k + 1, name, flush=True)


if __name__ == '__main__':
    a = sys.argv[1:]
    dict(geom=geom, join=join, dist=dist, top5=top5, top5join=top5join)[a[0]](*a[1:])
