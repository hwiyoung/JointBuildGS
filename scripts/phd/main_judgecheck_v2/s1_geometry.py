"""단계 0-3/1: 구역마다 기하 셈 (MVS 원통, 항공 LiDAR 법선과 LiDAR 원통). 참값 읽지 않음.
WIDEN0 raw_centre + 탐색 지역 이동(ALS)을 쓴다. 상속: JUDGECHECK-v1 cylinders.cpp / geometry.fit_normals (바이트 같음)."""
from common import *
from inherit import functions
from scipy.spatial import cKDTree
import subprocess
BASE = O/'r1'; S = HERE/'inherited'
scope = dict(np=np, cKDTree=cKDTree, Path=Path, sha=sha, dump=dump, now=now, subprocess=subprocess, time=time, BASE=BASE, S=S)
fit_normals, = functions('geometry.py', ['fit_normals'], scope)
build, run = functions('cylinder.py', ['build', 'run'], scope)
KEYS = ['patch_id', 'building', 'kind', 'area', 'raw_centre', 'centre', 'normal', 'tangent1', 'tangent2', 'roof_like', 'surf', 'face_ext', 'source_patch', 'source_extra', 'normal_defined', 'roof_type', 'holdout', 'u_mvs', 'mvs_a_status', 'u_prior']
def buildings():
    return {r['building']: r for r in json.loads((O/'stage0/buildings.json').read_text())['rows'] if r['in_scope']}
def load_tile(tile, prior):
    parts = []
    for split, root in [('development', W/'patch_values'), ('holdout', W/'holdout/patch_values')]:
        p = root/f'{tile}__{prior}__R1.5.npz'
        if p.exists():
            z = loadz(p, [k for k in KEYS if k != 'u_prior' or prior == 'ALS']); z['split'] = np.full(len(z['kind']), split); parts.append(z)
    if not parts: return None
    return {k: np.concatenate([q[k] for q in parts]) for k in parts[0]}
def main(tile):
    cfg(); B = buildings(); T = Timer()
    BASE.mkdir(parents=True, exist_ok=True); (O/'tmp').mkdir(exist_ok=True)
    if not (BASE/'cylinders').exists(): build()
    for prior in ['LoD2', 'ALS']:
        dest = O/'geometry_raw'/f'{tile}__{prior}.npz'
        if dest.exists(): continue
        d = load_tile(tile, prior)
        if d is None: continue
        keep = np.isin(d['building'], list(B)); d = {k: v[keep] for k, v in d.items()}; N = len(d['kind'])
        if N == 0: continue
        d['widen0_index'] = np.array([int(s.rsplit(':', 1)[1]) for s in d['patch_id']], np.int64)
        d['region'] = np.array([B[b]['search_region'] for b in d['building']])
        d['group'] = np.array([B[b]['group'] for b in d['building']])
        sh = np.array([B[b]['als_shift_m'] for b in d['building']], float) if prior == 'ALS' else np.zeros((N, 3))
        d['shift_m'] = sh; d['widen0_centre'] = d.pop('centre'); d['centre'] = d['raw_centre'] + sh; d['old_normal'] = d['normal'].copy()
        d['widen0_same_centre'] = np.all(d['centre'] == d['widen0_centre'], 1)
        if prior == 'ALS':
            raw = np.fromfile(W/'inputs/points'/tile/'als.bin', dtype=[('x', '<f8'), ('y', '<f8'), ('z', '<f8'), ('cls', 'u1'), ('multi', 'u1')])
            A = np.c_[raw['x'], raw['y'], raw['z']][np.isin(raw['cls'], [2, 6])]; del raw
            nf = fit_normals(A, d['raw_centre']); d.update(nf); T.mark('normals')
            tmp = O/'tmp'/f'als_{tile}.npy'; np.save(tmp, A); del A
            v = np.array(run(tmp, d['raw_centre'], np.nan_to_num(d['normal']), [.75], O/'cylinders'/f'{tile}__ALS_prior.bin')); tmp.unlink()
            d['prior_n'] = v[:, 1, 0, 0].astype(int); d['prior_height_m'] = np.where(d['prior_n'] >= 4, v[:, 1, 0, 1], np.nan)
            d['prior_height_m'][~np.isfinite(d['normal']).all(1)] = np.nan
            d['u_prior_widen0'] = d.pop('u_prior').astype(float)
        else:
            d['prior_n'] = np.full(N, -1); d['prior_height_m'] = np.where(np.isfinite(d['normal']).all(1), 0., np.nan)
        pts = WI/'points'/tile/'mvs_a_xyz.npy'
        v = np.array(run(pts, d['centre'], np.nan_to_num(d['normal']), [.075, .125], O/'cylinders'/f'{tile}__{prior}_mvs.bin'))
        ri = np.where((d['kind'] == 2) & (prior == 'LoD2'), 1, 0); hi = np.where(d['kind'] == 1, 1, 0); ii = np.arange(N); a = v[ii, hi, ri, :]
        d.update(n=a[:, 0].astype(int), mvs_mean_m=a[:, 1], mvs_median_m=a[:, 2], mvs_sd_m=a[:, 3], mvs_face_m=a[:, 5], n5=v[ii, 0, ri, 0].astype(int), n10=v[ii, 1, ri, 0].astype(int), d10_m=v[ii, 1, ri, 1] - d['prior_height_m'])
        bad = ~np.isfinite(d['normal']).all(1); d['n'][bad] = -1; d['n5'][bad] = -1; d['n10'][bad] = -1
        d['d_m'] = d['mvs_mean_m'] - d['prior_height_m']; d['u_mvs_widen0'] = d.pop('u_mvs').astype(float)
        rt = cfg()['geometry']['sigma_P']['LoD2_roof_by_roof_type']
        d['sigma_P_lod2_m'] = np.array([rt.get(str(x), rt['other']) if k == 1 else .144 for x, k in zip(d['roof_type'], d['kind'])]) if prior == 'LoD2' else np.full(N, np.nan)
        savez(dest, **d)
        rec = dict(at=now(), tile=tile, prior=prior, count=N, area_m2=float(d['area'].sum()), buildings=len(set(d['building'])), widen0_same_centre=int(d['widen0_same_centre'].sum()),
                   n_ge4=int((d['n'] >= 4).sum()), seconds=T.mark(prior), GT_read=False, scientific_verdict=None)
        dump(dest.with_suffix('.json'), rec); print('GEOMETRY', json.dumps(rec), flush=True)
if __name__ == '__main__':
    for t in sys.argv[1:]: main(t)
