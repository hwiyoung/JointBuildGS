"""확인 다 5.2 의 관측 넷을 패치에 주고 확인 가와 같은 셈(분포, AUC, 5 % 기각)을 B0 패치만 값이 있는 줄로 더한다 (B0 패치만, 표 이름 끝 _B0_mvs_views)."""
from common import *
import obs, p2_ga
NEW = {'mv_sel_share_abs0p05': ('다5', '고른 사진 일치 비율 0.05 m'), 'mv_sel_share_abs0p1': ('다6', '고른 사진 일치 비율 0.1 m'), 'mv_sel_share_abs0p2': ('다7', '고른 사진 일치 비율 0.2 m'), 'mv_all_agree_0p1': ('다8', '모든 사진 일치 비율 0.1 m'), 'mv_all_agree_0p2': ('다9', '모든 사진 일치 비율 0.2 m'), 'mv_all_behind_0p1': ('다10', '모든 사진 지나쳐 봄 비율 0.1 m'), 'mv_all_behind_0p2': ('다11', '모든 사진 지나쳐 봄 비율 0.2 m'), 'mv_all_front_0p2': ('다12', '모든 사진 앞 가림 비율 0.2 m'), 'mv_all_median_absdiff': ('다13', '모든 사진 |D − z| 중앙값'), 'n_all_with_D': ('다14', '모든 사진 수'), 'mv_share_0p5': ('다1', '다시점 일치 비율 0.5 %'), 'mv_share_1': ('다2', '다시점 일치 비율 1 %'), 'mv_share_2': ('다3', '다시점 일치 비율 2 %'), 'mv_median_absdiff': ('다4', '|D − z| 중앙값')}
def main():
    extra = {}
    for prior in ['LoD2', 'ALS']:
        P = loadz(O/f'photo_{prior}.npz', ['tile', 'row']); e = loadz(O/f'da_mv_{prior}.npz'); e2 = loadz(O/f'da_mv2_{prior}.npz'); assert np.array_equal(e['idx'], e2['idx']); e.update({k: v for k, v in e2.items() if k != 'idx'}); d = loadz(O/f'patch_{prior}.npz', ['tile', 'pp_row'])
        key_pp = P['tile'][e['idx']].astype(np.int64)*10**7 + P['row'][e['idx']]; key_patch = np.where(d['pp_row'] >= 0, d['tile'].astype(np.int64)*10**7 + d['pp_row'], -1)
        o = np.argsort(key_pp); pos = np.searchsorted(key_pp[o], key_patch); pos = np.clip(pos, 0, len(o) - 1); hit = (key_patch >= 0) & (key_pp[o][pos] == key_patch)
        extra[prior] = {}
        for k in NEW:
            v = np.full(len(key_patch), np.nan); v[hit] = e[k].astype(float)[o][pos[hit]]; extra[prior][k] = v
        print('patches with views', prior, int(hit.sum()))
    for k, (no, ko) in NEW.items(): obs.OBS_NO[k] = no; obs.OBS_KO[k] = ko; p2_ga.OBS_NO[k] = no; p2_ga.OBS_KO[k] = ko
    p2_ga.run(extra, only_region='B0')
if __name__ == '__main__': main()
