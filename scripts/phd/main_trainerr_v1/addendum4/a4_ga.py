"""Work ga (order 2): why release and retarget happen (addendum4.json work_ga + addendum4_b.json events).
  events <run>   : per release / retarget event of the place patches: condition (tangent / normal excess to the previous patch), position at the
                   event (normal + outward, tangent), movement since first placement, self or child, fate at the last state -> addendum4/ga/events_<run>.npz + tables
  balance <run>  : per window between saved states: start + born + in - deleted - released - out (+ range in/out) = end, per place
  floater        : B173 x ALS edge floater and control (scene states, state-based: released_at, last bound patch)
  grads          : sa-1 signed position gradients along the outward target normal by term, window, place, released-ever vs bound
  check6000      : sa-1 6000 vs record run 6000 (counts, losses, signed-vs-magnitude field check)"""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1/addendum4')
from a4_common import *
import time
GA = A4O/'ga'
HOW = {0: '본인(사전 정보 씨앗)', 1: '본인(배경 씨앗)', 2: '자식(복제)', 3: '자식(분할)'}

def raw_state(model, name): return loadz(model/'trainlog/states'/f'{name}.npz')

def plane_geom(T, vrow, X, out):
    """normal (outward +) and tangent distance of X to the target plane of valid rows vrow; excess = max(|h| - 1.96 sigma, 0)."""
    a = T.anchor[vrow]; n = T.normal[vrow]; d = X-a; h = (d*n).sum(1); tan = np.linalg.norm(d-h[:, None]*n, axis=1)
    sgn = np.sign((n*out).sum(1)); sgn[sgn == 0] = 1
    return h*sgn, tan, np.maximum(np.abs(h)-1.96*T.sigma[vrow], 0)

def out_lookup(pp):
    lut = {int(v): pp['out'][i] for i, v in enumerate(pp['v'])}
    def f(vrows, T):
        o = np.array([lut.get(int(v), T.normal[int(v)]) for v in vrows]).reshape(-1, 3); return o
    return f

def events(run):
    t0 = time.monotonic(); cfgr = RUNS4[run]; model = cfgr['model']; E = load_events(model, ('delete', 'release', 'retarget', 'birth'))
    last = raw_state(model, cfgr['last']); s0 = raw_state(model, '0'); first0 = {int(u): s0['xyz'][i] for i, u in enumerate(s0['uid'])}
    bx = {int(u): E['birth']['xyz'][i] for i, u in enumerate(E['birth']['uid'])} if len(E['birth']) else {}
    luid = {int(u): i for i, u in enumerate(last['uid'])}; dl = {int(u): (int(r), int(it)) for u, r, it in zip(E['delete']['uid'], E['delete']['reason'], E['delete']['iteration'])} if len(E['delete']) else {}
    GA.mkdir(parents=True, exist_ok=True); rows = []; save = {}
    for place in cfgr['places']:
        pp = place_patches(place); T = pp['T']; Sp = pp['v']; of = out_lookup(pp)
        r = E['release']; m = np.isin(r['previous_target_index'], Sp); ii = np.flatnonzero(m)
        X = r['xyz'][ii].astype('f8'); vprev = r['previous_target_index'][ii].astype('i8'); out = of(vprev, T)
        hn, tan, exc = plane_geom(T, vprev, X, out)
        cond = np.where((tan > .5) & (exc > .5), 3, np.where(tan > .5, 1, np.where(exc > .5, 2, 0)))
        how = r['born_how'][ii].astype('i8'); atbirth = (r['birth_iteration'][ii] == r['iteration'][ii]) & (r['cause'][ii] == 0)
        cause = np.where(r['cause'][ii] == 1, 0, np.where(atbirth, 1, 2))   # 0 periodic 100-step check, 1 reattach right after the child was made, 2 other reattach
        uid = r['uid'][ii].astype('i8'); fp = np.array([first0.get(int(u), bx.get(int(u), np.full(3, np.nan))) for u in uid]).reshape(-1, 3)
        dv = X-fp; n_ = T.normal[vprev]*np.sign((T.normal[vprev]*out).sum(1, keepdims=True)+1e-30); mvn = (dv*n_).sum(1); mvt = np.linalg.norm(dv-mvn[:, None]*n_, axis=1)
        fate = np.zeros(len(uid), 'i1'); fate_d = np.full(len(uid), np.nan); fate_r = np.full(len(uid), -1)
        for k, u in enumerate(uid):
            u = int(u)
            if u in luid:
                j = luid[u]; tg = int(last['target_tag'][j]); fate[k] = 1 if tg == 2 else (3 if tg == 1 else 4)
                fate_d[k] = plane_geom(T, vprev[k:k+1], last['xyz'][j:j+1].astype('f8'), out[k:k+1])[0][0]
            elif u in dl: fate[k] = 2; fate_r[k] = dl[u][0]
            else: fate[k] = 5
        save[place+'_release'] = dict(uid=uid, iteration=r['iteration'][ii], cond=cond, cause=cause, normal_m=hn, tangent_m=tan, excess_m=exc, move_normal_m=mvn, move_tangent_m=mvt,
                                      how=how, fate=fate, fate_normal_m=fate_d, fate_delete_reason=fate_r, opacity=r['opacity'][ii], size_m=r['longest_axis_m'][ii])
        n = len(ii)
        def share(mask): return pct(mask) if n else None
        row = dict(run=run, place=place, place_ko=PLACE_KO.get(place, place), patches=len(Sp), released=n,
                   cause_periodic=int((cause == 0).sum()), cause_right_after_child=int((cause == 1).sum()), cause_other=int((cause == 2).sum()),
                   cond_tangent_only=int((cond == 1).sum()), cond_normal_only=int((cond == 2).sum()), cond_both=int((cond == 3).sum()), cond_none_at_event=int((cond == 0).sum()),
                   self_prior_seed=int((how == 0).sum()), self_background_seed=int((how == 1).sum()), child_clone=int((how == 2).sum()), child_split=int((how == 3).sum()),
                   tangent_m_median=med(tan), tangent_m_p10=float(np.quantile(tan, .1)) if n else None, tangent_m_p90=float(np.quantile(tan, .9)) if n else None,
                   normal_out_m_median=med(hn), normal_out_pos_pct=share(hn > 0), excess_m_median=med(exc),
                   move_normal_m_median=med(mvn), move_tangent_m_median=med(mvt), move_tangent_gt05_pct=share(mvt > .5),
                   fate_alive_released=int((fate == 1).sum()), fate_deleted=int((fate == 2).sum()), fate_deleted_opacity=int(((fate == 2) & (fate_r == 1)).sum()),
                   fate_rebound=int((fate == 3).sum()), fate_left_range=int((fate == 5).sum()), fate_alive_normal_m_median=med(fate_d[fate == 1]), last_state=cfgr['last'])
        for c in [0, 1, 2]:
            q = cause == c; row[f'cause{c}_tangent_m_median'] = med(tan[q]); row[f'cause{c}_child_pct'] = pct(how[q] >= 2) if q.any() else None
        rows.append(row)
        t = E['retarget']
        if len(t):
            wo = np.isin(t['old'], Sp) & ~np.isin(t['new'], Sp); wi = ~np.isin(t['old'], Sp) & np.isin(t['new'], Sp)
            for kind, w in [('out', wo), ('in', wi)]:
                jj = np.flatnonzero(w); Xr = t['xyz'][jj].astype('f8'); vo = t['old'][jj].astype('i8'); vn = t['new'][jj].astype('i8')
                ho, to, eo = plane_geom(T, vo, Xr, of(vo, T)); hn2, tn, en = plane_geom(T, vn, Xr, T.normal[vn])
                cs = t['cause'][jj]; jud_o = T.judge[vo]; jud_n = T.judge[vn]
                save[f'{place}_retarget_{kind}'] = dict(uid=t['uid'][jj], iteration=t['iteration'][jj], cause=cs, old_tangent_m=to, old_excess_m=eo, old_normal_m=ho, new_tangent_m=tn, new_excess_m=en,
                                                        old_judge=jud_o, new_judge=jud_n, anchor_gap_normal_m=np.abs(((T.anchor[vn]-T.anchor[vo])*T.normal[vo]).sum(1)))
                rows.append(dict(run=run, place=place, place_ko=PLACE_KO.get(place, place), kind=f'retarget_{kind}', events=len(jj), cause_periodic=int((cs == 1).sum()), cause_other=int((cs == 0).sum()),
                                 old_tangent_gt05_pct=pct(to > .5) if len(jj) else None, old_tangent_m_median=med(to), new_tangent_m_median=med(tn), old_excess_gt05_pct=pct(eo > .5) if len(jj) else None,
                                 same_judgment_pct=pct(jud_o == jud_n) if len(jj) else None, anchor_gap_normal_m_median=med(np.abs(((T.anchor[vn]-T.anchor[vo])*T.normal[vo]).sum(1)))))
    np.savez_compressed(GA/f'events_{run}.npz', **{f'{k}__{f}': v for k, d in save.items() for f, v in d.items()})
    dtable(f'ga_events_{run}', rows); print('GA_EVENTS', run, round(time.monotonic()-t0), flush=True)

def balance(run):
    """event counts per window; a child counts as born into the place when the target it inherited (its first event's old index, else its end-state
    target) is a place patch; range in/out the same with the target at entry (next event old index, else end state) / at exit (start-state membership)."""
    cfgr = RUNS4[run]; model = cfgr['model']; E = load_events(model, ('delete', 'release', 'retarget', 'birth', 'range')); sv = saves(model); rows = []
    d, r, t, bth, g = E['delete'], E['release'], E['retarget'], E['birth'], E['range']
    ev_seq = np.concatenate([t['seq'], r['seq'], d['seq']]) if len(t) else np.concatenate([r['seq'], d['seq']])
    ev_uid = np.concatenate([t['uid'], r['uid'], d['uid']]) if len(t) else np.concatenate([r['uid'], d['uid']])
    ev_old = np.concatenate([t['old'], r['previous_target_index'], np.where(d['tag'] == 1, d['target_index'], -1)]) if len(t) else np.concatenate([r['previous_target_index'], np.where(d['tag'] == 1, d['target_index'], -1)])
    o = np.argsort(ev_seq, kind='stable'); ev_seq, ev_uid, ev_old = ev_seq[o], ev_uid[o], ev_old[o]
    by_uid = {}
    for sq, u, ol in zip(ev_seq, ev_uid, ev_old): by_uid.setdefault(int(u), []).append((int(sq), int(ol)))
    def next_old(u, sq):
        for s2, ol in by_uid.get(int(u), []):
            if s2 > sq: return ol, s2
        return None, None
    for place in cfgr['places']:
        pp = place_patches(place); Sp = pp['v']; SpS = set(Sp.tolist()); prev = None
        for s in sv:
            S = raw_state(model, s['name']); b = (S['target_tag'] == 1) & np.isin(S['target_index'], Sp); cur = set(S['uid'][b].tolist()); endt = dict(zip(S['uid'].tolist(), np.where(S['target_tag'] == 1, S['target_index'], -1).tolist()))
            if prev is not None:
                q0, q1 = prev[1], s['seq']
                md = (d['seq'] > q0) & (d['seq'] <= q1) & (d['tag'] == 1) & np.isin(d['target_index'], Sp)
                mr = (r['seq'] > q0) & (r['seq'] <= q1) & np.isin(r['previous_target_index'], Sp)
                if len(t): w = (t['seq'] > q0) & (t['seq'] <= q1); mo = w & np.isin(t['old'], Sp) & ~np.isin(t['new'], Sp); mi = w & ~np.isin(t['old'], Sp) & np.isin(t['new'], Sp)
                else: mo = mi = np.zeros(0, bool)
                def inherited(u, sq):
                    ol, s2 = next_old(u, sq)
                    if ol is not None and s2 <= q1: return ol
                    return endt.get(int(u), -1)
                born = 0
                if len(bth):
                    wb = (bth['seq'] > q0) & (bth['seq'] <= q1) & (bth['tag'] == 1)
                    born = sum(1 for u, sq in zip(bth['uid'][wb], bth['seq'][wb]) if inherited(u, sq) in SpS)
                rin = rout = 0
                if len(g):
                    wr = (g['seq'] > q0) & (g['seq'] <= q1) & (g['tag'] == 1)
                    rin = sum(1 for u, sq, en in zip(g['uid'][wr], g['seq'][wr], g['enter'][wr]) if en and inherited(u, sq) in SpS)
                    last_t = {}
                    for u0 in prev[0]: last_t[int(u0)] = 'in'
                    for u, sq, en in zip(g['uid'][wr], g['seq'][wr], g['enter'][wr]):
                        if en: continue
                        # target at exit: the last event before the exit (new index of a retarget / none), else start-state membership
                        hist = [(s2, ol) for s2, ol in by_uid.get(int(u), []) if q0 < s2 < sq]
                        tr = [(s2, nw) for s2, nw in zip(t['seq'][(t['uid'] == u) & (t['seq'] > q0) & (t['seq'] < sq)], t['new'][(t['uid'] == u) & (t['seq'] > q0) & (t['seq'] < sq)])] if len(t) else []
                        if tr: rout += int(int(max(tr)[1]) in SpS)
                        else: rout += int(int(u) in prev[0])
                start, end = len(prev[0]), len(cur); bal = start+born+int(mi.sum())+rin-int(md.sum())-int(mr.sum())-int(mo.sum())-rout
                rows.append(dict(run=run, place=place, place_ko=PLACE_KO.get(place, place), window=f'{prev[3]}–{s["name"]}', start=start, born=born, retarget_in=int(mi.sum()), range_in=rin,
                                 deleted=int(md.sum()), released=int(mr.sum()), retarget_out=int(mo.sum()), range_out=rout, end=end, computed_end=bal, residual=end-bal))
            prev = (cur, s['seq'], s['iteration'], s['name'])
    dtable(f'ga_balance_{run}', rows); res = [abs(x['residual']) for x in rows]
    print('GA_BALANCE', run, 'windows', len(rows), 'nonzero residual', sum(1 for x in res if x), 'max', max(res) if res else None, flush=True)

def floater():
    """state-based (TRAINLOG records events only inside the footprint buffer): uids within 0.5 m of the face centres at 30000 + ancestors."""
    import torch
    cfgr = RUNS4['tl_B173nb_b10_ALS_s0']; model = cfgr['model']; sv = saves(model); T = Targets('B173nb_b10__ALS'); rows = []; save = {}
    def pt(name): return torch.load(model/'trainlog/scene'/f'{name}.pt', map_location='cpu', weights_only=False)
    L = pt('30000'); X = L['xyz'].double().numpy(); par = {}
    for s in sv:
        d = pt(s['name']); par.update(dict(zip(d['uid'].tolist(), d['parent_uid'].tolist())))
    for place in ['floater', 'floater_control']:
        C = floater_centres(place); lo = C.min(0)-.6; hi = C.max(0)+.6; k = np.flatnonzero(np.all((X >= lo) & (X <= hi), 1)); dd, _ = cKDTree(C).query(X[k]); g = k[dd <= .5]
        uids = L['uid'].numpy()[g]; anc = {}
        for u in uids:
            chain = [int(u)]
            while par.get(chain[-1], -1) >= 0 and len(chain) < 64: chain.append(int(par[chain[-1]]))
            anc[int(u)] = chain
        allu = sorted({x for c in anc.values() for x in c}); hist = {u: [] for u in allu}
        for s in sv:
            d = pt(s['name']); idx = {int(u): i for i, u in enumerate(d['uid'].tolist())}
            for u in allu:
                if u in idx:
                    i = idx[u]; hist[u].append((s['iteration'], int(d['target_tag'][i]), int(d['target_index'][i]), d['xyz'][i].double().numpy(), int(d['born_how'][i]), int(d['origin'][i]), int(d['target_released_at'][i])))
        cls = []; fields = dict(uid=[], tag30000=[], how=[], origin=[], lineage_bound_ever=[], released_at=[], last_patch=[], last_patch_dist_m=[], last_patch_tangent_m=[], last_patch_normal_m=[],
                                release_state_tangent_m=[], release_state_normal_m=[], gt_dist_of_last_patch_m=[])
        G = loadz(GT/'reference/B173nb_b10/dense.npz', ['xyz'])['xyz'].astype('f8'); TG_ = cKDTree(G)
        for u in uids:
            u = int(u); h = hist[u]; tag = h[-1][1]; lin = [x for c in anc[u] for x in hist.get(c, [])]
            bound = [x for x in lin if x[1] == 1]; rel = [x for x in lin if x[1] == 2]
            fields['uid'].append(u); fields['tag30000'].append(tag); fields['how'].append(h[-1][4]); fields['origin'].append(h[-1][5]); fields['lineage_bound_ever'].append(bool(bound))
            ra = max([x[6] for x in lin if x[6] >= 0], default=-1); fields['released_at'].append(ra)
            if bound:
                lb = max(bound, key=lambda x: x[0]); v = lb[2]; Xp = h[-1][3][None]
                hn, tn, _ = plane_geom(T, np.array([v]), Xp, T.normal[[v]]); fields['last_patch'].append(v); fields['last_patch_tangent_m'].append(float(tn[0])); fields['last_patch_normal_m'].append(float(hn[0]))
                fields['last_patch_dist_m'].append(float(np.linalg.norm(Xp[0]-T.anchor[v]))); fields['gt_dist_of_last_patch_m'].append(float(TG_.query(T.anchor[v])[0]))
                h1, t1, _ = plane_geom(T, np.array([v]), lb[3][None], T.normal[[v]]); fields['release_state_tangent_m'].append(float(t1[0])); fields['release_state_normal_m'].append(float(h1[0]))
            else:
                for kk in ['last_patch', 'last_patch_dist_m', 'last_patch_tangent_m', 'last_patch_normal_m', 'release_state_tangent_m', 'release_state_normal_m', 'gt_dist_of_last_patch_m']: fields[kk].append(np.nan)
        F = {k: np.asarray(v, 'f8' if k not in ('uid',) else 'i8') for k, v in fields.items()}; save[place] = F
        n = len(uids); lb = F['lineage_bound_ever'] > 0
        rows.append(dict(place=place, place_ko=PLACE_KO[place], gaussians_30000=n, bound_30000=int((F['tag30000'] == 1).sum()), released_30000=int((F['tag30000'] == 2).sum()), background_30000=int((F['tag30000'] == 0).sum()),
                         lineage_bound_ever=int(lb.sum()), self_prior_seed=int((F['how'] == 0).sum()), self_background_seed=int((F['how'] == 1).sum()), child_clone=int((F['how'] == 2).sum()), child_split=int((F['how'] == 3).sum()),
                         released_at_median=med(F['released_at'][F['released_at'] >= 0]), last_patch_dist_m_median=med(F['last_patch_dist_m']), last_patch_tangent_m_median=med(F['last_patch_tangent_m']),
                         last_patch_normal_m_median=med(F['last_patch_normal_m']), release_state_tangent_m_median=med(F['release_state_tangent_m']), gt_dist_of_last_patch_m_median=med(F['gt_dist_of_last_patch_m']),
                         rule='state-based: TRAINLOG records events only inside the 1 m footprint buffer; release iteration = target_released_at; last bound patch from the latest saved state where the uid or an ancestor was bound'))
        print('FLOATER', rows[-1], flush=True)
    GA.mkdir(parents=True, exist_ok=True); np.savez_compressed(GA/'floater_lineage.npz', **{f'{p}__{k}': v for p, d in save.items() for k, v in d.items()}); dtable('ga_floater_lineage', rows)

WINDOWS = [(0, 200), (200, 1000), (1000, 3000), (3000, 6000)]
def grads():
    run = 'sa1_R1_ALS_record6000'; model = RUNS4[run]['model']; files = sorted((model/'trainlog/grads').glob('*.npz'), key=lambda p: int(p.stem))
    E = load_events(model, ('release',)); rel_uid = set(E['release']['uid'].tolist()); rows = []; per = {}
    pps = {pl: place_patches(pl) for pl in ['floor_band', 'floor_control']}
    for f in files:
        it = int(f.stem); g = loadz(f); S = raw_state(model, str(it)); idx = {int(u): i for i, u in enumerate(S['uid'])}
        j = np.array([idx.get(int(u), -1) for u in g['uid']]); ok = j >= 0
        for pl, pp in pps.items():
            lut = {int(v): pp['out'][i] for i, v in enumerate(pp['v'])}; jj = np.flatnonzero(ok)
            b = (S['target_tag'][j[jj]] == 1) & np.isin(S['target_index'][j[jj]], pp['v']); sel = jj[b]
            if not len(sel): continue
            nout = np.array([lut[int(v)] for v in S['target_index'][j[sel]]])
            ever = np.array([int(u) in rel_uid for u in g['uid'][sel]])
            for term in ['photo', 'depth', 'gs2d']:
                vec = g[f'{term}_xyzvec'][sel].astype('f8'); comp = -(vec*nout).sum(1)   # gradient-descent direction along the outward normal (+ = towards the outside / camera side)
                per.setdefault((pl, term), []).append((it, comp, ever, g[f'{term}_xyz'][sel], g[f'{term}_opacity_signed'][sel] if f'{term}_opacity_signed' in g else None))
    for (pl, term), lst in per.items():
        for a, b_ in WINDOWS:
            for grp, gm in [('all', None), ('released_by_6000', True), ('bound_to_6000', False)]:
                parts = [(c if gm is None else c[e == gm]) for it, c, e, _, _ in lst if a < it <= b_ or (a == 0 and it == 0)]
                parts_mag = [(m if gm is None else m[e == gm]) for it, c, e, m, _ in lst if a < it <= b_ or (a == 0 and it == 0)]
                c = np.concatenate(parts) if parts else np.zeros(0); mg = np.concatenate(parts_mag) if parts_mag else np.zeros(0)
                nz = mg > 0; cn = c[nz]; mn = mg[nz]; tg = np.sqrt(np.maximum(mn**2-cn**2, 0))
                rows.append(dict(place=pl, place_ko=PLACE_KO[pl], term={'photo': '광도', 'depth': '깊이', 'gs2d': '2DGS 정규화'}[term], window=f'{a}–{b_}', group=grp, samples=len(c), nonzero_samples=int(nz.sum()),
                                 sum_descent_out=float(c.sum()), median_descent_out_nonzero=med(cn), outward_pct_nonzero=pct(cn > 0) if len(cn) else None, mean_abs_normal_nonzero=float(np.abs(cn).mean()) if len(cn) else None,
                                 median_tangent_abs_nonzero=med(tg), median_magnitude_nonzero=med(mn), normal_share_of_magnitude_median=med(np.abs(cn)/mn) if len(cn) else None,
                                 rule='value = -dL/dxyz . n_out (gradient-descent direction along the outward target normal; + = outside / camera side); nonzero = the Gaussian received a gradient from that iteration view'))
    dtable('ga_grad_normal', rows)
    np.savez_compressed(A4O/'ga/grad_normal.npz', **{f'{pl}__{term}__{k}': np.concatenate([x[i] for x in lst]) if lst else np.zeros(0) for (pl, term), lst in per.items()
                                                    for i, k in [(1, 'descent_out')]}, **{f'{pl}__{term}__iteration': np.concatenate([np.full(len(x[1]), x[0]) for x in lst]) for (pl, term), lst in per.items()},
                        **{f'{pl}__{term}__released_by_6000': np.concatenate([x[2] for x in lst]) for (pl, term), lst in per.items()})
    print('GRADS', len(files), flush=True)

def check6000():
    a = RUNS4['sa1_R1_ALS_record6000']['model']; b = RUNS4['tl_R1_ALS_own']['model']; rows = []
    pp = place_patches('floor_band'); pc = place_patches('floor_control')
    for nm, m in [('사-1(기록 더함)', a), ('기록 판', b)]:
        S = raw_state(m, '6000'); cv = [json.loads(l) for l in (m/'trainlog/curve.jsonl').read_text().splitlines() if '"iteration": 6000,' in l][0]
        rows.append(dict(run=nm, in_range=len(S['uid']), bound=int((S['target_tag'] == 1).sum()), released=int((S['target_tag'] == 2).sum()), background=int((S['target_tag'] == 0).sum()),
                         floor_band_bound=int(((S['target_tag'] == 1) & np.isin(S['target_index'], pp['v'])).sum()), floor_control_bound=int(((S['target_tag'] == 1) & np.isin(S['target_index'], pc['v'])).sum()),
                         scene_gaussians=cv['gaussians'], rgb_loss=cv['rgb'], depth_loss=cv['depth'], total_loss=cv['total'], camera=cv['camera']))
    g = loadz(sorted((a/'trainlog/grads').glob('*.npz'), key=lambda p: int(p.stem))[-1]); mx = 0.
    for t in ['photo', 'depth', 'gs2d']:
        mx = max(mx, float(np.max(np.abs(np.linalg.norm(g[f'{t}_xyzvec'], axis=1)-g[f'{t}_xyz'])/np.maximum(g[f'{t}_xyz'], 1e-12))) if len(g['uid']) else 0.)
    rows.append(dict(run='점검: |부호 벡터| 대 크기 필드 최대 상대 차', value=mx))
    dtable('sa1_check6000', rows); print('CHECK6000', rows, flush=True)

if __name__ == '__main__':
    a = sys.argv[1:]
    {'events': lambda: events(a[1]), 'balance': lambda: balance(a[1]), 'floater': floater, 'grads': grads, 'check6000': check6000}[a[0]]()
