"""Probe: true LoD2 footprint of given buildings (shapely, not the overwritten id raster),
overlaps with other footprints, and height statistics over the full footprint.
scientific_verdict: null."""
import json
import sys
from pathlib import Path

import numpy as np
from matplotlib.path import Path as MPath
from shapely.geometry import Polygon
from shapely.ops import unary_union

out = Path(sys.argv[1]); cfg = json.loads(Path(sys.argv[2]).read_text()); ids = sys.argv[3].split(',')
D = dict(np.load(out / 'derived.npz'))
A = dict(np.load(out / 's1' / 'rasters_als_mvs_uls.npz'))
blds = json.loads((out / 's1' / 'lod2_buildings.json').read_text())
g = cfg['grid']; res = g['res_m']
ny, nx = D['dtm'].shape
ec = g['e_min'] + (np.arange(nx) + 0.5) * res; nc = g['n_min'] + (np.arange(ny) + 0.5) * res
EE, NN = np.meshgrid(ec, nc); pts = np.column_stack([EE.ravel(), NN.ravel()])
fps = {}
for b in blds:
    ps = [Polygon(np.asarray(p['ext'])[:, :2], [np.asarray(h)[:, :2] for h in p['holes']]).buffer(0) for p in b['surfaces']['ground']]
    fps[b['id']] = unary_union([p for p in ps if p.area > 0]) if ps else None
dtm = D['dtm'].astype(float)
for bid in ids:
    bid = bid if bid.startswith('DEBY') else 'DEBY_LOD2_' + bid
    b = next(x for x in blds if x['id'] == bid)
    fp = fps[bid]
    print('==', bid, 'creationDate', b['creationDate'], 'roofType', b['roofType'], 'measuredHeight', b['measuredHeight'], 'function', b['function'],
          'HoeheDach', b['attrs'].get('HoeheDach'), 'HoeheGrund', b['attrs'].get('HoeheGrund'), 'dq', b['attrs'].get('DatenquelleDachhoehe'), 'methode', b['attrs'].get('Methode'))
    print('  footprint area %.1f m2, centroid %.1f %.1f, z range %.2f..%.2f' % (fp.area, fp.centroid.x, fp.centroid.y, b['zmin'], b['zmax']))
    ov = [(o, fp.intersection(f).area) for o, f in fps.items() if o != bid and f is not None and f.intersects(fp)]
    ov = [(o, a) for o, a in ov if a > 0.5]
    print('  overlaps:', [(o.replace('DEBY_LOD2_', ''), round(a, 1)) for o, a in ov])
    polys = list(fp.geoms) if fp.geom_type == 'MultiPolygon' else [fp]
    m = np.zeros(len(pts), bool)
    for pg in polys:
        s = MPath(np.asarray(pg.exterior.coords)).contains_points(pts)
        for h in pg.interiors:
            s &= ~MPath(np.asarray(h.coords)).contains_points(pts)
        m |= s
    m = m.reshape(ny, nx)
    for k in ('als', 'uls', 'mvs', 'lod'):
        h = (D[k].astype(float) - dtm)[m]; h = h[np.isfinite(h)]
        if len(h):
            print('  h_%s med %.2f p10 %.2f p90 %.2f (n %d)' % (k, np.median(h), np.quantile(h, .1), np.quantile(h, .9), len(h)))
    n = A['als_n'][m].sum()
    print('  ALS points %d: c2 %.2f c6 %.2f c20 %.2f; ULS pts %d; ULS multi %.2f' % (n, A['als_n_c2'][m].sum() / max(n, 1), A['als_n_c6'][m].sum() / max(n, 1),
                                                                                 A['als_n_c20'][m].sum() / max(n, 1), A['uls_n'][m].sum(), np.nanmean(D['veg'][m])))
