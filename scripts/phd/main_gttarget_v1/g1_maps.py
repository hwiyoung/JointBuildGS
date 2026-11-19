"""Stage 1 (order 4): per training view the target depth map with the four orders and the occlusion checks.
usage (CPU container): g1_maps.py <stem>
order 1 GT disc drawn, not occluded -> GT depth, weight 1, owner patch | order 2 GT disc drawn but occluded -> no depth, weight 0, owner -1
order 3 no GT disc, valid image depth -> image depth, weight 1 (FINALTRAIN rule) | order 4 otherwise.
occluded = back-facing front disc | GT point depth buffer (3x3 min) nearer than the disc by > margin | image depth nearer by > 10 m.
writes /gt/stage1/<stem>/maps/<view>.npz (depth, sigma, weight, owner: FINALTRAIN layout) + index.json, /gt/stage1/<stem>/occl/<view>.npz (order code u1)"""
import sys, ast, ctypes, subprocess, time
sys.path.insert(0, '/repo/scripts/phd/main_gttarget_v1')
from gt_common import *
from scipy.ndimage import minimum_filter

def rasterizer_env():
    src = R/'scripts/phd/main_target_v1/prepare_maps_r7.py'; tree = ast.parse(src.read_text())
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in ('rasterizer', 'draw')]; assert len(nodes) == 2
    env = dict(np=np, ctypes=ctypes, subprocess=subprocess, Path=Path, __file__=str(src), OUT=O)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(src), 'exec'), env); return env, src

def gt_points(site):
    a = loadz(GT/'reference'/site/'dense.npz', ['xyz']); b = loadz(GT/'reference'/site/'normal_points.npz', ['xyz'])
    P = np.r_[a['xyz'], b['xyz'].astype('f8')]; box = view_box(site); return P[((P >= box[0]) & (P <= box[1])).all(1)]

def main(stem):
    c = cfg(1); mc = c['maps']; t0 = time.monotonic(); site, prior = stem.split('__'); root = O/'stage1'/stem; dest = root/'maps'; occd = root/'occl'
    dest.mkdir(parents=True, exist_ok=False); occd.mkdir(parents=True, exist_ok=True)
    tp = O/'targets'/f'{stem}.npz'; t = loadz(tp); ref = float(t['sigma_ref']); ids = np.flatnonzero(t['surface_exists'])
    fs = loadz(FT/'stage1'/stem/'seeds.npz', ['sigma', 'origin']); bg_sigma = float(np.unique(fs['sigma'][fs['origin'] == 0])[0])
    fti = json.loads((FT/'stage1'/stem/'maps/index.json').read_text())
    env, src = rasterizer_env(); fn = env['rasterizer']()
    points = np.c_[t['target'][ids], t['normal'][ids], np.sqrt(t['area'][ids]/np.pi), ids].astype(float)
    G = gt_points(site); mvsroot = S0/'fork_inputs/s61'/site/'maps'
    index = dict(at=now(), site=site, prior=prior, title=TITLE, sigma_ref=ref, weight_power=1, background_weight=1, target_sha256=sha(tp),
                 background_sigma=bg_sigma, rule=mc, input_files={str(p): sha(p) for p in [src, src.with_name('target_discs.cpp'), FT/'stage1'/stem/'maps/index.json']},
                 views={}, scientific_verdict=None)
    rows = []
    for j, (name, fv) in enumerate(fti['views'].items()):
        K = np.asarray(fv['K']); M = np.asarray(fv['W2C']); cam = dict(H=741, W=1024, W2C=M, fx=K[0, 0], fy=K[1, 1], cx=K[0, 2], cy=K[1, 2])
        depth, owner, K2, M2 = env['draw'](fn, points, cam); assert np.allclose(K2, K) and np.allclose(M2, M)
        H, W = depth.shape; has = owner >= 0
        yy, xx = np.nonzero(has); ray = np.c_[(xx-K[0, 2])/K[0, 0], (yy-K[1, 2])/K[1, 1], np.ones(len(xx))]
        nc = t['normal'][owner[yy, xx]]@M[:3, :3].T; back = np.zeros((H, W), bool); back[yy, xx] = (nc*ray).sum(1) > 0
        # GT point depth buffer (nearest point per pixel), 3x3 minimum
        Pc = G@M[:3, :3].T+M[:3, 3]; z = Pc[:, 2]; ok = z > 0.1; u = np.floor(K[0, 0]*Pc[ok, 0]/z[ok]+K[0, 2]+.5).astype(int); v = np.floor(K[1, 1]*Pc[ok, 1]/z[ok]+K[1, 2]+.5).astype(int)
        inn = (u >= 0) & (u < W) & (v >= 0) & (v < H); buf = np.full(H*W, np.inf, 'f4'); np.minimum.at(buf, v[inn]*W+u[inn], z[ok][inn].astype('f4'))
        buf = minimum_filter(buf.reshape(H, W), size=3, mode='nearest')
        gtocc = has & (buf < depth-mc['gt_point_occlusion_margin_m'])
        mvs = np.load(mvsroot/'mvs'/f'{name}.npy'); conf = np.load(mvsroot/'conf'/f'{name}.npy'); mvalid = np.isfinite(mvs) & (mvs > 0)
        mvsocc = has & mvalid & (mvs < depth-mc['mvs_occlusion_m'])
        occ = has & (back | gtocc | mvsocc); o1 = has & ~occ; o3 = (~has) & mvalid & (conf > 0); code = np.full((H, W), 4, 'u1'); code[o1] = 1; code[occ] = 2; code[o3] = 3
        D = np.full((H, W), np.nan, 'f4'); D[o1] = depth[o1]; D[o3] = mvs[o3]
        S = np.full((H, W), np.nan, 'f4'); S[o1] = ref; S[o3] = bg_sigma
        Wt = np.zeros((H, W), 'f4'); Wt[o1] = np.clip(ref/S[o1], .1, 10); Wt[o3] = 1
        Ow = np.full((H, W), -1, 'i4'); Ow[o1] = owner[o1]
        p = dest/f'{name}.npz'; savez(p, depth=D, sigma=S, weight=Wt, owner=Ow); savez(occd/f'{name}.npz', code=code, back=back & has, gt_occluded=gtocc, mvs_occluded=mvsocc)
        index['views'][name] = dict(file=p.name, sha256=sha(p), sigma_ref=ref, prior_pixels=int(o1.sum()), background_pixels=int(o3.sum()), K=K.tolist(), W2C=M.tolist(),
                                    order_pixels=[int((code == k).sum()) for k in (1, 2, 3, 4)], ft_prior_pixels=int(fv['prior_pixels']), ft_background_pixels=int(fv['background_pixels']))
        rows.append(dict(stem=stem, view=name, order1=int(o1.sum()), order2=int(occ.sum()), order3=int(o3.sum()), order4=int((code == 4).sum()),
                         order2_backface=int((back & has).sum()), order2_gt_points=int(gtocc.sum()), order2_mvs_10m=int(mvsocc.sum()),
                         ft_prior_pixels=int(fv['prior_pixels']), ft_background_pixels=int(fv['background_pixels']), pixels=H*W))
        if (j+1) % 40 == 0: print('MAPS', stem, j+1, round(time.monotonic()-t0), flush=True)
    dump(dest/'index.json', index); table(f'stage1/maps_{stem}', rows)
    tot = {k: sum(r[k] for r in rows) for k in ['order1', 'order2', 'order3', 'order4', 'order2_backface', 'order2_gt_points', 'order2_mvs_10m', 'ft_prior_pixels', 'ft_background_pixels', 'pixels']}
    rec = dict(at=now(), stem=stem, title=TITLE, views=len(rows), totals=tot, seconds=time.monotonic()-t0, index_sha256=sha(dest/'index.json'), target_sha256=sha(tp),
               seeds_sha256=sha(root/'seeds.npz'), scientific_verdict=None)
    dump(root/'ready.json', rec); print('MAPS_READY', stem, json.dumps(tot), round(rec['seconds']), flush=True)

if __name__ == '__main__': main(sys.argv[1])
