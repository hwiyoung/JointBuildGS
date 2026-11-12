"""Addendum 2 check (read-only): target depth vs image depth agreement on one view (B0 LoD2 own): pixel-level distribution, also against the GT mesh-free depth of the target centres."""
import sys; sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1/addendum2')
from a2_common import *
for name in ['DJI_20241217094933_0013_D', 'DJI_20241217101359_0032_D']:
    md = maps_dir('B0_b10__LoD2', 'own'); mi = json.loads((md/'index.json').read_text())['views'][name]
    with np.load(md/mi['file']) as z: own = z['owner']; dep = z['depth']
    mvs = np.load(f'/s0/fork_inputs/s61/B0_b10/maps/mvs/{name}.npy'); conf = np.load(f'/s0/fork_inputs/s61/B0_b10/maps/conf/{name}.npy')
    k = own >= 0; h = np.isfinite(mvs) & (mvs > 0); b = h & ~k
    print(name, 'target px', int(k.sum()), 'target depth q', np.percentile(dep[k], [5, 50, 95]).round(2), 'mvs on target q', np.percentile(mvs[k & h], [5, 50, 95]).round(2) if (k & h).any() else None,
          'diff q', np.percentile((mvs-dep)[k & h], [5, 25, 50, 75, 95]).round(2) if (k & h).any() else None, 'bg mvs q', np.percentile(mvs[b], [5, 50, 95]).round(2), 'bg depth equals mvs', bool(np.allclose(dep[b & (conf > 0)], mvs[b & (conf > 0)])))
    t = loadz(targets_of('B0_b10__LoD2', 'own'), ['target']); E = np.asarray(mi['W2C']); K = np.asarray(mi['K']); q = np.unique(own[k])[:2000]; C = t['target'][q]@E[:3, :3].T+E[:3, 3]
    u = np.floor(K[0, 0]*C[:, 0]/C[:, 2]+K[0, 2]+.5).astype(int); v = np.floor(K[1, 1]*C[:, 1]/C[:, 2]+K[1, 2]+.5).astype(int); ins = (u >= 0) & (u < own.shape[1]) & (v >= 0) & (v < own.shape[0]) & (C[:, 2] > 0)
    print('  centre z vs map depth at its pixel: median |diff|', float(np.median(np.abs(C[ins, 2]-dep[v[ins], u[ins]]))), 'owner match', float((own[v[ins], u[ins]] == q[ins]).mean()))
