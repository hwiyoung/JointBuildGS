"""SUPERSEDED by the reply-2 check in df3b_ra.py (rule of 판 5~8 changed before any training). Order 2.4 check: with c = 1 a split patch trains like a 되돌림 patch, with c = 0 like an 영상 깊이 patch (per-patch loss value).
For one 되돌림 and one 영상 깊이 split patch of the stem (the one with most owner pixels in the first view where it owns >= 50 pixels):
  L_two(c) = Σ c·w_P|D̂−D_P| + (1−c)·w_M|D̂−D_M| over its pixels (df3 rule, 10 m rule per term), with D̂ = drawn depth + fixed noise;
  L_single(face) = Σ w|D̂−D| of the ga map when the patch has that face (되돌림 -> prior face as drawn, 영상 깊이 -> image face as drawn).
Equality is checked for c = 1 (되돌림) and c = 0 (영상 깊이). usage: df7_ccheck.py <stem>"""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_depthfix_v1')
from df_common import *
import df3_arms as D3

def main(stem):
    site, prior = stem.split('__'); pi = loadz(O/'patchinfo'/f'{stem}.npz'); tb = loadz(O/'families/base/targets'/f'{stem}.npz'); ref = float(tb['sigma_ref'])
    umed = json.loads((O/'families/targets_receipt'/f'{stem}.json').read_text())['split_u_filled']['u_m']; uM = np.where(pi['u_filled'], umed, tb['u_mvs'])
    idx = json.loads((O/'maps/base/ga'/stem/'index.json').read_text()); mvsroot = S0/'fork_inputs/s61'/site/'maps'; rng = np.random.default_rng(0); out = []
    for want, cval in [(2, 1.0), (1, 0.0)]:
        done = False
        for name, meta in idx['views'].items():
            z = loadz(O/'maps/base/ga'/stem/f'{name}.npz'); own = z['owner']; m = (own >= 0) & pi['split'][np.maximum(own, 0)] & (pi['type'][np.maximum(own, 0)] == want)
            if m.sum() < 50: continue
            p = np.bincount(own[m]).argmax(); sel = own == p
            if sel.sum() < 50: continue
            ys, xs = np.nonzero(sel); K = np.asarray(meta['K']); M = np.asarray(meta['W2C']); mvs = np.load(mvsroot/'mvs'/f'{name}.npy')[ys, xs]
            cen, nor, rad = tb['centre'][p], tb['normal'][p], np.sqrt(tb['area'][p]/np.pi)
            DP = D3.disc_depth(K, M, np.tile(cen + tb['prior_height_m'][p]*nor, (len(xs), 1)), np.tile(nor, (len(xs), 1)), np.full(len(xs), rad), xs, ys)
            DM = D3.disc_depth(K, M, np.tile(cen + tb['mvs_mean_m'][p]*nor, (len(xs), 1)), np.tile(nor, (len(xs), 1)), np.full(len(xs), rad), xs, ys)
            Dhat = z['depth'][ys, xs] + rng.normal(0, .3, len(xs))
            wP = np.clip(ref/tb['sigma_P_m'][p], .1, 10); wM = np.clip(ref/uM[p], .1, 10)
            v1 = np.isfinite(DP) & ~(np.isfinite(mvs) & (mvs > 0) & (mvs < DP - 10)); v2 = np.isfinite(DM) & ~(np.isfinite(mvs) & (mvs > 0) & (mvs < DM - 10))
            L_two = float(np.sum(np.where(v1, cval*wP*np.abs(Dhat - np.where(v1, DP, 0)), 0)) + np.sum(np.where(v2, (1 - cval)*wM*np.abs(Dhat - np.where(v2, DM, 0)), 0)))
            w = z['weight'][ys, xs]; L_one = float(np.sum(w*np.abs(Dhat - z['depth'][ys, xs])))
            out.append(dict(stem=stem, case='c = 1 → 되돌림' if want == 2 else 'c = 0 → 영상 깊이', view=name, patch=int(p), pixels=int(len(xs)), L_two=L_two, L_single=L_one,
                            rel_diff=abs(L_two - L_one)/max(L_one, 1e-12), passed=abs(L_two - L_one) <= 1e-4*max(L_one, 1e-12)))
            done = True; break
        assert done, (stem, want)
    dump(O/'checks'/f'ccheck_{stem}.json', dict(rows=out, scientific_verdict=None)); print('CCHECK', json.dumps(out, ensure_ascii=False), flush=True)

if __name__ == '__main__': main(sys.argv[1])
