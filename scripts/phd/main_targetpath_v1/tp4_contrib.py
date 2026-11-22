"""Order 4 (and the rendered depth of B173 x ALS FINALTRAIN in order 2): per (point, view) pixel the splat contributions of the 30,000 model,
on the CPU (no GPU: the running trainings are not slowed). usage: tp4_contrib.py <stem> <run ft|gtt> <mode all|sub>
  all = every selected point; sub = groups 가: 잃음 and 나: 고침 (and for gtt only 가: 잃음 / 가: 지킴)
The compositing is a numpy copy of TRAINERR addendum4 a4_da.contrib (2DGS ray-splat intersection, low-pass rho = min(rho3d, 2 |d|^2),
alpha = min(opacity exp(-rho/2), 0.99), skip alpha < 1/255 or depth < 0.2, front-to-back in camera z order, stop when T(1-alpha) < 1e-4,
pixel coordinates = integer pixel index, 16 x 16 tiles with the 3-sigma rect of the inherited rasterizer). Gaussians are cropped to the
GTJUDGE view box like the stored base renders. Per pair: accumulated opacity, mean depth (depth_ratio 0), median depth (last splat with T > 0.5),
the three splats of largest weight (index into the 30,000 ply, weight, ray depth). Pairs = tp2_pixels.pairs_for_view.
Writes /tp/contrib/<run>_<stem>_<mode>.npz."""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_targetpath_v1')
from tp_common import *
from tp2_pixels import pairs_for_view
from concurrent.futures import ProcessPoolExecutor
H, W = 741, 1024
G = {}

def qrot(q):
    q = q/np.linalg.norm(q, axis=1, keepdims=True); r, x, y, z = q.T
    return np.stack([np.stack([1-2*(y*y+z*z), 2*(x*y-r*z), 2*(x*z+r*y)], -1), np.stack([2*(x*y+r*z), 1-2*(x*x+z*z), 2*(y*z-r*x)], -1),
                     np.stack([2*(x*z-r*y), 2*(y*z+r*x), 1-2*(x*x+y*y)], -1)], 1)

def camera_mats(K, M):  # TRAINLOG render_states.camera
    zn, zf = .01, 2000.
    P = np.zeros((4, 4)); P[0, 0] = 2*K[0, 0]/W; P[1, 1] = 2*K[1, 1]/H; P[0, 2] = (2*K[0, 2]-(W-1))/W; P[1, 2] = (2*K[1, 2]-(H-1))/H; P[2, 2] = zf/(zf-zn); P[2, 3] = -zf*zn/(zf-zn); P[3, 2] = 1.
    w = np.asarray(M, 'f8').T; full = w@P.T
    ndc2pix = np.array([[W/2, 0, 0, (W-1)/2], [0, H/2, 0, (H-1)/2], [0, 0, zf-zn, zn], [0, 0, 0, 1]]).T
    return w, full@ndc2pix

def contrib(px, py, K, M, blk=2048, wmin=1e-4):
    xyz, L, op = G['xyz'], G['L'], G['op']; w, F = camera_mats(K, M); F3 = F[:, [0, 1, 3]]
    # s2w rows: [L0 (tangent u * s0), L1 (tangent v * s1), centre (homogeneous)] -> M3 = s2w[:, [0,1,3]] @ F3
    Tu_ = np.stack([L[:, 0], L[:, 1], xyz], 1)  # N x 3 x 3 (rows 0,1 have homogeneous 0, row 2 has 1)
    Mm = np.einsum('nij,jk->nik', Tu_, F3[:3])+np.stack([np.zeros_like(F3[3]), np.zeros_like(F3[3]), F3[3]])[None]
    Tu, Tv, Tw = Mm[:, :, 0], Mm[:, :, 1], Mm[:, :, 2]
    zc = xyz@w[:3, 2]+w[3, 2]
    c = 3.; t = np.array([c*c, c*c, -1.]); d = (t*Tw*Tw).sum(1); dd = np.where(d != 0, d, 1.); f = t[None]/dd[:, None]
    pxi = (f*Tu*Tw).sum(1); pyi = (f*Tv*Tw).sum(1); hx = np.sqrt(np.maximum(pxi**2-(f*Tu*Tu).sum(1), 1e-4)); hy = np.sqrt(np.maximum(pyi**2-(f*Tv*Tv).sum(1), 1e-4))
    rad = np.ceil(np.maximum(np.maximum(hx, hy), c*0.707106)); gx, gy = (W+15)//16, (H+15)//16
    tc = lambda v, hi: np.clip(np.trunc(v), 0, hi).astype('i8')
    rx0 = tc((pxi-rad)/16, gx); rx1 = tc((pxi+rad+15)/16, gx); ry0 = tc((pyi-rad)/16, gy); ry1 = tc((pyi+rad+15)/16, gy)
    ok = (zc > .2) & (d != 0) & ((rx1-rx0)*(ry1-ry0) > 0)
    tiles = (py//16)*gx+(px//16); Q = np.zeros((gy, gx), 'i4'); Q[py//16, px//16] = 1
    S = np.zeros((gy+1, gx+1), 'i4'); S[1:, 1:] = Q.cumsum(0).cumsum(1)
    hit = S[ry1, rx1]-S[ry0, rx1]-S[ry1, rx0]+S[ry0, rx0] > 0; sub = np.flatnonzero(ok & hit)
    sub = sub[np.argsort(zc[sub], kind='stable')]
    srx0, srx1, sry0, sry1 = rx0[sub], rx1[sub], ry0[sub], ry1[sub]
    out = []
    for tile in np.unique(tiles):
        ty, tx = divmod(int(tile), gx); cand = sub[(srx0 <= tx) & (tx < srx1) & (sry0 <= ty) & (ty < sry1)]   # already in z order (stable)
        pall = np.flatnonzero(tiles == tile)
        for c0_ in range(0, len(pall), 64):   # pixel chunks (memory); each pixel is composited independently
          pi = pall[c0_:c0_+64]; X = px[pi].astype('f8'); Y = py[pi].astype('f8'); T = np.ones(len(pi)); done = np.zeros(len(pi), bool)
          for b0 in range(0, len(cand), blk):
            gi = cand[b0:b0+blk]; tu, tv, tw = Tu[gi], Tv[gi], Tw[gi]
            k = X[:, None, None]*tw[None]-tu[None]; l = Y[:, None, None]*tw[None]-tv[None]; p = np.cross(k, l)
            pz = p[..., 2]; valid = pz != 0; pzs = np.where(valid, pz, 1.); sx = p[..., 0]/pzs; sy = p[..., 1]/pzs
            rho3 = sx*sx+sy*sy; ddx = pxi[gi][None]-X[:, None]; ddy = pyi[gi][None]-Y[:, None]; rho = np.minimum(rho3, 2.*(ddx*ddx+ddy*ddy))
            dep = sx*tw[None, :, 0]+sy*tw[None, :, 1]+tw[None, :, 2]
            alpha = np.minimum(op[gi][None]*np.exp(-.5*rho), .99); skip = ~valid | (dep < .2) | (rho < 0) | (alpha < 1./255.)
            alpha = np.where(skip, 0., alpha); om = 1-alpha
            ex = np.cumprod(np.concatenate([np.ones_like(om[:, :1]), om[:, :-1]], 1), 1); Tb = T[:, None]*ex
            term = (~skip) & (Tb*om < 1e-4); first = np.where(term.any(1), term.argmax(1), om.shape[1])
            idx = np.arange(om.shape[1])[None]; inc = (~skip) & (idx < first[:, None]) & (~done[:, None])
            wgt = np.where(inc, alpha*Tb, 0.); r_, c_ = np.nonzero(wgt > wmin)
            if len(r_): out.append(np.stack([pi[r_].astype('f8'), gi[c_].astype('f8'), wgt[r_, c_], dep[r_, c_], Tb[r_, c_]], 1))
            T = np.where(done, T, T*np.where(inc, om, 1.).prod(1)); done = done | (term.any(1) & (first < om.shape[1]))
            if done.all(): break
    return np.concatenate(out) if out else np.zeros((0, 5))

def one(j):
    nm = G['names'][j]; mm = G['views'][nm]; K = np.asarray(mm['K']); M = np.asarray(mm['W2C'])
    i, px, py, z = pairs_for_view(G['X'], G['nrm'], K, M); keep = G['want'][i]; i, px, py, z = i[keep], px[keep], py[keep], z[keep]
    if not len(i): return None
    C = contrib(px.astype('i8'), py.astype('i8'), K, M); n = len(i)
    p = C[:, 0].astype('i8'); wv = C[:, 2]; dz = C[:, 3]; acc = np.bincount(p, wv, n); mean = np.where(acc > 0, np.bincount(p, wv*dz, n)/np.maximum(acc, 1e-12), np.nan)
    med = np.full(n, np.nan); m_ = C[:, 4] > .5
    if m_.any(): o = np.lexsort((C[m_, 4], p[m_])); pm = p[m_][o]; zm = dz[m_][o]; last = np.r_[pm[1:] != pm[:-1], True]; med[pm[last]] = zm[last]
    tg = np.full((n, 3), -1, 'i8'); tw_ = np.zeros((n, 3), 'f4'); td = np.full((n, 3), np.nan, 'f4')
    if len(C):
        o = np.lexsort((-wv, p)); ps = p[o]; st = np.searchsorted(ps, np.arange(n+1))
        for r in range(3):
            has = st[1:]-st[:-1] > r; ii = np.flatnonzero(has); e = o[st[ii]+r]
            tg[ii, r] = G['gid'][C[e, 1].astype('i8')]; tw_[ii, r] = wv[e]; td[ii, r] = dz[e]
    return dict(pt=i.astype('i4'), view=np.full(n, j, 'i2'), px=px, py=py, z=z.astype('f4'), acc=acc.astype('f4'), mean=mean.astype('f4'), median=med.astype('f4'),
                top_g=tg, top_w=tw_, top_dep=td, n_contrib=np.bincount(p, minlength=n).astype('i4'))

def main(stem, run, mode):
    t0 = time.monotonic(); site = stem.split('__')[0]; P = loadz(O/'points'/f'sel_{stem}.npz')
    G['X'] = P['xyz'].astype('f8'); G['nrm'] = P['normal'].astype('f8')
    G['want'] = np.ones(len(P['group']), bool) if mode == 'all' else np.isin(P['group'], [0, 2] if run == 'ft' else [0, 1])
    md = maps_of(stem, run); idx = json.loads((md/'index.json').read_text()); G['views'] = idx['views']; G['names'] = list(idx['views'])
    ply = model_of(stem, run)/'point_cloud/iteration_30000/point_cloud.ply'
    g = ply_read(ply, ['x', 'y', 'z', 'scale_0', 'scale_1', 'rot_0', 'rot_1', 'rot_2', 'rot_3', 'opacity'])
    xyz = np.c_[g['x'], g['y'], g['z']].astype('f8'); box = view_box(site); inside = ((xyz >= box[0]) & (xyz <= box[1])).all(1); gid = np.flatnonzero(inside)
    s = np.exp(np.c_[g['scale_0'], g['scale_1']].astype('f8'))[gid]; R_ = qrot(np.c_[g['rot_0'], g['rot_1'], g['rot_2'], g['rot_3']].astype('f8')[gid])
    G['L'] = np.stack([R_[:, :, 0]*s[:, :1], R_[:, :, 1]*s[:, 1:2]], 1)   # rows of RS^T: column vectors of R*S
    G['xyz'] = xyz[gid]; G['op'] = 1/(1+np.exp(-g['opacity'].astype('f8')[gid])); G['gid'] = gid; del g, xyz
    with ProcessPoolExecutor(int(os.environ.get('TP_WORKERS', 16))) as ex: res = [r for r in ex.map(one, range(len(G['names'])), chunksize=1) if r is not None]
    out = {k: np.concatenate([r[k] for r in res]) for k in res[0]}
    savez(O/'contrib'/f'{run}_{stem}_{mode}.npz', **out, ply_sha256=np.array(sha(ply)), box=box, gaussians_in_box=np.int64(len(gid)))
    rec = dict(at=now(), stem=stem, run=run, mode=mode, pairs=len(out['pt']), points=int(G['want'].sum()), gaussians_in_box=int(len(gid)), ply=str(ply),
               acc_median=float(np.nanmedian(out['acc'])), seconds=time.monotonic()-t0, scientific_verdict=None)
    dump(O/'contrib'/f'{run}_{stem}_{mode}.json', rec); print('TP4C', json.dumps(rec, ensure_ascii=False), flush=True)

if __name__ == '__main__': main(*sys.argv[1:])
