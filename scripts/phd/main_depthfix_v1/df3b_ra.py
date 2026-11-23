"""Switch 라 / 마 maps by reply 2 (CPU). usage: df3b_ra.py <stem>
Map P: every split patch disc at its prior height (σ_P), map M: at its image height (u, filled as df1); all other discs as the 판 0 base target.
Each map is drawn with the 판 1 (ga) rule: back-facing discs not drawn (per disc), 10 m rule -> weight 0, no disc -> image depth with conf > 0, weight 1.
Per pixel (sP = map P owner is a split patch, sM = map M owner is a split patch):
  both    : q_P = c(owner P), q_M = 1 − c(owner M)
  P only  : q_P = c(owner P), q_M = 1 − q_P          M only : q_M = 1 − c(owner M), q_P = 1 − q_M
  neither : the 판 1 map (판 8: ga_na_da) value, single term
  loss term 1 = q_P·w_P·|D̂ − D_P| (map P depth/weight), term 2 = q_M·w_M·|D̂ − D_M| (map M) -> keys depth/weight and depth2/weight2.
마: each term × max(c, 1 − c) of that term's target patch (reply 2 addendum). 판 8: w from each map with 나 (sqrt) and 다 (ga_na_da type factors; split owner: 되돌림 factor in P, 영상 깊이 factor in M).
Check (reply 2): with c ≡ 1 the arrays equal map P alone (term 2 weight 0), with c ≡ 0 map M alone.
Replaces the df3 variants ga_ra_kA, ga_ra_ma_kA, ga_ra_k1, ga_na_da_ra_ma_kA and their arm folders (none used by any training)."""
import sys, os, shutil
sys.path.insert(0, '/repo/scripts/phd/main_depthfix_v1')
from df_common import *

RA = {'ga_ra_kA': ('kA', False, False), 'ga_ra_ma_kA': ('kA', True, False), 'ga_ra_k1': ('k1', False, False), 'ga_na_da_ra_ma_kA': ('kA', True, True)}

def combine(zP, zM, z1, split, c, typ, ref, mag_on, nada, fac):
    """per-pixel arrays for one arm; zP/zM/z1 dicts of the three maps (z1 = 판 1 or ga_na_da map for nada)."""
    oP, oM = zP['owner'], zM['owner']; sP = (oP >= 0) & split[np.maximum(oP, 0)]; sM = (oM >= 0) & split[np.maximum(oM, 0)]
    cP = np.where(sP, c[np.maximum(oP, 0)], np.nan); cM = np.where(sM, c[np.maximum(oM, 0)], np.nan)
    qP = np.where(sP, cP, np.where(sM, 1 - (1 - cM), 0.)); qM = np.where(sM, 1 - cM, np.where(sP, 1 - cP, 0.))
    lo, hi = np.sqrt(.1), np.sqrt(10.)
    def w_of(z, split_type):
        w = z['weight'].astype('f8').copy(); own = z['owner']; h = (own >= 0) & (w > 0)
        if nada:
            w[h] = np.clip(np.sqrt(ref/z['sigma'][h]), lo, hi)
            ty = np.where(own >= 0, typ[np.maximum(own, 0)], -1); ty = np.where((own >= 0) & split[np.maximum(own, 0)], split_type, ty)
            for k in range(4):
                mk = h & (ty == k)
                if fac[k]: w[mk] = w[mk]/fac[k]
        return w
    wP = w_of(zP, 2); wM = w_of(zM, 1)
    # 마 (reply 2 addendum): each term × max(c, 1 − c) of that term's target patch (owner of that map if split, otherwise the patch its q came from)
    cPsrc = np.where(sP, cP, cM); cMsrc = np.where(sM, cM, cP)
    magP = np.maximum(cPsrc, 1 - cPsrc) if mag_on else 1.; magM = np.maximum(cMsrc, 1 - cMsrc) if mag_on else 1.
    any_s = sP | sM
    out = dict(depth=np.where(any_s, zP['depth'], z1['depth']).astype('f4'), weight=np.where(any_s, qP*wP*magP, z1['weight']).astype('f4'),
               sigma=np.where(any_s, zP['sigma'], z1['sigma']).astype('f4'), owner=np.where(any_s, oP, z1['owner']).astype('i4'),
               depth2=np.where(any_s, zM['depth'], np.nan).astype('f4'), weight2=np.where(any_s, qM*wM*magM, 0.).astype('f4'))
    stats = dict(split_pixels=int(any_s.sum()), both_split=int((sP & sM).sum()), p_only=int((sP & ~sM).sum()), m_only=int((~sP & sM).sum()),
                 both_terms=int((any_s & (out['weight'] > 0) & (out['weight2'] > 0)).sum()), owners_differ=int((any_s & (oP != oM)).sum()),
                 map_M_image_face_instructed=int((sM & (zM['weight'] > 0)).sum()),
                 p1_image_face_instructed=int(((z1['owner'] >= 0) & split[np.maximum(z1['owner'], 0)] & (typ[np.maximum(z1['owner'], 0)] == 1) & (z1['weight'] > 0)).sum()),
                 map_P_prior_face_instructed=int((sP & (zP['weight'] > 0)).sum()),
                 p1_prior_face_instructed=int(((z1['owner'] >= 0) & split[np.maximum(z1['owner'], 0)] & (typ[np.maximum(z1['owner'], 0)] == 2) & (z1['weight'] > 0)).sum()))
    return out, stats

def main(stem):
    c = cfg(False); t0 = time.monotonic(); site, prior = stem.split('__')
    pi = loadz(O/'patchinfo'/f'{stem}.npz'); split = pi['split']; typ = pi['type']
    tb = loadz(O/'families/base/targets'/f'{stem}.npz'); ref = float(tb['sigma_ref']); ids = np.flatnonzero(tb['surface_exists'])
    umed = json.loads((O/'families/targets_receipt'/f'{stem}.json').read_text())['split_u_filled']['u_m']; uM = np.where(pi['u_filled'], umed, tb['u_mvs'])
    rec_old = json.loads((O/'maps/base'/f'arms_receipt_{stem}.json').read_text()); fac = {int(k): v for k, v in {i: rec_old['type_mean_weight']['ga_na'][TYPE_KO[i]] for i in range(4)}.items()}
    bg_sigma = json.loads((O/'families/base/stage1'/stem/'seed_receipt.json').read_text())['background_sigma']
    # disc sets for the two maps
    tP = tb['target'].copy(); tM = tb['target'].copy(); sgP = tb['sigma'].astype('f8').copy(); sgM = sgP.copy()
    tP[split] = tb['centre'][split] + tb['prior_height_m'][split, None]*tb['normal'][split]; sgP[split] = tb['sigma_P_m'][split]
    tM[split] = tb['centre'][split] + tb['mvs_mean_m'][split, None]*tb['normal'][split]; sgM[split] = uM[split]
    assert np.isfinite(tP[ids]).all() and np.isfinite(tM[ids]).all() and (sgP[ids] > 0).all() and (sgM[ids] > 0).all()
    env, src = rasterizer_env(); fn = env['rasterizer'](); rad = np.sqrt(tb['area'][ids]/np.pi)
    ptsP = np.c_[tP[ids], tb['normal'][ids], rad, ids].astype(float); ptsM = np.c_[tM[ids], tb['normal'][ids], rad, ids].astype(float)
    idx1 = json.loads((O/'maps/base/ga'/stem/'index.json').read_text()); mvsroot = S0/'fork_inputs/s61'/site/'maps'; front_m = c['switches']['ga_front_m']
    for v in list(RA) + ['ga_P', 'ga_M']:
        dd = O/'maps/base'/v/stem
        if dd.exists(): shutil.rmtree(dd)
        dd.mkdir(parents=True)
    idx = {v: dict(idx1, variant=v, at=now(), views={}, rule='reply 2 (회신2_v1.md)') for v in list(RA) + ['ga_P', 'ga_M']}
    for v in RA: idx[v]['target_sha256'] = sha(O/'families'/RA[v][0]/'targets'/f'{stem}.npz')
    tot = {v: {} for v in RA}; chk = dict(c1_equals_P=True, c0_equals_M=True, views_checked=0)
    for jv, (name, meta) in enumerate(idx1['views'].items()):
        K = np.asarray(meta['K']); M = np.asarray(meta['W2C']); cam = dict(H=741, W=1024, W2C=M, fx=K[0, 0], fy=K[1, 1], cx=K[0, 2], cy=K[1, 2]); Cc = cam_centre(M)
        mvs = np.load(mvsroot/'mvs'/f'{name}.npy'); conf = np.load(mvsroot/'conf'/f'{name}.npy'); mvalid = np.isfinite(mvs) & (mvs > 0)
        zz = {}
        for v, tt, sg, pts in [('ga_P', tP, sgP, ptsP), ('ga_M', tM, sgM, ptsM)]:
            front = ((Cc[None] - tt[ids])*tb['normal'][ids]).sum(1) > 0
            depth, owner, K2, M2 = env['draw'](fn, pts[front], cam); has = owner >= 0
            sigma = np.full(depth.shape, np.nan, 'f4'); sigma[has] = sg[owner[has]]
            bg = (~has) & mvalid & (conf > 0); depth[bg] = mvs[bg]; sigma[bg] = bg_sigma
            weight = np.zeros(depth.shape, 'f4'); weight[has] = np.clip(ref/sigma[has], .1, 10); weight[bg] = 1
            near = has & mvalid & (mvs < depth - front_m); weight[near] = 0
            zz[v] = dict(depth=depth, sigma=sigma, weight=weight, owner=owner)
            p = O/'maps/base'/v/stem/f'{name}.npz'; savez(p, **zz[v], front_rule=near); idx[v]['views'][name] = dict(meta, file=p.name, sha256=sha(p))
        z1 = loadz(O/'maps/base/ga'/stem/f'{name}.npz'); z4 = loadz(O/'maps/base/ga_na_da'/stem/f'{name}.npz')
        for v, (fam, mag_on, nada) in RA.items():
            cc = pi['c_kA'] if fam == 'kA' else pi['c_k1']
            out, st = combine(zz['ga_P'], zz['ga_M'], z4 if nada else z1, split, cc, typ, ref, mag_on, nada, fac)
            for k_, x in st.items(): tot[v][k_] = tot[v].get(k_, 0) + x
            p = O/'maps/base'/v/stem/f'{name}.npz'; savez(p, **out); idx[v]['views'][name] = dict(meta, file=p.name, sha256=sha(p))
        if jv % 25 == 0:   # reply 2 check on every 25th view
            for cv, key, other in [(1., 'ga_P', 'weight2'), (0., 'ga_M', 'weight')]:
                out, _ = combine(zz['ga_P'], zz['ga_M'], z1, split, np.where(split, cv, np.nan), typ, ref, False, False, fac)
                s_ = (zz['ga_P']['owner'] >= 0) & split[np.maximum(zz['ga_P']['owner'], 0)] | (zz['ga_M']['owner'] >= 0) & split[np.maximum(zz['ga_M']['owner'], 0)]
                if cv == 1.: ok = np.array_equal(out['weight'][s_], zz['ga_P']['weight'][s_]) and not out['weight2'][s_].any() and np.array_equal(out['depth'][s_], zz['ga_P']['depth'][s_], equal_nan=True)
                else: ok = np.array_equal(out['weight2'][s_], zz['ga_M']['weight'][s_]) and not out['weight'][s_].any() and np.array_equal(out['depth2'][s_], zz['ga_M']['depth'][s_], equal_nan=True)
                # outside split pixels: 판 1 map; map P / map M equal 판 1 there (no split disc in front in either map)
                ok = ok and np.array_equal(out['weight'][~s_], z1['weight'][~s_]) and np.array_equal(zz[key]['weight'][~s_], z1['weight'][~s_])
                chk['c1_equals_P' if cv == 1. else 'c0_equals_M'] &= bool(ok)
            chk['views_checked'] += 1
        if (jv+1) % 40 == 0: print('RAMAPS', stem, jv+1, round(time.monotonic()-t0), flush=True)
    for v in idx: dump(O/'maps/base'/v/stem/'index.json', idx[v])
    for arm, a in c['arms'].items():
        if a['maps'] not in RA: continue
        root = O/'arms'/arm; st = root/'stage1'/stem
        if st.exists(): shutil.rmtree(st)
        (root/'targets').mkdir(parents=True, exist_ok=True); tf = root/'targets'/f'{stem}.npz'
        if tf.exists(): tf.unlink()
        st.mkdir(parents=True); os.link(O/'families'/a['family']/'targets'/f'{stem}.npz', tf); os.link(O/'families'/a['family']/'stage1'/stem/'seeds.npz', st/'seeds.npz')
        os.symlink(os.path.relpath(O/'maps/base'/a['maps']/stem, st), st/'maps')
        dump(st/'ready.json', dict(at=now(), arm=arm, stem=stem, maps=a['maps'], family=a['family'], two=a['two'], rule='reply 2', target_sha256=sha(tf),
             seeds_sha256=sha(st/'seeds.npz'), index_sha256=sha(st/'maps/index.json'), scientific_verdict=None))
    dump(O/'maps/base'/f'ra_receipt_{stem}.json', dict(at=now(), stem=stem, pixels=tot, check=chk, type_factor_ga_na=fac, seconds=time.monotonic()-t0, scientific_verdict=None))
    print('RA_READY', stem, json.dumps(dict(pixels=tot, check=chk)), round(time.monotonic()-t0), flush=True)

if __name__ == '__main__': main(sys.argv[1])
