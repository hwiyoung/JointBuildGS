"""PHD-MAIN-FLOATDIAG-v1: paths and append-only evidence helpers."""
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

TASK = 'PHD-MAIN-FLOATDIAG-v1'
PH = Path('/ph')
LT = PH/'main_losstrain_v1/PHD-MAIN-LOSSTRAIN-v1'
S0 = PH/'main_stage0_v1/PHD-MAIN-STAGE0-v1'
S1 = PH/'main_stage1_v1/PHD-MAIN-STAGE1-v1'
S3 = PH/'main_stage3_v1/PHD-MAIN-STAGE3-v1'
OUT, DOC, CFG = Path('/out'), Path('/docs'), Path('/config')
PRIOR = sys.argv[sys.argv.index('--prior')+1] if '--prior' in sys.argv else 'ALS'
assert PRIOR in ['ALS','LoD2']
if PRIOR != 'ALS':
    OUT, DOC = OUT/PRIOR, DOC/PRIOR
SITES = ['B173nb_b10', 'B0_b10', 'R1rep_b10']
RESULTS = [f'{p}_{PRIOR}_s0' for p in ['nojudge','lt_dyngt','lt_dynnow']]

def now():
    return datetime.now(ZoneInfo('Asia/Seoul')).isoformat()

def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(2**20), b''):
            h.update(block)
    return h.hexdigest()

def save(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)+'\n'
    if path.exists():
        assert path.read_text() == text, f'refuse overwrite: {path}'
    else:
        path.write_text(text)

def config():
    path = CFG/'floatdiag_v1.json'
    lock = json.loads((CFG/'floatdiag_v1.lock.json').read_text())
    assert sha(path) == lock['sha256'], 'configuration lock changed'
    return json.loads(path.read_text())

def model_path(site, result):
    if result.startswith('nojudge_'):
        root = S3/'runs'/site/result
        if (root/'model').exists():
            return root/'model'
        finite = root.with_name(result+'.finite')
        return finite/'model'
    root = LT/'runs'/site/result
    receipt = json.loads((root/'PASS.json').read_text())
    return root/f"attempt_{receipt['attempt']}"/'model'

def mesh_path(site, result, prior='ALS'):
    receipt_path = LT/'patch_z'/f'{site}__{prior}__{result}.json'
    receipt = json.loads(receipt_path.read_text())
    path = Path(receipt['path'])
    if str(path).startswith('/out/'):
        path = LT/path.relative_to('/out')
    return path, receipt
