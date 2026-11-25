"""덧붙임 4 가2 정방향 정답: 영상 자리 h_I 를 판단 원통이 아니라 패치 기둥에서 고정 규칙으로 읽는다.
패치 기둥(칸 0.25 x 0.25 m, 지붕 ±10 / 벽 ±5 m, 기준 0 = 패치 중심 + 사전 정보 높이 x 법선) 안 영상 깊이 점(솎지 않음)에서 폭 2τ 창을 밀며
가장 많이 몰린 창: 4개 이상이면 h_I = 창 안 점 중앙값, 아니면 영상 없음(동률은 |중앙값| 작은 쪽). 참값은 v2 와 같게 기둥 안 [−τ, τ], [h_I − τ, h_I + τ].
정답 표는 v2 3.2. 사용: g7_forward_ga2.py  (범위 = 세 지역 10동)"""
from common import *
from g1_forward import KEYS, answer
def main():
    c = cfg(); F = c['forward']; build(); tau = tau_table(); B = buildings('ga2'); T = Timer(); recs = {}
    for prior in PRIORS:
        dest = O/'work/ga2'/f'forward_{prior}.npz'
        if dest.exists(): print('exists', dest); continue
        P = loadz(inp('patches', prior=prior), KEYS); tiles = list(P['tiles']); N = len(P['kind'])
        sc = np.isin(P['building'], list(B)); ids = np.flatnonzero(sc); wall = P['kind'] == 2
        key = np.where(wall, f'{prior}_wall', f'{prior}_roof') if prior == 'LoD2' else np.full(N, 'ALS_roof')
        TAU = np.full(N, np.nan); TAU[ids] = [tau[r][k] for r, k in zip(P['region'][ids], key[ids])]
        H = np.where(wall, F['column_half_length_m']['wall'], F['column_half_length_m']['roof']).astype(float)
        out = {k: np.full(N, np.nan) for k in ['img_col', 'img_win', 'h_I', 'img_tie', 'img_second_n', 'img_second_m', 'n_total', 'n_b0', 'n_bM', 'n_dens', 'n_cl']}; out['cl'] = np.full((N, 12), np.nan)
        for ti in np.unique(P['tile'][ids]):
            t0 = T.s(); m = ids[P['tile'][ids] == ti]; t = tiles[ti]; nor = P['normal'][m]; ph = P['prior_height_m'][m]
            good = np.isfinite(ph) & np.isfinite(nor).all(1); c0 = P['centre'][m] + np.nan_to_num(ph)[:, None]*np.nan_to_num(nor); nn = np.where(good[:, None], nor, 0.)
            im = run('img', WI/'points'/t/'mvs_a_xyz.npy', np.c_[c0, nn, P['tangent1'][m], np.full(len(m), F['cell_half_m']), H[m], TAU[m]], f'img_ga2_{prior}_{t}'); im[~good] = np.nan
            hI = np.where(im[:, 1] >= F['min_points'], im[:, 2], np.nan)
            for j, k in enumerate(['img_col', 'img_win']): out[k][m] = im[:, j]
            out['h_I'][m] = hI; out['img_tie'][m] = im[:, 3]; out['img_second_n'][m] = im[:, 4]; out['img_second_m'][m] = im[:, 5]
            col = run('col', WI/'points'/t/'gt_xyz.npy', np.c_[c0, nn, P['tangent1'][m], np.full(len(m), F['cell_half_m']), H[m], TAU[m], hI], f'col_ga2_{prior}_{t}'); col[~good] = np.nan
            for j, k in enumerate(['n_total', 'n_b0', 'n_bM', 'n_dens', 'n_cl']): out[k][m] = col[:, j]
            out['cl'][m] = col[:, 5:]; print('GA2', prior, t, len(m), round(T.s() - t0, 1), flush=True)
        mp = F['min_points']; good = np.isfinite(out['n_total']); has = good & (out['n_total'] >= mp); p_ok = out['n_b0'] >= mp
        m_none = ~np.isfinite(out['h_I']); m_ok = ~m_none & (out['n_bM'] >= mp)
        a = answer(has, p_ok, m_ok, m_none); a[~good] = -1
        ga = loadz(O/'work/ga'/f'forward_{prior}.npz', ['patch_index', 'answer', 'h_M']); assert np.array_equal(ga['patch_index'], ids)
        savez(dest, patch_index=ids, answer=a[ids], tau=TAU[ids], ga_answer=ga['answer'], ga_h_M=ga['h_M'], h_M=out['h_I'][ids], **{k: v[ids] for k, v in out.items()})
        recs[prior] = dict(patches=len(ids), area_m2=float(P['area'][ids].sum()), no_prior_height=int((~good[ids]).sum()), ties=int((out['img_tie'][ids] == 1).sum()), tie_area_m2=float(P['area'][ids][out['img_tie'][ids] == 1].sum()), seconds=T.s())
        progress(f'가2 정방향 {PN[prior]}: 패치 {len(ids):,}, {T.s():.0f} s'); del P
    if recs: dump(O/'work/ga2/forward.json', dict(at=now(), stage='ga2', rows=recs, scientific_verdict=None))
if __name__ == '__main__': main()
