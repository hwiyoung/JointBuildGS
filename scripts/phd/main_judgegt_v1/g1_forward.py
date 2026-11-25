"""단계 1: 정방향 정답 (사전 정보 패치마다). 판단 쪽 값은 읽기만. 참값은 정답을 만드는 데만.
패치마다 (구역의 자기 점 파일):
  영상 원통 = 판단의 원통(패치 중심·법선, 반지름 LoD2 지붕 0.075 / 벽 0.125 / ALS 0.075, 길이 지붕 ±10 / 벽 ±5) 안 영상 점 모두 → raw_n, 법선 거리 중앙값.
    h_M = 중앙값 − 사전 정보 높이(ALS, LoD2 는 0). 바깥 첫 면 규칙 없음. raw_n < 4 이면 영상 없음.
  패치 기둥 = 0.25 × 0.25 m 칸(tangent1, n × tangent1)을 법선으로 늘인 기둥, 기준 0 = 패치 중심 + 사전 정보 높이 × 법선, 지붕 ±10 / 벽 ±5 m.
    참값 점: 모두(n_total), [−τ, τ](n_b0), [h_M − τ, h_M + τ](n_bM), [−1, 1](밀도), 무리(이웃 간격 > 4τ).
사용: GT_STAGE=ga|full g1_forward.py"""
from common import *
import pandas as pd
KEYS = ['tile', 'kind', 'area', 'centre', 'normal', 'tangent1', 'prior_height_m', 'region', 'building', 'place', 'j_region', 'n', 'tiles']
def answer(has, p_ok, m_ok, m_none):
    a = np.full(len(has), 5, np.int8)   # 정답 없음
    a[has & p_ok & m_ok] = 0; a[has & ~p_ok & m_ok] = 1; a[has & p_ok & ~m_ok & ~m_none] = 2; a[has & p_ok & m_none] = 3; a[has & ~p_ok & ~m_ok] = 4
    return a
def main():
    c = cfg(); F = c['forward']; build(); tau = tau_table(); B = buildings(); T = Timer(); recs = {}
    for prior in PRIORS:
        dest = O/'work'/STAGE/f'forward_{prior}.npz'
        if dest.exists(): print('exists', dest); continue
        P = loadz(inp('patches', prior=prior), KEYS); tiles = list(P['tiles']); N = len(P['kind'])
        sc = np.isin(P['building'], list(B)); ids = np.flatnonzero(sc); kind = P['kind']; wall = kind == 2
        key = np.where(wall, f'{prior}_wall', f'{prior}_roof') if prior == 'LoD2' else np.full(N, 'ALS_roof')
        tv = np.array([tau[r][k] for r, k in zip(P['region'][ids], key[ids])]); TAU = np.full(N, np.nan); TAU[ids] = tv
        H = np.where(wall, F['column_half_length_m']['wall'], F['column_half_length_m']['roof']).astype(float)
        rad = np.where(wall & (prior == 'LoD2'), F['image_cylinder_radius_m']['LoD2_wall'], F['image_cylinder_radius_m'][f'{prior}_roof'])
        out = {k: np.full(N, np.nan) for k in ['raw_n', 'mvs_med', 'h_M', 'n_total', 'n_b0', 'n_bM', 'n_dens', 'n_cl']}; out['cl'] = np.full((N, 12), np.nan)
        for ti in np.unique(P['tile'][ids]):
            t0 = T.s(); m = ids[P['tile'][ids] == ti]; t = tiles[ti]; cen, nor = P['centre'][m], P['normal'][m]
            cyl = run('cyl', WI/'points'/t/'mvs_a_xyz.npy', np.c_[cen, np.nan_to_num(nor, nan=0.), rad[m], H[m]], f'cyl_{STAGE}_{prior}_{t}')
            ph = P['prior_height_m'][m]; out['raw_n'][m] = cyl[:, 0]; out['mvs_med'][m] = cyl[:, 1]
            hM = np.where(cyl[:, 0] >= F['min_points'], cyl[:, 1] - ph, np.nan); out['h_M'][m] = hM
            good = np.isfinite(ph) & np.isfinite(nor).all(1); c0 = cen + np.nan_to_num(ph)[:, None]*np.nan_to_num(nor); nn = np.where(good[:, None], nor, 0.)
            col = run('col', WI/'points'/t/'gt_xyz.npy', np.c_[c0, nn, P['tangent1'][m], np.full(len(m), F['cell_half_m']), H[m], TAU[m], hM], f'col_{STAGE}_{prior}_{t}')
            col[~good] = np.nan
            for j, k in enumerate(['n_total', 'n_b0', 'n_bM', 'n_dens', 'n_cl']): out[k][m] = col[:, j]
            out['cl'][m] = col[:, 5:]
            print('FWD', prior, t, len(m), round(T.s() - t0, 1), flush=True)
        mp = F['min_points']; good = np.isfinite(out['n_total']); has = good & (out['n_total'] >= mp); p_ok = out['n_b0'] >= mp
        m_none = ~np.isfinite(out['h_M']); m_ok = ~m_none & (out['n_bM'] >= mp)
        a = answer(has, p_ok, m_ok, m_none); a[~good] = -1; a[~sc] = -9
        savez(dest, patch_index=ids, answer=a[ids], tau=TAU[ids], **{k: v[ids] for k, v in out.items()})
        recs[prior] = dict(patches=len(ids), area_m2=float(P['area'][ids].sum()), no_prior_height=int((~good[ids]).sum()), seconds=T.s())
        progress(f'단계 1 정방향 {STAGE} {PN[prior]}: 패치 {len(ids):,}, {T.s():.0f} s'); del P
    if recs: dump(O/'work'/STAGE/'forward.json', dict(at=now(), stage=STAGE, rows=recs, scientific_verdict=None))
if __name__ == '__main__': main()
