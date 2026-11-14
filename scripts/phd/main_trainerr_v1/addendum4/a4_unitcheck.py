"""r31 unit check (addendum4.json fork.unit_check). Outputs under payload addendum4/verification.
  dump <name>     : te_replay deterministic real-state replay with the mounted fork (/source) (a3_unitcheck.dump_one rule)
  compare <a> <b> : byte comparison of two dumps
  funcs           : jbgs_a4 defaults: stop_now never true over 1..30000, apply_occl_mask leaves maps untouched, parser defaults
  diff            : r31 vs r30 file sets and changed files"""
import sys, hashlib
sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1'); sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1/addendum3')
import a3_unitcheck as U
from te_replay import *
V = O/'addendum4'/'verification'; U.V = V

def funcs():
    sys.path.insert(0, '/source'); import jbgs_a4 as G, argparse
    from argparse import Namespace as NS
    ap = argparse.ArgumentParser(); G.register_args(ap); d = vars(ap.parse_args([]))
    a = NS(**d); it = range(1, 30001)
    class TC: pass
    tc = TC(); tc.maps = {'v': {'depth': torch.ones(4, 4), 'weight': torch.ones(4, 4), 'owner': torch.zeros(4, 4, dtype=torch.int32)}}
    before = {k: v.clone() for k, v in tc.maps['v'].items()}; G.apply_occl_mask(tc, a); G.apply_occl_mask(tc, NS())
    same = all(torch.equal(before[k], tc.maps['v'][k]) for k in before) and all(before[k] is not tc.maps['v'][k] for k in before)
    rows = dict(parser_defaults=d, defaults_ok=d == dict(jbgs_a4_grad_signed='off', jbgs_a4_stop_at=-1, jbgs_a4_occl_mask_m=-1., jbgs_a4_mvs_dir=''),
                stop_never_default=not any(G.stop_now(i, a) for i in it), stop_never_missing=not any(G.stop_now(i, NS()) for i in it),
                stop_6000=[i for i in [5999, 6000, 6001] if G.stop_now(i, NS(jbgs_a4_stop_at=6000))], grad_signed_default=G.grad_signed(a) or G.grad_signed(NS()),
                mask_default_maps_unchanged=same)
    rows['status'] = 'PASS' if rows['defaults_ok'] and rows['stop_never_default'] and rows['stop_never_missing'] and rows['stop_6000'] == [6000, 6001] and not rows['grad_signed_default'] and same else 'FAIL'
    dump(V/'funcs.json', dict(at=now(), **rows, scientific_verdict=None)); print('FUNCS', rows, flush=True)

def diff():
    F = Path('/repo/src/phd/forks'); a, b = F/'GeoGS-conf-guided-v1-r30', F/'GeoGS-conf-guided-v1-r31'
    def files(r): return {str(p.relative_to(r)): hashlib.sha256(p.read_bytes()).hexdigest() for p in r.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    fa, fb = files(a), files(b); changed = sorted(k for k in fa if k in fb and fa[k] != fb[k]); only_b = sorted(set(fb)-set(fa)); only_a = sorted(set(fa)-set(fb))
    res = dict(at=now(), changed=changed, only_r31=only_b, only_r30=only_a, status='PASS' if changed == ['jbgs_trainlog.py', 'train.py'] and only_b == ['jbgs_a4.py'] and not only_a else 'FAIL', scientific_verdict=None)
    dump(V/'diff.json', res); print('DIFF', res, flush=True)

if __name__ == '__main__' and sys.argv[1] not in ('dual', 'diff32'):
    a = sys.argv[1:]
    {'dump': lambda: U.dump_one(a[1]), 'compare': lambda: U.compare(a[1], a[2]), 'funcs': funcs, 'diff': diff}[a[0]]()

def dual():
    """r32 --jbgs_a4_dual_depth: off = r31 loss expression; on = the r31 term + the same term for depth2/weight2 (stub maps)."""
    sys.path.insert(0, '/source'); import jbgs_target as JT
    from argparse import Namespace as NS
    torch.manual_seed(0); D = torch.rand(1, 6, 7)*20+1
    m = {'depth': torch.rand(6, 7)*20+1, 'weight': (torch.rand(6, 7) > .3).float()*torch.rand(6, 7)*3, 'depth2': torch.rand(6, 7)*20+1, 'weight2': (torch.rand(6, 7) > .5).float()}
    m['depth'][0, 0] = float('nan'); m['depth2'][1, 1] = float('nan')
    t = JT.Target.__new__(JT.Target); t.maps = {'v': m}
    def ref(d, w):
        v = torch.isfinite(d) & (d > 0) & (w > 0); return (torch.abs(D.squeeze(0)[v]-d[v])*w[v]).sum()/float(D.numel())
    t.a4_dual = False; off = t.loss('v', D); t.a4_dual = True; on = t.loss('v', D)
    rows = dict(off_equals_r31_expression=bool(torch.equal(off, ref(m['depth'], m['weight']))), on_equals_sum=bool(torch.allclose(on, ref(m['depth'], m['weight'])+ref(m['depth2'], m['weight2']), rtol=0, atol=1e-6)),
                default_flag_off=getattr(NS(), 'jbgs_a4_dual_depth', 'off') == 'off')
    import argparse; sys.modules.pop('jbgs_a4', None); import jbgs_a4 as G; ap = argparse.ArgumentParser(); G.register_args(ap); rows['parser_default'] = vars(ap.parse_args([]))['jbgs_a4_dual_depth']
    rows['status'] = 'PASS' if rows['off_equals_r31_expression'] and rows['on_equals_sum'] and rows['parser_default'] == 'off' else 'FAIL'
    dump(V/'dual_r32.json', dict(at=now(), **rows, scientific_verdict=None)); print('DUAL', rows, flush=True)

def diff32():
    F = Path('/repo/src/phd/forks'); a, b = F/'GeoGS-conf-guided-v1-r31', F/'GeoGS-conf-guided-v1-r32'
    def files(r): return {str(p.relative_to(r)): hashlib.sha256(p.read_bytes()).hexdigest() for p in r.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    fa, fb = files(a), files(b); changed = sorted(k for k in fa if k in fb and fa[k] != fb[k]); only_b = sorted(set(fb)-set(fa)); only_a = sorted(set(fa)-set(fb))
    res = dict(at=now(), changed=changed, only_r32=only_b, only_r31=only_a, status='PASS' if changed == ['jbgs_a4.py', 'jbgs_target.py'] and not only_b and not only_a else 'FAIL', scientific_verdict=None)
    dump(V/'diff_r32.json', res); print('DIFF32', res, flush=True)

if __name__ == '__main__' and sys.argv[1] in ('dual', 'diff32'):
    {'dual': dual, 'diff32': diff32}[sys.argv[1]]()
