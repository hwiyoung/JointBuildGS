"""PHD-MAIN-BASE151-v1 container-side paths and helpers (inputs read-only under /art, outputs under /b151).
scientific_verdict: null"""
import datetime as dt
import hashlib
import json
from pathlib import Path

R = Path('/repo')
C = R / 'configs/phd/main_base151_v1'
D = R / 'docs/experiments/phd/main_base151_v1'
B = Path('/b151')
ART = Path('/art')
PH = ART / 'phase-payloads/phd'
TU1 = PH / 'main_trainunit_v1/PHD-MAIN-TRAINUNIT-v1'
TU2 = PH / 'main_trainunit_v1/PHD-MAIN-TRAINUNIT-v2'
SB = PH / 'main_baselines_v1/PHD-MAIN-BASELINES-v1'
SF = PH / 'main_fix_v1/PHD-MAIN-FIX-v1'
SL = PH / 'main_fill_v1/PHD-MAIN-FILL-v1'
GT = PH / 'main_gtjudge_v1/PHD-MAIN-GTJUDGE-v1'
RS = PH / 'main_rescore_v1/PHD-MAIN-RESCORE-v1'
JC2 = PH / 'main_judgecheck_v2/PHD-MAIN-JUDGECHECK-v2'
S0 = PH / 'main_stage0_v1/PHD-MAIN-STAGE0-v1'
WD = PH / 'main_widen0_v2/PHD-MAIN-WIDEN0-v2'
KST = dt.timezone(dt.timedelta(hours=9))


def now():
    return dt.datetime.now(KST).isoformat()


def sha(p):
    h = hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda: f.read(8 << 20), b''):
            h.update(b)
    return h.hexdigest()


def dump(p, v):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(v, ensure_ascii=False, indent=1, allow_nan=False) + '\n')


def cfg(name='base151_v1'):
    lock = json.loads((C / f'{name}.lock.json').read_text())
    assert sha(C / f'{name}.json') == lock['config_sha256'], f'{name}.json changed after lock'
    return json.loads((C / f'{name}.json').read_text())


def progress(s):
    with (D / 'progress.md').open('a') as f:
        f.write(f'- {now()}: {s}\n')


def issue(s):
    with (D / 'issues.md').open('a') as f:
        f.write(f'- {now()}: {s}\n')
