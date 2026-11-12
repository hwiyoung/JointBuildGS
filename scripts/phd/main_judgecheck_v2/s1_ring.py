"""고리 불확실도 (UNCERT-v1 커널 = JUDGECHECK-v1 ring_kernel.py, 바이트 같음). 참값 읽지 않음.
  s1_ring.py base <tile>  : MVS u_M R1.5 - WIDEN0 중심과 다른 패치만 새로 셈 + 중심이 같은 패치 200개 재현 표본(MVS, ALS)
  s1_ring.py sens <tile>  : MVS u_M R1.0,3.0 모든 패치, ALS sigma_P R1.0,3.0 모든 ALS 패치
  s1_ring.py face <tile>  : 같은 면 고리 R1.5 (MVS, ALS) - s1_ring_face.py
시드: WIDEN0 widen0_v2.json split.seed, [구역 번호, 사전 정보, 자료, R 번호, WIDEN0 패치 번호]."""
from common import *
sys.path.insert(0, str(HERE/'inherited'))
import ring_kernel as K
from scipy.spatial import cKDTree
import multiprocessing as mp
K.U.R_ID.update({1.0: 0, 1.5: 1, 3.0: 2})
WORKERS = int(os.environ.get('JC2_CPUS', '4'))
def chunk(ids): return [(int(i), K.one_patch(int(i))) for i in ids]
def load_points(tile, data):
    if data == 'mvs_a':
        p = WI/'points'/tile; return np.load(p/'mvs_a_xyz.npy').astype(np.float64), np.load(p/'mvs_a_view.npy'), np.load(p/'mvs_a_key.npy')
    raw = np.fromfile(W/'inputs/points'/tile/'als.bin', dtype=[('x', '<f8'), ('y', '<f8'), ('z', '<f8'), ('cls', 'u1'), ('multi', 'u1')])
    return np.c_[raw['x'], raw['y'], raw['z']][np.isin(raw['cls'], [2, 6])], None, None
def setup(tile, data):
    X, V, Kk = load_points(tile, data)
    K.G.clear(); K.G.update(X=X, V=V, data=data, site=tile, gt=None)
    K.G['tree'] = cKDTree(X, leafsize=32, balanced_tree=False, compact_nodes=False); K.G['levels'] = {}
    if data == 'mvs_a':
        for k in range(1, 6):
            n = int(np.searchsorted(Kk, 4.0 ** -k))
            if n < 1000: break
            K.G['levels'][k] = (n, cKDTree(X[:n], leafsize=32, balanced_tree=False, compact_nodes=False))
def compute(d, prior, data, radii, ids, label):
    centre = d['centre'] if data == 'mvs_a' else d['raw_centre']
    K.G.update(radii=radii, pset=prior, c=centre, n=d['old_normal'], roof=d['roof_like'], original_index=d['widen0_index'])
    N = len(d['kind']); out = {R: dict(u=np.full(N, np.nan), status=np.full(N, -1, np.int8), n_inner=np.full(N, -1, np.int32), n_ring=np.full(N, -1, np.int32)) for R in radii}
    blocks = [ids[i:i+100] for i in range(0, len(ids), 100)]; done = 0; t0 = time.monotonic()
    with mp.get_context('fork').Pool(WORKERS) as pool:
        for res in pool.imap_unordered(chunk, blocks):
            for i, rows in res:
                for R, r in rows.items():
                    out[R]['status'][i] = r['status']; out[R]['n_inner'][i] = r.get('n_inner', -1); out[R]['n_ring'][i] = r.get('n_ring', -1)
                    if r['status'] == 0: out[R]['u'][i] = r['u']
            done += len(res)
            if done % 20000 < 100: print('RING', label, done, len(ids), round(time.monotonic()-t0), flush=True)
    return out, time.monotonic() - t0
def main(mode, tile):
    cfg(); T = Timer(); recs = []
    files = {p: O/'geometry_raw'/f'{tile}__{p}.npz' for p in ['LoD2', 'ALS'] if (O/'geometry_raw'/f'{tile}__{p}.npz').exists()}
    dest = lambda p: O/'ring'/mode/f'{tile}__{p}.npz'
    if not files or all(dest(p).exists() for p in files): return
    geo = {p: loadz(f) for p, f in files.items()}; res = {p: dict(patch_id=geo[p]['patch_id']) for p in files}
    for p in geo:  # WIDEN0 u_worker 시드의 패치 번호 = patch_geometry 파일 안의 차례 (patch_id 숫자가 아님)
        pg = loadz(WI/'patch_geometry'/f'{tile}_{p}.npz', ['patch_id']); pos = {s: i for i, s in enumerate(pg['patch_id'])}
        geo[p]['widen0_index'] = np.array([pos[s] for s in geo[p]['patch_id']], np.int64); res[p]['widen0_seed_index'] = geo[p]['widen0_index']
    for data in ['mvs_a', 'als']:
        priors = list(files) if data == 'mvs_a' else [p for p in files if p == 'ALS']
        if not priors: continue
        setup(tile, data); T.mark(f'setup_{data}')
        for prior in priors:
            d = geo[prior]; N = len(d['kind']); ok = d['normal_defined'] & np.isfinite(d['old_normal']).all(1)
            rng = np.random.default_rng([20261112, tile_id()[tile], 0 if prior == 'LoD2' else 1, 0 if data == 'mvs_a' else 2])
            if mode == 'base' and data == 'mvs_a':
                ids = np.flatnonzero(ok & ~d['widen0_same_centre']); same = np.flatnonzero(ok & d['widen0_same_centre'])
                sample = np.sort(rng.choice(same, min(200, len(same)), replace=False)) if len(same) else same
                o, sec = compute(d, prior, data, [1.5], np.r_[ids, sample], f'{tile}:{prior}:{data}:base')
                rep = o[1.5]['u'][sample]; ref = d['u_mvs_widen0'][sample]
                eq = int(np.sum((rep.astype(np.float32) == ref.astype(np.float32)) | (~np.isfinite(rep) & ~np.isfinite(ref))))
                res[prior].update(u_mvs_R1p5=np.where(d['widen0_same_centre'], d['u_mvs_widen0'], o[1.5]['u']), status_R1p5=np.where(d['widen0_same_centre'], 99, o[1.5]['status']).astype(np.int8),
                                  recomputed=np.isin(np.arange(N), ids), repro_sample=sample, repro_value=rep)
                recs.append(dict(tile=tile, prior=prior, data=data, recomputed=len(ids), repro_n=len(sample), repro_equal=eq, seconds=sec))
            elif mode == 'base':
                sample = np.sort(rng.choice(np.flatnonzero(ok), min(200, int(ok.sum())), replace=False))
                o, sec = compute(d, prior, data, [1.5], sample, f'{tile}:{prior}:{data}:base')
                rep = o[1.5]['u'][sample]; ref = d['u_prior_widen0'][sample]; eq = int(np.sum((rep.astype(np.float32) == ref.astype(np.float32)) | (~np.isfinite(rep) & ~np.isfinite(ref))))
                res[prior].update(sigma_P_R1p5=d['u_prior_widen0'], als_repro_sample=sample, als_repro_value=rep)
                recs.append(dict(tile=tile, prior=prior, data=data, repro_n=len(sample), repro_equal=eq, seconds=sec))
            else:
                ids = np.flatnonzero(ok); o, sec = compute(d, prior, data, [1.0, 3.0], ids, f'{tile}:{prior}:{data}:sens')
                key = 'u_mvs' if data == 'mvs_a' else 'sigma_P'
                for R in [1.0, 3.0]:
                    tag = str(R).replace('.', 'p'); res[prior][f'{key}_R{tag}'] = o[R]['u']; res[prior][f'{key}_status_R{tag}'] = o[R]['status']
                recs.append(dict(tile=tile, prior=prior, data=data, computed=len(ids), seconds=sec))
        K.G.clear()
    for p in files: savez(dest(p), **res[p])
    dump(O/'ring'/mode/f'{tile}.json', dict(at=now(), tile=tile, mode=mode, rows=recs, marks=T.marks, workers=WORKERS, GT_read=False, scientific_verdict=None))
    print('RING_DONE', json.dumps(recs), flush=True)
if __name__ == '__main__': main(sys.argv[1], sys.argv[2])
