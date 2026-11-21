#!/usr/bin/env python3
"""PHD-MAIN-BASE151-v1 addendum 2 light bundle (host, stdlib; request 2026-11-19 '덧붙임 2' 3절).

  python3 b151_package_add2.py
  -> PH/delivery/PHD-MAIN-BASE151-v1_덧붙임2_<MMDD>-<HHMM>_light.zip
Members: 보고_덧붙임2.md at the top, then the tables (md, json), figures (png + json) of add2/, progress.md and the add2 scripts; no meshes, no models.
A manifest with sha256 of every member is written inside. scientific_verdict: null
"""
import datetime as dt
import hashlib
import json
import zipfile
from pathlib import Path

W = Path(__file__).resolve().parents[3]
PH = (W.parent / 'JointBuildGS-artifacts').resolve() / 'phase-payloads/phd'
DOC = W / 'docs/experiments/phd/main_base151_v1'
KST = dt.timezone(dt.timedelta(hours=9))
TABLES = ['gt_buildings', 'gt_summary', 'inputs_sizes', 'method_filter', 'run_records', 'stops', 'running_status']


def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(8 << 20), b''):
            h.update(b)
    return h.hexdigest()


def main():
    t = dt.datetime.now(KST)
    dest = PH / 'delivery' / f'PHD-MAIN-BASE151-v1_덧붙임2_{t:%m%d}-{t:%H%M}_light.zip'
    files = [DOC / '보고_덧붙임2.md', DOC / 'progress.md']
    files += sorted(p for p in (DOC / 'add2').rglob('*') if p.suffix in ('.md', '.json', '.png'))
    files += [W / 'scripts/phd/main_base151_v1' / n for n in ('b151_add2.py', 'b151_add2_ef.py', 'b151_add2_render.py', 'b151_add2_retrain.py', 'b151_add2_ef_tables.py')]
    missing = [str(p) for p in files if not p.exists()]
    assert not missing, missing
    man = []
    with zipfile.ZipFile(dest, 'w', zipfile.ZIP_DEFLATED) as z:
        for p in files:
            arc = p.name if p.name == '보고_덧붙임2.md' else str(p.relative_to(W))
            z.write(p, arc)
            man.append(dict(path=arc, bytes=p.stat().st_size, sha256=sha(p)))
        z.writestr('MANIFEST.json', json.dumps(dict(at=t.isoformat(), task='PHD-MAIN-BASE151-v1', label='덧붙임2 light', files=man,
                                                    note='no meshes, no models (request 4); the add2 scripts included', scientific_verdict=None), ensure_ascii=False, indent=1))
    print('ZIP', dest, len(man), dest.stat().st_size, sha(dest))


if __name__ == '__main__':
    main()
