"""Work na (order 4): rendered-depth decomposition at the south-wall target pixels (GPU, fork r30 at /source).
The per-pixel 2DGS compositing of the FINALTRAIN speed renderer (rfix_speed builds/target forward.cu: compute_transmat via the inherited python
transMat path, compute_aabb cutoff 3, radius ceil(max(extent, 3*0.707106)), getRect 16x16 tiles, per-tile depth order of the centre view z (stable),
ray-splat intersection, low-pass rho2d = 2|d|^2, near 0.2, alpha = min(0.99, o exp(-rho/2)) >= 1/255, stop when T(1-alpha) < 1e-4,
median depth = depth of the last splat with T > 0.5) re-implemented in torch for the selected pixels; checked against the CUDA render at the same pixels.
  run <model> <view>   : addendum3/na/<model>__<view>.npz
  tables | figures"""
import sys, math
sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1/addendum3')
from a3_common import *
import time
NA = A3O/'na'; STEM = 'B0_b10__LoD2'
VIEWS = ['DJI_20241217094933_0013_D', 'DJI_20241217093905_0026_D', 'DJI_20241217101357_0031_D']
MODELS = ['FINALTRAIN_30000', 'record_7000', 'record_15000']
BINS = ['front', 'target', 'behind_near', 'behind_far']; CLASSES = ['front', 'same', 'none', 'behind']

def load(model):
    import torch
    sys.path.insert(0, '/source')
    from scene import GaussianModel
    g = GaussianModel(3); T = Targets(STEM)
    if model == 'FINALTRAIN_30000':
        md = model_dir(STEM, 'own'); g.load_ply(str(md/'point_cloud/iteration_30000/point_cloud.ply'))
        s = loadz(md/'target_monitor/snapshot_30000.npz', ['target_tag', 'target_index', 'xyz']); assert len(s['xyz']) == len(g._xyz)
        assert np.abs(s['xyz']-g._xyz.detach().cpu().numpy()).max() < 1e-4
        tag, ti = s['target_tag'], s['target_index']; src = str(md/'point_cloud/iteration_30000/point_cloud.ply')
    else:
        it = model.split('_')[1]; p = RUNS['tl_B0_b10_LoD2_s0']['model']/'trainlog/scene'/f'{it}.pt'; d = torch.load(p, map_location='cpu', weights_only=False)
        for a, k in [('_xyz', 'xyz'), ('_features_dc', 'f_dc'), ('_features_rest', 'f_rest'), ('_opacity', 'opacity'), ('_scaling', 'scaling'), ('_rotation', 'rotation')]:
            setattr(g, a, torch.nn.Parameter(d[k].cuda().contiguous(), requires_grad=False))
        g.active_sh_degree = int(d['active_sh_degree']); tag, ti = d['target_tag'].numpy(), d['target_index'].numpy(); src = str(p)
    south = np.asarray(wall_zone_patches(STEM, 'own')['south'], 'i8'); row = np.where(tag == 1, T.valid[np.clip(ti, 0, len(T.valid)-1)], -1)
    st = np.where(tag == 1, np.where(np.isin(row, south), 0, 1), np.where(tag == 2, 2, 3)).astype('i8')
    return g, torch.as_tensor(st, device='cuda'), south, src

def decompose(g, st, cam, px, py, tdepth, blk=4096):
    import torch
    W, H = cam.image_width, cam.image_height; xyz = g.get_xyz; op = g.get_opacity[:, 0]
    s2w = g.get_covariance(1.0); near, far = cam.znear, cam.zfar
    ndc2pix = torch.tensor([[W/2, 0, 0, (W-1)/2], [0, H/2, 0, (H-1)/2], [0, 0, far-near, near], [0, 0, 0, 1]]).float().cuda().T
    M = s2w[:, [0, 1, 3]] @ (cam.full_proj_transform @ ndc2pix)[:, [0, 1, 3]]; Tu, Tv, Tw = M[:, :, 0], M[:, :, 1], M[:, :, 2]
    zc = (torch.cat([xyz, torch.ones_like(xyz[:, :1])], 1) @ cam.world_view_transform)[:, 2]
    c = 3.; t = torch.tensor([c*c, c*c, -1.], device='cuda'); d = (t*Tw*Tw).sum(1); f = t[None]/d[:, None]
    pxi = (f*Tu*Tw).sum(1); pyi = (f*Tv*Tw).sum(1); hx = torch.sqrt(torch.clamp_min(pxi**2-(f*Tu*Tu).sum(1), 1e-4)); hy = torch.sqrt(torch.clamp_min(pyi**2-(f*Tv*Tv).sum(1), 1e-4))
    rad = torch.ceil(torch.maximum(torch.maximum(hx, hy), torch.full_like(hx, c*0.707106)))
    gx, gy = (W+15)//16, (H+15)//16
    def trunc_clamp(v, hi): return torch.clamp(torch.trunc(v), min=0, max=hi).long()
    rx0 = trunc_clamp((pxi-rad)/16, gx); rx1 = trunc_clamp((pxi+rad+15)/16, gx); ry0 = trunc_clamp((pyi-rad)/16, gy); ry1 = trunc_clamp((pyi+rad+15)/16, gy)
    ok = (zc > .2) & (d != 0) & ((rx1-rx0)*(ry1-ry0) > 0)
    n = len(px); A = torch.zeros(n, device='cuda'); Dsum = torch.zeros(n, device='cuda'); med = torch.zeros(n, device='cuda'); ncon = torch.zeros(n, device='cuda', dtype=torch.long)
    Wb = torch.zeros((n, 4, 4), device='cuda'); pxt = torch.as_tensor(px, device='cuda').long(); pyt = torch.as_tensor(py, device='cuda').long(); td = torch.as_tensor(tdepth, device='cuda').float()
    tiles = (pyt//16)*gx+(pxt//16)
    for tile in torch.unique(tiles).tolist():
        ty, tx = divmod(tile, gx); cand = torch.nonzero(ok & (rx0 <= tx) & (tx < rx1) & (ry0 <= ty) & (ty < ry1)).squeeze(1)
        cand = cand[torch.sort(zc[cand], stable=True).indices]; pi = torch.nonzero(tiles == tile).squeeze(1)
        X = pxt[pi].float(); Y = pyt[pi].float(); T = torch.ones(len(pi), device='cuda'); done = torch.zeros(len(pi), device='cuda', dtype=torch.bool)
        for b0 in range(0, len(cand), blk):
            gi = cand[b0:b0+blk]; tu, tv, tw = Tu[gi], Tv[gi], Tw[gi]
            k = X[:, None, None]*tw[None]-tu[None]; l = Y[:, None, None]*tw[None]-tv[None]; p = torch.cross(k, l, dim=-1)
            pz = p[..., 2]; valid = pz != 0; pzs = torch.where(valid, pz, torch.ones_like(pz)); sx = p[..., 0]/pzs; sy = p[..., 1]/pzs
            rho3 = sx*sx+sy*sy; ddx = pxi[gi][None]-X[:, None]; ddy = pyi[gi][None]-Y[:, None]; rho2 = 2.*(ddx*ddx+ddy*ddy); rho = torch.minimum(rho3, rho2)
            dep = sx*tw[None, :, 0]+sy*tw[None, :, 1]+tw[None, :, 2]
            alpha = torch.clamp_max(op[gi][None]*torch.exp(-.5*rho), .99); skip = ~valid | (dep < .2) | (rho < 0) | (alpha < 1./255.)
            alpha = torch.where(skip, torch.zeros_like(alpha), alpha)
            om = 1-alpha; ex = torch.cumprod(torch.cat([torch.ones_like(om[:, :1]), om[:, :-1]], 1), 1); Tb = T[:, None]*ex
            term = (~skip) & (Tb*om < 1e-4); first = torch.where(term.any(1), term.float().argmax(1), torch.full((len(pi),), om.shape[1], device='cuda', dtype=torch.long))
            idx = torch.arange(om.shape[1], device='cuda')[None]; inc = (~skip) & (idx < first[:, None]) & (~done[:, None])
            w = torch.where(inc, alpha*Tb, torch.zeros_like(alpha)); A[pi] += w.sum(1); Dsum[pi] += (w*dep).sum(1); ncon[pi] += inc.sum(1)
            mm = inc & (Tb > .5); last = torch.where(mm.any(1), (mm.long()*idx).max(1).values, torch.full((len(pi),), -1, device='cuda', dtype=torch.long))
            hasm = last >= 0; med[pi[hasm]] = dep[hasm, last[hasm]]
            rel = dep-td[pi][:, None]; bn = torch.where(rel < -1, 0, torch.where(rel <= 1, 1, torch.where(rel <= 5, 2, 3))); sg = st[gi][None].expand_as(bn)
            Wb[pi] += torch.zeros((len(pi), 16), device='cuda').scatter_add_(1, bn*4+sg, w).view(-1, 4, 4)
            T = torch.where(done, T, T*torch.where(inc, om, torch.ones_like(om)).prod(1)); done = done | (term & (idx >= 0)).any(1) & (first < om.shape[1])
            if bool(done.all()): break
    return dict(acc=A.cpu().numpy(), depth_mean=(Dsum/torch.clamp_min(A, 1e-12)).cpu().numpy(), depth_median=med.cpu().numpy(), contributors=ncon.cpu().numpy(), w=Wb.cpu().numpy())

def run(model, view):
    import torch
    sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1'); sys.path.append('/repo/scripts/phd/main_finaltrain_v1')
    from te_render import camera
    from gaussian_renderer import render
    from types import SimpleNamespace
    from renderer import install
    install(); NA.mkdir(parents=True, exist_ok=True); t0 = time.monotonic()
    with torch.no_grad():
        g, st, south, src = load(model); md = maps_dir(STEM, 'own'); mi = json.loads((md/'index.json').read_text())['views'][view]
        with np.load(md/mi['file']) as z: own = z['owner']; dep = z['depth']
        mvs = np.load(Path('/s0/fork_inputs/s61/B0_b10/maps/mvs')/f'{view}.npy'); H, W = own.shape
        sel = np.isin(own, south); py, px = np.nonzero(sel); td = dep[sel].astype('f8'); m = mvs[sel].astype('f8'); have = np.isfinite(m) & (m > 0)
        cls = np.where(~have, 2, np.where(m < td-1, 0, np.where(m > td+1, 3, 1))).astype('i1')
        cam = camera(W, H, np.asarray(mi['K']), np.asarray(mi['W2C']), view)
        pipe = SimpleNamespace(convert_SHs_python=False, compute_cov3D_python=False, depth_ratio=0., debug=False); pkg = render(cam, g, pipe, torch.zeros(3, device='cuda'))
        ca = pkg['rend_alpha'].squeeze()[py, px].cpu().numpy(); cd = pkg['surf_depth'].squeeze()[py, px].cpu().numpy()
        pipe2 = SimpleNamespace(convert_SHs_python=False, compute_cov3D_python=True, depth_ratio=0., debug=False); pk2 = render(cam, g, pipe2, torch.zeros(3, device='cuda'))
        ca2 = pk2['rend_alpha'].squeeze()[py, px].cpu().numpy()
        r = decompose(g, st, cam, px, py, td)
    savez(NA/f'{model}__{view}.npz', px=px.astype('i2'), py=py.astype('i2'), cls=cls, target=td.astype('f4'), mvs=np.where(have, m, np.nan).astype('f4'), owner=own[sel].astype('i4'),
          acc=r['acc'].astype('f4'), depth_mean=r['depth_mean'].astype('f4'), depth_median=r['depth_median'].astype('f4'), contributors=r['contributors'].astype('i4'), w=r['w'].astype('f4'),
          cuda_alpha=ca.astype('f4'), cuda_depth=cd.astype('f4'), cuda_alpha_python_transmat=ca2.astype('f4'), W=W, H=H)
    da = np.abs(r['acc']-ca); dd = np.abs(r['depth_mean']-cd); fin = np.isfinite(dd) & (ca > .01)
    rec = dict(at=now(), model=model, view=view, source=src, pixels=int(sel.sum()), classes={k: int((cls == i).sum()) for i, k in enumerate(CLASSES)},
               check=dict(alpha_abs_max=float(da.max()), alpha_abs_p99=float(np.quantile(da, .99)), depth_abs_p99_m=float(np.quantile(dd[fin], .99)) if fin.any() else None,
                          depth_abs_max_m=float(dd[fin].max()) if fin.any() else None, python_vs_cuda_transmat_alpha_abs_max=float(np.abs(ca2-ca).max())),
               seconds=time.monotonic()-t0, scientific_verdict=None)
    dump(NA/f'{model}__{view}.json', rec); print('NA', json.dumps(rec), flush=True)

if __name__ == '__main__':
    a = sys.argv[1:]
    if a[0] == 'run': run(a[1], a[2])
    else: raise SystemExit(a)
