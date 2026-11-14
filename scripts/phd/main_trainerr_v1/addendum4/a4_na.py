"""Work na (order 3): why bound Gaussians do not pass the opacity threshold after the 3000 reset (addendum4.json work_na + addendum4_b.json na). GPU, /source = r31.
  occl <run> <state>  : per Gaussian bound to a place patch at 3000_pre_reset and per training view containing its centre: accumulated opacity in front of it,
                        its own alpha*T, front weight by kind (2DGS torch compositing of addendum3 work na) at <state> -> addendum4/na/occl_<run>_<state>.npz
  tables              : per place / control and survived / deleted: occlusion, colour weight, views, size, angle, front kinds; sa-1 signed opacity gradients
                        by term every 100 from 3000 to 6000 (B0: magnitudes of tl_B0_LoD2_own, sign not recorded)"""
import sys, math
sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1/addendum4')
from a4_common import *
import time
NA = A4O/'na'
NARUNS = {'sa1_R1_ALS_record6000': dict(places=['floor_band', 'floor_control'], states=['3000_pre_reset', '3500'], surv='6000_pre_reset'),
          'tl_B0_b10_LoD2_s0': dict(places=['edge_back', 'edge_annex', 'edge_back_control', 'edge_annex_control'], states=['3000_pre_reset', '3500'], surv='6000_pre_reset'),
          'ba3_B0_ALS_record': dict(places=['annex_wrong', 'annex_right'], states=['3000_pre_reset'], surv='6000_pre_reset'),
          'tl_B0_LoD2_own': dict(places=['edge_back', 'edge_annex', 'edge_back_control'], states=['3000_pre_reset'], surv='6000_pre_reset')}

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

def survivors(run, name):
    m = RUNS4[run]['model']
    if (m/'trainlog/states'/f'{name}.npz').exists(): return set(loadz(m/'trainlog/states'/f'{name}.npz', ['uid'])['uid'].tolist())
    return set(load_pt(m, name)['uid'].tolist())

def comp(g, tag, tidx, cam, px, py, zref, selfi, blk=4096):
    """per pixel (one per Gaussian x view): front accumulated opacity (splats with depth < zref - 0.05), own alpha*T, front weight by kind relative to the pixel's Gaussian."""
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
    n = len(px); FA = torch.zeros(n, device='cuda'); SW = torch.zeros(n, device='cuda'); FK = torch.zeros((n, 4), device='cuda'); ACC = torch.zeros(n, device='cuda')
    pxt = torch.as_tensor(px, device='cuda').long(); pyt = torch.as_tensor(py, device='cuda').long(); zr = torch.as_tensor(zref, device='cuda').float(); si = torch.as_tensor(selfi, device='cuda').long()
    stag = tag[si]; sti = tidx[si]; tiles = (pyt//16)*gx+(pxt//16)
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
            w = torch.where(inc, alpha*Tb, torch.zeros_like(alpha)); ACC[pi] += w.sum(1)
            fr = dep < (zr[pi][:, None]-.05); wf = w*fr; FA[pi] += wf.sum(1)
            SW[pi] += (w*(gi[None] == si[pi][:, None])).sum(1)
            tg = tag[gi][None]; ti = tidx[gi][None]
            kind = torch.where(tg == 1, torch.where(ti == sti[pi][:, None], 0, 1), torch.where(tg == 2, 2, 3))
            FK[pi] += torch.zeros((len(pi), 4), device='cuda').scatter_add_(1, kind, wf)
            T = torch.where(done, T, T*torch.where(inc, om, torch.ones_like(om)).prod(1)); done = done | (term.any(1) & (first < om.shape[1]))
            if bool(done.all()): break
    return FA.cpu().numpy(), SW.cpu().numpy(), FK.cpu().numpy(), ACC.cpu().numpy()

def occl(run, state):
    import torch
    sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1'); sys.path.append('/repo/scripts/phd/main_finaltrain_v1')
    from te_render import camera
    from renderer import install
    install(); NA.mkdir(parents=True, exist_ok=True); t0 = time.monotonic(); cf = NARUNS[run]; model = RUNS4[run]['model']; stem = RUNS4[run]['stem']
    pre = load_pt(model, '3000_pre_reset'); S = pre if state == '3000_pre_reset' else load_pt(model, state)
    group = {}; pps = {pl: place_patches(pl) for pl in cf['places']}
    for pl, pp in pps.items():
        b = (pre['target_tag'].numpy() == 1) & np.isin(pre['target_index'].numpy(), pp['v']); group[pl] = pre['uid'].numpy()[b]
    uidx = {int(u): i for i, u in enumerate(S['uid'].tolist())}
    mi = json.loads((maps_dir(stem, 'own')/'index.json').read_text())['views']; out = {}
    with torch.no_grad():
        g = gmodel(S); tag = torch.as_tensor(S['target_tag'].long().numpy(), device='cuda'); tidx = torch.as_tensor(S['target_index'].long().numpy(), device='cuda')
        sel = {pl: np.array([uidx[int(u)] for u in us if int(u) in uidx], 'i8') for pl, us in group.items()}; allrows = np.unique(np.concatenate([v for v in sel.values()] or [np.zeros(0, 'i8')]))
        X = S['xyz'].double().numpy()[allrows]; recs = {k: [] for k in ['row', 'view', 'front', 'self_w', 'kind', 'acc']}
        for j, (nm, m) in enumerate(sorted(mi.items())):
            K = np.asarray(m['K']); M = np.asarray(m['W2C']); Xc = X@M[:3, :3].T+M[:3, 3]; z = Xc[:, 2]; okz = z > .2
            u = K[0, 0]*Xc[:, 0]/np.where(okz, z, 1)+K[0, 2]; v = K[1, 1]*Xc[:, 1]/np.where(okz, z, 1)+K[1, 2]
            with np.load(maps_dir(stem, 'own')/m['file']) as zz: H, W = zz['owner'].shape
            ins = okz & (u >= 0) & (u < W) & (v >= 0) & (v < H)
            if not ins.any(): continue
            cam = camera(W, H, K, M, nm); px = np.floor(u[ins]).astype('i8'); py = np.floor(v[ins]).astype('i8')
            FA, SW, FK, ACC = comp(g, tag, tidx, cam, px, py, z[ins], allrows[ins])
            recs['row'].append(allrows[ins]); recs['view'].append(np.full(ins.sum(), j, 'i2')); recs['front'].append(FA); recs['self_w'].append(SW); recs['kind'].append(FK); recs['acc'].append(ACC)
        R_ = {k: np.concatenate(v) if v else np.zeros(0) for k, v in recs.items()}
        rot = g.get_rotation.detach(); from utils.general_utils import build_rotation; nrm = build_rotation(rot)[:, :, 2].cpu().numpy()
    size = torch.exp(S['scaling']).max(1).values.numpy(); opa = torch.sigmoid(S['opacity'][:, 0]).numpy()
    np.savez_compressed(NA/f'occl_{run}_{state}.npz', **R_, uid=S['uid'].numpy()[allrows] if len(allrows) else np.zeros(0), rows=allrows, size=size[allrows], opacity=opa[allrows], disk_normal=nrm[allrows],
                        tag=S['target_tag'].numpy()[allrows], tidx=S['target_index'].numpy()[allrows], **{f'group_{pl}': us for pl, us in group.items()})
    rec = dict(at=now(), run=run, state=state, pairs=int(len(R_['row'])), gaussians=int(len(allrows)), views=len(mi), seconds=time.monotonic()-t0, scientific_verdict=None)
    dump(NA/f'occl_{run}_{state}.json', rec); print('OCCL', rec, flush=True)

def summarize(run):
    cf = NARUNS[run]; model = RUNS4[run]['model']; surv = survivors(run, cf['surv']); rows = []; per_g = {}
    E = load_events(model, ('delete',)); dl = {int(u): (int(r), int(it)) for u, r, it in zip(E['delete']['uid'], E['delete']['reason'], E['delete']['iteration'])}
    Z = {st: loadz(NA/f'occl_{run}_{st}.npz') for st in cf['states'] if (NA/f'occl_{run}_{st}.npz').exists()}
    for pl in cf['places']:
        pp = place_patches(pl); lut = {int(v): pp['out'][i] for i, v in enumerate(pp['v'])}; z0 = Z['3000_pre_reset']; us = z0[f'group_{pl}']
        for grp_name, gsel in [('살아남음', lambda u: int(u) in surv), ('제거됨', lambda u: int(u) not in surv and int(u) in dl)]:
            gu = np.array([u for u in us if gsel(u)], 'i8'); r = dict(run=run, place=pl, place_ko=PLACE_KO.get(pl, pl), group=grp_name, gaussians=len(gu))
            if grp_name == '제거됨': r['deleted_opacity_reason_pct'] = pct(np.array([dl[int(u)][0] == 1 for u in gu])) if len(gu) else None; r['deleted_iteration_median'] = med([dl[int(u)][1] for u in gu])
            for st, z in Z.items():
                rowuid = z['uid'][np.searchsorted(z['rows'], z['row'])] if len(z['row']) else np.zeros(0, 'i8'); m = np.isin(rowuid, gu)
                per = {}
                for u_, fr in zip(rowuid[m], z['front'][m]): per.setdefault(int(u_), []).append(fr)
                r[f'front_opacity_median_{st}'] = med([np.median(v) for v in per.values()]); r[f'gaussians_seen_{st}'] = len(per)
                r[f'open_view_share_median_{st}'] = med([np.mean(np.asarray(v) < .5) for v in per.values()]); r[f'open_views_median_{st}'] = med([int(np.sum(np.asarray(v) < .5)) for v in per.values()])
                if st == '3000_pre_reset':
                    sw = {}; vw = {}
                    for u_, s_ in zip(rowuid[m], z['self_w'][m]): sw[int(u_)] = sw.get(int(u_), 0.)+float(s_); vw[int(u_)] = vw.get(int(u_), 0)+1
                    r['colour_weight_sum_median'] = med(list(sw.values())); r['views_median'] = med(list(vw.values()))
                    fk = z['kind'][m]; tot = fk.sum(0); r.update({f'front_kind_{k}_share_pct': 100*float(tot[i]/max(tot.sum(), 1e-12)) for i, k in enumerate(['같은 목표', '다른 목표', '풀린 것', '묶이지 않은 것'])})
                    gi = np.isin(z['uid'], gu); r['size_m_median'] = med(z['size'][gi]); r['opacity_median_pre_reset'] = med(z['opacity'][gi])
                    tn = np.array([lut.get(int(t), pp['T'].normal[int(t)]) for t in z['tidx'][gi]]).reshape(-1, 3)
                    ang = np.degrees(np.arccos(np.clip(np.abs((z['disk_normal'][gi]*tn).sum(1)), 0, 1))); r['angle_to_target_normal_deg_median'] = med(ang)
                    per_g[(pl, grp_name)] = dict(uid=gu)
            rows.append(r)
    dtable(f'na_groups_{run}', rows); print('NA_GROUPS', run, len(rows), flush=True)
    if run == 'sa1_R1_ALS_record6000': grad_series(run, cf)
    if run == 'tl_B0_b10_LoD2_s0': grad_magnitude_b0()

def grad_series(run, cf):
    model = RUNS4[run]['model']; surv = survivors(run, cf['surv']); pre = raw_state(model, '3000_pre_reset'); rows = []
    files = [p for p in sorted((model/'trainlog/grads').glob('*.npz'), key=lambda p: int(p.stem)) if 3000 < int(p.stem) <= 6000]
    for pl in cf['places']:
        pp = place_patches(pl); b = (pre['target_tag'] == 1) & np.isin(pre['target_index'], pp['v']); us = pre['uid'][b]
        for f in files:
            g = loadz(f); it = int(f.stem)
            for grp, gs in [('살아남음', np.array([u for u in us if int(u) in surv])), ('제거됨', np.array([u for u in us if int(u) not in surv]))]:
                m = np.isin(g['uid'], gs); r = dict(place=pl, place_ko=PLACE_KO[pl], group=grp, iteration=it, alive=int(m.sum()))
                for term, ko in [('photo', '광도'), ('depth', '깊이')]:
                    up = -g[f'{term}_opacity_signed'][m].astype('f8')   # gradient-descent step direction on the opacity logit: + raises opacity
                    nz = up[up != 0]; r[f'{ko}_raise_sum'] = float(up.sum()); r[f'{ko}_raise_median'] = med(nz); r[f'{ko}_raise_pct'] = pct(nz > 0) if len(nz) else None; r[f'{ko}_nonzero'] = len(nz)
                rows.append(r)
    dtable('na_opacity_grad_sa1', rows)
    agg = []
    for pl in cf['places']:
        for grp in ['살아남음', '제거됨']:
            q = [r for r in rows if r['place'] == pl and r['group'] == grp]
            for w0, w1 in [(3000, 3500), (3500, 4500), (4500, 6000), (3000, 6000)]:
                qq = [r for r in q if w0 < r['iteration'] <= w1]
                agg.append(dict(place=pl, place_ko=PLACE_KO[pl], group=grp, window=f'{w0}–{w1}', **{f'{ko}_raise_sum': float(sum(r[f'{ko}_raise_sum'] for r in qq)) for ko in ['광도', '깊이']},
                                **{f'{ko}_nonzero_samples': int(sum(r[f'{ko}_nonzero'] for r in qq)) for ko in ['광도', '깊이']},
                                **{f'{ko}_raise_pct_of_nonzero': (100*sum(r[f'{ko}_raise_pct']*r[f'{ko}_nonzero']/100 for r in qq if r[f'{ko}_raise_pct'] is not None)/max(1, sum(r[f'{ko}_nonzero'] for r in qq))) for ko in ['광도', '깊이']},
                                **{f'{ko}_raise_median_of_iterations': med([r[f'{ko}_raise_median'] for r in qq if r[f'{ko}_raise_median'] is not None]) for ko in ['광도', '깊이']}))
    dtable('na_opacity_grad_sa1_windows', agg)

def grad_magnitude_b0():
    run = 'tl_B0_LoD2_own'; model = RUNS4[run]['model']; pre = raw_state(model, '3000_pre_reset'); surv = set(raw_state(model, '6000_pre_reset')['uid'].tolist()); rows = []
    files = [p for p in sorted((model/'trainlog/grads').glob('*.npz'), key=lambda p: int(p.stem)) if 3000 < int(p.stem) <= 6000]
    for pl in RUNS4[run]['places']:
        pp = place_patches(pl); b = (pre['target_tag'] == 1) & np.isin(pre['target_index'], pp['v']); us = pre['uid'][b]
        for grp, gs in [('살아남음', np.array([u for u in us if int(u) in surv])), ('제거됨', np.array([u for u in us if int(u) not in surv]))]:
            ph, dp = [], []
            for f in files:
                g = loadz(f); m = np.isin(g['uid'], gs); ph.append(g['photo_opacity'][m]); dp.append(g['depth_opacity'][m])
            ph = np.concatenate(ph) if ph else np.zeros(0); dp = np.concatenate(dp) if dp else np.zeros(0)
            rows.append(dict(run=run, place=pl, place_ko=PLACE_KO[pl], group=grp, gaussians=len(gs), samples=len(ph), photo_abs_median=med(ph), depth_abs_median=med(dp), photo_abs_sum=float(ph.sum()), depth_abs_sum=float(dp.sum()),
                             sign='확인 불가: 이 판의 기울기 기록은 크기만 있다(r28)', iterations=[int(f.stem) for f in files]))
    dtable('na_opacity_grad_b0_magnitude', rows)

if __name__ == '__main__' and sys.argv[1] != 'check':
    a = sys.argv[1:]
    {'occl': lambda: occl(a[1], a[2]), 'summarize': lambda: summarize(a[1])}[a[0]]()

def check(run, state, nview=3):
    """re-implementation check: total accumulated opacity at the pair pixels vs the CUDA render (same rule as addendum3 work na); front / self distributions."""
    import torch
    sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1'); sys.path.append('/repo/scripts/phd/main_finaltrain_v1')
    from te_render import camera
    from gaussian_renderer import render
    from types import SimpleNamespace
    from renderer import install
    install(); model = RUNS4[run]['model']; stem = RUNS4[run]['stem']; z = loadz(NA/f'occl_{run}_{state}.npz'); S = load_pt(model, state)
    mi = json.loads((maps_dir(stem, 'own')/'index.json').read_text())['views']; names = sorted(mi); rows = []
    vc = np.bincount(z['view'].astype('i8'), minlength=len(names)); top = np.argsort(-vc)[:nview]
    with torch.no_grad():
        g = gmodel(S); pipe = SimpleNamespace(convert_SHs_python=False, compute_cov3D_python=False, depth_ratio=0., debug=False)
        for j in top:
            nm = names[j]; m = mi[nm]; K = np.asarray(m['K']); M = np.asarray(m['W2C'])
            with np.load(maps_dir(stem, 'own')/m['file']) as zz: H, W = zz['owner'].shape
            cam = camera(W, H, K, M, nm); pk = render(cam, g, pipe, torch.zeros(3, device='cuda')); al = pk['rend_alpha'].squeeze().cpu().numpy()
            sel = z['view'] == j; X = S['xyz'].double().numpy()[z['row'][sel]]; Xc = X@M[:3, :3].T+M[:3, 3]
            u = np.floor(K[0, 0]*Xc[:, 0]/Xc[:, 2]+K[0, 2]).astype(int); v = np.floor(K[1, 1]*Xc[:, 1]/Xc[:, 2]+K[1, 2]).astype(int)
            d = np.abs(al[v, u]-z['acc'][sel])
            rows.append(dict(run=run, state=state, view=nm, pairs=int(sel.sum()), acc_abs_diff_max=float(d.max()), acc_abs_diff_p99=float(np.quantile(d, .99)), cuda_alpha_median=float(np.median(al[v, u])),
                             front_median=float(np.median(z['front'][sel])), front_lt05_pct=pct(z['front'][sel] < .5), self_w_median=float(np.median(z['self_w'][sel])), self_w_gt01_pct=pct(z['self_w'][sel] > .1)))
    allp = dict(run=run, state=state, view='모든 쌍', pairs=len(z['front']), front_median=float(np.median(z['front'])), front_lt05_pct=pct(z['front'] < .5), front_lt09_pct=pct(z['front'] < .9),
                self_w_median=float(np.median(z['self_w'])), self_w_gt01_pct=pct(z['self_w'] > .1), acc_median=float(np.median(z['acc'])))
    rows.append(allp); dtable(f'na_check_{run}_{state}', rows); print('NA_CHECK', rows, flush=True)

if __name__ == '__main__' and sys.argv[1] == 'check': check(sys.argv[2], sys.argv[3])
