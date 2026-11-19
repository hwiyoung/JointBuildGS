"""Quick coverage of the eval GT rows by the patch squares (diagnostic of the surface build, before the full order-5 check).
usage: g1_cover.py <site> [trial name]   -> prints per scene: rows within tau of a patch square (in-plane |u|,|v|<=0.125+slack)."""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_gttarget_v1')
from gt_common import *
from scipy.spatial import cKDTree
site = sys.argv[1]; trial = sys.argv[2] if len(sys.argv) > 2 else None
root = O/'surface'/site if not trial else O/'surface_trials'/site/trial
p = loadz(root/'patches.npz'); tree = cKDTree(p['centre']); h = 0.125
out = {}
for prior in ['ALS', 'LoD2']:
    stem = f'{site}__{prior}'; r = loadz(GT/'scenes'/stem/'rows.npz', ['xyz', 'row_tau_m']); X = r['xyz'].astype('f8'); tau = r['row_tau_m']
    d, j = tree.query(X, k=8, distance_upper_bound=1.0, workers=16); ok = np.zeros(len(X), bool); best = np.full(len(X), np.inf)
    for q in range(8):
        jj = j[:, q]; v = jj < len(p['centre']); jj = np.where(v, jj, 0)
        D = X-p['centre'][jj]; n = p['normal'][jj]; t1 = p['t1'][jj]; t2 = p['t2'][jj]
        hit = v & (np.abs((D*t1).sum(1)) <= h+0.02) & (np.abs((D*t2).sum(1)) <= h+0.02); dn = np.abs((D*n).sum(1))
        best = np.where(hit, np.minimum(best, dn), best)
    ok = best <= tau
    out[prior] = dict(rows=len(X), within_tau_pct=round(100*ok.mean(), 2), no_square_pct=round(100*np.isinf(best).mean(), 2))
print('COVER', site, trial, json.dumps(out))
