"""PHD-MAIN-DESIGN-REALCHANGE-SURVEY-v1 step 1: common 0.5 m height grids.

Reads only existing inputs (ALS 2022, ULS 2024-12-17, current-image MVS dense
cloud, LoD2 CityGML) and writes new grids into the task output folder.
No training, no input mutation.  scientific_verdict: null.

Layers (EPSG:25832, row 0 = south edge, heights in the working frame where
ALS/LoD2 get the inherited +45.7 m scalar bridge, MVS gets local z + 604):
  als_*  : zmax (non-noise), zmax_c6, zsum/n ground c2, counts per class,
           multi-return count; per-tile GPS time range.
  uls_*  : zmax, zmin, zmax_last, counts, multi-return count, mean RGB.
  mvs_*  : p90, zmax, count, mean RGB.
  lod2_* : roof plane max z, footprint building index.
"""
import argparse
import datetime
import hashlib
import json
import platform
import sys
import time
from pathlib import Path

import laspy
import numpy as np
from lxml import etree
from matplotlib.path import Path as MplPath

GML = '{http://www.opengis.net/gml}'
BLDG = '{http://www.opengis.net/citygml/building/1.0}'
GEN = '{http://www.opengis.net/citygml/generics/1.0}'
CORE = '{http://www.opengis.net/citygml/1.0}'


def sha256(path, limit=None):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 22), b''):
            h.update(chunk)
    return h.hexdigest()


def gps_to_utc(t):
    # LAS adjusted standard GPS time: GPS seconds - 1e9; GPS-UTC = 18 s (2017+).
    return (datetime.datetime(1980, 1, 6) + datetime.timedelta(seconds=float(t) + 1e9 - 18)).isoformat()


class Grid:
    def __init__(self, g):
        self.e0, self.e1, self.n0, self.n1, self.res = g['e_min'], g['e_max'], g['n_min'], g['n_max'], g['res_m']
        self.nx = int(round((self.e1 - self.e0) / self.res))
        self.ny = int(round((self.n1 - self.n0) / self.res))
        self.size = self.nx * self.ny

    def index(self, e, n):
        ix = np.floor((e - self.e0) / self.res).astype(np.int64)
        iy = np.floor((n - self.n0) / self.res).astype(np.int64)
        ok = (ix >= 0) & (ix < self.nx) & (iy >= 0) & (iy < self.ny)
        return iy * self.nx + ix, ok

    def centres(self):
        e = self.e0 + (np.arange(self.nx) + 0.5) * self.res
        n = self.n0 + (np.arange(self.ny) + 0.5) * self.res
        return e, n


def acc_max(arr, idx, val):
    np.maximum.at(arr, idx, val)


def acc_min(arr, idx, val):
    np.minimum.at(arr, idx, val)


def process_als(cfg, grid, art, layers, receipt):
    noise = set(cfg['rasters']['als_noise_classes'])
    add = cfg['vertical']['als_add_m']
    names = ['als_zmax', 'als_zmax_c6', 'als_zmin']
    for k in names:
        layers[k] = np.full(grid.size, np.nan if k != 'als_zmin' else np.inf, np.float64)
    layers['als_zmax'][:] = -np.inf
    layers['als_zmax_c6'][:] = -np.inf
    for k in ['als_zsum_c2', 'als_n', 'als_n_c2', 'als_n_c6', 'als_n_c20', 'als_n_other', 'als_n_multi']:
        layers[k] = np.zeros(grid.size, np.float64)
    tiles = []
    for rel in cfg['inputs']['als_tiles']:
        p = art / rel
        t0 = time.time()
        las = laspy.read(str(p))
        e = np.asarray(las.x); n = np.asarray(las.y); z = np.asarray(las.z) + add
        cls = np.asarray(las.classification); nr = np.asarray(las.number_of_returns)
        gps = np.asarray(las.gps_time)
        stem = p.stem.split('_')
        te0, tn0 = float(stem[0]) * 1000.0, float(stem[1]) * 1000.0
        nominal = (e >= te0) & (e < te0 + 1000.0) & (n >= tn0) & (n < tn0 + 1000.0)
        idx, ok = grid.index(e, n)
        keep = ok & nominal & ~np.isin(cls, list(noise))
        u, k = np.unique(cls[nominal], return_counts=True)
        dates = sorted({gps_to_utc(x)[:10] for x in np.quantile(gps, [0, 0.001, 0.5, 0.999, 1])})
        tiles.append(dict(file=rel, sha256=sha256(p), points=int(len(e)), nominal_points=int(nominal.sum()),
                          nominal_density_pts_m2=float(nominal.sum() / 1e6),
                          class_counts_nominal={int(a): int(b) for a, b in zip(u, k)},
                          gps_utc_min=gps_to_utc(gps.min()), gps_utc_max=gps_to_utc(gps.max()), gps_dates=dates,
                          header_creation_date=str(las.header.creation_date), seconds=round(time.time() - t0, 1)))
        i = idx[keep]; zz = z[keep]; cc = cls[keep]
        acc_max(layers['als_zmax'], i, zz)
        acc_min(layers['als_zmin'], i, zz)
        layers['als_n'] += np.bincount(i, minlength=grid.size)
        layers['als_n_multi'] += np.bincount(i[nr[keep] > 1], minlength=grid.size)
        m2 = cc == cfg['rasters']['als_ground_class']
        layers['als_zsum_c2'] += np.bincount(i[m2], weights=zz[m2], minlength=grid.size)
        layers['als_n_c2'] += np.bincount(i[m2], minlength=grid.size)
        m6 = cc == cfg['rasters']['als_building_class']
        acc_max(layers['als_zmax_c6'], i[m6], zz[m6])
        layers['als_n_c6'] += np.bincount(i[m6], minlength=grid.size)
        m20 = cc == 20
        layers['als_n_c20'] += np.bincount(i[m20], minlength=grid.size)
        mo = ~(m2 | m6 | m20)
        layers['als_n_other'] += np.bincount(i[mo], minlength=grid.size)
        print('ALS', rel, len(e), 'in grid', int(keep.sum()), round(time.time() - t0, 1), 's', flush=True)
        del las, e, n, z, cls, nr, gps
    for k in ['als_zmax', 'als_zmax_c6']:
        layers[k][~np.isfinite(layers[k])] = np.nan
    layers['als_zmin'][~np.isfinite(layers['als_zmin'])] = np.nan
    receipt['als_tiles'] = tiles


def process_uls(cfg, grid, art, layers, receipt, key, prefix):
    p = art / cfg['inputs'][key]
    t0 = time.time()
    layers[prefix + 'zmax'] = np.full(grid.size, -np.inf)
    layers[prefix + 'zmin'] = np.full(grid.size, np.inf)
    layers[prefix + 'zmax_last'] = np.full(grid.size, -np.inf)
    for k in ['n', 'n_multi', 'rsum', 'gsum', 'bsum']:
        layers[prefix + k] = np.zeros(grid.size, np.float64)
    gmin, gmax, total, ingrid = np.inf, -np.inf, 0, 0
    classes = {}
    with laspy.open(str(p)) as f:
        for pts in f.chunk_iterator(10_000_000):
            e = np.asarray(pts.x); n = np.asarray(pts.y); z = np.asarray(pts.z)
            idx, ok = grid.index(e, n)
            total += len(e); ingrid += int(ok.sum())
            gps = np.asarray(pts.gps_time); gmin = min(gmin, gps.min()); gmax = max(gmax, gps.max())
            cls = np.asarray(pts.classification)
            for a, b in zip(*np.unique(cls, return_counts=True)):
                classes[int(a)] = classes.get(int(a), 0) + int(b)
            i = idx[ok]; zz = z[ok]
            rn = np.asarray(pts.return_number)[ok]; nr = np.asarray(pts.number_of_returns)[ok]
            acc_max(layers[prefix + 'zmax'], i, zz)
            acc_min(layers[prefix + 'zmin'], i, zz)
            last = rn == nr
            acc_max(layers[prefix + 'zmax_last'], i[last], zz[last])
            layers[prefix + 'n'] += np.bincount(i, minlength=grid.size)
            layers[prefix + 'n_multi'] += np.bincount(i[nr > 1], minlength=grid.size)
            for c, k in (('red', 'rsum'), ('green', 'gsum'), ('blue', 'bsum')):
                layers[prefix + k] += np.bincount(i, weights=np.asarray(getattr(pts, c))[ok] / 256.0, minlength=grid.size)
            print(prefix, total, round(time.time() - t0, 1), 's', flush=True)
    for k in ['zmax', 'zmin', 'zmax_last']:
        a = layers[prefix + k]; a[~np.isfinite(a)] = np.nan
    receipt[prefix + 'source'] = dict(file=cfg['inputs'][key], sha256=sha256(p), points=total, points_in_grid=ingrid,
                                      gps_utc_min=gps_to_utc(gmin), gps_utc_max=gps_to_utc(gmax), class_counts=classes,
                                      seconds=round(time.time() - t0, 1))


def process_mvs(cfg, grid, art, layers, receipt):
    p = art / cfg['inputs']['mvs_fused']
    t0 = time.time()
    with open(p, 'rb') as f:
        header = b''
        while b'end_header' not in header:
            header += f.readline()
        offset = len(header)
    count = int([l for l in header.decode().splitlines() if l.startswith('element vertex')][0].split()[-1])
    dt = np.dtype([('x', '<f4'), ('y', '<f4'), ('z', '<f4'), ('r', 'u1'), ('g', 'u1'), ('b', 'u1')])
    mm = np.memmap(p, dtype=dt, mode='r', offset=offset, shape=(count,))
    sh = cfg['world_shift_xyz_m']
    e = mm['x'].astype(np.float64) + sh[0]; n = mm['y'].astype(np.float64) + sh[1]; z = mm['z'].astype(np.float64) + sh[2]
    idx, ok = grid.index(e, n)
    i = idx[ok]; zz = z[ok]
    order = np.lexsort((zz, i))
    i_s = i[order]; z_s = zz[order]
    cnt = np.bincount(i_s, minlength=grid.size)
    start = np.concatenate([[0], np.cumsum(cnt)[:-1]])
    has = cnt > 0
    p90 = np.full(grid.size, np.nan)
    pos = start[has] + np.floor(0.9 * (cnt[has] - 1)).astype(np.int64)
    p90[has] = z_s[pos]
    zmax = np.full(grid.size, np.nan)
    zmax[has] = z_s[start[has] + cnt[has] - 1]
    layers['mvs_p90'] = p90
    layers['mvs_zmax'] = zmax
    layers['mvs_n'] = cnt.astype(np.float64)
    for c, k in (('r', 'mvs_rsum'), ('g', 'mvs_gsum'), ('b', 'mvs_bsum')):
        layers[k] = np.bincount(i, weights=mm[c][ok].astype(np.float64), minlength=grid.size)
    receipt['mvs_source'] = dict(file=cfg['inputs']['mvs_fused'], sha256=sha256(p), points=count, points_in_grid=int(ok.sum()),
                                 epoch='2024-12-17 (937 current images)', seconds=round(time.time() - t0, 1))
    print('MVS', count, int(ok.sum()), round(time.time() - t0, 1), 's', flush=True)


def poslist(el):
    pl = el.find('.//' + GML + 'posList')
    if pl is not None and pl.text:
        v = np.array(pl.text.split(), float)
        return v.reshape(-1, 3)
    pos = el.findall('.//' + GML + 'pos')
    if pos:
        return np.array([[float(x) for x in q.text.split()] for q in pos])
    return None


def polygons_of(surface_el):
    out = []
    for poly in surface_el.iter(GML + 'Polygon'):
        ext = poly.find(GML + 'exterior')
        if ext is None:
            continue
        ring = poslist(ext)
        if ring is None or len(ring) < 4:
            continue
        holes = []
        for it in poly.findall(GML + 'interior'):
            h = poslist(it)
            if h is not None and len(h) >= 4:
                holes.append(h)
        out.append((ring, holes))
    return out


def parse_lod2(cfg, art, grid, receipt):
    margin = 20.0
    blds = []
    t0 = time.time()
    files = []
    for rel in cfg['inputs']['lod2_tiles']:
        p = art / rel
        files.append(dict(file=rel, sha256=sha256(p)))
        for _, el in etree.iterparse(str(p), events=('end',), tag=BLDG + 'Building'):
            if el.getparent() is not None and el.getparent().tag == BLDG + 'consistsOfBuildingPart':
                continue  # parts are visited through their parent building
            bid = el.get(GML + 'id')
            attrs = {}
            for sa in el.findall(GEN + 'stringAttribute') + el.findall(GEN + 'doubleAttribute') + el.findall(GEN + 'intAttribute'):
                v = sa.find(GEN + 'value')
                attrs[sa.get('name')] = v.text if v is not None else None
            cd = el.find(CORE + 'creationDate')
            rec = dict(id=bid, creationDate=cd.text if cd is not None else None, attrs=attrs,
                       function=(el.findtext(BLDG + 'function')), roofType=el.findtext(BLDG + 'roofType'),
                       measuredHeight=el.findtext(BLDG + 'measuredHeight'), storeys=el.findtext(BLDG + 'storeysAboveGround'),
                       parts=[bp.get(GML + 'id') for bp in el.iter(BLDG + 'BuildingPart')])
            surf = {'roof': [], 'wall': [], 'ground': [], 'other': []}
            for tag, key in ((BLDG + 'RoofSurface', 'roof'), (BLDG + 'WallSurface', 'wall'), (BLDG + 'GroundSurface', 'ground'),
                             (BLDG + 'ClosureSurface', 'other'), (BLDG + 'OuterCeilingSurface', 'other'), (BLDG + 'OuterFloorSurface', 'other')):
                for s in el.iter(tag):
                    for ring, holes in polygons_of(s):
                        surf[key].append(dict(id=s.get(GML + 'id'), ext=ring, holes=holes))
            allv = [p_['ext'] for k in surf for p_ in surf[k]]
            if allv:
                v = np.vstack(allv)
                if (v[:, 0].max() >= grid.e0 - margin and v[:, 0].min() <= grid.e1 + margin and
                        v[:, 1].max() >= grid.n0 - margin and v[:, 1].min() <= grid.n1 + margin):
                    rec['surfaces'] = surf
                    rec['bbox'] = [float(v[:, 0].min()), float(v[:, 1].min()), float(v[:, 0].max()), float(v[:, 1].max())]
                    rec['zmin'] = float(v[:, 2].min()); rec['zmax'] = float(v[:, 2].max())
                    rec['tile'] = rel
                    blds.append(rec)
            el.clear()
            while el.getprevious() is not None:
                del el.getparent()[0]
    receipt['lod2_tiles'] = files
    receipt['lod2_parse_seconds'] = round(time.time() - t0, 1)
    print('LoD2 buildings in domain', len(blds), round(time.time() - t0, 1), 's', flush=True)
    return blds


def cells_in_polygon(grid, ring2d, holes2d):
    e, n = grid.centres()
    x0, y0 = ring2d[:, 0].min(), ring2d[:, 1].min()
    x1, y1 = ring2d[:, 0].max(), ring2d[:, 1].max()
    ix0 = max(0, int(np.floor((x0 - grid.e0) / grid.res)) - 1); ix1 = min(grid.nx, int(np.ceil((x1 - grid.e0) / grid.res)) + 1)
    iy0 = max(0, int(np.floor((y0 - grid.n0) / grid.res)) - 1); iy1 = min(grid.ny, int(np.ceil((y1 - grid.n0) / grid.res)) + 1)
    if ix1 <= ix0 or iy1 <= iy0:
        return None, None, None
    ee, nn = np.meshgrid(e[ix0:ix1], n[iy0:iy1])
    pts = np.column_stack([ee.ravel(), nn.ravel()])
    inside = MplPath(ring2d).contains_points(pts)
    for h in holes2d:
        inside &= ~MplPath(h).contains_points(pts)
    iy, ix = np.divmod(np.arange(len(pts)), ix1 - ix0)
    flat = (iy + iy0) * grid.nx + (ix + ix0)
    return flat[inside], pts[inside, 0], pts[inside, 1]


def rasterize_lod2(cfg, grid, blds, layers):
    add = cfg['vertical']['lod2_add_m']
    roof = np.full(grid.size, -np.inf)
    fid = np.full(grid.size, -1, np.int32)
    for bi, b in enumerate(blds):
        polys = b['surfaces']['ground'] or []
        if not polys:  # fall back to roof projections
            polys = b['surfaces']['roof']
        for p in polys:
            flat, _, _ = cells_in_polygon(grid, p['ext'][:, :2], [h[:, :2] for h in p['holes']])
            if flat is not None and len(flat):
                fid[flat] = bi
        for p in b['surfaces']['roof']:
            ring = p['ext']
            A = np.column_stack([ring[:, 0] - ring[:, 0].mean(), ring[:, 1] - ring[:, 1].mean(), np.ones(len(ring))])
            # plane fit; skip near-vertical polygons (no stable z = f(x, y))
            ext = np.ptp(ring[:, :2], axis=0)
            if min(ext.max(), 1e9) < 0.3:
                continue
            coef, *_ = np.linalg.lstsq(A, ring[:, 2], rcond=None)
            if np.hypot(coef[0], coef[1]) > 20:
                continue
            flat, xe, yn = cells_in_polygon(grid, ring[:, :2], [h[:, :2] for h in p['holes']])
            if flat is None or not len(flat):
                continue
            zc = coef[0] * (xe - ring[:, 0].mean()) + coef[1] * (yn - ring[:, 1].mean()) + coef[2] + add
            np.maximum.at(roof, flat, zc)
    roof[~np.isfinite(roof)] = np.nan
    layers['lod2_roof'] = roof
    layers['lod2_fid'] = fid


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--config', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--only', default='als,uls,mvs,lod2')
    args = ap.parse_args()
    if not Path('/.dockerenv').exists():
        raise RuntimeError('Docker execution required')
    cfg = json.loads(Path(args.config).read_text())
    art = Path(cfg['artifact_root_container'])
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    grid = Grid(cfg['grid'])
    receipt = dict(task_id=cfg['task_id'], scientific_verdict=None, step='s1_rasters', started=datetime.datetime.now().isoformat(),
                   grid=dict(nx=grid.nx, ny=grid.ny, **cfg['grid']), python=sys.version, platform=platform.platform(),
                   numpy=np.__version__, laspy=laspy.__version__)
    layers = {}
    only = set(args.only.split(','))
    T = {}
    if 'als' in only:
        t = time.time(); process_als(cfg, grid, art, layers, receipt); T['als'] = time.time() - t
    if 'uls' in only:
        t = time.time(); process_uls(cfg, grid, art, layers, receipt, 'uls_nadir', 'uls_'); T['uls'] = time.time() - t
    if 'mvs' in only:
        t = time.time(); process_mvs(cfg, grid, art, layers, receipt); T['mvs'] = time.time() - t
    if 'lod2' in only:
        t = time.time()
        blds = parse_lod2(cfg, art, grid, receipt)
        rasterize_lod2(cfg, grid, blds, layers)
        slim = []
        for b in blds:
            s = {k: v for k, v in b.items() if k != 'surfaces'}
            s['surfaces'] = {k: [dict(id=p['id'], ext=np.round(p['ext'], 3).tolist(), holes=[np.round(h, 3).tolist() for h in p['holes']])
                                 for p in v] for k, v in b['surfaces'].items()}
            slim.append(s)
        (out / 'lod2_buildings.json').write_text(json.dumps(slim))
        receipt['lod2_buildings'] = len(blds)
        T['lod2'] = time.time() - t
    shape = (grid.ny, grid.nx)
    np.savez_compressed(out / ('rasters_%s.npz' % '_'.join(sorted(only))),
                        **{k: (v.reshape(shape).astype(np.float32) if v.dtype != np.int32 else v.reshape(shape)) for k, v in layers.items()})
    receipt['seconds'] = {k: round(v, 1) for k, v in T.items()}
    receipt['finished'] = datetime.datetime.now().isoformat()
    (out / ('receipt_s1_%s.json' % '_'.join(sorted(only)))).write_text(json.dumps(receipt, indent=1, ensure_ascii=False))
    print('done', receipt['seconds'], flush=True)


if __name__ == '__main__':
    main()
