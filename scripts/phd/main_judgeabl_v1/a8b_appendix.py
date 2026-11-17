"""본 보고서 부록(7.1의 2·3·5 가운데 본문 1만 자에 넣지 못한 것): 요약 표의 모든 칸, 값 훑기 전체, 판마다 쓴 값. 표 파일에서 만든다."""
from common import *
import pandas as pd
TAB = D/'tables'; CN = [CASE[c] for c in CASES]
def f(x, k=2):
    try: x = float(x)
    except (TypeError, ValueError): return str(x)
    return '' if not np.isfinite(x) else f'{x:.{k}f}'
def md(df, cols, heads=None):
    h = heads or cols; out = ['| ' + ' | '.join(h) + ' |', '|' + '---|'*len(h)]
    for _, r in df.iterrows(): out.append('| ' + ' | '.join(f(r[c], 1) if isinstance(r[c], (float, np.floating)) else str(r[c]) for c in cols) + ' |')
    return '\n'.join(out)
def main():
    S = pd.read_csv(TAB/'s_main_summary.csv'); W = pd.read_csv(TAB/'s_sweep.csv'); PR = pd.read_csv(TAB/'s_photo_refs.csv'); DT = pd.read_csv(TAB/'s_det3_limits.csv'); VN = pd.read_csv(TAB/'s_variant_notes.csv')
    A = pd.read_csv(TAB/'s_all_variants.csv')
    nm = A[(A.scope == '전체') & (((A.prior == 'LoD2') & (A.surface == '모두')) | (A.prior == 'ALS'))].set_index(['prior', 'variant'])
    S['made'] = [' / '.join(f(nm.loc[(p, v), f'made_{c}'], 1) for c in CN) if (p, v) in nm.index else '' for p, v in zip(S.prior, S.variant)]
    S['name'] = [' / '.join(f(nm.loc[(p, v), f'name_{c}'], 1) for c in CN) if (p, v) in nm.index else '' for p, v in zip(S.prior, S.variant)]
    S['ok4'] = [' / '.join(f(r[f'ok_{c}'], 1) for c in CN) for _, r in S.iterrows()]; S['dpp'] = [' / '.join(f(r[f'diff_pp_{c}'], 1) for c in CN) for _, r in S.iterrows()]
    out = ['# 판단 비교·절제 보고 v1 — 부록 (요약 표의 모든 칸, 값 훑기, 판마다 쓴 값)', '',
           '본문(1만 자)에 넣지 못한 7.1의 2·3·5. 값은 표 파일과 같음. 네 경우 = 두 자료 모두 유효 / 사전정보 오류 / 영상 깊이 오류 / 영상 깊이 결측. scientific_verdict: null.', '']
    for p, lab in [('LoD2', 'LoD2 (지붕과 벽 합침)'), ('ALS', '항공 LiDAR (지붕)')]:
        q = S[S.prior == p]
        out += [f'## 부록 1. 요약 표 — {lab}', '', md(q, ['variant', 'ok4', 'ok_전체', '요약 가 평균', '요약 나 최솟값', '요약 나 경우', '요약 다 최대 격차', 'dpp', 'building_diff_median_pp'],
                                                    ['판', '목표 맞음 네 경우', '전체', '요약 가', '요약 나', '요약 나 경우', '요약 다', '본값과의 차이 %p 네 경우', '건물 차이 중앙값 %p']), '',
                f'### 판정 이름 맞음 %·판정이 만든 오차 % — {lab}', '', md(q, ['variant', 'name', 'made'], ['판', '판정 이름 맞음 네 경우', '판정이 만든 오차 네 경우']), '']
    W = W[((W.prior == 'LoD2') & (W.surface == '모두')) | (W.prior == 'ALS')].copy(); W['ok4'] = [' / '.join(f(r[f'ok_{c}'], 1) for c in CN) for _, r in W.iterrows()]
    out += ['## 부록 2. 값 훑기 (3.1) 전체', '', md(W, ['prior', 'variant', 'ok4', 'ok_전체', '요약 가 평균', '요약 나 최솟값', '요약 나 경우', '요약 다 최대 격차'], ['사전 정보', '판', '목표 맞음 네 경우', '전체', '요약 가', '요약 나', '요약 나 경우', '요약 다']), '']
    out += ['## 부록 3. 판마다 쓴 값', '', '### 기준 t와 분위 값(기존 3), c_아래·c_위(식별 5): 탐색 지역 x 종류, t와 같은 사진 점 표본', '',
            md(PR, ['prior', 'kind', 'region', 't', 't_q1', 't_q5', 't_q10', 't_q25', 't_q50', 'c_lo', 'c_hi', 'sample_count']), '',
            '### 지역 하나의 한계(검출 3): 넓이 가중 중앙값 m, NMAD, 한계 = 1.96 NMAD (m)', '', md(DT, ['prior', 'kind', 'region', 'median_d_m', 'nmad_m', 'limit_m', 'pool_patches']), '',
            '### 고정 문턱', '', '기존 1 T = 0.1, 0.2, 0.3, 0.5, 0.75, 1.0, 1.5, 2.0 m; 검출 1·2 = 0.5·1.0 m; 기존 5 T = 0.5 m 또는 저장된 L. 기존 2 = 배수 1.0, 1.645, 1.96, 2.576, 3.29 x (√(u_M² + σ_P² + σ_W²) + |r|), JC 저장 값.', '',
            '### 결합(기존 4) 문턱', '', 'JUDGEAPPLY 저장 색 문턱 25 (in_change_25), 판정 줄 `scripts/phd/main_baselines_v1/mvsfuse/detect.py:315-353,355-364,725-732,770-772`, 규칙 `mf_common.py:56-101`.', '',
            '### 넓이 기록', '', md(VN.fillna(''), [c for c in ['prior', 'variant', 'L_missing_area_m2', 'agree_without_uM_area_m2', 'outside_area_m2', 'inside_area_m2', 'changed_area_m2'] if c in VN.columns]), '']
    (D/'판단비교절제_보고_v1_부록.md').write_text('\n'.join(out) + '\n'); print('APPENDIX', sum(len(x) for x in out))
if __name__ == '__main__': main()
