"""Work da (order 4): Gaussians exist but no surface; where Gaussians in front of walls and in the air come from; which splats make the non-existent surfaces;
whether the edge bands are occluded in the photos. GPU (/source = r31) except 'front' and 'edge' (CPU).
  wall <model>        : B0 visible wall (0-5 / 5-10 m) target pixels in every training view: weight by depth bin x kind, rendered depth - target, pixel classes;
                        per GT wall point the share of seeing views whose rendered depth is within tau; wall-bound Gaussians -> addendum4/da/wall_<model>.npz
  front               : Gaussians 0.2-3 m in front of the visible wall (record 30000), within 0.5 m of the edge floater (B173 x ALS 30000) and 0.2-3 m above
                        the R1 floor band (record 30000): kind, birth, ancestry -> tables/da_front_*.csv
  wrong <case>        : annex (B0 x ALS ba-3 30000) / south (B0 x LoD2 record 30000): 2000 wrong mesh points, the views that made them, splats by depth bin and kind
  edge                : B0 edge bands: per view median (target - image depth) at the place target pixels; photos of 2 large / 2 small
  tables"""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1/addendum4')
from a4_common import *
import time
DA = A4O/'da'
TLCASE = TLC/'runs/B0_b10/tl_B0_b10_LoD2_s0/attempt1/model'
BA2B = A3O/'runs/B0_b10/ba2b_B0_LoD2_noreset_nocheck/attempt1/model'
BA3 = A3O/'runs/B0_b10/ba3_B0_ALS_record/attempt1/model'
WALL_MODELS = {'record_7000': (TLCASE, '7000'), 'record_15000': (TLCASE, '15000'), 'record_30000': (TLCASE, '30000'), 'ba2b_15000': (BA2B, '15000'), 'ba2b_30000': (BA2B, '30000')}
KINDS = ['같은 자리 목표', '다른 목표', '풀린 것', '묶이지 않은 것']

def gpu_setup():
    sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1'); sys.path.append('/repo/scripts/phd/main_finaltrain_v1')
    from te_render import camera
    from renderer import install
    install(); return camera

def load_pt(model, name):
    import torch
    return torch.load(model/'trainlog/scene'/f'{name}.pt', map_location='cpu', weights_only=False)

def gmodel(d):
    import torch
    sys.path.insert(0, '/source')
    from scene import GaussianModel
    g = GaussianModel(3)
    for a, k in [('_xyz', 'xyz'), ('_features_dc', 'f_dc'), ('_features_rest', 'f_rest'), ('_opacity', 'opacity'), ('_scaling', 'scaling'), ('_rotation', 'rotation')]:
        setattr(g, a, torch.nn.Parameter(d[k].cuda().contiguous(), requires_grad=False))
    g.active_sh_degree = int(d['active_sh_degree']); return g

def contrib(g, cam, px, py, blk=4096, wmin=1e-4):
    """flat per-pixel splat contributions (addendum3 work na compositing): pixel index, splat index, weight alpha*T, ray-splat depth, T before the splat."""
    import torch
    W, H = cam.image_width, cam.image_height; xyz = g.get_xyz; op = g.get_opacity[:, 0]; s2w = g.get_covariance(1.0); near, far = cam.znear, cam.zfar
    ndc2pix = torch.tensor([[W/2, 0, 0, (W-1)/2], [0, H/2, 0, (H-1)/2], [0, 0, far-near, near], [0, 0, 0, 1]]).float().cuda().T
    M = s2w[:, [0, 1, 3]] @ (cam.full_proj_transform @ ndc2pix)[:, [0, 1, 3]]; Tu, Tv, Tw = M[:, :, 0], M[:, :, 1], M[:, :, 2]
    zc = (torch.cat([xyz, torch.ones_like(xyz[:, :1])], 1) @ cam.world_view_transform)[:, 2]
    c = 3.; t = torch.tensor([c*c, c*c, -1.], device='cuda'); d = (t*Tw*Tw).sum(1); f = t[None]/d[:, None]
    pxi = (f*Tu*Tw).sum(1); pyi = (f*Tv*Tw).sum(1); hx = torch.sqrt(torch.clamp_min(pxi**2-(f*Tu*Tu).sum(1), 1e-4)); hy = torch.sqrt(torch.clamp_min(pyi**2-(f*Tv*Tv).sum(1), 1e-4))
    rad = torch.ceil(torch.maximum(torch.maximum(hx, hy), torch.full_like(hx, c*0.707106))); gx, gy = (W+15)//16, (H+15)//16
    def tc(v, hi): return torch.clamp(torch.trunc(v), min=0, max=hi).long()
    rx0 = tc((pxi-rad)/16, gx); rx1 = tc((pxi+rad+15)/16, gx); ry0 = tc((pyi-rad)/16, gy); ry1 = tc((pyi+rad+15)/16, gy)
    ok = (zc > .2) & (d != 0) & ((rx1-rx0)*(ry1-ry0) > 0)
    pxt = torch.as_tensor(px, device='cuda').long(); pyt = torch.as_tensor(py, device='cuda').long(); tiles = (pyt//16)*gx+(pxt//16); out = []
    for tile in torch.unique(tiles).tolist():
        ty, tx = divmod(tile, gx); cand = torch.nonzero(ok & (rx0 <= tx) & (tx < rx1) & (ry0 <= ty) & (ty < ry1)).squeeze(1)
        cand = cand[torch.sort(zc[cand], stable=True).indices]; pi = torch.nonzero(tiles == tile).squeeze(1)
        X = pxt[pi].float(); Y = pyt[pi].float(); T = torch.ones(len(pi), device='cuda'); done = torch.zeros(len(pi), device='cuda', dtype=torch.bool)
        for b0 in range(0, len(cand), blk):
            gi = cand[b0:b0+blk]; tu, tv, tw = Tu[gi], Tv[gi], Tw[gi]
            k = X[:, None, None]*tw[None]-tu[None]; l = Y[:, None, None]*tw[None]-tv[None]; p = torch.cross(k, l, dim=-1)
            pz = p[..., 2]; valid = pz != 0; pzs = torch.where(valid, pz, torch.ones_like(pz)); sx = p[..., 0]/pzs; sy = p[..., 1]/pzs
            rho3 = sx*sx+sy*sy; ddx = pxi[gi][None]-X[:, None]; ddy = pyi[gi][None]-Y[:, None]; rho = torch.minimum(rho3, 2.*(ddx*ddx+ddy*ddy))
            dep = sx*tw[None, :, 0]+sy*tw[None, :, 1]+tw[None, :, 2]
            alpha = torch.clamp_max(op[gi][None]*torch.exp(-.5*rho), .99); skip = ~valid | (dep < .2) | (rho < 0) | (alpha < 1./255.)
            alpha = torch.where(skip, torch.zeros_like(alpha), alpha); om = 1-alpha
            ex = torch.cumprod(torch.cat([torch.ones_like(om[:, :1]), om[:, :-1]], 1), 1); Tb = T[:, None]*ex
            term = (~skip) & (Tb*om < 1e-4); first = torch.where(term.any(1), term.float().argmax(1), torch.full((len(pi),), om.shape[1], device='cuda', dtype=torch.long))
            idx = torch.arange(om.shape[1], device='cuda')[None]; inc = (~skip) & (idx < first[:, None]) & (~done[:, None])
            w = torch.where(inc, alpha*Tb, torch.zeros_like(alpha)); r_, c_ = torch.nonzero(w > wmin, as_tuple=True)
            if len(r_): out.append(torch.stack([pi[r_].double(), gi[c_].double(), w[r_, c_].double(), dep[r_, c_].double(), Tb[r_, c_].double()], 1).cpu())
            T = torch.where(done, T, T*torch.where(inc, om, torch.ones_like(om)).prod(1)); done = done | (term.any(1) & (first < om.shape[1]))
            if bool(done.all()): break
    if not out: return np.zeros((0, 5))
    return torch.cat(out).numpy()

def per_pixel(C, n):
    """accumulated opacity, weighted-mean depth (2DGS depth_ratio 0), median depth (last splat with T > 0.5) per pixel from flat contributions."""
    p = C[:, 0].astype('i8'); w = C[:, 2]; z = C[:, 3]; acc = np.bincount(p, w, n); zs = np.bincount(p, w*z, n)
    mean = np.where(acc > 0, zs/np.maximum(acc, 1e-12), np.nan); med_ = np.full(n, np.nan); m = C[:, 4] > .5
    if m.any(): o = np.lexsort((C[m, 4], p[m])); pm = p[m][o]; zm = z[m][o]; last = np.r_[pm[1:] != pm[:-1], True]; med_[pm[last]] = zm[last]   # smallest T above 0.5 = last in order
    return acc, mean, med_

def kind_of(S, rows, place_rows):
    tag = S['target_tag'].numpy()[rows]; ti = S['target_index'].numpy()[rows]
    return np.where(tag == 1, np.where(np.isin(ti, place_rows), 0, 1), np.where(tag == 2, 2, 3))

def views_of(stem):
    md = maps_dir(stem, 'own'); return md, json.loads((md/'index.json').read_text())['views']

def wall(model_name):
    import torch
    camera = gpu_setup(); t0 = time.monotonic(); DA.mkdir(parents=True, exist_ok=True); stem = 'B0_b10__LoD2'; model, st = WALL_MODELS[model_name]; S = load_pt(model, st)
    places = {pl: place_points_cached(pl) for pl in ['visible_low', 'visible_high']}; md, mi = views_of(stem); site = 'B0_b10'
    praw = {pl: np.unique(P['patch_row'][P['patch_row'] >= 0]) for pl, P in places.items()}; pv = {pl: np.unique(P['v'][P['v'] >= 0]) for pl, P in places.items()}
    out = {pl: dict(bins=np.zeros((3, 4, 4)), pixels=np.zeros(3, 'i8'), dd=[], cls=[]) for pl in places}   # class x bin x kind
    taus = {pl: tau_of_points(P) for pl, P in places.items()}
    pts_ok = {pl: np.zeros(len(P['xyz'])) for pl, P in places.items()}; pts_n = {pl: np.zeros(len(P['xyz'])) for pl, P in places.items()}
    with torch.no_grad():
        g = gmodel(S); from gaussian_renderer import render; from types import SimpleNamespace
        pipe = SimpleNamespace(convert_SHs_python=False, compute_cov3D_python=False, depth_ratio=0., debug=False)
        for nm, m in sorted(mi.items()):
            with np.load(md/m['file']) as z: own = z['owner']; dep = z['depth']
            H, W = own.shape; K = np.asarray(m['K']); M = np.asarray(m['W2C']); cam = camera(W, H, K, M, nm); rd = None
            mvs = np.load(Path('/s0/fork_inputs/s61')/site/'maps/mvs'/f'{nm}.npy')
            for pl, P in places.items():
                X = P['xyz']; Xc = X@M[:3, :3].T+M[:3, 3]; zc = Xc[:, 2]; okz = zc > .2
                u = np.floor(K[0, 0]*Xc[:, 0]/np.where(okz, zc, 1)+K[0, 2]).astype('i8'); v = np.floor(K[1, 1]*Xc[:, 1]/np.where(okz, zc, 1)+K[1, 2]).astype('i8')
                inside = okz & (u >= 0) & (u < W) & (v >= 0) & (v < H); sel = np.isin(own, praw[pl])
                if not sel.any() and not inside.any(): continue
                if rd is None: rd = render(cam, g, pipe, torch.zeros(3, device='cuda'))['surf_depth'].squeeze().cpu().numpy()
                if inside.any():   # surface-extraction input: rendered depth within tau of the GT point depth, seeing views = point in the image and owner of the pixel is a place patch
                    seen = inside.copy(); seen[inside] = np.isin(own[v[inside], u[inside]], praw[pl])
                    ii = np.flatnonzero(seen); pts_n[pl][ii] += 1
                    pts_ok[pl][ii] += np.abs(rd[v[ii], u[ii]]-zc[ii]) <= taus[pl][ii]
                if not sel.any(): continue
                py, px = np.nonzero(sel); td = dep[sel].astype('f8'); mv = mvs[sel].astype('f8'); have = np.isfinite(mv) & (mv > 0)
                cls = np.where(~have, 2, np.where(mv < td-1, 0, 1))   # 0 앞에 다른 것, 1 같음(뒤 포함), 2 영상 깊이 없음
                C = contrib(g, cam, px, py); n = len(px); acc, mean, _ = per_pixel(C, n)
                rel = C[:, 3]-td[C[:, 0].astype('i8')]; b = np.where(rel < -1, 0, np.where(rel <= 1, 1, np.where(rel <= 5, 2, 3)))
                kd = kind_of(S, C[:, 1].astype('i8'), pv[pl]); cl = cls[C[:, 0].astype('i8')]
                np.add.at(out[pl]['bins'], (cl, b, kd), C[:, 2]); out[pl]['pixels'] += np.bincount(cls, minlength=3)
                out[pl]['dd'].append((mean-td).astype('f4')); out[pl]['cls'].append(cls.astype('i1'))
    sv = {}
    for pl in places:
        sv[f'{pl}__bins'] = out[pl]['bins']; sv[f'{pl}__pixels'] = out[pl]['pixels']; sv[f'{pl}__dd'] = np.concatenate(out[pl]['dd']) if out[pl]['dd'] else np.zeros(0)
        sv[f'{pl}__cls'] = np.concatenate(out[pl]['cls']) if out[pl]['cls'] else np.zeros(0); sv[f'{pl}__pts_ok'] = pts_ok[pl]; sv[f'{pl}__pts_n'] = pts_n[pl]
        # wall-bound Gaussians
        tag = S['target_tag'].numpy(); ti = S['target_index'].numpy(); b = (tag == 1) & np.isin(ti, pv[pl]); X = S['xyz'].double().numpy()[b]
        from utils.general_utils import build_rotation
        nrm = build_rotation(S['rotation'][b].cuda()).cpu().numpy()[:, :, 2] if b.any() else np.zeros((0, 3))
        T = places[pl]['T']; on = np.asarray(places[pl]['u'], 'f8'); h = ((X-T.anchor[ti[b]])*on).sum(1) if b.any() else np.zeros(0)
        sv[f'{pl}__bound_opacity'] = 1/(1+np.exp(-S['opacity'][b, 0].numpy())); sv[f'{pl}__bound_size'] = np.exp(S['scaling'][b].numpy()).max(1); sv[f'{pl}__bound_angle'] = np.degrees(np.arccos(np.clip(np.abs(nrm@on), 0, 1))); sv[f'{pl}__bound_h'] = h
    savez(DA/f'wall_{model_name}.npz', **sv); print('WALL', model_name, round(time.monotonic()-t0), flush=True)

def tau_of_points(P):
    if 'tau' in P: return np.asarray(P['tau'], 'f8')
    ref = a11_ref(P['stem']); lut = dict(zip(ref['point_id'].tolist(), ref['tau_m'].tolist())); return np.array([lut.get(int(i), np.nan) for i in P['point_id']])

# ---------------- front / ancestry (CPU) ----------------
FT_ = PH/'main_finaltrain_v1/PHD-MAIN-FINALTRAIN-v1'
def ancestry(S, rows, stem, ref_xyz):
    """kind, born_at, born_how, seed origin (prior / background), seed patch anchor distance to the place, released iteration."""
    sd = loadz(FT_/'stage1'/stem/'seeds.npz', ['patch', 'origin']); t = loadz(targets_of(stem, 'own'), ['target'])
    ii = S['init_id'].numpy()[rows].astype('i8'); sp = sd['patch'][ii]; so = sd['origin'][ii]
    anc = np.where((sp >= 0)[:, None], t['target'][np.clip(sp, 0, None)], np.nan); dd = np.full(len(rows), np.nan); ok = sp >= 0
    if ok.any(): dd[ok] = cKDTree(ref_xyz).query(anc[ok])[0]
    return dict(tag=S['target_tag'].numpy()[rows], born_at=S['born_at'].numpy()[rows], born_how=S['born_how'].numpy()[rows], seed_origin=so, seed_patch_dist_m=dd,
                released_at=S['target_released_at'].numpy()[rows], opacity=1/(1+np.exp(-S['opacity'][rows, 0].numpy())), size=np.exp(S['scaling'][rows].numpy()).max(1))

def summarize_front(name, A, ko):
    n = len(A['tag']); r = dict(set=name, set_ko=ko, gaussians=n)
    if not n: return r
    r.update(bound=int((A['tag'] == 1).sum()), released=int((A['tag'] == 2).sum()), unbound=int((A['tag'] == 0).sum()),
             seed_prior_pct=pct(A['seed_origin'] == 1), seed_background_pct=pct(A['seed_origin'] == 0), child_pct=pct(A['born_how'] >= 2),
             born_at_median=med(A['born_at']), born_after_3000_pct=pct(A['born_at'] > 3000), born_after_15000_pct=pct(A['born_at'] > 15000),
             released_at_median=med(A['released_at'][A['released_at'] >= 0]), released_lineage_pct=pct(A['released_at'] >= 0),
             prior_seed_patch_dist_m_median=med(A['seed_patch_dist_m'][A['seed_origin'] == 1]), opacity_median=med(A['opacity']), opacity_sum=float(A['opacity'].sum()), size_median_m=med(A['size']))
    return r

def front():
    import torch
    sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1/addendum3'); from a3_ga import match
    rows = []; save = {}
    S = load_pt(TLCASE, '30000')
    for pl in ['visible_low', 'visible_high', 'visible_side']:
        P = place_points_cached(pl); X = S['xyz'].double().numpy(); lo = P['xyz'].min(0)-3.6; hi = P['xyz'].max(0)+3.6; cand = np.flatnonzero(np.all((X >= lo) & (X <= hi), 1))
        j, sgn = match(P, X[cand]); m = (j >= 0) & (sgn > .2) & (sgn <= 3.); g = cand[m]; A = ancestry(S, g, 'B0_b10__LoD2', P['xyz']); A['s'] = sgn[m]
        rows.append(summarize_front(f'front_{pl}', A, f'{PLACE_KO[pl]} 앞 0.2~3 m (기록 판 30,000)')); save[pl] = A
    S = load_pt(RUNS4['tl_B173nb_b10_ALS_s0']['model'], '30000'); X = S['xyz'].double().numpy()
    for pl in ['floater', 'floater_control']:
        C = floater_centres(pl); lo = C.min(0)-.6; hi = C.max(0)+.6; k = np.flatnonzero(np.all((X >= lo) & (X <= hi), 1)); d, _ = cKDTree(C).query(X[k]); g = k[d <= .5]
        A = ancestry(S, g, 'B173nb_b10__ALS', C); rows.append(summarize_front(pl, A, PLACE_KO[pl]+' 0.5 m 안 (TRAINLOG 30,000)')); save[pl] = A
    S = load_pt(RUNS4['tl_R1_ALS_own']['model'], '30000'); X = S['xyz'].double().numpy()
    for pl in ['floor_band', 'floor_control']:
        P = place_points_cached(pl) if pl == 'floor_band' else place_points(pl); lo = P['xyz'].min(0)-3.6; hi = P['xyz'].max(0)+3.6; cand = np.flatnonzero(np.all((X >= lo) & (X <= hi), 1))
        j, sgn = match(P, X[cand]); m = (j >= 0) & (sgn > .2) & (sgn <= 3.); g = cand[m]; A = ancestry(S, g, 'R1rep_b10__ALS', P['xyz']); A['s'] = sgn[m]
        rows.append(summarize_front(f'above_{pl}', A, f'{PLACE_KO[pl]} 위 0.2~3 m (기록 판 30,000)')); save[pl] = A
    DA.mkdir(parents=True, exist_ok=True); np.savez_compressed(DA/'front.npz', **{f'{k}__{f}': v for k, A in save.items() for f, v in A.items()}); dtable('da_front_ancestry', rows); print('FRONT', rows, flush=True)

# ---------------- wrong surfaces (GPU) ----------------
def wrong(case):
    import torch
    camera = gpu_setup(); t0 = time.monotonic(); rng = np.random.default_rng(0)
    if case == 'annex':
        stem, model, st, mesh = 'B0_b10__ALS', BA3, '30000', A3O/'gtj/meshes/B0_b10__ALS__ba3_30000/final.ply'
    else:
        stem, model, st, mesh = 'B0_b10__LoD2', TLCASE, '30000', TLC/'gtj/meshes/B0_b10__LoD2__tl_30000/final.ply'
    m = o3d.io.read_triangle_mesh(str(mesh)); V = np.asarray(m.vertices, 'f8'); del m
    G = loadz(GT/'reference/B0_b10/dense.npz', ['xyz', 'wall']); TG = cKDTree(G['xyz'].astype('f8'))
    if case == 'annex':
        b = ANNEX; inb = (V[:, 0] >= b['x'][0]) & (V[:, 0] <= b['x'][1]) & (V[:, 1] >= b['y'][0]) & (V[:, 1] <= b['y'][1]) & (V[:, 2] >= b['z'][0]) & (V[:, 2] <= b['z'][1])
        ii = np.flatnonzero(inb); dg, jg = TG.query(V[ii]); wrongm = ii[dg > 1.]; right = ii[(dg <= .2) & ~G['wall'][jg].astype(bool)]
        sets = {'wrong': wrongm, 'right_roof': right}
    else:
        sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1/addendum1'); import a1_common as A1
        a, d, zone = A1.wall_coords(V, 'south')   # zone includes the addendum1 offset range (the addendum3 'behind > 0.64 m share' definition)
        sets = {'wrong': np.flatnonzero(zone & (d < -.64))}
    S = load_pt(model, st); md, mi = views_of(stem); names = sorted(mi); res = {}
    tag = S['target_tag'].numpy(); gx = S['xyz'].double().numpy(); gsize = np.exp(S['scaling'].numpy()).max(1)
    dgc, jgc = TG.query(gx, distance_upper_bound=50.); gwall = np.where(np.isfinite(dgc), G['wall'][np.clip(jgc, 0, len(G['wall'])-1)], False)
    zg = np.quantile(G['xyz'][:, 2], .01)
    what = np.where(~(dgc <= 1.), 3, np.where(gwall, 1, np.where(gx[:, 2] < zg+1.5, 2, 0)))   # 0 지붕, 1 벽, 2 바닥, 3 참값 1 m 밖
    with torch.no_grad():
        g = gmodel(S); from gaussian_renderer import render; from types import SimpleNamespace
        pipe = SimpleNamespace(convert_SHs_python=False, compute_cov3D_python=False, depth_ratio=0., debug=False); rdc = {}
        for sname, idx in sets.items():
            pick = np.sort(rng.choice(idx, min(2000, len(idx)), replace=False)) if len(idx) else idx; X = V[pick]; recs = []
            for j, nm in enumerate(names):
                mm = mi[nm]; K = np.asarray(mm['K']); M = np.asarray(mm['W2C']); Xc = X@M[:3, :3].T+M[:3, 3]; zc = Xc[:, 2]; okz = zc > .2
                u = np.floor(K[0, 0]*Xc[:, 0]/np.where(okz, zc, 1)+K[0, 2]).astype('i8'); v = np.floor(K[1, 1]*Xc[:, 1]/np.where(okz, zc, 1)+K[1, 2]).astype('i8')
                W, H = 1024, 741; ins = okz & (u >= 0) & (u < W) & (v >= 0) & (v < H)
                if not ins.any(): continue
                cam = camera(W, H, K, M, nm); rd = render(cam, g, pipe, torch.zeros(3, device='cuda'))['surf_depth'].squeeze().cpu().numpy()
                q = np.flatnonzero(ins); dz = np.abs(rd[v[q], u[q]]-zc[q]); q = q[dz <= .1]
                for k_ in q: recs.append((k_, j, abs(rd[v[k_], u[k_]]-zc[k_]), u[k_], v[k_], zc[k_]))
            recs = np.array(recs) if recs else np.zeros((0, 6))
            # up to three views per point: smallest |rendered depth - point depth|
            keep = []
            for k_ in np.unique(recs[:, 0]).astype(int) if len(recs) else []:
                r = recs[recs[:, 0] == k_]; keep.extend(r[np.argsort(r[:, 2])[:3]].tolist())
            keep = np.array(keep) if keep else np.zeros((0, 6)); out = dict(point=keep[:, 0].astype('i8'), view=keep[:, 1].astype('i8'), zpt=keep[:, 5])
            W_ = np.zeros((len(keep), 3, 4, 4)); acc = np.zeros(len(keep)); meanz = np.zeros(len(keep)); medz = np.zeros(len(keep)); szw = np.zeros((len(keep), 3))
            for j in np.unique(out['view']) if len(keep) else []:
                sel = np.flatnonzero(out['view'] == j); nm = names[j]; mm = mi[nm]; cam = camera(1024, 741, np.asarray(mm['K']), np.asarray(mm['W2C']), nm)
                C = contrib(g, cam, keep[sel, 3].astype('i8'), keep[sel, 4].astype('i8')); a_, me, md_ = per_pixel(C, len(sel)); acc[sel] = a_; meanz[sel] = me; medz[sel] = md_
                p = C[:, 0].astype('i8'); rel = C[:, 3]-keep[sel, 5][p]; b = np.where(rel < -.5, 0, np.where(rel <= .5, 1, 2)); gi = C[:, 1].astype('i8')
                kd = np.where(tag[gi] == 1, 1, np.where(tag[gi] == 2, 2, 3)); kd[(tag[gi] == 1)] = 1
                np.add.at(W_, (sel[p], b, kd, what[gi]), C[:, 2])
                for bb in range(3):
                    q = b == bb; np.add.at(szw, (sel[p[q]], bb), C[q, 2]*gsize[gi[q]])
            out.update(w=W_, acc=acc, mean_depth=meanz, median_depth=medz, size_w=szw); res[sname] = out
    savez(DA/f'wrong_{case}.npz', **{f'{k}__{f}': v for k, o in res.items() for f, v in o.items()}, what_names=np.array(['지붕', '벽', '바닥', '참값 1 m 밖']))
    rows = []
    for sname, o in res.items():
        n = len(o['point']); r = dict(case=case, set=sname, points_sampled=min(2000, len(sets[sname])), points_total=len(sets[sname]), pixels=n, points_with_view=len(np.unique(o['point'])))
        if n:
            tw = o['w'].sum((2, 3)); tot = tw.sum(1)
            for bi, bn in enumerate(['앞', '틀린 면 ±0.5 m', '뒤']): r[f'{bn}_weight_mean'] = float(tw[:, bi].mean())
            r['at_surface_weight_lt_05_pct'] = pct(tw[:, 1] < .5)
            for bi, bn in enumerate(['앞', '틀린 면 ±0.5 m', '뒤']):
                ww = o['w'][:, bi].sum((0, 1))
                for wi, wn in enumerate(['지붕', '벽', '바닥', '참값 1 m 밖']): r[f'{bn}_{wn}_share_pct'] = 100*float(ww[wi]/max(ww.sum(), 1e-12))
                kk = o['w'][:, bi].sum((0, 2))
                for ki, kn in enumerate(['-', '묶인 것', '풀린 것', '묶이지 않은 것']):
                    if ki: r[f'{bn}_{kn}_share_pct'] = 100*float(kk[ki]/max(kk.sum(), 1e-12))
                r[f'{bn}_size_weighted_m'] = float(o['size_w'][:, bi].sum()/max(tw[:, bi].sum(), 1e-12))
            if case == 'south':
                kept = np.abs(o['median_depth']-o['zpt']) <= .1; r['median_depth_kept_pixel_pct'] = pct(kept)
                for lab, mk in [('중앙 깊이로도 남는 화소', kept), ('중앙 깊이로 없어지는 화소', ~kept)]:
                    tw2 = o['w'][mk].sum((2, 3))
                    for bi, bn in enumerate(['앞', '틀린 면', '뒤']): r[f'{lab}_{bn}_weight_mean'] = float(tw2[:, bi].mean()) if mk.any() else None
            if sname == 'right_roof':
                r['contributors_at_surface_note'] = 'weights above'
        rows.append(r)
    dtable(f'da_wrong_{case}', rows); print('WRONG', case, rows, round(time.monotonic()-t0), flush=True)

# ---------------- edge bands (CPU) ----------------
def edge():
    from PIL import Image, ImageDraw
    plt = korean_plt(); stem = 'B0_b10__LoD2'; md, mi = views_of(stem); rows = []; figs = {}
    for pl in ['edge_back', 'edge_annex']:
        P = place_points_cached(pl); pr = np.unique(P['patch_row'][P['patch_row'] >= 0]); per = []
        for nm, m in sorted(mi.items()):
            with np.load(md/m['file']) as z: own = z['owner']; dep = z['depth']
            sel = np.isin(own, pr)
            if sel.sum() < 20: continue
            mv = np.load(Path('/s0/fork_inputs/s61/B0_b10/maps/mvs')/f'{nm}.npy')[sel].astype('f8'); td = dep[sel].astype('f8'); h = np.isfinite(mv) & (mv > 0)
            if h.sum() < 10: continue
            dmed = float(np.median(td[h]-mv[h])); per.append(dict(place=pl, place_ko=PLACE_KO[pl], view=nm, target_pixels=int(sel.sum()), image_depth_pixels=int(h.sum()), median_target_minus_image_m=dmed, unoccluded=abs(dmed) <= 1.))
        rows += per; per.sort(key=lambda r: r['median_target_minus_image_m'])
        pick = per[-2:][::-1]+per[:2] if len(per) >= 4 else per; figs[pl] = pick
        fig, axes = plt.subplots(1, len(pick), figsize=(5.2*len(pick), 4.6))
        for ax, r in zip(np.atleast_1d(axes), pick):
            with np.load(md/mi[r['view']]['file']) as z: own = z['owner']
            sel = np.isin(own, pr); im = np.asarray(Image.open(Path('/s0/fork_inputs/s61/B0_b10/images')/f'{r["view"]}.jpg').convert('RGB').resize((own.shape[1], own.shape[0])))
            ys, xs = np.nonzero(sel); cy, cx = int(np.median(ys)), int(np.median(xs)); hw = 140
            y0, y1, x0, x1 = max(0, cy-hw), min(own.shape[0], cy+hw), max(0, cx-hw), min(own.shape[1], cx+hw)
            ov = im.copy().astype('f4'); ov[sel] = .45*ov[sel]+.55*np.array([255, 0, 200]); ax.imshow(ov[y0:y1, x0:x1].astype('u1')); ax.set_axis_off()
            ax.set_title(f'목표 − 영상 깊이 중앙값 {r["median_target_minus_image_m"]:.1f} m\n' + ('사진에서 앞이 가려짐' if not r['unoccluded'] else '앞이 트임(1 m 안)'), fontsize=10)
        fig.suptitle(f'{PLACE_KO[pl]}: 분홍 = 이 자리의 목표가 적힌 화소. 왼쪽 둘 = 차이가 가장 큰 영상, 오른쪽 둘 = 가장 작은 영상', fontsize=11); fig.tight_layout()
        fig.savefig(A4D/'figures'/f'da_edge_photos_{pl}.png', dpi=110); dump(A4D/'figures'/f'da_edge_photos_{pl}.json', dict(at=now(), views=[r['view'] for r in pick], table='tables/da_edge_views.csv', scientific_verdict=None))
    dtable('da_edge_views', rows)
    summ = []
    for pl in ['edge_back', 'edge_annex']:
        q = [r for r in rows if r['place'] == pl]; summ.append(dict(place=pl, place_ko=PLACE_KO[pl], views=len(q), unoccluded_views=sum(r['unoccluded'] for r in q),
                                                              median_of_view_medians_m=med([r['median_target_minus_image_m'] for r in q]), views_diff_gt_10m=sum(r['median_target_minus_image_m'] > 10 for r in q)))
    dtable('da_edge_summary', summ); print('EDGE', summ, flush=True)

if __name__ == '__main__' and sys.argv[1] != 'wall_tables':
    a = sys.argv[1:]
    {'wall': lambda: wall(a[1]), 'front': front, 'wrong': lambda: wrong(a[1]), 'edge': edge}[a[0]]()

def wall_tables():
    rows = []; KB = ['목표 앞', '목표 ±1 m', '목표 뒤 1~5 m', '목표 뒤 5 m+']; CL = ['앞에 다른 것', '같음', '영상 깊이 없음']
    for mn in WALL_MODELS:
        f = DA/f'wall_{mn}.npz'
        if not f.exists(): continue
        z = loadz(f)
        for pl in ['visible_low', 'visible_high']:
            B = z[f'{pl}__bins']; px = z[f'{pl}__pixels']; dd = z[f'{pl}__dd']; cl = z[f'{pl}__cls']; ok = z[f'{pl}__pts_ok']; n = z[f'{pl}__pts_n']; r_ = np.where(n > 0, ok/np.maximum(n, 1), np.nan)
            r = dict(model=mn, place=pl, place_ko=PLACE_KO[pl], pixels=int(px.sum()), **{f'pixels_{c}_pct': 100*float(px[i]/max(px.sum(), 1)) for i, c in enumerate(CL)})
            tot = B.sum((0, 2)); r.update({f'w_{k}_per_pixel': float(tot[i]/max(px.sum(), 1)) for i, k in enumerate(KB)})
            front_kind = B[:, 0, :].sum(0); r.update({f'front_w_{KINDS[i]}_share_pct': 100*float(front_kind[i]/max(front_kind.sum(), 1e-12)) for i in range(4)})
            for ci, c in enumerate(CL):
                q = cl == ci; r[f'depth_minus_target_median_{c}'] = med(dd[q]); tb = B[ci].sum(1); r[f'w_front_per_pixel_{c}'] = float(tb[0]/max(px[ci], 1)); r[f'w_target_per_pixel_{c}'] = float(tb[1]/max(px[ci], 1))
            r.update(depth_minus_target_median=med(dd), depth_in_front_gt1m_pct=pct(dd < -1) if len(dd) else None, gt_points=len(n), gt_points_seen=int((n > 0).sum()),
                     extraction_share_median=med(r_), extraction_share_ge05_pct=pct(r_[np.isfinite(r_)] >= .5) if np.isfinite(r_).any() else None,
                     bound=len(z[f'{pl}__bound_opacity']), bound_opacity_median=med(z[f'{pl}__bound_opacity']), bound_size_median_m=med(z[f'{pl}__bound_size']), bound_angle_median_deg=med(z[f'{pl}__bound_angle']),
                     bound_normal_offset_median_m=med(z[f'{pl}__bound_h']))
            rows.append(r)
    dtable('da_visible_wall', rows); print('WALLT', len(rows), flush=True)
if __name__ == '__main__' and sys.argv[1] == 'wall_tables': wall_tables()
