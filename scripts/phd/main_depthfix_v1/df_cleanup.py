"""Disk cleanup of this task's own payload (host python, stdlib), user approval 11-24 21:40 ('정리할 수 있는 것 정리하자'). Never touches other tasks' payloads,
running trainings (no receipt.json), extractions in progress, or anything a result depends on (30k checkpoint, 15k/30k point clouds, final meshes, scores, tables).
Deletes: completed runs' jbgs_complete/iteration_7000 + iteration_15000, point_cloud/iteration_7000, test renders iteration_07000 + iteration_15000, tfevents;
gtj/renders/<key> whose extraction is scored; fastwork/<key> not in use; superseded maps (cell_ga_diag = old 판 10 rule, cell_ga_na_da = 판 11 cancelled, ga_P/ga_M build
intermediates of the 판 5~8 maps), maps/ftcheck. usage: python3 df_cleanup.py [dry]   writes logs/cleanup_<time>.json"""
import json, os, shutil, subprocess, sys, datetime as dt
from pathlib import Path
O = Path('/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/main_depthfix_v1/PHD-MAIN-DEPTHFIX-v1'); dry = len(sys.argv) > 1
def size(p): return int(subprocess.check_output(['du', '-sb', str(p)]).split()[0]) if p.exists() else 0
active = set(subprocess.run(['ps', '-eo', 'args'], capture_output=True, text=True).stdout.split())
meshing = {a.split(':')[0] + '__df_' + a.split(':')[1] + '_' + a.split(':')[2] for a in active if a.count(':') == 2 and '__' in a}
items = []
for run in sorted((O/'runs').glob('*/*')):
    if not (run/'receipt.json').exists() or not (run/'model').exists(): continue
    if not (O/'score'/f'{run.parent.name}__{run.name}.json').exists(): continue   # only scored runs (user 11-24 22h)
    m = run/'model'
    for p in [m/'jbgs_complete/iteration_7000', m/'jbgs_complete/iteration_15000', m/'point_cloud/iteration_7000', m/'iteration_07000', m/'iteration_15000'] + list(m.glob('events.out.tfevents*')):
        if p.exists(): items.append(('run', p))
for r in sorted((O/'gtj/renders').glob('*')):
    if (O/'meshes'/r.name/'score.json').exists() and r.name not in meshing: items.append(('render', r))
for f in sorted((O/'fastwork').glob('*')):
    if f.name not in meshing: items.append(('fastwork', f))
for v in ['cell_ga_diag', 'cell_ga_na_da', 'ga_P', 'ga_M']: items.append(('map', O/'maps/base'/v))
items.append(('map', O/'maps/ftcheck'))
rec = []; tot = 0
for kind, p in items:
    if not p.exists(): continue
    b = size(p); tot += b; rec.append(dict(kind=kind, path=str(p.relative_to(O)), bytes=b))
    if not dry: shutil.rmtree(p) if p.is_dir() else p.unlink()
out = O/'logs'/f'cleanup_{dt.datetime.now().strftime("%m%d-%H%M")}{"_dry" if dry else ""}.json'
out.write_text(json.dumps(dict(at=dt.datetime.now().astimezone().isoformat(), dry=dry, total_bytes=tot, items=rec, kept_rule=__doc__, scientific_verdict=None), ensure_ascii=False, indent=1))
by = {}
for r in rec: by[r['kind']] = by.get(r['kind'], 0) + r['bytes']
print('TOTAL GB', round(tot/1e9, 1), {k: round(v/1e9, 1) for k, v in by.items()}, out)
