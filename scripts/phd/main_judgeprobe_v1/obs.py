"""후보 관측 (설정 candidates). 패치 표에서 셈."""
from common import *
OBS = ['n', 'mvs_sd', 'u_M', 'fit_nmad', 'fit_count', 'plane_angle', 's_P', 's_M', 'sM_minus_sP', 'views_min', 'views_P', 'views_M', 'texture_min', 'texture_P', 'texture_M',
       'mask_frac_min', 'mask_P', 'mask_M', 'd_over_L', 'mean_minus_median', 'face_minus_mean', 'n10_over_n']
OBS_NO = {'n': '1', 'mvs_sd': '2', 'u_M': '3', 'fit_nmad': '4', 'fit_count': '5', 'plane_angle': '6', 's_P': '7', 's_M': '8', 'sM_minus_sP': '9', 'views_min': '10', 'views_P': '10a', 'views_M': '10b',
          'texture_min': '11', 'texture_P': '11a', 'texture_M': '11b', 'mask_frac_min': '12', 'mask_P': '12a', 'mask_M': '12b', 'd_over_L': '13', 'mean_minus_median': '14', 'face_minus_mean': '15', 'n10_over_n': '16'}
OBS_KO = {'n': '원통 안 점 수', 'mvs_sd': '원통 안 높이 표준 편차', 'u_M': 'u_M', 'fit_nmad': '면 맞춤 잔차 NMAD', 'fit_count': '면 맞춤 점 수', 'plane_angle': '영상 면·사전 법선 각', 's_P': 's_P', 's_M': 's_M',
          'sM_minus_sP': 's_M − s_P', 'views_min': '고른 사진 수(작은 쪽)', 'views_P': '고른 사진 수(사전)', 'views_M': '고른 사진 수(영상)', 'texture_min': '무늬 세기(작은 쪽)', 'texture_P': '무늬 세기(사전)',
          'texture_M': '무늬 세기(영상)', 'mask_frac_min': '남은 표본 비율(작은 쪽)', 'mask_P': '남은 표본 비율(사전)', 'mask_M': '남은 표본 비율(영상)', 'd_over_L': '|d| ÷ L', 'mean_minus_median': '평균 − 중앙값',
          'face_minus_mean': '바깥면 높이 − 평균', 'n10_over_n': 'n10 ÷ n'}
def observations(d):
    with np.errstate(invalid='ignore', divide='ignore'):
        o = dict(n=d['n'].astype(float), mvs_sd=d['mvs_sd_m'], u_M=d['u_M'], fit_nmad=d['fit_nmad'], fit_count=d['fit_count'], plane_angle=d['plane_angle'], s_P=d['s_P'], s_M=d['s_M'], sM_minus_sP=d['s_M'] - d['s_P'],
                 views_min=np.fmin(d['views_P'], d['views_M']), views_P=d['views_P'], views_M=d['views_M'], texture_min=np.fmin(d['texture_P'], d['texture_M']), texture_P=d['texture_P'], texture_M=d['texture_M'],
                 mask_frac_min=np.fmin(d['mask_P'], d['mask_M']), mask_P=d['mask_P'], mask_M=d['mask_M'], d_over_L=np.abs(d['d_for_check'])/d['L_m'], mean_minus_median=d['mvs_mean_m'] - d['mvs_median_m'],
                 face_minus_mean=d['mvs_face_m'] - d['mvs_mean_m'], n10_over_n=d['n10']/d['n'])
    for k in ['views_min', 'texture_min', 'mask_frac_min']:   # fmin 은 한쪽 NaN 이면 다른 쪽을 냄 -> 둘 다 있을 때만
        a, b = {'views_min': ('views_P', 'views_M'), 'texture_min': ('texture_P', 'texture_M'), 'mask_frac_min': ('mask_P', 'mask_M')}[k]
        o[k] = np.where(np.isfinite(o[a]) & np.isfinite(o[b]), o[k], np.nan)
    return o
def unit_mask(d, unit):
    prior, kind = UNITS[unit]; return d['kind'] == kind
def thresholds(d, o, unit_m, inside):
    """탐색 지역 x 단위마다 한계 안 패치의 넓이 가중 5 %, 95 % (참값 없음). 'none' = 일곱 지역 합침. 반환 lo, hi (패치마다), 표."""
    lo = {k: np.full(len(d['kind']), np.nan) for k in o}; hi = {k: np.full(len(d['kind']), np.nan) for k in o}; rows = []
    reg = d['region']
    for r in REGIONS + ['none']:
        pool = unit_m & inside & ((reg == r) if r != 'none' else np.isin(reg, REGIONS)); tgt = unit_m & (reg == r)
        for k, x in o.items():
            a, b = wq(x[pool], d['area'][pool], .05), wq(x[pool], d['area'][pool], .95); lo[k][tgt] = a; hi[k][tgt] = b
            rows.append(dict(region=r, obs=k, lo5=a, hi95=b, pool_n=int((pool & np.isfinite(x)).sum())))
    return lo, hi, rows
