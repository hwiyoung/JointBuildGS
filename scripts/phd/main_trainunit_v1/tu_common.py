"""Container-side paths and helpers for TRAINUNIT (inputs read-only, outputs under /tu)."""
import ast
import datetime as dt
import hashlib
import json
from pathlib import Path

import numpy as np

R = Path('/repo')
C = R / 'configs/phd/main_trainunit_v1'
D = R / 'docs/experiments/phd/main_trainunit_v1'
TU = Path('/tu')
ART = Path('/art')
PH = ART / 'phase-payloads/phd'
FT = PH / 'main_finaltrain_v1/PHD-MAIN-FINALTRAIN-v1'
TG = PH / 'main_target_v1/PHD-MAIN-TARGET-v1'
S0 = PH / 'main_stage0_v1/PHD-MAIN-STAGE0-v1'
JC = PH / 'main_judgecheck_v1/PHD-MAIN-JUDGECHECK-v1'
WD = PH / 'main_widen0_v2/PHD-MAIN-WIDEN0-v2'
RS = PH / 'main_rescore_v1/PHD-MAIN-RESCORE-v1'
DENSE = ART / 'phase-payloads/p0-audit/data/work/mvs/colmap_dense'
SITES = ['B0_b10', 'R1rep_b10', 'B173nb_b10']
PRIORS = ['ALS', 'LoD2']
GRID_W, GRID_H = 1024, 741
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
    p.write_text(json.dumps(v, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def loadz(p, keys=None):
    with np.load(p, allow_pickle=False) as z:
        return {k: z[k] for k in (z.files if keys is None else keys)}


def savez(p, **v):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(p, **v)


def cfg():
    lock = json.loads((C / 'trainunit_v1.initial.lock.json').read_text())
    assert sha(C / 'trainunit_v1.json') == lock['config_sha256'], 'config changed after lock'
    return json.loads((C / 'trainunit_v1.json').read_text())


def inherit(path, names, scope):
    """Execute only the named top-level functions/classes of an inherited file (unchanged code)."""
    nodes = [x for x in ast.parse(Path(path).read_text()).body if isinstance(x, (ast.FunctionDef, ast.ClassDef)) and x.name in names]
    assert len(nodes) == len(names), (path, names)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), scope)
    return {n: scope[n] for n in names}


def progress(s):
    with (D / 'progress.md').open('a') as f:
        f.write(f'- {now()}: {s}\n')


def issue(s):
    with (D / 'issues.md').open('a') as f:
        f.write(f'- {now()}: {s}\n')
