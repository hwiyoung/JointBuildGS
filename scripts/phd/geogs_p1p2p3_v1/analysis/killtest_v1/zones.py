"""Zone rasters for diagnostic attribution (evaluation-only; uses UAS reference + prior distances + LoD2 ground plan)."""
import json, numpy as np
from shapely.geometry import shape, Point
from shapely.strtree import STRtree
from shapely.prepared import prep

WORLD_SHIFT = (690953.0, 5336071.0)
CELL = 0.5
DOMAINS = {'P1': ((-23, 7), (-21, 9)), 'P2': ((110, 158), (86, 132)), 'P3': ((-60, -20), (-42, 12))}

def load_footprint_mask_fn(geojson_path, region, buffer_m=0.5):
    d = json.load(open(geojson_path))
    (x0, x1), (y0, y1) = DOMAINS[region]
    from shapely.geometry import box
    dom = box(x0 + WORLD_SHIFT[0], y0 + WORLD_SHIFT[1], x1 + WORLD_SHIFT[0], y1 + WORLD_SHIFT[1])
    polys = [shape(f['geometry']).buffer(buffer_m) for f in d['features'] if shape(f['geometry']).intersects(dom)]
    ids = [f['properties'].get('building_id') for f in d['features'] if shape(f['geometry']).intersects(dom)]
    if not polys:
        return (lambda xy: np.zeros(len(xy), bool)), []
    union = polys[0]
    for p in polys[1:]:
        union = union.union(p)
    pu = prep(union)
    def fn(xy):
        return np.array([pu.contains(Point(x + WORLD_SHIFT[0], y + WORLD_SHIFT[1])) for x, y in xy], bool)
    return fn, ids

def cell_index(xy, region):
    (x0, x1), (y0, y1) = DOMAINS[region]
    ix = np.floor((xy[:, 0] - x0) / CELL).astype(int)
    iy = np.floor((xy[:, 1] - y0) / CELL).astype(int)
    nx = int(np.ceil((x1 - x0) / CELL)); ny = int(np.ceil((y1 - y0) / CELL))
    ix = np.clip(ix, 0, nx - 1); iy = np.clip(iy, 0, ny - 1)
    return ix, iy, nx, ny

def build_zone_raster(region, ref_xyz, ref_to_prior, footprint_fn=None, stale_m=1.5, consistent_m=0.25, elevated_m=2.0):
    """Returns dict with per-cell arrays: prior_state (0 consistent,1 mixed,2 stale,-1 empty), elevated (bool), footprint (bool), ground_z."""
    ix, iy, nx, ny = cell_index(ref_xyz[:, :2], region)
    flat = iy * nx + ix
    n = nx * ny
    cnt = np.bincount(flat, minlength=n)
    # ground z: 5th percentile of z in 5x5 cell window (approx via per-cell min then window min)
    zmin = np.full(n, np.inf); np.minimum.at(zmin, flat, ref_xyz[:, 2])
    zmin2 = zmin.reshape(ny, nx)
    gz = np.full((ny, nx), np.inf)
    for dy in range(-3, 4):
        for dx in range(-3, 4):
            sh = np.full((ny, nx), np.inf)
            ys = slice(max(0, dy), ny + min(0, dy)); yd = slice(max(0, -dy), ny + min(0, -dy))
            xs = slice(max(0, dx), nx + min(0, dx)); xd = slice(max(0, -dx), nx + min(0, -dx))
            sh[yd, xd] = zmin2[ys, xs]
            gz = np.minimum(gz, sh)
    ground_z = gz.reshape(-1)
    h = ref_xyz[:, 2] - ground_z[flat]
    hmed = np.full(n, np.nan)
    order = np.argsort(flat)
    fs = flat[order]; hs = h[order]
    starts = np.searchsorted(fs, np.arange(n)); ends = np.searchsorted(fs, np.arange(n), side='right')
    ds = ref_to_prior[order]
    dmed = np.full(n, np.nan)
    for c in range(n):
        if ends[c] > starts[c]:
            hmed[c] = np.median(hs[starts[c]:ends[c]]); dmed[c] = np.median(ds[starts[c]:ends[c]])
    prior_state = np.full(n, -1, int)
    prior_state[(cnt > 0) & (dmed < consistent_m)] = 0
    prior_state[(cnt > 0) & (dmed >= consistent_m) & (dmed < stale_m)] = 1
    prior_state[(cnt > 0) & (dmed >= stale_m)] = 2
    elevated = (cnt > 0) & (hmed >= elevated_m)
    fp = np.zeros(n, bool)
    if footprint_fn is not None:
        (x0, x1), (y0, y1) = DOMAINS[region]
        cx = x0 + (np.arange(n) % nx + 0.5) * CELL; cy = y0 + (np.arange(n) // nx + 0.5) * CELL
        fp = footprint_fn(np.stack([cx, cy], 1))
    return dict(nx=nx, ny=ny, count=cnt, prior_state=prior_state, elevated=elevated, footprint=fp, ground_z=ground_z, hmed=hmed, dmed=dmed)

def zone_labels(region, raster):
    """Named zones per cell."""
    ps, el, fp, cnt = raster['prior_state'], raster['elevated'], raster['footprint'], raster['count']
    z = np.full(len(ps), 'empty', dtype=object)
    if region == 'P2' or region == 'P3':
        z[(cnt > 0) & fp & (ps == 2)] = 'bldg_stale'
        z[(cnt > 0) & fp & (ps == 0)] = 'bldg_consistent'
        z[(cnt > 0) & fp & (ps == 1)] = 'bldg_mixed'
        z[(cnt > 0) & ~fp & ~el] = 'nonbldg_low'
        z[(cnt > 0) & ~fp & el] = 'nonbldg_elevated'
    else:
        z[(cnt > 0) & (ps == 2) & ~el] = 'stale_now_low'
        z[(cnt > 0) & (ps == 2) & el] = 'stale_elevated'
        z[(cnt > 0) & (ps == 0) & el] = 'consistent_elevated'
        z[(cnt > 0) & (ps == 0) & ~el] = 'consistent_low'
        z[(cnt > 0) & (ps == 1)] = 'mixed'
    return z

def label_points(region, raster, labels, xy):
    ix, iy, nx, ny = cell_index(xy, region)
    return labels[iy * nx + ix]
