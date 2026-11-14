"""r30 unit check (addendum3.json fork.unit_check). Outputs under payload addendum3/verification and docs addendum3/tables.
  dump <name>      : TRAINERR te_replay deterministic real-state replay with the mounted fork (/source) -> addendum3/verification/replay_<name>/state.pt
  compare <a> <b>  : byte comparison of two dumps (te_replay PARTS)
  gates            : jbgs_a3 gate functions of /source (r30) vs the inherited expressions over iterations 1..30000
  diff             : r30 vs r28 file sets and changed files (from /repo/src/phd/forks)
Added for the ba-2 rerun (third switch --jbgs_a3_count_check; earlier outputs are kept, new ones carry the suffix _c):
  gates_c          : gates of the three switches -> verification/gates_c.json
  diff_c           : r30 vs r28 with jbgs_finaltrain.py as the second changed file -> verification/diff_c.json
  count <fork> <on|off|none> <tag> : FinalTrain.observe of /repo/src/phd/forks/<fork> on a stub model whose count passes 3 x count at 6000
                     at 9000 (time and CUDA memory readers fixed) -> verification/count_<tag>/ (curve.jsonl, health_*.json, STOP.json, result.json)
  countcmp         : r28 vs r30 default vs r30 on (bytes equal) and r30 off (no stop, rows before 9000 equal) -> verification/count_compare_c.json"""
import sys, hashlib
sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1')
import te_replay as TR
from te_replay import *
A3O = O/'addendum3'; A3D = D/'addendum3'; V = A3O/'verification'

def dump_one(name, probe='r28off_a'):
    torch.use_deterministic_algorithms(True); root = V/f'replay_{name}'; root.mkdir(parents=True, exist_ok=False)
    st, _ = TR.run(FinalTrain, root/'off', TR.ckpt(probe), 'own'); torch.save(st, root/'state.pt')
    dump(root/'dump.json', dict(at=now(), name=name, start=str(TR.ckpt(probe)), start_sha256=sha(TR.ckpt(probe)), source={p.name: sha(p) for p in sorted(Path('/source').glob('*.py'))}, trace=st['trace'], scientific_verdict=None))
    print('DUMPED', name, st['trace'], flush=True)

def compare(a, b):
    x = torch.load(V/f'replay_{a}/state.pt', weights_only=False); y = torch.load(V/f'replay_{b}/state.pt', weights_only=False)
    parts = {k: TR.equal(x[k], y[k]) for k in TR.PARTS}
    res = dict(at=now(), a=a, b=b, parts_byte_equal=parts, status='PASS' if all(parts.values()) else 'FAIL', trace=x['trace'], scientific_verdict=None)
    dump(V/f'replay_compare_{a}_{b}.json', res); print(res['status'], parts, flush=True)

def gates():
    sys.path.insert(0, '/source'); import jbgs_a3 as G
    from argparse import Namespace as NS
    it = range(1, 30001); off = NS(jbgs_a3_normal='inherit', jbgs_a3_reset_after=-1)
    rows = dict(normal_default_equal=all(G.normal_active(i, off) == (i > 7000) for i in it), reset_default_equal=all(G.reset_allowed(i, off) for i in it),
                missing_args_equal=all(G.normal_active(i, NS()) == (i > 7000) and G.reset_allowed(i, NS()) for i in it),
                normal_off_never=not any(G.normal_active(i, NS(jbgs_a3_normal='off', jbgs_a3_reset_after=-1)) for i in it),
                reset_after_7000=[i for i in [3000, 6000, 9000, 12000] if G.reset_allowed(i, NS(jbgs_a3_normal='inherit', jbgs_a3_reset_after=7000))])
    rows['status'] = 'PASS' if rows['normal_default_equal'] and rows['reset_default_equal'] and rows['missing_args_equal'] and rows['normal_off_never'] and rows['reset_after_7000'] == [3000, 6000] else 'FAIL'
    dump(V/'gates.json', dict(at=now(), **rows, scientific_verdict=None)); print('GATES', rows, flush=True)

def diff():
    F = Path('/repo/src/phd/forks'); a, b = F/'GeoGS-conf-guided-v1-r28', F/'GeoGS-conf-guided-v1-r30'
    def files(r): return {str(p.relative_to(r)): hashlib.sha256(p.read_bytes()).hexdigest() for p in r.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    fa, fb = files(a), files(b); changed = sorted(k for k in fa if k in fb and fa[k] != fb[k]); only_b = sorted(set(fb)-set(fa)); only_a = sorted(set(fa)-set(fb))
    res = dict(at=now(), changed=changed, only_r30=only_b, only_r28=only_a, status='PASS' if changed == ['train.py'] and only_b == ['jbgs_a3.py'] and not only_a else 'FAIL', scientific_verdict=None)
    dump(V/'diff.json', res); print('DIFF', res, flush=True)

def gates_c():
    sys.path.insert(0, '/source'); import jbgs_a3 as G
    from argparse import Namespace as NS
    it = range(1, 30001); off = NS(jbgs_a3_normal='inherit', jbgs_a3_reset_after=-1, jbgs_a3_count_check='on')
    rows = dict(normal_default_equal=all(G.normal_active(i, off) == (i > 7000) for i in it), reset_default_equal=all(G.reset_allowed(i, off) for i in it),
                missing_args_equal=all(G.normal_active(i, NS()) == (i > 7000) and G.reset_allowed(i, NS()) for i in it) and G.count_check_active(NS()),
                count_default_on=G.count_check_active(off), count_off=not G.count_check_active(NS(jbgs_a3_count_check='off')),
                normal_off_never=not any(G.normal_active(i, NS(jbgs_a3_normal='off', jbgs_a3_reset_after=-1)) for i in it),
                reset_after_7000=[i for i in [3000, 6000, 9000, 12000] if G.reset_allowed(i, NS(jbgs_a3_normal='inherit', jbgs_a3_reset_after=7000))])
    import argparse; ap = argparse.ArgumentParser(); G.register_args(ap); d = vars(ap.parse_args([]))
    rows['parser_defaults'] = d; ok_d = d == dict(jbgs_a3_normal='inherit', jbgs_a3_reset_after=-1, jbgs_a3_count_check='on')
    rows['status'] = 'PASS' if ok_d and all(rows[k] for k in ['normal_default_equal', 'reset_default_equal', 'missing_args_equal', 'count_default_on', 'count_off', 'normal_off_never']) and rows['reset_after_7000'] == [3000, 6000] else 'FAIL'
    dump(V/'gates_c.json', dict(at=now(), **rows, scientific_verdict=None)); print('GATES_C', rows, flush=True)

def diff_c():
    F = Path('/repo/src/phd/forks'); a, b = F/'GeoGS-conf-guided-v1-r28', F/'GeoGS-conf-guided-v1-r30'
    def files(r): return {str(p.relative_to(r)): hashlib.sha256(p.read_bytes()).hexdigest() for p in r.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    fa, fb = files(a), files(b); changed = sorted(k for k in fa if k in fb and fa[k] != fb[k]); only_b = sorted(set(fb)-set(fa)); only_a = sorted(set(fa)-set(fb))
    init_line = 'import jbgs_a3;self.a3_count_check=jbgs_a3.count_check_active(args)' in (b/'jbgs_finaltrain.py').read_text()
    res = dict(at=now(), changed=changed, only_r30=only_b, only_r28=only_a, finaltrain_init_sets_switch=init_line,
               status='PASS' if changed == ['jbgs_finaltrain.py', 'train.py'] and only_b == ['jbgs_a3.py'] and not only_a and init_line else 'FAIL', scientific_verdict=None)
    dump(V/'diff_c.json', res); print('DIFF_C', res, flush=True)

COUNT_SEQ = [(6000, 10), (7000, 20), (8000, 25), (9000, 31), (10000, 40), (15000, 50), (16000, 60)]   # 9000: 31 > 3 x 10

def count_one(fork, mode, tag):
    import importlib, types
    from argparse import Namespace as NS
    src = Path('/repo/src/phd/forks')/fork; sys.path.insert(0, str(src))
    for m in ['jbgs_finaltrain', 'jbgs_target', 'jbgs_target_r8', 'jbgs_a3']: sys.modules.pop(m, None)
    F = importlib.import_module('jbgs_finaltrain'); assert Path(F.__file__).parent == src
    F.time.monotonic = lambda: 5.0; torch.cuda.memory_allocated = lambda *a: 0; torch.cuda.memory_reserved = lambda *a: 0; torch.cuda.mem_get_info = lambda *a: (0, 0)
    out = V/f'count_{tag}'; out.mkdir(parents=True, exist_ok=False)
    c = F.FinalTrain.__new__(F.FinalTrain); c.mon = out; c.n6000 = None; c.started = 0.0
    if (src/'jbgs_a3.py').exists():   # the same expression FinalTrain.__init__ uses in r30
        import jbgs_a3; c.a3_count_check = jbgs_a3.count_check_active(NS() if mode == 'none' else NS(jbgs_a3_count_check=mode))
    stopped = None; done = []
    for it, n in COUNT_SEQ:
        g = types.SimpleNamespace(_xyz=torch.zeros(n, 3), origin=torch.ones(n), get_opacity=torch.full((n, 1), .5))
        try: c.observe(it, g, 1.0, .5, .25, 'stub')
        except RuntimeError as e: stopped = dict(iteration=it, message=str(e)); break
        done.append(it)
    res = dict(at=now(), fork=fork, mode=mode, observed=done, stopped=stopped, files={p.name: sha(p) for p in sorted(out.glob('*.json*'))}, scientific_verdict=None)
    dump(out/'result.json', res); print('COUNT', tag, done, stopped, flush=True)

def countcmp():
    def files(tag): return {p.name: p.read_bytes() for p in sorted((V/f'count_{tag}').glob('*')) if p.name != 'result.json'}
    def res(tag): return json.loads((V/f'count_{tag}/result.json').read_text())
    r28, dflt, on, off = files('r28'), files('r30_none'), files('r30_on'), files('r30_off')
    cl = [json.loads(l) for l in (V/'count_r30_off/curve.jsonl').read_text().splitlines()]; cl_on = (V/'count_r30_on/curve.jsonl').read_text().splitlines()
    rows = dict(r28_eq_r30_default=r28 == dflt, r28_eq_r30_on=r28 == on, r28_stops_at=res('r28')['stopped'], r30_off_stopped=res('r30_off')['stopped'], r30_off_observed=res('r30_off')['observed'],
                off_rows_before_9000_equal_on=(V/'count_r30_off/curve.jsonl').read_text().splitlines()[:3] == cl_on[:3],
                off_flagged_iterations=[r['iteration'] for r in cl if 'a3_count_check_off_would_stop' in r], off_has_stop_json=(V/'count_r30_off/STOP.json').exists())
    ok = rows['r28_eq_r30_default'] and rows['r28_eq_r30_on'] and rows['r28_stops_at'] and rows['r28_stops_at']['iteration'] == 9000 and rows['r30_off_stopped'] is None \
        and rows['r30_off_observed'] == [i for i, _ in COUNT_SEQ] and rows['off_rows_before_9000_equal_on'] and rows['off_flagged_iterations'] == [9000, 10000, 15000] and not rows['off_has_stop_json']
    rows['status'] = 'PASS' if ok else 'FAIL'; dump(V/'count_compare_c.json', dict(at=now(), seq=COUNT_SEQ, **rows, scientific_verdict=None)); print('COUNTCMP', rows, flush=True)

if __name__ == '__main__':
    a = sys.argv[1:]
    {'dump': lambda: dump_one(a[1]), 'compare': lambda: compare(a[1], a[2]), 'gates': gates, 'diff': diff, 'gates_c': gates_c, 'diff_c': diff_c,
     'count': lambda: count_one(a[1], a[2], a[3]), 'countcmp': countcmp}[a[0]]()
