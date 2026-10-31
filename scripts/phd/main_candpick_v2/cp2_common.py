"""Task-local paths, exact inputs and JSON receipts."""
import hashlib
import importlib.util
import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import numpy as np

OUT, DOC, CFG, CP1 = map(Path, ['/out', '/docs', '/config', '/cp1'])
PH = Path('/art/phase-payloads/phd')
PC = PH / 'main_photocheck_v1/PHD-MAIN-PHOTOCHECK-v1'
WP = PH / 'main_wallphoto_v1/PHD-MAIN-WALLPHOTO-v1'
JN = PH / 'main_judgenum_v1/PHD-MAIN-JUDGENUM-v1'
W = PH / 'main_widen0_v2/PHD-MAIN-WIDEN0-v2'
UNITS = ['B173_ALS', 'B173_LoD2', 'R1_LoD2']
SOURCE = '[이 발주에서 냄]'

def now(): return datetime.now(ZoneInfo('Asia/Seoul')).isoformat()

def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(4 << 20), b''): h.update(chunk)
    return h.hexdigest()

def bind(path):
    p = Path(path)
    return dict(path=str(p), bytes=p.stat().st_size, sha256=sha(p))

def clean(v):
    if isinstance(v, dict): return {str(k): clean(x) for k, x in v.items()}
    if isinstance(v, (list, tuple, np.ndarray)): return [clean(x) for x in v]
    if isinstance(v, np.generic): return clean(v.item())
    if isinstance(v, Path): return str(v)
    if isinstance(v, float) and not np.isfinite(v): return None
    return v

def save(path, value, replace=False):
    p = Path(path)
    assert any(p == root or root in p.parents for root in [OUT, DOC, CFG]), p
    p.parent.mkdir(parents=True, exist_ok=True)
    assert replace or not p.exists(), f'refuse replacement: {p}'
    temp = p.with_name(p.name + '.tmp')
    temp.write_text(json.dumps(clean(value), ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    os.replace(temp, p)

def arrays(path):
    with np.load(path, allow_pickle=False) as z: return {k: z[k] for k in z.files}

def module(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m

def config():
    p = CFG / 'candpick_v2.json'
    c = json.loads(p.read_text())
    assert sha(p) == json.loads(p.with_suffix('.lock.json').read_text())['sha256']
    return c

def table(name, rows, **extra):
    import csv
    save(DOC / 'tables' / (name + '.json'), dict(rows=rows, source=SOURCE, scientific_verdict=None, **extra), replace=True)
    if rows:
        keys = list(dict.fromkeys(k for r in rows for k in r))
        with (DOC / 'tables' / (name + '.csv')).open('w', newline='', encoding='utf-8-sig') as f:
            w = csv.DictWriter(f, fieldnames=keys); w.writeheader()
            for row in clean(rows): w.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v for k, v in row.items()})
