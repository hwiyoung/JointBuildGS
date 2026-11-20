"""Stage 3 (order 8) tables of the GT target run next to the method run (CPU, reads g3_ca.py outputs and TRAINERR addendum 6 causes, read only).
tables: ca_state (8.1), ra_share (table ra, 8.2), ma_state (table ma), da_labels (8.3 labels by view set and pair set), da_front (kinds / size / distance of the
Gaussians in front of lost points), ga_course (8.3 patch course: empty, refill, main exit path), ba_causes (8.4), ba_unexplained (8.4), check8 (order 11 sums).
Method run column = TRAINERR addendum 6 (payload addendum6/ba/causes_<stem>.npz: state, cause, within_occl = occl_10 | occl_10_median, within_median, secondary_facing).
Table ma: label '앞이 가려진다' from view set 2 with all pairs (gtt_*) and with the occlusion-checked pairs (gtt_occlusion_checked_*: no order-2 pixel, not behind another GT patch).\nTable ra for GTT uses every eligible GT row (not only the selected points): lost = target mesh within tau and base outside; back with occl = within tau in the occl extraction;
back with median = not the former and within tau in median_depth or occl_median (order 8.2 table ra); not back = the rest. Method: addendum6/ra/within_<stem>.npz occl_10 / median_depth / occl_10_median."""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_gttarget_v1')
from gt_common import *
import g3_ca as CAm

CA = O/'ca'; ORDER_RA = {'가림 제외로 돌아옴': 29, '중앙 깊이까지 쓰면 돌아옴': 27, '돌아오지 않음': 44}
ORDER_MA = {'배치한 가우시안이 없고 앞이 가려진다': 73, '배치한 가우시안이 없다 (그 밖)': 7, '처음부터 배치하지 않았다': 11, '가우시안이 있는데 그린 깊이가 벗어난다': 6, '조각이 유효하지 않다': 3}
RA_KO = ['가림 제외로 돌아옴', '중앙 깊이까지 쓰면 돌아옴', '돌아오지 않음']
GRP = {0: '지킨 점', 1: '잃은 점'}
def pct(m): m = np.asarray(m, bool); return round(100*float(m.mean()), 3) if len(m) else None
def small(n): return 'n<30' if n < 30 else ''
def share(cnt, tot): return round(100*cnt/tot, 3) if tot else None

def ma_rows(st, l1):
    """table ma lines for not-recovered lost points: state 1 + '앞이 가려진다' / state 1 other / state 3 / state 2 / state 4."""
    return [('배치한 가우시안이 없고 앞이 가려진다', (st == 1) & (l1 == 1)), ('배치한 가우시안이 없다 (그 밖)', (st == 1) & (l1 != 1)), ('처음부터 배치하지 않았다', st == 3),
            ('가우시안이 있는데 그린 깊이가 벗어난다', st == 2), ('조각이 유효하지 않다', st == 4)]

def main():
    cfg(3); stems = [s for s in STEMS if (CA/f'causes_{s}_gtt_s0.npz').exists()]
    state_r, ra_r, ma_r, lab_r, front_r, course_r, ba_r, un_r, chk = [], [], [], [], [], [], [], [], []
    pool = {k: {} for k in ['ra_m', 'ra_g', 'ra_s1', 'ma_m', 'ma_g', 'ba_m', 'ba_g']}
    def add(d, k, v): d[k] = d.get(k, 0)+v
    for stem in stems:
        Z = loadz(CA/f'causes_{stem}_gtt_s0.npz'); T6 = loadz(TE/'addendum6/ba'/f'causes_{stem}.npz'); g = Z['group']; st = Z['state']; c = Z['cause']
        # ---- 8.1 state ----
        for arm, gg, ss in [('참값 목표 판', g, st), ('본 방법 판(FINALTRAIN, 덧붙임 6)', T6['group'], T6['state'])]:
            for gk in (0, 1):
                m = gg == gk; n = int(m.sum()); cnt = np.bincount(ss[m], minlength=5)
                state_r.append(dict(title=TITLE, stem=stem, arm=arm, group=GRP[gk], n=n, sample='전부' if gk == 1 else '표본 20,000', **{f'상태{k}_n': int(cnt[k]) for k in range(1, 5)}, **{f'상태{k}_pct': share(cnt[k], n) for k in range(1, 5)}, small=small(n)))
        # ---- table ra: GTT over every eligible row (s0, and s1 where it exists), method from addendum 6 ----
        A = np.load(GT/'addendum11/final_data'/f'{stem}.npz'); el = A['reference__eligible'].astype(bool); tw = np.load(O/'meshes'/f'{stem}__gtt_target/points.npz')['reference__within_tau1'].astype(bool)
        for run, key in [('gtt_s0', 'ra_g'), ('gtt_s1', 'ra_s1')]:
            if not (O/'meshes'/f'{stem}__{run}_occl_median/points.npz').exists(): continue
            W = {v: np.load(O/'meshes'/f'{stem}__{run}_{v}/points.npz')['reference__within_tau1'].astype(bool) for v in ['base', 'occl', 'median_depth', 'occl_median']}
            lost = el & tw & ~W['base']; rec = np.where(W['occl'], 0, np.where(W['median_depth'] | W['occl_median'], 1, 2)); cnt = np.bincount(rec[lost], minlength=3); n = int(lost.sum())
            ra_r.append(dict(title=TITLE, stem=stem, arm=f'참값 목표 판 씨앗 {run[-1]}', lost_n=n, **{f'{RA_KO[i]}_n': int(cnt[i]) for i in range(3)}, **{f'{RA_KO[i]}_pct': share(cnt[i], n) for i in range(3)}, sum_equals_lost=int(cnt.sum()) == n, small=small(n)))
            for i in range(3): add(pool[key], i, int(cnt[i]))
        m6 = T6['group'] == 1; W6 = loadz(TE/'addendum6/ra'/f'within_{stem}.npz', ['ft__occl_10', 'ft__median_depth', 'ft__occl_10_median']); assert len(W6['ft__occl_10']) == len(T6['group'])
        r6 = np.where(W6['ft__occl_10'][m6], 0, np.where(W6['ft__median_depth'][m6] | W6['ft__occl_10_median'][m6], 1, 2)); cnt = np.bincount(r6, minlength=3); n = int(m6.sum())
        ra_r.append(dict(title=TITLE, stem=stem, arm='본 방법 판(FINALTRAIN, 덧붙임 6)', lost_n=n, **{f'{RA_KO[i]}_n': int(cnt[i]) for i in range(3)}, **{f'{RA_KO[i]}_pct': share(cnt[i], n) for i in range(3)}, sum_equals_lost=True, small=small(n)))
        for i in range(3): add(pool['ra_m'], i, int(cnt[i]))
        # selected-point recovery equals the full-row count (check)
        chk.append(dict(title=TITLE, stem=stem, check='표 라: 고른 점의 잃은 점 수 = 전체 행의 잃은 점 수', selected_lost=int((g == 1).sum()), all_rows_lost=int((el & tw & ~np.load(O/'meshes'/f'{stem}__gtt_s0_base/points.npz')['reference__within_tau1'].astype(bool)).sum())))
        # ---- table ma (not recovered lost points) ----
        nb = (g == 1) & (Z['recovery'] == 2); l1 = Z['facing__all__l1']; l1c = Z['facing__no_occl2_no_behind_gt__l1']
        for nm, mm in ma_rows(st[nb], l1[nb]): add(pool['ma_g'], nm, int(mm.sum()))
        for nm, mm in ma_rows(st[nb], l1c[nb]): add(pool.setdefault('ma_gc', {}), nm, int(mm.sum()))
        rows_g = {nm: int(mm.sum()) for nm, mm in ma_rows(st[nb], l1[nb])}; rows_gc = {nm: int(mm.sum()) for nm, mm in ma_rows(st[nb], l1c[nb])}
        nb6 = m6 & ~T6['within_occl'] & ~T6['within_median']; l16 = np.where(np.isin(T6['cause'][nb6], [5, 6, 7, 8, 9]) & (T6['state'][nb6] == 1), T6['secondary_facing'][nb6], -2)
        rows_m = {nm: int(mm.sum()) for nm, mm in ma_rows(T6['state'][nb6], l16)}
        for nm in rows_g: add(pool['ma_m'], nm, rows_m[nm])
        for nm in rows_g:
            ma_r.append(dict(title=TITLE, stem=stem, line=nm, gtt_n=rows_g[nm], gtt_pct=share(rows_g[nm], int(nb.sum())), gtt_occlusion_checked_n=rows_gc[nm], gtt_occlusion_checked_pct=share(rows_gc[nm], int(nb.sum())),
                             method_n=rows_m[nm], method_pct=share(rows_m[nm], int(nb6.sum())),
                             gtt_not_back=int(nb.sum()), method_not_back=int(nb6.sum()), small=small(rows_g[nm])))
        # ---- 8.3 labels by view set and pair set ----
        L = loadz(CA/f'labels_{stem}_gtt_s0.npz'); dpos = np.full(len(g), -1, 'i8'); dpos[L['sel']] = np.arange(len(L['sel']))
        for vs, vk in [(CAm.VIEWSETS[0], 'all'), (CAm.VIEWSETS[1], 'facing')]:
            for ps, pk in zip(CAm.PAIRSETS, ['all', 'no_occl2', 'no_occl2_no_behind_gt']):
                for gk in (0, 1):
                    for s_, lab, key in [(1, CAm.L1, 'l1'), (2, CAm.L2, 'l2')]:
                        m = (g == gk) & (st == s_); n = int(m.sum())
                        if not n: continue
                        x = Z[f'{vk}__{pk}__{key}'][m]
                        lab_r.append(dict(title=TITLE, stem=stem, group=GRP[gk], state=f'상태 {s_}', views=vs, pairs=ps, n=n, **{f'{nm}_pct': pct(x == i) for i, nm in enumerate(lab)}, no_view_pct=pct(x == -1), small=small(n)))
        # ---- Gaussians in front of the lost points (state 1, definition 2, all pairs and occlusion-checked pairs) ----
        for pk, ps in zip(['all', 'no_occl2_no_behind_gt'], [CAm.PAIRSETS[0], CAm.PAIRSETS[2]]):
            for nm, m in [('잃은 점 상태 1', (g == 1) & (st == 1)), ('잃은 점 상태 1, 앞이 가려진다', (g == 1) & (st == 1) & (Z[f'facing__{pk}__l1'] == 1)), ('지킨 점 상태 1', (g == 0) & (st == 1))]:
                q = dpos[m]; q = q[q >= 0]; n = len(q)
                if not n: continue
                kw = L[f'facing__{pk}__front_kind_w'][q]; tot = kw.sum(1); ok = tot > 0; sh = kw[ok]/tot[ok, None]
                fo = L[f'facing__{pk}__front_off_med'][q]; fs = L[f'facing__{pk}__front_size_med'][q]
                front_r.append(dict(title=TITLE, stem=stem, points=nm, pairs=ps, n=n, with_front_weight=int(ok.sum()), **{f'{CAm.KIND4[i]}_share_mean_pct': round(100*float(sh[:, i].mean()), 2) if ok.any() else None for i in range(4)},
                                    **{f'{CAm.KIND4[i]}_main_pct': pct(sh.argmax(1) == i) if ok.any() else None for i in range(4)},
                                    front_distance_m_q25_q50_q75=np.nanquantile(fo, [.25, .5, .75]).round(3).tolist() if np.isfinite(fo).any() else None,
                                    front_size_m_q25_q50_q75=np.nanquantile(fs, [.25, .5, .75]).round(3).tolist() if np.isfinite(fs).any() else None, small=small(n)))
        # ---- patch course ----
        Gp = loadz(CA/f'patch_{stem}_gtt_s0.npz'); S = loadz(CA/f'state_{stem}_gtt_s0.npz', ['v']); pos = np.full(int(max(Gp['patches'].max(), S['v'].max()))+2, -1, 'i8'); pos[Gp['patches']] = np.arange(len(Gp['patches']))
        names = [str(x) for x in Gp['names']]
        for gk in (0, 1):
            for s_ in (1, 2):
                m = (g == gk) & (st == s_) & (S['v'] >= 0); q = pos[S['v'][m]]; q = q[q >= 0]; n = len(q)
                if not n: continue
                fe = Gp['first_empty'][q]; rf = Gp['refill'][q]; mp = Gp['main_path'][q]
                course_r.append(dict(title=TITLE, stem=stem, group=GRP[gk], state=f'상태 {s_}', n=n, never_empty_pct=pct(fe < 0), empty_from_0_pct=pct(fe == 0),
                                     **{f'first_empty_{names[k]}_pct': pct(fe == k) for k in range(1, len(names))}, refilled_pct_of_emptied=pct(rf[fe >= 0] >= 0) if (fe >= 0).any() else None,
                                     **{f'main_{CAm.PATH_KO[p]}_pct': pct(mp == i) for i, p in enumerate(CAm.PATHS)}, main_none_pct=pct(mp < 0), small=small(n)))
        # ---- 8.4 causes ----
        for arm, gg, cc, key in [('참값 목표 판', g, c, 'ba_g'), ('본 방법 판(FINALTRAIN, 덧붙임 6)', T6['group'], T6['cause'], 'ba_m')]:
            for gk in (0, 1):
                m = gg == gk; n = int(m.sum()); cnt = np.bincount(cc[m], minlength=10)
                if gk == 1:
                    for i in range(10): add(pool[key], i, int(cnt[i]))
                ba_r.append(dict(title=TITLE, stem=stem, arm=arm, group=GRP[gk], n=n, **{f'{CAm.CAUSE[i]}_n': int(cnt[i]) for i in range(10)}, **{f'{CAm.CAUSE[i]}_pct': share(cnt[i], n) for i in range(10)}, small=small(n)))
        un = Z['unexplained'] & (g == 1); nbn = int(nb.sum())
        un_r.append(dict(title=TITLE, stem=stem, not_back_lost=nbn, unexplained_n=int(un.sum()), unexplained_pct_of_not_back=share(int(un.sum()), nbn),
                         state2_drawn_right=int((un & (st == 2) & (Z['facing__all__l2'] == 4)).sum()), state2_not_split=int((un & (st == 2) & (Z['facing__all__l2'] == 5)).sum()),
                         state1_neighbour_draws=int((un & (st == 1) & (Z['facing__all__l1'] == 0)).sum()), map_needed=int(un.sum()) > 100, small=small(nbn)))
        chk.append(dict(title=TITLE, stem=stem, check='표 마 합 = 돌아오지 않음', ma_sum=sum(rows_g.values()), not_back=nbn, equal=sum(rows_g.values()) == nbn))
    # ---- pooled rows ----
    if stems:
        lbl = f"합({len(stems)} 장면)"
        for key, arm in [('ra_m', '본 방법 판(FINALTRAIN, 덧붙임 6)'), ('ra_g', '참값 목표 판 씨앗 0'), ('ra_s1', '참값 목표 판 씨앗 1')]:
            if pool[key]:
                n = sum(pool[key].values()); ra_r.append(dict(title=TITLE, stem=lbl if key != 'ra_s1' else 'R1 두 장면 합', arm=arm, lost_n=n, **{f'{RA_KO[i]}_n': pool[key].get(i, 0) for i in range(3)}, **{f'{RA_KO[i]}_pct': share(pool[key].get(i, 0), n) for i in range(3)}, sum_equals_lost=True, small=small(n)))
        ra_r.append(dict(title=TITLE, stem='발주문 값(여섯 장면)', arm='본 방법 판', **{f'{k}_pct': v for k, v in ORDER_RA.items()}))
        ng, nm_ = sum(pool['ma_g'].values()), sum(pool['ma_m'].values())
        for nm in pool['ma_g']: ma_r.append(dict(title=TITLE, stem=lbl, line=nm, gtt_n=pool['ma_g'][nm], gtt_pct=share(pool['ma_g'][nm], ng), gtt_occlusion_checked_n=pool['ma_gc'][nm], gtt_occlusion_checked_pct=share(pool['ma_gc'][nm], ng), method_n=pool['ma_m'][nm], method_pct=share(pool['ma_m'][nm], nm_), order_method_pct=ORDER_MA[nm], gtt_not_back=ng, method_not_back=nm_))
        for key, arm in [('ba_g', '참값 목표 판'), ('ba_m', '본 방법 판(FINALTRAIN, 덧붙임 6)')]:
            n = sum(pool[key].values()); ba_r.append(dict(title=TITLE, stem=lbl, arm=arm, group='잃은 점', n=n, **{f'{CAm.CAUSE[i]}_n': pool[key].get(i, 0) for i in range(10)}, **{f'{CAm.CAUSE[i]}_pct': share(pool[key].get(i, 0), n) for i in range(10)}))
        tot_un = sum(r['unexplained_n'] for r in un_r); tot_nb = sum(r['not_back_lost'] for r in un_r)
        un_r.append(dict(title=TITLE, stem=lbl, not_back_lost=tot_nb, unexplained_n=tot_un, unexplained_pct_of_not_back=share(tot_un, tot_nb), map_needed=tot_un > 100))
    absent = [s for s in STEMS if s not in stems]
    for n, rows in [('ca_state', state_r), ('ra_share', ra_r), ('ma_state', ma_r), ('da_labels', lab_r), ('da_front', front_r), ('ga_course', course_r), ('ba_causes', ba_r), ('ba_unexplained', un_r), ('check8', chk)]:
        table(n, rows+([dict(title=TITLE, stem=s, note='결과 없음(B173 × LoD2: 15,000회 건강 점검 멈춤 3회) 또는 계산 미완') for s in absent] if n in ('ra_share', 'ba_causes') else []))
    progress(f'g3_tables8: scenes {stems}, absent {absent}')
    print('T8', stems, absent, flush=True)

if __name__ == '__main__': main()
