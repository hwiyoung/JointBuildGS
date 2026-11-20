"""PHD-MAIN-BASE151-v1 4.2 scorer (configs/phd/main_base151_v1/score151.json), GTJUDGE environment (jointbuildgs:dev, CPU; /gtjudge = OUT/gt).

  python b151_score151.py unit <run> <prior> <unit>     -> /gtjudge/score151/<run>__<prior>/<unit>.npz
  python b151_score151.py gather <run> <prior>          -> /gtjudge/score151/<run>__<prior>/rows.npz, samples.npz, summary.json
Mesh of a unit: /gtjudge/meshes/<unit>__<P>__<run>/final.ply (P = the run prior; 2DGS: ALS key, the same mesh for both priors).
Rows = /b151/gt/gt151_<prior>.npz. Completeness: GTJUDGE normal_line.measure; main = rows of the unit (the cell that holds the point);
literal = rows of buildings of the unit's cell lying in the unit's tile outside the cell, measured on this unit mesh.
Accuracy: GTJUDGE geometry_add1.sample_normals (400 / m2) in the 0.5 m sample cells, eligible within 1 m of the reference (all rows of the
JUDGECHECK-v2 file, unit rectangle + 1 m), Cylinder distance along the sample normal oriented to the nearest reference normal, RESCORE prism
columns of the JUDGECHECK-v2 patches -> owner patch -> nearest paired row with the same patch (assigned row: case, tau, building).
scientific_verdict: null
"""
import sys

import numpy as np
from scipy.spatial import cKDTree

sys.path.insert(0, '/repo/scripts/phd/main_gtjudge_v1')
from inherited import O, cfg as gt_cfg  # noqa: E402
from geometry_add1 import read_surface, sample_normals  # noqa: E402
from normal_line import measure  # noqa: E402
from cylinder import Cylinder  # noqa: E402
from src.phd.metrics_v3.surface import MeshScene  # noqa: E402
import b151_common as BC  # noqa: E402
import json  # noqa: E402
import subprocess  # noqa: E402
from pathlib import Path  # noqa: E402

E0, N0 = 690953.0, 5336071.0
GRID = dict(e0=690700.0, n0=5335820.0, res=0.5, nx=1000)


class CampusGrid:
    """0.5 m sample cells of the site grid frame holding >= 1 paired GT row of the prior (score151 accuracy.sample_cells)."""

    def __init__(self, xyz):
        self.keys = np.unique(self.key(xyz))

    @staticmethod
    def key(P):
        x = np.floor((P[:, 0] + E0 - GRID['e0']) / GRID['res']).astype('i8')
        y = np.floor((P[:, 1] + N0 - GRID['n0']) / GRID['res']).astype('i8')
        return y * GRID['nx'] + x

    def in_cells(self, P):
        return np.isin(self.key(P), self.keys)


def layout():
    return {u['unit']: u for u in json.loads((O / 'units/layout.json').read_text())['units']}


def ref_all(prior):
    z = np.load(BC.JC2 / 'analysis' / f'gt_{prior}.npz')
    return dict(xyz=z['xyz'], normal=z['normal'], paired=z['paired'], wall=z['patch_kind'] == 2, gt_wall=z['gt_kind'] == 2,
                tile=z['patch_tile'], index=z['patch_index'])


def prism(points, c, a, b, n, length, folder):
    """JUDGECHECK-v2 s4_truth_rest.prism = RESCORE geometry.columns record layout, RESCORE prism.cpp (same sha256)."""
    basis = np.stack([a, b, n], axis=2)
    good = np.isfinite(basis).all((1, 2)) & np.isfinite(c).all(1)
    inv = np.full_like(basis, np.nan)
    good[good] &= np.abs(np.linalg.det(basis[good])) > 1e-10
    inv[good] = np.linalg.inv(basis[good])
    ext = .125 * (abs(a) + abs(b)) + length[:, None] * abs(n)
    rec = np.c_[c, inv.reshape(-1, 9), np.where(good, length, 0), c - ext, c + ext].astype('<f8')
    folder.mkdir(parents=True, exist_ok=True)
    points.astype('<f8').tofile(folder / 'points.bin')
    rec.tofile(folder / 'columns.bin')
    exe = O / 'bin/prism_b151'
    src = Path('/repo/scripts/phd/main_rescore_v1/prism.cpp')
    if not exe.exists():
        exe.parent.mkdir(exist_ok=True)
        subprocess.run(['g++', '-O3', '-std=c++17', str(src), '-o', str(exe)], check=True)
    subprocess.run([str(exe), str(folder / 'points.bin'), str(folder / 'columns.bin'), str(folder / 'owner.bin'), str(folder / 'hits.bin')], check=True,
                   stdout=subprocess.DEVNULL)
    o = np.fromfile(folder / 'owner.bin', '<i4')
    for f in ['points.bin', 'columns.bin', 'owner.bin', 'hits.bin']:
        (folder / f).unlink()
    return o


def patches_near(prior, lo, hi):
    P = []
    for q in sorted((BC.JC2 / 'geometry_raw').glob(f'*__{prior}.npz')):
        z = np.load(q)
        cen = z['centre']
        m = ((cen[:, :2] >= lo - 12) & (cen[:, :2] <= hi + 12)).all(1)
        if m.any():
            d = {k: z[k][m] for k in ['centre', 'normal', 'tangent1', 'tangent2', 'kind', 'prior_height_m']}
            d['tile'] = np.full(int(m.sum()), q.stem.split('__')[0])
            d['index'] = np.flatnonzero(m)
            P.append(d)
    p = {k: np.concatenate([x[k] for x in P]) for k in P[0]}
    n = p['normal'].astype(float)
    a, b = p['tangent1'].astype(float).copy(), p['tangent2'].astype(float).copy()
    if prior == 'ALS':   # s4_truth_rest rule for ALS tangents
        for i in np.flatnonzero(np.isfinite(n).all(1)):
            e = np.array([1., 0., 0.]) if abs(n[i, 0]) < .9 else np.array([0., 1., 0.])
            e = e - n[i] * (e @ n[i]); e /= np.linalg.norm(e); a[i] = e; b[i] = np.cross(n[i], e)
    c = p['centre'] + np.nan_to_num(p['prior_height_m'])[:, None] * n
    return p, c, a, b, n, np.where(p['kind'] == 1, 10., 5.)


def unit(run, prior, uname):
    gt_cfg()
    BC.cfg('score151')
    u = layout()[uname]
    k = u['cell']
    method = run.split('_')[1]
    P_ = 'ALS' if method == '2DGS' else run.split('_')[2]
    mesh = O / 'meshes' / f'{uname}__{P_}__{run}' / 'final.ply'
    out = O / 'score151' / f'{run}__{prior}' / f'{uname}.npz'
    if out.exists():
        return
    lo, hi = np.array(u['rect_min']), np.array(u['rect_max'])
    g = np.load(BC.B / 'gt' / f'gt151_{prior}.npz')
    xy = g['xyz'][:, :2]
    e = np.floor((xy[:, 0] + E0) / 100).astype(int); nn = np.floor((xy[:, 1] + N0) / 100).astype(int)
    te, tn = (int(x) for x in u['tile'].split('_'))
    in_tile = (e == te) & (nn == tn)
    main_rows = np.flatnonzero(in_tile & (g['point_cell'] == k))
    lit_rows = np.flatnonzero(in_tile & (g['building_cell'] == k) & (g['point_cell'] != k))
    V, F = read_surface(mesh)
    sc = MeshScene(V, F)
    rows = np.r_[main_rows, lit_rows]
    s, off = measure(sc, g['xyz'][rows], g['normal'][rows], g['wall'][rows]) if len(rows) else (np.zeros(0), np.zeros(0, 'i1'))
    del sc
    # accuracy samples
    grid = CampusGrid(g['xyz'])
    # 11-20: sample_normals fails when no triangle passes its keep test (centroid in a sample cell or area > 0.01 m2);
    # same keep test here, zero triangles kept -> zero accuracy samples ("표본 없음"), completeness rows above unchanged.
    kept_any = any((grid.in_cells(V[F[i:i + 500000]].mean(1)) | (.5 * np.linalg.norm(np.cross(
        V[F[i:i + 500000]][:, 1] - V[F[i:i + 500000]][:, 0], V[F[i:i + 500000]][:, 2] - V[F[i:i + 500000]][:, 0]), axis=1) > .01)).any()
        for i in range(0, len(F), 500000))
    Ps, Ns = sample_normals(V, F, grid) if kept_any else (np.zeros((0, 3)), np.zeros((0, 3)))
    del V, F
    inrect = (Ps[:, :2] >= lo).all(1) & (Ps[:, :2] <= hi).all(1)
    Ps, Ns = Ps[inrect], Ns[inrect]
    R = ref_all(prior)
    rm = ((R['xyz'][:, :2] >= lo - 1) & (R['xyz'][:, :2] <= hi + 1)).all(1)
    rx, rn = R['xyz'][rm], R['normal'][rm].copy()
    rwall = np.where(R['paired'][rm], R['wall'][rm], R['gt_wall'][rm])
    if prior == 'ALS':
        rn[rn[:, 2] < 0] *= -1
    res = dict(rows=rows.astype('i8'), row_main=np.r_[np.ones(len(main_rows), bool), np.zeros(len(lit_rows), bool)], row_s=s.astype('f8'), row_offset=off,
               samples=np.int64(len(Ps)), kept_triangles_any=np.bool_(kept_any))
    if len(Ps) and len(rx):
        tree = cKDTree(rx)
        euc, idx = tree.query(Ps, workers=4)
        radius = float(np.median(tree.query(rx, k=2, workers=4)[0][:, 1]))
        N = Ns * np.where((Ns * rn[idx]).sum(1) < 0, -1., 1.)[:, None]
        eligible = euc <= 1
        qs = np.full(len(Ps), np.nan)
        cy = Cylinder(rx)
        qs[eligible], _ = cy.query(Ps[eligible], N[eligible], np.where(rwall[idx][eligible], 5., 10.), radius)
        cy.close()
        # owner columns -> nearest paired row with the same patch
        p, c, a, b, n, length = patches_near(prior, lo, hi)
        owner = prism(Ps, c, a, b, n, length, O / 'tmp' / f'prism_{run}_{prior}_{uname}')
        pr = np.flatnonzero(R['paired'] & ((R['xyz'][:, :2] >= lo - 12) & (R['xyz'][:, :2] <= hi + 12)).all(1))
        col_of = {(t, int(i)): j for j, (t, i) in enumerate(zip(p['tile'].tolist(), p['index'].tolist()))}
        row_col = np.array([col_of.get((t, int(i)), -1) for t, i in zip(R['tile'][pr].tolist(), R['index'][pr].tolist())], 'i8')
        ok = row_col >= 0
        assigned_src = np.full(len(Ps), -1, 'i8')
        if ok.any():
            t2 = cKDTree(np.c_[row_col[ok].astype(float) * 100000., R['xyz'][pr[ok]]])
            has = owner >= 0
            ii = t2.query(np.c_[owner[has].astype(float) * 100000., Ps[has]], workers=4)[1]
            same = row_col[ok][ii] == owner[has]
            sel = np.flatnonzero(has)[same]
            assigned_src[sel] = pr[ok][ii[same]]
        # map JUDGECHECK file index -> gt151 row (paired rows of the 151 buildings)
        pos = np.full(len(R['paired']), -1, 'i8')
        pos[g['source_index']] = np.arange(len(g['source_index']))
        arow = np.where(assigned_src >= 0, pos[np.clip(assigned_src, 0, None)], -1)
        # nearest paired row of the 151 buildings (tau / building of samples without an assigned row)
        near = np.flatnonzero(((g['xyz'][:, :2] >= lo - 1) & (g['xyz'][:, :2] <= hi + 1)).all(1))
        if len(near):
            dn, jn = cKDTree(g['xyz'][near]).query(Ps, workers=4)
            nrow = near[jn]
        else:
            dn, nrow = np.full(len(Ps), np.inf), np.full(len(Ps), -1)
        tau = np.where(arow >= 0, g['tau'][np.clip(arow, 0, None)], np.where(nrow >= 0, g['tau'][np.clip(nrow, 0, None)], np.nan))
        bidx = np.where(arow >= 0, arow, np.where((nrow >= 0) & (dn <= 1), nrow, -1))
        res.update(sample_xyz=Ps.astype('f4'), sample_nz=N[:, 2].astype('f4'), sample_eligible=eligible, sample_s=qs, sample_tau=tau,
                   sample_row=arow, sample_building_row=bidx, sample_owner=owner, radius=np.float64(radius), reference_rows=np.int64(len(rx)))
    out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out, **res)
    print('UNIT_SCORED', run, prior, uname, len(rows), len(Ps), flush=True)


def gather(run, prior):
    BC.cfg('score151')
    g = np.load(BC.B / 'gt' / f'gt151_{prior}.npz')
    n = len(g['case'])
    s_main, s_lit = np.full(n, np.nan), np.full(n, np.nan)
    covered = np.zeros(n, bool)
    S = {k: [] for k in ['sample_s', 'sample_tau', 'sample_eligible', 'sample_nz', 'sample_row', 'sample_building_row', 'sample_xyz']}
    units = []
    for uname in sorted(layout()):
        p = O / 'score151' / f'{run}__{prior}' / f'{uname}.npz'
        if not p.exists():
            units.append(dict(unit=uname, scored=False))
            continue
        z = np.load(p)
        r, m = z['rows'], z['row_main']
        s_main[r[m]] = z['row_s'][m]; covered[r[m]] = True
        s_lit[r[~m]] = z['row_s'][~m]
        if 'sample_s' in z.files:
            for k in S:
                S[k].append(z[k])
        units.append(dict(unit=uname, scored=True, rows_main=int(m.sum()), rows_literal=int((~m).sum()), samples=int(z['samples'])))
    own = g['point_cell'] == g['building_cell']
    s_lit[own] = s_main[own]
    dest = O / 'score151' / f'{run}__{prior}'
    np.savez_compressed(dest / 'rows.npz', s_main=s_main, s_literal=s_lit, covered=covered)
    np.savez_compressed(dest / 'samples.npz', **{k: np.concatenate(v) if v else np.zeros(0) for k, v in S.items()})
    BC.dump(dest / 'summary.json', dict(at=BC.now(), run=run, prior=prior, rows=n, rows_covered=int(covered.sum()), units=units, scientific_verdict=None))
    print('GATHERED', run, prior, int(covered.sum()), n, flush=True)


if __name__ == '__main__':
    a = sys.argv[1:]
    if a[0] == 'unit':
        unit(a[1], a[2], a[3])
    elif a[0] == 'gather':
        gather(a[1], a[2])
