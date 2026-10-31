"""Task-local utilities; all derived payloads stay in the approved output tree."""
import datetime as dt
import hashlib
import json
from pathlib import Path

REPO = Path('/repo')
PH = Path('/art/phase-payloads/phd')
OUT, CFG, DOC = Path('/out'), Path('/cfg'), Path('/docs')
S0 = PH / 'main_stage0_v1/PHD-MAIN-STAGE0-v1'
S1 = PH / 'main_stage1_v1/PHD-MAIN-STAGE1-v1'
UN = PH / 'main_uncert_v1/PHD-MAIN-UNCERT-v1'
JN = PH / 'main_judgenum_v1/PHD-MAIN-JUDGENUM-v1'


def stamp():
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat()


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(8 * 1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()


def dump(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def locked():
    lock = json.loads((CFG / 'target_v1.stage0.lock.json').read_text())
    p=CFG/'target_v1.json'
    if (CFG/'target_v1.stage1.lock.json').exists():p=CFG/'revisions/r1/target_v1.json'
    assert sha(p) == lock['config_sha256']
    c=json.loads(p.read_text())
    return c, lock


def training_locked():
    c=json.loads((CFG/'target_v1.json').read_text());lock=json.loads((CFG/'target_v1.stage1.lock.json').read_text())
    assert sha(CFG/'target_v1.json')==lock['config_sha256']
    return c,lock
