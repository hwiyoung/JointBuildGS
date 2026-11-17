"""Work ga (order 3) and the run table (order 2.2), addendum6.json (locked). CPU container.
  select <stem> : points of the four groups (lost all, others 20,000), point state 1-4, regroup with the record-run 30000 mesh -> addendum6/points/sel_<stem>.npz
  dumps <stem>  : the record run's whole-scene dumps reduced to uid / tag / target_index / opacity / xyz -> addendum6/dumps/<run>.npz (cache, read by works ga and na)
  track <stem>  : per patch of the selected points: bound count at every dump, empty / refill iteration, exits and their paths -> addendum6/ga/patch_<stem>.npz
  tables        : tables/ga_runs, ga_regroup, ga_empty, ga_paths, ga_refill (group x scene x definition x state)"""
import sys, time
sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1/addendum6')
from a6_common import *
PTS = A6O/'points'; DMP = A6O/'dumps'; GA6 = A6O/'ga'
PATHS = ['release', 'retarget', 'reset_delete', 'other_delete', 'split']
PATH_KO = {'release': '풀림', 'retarget': '재할당', 'reset_delete': '재설정 뒤 제거', 'other_delete': '그 밖의 제거', 'split': '분할로 대체', 'none': '나간 것 없음'}
STATE_KO = {1: '상태 1', 2: '상태 2', 3: '상태 3', 4: '상태 4'}

def run_of(stem): c = cfg6(); return c['runs'][stem]['run']

def a11_index(stem, pid):
    A = np.load(GT/'addendum11/final_data'/f'{stem}.npz'); rp = A['reference__point_id']; o = np.argsort(rp); j = o[np.searchsorted(rp[o], pid)]; assert (rp[j] == pid).all(); return A, j

def select(stem):
    c = cfg6(); t0 = time.monotonic(); z = loadz(O/'addendum2/points'/f'ra_{stem}__own.npz'); g = z['group']
    rng = np.random.default_rng(c['points']['rng_seed']+c['points']['scenes'].index(stem)); idx = []
    for k in range(4):
        ii = np.flatnonzero(g == k)
        if k != 1 and len(ii) > c['points']['others_per_scene_per_group']: ii = np.sort(rng.choice(ii, c['points']['others_per_scene_per_group'], replace=False))
        idx.append(ii)
    idx = np.sort(np.concatenate(idx)); pr = z['patch_row'][idx]; spot = z['spot_n_all'][idx]; seeds = z['seeds'][idx]; pid = z['point_id'][idx]; xyz = z['xyz'][idx]; gg = g[idx]
    case = z['case_id'][idx]; judge = z['judge'][idx]; ra_index = idx; added = np.zeros(len(idx), bool)
    A = np.load(GT/'addendum11/final_data'/f'{stem}.npz')
    if len(z['group']) < int(A['reference__eligible'].sum()):
        # addendum 2 subsampled this scene to 300,000 points: the lost points it left out are added from the GT point data with the same rules (a2_ra.points)
        el = A['reference__eligible'].astype(bool); lost = el & A['reference__judgment_mesh__within_tau1'].astype(bool) & ~A['reference__FINALTRAIN_30000__within_tau1'].astype(bool)
        new = np.setdiff1d(A['reference__point_id'][lost], z['point_id']); rp_ = A['reference__point_id']; o = np.argsort(rp_); jn = o[np.searchsorted(rp_[o], new)]
        t = loadz(targets_of(stem, 'own'), ['target', 'normal', 'sigma', 'region', 'judge_region', 'area']); vp = np.flatnonzero(valid_patch(t)); N = len(t['area'])
        praw = gt_row_patch(stem)[new]; prow = np.where(np.isin(praw, vp), praw, -1)
        sd = loadz(maps_dir(stem, 'own').parent/'seeds.npz', ['origin', 'patch']); scnt = np.bincount(sd['patch'][(sd['origin'] == 1) & (sd['patch'] >= 0)], minlength=N)
        Sn = Snap(stem, 'own'); sp_n = np.array([len(q) for q in Sn.spots(A['reference__xyz'][jn].astype('f8'))])
        pr = np.r_[pr, prow]; spot = np.r_[spot, sp_n]; seeds = np.r_[seeds, np.where(prow >= 0, scnt[np.clip(prow, 0, None)], -1)]; pid = np.r_[pid, new]; xyz = np.r_[xyz, A['reference__xyz'][jn].astype('f4')]
        gg = np.r_[gg, np.ones(len(new), 'i1')]; case = np.r_[case, A['reference__case_id'][jn]]; judge = np.r_[judge, np.where(praw >= 0, t['judge_region'][np.clip(praw, 0, None)], -1).astype('i1')]
        ra_index = np.r_[ra_index, np.full(len(new), -1)]; added = np.r_[added, np.ones(len(new), bool)]
    st = np.where(pr < 0, 4, np.where(spot > 0, 2, np.where(seeds > 0, 1, 3))).astype('i1')
    A, j = a11_index(stem, pid); tw = A['reference__judgment_mesh__within_tau1'].astype(bool)[j]; tau = A['reference__tau_m'][j].astype('f4')
    mp = loadz(O/c['runs'][stem]['mesh_30000']/'points.npz', ['reference__within_tau1']); assert len(mp['reference__within_tau1']) == len(A['reference__point_id'])
    rw = mp['reference__within_tau1'].astype(bool)[j]; g_rec = np.where(tw, np.where(rw, 0, 1), np.where(rw, 2, 3)).astype('i1')
    T = Targets(stem); v = T.v_of_rows(pr)
    savez(PTS/f'sel_{stem}.npz', ra_index=ra_index, added_from_gt=added, point_id=pid, xyz=xyz, group=gg, group_rec=g_rec, state=st, patch_row=pr, v=v, seeds=seeds,
          tau=tau, a11_row=j, case_id=case, judge=judge)
    full = dict(all_points=len(g), lost_added_from_gt=int(added.sum()), **{f'group{k}_all': int((g == k).sum()) for k in range(4)}, **{f'group{k}_selected': int((gg == k).sum()) for k in range(4)})
    dump(PTS/f'sel_{stem}.json', dict(at=now(), stem=stem, **full, record_mesh=c['runs'][stem]['mesh_30000'], seconds=time.monotonic()-t0, scientific_verdict=None))
    print('GA6_SELECT', stem, len(gg), int(added.sum()), flush=True)

def dump_order(model):
    names = [p.stem for p in (model/'trainlog/scene').glob('*.pt')]
    return sorted(names, key=lambda n: (int(n.split('_')[0]), 0 if n.endswith('pre_reset') else 1))

def dumps(stem):
    import torch
    run = run_of(stem); m = RUNS4[run]['model']; t0 = time.monotonic(); out = {}; names = dump_order(m)
    for n in names:
        s = torch.load(m/'trainlog/scene'/f'{n}.pt', map_location='cpu', weights_only=False)
        out[f'{n}__uid'] = s['uid'].numpy(); out[f'{n}__tag'] = s['target_tag'].numpy().astype('i1'); out[f'{n}__tidx'] = s['target_index'].numpy()
        out[f'{n}__opacity'] = torch.sigmoid(s['opacity'][:, 0]).numpy().astype('f4'); out[f'{n}__xyz'] = s['xyz'].numpy().astype('f4')
        out[f'{n}__size'] = torch.exp(s['scaling']).max(1).values.numpy().astype('f4'); out[f'{n}__iteration'] = np.int64(s['iteration'])
        print('GA6_DUMP', run, n, len(s['uid']), round(time.monotonic()-t0), flush=True); del s
    savez(DMP/f'{run}.npz', names=np.array(names), **out); print('GA6_DUMPS_DONE', run, len(names), round(time.monotonic()-t0), flush=True)

def events(model):
    E = load_events(model, ('delete', 'release', 'link'))
    return E

def track(stem):
    c = cfg6()['work_ga']; t0 = time.monotonic(); run = run_of(stem); m = RUNS4[run]['model']; Z = np.load(DMP/f'{run}.npz'); names = [str(x) for x in Z['names']]
    it = np.array([int(Z[f'{n}__iteration']) for n in names]); post = np.array([(not n.endswith('pre_reset')) and int(n) in c['resets'] for n in names])
    S = loadz(PTS/f'sel_{stem}.npz'); T = Targets(stem); P = np.unique(S['v'][S['v'] >= 0]); nP = len(T.valid); interest = np.zeros(nP, bool); interest[P] = True
    E = events(m); de = E['delete']; re = E['release']; lk = E['link']
    del_by = {}
    if de:
        for u, r, i in zip(de['uid'], de['reason'], de['iteration']): del_by[int(u)] = (int(r), int(i))
    rel_uid = re['uid'] if re else np.zeros(0, 'i8'); rel_it = re['iteration'] if re else np.zeros(0, 'i4')
    split_par = lk['parent_uid'][lk['how'] == 3] if lk else np.zeros(0, 'i8'); split_it = lk['iteration'][lk['how'] == 3] if lk else np.zeros(0, 'i4'); split_ch = lk['uid'][lk['how'] == 3] if lk else np.zeros(0, 'i8')
    so = np.argsort(split_par, kind='stable'); split_par, split_it, split_ch = split_par[so], split_it[so], split_ch[so]
    ro = np.lexsort((rel_it, rel_uid)); rel_uid, rel_it = rel_uid[ro], rel_it[ro]; rel_n = re['movement_normal_m'][ro] if re else np.zeros(0); rel_t = re['movement_tangent_m'][ro] if re else np.zeros(0)
    counts = np.zeros((len(names), len(P)), 'i4'); pidx = np.full(nP, -1, 'i8'); pidx[P] = np.arange(len(P))
    ex = {k: [] for k in ['patch', 'pair', 'path', 'sub', 'window', 'rel_n', 'rel_t', 'new_patch', 'child_kept', 'reason']}
    def bound(k):
        tag = Z[f'{names[k]}__tag']; ti = Z[f'{names[k]}__tidx']; b = (tag == 1) & (ti >= 0) & (ti < nP); b[b] &= interest[ti[b]]; return np.flatnonzero(b), ti
    for k in range(len(names)):
        rows, ti = bound(k); counts[k] = np.bincount(pidx[ti[rows]], minlength=len(P))
    for k in range(len(names)-1):
        ra, ta = bound(k); ua = Z[f'{names[k]}__uid'][ra]; pa = ta[ra]; ub = Z[f'{names[k+1]}__uid']; tb = Z[f'{names[k+1]}__tag']; ib = Z[f'{names[k+1]}__tidx']
        ob = np.argsort(ub); pos = np.searchsorted(ub[ob], ua); pos = np.clip(pos, 0, len(ub)-1); found = ub[ob][pos] == ua; jb = ob[pos]
        stay = found & (tb[jb] == 1) & (ib[jb] == pa); out = np.flatnonzero(~stay); ia_, ib_ = it[k], it[k+1]
        if not len(out): continue
        for q in out:
            u = int(ua[q]); p = int(pa[q]); path = sub = ''; w = 0; rn = rt = np.nan; npat = -1; ck = -1; rs = -1
            if found[q]:
                j = jb[q]
                if tb[j] == 1:
                    path = 'retarget'; npat = int(ib[j])
                else:
                    path = 'release'; a = np.searchsorted(rel_uid, u); b = np.searchsorted(rel_uid, u, 'right')
                    for e in range(a, b):
                        if ia_ < rel_it[e] <= ib_: rn, rt = float(rel_n[e]), float(rel_t[e]); break
            else:
                a = np.searchsorted(split_par, u); b = np.searchsorted(split_par, u, 'right'); sp = [e for e in range(a, b) if ia_ < split_it[e] <= ib_]
                if sp:
                    path = 'split'; ch = split_ch[sp]; pc = np.clip(np.searchsorted(ub[ob], ch), 0, len(ub)-1); jc = ob[pc]; okc = ub[jc] == ch
                    ck = int((okc & (tb[jc] == 1) & (ib[jc] == p)).any())
                elif u in del_by and ia_ < del_by[u][1] <= ib_:
                    rs, di = del_by[u]; R = [x for x in c['resets'] if di == x+c['check_after']]
                    if rs == 1 and R: path = 'reset_delete'; w = c['check_after']; sub = 'event'
                    else: path = 'other_delete'; sub = f'event_reason_{rs}'
                elif post[k]:
                    path = 'reset_delete'; w = int(ib_-ia_); sub = 'no_event'
                else:
                    chk = [x for x in c['resets'] if ia_ < x+c['check_after'] <= ib_]
                    path = 'other_delete'; sub = 'no_event_window_with_reset' if chk else 'no_event'
            ex['patch'].append(p); ex['pair'].append(k); ex['path'].append(PATHS.index(path)); ex['sub'].append(sub); ex['window'].append(w); ex['rel_n'].append(rn); ex['rel_t'].append(rt)
            ex['new_patch'].append(npat); ex['child_kept'].append(ck); ex['reason'].append(rs)
        if k % 8 == 0: print('GA6_TRACK', stem, names[k], len(ex['patch']), round(time.monotonic()-t0), flush=True)
    exa = {k: np.asarray(v) for k, v in ex.items()}; exa['sub'] = exa['sub'].astype('U40')
    first0 = np.full(len(P), -1, 'i8'); refill = np.full(len(P), -1, 'i8')
    for i in range(len(P)):
        z0 = np.flatnonzero(counts[:, i] == 0)
        if len(z0):
            first0[i] = z0[0]; r = np.flatnonzero(counts[z0[0]:, i] > 0)
            if len(r): refill[i] = z0[0]+r[0]
    npath = np.zeros((len(P), len(PATHS)), 'i4')
    if len(exa['patch']): np.add.at(npath, (pidx[exa['patch']], exa['path']), 1)
    main = np.where(npath.sum(1) > 0, npath.argmax(1), -1)
    savez(GA6/f'patch_{stem}.npz', patches=P, names=np.array(names), iterations=it, counts=counts, first_empty=first0, refill=refill, path_counts=npath, main_path=main,
          **{f'exit__{k}': v for k, v in exa.items()})
    dump(GA6/f'patch_{stem}.json', dict(at=now(), stem=stem, run=run, patches=len(P), dumps=len(names), exits=int(len(exa['patch'])), events=dict(delete=len(del_by), release=int(len(rel_uid)), split_links=int(len(split_par))),
                                       seconds=time.monotonic()-t0, scientific_verdict=None))
    print('GA6_TRACK_DONE', stem, len(P), len(exa['patch']), round(time.monotonic()-t0), flush=True)

def stage_label(names, it, k):
    """the work-ga stage interval (prev stage, stage] that holds dump k."""
    st = cfg6()['work_ga']['stages']; key = lambda n: (int(n.split('_')[0]), 0 if n.endswith('pre_reset') else 1)
    kk = key(names[k])
    for i, s in enumerate(st):
        if kk <= key(s): return '0' if i == 0 else f'({st[i-1]}, {s}]'
    return '(30000, ...]'

def tables():
    c = cfg6(); runs, regroup, empty, paths, refill, stage_rows = [], [], [], [], [], []
    for stem in c['points']['scenes']:
        f = GA6/f'patch_{stem}.npz'
        if not (PTS/f'sel_{stem}.npz').exists(): continue
        S = loadz(PTS/f'sel_{stem}.npz'); run = run_of(stem); m = RUNS4[run]['model']; st = json.loads((m/'trainlog/start.json').read_text())
        names = dump_order(m)
        runs.append(dict(stem=stem, run=run, model=str(m).replace(str(O), 'payload'), whole_scene_dumps=len(names), dumps=' '.join(names), event_scope_gaussians_at_0=st['inside'], gaussians_at_0=st['gaussians'],
                         region_file=st.get('region_file'), record_mesh_30000=c['runs'][stem]['mesh_30000'], tie=c['runs'][stem].get('tie', ''),
                         event_rule='delete / birth / retarget events only for Gaussians in the record scope; release and split links scene-wide; outside the scope the dumps are used'))
        for gk in range(4):
            mm = S['group'] == gk; regroup.append(dict(stem=stem, run=run, group=GROUP_KO[gk], n=int(mm.sum()), **{f'record_group_{GROUP_KO[j]}_pct': pct(S['group_rec'][mm] == j) for j in range(4)}, same_pct=pct(S['group_rec'][mm] == gk)))
        regroup.append(dict(stem=stem, run=run, group='네 무리 전체(뽑은 점)', n=len(S['group']), same_pct=pct(S['group_rec'] == S['group'])))
        if not f.exists(): continue
        z = loadz(f); P = z['patches']; pos = np.full(len(Targets(stem).valid), -1, 'i8'); pos[P] = np.arange(len(P)); nm = [str(x) for x in z['names']]
        stl = np.array([stage_label(nm, z['iterations'], k) for k in range(len(nm))])
        for defn, G in [('FINALTRAIN', S['group']), ('기록 판', S['group_rec'])]:
            for stt in [0, 1, 2, 3, 4]:
                for gk in range(4):
                    mm = (G == gk) & ((S['state'] == stt) if stt else True); n = int(mm.sum())
                    if not n: continue
                    q = pos[np.clip(S['v'][mm], 0, None)]; has = (S['v'][mm] >= 0) & (q >= 0); qh = q[has]
                    fe = z['first_empty'][qh]; ini = z['counts'][0, qh]
                    base = dict(stem=stem, run=run, definition=defn, state='전체' if stt == 0 else STATE_KO[stt], group=GROUP_KO[gk], n=n, with_valid_patch=int(has.sum()), small=n < c['small_n'])
                    e = dict(base, empty_from_0_pct=pct((fe == 0) & (ini == 0)) if len(qh) else None, never_empty_pct=pct(fe < 0) if len(qh) else None)
                    for lab in dict.fromkeys(stl): e[f'empty_in_{lab}_pct'] = pct((fe >= 0) & (stl[np.clip(fe, 0, None)] == lab) & ~((fe == 0) & (ini == 0))) if len(qh) else None
                    e['empty_iteration_q25_50_75'] = q4(z['iterations'][fe[fe >= 0]]) if (fe >= 0).any() else [None]*3; empty.append(e)
                    mp = z['main_path'][qh]; pr = dict(base, **{f'main_{PATH_KO[k]}_pct': pct(mp == i) if len(qh) else None for i, k in enumerate(PATHS)}, main_none_pct=pct(mp < 0) if len(qh) else None)
                    pc = z['path_counts'][qh]; tot = max(1, int(pc.sum())); pr.update({f'exits_{PATH_KO[k]}_share_pct': 100*float(pc[:, i].sum())/tot for i, k in enumerate(PATHS)}); pr['exits_total'] = int(pc.sum())
                    ep = z['exit__patch']; eh = np.isin(ep, P[qh]) if len(qh) else np.zeros(len(ep), bool); A_ = Targets(stem).anchor
                    rt = eh & (z['exit__path'] == 1) & (z['exit__new_patch'] >= 0)
                    if rt.any():
                        dd = np.linalg.norm(A_[z['exit__new_patch'][rt]]-A_[ep[rt]], axis=1); pr['retarget_new_anchor_within_0.5m_of_old_pct'] = pct(dd <= c['work_ga']['retarget_near_m']); pr['retarget_old_new_anchor_m_q'] = q4(dd)
                        # point -> new anchor, every (point, retarget exit of its patch) pair
                        o = np.argsort(ep[rt], kind='stable'); eps = ep[rt][o]; nps = z['exit__new_patch'][rt][o]; vv = S['v'][mm][has]; xx = S['xyz'][mm][has].astype('f8'); a_ = np.searchsorted(eps, vv); b_ = np.searchsorted(eps, vv, 'right')
                        cnt = b_-a_; ii = np.repeat(np.arange(len(vv)), cnt); jj = np.concatenate([np.arange(x, y) for x, y in zip(a_, b_)]) if cnt.sum() else np.zeros(0, 'i8')
                        if len(jj): dp = np.linalg.norm(A_[nps[jj]]-xx[ii], axis=1); pr['retarget_point_to_new_anchor_m_q'] = q4(dp); pr['retarget_point_to_new_anchor_within_0.5m_pct'] = pct(dp <= c['work_ga']['retarget_near_m'])
                    rl = eh & (z['exit__path'] == 0)
                    if rl.any(): pr['release_move_normal_abs_m_q'] = q4(np.abs(z['exit__rel_n'][rl])); pr['release_move_tangent_m_q'] = q4(z['exit__rel_t'][rl]); pr['release_with_event_pct'] = pct(np.isfinite(z['exit__rel_n'][rl]))
                    rd = eh & (z['exit__path'] == 2)
                    if rd.any(): pr['reset_delete_by_event_pct'] = pct(z['exit__sub'][rd] == 'event'); pr['reset_delete_window_iterations_q'] = q4(z['exit__window'][rd])
                    od = eh & (z['exit__path'] == 3)
                    if od.any(): pr['other_delete_no_event_pct'] = pct(np.char.startswith(z['exit__sub'][od], 'no_event')); pr['other_delete_window_with_reset_pct'] = pct(z['exit__sub'][od] == 'no_event_window_with_reset')
                    sp_ = eh & (z['exit__path'] == 4)
                    if sp_.any(): pr['split_child_kept_on_patch_pct'] = pct(z['exit__child_kept'][sp_] == 1)
                    paths.append(pr)
                    rf = z['refill'][qh]; refill.append(dict(base, emptied=int((fe >= 0).sum()), refilled_pct=pct(rf[fe >= 0] >= 0) if (fe >= 0).any() else None,
                                                             refill_iteration_q25_50_75=q4(z['iterations'][rf[rf >= 0]]) if (rf >= 0).any() else [None]*3))
                    sr = dict(base)
                    for s_ in c['work_ga']['stages']:
                        if s_ in nm: sr[f'bound_at_{s_}_median'] = med(z['counts'][nm.index(s_), qh]); sr[f'bound_at_{s_}_zero_pct'] = pct(z['counts'][nm.index(s_), qh] == 0) if len(qh) else None
                        else: sr[f'bound_at_{s_}_median'] = '저장 없음'
                    stage_rows.append(sr)
    table6('ga_runs', runs); table6('ga_regroup', regroup); table6('ga_empty', empty); table6('ga_paths', paths); table6('ga_refill', refill); table6('ga_stage_counts', stage_rows)
    print('GA6_TABLES', len(runs), len(empty), flush=True)

if __name__ == '__main__':
    a = sys.argv[1:]
    {'select': lambda: select(a[1]), 'dumps': lambda: dumps(a[1]), 'track': lambda: track(a[1]), 'tables': tables}[a[0]]()
