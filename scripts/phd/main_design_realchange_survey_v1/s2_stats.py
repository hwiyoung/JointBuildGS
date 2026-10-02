"""PHD-MAIN-DESIGN-REALCHANGE-SURVEY-v1 step 2: building / region statistics.

Inputs: s1 grids + LoD2 building list.  Outputs (new files only):
  derived.npz            DSMs used for every figure and statistic
  offsets.json           vertical agreement of the sources on bare ground / flat roofs
  buildings.csv          per LoD2 building: current-minus-prior statistics
  components.csv         height-change components outside LoD2 footprints
  regions.json           R1-R5 and B0 geometry, buildings inside, densities, vintages
Candidate rules (stated in the config before the result was read):
  thresholds 1.0 / 2.5 m, connected area >= 25 m2, ULS multi-return fraction < 0.3.
These are descriptive screens, not change verdicts.  scientific_verdict: null.
"""
import argparse
import csv
import datetime
import json
import time
import warnings
from pathlib import Path

import numpy as np
import scipy.ndimage as ndi
from shapely.geometry import Polygon, box
from shapely.ops import unary_union

warnings.simplefilter('ignore', RuntimeWarning)


def nanmedian3(a):
    p = np.pad(a, 1, mode='constant', constant_values=np.nan)
    w = np.lib.stride_tricks.sliding_window_view(p, (3, 3)).reshape(a.shape[0], a.shape[1], 9)
    return np.nanmedian(w, axis=2)


def nanmean3(a):
    p = np.pad(a, 1, mode='constant', constant_values=np.nan)
    w = np.lib.stride_tricks.sliding_window_view(p, (3, 3)).reshape(a.shape[0], a.shape[1], 9)
    return np.nanmean(w, axis=2)


def object_basis(deg):
    a = np.deg2rad(deg)
    return np.array([[np.cos(a), np.sin(a)], [np.sin(a), -np.cos(a)]])


def region_polygons(rcfg):
    B = object_basis(rcfg['frame']['u_axis_angle_degrees_ccw_from_easting'])
    sh = np.array(rcfg['frame']['world_shift_xyz_m'][:2])
    out = {}
    for r in rcfg['regions']:
        u0, u1 = r['u_m']; v0, v1 = r['v_m']
        c = np.array([[u0, v0], [u1, v0], [u1, v1], [u0, v1]]) @ B + sh
        out[r['id']] = dict(poly=Polygon(c), corners=c.tolist(), u=r['u_m'], v=r['v_m'], label=r['label_ko'],
                            color=r['color'], legacy=r['contains_legacy'], area=(u1 - u0) * (v1 - v0))
    return out, B, sh


def to_uv(e, n, B, sh):
    xy = np.column_stack([np.asarray(e) - sh[0], np.asarray(n) - sh[1]])
    return xy @ B.T


class G:
    def __init__(self, g):
        self.e0, self.n0, self.res = g['e_min'], g['n_min'], g['res_m']
        self.nx = int(round((g['e_max'] - g['e_min']) / g['res_m'])); self.ny = int(round((g['n_max'] - g['n_min']) / g['res_m']))
        self.ec = self.e0 + (np.arange(self.nx) + 0.5) * self.res
        self.nc = self.n0 + (np.arange(self.ny) + 0.5) * self.res

    def poly_mask(self, poly):
        from matplotlib.path import Path as P
        x0, y0, x1, y1 = poly.bounds
        ix0 = max(0, int((x0 - self.e0) / self.res) - 1); ix1 = min(self.nx, int((x1 - self.e0) / self.res) + 2)
        iy0 = max(0, int((y0 - self.n0) / self.res) - 1); iy1 = min(self.ny, int((y1 - self.n0) / self.res) + 2)
        m = np.zeros((self.ny, self.nx), bool)
        if ix1 <= ix0 or iy1 <= iy0:
            return m
        ee, nn = np.meshgrid(self.ec[ix0:ix1], self.nc[iy0:iy1])
        polys = list(poly.geoms) if poly.geom_type == 'MultiPolygon' else [poly]
        sub = np.zeros(ee.shape, bool)
        pts = np.column_stack([ee.ravel(), nn.ravel()])
        for pg in polys:
            s = P(np.asarray(pg.exterior.coords)).contains_points(pts)
            for h in pg.interiors:
                s &= ~P(np.asarray(h.coords)).contains_points(pts)
            sub |= s.reshape(ee.shape)
        m[iy0:iy1, ix0:ix1] = sub
        return m


def stats_pair(d, core, veg, res, thr=(1.0, 2.5), min_area=25.0):
    v = core & np.isfinite(d)
    n = int(v.sum()); ncore = int(core.sum())
    out = dict(n=n, cover=round(n / ncore, 3) if ncore else 0.0)
    if n < 10:
        return out
    x = d[v]
    out.update(med=round(float(np.median(x)), 3), p10=round(float(np.quantile(x, .1)), 3), p90=round(float(np.quantile(x, .9)), 3),
               nmad=round(float(1.4826 * np.median(np.abs(x - np.median(x)))), 3))
    for t in thr:
        out['frac_gt%g' % t] = round(float((np.abs(x) > t).mean()), 3)
        out['frac_pos%g' % t] = round(float((x > t).mean()), 3)
        out['frac_neg%g' % t] = round(float((x < -t).mean()), 3)
        m = v & (np.abs(d) > t) & ~(veg > 0.3)
        lab, k = ndi.label(m)
        best = (0.0, 0.0, None)
        if k:
            sizes = ndi.sum(np.ones_like(d), lab, index=np.arange(1, k + 1))
            j = int(np.argmax(sizes)) + 1
            area = float(sizes[j - 1]) * res * res
            sel = lab == j
            best = (area, float(np.median(d[sel])), np.argwhere(sel).mean(axis=0))
        out['comp_area%g' % t] = round(best[0], 2)
        out['comp_med%g' % t] = round(best[1], 3)
        out['comp_ok%g' % t] = bool(best[0] >= min_area)
        if best[2] is not None:
            out['comp_rc%g' % t] = [round(float(best[2][0]), 1), round(float(best[2][1]), 1)]
    return out


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--config', required=True); ap.add_argument('--out', required=True)
    args = ap.parse_args()
    if not Path('/.dockerenv').exists():
        raise RuntimeError('Docker execution required')
    t0 = time.time()
    cfg = json.loads(Path(args.config).read_text())
    out = Path(args.out)
    g = G(cfg['grid'])
    A = dict(np.load(out / 's1' / 'rasters_als_mvs_uls.npz')); L = dict(np.load(out / 's1' / 'rasters_lod2.npz'))
    blds = json.loads((out / 's1' / 'lod2_buildings.json').read_text())
    res = g.res
    # --- derived surfaces -------------------------------------------------------
    n2 = A['als_n_c2']
    dtm = np.where(n2 > 0, A['als_zsum_c2'] / np.maximum(n2, 1), np.nan)
    hole = ~np.isfinite(dtm)
    idx = ndi.distance_transform_edt(hole, return_distances=False, return_indices=True)
    dtm_f = dtm[tuple(idx)]
    dtm_f = ndi.median_filter(dtm_f, size=5)
    als = nanmedian3(A['als_zmax'].astype(np.float64))
    uls = nanmedian3(A['uls_zmax'].astype(np.float64))
    mvs = nanmedian3(A['mvs_p90'].astype(np.float64))
    lod = L['lod2_roof'].astype(np.float64)
    fid = L['lod2_fid']
    veg = nanmean3(np.where(A['uls_n'] > 0, A['uls_n_multi'] / np.maximum(A['uls_n'], 1), np.nan))
    als_veg = nanmean3(np.where(A['als_n'] > 0, A['als_n_c20'] / np.maximum(A['als_n'], 1), np.nan))
    mvs_dom = ndi.binary_dilation(A['mvs_n'] > 0, iterations=4)
    dom_bbox = [690712.1673758544, 5335851.2468733825, 691175.7141398315, 5336372.438672913]
    ee, nn = np.meshgrid(g.ec, g.nc)
    in_dom = (ee >= dom_bbox[0]) & (ee <= dom_bbox[2]) & (nn >= dom_bbox[1]) & (nn <= dom_bbox[3]) & mvs_dom
    uls_cov = A['uls_n'] > 0
    rgb_uls = np.stack([A['uls_rsum'], A['uls_gsum'], A['uls_bsum']], -1) / np.maximum(A['uls_n'], 1)[..., None]
    rgb_mvs = np.stack([A['mvs_rsum'], A['mvs_gsum'], A['mvs_bsum']], -1) / np.maximum(A['mvs_n'], 1)[..., None]
    np.savez_compressed(out / 'derived.npz', dtm=dtm_f.astype(np.float32), als=als.astype(np.float32), uls=uls.astype(np.float32),
                        mvs=mvs.astype(np.float32), lod=lod.astype(np.float32), fid=fid, veg=veg.astype(np.float32),
                        als_veg=als_veg.astype(np.float32), in_dom=in_dom, uls_cov=uls_cov,
                        rgb_uls=np.clip(rgb_uls, 0, 255).astype(np.uint8), rgb_mvs=np.clip(rgb_mvs, 0, 255).astype(np.uint8),
                        als_n_c6=A['als_n_c6'].astype(np.float32), als_n_c2=n2.astype(np.float32))
    # --- vertical agreement on bare hard ground --------------------------------
    rough = A['uls_zmax'] - A['uls_zmin']
    ground = (n2 >= 2) & (rough < 0.25) & (fid < 0) & (veg < 0.05) & np.isfinite(uls) & np.isfinite(mvs) & in_dom
    ground &= np.abs(uls - dtm) < 1.0
    offs = {}

    def rob(x):
        x = x[np.isfinite(x)]
        if len(x) < 20:
            return dict(n=int(len(x)))
        m = float(np.median(x))
        return dict(n=int(len(x)), median=round(m, 3), nmad=round(float(1.4826 * np.median(np.abs(x - m))), 3),
                    p10=round(float(np.quantile(x, .1)), 3), p90=round(float(np.quantile(x, .9)), 3))
    gz = np.where(n2 > 0, A['als_zsum_c2'] / np.maximum(n2, 1), np.nan)
    offs['ground_uls_minus_als'] = rob((uls - gz)[ground])
    offs['ground_mvs_minus_uls'] = rob((mvs - uls)[ground])
    offs['ground_mvs_minus_als'] = rob((mvs - gz)[ground])
    # flat LoD2 roof cells (slope < 5 deg) for LoD2 vs current / ALS
    gy, gx = np.gradient(lod, res)
    slope = np.hypot(gx, gy)
    flat = np.isfinite(lod) & (slope < 0.09) & (fid >= 0)
    flat_core = flat & ndi.binary_erosion(np.isfinite(lod), iterations=3)
    offs['flatroof_uls_minus_lod2'] = rob((uls - lod)[flat_core & (veg < 0.1)])
    offs['flatroof_als_minus_lod2'] = rob((als - lod)[flat_core & (veg < 0.1)])
    offs['flatroof_uls_minus_als'] = rob((uls - als)[flat_core & (veg < 0.1)])
    offs['flatroof_mvs_minus_uls'] = rob((mvs - uls)[flat_core & (veg < 0.1)])
    offs['definition'] = ('ground = ALS class-2 cells (>=2 pts) outside LoD2 footprints, ULS max-min < 0.25 m, ULS multi-return < 5 %, '
                          '|ULS-DTM| < 1 m; flat roof = LoD2 roof cells with slope < 5 deg, 1.5 m inside roof edges, ULS multi-return < 10 %. '
                          'Medians include real change cells, so the roof value is an upper bound of the registration offset.')
    # --- regions, B0 --------------------------------------------------------------
    rcfg = json.loads(Path('/repo/' + cfg['inputs']['region_config_repo']).read_text())
    regs, B, sh = region_polygons(rcfg)
    b0poly_local = json.loads((Path(cfg['artifact_root_container']) / cfg['inputs']['b0_stage1_polygons']).read_text())
    shift = b0poly_local['shift_global_to_local']
    (x0, y0), (x1, y1) = b0poly_local['als_crop_local_xy']
    b0crop = box(x0 - shift[0], y0 - shift[1], x1 - shift[0], y1 - shift[1])
    fps = {}
    for bi, b in enumerate(blds):
        polys = []
        for p in b['surfaces']['ground']:
            ext = np.asarray(p['ext'])[:, :2]
            if len(ext) >= 4:
                pg = Polygon(ext, [np.asarray(h)[:, :2] for h in p['holes']]).buffer(0)
                if pg.area > 0:
                    polys.append(pg)
        fps[bi] = unary_union(polys) if polys else None
    # --- per-building statistics ------------------------------------------------------
    rows = []
    cur = dict(uls=uls, mvs=mvs)
    pri = dict(als=als, lod2=lod)
    for bi, b in enumerate(blds):
        fp = fid == bi
        if fp.sum() == 0:
            continue
        ys, xs = np.nonzero(fp)
        y0_, y1_, x0_, x1_ = max(0, ys.min() - 3), min(g.ny, ys.max() + 4), max(0, xs.min() - 3), min(g.nx, xs.max() + 4)
        win = (slice(y0_, y1_), slice(x0_, x1_))
        f = fp[win]
        core = ndi.binary_erosion(f, iterations=int(round(cfg['building_stats']['core_erosion_m'] / res)))
        if core.sum() < 20:
            core = f
        r = dict(id=b['id'], idx=bi, creationDate=b['creationDate'], grundriss=b['attrs'].get('Grundrissaktualitaet'),
                 dq_dach=b['attrs'].get('DatenquelleDachhoehe'), methode=b['attrs'].get('Methode'), roofType=b['roofType'],
                 function=b['function'], measuredHeight=b['measuredHeight'], fp_area=round(float(f.sum()) * res * res, 1),
                 core_area=round(float(core.sum()) * res * res, 1))
        c_rc = np.argwhere(f).mean(axis=0)
        r['e'] = round(float(g.ec[int(c_rc[1]) + x0_]), 2); r['n'] = round(float(g.nc[int(c_rc[0]) + y0_]), 2)
        uv = to_uv([r['e']], [r['n']], B, sh)[0]
        r['u'] = round(float(uv[0]), 1); r['v'] = round(float(uv[1]), 1)
        r['in_dom_frac'] = round(float(in_dom[win][core].mean()), 3)
        r['uls_cover'] = round(float(uls_cov[win][core].mean()), 3)
        r['veg_med'] = round(float(np.nanmedian(veg[win][core])), 3) if np.isfinite(veg[win][core]).any() else None
        for nm, s in (('uls', uls), ('mvs', mvs), ('als', als), ('lod2', lod)):
            h = (s[win] - dtm_f[win])[core]
            h = h[np.isfinite(h)]
            r['h_' + nm] = round(float(np.median(h)), 2) if len(h) else None
        for cn, cs in cur.items():
            for pn, ps in pri.items():
                st = stats_pair((cs[win] - ps[win]), core, veg[win], res)
                for k, v in st.items():
                    if k.startswith('comp_rc') and v is not None:
                        v = [round(v[0] + y0_, 1), round(v[1] + x0_, 1)]
                    r['%s_%s__%s' % (cn, pn, k)] = v
        st = stats_pair(als[win] - lod[win], core, veg[win], res)
        for k, v in st.items():
            if not k.startswith('comp_rc'):
                r['als_lod2__%s' % k] = v
        st = stats_pair(mvs[win] - uls[win], core, veg[win], res)
        for k in ('n', 'med', 'nmad', 'frac_gt1'):
            if k in st:
                r['mvs_uls__%s' % k] = st[k]
        mem = []
        for rid, rg in regs.items():
            if fps[bi] is not None and fps[bi].intersects(rg['poly']):
                fr = fps[bi].intersection(rg['poly']).area / fps[bi].area
                if fr > 0.001:
                    mem.append('%s:%.2f' % (rid, fr))
        r['regions'] = ';'.join(mem)
        r['in_b0crop'] = round(fps[bi].intersection(b0crop).area / fps[bi].area, 3) if fps[bi] is not None else 0.0
        rows.append(r)
    keys = []
    for r in rows:
        for k in r:
            if k not in keys:
                keys.append(k)
    with open(out / 'buildings.csv', 'w', newline='') as fcsv:
        w = csv.DictWriter(fcsv, fieldnames=keys); w.writeheader()
        for r in rows:
            w.writerow({k: (json.dumps(v) if isinstance(v, list) else v) for k, v in r.items()})
    # --- components outside LoD2 footprints -----------------------------------------
    outside = ~ndi.binary_dilation(fid >= 0, iterations=2)
    comps = []
    nd_als = als - dtm_f
    for cname, cs in (('uls', uls), ('mvs', mvs)):
        nd_cur = cs - dtm_f
        tests = {
            'new_structure': outside & (nd_cur > 2.5) & (nd_als < 1.0) & (veg < 0.3) & np.isfinite(nd_cur),
            'removed_structure': outside & (nd_als > 2.5) & (nd_cur < 1.0) & (A['als_n_c6'] > 0) & np.isfinite(nd_cur),
        }
        for kind, m in tests.items():
            m = ndi.binary_opening(m, iterations=1) & in_dom
            lab, k = ndi.label(m)
            if not k:
                continue
            sizes = ndi.sum(np.ones(m.shape), lab, index=np.arange(1, k + 1)) * res * res
            for j in np.nonzero(sizes >= 25.0)[0]:
                sel = lab == j + 1
                yy, xx = np.nonzero(sel)
                e = float(g.ec[int(xx.mean())]); n = float(g.nc[int(yy.mean())])
                uv = to_uv([e], [n], B, sh)[0]
                dd = (cs - als)[sel]
                inreg = [rid for rid, rg in regs.items() if rg['poly'].contains(Polygon_point(e, n))]
                comps.append(dict(source=cname, kind=kind, area_m2=round(float(sizes[j]), 1), e=round(e, 2), n=round(n, 2),
                                  u=round(float(uv[0]), 1), v=round(float(uv[1]), 1), dz_med=round(float(np.nanmedian(dd)), 2),
                                  h_cur_med=round(float(np.nanmedian(nd_cur[sel])), 2), h_als_med=round(float(np.nanmedian(nd_als[sel])), 2),
                                  veg_med=round(float(np.nanmedian(veg[sel])), 3), uls_cover=round(float(uls_cov[sel].mean()), 3),
                                  bbox_rc=[int(yy.min()), int(xx.min()), int(yy.max()), int(xx.max())], regions=';'.join(inreg),
                                  in_b0crop=bool(b0crop.contains(Polygon_point(e, n)))))
    with open(out / 'components.csv', 'w', newline='') as fcsv:
        keys = list(comps[0].keys()) if comps else ['source']
        w = csv.DictWriter(fcsv, fieldnames=keys); w.writeheader()
        for c in comps:
            w.writerow({k: (json.dumps(v) if isinstance(v, list) else v) for k, v in c.items()})
    # --- region summaries ----------------------------------------------------------------
    rec = {}
    for rid, rg in list(regs.items()) + [('B0crop', dict(poly=b0crop, corners=list(b0crop.exterior.coords)[:4], area=b0crop.area))]:
        m = g.poly_mask(rg['poly'])
        cells = int(m.sum()); area_cells = cells * res * res
        d = dict(corners_epsg25832=[[round(a, 2), round(b_, 2)] for a, b_ in rg['corners']], area_m2=round(float(rg['area']), 1),
                 grid_cells=cells, in_image_domain_frac=round(float(in_dom[m].mean()), 3),
                 uls_cover_frac=round(float(uls_cov[m].mean()), 3),
                 uls_density_pts_m2=round(float(A['uls_n'][m].sum() / area_cells), 1),
                 als_density_pts_m2=round(float(A['als_n'][m].sum() / area_cells), 2),
                 als_density_ground_c2=round(float(A['als_n_c2'][m].sum() / area_cells), 2),
                 als_density_building_c6=round(float(A['als_n_c6'][m].sum() / area_cells), 2),
                 als_density_c20=round(float(A['als_n_c20'][m].sum() / area_cells), 2),
                 mvs_density_pts_m2=round(float(A['mvs_n'][m].sum() / area_cells), 1))
        if 'u' in rg:
            d.update(u_m=rg['u'], v_m=rg['v'], label=rg['label'], legacy=rg['legacy'])
        inter = []
        for bi, b in enumerate(blds):
            if fps[bi] is None or not fps[bi].intersects(rg['poly']):
                continue
            fr = fps[bi].intersection(rg['poly']).area / fps[bi].area
            if fr > 0.001:
                inter.append(dict(id=b['id'], frac_inside=round(fr, 3), fp_area=round(fps[bi].area, 1), creationDate=b['creationDate'],
                                  dq_dach=b['attrs'].get('DatenquelleDachhoehe'), methode=b['attrs'].get('Methode')))
        d['buildings'] = inter
        vint = {}
        for x in inter:
            if x['frac_inside'] >= 0.5:
                vint[x['creationDate']] = vint.get(x['creationDate'], 0) + 1
        d['creationDate_counts_majority_inside'] = dict(sorted(vint.items()))
        d['b0crop_intersection_m2'] = round(float(rg['poly'].intersection(b0crop).area), 1)
        gr = ground & m
        d['ground_uls_minus_als'] = rob((uls - gz)[gr])
        d['ground_mvs_minus_uls'] = rob((mvs - uls)[gr])
        d['flatroof_uls_minus_lod2'] = rob((uls - lod)[flat_core & (veg < 0.1) & m])
        d['flatroof_uls_minus_als'] = rob((uls - als)[flat_core & (veg < 0.1) & m])
        rec[rid] = d
    b0i = [i for i, b in enumerate(blds) if b['id'] == 'DEBY_LOD2_4959323']
    rec['B0crop']['target_building'] = 'DEBY_LOD2_4959323'
    if b0i:
        fp0 = fps[b0i[0]]
        rec['B0crop']['target_building_distance_to_regions_m'] = {rid: round(float(fp0.distance(rg['poly'])), 1) for rid, rg in regs.items()}
        rec['B0crop']['crop_distance_to_regions_m'] = {rid: round(float(b0crop.distance(rg['poly'])), 1) for rid, rg in regs.items()}
    rec['B0crop']['crop_epsg25832'] = [round(v, 2) for v in b0crop.bounds]
    (out / 'regions.json').write_text(json.dumps(rec, indent=1, ensure_ascii=False))
    (out / 'offsets.json').write_text(json.dumps(offs, indent=1, ensure_ascii=False))
    receipt = dict(task_id=cfg['task_id'], step='s2_stats', scientific_verdict=None, finished=datetime.datetime.now().isoformat(),
                   seconds=round(time.time() - t0, 1), buildings=len(rows), components=len(comps),
                   rules=cfg['building_stats'], ground_cells=int(ground.sum()), flatroof_cells=int(flat_core.sum()))
    (out / 'receipt_s2.json').write_text(json.dumps(receipt, indent=1, ensure_ascii=False))
    print('s2 done', receipt)


def Polygon_point(e, n):
    from shapely.geometry import Point
    return Point(e, n)


if __name__ == '__main__':
    main()
