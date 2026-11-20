"""가시성 검사 다시 냄 (발주 6절: '가시성 검사는 그 방법에서 살아남은 화소만 남긴 깊이 지도로 한다'). 참값 읽지 않음. CPU.
JC s2_sight.py 와 같은 절차·같은 상속 함수(test_groups, nearest, fill_median). 바뀌는 것: n5·n10·u_M = mf2 의 그 방법 값, 깊이 지도 = 살아남은 화소만.
사용: mf3_sight.py <method> <prior>"""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_mvsfilter_v1')
from mfcommon import *
import mfcommon as MC
sys.path.insert(0, '/repo/scripts/phd/main_judgecheck_v2'); sys.path.insert(1, '/repo/scripts/phd/main_judgecheck_v2/inherited')
from inherit import functions
from scipy.spatial import cKDTree
import warnings
from photo_cameras import Cameras
scope = dict(np=np, cKDTree=cKDTree, warnings=warnings, sha=sha)
nearest, = functions('main_target_v1__disappearance_r7.py', ['nearest'], scope)
test_groups, = functions('main_target_v1__disappearance_core_r7.py', ['test_groups'], scope)
fill_median, = functions('main_target_v1__target_rules.py', ['fill_median'], dict(np=np))

def main(method, prior):
    MC.cfg(); T = Timer(); parts = []; offsets = []; n = 0; dest = O/'sight'/method
    if (dest/f'{prior}.complete.json').exists(): return
    for p in sorted((JC/'geometry_raw').glob(f'*__{prior}.npz')):
        tile = p.stem.split('__')[0]
        g = loadz(p, ['patch_id', 'centre', 'kind', 'area', 'building', 'sigma_P_lod2_m'] + (['u_prior_widen0'] if prior == 'ALS' else []))
        m = loadz(O/'patch'/method/f'{tile}.npz', [f'{prior}__patch_id', f'{prior}__n5', f'{prior}__n10', f'{prior}__u_M'])
        assert np.array_equal(m[f'{prior}__patch_id'], g['patch_id'])
        raw_sigma = np.sqrt(g['u_prior_widen0']**2 + .0275**2) if prior == 'ALS' else g['sigma_P_lod2_m']
        parts.append(dict(patch_id=g['patch_id'], centre=g['centre'], kind=g['kind'], area=g['area'], building=g['building'], n5=m[f'{prior}__n5'], n10=m[f'{prior}__n10'],
                          u=m[f'{prior}__u_M'].astype(float), raw_sigma=raw_sigma))
        offsets.append((p.name, n, n + len(g['kind']))); n += len(g['kind'])
    d = {k: np.concatenate([q[k] for q in parts]) for k in parts[0]}; del parts
    groups = np.char.add(np.char.add(d['building'].astype(str), ':'), d['kind'].astype(str))
    d['sigma_p'], sigma_replaced, _ = fill_median(d['raw_sigma'], groups, positive=True)
    d['u_replaced'] = np.zeros(n, bool)
    d['region'] = np.where(((d['n5'] >= 0) & (d['n5'] < 4)) | ((d['n10'] >= 0) & (d['n10'] < 4)), 0, 1).astype('i1')
    units, d['unit'] = np.unique(d['building'], return_inverse=True)
    tested = d['region'] == 0; donors = np.isfinite(d['u'])
    bad_units = [i for i in np.unique(d['unit'][tested]) if not donors[d['unit'] == i].any()]
    unavailable = tested & np.isin(d['unit'], bad_units); d['region'][unavailable] = 1
    cam = Cameras(); cameras = [dict(name=nm, W=1024, H=741, K=cam.K, W2C=cam.M[j]) for j, nm in enumerate(cam.names)]
    names = json.loads((W/'image_split.json').read_text())['train']; assert names == cam.names
    M = None if method == 'none' else np.load(O/'masks'/f'{method}.npy'); idx = {nm: i for i, nm in enumerate(names)}
    def read(name):
        p = WS/'stereo/depth_maps'/f'{name}.geometric.bin'
        if not p.exists(): return np.full((741, 1024), np.nan, 'f4'), np.zeros((741, 1024), 'u1'), []
        v = read_depth(p).copy()
        if M is not None:
            keep = np.unpackbits(np.asarray(M[idx[name]]), count=H*Wd).astype(bool).reshape(H, Wd); v[~keep] = 0
        return v, (np.isfinite(v) & (v > 0)).astype('u1'), [p]
    result, record = test_groups(d, cameras, read)
    for name, l, r in offsets:
        out = {k: v[l:r] for k, v in result.items()}; out['patch_id'] = d['patch_id'][l:r]; out['sight_unavailable'] = unavailable[l:r]; out['tested'] = tested[l:r]
        out['free10'] = out['disappeared'] & (d['n10'][l:r] >= 0) & (d['n10'][l:r] < 4); out['free5'] = out['disappeared'] & (d['n5'][l:r] >= 0) & (d['n5'][l:r] < 4)
        savez(dest/name, **out)
    record.pop('files', None); record.update(at=now(), method=method, prior=prior, patches=n, tested=int(tested.sum()), unavailable=int(unavailable.sum()), unavailable_buildings=len(bad_units),
                                             seconds=T.s(), GT_read=False, scientific_verdict=None)
    dump(dest/f'{prior}.complete.json', record); print('SIGHT', method, prior, round(record['seconds']), int(tested.sum()), int(result['disappeared'].sum()), flush=True)

if __name__ == '__main__': main(sys.argv[1], sys.argv[2])
