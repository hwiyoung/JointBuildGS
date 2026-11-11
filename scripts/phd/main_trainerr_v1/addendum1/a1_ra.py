"""Addendum 1 work 라 (order 6). CPU container.
  points <stem> <arm>  : per-point (completeness side) and per-patch (accuracy side) values -> addendum1/ra/<stem>__<arm>.npz
  tables               : decile / 5x5 / supervision x opacity tables (per scene x arm x case and pooled), figures, R1 maps"""
from a1_common import *
from s0_sets import columns
SCENES6 = ['B0_b10__ALS', 'B0_b10__LoD2', 'B173nb_b10__ALS', 'B173nb_b10__LoD2', 'R1rep_b10__ALS', 'R1rep_b10__LoD2']
OPB = ['없음', '<0.1', '0.1-0.5', '>=0.5']
def model_dir(stem, arm):
    site, prior = stem.split('__')
    if arm == 'own': return FT/'runs'/site/f'ft_{prior}_s0/attempt1/model'
    for a in ['attempt2', 'attempt1']:
        p = GT/'runs'/site/f'gt_{prior}_s0'/a/'model'
        if (p/'point_cloud/iteration_30000/point_cloud.ply').exists() and (p/'target_monitor/snapshot_30000.npz').exists(): return p
def available(stem, arm):
    if arm == 'gt' and not (GT/'addendum12/distance_A1'/f'{stem}.npz').exists(): return False
    m = model_dir(stem, arm); return m is not None and (m/'target_monitor/snapshot_30000.npz').exists()

def points(stem, arm):
    c = acfg(); t = Timer(f'a1_ra_{stem}_{arm}'); site, prior = stem.split('__'); tm, rm = TARGET_METHOD[arm], TRAINED_METHOD[arm]; ap = arm_paths(stem, arm)
    A11 = np.load(GT/'addendum11/final_data'/f'{stem}.npz'); Ar = np.load(GT/'addendum12/distance_A1'/f'{stem}.npz') if rm == 'A1' else A11
    base = {k: A11[f'reference__{k}'] for k in ['point_id', 'xyz', 'normal', 'case_id', 'tau_m']}; tw = A11[f'reference__{tm}__within_tau1'].astype(bool); rw = Ar[f'reference__{rm}__within_tau1'].astype(bool)
    idx = np.flatnonzero(tw); sub = len(idx) > 200000
    if sub: idx = np.sort(np.random.default_rng(20261111).choice(idx, 200000, replace=False))
    X = base['xyz'][idx].astype(float); Nn = base['normal'][idx].astype(float); Nn /= np.linalg.norm(Nn, axis=1)[:, None]; tau = base['tau_m'][idx].astype(float)
    rows = loadz(GT/'scenes'/stem/'rows.npz', ['row_owner']); core = loadz(JA/'core_points'/f'{stem}.npz', ['source_index']); own = rows['row_owner'][base['point_id'][idx]]
    prow = np.where(own >= 0, core['source_index'][np.clip(own, 0, None)], -1)
    tg = loadz(ap['targets'], ['target', 'normal', 'sigma', 'region', 'area']); vp = np.flatnonzero(valid_patch(tg)); prow = np.where(np.isin(prow, vp), prow, -1)
    pr, info, inimg = vis_a1(stem, arm, X, Nn, tau, np.zeros(len(X), bool), maps=True, progress=f'{stem}_{arm}')
    n = len(X); seen = np.bincount(pr['point'], minlength=n); app = pr['owner'] == prow[pr['point']]
    applied = np.bincount(pr['point'], weights=app, minlength=n).astype(int); sup = np.bincount(pr['point'], weights=np.where(app, pr['weight'], 0), minlength=n)
    wmed = np.full(n, np.nan); o = np.argsort(pr['point'], kind='stable'); pp = pr['point'][o]; ww = np.where(app, pr['weight'], np.nan)[o]; b = np.searchsorted(pp, np.arange(n+1))
    for i in np.flatnonzero(applied > 0): wmed[i] = np.nanmedian(ww[b[i]:b[i+1]])
    snap = loadz(model_dir(stem, arm)/'target_monitor/snapshot_30000.npz', ['xyz', 'opacity', 'target_tag', 'target_index', 'patch_ids'])
    assert np.array_equal(snap['patch_ids'], vp)
    bt = np.flatnonzero(snap['target_tag'] == 1); bpatch = vp[snap['target_index'][bt]]; ob = np.argsort(bpatch, kind='stable'); bps = bpatch[ob]; bts = bt[ob]
    lo = np.searchsorted(bps, prow, 'left'); hi = np.searchsorted(bps, prow, 'right'); bop = np.full(n, np.nan)
    for i in np.flatnonzero((prow >= 0) & (hi > lo)):
        g = bts[lo[i]:hi[i]]; near = np.abs((snap['xyz'][g]-X[i])@Nn[i]) <= tau[i]
        if near.any(): bop[i] = float(snap['opacity'][g][near].max())
    out = dict(point_id=base['point_id'][idx], xyz=X.astype('f4'), case_id=base['case_id'][idx], tau=tau.astype('f4'), patch_row=prow, outcome_within=rw[idx].astype('u1'),
               seen_views=seen.astype('i2'), applied_views=applied.astype('i2'), supervision=sup.astype('f4'), weight_median=wmed.astype('f4'), bound_opacity=bop.astype('f4'))
    # ---- accuracy side: per patch ----
    def owner_of(method, Z):
        if method == 'A1': return loadz(GT/'scenes'/stem/'distances/A1_samples.npz', ['owner'])['owner'][Z[f'result__{method}__point_id']]
        o_, _ = columns(Z[f'result__{method}__xyz'].astype('f8'), loadz(JA/'core_points'/f'{stem}.npz'), A1O/'columns'/f'{stem}__{method}'); return o_
    acc = {}
    for role, mth, Z in [('trained', rm, Ar), ('target', tm, A11)]:
        ow = owner_of(mth, Z); pw = np.where(ow >= 0, core['source_index'][np.clip(ow, 0, None)], -1); e = Z[f'result__{mth}__eligible_new'].astype(bool) & (pw >= 0)
        far = e & ~Z[f'result__{mth}__within_tau1'].astype(bool); acc[role+'_n'] = np.bincount(pw[e], minlength=len(tg['area'])); acc[role+'_far'] = np.bincount(pw[far], minlength=len(tg['area']))
        acc[role+'_case'] = Z[f'result__{mth}__case_id']
    index = json.loads((ap['target_dir']/'maps/index.json').read_text())['views']; wsum = np.zeros(len(tg['area'])); vcount = np.zeros(len(tg['area']), int)
    for nm, mi in index.items():
        with np.load(ap['target_dir']/'maps'/mi['file']) as mp: ow_ = mp['owner'].ravel(); w_ = mp['weight'].ravel()
        k = ow_ >= 0; wsum += np.bincount(ow_[k], weights=w_[k], minlength=len(wsum)); vcount += np.bincount(ow_[k], minlength=len(wsum)) > 0
    cnt = np.bincount(bpatch, minlength=len(tg['area'])); omax = np.full(len(tg['area']), np.nan); omed = np.full(len(tg['area']), np.nan)
    so = snap['opacity'][bts]; st = np.searchsorted(bps, np.arange(len(tg['area'])+1))
    for q in np.flatnonzero(cnt > 0): v = so[st[q]:st[q+1]]; omax[q] = v.max(); omed[q] = np.median(v)
    # patch case = modal case of its GT rows (stage1 cells)
    cells = loadz(GT/'scenes'/stem/'stage1_cells.npz', ['case_id']); ro = rows['row_owner']; rp = np.where(ro >= 0, core['source_index'][np.clip(ro, 0, None)], -1); pc = np.full(len(tg['area']), -1, 'i1')
    k = rp >= 0; key = rp[k]*10+cells['case_id'][k].astype(int); u, cc = np.unique(key, return_counts=True); pq = u//10; cs = u % 10; ordr = np.lexsort((cs, -cc, pq)); first = np.r_[True, pq[ordr][1:] != pq[ordr][:-1]]
    pc[pq[ordr][first]] = cs[ordr][first]
    out.update(patch_valid=np.isin(np.arange(len(tg['area'])), vp).astype('u1'), patch_area=tg['area'].astype('f4'), patch_case=pc, patch_supervision=(wsum/np.maximum(tg['area'], 1e-9)).astype('f4'),
               patch_applied_views=vcount.astype('i2'), patch_bound_count=cnt.astype('i4'), patch_opacity_max=omax.astype('f4'), patch_opacity_median=omed.astype('f4'),
               patch_trained_n=acc['trained_n'], patch_trained_far=acc['trained_far'], patch_target_n=acc['target_n'], patch_target_far=acc['target_far'])
    savez(A1O/'ra'/f'{stem}__{arm}.npz', **out)
    dump(A1O/'ra'/f'{stem}__{arm}.json', dict(at=now(), stem=stem, arm=arm, points=n, subsampled=sub, vis=info, model=str(model_dir(stem, arm)), trained_mesh=str(trained_mesh(stem, arm)),
         target_method=tm, trained_method=rm, seconds=t.done(), scientific_verdict=None))
    A11.close(); print('RA_POINTS', stem, arm, n, info, flush=True)

def opbin(v): return np.where(~np.isfinite(v), 0, np.where(v < .1, 1, np.where(v < .5, 2, 3)))
def qbins(v, k):
    f = np.isfinite(v); e = np.unique(np.quantile(v[f], np.linspace(0, 1, k+1))) if f.any() else np.array([0, 1])
    b = np.clip(np.searchsorted(e, v, 'right')-1, 0, len(e)-2); return np.where(f, b, -1), e

def tables():
    import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt; from matplotlib import font_manager as fm
    fm.fontManager.addfont('/fonts/NotoSansCJK-Regular.ttc'); plt.rcParams['font.family'] = fm.FontProperties(fname='/fonts/NotoSansCJK-Regular.ttc').get_name()
    CC = json.loads((R/'configs/phd/main_gtjudge_v1/addendum6.json').read_text())['case_colors']; CN = {0: '두 자료 모두 유효', 1: '사전정보 오류', 2: '영상 깊이 오류', 3: '둘 다 틀림', 4: '영상 깊이 결측'}
    dec, two, hyp, pdec, phyp, miss = [], [], [], [], [], []; pooled = []
    for stem in SCENES6:
        for arm in ARMS:
            f = A1O/'ra'/f'{stem}__{arm}.npz'
            if not f.exists(): miss.append(dict(stem=stem, arm=arm, status='없음', why='no A1 run for B173nb_b10__LoD2' if arm == 'gt' else 'not computed')); continue
            z = loadz(f); pooled.append((stem, arm, z))
            for case in [-1, 0, 1, 2, 3, 4]:
                m = np.ones(len(z['case_id']), bool) if case == -1 else z['case_id'] == case
                if m.sum() < 50: continue
                y = z['outcome_within'][m].astype(float)
                for key in ['seen_views', 'applied_views', 'supervision', 'weight_median', 'bound_opacity']:
                    v = z[key][m].astype(float)
                    if key in ('supervision',): v = np.where(z['applied_views'][m] > 0, v, np.nan)
                    b, e = qbins(v, 10)
                    for k in sorted(set(b.tolist())):
                        s = b == k; dec.append(dict(stem=stem, arm=arm, case='all' if case == -1 else case, value=key, bin='없음' if k < 0 else k, lo=None if k < 0 else float(e[k]), hi=None if k < 0 else float(e[k+1]), n=int(s.sum()), within_pct=100*float(y[s].mean())))
                ba, _ = qbins(z['applied_views'][m].astype(float), 5); bw, _ = qbins(z['weight_median'][m].astype(float), 5)
                for i in range(-1, 5):
                    for j in range(-1, 5):
                        s = (ba == i) & (bw == j)
                        if s.any(): two.append(dict(stem=stem, arm=arm, case='all' if case == -1 else case, applied_views_q=i, weight_median_q=j, n=int(s.sum()), within_pct=100*float(y[s].mean())))
                bs, _ = qbins(np.where(z['applied_views'][m] > 0, z['supervision'][m].astype(float), np.nan), 5); bo = opbin(z['bound_opacity'][m].astype(float))
                for i in range(-1, 5):
                    for j in range(4):
                        s = (bs == i) & (bo == j)
                        if s.any(): hyp.append(dict(stem=stem, arm=arm, case='all' if case == -1 else case, supervision_q='감독 없음' if i < 0 else i, opacity=OPB[j], n=int(s.sum()), within_pct=100*float(y[s].mean())))
            # accuracy side per patch
            pv = z['patch_valid'].astype(bool) & (z['patch_trained_n'] > 0); far = z['patch_trained_far'][pv]/z['patch_trained_n'][pv]
            tfar = np.where(z['patch_target_n'][pv] > 0, z['patch_target_far'][pv]/np.maximum(z['patch_target_n'][pv], 1), np.nan)
            for key in ['patch_supervision', 'patch_applied_views', 'patch_bound_count', 'patch_opacity_max', 'patch_opacity_median']:
                v = z[key][pv].astype(float); b, e = qbins(v, 10)
                for k in sorted(set(b.tolist())):
                    s = b == k; pdec.append(dict(stem=stem, arm=arm, value=key, bin='없음' if k < 0 else k, lo=None if k < 0 else float(e[k]), hi=None if k < 0 else float(e[k+1]), patches=int(s.sum()),
                                                 result_points=int(z['patch_trained_n'][pv][s].sum()), trained_far_pct=100*float(z['patch_trained_far'][pv][s].sum()/max(1, z['patch_trained_n'][pv][s].sum())),
                                                 target_far_pct=100*float(np.nansum(np.where(np.isfinite(tfar[s]), z['patch_target_far'][pv][s], 0))/max(1, z['patch_target_n'][pv][s].sum()))))
            bs, _ = qbins(z['patch_supervision'][pv].astype(float), 5); bo = opbin(z['patch_opacity_max'][pv].astype(float))
            for i in range(5):
                for j in range(4):
                    s = (bs == i) & (bo == j)
                    if s.any(): phyp.append(dict(stem=stem, arm=arm, supervision_q=i, opacity_max=OPB[j], patches=int(s.sum()), trained_far_pct=100*float(z['patch_trained_far'][pv][s].sum()/max(1, z['patch_trained_n'][pv][s].sum()))))
            # figures
            fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 4))
            for case in [0, 1, 2, 4]:
                m = (z['case_id'] == case) & (z['applied_views'] > 0)
                if m.sum() < 200: continue
                v = z['supervision'][m].astype(float); y = z['outcome_within'][m].astype(float); b, e = qbins(v, 10); xs = [np.median(v[b == k]) for k in range(len(e)-1) if (b == k).any()]; ys = [100*y[b == k].mean() for k in range(len(e)-1) if (b == k).any()]
                a1.plot(xs, ys, '-o', c=CC[str(case)], label=CN[case], ms=3)
                bo = opbin(z['bound_opacity'][z['case_id'] == case].astype(float)); yy = z['outcome_within'][z['case_id'] == case].astype(float)
                a2.bar(np.arange(4)+.2*[0, 1, 2, 4].index(case)-.3, [100*yy[bo == j].mean() if (bo == j).any() else np.nan for j in range(4)], width=.2, color=CC[str(case)], label=CN[case])
            a1.set_xscale('log'); a1.set_xlabel('감독의 양(적용 화소 무게 합)'); a1.set_ylabel('학습 뒤 τ 안 (%)'); a1.legend(fontsize=7); a2.set_xticks(range(4)); a2.set_xticklabels(OPB); a2.set_xlabel('묶인 가우시안 불투명도'); a2.set_ylabel('학습 뒤 τ 안 (%)')
            fig.suptitle(f'{stem} · {"본 방법 판정" if arm == "own" else "정답 판정"}', fontsize=9); (A1D/'figures').mkdir(parents=True, exist_ok=True); fig.savefig(A1D/'figures'/f'ra_{stem}_{arm}.png', dpi=170, bbox_inches='tight'); plt.close(fig)
            dump(A1D/'figures'/f'ra_{stem}_{arm}.json', dict(stem=stem, arm=arm, source=str(f), scientific_verdict=None))
            if stem.startswith('R1rep'):
                fig, ax = plt.subplots(1, 3, figsize=(16, 5.5)); xy = z['xyz']
                for a_, val, cm, lab in [(ax[0], np.log10(np.maximum(z['supervision'], 1e-3)), 'viridis', 'log10 감독의 양'), (ax[1], np.where(np.isfinite(z['bound_opacity']), z['bound_opacity'], -0.1), 'magma', '묶인 가우시안 불투명도(없음=-0.1)'), (ax[2], z['outcome_within'].astype(float), 'RdYlGn', '학습 뒤 τ 안')]:
                    sc_ = a_.scatter(xy[:, 0], xy[:, 1], c=val, s=.3, cmap=cm, lw=0, rasterized=True); a_.set_aspect('equal'); plt.colorbar(sc_, ax=a_, shrink=.7, label=lab)
                fig.suptitle(f'{stem} · {"본 방법 판정" if arm == "own" else "정답 판정"}', fontsize=9); fig.savefig(A1D/'figures'/f'ra_map_{stem}_{arm}.png', dpi=170, bbox_inches='tight'); plt.close(fig)
    # pooled tables (bins on pooled values)
    if pooled:
        Z = {k: np.concatenate([p[2][k] for p in pooled]) for k in ['case_id', 'outcome_within', 'supervision', 'applied_views', 'bound_opacity', 'weight_median', 'seen_views']}
        for case in [-1, 0, 1, 2, 3, 4]:
            m = np.ones(len(Z['case_id']), bool) if case == -1 else Z['case_id'] == case
            if m.sum() < 50: continue
            y = Z['outcome_within'][m].astype(float)
            for key in ['seen_views', 'applied_views', 'supervision', 'weight_median', 'bound_opacity']:
                v = Z[key][m].astype(float)
                if key == 'supervision': v = np.where(Z['applied_views'][m] > 0, v, np.nan)
                b, e = qbins(v, 10)
                for k in sorted(set(b.tolist())):
                    s = b == k; dec.append(dict(stem='pooled', arm='all', case='all' if case == -1 else case, value=key, bin='없음' if k < 0 else k, lo=None if k < 0 else float(e[k]), hi=None if k < 0 else float(e[k+1]), n=int(s.sum()), within_pct=100*float(y[s].mean())))
            bs, _ = qbins(np.where(Z['applied_views'][m] > 0, Z['supervision'][m].astype(float), np.nan), 5); bo = opbin(Z['bound_opacity'][m].astype(float))
            for i in range(-1, 5):
                for j in range(4):
                    s = (bs == i) & (bo == j)
                    if s.any(): hyp.append(dict(stem='pooled', arm='all', case='all' if case == -1 else case, supervision_q='감독 없음' if i < 0 else i, opacity=OPB[j], n=int(s.sum()), within_pct=100*float(y[s].mean())))
            ba, _ = qbins(Z['applied_views'][m].astype(float), 5); bw, _ = qbins(Z['weight_median'][m].astype(float), 5)
            for i in range(-1, 5):
                for j in range(-1, 5):
                    s = (ba == i) & (bw == j)
                    if s.any(): two.append(dict(stem='pooled', arm='all', case='all' if case == -1 else case, applied_views_q=i, weight_median_q=j, n=int(s.sum()), within_pct=100*float(y[s].mean())))
    atable('ra_deciles', dec); atable('ra_applied_x_weight', two); atable('ra_supervision_x_opacity', hyp); atable('ra_patch_deciles', pdec); atable('ra_patch_supervision_x_opacity', phyp); atable('ra_missing', miss or [dict(note='none')])
    print('RA_TABLES', len(dec), len(two), len(hyp), len(pdec), flush=True)

if __name__ == '__main__':
    a = sys.argv[1:]
    if a[0] == 'points': points(a[1], a[2])
    else: tables()
