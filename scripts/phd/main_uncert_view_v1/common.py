"""Read-only source adapters; output belongs exclusively to UNCERT-VIEW-v1."""
import datetime as dt
import hashlib
import json
from pathlib import Path
import sys
import numpy as np

ROOT = Path('/repo')
SRC = Path('/out')
OUT = Path('/view')
DOC = Path('/docs')
CFG = Path('/cfg')
sys.path.insert(0, str(ROOT / 'scripts/phd/main_uncert_v1'))
import uc_common as U
import u3_lib as L

def now():
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat()

def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(4 << 20), b''):
            h.update(b)
    return h.hexdigest()

def clean(o):
    if isinstance(o, dict): return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)): return [clean(x) for x in o]
    if isinstance(o, np.ndarray): return clean(o.tolist())
    if isinstance(o, (np.floating, float)): return float(o) if np.isfinite(o) else None
    if isinstance(o, np.integer): return int(o)
    if isinstance(o, np.bool_): return bool(o)
    if isinstance(o, Path): return str(o)
    return o

def dump(p, obj):
    p = Path(p); p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(clean(obj), ensure_ascii=False, indent=2, allow_nan=False) + '\n')

def load(p): return json.loads(Path(p).read_text())
def pv(site, prior, r):
    with np.load(SRC / 'patch_values' / f'{site}__{prior}__R{r:.1f}.npz') as z:
        return {k: z[k] for k in z.files}

def progress(message):
    for p in (OUT / 'progress.md', DOC / 'progress.md'):
        with p.open('a') as f: f.write(f'\n- {now()} {message}\n')
