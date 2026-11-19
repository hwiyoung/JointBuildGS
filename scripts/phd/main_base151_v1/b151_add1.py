"""PHD-MAIN-BASE151-v1 addendum 1 (2026-11-19): why the cell-3 surfaces sit above the reference. Read-only on models, inputs, meshes and
scores; no training, no new scoring. Runs in the GTJUDGE environment (b151_post41.gt_cpu); writes /gtjudge/add1/ (= OUT/gt/add1).

  python b151_add1.py gauss    가-1  Gaussian centres (opacity >= 0.5) over flat roof GT points with case 0, cells 2 / 3 (+ R1 box)
  python b151_add1.py depth    가-2  rendered depth (the 4.2 unit renders) vs campus MVS depth and the prior depth, 20 training views per cell
  python b151_add1.py mesh     가-3  4.1 site mesh vs 4.2 unit mesh at the same GT points (site rows <-> gt151 rows by equal coordinates <= 1 mm)
  python b151_add1.py shape    나    s of the GT points vs x, y, height, slope; displacement fit; per building medians; bottom band
  python b151_add1.py prev     라    building-unit runs (2DGS_30000, GeoGS_30000) vs 2 x 2 on the same flat roof rows (B173nb, R1rep)
  python b151_add1.py inputs   다    per cell inputs (cameras, initial points, normalisation, merge, DA3) and cellsef_ALS_s0 cell 3
Definitions (fixed before computing):
  flat roof GT point = not wall, |n_z| >= 0.985 (slope <= 10 deg), case 0 (both data valid); normal oriented up (n_z > 0)
  signed distance of a Gaussian centre = (centre - nearest flat roof GT point (xy, <= 0.25 m, |dz| <= 3 m)) . n
  s of a GT point = the scorer's normal-line distance (score151 rows s_main / GTJUDGE site row_s), positive = surface above along n
  cells = TRAINUNIT cells.json original (unexpanded) cells
scientific_verdict: null
"""
import json
import sys
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

O = Path('/gtjudge')
A = O / 'add1'
B = Path('/b151')
TU1 = Path('/art/phase-payloads/phd/main_trainunit_v1/PHD-MAIN-TRAINUNIT-v1')
CELLS = json.loads((TU1 / 'cells/cells.json').read_text())['cells']
RUNS = {'b151_2DGS_s0': B / 'runs/b151_2DGS_s0/merged/point_cloud.ply',
        'b151_GeoGS_ALS_s0': B / 'runs/b151_GeoGS_ALS_s0/merged/point_cloud.ply',
        'b151_GeoGS_LoD2_s0': B / 'runs/b151_GeoGS_LoD2_s0/merged/point_cloud.ply',
        'b151_CDGS_ALS_s0': B / 'runs/b151_CDGS_ALS_s0/merged/point_cloud.ply',
        'b151_CDGS_LoD2_s0': B / 'runs/b151_CDGS_LoD2_s0/merged/point_cloud.ply',
        'cellsef_ALS_s0 (TRAINUNIT)': TU1 / 'runs/ef/cellsef_ALS_s0/merged/point_cloud.ply'}
FLAT_NZ = 0.985
R1BOX = None   # filled from the TRAINUNIT evaluation boxes


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


def in_cell(xy, k):
    c = CELLS[k]
    lo, hi = np.array(c['original_min']), np.array(c['original_max'])
    return np.all((xy >= lo) & (xy < hi), axis=1)


def box_of(site):
    b = [e for e in json.loads((TU1 / 'cells/cells.json').read_text())['evaluation_boxes'] if e['site'] == site][0]
    return np.array(b['box_min']), np.array(b['box_max'])


def read_ply(p, names):
    with open(p, 'rb') as f:
        head = b''
        while not head.endswith(b'end_header\n'):
            head += f.readline()
        lines = head.decode().splitlines()
        n = int([l for l in lines if l.startswith('element vertex')][0].split()[-1])
        iv = [i for i, l in enumerate(lines) if l.startswith('element vertex')][0]
        pl = []
        for l in lines[iv + 1:]:
            if l.startswith('element'):
                break
            if l.startswith('property'):
                pl.append(l.split())
        dt = np.dtype([(x[2], {'float': '<f4', 'float32': '<f4', 'double': '<f8', 'float64': '<f8', 'int': '<i4', 'int32': '<i4', 'uint': '<u4', 'uint32': '<u4', 'uchar': 'u1', 'uint8': 'u1', 'short': '<i2', 'ushort': '<u2', 'char': 'i1'}[x[1]]) for x in pl])
        a = np.fromfile(f, dtype=dt, count=n)
    return {k: a[k] for k in names if k in a.dtype.names}, [x[2] for x in pl]


def site_map(g, site, site_xyz):
    """gt151 rows of a site <-> the site rows of GTJUDGE by equal coordinates (<= 1 mm); returns (gt151 index, site row index)"""
    m = np.flatnonzero(g['site'] == site)
    d, i = cKDTree(site_xyz).query(g['xyz'][m], k=1, distance_upper_bound=1e-3)
    ok = np.isfinite(d)
    return m[ok], i[ok]


def q(v, p):
    return float(np.percentile(v, p)) if len(v) else None


def stats(v):
    v = np.asarray(v, float)
    v = v[np.isfinite(v)]
    if not len(v):
        return dict(n=0, median=None, p10=None, p90=None, nmad=None)
    med = float(np.median(v))
    return dict(n=int(len(v)), median=med, p10=q(v, 10), p90=q(v, 90), nmad=float(1.4826 * np.median(np.abs(v - med))))


def gt(prior='ALS'):
    g = np.load(O / f'gt151_{prior}.npz')
    n = g['normal'] * np.sign(g['normal'][:, 2:3] + 1e-12)
    return g, n


def flat_mask(g, n):
    return (~g['wall'].astype(bool)) & (np.abs(n[:, 2]) >= FLAT_NZ) & (g['case'] == 0)


# ------------------------------------------------------------------------------------------------ 가-1
def gauss(_):
    rows = []
    for prior in ['ALS', 'LoD2']:
        g, n = gt(prior)
        fm = flat_mask(g, n)
        P, N = g['xyz'][fm], n[fm]
        tree = cKDTree(P[:, :2])
        regions = [(f'cell{k}', None, k) for k in [0, 1, 2, 3]] + [('R1rep_b10 box', box_of('R1rep_b10'), None)]
        for run, ply in RUNS.items():
            if prior == 'LoD2' and run in ('b151_GeoGS_ALS_s0', 'b151_CDGS_ALS_s0', 'cellsef_ALS_s0 (TRAINUNIT)'):
                continue
            if prior == 'ALS' and run in ('b151_GeoGS_LoD2_s0', 'b151_CDGS_LoD2_s0'):
                continue
            if not ply.exists():
                rows.append(dict(run=run, prior_gt=prior, region='-', status='없음 (model not written yet)'))
                continue
            v, props = read_ply(ply, ['x', 'y', 'z', 'opacity'])
            xyz = np.stack([v['x'], v['y'], v['z']], 1).astype(np.float64)
            op = 1 / (1 + np.exp(-v['opacity'].astype(np.float64)))
            keep = op >= 0.5
            d, i = tree.query(xyz[keep, :2], k=1, distance_upper_bound=0.25)
            ok = np.isfinite(d)
            gi = np.flatnonzero(keep)[ok]
            j = i[ok]
            sd = np.einsum('ij,ij->i', xyz[gi] - P[j], N[j])
            near = np.abs(xyz[gi, 2] - P[j, 2]) <= 3
            gi, j, sd = gi[near], j[near], sd[near]
            for name, box, k in regions:
                m = in_cell(xyz[gi, :2], k) if k is not None else np.all((xyz[gi, :2] >= box[0][:2]) & (xyz[gi, :2] <= box[1][:2]), 1)
                rows.append(dict(run=run, prior_gt=prior, region=name, status='있음', gaussians_total=int(len(xyz)),
                                 gaussians_opacity_ge_05=int(keep.sum()), **{f'gauss_{a}': b for a, b in stats(sd[m]).items()},
                                 flat_gt_points_hit=int(len(np.unique(j[m])))))
            print('GAUSS', run, prior, flush=True)
    table('a1_gaussians', rows, '가-1: signed distance of Gaussian centres (opacity >= 0.5) to the flat roof GT surface (case 0, |n_z| >= 0.985, '
          'nearest GT point in xy <= 0.25 m, |dz| <= 3 m), per original cell and the R1rep_b10 box; m, positive = above')


# ------------------------------------------------------------------------------------------------ 가-2
def read_depth_bin(p):
    data = Path(p).read_bytes()
    off = 0
    for _ in range(3):
        off = data.find(b'&', off, 100) + 1
    w, h, c = map(int, data[:off].decode('ascii').split('&')[:3])
    return np.frombuffer(data, dtype='<f4', offset=off, count=w * h).reshape((w, h), order='F').T.copy()


MVSD = Path('/art/phase-payloads/phd/main_widen0_v2/PHD-MAIN-WIDEN0-v2/mvs/full/stereo/depth_maps')


def depth(argv):
    """20 training views per cell, evenly spaced over the cell's training list among the views the 4.2 unit renders hold. Per pixel the
    render of the unit whose box holds the MVS point (xy, z inside the box) is used. Building pixels: the MVS point lies within 0.25 m (xy) of
    a GT point of a building (any case) and within 3 m in z (GT used only to pick pixels for this diagnosis). Depth = camera z (the render npz,
    the MVS map and the prior map all hold camera-z depth; checked on the prior map vs the MVS map in flat ground pixels: see 'convention')."""
    runs = argv or ['b151_2DGS_s0', 'b151_GeoGS_ALS_s0', 'b151_LGDM_ALS']
    g, n = gt('ALS')
    tree = cKDTree(g['xyz'][:, :2])
    split = {k: json.loads((TU1 / 'scenes' / f'cell{k}' / 'split.json').read_text()) for k in range(4)}
    rows, perview = [], []
    for run in runs:
        prior = 'LoD2' if 'LoD2' in run else 'ALS'
        units = sorted(p for p in (O / 'renders').glob(f'c*__{prior}__{run}') if (p / 'receipt.json').exists())
        rec = {u.name: json.loads((u / 'receipt.json').read_text()) for u in units}
        for k in [2, 3]:
            train = split[k]['train'] if isinstance(split[k], dict) and 'train' in split[k] else split[k]
            train = [t.rsplit('.', 1)[0] for t in train]
            have = {}
            for un, r in rec.items():
                if not un.startswith(f'c{k}_'):
                    continue
                for v in r['views']:
                    have.setdefault(v['name'], []).append((un, v))
            cand = [t for t in train if t in have]
            pick = [cand[int(i)] for i in np.linspace(0, len(cand) - 1, 20).round().astype(int)] if len(cand) >= 20 else cand
            dm_all, dp_all = [], []
            for name in pick:
                mvs = read_depth_bin(MVSD / f'{name}.JPG.geometric.bin')
                mvs = np.where(np.isfinite(mvs) & (mvs > 0), mvs, np.nan)
                pr = np.load(B / 'priordepth' / prior / f'cell{k}' / f'{name}.npy') if (B / 'priordepth' / prior / f'cell{k}' / f'{name}.npy').exists() else None
                un, v = have[name][0]
                K, W2C = np.array(v['K']), np.array(v['W2C'])
                hh, ww = mvs.shape
                yy, xx = np.mgrid[0:hh, 0:ww]
                ok = np.isfinite(mvs)
                Xc = np.stack([(xx[ok] - K[0, 2]) / K[0, 0] * mvs[ok], (yy[ok] - K[1, 2]) / K[1, 1] * mvs[ok], mvs[ok]], 1)
                C2W = np.linalg.inv(W2C)
                Xw = Xc @ C2W[:3, :3].T + C2W[:3, 3]
                d, i = tree.query(Xw[:, :2], k=1, distance_upper_bound=0.25)
                bld = np.isfinite(d)
                bld[bld] = np.abs(Xw[bld, 2] - g['xyz'][i[bld], 2]) <= 3
                ren = np.full(ok.sum(), np.nan)
                for un2, v2 in have[name]:
                    bx = np.array(rec[un2]['box'])
                    inb = np.all((Xw >= bx[0]) & (Xw <= bx[1]), 1) & np.isnan(ren)
                    z = np.load(O / 'renders' / un2 / v2['file'])['depth'][ok]
                    ren[inb] = np.where(z[inb] > 0, z[inb], np.nan)
                m = bld & np.isfinite(ren)
                dm = ren[m] - mvs[ok][m]
                dp = (ren[m] - pr[ok][m]) if pr is not None else np.array([])
                dm_all.append(dm)
                dp_all.append(dp[np.isfinite(dp)])
                perview.append(dict(run=run, cell=k, view=name, units=len(have[name]), building_pixels=int(m.sum()),
                                    render_minus_mvs_median=stats(dm)['median'], render_minus_prior_median=stats(dp)['median'] if len(dp) else None))
            dm_all, dp_all = np.concatenate(dm_all) if dm_all else np.array([]), np.concatenate(dp_all) if dp_all else np.array([])
            sm, sp = stats(dm_all), stats(dp_all)
            rows.append(dict(run=run, cell=k, views=len(pick), views_available=len(cand), building_pixels=sm['n'],
                             render_minus_mvs_median=sm['median'], render_minus_mvs_nmad=sm['nmad'], render_minus_mvs_p10=sm['p10'], render_minus_mvs_p90=sm['p90'],
                             render_minus_prior_median=sp['median'], render_minus_prior_nmad=sp['nmad'], prior_pixels=sp['n']))
            print('DEPTH', run, k, sm, flush=True)
    table('a2_render_depth', rows, '가-2: camera-z depth difference (m) on building pixels, method render (4.2 unit renders) minus campus MVS and minus the '
          'prior depth map (OUT/priordepth); negative = the render is nearer to the camera (surface higher for nadir views)')
    table('a2_render_depth_views', perview, '가-2 per view')


# ------------------------------------------------------------------------------------------------ 가-3
def mesh(_):
    rows = []
    for prior, runs in [('ALS', ['b151_2DGS_s0', 'b151_GeoGS_ALS_s0', 'b151_LGDM_ALS']), ('LoD2', ['b151_2DGS_s0', 'b151_LGDM_LoD2'])]:
        g, n = gt(prior)
        for run in runs:
            s42 = np.load(O / 'score151' / f'{run}__{prior}' / 'rows.npz')['s_main']
            for site in ['B0_b10', 'R1rep_b10', 'B173nb_b10']:
                f = O / 'scenes' / f'{site}__{prior}' / 'distances' / f'{run}.npz'
                if not f.exists():
                    rows.append(dict(run=run, prior=prior, site=site, status='없음'))
                    continue
                gi, si = site_map(g, site, np.load(O / 'scenes' / f'{site}__{prior}' / 'rows.npz')['xyz'])
                m = np.zeros(len(g['case']), bool)
                m[gi] = True
                a = np.full(len(g['case']), np.nan)
                a[gi] = np.load(f)['row_s'][si]
                a, b = a[m], s42[m]
                both = np.isfinite(a) & np.isfinite(b)
                for k in sorted(np.unique(g['point_cell'][m])):
                    mk = both & (g['point_cell'][m] == k)
                    d = a[mk] - b[mk]
                    rows.append(dict(run=run, prior=prior, site=site, cell=int(k), status='있음', rows_both=int(mk.sum()),
                                     rows_41_only=int((np.isfinite(a) & ~np.isfinite(b) & (g['point_cell'][m] == k)).sum()),
                                     rows_42_only=int((~np.isfinite(a) & np.isfinite(b) & (g['point_cell'][m] == k)).sum()),
                                     s41_median=stats(a[mk])['median'], s42_median=stats(b[mk])['median'], diff_median=stats(d)['median'],
                                     diff_abs_p90=q(np.abs(d), 90), equal_within_1cm_pct=float(100 * (np.abs(d) <= 0.01).mean()) if mk.any() else None))
    table('a3_mesh_41_vs_42', rows, '가-3: s of the same GT points on the 4.1 site mesh and on the 4.2 unit mesh (site rows <-> gt151 rows by equal coordinates <= 1 mm), per cell')


# ------------------------------------------------------------------------------------------------ 나
def fit_disp(s, n, w=None):
    ok = np.isfinite(s) & (np.abs(s) < 2)
    if ok.sum() < 50:
        return None
    d, *_ = np.linalg.lstsq(n[ok], s[ok], rcond=None)
    return [float(x) for x in d]


def shape(argv):
    runs = argv or [('b151_2DGS_s0', 'ALS'), ('b151_2DGS_s0', 'LoD2'), ('b151_GeoGS_ALS_s0', 'ALS'), ('b151_LGDM_ALS', 'ALS'), ('b151_LGDM_LoD2', 'LoD2')]
    rows, blds, pts = [], [], {}
    for run, prior in runs:
        sp = O / 'score151' / f'{run}__{prior}' / 'rows.npz'
        if not sp.exists():
            rows.append(dict(run=run, prior=prior, status='없음'))
            continue
        g, n = gt(prior)
        s = np.load(sp)['s_main']
        wall = g['wall'].astype(bool)
        slope = np.degrees(np.arccos(np.clip(np.abs(n[:, 2]), 0, 1)))
        xy = g['xyz'][:, :2]
        regions = [(f'cell{k}', in_cell(xy, k)) for k in range(4)] + \
                  [(f'bottom band cell{k} (y < -150 m)', in_cell(xy, k) & (xy[:, 1] < -150)) for k in [0, 2]] + \
                  [(f'cell{k} without the band', in_cell(xy, k) & (xy[:, 1] >= -150)) for k in [0, 2]] + \
                  [('R1rep_b10 box', np.all((xy >= box_of('R1rep_b10')[0][:2]) & (xy <= box_of('R1rep_b10')[1][:2]), 1))]
        for name, m in regions:
            if not m.any():
                continue
            flat = m & ~wall & (slope <= 10)
            tilted = m & ~wall & (slope > 10) & (slope < 60)
            wl = m & wall
            c = np.array(CELLS[int(name[4])]['original_min']) if name.startswith('cell') else None
            ctr = np.median(xy[m], 0)
            r = np.linalg.norm(xy - ctr, axis=1)
            ff = flat & np.isfinite(s) & (np.abs(s) < 2)
            corr_r = float(np.corrcoef(r[ff], s[ff])[0, 1]) if ff.sum() > 50 else None
            corr_z = float(np.corrcoef(g['xyz'][ff, 2], s[ff])[0, 1]) if ff.sum() > 50 else None
            slope_r = float(np.polyfit(r[ff], s[ff], 1)[0]) if ff.sum() > 50 else None
            slope_z = float(np.polyfit(g['xyz'][ff, 2], s[ff], 1)[0]) if ff.sum() > 50 else None
            # tilted roofs: split by the horizontal direction of the normal (4 quadrants of the aspect)
            asp = np.degrees(np.arctan2(n[:, 1], n[:, 0])) % 360
            quad = {f'tilted_aspect_{a}': stats(s[tilted & (asp >= a) & (asp < a + 90)])['median'] for a in [0, 90, 180, 270]}
            wq = {f'wall_facing_{a}': stats(s[wl & (asp >= a) & (asp < a + 90)])['median'] for a in [0, 90, 180, 270]}
            d = fit_disp(s[m & np.isfinite(s)], n[m & np.isfinite(s)])
            rows.append(dict(run=run, prior=prior, region=name, status='있음', gt_points=int(m.sum()), no_surface=int((m & ~np.isfinite(s)).sum()),
                             flat_s_median=stats(s[flat])['median'], flat_s_nmad=stats(s[flat])['nmad'], flat_s_p10=stats(s[flat])['p10'], flat_s_p90=stats(s[flat])['p90'],
                             tilted_s_median=stats(s[tilted])['median'], wall_s_median=stats(s[wl])['median'], **quad, **wq,
                             fit_dx=d[0] if d else None, fit_dy=d[1] if d else None, fit_dz=d[2] if d else None,
                             flat_corr_s_vs_dist_from_centre=corr_r, flat_slope_s_per_100m_from_centre=slope_r * 100 if slope_r is not None else None,
                             flat_corr_s_vs_height=corr_z, flat_slope_s_per_10m_height=slope_z * 10 if slope_z is not None else None))
        names, code = np.unique(g['building'], return_inverse=True)
        for b in range(len(names)):
            mb = code == b
            k = int(np.bincount(g['point_cell'][mb].astype(int), minlength=4).argmax())
            fb = mb & ~wall & (slope <= 10)
            blds.append(dict(run=run, prior=prior, building=str(names[b]), cell_of_most_points=k, gt_points=int(mb.sum()),
                             s_median=stats(s[mb])['median'], flat_s_median=stats(s[fb])['median'], flat_points=int(fb.sum()),
                             completeness_pct=float(100 * (np.isfinite(s[mb]) & (np.abs(s[mb]) <= g['tau'][mb])).mean())))
        sel = np.flatnonzero(in_cell(xy, 3) | in_cell(xy, 2) | (xy[:, 1] < -150))
        rng = np.random.default_rng(0)
        sel = rng.choice(sel, min(len(sel), 400000), replace=False)
        pts[f'{run}__{prior}'] = dict(idx=sel, s=s[sel])
        print('SHAPE', run, prior, flush=True)
    table('b_shape', rows, '나: s (m) of the GT points per region: flat roofs (slope <= 10 deg), tilted roofs (10-60 deg) by aspect quadrant, walls by facing quadrant; '
          'least-squares displacement d with s = n . d over |s| < 2 m (fit_dx/dy/dz); s vs distance from the region centre (scale) and vs height')
    table('b_buildings', blds, '나: per building s median (all GT points and flat roofs) and completeness; cell = the cell holding most of its GT points')
    np.savez_compressed(A / 'b_points_sample.npz', **{f'{k}__{f}': v[f] for k, v in pts.items() for f in v})


# ------------------------------------------------------------------------------------------------ 라
def prev(_):
    rows = []
    for site in ['B173nb_b10', 'R1rep_b10']:
        sd = O / 'scenes' / f'{site}__ALS'
        r = np.load(sd / 'rows.npz')
        nn = r['normal'] * np.sign(r['normal'][:, 2:3] + 1e-12)
        flat = (~r['wall']) & (np.abs(nn[:, 2]) >= FLAT_NZ)
        # case 0 of the site rows = the gt151 case of the same row (gt151 src 1 rows carry the site row index in source_index)
        g, _ = gt('ALS')
        gi, si = site_map(g, site, r['xyz'])
        case0 = np.zeros(len(r['xyz']), bool)
        case0[si] = g['case'][gi] == 0
        print('PREV map', site, len(si), 'of', len(r['xyz']), flush=True)
        cellk = {k: in_cell(r['xyz'][:, :2], k) for k in range(4)}
        for fam in ['2DGS_30000', 'b151_2DGS_s0', 'GeoGS_30000', 'b151_GeoGS_ALS_s0', 'FINALTRAIN_30000', 'mvs', 'prior', 'b151_LGDM_ALS']:
            f = sd / 'distances' / f'{fam}.npz'
            if not f.exists():
                rows.append(dict(site=site, family=fam, status='없음'))
                continue
            s = np.load(f)['row_s']
            for k in range(4):
                m = flat & case0 & cellk[k]
                if m.sum() == 0:
                    continue
                st = stats(s[m])
                rows.append(dict(site=site, family=fam, cell=k, status='있음', flat_case0_rows=int(m.sum()), s_median=st['median'], s_nmad=st['nmad'],
                                 s_p10=st['p10'], s_p90=st['p90'], no_surface=int((~np.isfinite(s[m])).sum()),
                                 within_tau_pct=float(100 * (np.isfinite(s[m]) & (np.abs(s[m]) <= r['row_tau_m'][m])).mean())))
    table('d_prev', rows, '라: flat roof site rows (|n_z| >= 0.985, case 0 = gt151 case of the row matched by equal coordinates; rows not in gt151 left out), s per cell, previous building-unit '
          'runs vs 2 x 2, plus the main method (FINALTRAIN_30000), MVS and prior')


# ------------------------------------------------------------------------------------------------ 가-1b
def above(_):
    """All Gaussians (any opacity) over flat roof GT points with case 0 (xy <= 0.25 m, |dz| <= 3 m): how many and how opaque those above
    the roof are (signed distance > 0.1 m) vs those at the roof (|sd| <= 0.1 m), per cell."""
    rows = []
    g, n = gt('ALS')
    fm = flat_mask(g, n)
    P, N = g['xyz'][fm], n[fm]
    tree = cKDTree(P[:, :2])
    for run in ['b151_2DGS_s0', 'b151_GeoGS_ALS_s0', 'b151_CDGS_ALS_s0', 'cellsef_ALS_s0 (TRAINUNIT)']:
        v, _ = read_ply(RUNS[run], ['x', 'y', 'z', 'opacity'])
        xyz = np.stack([v['x'], v['y'], v['z']], 1).astype(np.float64)
        op = 1 / (1 + np.exp(-v['opacity'].astype(np.float64)))
        d, i = tree.query(xyz[:, :2], k=1, distance_upper_bound=0.25)
        ok = np.flatnonzero(np.isfinite(d))
        j = i[ok]
        sd = np.einsum('ij,ij->i', xyz[ok] - P[j], N[j])
        near = np.abs(xyz[ok, 2] - P[j, 2]) <= 3
        ok, j, sd = ok[near], j[near], sd[near]
        for k in range(4):
            m = in_cell(xyz[ok, :2], k)
            pts = len(np.unique(j[m]))
            ab, at, be = m & (sd > 0.1), m & (np.abs(sd) <= 0.1), m & (sd < -0.1)
            rows.append(dict(run=run, region=f'cell{k}', flat_gt_points_hit=pts, gaussians=int(m.sum()),
                             above_n=int(ab.sum()), at_n=int(at.sum()), below_n=int(be.sum()),
                             above_per_gt_point=float(ab.sum() / max(pts, 1)), at_per_gt_point=float(at.sum() / max(pts, 1)),
                             above_opacity_sum_per_gt_point=float(op[ok][ab].sum() / max(pts, 1)), at_opacity_sum_per_gt_point=float(op[ok][at].sum() / max(pts, 1)),
                             above_opacity_median=stats(op[ok][ab])['median'], above_opacity_lt_05_pct=float(100 * (op[ok][ab] < .5).mean()) if ab.any() else None,
                             above_sd_median=stats(sd[ab])['median'], opacity_weighted_sd_mean=float((op[ok][m] * sd[m]).sum() / max(op[ok][m].sum(), 1e-9))))
        print('ABOVE', run, flush=True)
    table('a1b_above_roof', rows, '가-1b: all Gaussians over flat roof GT points (case 0, ALS GT): above the roof (sd > 0.1 m), at it (|sd| <= 0.1 m), below '
          '(sd < -0.1 m), counts and opacity sums per hit GT point, and the opacity-weighted mean signed distance')


# ------------------------------------------------------------------------------------------------ 가-2 check (expected vs median depth)
def jobs(_):
    """job files for b151_add1_render.py: the 20 views per cell of 가-2 (a2_render_depth_views), K / W2C from the 4.2 render receipts"""
    pv = json.loads((A / 'a2_render_depth_views.json').read_text())['rows']
    for run in ['b151_2DGS_s0', 'b151_GeoGS_ALS_s0']:
        for k in [2, 3]:
            names = [r['view'] for r in pv if r['run'] == run and r['cell'] == k]
            look = {}
            for rp in (O / 'renders').glob(f'c{k}_*__ALS__{run}/receipt.json'):
                for v in json.loads(rp.read_text())['views']:
                    look.setdefault(v['name'], {kk: v[kk] for kk in ['name', 'K', 'W2C', 'width', 'height']})
            key = f'{run}__cell{k}'
            dump(A / 'jobs' / f'{key}.json', dict(key=key, run=run, cell=k, ply=f'/b151/runs/{run}/cell{k}/attempt1/model/point_cloud/iteration_30000/point_cloud.ply',
                                                 views=[look[n] for n in names], scientific_verdict=None))
            print('JOB', key, len(names), flush=True)


def depth2(_):
    g, n = gt('ALS')
    tree = cKDTree(g['xyz'][:, :2])
    rows = []
    for run in ['b151_2DGS_s0', 'b151_GeoGS_ALS_s0']:
        for k in [2, 3]:
            key = f'{run}__cell{k}'
            rc = A / 'renders' / key / 'receipt.json'
            if not rc.exists():
                rows.append(dict(run=run, cell=k, status='없음'))
                continue
            job = json.loads((A / 'jobs' / f'{key}.json').read_text())
            acc = {x: [] for x in ['expected', 'median', 'alpha', 'median_minus_expected']}
            for v in job['views']:
                mvs = read_depth_bin(MVSD / f"{v['name']}.JPG.geometric.bin")
                ok = np.isfinite(mvs) & (mvs > 0)
                K, W2C = np.array(v['K']), np.array(v['W2C'])
                yy, xx = np.mgrid[0:mvs.shape[0], 0:mvs.shape[1]]
                Xc = np.stack([(xx[ok] - K[0, 2]) / K[0, 0] * mvs[ok], (yy[ok] - K[1, 2]) / K[1, 1] * mvs[ok], mvs[ok]], 1)
                C2W = np.linalg.inv(W2C)
                Xw = Xc @ C2W[:3, :3].T + C2W[:3, 3]
                d, i = tree.query(Xw[:, :2], k=1, distance_upper_bound=0.25)
                bld = np.isfinite(d)
                bld[bld] = np.abs(Xw[bld, 2] - g['xyz'][i[bld], 2]) <= 3
                z = np.load(A / 'renders' / key / f"{v['name']}.npz")
                e, m_, a = z['expected'][ok], z['median'][ok], z['alpha'][ok]
                sel = bld & (e > 0) & (m_ > 0)
                acc['expected'].append(e[sel] - mvs[ok][sel])
                acc['median'].append(m_[sel] - mvs[ok][sel])
                acc['median_minus_expected'].append(m_[sel] - e[sel])
                acc['alpha'].append(a[sel])
            acc = {x: np.concatenate(v) for x, v in acc.items()}
            se, sm, sa = stats(acc['expected']), stats(acc['median']), stats(acc['alpha'])
            rows.append(dict(run=run, cell=k, status='있음', views=len(job['views']), building_pixels=se['n'],
                             expected_minus_mvs_median=se['median'], expected_minus_mvs_nmad=se['nmad'],
                             median_minus_mvs_median=sm['median'], median_minus_mvs_nmad=sm['nmad'],
                             median_minus_expected_median=stats(acc['median_minus_expected'])['median'],
                             alpha_median=sa['median'], alpha_p10=sa['p10'], alpha_lt_099_pct=float(100 * (acc['alpha'] < .99).mean())))
            print('DEPTH2', run, k, flush=True)
    table('a2b_expected_vs_median', rows, '가-2 check: whole cell model rendered at the same 20 views per cell; camera-z depth minus campus MVS on building pixels '
          'for the expected depth (depth_ratio 0, the mesh rule) and the median depth (depth_ratio 1); alpha of the pixels')


# ------------------------------------------------------------------------------------------------ 다
def colmap_images(p):
    import struct
    out = {}
    with open(p, 'rb') as f:
        n = struct.unpack('<Q', f.read(8))[0]
        for _ in range(n):
            struct.unpack('<i', f.read(4))
            qv = struct.unpack('<4d', f.read(32))
            t = struct.unpack('<3d', f.read(24))
            struct.unpack('<i', f.read(4))
            name = b''
            while (c := f.read(1)) != b'\x00':
                name += c
            n2 = struct.unpack('<Q', f.read(8))[0]
            f.read(24 * n2)
            w, x, y, z = qv
            R = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)], [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
                          [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)]])
            out[name.decode().rsplit('.', 1)[0]] = (R, -R.T @ np.array(t))
    return out


def ply_xyz(p):
    v, _ = read_ply(p, ['x', 'y', 'z', 'origin'])
    return np.stack([v['x'], v['y'], v['z']], 1), v.get('origin')


def zq(z):
    return dict(n=int(len(z)), z_p5=q(z, 5), z_p50=q(z, 50), z_p95=q(z, 95)) if len(z) else dict(n=0)


def inputs(_):
    g, _n = gt('ALS')
    camp = colmap_images(TU1 / 'scenes/campus/scene_ALS/sparse/0/images.bin')
    rows = []
    for k in range(4):
        split = json.loads((TU1 / 'scenes' / f'cell{k}' / 'split.json').read_text())
        im = colmap_images(B / 'scenes/2DGS' / f'cell{k}' / 'sparse/0/images.bin')
        tr = [im[nm] for nm in split['train']]
        C = np.array([c for _, c in tr])
        axis = np.array([R[2] for R, _ in tr])           # camera z axis (viewing direction) in world
        tilt = np.degrees(np.arccos(np.clip(-axis[:, 2], -1, 1)))
        dC = max(float(np.abs(c - camp[nm][1]).max()) for nm, (_, c) in im.items())
        gz = float(np.median(g['xyz'][in_cell(g['xyz'][:, :2], k), 2]))
        centre = C.mean(0)
        radius = float(1.1 * np.linalg.norm(C - centre, axis=1).max())
        p2, o2 = ply_xyz(B / 'scenes/2DGS' / f'cell{k}' / 'sparse/0/points3D.ply')
        pg, _ = ply_xyz(B / 'scenes/GeoGS_ALS' / f'cell{k}' / 'sparse_lod/0/points3D.ply')
        un = json.loads((B / 'scenes/CDGS' / f'cell{k}' / 'units.json').read_text())
        da3 = json.loads((B / 'da3/geogs' / f'cell{k}' / 'da3_diag_consec12.json').read_text())
        sc = np.array([b['scale'] for b in da3['batch_rows']])
        res = np.concatenate([b['residual_rel'] for b in da3['batch_rows']])
        gs = json.loads((B / 'scenes/GeoGS_ALS' / f'cell{k}' / 'scene_receipt.json').read_text())
        mg = {r: json.loads((B / 'runs' / r / 'merged/point_cloud.json').read_text()) for r in ['b151_2DGS_s0', 'b151_GeoGS_ALS_s0']}
        rows.append(dict(cell=k, train_views=len(split['train']), test_views=len(split['test']),
                         pose_max_abs_diff_vs_campus_m=dC, intrinsics='PINHOLE 674.42 / 674.78 / 513.92 / 365.60, one camera for all views (cameras.bin)',
                         cam_z_p10=q(C[:, 2], 10), cam_z_p50=q(C[:, 2], 50), cam_z_p90=q(C[:, 2], 90), gt_z_median=gz,
                         cam_height_above_gt_median_m=float(np.median(C[:, 2]) - gz),
                         views_axis_within_15deg_of_down_pct=float(100 * (tilt <= 15).mean()), view_tilt_median_deg=float(np.median(tilt)),
                         nerf_norm_centre=[round(float(x), 2) for x in centre], nerf_norm_radius_m=radius,
                         clone_split_size_threshold_m=0.01 * radius, prune_big_world_size_m=0.1 * radius,
                         init_2DGS=zq(p2[:, 2]), init_GeoGS_ALS=zq(pg[:, 2]), init_CDGS_kept=(un.get('points') or {}).get('kept'),
                         geogs_prior_depth_maps=gs.get('depth_maps'), geogs_protection_points=gs.get('protection_cloud_points'),
                         da3_batches=len(sc), da3_scale_median=float(np.median(sc)), da3_scale_min=float(sc.min()), da3_scale_max=float(sc.max()),
                         da3_residual_rel_median=float(np.median(res)), da3_residual_rel_p90=q(res, 90),
                         merge_2DGS_kept_of_total=f"{mg['b151_2DGS_s0']['cells'][k]['kept']} / {mg['b151_2DGS_s0']['cells'][k]['total']}",
                         merge_GeoGS_ALS_kept_of_total=f"{mg['b151_GeoGS_ALS_s0']['cells'][k]['kept']} / {mg['b151_GeoGS_ALS_s0']['cells'][k]['total']}",
                         merge_transform='없음 (keep xy in the original cell, concatenate; no coordinate change: tu_postcpu.merge rule)'))
        print('INPUTS', k, flush=True)
    # TRAINUNIT cellsef_ALS_s0 cell 3
    ce = TU1 / 'runs/ef/cellsef_ALS_s0_cell3/attempt2'
    ib = json.loads((ce / 'input_binding.json').read_text())
    eo = json.loads((ce / 'extent_override.json').read_text())
    pc, oc = ply_xyz(TU1 / 'scenes/cell3/scene_ALS/sparse/0/points3D.ply')
    rows.append(dict(cell='3 (cellsef_ALS_s0, TRAINUNIT)', train_views=eo.get('cameras'), scene=ib['argv'][1],
                     same_cameras_bin_images_bin_as_this_task='yes (byte copies, sha256 equal)', nerf_norm_radius_m=eo.get('used_radius'),
                     init_points_all_origins=zq(pc[:, 2]), init_points_origin0=zq(pc[oc == 0, 2]) if oc is not None else None,
                     init_points_prior_rows=int((oc != 0).sum()) if oc is not None else None,
                     supervision='target maps (jbgs_target on, lambda .05, /tu/stage1/cell3__ALS), finaltrain on, filter (addendum 12); DA3 / LoD depth off',
                     argv=' '.join(ib['argv'])))
    table('c_inputs', rows, '다: per cell inputs of this task (2DGS, GeoGS ALS, CDGS; TU1 cell scenes) and TRAINUNIT cellsef_ALS_s0 cell 3. nerf_norm = '
          'getNerfppNorm of the training cameras (centre = mean camera centre, radius = 1.1 x the largest distance); it sets cameras_extent only '
          '(densify / prune thresholds), the Gaussian positions stay in the scene frame, so there is nothing to undo at the merge')


if __name__ == '__main__':
    A.mkdir(parents=True, exist_ok=True)
    dict(inputs=inputs, gauss=gauss, above=above, depth=depth, jobs=jobs, depth2=depth2, mesh=mesh, shape=shape, prev=prev)[sys.argv[1]](sys.argv[2:])
