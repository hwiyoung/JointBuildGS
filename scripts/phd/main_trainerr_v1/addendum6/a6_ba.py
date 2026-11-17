"""Work ba (order 8): one cause per point, addendum6_c.json work_ba (locked). CPU.
Inputs: points (addendum6/points/sel_*), work ga patch main path (addendum6/ga/patch_*), work da labels (addendum6/da/labels_*), work ra FINALTRAIN re-extractions
(addendum6/ra/within_*: within tau of the point in base / occl_10 / median_depth / occl_10_median).
  tables : tables/ba_causes (scene x group, pooled six scenes), ba_secondary (with the work-da labels, both view sets), payload addendum6/ba/causes_<stem>.npz,
           figures/ba_cause_map.png (+ json)"""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1/addendum6')
from a6_common import *
PTS = A6O/'points'; BA6 = A6O/'ba'; FIG = A6D/'figures'
CAUSE = ['유효한 조각 없음', '씨앗이 놓이지 않음', '표면 추출에서 없어짐: 가려진 화소', '표면 추출에서 없어짐: 평균 깊이', '가우시안은 있는데 그린 깊이가 벗어남',
         '묶인 가우시안이 풀려 나감', '묶인 가우시안이 재할당으로 나감', '묶인 가우시안이 재설정 뒤 제거됨', '그 밖의 길로 없어짐', '설명되지 않음']
CCOL = ['#7f7f7f', '#bcbd22', '#17becf', '#9edae5', '#9467bd', '#ff7f0e', '#1f77b4', '#d62728', '#8c564b', '#000000']
L1 = ['이웃이 그린다', '앞이 가려진다', '뚫려 있다', '섞여 있다']
L2 = ['가우시안이 어긋나 있다', '앞으로 당겨진다', '뒤로 밀린다', '영상마다 다르다', '그린 깊이는 맞다', '나뉘지 않음(그 밖)']
SC_KO = {'R1rep_b10__LoD2': 'R1 × LoD2', 'R1rep_b10__ALS': 'R1 × 항공 LiDAR', 'B0_b10__LoD2': 'B0 × LoD2', 'B0_b10__ALS': 'B0 × 항공 LiDAR', 'B173nb_b10__ALS': 'B173 × 항공 LiDAR', 'B173nb_b10__LoD2': 'B173 × LoD2'}

def causes(stem):
    S = loadz(PTS/f'sel_{stem}.npz'); n = len(S['group']); W = loadz(A6O/'ra'/f'within_{stem}.npz'); G = loadz(A6O/'ga'/f'patch_{stem}.npz', ['patches', 'main_path'])
    D = loadz(A6O/'da'/f'labels_{stem}.npz'); pos = np.full(int(G['patches'].max())+2, -1, 'i8'); pos[G['patches']] = np.arange(len(G['patches']))
    need = ['ft__occl_10', 'ft__median_depth', 'ft__occl_10_median', 'ft__base']; miss = [k for k in need if k not in W]
    if miss: raise SystemExit(f'{stem}: re-extraction missing {miss}')
    st = S['state']; occ = W['ft__occl_10'] | W['ft__occl_10_median']; medw = W['ft__median_depth']
    mp = np.where(S['v'] >= 0, G['main_path'][np.clip(pos[np.clip(S['v'], 0, len(pos)-1)], 0, None)], -1); mp = np.where((S['v'] >= 0) & (pos[np.clip(S['v'], 0, len(pos)-1)] >= 0), mp, -1)
    c = np.full(n, 9, 'i1')
    c = np.where(st == 2, np.where(occ, 2, np.where(medw, 3, 4)), c)
    c = np.where(st == 1, np.select([mp == 0, mp == 1, mp == 2, (mp == 3) | (mp == 4)], [5, 6, 7, 8], 9), c)
    c = np.where((S['patch_row'] >= 0) & (S['seeds'] == 0), 1, c); c = np.where(S['patch_row'] < 0, 0, c)
    # secondary labels (both work-da view sets); -2 = not applicable
    dpos = np.full(n, -1, 'i8'); dpos[D['sel']] = np.arange(len(D['sel'])); sec = {}
    for t in ['all', 'facing']:
        l1 = np.where(dpos >= 0, D[f'{t}__label1'][np.clip(dpos, 0, None)], -2); l2 = np.where(dpos >= 0, D[f'{t}__label2'][np.clip(dpos, 0, None)], -2)
        sec[t] = np.where(np.isin(c, [2, 3, 4]), l2, np.where(np.isin(c, [5, 6, 7, 8]), l1, -2)).astype('i1')
    BA6.mkdir(parents=True, exist_ok=True)
    savez(BA6/f'causes_{stem}.npz', point_id=S['point_id'], xyz=S['xyz'], group=S['group'], state=st, cause=c, secondary_all=sec['all'], secondary_facing=sec['facing'], main_path=mp,
          within_base=W['ft__base'], within_occl=occ, within_median=medw, cause_names=np.array(CAUSE))
    return S, c, sec, (W['ft__occl_10'] | W['ft__occl_10_median'] | W['ft__median_depth'])

def tables():
    plt = korean_plt(); rows, srows = [], []; pooled = {g: np.zeros(10, 'i8') for g in range(4)}; recn = {g: np.zeros(10, 'i8') for g in range(4)}; scenes = cfg6()['points']['scenes']; data = {}
    for stem in scenes:
        S, c, sec, rec = causes(stem); data[stem] = (S, c)
        for gk in range(4):
            m = S['group'] == gk; nn = int(m.sum()); cnt = np.bincount(c[m], minlength=10); pooled[gk] += cnt
            rows.append(dict(stem=stem, group=GROUP_KO[gk], n=nn, sample='전부' if gk == 1 else '표본', **{f'{k}_n': int(cnt[i]) for i, k in enumerate(CAUSE)}, **{f'{k}_pct': 100*cnt[i]/max(1, nn) for i, k in enumerate(CAUSE)},
                             **{f'{k}_recovered_in_any_reextraction_pct': pct(rec[m & (c == i)]) if (m & (c == i)).any() else None for i, k in enumerate(CAUSE)}, recovered_rule='within tau in occl_10, median_depth or occl_10_median (FINALTRAIN)')); recn[gk] += np.bincount(c[m & rec], minlength=10)
            for t, tl in [('all', '화면에 드는 모든 영상(발주문 정의)'), ('facing', '점의 바깥쪽에서 보는 영상')]:
                for ci in range(2, 9):
                    mm = m & (c == ci)
                    if not mm.any(): continue
                    lab = L2 if ci <= 4 else L1; s = sec[t][mm]
                    srows.append(dict(stem=stem, group=GROUP_KO[gk], cause=CAUSE[ci], views=tl, n=int(mm.sum()), **{f'{x}_pct': pct(s == i) for i, x in enumerate(lab)}, no_view_pct=pct(s == -1)))
    for gk in range(4):
        cnt = pooled[gk]; nn = int(cnt.sum()); rows.append(dict(stem='여섯 장면 합', group=GROUP_KO[gk], n=nn, sample='전부' if gk == 1 else '표본(장면마다 20,000)', **{f'{k}_n': int(cnt[i]) for i, k in enumerate(CAUSE)}, **{f'{k}_pct': 100*cnt[i]/max(1, nn) for i, k in enumerate(CAUSE)}, **{f'{k}_recovered_in_any_reextraction_pct': 100*recn[gk][i]/cnt[i] if cnt[i] else None for i, k in enumerate(CAUSE)}))
    lost_total = int(pooled[1].sum()); exp = 0
    for s_ in scenes:
        A_ = np.load(GT/'addendum11/final_data'/f'{s_}.npz'); exp += int((A_['reference__eligible'].astype(bool) & A_['reference__judgment_mesh__within_tau1'].astype(bool) & ~A_['reference__FINALTRAIN_30000__within_tau1'].astype(bool)).sum())
    table6('ba_causes', rows); table6('ba_secondary', srows); dump(A6D/'tables/ba_check.json', dict(lost_points_labelled=lost_total, lost_points_in_gt_data=exp, equal=lost_total == exp, unexplained_lost=int(pooled[1][9]),
                                                                                                unexplained_lost_pct=100*pooled[1][9]/max(1, lost_total), scientific_verdict=None))
    fig, axs = plt.subplots(2, 3, figsize=(27, 18)); axs = axs.ravel()
    for ax, stem in zip(axs, scenes):
        S, c = data[stem]; xy = S['xyz'][:, :2]; bg = S['group'] == 0; ax.scatter(xy[bg, 0], xy[bg, 1], s=.3, c='#e0e0e0', lw=0, rasterized=True)
        m = S['group'] == 1
        for ci in range(10):
            mm = m & (c == ci)
            if mm.any(): ax.scatter(xy[mm, 0], xy[mm, 1], s=2.5, c=CCOL[ci], lw=0, rasterized=True, label=f'{CAUSE[ci]} {int(mm.sum()):,}')
        ax.set_aspect('equal'); ax.set_title(f'{SC_KO[stem]} — 잃은 점 {int(m.sum()):,}', fontsize=14, loc='left'); ax.legend(markerscale=5, fontsize=10, loc='upper right'); ax.set_xlabel('x (m)'); ax.set_ylabel('y (m)')
        ax.annotate('', xy=(.04, .14), xytext=(.04, .04), xycoords='axes fraction', arrowprops=dict(arrowstyle='->', lw=2)); ax.text(.05, .14, '북', transform=ax.transAxes, fontsize=12)
    fig.suptitle('잃은 점에 붙인 원인 (위에서 본 그림, 회색 = 지킨 점 표본)', fontsize=18, weight='bold'); fig.tight_layout(rect=(0, 0, 1, .96)); FIG.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG/'ba_cause_map.png', dpi=100); plt.close(fig)
    dump(FIG/'ba_cause_map.json', dict(at=now(), figure='ba_cause_map.png', points='payload addendum6/ba/causes_<stem>.npz', colours=dict(zip(CAUSE, CCOL)), frame='local training frame (m), +y = north', scientific_verdict=None))
    print('BA6', lost_total, exp, pooled[1].tolist(), flush=True)

if __name__ == '__main__': tables()
