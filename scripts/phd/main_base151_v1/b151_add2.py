"""PHD-MAIN-BASE151-v1 addendum 2 (2026-11-21): image make-up per cell / scene / building vs the flat roof s. No training, no new scoring:
reads campus poses, TRAINUNIT cells.json, building-unit view lists, gt151 and the 4.2 score rows. GTJUDGE environment (b151_post41.gt_cpu);
writes /gtjudge/add2 (= OUT/gt/add2).

  python b151_add2.py views    1-1 .. 1-4   per image height / tilt / group; cell lists by selection way; scenes; cell-3 roofs
  python b151_add2.py blds     1-5, 1-6     per building (flat roof GT >= 200): images seeing the roof by group, triangulation angle, s median
  python b151_add2.py figs     figures of 1-1 .. 1-6

Definitions
  height of an image = camera centre z - median z of the gt151 ALS rows in the original cell holding the camera centre (addendum 1, c_inputs)
  tilt of an image   = angle between the viewing axis and straight down (addendum 1)
  groups             = boundaries at the valleys of the campus distribution (see GROUPS)
  cell selection     = TRAINUNIT tu2_cells.partition rule, recomputed on the campus poses: position = centre in the expanded cell;
                       visibility = coverage of the 8 projected corners of the cell's projection box >= 25 % (coverage() / clip_polygon() copied
                       from tu_cells.py); checked against the counts in cells.json
  roof GT of a building = its gt151 ALS rows that are not wall; flat roof = not wall, n_z >= 0.985, case 0 (addendum 1)
  an image sees a roof  = at least half of up to 200 roof sample points (fixed seed) project inside the image with positive depth;
                          occlusion is not checked
  triangulation angle   = per roof sample point, the largest angle between two viewing rays of the images that see the point (inside, in front);
                          per building the median over its sample points
scientific_verdict: null
"""
import json
import struct
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, '/b151s')
from b151_add1 import CELLS, O, TU1, colmap_images, in_cell  # noqa: E402

A = O / 'add2'
SB = Path('/ph/main_baselines_v1/PHD-MAIN-BASELINES-v1')
CJ = json.loads((TU1 / 'cells/cells.json').read_text())
H_CUT, T_CUT = 45.0, 15.0
GROUPS = {'low_oblique': '낮고 비스듬', 'low_vertical': '낮고 수직', 'high_vertical': '높고 수직', 'high_oblique': '높고 비스듬'}
SITES = ['B173nb_b10', 'R1rep_b10', 'B0_b10']
NS = 200


def dump(p, d):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, 'item') else str(o)))


def table(name, rows, note):
    dump(A / f'{name}.json', dict(note=note, rows=rows, scientific_verdict=None))
    fields = list(dict.fromkeys(k for r in rows for k in r))
    fmt = lambda v: '없음' if v is None else (f'{v:.3f}' if isinstance(v, float) else str(v))
    with (A / f'{name}.md').open('w') as f:
        f.write(f'# {name}\n\n{note}\n\nscientific_verdict: null\n\n| ' + ' | '.join(fields) + ' |\n|' + '---|' * len(fields) + '\n')
        for r in rows:
            f.write('| ' + ' | '.join(fmt(r.get(k)).replace('|', '/') for k in fields) + ' |\n')
    print('TABLE', name, len(rows), flush=True)


def intrinsics():
    with open(TU1 / 'scenes/campus/scene_ALS/sparse/0/cameras.bin', 'rb') as f:
        n = struct.unpack('<Q', f.read(8))[0]
        assert n == 1, n
        _cid, model, W, H = struct.unpack('<iiQQ', f.read(24))
        assert model == 1, model          # PINHOLE
        fx, fy, cx, cy = struct.unpack('<4d', f.read(32))
    return dict(fx=fx, fy=fy, cx=cx, cy=cy, W=int(W), H=int(H))


def cams():
    K = intrinsics()
    im = colmap_images(TU1 / 'scenes/campus/scene_ALS/sparse/0/images.bin')
    out = {}
    for nm, (R, C) in im.items():
        out[nm] = dict(name=nm, R=R, C=C, W2C=np.c_[R, -R @ C], **K)
    return out


# ---- copied from scripts/phd/main_trainunit_v1/tu_cells.py (clip_polygon, coverage), cv2 convex hull replaced by an equal monotone-chain hull
def hull2d(p):
    p = sorted(map(tuple, p))
    if len(p) < 3:
        return np.array(p)
    cross = lambda o, a, b: (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lo, up = [], []
    for q in p:
        while len(lo) >= 2 and cross(lo[-2], lo[-1], q) <= 0:
            lo.pop()
        lo.append(q)
    for q in reversed(p):
        while len(up) >= 2 and cross(up[-2], up[-1], q) <= 0:
            up.pop()
        up.append(q)
    return np.array(lo[:-1] + up[:-1])


def clip_polygon(poly, W, H):
    def clip(pts, inside, inter):
        out = []
        for i in range(len(pts)):
            a, b = pts[i - 1], pts[i]
            ia, ib = inside(a), inside(b)
            if ib:
                if not ia:
                    out.append(inter(a, b))
                out.append(b)
            elif ia:
                out.append(inter(a, b))
        return out
    pts = [tuple(p) for p in poly]
    for axis, val, keep_ge in [(0, 0., True), (0, float(W), False), (1, 0., True), (1, float(H), False)]:
        if not pts:
            break
        inside = (lambda p, a=axis, v=val, g=keep_ge: p[a] >= v if g else p[a] <= v)

        def inter(p, q, a=axis, v=val):
            t = (v - p[a]) / (q[a] - p[a])
            return (p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1]))
        pts = clip(pts, inside, inter)
    if len(pts) < 3:
        return 0.
    x = np.array([p[0] for p in pts]); y = np.array([p[1] for p in pts])
    return float(0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))))


def coverage(cam, lo, hi):
    corners = np.array([[x, y, z] for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])], float)
    M = np.asarray(cam['W2C'], float)
    c = corners @ M[:3, :3].T + M[:3, 3]
    if (c[:, 2] <= 0).any():
        c = c[c[:, 2] > 0]
        if len(c) < 3:
            return 0.
    u = cam['fx'] * c[:, 0] / c[:, 2] + cam['cx']
    v = cam['fy'] * c[:, 1] / c[:, 2] + cam['cy']
    return clip_polygon(hull2d(np.c_[u, v]), cam['W'], cam['H']) / float(cam['W'] * cam['H'])
# ----


def project(cam, P):
    c = P @ cam['R'].T - cam['R'] @ cam['C']
    z = c[:, 2]
    with np.errstate(divide='ignore', invalid='ignore'):
        u = cam['fx'] * c[:, 0] / z + cam['cx']; v = cam['fy'] * c[:, 1] / z + cam['cy']
    return (z > 0) & (u >= 0) & (u < cam['W']) & (v >= 0) & (v < cam['H'])


def group(h, t):
    return ('low' if h < H_CUT else 'high') + ('_vertical' if t <= T_CUT else '_oblique')


def image_table(cm, g):
    sp = json.loads((TU1 / 'scenes/campus/split.json').read_text())
    gz = [float(np.median(g['xyz'][in_cell(g['xyz'][:, :2], k), 2])) for k in range(4)]
    rows = {}
    for part in ['train', 'test']:
        for nm in sp[part]:
            c = cm[nm]
            k = [k for k in range(4) if in_cell(c['C'][None, :2], k)[0]][0]
            h = float(c['C'][2] - gz[k]); t = float(np.degrees(np.arccos(np.clip(-c['R'][2][2], -1, 1))))
            rows[nm] = dict(name=nm, split=part, centre_cell=k, x=float(c['C'][0]), y=float(c['C'][1]), z=float(c['C'][2]),
                            height_m=h, tilt_deg=t, group=group(h, t))
    return rows, gz, sp


def cell_lists(cm, sp):
    out = []
    for c in CJ['cells']:
        elo, ehi = c['expanded_min'], c['expanded_max']
        pos = [nm for nm in sp['train'] if elo[0] <= cm[nm]['C'][0] < ehi[0] and elo[1] <= cm[nm]['C'][1] < ehi[1]]
        cov = {nm: coverage(cm[nm], c['projection_box_min'], c['projection_box_max']) for nm in sp['train'] if nm not in pos}
        # the lists used in training are cells.json 'images'; the recomputed position set must equal its count, visibility = the rest
        assert len(pos) == c['position_selected'] and set(pos) <= set(c['images']), c['id']
        vis = sorted(set(c['images']) - set(pos))
        assert len(vis) == c['visibility_added'], c['id']
        recomputed = [nm for nm, f in cov.items() if f >= .25]
        diff = sorted(set(recomputed) ^ set(vis))
        out.append(dict(cell=c['id'], position=pos, visibility=vis, coverage_others=cov,
                        recompute_differs=[dict(name=n, coverage=cov[n], in_cells_json=n in vis) for n in diff]))
    return out


def roof_samples(g, rng):
    """per building: up to NS roof (not wall) GT points of the ALS rows"""
    roof = ~g['wall']
    b = g['building']
    out = {}
    for nm in np.unique(b[roof]):
        idx = np.flatnonzero(roof & (b == nm))
        if len(idx) > NS:
            idx = np.sort(rng.choice(idx, NS, replace=False))
        out[nm] = idx
    return out


def views(_):
    g = dict(np.load(O / 'gt151_ALS.npz'))   # read once (NpzFile reads the array again on every access)
    cm = cams()
    rows, gz, sp = image_table(cm, g)
    G = list(GROUPS)
    # 1-1
    tr = [r for r in rows.values() if r['split'] == 'train']
    t11 = []
    for part, rs in [('train', tr), ('test', [r for r in rows.values() if r['split'] == 'test'])]:
        for gg in G:
            sel = [r for r in rs if r['group'] == gg]
            t11.append(dict(split=part, group=gg, group_ko=GROUPS[gg], images=len(sel),
                            height_median_m=float(np.median([r['height_m'] for r in sel])) if sel else None,
                            tilt_median_deg=float(np.median([r['tilt_deg'] for r in sel])) if sel else None,
                            **{f'centre_in_cell{k}': sum(r['centre_cell'] == k for r in sel) for k in range(4)}))
    table('a2_11_groups', t11, f'1-1: campus images by group. height = camera z - median gt151 ALS z of the original cell holding the camera centre '
          f'(cells 0-3: {", ".join(f"{z:.2f}" for z in gz)} m); tilt = angle of the viewing axis from straight down; boundaries at the valleys of the '
          f'training-image distribution: height {H_CUT} m (no image between 40 and 55 m), tilt {T_CUT} deg (fewest images in 10-15 deg)')
    table('a2_11_images', sorted(rows.values(), key=lambda r: r['name']), '1-1: every campus image (training 819, test 118)')
    # 1-2
    cl = cell_lists(cm, sp)
    t12 = []
    for c in cl:
        for way in ['position', 'visibility']:
            names = c[way]
            t12.append(dict(cell=c['cell'], way={'position': '위치로 고른 것', 'visibility': '투영 25 % 규칙으로 더한 것'}[way], images=len(names),
                            **{gg: sum(rows[n]['group'] == gg for n in names) for gg in G}))
        names = c['position'] + c['visibility']
        t12.append(dict(cell=c['cell'], way='합', images=len(names), **{gg: sum(rows[n]['group'] == gg for n in names) for gg in G}))
    diffs = [dict(cell=c['cell'], **d) for c in cl for d in c['recompute_differs']]
    table('a2_12_cells', t12, '1-2: training images of cells 0-3 by the way they were chosen (cells.json image lists = the lists used in training; position = '
          'camera centre in the expanded cell, recomputed, count equal to position_selected; visibility = the rest, count equal to visibility_added) and by group. '
          f'Recomputing the 25 % rule here differs from cells.json for {len(diffs)} image(s): ' + '; '.join(f"cell {d['cell']} {d['name']} coverage {d['coverage']:.5f} "
          f"in cells.json {d['in_cells_json']}" for d in diffs))
    # 1-3
    t13 = []
    for site in SITES:
        bu = json.loads((SB / 'runs' / site / 'imgonly_2dgs_s0/views.json').read_text())['train_names']
        eb = [e for e in CJ['evaluation_boxes'] if e['site'] == site][0]
        for cells in [[k] for k in eb['cells']] + ([eb['cells']] if len(eb['cells']) > 1 else []):
            cel = sorted(set().union(*[set(cl[k]['position'] + cl[k]['visibility']) for k in cells]))
            for part, names in [('공통', sorted(set(bu) & set(cel))), ('건물 단위에만', sorted(set(bu) - set(cel))), ('칸에만', sorted(set(cel) - set(bu)))]:
                t13.append(dict(scene=site, box_cells=str(eb['cells']), compared_cells='+'.join(map(str, cells)), building_unit_images=len(bu),
                                cell_images=len(cel), part=part, images=len(names), **{gg: sum(rows[n]['group'] == gg for n in names) for gg in G}))
    table('a2_13_scenes', t13, '1-3: building-unit training images (BASELINES imgonly_2dgs_s0 views.json train_names; GeoGS / CDGS used the same scene images) '
          'vs the training images of the cells the evaluation box touches (cells.json evaluation_boxes), by group')
    # 1-4
    rng = np.random.default_rng(0)
    rs = roof_samples(g, rng)
    bcell = {nm: int(np.bincount(g['building_cell'][idx][g['building_cell'][idx] >= 0]).argmax()) for nm, idx in rs.items()}
    c3 = [nm for nm in rs if bcell[nm] == 3]
    in3 = set(cl[3]['position'] + cl[3]['visibility'])
    t14, cov_rows = [], []
    for part in ['train', 'test']:
        for gg in G:
            names = [r['name'] for r in rows.values() if r['split'] == part and r['group'] == gg]
            seeing = [n for n in names if any(project(cm[n], g['xyz'][rs[b]]).mean() >= .5 for b in c3)]
            if part == 'train':
                miss = [n for n in seeing if n not in in3]
                for n in miss:
                    cov_rows.append(dict(name=n, group=gg, coverage_of_cell3_box=cl[3]['coverage_others'][n],
                                         cell3_roofs_seen=sum(project(cm[n], g['xyz'][rs[b]]).mean() >= .5 for b in c3)))
                t14.append(dict(split=part, group=gg, images=len(names), see_cell3_roof=len(seeing), in_cell3_list=len(seeing) - len(miss), missing=len(miss),
                                missing_coverage_median=float(np.median([cl[3]['coverage_others'][n] for n in miss])) if miss else None,
                                missing_coverage_p90=float(np.quantile([cl[3]['coverage_others'][n] for n in miss], .9)) if miss else None))
            else:
                t14.append(dict(split=part, group=gg, images=len(names), see_cell3_roof=len(seeing), in_cell3_list=None, missing=None))
    table('a2_14_cell3_roofs', t14, f'1-4: campus images that see the roof of at least one cell-3 building ({len(c3)} buildings; building cell = the cell of most of '
          'its GT rows; sees = half of up to 200 roof sample points inside the image in front, occlusion not checked); training images in / not in the cell-3 '
          'list; coverage = share of the image covered by the projected cell-3 box (the 25 % rule)')
    table('a2_14_missing', sorted(cov_rows, key=lambda r: -r['coverage_of_cell3_box']), '1-4: training images that see a cell-3 roof but are not in the cell-3 list')
    dump(A / 'state.json', dict(cell_lists={c['cell']: dict(position=c['position'], visibility=c['visibility']) for c in cl}, building_cell=bcell,
                                H_CUT=H_CUT, T_CUT=T_CUT, NS=NS))


def blds(_):
    from scipy.stats import spearmanr
    g = dict(np.load(O / 'gt151_ALS.npz'))   # read once (NpzFile reads the array again on every access)
    cm = cams()
    rows, _gz, _sp = image_table(cm, g)
    st = json.loads((A / 'state.json').read_text())
    lists = {int(k): v['position'] + v['visibility'] for k, v in st['cell_lists'].items()}
    rs = roof_samples(g, np.random.default_rng(0))
    flat = (~g['wall']) & (g['normal'][:, 2] >= .985) & (g['case'] == 0)
    S = {run: np.load(O / 'score151' / f'{run}__ALS' / 'rows.npz')['s_main'] for run in ['b151_2DGS_s0', 'b151_GeoGS_ALS_s0']}
    G = list(GROUPS)
    out = []
    for nm, idx in rs.items():
        fl = np.flatnonzero(flat & (g['building'] == nm))
        if len(fl) < 200:
            continue
        k = st['building_cell'][nm]
        P = g['xyz'][idx]
        inside = {n: project(cm[n], P) for n in lists[k]}
        seeing = [n for n, m in inside.items() if m.mean() >= .5]
        ang = []
        for j in range(len(P)):
            cs = [cm[n]['C'] for n, m in inside.items() if m[j]]
            if len(cs) < 2:
                ang.append(0.); continue
            d = np.array(cs) - P[j]; d /= np.linalg.norm(d, axis=1, keepdims=True)
            ang.append(float(np.degrees(np.arccos(np.clip((d @ d.T).min(), -1, 1)))))
        r = dict(building=nm, cell=k, flat_roof_gt=len(fl), roof_samples=len(idx), images_in_cell_list=len(lists[k]), see_roof_all=len(seeing),
                 **{f'see_{gg}': sum(rows[n]['group'] == gg for n in seeing) for gg in G}, triangulation_angle_median_deg=float(np.median(ang)))
        for run, s in S.items():
            v = s[fl]; f = np.isfinite(v)
            r[f's_median_{run}'] = float(np.median(v[f])) if f.any() else None
            r[f's_finite_{run}'] = int(f.sum())
        out.append(r)
    table('a2_15_buildings', sorted(out, key=lambda r: (r['cell'], r['building'])),
          '1-5 / 1-6: buildings with >= 200 flat roof GT rows (not wall, n_z >= 0.985, case 0, ALS GT); images of the building cell\'s training list that see '
          'the roof, by group; triangulation angle (median over roof samples of the largest angle between two rays); flat roof s median of the 4.2 score rows '
          '(finite s only; s_finite = how many)')
    cor = []
    for x in ['see_low_oblique', 'see_roof_all', 'triangulation_angle_median_deg']:
        for run in S:
            for cells in [[0], [1], [2], [3], [0, 1, 2, 3]]:
                sel = [r for r in out if r['cell'] in cells and r[f's_median_{run}'] is not None]
                if len(sel) < 3:
                    cor.append(dict(x=x, run=run, cells='+'.join(map(str, cells)), buildings=len(sel), spearman_rho=None, p=None)); continue
                rho, p = spearmanr([r[x] for r in sel], [r[f's_median_{run}'] for r in sel])
                cor.append(dict(x=x, run=run, cells='+'.join(map(str, cells)), buildings=len(sel),
                                spearman_rho=None if np.isnan(rho) else float(rho), p=None if np.isnan(p) else float(p)))
    table('a2_15_spearman', cor, '1-5 / 1-6: Spearman rank correlation of the building columns with the flat roof s median, per cell and all cells')


def figs(_):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    for f in Path('/fonts').rglob('NotoSansCJK*.ttc'):
        font_manager.fontManager.addfont(str(f))
    plt.rcParams['font.family'] = 'Noto Sans CJK JP'
    F = A / 'figures'; F.mkdir(parents=True, exist_ok=True)
    im = json.loads((A / 'a2_11_images.json').read_text())['rows']
    col = {'low_oblique': '#d95f02', 'low_vertical': '#7570b3', 'high_vertical': '#1b9e77', 'high_oblique': '#e7298a'}
    def save(fig, name, meta):
        fig.tight_layout(); fig.savefig(F / f'{name}.png', dpi=130, facecolor='white'); plt.close(fig)
        dump(F / f'{name}.json', dict(**meta, crs='EPSG:25832; local XY = EPSG:25832 - [690953, 5336071]', scientific_verdict=None))
    # 1-1 2D distribution
    fig, ax = plt.subplots(1, 3, figsize=(17, 5.2))
    tr = [r for r in im if r['split'] == 'train']
    h = np.array([r['height_m'] for r in tr]); t = np.array([r['tilt_deg'] for r in tr])
    hh = ax[0].hist2d(t, h, bins=[np.arange(0, 95, 5), np.arange(0, 90, 5)], cmap='Greys', cmin=1)
    fig.colorbar(hh[3], ax=ax[0], label='영상 수')
    for a in ax[:1]:
        a.axhline(H_CUT, color='r', lw=1); a.axvline(T_CUT, color='r', lw=1)
    ax[0].set_xlabel('기울기 (°, 0 = 수직 아래)'); ax[0].set_ylabel('지붕 위 높이 (m)'); ax[0].set_title('학습 영상 819장, 5 m × 5° 칸, 빨강 = 경계')
    ax[1].hist(h, bins=np.arange(0, 90, 2.5), color='0.4'); ax[1].axvline(H_CUT, color='r'); ax[1].set_xlabel('지붕 위 높이 (m)'); ax[1].set_ylabel('영상 수')
    ax[2].hist(t, bins=np.arange(0, 92.5, 2.5), color='0.4'); ax[2].axvline(T_CUT, color='r'); ax[2].set_xlabel('기울기 (°)')
    save(fig, 'a2_11_distribution', dict(item='1-1', H_CUT=H_CUT, T_CUT=T_CUT, images=len(tr)))
    # 1-1 map
    fig, ax = plt.subplots(figsize=(9, 9))
    for gg, c in col.items():
        s = [r for r in tr if r['group'] == gg]
        if s:
            ax.scatter([r['x'] for r in s], [r['y'] for r in s], s=7, c=c, label=f'{GROUPS[gg]} {len(s)}')
    for b in CJ['boundaries']:
        ax.plot([b['lo'][0], b['hi'][0]], [b['lo'][1], b['hi'][1]], 'k-', lw=1)
    for c in CJ['cells']:
        lo, hi = np.clip(c['original_min'], -500, 500), np.clip(c['original_max'], -500, 500)
        ax.text(*(np.clip((lo + hi) / 2, -150, 250)), f'칸 {c["id"]}', fontsize=14, alpha=.6)
    ax.set_xlim(-220, 260); ax.set_ylim(-240, 320); ax.set_aspect('equal'); ax.legend(loc='upper left'); ax.set_title('학습 영상 카메라 위치(무리별), 검은 선 = 칸 경계')
    save(fig, 'a2_11_map', dict(item='1-1', boundaries='cells.json boundaries (original cells)'))
    # 1-4 missing coverage
    ms = json.loads((A / 'a2_14_missing.json').read_text())['rows']
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for gg, c in col.items():
        v = [r['coverage_of_cell3_box'] for r in ms if r['group'] == gg]
        if v:
            ax.hist(v, bins=np.arange(0, .26, .01), color=c, alpha=.6, label=f'{GROUPS[gg]} {len(v)}')
    ax.axvline(.25, color='r'); ax.set_xlabel('칸 3 상자 투영이 영상을 덮는 몫'); ax.set_ylabel('영상 수'); ax.legend()
    ax.set_title('칸 3 지붕을 보지만 칸 3 목록에 없는 학습 영상')
    save(fig, 'a2_14_missing_coverage', dict(item='1-4', rule='25 % rule of tu2_cells'))
    # 1-5 / 1-6 scatter
    bl = json.loads((A / 'a2_15_buildings.json').read_text())['rows']
    cc = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728']
    for x, xl in [('see_low_oblique', '지붕을 보는 낮고 비스듬한 영상 수'), ('see_roof_all', '지붕을 보는 영상 수(전체)'),
                  ('triangulation_angle_median_deg', '가장 큰 교회각의 중앙값 (°)')]:
        fig, ax = plt.subplots(1, 2, figsize=(14, 5.5), sharey=True)
        for a, run in zip(ax, ['b151_2DGS_s0', 'b151_GeoGS_ALS_s0']):
            for k in range(4):
                s = [r for r in bl if r['cell'] == k and r[f's_median_{run}'] is not None]
                a.scatter([r[x] for r in s], [r[f's_median_{run}'] for r in s], s=18, c=cc[k], label=f'칸 {k} ({len(s)}동)')
            a.axhline(0, color='k', lw=.6); a.set_xlabel(xl); a.set_title(run); a.legend()
        ax[0].set_ylabel('평지붕 s 중앙값 (m, + = 위)')
        save(fig, f'a2_15_scatter__{x}', dict(item='1-5' if x == 'see_low_oblique' else '1-6', x=x, source='a2_15_buildings'))
    print('FIGS', flush=True)


if __name__ == '__main__':
    A.mkdir(parents=True, exist_ok=True)
    dict(views=views, blds=blds, figs=figs)[sys.argv[1]](sys.argv[2:])
