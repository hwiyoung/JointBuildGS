"""Order 4.2 per-state tables, 4.3 fate tables (가~마), 4.4 trajectory selection, per-state curve values (CPU).
GT only for scoring/colouring/selection places (config GT_use). Writes docs tables + payload analysis/*.npz|json."""
import sys
from common import *
from tl_defs import Defs, TAU
from derive_states import scope_mask
from shapely.geometry import shape, Point
import torch
A = O/'analysis'; TB = D/'tables'
Q = lambda v, p=.5: float(np.quantile(v, p)) if len(v) else None
F = lambda v: float(np.mean(v)) if len(v) else None

def saves(): return [json.loads(l) for l in (RUNM/'trainlog/saves.jsonl').read_text().splitlines()]
def ev(kind): p = DER/'events'/f'{kind}.npz'; return loadz(p) if p.exists() else {}
def state(name): return loadz(DER/'gaussians'/f'{name}.npz')
def dumpload(name): return torch.load(RUNM/'trainlog/scene'/f'{name}.pt', map_location='cpu', weights_only=False)

def drawing(name, key):
    """uids that draw the surface: key iterations = PROCFIG lineage over GT rows; others = max alpha*T in two training images."""
    if key and (O/'lineage'/f'{name}.npz').exists():
        z = loadz(O/'lineage'/f'{name}.npz'); return set(z['uid'][z['uid'] >= 0].tolist()), 'lineage_gt_rows'
    p = O/'renders'/name/'data.npz'
    if p.exists():
        z = loadz(p, ['train1_maxid_uid', 'train2_maxid_uid']); u = np.concatenate([z['train1_maxid_uid'].ravel(), z['train2_maxid_uid'].ravel()]); return set(np.unique(u[u >= 0]).tolist()), 'max_alpha_T_two_training_images'
    return set(), 'none'

def main():
    c = cfg(); A.mkdir(parents=True, exist_ok=True); key = set(c['key_iterations']); SV = saves(); names = [s['name'] for s in SV]; it_of = {s['name']: s['iteration'] for s in SV}
    d0 = state('0'); defs = Defs(d0); t = loadz(FT/'targets'/f'{STEM}.npz'); groups = loadz(PF/'work/patch_groups.npz'); prior_xyz = groups['prior_xyz']; up = np.array(c['coordinates']['up'])
    roof_area = float(loadz(PF/'work/prior_clipped.npz', ['area', 'roof'])['area'][loadz(PF/'work/prior_clipped.npz', ['roof'])['roof']].sum())
    E = {k: ev(k) for k in ['birth', 'delete', 'release', 'retarget', 'range', 'opacity_reset', 'link']}
    resets = sorted(set(E['opacity_reset']['iteration'].tolist())) if E['opacity_reset'] else []
    n0 = int(len(dumpload('0')['uid'])); W0 = d0['uid'][d0['group33'] == 1]; Winit = set(d0['init_id'][d0['group33'] == 1].tolist())
    # ---- section band (30,000 unbound) and per-state curve values
    s30 = defs.section(state('30000')); b0 = defs.band(s30)
    counts, filling, lineage, site_rows, curve, shape_rows = [], [], [], [], [], []
    cover0 = {}; drawsets = {}
    for sv in SV:
        name = sv['name']; it = sv['iteration']; d = state(name); s = defs.section(d); b = s['bound']; sd = s['sd']; tin = np.abs(sd) <= TAU
        wall = d['wall']; counts.append(dict(state=name, iteration=it, scene_gaussians=sv['gaussians'], building_gaussians=len(d['xyz']), roof=int((~wall).sum()), wall=int(wall.sum()), roof_prior_area_m2=roof_area))
        h = d['normal_offset'].astype(float); limit = (np.float32(1.96)*d['target_sigma'].astype('f4')).astype(float)
        for tag, tname in [(1, '묶임'), (2, '풀림'), (0, '배경')]:
            for fac, face in [(False, '지붕'), (True, '벽')]:
                for reg in ([-1, 0, 2, 1, 4] if tag == 1 else [-1]):
                    m = (d['target_tag'] == tag) & (wall == fac); m &= (d['judgment'] == reg) if reg != -1 else True; n = int(m.sum()); al = d['opacity'][m]; sc = d['scale'][m]
                    ab = abs(h[m]); lim = limit[m]; inb = (ab <= lim) if tag == 1 else np.array([]); edge = (abs(ab-lim) <= .001) if tag == 1 else np.array([])
                    filling.append(dict(state=name, iteration=it, origin=tname, face=face, judgment='전체' if reg == -1 else {0: '일치', 2: '보정', 1: '보존', 4: '결측'}[reg], n=n, opacity_median=Q(al),
                        opacity_lt_0p1_fraction=F(al < .1), long_axis_median_m=Q(sc.max(1)) if n else None, short_axis_median_m=Q(sc.min(1)) if n else None, density_per_m2=n/roof_area if not fac else None,
                        within_interval_fraction=F(inb) if tag == 1 else None, interval_edge_fraction=F(edge) if tag == 1 else None, target_distance_p50_m=Q(ab) if tag == 1 else None, target_distance_p90_m=Q(ab, .9) if tag == 1 else None))
        mark = d['group33']; ip = d['initial_patch']
        for gp, gname in [(1, '틀린 판정'), (2, '보정 비교')]:
            m = mark == gp; al = d['opacity'][m]; sc = d['scale'][m]; cover = float(np.sum(al.astype(float)*np.pi*sc[:, 0]*sc[:, 1])); xyz = d['xyz'][m]; pn = t['normal'][ip[m]]; anchor = prior_xyz[ip[m]]
            oldz = anchor[:, 2]-np.sum((xyz[:, :2]-anchor[:, :2])*pn[:, :2], axis=1)/pn[:, 2]; near = abs(xyz[:, 2]-oldz) <= .5
            if it == 0: cover0[gp] = cover
            lineage.append(dict(state=name, iteration=it, group=gname, live_init_ids=len(np.unique(d['init_id'][m])), descendants=int(m.sum()), opacity_median=Q(al), coverage_sum_m2=cover,
                coverage_ratio=cover/cover0[gp] if cover0.get(gp) else None, near_old_roof_fraction=F(near), near_old_roof_opacity_median=Q(al[near]), released_fraction=F(d['target_tag'][m] == 2)))
        sig = s['sigma_cm']; row = dict(state=name, iteration=it)
        for lab, mm in [('bound', b), ('unbound', ~b)]:
            ii = s['index'][mm]; sc = d['scale'][ii]
            row.update({f'{lab}_n': int(mm.sum()), f'{lab}_interval_in_pct': F(np.abs(sd[mm]) <= 1.96*sig[mm])*100 if mm.any() else None, f'{lab}_tau_in_pct': F(tin[mm])*100 if mm.any() else None,
                        f'{lab}_below_tau_pct': F(sd[mm] < -TAU)*100 if mm.any() else None, f'{lab}_above_tau_pct': F(sd[mm] > TAU)*100 if mm.any() else None,
                        f'{lab}_distance_median_cm': Q(sd[mm]), f'{lab}_opacity_median': Q(d['opacity'][ii]), f'{lab}_long_axis_median_m': Q(sc.max(1)) if len(ii) else None,
                        f'{lab}_short_axis_median_m': Q(sc.min(1)) if len(ii) else None, f'{lab}_axis_ratio_median': Q(sc.max(1)/np.maximum(sc.min(1), 1e-9)) if len(ii) else None})
        site_rows.append(row)
        for lab, mm in [('bound', d['target_tag'] == 1), ('unbound', d['target_tag'] != 1)]:
            sc = d['scale'][mm]; shape_rows.append(dict(state=name, iteration=it, population='building scope', kind=lab, n=int(mm.sum()), long_median_m=Q(sc.max(1)), short_median_m=Q(sc.min(1)), ratio_median=Q(sc.max(1)/np.maximum(sc.min(1), 1e-9))))
        for lab, mm in [('bound', b), ('unbound', ~b)]:
            sc = d['scale'][s['index'][mm]]; shape_rows.append(dict(state=name, iteration=it, population='correction site', kind=lab, n=int(mm.sum()), long_median_m=Q(sc.max(1)), short_median_m=Q(sc.min(1)), ratio_median=Q(sc.max(1)/np.maximum(sc.min(1), 1e-9))))
        dset, how = drawing(name, it in key and not name.endswith('pre_reset')); drawsets[name] = how
        dr = np.isin(d['uid'][s['index']], np.fromiter(dset, 'i8')) if dset else np.zeros(len(s['index']), bool)
        curve.append(dict(state=name, iteration=it, drawing_rule=how, drawing_site_n=int(dr.sum()), drawing_tau_in_pct=F(tin[dr])*100 if dr.any() else None, drawing_bound_share_pct=F(b[dr])*100 if dr.any() else None,
                          all_site_n=len(sd), all_tau_in_pct=F(tin)*100 if len(sd) else None))
        print('STATE', name, len(d['xyz']), flush=True)
    for nm, rows in [('per_state_counts', counts), ('per_state_filling', filling), ('per_state_lineage', lineage), ('per_state_correction_site', site_rows), ('fate_ma_shape', shape_rows), ('per_state_curve', curve)]: table(nm, rows)
    dump(A/'band.json', dict(b0=b0, c2=defs.c2.tolist(), a1=defs.a1.tolist(), a2=defs.a2.tolist(), hw_cm=defs.hw, tau_cm=TAU, rule='30,000 unbound on correction site, 1 m bin of v with most (prototype)', scientific_verdict=None))
    fates(c, defs, SV, E, d0, n0, W0, Winit, t, prior_xyz, resets, key)

def fates(c, defs, SV, E, d0, n0, W0, Winit, t, prior_xyz, resets, key):
    names = [s['name'] for s in SV]; it_of = {s['name']: s['iteration'] for s in SV}
    dl = E['delete']; dl_w = np.isin(dl['init_id'], np.fromiter(Winit, 'i8')) if dl else None
    # root ancestor from scene-wide links (initial uid == init_id)
    link = E['link']; parent = dict(zip(link['uid'].tolist(), link['parent_uid'].tolist())) if link else {}
    def root(u):
        while u >= n0: u = parent[u]
        return u
    if link:
        memo = {}
        def root2(u):
            path = []
            while u >= n0 and u not in memo: path.append(u); u = parent[u]
            r_ = memo.get(u, u)
            for x in path: memo[x] = r_
            return r_
        inW = np.fromiter((root2(u) in Winit for u in link['uid'].tolist()), bool, len(link['uid'])); wseq = np.sort(link['seq'][inW])
    else: inW = None; wseq = np.zeros(0, 'i8')
    born_w = int(len(wseq))
    # ---- 가: wrong lineage seeds + descendants
    ga = []; traj_needed = {}; opac = {}
    deleted_w_uids = set(dl['uid'][dl_w].tolist()) if dl else set()
    for sv in SV:
        name, it = sv['name'], sv['iteration']; d = state(name); m = d['group33'] == 1; z = dumpload(name); zin = z['inside'].numpy(); zinit = z['init_id'].numpy().astype('i8')
        out_alive = int((np.isin(zinit, np.fromiter(Winit, 'i8')) & ~zin).sum()); row = dict(state=name, iteration=it, alive_inside_bound=int((m & (d['target_tag'] == 1)).sum()), alive_inside_released=int((m & (d['target_tag'] == 2)).sum()), alive_outside=out_alive)
        upto = dl_w & (dl['seq'] <= sv['seq']) if dl else None
        for r, rn in {1: 'opacity', 2: 'world_size', 3: 'screen_size', 4: 'other', 5: 'split_parent'}.items(): row[f'deleted_{rn}_cum'] = int((upto & (dl['reason'] == r)).sum()) if dl else 0
        nb = int(np.searchsorted(wseq, sv['seq'], side='right'))
        row['born_cum'] = nb; row['deleted_inside_cum'] = sum(row[f'deleted_{k}_cum'] for k in ['opacity', 'world_size', 'screen_size', 'other', 'split_parent'])
        row['unrecorded_outside_deleted_cum'] = len(W0)+nb-row['alive_inside_bound']-row['alive_inside_released']-row['alive_outside']-row['deleted_inside_cum']
        dw = np.isin(d['uid'], np.fromiter(deleted_w_uids, 'i8')) if deleted_w_uids else np.zeros(len(d['uid']), bool)
        op = d['opacity'][dw]; row.update(to_be_deleted_alive_inside=int(dw.sum()), to_be_deleted_opacity_p25=Q(op, .25), to_be_deleted_opacity_median=Q(op), to_be_deleted_opacity_p75=Q(op, .75))
        ga.append(row); del z
    if dl:
        x = dl['xyz'][dl_w].astype(float); ip = loadz(FT/'stage1'/STEM/'seeds.npz', ['patch'])['patch'][dl['init_id'][dl_w]]; pn = t['normal'][ip]; anchor = prior_xyz[ip]
        oldz = anchor[:, 2]-np.sum((x[:, :2]-anchor[:, :2])*pn[:, :2], axis=1)/pn[:, 2]; near = abs(x[:, 2]-oldz) <= .5
        ga_summary = dict(initial_seeds=len(W0), born_total=born_w, deleted_inside=int(dl_w.sum()), by_reason={int(r): int(n) for r, n in zip(*np.unique(dl['reason'][dl_w], return_counts=True))},
                          near_old_roof_at_deletion_fraction=F(near), seeds_themselves=None)
        # the 3,525 seeds themselves
        sd_ = dict(zip(dl['uid'][dl_w].tolist(), dl['reason'][dl_w].tolist())); last = dumpload('30000'); lu = last['uid'].numpy(); lin = last['inside'].numpy(); ltag = last['target_tag'].numpy()
        pos = {u: i for i, u in enumerate(lu.tolist())}; fate = {}
        for u in W0.tolist():
            if u in pos: fate[u] = ('alive_inside_' + ('bound' if ltag[pos[u]] == 1 else 'released')) if lin[pos[u]] else 'alive_outside'
            elif u in sd_: fate[u] = 'deleted_' + {1: 'opacity', 2: 'world_size', 3: 'screen_size', 4: 'other', 5: 'split_parent'}[int(sd_[u])]
            else: fate[u] = 'deleted_outside_unrecorded'
        ga_summary['seeds_themselves'] = {k: sum(1 for v in fate.values() if v == k) for k in sorted(set(fate.values()))}
    else: ga_summary = {}
    table('fate_ga_wrong_lineage', ga); dump(A/'fate_ga.json', dict(ga_summary, scientific_verdict=None))
    # ---- 나
    na = []; z7 = dumpload('7000'); u7 = z7['uid'].numpy(); pos7 = {u: i for i, u in enumerate(u7.tolist())}; x7 = z7['xyz'].double().numpy(); del z7
    bp = {u: p for u, p in zip(E['birth']['uid'].tolist(), E['birth']['parent_xyz'].astype(float))} if E['birth'] else {}
    lin30 = loadz(O/'lineage/30000.npz') if (O/'lineage/30000.npz').exists() else None
    cats30 = {}
    for name in ['15000', '30000']:
        d = state(name); s = defs.section(d); tin = np.abs(s['sd']) <= TAU; sel = (~s['bound']) & tin; uids = d['uid'][s['index'][sel]]; born = d['born_at'][s['index'][sel]]
        cat = []
        for u, bt in zip(uids.tolist(), born.tolist()):
            if u in pos7:
                sdv, _, _ = defs.signed_points(x7[pos7[u]][None]); ok = np.isfinite(sdv[0]) and abs(sdv[0]) <= TAU; cat.append('2_stayed' if ok else ('1_moved_in_from_site_out_of_tau' if np.isfinite(sdv[0]) else '1_moved_in_from_off_site'))
            elif bt > 7000:
                if u in bp:
                    sp, _, _ = defs.signed_points(bp[u][None]); cat.append('3_new_parent_in_tau' if np.isfinite(sp[0]) and abs(sp[0]) <= TAU else '3_new_parent_out_of_tau')
                else: cat.append('3_new_parent_unknown')
            else: cat.append('existed_before_7000_not_alive_at_7000?')
        cats = {k: cat.count(k) for k in sorted(set(cat))}; row = dict(state=name, unbound_tau_in_on_site=len(cat), **cats)
        if name == '30000':
            cats30 = dict(zip(uids.tolist(), cat))
            if lin30 is not None:
                g2 = lin30['group'] == 2; att = lin30['uid'][g2]; ok = att >= 0; row['comparison_rows_attributed'] = int(ok.sum())
                lab = np.array([cats30.get(int(u), 'other') for u in att[ok]]); d30b = set(d['uid'][d['target_tag'] == 1].tolist())
                lab = np.array(['bound' if int(u) in d30b else l for u, l in zip(att[ok], lab)])
                for k in sorted(set(lab)): row[f'draw_share_{k}_pct'] = float((lab == k).mean()*100)
        na.append(row)
    table('fate_na_unbound_tau_in', na)
    # ---- 다: release events
    r = E['release']; da = []
    if r:
        z30 = dumpload('30000'); re30 = z30['release_event'].numpy(); maxid = int(r['event_id'].max())+1; w30 = np.bincount(re30[re30 >= 0], minlength=maxid); del z30
        d30 = state('30000'); s = defs.section(d30); site_ev = d30['release_event'][s['index']]; ws = np.bincount(site_ev[site_ev >= 0], minlength=maxid)
        bins = [(0, 100), (101, 600), (601, 3000), (3001, 7000), (7001, 15000), (15001, 30000)]
        for lo, hi in bins:
            for case in [0, 1]:
                for birth in [0, 1, 2, 3]:
                    for cause in [0, 1]:
                        m = (r['iteration'] >= lo) & (r['iteration'] <= hi) & (r['case'] == case) & (r['birth_category'] == birth) & (r['cause'] == cause); e = r['event_id'][m]
                        da.append(dict(interval=f'{lo}-{hi}', case={0: '가', 1: '나'}[case], birth={0: '처음 씨앗', 1: '이번 복제', 2: '이번 분할', 3: '그 전부터'}[birth], cause={0: '밀도 제어', 1: '100회 점검'}[cause],
                                       events=int(m.sum()), descendants_30000=int(w30[e].sum()), site_descendants_30000=int(ws[e].sum())))
        early = r['iteration'] <= 3000; da_summary = dict(events=len(r['event_id']), before_3000=int(early.sum()), before_3000_split_now=int((early & (r['birth_category'] == 2)).sum()), before_3000_initial=int((early & (r['birth_category'] == 0)).sum()),
            initial_longest_axis_median_m=Q(r['longest_axis_m'][early & (r['birth_category'] == 0)]), inside_scope=int(r['inside'].sum()))
    else: da_summary = {}
    table('fate_da_release', da); dump(A/'fate_da.json', dict(da_summary, scientific_verdict=None))
    # ---- 라: bound on correction site
    ra = []; prev = None
    for sv in SV:
        d = state(sv['name']); s = defs.section(d); n = int(s['bound'].sum()); row = dict(state=sv['name'], iteration=sv['iteration'], bound_on_site=n, opacity_reset=sv['iteration'] in resets)
        if prev is not None:
            lo, hi = prev['seq'], sv['seq']
            for kind in ['birth', 'delete']:
                e = E[kind]
                if not e: continue
                m = (e['seq'] > lo) & (e['seq'] <= hi) & (e['tag'] == 1); dd, _ = defs.tr.query(e['xyz'][m][:, :2].astype(float)) if m.any() else (np.zeros(0), None); on = dd <= .25
                if kind == 'birth':
                    hw = e['how'][m][on]; row.update(born_clone=int((hw == 2).sum()), born_split=int((hw == 3).sum()))
                else:
                    rs = e['reason'][m][on]
                    for rr, rn in {1: 'opacity', 2: 'world_size', 3: 'screen_size', 4: 'other', 5: 'split_parent'}.items(): row[f'deleted_{rn}'] = int((rs == rr).sum())
            rel = E['release']
            if rel:
                m = (rel['seq'] > lo) & (rel['seq'] <= hi)
                if m.any():
                    dd, _ = defs.tr.query(rel['xyz'][m][:, :2].astype(float)); row['released_on_site'] = int((dd <= .25).sum())
                else: row['released_on_site'] = 0
        ra.append(row); prev = sv
    table('fate_ra_bound_site', ra)
    # ---- 4.4 trajectories
    selections(c, defs, SV, E, d0, W0, cats30, lin30)

def selections(c, defs, SV, E, d0, W0, cats30, lin30):
    box = json.loads((R/'docs/experiments/phd/main_gtjudge_v1/tables/addendum10/c1_boxes.json').read_text()); poly = shape(dict(type='Polygon', coordinates=[box['panel1_box_corners_local_xy']+[box['panel1_box_corners_local_xy'][0]]]))
    dl = E['delete']; death = dict(zip(dl['uid'].tolist(), dl['iteration'].tolist())) if dl else {}
    w = d0['group33'] == 1; cand = [int(u) for u, p in zip(d0['uid'][w], d0['xyz'][w]) if poly.contains(Point(float(p[0]), float(p[1])))]
    life = sorted(cand, key=lambda u: (-death.get(u, 10**9), u)); pick1 = life[0] if life else None
    moved = [u for u, k in cats30.items() if k.startswith('1_')]; pick2 = None; rule2 = None
    if moved and lin30 is not None:
        att = lin30['uid'][lin30['group'] == 2]; cnt = {u: int((att == u).sum()) for u in moved}; best = max(cnt.values())
        if best > 0: pick2 = min(u for u, v in cnt.items() if v == best); rule2 = 'largest 30,000 drawing share'
    d30 = state('30000'); s = defs.section(d30)
    if pick2 is None and moved:
        sdm = {int(u): abs(v) for u, v in zip(d30['uid'][s['index']], s['sd'])}; pick2 = min(moved, key=lambda u: (sdm.get(u, 1e9), u)); rule2 = 'smallest |distance| at 30,000'
    ok = (np.abs(s['sd']) <= TAU) & (d30['born_how'][s['index']] == 1); pick3 = int(d30['uid'][s['index'][ok]].min()) if ok.any() else None
    picks = dict(wrong_lineage=pick1, moved_in=pick2, background=pick3)
    tr = {k: [] for k in picks}
    for sv in SV:
        z = dumpload(sv['name']); u = z['uid'].numpy(); pos = {x: i for i, x in enumerate(u.tolist())}
        for k, uid in picks.items():
            if uid is None: continue
            if uid in pos:
                p = z['xyz'][pos[uid]].double().numpy(); dd, nn = defs.tr.query(p[:2]); sd = float((p-defs.tx[nn])@defs.nrm(p)*100)
                tr[k].append(dict(iteration=sv['iteration'], state=sv['name'], alive=True, sd_cm=sd, horizontal_to_site_m=float(dd), tag=int(z['target_tag'][pos[uid]])))
            else: tr[k].append(dict(iteration=sv['iteration'], state=sv['name'], alive=False))
        del z
    dump(A/'trajectories.json', dict(picks=picks, rules=dict(wrong_lineage='initial wrong-lineage seed inside c1 panel1 case box, longest lived, tie smallest uid', moved_in=rule2, background='initial background alive at 30,000 on correction site within τ, smallest uid'),
         death_iteration={k: death.get(v) for k, v in picks.items() if v is not None}, candidates_in_box=len(cand), trajectories=tr, distance_rule='nearest reference target (no 0.25 m restriction for trajectories), prototype nrm', scientific_verdict=None))
    print('PICKS', picks, flush=True)

if __name__ == '__main__': main()
