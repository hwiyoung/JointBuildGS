"""덧붙임 2 1절: 판단 평가가 읽는 mvs_mean_m(JUDGEPROBE patch_<prior>.npz, step1 cur_mean)이 학습이 받는 값(main_finaltrain_v1 targets/<지역>__<prior>.npz 의 mvs_mean_m, targets.py:12·18·24 입력)과 같은지 패치 중심으로 맞대 본다.
u_M(JUDGEPROBE)와 u_mvs(학습)도 맞댐. 참값 안 읽음. 사용: GT_STAGE=ga3 run.sh g19_mvs_source.py"""
from common import *
FT = PH/'main_finaltrain_v1/PHD-MAIN-FINALTRAIN-v1/targets'
def main():
    rec = dict(at=now(), scientific_verdict=None, training_code='scripts/phd/main_finaltrain_v1/targets.py: hm = mvs_mean_m (12줄), 두 자료 h = (h_P·u_M² + h_M·σ_P²)/(u_M² + σ_P²) (18줄), 영상(고침) h = h_M (20줄)')
    for prior in PRIORS:
        S1 = loadz(O/'work'/STAGE/f'step1_{prior}.npz', ['patch_index', 'cur_mean', 'u_M', 'sigma_P', 'prior_height'])
        P = loadz(inp('patches', prior=prior), ['centre']); cen = P['centre'][S1['patch_index']]
        key = {tuple(np.round(c, 4)): i for i, c in enumerate(cen)}; hit = np.zeros(len(cen), bool); dm = []; du = []; ds = []; nboth = 0; nan_mis = 0
        for f in sorted(FT.glob(f'*__{prior}.npz')):
            t = loadz(f, ['centre', 'mvs_mean_m', 'u_mvs', 'sigma_P_m'])
            for j, c in enumerate(t['centre']):
                i = key.get(tuple(np.round(c, 4)))
                if i is None: continue
                hit[i] = True; a, b = S1['cur_mean'][i], t['mvs_mean_m'][j]
                if np.isfinite(a) != np.isfinite(b): nan_mis += 1
                elif np.isfinite(a): nboth += 1; dm.append(abs(a - b)); du.append(abs(S1['u_M'][i] - t['u_mvs'][j]) if np.isfinite(S1['u_M'][i]) and np.isfinite(t['u_mvs'][j]) else 0.); ds.append(abs(S1['sigma_P'][i] - t['sigma_P_m'][j]) if np.isfinite(S1['sigma_P'][i]) and np.isfinite(t['sigma_P_m'][j]) else 0.)
        rec[prior] = dict(patches=len(cen), matched=int(hit.sum()), both_finite=nboth, finite_mismatch=nan_mis, max_abs_diff_mvs_mean_m=float(max(dm)) if dm else None, share_within_1mm=float(np.mean(np.array(dm)<=1e-3)) if dm else None, median_abs_diff=float(np.median(dm)) if dm else None, q99_abs_diff=float(np.quantile(dm,.99)) if dm else None, share_u_within_1mm=float(np.mean(np.array(du)<=1e-3)) if du else None, max_abs_diff_u=float(max(du)) if du else None, max_abs_diff_sigmaP=float(max(ds)) if ds else None,
                          cur_mean_finite=int(np.isfinite(S1['cur_mean']).sum()), target_files=[f.name for f in sorted(FT.glob(f'*__{prior}.npz'))])
        print(prior, rec[prior], flush=True)
    dump(D/'tables/마/t0_mvs_source.json', rec); progress(f'덧붙임 2 mvs_mean_m 출처 맞댐: {rec}')
if __name__ == '__main__': main()
