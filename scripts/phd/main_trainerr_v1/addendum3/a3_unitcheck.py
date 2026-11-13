"""r30 unit check (addendum3.json fork.unit_check). Outputs under payload addendum3/verification and docs addendum3/tables.
  dump <name>      : TRAINERR te_replay deterministic real-state replay with the mounted fork (/source) -> addendum3/verification/replay_<name>/state.pt
  compare <a> <b>  : byte comparison of two dumps (te_replay PARTS)
  gates            : jbgs_a3 gate functions of /source (r30) vs the inherited expressions over iterations 1..30000
  diff             : r30 vs r28 file sets and changed files (from /repo/src/phd/forks)"""
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

if __name__ == '__main__':
    a = sys.argv[1:]
    {'dump': lambda: dump_one(a[1]), 'compare': lambda: compare(a[1], a[2]), 'gates': gates, 'diff': diff}[a[0]]()
