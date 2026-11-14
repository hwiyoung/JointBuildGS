"""Addendum 4 work sa-3 input build (configs/phd/main_trainerr_v1/addendum4_sa3.json). Runs in the FINALTRAIN CPU image with
/out = FINALTRAIN payload (read only) and /a4 = addendum4 payload sa3 folder (rw). Writes /a4/targets/<stem>.npz and /a4/stage1/<stem>/.
The FINALTRAIN functions (targets.calculate formulas, prepare_inputs.seeds, prepare_maps_r7 rasterizer) are called unchanged."""
import ctypes, subprocess, sys, time
sys.path.insert(0, '/repo/scripts/phd/main_finaltrain_v1')
from common import *
import prepare_inputs as P

A4 = Path('/a4'); SITE, PRIOR = 'B173nb_b10', 'ALS'; STEM = f'{SITE}__{PRIOR}'; NEW = STEM + '_nojudge'

def targets():
    t = loadz(O/'targets'/f'{STEM}.npz')
    hp, sp, nrm = t['prior_height_m'], t['sigma_P_m'], t['normal']
    ok = np.isfinite(hp) & np.isfinite(sp) & (sp > 0) & np.isfinite(nrm).all(1) & (np.linalg.norm(nrm, axis=1) > 0)
    h = np.where(ok, hp, np.nan); sigma = np.where(ok, sp, np.nan)
    region = np.where(ok, 2, -1).astype('i1'); judge = np.where(ok, 1, 9).astype('i1')
    area = t['area']; ref = float(area[ok].sum()/np.sum(area[ok]/sigma[ok]))
    new = dict(t); new.update(region=region, judge_region=judge, h=h, sigma=sigma, target=t['centre']+h[:, None]*nrm, target_height_m=h, target_sigma_m=sigma,
                              surface_exists=ok, sigma_ref=np.asarray(ref), sigma_replaced=np.zeros(len(h), bool), any_replaced=np.zeros(len(h), bool))
    p = A4/'targets'/f'{NEW}.npz'; savez(p, **new)
    old = t['surface_exists']; jr = t['judge_region']
    rec = dict(at=now(), source=str(O/'targets'/f'{STEM}.npz'), source_sha256=sha(O/'targets'/f'{STEM}.npz'), output=str(p), output_sha256=sha(p), patches=len(h),
               surface_patches=int(ok.sum()), surface_area_m2=float(area[ok].sum()), original_surface_patches=int(old.sum()), original_surface_area_m2=float(area[old].sum()),
               original_judge_region_of_new_surface={str(int(r)): dict(patches=int((ok & (jr == r)).sum()), area_m2=float(area[ok & (jr == r)].sum())) for r in np.unique(jr)},
               original_surface_without_prior=dict(patches=int((old & ~ok).sum()), area_m2=float(area[old & ~ok].sum())), sigma_ref=ref, scientific_verdict=None)
    dump(A4/'targets'/f'{NEW}.json', rec); print('TARGETS', rec, flush=True)
    return new, p

def maps(t, tp):
    root = A4/'stage1'/NEW; root.mkdir(parents=True, exist_ok=False)
    bg_sigma = P.seeds(SITE, PRIOR, t, root)
    src = R/'scripts/phd/main_target_v1/prepare_maps_r7.py'; (A4/'tmp').mkdir(exist_ok=True)
    env = dict(np=np, ctypes=ctypes, subprocess=subprocess, Path=Path, __file__=str(src), OUT=A4)
    P.named_functions(src, ['rasterizer', 'draw'], env); fn = env['rasterizer'](); ids = np.flatnonzero(t['surface_exists'])
    points = np.c_[t['target'][ids], t['normal'][ids], np.sqrt(t['area'][ids]/np.pi), ids].astype(float); ref = float(t['sigma_ref']); dest = root/'maps'; dest.mkdir()
    camera_root = S0/'fork_inputs/s61'/SITE
    index = dict(at=now(), site=SITE, prior=PRIOR, sigma_ref=ref, weight_power=1, background_weight=1, target_sha256=sha(tp), dual_depth=True,
                 rule='addendum4_sa3.json maps: depth/weight = prior-face discs only; depth2/weight2 = image depth (finite > 0, conf > 0) with weight 1',
                 input_files={str(p): sha(p) for p in [camera_root/'split.json', camera_root/'scene_LoD2/jbgs_calibration.json', camera_root/'scene_LoD2/sparse/0/images.bin', src, src.with_name('target_discs.cpp')]},
                 views={}, scientific_verdict=None)
    tot = dict(owner=0, image=0, both=0)
    for j, cam in enumerate(P.cameras(SITE)):
        depth, owner, K, M = env['draw'](fn, points, cam); has = owner >= 0; name = cam['name']
        sigma = np.full(depth.shape, np.nan, 'f4'); sigma[has] = t['sigma'][owner[has]]
        weight = np.zeros(depth.shape, 'f4'); weight[has] = np.clip(ref/sigma[has], .1, 10)
        old = camera_root/'maps'; mvs = np.load(old/'mvs'/f'{name}.npy'); conf = np.load(old/'conf'/f'{name}.npy')
        im = np.isfinite(mvs) & (mvs > 0) & (conf > 0); depth2 = np.where(im, mvs, np.nan).astype('f4'); weight2 = im.astype('f4')
        p = dest/f'{name}.npz'; savez(p, depth=depth, sigma=sigma, weight=weight, owner=owner, depth2=depth2, weight2=weight2)
        tot['owner'] += int(has.sum()); tot['image'] += int(im.sum()); tot['both'] += int((has & im).sum())
        index['views'][name] = dict(file=p.name, sha256=sha(p), sigma_ref=ref, prior_pixels=int(has.sum()), background_pixels=0, image_depth_pixels=int(im.sum()), K=K.tolist(), W2C=M.tolist(),
                                    mvs_input_sha256=sha(old/'mvs'/f'{name}.npy'), confidence_input_sha256=sha(old/'conf'/f'{name}.npy'))
        if (j+1) % 40 == 0: print('MAPS', j+1, flush=True)
    dump(dest/'index.json', index)
    rec = dict(at=now(), pixels=tot, background_sigma=bg_sigma, index_sha256=sha(dest/'index.json'), seeds_sha256=sha(root/'seeds.npz'), target_sha256=sha(tp), scientific_verdict=None)
    dump(root/'ready.json', rec); print('READY', rec, flush=True)

if __name__ == '__main__':
    t0 = time.monotonic(); t, tp = targets(); maps(t, tp); print('SECONDS', time.monotonic()-t0, flush=True)
