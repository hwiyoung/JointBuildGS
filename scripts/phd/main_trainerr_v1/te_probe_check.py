"""Stage-0 unit checks for r28 (order 2.4): default = r23, gt targets = r25, recording invariance, numbers and events, switches.
Adapted from TRAINLOG probe_check.py (load/compare/events/tracking/quantities unchanged except the range test = region voxels).
GPU rule B (TRAINLOG unit_check_v2, two runs per setting as the order's alternative test): for each quantity at 100/200/300,
median over cross pairs <= maximum over same-setting pairs. Replay byte tests come from te_replay.py."""
import glob, itertools
import torch
from common import *
P = O/'probe'; ITS = [100, 200, 300]
PARAM = {'xyz': 1, 'f_dc': 2, 'scaling': 4, 'rotation': 5, 'opacity': 6}
def load(label, it):
    s = torch.load(P/label/f'model/jbgs_complete/iteration_{it}/checkpoint.pth', map_location='cpu', weights_only=False)
    m = s['model']; out = {k: m[i] for k, i in PARAM.items()}
    out.update({k: v for k, v in s['target_r6']['meta'].items()}); out['origin'] = s['origin']; out['init_id'] = s['init_id']
    out['adam_xyz_avg'] = m[10]['state'][0]['exp_avg'] if 0 in m[10]['state'] else None
    out['train_order'] = s['train_order']; out['viewpoint_stack'] = s['viewpoint_stack']
    out['rng_python'] = s['rng']['python']; out['rng_torch'] = s['rng']['torch_cpu']
    return out

def compare(a, b):
    r = dict(count_a=len(a['xyz']), count_b=len(b['xyz']), count_equal=len(a['xyz']) == len(b['xyz']),
             camera_stack_equal=a['viewpoint_stack'] == b['viewpoint_stack'], rng_python_equal=a['rng_python'] == b['rng_python'],
             rng_torch_equal=bool(torch.equal(a['rng_torch'], b['rng_torch'])))
    for k in ['xyz', 'scaling', 'opacity', 'rotation', 'f_dc', 'target_tag', 'target_index', 'target_released_at', 'origin', 'init_id']:
        if r['count_equal']:
            x, y = a[k], b[k]; r[f'{k}_bytes_equal'] = bool(torch.equal(x, y))
            if x.dtype.is_floating_point: r[f'{k}_max_abs_diff'] = float((x.double()-y.double()).abs().max()) if len(x) else 0.
            else: r[f'{k}_mismatch'] = int((x != y).sum())
        else:
            r[f'{k}_bytes_equal'] = False
            if not a[k].dtype.is_floating_point: r[f'{k}_value_counts_a'] = {int(v): int(c) for v, c in zip(*torch.unique(a[k], return_counts=True))} if k == 'target_tag' else None
    if not r['count_equal']:
        r['target_tag_counts_a'] = {int(v): int(c) for v, c in zip(*torch.unique(a['target_tag'], return_counts=True))}
        r['target_tag_counts_b'] = {int(v): int(c) for v, c in zip(*torch.unique(b['target_tag'], return_counts=True))}
    return r

def events(label):
    ev = {}
    for f in sorted(glob.glob(str(P/label/'model/trainlog/events/*.npz'))):
        kind = Path(f).name.rsplit('_', 1)[0]; z = loadz(f); ev.setdefault(kind, []).append(z)
    return {k: {c: np.concatenate([p[c] for p in v]) for c in v[0]} for k, v in ev.items()}

def tracking(label, inside_ref):
    root = P/label/'model/trainlog'; saves = [json.loads(l) for l in (root/'saves.jsonl').read_text().splitlines()]
    ev = events(label); out = dict(label=label, saves=[s['name'] for s in saves], failures=[])
    prev = None; seen_dead = set(); max_uid = -1; balance = []
    for s in saves:
        st = loadz(root/'states'/f'{s["name"]}.npz'); sc = torch.load(root/'scene'/f'{s["name"]}.pt', map_location='cpu', weights_only=False)
        uid_all = sc['uid'].numpy(); xyz = sc['xyz'].double().numpy()
        if len(np.unique(uid_all)) != len(uid_all): out['failures'].append(f'{s["name"]}: duplicate uid in scene')
        if len(np.unique(st['uid'])) != len(st['uid']): out['failures'].append(f'{s["name"]}: duplicate uid in state')
        if not np.array_equal(uid_all[st['full_gaussian_index']], st['uid']): out['failures'].append(f'{s["name"]}: state uid != scene uid')
        ref = inside_ref(xyz)
        mism = int((ref != sc['inside'].numpy()).sum())
        if mism: out['failures'].append(f'{s["name"]}: inside flag vs region voxel mismatch {mism}')
        if seen_dead & set(uid_all.tolist()): out['failures'].append(f'{s["name"]}: deleted uid reappears')
        if 'release_event' in sc and 'release' in ev:
            ids = set(np.unique(sc['release_event'].numpy()[sc['release_event'].numpy() >= 0]).tolist())
            if not ids <= set(ev['release']['event_id'].tolist()): out['failures'].append(f'{s["name"]}: release_event not recorded')
            out.setdefault('release_event_checked', 0); out['release_event_checked'] += 1
        if 'link' in ev and prev is not None:
            newu = set(uid_all[uid_all > prev[0].max()].tolist())
            if not newu <= set(ev['link']['uid'].tolist()): out['failures'].append(f'{s["name"]}: new uid missing from link events')
            par = dict(zip(ev['link']['uid'].tolist(), ev['link']['parent_uid'].tolist()))
            if 'parent_uid' in sc and any(par[u] != pu for u, pu in zip(uid_all.tolist(), sc['parent_uid'].numpy().tolist()) if u in newu): out['failures'].append(f'{s["name"]}: link parent mismatch')
            out.setdefault('link_checked', 0); out['link_checked'] += 1
        if prev is not None:
            pu, pst, pseq = prev
            gone = set(pu.tolist()) - set(uid_all.tolist()); seen_dead |= gone
            new = uid_all[uid_all > pu.max()]
            if len(new) and new.min() <= max_uid: out['failures'].append(f'{s["name"]}: new uid not above previous max')
            born = st['born_at'] > (saves[saves.index(s)-1]['iteration'] if s['name'] != saves[saves.index(s)-1]['name'] else -1)
            par = st['parent_uid'][(st['born_how'] >= 2) & np.isin(st['uid'], new)]
            alive_or_new = set(pu.tolist()) | set(new.tolist())
            missing = [int(p) for p in par if int(p) not in alive_or_new]
            if missing: out['failures'].append(f'{s["name"]}: {len(missing)} parent_uid not alive at previous state')
            sel = {k: (v['seq'] > pseq) & (v['seq'] <= s['seq']) for k, v in ev.items()}
            nb = int(sel['birth'].sum()) if 'birth' in sel else 0; nd = int(sel['delete'].sum()) if 'delete' in sel else 0
            ein = int((ev['range']['enter'][sel['range']] == 1).sum()) if 'range' in sel else 0
            eout = int((ev['range']['enter'][sel['range']] == 0).sum()) if 'range' in sel else 0
            ok = len(st['uid']) == len(pst) + nb - nd + ein - eout
            setok = None
            if 'birth' in ev or 'range' in ev:
                cur = set(pst.tolist()); ops = []
                for kind, sign in [('birth', 1), ('delete', -1), ('range', 0)]:
                    if kind in ev:
                        m = sel[kind]; u = ev[kind]['uid'][m]; q = ev[kind]['seq'][m]
                        sg = np.full(len(u), sign) if sign else np.where(ev['range']['enter'][m] == 1, 1, -1)
                        ops.append(np.c_[q, u, sg])
                ops = np.concatenate(ops) if ops else np.zeros((0, 3), 'i8'); ops = ops[np.argsort(ops[:, 0], kind='stable')]
                bad = 0
                for _, u, sg in ops:
                    if sg == 1:
                        bad += int(u) in cur; cur.add(int(u))
                    else:
                        bad += int(u) not in cur; cur.discard(int(u))
                setok = (cur == set(st['uid'].tolist())) and bad == 0
            balance.append(dict(state=s['name'], before=len(pst), births=nb, deletions=nd, enter=ein, exit=eout, after=len(st['uid']), count_equal=ok, uid_set_equal=setok))
            if not ok or setok is False: out['failures'].append(f'{s["name"]}: event balance failed')
        max_uid = max(max_uid, int(uid_all.max())); prev = (uid_all, st['uid'], s['seq'])
    out['balance'] = balance
    out['event_counts'] = {k: int(len(v['seq'])) for k, v in ev.items()}
    if 'delete' in ev: out['delete_reasons'] = {int(k): int(v) for k, v in zip(*np.unique(ev['delete']['reason'], return_counts=True))}
    if 'birth' in ev: out['birth_how'] = {int(k): int(v) for k, v in zip(*np.unique(ev['birth']['how'], return_counts=True))}
    return out

def quantities(a, b):
    q = dict(count=abs(len(a['xyz'])-len(b['xyz'])), bound=abs(int((a['target_tag'] == 1).sum())-int((b['target_tag'] == 1).sum())))
    ta = {t: int((a['target_tag'] == t).sum()) for t in range(3)}; tb = {t: int((b['target_tag'] == t).sum()) for t in range(3)}; q['tag_l1'] = sum(abs(ta[t]-tb[t]) for t in range(3))
    if len(a['xyz']) == len(b['xyz']):
        for k in ['xyz', 'scaling', 'opacity']: q[k+'_max'] = float((a[k].double()-b[k].double()).abs().max())
        q['tag_mismatch'] = int((a['target_tag'] != b['target_tag']).sum()); q['index_mismatch'] = int((a['target_index'] != b['target_index']).sum())
    return q


def region_inside(stem):
    reg = json.loads((O/'region'/f'{stem}.json').read_text()); v = float(reg['voxel_m']); lo = np.asarray(reg['grid_origin']); shape = tuple(reg['grid_shape']); occ = np.zeros(shape, bool)
    for b in reg['boxes']:
        b = np.asarray(b[:6], float); i0 = np.floor((b[[0, 2, 4]]-lo)/v+1e-9).astype(int); i1 = np.ceil((b[[1, 3, 5]]-lo)/v-1e-9).astype(int); occ[i0[0]:i1[0], i0[1]:i1[1], i0[2]:i1[2]] = True
    def f(xyz):
        k = np.floor((xyz-lo)/v).astype(int); ok = ((k >= 0) & (k < np.array(shape))).all(1); out = np.zeros(len(xyz), bool)
        out[ok] = occ[k[ok, 0], k[ok, 1], k[ok, 2]]; return out
    return f

PAIRINGS = {'record_invariance': (['r28off_a', 'r28off_b'], ['r28on_a', 'r28on_b']), 'default_r23': (['r23_a', 'r23_b'], ['r28off_a', 'r28off_b']),
            'gt_r25': (['r25gt_a', 'r25gt_b'], ['r28gt_a', 'r28gt_b']),
            'default_r23_four': (['r23_a', 'r23_b', 'r23_c', 'r23_d'], ['r28off_a', 'r28off_b', 'r28off_c', 'r28off_d']),
            'gt_r25_four': (['r25gt_a', 'r25gt_b', 'r25gt_c', 'r25gt_d'], ['r28gt_a', 'r28gt_b', 'r28gt_c', 'r28gt_d'])}
def main():
    S = {l: {it: load(l, it) for it in ITS} for l in sorted(p.name for p in P.iterdir()) if (P/l/'TRAINING_COMPLETE.json').exists()}
    rows = []; status = {}
    for key, (A, B) in PAIRINGS.items():
        if not all(l in S for l in A+B): status[key] = None; continue
        same = list(itertools.combinations(A, 2))+list(itertools.combinations(B, 2)); cross = [(a, b) for a in A for b in B]; ok_all = True
        for it in ITS:
            Q = {k: {p: quantities(S[p[0]][it], S[p[1]][it]) for p in pairs} for k, pairs in [('same', same), ('cross', cross)]}
            keys = sorted(set().union(*[set(v) for d in Q.values() for v in d.values()]))
            for k in keys:
                sv = [v[k] for v in Q['same'].values() if k in v]; cv = [v[k] for v in Q['cross'].values() if k in v]
                if not sv or not cv: continue
                ok = float(np.median(cv)) <= max(sv); ok_all &= ok
                rows.append(dict(pairing=key, iteration=it, quantity=k, same_n=len(sv), same_min=min(sv), same_max=max(sv), cross_n=len(cv), cross_median=float(np.median(cv)), cross_max=max(cv), rule_B=ok))
        status[key] = ok_all
    # initial state (snapshot 0) byte equality: r23 vs r28 off, r25 vs r28 gt
    init = {}
    for a, b in [('r23_a', 'r28off_a'), ('r25gt_a', 'r28gt_a'), ('r28off_a', 'r28on_a')]:
        # FinalTrain keeps no iteration-0 snapshot: compare the initialization records (seed counts, target/seed hashes, large-background list)
        eq = True
        for f in ['initialization.json', 'loaded_targets.json', 'initial_large_background.json']:
            ja, jb = (json.loads((P/x/'model/target_monitor'/f).read_text()) for x in (a, b)); ja.pop('at', None); jb.pop('at', None); eq &= ja == jb
        init[f'{a}_vs_{b}'] = eq
    loaded = {l: json.loads((P/l/'model/target_monitor/loaded_targets.json').read_text())['target_sha256'] for l in S}
    tsha = {'own': sha(FT/'targets/R1rep_b10__ALS.npz'), 'gt': sha(GT/'targets_gt/R1rep_b10__ALS.npz')}
    targets_ok = all(loaded[l] == tsha['gt' if 'gt' in l else 'own'] for l in loaded)
    inside = region_inside('R1rep_b10__ALS'); track = {l: tracking(l, inside) for l in S if '_on_' in l or 'on_' in l}
    selfcheck = {l: 'TRAINLOG_SELFCHECK_CHANGED' not in (P/l/'train.log').read_text() for l in track if 'JBGS_TRAINLOG_SELFCHECK=1' in (P/l/'command.json').read_text()}
    grads = {l: sorted(int(Path(f).stem) for f in glob.glob(str(P/l/'model/trainlog/grads/*.npz'))) for l in track}
    rep = {}
    for name in ['replay_compare_r23d_r28d', 'replay_compare_r25g_r28g', 'replay_record_own', 'replay_record_gt']:
        p = O/'verification'/f'{name}.json'; rep[name] = json.loads(p.read_text())['status'] if p.exists() else None
    sw = {}
    for p in sorted((O/'verification').glob('switches_*.json')): sw[p.stem] = json.loads(p.read_text())['status']
    v2 = json.loads((C/'unitcheck_v2.json').read_text()); assert sha(C/'unitcheck_v2.json') == json.loads((C/'unitcheck_v2.lock.json').read_text())['config_sha256']
    reported = dict(default_r23_gpu_rule_B=status['default_r23'], gt_r25_gpu_rule_B=status['gt_r25'], default_r23_four_runs=status.get('default_r23_four'), gt_r25_four_runs=status.get('gt_r25_four'))  # unit_check_v2: reported, not in status
    checks = dict(default_r23_replay=rep['replay_compare_r23d_r28d'] == 'PASS', default_r23_initial_state=init['r23_a_vs_r28off_a'],
                  gt_r25_replay=rep['replay_compare_r25g_r28g'] == 'PASS', gt_r25_initial_state=init['r25gt_a_vs_r28gt_a'], targets_loaded=targets_ok,
                  record_replay=rep['replay_record_own'] == 'PASS' and rep['replay_record_gt'] == 'PASS', record_gpu_rule_B=status['record_invariance'],
                  id_tracking=all(not [f for f in t['failures'] if 'balance' not in f] for t in track.values()) and bool(track),
                  event_balance=all(all(b['count_equal'] and b['uid_set_equal'] is not False for b in t['balance']) for t in track.values()) and bool(track),
                  self_check=all(selfcheck.values()) and bool(selfcheck), gradients_written=all(len(v) >= 5 for v in grads.values()) and bool(grads),
                  switches=bool(sw) and all(v == 'PASS' for v in sw.values()))
    res = dict(at=now(), status='PASS' if all(checks.values()) else 'FAIL', checks=checks, reported_not_in_status=reported, rule=v2['status_rule'], runs=list(S), rule_B=rows, initial_state_equal=init, loaded_targets=loaded,
               replay=rep, switches=sw, tracking=track, self_check_runs=selfcheck, gradient_iterations=grads, scientific_verdict=None)
    dump(O/'verification/unit_checks.json', res); table('unit_checks_rule_B', rows); table('unit_checks_event_balance', [dict(run=l, **b) for l, t in track.items() for b in t['balance']])
    table('unit_checks_summary', [dict(check=k, passed=v) for k, v in checks.items()])
    print('STATUS', res['status'], checks, flush=True)
    for r in rows:
        if not r['rule_B']: print('RULE_B_FAIL', r)
    for l, t in track.items(): print(l, t['failures'][:5], t['event_counts'], t.get('delete_reasons'), t.get('birth_how'))
if __name__ == '__main__': main()
