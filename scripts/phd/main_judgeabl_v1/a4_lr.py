"""4.6 참고 줄: 참값으로 학습한 결합 (방법의 후보 아님). 세 부류 로지스틱 회귀(넓이 가중, 표준화), 건물 단위 5겹(씨앗 20261117).
학습 = n >= 4·MVS 높이 있음·섞이지 않은 패치(JP 정의) 가운데 패치의 경우 0/1/2. 예측 = 같은 조건의 패치 전부(경우 4·네 경우 밖·참값 없음 포함). 시험 겹의 예측만 판정에 씀. 나머지 패치는 본값 판정.
출력: /out/lr_<prior>.npz (region, reason, target_h; 모든 패치), 계수 표."""
from common import *
import importlib.util, pandas as pd
from sklearn.linear_model import LogisticRegression
_s = importlib.util.spec_from_file_location('jpobs', '/repo/scripts/phd/main_judgeprobe_v1/obs.py'); OB = importlib.util.module_from_spec(_s)
sys.modules['common_jp'] = JPC; sys.path.insert(0, '/repo/scripts/phd/main_judgeprobe_v1')
_s.loader.exec_module(OB)
FEAT = ['n', 'mvs_sd', 'u_M', 'fit_nmad', 'fit_count', 'plane_angle', 's_P', 's_M', 'sM_minus_sP', 'views_min', 'texture_min', 'mask_frac_min', 'd_over_L', 'mean_minus_median']   # JP 3.1 의 1~14
def load(prior):
    keys = ['kind', 'area', 'n', 'n10', 'mvs_sd_m', 'u_M', 'fit_nmad', 'fit_count', 'plane_angle', 's_P', 's_M', 'views_P', 'views_M', 'texture_P', 'texture_M', 'mask_P', 'mask_M', 'd_for_check', 'L_m',
            'mvs_mean_m', 'mvs_median_m', 'mvs_face_m', 'prior_height_m', 'normal', 'case', 'mixed', 'building', 'j_region', 'j_reason', 'target_h', 'sigma_P', 'sigma_W']
    return loadz(JP/f'patch_{prior}.npz', keys)
def main():
    T = Timer(); cfg(); P = {p: load(p) for p in ['LoD2', 'ALS']}; X, Y, W, B, idx = [], [], [], [], []
    for pi, (prior, d) in enumerate(P.items()):
        o = OB.observations(d)
        elig = (d['n'] >= 4) & np.isfinite(d['mvs_mean_m']) & np.isfinite(d['prior_height_m']) & np.isfinite(d['normal']).all(1) & ~d['mixed']   # 예측 대상 = n >= 4·섞이지 않은 패치 전부 (11-17 고침: 앞 판은 경우 0·1·2 패치에만 예측)
        m = np.flatnonzero(elig); cols = [o[k][m] for k in FEAT] + [np.full(len(m), float(pi)), (d['kind'][m] == 2).astype(float)]
        X.append(np.column_stack(cols)); Y.append(d['case'][m].astype(int)); W.append(d['area'][m]); B.append(d['building'][m]); idx.append((prior, m))
    X = np.concatenate(X); Y = np.concatenate(Y); TM = np.isin(Y, [0, 1, 2]); W = np.concatenate(W); Bn = np.concatenate(B)
    names = FEAT + ['사전 정보 종류(항공 LiDAR = 1)', '벽 = 1']
    miss = ~np.isfinite(X[:, :len(FEAT)]); med = np.nanmedian(X[:, :len(FEAT)], 0); Xf = X.copy()
    for j in range(len(FEAT)): Xf[miss[:, j], j] = med[j]
    flag_cols = [j for j in range(len(FEAT)) if miss[:, j].any()]; Xf = np.column_stack([Xf] + [miss[:, j].astype(float) for j in flag_cols]); names += [f'{FEAT[j]} 비어 있음' for j in flag_cols]
    ub = np.unique(Bn); rng = np.random.default_rng(20261117); fold_of = dict(zip(ub, rng.permutation(len(ub)) % 5)); fold = np.array([fold_of[b] for b in Bn])
    pred = np.full(len(Y), -1); coefs = []; rows = []
    for k in range(5):
        tr = (fold != k) & TM; te = fold == k
        mu = np.average(Xf[tr], 0, W[tr]); sd = np.sqrt(np.average((Xf[tr] - mu)**2, 0, W[tr])); sd[sd == 0] = 1
        clf = LogisticRegression(C=1.0, max_iter=2000, solver='lbfgs'); clf.fit((Xf[tr] - mu)/sd, Y[tr], sample_weight=W[tr]/W[tr].mean())
        pred[te] = clf.predict((Xf[te] - mu)/sd); coefs.append(clf.coef_)
        rows.append(dict(fold=k, train_patches=int(tr.sum()), test_patches=int(te.sum()), test_labeled=int((te & TM).sum()), test_buildings=int(len(np.unique(Bn[te]))), iterations=int(np.max(clf.n_iter_)), seconds=T.s()))
        print('LR fold', k, round(T.s()), flush=True)
    cm = np.mean(coefs, 0); C_ = pd.DataFrame([dict(input=n, **{f'coef_{CASE[c]}': cm[i, j] for i, c in enumerate([0, 1, 2])}) for j, n in enumerate(names)])
    TAB = D/'tables'; TAB.mkdir(exist_ok=True); C_.to_csv(TAB/'s_ref46_coefficients.csv', index=False); pd.DataFrame(rows).to_csv(TAB/'s_ref46_folds.csv', index=False)
    (TAB/'s_ref46_coefficients.md').write_text('4.6 참고 줄 계수(겹 평균, 표준화 입력). 부류 = 패치의 경우. 참값으로 학습한 참고 줄이며 방법의 후보가 아님.\n\n| 입력 | ' + ' | '.join(f'계수 {CASE[c]}' for c in [0, 1, 2]) + ' |\n|---|---|---|---|\n' +
                                                '\n'.join(f"| {r.input} | " + ' | '.join(f'{v:.3f}' for v in r[1:]) + ' |' for r in C_.itertuples(index=False)) + '\n')
    acc = float(np.average(pred[TM] == Y[TM], weights=W[TM])); off = 0
    for prior, m in idx:
        d = P[prior]; mi = J.VARIANTS.index('method'); reg = d['j_region'][:, mi].copy(); why = d['j_reason'][:, mi].copy(); p = pred[off:off + len(m)]; off += len(m)
        reg[m] = np.array([0, 2, 1])[p]; why[m] = 7
        h = J.target_height(reg, d['prior_height_m'], d['mvs_mean_m'], d['u_M'], d['sigma_P'], d['sigma_W'])
        nm = (reg == 0) & ~np.isfinite(h); h[nm] = .5*(d['prior_height_m'][nm] + d['mvs_mean_m'][nm])
        np.savez(O/f'lr_{prior}.npz', region=reg, reason=why, target_h=h, predicted=np.isin(np.arange(len(reg)), m), agree_without_uM_area_m2=float(d['area'][nm].sum()))
    dump(O/'lr.json', dict(at=now(), patches=len(Y), labeled_patches=int(TM.sum()), predicted_unlabeled_patches=int((~TM).sum()), area_weighted_accuracy=acc, folds=rows, features=names, seconds=T.s(), scientific_verdict=None))
    progress(f'4.6 로지스틱 회귀 끝: 패치 {len(Y)}, 넓이 가중 맞힘 {acc:.4f}, {round(T.s())} 초')
if __name__ == '__main__': main()
