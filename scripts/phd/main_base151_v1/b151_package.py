#!/usr/bin/env python3
"""PHD-MAIN-BASE151-v1 delivery bundles (host, stdlib).

  python3 b151_package.py <label> [extra_glob ...]
  -> PH/delivery/PHD-MAIN-BASE151-v1_<label>_<MMDD-HHMM>.zip  (label '' -> PHD-MAIN-BASE151-v1_<MMDD-HHMM>.zip)
Always: docs/experiments/phd/main_base151_v1 (md, tables, figures), configs/phd/main_base151_v1, scripts/phd/main_base151_v1 (no caches).
Extra globs are relative to OUT (e.g. 'runs/*/cell*/receipt.json'). A manifest with sha256 of every member is written inside.
scientific_verdict: null
"""
import datetime as dt
import hashlib
import json
import sys
import zipfile
from pathlib import Path

W = Path(__file__).resolve().parents[3]
ART = (W.parent / 'JointBuildGS-artifacts').resolve()
PH = ART / 'phase-payloads/phd'
OUT = PH / 'main_base151_v1/PHD-MAIN-BASE151-v1'
KST = dt.timezone(dt.timedelta(hours=9))


def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(8 << 20), b''):
            h.update(b)
    return h.hexdigest()


def main(label, *extra):
    t = dt.datetime.now(KST)
    name = f'PHD-MAIN-BASE151-v1_{label + "_" if label else ""}{t:%m%d-%H%M}.zip'
    dest = PH / 'delivery' / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    files = []
    for base in ['docs/experiments/phd/main_base151_v1', 'configs/phd/main_base151_v1', 'scripts/phd/main_base151_v1']:
        for p in sorted((W / base).rglob('*')):
            if p.is_file() and '__pycache__' not in p.parts:
                files.append((p, str(p.relative_to(W))))
    for g in extra:
        for p in sorted(OUT.glob(g)):
            if p.is_file() and ('payload/' + str(p.relative_to(OUT))) not in {a for _, a in files}:
                files.append((p, 'payload/' + str(p.relative_to(OUT))))
    man = []
    with zipfile.ZipFile(dest, 'w', zipfile.ZIP_DEFLATED) as z:
        for p, arc in files:
            z.write(p, arc)
            man.append(dict(path=arc, bytes=p.stat().st_size, sha256=sha(p)))
        z.writestr('MANIFEST.json', json.dumps(dict(at=t.isoformat(), task='PHD-MAIN-BASE151-v1', label=label, files=man, scientific_verdict=None),
                                               ensure_ascii=False, indent=1))
    print('ZIP', dest, len(man), dest.stat().st_size, sha(dest))


if __name__ == '__main__':
    main(*sys.argv[1:])
