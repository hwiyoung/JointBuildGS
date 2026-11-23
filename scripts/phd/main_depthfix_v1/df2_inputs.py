"""Seeds and target-depth maps (CPU). usage: df2_inputs.py <family> <stem> [maps]
Seeds: FINALTRAIN prepare_inputs.seeds() rule, copied unchanged except paths (outside receipt read from FINALTRAIN).
Maps (family base, or ftcheck = FINALTRAIN target file for the byte check), per training view (FINALTRAIN maps/index.json K, W2C, order):
  variant base : FINALTRAIN prepare_inputs map rule unchanged (all discs, nearest wins; no disc + MVS valid & conf>0 -> MVS depth, weight 1)
  variant ga   : switch 가 — discs whose normal faces away from the camera (n·(C − disc centre) <= 0) are not drawn in that view;
                 then target pixels whose image depth (STAGE0 maps/mvs, finite > 0, no conf filter) is nearer than the target depth by > 10 m get weight 0.
                 Pixels left without a disc follow the base background rule (image depth, weight 1).
writes /df/families/<fam>/stage1/<stem>/seeds.npz, /df/maps/<fam>/<variant>/<stem>/<view>.npz + index.json"""
import sys, os
sys.path.insert(0, '/repo/scripts/phd/main_depthfix_v1')
from df_common import *
from plyfile import PlyData

def seeds(site, prior, t, root):
    """FINALTRAIN scripts/phd/main_finaltrain_v1/prepare_inputs.py seeds(), unchanged except O -> FT for the outside receipt."""
    sys.path.insert(0, str(R))
    from src.phd.prior_propagation_v6.locations import locate
    from src.phd.prior_propagation_v6.orientation import quat_from_normal
    f=S0/'fork_inputs/s61'/site;source=f/f'scene_{prior}/sparse/0';ply=source/'points3D.ply'
    v=PlyData.read(str(ply))['vertex'];xyz=np.c_[v['x'],v['y'],v['z']].astype('f4');rgb=np.c_[v['red'],v['green'],v['blue']].astype('f4')/255
    origin=np.load(source/'origin.npy');seat=np.load(f/f'seat_{prior}.npy');store=loadz(f/f'store_{prior}.npz')
    loc=np.full(len(xyz),-1,np.int64);has=(origin==1)&(seat>=0);loc[has]=locate(store,seat[has],xyz[has].astype(float))
    keep=np.flatnonzero(has&(loc>=0)&t['surface_exists'][np.maximum(loc,0)]);pid=loc[keep]
    raw=loadz(TG/'stage0_r1/inputs'/f'{site}_{prior}.npz')
    c2=json.loads((R/'configs/phd/main_target_v1/revisions/r2/target_v1.json').read_text())
    radius=np.array([c2['inherited_radius'][prior][str(int(k))]['radius_m'] or np.nan for k in raw['kind']])
    fallback=json.loads((FT/'outside'/site/'budget_receipt.json').read_text())['status']=='TIME_LIMIT_BACKGROUND_FALLBACK'
    exclude_mask=raw['in_eval'] if fallback else np.ones(len(radius),bool)
    cores=root/'cylinders.bin';np.c_[raw['centre'][exclude_mask],raw['normal'][exclude_mask],np.where(raw['kind'][exclude_mask]==1,10.,5.),radius[exclude_mask]].astype('<f8').tofile(cores)
    ids=np.flatnonzero(origin==0);np.save(root/'sfm_original_xyz.npy',xyz[ids]);cpp=R/'scripts/phd/main_target_v1/exclude_cylinders_r2.cpp';binary=root/'exclude_cylinders'
    subprocess.run(['g++','-O3','-std=c++17',str(cpp),'-o',str(binary)],check=True)
    with (root/'sfm_original_xyz.npy').open('rb') as fh:
        version=np.lib.format.read_magic(fh);np.lib.format._read_array_header(fh,version);offset=fh.tell()
    subprocess.run([str(binary),str(root/'sfm_original_xyz.npy'),str(offset),str(len(ids)),str(cores),str(int(exclude_mask.sum())),str(root/'excluded.bin')],check=True)
    excluded=np.fromfile(root/'excluded.bin',dtype=np.uint8).astype(bool);bg=ids[~excluded];nb=len(bg)
    raw_u=raw['mvs_a_u'];donors=raw_u[(raw['kind']==1)&np.isfinite(raw_u)]
    assert len(donors) and np.median(donors)>0;bg_sigma=float(np.hypot(np.median(donors),.0275))
    normal=np.r_[t['normal'][pid],np.tile([0.,0.,1.],(nb,1))];pos=np.r_[t['target'][pid],xyz[bg]]
    sigma=np.r_[t['sigma'][pid],np.full(nb,bg_sigma)]
    assert np.isfinite(pos).all() and np.isfinite(sigma).all() and (sigma>0).all()
    savez(root/'seeds.npz',original_xyz=xyz,keep_original=keep,xyz=pos.astype('f4'),target=pos.astype('f4'),normal=normal.astype('f4'),sigma=sigma.astype('f4'),
        quaternion=quat_from_normal(normal).astype('f4'),origin=np.r_[np.ones(len(pid),'i1'),np.zeros(nb,'i1')],region=np.r_[t['region'][pid],np.full(nb,4,'i1')],
        patch=np.r_[pid,np.full(nb,-1,'i8')],background_rgb=rgb[bg],background_original=bg,uncertainty_replaced=np.r_[t['sigma_replaced'][pid],np.ones(nb,bool)])
    rec=dict(at=now(),prior_kept=len(pid),background_kept=nb,source_ply_sha256=sha(ply),seeds_sha256=sha(root/'seeds.npz'),exclusion_code_sha256=sha(cpp),
        fallback_outside_background=fallback,background_sigma=bg_sigma,rule='FINALTRAIN prepare_inputs.seeds() unchanged',scientific_verdict=None)
    for p_ in [root/'sfm_original_xyz.npy', root/'excluded.bin', root/'cylinders.bin', binary]: p_.unlink()
    dump(root/'seed_receipt.json',rec);return bg_sigma

def target_file(fam, stem): return FT/'targets'/f'{stem}.npz' if fam == 'ftcheck' else O/'families'/fam/'targets'/f'{stem}.npz'

def main(fam, stem, what='all'):
    c = cfg(False); t0 = time.monotonic(); site, prior = stem.split('__'); tp = target_file(fam, stem); t = loadz(tp)
    root = O/'families'/fam/'stage1'/stem
    if what in ('all', 'seeds'):
        root.mkdir(parents=True, exist_ok=False); bg_sigma = seeds(site, prior, t, root)
    else: bg_sigma = json.loads((root/'seed_receipt.json').read_text())['background_sigma']
    if what == 'seeds' or fam not in ('base', 'ftcheck'): print('SEEDS_READY', fam, stem, round(time.monotonic()-t0), flush=True); return
    env, src = rasterizer_env(); fn = env['rasterizer'](); ids = np.flatnonzero(t['surface_exists'])
    points = np.c_[t['target'][ids], t['normal'][ids], np.sqrt(t['area'][ids]/np.pi), ids].astype(float); ref = float(t['sigma_ref'])
    variants = ['base'] if fam == 'ftcheck' else ['base', 'ga']; front_m = c['switches']['ga_front_m']
    dests = {v: O/'maps'/fam/v/stem for v in variants}
    for v in variants: dests[v].mkdir(parents=True, exist_ok=False)
    fti = json.loads((FT/'stage1'/stem/'maps/index.json').read_text())
    idx = {v: dict(at=now(), site=site, prior=prior, variant=v, sigma_ref=ref, weight_power=1, background_weight=1, target_sha256=sha(tp), views={}, scientific_verdict=None) for v in variants}
    mvsroot = S0/'fork_inputs/s61'/site/'maps'; rows = []
    for jv, (name, fv) in enumerate(fti['views'].items()):
        K = np.asarray(fv['K']); M = np.asarray(fv['W2C']); cam = dict(H=741, W=1024, W2C=M, fx=K[0, 0], fy=K[1, 1], cx=K[0, 2], cy=K[1, 2])
        mvs = np.load(mvsroot/'mvs'/f'{name}.npy'); conf = np.load(mvsroot/'conf'/f'{name}.npy'); mvalid = np.isfinite(mvs) & (mvs > 0)
        Cc = cam_centre(M); front = ((Cc[None] - t['target'][ids])*t['normal'][ids]).sum(1) > 0
        for v in variants:
            pts = points if v == 'base' else points[front]
            depth, owner, K2, M2 = env['draw'](fn, pts, cam); assert np.allclose(K2, K) and np.allclose(M2, M)
            has = owner >= 0; sigma = np.full(depth.shape, np.nan, 'f4'); sigma[has] = t['sigma'][owner[has]]
            bg = (~has) & mvalid & (conf > 0); depth[bg] = mvs[bg]; sigma[bg] = bg_sigma
            weight = np.zeros(depth.shape, 'f4'); weight[has] = np.clip(ref/sigma[has], .1, 10); weight[bg] = 1
            extra = {}
            if v == 'ga':
                near = has & mvalid & (mvs < depth - front_m); weight[near] = 0; extra = dict(front_rule=near)
            p = dests[v]/f'{name}.npz'; savez(p, depth=depth, sigma=sigma, weight=weight, owner=owner, **extra)
            idx[v]['views'][name] = dict(file=p.name, sha256=sha(p), sigma_ref=ref, prior_pixels=int(has.sum()), background_pixels=int(bg.sum()), K=K.tolist(), W2C=M.tolist())
            if v == 'ga': rows.append(dict(view=name, discs=len(ids), back_discs=int((~front).sum()), owner_pixels=int(has.sum()), front_rule_pixels=int(extra['front_rule'].sum())))
        if (jv+1) % 40 == 0: print('MAPS', fam, stem, jv+1, round(time.monotonic()-t0), flush=True)
    for v in variants: dump(dests[v]/'index.json', idx[v])
    dump(O/'maps'/fam/f'receipt_{stem}.json', dict(at=now(), stem=stem, family=fam, variants=variants, seconds=time.monotonic()-t0, ga_views=rows,
         index_sha256={v: sha(dests[v]/'index.json') for v in variants}, seeds_sha256=sha(root/'seeds.npz'), target_sha256=sha(tp), scientific_verdict=None))
    print('MAPS_READY', fam, stem, round(time.monotonic()-t0), flush=True)

if __name__ == '__main__': main(*sys.argv[1:])
