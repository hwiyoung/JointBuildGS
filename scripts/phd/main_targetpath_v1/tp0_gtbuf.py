"""GT point depth buffer per training view, once per site (shared by both priors and both runs). usage: tp0_gtbuf.py <site>
Rule = GTTARGET g1_maps: nearest GT point per pixel (u = floor(fx x/z + cx + 0.5)), then 3 x 3 minimum. GT points = GTJUDGE reference dense +
normal points inside the view box. Points kept in float32 and projected in chunks (memory). Writes /tp/gtbuf/<site>/<view>.npy (float32, inf = none)."""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_targetpath_v1')
from tp_common import *
from scipy.ndimage import minimum_filter
from concurrent.futures import ProcessPoolExecutor
H, W = 741, 1024
G = {}

def one(nm):
    out = O/'gtbuf'/G['site']/f'{nm}.npy'
    if out.exists(): return 0
    mm = G['views'][nm]; K = np.asarray(mm['K']); M = np.asarray(mm['W2C'], 'f4'); buf = np.full(H*W, np.inf, 'f4'); P = G['P']
    for a in range(0, len(P), 2_000_000):
        Pc = P[a:a+2_000_000]@M[:3, :3].T+M[:3, 3]; zz = Pc[:, 2]; ok = zz > .1; zo = zz[ok]
        uu = np.floor(K[0, 0]*Pc[ok, 0]/zo+K[0, 2]+.5).astype('i8'); vv = np.floor(K[1, 1]*Pc[ok, 1]/zo+K[1, 2]+.5).astype('i8')
        q_ = (uu >= 0) & (uu < W) & (vv >= 0) & (vv < H); lin = vv[q_]*W+uu[q_]; zv = zo[q_]
        if not len(lin): continue
        o = np.lexsort((zv, lin)); l2 = lin[o]; f = np.r_[True, l2[1:] != l2[:-1]]; np.minimum.at(buf, l2[f], zv[o][f])
    buf = minimum_filter(buf.reshape(H, W), size=3, mode='nearest'); tmp = out.with_suffix('.tmp.npy'); np.save(tmp, buf); tmp.rename(out); return 1

def main(site):
    t0 = time.monotonic(); G['site'] = site; G['P'] = gt_points(site).astype('f4'); (O/'gtbuf'/site).mkdir(parents=True, exist_ok=True)
    idx = json.loads((maps_of(f'{site}__ALS', 'ft')/'index.json').read_text()); G['views'] = idx['views']
    print('TP0_LOADED', site, len(G['P']), round(time.monotonic()-t0), flush=True)
    with ProcessPoolExecutor(int(os.environ.get('TP_WORKERS', 8))) as ex: done = sum(ex.map(one, list(idx['views']), chunksize=2))
    dump(O/'gtbuf'/f'{site}.json', dict(at=now(), site=site, gt_points=len(G['P']), views=len(idx['views']), written=done, rule='GTTARGET g1_maps GT point depth buffer, 3x3 min',
                                       seconds=time.monotonic()-t0, scientific_verdict=None))
    print('TP0', site, len(idx['views']), done, round(time.monotonic()-t0), flush=True)

if __name__ == '__main__': main(sys.argv[1])
