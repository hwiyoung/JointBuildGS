"""PHD-MAIN-BASE151-v1 LGDM over the campus, inputs (jointbuildgs:dev, CPU; run_lgdm_cpu.sh). Rules: configs/phd/main_base151_v1/inputs_LGDM.json.

  python b151_lgdm_inputs.py prior     -> /b151/lgdm/prior/{lod2_campus.npz, als_campus.npz, grid.json, receipt.json}
  python b151_lgdm_inputs.py pairs     -> /b151/lgdm/prep/pairs_campus.json

prior  the inputs_prior surface rule (b151_prior.py: tile union by centroid in the tile core, all faces, LoD2 shift 0, ALS vertex +
       als_shift_m of the nearest JUDGECHECK-v2 ALS patch) over all WIDEN0 prior tiles without a range cut, plus what mvsfuse needs:
       LoD2 building id (sorted names), tri_type, wall surface id (tile surface table polygon gml id); ALS building_tri, vertex class,
       building region = vertex-connected components of building_tri triangles with coincident registered vertices merged;
       tri_cells bit k = centroid (before the ALS shift) in expanded cell k + 20 m. Check: bit-k triangles == OUT/prior/cell<k> mesh.
       grid.json: the 0.25 m plan grid over the tile-core union +- 10 m.
pairs  mvsfuse/pairs.py main() over the 819 campus training views (MVS map = WIDEN0 geometric depth, stage-0 export a1 rule).
scientific_verdict: null
"""
import sys
import time

import numpy as np

from b151_common import *

sys.path.insert(0, '/exp/scripts/phd/main_baselines_v1/mvsfuse')
import mf_common as M  # noqa: E402  (inserts /repo and /repo/scripts/phd/main_stage0_v1; common.py is byte-identical to the exp copy)
from common import GRID_H, GRID_W, Views, read_depth_bin  # noqa: E402
import b151_prior as BP  # noqa: E402  (tiles, als_shift_tree, MARGIN; its main() is not called)

L = B / 'lgdm'
CAMPUS = TU1 / 'scenes/campus'
MVSD = WD / 'mvs/full/stereo/depth_maps'
GRID_MARGIN = 10.0
NAME = {'LoD2': 'lod2_mesh.npz', 'ALS': 'als_mesh.npz'}
CAMPUS_MESH = {'LoD2': 'lod2_campus.npz', 'ALS': 'als_campus.npz'}


def lcfg():
    return cfg('inputs_LGDM')


def campus_views():
    return Views(sparse=CAMPUS / 'scene_LoD2/sparse/0')


def campus_train():
    return list(json.loads((CAMPUS / 'split.json').read_text())['train'])


def cell_train(k):
    return list(json.loads((TU1 / 'scenes' / f'cell{k}' / 'split.json').read_text())['train'])


def mvs_map(stem):
    """stage-0 export rule (s03_stage1_v6.py:135-139,145,378): COLMAP geometric depth, a1 = finite & > 0, NaN elsewhere, float32."""
    dm = read_depth_bin(MVSD / f'{stem}.JPG.geometric.bin')
    assert dm.shape == (GRID_H, GRID_W), (stem, dm.shape)
    a1 = np.isfinite(dm) & (dm > 0)
    return np.where(a1, dm, np.nan).astype(np.float32)


def read_rgb(site, stem):
    """mf_common.read_rgb with the campus image folder."""
    import cv2
    img = cv2.imread(str(CAMPUS / 'images' / f'{stem}.jpg'), cv2.IMREAD_COLOR)
    if img is None or img.shape[:2] != (M.H, M.W):
        raise RuntimeError(f'image {stem}: {None if img is None else img.shape}')
    return cv2.cvtColor(img, cv2.COLOR_BGR2RGB).astype(np.float32)


def cell_ranges():
    return [(np.array(x['expanded_min'], float) - BP.MARGIN, np.array(x['expanded_max'], float) + BP.MARGIN) for x in cfg()['cells']['per_cell']]


# ------------------------------------------------------------------------------------------------ campus prior surface
def build_prior():
    lcfg()
    t0 = time.time()
    T = BP.tiles()
    tree, shifts = BP.als_shift_tree()
    R = cell_ranges()
    out = L / 'prior'
    out.mkdir(parents=True, exist_ok=True)
    rec = dict(at=now(), rule='inputs_LGDM.json inputs.prior_surface_judge / prior_surface_check / building_regions', tiles=[t[0] for t in T],
               source=str(BP.WI / 'prior_tiles'), cell_ranges=[[lo.tolist(), hi.tolist()] for lo, hi in R], checks={}, scientific_verdict=None)
    for prior in ('LoD2', 'ALS'):
        Vs, Fs, ex, nv = [], [], {}, 0
        app = lambda key, v: ex.setdefault(key, []).append(v)
        for tid, tlo, thi in T:
            m = np.load(BP.WI / 'prior_tiles' / tid / NAME[prior])
            V, F = m['V'].astype(np.float64), m['F'].astype(np.int64)
            cen = V[F].mean(1)[:, :2]
            keep = ((cen >= tlo) & (cen < thi)).all(1)
            if not keep.any():
                continue
            ck = cen[keep]
            bits = np.zeros(int(keep.sum()), np.uint8)
            for k, (lo, hi) in enumerate(R):
                bits |= (((ck >= lo) & (ck < hi)).all(1)).astype(np.uint8) << k
            F = F[keep]
            used = np.unique(F)
            remap = np.full(len(V), -1, np.int64)
            remap[used] = np.arange(len(used)) + nv
            Vs.append(V[used]); Fs.append(remap[F]); nv += len(used)
            app('tri_cells', bits); app('tri_tile', np.full(int(keep.sum()), [t[0] for t in T].index(tid), np.int16))
            if prior == 'LoD2':
                bn = m['building_names']
                tb = m['tri_building'][keep]
                app('tri_type', m['tri_type'][keep].astype(np.int8))
                app('tri_building_name', np.where(tb >= 0, bn[np.clip(tb, 0, None)], ''))
                gml = {int(r['ext']): r['gml'] for r in json.loads((BP.WI / 'prior_tiles' / tid / 'lod2_surfaces.json').read_text())['surfaces']}
                app('tri_surface_key', np.array([gml.get(int(e), f'{tid}:{int(e)}') for e in m['tri_surface'][keep]]))
            else:
                app('cls', m['cls'][used]); app('building_tri', m['building_tri'][keep])
        V = np.concatenate(Vs); F = np.concatenate(Fs)
        ex = {key: np.concatenate(v) for key, v in ex.items()}
        if prior == 'ALS':
            _, ii = tree.query(V[:, :2], workers=8)
            V = V + shifts[ii]
            # building regions: vertex-connected components with coincident registered vertices merged across tiles
            _, vkey = np.unique(V, axis=0, return_inverse=True)
            vkey = vkey.ravel().astype(np.int64)
            tri_bld = M.tri_components(vkey[F], ex['building_tri'].astype(bool))
            tri_bld_nomerge = M.tri_components(F, ex['building_tri'].astype(bool))
            r = dict(vertices=int(len(V)), distinct_vertices=int(vkey.max() + 1), faces=int(len(F)), building_tri=int(ex['building_tri'].sum()),
                     building_regions=int(tri_bld.max() + 1), building_regions_without_merge=int(tri_bld_nomerge.max() + 1))
            np.savez(out / CAMPUS_MESH[prior], V=V, F=F, cls=ex['cls'], building_tri=ex['building_tri'].astype(bool), tri_bld=tri_bld,
                     tri_cells=ex['tri_cells'], tri_tile=ex['tri_tile'], tiles=np.array([t[0] for t in T]))
        else:
            names = sorted(set(ex['tri_building_name'].tolist()) - {''})
            nid = {n: i for i, n in enumerate(names)}
            tri_bld = np.array([nid.get(n, -1) for n in ex['tri_building_name']], np.int64)
            skeys = sorted(set(ex['tri_surface_key'].tolist()))
            sid = {s: i for i, s in enumerate(skeys)}
            tri_surface = np.array([sid[s] for s in ex['tri_surface_key']], np.int64)
            r = dict(vertices=int(len(V)), faces=int(len(F)), buildings=len(names), surfaces=len(skeys),
                     faces_by_type={str(t): int((ex['tri_type'] == t).sum()) for t in (0, 1, 2)},
                     faces_without_building=int((tri_bld < 0).sum()))
            np.savez(out / CAMPUS_MESH[prior], V=V, F=F, tri_type=ex['tri_type'], tri_bld=tri_bld, building_names=np.array(names),
                     tri_surface=tri_surface, surface_keys=np.array(skeys), tri_cells=ex['tri_cells'], tri_tile=ex['tri_tile'], tiles=np.array([t[0] for t in T]))
        # check against the cell surfaces (inputs_prior, b151_prior.py)
        TV = V[F]
        ck = {}
        for k in range(len(R)):
            sel = ((ex['tri_cells'] >> k) & 1).astype(bool)
            mk = np.load(B / 'prior' / f'cell{k}' / NAME[prior])
            same = bool(int(sel.sum()) == len(mk['F']) and np.array_equal(TV[sel], mk['V'][mk['F']]))
            if prior == 'LoD2':
                same = same and np.array_equal(ex['tri_type'][sel], mk['tri_type']) and np.array_equal(ex['tri_building_name'][sel], mk['tri_building'])
            else:
                same = same and np.array_equal(ex['building_tri'][sel], mk['building_tri'])
            ck[f'cell{k}'] = dict(campus_faces_in_range=int(sel.sum()), cell_faces=int(len(mk['F'])), identical=same)
        r['cell_check'] = ck
        r['sha256'] = sha(out / CAMPUS_MESH[prior])
        rec[prior] = r
        rec['checks'][prior] = all(v['identical'] for v in ck.values())
        print('CAMPUS_PRIOR', prior, {k: v for k, v in r.items() if k != 'cell_check'}, {k: v['identical'] for k, v in ck.items()}, flush=True)
    # plan grid: tile-core union +- 10 m
    lo = np.min([t[1] for t in T], 0) - GRID_MARGIN
    hi = np.max([t[2] for t in T], 0) + GRID_MARGIN
    lo = np.floor(lo / M.CELL) * M.CELL
    hi = np.ceil(hi / M.CELL) * M.CELL
    nx, ny = int(round((hi[0] - lo[0]) / M.CELL)), int(round((hi[1] - lo[1]) / M.CELL))
    grid = dict(lo=lo.tolist(), hi=hi.tolist(), nx=nx, ny=ny, cell_m=M.CELL, rule='tile-core union +- 10 m, floor / ceil to 0.25 m; no evaluation range')
    dump(out / 'grid.json', grid)
    rec['grid'] = grid
    rec['seconds'] = round(time.time() - t0, 1)
    dump(out / 'receipt.json', rec)
    if not all(rec['checks'].values()):
        dump(L / 'STOP_prior_check.json', dict(checks=rec['checks'], scientific_verdict=None))
        raise SystemExit('campus surface differs from a cell surface: stop')
    print('GRID', grid, 'seconds', rec['seconds'], flush=True)


class CampusPrior(M.Prior):
    """mf_common.Prior with the campus surface (same attributes; scene() / building_scene() inherited)."""

    def __init__(self, prior):
        self.site, self.prior = 'campus', prior
        m = np.load(L / 'prior' / CAMPUS_MESH[prior])
        self.shift = np.zeros(3)
        self.V, self.F = m['V'].astype(np.float64), m['F'].astype(np.int64)
        self.tri_bld = m['tri_bld'].astype(np.int64)
        self.tri_cells = m['tri_cells']
        if prior == 'LoD2':
            self.tri_type = m['tri_type'].astype(np.int64)
            self.tri_surface = m['tri_surface'].astype(np.int64)
            self.building_names = [str(x) for x in m['building_names']]
        else:
            self.building_tri = m['building_tri'].astype(bool)
            self.tri_type = None
            self.tri_surface = None
            self.building_names = None
        self.n_bld = int(self.tri_bld.max()) + 1 if (self.tri_bld >= 0).any() else 0
        nrm = np.cross(self.V[self.F[:, 1]] - self.V[self.F[:, 0]], self.V[self.F[:, 2]] - self.V[self.F[:, 0]])
        self.nz = np.abs(nrm[:, 2]) / np.maximum(np.linalg.norm(nrm, axis=1), 1e-12)     # mf_common.Prior: |vertical normal component|
        self._scene = None
        self._bscene = None


class MeshOnly(M.Prior):
    """a surface for re-casts only (the cell surfaces of inputs_prior)."""

    def __init__(self, path):
        m = np.load(path)
        self.V, self.F = m['V'].astype(np.float64), m['F'].astype(np.int64)
        self._scene = None
        self._bscene = None


class CampusGrid(M.Grid):
    """mf_common.Grid on grid.json (no evaluation range)."""

    def __init__(self):
        g = json.loads((L / 'prior/grid.json').read_text())
        self.lo = np.array(g['lo'], np.float64)
        self.nx, self.ny = int(g['nx']), int(g['ny'])
        self.B = M.basis()
        self.in_eval = np.zeros((self.ny, self.nx), bool)


# ------------------------------------------------------------------------------------------------ pairs (mvsfuse/pairs.py main)
def pairs():
    lcfg()
    t0 = time.time()
    R = M.RULE['pairs']
    fl, table = M.flights()
    V = campus_views()
    train = campus_train()
    st = R['overlap_stride_px']
    pts, nmvs = {}, {}
    for s in train:
        n = f'{s}.jpg'
        m = mvs_map(s)
        sub = m[::st, ::st].astype(np.float64)
        ok = np.isfinite(sub) & (sub > 0)
        rays = V.rays(n, np.float64)[::st, ::st]
        pts[s] = V.C(n)[None, :] + sub[ok][:, None] * rays[ok]
        nmvs[s] = int(ok.sum())
    axis = {s: V.R(f'{s}.jpg').T @ np.array([0.0, 0.0, 1.0]) for s in train}
    rows, no_pair = [], []
    for s in train:
        if s not in fl:
            raise SystemExit(f'{s} is not among the 937 posed images')
        cand = []
        for j in train:
            if j == s or fl[j] != fl[s]:
                continue
            ang = float(np.degrees(np.arccos(np.clip(axis[s] @ axis[j], -1.0, 1.0))))
            if ang >= R['max_view_angle_deg']:
                continue
            ov = None
            if nmvs[s] >= R['min_overlap_points']:
                u, v, z = V.project(f'{j}.jpg', pts[s])
                ins = (z > 0) & (u >= 0) & (u < M.W) & (v >= 0) & (v < M.H)
                ov = float(ins.mean())
            cand.append((j, ang, ov))
        ok = [c for c in cand if c[2] is not None and c[2] > 0]
        if not ok:
            no_pair.append(dict(view=s, flight=fl[s], candidates_same_flight_under_20deg=len(cand), mvs_points=nmvs[s],
                                why='no candidate' if not cand else ('too few MVS points for the overlap' if nmvs[s] < R['min_overlap_points'] else 'zero overlap')))
            rows.append(dict(view=s, flight=fl[s], pair=None, angle_deg=None, overlap=None, candidates=len(cand), mvs_points=nmvs[s]))
            continue
        best = min(ok, key=lambda c: (abs(c[2] - R['target_overlap']), c[1], c[0]))
        rows.append(dict(view=s, flight=fl[s], pair=best[0], angle_deg=round(best[1], 3), overlap=round(best[2], 4), candidates=len(ok), mvs_points=nmvs[s]))
    ov = np.array([r['overlap'] for r in rows if r['pair']])
    an = np.array([r['angle_deg'] for r in rows if r['pair']])
    fls = sorted({fl[s] for s in train})
    out = dict(site='campus', rule=R, training_views=len(train), paired=int(len(ov)), without_pair=len(no_pair), without_pair_views=no_pair,
               mvs_maps_equal_between_priors='one map for both priors (WIDEN0 geometric depth, stage-0 export a1 rule)',
               overlap_quantiles_5_25_50_75_95=np.percentile(ov, [5, 25, 50, 75, 95]).round(4).tolist() if len(ov) else None,
               angle_quantiles_5_50_95=np.percentile(an, [5, 50, 95]).round(3).tolist() if len(an) else None,
               flights_of_training_views={str(f): int(sum(1 for s in train if fl[s] == f)) for f in fls}, flight_table=table,
               pairs=rows, seconds=round(time.time() - t0, 1), source='mvsfuse/pairs.py main() with the campus views and MVS', scientific_verdict=None)
    dump(L / 'prep/pairs_campus.json', out)
    print('PAIRS', dict(views=len(train), paired=out['paired'], without_pair=len(no_pair), overlap=out['overlap_quantiles_5_25_50_75_95'],
                        angle=out['angle_quantiles_5_50_95'], s=out['seconds']), flush=True)


if __name__ == '__main__':
    {'prior': build_prior, 'pairs': pairs}[sys.argv[1]]()
