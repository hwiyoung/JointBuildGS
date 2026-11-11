"""Order 3.4: record run vs original run at 7000/15000/30000 (range Gaussian counts by tag, cell values on the 30000 mesh, lost-point overlap)
and the run manifest (states, events, gradients, scene dumps with sha256). argv: <run>"""
import torch
from common import *
from te_sets_tl import RUNS
from te_sim import region_inside
from te_check5 import model_of
def counts(tag):
    return {'all': int(len(tag)), 'patch_bound': int((tag == 1).sum()), 'released': int((tag == 2).sum()), 'background': int((tag == 0).sum())}
def main(run):
    c = cfg(); stem, arm = RUNS[run]; m = model_of(run); orig = Path(arm_paths(stem, arm)['model']); rows = []; tol = c['record_runs']['comparison']
    for it in tol['iterations']:
        s = loadz(orig/'target_monitor'/f'snapshot_{it}.npz', ['xyz', 'target_tag']); ins = region_inside(stem, s['xyz'].astype(float)); a = counts(s['target_tag'][ins])
        st = loadz(m/'trainlog/states'/f'{it}.npz', ['target_tag', 'xyz']); ins2 = region_inside(stem, st['xyz'].astype(float)); b = counts(st['target_tag'][ins2])
        for k in a:
            d = 100*(b[k]-a[k])/a[k] if a[k] else None
            rows.append(dict(run=run, iteration=it, item=f'range {k}', original=a[k], record=b[k], diff_pct=d, within=d is not None and abs(d) <= tol['count_tolerance_pct']))
    st = json.loads((O/'sets_tl'/f'{run}.json').read_text())['rows']
    for r in st:
        rows.append(dict(run=run, iteration=30000, item=f"{r['cell']} {r['metric']}", original=r['original_trained'], record=r['record_value'], diff_pp=r['diff_pp'], within=r['same_value']))
        rows.append(dict(run=run, iteration=30000, item=f"{r['cell']} lost overlap", original=r['original_lost'], record=r['record_lost'], overlap=r['overlap'],
                         overlap_pct_of_record=r['overlap_pct_of_record'], overlap_pct_of_original=r['overlap_pct_of_original']))
    same = all(r['within'] for r in rows if 'within' in r)
    table(f'record_compare_{run}', rows)
    man = []
    for sub in ['states', 'events', 'grads', 'scene']:
        for f in sorted((m/'trainlog'/sub).glob('*')): man.append(dict(file=str(f.relative_to(m.parent)), bytes=f.stat().st_size, sha256=sha(f)))
    dump(D/'manifests'/f'{run}.json', dict(at=now(), run=run, model=str(m), files=man, total_bytes=sum(x['bytes'] for x in man), scientific_verdict=None))
    dump(O/'compare'/f'{run}.json', dict(at=now(), run=run, label='원래 판과 같은 판' if same else '다시 돌린 판', rows=rows, scientific_verdict=None))
    print('COMPARE', run, '원래 판과 같은 판' if same else '다시 돌린 판', flush=True)
if __name__ == '__main__': main(*sys.argv[1:])
