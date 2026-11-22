"""Order 2: the depth supervision of the pixel of every (point, training view) pair (CPU). usage: tp2_pixels.py <stem> <run ft|gtt>
Pairs: the point projects inside the 1024 x 741 frame (z > 0.2 m) of a training view whose camera centre lies on the side the point's oriented
normal points to ('바깥쪽에서 보는 영상'). Pixel = floor(u), floor(v) (the convention of the target maps and GTTARGET g3_ca.pix).
Kind of the pixel's target in the run's own training maps (depth, weight, owner) with the point's tau:
  5 감독 없음: weight 0 | 3 영상 깊이 목표: owner < 0 (image depth target, weight > 0) with its position to the point (front / within / behind)
  1 맞는 목표: owner >= 0 and |d - z| <= tau | 2 앞의 다른 목표: owner >= 0 and d < z - tau | 4 뒤의 목표: owner >= 0 and d > z + tau
  for owner >= 0: the owner patch's method judgment region (FINALTRAIN target judge_region; GTT: -1) and whether the target depth lies within
  tau of the GT depth seen at that pixel (GTTARGET order-1 GT disc depth at the pixel when drawn and not occluded, else the GT point depth
  buffer 3 x 3 minimum).
Per pair also: weight, sigma, occluded pixel (GTTARGET rule at the point: GT point buffer nearer than z by > 0.5 m, or image depth nearer than z by
> 10 m / > 1 m), rendered depth of the run's 30,000 model at the pixel (stored base render; B173 x ALS FINALTRAIN from tp4 CPU compositing)
and its position to the point.
Writes /tp/pairs/<run>_<stem>.npz."""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_targetpath_v1')
from tp_common import *
from scipy.ndimage import minimum_filter
from concurrent.futures import ProcessPoolExecutor
H, W = 741, 1024
G = {}

def pairs_for_view(X, nrm, K, M):
    u, v, z, okz = project(X, K, M); inn = okz & (u >= 0) & (u < W) & (v >= 0) & (v < H)
    fac = ((cam_centre(M)[None]-X)*nrm).sum(1) > 0; i = np.flatnonzero(inn & fac)
    return i, np.floor(u[i]).astype('i4'), np.floor(v[i]).astype('i4'), z[i]

def one(j):
    nm = G['names'][j]; mm = G['views'][nm]; K = np.asarray(mm['K']); M = np.asarray(mm['W2C'])
    i, px, py, z = pairs_for_view(G['X'], G['nrm'], K, M)
    if not len(i): return None
    m = loadz(G['maps']/mm['file']); d = m['depth'][py, px]; w = m['weight'][py, px]; o = m['owner'][py, px]; s = m['sigma'][py, px]; tau = G['tau'][i]
    kind = np.where(w <= 0, 4, np.where(o < 0, 2, np.where(np.abs(d-z) <= tau, 0, np.where(d < z-tau, 1, 3)))).astype('i1')
    pos = np.where(d < z-tau, 0, np.where(d > z+tau, 2, 1)).astype('i1'); pos[~np.isfinite(d) | (w <= 0)] = -1
    # GT point depth buffer (3x3 min) and GT seen depth
    gb = np.load(G['gtbuf']/f'{nm}.npy', mmap_mode='r')[py, px]   # tp0_gtbuf.py (GTTARGET g1_maps rule)
    gseen = gb.astype('f8')
    if G['gttmaps'] is not None and (G['gttmaps']/mm['file']).exists():
        g = loadz(G['gttmaps']/mm['file'], ['depth', 'owner']); gd = g['depth'][py, px]; use = (g['owner'][py, px] >= 0) & np.isfinite(gd); gseen = np.where(use, gd, gseen)
    tok = np.abs(d-gseen) <= tau; tok[~np.isfinite(d)] = False
    mvs = np.load(G['mvsroot']/f'{nm}.npy')[py, px]; mv = np.isfinite(mvs) & (mvs > 0)
    occ_gt = gb < z-0.5; occ10 = mv & (mvs < z-10.); occ1 = mv & (mvs < z-1.)
    reg = np.where(o >= 0, G['jreg'][np.clip(o, 0, None)], -1).astype('i1')
    rd = np.full(len(i), np.nan)
    if G['render'] is not None and nm in G['render']:
        with np.load(G['render'][nm]) as zr: rd = zr['depth'][py, px].astype('f8')
        rd[rd <= 0] = np.nan
    return dict(pt=i.astype('i4'), view=np.full(len(i), j, 'i2'), px=px, py=py, z=z.astype('f4'), kind=kind, pos=pos, w=w.astype('f4'), sigma=s.astype('f4'),
                tdepth=d.astype('f4'), owner=o.astype('i4'), owner_region=reg, target_ok=tok, gseen=gseen.astype('f4'), occ_gt=occ_gt, occ10=occ10 | occ_gt, occ1=occ1 | occ_gt,
                mvs=np.where(mv, mvs, np.nan).astype('f4'), rdepth=rd.astype('f4'))

def main(stem, run):
    t0 = time.monotonic(); site, prior = stem.split('__'); P = loadz(O/'points'/f'sel_{stem}.npz')
    G['X'] = P['xyz'].astype('f8'); G['nrm'] = P['normal'].astype('f8'); G['tau'] = P['tau'].astype('f8')
    G['maps'] = maps_of(stem, run); idx = json.loads((G['maps']/'index.json').read_text()); G['views'] = idx['views']; G['names'] = list(idx['views'])
    gm = maps_of(stem, 'gtt'); G['gttmaps'] = gm if (gm/'index.json').exists() else None
    G['jreg'] = loadz(FT/'targets'/f'{stem}.npz', ['judge_region'])['judge_region'] if run == 'ft' else np.full(10**6, -1, 'i1')
    G['gtbuf'] = O/'gtbuf'/site; assert (O/'gtbuf'/f'{site}.json').exists(), 'run tp0_gtbuf.py first'; G['mvsroot'] = S0/'fork_inputs/s61'/site/'maps/mvs'
    rdir = render_dir(stem, run); G['render'] = None; rsrc = None
    if rdir is not None:
        rc = json.loads((rdir/'receipt.json').read_text()); G['render'] = {v['name']: rdir/v['file'] for v in rc['views']}
        rsrc = dict(dir=str(rdir), ply=rc.get('job', {}).get('ply'), model_sha256=rc.get('model_sha256'), depth_ratio=rc.get('depth_ratio', 0), variant=rc.get('variant', 'base'))
    with ProcessPoolExecutor(int(os.environ.get('TP_WORKERS', 16))) as ex: res = [r for r in ex.map(one, range(len(G['names'])), chunksize=2) if r is not None]
    out = {k: np.concatenate([r[k] for r in res]) for k in res[0]}
    if rdir is None:
        cp = O/'contrib'/f'{run}_{stem}_all.npz'
        if cp.exists():
            c = loadz(cp, ['pt', 'view', 'mean']); key = c['pt'].astype('i8')*100000+c['view']; o = np.argsort(key); k2 = out['pt'].astype('i8')*100000+out['view']
            pos = np.searchsorted(key[o], k2); pos = np.clip(pos, 0, len(o)-1); hit = key[o][pos] == k2; out['rdepth'] = np.where(hit, c['mean'][o][pos], np.nan).astype('f4')
            rsrc = f'{cp} (CPU compositing of the 30,000 ply, tp4_contrib.py all)'; print('TP2_RDEPTH_FROM_CONTRIB', hit.mean(), flush=True)
        else: rsrc = 'none'
    r = out['rdepth'].astype('f8'); z = out['z'].astype('f8'); tau = G['tau'][out['pt']]
    out['rpos'] = np.where(~np.isfinite(r), -1, np.where(r < z-tau, 0, np.where(r > z+tau, 2, 1))).astype('i1')
    savez(O/'pairs'/f'{run}_{stem}.npz', **out, views=np.int32(len(G['names'])))
    rec = dict(at=now(), stem=stem, run=run, pairs=len(out['pt']), points_with_pairs=int(len(np.unique(out['pt']))), points=len(G['X']), render_source=rsrc,
               rdepth_finite_pct=pct(np.isfinite(out['rdepth'])), kinds=np.bincount(out['kind'], minlength=5).tolist(), seconds=time.monotonic()-t0, scientific_verdict=None)
    dump(O/'pairs'/f'{run}_{stem}.json', rec); print('TP2', json.dumps(rec, ensure_ascii=False), flush=True)

if __name__ == '__main__': main(*sys.argv[1:])
