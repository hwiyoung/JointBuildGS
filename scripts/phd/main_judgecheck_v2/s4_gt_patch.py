"""패치마다 참값의 자리 gt_p (6.1 의 5 % 확인과 정밀도 확인에만, 평가 전용). UNCERT-v1 커널의 data=gt (ring_kernel.one_patch):
기둥 → 자료의 면 찾기 → 안쪽 점 LMedS 평면 → p = 안쪽 점 법선 거리 중앙값. 참값 점: WIDEN0 구역 gt_xyz.
LoD2: WIDEN0 gt_p 를 중심이 같은 패치에 그대로, 나머지는 WIDEN0 법선 축으로 새로 셈. ALS: JUDGEAPPLY truth.py 처럼 다시 맞춘 LiDAR 법선 축으로 모두 새로 셈.
  s4_gt_patch.py <tile> -> truth/gt_patch/<tile>__<prior>.npz (gt_p, gt_status)"""
from common import *
sys.path.insert(0, str(HERE/'inherited'))
import ring_kernel as K
from scipy.spatial import cKDTree
import multiprocessing as mp
WORKERS = int(os.environ.get('JC2_CPUS', '4'))
def chunk(ids): return [(int(i), K.one_patch(int(i))[0]) for i in ids]
def main(tile):
    cfg(); T = Timer(); recs = []
    files = {p: O/'geometry_raw'/f'{tile}__{p}.npz' for p in ['LoD2', 'ALS'] if (O/'geometry_raw'/f'{tile}__{p}.npz').exists()}
    dest = lambda p: O/'truth/gt_patch'/f'{tile}__{p}.npz'
    if not files or all(dest(p).exists() for p in files): return
    X = np.load(WI/'points'/tile/'gt_xyz.npy').astype(np.float64)
    K.G.clear(); K.G.update(X=X, V=None, data='gt', site=tile, gt=None, levels={}, tree=cKDTree(X, leafsize=32, balanced_tree=False, compact_nodes=False))
    for prior, f in files.items():
        d = loadz(f, ['patch_id', 'kind', 'centre', 'normal', 'old_normal', 'roof_like', 'widen0_same_centre', 'normal_defined'])
        pg = loadz(WI/'patch_geometry'/f'{tile}_{prior}.npz', ['patch_id']); pos = {s: i for i, s in enumerate(pg['patch_id'])}; oi = np.array([pos[s] for s in d['patch_id']], np.int64)
        N = len(d['kind']); gp = np.full(N, np.nan); st = np.full(N, -1, np.int8)
        if prior == 'LoD2':
            parts = []
            for root in [W/'patch_values', W/'holdout/patch_values']:
                q = root/f'{tile}__{prior}__R1.5.npz'
                if q.exists(): parts.append(loadz(q, ['patch_id', 'gt_p', 'gt_status']))
            wv = {k: np.concatenate([x[k] for x in parts]) for k in parts[0]}; wpos = {s: i for i, s in enumerate(wv['patch_id'])}; wi = np.array([wpos[s] for s in d['patch_id']])
            reuse = d['widen0_same_centre']; gp[reuse] = wv['gt_p'][wi[reuse]]; st[reuse] = wv['gt_status'][wi[reuse]]
            axis = d['old_normal']; ids = np.flatnonzero(~reuse & d['normal_defined'] & np.isfinite(axis).all(1)); roof = d['roof_like']
        else:
            axis = d['normal']; ids = np.flatnonzero(np.isfinite(axis).all(1)); roof = d['kind'] == 1
        K.G.update(c=d['centre'], n=np.nan_to_num(axis), roof=roof, pset=prior, original_index=oi)
        blocks = [ids[i:i+200] for i in range(0, len(ids), 200)]
        with mp.get_context('fork').Pool(WORKERS) as pool:
            for res in pool.imap_unordered(chunk, blocks):
                for i, r in res:
                    st[i] = r['status']
                    if r['status'] == 0: gp[i] = r['p']
        savez(dest(prior), patch_id=d['patch_id'], gt_p=gp, gt_status=st, recomputed=np.isin(np.arange(N), ids))
        recs.append(dict(prior=prior, patches=N, recomputed=len(ids), finite=int(np.isfinite(gp).sum())))
    K.G.clear(); dump(O/'truth/gt_patch'/f'{tile}.json', dict(at=now(), tile=tile, rows=recs, seconds=T.mark('end'), scientific_verdict=None)); print('GT_PATCH', tile, json.dumps(recs), round(T.mark('end')), flush=True)
if __name__ == '__main__': main(sys.argv[1])
