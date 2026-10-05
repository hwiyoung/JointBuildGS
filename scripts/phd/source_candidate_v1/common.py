from __future__ import annotations
import hashlib
import json
from pathlib import Path
import numpy as np


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def clean(value):
    if isinstance(value, np.ndarray): return clean(value.tolist())
    if isinstance(value, np.generic): return clean(value.item())
    if isinstance(value, float) and not np.isfinite(value): return None
    if isinstance(value, dict): return {str(k): clean(v) for k,v in value.items()}
    if isinstance(value, (tuple,list)): return [clean(v) for v in value]
    return value


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        json.dump(clean(value), stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')


def describe(values):
    values = np.asarray(values, float)
    values = values[np.isfinite(values)]
    if not len(values): return dict(n=0,mean=None,median=None,p95=None,rmse=None)
    return dict(n=len(values),mean=float(values.mean()),median=float(np.median(values)),
                p95=float(np.quantile(values,.95)),rmse=float(np.sqrt(np.mean(values**2))))
