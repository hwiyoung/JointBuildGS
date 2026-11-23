"""Switch maps and arm folders (CPU). usage: df3_arms.py <stem>
From /df/maps/base/{base,ga}/<stem> (family base targets) build the variants named in config 'arms':
  ga_na        : switch 나 on ga — owner-pixel weight = clip(sqrt(σ_ref/σ), √0.1, √10); 10 m-rule zeros stay 0
  ga_da / ga_na_da : switch 다 — per target type (owner patch type: 가중 평균, 영상 깊이, 되돌림, 결측) divide owner-pixel weights (>0)
                 by that type's mean over all training views; background image-depth pixels (weight 1) untouched
  ga_ra_*      : switch 라 (and 마) — for pixels owned (ga map) by a split patch p: term 1 = disc of p at the prior height (D_P, weight c·w_P),
                 term 2 = disc of p at the image height (D_M, weight (1−c)·w_M); ray–disc intersection exactly as target_discs.cpp
                 (rx = (x − cx)/fx, |X − disc centre| <= r); an uncovered term is dropped; 10 m rule applied to each term;
                 마: both terms × max(c, 1 − c). 판 8 (ga_na_da_ra_ma): w_P, w_M with 나 and the ga_na_da type factor of 되돌림 / 영상 깊이.
                 Pixels whose two terms are both uncovered fall back to the background rule (image depth with conf>0, weight 1).
Arm folders /df/arms/<arm>/{targets/<stem>.npz, stage1/<stem>/seeds.npz} hard links to the family files, stage1/<stem>/maps -> variant dir."""
import sys, os
sys.path.insert(0, '/repo/scripts/phd/main_depthfix_v1')
from df_common import *

def disc_depth(K, M, centre, normal, radius, xs, ys):
    """per pixel (xs, ys) the camera z of the ray hit on the disc (centre, normal, radius) in world coords; NaN if no hit (target_discs.cpp rule)."""
    Rm = M[:3, :3]; tt = M[:3, 3]; c = centre@Rm.T + tt; nn = normal@Rm.T
    rx = (xs - K[0, 2])/K[0, 0]; ry = (ys - K[1, 2])/K[1, 1]
    den = nn[:, 0]*rx + nn[:, 1]*ry + nn[:, 2]; off = (nn*c).sum(1)
    with np.errstate(divide='ignore', invalid='ignore'):
        z = off/den
        dx = z*rx - c[:, 0]; dy = z*ry - c[:, 1]; dz = z - c[:, 2]
        ok = (np.abs(den) >= 1e-12) & (z > 0) & (dx*dx + dy*dy + dz*dz <= radius*radius + 1e-12) & (c[:, 2] > radius)
    return np.where(ok, z, np.nan)

def main(stem):
    c = cfg(False); t0 = time.monotonic(); site, prior = stem.split('__')
    pi = loadz(O/'patchinfo'/f'{stem}.npz'); typ = pi['type']; split = pi['split']
    tb = loadz(O/'families/base/targets'/f'{stem}.npz'); ref = float(tb['sigma_ref'])
    src = {v: O/'maps/base'/v/stem for v in ['base', 'ga']}; idx_ga = json.loads((src['ga']/'index.json').read_text())
    mvsroot = S0/'fork_inputs/s61'/site/'maps'; front_m = c['switches']['ga_front_m']; lo, hi = np.sqrt(.1), np.sqrt(10.)
    fams = {'kA': loadz(O/'families/kA/targets'/f'{stem}.npz'), 'k1': loadz(O/'families/k1/targets'/f'{stem}.npz')}
    cpat = {'kA': pi['c_kA'], 'k1': pi['c_k1']}
    want = sorted({a['maps'] for a in c['arms'].values()} - {'base', 'ga'})
    # weights of split patches for both faces (FINALTRAIN rule; u filled as in df1)
    umed = json.loads((O/'families/targets_receipt'/f'{stem}.json').read_text())['split_u_filled']['u_m']
    sP = tb['sigma_P_m']; uM = np.where(pi['u_filled'], umed, tb['u_mvs'])   # image-face σ (u filled with the scene's 보정 donor median, as df1)
    for f in fams:
        mI = split & (cpat[f] < .5); mP = split & (cpat[f] >= .5)
        assert np.allclose(fams[f]['sigma'][mI], uM[mI]) and np.allclose(fams[f]['sigma'][mP], sP[mP]), 'family σ differs from the face σ'
    hP, hM = tb['prior_height_m'], tb['mvs_mean_m']; rad = np.sqrt(tb['area']/np.pi); cen, nor = tb['centre'], tb['normal']
    # pass 1: type means (switch 다), over owner pixels with weight > 0
    sums = {v: np.zeros((2, 5)) for v in ['ga', 'ga_na']}
    names = list(idx_ga['views'])
    def na(w, sg, has): w = w.copy(); m = has & (w > 0); w[m] = np.clip(np.sqrt(ref/sg[m]), lo, hi); return w
    for name in names:
        z = loadz(src['ga']/f'{name}.npz'); own = z['owner']; has = own >= 0; tyx = np.where(has, typ[np.maximum(own, 0)], -1)
        for v, w in [('ga', z['weight']), ('ga_na', na(z['weight'], z['sigma'], has))]:
            m = has & (w > 0)
            for k in range(4): mk = m & (tyx == k); sums[v][0, k] += w[mk].sum(); sums[v][1, k] += mk.sum()
    factor = {v: {k: float(sums[v][0, k]/sums[v][1, k]) if sums[v][1, k] else None for k in range(4)} for v in sums}
    assert all(factor[v][k] is None or factor[v][k] > 0 for v in factor for k in factor[v])
    dests = {v: O/'maps/base'/v/stem for v in want}
    for v in want: dests[v].mkdir(parents=True, exist_ok=False)
    idx = {v: dict(idx_ga, variant=v, at=now(), views={}, type_mean_weight=({TYPE_KO[k]: f for k, f in factor['ga_na' if '_na' in v else 'ga'].items()} if '_da' in v else None)) for v in want}
    for v in want:
        if v.endswith(('_kA', '_k1')): idx[v]['target_sha256'] = sha(O/'families'/v.split('_')[-1]/'targets'/f'{stem}.npz')
    cnt = {v: dict(split_owner_pixels=0, both_terms=0, prior_only=0, image_only=0, neither_to_background=0, neither_no_image=0, front_rule_P=0, front_rule_M=0, check_return_DP_vs_drawn_max_m=0., check_image_DM_vs_drawn_max_m=0., check_pixels=0) for v in want if '_ra' in v}
    for jv, name in enumerate(names):
        z = loadz(src['ga']/f'{name}.npz'); own = z['owner']; has = own >= 0; tyx = np.where(has, typ[np.maximum(own, 0)], -1)
        meta = idx_ga['views'][name]; K = np.asarray(meta['K']); M = np.asarray(meta['W2C'])
        mvs = np.load(mvsroot/'mvs'/f'{name}.npy'); conf = np.load(mvsroot/'conf'/f'{name}.npy'); mvalid = np.isfinite(mvs) & (mvs > 0)
        for v in want:
            nav = '_na' in v; dav = '_da' in v; rav = '_ra' in v; mav = '_ma' in v
            w = na(z['weight'], z['sigma'], has) if nav else z['weight'].copy()
            fac = factor['ga_na' if nav else 'ga']
            if dav:
                for k in range(4):
                    mk = has & (w > 0) & (tyx == k)
                    if fac[k]: w[mk] = w[mk]/fac[k]
            out = dict(depth=z['depth'].copy(), sigma=z['sigma'].copy(), weight=w, owner=own)
            if rav:
                fam = v.split('_')[-1]; cc = cpat[fam]
                sp = has & split[np.maximum(own, 0)]; ys, xs = np.nonzero(sp); p = own[ys, xs]; cp = cc[p]; assert np.isfinite(cp).all()
                DP = disc_depth(K, M, cen[p] + hP[p, None]*nor[p], nor[p], rad[p], xs, ys)
                DM = disc_depth(K, M, cen[p] + hM[p, None]*nor[p], nor[p], rad[p], xs, ys)
                wP = np.clip(ref/sP[p], .1, 10); wM = np.clip(ref/uM[p], .1, 10)
                if nav: wP = np.clip(np.sqrt(ref/sP[p]), lo, hi); wM = np.clip(np.sqrt(ref/uM[p]), lo, hi)
                if dav: wP = wP/fac[2]; wM = wM/fac[1]
                mag = np.maximum(cp, 1 - cp) if mav else np.ones_like(cp)
                mv = mvs[ys, xs]; mvv = mvalid[ys, xs]
                fP = mvv & np.isfinite(DP) & (mv < DP - front_m); fM = mvv & np.isfinite(DM) & (mv < DM - front_m)
                w1 = np.where(np.isfinite(DP) & ~fP, cp*wP*mag, 0.).astype('f4'); w2 = np.where(np.isfinite(DM) & ~fM, (1 - cp)*wM*mag, 0.).astype('f4')
                d1 = np.where(np.isfinite(DP), DP, np.nan).astype('f4'); d2 = np.where(np.isfinite(DM), DM, np.nan).astype('f4')
                depth2 = np.full(own.shape, np.nan, 'f4'); weight2 = np.zeros(own.shape, 'f4')
                out['depth'][ys, xs] = d1; out['weight'][ys, xs] = w1; depth2[ys, xs] = d2; weight2[ys, xs] = w2
                neither = ~np.isfinite(DP) & ~np.isfinite(DM); bgp = neither & mvv & (conf[ys, xs] > 0)
                out['depth'][ys[bgp], xs[bgp]] = mv[bgp]; out['weight'][ys[bgp], xs[bgp]] = 1; out['owner'] = own.copy(); out['owner'][ys[neither], xs[neither]] = -1
                out['sigma'][ys[neither], xs[neither]] = np.nan
                out['depth2'] = depth2; out['weight2'] = weight2
                q = cnt[v]; q['split_owner_pixels'] += len(p); q['both_terms'] += int((np.isfinite(DP) & np.isfinite(DM)).sum()); q['prior_only'] += int((np.isfinite(DP) & ~np.isfinite(DM)).sum())
                q['image_only'] += int((~np.isfinite(DP) & np.isfinite(DM)).sum()); q['neither_to_background'] += int(bgp.sum()); q['neither_no_image'] += int((neither & ~bgp).sum())
                q['front_rule_P'] += int(fP.sum()); q['front_rule_M'] += int(fM.sum())
                # check: the ga map drew each split patch at its base-target face (되돌림 -> prior, 영상 깊이 -> image); the analytic disc must give the same depth
                dr = z['depth'][ys, xs]; tp_ = typ[p]; a1 = (tp_ == 2) & np.isfinite(DP); a2 = (tp_ == 1) & np.isfinite(DM)
                if a1.any(): q['check_return_DP_vs_drawn_max_m'] = max(q['check_return_DP_vs_drawn_max_m'], float(np.abs(DP[a1] - dr[a1]).max()))
                if a2.any(): q['check_image_DM_vs_drawn_max_m'] = max(q['check_image_DM_vs_drawn_max_m'], float(np.abs(DM[a2] - dr[a2]).max()))
                q['check_pixels'] += int(a1.sum() + a2.sum())
            pth = dests[v]/f'{name}.npz'; savez(pth, **out)
            idx[v]['views'][name] = dict(meta, file=pth.name, sha256=sha(pth))
        if (jv+1) % 40 == 0: print('ARMMAPS', stem, jv+1, round(time.monotonic()-t0), flush=True)
    for v in want: dump(dests[v]/'index.json', idx[v])
    # arm folders
    for arm, a in c['arms'].items():
        root = O/'arms'/arm; (root/'targets').mkdir(parents=True, exist_ok=True); st = root/'stage1'/stem; st.mkdir(parents=True, exist_ok=False)
        os.link(O/'families'/a['family']/'targets'/f'{stem}.npz', root/'targets'/f'{stem}.npz'); os.link(O/'families'/a['family']/'stage1'/stem/'seeds.npz', st/'seeds.npz')
        os.symlink(os.path.relpath(O/'maps/base'/a['maps']/stem, st), st/'maps')
        dump(st/'ready.json', dict(at=now(), arm=arm, stem=stem, maps=a['maps'], family=a['family'], two=a['two'], target_sha256=sha(root/'targets'/f'{stem}.npz'),
             seeds_sha256=sha(st/'seeds.npz'), index_sha256=sha(st/'maps/index.json'), scientific_verdict=None))
    dump(O/'maps/base'/f'arms_receipt_{stem}.json', dict(at=now(), stem=stem, variants=want, type_mean_weight={v: {TYPE_KO[k]: f for k, f in factor[v].items()} for v in factor},
         ra_pixels=cnt, seconds=time.monotonic()-t0, scientific_verdict=None))
    print('ARMS_READY', stem, json.dumps(cnt), round(time.monotonic()-t0), flush=True)

if __name__ == '__main__': main(sys.argv[1])
