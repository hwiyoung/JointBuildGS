"""판 다 cells: VastGaussian progressive partition on the ground plane, 20 % boundary expansion,
position- then visibility-based camera selection (>= 25 % projected coverage). Writes /tu/cells/cells.json.

  python tu_cells.py partition
"""
import sys

import cv2

from tu_common import *
from tu_campus import CAMPUS, cameras, read_points3d_bin, scope, stem


def boxes():
    out = {}
    for site in SITES:
        p = PH / 'main_gtjudge_v1/PHD-MAIN-GTJUDGE-v1/views' / f'{site}.json'
        b = json.loads(p.read_text())['box']
        out[site] = dict(min=b[0], max=b[1], source=str(p))
    return out


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
    hull = cv2.convexHull(np.c_[u, v].astype(np.float32)).reshape(-1, 2)
    return clip_polygon(hull, cam['W'], cam['H']) / float(cam['W'] * cam['H'])


def partition():
    c = cfg()
    split = json.loads((CAMPUS / 'split.json').read_text())
    train, test = split['train'], split['test']
    cams = {x['name']: x for x in cameras(train + test)}
    centre = {n: (-np.asarray(cams[n]['W2C'], float)[:3, :3].T @ np.asarray(cams[n]['W2C'], float)[:3, 3]) for n in cams}
    Ct = np.array([centre[n] for n in train])
    k = int(round(len(train) / 200))
    m, n = 2, 2
    assert m * n == k, (k, m, n)
    sfm, _ = read_points3d_bin(WD / 'mvs/full/sparse/points3D.bin')
    outer_lo = np.percentile(sfm[:, :2], .5, axis=0); outer_hi = np.percentile(sfm[:, :2], 99.5, axis=0)
    xs = np.sort(Ct[:, 0])
    xcut = [-np.inf] + [float(np.median(xs))] + [np.inf] if m == 2 else None
    cells = []
    cid = 0
    for i in range(m):
        colmask = (Ct[:, 0] >= xcut[i]) & (Ct[:, 0] < xcut[i + 1])
        ycol = np.sort(Ct[colmask, 1])
        ycut = [-np.inf, float(np.median(ycol)), np.inf]
        for j in range(n):
            mask = colmask & (Ct[:, 1] >= ycut[j]) & (Ct[:, 1] < ycut[j + 1])
            lo = np.array([xcut[i], ycut[j]]); hi = np.array([xcut[i + 1], ycut[j + 1]])
            own = Ct[mask, :2]
            ext = own.max(0) - own.min(0)
            elo = lo.copy(); ehi = hi.copy()
            for a in range(2):
                if np.isfinite(lo[a]):
                    elo[a] = lo[a] - .2 * ext[a]
                if np.isfinite(hi[a]):
                    ehi[a] = hi[a] + .2 * ext[a]
            blo = np.where(np.isfinite(elo), elo, outer_lo); bhi = np.where(np.isfinite(ehi), ehi, outer_hi)
            ins = (sfm[:, 0] >= blo[0]) & (sfm[:, 0] < bhi[0]) & (sfm[:, 1] >= blo[1]) & (sfm[:, 1] < bhi[1])
            z0, z1 = np.percentile(sfm[ins, 2], [.5, 99.5])
            box_lo = np.r_[blo, z0]; box_hi = np.r_[bhi, z1]
            pos = [nm for nm in train if elo[0] <= centre[nm][0] < ehi[0] and elo[1] <= centre[nm][1] < ehi[1]]
            vis = []
            cov = {}
            for nm in train:
                if nm in pos:
                    continue
                f = coverage(cams[nm], box_lo, box_hi)
                cov[nm] = f
                if f >= .25:
                    vis.append(nm)
            own_names = [nm for nm, keep in zip(train, mask) if keep]
            tst = [nm for nm in test if elo[0] <= centre[nm][0] < ehi[0] and elo[1] <= centre[nm][1] < ehi[1]]
            cells.append(dict(id=cid, column=i, row=j, original_min=lo.tolist(), original_max=hi.tolist(),
                              expanded_min=elo.tolist(), expanded_max=ehi.tolist(), projection_box_min=box_lo.tolist(), projection_box_max=box_hi.tolist(),
                              own_cameras=len(own_names), position_selected=len(pos), visibility_added=len(vis), images=sorted(pos + vis),
                              test_images=sorted(tst), coverage_quantiles_of_others=np.quantile(list(cov.values()), [.1, .5, .9]).tolist() if cov else None))
            cid += 1
    # evaluation boxes against original cell boundaries (segments as degenerate rectangles)
    BIG = 1e6
    fin = lambda v: float(np.clip(v, -BIG, BIG))
    segs = []
    for cc in cells:
        lo, hi = cc['original_min'], cc['original_max']
        for a in range(2):
            for v in [lo[a], hi[a]]:
                if not np.isfinite(v):
                    continue
                if a == 0:
                    segs.append(dict(cell=cc['id'], axis='x', at=float(v), lo=[float(v), fin(lo[1])], hi=[float(v), fin(hi[1])]))
                else:
                    segs.append(dict(cell=cc['id'], axis='y', at=float(v), lo=[fin(lo[0]), float(v)], hi=[fin(hi[0]), float(v)]))
    def rect_dist(alo, ahi, blo, bhi):
        dx = max(blo[0] - ahi[0], alo[0] - bhi[0], 0.); dy = max(blo[1] - ahi[1], alo[1] - bhi[1], 0.)
        return float(np.hypot(dx, dy))
    rel = []
    for site, b in boxes().items():
        lo, hi = list(map(float, b['min'][:2])), list(map(float, b['max'][:2]))
        touch = [cc['id'] for cc in cells if rect_dist(lo, hi, [fin(v) for v in cc['original_min']], [fin(v) for v in cc['original_max']]) == 0 and
                 not (hi[0] <= cc['original_min'][0] or lo[0] >= cc['original_max'][0] or hi[1] <= cc['original_min'][1] or lo[1] >= cc['original_max'][1])]
        d = [dict(segment=sg, distance_m=rect_dist(lo, hi, sg['lo'], sg['hi'])) for sg in segs]
        dmin = min(x['distance_m'] for x in d)
        rel.append(dict(site=site, box_min=lo, box_max=hi, cells=touch, boundary_crosses_box=len(touch) > 1,
                        nearest_boundary_distance_m=dmin, within_2m_band=dmin <= 2.,
                        nearest=[x for x in d if x['distance_m'] == dmin][:2]))
    out = dict(at=now(), rule=c['cells'], k=k, m=m, n=n, x_cut=xcut[1], y_cuts=None, train_images=len(train),
               outer_limits_sfm_p05_p995=[outer_lo.tolist(), outer_hi.tolist()], cells=cells, boundaries=segs, evaluation_boxes=rel,
               images_per_cell=[len(cc['images']) for cc in cells], scientific_verdict=None)
    def clean(v):
        if isinstance(v, dict):
            return {a: clean(b) for a, b in v.items()}
        if isinstance(v, list):
            return [clean(b) for b in v]
        if isinstance(v, float) and not np.isfinite(v):
            return 1e9 if v > 0 else -1e9
        return v
    out = clean(out)
    cells = out['cells']
    dump(TU / 'cells/cells.json', out)
    dump(D / 'tables/cells.json', {k2: v for k2, v in out.items() if k2 != 'cells'} | dict(cells=[{k3: v3 for k3, v3 in cc.items() if k3 not in ['images', 'test_images']} for cc in cells]))
    print('CELLS', [len(cc['images']) for cc in cells], [(r['site'], r['cells'], r['nearest_boundary_distance_m']) for r in rel], flush=True)


if __name__ == '__main__':
    dict(partition=partition)[sys.argv[1]](*sys.argv[2:])
