"""Request 2 (11-24 15h): target maps drawn with patch CELLS instead of discs (CPU). usage: df24_cellmaps.py <stem>
Cell of a patch = its cell of the prior surface store (prior_propagation_v6 locations): parallelogram loc_center + sp*(a*loc_t1 + b*loc_t2), |a|,|b| <= 1/2
(LoD2: square on the polygon plane; TIN/ALS: the XY grid cell lifted onto the surface), moved along the patch normal by the 판 0 target height
(cell centre = 판 0 target point). Surfaces without member cells (loc_extra: one location at the centroid) get a square of side sqrt(area) on the patch plane
(closest available; issues 27). Rasterized by target_cells.cpp (target_discs.cpp rules, point-in-parallelogram instead of point-in-disc).
  cell_ga        (판 9)  : 판 1 rules on the cell map: back-facing cells not drawn per view, 10 m rule -> weight 0, no cell -> image depth (conf > 0), weight 1;
                          target / σ / weight as 판 1 (clip(σ_ref/σ, .1, 10))
  cell_ga_diag   (판 10, diagnostic, uses GT): cell_ga, then weight 0 where the GT depth buffer (TARGETPATH tp0) is nearer than the target depth by > τ of the owner
                          patch kind; then every target pixel with weight > 0 gets weight 1. Pixels without GT buffer as 판 9.
  cell_ga_na_da  (판 11) : cell_ga with switch 나 (clip(sqrt(σ_ref/σ), √.1, √10)) and 다 (type means over the cell_ga_na owner pixels with weight > 0), as 판 4 from 판 1.
Arm folders p9 / p10 / p11 = family base targets and seeds (as 판 1) + these maps."""
import sys, os, shutil
sys.path.insert(0, '/repo/scripts/phd/main_depthfix_v1')
from df_common import *
TP = PH/'main_targetpath_v1/PHD-MAIN-TARGETPATH-v1'

def lib():
    src = R/'scripts/phd/main_depthfix_v1/target_cells.cpp'; so = O/'tmp/raster/target_cells.so'; so.parent.mkdir(parents=True, exist_ok=True)
    if not so.exists(): subprocess.run(['g++', '-O3', '-shared', '-fPIC', str(src), '-o', str(so)], check=True)
    L = ctypes.CDLL(str(so)); f = L.target_cells; P = np.ctypeslib.ndpointer
    f.argtypes = [ctypes.c_int, P(np.float64, flags='C'), P(np.float64, flags='C'), P(np.float64, flags='C'), P(np.float64, flags='C'), ctypes.c_int, ctypes.c_int,
                  P(np.float32, flags='C'), P(np.int32, flags='C')]
    return f, src

def draw(fn, items, K, M, H=741, W=1024):
    depth = np.empty((H, W), np.float32); owner = np.empty((H, W), np.int32)
    fn(len(items), np.ascontiguousarray(items), np.ascontiguousarray(M[:3, :3]), np.ascontiguousarray(M[:3, 3]), np.ascontiguousarray(K), H, W, depth, owner)
    depth[owner < 0] = np.nan; return depth, owner

def main(stem):
    c = cfg(False); t0 = time.monotonic(); site, prior = stem.split('__'); roof, wall = tau_of(site, prior)
    tb = loadz(O/'families/base/targets'/f'{stem}.npz'); ids = np.flatnonzero(tb['surface_exists']); ref = float(tb['sigma_ref'])
    st = loadz(S0/'fork_inputs/s61'/site/f'store_{prior}.npz', ['sp', 'loc_center', 'loc_t1', 'loc_t2', 'loc_extra', 'frame_shift', 'loc_area'])
    sp = float(st['sp']); assert len(st['loc_center']) == len(tb['centre'])
    cshift = np.median(tb['centre'] - st['loc_center'], axis=0); dev = np.abs(tb['centre'] - st['loc_center'] - cshift).max()
    T1 = sp*st['loc_t1']; T2 = sp*st['loc_t2']; ex = st['loc_extra'].astype(bool)
    if ex.any():   # centroid locations: square of side sqrt(area) on the patch plane
        nrm = tb['normal'][ex]/np.linalg.norm(tb['normal'][ex], axis=1)[:, None]; a = np.cross(nrm, [0, 0, 1.]); bad = np.linalg.norm(a, axis=1) < 1e-6; a[bad] = np.cross(nrm[bad], [1., 0, 0])
        a /= np.linalg.norm(a, axis=1)[:, None]; b = np.cross(nrm, a); s = np.sqrt(tb['area'][ex])[:, None]; T1[ex] = s*a; T2[ex] = s*b
    items = np.c_[tb['target'][ids], tb['normal'][ids], T1[ids], T2[ids], ids].astype(np.float64)
    fn, src = lib(); bg_sigma = json.loads((O/'families/base/stage1'/stem/'seed_receipt.json').read_text())['background_sigma']
    ptau = np.where(tb['kind'] == 2, wall if prior == 'LoD2' else roof, roof); typ = loadz(O/'patchinfo'/f'{stem}.npz', ['type'])['type']
    idx1 = json.loads((O/'maps/base/ga'/stem/'index.json').read_text()); mvsroot = S0/'fork_inputs/s61'/site/'maps'; front_m = c['switches']['ga_front_m']
    V = ['cell_ga', 'cell_ga_diag', 'cell_ga_na_da']
    for v in V:
        dd = O/'maps/base'/v/stem
        if dd.exists(): shutil.rmtree(dd)
        dd.mkdir(parents=True)
    idx = {v: dict(idx1, variant=v, at=now(), views={}, rule=__doc__.split('\n')[0]) for v in V}
    sums = np.zeros((2, 4)); lo, hi = np.sqrt(.1), np.sqrt(10.); stats = dict(cell_pixels=0, disc_pixels_ga=0, diag_zeroed=0, gap_behind=0, gap_image=0, gap_none=0)
    names = list(idx1['views'])
    for jv, name in enumerate(names):
        meta = idx1['views'][name]; K = np.asarray(meta['K']); M = np.asarray(meta['W2C']); Cc = cam_centre(M)
        front = ((Cc[None] - tb['target'][ids])*tb['normal'][ids]).sum(1) > 0
        depth, owner = draw(fn, items[front], K, M); has = owner >= 0
        mvs = np.load(mvsroot/'mvs'/f'{name}.npy'); conf = np.load(mvsroot/'conf'/f'{name}.npy'); mvalid = np.isfinite(mvs) & (mvs > 0)
        sigma = np.full(depth.shape, np.nan, 'f4'); sigma[has] = tb['sigma'][owner[has]]; bgp = (~has) & mvalid & (conf > 0); depth[bgp] = mvs[bgp]; sigma[bgp] = bg_sigma
        weight = np.zeros(depth.shape, 'f4'); weight[has] = np.clip(ref/sigma[has], .1, 10); weight[bgp] = 1
        near = has & mvalid & (mvs < depth - front_m); weight[near] = 0
        p = O/'maps/base/cell_ga'/stem/f'{name}.npz'; savez(p, depth=depth, sigma=sigma, weight=weight, owner=owner, front_rule=near); idx['cell_ga']['views'][name] = dict(meta, file=p.name, sha256=sha(p))
        # gaps: pixels the disc map (판 1) gives a disc target but the cell map gives image depth / a target behind it / nothing
        g = loadz(O/'maps/base/ga'/stem/f'{name}.npz', ['depth', 'owner', 'weight']); gh = (g['owner'] >= 0) & (g['weight'] > 0)
        stats['cell_pixels'] += int(has.sum()); stats['disc_pixels_ga'] += int(gh.sum())
        stats['gap_image'] += int((gh & ~has & (weight > 0)).sum()); stats['gap_none'] += int((gh & ~has & (weight == 0)).sum())
        stats['gap_behind'] += int((gh & has & (depth > g['depth'] + np.where(gh, ptau[np.maximum(g['owner'], 0)], 0))).sum())
        # 판 10
        gt = np.load(TP/'gtbuf'/site/f'{name}.npy'); w10 = weight.copy(); z10 = has & np.isfinite(gt) & (gt < depth - np.where(has, ptau[np.maximum(owner, 0)], 0))
        w10[z10] = 0; w10[has & (w10 > 0)] = 1; stats['diag_zeroed'] += int((z10 & (weight > 0)).sum())
        p = O/'maps/base/cell_ga_diag'/stem/f'{name}.npz'; savez(p, depth=depth, sigma=sigma, weight=w10, owner=owner); idx['cell_ga_diag']['views'][name] = dict(meta, file=p.name, sha256=sha(p))
        # 판 11 pass 1 (나 then type means)
        wn = weight.copy(); m = has & (wn > 0); wn[m] = np.clip(np.sqrt(ref/sigma[m]), lo, hi); ty = np.where(has, typ[np.maximum(owner, 0)], -1)
        for k in range(4): mk = m & (ty == k); sums[0, k] += wn[mk].sum(); sums[1, k] += mk.sum()
        if (jv+1) % 40 == 0: print('CELL', stem, jv+1, round(time.monotonic()-t0), flush=True)
    fac = {k: float(sums[0, k]/sums[1, k]) if sums[1, k] else None for k in range(4)}
    for name in names:
        z = loadz(O/'maps/base/cell_ga'/stem/f'{name}.npz', ['depth', 'sigma', 'weight', 'owner']); has = z['owner'] >= 0; w = z['weight'].copy(); m = has & (w > 0)
        w[m] = np.clip(np.sqrt(ref/z['sigma'][m]), lo, hi); ty = np.where(has, typ[np.maximum(z['owner'], 0)], -1)
        for k in range(4):
            mk = m & (ty == k)
            if fac[k]: w[mk] = w[mk]/fac[k]
        p = O/'maps/base/cell_ga_na_da'/stem/f'{name}.npz'; savez(p, depth=z['depth'], sigma=z['sigma'], weight=w, owner=z['owner']); idx['cell_ga_na_da']['views'][name] = dict(idx1['views'][name], file=p.name, sha256=sha(p))
    idx['cell_ga_na_da']['type_mean_weight'] = {TYPE_KO[k]: f for k, f in fac.items()}
    for v in V: dump(O/'maps/base'/v/stem/'index.json', idx[v])
    for arm, a in c['arms'].items():
        if a['maps'] not in V: continue
        root = O/'arms'/arm; st_ = root/'stage1'/stem
        if st_.exists(): shutil.rmtree(st_)
        (root/'targets').mkdir(parents=True, exist_ok=True); tf = root/'targets'/f'{stem}.npz'
        if tf.exists(): tf.unlink()
        st_.mkdir(parents=True); os.link(O/'families'/a['family']/'targets'/f'{stem}.npz', tf); os.link(O/'families'/a['family']/'stage1'/stem/'seeds.npz', st_/'seeds.npz')
        os.symlink(os.path.relpath(O/'maps/base'/a['maps']/stem, st_), st_/'maps')
        dump(st_/'ready.json', dict(at=now(), arm=arm, stem=stem, maps=a['maps'], family=a['family'], two=a['two'], target_sha256=sha(tf), seeds_sha256=sha(st_/'seeds.npz'),
             index_sha256=sha(st_/'maps/index.json'), scientific_verdict=None))
    rec = dict(at=now(), stem=stem, sp=sp, centre_shift_store_to_target=cshift.tolist(), centre_max_deviation_m=float(dev), extra_locations=int(ex.sum()),
               extra_locations_active=int(ex[ids].sum()), stats=stats, gap_share_of_disc_pixels_pct=100*(stats['gap_image'] + stats['gap_behind'] + stats['gap_none'])/max(1, stats['disc_pixels_ga']),
               type_mean_weight_p11={TYPE_KO[k]: f for k, f in fac.items()}, cpp_sha256=sha(src), seconds=time.monotonic()-t0, scientific_verdict=None)
    dump(O/'maps/base'/f'cell_receipt_{stem}.json', rec); print('CELL_READY', stem, json.dumps(rec, ensure_ascii=False)[:700], flush=True)

if __name__ == '__main__': main(sys.argv[1])
