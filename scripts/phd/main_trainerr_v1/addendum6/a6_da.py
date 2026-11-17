"""Work da (order 5): where the rendered depth lies at the point. FINALTRAIN 30000, addendum6_b.json work_da (locked). GPU (/source = r31).
  pix <stem>  : selected points of state 1 and 2 (all four groups); every training view whose image contains the point (camera z > 0.2): at the point's pixel the
                2DGS compositing (addendum 4 a4_da.contrib): weight alpha*T in front of / within +-tau of / behind the point depth, by kind relative to the
                point's patch; front mean offset; weighted median size; accumulated opacity; weighted-mean and median depth -> addendum6/da/pix_<stem>.npz
              + per point the nearest Gaussian (opacity >= 0.1): distance, normal / tangent parts on the target normal; Gaussians within tau: count, kind, opacity, size, angle
  tables      : labels of 5.2 / 5.3 per point (addendum6/da/labels_<stem>.npz) and tables/da_state1, da_state2 (four groups side by side)"""
import sys, time, math
sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1/addendum6')
from a6_common import *
DA6 = A6O/'da'; PTS = A6O/'points'

def bcfg6():
    p = R/'configs/phd/main_trainerr_v1/addendum6_b.json'; assert sha(p) == json.loads(p.with_name('addendum6_b.lock.json').read_text())['config_sha256'], 'addendum6_b changed after lock'
    return json.loads(p.read_text())

def load_ft(stem):
    """FINALTRAIN 30000 Gaussians (ply) with the snapshot binding (rows in the same order, checked on xyz)."""
    import torch
    sys.path.insert(0, '/source'); from scene import GaussianModel
    site, prior = stem.split('__'); m = FT/'runs'/site/f'ft_{prior}_s0/attempt1/model'; ply = m/'point_cloud/iteration_30000/point_cloud.ply'
    names = []
    with ply.open('rb') as f:
        while True:
            line = f.readline().decode('ascii').strip()
            if line == 'end_header': break
            if line.startswith('property') and 'f_rest_' in line: names.append(line)
    g = GaussianModel(round(math.sqrt(len(names)/3+1)-1)); g.load_ply(str(ply))
    for a in ['_xyz', '_features_dc', '_features_rest', '_scaling', '_rotation', '_opacity']: setattr(g, a, torch.nn.Parameter(getattr(g, a).detach(), requires_grad=False))
    s = loadz(m/'target_monitor/snapshot_30000.npz', ['xyz', 'target_tag', 'target_index'])
    assert len(s['xyz']) == len(g._xyz) and np.abs(s['xyz']-g._xyz.detach().cpu().numpy()).max() < 1e-4, 'snapshot rows differ from ply rows'
    return g, s['target_tag'], s['target_index'], ply

def pix(stem):
    import torch
    sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1'); sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1/addendum4'); import a4_da as D4
    camera = D4.gpu_setup(); t0 = time.monotonic(); P = loadz(PTS/f'sel_{stem}.npz'); sel = np.flatnonzero(np.isin(P['state'], [1, 2])); X = P['xyz'][sel].astype('f8'); tau = P['tau'][sel].astype('f8'); v = P['v'][sel]
    g, tag, tidx, ply = load_ft(stem); size = torch.exp(g._scaling).max(1).values.cpu().numpy(); op = torch.sigmoid(g._opacity[:, 0]).cpu().numpy()
    md, mi = D4.views_of(stem); vn = sorted(mi); recs = {k: [] for k in ['pt', 'view', 'zp', 'acc', 'mean', 'median', 'w3', 'wk', 'front_off', 'size_within', 'size_front', 'dist_within']}
    with torch.no_grad():
        for j, nm in enumerate(vn):
            mm = mi[nm]; K = np.asarray(mm['K']); M = np.asarray(mm['W2C']); Xc = X@M[:3, :3].T+M[:3, 3]; z = Xc[:, 2]; okz = z > .2
            with np.load(md/mm['file']) as zz: H, W = zz['owner'].shape
            uu = K[0, 0]*Xc[:, 0]/np.where(okz, z, 1)+K[0, 2]; vv = K[1, 1]*Xc[:, 1]/np.where(okz, z, 1)+K[1, 2]; ins = np.flatnonzero(okz & (uu >= 0) & (uu < W) & (vv >= 0) & (vv < H))
            if not len(ins): continue
            C = D4.contrib(g, camera(W, H, K, M, nm), np.floor(uu[ins]).astype('i8'), np.floor(vv[ins]).astype('i8')); n = len(ins)
            acc, mean, med_ = D4.per_pixel(C, n) if len(C) else (np.zeros(n), np.full(n, np.nan), np.full(n, np.nan))
            p = C[:, 0].astype('i8'); gi = C[:, 1].astype('i8'); w = C[:, 2]; dep = C[:, 3]; zp = z[ins][p]; tl = tau[ins][p]
            b = np.where(dep < zp-tl, 0, np.where(dep > zp+tl, 2, 1)); vp = v[ins][p]
            kd = np.where(tag[gi] == 1, np.where(tidx[gi] == vp, 0, 1), np.where(tag[gi] == 2, 2, 3))
            w3 = np.zeros((n, 3)); np.add.at(w3, (p, b), w); wk = np.zeros((n, 3, 4)); np.add.at(wk, (p, b, kd), w)
            fo = np.bincount(p, w*(zp-dep)*(b == 0), n)/np.maximum(w3[:, 0], 1e-12)
            def wmed(mask, val):
                out = np.full(n, np.nan); q = np.flatnonzero(mask)
                if len(q):
                    o = np.lexsort((val[q], p[q])); pq = p[q][o]; vq = val[q][o]; wq = w[q][o]; cs = np.cumsum(wq); st = np.searchsorted(pq, np.arange(n+1))
                    for i in np.flatnonzero(st[1:] > st[:-1]):
                        a_, e_ = st[i], st[i+1]; c0 = cs[a_-1] if a_ else 0.; k = np.searchsorted(cs[a_:e_]-c0, .5*(cs[e_-1]-c0)); out[i] = vq[a_+min(k, e_-a_-1)]
                return out
            sw = wmed(b == 1, size[gi]); sf = wmed(b == 0, size[gi]); dw = wmed(b == 1, np.abs(dep-zp))
            for k_, val in [('pt', sel[ins]), ('view', np.full(n, j, 'i2')), ('zp', z[ins]), ('acc', acc), ('mean', mean), ('median', med_), ('w3', w3), ('wk', wk), ('front_off', fo),
                            ('size_within', sw), ('size_front', sf), ('dist_within', dw)]: recs[k_].append(np.asarray(val))
            if j % 20 == 0: print('DA6_PIX', stem, j, len(vn), n, round(time.monotonic()-t0), flush=True)
    out = {k: np.concatenate(v_) for k, v_ in recs.items()}
    # nearest Gaussians (opacity >= 0.1) around each point
    T = Targets(stem); vis = np.flatnonzero(op >= .1); xyz = g._xyz.detach().cpu().numpy().astype('f8'); tree = cKDTree(xyz[vis]); d, jj = tree.query(X); jj = vis[jj]
    nrm = np.where((v >= 0)[:, None], T.normal[np.clip(v, 0, None)], np.nan); e = xyz[jj]-X; en = (e*nrm).sum(1); et = np.linalg.norm(e-en[:, None]*nrm, axis=1)
    from utils.general_utils import build_rotation
    gn = build_rotation(g._rotation)[:, :, 2].cpu().numpy(); within = tree.query_ball_point(X, tau); cnt = np.array([len(q) for q in within])
    kin = np.zeros((len(X), 4), 'i4'); omax = np.full(len(X), np.nan); smed = np.full(len(X), np.nan); ang = np.full(len(X), np.nan)
    for i, q in enumerate(within):
        if not q: continue
        r = vis[np.asarray(q)]; kd = np.where(tag[r] == 1, np.where(tidx[r] == v[i], 0, 1), np.where(tag[r] == 2, 2, 3)); kin[i] = np.bincount(kd, minlength=4)
        omax[i] = op[r].max(); smed[i] = np.median(size[r])
        if v[i] >= 0: ang[i] = np.degrees(np.median(np.arccos(np.clip(np.abs(gn[r]@nrm[i]), 0, 1))))
    savez(DA6/f'pix_{stem}.npz', **out, sel=sel, near_d=d, near_n=en, near_t=et, near_kind=np.where(tag[jj] == 1, np.where(tidx[jj] == v, 0, 1), np.where(tag[jj] == 2, 2, 3)),
          within_n=cnt, within_kind=kin, within_op_max=omax, within_size_med=smed, within_angle_med=ang, views=np.int32(len(vn)))
    dump(DA6/f'pix_{stem}.json', dict(at=now(), stem=stem, points=len(sel), pairs=len(out['pt']), model=str(ply), seconds=time.monotonic()-t0, scientific_verdict=None))
    print('DA6_DONE', stem, len(sel), len(out['pt']), round(time.monotonic()-t0), flush=True)

L1 = ['이웃이 그린다', '앞이 가려진다', '뚫려 있다', '섞여 있다']
L2 = ['가우시안이 어긋나 있다', '앞으로 당겨진다', '뒤로 밀린다', '영상마다 다르다', '그린 깊이는 맞다', '나뉘지 않음(그 밖)']
KIND4 = ['같은 목표', '다른 목표', '풀린 것', '묶이지 않은 것']

def ccfg6():
    p = R/'configs/phd/main_trainerr_v1/addendum6_c.json'; assert sha(p) == json.loads(p.with_name('addendum6_c.lock.json').read_text())['config_sha256'], 'addendum6_c changed after lock'
    return json.loads(p.read_text())

def gmed(key, val, n):
    """median of val per key (0..n-1), nan where none."""
    out = np.full(n, np.nan); ok = np.isfinite(val); k = key[ok]; v = val[ok]
    if not len(k): return out
    o = np.lexsort((v, k)); k = k[o]; v = v[o]; st = np.searchsorted(k, np.arange(n+1)); c = st[1:]-st[:-1]; h = np.flatnonzero(c)
    out[h] = .5*(v[st[h]+(c[h]-1)//2]+v[st[h]+c[h]//2]); return out

def facing(stem, P, sel, z):
    """per pair: camera centre on the outward side of the point (outward = target normal oriented by addendum3 outward(): non-walls up, walls by the LoD2 solid; no GT)."""
    sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1/addendum3')
    T = Targets(stem); v = P['v'][sel]; X = P['xyz'][sel].astype('f8'); nrm = np.where((v >= 0)[:, None], T.normal[np.clip(v, 0, None)], np.nan)
    ok = np.isfinite(nrm).all(1); out = np.full_like(nrm, np.nan); out[ok] = outward(stem, X[ok], nrm[ok])[0]
    mi = json.loads((maps_dir(stem, 'own')/'index.json').read_text())['views']; vn = sorted(mi); C = np.zeros((len(vn), 3))
    for j, nm in enumerate(vn): M = np.asarray(mi[nm]['W2C']); C[j] = -M[:3, :3].T@M[:3, 3]
    pos = np.full(len(P['state']), -1, 'i8'); pos[sel] = np.arange(len(sel)); k = pos[z['pt']]
    return ((C[z['view'].astype('i8')]-X[k])*out[k]).sum(1) > 0

def labels_of(c, z, k, n, tau, use):
    kk = k[use]; tl = tau[kk]; d = (z['mean']-z['zp'])[use]
    M = {nm: gmed(kk, z['w3'][use, i], n) for i, nm in enumerate(['front', 'within', 'behind'])}; M['acc'] = gmed(kk, z['acc'][use], n); M['mean_off'] = gmed(kk, d, n); M['median_off'] = gmed(kk, (z['median']-z['zp'])[use], n)
    vf = np.isfinite(d) & (d < -tl); vb = np.isfinite(d) & (d > tl); vw = np.isfinite(d) & ~vf & ~vb; nv = np.bincount(kk, minlength=n).astype(float)
    sf = np.bincount(kk, vf, n)/np.maximum(nv, 1); sb = np.bincount(kk, vb, n)/np.maximum(nv, 1); sw = np.bincount(kk, vw, n)/np.maximum(nv, 1)
    h = c['half']; sp = c['split_share']
    l1 = np.where(M['within'] >= h, 0, np.where(M['front'] >= h, 1, np.where((M['behind'] >= h) | (M['acc'] < h), 2, 3)))
    l2 = np.where(z['within_n'] == 0, 0, np.where((M['mean_off'] < -tau) & (M['front'] > M['within']), 1, np.where((M['mean_off'] > tau) & (M['behind'] > M['within']), 2,
                  np.where((sf >= sp) & (sb >= sp) & (sw < h), 3, np.where(sw >= h, 4, 5)))))
    nov = nv == 0; l1 = np.where(nov, -1, l1); l2 = np.where(nov & (z['within_n'] > 0), -1, l2)
    return l1, l2, M, sf, sb, sw, nv

VIEWSETS = ['화면에 드는 모든 영상(발주문 정의)', '점의 바깥쪽에서 보는 영상']

def labels(stem):
    c = ccfg6()['work_da']; P = loadz(PTS/f'sel_{stem}.npz'); z = loadz(DA6/f'pix_{stem}.npz'); sel = z['sel']; n = len(sel); pos = np.full(len(P['state']), -1, 'i8'); pos[sel] = np.arange(n)
    k = pos[z['pt']]; tau = P['tau'][sel].astype('f8'); fc = facing(stem, P, sel, z); res = {}
    for vs, use in zip(VIEWSETS, [np.ones(len(k), bool), fc]): res[vs] = labels_of(c, z, k, n, tau, use)
    savez(DA6/f'labels_{stem}.npz', sel=sel, state=P['state'][sel], group=P['group'][sel], facing_pairs=fc,
          **{f'{t}__{nm}': v for t, vs in zip(['all', 'facing'], VIEWSETS) for nm, v in zip(['label1', 'label2'], res[vs][:2])},
          **{f'{t}__views': res[vs][6].astype('i4') for t, vs in zip(['all', 'facing'], VIEWSETS)},
          **{f'{t}__share_{x}': res[vs][j] for t, vs in zip(['all', 'facing'], VIEWSETS) for x, j in [('front', 3), ('behind', 4), ('within', 5)]},
          **{f'{t}__med_{kk_}': v for t, vs in zip(['all', 'facing'], VIEWSETS) for kk_, v in res[vs][2].items()})
    return P, z, sel, k, res, fc

def tables():
    rows1, rows2 = [], []
    for stem in cfg6()['points']['scenes']:
        if not (DA6/f'pix_{stem}.npz').exists(): continue
        P, z, sel, k, res, fc = labels(stem); st = P['state'][sel]; g = P['group'][sel]
        for vs in VIEWSETS:
          l1, l2, M, sf, sb, sw, nv = res[vs]; use = fc if vs != VIEWSETS[0] else np.ones(len(k), bool)
          fk = np.zeros((len(sel), 4)); np.add.at(fk, k[use], z['wk'][use, 0, :]); wk_in = np.zeros((len(sel), 4)); np.add.at(wk_in, k[use], z['wk'][use, 1, :])
          for stt, lab, rows in [(1, L1, rows1), (2, L2, rows2)]:
              for gk in range(4):
                  m = (st == stt) & (g == gk); nn = int(m.sum())
                  if not nn: continue
                  L = l1 if stt == 1 else l2
                  r = dict(stem=stem, views=vs, state=f'상태 {stt}', group=GROUP_KO[gk], n=nn, small=nn < 30, no_view_pct=pct(nv[m] == 0), views_median=med(nv[m]))
                  r.update({f'{x}_pct': pct(L[m] == i) for i, x in enumerate(lab)})
                  r.update(weight_front_median=med(M['front'][m]), weight_within_median=med(M['within'][m]), weight_behind_median=med(M['behind'][m]), opacity_sum_median=med(M['acc'][m]),
                           mean_depth_minus_point_m_median=med(M['mean_off'][m]), median_depth_minus_point_m_median=med(M['median_off'][m]),
                           front_offset_m_median=med(gmed(k[use], z['front_off'][use], len(sel))[m]), size_within_m_median=med(gmed(k[use], z['size_within'][use], len(sel))[m]), size_front_m_median=med(gmed(k[use], z['size_front'][use], len(sel))[m]),
                           dist_within_m_median=med(gmed(k[use], z['dist_within'][use], len(sel))[m]))
                  tf = max(1e-12, float(fk[m].sum())); ti = max(1e-12, float(wk_in[m].sum()))
                  r.update({f'front_weight_{x}_pct': 100*float(fk[m][:, i].sum())/tf for i, x in enumerate(KIND4)}); r.update({f'within_weight_{x}_pct': 100*float(wk_in[m][:, i].sum())/ti for i, x in enumerate(KIND4)})
                  if stt == 2:
                      r.update(nearest_m_median=med(z['near_d'][m]), nearest_normal_abs_m_median=med(np.abs(z['near_n'][m])), nearest_tangent_m_median=med(z['near_t'][m]), within_tau_count_median=med(z['within_n'][m]),
                               within_tau_opacity_max_median=med(z['within_op_max'][m]), within_tau_size_median=med(z['within_size_med'][m]), within_tau_angle_deg_median=med(z['within_angle_med'][m]),
                               view_within_share_median=med(sw[m]), view_front_share_median=med(sf[m]), view_behind_share_median=med(sb[m]))
                      wk = z['within_kind'][m]; tw = max(1, int(wk.sum())); r.update({f'within_tau_{x}_pct': 100*float(wk[:, i].sum())/tw for i, x in enumerate(KIND4)})
                  rows.append(r)
        print('DA6_TABLE', stem, flush=True)
    table6('da_state1', rows1); table6('da_state2', rows2)

if __name__ == '__main__':
    a = sys.argv[1:]
    {'pix': lambda: pix(a[1]), 'tables': tables}[a[0]]()
