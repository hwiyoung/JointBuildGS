"""Stage-1 unit checks (order 2.5): decision invariance, id tracking, event balance, r23 equality.
CPU only (jointbuildgs:dev, torch CPU + shapely). Reads /tl/probe/<label>/model."""
import glob, itertools
import torch
import shapely
from shapely.geometry import shape
from common import *
P = O/'probe'; LABELS = ['r23', 'r27_off_a', 'r27_off_b', 'r27_off_c', 'r27_off_d', 'r27_on_a', 'r27_on_b', 'r27_on_c', 'r27_on_d']; ITS = [100, 200, 300]
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

def tracking(label, scope):
    root = P/label/'model/trainlog'; saves = [json.loads(l) for l in (root/'saves.jsonl').read_text().splitlines()]
    ev = events(label); out = dict(label=label, saves=[s['name'] for s in saves], failures=[])
    poly = shape(scope['buffered_footprint']); z0, z1 = float(scope['z_min']), float(scope['z_max'])
    prev = None; seen_dead = set(); max_uid = -1; balance = []
    for s in saves:
        st = loadz(root/'states'/f'{s["name"]}.npz'); sc = torch.load(root/'scene'/f'{s["name"]}.pt', map_location='cpu', weights_only=False)
        uid_all = sc['uid'].numpy(); xyz = sc['xyz'].double().numpy()
        if len(np.unique(uid_all)) != len(uid_all): out['failures'].append(f'{s["name"]}: duplicate uid in scene')
        if len(np.unique(st['uid'])) != len(st['uid']): out['failures'].append(f'{s["name"]}: duplicate uid in state')
        if not np.array_equal(uid_all[st['full_gaussian_index']], st['uid']): out['failures'].append(f'{s["name"]}: state uid != scene uid')
        ref = shapely.contains_xy(poly, xyz[:, 0], xyz[:, 1]) & (xyz[:, 2] >= z0) & (xyz[:, 2] <= z1)
        mism = int((ref != sc['inside'].numpy()).sum())
        if mism: out['failures'].append(f'{s["name"]}: inside flag vs shapely mismatch {mism}')
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

def main():
    c = cfg(); v2 = json.loads((C/'trainlog_v1.unitcheck_v2.json').read_text()); assert sha(C/'trainlog_v1.unitcheck_v2.json') == json.loads((C/'trainlog_v1.unitcheck_v2.lock.json').read_text())['config_sha256']
    S = {l: {it: load(l, it) for it in ITS} for l in LABELS if (P/l/'TRAINING_COMPLETE.json').exists()}
    off = [l for l in S if 'off' in l]; on = [l for l in S if '_on_' in l]
    same = list(itertools.combinations(off, 2))+list(itertools.combinations(on, 2)); cross = [(a, b) for a in off for b in on]; r23 = [('r23', b) for b in off] if 'r23' in S else []
    rows = []; status = True; v1 = {}
    for it in ITS:
        Q = {k: {p: quantities(S[p[0]][it], S[p[1]][it]) for p in pairs} for k, pairs in [('same', same), ('cross', cross), ('r23', r23), ('offoff', list(itertools.combinations(off, 2)))]}
        keys = sorted(set().union(*[set(v) for d in Q.values() for v in d.values()]))
        for k in keys:
            sv = [v[k] for v in Q['same'].values() if k in v]; cv = [v[k] for v in Q['cross'].values() if k in v]; rv = [v[k] for v in Q['r23'].values() if k in v]; ov = [v[k] for v in Q['offoff'].values() if k in v]
            if not sv or not cv: continue
            ok = float(np.median(cv)) <= max(sv); ok23 = (float(np.median(rv)) <= max(ov)) if rv and ov else None
            rows.append(dict(iteration=it, quantity=k, same_n=len(sv), same_min=min(sv), same_max=max(sv), cross_n=len(cv), cross_median=float(np.median(cv)), cross_max=max(cv), rule_B=ok,
                             r23_n=len(rv), r23_median=float(np.median(rv)) if rv else None, offoff_max=max(ov) if ov else None, rule_r23=ok23))
            status &= ok  # locked v2 status_rule: PASS iff A and B; r23 GPU line is reported (rule_r23) and diagnosed with four r23 runs
    replay = json.loads((O/'verification/replay_test.json').read_text()); r23rep = json.loads((O/'verification/replay_compare_r23_r27off.json').read_text())
    track = {l: tracking(l, c['scope']) for l in on+[x for x in ['r27_on_e'] if (P/x/'TRAINING_COMPLETE.json').exists()]}
    selfcheck = {l: 'TRAINLOG_SELFCHECK_CHANGED' not in (P/l/'train.log').read_text() for l in list(track) if 'JBGS_TRAINLOG_SELFCHECK=1' in (P/l/'command.json').read_text()}
    diag = json.loads((O/'verification/unit_checks_r23_diagnostic.json').read_text()) if (O/'verification/unit_checks_r23_diagnostic.json').exists() else None
    checks = dict(decision_invariance_replay=replay['status'] == 'PASS', r23_replay=r23rep['status'] == 'PASS', gpu_repeat_rule_B=status,
                  id_tracking=all(not [f for f in t['failures'] if 'balance' not in f] for t in track.values()),
                  event_balance=all(all(b['count_equal'] and b['uid_set_equal'] is not False for b in t['balance']) for t in track.values()),
                  self_check=all(selfcheck.values()) and bool(selfcheck))
    res = dict(at=now(), status='PASS' if all(checks.values()) else 'FAIL', checks=checks, reported_not_in_status=dict(r23_single_run_rule=[r for r in rows if r['rule_r23'] is False], r23_four_run_diagnostic=diag and diag['all_median_le_same_max']), rule=v2['decision_invariance'], runs=list(S), gpu_repeat=rows, replay=replay, r23_replay=r23rep,
               tracking=track, self_check_runs=selfcheck, scientific_verdict=None)
    dump(O/'verification/unit_checks.json', res); table('unit_checks_gpu_repeat', rows)
    table('unit_checks_event_balance', [dict(run=l, **b) for l, t in track.items() for b in t['balance']])
    print('STATUS', res['status'], checks, flush=True)
    for r in rows: print(r['iteration'], r['quantity'], 'same', r['same_min'], r['same_max'], 'cross med', r['cross_median'], 'max', r['cross_max'], r['rule_B'], 'r23', r['r23_median'], r['rule_r23'])
    for l, t in track.items(): print(l, t['failures'][:5], t['event_counts'], t.get('delete_reasons'), t.get('birth_how'))
if __name__ == '__main__': main()
