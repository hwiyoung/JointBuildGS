"""PHD-MAIN-BASE151-v1 LGDM over the campus: judge -> decide on the campus, compose per cell, patch in_change (jointbuildgs:dev, CPU;
run_lgdm_cpu.sh). Rules: configs/phd/main_base151_v1/inputs_LGDM.json. The BASELINES mvsfuse modules (exp checkout, /exp) are imported
and their rule functions are called unchanged (detect.judge, decide, growth, size_filter, cell_median, ocast; mf_common.RULE); only the
I/O adapters (mf_common.load_map, read_rgb) and the driver around them (detect.unit) are written here. No GT file is read.

  python b151_lgdm_detect.py judge <LoD2|ALS> [--nproc 6] [--views N]
        -> /b151/lgdm/<prior>/detect/{detect.json, cells.npz, views.json, quicklook.png}   (campus change map, thresholds 25 / 20 / 30)
  python b151_lgdm_detect.py compose <LoD2|ALS> <cell|all> [--nproc 8] [--views N]
        -> /b151/lgdm/<prior>/cell<k>/{depth/<stem>.npy, compose.json}   (composite camera-z depth, float32 [741, 1024], NaN = none)
  python b151_lgdm_detect.py patches <LoD2|ALS>   -> /b151/lgdm/<prior>/patches_<tile>.npz, /b151/lgdm/<prior>/patches.json
  python b151_lgdm_detect.py receipt <LoD2|ALS>   -> /b151/lgdm/receipt_<prior>.json
--views N: first N views only, outputs under /b151/lgdm/tests/ (code test; never a result).
scientific_verdict: null
"""
import argparse
import multiprocessing as mp
import resource
import shutil
import sys
import time

import numpy as np

import b151_lgdm_inputs as LI
from b151_common import *

import detect as DT  # noqa: E402  (/exp/scripts/phd/main_baselines_v1/mvsfuse, path inserted by b151_lgdm_inputs)

M = DT.M
assert M is LI.M
THR, RC, RR = DT.THR, DT.RC, DT.RR
SITE = 'campus'
NBLK = 32                     # cell-id blocks for the per-cell medians (same medians as one sort)
_cast = {}


# ------------------------------------------------------------------------------------------------ I/O adapters
def campus_cast(stem):
    """stage-0 export 'prior' rule (s03_stage1_v6.py:141-145,379) on the campus surface: common.Scene.cast inputs (C and Views.rays as
    float32), camera z, NaN no hit; the triangle ids are kept for the cell-map comparison."""
    if stem not in _cast:
        import open3d as o3d
        _cast.clear()
        V, P = DT.G['V'], DT.G['P']
        n = f'{stem}.jpg'
        Dr = V.rays(n)
        r = np.concatenate([np.broadcast_to(np.asarray(V.C(n), np.float32), Dr.shape), Dr.astype(np.float32)], -1).reshape(-1, 6)
        ans = P.scene().scene.cast_rays(o3d.core.Tensor(r), nthreads=DT.NTH)
        t = ans['t_hit'].numpy().reshape(M.H, M.W)
        tri = ans['primitive_ids'].numpy().astype(np.int64).reshape(M.H, M.W)
        tri[~np.isfinite(t)] = -1
        _cast[stem] = (np.where(np.isfinite(t), t, np.nan).astype(np.float32), tri)
    return _cast[stem]


def load_map(site, prior, kind, stem):
    if kind == 'prior':
        return campus_cast(stem)[0]
    if kind == 'mvs':
        return LI.mvs_map(stem)
    if kind == 'tau':             # inputs_LGDM.json inputs.tau: not made; the colour reference of agreeing pixels stays empty
        return np.full((M.H, M.W), np.nan, np.float32)
    raise KeyError(kind)


M.load_map = load_map
M.read_rgb = LI.read_rgb


def mem():
    out = dict(self_maxrss_gb=round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1048576, 2),
               children_maxrss_gb=round(resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 1048576, 2))
    for f in ('memory.peak', 'memory.max_usage_in_bytes'):
        for root in (Path('/sys/fs/cgroup'), Path('/sys/fs/cgroup/memory')):
            p = root / f
            if p.exists():
                try:
                    out['cgroup_peak_gb'] = round(int(p.read_text().split()[0]) / 1e9, 2)
                except Exception:  # noqa: BLE001
                    pass
    return out


def base(a):
    return LI.L / 'tests' if getattr(a, 'views', 0) else LI.L


# ------------------------------------------------------------------------------------------------ step 1 + 2: judge and decide (campus)
def judge_w(stem):
    r = DT.judge(stem)
    G = DT.G
    D, tri = campus_cast(stem)
    P = G['P']
    fa = np.isfinite(D)
    cmp = []
    for k in G['cells_of'].get(stem, []):
        Dk = np.load(B / 'priordepth' / G['prior'] / f'cell{k}' / f'{stem}.npy')
        fb = np.isfinite(Dk)
        both = fa & fb
        ink = (tri >= 0) & (((P.tri_cells[np.maximum(tri, 0)] >> k) & 1) > 0)
        bi = ink & both
        d = np.abs(D[bi] - Dk[bi])
        cmp.append(dict(cell=k, campus_hit_px=int(fa.sum()), cell_hit_px=int(fb.sum()), finite_mismatch_px=int((fa != fb).sum()),
                        diff_over_1cm_px=int((np.abs(D[both] - Dk[both]) > 0.01).sum()), campus_hit_on_cell_surface_px=int(ink.sum()),
                        on_cell_surface_mismatch_px=int((ink & ~fb).sum() + (d > 0.01).sum()), on_cell_surface_max_abs_m=float(d.max()) if len(d) else 0.0))
    r['cell_map_cmp'] = cmp
    r['hit_cells'] = r['hit_cells'].astype(np.int32)
    r['dz_cell'] = r['dz_cell'].astype(np.int32)
    return r


def band_ring(grid, cb, band_m):
    """= (M.dilate(mk, band_m) & ~mk) of detect.unit (detect.py:650-652) on a window around the building's cells (margin > radius)."""
    if not len(cb):
        return np.zeros(0, np.int64)
    iy, ix = np.divmod(cb, grid.nx)
    pad = int(np.ceil(band_m / M.CELL)) + 1
    y0, y1 = max(int(iy.min()) - pad, 0), min(int(iy.max()) + pad + 1, grid.ny)
    x0, x1 = max(int(ix.min()) - pad, 0), min(int(ix.max()) + pad + 1, grid.nx)
    mk = np.zeros((y1 - y0, x1 - x0), bool)
    mk[iy - y0, ix - x0] = True
    ring = M.dilate(mk, band_m) & ~mk
    ry, rx = np.nonzero(ring)
    return np.sort((ry + y0).astype(np.int64) * grid.nx + (rx + x0))


def buildings(P, grid, prior):
    """detect.unit lines 633-657 (building plan cells and ground height), grouped by building instead of a scan per building."""
    nb = P.n_bld
    bcells, hg, binfo = [], np.full(max(nb, 1), np.nan), []
    order = np.argsort(P.tri_bld, kind='stable')
    sb = P.tri_bld[order]
    st, en = np.searchsorted(sb, np.arange(nb), 'left'), np.searchsorted(sb, np.arange(nb), 'right')
    if prior == 'ALS':
        gsel = ~P.building_tri
        cen = P.V[P.F[gsel]].mean(1)
        gcell = grid.cell(cen)
        go = np.argsort(gcell, kind='stable')
        gs = gcell[go]
    for b in range(nb):
        tb = order[st[b]:en[b]]                       # = np.nonzero(P.tri_bld == b)[0]
        cb = M.raster_triangles(grid, P.V, P.F[tb])
        bcells.append(cb)
        if prior == 'LoD2':
            walls = tb[P.tri_type[tb] == 1]
            lows = [float(P.V[P.F[walls[P.tri_surface[walls] == s_]]].reshape(-1, 3)[:, 2].min()) for s_ in np.unique(P.tri_surface[walls])]
            hg[b] = float(np.median(lows)) if lows else np.nan
            binfo.append(dict(building=b, name=P.building_names[b] if P.building_names and b < len(P.building_names) else None, triangles=int(len(tb)),
                              cells=int(len(cb)), wall_surfaces=len(lows), ground_m=None if not lows else round(hg[b], 3)))
        else:
            ring = band_ring(grid, cb, RR['band_m'])
            lo_, hi_ = np.searchsorted(gs, ring, 'left'), np.searchsorted(gs, ring, 'right')
            cnt = hi_ - lo_
            idx = np.repeat(lo_, cnt) + (np.arange(int(cnt.sum())) - np.repeat(np.cumsum(cnt) - cnt, cnt)) if cnt.sum() else np.zeros(0, np.int64)
            zs = cen[go[idx], 2]
            hg[b] = float(np.median(zs)) if len(zs) else np.nan
            binfo.append(dict(building=b, triangles=int(len(tb)), cells=int(len(cb)), band_ground_triangles=int(len(zs)),
                              ground_m=None if not len(zs) else round(hg[b], 3)))
    return bcells, hg, binfo


def run_judge(a):
    LI.lcfg()
    T0 = time.time()
    times = {}
    prior = a.prior
    RD = base(a) / prior / 'detect'
    RD.mkdir(parents=True, exist_ok=True)
    V = LI.campus_views()
    train = LI.campus_train()
    if a.views:
        train = train[:a.views]
    pfile = LI.L / 'prep/pairs_campus.json'
    pj = json.loads(pfile.read_text())
    pairs = {r['view']: r['pair'] for r in pj['pairs']}
    P = LI.CampusPrior(prior)
    grid = LI.CampusGrid()
    cells_of = {}
    for k in range(4):
        for s in LI.cell_train(k):
            cells_of.setdefault(s, []).append(k)
    t = time.time()
    bcells, hg, binfo = buildings(P, grid, prior)
    times['buildings_s'] = round(time.time() - t, 1)
    DT.G.update(V=V, P=P, grid=grid, site=SITE, prior=prior, pairs=pairs, n_bld=P.n_bld, tri_bld=P.tri_bld, hg=hg, dz_only=False, cells_of=cells_of)
    M.log(SITE, prior, 'buildings', P.n_bld, 'views', len(train), 'paired', sum(1 for s in train if pairs.get(s)), 'grid', grid.nx, grid.ny, times)
    # step 1: per view, reduced as the results arrive
    t = time.time()
    n = grid.n
    nb1 = max(P.n_bld, 1)
    nsee = np.zeros(n, np.int64)
    nch = np.zeros((len(THR), n), np.int64)
    prior_cells = np.zeros(n, bool)
    rem_n = np.zeros(nb1, np.int64)
    rem_sim = np.zeros((len(THR), nb1), np.int64)
    hist_a = np.zeros(len(DT.HB) - 1, np.int64)
    hist_all = np.zeros(len(DT.HB) - 1, np.int64)
    bounds = np.linspace(0, n, NBLK + 1).astype(np.int64)
    blk_c, blk_v = [[] for _ in range(NBLK)], [[] for _ in range(NBLK)]
    pstats, vers, npaired, ndz = [], [], 0, 0
    ctx = mp.get_context('fork')
    with ctx.Pool(a.nproc) as pool:
        for r in pool.imap(judge_w, train, chunksize=1):
            vers.append(dict(view=r['view'], **r['ver']))
            pstats.append(dict(view=r['view'], pair=r['pair'], seconds=r['seconds'], **r['stats'], cell_map_cmp=r['cell_map_cmp']))
            prior_cells[r['hit_cells']] = True
            c, v = r['dz_cell'], r['dz']
            ndz += len(c)
            bi = np.searchsorted(bounds, c, 'right') - 1
            o = np.argsort(bi, kind='stable')
            cut = np.searchsorted(bi[o], np.arange(NBLK + 1))
            for q in range(NBLK):
                if cut[q + 1] > cut[q]:
                    blk_c[q].append(c[o[cut[q]:cut[q + 1]]])
                    blk_v[q].append(v[o[cut[q]:cut[q + 1]]])
            if r['pair'] is not None and 'vote_cells' in r:
                npaired += 1
                cc = r['vote_cells']
                nsee[cc] += 1
                nch[:, cc] += (2 * r['vote_ch'] > r['vote_n'][None, :]).astype(np.int64)
                hist_a += r['hist_agree']
                hist_all += r['hist_all']
                if 'rem_n' in r:
                    rem_n += r['rem_n']
                    rem_sim += r['rem_sim']
            if len(pstats) % 50 == 0:
                M.log('views', len(pstats), '/', len(train), round(time.time() - t), 's', mem())
    times['views_s'] = round(time.time() - t, 1)
    M.log('views done', times['views_s'], mem())
    ver_bad = [r['view'] for r in vers if r['mismatch_px'] > 0.001 * M.H * M.W or r['max_abs_m'] > 0.01]
    ver = dict(views=len(vers), max_mismatch_px=max(r['mismatch_px'] for r in vers), max_abs_m=max(r['max_abs_m'] for r in vers), views_failing=ver_bad,
               note='detect.judge re-cast (ocast, float64 rays) against the campus cast with the stage-0 export rule: two casts of the same surface')
    if ver_bad:
        M.jdump(RD.parent / 'STOP_recast.json', dict(ver=ver, scientific_verdict=None))
        raise SystemExit(f'the re-cast prior differs from the export-rule cast in {len(ver_bad)} views: stop')
    cm = [c_ for s_ in pstats for c_ in s_['cell_map_cmp']]
    cell_cmp = dict(pairs_view_cell=len(cm), on_cell_surface_mismatch_px_max=max((c_['on_cell_surface_mismatch_px'] for c_ in cm), default=0),
                    on_cell_surface_mismatch_share_max=max((c_['on_cell_surface_mismatch_px'] / max(c_['campus_hit_on_cell_surface_px'], 1) for c_ in cm), default=0.0),
                    on_cell_surface_max_abs_m=max((c_['on_cell_surface_max_abs_m'] for c_ in cm), default=0.0),
                    finite_mismatch_share_quantiles_50_95_max=np.percentile([c_['finite_mismatch_px'] / (M.H * M.W) for c_ in cm], [50, 95, 100]).round(5).tolist() if cm else None,
                    diff_over_1cm_share_quantiles_50_95_max=np.percentile([c_['diff_over_1cm_px'] / (M.H * M.W) for c_ in cm], [50, 95, 100]).round(5).tolist() if cm else None,
                    rule='campus cast vs the cell prior map (OUT/priordepth) of every cell the view trains: on pixels whose campus hit is a triangle of '
                         'that cell surface they must agree (mismatch = no cell hit or |diff| > 0.01 m); elsewhere the difference = surfaces outside '
                         'the cell range (recorded, not a check)')

    def hq(h):
        c = np.cumsum(h)
        if c[-1] == 0:
            return None
        mids = 0.5 * (DT.HB[1:] + DT.HB[:-1])
        return {f'q{int(q * 100)}': round(float(mids[np.searchsorted(c, q * c[-1])]), 2) for q in (0.05, 0.25, 0.5, 0.75, 0.95, 0.99)}
    colour = dict(rule='order 5.6 item 4 (reference only); no tau map (inputs_LGDM.json inputs.tau), so the agreeing-pixel histogram is empty',
                  agree_pixels=int(hist_a.sum()), agree_quantiles=hq(hist_a), all_judged_pixels=int(hist_all.sum()), all_judged_quantiles=hq(hist_all),
                  share_all_above={str(int(th_)): round(float(hist_all[DT.HB[:-1] >= th_].sum() / max(hist_all.sum(), 1)), 4) for th_ in THR})
    ks = [s_['opening_k'] for s_ in pstats if s_.get('opening_k') is not None and s_.get('relief_disp_px') is not None]
    ds = [s_['relief_disp_px'] for s_ in pstats if s_.get('relief_disp_px') is not None]
    opening = dict(relief_disp_px_quantiles_5_50_95=np.percentile(ds, [5, 50, 95]).round(2).tolist() if ds else None,
                   k_counts={str(k): int(sum(1 for x in ks if x == k)) for k in sorted(set(ks))}, pairs_without_opening=int(sum(1 for x in ks if x < 2)))
    # step 2: plan cells (cell medians in blocks of cell ids)
    t = time.time()
    dz_med = np.full(n, np.nan, np.float32)
    dz_cnt = np.zeros(n, np.int64)
    for q in range(NBLK):
        lo_, hi_ = int(bounds[q]), int(bounds[q + 1])
        if blk_c[q]:
            cq = np.concatenate(blk_c[q]).astype(np.int64) - lo_
            vq = np.concatenate(blk_v[q])
            blk_c[q] = blk_v[q] = None
            med, cnt = DT.cell_median(cq, vq, hi_ - lo_)
            dz_med[lo_:hi_], dz_cnt[lo_:hi_] = med, cnt
            del cq, vq
    ss = dict(ny=grid.ny, nx=grid.nx, lo=grid.lo, nsee=nsee, nch=nch, n_bld=P.n_bld, rem_n=rem_n, rem_sim=rem_sim, bcells=bcells,
              prior_cells=prior_cells.reshape(grid.ny, grid.nx), dz_med=dz_med.reshape(grid.ny, grid.nx), dz_cnt=dz_cnt, in_eval=grid.in_eval)
    decisions, finals = {}, {}
    A = M.CELL ** 2
    for t_i, th_ in enumerate(THR):
        final, rec, layers = DT.decide(ss, t_i, extra=(t_i == 0))
        finals[int(th_)] = final
        rec['final_m2'] = round(rec['final_cells'] * A, 2)
        if t_i == 0:
            main_final, main_layers = final, layers
            ref = rec['reference']['growth_dz_1p5m']
            f15 = ref.pop('final')
            ref['final_m2'] = round(ref['final_cells'] * A, 2)
        decisions[str(int(th_))] = rec
    times['cells_s'] = round(time.time() - t, 1)
    np.savez_compressed(RD / 'cells.npz', lo=grid.lo, cell=M.CELL, nx=grid.nx, ny=grid.ny, nsee=nsee.reshape(grid.ny, grid.nx).astype(np.int32),
                        nch=nch.reshape(len(THR), grid.ny, grid.nx).astype(np.int32), thresholds=np.array(THR), prior_cells=ss['prior_cells'],
                        dz_med=ss['dz_med'], dz_cnt=dz_cnt.reshape(grid.ny, grid.nx).astype(np.int32), in_eval=grid.in_eval, vote=main_layers['vote'],
                        removal=main_layers['removal'], grown=main_layers['grown'], final=main_final, final_20=finals[20], final_30=finals[30],
                        final_growth_dz_1p5m_reference=f15)
    M.jdump(RD / 'views.json', dict(site=SITE, prior=prior, views=pstats, scientific_verdict=None))
    try:
        DT.quicklook(RD / 'quicklook.png', ss, main_final, main_layers,
                     f'campus {prior} LGDM: red final change; dropped by the size filter: orange voted, purple removal, blue grown; grey prior (not a result)')
    except Exception as e:  # noqa: BLE001
        M.log('quicklook failed', repr(e))
    times['all_s'] = round(time.time() - T0, 1)
    rec0 = decisions['25']
    det = dict(site=SITE, prior=prior, rule=M.RULE, decisions_1015=M.DECISIONS_1015, pairs_file=str(pfile), pairs_sha256=sha(pfile),
               training_views=len(train), paired_views=npaired, views_without_pair=int(sum(1 for s in train if not pairs.get(s))),
               dz_values=int(ndz), buildings=binfo, recast_check=ver, cell_map_check=cell_cmp, colour_reference=colour, opening=opening,
               decisions=decisions, areas_m2=dict(vote=round(rec0['vote_cells'] * A, 2), removal_added=round(rec0['removal_added_cells'] * A, 2),
                                                  grown=round(rec0['growth_added_cells'] * A, 2), final=round(rec0['final_cells'] * A, 2),
                                                  final_20=decisions['20']['final_m2'], final_30=decisions['30']['final_m2'],
                                                  final_growth_dz_1p5m_reference=rec0['reference']['growth_dz_1p5m']['final_m2'],
                                                  prior_cells=round(float(prior_cells.sum()) * A, 2)),
               grid=dict(lo=grid.lo.tolist(), nx=grid.nx, ny=grid.ny), inputs=dict(prior_surface=str(LI.L / 'prior' / LI.CAMPUS_MESH[prior]),
                                                                                    mvs=str(LI.MVSD), images=str(LI.CAMPUS / 'images'), views=str(LI.CAMPUS / 'scene_LoD2/sparse/0')),
               gt_read=False, code_test_first_views=a.views or None, nproc=a.nproc, seconds=times, memory=mem(), scientific_verdict=None)
    M.jdump(RD / 'detect.json', det)
    M.log(json.dumps(dict(prior=prior, areas=det['areas_m2'], s=times, mem=det['memory'], recast=ver['max_abs_m'], cellcmp=cell_cmp['on_cell_surface_mismatch_share_max'])))


# ------------------------------------------------------------------------------------------------ step 3: compose (per cell)
def compose_w(stem):
    G = DT.G
    V, grid = G['V'], G['grid']
    n = f'{stem}.jpg'
    D = np.load(B / 'priordepth' / G['prior'] / f"cell{G['cell']}" / f'{stem}.npy').astype(np.float64)
    R = V.rays(n, np.float64)
    C = V.C(n)
    # detect.judge's re-cast check (detect.py:122-128, 667) of the cell prior map against the cell surface
    t, _ = DT.ocast(G['Pc'].scene(), np.broadcast_to(C, R.shape), R)
    t = t.reshape(M.H, M.W)
    h0 = np.isfinite(D)
    both = h0 & np.isfinite(t)
    ver = dict(mismatch_px=int((h0 != np.isfinite(t)).sum()), max_abs_m=float(np.abs(t[both] - D[both]).max()) if both.any() else 0.0)
    del t
    # detect.compose (detect.py:526-545, 551-552; the locmap / patch-record lines are not run)
    Mv = LI.mvs_map(stem).astype(np.float64)
    hit = np.isfinite(D) & (D > 0)
    mvs_ok = np.isfinite(Mv) & (Mv > 0)
    idx = np.flatnonzero(hit)
    X = C[None, :] + D.ravel()[idx][:, None] * R.reshape(-1, 3)[idx]
    cell = grid.cell(X)
    chg_h = np.zeros(len(idx), bool)
    chg_h[cell >= 0] = G['final_flat'][cell[cell >= 0]]
    chg = np.zeros(M.H * M.W, bool)
    chg[idx[chg_h]] = True
    chg = chg.reshape(M.H, M.W)
    mv = np.where(mvs_ok, Mv, np.nan)
    out = np.where(hit, np.where(chg, mv, D), mv).astype(np.float32)
    np.save(G['depth_dir'] / f'{stem}.npy', out)
    nop = ~hit & mvs_ok
    return dict(view=stem, ver=ver, pixels=int(out.size), prior_px=int(hit.sum()), prior_kept_px=int((hit & ~chg).sum()), replaced_by_mvs_px=int((chg & mvs_ok).sum()),
                emptied_px=int((chg & ~mvs_ok).sum()), filled_from_mvs_px=int(nop.sum()), empty_without_prior_px=int((~hit & ~mvs_ok).sum()),
                change_px=int(chg.sum()), prior_outside_grid_px=int((cell < 0).sum()), finite_px=int(np.isfinite(out).sum()))


def run_compose(a):
    LI.lcfg()
    prior = a.prior
    BD = base(a) / prior
    cz = np.load(BD / 'detect/cells.npz')
    final = cz['final']
    V = LI.campus_views()
    grid = LI.CampusGrid()
    assert final.shape == (grid.ny, grid.nx)
    cells = range(4) if a.cell == 'all' else [int(a.cell)]
    for k in cells:
        T0 = time.time()
        views = LI.cell_train(k)
        if a.views:
            views = views[:a.views]
        OD = BD / f'cell{k}'
        if (OD / 'compose.json').exists() and (OD / 'depth').exists():
            have = sorted(p.stem for p in (OD / 'depth').glob('*.npy'))
            M.log('cell', k, 'already made:', len(have), 'files; expected', len(views), 'same names', have == sorted(views))
            continue
        tmp = OD / 'depth_tmp'
        if tmp.exists():
            shutil.rmtree(tmp)
        tmp.mkdir(parents=True)
        Pc = LI.MeshOnly(B / 'prior' / f'cell{k}' / LI.NAME[prior])
        DT.G.clear()
        DT.G.update(V=V, grid=grid, prior=prior, cell=k, Pc=Pc, final_flat=final.ravel(), depth_dir=tmp)
        ctx = mp.get_context('fork')
        with ctx.Pool(a.nproc) as pool:
            comp = pool.map(compose_w, views, chunksize=2)
        bad = [r['view'] for r in comp if r['ver']['mismatch_px'] > 0.001 * M.H * M.W or r['ver']['max_abs_m'] > 0.01]
        ver = dict(views=len(comp), max_mismatch_px=max(r['ver']['mismatch_px'] for r in comp), max_abs_m=max(r['ver']['max_abs_m'] for r in comp),
                   views_failing=bad, rule='detect.judge re-cast check (mismatch <= 0.1 % of the pixels, |diff| <= 0.01 m) of OUT/priordepth/<prior>/cell<k> '
                                           'against an ocast of OUT/prior/cell<k>')
        if bad:
            M.jdump(OD / 'STOP_recast.json', dict(ver=ver, scientific_verdict=None))
            raise SystemExit(f'cell {k}: the cell prior map differs from the re-cast in {len(bad)} views: stop')
        tmp.rename(OD / 'depth')
        tot = {key: int(sum(r[key] for r in comp)) for key in ('pixels', 'prior_px', 'prior_kept_px', 'replaced_by_mvs_px', 'emptied_px', 'filled_from_mvs_px',
                                                               'empty_without_prior_px', 'change_px', 'prior_outside_grid_px', 'finite_px')}
        size = sum(p.stat().st_size for p in (OD / 'depth').glob('*.npy'))
        M.jdump(OD / 'compose.json', dict(prior=prior, cell=k, views=len(views), files=len(list((OD / 'depth').glob('*.npy'))), bytes=size,
                                       depth_dir=str(OD / 'depth'), format='camera-z metres, float32 [741, 1024], NaN = none (detect.compose)',
                                       change_map=str(BD / 'detect/cells.npz') + ' final (threshold 25)', change_map_sha256=sha(BD / 'detect/cells.npz'),
                                       prior_maps=str(B / 'priordepth' / prior / f'cell{k}'), recast_check=ver, totals=tot, per_view=comp,
                                       seconds=round(time.time() - T0, 1), memory=mem(), nproc=a.nproc, code_test_first_views=a.views or None,
                                       scientific_verdict=None))
        M.log('COMPOSE', prior, 'cell', k, len(views), 'views', tot, round(time.time() - T0, 1), 's', mem())


# ------------------------------------------------------------------------------------------------ step 4: patches
def run_patches(a):
    LI.lcfg()
    prior = a.prior
    BD = LI.L / prior
    cz = np.load(BD / 'detect/cells.npz')
    final, nsee = cz['final'].ravel(), cz['nsee'].ravel()
    grid = LI.CampusGrid()
    rows = []
    T0 = time.time()
    for p in sorted((JC2 / 'geometry_raw').glob(f'*__{prior}.npz')):
        tile = p.name.split('__')[0]
        g = np.load(p)
        c = grid.cell(g['centre'])
        ok = c >= 0
        inch = np.zeros(len(c), bool)
        inch[ok] = final[c[ok]]                       # detect.patch_flags (detect.py:356-359)
        jd = np.zeros(len(c), bool)
        jd[ok] = nsee[c[ok]] >= RC['min_views']       # detect.patch_flags (detect.py:360-361)
        f = BD / f'patches_{tile}.npz'
        np.savez_compressed(f, patch_id=g['patch_id'], in_change=inch, judged=jd, centre=g['centre'], normal=g['normal'], kind=g['kind'],
                            prior_height_m=g['prior_height_m'], mvs_mean_m=g['mvs_mean_m'])
        dsh = g['centre'] - g['raw_centre'] - g['shift_m']
        rows.append(dict(tile=tile, file=f.name, sha256=sha(f), patches=int(len(c)), in_change=int(inch.sum()), in_change_area_m2=round(float(g['area'][inch].sum()), 3),
                         judged=int(jd.sum()), outside_grid=int((~ok).sum()), area_m2=round(float(g['area'].sum()), 3),
                         kinds={str(int(kk)): dict(patches=int((g['kind'] == kk).sum()), in_change=int((inch & (g['kind'] == kk)).sum())) for kk in np.unique(g['kind'])},
                         centre_minus_raw_minus_shift_max_abs_m=float(np.abs(dsh).max())))
    tot = dict(tiles=len(rows), patches=sum(r['patches'] for r in rows), in_change=sum(r['in_change'] for r in rows),
               in_change_area_m2=round(sum(r['in_change_area_m2'] for r in rows), 3), judged=sum(r['judged'] for r in rows),
               outside_grid=sum(r['outside_grid'] for r in rows))
    M.jdump(BD / 'patches.json', dict(prior=prior, rule='inputs_LGDM.json patch_rule: in_change = final (25) at grid.cell(centre) = detect.patch_flags as JUDGEAPPLY '
                                                     'judgments.py:54-58 (region 4 = 2 MVS height if in_change else 1 prior height); judged = cell nsee >= 2',
                                   source=str(JC2 / 'geometry_raw'), change_map_sha256=sha(BD / 'detect/cells.npz'), totals=tot, tiles=rows,
                                   seconds=round(time.time() - T0, 1), scientific_verdict=None))
    M.log('PATCHES', prior, tot)


# ------------------------------------------------------------------------------------------------ receipt
def run_receipt(a):
    lk = json.loads((C / 'inputs_LGDM.lock.json').read_text())
    LI.lcfg()
    prior = a.prior
    BD = LI.L / prior
    det = json.loads((BD / 'detect/detect.json').read_text())
    comp = {k: json.loads((BD / f'cell{k}' / 'compose.json').read_text()) for k in range(4)}
    pat = json.loads((BD / 'patches.json').read_text())
    pr = json.loads((LI.L / 'prior/receipt.json').read_text())
    pj = json.loads((LI.L / 'prep/pairs_campus.json').read_text())
    du = lambda p: sum(f.stat().st_size for f in Path(p).rglob('*') if f.is_file())
    rc = dict(task_id='PHD-MAIN-BASE151-v1', method='LGDM = MVS 기반 결합 (Zhou 외 2020 재현, BASELINES mvsfuse) over the campus', prior=prior, status='PASS',
              config=dict(file=lk['file'], sha256=lk['config_sha256']), training=None, gpu=None,
              unit=dict(judge_decide='campus (819 training views)', compose='per cell (cells.json images)'),
              areas_m2=det['areas_m2'], change_area_m2=det['areas_m2']['final'],
              change_patches=pat['totals'], recast_check=det['recast_check'], cell_map_check=det['cell_map_check'],
              compose={f'cell{k}': dict(views=v['views'], files=v['files'], bytes=v['bytes'], recast_check={kk: v['recast_check'][kk] for kk in ('views', 'max_mismatch_px', 'max_abs_m', 'views_failing')},
                                        totals=v['totals'], seconds=v['seconds'], memory=v['memory']) for k, v in comp.items()},
              pairs=dict(file=str(LI.L / 'prep/pairs_campus.json'), training_views=pj['training_views'], paired=pj['paired'], without_pair=pj['without_pair'],
                         overlap_quantiles_5_25_50_75_95=pj['overlap_quantiles_5_25_50_75_95'], seconds=pj['seconds']),
              prior_surface={kk: vv for kk, vv in pr[prior].items()}, grid=pr['grid'],
              seconds=dict(prior_surface_both_priors=pr['seconds'], pairs=pj['seconds'], judge=det['seconds'], compose={f'cell{k}': v['seconds'] for k, v in comp.items()},
                           patches=pat['seconds']),
              memory=dict(judge=det['memory'], compose={f'cell{k}': v['memory'] for k, v in comp.items()}),
              bytes=dict(detect=du(BD / 'detect'), depth={f'cell{k}': comp[k]['bytes'] for k in range(4)}, patches=sum(f.stat().st_size for f in BD.glob('patches_*.npz')),
                         prior_surface=(LI.L / 'prior' / LI.CAMPUS_MESH[prior]).stat().st_size),
              files=dict(depth={f'cell{k}': comp[k]['files'] for k in range(4)}, patches=len(list(BD.glob('patches_*.npz')))),
              gt_read=False, scientific_verdict=None)
    M.jdump(LI.L / f'receipt_{prior}.json', rc)
    M.log('RECEIPT', prior, rc['change_area_m2'], rc['change_patches'])


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('step', choices=['judge', 'compose', 'patches', 'receipt'])
    ap.add_argument('prior', choices=['LoD2', 'ALS'])
    ap.add_argument('cell', nargs='?', default='all')
    ap.add_argument('--nproc', type=int, default=6)
    ap.add_argument('--views', type=int, default=0)
    a = ap.parse_args()
    dict(judge=run_judge, compose=run_compose, patches=run_patches, receipt=run_receipt)[a.step](a)
