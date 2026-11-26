"""덧붙임 1 2절: 패치마다 목표 높이 후보와 그 높이의 목표 맞음(참값은 target_check 에서만).
1 ②→③ 길의 h_M: ③ 시작 점(② 지나감 화소, g6 과 같은 need2 패치)을 judgevis fuse 로 다시 돌려 점마다 일관됨을 얻고(패치마다 수가 step3 저장값과 같은지 점검),
  그 화소를 깊이 지도(카메라 z)로 3차원으로 옮겨 패치 법선 거리(사전 정보 면 = 0)를 구함. h_M3c = 일관된 점 평균, h_M3a = 모든 시작 점 평균.
2 높이 후보 17(본 τ): 0 | 영상 d(길이 3 x 대푯값 2) | 섞음(같은 6) | h_M3c | h_M3a | 저장 mvs_mean_m(학습 h_M) | 저장 값 섞음.
  섞음 = d·σ_P² / (σ_P² + u_M²) (학습 코드 targets.py:18, h_P = 0). τ: 0 -> τ_P, 영상류 -> τ_I, 섞음 -> max(τ_P, τ_I).
3 문턱 곡선(τ 0.10~1.00, 모든 τ 같음): 높이 d 본·섞음 본·h_M3c·h_M3a·저장·저장 섞음(높이 0 은 정답의 n_b0 와 같아 그 값을 씀).
나오는 것: work/ga3/heights_<prior>.npz. 사용: GT_STAGE=ga3 g14_heights.py"""
from common import *
import target_check as TC
from g11_figs import read_depth
NAMES = ['0'] + [f'd_{rp}_{h}' for h in range(3) for rp in ['mean', 'med']] + [f'mix_{rp}_{h}' for h in range(3) for rp in ['mean', 'med']] + ['hM3c', 'hM3a', 'cur', 'curmix']
CURVE = ['d_mean_2', 'mix_mean_2', 'hM3c', 'hM3a', 'cur', 'curmix']
def step2_heights(prior, S1, S3, C2):
    """need2 패치의 ② 지나감 화소를 다시 fuse -> 점마다 일관됨, 깊이로 옮긴 점의 법선 거리."""
    N = len(S1['patch_index']); pp = C2['pass_pix']; m2 = S3['need2'][pp[:, 0]]; st = pp[m2][:, 1:].astype(np.int32); own = pp[m2][:, 0]
    key = st[:, 0].astype(np.int64)*(1024*741) + st[:, 1]; uk, inv = np.unique(key, return_inverse=True); us = np.c_[(uk // (1024*741)).astype(np.int32), (uk % (1024*741)).astype(np.int32)]
    sb = O/'tmp'/f'fz2_{prior}.bin'; ob = O/'tmp'/f'fz2_{prior}.out'; np.ascontiguousarray(us, '<i4').tofile(sb)
    subprocess.run([str(VBIN), 'fuse', str(VIS/'cams.bin'), str(VIS/'maps.txt'), str(VIS/'overlap.bin'), str(sb), str(len(us)), str(ob)], check=True, env=dict(os.environ, OMP_NUM_THREADS='30'), stderr=subprocess.DEVNULL)
    R = np.fromfile(ob, '<i4').reshape(-1, 3); sb.unlink(); ob.unlink(); cons_u = R[:, 0] == 1
    h = np.fromfile(VIS/'cams.bin', '<i4', 3); Cm = np.fromfile(VIS/'cams.bin', '<f8', offset=12).reshape(h[0], 16); W = int(h[1]); maps = [l.split('\t')[0] for l in (VIS/'maps.txt').read_text().splitlines()]
    Xu = np.full((len(us), 3), np.nan)
    for im in np.unique(us[:, 0]):
        m = us[:, 0] == im; row, col = np.divmod(us[m, 1], W); Dd = read_depth(maps[im])[row, col].astype(np.float64); Rm = Cm[im, :9].reshape(3, 3); tt = Cm[im, 9:12]
        ray = np.c_[(col - Cm[im, 14])/Cm[im, 12], (row - Cm[im, 15])/Cm[im, 13], np.ones(len(row))]; Y = ray*Dd[:, None]; X = (Y - tt)@Rm; X[~(Dd > 0)] = np.nan; Xu[m] = X
    P = loadz(inp('patches', prior=prior), ['centre', 'normal', 'prior_height_m']); ids = S1['patch_index']; n = np.nan_to_num(P['normal'][ids]); ref = P['centre'][ids] + np.nan_to_num(P['prior_height_m'][ids])[:, None]*n
    X = Xu[inv]; tn = np.einsum('ij,ij->i', X - ref[own], n[own]); cons = cons_u[inv]; ok = np.isfinite(tn)
    cnt_c = np.bincount(own, weights=cons, minlength=N); same = bool(np.array_equal(cnt_c, S3['from2_cons']))
    sc = np.bincount(own[ok & cons], weights=tn[ok & cons], minlength=N); nc = np.bincount(own[ok & cons], minlength=N); sa = np.bincount(own[ok], weights=tn[ok], minlength=N); na = np.bincount(own[ok], minlength=N)
    with np.errstate(invalid='ignore', divide='ignore'): return np.where(nc > 0, sc/nc, np.nan), np.where(na > 0, sa/na, np.nan), dict(cons_counts_equal_step3=same, starts=len(st), unique=len(us), no_depth=int((~ok).sum()))
def main():
    c = cfg(); build_vis(); T = Timer(); curve = c['truth']['threshold_curve_m']
    for prior in PRIORS:
        dest = O/'work'/STAGE/f'heights_{prior}.npz'
        if dest.exists(): print('exists', dest); continue
        S1 = loadz(O/'work'/STAGE/f'step1_{prior}.npz', ['patch_index', 'd_mean', 'd_med', 'u_M', 'sigma_P', 'prior_height', 'cur_mean']); S3 = loadz(O/'work'/STAGE/f'step3_{prior}.npz'); C2 = loadz(O/'work'/STAGE/f'step2_{prior}.npz', ['patch_index', 'pass_pix'])
        idx = S1['patch_index']; N = len(idx); kind = loadz(inp('patches', prior=prior), ['kind'])['kind'][idx]
        hM3c, hM3a, rec3 = step2_heights(prior, S1, S3, C2); progress(f'②→③ h_M {PN[prior]}: {rec3}'); print('H3', prior, rec3, flush=True)
        sP2 = S1['sigma_P']**2; uM2 = S1['u_M']**2; wmix = sP2/(sP2 + uM2); cur = S1['cur_mean'] - S1['prior_height']
        Hs = {'0': np.zeros(N)}
        for h in range(3):
            for rp, key in [('mean', 'd_mean'), ('med', 'd_med')]: Hs[f'd_{rp}_{h}'] = S1[key][:, h]; Hs[f'mix_{rp}_{h}'] = S1[key][:, h]*wmix
        Hs.update(hM3c=hM3c, hM3a=hM3a, cur=cur, curmix=cur*wmix)
        tP = np.array([tauP(prior, k) for k in kind]); tI = tauI(); tau = {k: (tP if k == '0' else (np.maximum(tP, tI) if 'mix' in k else np.full(N, tI))) for k in NAMES}
        H = np.c_[[Hs[k] for k in NAMES]].T; TAU = np.c_[[tau[k] for k in NAMES]].T; ok, cnt = TC.check(prior, idx, H, TAU, 'main'); progress(f'목표 맞음(본 τ) {PN[prior]}: {T.s():.0f} s')
        Hc = np.repeat(np.c_[[Hs[k] for k in CURVE]].T, len(curve), axis=1); Tc = np.tile(np.repeat(curve, 1)[None, :], (N, len(CURVE)))
        okc, _ = TC.check(prior, idx, Hc, Tc, 'curve'); okc = okc.reshape(N, len(CURVE), len(curve)); progress(f'목표 맞음(곡선) {PN[prior]}: {T.s():.0f} s')
        savez(dest, patch_index=idx, names=np.array(NAMES), H=H, TAU=TAU, ok=ok, cnt=cnt, curve_names=np.array(CURVE), curve_tau=np.array(curve), ok_curve=okc)
        dump(dest.with_suffix('.json'), dict(at=now(), prior=prior, names=NAMES, step3_heights=rec3, finite={k: int(np.isfinite(Hs[k]).sum()) for k in NAMES}, ok_share={k: float(ok[:, i].mean()) for i, k in enumerate(NAMES)}, seconds=T.s(), scientific_verdict=None))
if __name__ == '__main__': main()
