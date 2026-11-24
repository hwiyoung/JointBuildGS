"""Order 5.3 (판 1~4) and 6 (판 1 own points): per GT point, what the pixels it lands on receive in each map (CPU, no training result needed).
For every point (pts_<stem>) and training view where the point is in frame and its normal faces the camera ('outward', TARGETPATH rule):
  pixel = floor(K·x + 0.5); occluded = GT depth buffer (TARGETPATH tp0) nearer than the point by > 0.5 m (GTTARGET margin);
  per map (판 0 base, 판 1 ga, 판 2 ga_na, 판 3 ga_da, 판 4 ga_na_da): right target = disc owner, weight > 0, |target depth − point depth| <= τ;
  weight = map weight of the pixel (NaN if no disc target).
Per point: outward views, share of views with a right target (> 1/2 flag), median pixel weight over disc-target views,
occluded-instruction views in 판 0 (occluded & disc target with weight > 0) and its > 1/2 flag (판 1 own points, order 6).
usage: df12_pixels.py <stem>   writes /df/points/pix_<stem>.npz"""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_depthfix_v1')
from df_common import *
TP = PH/'main_targetpath_v1/PHD-MAIN-TARGETPATH-v1'
MAPS = {'p0': 'base', 'p1': 'ga', 'p2': 'ga_na', 'p3': 'ga_da', 'p4': 'ga_na_da'}

def main(stem):
    t0 = time.monotonic(); site = stem.split('__')[0]; P = loadz(O/'points'/f'pts_{stem}.npz', ['xyz', 'normal', 'tau']); X = P['xyz'].astype('f8'); N = P['normal'].astype('f8'); tau = P['tau']; n = len(X)
    idx = json.loads((O/'maps/base/base'/stem/'index.json').read_text())['views']; V = len(idx)
    nvis = np.zeros(n, 'i2'); rvis = {a: np.zeros(n, 'i2') for a in MAPS}; nout = np.zeros(n, 'i2'); nocc = np.zeros(n, 'i2'); right = {a: np.zeros(n, 'i2') for a in MAPS}; W = {a: np.full((V, n), np.nan, 'f4') for a in MAPS}
    for j, (name, meta) in enumerate(idx.items()):
        K = np.asarray(meta['K']); M = np.asarray(meta['W2C']); Cc = cam_centre(M); Pc = X@M[:3, :3].T + M[:3, 3]; z = Pc[:, 2]
        with np.errstate(divide='ignore', invalid='ignore'):
            u = np.floor(K[0, 0]*Pc[:, 0]/z + K[0, 2] + .5); v = np.floor(K[1, 1]*Pc[:, 1]/z + K[1, 2] + .5)
        ok = (z > .1) & (u >= 0) & (u < 1024) & (v >= 0) & (v < 741) & (((Cc[None] - X)*N).sum(1) > 0)
        ii = np.flatnonzero(ok); uu = u[ii].astype(int); vv = v[ii].astype(int); zz = z[ii]; nout[ii] += 1
        mv = np.load(S0/'fork_inputs/s61'/site/'maps/mvs'/f'{name}.npy')[vv, uu]; vis = ~(np.isfinite(mv) & (mv > 0) & (mv < zz - 10.)); nvis[ii] += vis
        gt = np.load(TP/'gtbuf'/site/f'{name}.npy')[vv, uu]; occ = np.isfinite(gt) & (gt < zz - .5)
        for a, var in MAPS.items():
            zm = loadz(O/'maps/base'/var/stem/f'{name}.npz', ['depth', 'weight', 'owner']); own = zm['owner'][vv, uu] >= 0; w = zm['weight'][vv, uu]; d = zm['depth'][vv, uu]
            rr = own & (w > 0) & (np.abs(d - zz) <= tau[ii]); right[a][ii] += rr.astype('i2'); rvis[a][ii] += (rr & vis).astype('i2'); W[a][j, ii] = np.where(own, w, np.nan)
            if a == 'p0': nocc[ii] += (occ & own & (w > 0)).astype('i2')
        if (j+1) % 50 == 0: print('PIX', stem, j+1, round(time.monotonic()-t0), flush=True)
    out = dict(visible_views=nvis, outward_views=nout, occluded_instr_views_p0=nocc, occluded_instr_half_p0=nocc*2 > nout)
    for a in MAPS:
        out[f'right_views_{a}'] = right[a]; out[f'right_half_{a}'] = right[a]*2 > nout
        out[f'right_half_visible_{a}'] = rvis[a]*2 > nvis
        with np.errstate(all='ignore'):
            out[f'w_median_{a}'] = np.nanmedian(W[a], axis=0).astype('f4'); Wp = np.where(W[a] > 0, W[a], np.nan); out[f'w_median_pos_{a}'] = np.nanmedian(Wp, axis=0).astype('f4')
    savez(O/'points'/f'pix_{stem}.npz', **out); print('PIX_DONE', stem, n, round(time.monotonic()-t0), flush=True)

if __name__ == '__main__': main(sys.argv[1])
