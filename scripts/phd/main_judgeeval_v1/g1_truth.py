"""2절 판단 GT 다시 만들기(ga3) · 8절 151동(full). 참값은 정답을 만드는 데만.
패치 기둥(칸 0.25 x 0.25 m, 지붕 ±10 / 벽 ±5 m, 기준 0 = 패치 중심 + 사전 정보 높이 x 법선) 안에서
  영상 자리 h_I: 영상 깊이 점(솎지 않음)에서 폭 2τ_I 창을 밀어 가장 많은 창, 4개 이상이면 중앙값(동률 |중앙값| 작은 창)
  사전 정보 맞음: [−τ_P, τ_P] 참값 4개 이상 · 영상 맞음: [h_I − τ_I, h_I + τ_I] 참값 4개 이상 · 기둥 안 참값 4개 미만 = 정답 없음.
슬롯 0 = 본 정답(τ_P: LoD2 0.30, 항공 LiDAR 0.15; τ_I 0.15), 슬롯 1~6 = 문턱 곡선(세 자료 같은 τ).
사용: GT_STAGE=ga3|full g1_truth.py"""
from common import *
KEYS = ['tile', 'kind', 'area', 'centre', 'normal', 'tangent1', 'prior_height_m', 'building', 'tiles']
def answer(has, p_ok, m_ok, m_none):
    a = np.full(len(has), 5, np.int8); a[has & p_ok & m_ok] = 0; a[has & ~p_ok & m_ok] = 1; a[has & p_ok & ~m_ok & ~m_none] = 2; a[has & p_ok & m_none] = 3; a[has & ~p_ok & ~m_ok] = 4
    return a
def main():
    c = cfg(); T_ = c['truth']; build(); B = buildings(); T = Timer(); curve = T_['threshold_curve_m']; NS = 1 + len(curve); recs = {}
    for prior in PRIORS:
        dest = O/'work'/STAGE/f'truth_{prior}.npz'
        if dest.exists(): print('exists', dest); continue
        P = loadz(inp('patches', prior=prior), KEYS); tiles = list(P['tiles']); N = len(P['kind'])
        ids = np.flatnonzero(np.isin(P['building'], list(B))); wall = P['kind'] == 2
        tP = np.where(wall, tauP(prior, 2), tauP(prior, 1)); tI = tauI(); H = np.where(wall, T_['column']['half_length_m']['wall'], T_['column']['half_length_m']['roof']).astype(float)
        TP = np.c_[tP, np.tile(curve, (N, 1))]; TI = np.c_[np.full(N, tI), np.tile(curve, (N, 1))]   # (N, NS)
        out = dict(img_col=np.full(N, np.nan), win=np.full((N, NS), np.nan), h_I=np.full((N, NS), np.nan), tie=np.full(N, np.nan), second_n=np.full(N, np.nan), second_m=np.full(N, np.nan),
                   n_total=np.full(N, np.nan), n_dens=np.full(N, np.nan), n_b0=np.full((N, NS), np.nan), n_bI=np.full((N, NS), np.nan))
        for ti in np.unique(P['tile'][ids]):
            t0 = T.s(); m = ids[P['tile'][ids] == ti]; t = tiles[ti]; nor = P['normal'][m]; ph = P['prior_height_m'][m]
            good = np.isfinite(ph) & np.isfinite(nor).all(1); c0 = P['centre'][m] + np.nan_to_num(ph)[:, None]*np.nan_to_num(nor); nn = np.where(good[:, None], nor, 0.); base = np.c_[c0, nn, P['tangent1'][m], np.full(len(m), T_['column']['cell_half_m'][0]), H[m]]
            pad = lambda A: np.c_[A, np.full((len(A), KW - A.shape[1]), np.nan)]
            ik = run('imgk', inp('image_points', tile=t), np.c_[base, pad(TI[m])], f'imgk_{STAGE}_{prior}_{t}'); ik[~good] = np.nan
            win = ik[:, 1:1+5*NS:5]; med = ik[:, 2:2+5*NS:5]; hI = np.where(win >= T_['min_points'][0], med, np.nan)
            out['img_col'][m] = ik[:, 0]; out['win'][m] = win; out['h_I'][m] = hI; out['tie'][m] = ik[:, 3]; out['second_n'][m] = ik[:, 4]; out['second_m'][m] = ik[:, 5]
            trip = np.full((len(m), 3*KW), np.nan); trip[:, 0:3*NS:3] = TP[m]; trip[:, 1:3*NS:3] = hI; trip[:, 2:3*NS:3] = TI[m]
            ck = run('colk', inp('truth_points', tile=t), np.c_[base, trip], f'colk_{STAGE}_{prior}_{t}'); ck[~good] = np.nan
            out['n_total'][m] = ck[:, 0]; out['n_dens'][m] = ck[:, 1]; out['n_b0'][m] = ck[:, 2:2+2*NS:2]; out['n_bI'][m] = ck[:, 3:3+2*NS:2]
            print('TRUTH', STAGE, prior, t, len(m), round(T.s() - t0, 1), flush=True)
        mp = T_['min_points'][0]; good = np.isfinite(out['n_total']); has = good & (out['n_total'] >= mp); ans = np.full((N, NS), -1, np.int8)
        for k in range(NS):
            m_none = ~np.isfinite(out['h_I'][:, k]); a = answer(has, out['n_b0'][:, k] >= mp, ~m_none & (out['n_bI'][:, k] >= mp), m_none); a[~good] = -1; ans[:, k] = a
        two = (out['win'][:, 0] >= mp) & (out['second_n'] >= .5*out['win'][:, 0])
        savez(dest, patch_index=ids, answer=ans[ids], tau_P=TP[ids], tau_I=TI[ids], two_layer=two[ids], **{k: v[ids] for k, v in out.items()})
        recs[prior] = dict(patches=len(ids), area_m2=float(P['area'][ids].sum()), no_prior_height=int((~good[ids]).sum()), seconds=T.s()); progress(f'정답 {STAGE} {PN[prior]}: 패치 {len(ids):,}, {T.s():.0f} s'); del P
    if recs: dump(O/'work'/STAGE/'truth.json', dict(at=now(), stage=STAGE, slots=['본 정답'] + [f'τ {x}' for x in curve], rows=recs, scientific_verdict=None))
if __name__ == '__main__': main()
