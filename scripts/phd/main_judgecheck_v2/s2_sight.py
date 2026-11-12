"""시선 검사 (TARGET-v1 덧붙임 2 r7; JUDGECHECK-v1 sight_reply2.py 의 건물 단위 test_groups 와 nearest, 바이트 같은 복사). 참값 읽지 않음.
검사 대상: 0<=n5<4 또는 0<=n10<4. u = 본값 R1.5 u_M(없으면 건물 중앙값), σ_p = LoD2 표 / ALS sqrt(u_prior^2+0.0275^2) 건물:지붕 중앙값 채움(TARGET target_rules.uncertainties).
깊이: WIDEN0 학습 819장 COLMAP 기하 단계 깊이 (깊이>0 = conf)."""
from common import *
from inherit import functions
from scipy.spatial import cKDTree
import warnings
sys.path.insert(0, str(HERE/'inherited'))
from photo_cameras import Cameras, read_depth
scope = dict(np=np, cKDTree=cKDTree, warnings=warnings, sha=sha)
nearest, = functions('main_target_v1__disappearance_r7.py', ['nearest'], scope)
test_groups, = functions('main_target_v1__disappearance_core_r7.py', ['test_groups'], scope)
fill_median, = functions('main_target_v1__target_rules.py', ['fill_median'], dict(np=np))
def main(prior):
    cfg(); T = Timer(); parts = []; offsets = []; n = 0
    for p in sorted((O/'geometry_raw').glob(f'*__{prior}.npz')):
        g = loadz(p, ['patch_id', 'centre', 'kind', 'area', 'building', 'n5', 'n10', 'sigma_P_lod2_m'] + (['u_prior_widen0'] if prior == 'ALS' else []))
        b = loadz(O/'ring/base'/p.name, ['u_mvs_R1p5'])
        raw_sigma = np.sqrt(g['u_prior_widen0']**2 + .0275**2) if prior == 'ALS' else g['sigma_P_lod2_m']
        parts.append(dict(patch_id=g['patch_id'], centre=g['centre'], kind=g['kind'], area=g['area'], building=g['building'], n5=g['n5'], n10=g['n10'], u=b['u_mvs_R1p5'].astype(float), raw_sigma=raw_sigma))
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
    if unavailable.any(): issue(f'시선 검사 {prior}: u_M 이 하나도 없는 건물 {len(bad_units)}동의 검사 대상 {int(unavailable.sum())}개({float(d["area"][unavailable].sum()):.1f} m²)는 확인 불가(결측으로 남음).')
    cam = Cameras(); cameras = [dict(name=nm, W=1024, H=741, K=cam.K, W2C=cam.M[j]) for j, nm in enumerate(cam.names)]
    def read(name):
        p = W/'mvs/full/stereo/depth_maps'/f'{name}.geometric.bin'
        if not p.exists(): return np.full((741, 1024), np.nan, 'f4'), np.zeros((741, 1024), 'u1'), []
        v = read_depth(p); return v, (np.isfinite(v) & (v > 0)).astype('u1'), [p]
    result, record = test_groups(d, cameras, read)
    for name, l, r in offsets:
        out = {k: v[l:r] for k, v in result.items()}; out['patch_id'] = d['patch_id'][l:r]; out['sight_unavailable'] = unavailable[l:r]; out['tested'] = tested[l:r]
        out['free10'] = out['disappeared'] & (d['n10'][l:r] >= 0) & (d['n10'][l:r] < 4); out['free5'] = out['disappeared'] & (d['n5'][l:r] >= 0) & (d['n5'][l:r] < 4)
        out['sigma_p_sight'] = d['sigma_p'][l:r]; out['sigma_p_replaced'] = sigma_replaced[l:r]
        savez(O/'sight'/name, **out)
    record.pop('files', None); record.update(at=now(), prior=prior, patches=n, tested=int(tested.sum()), unavailable=int(unavailable.sum()), seconds=T.mark('end'), GT_read=False, scientific_verdict=None)
    dump(O/'sight'/f'{prior}.complete.json', record); print('SIGHT_COMPLETE', prior, round(record['seconds']), int(result['disappeared'].sum()), flush=True)
if __name__ == '__main__': main(sys.argv[1])
