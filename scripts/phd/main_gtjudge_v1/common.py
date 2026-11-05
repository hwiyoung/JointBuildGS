"""GTJUDGE bindings: inherited inputs read-only; new payloads in /gtjudge."""
import csv
import datetime as dt
import hashlib
import json
import os
from pathlib import Path

R, C, D, O = map(Path, ['/repo', '/cfg', '/docs', '/gtjudge'])
PH = Path('/art/phase-payloads/phd')
S1 = PH / 'main_stage1_v1/PHD-MAIN-STAGE1-v1'
FT = PH / 'main_finaltrain_v1/PHD-MAIN-FINALTRAIN-v1'
JA = PH / 'main_judgeapply_v1/PHD-MAIN-JUDGEAPPLY-v1'
RS = PH / 'main_rescore_v1/PHD-MAIN-RESCORE-v1'
RL = PH / 'main_release_v1/PHD-MAIN-RELEASE-v1'
RC = PH / 'main_recount_v1/PHD-MAIN-RECOUNT-v1'
SITES = ['B173nb_b10', 'B0_b10', 'R1rep_b10']
PRIORS = ['ALS', 'LoD2']
METHODS = ['prior', 'mvs', 'fusion', 'baseline_30000', 'GeoGS_30000',
           '2DGS_30000', 'CDGS_30000', 'judgment_mesh', 'FINALTRAIN_30000']

def now():
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat()

def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(8 << 20), b''):
            h.update(block)
    return h.hexdigest()

def dump(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')

def table(name, rows):
    path = D / 'tables' / name
    path.parent.mkdir(parents=True, exist_ok=True)
    dump(path.with_suffix('.json'), dict(rows=rows, scientific_verdict=None))
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with path.with_suffix('.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields, lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)

def cfg():
    path = C / 'gtjudge_v1.json'
    lock = json.loads((C / 'gtjudge_v1.initial.lock.json').read_text())
    assert sha(path) == lock['config_sha256']
    return json.loads(path.read_text())

def score_dir(site, prior, method):
    phase = 'addendum3_stage1' if site == 'B173nb_b10' else 'addendum3_stage2'
    return RS / phase / 'scores' / f'{site}__{prior}__{method}'
