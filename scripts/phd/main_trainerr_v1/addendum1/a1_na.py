"""Addendum 1 work 나 (order 4), B0_b10__LoD2, both arms. CPU container; the renders are separate GPU jobs (te_render with tags a1, wall, wallgt).
  views    : visibility_a1 pairs for the v1 point tables (tag a1), the south-wall result sets (wall) and the two walls' face GT rows (wallgt)
  analyze  : rule check, c1 place split, south-wall checks 3/4, wall observation (4.3), wall patch opacity (4.4), baseline (4.5), code check"""
from a1_common import *
from te_views import point_table
from s0_sets import columns
STEM, SITE = 'B0_b10__LoD2', 'B0_b10'
def add_v1_keys(arr):
    n = len(arr['point']); arr['zbuf'] = np.full(n, np.nan, 'f4'); arr['tsigma'] = np.full(n, np.nan, 'f4'); return arr

def wall_sets(arm, c):
    rm = TRAINED_METHOD[arm]; Z = np.load(GT/'addendum12/distance_A1'/f'{STEM}.npz') if rm == 'A1' else np.load(GT/'addendum11/final_data'/f'{STEM}.npz')
    r = {k: Z[f'result__{rm}__{k}'] for k in ['point_id', 'xyz', 'normal', 'tau_m', 'case_id', 'eligible_new', 'within_tau1', 's_m', 'wall']}; Z.close()
    a, d, zone = wall_coords(r['xyz'].astype(float), 'south'); e = r['eligible_new'].astype(bool) & zone; w = r['within_tau1'].astype(bool)
    behind = np.flatnonzero(e & ~w & (d < -.64)); face = np.flatnonzero(e & w); rng = np.random.default_rng(c['work_na']['south_wall_sets']['seed']); mx = c['work_na']['south_wall_sets']['max']
    stats = dict(arm=arm, zone_result_points=int(zone.sum()), eligible=int(e.sum()), behind_all=len(behind), face_all=len(face))
    if len(behind) > mx: behind = np.sort(rng.choice(behind, mx, replace=False))
    if len(face) > mx: face = np.sort(rng.choice(face, mx, replace=False))
    idx = np.r_[behind, face]
    if rm == 'A1': own = loadz(GT/'scenes'/STEM/'distances/A1_samples.npz', ['owner'])['owner'][r['point_id'][idx]]
    else: own, _ = columns(r['xyz'][idx].astype('f8'), loadz(JA/'core_points'/f'{STEM}.npz'), A1O/'columns'/f'wall_{arm}')
    core = loadz(JA/'core_points'/f'{STEM}.npz', ['source_index']); prow = np.where(own >= 0, core['source_index'][np.clip(own, 0, None)], -1)
    out = dict(point_id=r['point_id'][idx], xyz=r['xyz'][idx].astype('f8'), normal=r['normal'][idx].astype('f8'), tau=r['tau_m'][idx].astype('f8'), case_id=r['case_id'][idx], d=d[idx], a=a[idx],
               set=np.r_[np.zeros(len(behind), 'i1'), np.ones(len(face), 'i1')], patch_row=prow)
    stats.update(behind_used=len(behind), face_used=len(face)); return out, stats

def wall_gt():
    rows = loadz(GT/'scenes'/STEM/'rows.npz', ['xyz', 'normal', 'wall', 'row_tau_m', 'row_owner']); core = loadz(JA/'core_points'/f'{STEM}.npz', ['source_index'])
    case = loadz(GT/'scenes'/STEM/'stage1_cells.npz', ['case_id'])['case_id']; parts = []
    for k, which in enumerate(['south', 'long']):
        a, d, zone = wall_coords(rows['xyz'], which); m = zone & rows['wall'].astype(bool) & (np.abs(d) <= rows['row_tau_m']); i = np.flatnonzero(m)
        parts.append(dict(row=i, wall=np.full(len(i), k, 'i1'), a=a[i], d=d[i]))
    P = {k: np.concatenate([p[k] for p in parts]) for k in parts[0]}; i = P['row']; own = rows['row_owner'][i]
    return dict(row=i, wall=P['wall'], a=P['a'], d=P['d'], xyz=rows['xyz'][i], normal=rows['normal'][i], tau=rows['row_tau_m'][i], case_id=case[i],
                patch_row=np.where(own >= 0, core['source_index'][np.clip(own, 0, None)], -1))

def views():
    c = acfg(); t = Timer('a1_na_views'); info = []
    G = wall_gt(); savez(A1O/'wall/gt_points.npz', **G)
    for arm in ARMS:
        scenes = blockers(STEM, arm)
        P = point_table(STEM, arm); Nn = P['normal']/np.linalg.norm(P['normal'], axis=1)[:, None]
        pr, inf, _ = vis_a1(STEM, arm, P['xyz'], Nn, P['tau'], P['result'], maps=True, scenes=scenes, progress=f'a1_{arm}'); savez(A1O/'views'/f'{STEM}__{arm}__a1.npz', **add_v1_keys(pr)); info.append(dict(set='v1 points', arm=arm, **inf))
        W, st = wall_sets(arm, c); savez(A1O/'wall'/f'{arm}_points.npz', **W); Nw = W['normal']/np.linalg.norm(W['normal'], axis=1)[:, None]
        pr, inf, _ = vis_a1(STEM, arm, W['xyz'], Nw, W['tau'], np.ones(len(W['xyz']), bool), maps=True, scenes=scenes, progress=f'wall_{arm}'); savez(A1O/'views'/f'{STEM}__{arm}__wall.npz', **add_v1_keys(pr)); info.append(dict(set='south wall result points', arm=arm, **inf, **st))
        Ng = G['normal']/np.linalg.norm(G['normal'], axis=1)[:, None]
        pr, inf, _ = vis_a1(STEM, arm, G['xyz'], Ng, G['tau'], np.zeros(len(G['xyz']), bool), maps=True, scenes=scenes, progress=f'wallgt_{arm}'); savez(A1O/'views'/f'{STEM}__{arm}__wallgt.npz', **add_v1_keys(pr)); info.append(dict(set='wall face GT rows', arm=arm, **inf))
    atable('na_visibility', [{k: (json.dumps(v) if isinstance(v, dict) else v) for k, v in r.items()} for r in info]); aprogress(f'일 나 보는 영상 ({t.done():.0f} s)')

def per_view_render(name, X, Nn):
    V = loadz(A1O/'views'/f'{name}.npz'); Rr = loadz(A1O/'render'/f'{name}.npz'); views = train_views(SITE); Ks = np.array([v['K'] for v in views]); Es = np.array([v['W2C'] for v in views])
    K = Ks[V['view']]; E = Es[V['view']]; D_ = Rr['rdepth'].astype(float); xc = np.c_[(V['u']-K[:, 0, 2])/K[:, 0, 0]*D_, (V['v']-K[:, 1, 2])/K[:, 1, 1]*D_, D_]
    Xw = np.einsum('nji,nj->ni', E[:, :3, :3], xc-E[:, :3, 3]); p = V['point']; dv = np.einsum('ij,ij->i', Nn[p], Xw-X[p]); empty = ~(Rr['ralpha'] >= .5) | ~np.isfinite(D_) | (D_ <= 0)
    return V, Rr, Xw, dv, empty

def classes34(name, X, Nn, tau, prow, snap, vp):
    """v1 check 3 (drawer modal, 3-마..라) and check 4 with result-point meaning (맞음 = render reproduces the point)."""
    V, Rr, Xw, dv, empty = per_view_render(name, X, Nn); n = len(X); pt = V['point']; nseen = np.bincount(pt, minlength=n)
    d = Rr['drawer']; ok = d >= 0; key = np.c_[pt[ok], d[ok]]; modal = np.full(n, -1, np.int64); mc = np.zeros(n, int)
    if len(key):
        u, cnt = np.unique(key, axis=0, return_counts=True); o = np.lexsort((u[:, 1], -cnt, u[:, 0])); u, cnt = u[o], cnt[o]; f = np.r_[True, u[1:, 0] != u[:-1, 0]]; modal[u[f, 0]] = u[f, 1]; mc[u[f, 0]] = cnt[f]
    gi = np.clip(modal, 0, None); tag = np.where(modal >= 0, snap['target_tag'][gi], -1); ori = np.where(modal >= 0, snap['origin'][gi], -1)
    bp = np.where((modal >= 0) & (tag == 1), vp[np.clip(snap['target_index'][gi], 0, None)], -1)
    c3 = np.where((modal < 0) | (mc*2 < nseen) | (nseen == 0), '3-마', np.where((tag == 1) & (bp == prow), '3-가', np.where(tag == 1, '3-나', np.where(ori == 1, '3-다', np.where(ori == 0, '3-라', '3-마')))))
    right = ~empty & (np.abs(dv) <= tau[pt]); wrong = ~empty & ~right; nr = np.bincount(pt, weights=right, minlength=n); nw = np.bincount(pt, weights=wrong, minlength=n); ne = np.bincount(pt, weights=empty, minlength=n)
    fac = V['facing'] == 1; fr = np.bincount(pt, weights=right & fac, minlength=n); fw = np.bincount(pt, weights=wrong & fac, minlength=n); orr, ow = nr-fr, nw-fw
    maj = lambda a, b: np.where(a > b, 1, np.where(b > a, -1, 0)); mf, mo = maj(fr, fw), maj(orr, ow); vd = ((fr+fw) >= 2) & ((orr+ow) >= 2) & (mf != 0) & (mo != 0) & (mf != mo)
    c4 = np.where(nseen < 3, '4-마', np.where(ne*2 > nseen, '4-라', np.where(vd, '4-나', np.where(nw*2 > nseen, '4-가', np.where(nr*2 > nseen, '4-다', '4-확인불가')))))
    return dict(check3=c3, check4=c4, drawer=modal, drawer_votes=mc, seen=nseen, views_right=nr, views_wrong=nw, views_empty=ne)

def analyze():
    c = acfg(); t = Timer('a1_na_analyze'); T = {}
    import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt; from matplotlib import font_manager as fm
    fm.fontManager.addfont('/fonts/NotoSansCJK-Regular.ttc'); plt.rcParams['font.family'] = fm.FontProperties(fname='/fonts/NotoSansCJK-Regular.ttc').get_name()
    from te_figs import COL
    tg = loadz(arm_paths(STEM, 'own')['targets'], ['target', 'normal', 'sigma', 'region', 'area']); vp = np.flatnonzero(valid_patch(tg))
    # ---- rule check (order 2) and c1 place split (4.1) from checks/<stem>__<arm>__a1 ----
    rc, place = [], []
    for arm in ARMS:
        z = loadz(A1O/'checks'/f'{STEM}__{arm}__a1.npz'); pr = loadz(A1O/'checks'/f'{STEM}__{arm}__a1_pairs.npz', ['point', 'right', 'empty']); z0 = loadz(O/'checks'/f'{STEM}__{arm}.npz', ['check4', 'cell', 'set'])
        K = (z['cell'] == 3) & (z['set'] == 1); pm = np.isin(pr['point'], np.flatnonzero(K))
        rc.append(dict(arm=arm, c3_control_points=int(K.sum()), share_4da_points_v1=100*float((z0['check4'][(z0['cell'] == 3) & (z0['set'] == 1)] == '4-다').mean()),
                       share_4da_points_a1=100*float((z['check4'][K] == '4-다').mean()), reproduce_pairs_pct_a1=100*float(pr['right'][pm].mean()) if pm.any() else None,
                       reproduce_nonempty_pairs_pct_a1=100*float(pr['right'][pm][~pr['empty'][pm]].mean()) if pm.any() else None, seen_views_median_a1=float(np.median(z['seen_views'][K])),
                       pass_90=bool((z['check4'][K] == '4-다').mean() >= .9)))
        for setname, sv in [('lost', 0), ('control', 1)]:
            m = (z['cell'] == 1) & (z['set'] == sv); X = z['xyz']
            for pl in ['annex_roof_edge', 'back_wall_bottom', 'other']:
                pm_ = m & (place_mask(X, pl) if pl != 'other' else ~(place_mask(X, 'annex_roof_edge') | place_mask(X, 'back_wall_bottom')))
                for key in ['check1', 'check2', 'check3', 'check4']:
                    u, cnt = np.unique(z[key][pm_], return_counts=True)
                    for k_, n_ in zip(u, cnt): place.append(dict(arm=arm, set=setname, place=pl, check=key, cls=str(k_), n=int(n_), pct=100*n_/max(1, int(pm_.sum()))))
    T['na_rule_check'] = rc; T['na_c1_place_split_a1'] = place
    # ---- south wall sets: checks 3/4 (4.2) ----
    rows3, extra = [], []
    for arm in ARMS:
        W = loadz(A1O/'wall'/f'{arm}_points.npz'); Nw = W['normal']/np.linalg.norm(W['normal'], axis=1)[:, None]
        snap = loadz(arm_paths(STEM, arm)['model']/'target_monitor/snapshot_30000.npz', ['xyz', 'opacity', 'origin', 'target_tag', 'target_index', 'patch_ids'])
        r = classes34(f'{STEM}__{arm}__wall', W['xyz'], Nw, W['tau'], W['patch_row'], snap, snap['patch_ids'])
        savez(A1O/'points'/f'na_wall_{arm}.npz', **{k: W[k] for k in ['point_id', 'xyz', 'case_id', 'd', 'a', 'set', 'patch_row']}, **{k: (v.astype('U12') if v.dtype.kind == 'U' else v) for k, v in r.items()})
        for split, sm in [('all', np.ones(len(W['set']), bool)), ('case0', W['case_id'] == 0), ('case4', W['case_id'] == 4)]:
            B = sm & (W['set'] == 0); F_ = sm & (W['set'] == 1)
            for key in ['check3', 'check4']:
                for k_ in sorted(set(r[key].tolist())):
                    a_ = 100*float((r[key][B] == k_).mean()) if B.any() else None; b_ = 100*float((r[key][F_] == k_).mean()) if F_.any() else None
                    rows3.append(dict(arm=arm, split=split, check=key, cls=k_, behind_n=int((r[key][B] == k_).sum()), behind_pct=a_, face_n=int((r[key][F_] == k_).sum()), face_pct=b_, ratio=(a_/b_ if a_ is not None and b_ else None)))
        B = W['set'] == 0; gi = r['drawer'][B]; ok = gi >= 0; dn = np.array(wall_normal('south')); dd = (snap['xyz'][gi[ok], :2]-np.array(c['places']['south_wall']['p0']))@dn[:2]
        op = snap['opacity'][gi[ok]]; ori = snap['origin'][gi[ok]]
        extra.append(dict(arm=arm, behind_points=int(B.sum()), with_drawer=int(ok.sum()), drawer_offset_p10=float(np.quantile(dd, .1)), drawer_offset_p50=float(np.median(dd)), drawer_offset_p90=float(np.quantile(dd, .9)),
                          drawer_opacity_p10=float(np.quantile(op, .1)), drawer_opacity_p50=float(np.median(op)), drawer_opacity_p90=float(np.quantile(op, .9)), drawer_origin_patch_pct=100*float((ori == 1).mean()), drawer_origin_background_pct=100*float((ori == 0).mean())))
        for key in ['check3', 'check4']:
            fig, ax = plt.subplots(figsize=(12, 5)); s_ = W['set'] == 1; ax.scatter(W['a'][s_], W['xyz'][s_, 2], s=.4, c='#dddddd', lw=0, rasterized=True)
            for k_ in sorted(set(r[key][B].tolist())):
                q = B & (r[key] == k_); ax.scatter(W['a'][q], W['xyz'][q, 2], s=2, c=COL.get(k_, '#000000'), lw=0, label=k_)
            ax.set_xlabel('벽 방향 거리 (m)'); ax.set_ylabel('높이 (m)'); ax.legend(fontsize=7, markerscale=4); ax.set_title(f'남쪽 끝 벽 · {"본 방법 판정" if arm == "own" else "정답 판정"}', fontsize=9)
            (A1D/'figures').mkdir(parents=True, exist_ok=True); fig.savefig(A1D/'figures'/f'na_wall_{key}_{arm}.png', dpi=180, bbox_inches='tight'); plt.close(fig)
            dump(A1D/'figures'/f'na_wall_{key}_{arm}.json', dict(arm=arm, view='wall face elevation (along e, height); grey = face points, colours = behind-wall points by class', scientific_verdict=None))
    T['na_south_wall_checks'] = rows3; T['na_south_wall_drawers'] = extra
    # ---- 4.3 observation of the two walls' face GT rows ----
    G = loadz(A1O/'wall/gt_points.npz'); obs = []; obs_bin = []
    for arm in ARMS:
        Ng = G['normal']/np.linalg.norm(G['normal'], axis=1)[:, None]; V, Rr, Xw, dv, empty = per_view_render(f'{STEM}__{arm}__wallgt', G['xyz'], Ng); pt = V['point']; n = len(G['xyz'])
        wn = np.where(G['wall'][pt][:, None] == 0, np.array(wall_normal('south')), np.array(wall_normal('long'))); views = train_views(SITE); Es = np.array([v['W2C'] for v in views])
        C = np.array([-E[:3, :3].T@E[:3, 3] for E in Es])[V['view']]; dirn = G['xyz'][pt]-C; dirn /= np.linalg.norm(dirn, axis=1)[:, None]; inc = np.degrees(np.arccos(np.clip(np.abs((dirn*wn).sum(1)), 0, 1)))
        off = -np.einsum('ij,ij->i', wn, Xw-G['xyz'][pt]); off[empty] = np.nan; app = V['owner'] == G['patch_row'][pt]
        seen = np.bincount(pt, minlength=n); applied = np.bincount(pt, weights=app, minlength=n)
        o = np.argsort(pt, kind='stable'); b = np.searchsorted(pt[o], np.arange(n+1)); incmin = np.full(n, np.nan); incmed = np.full(n, np.nan); wmed = np.full(n, np.nan); offmed = np.full(n, np.nan)
        for i in np.flatnonzero(seen > 0):
            s_ = o[b[i]:b[i+1]]; incmin[i] = inc[s_].min(); incmed[i] = np.median(inc[s_]); offmed[i] = np.nanmedian(off[s_]) if np.isfinite(off[s_]).any() else np.nan
            if app[s_].any(): wmed[i] = np.median(V['weight'][s_][app[s_]])
        for wl, wname in [(0, 'south'), (1, 'long')]:
            for split, sm in [('all', G['wall'] == wl), ('case0', (G['wall'] == wl) & (G['case_id'] == 0)), ('case4', (G['wall'] == wl) & (G['case_id'] == 4))]:
                if not sm.any(): continue
                q = lambda v: (float(np.nanmedian(v[sm])) if np.isfinite(v[sm]).any() else None)
                obs.append(dict(arm=arm, wall=wname, split=split, gt_rows=int(sm.sum()), seen_views_median=q(seen.astype(float)), seen_views_p10=float(np.quantile(seen[sm], .1)), applied_views_median=q(applied.astype(float)),
                                incidence_min_median_deg=q(incmin), incidence_median_median_deg=q(incmed), weight_median_median=q(wmed), render_offset_behind_median_m=q(offmed), no_seen_view_pct=100*float((seen[sm] == 0).mean())))
                for lo_, hi_ in [(0, 30), (30, 60), (60, 91)]:
                    pm = sm[pt] & (inc >= lo_) & (inc < hi_) & np.isfinite(off)
                    obs_bin.append(dict(arm=arm, wall=wname, split=split, incidence=f'{lo_}-{hi_ if hi_ < 91 else "90"}', pairs=int(pm.sum()), offset_behind_p50_m=float(np.median(off[pm])) if pm.any() else None,
                                        offset_abs_p50_m=float(np.median(np.abs(off[pm]))) if pm.any() else None, behind_over_0p64_pct=100*float((off[pm] > .64).mean()) if pm.any() else None))
        savez(A1O/'points'/f'na_wallgt_{arm}.npz', row=G['row'], wall=G['wall'], case_id=G['case_id'], xyz=G['xyz'].astype('f4'), seen=seen, applied=applied, incidence_min=incmin, incidence_median=incmed, weight_median=wmed, render_offset_median=offmed)
    T['na_wall_observation'] = obs; T['na_wall_render_offset_by_incidence'] = obs_bin
    # ---- 4.4 bound Gaussian opacity on the wall patches ----
    op_rows, op_patch = [], []; cells = loadz(GT/'scenes'/STEM/'stage1_cells.npz', ['case_id']); rws = loadz(GT/'scenes'/STEM/'rows.npz', ['row_owner']); core = loadz(JA/'core_points'/f'{STEM}.npz', ['source_index'])
    rp = np.where(rws['row_owner'] >= 0, core['source_index'][np.clip(rws['row_owner'], 0, None)], -1); kk = rp >= 0; key = rp[kk]*10+cells['case_id'][kk].astype(int); u, cc = np.unique(key, return_counts=True)
    pq, cs = u//10, u % 10; oo = np.lexsort((cs, -cc, pq)); f = np.r_[True, pq[oo][1:] != pq[oo][:-1]]; pcase = dict(zip(pq[oo][f].tolist(), cs[oo][f].tolist()))
    for arm in ARMS:
        ap = arm_paths(STEM, arm); tga = loadz(ap['targets'], ['target', 'area', 'region', 'normal', 'sigma']); vpa = np.flatnonzero(valid_patch(tga))
        snap = loadz(ap['model']/'target_monitor/snapshot_30000.npz', ['opacity', 'target_tag', 'target_index', 'init_id']); seeds = loadz(ap['target_dir']/'seeds.npz', ['origin', 'patch'])
        bt = np.flatnonzero(snap['target_tag'] == 1); bpatch = vpa[snap['target_index'][bt]]
        for which in ['south', 'long']:
            a_, d_, _ = wall_coords(tga['target'][vpa], which); pl = c['places']['south_wall' if which == 'south' else 'long_wall']
            inzone = (a_ >= pl['along_m'][0]) & (a_ <= pl['along_m'][1]) & (tga['target'][vpa, 2] >= pl['z_m'][0]) & (tga['target'][vpa, 2] <= pl['z_m'][1]) & (np.abs(d_) <= 1.)
            P_ = vpa[inzone]; inb = np.isin(bpatch, P_); cnt = np.bincount(bpatch[inb], minlength=len(tga['area'])); op = {}
            for q, oval in zip(bpatch[inb], snap['opacity'][bt[inb]]): op.setdefault(int(q), []).append(float(oval))
            seedp = {}; sp = np.flatnonzero((seeds['origin'] == 1) & np.isin(seeds['patch'], P_))
            for i in sp: seedp.setdefault(int(seeds['patch'][i]), []).append(int(i))
            alive = {}
            for q, iid in zip(bpatch[inb], snap['init_id'][bt[inb]]): alive.setdefault(int(q), set()).add(int(iid))
            for split, cm in [('all', None), ('case0', 0), ('case4', 4)]:
                if which == 'long' and split != 'all': continue
                S = [q for q in P_.tolist() if cm is None or pcase.get(q) == cm]
                if not S: continue
                allop = np.array([v for q in S for v in op.get(q, [])]); area = float(tga['area'][S].sum()); empty_area = float(tga['area'][[q for q in S if cnt[q] == 0]].sum()) if any(cnt[q] == 0 for q in S) else 0.
                ret = [len(set(seedp.get(q, [])) & alive.get(q, set()))/len(seedp[q]) for q in S if seedp.get(q)]
                op_rows.append(dict(arm=arm, wall=which, split=split, patches=len(S), area_m2=area, bound_gaussians=int(len(allop)), per_m2=len(allop)/max(area, 1e-9),
                                    opacity_lt_0p1_pct=100*float((allop < .1).mean()) if len(allop) else None, opacity_0p1_0p5_pct=100*float(((allop >= .1) & (allop < .5)).mean()) if len(allop) else None,
                                    opacity_ge_0p5_pct=100*float((allop >= .5).mean()) if len(allop) else None, opacity_median=float(np.median(allop)) if len(allop) else None,
                                    seeds=int(sum(len(seedp.get(q, [])) for q in S)), retained_seed_share_median=float(np.median(ret)) if ret else None, retained_seed_share_mean=float(np.mean(ret)) if ret else None,
                                    empty_patch_area_pct=100*empty_area/max(area, 1e-9)))
            fig, ax = plt.subplots(figsize=(12, 5)); mo = np.array([max(op.get(q, [np.nan])) for q in P_.tolist()]); A_ = a_[inzone]; Zt = tga['target'][P_, 2]
            sc_ = ax.scatter(A_[np.isfinite(mo)], Zt[np.isfinite(mo)], c=mo[np.isfinite(mo)], cmap='viridis', vmin=0, vmax=1, s=10, marker='s'); ax.scatter(A_[~np.isfinite(mo)], Zt[~np.isfinite(mo)], c='#d62728', s=10, marker='x', label='묶인 것 없음')
            plt.colorbar(sc_, ax=ax, label='패치의 묶인 가우시안 불투명도 최댓값'); ax.set_xlabel('벽 방향 거리 (m)'); ax.set_ylabel('높이 (m)'); ax.legend(fontsize=7); ax.set_title(f'{"남쪽 끝 벽" if which == "south" else "길 쪽 긴 벽"} · {"본 방법 판정" if arm == "own" else "정답 판정"}', fontsize=9)
            fig.savefig(A1D/'figures'/f'na_wall_opacity_{which}_{arm}.png', dpi=180, bbox_inches='tight'); plt.close(fig); dump(A1D/'figures'/f'na_wall_opacity_{which}_{arm}.json', dict(arm=arm, wall=which, scientific_verdict=None))
    T['na_wall_patch_opacity'] = op_rows
    # ---- 4.5 baseline and the other surfaces in the two wall zones ----
    A11 = np.load(GT/'addendum11/final_data'/f'{STEM}.npz'); A12 = np.load(GT/'addendum12/distance_A1'/f'{STEM}.npz'); bl = []
    for mth, Z in [('baseline_30000', A11), ('FINALTRAIN_30000', A11), ('A1', A12), ('judgment_mesh', A11), ('gt_judgment_mesh', A11)]:
        if f'result__{mth}__xyz' not in Z.files: bl.append(dict(method=mth, status='없음')); continue
        xyz = Z[f'result__{mth}__xyz'].astype(float); e = Z[f'result__{mth}__eligible_new'].astype(bool); w = Z[f'result__{mth}__within_tau1'].astype(bool); cs_ = Z[f'result__{mth}__case_id']
        for which in ['south', 'long']:
            _, d_, zone = wall_coords(xyz, which)
            for split, sm in [('all', zone), ('case0', zone & (cs_ == 0)), ('case4', zone & (cs_ == 4)), ('case2', zone & (cs_ == 2))]:
                ee = e & sm
                if ee.sum() < 20: continue
                bl.append(dict(method=mth, wall=which, split=split, result_points=int(ee.sum()), accuracy_pct=100*float(w[ee].mean()), behind_over_0p64_pct=100*float((d_[ee] < -.64).mean())))
    A11.close(); A12.close(); T['na_baseline_walls'] = bl
    T['na_code_check'] = [
        dict(item='위치 제약', where='jbgs_target_r6.py:67 project_bounds (r23/r25)', bound='묶인 것(target_tag 1)만 법선 방향 1.96σ 구간으로 투영', unbound='없음'),
        dict(item='재할당·풀림', where='jbgs_target_r7.py:46 reattach (100회 점검, 복제·분할·지우기 뒤)', bound='접선 0.5 m·법선 초과 0.5 m 밖이면 풀림(target_tag 2)', unbound='해당 없음(배경·풀린 것은 다시 묶이지 않음)'),
        dict(item='불투명도 되돌리기', where='scene/gaussian_model.py:244-248 reset_opacity, train.py:1207(r23)/1215(r25) exempt_mask=None', bound='같음(모두 0.01로 낮춤)', unbound='같음'),
        dict(item='지우기(불투명도·화면 크기·세계 크기)', where='scene/gaussian_model.py:524-531(r23)/528-536(r25) densify_and_prune; density_exempt :67-72 = frozen_mask', bound='같음(frozen_mask 모두 거짓: jbgs_target.py:77)', unbound='같음'),
        dict(item='분할·복제', where='scene/gaussian_model.py:464-474·496-503(r23)/468-478·500-507(r25); child_metadata jbgs_target_r6.py:71', bound='같은 규칙. 자식은 부모의 꼬리표·패치를 물려받고 바로 재할당 점검', unbound='같은 규칙'),
        dict(item='건강 점검', where='jbgs_target_r7.py observe / jbgs_finaltrain.py observe', bound='패치 출신 계보 불투명도 중간값 < 0.05면 멈춤(기록만, 개체 처리 없음)', unbound='해당 없음')]
    for k, rows in T.items(): atable(k, rows)
    aprogress(f'일 나 분석 ({t.done():.0f} s)'); print('NA_DONE', {k: len(v) for k, v in T.items()}, flush=True)

if __name__ == '__main__':
    {'views': views, 'analyze': analyze}[sys.argv[1]]()
