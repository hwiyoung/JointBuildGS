"""Addendum 2 work 라 (order 5): judgment right/wrong x result right/wrong, six scenes x arms. CPU container.
  points <stem> <arm> : per GT point values -> addendum2/points/ra_<stem>__<arm>.npz
  tables              : scene x arm x case x group tables, pooled tables, the two comparisons, applied-view bins, top-view figures"""
from a2_common import *
GROUPS = ['지킴', '잃음', '고침', '둘 다 틀림']; GCOL = ['#BDBDBD', '#1F5FD6', '#2CA02C', '#D62728']

def points(stem, arm):
    c = bcfg(); t0 = Timer(f'a2_ra_{stem}_{arm}'); tm, rm = TARGET_METHOD[arm], TRAINED_METHOD[arm]
    A11 = np.load(GT/'addendum11/final_data'/f'{stem}.npz'); Ar = np.load(GT/'addendum12/distance_A1'/f'{stem}.npz') if rm == 'A1' else A11
    el = A11['reference__eligible'].astype(bool); tw = A11[f'reference__{tm}__within_tau1'].astype(bool); rw = Ar[f'reference__{rm}__within_tau1'].astype(bool)
    idx = np.flatnonzero(el); n_all = len(idx); sub = n_all > 300000
    if sub: idx = np.sort(np.random.default_rng(c['common']['seed']).choice(idx, 300000, replace=False))
    pid = A11['reference__point_id'][idx]; X = A11['reference__xyz'][idx].astype('f8'); case = A11['reference__case_id'][idx]; mvs = A11['reference__mvs__within_tau1'][idx].astype('u1')
    g = np.where(tw[idx], np.where(rw[idx], 0, 1), np.where(rw[idx], 2, 3)).astype('i1')
    t = loadz(targets_of(stem, arm), ['target', 'normal', 'sigma', 'region', 'judge_region', 'area']); vp = np.flatnonzero(valid_patch(t)); N = len(t['area'])
    praw = gt_row_patch(stem)[pid]; judge = np.where(praw >= 0, t['judge_region'][np.clip(praw, 0, None)], -1).astype('i1'); prow = np.where(np.isin(praw, vp), praw, -1)
    nrm = t['normal'][np.clip(prow, 0, None)]; nrm = nrm/np.linalg.norm(nrm, axis=1)[:, None]; tdist = np.where(prow >= 0, ((X-t['target'][np.clip(prow, 0, None)])*nrm).sum(1), np.nan)
    ga = loadz(A2O/'ga'/f'{stem}__{arm}.npz', ['applied_views', 'weight_sum', 'area']); sup_p = ga['weight_sum']/np.maximum(ga['area'], 1e-9)
    S = Snap(stem, arm); bound = S.tag == 1; bcnt = np.bincount(S.patch[bound], minlength=N); bmax = np.full(N, np.nan); o = np.argsort(S.patch[bound], kind='stable'); bp = S.patch[bound][o]; bo = S.opacity[bound][o]; st = np.searchsorted(bp, np.arange(N+1))
    for q in np.flatnonzero(bcnt): bmax[q] = bo[st[q]:st[q+1]].max()
    seeds = loadz(maps_dir(stem, arm).parent/'seeds.npz', ['origin', 'patch']); scnt = np.bincount(seeds['patch'][(seeds['origin'] == 1) & (seeds['patch'] >= 0)], minlength=N)
    sv, _, _ = spot_values(S, S.spots(X), prow); q = np.clip(prow, 0, None); has = prow >= 0
    out = dict(point_id=pid, xyz=X.astype('f4'), case_id=case, group=g, judge=judge, patch_raw=praw, patch_row=prow, target_distance=tdist.astype('f4'), mvs_within=mvs,
               applied_views=np.where(has, ga['applied_views'][q], -1).astype('i4'), supervision=np.where(has, sup_p[q], np.nan).astype('f4'),
               bound_count=np.where(has, bcnt[q], -1).astype('i4'), bound_opacity_max=np.where(has, bmax[q], np.nan).astype('f4'), seeds=np.where(has, scnt[q], -1).astype('i4'),
               **{f'spot_{k}': v for k, v in sv.items() if k.startswith(('n_', 'op_'))})
    savez(A2O/'points'/f'ra_{stem}__{arm}.npz', **out)
    dump(A2O/'points'/f'ra_{stem}__{arm}.json', dict(at=now(), stem=stem, arm=arm, eligible_points=n_all, points=len(idx), subsampled=sub, target_method=tm, trained_method=rm, snapshot=str(S.path), seconds=t0.done(), scientific_verdict=None))
    A11.close(); print('RA2_POINTS', stem, arm, len(idx), flush=True)

VALS = ['abs_target_distance', 'applied_views', 'supervision', 'bound_count', 'bound_opacity_max', 'seeds', 'spot_op_max', 'spot_n_all']
def values(z, m):
    r = dict(n=int(m.sum()))
    if not m.any(): return r
    has = z['patch_row'][m] >= 0; r['valid_patch_pct'] = pct(has)
    r['abs_target_distance_median'] = med(np.abs(z['target_distance'][m])); r['applied_views_median'] = med(np.where(has, z['applied_views'][m], np.nan)); r['supervision_median'] = med(z['supervision'][m])
    r['bound_count_median'] = med(np.where(has, z['bound_count'][m], np.nan)); r['no_bound_pct'] = pct(z['bound_count'][m][has] == 0) if has.any() else None
    r['bound_opacity_max_median'] = med(z['bound_opacity_max'][m]); r['seeds_median'] = med(np.where(has, z['seeds'][m], np.nan))
    tot = max(1, int(z['spot_n_all'][m].sum())); opt = max(1e-12, float(z['spot_op_sum'][m].sum()))
    r['spot_no_gaussian_pct'] = pct(z['spot_n_all'][m] == 0); r['spot_op_max_median'] = med(z['spot_op_max'][m]); r['spot_n_all_median'] = med(z['spot_n_all'][m])
    for k in STATES: r[f'spot_{k}_count_pct'] = 100*float(z[f'spot_n_{k}'][m].sum())/tot; r[f'spot_{k}_opacity_pct'] = 100*float(z[f'spot_op_{k}'][m].sum())/opt; r[f'spot_has_{k}_pct'] = pct(z[f'spot_n_{k}'][m] > 0)
    r['mvs_within_pct'] = pct(z['mvs_within'][m] == 1)
    for code, nm in JNAME.items(): r[f'judge_{nm}_pct'] = pct(z['judge'][m] == code)
    return r

def load_all():
    out = []
    for stem in SCENES6:
        for arm in ARMS:
            f = A2O/'points'/f'ra_{stem}__{arm}.npz'
            if f.exists(): out.append((stem, arm, loadz(f)))
    return out
def cat(parts):
    return {k: np.concatenate([p[k] for p in parts]) for k in parts[0]}

def tables():
    import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt; from matplotlib import font_manager as fm
    fm.fontManager.addfont('/fonts/NotoSansCJK-Regular.ttc'); plt.rcParams['font.family'] = fm.FontProperties(fname='/fonts/NotoSansCJK-Regular.ttc').get_name()
    data = load_all(); main, comp, binsr, cum, miss = [], [], [], [], []
    have = {(s, a) for s, a, _ in data}
    for s in SCENES6:
        for a in ARMS:
            if (s, a) not in have: miss.append(dict(stem=s, arm=a, status='없음', why='no A1 run (GTJUDGE) for this scene' if a == 'gt' else 'not computed'))
    pools = [(s, a, z) for s, a, z in data]+[('pooled', a, cat([z for s_, a_, z in data if a_ == a])) for a in ARMS]+[('pooled', 'all', cat([z for _, _, z in data]))]
    allz = pools[-1][2]; av = allz['applied_views'][allz['patch_row'] >= 0].astype(float); edges = np.unique(np.quantile(av, np.linspace(0, 1, 6)))
    def abin(v, has): b = np.clip(np.searchsorted(edges, v, 'right')-1, 0, len(edges)-2); return np.where(has, b, -1)
    for s, a, z in pools:
        for cs in [-1, 0, 1, 2, 3, 4]:
            cm = np.ones(len(z['case_id']), bool) if cs == -1 else z['case_id'] == cs
            if not cm.any(): continue
            for gi, gname in enumerate(GROUPS):
                m = cm & (z['group'] == gi); r = values(z, m); r['group_share_in_case_pct'] = 100*float(m.sum())/max(1, int(cm.sum()))
                main.append(dict(stem=s, arm=a, case='all' if cs == -1 else CNAME[cs], group=gname, **r))
            for cs_, A, B in ([(1, 2, 3)] if cs == 1 else [])+([(cs, 1, 0)] if cs in (2, 4) else []):
                ra, rb = values(z, cm & (z['group'] == A)), values(z, cm & (z['group'] == B)); row = dict(stem=s, arm=a, case=CNAME[cs], compare=f'{GROUPS[A]} 대 {GROUPS[B]}', n_a=ra['n'], n_b=rb['n'])
                for k in ra:
                    if k in ('n',): continue
                    va, vb = ra.get(k), rb.get(k); row[f'{k}__{GROUPS[A]}'] = va; row[f'{k}__{GROUPS[B]}'] = vb; row[f'{k}__차이'] = (va-vb) if (va is not None and vb is not None) else None
                comp.append(row)
            has = z['patch_row'] >= 0; b = abin(z['applied_views'].astype(float), has)
            for k in range(-1, len(edges)-1):
                m = cm & (b == k)
                if not m.any(): continue
                lab = '유효 패치 없음' if k < 0 else f'[{edges[k]:.0f}, {edges[k+1]:.0f}{"]" if k == len(edges)-2 else ")"}'
                binsr.append(dict(stem=s, arm=a, case='all' if cs == -1 else CNAME[cs], applied_views_bin=lab, bin_index=k, n=int(m.sum()), **{f'{gn}_pct': 100*float((m & (z['group'] == gi)).sum())/int(m.sum()) for gi, gn in enumerate(GROUPS)}))
            for gi, gname in [(1, '잃음'), (2, '고침')]:
                m = cm & (z['group'] == gi)
                if not m.any(): continue
                for k in range(len(edges)-1):
                    cum.append(dict(stem=s, arm=a, case='all' if cs == -1 else CNAME[cs], group=gname, up_to_bin=k, applied_views_below=float(edges[k+1]), n=int(m.sum()), share_in_bins_0_to_k_pct=100*float((m & (b >= 0) & (b <= k)).sum())/int(m.sum()),
                                    no_valid_patch_pct=100*float((m & (b < 0)).sum())/int(m.sum())))
    btable('ra2_groups', main); btable('ra2_comparisons', comp); btable('ra2_applied_view_bins', binsr); btable('ra2_applied_view_cumulative', cum); btable('ra2_missing', miss or [dict(note='none')])
    dump(A2D/'tables/ra2_applied_view_edges.json', dict(edges=edges.tolist(), rule='quintile edges of patch applied views over all points with a valid patch, all scenes and arms pooled, ties merged', scientific_verdict=None))
    FIG = A2D/'figures'; FIG.mkdir(parents=True, exist_ok=True)
    for s, a, z in data:
        fig, ax = plt.subplots(figsize=(9, 9)); xy = z['xyz']
        for gi in [0, 3, 2, 1]:
            m = z['group'] == gi; ax.scatter(xy[m, 0], xy[m, 1], s=.4 if gi == 0 else .8, c=GCOL[gi], lw=0, rasterized=True, label=f'{GROUPS[gi]} {int(m.sum()):,}')
        ax.set_aspect('equal'); ax.legend(markerscale=12, fontsize=8, loc='upper right'); ax.set_title(f'{s} · {"본 방법 판정" if a == "own" else "정답 판정"} · 위에서 본 지도', fontsize=9)
        p = FIG/f'ra2_map_{s}_{a}.png'; fig.savefig(p, dpi=170, bbox_inches='tight'); plt.close(fig); dump(p.with_suffix('.json'), dict(stem=s, arm=a, colours=dict(zip(GROUPS, GCOL)), source=f'addendum2/points/ra_{s}__{a}.npz', scientific_verdict=None))
    bprogress(f'일 라 표·그림 ({len(data)}개 장면 × 판)'); print('RA2_TABLES', len(main), len(comp), len(binsr), flush=True)

if __name__ == '__main__':
    a = sys.argv[1:]
    if a[0] == 'points': points(a[1], a[2])
    else: tables()
