"""덧붙임 1 보충 (11-17 점검 뒤): 확인 1의 4 '어느 반지름도 셋을 만족하지 못하는 넓이와 까닭', 확인 4 '유효 표본 수로 본 건물당 필요한 n'. 참값 없음."""
import sys; sys.path.insert(0, '/repo/scripts/phd/main_judgeabl_v1'); sys.path.insert(0, '/repo/scripts/phd/main_judgeabl_v1/addendum1')
from common import *
import pandas as pd
import b1_checks as B1
TAB = D/'tables/addendum1'; A1 = O/'addendum1'
def main():
    T = Timer(); VS = pd.read_csv(TAB/'variogram_summary.csv'); BD = np.load(A1/'boundary_dist.npz'); rows = []
    La = {r.region: r.L95 for r in VS[VS.unit == '항공 LiDAR 지붕'].itertuples()}
    for prior, kind, lab in B1.UNITS3:
        d = B1.load(prior); dist = BD[prior]; A = d['area']; inl = (d['geometry'] == 0) & (d['kind'] == kind)
        has = inl & np.isfinite(d['m_s0']) & np.isfinite(d['m_nring'])
        L95 = np.array([La.get(r, La['전체']) for r in d['region']])
        ok = {}; fa = {}; fb = {}; fc = {}
        for R, uk in [(1.0, 'u10'), (1.5, 'u_M'), (3.0, 'u30')]:
            N = d['m_nring'] if R == 1.5 else np.minimum(8000, d['m_found']*(R**2 - .25)/(1.5**2 - .25))
            sig = d['m_s0']/np.sqrt(N)*np.sqrt(1 + 4*.25/(R**2 + .25))
            a = (.5 + R)/2 >= L95; b = sig <= d[uk]/3; c = dist >= R
            ok[R] = a & b & c; fa[R] = ~a; fb[R] = ~b; fc[R] = ~c
        none = has & ~(ok[1.0] | ok[1.5] | ok[3.0])
        face_lt = has & (dist < 2*L95 - .5)   # (가)를 만족하는 가장 작은 R(= 2 L95 − 0.5)보다 면이 작음: 어느 R도 (가)와 (다)를 함께 만족 못함
        for reg in REGIONS + ['전체']:
            m = has & ((d['region'] == reg) if reg != '전체' else True); a_ = A[m].sum()
            if not a_: continue
            pc = lambda x: 100*A[m & x].sum()/a_
            rows.append(dict(unit=lab, region=reg, area_m2=float(a_), none_of_radii_pct=pc(none),
                             reason_a_all_radii_pct=pc(fa[1.0] & fa[1.5] & fa[3.0]), reason_b_all_radii_pct=pc(fb[1.0] & fb[1.5] & fb[3.0]), reason_c_all_radii_pct=pc(fc[1.0] & fc[1.5] & fc[3.0]),
                             face_smaller_than_needed_radius_pct=pc(face_lt), needed_radius_for_a_m=float(np.median(2*L95[m] - .5)),
                             only_a_fails_at_1p5_pct=pc(fa[1.5] & ~fb[1.5] & ~fc[1.5]), a_and_c_fail_at_1p5_pct=pc(fa[1.5] & fc[1.5])))
        print('C14', lab, round(T.s()), flush=True)
    B1.write('check1_no_radius', pd.DataFrame(rows), '확인 1의 4: 한계 안 패치(고리 값 있는 것) 가운데 R 1.0·1.5·3.0 어느 것도 (가)(나)(다)를 함께 만족하지 못하는 넓이 비율과 까닭. reason_*_all_radii = 세 반지름 모두에서 그 조건이 깨짐. face_smaller = 면 경계까지 거리 < (가)를 만족하는 가장 작은 반지름(2 L95 − 0.5).')
    b = pd.read_csv(TAB/'check4_buildings.csv'); b['n_needed_eff_basis'] = b['n_needed']*b['n_b']/b['n_eff']; b['meets_eff'] = b['n_b'] >= b['n_needed_eff_basis']
    B1.write('check4_buildings', b, '확인 4: 건물마다 일치 핵심점 n_b, (d − r) NMAD, 표준 오차, 유효 표본 수 n_eff = min(n_b, 넓이 ÷ L50²), σ_W/3 에 필요한 n(n_needed), 유효 표본 수로 본 필요한 n_b(n_needed_eff_basis = n_needed x n_b ÷ n_eff).')
    s = b.groupby('unit').agg(buildings=('n_b', 'size'), n_needed_q50=('n_needed', 'median'), n_needed_q90=('n_needed', lambda x: x.quantile(.9)), n_needed_eff_q50=('n_needed_eff_basis', 'median'),
                              n_needed_eff_q90=('n_needed_eff_basis', lambda x: x.quantile(.9)), meets_100_pct=('meets_100', 'mean'), se_le_sw3_pct=('se_le_sw3', 'mean'), meets_eff_pct=('meets_eff', 'mean')).reset_index()
    B1.write('check4_buildings_summary', s, '확인 4 건물 요약(비율은 0~1).')
    progress(f'덧붙임 1 보충(확인 1의 4, 확인 4 유효 표본) 끝 ({round(T.s())} 초)')
if __name__ == '__main__': main()
