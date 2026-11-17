"""Work ga (order 3) + record coverage (order 2.2): where the problem-making Gaussians come from and whether the same individuals stay. CPU, states runs.
  coverage <run> <place> <control>   : record range over the group heights, signed gradients present  -> tables/rec_coverage_<run>.csv
  seeds <run> <place> <control> [st] : order 3.1 first seeds of the group at <st> (default 30000)          -> tables/ga_seeds_<run>_*.csv
  flows <run> <place> <control>      : order 3.2 interval in/out with the balance start + in - out = end    -> tables/ga_flows_<run>_*.csv
  resets <run> <place> <control>     : order 3.3 survival of the first prune check after each reset          -> tables/ga_resets_<run>_*.csv"""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1/addendum5')
from a5_common import *
GA5 = A5O/'ga'

def it_of(st): return int(str(st).split('_')[0])

# runs whose record range (states) does not cover the place: read the full-scene dumps (trainlog/scene/<name>.pt, same fields) instead (issues.md)
SCENE_STATE_RUNS = {'sb3_R1_LoD2_record'}
def state_of(run, st):
    if run not in SCENE_STATE_RUNS: return raw_state(run_model(run), st)
    import torch
    s = torch.load(run_model(run)/'trainlog/scene'/f'{st}.pt', map_location='cpu', weights_only=False)
    return {k: (v.numpy() if hasattr(v, 'numpy') else v) for k, v in s.items() if k in ('xyz', 'origin', 'init_id', 'target_tag', 'target_index', 'uid', 'parent_uid', 'born_at', 'born_how', 'release_event', 'target_released_at')}
def scene_names(run): return {p.stem for p in (run_model(run)/'trainlog/scene').glob('*.pt')}

def groups_at(run, st, bands):
    S = state_of(run, st); out = {}
    for nm, B in bands.items():
        m, dn, k = member_of(B, S, it_of(st)); out[nm] = dict(rows=np.flatnonzero(m), dn=dn[m], kind=kind_of5(S['target_tag'][m], S['target_index'][m], B.vset), stage_used=k)
    return S, out

RUNCUR = {}
def bands_of(place, control): return groups_for(place, control, RUNCUR['run'])

def available(run):
    return {p.stem for p in (run_model(run)/'trainlog/states').glob('*.npz')}

def coverage(run, place, control):
    bands = bands_of(place, control); rows = []; g = sorted((run_model(run)/'trainlog/grads').glob('*.npz'), key=lambda p: int(p.stem))
    gz = loadz(g[-1]) if g else {}; si = start_info(run)
    for nm, B in bands.items():
        if not isinstance(B, Band):
            rows.append(dict(run=run, group=nm, place=place if nm == '문제 무리' else control, rule='group not a height band: record range checked on the group Gaussians (see ga_flows: left_record_range)')); continue
        P = B.P
        for h in [.2, .5, 1., 1.5, 2., 2.5, 3.]:
            X = P['anchor']+h*P['out']; rows.append(dict(run=run, group=nm, place=place if nm == '문제 무리' else control, height_m=h, points=len(X), in_record_range_pct=pct(record_region_mask(run, X))))
    rows.append(dict(run=run, group='기록', place='', height_m=None, points=None, in_record_range_pct=None, region_file=si['region_file'], gradients=bool(si.get('gradients')),
                     signed=any(k.endswith('_signed') for k in getattr(gz, 'files', list(gz))), grad_files=len(g), last_grad_iteration=int(g[-1].stem) if g else None,
                     state_files=len(available(run)), size_gradient='기록 없음(xyz·불투명도만)'))
    table5(f'rec_coverage_{run}', rows); print('COVERAGE', run, flush=True)

def seeds(run, place, control, st='30000'):
    model = run_model(run); bands = bands_of(place, control); S, G = groups_at(run, st, bands)
    import torch
    z0 = torch.load(model/'trainlog/scene/0.pt', map_location='cpu', weights_only=False) if (model/'trainlog/scene/0.pt').exists() else None
    if z0 is None: raise SystemExit('no 0.pt full scene dump for seed sizes')
    ini = z0['init_id'].numpy(); assert np.array_equal(ini, np.arange(len(ini)))
    s_or = z0['origin'].numpy(); s_xyz = z0['xyz'].double().numpy(); s_size = torch.exp(z0['scaling']).max(1).values.numpy()
    large = (s_or == 0) & (s_size > 1.)
    ref = a11_ref(RUNS4[run]['stem']); TG = cKDTree(ref['xyz'].astype('f8'))
    rows = []; pts = {}
    for nm, g in G.items():
        r = g['rows']; iid = S['init_id'][r].astype('i8'); n = len(r); B = bands[nm]
        sdn = dist_seed(B, s_xyz[iid]); sg, _ = TG.query(s_xyz[iid], distance_upper_bound=50.)
        u, c = np.unique(iid, return_counts=True); top = np.sort(c)[::-1]
        base = dict(run=run, state=st, group=nm, gaussians=n, small_group=n < 30)
        for k in range(4): base[f'kind_{KIND_KO[k]}'] = int((g['kind'] == k).sum())
        rows.append(dict(base, value='씨앗 종류', prior_seed_pct=pct(s_or[iid] == 1), background_seed_pct=pct(s_or[iid] == 0)))
        rows.append(dict(base, value='씨앗 처음 크기(m)', q25_q50_q75=q4(s_size[iid]), gt_1m_pct=pct(s_size[iid] > 1.)))
        rows.append(dict(base, value='씨앗 처음 자리: 목표면 법선 거리(m)', q25_q50_q75=q4(sdn), within_tangent_pct=pct(np.isfinite(sdn)), rule='nan = no place point within 0.25 m tangent (seed not above the place)'))
        rows.append(dict(base, value='씨앗 처음 자리: 참값 점까지 거리(m)', q25_q50_q75=q4(np.where(np.isfinite(sg), sg, np.nan)), gt_1m_pct=pct(~(sg <= 1.))))
        rows.append(dict(base, value='씨앗 하나의 후손 수', seeds=len(u), q25_q50_q75=q4(c), top10_seed_share_pct=100*float(top[:10].sum())/max(n, 1), top1=int(top[0]) if n else 0))
        rows.append(dict(base, value='처음부터 큰 배경 씨앗(1 m 초과)의 후손', pct=pct(large[iid]), seeds_large=int(np.isin(u, np.flatnonzero(large)).sum()), rule='jbgs_target.py initial_large_background: origin 0 and max initial scale > 1 m (0.pt)'))
        for k in range(4):
            mk = g['kind'] == k
            if mk.any(): rows.append(dict(base, value=f'종류별: {KIND_KO[k]}', n=int(mk.sum()), background_seed_pct=pct(s_or[iid[mk]] == 0), large_bg_pct=pct(large[iid[mk]]), seed_size_median=med(s_size[iid[mk]])))
        pts[nm] = dict(uid=S['uid'][r], init_id=iid, kind=g['kind'], dn=g['dn'], xyz=S['xyz'][r], seed_xyz=s_xyz[iid], seed_size=s_size[iid], seed_origin=s_or[iid], seed_dn=sdn, seed_gt=sg)
    GA5.mkdir(parents=True, exist_ok=True); savez(GA5/f'seeds_{run}_{st}.npz', **{f'{"problem" if nm == "문제 무리" else "control"}__{k}': v for nm, d in pts.items() for k, v in d.items()})
    table5(f'ga_seeds_{run}_{st}', rows); print('SEEDS', run, flush=True)

def flows(run, place, control):
    c = cfg5(); model = run_model(run); bands = bands_of(place, control); av = scene_names(run) if run in SCENE_STATE_RUNS else available(run); E = load_events(model, ('delete', 'birth', 'range'))
    de = E['delete']; dpos = {}
    for i, u in enumerate(de['uid'].tolist()): dpos[u] = i
    rows = []
    for a, b in c['intervals']:
        sa = '0' if a == 0 else state_name(a); sb = state_name(b)
        if sa not in av or sb not in av: continue
        S0, G0 = groups_at(run, sa, bands); S1, G1 = groups_at(run, sb, bands); i0 = {int(u): i for i, u in enumerate(S0['uid'])}
        for nm in bands:
            A = set(S0['uid'][G0[nm]['rows']].tolist()); Bm = S1['uid'][G1[nm]['rows']]; B_ = set(Bm.tolist()); rowB = dict(zip(Bm.tolist(), G1[nm]['rows']))
            stay = A & B_; new = B_ - A; gone = A - B_
            born = [u for u in new if a < int(S1['born_at'][rowB[u]]) <= b]; moved = [u for u in new if u not in set(born)]
            how = np.array([int(S1['born_how'][rowB[u]]) for u in born], 'i1')
            moved_known = [u for u in moved if u in i0]; dist = [float(np.linalg.norm(S1['xyz'][rowB[u]].astype('f8')-S0['xyz'][i0[u]].astype('f8'))) for u in moved_known]
            # parents of the newborn
            par = [int(S1['parent_uid'][rowB[u]]) for u in born]; pin = [p in A for p in par]; pk = []
            for p in par:
                if p in i0: pk.append(int(kind_of5([S0['target_tag'][i0[p]]], [S0['target_index'][i0[p]]], bands[nm].vset)[0]))
                else: pk.append(-1)
            # the gone
            iu1 = {int(u): i for i, u in enumerate(S1['uid'])}; dr = []
            for u in gone:
                if u in dpos and a < int(de['iteration'][dpos[u]]) <= b: dr.append(int(de['reason'][dpos[u]]))
                elif u in iu1: dr.append(-1)   # still exists, outside the group
                else: dr.append(-2)            # left the record range (no delete event)
            dr = np.array(dr, 'i1'); age = S1['born_at'][G1[nm]['rows']]
            r = dict(run=run, group=nm, interval=f'{a}–{b}', start=len(A), end=len(B_), stayed=len(stay), born_clone=int((how == 2).sum()), born_split=int((how == 3).sum()),
                     moved_in=len(moved), moved_in_from_outside_range=len(moved)-len(moved_known), moved_in_distance_m_q=q4(dist),
                     deleted_opacity=int((dr == 1).sum()), deleted_size=int(((dr == 2) | (dr == 3)).sum()), deleted_split_parent=int((dr == 5).sum()), deleted_other=int((dr == 4).sum()),
                     moved_out=int((dr == -1).sum()), left_record_range=int((dr == -2).sum()))
            r['balance_residual'] = r['start']+r['born_clone']+r['born_split']+r['moved_in']-(len(gone))-r['end']
            r['gone_total'] = len(gone)
            if run in SCENE_STATE_RUNS: r['deleted_no_event'] = r.pop('left_record_range')   # full scene: gone = deleted; the delete event is missing outside the record range
            r['parent_in_group_pct'] = pct(np.array(pin)) if pin else None
            for k in range(4): r[f'parent_kind_{KIND_KO[k]}'] = int(sum(1 for x in pk if x == k))
            r['parent_born_in_interval_or_outside'] = int(sum(1 for x in pk if x == -1))
            for k in range(4): r[f'end_kind_{KIND_KO[k]}'] = int((G1[nm]['kind'] == k).sum())
            r['end_born_at_q'] = q4(age); r['small_group'] = len(B_) < 30
            rows.append(r)
    table5(f'ga_flows_{run}', rows); print('FLOWS', run, flush=True)

def resets(run, place, control):
    c = cfg5(); model = run_model(run); bands = bands_of(place, control); av = scene_names(run) if run in SCENE_STATE_RUNS else available(run); de = load_events(model, ('delete',))['delete']; rows = []
    vb = np.unique(place_points5(place)['v']) if place == 'floor_band' else None
    for rs in c['resets']:
        st = f'{rs}_pre_reset'
        if st not in av or int(RUNS4[run]['last']) < rs+100: continue   # the first prune check after the reset must be inside the run
        S, G = groups_at(run, st, bands); win = (de['iteration'] > rs) & (de['iteration'] <= rs+100); du = de['uid'][win]; dre = de['reason'][win]
        rule = 'delete events in (reset, reset+100]'
        if run in SCENE_STATE_RUNS:   # events cover the record range only: absent from the next full-scene dump instead (500 iterations after, not 100)
            nxt = state_of(run, str(rs+500)); du = np.setdiff1d(S['uid'], nxt['uid']); dre = np.full(len(du), -1); rule = f'absent from scene dump {rs+500} (no delete events outside the record range)'
        groups = {nm: S['uid'][g['rows']] for nm, g in G.items()}
        if vb is not None: groups['바닥에 묶인 가우시안(덧붙임 4)'] = S['uid'][(S['target_tag'] == 1) & np.isin(S['target_index'], vb[vb >= 0])]
        for nm, us in groups.items():
            dd = np.isin(us, du); op = np.isin(us, du[dre == 1])
            r = dict(run=run, reset=rs, group=nm, before=len(us), survived_pct=pct(~dd), deleted_any=int(dd.sum()), deleted_opacity=int(op.sum()), small_group=len(us) < 30,
                     group_stage_used=G[nm]['stage_used'] if nm in G else None, deletion_rule=rule)
            if nm in G:
                for k in range(4):
                    mk = G[nm]['kind'] == k; r[f'{KIND_KO[k]}_n'] = int(mk.sum()); r[f'{KIND_KO[k]}_survived_pct'] = pct(~dd[mk]) if mk.any() else None
            rows.append(r)
    table5(f'ga_resets_{run}', rows); print('RESETS', run, flush=True)

if __name__ == '__main__':
    a = sys.argv[1:]; RUNCUR['run'] = a[1]
    {'coverage': coverage, 'seeds': seeds, 'flows': flows, 'resets': resets}[a[0]](*a[1:])
