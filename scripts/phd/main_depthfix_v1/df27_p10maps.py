"""판 10 (diagnostic, uses GT; rule of 11-24 16h) target maps, CPU. usage: df27_p10maps.py <stem>
GT depth buffer = TARGETPATH tp0 (nearest GT point per pixel, 3×3 minimum; GTJUDGE dense + normal points in the view box).
Owner buffer = the same rule on the GT rows that carry the point→patch link used for the point groups (GTJUDGE scenes/<stem>/rows.npz row_owner ->
JUDGEAPPLY core source_index = patch; TRAINERR a2_common.gt_row_patch): per pixel the nearest row point (3×3 window, nearest depth) and its patch.
Pixel with GT buffer:
  if the owner-buffer point exists, belongs to an active patch, and its depth is within 0.5 m of the GT buffer depth (= it is the frontmost visible GT point):
     owner = that patch; target depth = depth where the pixel ray meets the owner patch's 판 0 target plane (point = target, normal); weight 1;
  else ('the GT point belongs to no patch'): the 판 9 (cell_ga) pixel, weight 1 where it has a target.
Pixel without GT buffer: the 판 9 pixel, weight 1 where it has a target. Seeds etc. as 판 1 (family base).
writes /df/maps/base/cell_diag_owner/<stem>/*.npz + index.json, arm folder p10, receipt with the share of owner pixels whose target differs from the GT buffer by > 0.5 m."""
import sys, os, shutil
sys.path.insert(0, '/repo/scripts/phd/main_depthfix_v1')
from df_common import *
from scipy.ndimage import minimum_filter
TP = PH/'main_targetpath_v1/PHD-MAIN-TARGETPATH-v1'; GJ = PH/'main_gtjudge_v1/PHD-MAIN-GTJUDGE-v1'; JA = PH/'main_judgeapply_v1/PHD-MAIN-JUDGEAPPLY-v1'
H, W = 741, 1024

def owner_buffer(P, own, K, M):
    Pc = P@M[:3, :3].T + M[:3, 3]; z = Pc[:, 2]; ok = z > .1
    u = np.floor(K[0, 0]*Pc[ok, 0]/z[ok] + K[0, 2] + .5).astype(int); v = np.floor(K[1, 1]*Pc[ok, 1]/z[ok] + K[1, 2] + .5).astype(int); zz = z[ok]; oo = own[ok]
    q = (u >= 0) & (u < W) & (v >= 0) & (v < H); lin = v[q]*W + u[q]; zz = zz[q]; oo = oo[q]
    buf = np.full(H*W, np.inf, 'f4'); idx = np.full(H*W, -1, 'i8')
    if not len(lin): return buf.reshape(H, W), idx.reshape(H, W)
    o = np.lexsort((zz, lin)); l2 = lin[o]; f = np.r_[True, l2[1:] != l2[:-1]]; buf[l2[f]] = zz[o][f]; idx[l2[f]] = oo[o][f]
    buf = buf.reshape(H, W); idx = idx.reshape(H, W)
    # 3×3: nearest depth in the window and its owner
    mb = minimum_filter(buf, size=3, mode='nearest'); mi = np.full((H, W), -1, 'i8')
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            sb = np.roll(np.roll(buf, dy, 0), dx, 1); si = np.roll(np.roll(idx, dy, 0), dx, 1); hit = (sb == mb) & (mi < 0) & np.isfinite(mb); mi[hit] = si[hit]
    return mb, mi

def main(stem):
    t0 = time.monotonic(); site, prior = stem.split('__')
    tb = loadz(O/'families/base/targets'/f'{stem}.npz', ['target', 'normal', 'sigma', 'surface_exists'])
    a11 = loadz(GJ/'addendum11/final_data'/f'{stem}.npz', ['reference__xyz']); rows = loadz(GJ/'scenes'/stem/'rows.npz', ['row_owner']); core = loadz(JA/'core_points'/f'{stem}.npz', ['source_index'])
    ro = rows['row_owner']; assert len(ro) == len(a11['reference__xyz'])
    patch = np.where(ro >= 0, core['source_index'][np.clip(ro, 0, None)], -1); patch = np.where((patch >= 0) & tb['surface_exists'][np.maximum(patch, 0)], patch, -1)
    G = a11['reference__xyz'].astype('f8'); keep = patch >= 0; Gp, pp = G[keep], patch[keep]
    n = tb['normal']/np.linalg.norm(tb['normal'], axis=1)[:, None]
    idx9 = json.loads((O/'maps/base/cell_ga'/stem/'index.json').read_text()); dest = O/'maps/base/cell_diag_owner'/stem
    if dest.exists(): shutil.rmtree(dest)
    dest.mkdir(parents=True); idx = dict(idx9, variant='cell_diag_owner', at=now(), views={}, rule=__doc__.split('\n')[0])
    st = dict(gt_pixels=0, owner_pixels=0, owner_off_gt_05=0, fallback_gt_pixels=0, no_gt_pixels_with_target=0, rows_linked=int(keep.sum()), rows_total=len(patch))
    for jv, (name, meta) in enumerate(idx9['views'].items()):
        K = np.asarray(meta['K']); M = np.asarray(meta['W2C']); Cc = cam_centre(M)
        z9 = loadz(O/'maps/base/cell_ga'/stem/f'{name}.npz', ['depth', 'sigma', 'weight', 'owner']); gt = np.load(TP/'gtbuf'/site/f'{name}.npy'); gv = np.isfinite(gt)
        ob, oi = owner_buffer(Gp, pp, K, M); ow = gv & (oi >= 0) & (np.abs(ob - gt) <= .5)
        depth = z9['depth'].copy(); sigma = z9['sigma'].copy(); owner = z9['owner'].copy(); weight = np.where(z9['weight'] > 0, 1., 0.).astype('f4')
        ys, xs = np.nonzero(ow); p_ = oi[ys, xs]
        if len(p_):
            Rw = M[:3, :3]; tt = M[:3, 3]; c = tb['target'][p_]@Rw.T + tt; nn = n[p_]@Rw.T
            rx = (xs - K[0, 2])/K[0, 0]; ry = (ys - K[1, 2])/K[1, 1]; den = nn[:, 0]*rx + nn[:, 1]*ry + nn[:, 2]
            with np.errstate(divide='ignore', invalid='ignore'): zt = (nn*c).sum(1)/den
            good = np.isfinite(zt) & (zt > 0)
            depth[ys[good], xs[good]] = zt[good]; owner[ys[good], xs[good]] = p_[good]; sigma[ys[good], xs[good]] = tb['sigma'][p_[good]]; weight[ys[good], xs[good]] = 1
            st['owner_pixels'] += int(good.sum()); st['owner_off_gt_05'] += int((np.abs(zt[good] - gt[ys[good], xs[good]]) > .5).sum())
        st['gt_pixels'] += int(gv.sum()); st['fallback_gt_pixels'] += int((gv & ~ow & (z9['weight'] > 0)).sum()); st['no_gt_pixels_with_target'] += int((~gv & (z9['weight'] > 0)).sum())
        p = dest/f'{name}.npz'; savez(p, depth=depth.astype('f4'), sigma=sigma, weight=weight, owner=owner.astype('i4')); idx['views'][name] = dict(meta, file=p.name, sha256=sha(p))
        if (jv+1) % 40 == 0: print('P10', stem, jv+1, round(time.monotonic()-t0), flush=True)
    dump(dest/'index.json', idx)
    root = O/'arms/p10'; st_ = root/'stage1'/stem
    if st_.exists(): shutil.rmtree(st_)
    (root/'targets').mkdir(parents=True, exist_ok=True); tf = root/'targets'/f'{stem}.npz'
    if tf.exists(): tf.unlink()
    st_.mkdir(parents=True); os.link(O/'families/base/targets'/f'{stem}.npz', tf); os.link(O/'families/base/stage1'/stem/'seeds.npz', st_/'seeds.npz'); os.symlink(os.path.relpath(dest, st_), st_/'maps')
    dump(st_/'ready.json', dict(at=now(), arm='p10', stem=stem, maps='cell_diag_owner', family='base', two=False, target_sha256=sha(tf), seeds_sha256=sha(st_/'seeds.npz'), index_sha256=sha(st_/'maps/index.json'), scientific_verdict=None))
    st['owner_off_gt_05_pct'] = 100*st['owner_off_gt_05']/max(1, st['owner_pixels']); st['owner_share_of_gt_pixels_pct'] = 100*st['owner_pixels']/max(1, st['gt_pixels'])
    dump(O/'maps/base'/f'p10_receipt_{stem}.json', dict(at=now(), stem=stem, stats=st, seconds=time.monotonic()-t0, scientific_verdict=None)); print('P10_READY', stem, json.dumps(st), flush=True)

if __name__ == '__main__': main(sys.argv[1])
