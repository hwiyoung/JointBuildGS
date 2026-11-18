"""PHD-MAIN-BASE151-v1 2.2: the prior surfaces of the four cells (jointbuildgs:dev, CPU; run_cpu.sh). Shared by GeoGS, CDGS and LGDM.

  python b151_prior.py [<cell> ...]        -> /b151/prior/cell<k>/{lod2_mesh.npz, als_mesh.npz, receipt.json}

Source (decision request 3 of 준비.md): the surfaces JUDGECHECK-v2 measured the 151 buildings' cases against,
WD holdout/internal/prior_tiles/<tile>/{lod2,als}_mesh.npz (100 m tiles + 10 m buffer, made with the unchanged s02 mesh function).
  - tile union: a triangle of a tile is kept when its centroid xy lies in the tile's own 100 m core [E0, E0+100) x [N0, N0+100)
    (local = EPSG:25832 - (690953, 5336071)), so every place is taken from exactly one tile;
  - cell range: triangles whose centroid xy lies in the expanded cell + 20 m (the s02 rule 'range + 20 m' of the site meshes); the
    expanded cell's unbounded outer edges keep every tile on that side;
  - registration: LoD2 shift 0 (JUDGECHECK-v2: shift zeros for LoD2); ALS: every vertex moved by the als_shift_m of the building of the
    nearest JUDGECHECK-v2 ALS patch (xy; geometry_raw/<tile>__ALS.npz shift_m = stage0/buildings.json als_shift_m, 0-7 cm, 8 regions);
  - kept per triangle: LoD2 tri_type (0, 1 polygons, 2 caps), source tile, building name; ALS vertex class (2 ground / 6 building),
    building_tri as in the tile file.
Vertices are re-indexed per cell (only vertices of kept faces). scientific_verdict: null
"""
import sys

import numpy as np
from scipy.spatial import cKDTree

from b151_common import *

WI = WD / 'holdout/internal'
E0, N0 = 690953.0, 5336071.0
MARGIN = 20.0


def tiles():
    out = []
    for d in sorted((WI / 'prior_tiles').iterdir()):
        e, n = (int(x) for x in d.name.split('_'))
        lo = np.array([e * 100 - E0, n * 100 - N0])
        out.append((d.name, lo, lo + 100.0))
    return out


def als_shift_tree():
    xy, sh = [], []
    for p in sorted((JC2 / 'geometry_raw').glob('*__ALS.npz')):
        z = np.load(p)
        xy.append(z['centre'][:, :2]); sh.append(z['shift_m'])
    return cKDTree(np.concatenate(xy)), np.concatenate(sh)


def main(*which):
    c = cfg()
    T = tiles()
    tree, shifts = als_shift_tree()
    for cell in c['cells']['per_cell']:
        k = cell['id']
        if which and str(k) not in which:
            continue
        lo = np.array(cell['expanded_min']) - MARGIN
        hi = np.array(cell['expanded_max']) + MARGIN
        rec = dict(at=now(), cell=k, range_min=lo.tolist(), range_max=hi.tolist(), margin_m=MARGIN, source=str(WI / 'prior_tiles'), tiles={})
        for prior, name in [('LoD2', 'lod2_mesh.npz'), ('ALS', 'als_mesh.npz')]:
            Vs, Fs, extra, nv = [], [], {}, 0
            for tid, tlo, thi in T:
                if (tlo >= hi).any() or (thi <= lo).any():
                    continue
                m = np.load(WI / 'prior_tiles' / tid / name)
                V, F = m['V'].astype(np.float64), m['F'].astype(np.int64)
                cen = V[F].mean(1)[:, :2]
                keep = ((cen >= tlo) & (cen < thi)).all(1) & ((cen >= lo) & (cen < hi)).all(1)
                if not keep.any():
                    continue
                F = F[keep]
                used = np.unique(F)
                remap = np.full(len(V), -1, np.int64)
                remap[used] = np.arange(len(used)) + nv
                Vs.append(V[used]); Fs.append(remap[F]); nv += len(used)
                if prior == 'LoD2':
                    bn = m['building_names']
                    tb = m['tri_building'][keep]
                    extra.setdefault('tri_type', []).append(m['tri_type'][keep].astype(np.int8))
                    extra.setdefault('tri_building', []).append(np.where(tb >= 0, bn[np.clip(tb, 0, None)], ''))
                else:
                    extra.setdefault('cls', []).append(m['cls'][used])
                    extra.setdefault('building_tri', []).append(m['building_tri'][keep])
                extra.setdefault('tri_tile', []).append(np.full(int(keep.sum()), tid))
                rec['tiles'].setdefault(prior, {})[tid] = int(keep.sum())
            V = np.concatenate(Vs); F = np.concatenate(Fs)
            ex = {key: np.concatenate(v) for key, v in extra.items()}
            if prior == 'ALS':
                _, ii = tree.query(V[:, :2], workers=8)
                sh = shifts[ii]
                V = V + sh
                ex['vertex_shift'] = sh.astype(np.float32)
            else:
                sh = np.zeros((len(V), 3))
            T3 = V[F]
            area = 0.5 * np.linalg.norm(np.cross(T3[:, 1] - T3[:, 0], T3[:, 2] - T3[:, 0]), axis=1)
            out = B / 'prior' / f'cell{k}' / name
            out.parent.mkdir(parents=True, exist_ok=True)
            np.savez_compressed(out, V=V, F=F, **ex)
            r = dict(vertices=int(len(V)), faces=int(len(F)), area_m2=float(area.sum()), sha256=sha(out),
                     shift_distinct=[list(map(float, s)) for s in np.unique(np.round(sh, 6), axis=0)])
            if prior == 'LoD2':
                r.update(faces_by_type={str(t): int((ex['tri_type'] == t).sum()) for t in [0, 1, 2]},
                         buildings=int(len(set(ex['tri_building'].tolist()) - {''})))
            else:
                b6 = (ex['cls'][F] == 6).any(1)
                r.update(faces_with_class6_vertex=int(b6.sum()), building_tri=int(ex['building_tri'].sum()))
            rec[prior] = r
            print('PRIOR', k, prior, r['vertices'], r['faces'], round(r['area_m2']), flush=True)
        rec['scientific_verdict'] = None
        dump(B / 'prior' / f'cell{k}' / 'receipt.json', rec)


if __name__ == '__main__':
    main(*sys.argv[1:])
